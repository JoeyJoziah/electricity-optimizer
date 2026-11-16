# Audit Report: Authentication & Security
**Date:** 2026-03-19
**Scope:** Auth flows, session management, access control, security middleware
**Auditor:** Security Auditor (claude-opus-4-6)
**Mode:** READ-ONLY

**Files Reviewed:**
- `backend/auth/__init__.py`
- `backend/auth/password.py`
- `backend/auth/neon_auth.py`
- `backend/api/v1/auth.py`
- `backend/api/dependencies.py`
- `backend/api/v1/billing.py`
- `backend/api/v1/webhooks.py`
- `backend/api/v1/agent.py`
- `backend/api/v1/user.py`
- `backend/api/v1/users.py`
- `backend/api/v1/savings.py`
- `backend/api/v1/notifications.py`
- `backend/api/v1/community.py`
- `backend/api/v1/internal/__init__.py`
- `backend/api/v1/connections/common.py`
- `backend/api/v1/connections/crud.py`
- `backend/api/v1/connections/email_oauth.py`
- `backend/api/v1/connections/portal_scrape.py`
- `backend/middleware/security_headers.py`
- `backend/middleware/rate_limiter.py`
- `backend/middleware/tracing.py`
- `backend/config/settings.py`
- `backend/config/secrets.py`
- `backend/utils/encryption.py`
- `backend/app_factory.py`
- `backend/main.py`
- `backend/gunicorn_config.py`
- `backend/services/email_oauth_service.py`
- `backend/compliance/gdpr.py`
- `frontend/lib/auth/client.ts`
- `frontend/lib/auth/server.ts`
- `frontend/lib/hooks/useAuth.tsx`
- `frontend/lib/api/client.ts`
- `frontend/lib/utils/url.ts`
- `frontend/lib/config/env.ts`
- `frontend/components/auth/LoginForm.tsx`
- `frontend/components/auth/SignupForm.tsx`
- `frontend/app/(app)/auth/login/page.tsx`
- `frontend/app/(app)/auth/signup/page.tsx`
- `frontend/app/(app)/auth/callback/page.tsx`
- `frontend/app/(app)/auth/forgot-password/page.tsx`
- `frontend/app/(app)/auth/reset-password/page.tsx`
- `frontend/app/(app)/auth/verify-email/page.tsx`
- `frontend/app/api/auth/[...all]/route.ts`
- `frontend/middleware.ts`

---

## P0 — Critical (Fix Immediately)

### P0-1: OAuth Callback State Has No Expiry Check (Replay Window Indefinite)

**File:** `backend/api/v1/connections/common.py`, lines 60–100

The `sign_callback_state()` function at line 60 embeds a timestamp in the HMAC payload:

```python
timestamp = str(int(time.time()))
payload = f"{connection_id}:{user_id}:{timestamp}"
```

However, `verify_callback_state()` at line 75 extracts the timestamp at line 88 but **never checks it against `OAUTH_STATE_TIMEOUT_SECONDS`** (defined at line 42 as 600 seconds):

```python
connection_id, user_id, timestamp, received_sig = parts
# ... HMAC verification only, no expiry check
return connection_id, user_id
```

The constant `OAUTH_STATE_TIMEOUT_SECONDS = 600` is dead code. A captured OAuth callback state parameter is valid indefinitely, enabling replay attacks. If an attacker intercepts a callback URL (e.g., via referrer header, browser history, or shared link), they can replay it at any future time to bind a connection to the victim's account.

**Remediation:** Add timestamp expiry validation in `verify_callback_state()`:

```python
import time
elapsed = int(time.time()) - int(timestamp)
if elapsed > OAUTH_STATE_TIMEOUT_SECONDS:
    raise HTTPException(status_code=400, detail="Callback state expired")
```

---

### P0-2: Email OAuth State Has No Expiry Check (Replay Window Indefinite)

**File:** `backend/services/email_oauth_service.py`, lines 37–64

The `generate_oauth_state()` function at line 37 creates a signed state with format `{connection_id}:{nonce}:{hmac}` but **includes no timestamp at all**. The `verify_oauth_state()` function at line 51 verifies the HMAC signature but has no temporal validation:

```python
def verify_oauth_state(state: str) -> str | None:
    parts = state.split(":")
    if len(parts) != 3:
        return None
    connection_id, nonce, received_mac = parts
    # ... HMAC check only, no expiry
```

Unlike the UtilityAPI callback state which at least includes a timestamp (even if unchecked), the email OAuth state has **no timestamp component at all**. A captured email OAuth state is valid forever.

**Remediation:** Include a timestamp in the state payload and verify expiry:

```python
def generate_oauth_state(connection_id: str) -> str:
    nonce = secrets.token_hex(16)
    ts = str(int(time.time()))
    payload = f"{connection_id}:{nonce}:{ts}"
    # ... HMAC over payload
    return f"{payload}:{mac}"

def verify_oauth_state(state: str) -> str | None:
    parts = state.split(":")
    if len(parts) != 4:
        return None
    connection_id, nonce, ts, received_mac = parts
    if int(time.time()) - int(ts) > 600:
        return None  # Expired
    # ... HMAC verification
```

---

## P1 — High (Fix This Sprint)

### P1-1: No Login Brute-Force Protection on Better Auth Endpoint

**Files:**
- `frontend/lib/auth/server.ts`, lines 28–152
- `backend/middleware/rate_limiter.py`, lines 307–356

Better Auth handles login via `POST /api/auth/sign-in/email` on the Next.js frontend. The Better Auth configuration in `server.ts` does not configure any login attempt rate limiting or account lockout. The `UserRateLimiter` in the backend has `record_login_attempt()` and `is_locked_out()` methods (lines 307–383) but these are **never called** anywhere in the codebase — only in test files.

The global middleware rate limiter applies a blanket 100 req/min per IP, but this is shared across all endpoints and is far too generous for login attempts. An attacker can attempt ~100 password guesses per minute per IP against the Better Auth sign-in endpoint without triggering any lockout.

**Remediation:** Configure Better Auth's built-in rate limiting or add explicit per-IP rate limiting to the `/api/auth/sign-in/*` routes. Better Auth supports `rateLimit` configuration:

```typescript
emailAndPassword: {
  enabled: true,
  rateLimit: {
    window: 60,  // 1 minute
    max: 5,      // 5 attempts per window
  },
},
```

---

### P1-2: Session Cache TTL Creates 60-Second Stale Access Window After Ban

**File:** `backend/auth/neon_auth.py`, lines 52–55

The session cache TTL is 60 seconds:

```python
_SESSION_CACHE_TTL = 60  # seconds
```

When a user is banned (`u.banned = true` in `neon_auth.user`), the ban is only checked on DB queries at line 137:

```sql
AND (u.banned IS NULL OR u.banned = false)
```

If the session is cached in Redis, a banned user retains access for up to 60 seconds. While explicit `invalidate_session_cache()` is called on logout (line 178), there is **no mechanism to invalidate the cache when a user is banned**. An admin banning a malicious user must wait up to 60 seconds for the ban to take effect.

**Remediation:** Add an `invalidate_session_cache_for_user()` function that invalidates all cached sessions for a given user_id (requires a secondary index or iterating cache keys), or reduce TTL to 10 seconds. Alternatively, call `invalidate_session_cache()` from the admin ban action if a session token is known.

---

### P1-3: Reset Password Page Only Validates Length, Not Full Password Policy

**File:** `frontend/app/(app)/auth/reset-password/page.tsx`, lines 37–44

The reset password form only checks minimum length:

```typescript
if (password.length < MIN_PASSWORD_LENGTH) {
  setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
  return
}
```

Unlike the signup form (`SignupForm.tsx`, lines 70–78) which validates uppercase, lowercase, digits, and special characters, the reset password form allows passwords like `aaaaaaaaaaaa` (12 lowercase characters only). While Better Auth may enforce server-side requirements, the frontend provides a false sense of security and a poor user experience when the server rejects the password after submission.

**Remediation:** Extract the shared password validation logic from `SignupForm.tsx` into a reusable utility and apply it in `ResetPasswordPage` as well.

---

## P2 — Medium (Fix Soon)

### P2-1: In-Memory Tier Cache Not Invalidated Across Workers on Scale-Up

**File:** `backend/api/dependencies.py`, lines 96–142

The tier-gating system uses a dual-layer cache: Redis (line 110) and in-memory dict `_tier_cache` (line 96):

```python
_tier_cache: dict[str, tuple[str, float]] = {}
_TIER_CACHE_TTL = 30  # seconds
```

Currently this is safe because the Gunicorn config (`gunicorn_config.py`, line 16) uses `workers = 1`. However, if the application scales to multiple workers, the in-memory cache becomes inconsistent: `invalidate_tier_cache()` at line 145 only clears the local process cache and Redis, leaving stale entries in other workers' memory for up to 30 seconds.

A user whose subscription is canceled could retain `pro` or `business` tier access for 30 seconds on workers that haven't had their in-memory cache cleared. This is a latent risk that becomes active upon horizontal scaling.

**Remediation:** Document this limitation in `gunicorn_config.py`, or remove the in-memory fallback and rely solely on Redis. The 30s TTL limits blast radius, but stale elevated permissions are a concern.

---

### P2-2: Password Strength Check Endpoint May Leak Information About Common Password List

**Files:**
- `backend/api/v1/auth.py`, lines 161–201
- `backend/auth/password.py`, lines 267–314

The `POST /auth/password/check-strength` endpoint returns a detailed `checks` dict including a `not_common` boolean:

```python
checks = {
    "not_common": password.lower() not in COMMON_PASSWORDS,
    # ...
}
```

While rate-limited to 5/min, this allows an attacker to systematically confirm which passwords are in the common password blocklist over time. The endpoint is unauthenticated (by design for signup flow), but the `not_common` field specifically reveals membership in the server's internal blocklist.

**Remediation:** Consider returning only the aggregate `valid` boolean and `strength` level rather than individual check results, or at minimum suppress the `not_common` field from the public response.

---

### P2-3: Email OAuth Callback Does Not Verify User Ownership

**File:** `backend/api/v1/connections/email_oauth.py`, lines 112–149

The `GET /email/callback` endpoint at line 116 does not require authentication and does not verify that the user who initiated the OAuth flow is the same user receiving the callback:

```python
async def email_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
):
```

The state parameter binds to a `connection_id` but the connection's `user_id` is not validated against the current session. An attacker who obtains a valid callback URL could complete the OAuth flow and bind tokens to another user's connection. The connection lookup at line 141 only checks existence and status, not ownership.

**Remediation:** Either require session authentication on the callback endpoint and verify `row["user_id"] == current_user.user_id`, or include the `user_id` in the signed state and verify it matches the connection's `user_id` in the database.

---

### P2-4: Frontend Middleware Auth Check Is Cookie-Presence-Only (No Validation)

**File:** `frontend/middleware.ts`, lines 72–76

The Next.js middleware checks only for the presence of a session cookie, not its validity:

```typescript
const sessionToken =
  request.cookies.get('better-auth.session_token')?.value ||
  request.cookies.get('__Secure-better-auth.session_token')?.value
```

A user with an expired or invalidated session token will pass the middleware check and reach protected pages. The page will then load, make API calls that return 401, and finally redirect to login. This creates a flash of authenticated UI for unauthenticated users.

This is a known limitation of edge middleware (validating the token requires a database call), but it should be documented. The risk is UX-only — no actual data exposure occurs because backend APIs properly validate sessions.

**Remediation:** Document this as an accepted limitation. Consider implementing a lightweight JWT validation in middleware if Better Auth supports signed session cookies, or use the cookie cache's `maxAge` as a staleness heuristic.

---

### P2-5: Encryption Key Fallback to Plaintext in Development

**File:** `backend/auth/neon_auth.py`, lines 58–72

When `FIELD_ENCRYPTION_KEY` is not configured, session cache data is stored in Redis as plaintext:

```python
def _encrypt_session_cache(plaintext: str) -> bytes:
    try:
        from utils.encryption import encrypt_field
        return encrypt_field(plaintext)
    except RuntimeError:
        return plaintext.encode("utf-8")
```

While `settings.py` line 246 enforces the key's presence in production, a misconfiguration (e.g., key set but malformed) could cause the `encrypt_field` call to raise a non-`RuntimeError` exception, which would propagate instead of falling back. More concerning: any `RuntimeError` from `encrypt_field` (not just "key missing") triggers plaintext fallback. In a staging environment with partial configuration, session data (user_id, email, name, role) could be stored unencrypted in Redis.

**Remediation:** Catch only the specific "key not configured" RuntimeError, and log a warning when falling back to plaintext. Consider making encryption mandatory in staging as well.

---

## P3 — Low / Housekeeping

### P3-1: Gunicorn Access Log May Contain Sensitive Query Parameters

**File:** `backend/gunicorn_config.py`, line 39

The access log format includes `%(r)s` which logs the full request line including query parameters:

```python
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sus'
```

While passwords are sent in request bodies (not query params), some endpoints accept sensitive information as query parameters (e.g., email verification token at `/auth/verify-email?token=...`, reset password token at `/auth/reset-password?token=...`). These tokens appear in Gunicorn access logs.

**Remediation:** Consider using a custom access log format that strips query parameters from the request path, or truncate them to a safe length.

---

### P3-2: Common Password List Is Small (200 Entries)

**File:** `backend/auth/password.py`, lines 19–212

