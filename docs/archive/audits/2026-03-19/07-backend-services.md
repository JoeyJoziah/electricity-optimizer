# Backend Services Layer Audit

> Audited: 2026-03-19
> Scope: All 52 files in `backend/services/*.py`
> Auditor: Claude Opus 4.6 (read-only, zero modifications)

---

## Executive Summary

The services layer is well-structured overall, with good separation of concerns, consistent use of parameterized SQL queries, proper async patterns, and thoughtful error handling. The codebase demonstrates mature engineering practices: fail-closed moderation, SSRF protection, IDOR prevention, XSS sanitization, and dual-provider fallback chains.

That said, the audit identified **5 P0 critical findings**, **8 P1 high findings**, **12 P2 medium findings**, and **14 P3 low findings** across the 52 service files. The most concerning patterns are: (1) race conditions in shared mutable state under concurrency, (2) a module-level global API key mutation that is not thread-safe, (3) f-string SQL construction that, while using parameterized values, creates attack surface if patterns are copied incorrectly, and (4) synchronous blocking I/O called inside async contexts.

---

## P0 -- Critical (must fix before next deploy)

### P0-01: `resend.api_key` global mutation is not concurrency-safe
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/email_service.py`
**Line:** 81

```python
resend.api_key = self._settings.resend_api_key
```

The `resend` library stores its API key as a module-level global attribute (`resend.api_key`). This is set on every call to `_send_via_resend`. In a multi-worker Gunicorn/Uvicorn deployment with shared memory (e.g., `--workers 1 --threads N` or multiple async tasks in the same event loop), concurrent calls all mutate the same global. While this is fine when all callers use the same key, the pattern is fragile: if a test or misconfiguration ever supplies a different key, requests will silently use the wrong credential. More importantly, the `resend.Emails.send` call is dispatched to a thread via `asyncio.to_thread` (line 97), creating a window where another coroutine could overwrite `resend.api_key` between the assignment and the actual HTTP call.

**Recommendation:** Set `resend.api_key` once at service initialization (`__init__`) or at module load time, not on every send call. Alternatively, use the `resend.Resend(api_key=...)` client pattern if the library supports it.

---

### P0-02: `asyncio.create_task` with no reference retention -- task may be garbage collected
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/agent_service.py`
**Line:** 317

```python
asyncio.create_task(self._run_async_job(job_id, user_id, prompt, context, redis))
```

The created task is not stored in any set or variable. Per Python docs: "Save a reference to the result of this function, to avoid a task disappearing mid-execution." The event loop only holds a weak reference to tasks; if no strong reference exists, the task may be garbage collected before completion, silently dropping the user's async job with no error logged.

**Recommendation:** Store the task in a `set` and use `task.add_done_callback(task_set.discard)` to clean up completed tasks, or store references in a module-level `_background_tasks: set[asyncio.Task]` set.

---

### P0-03: `_run_async_job` leaks internal error details to Redis (accessible by user)
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/agent_service.py`
**Line:** 353

```python
json.dumps({"status": "failed", "user_id": user_id, "error": str(e)}),
```

When an async agent job fails, the raw exception string is stored in Redis and returned to the user via `get_job_result`. Exception messages may contain internal details such as database connection strings, API keys in URLs, stack trace fragments, or file paths. This violates the principle of not exposing internal error details to end users.

**Recommendation:** Store a generic user-facing message (e.g., "An internal error occurred") while logging the full exception server-side with `logger.error`. The detailed error is already logged at line 349.

---

### P0-04: TOCTOU gap between `check_rate_limit` and `increment_usage` in agent queries
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/agent_service.py`
**Lines:** 110-153 (check_rate_limit) and 253 (increment_usage call in query_streaming)

While `check_rate_limit` uses an atomic upsert to read the current count (good), the actual increment happens later in `increment_usage` (line 253) -- after the full LLM query has been executed. Between the rate limit check (line ~184 in the caller) and the increment (line 253), concurrent requests from the same user can all pass the check before any of them increments the counter. This allows a user to exceed their daily limit by issuing concurrent requests.

The docstring on `check_rate_limit` (line 113) claims the TOCTOU race is fixed, but the fix only prevents duplicate reads -- it does not prevent the window between check and increment.

**Recommendation:** Perform an atomic `check_and_increment` in a single query: `INSERT ... ON CONFLICT DO UPDATE SET query_count = query_count + 1 RETURNING query_count` and only allow the request if the returned count is within the limit. Roll back or decrement if the LLM call fails.

---

### P0-05: `forecast_service.py` passes `where_clause` as raw SQL string into f-string query
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/forecast_service.py`
**Line:** 185-199

```python
if where_clause:
    conditions.append(where_clause)
# ...
result = await self.db.execute(
    text(f"""
        SELECT {price_col}, {time_col}
        FROM {table}
        WHERE {where}
        ORDER BY {time_col} ASC
    """),
    params,
)
```

While the `table`, `price_col`, and `time_col` identifiers are validated against allowlists (lines 170-182), the `where_clause` parameter is **not validated** and is injected directly into the SQL string. The `where_clause` comes from the `UTILITY_CONFIGS` dictionary at the top of the file (e.g., `"utility_type = 'ELECTRICITY'"`) which is currently safe. However, if any caller ever constructs a `where_clause` from user input, this becomes a SQL injection vector. The lack of validation on this specific parameter, when all other SQL identifiers in the same function are validated, creates a misleading sense of safety.

**Recommendation:** Either validate `where_clause` against an allowlist of known clauses, or convert the static `where_clause` values in `UTILITY_CONFIGS` to parameterized form (e.g., `{"col": "utility_type", "val": "ELECTRICITY"}` and construct the clause programmatically).

---

## P1 -- High (should fix this sprint)

### P1-01: Shared mutable `results` dict in `gas_rate_service.py` concurrent gather
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/gas_rate_service.py`
**Lines:** 60-116

```python
results = {"fetched": 0, "stored": 0, "errors": 0, "details": []}

async def fetch_state(state_code: str):
    async with semaphore:
        # ...
        results["fetched"] += 1  # line 81
        results["stored"] += 1   # line 82
        results["details"].append(...)  # line 83
```

Multiple coroutines running inside `asyncio.gather` mutate the same `results` dict. While CPython's GIL prevents true data races for simple operations, `+=` on an integer is not atomic at the Python level (it's a read-modify-write). In practice, asyncio coroutines yield at `await` points and the `+=` between awaits is likely safe, but `results["details"].append(...)` interleaved with `results["errors"] += 1` in exception handlers creates subtle ordering bugs if an exception occurs during the append. More importantly, this pattern is unsafe to copy into threaded contexts.

**Recommendation:** Use the same pattern as `community_service.py`'s `retroactive_moderate` -- return per-task results from the coroutines and aggregate after `asyncio.gather` completes.

---

### P1-02: Shared mutable `results` dict in `weather_service.py` concurrent gather
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/weather_service.py`
**Lines:** 152-167

```python
results: dict[str, dict] = {}

async def _fetch_one(region: str) -> None:
    # ...
    results[region] = weather  # mutation from multiple coroutines
