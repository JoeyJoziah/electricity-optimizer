# Audit Report: Middleware & Library Utilities
**Date:** 2026-03-23
**Scope:** Middleware pipeline, circuit breaker, tracing, config management
**Files Reviewed:**
- `backend/middleware/__init__.py`
- `backend/middleware/rate_limiter.py`
- `backend/middleware/security_headers.py`
- `backend/middleware/tracing.py`
- `backend/lib/__init__.py`
- `backend/lib/circuit_breaker.py`
- `backend/lib/tracing.py`
- `backend/config/__init__.py`
- `backend/config/settings.py`
- `backend/config/secrets.py`
- `backend/config/database.py`
- `backend/app_factory.py`
- `backend/main.py`
- `backend/observability.py`
- `backend/gunicorn_config.py`

---

## P0 -- Critical (Fix Immediately)

### P0-01: OTel `_server_request_hook` silently fails to read `trace_id` from scope state (observability.py:286-290)

**File:** `backend/observability.py`, lines 286-290
**File:** `backend/middleware/tracing.py`, line 57

The `TracingMiddleware` stores `trace_id` in a plain Python `dict`:

```python
# tracing.py:57
scope.setdefault("state", {})["trace_id"] = trace_id
```

But `_server_request_hook` in `observability.py` retrieves it with `getattr`:

```python
# observability.py:286-288
state = scope.get("state")
if state is not None:
    request_id = getattr(state, "trace_id", None)
```

`getattr(a_dict, "trace_id", None)` always returns `None` because a plain `dict` does not have a `trace_id` attribute -- dict items are accessed via subscript (`d["trace_id"]`), not via attribute access. This means the `http.request_id` span attribute is **never set** on OTel spans, even though the middleware correctly injects it into the scope. The same problem affects `app.user_id` on line 296.

Note: When accessed via Starlette's `request.state` (as in `app_factory.py:488`), Starlette wraps the scope dict into a `State` object that supports attribute access, so the `add_process_time_header` middleware works correctly. However, the raw `scope` dict passed to `_server_request_hook` by the FastAPI instrumentor does **not** go through that transformation.

**Impact:** All OTel traces are missing `http.request_id` and `app.user_id` attributes, significantly reducing observability value in Grafana Tempo. This is invisible (no error raised) because `getattr` silently returns `None`.

**Fix:** In `_server_request_hook`, access the state dict with subscript:
```python
state = scope.get("state")
if isinstance(state, dict):
    request_id = state.get("trace_id")
else:
    request_id = getattr(state, "trace_id", None)
```

---

### P0-02: `UserRateLimiter.__init__` mutable default arguments typed as `int = None` (rate_limiter.py:90-91)

**File:** `backend/middleware/rate_limiter.py`, lines 90-91

```python
requests_per_minute: int = None,
requests_per_hour: int = None,
```

The type annotation declares `int` but the default is `None`. While Python does not enforce type hints at runtime, this is misleading to type checkers and developers. More critically, the `or` fallback on lines 106-107:

```python
self.requests_per_minute = requests_per_minute or settings.rate_limit_per_minute
self.requests_per_hour = requests_per_hour or settings.rate_limit_per_hour
```

This means passing `0` explicitly (e.g., to disable rate limiting for a test) would be silently treated as falsy, falling through to the settings default. This is a correctness bug for any caller that passes `requests_per_minute=0`.

**Fix:** Use `int | None = None` for the type and `if requests_per_minute is not None` instead of `or`:
```python
self.requests_per_minute = requests_per_minute if requests_per_minute is not None else settings.rate_limit_per_minute
```

---

## P1 -- High (Fix This Sprint)

### P1-01: Log sanitizer recompiles regex patterns on every log call (app_factory.py:58-68)

**File:** `backend/app_factory.py`, lines 58-68

The `_sanitize_log_record` structlog processor defines `_SENSITIVE_PATTERNS` as a local variable inside the function body:

