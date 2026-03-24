# Audit 13: ML Pipeline

**Auditor**: Claude Opus 4.6 (inline)
**Date**: 2026-03-19
**Scope**: All Python files in `ml/` and subdirectories (44 files: 26 source, 18 test)
**Method**: Full manual read of every file, line-by-line analysis
**Status**: COMPLETE

---

## Executive Summary

The ML pipeline implements an ensemble electricity price forecasting system (CNN-LSTM + XGBoost + LightGBM) with MILP-based appliance scheduling optimization, split conformal prediction for confidence intervals, walk-forward backtesting, and Bayesian hyperparameter tuning. The codebase is generally well-structured with good separation of concerns. However, the audit uncovered 4 P0 critical issues including a model serialization incompatibility that will crash at runtime, 8 P1 high-severity issues including data leakage and unprotected deserialization, 11 P2 medium issues, and 7 P3 low issues.

Test coverage is solid (611 tests) with well-written tests for the optimization, scheduling, and inference subsystems. The `test_ml_fixes.py` file demonstrates that the data leakage, MIMO, and conformal prediction issues were identified and fixed -- however some of the underlying root causes in the training code remain partially unaddressed. The most critical concern is the torch.save/torch.load incompatibility between the trainer and predictor modules, which will produce a silent runtime failure in production.

---

## Files Reviewed

### Source Files (26)

| File | Lines | Purpose |
|------|-------|---------|
| `ml/__init__.py` | ~40 | Package root, lazy imports, version |
| `ml/models/__init__.py` | ~20 | Models subpackage exports |
| `ml/models/price_forecaster.py` | ~550 | CNN-LSTM with attention (TensorFlow/Keras) |
| `ml/models/ensemble.py` | ~560 | XGBoost + LightGBM + ensemble orchestration |
| `ml/data/__init__.py` | ~10 | Data subpackage |
| `ml/data/feature_engineering.py` | ~560 | Feature pipeline (temporal, lag, rolling, seasonal) |
| `ml/training/__init__.py` | ~30 | Training subpackage exports |
| `ml/training/train_forecaster.py` | ~600 | ModelTrainer orchestrating full pipeline |
| `ml/training/cnn_lstm_trainer.py` | ~470 | PyTorch CNN-LSTM trainer |
| `ml/training/hyperparameter_tuning.py` | ~550 | Optuna-based HP tuning |
| `ml/inference/predictor.py` | ~400 | PricePredictor with conformal calibration |
| `ml/inference/ensemble_predictor.py` | ~350 | EnsemblePredictor combining models |
| `ml/evaluation/__init__.py` | ~10 | Evaluation subpackage |
| `ml/evaluation/metrics.py` | ~460 | MAE, RMSE, MAPE, sMAPE, interval score |
| `ml/evaluation/backtesting.py` | ~350 | Walk-forward backtesting |
| `ml/optimization/__init__.py` | ~20 | Optimization subpackage |
| `ml/optimization/appliance_models.py` | ~300 | Data models (Appliance, PriceProfile, etc.) |
| `ml/optimization/constraints.py` | ~250 | MILP constraint builder |
| `ml/optimization/objective.py` | ~280 | Multi-objective builder |
| `ml/optimization/load_shifter.py` | ~350 | MILP optimizer core |
| `ml/optimization/scheduler.py` | ~400 | High-level ApplianceScheduler API |
| `ml/optimization/switching_decision.py` | ~320 | Supplier switching engine |
| `ml/optimization/visualization.py` | ~380 | Schedule visualization |

### Test Files (18)

