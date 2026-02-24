"""
User API Router - User preferences and settings

Provides endpoints for user profile and preference management.
Preferences are persisted to the users table via UserRepository.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, TokenData
from config.database import get_timescale_session
from repositories.user_repository import UserRepository
from models.user import UserPreferences

import structlog

logger = structlog.get_logger()

router = APIRouter()


class UserPreferencesUpdate(BaseModel):
    """User preferences update request (partial update)"""
    notification_enabled: Optional[bool] = None
    auto_switch_enabled: Optional[bool] = None
    green_energy_only: Optional[bool] = None
    region: Optional[str] = None


@router.get("/preferences")
async def get_preferences(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_timescale_session),
):
    """Get current user preferences from database."""
    repo = UserRepository(db)
    user = await repo.get_by_id(current_user.user_id)

    if not user:
        return {
            "user_id": current_user.user_id,
            "preferences": UserPreferences().model_dump(),
        }

    # Merge stored dict with UserPreferences defaults
    stored = user.preferences or {}
    prefs = UserPreferences(**{k: v for k, v in stored.items() if k in UserPreferences.model_fields})

    return {
        "user_id": current_user.user_id,
        "preferences": prefs.model_dump(),
    }


@router.post("/preferences")
async def update_preferences(
    preferences: UserPreferencesUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_timescale_session),
):
    """Update user preferences in database (partial update — only non-null fields)."""
    repo = UserRepository(db)
    user = await repo.get_by_id(current_user.user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Merge incoming non-null fields into existing preferences
    existing = user.preferences or {}
    updates = preferences.model_dump(exclude_none=True)
    existing.update(updates)

    # Validate merged preferences against the full schema
    merged_prefs = UserPreferences(
        **{k: v for k, v in existing.items() if k in UserPreferences.model_fields}
    )

    updated = await repo.update_preferences(current_user.user_id, merged_prefs)

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences",
        )

    logger.info("preferences_updated", user_id=current_user.user_id, fields=list(updates.keys()))

    return {
        "user_id": current_user.user_id,
        "preferences": merged_prefs.model_dump(),
        "message": "Preferences updated successfully",
    }
