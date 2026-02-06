"""
CNN-LSTM Price Forecasting Model with Attention Mechanism

This module implements a production-ready deep learning model for
24-hour electricity price forecasting. The architecture combines:
- CNN layers for extracting local patterns from time series
- LSTM layers for capturing temporal dependencies
- Multi-head attention for focusing on relevant time periods
- Dense layers for final prediction with confidence intervals

Target: MAPE < 10%
Inference: < 1 second for 24-hour forecast
"""

import os
import json
import logging
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import numpy as np

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, Model, regularizers
from tensorflow.keras.callbacks import (
    EarlyStopping,
    ModelCheckpoint,
    ReduceLROnPlateau,
    TensorBoard,
    Callback
)
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.losses import Loss

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for the CNN-LSTM model."""

    # Model name and version
    name: str = "electricity_price_forecaster"
    version: str = "1.0.0"

    # Input configuration
    sequence_length: int = 168  # 7 days of hourly data
    num_features: int = 15      # Number of input features

    # Output configuration
    forecast_horizon: int = 24  # 24-hour ahead forecast
    num_quantiles: int = 3      # point estimate, lower, upper bounds
    confidence_level: float = 0.9  # 90% confidence interval

    # CNN configuration
    cnn_filters: List[int] = None
    cnn_kernel_sizes: List[int] = None
    cnn_pooling_size: int = 2
    cnn_activation: str = "relu"
    use_batch_norm: bool = True

    # LSTM configuration
    lstm_units: List[int] = None
    lstm_dropout: float = 0.2
    lstm_recurrent_dropout: float = 0.1

    # Attention configuration
    use_attention: bool = True
    attention_heads: int = 4
    attention_key_dim: int = 32
    attention_dropout: float = 0.1

    # Dense configuration
    dense_units: List[int] = None
    dense_activation: str = "relu"
    dense_dropout: float = 0.3

    # Regularization
    l2_weight: float = 0.0001

    # Training configuration
    learning_rate: float = 0.001
    batch_size: int = 32
    epochs: int = 200

    def __post_init__(self):
        """Set default values for list fields."""
        if self.cnn_filters is None:
            self.cnn_filters = [64, 128, 64]
        if self.cnn_kernel_sizes is None:
            self.cnn_kernel_sizes = [3, 5, 3]
        if self.lstm_units is None:
            self.lstm_units = [128, 64]
        if self.dense_units is None:
            self.dense_units = [64, 32]


class AttentionLayer(layers.Layer):
    """
    Custom attention layer for time series.

    Implements scaled dot-product attention to allow the model
    to focus on the most relevant time steps for prediction.
    """

    def __init__(
        self,
        num_heads: int = 4,
        key_dim: int = 32,
        dropout: float = 0.1,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.num_heads = num_heads
        self.key_dim = key_dim
        self.dropout_rate = dropout

    def build(self, input_shape):
        self.attention = layers.MultiHeadAttention(
            num_heads=self.num_heads,
            key_dim=self.key_dim,
            dropout=self.dropout_rate
        )
        self.layer_norm = layers.LayerNormalization()
        self.dropout = layers.Dropout(self.dropout_rate)

    def call(self, inputs, training=None):
        # Self-attention with residual connection
        attention_output = self.attention(inputs, inputs, training=training)
        attention_output = self.dropout(attention_output, training=training)
        output = self.layer_norm(inputs + attention_output)
        return output

    def get_config(self):
        config = super().get_config()
        config.update({
            'num_heads': self.num_heads,
            'key_dim': self.key_dim,
            'dropout': self.dropout_rate
        })
        return config


class QuantileLoss(Loss):
    """
    Quantile loss function for probabilistic forecasting.

    This loss function enables the model to predict confidence intervals
    by training on multiple quantiles (e.g., 0.05, 0.5, 0.95).
    """

    def __init__(self, quantiles: List[float] = None, **kwargs):
        super().__init__(**kwargs)
        self.quantiles = quantiles or [0.05, 0.5, 0.95]

    def call(self, y_true, y_pred):
        """
        Compute quantile loss.

        Args:
            y_true: True values, shape (batch, forecast_horizon)
            y_pred: Predicted quantiles, shape (batch, forecast_horizon, num_quantiles)
        """
        losses = []

        # Reshape y_true to match y_pred dimensions
        y_true_expanded = tf.expand_dims(y_true, axis=-1)

        for i, q in enumerate(self.quantiles):
            pred_q = y_pred[:, :, i:i+1]
            error = y_true_expanded - pred_q
            loss_q = tf.maximum(q * error, (q - 1) * error)
            losses.append(loss_q)

        total_loss = tf.reduce_mean(tf.concat(losses, axis=-1))
        return total_loss


class MAPECallback(Callback):
    """Callback to compute MAPE on validation set during training."""

    def __init__(self, validation_data: Tuple[np.ndarray, np.ndarray]):
        super().__init__()
        self.X_val = validation_data[0]
        self.y_val = validation_data[1]

    def on_epoch_end(self, epoch, logs=None):
        logs = logs or {}

        # Get predictions (median quantile)
        y_pred = self.model.predict(self.X_val, verbose=0)

        # If output has multiple quantiles, take the median (index 1)
        if len(y_pred.shape) == 3 and y_pred.shape[-1] > 1:
            y_pred = y_pred[:, :, 1]

        # Compute MAPE
        mape = np.mean(np.abs((self.y_val - y_pred) / (self.y_val + 1e-8))) * 100
        logs['val_mape'] = mape

        if epoch % 10 == 0:
            logger.info(f"Epoch {epoch}: MAPE = {mape:.2f}%")


def create_cnn_lstm_model(config: ModelConfig) -> Model:
    """
    Create CNN-LSTM model with attention mechanism.

    Architecture:
    1. Input layer: (batch, sequence_length, num_features)
    2. CNN blocks: Conv1D -> BatchNorm -> ReLU -> MaxPool
    3. Attention layer: Multi-head self-attention
    4. LSTM layers: Bidirectional LSTMs with dropout
    5. Dense layers: Fully connected with dropout
    6. Output layer: (batch, forecast_horizon, num_quantiles)

    Args:
        config: ModelConfig with architecture parameters

    Returns:
        Compiled Keras model
    """
    # Input layer
    inputs = layers.Input(
        shape=(config.sequence_length, config.num_features),
        name='input'
    )

    x = inputs

    # CNN Blocks
    for i, (filters, kernel_size) in enumerate(zip(
        config.cnn_filters, config.cnn_kernel_sizes
    )):
        x = layers.Conv1D(
            filters=filters,
            kernel_size=kernel_size,
            padding='same',
            kernel_regularizer=regularizers.l2(config.l2_weight),
            name=f'conv1d_{i}'
        )(x)

        if config.use_batch_norm:
            x = layers.BatchNormalization(name=f'bn_{i}')(x)

        x = layers.Activation(config.cnn_activation, name=f'activation_{i}')(x)

        # Pool every other layer
        if i % 2 == 1:
            x = layers.MaxPooling1D(
                pool_size=config.cnn_pooling_size,
                name=f'maxpool_{i}'
            )(x)

    # Attention Layer
    if config.use_attention:
        x = AttentionLayer(
            num_heads=config.attention_heads,
            key_dim=config.attention_key_dim,
            dropout=config.attention_dropout,
            name='attention'
        )(x)

    # LSTM Layers
    for i, units in enumerate(config.lstm_units):
        return_sequences = (i < len(config.lstm_units) - 1)

        x = layers.Bidirectional(
            layers.LSTM(
                units=units,
                return_sequences=return_sequences,
                dropout=config.lstm_dropout,
                recurrent_dropout=config.lstm_recurrent_dropout,
                kernel_regularizer=regularizers.l2(config.l2_weight),
            ),
            name=f'bilstm_{i}'
        )(x)

    # Dense Layers
    for i, units in enumerate(config.dense_units):
        x = layers.Dense(
            units,
            activation=config.dense_activation,
            kernel_regularizer=regularizers.l2(config.l2_weight),
            name=f'dense_{i}'
        )(x)
        x = layers.Dropout(config.dense_dropout, name=f'dropout_{i}')(x)

    # Output Layer - produces forecast_horizon x num_quantiles
    # First expand to full forecast horizon
    x = layers.Dense(
        config.forecast_horizon * config.num_quantiles,
        kernel_regularizer=regularizers.l2(config.l2_weight),
        name='output_dense'
    )(x)

    # Reshape to (batch, forecast_horizon, num_quantiles)
    outputs = layers.Reshape(
        (config.forecast_horizon, config.num_quantiles),
        name='output'
    )(x)

    # Create model
    model = Model(inputs=inputs, outputs=outputs, name=config.name)

    return model


class ElectricityPriceForecaster:
    """
    Main forecasting class that wraps the CNN-LSTM model.

    Provides high-level methods for:
    - Training with configurable callbacks
    - Prediction with confidence intervals
    - Model saving/loading
    - Performance evaluation
    """

    def __init__(
        self,
        config: ModelConfig = None,
        model_path: Optional[str] = None
    ):
        """
        Initialize the forecaster.

        Args:
            config: Model configuration (if training new model)
            model_path: Path to load existing model (if inferencing)
        """
        self.config = config or ModelConfig()
        self.model = None
        self.history = None
        self.is_fitted = False

        if model_path:
            self.load(model_path)
        else:
            self._build_model()

    def _build_model(self):
        """Build the CNN-LSTM model."""
        logger.info("Building CNN-LSTM model...")

        self.model = create_cnn_lstm_model(self.config)

        # Compile with quantile loss
        quantiles = [
            (1 - self.config.confidence_level) / 2,  # Lower bound
            0.5,  # Median
            (1 + self.config.confidence_level) / 2   # Upper bound
        ]

        self.model.compile(
            optimizer=Adam(learning_rate=self.config.learning_rate),
            loss=QuantileLoss(quantiles=quantiles),
            metrics=['mae']
        )

        logger.info(f"Model built with {self.model.count_params():,} parameters")
        self.model.summary(print_fn=logger.info)

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        checkpoint_dir: str = 'checkpoints',
        log_dir: str = 'logs',
        verbose: int = 1
    ) -> Dict:
        """
        Train the model.

        Args:
            X_train: Training features, shape (samples, sequence_length, features)
            y_train: Training targets, shape (samples, forecast_horizon)
            X_val: Validation features (optional, will split from train if not provided)
            y_val: Validation targets
            checkpoint_dir: Directory for model checkpoints
            log_dir: Directory for TensorBoard logs
            verbose: Verbosity level

        Returns:
            Dictionary with training history
        """
        logger.info(f"Training model on {len(X_train)} samples...")

        # Create directories
        os.makedirs(checkpoint_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)

        # Prepare validation data
        if X_val is None:
            # Split from training data
            split_idx = int(len(X_train) * 0.85)
            X_val = X_train[split_idx:]
            y_val = y_train[split_idx:]
            X_train = X_train[:split_idx]
            y_train = y_train[:split_idx]

        # Setup callbacks
        callbacks = [
            EarlyStopping(
                monitor='val_loss',
                patience=20,
                restore_best_weights=True,
                verbose=1
            ),
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=10,
                min_lr=1e-6,
                verbose=1
            ),
            ModelCheckpoint(
                filepath=os.path.join(checkpoint_dir, 'best_model.keras'),
                monitor='val_loss',
                save_best_only=True,
                verbose=1
            ),
            TensorBoard(
                log_dir=log_dir,
                histogram_freq=1
            ),
            MAPECallback(validation_data=(X_val, y_val))
        ]

        # Train
        self.history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=self.config.epochs,
            batch_size=self.config.batch_size,
            callbacks=callbacks,
            verbose=verbose
        )

        self.is_fitted = True
        logger.info("Training completed")

        # Return training history
        return {
            'loss': self.history.history['loss'],
            'val_loss': self.history.history['val_loss'],
            'mae': self.history.history['mae'],
            'val_mae': self.history.history['val_mae']
        }

    def predict(
        self,
        X: np.ndarray,
        return_confidence: bool = True
    ) -> Union[np.ndarray, Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """
        Generate predictions with optional confidence intervals.

        Args:
            X: Input features, shape (samples, sequence_length, features)
            return_confidence: Whether to return confidence bounds

        Returns:
            If return_confidence=False: predictions array (samples, forecast_horizon)
            If return_confidence=True: (predictions, lower_bound, upper_bound)
        """
        if not self.is_fitted and self.model is None:
            raise RuntimeError("Model must be fitted or loaded before prediction")

        # Get predictions - shape (samples, forecast_horizon, num_quantiles)
        predictions = self.model.predict(X, verbose=0)

        if return_confidence:
            lower_bound = predictions[:, :, 0]
            point_forecast = predictions[:, :, 1]
            upper_bound = predictions[:, :, 2]
            return point_forecast, lower_bound, upper_bound
        else:
            return predictions[:, :, 1]  # Return median forecast

    def predict_single(
        self,
        X: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        Generate single prediction with full metadata.

        Args:
            X: Input features, shape (1, sequence_length, features)

        Returns:
            Dictionary with forecast, confidence bounds, and metadata
        """
        if X.shape[0] != 1:
            X = X[:1]

        forecast, lower, upper = self.predict(X, return_confidence=True)

        return {
            'forecast': forecast[0],
            'lower_bound': lower[0],
            'upper_bound': upper[0],
            'confidence_level': self.config.confidence_level,
            'forecast_horizon': self.config.forecast_horizon
        }

    def evaluate(
        self,
        X_test: np.ndarray,
        y_test: np.ndarray
    ) -> Dict[str, float]:
        """
        Evaluate model performance.

        Args:
            X_test: Test features
            y_test: Test targets

        Returns:
            Dictionary with evaluation metrics
        """
        predictions, lower, upper = self.predict(X_test, return_confidence=True)

        # Compute metrics
        mae = np.mean(np.abs(y_test - predictions))
        rmse = np.sqrt(np.mean((y_test - predictions) ** 2))
        mape = np.mean(np.abs((y_test - predictions) / (y_test + 1e-8))) * 100

        # Direction accuracy
        if y_test.shape[1] > 1:
            actual_direction = np.sign(y_test[:, 1:] - y_test[:, :-1])
            pred_direction = np.sign(predictions[:, 1:] - predictions[:, :-1])
            direction_accuracy = np.mean(actual_direction == pred_direction)
        else:
            direction_accuracy = 0.0

        # Coverage of confidence intervals
        in_interval = (y_test >= lower) & (y_test <= upper)
        coverage = np.mean(in_interval)

        metrics = {
            'mae': float(mae),
            'rmse': float(rmse),
            'mape': float(mape),
            'direction_accuracy': float(direction_accuracy),
            'coverage': float(coverage),
            'expected_coverage': float(self.config.confidence_level)
        }

        logger.info(f"Evaluation results: MAPE={mape:.2f}%, MAE={mae:.4f}, RMSE={rmse:.4f}")

        return metrics

    def save(self, path: str):
        """
        Save model and configuration.

        Args:
            path: Directory path to save model
        """
        os.makedirs(path, exist_ok=True)

        # Save model
        model_path = os.path.join(path, 'model.keras')
        self.model.save(model_path)

        # Save config
        config_path = os.path.join(path, 'config.json')
        with open(config_path, 'w') as f:
            json.dump(asdict(self.config), f, indent=2)

        logger.info(f"Model saved to {path}")

    def load(self, path: str):
        """
        Load model and configuration.

        Args:
            path: Directory path to load model from
        """
        # Load config
        config_path = os.path.join(path, 'config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config_dict = json.load(f)
            self.config = ModelConfig(**config_dict)

        # Load model
        model_path = os.path.join(path, 'model.keras')
        custom_objects = {
            'AttentionLayer': AttentionLayer,
            'QuantileLoss': QuantileLoss
        }
        self.model = keras.models.load_model(
            model_path,
            custom_objects=custom_objects
        )

        self.is_fitted = True
        logger.info(f"Model loaded from {path}")

    def get_inference_time(self, X: np.ndarray, num_runs: int = 100) -> float:
        """
        Benchmark inference time.

        Args:
            X: Sample input
            num_runs: Number of runs for averaging

        Returns:
            Average inference time in milliseconds
        """
        import time

        # Warm-up
        _ = self.model.predict(X[:1], verbose=0)

        # Benchmark
        times = []
        for _ in range(num_runs):
            start = time.perf_counter()
            _ = self.model.predict(X[:1], verbose=0)
            times.append((time.perf_counter() - start) * 1000)

        avg_time = np.mean(times)
        logger.info(f"Average inference time: {avg_time:.2f}ms")

        return avg_time


def test_model():
    """Test the model with dummy data."""
    print("Testing CNN-LSTM Price Forecaster...")

    # Create dummy data
    np.random.seed(42)
    n_samples = 1000
    sequence_length = 168
    num_features = 15
    forecast_horizon = 24

    X = np.random.randn(n_samples, sequence_length, num_features)
    y = np.random.randn(n_samples, forecast_horizon) * 10 + 50  # Prices around 50

    # Split data
    train_size = int(0.8 * n_samples)
    X_train, X_test = X[:train_size], X[train_size:]
    y_train, y_test = y[:train_size], y[train_size:]

    # Create model
    config = ModelConfig(
        sequence_length=sequence_length,
        num_features=num_features,
        forecast_horizon=forecast_horizon,
        epochs=5,  # Quick test
        batch_size=32
    )

    forecaster = ElectricityPriceForecaster(config=config)

    # Train
    print("\nTraining model...")
    history = forecaster.fit(
        X_train, y_train,
        checkpoint_dir='/tmp/checkpoints',
        log_dir='/tmp/logs',
        verbose=1
    )

    # Evaluate
    print("\nEvaluating model...")
    metrics = forecaster.evaluate(X_test, y_test)
    print(f"Test metrics: {metrics}")

    # Predict single sample
    print("\nSingle prediction:")
    result = forecaster.predict_single(X_test[:1])
    print(f"Forecast shape: {result['forecast'].shape}")
    print(f"Confidence level: {result['confidence_level']}")

    # Benchmark inference time
    print("\nBenchmarking inference time...")
    inference_time = forecaster.get_inference_time(X_test, num_runs=50)
    print(f"Inference time: {inference_time:.2f}ms")

    # Save and reload
    print("\nTesting save/load...")
    forecaster.save('/tmp/test_model')

    # Load model
    loaded_forecaster = ElectricityPriceForecaster(model_path='/tmp/test_model')
    loaded_metrics = loaded_forecaster.evaluate(X_test, y_test)
    print(f"Loaded model metrics: {loaded_metrics}")

    print("\nAll tests passed!")
    return forecaster


if __name__ == "__main__":
    test_model()