```python
def _sanitize_log_record(logger, method, event_dict):
    import re
    _SENSITIVE_PATTERNS = [
        re.compile(r"(postgresql|postgres|redis)://[^@\s]*@", re.IGNORECASE),
        re.compile(r"\b(sk_live_|rk_live_)\w+", re.IGNORECASE),
    ]
```

The inline comment claims "Python caches re.compile results," which is true for `re.search`/`re.match` with string patterns (via the module-level `_cache`), but `re.compile()` itself is **not cached** -- it creates a new compiled pattern object every invocation. This function is called for **every log record emitted by the application**, meaning two `re.compile` calls and two `re.sub` calls per string field per log line.

**Impact:** Unnecessary CPU overhead on every log call in production. Under high request volume, this adds measurable latency to the hot path.

**Fix:** Move the patterns to module level or make them a mutable default argument:
```python
_SENSITIVE_PATTERNS = [
    re.compile(r"(postgresql|postgres|redis)://[^@\s]*@", re.IGNORECASE),
    re.compile(r"\b(sk_live_|rk_live_)\w+", re.IGNORECASE),
]

def _sanitize_log_record(logger, method, event_dict):
    ...
```

---

### P1-02: `add_process_time_header` uses Starlette `@app.middleware("http")` (BaseHTTPMiddleware) (app_factory.py:478-510)

**File:** `backend/app_factory.py`, lines 478-510

All other middleware in the pipeline (`RateLimitMiddleware`, `SecurityHeadersMiddleware`, `TracingMiddleware`, `RequestBodySizeLimitMiddleware`, `RequestTimeoutMiddleware`) are implemented as pure ASGI middleware for good reason: they avoid the `BaseHTTPMiddleware` pattern which **buffers the entire response body in memory** before sending it.

However, `add_process_time_header` uses `@app.middleware("http")` which internally uses Starlette's `BaseHTTPMiddleware`. This means:

1. **SSE streaming responses** (e.g., `/prices/stream`) will be buffered entirely before the first byte is sent, breaking real-time streaming semantics.
2. **Large response bodies** are held in memory, increasing memory pressure on the 512MB Render free tier.
3. **Background tasks** may behave unexpectedly because `BaseHTTPMiddleware` reads the entire response before yielding.

The `RequestTimeoutMiddleware` explicitly excludes `/prices/stream`, but the process time middleware does not -- it wraps all requests including SSE.

**Impact:** SSE endpoint may be broken or significantly degraded. Memory usage spikes on large responses.

**Fix:** Convert to pure ASGI middleware like the others, or at minimum exclude SSE paths. The same metric can be computed by recording `time.time()` before and after `self.app(scope, receive, send_wrapper)`.

---

### P1-03: `protect_metrics` middleware duplicates the `@app.middleware("http")` buffering problem (app_factory.py:566-581)

**File:** `backend/app_factory.py`, lines 566-581

Same issue as P1-02. The `protect_metrics` handler uses `@app.middleware("http")`, meaning all requests -- including SSE and streaming -- pass through `BaseHTTPMiddleware` response buffering just to check if the path starts with `/metrics`.

**Impact:** Every request incurs `BaseHTTPMiddleware` buffering overhead for a path check that only applies to `/metrics`.

**Fix:** Convert to a pure ASGI middleware or move the API key check into the `/metrics` route handler itself.

---

### P1-04: Missing `OAUTH_STATE_SECRET` and `ML_MODEL_SIGNING_KEY` in Settings (settings.py)

**File:** `backend/config/settings.py`

The CLAUDE.md documents two security-critical settings:
- `OAUTH_STATE_SECRET` -- used for HMAC-SHA256 signing of OAuth state parameters (5-part format with 10-min expiry)
- `ML_MODEL_SIGNING_KEY` -- used for HMAC model integrity verification

Neither of these appears in `Settings` class or anywhere in the backend codebase. If these features are implemented (as the CLAUDE.md patterns section indicates), they may be reading from `os.environ` directly, bypassing the validated settings pipeline. If they are not yet implemented, they should be added proactively with production validators.

**Impact:** OAuth state tokens and ML model signatures may be using unvalidated secrets or missing entirely.

---

### P1-05: `decode_responses=True` on Redis may cause subtle issues with Lua script numeric returns (database.py:129 + rate_limiter.py:162)

**File:** `backend/config/database.py`, line 129
**File:** `backend/middleware/rate_limiter.py`, lines 162-170

Redis is initialized with `decode_responses=True`:
```python
self.redis_client = await aioredis.from_url(
    ...
    decode_responses=True,
)
```

The rate limiter Lua script returns a numeric value (ZCARD count). With `decode_responses=True`, redis-py will attempt to decode the return value as a UTF-8 string. While `int()` on line 170 handles this (`int("5")` works), the behavior is fragile and relies on undocumented coercion. More importantly, the Lua `EVAL` command with `decode_responses=True` decodes ALL returned values, including ones that are already integers in the Redis protocol. The `int(request_count)` cast on line 170 is defensive but depends on redis-py's internal behavior for how it decodes integer responses.

This is currently working but is a reliability risk during redis-py version upgrades.

**Impact:** Low probability but high consequence -- a redis-py upgrade could change how `EVAL` return values are decoded with `decode_responses=True`, potentially causing `TypeError` or `ValueError`.

**Recommendation:** Document this dependency explicitly, or create a separate Redis client for rate limiting without `decode_responses=True`.

---

### P1-06: `_check_memory` in-memory rate limiter is not thread-safe under Gunicorn (rate_limiter.py:270-305)

**File:** `backend/middleware/rate_limiter.py`, lines 270-305

The `_check_memory` fallback uses a plain `dict` (`self._memory_store`) without any locking. While the comment on line 280 mentions "race with concurrent coroutines," the actual code does not use any synchronization primitive. Under a multi-threaded executor or when `asyncio.gather` runs concurrent tasks, multiple coroutines can:

1. Both read the same list from `self._memory_store`
2. Both independently compute filtered lists
3. Both write back, with one overwriting the other's filtered result

Additionally, the `del self._memory_store[key]` on line 286 followed by `self._memory_store.setdefault(key, []).append(now)` on line 299 creates a TOCTOU window where another coroutine could insert between the delete and the setdefault.

In practice, this only manifests when Redis is down (fallback mode) and under concurrent load, but that is exactly the scenario where accuracy matters most.

**Impact:** Inaccurate rate limiting counts during Redis outages.

**Fix:** Use `asyncio.Lock` to protect `_memory_store` mutations, similar to the circuit breaker pattern.

---

### P1-07: Circuit breaker `state` property has side-effect-free OPEN-to-HALF_OPEN transition without lock (circuit_breaker.py:80-86)

**File:** `backend/lib/circuit_breaker.py`, lines 80-86

```python
@property
def state(self) -> CircuitState:
    if self._state == CircuitState.OPEN:
        if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
            return CircuitState.HALF_OPEN
    return self._state
```

The `state` property checks the timeout and returns `HALF_OPEN` without actually transitioning `self._state`. This means:

1. The `state` property is called both inside and outside the lock (e.g., in `call()` at line 96 where it is inside the lock, but also potentially by external monitoring code without the lock).
2. Multiple concurrent calls to `call()` could all see `HALF_OPEN` via the property and all pass the `_half_open_calls < half_open_max` check (line 102), since `_half_open_calls` is only incremented one-at-a-time inside the lock. However, since the property is read inside `async with self._lock`, this specific path is safe.
3. But any external code calling `.state` (e.g., health checks, metrics exporters) would get a misleading `HALF_OPEN` return without the actual state mutation, and repeated calls would keep returning `HALF_OPEN` even after a probe has already been dispatched.

**Impact:** Monitoring dashboards and health checks could report stale state. External consumers of `.state` may make incorrect decisions.

**Recommendation:** Either make the transition to HALF_OPEN explicit (mutate `_state` inside the lock on first access), or document that `.state` is only reliable when accessed inside the lock.

---

## P2 -- Medium (Fix Soon)

### P2-01: Missing `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy` headers (security_headers.py)

**File:** `backend/middleware/security_headers.py`

The security headers middleware includes a solid set of headers (CSP, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy, X-Content-Type-Options). However, it is missing two modern security headers recommended by OWASP:

