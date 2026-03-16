# Audit: Middleware, Lib, and Config
**Date**: 2026-03-16
**Scope**: `backend/middleware/`, `backend/lib/`, `backend/config/`
**Files read**: 11 source files + `backend/app_factory.py` (middleware registration context)

---

## Summary

| Severity | Count |
|----------|-------|
| P0       | 2     |
| P1       | 6     |
| P2       | 8     |
| P3       | 6     |
| **Total**| **22**|

---

## P0 — Critical / Production Safety

### P0-01: `TracingMiddleware.structlog_clear_contextvars` erases context set by outer middleware

**File**: `backend/middleware/tracing.py`, line 61
**Description**: `structlog.contextvars.clear_contextvars()` is called unconditionally at the start of every request. In FastAPI's ASGI middleware stack, `add_middleware()` wraps in LIFO order, so the effective execution order inbound is:

```
TracingMiddleware  →  SecurityHeadersMiddleware  →  RateLimitMiddleware
→  RequestBodySizeLimitMiddleware  →  RequestTimeoutMiddleware  →  GZipMiddleware
→  CORSMiddleware  →  route handler
```

`TracingMiddleware` runs first (outermost), which is correct — but `clear_contextvars()` will wipe any context that Sentry's SDK or OTel instrumentation may have bound before the middleware was invoked (e.g. from async task inheritance or ASGI lifespan context). More critically, if two concurrent requests are handled in overlapping asyncio tasks and both share the same context variable namespace (structlog's `contextvars` module uses `contextvars.ContextVar` which is task-scoped, so this is safe in pure asyncio), the behaviour is correct. However, the `clear_contextvars()` call is unnecessary overhead and would become dangerous if the app were ever used with a thread executor or sync workers. The real issue is documented: the comment at lines 34-38 says this middleware should run "after" rate-limit and security-header middleware, but `app.add_middleware()` LIFO semantics mean **the last `add_middleware()` call executes first**. The code comment contradicts the actual registration order in `app_factory.py` (line 393), leading to whoever reads the comment believing the ordering is wrong when it is actually correct — or vice versa. Whoever changes registration order based on the comment will break tracing for all downstream middleware.

**Actual issue (P0)**: Line 61 calls `clear_contextvars()` which unconditionally drops any structlog context that Sentry (or any async task that spawned the request coroutine) already attached. This silently drops `sentry_sdk`'s `scope` breadcrumbs if Sentry binds to structlog context.

**Fix**:
```python
# Replace clear + bind with merge:
structlog.contextvars.bind_contextvars(trace_id=trace_id)
# Remove line 61: structlog.contextvars.clear_contextvars()
```
Also correct the docstring at lines 34-38 to accurately reflect LIFO ordering: "Register this middleware *last* (i.e. highest `add_middleware()` call position) so it executes first on the inbound path."

---

### P0-02: `RequestBodySizeLimitMiddleware` silently swallows chunked-body overflow — handler receives truncated data and may commit partial state

**File**: `backend/app_factory.py`, lines 138-151
**Description**: When a chunked `POST`/`PUT`/`PATCH` request exceeds the size limit, `counting_receive()` returns a sentinel `{"type": "http.request", "body": b"", "more_body": False}` to signal end-of-body. The inner application (`self.app`) receives this and processes what it has seen so far (a partial, possibly invalid body). The route handler may partially validate the truncated Pydantic model and — depending on the endpoint — write partial state to the database before the response path checks `limit_exceeded`. The `_send_413` is only called *after* `self.app` has finished, at line 150:

```python
await self.app(scope, counting_receive, guarded_send)
if limit_exceeded and not response_started:
    await self._send_413(send, max_bytes)
```

The inner application will have already processed the request (possibly committing a DB transaction) and sent a 200 before this point sets `response_started = True`. The `_send_413` is then silently suppressed because `response_started is True`.

**Fix**: Reject at the `counting_receive` level by raising an exception or — better — check `Content-Length` only, and for truly chunked transfers without a `Content-Length`, buffer up to `max_bytes + 1` before forwarding. The safest fix is to buffer the full body and reject before calling `self.app`:

```python
# In the chunked-encoding path, buffer first:
chunks = []
total = 0
async for chunk in _iter_body(receive):
    total += len(chunk)
    if total > max_bytes:
        await self._send_413(send, max_bytes)
        return
    chunks.append(chunk)
# Then replay buffered body to self.app via a synthetic receive callable.
```

---

## P1 — High / Should Fix Before Next Release

### P1-01: `RateLimitMiddleware._get_identifier` trusts `CF-Connecting-IP` without origin verification

**File**: `backend/middleware/rate_limiter.py`, lines 431-434
**Description**: The middleware unconditionally trusts the `CF-Connecting-IP` header (line 432) and `X-Forwarded-For` (line 438). These are client-controlled headers on any non-Cloudflare path to the backend. Render's direct URL (`srv-*.render.com`) is not behind the CF Worker; it is publicly accessible. An attacker who reaches Render directly can send `CF-Connecting-IP: 1.2.3.4` and bypass per-IP rate limiting entirely or spoof another user's IP bucket. The rate limiter then applies limits against the spoofed identifier rather than the real client IP.

**Fix**: Validate that the request originated from Cloudflare by checking the `CF-RAY` header **and** one of Cloudflare's known IP ranges, or — simpler — require the `X-Internal-Secret` / `X-Gateway-Auth` header that the CF Worker already sets (the gateway sends `X-API-Key` per CLAUDE.md). Only trust `CF-Connecting-IP` when the gateway auth header is present and valid.

```python
# Only trust CF-Connecting-IP when the CF Worker's auth header is present
gateway_auth_valid = any(
    name == b"x-api-key" and value.decode("latin-1") == settings.internal_api_key
    for name, value in headers
)
if gateway_auth_valid:
    for name, value in headers:
        if name == b"cf-connecting-ip":
            return f"ip:{value.decode('ascii')}"
```

---

### P1-02: `UserRateLimiter.get_rate_limiter` global singleton is not thread/coroutine safe during initialisation

**File**: `backend/middleware/rate_limiter.py`, lines 454-459
**Description**: `get_rate_limiter` uses a module-level `rate_limiter` variable with a naive `if rate_limiter is None` check. In an asyncio environment under high concurrency at startup, two coroutines may simultaneously see `rate_limiter is None` and both create a new `UserRateLimiter`. The second one overwrites the first, losing any Redis connection that was wired into the first instance. Note: `create_app()` creates its own `UserRateLimiter` and does not use `get_rate_limiter()`, so in the main application this function is currently unused — but it is part of the public API and test code may rely on it.

**Fix**: Use `asyncio.Lock` or remove the function entirely since `create_app()` manages the lifecycle. If retained:
```python
_rate_limiter_lock = asyncio.Lock()

async def get_rate_limiter(redis=None) -> UserRateLimiter:
    global rate_limiter
    async with _rate_limiter_lock:
        if rate_limiter is None:
            rate_limiter = UserRateLimiter(redis_client=redis)
    return rate_limiter
```

---

### P1-03: `CircuitBreaker.state` property has a TOCTOU race — state can change between property read and lock acquisition

**File**: `backend/lib/circuit_breaker.py`, lines 79-85 and 94-104
**Description**: `call()` calls `self.state` (the property, which checks `time.monotonic()`) without holding `_lock`, then acquires `_lock` and acts on the result. Between the property read and the lock acquisition another coroutine could call `record_failure()` and transition the breaker from `HALF_OPEN` to `OPEN`. The first coroutine then proceeds thinking the state is `HALF_OPEN` and increments `_half_open_calls`, allows the probe through, and awaits the coroutine — but the breaker is now actually `OPEN`. The coroutine runs when it should have fast-failed.

Concretely: with `half_open_max=1`, two concurrent probe requests can both see `HALF_OPEN` from the property and both enter `call()` before either acquires the lock. The first wins the lock, increments `_half_open_calls` to 1, releases, and proceeds. The second then acquires the lock, increments to 2, and also proceeds because the check `>= half_open_max` only gates on `>=` — both calls run.

**Fix**: Read `self.state` inside the lock to ensure atomicity:
```python
async with self._lock:
    current = self.state  # move inside the lock
    if current == CircuitState.OPEN:
        coro.close()
        raise CircuitBreakerOpen(self.name)
    if current == CircuitState.HALF_OPEN:
        if self._half_open_calls >= self.half_open_max:
            coro.close()
            raise CircuitBreakerOpen(self.name)
        self._half_open_calls += 1
```
This is already the pattern in the existing code but `self.state` must be evaluated *after* `async with self._lock:`, not before.

Wait — re-reading lines 94-104: `current = self.state` is called **inside** `async with self._lock:`. The lock IS held when `state` is read. The actual race is between `self.state` (property) doing `time.monotonic()` check and transitioning conceptually to `HALF_OPEN` while `self._state` is still `OPEN`. This is safe because the property only returns `HALF_OPEN` when enough time has elapsed — it does not mutate `_state`. **However**, `record_success()` and `record_failure()` also call `self.state` inside their own locks (lines 117, 128) — meaning two concurrent `record_success` calls both see `HALF_OPEN` and both call `_transition_to_closed()`. This is harmless (idempotent transition) but logs `circuit_breaker_closed` twice.

The real TOCTOU issue is: `_half_open_calls` is incremented inside `call()`'s lock (line 104), but `record_failure()` and `record_success()` each acquire their own lock calls. Between `call()` releasing the lock after incrementing `_half_open_calls` and actually awaiting `coro` (line 107), another coroutine's `record_failure` can fire and re-open the circuit. Then when this coroutine's `record_success` fires (line 112), it transitions the breaker back to CLOSED — undoing the failure record of the other coroutine. This is the intended cascading failure protection that is defeated.

**Fix**: Track `_half_open_calls` as a semaphore checked and released atomically, or use a single lock that spans check-and-execute.

---

### P1-04: `SecretsManager` invokes `subprocess.run(["op", ...])` synchronously from async context

**File**: `backend/config/secrets.py`, lines 128-135, 184-194
**Description**: `_is_op_available()` and `_get_from_1password()` call `subprocess.run(...)` which is a blocking syscall. In production this is called from `get_secret()`, which is called from service layer code that may be inside an async event loop (e.g., during startup lifespan or request handling). A 10-second `op read` timeout blocks the entire event loop thread, causing all other requests to stall for up to 10 seconds.

**Fix**: Use `asyncio.create_subprocess_exec` + `asyncio.wait_for` instead of `subprocess.run`, or run the subprocess in a thread executor:
```python
import asyncio
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, lambda: subprocess.run(...))
```
Alternatively, since secrets are only fetched at startup and cached for 1 hour (`CACHE_TTL = 3600`), restrict `_get_from_1password()` to a startup-only path and raise an error if called from within a request context.

---

### P1-05: `RateLimitMiddleware` does not emit `X-RateLimit-Reset` header — clients cannot implement correct backoff

**File**: `backend/middleware/rate_limiter.py`, lines 393-398
**Description**: The `X-RateLimit-Limit` and `X-RateLimit-Remaining` headers are added to successful responses but `X-RateLimit-Reset` (the Unix timestamp or seconds-until-reset) is absent. The 429 response also lacks `X-RateLimit-Reset`, only providing `Retry-After`. IETF draft `draft-ietf-httpapi-ratelimit-headers` requires all three headers for conformant clients. Without `X-RateLimit-Reset`, legitimate clients with burst patterns cannot determine the exact window boundary and may hit the limit repeatedly.

