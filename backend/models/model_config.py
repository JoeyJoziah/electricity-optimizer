"""
Model Config — Pydantic models for ML ensemble weight persistence.

Stores the trained ensemble weights (CNN-LSTM / XGBoost / LightGBM) together
with training metadata and accuracy metrics so that EnsemblePredictor can
reload them from PostgreSQL after a Render restart instead of losing state.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    """
    Represents a versioned snapshot of ensemble model weights.

    One row is marked is_active=True per model_name at any given time.
    Previous rows are retained for rollback and auditing.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    model_name: str = Field(..., min_length=1, max_length=100)
    model_version: str = Field(..., min_length=1, max_length=50)

    # JSONB — stores the full weights dict, e.g.
    # {"cnn_lstm": {"weight": 0.5}, "xgboost": {"weight": 0.25}, ...}
    weights_json: dict[str, Any]

    # Arbitrary key-value bag for provenance (region, days window, etc.)
    training_metadata: dict[str, Any] = Field(default_factory=dict)

    # MAPE, RMSE, coverage, etc. captured at the time of training.
    accuracy_metrics: dict[str, Any] = Field(default_factory=dict)

    is_active: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ModelConfigCreate(BaseModel):
    """Input schema for persisting a new model configuration."""

    model_name: str = Field(..., min_length=1, max_length=100)
    model_version: str = Field(..., min_length=1, max_length=50)
    weights_json: dict[str, Any]
    training_metadata: dict[str, Any] = Field(default_factory=dict)
    accuracy_metrics: dict[str, Any] = Field(default_factory=dict)


class ModelConfigResponse(BaseModel):
    """Public response schema for a model configuration record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    model_name: str
    model_version: str
    weights_json: dict[str, Any]
    training_metadata: dict[str, Any]
    accuracy_metrics: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
