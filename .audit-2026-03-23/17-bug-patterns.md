# Bug Pattern Audit — RateShift
**Date**: 2026-03-23
**Scope**: READ-ONLY audit — no source files modified
**Primary focus**: `backend/services/`, `backend/api/`, `frontend/lib/`
**Auditor**: Claude (claude-sonnet-4-6)

---

## Executive Summary

This audit systematically reviewed the RateShift codebase for common bug patterns across five
categories: race conditions, null/undefined handling, error swallowing, resource leaks, and type
coercion issues. A total of **21 findings** were identified across backend services, API endpoints,
and frontend hooks.

The most severe issues (P0) involve an `IndexError` crash path in the Groq response handler and a
cache stampede gap that silently returns empty data to callers under load. P1 issues center on
unlogged Gemini-to-Groq fallback (errors invisible in monitoring), a potential `TypeError` in alert
window calculation, and silent data corruption during OAuth token round-trips.

No findings require immediate production incident response, but the P0 items should be addressed
in the next sprint.

---

## P0 — Crash / Data Corruption Risk

### P0-1: `IndexError` on empty Groq `choices` list
**File**: `backend/services/agent_service.py`, line 305
**Category**: Null/undefined — missing bounds check

```python
# agent_service.py line 290-305
async def _query_groq(self, system: str, prompt: str) -> str:
    ...
    response = await asyncio.wait_for(
        client.chat.completions.create(...),
        timeout=QUERY_TIMEOUT_SECONDS,
    )
    return response.choices[0].message.content   # <-- no bounds check
```

**Risk**: If Groq returns a valid HTTP 200 response but with an empty `choices` list (which the
Groq API can do under content filtering or safety refusal), `response.choices[0]` raises
`IndexError`. This propagates up to `_run_async_job` as an unhandled inner exception. The outer
`except Exception` on line 365 catches it and stores `status: failed` in Redis — so the user
receives an unexplained job failure with no actionable error message.

**Fix**: Guard the access before returning.

```python
if not response.choices:
    raise ValueError("Groq returned empty choices list (content filtered?)")
return response.choices[0].message.content
```

---

### P0-2: Cache stampede gap — callers silently receive `None` / empty dict
**File**: `backend/services/analytics_service.py`, lines 137–145
**Category**: Race condition / error handling — silent fallback gap

```python
# analytics_service.py — get_price_trend (and peak_hours, supplier_comparison follow same pattern)
if not await self._acquire_cache_lock(cache_key):
    # Cache lock held by another request; re-check cache
    cached = await self._get_cached(cache_key)
    if cached:
        return cached
    # *** Falls through here with no return — caller receives None ***
```

**Risk**: `_acquire_cache_lock` returns `False` in two cases: (a) the lock is legitimately held
by another coroutine that is computing the result, and (b) Redis is unavailable (fail-closed).
In case (a) the re-check of cache may find nothing if the computing coroutine has not yet written
the result. In case (b) Redis is down so `_get_cached` also returns `None`. In both situations
the function falls through without returning, so Python implicitly returns `None`. Callers that do
`result["direction"]` on the returned value will raise `TypeError: 'NoneType' object is not
subscriptable`.

The same pattern is repeated in `get_peak_hours_analysis` (line 219-229) and
`get_supplier_comparison_analytics` (line 310-319).

**Fix**: After the re-check, fall through to the expensive computation rather than returning
implicitly, or at minimum return a safe default:

```python
if not await self._acquire_cache_lock(cache_key):
    cached = await self._get_cached(cache_key)
    if cached:
        # restore Decimal types
        return cached
    # Do NOT return None — fall through to compute below
    # (lock contention is transient; a second computation is cheaper than
    #  serving corrupt empty data to the caller)
```

---

## P1 — Silent Failures / Logic Errors

### P1-1: Gemini fallback swallows error with no logging
**File**: `backend/services/agent_service.py`, lines 345–350
**Category**: Error swallowing

