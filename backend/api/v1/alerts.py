"""
Alerts API

CRUD endpoints for user price-alert configurations and paginated alert
trigger history.  All endpoints require an authenticated Neon Auth session.

Routes
------
GET    /alerts              — list all alert configs for the current user
POST   /alerts              — create a new alert config
GET    /alerts/history      — paginated alert trigger history
DELETE /alerts/{alert_id}   — delete an alert config
PUT    /alerts/{alert_id}   — update an alert config
"""

import re
import uuid
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import SessionData, get_current_user, get_db_session
from services.alert_service import AlertService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


# =============================================================================
# Request / response models
# =============================================================================


_REGION_RE = re.compile(r"^[a-z]{2}(_[a-z]{2})?$")


class CreateAlertRequest(BaseModel):
    """Body for POST /alerts."""

    region: str = Field(description="Region code (e.g. 'us_ct')")
    currency: str = Field(
        default="USD", max_length=10, description="ISO 4217 currency code"
    )
    price_below: float | None = Field(
        default=None,
        gt=0,
        description="Alert when price drops to/below this value ($/kWh)",
    )
    price_above: float | None = Field(
        default=None,
        gt=0,
        description="Alert when price rises to/above this value ($/kWh)",
    )
    notify_optimal_windows: bool = Field(
        default=True, description="Notify when an optimal usage window is detected"
    )

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str) -> str:
        if not _REGION_RE.match(v):
            raise ValueError(
                f"Invalid region code: '{v}'. Expected format: 'us_ct', 'uk', 'de'"
            )
        return v

    @model_validator(mode="after")
    def require_at_least_one_condition(self) -> "CreateAlertRequest":
        if (
            self.price_below is None
            and self.price_above is None
            and not self.notify_optimal_windows
        ):
            raise ValueError(
                "At least one of price_below, price_above, or notify_optimal_windows "
                "must be specified."
            )
        return self


class UpdateAlertRequest(BaseModel):
    """Body for PUT /alerts/{alert_id}.  All fields optional."""

    region: str | None = None
    currency: str | None = Field(default=None, max_length=10)
    price_below: float | None = Field(default=None, gt=0)
    price_above: float | None = Field(default=None, gt=0)
    notify_optimal_windows: bool | None = None
    is_active: bool | None = None


# =============================================================================
# Helper — resolve AlertService
# =============================================================================


def _get_alert_service() -> AlertService:
    return AlertService()


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    summary="List price alerts",
    response_description="All alert configurations for the current user",
)
async def get_alerts(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Return all price alert configurations for the authenticated user,
    ordered by creation date (newest first).
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    service = _get_alert_service()
    alerts = await service.get_user_alerts(user_id=current_user.user_id, db=db)
    return {"alerts": alerts, "total": len(alerts)}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a price alert",
    response_description="The newly created alert configuration",
)
async def create_alert(
    body: CreateAlertRequest,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Create a new price alert configuration for the authenticated user.

    At least one of ``price_below``, ``price_above``, or
    ``notify_optimal_windows`` must be specified.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    service = _get_alert_service()
    try:
        alert = await service.create_alert(
            user_id=current_user.user_id,
            db=db,
            region=body.region,
            currency=body.currency,
            price_below=(
                Decimal(str(body.price_below)) if body.price_below is not None else None
            ),
            price_above=(
                Decimal(str(body.price_above)) if body.price_above is not None else None
            ),
            notify_optimal_windows=body.notify_optimal_windows,
        )
    except PermissionError as exc:
        logger.warning(
            "alert_create_forbidden", user_id=current_user.user_id, error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alert limit reached for your subscription tier.",
        ) from exc
    except ValueError as exc:
        logger.warning(
            "alert_create_invalid", user_id=current_user.user_id, error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid alert configuration. Check thresholds and region.",
        ) from exc

    logger.info("alert_endpoint_created", user_id=current_user.user_id)
    return alert


@router.get(
    "/history",
    summary="Alert trigger history",
    response_description="Paginated history of triggered alerts",
)
async def get_alert_history(
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(
        default=20, ge=1, le=100, description="Records per page (max 100)"
    ),
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Return a paginated list of alert trigger events for the authenticated user,
    ordered by trigger time (newest first).
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    service = _get_alert_service()
    return await service.get_alert_history(
        user_id=current_user.user_id,
        db=db,
        page=page,
        page_size=page_size,
    )


@router.delete(
    "/{alert_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a price alert",
    response_description="Deletion confirmation",
)
async def delete_alert(
    alert_id: uuid.UUID = Path(..., description="UUID of the alert config to delete"),
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Delete the price alert configuration with the given ID.  The alert must
    belong to the authenticated user; otherwise 404 is returned.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    service = _get_alert_service()
    deleted = await service.delete_alert(
        user_id=current_user.user_id,
        alert_id=str(alert_id),
        db=db,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )
    return {"deleted": True, "alert_id": str(alert_id)}


@router.put(
    "/{alert_id}",
    summary="Update a price alert",
    response_description="The updated alert configuration",
)
async def update_alert(
    alert_id: uuid.UUID = Path(..., description="UUID of the alert config to update"),
    body: UpdateAlertRequest = ...,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Update fields on an existing price alert configuration.  Only fields
    present in the request body are modified; unknown fields are ignored.
    The alert must belong to the authenticated user; otherwise 404 is returned.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    service = _get_alert_service()
    updates = body.model_dump(exclude_unset=True)
    updated = await service.update_alert(
        user_id=current_user.user_id,
        alert_id=str(alert_id),
        db=db,
        updates=updates,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )
    return updated
