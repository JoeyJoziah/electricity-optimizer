# Remediation Plan — Codebase Audit 2026-03-17

> 617 findings across 30 reports. 33 P0, 147 P1, 233 P2, 204 P3.

---

## Sprint 0 — Immediate Hotfixes (Day 1)

All S-effort, zero-dependency fixes. Can be done in a single PR.

### 0.1 Rotate leaked credentials
- **Finding**: 28/P0-1 — `backend/.env` contains 4 live secrets on disk
- **Action**: `rm backend/.env`. Rotate REDIS_URL password, JWT_SECRET, INTERNAL_API_KEY, FIELD_ENCRYPTION_KEY in Render dashboard + 1Password. Note: FIELD_ENCRYPTION_KEY rotation requires re-encrypting portal credentials in DB.
- **Files**: `backend/.env` (delete), Render dashboard, 1Password vault
- **Effort**: S (rotation) + M (re-encryption migration if FIELD_ENCRYPTION_KEY changed)
- **Severity**: P0 | **Blocks**: Nothing

### 0.2 Fix broken beta code verification
- **Finding**: 02/P0-1 — `hmac.compare_digest(code, code)` compares input vs itself
- **Action**: Change to `hmac.compare_digest(code, stored_beta_code)`
- **File**: `backend/api/v1/beta.py` ~line 48
- **Effort**: S | **Severity**: P0

### 0.3 Fix open redirect in OAuth callback
- **Finding**: 02/P0-2 — `frontend_url` not validated
- **Action**: Validate against `isSafeRedirect()` or hardcode allowed origins
- **File**: `backend/api/v1/connections/common.py` (OAuth callback handler)
- **Effort**: S | **Severity**: P0

### 0.4 Fix `hmac.new` → `hmac.HMAC` (5 sites)
- **Finding**: 26/P0-1 — deprecated in Python 3.13
- **Action**: Replace `hmac.new(` with `hmac.HMAC(` at all 5 call sites
- **Files**: `backend/api/v1/webhooks.py:48`, `backend/services/email_oauth_service.py:48,62`, `backend/api/v1/connections/common.py:72,93`
- **Effort**: S | **Severity**: P0

### 0.5 Fix SSRF in portal scraper
- **Finding**: 05/P0-1 — unvalidated portal login URL
- **Action**: Validate URL scheme (https only) and domain against utility allowlist; block private IP ranges
- **File**: `backend/services/portal_scraper_service.py`
- **Effort**: S | **Severity**: P0

### 0.6 Fix dunning commit gap
- **Finding**: 06/P0-1 — missing `await db.commit()` after recording payment failure
- **Action**: Add commit call after `record_payment_failure()`
- **File**: `backend/services/dunning_service.py`
- **Effort**: S | **Severity**: P0

### 0.7 Add missing middleware routes
- **Finding**: 14/P1-1, 16/P0-1 — `/analytics`, `/gas-rates`, `/community-solar`, `/beta-signup` not in protectedPaths
- **Action**: Add all 4 paths to `protectedPaths` array and `config.matcher`
- **File**: `frontend/middleware.ts`
- **Effort**: S | **Severity**: P0

### 0.8 Remove verification URL from logs
- **Finding**: 26/P3-6, 17/P2-4 — token leaked to Vercel log drains
- **Action**: Remove `url=${url}` from console.log in `sendVerificationEmail`
- **File**: `frontend/lib/auth/server.ts:57`
- **Effort**: S | **Severity**: P1 (high value, trivial fix)

### 0.9 Fix EmailConnectionFlow query-param trust
- **Finding**: 13/P0-1 — `?connected=<id>` bypasses OAuth flow
- **Action**: Validate `connectedId` against user's actual connections via API call before entering connected state
- **File**: `frontend/components/connections/EmailConnectionFlow.tsx:56-63`
- **Effort**: S | **Severity**: P0

### 0.10 Zero out portal password after submission
- **Finding**: 13/P0-2 — password persists in React state
- **Action**: Add `setPortalPassword('')` immediately after successful POST; add https-only scheme guard on `portalLoginUrl`
- **File**: `frontend/components/connections/PortalConnectionFlow.tsx`
- **Effort**: S | **Severity**: P0

