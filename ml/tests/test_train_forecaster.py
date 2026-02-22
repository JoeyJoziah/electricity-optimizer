"""
Tests for Training Forecaster Orchestration (ml/training/train_forecaster.py)

Covers:
- TrainingConfig: defaults, YAML loading, validation
- ModelTrainer: orchestration flow (load -> preprocess -> train -> evaluate -> save)
- Error handling for missing data paths
- Metric logging and report generation
- split_data: correct train/val/test proportions
- train_model convenience function

Uses direct module loading to bypass ml.training.__init__.py.
Pre-mocks ml.models.* and ml.data.* that train_forecaster imports.
"""

import os
import sys
import json
import importlib.util
import types
import pytest
import numpy as np
import pandas as pd
import yaml
from unittest.mock import MagicMock, patch
from pathlib import Path

# ---------------------------------------------------------------------------
# Pre-mock the ml.models and ml.data packages that train_forecaster imports.
# These require tensorflow / holidays which are not installed.
# ---------------------------------------------------------------------------

# Create mock modules for the imports that train_forecaster.py does:
#   from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig as CNNLSTMConfig
#   from ml.models.ensemble import EnsembleForecaster, EnsembleConfig, XGBoostConfig, LightGBMConfig
#   from ml.data.feature_engineering import ElectricityPriceFeatureEngine, create_dummy_data

_mock_price_forecaster = types.ModuleType("ml.models.price_forecaster")
_mock_price_forecaster.ElectricityPriceForecaster = MagicMock()
_mock_price_forecaster.ModelConfig = MagicMock()

_mock_ensemble = types.ModuleType("ml.models.ensemble")
_mock_ensemble.EnsembleForecaster = MagicMock()
_mock_ensemble.EnsembleConfig = MagicMock()
_mock_ensemble.XGBoostConfig = MagicMock()
_mock_ensemble.LightGBMConfig = MagicMock()

_mock_feature_eng = types.ModuleType("ml.data.feature_engineering")
_mock_feature_eng.ElectricityPriceFeatureEngine = MagicMock()
_mock_feature_eng.create_dummy_data = MagicMock()

_mock_models = types.ModuleType("ml.models")
_mock_data = types.ModuleType("ml.data")

# Install them into sys.modules BEFORE loading the trainer
sys.modules.setdefault("ml.models", _mock_models)
sys.modules.setdefault("ml.models.price_forecaster", _mock_price_forecaster)
sys.modules.setdefault("ml.models.ensemble", _mock_ensemble)
sys.modules.setdefault("ml.data", _mock_data)
sys.modules.setdefault("ml.data.feature_engineering", _mock_feature_eng)

# ---------------------------------------------------------------------------
# Direct-load train_forecaster.py
# ---------------------------------------------------------------------------
_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "training"))


def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_tf_mod = _load_module(
    "ml.training.train_forecaster",
    os.path.join(_BASE, "train_forecaster.py"),
)

TrainingConfig = _tf_mod.TrainingConfig
ModelTrainer = _tf_mod.ModelTrainer
train_model = _tf_mod.train_model


# ===================================================================
# Tests for TrainingConfig
# ===================================================================


class TestTrainingConfig:
    """Tests for TrainingConfig dataclass."""

    def test_default_values(self):
        """Default config has sensible defaults for all fields."""
        cfg = TrainingConfig()
        assert cfg.sequence_length == 168
        assert cfg.forecast_horizon == 24
        assert cfg.train_ratio == 0.7
        assert cfg.val_ratio == 0.15
        assert cfg.test_ratio == 0.15
        assert cfg.epochs == 100
        assert cfg.batch_size == 32
        assert cfg.learning_rate == 0.001
        assert cfg.target_mape == 10.0

    def test_ratios_sum_to_one(self):
        """train + val + test ratios should sum to 1.0."""
        cfg = TrainingConfig()
        total = cfg.train_ratio + cfg.val_ratio + cfg.test_ratio
        assert total == pytest.approx(1.0)

    def test_from_yaml(self, tmp_path):
        """from_yaml loads config values from a YAML file."""
        yaml_content = {
            "model": {
                "sequence_length": 72,
                "forecast_horizon": 12,
                "filters": [32, 64],
            },
            "training": {
                "epochs": 50,
                "batch_size": 64,
                "learning_rate": 0.0005,
            },
            "targets": {
                "mape": 8.0,
            },
        }
        yaml_path = tmp_path / "test_config.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        cfg = TrainingConfig.from_yaml(str(yaml_path))
        assert cfg.sequence_length == 72
        assert cfg.forecast_horizon == 12
        assert cfg.epochs == 50
        assert cfg.batch_size == 64
        assert cfg.learning_rate == 0.0005
        assert cfg.target_mape == 8.0
        assert cfg.cnn_filters == [32, 64]

    def test_from_yaml_missing_file_raises(self):
        """from_yaml raises FileNotFoundError for a missing YAML path."""
        with pytest.raises(FileNotFoundError):
            TrainingConfig.from_yaml("/nonexistent/config.yaml")

    def test_custom_overrides(self):
        """Custom keyword arguments override defaults."""
        cfg = TrainingConfig(
            epochs=10, batch_size=8, learning_rate=0.01, target_mape=5.0,
        )
        assert cfg.epochs == 10
        assert cfg.batch_size == 8
        assert cfg.learning_rate == 0.01
        assert cfg.target_mape == 5.0

    def test_data_path_default_is_none(self):
        """By default, data_path is None (dummy data used)."""
        cfg = TrainingConfig()
        assert cfg.data_path is None
        assert cfg.use_dummy_data is True

    def test_default_output_paths(self):
        """Default output directories have expected string values."""
        cfg = TrainingConfig()
        assert cfg.output_dir == "ml/saved_models"
        assert cfg.checkpoint_dir == "ml/checkpoints"
        assert cfg.log_dir == "ml/logs"

    def test_from_yaml_partial_keys(self, tmp_path):
        """from_yaml with partial keys falls back to defaults for missing ones."""
        yaml_content = {"training": {"epochs": 25}}
        yaml_path = tmp_path / "partial.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        cfg = TrainingConfig.from_yaml(str(yaml_path))
        assert cfg.epochs == 25
        assert cfg.batch_size == 32  # default
        assert cfg.sequence_length == 168  # default


