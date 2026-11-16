# Audit Report: Bug Patterns
**Date:** 2026-03-19
**Scope:** Race conditions, null handling, error swallowing, resource leaks, edge cases
**Files Reviewed:**
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/notification_dispatcher.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/agent_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/alert_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/community_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/email_scanner_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/portal_scraper_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/gas_rate_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/learning_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/bill_parser.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/data_quality_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/referral_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/analytics_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/connection_sync_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/hnsw_vector_store.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/price_sync_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/email_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/recommendation_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/price_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/data_persistence_helper.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/ab_test_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/model_version_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/geocoding_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/weather_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/integrations/pricing_apis/service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/integrations/pricing_apis/iea.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/integrations/pricing_apis/cache.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/integrations/pricing_apis/base.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/prices.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/suppliers.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/rates.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/hooks/useAuth.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/hooks/useRealtime.ts`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/api/client.ts`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/api/agent.ts`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/DirectLoginForm.tsx`

***

## P0 -- Critical (Fix Immediately)

### 1. Race condition: shared mutable dict mutated from concurrent coroutines in `gas_rate_service.py`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/gas_rate_service.py`
**Lines:** 60, 81-82, 96, 106

The `results` dict is defined once (line 60) and then mutated from multiple concurrent coroutines launched via `asyncio.gather` (line 116). Each coroutine increments `results["fetched"]`, `results["stored"]`, `results["errors"]`, and appends to `results["details"]` without any synchronization.

```python
results = {"fetched": 0, "stored": 0, "errors": 0, "details": []}  # line 60

async def fetch_state(state_code: str):
    async with semaphore:
        ...
        results["fetched"] += 1   # line 81 -- unsynchronized
        results["stored"] += 1    # line 82 -- unsynchronized
        results["details"].append(...)  # line 83
```

While CPython's GIL protects against data corruption for simple operations, `+=` on an integer is NOT atomic at the Python level (`LOAD_FAST`, `BINARY_ADD`, `STORE_FAST`) and can lose increments if an `await` yield point occurs between the load and store. In practice, the `await self._price_repo.create(price)` on line 80 IS a yield point immediately before the mutation, making interleaving plausible.

**Risk:** Under-counted `fetched`/`stored`/`errors` values in the sync summary, leading to misleading operational metrics.

**Fix:** Use an `asyncio.Lock` to protect the counter updates, or accumulate results per-coroutine and merge after `gather` completes.

---

### 2. Race condition: identical pattern in `weather_service.py` with shared `results` dict

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/weather_service.py`
**Lines:** 152, 162, 166

Same pattern as gas_rate_service: a shared `results` dict is mutated from concurrent `asyncio.gather` coroutines.

```python
results: dict[str, dict] = {}  # line 152

async def _fetch_one(region: str) -> None:
    ...
    results[region] = weather  # line 162 -- unsynchronized dict assignment

await asyncio.gather(*[_fetch_one(r) for r in regions])  # line 166
```

Dictionary key assignment is safer than `+=` but concurrent dict resizing during insertion can cause `RuntimeError` in CPython. This is unlikely with few regions but is architecturally fragile.

**Fix:** Have each coroutine return a `(region, weather)` tuple and collect results from `gather`'s return value.

---

### 3. `asyncio.gather` with `return_exceptions=True` used as a keyword argument to a non-keyword parameter

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/notification_dispatcher.py`
**Line:** 254

```python
await asyncio.gather(_dispatch_push(), _dispatch_email(), return_exceptions=True)
```

When `return_exceptions=True`, exceptions from `_dispatch_push()` or `_dispatch_email()` are returned as values in the result tuple rather than being raised. However, the return value of `gather` is never captured or inspected. This means:

1. If `_dispatch_push()` raises, the exception is silently swallowed -- it will not appear in logs because the `except` blocks inside those closures already catch and log. But if an exception occurs AFTER the `except` blocks (e.g., in `_persist_channel_outcome`), it will be silently eaten.
2. The `results` dict mutations inside the closures (`results[NotificationChannel.PUSH.value] = success` on line 219) happen by side-effect, and if an exception short-circuits the closure, the key is never set -- causing downstream logic to silently skip reporting on that channel.

**Risk:** Silent notification delivery failures with no audit trail. A push or email notification could fail after the logging but before the `results` dict write, and the caller would never know.

**Fix:** Either capture the return value and check for exceptions, or remove `return_exceptions=True` so that exceptions propagate naturally (the internal try/except blocks already handle expected errors).

---