| File | Tests | Coverage Area |
|------|-------|---------------|
| `ml/tests/conftest.py` | - | Fixtures, marks, global config |
| `ml/tests/test_backtesting.py` | ~30 | Walk-forward validation |
| `ml/tests/test_cnn_lstm_trainer.py` | ~20 | PyTorch trainer (mocked torch) |
| `ml/tests/test_feature_engineering.py` | ~25 | Feature pipeline |
| `ml/tests/test_hyperparameter_tuning.py` | ~15 | HP space, tuner, Bayesian wrapper |
| `ml/tests/test_inference.py` | ~45 | PricePredictor + EnsemblePredictor |
| `ml/tests/test_load_shifter.py` | ~35 | MILP optimizer unit tests |
| `ml/tests/test_metrics.py` | ~40 | All metric functions |
| `ml/tests/test_milp_standalone.py` | ~10 | Standalone optimization script |
| `ml/tests/test_ml_fixes.py` | ~30 | Data leakage, MIMO, conformal fixes |
| `ml/tests/test_models.py` | ~25 | CNN-LSTM model (requires TF) |
| `ml/tests/test_optimization.py` | ~30 | Integration: optimization pipeline |
| `ml/tests/test_predictor.py` | ~50 | PricePredictor exhaustive tests |
| `ml/tests/test_scheduler.py` | ~40 | ApplianceScheduler API |
| `ml/tests/test_switching_decision.py` | ~30 | Supplier switching engine |
| `ml/tests/test_train_forecaster.py` | ~25 | ModelTrainer (mocked models) |
| `ml/tests/test_training.py` | ~20 | Training (requires TF) |
| `ml/tests/test_visualization.py` | ~25 | Schedule visualizer |

---

## P0 -- Critical (Must Fix Before Next Deployment)

### P0-1: torch.save/torch.load Serialization Incompatibility

**File**: `ml/training/cnn_lstm_trainer.py` line ~430; `ml/inference/predictor.py` line ~178
**Category**: Model Loading Safety

The CNN-LSTM trainer saves the **full model object** using `torch.save(self.model, path)`, which serializes via Python's `pickle` module. However, the predictor loads with `torch.load(model_file, map_location="cpu", weights_only=True)`.

The `weights_only=True` parameter (added in PyTorch 2.0 for security) restricts deserialization to tensor data only and **rejects full model objects**. This means any model trained by `CNNLSTMTrainer.save()` will fail to load in `PricePredictor._load_model()` with an `UnpicklingError`.

```python
# cnn_lstm_trainer.py line ~430 -- SAVES full model (pickle)
torch.save(self.model, model_path)

# predictor.py line ~178 -- LOADS with weights_only=True (rejects pickle)
model = torch.load(model_file, map_location="cpu", weights_only=True)
```

**Impact**: Complete inference failure for any CNN-LSTM model trained by the pipeline. This is a silent incompatibility -- no error occurs at training time, only at inference time.

**Fix**: Change the trainer to save only state_dict:
```python
# In CNNLSTMTrainer.save():
torch.save(self.model.state_dict(), model_path)

# In PricePredictor._load_model():
model = CNNLSTMModel(...)  # reconstruct architecture
model.load_state_dict(torch.load(model_file, map_location="cpu", weights_only=True))
```

This requires persisting the model architecture config alongside the weights (e.g., in `metadata.yaml`).

---

### P0-2: Unsafe Pickle Deserialization with Bypassable Hash Verification

**File**: `ml/inference/ensemble_predictor.py` lines ~136-200; `ml/inference/predictor.py` line ~200
**Category**: Model Loading Safety

Both predictor modules use `joblib.load()` (which uses pickle) to load scaler files. The ensemble predictor has a `_verify_model_hash()` method that checks SHA-256 hashes, but it **returns True when no hash file exists**:

```python
def _verify_model_hash(self, model_path):
    hash_file = os.path.join(model_path, "model.sha256")
    if not os.path.exists(hash_file):
        return True  # No hash to verify -- PASSES by default
```

This means an attacker who replaces `scaler.pkl` with a malicious pickle payload can achieve arbitrary code execution on the inference server, since no hash file needs to be present.

**Impact**: Remote code execution if an attacker can write to the model directory (e.g., via path traversal, compromised model registry, or supply chain attack).

**Fix**:
1. Change `_verify_model_hash()` to return `False` (or raise) when no hash file exists.
2. Generate and store hash files during training.
3. Consider using `safetensors` or ONNX format instead of pickle-based serialization for scalers.
4. At minimum, log a critical warning when loading without hash verification.

---

### P0-3: Deprecated Optuna API Will Crash on Optuna v4+

**File**: `ml/training/hyperparameter_tuning.py` lines ~92-93
**Category**: Runtime Failure

The `to_optuna_space()` method in `HyperparameterSpace` uses `trial.suggest_loguniform()`, which was deprecated in Optuna v3 and **removed in Optuna v4**:

