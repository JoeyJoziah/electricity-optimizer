# Security Audit Report: Authentication, Authorization & Security

**Date**: 2026-03-18
**Scope**: Authentication, authorization, and security controls across the RateShift full stack
**Files Reviewed**: backend/auth/__init__.py, backend/auth/password.py, backend/auth/neon_auth.py, backend/middleware/__init__.py, backend/middleware/security_headers.py, backend/middleware/rate_limiter.py, backend/middleware/tracing.py, backend/config/settings.py, backend/api/v1/auth.py, backend/api/dependencies.py, backend/api/v1/billing.py, backend/api/v1/agent.py, backend/api/v1/internal/__init__.py, backend/api/v1/webhooks.py, backend/api/v1/compliance.py, backend/api/v1/feedback.py, backend/api/v1/connections/portal_scrape.py, backend/app_factory.py, backend/utils/encryption.py, backend/services/stripe_service.py, backend/services/community_service.py, frontend/lib/auth/client.ts, frontend/lib/auth/server.ts, frontend/app/api/auth/[...all]/route.ts, frontend/components/auth/LoginForm.tsx, frontend/components/auth/SignupForm.tsx, frontend/lib/hooks/useAuth.tsx, frontend/lib/utils/url.ts, frontend/lib/api/client.ts, frontend/lib/config/env.ts, frontend/middleware.ts, workers/api-gateway/src/index.ts, workers/api-gateway/src/config.ts, workers/api-gateway/src/router.ts, workers/api-gateway/src/types.ts, workers/api-gateway/src/middleware/internal-auth.ts, workers/api-gateway/src/middleware/security.ts, workers/api-gateway/src/middleware/rate-limiter.ts, workers/api-gateway/src/middleware/cors.ts, workers/api-gateway/src/middleware/cache.ts, workers/api-gateway/src/handlers/proxy.ts, workers/api-gateway/src/handlers/scheduled.ts, .env.example

***

## Executive Summary

The RateShift application demonstrates a mature security posture with well-implemented defense-in-depth across its stack. The architecture -- Better Auth (frontend) for session management, Neon Auth (database) for session storage, FastAPI (backend) for session validation, and Cloudflare Workers (edge) for rate limiting and bot detection -- is sound. Session-based authentication with httpOnly cookies is a strong choice over JWT-in-localStorage.

However, this audit identified **2 P0-Critical**, **5 P1-High**, **8 P2-Medium**, and **7 P3-Low** findings that require attention, several of which could lead to security bypass, timing attacks, or privilege escalation under specific conditions.

**Controls Reviewed**: 84 | **Findings Identified**: 22 | **Critical/High Issues**: 7

## P0 — Critical (Fix Immediately)

### P0-01: Metrics Endpoint Uses Non-Constant-Time String Comparison for API Key

**File**: `backend/app_factory.py`, line 519

The `/metrics` endpoint uses Python's `!=` operator for API key comparison, which is **not constant-time**:

```python
if settings.internal_api_key and api_key != settings.internal_api_key:
    return JSONResponse(status_code=403, content={"detail": "Forbidden"})
```

This contrasts with `verify_api_key` in `backend/api/dependencies.py` (line 86) which correctly uses `hmac.compare_digest()`. An attacker can measure response time differences to extract the `INTERNAL_API_KEY` byte-by-byte.

Additionally, when `settings.internal_api_key` is falsy, the condition short-circuits to False, making the metrics endpoint **completely unauthenticated**.

**Remediation**: Replace `!=` with `hmac.compare_digest()` and add fail-closed guard for unconfigured key.

### P0-02: Rate Limit Bypass Key Comparison Uses JavaScript `===` (Not Timing-Safe)

**File**: `workers/api-gateway/src/middleware/rate-limiter.ts`, line 26

```typescript
if (bypassKey && env.RATE_LIMIT_BYPASS_KEY && bypassKey === env.RATE_LIMIT_BYPASS_KEY) {
    return { allowed: true, remaining: Infinity, limit: Infinity, resetAt: 0 };
}
```

JavaScript's `===` is not timing-safe. The same codebase uses `timingSafeEqual()` for `INTERNAL_API_KEY` validation in `internal-auth.ts` (line 38), but this bypass key check does not.

**Remediation**: Use `timingSafeEqual()` for bypass key comparison.

## P1 — High (Fix This Sprint)

### P1-01: Session Cache Stores Cleartext Session Data in Redis Without Encryption

**File**: `backend/auth/neon_auth.py`, lines 112-125

The session cache stores `SessionData` as plaintext JSON in Redis (user_id, email, name, role). If Redis is compromised, an attacker gains all active user sessions and can forge cache entries to impersonate any user for up to 60 seconds.

**Remediation**: Encrypt cached session data using `FIELD_ENCRYPTION_KEY` (AES-256-GCM, already available in `utils/encryption.py`).

### P1-02: No CSRF Protection on State-Changing Backend API Endpoints

**Files**: All `POST/PUT/PATCH/DELETE` routes in `backend/api/v1/`

The backend relies on session cookies with `credentials: 'include'` but has no CSRF token validation. While CORS and SameSite provide partial protection, older browsers may not enforce SameSite.

**Remediation**: Verify and enforce `SameSite=Strict` on session cookies, or implement double-submit CSRF token pattern.

### P1-03: Development Error Messages Leak Exception Details in Staging

**File**: `backend/app_factory.py`, lines 498-506

Error sanitization covers production and staging, but defaults to raw exception details. If `ENVIRONMENT` is misconfigured, raw exception messages are returned.

**Remediation**: Default to sanitized responses (fail-closed). Only return raw details when `settings.environment == "development"`.

### P1-04: OAuth Social Login PKCE Not Explicitly Enabled

**File**: `frontend/lib/auth/server.ts`, lines 80-98

Social provider configuration does not explicitly enable PKCE.

**Remediation**: Explicitly configure `pkce: true` or verify Better Auth enables it by default.

### P1-05: In-Memory Rate Limiter Fallback Creates Per-Worker Isolation

**File**: `backend/middleware/rate_limiter.py`, lines 266-300

When Redis is unavailable, each worker maintains independent rate limit state, giving attackers `rate_limit * worker_count` effective requests.

**Remediation**: Reduce in-memory fallback limits or return 503 for sensitive endpoints when Redis is unavailable.

## P2 — Medium (Fix Soon)

### P2-01: Session Token Hash Truncated to 32 Hex Characters
**File**: `backend/auth/neon_auth.py`, line 69. SHA-256 truncated to 128 bits. Use full 64-char digest.

### P2-02: Better Auth cookieCache Allows 5-Minute Stale Sessions
**File**: `frontend/lib/auth/server.ts`, lines 104-107. 5-minute frontend cookie cache + 60s backend Redis = banned users retain access up to 5 min. Reduce to 60s.

### P2-03: No Rate Limiting on OAuth Social Login Endpoints
OAuth initiation through Better Auth's `/api/auth/*` routes may bypass CF Worker rate limiting. Verify or add server-side throttling.

### P2-04: Password Check Endpoint Rate Limit Uses Potentially Spoofable Client IP
**File**: `backend/api/v1/auth.py`, line 181. Uses `request.client.host` instead of `CF-Connecting-IP`/`X-Forwarded-For`.

### P2-05: X-Process-Time Header Leaks Timing Information in Non-Production
**File**: `backend/app_factory.py`, line 431. Exposed in staging. Only expose in development.

### P2-06: Validation Error Handler Strips input but Not url or loc Fields
**File**: `backend/app_factory.py`, lines 466-478. `loc` field reveals API structure details.

### P2-07: Agent Endpoint Allows User-Supplied Context to Inject Arbitrary Data
**File**: `backend/api/v1/agent.py`, lines 121-127. While `tier` and `user_id` are re-asserted, arbitrary keys can influence AI behavior. Whitelist allowed context keys.

### P2-08: Frontend next.config.js API Rewrites May Bypass CF Worker Auth
Frontend proxies API calls through Vercel directly to Render, bypassing CF Worker security controls (bot detection, edge rate limiting).

## P3 — Low / Housekeeping

- **P3-01**: `style-src 'unsafe-inline'` in CSP — common for React/Tailwind, low risk
- **P3-02**: Magic link expiry 5 min — consider reducing to 3 min
- **P3-03**: Root endpoint exposes environment name — remove in production
- **P3-04**: Missing `preload` directive in CF Worker HSTS header
- **P3-05**: (POSITIVE) Swagger/ReDoc correctly disabled in production
- **P3-06**: (POSITIVE) `send_default_pii=False` correctly set for Sentry
- **P3-07**: Common password blocklist is 200 entries — expand to 10,000+

***

## Files With No Issues Found

- `backend/utils/encryption.py` — AES-256-GCM implementation is solid
- `frontend/lib/utils/url.ts` — `isSafeRedirect()` properly validates same-origin

## Summary

The security architecture is sound with defense-in-depth across three layers (CF Worker, FastAPI, Neon Auth). Two P0 findings are straightforward 15-minute fixes (timing-safe comparisons). The five P1 findings address session security, CSRF protection, and rate limiting resilience. Total estimated remediation: ~12 hours. The strongest security controls are session-based auth with httpOnly cookies, AES-256-GCM field encryption, multi-tier rate limiting, and proper webhook signature verification.
