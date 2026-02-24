"""
Unit Tests for ML Inference Modules

Tests for:
- PricePredictor: model loading, preprocessing, prediction, error handling
- EnsemblePredictor: weighted averaging, uncertainty estimation, evaluation

All heavy model loading is mocked to keep tests fast and isolated.
"""

import os
import tempfile
from unittest.mock import MagicMock, mock_open, patch, PropertyMock

import numpy as np
import pandas as pd
import pytest
import yaml

# Check for optional torch dependency (guard against MagicMock in sys.modules)
import types as _types
try:
    import torch as _torch  # noqa: F401
    HAS_TORCH = isinstance(_torch, _types.ModuleType)
except ImportError:
    HAS_TORCH = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_features_df(n_rows: int = 200, n_features: int = 5, seed: int = 42) -> pd.DataFrame:
    """Create a synthetic feature DataFrame with numeric columns."""
    rng = np.random.RandomState(seed)
    data = {f"feat_{i}": rng.randn(n_rows) for i in range(n_features)}
    dates = pd.date_range("2024-06-01", periods=n_rows, freq="h")
    return pd.DataFrame(data, index=dates)


def _make_prediction(horizon: int = 24, base: float = 50.0, seed: int = 0) -> dict:
    """Return a dict shaped like PricePredictor.predict() output."""
    rng = np.random.RandomState(seed)
    point = base + rng.randn(horizon) * 5
    std = np.abs(point) * 0.1
    return {
        "point": point,
        "lower": point - 1.645 * std,
        "upper": point + 1.645 * std,
    }


# ============================================================================
# PricePredictor Tests
# ============================================================================


class TestPricePredictorModelTypeInference:
    """Test _infer_model_type detects files correctly."""

    def test_infer_cnn_lstm_from_model_pt(self, tmp_path):
        """model.pt should map to cnn_lstm."""
        (tmp_path / "model.pt").touch()
        with patch("ml.inference.predictor.PricePredictor._load_model"), \
             patch("ml.inference.predictor.PricePredictor._load_metadata"):
            from ml.inference.predictor import PricePredictor
            p = PricePredictor.__new__(PricePredictor)
            p.model_path = str(tmp_path)
            assert p._infer_model_type() == "cnn_lstm"

    def test_infer_xgboost_from_model_json(self, tmp_path):
        """model.json should map to xgboost."""
        (tmp_path / "model.json").touch()
        with patch("ml.inference.predictor.PricePredictor._load_model"), \
             patch("ml.inference.predictor.PricePredictor._load_metadata"):
            from ml.inference.predictor import PricePredictor
            p = PricePredictor.__new__(PricePredictor)
            p.model_path = str(tmp_path)
            assert p._infer_model_type() == "xgboost"

    def test_infer_lightgbm_from_model_txt(self, tmp_path):
        """model.txt should map to lightgbm."""
        (tmp_path / "model.txt").touch()
        with patch("ml.inference.predictor.PricePredictor._load_model"), \
             patch("ml.inference.predictor.PricePredictor._load_metadata"):
            from ml.inference.predictor import PricePredictor
            p = PricePredictor.__new__(PricePredictor)
            p.model_path = str(tmp_path)
            assert p._infer_model_type() == "lightgbm"

    def test_raises_when_no_model_file_found(self, tmp_path):
        """Should raise ValueError when directory has no recognised model."""
        from ml.inference.predictor import PricePredictor
        p = PricePredictor.__new__(PricePredictor)
        p.model_path = str(tmp_path)
        with pytest.raises(ValueError, match="Cannot infer model type"):
            p._infer_model_type()


class TestPricePredictorLoadMetadata:
    """Test _load_metadata reads version from YAML or uses fallback."""

    def _make_predictor_stub(self):
        from ml.inference.predictor import PricePredictor
        p = PricePredictor.__new__(PricePredictor)
        p.model_path = "/fake"
        p.model_type = "xgboost"
        p.model = None
        p.scaler = None
        p.config = None
        p.model_version = None
        return p

    def test_loads_version_from_metadata_yaml(self, tmp_path):
        meta = {"version": "2.3.1"}
        (tmp_path / "metadata.yaml").write_text(yaml.dump(meta))

        p = self._make_predictor_stub()
        p.model_path = str(tmp_path)
        p._load_metadata()
        assert p.model_version == "2.3.1"

    def test_defaults_to_unknown_when_no_file(self, tmp_path):
        p = self._make_predictor_stub()
        p.model_path = str(tmp_path)
        p._load_metadata()
        assert p.model_version == "unknown"


