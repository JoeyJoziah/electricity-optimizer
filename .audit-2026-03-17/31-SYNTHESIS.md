# Codebase Audit Synthesis — 2026-03-17

## Overview

**30 agents** reviewed **~1,100 files** across backend, frontend, workers, ML, CI/CD, infrastructure, and cross-cutting concerns. Each agent independently produced a P0–P3 severity-classified report.

---

## Total Findings by Severity

| Severity | Count | % |
|----------|-------|---|
| P0 — Critical | 33 | 5.3% |
| P1 — High | 147 | 23.8% |
| P2 — Medium | 233 | 37.8% |
| P3 — Low | 204 | 33.1% |
| **Total** | **617** | 100% |

---

## Per-Report Breakdown

| # | Report | P0 | P1 | P2 | P3 | Total |
|---|--------|----|----|----|----|-------|
| 01 | api-public-core | 1 | 8 | 9 | 9 | 27 |
| 02 | api-public-extended | 3 | 7 | 13 | 10 | 33 |
| 03 | api-internal | 1 | 5 | 8 | 6 | 20 |
| 04 | svc-core | 2 | 6 | 10 | 10 | 28 |
| 05 | svc-integrations | 1 | 5 | 7 | 6 | 19 |
| 06 | svc-infra | 1 | 6 | 8 | 10 | 25 |
| 07 | svc-domain | 0 | 5 | 13 | 7 | 25 |
| 08 | models-repos | 2 | 7 | 8 | 10 | 27 |
| 09 | backend-infra | 0 | 3 | 6 | 4 | 13 |
| 10 | backend-tests-1 | 2 | 6 | 11 | 6 | 25 |
| 11 | backend-tests-2 | 3 | 5 | 9 | 7 | 24 |
| 12 | fe-dashboard-charts | 0 | 2 | 3 | 2 | 7 |
| 13 | fe-connections-forms | 2 | 6 | 7 | 7 | 22 |
| 14 | fe-auth-layout-ui | 0 | 4 | 7 | 10 | 21 |
| 15 | fe-remaining-components | 0 | 5 | 12 | 7 | 24 |
| 16 | fe-app-pages | 2 | 5 | 8 | 7 | 22 |
| 17 | fe-app-api | 2 | 4 | 5 | 5 | 16 |
| 18 | fe-hooks-state | 0 | 4 | 6 | 10 | 20 |
| 19 | fe-lib-types | 0 | 4 | 11 | 7 | 22 |
| 20 | fe-tests-unit | 2 | 6 | 9 | 6 | 23 |
| 21 | fe-css-config | 1 | 5 | 6 | 7 | 19 |
| 22 | cf-worker | 0 | 3 | 8 | 8 | 19 |
| 23 | ml-pipeline | 2 | 5 | 9 | 6 | 22 |
| 24 | gha-workflows | 0 | 6 | 9 | 9 | 24 |
| 25 | infra-deploy | 2 | 5 | 8 | 7 | 22 |
| 26 | auth-security | 1 | 3 | 6 | 6 | 16 |
| 27 | database-migrations | 2 | 5 | 4 | 4 | 15 |
| 28 | config-secrets | 2 | 5 | 7 | 6 | 20 |
| 29 | performance | 1 | 6 | 6 | 4 | 17 |
| 30 | dependencies | 0 | 3 | 6 | 8 | 17 |

---

## Top 10 Critical Findings

These are the highest-impact P0 findings across the entire audit, ranked by blast radius and exploitability.

### 1. Live credentials on developer disk — `backend/.env` (Report 28, P0-1)
**Impact**: 4 live production secrets (Upstash Redis password, JWT_SECRET, INTERNAL_API_KEY, FIELD_ENCRYPTION_KEY) exist in plaintext on disk. FIELD_ENCRYPTION_KEY compromise would allow decryption of all stored utility portal credentials.
**Fix**: Rotate all 4 secrets immediately. Delete `backend/.env`. Confirm file was never committed via `git log --all`.
**Effort**: S | **Urgency**: Immediate

