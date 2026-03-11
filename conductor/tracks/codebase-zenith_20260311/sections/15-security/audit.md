# Section 15: Security (Cross-Cutting) — Clarity Gate Audit

**Date:** 2026-03-12
**Auditor:** Claude Code (Direct)
**Score:** 82/90 (PASS)

---

## Aggregate Scores

| # | Dimension | Score |
|---|-----------|-------|
| 1 | Correctness | 9/10 |
| 2 | Coverage | 9/10 |
| 3 | Security | 10/10 |
| 4 | Performance | 9/10 |
| 5 | Maintainability | 9/10 |
| 6 | Documentation | 9/10 |
| 7 | Error Handling | 9/10 |
| 8 | Consistency | 9/10 |
| 9 | Modernity | 9/10 |
| | **TOTAL** | **82/90** |

---

## Files Analyzed (cross-cutting across ~30 files)

**Auth**: `auth/neon_auth.py` (session validation, Redis cache, cookie/bearer extraction), `lib/auth/client.ts` (Better Auth client), `lib/hooks/useAuth.tsx` (auth context)
**Middleware**: `middleware/security_headers.py` (CSP, HSTS, X-Frame-Options), `middleware/rate_limiter.py` (Redis sliding window, login lockout)
**API Security**: `api/v1/internal/__init__.py` (API key gate), CF Worker (`workers/api-gateway/`) (KV rate limiting, bot detection, HMAC verification)
**Frontend Security**: `lib/api/client.ts` (401 loop prevention, safe redirect), `lib/api/circuit-breaker.ts`
**Tests**: `tests/test_security.py`, `tests/test_security_adversarial.py`, `tests/test_gdpr_compliance.py`, `tests/test_middleware_asgi.py`
**CI Security**: `ci.yml` (Bandit SAST, npm audit), `secret-scan.yml`

---

## Architecture Assessment

Defense-in-depth security architecture spanning 4 layers: (1) Edge — Cloudflare Worker with KV rate limiting (120/30/600 per min), bot detection via CF headers, HMAC-signed internal requests. (2) Backend — SecurityHeadersMiddleware (CSP, HSTS, X-Frame-Options, Permissions-Policy), RateLimitMiddleware (Redis sliding window per-user/IP), session validation via neon_auth tables with Redis cache. (3) Frontend — 401 redirect loop prevention (MAX_401_REDIRECTS=2), safe redirect validation, circuit breaker for gateway errors. (4) CI — Bandit SAST for Python, npm audit for JS, secret scanning workflow.

## HIGH Findings (1)

**H-01: Session cache TTL of 5 minutes means delayed ban/logout propagation**
- File: `auth/neon_auth.py:54`
- `_SESSION_CACHE_TTL = 300` means a banned user can still access the API for up to 5 minutes
- While `invalidate_session_cache()` exists for explicit logout, admin bans don't call it
- Fix: Add a ban-propagation mechanism (e.g., publish ban event that clears cache) or reduce TTL to 60s

## MEDIUM Findings (3)

**M-01: CSP allows 'unsafe-inline' for scripts in development mode**
- File: `middleware/security_headers.py:52`
- Development CSP: `script-src 'self' 'unsafe-inline'` — standard for dev but if dev mode is accidentally enabled in production, XSS protection is weakened
- Fix: Add a startup assertion that `settings.is_development == False` in production

**M-02: Rate limiter in-memory fallback doesn't share state across workers**
- File: `middleware/rate_limiter.py:74`
- When Redis is unavailable, rate limiting falls back to in-memory dict
- In multi-worker deployments (Render uses multiple Uvicorn workers), each worker has its own state
- Effective rate limit becomes N*limit (where N = number of workers)
- Fix: Log a warning when falling back to memory; consider rejecting requests if Redis is down for critical paths

**M-03: No CSRF protection on non-GET endpoints**
- Backend relies on same-origin cookie policy and CORS for CSRF protection
- Better Auth's httpOnly session cookies are sent with `credentials: 'include'`
- While the CF Worker enforces CORS origin checks, the backend doesn't validate the `Origin` header itself
- Fix: Add `Origin` header validation in middleware for state-changing requests, or implement double-submit cookie pattern

## Strengths

- **4-layer defense**: Edge (CF Worker) -> Middleware (security headers + rate limit) -> Auth (neon_auth) -> Frontend (circuit breaker + 401 loop)
- **Session validation**: Direct neon_auth.session table query with Redis cache + explicit logout invalidation
- **Login lockout**: 5 failed attempts -> 15 minute lockout via Redis/memory fallback
- **HSTS with preload**: Production HSTS with `includeSubDomains; preload` (1 year max-age)
- **Permissions-Policy**: Disables camera, microphone, geolocation, payment, USB browser APIs
- **API cache prevention**: `Cache-Control: no-store, no-cache, must-revalidate, private` on API paths
- **Safe redirect**: `isSafeRedirect()` in frontend + `new URL()` origin check in useAuth
- **Swagger disabled in prod**: `if settings.is_production: docs_url=None, redoc_url=None`
- **Security test coverage**: Dedicated `test_security.py`, `test_security_adversarial.py`, `test_gdpr_compliance.py`
- **Bandit SAST in CI**: High-severity Python security scanning as a blocking job
- **AES-256-GCM portal credentials**: Portal scraper credentials encrypted at rest
- **CF Worker bot detection**: `cf-ipcountry`, `cf-connecting-ip`, threat score headers

**Verdict:** PASS (82/90). Strong defense-in-depth security posture with 4-layer architecture. Production-hardened with HSTS, CSP, rate limiting, and comprehensive security test suite. Main concern is session cache TTL for ban propagation and missing explicit CSRF tokens.