```python
"learning_rate": trial.suggest_loguniform(
    "learning_rate", min(self.learning_rate), max(self.learning_rate)
),
```

The project's `pyproject.toml` does not pin Optuna to v3.x, so any `pip install --upgrade` will break this code.

**Impact**: `AttributeError` at runtime when running hyperparameter tuning with Optuna v4+.

**Fix**: Replace with `trial.suggest_float(..., log=True)`:
```python
"learning_rate": trial.suggest_float(
    "learning_rate", min(self.learning_rate), max(self.learning_rate), log=True
),
```

---

### P0-4: Broken Import -- `build_model_from_params` Does Not Exist

**File**: `ml/training/hyperparameter_tuning.py` line ~517
**Category**: Runtime Failure

The `tune_price_forecaster()` convenience function imports a function that does not exist in the target module:

```python
from models.price_forecaster import build_model_from_params
```

No function named `build_model_from_params` exists in `ml/models/price_forecaster.py`. The module defines `ElectricityPriceForecaster`, `ModelConfig`, `AttentionLayer`, and `QuantileLoss` -- but no `build_model_from_params`.

Additionally, the import uses a bare `models.` prefix rather than `ml.models.`, which would also fail in a standard package installation.

**Impact**: `ImportError` crash when calling `tune_price_forecaster()`. This function is exported from `ml/training/__init__.py` and is part of the public API.

**Fix**: Either implement `build_model_from_params()` in `price_forecaster.py`, or refactor `tune_price_forecaster()` to use the existing `ElectricityPriceForecaster` class constructor with a `ModelConfig`.

---

## P1 -- High (Should Fix This Sprint)

### P1-1: Data Leakage in CNNLSTMTrainer.prepare_sequences()

**File**: `ml/training/cnn_lstm_trainer.py` lines ~87-88
**Category**: Data Preprocessing Bug

The `prepare_sequences()` method fits the scaler on the **entire dataset** before creating the train/test split:

```python
self.scaler = StandardScaler()
scaled_data = self.scaler.fit_transform(data)  # Fits on ALL data
# ... then splits into train/test
```

This leaks test set statistics (mean, variance) into the training data, inflating validation metrics and giving a falsely optimistic view of model performance.

**Note**: The `ModelTrainer` in `train_forecaster.py` correctly implements a split-first pipeline (verified by `test_ml_fixes.py::TestNoDataLeakageScaler`), but `CNNLSTMTrainer` remains unfixed. If `CNNLSTMTrainer` is used directly (bypassing `ModelTrainer`), data leakage occurs.

**Impact**: Overly optimistic validation metrics; model may underperform in production compared to backtesting results.

**Fix**: Split data first, fit scaler on training split only, then transform both splits:
```python
train_data = data[:n_train]
test_data = data[n_train:]
self.scaler = StandardScaler()
scaled_train = self.scaler.fit_transform(train_data)
scaled_test = self.scaler.transform(test_data)
```

---

### P1-2: Shuffle=True on Time Series DataLoader

**File**: `ml/training/cnn_lstm_trainer.py` line ~304
**Category**: Data Preprocessing Bug

The training DataLoader uses `shuffle=True`:

```python
train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
```

For time series data, shuffling destroys temporal ordering within batches. While individual sequences maintain their internal ordering, shuffled batch composition can reduce the effectiveness of batch normalization layers and prevent the model from learning inter-sequence temporal patterns.

**Impact**: Suboptimal training dynamics for temporal models; may reduce forecast accuracy.

**Fix**: Use `shuffle=False` for time series DataLoaders.

---

### P1-3: LightGBM Type Mismatch on Model Reload

**File**: `ml/models/ensemble.py` lines ~363-365
**Category**: Model Loading Safety

The `LightGBMForecaster.load()` method loads a model using `lgb.Booster(model_file=path)`, which returns a `Booster` object. However, `LightGBMForecaster.train()` stores the model as an `LGBMRegressor` (scikit-learn API wrapper). The `predict()` method may call `.predict()` on either type, but the signatures differ:

```python
# load() returns Booster
model = lgb.Booster(model_file=model_path)

# train() stores LGBMRegressor
self.model = lgb.LGBMRegressor(**params)
self.model.fit(X_train, y_train, ...)
```