The blocklist contains approximately 200 passwords. While this covers the most common choices, NIST SP 800-63B recommends checking against a larger corpus. The check is case-insensitive (line 238), which is good, but the list does not include many keyboard patterns, l33tspeak variants, or contextual passwords (e.g., "rateshift", "electricity", "energy123").

**Remediation:** Consider expanding the blocklist to 10,000+ entries using the HaveIBeenPwned top passwords list, or integrate the `zxcvbn` library for more comprehensive strength estimation. Add domain-specific words ("rateshift", "electricity", "kwh") to the blocklist.

---

### P3-3: X-Process-Time Header Exposed in Non-Production Environments

**File:** `backend/app_factory.py`, lines 436–438

```python
if not settings.is_production:
    response.headers["X-Process-Time"] = str(process_time)
```

This header reveals internal processing time in development and staging environments. While production is protected, staging may be internet-accessible. Processing time can be used for timing attacks (e.g., inferring whether a user exists based on response time differences).

**Remediation:** Consider removing this header in staging as well, or restrict it to development only.

---

### P3-4: Error Details Exposed in Non-Production/Non-Staging 500 Responses

**File:** `backend/app_factory.py`, lines 502–510

```python
if settings.environment in ("production", "staging"):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
return JSONResponse(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    content={"detail": str(exc)},
)
```

In development and test environments, raw exception messages (which may contain database queries, file paths, or configuration details) are returned in HTTP responses. If a development instance is accidentally exposed, this becomes an information disclosure vector.

**Remediation:** This is acceptable for local development. Ensure development instances are never exposed to the public internet.

---

### P3-5: User Profile `current_supplier_id` Accepts Arbitrary String

**File:** `backend/api/v1/users.py`, line 119

```python
current_supplier_id: str | None = None
```

The `UserProfileUpdate` model accepts any string for `current_supplier_id` without validating it as a UUID or checking that the supplier exists. While this field is only writable by the authenticated user for their own profile (no IDOR risk), an attacker could store arbitrary data in this field.

**Remediation:** Add UUID format validation and optionally verify the supplier exists.

---

### P3-6: Sentry `send_default_pii=False` Is Correctly Set (Positive Finding Noted)

**File:** `backend/app_factory.py`, line 329

Sentry is configured with `send_default_pii=False`, which prevents accidental PII leakage to error tracking. This is good practice.

---

## Files With No Issues Found

The following files were reviewed and found to have no security issues:

- `backend/auth/__init__.py` — Clean lazy-loading pattern, no security concerns.
- `frontend/components/auth/LoginForm.tsx` — Proper input validation, no XSS vectors, correct `autoComplete` attributes.
- `frontend/components/auth/SignupForm.tsx` — Comprehensive password validation, terms acceptance required, proper form handling.
- `frontend/app/(app)/auth/login/page.tsx` — Thin wrapper, no security concerns.
- `frontend/app/(app)/auth/signup/page.tsx` — Thin wrapper, no security concerns.
- `frontend/app/(app)/auth/callback/page.tsx` — Simple redirect to dashboard, no auth bypass.
- `frontend/app/(app)/auth/forgot-password/page.tsx` — Does not reveal whether email exists (line 89: "If an account exists..."), proper security practice.
- `frontend/app/(app)/auth/verify-email/page.tsx` — Proper token-based verification flow.
- `frontend/app/api/auth/[...all]/route.ts` — Lazy handler initialization, proper error handling, no auth bypass.
- `frontend/lib/auth/client.ts` — Correctly uses `window.location.origin` for baseURL, preventing SSRF.
- `frontend/lib/utils/url.ts` — Solid URL validation using `URL` constructor with origin comparison.
- `backend/utils/encryption.py` — AES-256-GCM with random nonce, proper key length validation.
- `backend/config/secrets.py` — 1Password integration with TTL cache, no secret leakage in logs.
- `backend/api/v1/webhooks.py` — Proper HMAC-SHA256 signature verification with constant-time comparison.
- `backend/api/v1/billing.py` — Stripe webhook signature verification, idempotency guard, redirect domain allowlist.
- `backend/api/v1/internal/__init__.py` — All internal routes gated by `verify_api_key` dependency.
- `backend/api/v1/notifications.py` — All endpoints properly scoped to `current_user.user_id`.
- `backend/api/v1/user.py` — Proper auth dependency, no IDOR.
- `backend/middleware/tracing.py` — Safe ASCII validation for caller-supplied request IDs.

---

## Summary

### Overall Assessment: GOOD with targeted improvements needed

The RateShift authentication and authorization system demonstrates strong security engineering across most areas. The architecture — Better Auth managing sessions on the frontend, Neon Auth tables queried by the backend, AES-256-GCM encrypted Redis cache, and httpOnly cookies with SameSite=Lax — represents a well-considered design.