**Fix**: Compute and include `X-RateLimit-Reset` as the Unix timestamp of the oldest entry's expiry:
```python
reset_ts = int(time.time()) + 60  # conservative: current time + window
headers["X-RateLimit-Reset"] = str(reset_ts)
```
For the 429 path, include it in the raw ASGI headers list in `_send_429`.

---

### P1-06: `RequestTimeoutMiddleware` timeout exclusion is path-prefix only — `/api/v1/agent/stream` is NOT excluded

**File**: `backend/app_factory.py`, lines 185, 198-205
**Description**: `TIMEOUT_EXCLUDED_PREFIXES` includes `/api/v1/agent/` (line 185), but `/prices/stream` is excluded by a separate `endswith` check (line 198). The agent SSE streaming endpoint (`POST /agent/query`) is correctly excluded. However, the `/prices/stream` exclusion uses `endswith("/prices/stream")` which will **not** match `/api/v1/prices/stream` — it only matches the literal suffix. Since the router mounts prices at `/api/v1/prices/stream`, the path in scope will be `/api/v1/prices/stream`. `endswith("/prices/stream")` does match that string (it ends with that substring), so this particular case is actually correct.

The real gap: the `TIMEOUT_EXCLUDED_PREFIXES` check (line 203) runs **after** the `endswith` check (line 198). If a new SSE endpoint is added that does not follow the `/prices/stream` naming pattern, it will not be excluded and will be subject to the 30-second hard timeout, breaking SSE. This is a latent bug waiting for the next streaming endpoint addition.

Additionally, the timeout `asyncio.wait_for` wraps the full ASGI call including the `send` callable. If the inner app times out **after** response headers were sent (partial SSE stream), `asyncio.TimeoutError` is caught but `response_started` is `True`, so the 504 is suppressed — but the client connection is left open with an incomplete response body. The ASGI connection is never explicitly closed, leaving the client hanging until their own timeout fires.

**Fix**:
1. Replace the `endswith` pattern with a dedicated set: `SSE_PATHS = {"/api/v1/prices/stream", "/api/v1/agent/query"}`.
2. After catching `TimeoutError` when `response_started is True`, send a final `http.response.body` message with `more_body=False` to cleanly close the connection.

---

## P2 — Medium / Should Fix Soon

### P2-01: `SecurityHeadersMiddleware` applies `Cache-Control: no-store` to ALL `/api/` paths including public rate data

**File**: `backend/middleware/security_headers.py`, lines 121-126
**Description**: The check `path.startswith("/api/")` applies aggressive `no-store, no-cache, must-revalidate, private` cache headers to every API response. This includes public-facing, non-sensitive endpoints like `/api/v1/prices`, `/api/v1/suppliers`, and `/api/v1/rates/*` which are designed to be cached at the Cloudflare Worker edge layer with a `cacheTtl`. The browser and any intermediate CDN will refuse to cache these responses, negating the CF Worker's caching strategy and increasing backend load.

**Fix**: Add a carve-out for known public, cacheable endpoints or add a mechanism for routes to opt out (e.g., a response header `X-Cache-Policy: public` that the security middleware respects):
```python
PUBLIC_CACHE_PATHS = ("/api/v1/prices", "/api/v1/suppliers", "/api/v1/rates")
if is_api_path and not any(path.startswith(p) for p in PUBLIC_CACHE_PATHS):
    headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
```

---

### P2-02: `SecurityHeadersMiddleware` uses `mutableheaders(scope=message)` which mutates the ASGI message dict in-place — not safe for all ASGI servers

**File**: `backend/middleware/security_headers.py`, line 85
**Description**: `MutableHeaders(scope=message)` modifies the `headers` list inside the `message` dict in-place. This is the documented Starlette pattern, but it assumes `message["headers"]` is a mutable list. Some ASGI servers (e.g., Daphne, some versions of Hypercorn) pass an immutable tuple for headers. This will raise a `TypeError: 'tuple' object does not support item assignment` at runtime on those servers.