`Booster.predict()` expects a numpy array and returns raw predictions. `LGBMRegressor.predict()` accepts the same but may apply different post-processing. More critically, if any code checks `isinstance(self.model, lgb.LGBMRegressor)`, it will fail after loading.

**Impact**: Potential silent prediction differences between freshly trained and reloaded models.

**Fix**: Use `LGBMRegressor` for loading:
```python
model = lgb.LGBMRegressor()
model.booster_ = lgb.Booster(model_file=model_path)
```
Or save using `model.booster_.save_model()` and load with `lgb.Booster()` consistently.

---

### P1-4: Global Random Seed Pollution

**File**: `ml/data/feature_engineering.py` line ~539; `ml/tests/conftest.py` lines ~15-20
**Category**: Reproducibility

The `create_dummy_data()` function in the feature engineering module calls `np.random.seed(42)`, which sets the **global** NumPy random state. This affects all subsequent random operations in the process, not just the dummy data generation:

```python
def create_dummy_data(n_hours=8760, seed=42):
    np.random.seed(seed)  # Pollutes global state
```

The test `conftest.py` also sets `np.random.seed(42)` in fixtures, which can mask test isolation issues.

**Impact**: Non-reproducible results in multi-test runs; hidden test dependencies; production code that accidentally depends on a fixed seed.

**Fix**: Use `np.random.RandomState(seed)` or `np.random.default_rng(seed)` for local random state:
```python
def create_dummy_data(n_hours=8760, seed=42):
    rng = np.random.default_rng(seed)
    # Use rng.normal(), rng.uniform(), etc.
```

---

### P1-5: No Connection Pooling or Timeout for Synchronous DB Connections

**File**: `ml/inference/ensemble_predictor.py` lines ~136-191
**Category**: Inference Latency / Resource Leak

The `EnsemblePredictor` creates synchronous `psycopg2` database connections and Redis connections without connection pooling or timeout parameters:

```python
# psycopg2 connection -- no pool, no timeout
conn = psycopg2.connect(database_url)

# Redis connection -- no timeout
redis_client = redis.Redis.from_url(redis_url)
```

During inference (which is latency-critical), a slow or unresponsive database will block the prediction thread indefinitely. Without connection pooling, each prediction creates a new TCP connection.

**Impact**: Inference latency spikes; potential thread exhaustion under load; resource leaks if connections are not properly closed.

**Fix**: Add connection timeouts and use connection pooling:
```python
conn = psycopg2.connect(database_url, connect_timeout=5)
redis_client = redis.Redis.from_url(redis_url, socket_timeout=5, socket_connect_timeout=5)
```
Consider using `psycopg2.pool.ThreadedConnectionPool` for pooling.

---

### P1-6: MAPE Epsilon Too Small in Price Forecaster

**File**: `ml/models/price_forecaster.py` line ~195
**Category**: Numerical Instability

The MAPE calculation in `ElectricityPriceForecaster` uses an epsilon of `1e-8`:

```python
mape = np.mean(np.abs(y_true - y_pred) / (np.abs(y_true) + 1e-8)) * 100
```

For electricity prices near zero (which occur during off-peak hours in deregulated markets), `|y_true| + 1e-8` is essentially `1e-8`, producing MAPE values in the millions. This makes MAPE useless as a training metric during these periods.

By contrast, `ml/evaluation/metrics.py` line ~133 correctly handles this by masking zero values:

```python
mask = y_true != 0
mape = np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100
```

**Impact**: Misleading MAPE values during model evaluation; potential gradient instability if MAPE is used as a loss function.

**Fix**: Use the same masking approach as `metrics.py`, or use sMAPE which is bounded.

---

### P1-7: No Random Seed Management in Training Pipeline

**File**: `ml/training/train_forecaster.py` (entire file); `ml/training/cnn_lstm_trainer.py` (entire file)
**Category**: Reproducibility

Neither `ModelTrainer` nor `CNNLSTMTrainer` sets random seeds for NumPy, Python's `random` module, or PyTorch/TensorFlow at the start of training. This means:

1. Training runs are not reproducible
2. A/B comparisons between model configurations are confounded by randomness
3. Bug reproduction is harder