### 0.11 Fix onboarding auto-complete on error
- **Finding**: 16/P1-3 — completes onboarding even on mutation failure
- **Action**: Move `completeOnboarding()` call into `onSuccess` callback only
- **File**: `frontend/app/(app)/onboarding/page.tsx`
- **Effort**: S | **Severity**: P1

### 0.12 Align password minimum to 12 chars
- **Finding**: 14/P1-2, 16/P1-2 — Settings page uses 8, backend requires 12
- **Action**: Change `minLength` from 8 to 12 in Settings change-password form
- **File**: `frontend/app/(app)/settings/page.tsx`
- **Effort**: S | **Severity**: P1

### 0.13 Add UUID type hints to path params
- **Finding**: 01/P1 — 5 endpoints accept `str` instead of `uuid.UUID`
- **Action**: Change type annotation from `str` to `uuid.UUID` on path params
- **Files**: 5 API endpoint files identified in report 01
- **Effort**: S | **Severity**: P1

### 0.14 Fix beta-signup hardcoded Gmail + broken POST
- **Finding**: 16/P0-2 — POSTs to non-existent `/api/beta-signup`, hardcodes personal Gmail
- **Action**: Either remove the beta-signup form entirely or wire it to a real endpoint; remove hardcoded email
- **Files**: `frontend/app/(app)/beta-signup/page.tsx`, `frontend/app/privacy/page.tsx`
- **Effort**: S | **Severity**: P0

---

## Sprint 1 — Security & GDPR (Days 2-3)

### 1.1 GDPR deletion cascade — Migration 052
- **Finding**: 27/P0-1, 27/P0-2, 27/P1-2, 27/P1-3
- **Action**: Create migration 052 adding FK constraints with ON DELETE CASCADE to: `user_savings`, `recommendation_outcomes`, `model_predictions`, `model_ab_assignments`, `referrals` (referrer=CASCADE, referee=SET NULL). Add NOT NULL to `model_config.is_active/created_at/updated_at`. Fix 051 non-idempotent ADD CONSTRAINT.
- **Files**: New `backend/migrations/052_fk_gdpr_cascade_round2.sql`
- **Effort**: M | **Severity**: P0 | **Blocks**: 1.2

### 1.2 Fill GDPR test stubs + update deletion endpoint
- **Finding**: 10/P0-1, 08/P0-1
- **Action**: Fill all 14 empty GDPR test stubs with real assertions. Update GDPR deletion endpoint to cover all tables with user_id. Add CI check for FK coverage.
- **Files**: `backend/tests/test_gdpr_compliance.py`, `backend/api/v1/compliance.py`
- **Effort**: M | **Severity**: P0 | **Depends**: 1.1

### 1.3 CSP nonce migration — remove `unsafe-inline`
- **Finding**: 21/P0-1, 17/P2-1
- **Action**: Implement nonce-based CSP via Next.js middleware. Remove `'unsafe-inline'` from `script-src` and `style-src`. Update OneSignal and Clarity script loading.
- **Files**: `frontend/middleware.ts`, `frontend/next.config.js`
- **Effort**: M | **Severity**: P0

### 1.4 Enforce email_verified in backend
- **Finding**: 26/P1-1
- **Action**: Add `AND u."emailVerified" = true` to session query in `_get_session_from_token`, or create `require_verified_email` dependency
- **File**: `backend/auth/neon_auth.py`
- **Effort**: S | **Severity**: P1

### 1.5 Fix security test suite
- **Finding**: 11/P0-1, 11/P0-2, 11/P0-3
- **Action**: Rewrite auth bypass tests to use session-based auth (not JWT). Fix SQL injection tests to assert 400/422 (not accept 500). Fix rate limiting tests with realistic thresholds.
- **Files**: `tests/security/test_auth_bypass.py`, `tests/security/test_sql_injection.py`, `tests/security/test_rate_limiting.py`
- **Effort**: M | **Severity**: P0