- `Cross-Origin-Opener-Policy: same-origin` -- prevents cross-origin documents from opening the app in a new window context (Spectre mitigation)
- `Cross-Origin-Resource-Policy: same-origin` -- prevents cross-origin reads of the API response (Spectre mitigation)

X-XSS-Protection is intentionally omitted (verified via tests), which is correct for modern browsers.

**Impact:** Reduced defense-in-depth against Spectre-class side-channel attacks.

---

### P2-02: CSP `img-src` allows all HTTPS origins in production (security_headers.py:66)

**File:** `backend/middleware/security_headers.py`, line 66

```python
"img-src 'self' data: https:; "
```

The production CSP allows loading images from any `https:` origin. This is overly permissive for a backend API that primarily serves JSON. If any endpoint serves HTML (e.g., email previews, error pages), this could be leveraged for exfiltration via image tags.

**Impact:** Minor CSP bypass potential. Low risk for a pure API backend, but tightening to specific domains would be more secure.

---

### P2-03: `add_security_headers` utility function is incomplete relative to middleware (security_headers.py:131-143)

**File:** `backend/middleware/security_headers.py`, lines 131-143

The standalone `add_security_headers()` function only sets three headers:

```python
response.headers["X-Frame-Options"] = "DENY"
response.headers["X-Content-Type-Options"] = "nosniff"
response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
```

It is missing CSP, Permissions-Policy, HSTS, and Cache-Control compared to the middleware. If any code path uses this function instead of relying on the middleware (e.g., error responses emitted before the middleware runs), those responses will have incomplete security headers.

**Impact:** Inconsistent security header coverage on responses that bypass the middleware.

**Fix:** Either complete the function to match the middleware, or remove it to avoid the false sense of security.

---

### P2-04: `_execute_raw_query` uses `text()` without parameterization guard (database.py:176-189)

**File:** `backend/config/database.py`, lines 176-189

```python
async def _execute_raw_query(self, query: str, *args):
    if self.timescale_pool:
        async with self.timescale_pool.acquire() as conn:
            return await conn.fetch(query, *args)

    if self.timescale_engine:
        from sqlalchemy import text
        async with self.timescale_engine.connect() as conn:
            result = await conn.execute(text(query))
            return result.fetchall()
```

In the SQLAlchemy fallback path (line 186), `*args` are **ignored** -- the query is passed to `text(query)` without binding parameters. The asyncpg path (line 180) correctly passes `*args`. This means:

1. If a caller passes parameters expecting them to be bound, the SQLAlchemy fallback silently drops them, potentially executing an incomplete or incorrect query.
2. If a caller passes user-derived strings concatenated into `query`, this is a SQL injection vector in the SQLAlchemy path.

Current callers (`health.py`) only use `"SELECT 1"` with no parameters, so no active exploit exists, but the API contract is dangerously inconsistent.

**Impact:** Silent parameter dropping in fallback path; potential future SQL injection if callers are added.

**Fix:** Bind params in the SQLAlchemy path:
```python
result = await conn.execute(text(query), dict(enumerate(args)))
```
Or better, remove the raw query method and use the session-based approach exclusively.

---

### P2-05: Secrets manager subprocess calls are blocking (secrets.py:127-134, 183-193)

**File:** `backend/config/secrets.py`, lines 127-134 and 183-193

`SecretsManager` uses `subprocess.run()` which is a **blocking** call. In an async FastAPI application, this blocks the event loop for up to 10 seconds (the timeout) per secret retrieval:

```python
result = subprocess.run(
    ["op", "read", f"op://{self.OP_VAULT}/{item_field}"],
    capture_output=True,
    text=True,
    timeout=10,
)
```

While secrets are cached (1-hour TTL), the first retrieval and any cache miss will block the entire event loop.

**Impact:** Event loop blocking during secret retrieval can cause request timeouts for concurrent requests. Mitigated by caching, but cold starts and cache expirations are affected.

**Fix:** Use `asyncio.subprocess` or `asyncio.to_thread(subprocess.run, ...)` for the `op` CLI calls.