**Impact**: Inability to reproduce training results; unreliable model comparison.

**Fix**: Add a `seed` parameter to training configs and set all relevant seeds at the start of training:
```python
def _set_seeds(seed: int):
    np.random.seed(seed)
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    tf.random.set_seed(seed)
```

---

### P1-8: Fabricated Uncertainty Bounds in CNNLSTMTrainer

**File**: `ml/training/cnn_lstm_trainer.py` lines ~107-111
**Category**: Data Preprocessing Bug

When the model outputs only point predictions (2D output), the trainer creates fake lower/upper bounds as +/-10% of the point prediction:

```python
lower = point * 0.9
upper = point * 1.1
```

These bounds are not calibrated and do not represent real prediction uncertainty. They are passed downstream to the ensemble and will be treated as genuine confidence intervals.

**Note**: The `test_ml_fixes.py::TestConformalPredictionIntervals` tests verify that the conformal prediction system in `predictor.py` correctly replaces these fabricated bounds when calibrated. However, if the conformal calibration step is skipped (e.g., in a quick deployment), the fabricated bounds propagate to users.

**Impact**: Users receive false confidence intervals that do not reflect actual model uncertainty.

**Fix**: Either implement proper uncertainty quantification (MC Dropout, deep ensembles, or quantile regression), or clearly mark the fallback bounds as uncalibrated with a warning.

---

## P2 -- Medium (Should Fix This Quarter)

### P2-1: UInt32 Type from isocalendar().week

**File**: `ml/data/feature_engineering.py` line ~121
**Category**: Feature Engineering

`df.index.isocalendar().week` returns a `UInt32` Series (pandas nullable integer). Some downstream operations (StandardScaler, numpy concatenation) may not handle nullable integer types correctly, potentially causing silent type coercion or NaN introduction.

**Fix**: Cast explicitly: `df.index.isocalendar().week.astype(int)`

---

### P2-2: NaN Fill Before Scaler Fit Skews Statistics

**File**: `ml/data/feature_engineering.py` line ~379
**Category**: Feature Engineering

The feature engine fills NaN values with 0 before fitting the scaler. If a feature has many NaN values (e.g., lag features at the start of the time series), the zeros pull the mean toward zero and reduce the standard deviation, distorting the scaling.

**Fix**: Fill NaN after scaling, or use the scaler's built-in NaN handling, or fill with the column mean/median instead of 0.

---

### P2-3: ffill/bfill Can Leak Across Train/Test Boundary

**File**: `ml/data/feature_engineering.py` line ~428
**Category**: Data Leakage (Conditional)

The `transform()` method calls `df.ffill().bfill()` on the input DataFrame. If `transform()` is called on the full dataset (before splitting), forward-fill can propagate future values into the training window.

**Note**: `test_ml_fixes.py::TestNoDataLeakageScaler::test_ffill_does_not_propagate_across_split_boundary` verifies that per-split transformation prevents this. The risk exists only if someone calls `transform()` on the unsplit data.

**Fix**: Document that `transform()` must be called per-split, or add an assertion that the input length does not exceed the fitted training length.

---

### P2-4: Incorrect 90% CI Approximation in Metrics

**File**: `ml/evaluation/metrics.py` lines ~421-427
**Category**: Numerical Correctness

The `evaluate_forecast()` function approximates 90% confidence intervals by scaling 95% interval width by 0.9:

```python
lower_90 = point - (point - lower_95) * 0.9
upper_90 = point + (upper_95 - point) * 0.9
```

This is mathematically incorrect. For Gaussian distributions, the correct scaling factor is the ratio of z-scores: `1.645 / 1.960 = 0.839`, not 0.9. The current formula overestimates the 90% CI width by ~7%.

**Impact**: Overly conservative 90% interval scores; misleading coverage metrics.

**Fix**: Use `0.839` instead of `0.9`, or better yet, compute 90% intervals directly from the underlying distribution.

---

### P2-5: predict() Guard Logic Uses AND Instead of OR

**File**: `ml/models/price_forecaster.py` line ~448
**Category**: Logic Bug

The unfitted model guard in `predict()` uses:

```python
if not self.is_fitted and self.model is None:
    raise ValueError("Model is not fitted")
```

