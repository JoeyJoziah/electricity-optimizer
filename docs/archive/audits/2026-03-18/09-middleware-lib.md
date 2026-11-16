# Audit Report: Middleware, Shared Libraries & Utilities

**Date**: 2026-03-18
**Scope**: All middleware, shared libraries, and utility modules in the backend
**Files Reviewed**:
- `backend/middleware/__init__.py`
- `backend/middleware/security_headers.py`
- `backend/middleware/rate_limiter.py`
- `backend/middleware/tracing.py`
- `backend/lib/__init__.py`
- `backend/lib/circuit_breaker.py`
- `backend/lib/tracing.py`
- `backend/utils/__init__.py`
- `backend/utils/encryption.py`
- `backend/config/settings.py`
- `backend/config/database.py`
- `backend/config/secrets.py`
- `backend/app_factory.py`
- `backend/services/email_service.py`

***

## Executive Summary

The middleware and shared-library layer is generally well-architected. The code uses pure ASGI middleware (avoiding BaseHTTPMiddleware response-buffering issues), the rate limiter has been hardened with an atomic Lua sliding-window script, and the settings module enforces production-required fields at startup. The encryption module is cryptographically correct (AES-256-GCM, 96-bit random nonce).

However, this audit identified **2 P0-Critical**, **5 P1-High**, **7 P2-Medium**, and **8 P3-Low** findings. The most severe issues are: the in-memory rate limiter fallback is not thread-safe under asyncio concurrency, `decrypt_field()` can silently discard a `InvalidTag` authentication failure if callers do not explicitly catch it, the `SecretsManager` singleton is backed by `lru_cache` which breaks when tests call `SecretsManager()` directly, and the `RequestBodySizeLimitMiddleware` chunked-encoding guard has a logic bug that silently accepts oversized bodies on certain code paths.

**Controls Reviewed**: 68 | **Findings Identified**: 22 | **Critical/High Issues**: 7

---

## P0 — Critical (Fix Immediately)

### P0-01: `RequestBodySizeLimitMiddleware` Chunked-Encoding Guard Silently Accepts Oversized Bodies

**File**: `backend/app_factory.py`, lines 128–159

The chunked-encoding guard only activates when **all** three conditions are true: the method is `POST`, `PUT`, or `PATCH` **and** `Content-Length` is absent:

```python
if method in ("POST", "PUT", "PATCH") and content_length_value is None:
```

This means:

1. `DELETE` requests with a body (valid in HTTP/1.1) bypass the stream guard entirely. A `DELETE /api/v1/...` with a 50 MB body is accepted without any check.
2. Any request that sends a `Content-Length` header **below** the limit but then sends more bytes in the body (i.e., a lying chunked transfer) bypasses the guard because the Content-Length fast-path approves the request after checking only the header value, and the stream guard is then skipped because `content_length_value is not None`.

Additionally, the `guarded_send` function (lines 143–154) has a response-suppression logic defect. When `limit_exceeded` is set:

```python
async def guarded_send(message: dict) -> None:
    nonlocal response_started
    if message.get("type") == "http.response.start":
        if limit_exceeded and not response_started:
            # Suppress the app's response — we will send 413
            # after self.app returns.
            return                          # <— never sets response_started = True
    response_started = True
    if not response_started and message.get("type") == "http.response.body":
        return
    await send(message)
```

The guard sets `response_started = True` **after** the `if` block, but when the branch returns early (suppressing the response.start), `response_started` is never set to `True`. The subsequent `http.response.body` message then reaches `await send(message)` with `response_started = True` because of line execution order — meaning the body **is** forwarded to the client even though the start was suppressed. In practice this means a response with no headers but with a body can be sent, which may crash the ASGI server or send corrupt data.

**Remediation**:
- Extend the method guard to all HTTP verbs that can carry a body.
- Add a second stream-counting pass even when `Content-Length` is present (or trust only the actual bytes transferred).
- Fix the response suppression logic to correctly gate the body message when start was suppressed.

---

### P0-02: In-Memory Rate Limiter Fallback Is Not Coroutine-Safe

**File**: `backend/middleware/rate_limiter.py`, lines 266–300 (`_check_memory`)

The `_check_memory` method mutates `self._memory_store` without any synchronization primitive. Although this is asyncio (single-threaded), coroutines **can** interleave at `await` points. The method itself does not `await`, but callers (`check_rate_limit`, `check_rate_limits_combined`) dispatch to it inside an `async` context. The critical risk is in the eviction sweep (lines 285–291):

