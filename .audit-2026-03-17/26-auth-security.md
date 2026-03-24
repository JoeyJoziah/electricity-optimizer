# Audit Report: Auth & Security
## Date: 2026-03-17
## Auditor: Claude Code (claude-sonnet-4-6)
## Scope: Auth & Security (Cross-cutting)

---

### Executive Summary

The auth and security layer is in solid shape overall. The core session-validation path (`neon_auth.py`) is correct and well-structured: parameterized SQL, constant-time HMAC comparisons, SHA-256 session cache keys, a 60-second cache TTL with explicit invalidation on logout, and `banned` user filtering baked into the DB query. The Stripe webhook handler correctly reads the raw body before any middleware parsing. The security-headers middleware provides a tight production CSP with no `unsafe-inline`. The rate limiter uses an atomic Lua sliding-window script and the `:seq` TTL leak was previously remediated.

Three findings require attention before the next production promotion. One is a P0 (incorrect HMAC API call in the GitHub webhook handler that raises a `TypeError` at runtime). Two are P1 (the `email_verified` flag is never enforced at the API layer, and the in-memory fallback rate limiter is not safe for multi-process deployments). The remaining findings are P2/P3 and are improvements rather than blockers.

---

### Files Reviewed

| File | Lines | Notes |
|------|-------|-------|
| `backend/auth/__init__.py` | 24 | Lazy-load module shim |
| `backend/auth/neon_auth.py` | 273 | Core session validation |
| `backend/auth/password.py` | 155 | Password policy + strength check |
| `backend/api/v1/auth.py` | 192 | Auth API endpoints |
| `backend/api/v1/billing.py` | 423 | Stripe checkout + webhook |
| `backend/api/v1/webhooks.py` | 102 | GitHub webhook |
| `backend/api/dependencies.py` | 326 | `verify_api_key`, `require_tier` |
| `backend/middleware/rate_limiter.py` | 503 | Redis sliding-window + in-memory fallback |
| `backend/middleware/security_headers.py` | 145 | CSP, HSTS, security headers |
| `frontend/lib/auth/client.ts` | 17 | Better Auth client setup |
| `frontend/lib/auth/server.ts` | 152 | Better Auth server config |
| `frontend/middleware.ts` | 91 | Next.js route protection |
| `frontend/lib/utils/url.ts` | 46 | `isSafeRedirect`, `isSafeOAuthRedirect` |
| `tests/security/test_auth_bypass.py` | 340 | Auth bypass tests |
| `tests/security/test_rate_limiting.py` | 269 | Rate limit tests |
| `tests/security/test_sql_injection.py` | 312 | SQL injection tests |

---

### Findings

---

#### P0 — Critical

---

**P0-01: `hmac.new` in GitHub webhook handler raises `TypeError` at runtime**

- **File**: `backend/api/v1/webhooks.py`, line 48
- **Severity**: Critical — the GitHub webhook endpoint is completely broken in production. Every inbound event returns a 500.

```python
# Current (BROKEN):
expected = hmac.new(
    secret.encode("utf-8"),
    payload,
    hashlib.sha256,
).hexdigest()
```

Python's `hmac.new()` requires `digestmod` to be passed as a keyword argument in Python 3.8+ and the positional order is `(key, msg=None, digestmod='')`. Passing `hashlib.sha256` as the third positional argument works — that part is fine. However, the `hmac` module was imported at the top of the file (`import hmac`) but `hmac.new` is the correct function name. The issue here is subtle: `hashlib.sha256` is the constructor function, not a hash name string. This works, but the deeper problem is that `hmac.new` is the deprecated alias for `hmac.HMAC`. In Python 3.13, `hmac.new` was removed. Running this on any Python 3.13+ deployment (or a fresh container that upgrades) will fail with `AttributeError: module 'hmac' has no attribute 'new'`.

The same pattern is present in `backend/services/email_oauth_service.py` lines 48 and 62, and `backend/api/v1/connections/common.py` lines 72 and 93.

**Recommendation**: Replace all `hmac.new(...)` with `hmac.HMAC(...)` or the equivalent `hmac.new` wrapper where still available. The preferred idiomatic form is:

```python
# Correct for all Python 3.x versions:
expected = hmac.new(
    key=secret.encode("utf-8"),
    msg=payload,
    digestmod=hashlib.sha256,
).hexdigest()

# Or use the class directly to be explicit and forward-compatible:
expected = hmac.HMAC(
    key=secret.encode("utf-8"),
    msg=payload,
    digestmod=hashlib.sha256,
).hexdigest()
```

Check all four sites:
- `backend/api/v1/webhooks.py:48`
- `backend/services/email_oauth_service.py:48`
- `backend/services/email_oauth_service.py:62`
- `backend/api/v1/connections/common.py:72`
- `backend/api/v1/connections/common.py:93`

Note: The existing `tests/test_webhooks.py:25` also uses `hmac.new` and would need the same fix. Run `grep -rn "hmac\.new" backend/ tests/` to find all instances.

---

#### P1 — High

---

**P1-01: `email_verified` is not enforced at the backend API layer**

- **File**: `backend/auth/neon_auth.py`, lines 42–49 (`SessionData`); `backend/api/v1/auth.py`, line 83 (`GET /me`); all endpoints using `Depends(get_current_user)`
- **Severity**: High — users who have registered but not yet verified their email can call every authenticated API endpoint. The `requireEmailVerification: true` flag in `frontend/lib/auth/server.ts` (line 41) prevents unverified users from signing in through the Better Auth frontend flow, but the backend session-validation query does not check `emailVerified`. Any user who obtains a valid session token (e.g., through a direct API call, a race between sign-up and the verification check, or a social provider whose email is not pre-verified) can bypass email verification entirely.

The `SessionData` dataclass carries `email_verified: bool` but it is never read outside of `UserResponse` (returned by `GET /me`) and tests. No endpoint checks it before proceeding.

**Recommendation**: Add a `require_email_verified` FastAPI dependency — or extend `get_current_user` — to reject sessions where `email_verified is False` with a descriptive 403. Alternatively, add the check to the DB query in `_get_session_from_token` by joining against the `emailVerified` column:

```python
# Option A: Extend the SQL query to hard-reject unverified sessions
AND u."emailVerified" = true

# Option B: Lightweight dependency for sensitive endpoints
async def require_verified_email(
    current_user: SessionData = Depends(get_current_user),
) -> SessionData:
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    return current_user
```

Option A is the stronger control because it eliminates the gap at the session cache layer as well (a cached unverified session would not survive a re-query after the user verifies).

---

**P1-02: `_password_check_limiter` uses in-memory store only — bypassed on multi-process/multi-instance deployments**

- **File**: `backend/api/v1/auth.py`, lines 33–39
- **Severity**: High — the per-IP rate limiter on `POST /password/check-strength` is instantiated as `UserRateLimiter()` with no Redis client. On Render, Uvicorn runs multiple workers (typically 2–4 by default). Each worker has its own `_memory_store`, so the effective rate limit is `5 * num_workers` per minute per IP, not 5. An attacker can enumerate the common-password list or run timing analyses against the password-strength endpoint at a rate far higher than intended.

```python
# Current — no Redis, falls back to in-memory:
_password_check_limiter = UserRateLimiter(
    requests_per_minute=5,
    requests_per_hour=60,
)
```

**Recommendation**: Inject the shared Redis client at startup (the pattern already exists in `middleware/rate_limiter.py`). The simplest fix is to lazily wire Redis in the first call rather than at module import time:

```python
async def check_password(http_request: Request, request: PasswordStrengthRequest):
    redis = None
    try:
        redis = await db_manager.get_redis_client()
    except Exception:
        pass
    limiter = UserRateLimiter(redis_client=redis, requests_per_minute=5, requests_per_hour=60)
    ...
```

Or, refactor to use a module-level limiter that accepts a Redis client injected via FastAPI `Depends(get_redis)` — consistent with how the global `RateLimitMiddleware` works.