This should be `or`, not `and`. If `is_fitted` is False but `model` is not None (e.g., partially initialized), the guard is skipped and prediction proceeds with an untrained model.

**Fix**: `if not self.is_fitted or self.model is None:`

---

### P2-6: Fallback CI Uses Global Standard Deviation

**File**: `ml/evaluation/backtesting.py` lines ~298-299
**Category**: Numerical Correctness

When a model does not return confidence intervals, the backtester falls back to computing `np.std(predictions)` across **all** predictions from all time windows, then uses this as the CI half-width for every prediction. This produces uniform-width intervals that do not reflect per-prediction uncertainty.

**Fix**: Compute prediction intervals per-window using the residuals from that window's training set.

---

### P2-7: sys.path Manipulation in Multiple Files

**File**: `ml/training/train_forecaster.py` line ~32; `ml/training/hyperparameter_tuning.py` line ~547
**Category**: Code Quality / Security

Both files manipulate `sys.path` at module load time:

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

This is fragile and can cause import shadowing. If a user has a local `models/` directory, it could be imported instead of the intended `ml/models/`.

**Fix**: Use proper package-relative imports (`from ml.models import ...`) and ensure the package is installed in development mode (`pip install -e .`).

---

### P2-8: Ensemble Confidence Interval Assumes Gaussian Distribution

**File**: `ml/models/ensemble.py` lines ~539-544
**Category**: Statistical Correctness

`predict_with_confidence()` computes confidence intervals as `mean +/- 1.96 * std`, assuming Gaussian errors. With an ensemble of only 2-3 models, the Student's t-distribution (with 1-2 degrees of freedom) would be more appropriate, producing much wider intervals.

**Fix**: Use `scipy.stats.t.ppf()` with `df = n_models - 1` for small ensembles, or switch to bootstrap confidence intervals.

---

### P2-9: Multiple MAPE Implementations with Different Epsilon Handling

**Files**: `ml/models/price_forecaster.py` line ~195; `ml/evaluation/metrics.py` lines ~133-138; `ml/inference/ensemble_predictor.py` (evaluate method)
**Category**: Consistency

Three different MAPE implementations exist in the codebase, each handling zero/near-zero actuals differently:

1. `price_forecaster.py`: Uses epsilon `1e-8` (produces huge values near zero)
2. `metrics.py`: Masks zero values (most correct)
3. `ensemble_predictor.py`: Uses `np.abs(actuals) + 1e-10`

This means MAPE values are not comparable across different parts of the pipeline.

**Fix**: Centralize MAPE calculation in `metrics.py` and use it everywhere.

---

### P2-10: Empty YAML Causes AttributeError in _load_metadata

**File**: `ml/inference/predictor.py` (confirmed by `test_predictor.py` lines ~150-162)
**Category**: Error Handling

When `metadata.yaml` exists but is empty, `yaml.safe_load()` returns `None`. The subsequent call to `metadata.get("version", "unknown")` raises `AttributeError: 'NoneType' object has no attribute 'get'`.

The test file (`test_predictor.py` line ~162) explicitly accepts this as "valid behavior" by catching the exception, but it is a defensive programming gap.

**Fix**: Add a None guard: `metadata = yaml.safe_load(f) or {}`

---

### P2-11: No Input Validation for NaN/Inf in price_forecaster.predict()

**File**: `ml/models/price_forecaster.py` (predict method)
**Category**: Missing Input Validation

Unlike `predictor.py` (lines ~234-238) and `ensemble_predictor.py` (lines ~266-272), which both validate inputs for NaN/Inf values, the `ElectricityPriceForecaster.predict()` method has no such validation. NaN inputs can silently propagate through the TensorFlow model and produce NaN predictions.

**Fix**: Add input validation at the start of `predict()`:
```python
if np.any(np.isnan(X)) or np.any(np.isinf(X)):
    raise ValueError("Input contains NaN or Inf values")
```

---

## P3 -- Low (Nice to Fix)

### P3-1: Duplicated Z_SCORES Dictionary

**Files**: `ml/inference/predictor.py`; `ml/inference/ensemble_predictor.py`
**Category**: Code Duplication

Both files define an identical `Z_SCORES` dictionary mapping confidence levels to z-scores. This should be extracted to a shared constants module.

---