### 1.6 Fix checkout proxy security
- **Finding**: 17/P1-1, 17/P1-2, 17/P1-4
- **Action**: Add `getAuth().api.getSession(request)` validation. Sanitize error payloads. Validate `success_url`/`cancel_url` with `isSafeRedirect()` or construct server-side.
- **File**: `frontend/app/api/checkout/route.ts`
- **Effort**: S | **Severity**: P1

### 1.7 Wire password-check rate limiter to Redis
- **Finding**: 26/P1-2
- **Action**: Inject shared Redis client into `_password_check_limiter`
- **File**: `backend/api/v1/auth.py`
- **Effort**: S | **Severity**: P1

### 1.8 Fix CF Worker cache key injection
- **Finding**: 22/P1-1
- **Action**: Sanitize query params before building cache key; use URL-safe encoding
- **File**: `workers/api-gateway/src/cache.ts`
- **Effort**: S | **Severity**: P1

### 1.9 Narrow CSP connect-src wildcards
- **Finding**: 17/P2-2
- **Action**: Replace `*.onrender.com` and `*.vercel.app` with exact hostnames
- **File**: `frontend/next.config.js`
- **Effort**: S | **Severity**: P2

---

## Sprint 2 — ML Safety & Performance (Days 4-5)

### 2.1 Fix unsafe model deserialization
- **Finding**: 23/P0-1, 23/P0-2
- **Action**: Set `weights_only=True` on all `torch.load()` calls. Replace joblib/pickle model loading with safetensors or add SHA-256 hash verification.
- **Files**: `ml/models/*.py`, `backend/services/learning_service.py`
- **Effort**: M | **Severity**: P0

### 2.2 Fix unbounded SELECT in ForecastService
- **Finding**: 29/PERF-01
- **Action**: Replace raw SELECT with `GROUP BY DATE_TRUNC('day', timestamp)` aggregation. Add LIMIT clause as safety net.
- **File**: `backend/services/forecast_service.py:128-148`
- **Effort**: S | **Severity**: P0

### 2.3 Fix SSE setQueryData shape mismatch
- **Finding**: 29/PERF-13
- **Action**: Update cache updater to use `ApiCurrentPriceResponse` shape (object with `prices` array, not bare array). Once fixed, remove history cache invalidation (PERF-04).
- **File**: `frontend/lib/hooks/useRealtime.ts:76-84`
- **Effort**: S | **Severity**: P2 (correctness bug)

### 2.4 Replace sequential per-region DB calls in check-alerts
- **Finding**: 29/PERF-03
- **Action**: Replace sequential `for region in regions` loop with single `DISTINCT ON (region)` SQL query
- **File**: `backend/api/v1/internal/alerts.py:81-90`
- **Effort**: S | **Severity**: P1

### 2.5 Push optimal-window computation to SQL
- **Finding**: 29/PERF-02
- **Action**: Replace Python sliding-window loop with SQL window function `AVG() OVER (ROWS BETWEEN...)`
- **File**: `backend/services/price_service.py:395-425`
- **Effort**: M | **Severity**: P1

### 2.6 Normalize usePriceHistory queryKey
- **Finding**: 29/PERF-05
- **Action**: Change queryKey from `['prices', 'history', region, hours]` to `['prices', 'history', region, days]`
- **File**: `frontend/lib/hooks/usePrices.ts:33-41`
- **Effort**: S | **Severity**: P1

### 2.7 Pipeline Redis INCR + EXPIRE
- **Finding**: 29/PERF-11
- **Action**: Use `pipeline()` for atomic INCR + EXPIRE in `record_login_attempt`
- **File**: `backend/middleware/rate_limiter.py:328-330`
- **Effort**: S | **Severity**: P2

### 2.8 Add ML input validation + model freshness check
- **Finding**: 23/P1-3, 23/P1-4
- **Action**: Add input-range validation on prediction inputs; add model freshness TTL check before serving predictions
- **Files**: `ml/models/ensemble_predictor.py`, `backend/services/model_version_service.py`
- **Effort**: M | **Severity**: P1

