# ML Pipeline Audit — 13-ml-pipeline

**Date**: 2026-03-23
**Auditor**: ML Engineer (Claude Sonnet 4.6)
**Scope**: Complete read-only review of all files in `ml/` and four backend services (`hnsw_vector_store.py`, `vector_store.py`, `forecast_service.py`, `learning_service.py`).

---

## P0 — Critical (Must Fix Before Next Deploy)

### P0-1: PyTorch legacy fallback uses `weights_only=False` — arbitrary code execution via pickle

**File**: `ml/inference/predictor.py`, lines 247–251

When the config file is absent or does not contain a `type` key, `PricePredictor._load_cnn_lstm()` falls through to a legacy branch that calls `torch.load(..., weights_only=False)`. This loads the full pickled `nn.Module` object graph and executes arbitrary Python during deserialization. A poisoned model file (or a supply-chain substitution) would result in remote code execution on any server that loads it.

```python
# Current (unsafe):
self.model = torch.load(
    model_file, map_location="cpu", weights_only=False  # line ~249
)
```

The safe path (`weights_only=True` with explicit state-dict loading) is already implemented in the primary branch. The legacy branch should be deleted or replaced with the same pattern.

**Fix**: Remove the `weights_only=False` fallback. Load via `state_dict` with `weights_only=True` in all code paths. If a legacy model file truly must be loaded once for migration, do it in a sandboxed subprocess, not the web worker.

---

### P0-2: CNN-LSTM trainer produces fake prediction intervals that are trained as ground truth

**File**: `ml/training/cnn_lstm_trainer.py`, lines 121–124

The interval targets fed to the quantile-loss training loop are not observed quantiles — they are computed as a deterministic ±10 % of the point prediction for that same sample:

```python
y_lower = y_values * 0.9   # fabricated 10 % lower bound
y_upper = y_values * 1.1   # fabricated 10 % upper bound
y_list.append(np.stack([y_point, y_lower, y_upper], axis=-1))
```

The network therefore learns to output intervals that are systematically biased toward being exactly ±10 % of the point forecast, regardless of actual price volatility. High-volatility periods will be severely underestimated; low-volatility periods will be overestimated. Because this is the **training target**, the problem cannot be corrected at inference time.

**Fix**: Replace fabricated bounds with empirically-derived quantile targets. Either (a) use a two-step approach — train the point estimator first, then fit conformal prediction residuals on the calibration set, already implemented in `predictor.py`; or (b) compute rolling empirical quantiles (e.g., 5th/95th percentile of rolling 168-hour windows) to produce realistic lower/upper targets before training.

---

### P0-3: LightGBM model persistence uses joblib pickle with no integrity verification before deserialisation

**File**: `ml/models/ensemble.py`, lines 377–381 (`LightGBMForecaster.load`)

```python
model = joblib.load(model_path)   # untrusted pickle executed here
self.models.append(model)
```

`joblib.load` is equivalent to `pickle.load`: it executes arbitrary Python when the file is read. The `PricePredictor` in `ml/inference/predictor.py` implements HMAC-SHA256 integrity verification (`_verify_model_integrity`) before loading PyTorch checkpoints, but `LightGBMForecaster.load` has no equivalent check. The same risk applies to the scaler saved as `scaler.pkl` by `cnn_lstm_trainer.py`.

**Fix**: Before calling `joblib.load`, compute the SHA-256 of the file and verify it against a stored signature (signed with `ML_MODEL_SIGNING_KEY`). The signing/verification helpers already exist in `predictor.py` — extract them to a shared `ml/utils/integrity.py` and call them from all pickle load sites.

---

## P1 — High (Fix in Next Sprint)

### P1-1: Ensemble weight keys from LearningService never match EnsemblePredictor's expected keys — adaptive learning is silently a no-op

**File**: `backend/services/learning_service.py`, lines 148–155; `ml/inference/ensemble_predictor.py`, lines 321, 336

`LearningService.update_ensemble_weights()` writes weights keyed by `model_version` strings (e.g. `"v2.1"`, `"v1.0"`):

```python
# learning_service.py line 155
ensemble_payload = {k: {"weight": v} for k, v in weights.items()}
# k here is a model_version string like "v2.1"
```

`EnsemblePredictor.predict()` looks up weights by model *type* keys (`"cnn_lstm"`, `"xgboost"`, `"lightgbm"`):

```python
# ensemble_predictor.py line 321
total_weight += current_weights.get(model_type, {}).get("weight", 0)
```

No key ever matches, `total_weight` stays zero, and the code falls into the equal-weight path. The nightly learning cycle runs, computes MAPE-derived weights, persists them to Redis and PostgreSQL, but they are never used. This has been documented in a code comment but never fixed.

**Fix**: In `LearningService`, record `model_type` alongside `model_version` in `forecast_observations` and use it as the weight key. Alternatively, add a mapping layer in `EnsemblePredictor._load_weights` that normalises version strings to type strings using a lookup table stored in metadata.yaml.

---

### P1-2: `EnsembleForecaster.load()` sets `is_fitted = True` unconditionally even when zero models loaded

**File**: `ml/models/ensemble.py`, lines 668–672 (approximately)

After the loop that attempts to load each sub-model, `is_fitted` is set to `True` regardless of how many models were actually restored. A subsequent call to `predict()` on an empty `self.models` list will produce either a division-by-zero or an empty array silently, depending on the weighting branch taken.

**Fix**: Set `self.is_fitted = len(self.models) > 0`. Raise `RuntimeError` if the loaded state is empty (the caller should receive an actionable error, not a silent wrong result).

---

### P1-3: `_load_weights_from_redis` deserialises JSON with no schema validation — malformed data silently corrupts ensemble weights

**File**: `ml/inference/ensemble_predictor.py`, lines 204–222

```python
cached = r.get("model:ensemble_weights")
if cached:
    return _json.loads(cached)
```

The returned object is used directly as the `current_weights` dict. If a Redis memory corruption, encoding error, or malicious write produces a value such as `{"cnn_lstm": 0.5}` (flat float instead of `{"weight": float}`) or `{"cnn_lstm": {"weight": "not-a-number"}}`, the downstream `.get("weight", 0)` call will either return a string or crash inside the arithmetic, producing a `TypeError` or silent zero weighting respectively.

**Fix**: After JSON parsing, validate that the result is a dict where every value is itself a dict containing a numeric `"weight"` key. Reject and log any payload that fails validation, then fall through to the file/default path.

---

### P1-4: `ElectricityPriceFeatureEngine.fit()` fills NaN with zero before fitting the scaler, corrupting scale statistics when zeros represent missing data

**File**: `ml/data/feature_engineering.py`, line 379

```python
self.scaler.fit(df_transformed[feature_cols].fillna(0))
```

Filling NaN with 0 before fitting `StandardScaler` shifts the mean toward zero and deflates the standard deviation for any feature that has missing values. If missing values are structurally correlated with specific conditions (e.g., `solar_radiation` is NaN at night), the scaler will be systematically biased. At inference, actual night-time values will be incorrectly scaled.

**Fix**: Fit the scaler only on non-NaN rows, or use `sklearn.impute.SimpleImputer` before scaling (with `strategy="mean"` or domain-appropriate fill, not zero). Store the imputer alongside the scaler and apply it during `transform()` before calling `scaler.transform()`.

---

### P1-5: Infeasibility constraint in `add_continuity_constraint` is mathematically inconsistent — MILP solver emits confusing dual constraints

**File**: `ml/optimization/constraints.py`, lines 155–163

When no valid starting positions exist for a continuous appliance, the code adds:

```python
problem += pulp.lpSum(vars) >= required_slots + 1  # infeasibility guard
```

But the duration constraint requires:

```python
problem += pulp.lpSum(vars) == required_slots       # duration constraint
```

The two constraints together form a system that is provably infeasible (`== N` and `>= N+1` simultaneously). The solver will correctly return INFEASIBLE, but the root cause will be opaque — the solver log will show a contradiction between two generated constraints, making debugging difficult.

**Fix**: Replace the infeasibility guard with a `problem += 0 == 1, "infeasible_<name>"` constraint (the canonical PuLP infeasibility marker) along with a structured log message naming the appliance and explaining why no valid window exists.

---

### P1-6: Training/serving feature skew — training uses `ElectricityPriceFeatureEngine` (50+ features); inference uses `_preprocess_features()` (generic numeric column selection)

**File**: `ml/training/train_forecaster.py` (uses `ElectricityPriceFeatureEngine`); `ml/inference/predictor.py`, `_preprocess_features()` method

`ModelTrainer.prepare_features()` drives `ElectricityPriceFeatureEngine` to produce ~50 engineered features (lags, rolling stats, cyclical encodings, seasonal decomposition, generation mix, weather). `PricePredictor._preprocess_features()` selects the first 19 numeric columns from the input DataFrame. If the inference-time input does not already contain the same 50 features in the same column order, the model receives a completely different feature matrix than it was trained on.

The `model_config.yaml` specifies exactly 19 features, but `ElectricityPriceFeatureEngine` generates many more. This discrepancy has no automated detection.

**Fix**: At model save time, persist the ordered list of feature column names used during training (already partially done for `ModelConfig.features` in `price_forecaster.py`). At inference, load this list, apply `ElectricityPriceFeatureEngine.transform()`, and select columns by name — never by positional index.

---

### P1-7: `backtesting.py` calls `feature_engine.transform()` without confirming the engine is fitted first

**File**: `ml/evaluation/backtesting.py`, line 214

```python
X = self.feature_engine.transform(df)
```

`WalkForwardBacktester` accepts a `feature_engine` argument at construction but does not call `fit()` on it. If the caller forgets to pre-fit the engine, `transform()` will attempt to call `self.scaler.transform()` on an unfitted `StandardScaler`, raising an unhelpful `sklearn.exceptions.NotFittedError` deep in a backtesting loop.

**Fix**: Add an `if not self.feature_engine.is_fitted_: raise ValueError(...)` guard at the top of `run()`, or call `fit()` on the first training fold if the engine is not yet fitted.

---

## P2 — Medium (Address Within 30 Days)

### P2-1: Dual-framework divergence — `price_forecaster.py` uses Keras/TensorFlow; `cnn_lstm_trainer.py` uses PyTorch — the two pipelines produce incompatible artefacts

**Files**: `ml/models/price_forecaster.py` (saves `.keras` files); `ml/training/cnn_lstm_trainer.py` (saves `model.pt` state-dict files); `ml/inference/predictor.py` (loads `model.pt`)

`ElectricityPriceForecaster` (Keras) saves with `model.save(path + ".keras")`. `CNNLSTMTrainer` (PyTorch) saves `torch.save(model.state_dict(), path / "model.pt")`. `PricePredictor._load_cnn_lstm()` expects a `model.pt` file. The two training paths produce artefacts that are loaded by different code paths in the inference layer. The YAML config at `ml/config/model_config.yaml` references only one architecture, but both trainers claim to implement "the" CNN-LSTM model with differing layer structures, sequence lengths (168 for Keras vs. configurable for PyTorch), and output shapes (horizon×3 for Keras, configurable for PyTorch).

This creates a permanent risk of deploying a model trained by one framework with inference code written for the other.

**Fix**: Designate one framework as canonical for CNN-LSTM. Archive the other. Until then, add a `framework: keras|pytorch` key to `metadata.yaml` and have `PricePredictor._load_cnn_lstm()` dispatch on this field rather than assuming PyTorch.

---

### P2-2: `TrainingConfig.from_yaml()` YAML key mapping is incomplete — several fields silently use defaults when loaded from config file

**File**: `ml/training/train_forecaster.py`, lines 99–124

The YAML flattening loop merges all nested dicts into a single flat dict by key name. The CNN section in `model_config.yaml` uses the key `filters` (under `cnn:`), but `TrainingConfig` stores the field as `cnn_filters`. The mapping at line 121 reads `flat_config.get("filters", [64, 128, 64])` — this accidentally works because after flattening, `filters` maps to `[64, 128, 64]`. However, `units` at line 122 is ambiguous: both `lstm.units` and `dense.units` flatten to `units`, and whichever appears last in the YAML dict iteration overwrites the other. Similarly `dropout`, `activation`, and other shared keys will be arbitrarily resolved to whichever nested section Python's dict iteration encounters last.

**Fix**: Parse each YAML section explicitly by key path (e.g., `config_dict["model"]["cnn"]["filters"]`) rather than flattening to a shared namespace.

---

### P2-3: `calculate_all_metrics()` approximates 90 % CI from 95 % CI by multiplying width by 0.9 — this is statistically incorrect

**File**: `ml/evaluation/metrics.py`, lines 421–423 (approximately)

Converting a 95 % interval to a 90 % interval requires recalibrating from prediction residuals (or at minimum using the correct z-score ratio: 1.645/1.960 ≈ 0.839, not 0.9). Using 0.9 produces a wider-than-correct 90 % interval, which will over-report CI coverage.

**Fix**: Use the ratio of z-scores from the `Z_SCORES` lookup table in `ensemble_predictor.py`, or recalibrate the interval on held-out data.

---

### P2-4: `vector_store.py` `record_outcome()` has a read-modify-write race condition on `usage_count`

**File**: `backend/services/vector_store.py`, lines 240–246

`record_outcome()` increments `success_count` and then reads back `usage_count` to update `avg_accuracy`. If two concurrent requests call this for the same vector ID, both may read the same pre-increment `usage_count`, causing one update to be lost. SQLite has per-write serialization at the file level, but the gap between two separate SQL statements is not atomic.

**Fix**: Combine the increment and the read into a single SQL statement using `RETURNING` (SQLite 3.35+), or wrap the read-modify-write in a `BEGIN IMMEDIATE` transaction.

---

### P2-5: `HNSWVectorStore` singleton factory is not thread-safe — concurrent cold starts can create two instances

**File**: `backend/services/hnsw_vector_store.py`, `get_vector_store_singleton()` function

The singleton is guarded by a module-level `_instance` variable with no lock. Under a multi-threaded ASGI server with a cold start, two threads can both observe `_instance is None` and proceed to create two `HNSWVectorStore` objects, each building the full HNSW index from SQLite. This doubles memory usage and the two instances will diverge on subsequent writes.

**Fix**: Guard with a `threading.Lock` using double-checked locking, or use `functools.lru_cache` on the factory function (which is thread-safe in CPython for the initial call).

---

### P2-6: `MAPE` silently drops zero-value samples with no warning — reported MAPE can be misleadingly low

**File**: `ml/evaluation/metrics.py`, lines 134–138

```python
mask = y_true != 0
if not np.any(mask):
    return np.inf
return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100
```

When electricity prices spike to zero (negative-price events happen regularly on grids with high renewable penetration), those hours are silently excluded from the MAPE calculation. If a model consistently misforecasts near-zero price events, this bias is invisible in the metric.

**Fix**: Log a warning with the count of excluded zero-price samples whenever `mask.sum() < len(y_true)`. Consider using SMAPE or a custom metric that handles zeros explicitly.

---

### P2-7: `forecast_service.py` `_extrapolate_trend()` assumes `base_time` supports `.total_seconds()` — fails if DB returns a `date` instead of `datetime`

**File**: `backend/services/forecast_service.py`, line 263

```python
days = [(t - base_time).total_seconds() / 86400 for t in timestamps]
```

`(date - date)` returns a `timedelta` which supports `.total_seconds()`. However `(datetime - date)` raises `TypeError: can't subtract offset-naive and offset-aware datetimes` (or a type mismatch error on Python 3.12). SQLAlchemy may return either `date` or `datetime` depending on the column type and the database timezone. The code has no type guard.

**Fix**: Add `timestamps = [t if isinstance(t, datetime) else datetime(t.year, t.month, t.day) for t in timestamps]` before the list comprehension.

---

### P2-8: `np.random.seed(42)` in `create_dummy_data` and `PriceProfile.create_realtime` sets global numpy state — not safe under concurrent calls

**Files**: `ml/data/feature_engineering.py`, line 541; `ml/optimization/appliance_models.py`, `PriceProfile.create_realtime()`

`np.random.seed()` mutates global state. Under a multi-threaded or multi-process environment (e.g., Gunicorn workers sharing memory, or parallel test execution), one call to `create_dummy_data()` will reset the RNG for all concurrent numpy random operations, producing non-reproducible sequences and potential test interference.

**Fix**: Replace `np.random.seed(42)` + `np.random.xxx()` with `rng = np.random.default_rng(42)` + `rng.xxx()` throughout. The `Generator` object is instance-local and does not touch global state.

---

### P2-9: `load_shifter.py` uses `print()` for validation warnings — they are not captured by structured logging

**File**: `ml/optimization/load_shifter.py`, line 445

```python
print(f"Warning: {error}")
```

This is inside `MILPOptimizer.optimize()` and runs in-process during API request handling. `print()` output goes to stdout, bypassing structlog and the OTel trace pipeline. Validation warnings are invisible in Grafana/Loki.

**Fix**: Replace `print(f"Warning: {error}")` with `logger.warning("milp_validation_error error=%s", error)`.

---

### P2-10: `learning_service.py` `store_bias_correction()` normalises the bias vector before storing — magnitude information is lost

**File**: `backend/services/learning_service.py`, `store_bias_correction()` method

The bias correction is stored as a unit-normalised embedding vector via `price_curve_to_vector()`. Actual bias correction requires knowing the *magnitude* of the systematic error (e.g., "model consistently underpredicts by 5 % in the afternoon"). A normalised vector retains only the *shape* of the bias, not its scale. Downstream code applying this correction will produce zero-magnitude corrections.

**Fix**: Store the raw bias array (before normalisation) in a separate column or as a JSON field. Use the normalised vector only for similarity search.

---

## P3 — Low (Tech Debt / Polish)

### P3-1: `datetime.utcnow()` is deprecated in Python 3.12 — use `datetime.now(UTC)`

**File**: `ml/inference/predictor.py`, line 639 (approximately)

```python
self.version = datetime.utcnow().strftime("%Y%m%d")
```

`datetime.utcnow()` is deprecated as of Python 3.12 (PEP 615) and will emit `DeprecationWarning` in future versions. The codebase uses `datetime.now(UTC)` elsewhere.

**Fix**: Replace `datetime.utcnow()` with `datetime.now(UTC)` and import `UTC` from `datetime`.

---

### P3-2: `hyperparameter_tuning.py` uses `sys.path.append` for imports — fragile in package context

**File**: `ml/training/hyperparameter_tuning.py`, line 34

```python
sys.path.append(str(Path(__file__).parent.parent.parent))
```

This works from the CLI but breaks when the module is imported as part of a package (e.g., during pytest collection or when run from a different working directory). The correct solution for an installed package is to use relative imports or install the package in editable mode.

**Fix**: Remove the `sys.path.append`. The `ml/` directory has an `__init__.py`; use `from ml.models.xxx import ...` or ensure the project is installed with `pip install -e .` in the development environment.

---

### P3-3: `Appliance.from_dict()` accepts arbitrary `**kwargs` — unknown fields are silently ignored, masking configuration errors

**File**: `ml/optimization/appliance_models.py`, `Appliance.from_dict()`

The method passes `**data` to the dataclass constructor. Unknown keys (e.g., a typo like `duraton_hours` instead of `duration_hours`) will cause a `TypeError: __init__() got an unexpected keyword argument` only if the key is not in the model's known fields — but in Python dataclasses, extra kwargs always raise `TypeError`. This is actually correct behaviour, but the error message is unhelpful: it names the field but not the calling context (which appliance definition, which config file).

**Minor variant**: if the `from_dict()` implementation filters `data` to known fields before constructing, unknown fields would be silently dropped. Confirm the implementation explicitly rejects unknown keys.

**Fix**: Verify that unknown keys raise a clear, named error. Add a `frozenset(KNOWN_FIELDS)` validation at the top of `from_dict()` that lists unrecognised keys before raising.

---

### P3-4: `scheduler.py` `compare_scenarios()` mutates `self.price_profile` inside the loop — leaves object in inconsistent state on failure

**File**: `ml/optimization/scheduler.py`, `compare_scenarios()` method

Each iteration assigns a new `PriceProfile` to `self.price_profile`. If the optimization call raises an exception mid-loop, `self.price_profile` is left pointing to an intermediate scenario profile, not the original. Subsequent calls on the same `ApplianceScheduler` instance will use the wrong price data.

**Fix**: Save `original_profile = self.price_profile` before the loop and restore it in a `finally` block.

---

### P3-5: `model_config.yaml` feature list (19 features) is inconsistent with `ElectricityPriceFeatureEngine` output (50+ features) — no automated reconciliation

**File**: `ml/config/model_config.yaml`, line 30 (`num_features: 19`); `ml/data/feature_engineering.py`

The config comment says "19 features (was 15 — corrected 2026-03-02)" and lists them explicitly. The feature engine generates weather, generation mix, seasonal decomposition, demand proxy, and extended lag features that bring the count to ~50+. There is no automated test that asserts `len(feature_engine.transform(df).columns) == model_config.num_features`.

**Fix**: Add a CI-level integration test that instantiates `ElectricityPriceFeatureEngine`, runs `transform()` on dummy data, and asserts the output column count matches `model_config.yaml:model.input.num_features`.

---

### P3-6: `ScheduleVisualizer` uses `print()` when matplotlib is unavailable — should use `logger.warning()`

**File**: `ml/optimization/visualization.py`, lines 113, 209, 286

```python
print("Matplotlib not available. Install with: pip install matplotlib")
```

Same structured-logging issue as P2-9. These print statements run in-process and are invisible to the observability stack.

**Fix**: Replace with `logger.warning("matplotlib_unavailable")` etc.

---

### P3-7: `rolling_std` with `min_periods=1` returns NaN for single-sample windows — may propagate to model input

**File**: `ml/data/feature_engineering.py`, `create_rolling_features()` method

