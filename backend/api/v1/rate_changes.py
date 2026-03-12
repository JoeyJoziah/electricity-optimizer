"""
Rate Changes API

Endpoints for viewing detected rate changes across utility types
and managing per-utility alert preferences.

Routes
------
GET  /rate-changes               — recent rate changes (public, optionally filtered)
GET  /rate-changes/preferences   — user's per-utility alert preferences
PUT  /rate-changes/preferences   — upsert per-utility alert preference
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from api.dependencies import get_current_user, get_db_session, SessionData

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/rate-changes", tags=["Rate Changes"])


# =============================================================================
# Request / response models
# =============================================================================


class UpsertPreferenceRequest(BaseModel):
    """Body for PUT /rate-changes/preferences."""

    utility_type: str = Field(description="Utility type: electricity, natural_gas, heating_oil, etc.")
    enabled: Optional[bool] = Field(default=None, description="Enable/disable alerts for this utility")
    channels: Optional[List[str]] = Field(
        default=None,
        description="Notification channels: email, push, in_app",
    )
    cadence: Optional[str] = Field(
        default=None,
        description="Alert cadence: realtime, daily, weekly",
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    summary="Recent rate changes",
    response_description="Recent rate changes across utility types",
)
async def get_rate_changes(
    utility_type: Optional[str] = Query(default=None, description="Filter by utility type"),
    region: Optional[str] = Query(default=None, description="Filter by region/state"),
    days: int = Query(default=7, ge=1, le=90, description="Look back N days"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Return recent rate changes, optionally filtered by utility type and region.
    Shows both increases and decreases with optional cheaper-alternative recommendations.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    from services.rate_change_detector import RateChangeDetector

    detector = RateChangeDetector(db)
    changes = await detector.get_recent_changes(
        utility_type=utility_type,
        region=region,
        days=days,
        limit=limit,
    )
    return {"changes": changes, "total": len(changes)}


@router.get(
    "/preferences",
    summary="Alert preferences",
    response_description="Per-utility alert preferences for the current user",
)
async def get_preferences(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Return the authenticated user's per-utility alert notification preferences."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    from services.rate_change_detector import AlertPreferenceService

    service = AlertPreferenceService(db)
    prefs = await service.get_preferences(current_user.user_id)
    return {"preferences": prefs}


@router.put(
    "/preferences",
    summary="Update alert preference",
    response_description="The upserted alert preference",
)
async def upsert_preference(
    body: UpsertPreferenceRequest,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Create or update per-utility alert notification preferences."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    valid_types = {"electricity", "natural_gas", "heating_oil", "propane", "community_solar"}
    if body.utility_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid utility_type. Must be one of: {', '.join(sorted(valid_types))}",
        )

    valid_cadences = {"realtime", "daily", "weekly"}
    if body.cadence and body.cadence not in valid_cadences:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid cadence. Must be one of: {', '.join(sorted(valid_cadences))}",
        )

    from services.rate_change_detector import AlertPreferenceService

    service = AlertPreferenceService(db)
    pref = await service.upsert_preference(
        user_id=current_user.user_id,
        utility_type=body.utility_type,
        enabled=body.enabled,
        channels=body.channels,
        cadence=body.cadence,
    )
    return pref
