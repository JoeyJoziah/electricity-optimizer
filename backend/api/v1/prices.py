"""
Price API Endpoints

REST endpoints for electricity price data.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from models.price import (
    PriceRegion,
    PriceResponse,
    PriceListResponse,
    PriceHistoryResponse,
    PriceForecastResponse,
    PriceComparisonResponse,
)
from services.price_service import PriceService
from services.analytics_service import AnalyticsService
from api.dependencies import (
    get_price_service,
    get_analytics_service,
    get_current_user_optional,
    TokenData,
)


router = APIRouter()


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

    # Get statistics
    stats = await price_service.get_price_statistics(region, days)

    # For now, return simplified response
    # In production, would return actual historical data
    return PriceHistoryResponse(
        region=region.value,
        supplier=supplier,
        start_date=start,
        end_date=end,
        prices=[],  # Would be populated with actual data
        average_price=stats.get("avg_price"),
        min_price=stats.get("min_price"),
        max_price=stats.get("max_price"),
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
    prices = await price_service.get_price_comparison(region)

    if not prices:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No prices available for region '{region.value}'"
        )

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
    stats = await price_service.get_price_statistics(region, days)

    return PriceStatisticsResponse(
        region=region.value,
        period_days=days,
        min_price=stats.get("min_price"),
        max_price=stats.get("max_price"),
        avg_price=stats.get("avg_price"),
        count=stats.get("count", 0),
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
    trend = await analytics_service.get_price_trend(region, days)

    return {
        "region": region.value,
        "period_days": days,
        **trend,
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
    analysis = await analytics_service.get_peak_hours_analysis(region, days)

    return {
        "region": region.value,
        "period_days": days,
        **analysis,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
