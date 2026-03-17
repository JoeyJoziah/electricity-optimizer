"""
Price Predictor Module

Provides inference capabilities for trained price forecasting models.
Handles model loading, feature preprocessing, and prediction generation.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Standard normal z-scores for common confidence levels (two-tailed).
# Used to construct symmetric confidence intervals: point ± z * std.
Z_SCORES: Dict[float, float] = {
    0.80: 1.282,
    0.85: 1.440,
    0.90: 1.645,
    0.95: 1.960,
    0.99: 2.576,
}

# Fractional uncertainty applied to point predictions when the model does not
# output explicit confidence bounds (e.g. tree models, 2-D CNN-LSTM output).
# A value of 0.1 means "assume 10 % of the prediction magnitude as 1-sigma std".
DEFAULT_UNCERTAINTY_FRACTION: float = 0.1

# Default train fraction when splitting training data internally.
DEFAULT_TRAIN_SPLIT: float = 0.85


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

    @staticmethod
    def _verify_hash(file_path: str, metadata_hashes: dict) -> bool:
        """Verify a file's SHA-256 hash against the manifest in metadata.yaml.

        Returns True if the hash matches or no manifest is available
        (backward-compatible). Raises ValueError on mismatch.
        """
        basename = os.path.basename(file_path)
        expected = metadata_hashes.get(basename)
        if expected is None:
            # No hash recorded — allow loading but log a warning
            logger.warning("model_hash_missing: %s", basename)
            return True

        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                sha.update(chunk)
        actual = sha.hexdigest()
        if actual != expected:
            raise ValueError(
                f"Model file hash mismatch for {basename}: "
                f"expected {expected[:16]}…, got {actual[:16]}…"
            )
        logger.info("model_hash_verified: %s", basename)
        return True

    def _load_model(self):
        """Load the trained model."""
        logger.info(f"Loading {self.model_type} model from {self.model_path}")

        # Load known-good SHA-256 hashes from metadata.yaml (if present)
        hashes: dict = {}
        metadata_path = os.path.join(self.model_path, "metadata.yaml")
        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                meta = yaml.safe_load(f) or {}
            hashes = meta.get("file_hashes", {})

        if self.model_type == "cnn_lstm":
            import torch
            from ml.models.cnn_lstm import CNNLSTMModel

            # Load model architecture config
            config_path = os.path.join(self.model_path, "config.yaml")
            if os.path.exists(config_path):
                with open(config_path) as f:
                    self.config = yaml.safe_load(f)

            # Verify hash before unsafe deserialization.
            # NOTE: weights_only=False is required for full nn.Module; we
            # mitigate with hash verification + trusted-source policy.
            # TODO: Migrate to state-dict format so weights_only=True works.
            model_file = os.path.join(self.model_path, "model.pt")
            self._verify_hash(model_file, hashes)
            self.model = torch.load(  # noqa: S614
                model_file, map_location="cpu", weights_only=False
            )
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

        # Load scaler if exists — verify hash before joblib deserialization
        scaler_path = os.path.join(self.model_path, "scaler.pkl")
        if os.path.exists(scaler_path):
            self._verify_hash(scaler_path, hashes)
            import joblib
            self.scaler = joblib.load(scaler_path)

        logger.info(f"Model loaded successfully")

    def _load_metadata(self):
        """Load model metadata including training date for freshness checks."""
        metadata_path = os.path.join(self.model_path, "metadata.yaml")
        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                metadata = yaml.safe_load(f) or {}
                self.model_version = metadata.get("version", "unknown")
                trained_at = metadata.get("trained_at")
                if trained_at:
                    self._trained_at = datetime.fromisoformat(str(trained_at))
                else:
                    self._trained_at = None
                # Expected input ranges for sanity checking predictions
                self._input_ranges = metadata.get("input_ranges", {})
        else:
            self.model_version = "unknown"
            self._trained_at = None
            self._input_ranges = {}

    def _preprocess_features(
        self,
        df: pd.DataFrame,
        sequence_length: int = 168,
    ) -> np.ndarray:
        """Preprocess features for model input."""
        # Select numeric columns only
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        # Validate for NaN / infinity before any downstream computation
        if numeric_cols:
            raw_values = df[numeric_cols].values
            if np.any(np.isnan(raw_values)):
                raise ValueError("Input features contain NaN values")
            if np.any(np.isinf(raw_values)):
                raise ValueError("Input features contain infinite values")

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
        # Model freshness check: warn if model is older than 30 days
        max_age_days = 30
        if getattr(self, "_trained_at", None):
            age_days = (datetime.utcnow() - self._trained_at).days
            if age_days > max_age_days:
                logger.warning(
                    "model_stale: version=%s age=%dd max=%dd",
                    self.model_version, age_days, max_age_days,
                )

        # Input range validation: flag out-of-distribution values
        input_ranges = getattr(self, "_input_ranges", {})
        for col, bounds in input_ranges.items():
            if col in df.columns:
                col_min, col_max = bounds.get("min"), bounds.get("max")
                if col_min is not None and df[col].min() < col_min:
                    logger.warning("input_below_range: %s=%.4f (min=%.4f)", col, float(df[col].min()), col_min)
                if col_max is not None and df[col].max() > col_max:
                    logger.warning("input_above_range: %s=%.4f (max=%.4f)", col, float(df[col].max()), col_max)

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
                    # Single output — estimate uncertainty from prediction magnitude
                    point = output.numpy()[0]
                    std = np.abs(point) * DEFAULT_UNCERTAINTY_FRACTION
                    z = Z_SCORES.get(confidence_level, 1.960)
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

                # Shift lag features: roll existing lags right, insert
                # latest prediction at position 0 (convention: col 0 = lag_1)
                if len(current_features.shape) == 2:
                    current_features = current_features.copy()
                    current_features[0, 1:] = current_features[0, :-1]
                    current_features[0, 0] = pred

            point = np.array(point)

            # Estimate uncertainty from prediction magnitude
            std = np.abs(point) * DEFAULT_UNCERTAINTY_FRACTION
            z = Z_SCORES.get(confidence_level, 1.960)
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
