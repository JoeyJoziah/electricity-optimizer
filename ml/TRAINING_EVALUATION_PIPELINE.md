# ML Training and Evaluation Pipeline

## Overview

Complete end-to-end pipeline for training, tuning, and evaluating electricity price forecasting models with production-grade tooling.

---

## Components

### 1. Model Training (`ml/training/`)

#### `train_forecaster.py` (563 lines)
- **TrainingConfig**: Dataclass for training configuration
- **ModelTrainer**: Main training orchestrator
- **load_training_data()**: Data loading with validation
- **prepare_datasets()**: Train/val/test splitting with temporal awareness
- **Features**:
  - Multi-GPU support
  - Automatic checkpointing
  - TensorBoard logging
  - Early stopping
  - Learning rate scheduling

**Usage**:
```python
from ml.training import ModelTrainer, TrainingConfig

config = TrainingConfig(
    lookback_hours=168,
    forecast_horizon=24,
    batch_size=32,
    learning_rate=0.001,
    n_epochs=100
)

trainer = ModelTrainer(config)
model, history = trainer.train()
```

#### `hyperparameter_tuning.py` (625 lines)
- **HyperparameterSpace**: Defines search space for optimization
- **HyperparameterTuner**: Multi-strategy tuning orchestrator
- **BayesianOptimizer**: Simplified Optuna wrapper
- **Tuning Strategies**:
  - **Grid Search**: Exhaustive parameter combinations
  - **Random Search**: Random sampling from distributions
  - **Bayesian Optimization**: Sequential model-based optimization (Optuna with TPE sampler)

**Hyperparameter Search Space**:
- CNN: filters [32, 64, 128], kernel_size [3, 5, 7], layers [1-3]
- LSTM: units [32-256], layers [1-3], dropout [0.0-0.3]
- Dense: units [16-64], layers [1-2], dropout [0.0-0.2]
- Training: learning_rate [0.0001-0.005], batch_size [16, 32, 64]
- Features: lookback_hours [72, 168, 336]

**Usage**:
```python
from ml.training import tune_price_forecaster, HyperparameterSpace

# Bayesian optimization with 50 trials
best_params, best_score = tune_price_forecaster(
    X_train, y_train,
    X_val, y_val,
    method='bayesian',
    n_trials=50
)

# Custom search space
custom_space = HyperparameterSpace(
    lstm_units=[64, 128, 256],
    learning_rate=[0.0001, 0.001],
    batch_size=[32, 64]
)

tuner = HyperparameterTuner(
    model_builder=build_model,
    search_space=custom_space,
    X_train=X_train,
    y_train=y_train,
    X_val=X_val,
    y_val=y_val
)

best_params, best_score = tuner.bayesian_optimization(n_trials=100)
```

**Optimization Features**:
- Optuna study persistence
- Trial pruning (MedianPruner)
- TPE sampler for efficient search
- Results saved as JSON
- Progress bar for monitoring

---

### 2. Model Evaluation (`ml/evaluation/`)

#### `metrics.py` (625 lines)
Comprehensive forecast evaluation metrics with business impact analysis.

**Point Forecast Metrics**:
- **MAE** (Mean Absolute Error): Average prediction error
- **RMSE** (Root Mean Squared Error): Penalizes large errors
- **MAPE** (Mean Absolute Percentage Error): Percentage error
- **sMAPE** (Symmetric MAPE): Robust to near-zero values
- **R²** (Coefficient of Determination): Variance explained

**Directional Metrics**:
- **Direction Accuracy**: % correct up/down predictions
- **Weighted Direction Accuracy**: Weighted by magnitude of change

**Probabilistic Metrics** (with prediction intervals):
- **Coverage**: % of actuals within prediction intervals (90%, 95%)
- **Interval Score**: Gneiting-Raftery scoring rule (lower = better)

**Business Metrics**:
- **Cost of Prediction Error**: Financial cost (GBP/USD) due to forecast errors
- **Optimization Savings Impact**: % reduction in optimization savings

