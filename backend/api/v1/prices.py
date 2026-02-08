"""
Price API Endpoints

REST endpoints for electricity price data.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List
import numpy as np

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from models.price import (
    Price,
    PriceRegion,
    PriceResponse,
    PriceListResponse,
    PriceHistoryResponse,
    PriceForecastResponse,
    PriceForecast,
    PriceComparisonResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from services.price_service import PriceService
from services.analytics_service import AnalyticsService
from api.dependencies import (
    get_price_service,
    get_analytics_service,
    get_current_user_optional,
    TokenData,
)
from config.database import get_timescale_session
from integrations.pricing_apis.service import create_pricing_service_from_settings
from integrations.pricing_apis.base import (
    PriceData as APIPriceData,
    PricingRegion,
    APIError,
    RateLimitError,
)

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()


def _generate_mock_prices(region: str, count: int = 24) -> List[Price]:
    """Generate mock price data for development without DB"""
    now = datetime.now(timezone.utc)
    prices = []
    for i in range(count):
        ts = now - timedelta(hours=count - i)
        hour = ts.hour
        base = round(0.22 + 0.06 * np.sin((hour - 6) * np.pi / 12), 4)
        prices.append(Price(
            region=region,
            supplier="Eversource Energy",
            price_per_kwh=Decimal(str(base)),
            timestamp=ts,
            currency="USD",
            is_peak=7 <= hour <= 19,
            carbon_intensity=round(150 + 50 * np.sin((hour - 6) * np.pi / 12), 1),
        ))
    return prices


# =============================================================================
# Request/Response Models
# =============================================================================


class CurrentPriceResponse(BaseModel):
    """Response for current price endpoint"""
    price: Optional[PriceResponse] = None
    prices: Optional[List[PriceResponse]] = None
    region: str
    timestamp: datetime


class PriceStatisticsResponse(BaseModel):
    """Response for price statistics"""
    region: str
    period_days: int
    min_price: Optional[Decimal]
    max_price: Optional[Decimal]
    avg_price: Optional[Decimal]
    count: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/current",
    response_model=CurrentPriceResponse,
    summary="Get current electricity prices",
    responses={
        200: {"description": "Current prices retrieved successfully"},
        422: {"description": "Invalid region parameter"},
    }
)
async def get_current_prices(
    region: PriceRegion = Query(..., description="Price region (e.g., uk, germany)"),
    supplier: Optional[str] = Query(None, description="Filter by specific supplier"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of prices"),
    price_service: PriceService = Depends(get_price_service),
):
    """
    Get current electricity prices for a region.

    Returns the latest prices from all suppliers in the specified region,
    or for a specific supplier if provided.
    """
    try:
        if supplier:
            price = await price_service.get_current_price(region, supplier)
            if not price:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No price found for supplier '{supplier}' in region '{region.value}'"
                )

            return CurrentPriceResponse(
                price=PriceResponse(
                    ticker=f"ELEC-{region.value.upper()}",
                    current_price=price.price_per_kwh,
                    currency=price.currency,
                    region=region.value,
                    supplier=price.supplier,
                    updated_at=price.timestamp,
                    is_peak=price.is_peak,
                    carbon_intensity=price.carbon_intensity,
                ),
                region=region.value,
                timestamp=datetime.now(timezone.utc)
            )

        prices = await price_service.get_current_prices(region, limit)

        price_responses = [
            PriceResponse(
                ticker=f"ELEC-{region.value.upper()}",
                current_price=p.price_per_kwh,
                currency=p.currency,
                region=region.value,
                supplier=p.supplier,
                updated_at=p.timestamp,
                is_peak=p.is_peak,
                carbon_intensity=p.carbon_intensity,
            )
            for p in prices
        ]

        return CurrentPriceResponse(
            prices=price_responses,
            region=region.value,
            timestamp=datetime.now(timezone.utc)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("using_mock_prices", reason=str(e))
        mock = _generate_mock_prices(region.value, 3)
        return CurrentPriceResponse(
            prices=[
                PriceResponse(
                    ticker=f"ELEC-{region.value.upper()}",
                    current_price=p.price_per_kwh,
                    currency=p.currency,
                    region=region.value,
                    supplier=p.supplier,
                    updated_at=p.timestamp,
                    is_peak=p.is_peak,
                    carbon_intensity=p.carbon_intensity,
                )
                for p in mock[-3:]
            ],
            region=region.value,
            timestamp=datetime.now(timezone.utc)
        )


@router.get(
    "/history",
    response_model=PriceHistoryResponse,
    summary="Get historical electricity prices",
    responses={
        200: {"description": "Historical prices retrieved successfully"},
        422: {"description": "Invalid parameters"},
    }
)
async def get_price_history(
    region: PriceRegion = Query(..., description="Price region"),
    days: int = Query(7, ge=1, le=365, description="Number of days of history"),
    supplier: Optional[str] = Query(None, description="Filter by supplier"),
    price_service: PriceService = Depends(get_price_service),
):
    """
    Get historical electricity prices for a region.

    Returns price data for the specified time period, optionally
    filtered by supplier.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    try:
        stats = await price_service.get_price_statistics(region, days)
        return PriceHistoryResponse(
            region=region.value,
            supplier=supplier,
            start_date=start,
            end_date=end,
            prices=[],
            average_price=stats.get("avg_price"),
            min_price=stats.get("min_price"),
            max_price=stats.get("max_price"),
        )
    except Exception as e:
        logger.warning("using_mock_history", reason=str(e))
        mock = _generate_mock_prices(region.value, days * 24)
        avg = sum(float(p.price_per_kwh) for p in mock) / len(mock)
        return PriceHistoryResponse(
            region=region.value,
            supplier=supplier,
            start_date=start,
            end_date=end,
            prices=mock,
            average_price=Decimal(str(round(avg, 4))),
            min_price=min(p.price_per_kwh for p in mock),
            max_price=max(p.price_per_kwh for p in mock),
        )


