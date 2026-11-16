# Audit Report: Backend Middleware & Lib
**Date:** 2026-03-19
**Scope:** Middleware pipeline, shared utilities, config, compliance, observability
**Files Reviewed:**
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/__init__.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/security_headers.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/tracing.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/lib/__init__.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/lib/circuit_breaker.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/lib/tracing.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/utils/__init__.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/utils/encryption.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/__init__.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/database.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/settings.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/secrets.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/__init__.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/gdpr.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/repositories.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/observability.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/app_factory.py` (middleware wiring)
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/auth/password.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/dependencies.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/gunicorn_config.py`

***

## P0 -- Critical (Fix Immediately)

### P0-1: Structlog contextvars never cleared between requests -- trace_id leaks across requests
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/tracing.py`, line 60
**Impact:** Security / Data Integrity

`TracingMiddleware` binds `trace_id` to `structlog.contextvars` via `bind_contextvars(trace_id=trace_id)` at line 60, but never calls `clear_contextvars()` or `unbind_contextvars("trace_id")` after the request completes. A search of the entire backend confirms no call to `clear_contextvars` or `unbind_contextvars` exists anywhere.

In asyncio-based servers (uvicorn), context variables are tied to the `Task`. While `asyncio.Task` objects do inherit context on creation, there are scenarios (middleware errors, exception paths before the `send_with_trace_id` wrapper fires, or connection reuse in HTTP/2) where a stale `trace_id` from a previous request could bleed into logs for a subsequent request handled by the same coroutine context, producing misleading log correlation and potentially exposing one user's trace_id in another user's log entries.

**Recommendation:** Wrap the `self.app(scope, receive, send_with_trace_id)` call in a `try/finally` that calls `structlog.contextvars.unbind_contextvars("trace_id")` or `structlog.contextvars.clear_contextvars()`:
```python
try:
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
    await self.app(scope, receive, send_with_trace_id)
finally:
    structlog.contextvars.unbind_contextvars("trace_id")
```

---

### P0-2: DeletionLogORM FK constraint SET NULL on users.id conflicts with GDPR deletion flow
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/repositories.py`, line 50-52
**Impact:** Data Integrity / GDPR Compliance

The `DeletionLogORM.user_id` column is defined as:
```python
mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=False)
```

This has two conflicting constraints:
1. `ondelete="SET NULL"` -- instructs the DB to set `user_id` to `NULL` when the referenced user is deleted.
2. `nullable=False` -- forbids `NULL` values in this column.

When `delete_user_data()` in `gdpr.py` deletes the user at line 938 (`DELETE FROM users WHERE id = :uid`) and then tries to insert the deletion log at line 981-1001 in a subsequent commit, the first commit will trigger the FK SET NULL constraint *before* the log is inserted. However, because `nullable=False` conflicts with SET NULL, the database will raise a constraint violation error if CASCADE/SET NULL is triggered on any existing deletion_log rows for that user_id.

In the current GDPR flow this is somewhat mitigated because the deletion log INSERT happens *after* the user DELETE commit (separate transaction), but the ORM declaration is contradictory and will fail if any pre-existing deletion_log rows exist for the user.

**Recommendation:** Change to either:
- `ondelete="CASCADE"` if deletion logs should be purged with the user (unlikely -- audit records should persist), or
- `nullable=True` to allow SET NULL to work correctly, or
- Remove the FK entirely since deletion_logs are audit records that must survive user deletion.

---

### P0-3: GDPR deletion log persisted in a separate transaction -- can be lost on crash
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/gdpr.py`, lines 944 and 981-1002
**Impact:** GDPR Compliance / Audit Trail

The `delete_user_data()` method commits the user deletion at line 944, then writes the `deletion_log` in a *separate* `commit()` at line 1002. If the application crashes between these two commits (or the second commit fails for any reason), the user's data is deleted but no audit record exists. GDPR Article 17 requires demonstrable evidence that deletion was performed.

The error at line 1003-1008 catches the exception and logs it but does not raise -- meaning the deletion succeeds from the caller's perspective even though the legally-required audit trail was not persisted.

**Recommendation:** Either:
- Include the deletion log INSERT in the same atomic transaction as the data deletion (restructure to avoid the FK issue in P0-2 first), or
- Use a separate audit table without an FK to `users`, and insert it within the same transaction, or
- At minimum, raise the exception so the caller knows the audit trail failed.

***

## P1 -- High (Fix This Sprint)

### P1-1: CORS missing `expose_headers` -- frontend cannot read rate-limit or request-ID headers
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/app_factory.py`, lines 388-400
**Impact:** Functionality

The `CORSMiddleware` configuration does not include `expose_headers`. By CORS specification, browsers will only expose "simple response headers" (Cache-Control, Content-Language, Content-Type, Expires, Last-Modified, Pragma) to JavaScript code. The following custom headers set by the middleware are invisible to the frontend:

- `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (set by `RateLimitMiddleware` at lines 449-451 of `app_factory.py`)
- `X-Request-ID` (set by `TracingMiddleware` at line 65 of `tracing.py`)
- `X-Process-Time` (set in development at line 438 of `app_factory.py`)

**Recommendation:** Add `expose_headers` to the CORS configuration:
```python
expose_headers=[
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
    "X-Request-ID",
    "X-Process-Time",
    "Retry-After",
],
```

---

### P1-2: Rate limiter identifies users by bearer token hash -- same user gets different identifiers across sessions
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py`, lines 480-484
**Impact:** Rate Limiting Effectiveness

The `_get_identifier` method hashes the bearer token to derive the rate-limit key:
```python
token_hash = hashlib.sha256(auth[7:].encode()).hexdigest()[:16]
return f"user:{token_hash}"
```

When a user refreshes their session (new token), their rate-limit counter resets. This means:
- A user can bypass per-minute and per-hour limits by simply refreshing their auth token.
- Rate limits effectively only apply within a single session token's lifetime.

For most authenticated endpoints, the actual user ID should be extracted from the token (e.g., by decoding the Better Auth session token) rather than hashing the raw token string.

**Recommendation:** Decode the session token to extract the user_id and use that as the rate-limit key, or move the rate-limit identifier resolution to after auth middleware resolution and use `request.state.user_id`.

---

### P1-3: In-memory rate limiter fallback unbounded under high concurrent load without Redis
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py`, lines 270-305
**Impact:** Availability / DoS

The in-memory fallback `_check_memory` stores individual timestamps as list items. Under high load without Redis, a single IP doing 10,000 requests/second will accumulate 10,000 float entries per key before the sweep at line 289 triggers (only when total keys exceed 10,000, not total entries).

Additionally, the sweep only removes keys that are *entirely* stale (line 293: `not v or v[-1] < window_start`). Active-but-large lists are never pruned. For a sustained attack, a single key could accumulate millions of entries consuming significant memory.

**Recommendation:** Add a per-key entry count cap (e.g., `2 * limit`) to prevent individual key bloat:
```python
if len(self._memory_store[key]) > limit * 2:
    self._memory_store[key] = self._memory_store[key][-limit:]
```

---

### P1-4: `anonymize_ip()` does not handle IPv6 addresses
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/gdpr.py`, lines 100-114
**Impact:** GDPR Compliance

The `anonymize_ip` function only handles IPv4 (splits on `.`, checks for 4 parts). For any IPv6 address (increasingly common), it falls through to the else branch and returns `"0.0.0.0"`, which destroys the partial geographic information that could be legitimately retained. More importantly, if this function is used for log anonymization rather than deletion, returning a fixed value for all IPv6 addresses creates a collision that could correlate otherwise unrelated records.

**Recommendation:** Add IPv6 handling by zeroing the last 80 bits (keeping the /48 prefix):
```python
import ipaddress
def anonymize_ip(ip_address: str) -> str:
    try:
        addr = ipaddress.ip_address(ip_address)
        if isinstance(addr, ipaddress.IPv4Address):
            parts = ip_address.split(".")
            parts[-1] = "0"
            return ".".join(parts)
        else:
            # Zero last 80 bits (keep /48)
            network = ipaddress.IPv6Network(f"{ip_address}/48", strict=False)
            return str(network.network_address)
    except ValueError:
        return "0.0.0.0"
```

---

### P1-5: Login lockout identifier logged with raw email/IP
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py`, lines 349-354
**Impact:** PII in Logs

When account lockout occurs, the raw `identifier` (which may be the user's email address) is logged:
```python
logger.warning(
    "account_locked_out",
    identifier=identifier,
    ...
)
```

If the caller passes an email as the identifier (as suggested by the docstring at line 309: "User email or IP"), this constitutes logging PII. In a production JSON log pipeline, email addresses in structured log fields are a GDPR concern and a data exposure risk if logs are shipped to third-party services.

**Recommendation:** Hash or mask the identifier before logging:
```python
masked = identifier if identifier.startswith("ip:") else f"user:***{identifier[-4:]}"
logger.warning("account_locked_out", identifier=masked, ...)
```

---

### P1-6: Encryption module uses no AAD (Associated Authenticated Data) -- ciphertext is context-free
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/utils/encryption.py`, lines 44 and 65
**Impact:** Security