---

### P2-06: `RequestTimeoutMiddleware` timeout cancellation may leave dangling state (app_factory.py:230-289)

**File:** `backend/app_factory.py`, lines 271-289

```python
try:
    await asyncio.wait_for(
        self.app(scope, receive, guarded_send),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
except TimeoutError:
    if not response_started:
        ...send 504...
```

When `asyncio.wait_for` cancels the inner task due to timeout:
1. The cancelled coroutine may be in the middle of a database transaction, leaving the session in an inconsistent state.
2. The SQLAlchemy session's `rollback()` in the `get_timescale_session` context manager may not execute if the cancellation occurs at an inopportune point.
3. If `response_started` is `True` (headers already sent), the timeout exception is silently swallowed and the client receives a truncated response with no indication of failure.

**Impact:** Database sessions could be leaked or left in uncommitted states after timeouts. Clients may receive partial responses.

**Recommendation:** Add a `finally` block to clean up resources, and log when a timeout occurs after response headers have been sent.

---

### P2-07: Middleware ordering allows rate-limited requests to still incur body size check and timeout overhead (app_factory.py:431-471)

**File:** `backend/app_factory.py`, lines 431-471

The middleware registration order is:
```
1. CORSMiddleware                   (innermost -- runs last on request)
2. GZipMiddleware
3. TracingMiddleware
4. SecurityHeadersMiddleware
5. RateLimitMiddleware
6. RequestBodySizeLimitMiddleware
7. RequestTimeoutMiddleware          (outermost -- runs first on request)
```

Since Starlette middleware is LIFO (last registered = outermost), the actual inbound execution order is:

```
Inbound:  Timeout -> BodySize -> RateLimit -> Security -> Tracing -> GZip -> CORS -> App
```

This means:
- `RequestBodySizeLimitMiddleware` runs **before** `RateLimitMiddleware`. A rate-limited IP can still trigger the body size counting logic before being rejected.
- `RequestTimeoutMiddleware` wraps everything, including rate limit checks. If Redis is slow, a rate limit check could itself timeout at 30s and return 504 instead of 429.
- `TracingMiddleware` runs **after** `RateLimitMiddleware`, so rate-limited requests do not get a trace ID in their 429 response.

**Impact:** Rate-limited requests incur unnecessary processing. Trace IDs are missing from 429 responses, making abuse debugging harder.

**Recommended order:**
```
Inbound: Tracing -> RateLimit -> Timeout -> BodySize -> Security -> GZip -> CORS -> App
```

---

### P2-08: `_sanitize_log_record` does not redact secrets in nested dicts or exception objects (app_factory.py:76-86)

**File:** `backend/app_factory.py`, lines 76-86

The sanitizer handles `str`, `list`, and `tuple` values, but does not recurse into:
- Nested `dict` values (e.g., `extra={"url": "postgresql://user:pass@host"}`)
- Exception objects whose `str()` representation may contain secrets
- `bytes` values

```python
for key, value in event_dict.items():
    if isinstance(value, str):
        sanitized[key] = _scrub(value)
    elif isinstance(value, (list, tuple)):
        sanitized[key] = type(value)(...)
    else:
        sanitized[key] = value  # <-- nested dicts pass through unsanitized
```

**Impact:** Secrets in nested structures bypass sanitization and appear in Grafana Cloud logs.

---

### P2-09: `SecretsManager.get_instance()` uses `@lru_cache` which is not thread-safe pre-Python 3.12 (secrets.py:228-232)

**File:** `backend/config/secrets.py`, lines 228-232

```python
@staticmethod
@lru_cache(maxsize=1)
def get_instance() -> "SecretsManager":
    return SecretsManager()
```

`functools.lru_cache` is thread-safe in Python 3.12+ (GIL refactoring), but in earlier versions, concurrent calls could create multiple `SecretsManager` instances before the cache is populated. Since this project requires Python 3.12, this is acceptable, but worth documenting the dependency.

Additionally, `lru_cache` prevents garbage collection of the `SecretsManager` instance even after it is no longer needed, though for a singleton this is acceptable.

