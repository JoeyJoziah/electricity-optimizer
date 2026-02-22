# ML and Optimization Layer -- Specification & Pseudocode

> Spec ID: 03
> Status: Draft
> Last updated: 2026-02-22
> Modules: `ml/`, `backend/routers/predictions.py`, `backend/services/vector_store.py`

---

## 1. ML Architecture Overview

### 1.1 System Diagram

```
                       +-------------------+
                       | Predictions Router |  (FastAPI)
                       | /predict/price     |
                       | /predict/optimal   |
                       | /predict/savings   |
                       +---------+---------+
                                 |
               +-----------------+-----------------+
               |                                   |
    +----------v----------+             +----------v----------+
    | EnsemblePredictor   |             | MILP Optimizer      |
    | (inference layer)   |             | (PuLP / CBC)        |
    +---+------+------+---+             +-----------+---------+
        |      |      |                             |
   +----+  +---+  +---+----+          +-------------+----------+
   |CNN- | |XGB | |LightGBM|          | ApplianceScheduler     |
   |LSTM | |    | |         |          | ConstraintBuilder      |
   +--+--+ +---++ +---+----+          | ObjectiveBuilder       |
      |        |       |               +-----------+----------+
      +--------+-------+                           |
               |                        +-----------+----------+
    +----------v----------+             | SwitchingDecisionEng |
    | FeatureEngine       |             +----------------------+
    | (data pipeline)     |
    +----------+----------+
               |
    +----------v----------+
    | VectorStore         |
    | (pattern matching)  |
    +---------------------+
```

### 1.2 Model Inventory

| Model | Framework | Input Shape | Output Shape | Target Metric |
|-------|-----------|-------------|--------------|---------------|
| CNN-LSTM (TF) | TensorFlow/Keras | `(batch, 168, 19)` | `(batch, 24, 3)` | MAPE < 10% |
| CNN-LSTM (PyTorch) | PyTorch | `(batch, 168, N)` | `(batch, 24, 3)` | MAPE < 10% |
| XGBoost | xgboost | `(batch, 168*N)` | `(batch, 24)` | Ensemble member |
| LightGBM | lightgbm | `(batch, 168*N)` | `(batch, 24)` | Ensemble member |
| Ensemble | N/A | `(batch, 168, N)` | `(batch, 24)` | MAPE < 10% |

### 1.3 Dual-Framework Design

The codebase contains two CNN-LSTM implementations:

- **`ml/models/price_forecaster.py`** -- TensorFlow/Keras implementation used by
  `ElectricityPriceForecaster`. Compiles with `QuantileLoss` for direct probabilistic
  output (3 quantiles: lower, median, upper).
- **`ml/training/cnn_lstm_trainer.py`** -- PyTorch implementation used by `CNNLSTMTrainer`.
  Trains with MSE loss on a 3-output target (point, lower, upper). Saves as `.pt` files.

The inference layer (`ml/inference/predictor.py`) auto-detects framework from saved
artifacts (`model.pt` = PyTorch, `model.keras` = TensorFlow).

---

## 2. Price Forecasting -- CNN-LSTM with Attention

### 2.1 Architecture Detail

```
Layer                    Shape Transformation              Notes
------------------------------------------------------------------
Input                    (B, 168, 19)                      7 days hourly, 19 features
Conv1D block 0           (B, 168, 64)  k=3, pad=same      + BatchNorm + ReLU
Conv1D block 1           (B, 168, 128) k=5, pad=same      + BatchNorm + ReLU + MaxPool(2)
Conv1D block 2           (B, 84, 64)   k=3, pad=same      + BatchNorm + ReLU
MultiHeadAttention       (B, 84, 64)   heads=4, key=32    Self-attn + residual + LayerNorm
Bidirectional LSTM 0     (B, 84, 256)  units=128 x2       return_sequences=True
Bidirectional LSTM 1     (B, 128)      units=64 x2        return_sequences=False
Dense 0                  (B, 64)       + dropout(0.3)
Dense 1                  (B, 32)       + dropout(0.3)
Output Dense             (B, 72)       24 * 3
Reshape                  (B, 24, 3)    [lower, median, upper]
```

### 2.2 Quantile Loss Function

The model predicts three quantiles simultaneously: `q_lower` (0.05), `q_median` (0.5),
`q_upper` (0.95) for a 90% confidence interval.

```
FUNCTION QuantileLoss(y_true, y_pred, quantiles=[0.05, 0.5, 0.95]):
    y_expanded = expand_dims(y_true, axis=-1)      // (B, 24, 1)
    total_loss = 0

    FOR i, q IN enumerate(quantiles):
        pred_q = y_pred[:, :, i:i+1]               // (B, 24, 1)
        error = y_expanded - pred_q
        loss_q = max(q * error, (q - 1) * error)   // asymmetric penalty
        total_loss += mean(loss_q)

    RETURN total_loss
```

### 2.3 Training Pipeline Pseudocode

```
FUNCTION train_forecaster(config):
    // 1. Data loading
    df = load_data(config.data_path)                  // DateTimeIndex + price column
        OR create_dummy_data(config.dummy_data_hours)

    // 2. Feature engineering
    engine = ElectricityPriceFeatureEngine(country=config.country_code)
    engine.fit(df)
    df_features = engine.transform(df)

    // 3. Sequence creation
    X, y = engine.create_sequences(df_features)       // X: (N, 168, F), y: (N, 24)

    // 4. Temporal split (no shuffle -- time series)
    split at 70% / 15% / 15%
    X_train, X_val, X_test = split(X)
    y_train, y_val, y_test = split(y)

    // 5. Build CNN-LSTM model
    model = create_cnn_lstm_model(ModelConfig(
        sequence_length=168,
        num_features=X.shape[2],
        forecast_horizon=24,
        num_quantiles=3
    ))
    model.compile(optimizer=Adam(lr=0.001), loss=QuantileLoss)

    // 6. Training with callbacks
    callbacks = [
        EarlyStopping(patience=20, restore_best_weights=True),
        ReduceLROnPlateau(factor=0.5, patience=10, min_lr=1e-6),
        ModelCheckpoint(save_best_only=True),
        MAPECallback(validation_data=(X_val, y_val))
    ]
    model.fit(X_train, y_train, validation=(X_val, y_val),
              epochs=200, batch_size=32, callbacks=callbacks)

    // 7. Ensemble training (optional)
    IF config.train_ensemble:
        xgb = XGBoostForecaster(n_estimators=200)  // per-step models
        lgb = LightGBMForecaster(n_estimators=200)
        FOR step IN 0..23:
            xgb.models[step].fit(flatten(X_train), y_train[:, step])
            lgb.models[step].fit(flatten(X_train), y_train[:, step])

    // 8. Evaluation
    predictions, lower, upper = model.predict(X_test)
    metrics = evaluate(y_test, predictions)           // MAE, RMSE, MAPE, coverage
    ASSERT metrics.mape <= config.target_mape         // target: 10%

    // 9. Persist
    model.save(config.output_dir)
    RETURN metrics
```

### 2.4 Inference Flow Pseudocode

```
FUNCTION predict_prices(region, hours_ahead, session):
    // 1. Try cache first
    cached = redis.get("forecast:{region}:{hours_ahead}")
    IF cached: RETURN cached

    // 2. Load model (cached in process memory)
    model = load_model()   // EnsemblePredictor or PricePredictor or None

    // 3. Fetch features from DB
    rows = SELECT price, hour, day_of_week, is_peak, carbon_intensity
           FROM prices WHERE region = {region}
           ORDER BY timestamp DESC LIMIT 168

    IF model IS None OR rows IS empty:
        RETURN simulate_forecast(region, hours_ahead)   // sinusoidal fallback

    // 4. Build feature DataFrame
    features_df = DataFrame(reversed(rows))

    // 5. Run inference
    result = model.predict(features_df, horizon=hours_ahead)
    // result = { point: ndarray(H,), lower: ndarray(H,), upper: ndarray(H,) }

    // 6. Package response
    predictions = []
    FOR i IN 0..hours_ahead:
        predictions.append(PricePrediction(
            timestamp=now + (i+1) hours,
            predicted_price=result.point[i],
            confidence_lower=result.lower[i],
            confidence_upper=result.upper[i],
            currency=region_currency_map[region]
        ))

    // 7. Cache for 1 hour
    redis.setex("forecast:{region}:{hours_ahead}", 3600, predictions)
    RETURN predictions
```

---

## 3. MILP Optimization -- Appliance Scheduling

### 3.1 Problem Formulation

**Decision variables:** Binary `x[a,t]` for each appliance `a` and 15-minute time
slot `t` (96 slots per day). `x[a,t] = 1` means appliance `a` runs during slot `t`.

**Objective:** Minimize weighted sum of:
- Primary: electricity cost
- Secondary (optional): peak power, interruption penalties, load balancing

**Constraints:** duration, time window, continuity, power limits, dependencies,
mutual exclusion.

### 3.2 Objective Function Pseudocode

```
FUNCTION build_objective(problem, appliances, variables, prices, config):
    builder = ObjectiveBuilder(problem, config)

    // Primary: minimize electricity cost
    cost = 0
    FOR a IN appliances:
        FOR t IN 0..95:
            cost += prices[t] * a.power_kw * 0.25 * x[a,t]  // 0.25h per slot
    builder.add("electricity_cost", cost, weight=1.0)

    // Optional: minimize peak power
    IF minimize_peak:
        peak_var = ContinuousVar("peak_power", lb=0)
        FOR t IN 0..95:
            problem += peak_var >= SUM(a.power_kw * x[a,t] for a in appliances)
        builder.add("peak_power", peak_var, weight=0.1)

    // Optional: interruption penalty
    IF minimize_interruptions:
        FOR a IN interruptible_appliances:
            FOR t IN 0..94:
                diff[a,t] = ContinuousVar(lb=0)
                problem += diff[a,t] >= x[a,t] - x[a,t+1]
            builder.add("interruption", 0.05 * SUM(diff), weight=1.0)

    // Optional: load balancing
    IF balance_load:
        avg_power = total_energy / (96 * 0.25)
        FOR t IN 0..95:
            dev[t] = ContinuousVar(lb=0)
            problem += dev[t] >= power_at_t - avg_power
            problem += dev[t] >= avg_power - power_at_t
        builder.add("balance", 0.01 * SUM(dev), weight=1.0)

    // Always: small preference penalty (favor earlier slots for high priority)
    FOR a IN appliances:
        penalty = SUM(priority_weight[a] * (t/96) * x[a,t] * 0.001)
    builder.add("preference", penalty, weight=1.0)

    problem.minimize(SUM(weight * expr for each term))
```

### 3.3 Constraint Pseudocode

```
FUNCTION build_constraints(problem, appliances, variables, config):

    FOR a IN appliances:
        slots = variables[a.name]

        // C1 -- Duration: appliance runs exactly required time
        problem += SUM(slots.values()) == a.duration_slots

        // C2 -- Time window: zero out invalid slots
        valid = a.get_valid_slots(96)
        FOR t NOT IN valid:
            problem += slots[t] == 0

        // C3 -- Continuity (for must_be_continuous appliances)
        IF a.must_be_continuous:
            create start_vars[t] for each feasible start position
            problem += SUM(start_vars) == 1            // exactly one start
            FOR each start_var at position t:
                FOR offset IN 0..duration-1:
                    problem += slots[t+offset] >= start_vars[t]

        // C4 -- Minimum chunk size (for interruptible appliances)
        IF a.can_be_interrupted AND min_chunk > 1:
            FOR t IN 0..95:
                FOR offset IN 1..min_chunk-1:
                    problem += slots[t+offset] >= slots[t] - slots[t-1]

        // C5 -- Max interruptions
        IF NOT a.must_be_continuous:
            stop_vars = []
            FOR t IN 0..95:
                stop[t] = BinaryVar()
                problem += stop[t] >= slots[t] - slots[t+1]
            problem += SUM(stop_vars) <= a.max_interruptions + 1

    // C6 -- Power limit (global)
    IF config.max_total_power_kw IS NOT None:
        FOR t IN 0..95:
            problem += SUM(a.power_kw * x[a,t]) <= config.max_total_power_kw

    // C7 -- Dependencies: predecessor must finish before successor
    FOR (pred, succ) IN dependencies:
        FOR t < pred.duration_slots + gap:
            problem += SUM(succ_vars[0..t]) == 0

    // C8 -- Mutual exclusion
    FOR (a1, a2) IN mutual_exclusions:
        FOR t IN 0..95:
            problem += x[a1,t] + x[a2,t] <= 1
```

### 3.4 Appliance Model Defaults

| Type | Power (kW) | Duration (h) | Continuous | Interruptible |
|------|-----------|-------------|-----------|--------------|
| Dishwasher | 1.5 | 2.0 | Yes | No |
| Washing Machine | 2.0 | 1.5 | Yes | No |
| Dryer | 3.0 | 1.0 | Yes | No |
| EV Charger | 7.0 | 6.0 | No | Yes |
| Pool Pump | 1.2 | 4.0 | No | Yes |
| Water Heater | 4.0 | 2.0 | No | Yes |
| HVAC | 3.5 | 8.0 | No | Yes |

### 3.5 Solver Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `time_slots` | 96 | 15-min intervals over 24 hours |
| `slot_duration_hours` | 0.25 | Hours per slot |
| `max_solve_time_seconds` | 5.0 | CBC solver time limit |
| `mip_gap` | 0.01 | 1% optimality gap tolerance |
| `solver_name` | "CBC" | Bundled with PuLP |

### 3.6 Performance Targets

- **FR-OPT-001**: Achieve >= 15% cost savings on TOU pricing (3.5x peak/off-peak ratio).
- **FR-OPT-002**: Achieve >= 15% average savings across 5 real-time pricing scenarios.
- **NFR-OPT-001**: Solve time < 5 seconds for up to 7 appliances.
- **NFR-OPT-002**: All constraint violations detected and reported post-solve.

---

## 4. Vector Store -- Price Pattern Matching

### 4.1 Storage Schema

```sql
CREATE TABLE vectors (
    id              TEXT PRIMARY KEY,       -- sha256(domain:vector_bytes)[:16]
    domain          TEXT NOT NULL,           -- 'price_pattern' | 'optimization' | 'recommendation'
    vector          BLOB NOT NULL,           -- float32 array, dimension=24
    metadata        TEXT DEFAULT '{}',       -- JSON blob
    confidence      REAL DEFAULT 1.0,        -- success_count / usage_count
    usage_count     INTEGER DEFAULT 0,
    success_count   INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    last_used       TEXT NOT NULL
);
CREATE INDEX idx_vectors_domain ON vectors(domain);
CREATE INDEX idx_vectors_confidence ON vectors(confidence DESC);
```

### 4.2 Cosine Similarity Search Pseudocode

```
FUNCTION search(query_vector, domain=None, k=5, min_similarity=0.7):
    // 1. Normalize query to store dimension (pad or truncate to 24)
    query = resize(query_vector, dimension=24)

    // 2. Fetch candidate vectors
    IF domain:
        rows = SELECT * FROM vectors WHERE domain = {domain}
    ELSE:
        rows = SELECT * FROM vectors

    // 3. Brute-force cosine similarity (sufficient for hundreds of patterns)
    results = []
    FOR row IN rows:
        stored = bytes_to_float32(row.vector)
        sim = dot(query, stored) / (norm(query) * norm(stored))
        IF sim >= min_similarity:
            results.append({id, domain, similarity, confidence, metadata})

    // 4. Sort by similarity descending, take top k
    results.sort(by=similarity, desc=True)
    results = results[:k]

    // 5. Update usage counts
    FOR r IN results:
        UPDATE vectors SET usage_count += 1, last_used = now() WHERE id = r.id

    RETURN results
```

### 4.3 Outcome Tracking Pseudocode

```
FUNCTION record_outcome(vector_id, success):
    IF success:
        UPDATE vectors SET success_count += 1 WHERE id = vector_id

    row = SELECT usage_count, success_count FROM vectors WHERE id = vector_id
    new_confidence = row.success_count / row.usage_count
    UPDATE vectors SET confidence = new_confidence WHERE id = vector_id
```

### 4.4 Domain-Specific Helpers

**Price curve vectorization:**
```
FUNCTION price_curve_to_vector(prices, target_dim=24):
    arr = float32(prices)
    IF len(arr) != target_dim:
        arr = interpolate(arr, target_dim)      // linear resampling
    norm = l2_norm(arr)
    IF norm > 0: arr = arr / norm               // unit vector for cosine sim
    RETURN arr
```

**Appliance config vectorization:**
```
FUNCTION appliance_config_to_vector(appliances, target_dim=24):
    vec = zeros(target_dim)
    FOR i, app IN enumerate(appliances[:8]):     // max 8 appliances
        base = i * 3
        vec[base]     = app.power_kw
        vec[base + 1] = app.duration_hours
        vec[base + 2] = app.earliest_start / 24.0
    RETURN normalize(vec)
```

### 4.5 Cache Layer

- **In-memory LRU cache**: `OrderedDict` with configurable `cache_size` (default 500).
- **Eviction**: FIFO when cache exceeds `cache_size`.
- **Thread safety**: `threading.Lock` guards all cache mutations.
- **Pruning**: `prune(min_confidence=0.3, min_usage=0)` removes low-quality vectors.

---

## 5. Data Pipeline -- Feature Engineering

### 5.1 Feature Groups

| Group | Features | Count |
|-------|----------|-------|
| Temporal | hour, day_of_week, month, quarter, week_of_year, is_weekend, is_holiday | 7 |
| Cyclical | hour_sin, hour_cos, dow_sin, dow_cos, month_sin, month_cos | 6 |
| Peak indicators | is_morning_peak, is_evening_peak, is_night | 3 |
| Lag | price_lag_{1,2,3,24,48,168}h | 6 |
| Rolling | rolling_{mean,std,min,max,range}_{3,6,12,24,168}h | 25 |
| Price dynamics | change_{1,3,24}h, pct_change_{1,24}h, momentum_{3,24}h, volatility_24h, dist_from_mean_24h | 8 |
| Seasonal decomposition | seasonal_component, trend_component, residual_component | 3 |
| Weather (optional) | temperature, wind_speed, solar_radiation, cloud_cover, heating_degree, cooling_degree, temp_change_{1,24}h, renewable_potential, wind_power_potential | 9 |
| Generation (optional) | load_forecast, renewable_percentage, fossil_percentage, nuclear_percentage, renewable_volatility, is_high_renewable | 6 |
| Demand proxy | demand_proxy_hour, demand_proxy_adjusted | 2 |

**Total features (all groups):** ~75. Base features (without weather/generation): ~58.

### 5.2 Pipeline Pseudocode

```
FUNCTION transform(df, target_col='price'):
    REQUIRE df.index IS DateTimeIndex

    // Phase 1: Temporal features
    df['hour'] = df.index.hour
    df['hour_sin'] = sin(2*pi*hour/24)
    df['hour_cos'] = cos(2*pi*hour/24)
    df['is_weekend'] = (dayofweek >= 5)
    df['is_holiday'] = date IN holiday_calendar[country]
    // ... (15 temporal + cyclical features)

    // Phase 2: Lag features
    FOR lag IN [1, 2, 3, 24, 48, 168]:
        df[f'price_lag_{lag}h'] = df['price'].shift(lag)

    // Phase 3: Rolling statistics
    FOR window IN [3, 6, 12, 24, 168]:
        df[f'rolling_mean_{window}h'] = df['price'].rolling(window).mean()
        df[f'rolling_std_{window}h']  = df['price'].rolling(window).std()
        df[f'rolling_min_{window}h']  = df['price'].rolling(window).min()
        df[f'rolling_max_{window}h']  = df['price'].rolling(window).max()
        df[f'rolling_range_{window}h'] = max - min

    // Phase 4: Price dynamics
    df['price_change_1h']    = df['price'].diff(1)
    df['price_pct_change_1h'] = df['price'].pct_change(1)
    df['volatility_24h']     = pct_change_1h.rolling(24).std()

    // Phase 5: Seasonal decomposition (additive, period=24)
    IF statsmodels available AND len >= 48:
        decomp = seasonal_decompose(df['price'], period=24)
        df['seasonal_component'] = decomp.seasonal
        df['trend_component']    = decomp.trend
        df['residual_component'] = decomp.resid

    // Phase 6: Weather and generation (if data available)
    df = merge_weather(df, weather_data)
    df = merge_generation(df, generation_data)

    // Phase 7: Clean up
    df.replace([inf, -inf], NaN)
    df.ffill().bfill()

    // Phase 8: Scale (if scaler fitted)
    IF scaler IS fitted:
        df[feature_cols] = scaler.transform(df[feature_cols])

    RETURN df
```

### 5.3 Sequence Creation

```
FUNCTION create_sequences(df, target_col, lookback=168, horizon=24):
    X, y = [], []
    FOR i IN 0..(len(df) - lookback - horizon):
        X.append(df[feature_cols].iloc[i : i+lookback].values)   // (168, F)
        y.append(df[target_col].iloc[i+lookback : i+lookback+horizon].values)  // (24,)
    RETURN array(X), array(y)
    // X shape: (N, 168, F)
    // y shape: (N, 24)
```

---

## 6. Model Configuration

### 6.1 CNN-LSTM Hyperparameters

| Parameter | Default | Search Range |
|-----------|---------|-------------|
| `sequence_length` | 168 | [72, 168, 336] |
| `cnn_filters` | [64, 128, 64] | filters in [32, 64, 128] |
| `cnn_kernel_sizes` | [3, 5, 3] | [3, 5, 7] |
| `lstm_units` | [128, 64] | [32, 64, 128, 256] |
| `lstm_dropout` | 0.2 | [0.0, 0.3] |
| `attention_heads` | 4 | fixed |
| `attention_key_dim` | 32 | fixed |
| `dense_units` | [64, 32] | [16, 32, 64] |
| `dense_dropout` | 0.3 | [0.0, 0.2] |
| `l2_weight` | 0.0001 | fixed |
| `learning_rate` | 0.001 | [0.0001, 0.005] (log-uniform) |
| `batch_size` | 32 | [16, 32, 64] |
| `epochs` | 200 | max; early stopping controls |

### 6.2 Ensemble Weights

| Model | Default Weight |
|-------|---------------|
| CNN-LSTM | 0.50 |
| XGBoost | 0.25 |
| LightGBM | 0.25 |

Weights are normalized to sum to 1.0. Confidence intervals are derived from model
disagreement (standard deviation across members scaled by z=1.96 for 95% CI).

### 6.3 Hyperparameter Tuning

Three search strategies are supported via `HyperparameterTuner`:

- **Grid search**: exhaustive; practical only with `max_trials` cap.
- **Random search**: `ParameterSampler` with `n_trials` (default 50).
- **Bayesian optimization**: Optuna `TPESampler` with `MedianPruner` (default 100 trials,
  10 startup random trials).

### 6.4 Retraining Schedule

| Trigger | Condition |
|---------|-----------|
| Scheduled | Weekly (168-hour interval in backtesting) |
| Performance-based | When rolling MAPE > 1.5x target |
| Data drift | When feature distribution shift detected |

---

## 7. Integration Points

### 7.1 API Endpoints (predictions router)

| Endpoint | Method | Request | Response | Caching |
|----------|--------|---------|----------|---------|
| `/predict/price` | POST | `{region, hours_ahead, include_confidence}` | `{predictions[], model_version, accuracy_mape}` | Redis, 1h TTL |
| `/predict/optimal-times` | POST | `{region, duration_hours, earliest_start, latest_end, num_slots}` | `{optimal_slots[], potential_savings_percent}` | None |
| `/predict/savings` | POST | `{region, appliances[]}` | `{unoptimized_cost, optimized_cost, savings_amount, savings_percent, schedule}` | None |
| `/predict/model-info` | GET | -- | `{model_version, accuracy_mape, model_type, last_updated}` | Redis |

### 7.2 Model Loading Strategy

```
FUNCTION load_model():
    IF "model" IN process_cache:
        RETURN process_cache["model"]

    model_path = settings.model_path OR env.MODEL_PATH

    TRY: model = EnsemblePredictor(model_path)     // preferred
    CATCH: TRY: model = PricePredictor(model_path)  // single-model fallback
    CATCH: model = None                              // simulation fallback

    process_cache["model"] = model
    RETURN model
```

### 7.3 Simulation Fallback

When no trained model is available, the system generates synthetic forecasts:
```
price(hour) = 0.20 + 0.05 * sin((hour - 6) * pi / 12) + N(0, 0.01)
CI = [price * 0.85, price * 1.15]
```

### 7.4 Supplier Switching Engine

The `SupplierSwitchingEngine` compares tariffs against a user's `ConsumptionProfile`:

- **Inputs**: current tariff, list of alternatives, annual consumption, peak fraction.
- **Outputs**: ranked `SwitchingRecommendation` list sorted by `annual_savings`.
- **Thresholds**: minimum 5% savings, maximum 6-month payback, confidence >= 0.5.
- **Risk assessment**: Fixed=Low, Variable=Medium, Dynamic=High.
- **Tariff types**: FIXED_RATE, VARIABLE_RATE, TIME_OF_USE, DYNAMIC, GREEN.

---

## 8. Evaluation Framework

### 8.1 Metrics Suite