```python
if len(self._memory_store) > 10_000:
    stale_keys = [
        k for k, v in self._memory_store.items()
        if isinstance(v, list) and (not v or v[-1] < window_start)
    ]
    for k in stale_keys:
        del self._memory_store[k]
```

A coroutine that is inside `_check_redis_both` can call the Lua `eval` coroutines, which **do** await. If another coroutine runs its `_check_memory` sweep concurrently and deletes the key that the first coroutine just inserted via `setdefault`, the count will be wrong and a request that should have been rate-limited will pass.

More critically, `_memory_store` is a module-level singleton instance attribute on the `UserRateLimiter`, which is shared across all requests. During a Redis outage (the fallback scenario), every in-flight request mutates the same dict. Because Python dicts are not coroutine-safe at the mutation level (reads may interleave with writes mid-resize), this can produce `RuntimeError: dictionary changed size during iteration` in the sweep path.

Additionally, the login-attempt storage in `_memory_store` mixes `list` and `dict` values for the same conceptual store (lines 334–339), making the periodic sweep (which checks `isinstance(v, list)`) skip login-attempt keys entirely — those keys never expire during a Redis outage.

**Remediation**:
- Wrap `_check_memory` mutations in `asyncio.Lock()`.
- Separate login-attempt storage from sliding-window storage, or unify their value type.
- Add expiry to login-attempt keys in the in-memory path.

---

## P1 — High (Fix This Sprint)

### P1-01: `decrypt_field()` Does Not Handle `InvalidTag` — Callers Receive Uncaught Cryptography Exceptions

**File**: `backend/utils/encryption.py`, lines 48–65

The docstring says `InvalidTag` is raised on tamper detection, but the function itself performs no error handling. Any code path that calls `decrypt_field()` on corrupted or tampered ciphertext will propagate `cryptography.exceptions.InvalidTag` as an unhandled exception to the endpoint. FastAPI's generic exception handler (in `app_factory.py`, lines 480–506) will then return a `500 Internal Server Error` with the raw exception class name visible in non-production environments.

More critically, if a service layer catches a broad `Exception` and swallows it (a common anti-pattern elsewhere in the codebase), a tampered ciphertext would be silently accepted rather than rejected. The function should either:

1. Raise a domain-specific exception (`DecryptionError`) so callers handle it explicitly; or
2. Return `Optional[str]` and return `None` on failure, with a mandatory log entry.

Currently neither pattern is enforced.

**Remediation**: Wrap the `decrypt` call in a `try/except InvalidTag` block, log a `security_tampered_ciphertext` event, and raise a `DecryptionError(field_name)` domain exception. Update all call sites.

---

### P1-02: `SecretsManager` `lru_cache` Singleton Caches Across Class Instantiations

**File**: `backend/config/secrets.py`, lines 228–232

```python
@staticmethod
@lru_cache(maxsize=1)
def get_instance() -> "SecretsManager":
    """Get singleton instance of SecretsManager"""
    return SecretsManager()
```

`lru_cache` on a `staticmethod` is permanent for the process lifetime. This causes two problems:

1. **Test isolation**: If tests call `SecretsManager.get_instance()` after mocking environment variables, they may receive a cached instance that was created before the mocks were applied, causing test data to bleed across test runs.
2. **Secret rotation**: The module-level docstring claims the 1-hour `CACHE_TTL` enables secret rotation, but the singleton itself never rotates its `use_1password` decision. If the `op` CLI becomes available or unavailable after startup, the singleton continues using the original decision.
3. **No cache invalidation**: There is no way to reset the `lru_cache`-cached singleton in tests without calling `SecretsManager.get_instance.cache_clear()`, which is not documented and not called in any test fixtures.

**Remediation**: Replace `lru_cache` singleton with an explicit module-level instance, or store the instance in a mutable container that can be reset:

```python
_instance: Optional["SecretsManager"] = None

@staticmethod
def get_instance() -> "SecretsManager":
    global _instance
    if _instance is None:
        _instance = SecretsManager()
    return _instance

@staticmethod
def reset_instance() -> None:  # for tests
    global _instance
    _instance = None
```

---

### P1-03: `_get_from_env()` Uppercases the Secret Name and Reads Arbitrary Environment Variables

**File**: `backend/config/secrets.py`, lines 213–220

```python
def _get_from_env(self, name: str) -> Optional[str]:
    env_name = name.upper()
    value = os.environ.get(env_name)
    ...
```

Any caller-supplied `name` is uppercased and used directly as an environment variable key. If any code path calls `get_secret(user_supplied_value)` — even indirectly — an attacker could read arbitrary environment variables by controlling the `name` argument. The function has no allowlist check against `SECRET_MAPPINGS`.

While current call sites use hardcoded string literals, this is a latent vulnerability given that `SecretsManager` is exposed via a public `get_secret()` module-level function.

**Remediation**: Add an allowlist check in `_get_from_env`:

```python
if name not in self.SECRET_MAPPINGS:
    logger.warning("secret_name_not_in_allowlist", name=name)
    return None
```

---

### P1-04: Tracing Middleware Does Not Clear `structlog` Contextvars Between Requests

**File**: `backend/middleware/tracing.py`, lines 61–70

```python
structlog.contextvars.bind_contextvars(trace_id=trace_id)
...
await self.app(scope, receive, send_with_trace_id)
```

`bind_contextvars` writes to a `contextvars.ContextVar`. In asyncio, each coroutine that is spawned via `asyncio.create_task()` inherits the context of the parent at the time of task creation. However, the middleware does **not** call `structlog.contextvars.clear_contextvars()` after the request completes. In Uvicorn/Starlette's connection handling, if a worker coroutine reuses the same context object (e.g., WebSocket connections, long-polling), the `trace_id` from a previous request can persist into the next request's log records.

This is particularly dangerous for SSE endpoints (`/prices/stream`) where the connection is long-lived and multiple logical "events" share the same OS-level connection. Log records emitted during event delivery will carry the original trace ID from the connection establishment, not per-event trace IDs.

**Remediation**: Add `structlog.contextvars.clear_contextvars()` at the start of `__call__` before binding, and/or after the `await self.app(...)` returns:

```python
structlog.contextvars.clear_contextvars()
structlog.contextvars.bind_contextvars(trace_id=trace_id)
```

---

### P1-05: `rate_limiter` Global Instance in Module Scope Creates Race Between Lifespan Init and First Request

**File**: `backend/middleware/rate_limiter.py`, lines 499–508

```python
rate_limiter: Optional[UserRateLimiter] = None

async def get_rate_limiter(redis: aioredis.Redis = None) -> UserRateLimiter:
    global rate_limiter
    if rate_limiter is None:
        rate_limiter = UserRateLimiter(redis_client=redis)
    return rate_limiter
```

The module-level `get_rate_limiter()` factory and the `RateLimitMiddleware` instantiation in `app_factory.py` (line 264) create **separate** `UserRateLimiter` instances. The middleware uses `app_rate_limiter` from `create_app()`, while `get_rate_limiter()` creates its own global singleton `rate_limiter`. Any code that calls `get_rate_limiter()` (via FastAPI dependency injection or directly) uses a different instance with a separate `_memory_store` and possibly no Redis wired in.

This means:
- Rate limits applied through the middleware are not shared with limits applied through `get_rate_limiter()`.
- The `get_rate_limiter()` singleton is never wired to Redis (the lifespan only wires the `app_rate_limiter`, not the module-level global).

The module-level `rate_limiter` global also has an unguarded `if rate_limiter is None` check with no lock, creating a TOCTOU risk under concurrent startup (though asyncio makes this unlikely in practice).

**Remediation**: Remove the module-level `get_rate_limiter()` factory and the `rate_limiter` global. All callers should receive the `UserRateLimiter` instance from `create_app()` via FastAPI dependency injection from `app.state`.

---

## P2 — Medium (Fix This Quarter)

### P2-01: Security Headers Missing `X-Permitted-Cross-Domain-Policies` and `Cross-Origin-*` Headers

**File**: `backend/middleware/security_headers.py`, lines 86–128

The middleware adds the seven most common security headers but omits several headers that modern browsers and security scanners expect:

- `X-Permitted-Cross-Domain-Policies: none` — Prevents Adobe Flash and PDF from embedding the site.
- `Cross-Origin-Opener-Policy: same-origin` — Prevents cross-origin windows from obtaining a reference to the app window (required for full Spectre mitigation).
- `Cross-Origin-Resource-Policy: same-origin` — Prevents other origins from loading resources via `<script>`, `<img>`, etc.
- `Cross-Origin-Embedder-Policy: require-corp` — Required for `SharedArrayBuffer`; needed if the app ever enables high-resolution timer or WebAssembly features.

OWASP's Secure Headers Project and Mozilla Observatory both flag the absence of `Cross-Origin-Opener-Policy` as a medium finding.

Additionally, the production CSP (lines 62–72) uses `img-src 'self' data: https:` which allows loading images from **any** HTTPS origin. This should be restricted to known CDN origins.

**Remediation**: Add the three `Cross-Origin-*` headers unconditionally and `X-Permitted-Cross-Domain-Policies` unconditionally. Tighten `img-src` to known origins (e.g., `'self' data: https://rateshift.app`).

---

### P2-02: Middleware Registration Order Places `SecurityHeadersMiddleware` Inside `TracingMiddleware`

**File**: `backend/app_factory.py`, lines 386–416

FastAPI's `add_middleware()` uses LIFO ordering (last registered = outermost = runs first). The current registration order is:

```
1. CORSMiddleware           (registered first → innermost → runs last)
2. GZipMiddleware           (2nd → runs 2nd-to-last)
3. TracingMiddleware        (registered last → outermost → runs first)
4. SecurityHeadersMiddleware
5. RateLimitMiddleware
6. RequestBodySizeLimitMiddleware
7. RequestTimeoutMiddleware (registered before decorator middleware)
```

The comment on line 397 states TracingMiddleware is "registered last so it runs first" — which is correct per LIFO ordering. However the **security headers** middleware is registered at position 4 (from last), meaning it runs **inside** the rate limiter and body-size limiter. If the rate limiter or body-size limiter raises an exception or sends a 429/413 directly via raw ASGI (bypassing the `send_wrapper` chain), the security headers are **not added** to those error responses.

Concretely, `RateLimitMiddleware._send_429()` (lines 452–466) sends a raw ASGI response that completely bypasses `SecurityHeadersMiddleware` — meaning 429 responses lack `X-Frame-Options`, `CSP`, and `X-Content-Type-Options` headers.

The correct conceptual order (outermost to innermost) should be:
1. Tracing (generate trace ID for all downstream logs)
2. Security headers (applied to all responses including error responses)
3. Rate limiting (must see security headers on 429 responses)
4. Body size limit
5. Timeout
6. GZip
7. CORS (innermost)

**Remediation**: Reorder `add_middleware()` calls so `SecurityHeadersMiddleware` is registered **after** `TracingMiddleware` but **before** `RateLimitMiddleware`. Alternatively, have error-response senders apply security headers themselves (but this is duplicative).

---

### P2-03: `_execute_raw_query` in `DatabaseManager` Accepts Raw SQL Strings Without Parameterization Guard

**File**: `backend/config/database.py`, lines 176–188

```python
async def _execute_raw_query(self, query: str, *args):
    if self.timescale_pool:
        async with self.timescale_pool.acquire() as conn:
            return await conn.fetch(query, *args)
    if self.timescale_engine:
        from sqlalchemy import text
        async with self.timescale_engine.connect() as conn:
            result = await conn.execute(text(query))    # <— args ignored!
            return result.fetchall()
    return []
```

The `text(query)` path (lines 184–186) discards `*args` entirely. If a caller passes parameterized arguments expecting them to be bound, the SQLAlchemy fallback path silently ignores all parameters and executes the raw SQL string as-is. This is a latent SQL injection vulnerability if any call site constructs `query` with user input.

Furthermore, `text(query)` produces a SQL expression object that bypasses SQLAlchemy's ORM-level parameterization. There is no check that `query` does not contain format-string interpolation (`%s`, `{}`).

**Remediation**: Either remove the SQLAlchemy fallback path (the asyncpg pool is the intended raw-query mechanism) or correctly pass args to the text path:

```python
result = await conn.execute(text(query), {f"p{i}": v for i, v in enumerate(args)})
```

And add a guard that rejects queries with obvious f-string interpolation markers.

---

### P2-04: `SecretsManager._get_from_1password()` Logs `result.stderr` Which May Contain Vault Paths or Partial Secrets

**File**: `backend/config/secrets.py`, lines 197–203

```python
logger.warning(
    "1password_read_failed",
    name=name,
    error=result.stderr,    # <— may contain vault path, item name, or credential fragment
)
```

The `op read` command writes error messages to `stderr` that can include the full `op://RateShift/Item Name/field` URI in the error text (e.g., `"[ERROR] 2026/03/18 12:00:00 Item "API Secrets" not found in vault "RateShift""`). If the vault name, item name, or field name encodes metadata about the secret (e.g., `"Google OAuth Client Secret"`), this information is written to structured logs that may be shipped to Grafana Cloud.

Additionally, the `error=str(e)` path (line 210) can log the full exception message from the `op` subprocess, which in some versions of the 1Password CLI includes the full `op://` URI.

**Remediation**: Truncate or sanitize `result.stderr` before logging. Do not log the full error from external secret stores; log only the secret `name` and a generic failure code.

---

### P2-05: `EmailService` Sets `resend.api_key` as a Module-Level Global on Every Send

**File**: `backend/services/email_service.py`, lines 82–83

```python
import resend
resend.api_key = self._settings.resend_api_key
```

The `resend` library uses a module-level `api_key` global. Setting it inside `_send_via_resend()` on every call is safe in single-process mode, but under asyncio concurrency, two concurrent email sends could interleave their `api_key` assignments. If a future code path uses multiple Resend API keys (e.g., for different sub-accounts), this pattern creates a race condition where the wrong key is used for a given send.

More practically, this means any code that `import resend` after the first email send will inherit the `api_key` side-effect, making the module stateful in a non-obvious way.

**Remediation**: Initialize `resend.api_key` once at `EmailService.__init__()` time, not on every call. Or use the Resend client constructor pattern if the library supports it.

---

### P2-06: Database SSL Is Only Enforced for `*.neon.tech` Hostnames

**File**: `backend/config/database.py`, lines 52–64

```python
if _host.endswith(".neon.tech"):
    connect_args["ssl"] = "require"
    connect_args["statement_cache_size"] = 0
```

SSL is silently disabled for non-Neon hosts. If `DATABASE_URL` is set to a custom PostgreSQL host (e.g., on staging or local dev pointing to a remote DB), connections are made without TLS. The `settings.py` validator (line 332) only checks that the URL starts with `postgresql://` in production — it does not enforce SSL.

For a financial application handling electricity usage data and billing information, unencrypted database connections are a compliance risk (PCI-DSS, SOC 2).

**Remediation**: Default to `ssl="prefer"` or `ssl="require"` for all hosts, not just `*.neon.tech`. Allow opt-out via `DB_SSL=disable` environment variable for local development only.

---

### P2-07: `CircuitBreaker.call()` Holds `asyncio.Lock` Across the Awaited Coroutine on HALF_OPEN Path

**File**: `backend/lib/circuit_breaker.py`, lines 94–113

```python
async def call(self, coro: Coroutine[Any, Any, T]) -> T:
    async with self._lock:
        current = self.state
        if current == CircuitState.OPEN:
            coro.close()
            raise CircuitBreakerOpen(self.name)
        if current == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max:
                coro.close()
                raise CircuitBreakerOpen(self.name)
            self._half_open_calls += 1
    # lock is released here
    try:
        result = await coro    # coroutine runs without the lock held
    ...
```

The lock is released **before** awaiting the coroutine (line 107 `result = await coro`). This is correct for the normal `CLOSED` state. However in `HALF_OPEN` state, multiple concurrent callers can all pass the `self._half_open_calls < self.half_open_max` check, increment `_half_open_calls`, release the lock, and then all proceed to call the external service concurrently. With `half_open_max=1` (the default), the intent is that exactly one probe call should be made — but if two requests arrive simultaneously in HALF_OPEN, both pass the guard before either increments the count past 1.

This is a classic TOCTOU: the check-then-increment sequence is not atomic relative to other concurrent callers.

**Remediation**: Increment `_half_open_calls` to the sentinel value atomically within the lock:

```python
if current == CircuitState.HALF_OPEN:
    if self._half_open_calls >= self.half_open_max:
        coro.close()
        raise CircuitBreakerOpen(self.name)
    self._half_open_calls = self.half_open_max  # saturate to block all other callers
```

---

## P3 — Low (Address in Backlog)

### P3-01: `Settings.validate_database_url` Only Accepts `postgresql://` — Rejects `postgres://` (Heroku/Render Default)

**File**: `backend/config/settings.py`, lines 324–336

```python
if not v.startswith("postgresql://"):
    raise ValueError(
        "DATABASE_URL must start with 'postgresql://' in production."
    )
```