**Usage**:
```python
from ml.evaluation import evaluate_forecast, compare_models

# Single model evaluation
metrics = evaluate_forecast(
    y_true=actuals,
    y_pred=predictions,
    y_lower=lower_bounds,  # optional
    y_upper=upper_bounds,  # optional
    verbose=True  # prints detailed report
)

print(f"MAPE: {metrics.mape:.2f}%")
print(f"Direction Accuracy: {metrics.direction_accuracy:.2f}%")
print(f"Savings Impact: {metrics.optimization_savings_impact:.2f}%")

# Multi-model comparison
predictions = {
    'CNN-LSTM': cnn_lstm_preds,
    'XGBoost': xgb_preds,
    'ARIMA': arima_preds
}

comparison_df = compare_models(y_true, predictions, metric='mape')
print(comparison_df)
#      model    mae   rmse   mape  smape    r2  dir_acc  weighted_dir_acc
# 0  CNN-LSTM  0.015  0.021   5.2    5.1  0.92     78.3              82.1
# 1   XGBoost  0.018  0.024   6.1    5.9  0.89     73.5              76.8
# 2     ARIMA  0.022  0.029   7.8    7.5  0.84     68.2              71.3
```

#### `backtesting.py` (721 lines)
Historical validation with walk-forward testing.

**Features**:
- Walk-forward backtesting with expanding/rolling windows
- Multiple forecast horizons (1h, 6h, 12h, 24h)
- Automatic retraining at specified intervals
- Performance tracking over time
- Degradation detection

**Usage**:
```python
from ml.evaluation import ModelBacktester, BacktestConfig

config = BacktestConfig(
    start_date='2024-01-01',
    end_date='2024-12-31',
    window_type='expanding',  # or 'rolling'
    initial_training_days=365,
    forecast_horizons=[1, 6, 12, 24],
    retrain_frequency='weekly'
)

backtester = ModelBacktester(config)
results = backtester.run(model, data)

# Analyze results
print(f"Overall MAPE: {results.overall_mape:.2f}%")
print(f"Best Period: {results.best_period}")
print(f"Worst Period: {results.worst_period}")

# Plot performance over time
backtester.plot_results(results)
```

---

## Training Workflow

### 1. Data Preparation
```python
from ml.data import ElectricityPriceFeatureEngine
from ml.training import load_training_data, prepare_datasets

# Load raw data
df = load_training_data('data/raw/electricity_prices.csv')

# Feature engineering (73 features)
feature_engine = ElectricityPriceFeatureEngine()
df_features = feature_engine.transform(df)

# Split datasets (temporal split)
X_train, y_train, X_val, y_val, X_test, y_test = prepare_datasets(
    df_features,
    lookback_hours=168,
    forecast_horizon=24,
    val_ratio=0.15,
    test_ratio=0.15
)
```

### 2. Hyperparameter Tuning
```python
from ml.training import tune_price_forecaster

# Run Bayesian optimization
best_params, best_score = tune_price_forecaster(
    X_train, y_train,
    X_val, y_val,
    method='bayesian',
    n_trials=100
)

print(f"Best MAPE: {best_score:.2f}%")
print(f"Best params: {best_params}")
```

### 3. Model Training
```python
from ml.training import ModelTrainer, TrainingConfig

# Configure with best hyperparameters
config = TrainingConfig(
    **best_params,
    n_epochs=200,
    early_stopping_patience=20,
    checkpoint_dir='models/checkpoints'
)

# Train model
trainer = ModelTrainer(config)
model, history = trainer.train()

# Save model
trainer.save_model('models/cnn_lstm_best.h5')
```

### 4. Model Evaluation
```python
from ml.evaluation import evaluate_forecast, calculate_all_metrics

# Generate predictions on test set
y_pred = model.predict(X_test)

# Comprehensive evaluation
metrics = evaluate_forecast(
    y_true=y_test,
    y_pred=y_pred,
    verbose=True
)

# Check if model meets target (MAPE < 10%)
if metrics.mape < 10.0:
    print("✅ Model meets accuracy target!")
else:
    print(f"❌ MAPE {metrics.mape:.2f}% exceeds target of 10%")
```

### 5. Backtesting
```python
from ml.evaluation import ModelBacktester, BacktestConfig

# Historical validation
config = BacktestConfig(
    start_date='2024-01-01',
    end_date='2024-12-31',
    window_type='expanding',
    retrain_frequency='weekly'
)

backtester = ModelBacktester(config)
backtest_results = backtester.run(model, historical_data)

# Verify stability over time
if backtest_results.overall_mape < 10.0:
    print("✅ Model maintains accuracy over time!")
```