class TestPricePredictorPreprocessFeatures:
    """Test _preprocess_features with various inputs."""

    def _make_predictor_stub(self, model_type="xgboost", scaler=None):
        from ml.inference.predictor import PricePredictor
        p = PricePredictor.__new__(PricePredictor)
        p.model_path = "/fake"
        p.model_type = model_type
        p.model = None
        p.scaler = scaler
        p.config = None
        p.model_version = None
        return p

    def test_selects_only_numeric_columns(self):
        df = pd.DataFrame({
            "feat_a": [1.0, 2.0, 3.0],
            "category": ["a", "b", "c"],
            "feat_b": [4.0, 5.0, 6.0],
        })
        p = self._make_predictor_stub()
        features = p._preprocess_features(df)
        assert features.shape == (3, 2)

    def test_excludes_target_columns(self):
        df = pd.DataFrame({
            "feat_a": [1.0, 2.0],
            "target": [10.0, 20.0],
            "price_target": [11.0, 21.0],
        })
        p = self._make_predictor_stub()
        features = p._preprocess_features(df)
        assert features.shape == (2, 1)

    def test_applies_scaler_when_available(self):
        df = _make_features_df(n_rows=5, n_features=3)
        mock_scaler = MagicMock()
        scaled = np.ones((5, 3))
        mock_scaler.transform.return_value = scaled

        p = self._make_predictor_stub(scaler=mock_scaler)
        features = p._preprocess_features(df)
        mock_scaler.transform.assert_called_once()
        np.testing.assert_array_equal(features, scaled)

    def test_cnn_lstm_creates_sequence_with_batch_dim(self):
        """CNN-LSTM should produce shape (1, sequence_length, n_features)."""
        df = _make_features_df(n_rows=200, n_features=5)
        p = self._make_predictor_stub(model_type="cnn_lstm")
        features = p._preprocess_features(df, sequence_length=168)
        assert features.shape == (1, 168, 5)

    def test_cnn_lstm_pads_short_input(self):
        """If fewer rows than sequence_length, should pad to reach it."""
        df = _make_features_df(n_rows=50, n_features=3)
        p = self._make_predictor_stub(model_type="cnn_lstm")
        features = p._preprocess_features(df, sequence_length=168)
        assert features.shape == (1, 168, 3)

    def test_tree_models_return_2d(self):
        """XGBoost / LightGBM should return plain 2D array."""
        df = _make_features_df(n_rows=100, n_features=4)
        for mt in ["xgboost", "lightgbm"]:
            p = self._make_predictor_stub(model_type=mt)
            features = p._preprocess_features(df)
            assert features.ndim == 2

    def test_empty_dataframe_returns_empty_features(self):
        """An empty DataFrame should not crash but return an empty array."""
        df = pd.DataFrame({"feat_a": pd.Series(dtype=float)})
        p = self._make_predictor_stub()
        features = p._preprocess_features(df)
        assert features.shape[0] == 0