**Impact:** Minimal given Python 3.12 requirement. Document the version dependency.

---

### P2-10: Gunicorn config references old brand name "Electricity Optimizer" (gunicorn_config.py:63)

**File:** `backend/gunicorn_config.py`, line 63

```python
server.log.info("Starting Electricity Optimizer API...")
```

The project has been rebranded to "RateShift" but the gunicorn startup message still references the old name.

**Impact:** Cosmetic / operational confusion in logs.

---

## P3 -- Low / Housekeeping

### P3-01: `tracemalloc` or memory profiling not configured in Gunicorn despite free-tier memory constraints (gunicorn_config.py)

**File:** `backend/gunicorn_config.py`

Given the 512MB RAM constraint documented in the file header, there is no memory limit enforcement or `tracemalloc` configuration. The `max_requests=1000` provides worker recycling but does not prevent a single request from consuming excessive memory.

**Recommendation:** Add `limit_request_line`, `limit_request_fields`, and `limit_request_field_size` to constrain inbound request sizes at the Gunicorn level (defense in depth alongside `RequestBodySizeLimitMiddleware`).

---

### P3-02: `RateLimitMiddleware._get_identifier` uses SHA-256 hash of bearer token but only first 16 hex chars (rate_limiter.py:483)

**File:** `backend/middleware/rate_limiter.py`, line 483

```python
token_hash = hashlib.sha256(auth[7:].encode()).hexdigest()[:16]
```

Using only 16 hex characters (64 bits) of the SHA-256 hash creates a collision space of 2^64, which is sufficient for rate limiting purposes. However, if two different users happen to collide (improbable but nonzero), they would share a rate limit bucket. This is acceptable for rate limiting but should be documented.

**Impact:** Negligible collision risk, but worth a comment.

---

### P3-03: `SecurityHeadersMiddleware` applies CSP to all responses including JSON API responses (security_headers.py:94)

**File:** `backend/middleware/security_headers.py`, line 94

CSP headers are primarily meaningful for HTML responses. Applying them to every JSON API response adds unnecessary bytes to every response. While not harmful, it increases bandwidth.

**Recommendation:** Conditionally apply CSP only to responses with `text/html` content type, or document that the uniform application is intentional for defense-in-depth.

---

### P3-04: `settings.cors_origins` property silently swallows JSON parse errors (settings.py:42-46)

**File:** `backend/config/settings.py`, lines 42-46

```python
if raw.startswith("["):
    try:
        return _json.loads(raw)
    except _json.JSONDecodeError:
        pass
return [origin.strip() for origin in raw.split(",") if origin.strip()]
```

If the value starts with `[` but is malformed JSON (e.g., `["http://localhost:3000",]`), it silently falls through to comma-splitting, which would produce `['["http://localhost:3000"', ']']` -- completely wrong origins. This should at minimum log a warning.

**Impact:** Misconfigured CORS origins could silently produce incorrect values.

---

### P3-05: `import asyncio as _asyncio` inside method body (rate_limiter.py:222)

**File:** `backend/middleware/rate_limiter.py`, line 222

```python
async def _check_redis_both(self, identifier):
    import asyncio as _asyncio
```

This deferred import is unnecessary -- `asyncio` is a stdlib module that is already loaded (the entire middleware runs in an async context). Move to top-level imports for clarity and to avoid the per-call import lookup overhead.

---

### P3-06: `time` imported inline via `__import__` (rate_limiter.py:443)

**File:** `backend/app_factory.py`, line 443 (inside `RateLimitMiddleware.__call__` send_wrapper)

```python
now = int(__import__("time").time())
```

`time` is already imported at the top of `rate_limiter.py`. In `app_factory.py`, `time` is also imported at module level. This `__import__` call is unnecessary and slightly less readable.

**Impact:** Cosmetic only.

---

### P3-07: `RequestBodySizeLimitMiddleware._send_413` integer division truncates for non-MB limits (app_factory.py:213)

**File:** `backend/app_factory.py`, line 213

```python
max_mb = max_bytes // (1024 * 1024)
```