**Fix**: Use the same defensive copy pattern as `TracingMiddleware` (line 66-68):
```python
raw_headers = list(message.get("headers", []))
raw_headers.extend([
    (b"x-frame-options", b"DENY"),
    ...
])
message = {**message, "headers": raw_headers}
```

---

### P2-03: `settings.nrel_api_base_url` contains a typo in the default value

**File**: `backend/config/settings.py`, line 74
**Description**: The default URL is `"https://developer.nlr.gov/api/utility_rates/v3"` — `nlr.gov` should be `nrel.gov`. All environments that rely on the default (any that do not set `NREL_API_BASE_URL` explicitly) will make requests to a non-existent domain and fail silently.

**Fix**:
```python
nrel_api_base_url: str = Field(
    default="https://developer.nrel.gov/api/utility_rates/v3",
    validation_alias="NREL_API_BASE_URL",
)
```

---

### P2-04: `SecretsManager.get_instance` is `@lru_cache(maxsize=1)` on a `@staticmethod` — `clear_cache()` does not reset the singleton

**File**: `backend/config/secrets.py`, lines 228-232
**Description**: `get_instance()` is decorated with `@lru_cache`, so it returns the same `SecretsManager` object for the lifetime of the process. The instance's `clear_cache()` method (line 223) clears only the internal `_cache` dict (secret values), but the singleton itself — including its `use_1password` flag computed at construction time — is never refreshed. If `_is_op_available()` returns `False` at startup (e.g., `op` CLI is not yet authenticated), the singleton is permanently set to env-var mode even after 1Password becomes available. In production on Render, the `op` CLI is typically not available (it is a local tool), so this pattern is effectively vestigial but could cause confusion during debugging.

**Fix**: Document explicitly that the singleton is process-scoped and does not support 1Password on Render. Alternatively, expose a `reset_instance()` class method that clears the `lru_cache`:
```python
@classmethod
def reset_instance(cls) -> None:
    cls.get_instance.cache_clear()
```

---

### P2-05: `DatabaseManager._execute_raw_query` uses `text()` without parameter binding — SQL injection risk if query string is ever externally influenced

**File**: `backend/config/database.py`, lines 184-186
**Description**: The `_execute_raw_query` fallback path wraps `query` in `sqlalchemy.text()` and executes it without the `*args` parameters:
```python
result = await conn.execute(text(query))
```
The `*args` passed to `_execute_raw_query` are silently dropped in the SQLAlchemy fallback path. If any caller passes user-supplied data in `*args` expecting it to be bound, the query executes without those parameters and the args are ignored. Depending on how the query is constructed, this could either return wrong data or expose an injection surface if the caller interpolates args into the query string before passing it.

**Fix**:
```python
result = await conn.execute(text(query), list(args))
```
Also audit all callers of `_execute_raw_query` to ensure none construct `query` by string interpolation of user input.

---

### P2-06: `TracingMiddleware` leaks the `X-Request-ID` header from the caller without sanitising it in the response — header injection risk

**File**: `backend/middleware/tracing.py`, lines 51-55, 67
**Description**: When a caller supplies a valid `X-Request-ID` header (matching `_SAFE_REQUEST_ID`), the raw caller-supplied value is echoed back in the response `X-Request-ID` header (line 67). While the regex `^[\w\-]{1,64}$` prevents newline injection (CR/LF), it permits Unicode word characters (`\w` matches Unicode by default in Python). A caller could supply a trace ID like `ÄBC` which would pass the regex but could cause issues with some downstream log parsers or HTTP/1.1 header parsers that expect ASCII-only header values.

**Fix**: Restrict the regex to ASCII only:
```python
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-_]{1,64}$")
```

---

### P2-07: `app_factory.py` `protect_metrics` middleware allows `api_key` as a query parameter — API key in URLs leaks to access logs

