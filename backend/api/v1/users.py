"""
Users API Router — User profile management

Provides GET /profile and PUT /profile endpoints for reading and updating
a user's extended profile data (region, utility_types, current_supplier_id,
annual_usage_kwh, onboarding_completed).

These columns are added by migration 013_user_profile_columns.sql.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import SessionData, get_current_user, get_db_session
from auth.neon_auth import ensure_user_profile

logger = structlog.get_logger()

router = APIRouter(prefix="/users", tags=["Users"])


# =============================================================================
# SCHEMAS
# =============================================================================


class UserProfile(BaseModel):
    email: str
    name: str | None = None
    region: str | None = None
    utility_types: list[str] | None = None
    current_supplier_id: str | None = None
    annual_usage_kwh: int | None = None
    onboarding_completed: bool = False


VALID_REGIONS = {
    "us_al",
    "us_ak",
    "us_az",
    "us_ar",
    "us_ca",
    "us_co",
    "us_ct",
    "us_de",
    "us_dc",
    "us_fl",
    "us_ga",
    "us_hi",
    "us_id",
    "us_il",
    "us_in",
    "us_ia",
    "us_ks",
    "us_ky",
    "us_la",
    "us_me",
    "us_md",
    "us_ma",
    "us_mi",
    "us_mn",
    "us_ms",
    "us_mo",
    "us_mt",
    "us_ne",
    "us_nv",
    "us_nh",
    "us_nj",
    "us_nm",
    "us_ny",
    "us_nc",
    "us_nd",
    "us_oh",
    "us_ok",
    "us_or",
    "us_pa",
    "us_ri",
    "us_sc",
    "us_sd",
    "us_tn",
    "us_tx",
    "us_ut",
    "us_vt",
    "us_va",
    "us_wa",
    "us_wv",
    "us_wi",
    "us_wy",
    "uk",
    "uk_scotland",
    "uk_wales",
    "ie",
    "de",
    "fr",
    "es",
    "it",
    "nl",
    "be",
    "at",
    "jp",
    "au",
    "ca",
    "cn",
    "in",
    "br",
}

VALID_UTILITY_TYPES = {"electricity", "natural_gas", "heating_oil", "propane", "community_solar"}


class UserProfileUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    region: str | None = Field(None, max_length=50)
    utility_types: list[str] | None = None
    current_supplier_id: str | None = None
    annual_usage_kwh: int | None = Field(None, ge=0, le=1000000)
    onboarding_completed: bool | None = None

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str | None) -> str | None:
        if v is not None and v.lower() not in VALID_REGIONS:
            raise ValueError(f"Invalid region: {v}")
        return v.lower() if v else v

    @field_validator("utility_types")
    @classmethod
    def validate_utility_types(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for t in v:
                if t not in VALID_UTILITY_TYPES:
                    raise ValueError(f"Invalid utility type: {t}")
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
    current_user: SessionData = Depends(get_current_user),
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
        # The user authenticated via Better Auth but the public.users record
        # hasn't been created yet (race between sign-up and first profile fetch,
        # or user signed up before the sync logic was deployed).
        # Attempt an on-demand sync now rather than returning a hard 404.
        try:
            await ensure_user_profile(
                neon_user_id=current_user.user_id,
                email=current_user.email,
                name=current_user.name,
                db=db,
            )
        except Exception as sync_err:
            logger.error(
                "profile_sync_on_demand_failed",
                user_id=current_user.user_id,
                error=str(sync_err),
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found and could not be created automatically.",
            )
        # Re-fetch after creating the profile
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

    (
        email,
        name,
        region,
        utility_types_raw,
        current_supplier_id,
        annual_usage_kwh,
        onboarding_completed,
    ) = row

    # utility_types is stored as a comma-separated string; split on read
    utility_types: list[str] | None = None
    if utility_types_raw:
        utility_types = [t.strip() for t in utility_types_raw.split(",") if t.strip()]

    return UserProfile(
        email=email,
        name=name,
        region=region,
        utility_types=utility_types,
        current_supplier_id=str(current_supplier_id) if current_supplier_id else None,
        annual_usage_kwh=annual_usage_kwh,
        onboarding_completed=bool(onboarding_completed)
        if onboarding_completed is not None
        else False,
    )


@router.put(
    "/profile",
    response_model=UserProfile,
    summary="Update user profile",
    description="Update the authenticated user's extended profile data (partial update — only provided fields are changed)",
)
async def update_profile(
    update: UserProfileUpdate,
    current_user: SessionData = Depends(get_current_user),
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

    UPDATABLE_COLUMNS = frozenset(
        {
            "name",
            "region",
            "utility_types",
            "current_supplier_id",
            "annual_usage_kwh",
            "onboarding_completed",
        }
    )
    disallowed = set(updates.keys()) - UPDATABLE_COLUMNS
    if disallowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update columns: {', '.join(sorted(disallowed))}",
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
        fields=[k for k in updates if k != "uid"],
    )

    # Return the refreshed profile
    return await get_profile(current_user, db)
