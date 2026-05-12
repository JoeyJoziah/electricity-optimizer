"""
Water Rate API Endpoints

Public endpoints for water rate benchmarking and conservation tips.
Monitoring only — no "switch" CTA (Decision D4: water is a monopoly).
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from services.water_rate_service import AVG_MONTHLY_GALLONS, WaterRateService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/rates/water")


@router.get("", tags=["Water"])
async def get_water_rates(
    state: str | None = Query(None, description="2-letter state code"),
    municipality: str | None = Query(None, description="Municipality name"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get water rates, optionally filtered by state or municipality."""
    service = WaterRateService(db)

    if municipality and state:
        rate = await service.get_rate_by_municipality(municipality, state)
        if not rate:
            raise HTTPException(
                status_code=404,
                detail=f"No water rate data for {municipality}, {state.upper()}",
            )
        return {"rates": [rate]}

    rates = await service.get_rates(state)
    return {"rates": rates, "count": len(rates)}


@router.get("/benchmark", tags=["Water"])
async def get_water_benchmark(
    state: str = Query(..., description="2-letter state code"),
    usage_gallons: int = Query(
        AVG_MONTHLY_GALLONS,
        ge=0,
        le=100000,
        description="Monthly usage in gallons",
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """Compare water rates across municipalities in a state."""
    service = WaterRateService(db)
    benchmark = await service.get_benchmark(state)

    if benchmark["municipalities"] == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No water rate data for {state.upper()}",
        )

    return benchmark


@router.get("/tips", tags=["Water"])
async def get_water_tips():
    """Get water conservation recommendations."""
    tips = WaterRateService.get_conservation_tips()
    return {
        "tips": tips,
        "count": len(tips),
        "estimated_annual_savings_gallons": sum(
            t["estimated_savings_gallons"] for t in tips
        ),
    }
