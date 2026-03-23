"""
Observation Models

Pydantic models for the forecast_observations and recommendation_outcomes tables.
Used by the adaptive learning pipeline.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ForecastObservation(BaseModel):
    """A single forecast prediction with optional actual price backfill."""

    id: str
    forecast_id: str
    region: str
    forecast_hour: int = Field(..., ge=0, le=23)
    predicted_price: float
    actual_price: float | None = None
    confidence_lower: float | None = None
    confidence_upper: float | None = None
    model_version: str | None = None
    observed_at: datetime | None = None
    created_at: datetime | None = None


class RecommendationOutcome(BaseModel):
    """A recommendation served to a user with outcome tracking."""

    id: str
    user_id: str
    recommendation_type: str
    recommendation_data: dict[str, Any]
    was_accepted: bool | None = None
    actual_savings: float | None = None
    responded_at: datetime | None = None
    created_at: datetime | None = None


class AccuracyMetrics(BaseModel):
    """Forecast accuracy metrics for a region."""

    total: int
    mape: float | None = Field(None, description="Mean Absolute Percentage Error")
    rmse: float | None = Field(None, description="Root Mean Square Error")
    coverage: float | None = Field(None, description="Confidence interval coverage %")


class HourlyBias(BaseModel):
    """Per-hour prediction bias."""

    hour: int
    avg_bias: float
    count: int
