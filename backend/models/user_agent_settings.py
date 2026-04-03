"""
User Agent Settings Models

Pydantic models for per-user auto-switcher configuration.  Controls the
savings thresholds, cooldown period, pause window, and Letter of Authority
(LOA) state required before the agent can execute plan switches on a user's
behalf.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Domain Model
# ---------------------------------------------------------------------------


class UserAgentSettings(BaseModel):
    """Full representation of a user's auto-switcher settings."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    enabled: bool = False
    savings_threshold_pct: Decimal = Decimal("10.0")
    savings_threshold_min: Decimal = Decimal("10.0")
    cooldown_days: int = 5
    paused_until: datetime | None = None
    loa_signed_at: datetime | None = None
    loa_document_s3_key: str | None = None
    loa_revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class UserAgentSettingsUpdate(BaseModel):
    """Request body for updating auto-switcher settings (all fields optional)."""

    enabled: bool | None = None
    savings_threshold_pct: Decimal | None = Field(default=None, ge=Decimal("5"), le=Decimal("50"))
    savings_threshold_min: Decimal | None = Field(default=None, ge=Decimal("5"))
    cooldown_days: int | None = Field(default=None, ge=3, le=90)
    paused_until: datetime | None = None

    @field_validator("savings_threshold_pct", "savings_threshold_min")
    @classmethod
    def validate_positive_decimal(cls, v: Decimal | None) -> Decimal | None:
        """Ensure threshold values are positive when provided."""
        if v is not None and v <= Decimal("0"):
            raise ValueError("Threshold values must be positive")
        return v


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class UserAgentSettingsResponse(BaseModel):
    """Serialised representation of agent settings (safe for API responses)."""

    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    savings_threshold_pct: Decimal
    savings_threshold_min: Decimal
    cooldown_days: int
    paused_until: datetime | None = None
    loa_signed_at: datetime | None = None
    loa_revoked_at: datetime | None = None
