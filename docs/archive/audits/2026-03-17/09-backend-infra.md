# Audit Report: Backend Infrastructure & Config
## Date: 2026-03-17

---

### Executive Summary

The backend infrastructure is in strong shape overall. The application factory
pattern cleanly separates construction concerns, all secrets have production
validators, CORS is locked down to an explicit allowlist, and security headers
cover the full OWASP recommended set. The session-validation layer correctly
handles both cookie and Bearer paths, caches with a 60-second TTL, and
invalidates on logout. Rate limiting uses an atomic Lua sliding-window script
(TOCTOU-safe since the Zenith audit). The GDPR deletion path covers all 53
known tables.

Nine issues were identified across all severity tiers. None are auth bypasses.
The most actionable near-term items are: the `protect_metrics` middleware
registration ordering gap (P1), the `gunicorn_config.py` stale brand name and
missing `umask` hardening (P2), missing `better_auth_secret` nil-check in
production (P1), and the synchronous 1Password `subprocess` call on the hot
startup path (P2).

---

### Findings

---

#### P0 — Critical

No P0 findings. Auth bypass, CORS wildcard, and secret-in-error-response
patterns were specifically reviewed and are not present.

---

#### P1 — High

**P1-01: `protect_metrics` middleware registered AFTER `add_middleware()` calls — security gap window**

File: `backend/app_factory.py`, lines 514–524

The `protect_metrics` `@app.middleware("http")` decorator is registered after
all `add_middleware()` calls. In Starlette/FastAPI, `add_middleware()` wrappers
are applied in LIFO order (last registered = outermost), while
`@app.middleware("http")` decorators are inserted into the innermost position of
the stack. This means `protect_metrics` runs *inside* `RateLimitMiddleware`,
`RequestBodySizeLimitMiddleware`, and `RequestTimeoutMiddleware` rather than
outside them.

Practical consequences:
- A `/metrics` request is fully rate-limited and body-sized before the API key
  gate fires, which is the correct order for those concerns.
- However, the 30-second `RequestTimeoutMiddleware` timeout does apply to the
  key-check logic, which is negligible overhead and not a real risk.
- The more meaningful gap: the `protect_metrics` check only runs for the mounted
  `/metrics` ASGI sub-application's path *after* the main app routing has
  already matched the route. An attacker who crafts a path that normalizes to
  `/metrics` after ASGI scope manipulation may bypass the guard on some proxies,
  since the guard relies on `request.url.path` rather than the lower-level ASGI
  `scope["path"]`.

Additionally, `protect_metrics` is only active when `settings.internal_api_key`
is set. If the env var is absent in a non-production environment (where
`internal_api_key` is `Optional[str]` and defaults to `None`), the guard
silently does nothing — Prometheus metrics are world-readable.

Recommendation:

```python
# Move protect_metrics ABOVE the mount() call and check scope["path"] instead
@app.middleware("http")
async def protect_metrics(request: Request, call_next):
    if scope_path(request).startswith("/metrics"):
        api_key = request.headers.get("X-API-Key")
        if api_key != settings.internal_api_key:  # always compare, key may be None
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)
```

Also consider making `/metrics` require the key unconditionally (not gated on
`settings.internal_api_key` being truthy) so a misconfigured deploy does not
silently expose it.

---

**P1-02: No startup validation that `better_auth_secret` is set in production**

File: `backend/config/settings.py`, lines 258–268

`validate_better_auth_secret` only validates the *length* of the secret when it
is non-None in production. If `BETTER_AUTH_SECRET` is absent entirely, the
validator silently passes (returns `None`), and the application starts without a
signing secret for Better Auth session tokens.

Better Auth uses this secret to sign session cookies. Without it, it likely
falls back to an internally-generated ephemeral key that rotates on each
process restart — breaking all active sessions on every Gunicorn worker recycle
(`max_requests=1000`).

