"""
Notification Models

Pydantic models for the notifications table, including the delivery-tracking
columns added by migration 029.

Schema (cumulative across migrations 015, 026, 029):

    id               UUID PRIMARY KEY DEFAULT gen_random_uuid()
    user_id          UUID NOT NULL
    type             VARCHAR(50) NOT NULL DEFAULT 'info'
    title            TEXT NOT NULL
    body             TEXT
    read_at          TIMESTAMPTZ
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    metadata         JSONB                              -- migration 026
    delivery_channel VARCHAR(20)                        -- migration 029
    delivery_status  VARCHAR(20) NOT NULL DEFAULT 'pending'
    delivered_at     TIMESTAMPTZ
    delivery_metadata JSONB NOT NULL DEFAULT '{}'
    retry_count      INTEGER NOT NULL DEFAULT 0
"""

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Delivery status literals
# ---------------------------------------------------------------------------

DeliveryStatus = Literal["pending", "sent", "delivered", "failed", "bounced"]
DeliveryChannel = Literal["email", "push", "in_app"]


# ---------------------------------------------------------------------------
# Core notification model (mirrors the notifications table exactly)
# ---------------------------------------------------------------------------


class Notification(BaseModel):
    """
    Full notification row including delivery-tracking columns.

    Maps 1-to-1 to the ``notifications`` database table after migrations
    015 (initial), 026 (metadata column), and 029 (delivery tracking).
    """

    model_config = ConfigDict(from_attributes=True)

    # Core fields (migration 015)
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    type: str = Field(default="info", max_length=50)
    title: str
    body: Optional[str] = None
    read_at: Optional[datetime] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Dispatcher metadata (migration 026)
    metadata: Optional[Dict[str, Any]] = None

    # Delivery tracking (migration 029)
    delivery_channel: Optional[DeliveryChannel] = None
    delivery_status: DeliveryStatus = "pending"
    delivered_at: Optional[datetime] = None
    delivery_metadata: Dict[str, Any] = Field(default_factory=dict)
    retry_count: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Create / update request schemas
# ---------------------------------------------------------------------------


class NotificationCreate(BaseModel):
    """
    Input schema for creating a new notification.

    Callers supply the user-facing content and optionally the delivery channel.
    ``delivery_status`` starts as ``"pending"`` by default.
    """

    user_id: str
    type: str = Field(default="info", max_length=50)
    title: str = Field(..., min_length=1)
    body: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    delivery_channel: Optional[DeliveryChannel] = None


class NotificationDeliveryUpdate(BaseModel):
    """
    Schema for updating the delivery status of an existing notification.

    Used by the NotificationDispatcher after each channel attempt so that
    the row reflects the current delivery outcome.
    """

    delivery_status: DeliveryStatus
    delivery_channel: Optional[DeliveryChannel] = None
    delivered_at: Optional[datetime] = None
    delivery_metadata: Optional[Dict[str, Any]] = None
    retry_count: Optional[int] = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class NotificationResponse(BaseModel):
    """
    Public response schema returned by the notifications API.

    Includes the delivery-tracking fields so the frontend can show
    per-notification delivery state (e.g. grey icon for "pending",
    green for "delivered", red for "failed"/"bounced").
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    title: str
    body: Optional[str] = None
    read_at: Optional[datetime] = None
    created_at: datetime

    # Delivery tracking
    delivery_channel: Optional[DeliveryChannel] = None
    delivery_status: DeliveryStatus = "pending"
    delivered_at: Optional[datetime] = None
    retry_count: int = 0


class NotificationListResponse(BaseModel):
    """Paginated list of notification responses."""

    notifications: list[NotificationResponse]
    total: int