### 2.9 Fix Diffbot API token in query params
- **Finding**: 04/P0-2
- **Action**: Move Diffbot token from query params to Authorization header
- **File**: `backend/services/rate_scraper_service.py`
- **Effort**: S | **Severity**: P0

### 2.10 Fix ML predictor race condition
- **Finding**: 04/P0-1
- **Action**: Add lock or use module-level singleton pattern for ML predictor initialization
- **File**: `backend/services/forecast_service.py`
- **Effort**: S | **Severity**: P0

---

## Sprint 3 — Infrastructure & Config (Days 6-7)

### 3.1 Sync render.yaml with all 42+ env vars
- **Finding**: 25/P1-1, 28/P2-7
- **Action**: Add all missing env vars (GEMINI_API_KEY, GROQ_API_KEY, COMPOSIO_API_KEY, ENABLE_AI_AGENT, FRONTEND_URL, UTILITYAPI_KEY, GMAIL_CLIENT_ID/SECRET, OUTLOOK_CLIENT_ID/SECRET) with `sync: false`
- **File**: `render.yaml`
- **Effort**: S | **Severity**: P1

### 3.2 Fix CF Worker ORIGIN_URL
- **Finding**: 25/P0-2
- **Action**: Verify actual Render service URL and update `ORIGIN_URL` in wrangler.toml
- **File**: `workers/api-gateway/wrangler.toml:40`
- **Effort**: S | **Severity**: P0

### 3.3 Fix Dockerfile port/CMD alignment
- **Finding**: 25/P0-1
- **Action**: Align EXPOSE, HEALTHCHECK, and CMD to use same PORT default; verify `--timeout-graceful-shutdown` flag support
- **File**: `Dockerfile` (root)
- **Effort**: S | **Severity**: P0

### 3.4 Fix GHA workflow permissions
- **Finding**: 24/P1-1, 24/P1-5
- **Action**: Add explicit `permissions:` blocks to 2 workflows missing them. Pin `claude-flow@latest` to a specific version.
- **Files**: `.github/workflows/detect-rate-changes.yml`, `.github/workflows/self-healing-monitor.yml`
- **Effort**: S | **Severity**: P1

### 3.5 Fix shell injection in self-healing monitor
- **Finding**: 24/P1-3
- **Action**: Quote matrix variables in shell commands
- **File**: `.github/workflows/self-healing-monitor.yml`
- **Effort**: S | **Severity**: P1

### 3.6 Move vars.BACKEND_URL to secrets
- **Finding**: 24/P1-2
- **Action**: Change `vars.BACKEND_URL` to `secrets.BACKEND_URL` in detect-rate-changes workflow
- **File**: `.github/workflows/detect-rate-changes.yml`
- **Effort**: S | **Severity**: P1

### 3.7 Fix JWT_SECRET ephemeral generation
- **Finding**: 28/P1-3
- **Action**: Add warning log when JWT_SECRET is absent; raise in staging/production
- **File**: `backend/config/settings.py:59-62`
- **Effort**: S | **Severity**: P1

### 3.8 Fix BETTER_AUTH_SECRET presence check
- **Finding**: 28/P2-4
- **Action**: Add `if env == "production" and not v: raise ValueError(...)` to validator
- **File**: `backend/config/settings.py:258-268`
- **Effort**: S | **Severity**: P2

### 3.9 Delete or sync requirements.prod.txt
- **Finding**: 30/P1-2
- **Action**: Verify if referenced anywhere; if not, delete. If used, sync with `backend/requirements.txt`
- **File**: `backend/requirements.prod.txt`
- **Effort**: S | **Severity**: P1

### 3.10 Fix SecretsManager vault name
- **Finding**: 28/P1-1
- **Action**: Change `OP_VAULT = "Electricity Optimizer"` to `"RateShift"`
- **File**: `backend/config/secrets.py:40`
- **Effort**: S | **Severity**: P1

---

## Sprint 4 — Frontend Polish & Test Quality (Days 8-10)