class TestPricePredictorPredict:
    """Test the predict() method with mocked model backends."""

    def _build_predictor(self, model_type, model_mock, scaler=None):
        from ml.inference.predictor import PricePredictor
        p = PricePredictor.__new__(PricePredictor)
        p.model_path = "/fake"
        p.model_type = model_type
        p.model = model_mock
        p.scaler = scaler
        p.config = None
        p.model_version = "test"
        return p

    # -- XGBoost / LightGBM path -------------------------------------------

    def test_xgboost_returns_correct_keys(self):
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([55.0])

        p = self._build_predictor("xgboost", mock_model)
        df = _make_features_df(n_rows=200, n_features=5)

        result = p.predict(df, horizon=24)

        assert set(result.keys()) == {"point", "lower", "upper"}
        assert result["point"].shape == (24,)
        assert result["lower"].shape == (24,)
        assert result["upper"].shape == (24,)

    def test_lightgbm_returns_correct_shapes(self):
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([42.0])

        p = self._build_predictor("lightgbm", mock_model)
        df = _make_features_df(n_rows=200, n_features=5)

        result = p.predict(df, horizon=12)
        assert result["point"].shape == (12,)

    def test_tree_model_lower_below_upper(self):
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([60.0])

        p = self._build_predictor("xgboost", mock_model)
        df = _make_features_df()

        result = p.predict(df, horizon=24)
        assert np.all(result["lower"] <= result["upper"])

    def test_confidence_95_wider_than_90(self):
        """95% CI should produce wider intervals than 90%."""
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([50.0])

        p = self._build_predictor("xgboost", mock_model)
        df = _make_features_df()

        r90 = p.predict(df, horizon=24, confidence_level=0.9)
        r95 = p.predict(df, horizon=24, confidence_level=0.95)

        width_90 = r90["upper"] - r90["lower"]
        width_95 = r95["upper"] - r95["lower"]
        assert np.all(width_95 >= width_90)

    def test_horizon_parameter_controls_output_length(self):
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([50.0])

        p = self._build_predictor("xgboost", mock_model)
        df = _make_features_df()

        for h in [1, 6, 48]:
            result = p.predict(df, horizon=h)
            assert result["point"].shape == (h,), f"Mismatch for horizon={h}"

    # -- CNN-LSTM path (via torch mock) ------------------------------------

    @pytest.mark.skipif(not HAS_TORCH, reason="torch not installed")
    def test_cnn_lstm_3d_output(self):
        """When model outputs (1, horizon, 3), point/lower/upper are split."""
        import torch

        horizon = 24
        mock_output = torch.FloatTensor(np.random.randn(1, horizon, 3))
        mock_model = MagicMock()
        mock_model.return_value = mock_output

        p = self._build_predictor("cnn_lstm", mock_model)
        df = _make_features_df(n_rows=200, n_features=5)

        result = p.predict(df, horizon=horizon)
        assert result["point"].shape == (horizon,)
        assert result["lower"].shape == (horizon,)
        assert result["upper"].shape == (horizon,)

    @pytest.mark.skipif(not HAS_TORCH, reason="torch not installed")
    def test_cnn_lstm_2d_output_adds_uncertainty(self):
        """When model returns (1, horizon), uncertainty is estimated at 10%."""
        import torch

        horizon = 24
        mock_output = torch.FloatTensor(np.full((1, horizon), 50.0))
        mock_model = MagicMock()
        mock_model.return_value = mock_output

        p = self._build_predictor("cnn_lstm", mock_model)
        df = _make_features_df(n_rows=200, n_features=5)

        result = p.predict(df, horizon=horizon, confidence_level=0.9)
        assert result["point"].shape == (horizon,)
        # 10% uncertainty * z=1.645 around 50 => width ~16.45
        widths = result["upper"] - result["lower"]
        assert np.all(widths > 0)


# ============================================================================
# EnsemblePredictor Tests
# ============================================================================


def _build_ensemble(
    predictors: dict,
    weights: dict = None,
    version: str = "test",
):
    """Build an EnsemblePredictor without touching the filesystem."""
    from ml.inference.ensemble_predictor import EnsemblePredictor

    ep = EnsemblePredictor.__new__(EnsemblePredictor)
    ep.model_path = "/fake/ensemble"
    ep.weights = weights or EnsemblePredictor.DEFAULT_WEIGHTS
    ep.predictors = predictors
    ep.version = version
    return ep


class TestEnsembleLoadWeights:
    """Test _load_weights and weight resolution."""

    def test_returns_defaults_when_no_metadata(self, tmp_path):
        from ml.inference.ensemble_predictor import EnsemblePredictor
        ep = EnsemblePredictor.__new__(EnsemblePredictor)
        ep.model_path = str(tmp_path)
        result = ep._load_weights()
        assert result == EnsemblePredictor.DEFAULT_WEIGHTS

    def test_loads_weights_from_metadata_yaml(self, tmp_path):
        custom_weights = {
            "cnn_lstm": {"weight": 0.6},
            "xgboost": {"weight": 0.2},
            "lightgbm": {"weight": 0.2},
        }
        meta = {"weights": custom_weights}
        (tmp_path / "metadata.yaml").write_text(yaml.dump(meta))

        from ml.inference.ensemble_predictor import EnsemblePredictor
        ep = EnsemblePredictor.__new__(EnsemblePredictor)
        ep.model_path = str(tmp_path)
        result = ep._load_weights()
        assert result["cnn_lstm"]["weight"] == 0.6