### P3-2: Duplicated DEFAULT_UNCERTAINTY_FRACTION

**Files**: `ml/inference/predictor.py`; `ml/inference/ensemble_predictor.py`
**Category**: Code Duplication

Both files define `DEFAULT_UNCERTAINTY_FRACTION = 0.10`. Extract to shared constants.

---

### P3-3: Unused Import in visualization.py

**File**: `ml/optimization/visualization.py`
**Category**: Dead Code

`LinearSegmentedColormap` is imported from matplotlib but never used in the file.

---

### P3-4: Missing Type Hints on Several Functions

**Files**: Various source files
**Category**: Code Quality

Several functions lack return type annotations and parameter type hints, particularly in:
- `ml/evaluation/backtesting.py`: `BacktestResult` methods
- `ml/training/train_forecaster.py`: `ModelTrainer` internal methods
- `ml/optimization/load_shifter.py`: `MILPOptimizer` helper methods

---

### P3-5: test_milp_standalone.py Is Not pytest-Compatible

**File**: `ml/tests/test_milp_standalone.py`
**Category**: Test Infrastructure

This file uses `if __name__ == "__main__"` with manual test execution and `sys.exit()`. It is a standalone script, not a proper pytest test file. It uses direct module loading and will not be discovered by pytest's default collection.

**Fix**: Convert to proper pytest format or move to a `scripts/` directory.

---

### P3-6: Hardcoded File Extensions for Model Type Inference

**File**: `ml/inference/predictor.py` (_infer_model_type method)
**Category**: Maintainability

The model type inference uses hardcoded file extension checks (`model.pt`, `model.json`, `model.txt`). Adding a new model type requires modifying this method. Consider using a registry pattern or storing the model type in `metadata.yaml`.

---

### P3-7: Test Files Duplicate Helper Functions

**Files**: `ml/tests/test_inference.py`, `ml/tests/test_predictor.py`, `ml/tests/test_ml_fixes.py`
**Category**: Test Maintainability

All three test files define nearly identical `_make_features_df()` and `_stub_predictor()` helper functions. These should be consolidated into `conftest.py` as shared fixtures.

---

## Test Quality Assessment

### Strengths

1. **Comprehensive inference testing**: `test_predictor.py` (50 tests) and `test_inference.py` (45 tests) provide thorough coverage of the prediction pipeline, including edge cases like empty DataFrames, single-row inputs, horizon=0, and all-target-column DataFrames.

2. **Fix verification tests**: `test_ml_fixes.py` (30 tests) is excellently structured, directly testing the three critical fixes (data leakage, MIMO inference, conformal prediction) with precise assertions about scaler fitting, model call counts, and interval widths.

3. **Optimization test suite**: `test_load_shifter.py`, `test_scheduler.py`, and `test_optimization.py` together provide ~105 tests covering the MILP solver, constraint builder, and scheduling API thoroughly.

4. **Proper mocking strategy**: Tests that require TensorFlow or PyTorch use direct module loading with `sys.modules` stubs, allowing the test suite to run without heavy ML dependencies installed.

5. **Statistical property tests**: `test_metrics.py` includes property-based assertions (RMSE >= MAE, MAPE >= 0, coverage in [0, 100]) that catch mathematical errors.

### Weaknesses

1. **Torch-dependent tests skipped by default**: All tests in `test_models.py` and `test_training.py` are marked `@pytest.mark.requires_tf` and will be skipped in CI unless TensorFlow is installed. This creates a coverage blind spot for the TensorFlow model code.

2. **No integration tests for the full training-to-inference pipeline**: No test verifies that a model trained by `CNNLSTMTrainer` can be loaded and used by `PricePredictor` end-to-end. This is how P0-1 (the serialization incompatibility) went undetected.

3. **conftest.py uses global random seed**: `np.random.seed(42)` in fixtures sets global state, which can hide test isolation issues where one test's random state depends on the execution order of previous tests.

4. **No negative/adversarial tests for model loading**: No test verifies behavior when a corrupted or malicious model file is loaded (relevant to P0-2).

5. **Duplicated test helpers across files**: Three test files duplicate `_make_features_df()` and `_stub_predictor()` instead of using shared fixtures from `conftest.py`.

---

## Architecture Observations

### Positive Patterns

