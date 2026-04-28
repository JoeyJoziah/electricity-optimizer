"""
Internal operations endpoints.

Covers: /maintenance/cleanup, /health-data, /kpi-report,
        /flags, /flags/{name}
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class FlagUpdateBody(BaseModel):
    enabled: bool | None = Field(None, description="Enable or disable the flag")
    tier_required: str | None = Field(
        None, description="Minimum subscription tier required"
    )
    percentage: int | None = Field(
        None, ge=0, le=100, description="Rollout percentage (0-100)"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


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
        raise HTTPException(
            status_code=404, detail="Flag not found or no changes provided"
        )
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

    Deletes activity logs older than 365 days, bill upload records
    (plus associated extracted rates and files) older than 730 days,
    electricity prices older than 365 days, forecast observations
    older than 90 days, weather cache older than 30 days, scraped
    rates older than 90 days, market intelligence older than 180 days,
    and Stripe webhook idempotency records older than 72 hours.

    Requires a valid X-API-Key header (enforced by the router-level dependency).
    """
    from services.maintenance_service import MaintenanceService

    svc = MaintenanceService(db)
    results = {}
    errors = []

    for task_name, task_fn in [
        ("activity_logs", svc.cleanup_activity_logs),
        ("uploads", svc.cleanup_expired_uploads),
        ("prices", svc.cleanup_old_prices),
        ("observations", svc.cleanup_old_observations),
        ("weather_cache", svc.cleanup_weather_cache),
        ("scraped_rates", svc.cleanup_scraped_rates),
        ("market_intelligence", svc.cleanup_market_intelligence),
        ("stripe_processed_events", svc.cleanup_stripe_processed_events),
    ]:
        try:
            results[task_name] = await task_fn()
        except Exception as e:
            logger.warning("maintenance_task_failed", task=task_name, error=str(e))
            results[task_name] = {"error": "Task failed. See server logs."}
            errors.append(task_name)

    results["status"] = "partial" if errors else "ok"
    return results


@router.get("/health-data", tags=["Internal"])
async def data_health_check(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Return row counts and last-write timestamps for key data tables.

    Provides a quick health overview without direct DB access.
    Protected by the router-level X-API-Key dependency.
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tables = [
        ("electricity_prices", "timestamp"),
        ("supplier_registry", "updated_at"),
        ("weather_cache", "fetched_at"),
        ("market_intelligence", "fetched_at"),
        ("scraped_rates", "fetched_at"),
        ("alert_history", "created_at"),
        ("users", "created_at"),
        ("user_connections", "updated_at"),
        ("forecast_observations", "created_at"),
        ("payment_retry_history", "created_at"),
    ]

    # Validate all table/column identifiers against hardcoded allowlist
    _HEALTH_TABLES = frozenset(t[0] for t in tables)
    _HEALTH_COLS = frozenset(t[1] for t in tables)
    for table_name, ts_col in tables:
        assert (
            table_name in _HEALTH_TABLES and ts_col in _HEALTH_COLS
        ), f"Unexpected health check identifier: {table_name}.{ts_col}"

    health = {}
    for table_name, ts_col in tables:
        try:
            count_result = await db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            count = count_result.scalar() or 0

            last_write = None
            if count > 0:
                ts_result = await db.execute(
                    text(f"SELECT MAX({ts_col}) FROM {table_name}")
                )
                last_write_val = ts_result.scalar()
                if last_write_val:
                    last_write = str(last_write_val)

            health[table_name] = {
                "count": count,
                "last_write": last_write,
            }
        except Exception:
            health[table_name] = {"count": -1, "error": "query failed"}

    # Flag critical tables that should not be empty
    critical_empty = [
        t
        for t in ["electricity_prices", "supplier_registry", "weather_cache"]
        if health.get(t, {}).get("count", 0) == 0
    ]

    return {
        "status": "warning" if critical_empty else "ok",
        "checked_at": datetime.now(UTC).isoformat(),
        "critical_empty": critical_empty,
        "tables": health,
    }


@router.post("/kpi-report", tags=["Internal"])
async def generate_kpi_report(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Aggregate key business metrics and return them as JSON.

    Metrics: active users (7d), total users, prices tracked, alerts sent today,
    connection status breakdown, subscription breakdown, estimated MRR,
    weather data freshness.

    Protected by the router-level X-API-Key dependency.
    """
    from services.kpi_report_service import KPIReportService

    service = KPIReportService(db)

    try:
        metrics = await service.aggregate_metrics()
        generated_at = datetime.now(UTC).isoformat()

        return {
            "status": "ok",
            "generated_at": generated_at,
            "metrics": metrics,
        }

    except Exception as exc:
        logger.error("kpi_report_failed", error=str(exc))
        raise HTTPException(
            status_code=500, detail="KPI report failed. See server logs."
        )
