"""
User Plan Models

Pydantic models for tracking current and historical electricity plans per user.
Covers plans sourced from Arcadia, EnergyBot, UtilityAPI, manual entry, and
portal scrapes.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums (expressed as Literal types to stay Pydantic-native)
# ---------------------------------------------------------------------------

PlanStatus = Literal["active", "expired", "switched_away"]
PlanSource = Literal["arcadia", "manual", "energybot", "utilityapi", "portal"]


# ---------------------------------------------------------------------------
# Domain Model
# ---------------------------------------------------------------------------


class UserPlan(BaseModel):
    """Full representation of a user's electricity plan record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    plan_name: str
    provider_name: str
    rate_kwh: Decimal | None = None
    fixed_charge: Decimal | None = None
    term_months: int | None = None
    etf_amount: Decimal = Decimal("0")
    contract_start: datetime | None = None
    contract_end: datetime | None = None
    status: PlanStatus = "active"
    source: PlanSource
    raw_plan_data: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class UserPlanCreate(BaseModel):
    """Request body for creating a new user plan entry."""

    plan_name: str = Field(..., min_length=1, max_length=200)
    provider_name: str = Field(..., min_length=1, max_length=200)
    rate_kwh: Decimal | None = Field(default=None, ge=Decimal("0"))
    fixed_charge: Decimal | None = Field(default=None, ge=Decimal("0"))
    term_months: int | None = Field(default=None, ge=1)
    etf_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    contract_start: datetime | None = None
    contract_end: datetime | None = None
    source: PlanSource


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class UserPlanResponse(BaseModel):
    """Serialised representation of a user plan (safe for API responses)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_name: str
    provider_name: str
    rate_kwh: Decimal | None = None
    fixed_charge: Decimal | None = None
    term_months: int | None = None
    etf_amount: Decimal = Decimal("0")
    contract_start: datetime | None = None
    contract_end: datetime | None = None
    status: PlanStatus
    source: PlanSource
    created_at: datetime
