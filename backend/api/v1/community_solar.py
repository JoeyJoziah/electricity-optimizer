"""
Community Solar API Endpoints

Public endpoints for community solar program discovery,
savings estimation, and program details.
"""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from models.region import COMMUNITY_SOLAR_STATES
from services.community_solar_service import CommunitySolarService

router = APIRouter(tags=["Community Solar"])


@router.get("/programs")
async def get_community_solar_programs(
    state: str = Query(..., description="2-letter state code (e.g. NY, MA)"),
    enrollment_status: str | None = Query(None, description="Filter: open, waitlist, closed"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
):
    """Get community solar programs available in a state."""
    state_upper = state.upper()

    if state_upper not in COMMUNITY_SOLAR_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Community solar programs not tracked for state '{state_upper}'. "
                   f"Available states: {sorted(COMMUNITY_SOLAR_STATES)}",
        )

    if enrollment_status and enrollment_status not in ("open", "waitlist", "closed"):
        raise HTTPException(
            status_code=400,
            detail="enrollment_status must be one of: open, waitlist, closed",
        )

    service = CommunitySolarService(db)
    programs = await service.get_programs(
        state=state_upper,
        enrollment_status=enrollment_status,
        limit=limit,
    )

    return {
        "state": state_upper,
        "count": len(programs),
        "programs": programs,
    }


@router.get("/savings")
async def estimate_community_solar_savings(
    monthly_bill: str = Query(..., description="Current monthly electricity bill in dollars"),
    savings_percent: str = Query(..., description="Program savings percentage (e.g. 10)"),
):
    """Estimate savings from a community solar program."""
    try:
        bill = Decimal(monthly_bill)
        pct = Decimal(savings_percent)
    except InvalidOperation:
        raise HTTPException(
            status_code=400,
            detail="monthly_bill and savings_percent must be valid decimal numbers",
        )

    if bill <= 0:
        raise HTTPException(status_code=400, detail="monthly_bill must be positive")
    if pct <= 0 or pct > 100:
        raise HTTPException(status_code=400, detail="savings_percent must be between 0 and 100")

    savings = CommunitySolarService.calculate_savings(
        monthly_bill=bill,
        savings_percent=pct,
    )
    return savings


@router.get("/program/{program_id}")
async def get_community_solar_program(
    program_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Get details for a specific community solar program."""
    service = CommunitySolarService(db)
    program = await service.get_program_by_id(program_id)

    if not program:
        raise HTTPException(status_code=404, detail="Program not found")

    return program


@router.get("/states")
async def get_community_solar_states(
    db: AsyncSession = Depends(get_db_session),
):
    """Get states with available community solar programs and their counts."""
    service = CommunitySolarService(db)
    counts = await service.get_state_program_count()

    return {
        "total_states": len(counts),
        "states": [
            {"state": state, "program_count": count}
            for state, count in counts.items()
        ],
    }