1. **Clean separation of concerns**: Models, training, inference, evaluation, and optimization are properly separated into subpackages with minimal cross-coupling.

2. **Split conformal prediction**: The implementation in `predictor.py` (lines ~270-373) is well-designed, providing statistically grounded confidence intervals that adapt to model accuracy per-horizon-step. The test coverage in `test_ml_fixes.py` verifies heteroscedastic behavior.

3. **MILP optimization**: The PuLP-based optimizer in `load_shifter.py` is well-structured with separate constraint and objective builders, supporting multi-objective optimization with customizable weights.

4. **Graceful degradation in ensemble**: `EnsemblePredictor.predict()` tolerates partial model failures, re-normalizing weights when some component predictions fail. This is well-tested in `test_inference.py`.

5. **Multi-tier model weight loading**: The ensemble predictor supports loading weights from Redis, PostgreSQL, filesystem, and defaults, with proper fallback ordering.

### Concerns

1. **Two parallel CNN-LSTM implementations**: `price_forecaster.py` (TensorFlow/Keras) and `cnn_lstm_trainer.py` (PyTorch) implement the same architecture in different frameworks with different save/load formats. This creates maintenance burden and the serialization incompatibility in P0-1.

2. **No model versioning protocol**: Models are versioned by a string in `metadata.yaml`, but there is no schema validation, no compatibility checking between model versions and code versions, and no migration path for loading older model formats.

3. **Synchronous inference in async backend**: The `EnsemblePredictor` uses synchronous `psycopg2` and `redis.Redis` connections, which will block the FastAPI event loop if called from an async endpoint. The backend should use `asyncpg` and `redis.asyncio`.

---

## Recommendations

### Immediate (Before Next Deploy)

1. **Fix torch.save/torch.load incompatibility (P0-1)**: Switch to state_dict serialization. This is the highest-priority fix as it causes complete inference failure.

2. **Fix the hash verification bypass (P0-2)**: Change `_verify_model_hash()` to reject files without hash verification.

3. **Pin Optuna version or fix deprecated API (P0-3)**: Add `optuna>=3,<4` to `pyproject.toml` as a temporary fix, then replace `suggest_loguniform` with `suggest_float(..., log=True)`.

4. **Fix or remove `build_model_from_params` import (P0-4)**: Either implement the function or refactor `tune_price_forecaster()`.

### Short-Term (This Sprint)

5. **Add end-to-end training-to-inference test**: Create a test that trains a small model with `CNNLSTMTrainer`, saves it, and loads it with `PricePredictor`. This would have caught P0-1.

6. **Fix data leakage in CNNLSTMTrainer (P1-1)**: Move scaler fitting after the train/test split.

7. **Centralize MAPE calculation (P2-9)**: Use `metrics.py` implementation everywhere.

8. **Add connection timeouts to inference DB calls (P1-5)**: Prevent unbounded blocking during prediction.

### Medium-Term (This Quarter)

9. **Consolidate CNN-LSTM implementations**: Pick one framework (TensorFlow or PyTorch) and remove the other to eliminate the maintenance burden and incompatibility surface.

10. **Add model compatibility metadata**: Store framework version, architecture config, and code version hash in `metadata.yaml` and validate at load time.

11. **Switch to async DB clients in inference**: Replace `psycopg2` with `asyncpg` and `redis.Redis` with `redis.asyncio.Redis` for FastAPI compatibility.

12. **Replace global random seeds with local RNG instances (P1-4)**: Use `np.random.default_rng()` throughout.

---

## Finding Summary

| Severity | Count | Categories |
|----------|-------|------------|
| P0 Critical | 4 | Serialization incompatibility, unsafe deserialization, deprecated API crash, broken import |
| P1 High | 8 | Data leakage, shuffled time series, type mismatch, global seeds, no connection pooling, epsilon too small, no seed management, fabricated bounds |
| P2 Medium | 11 | UInt32 type, NaN fill, ffill leakage, incorrect CI math, logic bug, global std fallback, sys.path, Gaussian assumption, MAPE inconsistency, empty YAML, missing validation |
| P3 Low | 7 | Duplicated constants, unused import, missing types, standalone test, hardcoded extensions, duplicated test helpers |
| **Total** | **30** | |