```python
# agent_service.py line 345-350 (_run_async_job)
try:
    result = await self._query_gemini(system, prompt)
    model_used = "gemini-3-flash-preview"
except Exception:           # <-- no logger.warning / logger.error here
    result = await self._query_groq(system, prompt)
    model_used = "llama-3.3-70b-versatile"
```

**Risk**: Every Gemini failure — timeout, quota exceeded, bad API key, network error — is silently
swallowed before the Groq fallback is attempted. Monitoring (OTel/Grafana) will show only the
final model used (`llama-3.3-70b-versatile`) with no record that Gemini failed. If Gemini's API
key expires or quota is permanently exhausted, operations will have no alertable signal. The same
pattern appears in the streaming query path.

The same pattern also appears at line 348 in `_run_async_job`.

**Fix**: Log the error before falling back.

```python
except Exception as gemini_err:
    logger.warning("gemini_query_failed_falling_back", error=str(gemini_err))
    result = await self._query_groq(system, prompt)
    model_used = "llama-3.3-70b-versatile"
```

---

### P1-2: `TypeError` when alert window `timestamp` attribute is `None`
**File**: `backend/services/alert_service.py`, line 229
**Category**: Null handling — `getattr` fallback masks None value

```python
# alert_service.py line 229 (approximate)
window_end = getattr(window_end_price, "timestamp", datetime.now(UTC)) + timedelta(hours=1)
```

**Risk**: `getattr(obj, attr, default)` returns the default only when the attribute does **not
exist** on the object. If `window_end_price.timestamp` is `None` (the attribute exists but is
explicitly `None`, which is possible for freshly constructed `Price` objects), `getattr` returns
`None` and the subsequent `+ timedelta(hours=1)` raises `TypeError: unsupported operand type(s)
for +: 'NoneType' and 'datetime.timedelta'`.

**Fix**: Use an explicit `None` check.

```python
ts = getattr(window_end_price, "timestamp", None)
window_end = (ts if ts is not None else datetime.now(UTC)) + timedelta(hours=1)
```

---

### P1-3: `PriceRegion` enum construction with no null/invalid guard
**File**: `backend/services/recommendation_service.py`, line 93
**Category**: Null handling — missing defensive check before enum construction

```python
# recommendation_service.py line 93
region = PriceRegion(user.region)
```

**Risk**: If `user.region` is `None` (new users who have not completed onboarding) or an invalid
string (legacy data before enum enforcement), this raises `ValueError` with no surrounding
try/except. The exception propagates up to the API layer and the caller receives a 500.

Additionally on line 134:
```python
peak_price = max(p.price_per_kwh for p in prices) if prices else best_window["avg_price"]
```
If `prices` is non-empty but every `p.price_per_kwh` is `None`, `max()` raises `TypeError`.

**Fix**:
```python
if not user.region:
    return []  # or raise appropriate HTTP 422 with guidance
try:
    region = PriceRegion(user.region)
except ValueError:
    logger.warning("recommendation_invalid_region", region=user.region, user_id=user.id)
    return []
```

---

### P1-4: OAuth token `encode("latin-1")` silently corrupts non-latin-1 bytes
**File**: `backend/services/connection_sync_service.py`, line 140
**Category**: Type coercion — lossy string-to-bytes conversion

```python
# connection_sync_service.py line 140 (approximate)
auth_uid_encrypted = auth_uid_encrypted.encode("latin-1")
```

**Risk**: The value being encoded is a previously stored encrypted token retrieved from the
database. If the database driver returns it as a Python `str` via an incorrect decoding step
earlier in the pipeline, re-encoding to `latin-1` will silently replace or raise on any byte value
outside `0x00–0xFF`. In practice, AES-GCM ciphertext routinely contains bytes `> 0x7F`; if any
of those were decoded as UTF-8 (which can represent them as multi-byte sequences) and then
re-encoded to `latin-1`, the resulting bytes will differ from the original ciphertext, causing
decryption to produce garbage or raise `InvalidTag`.

The correct fix is to read the raw bytes directly (the column type is BYTEA per migration 059)
without going through a string round-trip.

---

