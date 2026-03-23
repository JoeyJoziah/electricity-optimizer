"""
Ensemble Predictor Module

Combines predictions from multiple models (CNN-LSTM, XGBoost, LightGBM)
using weighted averaging for improved accuracy and robustness.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import yaml

from ml.inference.predictor import PricePredictor

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


class EnsemblePredictor:
    """
    Ensemble model predictor combining CNN-LSTM, XGBoost, and LightGBM.

    Uses weighted averaging of predictions with configurable weights.
    Provides improved uncertainty estimation by combining model outputs.

    Weights are loaded lazily on first use so that constructing an
    ``EnsemblePredictor`` never blocks on Redis or PostgreSQL I/O.  This
    avoids holding a worker thread (or stalling an event loop) during startup
    when the cache/DB may not yet be warm.

    Args:
        model_path: Path to ensemble model directory containing:
                   - cnn_lstm/
                   - xgboost/
                   - lightgbm/
                   - metadata.yaml
        weights: Optional dict of model weights.  If supplied, these weights
                 are used directly and the lazy-load path is skipped entirely.

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
        self.predictors: Dict[str, PricePredictor] = {}
        self.version = None

        # ``_weights`` is None until ``weights`` property is first accessed.
        # Callers may pass explicit weights to skip the lazy-load path entirely
        # (e.g. in tests or when weights are already known).
        self._weights: Optional[Dict[str, Dict]] = weights

        self._load_models()
        self._load_metadata()

    # ------------------------------------------------------------------
    # Async construction helper
    # ------------------------------------------------------------------

    @classmethod
    async def load_async(
        cls,
        model_path: str,
        weights: Optional[Dict[str, Dict]] = None,
    ) -> "EnsemblePredictor":
        """Construct an EnsemblePredictor without blocking the event loop.

        ``__init__`` calls ``_load_models()`` which invokes ``PricePredictor``
        constructors that may perform blocking I/O (``joblib.load``,
        ``torch.load``, file reads).  Calling ``EnsemblePredictor(...)``
        directly from an ``async`` function would block the uvicorn worker
        thread for the duration of model loading.

        This classmethod offloads the entire construction to a thread pool via
        ``asyncio.to_thread`` so the event loop stays unblocked.

        Args:
            model_path: Path to ensemble model directory.
            weights: Optional explicit weights dict (skips Redis/DB lazy load).

        Returns:
            A fully initialised ``EnsemblePredictor`` instance.

        Example::

            predictor = await EnsemblePredictor.load_async("/path/to/ensemble")
            result = await asyncio.to_thread(predictor.predict, df, horizon=24)
        """
        return await asyncio.to_thread(cls, model_path, weights)

    # ------------------------------------------------------------------
    # Lazy weight loading
    # ------------------------------------------------------------------

    @property
    def weights(self) -> Dict[str, Dict]:
        """Return ensemble weights, loading from Redis/DB on first access.

        The first call to this property triggers blocking I/O (Redis then
        PostgreSQL fallback).  All subsequent calls return the cached result.
        Lazy loading means the constructor never blocks, which is safe in
        both sync (Gunicorn) and async (uvicorn / event-loop) contexts.
        """
        if self._weights is None:
            self._weights = self._load_weights()
        return self._weights

    @weights.setter
    def weights(self, value: Dict[str, Dict]) -> None:
        self._weights = value

    def _load_weights(self) -> Dict[str, Dict]:
        """Load weights from Redis, PostgreSQL (fallback), metadata file, or defaults.

        Load order:
        1. Redis (fast, set by LearningService on every nightly cycle).
        2. PostgreSQL model_config table (durable, survives Render restarts).
        3. metadata.yaml on disk.
        4. Hard-coded DEFAULT_WEIGHTS.
        """
        # 1. Try Redis first (dynamic weights from nightly learning)
        try:
            redis_weights = self._load_weights_from_redis()
            if redis_weights:
                logger.info("ensemble_weights_loaded_from_redis")
                return redis_weights
        except Exception as e:
            logger.warning(
                "Failed to load model weights from Redis: %s, trying PostgreSQL", e
            )

        # 2. Try PostgreSQL (durable fallback that survives restarts)
        try:
            db_weights = self._load_weights_from_db()
            if db_weights:
                logger.info("ensemble_weights_loaded_from_db")
                return db_weights
        except Exception as e:
            logger.warning(
                "Failed to load model weights from DB: %s, using file/defaults", e
            )

        return self._load_weights_from_file()

    @staticmethod
    def _load_weights_from_db() -> Optional[Dict[str, Dict]]:
        """
        Synchronously load ensemble weights from PostgreSQL model_config table.

        Uses a raw psycopg2 connection so that no async event-loop is required
        at EnsemblePredictor construction time (which may run outside an async
        context, e.g. during a Gunicorn worker startup).

        The DATABASE_URL environment variable must be set.  If it is absent or
        the query fails the method returns None so the caller can fall back to
        the file/default path.
        """
        try:
            import json as _json
            import os
            import psycopg2

            db_url = os.environ.get("DATABASE_URL", "")
            if not db_url:
                return None

            conn = psycopg2.connect(db_url)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT weights_json
                          FROM model_config
                         WHERE model_name = 'ensemble'
                           AND is_active = true
                         ORDER BY created_at DESC
                         LIMIT 1
                        """
                    )
                    row = cur.fetchone()
                    if row is None:
                        return None
                    weights_raw = row[0]
                    # psycopg2 may return a dict (JSON type) or a string
                    if isinstance(weights_raw, str):
                        return _json.loads(weights_raw)
                    return weights_raw
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to load model weights from DB: %s", e)
        return None

    @staticmethod
    def _load_weights_from_redis() -> Optional[Dict[str, Dict]]:
        """Try to load ensemble weights from Redis (sync, for on-demand access)."""
        try:
            import redis as _redis

            r = _redis.from_url(
                os.environ.get("REDIS_URL", "redis://localhost:6379"),
                decode_responses=True,
            )
            cached = r.get("model:ensemble_weights")
            if cached:
                import json as _json

                return _json.loads(cached)
        except Exception as e:
            logger.warning(
                "Failed to load model weights from Redis: %s, using defaults", e
            )
        return None

    def _load_weights_from_file(self) -> Dict[str, Dict]:
        """Load weights from metadata.yaml or use defaults."""
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
                    logger.info("Loaded %s component", model_type)
                except Exception as e:
                    logger.warning("Failed to load %s: %s", model_type, e)
            else:
                logger.warning("Model directory not found: %s", model_dir)

        if not self.predictors:
            raise ValueError("No models could be loaded for ensemble")

        logger.info("Loaded %d ensemble components", len(self.predictors))

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
        # Validate input for NaN / infinity before any inference
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            feature_values = df[numeric_cols].values
            if np.any(np.isnan(feature_values)):
                raise ValueError("Input features contain NaN values")
            if np.any(np.isinf(feature_values)):
                raise ValueError("Input features contain infinite values")

        component_predictions = {}
        total_weight = 0

        # Accessing self.weights triggers lazy load on first call only
        current_weights = self.weights

        # Get predictions from each component
        for model_type, predictor in self.predictors.items():
            try:
                preds = predictor.predict(
                    df,
                    horizon=horizon,
                    confidence_level=confidence_level,
                )
                component_predictions[model_type] = preds
                total_weight += current_weights.get(model_type, {}).get("weight", 0)
            except Exception as e:
                logger.warning("Prediction failed for %s: %s", model_type, e)

        if not component_predictions:
            raise ValueError("All component predictions failed")

        # Normalize weights
        if total_weight == 0:
            total_weight = len(component_predictions)
            normalized_weights = {
                k: 1.0 / total_weight for k in component_predictions.keys()
            }
        else:
            normalized_weights = {
                k: current_weights.get(k, {}).get("weight", 0) / total_weight
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
        point_stack = np.stack(
            [preds["point"][:horizon] for preds in component_predictions.values()]
        )
        model_variance = np.var(point_stack, axis=0)

        # Average individual uncertainty (aleatoric uncertainty)
        individual_uncertainties = []
        for model_type, preds in component_predictions.items():
            weight = normalized_weights.get(model_type, 0)
            width = preds["upper"][:horizon] - preds["lower"][:horizon]
            individual_uncertainties.append(weight * width)

        avg_uncertainty = np.sum(individual_uncertainties, axis=0)

        # Resolve the z-score for the requested confidence level.
        # Falls back to 1.96 (95 % CI) for any level not in the lookup table.
        z_score = Z_SCORES.get(confidence_level, 1.960)

        # Combine uncertainties (assuming independence).
        # avg_uncertainty is the full CI width (upper - lower), so dividing by
        # 2 * z_score converts it back to a 1-sigma std estimate regardless of
        # which confidence level was used to produce the individual bounds.
        total_std = np.sqrt(model_variance + (avg_uncertainty / (2 * z_score)) ** 2)

        # Calculate confidence intervals
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
        current_weights = self.weights
        total = sum(
            current_weights.get(k, {}).get("weight", 0) for k in self.predictors.keys()
        )

        if total == 0:
            return {k: 1.0 / len(self.predictors) for k in self.predictors.keys()}

        return {
            k: current_weights.get(k, {}).get("weight", 0) / total
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
