"""
Switch Execution Models

Pydantic models for the enrollment lifecycle state machine.  Tracks every
state transition from ``initiating`` through ``active`` (or ``failed`` /
``rolled_back``), including rescission and cooldown windows required by
retail-energy regulations.
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums (expressed as Literal types to stay Pydantic-native)
# ---------------------------------------------------------------------------

ExecutionStatus = Literal[
    "initiating", "initiated", "submitted", "accepted", "active", "failed", "rolled_back"
]
ExecutorType = Literal["energybot", "powerkiosk", "advisory_only"]


# ---------------------------------------------------------------------------
# Domain Model
# ---------------------------------------------------------------------------


class SwitchExecution(BaseModel):
    """Full representation of a switch-execution record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    audit_log_id: UUID
    old_plan_id: UUID | None = None
    new_plan_id: UUID | None = None
    idempotency_key: UUID
    enrollment_id: str | None = None
    executor_type: ExecutorType = "energybot"
    status: ExecutionStatus = "initiating"
    initiated_at: datetime | None = None
    confirmed_at: datetime | None = None
    enacted_at: datetime | None = None
    rescission_ends: datetime | None = None
    cooldown_ends: datetime | None = None
    failure_reason: str | None = None
    rolled_back_from: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class SwitchExecutionResponse(BaseModel):
    """Serialised representation of a switch execution (safe for API responses)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    old_plan_id: UUID | None = None
    new_plan_id: UUID | None = None
    executor_type: ExecutorType
    status: ExecutionStatus
    initiated_at: datetime | None = None
    enacted_at: datetime | None = None
    rescission_ends: datetime | None = None
    cooldown_ends: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime
