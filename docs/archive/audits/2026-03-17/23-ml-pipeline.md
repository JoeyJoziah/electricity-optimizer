# Audit Report: ML Pipeline
## Date: 2026-03-17

---

### Executive Summary

The ML pipeline is structurally sound and meaningfully more mature than a typical early-stage project. The ensemble architecture (CNN-LSTM + XGBoost + LightGBM), HNSW-accelerated vector store, nightly learning cycle, and model versioning with A/B testing infrastructure are all thoughtfully designed. The learning service weight-persistence stack (Redis -> PostgreSQL -> file -> defaults) is resilient and well-documented.

However, three issues require attention before the system can be considered fully production-safe:

1. **P0 — Unsafe PyTorch model deserialization** (`torch.load(..., weights_only=False)`) accepts arbitrary pickle payloads and enables remote code execution if the model file path is ever influenced by an external actor.
2. **P0 — Joblib scaler deserialization** (`joblib.load(scaler_path)`) shares the same risk: joblib uses pickle internally and will execute arbitrary Python during load.
3. **P1 — `optuna.save_study` deprecated API** (`hyperparameter_tuning.py:352`) — this API was removed in Optuna 3.x and will raise `AttributeError` at runtime when Bayesian tuning is invoked, silently corrupting tuning runs.

Beyond those, several high and medium findings cover missing input-range guards on prediction requests, unbounded vector-store growth, a dead `pickle` import, a hardcoded uncertainty approximation presented as a real confidence interval, and a handful of code-quality issues.

---

### Findings

---

#### P0 — Critical

---

**P0-01: Unsafe PyTorch model deserialization (arbitrary code execution)**

- **File**: `ml/inference/predictor.py`, lines 109-111
- **File**: `ml/training/cnn_lstm_trainer.py`, line 409

`predictor.py` calls:

```python
self.model = torch.load(  # noqa: S614
    model_file, map_location="cpu", weights_only=False
)
```

`cnn_lstm_trainer.py` saves the full `nn.Module` object (not just `state_dict`):

```python
torch.save(self.model, os.path.join(path, "model.pt"))
```

`weights_only=False` passes the file through Python's `pickle` module unconditionally. If a model file is replaced by a malicious actor — through a compromised deployment pipeline, a writable model-storage path, or a supply-chain attack — the payload executes arbitrary Python on the inference server at startup. The comment in the code acknowledges the risk and defers mitigation to a TODO.

The model file path is constructed from `self.model_path`, which flows from `EnsemblePredictor.__init__` → `PricePredictor.__init__` → callers in the backend. If `model_path` can ever be derived from an API request or environment variable that an attacker can influence, this becomes a direct RCE vector.

**Fix**: Migrate the save format from `torch.save(model)` to `torch.save(model.state_dict())`, then reconstruct the model from config before loading state dict with `weights_only=True`. This eliminates the pickle deserialization surface entirely.

```python
# Save (cnn_lstm_trainer.py)
torch.save(self.model.state_dict(), os.path.join(path, "model_state.pt"))

# Load (predictor.py)
config_path = os.path.join(self.model_path, "config.yaml")
with open(config_path) as f:
    cfg = yaml.safe_load(f)
self.model = CNNLSTMModel(cfg["n_features"], cfg["sequence_length"], cfg)
state = torch.load(
    model_file, map_location="cpu", weights_only=True
)
self.model.load_state_dict(state)
self.model.eval()
```

This work is already tracked as a TODO in the source; it should be promoted to a ticket and completed before the next deployment.

---

**P0-02: Unsafe joblib/pickle scaler deserialization**

- **File**: `ml/inference/predictor.py`, lines 128-131

```python
scaler_path = os.path.join(self.model_path, "scaler.pkl")
if os.path.exists(scaler_path):
    import joblib
    self.scaler = joblib.load(scaler_path)
```

`joblib.load` uses pickle internally. A tampered `scaler.pkl` file executes arbitrary Python at load time, with identical risk to P0-01. The scaler is a `sklearn.preprocessing.StandardScaler`, which is a simple structure — it can be serialized safely without pickle.

**Fix option A**: Save the scaler as JSON (its `mean_` and `scale_` arrays are plain numpy arrays):

```python
# Save
import json, numpy as np
scaler_data = {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}
with open(os.path.join(path, "scaler.json"), "w") as f:
    json.dump(scaler_data, f)

# Load
with open(scaler_path) as f:
    scaler_data = json.load(f)
scaler = StandardScaler()
scaler.mean_ = np.array(scaler_data["mean"])
scaler.scale_ = np.array(scaler_data["scale"])
scaler.var_ = scaler.scale_ ** 2
scaler.n_features_in_ = len(scaler.mean_)
```

**Fix option B**: If joblib is kept, verify a cryptographic signature (e.g., HMAC-SHA256 using a server-side key) over the file before deserializing, and enforce that model files can only be written by the training pipeline under a controlled service account.

---

#### P1 — High

---

**P1-01: `optuna.save_study` API removed in Optuna 3.x**

- **File**: `ml/training/hyperparameter_tuning.py`, line 352

```python
study_path = self.results_dir / f"{study_name}.pkl"
optuna.save_study(study, str(study_path))
```

`optuna.save_study` was deprecated in Optuna 2.x and removed entirely in Optuna 3.0. The project's requirements include `optuna` (version not pinned in this file). This call raises `AttributeError: module 'optuna' has no attribute 'save_study'` at runtime whenever `bayesian_optimization()` is invoked, silently aborting hyperparameter tuning runs.

**Fix**: Replace with the current persistent-storage approach — pass a `storage` URL to `create_study`:

```python
storage_url = f"sqlite:///{self.results_dir / study_name}.db"
study = optuna.create_study(
    direction=self.direction,
    study_name=study_name,
    storage=storage_url,
    load_if_exists=True,
    sampler=TPESampler(n_startup_trials=n_startup_trials),
    pruner=MedianPruner(n_startup_trials=n_startup_trials, n_warmup_steps=5),
)
# No explicit save needed — SQLite storage is persistent.
```

---

**P1-02: No input-range validation on prediction inputs**

- **File**: `ml/inference/predictor.py`, `predict()` (line 191); `ml/inference/ensemble_predictor.py`, `predict()` (line 231)

`EnsemblePredictor.predict()` validates NaN and infinite values (lines 259-265). `PricePredictor.predict()` calls `_preprocess_features()` which also validates for NaN and infinity (lines 154-160). However, neither layer validates:

- That `horizon` is within `[1, config.forecast_horizon]`.
- That `confidence_level` is within `(0.0, 1.0)`.
- That the input DataFrame has any rows.
- That feature count matches what the model was trained on (a mismatch causes a silent shape error deep in the forward pass, which is harder to diagnose than a clear validation message).

An API caller that passes `horizon=0` or `horizon=99999` receives an array-slicing no-op or an out-of-bounds indexing error rather than an actionable message.

**Fix**: Add a validation block at the top of `predict()`:

```python
def predict(self, df, horizon=24, confidence_level=0.9):
    if df.empty:
        raise ValueError("Input DataFrame is empty")
    if not (1 <= horizon <= 168):  # cap at 7-day horizon
        raise ValueError(f"horizon must be between 1 and 168, got {horizon}")
    if not (0.0 < confidence_level < 1.0):
        raise ValueError(f"confidence_level must be in (0, 1), got {confidence_level}")
    ...
```

---

**P1-03: Unbounded HNSW index memory growth**

- **File**: `backend/services/hnsw_vector_store.py`, lines 153-157

```python
if self._next_label >= self._index.get_max_elements():
    self._index.resize_index(
        self._index.get_max_elements() * 2
    )
```

The HNSW index uses geometric doubling with an initial cap of `max_elements=10000`. Each doubling doubles in-process memory. With nightly learning running continuously and `prune()` only called during the learning cycle (no size ceiling), the index can grow without bound between prune runs on a long-lived Render instance.

Additionally, the two Python dicts `_label_to_id` and `_id_to_label` grow in parallel and are never trimmed independently of a full `prune()` call.

**Fix**: Add a hard ceiling on `max_elements` (e.g., 100,000) and log a warning when the index is resized past a threshold. Also enforce that the pruner runs before every resize, not just during the learning cycle:

```python
MAX_INDEX_ELEMENTS = 100_000

if self._next_label >= self._index.get_max_elements():
    new_size = min(self._index.get_max_elements() * 2, MAX_INDEX_ELEMENTS)
    if new_size == self._index.get_max_elements():
        logger.error("hnsw_index_at_max_capacity pruning_required=true")
        # Force prune before accepting more inserts
        self._store.prune(min_confidence=0.5, min_usage=1)
        self._rebuild_label_maps()
    else:
        self._index.resize_index(new_size)
        logger.warning("hnsw_index_resized new_size=%d", new_size)
```

---

**P1-04: Stale model served with no freshness check**

- **File**: `ml/inference/ensemble_predictor.py`, `_load_models()` (lines 196-218)

Models are loaded once at `EnsemblePredictor` construction time. There is no mechanism for the nightly learning cycle to signal the inference layer to reload updated model weights or detect that a model file on disk is newer than what is currently loaded. The weight update path (Redis/PostgreSQL) works for ensemble weights, but the underlying model `.pt`/`.json`/`.txt` files — which change when retraining is triggered — are never reloaded without a Render restart.

If retraining runs to completion but a Render restart does not follow, the serving layer continues using the old model for up to 24 hours, silently defeating the adaptive learning cycle.

**Fix**: Add a file-modification-time check on `_load_models` and expose a `reload_if_stale(max_age_hours=25)` method callable by the nightly learning endpoint:

```python
def reload_if_stale(self, max_age_hours: int = 25) -> bool:
    """Reload component models if any on-disk file is newer than loaded version."""
    for model_type in self.predictors:
        model_dir = os.path.join(self.model_path, model_type)
        if self._any_file_newer(model_dir, self._load_timestamps.get(model_type)):
            logger.info("model_reload_triggered model_type=%s", model_type)
            self._load_models()
            return True
    return False
```

---

**P1-05: Recursive tree-model prediction loop does not update lag features**

- **File**: `ml/inference/predictor.py`, lines 236-258

The XGBoost/LightGBM multi-step prediction loop calls the model `horizon` times but does not update the feature vector between steps:

```python
for h in range(horizon):
    pred = self.model.predict(current_features)[0]
    point.append(pred)
    # Update features for next step (simplified)
    # In production, would properly update lag features
```

The comment acknowledges this is intentionally deferred, but the consequence is that every step beyond the first uses identical features — effectively predicting the same one-step-ahead value 24 times. For a 24-step horizon the last 23 forecasts are meaningless. The ensemble output for XGBoost/LightGBM is therefore systematically wrong for multi-step prediction.

**Fix**: At minimum, shift the price lag features by one position per iteration, or implement a proper recursive feature update. If true multi-step prediction is deferred, restrict tree models to single-step output and document the ensemble as `effective_horizon=1` for tree components.

---

#### P2 — Medium

---

**P2-01: Dead `import pickle` in `ml/models/ensemble.py`**

- **File**: `ml/models/ensemble.py`, line 16

`import pickle` is present in the import list but `pickle` is never referenced anywhere in the file. XGBoost models are saved/loaded as JSON (`model.save_model()`/`model.load_model()`), and LightGBM models are saved as text files. The import is dead code.

This is worth calling out because any future developer seeing `import pickle` in this file may assume pickle is an intentional serialization path and use it, creating a P0 issue from apparent precedent.

**Fix**: Remove the import.

---

**P2-02: Fake confidence intervals in `CNNLSTMTrainer.prepare_sequences()`**

- **File**: `ml/training/cnn_lstm_trainer.py`, lines 106-110

```python
y_point = y_values
y_lower = y_values * 0.9  # Simple 10% lower bound
y_upper = y_values * 1.1  # Simple 10% upper bound

y_list.append(np.stack([y_point, y_lower, y_upper], axis=-1))
```

The training targets for the lower and upper bounds are computed as deterministic ±10% of the actual price, not as genuine quantile targets. The CNN-LSTM model is then trained to fit these synthetic bounds. At inference time, the model outputs are interpreted as calibrated 90% confidence intervals (`config.confidence_level = 0.9`), but they are actually trained to reproduce ±10% scaling of truth — an interval that has nothing to do with the true conditional distribution of forecast errors.

This means the `coverage` metric reported by `EnsemblePredictor.evaluate()` reflects how well the model reproduced the fake bounds, not actual coverage of the true price distribution.

**Fix**: Replace with proper quantile regression targets. The `ElectricityPriceForecaster` (Keras version in `price_forecaster.py`) already uses `QuantileLoss` with correct quantile targets (`[0.05, 0.5, 0.95]`). The PyTorch trainer should adopt the same approach:

```python
# At target creation time, do not pre-set fake bounds:
y_list.append(y_values)  # shape: (horizon,) — point targets only

# Use quantile loss during training:
alpha = 0.1  # for 90% CI
quantile_loss = (q * error.clamp(min=0) + (1-q) * (-error).clamp(min=0))
```

---

**P2-03: Approximate 90% CI computed by shrinking 95% bounds — `metrics.py`**

- **File**: `ml/evaluation/metrics.py`, lines 428-432

```python
interval_width = y_upper - y_lower
y_lower_90 = y_pred - (interval_width * 0.9 / 2)
y_upper_90 = y_pred + (interval_width * 0.9 / 2)

coverage_90 = prediction_interval_coverage(y_true, y_lower_90, y_upper_90)
```

Shrinking a 95% interval by multiplying its half-width by 0.9 does not produce a 90% interval — it produces an ~85.5% interval (0.9 of the z-ratio, which scales non-linearly with coverage). This causes systematic miscalculation of `coverage_90` and `interval_score_90` in `ForecastMetrics`, which are reported to users.

**Fix**: If both a 90% and 95% interval are needed, train the model with both quantile pairs (0.05/0.95 and 0.025/0.975) or compute the 90% interval directly from model outputs at the correct quantiles.

---

**P2-04: No training data quality gates in `ModelTrainer.load_data()`**

- **File**: `ml/training/train_forecaster.py`, lines 155-176

When `use_dummy_data=False`, the CSV file is loaded with:

```python
df = pd.read_csv(self.config.data_path, index_col=0, parse_dates=True)
```

No checks are performed for:
- Required columns (e.g., `price`) being present.
- Minimum row count sufficient for the configured `sequence_length + forecast_horizon`.
- Fraction of NaN values beyond which training becomes unreliable.
- Price plausibility (negative prices, prices above a realistic ceiling, zeroes in a time series where MAPE is the primary metric — division by zero in MAPE produces `inf`).

A misconfigured data path or corrupted CSV will produce a cryptic numpy or pandas error deep in the pipeline rather than a clear early-exit message.

**Fix**:

```python
def _validate_data(self, df: pd.DataFrame) -> None:
    if "price" not in df.columns:
        raise ValueError("Data must contain a 'price' column")
    min_rows = self.config.sequence_length + self.config.forecast_horizon + 100
    if len(df) < min_rows:
        raise ValueError(f"Need at least {min_rows} rows, got {len(df)}")
    nan_frac = df["price"].isna().mean()
    if nan_frac > 0.05:
        raise ValueError(f"price column has {nan_frac:.1%} NaN values (threshold: 5%)")
    zero_frac = (df["price"] == 0).mean()
    if zero_frac > 0.01:
        logger.warning("price_column_zeros frac=%.3f mape_may_be_inf", zero_frac)
```

