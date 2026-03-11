"""
Internal ML endpoints.

Covers: /observe-forecasts, /learn, /observation-stats,
        /model-versions, /model-versions/compare
"""

from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, get_redis

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ObserveRequest(BaseModel):
    region: Optional[str] = Field(None, description="Region filter (optional)")


class LearnRequest(BaseModel):
    regions: Optional[List[str]] = Field(
        None, description="Regions to process (defaults to ['US'])"
    )
    days: int = Field(default=7, ge=1, le=90, description="Lookback window in days")


class ModelVersionCompareRequest(BaseModel):
    """Request body for the model-versions comparison endpoint."""

    model_name: str = Field(..., min_length=1, max_length=100)
    version_a_id: str = Field(..., description="UUID of the baseline version")
    version_b_id: str = Field(..., description="UUID of the candidate version")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


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


@router.get("/model-versions", tags=["Internal"])
async def list_model_versions(
    model_name: str = "ensemble",
    limit: int = 10,
    db: AsyncSession = Depends(get_db_session),
):
    """
    List recent model versions with their metrics.

    Returns the most recent `limit` versions for the given model_name,
    ordered newest-first.  Requires X-API-Key header.
    """
    from services.model_version_service import ModelVersionService

    svc = ModelVersionService(db)
    versions = await svc.list_versions(model_name, limit=limit)
    return {
        "model_name": model_name,
        "versions": [
            {
                "id": v.id,
                "version_tag": v.version_tag,
                "is_active": v.is_active,
                "metrics": v.metrics,
                "created_at": v.created_at.isoformat(),
                "promoted_at": v.promoted_at.isoformat() if v.promoted_at else None,
            }
            for v in versions
        ],
        "count": len(versions),
    }


@router.post("/model-versions/compare", tags=["Internal"])
async def compare_model_versions(
    body: ModelVersionCompareRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Trigger a side-by-side metric comparison for two model versions.

    Returns per-metric deltas (b - a) for all numeric metrics stored
    in the versions' metrics JSONB columns.  Requires X-API-Key header.
    """
    from services.model_version_service import ModelVersionService

    svc = ModelVersionService(db)
    try:
        result = await svc.compare_versions(body.version_a_id, body.version_b_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "model_name": body.model_name,
        "version_a": {
            "id": result.version_a.id,
            "version_tag": result.version_a.version_tag,
            "metrics": result.version_a.metrics,
        },
        "version_b": {
            "id": result.version_b.id,
            "version_tag": result.version_b.version_tag,
            "metrics": result.version_b.metrics,
        },
        "metric_comparison": result.metric_comparison,
    }
