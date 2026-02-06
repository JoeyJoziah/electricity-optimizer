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

# Lazy imports to handle missing dependencies gracefully
__all__ = []

# Feature Engineering (no TensorFlow required)
try:
    from .data.feature_engineering import (
        ElectricityPriceFeatureEngine,
        create_dummy_data,
    )
    __all__.extend(['ElectricityPriceFeatureEngine', 'create_dummy_data'])
except ImportError:
    pass

# Optimization (no TensorFlow required)
try:
    from .optimization.switching_decision import (
        SupplierSwitchingEngine,
        Tariff,
        TariffType,
        ConsumptionProfile,
        SwitchingRecommendation,
    )
    __all__.extend([
        'SupplierSwitchingEngine',
        'Tariff',
        'TariffType',
        'ConsumptionProfile',
        'SwitchingRecommendation',
    ])
except ImportError:
    pass

# Models (require TensorFlow)
try:
    from .models import (
        ElectricityPriceForecaster,
        EnsembleForecaster,
    )
    __all__.extend(['ElectricityPriceForecaster', 'EnsembleForecaster'])
except ImportError:
    pass

# Try XGBoost/LightGBM
try:
    from .models.ensemble import (
        XGBoostForecaster,
        LightGBMForecaster,
    )
    __all__.extend(['XGBoostForecaster', 'LightGBMForecaster'])
except ImportError:
    pass

# Training (require TensorFlow)
try:
    from .training import (
        TrainingConfig,
        ModelTrainer,
        train_model,
    )
    __all__.extend(['TrainingConfig', 'ModelTrainer', 'train_model'])
except ImportError:
    pass

# Evaluation
try:
    from .evaluation import (
        BacktestConfig,
        BacktestResult,
        ModelBacktester,
        run_backtest,
    )
    __all__.extend(['BacktestConfig', 'BacktestResult', 'ModelBacktester', 'run_backtest'])
except ImportError:
    pass