### P1-5: Shared `AsyncSession` reused across `asyncio.wait_for` boundary in `community_service`
**File**: `backend/services/community_service.py`, lines 92–113
**Category**: Race condition / resource lifecycle

```python
# community_service.py create_post (lines 92-113, approximate)
await db.commit()   # line 95 — commits the INSERT
...
await asyncio.wait_for(
    _run_moderation(db, post_id, ...),   # reuses same session
    timeout=_MODERATION_TIMEOUT,
)
```

**Risk**: The same `AsyncSession` is committed on line 95 to persist the post, then passed
immediately into `_run_moderation` which issues additional queries and commits on the same session.
SQLAlchemy's async sessions should not be shared across concurrent coroutines, and reusing a
committed session for follow-on writes is fragile. If `asyncio.wait_for` raises
`asyncio.TimeoutError` after `_run_moderation` has issued partial writes (e.g., the moderation
status INSERT has begun), the session is left in an undefined state — the timeout cancels the
coroutine but does not roll back the in-flight transaction.

---

### P1-6: `email_scanner_service` swallows attachment download and parse errors silently
**File**: `backend/services/email_scanner_service.py`, lines 359, 407, 487
**Category**: Error swallowing — bare `except Exception: continue`

```python
# email_scanner_service.py lines 359-361
except Exception:
    # Skip attachments that fail to download
    continue

# line 487-489
except Exception:
    # Never crash on a single attachment — log and move on
    extracted_results.append({"filename": filename})
```

**Risk**: Attachment download failures and parsing errors are never logged. If all attachment
downloads for a particular provider start failing (e.g., due to a Gmail API breaking change or
token scope issue), the scan will silently succeed with zero attachments processed, returning
`attachments_parsed=0` as if there were simply no attachments. Operations has no signal.

**Fix**: At minimum add `logger.warning("attachment_download_failed", email_id=..., error=str(exc))`
before `continue`.

---

## P2 — Degraded Behavior / Maintenance Risk

### P2-1: Background parse session not rolled back on error
**File**: `backend/api/v1/connections/bill_upload.py`, lines 71–85
**Category**: Resource leak — implicit state on error

```python
# bill_upload.py _run_background_parse
gen = _get_db()
db: AsyncSession = await gen.__anext__()
try:
    parser = BillParserService(db=db, uploads_dir=uploads_dir)
    await parser.parse(...)
finally:
    try:
        await gen.aclose()
    except Exception:
        pass
```

**Risk**: If `parser.parse()` raises after issuing partial SQL writes (e.g., updating
`bill_uploads` to `parse_status='parsing'` and then failing mid-extraction), there is no explicit
`await db.rollback()` before `gen.aclose()`. The `aclose()` call will trigger the generator's
finally block in `get_db_session`, which typically calls `rollback()` — but this depends on the
generator's implementation. If the generator's finally block only closes the session (without
rollback), partial state may be committed. More critically, there is no logging of the
exception before the outer `except Exception` on line 86 swallows it after logging
`background_parse_error`.

**Fix**: Add explicit rollback in the finally block.

```python
finally:
    try:
        await db.rollback()
    except Exception:
        pass
    try:
        await gen.aclose()
    except Exception:
        pass
```

---

### P2-2: Token refresh `except Exception` loses original error context
**File**: `backend/api/v1/connections/email_oauth.py`, line 331
**Category**: Error swallowing — original error not logged before 502

```python
# email_oauth.py trigger_email_scan — token refresh path
except Exception:
    raise HTTPException(status_code=502, detail="Token refresh failed")
```

**Risk**: Any exception during token refresh (network timeout, provider API change, decryption
failure, etc.) is converted to a generic 502 with no logging. When users report "Token refresh
failed", the on-call engineer has no structured log entry to trace the root cause.

**Fix**:
```python
except Exception as exc:
    logger.error("token_refresh_failed", connection_id=connection_id, error=str(exc))
    raise HTTPException(status_code=502, detail="Token refresh failed") from exc
```

---

### P2-3: `datetime.utcnow()` returns naive datetime mixed with aware context
**File**: `backend/services/observation_service.py`, line 129
**Category**: Type coercion — naive/aware datetime mixing