# ===================================================================
# Tests for ModelTrainer
# ===================================================================


class TestModelTrainer:
    """Tests for ModelTrainer orchestration."""

    def _make_trainer(self, tmp_path, **config_overrides):
        config_overrides.setdefault("output_dir", str(tmp_path / "output"))
        config_overrides.setdefault("checkpoint_dir", str(tmp_path / "checkpoints"))
        config_overrides.setdefault("log_dir", str(tmp_path / "logs"))
        config_overrides.setdefault("use_dummy_data", True)
        config_overrides.setdefault("epochs", 2)
        config_overrides.setdefault("train_ensemble", False)
        cfg = TrainingConfig(**config_overrides)
        return ModelTrainer(cfg)

    def test_init_creates_directories(self, tmp_path):
        """ModelTrainer constructor creates output, checkpoint, and log dirs."""
        trainer = self._make_trainer(tmp_path)
        assert os.path.isdir(trainer.config.output_dir)
        assert os.path.isdir(trainer.config.checkpoint_dir)
        assert os.path.isdir(trainer.config.log_dir)

    def test_load_data_missing_path_raises(self, tmp_path):
        """load_data raises ValueError when use_dummy_data=False and no data_path."""
        trainer = self._make_trainer(tmp_path, use_dummy_data=False, data_path=None)
        with pytest.raises(ValueError, match="data_path must be provided"):
            trainer.load_data()

    def test_split_data_proportions(self, tmp_path):
        """split_data creates train/val/test with correct proportions."""
        trainer = self._make_trainer(tmp_path, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15)

        n = 100
        X = np.random.randn(n, 168, 10).astype(np.float32)
        y = np.random.randn(n, 24).astype(np.float32)

        (X_train, y_train), (X_val, y_val), (X_test, y_test) = trainer.split_data(X, y)

        assert len(X_train) == 70
        assert len(X_val) == 15
        assert len(X_test) == 15
        assert len(X_train) + len(X_val) + len(X_test) == n

    def test_split_data_temporal_order(self, tmp_path):
        """split_data preserves temporal order (no shuffling)."""
        trainer = self._make_trainer(tmp_path)
        n = 100
        X = np.arange(n * 168 * 10, dtype=np.float32).reshape(n, 168, 10)
        y = np.arange(n * 24, dtype=np.float32).reshape(n, 24)

        (X_train, _), (X_val, _), (X_test, _) = trainer.split_data(X, y)

        assert X_val[0, 0, 0] > X_train[-1, 0, 0]
        assert X_test[0, 0, 0] > X_val[-1, 0, 0]

    def test_generate_report_contains_key_sections(self, tmp_path):
        """generate_report produces a string with config and target sections."""
        trainer = self._make_trainer(tmp_path)
        report = trainer.generate_report()

        assert "TRAINING REPORT" in report
        assert "CONFIGURATION" in report
        assert "Sequence Length" in report
        assert "Forecast Horizon" in report
        assert "TARGET ACHIEVEMENT" in report

    def test_generate_report_with_evaluation_results(self, tmp_path):
        """Report includes evaluation metrics when training_results has them."""
        trainer = self._make_trainer(tmp_path)
        trainer.training_results = {
            "evaluation": {
                "cnn_lstm": {"mape": 7.5, "rmse": 3.2},
            },
        }
        report = trainer.generate_report()

        assert "EVALUATION RESULTS" in report
        assert "CNN_LSTM" in report
        assert "ACHIEVED" in report  # 7.5 < 10.0 target

    def test_save_models_writes_results_json(self, tmp_path):
        """save_models writes a training_results JSON file."""
        trainer = self._make_trainer(tmp_path)
        trainer.training_results = {"status": "success", "val_loss": 0.3}
        trainer.cnn_lstm_model = None
        trainer.ensemble_model = None

        trainer.save_models()

        json_files = list(Path(trainer.config.output_dir).glob("training_results_*.json"))
        assert len(json_files) == 1

        with open(json_files[0]) as f:
            data = json.load(f)
        assert data["status"] == "success"

    def test_evaluate_returns_metrics(self, tmp_path):
        """evaluate returns a dict containing model metrics."""
        trainer = self._make_trainer(tmp_path, target_mape=10.0)

        mock_model = MagicMock()
        mock_model.evaluate.return_value = {"mape": 8.5, "rmse": 3.0}
        trainer.cnn_lstm_model = mock_model
        trainer.ensemble_model = None

        X_test = np.random.randn(20, 168, 10).astype(np.float32)
        y_test = np.random.randn(20, 24).astype(np.float32)

        results = trainer.evaluate(X_test, y_test)
        assert "cnn_lstm" in results
        assert results["cnn_lstm"]["mape"] == 8.5


