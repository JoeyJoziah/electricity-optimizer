"""
Neighborhood API — rate comparison vs. regional peers.

Routes
------
GET /neighborhood/compare  — user rate percentile and cheapest alternative
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_db_session, SessionData
from services.neighborhood_service import NeighborhoodService

router = APIRouter(prefix="/neighborhood", tags=["Neighborhood"])


# =============================================================================
# GET /neighborhood/compare
# =============================================================================


@router.get("/compare")
async def neighborhood_compare(
    region: str = Query(description="Region code (e.g. 'us_ct')"),
    utility_type: str = Query(description="Utility type (e.g. 'electricity')"),
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Compare the user's rate against regional peers."""
    service = NeighborhoodService()
    return await service.get_comparison(
        db=db,
        user_id=current_user.user_id,
        region=region,
        utility_type=utility_type,
    )