```python
# observation_service.py line 129
ts = datetime.utcnow()  # noqa: DTZ003  — naive datetime
```

**Risk**: `datetime.utcnow()` is deprecated in Python 3.12 and returns a naive datetime (no
timezone info). If this value is compared with or inserted alongside `datetime.now(UTC)` (aware
datetime), Python raises `TypeError: can't compare offset-naive and offset-aware datetimes`.
Additionally, the `# noqa: DTZ003` comment suppresses the ruff warning that would otherwise flag
this. The column type is likely `TIMESTAMPTZ` in Postgres, which will interpret a naive datetime
as local time (could be UTC-offset depending on DB session timezone).

Found also in `backend/integrations/pricing_apis/cache.py` line 70.

**Fix**: Replace with `datetime.now(UTC)`.

---

### P2-4: `Decimal("0")` falsy check incorrectly shows "N/A" for zero-value invoices
**File**: `backend/services/dunning_service.py`, line 194 (approximate)
**Category**: Type coercion — falsy check on Decimal

```python
# dunning_service.py
formatted = f"${amount:.2f}" if amount else "N/A"
```

**Risk**: `Decimal("0")` is falsy in Python. An invoice for $0.00 (legitimate edge case: trial
period charge, refund credit, etc.) would display as "N/A" in the dunning email rather than
"$0.00". This is a confusing UX defect in a billing-critical email.

**Fix**: Use an explicit `None` check.

```python
formatted = f"${amount:.2f}" if amount is not None else "N/A"
```

---

### P2-5: `_ml_result_to_forecast` `point` key access without bounds check
**File**: `backend/services/price_service.py`, lines 291–295
**Category**: Null handling — missing key existence check

```python
# price_service.py _ml_result_to_forecast
point = ml_result["point"]    # KeyError if not present
lower = ml_result.get("lower", point)
upper = ml_result.get("upper", point)

for i in range(min(hours, len(point))):
```

**Risk**: The ML result dict's `"point"` key is accessed with direct dict subscription, not
`.get()`. If the EnsemblePredictor returns a result without a `"point"` key (e.g., after a model
format change or deserialization error), this raises `KeyError` which propagates to the caller.
The `_try_ml_forecast` wrapper catches `Exception` and returns `None`, which would be correct — but
only if the error occurs inside `_try_ml_forecast`. The `_ml_result_to_forecast` call is made from
`get_price_forecast` **after** `_try_ml_forecast` returns successfully, so the `KeyError` is not
caught.

---

### P2-6: HNSW vector store performs synchronous SQLite I/O on the async event loop thread
**File**: `backend/services/hnsw_vector_store.py`, lines 264–270 and line 87
**Category**: Resource / performance — blocking I/O in async context

```python
# hnsw_vector_store.py search() lines 264-270
def _update_usage_count(self, item_id: str) -> None:
    conn = sqlite3.connect(self._store._db_path)
    ...
```

**Risk**: `sqlite3.connect()` and subsequent reads/writes are synchronous blocking calls. When
called from an `async def search()` method on the asyncio event loop, these calls block the entire
event loop for the duration of the SQLite I/O. Under load this can cause latency spikes across all
concurrent requests sharing the same event loop.

Also at line 87 in `_build_index`, `sqlite3.connect(self._store._db_path)` is called from within
`__init__`, which is invoked during module startup but could still block the event loop if
initialization happens asynchronously.

**Fix**: Wrap synchronous SQLite calls in `asyncio.to_thread()`.

---

### P2-7: Never-resolving promise accumulates in memory on 401
**File**: `frontend/lib/api/client.ts`, line 123 (approximate)
**Category**: Resource leak — promise never resolved or rejected

```python
# client.ts — 401 handler
return new Promise<T>(() => {})   // intentionally never resolves
```

