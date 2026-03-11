"""
Internal data quality endpoints.

Covers: /data-quality/freshness, /data-quality/anomalies, /data-quality/sources
"""

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from services.data_quality_service import DataQualityService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/data-quality")


@router.get("/freshness")
async def freshness_report(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get data freshness status per utility_type and region.

    Returns stale indicators based on expected freshness thresholds.
    """
    service = DataQualityService(db)
    report = await service.get_freshness_report()

    stale_count = sum(1 for r in report if r["is_stale"])

    return {
        "total_entries": len(report),
        "stale_count": stale_count,
        "entries": report,
    }


@router.get("/anomalies")
async def anomalies_report(
    lookback_days: int = Query(30, ge=1, le=365, description="Days to look back"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get recently detected rate anomalies.

    Flags rates deviating > 3 standard deviations from rolling average.
    """
    service = DataQualityService(db)
    anomalies = await service.detect_anomalies(lookback_days=lookback_days)

    return {
        "lookback_days": lookback_days,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }


@router.get("/sources")
async def sources_report(
    window_hours: int = Query(24, ge=1, le=720, description="Hours to analyze"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get source reliability scores.

    Tracks success/failure rates per data source within the time window.
    """
    service = DataQualityService(db)
    sources = await service.get_source_reliability(window_hours=window_hours)

    degraded_count = sum(1 for s in sources if s["is_degraded"])

    return {
        "window_hours": window_hours,
        "total_sources": len(sources),
        "degraded_count": degraded_count,
        "sources": sources,
    }
