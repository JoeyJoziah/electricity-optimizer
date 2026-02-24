"""
Price API Endpoints

CRUD endpoints for electricity price data: current, history, forecast, compare, refresh.
Analytics and SSE streaming live in prices_analytics.py and prices_sse.py respectively.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List
import numpy as np

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from models.price import (
    Price,
    PriceRegion,
    PriceResponse,
    PriceHistoryResponse,
    PriceForecastResponse,
    PriceForecast,
    PriceComparisonResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from services.price_service import PriceService
from api.dependencies import (
    get_price_service,
    verify_api_key,
)
from config.database import get_timescale_session
from config.settings import get_settings

import structlog

logger = structlog.get_logger(__name__)
settings = get_settings()

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
    source: Optional[str] = None


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
                timestamp=datetime.now(timezone.utc),
                source="live",
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
            timestamp=datetime.now(timezone.utc),
            source="live",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("using_mock_prices", reason=str(e))
        if settings.environment == "production":
            raise HTTPException(
                status_code=503,
                detail="Price service temporarily unavailable",
            )
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
            timestamp=datetime.now(timezone.utc),
            source="fallback",
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
            source="live",
        )
    except Exception as e:
        logger.error("using_mock_history", reason=str(e))
        if settings.environment == "production":
            raise HTTPException(
                status_code=503,
                detail="Price service temporarily unavailable",
            )
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
            source="fallback",
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
            source="live",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("using_mock_forecast", reason=str(e))
        if settings.environment == "production":
            raise HTTPException(
                status_code=503,
                detail="Price service temporarily unavailable",
            )
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
            source="fallback",
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
            source="live",
        )
    except Exception as e:
        logger.error("using_mock_comparison", reason=str(e))
        if settings.environment == "production":
            raise HTTPException(
                status_code=503,
                detail="Price service temporarily unavailable",
            )
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
            source="fallback",
        )


@router.post(
    "/refresh",
    summary="Trigger price data refresh",
    responses={
        200: {"description": "Price sync triggered successfully"},
    }
)
async def refresh_prices(
    _api_key: bool = Depends(verify_api_key),
    session: AsyncSession = Depends(get_timescale_session),
):
    """
    Trigger a refresh of electricity price data from external sources.

    Called by the GitHub Actions price-sync workflow (every 6 hours)
    to keep cached price data up to date.
    """
    from services.price_sync_service import sync_prices

    logger.info("price_refresh_triggered")
    return await sync_prices(session)