**Risk**: This is intentional to prevent React Query retry cascades on 401 (documented in
CLAUDE.md patterns), but every 401 response creates a `Promise` object that is allocated and never
freed. In a long-running SPA session where a user's token expires and they navigate between pages
triggering multiple simultaneous queries (all 401), each query creates one leaked promise. The
accumulated count is bounded by the number of distinct query keys that fire before the redirect
completes, so in practice this is a small number — but the pattern is fragile if the redirect
timing changes.

---

### P2-8: `rate_scraper_service` uses `return_exceptions=False` with concurrent supplier tasks
**File**: `backend/services/rate_scraper_service.py`, line 189
**Category**: Error handling — single supplier failure aborts entire batch

```python
# rate_scraper_service.py line 189
raw_results: list[dict] = list(await asyncio.gather(*tasks, return_exceptions=False))
```

**Risk**: With `return_exceptions=False`, if any single supplier scrape task raises an uncaught
exception (despite the inner per-task `try/except`), `asyncio.gather` re-raises that exception
immediately, cancelling all remaining in-flight supplier tasks. The partial results are lost and
the entire batch is marked as failed.

The individual `_scrape_supplier` task functions have their own `except` blocks, but if an
unexpected error escapes those handlers (e.g., `asyncio.CancelledError`, which is not a subclass
of `Exception` in Python 3.8+ but is in earlier versions), the gather would abort.

**Fix**: Use `return_exceptions=True` and inspect results for `Exception` instances.

---

## P3 — Low Risk / Code Quality

### P3-1: `analytics_service.py` Redis errors fully silent — no visibility into connectivity issues
**File**: `backend/services/analytics_service.py`, lines 42–43, 75–76
**Category**: Error swallowing — acceptable but monitoring-blind

```python
except Exception:
    pass  # Redis get failure
...
except Exception:
    pass  # Redis set failure
```

**Risk**: Acceptable behavior for a cache (fail-open), but any Redis connectivity issue is
completely invisible in logs and metrics. A sustained Redis outage (even a degraded connection
causing timeouts) would look identical to normal cache-miss operation from a monitoring
perspective. Given that the rate limiter also depends on Redis, a silent Redis failure here could
mask a wider infrastructure problem.

**Fix**: At minimum log at `DEBUG` level or increment a Prometheus counter.

---

### P3-2: `agent_service.py` usage increment called after first yield, may be skipped
**File**: `backend/services/agent_service.py`, line 264 (approximate, streaming query path)
**Category**: Logic — usage not recorded if stream yields partially then aborts

```python
# agent_service.py streaming query path
async for chunk in response_stream:
    yield {"role": "assistant", "content": chunk, ...}

await self.increment_usage(user_id, db)   # called after all yields
```

**Risk**: If the client disconnects mid-stream (user closes browser tab, network drop), the
generator is garbage-collected or cancelled by FastAPI's SSE handler before the final
`increment_usage` await is reached. The query consumed Gemini API quota but is not counted against
the user's daily limit. For free-tier users (3/day limit), this allows slightly more queries than
intended.

---

### P3-3: `forecast_service.py` timestamp subtraction with mixed naive/aware types
**File**: `backend/services/forecast_service.py`, line 263
**Category**: Type coercion — potential runtime TypeError

```python
# forecast_service.py _extrapolate_trend line 263
days = [(t - base_time).total_seconds() / 86400 for t in timestamps]
```

**Risk**: If database rows contain a mix of timezone-aware and timezone-naive `datetime` objects
(which can happen if the column lacks consistent `TIMESTAMPTZ` enforcement), the subtraction
`t - base_time` raises `TypeError: can't subtract offset-naive and offset-aware datetimes`.
This would affect any region with partially migrated historical data.

---

### P3-4: `referral_service.py` bare `except Exception` before rollback may hide constraint violations
**File**: `backend/services/referral_service.py`, lines 55–57
**Category**: Error swallowing — retry loop masks constraint violations

```python
# referral_service.py
except Exception:
    await self._db.rollback()
    if attempt == _MAX_RETRIES - 1:
        raise
```

**Risk**: The `except Exception` catches `UniqueConstraintViolation`, `ForeignKeyViolation`, and
other database errors that are not retryable. These are retried up to `_MAX_RETRIES - 1` times
before finally re-raising. This wastes retry budget on non-retriable errors and introduces
unnecessary latency for users who trigger a constraint violation.

