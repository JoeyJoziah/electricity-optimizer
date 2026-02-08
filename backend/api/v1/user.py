"""
User API Router - User preferences and settings

Provides endpoints for user profile and preference management.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from api.dependencies import get_current_user, TokenData

router = APIRouter()


class UserPreferencesUpdate(BaseModel):
    """User preferences update request"""
    notification_enabled: Optional[bool] = None
    auto_switch_enabled: Optional[bool] = None
    green_energy_only: Optional[bool] = None
    region: Optional[str] = None


@router.get("/preferences")
async def get_preferences(
    current_user: TokenData = Depends(get_current_user),
):
    """Get current user preferences"""
    return {
        "user_id": current_user.user_id,
        "preferences": {
            "notification_enabled": True,
            "auto_switch_enabled": False,
            "green_energy_only": False,
        }
    }


@router.post("/preferences")
async def update_preferences(
    preferences: UserPreferencesUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    """Update user preferences"""
    return {
        "user_id": current_user.user_id,
        "preferences": preferences.model_dump(exclude_none=True),
        "message": "Preferences updated successfully"
    }