| Category | Metric | Formula | Target |
|----------|--------|---------|--------|
| Point forecast | MAE | `mean(abs(y - y_hat))` | -- |
| Point forecast | RMSE | `sqrt(mean((y - y_hat)^2))` | -- |
| Point forecast | MAPE | `mean(abs((y - y_hat)/y)) * 100` | < 10% |
| Point forecast | sMAPE | `mean(abs(y - y_hat) / ((abs(y)+abs(y_hat))/2)) * 100` | -- |
| Point forecast | R2 | `1 - SS_res/SS_tot` | > 0.8 |
| Direction | Direction accuracy | `mean(sign(dy) == sign(dy_hat)) * 100` | > 60% |
| Direction | Weighted direction | Magnitude-weighted direction accuracy | > 55% |
| Probabilistic | Coverage (90%) | `mean(y in [lower, upper]) * 100` | >= 90% |
| Probabilistic | Interval score | Gneiting & Raftery 2007 proper scoring rule | Lower is better |
| Business | Cost of error | `abs(sum(y_hat * kWh) - sum(y * kWh))` | -- |
| Business | Savings impact | `(perfect_savings - actual_savings) / perfect_savings * 100` | < 20% |

### 8.2 Walk-Forward Backtesting Pseudocode

```
FUNCTION run_backtest(model, feature_engine, df, config):
    df_features = feature_engine.transform(df)
    position = config.min_train_size + config.sequence_length
    hours_since_retrain = 0
    results = []

    WHILE position + config.test_size <= len(df_features):
        // Determine training window
        IF config.window_type == "expanding":
            train = df_features[0 : position]
        ELSE:  // rolling
            train = df_features[max(0, position - min_train) : position]

        test = df_features[position : position + config.test_size]

        // Retrain if needed
        IF hours_since_retrain >= config.retrain_frequency:
            X_train, y_train = create_sequences(train)
            model.fit(X_train, y_train)
            hours_since_retrain = 0

        // Predict
        X_test, y_test = create_sequences(test)
        predictions, lower, upper = model.predict(X_test)

        // Evaluate
        metrics = compute_all_metrics(y_test, predictions, lower, upper)
        results.append(metrics)

        position += config.step_size
        hours_since_retrain += config.step_size

    // Aggregate
    overall = aggregate_metrics(results)
    ASSERT overall.mape <= config.target_mape
    ASSERT overall.coverage >= config.target_coverage
    RETURN summary
```

---

## 9. TDD Anchors -- Test Scenarios

### 9.1 Forecasting Accuracy Tests

| ID | Scenario | Assertion |
|----|----------|-----------|
| T-FC-001 | Model output shape | `predict(X).shape == (batch, 24, 3)` |
| T-FC-002 | Quantile ordering | `lower <= median <= upper` for all samples |
| T-FC-003 | MAPE on test set | `mape(y_test, predictions) <= 10.0` |
| T-FC-004 | Coverage of 90% CI | `coverage(y_test, lower, upper) >= 0.85` |
| T-FC-005 | Inference latency | `avg_inference_time < 1000ms` for single sample |
| T-FC-006 | Save/load roundtrip | `metrics_before == metrics_after` |
| T-FC-007 | Ensemble beats any single model | `ensemble_mape <= min(cnn_mape, xgb_mape, lgb_mape)` |
| T-FC-008 | Simulation fallback | When no model loaded, predictions returned with sinusoidal pattern |

### 9.2 Optimization Constraint Tests

| ID | Scenario | Assertion |
|----|----------|-----------|
| T-OPT-001 | Basic MILP solves | `result.status == "Optimal"` |
| T-OPT-002 | Duration satisfied | `len(scheduled_slots) == appliance.duration_slots` for all appliances |
| T-OPT-003 | Time window respected | All scheduled slots in `appliance.get_valid_slots()` |
| T-OPT-004 | Continuity enforced | No gaps in `sorted(slots)` for continuous appliances |
| T-OPT-005 | Power limit honored | `max(power_profile) <= config.max_total_power_kw` |
| T-OPT-006 | Dependency ordering | Successor starts after predecessor finishes |
| T-OPT-007 | Mutual exclusion | `x[a1,t] + x[a2,t] <= 1` for all t |
| T-OPT-008 | TOU savings >= 15% | Dishwasher + EV + water heater with 3.5x peak ratio |
| T-OPT-009 | Real-time savings >= 15% | Average over 5 random price scenarios |
| T-OPT-010 | Solve time < 5s | 7 appliances, 96 slots |

### 9.3 Vector Store Tests

