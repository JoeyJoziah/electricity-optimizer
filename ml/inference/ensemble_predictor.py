"""
Ensemble Predictor Module

Combines predictions from multiple models (CNN-LSTM, XGBoost, LightGBM)
using weighted averaging for improved accuracy and robustness.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yaml

from ml.inference.predictor import PricePredictor

logger = logging.getLogger(__name__)


class EnsemblePredictor:
    """
    Ensemble model predictor combining CNN-LSTM, XGBoost, and LightGBM.

    Uses weighted averaging of predictions with configurable weights.
    Provides improved uncertainty estimation by combining model outputs.

    Args:
        model_path: Path to ensemble model directory containing:
                   - cnn_lstm/
                   - xgboost/
                   - lightgbm/
                   - metadata.yaml
        weights: Optional dict of model weights. If None, uses metadata.

    Example:
        ensemble = EnsemblePredictor("/path/to/ensemble")
        forecasts = ensemble.predict(
            features_df,
            horizon=24,
            confidence_level=0.9,
            return_components=True
        )
    """

    DEFAULT_WEIGHTS = {
        "cnn_lstm": {"weight": 0.5},
        "xgboost": {"weight": 0.25},
        "lightgbm": {"weight": 0.25},
    }

    def __init__(
        self,
        model_path: str,
        weights: Optional[Dict[str, Dict]] = None,
    ):
        self.model_path = model_path
        self.weights = weights or self._load_weights()
        self.predictors: Dict[str, PricePredictor] = {}
        self.version = None

        self._load_models()
        self._load_metadata()

    def _load_weights(self) -> Dict[str, Dict]:
        """Load weights from metadata or use defaults."""
        metadata_path = os.path.join(self.model_path, "metadata.yaml")

        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                metadata = yaml.safe_load(f)
                return metadata.get("weights", self.DEFAULT_WEIGHTS)

        return self.DEFAULT_WEIGHTS

    def _load_models(self):
        """Load all component models."""
        model_types = ["cnn_lstm", "xgboost", "lightgbm"]

        for model_type in model_types:
            model_dir = os.path.join(self.model_path, model_type)

            if os.path.exists(model_dir):
                try:
                    self.predictors[model_type] = PricePredictor(
                        model_path=model_dir,
                        model_type=model_type,
                    )
                    logger.info(f"Loaded {model_type} component")
                except Exception as e:
                    logger.warning(f"Failed to load {model_type}: {e}")
            else:
                logger.warning(f"Model directory not found: {model_dir}")

        if not self.predictors:
            raise ValueError("No models could be loaded for ensemble")

        logger.info(f"Loaded {len(self.predictors)} ensemble components")

    def _load_metadata(self):
        """Load ensemble metadata."""
        metadata_path = os.path.join(self.model_path, "metadata.yaml")

        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                metadata = yaml.safe_load(f)
                self.version = metadata.get("version", "unknown")
        else:
            self.version = datetime.utcnow().strftime("%Y%m%d")

    def predict(
        self,
        df: pd.DataFrame,
        horizon: int = 24,
        confidence_level: float = 0.9,
        return_components: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate ensemble forecasts.

        Combines predictions from all component models using weighted
        averaging. Estimates uncertainty from prediction variance across
        models plus individual model uncertainties.

        Args:
            df: DataFrame with feature columns
            horizon: Number of hours to forecast
            confidence_level: Confidence level for intervals (0-1)
            return_components: If True, include individual model predictions

        Returns:
            Dictionary with:
                - point: Ensemble point forecasts (horizon,)
                - lower: Lower bounds (horizon,)
                - upper: Upper bounds (horizon,)
                - components: (optional) Dict of per-model predictions
        """
        component_predictions = {}
        total_weight = 0

        # Get predictions from each component
        for model_type, predictor in self.predictors.items():
            try:
                preds = predictor.predict(
                    df,
                    horizon=horizon,
                    confidence_level=confidence_level,
                )
                component_predictions[model_type] = preds
                total_weight += self.weights.get(model_type, {}).get("weight", 0)
            except Exception as e:
                logger.warning(f"Prediction failed for {model_type}: {e}")

        if not component_predictions:
            raise ValueError("All component predictions failed")

        # Normalize weights
        if total_weight == 0:
            total_weight = len(component_predictions)
            normalized_weights = {
                k: 1.0 / total_weight
                for k in component_predictions.keys()
            }
        else:
            normalized_weights = {
                k: self.weights.get(k, {}).get("weight", 0) / total_weight
                for k in component_predictions.keys()
            }

        # Combine point predictions
        ensemble_point = np.zeros(horizon)
        for model_type, preds in component_predictions.items():
            weight = normalized_weights.get(model_type, 0)
            ensemble_point += weight * preds["point"][:horizon]

        # Calculate uncertainty from multiple sources:
        # 1. Variance across model predictions
        # 2. Average of individual model uncertainties

        # Model variance (epistemic uncertainty)
        point_stack = np.stack([
            preds["point"][:horizon]
            for preds in component_predictions.values()
        ])
        model_variance = np.var(point_stack, axis=0)

        # Average individual uncertainty (aleatoric uncertainty)
        individual_uncertainties = []
        for model_type, preds in component_predictions.items():
            weight = normalized_weights.get(model_type, 0)
            width = preds["upper"][:horizon] - preds["lower"][:horizon]
            individual_uncertainties.append(weight * width)

        avg_uncertainty = np.sum(individual_uncertainties, axis=0)

        # Combine uncertainties (assuming independence)
        total_std = np.sqrt(model_variance + (avg_uncertainty / 3.92) ** 2)

        # Calculate confidence intervals
        z_score = 1.645 if confidence_level == 0.9 else 1.96
        ensemble_lower = ensemble_point - z_score * total_std
        ensemble_upper = ensemble_point + z_score * total_std

        result = {
            "point": ensemble_point,
            "lower": ensemble_lower,
            "upper": ensemble_upper,
        }

        if return_components:
            result["components"] = {
                model_type: preds["point"][:horizon]
                for model_type, preds in component_predictions.items()
            }

        return result

    def get_model_weights(self) -> Dict[str, float]:
        """Get normalized model weights."""
        total = sum(
            self.weights.get(k, {}).get("weight", 0)
            for k in self.predictors.keys()
        )

        if total == 0:
            return {k: 1.0 / len(self.predictors) for k in self.predictors.keys()}

        return {
            k: self.weights.get(k, {}).get("weight", 0) / total
            for k in self.predictors.keys()
        }

    def evaluate(
        self,
        df: pd.DataFrame,
        actuals: np.ndarray,
        horizon: int = 24,
    ) -> Dict[str, float]:
        """
        Evaluate ensemble performance against actual values.

        Args:
            df: DataFrame with feature columns
            actuals: Actual price values (horizon,)
            horizon: Forecast horizon

        Returns:
            Dictionary with metrics:
                - mape: Mean Absolute Percentage Error
                - rmse: Root Mean Squared Error
                - mae: Mean Absolute Error
                - coverage: Confidence interval coverage
        """
        predictions = self.predict(df, horizon=horizon)

        point = predictions["point"]
        lower = predictions["lower"]
        upper = predictions["upper"]

        # MAPE
        mape = np.mean(np.abs((actuals - point) / (actuals + 1e-8))) * 100

        # RMSE
        rmse = np.sqrt(np.mean((actuals - point) ** 2))

        # MAE
        mae = np.mean(np.abs(actuals - point))

        # Coverage (what % of actuals fall within CI)
        in_interval = (actuals >= lower) & (actuals <= upper)
        coverage = np.mean(in_interval) * 100

        return {
            "mape": float(mape),
            "rmse": float(rmse),
            "mae": float(mae),
            "coverage": float(coverage),
        }
