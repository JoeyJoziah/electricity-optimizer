"""
Available Plan Models

Pydantic models for cached marketplace electricity plans keyed by zip code
and utility.  Records expire after a configurable TTL so the decision engine
always works from fresh market data.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Domain Model
# ---------------------------------------------------------------------------


class AvailablePlan(BaseModel):
    """Full representation of a cached marketplace plan record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    zip_code: str
    utility_code: str | None = None
    region: str
    plan_name: str
    provider_name: str
    rate_kwh: Decimal
    fixed_charge: Decimal = Decimal("0")
    term_months: int | None = None
    etf_amount: Decimal = Decimal("0")
    renewable_pct: int = 0
    plan_url: str | None = None
    energybot_id: str | None = None
    raw_plan_data: dict[str, Any] | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class AvailablePlanResponse(BaseModel):
    """Serialised representation of an available plan (safe for API responses)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    zip_code: str
    plan_name: str
    provider_name: str
    rate_kwh: Decimal
    fixed_charge: Decimal = Decimal("0")
    term_months: int | None = None
    etf_amount: Decimal = Decimal("0")
    renewable_pct: int = 0
    plan_url: str | None = None
    fetched_at: datetime
