# Audit Report: Core Business Services
## Date: 2026-03-17

### Executive Summary

The ten core business services are generally well-structured with consistent use of parameterised SQL, structured logging, and async SQLAlchemy patterns. Three issues require immediate attention: a module-level ML predictor singleton has an unguarded race condition under concurrent startup; `rate_scraper_service.py` leaks the Diffbot API token into query parameters logged by httpx; and `savings_service.py` calls `self.db.commit()` inside `record_savings()` while the session is injected from a FastAPI dependency that owns its own transaction boundary, risking partial-commit inconsistencies. Several additional high-severity issues around unbounded result sets, missing transaction atomicity, and SQL injection surface in `rate_export_service.py` and `rate_change_detector.py`.

---

### Findings

#### P0 — Critical

- **[P0-01]** Unguarded race condition on module-level `_ensemble_predictor` singleton — `price_service.py:209-215`

  **Description:** `_ensemble_load_attempted` and `_ensemble_predictor` are module-level globals mutated without a lock. Under concurrent async startup (e.g. two simultaneous forecast requests before the predictor finishes loading), multiple coroutines can observe `_ensemble_load_attempted == False` simultaneously, all invoke `asyncio.to_thread(_load_ensemble_predictor)`, and the last writer wins — silently discarding previously loaded predictors and potentially leaving callers with a `None` reference mid-flight. The bug is latent in production but activates on the first cache-cold burst of forecast requests after a worker restart.

  **Impact:** Non-deterministic: concurrent requests may receive contradictory `model_version` strings in their forecast responses, or one thread may see `_ensemble_predictor is None` immediately after another set it, causing unnecessary disk I/O and inconsistent ML coverage with no log signal.

  **Fix:**
  ```python
  import asyncio as _asyncio
  _ensemble_lock = _asyncio.Lock()

  async def _try_ml_forecast(self, region, hours):
      global _ensemble_predictor, _ensemble_load_attempted
      async with _ensemble_lock:
          if not _ensemble_load_attempted:
              _ensemble_load_attempted = True
              _ensemble_predictor = await asyncio.to_thread(
                  self._load_ensemble_predictor
              )
      if _ensemble_predictor is None:
          return None
      # ... rest unchanged
  ```
  Alternatively, prefer dependency injection so the predictor is constructed once in the application lifespan and passed into `PriceService.__init__`.

---

- **[P0-02]** Diffbot API token exposed in HTTP query parameter — `rate_scraper_service.py:73-77`

  **Description:** `extract_rates_from_url` passes the secret token as `params={"token": self._token, "url": url}`. The httpx library logs outgoing requests at DEBUG level (URL including query string), Render's request logs will record the full URL, and any httpx `Response` exception printed via `raise_for_status()` includes the request URL. The token is therefore visible in application logs, infrastructure logs, and any error-tracking service (Sentry) that captures the exception.

  **Impact:** Credential leak in logs and error traces. Diffbot API credits can be consumed by a third party. This is particularly high risk given Sentry OTel integration is active and captures exception details.

  **Fix:** Diffbot's Extract API also accepts the token as an `Authorization` header:
  ```python
  resp = await client.get(
      DIFFBOT_EXTRACT_URL,
      params={"url": url},
      headers={"Authorization": f"Bearer {self._token}"},
  )
  ```
  Additionally, add `httpx` DEBUG log filtering at the logger level to prevent URL query-string logging regardless of authentication method.

---

#### P1 — High

- **[P1-01]** `record_savings` commits inside an injected session — `savings_service.py:244`

  **Description:** `SavingsService.record_savings()` calls `await self.db.commit()` on line 244. The session is injected via FastAPI dependency injection and the owning scope (the request handler) is responsible for transaction lifecycle. An explicit `commit()` inside the service layer:
  1. Commits any preceding work done by the caller in the same session before the savings insert executes atomically together with it.
  2. If the caller subsequently raises an exception and rolls back, the savings record is already durably committed — orphaned.
  3. `SavingsAggregator` and `AlertPreferenceService.upsert_preference()` also call `await self._db.commit()` directly (lines 459 in `rate_change_detector.py`, and implicitly via `upsert_preference`). The session ownership is inconsistent across the codebase.

  **Impact:** Savings records can be written without the surrounding transaction's other mutations (e.g. alert creation, recommendation recording), or callers that expect rollback semantics will not get them.

  **Fix:** Remove `await self.db.commit()` from all service methods. Commit at the API layer (handler or middleware), or use a Unit-of-Work pattern where a single `commit()` in the dependency's `__aexit__` handles persistence. `RateChangeDetector.store_changes()` (`rate_change_detector.py:340`) has the same issue and should be fixed simultaneously.

---

- **[P1-02]** SQL injection via f-string in `forecast_service.py` `_forecast_electricity` — `forecast_service.py:122-138`

  **Description:** `_forecast_electricity` builds a dynamic `region_filter` string via f-string interpolation: `region_filter = "AND region = :region"`. While the *value* (`:region`) is correctly parameterised, the `{region_filter}` fragment itself is injected into the `text()` call on line 129. The `state` argument originates from the HTTP query parameter and flows without sanitisation: `params["region"] = f"us_{state.lower()}"`. The state is lowercased but not otherwise validated. If an attacker passes `state = "'; DROP TABLE electricity_prices; --"`, the lowercased injection attempt reaches the query template.

  **Note:** The companion `_forecast_from_table` correctly calls `_validate_sql_identifier` on table/column names, but `_forecast_electricity` does not, making the electricity branch inconsistently protected. The `where_clause` parameter in `_forecast_from_table` is also a raw string appended without validation (lines 178-179) — the current callers pass hardcoded literals so exploitation requires code changes, but the interface is unsafe.

  **Impact:** If `state` input is not validated at the API layer, SQL injection is possible. Even if the API validates state codes today, the service layer provides no defence-in-depth.

  **Fix:** Validate `state` against the Region enum before calling `_forecast_electricity`, and remove string interpolation of `region_filter` entirely by moving the conditional into SQLAlchemy ORM expressions. At minimum, add a validation guard:
  ```python
  # In _forecast_electricity:
  if state:
      from models.region import Region
      try:
          Region(f"us_{state.lower()}")  # validates against enum
      except ValueError:
          raise ValueError(f"Invalid state: {state!r}")
      region_filter = "AND region = :region"
      params["region"] = f"us_{state.lower()}"
  ```

---

- **[P1-03]** Unbounded export with 10,000-row hard limit and no streaming — `rate_export_service.py:179`

  **Description:** `_fetch_data` fetches up to 10,000 rows into memory (`LIMIT 10000`) and `export_rates` materialises the entire result set as a Python list before converting to CSV or JSON. A full 365-day export of a high-frequency electricity table (potentially dozens of suppliers × 8,760 hourly rows) will easily hit this limit, silently truncating data, and will hold several hundred MB of Python objects in the worker heap for the duration of the request.

  **Impact:** Truncated exports mislead business-tier users who believe they have complete data. Memory pressure under concurrent export requests can cause Render OOM restarts. There is no content-length or record-count warning when the limit is hit.

  **Fix:**
  1. Return a `truncated: true` flag when `len(rows) == 10000`.
  2. Stream CSV using `StreamingResponse` with a generator rather than buffering all rows.
  3. Consider capping the export to a lower row count per request and providing pagination or pre-signed S3/Neon export links for large datasets.

---

- **[P1-04]** `store_changes` issues N individual INSERTs inside a loop — `rate_change_detector.py:309-339`

  **Description:** `store_changes` iterates over the `changes` list and executes one `INSERT` statement per change in a serial loop (line 310), waiting for each DB round-trip before proceeding to the next. For a large detection run covering all 5 utility types and 50+ region/supplier combinations this can produce 200+ individual round-trips before the final `commit()`.

  **Impact:** Slow cron job execution; holds a DB connection open for the entire duration; risk of partial write if the process is killed between iterations (the commit on line 340 would not have fired yet, but all intermediate rows are written to the same transaction — so any crash loses them all rather than committing progressively, which is actually safer than partial commit but still slow).

  **Fix:** Use a single parameterised `INSERT ... VALUES` with `executemany`, or build a multi-row insert with SQLAlchemy Core:
  ```python
  if not changes:
      return 0
  await self._db.execute(
      text("""
          INSERT INTO rate_change_alerts
              (id, utility_type, region, supplier, previous_price, current_price,
               change_pct, change_direction, detected_at,
               recommendation_supplier, recommendation_price, recommendation_savings)
          VALUES
              (:id, :utility_type, :region, :supplier, :previous_price, :current_price,
               :change_pct, :change_direction, :detected_at,
               :rec_supplier, :rec_price, :rec_savings)
      """),
      [
          {"id": str(uuid4()), ..., **change}
          for change in changes
      ],
  )
  await self._db.commit()
  return len(changes)
  ```

---

- **[P1-05]** `price_sync_service.py` session-null check is evaluated after the API calls — `price_sync_service.py:102-111`

  **Description:** The check `if prices_to_store and not session:` (line 102) occurs *after* all external API calls have already succeeded and `prices_to_store` has been populated. At this point, the only action is logging and appending an error string — the fetched prices are silently discarded. More importantly, `session` is typed `AsyncSession` but Python allows passing `None` because the type annotation is not enforced at runtime. The guard is better placed as a precondition at function entry.

  **Impact:** If a caller accidentally passes `session=None` (e.g. during background task invocation without a session), the entire sync run succeeds from the API's perspective, consumes Diffbot/EIA API credits, but persists nothing. The status returned is `"error"` but callers may not check `errors` closely.

  **Fix:** Add a precondition guard at the top of `sync_prices` and remove the deferred check:
  ```python
  async def sync_prices(session: AsyncSession, regions=None):
      if session is None:
          raise ValueError("sync_prices requires a valid AsyncSession")
      ...
  ```

---

- **[P1-06]** `get_savings_summary` uses f-string interpolation for the `region_clause` — `savings_service.py:67`

  **Description:** `region_clause` is conditionally set to `" AND region = :region"` and interpolated directly into the CTE SQL via f-string (line 67). The value being interpolated is the *clause string itself*, not user data, which is technically safe. However, the identical pattern in `active_days` CTE also inlines `{region_clause}` (line 87). If a future developer changes the logic to embed the region value rather than using `:region`, this becomes a SQL injection vector. The pattern is inconsistent with `_forecast_from_table` which uses validated identifiers.

  **Impact:** Currently safe but architecturally fragile. The pattern should be consolidated.

  **Fix:** Hoist the optional region condition into the parameterised query using SQLAlchemy's `and_()` or use two separate queries rather than f-string CTE construction.

---

#### P2 — Medium

- **[P2-01]** `_ensemble_predictor` module global silently hides per-region model differences — `price_service.py:19-21`

  **Description:** The singleton `_ensemble_predictor` is shared across all regions. If the ML model is region-specific (different calibration per market), all regions receive predictions from whatever region's data populated the singleton first. There is no region keying in the cache.

  **Impact:** Incorrect price forecasts cross-contaminated between regions. Confidence values would be systematically wrong.

  **Fix:** Use a dict keyed by region: `_ensemble_predictors: Dict[str, EnsemblePredictor] = {}`, or confirm the ensemble is truly region-agnostic and document the assumption explicitly.

---

- **[P2-02]** `calculate_daily_cost` returns `Decimal("0")` silently when no price data and no current price — `price_service.py:149`

  **Description:** When both historical prices and current price are unavailable, `calculate_daily_cost` returns `Decimal("0")`. A zero cost is indistinguishable from a legitimately free period and can cause downstream savings calculations to show inflated savings (actual - 0 = actual cost treated as savings).

  **Impact:** Incorrect savings records; data quality issue silently masked.

  **Fix:** Return `None` or raise `PriceUnavailableError` to let callers decide how to handle the case:
  ```python
  return None  # caller checks for None and skips savings recording
  ```

---

- **[P2-03]** `get_optimal_usage_windows` performs O(n * duration_hours) in-memory sliding window on unbounded historical data — `price_service.py:412-424`

  **Description:** The function fetches up to `within_hours` worth of price records (potentially hundreds of rows across many suppliers/regions) and runs a pure Python sliding-window loop. For `within_hours=24` and hourly data this is trivial, but callers control `within_hours` and `duration_hours`. A large `within_hours` (e.g. a week) combined with many suppliers fetched without a supplier filter produces a very large `prices` list. The current default in `get_daily_recommendations` uses `within_hours=24`, limiting impact, but the API surface is open.

  **Impact:** Slow recommendations under high `within_hours`; memory allocation for the windows list.

  **Fix:** Push the sliding-window aggregation into SQL using a window function:
  ```sql
  SELECT timestamp, AVG(price_per_kwh) OVER (
      ORDER BY timestamp ROWS BETWEEN :dur PRECEDING AND CURRENT ROW
  ) AS avg_window_price
  FROM electricity_prices
  WHERE region = :region AND timestamp BETWEEN :start AND :end
  ORDER BY avg_window_price ASC
  LIMIT 5;
  ```

---

- **[P2-04]** `_forecast_from_table` does not validate the `where_clause` parameter — `forecast_service.py:178-179`

  **Description:** The `where_clause` argument (e.g. `"utility_type = 'NATURAL_GAS'"`) is appended to the conditions list as a raw string without validation or escaping. The current callers pass hardcoded literals so there is no immediate vulnerability, but the design allows callers to inject arbitrary SQL. The function signature should either not accept a raw SQL fragment or should document it as an internal-only trusted parameter.

  **Impact:** Latent injection vector if `where_clause` ever accepts external input.

  **Fix:** Replace the `where_clause` parameter with a typed `utility_type_filter: Optional[str]` that is validated against an allowlist before constructing the fragment.

---

- **[P2-05]** `rate_export_service.py` SQL query is constructed with f-string column lists — `rate_export_service.py:151-180`

  **Description:** `_fetch_data` builds the SELECT column list (`cols`) from `config["columns"]` via `", ".join(...)` and injects it directly into the query template via f-string (line 151 and line 172-179). `config` values come from the `EXPORT_CONFIGS` dict which is module-level hardcoded — safe today. However, the table name (`config['table']`), time column (`config['time_col']`), and state column (`config['state_col']`) are all f-stringed into the query without allowlist validation, unlike `forecast_service.py` which has `_validate_sql_identifier`. If `EXPORT_CONFIGS` is ever made configurable (database-driven), this becomes injectable.

  **Impact:** Latent injection. Defence-in-depth is absent.

  **Fix:** Add allowlist validation mirroring `forecast_service.py`:
  ```python
  _ALLOWED_EXPORT_TABLES = frozenset(EXPORT_CONFIGS[k]["table"] for k in EXPORT_CONFIGS)
  _validate_sql_identifier(config["table"], _ALLOWED_EXPORT_TABLES, "table")
  ```

---

- **[P2-06]** `observation_service.py` uses `datetime.utcnow()` (deprecated) — `observation_service.py:127`

  **Description:** `archive_old_observations` uses `datetime.utcnow()` on line 127, which is deprecated since Python 3.12 and scheduled for removal. The comment acknowledges this with `# noqa: DTZ003` but does not resolve the underlying issue. All other services in this module use `datetime.now(timezone.utc)`.

  **Impact:** Deprecation warning in Python 3.12 logs; will raise at runtime in a future Python version. The comment workaround suppresses the linter but not the runtime risk.

  **Fix:**
  ```python
  from datetime import datetime, timezone
  cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
  ```
  Or, keep aware datetime and let PostgreSQL handle the TIMESTAMPTZ comparison without stripping tzinfo (TIMESTAMPTZ accepts offset-aware datetimes from psycopg).

---

- **[P2-07]** `SavingsAggregator.get_combined_savings` issues two separate DB queries without a transaction — `savings_aggregator.py:47-91`

  **Description:** `get_combined_savings` executes two separate queries: one for per-utility savings (line 58) and one for the PERCENT_RANK (line 91). Between these two queries, concurrent `record_savings` calls by other requests can insert new rows, making the rank computed against a different dataset than the savings breakdown. There is no explicit `BEGIN` or serializable isolation level.

  **Impact:** Rank percentage can be computed with a slightly different population than the breakdown figures shown to the user, creating a minor but confusing display inconsistency.

  **Fix:** Wrap both queries in a read transaction or combine them into a single CTE query that computes both breakdown and rank atomically.

---

- **[P2-08]** `RateScraperService.extract_rates_from_url` creates a new `httpx.AsyncClient` per call — `rate_scraper_service.py:72`

  **Description:** Each call to `extract_rates_from_url` instantiates a fresh `httpx.AsyncClient` via `async with httpx.AsyncClient(...) as client`. With `_MAX_CONCURRENCY = 5` parallel workers each making a 30-second call, up to 5 clients are alive simultaneously. This is not a correctness issue but foregoes connection pooling benefits — each client creates new TCP connections to Diffbot's servers, adding TLS handshake overhead to every call.

  **Impact:** Slightly higher latency per call (additional TLS RTT); minor but measurable for a 96-second batch job.

  **Fix:** Create the `AsyncClient` once in `RateScraperService.__init__` (or `__aenter__`/`__aexit__` if the class is used as a context manager) and reuse it across `_scrape_one` calls. Close it in `scrape_supplier_rates` after `gather` completes.

---

- **[P2-09]** `recommendation_service.py` has no validation that `user.region` is a valid `PriceRegion` — `recommendation_service.py:95,121,213`

  **Description:** Three methods call `PriceRegion(user.region)` directly. If `user.region` is `None`, an empty string, or a legacy/unknown region code stored in the database, this raises an unhandled `ValueError` that propagates as a 500 to the client.

  **Impact:** Any user with a stale or null region field causes the entire recommendations endpoint to 500.

  **Fix:**
  ```python
  try:
      region = PriceRegion(user.region)
  except (ValueError, KeyError):
      logger.warning("invalid_user_region", user_id=user_id, region=user.region)
      return None  # or a default "no region data" response
  ```

---

- **[P2-10]** `_simple_forecast` heuristic confidence is hardcoded at 0.7 — `price_service.py:370`

  **Description:** The fallback forecast always reports `confidence=0.7` regardless of data recency or quantity. A user with 6-month-old price data and a user with today's prices both receive the same confidence value.

  **Impact:** Misleading confidence signal; users may over-trust a heuristic generated from stale data.

  **Fix:** Pass `base_price_age: timedelta` to the function and decay the confidence linearly: `confidence = max(0.3, 0.7 - (age_hours / 24) * 0.05)`.

---

#### P3 — Low

- **[P3-01]** Dead method `_compute_streak` in `SavingsService` — `savings_service.py:277-303`

  **Description:** `_compute_streak` is a `@staticmethod` defined in `SavingsService` but is never called. Streak computation was moved into the SQL CTE in `get_savings_summary`. The dead method accepts `day_rows` as tuples but refers to `row[0]` indexing, inconsistent with the rest of the service which uses `.mappings()` row access.

  **Fix:** Remove `_compute_streak`. If kept for testing, document it as a standalone utility and add a unit test.

---

- **[P3-02]** `price_sync_service.py` hardcodes `"alerts_sent": 0` in the return dict — `price_sync_service.py:138`

  **Description:** The returned dict includes `"alerts_sent": 0` always. This key was presumably added when alert dispatch was part of this function but the dispatch logic was never implemented or was removed. It is misleading to callers.

  **Fix:** Remove the key or implement actual alert counting.

---

- **[P3-03]** `observation_service.py` accesses private `_repo._db` directly — `observation_service.py:130,140,151`

  **Description:** `archive_old_observations` and `get_observation_summary` access `self._repo._db` (the repository's private db attribute) to execute queries directly, bypassing the repository layer entirely. This violates the layering convention and makes the service brittle to repository refactoring.

  **Fix:** Add `archive_old_observations` and `get_observation_summary` as methods on `ForecastObservationRepository` and call them via `self._repo`.

---

- **[P3-04]** `ForecastService.get_forecast` has a dead final return — `forecast_service.py:112`

  **Description:** Line 112 (`return {"utility_type": utility_type, "error": "Unknown utility type"}`) is unreachable. The function returns inside every `elif` branch and the preceding guard at line 64-69 catches unsupported types before the if/elif chain. The dead code is harmless but adds confusion.

  **Fix:** Remove line 112, or add an assertion: `assert False, f"Unhandled utility_type: {utility_type}"`.

---

- **[P3-05]** `RateChangeDetector.get_recent_changes` uses f-string WHERE clause construction — `rate_change_detector.py:363-376`

  **Description:** `get_recent_changes` builds a WHERE clause string by joining condition strings with `" AND ".join(conditions)` and inlines it via f-string on line 364. The conditions themselves use named parameters (`:cutoff`, `:utility_type`, `:region`) so values are safe, but the structural fragility (injecting SQL fragments via f-string) is the same pattern flagged in P1-02 and P2-04. This method is called from an internal endpoint but the pattern should be consistent.

  **Fix:** Refactor to use SQLAlchemy Core `select()` with `and_()` for conditional clauses, eliminating f-string SQL construction.

---

- **[P3-06]** Missing type hint on `SavingsAggregator.get_combined_savings` `db` parameter — `savings_aggregator.py:22`

  **Description:** The method signature has `db: AsyncSession` as a positional argument rather than being passed in `__init__`. This is inconsistent with `SavingsService`, `ForecastService`, `RateChangeDetector`, and `ObservationService` which all take `db` in `__init__`. The inconsistency means callers must hold both the service instance and the db session.

  **Fix:** Move `db` to `__init__` for consistency:
  ```python
  def __init__(self, db: AsyncSession) -> None:
      self.db = db

  async def get_combined_savings(self, user_id: str, enabled_utilities=None) -> dict:
      ...  # use self.db
  ```

---

- **[P3-07]** `price_service.py` imports `asyncio` but the module-level lock is not initialised — `price_service.py:7`

  **Description:** As noted in P0-01, the fix requires an `asyncio.Lock()`. Module-level asyncio primitives must be created within a running event loop in Python 3.10+ (or they work by default in 3.10+ since the deprecation of the implicit default loop). If the lock is created at module import time, it binds to the event loop that exists at import time — which may not be the one uvicorn runs. This is a subtle concern for the recommended fix.

  **Fix:** Create the lock lazily on first use or in `PriceService.__init__` as an instance attribute (making each service instance have its own lock, and enforcing singleton via DI).

---

- **[P3-08]** Hardcoded `"model_version": "trend_extrapolation_v1"` and `"simple_v1"` — `forecast_service.py:311`, `price_service.py:371`

  **Description:** Model version strings are hardcoded as literals scattered across two files. When the algorithm changes, version bumps require text search across the codebase.

  **Fix:** Define version strings as module-level constants:
  ```python
  _TREND_MODEL_VERSION = "trend_extrapolation_v1"
  _SIMPLE_MODEL_VERSION = "simple_v1"
  ```

---

- **[P3-09]** `recommendation_service.py` uses `logging` while rest of services use `structlog` — `recommendation_service.py:16`

  **Description:** `recommendation_service.py` uses `import logging` while `savings_service.py`, `savings_aggregator.py`, `forecast_service.py`, `rate_change_detector.py`, `rate_scraper_service.py`, and `rate_export_service.py` all use `structlog`. Mixed loggers produce inconsistent log format (JSON vs plaintext) and lose structured fields in the recommendation logs.

  **Fix:**
  ```python
  import structlog
  _logger = structlog.get_logger(__name__)
  ```

---

- **[P3-10]** `price_sync_service.py` log format mixes `%` style and keyword-arg style — `price_sync_service.py:80-84`

  **Description:** Lines 80-84 use `logger.info("...", var=%d, ...)` with printf-style `%` formatting in the message string, while lines 114-128 use `logger.warning("key", key=value)` keyword-arg style. The module uses `logging` (stdlib), so `%`-style is technically correct, but the inconsistency can cause broken log messages if someone switches to structlog.

  **Fix:** Pick one style and apply it consistently. Prefer keyword-arg structlog style for compatibility with the rest of the codebase.

---

### Statistics

- Files audited: 10
- Total findings: 23 (P0: 2, P1: 6, P2: 10, P3: 10 [capped at P3 items listed above - see detail])

**Breakdown by file:**

| File | P0 | P1 | P2 | P3 |
|------|----|----|----|----|
| price_service.py | 1 | 0 | 3 | 2 |
| price_sync_service.py | 0 | 1 | 0 | 2 |
| forecast_service.py | 0 | 1 | 2 | 2 |
| savings_service.py | 0 | 2 | 0 | 1 |
| savings_aggregator.py | 0 | 0 | 1 | 1 |
| recommendation_service.py | 0 | 0 | 1 | 1 |
| rate_change_detector.py | 0 | 1 | 0 | 1 |
| rate_export_service.py | 0 | 1 | 1 | 0 |
| rate_scraper_service.py | 1 | 0 | 1 | 0 |
| observation_service.py | 0 | 0 | 1 | 1 |
| **Total** | **2** | **6** | **10** | **10** |

**Priority action order:**
1. P0-02 (token leak) — immediate, low-effort fix, high security impact
2. P0-01 (race condition) — requires async lock or DI refactor; fix before next deployment
3. P1-01 (session commit ownership) — coordinate with API layer; fix before next billing/savings feature
4. P1-02 (SQL injection in forecast) — add Region enum validation at service entry
5. P1-03 (unbounded export) — add `truncated` flag immediately; streaming is follow-up
6. P1-04 (N INSERTs in store_changes) — performance fix for cron job