```

Same pattern as P1-01. While dict key assignment is effectively atomic in CPython's async model, the pattern is fragile and inconsistent with the `community_service.py` approach which collects return values from `asyncio.gather`.

**Recommendation:** Return `(region, weather)` tuples from `_fetch_one` and build the dict after gather.

---

### P1-03: `VectorStore` and `HNSWVectorStore` perform synchronous SQLite I/O in `__init__`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/vector_store.py`
**Lines:** 46-71

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/hnsw_vector_store.py`
**Lines:** ~359-364 (singleton initialization)

```python
def _init_db(self) -> None:
    os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
    with sqlite3.connect(self._db_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS ...""")
```

Both vector stores perform synchronous SQLite I/O (disk reads, table creation, index building) during `__init__`. When these are instantiated in an async FastAPI context (e.g., via the singleton pattern at line 359 of `hnsw_vector_store.py`), this blocks the event loop for the duration of the SQLite operations. For `HNSWVectorStore`, the `_build_index` method in `__init__` reads all vectors from SQLite and builds the HNSW graph, which can take significant time as the dataset grows.

**Recommendation:** Wrap the initialization in `asyncio.to_thread()` or perform lazy initialization on first use within an async wrapper.

---

### P1-04: `notification_dispatcher.py` concurrent gather closures capture mutable `results` dict
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/notification_dispatcher.py`
**Line:** 254

```python
await asyncio.gather(_dispatch_push(), _dispatch_email(), return_exceptions=True)
```

The `_dispatch_push()` and `_dispatch_email()` closures (lines 210-252) both mutate the `results` dict defined at line 192. While there are only two concurrent tasks (push and email), using `return_exceptions=True` means exceptions are returned as values rather than raised -- but the dict mutation still happens before the exception could be caught. If `_dispatch_push` raises after writing to `results`, the exception is swallowed and the partial result is silently included.

**Recommendation:** Collect results from the gather return values instead of mutating a shared dict, or at minimum handle the `return_exceptions=True` results explicitly.

---

### P1-05: `portal_scraper_service.py` SSRF allowlist is logged but not enforced
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/portal_scraper_service.py`
**Lines:** 92-98

```python
if hostname and not any(hostname == d or hostname.endswith(f".{d}") for d in _ALLOWED_DOMAINS):
    logger.warning(
        "portal_url_not_in_allowlist",
        hostname=hostname,
        url=url,
    )
    # Allow but log -- generic scraping is a documented feature
```

The SSRF protection validates the URL scheme (HTTPS only) and blocks private/internal IPs, but non-allowlisted hostnames are logged and then allowed through. This means an attacker who provides a URL like `https://evil.com/` as a portal login URL will have the service make authenticated requests (with the user's credentials) to an attacker-controlled server. The "generic scraping" feature creates a credential-forwarding vulnerability.

**Recommendation:** Either enforce the allowlist strictly (reject non-allowlisted domains) or at minimum do not send credentials (username/password) to non-allowlisted domains. The `_scrape_generic` method at line 418 posts credentials to arbitrary URLs.

---

### P1-06: `stripe_service.py` sets `stripe.api_key` as module-level global
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/stripe_service.py`
**Line:** 38

```python
stripe.api_key = settings.stripe_secret_key
```

Same class of issue as P0-01. The `stripe` library uses a module-level global for the API key. While there is typically only one Stripe key per deployment, multiple `StripeService()` instantiations (e.g., in tests) would overwrite each other's keys. All Stripe SDK calls subsequently use `asyncio.to_thread()` (good), but the global state remains fragile.

**Recommendation:** Use `stripe.StripeClient(api_key=...)` instance-based pattern (available in stripe-python v14+) instead of the global `stripe.api_key`.

---

### P1-07: `rate_export_service.py` constructs SQL from config dict values via f-string
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/rate_export_service.py`
**Lines:** 150-180

```python
cols = ", ".join(config["columns"])
# ...
result = await self.db.execute(
    text(f"""
        SELECT {cols}
        FROM {config["table"]}
        WHERE {where}
        ORDER BY {config["time_col"]} ASC
        LIMIT 10000
    """),
    params,
)
```

Table names, column names, and ordering columns are interpolated into SQL via f-strings from the `EXPORT_CONFIGS` dictionary. While the dictionary is defined at module level (lines 22-63) and not user-controlled, there is no allowlist validation (unlike `forecast_service.py` which validates against `_ALLOWED_TABLES` and `_ALLOWED_COLS`). If `EXPORT_CONFIGS` is ever modified to accept user input or dynamically constructed values, this becomes a direct SQL injection vector.

**Recommendation:** Add allowlist validation for the table and column identifiers, consistent with the pattern used in `forecast_service.py`.

---

### P1-08: `community_service.py` `moderate_post` clears pending on dual AI failure (fail-open)
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/community_service.py`
**Lines:** 397-400

```python
except Exception:
    # Both failed -- clear pending moderation
    await self._clear_pending_moderation(db, post_id)
    return
```

In `moderate_post` (the standalone moderation endpoint), when both Groq and Gemini fail, the code calls `_clear_pending_moderation` which makes the post visible. This is **fail-open** behavior, contradicting the service's documented "fail-closed" design principle stated in the module docstring (line 5) and correctly implemented in `create_post` (line 107). A post that fails AI moderation should remain hidden/pending, not be automatically published.

**Recommendation:** Remove the `_clear_pending_moderation` call on dual failure. Leave the post in pending state for the retroactive moderation pass to handle, consistent with `create_post`'s behavior.

---

## P2 -- Medium (fix within 2 sprints)

### P2-01: `savings_service.py` f-string SQL clause construction
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/savings_service.py`
**Lines:** 58-102

```python
region_clause = ""
if region:
    region_clause = " AND region = :region"
    base_params["region"] = region

combined_sql = text(f"""
    ...
    WHERE user_id = :user_id
    {region_clause}
    ...
""")
```

While the `region_clause` only contains a parameterized clause (`:region`) and the actual value goes through proper parameter binding, the pattern of injecting SQL fragments via f-string is error-prone. The same pattern appears in `savings_aggregator.py` (line 43-47). If a developer copies this pattern and accidentally interpolates a value instead of a parameter placeholder, it becomes a SQL injection.

**Recommendation:** Use conditional query building with SQLAlchemy's `text()` and explicit clause concatenation, or use a query builder pattern that makes the parameterization more explicit.

---

### P2-02: `notification_service.py` shadows Python builtin `type`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/notification_service.py`
**Line:** 24

```python
async def create(
    self,
    user_id: str,
    title: str,
    body: str = None,
    type: str = "info",
) -> None:
```

The parameter name `type` shadows the Python builtin. While this does not cause a runtime bug in this particular method, it prevents using `type()` for type checking within the function body and is a violation of Python best practices.

**Recommendation:** Rename to `notification_type` or `ntype`.

---

### P2-03: `price_service.py` accesses private `self._repo._db` directly
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/price_service.py`
**Line:** 395

```python
result = await self._repo._db.execute(...)
```

The service layer reaches into the repository's private `_db` attribute to execute a raw SQL query. This breaks the repository abstraction pattern and creates tight coupling. If the repository's internal session management changes, this code would break silently.

**Recommendation:** Add a `get_optimal_usage_windows` method to `PriceRepository` and delegate the query there.

---

### P2-04: `price_service.py` module-level `asyncio.Lock` is not safe across event loops
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/price_service.py`
**Lines:** 20-22

```python
_ensemble_predictor = None
_ensemble_load_attempted = False
_ensemble_lock = asyncio.Lock()
```

The `asyncio.Lock` is created at module import time, binding it to whatever event loop exists at that point (or no loop at all in Python 3.10+). If the module is imported before the event loop starts (common in testing or multi-process deployments), the lock may be bound to a different loop than the one used at runtime. Python 3.10+ deprecated passing `loop` to Lock, but creating it outside an async context can still cause issues in some configurations.

**Recommendation:** Create the lock lazily inside an async function, or use a sentinel pattern that initializes on first use within the running event loop.

---

### P2-05: `observation_service.py` uses deprecated `datetime.utcnow()`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/observation_service.py`
**Line:** 129 (approximate -- from prior read)

`datetime.utcnow()` is deprecated since Python 3.12 in favor of `datetime.now(UTC)`. The rest of the codebase consistently uses `datetime.now(UTC)`, making this an inconsistency.

**Recommendation:** Replace with `datetime.now(UTC)`.

---

### P2-06: `data_persistence_helper.py` row-by-row INSERT instead of batch
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/data_persistence_helper.py`
**Lines:** 42-54

```python
for row in rows:
    try:
        await db.execute(insert_stmt, row)
        persisted += 1
    except Exception as e:
        # ...
```

The `persist_batch` function inserts rows one at a time in a loop, committing all at the end. For large batches this is significantly slower than using `executemany` or VALUES-list inserts. The function name suggests batch semantics but the implementation is serial. Additionally, if the commit at line 54 fails after partial inserts, the entire batch is lost with no partial commit.

**Recommendation:** Use `executemany` or build a multi-row VALUES clause. Consider chunked commits (e.g., every 500 rows) for large batches, consistent with the `bulk_create()` pattern documented in CLAUDE.md.

---

### P2-07: `dunning_service.py` double-commit in `handle_payment_failure`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/dunning_service.py`
**Lines:** 341 and 390

```python
# Line 341: Commit the payment failure record before any early returns
await self._db.commit()
# ...
# Line 390: Single commit for the entire payment failure flow
await self._db.commit()
```

The first commit (line 341) is described as ensuring the record is persisted before early returns, but the method then does additional DB writes (marking email sent at line 366, recording escalation at line 380) followed by a second commit. If the second commit fails, the payment failure record is committed but the email/escalation status is lost, leaving the system in an inconsistent state. The inline comment "Single commit for the entire payment failure flow" at line 389 contradicts the actual double-commit.

**Recommendation:** Remove the first commit and rely solely on the final commit, or use savepoints to create recovery points within the transaction.

---

### P2-08: `vector_store.py` `record_outcome` is not atomic (read-then-write)
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/vector_store.py`
**Lines:** 227-252

```python
if success:
    conn.execute(
        "UPDATE vectors SET success_count = success_count + 1 WHERE id = ?", ...)
row = conn.execute(
    "SELECT usage_count, success_count FROM vectors WHERE id = ?", ...).fetchone()
if row and row[0] > 0:
    new_confidence = row[1] / row[0]
    conn.execute("UPDATE vectors SET confidence = ? WHERE id = ?", ...)
```

The success count increment, the select, and the confidence update are three separate operations. Concurrent calls to `record_outcome` could read stale counts and compute incorrect confidence values. SQLite's default locking may serialize writes at the file level, but the logic is still vulnerable to stale reads between statements.

**Recommendation:** Combine into a single UPDATE: `UPDATE vectors SET success_count = success_count + CASE WHEN :success THEN 1 ELSE 0 END, confidence = (success_count + CASE WHEN :success THEN 1 ELSE 0 END) / NULLIF(usage_count, 0) WHERE id = ?`.

---

### P2-09: `referral_service.py` `apply_referral` has no row-level locking
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/referral_service.py`
**Lines:** 89-116

The `apply_referral` method reads a referral (line 95), checks its status (lines 100-107), then updates it (line 109). Between the read and write, another concurrent request could claim the same referral code. The `get_referral_by_code` call does not use `FOR UPDATE` locking.

**Recommendation:** Either use `SELECT ... FOR UPDATE` in `get_referral_by_code` when called from `apply_referral`, or combine the read-check-update into a single `UPDATE ... WHERE status = 'pending' AND referee_id IS NULL RETURNING ...` query.

---

### P2-10: `analytics_service.py` cache lock allows no-data response when lock is held
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/analytics_service.py`
**Lines:** 137-145

```python
if not await self._acquire_cache_lock(cache_key):
    cached = await self._get_cached(cache_key)
    if cached:
        return cached
    # Falls through to compute -- but lock holder will also compute
```

When the cache lock is already held (another request is computing), the code re-checks the cache. If the cache is still empty (the other request hasn't finished yet), the code falls through to the computation block. This means multiple requests will compute the same expensive query simultaneously, defeating the stampede protection. The same pattern is repeated in `get_peak_hours_analysis` (line 219) and `get_supplier_comparison_analytics` (line 310).

**Recommendation:** Add a retry loop with a short sleep when the lock is held, or return a 202/stale response, rather than falling through to duplicate computation.

---

### P2-11: `maintenance_service.py` unbounded DELETE without LIMIT
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/maintenance_service.py`
**Lines:** 32-35, 108-111, 120-123, 132-135

```python
result = await self._db.execute(
    text("DELETE FROM activity_logs WHERE created_at < :cutoff"),
    {"cutoff": cutoff},
)
await self._db.commit()
```

All cleanup methods execute unbounded `DELETE` statements. On a large table, this can lock the table for an extended period, cause WAL growth, and potentially trigger statement timeouts. The `cleanup_old_prices` and `cleanup_old_observations` methods correctly delegate to PL/pgSQL functions (which may batch internally), but the remaining cleanup methods do not.

**Recommendation:** Add a `LIMIT` clause and loop until no more rows are deleted, or use batched deletes with intermediate commits.

---

### P2-12: Inconsistent logging framework usage across services
**Files:** Multiple

Some services use `structlog.get_logger()` while others use `logging.getLogger()`:

- `structlog`: `email_service.py`, `notification_service.py`, `portal_scraper_service.py`, `savings_service.py`, `agent_service.py`, `dunning_service.py`, etc. (majority)
- `logging`: `price_service.py` (line 8), `recommendation_service.py` (line 8), `vector_store.py` (line 13), `learning_service.py`

Services using stdlib `logging` miss out on structlog's structured key-value logging and cannot use keyword arguments in log calls (e.g., `logger.warning("msg", key=val)` works in structlog but not stdlib logging without `%s` formatting).

**Recommendation:** Standardize on `structlog` across all services for consistent structured logging.

---

## P3 -- Low (nice to have / tech debt)

### P3-01: `notification_service.py` `body` parameter default is `None` not `str | None`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/notification_service.py`
**Line:** 24

```python
body: str = None,
```

Should be `body: str | None = None` for correct type annotation.

---

### P3-02: `feature_flag_service.py` `update_flag` parameters default to `None` not typed as optional
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/feature_flag_service.py`
**Lines:** 93-97

```python
enabled: bool = None,
tier_required: str = None,
percentage: int = None,
```

Should use `bool | None = None`, `str | None = None`, `int | None = None`.

---

### P3-03: `feature_flag_service.py` `is_enabled` parameters default to `None` not typed
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/feature_flag_service.py`
**Lines:** 29-30

```python
user_id: str = None,
user_tier: str = None,
```

Should use `str | None = None`.

---

### P3-04: `rate_export_service.py` `format` parameter shadows Python builtin
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/rate_export_service.py`
**Line:** 76

```python
format: str = "json",
```

Shadows the Python builtin `format()`.

**Recommendation:** Rename to `output_format` or `export_format`.

---

### P3-05: `recommendation_service.py` `_compute_switching` does not handle `current_supplier = None`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/recommendation_service.py`
**Line:** 243

```python
current_supplier = user.current_supplier
```

If `user.current_supplier` is `None`, the loop at lines 247-250 will never match, and `current_price` falls back to `prices[-1].price_per_kwh` (the most expensive). This silently produces a recommendation based on incorrect data. The `or "Unknown"` fallback at line 286 only applies to the output, not the price lookup.

**Recommendation:** Return `None` or a distinct "no current supplier" recommendation when `current_supplier` is None, rather than silently comparing against the most expensive price.

---

### P3-06: `savings_service.py` `_compute_streak` is dead code
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/savings_service.py`
**Lines:** 276-302

The `_compute_streak` static method is defined but never called. The streak computation is now done entirely in SQL via the CTE in `get_savings_summary` (lines 88-96). The Python implementation is dead code.

**Recommendation:** Remove `_compute_streak` or mark it as deprecated.

---

### P3-07: `water_rate_service.py` `get_rates` unbounded query when no state filter
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/water_rate_service.py`
**Lines:** 107-115

```python
result = await self.db.execute(
    text("""
        SELECT id, municipality, state, rate_tiers, ...
        FROM water_rates
        ORDER BY state, municipality
    """),
)
```

When called without a `state` filter, the query returns all water rates with no LIMIT. As the dataset grows, this could return thousands of rows.

**Recommendation:** Add a `LIMIT` clause or enforce the `state` filter as required.

---

### P3-08: `agent_service.py` `_composio_toolset` uses `False` as sentinel value
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/agent_service.py`
**Lines:** 105-108

```python
self._composio_toolset = False  # sentinel: don't retry
# ...
return self._composio_toolset if self._composio_toolset is not False else None
```

Using `False` as a sentinel for "initialization was attempted but failed" is a type confusion pattern. A proper sentinel would be a dedicated object (e.g., `_NOT_INITIALIZED = object()`).

**Recommendation:** Use a dedicated sentinel or a separate boolean flag `_composio_init_attempted`.

---

### P3-09: `market_intelligence_service.py` sends API key in request body
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/market_intelligence_service.py`
**Line:** ~33 (from prior read)

The Tavily API key is sent in the JSON request body rather than an Authorization header. While Tavily's API may require this format, request bodies are more likely to be logged by intermediate proxies than auth headers.

**Recommendation:** Verify this is Tavily's required format. If headers are supported, prefer that.

---

### P3-10: `community_service.py` `retroactive_moderate` selects posts with ambiguous criteria
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/community_service.py`
**Lines:** 439-446

```python
WHERE is_pending_moderation = false
  AND is_hidden = false
  AND hidden_reason IS NULL
  AND created_at >= NOW() - INTERVAL '24 hours'
```

This query selects ALL visible, non-pending posts from the last 24 hours, not just those that timed out during initial moderation. Posts that were successfully moderated and approved will also be re-checked unnecessarily, wasting AI API credits.

**Recommendation:** Add a column or metadata flag to distinguish "timed out during moderation" from "successfully moderated" posts.

---

### P3-11: `price_sync_service.py` potentially unreachable code path
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/price_sync_service.py`
**Line:** ~104 (from prior read)

A condition `if prices_to_store and not session` appears to check whether a session was provided, but `session` is a required parameter in the function signature. This code path can never be reached unless the caller explicitly passes `None`.

**Recommendation:** Remove the dead branch or make `session` optional if needed.

---

### P3-12: `hnsw_vector_store.py` singleton has no thread safety
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/hnsw_vector_store.py`
**Lines:** 359-364

```python
def get_vector_store_singleton() -> "HNSWVectorStore":
    global _vector_store_singleton
    if _vector_store_singleton is None:
        _vector_store_singleton = HNSWVectorStore()
    return _vector_store_singleton
```

The singleton check-and-assign is not thread-safe. In a multi-threaded server, two threads could both see `None` and create two instances. While the async event loop is typically single-threaded, `asyncio.to_thread()` calls can trigger this from multiple OS threads.

**Recommendation:** Use a `threading.Lock` to guard the singleton initialization.

---

### P3-13: `email_scanner_service.py` individual email failures may abort scan
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/email_scanner_service.py`
(From prior read)

If an exception occurs while processing an individual email message during the scan loop, and it is not caught within the per-message handler, the entire scan operation fails. The service should catch per-message exceptions and continue processing remaining emails.

**Recommendation:** Wrap individual email processing in try/except and log failures without aborting the batch.

---

### P3-14: `learning_service.py` uses stdlib logger with structlog-style keyword args
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/learning_service.py`
(From prior read)

The service uses `logging.getLogger()` but may attempt structlog-style keyword argument logging. Stdlib `logger.warning("msg", key=val)` treats `key=val` as a format argument, not a structured field, potentially causing `TypeError` or silent formatting failures.

**Recommendation:** Switch to `structlog.get_logger()` consistent with the rest of the codebase.

---

## Cross-Cutting Observations

### What the codebase does well

1. **Parameterized SQL everywhere.** All user-supplied values flow through `:param` bind variables in `sqlalchemy.text()`. No raw string concatenation of user input into SQL.

2. **Fail-closed moderation in `create_post`.** The community service correctly leaves posts in `is_pending_moderation=true` when AI moderation times out, preventing unapproved content from appearing.

3. **IDOR prevention in agent jobs.** The `get_job_result` method verifies that the requesting user owns the job before returning results (line 372).

4. **Atomic vote toggle.** The `toggle_vote` CTE in `community_service.py` (lines 272-296) uses `INSERT ... ON CONFLICT DO NOTHING` + conditional `DELETE` to implement an atomic toggle without TOCTOU races.

5. **SSRF protection.** `portal_scraper_service.py` validates URL scheme (HTTPS only) and blocks private/internal IP ranges.

6. **Dual-provider fallback chains.** Email (Resend + SMTP), AI (Gemini + Groq), geocoding (OWM + Nominatim) all have graceful fallback.

7. **Rate limiting with semaphores.** Services that call external APIs (Diffbot, OWM, EIA) consistently use `asyncio.Semaphore` to respect rate limits.

8. **XSS sanitization.** Community posts are sanitized with `nh3.clean()` before storage.

9. **Proper async patterns.** Blocking SDK calls (Stripe, Gemini, Resend) are consistently wrapped in `asyncio.to_thread()`.

10. **Webhook signature verification.** Stripe webhooks are validated before processing.

### Systemic patterns to address

1. **F-string SQL construction**: While values are parameterized, the pattern of building SQL structure (table names, column names, WHERE clauses) via f-strings appears in 5+ services. A query builder abstraction would reduce this risk.

2. **Shared mutable state in asyncio.gather closures**: At least 3 services (gas_rate, weather, notification_dispatcher) use the pattern of mutating a shared dict from concurrent coroutines. The codebase already has a correct example in `community_service.py` that should be the standard.

3. **Module-level global API key assignment**: Both `resend.api_key` and `stripe.api_key` are set as module-level globals. Modern Python SDK patterns favor instance-based clients.

4. **Inconsistent logging framework**: ~4 services use stdlib `logging` while ~48 use `structlog`. This should be standardized.

---

## Files Reviewed (52 total)

| # | File | Lines | Findings |
|---|------|-------|----------|
| 1 | `__init__.py` | 12 | None |
| 2 | `ab_test_service.py` | ~180 | None |
| 3 | `affiliate_service.py` | ~120 | None |
| 4 | `agent_service.py` | 415 | P0-02, P0-03, P0-04, P3-08 |
| 5 | `alert_renderer.py` | ~150 | None |
| 6 | `alert_service.py` | ~959 | None |
| 7 | `analytics_service.py` | 357 | P2-10 |
| 8 | `bill_parser.py` | ~500 | None |
| 9 | `cca_service.py` | ~100 | None |
| 10 | `community_service.py` | 606 | P1-08, P3-10 |
| 11 | `community_solar_service.py` | ~200 | None |
| 12 | `connection_analytics_service.py` | ~250 | None |
| 13 | `connection_sync_service.py` | ~300 | None |
| 14 | `data_persistence_helper.py` | 57 | P2-06 |
| 15 | `data_quality_service.py` | ~250 | None |
| 16 | `dunning_service.py` | 426 | P2-07 |
| 17 | `email_oauth_service.py` | ~250 | None |
| 18 | `email_scanner_service.py` | ~400 | P3-13 |
| 19 | `email_service.py` | 149 | P0-01 |
| 20 | `feature_flag_service.py` | 127 | P3-02, P3-03 |
| 21 | `forecast_service.py` | ~300 | P0-05 |
| 22 | `gas_rate_service.py` | ~180 | P1-01 |
| 23 | `geocoding_service.py` | ~200 | None |
| 24 | `heating_oil_service.py` | ~180 | None |
| 25 | `hnsw_vector_store.py` | 365 | P1-03, P3-12 |
| 26 | `kpi_report_service.py` | ~250 | None |
| 27 | `learning_service.py` | ~350 | P3-14 |
| 28 | `maintenance_service.py` | 161 | P2-11 |
| 29 | `market_intelligence_service.py` | ~150 | P3-09 |
| 30 | `model_version_service.py` | ~300 | None |
| 31 | `neighborhood_service.py` | ~200 | None |
| 32 | `notification_dispatcher.py` | 500 | P1-04 |
| 33 | `notification_service.py` | 114 | P2-02, P3-01 |
| 34 | `observation_service.py` | ~200 | P2-05 |
| 35 | `optimization_report_service.py` | ~300 | None |
| 36 | `portal_scraper_service.py` | 542 | P1-05 |
| 37 | `price_service.py` | 509 | P2-03, P2-04 |
| 38 | `price_sync_service.py` | ~200 | P3-11 |
| 39 | `propane_service.py` | ~180 | None |
| 40 | `push_notification_service.py` | ~120 | None |
| 41 | `rate_change_detector.py` | ~300 | None |
| 42 | `rate_export_service.py` | 216 | P1-07, P3-04 |
| 43 | `rate_scraper_service.py` | 213 | None |
| 44 | `recommendation_service.py` | 388 | P3-05 |
| 45 | `referral_service.py` | 166 | P2-09 |
| 46 | `savings_aggregator.py` | 99 | P2-01 (related) |
| 47 | `savings_service.py` | 303 | P2-01, P3-06 |
| 48 | `stripe_service.py` | 607 | P1-06 |
| 49 | `utility_discovery_service.py` | 130 | None |
| 50 | `vector_store.py` | 337 | P1-03, P2-08 |
| 51 | `water_rate_service.py` | 331 | P3-07 |
| 52 | `weather_service.py` | 168 | P1-02 |

---

## Summary Statistics

| Severity | Count | Description |
|----------|-------|-------------|
| P0 | 5 | Critical: concurrency bugs, info leak, SQL injection risk |
| P1 | 8 | High: race conditions, SSRF bypass, blocking I/O, fail-open |
| P2 | 12 | Medium: dead code, inconsistencies, non-atomic operations |
| P3 | 14 | Low: type annotations, naming, dead code, minor patterns |
| **Total** | **39** | |

**Files with no findings: 24 out of 52 (46%)**
**Files with findings: 28 out of 52 (54%)**