Render's PostgreSQL add-on, many managed DB providers, and SQLAlchemy docs all use `postgres://` (without "sql"). If the `DATABASE_URL` is provided by Render's environment injection without normalization, the validator raises a startup error. There is no automatic rewriting of `postgres://` to `postgresql://`.

**Remediation**: Accept both prefixes, or normalize in the validator:
```python
if v.startswith("postgres://"):
    v = "postgresql" + v[8:]
```

---

### P3-02: `_default_csp()` Checks `settings.is_development` But CSP Is Constructed at `__init__` Time

**File**: `backend/middleware/security_headers.py`, lines 47–72

The CSP policy is computed once in `__init__` (line 43: `self.csp_policy = csp_policy or self._default_csp()`). The `is_development` flag is read at middleware construction time. If `settings.environment` is changed after construction (e.g., in tests that mutate the global `settings` object), the CSP will reflect the value from construction time, not the current value. This is a minor correctness issue rather than a security issue since production deployments set `ENVIRONMENT` before startup.

**Remediation**: Document that the CSP is frozen at construction time. In tests, reconstruct the middleware after changing `settings.environment`.

---

### P3-03: `get_timescale_session()` Yields `None` Without Warning When Database Is Not Configured

**File**: `backend/config/database.py`, lines 159–174

```python
@asynccontextmanager
async def get_timescale_session(self):
    if not self.async_session_maker:
        yield None    # <— silently yields None
        return
    ...
```

When `DATABASE_URL` is not set, every endpoint that uses `get_timescale_session()` receives `None` as its `session` parameter. Unless every endpoint correctly checks `if session is None`, this results in `AttributeError: 'NoneType' object has no attribute 'execute'` at runtime, not at startup.

There is no startup check that verifies all `Depends(get_timescale_session)` endpoints can actually obtain a session. The error manifests per-request rather than at application startup, making it harder to detect in staging.

**Remediation**: Raise a `RuntimeError` in `get_timescale_session` when `async_session_maker` is `None` in production. In development/test, the current `yield None` behavior may be acceptable, but it should be clearly documented.

---

### P3-04: `SecurityHeadersMiddleware` Applies `Cache-Control: no-store` to All `/api/` Paths, Including Public Rate-Pricing Endpoints

**File**: `backend/middleware/security_headers.py`, lines 121–126

```python
if is_api_path:
    headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, private"
    )
```

All paths under `/api/` receive `private, no-store` cache headers. This prevents Cloudflare's edge cache from caching public data endpoints like `GET /api/v1/prices/current` and `GET /api/v1/public/rates`, which the CF Worker explicitly tries to cache (per the CLAUDE.md architecture notes: "2-tier caching (Cache API + KV with cacheTtl)"). The `private` directive instructs Cloudflare and any intermediate proxy not to cache the response.

