"""
Tests for Hyperparameter Tuning (ml/training/hyperparameter_tuning.py)

Covers:
- HyperparameterSpace: search space definition and validation
- HyperparameterTuner: grid search, random search, bayesian optimization
- Trial execution with mocked objective function
- Best params selection and bounds validation
- _is_better helper, _save_results, _evaluate_params
- BayesianOptimizer convenience wrapper

Uses direct module loading to bypass ml.training.__init__.py.
"""

import os
import sys
import json
import importlib.util
import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from pathlib import Path

# ---------------------------------------------------------------------------
# Mock tensorflow and optuna at sys.modules level
# ---------------------------------------------------------------------------

_tf = MagicMock()
_tf.__version__ = "2.15.0"
_keras = MagicMock()
_tf.keras = _keras

_optuna = MagicMock()
_optuna.Trial = type("Trial", (), {})
_optuna.TrialPruned = type("TrialPruned", (Exception,), {})

for mod_name, mod in {
    "tensorflow": _tf,
    "tensorflow.keras": _keras,
    "tensorflow.keras.callbacks": MagicMock(),
    "tensorflow.keras.layers": MagicMock(),
    "tensorflow.keras.optimizers": MagicMock(),
    "tensorflow.keras.losses": MagicMock(),
    "tensorflow.keras.regularizers": MagicMock(),
    "tensorflow.keras.models": MagicMock(),
    "optuna": _optuna,
    "optuna.samplers": MagicMock(),
    "optuna.pruners": MagicMock(),
}.items():
    sys.modules.setdefault(mod_name, mod)

# ---------------------------------------------------------------------------
# Direct-load the hyperparameter_tuning module
# ---------------------------------------------------------------------------
_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "training"))

def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_hp_mod = _load_module(
    "ml.training.hyperparameter_tuning",
    os.path.join(_BASE, "hyperparameter_tuning.py"),
)

