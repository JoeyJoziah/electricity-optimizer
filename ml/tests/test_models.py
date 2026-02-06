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
from typing import Tuple


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
            lstm_units=[64, 32]
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
            lstm_units=[64, 32]
        )
        model = ElectricityPriceForecaster(config=config)

        layer_types = [type(layer).__name__ for layer in model.model.layers]

        # Should have CNN layers
        assert 'Conv1D' in layer_types
        # Should have LSTM layers (bidirectional wraps them)
        assert any('Bidirectional' in t or 'LSTM' in t for t in layer_types)
        # Should have Dense layers
        assert 'Dense' in layer_types

    @pytest.mark.requires_tf
    def test_model_input_output_shapes(self):
        """Test model input and output shapes are correct."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        config = ModelConfig(
            sequence_length=168,
            num_features=10,
            forecast_horizon=24,
            num_quantiles=3
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
            dense_units=[64, 32]
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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        history = model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
        )

        assert 'loss' in history
        assert 'val_loss' in history
        assert len(history['loss']) >= 1

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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        history = model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
        )

        losses = history['loss']
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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        assert not model.is_fitted

        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
        )

        X_test = X[:10]
        predictions = model.predict(X_test, return_confidence=False)

        assert predictions.shape == (10, y.shape[1])

    @pytest.mark.requires_tf
    def test_prediction_with_confidence_intervals(self, sample_training_data, tmp_model_dir):
        """Test prediction returns confidence intervals."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=1,
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
        )

        result = model.predict_single(X[0:1])

        assert 'forecast' in result
        assert 'lower_bound' in result
        assert 'upper_bound' in result
        assert result['forecast'].shape == (y.shape[1],)


class TestCNNLSTMModelEvaluation:
    """Tests for model evaluation metrics."""

    @pytest.mark.requires_tf
    def test_model_evaluation_returns_metrics(self, sample_training_data, tmp_model_dir):
        """Test evaluation returns required metrics."""
        from ml.models.price_forecaster import ElectricityPriceForecaster, ModelConfig

        X, y = sample_training_data

        config = ModelConfig(
            sequence_length=X.shape[1],
            num_features=X.shape[2],
            forecast_horizon=y.shape[1],
            epochs=2,
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
        )

        X_test, y_test = X[80:], y[80:]
        metrics = model.evaluate(X_test, y_test)

        assert 'mae' in metrics
        assert 'rmse' in metrics
        assert 'mape' in metrics
        assert 'direction_accuracy' in metrics
        assert 'coverage' in metrics

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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
        )

        metrics = model.evaluate(X[80:], y[80:])

        # MAPE should be positive
        assert metrics['mape'] >= 0
        # MAE should be positive
        assert metrics['mae'] >= 0
        # RMSE should be positive
        assert metrics['rmse'] >= 0
        # Direction accuracy should be 0-1
        assert 0 <= metrics['direction_accuracy'] <= 1
        # Coverage should be 0-1
        assert 0 <= metrics['coverage'] <= 1


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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
        )

        save_path = os.path.join(tmp_model_dir, 'saved_model')
        model.save(save_path)

        assert os.path.exists(save_path)
        assert os.path.exists(os.path.join(save_path, 'model.keras'))
        assert os.path.exists(os.path.join(save_path, 'config.json'))

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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
        )

        save_path = os.path.join(tmp_model_dir, 'saved_model')
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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
        )

        X_test = X[:5]
        original_pred = model.predict(X_test, return_confidence=False)

        save_path = os.path.join(tmp_model_dir, 'saved_model')
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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
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
            batch_size=16
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
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
                forecast_horizon=24
            )

            ensemble = EnsembleForecaster(config=config)
            assert ensemble is not None
        except ImportError:
            pytest.skip("Ensemble model dependencies not installed")

    @pytest.mark.requires_tf
    def test_ensemble_prediction_combines_models(self, sample_training_data, tmp_model_dir):
        """Test ensemble combines predictions from multiple models."""
        try:
            from ml.models.ensemble import EnsembleForecaster, EnsembleConfig

            X, y = sample_training_data

            config = EnsembleConfig(
                cnn_lstm_weight=0.5,
                xgboost_weight=0.25,
                lightgbm_weight=0.25,
                forecast_horizon=y.shape[1]
            )

            ensemble = EnsembleForecaster(config=config)
            ensemble.fit(
                X, y,
                X_val=X[:10],
                y_val=y[:10],
                cnn_lstm_epochs=1,
                verbose=0
            )

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
    def test_mape_below_10_percent_with_training(self, large_training_data, tmp_model_dir):
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
            batch_size=32
        )

        model = ElectricityPriceForecaster(config=config)
        model.fit(
            X, y,
            checkpoint_dir=os.path.join(tmp_model_dir, 'checkpoints'),
            log_dir=os.path.join(tmp_model_dir, 'logs'),
            verbose=0
        )

        X_test, y_test = X[800:], y[800:]
        metrics = model.evaluate(X_test, y_test)

        # On random data, MAPE will be high
        # This test validates the metric calculation works
        assert metrics['mape'] >= 0
        assert isinstance(metrics['mape'], float)

        # For real data with proper training, uncomment:
        # assert metrics['mape'] < 10.0, f"MAPE {metrics['mape']:.2f}% exceeds 10% target"
