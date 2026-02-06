"""
Machine Learning Package for Electricity Price Forecasting

This package provides production-ready ML models for 24-hour electricity
price forecasting with the following components:

Models:
- CNN-LSTM with attention mechanism for temporal pattern capture
- Ensemble combining deep learning with gradient boosting (XGBoost, LightGBM)

Feature Engineering:
- Temporal features (hour, day, month, holidays)
- Lag features and rolling statistics
- Weather feature processing
- Seasonal decomposition

Training:
- Walk-forward validation
- Early stopping and learning rate scheduling
- Model checkpointing

Evaluation:
- Comprehensive backtesting framework
- Multiple metrics (MAPE, RMSE, MAE, direction accuracy)
- Confidence interval coverage analysis

Target Performance:
- MAPE < 10%
- Inference < 1 second for 24-hour forecast
"""

__version__ = "1.0.0"

from .models import (
    ElectricityPriceForecaster,
    EnsembleForecaster,
    XGBoostForecaster,
    LightGBMForecaster,
)

from .data.feature_engineering import (
    ElectricityPriceFeatureEngine,
    create_dummy_data,
)

from .training import (
    TrainingConfig,
    ModelTrainer,
    train_model,
)

from .evaluation import (
    BacktestConfig,
    BacktestResult,
    ModelBacktester,
    run_backtest,
)

__all__ = [
    # Models
    'ElectricityPriceForecaster',
    'EnsembleForecaster',
    'XGBoostForecaster',
    'LightGBMForecaster',

    # Feature Engineering
    'ElectricityPriceFeatureEngine',
    'create_dummy_data',

    # Training
    'TrainingConfig',
    'ModelTrainer',
    'train_model',

    # Evaluation
    'BacktestConfig',
    'BacktestResult',
    'ModelBacktester',
    'run_backtest',
]
