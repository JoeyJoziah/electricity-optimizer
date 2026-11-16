# Audit Report: Backend Services Layer
**Scope**: `backend/services/*.py` — all 52 Python files
**Date**: 2026-03-18
**Auditor**: python-pro agent
**Method**: READ-ONLY — no source files modified

---

## Coverage

All 52 service files were read in full:

`ab_test_service.py`, `affiliate_service.py`, `agent_service.py`, `alert_renderer.py`, `alert_service.py`, `analytics_service.py`, `bill_parser.py`, `cca_service.py`, `community_service.py`, `community_solar_service.py`, `connection_analytics_service.py`, `connection_sync_service.py`, `data_persistence_helper.py`, `data_quality_service.py`, `dunning_service.py`, `email_oauth_service.py`, `email_scanner_service.py`, `email_service.py`, `feature_flag_service.py`, `forecast_service.py`, `gas_rate_service.py`, `geocoding_service.py`, `heating_oil_service.py`, `hnsw_vector_store.py`, `kpi_report_service.py`, `learning_service.py`, `maintenance_service.py`, `market_intelligence_service.py`, `model_version_service.py`, `neighborhood_service.py`, `notification_dispatcher.py`, `notification_service.py`, `observation_service.py`, `optimization_report_service.py`, `portal_scraper_service.py`, `price_service.py`, `price_sync_service.py`, `propane_service.py`, `push_notification_service.py`, `rate_change_detector.py`, `rate_export_service.py`, `rate_scraper_service.py`, `recommendation_service.py`, `referral_service.py`, `savings_aggregator.py`, `savings_service.py`, `stripe_service.py`, `utility_discovery_service.py`, `vector_store.py`, `water_rate_service.py`, `weather_service.py`, `__init__.py`

---

## Audit Dimensions

Each finding was evaluated against the following 13 dimensions:

1. Business logic correctness — edge cases, null handling, validation
2. Database session management — async session usage, transaction boundaries, no `asyncio.gather` with shared sessions
3. Error handling — exception types, propagation, no swallowed errors
4. External API calls — timeout handling, retry logic, error handling
5. Caching — Redis patterns, TTL management, cache invalidation
6. Async patterns — proper `await` usage, no blocking calls in async context
7. Service boundaries — separation of concerns, no circular dependencies
8. Data transformation — Pydantic model usage, serialization safety
9. GDPR compliance — data deletion handling, user data access patterns
10. Logging — structured logging consistency, no PII in logs, log levels
11. Rate limiting — atomic operations, TOCTOU safety
12. Email handling — template rendering, error handling, dual-provider
13. Notification fan-out — IN_APP first, then PUSH+EMAIL concurrently

---

## P0 — Critical: Data Corruption / Security / Production Breakage

### P0-1: `data_quality_service.py` — Non-Existent Column References Break `detect_anomalies`
**File**: `backend/services/data_quality_service.py`
**Lines**: ~107–133
**Dimension**: Business logic correctness, DB session management

The `detect_anomalies` SQL query references two columns that do not exist in the `electricity_prices` table:
- `rate_per_kwh` — the actual column is `price_per_kwh`
- `updated_at` — the actual column is `timestamp`

This means every call to `detect_anomalies()` raises a `sqlalchemy.exc.ProgrammingError` (PostgreSQL `column does not exist`) at runtime. The anomaly detection feature is completely broken in production. The freshness check in the same file likely uses `timestamp` correctly elsewhere, making this an isolated inconsistency introduced during refactoring.

**Impact**: The `/internal/data-quality` endpoint (if wired) and any callers of `detect_anomalies()` throw 500 errors. Anomaly detection is silently non-functional.

---

### P0-2: `agent_service.py` — Fire-and-Forget Task Lacks Session and May Be Garbage-Collected
**File**: `backend/services/agent_service.py`
**Lines**: ~305–315
**Dimension**: Async patterns, DB session management

`asyncio.create_task(self._run_async_job(...))` creates a background task with no reference stored and no `db` session passed. Per asyncio documentation, tasks not referenced by user code can be garbage-collected mid-execution. Additionally, `_run_async_job` uses `self._db` which is the request-scoped `AsyncSession` — by the time the background task runs, the HTTP request has ended, the session has been closed, and any DB operations in the background task will raise `sqlalchemy.exc.InvalidRequestError`.

**Impact**: Async job tasks fail silently on any DB access after the request completes. Job status is never written to Redis, leaving the caller with a dangling job ID.

---

### P0-3: `community_service.py` — `retroactive_moderate` Uses `asyncio.gather` with Shared `AsyncSession`
**File**: `backend/services/community_service.py`
**Lines**: ~454–484
**Dimension**: DB session management, async patterns

`retroactive_moderate` calls:
```python
await asyncio.gather(*(classify_post(p) for p in posts))
```
where `classify_post` is a coroutine that uses `db` (passed in) and updates rows with the same session concurrently. As documented in `CLAUDE.md` and confirmed by SQLAlchemy async docs, concurrent use of a single `AsyncSession` across `asyncio.gather` tasks causes undefined behavior including session corruption.

**Impact**: Bulk re-moderation operations can corrupt session state, leading to mixed-up DB operations, partial updates applied to wrong rows, or `MissingGreenlet` exceptions that crash the endpoint.

---

## P1 — High: Incorrect Logic / Silent Failures / Security Weakness

### P1-1: `agent_service.py` — TOCTOU Race in `check_rate_limit` / `increment_usage`
**File**: `backend/services/agent_service.py`
**Lines**: ~110–153
**Dimension**: Rate limiting

`check_rate_limit` (line ~110) reads the current usage count. `increment_usage` (line ~140) is called separately afterward. These are two non-atomic operations. A concurrent request can pass the check between these two calls, allowing more than the tier limit of requests through. The `CLAUDE.md` critical patterns explicitly call for `INSERT ... ON CONFLICT DO UPDATE SET count=count+1 RETURNING count` for atomic rate limiting.

**Impact**: Under concurrent load (race with another in-flight request), users can exceed their daily AI agent quota. A Free user limited to 3/day could fire 4+ concurrent requests and all would pass the rate check.

---

### P1-2: `notification_dispatcher.py` — `_dispatch_push` and `_dispatch_email` Share `self._db` Concurrently
**File**: `backend/services/notification_dispatcher.py`
**Lines**: ~210–253
**Dimension**: DB session management, notification fan-out

After the IN_APP step creates the `notification_id`, the dispatcher runs:
```python
await asyncio.gather(
    _dispatch_push(...),
    _dispatch_email(...),
    return_exceptions=True
)
```
Both closures access `self._db` to read notification templates or update delivery status. This is a shared `AsyncSession` used concurrently — a violation of the known rule in this codebase.

**Impact**: Concurrent reads are generally safe, but if either closure issues a write (status update) while the other is mid-read, session corruption can occur. This is a latent bug that becomes visible under load.

---

### P1-3: `forecast_service.py` — `where_clause` Parameter Directly Interpolated into SQL
**File**: `backend/services/forecast_service.py`
**Lines**: ~182–199
**Dimension**: Security (SQL injection)

`_forecast_from_table` accepts a `where_clause: Optional[str]` parameter and inserts it directly into the SQL string:
```python
conditions.append(where_clause)
...
where = " AND ".join(conditions)
result = await self.db.execute(text(f"SELECT ... WHERE {where}"), params)
```
While current callers pass hardcoded strings (`"utility_type = 'NATURAL_GAS'"`, `None`), the parameter is not validated, not allowlisted, and not parameterized. If a future caller passes user-controlled input, this is a textbook SQL injection vector.

Additionally, `_forecast_electricity` at line ~129 uses `region_filter = "AND region = :region"` (safely parameterized) but it is still built via f-string interpolation. The pattern is inconsistent and fragile.

**Impact**: SQL injection risk if the method is ever called with user-supplied `where_clause`. Current callers are safe; the risk is in future misuse.

---

### P1-4: `email_service.py` — No Timeout on Resend API Call, PII in Logs
**File**: `backend/services/email_service.py`
**Lines**: ~80–110
**Dimension**: External API calls, logging

`asyncio.to_thread(resend.Emails.send, params)` wraps the synchronous Resend SDK but applies no `asyncio.wait_for` timeout. If the Resend API hangs, the worker thread blocks indefinitely — the thread pool fills up, and new async tasks queue behind it until the event loop appears frozen.

Additionally, at line ~100 the log entry `email_sent_resend` includes `to=params["to"]` which is a user email address — PII in production logs.

**Impact**: Resend API degradation hangs the event loop indirectly. PII violation in structured logs sent to Grafana.

---

### P1-5: `email_oauth_service.py` — OAuth State Tokens Have No Expiry, Enabling Replay Attacks
**File**: `backend/services/email_oauth_service.py`
**Lines**: ~80–120
**Dimension**: Security

`generate_oauth_state()` creates an HMAC-signed token containing a random nonce but no timestamp or expiry. `verify_oauth_state()` validates only the HMAC signature, not a TTL. A state token intercepted from a user's OAuth flow can be replayed indefinitely against the callback endpoint.

OAuth 2.0 best practices (RFC 6749) require state tokens to be short-lived (typically 10 minutes).

**Impact**: If a state token is leaked (e.g., from a referrer header, proxy log, or phishing redirect), an attacker can complete the OAuth flow on behalf of the victim at any time in the future.

---

### P1-6: `observation_service.py` — `datetime.utcnow()` Produces Naive Datetime (Deprecated)
**File**: `backend/services/observation_service.py`
**Line**: 127
**Dimension**: Business logic correctness

```python
cutoff = datetime.utcnow() - timedelta(days=days)  # noqa: DTZ003
```
The comment explicitly suppresses the linter warning, but the underlying problem is real: `datetime.utcnow()` returns a naive datetime. If the PostgreSQL driver compares this against a `TIMESTAMPTZ` column, the behavior is driver-dependent and may produce incorrect cutoffs or raise `TypeError` with strict drivers. The noqa suppression hides the issue from CI.

All other datetime usages in the codebase use `datetime.now(timezone.utc)`.

**Impact**: The `archive_old_observations` function may archive too many or too few rows, or fail entirely, depending on database driver strictness.

---

### P1-7: `portal_scraper_service.py` — Non-Allowlisted Domains Log Warning But Still Scrape
**File**: `backend/services/portal_scraper_service.py`
**Lines**: ~87–98
**Dimension**: Security (SSRF)

The SSRF domain-allowlist check logs a warning for non-allowlisted domains but does not reject the request:
```python
if domain not in ALLOWED_DOMAINS:
    logger.warning("portal_domain_not_allowlisted", domain=domain)
    # Continues to scrape anyway
```
This is partial SSRF protection. An attacker who can control the portal URL (e.g., via a malicious portal connection configuration) can reach internal services (Redis, metadata endpoints, Neon DB control plane).

**Impact**: SSRF vulnerability against any URL a user can register as a portal connection. The allowlist is present but ineffective.

---

### P1-8: `recommendation_service.py` — Blocking `sqlite3` Call from Async Context
**File**: `backend/services/recommendation_service.py`
**Lines**: ~200–220
**Dimension**: Async patterns

`_adjust_confidence_from_patterns` calls `self._vector_store.search()` synchronously. `VectorStore.search()` uses `sqlite3.connect()` (blocking I/O). This blocks the asyncio event loop for the duration of the SQLite query — all other async tasks queued on the same event loop are starved.

`HNSWVectorStore` provides `async_search()` which wraps the call in `asyncio.to_thread`. The recommendation service should use `async_search` instead.

**Impact**: Event loop starvation during recommendation confidence adjustment. Latency spikes visible to all concurrent requests.

---

## P2 — Medium: Correctness Issues / Technical Debt / Code Quality

### P2-1: `optimization_report_service.py` — Off-By-One: Gets Oldest Supplier, Not Cheapest
**File**: `backend/services/optimization_report_service.py`
**Line**: ~137
**Dimension**: Business logic correctness

```python
rows[-1].get('supplier', 'best rate')
```
`rows[-1]` is the last element in the query result. If the query orders rows by `price_per_kwh ASC` (cheapest first), then `rows[-1]` is the most expensive supplier, not the cheapest. If ordered by `timestamp DESC` (most recent first), then `rows[-1]` is the oldest entry.

The intent appears to be "the supplier with the best rate", but the implementation gets the last row of whatever ORDER BY the query used.

**Impact**: The optimization report recommends switching to the wrong supplier. Users may be shown misleading savings estimates.

---

### P2-2: `market_intelligence_service.py` — Hardcoded Year 2026 in Search Query
**File**: `backend/services/market_intelligence_service.py`
**Line**: ~62
**Dimension**: Business logic correctness

```python
f"{region} electricity rate change 2026"
```
This hardcoded year will produce stale/incorrect Tavily search results starting in 2027. The search should use the current year dynamically: `datetime.now().year`.

**Impact**: Market intelligence searches return stale results starting 2027-01-01.

---

### P2-3: `savings_service.py` — Dead Code: `_compute_streak` Never Called
**File**: `backend/services/savings_service.py`
**Lines**: ~278–303
**Dimension**: Code quality

The `_compute_streak` static method computes a savings streak in Python. The actual streak is computed via a SQL CTE in the main query. This method is unreachable dead code that will mislead future maintainers into thinking the Python path is active.

**Impact**: Technical debt. No runtime impact.

---

### P2-4: `hnsw_vector_store.py` — Module-Level Singleton Not Thread-Safe
**File**: `backend/services/hnsw_vector_store.py`
**Lines**: ~346–354
**Dimension**: Async patterns, business logic

```python
def get_vector_store_singleton() -> "HNSWVectorStore":
    global _vector_store_singleton
    if _vector_store_singleton is None:
        _vector_store_singleton = HNSWVectorStore()
    return _vector_store_singleton
```
Under concurrent async startup (multiple requests arriving simultaneously before the singleton is initialized), multiple `HNSWVectorStore` instances can be created, each with their own HNSW index rebuild from SQLite. This is a TOCTOU race.

Additionally, `HNSWVectorStore.__init__` calls `_build_index()` which calls `sqlite3.connect()` (blocking I/O) synchronously — this blocks the event loop during first request if the singleton hasn't been initialized yet.

**Impact**: Multiple HNSW index builds on cold start (expensive); potential double-initialization of the singleton under high concurrency.

---

### P2-5: `dunning_service.py` — Commit Before Email Send Creates Inconsistent State
**File**: `backend/services/dunning_service.py`
**Lines**: ~338, ~387
**Dimension**: DB session management, error handling

The failure event is committed to the DB at line ~338. The email is sent afterward. A second commit at line ~387 marks `email_sent = True`. If the email send fails between these commits:
- The failure record exists in the DB (committed)
- `email_sent` remains `False`
- The dunning service may retry correctly on the next cycle

However, if the second commit (line ~387) fails after the email was successfully sent:
- The user received the dunning email
- The DB still shows `email_sent = False`
- The user will receive duplicate dunning emails on the next cycle

**Impact**: Dunning email deduplication is based on `email_sent` flag — a commit failure after a successful send causes duplicate emails to users, which is harmful to customer experience.

---

### P2-6: `community_service.py` — `MODERATION_TIMEOUT_SECONDS` Mismatch vs. Documentation
**File**: `backend/services/community_service.py`
**Line**: ~35
**Dimension**: Business logic correctness

`MODERATION_TIMEOUT_SECONDS = 5` but `CLAUDE.md` states "AI moderation: ... fail-closed 30s." The 5-second timeout is extremely aggressive for a Groq API call with network latency and may cause frequent moderation failures, falling through to "fail-closed" (post rejected or flagged).

**Impact**: High moderation false-failure rate under normal network conditions; community posts unnecessarily rejected during Groq API latency spikes.

---

### P2-7: `kpi_report_service.py` — Cross-Schema Dependency on `neon_auth.sessions`
**File**: `backend/services/kpi_report_service.py`
**Lines**: ~60–80
**Dimension**: Service boundaries, DB session management

The KPI query joins across `neon_auth.sessions` (the Better Auth internal schema):
```sql
SELECT COUNT(*) FROM neon_auth.sessions WHERE ...
```
This is a fragile dependency on Better Auth's internal schema. Better Auth version upgrades may rename, restructure, or drop this table without warning, breaking the KPI report.

**Impact**: KPI reports break silently on Better Auth upgrades.

---

### P2-8: `heating_oil_service.py` and `propane_service.py` — Price Comparison Subquery Timing Mismatch
**Files**: `backend/services/heating_oil_service.py` (~line 121), `backend/services/propane_service.py` (~line 118)
**Dimension**: Business logic correctness

Both services use the same pattern:
```sql
WHERE state IN (:state, 'US')
  AND fetched_at = (
      SELECT MAX(fetched_at) FROM propane_prices
      WHERE state IN (:state, 'US')
  )
```
The `MAX(fetched_at)` subquery returns a single maximum timestamp across BOTH states. If the national average (`'US'`) was last fetched at 10:00 and the state was last fetched at 10:05, the query returns only the state's 10:05 row (the national row is excluded because it doesn't match the max timestamp). The comparison then falls through to `national_price = None`, and `difference_pct` returns `None` rather than the actual percentage difference.

**Impact**: Price comparisons return null deltas whenever state and national data are fetched at different times — which is the normal case.

---

### P2-9: `price_service.py` — Leaks Internal Repository Implementation Detail
**File**: `backend/services/price_service.py`
**Line**: ~410
**Dimension**: Service boundaries

```python
result = await self._repo._db.execute(...)
```
`PriceService` accesses `self._repo._db` directly, bypassing the repository abstraction. This couples the service to the repository's private implementation. If `PriceRepository` changes how it stores the session (e.g., moves to a different attribute name), the service silently breaks.

**Same pattern** exists in `observation_service.py` lines ~130, ~140, ~151 which accesses `self._repo._db` directly.

**Impact**: Technical debt / brittle service boundary. No immediate runtime impact.

---

### P2-10: `connection_analytics_service.py` — `detect_rate_changes` Query Orders Inconsistently
**File**: `backend/services/connection_analytics_service.py`
**Lines**: ~243–257
**Dimension**: Business logic correctness

```sql
ORDER BY cer.connection_id, cer.effective_date DESC
```
The `LAG()` window function uses `ORDER BY cer.effective_date` (ASC by default inside the window frame), but the outer `ORDER BY` is `DESC`. The LAG function compares each row to the previous row in the window's ascending order, so `prev_rate` is the chronologically earlier rate. However, the outer DESC ordering means the first returned row for each connection is the most recent — but `prev_rate` for that row is the second-most-recent, which is correct. This happens to work, but it's confusing and relies on two conflicting sort directions that must both be correct simultaneously.

**Impact**: Fragile query that could produce wrong rate change direction if the ORDER BY or window definition is modified. No immediate bug.

---

### P2-11: `community_solar_service.py` — SQL Injection Risk via `enrollment_status` in f-string
**File**: `backend/services/community_solar_service.py`
**Lines**: ~47–66
**Dimension**: Security

```python
where_clauses.append("enrollment_status = :enrollment_status")
```
The `enrollment_status` value is properly parameterized. However the `where_sql = " AND ".join(where_clauses)` result is inserted into the query via f-string:
```python
text(f"""... WHERE {where_sql} ...""")
```
The clause strings themselves are hardcoded so this is safe for current callers. But the pattern is SQL injection prone if any non-parameterized condition is ever added to `where_clauses`.

**Impact**: Current code is safe. Pattern risk for future modifications.

---

### P2-12: `rate_export_service.py` — Table and Column Names from Config Dict Used in f-string SQL
**File**: `backend/services/rate_export_service.py`
**Lines**: ~151–181
**Dimension**: Security

`EXPORT_CONFIGS` is a module-level constant with hardcoded table/column names. These values are interpolated directly into SQL via f-string in `_fetch_data`. The config dict is not user-supplied, so there is no immediate injection risk, but there is also no allowlist validation. A code modification that adds user-controlled config values would immediately become injectable.

**Impact**: Pattern risk. No current injection vector.

---

## P3 — Low: Style / Consistency / Minor Improvement

### P3-1: Inconsistent Logger Type Across Services (stdlib vs. structlog)
**Files**: `learning_service.py`, `observation_service.py`, `vector_store.py`, `price_service.py`, `recommendation_service.py`, `price_sync_service.py`, `model_version_service.py` (imports both)

Most services use `structlog.get_logger(__name__)`. The following use `logging.getLogger(__name__)` (stdlib):
- `backend/services/learning_service.py` (line 33)
- `backend/services/observation_service.py` (line 18)
- `backend/services/vector_store.py` (line 23)
- `backend/services/price_service.py` (line 17)
- `backend/services/recommendation_service.py`
- `backend/services/price_sync_service.py`

Stdlib `logging` does not produce structured JSON logs. Entries from these services will appear as plaintext strings in Grafana/Loki, making correlation and filtering significantly harder.

Additionally, stdlib `logger.warning()` does not accept keyword arguments the way structlog does — the pattern `logger.info("...", key=val)` works in structlog but raises `TypeError` in stdlib logging. Services that mix the styles may fail at runtime if they use keyword-style log calls.

**Impact**: Reduced observability for ML/learning/vector store subsystems. Potential `TypeError` if structlog-style keyword args are used with a stdlib logger.

---

### P3-2: `notification_service.py` — Missing `Optional` Type Annotation
**File**: `backend/services/notification_service.py`
**Line**: ~25
**Dimension**: Code quality

```python
def create(self, ..., body: str = None, ...):
```
The `body` parameter has a default of `None` but its type annotation is `str` (not `Optional[str]`). Under `mypy --strict` this is a type error. Pydantic models that call this with `None` will pass a `None` where `str` is expected.

**Impact**: mypy strict mode failure. No runtime impact since Python is duck-typed.

---

### P3-3: `gas_rate_service.py` — Field Naming Confusion: `price_per_kwh` Stores $/therm
**File**: `backend/services/gas_rate_service.py`
**Lines**: ~70–80
**Dimension**: Code quality, data transformation

Natural gas prices are stored in the `price_per_kwh` column of `electricity_prices` with `utility_type = 'NATURAL_GAS'`, but the actual unit is $/therm (as noted in a comment). The column name `price_per_kwh` is misleading for gas prices and could cause incorrect calculations if code assumes the column is always $/kWh.

The `rate_export_service.py` exports natural gas data with `"unit": "$/therm"` which is correct, but the column used is still `price_per_kwh` — a consumer reading only the column name would compute wrong values.

**Impact**: Potential unit conversion errors for consumers of the gas rate data.

---

### P3-4: `hnsw_vector_store.py` — `_build_index` Blocking SQLite I/O in Constructor
**File**: `backend/services/hnsw_vector_store.py`
**Lines**: ~70–71, ~73–114
**Dimension**: Async patterns

`HNSWVectorStore.__init__` calls `_build_index()` which calls `sqlite3.connect()` synchronously. When the singleton is first initialized during a request (in an async context), this blocks the event loop for the duration of the SQLite read. With 10,000 vectors at 24 dimensions each, this could be 50–200ms of blocking.

**Impact**: Cold-start latency spike of 50–200ms on first request after server restart.

---

### P3-5: `connection_sync_service.py` — `latin-1` Encoding for Bytes Conversion Is Non-Obvious
**File**: `backend/services/connection_sync_service.py`
**Line**: ~141
**Dimension**: Code quality

```python
auth_uid_encrypted.encode("latin-1")
```
`latin-1` is used as a binary-safe round-trip encoding (bytes → str → bytes). This is a known Python pattern but highly non-obvious and will confuse future maintainers who expect `utf-8`. A comment explaining why `latin-1` is intentional would prevent well-meaning refactors from introducing a data corruption bug.

**Impact**: Documentation gap. No runtime issue.

---

### P3-6: `kpi_report_service.py` — `pg_class.reltuples` Is an Estimate, Not Exact Count
**File**: `backend/services/kpi_report_service.py`
**Lines**: ~85–90
**Dimension**: Business logic correctness (minor)

The KPI report uses `pg_class.reltuples` for table size estimates. These are stale statistics updated by AUTOVACUUM and can be significantly off (20–30%) for rapidly growing tables. The KPI dashboard may show inaccurate table sizes between AUTOVACUUM runs.

**Impact**: Dashboard metric inaccuracy. No functional impact.

---

### P3-7: `email_scanner_service.py` — Serial N+1 HTTP Calls for Gmail Message Fetch
**File**: `backend/services/email_scanner_service.py`
**Lines**: ~200–250
**Dimension**: Async patterns, external API calls

`scan_gmail_inbox` fetches message IDs in a list call, then fetches each individual message body in a serial loop. With 50 emails in the inbox, this is 1 + 50 = 51 sequential HTTP requests. The `httpx.AsyncClient` is async-capable and could run these concurrently with `asyncio.gather`, bounded by a semaphore to respect Google's rate limits.

Additionally, `raise_for_status()` propagates raw `httpx.HTTPStatusError` to the caller without wrapping in a domain exception. The caller receives a framework exception rather than a meaningful `EmailScanError`.

**Impact**: Gmail inbox scans take much longer than necessary. HTTP errors surface as raw httpx exceptions in API responses.

---

### P3-8: `analytics_service.py` — Cache Lock Abandoned on Exception
**File**: `backend/services/analytics_service.py`
**Lines**: ~120–145
**Dimension**: Caching, error handling

The cache stampede prevention uses a lock key in Redis with `px=5000` (5-second TTL). If `_compute_stats()` raises an exception before setting the cache result, the lock key remains in Redis for up to 5 seconds, blocking all other callers from computing the cache. The 5-second TTL self-heals, but this causes a 5-second window of blocked analytics requests per exception.

**Impact**: Analytics endpoint unresponsive for up to 5 seconds after a DB error during cache population.

---