Compare the pattern used for `internal_api_key` (lines 270–285), which raises
`ValueError` when the key is absent in production. The same protection is
missing for `better_auth_secret`.

Recommendation:

```python
@field_validator("better_auth_secret")
@classmethod
def validate_better_auth_secret(cls, v: Optional[str]) -> Optional[str]:
    env = os.environ.get("ENVIRONMENT", "development")
    if env == "production":
        if not v:
            raise ValueError(
                "CRITICAL: BETTER_AUTH_SECRET must be set in production. "
                "Generate one with: openssl rand -hex 32"
            )
        if len(v) < 32:
            raise ValueError(
                "BETTER_AUTH_SECRET must be at least 32 characters in production."
            )
    return v
```

---

**P1-03: `database_url` validator accepts `postgresql+asyncpg://` prefix but only validates `postgresql://`**

File: `backend/config/settings.py`, lines 303–317

`validate_database_url` checks `v.startswith("postgresql://")`, but if the
operator sets `DATABASE_URL=postgresql+asyncpg://...` directly (a reasonable
thing to do based on database.py line 79 which does the replacement internally),
the validator raises a `ValueError` and the app refuses to start. Conversely, if
they set a `postgres://` URL (the older Heroku/Render default format), the
validator also rejects it even though the database.py rewrite would still work.

This is a correctness issue: valid configs are rejected and the error message is
misleading.

Recommendation:

```python
@field_validator("database_url")
@classmethod
def validate_database_url(cls, v: Optional[str]) -> Optional[str]:
    env = os.environ.get("ENVIRONMENT", "development")
    if env == "production":
        if not v:
            raise ValueError("CRITICAL: DATABASE_URL must be set in production.")
        # Accept all Postgres URL schemes used in practice
        if not any(v.startswith(p) for p in (
            "postgresql://", "postgres://", "postgresql+asyncpg://"
        )):
            raise ValueError(
                "DATABASE_URL must start with 'postgresql://', 'postgres://', "
                "or 'postgresql+asyncpg://' in production."
            )
    return v
```

---

#### P2 — Medium

**P2-01: `SecretsManager._get_from_1password` uses blocking `subprocess.run` on the lifespan/startup path**

File: `backend/config/secrets.py`, lines 183–210

`_get_from_1password` calls `subprocess.run` synchronously with a 10-second
timeout. In production (`use_1password=True`), this blocks the asyncio event
loop for up to 10 seconds per secret fetch during application startup. With
~28+ mapped secrets, startup could block for up to 280 seconds in the worst
case.

In practice the cache means subsequent calls are fast, but the *first* call per
secret still blocks. Since this is called from `SecretsManager.__init__` context
and ultimately from module-level `settings = Settings()`, it runs before the
event loop is even started — this is actually safe from an async perspective,
but it means startup time is impacted by subprocess latency. More critically, if
`get_secret()` is ever called at request time (which `require_secret()` could
be), it would block the event loop.

Recommendation: Switch to `asyncio.create_subprocess_exec` for any calls made
inside async context. For the module-level initialization path, the synchronous
approach is acceptable but should be documented explicitly. Add a log warning if
startup secret fetch takes > 5 seconds.

---

**P2-02: `gunicorn_config.py` stale brand name and missing `umask` hardening**

File: `backend/gunicorn_config.py`, lines 62 and 51

Line 63: `server.log.info("Starting Electricity Optimizer API...")` — stale
working name, should be "RateShift API".

Line 51: `umask = 0` — sets file creation permissions to 0o777 (world-readable/
writable). Gunicorn uses umask when creating PID files, temp upload dirs, and
Unix domain sockets. A umask of `0` means any file created by Gunicorn inherits
permissions that allow world-write on a multi-user system.

Recommendation:
```python
umask = 0o027   # owner rw, group r, others none
proc_name = "rateshift-api"
```
Also update the `on_starting` log message.

---

**P2-03: `RequestBodySizeLimitMiddleware` chunked-encoding path has a response-suppression race**