| ID | Scenario | Assertion |
|----|----------|-----------|
| T-VS-001 | Insert and retrieve | `search(same_vector).similarity >= 0.99` |
| T-VS-002 | Dimension padding | Insert dim=12 vector, search with dim=24, no error |
| T-VS-003 | Domain filtering | Search with domain filter returns only matching domain |
| T-VS-004 | Similarity threshold | No results returned below `min_similarity` |
| T-VS-005 | Outcome tracking | After `record_outcome(id, success=True)`, `confidence` increases |
| T-VS-006 | Pruning | `prune(min_confidence=0.3)` removes low-confidence vectors |
| T-VS-007 | LRU cache eviction | Cache size stays <= `cache_size` after many inserts |
| T-VS-008 | Usage count incremented | After search, `usage_count` of returned vectors increases by 1 |

### 9.4 Feature Engineering Tests

| ID | Scenario | Assertion |
|----|----------|-----------|
| T-FE-001 | Temporal features created | `hour_sin`, `is_weekend`, `is_holiday` columns exist |
| T-FE-002 | Lag values correct | `price_lag_1h[i] == price[i-1]` |
| T-FE-003 | Rolling mean correct | `rolling_mean_24h[i] == mean(price[i-23:i+1])` |
| T-FE-004 | No NaN in output | After `transform()`, `df.isna().sum() == 0` |
| T-FE-005 | Sequence shapes | `X.shape == (N, 168, F)` and `y.shape == (N, 24)` |
| T-FE-006 | Scaler roundtrip | `fit` then `transform` produces standardized features (mean~0, std~1) |
| T-FE-007 | Holiday detection | Known holidays in calendar are flagged `is_holiday=1` |

### 9.5 Switching Decision Tests

| ID | Scenario | Assertion |
|----|----------|-----------|
| T-SW-001 | Savings calculation | `annual_savings == current_cost - projected_cost` |
| T-SW-002 | Risk assessment | Fixed rate returns `RiskLevel.LOW` |
| T-SW-003 | Minimum threshold | No recommendations when savings < 5% |
| T-SW-004 | Payback calculation | `payback_months == exit_fee / monthly_savings` |
| T-SW-005 | Sorted by savings | `recommendations[0].savings >= recommendations[1].savings` |

---

## 10. File Reference

| File | Purpose |
|------|---------|
| `ml/models/price_forecaster.py` | TF/Keras CNN-LSTM model, QuantileLoss, ModelConfig |
| `ml/models/ensemble.py` | EnsembleForecaster, XGBoostForecaster, LightGBMForecaster |
| `ml/training/cnn_lstm_trainer.py` | PyTorch CNN-LSTM trainer, sequence preparation |
| `ml/training/train_forecaster.py` | End-to-end training pipeline orchestrator |
| `ml/training/hyperparameter_tuning.py` | Grid/random/Bayesian tuning via Optuna |
| `ml/inference/predictor.py` | PricePredictor (single model inference) |
| `ml/inference/ensemble_predictor.py` | EnsemblePredictor (weighted model combination) |
| `ml/data/feature_engineering.py` | ElectricityPriceFeatureEngine, create_dummy_data |
| `ml/optimization/appliance_models.py` | Appliance, PriceProfile, ScheduleResult, OptimizationConfig |
| `ml/optimization/load_shifter.py` | MILPOptimizer core solver |
| `ml/optimization/constraints.py` | ConstraintBuilder, build_all_constraints |
| `ml/optimization/objective.py` | ObjectiveBuilder, build_objective, baseline_cost |
| `ml/optimization/scheduler.py` | ApplianceScheduler (high-level API), SchedulerPresets |
| `ml/optimization/switching_decision.py` | SupplierSwitchingEngine, Tariff, ConsumptionProfile |
| `ml/optimization/visualization.py` | ScheduleVisualizer (matplotlib + plotly) |
| `ml/evaluation/metrics.py` | ForecastMetrics, MAE/RMSE/MAPE/sMAPE/interval_score |
| `ml/evaluation/backtesting.py` | ModelBacktester, walk-forward validation |
| `ml/tests/test_milp_standalone.py` | 9 standalone MILP tests (no TF dependency) |
| `backend/routers/predictions.py` | FastAPI endpoints for inference + optimization |
| `backend/services/vector_store.py` | VectorStore with SQLite + cosine similarity |
