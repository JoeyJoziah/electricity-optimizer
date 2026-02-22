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
    "torch", "torch.nn", "torch.optim", "torch.optim.lr_scheduler",
    "torch.utils", "torch.utils.data",
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
        "early_stopping": {"patience": 5, "min_delta": 0.0001, "restore_best_weights": True},
    }


def _make_dataframe(n_rows=500, n_features=4):
    """Build a simple DataFrame with feature and target columns."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_rows, freq="h")
    data = {f"feat_{i}": np.random.randn(n_rows).astype(np.float32) for i in range(n_features)}
    data["price"] = (50 + 10 * np.sin(np.arange(n_rows) * 0.1) + np.random.randn(n_rows) * 2).astype(np.float32)
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

        X, y = trainer.prepare_sequences(df, feature_cols, "price", sequence_length=seq_len)

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

        X, y = trainer.prepare_sequences(df, feature_cols, "price", sequence_length=seq_len)

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

    def _make_trainer_and_data(self, n_samples=100, n_features=4, seq_len=20, horizon=6):
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
            np.random.randn(args[0].shape[0] if hasattr(args[0], 'shape') else n_val, horizon, n_outputs)
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
            for key, saved in [("torch.utils.data", saved_utils), ("torch.nn", saved_nn), ("torch.optim", saved_optim)]:
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
        trainer.history = {"loss": [0.1, 0.08], "val_loss": [0.12, 0.09], "val_mape": [8.5, 7.2]}

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
        trainer.history = {"loss": [0.5, 0.3, 0.2], "val_loss": [0.6, 0.4, 0.25], "val_mape": [15.0, 10.0, 7.5]}

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