### Key Strengths

1. **Session cookies:** httpOnly=true, Secure=true in production, SameSite=Lax — correctly preventing XSS token theft and CSRF attacks.
2. **Password policy:** 12-character minimum with complexity requirements and common password blocklist.
3. **API key security:** Constant-time comparison (`hmac.compare_digest`) used consistently across all API key and webhook signature verification.
4. **Tier-gating:** `require_tier()` dependency with cache invalidation on Stripe webhook events. Context override protection in the agent API (lines 129–131 of `agent.py`).
5. **Input validation:** SQL parameterized queries throughout (no SQL injection found), redirect URL validation with `isSafeRedirect()`, and strict column allowlists.
6. **CSP:** Nonce-based script-src with strict-dynamic, frame-ancestors 'none', base-uri 'self'.
7. **Internal API protection:** All `/internal/*` routes gated by `verify_api_key` dependency; fail-closed when key is unconfigured.
8. **CORS:** Explicit origin list, credentials enabled, restricted headers.
9. **Production validators:** Settings validators enforce strong secrets, proper key lengths, and separation between JWT_SECRET and INTERNAL_API_KEY in production.

### Critical Gaps

1. **Two OAuth state replay vulnerabilities (P0-1, P0-2)** — signed state tokens have no expiry, allowing indefinite replay.
2. **No login brute-force protection (P1-1)** — Better Auth endpoint has no rate limiting beyond the global 100/min/IP.
3. **60-second stale access after user ban (P1-2)** — Redis session cache not invalidated on ban.
4. **Inconsistent password validation on reset (P1-3)** — reset form validates only length, not full policy.

### Metrics

- **Total findings:** 14 (2 Critical, 3 High, 5 Medium, 4 Low/Housekeeping + 1 positive)
- **SQL injection vectors found:** 0
- **XSS vectors found:** 0
- **IDOR vulnerabilities found:** 0
- **Authentication bypass paths found:** 0
- **Session token leakage in logs:** 0
- **Files with no issues:** 19 of 44

### Risk Matrix

| ID | Finding | CVSS Est. | Exploitability | Impact |
|----|---------|-----------|----------------|--------|
| P0-1 | OAuth callback state no expiry | 7.5 | Medium (requires intercepting callback URL) | High (account takeover via connection binding) |
| P0-2 | Email OAuth state no expiry | 7.5 | Medium (requires intercepting callback URL) | High (email token binding to wrong account) |
| P1-1 | No login rate limit | 7.0 | High (trivially scriptable) | Medium (credential stuffing) |
| P1-2 | Stale ban cache | 5.0 | Low (requires admin action + timing) | Medium (60s continued access) |
| P1-3 | Weak reset password validation | 4.0 | Low (user sets weak password) | Medium (weak credential) |
| P2-1 | In-memory tier cache cross-worker staleness | 3.5 | Low (requires horizontal scale-up) | Medium (stale elevated permissions) |
| P2-2 | Password blocklist membership leakage | 3.0 | Medium (slow enumeration via public endpoint) | Low (blocklist intelligence) |
| P2-3 | Email OAuth callback no ownership check | 6.0 | Medium (requires intercepting callback URL) | High (token binding to wrong account) |
| P2-4 | Middleware cookie-presence-only auth | 2.0 | N/A (UX only) | Low (flash of authenticated UI) |
| P2-5 | Encryption fallback to plaintext | 4.0 | Low (requires misconfiguration) | Medium (session data unencrypted in Redis) |
| P3-1 | Auth tokens in Gunicorn access logs | 3.5 | Low (requires log access) | Medium (token leakage to log readers) |
| P3-2 | Small common password blocklist | 2.0 | Low | Low (weaker password policy) |
| P3-3 | X-Process-Time header in staging | 2.0 | Low | Low (timing oracle) |
| P3-4 | Error details in dev 500 responses | 1.5 | Low (dev only) | Low (info disclosure) |
| P3-5 | Supplier ID accepts arbitrary string | 1.5 | Low (self-only write) | Low (junk data storage) |

### Recommended Priority Order

1. Fix P0-1 and P0-2 (OAuth state expiry) — same day
2. Add login rate limiting to Better Auth config (P1-1) — same sprint
3. Add ban cache invalidation mechanism (P1-2) — same sprint
4. Harmonize password validation on reset page (P1-3) — next sprint
5. Evaluate email OAuth callback ownership check (P2-3) — next sprint
6. Address remaining P2 findings — next sprint cycle
7. P3 items — backlog
