"""
Propane API Endpoints

Public endpoints for propane prices, history, comparison, and timing advice.
No dealer directory (Decision D12: no propane dealer API).
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from services.propane_service import PropaneService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/rates/propane")


@router.get("", tags=["Propane"])
async def get_propane_prices(
    state: str | None = Query(None, description="2-letter state code"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get current propane prices, optionally filtered by state."""
    service = PropaneService(db)
    prices = await service.get_current_prices(state)
    return {
        "prices": prices,
        "tracked_states": PropaneService.get_tracked_states(),
    }


@router.get("/history", tags=["Propane"])
async def get_propane_history(
    state: str = Query(..., description="2-letter state code"),
    weeks: int = Query(12, ge=1, le=52, description="Number of weeks"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get propane price history for a state."""
    if not PropaneService.is_propane_state(state):
        raise HTTPException(
            status_code=404,
            detail=f"Propane tracking not available for {state.upper()}",
        )

    service = PropaneService(db)
    history = await service.get_price_history(state, weeks)
    comparison = await service.get_price_comparison(state)

    return {
        "state": state.upper(),
        "weeks": weeks,
        "history": history,
        "comparison": comparison,
    }


@router.get("/compare", tags=["Propane"])
async def compare_propane_price(
    state: str = Query(..., description="2-letter state code"),
    db: AsyncSession = Depends(get_db_session),
):
    """Compare a state's propane price against the national average."""
    service = PropaneService(db)
    comparison = await service.get_price_comparison(state)

    if not comparison:
        raise HTTPException(
            status_code=404,
            detail=f"No propane price data for {state.upper()}",
        )

    return comparison


@router.get("/timing", tags=["Propane"])
async def get_propane_timing(
    state: str = Query(..., description="2-letter state code"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get fill-up timing advice based on seasonal price patterns."""
    if not PropaneService.is_propane_state(state):
        raise HTTPException(
            status_code=404,
            detail=f"Propane tracking not available for {state.upper()}",
        )

    service = PropaneService(db)
    advice = await service.get_seasonal_advice(state)
    return advice