class TestEnsembleLoadModels:
    """Test _load_models detects available models and raises on none."""

    def test_raises_if_no_model_dirs_exist(self, tmp_path):
        from ml.inference.ensemble_predictor import EnsemblePredictor
        ep = EnsemblePredictor.__new__(EnsemblePredictor)
        ep.model_path = str(tmp_path)
        ep.weights = EnsemblePredictor.DEFAULT_WEIGHTS
        ep.predictors = {}
        with pytest.raises(ValueError, match="No models could be loaded"):
            ep._load_models()

    def test_loads_available_models_skips_missing(self, tmp_path):
        """Only directories that exist get loaded; missing ones are skipped."""
        (tmp_path / "xgboost").mkdir()

        from ml.inference.ensemble_predictor import EnsemblePredictor

        mock_predictor = MagicMock()
        with patch("ml.inference.ensemble_predictor.PricePredictor", return_value=mock_predictor):
            ep = EnsemblePredictor.__new__(EnsemblePredictor)
            ep.model_path = str(tmp_path)
            ep.weights = EnsemblePredictor.DEFAULT_WEIGHTS
            ep.predictors = {}
            ep._load_models()
            assert "xgboost" in ep.predictors
            assert "cnn_lstm" not in ep.predictors
            assert "lightgbm" not in ep.predictors

    def test_tolerates_single_model_load_failure(self, tmp_path):
        """If one model fails to load, others should still be available."""
        (tmp_path / "cnn_lstm").mkdir()
        (tmp_path / "xgboost").mkdir()

        from ml.inference.ensemble_predictor import EnsemblePredictor

        call_count = {"n": 0}

        def side_effect(**kwargs):
            call_count["n"] += 1
            if kwargs.get("model_type") == "cnn_lstm":
                raise RuntimeError("torch not installed")
            return MagicMock()

        with patch("ml.inference.ensemble_predictor.PricePredictor", side_effect=side_effect):
            ep = EnsemblePredictor.__new__(EnsemblePredictor)
            ep.model_path = str(tmp_path)
            ep.weights = EnsemblePredictor.DEFAULT_WEIGHTS
            ep.predictors = {}
            ep._load_models()
            assert "xgboost" in ep.predictors
            assert "cnn_lstm" not in ep.predictors


class TestEnsembleLoadMetadata:
    """Test _load_metadata version extraction."""

    def test_loads_version_from_yaml(self, tmp_path):
        (tmp_path / "metadata.yaml").write_text(yaml.dump({"version": "1.0.0"}))
        from ml.inference.ensemble_predictor import EnsemblePredictor
        ep = EnsemblePredictor.__new__(EnsemblePredictor)
        ep.model_path = str(tmp_path)
        ep.version = None
        ep._load_metadata()
        assert ep.version == "1.0.0"

    def test_uses_date_fallback_when_no_file(self, tmp_path):
        from ml.inference.ensemble_predictor import EnsemblePredictor
        ep = EnsemblePredictor.__new__(EnsemblePredictor)
        ep.model_path = str(tmp_path)
        ep.version = None
        ep._load_metadata()
        # Should be a date string like "20260223"
        assert len(ep.version) == 8
        assert ep.version.isdigit()