### 4.1 Fix Zustand settings not cleared on sign-out
- **Finding**: 18/P1-1
- **Action**: Add `useSettingsStore.getState().reset()` to sign-out handler
- **Files**: `frontend/store/settings.ts`, `frontend/lib/hooks/useAuth.tsx`
- **Effort**: S | **Severity**: P1

### 4.2 Fix useGeocoding calling /internal/ endpoint
- **Finding**: 18/P1-2
- **Action**: Change to a public geocoding endpoint or proxy through a frontend API route
- **File**: `frontend/lib/hooks/useGeocoding.ts`
- **Effort**: S | **Severity**: P1

### 4.3 Add useAgentQuery cleanup + tests
- **Finding**: 18/P1-3, 20/P0-1
- **Action**: Add AbortController cleanup on unmount. Write tests covering sendQuery, error, and cancel flows.
- **Files**: `frontend/lib/hooks/useAgentQuery.ts`, `frontend/__tests__/hooks/useAgentQuery.test.ts`
- **Effort**: M | **Severity**: P0+P1

### 4.4 Fix queryAgent bypassing apiClient
- **Finding**: 19/P1-3
- **Action**: Route agent queries through shared apiClient to get retry, circuit breaker, and 401 redirect
- **File**: `frontend/lib/api/agent.ts`
- **Effort**: S | **Severity**: P1

### 4.5 Fix duplicate redirect validation
- **Finding**: 19/P1-1
- **Action**: Extend `isSafeRedirect()` to also check `pathname.startsWith('/')` and replace inline checks in useAuth.tsx
- **Files**: `frontend/lib/utils/url.ts`, `frontend/lib/hooks/useAuth.tsx`
- **Effort**: S | **Severity**: P1

### 4.6 Encode SSE URL region param
- **Finding**: 19/P1-2
- **Action**: Add `encodeURIComponent(region)` to SSE URL construction
- **File**: `frontend/lib/api/sse.ts`
- **Effort**: S | **Severity**: P1

### 4.7 Wire AbortController signals in PortalConnectionFlow
- **Finding**: 13/P2-1
- **Action**: Pass `controller.signal` to `createPortalConnection()` and `triggerPortalScrape()`
- **File**: `frontend/components/connections/PortalConnectionFlow.tsx`
- **Effort**: S | **Severity**: P2

### 4.8 Add PostForm accessibility (htmlFor, aria-invalid, role=alert)
- **Finding**: 13/P1-5
- **Action**: Add `id`/`htmlFor` pairs, `aria-invalid`, `role="alert"` to all form fields
- **File**: `frontend/components/community/PostForm.tsx`
- **Effort**: S | **Severity**: P1

### 4.9 Fix VoteButton stale count closure
- **Finding**: 13/P1-6
- **Action**: Capture `optimisticCount` at click time instead of using `count` prop in error handler
- **File**: `frontend/components/community/VoteButton.tsx`
- **Effort**: S | **Severity**: P1

### 4.10 Add URL scheme validation for server-supplied hrefs
- **Finding**: 13/P2-6, 15/P1-5
- **Action**: Create `isSafeHref()` helper and apply to all `enrollment_url`, `opt_out_url`, `program_url` renderings
- **Files**: `frontend/lib/utils/url.ts`, `frontend/components/community-solar/CommunitySolarContent.tsx`, `frontend/components/cca/CCAInfo.tsx`
- **Effort**: S | **Severity**: P1

---

## Sprint 5 — Remaining P1s & P2 Cleanup (Days 11-14)

### 5.1 Backend service fixes
- Fix f-string SQL guarded by assert (03/P0-1) — parameterize query
- Fix compliance exception leakage (02/P0-3) — sanitize error response
- Fix `asyncio.gather` on shared AsyncSession (08/P0-2) — use sequential loop
- Fix GDPR consent fields silent False (08/P0-1) — raise ValueError when unset
- Fix internal alert 500 raw exception (10/P0-2) — sanitize error message
- Add `X-RateLimit-Reset` header (26/P1-3)
- Fix notification dedup partial index (29/PERF-07)
- **Effort**: M | **Severity**: P0-P1

