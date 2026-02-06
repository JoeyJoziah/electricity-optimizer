"""
Pytest Configuration and Fixtures for ML Pipeline Tests

Provides shared fixtures for:
- Sample data generation
- Model configurations
- Feature engineering setup
- Mock models for fast testing
"""

import pytest
import numpy as np
import pandas as pd
from typing import Tuple, Optional
from datetime import datetime, timedelta
import os
import tempfile
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# Data Fixtures
# ============================================================================


@pytest.fixture
def sample_price_data() -> pd.DataFrame:
    """
    Generate sample electricity price time series data.

    Returns DataFrame with:
    - DateTimeIndex (hourly frequency)
    - 'price' column with realistic patterns
    - 2000 hours (83 days) to allow for sequence creation
    """
    np.random.seed(42)
    n_hours = 2000  # 83 days - enough for backtesting

    dates = pd.date_range(
        start='2024-01-01',
        periods=n_hours,
        freq='h'  # Use lowercase 'h' to avoid deprecation warning
    )

    hours = np.arange(n_hours)

    # Daily pattern (higher during day)
    daily_pattern = 20 * np.sin(2 * np.pi * (hours % 24 - 6) / 24)

    # Weekly pattern (lower on weekends)
    weekly_pattern = 5 * np.sin(2 * np.pi * (hours % 168) / 168)

    # Noise
    noise = np.random.normal(0, 5, n_hours)

    # Combined price (base 50)
    price = 50 + daily_pattern + weekly_pattern + noise
    price = np.maximum(price, 5)  # Minimum price

    return pd.DataFrame({'price': price}, index=dates)


@pytest.fixture
def extended_price_data() -> pd.DataFrame:
    """
    Generate extended price data for backtesting.
    6 months (4320 hours) of data.
    """
    np.random.seed(42)
    n_hours = 4320  # 6 months

    dates = pd.date_range(
        start='2024-01-01',
        periods=n_hours,
        freq='H'
    )

    hours = np.arange(n_hours)

    # Daily pattern
    daily_pattern = 20 * np.sin(2 * np.pi * (hours % 24 - 6) / 24)

    # Weekly pattern
    weekly_pattern = 10 * np.sin(2 * np.pi * (hours % 168) / 168)

    # Seasonal pattern
    seasonal_pattern = 15 * np.cos(2 * np.pi * hours / 8760)

    # Trend
    trend = 0.001 * hours

    # Noise
    noise = np.random.normal(0, 8, n_hours)

    # Combined price
    price = 50 + daily_pattern + weekly_pattern + seasonal_pattern + trend + noise
    price = np.maximum(price, 1)

    return pd.DataFrame({'price': price}, index=dates)


@pytest.fixture
def sample_training_data() -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate sample training data for model tests.

    Returns:
        X: (100, 168, 10) - 100 samples, 168 lookback, 10 features
        y: (100, 24) - 100 samples, 24-hour forecast
    """
    np.random.seed(42)
    n_samples = 100
    lookback = 168
    features = 10
    forecast = 24

    X = np.random.randn(n_samples, lookback, features).astype(np.float32)
    y = np.random.randn(n_samples, forecast).astype(np.float32) * 10 + 50

    return X, y


@pytest.fixture
def large_training_data() -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate larger training data for performance tests.

    Returns:
        X: (1000, 168, 15) - 1000 samples
        y: (1000, 24) - 24-hour forecast
    """
    np.random.seed(42)
    n_samples = 1000
    lookback = 168
    features = 15
    forecast = 24

    X = np.random.randn(n_samples, lookback, features).astype(np.float32)
    y = np.random.randn(n_samples, forecast).astype(np.float32) * 10 + 50

    return X, y


# ============================================================================
# Model Configuration Fixtures
# ============================================================================


@pytest.fixture
def minimal_model_config():
    """Minimal model configuration for fast testing."""
    try:
        from ml.models.price_forecaster import ModelConfig
        return ModelConfig(
            sequence_length=168,
            num_features=10,
            forecast_horizon=24,
            cnn_filters=[16, 32, 16],
            lstm_units=[32, 16],
            dense_units=[16, 8],
            epochs=2,
            batch_size=16,
            use_attention=False  # Faster without attention
        )
    except ImportError:
        pytest.skip("TensorFlow not installed")


@pytest.fixture
def full_model_config():
    """Full model configuration for accuracy tests."""
    try:
        from ml.models.price_forecaster import ModelConfig
        return ModelConfig(
            sequence_length=168,
            num_features=15,
            forecast_horizon=24,
            cnn_filters=[64, 128, 64],
            lstm_units=[128, 64],
            dense_units=[64, 32],
            epochs=50,
            batch_size=32,
            use_attention=True
        )
    except ImportError:
        pytest.skip("TensorFlow not installed")


# ============================================================================
# Feature Engineering Fixtures
# ============================================================================