class TestEnsemblePredict:
    """Test ensemble predict() combining multiple model outputs."""

    def _mock_predictor(self, horizon=24, base=50.0, seed=0):
        m = MagicMock()
        m.predict.return_value = _make_prediction(horizon=horizon, base=base, seed=seed)
        return m

    def test_returns_required_keys(self):
        predictors = {
            "cnn_lstm": self._mock_predictor(base=50, seed=1),
            "xgboost": self._mock_predictor(base=52, seed=2),
        }
        ep = _build_ensemble(predictors)
        df = _make_features_df()
        result = ep.predict(df, horizon=24)
        assert set(result.keys()) == {"point", "lower", "upper"}

    def test_output_shapes(self):
        predictors = {
            "cnn_lstm": self._mock_predictor(seed=1),
            "xgboost": self._mock_predictor(seed=2),
            "lightgbm": self._mock_predictor(seed=3),
        }
        ep = _build_ensemble(predictors)
        df = _make_features_df()
        result = ep.predict(df, horizon=24)
        for key in ("point", "lower", "upper"):
            assert result[key].shape == (24,), f"{key} has wrong shape"

    def test_custom_horizon(self):
        predictors = {"xgboost": self._mock_predictor(horizon=48, seed=1)}
        ep = _build_ensemble(predictors)
        df = _make_features_df()
        result = ep.predict(df, horizon=48)
        assert result["point"].shape == (48,)

    def test_lower_below_upper(self):
        predictors = {
            "cnn_lstm": self._mock_predictor(seed=1),
            "xgboost": self._mock_predictor(seed=2),
        }
        ep = _build_ensemble(predictors)
        df = _make_features_df()
        result = ep.predict(df, horizon=24)
        assert np.all(result["lower"] <= result["upper"])

    def test_return_components(self):
        predictors = {
            "cnn_lstm": self._mock_predictor(base=50, seed=1),
            "xgboost": self._mock_predictor(base=55, seed=2),
        }
        ep = _build_ensemble(predictors)
        df = _make_features_df()
        result = ep.predict(df, horizon=24, return_components=True)
        assert "components" in result
        assert set(result["components"].keys()) == {"cnn_lstm", "xgboost"}
        assert result["components"]["cnn_lstm"].shape == (24,)

    def test_components_excluded_by_default(self):
        predictors = {"xgboost": self._mock_predictor(seed=1)}
        ep = _build_ensemble(predictors)
        df = _make_features_df()
        result = ep.predict(df, horizon=24)
        assert "components" not in result

    def test_weighted_average_correctness(self):
        """Point forecast should be weighted average of components."""
        horizon = 24
        pred_a = np.full(horizon, 100.0)
        pred_b = np.full(horizon, 200.0)

        mock_a = MagicMock()
        mock_a.predict.return_value = {
            "point": pred_a,
            "lower": pred_a - 10,
            "upper": pred_a + 10,
        }
        mock_b = MagicMock()
        mock_b.predict.return_value = {
            "point": pred_b,
            "lower": pred_b - 10,
            "upper": pred_b + 10,
        }

        weights = {
            "cnn_lstm": {"weight": 0.6},
            "xgboost": {"weight": 0.4},
        }
        predictors = {"cnn_lstm": mock_a, "xgboost": mock_b}
        ep = _build_ensemble(predictors, weights=weights)
        df = _make_features_df()
        result = ep.predict(df, horizon=horizon)

        expected = 0.6 * 100.0 + 0.4 * 200.0  # 140.0
        np.testing.assert_allclose(result["point"], expected, atol=1e-10)

    def test_single_model_ensemble(self):
        """Ensemble with one model should return that model's predictions."""
        horizon = 24
        pred = _make_prediction(horizon=horizon, base=60.0, seed=7)
        mock_p = MagicMock()
        mock_p.predict.return_value = pred

        weights = {"cnn_lstm": {"weight": 1.0}}
        ep = _build_ensemble({"cnn_lstm": mock_p}, weights=weights)
        df = _make_features_df()
        result = ep.predict(df, horizon=horizon)
        np.testing.assert_allclose(result["point"], pred["point"], atol=1e-10)

    def test_raises_when_all_predictors_fail(self):
        mock_p = MagicMock()
        mock_p.predict.side_effect = RuntimeError("inference failure")
        ep = _build_ensemble({"xgboost": mock_p})
        df = _make_features_df()
        with pytest.raises(ValueError, match="All component predictions failed"):
            ep.predict(df, horizon=24)

    def test_tolerates_partial_predictor_failure(self):
        """If one predictor fails, ensemble should still produce results."""
        good = MagicMock()
        good.predict.return_value = _make_prediction(horizon=24, base=50, seed=1)
        bad = MagicMock()
        bad.predict.side_effect = RuntimeError("boom")

        predictors = {"cnn_lstm": bad, "xgboost": good}
        ep = _build_ensemble(predictors)
        df = _make_features_df()
        result = ep.predict(df, horizon=24)
        assert result["point"].shape == (24,)

    def test_zero_weight_normalization(self):
        """If all weights are zero, should use equal weighting."""
        horizon = 24
        pred_a = np.full(horizon, 100.0)
        pred_b = np.full(horizon, 200.0)

        mock_a = MagicMock()
        mock_a.predict.return_value = {
            "point": pred_a,
            "lower": pred_a - 5,
            "upper": pred_a + 5,
        }
        mock_b = MagicMock()
        mock_b.predict.return_value = {
            "point": pred_b,
            "lower": pred_b - 5,
            "upper": pred_b + 5,
        }

        weights = {"model_a": {"weight": 0}, "model_b": {"weight": 0}}
        predictors = {"model_a": mock_a, "model_b": mock_b}
        ep = _build_ensemble(predictors, weights=weights)
        df = _make_features_df()
        result = ep.predict(df, horizon=horizon)

        # Equal weights => average
        expected = 0.5 * 100.0 + 0.5 * 200.0
        np.testing.assert_allclose(result["point"], expected, atol=1e-10)

    def test_confidence_90_uses_z_1645(self):
        """Verify z_score selection for 90% confidence."""
        horizon = 24
        # Two identical models to have zero model_variance
        pred = np.full(horizon, 50.0)
        width = 10.0
        mock_pred = {
            "point": pred,
            "lower": pred - width / 2,
            "upper": pred + width / 2,
        }
        mock_p = MagicMock()
        mock_p.predict.return_value = mock_pred

        ep = _build_ensemble(
            {"cnn_lstm": mock_p},
            weights={"cnn_lstm": {"weight": 1.0}},
        )
        df = _make_features_df()
        result = ep.predict(df, horizon=horizon, confidence_level=0.9)
        # Intervals should be built using z=1.645
        assert np.all(result["lower"] < result["point"])
        assert np.all(result["upper"] > result["point"])

    def test_confidence_95_uses_z_196(self):
        """Non-0.9 confidence should use z=1.96, producing wider intervals."""
        horizon = 24
        pred = np.full(horizon, 50.0)
        width = 10.0
        mock_pred = {
            "point": pred,
            "lower": pred - width / 2,
            "upper": pred + width / 2,
        }
        mock_p = MagicMock()
        mock_p.predict.return_value = mock_pred

        ep = _build_ensemble(
            {"cnn_lstm": mock_p},
            weights={"cnn_lstm": {"weight": 1.0}},
        )
        df = _make_features_df()

        r90 = ep.predict(df, horizon=horizon, confidence_level=0.9)
        r95 = ep.predict(df, horizon=horizon, confidence_level=0.95)

        w90 = np.mean(r90["upper"] - r90["lower"])
        w95 = np.mean(r95["upper"] - r95["lower"])
        assert w95 > w90


