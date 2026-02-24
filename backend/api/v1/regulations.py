"""
State Regulations API Endpoints

Provides state-level energy regulation data including:
- Deregulation status for electricity, gas, oil
- Community solar program availability
- PUC contact info and comparison tool links
- Licensing and bond requirements
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status

from api.dependencies import get_db_session
from models.regulation import StateRegulationResponse, StateRegulationListResponse
from repositories.supplier_repository import StateRegulationRepository


router = APIRouter()


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=StateRegulationListResponse,
    summary="List state regulations",
)
async def list_regulations(
    electricity: Optional[bool] = Query(None, description="Filter by electricity deregulation"),
    gas: Optional[bool] = Query(None, description="Filter by gas deregulation"),
    oil: Optional[bool] = Query(None, description="Filter by oil market competition"),
    community_solar: Optional[bool] = Query(None, description="Filter by community solar availability"),
    db=Depends(get_db_session),
):
    """
    List state energy regulations with optional filtering.

    Use query parameters to find states with specific deregulation profiles.
    For example, `?electricity=true&gas=true` returns states where both
    electricity and gas markets are deregulated.
    """
    repo = StateRegulationRepository(db)
    states = await repo.list_deregulated(
        electricity=electricity,
        gas=gas,
        oil=oil,
        community_solar=community_solar,
    )

    return StateRegulationListResponse(
        states=[StateRegulationResponse(**s) for s in states],
        total=len(states),
    )


@router.get(
    "/{state_code}",
    response_model=StateRegulationResponse,
    summary="Get state regulation details",
    responses={
        404: {"description": "State not found"},
    },
)
async def get_state_regulation(
    state_code: str = Path(..., description="Two-letter state code (e.g., CT, TX, NY)"),
    db=Depends(get_db_session),
):
    """
    Get detailed regulation information for a specific state.

    Returns deregulation status, PUC contact info, licensing requirements,
    and links to state comparison tools where available.
    """
    repo = StateRegulationRepository(db)
    state = await repo.get_by_state(state_code)

    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No regulation data for state '{state_code.upper()}'"
        )

    return StateRegulationResponse(**state)
