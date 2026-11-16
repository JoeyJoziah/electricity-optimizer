# Audit Report: Authentication & Security

**Date:** 2026-03-23
**Scope:** Auth system, RBAC, session management, CORS, encryption, security headers
**Auditor:** Security Audit Agent (claude-opus-4-6)

**Files Reviewed:** 43 files across backend/auth, backend/middleware, backend/api, backend/config, backend/utils, frontend/middleware, frontend/components/auth, frontend/lib, workers/api-gateway

---

## P0 -- Critical (Fix Immediately)

### 11-P0-1: UtilityAPI Callback State Lacks Timestamp Expiry Enforcement

**File:** `backend/api/v1/connections/common.py`
**Lines:** 42, 60-72, 75-100

The `verify_callback_state()` function defines `OAUTH_STATE_TIMEOUT_SECONDS = 600` (line 42) and embeds a timestamp in the signed state (line 68), but **never checks the timestamp for expiry** during verification. The verification at lines 75-100 only validates the HMAC signature and the 4-part format -- it does not compare the embedded timestamp against the current time.

Compare with the email OAuth state verifier at `backend/services/email_oauth_service.py` lines 99-114, which correctly enforces `max_age_seconds`.

**Impact:** A captured UtilityAPI callback URL with valid HMAC remains usable indefinitely. An attacker who obtains a valid callback URL (from browser history, referrer leak, or logs) can replay it days or months later to bind an arbitrary UtilityAPI authorization to the victim's connection record.

**Remediation:** Add timestamp expiry enforcement mirroring `email_oauth_service.py:verify_oauth_state()`:
```python
try:
    state_time = int(timestamp)
except (ValueError, OverflowError):
    raise HTTPException(status_code=400, detail="Invalid callback state timestamp")
age = int(time.time()) - state_time
if age > OAUTH_STATE_TIMEOUT_SECONDS or age < 0:
    raise HTTPException(status_code=400, detail="Callback state expired")
```

---

## P1 -- High (Fix This Sprint)

### 11-P1-1: No Explicit CSRF Protection Beyond SameSite Cookies

**Files:** `backend/app_factory.py` (lines 436-448), All POST/PUT/DELETE/PATCH endpoints

The backend relies entirely on CORS `allow_credentials=True` (line 439) and Better Auth's `SameSite=Lax` cookie for CSRF protection. There are no explicit CSRF tokens on state-changing endpoints. The UtilityAPI callback (`/connections/direct/callback`) is a GET endpoint that activates connections and triggers data syncs without session authentication.

**Impact:** The HMAC-signed state parameter is the only CSRF defense for callback endpoints. If P0-1 is not fixed, replayed states could modify database records.

**Remediation:** Fix P0-1 (timestamp expiry). For defense-in-depth, consider adding `Origin` header validation middleware.

### 11-P1-2: Session Cookie Accepted Without `__Secure-` Prefix in Production

**File:** `backend/auth/neon_auth.py` (lines 36-38, 278-280)

The backend accepts session tokens from both cookie names in all environments. In production, if a user's first visit arrives over HTTP before HSTS forces HTTPS, the non-`__Secure-` cookie could be transmitted in cleartext.

**Impact:** Session hijacking via network eavesdropping on initial HTTP connection before HSTS redirect.

**Remediation:** In production, only accept the `__Secure-` prefixed cookie.

### 11-P1-3: OAuth HMAC Key Shared with Internal API Authentication

**Files:** `backend/services/email_oauth_service.py` (lines 61-64), `backend/api/v1/connections/common.py` (lines 45-57), `backend/api/dependencies.py` (lines 55-84)

Both OAuth state HMAC signing implementations use `settings.internal_api_key` as the signing key. This same key authenticates all internal service-to-service API calls.

**Impact:** If `INTERNAL_API_KEY` is leaked, an attacker can both forge OAuth states AND authenticate as the internal service.

**Remediation:** Introduce a dedicated `OAUTH_STATE_SECRET` environment variable.

### 11-P1-4: Session Cache Encryption Silently Degrades to Plaintext

**File:** `backend/auth/neon_auth.py` (lines 65-79)

`_encrypt_session_cache()` catches `RuntimeError` and falls back to unencrypted storage. There is no environment check -- this fallback activates in **any** environment, including production.

**Impact:** A key rotation failure or deployment error in production silently stores user PII unencrypted in Redis.

**Remediation:** In production, raise instead of falling back to plaintext.

---

## P2 -- Medium (Fix Soon)

### 11-P2-1: Backend Production CSP Allows `connect-src 'self' https:`

**File:** `backend/middleware/security_headers.py` (line 68)

The production CSP permits fetch/XHR to any HTTPS origin. The frontend `middleware.ts` correctly restricts to specific domains.

**Remediation:** Replace `https:` with specific allowed domains.

### 11-P2-2: Rate Limiter Identifier Spoofable via Fake Bearer Tokens

**File:** `backend/middleware/rate_limiter.py` (lines 475-484)

The `_get_identifier` method hashes any supplied Bearer token without validating it. An attacker can rotate arbitrary tokens to get distinct rate-limit buckets.

**Impact:** Complete rate limit bypass for unauthenticated attackers.

**Remediation:** Always use IP-based identification at the middleware level.

### 11-P2-3: Stripe Webhook Endpoint Susceptible to Payload Flooding

**File:** `backend/api/v1/billing.py` (lines 319-523)

The `/billing/webhook` endpoint is publicly accessible and subject only to global rate limits.

