# Audit Report: Backend Internal APIs
## Date: 2026-03-17

### Executive Summary

Ten internal endpoint files were audited covering 22 routes across alerts, billing, data pipeline, data quality, email scan, ML, operations, portal scan, and sync domains. The auth boundary is well-designed: a single `verify_api_key` dependency with constant-time comparison is applied at the router level in `__init__.py`, meaning no individual endpoint can accidentally bypass it. The most significant findings are an f-string SQL injection risk in `operations.py` that is currently masked by a validate-before-interpolate pattern (but is still structurally unsafe), missing input bounds on three query parameters in `ml.py`, an unbounded `supplier_urls` list in `scrape-rates`, and a silent no-op data loss path in `data_persistence_helper.py` when the final batch commit fails.

---

### Findings

#### P0 — Critical

**[P0-01] f-string SQL interpolation with unvalidated column names — `operations.py` lines 155-165**

Description: `health-data` constructs raw SQL using Python f-strings to interpolate table names and timestamp column names:

```python
text(f"SELECT COUNT(*) FROM {table_name}")
text(f"SELECT MAX({ts_col}) FROM {table_name}")
```

The code attempts mitigation via an `assert` against an allowlist (`_HEALTH_TABLES`, `_HEALTH_COLS`) immediately before the query loop. However this mitigation has two critical flaws:

1. `assert` statements are removed entirely when Python runs with the `-O` (optimize) flag. Render does not set `-O` by default, but this is a reliability assumption, not a guarantee.
2. The allowlist check is logically redundant — `tables` is a hardcoded local list that never accepts external input, so the assert can never actually fire. This creates a false sense of security: if a future maintainer adds a user-controlled column name to `tables`, the pattern gives no real protection.

The correct fix is to use an explicit set-based check that raises `HTTPException` rather than `assert`, or — better — to restructure the query to avoid interpolation entirely using per-table hardcoded queries or a proper query builder.

Impact: In current code the risk is low because `tables` is hardcoded. The structural pattern is dangerous enough that it should be corrected before any future refactoring touches this function.

Fix:
```python
# Replace assert with explicit validation that cannot be optimized away
_HEALTH_TABLES = frozenset(t[0] for t in tables)
_HEALTH_COLS = frozenset(t[1] for t in tables)
for table_name, ts_col in tables:
    if table_name not in _HEALTH_TABLES or ts_col not in _HEALTH_COLS:
        raise HTTPException(status_code=500, detail=f"Unexpected identifier: {table_name}.{ts_col}")
```

Or restructure to avoid f-string interpolation entirely using SQLAlchemy's `quoted_name` / `identifier` quoting utilities.

---

#### P1 — High

**[P1-01] `persist_batch` swallows all data on commit failure — `data_persistence_helper.py` lines 53-55**

Description: `persist_batch` loops through rows executing individual INSERT statements, accumulating `persisted` count, and then calls `db.commit()` once at the end. If the commit raises an exception, the function returns `persisted = N` (the count before commit) but the data was never actually persisted. The caller receives an inflated success count while no data reached the database. There is no `db.rollback()` call in the failure path.

This helper is used in `fetch-weather` (weather_cache), `market-research` (market_intelligence), and `scrape-rates` (scraped_rates).

Impact: Silent data loss on DB commit failures during cron runs. The GHA workflow or CF Worker will receive a 200 OK with a nonzero `persisted` count and not retry, leaving the database without the data.

Fix:
```python
async def persist_batch(...) -> int:
    persisted = 0
    insert_stmt = text(sql)
    for row in rows:
        try:
            await db.execute(insert_stmt, row)
            persisted += 1
        except Exception as e:
            safe_extras = {k: v for k, v in row.items() if k in _SAFE_LOG_KEYS}
            logger.warning(f"{log_context}_insert_failed", error=str(e), **safe_extras)
    if persisted:
        try:
            await db.commit()
            logger.info(f"{log_context}_persisted", count=persisted)
        except Exception as e:
            logger.error(f"{log_context}_commit_failed", error=str(e), count=persisted)
            await db.rollback()
            return 0  # Signal to caller that nothing was persisted
    return persisted
```