If `max_bytes` is less than 1 MB (e.g., 500 KB), this would produce `max_mb = 0`, and the error message would say "Maximum size is 0 MB." Currently both code paths use 1 MB and 10 MB so this is not triggered, but it is a latent bug for future configurations.

**Fix:** Use float division or format in KB when under 1 MB.

---

### P3-08: `Sentry traces_sample_rate` discrepancy between prod and non-prod (app_factory.py:375-376)

**File:** `backend/app_factory.py`, lines 375-376

```python
traces_sample_rate=0.1 if settings.is_production else 0.05,
```

Production samples 10% of traces while non-production (development/staging) samples 5%. Typically, you want **higher** sampling in development for debugging and **lower** in production for cost management. The current values appear inverted.

**Impact:** Higher-than-expected Sentry trace costs in production; lower-than-expected trace coverage in development.

---

### P3-09: `app_factory.py` root endpoint exposes `environment` value (app_factory.py:594)

**File:** `backend/app_factory.py`, line 594

```python
info = {
    "name": settings.app_name,
    "version": settings.app_version,
    "environment": settings.environment,
    ...
}
```

The root endpoint returns `"environment": "production"` which confirms to an attacker that they are hitting the production system. This is minor since the endpoint is unauthenticated and other fingerprinting methods exist, but it is unnecessary information disclosure.

**Recommendation:** Remove `environment` from the root endpoint response in production.

---

### P3-10: No `Vary` header set on responses (security_headers.py, app_factory.py)

**File:** `backend/middleware/security_headers.py`

The security headers middleware does not set a `Vary` header. For an API behind Cloudflare caching, missing `Vary: Authorization` could cause cached authenticated responses to be served to unauthenticated users (or vice versa). The CF Worker likely handles this, but defense-in-depth at the backend would be more robust.

**Impact:** Low due to CF Worker cache layer, but a hardening opportunity.

---

## Files With No Issues Found

- `backend/middleware/__init__.py` -- Empty module init, no issues.
- `backend/lib/__init__.py` -- Empty module init, no issues.
- `backend/config/__init__.py` -- Empty module init, no issues.
- `backend/main.py` -- Minimal entry point delegating to `create_app()`, clean and correct.

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| P0       | 2     | OTel trace attribute silently broken (dict vs attribute access); rate limiter falsy-zero bug |
| P1       | 7     | Log sanitizer perf (regex per-call); BaseHTTPMiddleware on SSE paths; missing settings for documented secrets; Redis decode_responses fragility; in-memory rate limiter thread safety; circuit breaker state property ambiguity |
| P2       | 10    | Missing modern security headers; CSP overly permissive; incomplete utility function; raw query param dropping; blocking subprocess; timeout cancellation cleanup; middleware ordering; nested dict sanitization; lru_cache docs; brand name |
| P3       | 10    | Memory profiling; hash collision docs; CSP on JSON; CORS parse silence; inline imports; integer division; Sentry sample rate inversion; environment disclosure; Vary header |
| **Total** | **29** | |

**Overall Assessment:**

The middleware and library layer is well-architected with a strong emphasis on pure ASGI middleware (avoiding BaseHTTPMiddleware), atomic Redis Lua scripts for rate limiting, and proper circuit breaker patterns. The settings validation is thorough with production-specific guards for all critical secrets.

The two P0 findings are both "silent failure" bugs -- they do not crash the application but silently degrade functionality. The OTel trace attribute bug means all distributed traces are missing request correlation IDs, significantly reducing the value of the Grafana Tempo investment. The rate limiter `int = None` with `or` fallback is a correctness issue that could manifest if any caller passes `0`.

The P1 findings around BaseHTTPMiddleware usage on the process-time and metrics-protection handlers are architectural concerns that could impact SSE streaming and memory usage. The log sanitizer regex recompilation is a measurable performance issue on the hot path.

The middleware ordering analysis (P2-07) reveals that rate-limited requests still incur body-size counting and timeout wrapping overhead, and that rate-limited 429 responses lack trace IDs -- both of which are worth addressing for operational hygiene.