Both `encrypt_field` and `decrypt_field` pass `None` as the AAD parameter to AESGCM:
```python
ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
```

Without AAD, an encrypted account number from one database row can be copy-pasted into another row and will decrypt successfully. An attacker with write access to the database (but not the key) could swap encrypted values between users without detection.

**Recommendation:** Use the record's primary key (or user_id + field name) as AAD:
```python
def encrypt_field(plaintext: str, context: str = "") -> bytes:
    ...
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), context.encode("utf-8") or None)
    ...
```

***

## P2 -- Medium (Fix Soon)

### P2-1: Middleware ordering places SecurityHeaders inside RateLimit -- 429 responses lack security headers
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/app_factory.py`, lines 388-424
**Impact:** Security Headers Incomplete

The middleware registration order in `app_factory.py` is (LIFO -- last registered runs first inbound):
1. `RequestTimeoutMiddleware` (outermost)
2. `RequestBodySizeLimitMiddleware`
3. `RateLimitMiddleware`
4. `SecurityHeadersMiddleware`
5. `TracingMiddleware`
6. `GZipMiddleware`
7. `CORSMiddleware` (innermost)

When `RateLimitMiddleware` returns a 429 response directly at line 462-473 via `_send_429()`, it bypasses `SecurityHeadersMiddleware` entirely because security headers are registered *after* (inside) rate limiting. This means 429 responses lack `X-Frame-Options`, `X-Content-Type-Options`, `Content-Security-Policy`, `Strict-Transport-Security`, and `Referrer-Policy`.

Similarly, 413 responses from `RequestBodySizeLimitMiddleware` and 504 from `RequestTimeoutMiddleware` also lack security headers.

**Recommendation:** Move `SecurityHeadersMiddleware` to be registered *after* (i.e., outermost) `RequestTimeoutMiddleware`, or have the early-return responses (`_send_429`, `_send_413`, 504) include security headers inline.

---

### P2-2: Security headers CSP missing `upgrade-insecure-requests` directive in production
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/security_headers.py`, lines 60-72
**Impact:** Security

The production CSP policy does not include `upgrade-insecure-requests`. While HSTS handles this for subsequent visits, the first visit from a user who types `http://` will not be upgraded by CSP. Adding this directive provides defense-in-depth alongside HSTS.

**Recommendation:** Add `upgrade-insecure-requests` to the production CSP string.

---

### P2-3: Circuit breaker `state` property has a TOCTOU race with the lock-protected `call()` method
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/lib/circuit_breaker.py`, lines 80-86 and 95-106
**Impact:** Correctness

The `state` property at line 80 reads `_state` and `_last_failure_time` without acquiring `_lock`. Meanwhile, `call()` at line 95 acquires the lock and then calls `self.state` inside the lock -- but the property itself does not hold the lock while reading the fields. This creates a window where another coroutine could modify `_state` or `_last_failure_time` between the property's check and the caller's use of the result.

In practice, the `call()` method does acquire the lock before checking `self.state`, which mitigates the race for the primary usage path. However, any external caller reading `breaker.state` for monitoring or logging purposes could get an inconsistent view.

**Recommendation:** Make the state property private (`_get_state_unlocked`) and only call it from within lock-protected methods. Expose a public `async def get_state()` that acquires the lock.

---

### P2-4: `_execute_raw_query` accepts arbitrary SQL string -- potential injection vector
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/database.py`, lines 176-189
**Impact:** Security (Latent)

`_execute_raw_query(self, query: str, *args)` accepts a raw SQL string. While current callers only pass `"SELECT 1"`, this method is public (no underscore prefix in the class API convention -- it uses a single underscore which in Python is merely a convention, not enforced access control). Any future caller could pass unsanitized input.

The asyncpg path at line 180 uses parameterized queries (`conn.fetch(query, *args)`), but the SQLAlchemy fallback at line 186 uses `text(query)` without parameter binding for `*args`, meaning additional arguments are silently ignored when falling through to the SQLAlchemy path.

**Recommendation:**
- Rename to `__execute_raw_query` (name-mangled) or add a docstring warning.
- Fix the SQLAlchemy fallback to pass `*args` as bind parameters.