`pandas.DataFrame.rolling(window=N, min_periods=1).std()` returns `NaN` when the window contains exactly one sample (standard deviation is undefined for a single observation). The subsequent `fillna(0)` applied elsewhere in `transform()` will turn those NaNs into zeros, which are then scaled. This is not incorrect, but the zeros are indistinguishable from "true zero std" and may confuse downstream models at the start of a time series.

**Fix**: Use `min_periods=2` for standard deviation features, or explicitly fill with the overall rolling mean as a better prior.

---

## Files With No Issues Found

The following files were reviewed and contained no actionable findings:

- `ml/optimization/visualization.py` — Clean optional-import pattern, graceful degradation, no business logic issues beyond the P3-6 `print()` calls.
- `ml/optimization/load_shifter.py` (`MILPOptimizer`) — Correct MILP formulation, proper infeasibility/timeout handling, constraint and objective builders called correctly, solution validation is thorough. Only issue is P2-9 `print()` call.
- `ml/optimization/objective.py` — Objective terms are correctly weighted and combined. The `avg_power == 0` degenerate case is harmless (constraint `dev_var >= 0 - 0` is always satisfied).
- `ml/optimization/switching_decision.py` — Rule-based switching logic is correct for its stated purpose. The confidence cap at 0.95 is documented.
- `ml/optimization/appliance_models.py` — Data models are well-typed. `_validate()` constraints are enforced at construction time. `get_valid_slots()` handles wrap-around windows correctly for `latest_end < earliest_start`.
- `ml/optimization/constraints.py` — Duration, time-window, power-limit, dependency, and mutual-exclusion constraints are correctly formulated in PuLP. Only issue is P1-5.
- `ml/evaluation/backtesting.py` — Walk-forward logic correctly partitions data, expands or slides the training window, and records metrics per fold. Only issue is P1-7.
- `ml/evaluation/metrics.py` — SMAPE, RMSE, MAE, direction accuracy, and coverage metrics are correctly implemented. Issues P2-3 and P2-6 noted above.
- `backend/services/forecast_service.py` — SQL injection prevention via allowlist validation is correct. Linear regression is correct. Only issue is P2-7.
- `ml/config/model_config.yaml` — Configuration values are internally consistent for the Keras `ElectricityPriceForecaster`. The `num_features: 19` discrepancy with the feature engine is noted as P3-5.

---

## Summary

**Total findings**: 22 (3 P0, 7 P1, 10 P2, 7 P3 — some P3 items are sub-items of broader patterns)

### Critical Path

The three P0 issues represent immediate security and data-quality risks:

1. **P0-1 (pickle RCE)** and **P0-3 (LightGBM pickle without integrity check)**: Any path that loads a model file without prior HMAC verification can execute arbitrary code if the model store is compromised. The fix is straightforward — the verification infrastructure already exists in `predictor.py`.

2. **P0-2 (fake training intervals)**: The CNN-LSTM model's uncertainty outputs are not learned from data — they are a deterministic ±10 % of the point prediction baked in at training time. Every confidence interval produced by this model is invalid. The conformal prediction layer in `predictor.py` partially mitigates this for the PyTorch inference path, but the training artefact itself is corrupted.

### Systemic Patterns

Three systemic patterns account for most of the P1 findings and should be addressed architecturally:

- **Dual-framework divergence** (P0-2, P1-6, P2-1): Two independent CNN-LSTM implementations (Keras and PyTorch) with incompatible artefacts, different feature sets, and no automated reconciliation.

- **Weight key mismatch in the learning cycle** (P1-1): The adaptive nightly learning cycle is entirely inoperative because version-keyed weights are written but type-keyed weights are read. No alert fires when this falls back to equal weighting.

- **Unvalidated external data ingestion** (P1-3, P1-4): Redis weight payloads and scaler inputs both accept unvalidated external data that can silently corrupt model behaviour.

### Positive Observations

- The `ModelTrainer.prepare_features()` pipeline correctly implements data-leakage-free temporal splitting — scaler is fit on training rows only, applied independently to each split.
- `PricePredictor` implements HMAC-SHA256 model integrity verification and split conformal prediction correctly.
- MILP constraint formulation in `constraints.py` and `objective.py` is mathematically sound except for the P1-5 infeasibility guard.
- `EnsemblePredictor.predict()` validates NaN/infinity in input features before inference and handles the zero-weight degenerate case.
- Ensemble uncertainty quantification correctly combines epistemic (model variance) and aleatoric (CI width) components.
- Redis → PostgreSQL → file → default fallback chain for ensemble weights is robust against infrastructure failures.