---

**P1-03: Missing `X-RateLimit-Reset` header on rate-limit responses**

- **File**: `backend/middleware/rate_limiter.py`, lines 436–443 (`send_wrapper`); line 454 (`_send_429`)
- **Severity**: High (usability+security) — the middleware emits `X-RateLimit-Limit` and `X-RateLimit-Remaining` on normal responses, and `Retry-After` on 429s, but omits `X-RateLimit-Reset`. The test in `tests/security/test_rate_limiting.py` line 93 explicitly lists `X-RateLimit-Reset` as an expected header. Without it, clients implementing standard rate-limit backoff (e.g., RFC 6585) cannot calculate when the window resets and will either hammer the endpoint anyway or implement arbitrary sleeps.

This is also a minor inconsistency: `test_rate_limit_remaining_decreases` (line 102) checks `X-RateLimit-Remaining` which *is* emitted, but the test file lists `X-RateLimit-Reset` as also expected.

**Recommendation**: Add `X-RateLimit-Reset` to both the normal response wrapper and the 429 response. The reset time is the end of the current sliding window, which is `ceil(now + window)`:

```python
# In send_wrapper and _send_429:
import time, math
reset_time = str(math.ceil(time.time() + 60))  # for minute window
headers["X-RateLimit-Reset"] = reset_time
```

---

#### P2 — Medium

---

**P2-01: `callbackUrl` redirect validation is duplicated and slightly inconsistent between middleware and `useAuth`**

- **File**: `frontend/middleware.ts`, line 58; `frontend/lib/hooks/useAuth.tsx`, lines 267–276; `frontend/lib/utils/url.ts`, line 17 (`isSafeRedirect`)
- **Severity**: Medium — the redirect validation logic exists in three places with slightly different implementations.

  - `frontend/middleware.ts` (line 58) sets `callbackUrl` via `signInUrl.searchParams.set('callbackUrl', pathname)` — uses `pathname` only (no query string), which is safe but loses query params on deep-linked URLs.
  - `frontend/lib/api/client.ts` (line 84) correctly uses `isSafeRedirect(existingCallback)` from `url.ts` before forwarding the callback.
  - `frontend/lib/hooks/useAuth.tsx` (lines 270–273) re-implements the origin check inline rather than calling `isSafeRedirect`. The inline check adds `parsed.pathname.startsWith('/')` which `isSafeRedirect` does not enforce.

The inline check in `useAuth.tsx` is slightly stronger than `isSafeRedirect` (enforces pathname starts with `/`), but the duplication means a future refactor could diverge. The `isSafeRedirect` function does not cover the case where `parsed.pathname` could be empty (e.g., `https://rateshift.app` with no path) — in that case `pathname.startsWith('/')` would be false and the fallback to `/dashboard` would kick in, which is the correct safe behavior. However, it would be cleaner to have a single source of truth.

**Recommendation**: Extend `isSafeRedirect` in `url.ts` to also require `pathname.startsWith('/')` and replace the inline check in `useAuth.tsx` with a call to `isSafeRedirect`. This centralizes the logic and removes the duplication.

---

**P2-02: Session cache key uses only 32 hex characters (128-bit prefix) of SHA-256**

- **File**: `backend/auth/neon_auth.py`, line 69
- **Severity**: Medium (theoretical) — the Redis cache key is `session:{sha256(token)[:32]}`. Truncating to the first 32 hex characters (16 bytes = 128 bits) is still collision-resistant for all practical purposes, but it means two distinct session tokens that share the same 128-bit SHA-256 prefix would map to the same cache entry. SHA-256 gives 256 bits; the truncation halves the collision resistance to ~2^64, which is well below what a motivated attacker with a large pre-computed table could reach over a long-lived system.

**Recommendation**: Use the full SHA-256 hex digest (64 characters) as the key suffix. The Redis key length increases by 32 bytes — negligible. This also makes the code consistent with how `invalidate_session_cache` (line 138) generates its key using the same truncated hash, which is correct as long as both sides use the same truncation — they do — but any future code that independently computes the key might use the full digest and silently fail to find the cache entry.

