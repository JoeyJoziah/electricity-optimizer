# ML Module — RateShift Price Prediction

The ML module powers electricity price forecasting and optimization for RateShift. It combines multiple machine learning models using ensemble techniques to provide accurate price predictions and optimal scheduling recommendations.

## Overview

The ML pipeline predicts electricity prices 24 hours in advance across multiple regions, enabling users to shift loads to cheaper time windows and minimize bills. The module is organized into modular, testable components with comprehensive training, evaluation, and inference workflows.

## Architecture

### Core Components

**Ensemble Predictor** (`inference/ensemble_predictor.py`)
- Combines three model types for improved accuracy and robustness
- CNN-LSTM captures complex temporal patterns (50% weight)
- XGBoost captures feature interactions (25% weight)
- LightGBM provides gradient boosting signal (25% weight)
- Configurable weights via Redis, PostgreSQL, or metadata files
- Provides uncertainty quantification and confidence intervals

**Price Forecaster** (`models/price_forecaster.py`)
- CNN-LSTM deep learning model for time series forecasting
- Input: 7-day historical prices + 73 engineered features
- Output: 24-hour price forecast with directional accuracy

**Feature Engineering** (`data/feature_engineering.py`)
- 73 features spanning temporal, cyclical, and domain patterns
- Temporal: hour, day of week, day of month, month of year
- Cyclical: sine/cosine encoding for periodic patterns
- Domain: price volatility, moving averages, seasonal indices
- Custom normalization for electricity market data

**Training Pipeline** (`training/`)
- Multi-strategy hyperparameter tuning (grid, random, Bayesian)
- Automatic model checkpointing and early stopping
- TensorBoard integration for training visualization
- Multi-GPU support for faster training

**Evaluation Framework** (`evaluation/`)
- 13 comprehensive metrics: MAE, RMSE, MAPE, sMAPE, R², direction accuracy
- Backtesting with walk-forward validation
- Expanding and rolling window strategies
- Business impact metrics: savings potential, cost of errors

**Optimization Engine** (`optimization/`)
- Load shifting scheduler: MILP optimization for appliance scheduling
- Constraint management: appliance operating hours, user preferences
- Visualization: Plotly-based load shifting graphs
- Switching decision logic: buy/hold/sell signals

## Data Flow

```
Price Data (EIA, NREL) → Price Sync Service
                ↓
        Feature Engineering (73 features)
                ↓
        Training Data (Train/Val/Test split)
                ↓
    ┌─ CNN-LSTM Model ─┐
    ├─ XGBoost Model ──┤ → Ensemble Predictor
    └─ LightGBM Model ─┘
                ↓
    Nightly Retraining (GHA cron, weekly)
                ↓
        Production Models (stored in S3 or local)
                ↓
        Real-time Inference (/predict/price endpoint)
                ↓
    Load Shifting Optimization → User Recommendations
```

## Testing

611 tests total, covering models, optimization, training, and inference:

```bash
# Run all ML tests
.venv/bin/python -m pytest ml/

# Run specific test module
.venv/bin/python -m pytest ml/tests/test_models.py

# Run with coverage
.venv/bin/python -m pytest ml/ --cov=ml --cov-report=term-missing

# Run specific test
.venv/bin/python -m pytest ml/tests/test_models.py::TestEnsemblePredictor::test_predict
```

Test modules:
- `test_forecaster.py`: Price forecaster model
- `test_models.py`: Ensemble model components
- `test_optimization.py`: Load shifting optimization
- `test_backtesting.py`: Backtesting validation
- `test_training.py`: Training pipeline
- `test_hyperparameter_tuning.py`: Hyperparameter optimization
- `test_feature_engineering.py`: Feature engineering
- `test_metrics.py`: Evaluation metrics
- `test_inference.py`: Inference pipeline
- `test_load_shifter.py`: Load shifter engine

## Configuration

**Model Config** (`config/model_config.yaml`)
- Model weights (CNN-LSTM, XGBoost, LightGBM ratios)
- Training hyperparameters
- Forecasting horizon (default: 24 hours)
- Lookback window (default: 7 days / 168 hours)

**Environment Variables**
- `ML_MODELS_PATH`: Location of trained models (default: `ml/models/`)
- `REDIS_URL`: Redis URL for dynamic weight loading
- `DATABASE_URL`: PostgreSQL connection for model_config table

