"""
Referrals API Router

Endpoints for referral code management and user growth.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import SessionData, get_current_user, get_db_session
from services.referral_service import ReferralError, ReferralService

logger = structlog.get_logger()

router = APIRouter(tags=["Referrals"])


class ApplyReferralRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=12)


@router.get("/referrals/code")
async def get_referral_code(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get or generate a referral code for the current user."""
    svc = ReferralService(db)
    code = await svc.get_or_create_code(current_user.user_id)
    return {"referral_code": code}


@router.post("/referrals/apply")
async def apply_referral(
    body: ApplyReferralRequest,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Apply a referral code (referee side)."""
    svc = ReferralService(db)
    try:
        result = await svc.apply_referral(current_user.user_id, body.code)
        return {"status": "applied", "referral_code": result["referral_code"]}
    except ReferralError as e:
        logger.warning("referral_apply_failed", user_id=current_user.user_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired referral code.",
        )


@router.get("/referrals/stats")
async def get_referral_stats(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get referral statistics for the current user."""
    svc = ReferralService(db)
    stats = await svc.get_stats(current_user.user_id)
    return stats
