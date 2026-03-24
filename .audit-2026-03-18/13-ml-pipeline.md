# ML/AI Pipeline Audit Report

**Audit Date**: 2026-03-18
**Auditor**: ML Engineer (Claude Sonnet 4.6)
**Scope**: All ML/AI pipeline code — `ml/`, `backend/services/agent_service.py`, `backend/api/v1/agent.py`, `backend/api/v1/internal/ml.py`, `backend/routers/predictions.py`
**Status**: READ-ONLY — no source files modified

---

## Executive Summary

The ML pipeline has solid architectural intent: an ensemble predictor (CNN-LSTM + XGBoost + LightGBM), an HNSW vector store for pattern retrieval, an adaptive learning service that updates weights nightly, and a versioning/A-B testing layer. However, a number of correctness, safety, and reliability issues were found across all severity levels. The most critical finding is a **data leakage bug in feature engineering** that causes the `transform()` method to apply the training scaler during sequence creation when it must not, and a **target-variable leak** from `ffill/bfill` applied across the training/test boundary. The agent service stores raw user prompts in the database without sanitization, creating a secondary prompt-injection risk from the conversation log.

---

## P0 — Critical

### P0-ML-01: Data Leakage — Scaler Applied Before Train/Test Split

**File**: `ml/data/feature_engineering.py`, lines 380–446
**File**: `ml/training/train_forecaster.py`, lines 178–201

`ElectricityPriceFeatureEngine.fit()` calls `transform()` on the full DataFrame **before** it returns (line 383), then the caller (`ModelTrainer.prepare_features`) calls `transform()` again on the same full DataFrame after fitting (line 191). The scaler is fitted on all data (train + validation + test) because `fit()` internally calls `transform(fit_scaler=False)` on the **entire** input, then fits the scaler on the entire result. When `create_sequences` is later called and the data is subsequently split by `split_data()`, the scaler already contains statistics from the test period.

```python
# train_forecaster.py line 190-201
self.feature_engine.fit(df)          # fit on ALL data (train+val+test)
df_features = self.feature_engine.transform(df)  # transform ALL data
X, y = self.feature_engine.create_sequences(df_features)
# ... THEN split:
(X_train, y_train), (X_val, y_val), (X_test, y_test) = self.split_data(X, y)
```

**Impact**: The StandardScaler's mean and variance are computed from future test data, causing optimistic evaluation metrics (MAPE, RMSE) that will not generalize to production. Models appear more accurate than they are. Any reported MAPE < 10% target achievement cannot be trusted.

**Fix**: Fit the scaler only on training sequences. Split the raw DataFrame first, then fit and transform separately:
```python
df_train = df.iloc[:train_end_idx]
feature_engine.fit(df_train)
df_all_transformed = feature_engine.transform(df)  # scaler applies only train stats
```

---

### P0-ML-02: Data Leakage — `ffill/bfill` Propagates Future Values Across Boundaries

**File**: `ml/data/feature_engineering.py`, lines 436–439

The `transform()` method calls `.ffill().bfill()` on the **entire** DataFrame after feature engineering:

```python
df = df.ffill().bfill()
```

When this is applied to the full dataset before splitting, missing values in the training tail are filled with values from the validation period, and missing values at the start of validation are filled backward from training (bfill). For lag features (e.g., `price_lag_168h` at row 0 is NaN), the backward fill propagates the earliest training price into positions that should be unknown.

**Impact**: Training samples near the train/val boundary "see" true future values through backfill. This is a form of target-variable leakage. Models trained this way will exhibit overly optimistic validation metrics.

**Fix**: Apply `ffill/bfill` only within each split segment, or use `fillna(0)` for initial NaN lag values instead of backward-fill.

---

### P0-ML-03: Recursive Multi-Step Inference Uses Only Column 0 as Lag Feature

**File**: `ml/inference/predictor.py`, lines 299–319

For XGBoost and LightGBM models in multi-step prediction, the code uses a naive recursive strategy:

```python
for h in range(horizon):
    pred = self.model.predict(current_features)[0]
    point.append(pred)
    # Shift lag features: roll existing lags right, insert
    # latest prediction at position 0
    if len(current_features.shape) == 2:
        current_features = current_features.copy()
        current_features[0, 1:] = current_features[0, :-1]
        current_features[0, 0] = pred
```

This assumes that column index 0 is always the lag_1 feature, and that all other features remain constant across the forecast horizon. In practice:
1. The feature order depends on the column order in the preprocessed DataFrame, which is not guaranteed to put lag_1 at index 0.
2. Temporal features (hour, day_of_week, month) are **not updated** as the horizon advances. Predicting hour 6 with hour=0 features produces systematically wrong predictions.
3. Weather and generation features are held constant across all 24 forecast steps, which is particularly problematic for solar radiation (which varies to zero at night).

**Impact**: Multi-step XGBoost/LightGBM predictions will be increasingly incorrect as the horizon grows, particularly at peak/off-peak transitions. The first few predictions may be reasonable; predictions at hour 12+ are unreliable.

**Fix**: Use a direct (MIMO) strategy where one model is trained per forecast step, or propagate correct temporal features for each horizon step.

---

### P0-ML-04: `torch.load(weights_only=False)` Enables Arbitrary Code Execution

**File**: `ml/inference/predictor.py`, lines 138–144

```python
self.model = torch.load(  # noqa: S614
    model_file, map_location="cpu", weights_only=False
)
```

The comment acknowledges this risk and references a hash check as mitigation. However:
1. The hash check only warns (returns `True`) when no hash is recorded: `logger.warning("model_hash_missing: %s", ...)` then `return True`.
2. If `metadata.yaml` does not contain `file_hashes`, all model files are silently allowed to load without verification.
3. The `# noqa: S614` suppresses the Bandit security warning rather than fixing it.

**Impact**: If an attacker replaces a model file on the filesystem (e.g., through a compromised artifact registry, mounted volume, or misconfigured storage), PyTorch will execute arbitrary Python bytecode during load. This is a known critical vulnerability (CWE-502).

**Fix**: Migrate to state-dict format so `weights_only=True` can be used. Make hash verification mandatory (raise, not warn, on missing hash):
```python
if expected is None:
    raise ValueError(f"No hash recorded for {basename} — refusing to load")
```

---

### P0-ML-05: Training Labels Constructed With Fixed 10% Bounds (Not Actual Uncertainty)

**File**: `ml/training/cnn_lstm_trainer.py`, lines 104–110

```python
y_point = y_values
y_lower = y_values * 0.9  # Simple 10% lower bound
y_upper = y_values * 1.1  # Simple 10% upper bound
y_list.append(np.stack([y_point, y_lower, y_upper], axis=-1))
```

The confidence interval bounds used during training are **fabricated** as ±10% of the actual target. The model learns to output ±10% of its predictions regardless of actual price volatility. This means:
1. Confidence intervals are artificially calibrated to ±10% and do not reflect true aleatoric uncertainty.
2. In high-volatility periods, intervals will be too narrow (dangerously overconfident).
3. In low-volatility periods, intervals will be unnecessarily wide.
4. The `QuantileLoss` in `ml/models/price_forecaster.py` is never used by `CNNLSTMTrainer` — that trainer uses `MSELoss` instead.

**Impact**: Users receive confidence intervals that are uncalibrated fictions. The `/predict/price` endpoint exposes `confidence_lower` and `confidence_upper` which may mislead users into believing predictions are more certain than they are, affecting appliance scheduling decisions and savings estimates.

**Fix**: Use proper quantile regression targets derived from empirical residuals, or use a calibrated conformal prediction approach.

---

## P1 — High

### P1-ML-01: Ensemble Weight Keys Are Model Version Strings, Not Component Names

**File**: `backend/services/learning_service.py`, lines 147–154

```python
# NOTE: keys here are model_version strings from forecast_observations
# (e.g. "v2.1"), which may not match the predictor's model type keys
# (e.g. "cnn_lstm"). When no match is found, the predictor falls back
# to equal weighting — safe but suboptimal.
ensemble_payload = {k: {"weight": v} for k, v in weights.items()}
```

The nightly learning cycle computes per-version accuracy but stores the weights keyed by `model_version` strings (e.g., `"v20260318_040000"`), while `EnsemblePredictor._load_weights_from_redis()` / `_load_weights_from_file()` expects keys `"cnn_lstm"`, `"xgboost"`, `"lightgbm"`. The mismatch means:
- Nightly weight updates effectively **never apply** to the EnsemblePredictor.
- The predictor always falls back to default weights (0.5, 0.25, 0.25).
- The learning loop's primary output has no effect on actual predictions.

**Impact**: Adaptive learning is broken end-to-end. The nightly cycle writes to Redis and PostgreSQL but the values are never consumed. Model quality does not improve based on observed prediction errors.

**Fix**: Store weights keyed by component name, not version. The `forecast_observations` table must also record per-component contributions, or use a stable key mapping.

---

### P1-ML-02: HNSW Index Not Thread-Safe — Concurrent Insert/Search Race

**File**: `backend/services/hnsw_vector_store.py`, lines 116–173
**File**: `backend/services/vector_store.py`, lines 95–103

`HNSWVectorStore.insert()` and `search()` are not synchronized. The underlying `VectorStore._lock` protects only the LRU cache, not SQLite writes. `HNSWVectorStore` has no lock at all. The `_next_label` counter and `_label_to_id` / `_id_to_label` dicts are mutated without any lock:

```python
label = self._next_label
self._next_label += 1
self._label_to_id[label] = vec_id
self._id_to_label[vec_id] = label
self._index.add_items(v.reshape(1, -1), [label])
```

Under FastAPI's async execution model, `asyncio.to_thread()` wraps these in threads. Multiple concurrent forecast requests can trigger concurrent inserts.

**Impact**: Race conditions on `_next_label` can produce duplicate labels, corrupting the HNSW index mapping. Search results may return wrong vector IDs. Index corruption may cause crashes or incorrect bias correction lookups.

**Fix**: Add a `threading.Lock()` to `HNSWVectorStore` protecting all mutations to `_next_label`, `_label_to_id`, `_id_to_label`, and `self._index.add_items()`.

---

### P1-ML-03: Simulated Forecast Returned Without Warning to End Users

**File**: `backend/routers/predictions.py`, lines 247–269, 373–374

When no model is loaded, `_simulate_forecast()` is called silently. The returned `PriceForecastResponse` contains a `model_version` of `"v1.0.0"` (from Redis default) with no indication that the data is simulated. The API response is indistinguishable from a real ML prediction.

```python
logger.info("using_simulated_forecast", region=region)
return _simulate_forecast(region, hours_ahead)
```

The simulated forecast uses a fixed sinusoidal pattern with Gaussian noise (`np.random.normal(0, 0.01)`) seeded differently on each call, meaning repeated requests for the same region return **different prices** without any model.

**Impact**: Users receive fabricated price predictions that vary randomly. Appliance scheduling decisions and savings estimates are based on noise. No downstream system or user is informed that the ML model is unavailable. This is a correctness and trust failure.

**Fix**: Add a `is_simulated: bool` field to `PriceForecastResponse`. Return HTTP 503 when no model is loaded and `is_simulated` is not acceptable, or at minimum add a prominent warning field.

---

### P1-ML-04: Model Loading Is Not Thread-Safe (Module-Level Cache Race)

**File**: `backend/routers/predictions.py`, lines 195–244

```python
_model_cache: Dict[str, Any] = {}

def _load_model():
    cached = _model_cache.get("model")
    if cached is not None:
        return cached
    ...
    _model_cache["model"] = model
```

This module-level dict is accessed without a lock. Under concurrent requests (multiple Gunicorn/uvicorn workers sharing a process, or concurrent async requests), two threads can simultaneously find `cached is None`, both attempt to load the model, and both write to `_model_cache`. This wastes memory and may cause inconsistent state.

**Impact**: Under burst traffic, multiple model instances may be loaded simultaneously. If model loading fails partway through for one thread, a partial object may be written to cache.

**Fix**: Use a `threading.Lock()` or `asyncio.Lock()` around the check-and-set pattern.

---

### P1-ML-05: `pct_change()` Produces `inf` When Previous Price Is Zero

**File**: `ml/data/feature_engineering.py`, lines 214–215

```python
df[f'{target_col}_pct_change_1h'] = df[target_col].pct_change(1)
df[f'{target_col}_pct_change_24h'] = df[target_col].pct_change(24)
```

`pandas.DataFrame.pct_change()` produces `inf` when the previous value is 0 (e.g., negative prices clipped to 0 in `create_dummy_data`, or actual zero-price electricity events in some markets). Although `replace([np.inf, -np.inf], np.nan)` is called later (line 436), and `ffill/bfill` follows, the forward-filled values may propagate a pre-zero price across many timesteps, masking the actual price dynamics.

**Impact**: In European electricity markets (UK, Germany), zero and negative prices occur regularly. The `volatility_24h` feature computed from `pct_change_1h` will contain NaN/Inf artifacts that degrade model accuracy for regions with negative prices.

**Fix**: Use a safe percentage change: `(curr - prev) / (abs(prev) + 1e-8)`.

---

### P1-ML-06: Async Job in `_run_async_job` Has No Rate-Limit Enforcement

**File**: `backend/services/agent_service.py`, lines 314–342

The async task endpoint (`POST /agent/task`) increments the usage counter **after** the job is submitted:

```python
job_id = await service.query_async(...)
# Increment usage now (async job already started)
await service.increment_usage(current_user.user_id, db)
```

Inside `query_async`, `asyncio.create_task()` is called immediately before `increment_usage` returns. A user can submit many tasks in rapid succession: the rate limit check passes for each (count is 0), all tasks start, then `increment_usage` catches up. The rate limit is not respected for concurrent task submissions.

**File**: `backend/api/v1/agent.py`, lines 203–219

**Impact**: Free-tier users can exhaust the AI service quota (10 RPM on Gemini free tier) by submitting multiple concurrent async tasks.

**Fix**: Atomically check-and-increment at submission time (before creating the background task), not after.

---

### P1-ML-07: `FeatureConfig.country_code` Defaults to `"DE"` but `ElectricityPriceFeatureEngine` Defaults to `"GB"`

**File**: `ml/data/feature_engineering.py`, lines 55, 88

```python
class FeatureConfig:
    country_code: str = "DE"  # Germany as default

class ElectricityPriceFeatureEngine:
    def __init__(self, country: str = "GB", ...):
```

`FeatureConfig` is the declared configuration dataclass for the feature pipeline, but `ElectricityPriceFeatureEngine` does not read from `FeatureConfig`. The two have different default countries ("DE" vs "GB"), and the actual production system uses the US market (region enum has all 50 US states). Neither "DE" nor "GB" is correct for a US-facing product.

**Impact**: Holiday features (`is_holiday`) are populated using German or British public holidays for all US users, producing incorrect binary indicators. US Thanksgiving, Independence Day, Labor Day, etc. are not recognized.

**Fix**: Set `country_code` default to `"US"` in both classes, or make `ElectricityPriceFeatureEngine` accept a per-region holiday calendar and map US states to the correct US holiday calendar.

---

### P1-ML-08: Backtesting Applies `transform()` Before Data Split, Leaking Future Statistics

**File**: `ml/evaluation/backtesting.py`, lines 218–222

```python
df_features = self.feature_engine.transform(df, target_col=target_col)
```

The backtester calls `transform()` on the full DataFrame (all periods) before beginning the walk-forward loop. If the feature engine's scaler is fitted (from prior training), this may be acceptable — but if `fit()` was called on the full dataset (P0-ML-01 above), the scaler already leaks future statistics. Additionally, seasonal decomposition via `seasonal_decompose()` is computed on the full series, which uses future data to estimate trend and seasonal components at any point in time.

**Impact**: Backtesting MAPE figures are artificially optimistic because trend/seasonal features incorporate future information. The "target achievement" metrics in `BacktestConfig.target_mape` are based on tainted data.

**Fix**: Apply feature engineering within each walk-forward step, fitting only on the available training window.

---

### P1-ML-09: HNSW Index Silently Skips Inserts at 100K Cap Without Alerting

**File**: `backend/services/hnsw_vector_store.py`, lines 155–162

```python
if new_size > self._max_elements_cap:
    logger.warning(
        "hnsw_index_at_cap max=%d", self._max_elements_cap
    )
    return vec_id  # Skip HNSW, still in SQLite
```

When the HNSW index reaches 100,000 elements, new vectors are silently accepted into SQLite but not added to the HNSW index. After this point:
- HNSW search is used (index exists, count > 0) but returns results only from the first 100K vectors.
- New bias correction vectors are never searchable via HNSW.
- The search method has no way to distinguish "index contains all vectors" from "index is incomplete."

**Impact**: After 100K vectors, search quality degrades silently. Bias corrections stored after the cap are never retrieved by the learning service.

**Fix**: Log an alert and fall back to brute-force VectorStore.search() when the index is known to be incomplete (add an `_index_complete: bool` flag), or implement index eviction.

---

## P2 — Medium

### P2-ML-01: No Feature Drift Detection Anywhere in the Pipeline

No file in `ml/` or `backend/services/` implements feature drift detection. The `LearningService` computes output accuracy (MAPE on predictions vs. actuals) but does not monitor input feature distributions. There is no comparison of:
- Current feature means/stdevs vs. training-time statistics stored in `metadata.yaml`'s `input_ranges`.
- Population Stability Index (PSI) or Jensen-Shannon divergence on input features.
- Data Quality alerts when features fall outside `_input_ranges` bounds (currently only a warning log in `predictor.py:predict()`, line 265–272).

**Impact**: Silent model degradation when electricity price regimes shift (e.g., energy crisis, policy change, new renewable capacity). The 30-day stale model warning is the only monitoring in place.

**Fix**: Add a `FeatureDriftDetector` service that runs alongside `LearningService.run_full_cycle()`, computing PSI on critical features (price, temperature) against training baselines stored in `metadata.yaml`.

---

### P2-ML-02: `min_periods=1` in Rolling Features Produces Misleading Early-Window Stats

**File**: `ml/data/feature_engineering.py`, lines 174–197

All rolling windows use `min_periods=1`:
```python
df[target_col].rolling(window=window, min_periods=1).std()
```

A standard deviation computed on 1 sample returns `NaN` in pandas. With `min_periods=1`, the first `window-1` values of rolling stats are computed on partial windows. The rolling std on window=168 for row 0 is the std of one value (NaN), which then gets forward-filled. The first 168 hours of training sequences include "statistics" that are based on incomplete data.

**Impact**: The initial sequences in every training run contain degraded features. For a 1-year (8760 hour) dataset, approximately 2% of training sequences are affected.

**Fix**: Use `min_periods=window` and drop or handle the resulting NaN rows, or explicitly pad with zeros and mark with an `is_padded` indicator feature.

---

### P2-ML-03: `seasonal_decompose` Applied in `transform()` Uses Full-Series Statistics

**File**: `ml/data/feature_engineering.py`, lines 255–267

`statsmodels.seasonal_decompose` with `model='additive'` is applied to the entire price series passed to `transform()`. The seasonal component extracted at time `t` depends on data at `t + k` for future lags (symmetric filter). This is not causal and constitutes a subtle form of look-ahead bias.

**Impact**: `seasonal_component`, `trend_component`, `residual_component` features contain non-causal information. Any model trained with these features cannot replicate production behavior where only past data is available.

**Fix**: Use a causal decomposition (e.g., centered moving average only on past data) or STL decomposition with `robust=True` in causal mode.

---

### P2-ML-04: `XGBoostForecaster` Uses `early_stopping_rounds` Without Validation Set

**File**: `ml/models/ensemble.py`, lines 213–229

```python
return xgb.XGBRegressor(
    ...
    early_stopping_rounds=self.config.early_stopping_rounds,  # 50
    ...
)
```

`early_stopping_rounds` on `XGBRegressor` requires `eval_set` during `fit()`. When `X_val is None`, the code calls `model.fit(X_flat, y[:, step])` without an `eval_set`, which will either raise an error or silently ignore `early_stopping_rounds` depending on the XGBoost version. With XGBoost 2.x, this raises `ValueError: Must have at least 1 validation dataset for early stopping`.

**Impact**: XGBoost training will fail when called without a validation set, causing the ensemble to fall back to CNN-LSTM only.

**Fix**: Remove `early_stopping_rounds` from `_create_model()` and apply it only at `fit()` time when a validation set is provided:
```python
if X_val is not None:
    model.fit(X_flat, y[:, step], eval_set=[(X_val_flat, y_val[:, step])], early_stopping_rounds=50)
else:
    model.fit(X_flat, y[:, step])
```

---

### P2-ML-05: LightGBM Booster Loaded Without Wrapper, Breaking `predict()` Interface

**File**: `ml/models/ensemble.py`, lines 366–375

```python
model = lgb.Booster(model_file=model_path)
self.models.append(model)
```

`LightGBMForecaster.load()` loads models as `lgb.Booster` objects, but `predict()` calls `model.predict(X_flat)` which works on `Booster` directly. However, `get_feature_importance()` calls `model.feature_importances_` (line 334), which is an attribute of `LGBMRegressor`, not `lgb.Booster`. After a save/load cycle, `get_feature_importance()` will raise `AttributeError: 'Booster' object has no attribute 'feature_importances_'`.

**Impact**: Feature importance retrieval fails after model reload. Any monitoring or explainability workflow that calls `get_feature_importance()` post-load will crash.

**Fix**: Either save/load as `LGBMRegressor` (using `joblib`) or use `model.feature_importance(importance_type='gain')` for the `lgb.Booster` API.

---

### P2-ML-06: `optimal-times` Endpoint Computes `duration_slots` Incorrectly

**File**: `backend/routers/predictions.py`, lines 504–511

```python
duration_slots = int(request.duration_hours * 4)  # 15-min intervals
for i in range(len(predictions) - duration_slots + 1):
    window = predictions[i:i + duration_slots]
```

The `predictions` list contains **hourly** predictions (one per hour from `generate_price_forecast`). Converting to 15-minute slots by multiplying by 4 is incorrect: `duration_slots` will be 4x too large. For a 2-hour appliance, `duration_slots = 8`, but there are only 24 hourly predictions. The sliding window will find very few valid windows and may return zero slots for requests over 6 hours.

**Impact**: The `/predict/optimal-times` endpoint returns incorrect optimal windows. `total_cost` calculation (line 511) divides by `len(window)` which compounds the error.

**Fix**: Remove the `* 4` multiplier since predictions are already hourly: `duration_slots = max(1, int(request.duration_hours))`.

---

### P2-ML-07: Bias Correction Vector Is Stored But Never Applied to Predictions

**File**: `backend/services/learning_service.py`, lines 320–366

`store_bias_correction()` stores an hourly bias correction vector in the HNSW vector store. However, no code in `ml/inference/predictor.py`, `ml/inference/ensemble_predictor.py`, or `backend/routers/predictions.py` queries the vector store to retrieve and apply bias corrections before returning predictions to users.

**Impact**: The entire bias correction pipeline is implemented but disconnected. Systematic prediction errors identified by the learning service are detected but never corrected, meaning users receive systematically biased price forecasts.

**Fix**: In `generate_price_forecast()` or `EnsemblePredictor.predict()`, query the vector store for the most recent bias correction for the relevant region and subtract it from the raw predictions.

---

### P2-ML-08: `_load_model()` Is Synchronous and Blocks the Event Loop

**File**: `backend/routers/predictions.py`, lines 199–244

`_load_model()` is a synchronous function called from the async route handler `generate_price_forecast()`:

```python
async def generate_price_forecast(...) -> List[PricePrediction]:
    model = _load_model()  # Synchronous, may do disk I/O
```

Model loading involves disk I/O (`os.path.isdir()`, `yaml.safe_load()`, `torch.load()`). These operations can block the asyncio event loop for hundreds of milliseconds on the first load, degrading all concurrent requests.

**Impact**: First-request latency spike (potentially seconds) that blocks all other async requests in the same event loop.

**Fix**: Wrap `_load_model()` in `await asyncio.to_thread(_load_model)` or load the model at application startup in a lifespan event.

---

### P2-ML-09: `create_dummy_data` Uses `np.random.seed(42)` — Not Isolated Between Tests

**File**: `ml/data/feature_engineering.py`, lines 531

```python
np.random.seed(42)
```

The module-level function `create_dummy_data()` mutates the global NumPy random state. Any test that calls this function changes subsequent random number generation for all other tests in the same process. This causes test non-determinism when test ordering changes.

**Impact**: Test reliability issue. Tests may pass or fail depending on execution order.

**Fix**: Use `np.random.default_rng(42)` (isolated generator) instead of seeding the global state.

---

### P2-ML-10: No Automated Retraining — `retrain_frequency` in Backtesting Is Not Wired to Production

**File**: `ml/evaluation/backtesting.py`, lines 265–277

The backtester supports retraining within the walk-forward loop (`retrain_frequency` config), but the production pipeline has no automated retraining mechanism. The CLAUDE.md notes "nightly-learning" which only updates ensemble weights (not the underlying models). The CNN-LSTM and XGBoost/LightGBM models are trained once (via the manual `train_forecaster.py` script) and never retrained.

**Impact**: Models will suffer performance decay as electricity market conditions evolve. The 30-day staleness warning in `predictor.py` will trigger but no automatic remediation occurs.

**Fix**: Implement an automated retraining GHA workflow triggered weekly, gated by evaluation on held-out data, with automatic promotion only if MAPE improves.

---

### P2-ML-11: Agent Prompt Logged to DB Without Sanitization — Secondary Injection Risk

**File**: `backend/services/agent_service.py`, lines 372–401

```python
await db.execute(
    text("""
        INSERT INTO agent_conversations (user_id, prompt, ...)
        VALUES (:user_id, :prompt, ...)
    """),
    {"user_id": user_id, "prompt": prompt, ...},
)
```

The raw user prompt is stored in `agent_conversations` with parameterized SQL (correct), but:
1. If conversation logs are ever read and fed back into subsequent LLM calls (e.g., for multi-turn context), a stored adversarial prompt becomes a persistent injection vector.
2. The `response` field stores the raw LLM output, which could contain injected instructions to future processing.

**Impact**: Stored prompt injection if conversation history is ever used as LLM context. Currently low risk since `query_streaming()` does not use history, but the risk increases with any future multi-turn feature.

**Fix**: Store prompts with a flag indicating they are untrusted user input. If multi-turn context is added, sanitize user content before inclusion in the system prompt.

---

### P2-ML-12: MAPE Formula Uses `+1e-8` Epsilon Inconsistently Across Files

The MAPE formula varies in three different places:

- `ml/evaluation/metrics.py` line 132: masks zeros (`y_true[mask]`) — most correct
- `ml/evaluation/backtesting.py` line 101: `(np.abs(y_true) + epsilon)` — acceptable
- `ml/models/price_forecaster.py` line 199: `(self.y_val + 1e-8)` — only adds epsilon to positive y_val, will fail for y_val < 0
- `ml/inference/ensemble_predictor.py` line 396: `(actuals + 1e-8)` — same issue as above

For electricity markets with negative prices (European markets), `y_val + 1e-8` still produces a negative denominator, yielding a negative MAPE that is meaningless.

**Impact**: Metrics reported during training (`MAPECallback`) and backtesting are wrong for negative-price electricity data. Target achievement checks (`mape <= target_mape`) may incorrectly pass or fail.

**Fix**: Use a consistent formula: `np.abs((y_true - y_pred) / (np.abs(y_true) + 1e-8))`.

---

## P3 — Low

### P3-ML-01: `FeatureConfig` Dataclass Is Never Used by `ElectricityPriceFeatureEngine`

**File**: `ml/data/feature_engineering.py`, lines 36–64

`FeatureConfig` is defined but never passed to or used by `ElectricityPriceFeatureEngine`. All configuration (sequence lengths, lag windows, rolling windows, scaling method) is hardcoded inside the engine or set via constructor parameters. `FeatureConfig` is dead code.

**Impact**: Developers may assume `FeatureConfig.price_lags` controls the actual lags used, but it has no effect.

**Fix**: Either wire `FeatureConfig` into `ElectricityPriceFeatureEngine.__init__()` or remove it.

---

### P3-ML-02: `get_feature_importance_names()` Returns Hardcoded List That May Not Match Actual Features

**File**: `ml/data/feature_engineering.py`, lines 480–510

`get_feature_importance_names()` returns a hardcoded list of feature names that does not necessarily match what `transform()` actually produces. The hardcoded list includes `price_lag_1h` through `price_lag_168h` but `create_lag_features()` by default creates `price_lag_1h` through `price_lag_48h` (not `168h` unless lags=[1,2,3,24,48,168]).

**Impact**: Feature importance analysis uses incorrect feature labels, making model interpretability unreliable.

**Fix**: Derive feature names from `self.feature_names_` (set after fitting) rather than a hardcoded list.

---

### P3-ML-03: `optuna.suggest_loguniform` Is Deprecated

**File**: `ml/training/hyperparameter_tuning.py`, line 82

```python
'learning_rate': trial.suggest_loguniform('learning_rate', ...)
```

`suggest_loguniform` was deprecated in Optuna v3.0 in favor of `trial.suggest_float(..., log=True)`.

**Impact**: `DeprecationWarning` during hyperparameter tuning. Will break in Optuna v4+.

**Fix**: Replace with `trial.suggest_float('learning_rate', min_val, max_val, log=True)`.

---

### P3-ML-04: Hyperparameter Tuning Holds All Training Data in Memory During Trials

**File**: `ml/training/hyperparameter_tuning.py`, lines 127–135

`HyperparameterTuner` stores full `X_train`, `y_train`, `X_val`, `y_val` arrays as instance attributes. For 1 year of data with 168-step sequences and 50+ features, `X_train` alone is approximately `(7000, 168, 50) * 4 bytes ≈ 235 MB`. With 50–100 Optuna trials all sharing this instance, peak memory during tuning is in the multi-GB range with GPU model copies.

**Impact**: Hyperparameter tuning may OOM on the Render free-tier instance (512 MB RAM).

**Fix**: Use generators or memory-mapped arrays; or use Optuna's pruning to terminate trials early.

---

### P3-ML-05: `_simulate_forecast` Uses `np.random.normal` Without Seeding — Non-Deterministic

**File**: `backend/routers/predictions.py`, lines 247–268

The simulation fallback calls `np.random.normal(0, 0.01)` with no seed, producing different "prices" on every call. A user who requests the same forecast twice will receive different results, making it impossible to debug or reproduce issues.

**Impact**: Support and debugging of forecast issues is hampered.

**Fix**: Seed with a deterministic function of `(region, timestamp_hour)` so the simulation is stable for a given hour.

---

### P3-ML-06: No Gradient Clipping in CNN-LSTM Training

**File**: `ml/training/cnn_lstm_trainer.py`, lines 337–343

```python
optimizer.zero_grad()
output = self.model(batch_X)
loss = loss_fn(output, batch_y)
loss.backward()
optimizer.step()
```

No gradient clipping is applied. With Bidirectional LSTMs and long sequences (168 timesteps), exploding gradients are a real risk, especially at the start of training.

**Impact**: Training instability, NaN losses, model corruption during early epochs.

**Fix**: Add `torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)` before `optimizer.step()`.

---

### P3-ML-07: `MAPECallback` Calls `self.model.predict()` on Full Validation Set Every Epoch

**File**: `ml/models/price_forecaster.py`, lines 188–204

```python
def on_epoch_end(self, epoch, logs=None):
    y_pred = self.model.predict(self.X_val, verbose=0)
```

`self.X_val` is the full validation set. `model.predict()` is called every epoch (up to 200 epochs) on potentially thousands of samples. TensorFlow's `predict()` method has significant overhead from batching and data copying. This significantly slows training.

**Impact**: Training is 20–50% slower than necessary. For 200 epochs and a validation set of 1000 samples, this adds hours to training time.

**Fix**: Only compute MAPE every 10 epochs (already guarded by `if epoch % 10 == 0` for logging, but prediction is not), or use the `val_loss` from the training loop directly.

---

### P3-ML-08: `save()` in `CNNLSTMTrainer` Saves Full Model Object (Not State Dict)

**File**: `ml/training/cnn_lstm_trainer.py`, line 409

```python
torch.save(self.model, os.path.join(path, "model.pt"))
```

Saving the full model object (not just `state_dict`) couples the saved file to the exact Python class definition. If the `CNNLSTMModel` class is refactored, existing saved models cannot be loaded. This is also the root cause of P0-ML-04 (requiring `weights_only=False`).

**Impact**: Long-term model maintainability and security risk.

**Fix**: Save with `torch.save(self.model.state_dict(), ...)` and load with `model.load_state_dict(torch.load(..., weights_only=True))`.

---

### P3-ML-09: `_get_user_context` and `_get_user_tier` Make Two Separate DB Queries

**File**: `backend/api/v1/agent.py`, lines 65–89

```python
context = await _get_user_context(current_user.user_id, db)
...
context["tier"] = await _get_user_tier(current_user.user_id, db)
```

`_get_user_tier()` queries `SELECT subscription_tier FROM users WHERE id = :id`. `_get_user_context()` queries `SELECT region, subscription_tier FROM users WHERE id = :id`. Two queries fetch the same `subscription_tier` column unnecessarily.

**Impact**: Minor — two round trips to the database per agent request.

**Fix**: Use the tier from `_get_user_context()`: `context["tier"] = context.get("tier") or "free"`.

---

### P3-ML-10: `backtesting.py` Saves Predictions and Results With `datetime.now()` (Not UTC)

**File**: `ml/evaluation/backtesting.py`, line 492

```python
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
```

Uses local time, not UTC. On a server in a non-UTC timezone, file timestamps will be misleading and may collide if timezone changes (DST).

**Fix**: Use `datetime.now(timezone.utc)`.

---

### P3-ML-11: `observe-forecasts` Endpoint Returns Raw Exception Message in 500 Response

**File**: `backend/api/v1/internal/ml.py`, line 75

```python
raise HTTPException(status_code=500, detail=f"Observation failed: {str(e)}")
```

Raw exception messages may contain database schema details, internal paths, or sensitive data in error responses on internal endpoints. Other internal endpoints follow the same pattern (lines 109, 136).

**Impact**: Information leakage in error responses.

**Fix**: Log the full exception server-side; return a generic message to callers: `"Observation failed. See server logs."`.

---

### P3-ML-12: `MaxPooling1D` in CNN-LSTM Reduces Sequence Length by Half Per Layer — Unchecked

**File**: `ml/models/price_forecaster.py`, lines 249–254
**File**: `ml/training/cnn_lstm_trainer.py`, lines 154–158

MaxPooling with `pool_size=2` is applied every other CNN layer. With `sequence_length=168` and 3 CNN layers (pooling at layer 1 only), the sequence dimension after pooling is `168/2 = 84`. This is implicitly assumed but never validated. If kernel_size=5 and padding='same' does not exactly preserve length (edge cases), the sequence dimension passed to LSTM may be wrong.

In `cnn_lstm_trainer.py`, the sequence length is tracked manually:
```python
sequence_length = sequence_length // 2  # line 158
```
But in the PyTorch forward pass, if `sequence_length` starts at a non-power-of-2 value (e.g., 168), three halvings would give 168 → 84 → 42 → 21. The trainer only applies pooling per conv layer in the ModuleList but the manual tracking variable `sequence_length` (used only for logging) may diverge from actual dimensions.

**Impact**: Potential shape mismatch in the attention layer if `embed_dim` is miscalculated.