**Fix**: Catch `asyncpg.UniqueViolationError` / `asyncpg.ForeignKeyViolationError` separately and
re-raise immediately without retry.

---

### P3-5: `community_service.py` moderation fallback error logged via stdlib `logger.warning()` with f-string but structlog is active
**File**: `backend/services/community_service.py`, lines 134–142
**Category**: Code quality — logging inconsistency

```python
# community_service.py — Groq/Gemini fallback error logging
except Exception as exc:
    logger.warning(...)
    try:
        ...
    except Exception as fallback_exc:
        ...
```

`community_service.py` uses `structlog.get_logger(__name__)`, so `logger.warning()` accepts
keyword arguments for structured fields. The exception variables (`exc`, `fallback_exc`) are
available in scope but may not be included in the log call, losing context about what the
moderation failure was.

---

### P3-6: `useAgentQuery` hook does not handle the case where `sendQuery` is called while already streaming
**File**: `frontend/lib/hooks/useAgent.ts`, line 27
**Category**: Race condition — concurrent send calls

```python
# useAgent.ts
const sendQuery = useCallback(async (prompt: string) => {
    setError(null)
    setIsStreaming(true)
    abortRef.current = new AbortController()     // overwrites previous controller
    ...
```

**Risk**: If `sendQuery` is called a second time while a previous stream is still in flight (e.g.,
due to accidental double-click or programmatic rapid invocation), the previous `AbortController`
is replaced without aborting the previous request. Two SSE streams can be active simultaneously,
both appending to the same `messages` state, interleaving assistant tokens.

**Fix**: Abort the previous request before starting a new one.

```typescript
const sendQuery = useCallback(async (prompt: string) => {
    abortRef.current?.abort()  // cancel any in-flight stream first
    abortRef.current = new AbortController()
    ...
```

---

### P3-7: SSE `queryAgent` silently skips malformed JSON lines
**File**: `frontend/lib/api/agent.ts`, lines 103–107
**Category**: Error swallowing — silent parse failure in stream

```typescript
try {
  yield JSON.parse(data) as AgentMessage
} catch {
  // skip malformed lines
}
```

**Risk**: Acceptable for SSE comment lines and empty data events, but if a real backend error
message arrives as a malformed JSON fragment (e.g., a partial write due to an upstream proxy
truncation), it will be silently dropped. The user receives no indication that some content was
lost.

---

## Summary Table

