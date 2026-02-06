"""
Price Predictor Module

Provides inference capabilities for trained price forecasting models.
Handles model loading, feature preprocessing, and prediction generation.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


class PricePredictor:
    """
    Single model price predictor.

    Supports CNN-LSTM, XGBoost, and LightGBM models.

    Args:
        model_path: Path to saved model directory
        model_type: Type of model ('cnn_lstm', 'xgboost', 'lightgbm')
                   If None, inferred from model files

    Example:
        predictor = PricePredictor("/path/to/model")
        forecast = predictor.predict(features_df, horizon=24)
    """

    def __init__(
        self,
        model_path: str,
        model_type: Optional[str] = None,
    ):
        self.model_path = model_path
        self.model_type = model_type or self._infer_model_type()
        self.model = None
        self.scaler = None
        self.config = None
        self.model_version = None

        self._load_model()
        self._load_metadata()

    def _infer_model_type(self) -> str:
        """Infer model type from files in model directory."""
        if os.path.exists(os.path.join(self.model_path, "model.pt")):
            return "cnn_lstm"
        elif os.path.exists(os.path.join(self.model_path, "model.json")):
            return "xgboost"
        elif os.path.exists(os.path.join(self.model_path, "model.txt")):
            return "lightgbm"
        else:
            raise ValueError(f"Cannot infer model type from {self.model_path}")

    def _load_model(self):
        """Load the trained model."""
        logger.info(f"Loading {self.model_type} model from {self.model_path}")

        if self.model_type == "cnn_lstm":
            import torch
            from ml.models.cnn_lstm import CNNLSTMModel

            # Load model architecture config
            config_path = os.path.join(self.model_path, "config.yaml")
            if os.path.exists(config_path):
                with open(config_path) as f:
                    self.config = yaml.safe_load(f)

            # Initialize and load model
            model_file = os.path.join(self.model_path, "model.pt")
            self.model = torch.load(model_file, map_location="cpu")
            self.model.eval()

        elif self.model_type == "xgboost":
            import xgboost as xgb

            model_file = os.path.join(self.model_path, "model.json")
            self.model = xgb.XGBRegressor()
            self.model.load_model(model_file)

        elif self.model_type == "lightgbm":
            import lightgbm as lgb

            model_file = os.path.join(self.model_path, "model.txt")
            self.model = lgb.Booster(model_file=model_file)

        # Load scaler if exists
        scaler_path = os.path.join(self.model_path, "scaler.pkl")
        if os.path.exists(scaler_path):
            import joblib
            self.scaler = joblib.load(scaler_path)

        logger.info(f"Model loaded successfully")

    def _load_metadata(self):
        """Load model metadata."""
        metadata_path = os.path.join(self.model_path, "metadata.yaml")
        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                metadata = yaml.safe_load(f)
                self.model_version = metadata.get("version", "unknown")
        else:
            self.model_version = "unknown"

    def _preprocess_features(
        self,
        df: pd.DataFrame,
        sequence_length: int = 168,
    ) -> np.ndarray:
        """Preprocess features for model input."""
        # Select numeric columns only
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        # Remove target columns if present
        feature_cols = [
            c for c in numeric_cols
            if c not in ["target", "price_target"]
        ]

        # Get features
        features = df[feature_cols].values

        # Scale if scaler available
        if self.scaler:
            features = self.scaler.transform(features)

        # For CNN-LSTM, create sequences
        if self.model_type == "cnn_lstm":
            if len(features) < sequence_length:
                # Pad with zeros or repeat first values
                pad_length = sequence_length - len(features)
                padding = np.tile(features[0], (pad_length, 1))
                features = np.vstack([padding, features])

            # Take last sequence_length rows
            features = features[-sequence_length:]

            # Add batch dimension: (1, sequence_length, n_features)
            features = np.expand_dims(features, axis=0)

        return features

    def predict(
        self,
        df: pd.DataFrame,
        horizon: int = 24,
        confidence_level: float = 0.9,
    ) -> Dict[str, np.ndarray]:
        """
        Generate price forecasts.

        Args:
            df: DataFrame with feature columns
            horizon: Number of hours to forecast
            confidence_level: Confidence level for intervals (0-1)

        Returns:
            Dictionary with:
                - point: Point forecasts (horizon,)
                - lower: Lower bounds (horizon,)
                - upper: Upper bounds (horizon,)
        """
        # Preprocess features
        features = self._preprocess_features(df)

        # Generate predictions
        if self.model_type == "cnn_lstm":
            import torch

            with torch.no_grad():
                x = torch.FloatTensor(features)
                output = self.model(x)

                # Model outputs (point, lower, upper) for each horizon
                if output.dim() == 3:
                    predictions = output.numpy()[0]  # (horizon, 3)
                    point = predictions[:, 0]
                    lower = predictions[:, 1]
                    upper = predictions[:, 2]
                else:
                    # Single output, estimate uncertainty
                    point = output.numpy()[0]
                    std = np.abs(point) * 0.1  # 10% uncertainty
                    z = 1.645 if confidence_level == 0.9 else 1.96
                    lower = point - z * std
                    upper = point + z * std

        elif self.model_type in ["xgboost", "lightgbm"]:
            # Tree models predict one step at a time
            # For multi-step, use recursive or direct approach
            point = []
            current_features = features[-1:] if len(features.shape) == 2 else features

            for h in range(horizon):
                if self.model_type == "xgboost":
                    pred = self.model.predict(current_features)[0]
                else:
                    pred = self.model.predict(current_features)[0]

                point.append(pred)

                # Update features for next step (simplified)
                # In production, would properly update lag features

            point = np.array(point)

            # Estimate uncertainty from model variance
            std = np.abs(point) * 0.1
            z = 1.645 if confidence_level == 0.9 else 1.96
            lower = point - z * std
            upper = point + z * std

        # Ensure horizon length
        point = point[:horizon]
        lower = lower[:horizon]
        upper = upper[:horizon]

        return {
            "point": point,
            "lower": lower,
            "upper": upper,
        }