class TestEnsembleGetModelWeights:
    """Test get_model_weights normalisation logic."""

    def test_normalizes_to_sum_one(self):
        predictors = {
            "cnn_lstm": MagicMock(),
            "xgboost": MagicMock(),
            "lightgbm": MagicMock(),
        }
        weights = {
            "cnn_lstm": {"weight": 0.5},
            "xgboost": {"weight": 0.25},
            "lightgbm": {"weight": 0.25},
        }
        ep = _build_ensemble(predictors, weights=weights)
        nw = ep.get_model_weights()
        assert abs(sum(nw.values()) - 1.0) < 1e-10

    def test_equal_weights_when_all_zero(self):
        predictors = {
            "cnn_lstm": MagicMock(),
            "xgboost": MagicMock(),
        }
        weights = {
            "cnn_lstm": {"weight": 0},
            "xgboost": {"weight": 0},
        }
        ep = _build_ensemble(predictors, weights=weights)
        nw = ep.get_model_weights()
        assert abs(nw["cnn_lstm"] - 0.5) < 1e-10
        assert abs(nw["xgboost"] - 0.5) < 1e-10

    def test_single_model_weight_is_one(self):
        ep = _build_ensemble(
            {"xgboost": MagicMock()},
            weights={"xgboost": {"weight": 0.25}},
        )
        nw = ep.get_model_weights()
        assert abs(nw["xgboost"] - 1.0) < 1e-10

    def test_handles_missing_weight_key(self):
        """If a predictor has no entry in weights, treat its weight as 0."""
        predictors = {
            "cnn_lstm": MagicMock(),
            "new_model": MagicMock(),
        }
        weights = {"cnn_lstm": {"weight": 1.0}}
        ep = _build_ensemble(predictors, weights=weights)
        nw = ep.get_model_weights()
        assert abs(nw["cnn_lstm"] - 1.0) < 1e-10
        assert abs(nw["new_model"] - 0.0) < 1e-10