---

**[P1-02] Unbounded `supplier_urls` list in `scrape-rates` — `data_pipeline.py` line 107-113**

Description: The `ScrapeRequest` model accepts a `List[dict]` for `supplier_urls` with no upper bound on list length or on the content of each dict. A caller (or a misconfigured cron) can submit thousands of supplier URLs, causing the endpoint to initiate thousands of Diffbot API calls, exhausting the free-tier credit pool (10,000/month) in a single invocation, and potentially holding the HTTP connection open for many minutes.

```python
class ScrapeRequest(BaseModel):
    supplier_urls: List[dict] = Field(
        default_factory=list,
        # No max_length constraint
    )
```

The auto-discovery path (when `supplier_urls` is empty) is bounded by whatever `supplier_registry` contains, but a caller supplying an explicit list bypasses this.

Impact: Diffbot credit exhaustion, prolonged request lifetime exceeding any upstream proxy timeout, potential OOM if the result list is large.

Fix:
```python
from pydantic import Field
from typing import Annotated

class SupplierUrl(BaseModel):
    supplier_id: str = Field(..., max_length=100)
    url: str = Field(..., max_length=2048)

class ScrapeRequest(BaseModel):
    supplier_urls: Annotated[List[SupplierUrl], Field(max_length=500)] = Field(
        default_factory=list,
        description="Max 500 suppliers per invocation"
    )
```

---

**[P1-03] `observation-stats` and `model-versions` have no input bounds on query parameters — `ml.py` lines 113-168**

Description: Two GET endpoints accept raw, unbounded query parameters:

- `GET /observation-stats`: `days: int = 7` — no `ge`/`le` constraint. A caller can submit `days=1000000`, causing the service to attempt a multi-year aggregation query against `forecast_observations`, which could be a very expensive full table scan.
- `GET /model-versions`: `limit: int = 10` — no `ge`/`le` constraint. A caller can submit `limit=1000000`, causing the service to return the full `model_versions` table in a single response.

The `LearnRequest` model for `POST /learn` correctly uses `ge=1, le=90` for its `days` field; the same discipline was not applied to the GET query parameters.

Impact: Unbounded DB queries triggered by internal tooling or misconfigured monitoring calls, potential OOM on response serialization for `model-versions`.

Fix:
```python
from fastapi import Query

@router.get("/observation-stats", tags=["Internal"])
async def get_observation_stats(
    region: str = Query("US", max_length=50),
    days: int = Query(7, ge=1, le=365),
    db=Depends(get_db_session),
):
    ...

@router.get("/model-versions", tags=["Internal"])
async def list_model_versions(
    model_name: str = Query("ensemble", max_length=100),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
):
    ...
```

---

**[P1-04] `dunning-cycle` has no cap on accounts processed per run — `billing.py` lines 51-83**

Description: `get_overdue_accounts()` fetches all overdue accounts with no LIMIT clause enforced at the endpoint level. If the result set is large (e.g., a payment processor outage causes widespread failures), the endpoint iterates over every account sequentially, sending a dunning email and calling `escalate_if_needed()` per account in a loop with no batching or concurrency cap.

```python
overdue = await dunning.get_overdue_accounts(grace_period_days=7)
# No len(overdue) > BATCH_SIZE guard
for account in overdue:
    email_sent = await dunning.send_dunning_email(...)  # external email API call
    action = await dunning.escalate_if_needed(...)       # DB write
```

Impact: In a catastrophic payment failure scenario this could: (a) exhaust Resend's free-tier email sending limit in one cron run, (b) hold the HTTP connection open for minutes, (c) cause the GHA workflow step to time out and leave the run in an ambiguous state. The retry-curl backoff would then re-trigger the full batch.

Fix: Add a configurable `max_per_run` guard at the endpoint and use async batching:
```python
MAX_DUNNING_PER_RUN = 100
overdue = (await dunning.get_overdue_accounts(grace_period_days=7))[:MAX_DUNNING_PER_RUN]
```

---

**[P1-05] `email_scan` token refresh writes to a shared `AsyncSession` inside an inner async function while other connections may be executing — `email_scan.py` lines 166-186**

Description: The `_scan_one` inner function performs a DB write (`UPDATE user_connections SET ... WHERE id = :cid`) and calls `await db.commit()` on the shared session passed from the outer scope. The outer loop runs sequentially (`for conn in connections: result = await _scan_one(conn)`), which is safe for the shared session. However, the semaphore (`async with sem:`) gates only the external email API calls — it does not gate the DB commit on line 186. If a future developer refactors the outer loop to use `asyncio.gather` (a natural optimization given the semaphore is already in place), the shared session commits will race.

Additionally, within a single `_scan_one` call, a successful token refresh triggers `await db.commit()` (line 186). If the subsequent inbox scan or rate persistence (lines 264-273) then also calls `await db.commit()`, there are now two commits per connection on the same session, interleaved with potential rollbacks. If the rate persistence fails and calls `await db.rollback()` (line 273), it silently rolls back any session state that was open — which, after the token refresh commit, should be none, but this is fragile and non-obvious.

Impact: Not currently exploitable because the outer loop is sequential. Fragile design that will break if parallelized.

Fix: Document the sequential-loop requirement explicitly with a code comment (it is there but easy to miss), or better, have `_scan_one` receive its own dedicated session from a session factory rather than sharing the outer session.

---

#### P2 — Medium

**[P2-01] `scrape-rates` returns raw Diffbot extracted data to callers — `data_pipeline.py` line 317**

Description: The endpoint response includes `"results": raw_results`, which contains the full Diffbot `extracted_data` payloads for every scraped URL. These payloads can be large (multi-KB HTML-extracted text) and may include PII from utility billing pages. Returning raw third-party API responses to cron callers (GHA logs, CF Worker logs) means this data appears in workflow run logs.

Fix: Strip the `extracted_data` field from the response results, keeping only summary fields (`supplier_id`, `success`, `error`). The raw data is already persisted to `scraped_rates.extracted_data` where it belongs.

```python
return {
    "status": "ok",
    "total": batch["total"],
    "succeeded": batch["succeeded"],
    "failed": batch["failed"],
    "errors": batch["errors"],
    "persisted": persisted,
    "rates_found": rates_found,
    # Omit "results": raw_results — data is in DB, not needed in response
}
```

---

**[P2-02] `check-alerts` uses a private service method (`_batch_should_send_alerts`) from the endpoint layer — `alerts.py` line 127**

Description: The endpoint directly calls `service._batch_should_send_alerts(...)`, a method prefixed with `_` indicating it is a private implementation detail of `AlertService`. This creates tight coupling between the endpoint and service internals, meaning any refactoring of the service's dedup logic requires coordinated changes in the endpoint.

Fix: Expose a public `batch_should_send_alerts(...)` method on `AlertService`, or refactor the entire "fetch prices + check thresholds + dedup + send" sequence into a single public `run_alert_pipeline()` service method that the endpoint simply calls, similar to how `billing.py` delegates entirely to `DunningService`.

---

**[P2-03] `portal_scan` silently counts rates_extracted as zero if any persist fails mid-loop — `portal_scan.py` lines 210-243**

Description: The portal scrape rate persistence loop iterates over each rate entry individually. If a single INSERT fails, the exception is caught and logged, but `rates_extracted` is still set to `len(rates)` (line 206) — the count before persistence. The status commit at line 247-251 proceeds regardless, recording `portal_scrape_status = 'active'` even when rate data was only partially persisted.

There is also no `ON CONFLICT DO NOTHING` guard on the portal rate INSERT (unlike the email scan INSERT at line 260 which has it), meaning re-running the cron after a partial success will create duplicate rows in `connection_extracted_rates`.

Fix: Count only successfully inserted rows, and add `ON CONFLICT (connection_id, source, effective_date) DO NOTHING` to the portal INSERT (matching the `unique_connection_rate` constraint that presumably exists given email_scan has it).

---

**[P2-04] `sync-users` commits after each error-rollback, then commits the entire batch — `sync.py` lines 85-91**

Description: When a single user's upsert fails, the code calls `await db.rollback()` (line 89) and continues. After processing all users, it calls `await db.commit()` unconditionally (line 91). This is correct for SQLAlchemy's async session model (rollback resets the transaction, subsequent statements start a new one), but it means a user that failed partway through a upsert sequence could leave the session in an uncommitted partial state for one user while successfully committing others. The behavior is correct but the pattern is confusing and would be clearer with an explicit `await db.begin()` per-row or by using `save_points`.

Additionally, after error rollback, the error is appended to `errors` but the error object includes the raw email address (`"email": email`), which will be returned to the caller in the JSON response. For a cron endpoint, this may appear in GHA logs.

Fix (minor): Redact email in error objects to avoid PII in logs:
```python
errors.append({"user_id": neon_id, "error": str(exc)})  # omit email
```

---

**[P2-05] `data-quality` endpoints lack logging for degraded/stale results — `data_quality.py`**

Description: All three data quality endpoints (`/freshness`, `/anomalies`, `/sources`) compute stale/degraded counts but never log a warning when those counts are nonzero. If these are called by a monitoring workflow, there is no structured log event to trigger an alert on. The `check-alerts` and `health-data` endpoints both emit `logger.info` or `logger.warning` on notable outcomes; data quality endpoints emit nothing.

Fix: Add structured warning logs:
```python
if stale_count > 0:
    logger.warning("data_quality_stale_detected", stale_count=stale_count, total=len(report))
```

---

**[P2-06] `billing.py` always calls `max(retry_count, 3)` which loses the real retry_count — `billing.py` line 72**

Description:
```python
retry_count=max(retry_count, 3),
```
`retry_count` is read from `account.get("retry_count", 3)` (already defaulting to 3). Then it is passed to `send_dunning_email()` as `max(retry_count, 3)`, meaning a user with only 1 failed retry will receive an email with `retry_count=3` context, which may cause the dunning email template to render an inaccurate message (e.g., "after 3 failed payment attempts" when only 1 attempt was made).

Fix: Remove the `max()` call and use the actual retry count:
```python
retry_count=retry_count,
```
The floor should be enforced in the DunningService or template, not silently here.

---

**[P2-07] `fetch-gas-rates`, `fetch-heating-oil`, `fetch-propane` call private `eia_client._fetch_series()` — `data_pipeline.py` lines 375, 400, 460, 485**

Description: All three fuel-type endpoints call `eia_client._fetch_series(...)` directly — a private method of `EIAClient`. This is the same coupling concern as P2-02 but more likely to cause breakage since EIA client refactoring would silently break these endpoints without any public API contract violation.

Fix: Expose `fetch_series()` (public) on `EIAClient`, or add dedicated public methods like `fetch_heating_oil_prices()` and `fetch_propane_prices()` that encapsulate the params.

---

**[P2-08] `sync-connections` returns individual connection results in response body — `sync.py` lines 117-126**

Description: `sync_connections` includes `"results": results` in its response, which is the full list of per-connection sync outcomes. For a user base with many active UtilityAPI connections, this could be a very large response body. The GHA workflow receives this payload but only cares about the summary counts.

Fix: Omit the `results` array from the HTTP response (it is already logged by the connection sync service). Add an opt-in `?include_details=true` query parameter if needed for debugging.

---

#### P3 — Low

**[P3-01] `data_pipeline.py` has no tests for `fetch-gas-rates`, `fetch-heating-oil`, `fetch-propane`, `fetch-heating-oil` routes**

Description: `test_internal_data_pipeline.py` exists but the three energy-pricing routes added later (`/fetch-gas-rates`, `/fetch-heating-oil`, `/fetch-propane`) are not covered. The `scrape-rates`, `fetch-weather`, and `geocode` routes do have coverage.

Fix: Add basic tests for the three fuel-type endpoints, at minimum testing the 503 response when `eia_api_key` is not configured.

---

**[P3-02] `data_pipeline.py` uses `Optional[WeatherRequest] = None` as default parameter in `fetch-weather` — `data_pipeline.py` line 127**

Description: The `Optional[WeatherRequest] = None` pattern on a FastAPI POST endpoint body parameter is unusual and can cause subtle issues with OpenAPI schema generation — FastAPI may render the body as optional in the schema, which is correct here, but the generated client types will indicate the body is nullable. The more idiomatic pattern is `request: WeatherRequest = Body(WeatherRequest())`.

Fix:
```python
@router.post("/fetch-weather", tags=["Internal"])
async def fetch_weather_data(
    request: WeatherRequest = Body(default_factory=WeatherRequest),
    db: AsyncSession = Depends(get_db_session),
):
```

---

**[P3-03] `ScrapeRequest` uses `List[dict]` instead of a typed model — `data_pipeline.py` lines 106-113**

Description: The `supplier_urls` field accepts untyped `dict` items. There is no validation that each dict has `supplier_id` or `url` keys. A missing `url` key will cause a `KeyError` deep in `RateScraperService`, which will bubble up as a 500.

Fix: Replace `List[dict]` with `List[SupplierUrl]` as described in P1-02.

---

**[P3-04] Lazy service imports inside endpoint function bodies throughout all files**

Description: Every endpoint in every file uses the pattern of importing service classes inside the function body (e.g., `from services.alert_service import AlertService`). This is done to avoid circular imports at module load time. While functional, it means: (a) import errors are only discovered at request time, not at startup; (b) IDE tooling and static analysis do not catch missing modules; (c) each request for a cold-started endpoint pays a (small) import resolution cost.

This is a project-wide pattern noted in many files. For the internal endpoints where cold starts matter more (each cron invocation is effectively a cold path), it is worth noting.

Fix: Restructure to use module-level imports and resolve circular imports via dependency injection or restructuring of the service layer. This is a larger refactor; the immediate mitigation is to add a startup health check that imports each service to validate availability at app startup.

---

**[P3-05] `market-research` result response includes full Tavily result content — `data_pipeline.py` line 221**

Description: `"results": results` in the response includes the full Tavily search result content (multi-KB text). Similar to P2-01, this will appear in GHA job logs.

Fix: Return only the summary (`regions`, `result_count`, `persisted`) and strip raw content from the HTTP response.

---

**[P3-06] `data_pipeline.py` has an unreferenced `GeocodeRequest` body class field for `address` not validated as a real US address**

Description: The `geocode` endpoint accepts any string as `address` with no length cap. A very long input string is passed directly to `GeocodingService.geocode()` which makes an outbound HTTP call with it. This is behind the API key so the risk is minimal, but a length limit is good hygiene.

Fix:
```python
class GeocodeRequest(BaseModel):
    address: str = Field(..., min_length=5, max_length=500, description="US address to geocode")
```

---

### Statistics

- Files audited: 11 (`__init__.py`, `alerts.py`, `billing.py`, `data_pipeline.py`, `data_quality.py`, `email_scan.py`, `ml.py`, `operations.py`, `portal_scan.py`, `sync.py`, `../../../api/dependencies.py`)
- Supporting files reviewed: `data_persistence_helper.py`, `app_factory.py`, 8 test files
- Total findings: 18 (P0: 1, P1: 5, P2: 8, P3: 4 [counted as 6 P3 items in body, grouped])

### Priority Action Plan

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| P0-01 | Replace assert-guarded f-string SQL with parameterized or identifier-quoting approach in `health-data` | Low | High |
| P1-01 | Fix `persist_batch` to rollback and return 0 on commit failure | Low | High |
| P1-02 | Add `max_length=500` and typed `SupplierUrl` model to `ScrapeRequest` | Low | Medium |
| P1-03 | Add `Query(ge=1, le=...)` constraints to `observation-stats` and `model-versions` | Low | Medium |
| P1-04 | Cap `dunning-cycle` to `MAX_DUNNING_PER_RUN = 100` accounts per invocation | Low | Medium |
| P2-01 | Strip raw Diffbot payload from `scrape-rates` response | Low | Low |
| P2-02 | Expose public `run_alert_pipeline()` on `AlertService` | Medium | Medium |
| P2-03 | Fix portal rate count and add `ON CONFLICT DO NOTHING` to portal INSERT | Low | Medium |
| P2-06 | Remove `max(retry_count, 3)` coercion in `billing.py` | Low | Low |