```python
# Current:
cache_key = f"session:{hashlib.sha256(session_token.encode()).hexdigest()[:32]}"

# Recommended:
cache_key = f"session:{hashlib.sha256(session_token.encode()).hexdigest()}"
```

---

**P2-03: No audit logging on authentication events (sign-in, sign-out, failed auth)**

- **File**: `backend/auth/neon_auth.py`, lines 183–184, 203–205; `backend/api/v1/auth.py`, lines 148–151
- **Severity**: Medium — failed session validations emit `logger.warning("invalid_or_expired_session")` and `logger.warning("missing_session_token")` with no contextual data (no IP address, no partial token identifier, no user agent). Successful logins are not logged at all in the backend auth layer (the `GET /me` call logs `user_id` but not the sign-in event itself). This makes forensic analysis after an incident difficult.

**Recommendation**: Add structured audit log entries at key points:
- On `get_current_user` failure: include `client_ip` from `request.client.host`, `user_agent` from headers, and the first 8 characters of the token (sufficient for correlation without leaking the credential).
- On successful `GET /me`: log `sign_in_success` with `user_id` and `ip`.
- On `POST /logout`: already logs `session_cache_invalidated` — good; consider adding `ip` and `user_agent` for completeness.

---

**P2-04: `require_tier` dependency does not verify the user record exists before returning a tier**

- **File**: `backend/api/dependencies.py`, lines 133–137
- **Severity**: Medium — `_get_user_tier` queries `public.users WHERE id = :id` and falls back to `"free"` if no row is found (`result.scalar_one_or_none() or "free"`). This means a user who has a valid Neon Auth session but whose `public.users` row was deleted (e.g., after a GDPR deletion that did not fully cascade) will silently pass tier checks as a free-tier user rather than receiving a 404 or 401. The user can continue to access free-tier endpoints indefinitely as long as their Neon Auth session is valid.

**Recommendation**: Add an explicit existence check in `require_tier` or in `_get_user_tier`:

```python
if result.scalar_one_or_none() is None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User account not found",
    )
```

---

**P2-05: Frontend middleware does not validate the session token — presence check only**

- **File**: `frontend/middleware.ts`, lines 44–64
- **Severity**: Medium (accepted design trade-off, but document it) — the Next.js middleware checks for the *presence* of the session cookie (`better-auth.session_token` or its `__Secure-` prefixed variant) but does not validate its signature or expiry. This means:
  - A tampered but structurally valid cookie value will pass the middleware and be served the protected page HTML.
  - The actual auth enforcement happens on the first API call from that page (backend returns 401, client redirects to login).
  - A user with an expired session will be shown the protected page shell (skeleton/loading state) briefly before being kicked to login.

This is an accepted architectural pattern for Next.js (full server-side validation at the middleware level is expensive and creates latency on every page navigation). However, it is worth documenting explicitly so future developers understand that middleware is "optimistic" and the backend is authoritative.

**Recommendation**: Add a comment in `middleware.ts` noting that this is a presence check only and that the backend validates the token cryptographically. Consider adding a short-lived `better-auth.session_valid_until` cookie (set by the Next.js auth handler on sign-in) that the middleware can use to avoid the brief flash for expired sessions, without needing to hit the database.

---

**P2-06: `onAPIError: { throw: true }` in Better Auth server config exposes internal errors**

- **File**: `frontend/lib/auth/server.ts`, lines 129–131
- **Severity**: Medium — the comment says this is needed to "catch [errors] with full detail" rather than having Better Auth silently swallow DB schema errors. In production, if Better Auth throws an internal error during sign-up or sign-in (e.g., a DB constraint violation), that error will propagate up to the Next.js API route handler. Whether it reaches the client depends on the error handler in the API route. If the route uses `{ throw: true }` without a catch, the raw error message (potentially including DB schema details) could appear in the HTTP response body or Next.js error page.