### P3-9: `alert_service.py` — `create_alert` FOR UPDATE Lock Scope Is Correct But Not Documented
**File**: `backend/services/alert_service.py`
**Lines**: ~280–310
**Dimension**: DB session management, business logic

The free-tier alert limit check uses `SELECT ... FOR UPDATE` to prevent TOCTOU races on concurrent alert creation. This is correct. However, the transaction boundary is not explicit — the lock is acquired inside the `traced` context manager which may not correspond to a DB transaction boundary. If `traced` does not open a transaction, the `FOR UPDATE` behavior depends on SQLAlchemy's autocommit mode.

**Impact**: The FOR UPDATE pattern should be verified to be inside a transaction. If autocommit is enabled, `FOR UPDATE` is a no-op and the race condition exists despite the lock.

---

### P3-10: `stripe_service.py` — Redundant User Re-Fetch
**File**: `backend/services/stripe_service.py`
**Lines**: ~541, ~561
**Dimension**: Performance, code quality

At line ~541 the user is fetched by Stripe customer ID. At line ~561 the same user is fetched again by `user_id`. The second fetch is redundant — the user object from line ~541 already has `user_id` as an attribute.

**Impact**: One extra SELECT per webhook event. Negligible performance impact.

---

### P3-11: `market_intelligence_service.py` — No Retry or Timeout Handling for Tavily
**File**: `backend/services/market_intelligence_service.py`
**Lines**: ~40–65
**Dimension**: External API calls, error handling

The Tavily search call uses `httpx.AsyncClient` with a default timeout (5 seconds per httpx default). If Tavily times out, the exception propagates raw to the caller. There is no retry logic, no exponential backoff, and no fallback.

**Impact**: Transient Tavily outages fail the weekly market research pipeline with no retry.

---

### P3-12: `propane_service.py` and `heating_oil_service.py` — `store_prices` Commits After Each Row Exception but Before Loop Ends
**File**: `backend/services/propane_service.py`
**Lines**: ~219–245
**Dimension**: DB session management, error handling

```python
for p in prices:
    try:
        await self.db.execute(...)
        stored += 1
    except Exception as e:
        logger.warning(...)
await self.db.commit()
```
Individual row failures are caught (correct for fault isolation), but the commit happens after the loop completes for all rows. This means a failed row's exception triggers the `logger.warning` but the execute may have left the session in an error state (depending on the exception type). PostgreSQL in particular requires a rollback after a statement error — without it, subsequent statements in the same session raise `sqlalchemy.exc.InternalError: (psycopg2.InternalError) current transaction is aborted`.

The `on_conflict_do_update` INSERT should handle most duplicates, but malformed data could trigger a check constraint violation that aborts the transaction.

**Impact**: A single bad row can corrupt the session state, causing all subsequent rows in the batch to fail with `InternalError`.

---

## Summary by Dimension

| Dimension | P0 | P1 | P2 | P3 |
|-----------|----|----|----|----|
| Business logic correctness | 1 | 1 | 4 | 2 |
| DB session management | 2 | 2 | 2 | 2 |
| Error handling | 0 | 1 | 1 | 2 |
| External API calls | 0 | 1 | 0 | 2 |
| Caching | 0 | 0 | 0 | 1 |
| Async patterns | 1 | 2 | 1 | 2 |
| Service boundaries | 0 | 0 | 2 | 0 |
| Data transformation | 0 | 0 | 0 | 1 |
| GDPR compliance | 0 | 0 | 0 | 0 |
| Logging | 0 | 1 | 0 | 1 |
| Rate limiting | 0 | 1 | 0 | 0 |
| Email handling | 0 | 1 | 0 | 0 |
| Notification fan-out | 0 | 1 | 0 | 0 |

**Total**: 3 P0, 8 P1, 10 P2, 13 P3 = **34 findings**

---

## Priority Remediation Order

### Immediate (P0 — before next production incident)

1. **`data_quality_service.py`** — Fix column names: `rate_per_kwh` → `price_per_kwh`, `updated_at` → `timestamp` in `detect_anomalies`. This is a production 500 error on every call.

2. **`agent_service.py` background task** — Store the `asyncio.Task` reference in `self._pending_tasks` list. Use a fresh `AsyncSession` (not the request-scoped `self._db`) for the background task. Use `asyncio.wait_for` with a timeout.

3. **`community_service.py` `retroactive_moderate`** — Replace `asyncio.gather` with a sequential loop. Each `classify_post` call must await independently to avoid concurrent session access.

### High Priority (P1 — within 1 sprint)

4. **`agent_service.py` rate limiting** — Replace check-then-increment with atomic `INSERT ... ON CONFLICT DO UPDATE SET count=count+1 RETURNING count`.

5. **`notification_dispatcher.py`** — Ensure `_dispatch_push` and `_dispatch_email` closures do not share write access to `self._db`. Pass read-only data (not the session) into the concurrent tasks.

6. **`forecast_service.py`** — Add `where_clause` to an explicit allowlist or eliminate the parameter entirely, using only caller-constructed parameterized conditions.

7. **`email_service.py`** — Wrap Resend call in `asyncio.wait_for(..., timeout=10.0)`. Remove the email address from the `email_sent_resend` log entry.

8. **`email_oauth_service.py`** — Add a UTC timestamp to the OAuth state payload. In `verify_oauth_state`, reject tokens older than 10 minutes.

9. **`observation_service.py`** — Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`. Remove the `# noqa: DTZ003` suppression.

10. **`portal_scraper_service.py`** — Change the non-allowlisted domain branch from `logger.warning` to `raise ValueError` (or return an error result). The scrape must not proceed for non-allowlisted domains.

11. **`recommendation_service.py`** — Replace synchronous `self._vector_store.search()` with `await self._vector_store.async_search()`.

### Medium Priority (P2 — within 2 sprints)

12. **`optimization_report_service.py`** — Verify the query ORDER BY and fix `rows[-1]` to `rows[0]` if ordering is cheapest-first.

13. **`market_intelligence_service.py`** — Replace hardcoded `2026` with `datetime.now().year`.

14. **`savings_service.py`** — Remove dead `_compute_streak` method.

15. **`hnsw_vector_store.py` singleton** — Initialize the singleton eagerly at app startup (in `lifespan`) rather than lazily on first request. Use a threading lock or asyncio lock for the initialization.

16. **`dunning_service.py`** — Combine the two commits into a single transaction: record failure, send email, mark email_sent, then commit once.

17. **`community_service.py` moderation timeout** — Align `MODERATION_TIMEOUT_SECONDS` with the documented 30-second value, or update `CLAUDE.md` to reflect the 5-second policy decision.

18. **`propane_service.py` and `heating_oil_service.py` batch commit** — Add `await self.db.rollback()` in the exception handler before continuing to the next row, to reset the session state after a statement error.

19. **`heating_oil_service.py` / `propane_service.py` price comparison** — Fix the MAX subquery to return rows where each state matches its own MAX, using two separate DISTINCT ON queries or lateral joins.

---

## GDPR Compliance Assessment

No GDPR-specific deficiencies were found beyond those already noted in prior audits. The services do not log user PII with the exception of the `email_service.py` Resend log entry (P1-4 above). Deletion cascades cover all user-linked tables per migration 051.

## Positive Observations

The following services demonstrate excellent patterns worth highlighting:

- **`alert_service.py`** — `_batch_should_send_alerts` uses a single batched SQL query per frequency tier instead of N+1 individual checks. Clean FOR UPDATE locking for free-tier limit enforcement.

- **`rate_scraper_service.py`** — Proper `asyncio.Semaphore` concurrency control, per-supplier error isolation, `asyncio.wait_for` timeout on each call, and clear rate limiting documentation.

- **`model_version_service.py`** — Atomic promote/deactivate in a single transaction with explicit rollback on failure. Clean `ON CONFLICT DO NOTHING` for idempotent outcome recording.

- **`bill_parser.py`** — Path traversal guard with `os.path.realpath` comparison. Magic-byte file type detection rather than extension-based. Secure temporary file handling.

- **`geocoding_service.py`** — Clean dual-provider pattern (OWM primary, Nominatim fallback) with proper User-Agent header for Nominatim ToS compliance.

- **`ab_test_service.py`** — SHA-256 based deterministic assignment (not MD5), correct traffic split math, explicit `model_name` guard on version validation.

- **`forecast_service.py` `_extrapolate_trend`** — Well-implemented least-squares linear regression with R² confidence weighting. Proper handling of degenerate cases (zero denominator, negative forecasts).

- **`community_solar_service.py` `calculate_savings`** — Correct use of `Decimal` with `ROUND_HALF_UP` for financial calculations.

- **`water_rate_service.py` `calculate_monthly_cost`** — Correct incremental tier billing algorithm.
