"""
Affiliate API

Endpoints for tracking affiliate clicks and internal revenue reporting.

Routes
------
POST /affiliate/click    — record an affiliate click
GET  /affiliate/revenue  — internal revenue summary (requires API key)
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import (get_current_user_optional, get_db_session,
                              verify_api_key)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/affiliate", tags=["Affiliate"])


class ClickRequest(BaseModel):
    supplier_name: str = Field(description="Supplier being clicked on")
    supplier_id: str | None = Field(default=None, description="Supplier UUID if known")
    utility_type: str = Field(
        description="Utility type: electricity, natural_gas, etc."
    )
    region: str = Field(description="State/region code")
    source_page: str = Field(description="Page where click originated")


@router.post("/click", summary="Record affiliate click")
async def record_affiliate_click(
    body: ClickRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Record a click on an affiliate/switch CTA.

    User ID is derived from the authenticated session when available.
    Anonymous clicks are allowed (user_id=None).
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    from services.affiliate_service import AffiliateService

    # Use authenticated user_id if logged in, otherwise None (anonymous)
    user_id = current_user.user_id if current_user else None

    service = AffiliateService(db)
    affiliate_url = service.generate_affiliate_url(
        supplier_name=body.supplier_name,
        utility_type=body.utility_type,
        region=body.region,
    )

    click_id = await service.record_click(
        user_id=user_id,
        supplier_id=body.supplier_id,
        supplier_name=body.supplier_name,
        utility_type=body.utility_type,
        region=body.region,
        source_page=body.source_page,
        affiliate_url=affiliate_url or "",
    )

    return {
        "click_id": click_id,
        "affiliate_url": affiliate_url,
    }


@router.get(
    "/revenue",
    summary="Affiliate revenue summary (internal)",
    dependencies=[Depends(verify_api_key)],
)
async def get_revenue_summary(
    days: int = Query(default=30, ge=1, le=365, description="Lookback period in days"),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Get affiliate revenue summary. Internal use only."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    from services.affiliate_service import AffiliateService

    service = AffiliateService(db)
    return await service.get_revenue_summary(days=days)