---

### P2-5: Redis `decode_responses=True` conflicts with rate limiter Lua script expectations
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/database.py`, line 129; `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py`, line 162
**Impact:** Correctness (Latent)

The Redis client is initialized with `decode_responses=True` (database.py line 129), which means all Redis responses are automatically decoded to strings. However, the rate limiter's `_check_redis` method at line 170 calls `int(request_count)` on the Lua script return value. With `decode_responses=True`, the Lua script's integer return value will arrive as a string, which `int()` can handle. But `ZADD` at line 51 in the Lua script uses `tostring(now)` for the member, which when combined with string-mode responses could cause subtle type mismatches if Redis return types change between versions.

Additionally, the `record_login_attempt` method at line 337 uses a pipeline with `pipe.incr(key)` whose result at line 338 (`attempts = results[0]`) will be a string `"1"` not integer `1` due to `decode_responses=True`. The comparison at line 346 (`attempts >= self.login_attempts`) compares a string to an integer, which in Python 3 raises `TypeError` for `>=` comparison.

**Recommendation:** Either:
- Remove `decode_responses=True` and handle decoding explicitly, or
- Add explicit `int()` cast at line 338: `attempts = int(results[0])`

---

### P2-6: Secrets cache values stored in plaintext in memory
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/secrets.py`, line 171
**Impact:** Security

The `SecretsManager._cache` dict stores secret values as plaintext strings in memory: `self._cache[name] = (value, time.monotonic())`. While all Python objects are in memory, this cache persists values for up to 1 hour (CACHE_TTL = 3600 seconds) even after they are no longer needed. A memory dump or debugger attachment could extract all cached secrets.

**Recommendation:** This is acceptable for most threat models, but for high-security deployments consider using `mmap`-backed memory that can be explicitly zeroed, or reducing the cache TTL to minimize the exposure window.

---

### P2-7: GDPR `withdraw_all_consents` fallback path is not atomic
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/gdpr.py`, lines 376-386
**Impact:** GDPR Compliance

When `db_session` is not available, the `withdraw_all_consents` method falls back to calling `self.consent_repo.create(record)` in a loop (lines 378-379). Each `create()` call commits individually (see `repositories.py` line 108: `await self.session.commit()`). If an error occurs partway through, some consent purposes are withdrawn and others are not, leaving the user in an inconsistent consent state.

The docstring acknowledges this ("backward compatibility with test fixtures that only inject repository mocks"), but the fallback is a production code path when `db_session` is None.

**Recommendation:** Ensure all production callers always provide `db_session`, or document this as a test-only path and add an assertion/guard.

---

### P2-8: Database password potentially in URL logged on failure
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/database.py`, lines 114-116
**Impact:** PII/Credential Exposure

When database initialization fails, the error message at line 115 may include connection details from the `DATABASE_URL`:
```python
logger.error("database_init_failed", error=str(e))
```

Some database driver exceptions include the connection string (with embedded password) in their string representation. While structlog's JSON renderer would not specially sanitize this, the password could appear in log output.

**Recommendation:** Catch and sanitize the error message to strip any URL fragments containing credentials, or log only `type(e).__name__` and a generic message.

***

## P3 -- Low / Housekeeping

### P3-1: `gunicorn_config.py` access log format includes client IP without anonymization
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/gunicorn_config.py`, line 39
**Impact:** GDPR (Minor)

The access log format includes `%(h)s` (client IP) and `%(a)s` (user agent). If Gunicorn access logs are retained, this constitutes processing PII under GDPR. The retention policy should align with `DATA_RETENTION_DAYS`.

**Recommendation:** Document the log retention policy. Consider removing `%(h)s` or using a custom log filter to anonymize IPs in access logs.

---

### P3-2: `requests_per_minute` and `requests_per_hour` accept `None` as mutable default
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py`, lines 90-91
**Impact:** Code Quality

The constructor parameters default to `None` and then fall back to settings values:
```python
requests_per_minute: int = None,
requests_per_hour: int = None,
```

The type annotation says `int` but the default is `None`. This should be `int | None = None` for correctness.

---

### P3-3: `lib/tracing.py` `traced` class duplicates sync/async context manager code
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/lib/tracing.py`, lines 53-97
**Impact:** Maintainability

The `__aenter__`/`__aexit__` and `__enter__`/`__exit__` methods are nearly identical (lines 53-73 vs 77-97). Any bug fix or feature addition needs to be applied twice.

**Recommendation:** Extract the shared span setup/teardown logic into private helper methods.

---

### P3-4: `app_factory.py` imports `asyncio` at module level but also re-imports `time` inline
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/app_factory.py`, line 443; `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py`, line 443
**Impact:** Code Quality (Minor)

