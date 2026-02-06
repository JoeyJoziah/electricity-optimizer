"""
ML Models for Electricity Price Forecasting

This package contains:
- CNN-LSTM model with attention mechanism
- Ensemble model combining deep learning with gradient boosting
- Model utilities and custom layers
"""

from .price_forecaster import (
    ElectricityPriceForecaster,
    AttentionLayer,
    QuantileLoss,
    create_cnn_lstm_model,
)

from .ensemble import (
    EnsembleForecaster,
    XGBoostForecaster,
    LightGBMForecaster,
)

__all__ = [
    'ElectricityPriceForecaster',
    'AttentionLayer',
    'QuantileLoss',
    'create_cnn_lstm_model',
    'EnsembleForecaster',
    'XGBoostForecaster',
    'LightGBMForecaster',
]