### 4. Fire-and-forget `asyncio.create_task` for async agent jobs with no exception handling

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/agent_service.py`
**Line:** 317

```python
asyncio.create_task(self._run_async_job(job_id, user_id, prompt, context, redis))
```

This creates a background task but never stores the returned `Task` object. If the task raises an unhandled exception:
- Python 3.12 emits a warning to stderr but does not propagate the error
- The task reference is garbage collected, triggering `Task exception was never retrieved`
- If Redis is `None` (line 301-307 shows this is possible), the failure writes to Redis fail silently, and the job status remains permanently stuck as `"processing"`

The `_run_async_job` method (line 320) does have a top-level try/except, but if `redis` is `None`, the job result is never written anywhere, leaving the client polling forever on a job that will never complete.

**Risk:** Jobs that appear to be "processing" indefinitely when Redis is unavailable, with no timeout or cleanup mechanism.

**Fix:** (a) Store the task and add a done-callback for error logging, (b) check `redis is None` before creating the task and return an immediate error, (c) add a TTL or timeout mechanism so clients do not poll forever.

---

## P1 -- High (Fix This Sprint)

### 5. Community moderation inconsistency: `moderate_post()` clears pending on dual-provider failure (fail-open)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/community_service.py`
**Lines:** 397-400

The `moderate_post()` method (line 367) and `_run_moderation()` (line 116) have different failure semantics:

- `_run_moderation()` (called from `create_post`, line 101): On exception, re-raises, which is caught on line 104 and the post is left in `is_pending_moderation=true` (fail-closed). This is correct.
- `moderate_post()` (line 367, used for retroactive moderation): On dual-provider failure, calls `_clear_pending_moderation()` (line 399), which sets `is_pending_moderation=false` -- making the post VISIBLE even though it was never classified. This is fail-OPEN.

```python
except Exception:
    # Both failed -- clear pending moderation
    await self._clear_pending_moderation(db, post_id)  # line 399 -- FAIL OPEN
    return
```

**Risk:** Unmoderated content becomes visible to all users when both AI providers are down simultaneously. This contradicts the documented fail-closed design in the module docstring (line 4).

**Fix:** On dual-provider failure in `moderate_post()`, leave `is_pending_moderation=true` instead of clearing it. Or log a warning and schedule a retry, matching the `_run_moderation()` behavior.

---

### 6. Agent rate limit check-then-act gap between `check_rate_limit` and `increment_usage`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/agent_service.py`
**Lines:** 110-138, 140-153, 253-254

The code comments claim the rate limiting is TOCTOU-safe (line 113), and the `check_rate_limit` method does use an atomic upsert. However, the rate check (line 110) and the usage increment (line 140, called on line 254) are separated by the entire LLM query execution (lines 207-233), which can take 2-120 seconds.

The upsert in `check_rate_limit()` does NOT increment the counter -- it just reads the current count atomically:

```python
# check_rate_limit: reads count, does NOT increment
ON CONFLICT (user_id, date) DO UPDATE
    SET query_count = agent_usage_daily.query_count  # no-op, just reads
RETURNING query_count
```

```python
# increment_usage: increments AFTER the query completes
ON CONFLICT (user_id, date)
DO UPDATE SET query_count = agent_usage_daily.query_count + 1
```

Between the check and the increment, a second concurrent request can also pass the rate limit check. For free-tier users with a 3/day limit, two simultaneous requests could both see count=2 and both proceed, resulting in 4 uses instead of 3.

**Risk:** Rate limit bypass under concurrent requests, particularly impactful for free-tier users (small limit = easy to exceed).

**Fix:** Atomically increment the counter in `check_rate_limit` itself and roll back or decrement if the query fails. Or use `SELECT ... FOR UPDATE` with the increment in a single transaction.

---

### 7. SSRF allowlist is log-only, not enforced for non-allowlisted domains

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/portal_scraper_service.py`
**Lines:** 92-98

The SSRF protection validates the URL but only LOGS when the hostname is not in the allowlist -- it does not block the request:

```python
if hostname and not any(hostname == d or hostname.endswith(f".{d}") for d in _ALLOWED_DOMAINS):
    logger.warning(
        "portal_url_not_in_allowlist",
        hostname=hostname,
        url=url,
    )
    # Allow but log -- generic scraping is a documented feature  # line 98
```

While the code blocks private IPs and non-HTTPS, an attacker could supply a public DNS name that resolves to an internal IP after the validation check (DNS rebinding attack). The `httpx` client follows redirects (`follow_redirects=True`, line 255), so a redirect from a public host to an internal host would bypass the validation.

**Risk:** SSRF via DNS rebinding or open redirect chains, allowing access to internal services. The portal scraper runs with the server's network context.

**Fix:** Either enforce the allowlist (reject unknown domains), disable redirect following, or re-validate the IP of the final resolved host before reading the response body.

---

### 8. `httpx.AsyncClient` created per-call without cleanup in geocoding service

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/geocoding_service.py`
**Lines:** 163, 192

Both `_geocode_owm()` and `_geocode_nominatim()` create a new `httpx.AsyncClient` per invocation using `async with`:

```python
async with httpx.AsyncClient(timeout=10.0) as client:  # line 163
    resp = await client.get(...)
```

While the `async with` block properly closes the client, creating a new TLS session for every geocoding call is expensive. When called in a loop (e.g., batch geocoding), this creates significant overhead from repeated TCP handshakes and TLS negotiations.

This is not a leak per se (the context manager handles cleanup), but it is a resource inefficiency that could cause connection exhaustion under load.

**Risk:** High latency and potential connection pool exhaustion during batch operations.

**Fix:** Share a single `httpx.AsyncClient` instance across calls (inject at construction or use a class-level client with `close()` on service shutdown).

---

### 9. `notification_dispatcher._send_in_app` commits inside the channel handler, breaking transactional boundaries

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/notification_dispatcher.py`
**Line:** 326

The `_send_in_app()` method calls `await self._db.commit()` on line 326 after inserting the notification row. This commits any pending work on the shared `AsyncSession` -- not just the notification INSERT.

If the caller of `dispatcher.send()` has other pending database changes on the same session that have not yet been committed, the `_send_in_app()` commit will flush those changes prematurely. This breaks the caller's transactional boundary.

For example, the `check-alerts` endpoint creates alert_history records and sends notifications in the same request scope. If an alert_history INSERT is pending on the session when `dispatcher.send()` is called, `_send_in_app()` will commit the alert_history record even if the caller intended to roll it back on failure.

**Risk:** Premature commits of unrelated pending changes on the shared session, preventing proper rollback on error.

**Fix:** Use `db.flush()` instead of `db.commit()` so the row is visible within the transaction but the commit decision stays with the caller. Or use a separate session for the notification insert.

---

### 10. Error detail leakage in portal scraper error messages

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/portal_scraper_service.py`
**Lines:** 339, 411

Exception details are interpolated directly into user-facing error strings:

```python
return {
    ...
    "error": f"Unexpected error during portal scrape: {exc}",  # line 339
}
```

```python
return {
    ...
    "error": f"HTTP error during portal scrape: {exc}",  # line 411
}
```

If `exc` contains internal details (stack frames, internal hostnames, file paths), these are returned to the API caller. The portal scraper runs with credentials and accesses internal infrastructure, so exception messages could reveal sensitive information.

**Risk:** Information leakage of internal infrastructure details to API consumers.

**Fix:** Return a generic error message and log the full exception details server-side.

---

## P2 -- Medium (Fix Soon)

### 11. `analytics_service._acquire_cache_lock` fail-closed blocks ALL requests when Redis is down

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/analytics_service.py`
**Lines:** 46-63

The cache stampede lock returns `False` on Redis failure (line 63), which means no caller can proceed to compute the value when Redis is unavailable:

```python
except Exception:
    # Fail-closed: treat Redis failure as "lock already held"
    return False
```

The callers (lines 137-145, 219-229, 310-318) re-check the cache after the lock fails, but since Redis is down, the cache check also returns `None`. The code then falls through to the computation step without ever acquiring the lock -- but only if the second `_get_cached` call returns `None`.

Actually, on closer inspection, the code falls through to the computation after the re-check. However, there is a logic gap: when `_acquire_cache_lock` returns `False` AND the second `_get_cached` also fails (because Redis is entirely down), the code continues WITHOUT the lock. This means the "fail-closed" comment is misleading -- under total Redis failure, ALL concurrent requests proceed to hit the database simultaneously, which is the exact stampede the lock was supposed to prevent.

**Risk:** Database stampede when Redis is completely unavailable, the opposite of the documented fail-closed behavior.

**Fix:** Track whether `_get_cached` also failed due to Redis being down, and in that case, allow exactly one request through using an in-memory fallback lock.

---

### 12. `data_persistence_helper.persist_batch` commits once after all inserts, losing partial progress

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/data_persistence_helper.py`
**Lines:** 42-56

Individual insert failures are caught and skipped (line 46), but the commit only happens after all rows are processed (line 54):

```python
for row in rows:
    try:
        await db.execute(insert_stmt, row)
        persisted += 1
    except Exception as e:
        ...  # logs warning, continues
if persisted:
    await db.commit()
```

If an `execute()` call fails with an integrity error, the SQLAlchemy session may be in an invalidated state. Subsequent `execute()` calls in the loop could raise `sqlalchemy.exc.PendingRollbackError` because the session requires a rollback after an error. This would cause all remaining rows in the batch to fail.

**Risk:** A single bad row causes all subsequent rows in the batch to fail due to the session needing a rollback.

**Fix:** Call `await db.rollback()` in the except block before continuing to the next row, or use SAVEPOINTs for per-row isolation.

---

### 13. `referral_service.generate_code` catches bare `Exception` for collision handling

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/referral_service.py`
**Lines:** 55-58

```python
except Exception:
    await self._db.rollback()
    if attempt == _MAX_RETRIES - 1:
        raise ReferralError("Failed to generate unique referral code")
```

The exception handler catches ALL exceptions, not just `IntegrityError` (unique constraint violation). A database connection error, timeout, or programming error would be retried 5 times before raising a generic `ReferralError`, masking the real root cause.

**Risk:** Transient database errors are masked and retried unnecessarily; the raised `ReferralError` does not convey the actual failure reason.

**Fix:** Catch `sqlalchemy.exc.IntegrityError` specifically for collision retries; let other exceptions propagate immediately.

---

### 14. `email_scanner_service.download_gmail_attachments` creates `httpx.AsyncClient` without cleanup on some paths

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/email_scanner_service.py`
**Lines:** 340-361

The Gmail attachment download uses an injected `client` parameter but the `except Exception` on line 359 silently swallows download failures without logging any details:

```python
except Exception:
    # Skip attachments that fail to download
    continue
```

There is no logging at all -- not even a warning. If an auth token expires mid-download, all subsequent attachments silently fail and the caller has no visibility into the failure.

**Risk:** Silent data loss -- all attachment-based rate extraction fails without any diagnostic information.

**Fix:** Add a `logger.warning()` with the filename and error message in the except block.

---

### 15. `community_service.moderate_post` can leave `classification = None` and auto-clear moderation

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/community_service.py`
**Lines:** 384, 392-400, 402

If the Groq call succeeds but returns `None` (not `"flagged"` and not a truthy classification), AND the Gemini fallback block is never entered (because no exception was raised), then `classification` remains `None`.

When `classification` is `None`, the check on line 402 (`if classification == "flagged"`) is `False`, so the post is cleared from pending moderation (line 414) without ever being properly classified. A malfunctioning AI provider that returns `None` or an empty string would cause all posts to pass moderation.

**Risk:** Unmoderated posts become visible if the AI provider returns a non-"flagged" falsy value.

**Fix:** Explicitly validate that `classification` is one of the expected values ("safe", "flagged") before acting on it. Treat unexpected/None values as a classification failure.

---

### 16. `price_sync_service.sync_prices` unreachable dead code for session check

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/price_sync_service.py`
**Lines:** 104-109

```python
if prices_to_store and not session:
    logger.error(...)
    errors.append("Database session unavailable -- prices not persisted")
```

The `session` parameter is `AsyncSession` (required by SQLAlchemy type). This check is unreachable in normal operation because the function signature requires a session. If the caller passes `None`, the type checker should catch this.

However, there is a more subtle issue: the `pricing_service.compare_prices()` call on line 78 uses `asyncio.gather` internally (in `pricing_apis/service.py` line 354) with `return_exceptions=True`, meaning API failures are returned as values, not raised. The outer `except` blocks (lines 115-123) only catch exceptions from the context manager (`async with pricing_service`), not from individual region failures. Failed regions are silently dropped from the `comparison` dict.

**Risk:** No explicit reporting of which regions failed during price sync when individual region API calls fail.

---

## P3 -- Low / Housekeeping

### 17. `agent_service._composio_toolset` uses `False` as a sentinel (not `None`)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/agent_service.py`
**Lines:** 105-108

```python
self._composio_toolset = False  # sentinel: don't retry
...
return self._composio_toolset if self._composio_toolset is not False else None
```

Using `False` as a sentinel alongside `None` is fragile and confusing. A future developer might check `if not self._composio_toolset` expecting it to be `None`, which would also match `False` and cause subtle logic errors.

**Fix:** Use a dedicated sentinel object: `_NOT_CONFIGURED = object()`.

