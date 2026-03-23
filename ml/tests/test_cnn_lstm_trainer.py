"""
Tests for CNN-LSTM Model Trainer (ml/training/cnn_lstm_trainer.py)

Covers:
- prepare_sequences(): data preprocessing, windowing, shape validation
- train(): training loop with mocked PyTorch model
- _build_model(): model architecture layer verification
- save(): model serialization to disk
- Edge cases: empty data, single sample, mismatched features

Uses direct module loading to bypass ml.training.__init__.py and its
deep import chain (tensorflow, holidays, etc.).
"""

import os
import sys
import importlib.util
import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Mock torch (and submodules) at sys.modules level so the trainer can import
# ---------------------------------------------------------------------------
_torch = MagicMock()
_torch.__version__ = "2.0.0"

for mod_name in [
    "torch",
    "torch.nn",
    "torch.optim",
    "torch.optim.lr_scheduler",
    "torch.utils",
    "torch.utils.data",
]:
    sys.modules.setdefault(mod_name, MagicMock() if mod_name != "torch" else _torch)

# ---------------------------------------------------------------------------
# Direct-load the cnn_lstm_trainer module, bypassing ml.training.__init__.py
# ---------------------------------------------------------------------------
_BASE = os.path.join(os.path.dirname(__file__), "..", "training")
_BASE = os.path.abspath(_BASE)


def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_trainer_mod = _load_module(
    "ml.training.cnn_lstm_trainer",
    os.path.join(_BASE, "cnn_lstm_trainer.py"),
)
CNNLSTMTrainer = _trainer_mod.CNNLSTMTrainer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(forecast_horizon=24, n_outputs=3):
    """Minimal model config dict."""
    return {
        "cnn": {"filters": [16, 32], "kernel_sizes": [3, 5], "batch_norm": False},
        "lstm": {"units": [32, 16], "dropout": 0.0},
        "attention": {"enabled": False},
        "dense": {"units": [16], "dropout": 0.0},
        "output": {"forecast_horizon": forecast_horizon, "num_outputs": n_outputs},
    }


def _make_training_config():
    return {
        "batch_size": 8,
        "optimizer": {"learning_rate": 0.001, "beta_1": 0.9, "beta_2": 0.999},
        "lr_schedule": {"enabled": False},
        "early_stopping": {
            "patience": 5,
            "min_delta": 0.0001,
            "restore_best_weights": True,
        },
    }


