"""
Savings API — endpoints for retrieving user savings summaries and history.

Routes
------
GET /savings/summary  — aggregated totals + streak for the authenticated user
GET /savings/history  — paginated list of individual savings records
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_db_session, TokenData
from services.savings_service import SavingsService

router = APIRouter(prefix="/savings", tags=["savings"])


# =============================================================================
# GET /savings/summary
# =============================================================================


@router.get("/summary")
async def get_savings_summary(
    region: Optional[str] = Query(default=None, description="Filter by region code (e.g. US_CT)"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Return aggregated savings totals for the authenticated user.

    Response fields:
    - **total**: lifetime savings amount
    - **weekly**: savings in the last 7 days
    - **monthly**: savings in the last 30 days
    - **streak_days**: consecutive days with at least one savings record ending today
    - **currency**: ISO 4217 currency code (e.g. 'USD')
    """
    service = SavingsService(db)
    return await service.get_savings_summary(
        user_id=current_user.user_id,
        region=region,
    )


# =============================================================================
# GET /savings/history
# =============================================================================


@router.get("/history")
async def get_savings_history(
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Records per page (max 100)"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Return a paginated list of savings records for the authenticated user.

    Response fields:
    - **items**: list of savings record objects
    - **total**: total number of records
    - **page**: current page number
    - **page_size**: records per page
    - **pages**: total number of pages
    """
    service = SavingsService(db)
    return await service.get_savings_history(
        user_id=current_user.user_id,
        page=page,
        page_size=page_size,
    )
