"""
Recommendations API Router - Switching and usage recommendations

Provides endpoints for supplier switching and energy usage optimization.
"""

import dataclasses
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.dependencies import get_current_user, get_recommendation_service, TokenData
from services.recommendation_service import RecommendationService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/switching")
async def get_switching_recommendation(
    current_user: TokenData = Depends(get_current_user),
    service: RecommendationService = Depends(get_recommendation_service),
):
    """Get supplier switching recommendation for the current user"""
    try:
        result = await service.get_switching_recommendation(current_user.user_id)
    except Exception:
        logger.exception("switching_recommendation_error")
        result = None

    if result is None:
        return {
            "user_id": current_user.user_id,
            "recommendation": None,
            "message": "No switching recommendations available at this time"
        }

    return {
        "user_id": current_user.user_id,
        "recommendation": dataclasses.asdict(result),
        "message": None
    }


@router.get("/usage")
async def get_usage_recommendation(
    appliance: str = Query(..., description="Appliance type"),
    duration_hours: float = Query(..., ge=0.25, le=24, description="Duration in hours"),
    current_user: TokenData = Depends(get_current_user),
    service: RecommendationService = Depends(get_recommendation_service),
):
    """Get usage timing recommendation for an appliance"""
    try:
        result = await service.get_usage_recommendation(
            current_user.user_id, appliance, int(duration_hours)
        )
    except Exception:
        logger.exception("usage_recommendation_error")
        result = None

    if result is None:
        return {
            "user_id": current_user.user_id,
            "appliance": appliance,
            "duration_hours": duration_hours,
            "optimal_start_time": None,
            "message": "No usage recommendations available at this time"
        }

    return {
        "user_id": current_user.user_id,
        "appliance": appliance,
        "duration_hours": duration_hours,
        **result,
        "message": None
    }


@router.get("/daily")
async def get_daily_recommendations(
    current_user: TokenData = Depends(get_current_user),
    service: RecommendationService = Depends(get_recommendation_service),
):
    """Get all daily recommendations for the current user"""
    try:
        result = await service.get_daily_recommendations(current_user.user_id)
    except Exception:
        logger.exception("daily_recommendations_error")
        result = None

    if result is None:
        return {
            "user_id": current_user.user_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "switching_recommendation": None,
            "usage_recommendations": [],
            "message": "No recommendations available at this time"
        }

    return result