| ID     | Severity | File                                             | Category             | Description                                           |
|--------|----------|--------------------------------------------------|----------------------|-------------------------------------------------------|
| P0-1   | P0       | `services/agent_service.py:305`                  | Null handling        | `IndexError` on empty Groq `choices` list             |
| P0-2   | P0       | `services/analytics_service.py:137-145`          | Race/error handling  | Cache stampede gap — implicit `None` return           |
| P1-1   | P1       | `services/agent_service.py:348`                  | Error swallowing     | Gemini fallback has no error logging                  |
| P1-2   | P1       | `services/alert_service.py:229`                  | Null handling        | `getattr` fallback masks `None` timestamp             |
| P1-3   | P1       | `services/recommendation_service.py:93`          | Null handling        | `PriceRegion()` with no null/invalid guard            |
| P1-4   | P1       | `services/connection_sync_service.py:140`        | Type coercion        | `encode("latin-1")` silently corrupts OAuth bytes     |
| P1-5   | P1       | `services/community_service.py:92-113`           | Race condition       | Shared `AsyncSession` across `wait_for` boundary      |
| P1-6   | P1       | `services/email_scanner_service.py:359,407,487`  | Error swallowing     | Attachment download/parse errors unlogged             |
| P2-1   | P2       | `api/v1/connections/bill_upload.py:71-85`        | Resource leak        | Background parse session no explicit rollback         |
| P2-2   | P2       | `api/v1/connections/email_oauth.py:331`          | Error swallowing     | Token refresh `except Exception` loses error context  |
| P2-3   | P2       | `services/observation_service.py:129`            | Type coercion        | `datetime.utcnow()` naive/aware mixing                |
| P2-4   | P2       | `services/dunning_service.py:194`                | Type coercion        | `Decimal("0")` falsy — zero invoices show "N/A"       |
| P2-5   | P2       | `services/price_service.py:291`                  | Null handling        | `ml_result["point"]` KeyError outside try/except      |
| P2-6   | P2       | `services/hnsw_vector_store.py:264-270`          | Resource/performance | Synchronous SQLite I/O on async event loop thread     |
| P2-7   | P2       | `frontend/lib/api/client.ts:123`                 | Resource leak        | Never-resolving `Promise` on 401                      |
| P2-8   | P2       | `services/rate_scraper_service.py:189`           | Error handling       | `return_exceptions=False` aborts entire batch         |
| P3-1   | P3       | `services/analytics_service.py:42,75`            | Error swallowing     | Redis cache errors fully silent                       |
| P3-2   | P3       | `services/agent_service.py:264`                  | Logic                | Usage increment skipped on mid-stream disconnect      |
| P3-3   | P3       | `services/forecast_service.py:263`               | Type coercion        | Mixed naive/aware datetime subtraction                |
| P3-4   | P3       | `services/referral_service.py:55`                | Error handling       | Retry loop retries non-retriable DB constraint errors |
| P3-5   | P3       | `services/community_service.py:134`              | Code quality         | Moderation error logging missing exception fields     |
| P3-6   | P3       | `frontend/lib/hooks/useAgent.ts:32`              | Race condition       | Concurrent `sendQuery` calls interleave SSE streams   |
| P3-7   | P3       | `frontend/lib/api/agent.ts:103`                  | Error swallowing     | Malformed SSE JSON silently dropped                   |

---

## Patterns Not Found (Checked But Clean)

- **Transaction missing rollback on exception** in API route handlers: All FastAPI route handlers
  using `get_db_session` dependency correctly rely on the session generator's `finally` block for
  rollback on unhandled exceptions.
- **asyncio.gather with shared mutable AsyncSession**: The `notification_dispatcher.py` gather
  pattern was reviewed — the two closures write to disjoint keys in the `results` dict, so no
  shared-state corruption is possible.
- **Off-by-one in pagination**: `get_historical_prices_paginated` correctly uses 1-based page
  parameter with `(page - 1) * page_size` offset in the repository.
- **Integer overflow**: Python has arbitrary-precision integers; no overflow risk in pure-Python
  arithmetic paths.
- **Unhandled promise rejections in frontend hooks**: All `useQuery` and `useMutation` hooks
  correctly handle errors via React Query's error boundary pattern. Fire-and-forget `.catch(() =>
  {})`  cases are intentional (onboarding flag update, auth session fire-and-forget) and do not
  affect user-visible state.
- **Open redirect in OAuth callback**: `email_oauth.py` has an explicit `_ALLOWED_FRONTENDS`
  allowlist and falls back to the production URL — correct.
- **Memory leak in asyncio background tasks**: `agent_service.py` uses `_background_tasks` set
  with `add_done_callback(_background_tasks.discard)` — correct strong-reference pattern.

---

## Recommended Next Steps

1. **P0-1**: Add `if not response.choices` guard in `_query_groq` — 2-line fix.
2. **P0-2**: In `analytics_service.py` all three methods (`get_price_trend`, `get_peak_hours_analysis`,
   `get_supplier_comparison_analytics`), replace the silent `None` return path after failed lock
   acquisition with a fall-through to the computation block.
3. **P1-1**: Add `logger.warning("gemini_query_failed_falling_back", ...)` in both streaming and
   async query paths of `agent_service.py`.
4. **P1-2 + P1-3**: Add null guards for `timestamp` access in alert service and `region` in
   recommendation service.
5. **P1-6**: Add `logger.warning` calls to all three bare `except Exception: continue` blocks in
   `email_scanner_service.py`.
6. **P2-3**: Replace all `datetime.utcnow()` calls with `datetime.now(UTC)`.