@pytest.fixture
def feature_engine():
    """Create feature engineering pipeline."""
    try:
        from ml.data.feature_engineering import ElectricityPriceFeatureEngine
    except ImportError:
        from data.feature_engineering import ElectricityPriceFeatureEngine

    return ElectricityPriceFeatureEngine(
        country='UK',
        lookback_hours=168,
        forecast_hours=24
    )


@pytest.fixture
def feature_engine_de():
    """Create feature engineering pipeline for Germany."""
    try:
        from ml.data.feature_engineering import ElectricityPriceFeatureEngine
    except ImportError:
        from data.feature_engineering import ElectricityPriceFeatureEngine

    return ElectricityPriceFeatureEngine(
        country='DE',
        lookback_hours=168,
        forecast_hours=24
    )


# ============================================================================
# Mock Model Fixtures
# ============================================================================


class MockForecaster:
    """Mock forecaster for testing without TensorFlow."""

    def __init__(self, forecast_horizon: int = 24):
        self.forecast_horizon = forecast_horizon
        self.is_fitted = False

    def fit(self, X, y, **kwargs):
        self.is_fitted = True
        return {'loss': [0.1, 0.08, 0.06], 'val_loss': [0.12, 0.1, 0.08]}

    def predict(self, X, return_confidence: bool = True):
        n_samples = len(X)
        predictions = np.random.randn(n_samples, self.forecast_horizon) * 10 + 50

        if return_confidence:
            lower = predictions - 5
            upper = predictions + 5
            return predictions, lower, upper
        return predictions

    def evaluate(self, X, y):
        return {
            'mape': 8.5,
            'rmse': 4.2,
            'mae': 3.1,
            'direction_accuracy': 0.65,
            'coverage': 0.92
        }

    def save(self, path):
        os.makedirs(path, exist_ok=True)
        np.save(os.path.join(path, 'mock_model.npy'), np.array([1]))

    @classmethod
    def load(cls, path):
        instance = cls()
        instance.is_fitted = True
        return instance


@pytest.fixture
def mock_forecaster():
    """Create mock forecaster."""
    return MockForecaster()


# ============================================================================
# Temporary Directory Fixtures
# ============================================================================


@pytest.fixture
def tmp_model_dir(tmp_path):
    """Create temporary directory for model storage."""
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    return str(model_dir)


@pytest.fixture
def tmp_results_dir(tmp_path):
    """Create temporary directory for results."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    return str(results_dir)


# ============================================================================
# Price Profile Fixtures (for optimization tests)
# ============================================================================


@pytest.fixture
def flat_prices() -> np.ndarray:
    """Flat electricity prices (96 slots = 24 hours at 15-min intervals)."""
    return np.full(96, 0.15)


@pytest.fixture
def tou_prices() -> np.ndarray:
    """Time-of-use prices with peak from 4-9 PM."""
    prices = np.full(96, 0.10)  # Off-peak
    prices[64:84] = 0.35  # Peak (4-9 PM)
    return prices


@pytest.fixture
def volatile_prices() -> np.ndarray:
    """Volatile real-time prices."""
    np.random.seed(42)
    base = np.full(96, 0.12)

    # Daily pattern
    hours = np.arange(96) / 4
    pattern = 0.08 * np.sin(2 * np.pi * (hours - 6) / 24)

    # Volatility
    noise = np.random.randn(96) * 0.05

    prices = base + pattern + noise
    return np.maximum(prices, 0.01)


# ============================================================================
# Appliance Fixtures (for optimization tests)
# ============================================================================


@pytest.fixture
def sample_appliances():
    """Sample appliances for optimization tests."""
    try:
        from ml.optimization.appliance_models import Appliance, ApplianceType

        return [
            Appliance(
                name="Dishwasher",
                appliance_type=ApplianceType.DISHWASHER,
                earliest_start=18,
                latest_end=8
            ),
            Appliance(
                name="EV Charger",
                appliance_type=ApplianceType.EV_CHARGER,
                earliest_start=21,
                latest_end=7
            ),
            Appliance(
                name="Washing Machine",
                appliance_type=ApplianceType.WASHING_MACHINE,
                earliest_start=8,
                latest_end=20
            )
        ]
    except ImportError:
        pytest.skip("Appliance models not available")


# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "gpu: marks tests that require GPU"
    )
    config.addinivalue_line(
        "markers", "requires_tf: marks tests that require TensorFlow"
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests based on available dependencies."""
    skip_tf = pytest.mark.skip(reason="TensorFlow not installed")
    skip_gpu = pytest.mark.skip(reason="GPU not available")

    try:
        import tensorflow as tf
        has_tf = True
        has_gpu = len(tf.config.list_physical_devices('GPU')) > 0
    except ImportError:
        has_tf = False
        has_gpu = False

    for item in items:
        if "requires_tf" in item.keywords and not has_tf:
            item.add_marker(skip_tf)
        if "gpu" in item.keywords and not has_gpu:
            item.add_marker(skip_gpu)