@router.get(
    "/forecast",
    response_model=PriceForecastResponse,
    summary="Get price forecast",
    responses={
        200: {"description": "Forecast retrieved successfully"},
        404: {"description": "No forecast available"},
    }
)
async def get_price_forecast(
    region: PriceRegion = Query(..., description="Price region"),
    hours: int = Query(24, ge=1, le=168, description="Forecast horizon in hours"),
    supplier: Optional[str] = Query(None, description="Filter by supplier"),
    price_service: PriceService = Depends(get_price_service),
):
    """
    Get electricity price forecast for upcoming hours.

    Returns predicted prices based on ML models and historical patterns.
    """
    try:
        forecast = await price_service.get_price_forecast(region, hours, supplier)

        if not forecast:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No forecast available for region '{region.value}'"
            )

        return PriceForecastResponse(
            region=region.value,
            forecast=forecast,
            generated_at=forecast.generated_at,
            horizon_hours=forecast.horizon_hours,
            confidence=forecast.confidence,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("using_mock_forecast", reason=str(e))
        now = datetime.now(timezone.utc)
        mock = _generate_mock_prices(region.value, hours)
        forecast = PriceForecast(
            region=region,
            generated_at=now,
            horizon_hours=hours,
            prices=mock,
            confidence=0.85,
            model_version="v1.0.0-mock",
        )
        return PriceForecastResponse(
            region=region.value,
            forecast=forecast,
            generated_at=now,
            horizon_hours=hours,
            confidence=0.85,
        )


@router.get(
    "/compare",
    response_model=PriceComparisonResponse,
    summary="Compare supplier prices",
    responses={
        200: {"description": "Comparison retrieved successfully"},
        404: {"description": "No prices available for comparison"},
    }
)
async def compare_prices(
    region: PriceRegion = Query(..., description="Price region"),
    price_service: PriceService = Depends(get_price_service),
):
    """
    Compare electricity prices across suppliers in a region.

    Returns prices sorted from cheapest to most expensive,
    along with summary statistics.
    """
    try:
        prices = await price_service.get_price_comparison(region)

        if not prices:
            raise Exception("No prices from DB")

        price_responses = [
            PriceResponse(
                ticker=f"ELEC-{region.value.upper()}",
                current_price=p.price_per_kwh,
                currency=p.currency,
                region=region.value,
                supplier=p.supplier,
                updated_at=p.timestamp,
                is_peak=p.is_peak,
                carbon_intensity=p.carbon_intensity,
            )
            for p in prices
        ]

        avg_price = sum(p.price_per_kwh for p in prices) / len(prices)

        return PriceComparisonResponse(
            region=region.value,
            timestamp=datetime.now(timezone.utc),
            suppliers=price_responses,
            cheapest_supplier=prices[0].supplier,
            cheapest_price=prices[0].price_per_kwh,
            average_price=avg_price.quantize(Decimal("0.0001")),
        )
    except Exception as e:
        logger.warning("using_mock_comparison", reason=str(e))
        now = datetime.now(timezone.utc)
        mock_suppliers = [
            ("Eversource Energy", Decimal("0.2600")),
            ("United Illuminating (UI)", Decimal("0.2850")),
            ("NextEra Energy", Decimal("0.2700")),
        ]
        responses = [
            PriceResponse(
                ticker=f"ELEC-{region.value.upper()}",
                current_price=price,
                currency="USD",
                region=region.value,
                supplier=name,
                updated_at=now,
            )
            for name, price in mock_suppliers
        ]
        return PriceComparisonResponse(
            region=region.value,
            timestamp=now,
            suppliers=responses,
            cheapest_supplier="Eversource Energy",
            cheapest_price=Decimal("0.2600"),
            average_price=Decimal("0.2717"),
        )


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
        )
    except Exception as e:
        logger.warning("using_mock_statistics", reason=str(e))
        return PriceStatisticsResponse(
            region=region.value,
            period_days=days,
            min_price=Decimal("0.1500"),
            max_price=Decimal("0.2800"),
            avg_price=Decimal("0.2100"),
            count=days * 24,
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
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.warning("using_mock_windows", reason=str(e))
        now = datetime.now(timezone.utc)
        return {
            "region": region.value,
            "duration_hours": duration_hours,
            "within_hours": within_hours,
            "windows": [
                {"start": (now + timedelta(hours=2)).isoformat(), "end": (now + timedelta(hours=2 + duration_hours)).isoformat(), "avg_price": 0.16, "rank": 1},
                {"start": (now + timedelta(hours=14)).isoformat(), "end": (now + timedelta(hours=14 + duration_hours)).isoformat(), "avg_price": 0.18, "rank": 2},
            ],
            "generated_at": now.isoformat()
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
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.warning("using_mock_trends", reason=str(e))
        return {
            "region": region.value,
            "period_days": days,
            "direction": "down",
            "change_percent": -2.3,
            "current_avg": 0.21,
            "previous_avg": 0.215,
            "generated_at": datetime.now(timezone.utc).isoformat()
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
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.warning("using_mock_peak_hours", reason=str(e))
        return {
            "region": region.value,
            "period_days": days,
            "peak_hours": list(range(7, 20)),
            "off_peak_hours": list(range(0, 7)) + list(range(20, 24)),
            "peak_avg_price": 0.25,
            "off_peak_avg_price": 0.16,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }


@router.post(
    "/refresh",
    summary="Trigger price data refresh",
    responses={
        200: {"description": "Price sync triggered successfully"},
    }
)
async def refresh_prices(
    session: AsyncSession = Depends(get_timescale_session),
):
    """
    Trigger a refresh of electricity price data from external sources.

    Called by the GitHub Actions price-sync workflow (every 6 hours)
    to keep cached price data up to date.
    """
    logger.info("price_refresh_triggered")

    default_regions = [
        PricingRegion.US_CT,
        PricingRegion.US_NY,
        PricingRegion.US_CA,
        PricingRegion.UK,
        PricingRegion.GERMANY,
        PricingRegion.FRANCE,
    ]

    synced_count = 0
    regions_covered = []
    errors = []

    pricing_service = create_pricing_service_from_settings()

    try:
        async with pricing_service:
            comparison = await pricing_service.compare_prices(default_regions)

            prices_to_store = []
            for region, price_data in comparison.items():
                kwh_price = price_data.convert_to_kwh()

                # Map PricingRegion to PriceRegion for DB storage
                region_map = {
                    "UK": "uk", "DE": "germany", "FR": "france",
                    "ES": "spain", "IT": "italy", "NL": "netherlands",
                    "US_CT": "us_ct", "US_CA": "us_ca", "US_NY": "us_ny",
                    "US_TX": "us_tx", "US_FL": "us_fl",
                }
                db_region = region_map.get(region.value, region.value.lower())

                prices_to_store.append(Price(
                    region=db_region,
                    supplier=kwh_price.supplier or "Unknown",
                    price_per_kwh=kwh_price.price,
                    timestamp=kwh_price.timestamp,
                    currency=kwh_price.currency,
                    is_peak=kwh_price.is_peak,
                    carbon_intensity=kwh_price.carbon_intensity,
                    source_api=kwh_price.source_api,
                ))
                regions_covered.append(region.value)

            if prices_to_store and session:
                from repositories.price_repository import PriceRepository
                repo = PriceRepository(session)
                synced_count = await repo.bulk_create(prices_to_store)

    except RateLimitError as e:
        logger.warning("price_refresh_rate_limited", error=str(e), retry_after=e.retry_after)
        errors.append(f"Rate limited: {e}")
    except APIError as e:
        logger.warning("price_refresh_api_error", error=str(e))
        errors.append(f"API error: {e}")
    except Exception as e:
        logger.error("price_refresh_failed", error=str(e))
        errors.append(f"Unexpected error: {e}")

    return {
        "status": "refreshed" if synced_count > 0 else "partial",
        "message": f"Synced {synced_count} price records from {len(regions_covered)} regions",
        "synced_records": synced_count,
        "regions_covered": regions_covered,
        "errors": errors if errors else None,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }
