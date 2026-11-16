# ML Pipeline Audit — 2026-03-16

## Summary

| Severity | Count |
|----------|-------|
| P0 (Critical — data correctness or security) | 3 |
| P1 (High — reliability or silent data corruption) | 7 |
| P2 (Medium — operational risk or missing safeguard) | 9 |
| P3 (Low — code quality or observability gap) | 6 |
| **Total** | **25** |

Files audited:
- `backend/services/forecast_service.py`
- `backend/services/learning_service.py`
- `backend/services/hnsw_vector_store.py`
- `backend/services/vector_store.py`
- `backend/services/observation_service.py`
- `backend/services/model_version_service.py`
- `backend/services/price_service.py`
- `backend/services/recommendation_service.py`
- `backend/services/ab_test_service.py`
- `backend/routers/predictions.py`
- `backend/api/v1/internal/ml.py`
- `backend/repositories/forecast_observation_repository.py`
- `backend/repositories/model_config_repository.py`

---

## P0 — Critical

### P0-01: SQL Injection via f-string interpolation in ForecastService

**File:** `backend/services/forecast_service.py`
**Lines:** 116–124, 169–177

**Description:**
`_forecast_electricity` and `_forecast_from_table` build raw SQL strings with
f-string interpolation of the module-level constants `TREND_LOOKBACK_DAYS` and
`table`/`price_col`/`time_col`/`state_col`. These constants are integers or
string literals at present, but `table`, `price_col`, `time_col`, and
`state_col` are passed in directly from `get_forecast()` as string arguments.
Any future caller that passes user-controlled input to `_forecast_from_table`
would produce a classic SQL injection vector. The PostgreSQL interval literal
`INTERVAL '{TREND_LOOKBACK_DAYS} days'` is already formatted with an f-string;
parameterized interval literals (`make_interval(days => :n)`) are available in
PostgreSQL and should be used instead.

```python
# current — unsafe pattern
result = await self.db.execute(
    text(f"""
        SELECT {price_col}, {time_col}
        FROM {table}
        WHERE {where}
        ...
    """),
    params,
)
```

**Fix:**
Allow only allowlisted identifiers for `table`, `price_col`, `time_col`,
`state_col`. Use `make_interval(days => :lookback_days)` for the interval.
Add an identifier allowlist guard at the top of `_forecast_from_table` that
raises `ValueError` for unexpected values.

```python
_ALLOWED_TABLES = frozenset({"electricity_prices", "heating_oil_prices", "propane_prices"})
_ALLOWED_COLS   = frozenset({"price_per_kwh", "price_per_gallon", "fetched_at", "timestamp",
                              "region", "state"})

def _validate_identifier(name: str, allowed: frozenset) -> None:
    if name not in allowed:
        raise ValueError(f"Disallowed SQL identifier: {name!r}")
```

---

### P0-02: Module-level _model_cache caches None permanently after first load failure

**File:** `backend/routers/predictions.py`
**Lines:** 193–232

**Description:**
`_load_model()` stores `None` in `_model_cache["model"]` when MODEL_PATH is
unset or when all load attempts fail (lines 210, 231). Because `_model_cache`
is a module-level dict that persists for the lifetime of the process, any
subsequent call to `_load_model()` will immediately return `None` (line
202–204) even if a model file later becomes available (e.g. after a hot-reload
or mount). The system silently falls back to the synthetic simulation forever
with no mechanism to retry.

This is a data-correctness P0 because users receive simulated data that claims
to be ML-generated; the `model_version` field still reads `"v1.0.0"` from
Redis, giving the impression that a trained model is in use.

**Fix:**
Cache a sentinel that distinguishes "never tried" from "tried and failed" only
for the duration of a startup window (e.g. 5 minutes). Alternatively, use an
explicit `_model_load_timestamp` and retry after a TTL.

```python
_model_cache: Dict[str, Any] = {}
_MODEL_RETRY_AFTER_SECONDS = 300  # retry after 5 min

def _load_model():
    cached = _model_cache.get("model")
    failed_at = _model_cache.get("failed_at")
    if cached is not None:
        return cached
    if failed_at and (time.monotonic() - failed_at) < _MODEL_RETRY_AFTER_SECONDS:
        return None  # still in backoff window
    ...  # attempt load
    if model is None:
        _model_cache["failed_at"] = time.monotonic()
    else:
        _model_cache["model"] = model
    return model
```

---

### P0-03: Simulated forecast does not set model_type to "simulation" — misleads consumers

**File:** `backend/routers/predictions.py`
**Lines:** 235–257, 418–424

**Description:**
`_simulate_forecast()` returns predictions indistinguishable from ML-generated
ones. The `PriceForecastResponse` at line 418 always reports `model_version`
from Redis (which may say `"v1.0.0"` or `"CNN-LSTM Ensemble"`) and
`/predict/model-info` at line 650 hardcodes `"model_type": "CNN-LSTM
Ensemble"`. When no ML model is loaded, downstream consumers, A/B test
infrastructure, and the observation recording loop (line 344) all receive and
store data as if it came from a real model.

**Fix:**
`_simulate_forecast` must return a clearly marked response. Add a
`is_simulated: bool` field to `PriceForecastResponse` and set
`model_version="simulation_v1"` when falling back. Skip writing to
`forecast_observations` for simulated data (line 330–352) to avoid polluting
accuracy metrics with synthetic actuals.

---

## P1 — High

### P1-01: HNSW index and SQLite store can diverge — no consistency check on startup

**File:** `backend/services/hnsw_vector_store.py`
**Lines:** 71–112

**Description:**
`_build_index()` loads vectors from SQLite into the HNSW in-memory index at
construction time. After construction, `insert()` writes to both. But `prune()`
(lines 289–298) calls `self._store.prune()` which deletes SQLite rows, then
rebuilds the HNSW index by calling `_build_index()` again. If the process
crashes between the SQLite delete and the HNSW rebuild, the in-memory index
retains stale labels for deleted vectors. On the next `search()` call, the
`_label_to_id` lookup at line 213 will find labels for vectors that no longer
exist in SQLite, and the subsequent metadata batch-lookup query (line 226–231)
will silently return no row for those IDs, yielding partial/truncated results
with no error or log warning.

**Fix:**
After `_build_index()` completes, log and assert that
`len(self._label_to_id) == self._index.get_current_count()`. In `search()`,
treat a missing metadata row as a warning log, not silent skip. Consider
making HNSW index writes atomic with SQLite writes using a mutex.

---

### P1-02: Missing input validation on prediction endpoint — NaN/Inf can propagate into DB

**File:** `backend/routers/predictions.py`
**Lines:** 302–317

**Description:**
The ML model's `predict()` return values `point[i]`, `lower[i]`, `upper[i]`
are cast to `float` with no NaN or Inf check before being stored in
`forecast_observations`. If the underlying numpy arrays contain NaN or Inf
(which can occur from division by zero or underflow in the model), those values
are stored verbatim in the DB. Downstream MAPE/RMSE SQL queries
(`AVG(ABS(predicted_price - actual_price) / NULLIF(actual_price, 0))`) will
propagate NaN silently, producing NULL accuracy metrics that block the nightly
weight-update cycle (`update_ensemble_weights` returns `None` at line 118 of
`learning_service.py`).

**Fix:**
```python
import math
def _safe_float(v: Any) -> float:
    f = float(v)
    if not math.isfinite(f):
        raise ValueError(f"Non-finite prediction value: {f}")
    return max(0.0, f)  # prices cannot be negative
```
Apply `_safe_float` to `point[i]`, `lower[i]`, `upper[i]` before building
`PricePrediction`. Log and fall back to simulation if any value is non-finite.

---

### P1-03: `archive_old_observations` uses `datetime.utcnow()` (deprecated naive datetime)

**File:** `backend/services/observation_service.py`
**Lines:** 127–144

**Description:**
`datetime.utcnow()` returns a naive datetime (no tzinfo). The column
`forecast_observations.created_at` is `TIMESTAMPTZ`. PostgreSQL will accept
naive UTC values in comparisons, but asyncpg can raise `TypeError` when the
driver encounters a naive datetime in a parameterized query bound to a
`TIMESTAMPTZ` column. The comment at line 123 explicitly acknowledges this is
fragile. More importantly, `utcnow()` is deprecated since Python 3.12.

**Fix:**
```python
cutoff = datetime.now(timezone.utc) - timedelta(days=days)
```
Remove the `# noqa: DTZ003` comment. Update conftest if needed.

---

### P1-04: LearningService instantiates a new HNSWVectorStore per /learn request, discarding the HNSW index

**File:** `backend/api/v1/internal/ml.py`
**Lines:** 91–96

**Description:**
The `/learn` endpoint constructs `HNSWVectorStore()` at line 95 on every
request. `HNSWVectorStore.__init__` calls `_build_index()` which reads all
vectors from SQLite and inserts them into a new in-memory HNSW index. For a
store with thousands of bias-correction and recommendation vectors, this is
O(N) work on every nightly learn call. The singleton accessor
`get_vector_store_singleton()` (line 343 of `hnsw_vector_store.py`) exists
precisely to avoid this but is never used by the `/learn` endpoint.

**Fix:**
```python
from services.hnsw_vector_store import get_vector_store_singleton
vs = get_vector_store_singleton()
```

---

### P1-05: Weight clamping + re-normalization produces non-deterministic output for single-model case

**File:** `backend/services/learning_service.py`
**Lines:** 137–145

**Description:**
When `model_stats` contains exactly one entry, `inverse_errors` has one key.
After clamping (`MAX_WEIGHT = 0.8`), the single weight is 0.8. After
re-normalization (`total = 0.8`, `weights[k] = 0.8/0.8 = 1.0`), the resulting
weight is 1.0, which exceeds `MAX_WEIGHT`. The resulting
`ensemble_payload = {"v1": {"weight": 1.0}}` violates the stated invariant and
could mislead EnsemblePredictor consumers that expect all weights to be
in [MIN_WEIGHT, MAX_WEIGHT].

**Fix:**
Re-apply clamping after normalization:
```python
weights = {k: round(max(MIN_WEIGHT, min(MAX_WEIGHT, v / total)), 4)
           for k, v in weights.items()}
```

---

### P1-06: Backfill actuals query matches by hour-of-day only — one-to-many join corrupts accuracy

**File:** `backend/repositories/forecast_observation_repository.py`
**Lines:** 99–133

**Description:**
The `backfill_actuals` UPDATE joins `forecast_observations` to
`electricity_prices` on `fo.forecast_hour = EXTRACT(HOUR FROM ep.timestamp)`
within a ±25-hour window. If multiple `electricity_prices` rows exist for the
same hour-of-day within that window (e.g. two readings at 14:00 on different
days), PostgreSQL's UPDATE will match the first row returned by the planner,
producing non-deterministic actual price values. This silently corrupts MAPE
and RMSE calculations and thus the ensemble weight update.

The correct join requires the date component too: the forecast's `created_at`
date should be matched against the actual price's `timestamp` date within a
1-hour tolerance.

**Fix:**
```sql
AND DATE_TRUNC('day', ep.timestamp) = DATE_TRUNC('day', fo.created_at)
AND ABS(EXTRACT(EPOCH FROM (ep.timestamp - fo.created_at))) < 86400
```
Replace the current window with a date-scoped match.

---

### P1-07: `_simulate_forecast` uses `np.random.normal` without seeding — non-reproducible test results

**File:** `backend/routers/predictions.py`
**Lines:** 244–246

**Description:**
`np.random.normal(0, 0.01)` at line 244 uses the global numpy random state,
which is not seeded. Each call to `_simulate_forecast` will produce different
values. Integration tests that cache forecasts and check for consistency, or
tests that assert on `predicted_price` ranges, can flake if the random draw is
unlucky. More importantly, the simulated data enters `forecast_observations`
via the observation hook at line 330, producing accuracy-metric noise with
unpredictable distribution.

**Fix:**
Use a deterministic hash of `(region, timestamp)` to seed the simulation, or
accept a seeded `rng` parameter in `_simulate_forecast`.

---

## P2 — Medium

### P2-01: No data quality gate before trend extrapolation — outliers and zeros corrupt slope

**File:** `backend/services/forecast_service.py`
**Lines:** 213–248

**Description:**
`_extrapolate_trend` processes all non-None price values without checking for
outliers, zeros, or negative prices. A single erroneous zero price in the
lookback window sets intercept close to zero and drives slope toward the mean,
producing a dramatically wrong forecast. The `min_similarity` guard exists in
the vector store but there is no equivalent in the trend model.

**Fix:**
Before the regression, add:
1. Filter prices where `price <= 0` (log and drop).
2. Compute median and IQR; drop values more than 3 IQR from median.
3. If fewer than 5 valid points remain, return the "insufficient data" response.

---

### P2-02: Forecast confidence formula weights data_density 60% but ignores forecast horizon

**File:** `backend/services/forecast_service.py`
**Lines:** 277–279

**Description:**
`confidence = round(0.4 * max(r_squared, 0) + 0.6 * data_density, 2)`

The hardcoded `0.4`/`0.6` weights are not configurable. More critically,
`horizon_days` (the extrapolation distance) is not factored in. A 90-day
forecast receives the same confidence as a 7-day forecast despite having much
higher extrapolation uncertainty. This misleads users and downstream automation
that consumes the `confidence` field.

**Fix:**
Apply a horizon decay penalty:
```python
horizon_penalty = max(0.0, 1.0 - (horizon_days / 90) * 0.4)
confidence = round((0.4 * max(r_squared, 0) + 0.6 * data_density) * horizon_penalty, 2)
```
Make the base weights (`0.4`, `0.6`) configurable in settings.

---

### P2-03: Hardcoded HNSW hyperparameters with no external configuration

**File:** `backend/services/hnsw_vector_store.py`
**Lines:** 46–53

**Description:**
`max_elements=10000`, `ef_search=50`, `M=16`, `dimension=24`, and
`ef_construction=200` are all hardcoded constructor defaults with no way to
override them at runtime. As the vector store grows (bias corrections + pattern
vectors accumulate nightly), these parameters will become stale without a code
change. `max_elements=10000` with `M=16` means each HNSW graph node holds 16
bidirectional edges; at 10,000 nodes the index uses ~12 MB of RAM. A busy
production instance will hit this ceiling in ~3 years of nightly inserts.

**Fix:**
Read from `settings` or environment variables:
```python
max_elements = int(os.environ.get("HNSW_MAX_ELEMENTS", 10000))
ef_search    = int(os.environ.get("HNSW_EF_SEARCH", 50))
```
Document the capacity math in a comment.

---

### P2-04: No model drift detection — accuracy degradation is only detected reactively

**File:** `backend/services/learning_service.py` (entire file)

**Description:**
The learning cycle computes rolling MAPE/RMSE but does not emit an alert when
accuracy degrades beyond a threshold. `run_full_cycle()` logs results but
returns them to the caller (the `/learn` endpoint), which discards them.
There is no mechanism to notify operators when MAPE exceeds e.g. 15% or doubles
from the previous cycle. Model drift (concept drift due to market structure
changes, or data pipeline failures) will go undetected until a manual review.

**Fix:**
Add a drift-detection step to `run_full_cycle`:
```python
MAPE_ALERT_THRESHOLD = float(os.environ.get("ML_MAPE_ALERT_THRESHOLD", "15.0"))

for region_result in results["regions_processed"]:
    mape = region_result["accuracy"].get("mape")
    if mape and mape > MAPE_ALERT_THRESHOLD:
        logger.warning("model_drift_detected", region=region_result["region"],
                       mape=mape, threshold=MAPE_ALERT_THRESHOLD)
        # Emit to Slack / alert service
```

---

### P2-05: `record_outcome` in VectorStore recomputes confidence from raw success ratio — ignores temporal decay

**File:** `backend/services/vector_store.py`
**Lines:** 228–253

**Description:**
`confidence = success_count / usage_count`. This formula treats a pattern used
200 times 6 months ago the same as one used 3 times last week. Old patterns
with high historical success rates but degraded recent performance will retain
high confidence and resist pruning, while new patterns that would immediately
improve recommendations are underweighted.

**Fix:**
Apply a temporal decay factor. Store a `last_success_at` timestamp and discount
old successes exponentially (e.g. half-life 30 days):
```python
days_since = (now - last_success_at).days
decay = 0.5 ** (days_since / 30)
confidence = (success_count * decay) / max(usage_count, 1)
```

---

### P2-06: VectorStore search opens a new SQLite connection per call — no connection pooling

**File:** `backend/services/vector_store.py`
**Lines:** 185–224

**Description:**
`search()` calls `sqlite3.connect(self._db_path)` at line 185. This opens a
new file handle, acquires SQLite's file-level lock, loads the page cache, and
releases it at exit. With the async wrappers in `HNSWVectorStore` running via
`asyncio.to_thread`, multiple concurrent searches can contend on the SQLite
write-ahead log. At high concurrency (recommendation generation during peak
API traffic), this causes measurable latency spikes.

**Fix:**
Use a single persistent `sqlite3.Connection` initialized in `__init__` with
`check_same_thread=False` and protected by `threading.Lock`, or migrate to
SQLite WAL mode with connection reuse:
```python
self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
self._conn.execute("PRAGMA journal_mode=WAL")
```

---

### P2-07: `_load_model` and `PriceService._load_ensemble_predictor` are duplicate code paths

**File:** `backend/routers/predictions.py` lines 196–232
**File:** `backend/services/price_service.py` lines 236–258

**Description:**
Both files independently implement logic to find `MODEL_PATH`, attempt to import
`ml.inference.ensemble_predictor.EnsemblePredictor`, fall back to a simpler
predictor, and log errors. They use different module-level caches
(`_model_cache` vs `_ensemble_predictor`/`_ensemble_load_attempted`). This
means a Render instance can have the router path succeed (and cache a model)
while the service path fails (and cache None), serving inconsistent predictions
depending on which code path is hit.

**Fix:**
Consolidate into a single `ModelLoader` in `backend/lib/model_loader.py` with
one module-level cache, used by both `predictions.py` and `price_service.py`.

---

### P2-08: A/B test hash bucket uses `% 100` but `traffic_split` is floored to int — precision loss

**File:** `backend/services/model_version_service.py`
**Lines:** 609–618
**File:** `backend/services/ab_test_service.py`
**Lines:** 163–164

**Description:**
Both services convert `traffic_split` to an integer percentage via
`int(traffic_split * 100)`. A `traffic_split=0.333` becomes `split_pct=33`,
not the intended 33.3%. With `% 100`, the distribution is 33/100 vs 67/100,
not 33.3%/66.7%. For a test with 10,000 users, the assignment error is ~70 users
in the wrong bucket. More critically, if a caller passes `traffic_split=0.005`
(0.5%), `split_pct=0` and every user is assigned to version B — the split is
completely ignored.

**Fix:**
Use the raw float for comparison:
```python
hash_float = (hash_int % 10000) / 10000.0  # 0.0000 – 0.9999 precision
bucket = "a" if hash_float < test.traffic_split else "b"
```

---

### P2-09: No test coverage for `_extrapolate_trend` with collinear data (all prices equal)

**File:** `backend/services/forecast_service.py`
**Lines:** 242–248

**Description:**
When all prices in the lookback window are identical, `ss_tot = 0` and
`r_squared = 0` (handled). But `denominator = n * sum_xx - sum_x * sum_x` can
be zero even when prices are not identical but all timestamps are equal
(e.g. all rows from the same second). The code handles this via `abs(denominator) < 1e-10`
check at line 243 and falls back to `slope=0`, `intercept=sum_y/n`. However,
this scenario is also triggered by having only 2 data points that are very
close together in time (e.g. sub-second) — producing a slope of
(price_change) / ~0 seconds which overflows to Inf or very large float,
since the denominator escapes the `1e-10` guard at those scales.

**Fix:**
Assert a minimum time span (e.g. 1 hour = 3600 seconds) before accepting
the regression:
```python
time_span = days[-1] - days[0]  # in fractional days
if time_span < 1/24:  # less than 1 hour
    slope, intercept = 0.0, sum_y / n
```

---

## P3 — Low

### P3-01: `get_observation_summary` and `archive_old_observations` access `_repo._db` directly

**File:** `backend/services/observation_service.py`
**Lines:** 130–131, 151

**Description:**
Both methods bypass the repository API and reach into the private `_db`
attribute of `ForecastObservationRepository`. This breaks the service/repository
separation, makes testing harder (the mock must expose a private attribute), and
means any change to how `ForecastObservationRepository` exposes its session
would silently break `ObservationService`.

**Fix:**
Move the raw SQL into dedicated methods on `ForecastObservationRepository`:
`archive_old_observations(cutoff: datetime)` and `get_summary() -> dict`.

---

### P3-02: `model_version` is stored as a string tag (not a FK) in `forecast_observations`

**File:** `backend/repositories/forecast_observation_repository.py`
**Lines:** 84

**Description:**
`model_version` is stored as a free-form string in `forecast_observations`.
It is populated from `getattr(model, "version", None) or "unknown"` in
`predictions.py` line 344. When the ML model is absent, the value is `"unknown"`.
`get_accuracy_by_version` then groups by this string field — all simulated
forecasts aggregate under `"unknown"`, masking the real model's performance.

**Fix:**
Enumerate a sentinel enum (`ModelVersionEnum.UNKNOWN`, `ModelVersionEnum.SIMULATION`),
or at minimum document that callers must exclude `model_version = 'unknown'`
from accuracy queries. The SQL query in `get_accuracy_by_version` already
filters `model_version IS NOT NULL` but does not filter `= 'unknown'`.

---

### P3-03: `LearningService.run_full_cycle` does not persist results across regions — per-region weight isolation missing