**Fix**: Add an assertion: `assert x.shape[1] == expected_seq_len` after the CNN stack.

---

## Summary Table

| ID | Severity | Category | File(s) |
|----|----------|----------|---------|
| P0-ML-01 | P0 | Data Leakage | `ml/data/feature_engineering.py`, `ml/training/train_forecaster.py` |
| P0-ML-02 | P0 | Data Leakage | `ml/data/feature_engineering.py:436-439` |
| P0-ML-03 | P0 | Prediction Correctness | `ml/inference/predictor.py:299-319` |
| P0-ML-04 | P0 | Security | `ml/inference/predictor.py:138-144` |
| P0-ML-05 | P0 | Model Correctness | `ml/training/cnn_lstm_trainer.py:104-110` |
| P1-ML-01 | P1 | Reliability | `backend/services/learning_service.py:147-154` |
| P1-ML-02 | P1 | Reliability | `backend/services/hnsw_vector_store.py:116-173` |
| P1-ML-03 | P1 | Reliability | `backend/routers/predictions.py:247-374` |
| P1-ML-04 | P1 | Reliability | `backend/routers/predictions.py:195-244` |
| P1-ML-05 | P1 | Numerical Stability | `ml/data/feature_engineering.py:214-215` |
| P1-ML-06 | P1 | Rate Limiting | `backend/services/agent_service.py:314-342` |
| P1-ML-07 | P1 | Feature Correctness | `ml/data/feature_engineering.py:55,88` |
| P1-ML-08 | P1 | Accuracy | `ml/evaluation/backtesting.py:218-222` |
| P1-ML-09 | P1 | Monitoring | `backend/services/hnsw_vector_store.py:155-162` |
| P2-ML-01 | P2 | Monitoring Gap | Entire pipeline |
| P2-ML-02 | P2 | Feature Quality | `ml/data/feature_engineering.py:174-197` |
| P2-ML-03 | P2 | Data Leakage | `ml/data/feature_engineering.py:255-267` |
| P2-ML-04 | P2 | Training Reliability | `ml/models/ensemble.py:213-229` |
| P2-ML-05 | P2 | Model Load | `ml/models/ensemble.py:366-375` |
| P2-ML-06 | P2 | Prediction Correctness | `backend/routers/predictions.py:504-511` |
| P2-ML-07 | P2 | Feature Gap | `backend/services/learning_service.py:320-366` |
| P2-ML-08 | P2 | Performance | `backend/routers/predictions.py:199-244` |
| P2-ML-09 | P2 | Test Reliability | `ml/data/feature_engineering.py:531` |
| P2-ML-10 | P2 | Operations | Entire pipeline |
| P2-ML-11 | P2 | Security | `backend/services/agent_service.py:372-401` |
| P2-ML-12 | P2 | Metrics | Multiple files |
| P3-ML-01 | P3 | Code Quality | `ml/data/feature_engineering.py:36-64` |
| P3-ML-02 | P3 | Correctness | `ml/data/feature_engineering.py:480-510` |
| P3-ML-03 | P3 | Deprecation | `ml/training/hyperparameter_tuning.py:82` |
| P3-ML-04 | P3 | Resource | `ml/training/hyperparameter_tuning.py:127-135` |
| P3-ML-05 | P3 | Reproducibility | `backend/routers/predictions.py:247-268` |
| P3-ML-06 | P3 | Training Stability | `ml/training/cnn_lstm_trainer.py:337-343` |
| P3-ML-07 | P3 | Performance | `ml/models/price_forecaster.py:188-204` |
| P3-ML-08 | P3 | Maintainability | `ml/training/cnn_lstm_trainer.py:409` |
| P3-ML-09 | P3 | Performance | `backend/api/v1/agent.py:65-89` |
| P3-ML-10 | P3 | Correctness | `ml/evaluation/backtesting.py:492` |
| P3-ML-11 | P3 | Security | `backend/api/v1/internal/ml.py:75,109,136` |
| P3-ML-12 | P3 | Reliability | `ml/models/price_forecaster.py`, `ml/training/cnn_lstm_trainer.py` |

---

## Prioritized Remediation Order

1. **P0-ML-01 + P0-ML-02** (Data Leakage): Fix scaler fitting before any evaluation metrics can be trusted.
2. **P0-ML-04** (Arbitrary Code Execution): Migrate to state-dict + `weights_only=True` before any production model file is deployed.
3. **P0-ML-05** (Fabricated Confidence Intervals): Remove fictional ±10% bounds; use proper quantile regression.
4. **P0-ML-03** (Recursive Inference): Fix temporal feature propagation for multi-step GBM predictions.
5. **P1-ML-01** (Weight Key Mismatch): The learning pipeline is currently a no-op; this fix makes adaptive learning work.
6. **P1-ML-02** (Thread Safety): Add locks before HNSW reaches production scale.
7. **P1-ML-03** (Silent Simulation): Expose simulation state to callers.
8. **P2-ML-06** (15-min vs hourly): Fix the obvious 4x error in optimal-times window calculation.
9. **P2-ML-07** (Bias Correction Not Applied): Wire bias correction into the prediction path.
10. **P1-ML-07** (Wrong Holiday Calendar): Use US holidays for US users.
