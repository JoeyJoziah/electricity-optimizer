"""
Forecast API — Multi-utility rate forecasting.

Pro tier gated. Provides trend-based forecasts for electricity,
natural gas, heating oil, and propane.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import get_db_session, require_tier
from services.forecast_service import FORECASTABLE_UTILITIES, ForecastService

router = APIRouter(prefix="/forecast")


@router.get(
    "/{utility_type}",
    tags=["Forecast"],
    summary="Get rate forecast for a utility type",
)
async def get_forecast(
    utility_type: str,
    state: str = Query(None, description="State code (e.g. CT, NY)"),
    horizon_days: int = Query(30, ge=1, le=90, description="Forecast horizon in days"),
    _user=Depends(require_tier("pro")),
    db=Depends(get_db_session),
):
    """
    Generate a rate forecast for the specified utility type.

    Requires Pro or Business subscription.

    - **electricity**: Uses historical price data with trend extrapolation
    - **natural_gas**: Simple linear trend from EIA data
    - **heating_oil**: Simple linear trend from EIA data
    - **propane**: Simple linear trend from EIA data
    """
    if utility_type not in FORECASTABLE_UTILITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid utility_type '{utility_type}'. "
                f"Valid values are: {', '.join(sorted(FORECASTABLE_UTILITIES))}"
            ),
        )
    service = ForecastService(db)
    return await service.get_forecast(
        utility_type=utility_type,
        state=state,
        horizon_days=horizon_days,
    )


@router.get(
    "",
    tags=["Forecast"],
    summary="List available forecast types",
)
async def list_forecast_types(
    _user=Depends(require_tier("pro")),
):
    """List all utility types that support forecasting."""
    return {
        "supported_types": list(FORECASTABLE_UTILITIES),
        "description": "Rate forecasting by utility type",
    }