**Remediation:** Add stricter per-IP rate limit on the webhook path.

### 11-P2-4: `X-Forwarded-For` Trusted Without Proxy Validation

**File:** `backend/middleware/rate_limiter.py` (lines 488-496)

If requests reach Render directly (bypassing the CF Worker), the `X-Forwarded-For` header is spoofable.

**Remediation:** In production, reject requests lacking `CF-Connecting-IP`.

### 11-P2-5: `style-src 'unsafe-inline'` in Frontend CSP

**File:** `frontend/middleware.ts` (line 46)

Allows arbitrary inline styles, which can be leveraged for CSS-based data exfiltration.

**Remediation:** Investigate using a style nonce.

---

## P3 -- Low / Housekeeping

### 11-P3-1: Password Strength Endpoint Returns Detailed Check Breakdown

**File:** `backend/api/v1/auth.py` (lines 237-277)

The unauthenticated `POST /auth/password/check-strength` returns exact checks that pass/fail.

**Remediation:** Return only `valid` and `strength` to unauthenticated callers.

### 11-P3-2: Common Password List Contains Only ~170 Entries

**File:** `backend/auth/password.py` (lines 37-230)

NIST SP 800-63B recommends checking against 100,000+ commonly-used passwords.

**Remediation:** Integrate Have I Been Pwned Passwords API.

### 11-P3-3: `.env` File Contains Placeholder Development Secrets

**File:** `.env`

Contains `POSTGRES_PASSWORD=testpassword123`, etc. Properly `.gitignore`d.

**Remediation:** Rename to `.env.example` for clarity.

### 11-P3-4: Permissions-Policy Mismatch Between CF Worker and Backend

**Files:** `backend/middleware/security_headers.py` (lines 100-108), `workers/api-gateway/src/middleware/security.ts` (line 60)

CF Worker uses `payment=(self), geolocation=(self)` while backend uses `payment=(), geolocation=()`.

**Remediation:** Align both to `payment=(), geolocation=()`.

### 11-P3-5: Missing `X-XSS-Protection: 0` Header in Backend

**File:** `backend/middleware/security_headers.py`

**Remediation:** Add `headers["X-XSS-Protection"] = "0"`.

### 11-P3-6: Gunicorn Access Log Includes Full Request Line

**File:** `backend/gunicorn_config.py` (line 39)

`%(r)s` logs the full request line including query parameters.

**Remediation:** Use `%(U)s` (URL path only).

---

## Files With No Issues Found

- `backend/auth/__init__.py` -- Clean lazy-import pattern
- `backend/utils/encryption.py` -- AES-256-GCM with proper nonces, key validation
- `backend/api/v1/internal/__init__.py` -- All routes gated behind `Depends(verify_api_key)`
- `backend/api/v1/connections/crud.py` -- All queries scoped by `user_id`. No IDOR
- `backend/api/v1/connections/rates.py` -- Ownership check on every query
- `backend/api/v1/connections/analytics.py` -- Properly gated behind `require_paid_tier`
- `backend/api/v1/user.py` -- Preferences scoped to authenticated user
- `backend/api/v1/users.py` -- `UPDATABLE_COLUMNS` allowlist prevents mass assignment
- `backend/api/v1/notifications.py` -- All operations scoped to `current_user.user_id`
- `backend/api/v1/savings.py` -- Gated by `require_tier("pro")`, scoped to user
- `backend/config/secrets.py` -- 1Password integration with TTL cache
- `backend/services/email_oauth_service.py` -- Correct HMAC + timestamp + constant-time comparison
- `backend/api/v1/connections/email_oauth.py` -- User ownership verification, state HMAC validation
- `backend/services/stripe_service.py` -- Proper webhook signature verification
- `backend/api/v1/billing.py` -- Redirect URL domain allowlist
- `workers/api-gateway/src/middleware/internal-auth.ts` -- Fail-closed, `crypto.subtle.timingSafeEqual`
- `frontend/middleware.ts` -- Per-request CSP nonce, proper route protection
- `frontend/components/auth/AuthGuard.tsx` -- Client-side auth gate with loading state
- `frontend/lib/hooks/useAuth.tsx` -- httpOnly cookie sessions, `isSafeRedirect()`
- `frontend/lib/api/client.ts` -- 401 loop protection, circuit breaker
- `backend/services/community_service.py` -- nh3 XSS sanitization, fail-closed AI moderation

---

## Summary

| Severity | Count | Key Areas |
|----------|-------|-----------|
| **P0 - Critical** | 1 | UtilityAPI callback state replay (missing timestamp expiry) |
| **P1 - High** | 4 | Missing CSRF defense-in-depth, session cookie HTTP fallback, OAuth HMAC key reuse, silent encryption degradation |
| **P2 - Medium** | 5 | Broad CSP connect-src, rate limiter spoofing, webhook DoS, XFF trust, unsafe-inline styles |
| **P3 - Low** | 6 | Password endpoint info leak, small password list, .env placeholders, header inconsistencies |
| **No Issues** | 21 files | Encryption, IDOR protection, tier gating, webhook signatures, OAuth flows, XSS sanitization |

**Overall Assessment:** The authentication and authorization architecture is well-designed with strong fundamentals. The P0 finding (missing timestamp enforcement on UtilityAPI callback state) is a straightforward 15-minute fix. The P1 findings are defense-in-depth improvements. P2 and P3 items are hardening measures.

**Estimated remediation effort:** P0: 15 minutes. P1s: 2-3 hours total. P2s: 3-4 hours total. P3s: 1-2 hours total.
