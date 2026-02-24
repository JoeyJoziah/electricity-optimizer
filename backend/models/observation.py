"""
Observation Models

Pydantic models for the forecast_observations and recommendation_outcomes tables.
Used by the adaptive learning pipeline.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ForecastObservation(BaseModel):
    """A single forecast prediction with optional actual price backfill."""
    id: str
    forecast_id: str
    region: str
    forecast_hour: int = Field(..., ge=0, le=23)
    predicted_price: float
    actual_price: Optional[float] = None
    confidence_lower: Optional[float] = None
    confidence_upper: Optional[float] = None
    model_version: Optional[str] = None
    observed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class RecommendationOutcome(BaseModel):
    """A recommendation served to a user with outcome tracking."""
    id: str
    user_id: str
    recommendation_type: str
    recommendation_data: Dict[str, Any]
    was_accepted: Optional[bool] = None
    actual_savings: Optional[float] = None
    responded_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class AccuracyMetrics(BaseModel):
    """Forecast accuracy metrics for a region."""
    total: int
    mape: Optional[float] = Field(None, description="Mean Absolute Percentage Error")
    rmse: Optional[float] = Field(None, description="Root Mean Square Error")
    coverage: Optional[float] = Field(None, description="Confidence interval coverage %")


class HourlyBias(BaseModel):
    """Per-hour prediction bias."""
    hour: int
    avg_bias: float
    count: int