**File**: `backend/app_factory.py`, lines 511-513
**Description**:
```python
api_key = (
    request.headers.get("X-API-Key")
    or request.query_params.get("api_key")
)
```
Accepting the API key as a query parameter means it will appear in Render's HTTP access logs, CF Worker logs, and any reverse proxy logs. This is a standard credential-in-URL anti-pattern (CWE-598).

**Fix**: Remove the `request.query_params.get("api_key")` fallback. Require the `X-API-Key` header exclusively.

---

### P2-08: `structlog.configure()` called at module import time in `app_factory.py` — affects all processes that import the module

**File**: `backend/app_factory.py`, lines 65-70
**Description**: `structlog.configure(...)` is a global side effect executed when the module is first imported. Test harnesses, management scripts, and worker processes that `import app_factory` (or `from app_factory import ...`) will have structlog reconfigured regardless of their own logging needs. This can cause double-logging or suppress test output in pytest.

**Fix**: Move the `structlog.configure()` call inside `create_app()` or inside a `configure_logging()` function that is called explicitly from `main.py` only.

---

## P3 — Low / Improvements

### P3-01: `RateLimitMiddleware` missing `X-RateLimit-Remaining` header for hour-limited responses

**File**: `backend/middleware/rate_limiter.py`, lines 390-398
**Description**: `remaining` is derived from the minute check only (from `check_rate_limits_combined` return value `minute_remaining`). When a request is blocked by the **hour** limit, the client receives a 429 with no `X-RateLimit-Remaining: 0` header. When requests pass through but are close to the hour limit, the `X-RateLimit-Remaining` header still reflects the minute bucket — potentially showing `95` remaining when the hour bucket is at `999/1000`.

---

### P3-02: `CircuitBreaker._transition_to_open` does not reset `_half_open_calls` counter when called from `record_failure` in HALF_OPEN state

**File**: `backend/lib/circuit_breaker.py`, lines 142-149 vs lines 128-129
**Description**: `_transition_to_open()` at line 149 does set `self._half_open_calls = 0`. However, when `record_failure()` is called while in `HALF_OPEN` state (line 128), it calls `_transition_to_open()` which resets the counter — this is correct. But there is no `success_count` tracked in HALF_OPEN to know how many probe calls succeeded before a failure re-opened. With `half_open_max > 1`, partial successes are not recorded — all must succeed for the breaker to close. This is intentional but undocumented.

**Fix**: Add a comment explaining the all-or-nothing probe policy for clarity.

---

### P3-03: `settings.py` production validators read `os.environ.get("ENVIRONMENT")` directly instead of using the already-validated `v` or model state

**File**: `backend/config/settings.py`, lines 217, 242, 263, 276, 292, 307, 324, 341
**Description**: Every `@field_validator` reads `os.environ.get("ENVIRONMENT", "development")` to determine the environment, bypassing the pydantic-validated `environment` field. This means:
1. If `ENVIRONMENT` is spelled differently in the environment (e.g., `Environment` on Windows), the validator silently uses `"development"` and skips production checks.
2. The `environment` field's own `validate_environment` validator runs after field validators, so theoretically an invalid `ENVIRONMENT` value could pass through field-level secret validators.

**Fix**: Use the already-validated `v` context or a `@model_validator(mode="after")` to check all secrets together after the `environment` field is validated.

---

### P3-04: `SecretsManager.SECRET_MAPPINGS` vault name is `"Electricity Optimizer"` but CLAUDE.md says vault is `"RateShift"`

**File**: `backend/config/secrets.py`, line 40
**Description**: `OP_VAULT = "Electricity Optimizer"` — the vault was renamed to `"RateShift"` per project branding (CLAUDE.md: "1Password vault: 'RateShift' with 28 credential mappings"). All `op://` URIs in `_get_from_1password()` will reference `op://Electricity Optimizer/...` which may 404 if the vault was renamed in 1Password.

**Fix**:
```python
OP_VAULT = "RateShift"
```

---

### P3-05: `lib/tracing.py` `traced` class does not handle `asyncio.CancelledError` — span may be left open if task is cancelled

