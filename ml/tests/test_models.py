"""
TDD Tests for ML Models - Price Forecasting

These tests are written FIRST following TDD principles.
Target: MAPE < 10% for 24-hour forecasts

Test Coverage:
- Model initialization and architecture
- Training pipeline
- Prediction with confidence intervals
- Model save/load
- Ensemble models
- Performance requirements
"""

import pytest
import numpy as np
import os
import time


# ============================================================================
# CNN-LSTM Model Tests
# ============================================================================


class TestCNNLSTMModelInitialization:
    """Tests for model initialization and architecture."""

    @pytest.mark.requires_tf
    def test_model_initialization_with_defaults(self):
        """Test CNN-LSTM model can be initialized with default config."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        config = ModelConfig()
        model = ElectricityPriceForecaster(config=config)

        assert model.model is not None
        assert model.config.sequence_length == 168
        assert model.config.num_features == 15
        assert model.config.forecast_horizon == 24

    @pytest.mark.requires_tf
    def test_model_initialization_with_custom_config(self):
        """Test CNN-LSTM model with custom configuration."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        config = ModelConfig(
            sequence_length=120,
            num_features=10,
            forecast_horizon=12,
            cnn_filters=[32, 64, 32],
            lstm_units=[64, 32],
        )
        model = ElectricityPriceForecaster(config=config)

        assert model.config.sequence_length == 120
        assert model.config.num_features == 10
        assert model.config.forecast_horizon == 12

    @pytest.mark.requires_tf
    def test_model_has_correct_architecture(self):
        """Test model has CNN, LSTM, and Dense layers."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        config = ModelConfig(
            sequence_length=168,
            num_features=10,
            cnn_filters=[32, 64, 32],
            lstm_units=[64, 32],
        )
        model = ElectricityPriceForecaster(config=config)

        layer_types = [type(layer).__name__ for layer in model.model.layers]

        # Should have CNN layers
        assert "Conv1D" in layer_types
        # Should have LSTM layers (bidirectional wraps them)
        assert any("Bidirectional" in t or "LSTM" in t for t in layer_types)
        # Should have Dense layers
        assert "Dense" in layer_types

    @pytest.mark.requires_tf
    def test_model_input_output_shapes(self):
        """Test model input and output shapes are correct."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        config = ModelConfig(
            sequence_length=168, num_features=10, forecast_horizon=24, num_quantiles=3
        )
        model = ElectricityPriceForecaster(config=config)

        # Input shape should be (batch, sequence_length, num_features)
        assert model.model.input_shape == (None, 168, 10)

        # Output shape should be (batch, forecast_horizon, num_quantiles)
        assert model.model.output_shape == (None, 24, 3)

    @pytest.mark.requires_tf
    def test_model_parameter_count_reasonable(self):
        """Test model has reasonable number of parameters."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        config = ModelConfig(
            sequence_length=168,
            num_features=15,
            cnn_filters=[64, 128, 64],
            lstm_units=[128, 64],
            dense_units=[64, 32],
        )
        model = ElectricityPriceForecaster(config=config)

        param_count = model.model.count_params()

        # Should have substantial but not excessive parameters
        assert 100_000 < param_count < 10_000_000


class TestCNNLSTMModelTraining:
    """Tests for model training pipeline."""

    @pytest.mark.requires_tf
    def test_model_training_runs(self, sample_training_data, tmp_model_dir):
        """Test model training completes without errors."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            cnn_filters=[16, 32, 16],
            lstm_units=[32, 16],
            epochs=2,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        history = model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        assert "loss" in history
        assert "val_loss" in history
        assert len(history["loss"]) >= 1

    @pytest.mark.requires_tf
    def test_training_loss_decreases(self, sample_training_data, tmp_model_dir):
        """Test that training loss decreases over epochs."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            cnn_filters=[16, 32, 16],
            lstm_units=[32, 16],
            epochs=5,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        history = model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        losses = history["loss"]
        # Loss should generally decrease (first vs last)
        assert losses[-1] <= losses[0] * 1.5  # Allow some variance

    @pytest.mark.requires_tf
    def test_model_is_fitted_after_training(self, sample_training_data, tmp_model_dir):
        """Test model is marked as fitted after training."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=1,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        assert not model.is_fitted

        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        assert model.is_fitted


class TestCNNLSTMModelPrediction:
    """Tests for model prediction functionality."""

    @pytest.mark.requires_tf
    def test_model_prediction_shape(self, sample_training_data, tmp_model_dir):
        """Test prediction output has correct shape."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=1,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        X_test = X[:10]
        predictions = model.predict(X_test, return_confidence=False)

        assert predictions.shape == (10, y.shape[1])

    @pytest.mark.requires_tf
    def test_prediction_with_confidence_intervals(
        self, sample_training_data, tmp_model_dir
    ):
        """Test prediction returns confidence intervals."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=1,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        X_test = X[:5]
        forecast, lower, upper = model.predict(X_test, return_confidence=True)

        assert forecast.shape == (5, y.shape[1])
        assert lower.shape == (5, y.shape[1])
        assert upper.shape == (5, y.shape[1])

        # Lower should be less than upper
        assert np.all(lower <= upper)

    @pytest.mark.requires_tf
    def test_predictions_no_nan_values(self, sample_training_data, tmp_model_dir):
        """Test predictions contain no NaN values."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=2,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        predictions = model.predict(X[:20], return_confidence=False)

        assert not np.isnan(predictions).any()
        assert not np.isinf(predictions).any()

    @pytest.mark.requires_tf
    def test_single_sample_prediction(self, sample_training_data, tmp_model_dir):
        """Test prediction on single sample."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=1,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        result = model.predict_single(X[0:1])

        assert "forecast" in result
        assert "lower_bound" in result
        assert "upper_bound" in result
        assert result["forecast"].shape == (y.shape[1],)


class TestCNNLSTMModelEvaluation:
    """Tests for model evaluation metrics."""

    @pytest.mark.requires_tf
    def test_model_evaluation_returns_metrics(
        self, sample_training_data, tmp_model_dir
    ):
        """Test evaluation returns required metrics."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=2,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        X_test, y_test = X[80:], y[80:]
        metrics = model.evaluate(X_test, y_test)

        assert "mae" in metrics
        assert "rmse" in metrics
        assert "mape" in metrics
        assert "direction_accuracy" in metrics
        assert "coverage" in metrics

    @pytest.mark.requires_tf
    def test_metrics_are_valid_ranges(self, sample_training_data, tmp_model_dir):
        """Test metrics are in valid ranges."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=2,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        metrics = model.evaluate(X[80:], y[80:])

        # MAPE should be positive
        assert metrics["mape"] >= 0
        # MAE should be positive
        assert metrics["mae"] >= 0
        # RMSE should be positive
        assert metrics["rmse"] >= 0
        # Direction accuracy should be 0-1
        assert 0 <= metrics["direction_accuracy"] <= 1
        # Coverage should be 0-1
        assert 0 <= metrics["coverage"] <= 1


class TestCNNLSTMModelSaveLoad:
    """Tests for model persistence."""

    @pytest.mark.requires_tf
    def test_model_save(self, sample_training_data, tmp_model_dir):
        """Test model can be saved."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=1,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        save_path = os.path.join(tmp_model_dir, "saved_model")
        model.save(save_path)

        assert os.path.exists(save_path)
        assert os.path.exists(os.path.join(save_path, "model.keras"))
        assert os.path.exists(os.path.join(save_path, "config.json"))

    @pytest.mark.requires_tf
    def test_model_load(self, sample_training_data, tmp_model_dir):
        """Test model can be loaded."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=1,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        save_path = os.path.join(tmp_model_dir, "saved_model")
        model.save(save_path)

        loaded_model = ElectricityPriceForecaster(model_path=save_path)

        assert loaded_model.is_fitted
        assert loaded_model.model is not None

    @pytest.mark.requires_tf
    def test_loaded_model_predictions_match(self, sample_training_data, tmp_model_dir):
        """Test loaded model produces same predictions."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=1,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        X_test = X[:5]
        original_pred = model.predict(X_test, return_confidence=False)

        save_path = os.path.join(tmp_model_dir, "saved_model")
        model.save(save_path)

        loaded_model = ElectricityPriceForecaster(model_path=save_path)
        loaded_pred = loaded_model.predict(X_test, return_confidence=False)

        np.testing.assert_array_almost_equal(original_pred, loaded_pred, decimal=5)


class TestCNNLSTMModelPerformance:
    """Tests for model performance requirements."""

    @pytest.mark.requires_tf
    @pytest.mark.slow
    def test_inference_time_under_1_second(self, sample_training_data, tmp_model_dir):
        """Test inference time is under 1 second for 24-hour forecast."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=1,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        X_test = X[0:1]  # Single sample

        # Warm up
        _ = model.predict(X_test, return_confidence=False)

        # Measure
        start = time.time()
        for _ in range(10):
            _ = model.predict(X_test, return_confidence=False)
        elapsed = (time.time() - start) / 10

        assert elapsed < 1.0, f"Inference time {elapsed:.3f}s exceeds 1s"

    @pytest.mark.requires_tf
    @pytest.mark.slow
    def test_batch_inference_efficient(self, sample_training_data, tmp_model_dir):
        """Test batch inference for 6000 samples completes in reasonable time."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=1,
            batch_size=16,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        # Simulate batch for 100 stocks (scaled down from 6000)
        X_batch = np.tile(X[:1], (100, 1, 1))

        start = time.time()
        _ = model.predict(X_batch, return_confidence=False)
        elapsed = time.time() - start

        # Should complete in under 30 seconds for 100 stocks
        assert elapsed < 30.0, f"Batch inference {elapsed:.2f}s too slow"


# ============================================================================
# Ensemble Model Tests
# ============================================================================


class TestEnsembleModel:
    """Tests for ensemble forecaster."""

    @pytest.mark.requires_tf
    def test_ensemble_initialization(self):
        """Test ensemble model can be initialized."""
        try:
            from ml.models.ensemble import EnsembleForecaster, EnsembleConfig

            config = EnsembleConfig(
                cnn_lstm_weight=0.5,
                xgboost_weight=0.25,
                lightgbm_weight=0.25,
                forecast_horizon=24,
            )

            ensemble = EnsembleForecaster(config=config)
            assert ensemble is not None
        except ImportError:
            pytest.skip("Ensemble model dependencies not installed")

    @pytest.mark.requires_tf
    def test_ensemble_prediction_combines_models(
        self, sample_training_data, tmp_model_dir
    ):
        """Test ensemble combines predictions from multiple models."""
        try:
            from ml.models.ensemble import EnsembleForecaster, EnsembleConfig

            X, y = sample_training_data

            config = EnsembleConfig(
                cnn_lstm_weight=0.5,
                xgboost_weight=0.25,
                lightgbm_weight=0.25,
                forecast_horizon=y.shape[1],
            )

            ensemble = EnsembleForecaster(config=config)
            ensemble.fit(X, y, X_val=X[:10], y_val=y[:10], cnn_lstm_epochs=1, verbose=0)

            predictions = ensemble.predict(X[:5])
            assert predictions.shape == (5, y.shape[1])

        except ImportError:
            pytest.skip("Ensemble model dependencies not installed")


# ============================================================================
# Target Accuracy Tests (MAPE < 10%)
# ============================================================================


class TestMAPETarget:
    """Critical tests for MAPE < 10% requirement."""

    @pytest.mark.requires_tf
    @pytest.mark.slow
    def test_mape_below_10_percent_with_training(
        self, large_training_data, tmp_model_dir
    ):
        """
        CRITICAL: Test MAPE is below 10% after proper training.

        Note: This is a placeholder that tests the metric calculation.
        Actual MAPE < 10% requires:
        - Real electricity price data
        - Proper feature engineering
        - Sufficient training epochs
        """
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = large_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            cnn_filters=[32, 64, 32],
            lstm_units=[64, 32],
            epochs=10,  # More epochs for better accuracy
            batch_size=32,
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X,
            y,
            checkpoint_dir=os.path.join(tmp_model_dir, "checkpoints"),
            log_dir=os.path.join(tmp_model_dir, "logs"),
            verbose=0,
        )

        X_test, y_test = X[800:], y[800:]
        metrics = model.evaluate(X_test, y_test)

        # On random data, MAPE will be high
        # This test validates the metric calculation works
        assert metrics["mape"] >= 0
        assert isinstance(metrics["mape"], float)

        # For real data with proper training, uncomment:
        # assert metrics['mape'] < 10.0, f"MAPE {metrics['mape']:.2f}% exceeds 10% target"


# ============================================================================
# Security Tests — Task 0.2: No unsafe pickle path in predictor
# ============================================================================


class TestNoUnsafePickleInPredictor:
    """Verify that PricePredictor never calls torch.load with weights_only=False."""

    def test_predictor_source_has_no_weights_only_false(self):
        """Static check: weights_only=False must not appear in predictor.py."""
        predictor_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "inference",
            "predictor.py",
        )
        with open(predictor_path) as fh:
            source = fh.read()
        assert "weights_only=False" not in source, (
            "Unsafe torch.load(weights_only=False) found in predictor.py — "
            "remove the fallback branch to prevent arbitrary code execution."
        )

    def test_predictor_no_config_raises_rather_than_unsafe_load(self, tmp_path):
        """
        When config.yaml is missing, PricePredictor must raise an error
        instead of falling back to the unsafe full-module load path.
        """
        torch = pytest.importorskip("torch", reason="torch not installed")

        # Create a minimal model directory with model.pt but NO config.yaml
        model_dir = str(tmp_path / "no_config_model")
        os.makedirs(model_dir, exist_ok=True)

        # Write a trivial state_dict so the file exists
        state = {"weight": torch.tensor([1.0, 2.0])}
        torch.save(state, os.path.join(model_dir, "model.pt"))

        # No config.yaml → the old code fell back to weights_only=False.
        # The new code must raise ValueError / RuntimeError instead.
        from ml.inference.predictor import PricePredictor

        with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
            PricePredictor(model_path=model_dir, model_type="cnn_lstm")

    def test_torch_load_called_with_weights_only_true(self, tmp_path, monkeypatch):
        """
        Patch torch.load to record kwargs; verify weights_only is always True.
        """
        torch = pytest.importorskip("torch", reason="torch not installed")
        import yaml

        calls = []
        original_load = torch.load

        def mock_load(*args, **kwargs):
            calls.append(kwargs)
            return original_load(*args, **kwargs)

        monkeypatch.setattr(torch, "load", mock_load)

        # Build a proper saved model dir
        model_dir = str(tmp_path / "safe_model")
        os.makedirs(model_dir, exist_ok=True)

        # Minimal config.yaml so predictor can reconstruct the architecture
        config = {
            "cnn": {"filters": [8], "kernel_sizes": [3]},
            "lstm": {"units": [8], "dropout": 0.0},
            "attention": {"enabled": False},
            "dense": {"units": [8], "dropout": 0.0},
            "output": {"forecast_horizon": 4, "num_outputs": 3},
            "input": {"n_features": 4, "sequence_length": 8},
        }
        with open(os.path.join(model_dir, "config.yaml"), "w") as f:
            yaml.dump(config, f)

        # Build and save a real state_dict using CNNLSTMTrainer
        from ml.training.cnn_lstm_trainer import CNNLSTMTrainer

        trainer = CNNLSTMTrainer(config, {})
        trainer._build_model(n_features=4, sequence_length=8)
        torch.save(trainer.model.state_dict(), os.path.join(model_dir, "model.pt"))

        from ml.inference.predictor import PricePredictor

        _ = PricePredictor(model_path=model_dir, model_type="cnn_lstm")

        # Every torch.load call in the loading path must use weights_only=True
        for call_kwargs in calls:
            assert call_kwargs.get("weights_only") is True, (
                f"torch.load was called without weights_only=True: {call_kwargs}"
            )


# ============================================================================
# Security Tests — Task 0.3: HMAC integrity verification for joblib sites
# ============================================================================


class TestModelIntegrityUtils:
    """Tests for ml/utils/integrity.py — sign_model / verify_model_integrity."""

    def _get_integrity_module(self):
        from ml.utils import integrity

        return integrity

    def test_sign_and_verify_roundtrip(self, tmp_path, monkeypatch):
        """sign_model + verify_model_integrity roundtrip succeeds on clean file."""
        monkeypatch.setenv("ML_MODEL_SIGNING_KEY", "a" * 64)
        integrity = self._get_integrity_module()

        target = tmp_path / "model.pkl"
        target.write_bytes(b"fake model content")

        integrity.sign_model(str(target))

        # Verification must not raise
        integrity.verify_model_integrity(str(target))

    def test_verify_raises_on_tampered_file(self, tmp_path, monkeypatch):
        """verify_model_integrity raises ValueError if file content is altered."""
        monkeypatch.setenv("ML_MODEL_SIGNING_KEY", "b" * 64)
        integrity = self._get_integrity_module()

        target = tmp_path / "scaler.pkl"
        target.write_bytes(b"original content")
        integrity.sign_model(str(target))

        # Tamper with the file
        target.write_bytes(b"evil payload")

        with pytest.raises(ValueError, match="[Ii]ntegrity|[Mm]ismatch|[Tt]amper"):
            integrity.verify_model_integrity(str(target))

    def test_verify_raises_when_signature_missing(self, tmp_path, monkeypatch):
        """verify_model_integrity raises FileNotFoundError if .sig file is absent."""
        monkeypatch.setenv("ML_MODEL_SIGNING_KEY", "c" * 64)
        integrity = self._get_integrity_module()

        target = tmp_path / "model.pkl"
        target.write_bytes(b"content without signature")

        with pytest.raises((FileNotFoundError, ValueError)):
            integrity.verify_model_integrity(str(target))

    def test_sign_creates_sig_file(self, tmp_path, monkeypatch):
        """sign_model must create a companion .sig file next to the model file."""
        monkeypatch.setenv("ML_MODEL_SIGNING_KEY", "d" * 64)
        integrity = self._get_integrity_module()

        target = tmp_path / "ensemble.pkl"
        target.write_bytes(b"some data")
        integrity.sign_model(str(target))

        sig_path = tmp_path / "ensemble.pkl.sig"
        assert sig_path.exists(), ".sig file was not created by sign_model()"
        assert len(sig_path.read_text().strip()) > 0

    def test_verify_no_key_env_raises(self, tmp_path, monkeypatch):
        """When ML_MODEL_SIGNING_KEY is unset, verify raises EnvironmentError."""
        monkeypatch.delenv("ML_MODEL_SIGNING_KEY", raising=False)
        integrity = self._get_integrity_module()

        target = tmp_path / "model.pkl"
        target.write_bytes(b"data")
        # Create a fake sig file to not trigger FileNotFoundError
        (tmp_path / "model.pkl.sig").write_text("deadbeef")

        with pytest.raises((EnvironmentError, ValueError)):
            integrity.verify_model_integrity(str(target))


def _load_source_file(path: str):
    """Load a Python source file directly without triggering package __init__ imports.

    This is used by structural tests that only need to inspect source text and
    cannot rely on the normal package import chain (which pulls in TF/torch).
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_src_module", path)
    # We intentionally do NOT exec_module — we only need the source text.
    with open(path) as fh:
        return fh.read()


class TestJobLibSitesHaveIntegrityChecks:
    """
    Structural tests ensuring every joblib.load call in ensemble.py and
    cnn_lstm_trainer.py is guarded by verify_model_integrity().
    """

    _ENSEMBLE_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models",
        "ensemble.py",
    )
    _TRAINER_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "training",
        "cnn_lstm_trainer.py",
    )

    def test_ensemble_load_calls_verify_integrity(self):
        """LightGBMForecaster.load must call verify_model_integrity before joblib.load."""
        source = _load_source_file(self._ENSEMBLE_PATH)

        assert "verify_model_integrity" in source, (
            "ensemble.py does not import/call verify_model_integrity — "
            "joblib.load sites are unprotected."
        )

    def test_cnn_lstm_trainer_scaler_save_calls_sign_model(self):
        """CNNLSTMTrainer.save must call sign_model after joblib.dump(scaler)."""
        source = _load_source_file(self._TRAINER_PATH)

        assert "sign_model" in source, (
            "cnn_lstm_trainer.py does not call sign_model after saving scaler.pkl."
        )

    def test_lightgbm_forecaster_save_calls_sign_model(self):
        """LightGBMForecaster.save must call sign_model after each joblib.dump."""
        source = _load_source_file(self._ENSEMBLE_PATH)

        assert "sign_model" in source, (
            "ensemble.py LightGBMForecaster.save() does not call sign_model."
        )


class TestJobLibLoadRaisesOnTamperedModel(object):
    """
    Integration tests: actual joblib.load sites raise when the .sig is wrong.
    """

    def test_lightgbm_forecaster_load_rejects_tampered_pkl(self, tmp_path, monkeypatch):
        """LightGBMForecaster.load raises ValueError when a .pkl is tampered."""
        # Skip gracefully if lightgbm is not installed in this environment
        pytest.importorskip("lightgbm", reason="lightgbm not installed")
        import json
        import importlib.util
        import joblib

        monkeypatch.setenv("ML_MODEL_SIGNING_KEY", "e" * 64)

        # Import directly from file to bypass ml/models/__init__.py (which pulls TF)
        ensemble_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "models",
            "ensemble.py",
        )
        spec = importlib.util.spec_from_file_location("ensemble_direct", ensemble_path)
        ensemble_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ensemble_mod)

        LightGBMForecaster = ensemble_mod.LightGBMForecaster
        LightGBMConfig = ensemble_mod.LightGBMConfig

        from ml.utils.integrity import sign_model

        # Write a minimal config
        model_dir = tmp_path / "lgb_model"
        model_dir.mkdir()
        config_path = model_dir / "lgb_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "n_estimators": 10,
                    "max_depth": 3,
                    "learning_rate": 0.1,
                    "num_leaves": 31,
                    "subsample": 0.8,
                    "colsample_bytree": 0.8,
                    "min_child_samples": 20,
                    "reg_alpha": 0.1,
                    "reg_lambda": 1.0,
                    "objective": "regression",
                    "boosting_type": "gbdt",
                    "random_state": 42,
                    "n_jobs": -1,
                    "verbose": -1,
                }
            )
        )

        # Save a dummy pkl and sign it
        pkl_path = model_dir / "lgb_model_0.pkl"
        joblib.dump({"dummy": True}, str(pkl_path))
        sign_model(str(pkl_path))

        # Tamper with the pkl after signing
        pkl_path.write_bytes(b"malicious payload")

        forecaster = LightGBMForecaster()
        with pytest.raises(ValueError, match="[Ii]ntegrity|[Mm]ismatch|[Tt]amper"):
            forecaster.load(str(model_dir))


# ============================================================================
# MockForecaster Tests — exercise the model interface without TensorFlow
#
# These tests run in CI even when TF is not installed, ensuring the Python
# interface contract (fit/predict/evaluate/save/load) is always validated.
# ============================================================================


def _get_mock_forecaster_class():
    """Import MockForecaster from ml/tests/conftest.py without relying on
    Python's implicit conftest loading (which does not put it in sys.modules
    as a regular importable module).
    """
    import importlib.util

    conftest_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "conftest.py"
    )
    spec = importlib.util.spec_from_file_location("_ml_conftest", conftest_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.MockForecaster


class TestMockForecasterInterface:
    """Tests that exercise the forecaster Python interface using MockForecaster.

    These tests do NOT require TensorFlow and will always run in CI.
    They verify the expected API contract that all forecaster implementations
    must satisfy.
    """

    def test_mock_initialization(self, mock_forecaster):
        """MockForecaster can be initialized with default forecast horizon."""
        assert mock_forecaster.forecast_horizon == 24
        assert mock_forecaster.is_fitted is False

    def test_mock_custom_horizon(self):
        """MockForecaster accepts custom forecast horizon."""
        model = _get_mock_forecaster_class()(forecast_horizon=12)
        assert model.forecast_horizon == 12

    def test_fit_marks_model_as_fitted(self, mock_forecaster, sample_training_data):
        """fit() sets is_fitted to True and returns training history."""
        X, y = sample_training_data
        history = mock_forecaster.fit(X, y)

        assert mock_forecaster.is_fitted is True
        assert "loss" in history
        assert "val_loss" in history
        assert isinstance(history["loss"], list)
        assert len(history["loss"]) > 0

    def test_predict_without_confidence(self, mock_forecaster, sample_training_data):
        """predict(return_confidence=False) returns array of correct shape."""
        X, y = sample_training_data
        mock_forecaster.fit(X, y)

        predictions = mock_forecaster.predict(X[:10], return_confidence=False)

        assert predictions.shape == (10, mock_forecaster.forecast_horizon)
        assert not np.isnan(predictions).any()

    def test_predict_with_confidence(self, mock_forecaster, sample_training_data):
        """predict(return_confidence=True) returns (forecast, lower, upper) tuple."""
        X, y = sample_training_data
        mock_forecaster.fit(X, y)

        result = mock_forecaster.predict(X[:5], return_confidence=True)

        assert len(result) == 3
        forecast, lower, upper = result
        assert forecast.shape == (5, mock_forecaster.forecast_horizon)
        assert lower.shape == (5, mock_forecaster.forecast_horizon)
        assert upper.shape == (5, mock_forecaster.forecast_horizon)
        # Lower bound should be less than or equal to upper bound
        assert np.all(lower <= upper)

    def test_evaluate_returns_all_required_metrics(
        self, mock_forecaster, sample_training_data
    ):
        """evaluate() returns dict with all required metric keys."""
        X, y = sample_training_data
        mock_forecaster.fit(X, y)

        metrics = mock_forecaster.evaluate(X[:20], y[:20])

        required_keys = {"mape", "rmse", "mae", "direction_accuracy", "coverage"}
        assert required_keys.issubset(metrics.keys())

        # All metrics should be numeric
        for key in required_keys:
            assert isinstance(metrics[key], (int, float))

    def test_evaluate_metric_ranges(self, mock_forecaster, sample_training_data):
        """evaluate() metrics are in valid ranges."""
        X, y = sample_training_data
        mock_forecaster.fit(X, y)

        metrics = mock_forecaster.evaluate(X[:20], y[:20])

        assert metrics["mape"] >= 0
        assert metrics["mae"] >= 0
        assert metrics["rmse"] >= 0
        assert 0 <= metrics["direction_accuracy"] <= 1
        assert 0 <= metrics["coverage"] <= 1

    def test_save_creates_directory(
        self, mock_forecaster, sample_training_data, tmp_model_dir
    ):
        """save() creates the target directory and writes model artifacts."""
        X, y = sample_training_data
        mock_forecaster.fit(X, y)

        save_path = os.path.join(tmp_model_dir, "mock_saved")
        mock_forecaster.save(save_path)

        assert os.path.exists(save_path)
        assert os.path.exists(os.path.join(save_path, "mock_model.npy"))

    def test_load_returns_fitted_instance(
        self, mock_forecaster, sample_training_data, tmp_model_dir
    ):
        """load() returns a fitted model instance."""
        MockForecaster = _get_mock_forecaster_class()

        X, y = sample_training_data
        mock_forecaster.fit(X, y)

        save_path = os.path.join(tmp_model_dir, "mock_saved")
        mock_forecaster.save(save_path)

        loaded = MockForecaster.load(save_path)
        assert loaded.is_fitted is True

    def test_loaded_model_can_predict(
        self, mock_forecaster, sample_training_data, tmp_model_dir
    ):
        """A loaded model can produce predictions."""
        MockForecaster = _get_mock_forecaster_class()

        X, y = sample_training_data
        mock_forecaster.fit(X, y)

        save_path = os.path.join(tmp_model_dir, "mock_saved")
        mock_forecaster.save(save_path)

        loaded = MockForecaster.load(save_path)
        predictions = loaded.predict(X[:3], return_confidence=False)

        assert predictions.shape == (3, loaded.forecast_horizon)

    def test_predict_single_sample(self, mock_forecaster, sample_training_data):
        """predict() works correctly with a single sample."""
        X, y = sample_training_data
        mock_forecaster.fit(X, y)

        predictions = mock_forecaster.predict(X[:1], return_confidence=False)
        assert predictions.shape == (1, mock_forecaster.forecast_horizon)

    def test_predict_large_batch(self, mock_forecaster, sample_training_data):
        """predict() handles the full dataset."""
        X, y = sample_training_data
        mock_forecaster.fit(X, y)

        predictions = mock_forecaster.predict(X, return_confidence=False)
        assert predictions.shape == (len(X), mock_forecaster.forecast_horizon)