HyperparameterSpace = _hp_mod.HyperparameterSpace
HyperparameterTuner = _hp_mod.HyperparameterTuner
BayesianOptimizer = _hp_mod.BayesianOptimizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dummy_data(n=50, seq_len=24, features=10, horizon=24):
    X_train = np.random.randn(n, seq_len, features).astype(np.float32)
    y_train = np.random.randn(n, horizon).astype(np.float32)
    X_val = np.random.randn(n // 5, seq_len, features).astype(np.float32)
    y_val = np.random.randn(n // 5, horizon).astype(np.float32)
    return X_train, y_train, X_val, y_val


def _default_model_builder(params):
    model = MagicMock()
    history = MagicMock()
    history.history = {
        "val_loss": [0.5, 0.4, 0.35],
        "loss": [0.6, 0.5, 0.45],
    }
    model.fit.return_value = history
    return model


# ===================================================================
# Tests for HyperparameterSpace
# ===================================================================


class TestHyperparameterSpace:
    """Tests for HyperparameterSpace dataclass."""

    def test_default_values_are_populated(self):
        """Default search space has non-empty lists for every field."""
        space = HyperparameterSpace()
        assert len(space.cnn_filters) > 0
        assert len(space.lstm_units) > 0
        assert len(space.learning_rate) > 0
        assert len(space.batch_size) > 0
        assert len(space.optimizer) > 0

    def test_learning_rate_range_is_valid(self):
        """All learning rates should be positive and less than 1."""
        space = HyperparameterSpace()
        for lr in space.learning_rate:
            assert 0 < lr < 1, f"Learning rate {lr} out of range"

    def test_dropout_range_is_valid(self):
        """Dropout values should be in [0, 1)."""
        space = HyperparameterSpace()
        for d in space.lstm_dropout:
            assert 0.0 <= d < 1.0
        for d in space.dense_dropout:
            assert 0.0 <= d < 1.0

    def test_custom_search_space(self):
        """Custom values override defaults."""
        space = HyperparameterSpace(
            cnn_filters=[8, 16],
            lstm_units=[16],
            learning_rate=[0.01],
        )
        assert space.cnn_filters == [8, 16]
        assert space.lstm_units == [16]
        assert space.learning_rate == [0.01]

    def test_to_optuna_space_returns_dict(self):
        """to_optuna_space returns a dict with all expected keys."""
        space = HyperparameterSpace()
        mock_trial = MagicMock()
        mock_trial.suggest_categorical.side_effect = lambda name, choices: choices[0]
        mock_trial.suggest_int.side_effect = lambda name, low, high: low
        mock_trial.suggest_float.side_effect = lambda name, low, high: low
        mock_trial.suggest_loguniform.side_effect = lambda name, low, high: low

        result = space.to_optuna_space(mock_trial)

        assert isinstance(result, dict)
        expected_keys = {
            "cnn_filters", "cnn_kernel_size", "cnn_layers",
            "lstm_units", "lstm_layers", "lstm_dropout",
            "dense_units", "dense_layers", "dense_dropout",
            "learning_rate", "batch_size", "optimizer",
            "lookback_hours",
        }
        assert expected_keys == set(result.keys())

    def test_optuna_params_within_bounds(self):
        """Values returned by to_optuna_space are within the defined ranges."""
        space = HyperparameterSpace()
        mock_trial = MagicMock()
        mock_trial.suggest_categorical.side_effect = lambda name, choices: choices[0]
        mock_trial.suggest_int.side_effect = lambda name, low, high: low
        mock_trial.suggest_float.side_effect = lambda name, low, high: low
        mock_trial.suggest_loguniform.side_effect = lambda name, low, high: low

        result = space.to_optuna_space(mock_trial)

        assert result["cnn_filters"] in space.cnn_filters
        assert result["lstm_units"] in space.lstm_units
        assert result["batch_size"] in space.batch_size
        assert result["optimizer"] in space.optimizer
        assert min(space.learning_rate) <= result["learning_rate"] <= max(space.learning_rate)

    def test_kernel_sizes_are_odd(self):
        """Default kernel sizes should be odd (required for symmetric padding)."""
        space = HyperparameterSpace()
        for ks in space.cnn_kernel_size:
            assert ks % 2 == 1, f"Kernel size {ks} is not odd"

    def test_batch_sizes_are_powers_of_two(self):
        """Default batch sizes should be powers of two for GPU efficiency."""
        space = HyperparameterSpace()
        for bs in space.batch_size:
            assert (bs & (bs - 1)) == 0 and bs > 0, f"Batch size {bs} is not a power of 2"


# ===================================================================
# Tests for HyperparameterTuner
# ===================================================================


class TestHyperparameterTuner:
    """Tests for HyperparameterTuner class."""

    def test_init_creates_results_dir(self, tmp_path):
        """Constructor creates the results directory."""
        results_dir = tmp_path / "tuning_results"
        X_train, y_train, X_val, y_val = _dummy_data()

        tuner = HyperparameterTuner(
            model_builder=_default_model_builder,
            search_space=HyperparameterSpace(),
            X_train=X_train, y_train=y_train,
            X_val=X_val, y_val=y_val,
            results_dir=results_dir,
        )
        assert results_dir.exists()

    def test_is_better_minimize(self, tmp_path):
        """_is_better with direction='minimize' returns True when score < best."""
        X_train, y_train, X_val, y_val = _dummy_data()
        tuner = HyperparameterTuner(
            model_builder=_default_model_builder,
            search_space=HyperparameterSpace(),
            X_train=X_train, y_train=y_train,
            X_val=X_val, y_val=y_val,
            direction="minimize",
            results_dir=tmp_path / "res",
        )
        assert tuner._is_better(0.3, 0.5) is True
        assert tuner._is_better(0.5, 0.3) is False
        assert tuner._is_better(0.3, 0.3) is False

    def test_is_better_maximize(self, tmp_path):
        """_is_better with direction='maximize' returns True when score > best."""
        X_train, y_train, X_val, y_val = _dummy_data()
        tuner = HyperparameterTuner(
            model_builder=_default_model_builder,
            search_space=HyperparameterSpace(),
            X_train=X_train, y_train=y_train,
            X_val=X_val, y_val=y_val,
            direction="maximize",
            results_dir=tmp_path / "res",
        )
        assert tuner._is_better(0.5, 0.3) is True
        assert tuner._is_better(0.3, 0.5) is False

    def test_evaluate_params_calls_model_builder(self, tmp_path):
        """_evaluate_params calls model_builder with the given params."""
        builder = MagicMock(return_value=_default_model_builder({}))
        X_train, y_train, X_val, y_val = _dummy_data()

        tuner = HyperparameterTuner(
            model_builder=builder,
            search_space=HyperparameterSpace(),
            X_train=X_train, y_train=y_train,
            X_val=X_val, y_val=y_val,
            results_dir=tmp_path / "res",
        )

        params = {"learning_rate": 0.001, "batch_size": 32}
        score, history = tuner._evaluate_params(params)

        builder.assert_called_once_with(params)
        assert isinstance(score, float)

    def test_evaluate_params_returns_best_val_loss(self, tmp_path):
        """With metric='val_loss' and minimize, _evaluate_params returns min."""
        model = MagicMock()
        h = MagicMock()
        h.history = {"val_loss": [0.9, 0.7, 0.5]}
        model.fit.return_value = h

        builder = MagicMock(return_value=model)
        X_train, y_train, X_val, y_val = _dummy_data()

        tuner = HyperparameterTuner(
            model_builder=builder,
            search_space=HyperparameterSpace(),
            X_train=X_train, y_train=y_train,
            X_val=X_val, y_val=y_val,
            metric="val_loss",
            direction="minimize",
            results_dir=tmp_path / "res",
        )

        score, _ = tuner._evaluate_params({"batch_size": 16})
        assert score == pytest.approx(0.5)

    def test_save_results_creates_json(self, tmp_path):
        """_save_results writes a JSON file to results_dir."""
        X_train, y_train, X_val, y_val = _dummy_data()

        tuner = HyperparameterTuner(
            model_builder=_default_model_builder,
            search_space=HyperparameterSpace(),
            X_train=X_train, y_train=y_train,
            X_val=X_val, y_val=y_val,
            results_dir=tmp_path / "res",
        )
        tuner.results = [{"trial": 1, "score": 0.5, "params": {"lr": 0.001}}]
        tuner._save_results()

        json_files = list((tmp_path / "res").glob("tuning_results_*.json"))
        assert len(json_files) == 1

        with open(json_files[0]) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["score"] == 0.5

    def test_grid_search_returns_best(self, tmp_path):
        """grid_search returns best params and score from evaluated trials."""
        space = HyperparameterSpace(
            cnn_filters=[16], cnn_kernel_size=[3], cnn_layers=[1],
            lstm_units=[32], lstm_layers=[1], lstm_dropout=[0.1],
            dense_units=[16], dense_layers=[1], dense_dropout=[0.0],
            learning_rate=[0.001], batch_size=[16],
            optimizer=["adam"], lookback_hours=[72],
        )
        X_train, y_train, X_val, y_val = _dummy_data()

        tuner = HyperparameterTuner(
            model_builder=_default_model_builder,
            search_space=space,
            X_train=X_train, y_train=y_train,
            X_val=X_val, y_val=y_val,
            results_dir=tmp_path / "res",
        )

        best_params, best_score = tuner.grid_search(max_trials=1)
        assert best_params is not None
        assert isinstance(best_score, float)
        assert best_score < float("inf")

    def test_random_search_respects_n_trials(self, tmp_path):
        """random_search should not exceed n_trials evaluations."""
        call_count = [0]
        def counting_builder(params):
            call_count[0] += 1
            return _default_model_builder(params)

        X_train, y_train, X_val, y_val = _dummy_data()
        tuner = HyperparameterTuner(
            model_builder=counting_builder,
            search_space=HyperparameterSpace(),
            X_train=X_train, y_train=y_train,
            X_val=X_val, y_val=y_val,
            results_dir=tmp_path / "res",
        )
        tuner.random_search(n_trials=3)
        assert call_count[0] == 3


# ===================================================================
# Tests for BayesianOptimizer
# ===================================================================


class TestBayesianOptimizer:
    """Tests for the BayesianOptimizer convenience wrapper."""

    def test_optimize_returns_params_and_score(self):
        """BayesianOptimizer.optimize returns (best_params, best_score)."""
        X_train, y_train, X_val, y_val = _dummy_data()

        with patch.object(_hp_mod, "HyperparameterTuner") as MockTuner:
            mock_instance = MagicMock()
            mock_instance.bayesian_optimization.return_value = (
                {"learning_rate": 0.0005},
                0.25,
            )
            MockTuner.return_value = mock_instance

            best_params, best_score = BayesianOptimizer.optimize(
                model_builder=_default_model_builder,
                X_train=X_train, y_train=y_train,
                X_val=X_val, y_val=y_val,
                n_trials=5,
            )

        assert best_params == {"learning_rate": 0.0005}
        assert best_score == pytest.approx(0.25)

    def test_optimize_uses_default_search_space(self):
        """When search_space is None, a default HyperparameterSpace is used."""
        X_train, y_train, X_val, y_val = _dummy_data()

        with patch.object(_hp_mod, "HyperparameterTuner") as MockTuner:
            mock_instance = MagicMock()
            mock_instance.bayesian_optimization.return_value = ({}, 0.5)
            MockTuner.return_value = mock_instance

            BayesianOptimizer.optimize(
                model_builder=_default_model_builder,
                X_train=X_train, y_train=y_train,
                X_val=X_val, y_val=y_val,
                n_trials=2,
                search_space=None,
            )

            _, kwargs = MockTuner.call_args
            assert isinstance(kwargs["search_space"], HyperparameterSpace)