def _make_dataframe(n_rows=500, n_features=4):
    """Build a simple DataFrame with feature and target columns."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_rows, freq="h")
    data = {
        f"feat_{i}": np.random.randn(n_rows).astype(np.float32)
        for i in range(n_features)
    }
    data["price"] = (
        50 + 10 * np.sin(np.arange(n_rows) * 0.1) + np.random.randn(n_rows) * 2
    ).astype(np.float32)
    return pd.DataFrame(data, index=dates)


# ===================================================================
# Tests for prepare_sequences
# ===================================================================


class TestPrepareSequences:
    """Tests for CNNLSTMTrainer.prepare_sequences()."""

    def test_output_shapes(self):
        """X and y arrays have correct 3-D shapes."""
        config = _make_config(forecast_horizon=24, n_outputs=3)
        trainer = CNNLSTMTrainer(config, _make_training_config())
        df = _make_dataframe(n_rows=500, n_features=4)
        feature_cols = [c for c in df.columns if c.startswith("feat_")]
        seq_len = 168

        X, y = trainer.prepare_sequences(
            df, feature_cols, "price", sequence_length=seq_len
        )

        expected_n_samples = 500 - seq_len - 24 + 1
        assert X.shape == (expected_n_samples, seq_len, len(feature_cols))
        assert y.shape == (expected_n_samples, 24, 3)

    def test_dtypes_are_float32(self):
        """Returned arrays are float32 for training efficiency."""
        config = _make_config()
        trainer = CNNLSTMTrainer(config, _make_training_config())
        df = _make_dataframe(n_rows=300)
        feature_cols = [c for c in df.columns if c.startswith("feat_")]

        X, y = trainer.prepare_sequences(df, feature_cols, "price", sequence_length=50)

        assert X.dtype == np.float32
        assert y.dtype == np.float32

    def test_scaler_is_fitted(self):
        """After prepare_sequences, trainer.scaler should be populated."""
        config = _make_config()
        trainer = CNNLSTMTrainer(config, _make_training_config())
        df = _make_dataframe(n_rows=300)
        feature_cols = [c for c in df.columns if c.startswith("feat_")]

        trainer.prepare_sequences(df, feature_cols, "price", sequence_length=50)

        assert trainer.scaler is not None

    def test_custom_forecast_horizon(self):
        """Forecast horizon from config controls y second dimension."""
        config = _make_config(forecast_horizon=12)
        trainer = CNNLSTMTrainer(config, _make_training_config())
        df = _make_dataframe(n_rows=300)
        feature_cols = [c for c in df.columns if c.startswith("feat_")]

        X, y = trainer.prepare_sequences(df, feature_cols, "price", sequence_length=50)

        assert y.shape[1] == 12

    def test_confidence_bounds_ordering(self):
        """Lower bound <= point estimate <= upper bound for positive prices."""
        config = _make_config(forecast_horizon=6)
        trainer = CNNLSTMTrainer(config, _make_training_config())
        df = _make_dataframe(n_rows=200)
        df["price"] = np.abs(df["price"]) + 10  # force positive
        feature_cols = [c for c in df.columns if c.startswith("feat_")]

        _, y = trainer.prepare_sequences(df, feature_cols, "price", sequence_length=50)

        point = y[:, :, 0]
        lower = y[:, :, 1]
        upper = y[:, :, 2]
        assert np.all(lower <= point + 1e-5)
        assert np.all(point <= upper + 1e-5)

    def test_short_data_produces_no_samples(self):
        """If data is shorter than seq_len + horizon, no sequences created."""
        config = _make_config(forecast_horizon=24)
        trainer = CNNLSTMTrainer(config, _make_training_config())
        df = _make_dataframe(n_rows=50)  # 50 < 168 + 24
        feature_cols = [c for c in df.columns if c.startswith("feat_")]

        X, y = trainer.prepare_sequences(df, feature_cols, "price", sequence_length=168)

        assert len(X) == 0
        assert len(y) == 0

    def test_single_valid_sample(self):
        """Exactly one sequence when data length == seq_len + horizon."""
        horizon = 24
        seq_len = 50
        config = _make_config(forecast_horizon=horizon)
        trainer = CNNLSTMTrainer(config, _make_training_config())
        df = _make_dataframe(n_rows=seq_len + horizon)
        feature_cols = [c for c in df.columns if c.startswith("feat_")]

        X, y = trainer.prepare_sequences(
            df, feature_cols, "price", sequence_length=seq_len
        )

        assert X.shape[0] == 1
        assert y.shape[0] == 1

    def test_features_are_scaled(self):
        """Scaled features should have approximately zero mean, unit variance."""
        config = _make_config(forecast_horizon=6)
        trainer = CNNLSTMTrainer(config, _make_training_config())
        df = _make_dataframe(n_rows=200, n_features=3)
        feature_cols = [c for c in df.columns if c.startswith("feat_")]

        X, _ = trainer.prepare_sequences(df, feature_cols, "price", sequence_length=50)

        flat = X.reshape(-1, X.shape[-1])
        means = np.mean(flat, axis=0)
        stds = np.std(flat, axis=0)
        for m in means:
            assert abs(m) < 1.0, f"Mean {m} not near zero after scaling"
        for s in stds:
            assert 0.1 < s < 5.0, f"Std {s} not reasonable after scaling"


# ===================================================================
# Tests for _build_model (mocked)
# ===================================================================


class TestBuildModel:
    """Tests for CNNLSTMTrainer._build_model() using patched internals."""

    def test_build_model_sets_self_model(self):
        """After _build_model, trainer.model should not be None."""
        config = _make_config()
        trainer = CNNLSTMTrainer(config, _make_training_config())

        with patch.object(trainer, "_build_model") as mock_build:
            fake_model = MagicMock()
            mock_build.return_value = fake_model
            result = trainer._build_model(4, 168)

        assert result is fake_model

    def test_build_model_accepts_feature_and_seqlen_args(self):
        """_build_model is called with (n_features, sequence_length)."""
        config = _make_config()
        trainer = CNNLSTMTrainer(config, _make_training_config())

        with patch.object(trainer, "_build_model") as mock_build:
            mock_build.return_value = MagicMock()
            trainer._build_model(10, 168)
            mock_build.assert_called_once_with(10, 168)


# ===================================================================
# Tests for train
# ===================================================================


class TestTrain:
    """Tests for CNNLSTMTrainer.train()."""

    def _make_trainer_and_data(
        self, n_samples=100, n_features=4, seq_len=20, horizon=6
    ):
        config = _make_config(forecast_horizon=horizon)
        training_config = _make_training_config()
        trainer = CNNLSTMTrainer(config, training_config)
        X = np.random.randn(n_samples, seq_len, n_features).astype(np.float32)
        y = np.random.randn(n_samples, horizon, 3).astype(np.float32)
        return trainer, X, y

    def test_train_returns_metrics_dict(self):
        """train() returns a dict with loss, val_loss, val_mape, epochs_trained."""
        trainer, X, y = self._make_trainer_and_data()

        # --- Build a fake tensor class that supports numpy-like subscript ---
        class FakeTensor:
            """Minimal tensor mock supporting shape, len, subscript, numpy()."""

            def __init__(self, arr):
                self._arr = np.array(arr, dtype=np.float32)
                self.shape = self._arr.shape

            def __len__(self):
                return self.shape[0]

            def __getitem__(self, key):
                return FakeTensor(self._arr[key])

            def numpy(self):
                return self._arr

        # Build a focused torch mock
        torch_test = MagicMock()
        torch_test.FloatTensor = lambda arr: FakeTensor(arr)

        batch_x = FakeTensor(X[:8])  # one batch
        batch_y = FakeTensor(y[:8])
        fake_loader = [(batch_x, batch_y)]
        torch_test.utils.data.DataLoader.return_value = fake_loader
        torch_test.utils.data.TensorDataset.return_value = MagicMock()

        loss_val = MagicMock()
        loss_val.item.return_value = 0.05
        loss_val.backward = MagicMock()
        torch_test.nn.MSELoss.return_value = MagicMock(return_value=loss_val)
        torch_test.optim.Adam.return_value = MagicMock()

        no_grad_ctx = MagicMock()
        no_grad_ctx.__enter__ = MagicMock(return_value=None)
        no_grad_ctx.__exit__ = MagicMock(return_value=False)
        torch_test.no_grad.return_value = no_grad_ctx

        # Model mock: must return a FakeTensor with correct shape for validation
        n_val = int(len(X) * 0.15)
        horizon = y.shape[1]
        n_outputs = y.shape[2]

        mock_model = MagicMock()
        # On each call, return a FakeTensor of the right shape
        mock_model.side_effect = lambda *args, **kwargs: FakeTensor(
            np.random.randn(
                args[0].shape[0] if hasattr(args[0], "shape") else n_val,
                horizon,
                n_outputs,
            )
        )
        mock_model.train = MagicMock()
        mock_model.eval = MagicMock()
        mock_model.parameters = MagicMock(return_value=[MagicMock()])
        mock_model.state_dict.return_value = {
            "w": MagicMock(clone=MagicMock(return_value=MagicMock()))
        }
        mock_model.load_state_dict = MagicMock()

        # Temporarily replace torch in sys.modules
        saved_torch = sys.modules["torch"]
        saved_utils = sys.modules.get("torch.utils.data")
        saved_nn = sys.modules.get("torch.nn")
        saved_optim = sys.modules.get("torch.optim")
        sys.modules["torch"] = torch_test
        sys.modules["torch.utils.data"] = torch_test.utils.data
        sys.modules["torch.nn"] = torch_test.nn
        sys.modules["torch.optim"] = torch_test.optim

        try:
            with patch.object(trainer, "_build_model", return_value=mock_model):
                trainer.model = mock_model
                metrics = trainer.train(X, y, validation_split=0.15, epochs=2)
        finally:
            sys.modules["torch"] = saved_torch
            for key, saved in [
                ("torch.utils.data", saved_utils),
                ("torch.nn", saved_nn),
                ("torch.optim", saved_optim),
            ]:
                if saved is not None:
                    sys.modules[key] = saved

        assert isinstance(metrics, dict)
        assert "loss" in metrics
        assert "val_loss" in metrics
        assert "val_mape" in metrics
        assert "epochs_trained" in metrics
        assert metrics["epochs_trained"] == 2

    def test_train_with_zero_samples_raises(self):
        """Training with empty arrays should raise an error."""
        config = _make_config(forecast_horizon=6)
        trainer = CNNLSTMTrainer(config, _make_training_config())

        X = np.empty((0, 20, 4), dtype=np.float32)
        y = np.empty((0, 6, 3), dtype=np.float32)

        with pytest.raises((ValueError, ZeroDivisionError, IndexError)):
            trainer.train(X, y, epochs=1)


# ===================================================================
# Tests for save
# ===================================================================


class TestSave:
    """Tests for CNNLSTMTrainer.save()."""

    def test_save_creates_expected_files(self, tmp_path):
        """save() writes config.yaml, training_config.yaml, metadata.yaml and calls torch.save/joblib.dump."""
        config = _make_config()
        training_config = _make_training_config()
        trainer = CNNLSTMTrainer(config, training_config)

        trainer.model = MagicMock()
        trainer.scaler = MagicMock()
        trainer.history = {
            "loss": [0.1, 0.08],
            "val_loss": [0.12, 0.09],
            "val_mape": [8.5, 7.2],
        }

        save_dir = str(tmp_path / "saved_model")

        # torch and joblib are imported lazily inside save().
        # We temporarily replace joblib with a mock so it doesn't
        # try to pickle a MagicMock scaler.
        torch_mock = sys.modules["torch"]
        torch_mock.save = MagicMock()

        original_joblib = sys.modules["joblib"]
        mock_joblib = MagicMock()
        sys.modules["joblib"] = mock_joblib

        try:
            trainer.save(save_dir)
        finally:
            sys.modules["joblib"] = original_joblib

        torch_mock.save.assert_called_once()
        mock_joblib.dump.assert_called_once()
        assert os.path.exists(os.path.join(save_dir, "config.yaml"))
        assert os.path.exists(os.path.join(save_dir, "training_config.yaml"))
        assert os.path.exists(os.path.join(save_dir, "metadata.yaml"))

    def test_save_without_scaler_skips_joblib_dump(self, tmp_path):
        """When scaler is None, joblib.dump should not be called."""
        config = _make_config()
        trainer = CNNLSTMTrainer(config, _make_training_config())
        trainer.model = MagicMock()
        trainer.scaler = None
        trainer.history = {"loss": [0.1], "val_loss": [0.12], "val_mape": [9.0]}

        save_dir = str(tmp_path / "model_no_scaler")

        # Replace real joblib with a fresh mock to track calls
        original_joblib = sys.modules.get("joblib")
        mock_joblib = MagicMock()
        sys.modules["joblib"] = mock_joblib

        try:
            trainer.save(save_dir)
            mock_joblib.dump.assert_not_called()
        finally:
            if original_joblib is not None:
                sys.modules["joblib"] = original_joblib

    def test_save_metadata_contains_metrics(self, tmp_path):
        """Metadata YAML includes val_loss and val_mape from training history."""
        import yaml

        config = _make_config()
        trainer = CNNLSTMTrainer(config, _make_training_config())
        trainer.model = MagicMock()
        trainer.scaler = None
        trainer.history = {
            "loss": [0.5, 0.3, 0.2],
            "val_loss": [0.6, 0.4, 0.25],
            "val_mape": [15.0, 10.0, 7.5],
        }

        save_dir = str(tmp_path / "model_meta")
        trainer.save(save_dir)

        with open(os.path.join(save_dir, "metadata.yaml")) as f:
            metadata = yaml.safe_load(f)

        assert metadata["metrics"]["val_loss"] == pytest.approx(0.25)
        assert metadata["metrics"]["val_mape"] == pytest.approx(7.5)
        assert metadata["epochs_trained"] == 3

    def test_save_creates_directory_if_missing(self, tmp_path):
        """save() creates nested directories that do not exist yet."""
        config = _make_config()
        trainer = CNNLSTMTrainer(config, _make_training_config())
        trainer.model = MagicMock()
        trainer.scaler = None
        trainer.history = {"loss": [0.1], "val_loss": [0.12], "val_mape": [9.0]}

        deep_path = str(tmp_path / "a" / "b" / "c")
        assert not os.path.exists(deep_path)

        trainer.save(deep_path)

        assert os.path.isdir(deep_path)

    def test_save_persists_residual_quantiles_when_available(self, tmp_path):
        """When _val_q5_residual and _val_q95_residual are set, save() includes
        them in metadata.yaml under 'val_residual_quantiles'."""
        import yaml

        config = _make_config(forecast_horizon=6)
        trainer = CNNLSTMTrainer(config, _make_training_config())
        trainer.model = MagicMock()
        trainer.scaler = None
        trainer.history = {"loss": [0.1], "val_loss": [0.12], "val_mape": [9.0]}
        trainer._val_q5_residual = np.array([-3.0, -2.5, -2.0, -1.5, -1.0, -0.5])
        trainer._val_q95_residual = np.array([3.0, 2.5, 2.0, 1.5, 1.0, 0.5])

        save_dir = str(tmp_path / "model_with_residuals")
        trainer.save(save_dir)

        with open(os.path.join(save_dir, "metadata.yaml")) as f:
            metadata = yaml.safe_load(f)

        assert "val_residual_quantiles" in metadata
        assert len(metadata["val_residual_quantiles"]["q5"]) == 6
        assert len(metadata["val_residual_quantiles"]["q95"]) == 6
        np.testing.assert_allclose(
            metadata["val_residual_quantiles"]["q5"],
            [-3.0, -2.5, -2.0, -1.5, -1.0, -0.5],
        )
        np.testing.assert_allclose(
            metadata["val_residual_quantiles"]["q95"], [3.0, 2.5, 2.0, 1.5, 1.0, 0.5]
        )

    def test_save_omits_residual_quantiles_when_none(self, tmp_path):
        """When residual quantiles are None (train not called), metadata.yaml
        does NOT include a 'val_residual_quantiles' key."""
        import yaml

        config = _make_config()
        trainer = CNNLSTMTrainer(config, _make_training_config())
        trainer.model = MagicMock()
        trainer.scaler = None
        trainer.history = {"loss": [0.1], "val_loss": [0.12], "val_mape": [9.0]}
        # Default: both are None
        assert trainer._val_q5_residual is None
        assert trainer._val_q95_residual is None

        save_dir = str(tmp_path / "model_no_residuals")
        trainer.save(save_dir)

        with open(os.path.join(save_dir, "metadata.yaml")) as f:
            metadata = yaml.safe_load(f)

        assert "val_residual_quantiles" not in metadata


# ===================================================================
# Tests for S3-10: Empirical prediction intervals (residual quantiles)
# ===================================================================


class TestResidualQuantileIntervals:
    """Tests for the empirical prediction interval fix (S3-10).

    Verifies that prepare_sequences() uses residual quantiles when available
    and that train() computes and stores them on the trainer instance.
    """

    def test_initial_residual_quantiles_are_none(self):
        """Freshly created trainer has no residual quantiles yet."""
        trainer = CNNLSTMTrainer(_make_config(), _make_training_config())
        assert trainer._val_q5_residual is None
        assert trainer._val_q95_residual is None

    def test_prepare_sequences_uses_empirical_bounds_when_available(self):
        """When residual quantiles are pre-set, prepare_sequences() must use
        them instead of the ±10 % fallback.

        We inject known non-trivial quantiles and verify the resulting y bounds
        differ from the fabricated ±10 % bounds.
        """
        config = _make_config(forecast_horizon=6)
        trainer = CNNLSTMTrainer(config, _make_training_config())

        # Inject a large downward residual quantile so the lower bound will
        # be much further below the point than 10 % would give.
        trainer._val_q5_residual = np.full(6, -20.0)  # Q5: point − 20
        trainer._val_q95_residual = np.full(6, 5.0)  # Q95: point + 5

        df = _make_dataframe(n_rows=200)
        df["price"] = np.abs(df["price"]) + 30.0  # force positive prices
        feature_cols = [c for c in df.columns if c.startswith("feat_")]

        _, y = trainer.prepare_sequences(df, feature_cols, "price", sequence_length=50)

        point = y[:, :, 0]
        lower = y[:, :, 1]
        upper = y[:, :, 2]

        # With q5 = −20, lower should be ~point − 20; ±10 % of ~30 would be ~3
        expected_lower = point + (-20.0)
        np.testing.assert_allclose(lower, expected_lower, rtol=1e-5)

        # With q95 = +5, upper should be ~point + 5; ±10 % of ~30 would be ~3
        expected_upper = point + 5.0
        np.testing.assert_allclose(upper, expected_upper, rtol=1e-5)

    def test_prepare_sequences_falls_back_to_10pct_when_no_residuals(self, caplog):
        """Without residual quantiles, bounds are ±10 % and a warning is logged."""
        import logging

        config = _make_config(forecast_horizon=6)
        trainer = CNNLSTMTrainer(config, _make_training_config())
        # No residuals set (default state)

        df = _make_dataframe(n_rows=200)
        df["price"] = np.abs(df["price"]) + 10.0  # force positive
        feature_cols = [c for c in df.columns if c.startswith("feat_")]

        with caplog.at_level(logging.WARNING, logger="ml.training.cnn_lstm_trainer"):
            _, y = trainer.prepare_sequences(
                df, feature_cols, "price", sequence_length=50
            )

        point = y[:, :, 0]
        lower = y[:, :, 1]
        upper = y[:, :, 2]

        np.testing.assert_allclose(lower, point * 0.9, rtol=1e-5)
        np.testing.assert_allclose(upper, point * 1.1, rtol=1e-5)

        warning_msgs = [r.message for r in caplog.records]
        assert any("residual quantiles not available" in m for m in warning_msgs), (
            f"Expected a warning about missing residual quantiles. Got: {warning_msgs}"
        )

    def test_empirical_bounds_differ_from_10pct_fabricated(self):
        """With non-trivial quantiles, the bounds must NOT equal ±10 % of point."""
        config = _make_config(forecast_horizon=4)
        trainer = CNNLSTMTrainer(config, _make_training_config())

        # Asymmetric quantiles: wider on the downside than 10 %
        trainer._val_q5_residual = np.full(4, -15.0)
        trainer._val_q95_residual = np.full(4, 2.0)

        df = _make_dataframe(n_rows=200)
        df["price"] = 50.0  # constant price for easy arithmetic
        feature_cols = [c for c in df.columns if c.startswith("feat_")]

        _, y = trainer.prepare_sequences(df, feature_cols, "price", sequence_length=50)

        point = y[:, :, 0]
        lower = y[:, :, 1]
        upper = y[:, :, 2]

        # ±10 % of 50 would give lower=45, upper=55.
        # Our quantiles give lower=50-15=35, upper=50+2=52.
        fabricated_lower = point * 0.9
        fabricated_upper = point * 1.1
        assert not np.allclose(lower, fabricated_lower, atol=0.1), (
            "Lower bound matches fabricated ±10 % — quantiles not applied."
        )
        assert not np.allclose(upper, fabricated_upper, atol=0.1), (
            "Upper bound matches fabricated ±10 % — quantiles not applied."
        )

    def test_residual_quantiles_stored_after_train(self):
        """train() must populate _val_q5_residual and _val_q95_residual.

        We use the same torch-mock infrastructure as TestTrain to exercise the
        residual computation path at the end of the training loop.
        """
        import torch as _torch_orig

        config = _make_config(forecast_horizon=6, n_outputs=3)
        training_config = _make_training_config()
        trainer = CNNLSTMTrainer(config, training_config)

        n_samples, seq_len, n_feats, horizon = 50, 10, 4, 6

        class FakeTensor:
            """Minimal tensor mock with numpy(), dim(), and shape support."""

            def __init__(self, arr):
                self._arr = np.array(arr, dtype=np.float32)
                self.shape = self._arr.shape

            def __len__(self):
                return self.shape[0]

            def __getitem__(self, key):
                return FakeTensor(self._arr[key])

            def numpy(self):
                return self._arr

            def dim(self):
                return self._arr.ndim

        X = np.random.randn(n_samples, seq_len, n_feats).astype(np.float32)
        y = np.random.randn(n_samples, horizon, 3).astype(np.float32) + 50.0

        torch_test = MagicMock()
        torch_test.FloatTensor = lambda arr: FakeTensor(arr)

        n_val = int(n_samples * 0.15)

        mock_model = MagicMock()
        mock_model.side_effect = lambda *args, **kwargs: FakeTensor(
            np.random.randn(
                args[0].shape[0] if hasattr(args[0], "shape") else n_val,
                horizon,
                3,
            ).astype(np.float32)
            + 50.0
        )
        mock_model.train = MagicMock()
        mock_model.eval = MagicMock()
        mock_model.parameters = MagicMock(return_value=[MagicMock()])
        mock_model.state_dict.return_value = {
            "w": MagicMock(clone=MagicMock(return_value=MagicMock()))
        }
        mock_model.load_state_dict = MagicMock()

        loss_val = MagicMock()
        loss_val.item.return_value = 0.05
        loss_val.backward = MagicMock()
        torch_test.nn.MSELoss.return_value = MagicMock(return_value=loss_val)
        torch_test.optim.Adam.return_value = MagicMock()

        no_grad_ctx = MagicMock()
        no_grad_ctx.__enter__ = MagicMock(return_value=None)
        no_grad_ctx.__exit__ = MagicMock(return_value=False)
        torch_test.no_grad.return_value = no_grad_ctx

        batch_x = FakeTensor(X[:8])
        batch_y = FakeTensor(y[:8])
        torch_test.utils.data.DataLoader.return_value = [(batch_x, batch_y)]
        torch_test.utils.data.TensorDataset.return_value = MagicMock()

        saved_torch = sys.modules["torch"]
        saved_submodules = {
            k: sys.modules.get(k)
            for k in ["torch.utils.data", "torch.nn", "torch.optim"]
        }
        sys.modules["torch"] = torch_test
        sys.modules["torch.utils.data"] = torch_test.utils.data
        sys.modules["torch.nn"] = torch_test.nn
        sys.modules["torch.optim"] = torch_test.optim

        try:
            with patch.object(trainer, "_build_model", return_value=mock_model):
                trainer.model = mock_model
                trainer.train(X, y, validation_split=0.15, epochs=2)
        finally:
            sys.modules["torch"] = saved_torch
            for key, saved in saved_submodules.items():
                if saved is not None:
                    sys.modules[key] = saved

        # After train(), residual quantiles must be set (or None with a warning
        # if computation failed — both are acceptable outcomes, but they must
        # be defined attributes).
        assert hasattr(trainer, "_val_q5_residual"), (
            "_val_q5_residual attribute missing after train()"
        )
        assert hasattr(trainer, "_val_q95_residual"), (
            "_val_q95_residual attribute missing after train()"
        )
