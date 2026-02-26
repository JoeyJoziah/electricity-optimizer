"""
Users API Router — User profile management

Provides GET /profile and PUT /profile endpoints for reading and updating
a user's extended profile data (region, utility_types, current_supplier_id,
annual_usage_kwh, onboarding_completed).

These columns are added by migration 013_user_profile_columns.sql.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
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


VALID_REGIONS = {
    'us_al', 'us_ak', 'us_az', 'us_ar', 'us_ca', 'us_co', 'us_ct', 'us_de',
    'us_dc', 'us_fl', 'us_ga', 'us_hi', 'us_id', 'us_il', 'us_in', 'us_ia',
    'us_ks', 'us_ky', 'us_la', 'us_me', 'us_md', 'us_ma', 'us_mi', 'us_mn',
    'us_ms', 'us_mo', 'us_mt', 'us_ne', 'us_nv', 'us_nh', 'us_nj', 'us_nm',
    'us_ny', 'us_nc', 'us_nd', 'us_oh', 'us_ok', 'us_or', 'us_pa', 'us_ri',
    'us_sc', 'us_sd', 'us_tn', 'us_tx', 'us_ut', 'us_vt', 'us_va', 'us_wa',
    'us_wv', 'us_wi', 'us_wy',
    'uk', 'uk_scotland', 'uk_wales', 'ie', 'de', 'fr', 'es', 'it', 'nl',
    'be', 'at', 'jp', 'au', 'ca', 'cn', 'in', 'br',
}

VALID_UTILITY_TYPES = {'electricity', 'natural_gas', 'heating_oil', 'propane', 'community_solar'}


class UserProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=50)
    utility_types: Optional[List[str]] = None
    current_supplier_id: Optional[str] = None
    annual_usage_kwh: Optional[int] = Field(None, ge=0, le=1000000)
    onboarding_completed: Optional[bool] = None

    @field_validator('region')
    @classmethod
    def validate_region(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.lower() not in VALID_REGIONS:
            raise ValueError(f'Invalid region: {v}')
        return v.lower() if v else v

    @field_validator('utility_types')
    @classmethod
    def validate_utility_types(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            for t in v:
                if t not in VALID_UTILITY_TYPES:
                    raise ValueError(f'Invalid utility type: {t}')
        return v


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