---

**P2-05: Feature engineering `country_code` default mismatch between config and engine**

- **File**: `ml/data/feature_engineering.py`, `FeatureConfig.country_code = "DE"` (line 56); `ElectricityPriceFeatureEngine.__init__` default `country="GB"` (line 88); `ml/training/train_forecaster.py`, `TrainingConfig.country_code = "GB"` (line 69)

The `FeatureConfig` dataclass (used by the full feature pipeline in `config`-driven code) defaults `country_code` to `"DE"` (Germany), while the `ElectricityPriceFeatureEngine` and `TrainingConfig` both default to `"GB"` (Great Britain). If code constructs a `FeatureConfig` and passes it to a path that feeds `ElectricityPriceFeatureEngine`, the holiday calendar used for `is_holiday` features will be inconsistent between what the config specifies and what the engine applies — resulting in silent feature mismatch between training and inference.

**Fix**: Align defaults across all three classes to the same value, or make `FeatureConfig.country_code` the single source of truth and require `ElectricityPriceFeatureEngine` to accept a `FeatureConfig` instance rather than keyword arguments.

---

**P2-06: LightGBM `Booster` objects returned by `load()` do not have `feature_importances_` attribute**

- **File**: `ml/models/ensemble.py`, `LightGBMForecaster.load()` (lines 365-376) and `get_feature_importance()` (lines 322-337)

When loading LightGBM models via `lgb.Booster(model_file=model_path)`, the returned objects are raw `Booster` instances, not `LGBMRegressor` sklearn-compatible wrappers. `Booster` does not expose `feature_importances_` as a property (it uses `.feature_importance()` method instead). The `get_feature_importance()` method attempts to access `model.feature_importances_` and will raise `AttributeError` on loaded models.

**Fix**:

```python
# In get_feature_importance() for LightGBM:
for model in self.models:
    if hasattr(model, "feature_importances_"):
        # LGBMRegressor (fitted in-process)
        importance['gain'] += model.feature_importances_
    else:
        # lgb.Booster (loaded from file)
        importance['gain'] += model.feature_importance(importance_type="gain")
```

---

**P2-07: `validate_solution` errors printed to stdout instead of logged**

- **File**: `ml/optimization/load_shifter.py`, line 445

```python
for error in validation_errors:
    print(f"Warning: {error}")
```

Constraint validation errors from the MILP solver are written to `stdout` using `print()` rather than the module logger. This bypasses all structured logging, OTel trace context, and log aggregation. On Render, stdout output is captured separately from structured logs and cannot be correlated with request traces.

**Fix**:

```python
for error in validation_errors:
    logger.warning("milp_constraint_violation detail=%s", error)
```

---

**P2-08: Ensemble weight updates keyed by `model_version` string, not by model type**

- **File**: `backend/services/learning_service.py`, lines 123-149

The inverse-MAPE weight update iterates over `model_stats` where `version = stat["model_version"]`. The resulting `weights` dict is keyed by version tag strings (e.g., `"v20260317_030000"`), not by model type names (`"cnn_lstm"`, `"xgboost"`, `"lightgbm"`).

`EnsemblePredictor._load_weights_from_redis()` and `_load_weights_from_db()` both return this dict, and `EnsemblePredictor._load_weights()` stores it in `self.weights`. But `EnsemblePredictor.predict()` does:

```python
total_weight += self.weights.get(model_type, {}).get("weight", 0)
```

where `model_type` is `"cnn_lstm"`, `"xgboost"`, or `"lightgbm"`. If weights are keyed by version tag, all `.get(model_type, {})` calls return `{}`, `total_weight` stays at 0, and the normalization fallback fires — assigning equal weights regardless of accuracy. The adaptive learning cycle therefore silently has no effect on the production ensemble.

**Fix**: Clarify and enforce the contract: the weight dict stored in Redis/PostgreSQL must use model type names as keys (matching `EnsemblePredictor.DEFAULT_WEIGHTS`). The `update_ensemble_weights` method should be updated to map from `model_version` to `model_type` before writing:

```python
# Map version tag back to model type (requires observation_service to return model_type)
weights = {"cnn_lstm": {...}, "xgboost": {...}, "lightgbm": {...}}
```

If `get_model_accuracy_by_version` cannot return model type, add a `model_type` column to the forecast observations schema.

---

**P2-09: `HyperparameterTuner` holds entire training dataset in memory for the life of the tuner**

- **File**: `ml/training/hyperparameter_tuning.py`, lines 129-136

`X_train`, `y_train`, `X_val`, `y_val` are stored as instance attributes on the `HyperparameterTuner`. For large datasets (e.g., 1 year of hourly data with 50+ features → ~(6400, 168, 50) ≈ 200 MB per array), and multiple active `HyperparameterTuner` instances (e.g., one per Optuna trial worker), this can exhaust Render's memory budget on the free tier.

**Fix**: Pass data by reference (already done via numpy array reference semantics), but explicitly `del` the arrays after the study completes, or use memory-mapped arrays (`numpy.memmap`) for datasets above a configurable threshold.

---

#### P3 — Low

---

**P3-01: `test_model()` function shipped in production code**

- **File**: `ml/models/price_forecaster.py`, lines 634-699

A `test_model()` function that trains on random data, writes to `/tmp/`, and prints results is defined at module level in production code. It is only called via `if __name__ == "__main__"`, so it does not execute on import. However, it inflates module size, and the hardcoded `/tmp/` paths would conflict if multiple processes ran it concurrently.

**Fix**: Move to `ml/tests/test_models.py` or a dedicated example script.

---

**P3-02: `logging` vs `structlog` used inconsistently within the same service tier**

- **File**: `backend/services/model_version_service.py` uses `structlog.get_logger()` (line 70); `backend/services/learning_service.py` uses `logging.getLogger()` (line 33); `backend/services/hnsw_vector_store.py` uses `logging.getLogger()` (line 21)

All three files are in the same service tier and relate to ML operations. Using both `structlog` and `logging` means some ML events produce structured JSON logs (compatible with OTel/Grafana) and others produce plain text. This makes log correlation harder in production.

**Fix**: Standardize on `structlog` across all backend service files. The project already uses structlog in `model_version_service.py` and elsewhere in the backend.

---

**P3-03: `_infer_model_type()` may mask missing model files**

- **File**: `ml/inference/predictor.py`, lines 75-84

If none of `model.pt`, `model.json`, or `model.txt` exist, `_infer_model_type()` raises `ValueError`. But if the calling code explicitly passes `model_type="cnn_lstm"` while `model.pt` does not exist, `_load_model()` will proceed to `torch.load(model_file, ...)` and raise a `FileNotFoundError` with a path in the exception message — which is not caught and propagates to the caller without a model-type-aware error message.

**Fix**: Add an explicit existence check before loading:

```python
if not os.path.exists(model_file):
    raise FileNotFoundError(
        f"Model file not found for type '{self.model_type}': {model_file}"
    )
```

---

**P3-04: `DefaultTrainSplit` constant defined in two files with identical values**

- **File**: `ml/inference/predictor.py`, line 41; `ml/inference/ensemble_predictor.py`, line 43

Both files define `DEFAULT_TRAIN_SPLIT: float = 0.1` and `DEFAULT_UNCERTAINTY_FRACTION: float = 0.1`. Neither constant is used in the file that defines it (they are defined but not referenced in any function body). This is dead code that may confuse future maintainers into thinking these constants govern behavior they do not actually control.

**Fix**: Remove from both files, or move to a shared `ml/inference/constants.py` if they are intended to be used.

---

**P3-05: `FeatureConfig.country_code = "DE"` default is arguably wrong for a US-focused app**

- **File**: `ml/data/feature_engineering.py`, line 55