### 2. Unsafe ML model deserialization — `torch.load(weights_only=False)` + unsafe joblib/pickle (Report 23, P0-1/P0-2)
**Impact**: Remote code execution if any `.pth`, `.joblib`, or `.pkl` model file is poisoned. Model files loaded from disk without integrity verification.
**Fix**: Set `weights_only=True` for torch.load; use `safetensors` for model serialization; add SHA-256 hash verification for all model artifacts.
**Effort**: M | **Urgency**: Before launch

### 3. GDPR deletion gaps — 4+ tables missing FK CASCADE on user_id (Reports 27, 08)
**Impact**: `user_savings`, `recommendation_outcomes`, `model_predictions`, `model_ab_assignments` survive user deletion. GDPR Article 17 (right to erasure) violation.
**Fix**: Migration 052 adding FK constraints with ON DELETE CASCADE to all 4 tables.
**Effort**: S | **Urgency**: Before launch

### 4. Broken beta code verification — `hmac.compare_digest(code, code)` (Report 02, P0-1)
**Impact**: Beta access code verification compares the input against itself — always passes. Any string is accepted as a valid beta code.
**Fix**: Change to `hmac.compare_digest(code, stored_code)`.
**Effort**: S | **Urgency**: Immediate

### 5. Open redirect in OAuth email callback (Report 02, P0-2)
**Impact**: `frontend_url` parameter in OAuth callback redirects without origin validation. Attacker can redirect authenticated users to phishing pages post-OAuth.
**Fix**: Validate `frontend_url` against `isSafeRedirect()` before redirecting.
**Effort**: S | **Urgency**: Immediate

### 6. `script-src 'unsafe-inline'` in production CSP (Reports 21, 17)
**Impact**: Completely neutralizes XSS protection from the Content Security Policy. Any injected inline script will execute.
**Fix**: Replace with nonce-based CSP. Next.js supports nonce injection via middleware.
**Effort**: M | **Urgency**: Before launch

### 7. SSRF via unvalidated portal login URL (Report 05, P0-1)
**Impact**: `PortalScraperService` accepts a user-supplied login URL and makes server-side HTTP requests to it. An attacker can probe internal network services.
**Fix**: Validate URL against an allowlist of known utility portal domains; block private IP ranges.
**Effort**: S | **Urgency**: Immediate

### 8. Security test suite provides false assurance (Report 11, P0-1/P0-2/P0-3)
**Impact**: Auth bypass tests use wrong signing secret (tests pass regardless of fix), SQL injection tests whitelist 500 as success, rate limiting tests always pass. The security test suite cannot catch regressions.
**Fix**: Rewrite all 3 test classes to use the actual auth mechanism (session-based, not JWT), properly assert 400/403 codes, and configure realistic rate limit thresholds.
**Effort**: M | **Urgency**: Before launch

### 9. Unbounded SELECT in ForecastService (Report 29, PERF-01)
**Impact**: `/forecast?utility_type=electricity` without a state filter scans 90 days of global price history — potentially millions of rows loaded into memory. Single unauthenticated call can OOM the process.
**Fix**: Push aggregation into SQL with `GROUP BY DATE_TRUNC('day', timestamp)` or add mandatory LIMIT.
**Effort**: S | **Urgency**: Before launch

### 10. `hmac.new` deprecated — broken on Python 3.13+ (Report 26, P0-1)
**Impact**: 5 call sites use `hmac.new()` which was removed in Python 3.13. GitHub webhook, email OAuth, and connection verification all break on Python upgrade.
**Fix**: Replace `hmac.new(...)` with `hmac.HMAC(...)` at all 5 sites.
**Effort**: S | **Urgency**: Immediate (if on Python 3.13) / Before launch (if on 3.12)

---

## Top 3 Cross-Cutting Patterns

### Pattern 1: Inconsistent Trust Boundaries — Frontend Trusts Backend Blindly, Backend Trusts Frontend Inputs

**Span**: Reports 01, 02, 05, 13, 15, 17, 19, 22

The most pervasive pattern across the codebase is a blurred trust boundary between frontend and backend. Specific manifestations:

- **Frontend → Backend**: Several frontend components render server-supplied data (URLs, error messages, HTML content) without sanitization or scheme validation. `enrollment_url`, `opt_out_url`, `last_sync_error`, and `program_url` are all rendered as `href` values directly from API responses (13, 15, 19).
- **Backend → Frontend**: Multiple backend endpoints accept frontend-supplied values (`region`, `portal_login_url`, `frontend_url`, `success_url`) without validation, passing them directly to SQL queries, HTTP requests, or redirect headers (01, 02, 05, 17).
- **CF Worker → Backend**: Cache keys constructed from unsanitized query parameters (22). Webhook route bypasses all rate limiting and bot detection.
- **Test → Production**: Security tests use wrong secrets, accept wrong status codes, and configure unrealistic thresholds (11). Test confidence does not reflect production reality.

**Root cause**: No shared validation library or middleware enforcing input sanitization at system boundaries. Each endpoint implements (or omits) its own validation.

**Fix direction**: Create `backend/lib/validators.py` with shared validators for URLs (scheme allowlist), regions (enum check), and UUIDs (format check). Create `frontend/lib/utils/safe-render.ts` with `isSafeHref()` for all server-supplied links. Apply at every trust boundary.

---

### Pattern 2: GDPR Compliance Gaps Accumulate With Each New Table

**Span**: Reports 08, 10, 27, 28, 06, 07

Each time a new table with `user_id` is added, the GDPR deletion cascade is not consistently applied:

- Migration 051 fixed community/notifications FKs but missed `user_savings`, `recommendation_outcomes`, `model_predictions`, `model_ab_assignments`, and `referrals` (27).
- The GDPR deletion endpoint in `compliance.py` manually lists tables to purge — any table not in that list is silently skipped (08).
- 14 GDPR compliance test stubs are empty and pass silently (10).
- `consent_given` and `consent_timestamp` fields on the User model return `False`/`None` silently when not set, rather than raising (08).

**Root cause**: No automated check that every table with a `user_id` column participates in the deletion cascade. GDPR coverage is manual and audit-driven rather than schema-enforced.

**Fix direction**: Add a CI check that queries `information_schema.columns` for all `user_id` columns and verifies each has a FK to `users(id)` with `ON DELETE CASCADE` (or is explicitly exempted in a whitelist file). Fill in all 14 empty GDPR test stubs.

---

### Pattern 3: Auth Model Is Optimistic Everywhere — Real Enforcement Happens Too Late

**Span**: Reports 14, 16, 17, 18, 26

The entire authentication architecture relies on a layered model where each layer is "optimistic":

- **Next.js middleware** checks cookie *presence* only — no validation (17, 26).
- **Frontend hooks** (useAuth) check session state in memory but don't re-verify on navigation (18).
- **Backend** validates the session token against the database — this is the real enforcement (26).
- **`email_verified`** is carried in SessionData but never checked by any endpoint (26).
- **3-4 app routes** are missing from the middleware matcher entirely: `/analytics`, `/gas-rates`, `/community-solar`, `/beta-signup` (14, 16).
- **Settings page** uses 8-char password minimum while backend requires 12 (14, 16).

The net effect: users with invalid sessions, unverified emails, or crafted cookies can access protected page shells (including loading states, layout chrome, and client-side data) before the first API call triggers a 401. Meanwhile, several routes never even get the optimistic check.

**Root cause**: Auth enforcement is distributed across 4 layers (middleware, frontend hooks, API client 401 handler, backend session validation) with no central documentation of what each layer guarantees. Developers add new routes without updating the middleware matcher.

**Fix direction**:
1. Add all authenticated routes to middleware matcher (immediate).
2. Enforce `email_verified` in the backend session query (add `AND u."emailVerified" = true`).
3. Add a CI check that verifies every route under `(app)/` is in the middleware `protectedPaths` list.
4. Document the auth model's guarantees per layer in `CLAUDE.md`.

---

## Quick Wins (S effort, high impact)

These can each be fixed in under 30 minutes with no architectural changes:

| # | Finding | Report | Fix |
|---|---------|--------|-----|
| 1 | `hmac.compare_digest(code, code)` — self-comparison | 02 | Change 2nd arg to `stored_code` |
| 2 | `hmac.new()` deprecated — 5 sites | 26 | s/hmac.new/hmac.HMAC/ |
| 3 | Open redirect in OAuth callback | 02 | Add `isSafeRedirect()` check |
| 4 | Delete `backend/.env` from disk | 28 | `rm backend/.env` + rotate secrets |
| 5 | Missing middleware routes | 14, 16 | Add 4 paths to `protectedPaths` |
| 6 | Verification URL logged with token | 26, 17 | Remove `url=` from console.log |
| 7 | Portal password not zeroed | 13 | `setPortalPassword('')` after POST |
| 8 | Onboarding auto-completes on error | 16 | Move `completeOnboarding` to `onSuccess` only |
| 9 | `count` stale closure in VoteButton | 13 | Capture `optimisticCount` at click time |
| 10 | UUID path param validation | 01 | Change `str` to `uuid.UUID` type hint on 5 routes |
| 11 | 8-char vs 12-char password min | 14, 16 | Align Settings page to 12 chars |
| 12 | Region slice without `us_` guard | 13 | Add `region?.startsWith('us_')` check |
| 13 | `connected` query-param trust | 13 | Validate against user's connections |
| 14 | Dunning commit missing | 06 | Add `await db.commit()` |
| 15 | `torch.load(weights_only=True)` | 23 | Single kwarg change per call site |

---

## Dependency Map Between Fixes

```
GDPR Migration 052
  ├── Depends on: identifying all user_id tables (Report 27)
  ├── Blocks: GDPR test stubs can be filled (Report 10)
  └── Blocks: GDPR deletion endpoint update (Report 08)

CSP nonce migration
  ├── Depends on: Next.js middleware nonce injection setup
  ├── Blocks: removing 'unsafe-inline' from script-src (Reports 21, 17)
  └── Blocks: removing 'unsafe-inline' from style-src (Report 21)

Auth middleware expansion
  ├── Depends on: route inventory (Report 16)
  ├── Blocks: email_verified enforcement (Report 26)
  └── Blocks: CI route-coverage check

Security test rewrite
  ├── Depends on: understanding actual auth mechanism (session-based)
  ├── Blocks: confidence in auth bypass detection
  └── Blocks: SQL injection regression detection

ML model safety
  ├── torch.load fix is independent (Report 23)
  ├── safetensors migration depends on model retrain (M effort)
  └── Blocks: model integrity verification system

render.yaml sync
  ├── Depends on: confirming all 42 env vars (Report 28)
  ├── Blocks: disaster recovery confidence
  └── Independent of other fixes
```

---

## Hotspot Files (appeared in 3+ reports)

| File | Reports | Finding Count |
|------|---------|---------------|
| `frontend/middleware.ts` | 14, 16, 17, 26 | 6 |
| `frontend/next.config.js` | 17, 21 | 4 |
| `frontend/lib/auth/server.ts` | 17, 26, 28 | 5 |
| `backend/api/v1/billing.py` | 02, 26 | 3 |
| `backend/services/price_service.py` | 29 | 6 (single report, multiple findings) |
| `backend/services/forecast_service.py` | 04, 29 | 4 |
| `backend/middleware/rate_limiter.py` | 26, 29 | 4 |
| `backend/config/settings.py` | 28 | 5 |
| `render.yaml` | 25, 28 | 4 |
| `workers/api-gateway/wrangler.toml` | 22, 25 | 3 |

---

## Strengths Identified Across Reports

Despite the 617 findings, the codebase demonstrates mature engineering practices in several areas:

1. **UUID primary keys and IF NOT EXISTS guards** across all 51 migrations — safe to replay (27)
2. **Atomic Lua sliding-window rate limiter** with TTL leak already fixed (26)
3. **Constant-time HMAC comparison** for API key and webhook verification (26)
4. **Complete loading.tsx/error.tsx coverage** across all authenticated routes (16)
5. **React Query stale-time tuning** prevents unnecessary refetches (29)
6. **nh3 XSS sanitization** on community posts — fail-closed AI moderation (07)
7. **Stripe webhook raw-body handling** reads before middleware parsing (26)
8. **Partial indexes** and CONCURRENTLY index creation throughout migrations (27)
9. **Circuit breaker** auto-fallback from CF Worker to Render on 502/503 (22)
10. **Password policy** meets NIST SP 800-63B (12-char min, 4 complexity classes, 200-entry blocklist) (26)
