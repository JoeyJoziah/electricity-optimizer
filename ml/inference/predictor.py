"""
Price Predictor Module

Provides inference capabilities for trained price forecasting models.
Handles model loading, feature preprocessing, and prediction generation.

Confidence Interval Approach
------------------------------
Intervals are produced via *split conformal prediction* (Papadopoulos 2002)
when calibration residuals are available, falling back to a Gaussian
approximation otherwise.

Split conformal prediction is distribution-free and provides marginal coverage
guarantees: if residuals are exchangeable, the empirical coverage across many
test points equals the requested level asymptotically.

Steps (performed once after training, stored alongside the model):
  1. On a held-out calibration set, compute per-horizon residuals
     r_h = |y_true_h - y_hat_h| for h in {0, …, horizon-1}.
  2. For each horizon step h, store q_lo_h and q_hi_h as the
     alpha/2 and (1-alpha/2) quantiles of the signed residuals
     (y_true_h - y_hat_h) so that asymmetric intervals can be produced.
  3. At inference time, CI = [point + q_lo_h, point + q_hi_h].

When no calibration residuals are available the module falls back to the
±z*σ approach with σ = DEFAULT_UNCERTAINTY_FRACTION * |point|, but this
fallback is clearly documented as approximate and emits a WARNING log.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime
from typing import Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd
import yaml

from ml.utils.integrity import verify_model_integrity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Standard normal z-scores for common confidence levels (two-tailed).
Z_SCORES: Dict[float, float] = {
    0.80: 1.282,
    0.85: 1.440,
    0.90: 1.645,
    0.95: 1.960,
    0.99: 2.576,
}

# Fractional uncertainty used ONLY as a last-resort fallback when no
# calibration residuals are stored.  This is clearly approximate and
# should be replaced by calling calibrate() after training.
DEFAULT_UNCERTAINTY_FRACTION: float = 0.1

# Default train fraction when splitting training data internally.
DEFAULT_TRAIN_SPLIT: float = 0.85


class PricePredictor:
    """
    Single model price predictor.

    Supports CNN-LSTM, XGBoost, and LightGBM models.

    Confidence intervals are generated via split conformal prediction when
    calibration residuals are available (call ``calibrate()`` after training),
    or fall back to an approximate Gaussian interval otherwise.

    Args:
        model_path: Path to saved model directory
        model_type: Type of model ('cnn_lstm', 'xgboost', 'lightgbm')
                   If None, inferred from model files

    Example:
        predictor = PricePredictor("/path/to/model")
        predictor.calibrate(cal_features_df, cal_actuals, horizon=24)
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

        # Conformal prediction quantiles, shape (2, horizon):
        #   [0, :] = lower quantile offsets (q_lo per horizon step, <= 0)
        #   [1, :] = upper quantile offsets (q_hi per horizon step, >= 0)
        # None means calibrate() has not been called yet.
        self._conformal_quantiles: Optional[np.ndarray] = None

        self._load_model()
        self._load_metadata()

    def _infer_model_type(self) -> str:
        """Infer model type from files in model directory."""
        if os.path.exists(os.path.join(self.model_path, "model.pt")):
            return "cnn_lstm"
        elif os.path.exists(os.path.join(self.model_path, "model.json")):
            return "xgboost"
        elif os.path.exists(
            os.path.join(self.model_path, "lgb_model_0.pkl")
        ) or os.path.exists(os.path.join(self.model_path, "model.txt")):
            return "lightgbm"
        else:
            raise ValueError(f"Cannot infer model type from {self.model_path}")

    @staticmethod
    def _get_signing_key() -> Optional[bytes]:
        """Return the HMAC signing key from the environment, or None if unset.

        The key is read from the ML_MODEL_SIGNING_KEY environment variable.
        If unset, integrity checks fall back to plain SHA-256 (backward-compat)
        with a WARNING — this is insecure because an attacker who controls the
        model file can recompute the hash and update metadata.yaml.

        Set ML_MODEL_SIGNING_KEY to a 32+ byte random hex string in production.
        """
        raw = os.environ.get("ML_MODEL_SIGNING_KEY", "")
        if not raw:
            return None
        try:
            return bytes.fromhex(raw)
        except ValueError:
            # Accept raw bytes (non-hex) for backward compatibility
            return raw.encode()

    @staticmethod
    def _verify_hash(file_path: str, metadata_hashes: dict) -> bool:
        """Verify a file's integrity against the manifest in metadata.yaml.

        When ML_MODEL_SIGNING_KEY is set, uses HMAC-SHA256 with the secret key
        so that an attacker who controls the model file cannot forge a valid
        signature by recomputing the hash.  Without the key, falls back to
        plain SHA-256 (backward-compatible) with a security WARNING.

        Returns True if verification passes. Raises ValueError on mismatch.
        """
        basename = os.path.basename(file_path)
        expected = metadata_hashes.get(basename)
        if expected is None:
            # No hash/MAC recorded — allow loading but log a warning
            logger.warning("model_integrity_missing: %s", basename)
            return True

        # Read the file contents once
        content = bytearray()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                content.extend(chunk)

        signing_key = PricePredictor._get_signing_key()
        if signing_key:
            # HMAC-SHA256: key-dependent MAC — cannot be forged without the key
            actual = hmac.new(signing_key, bytes(content), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(actual, expected):
                raise ValueError(
                    f"Model file HMAC mismatch for {basename}: "
                    f"expected {expected[:16]}…, got {actual[:16]}…"
                )
            logger.info("model_hmac_verified: %s", basename)
        else:
            # Fallback: plain SHA-256 (bypassable — set ML_MODEL_SIGNING_KEY)
            logger.warning(
                "model_signing_key_missing: using plain SHA-256 for %s. "
                "Set ML_MODEL_SIGNING_KEY for tamper-evident verification.",
                basename,
            )
            sha = hashlib.sha256(bytes(content))
            actual = sha.hexdigest()
            if not hmac.compare_digest(actual, expected):
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

            # Load model architecture config (required to reconstruct the model
            # before loading state_dict weights).
            config_path = os.path.join(self.model_path, "config.yaml")
            if os.path.exists(config_path):
                with open(config_path) as f:
                    self.config = yaml.safe_load(f)

            # Verify hash before deserialization to ensure model file integrity.
            # weights_only=True restricts unpickling to safe tensor/storage
            # primitives only, preventing arbitrary code execution from
            # malicious .pt files (CVE class: unsafe pickle deserialization).
            # The .pt file must contain a state_dict (OrderedDict of tensors),
            # NOT a full nn.Module object saved via torch.save(model) — the
            # trainer's save() method uses torch.save(model.state_dict(), path)
            # to guarantee this.
            model_file = os.path.join(self.model_path, "model.pt")
            self._verify_hash(model_file, hashes)
            state_dict = torch.load(model_file, map_location="cpu", weights_only=True)

            # Rebuild the model architecture from config, then load weights.
            # This is required because state_dict loading needs an instantiated
            # nn.Module before weights can be applied.
            if self.config is not None:
                from ml.training.cnn_lstm_trainer import CNNLSTMTrainer

                trainer = CNNLSTMTrainer(self.config, {})
                # Infer n_features and sequence_length from the saved config
                n_features = self.config.get("input", {}).get("n_features", 19)
                sequence_length = self.config.get("input", {}).get(
                    "sequence_length", 168
                )
                trainer._build_model(n_features, sequence_length)
                trainer.model.load_state_dict(state_dict)
                self.model = trainer.model
            else:
                # config.yaml is required to reconstruct the CNN-LSTM architecture
                # before loading the state_dict.  Without it we cannot safely
                # deserialise the model — the legacy unsafe full-module load path
                # (which allowed arbitrary pickle execution) has been removed
                # (CVE class: unsafe pickle deserialization, [13-P0-1]).
                # Re-save the model using CNNLSTMTrainer.save() which writes
                # both config.yaml and a state_dict .pt file.
                raise ValueError(
                    f"config.yaml not found in {self.model_path}. "
                    "Re-save the model with CNNLSTMTrainer.save() to produce "
                    "a config.yaml alongside the state_dict .pt file. "
                    "The unsafe legacy full-module load path has been removed."
                )
            self.model.eval()

        elif self.model_type == "xgboost":
            import xgboost as xgb

            model_file = os.path.join(self.model_path, "model.json")
            self.model = xgb.XGBRegressor()
            self.model.load_model(model_file)

        elif self.model_type == "lightgbm":
            import joblib
            import lightgbm as lgb

            # Prefer the sklearn-wrapped LGBMRegressor (joblib .pkl) saved by
            # LightGBMForecaster.save() so that predict() has consistent feature
            # type expectations.  Fall back to loading a raw lgb.Booster from
            # the legacy .txt format for backward compatibility with models
            # saved before this fix.
            pkl_file = os.path.join(self.model_path, "lgb_model_0.pkl")
            txt_file = os.path.join(self.model_path, "model.txt")
            if os.path.exists(pkl_file):
                # Load the first step's wrapped model; full multi-step loading
                # is handled by LightGBMForecaster.load() for ensemble use.
                # Verify HMAC integrity before joblib deserialization.
                verify_model_integrity(pkl_file)
                self.model = joblib.load(pkl_file)
            elif os.path.exists(txt_file):
                logger.warning(
                    "lightgbm_legacy_format: loading raw Booster from .txt; "
                    "re-save with LightGBMForecaster.save() for type consistency."
                )
                self.model = lgb.Booster(model_file=txt_file)
            else:
                raise FileNotFoundError(
                    f"No LightGBM model file found in {self.model_path}"
                )

        # Load scaler if exists.
        # Two-layer integrity check:
        #   1. _verify_hash: metadata.yaml HMAC/SHA-256 (legacy, backward-compat)
        #   2. verify_model_integrity: companion .sig file HMAC (new, mandatory
        #      for all artifacts saved by CNNLSTMTrainer.save() or later)
        scaler_path = os.path.join(self.model_path, "scaler.pkl")
        if os.path.exists(scaler_path):
            self._verify_hash(scaler_path, hashes)
            verify_model_integrity(scaler_path)
            import joblib

            self.scaler = joblib.load(scaler_path)

        logger.info("Model loaded successfully")

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
        feature_cols = [c for c in numeric_cols if c not in ["target", "price_target"]]

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

    # -------------------------------------------------------------------------
    # Conformal calibration
    # -------------------------------------------------------------------------

    def calibrate(
        self,
        cal_features: Union[pd.DataFrame, np.ndarray],
        cal_actuals: np.ndarray,
        horizon: int = 24,
        coverage: float = 0.80,
    ) -> "PricePredictor":
        """Calibrate the predictor using split conformal prediction.

        Call this ONCE on a held-out calibration set after training (before
        the model is used in production).  The calibration set must NOT overlap
        with the training data.

        The method computes per-horizon signed residuals
        r_{i,h} = y_{i,h} - ŷ_{i,h}  for every calibration sample i and
        horizon step h, then stores the alpha/2 and (1-alpha/2) quantiles
        as lower/upper offsets.  At inference time the intervals become:

            lower_h = point_h + q_lo_h
            upper_h = point_h + q_hi_h

        This gives marginal coverage ≈ ``coverage`` over exchangeable test data
        without any parametric distributional assumption.

        Args:
            cal_features: Calibration features (DataFrame or 2-D/3-D ndarray).
                          Each row (or batch element) is one calibration window.
            cal_actuals:  Ground-truth targets, shape (n_cal, horizon).
            horizon:      Number of forecast steps.
            coverage:     Desired marginal coverage, e.g. 0.80 → 80 % CI.
                          This maps to alpha = 1 - coverage.

        Returns:
            self (for chaining)
        """
        alpha = 1.0 - coverage
        lo_q = alpha / 2.0  # e.g. 0.10 for 80 % coverage
        hi_q = 1.0 - alpha / 2.0  # e.g. 0.90 for 80 % coverage

        # Collect point predictions for all calibration samples.
        # We need raw point predictions without applying existing conformal
        # offsets, so we temporarily clear them.
        saved_quantiles = self._conformal_quantiles
        self._conformal_quantiles = None
        try:
            if isinstance(cal_features, pd.DataFrame):
                # Predict each window individually when a DataFrame is passed.
                n_cal = len(cal_features)
                point_preds = np.zeros((n_cal, horizon))
                for i in range(n_cal):
                    row_df = cal_features.iloc[[i]]
                    result = self._predict_point_only(row_df, horizon=horizon)
                    point_preds[i] = result
            else:
                # ndarray: each row / slice is one sample.
                cal_arr = np.asarray(cal_features)
                if cal_arr.ndim == 2:
                    # (n_cal, n_features) — wrap each row
                    n_cal = cal_arr.shape[0]
                    point_preds = np.zeros((n_cal, horizon))
                    for i in range(n_cal):
                        row = cal_arr[[i]]
                        result = self._predict_point_only_array(row, horizon=horizon)
                        point_preds[i] = result
                elif cal_arr.ndim == 3:
                    # (n_cal, sequence_length, n_features)
                    n_cal = cal_arr.shape[0]
                    point_preds = np.zeros((n_cal, horizon))
                    for i in range(n_cal):
                        seq = cal_arr[[i]]  # shape (1, seq_len, n_features)
                        result = self._predict_point_only_array(seq, horizon=horizon)
                        point_preds[i] = result
                else:
                    raise ValueError(
                        f"cal_features must be 2-D or 3-D ndarray, got {cal_arr.ndim}-D"
                    )
        finally:
            self._conformal_quantiles = saved_quantiles

        # Signed residuals: shape (n_cal, horizon)
        actuals = np.asarray(cal_actuals)
        if actuals.shape != point_preds.shape:
            raise ValueError(
                f"cal_actuals shape {actuals.shape} does not match "
                f"predictions shape {point_preds.shape}"
            )
        residuals = actuals - point_preds  # positive → model under-predicted

        # Per-horizon quantiles, shape (horizon,)
        q_lo = np.quantile(residuals, lo_q, axis=0)  # negative → lower offset
        q_hi = np.quantile(residuals, hi_q, axis=0)  # positive → upper offset

        # Store as (2, horizon): row 0 = lower offsets, row 1 = upper offsets
        self._conformal_quantiles = np.stack([q_lo, q_hi], axis=0)

        logger.info(
            "conformal_calibrated: n_cal=%d coverage=%.0f%% "
            "mean_q_lo=%.4f mean_q_hi=%.4f",
            n_cal,
            coverage * 100,
            float(q_lo.mean()),
            float(q_hi.mean()),
        )
        return self

    def _conformal_intervals(
        self,
        point: np.ndarray,
        horizon: int,
        confidence_level: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return (lower, upper) using conformal quantiles when available.

        If conformal quantiles are not yet calibrated, falls back to the
        approximate Gaussian method with a clear WARNING log so operators
        know the intervals are not statistically grounded.

        Args:
            point:            Point predictions, shape (horizon,).
            horizon:          Number of forecast steps.
            confidence_level: Requested coverage (0-1).  Used only by the
                              fallback path; conformal uses the pre-computed
                              quantiles from calibrate().

        Returns:
            lower, upper — both shape (horizon,)
        """
        if self._conformal_quantiles is not None:
            # Trim / repeat quantiles if horizon changed after calibration.
            cal_horizon = self._conformal_quantiles.shape[1]
            if cal_horizon >= horizon:
                q_lo = self._conformal_quantiles[0, :horizon]
                q_hi = self._conformal_quantiles[1, :horizon]
            else:
                # Extend by repeating the last step's quantiles.
                pad = horizon - cal_horizon
                q_lo = np.concatenate(
                    [
                        self._conformal_quantiles[0],
                        np.full(pad, self._conformal_quantiles[0, -1]),
                    ]
                )
                q_hi = np.concatenate(
                    [
                        self._conformal_quantiles[1],
                        np.full(pad, self._conformal_quantiles[1, -1]),
                    ]
                )
            return point + q_lo, point + q_hi

        # ── Fallback: approximate Gaussian (NOT statistically grounded) ──────
        logger.warning(
            "conformal_not_calibrated: using approximate ±%.0f%% magnitude "
            "uncertainty. Call calibrate() on a held-out set for valid CIs.",
            DEFAULT_UNCERTAINTY_FRACTION * 100,
        )
        std = np.abs(point) * DEFAULT_UNCERTAINTY_FRACTION
        z = Z_SCORES.get(confidence_level, 1.960)
        return point - z * std, point + z * std

    # -------------------------------------------------------------------------
    # Internal point-prediction helpers (no CI computation, no logging noise)
    # -------------------------------------------------------------------------

    def _predict_point_only(
        self,
        df: pd.DataFrame,
        horizon: int = 24,
    ) -> np.ndarray:
        """Return raw point predictions (no CI) for a DataFrame input."""
        features = self._preprocess_features(df)
        return self._predict_point_only_array(features, horizon=horizon)

    def _predict_point_only_array(
        self,
        features: np.ndarray,
        horizon: int = 24,
    ) -> np.ndarray:
        """Return raw point predictions (no CI) for a pre-processed array.

        Tree models: single forward pass using all features as a flat 2-D
        array.  The MIMO (direct multi-output) approach predicts all horizon
        steps simultaneously from the same feature snapshot — no recursive
        feeding of predictions back as inputs, so errors do not compound.

        CNN-LSTM: standard forward pass, take the first column of the output
        if the model emits (batch, horizon, 3) or use the full output if
        (batch, horizon).
        """
        if self.model_type == "cnn_lstm":
            import torch

            with torch.no_grad():
                x = torch.FloatTensor(features)
                output = self.model(x)
                if output.dim() == 3:
                    # (batch, horizon, 3) → point is column 0
                    point = output.numpy()[0, :, 0]
                else:
                    # (batch, horizon)
                    point = output.numpy()[0]
            return point[:horizon]

        elif self.model_type in ["xgboost", "lightgbm"]:
            # MIMO: use the current feature snapshot to predict all horizon
            # steps at once.  The tree model is expected to have been trained
            # with MultiOutputRegressor (one estimator per step) so a single
            # predict() call returns shape (n_samples, horizon).
            #
            # If the stored model returns a 1-D array (single-step model),
            # we fall back to repeating the prediction — still no error
            # compounding, just lower accuracy for distant steps.
            feat_2d = features.reshape(1, -1) if features.ndim != 2 else features
            if feat_2d.shape[0] == 0:
                return np.zeros(horizon)

            raw = self.model.predict(feat_2d)
            raw = np.asarray(raw)

            if raw.ndim == 2:
                # MultiOutputRegressor: shape (n_samples, n_outputs)
                point = raw[0]
            else:
                # Single-output model: broadcast to all horizon steps
                point = np.full(horizon, float(raw[0]))

            return (
                point[:horizon]
                if len(point) >= horizon
                else np.concatenate([point, np.full(horizon - len(point), point[-1])])
            )

        else:
            raise ValueError(f"Unknown model_type: {self.model_type}")

    # -------------------------------------------------------------------------
    # Public predict API
    # -------------------------------------------------------------------------

    def predict(
        self,
        df: pd.DataFrame,
        horizon: int = 24,
        confidence_level: float = 0.9,
    ) -> Dict[str, np.ndarray]:
        """Generate price forecasts with statistically grounded intervals.

        Multi-step strategy
        -------------------
        Tree models (XGBoost / LightGBM) use a **direct multi-output (MIMO)**
        approach: a single model call with the current feature snapshot
        produces all horizon steps simultaneously.  This avoids the recursive
        strategy where prediction errors compound at each step.

        CNN-LSTM models produce all horizon steps in one forward pass by
        design.

        Confidence intervals
        --------------------
        Intervals are built by ``_conformal_intervals()``:
        - If ``calibrate()`` was called, split conformal prediction quantiles
          are used — distribution-free, empirically grounded.
        - Otherwise a Gaussian approximation (±z*σ, σ = 10 % of |point|) is
          used with a WARNING so operators know it is approximate.

        Args:
            df:               DataFrame with feature columns.
            horizon:          Number of hours to forecast.
            confidence_level: Desired CI coverage (used by fallback path).

        Returns:
            Dict with keys "point", "lower", "upper" — each shape (horizon,).
        """
        # Model freshness check: warn if model is older than 30 days
        max_age_days = 30
        if getattr(self, "_trained_at", None):
            age_days = (datetime.utcnow() - self._trained_at).days
            if age_days > max_age_days:
                logger.warning(
                    "model_stale: version=%s age=%dd max=%dd",
                    self.model_version,
                    age_days,
                    max_age_days,
                )

        # Input range validation: flag out-of-distribution values
        input_ranges = getattr(self, "_input_ranges", {})
        for col, bounds in input_ranges.items():
            if col in df.columns:
                col_min, col_max = bounds.get("min"), bounds.get("max")
                if col_min is not None and df[col].min() < col_min:
                    logger.warning(
                        "input_below_range: %s=%.4f (min=%.4f)",
                        col,
                        float(df[col].min()),
                        col_min,
                    )
                if col_max is not None and df[col].max() > col_max:
                    logger.warning(
                        "input_above_range: %s=%.4f (max=%.4f)",
                        col,
                        float(df[col].max()),
                        col_max,
                    )

        # ── Point predictions ────────────────────────────────────────────────
        features = self._preprocess_features(df)

        if self.model_type == "cnn_lstm":
            import torch

            with torch.no_grad():
                x = torch.FloatTensor(features)
                output = self.model(x)
                if output.dim() == 3:
                    # (batch, horizon, 3): column 0 = point, 1 = lo, 2 = hi
                    predictions = output.numpy()[0]  # (horizon, 3)
                    point = predictions[:horizon, 0]
                    # If model natively outputs intervals, prefer them but
                    # still allow conformal override when calibrated.
                    model_lower = predictions[:horizon, 1]
                    model_upper = predictions[:horizon, 2]
                    # Use native model intervals only if conformal is absent
                    if self._conformal_quantiles is None:
                        lower, upper = model_lower, model_upper
                    else:
                        lower, upper = self._conformal_intervals(
                            point, horizon, confidence_level
                        )
                else:
                    # 2-D output: (batch, horizon)
                    point = output.numpy()[0, :horizon]
                    lower, upper = self._conformal_intervals(
                        point, horizon, confidence_level
                    )

        elif self.model_type in ["xgboost", "lightgbm"]:
            # MIMO: predict all steps from one feature snapshot
            point = self._predict_point_only_array(features, horizon=horizon)
            lower, upper = self._conformal_intervals(point, horizon, confidence_level)

        else:
            raise ValueError(f"Unknown model_type: {self.model_type}")

        # Ensure exact horizon length
        point = np.asarray(point[:horizon])
        lower = np.asarray(lower[:horizon])
        upper = np.asarray(upper[:horizon])

        return {
            "point": point,
            "lower": lower,
            "upper": upper,
        }