In `rate_limiter.py` line 443, `time` is imported via `__import__("time")` inline:
```python
now = int(__import__("time").time())
```

This is an unusual pattern. The `time` module is already imported at the top of the file (line 9). This appears to be a leftover from a refactor.

**Recommendation:** Use `time.time()` directly since `time` is already imported.

---

### P3-5: `ConsentRepository.create()` commits immediately -- breaks caller transaction control
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/repositories.py`, line 108
**Impact:** Architectural Consistency

`ConsentRepository.create()` calls `await self.session.commit()` at line 108. This means every consent record creation is committed immediately, preventing the caller from batching operations or rolling back as part of a larger transaction.

The `delete_by_user_id()` method at line 227 correctly documents "Does NOT commit -- caller is responsible for transaction management." The `create()` method should follow the same pattern for consistency.

---

### P3-6: `account_locked_out` log includes `lockout_minutes` but not the key -- hard to correlate in monitoring
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py`, lines 349-354
**Impact:** Observability

The lockout warning log includes `identifier` and `lockout_minutes` but not the Redis `key`. When debugging rate-limit issues, operators need to inspect the Redis key directly.

---

### P3-7: `_SAFE_REQUEST_ID` regex allows underscores and hyphens but not dots or colons
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/tracing.py`, line 25
**Impact:** Interoperability (Minor)

The request ID validation regex `r"^[\w\-]{1,64}$"` accepts word chars and hyphens but not dots or colons. Some tracing systems (e.g., W3C Trace Context, AWS X-Ray) use dot- or colon-separated trace IDs. These would be rejected, causing new UUIDs to be generated instead.

**Recommendation:** Consider expanding to `r"^[\w\-.:]{1,128}$"` for broader interoperability.

***

## Files With No Issues Found
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/__init__.py` -- Single docstring, no logic.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/lib/__init__.py` -- Empty module.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/utils/__init__.py` -- Empty module.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/__init__.py` -- Single docstring, no logic.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/__init__.py` -- Re-exports only, no logic.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/auth/password.py` -- Solid implementation: 12-char minimum, 4 character class requirements, 200+ common password blocklist, NIST SP 800-63B compliant. No issues found.

## Summary

**Total findings: 20** (3 P0, 6 P1, 8 P2, 7 P3 including the 4 consolidated P3s)

### Strengths
- **Well-structured middleware pipeline**: Pure ASGI implementations throughout (no BaseHTTPMiddleware overhead), correct non-buffering behavior for SSE endpoints, proper `scope["type"] != "http"` guards on every middleware.
- **Strong secrets validation**: Settings module has comprehensive production-time validators for JWT_SECRET (length, blocklist, entropy), FIELD_ENCRYPTION_KEY (hex validity, 32-byte length), INTERNAL_API_KEY (distinct from JWT), STRIPE_SECRET_KEY (prefix check), and DATABASE_URL (scheme check).
- **Solid encryption**: AES-256-GCM with per-ciphertext random nonces, proper key length validation, `os.urandom()` for nonce generation.
- **Atomic GDPR deletion**: The main deletion flow uses a single transaction with explicit rollback on failure, covers 17 data categories across all 53 tables.
- **Rate limiter Lua atomicity**: TOCTOU race eliminated by atomic Lua sliding window with `:seq` key TTL management.
- **Defense-in-depth**: Sentry PII disabled (`send_default_pii=False`), validation errors sanitized (no input echo), metrics endpoint API-key-gated with constant-time comparison, Swagger/ReDoc disabled in production.
- **Circuit breaker**: Clean state machine (CLOSED/OPEN/HALF_OPEN), async-safe locking, proper coroutine cleanup (`.close()` on rejected coroutines).
- **Observability**: Well-designed opt-in OTel with graceful degradation (no-op tracer when disabled, console exporter in dev, silent discard in prod without endpoint).

### Risk Summary
The three P0 findings center on GDPR audit trail integrity (deletion log FK contradiction, non-atomic audit persistence) and structured logging context leakage. The P1 findings address rate-limit bypass via token rotation, missing CORS expose_headers, PII in logs, and encryption without AAD. All are fixable without architectural changes.