---

### 18. `learning_service` uses `logging` module while most other services use `structlog`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/learning_service.py`
**Line:** 34

```python
logger = logging.getLogger(__name__)
```

All other services in the codebase use `structlog.get_logger(__name__)`. The stdlib `logging` module does not support keyword arguments the way structlog does, and the format strings in this file use `%s` interpolation (e.g., line 120, 165) while the rest of the codebase uses structured key-value logging. This creates inconsistent log output and makes centralized log parsing harder.

**Fix:** Replace `import logging` with `import structlog` and update all `logger.*()` calls to use structlog's keyword-argument style.

---

### 19. `useAuth.tsx` calls `updateUserProfile` in a fire-and-forget `.catch(() => {})`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/hooks/useAuth.tsx`
**Line:** 235

```typescript
updateUserProfile({ onboarding_completed: true }).catch(() => {})
```

If this API call fails (network error, 500, 401), the user's `onboarding_completed` flag is never set. The user will see the onboarding flow on their next visit, which may be confusing if they already completed it. The empty `.catch()` provides no error visibility.

**Risk:** Users may see repeated onboarding prompts if the profile update silently fails.

**Fix:** Add at minimum a `console.warn()` in the catch block for visibility. Consider adding retry logic or queuing the update for later.

---

### 20. `queryAgent` in `agent.ts` does not use `apiClient` and bypasses circuit breaker / retry logic

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/api/agent.ts`
**Lines:** 55-59

```typescript
const response = await fetch(`${API_URL}/agent/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ prompt, context }),
    signal,
})
```

This uses raw `fetch()` instead of `apiClient.post()`, bypassing the circuit breaker, retry logic, and fallback URL handling that all other API calls benefit from. The 401 handling on lines 65-69 is a manual reimplementation that does not include the redirect-loop protection (sessionStorage counter) that the apiClient has.

**Risk:** Agent queries do not benefit from CF Worker fallback or retry logic, and the 401 handling is inconsistent with the rest of the app (no loop protection).

**Fix:** For SSE endpoints where `apiClient` does not apply (streaming response), extract the 401 handling into a shared utility function used by both `apiClient` and `queryAgent`. Consider using `fetchEventSource` for the SSE part (as `useRealtime.ts` does).

---

### 21. `geocoding_service._geocode_nominatim` assumes ISO3166-2-lvl4 key exists

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/geocoding_service.py`
**Lines:** 214-218

```python
iso_code = addr.get("ISO3166-2-lvl4", "")
if iso_code and "-" in iso_code:
    candidate = iso_code.split("-", 1)[1]
    if candidate in _US_STATES:
        state_abbr = candidate
```

This is defensive enough for missing keys, but Nominatim sometimes returns ISO3166-2-lvl4 with multiple levels (e.g., `"US-CA-06"` in some regions). The `split("-", 1)` with `maxsplit=1` would produce `"CA-06"`, which would not be in `_US_STATES`. This is a minor edge case that could cause geocoding to return `None` for the state when the data is actually available.

**Fix:** Use `iso_code.split("-")[1]` (without maxsplit limit and take index 1) or validate the candidate length.

---

### 22. `portal_scraper_service._extract_hidden_fields` regex pattern order sensitivity

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/portal_scraper_service.py`
**Lines:** 482-496

The regex for extracting hidden form fields expects `type="hidden"` BEFORE `name` and `value` attributes. But HTML attributes can appear in any order. The `pattern_alt` handles `value` before `name`, but neither pattern handles `name` or `value` appearing before `type="hidden"`. An input like:

```html
<input name="csrf_token" type="hidden" value="abc123">
```

would not be matched by either pattern. Most modern HTML generators put `type` first, but this is not guaranteed.

**Risk:** CSRF tokens or other hidden fields may not be captured, causing login POST failures on some utility portals.

**Fix:** Use a more flexible regex or an HTML parser (e.g., `re.findall` with separate attribute extraction, or `html.parser`/`lxml`).

---

### 23. `bill_parser.extract_rate_per_kwh` sanity check range may be too narrow

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/bill_parser.py`
**Lines:** 327-328

```python
if 0.05 <= value <= 0.80:
    confidence = 1.0 if i == 0 else (0.8 if i == 1 else 0.6)
    return round(value, 6), confidence
```

The sanity check rejects rates below $0.05/kWh or above $0.80/kWh. While reasonable for most US residential rates, some utility plans (especially time-of-use plans during off-peak hours, or industrial rates) can legitimately be below $0.03/kWh. Hawaii and some island territories can exceed $0.40/kWh but would pass; rates in some international contexts could exceed $0.80/kWh.

**Risk:** Legitimate rate extractions from bills with very low off-peak rates or very high international rates are silently rejected, returning `(None, 0.0)`.

**Fix:** Widen the range to `0.01 <= value <= 1.50` or make the bounds configurable per-region.

---

### 24. `analytics_service` cache deserialization converts string keys to int but does not handle parse errors

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/analytics_service.py`
**Lines:** 212-216

```python
cached["average_by_hour"] = {
    int(k): Decimal(v) for k, v in cached["average_by_hour"].items()
}
```

If the cached JSON has been corrupted (truncated write, Redis memory pressure), `int(k)` or `Decimal(v)` could raise `ValueError` or `InvalidOperation`. This exception would propagate uncaught and return a 500 to the caller, even though the data could be recomputed.

**Risk:** Corrupted cache entries cause 500 errors instead of graceful fallback to recomputation.

**Fix:** Wrap the deserialization in a try/except that deletes the corrupted cache key and falls through to recomputation.

---

### 25. `useRealtimeSubscription` polling interval is hardcoded to 30 seconds

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/hooks/useRealtime.ts`
**Line:** 193

```typescript
const timer = setInterval(() => {
    setLastUpdate(new Date())
    onUpdateRef.current?.({ table: config.table, event: config.event })
}, 30_000)
```

The generic `useRealtimeSubscription` hook has a hardcoded 30-second interval with no way for callers to customize it. Unlike `useRealtimePrices` which accepts an `interval` parameter, this hook does not. Consumers needing faster or slower polling must re-implement the hook.

**Fix:** Add an `interval` parameter with a default of 30000ms.

---

***

## Files With No Issues Found

- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/email_service.py` -- Clean dual-provider pattern with proper error handling and fallback.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/rates.py` -- Properly avoids `asyncio.gather` on shared session, includes ownership checks and EXISTS fallback.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/prices.py` -- Good defensive clamping of pagination parameters, proper fallback path.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py` -- Atomic Lua script approach is sound; concurrent gather for minute+hour windows is safe (separate Redis keys).
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/model_version_service.py` -- Proper rollback on error, correct promote/demote logic.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/ab_test_service.py` -- Good use of ON CONFLICT DO NOTHING, proper rollback handling.
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/api/client.ts` -- Robust 401 handling with redirect-loop protection, circuit breaker integration, proper retry logic.
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/hooks/useRealtime.ts` (useRealtimePrices) -- Good SSE lifecycle management, exponential backoff, auth failure detection, visibility API integration.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/integrations/pricing_apis/base.py` -- Request deduplication with async lock is well-implemented.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/connection_sync_service.py` -- Thorough error handling at each step with proper status persistence.

***

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| P0 - Critical | 4 | Shared mutable state in concurrent asyncio.gather coroutines (2 instances), silent exception swallowing in asyncio.gather with return_exceptions=True, fire-and-forget task with no job completion guarantee |
| P1 - High | 6 | Fail-open moderation on dual-provider failure, TOCTOU gap in agent rate limiting, SSRF allowlist not enforced, premature session commit breaking transactional boundaries, error detail leakage, httpx client-per-call inefficiency |
| P2 - Medium | 6 | Cache stampede on Redis failure, batch insert session invalidation, bare Exception masking in referral service, silent attachment download failures, None classification auto-clearing moderation, unreachable dead code |
| P3 - Low | 9 | False sentinel anti-pattern, stdlib vs structlog inconsistency, fire-and-forget profile updates, circuit breaker bypass in agent API, regex order sensitivity, rate sanity bounds too narrow, cache deserialization fragility, hardcoded poll interval, Nominatim ISO code edge case |

**Total findings: 25** across 36 files reviewed.

The most systemic pattern is **shared mutable state in asyncio.gather closures** (P0-1, P0-2), which appears in at least 2 services and represents a class of bug that could exist in other concurrent code paths. The second most impactful pattern is **broad Exception catching** that masks root causes and can leave systems in inconsistent states (P1-5, P2-13, P2-14, P2-15).

The codebase generally demonstrates strong defensive patterns: proper pagination clamping, ownership verification on CRUD operations, SSRF protection (despite the enforcement gap), and well-structured error handling in most services. The `asyncio.gather` + shared session anti-pattern is documented and avoided where noted (connections/rates.py line 87), indicating awareness of the issue -- it just was not applied universally.
