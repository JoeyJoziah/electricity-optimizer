"""
Switch Audit Log Models

Pydantic models for every decision-engine run.  Each record captures the
trigger type, decision, projected savings, confidence score, and whether the
switch was ultimately executed — forming the full audit trail for the
auto-switcher.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums (expressed as Literal types to stay Pydantic-native)
# ---------------------------------------------------------------------------

TriggerType = Literal[
    "market_scan", "price_spike", "contract_expiry", "rate_change", "manual"
]
DecisionAction = Literal["switch", "recommend", "hold", "monitor"]
UserTier = Literal["pro", "business"]


# ---------------------------------------------------------------------------
# Domain Model
# ---------------------------------------------------------------------------


class SwitchAuditLog(BaseModel):
    """Full representation of a single decision-engine audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    trigger_type: TriggerType
    decision: DecisionAction
    reason: str
    current_plan_id: UUID | None = None
    proposed_plan_id: UUID | None = None
    savings_monthly: Decimal | None = None
    savings_annual: Decimal | None = None
    etf_cost: Decimal = Decimal("0")
    net_savings_year1: Decimal | None = None
    confidence_score: Decimal | None = None
    data_source: str | None = None
    tier: UserTier
    executed: bool = False
    enrollment_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class SwitchAuditLogResponse(BaseModel):
    """Serialised representation of an audit log entry (safe for API responses)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trigger_type: TriggerType
    decision: DecisionAction
    reason: str
    savings_monthly: Decimal | None = None
    savings_annual: Decimal | None = None
    etf_cost: Decimal = Decimal("0")
    net_savings_year1: Decimal | None = None
    confidence_score: Decimal | None = None
    data_source: str | None = None
    executed: bool
    created_at: datetime