**File**: `backend/lib/tracing.py`, lines 62-74
**Description**: `asyncio.CancelledError` (a `BaseException` subclass, not `Exception`, in Python 3.8+) is not caught by `except Exception` in the ASGI layers, but the `traced` context manager's `__aexit__` does receive it as `exc_val`. The `finally` block (line 71) will call `self._span.end()`, which is correct. However, `self._span.set_status(StatusCode.ERROR, str(exc_val))` will set the span status to ERROR for a cancellation, which may produce misleading traces (a cancelled task is not an error in the service sense). The status should be `UNSET` or a custom `CANCELLED` attribute.

**Fix**:
```python
from asyncio import CancelledError
if exc_type is CancelledError:
    span.set_attribute("cancelled", True)
    # Do not set ERROR status
elif exc_val is not None:
    span.set_status(StatusCode.ERROR, str(exc_val))
    span.record_exception(exc_val)
else:
    span.set_status(StatusCode.OK)
```

---

### P3-06: `DatabaseManager` silently continues when `database_url` is missing in production

**File**: `backend/config/database.py`, lines 44-49
**Description**: If `DATABASE_URL` is not set, `_init_database()` logs a warning and returns without raising. The `settings.py` `validate_database_url` validator should catch this in production — but only if `ENVIRONMENT=production` is set in the OS environment at settings import time. If for any reason the validator is bypassed (e.g., during test setup that patches settings), the app starts without a database and every DB operation silently returns empty results (`[]` from `_execute_raw_query`, `None` from sessions). This can cause subtle data-loss bugs where writes appear to succeed but are discarded.

**Fix**: In `_init_database()`, add an explicit guard:
```python
if not db_url and settings.is_production:
    raise RuntimeError("DATABASE_URL must be set in production")
```

---

## Middleware Registration Order Analysis

Actual execution order (inbound request path, based on LIFO `add_middleware` + decorator `@app.middleware` wrapping):

```
1. TracingMiddleware           (last add_middleware → outermost → runs first)
2. SecurityHeadersMiddleware
3. RateLimitMiddleware
4. RequestBodySizeLimitMiddleware
5. RequestTimeoutMiddleware    (first add_middleware → innermost of ASGI stack)
6. GZipMiddleware              (Starlette built-in)
7. CORSMiddleware              (Starlette built-in)
8. add_process_time_header     (@app.middleware decorator — innermost, runs last before handler)
9. protect_metrics             (@app.middleware decorator)
10. Route handler
```

**Issue**: CORS runs *after* rate limiting (step 7 vs step 3). A pre-flight `OPTIONS` request that is rate-limited will receive a 429 **without CORS headers**. The browser will interpret this as a CORS error, not a rate limit error — providing a misleading error to the client. Rate-limited `OPTIONS` requests should still return CORS headers so the client can see the actual `Retry-After`.

**Fix**: Either exclude `OPTIONS` requests from rate limiting or move `CORSMiddleware` to execute before rate limiting. In Starlette, `add_middleware(CORSMiddleware)` should be called **after** `add_middleware(RateLimitMiddleware)` so CORS wraps the rate limiter.

---

## Config — Missing Env Var Validation

| Variable | Issue |
|----------|-------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No format validation (must be a valid URL). An invalid URL causes a runtime crash in the OTLP exporter, not a startup error. |
| `smtp_port` | No range validation. A value of `0` or `65536` would silently fail at email send time. |
| `data_retention_days` | No minimum validation. A value of `0` would cause all data to be immediately eligible for deletion. |
| `model_accuracy_threshold_mape` | No range validation — negative values or values > 100 are accepted. |
| `CORS_ORIGINS` | JSON parse failure falls back silently to comma-split; malformed JSON (e.g. `["http://localhost:3000"` — missing close bracket) will parse as a single string origin containing the bracket characters, effectively allowing no origins and breaking all browser requests without a clear error message. |