---

## Production Deployment Pipeline

### Complete End-to-End Flow

```
1. Data Collection (Airflow)
   └─> electricity_price_ingestion.py (every 15 min)
        ├─> Fetch from Flatpeak, NREL, IEA
        ├─> Aggregate & clean
        └─> Store in TimescaleDB

2. Feature Engineering
   └─> ElectricityPriceFeatureEngine.transform()
        └─> Generate 73 features

3. Model Training (Weekly/Monthly)
   └─> model_retraining.py (Airflow DAG)
        ├─> Load latest 2 years data
        ├─> Hyperparameter tuning (50 trials)
        ├─> Train best model
        ├─> Backtest validation
        └─> Deploy if MAPE < 10%

4. Real-time Inference
   └─> predictions.py (FastAPI)
        ├─> /predict/price → 24h forecast
        ├─> /predict/optimal-times → Best scheduling
        └─> /predict/savings → Cost estimation

5. Performance Monitoring
   └─> forecast_accuracy.py (Airflow DAG)
        ├─> Compare forecasts vs actuals
        ├─> Calculate MAPE, MAE, RMSE
        ├─> Alert if degradation detected
        └─> Trigger retraining if needed
```

---

## Performance Targets

### Accuracy Metrics
- **MAPE**: < 10% (primary target)
- **Direction Accuracy**: > 70%
- **R² Score**: > 0.85

### Business Metrics
- **Optimization Savings**: 15%+ vs immediate execution
- **Forecast Horizon**: 24 hours ahead
- **Update Frequency**: Every 15 minutes

### Infrastructure
- **Training Time**: < 2 hours (on GPU)
- **Inference Latency**: < 100ms (p95)
- **Model Size**: < 50MB

---

## Results

### Phase 3 Deliverables ✅

**Training Pipeline**:
- ✅ train_forecaster.py (563 lines) - Complete training orchestration
- ✅ hyperparameter_tuning.py (625 lines) - Multi-strategy optimization
- ✅ cnn_lstm_trainer.py (487 lines) - Specialized CNN-LSTM trainer

**Evaluation Pipeline**:
- ✅ metrics.py (625 lines) - 13 comprehensive metrics
- ✅ backtesting.py (721 lines) - Historical validation framework

**Total Code**: 3,021 lines across 5 modules

### Key Features Implemented
1. **Hyperparameter Optimization**
   - Grid Search (exhaustive)
   - Random Search (efficient sampling)
   - Bayesian Optimization (Optuna with TPE)
   - Automatic trial pruning

2. **Comprehensive Metrics**
   - Point forecast: MAE, RMSE, MAPE, sMAPE, R²
   - Directional: Direction accuracy (weighted)
   - Probabilistic: Coverage, Interval score
   - Business: Cost of error, Savings impact

3. **Production-Grade Training**
   - Multi-GPU support
   - Automatic checkpointing
   - TensorBoard integration
   - Early stopping & LR scheduling

4. **Robust Validation**
   - Walk-forward backtesting
   - Expanding/rolling windows
   - Multiple forecast horizons
   - Performance tracking

---

## Next Steps (Phase 4+)

### Immediate Priorities
1. **Integration Testing**: Test full pipeline end-to-end with real data
2. **Model Registry**: MLflow model versioning and deployment
3. **A/B Testing**: Compare CNN-LSTM vs XGBoost vs ensemble
4. **Monitoring Dashboard**: Real-time accuracy tracking

### Future Enhancements
- **AutoML**: Neural architecture search (NAS)
- **Ensemble Methods**: Weighted combination of models
- **Transfer Learning**: Pre-trained models for new regions
- **Explainability**: SHAP values for feature importance

---

## Dependencies

Added to `ml/requirements-ml.txt`:
```
# Hyperparameter Optimization
optuna>=3.5.0
```

Already included:
- tensorflow>=2.15.0 (model training)
- scikit-learn>=1.4.0 (metrics, splitting)
- numpy, pandas (data processing)
- mlflow>=2.9.0 (experiment tracking)

---

**Status**: ✅ **TASK #13 COMPLETED**
**Commit**: e5d76e6 - "Complete Phase 3 training and evaluation pipeline"
**Total Files**: 33 files changed, 12,138 insertions
**Phase 3**: **100% COMPLETE** 🎉