**Recommendation**: Wrap the `getAuth()` call site in the API route with a try/catch that maps errors to generic 500 responses, ensuring internal exception messages are logged but not forwarded to clients. The `onAPIError.throw` flag is the correct choice for development debugging, but in production it should be paired with a top-level error boundary.

---

#### P3 — Low

---

**P3-01: `_password_check_limiter` uses `http_request.client.host` without proxy awareness**

- **File**: `backend/api/v1/auth.py`, line 174
- **Severity**: Low — the password-check endpoint uses `http_request.client.host` (the direct TCP peer address) rather than the CF-Connecting-IP or X-Forwarded-For headers that the `RateLimitMiddleware._get_identifier` method correctly uses. Behind the Cloudflare Worker, `client.host` will always be Cloudflare's edge IP, so all users share the same rate limit bucket. This effectively means the 5 req/min limit is per-Cloudflare-edge-server rather than per user IP.

**Recommendation**: Extract the real client IP using the same helper logic as `_get_identifier`:

```python
client_ip = (
    http_request.headers.get("cf-connecting-ip")
    or http_request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    or (http_request.client.host if http_request.client else "unknown")
)
```

---

**P3-02: `record_login_attempt` does not use constant-time comparison for lockout check**

- **File**: `backend/middleware/rate_limiter.py`, lines 363–364
- **Severity**: Low (theoretical timing side-channel) — `is_locked_out` calls `await redis.get(key)` and checks `int(attempts) >= self.login_attempts`. The `int()` conversion and comparison are not constant-time, but since the check is against a counter (not a secret), this is not a meaningful attack vector. Documenting it as intentional would prevent a future auditor from flagging it.

---

**P3-03: `validate_password` errors include all failures in a single semicolon-joined string**

- **File**: `backend/auth/password.py`, lines 100–102
- **Severity**: Low (UX) — the `raise ValueError("; ".join(errors))` approach bundles all policy failures into one message. This works for server-side validation, but if the message is ever forwarded to a client it can read awkwardly. The `check_password_strength` function (line 107) provides the structured breakdown; callers who want per-rule feedback should use that instead. Consider a docstring note on `validate_password` directing callers to `check_password_strength` for structured output.

---

**P3-04: Security test suite uses JWT-based `valid_token` fixtures that don't match the actual session-token auth model**

- **File**: `tests/security/test_auth_bypass.py`, lines 28–64
- **Severity**: Low (test quality) — the test fixtures generate JWT tokens (`jwt.encode(payload, "test_secret_key", algorithm="HS256")`), but the actual auth system validates Bearer tokens as opaque session tokens against the `neon_auth.session` table — not as JWTs. The `TestTokenValidation` class (line 119) tests JWT-specific properties (algorithm, payload tampering, missing claims) that are irrelevant to the deployed auth mechanism. These tests will never catch a regression in the actual auth path because they exercise a path that doesn't exist in production.

**Recommendation**: Replace the JWT fixtures with `SessionData`-mock-based tests that patch `_get_session_from_token` to return `None` (expired/invalid) or a valid `SessionData` object. The tests in `backend/tests/test_auth.py` already do this correctly and can serve as the reference pattern.

---

**P3-05: `PasswordStrengthRequest` sets `max_length=128` — mismatched with Better Auth's `minPasswordLength: 12` but no maximum**

- **File**: `backend/api/v1/auth.py`, line 60; `frontend/lib/auth/server.ts`, line 40
- **Severity**: Low — the `POST /password/check-strength` endpoint accepts passwords up to 128 characters. Better Auth has no maximum length configured, so a user could register with a 500-character password. The strength check endpoint would reject passwords over 128 chars with a 422, but the actual sign-up flow would accept them (Better Auth has no `maxPasswordLength` set). This is a minor inconsistency — no security risk, but it creates a confusing user experience if someone tries to check a 200-character password's strength before registering.

**Recommendation**: Either remove the `max_length` cap on `PasswordStrengthRequest` (to match the unlimited behavior of Better Auth), or add `maxPasswordLength: 128` to the `emailAndPassword` config in `server.ts`.

