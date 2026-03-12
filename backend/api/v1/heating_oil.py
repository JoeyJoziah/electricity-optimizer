"""
Heating Oil API Endpoints

Public endpoints for heating oil prices, history, and dealer directory.
"""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from services.heating_oil_service import HeatingOilService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/rates/heating-oil")


@router.get("", tags=["Heating Oil"])
async def get_heating_oil_prices(
    state: Optional[str] = Query(None, description="2-letter state code"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get current heating oil prices, optionally filtered by state."""
    service = HeatingOilService(db)
    prices = await service.get_current_prices(state)
    return {
        "prices": prices,
        "tracked_states": HeatingOilService.get_tracked_states(),
    }


@router.get("/history", tags=["Heating Oil"])
async def get_heating_oil_history(
    state: str = Query(..., description="2-letter state code"),
    weeks: int = Query(12, ge=1, le=52, description="Number of weeks"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get heating oil price history for a state."""
    if not HeatingOilService.is_heating_oil_state(state):
        raise HTTPException(
            status_code=404,
            detail=f"Heating oil tracking not available for {state.upper()}",
        )

    service = HeatingOilService(db)
    history = await service.get_price_history(state, weeks)
    comparison = await service.get_price_comparison(state)

    return {
        "state": state.upper(),
        "weeks": weeks,
        "history": history,
        "comparison": comparison,
    }


@router.get("/dealers", tags=["Heating Oil"])
async def get_heating_oil_dealers(
    state: str = Query(..., description="2-letter state code"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db_session),
):
    """Get heating oil dealers for a state."""
    if not HeatingOilService.is_heating_oil_state(state):
        raise HTTPException(
            status_code=404,
            detail=f"Dealer directory not available for {state.upper()}",
        )

    service = HeatingOilService(db)
    dealers = await service.get_dealers(state, limit)
    return {
        "state": state.upper(),
        "count": len(dealers),
        "dealers": dealers,
    }


@router.get("/compare", tags=["Heating Oil"])
async def compare_heating_oil_price(
    state: str = Query(..., description="2-letter state code"),
    db: AsyncSession = Depends(get_db_session),
):
    """Compare a state's heating oil price against the national average."""
    service = HeatingOilService(db)
    comparison = await service.get_price_comparison(state)

    if not comparison:
        raise HTTPException(
            status_code=404,
            detail=f"No heating oil price data for {state.upper()}",
        )

    return comparison