File: `backend/app_factory.py`, lines 143–158

The `guarded_send` closure suppresses the app's `http.response.start` message
when `limit_exceeded` is True and `response_started` is False. However, after
`await self.app(scope, counting_receive, guarded_send)` returns, the code
checks:

```python
if limit_exceeded and not response_started:
    await self._send_413(send, max_bytes)
```

If the app sends `http.response.start` *between* setting `limit_exceeded = True`
and returning, `response_started` remains False (because `guarded_send` was
suppressing and didn't set it), so `_send_413` fires after the app has already
started sending a response. This would corrupt the HTTP stream.

The issue only occurs in the specific timing window where:
1. The body limit is exceeded mid-stream.
2. The downstream app emits a response before returning control.

In practice this is a narrow race for chunked POST bodies, but it can produce
malformed responses visible to clients.

Recommendation: Track whether `guarded_send` suppressed a response start, and
skip the 413 send if the response was already partially emitted. The current
`response_started` flag should be set to `True` even when suppressing, and a
separate `suppressed_response` flag used for the post-return check:

```python
async def guarded_send(message: dict) -> None:
    nonlocal response_started
    if message.get("type") == "http.response.start":
        response_started = True  # always mark as started
        if limit_exceeded:
            return  # suppress app's response
    ...
```

---

**P2-04: `DeletionLogORM.user_id` FK uses `ondelete="SET NULL"` but the column is `nullable=False`**

File: `backend/compliance/repositories.py`, lines 52–56

```python
user_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=False
)
```

The `ondelete="SET NULL"` directive instructs the database to set `user_id` to
NULL when the referenced user is deleted. However, `nullable=False` on the
column means NULL is not allowed. This is a contradictory constraint: if a user
is deleted, PostgreSQL will attempt to SET NULL on `deletion_logs.user_id`, but
the NOT NULL constraint will cause the DELETE on `users` to fail with a
constraint violation.

In the GDPR deletion flow, `users` is deleted in step 13, and `deletion_logs`
INSERT happens after the commit (lines 983–1005). So the row does not exist when
the user is deleted, but if a deletion log pre-exists for a user being re-deleted
or if a DBA manually deletes a user, this would fail.

Recommendation: Either change `ondelete` to `"CASCADE"` (delete the log when the
user is deleted — acceptable since the log is inserted after the user row is
gone) or make `user_id` nullable (`nullable=True`) and accept NULL for soft-
deleted users. Given that deletion logs are the audit trail, `SET NULL` is
semantically correct — fix the `nullable=False` to `nullable=True`.

---

**P2-05: `_execute_raw_query` in `database.py` falls through to SQLAlchemy ORM with raw SQL via `text()` — no parameter binding warning**

File: `backend/config/database.py`, lines 176–188

The `_execute_raw_query` method accepts raw SQL and positional `*args`. On the
asyncpg path (line 179), args are bound as positional parameters (`$1`, `$2`).
On the SQLAlchemy fallback (lines 182–186), the same `query` string is passed
directly to `text()` with *no* parameter binding — the `*args` are silently
ignored.

If any caller passes user-controlled data via `args` while the asyncpg pool is
unavailable (i.e., on Neon where the asyncpg pool is skipped), the fallback
executes the raw string without substitution, potentially with SQL injection if
the query was templated with format strings.

Recommendation: Audit all callers of `_execute_raw_query`. If the method is
internal-only, add a `# type: ignore` comment and prominent warning that args are
not forwarded on the SQLAlchemy path. Better yet, make both paths use the same
parameterized execution model, or remove the method and require callers to use
the ORM directly.

---

**P2-06: `SessionData.role` from cache is deserialized as a plain string — no enum validation**

File: `backend/auth/neon_auth.py`, lines 76–78

When a session is loaded from Redis cache (line 77), the `role` field is
deserialized directly from the JSON string with `SessionData(**data)`. There is
no validation that `role` contains an expected value. If a Redis key is manually
modified or corrupted, an attacker could inject an arbitrary role string that
downstream authorization checks (`session.role == "admin"`) would accept.

Recommendation: Validate `role` against an allowlist on deserialization:

```python
VALID_ROLES = {None, "admin", "user", "moderator"}

# In cache deserialization:
role = data.get("role")
if role not in VALID_ROLES:
    role = None  # treat unknown roles as unprivileged
```

---

#### P3 — Low

**P3-01: `gunicorn_config.py` imports `multiprocessing` but never uses it**

File: `backend/gunicorn_config.py`, line 11

`import multiprocessing` is present (likely from a template that originally
calculated worker count as `multiprocessing.cpu_count() * 2 + 1`) but is not
used anywhere in the file.

Recommendation: Remove the dead import.

```python
# Remove: import multiprocessing
```

---

**P3-02: `TODO` comment in `settings.py` for `FRONTEND_URL` remains after the fix was applied**

File: `backend/config/settings.py`, lines 164–167

```python
# TODO: Set FRONTEND_URL=https://rateshift.app on Render (and any other
# non-local deployment) so OAuth callbacks redirect to the correct frontend
# origin.  The default covers local development only.
frontend_url: str = Field(default="http://localhost:3000", validation_alias="FRONTEND_URL")
```

Per the MEMORY.md, `FRONTEND_URL` was added to Render env vars (42 total env
vars confirmed). The TODO comment is now stale and should be removed.

---

**P3-03: `compliance/repositories.py` imports `Column` and `String`, `Boolean`, `DateTime`, `JSON`, `ForeignKey` from both `sqlalchemy` and `sqlalchemy.orm` but uses `Mapped`/`mapped_column` throughout — legacy imports are dead**

File: `backend/compliance/repositories.py`, lines 12–15

```python
from sqlalchemy import Column, ForeignKey, String, Boolean, DateTime, JSON, text
```

`Column`, `Boolean`, `DateTime`, and `JSON` from the `sqlalchemy` top-level
import are not used anywhere in the file — all column definitions use the modern
`Mapped`/`mapped_column` style. `ForeignKey`, `String`, and `text` are still
used.

Recommendation: Remove the dead imports:

```python
from sqlalchemy import ForeignKey, String, text
```

---

**P3-04: `db_manager` global in `database.py` is a module-level singleton that initializes lazily — not clearly documented for multi-process Gunicorn workers**

File: `backend/config/database.py`, lines 195–196

```python
# Global database manager instance
db_manager = DatabaseManager()
```

With `preload_app = False` in `gunicorn_config.py` (line 30), each Gunicorn
worker imports the module fresh and creates its own `db_manager`. This is
correct for `preload_app=False`. However, the comment above the global makes no
mention of the multi-worker implications, and `preload_app = False` has a comment
saying "good practice for scaling" — if someone enables `preload_app = True` for
memory savings (a common optimization), the single `db_manager` object would be
shared across forked workers without re-running `initialize()`, leading to broken
asyncpg connections.

Recommendation: Add a comment warning that `preload_app = True` is incompatible
with the current module-level singleton pattern, and add a `post_fork` hook to
`gunicorn_config.py` that calls `asyncio.run(db_manager.initialize())` if
`preload_app` is ever enabled.

---

### Statistics

| Severity | Count | Files Affected |
|----------|-------|----------------|
| P0 (Critical) | 0 | — |
| P1 (High) | 3 | `app_factory.py`, `settings.py` (x2) |
| P2 (Medium) | 6 | `app_factory.py`, `gunicorn_config.py`, `config/secrets.py`, `compliance/repositories.py`, `config/database.py`, `auth/neon_auth.py` |
| P3 (Low) | 4 | `gunicorn_config.py`, `settings.py`, `compliance/repositories.py`, `config/database.py` |
| **Total** | **13** | **7 files** |

### Files Reviewed

| File | Lines | Status |
|------|-------|--------|
| `backend/main.py` | 27 | Clean — thin entry point, correct uvicorn args |
| `backend/app_factory.py` | 797 | 2 findings (P1-01, P2-03) |
| `backend/observability.py` | 305 | Clean — idempotent init, correct no-op fallback |
| `backend/gunicorn_config.py` | 81 | 3 findings (P2-02, P3-01, P3-04) |
| `backend/middleware/__init__.py` | 1 | Clean |
| `backend/middleware/security_headers.py` | 144 | Clean — full OWASP header set, HSTS prod-only |
| `backend/middleware/tracing.py` | 70 | Clean — safe ASCII validation on X-Request-ID |
| `backend/middleware/rate_limiter.py` | 503 | Clean — atomic Lua script, TTL on seq key |
| `backend/config/__init__.py` | 1 | Clean |
| `backend/config/settings.py` | 384 | 3 findings (P1-02, P1-03, P3-02) |
| `backend/config/database.py` | 209 | 2 findings (P2-05, P3-04) |
| `backend/config/secrets.py` | 287 | 1 finding (P2-01) |
| `backend/auth/__init__.py` | 24 | Clean — lazy import pattern correct |
| `backend/auth/neon_auth.py` | 273 | 1 finding (P2-06) |
| `backend/auth/password.py` | 155 | Clean — NIST SP 800-63B common password list present |
| `backend/compliance/__init__.py` | 31 | Clean |
| `backend/compliance/gdpr.py` | 1097 | Clean — all 53 tables covered in deletion |
| `backend/compliance/repositories.py` | 340 | 2 findings (P2-04, P3-03) |
| `backend/integrations/__init__.py` | 64 | Clean |
| `backend/integrations/weather_service.py` | 339 | Clean — circuit breaker, no key leakage |
| `backend/integrations/utilityapi.py` | 509 | Clean — circuit breaker, injected HTTP client |
| `backend/lib/__init__.py` | 1 | Clean |
| `backend/lib/circuit_breaker.py` | 159 | Clean — async-safe lock, correct HALF_OPEN probe limit |
| `backend/lib/tracing.py` | 114 | Clean — dual sync/async context manager |
| `backend/utils/__init__.py` | 1 | Clean |
| `backend/utils/encryption.py` | 88 | Clean — AES-256-GCM, random nonce per ciphertext |

### Strengths Observed

- **Middleware stack design**: Pure ASGI middleware throughout (no
  `BaseHTTPMiddleware`) avoids response buffering. Middleware ordering comment is
  accurate and LIFO ordering is well understood.
- **Atomic rate limiting**: The Lua sliding-window script is correct and the
  `:seq` counter TTL leak was already fixed (per quality hardening sprint).
- **Secret validation at startup**: Field validators for all critical production
  secrets (`jwt_secret`, `internal_api_key`, `stripe_secret_key`,
  `database_url`, `resend_api_key`, `field_encryption_key`) cause hard startup
  failure rather than runtime errors.
- **Exception handler sanitization**: `validation_exception_handler` strips
  `input` and `ctx` fields from Pydantic errors before returning them to the
  client — preventing echo-back of potentially sensitive user input. The general
  exception handler correctly suppresses stack traces in production.
- **GDPR coverage**: `delete_user_data` covers all community, notification,
  agent, connection, and supplier tables in a single atomic transaction. The
  post-commit file cleanup is correctly marked as best-effort.
- **Session cache invalidation**: `invalidate_session_cache` is wired into
  logout, ensuring immediate eviction of cached sessions rather than waiting for
  the 60-second TTL.
- **Encryption**: AES-256-GCM with per-ciphertext random 96-bit nonce is
  cryptographically sound. Key validation at startup rejects wrong-length keys.
- **Circuit breakers**: Both `WeatherService` and `UtilityAPIClient` implement
  circuit breakers with proper HALF_OPEN probe logic and asyncio.Lock for
  thread safety.
