"""
Price API Endpoints

CRUD endpoints for electricity price data: current, history, forecast, compare, refresh.
Analytics and SSE streaming live in prices_analytics.py and prices_sse.py respectively.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import (
    SessionData,
    get_price_service,
    require_tier,
    verify_api_key,
)
from config.database import get_pg_session
from config.settings import get_settings
from models.price import (
    Price,
    PriceComparisonResponse,
    PriceForecast,
    PriceForecastResponse,
    PriceHistoryResponse,
    PriceRegion,
    PriceResponse,
)
from services.price_service import PriceService

logger = structlog.get_logger(__name__)
settings = get_settings()

router = APIRouter(tags=["Prices"])


def _generate_mock_prices(region: str, count: int = 24) -> list[Price]:
    """Generate mock price data for development without DB"""
    now = datetime.now(UTC)
    prices = []
    for i in range(count):
        ts = now - timedelta(hours=count - i)
        hour = ts.hour
        base = round(0.22 + 0.06 * np.sin((hour - 6) * np.pi / 12), 4)
        prices.append(
            Price(
                region=region,
                supplier="Eversource Energy",
                price_per_kwh=Decimal(str(base)),
                timestamp=ts,
                currency="USD",
                is_peak=7 <= hour <= 19,
                carbon_intensity=round(150 + 50 * np.sin((hour - 6) * np.pi / 12), 1),
            )
        )
    return prices


# =============================================================================
# Request/Response Models
# =============================================================================


class CurrentPriceResponse(BaseModel):
    """Response for current price endpoint"""

    price: PriceResponse | None = None
    prices: list[PriceResponse] | None = None
    region: str
    timestamp: datetime
    source: str | None = None


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
    },
)
async def get_current_prices(
    region: PriceRegion = Query(..., description="Price region (e.g., uk, germany)"),
    supplier: str | None = Query(None, description="Filter by specific supplier"),
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
                    detail=f"No price found for supplier '{supplier}' in region '{region.value}'",
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
                timestamp=datetime.now(UTC),
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
            timestamp=datetime.now(UTC),
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
            timestamp=datetime.now(UTC),
            source="fallback",
        )


@router.get(
    "/history",
    response_model=PriceHistoryResponse,
    summary="Get historical electricity prices",
    responses={
        200: {"description": "Historical prices retrieved successfully"},
        400: {"description": "start_date must be before end_date"},
        422: {"description": "Invalid parameters"},
    },
)
async def get_price_history(
    region: PriceRegion = Query(..., description="Price region"),
    days: int = Query(
        7,
        ge=1,
        le=365,
        description="Number of days of history (ignored when start_date/end_date provided)",
    ),
    supplier: str | None = Query(None, description="Filter by supplier name"),
    start_date: datetime | None = Query(
        None, description="Filter by start date (ISO 8601, inclusive)"
    ),
    end_date: datetime | None = Query(None, description="Filter by end date (ISO 8601, inclusive)"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        24,
        ge=1,
        le=100,
        description="Records per page (1–100, default 24 = one day of hourly data)",
    ),
    price_service: PriceService = Depends(get_price_service),
):
    """
    Get historical electricity prices for a region.

    Returns a paginated page of price data for the specified time period,
    optionally filtered by supplier and/or explicit date range.

    Pagination defaults to page=1, page_size=24 (one day of hourly data).
    The response includes `total`, `page`, `page_size`, and `pages` so
    callers can navigate the full dataset without fetching all records at once.

    When start_date/end_date are supplied they take priority over `days`.
    Both datetimes are interpreted as UTC if no timezone offset is provided.
    """
    # Clamp page_size server-side as a defence-in-depth measure even though
    # FastAPI's ge/le constraints enforce it at the query-param layer.
    page = max(1, page)
    page_size = max(1, min(100, page_size))

    # Resolve the effective date window
    if start_date is not None or end_date is not None:
        # Explicit date range — ensure UTC and validate ordering
        resolved_end = (
            (end_date.replace(tzinfo=UTC) if end_date.tzinfo is None else end_date)
            if end_date is not None
            else datetime.now(UTC)
        )
        resolved_start = (
            (start_date.replace(tzinfo=UTC) if start_date.tzinfo is None else start_date)
            if start_date is not None
            else resolved_end - timedelta(days=days)
        )

        if resolved_start >= resolved_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be before end_date",
            )
    else:
        resolved_end = datetime.now(UTC)
        resolved_start = resolved_end - timedelta(days=days)

    try:
        prices, total = await price_service.get_historical_prices_paginated(
            region=region,
            start_date=resolved_start,
            end_date=resolved_end,
            page=page,
            page_size=page_size,
            supplier=supplier,
        )
        pages = max(1, (total + page_size - 1) // page_size)

        # Compute summary statistics from the returned page rows
        if prices:
            avg = sum(p.price_per_kwh for p in prices) / len(prices)
            avg_price = Decimal(str(round(avg, 4)))
            min_price = min(p.price_per_kwh for p in prices)
            max_price = max(p.price_per_kwh for p in prices)
        else:
            # Fall back to aggregate stats when no rows are returned
            stats = await price_service.get_price_statistics(region, days)
            avg_price = stats.get("avg_price")
            min_price = stats.get("min_price")
            max_price = stats.get("max_price")

        return PriceHistoryResponse(
            region=region.value,
            supplier=supplier,
            start_date=resolved_start,
            end_date=resolved_end,
            prices=prices,
            average_price=avg_price,
            min_price=min_price,
            max_price=max_price,
            source="live",
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("using_mock_history", reason=str(e))
        if settings.environment == "production":
            raise HTTPException(
                status_code=503,
                detail="Price service temporarily unavailable",
            )
        # Build the full mock dataset for the window, then slice it to the
        # requested page so that fallback behaviour mirrors live pagination.
        mock_all = _generate_mock_prices(region.value, days * 24)
        if supplier:
            mock_all = [p for p in mock_all if p.supplier == supplier]
        mock_all = [p for p in mock_all if resolved_start <= p.timestamp <= resolved_end]
        if not mock_all:
            mock_all = _generate_mock_prices(region.value, days * 24)

        total_mock = len(mock_all)
        pages_mock = max(1, (total_mock + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        mock_page = mock_all[offset : offset + page_size]

        avg = sum(float(p.price_per_kwh) for p in mock_all) / len(mock_all)
        return PriceHistoryResponse(
            region=region.value,
            supplier=supplier,
            start_date=resolved_start,
            end_date=resolved_end,
            prices=mock_page,
            average_price=Decimal(str(round(avg, 4))),
            min_price=min(p.price_per_kwh for p in mock_all),
            max_price=max(p.price_per_kwh for p in mock_all),
            source="fallback",
            total=total_mock,
            page=page,
            page_size=page_size,
            pages=pages_mock,
        )


@router.get(
    "/forecast",
    response_model=PriceForecastResponse,
    summary="Get price forecast",
    responses={
        200: {"description": "Forecast retrieved successfully"},
        404: {"description": "No forecast available"},
    },
)
async def get_price_forecast(
    region: PriceRegion = Query(..., description="Price region"),
    hours: int = Query(24, ge=1, le=168, description="Forecast horizon in hours"),
    supplier: str | None = Query(None, description="Filter by supplier"),
    current_user: SessionData = Depends(require_tier("pro")),
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
                detail=f"No forecast available for region '{region.value}'",
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
        now = datetime.now(UTC)
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
    },
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
            timestamp=datetime.now(UTC),
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
        now = datetime.now(UTC)
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
        503: {"description": "Price sync failed — no data retrieved"},
    },
)
async def refresh_prices(
    _api_key: bool = Depends(verify_api_key),
    session: AsyncSession = Depends(get_pg_session),
):
    """
    Trigger a refresh of electricity price data from external sources.

    Called by the GitHub Actions price-sync workflow (every 6 hours)
    to keep cached price data up to date.

    Returns HTTP 503 on failure so retry-curl will retry with backoff.
    """
    from fastapi.responses import JSONResponse

    from services.price_sync_service import sync_prices

    logger.info("price_refresh_triggered")
    result = await sync_prices(session)

    if result["status"] in ("error", "empty"):
        return JSONResponse(status_code=503, content=result)

    return result
