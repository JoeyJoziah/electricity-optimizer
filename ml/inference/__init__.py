"""
ML Inference Module for Electricity Price Forecasting

This module provides inference capabilities for:
- Single model predictions (CNN-LSTM, XGBoost, LightGBM)
- Ensemble model predictions with weighted averaging
- Confidence interval calculation

Usage:
    from ml.inference import EnsemblePredictor, PricePredictor

    # Single model prediction
    predictor = PricePredictor(model_path="/path/to/model")
    forecasts = predictor.predict(features_df, horizon=24)

    # Ensemble prediction
    ensemble = EnsemblePredictor(model_path="/path/to/ensemble")
    forecasts = ensemble.predict(features_df, horizon=24, confidence_level=0.9)
"""

from ml.inference.predictor import PricePredictor
from ml.inference.ensemble_predictor import EnsemblePredictor

__all__ = [
    "PricePredictor",
    "EnsemblePredictor",
]