# ===================================================================
# Tests for train_model function
# ===================================================================


class TestTrainModel:
    """Tests for the train_model convenience function."""

    def test_train_model_creates_trainer_and_calls_run(self, tmp_path):
        """train_model creates a ModelTrainer and calls .run()."""
        with patch.object(_tf_mod, "ModelTrainer") as MockTrainer:
            mock_instance = MagicMock()
            mock_instance.run.return_value = {"status": "success"}
            MockTrainer.return_value = mock_instance

            result = train_model(TrainingConfig(
                output_dir=str(tmp_path / "out"),
                checkpoint_dir=str(tmp_path / "ckpt"),
                log_dir=str(tmp_path / "log"),
            ))

        MockTrainer.assert_called_once()
        mock_instance.run.assert_called_once()
        assert result["status"] == "success"

    def test_train_model_default_config(self):
        """train_model with config=None uses default TrainingConfig."""
        with patch.object(_tf_mod, "ModelTrainer") as MockTrainer:
            mock_instance = MagicMock()
            mock_instance.run.return_value = {"status": "ok"}
            MockTrainer.return_value = mock_instance

            result = train_model(None)

        args, _ = MockTrainer.call_args
        assert isinstance(args[0], TrainingConfig)


# ===================================================================
# Tests for the full run() pipeline
# ===================================================================


class TestRunPipeline:
    """Tests for ModelTrainer.run() orchestration."""

    def test_run_orchestrates_all_steps(self, tmp_path):
        """run() calls load_data -> prepare_features -> split -> train -> eval -> save."""
        config = TrainingConfig(
            use_dummy_data=True, epochs=2, train_ensemble=False,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "ckpt"),
            log_dir=str(tmp_path / "log"),
        )
        trainer = ModelTrainer(config)

        mock_df = pd.DataFrame(
            {"price": np.random.randn(500)},
            index=pd.date_range("2024-01-01", periods=500, freq="h"),
        )
        X = np.random.randn(100, 168, 10).astype(np.float32)
        y = np.random.randn(100, 24).astype(np.float32)

        trainer.load_data = MagicMock(return_value=mock_df)
        trainer.prepare_features = MagicMock(return_value=(X, y))
        trainer.split_data = MagicMock(return_value=(
            (X[:70], y[:70]),
            (X[70:85], y[70:85]),
            (X[85:], y[85:]),
        ))
        trainer.train_cnn_lstm = MagicMock(return_value={"loss": [0.1]})
        trainer.train_ensemble = MagicMock()
        trainer.evaluate = MagicMock(return_value={"cnn_lstm": {"mape": 7.0}})
        trainer.save_models = MagicMock()

        results = trainer.run()

        trainer.load_data.assert_called_once()
        trainer.prepare_features.assert_called_once()
        trainer.split_data.assert_called_once()
        trainer.train_cnn_lstm.assert_called_once()
        trainer.evaluate.assert_called_once()
        trainer.save_models.assert_called_once()
        assert results["status"] == "success"

    def test_run_captures_failure(self, tmp_path):
        """run() sets status='failed' and re-raises on exception."""
        config = TrainingConfig(
            use_dummy_data=True,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "ckpt"),
            log_dir=str(tmp_path / "log"),
        )
        trainer = ModelTrainer(config)
        trainer.load_data = MagicMock(side_effect=RuntimeError("Data load failed"))

        with pytest.raises(RuntimeError, match="Data load failed"):
            trainer.run()

        assert trainer.training_results["status"] == "failed"
        assert "Data load failed" in trainer.training_results["error"]
