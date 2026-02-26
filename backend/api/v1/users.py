"""
Users API Router — User profile management

Provides GET /profile and PUT /profile endpoints for reading and updating
a user's extended profile data (region, utility_types, current_supplier_id,
annual_usage_kwh, onboarding_completed).

These columns are added by migration 013_user_profile_columns.sql.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_db_session, TokenData

import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/users", tags=["users"])


# =============================================================================
# SCHEMAS
# =============================================================================


class UserProfile(BaseModel):
    email: str
    name: Optional[str] = None
    region: Optional[str] = None
    utility_types: Optional[List[str]] = None
    current_supplier_id: Optional[str] = None
    annual_usage_kwh: Optional[int] = None
    onboarding_completed: bool = False


class UserProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=50)
    utility_types: Optional[List[str]] = None
    current_supplier_id: Optional[str] = None
    annual_usage_kwh: Optional[int] = Field(None, ge=0, le=1000000)
    onboarding_completed: Optional[bool] = None


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get(
    "/profile",
    response_model=UserProfile,
    summary="Get user profile",
    description="Retrieve the authenticated user's extended profile data",
)
async def get_profile(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserProfile:
    """Return the current user's profile, including region, utility types, and usage data."""
    result = await db.execute(
        text(
            "SELECT email, name, region, utility_types, current_supplier_id, "
            "annual_usage_kwh, onboarding_completed "
            "FROM users WHERE id = :uid"
        ),
        {"uid": current_user.user_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        )

    email, name, region, utility_types_raw, current_supplier_id, annual_usage_kwh, onboarding_completed = row

    # utility_types is stored as a comma-separated string; split on read
    utility_types: Optional[List[str]] = None
    if utility_types_raw:
        utility_types = [t.strip() for t in utility_types_raw.split(",") if t.strip()]

    return UserProfile(
        email=email,
        name=name,
        region=region,
        utility_types=utility_types,
        current_supplier_id=str(current_supplier_id) if current_supplier_id else None,
        annual_usage_kwh=annual_usage_kwh,
        onboarding_completed=bool(onboarding_completed) if onboarding_completed is not None else False,
    )


@router.put(
    "/profile",
    response_model=UserProfile,
    summary="Update user profile",
    description="Update the authenticated user's extended profile data (partial update — only provided fields are changed)",
)
async def update_profile(
    update: UserProfileUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserProfile:
    """Partially update the current user's profile. Returns the updated profile."""
    updates: dict = {}

    if update.name is not None:
        updates["name"] = update.name
    if update.region is not None:
        updates["region"] = update.region.lower()
    if update.utility_types is not None:
        updates["utility_types"] = ",".join(update.utility_types)
    if update.current_supplier_id is not None:
        updates["current_supplier_id"] = update.current_supplier_id
    if update.annual_usage_kwh is not None:
        updates["annual_usage_kwh"] = update.annual_usage_kwh
    if update.onboarding_completed is not None:
        updates["onboarding_completed"] = update.onboarding_completed

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["uid"] = current_user.user_id

    await db.execute(
        text(f"UPDATE users SET {set_clause}, updated_at = now() WHERE id = :uid"),
        updates,
    )
    await db.commit()

    logger.info(
        "user_profile_updated",
        user_id=current_user.user_id,
        fields=list(k for k in updates if k != "uid"),
    )

    # Return the refreshed profile
    return await get_profile(current_user, db)
