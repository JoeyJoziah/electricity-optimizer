"""
Recommendations API Router - Switching and usage recommendations

Provides endpoints for supplier switching and energy usage optimization.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.dependencies import get_current_user, TokenData

router = APIRouter()


@router.get("/switching")
async def get_switching_recommendation(
    current_user: TokenData = Depends(get_current_user),
):
    """Get supplier switching recommendation for the current user"""
    return {
        "user_id": current_user.user_id,
        "recommendation": None,
        "message": "No switching recommendations available at this time"
    }


@router.get("/usage")
async def get_usage_recommendation(
    appliance: str = Query(..., description="Appliance type"),
    duration_hours: float = Query(..., ge=0.25, le=24, description="Duration in hours"),
    current_user: TokenData = Depends(get_current_user),
):
    """Get usage timing recommendation for an appliance"""
    return {
        "user_id": current_user.user_id,
        "appliance": appliance,
        "duration_hours": duration_hours,
        "optimal_start_time": None,
        "message": "No usage recommendations available at this time"
    }