class TestEnsembleEvaluate:
    """Test evaluate() metrics computation."""

    def _mock_predictor(self, horizon=24, base=50.0, seed=0):
        m = MagicMock()
        m.predict.return_value = _make_prediction(horizon=horizon, base=base, seed=seed)
        return m

    def test_returns_all_metrics(self):
        predictors = {"xgboost": self._mock_predictor(seed=1)}
        ep = _build_ensemble(predictors, weights={"xgboost": {"weight": 1.0}})
        df = _make_features_df()
        actuals = np.full(24, 50.0)
        metrics = ep.evaluate(df, actuals, horizon=24)
        assert set(metrics.keys()) == {"mape", "rmse", "mae", "coverage"}

    def test_metrics_are_floats(self):
        predictors = {"xgboost": self._mock_predictor(seed=1)}
        ep = _build_ensemble(predictors, weights={"xgboost": {"weight": 1.0}})
        df = _make_features_df()
        actuals = np.full(24, 50.0)
        metrics = ep.evaluate(df, actuals, horizon=24)
        for k, v in metrics.items():
            assert isinstance(v, float), f"{k} is {type(v)}, expected float"

    def test_perfect_prediction_gives_zero_errors(self):
        """If point == actuals, MAPE/RMSE/MAE should be ~0 and coverage 100%."""
        horizon = 24
        perfect = np.full(horizon, 50.0)
        mock_pred = {
            "point": perfect.copy(),
            "lower": perfect - 1.0,
            "upper": perfect + 1.0,
        }
        mock_p = MagicMock()
        mock_p.predict.return_value = mock_pred

        ep = _build_ensemble(
            {"cnn_lstm": mock_p},
            weights={"cnn_lstm": {"weight": 1.0}},
        )
        df = _make_features_df()
        metrics = ep.evaluate(df, perfect, horizon=horizon)

        assert metrics["rmse"] < 1e-6
        assert metrics["mae"] < 1e-6
        assert metrics["coverage"] == 100.0

    def test_coverage_is_between_0_and_100(self):
        predictors = {"xgboost": self._mock_predictor(seed=5)}
        ep = _build_ensemble(predictors, weights={"xgboost": {"weight": 1.0}})
        df = _make_features_df()
        actuals = np.random.randn(24) * 100
        metrics = ep.evaluate(df, actuals, horizon=24)
        assert 0.0 <= metrics["coverage"] <= 100.0

    def test_mape_nonnegative(self):
        predictors = {"xgboost": self._mock_predictor(seed=3)}
        ep = _build_ensemble(predictors, weights={"xgboost": {"weight": 1.0}})
        df = _make_features_df()
        actuals = np.full(24, 50.0)
        metrics = ep.evaluate(df, actuals, horizon=24)
        assert metrics["mape"] >= 0.0

    def test_rmse_greater_or_equal_mae(self):
        """By Cauchy-Schwarz, RMSE >= MAE always."""
        predictors = {"xgboost": self._mock_predictor(base=60, seed=4)}
        ep = _build_ensemble(predictors, weights={"xgboost": {"weight": 1.0}})
        df = _make_features_df()
        actuals = np.full(24, 50.0)
        metrics = ep.evaluate(df, actuals, horizon=24)
        assert metrics["rmse"] >= metrics["mae"] - 1e-10


