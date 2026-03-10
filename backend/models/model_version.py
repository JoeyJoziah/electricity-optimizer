"""
Model Version — Pydantic models for ML model versioning and A/B testing.

These models back the three tables added in migration 030:
  - model_versions  (versioned ML configurations with active/inactive gating)
  - ab_tests        (A/B test runs pairing two model versions)
  - ab_outcomes     (per-user outcome events recorded during a test)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# model_versions
# ---------------------------------------------------------------------------


class ModelVersion(BaseModel):
    """A versioned snapshot of an ML model configuration."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    model_name: str = Field(..., min_length=1, max_length=100)
    version_tag: str = Field(..., min_length=1, max_length=50)

    # Arbitrary JSON: hyperparameters, ensemble weights, feature lists, etc.
    config: Dict[str, Any] = Field(default_factory=dict)

    # Evaluation metrics captured at training time (mape, rmse, coverage…)
    metrics: Dict[str, Any] = Field(default_factory=dict)

    is_active: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    promoted_at: Optional[datetime] = None


class ModelVersionCreate(BaseModel):
    """Input payload for creating a new model version."""

    model_name: str = Field(..., min_length=1, max_length=100)
    version_tag: str = Field(..., min_length=1, max_length=50)
    config: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class ModelVersionResponse(BaseModel):
    """Public response schema for a model version record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    model_name: str
    version_tag: str
    config: Dict[str, Any]
    metrics: Dict[str, Any]
    is_active: bool
    created_at: datetime
    promoted_at: Optional[datetime]


# ---------------------------------------------------------------------------
# ab_tests
# ---------------------------------------------------------------------------


class ABTest(BaseModel):
    """An A/B test run pairing two model versions."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    model_name: str = Field(..., min_length=1, max_length=100)
    version_a_id: str
    version_b_id: str

    # Fraction of traffic routed to version_a; version_b gets (1 - traffic_split)
    traffic_split: float = Field(default=0.5, gt=0.0, lt=1.0)

    # Status lifecycle: running → completed | stopped
    status: str = Field(default="running")

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None

    # Aggregated results written when the test is concluded
    results: Dict[str, Any] = Field(default_factory=dict)


class ABTestCreate(BaseModel):
    """Input payload for starting a new A/B test."""

    model_name: str = Field(..., min_length=1, max_length=100)
    version_a_id: str
    version_b_id: str
    traffic_split: float = Field(default=0.5, gt=0.0, lt=1.0)


class ABTestResponse(BaseModel):
    """Public response schema for an A/B test record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    model_name: str
    version_a_id: str
    version_b_id: str
    traffic_split: float
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    results: Dict[str, Any]


# ---------------------------------------------------------------------------
# ab_outcomes
# ---------------------------------------------------------------------------


class ABOutcome(BaseModel):
    """A single outcome event for one user within an A/B test."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    test_id: str
    version_id: str
    user_id: str
    outcome: str = Field(..., min_length=1, max_length=50)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ABOutcomeCreate(BaseModel):
    """Input payload for recording an A/B outcome event."""

    test_id: str
    version_id: str
    user_id: str
    outcome: str = Field(..., min_length=1, max_length=50)


# ---------------------------------------------------------------------------
# Comparison result (service-level, not DB-backed)
# ---------------------------------------------------------------------------


class VersionComparisonResult(BaseModel):
    """Side-by-side metric comparison for two model versions."""

    version_a: ModelVersionResponse
    version_b: ModelVersionResponse

    # Key → {version_a: value, version_b: value, delta: value}
    metric_comparison: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# A/B assignment result (service-level, not DB-backed)
# ---------------------------------------------------------------------------


class ABAssignment(BaseModel):
    """Deterministic A/B assignment for a (test, user) pair."""

    test_id: str
    user_id: str
    assigned_version_id: str
    bucket: str  # "a" or "b"