### 5.2 Frontend remaining fixes
- Fix side-effect in DataExport render (12/P1-1) — move to useEffect
- Fix hardcoded price fallbacks in SuppliersContent (15/P1-1)
- Fix AgentChat character limit bypass (15/P1-3)
- Fix FeedbackModal focus trap (15/P1-5)
- Fix `not-found.tsx` link to /dashboard (16/P1-4)
- Fix ISR rates page fetch timeout (16/P1-5) — add AbortSignal with 10s timeout
- Add `SavingsEstimateCard` negative value guard (13/P1-7)
- Fix `ConnectionAnalytics` sync error silencing (13/P1-8)
- **Effort**: M | **Severity**: P1

### 5.3 CF Worker + infra fixes
- Fix webhook route rate limiting bypass (22/P1-2)
- Add Vary header to cached responses (22/P1-3)
- Fix wrangler.toml compatibility_date (25/P2-6) — update to 2026-03-01
- Fix gunicorn umask (25/P2-7) — change from 0 to 0o022
- Fix Makefile pytest paths (25/P1-4)
- Fix sslmode=disable in prod compose (25/P1-2)
- **Effort**: M | **Severity**: P1-P2

### 5.4 Test quality improvements
- Fix "prices dropping" test documents dead code (20/P0-2)
- Fix Jest better-auth mock missing changePassword (21/P1-3)
- Fix AgentChat cancel button vacuous test guard (20/P1-2)
- Add integration tests for SSE EventSource (20/P1-5)
- Add Settings changePassword tests (20/P1-4)
- **Effort**: M | **Severity**: P0-P1

### 5.5 ML pipeline hardening
- Fix optuna.save_study deprecated API (23/P1-1)
- Fix unbounded HNSW index memory (23/P1-5)
- Fix recursive tree-model lag features (23/P1-6)
- Fix ensemble weight key mismatch (23/P2)
- **Effort**: M | **Severity**: P1-P2

### 5.6 Dependency cleanup
- Schedule ESLint v9/v10 migration (30/P1-3)
- Add nanoid override in package.json (30/P1-1)
- Remove pickle5 from ML requirements (30/P2-5)
- Align TF version caps (30/P2-4)
- Update CF Worker types snapshot (30/P3-6)
- **Effort**: M | **Severity**: P1-P2

---

## Backlog — P2/P3 (post-launch)

Items not covered above, organized by domain:

**Backend P2/P3** (~80 findings): Inconsistent error handling, missing docstrings, unused imports, logging improvements, dead code cleanup
**Frontend P2/P3** (~90 findings): Accessibility improvements, responsive fixes, Zustand selector optimization, component naming inconsistencies
**Infrastructure P2/P3** (~30 findings): Docker cleanup, env example alignment, stale comments
**Database P2/P3** (~8 findings): Version comment fixes, init_neon rename, utility_type enum standardization
**GHA P2/P3** (~18 findings): E2E migration coverage, keepalive cron removal, Dependabot CF Worker scope

---

## Summary

| Sprint | Focus | P0 Fixed | P1 Fixed | Total Fixed | Effort |
|--------|-------|----------|----------|-------------|--------|
| 0 | Immediate hotfixes | 12 | 5 | 17 | 1 day |
| 1 | Security & GDPR | 5 | 8 | 13 | 2 days |
| 2 | ML safety & performance | 4 | 8 | 12 | 2 days |
| 3 | Infrastructure & config | 3 | 10 | 13 | 2 days |
| 4 | Frontend polish & tests | 1 | 12 | 13 | 3 days |
| 5 | Remaining P1s & cleanup | 8 | 25+ | 33+ | 4 days |
| **Total** | | **33** | **68+** | **101+** | **14 days** |

All 33 P0 findings are addressed in Sprints 0-5. The top ~68 P1 findings are explicitly tasked. Remaining P1s and all P2/P3 findings are captured in Sprint 5 and the backlog.