**File:** `backend/services/learning_service.py`
**Lines:** 403–432

**Description:**
`update_ensemble_weights` is called with each `region`, but all regions write
to the same `model_config` row under `model_name="ensemble"`. The
`_persist_weights_to_db` call at line 219 passes `metadata={"region": region}`
as documentation only. The saved weights are not region-scoped; the last region
processed in the loop silently overwrites the weights for all previous regions.
In a multi-region production deployment, this means regions processed first
lose their tuned weights.

**Fix:**
Scope the `model_name` key: `f"ensemble_{region.lower()}"`. Update
`EnsemblePredictor` startup to load from the region-scoped key, falling back to
the global key.

---

### P3-04: `VectorStore._generate_id` uses only 16 hex chars (64 bits) of SHA-256

**File:** `backend/services/vector_store.py`
**Lines:** 90–93

**Description:**
`hashlib.sha256(content.encode()).hexdigest()[:16]` produces a 64-bit
identifier. At 10,000 stored vectors, the birthday collision probability is
~2.7e-9, which is negligible. However, at 1,000,000 vectors (possible after
3+ years of nightly bias insertions at 24 vectors/night × 365 = 8,760/year),
the collision probability exceeds 0.2%. An ID collision causes `INSERT OR
REPLACE` to silently overwrite the existing vector rather than inserting a new
one, corrupting historical pattern data.

**Fix:**
Use the full 32-byte (64-character) digest, or use `uuid4()` for guaranteed
uniqueness at the cost of losing deduplication semantics.

---

### P3-05: Missing TTL on Redis ensemble weights key — stale weights survive Redis restarts

**File:** `backend/services/learning_service.py`
**Lines:** 153–158

**Description:**
`await self._redis.set("model:ensemble_weights", json.dumps(ensemble_payload))`
uses `SET` without an expiry (`EX`/`PX`). The key persists indefinitely in
Redis. If the nightly learning cycle fails after updating Redis but before
updating PostgreSQL, the Redis weights diverge from the DB. The Redis weights
then survive until the next successful cycle. On a Render free-tier instance
with daily restarts, the PostgreSQL fallback kicks in correctly — but on paid
tiers with persistent Redis, a failed cycle leaves stale weights for potentially
multiple days.

**Fix:**
Set a 48-hour TTL:
```python
await self._redis.set("model:ensemble_weights", json.dumps(ensemble_payload), ex=172800)
```

---

### P3-06: No monitoring metric emitted for vector store size — unbounded growth undetectable

**File:** `backend/services/hnsw_vector_store.py`
**Lines:** 280–287

**Description:**
`get_stats()` returns size information but it is only accessible via the
internal `/internal/observation-stats` endpoint and is never pushed to a
metrics system. The vector store grows by at minimum one row per
`store_bias_correction` call (nightly, per region). There is no alerting on
approaching `max_elements`, no Grafana metric, and no automatic capacity
planning. The HNSW `resize_index` at line 154–157 silently doubles capacity
when full, but this is a runtime memory allocation that can cause an OOM on
Render's 512 MB free tier if the index doubles past ~200 MB.

**Fix:**
Emit an OpenTelemetry gauge in `get_stats()`:
```python
from lib.tracing import get_tracer
# or push to a simple Prometheus-style counter
logger.info("vector_store_stats", total=stats["total_vectors"],
            hnsw_count=stats.get("hnsw_count"),
            hnsw_max=stats.get("hnsw_max_elements"))
```
Add a Grafana alert when `hnsw_count / hnsw_max_elements > 0.8`.

---

## Appendix: Issues Not Found

The following potential issues were checked and are NOT present:

- **Data leakage between train/test sets**: The trend extrapolation model uses
  historical data only (`ORDER BY timestamp ASC`, regression computed on past
  data, forecast extrapolated forward). No future data is used in the regression.
- **Rollback capability**: `ModelVersionService.promote_version` correctly
  deactivates prior versions. `list_versions` enables manual rollback via
  `promote_version(old_id)`. `ModelConfigRepository` maintains full history.
- **Missing transaction rollbacks**: All DB-modifying service methods have
  `try/except` with `await self._db.rollback()` on failure.
- **Resource leaks on SQLite**: `vector_store.py` uses `with sqlite3.connect()`
  context managers consistently, ensuring connection close on exception.
- **Bias correction vector dimension mismatch**: `price_curve_to_vector` at
  `vector_store.py:295` resamples to `target_dim`, so variable-length inputs
  are handled.
