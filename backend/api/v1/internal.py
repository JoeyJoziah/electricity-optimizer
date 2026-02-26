"""
Internal API Endpoints

API-key-protected endpoints for scheduled jobs:
- observe-forecasts: Backfill actual prices into forecast observations
- learn: Run the nightly adaptive learning cycle
"""

from typing import Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import verify_api_key, get_db_session, get_redis
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(
    dependencies=[Depends(verify_api_key)],
)


class ObserveRequest(BaseModel):
    region: Optional[str] = Field(None, description="Region filter (optional)")


class LearnRequest(BaseModel):
    regions: Optional[List[str]] = Field(None, description="Regions to process (defaults to ['US'])")
    days: int = Field(default=7, ge=1, le=90, description="Lookback window in days")


@router.post("/observe-forecasts", tags=["Internal"])
async def observe_forecasts(
    request: ObserveRequest = ObserveRequest(),
    db=Depends(get_db_session),
):
    """
    Backfill actual prices into unobserved forecast rows.

    Matches forecast_observations to electricity_prices by region and hour,
    setting actual_price and observed_at.
    """
    from services.observation_service import ObservationService

    obs = ObservationService(db)

    try:
        count = await obs.observe_actuals_batch(region=request.region)
        return {
            "status": "ok",
            "observations_updated": count,
            "region": request.region or "all",
        }
    except Exception as e:
        logger.error("observe_forecasts_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Observation failed: {str(e)}")


@router.post("/learn", tags=["Internal"])
async def run_learning_cycle(
    request: LearnRequest = LearnRequest(),
    db=Depends(get_db_session),
    redis=Depends(get_redis),
):
    """
    Run the adaptive learning cycle.

    Computes rolling accuracy, detects bias, updates ensemble weights in Redis,
    stores bias correction vectors, and prunes stale patterns.
    """
    from services.observation_service import ObservationService
    from services.hnsw_vector_store import HNSWVectorStore
    from services.learning_service import LearningService

    obs = ObservationService(db)
    vs = HNSWVectorStore()
    learner = LearningService(obs, vs, redis)

    try:
        results = await learner.run_full_cycle(
            regions=request.regions,
            days=request.days,
        )
        return {
            "status": "ok",
            "results": results,
        }
    except Exception as e:
        logger.error("learning_cycle_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Learning cycle failed: {str(e)}")


class FlagUpdateBody(BaseModel):
    enabled: Optional[bool] = Field(None, description="Enable or disable the flag")
    tier_required: Optional[str] = Field(None, description="Minimum subscription tier required")
    percentage: Optional[int] = Field(None, ge=0, le=100, description="Rollout percentage (0-100)")


@router.put("/flags/{name}", tags=["Internal"])
async def update_feature_flag(
    name: str,
    body: FlagUpdateBody,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Partially update a feature flag.

    Requires a valid X-API-Key header (enforced by the router-level dependency).
    Returns 404 when the flag name is unknown or no fields were supplied.
    """
    from services.feature_flag_service import FeatureFlagService

    svc = FeatureFlagService(db)
    success = await svc.update_flag(
        name,
        enabled=body.enabled,
        tier_required=body.tier_required,
        percentage=body.percentage,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Flag not found or no changes provided")
    return {"success": True}


@router.get("/flags", tags=["Internal"])
async def list_feature_flags(
    db: AsyncSession = Depends(get_db_session),
):
    """Return all feature flags (admin/ops view). Requires API key."""
    from services.feature_flag_service import FeatureFlagService

    svc = FeatureFlagService(db)
    flags = await svc.get_all_flags()
    return {"flags": flags}


@router.post("/maintenance/cleanup", tags=["Internal"])
async def run_maintenance(db: AsyncSession = Depends(get_db_session)):
    """
    Run data retention cleanup tasks.

    Deletes activity logs older than 365 days and bill upload records
    (plus associated extracted rates and files) older than 730 days.

    Requires a valid X-API-Key header (enforced by the router-level dependency).
    """
    from services.maintenance_service import MaintenanceService

    svc = MaintenanceService(db)
    logs = await svc.cleanup_activity_logs()
    uploads = await svc.cleanup_expired_uploads()
    return {"activity_logs": logs, "uploads": uploads}


@router.get("/observation-stats", tags=["Internal"])
async def get_observation_stats(
    region: str = "US",
    days: int = 7,
    db=Depends(get_db_session),
):
    """
    Get forecast observation accuracy statistics.
    """
    from services.observation_service import ObservationService

    obs = ObservationService(db)

    try:
        accuracy = await obs.get_forecast_accuracy(region, days)
        bias = await obs.get_hourly_bias(region, days)
        return {
            "region": region,
            "days": days,
            "accuracy": accuracy,
            "hourly_bias": bias,
        }
    except Exception as e:
        logger.error("observation_stats_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
