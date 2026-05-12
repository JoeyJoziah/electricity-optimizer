"""
Utility Discovery API

Endpoints for determining available utility types per region
and tracking user completion progress.
"""

from fastapi import APIRouter, HTTPException, Query

from services.utility_discovery_service import UtilityDiscoveryService

router = APIRouter(tags=["Utility Discovery"])


@router.get("/discover")
async def discover_utilities(
    state: str = Query(
        ..., min_length=2, max_length=2, description="2-letter state code"
    ),
):
    """Discover available utility types for a state."""
    state_upper = state.upper()

    utilities = UtilityDiscoveryService.discover(state_upper)

    return {
        "state": state_upper,
        "count": len(utilities),
        "utilities": utilities,
    }


@router.get("/completion")
async def get_completion(
    state: str = Query(
        ..., min_length=2, max_length=2, description="2-letter state code"
    ),
    tracked: str = Query(
        "electricity",
        description="Comma-separated list of tracked utility types",
    ),
):
    """Get utility tracking completion status for a user."""
    state_upper = state.upper()
    tracked_types = [t.strip() for t in tracked.split(",") if t.strip()]

    if not tracked_types:
        raise HTTPException(
            status_code=400, detail="At least one tracked utility type required"
        )

    result = UtilityDiscoveryService.get_completion_status(state_upper, tracked_types)

    return {
        "state": state_upper,
        **result,
    }