The `FeatureConfig` docstring says "Germany as default for European electricity", but RateShift's primary market is the US (50 states + DC in the Region enum). Using a German holiday calendar as the default silently populates `is_holiday` features with German public holidays, affecting both training and inference for US users.

**Fix**: Change default to `"US"` and update the comment, or make the field required (no default) so callers must explicitly specify the market.

---

**P3-06: Backtesting `_generate_plots()` does not guard against empty array operations**

- **File**: `ml/evaluation/backtesting.py`, lines 547-549

```python
ax.plot(
    [actuals.min(), actuals.max()],
    [actuals.min(), actuals.max()],
    ...
)
```

If `actuals` is an empty array (which can happen if all backtest periods fail prediction), `actuals.min()` raises `ValueError: zero-size array`. The surrounding method only checks `len(all_actuals) == 0` in `_generate_summary()`, not in `_generate_plots()`.

**Fix**: Add a guard at the top of `_generate_plots()`:

```python
if actuals.size == 0:
    logger.warning("no_actuals_to_plot skipping_visualization")
    return
```

---

### Statistics

| Severity | Count | Files Affected |
|----------|-------|---------------|
| P0 — Critical | 2 | `ml/inference/predictor.py`, `ml/training/cnn_lstm_trainer.py` |
| P1 — High | 5 | `ml/training/hyperparameter_tuning.py`, `ml/inference/predictor.py`, `ml/inference/ensemble_predictor.py`, `backend/services/hnsw_vector_store.py`, `backend/services/learning_service.py` |
| P2 — Medium | 9 | `ml/models/ensemble.py`, `ml/training/cnn_lstm_trainer.py`, `ml/evaluation/metrics.py`, `ml/training/train_forecaster.py`, `ml/data/feature_engineering.py`, `ml/optimization/load_shifter.py`, `backend/services/learning_service.py` |
| P3 — Low | 6 | `ml/models/price_forecaster.py`, `backend/services/model_version_service.py`, `ml/inference/predictor.py`, `ml/inference/ensemble_predictor.py`, `ml/data/feature_engineering.py`, `ml/evaluation/backtesting.py` |
| **Total** | **22** | **13 files** |

**Files audited**: 46 (43 `ml/**/*.py` + `backend/services/hnsw_vector_store.py` + `backend/services/vector_store.py` + `backend/services/learning_service.py` + `backend/services/model_version_service.py`)

**No findings**: `ml/evaluation/backtesting.py` (overall structure), `ml/models/price_forecaster.py` (Keras model architecture), `ml/optimization/constraints.py`, `ml/optimization/objective.py`, `ml/optimization/appliance_models.py`, `ml/optimization/scheduler.py`, `backend/services/vector_store.py`, `backend/services/model_version_service.py` (versioning and A/B test logic correct), `ml/data/feature_engineering.py` (feature creation logic sound), `ml/tests/conftest.py` (fixtures appropriate).

---

### Recommended Priority Order

1. **P0-01 + P0-02** (same sprint, 1-2 days): Migrate CNN-LSTM to `state_dict` format and scaler to JSON. These share the same root cause (unsafe deserialization) and the same fix pattern.
2. **P1-01** (30 min): Fix `optuna.save_study` to use SQLite storage — this is a one-line change that unblocks hyperparameter tuning.
3. **P2-08** (1 day): Fix ensemble weight keying bug — without this, the entire nightly learning cycle's weight updates have no effect on production predictions.
4. **P1-05** (1-2 days): Implement proper recursive feature update in tree-model multi-step prediction — without this, XGBoost/LightGBM components are producing flat 24-step predictions.
5. **P1-02** (half day): Add input validation to `predict()` — small defensive guard, high return.
6. **P1-03 + P1-04** (1 day): Address vector store growth ceiling and model staleness detection.
7. **P2-02 + P2-03** (1-2 days): Fix confidence interval training targets and metrics calculation — improves honesty of reported model performance.