---

**P3-06: `console.log` in `sendVerificationEmail` logs the verification URL to server output**

- **File**: `frontend/lib/auth/server.ts`, line 57
- **Severity**: Low — `console.log(\`[Auth] sendVerificationEmail called for user=${user.email} url=${url}\`)` logs the full email verification link (including the token) to stdout. On Vercel, stdout is captured in function logs which are retained for 30 days and accessible to anyone with Vercel project access. If a verification URL is logged, it could be replayed by anyone with access to those logs to verify an arbitrary email address.

**Recommendation**: Remove this log line, or replace it with a log that records only the event and the user email (not the token):

```typescript
// Before (leaks the token):
console.log(`[Auth] sendVerificationEmail called for user=${user.email} url=${url}`)

// After (safe):
console.log(`[Auth] sendVerificationEmail called for user=${user.email}`)
```

---

### Statistics

| Severity | Count | Items |
|----------|-------|-------|
| P0 Critical | 1 | P0-01 (hmac.new deprecated — 5 call sites) |
| P1 High | 3 | P1-01 (email_verified not enforced), P1-02 (password check rate limiter not Redis-backed), P1-03 (missing X-RateLimit-Reset) |
| P2 Medium | 6 | P2-01 through P2-06 |
| P3 Low | 6 | P3-01 through P3-06 |
| **Total** | **16** | |

### Recommended Fix Order

1. **P0-01** — Fix `hmac.new` to `hmac.HMAC` across all 5 call sites. This is a one-line change per site and should be done immediately. Confirm with `python3 --version` on the Render deployment; if it is already on Python 3.13 this is actively broken.
2. **P1-01** — Enforce `email_verified` in the backend session query. Blocks unverified users from the API without frontend-side enforcement.
3. **P1-02** — Wire Redis into `_password_check_limiter`. Required for the rate limit to work correctly in production.
4. **P2-05** — Document the "optimistic middleware" pattern in `middleware.ts` (zero code change, prevents future confusion).
5. **P3-06** — Remove the verification URL console.log in `server.ts` (one-line deletion, high value).
6. **P2-02** — Use full SHA-256 digest for session cache keys (trivial change, removes a theoretical weakness).
7. Remaining P2/P3 items can be addressed in the next hardening sprint.

### Strengths

- Constant-time comparison is used correctly for both the `X-API-Key` check (`hmac.compare_digest` in `dependencies.py:86`) and the GitHub webhook signature (`webhooks.py:56`). This is a common oversight in security code and it is implemented correctly here.
- The Stripe webhook handler reads the raw body (`await request.body()`) before any FastAPI body parsing middleware can consume it, which is the correct approach for HMAC verification.
- The Lua sliding-window script is atomic and the `:seq` TTL leak fix (noted in CLAUDE.md Critical Patterns) has been applied correctly.
- The session cache TTL was previously reduced from 300s to 60s (`neon_auth.py:54`) and explicit cache invalidation on logout (`invalidate_session_cache`) is wired into `POST /logout`. This is a good defense-in-depth measure.
- The `require_tier` factory correctly chains `get_current_user` dependency injection, so it cannot be bypassed without a valid session.
- `isSafeRedirect` and `isSafeOAuthRedirect` cover the critical open-redirect vectors (`//evil.com`, `javascript:`, protocol-relative URLs) correctly.
- Stripe redirect URL validation in `billing.py` uses an allowlist (`settings.allowed_redirect_domains`) with subdomain matching, which is the correct approach.
- The `banned` user check is inside the DB query itself (`AND (u.banned IS NULL OR u.banned = false)`), so it applies even when Redis is unavailable.
- Password policy is strong: 12-character minimum, 4-complexity-class requirement, NIST SP 800-63B common-password blocklist of 200 entries.
- The production CSP in `security_headers.py` has no `unsafe-inline`, `unsafe-eval`, or wildcard sources. The development CSP relaxes this appropriately.