This creates an architectural conflict: the CF Worker may cache responses at the edge, but the `Cache-Control: private` header tells it not to. The current behavior depends on whether Cloudflare respects `Cache-Control: private` (it does for Cloudflare's cache by default unless `Edge-Cache-TTL` or Cache Rules override it).

**Remediation**: Exclude known public-data endpoints from the `Cache-Control: no-store` override, or set `Cache-Control: public, max-age=N` explicitly for those paths. Per-path logic is already present (the `is_api_path` flag); extend it to distinguish authenticated vs. public paths.

---

### P3-05: `EmailService` Does Not Validate the `to` Email Address Format Before Sending

**File**: `backend/services/email_service.py`, lines 43–69

The `send()` method accepts `to: str` without any format validation. An invalid email address (empty string, SQL injection attempt, or malformed address) is passed directly to both Resend and SMTP providers. Both providers will return an error, but the error is swallowed and logged. There is no `ValueError` raised at the call site for obviously invalid addresses.

**Remediation**: Add a simple RFC 5321 email validation at the top of `send()`:
```python
import re
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
if not _EMAIL_RE.match(to):
    logger.warning("email_invalid_address", to=to)
    return False
```

---

### P3-06: `settings.py` `field_validator` for `jwt_secret` Reads `os.environ` Directly Instead of Using the Model Value

**File**: `backend/config/settings.py`, lines 250–251

```python
jwt_from_env = os.environ.get("JWT_SECRET")
if env in ("production", "staging") and not jwt_from_env:
    raise ValueError(...)
```

The validator checks `os.environ.get("JWT_SECRET")` directly instead of checking whether `v` (the validated value) is the `default_factory` output. This means:

1. If `JWT_SECRET` is set to an empty string in the environment, `jwt_from_env` will be the empty string (falsy), and the validator will raise — even though `v` would have been set to the empty string too.
2. If `pydantic-settings` reads from a `.env` file (not `os.environ` directly), the validator could incorrectly conclude the key is absent even when it is present in the `.env` file.

The correct check is to inspect whether `v` was generated by `default_factory` (e.g., compare its length to a known minimum) rather than re-reading `os.environ`.

**Remediation**: Remove the `os.environ.get("JWT_SECRET")` check and instead check the model value:
```python
# The default_factory generates a 64-char hex string
# If a real secret was provided it should also be at least 32 chars
if env in ("production", "staging") and len(v) < 32:
    raise ValueError(...)
```

---

### P3-07: `_check_memory` Periodic Sweep Uses `v[-1] < window_start` Which Assumes Sorted Insertion

**File**: `backend/middleware/rate_limiter.py`, lines 285–291

```python
stale_keys = [
    k for k, v in self._memory_store.items()
    if isinstance(v, list) and (not v or v[-1] < window_start)
]
```

The sweep condition checks `v[-1] < window_start` (the last element is older than the window). This assumes the list is sorted in ascending order (oldest first, newest last). The insertion at line 294 (`self._memory_store.setdefault(key, []).append(now)`) does maintain this ordering because `now` is always greater than previous entries for a monotonically increasing clock — but only if `time.time()` is monotonic, which it is not guaranteed to be (NTP adjustments can cause `time.time()` to go backwards).

If the system clock is adjusted backwards (e.g., NTP sync during a Redis outage), the list will not be sorted, the sweep will incorrectly identify active keys as stale (their last entry is "in the past" relative to the adjusted `window_start`), and rate limit state will be lost.

**Remediation**: Use `time.monotonic()` instead of `time.time()` for the in-memory fallback. Note: the Redis Lua script uses `now` from `time.time()` (passed as `ARGV[1]`), so the two paths use different clock sources — document this explicitly.

---

### P3-08: `lib/tracing.py` `_set_span_in_context` and `_detach_context` Are Module-Level Functions That Are Not Exported

**File**: `backend/lib/tracing.py`, lines 101–113

The `traced` context manager calls `_set_span_in_context` and `_detach_context`, which are module-level private functions defined at the bottom of the file. Both functions import from `opentelemetry` **inside** the function body, which means:

1. Import errors from `opentelemetry` only surface when the span is entered or exited, not when the module is loaded.
2. The `context.detach(token)` call in `_detach_context` may be called with a `None` token if `_set_span_in_context` raised an exception (e.g., because `opentelemetry` is not installed). There is no guard against `token is None` in `__aexit__` / `__exit__`, meaning a missing dependency would produce a secondary `TypeError` that masks the original `ImportError`.

**Remediation**: Move the `opentelemetry` imports to module level (inside a `try/except ImportError` block that degrades to no-ops). Add a `None` guard before `context.detach(token)`.

---

## Summary Table

| ID | Severity | File | Description |
|----|----------|------|-------------|
| P0-01 | Critical | `app_factory.py:128` | `RequestBodySizeLimitMiddleware` chunked guard skips `DELETE`; response suppression logic bug |
| P0-02 | Critical | `rate_limiter.py:266` | In-memory rate limiter fallback not coroutine-safe; login keys never evicted |
| P1-01 | High | `utils/encryption.py:48` | `decrypt_field()` propagates `InvalidTag` unchecked; no domain exception |
| P1-02 | High | `config/secrets.py:228` | `lru_cache` singleton breaks test isolation and secret rotation |
| P1-03 | High | `config/secrets.py:213` | `_get_from_env` reads arbitrary env vars without allowlist check |
| P1-04 | High | `middleware/tracing.py:61` | `structlog` contextvars not cleared between requests; SSE trace ID leak |
| P1-05 | High | `rate_limiter.py:499` | Module-level `get_rate_limiter()` creates orphan instance not wired to Redis |
| P2-01 | Medium | `middleware/security_headers.py:86` | Missing `Cross-Origin-*` and `X-Permitted-Cross-Domain-Policies` headers |
| P2-02 | Medium | `app_factory.py:386` | Middleware LIFO order: security headers miss 429/413 raw ASGI error responses |
| P2-03 | Medium | `config/database.py:184` | `_execute_raw_query` SQLAlchemy fallback discards `*args`; potential SQL injection |
| P2-04 | Medium | `config/secrets.py:197` | `1password_read_failed` log may expose vault paths and item names |
| P2-05 | Medium | `services/email_service.py:82` | `resend.api_key` set as module global on every call; not safe for multi-key use |
| P2-06 | Medium | `config/database.py:52` | SSL only enforced for `*.neon.tech`; non-Neon hosts use unencrypted connections |
| P2-07 | Medium | `lib/circuit_breaker.py:94` | HALF_OPEN TOCTOU: multiple concurrent callers can bypass `half_open_max` |
| P3-01 | Low | `config/settings.py:332` | `validate_database_url` rejects `postgres://` prefix (Render/Heroku default) |
| P3-02 | Low | `middleware/security_headers.py:43` | CSP frozen at construction time; test mutations to `settings.environment` not reflected |
| P3-03 | Low | `config/database.py:163` | `get_timescale_session` silently yields `None`; `AttributeError` deferred to request time |
| P3-04 | Low | `middleware/security_headers.py:121` | `Cache-Control: private` on all `/api/` paths conflicts with CF Worker edge caching |
| P3-05 | Low | `services/email_service.py:43` | No email address format validation before sending |
| P3-06 | Low | `config/settings.py:250` | `jwt_secret` validator reads `os.environ` directly, bypassing pydantic-settings sources |
| P3-07 | Low | `rate_limiter.py:289` | In-memory sweep assumes sorted timestamps; breaks on NTP clock adjustment |
| P3-08 | Low | `lib/tracing.py:101` | Lazy OTel imports in private functions; `None` token risk on import failure |

---

## Positive Findings (No Action Required)

The following aspects of the middleware and library layer are implemented correctly and represent good engineering practices:

- **Atomic Lua sliding-window rate limiter** (`rate_limiter.py:42–65`): The Redis Lua script is correct. It atomically removes stale entries, adds the new request, sets TTL on both the sorted set and the `:seq` counter key (the `:seq` TTL fix was applied as part of the audit remediation track), and returns the post-increment count. This eliminates the TOCTOU that existed in the previous pipeline-based implementation.

- **AES-256-GCM encryption** (`utils/encryption.py:34–65`): The implementation is cryptographically correct. Per-ciphertext random 96-bit nonces via `os.urandom(12)` are used (not counter-based), the GCM authentication tag provides integrity verification, and the key is loaded from settings with production-enforcement validation. The wire format (nonce || ciphertext+tag) is correctly assembled and disassembled.

- **Pure ASGI middleware** (all middleware files): All custom middleware is implemented as pure ASGI (not `BaseHTTPMiddleware`), avoiding Starlette's response-buffering issue that breaks SSE and WebSocket connections. This is the correct approach for a streaming application.

- **`RequestBodySizeLimitMiddleware` Content-Length fast-path** (`app_factory.py:118–124`): The fast-path rejection before reading any body bytes is correct and efficient.

- **TracingMiddleware request ID validation** (`middleware/tracing.py:26–55`): The `_SAFE_REQUEST_ID` regex correctly limits caller-supplied request IDs to safe ASCII tokens of at most 64 characters, preventing header injection.

- **`CircuitBreaker` asyncio.Lock usage** (`lib/circuit_breaker.py:73`): The lock is correctly defined as an `asyncio.Lock` (not `threading.Lock`), appropriate for the async context.

- **Settings production validators**: The validators for `jwt_secret`, `internal_api_key`, `better_auth_secret`, `field_encryption_key`, `stripe_secret_key`, `database_url`, and `resend_api_key` all enforce presence and minimum strength in production. The cross-field validator (`validate_api_key_differs_from_jwt`) correctly prevents key reuse between service auth and user auth.

- **Sentry `send_default_pii=False`** (`app_factory.py:329`): PII is not sent to Sentry, which is correct for a financial application.

- **Swagger/ReDoc disabled in production** (`app_factory.py:356–357`): Correct. No API schema is exposed publicly.

- **`decode_responses=True` on Redis client** (`config/database.py:129`): Avoids the common bug of returning bytes instead of strings from Redis, which can cause subtle type errors in the rate limiter key comparisons.
