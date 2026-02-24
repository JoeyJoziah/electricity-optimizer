"""
Price Analytics Endpoints

Analytics and statistical endpoints for price data:
- statistics, trends, peak hours, optimal usage windows
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from models.price import PriceRegion
from services.price_service import PriceService
from services.analytics_service import AnalyticsService
from api.dependencies import get_price_service, get_analytics_service
from config.settings import get_settings

import structlog

logger = structlog.get_logger(__name__)
settings = get_settings()

router = APIRouter()


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class PriceStatisticsResponse(BaseModel):
    """Response for price statistics"""
    region: str
    period_days: int
    min_price: Optional[Decimal]
    max_price: Optional[Decimal]
    avg_price: Optional[Decimal]
    count: int
    source: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/statistics",
    response_model=PriceStatisticsResponse,
    summary="Get price statistics",
    responses={
        200: {"description": "Statistics retrieved successfully"},
    }
)
async def get_price_statistics(
    region: PriceRegion = Query(..., description="Price region"),
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
    price_service: PriceService = Depends(get_price_service),
):
    """
    Get price statistics for a region over a time period.

    Returns min, max, and average prices along with data point count.
    """
    try:
        stats = await price_service.get_price_statistics(region, days)
        return PriceStatisticsResponse(
            region=region.value,
            period_days=days,
            min_price=stats.get("min_price"),
            max_price=stats.get("max_price"),
            avg_price=stats.get("avg_price"),
            count=stats.get("count", 0),
            source="live",
        )
    except Exception as e:
        logger.error("using_mock_statistics", reason=str(e))
        if settings.environment == "production":
            raise HTTPException(
                status_code=503,
                detail="Price service temporarily unavailable",
            )
        return PriceStatisticsResponse(
            region=region.value,
            period_days=days,
            min_price=Decimal("0.1500"),
            max_price=Decimal("0.2800"),
            avg_price=Decimal("0.2100"),
            count=days * 24,
            source="fallback",
        )


@router.get(
    "/optimal-windows",
    summary="Get optimal usage windows",
    responses={
        200: {"description": "Optimal windows retrieved successfully"},
    }
)
async def get_optimal_usage_windows(
    region: PriceRegion = Query(..., description="Price region"),
    duration_hours: int = Query(2, ge=1, le=12, description="Required usage duration"),
    within_hours: int = Query(24, ge=1, le=48, description="Time window to search"),
    supplier: Optional[str] = Query(None, description="Filter by supplier"),
    price_service: PriceService = Depends(get_price_service),
):
    """
    Find optimal low-price windows for appliance usage.

    Returns the best times to run appliances based on price forecasts.
    """
    try:
        windows = await price_service.get_optimal_usage_windows(
            region=region,
            duration_hours=duration_hours,
            within_hours=within_hours,
            supplier=supplier
        )
        return {
            "region": region.value,
            "duration_hours": duration_hours,
            "within_hours": within_hours,
            "windows": windows,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "live",
        }
    except Exception as e:
        logger.error("using_mock_windows", reason=str(e))
        if settings.environment == "production":
            raise HTTPException(
                status_code=503,
                detail="Price service temporarily unavailable",
            )
        now = datetime.now(timezone.utc)
        return {
            "region": region.value,
            "duration_hours": duration_hours,
            "within_hours": within_hours,
            "windows": [
                {"start": (now + timedelta(hours=2)).isoformat(), "end": (now + timedelta(hours=2 + duration_hours)).isoformat(), "avg_price": 0.16, "rank": 1},
                {"start": (now + timedelta(hours=14)).isoformat(), "end": (now + timedelta(hours=14 + duration_hours)).isoformat(), "avg_price": 0.18, "rank": 2},
            ],
            "generated_at": now.isoformat(),
            "source": "fallback",
        }


@router.get(
    "/trends",
    summary="Get price trends",
    responses={
        200: {"description": "Trends retrieved successfully"},
    }
)
async def get_price_trends(
    region: PriceRegion = Query(..., description="Price region"),
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get price trend analysis for a region.

    Returns trend direction, percentage change, and detailed analytics.
    """
    try:
        trend = await analytics_service.get_price_trend(region, days)
        return {
            "region": region.value,
            "period_days": days,
            **trend,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "live",
        }
    except Exception as e:
        logger.error("using_mock_trends", reason=str(e))
        if settings.environment == "production":
            raise HTTPException(
                status_code=503,
                detail="Price service temporarily unavailable",
            )
        return {
            "region": region.value,
            "period_days": days,
            "direction": "down",
            "change_percent": -2.3,
            "current_avg": 0.21,
            "previous_avg": 0.215,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "fallback",
        }


@router.get(
    "/peak-hours",
    summary="Get peak hours analysis",
    responses={
        200: {"description": "Peak hours analysis retrieved successfully"},
    }
)
async def get_peak_hours_analysis(
    region: PriceRegion = Query(..., description="Price region"),
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Analyze peak and off-peak hours based on pricing.

    Returns identified peak/off-peak hours and hourly price averages.
    """
    try:
        analysis = await analytics_service.get_peak_hours_analysis(region, days)
        return {
            "region": region.value,
            "period_days": days,
            **analysis,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "live",
        }
    except Exception as e:
        logger.error("using_mock_peak_hours", reason=str(e))
        if settings.environment == "production":
            raise HTTPException(
                status_code=503,
                detail="Price service temporarily unavailable",
            )
        return {
            "region": region.value,
            "period_days": days,
            "peak_hours": list(range(7, 20)),
            "off_peak_hours": list(range(0, 7)) + list(range(20, 24)),
            "peak_avg_price": 0.25,
            "off_peak_avg_price": 0.16,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "fallback",
        }
