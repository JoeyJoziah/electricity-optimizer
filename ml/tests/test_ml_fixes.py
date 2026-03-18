"""
Tests for three ML pipeline fixes:

  2.1 — Data leakage: scaler and fill must be applied per-split, not on the
        whole dataset before train/test split.
  2.2 — Multi-step inference: MIMO (direct multi-output) strategy replaces
        recursive prediction to prevent error compounding; no column[0]
        hardcoding.
  2.3 — Confidence intervals: split conformal prediction replaces the
        fabricated ±10 % magnitude fallback.

All tests are written without requiring TensorFlow, XGBoost, or LightGBM
installed — heavy dependencies are mocked where needed.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from typing import Tuple
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Pre-mock the TensorFlow-dependent imports so train_forecaster.py can be
# loaded without TF installed.  This mirrors the approach in
# test_train_forecaster.py.
# ---------------------------------------------------------------------------

_mock_price_forecaster = types.ModuleType("ml.models.price_forecaster")
_mock_price_forecaster.ElectricityPriceForecaster = MagicMock()
_mock_price_forecaster.ModelConfig = MagicMock()

_mock_ensemble = types.ModuleType("ml.models.ensemble")
_mock_ensemble.EnsembleForecaster = MagicMock()
_mock_ensemble.EnsembleConfig = MagicMock()
_mock_ensemble.XGBoostConfig = MagicMock()
_mock_ensemble.LightGBMConfig = MagicMock()

_mock_models = types.ModuleType("ml.models")
sys.modules.setdefault("ml.models", _mock_models)
sys.modules.setdefault("ml.models.price_forecaster", _mock_price_forecaster)
sys.modules.setdefault("ml.models.ensemble", _mock_ensemble)

# Import the REAL feature engineering and data modules so we can test them.
# We do NOT mock these because the leakage tests need to exercise them.
# ---------------------------------------------------------------------------

_BASE_TRAINING = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "training")
)


def _load_train_forecaster():
    """Direct-load train_forecaster.py so it picks up our sys.modules stubs."""
    spec = importlib.util.spec_from_file_location(
        "ml.training.train_forecaster",
        os.path.join(_BASE_TRAINING, "train_forecaster.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ml.training.train_forecaster"] = mod
    spec.loader.exec_module(mod)
    return mod


_tf_mod = _load_train_forecaster()
ModelTrainer = _tf_mod.ModelTrainer
TrainingConfig = _tf_mod.TrainingConfig


# ===========================================================================
# Helpers
# ===========================================================================


def _make_price_df(n_hours: int = 2000, seed: int = 42) -> pd.DataFrame:
    """Synthetic hourly price DataFrame with DateTimeIndex."""
    rng = np.random.RandomState(seed)
    hours = np.arange(n_hours)
    price = (
        50 + 20 * np.sin(2 * np.pi * (hours % 24 - 6) / 24) + rng.normal(0, 5, n_hours)
    )
    price = np.maximum(price, 5)
    dates = pd.date_range("2024-01-01", periods=n_hours, freq="h")
    return pd.DataFrame({"price": price}, index=dates)


def _make_feature_df(
    n_rows: int = 200, n_features: int = 5, seed: int = 0
) -> pd.DataFrame:
    """Synthetic feature DataFrame for predictor tests."""
    rng = np.random.RandomState(seed)
    data = {f"feat_{i}": rng.randn(n_rows) for i in range(n_features)}
    dates = pd.date_range("2024-06-01", periods=n_rows, freq="h")
    return pd.DataFrame(data, index=dates)


def _stub_predictor(model_type: str = "xgboost", model=None, scaler=None):
    """Build a PricePredictor instance without touching the filesystem."""
    from ml.inference.predictor import PricePredictor

    p = PricePredictor.__new__(PricePredictor)
    p.model_path = "/fake"
    p.model_type = model_type
    p.model = model
    p.scaler = scaler
    p.config = None
    p.model_version = "test-1.0"
    p._conformal_quantiles = None
    p._trained_at = None
    p._input_ranges = {}
    return p


def _make_trainer_with_real_feature_engine(
    n_hours: int = 500,
) -> Tuple[ModelTrainer, pd.DataFrame]:
    """
    Create a ModelTrainer wired to the REAL ElectricityPriceFeatureEngine
    (not the mock from sys.modules).  This is needed for leakage tests.
    """
    from ml.data.feature_engineering import (
        ElectricityPriceFeatureEngine,
        create_dummy_data,
    )  # real

    config = TrainingConfig(
        use_dummy_data=False,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
        epochs=1,
        sequence_length=24,
        forecast_horizon=6,
    )

    # Patch the module-level name inside the loaded trainer so it uses the real engine
    _tf_mod.ElectricityPriceFeatureEngine = ElectricityPriceFeatureEngine
    _tf_mod.create_dummy_data = create_dummy_data

    trainer = ModelTrainer(config)
    df = _make_price_df(n_hours=n_hours)
    return trainer, df


# ===========================================================================
# Task 2.1 — No data leakage from scaler / fill
# ===========================================================================


class TestNoDataLeakageScaler:
    """The scaler must be fitted exclusively on training data."""

    def test_feature_engine_fit_uses_only_training_slice(self):
        """
        Verify that after calling ModelTrainer.prepare_features(), the scaler
        was fitted on the training split, not the whole DataFrame.

        Strategy: we spy on ElectricityPriceFeatureEngine.fit() to capture
        the DataFrame it receives and assert its length equals the training
        fraction of the raw data.
        """
        from ml.data.feature_engineering import ElectricityPriceFeatureEngine

        trainer, df = _make_trainer_with_real_feature_engine(n_hours=500)

        fit_calls = []
        original_fit = ElectricityPriceFeatureEngine.fit

        def spy_fit(self_inner, df_arg, *args, **kwargs):
            fit_calls.append(df_arg)
            return original_fit(self_inner, df_arg, *args, **kwargs)

        ElectricityPriceFeatureEngine.fit = spy_fit
        try:
            trainer.prepare_features(df)
        finally:
            ElectricityPriceFeatureEngine.fit = original_fit

        assert len(fit_calls) == 1, (
            "ElectricityPriceFeatureEngine.fit() must be called exactly once "
            f"(called {len(fit_calls)} times)"
        )

        fitted_df = fit_calls[0]
        expected_len = int(len(df) * trainer.config.train_ratio)

        assert len(fitted_df) <= expected_len + 1, (
            f"Scaler was fitted on {len(fitted_df)} rows but training split "
            f"should be at most {expected_len} rows. "
            "This indicates the full dataset was used (data leakage)."
        )
        assert len(fitted_df) >= expected_len - 10, (
            f"Scaler was fitted on only {len(fitted_df)} rows (expected ~{expected_len})."
        )

    def test_scaler_fitted_on_train_only_not_full_dataset(self):
        """
        Direct unit test: calling feature_engine.fit(train_only_df) followed
        by feature_engine.transform(test_df) must NOT re-fit the scaler.

        The StandardScaler's mean_ must reflect only the training data.
        """
        from ml.data.feature_engineering import ElectricityPriceFeatureEngine

        df = _make_price_df(n_hours=600)
        n_train = 420  # 70 %

        df_train = df.iloc[:n_train]
        df_test = df.iloc[n_train:]

        engine = ElectricityPriceFeatureEngine(
            country="US", lookback_hours=24, forecast_hours=6
        )
        engine.fit(df_train)

        # Store the scaler mean learned on train only
        train_mean = engine.scaler.mean_.copy()

        # Transform test data — should NOT change the fitted scaler
        engine.transform(df_test)

        # Scaler mean must be identical after transforming test data
        np.testing.assert_array_equal(
            engine.scaler.mean_,
            train_mean,
            err_msg="Scaler mean changed after transform(test) — scaler was re-fit on test data.",
        )

    def test_ffill_does_not_propagate_across_split_boundary(self):
        """
        ffill/bfill must NOT bleed future values from test into train.

        We create a DataFrame where the first row of the test split has a
        known sentinel price, then verify that after per-split transform()
        the training features do NOT contain the sentinel value.
        """
        from ml.data.feature_engineering import ElectricityPriceFeatureEngine

        n_hours = 200
        df = _make_price_df(n_hours=n_hours)

        # Mark the first test row with a sentinel (extremely high price)
        split = 140
        sentinel = 9999.0
        df_train = df.iloc[:split].copy()
        df_test = df.iloc[split:].copy()
        df_test.iloc[0, df_test.columns.get_loc("price")] = sentinel

        engine = ElectricityPriceFeatureEngine(
            country="US", lookback_hours=24, forecast_hours=6
        )
        engine.fit(df_train)

        # Transform each split independently (as the fixed pipeline does)
        train_feat = engine.transform(df_train)
        # test transform should not affect train
        _test_feat = engine.transform(df_test)

        # The sentinel should NOT appear in the training features
        assert sentinel not in train_feat.values, (
            "Sentinel value from test split leaked into training features — "
            "ffill/bfill crosses split boundary."
        )

    def test_prepare_features_returns_correct_shape(self):
        """
        Ensure prepare_features() still returns (X, y) with the right
        dimensionality after the leakage fix.
        """
        trainer, df = _make_trainer_with_real_feature_engine(n_hours=500)

        result = trainer.prepare_features(df)
        assert len(result) == 2, "prepare_features() should return (X, y)"
        X, y = result

        assert X.ndim == 3, f"X must be 3-D, got {X.ndim}-D"
        assert y.ndim == 2, f"y must be 2-D, got {y.ndim}-D"
        assert X.shape[1] == trainer.config.sequence_length
        assert y.shape[1] == trainer.config.forecast_horizon

    def test_split_uses_precomputed_boundaries(self):
        """
        After prepare_features(), split_data() must honour the boundaries
        stored in _train_seq_end / _val_seq_end rather than re-computing
        them from sequence count, which would give a different proportion.
        """
        trainer, df = _make_trainer_with_real_feature_engine(n_hours=500)

        X, y = trainer.prepare_features(df)

        assert hasattr(trainer, "_train_seq_end"), (
            "ModelTrainer must set _train_seq_end after prepare_features()"
        )
        assert hasattr(trainer, "_val_seq_end"), (
            "ModelTrainer must set _val_seq_end after prepare_features()"
        )

        (X_tr, y_tr), (X_v, y_v), (X_te, y_te) = trainer.split_data(X, y)

        assert len(X_tr) == trainer._train_seq_end
        assert len(X_v) == trainer._val_seq_end - trainer._train_seq_end
        assert len(X_te) == len(X) - trainer._val_seq_end

    def test_test_sequences_are_independent_of_training_data(self):
        """
        Each split is transformed independently, so no test-data statistics
        should influence the scaled training features.

        Verify: the scaler applied to train features uses only train statistics
        by checking that mean of scaled features is ~0 (StandardScaler fitted
        on train data applied to train data should give mean ~0).
        """
        from ml.data.feature_engineering import ElectricityPriceFeatureEngine

        df = _make_price_df(n_hours=600)
        n_train = 420

        df_train = df.iloc[:n_train]
        _df_test = df.iloc[n_train:]  # noqa: F841

        engine = ElectricityPriceFeatureEngine(
            country="US", lookback_hours=24, forecast_hours=6
        )
        engine.fit(df_train)
        train_feat = engine.transform(df_train)

        # When StandardScaler is fitted and applied to training data, the
        # scaled feature means should be close to 0.
        feature_cols = [c for c in train_feat.columns if c != "price"]
        if feature_cols:
            means = train_feat[feature_cols].mean()
            # Allow tolerance for edge effects from lag/rolling features
            assert means.abs().mean() < 1.0, (
                f"Scaled training features have non-zero mean {means.abs().mean():.3f}; "
                "suggests scaler was not fitted on training data only."
            )


# ===========================================================================
# Task 2.2 — MIMO multi-step inference (no recursive strategy)
# ===========================================================================


class TestMIMOInferenceStrategy:
    """Tree model prediction must use MIMO, not recursive error-compounding."""

    def test_xgboost_model_called_once_not_horizon_times(self):
        """
        With the MIMO fix, predict() must call model.predict() ONCE
        (one feature snapshot → all horizon steps), NOT once per horizon step.

        The recursive strategy called model.predict() `horizon` times.
        """
        horizon = 24

        mimo_output = np.random.randn(1, horizon).astype(np.float32) + 50.0
        mock_model = MagicMock()
        mock_model.predict.return_value = mimo_output

        p = _stub_predictor("xgboost", model=mock_model)
        df = _make_feature_df(n_rows=200)
        p.predict(df, horizon=horizon)

        assert mock_model.predict.call_count == 1, (
            f"model.predict() called {mock_model.predict.call_count} times — "
            "expected 1 (MIMO). Recursive strategy still in use."
        )

    def test_lightgbm_model_called_once_not_horizon_times(self):
        """Same MIMO check for LightGBM."""
        horizon = 12

        mimo_output = np.random.randn(1, horizon).astype(np.float32) + 40.0
        mock_model = MagicMock()
        mock_model.predict.return_value = mimo_output

        p = _stub_predictor("lightgbm", model=mock_model)
        df = _make_feature_df(n_rows=200)
        p.predict(df, horizon=horizon)

        assert mock_model.predict.call_count == 1, (
            f"LightGBM model.predict() called {mock_model.predict.call_count} times — "
            "expected 1 (MIMO)."
        )

    def test_mimo_output_shape_is_horizon(self):
        """Point forecast must have length equal to `horizon`."""
        horizon = 24
        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), 55.0)

        p = _stub_predictor("xgboost", model=mock_model)
        df = _make_feature_df()
        result = p.predict(df, horizon=horizon)

        assert result["point"].shape == (horizon,), (
            f"Expected point shape ({horizon},), got {result['point'].shape}"
        )

    def test_mimo_multiple_target_columns_handled(self):
        """
        MIMO predict must handle models that return multiple output columns
        without hardcoding column[0].
        """
        horizon = 6
        expected_values = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
        mock_model = MagicMock()
        mock_model.predict.return_value = expected_values.reshape(1, -1)

        p = _stub_predictor("xgboost", model=mock_model)
        df = _make_feature_df()
        result = p.predict(df, horizon=horizon)

        np.testing.assert_allclose(result["point"], expected_values, rtol=1e-5)

    def test_single_output_model_broadcasts_to_horizon(self):
        """
        A single-output model (1-D return) must be broadcast to fill all
        horizon steps rather than trying to index beyond position 0.
        """
        horizon = 8
        single_val = 42.0
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([single_val])

        p = _stub_predictor("xgboost", model=mock_model)
        df = _make_feature_df()
        result = p.predict(df, horizon=horizon)

        assert result["point"].shape == (horizon,)
        assert np.all(result["point"] == single_val), (
            "Single-output model should broadcast its value to all steps."
        )

    def test_predict_point_only_array_mimo_2d(self):
        """
        _predict_point_only_array must call model.predict() once for
        2-D feature input (n_samples, n_features).
        """
        horizon = 6
        mock_model = MagicMock()
        mock_model.predict.return_value = np.arange(horizon, dtype=float).reshape(1, -1)

        p = _stub_predictor("xgboost", model=mock_model)
        features = np.random.randn(200, 10)
        result = p._predict_point_only_array(features, horizon=horizon)

        assert mock_model.predict.call_count == 1
        assert result.shape == (horizon,)

    def test_predict_required_keys_present(self):
        """predict() output dict must contain point, lower, upper."""
        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, 24), 50.0)

        p = _stub_predictor("xgboost", model=mock_model)
        df = _make_feature_df()
        result = p.predict(df, horizon=24)

        assert set(result.keys()) == {"point", "lower", "upper"}

    def test_lower_le_upper_mimo(self):
        """Regardless of CI method, lower must never exceed upper."""
        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, 24), 50.0)

        p = _stub_predictor("xgboost", model=mock_model)
        df = _make_feature_df()
        result = p.predict(df, horizon=24)

        assert np.all(result["lower"] <= result["upper"]), (
            "lower > upper detected in prediction output."
        )

    def test_output_arrays_are_numpy(self):
        """All output arrays must be numpy ndarrays."""
        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, 6), 50.0)

        p = _stub_predictor("xgboost", model=mock_model)
        df = _make_feature_df()
        result = p.predict(df, horizon=6)

        for key in ("point", "lower", "upper"):
            assert isinstance(result[key], np.ndarray), f"{key} must be ndarray"


# ===========================================================================
# Task 2.3 — Conformal prediction confidence intervals
# ===========================================================================


class TestConformalPredictionIntervals:
    """Confidence intervals must be empirically grounded, not ±10 % fiction."""

    def test_calibrate_sets_conformal_quantiles(self):
        """After calibrate(), _conformal_quantiles must not be None."""
        horizon = 6
        n_cal = 50

        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), 50.0)

        p = _stub_predictor("xgboost", model=mock_model)
        cal_features = _make_feature_df(n_rows=n_cal)
        cal_actuals = np.random.randn(n_cal, horizon) * 5 + 50

        p.calibrate(cal_features, cal_actuals, horizon=horizon, coverage=0.80)

        assert p._conformal_quantiles is not None, (
            "_conformal_quantiles should be set after calibrate()"
        )

    def test_calibrate_quantiles_shape_is_2_by_horizon(self):
        """Stored quantiles must have shape (2, horizon)."""
        horizon = 12
        n_cal = 30

        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), 55.0)

        p = _stub_predictor("xgboost", model=mock_model)
        cal_feat = _make_feature_df(n_rows=n_cal)
        cal_act = np.random.randn(n_cal, horizon) + 55

        p.calibrate(cal_feat, cal_act, horizon=horizon, coverage=0.80)

        assert p._conformal_quantiles.shape == (2, horizon), (
            f"Expected shape (2, {horizon}), got {p._conformal_quantiles.shape}"
        )

    def test_calibrate_lower_quantile_le_upper_quantile(self):
        """Row 0 (q_lo) must be <= row 1 (q_hi) element-wise."""
        horizon = 6
        n_cal = 100

        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), 50.0)

        p = _stub_predictor("xgboost", model=mock_model)
        cal_feat = _make_feature_df(n_rows=n_cal)
        cal_act = np.random.randn(n_cal, horizon) * 3 + 50

        p.calibrate(cal_feat, cal_act, horizon=horizon, coverage=0.80)

        q_lo = p._conformal_quantiles[0]
        q_hi = p._conformal_quantiles[1]
        assert np.all(q_lo <= q_hi), "Lower quantile exceeds upper quantile."

    def test_calibrate_achieves_target_coverage_on_cal_set(self):
        """
        After calibration the intervals should capture at least the requested
        fraction of calibration points.
        """
        horizon = 1
        n_cal = 500
        coverage = 0.80

        np.random.seed(7)
        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), 50.0)

        p = _stub_predictor("xgboost", model=mock_model)
        cal_feat = _make_feature_df(n_rows=n_cal)
        cal_act = 50.0 + np.random.randn(n_cal, horizon) * 10

        p.calibrate(cal_feat, cal_act, horizon=horizon, coverage=coverage)

        in_interval = 0
        for i in range(n_cal):
            row = cal_feat.iloc[[i]]
            r = p.predict(row, horizon=horizon)
            if r["lower"][0] <= cal_act[i, 0] <= r["upper"][0]:
                in_interval += 1

        empirical_coverage = in_interval / n_cal
        assert empirical_coverage >= coverage - 0.05, (
            f"Conformal coverage {empirical_coverage:.2%} < target {coverage:.0%} - 5pp"
        )

    def test_conformal_intervals_wider_than_fabricated_10pct(self):
        """
        When the model is inaccurate (large residuals), the conformal intervals
        should be wider than the naive ±10 % fabricated interval.
        """
        horizon = 1
        n_cal = 200
        point_val = 50.0

        np.random.seed(99)
        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), point_val)

        p = _stub_predictor("xgboost", model=mock_model)
        cal_feat = _make_feature_df(n_rows=n_cal)
        cal_act = np.random.randn(n_cal, horizon) * 30 + point_val

        p.calibrate(cal_feat, cal_act, horizon=horizon, coverage=0.80)

        test_df = _make_feature_df(n_rows=5)
        result = p.predict(test_df, horizon=horizon)
        conformal_width = float(result["upper"][0] - result["lower"][0])

        # Fabricated ±10 % width = 2 * 1.645 * 0.1 * 50 = 16.45
        fabricated_width = 2 * 1.645 * 0.10 * point_val
        assert conformal_width > fabricated_width, (
            f"Conformal width {conformal_width:.2f} should exceed "
            f"fabricated ±10% width {fabricated_width:.2f} given large residuals."
        )

    def test_conformal_intervals_narrower_when_model_accurate(self):
        """
        When the model is very accurate (tiny residuals), the conformal
        intervals should be narrow.
        """
        horizon = 1
        n_cal = 200
        point_val = 50.0

        np.random.seed(3)
        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), point_val)

        p = _stub_predictor("xgboost", model=mock_model)
        cal_feat = _make_feature_df(n_rows=n_cal)
        cal_act = np.random.randn(n_cal, horizon) * 0.1 + point_val

        p.calibrate(cal_feat, cal_act, horizon=horizon, coverage=0.80)

        test_df = _make_feature_df(n_rows=5)
        result = p.predict(test_df, horizon=horizon)
        conformal_width = float(result["upper"][0] - result["lower"][0])

        # Width should be much less than 1 (residuals ~ 0.1)
        assert conformal_width < 2.0, (
            f"Conformal width {conformal_width:.3f} too wide for near-zero residuals."
        )

    def test_fallback_warns_when_not_calibrated(self, caplog):
        """Without calibration, a warning must be emitted."""
        import logging

        horizon = 6
        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), 50.0)

        p = _stub_predictor("xgboost", model=mock_model)
        p._conformal_quantiles = None  # explicitly uncalibrated

        df = _make_feature_df()
        with caplog.at_level(logging.WARNING, logger="ml.inference.predictor"):
            p.predict(df, horizon=horizon)

        warning_messages = [r.message for r in caplog.records]
        assert any("conformal_not_calibrated" in msg for msg in warning_messages), (
            "Expected 'conformal_not_calibrated' warning when calibrate() "
            "has not been called. Warnings found: " + str(warning_messages)
        )

    def test_fallback_lower_le_upper_always(self):
        """Fallback Gaussian intervals must still satisfy lower <= upper."""
        horizon = 24
        mock_model = MagicMock()
        mock_model.predict.return_value = np.linspace(10, 100, horizon).reshape(1, -1)

        p = _stub_predictor("xgboost", model=mock_model)
        df = _make_feature_df()
        result = p.predict(df, horizon=horizon)

        assert np.all(result["lower"] <= result["upper"])

    def test_calibrate_with_ndarray_2d_input(self):
        """calibrate() must work when cal_features is a 2-D ndarray."""
        horizon = 4
        n_cal = 40

        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), 50.0)

        p = _stub_predictor("xgboost", model=mock_model)
        cal_features = np.random.randn(n_cal, 10)
        cal_actuals = np.random.randn(n_cal, horizon) + 50

        p.calibrate(cal_features, cal_actuals, horizon=horizon, coverage=0.80)

        assert p._conformal_quantiles is not None
        assert p._conformal_quantiles.shape == (2, horizon)

    def test_calibrate_with_3d_ndarray_input(self):
        """calibrate() must work when cal_features is a 3-D ndarray (sequences)."""
        horizon = 4
        n_cal = 20
        seq_len = 10
        n_feats = 5

        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), 50.0)

        p = _stub_predictor("xgboost", model=mock_model)
        cal_features = np.random.randn(n_cal, seq_len, n_feats)
        cal_actuals = np.random.randn(n_cal, horizon) + 50

        p.calibrate(cal_features, cal_actuals, horizon=horizon, coverage=0.80)

        assert p._conformal_quantiles is not None
        assert p._conformal_quantiles.shape == (2, horizon)

    def test_calibrate_mismatched_actuals_raises(self):
        """Mismatched calibration actuals shape must raise ValueError."""
        horizon = 4
        n_cal = 20

        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), 50.0)

        p = _stub_predictor("xgboost", model=mock_model)
        cal_features = _make_feature_df(n_rows=n_cal)
        wrong_actuals = np.random.randn(n_cal, horizon + 5)

        with pytest.raises(ValueError, match="does not match"):
            p.calibrate(cal_features, wrong_actuals, horizon=horizon)

    def test_predict_uses_conformal_not_10pct_after_calibration(self):
        """
        After calibration with near-zero residuals, the interval width must
        not equal the ±10 % fabricated formula result.
        """
        horizon = 6
        n_cal = 100
        point_val = 80.0

        np.random.seed(55)
        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), point_val)

        p = _stub_predictor("xgboost", model=mock_model)
        cal_feat = _make_feature_df(n_rows=n_cal)
        cal_act = np.random.randn(n_cal, horizon) * 0.2 + point_val
        p.calibrate(cal_feat, cal_act, horizon=horizon, coverage=0.80)

        test_df = _make_feature_df(n_rows=5)
        result = p.predict(test_df, horizon=horizon)
        ci_width = float(result["upper"][0] - result["lower"][0])

        fabricated_half = 1.645 * 0.10 * point_val
        fabricated_width = 2 * fabricated_half

        assert abs(ci_width - fabricated_width) > 1.0, (
            f"Interval width {ci_width:.3f} looks like the fabricated ±10% formula "
            f"({fabricated_width:.3f}). Conformal intervals should differ."
        )

    def test_conformal_intervals_per_horizon_step_heteroscedastic(self):
        """
        Conformal intervals should be per-horizon-step.  When residuals are
        heteroscedastic (narrow at step 0, wide at step 5), the intervals
        must reflect that.
        """
        horizon = 6
        n_cal = 300
        point_val = 50.0

        np.random.seed(11)
        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), point_val)

        p = _stub_predictor("xgboost", model=mock_model)
        cal_feat = _make_feature_df(n_rows=n_cal)

        residual_stds = np.array([0.1, 2.0, 5.0, 8.0, 12.0, 20.0])
        cal_act = np.column_stack(
            [np.random.randn(n_cal) * std + point_val for std in residual_stds]
        )

        p.calibrate(cal_feat, cal_act, horizon=horizon, coverage=0.80)

        test_df = _make_feature_df(n_rows=5)
        result = p.predict(test_df, horizon=horizon)

        width_0 = result["upper"][0] - result["lower"][0]
        width_5 = result["upper"][5] - result["lower"][5]
        assert width_0 < width_5, (
            f"Per-horizon intervals not heteroscedastic: "
            f"width[0]={width_0:.2f} should be < width[5]={width_5:.2f}"
        )

    def test_different_coverage_levels_give_different_widths(self):
        """80 % coverage must produce narrower intervals than 95 % coverage."""
        horizon = 6
        n_cal = 200
        point_val = 50.0

        np.random.seed(77)
        mock_model = MagicMock()
        mock_model.predict.return_value = np.full((1, horizon), point_val)

        p80 = _stub_predictor(
            "xgboost",
            model=MagicMock(
                predict=MagicMock(return_value=np.full((1, horizon), point_val))
            ),
        )
        p95 = _stub_predictor(
            "xgboost",
            model=MagicMock(
                predict=MagicMock(return_value=np.full((1, horizon), point_val))
            ),
        )

        cal_feat = _make_feature_df(n_rows=n_cal)
        cal_act = np.random.randn(n_cal, horizon) * 5 + point_val

        p80.calibrate(cal_feat, cal_act, horizon=horizon, coverage=0.80)
        p95.calibrate(cal_feat, cal_act, horizon=horizon, coverage=0.95)

        test_df = _make_feature_df(n_rows=5)
        r80 = p80.predict(test_df, horizon=horizon)
        r95 = p95.predict(test_df, horizon=horizon)

        w80 = np.mean(r80["upper"] - r80["lower"])
        w95 = np.mean(r95["upper"] - r95["lower"])

        assert w80 < w95, (
            f"80% coverage width {w80:.3f} should be narrower than "
            f"95% coverage width {w95:.3f}."
        )


# ===========================================================================
# Integration: all three fixes working together
# ===========================================================================


class TestIntegration:
    """End-to-end smoke test exercising all three fixes together."""

    def test_full_pipeline_no_leakage_mimo_conformal(self):
        """
        Smoke test: prepare_features + split_data + calibrate + predict,
        verifying:
          1. Scaler was fitted on training data only (leakage fix).
          2. model.predict() called once per inference (MIMO fix).
          3. Conformal quantiles are set and intervals are non-trivial.
        """
        horizon = 6

        trainer, df = _make_trainer_with_real_feature_engine(n_hours=500)
        X, y = trainer.prepare_features(df)
        (X_tr, y_tr), (X_v, y_v), (X_te, y_te) = trainer.split_data(X, y)

        assert len(X_tr) > 0
        assert len(X_te) > 0

        # Set up a MIMO mock predictor
        mock_model_fn = MagicMock(
            predict=MagicMock(return_value=np.random.randn(1, horizon) + 50.0)
        )
        p = _stub_predictor("xgboost", model=mock_model_fn)

        # Calibrate on validation sequences (3-D ndarray)
        n_cal = min(len(X_v), 20) if len(X_v) > 0 else 0
        if n_cal > 5:
            cal_feat_arr = X_v[:n_cal]
            cal_act = y_v[:n_cal, :horizon]
            # Reshape 3-D to 2-D for calibrate since _predict_point_only_array
            # is called per sample; model returns scalar batch
            p.calibrate(cal_feat_arr, cal_act, horizon=horizon, coverage=0.80)
            assert p._conformal_quantiles is not None

        # Inference — model.predict called once (MIMO)
        test_df = _make_feature_df(n_rows=50)
        mock_model_fn.predict.reset_mock()
        result = p.predict(test_df, horizon=horizon)

        assert mock_model_fn.predict.call_count == 1, (
            "MIMO: model.predict() must be called once per inference."
        )
        assert result["point"].shape == (horizon,)
        assert np.all(result["lower"] <= result["upper"])