**Dependencies** (`requirements.txt`)
- Core: numpy, pandas, scipy, scikit-learn
- Deep Learning: tensorflow, keras, torch
- Boosting: xgboost, lightgbm
- Optimization: pulp (MILP solver)
- Time Series: statsmodels, prophet
- Utilities: pydantic, tqdm, joblib

## Training Pipeline

Nightly retraining runs every Sunday at 5am UTC via GitHub Actions:

1. Load latest 2 years of historical price data
2. Engineer 73 features for each sample
3. Hyperparameter tuning: 50-100 Bayesian trials
4. Train ensemble with best hyperparameters
5. Backtest on historical period (walk-forward)
6. Validate MAPE < 10% (primary success metric)
7. Deploy if validation passes, alert if fails

See `TRAINING_EVALUATION_PIPELINE.md` for detailed workflow.

## Key Patterns

**Model Versioning**: Each trained ensemble is versioned with timestamp and metrics. A/B testing framework uses SHA-256 deterministic hashing to assign users to model variants for production validation.

**Adaptive Learning**: Model weights adjust nightly based on recent forecast accuracy. Learning service updates Redis with new weights, picked up by ensemble predictor on next inference.

**Confidence Intervals**: Ensemble provides uncertainty quantification using Z-scores for confidence levels (80%-99%). Used to construct prediction intervals around point forecasts.

**Feature Normalization**: Custom normalization per region accounts for different price scales and seasonal patterns across utility territories.

## Performance Targets

- **MAPE**: < 10% (primary target)
- **Direction Accuracy**: > 70% (predict up/down correctly)
- **R² Score**: > 0.85
- **Inference Latency**: < 100ms (p95)
- **Model Size**: < 50MB total

## File Structure

```
ml/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── config/
│   └── model_config.yaml        # Model configuration
├── models/
│   ├── ensemble.py              # Ensemble model class
│   ├── price_forecaster.py      # CNN-LSTM forecaster
│   └── __init__.py
├── inference/
│   ├── ensemble_predictor.py    # Production ensemble predictor
│   ├── predictor.py             # Base predictor class
│   └── __init__.py
├── training/
│   ├── train_forecaster.py      # Training orchestrator
│   ├── hyperparameter_tuning.py # Bayesian optimization
│   ├── cnn_lstm_trainer.py      # CNN-LSTM specialist
│   └── __init__.py
├── evaluation/
│   ├── metrics.py               # 13 evaluation metrics
│   ├── backtesting.py           # Walk-forward validation
│   └── __init__.py
├── optimization/
│   ├── load_shifter.py          # MILP load shifting
│   ├── scheduler.py             # Scheduling engine
│   ├── appliance_models.py      # Appliance constraints
│   ├── constraints.py           # Optimization constraints
│   ├── objective.py             # Objective functions
│   ├── switching_decision.py    # Buy/hold/sell signals
│   ├── visualization.py         # Plotly graphs
│   └── __init__.py
├── data/
│   ├── feature_engineering.py   # 73-feature generator
│   └── __init__.py
└── tests/
    ├── conftest.py              # Test fixtures
    ├── test_forecaster.py
    ├── test_models.py
    ├── test_optimization.py
    ├── test_backtesting.py
    ├── test_training.py
    ├── test_hyperparameter_tuning.py
    ├── test_feature_engineering.py
    ├── test_metrics.py
    ├── test_inference.py
    └── test_load_shifter.py
```

## Quick Start

```python
from ml.inference import EnsemblePredictor
from ml.data import ElectricityPriceFeatureEngine

# Load ensemble model
ensemble = EnsemblePredictor("/path/to/ensemble/models")

# Prepare features
feature_engine = ElectricityPriceFeatureEngine()
features_df = feature_engine.transform(historical_prices_df)

# Get forecast with confidence intervals
forecast = ensemble.predict(
    features_df,
    horizon=24,
    confidence_level=0.9,
    return_components=True
)

# Results include point forecast + upper/lower bounds
print(f"Price forecast: ${forecast['point']:.2f}/MWh")
print(f"95% confidence interval: ${forecast['lower']:.2f} - ${forecast['upper']:.2f}")
```

## References

- Training/evaluation details: `TRAINING_EVALUATION_PIPELINE.md`
- Optimization details: `optimization/README.md`
- Architecture decision: `.dsp/uid_map.json` (DSP codebase graph)