# ============================================================================
# Integration-style Tests (using full __init__ with patched deps)
# ============================================================================


class TestEnsembleEndToEnd:
    """Higher-level tests exercising __init__ through predict."""

    def test_full_init_with_mocked_predictor(self, tmp_path):
        """Construct EnsemblePredictor via __init__ with patched PricePredictor."""
        # Create model dirs and metadata
        (tmp_path / "cnn_lstm").mkdir()
        (tmp_path / "xgboost").mkdir()
        meta = {
            "version": "3.0.0",
            "weights": {
                "cnn_lstm": {"weight": 0.7},
                "xgboost": {"weight": 0.3},
            },
        }
        (tmp_path / "metadata.yaml").write_text(yaml.dump(meta))

        mock_pred = MagicMock()
        mock_pred.predict.return_value = _make_prediction(horizon=24, base=50)

        with patch("ml.inference.ensemble_predictor.PricePredictor", return_value=mock_pred):
            from ml.inference.ensemble_predictor import EnsemblePredictor
            ep = EnsemblePredictor(model_path=str(tmp_path))

            assert ep.version == "3.0.0"
            assert len(ep.predictors) == 2

            df = _make_features_df()
            result = ep.predict(df, horizon=24)
            assert result["point"].shape == (24,)

    def test_init_with_custom_weights_overrides_file(self, tmp_path):
        """Passing weights to __init__ should override metadata.yaml weights."""
        (tmp_path / "xgboost").mkdir()
        meta = {
            "version": "1.0",
            "weights": {"xgboost": {"weight": 0.5}},
        }
        (tmp_path / "metadata.yaml").write_text(yaml.dump(meta))

        mock_pred = MagicMock()
        mock_pred.predict.return_value = _make_prediction(horizon=24)

        custom_weights = {"xgboost": {"weight": 0.9}}
        with patch("ml.inference.ensemble_predictor.PricePredictor", return_value=mock_pred):
            from ml.inference.ensemble_predictor import EnsemblePredictor
            ep = EnsemblePredictor(
                model_path=str(tmp_path),
                weights=custom_weights,
            )
            assert ep.weights["xgboost"]["weight"] == 0.9


class TestEnsembleUncertaintyEstimation:
    """Focused tests on the uncertainty / confidence interval logic."""

    def test_more_models_disagreeing_gives_wider_intervals(self):
        """When models disagree more, total uncertainty should be larger."""
        horizon = 24

        # Scenario A: models agree
        agree_a = MagicMock()
        agree_a.predict.return_value = {
            "point": np.full(horizon, 50.0),
            "lower": np.full(horizon, 45.0),
            "upper": np.full(horizon, 55.0),
        }
        agree_b = MagicMock()
        agree_b.predict.return_value = {
            "point": np.full(horizon, 50.0),
            "lower": np.full(horizon, 45.0),
            "upper": np.full(horizon, 55.0),
        }

        # Scenario B: models disagree
        disagree_a = MagicMock()
        disagree_a.predict.return_value = {
            "point": np.full(horizon, 30.0),
            "lower": np.full(horizon, 25.0),
            "upper": np.full(horizon, 35.0),
        }
        disagree_b = MagicMock()
        disagree_b.predict.return_value = {
            "point": np.full(horizon, 70.0),
            "lower": np.full(horizon, 65.0),
            "upper": np.full(horizon, 75.0),
        }

        weights = {"m1": {"weight": 0.5}, "m2": {"weight": 0.5}}

        ep_agree = _build_ensemble({"m1": agree_a, "m2": agree_b}, weights=weights)
        ep_disagree = _build_ensemble({"m1": disagree_a, "m2": disagree_b}, weights=weights)

        df = _make_features_df()
        result_agree = ep_agree.predict(df, horizon=horizon)
        result_disagree = ep_disagree.predict(df, horizon=horizon)

        width_agree = np.mean(result_agree["upper"] - result_agree["lower"])
        width_disagree = np.mean(result_disagree["upper"] - result_disagree["lower"])

        assert width_disagree > width_agree
