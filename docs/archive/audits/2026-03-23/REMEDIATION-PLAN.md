# RateShift Codebase Audit — Remediation Plan

**Audit Date:** 2026-03-23
**Produced by:** 20-agent parallel audit (Claude Opus 4.6)
**Total Findings:** ~560 across 20 domain reports
**Breakdown:** ~64 P0 | ~151 P1 | ~172 P2 | ~173 P3

---

## Cross-Cutting Patterns (Most Dangerous)

### Pattern 1: Missing Transaction Error Handling / Rollback
**Reports:** 07-P0-04/05/06/07/08, 08-P0-01/02, 06-P0-03, 12-P0-01
**Impact:** 12+ services perform INSERT/UPDATE + commit with no `try/except/rollback`. A constraint violation mid-transaction leaves the AsyncSession dirty, poisoning subsequent operations. This is the **single most pervasive P0 pattern**.
**Fix:** Systematic pass through all service write methods to add `try/except` with `await self._db.rollback()`.

### Pattern 2: Exception Details Leaked to HTTP Clients
**Reports:** 18-P0-1/2/3, 06-P2-*, 07-P2-*, 17-P1-*
**Impact:** Raw `str(exc)` returned in API responses in 15+ endpoints. SQLAlchemy exceptions routinely include `DATABASE_URL`. Cryptographic exceptions expose algorithm details. The dev-mode exception handler (`app_factory.py:557`) returns full tracebacks if `ENVIRONMENT=development` is accidentally deployed.
**Fix:** Return generic error messages in all environments. Log `str(e)` server-side only.

### Pattern 3: Unsafe Deserialization / Model Loading Without Integrity Verification
**Reports:** 13-P0-1 (pickle RCE), 13-P0-3 (joblib without HMAC), 13-P1-2
**Impact:** ML model files loaded via `torch.load(weights_only=False)` and `joblib.load()` without integrity checks enable arbitrary code execution. A poisoned model file → full server compromise.
**Fix:** Delete `weights_only=False` fallback. Add HMAC-SHA256 verification to all pickle/joblib load sites.

---

## Sprint 0: Critical Security & Data Integrity (Day 1)

**Objective:** Eliminate all P0 findings that represent active security vulnerabilities or data corruption risks.

### S0-1: Fix UtilityAPI callback state timestamp expiry (11-P0-1)
- **File:** `backend/api/v1/connections/common.py:75-100`
- **Action:** Add timestamp comparison to `verify_callback_state()`, mirror `email_oauth_service.py:verify_oauth_state()`
- **LOE:** 15 minutes

### S0-2: Remove unsafe pickle deserialization path (13-P0-1)
- **File:** `ml/inference/predictor.py:247-251`
- **Action:** Delete `weights_only=False` legacy branch; all paths use `state_dict` + `weights_only=True`
- **LOE:** 30 minutes

### S0-3: Add HMAC integrity verification to joblib.load sites (13-P0-3)
- **Files:** `ml/models/ensemble.py:377-381`, `ml/training/cnn_lstm_trainer.py` (scaler.pkl)
- **Action:** Extract `_verify_model_integrity` from `predictor.py` to `ml/utils/integrity.py`; call before all `joblib.load` sites
- **LOE:** 1 hour

### S0-4: Fix IDOR in connection PATCH endpoint (06-P0-2)
- **File:** `backend/api/v1/connections/crud.py:295`
- **Action:** Add `user_id` to WHERE clause on PATCH `/connections/{id}`
- **LOE:** 15 minutes

### S0-5: Encrypt plaintext account numbers in utility_accounts (06-P0-1)
- **File:** `backend/api/v1/utility_accounts.py:61`
- **Action:** Replace `.encode()` with `encrypt_field()` for `account_number`
- **LOE:** 30 minutes

### S0-6: Sanitize all exception-to-client leaks (18-P0-1/2/3)
- **Files:** `backend/routers/predictions.py:483,572,668`, `backend/app_factory.py:557`, `backend/api/v1/internal/portal_scan.py:183`
- **Action:** Replace `detail=f"...{str(e)}"` with generic messages; log original server-side
- **LOE:** 45 minutes

### S0-7: Fix missing try/except/rollback on write methods — batch 1 (07-P0-04/05/06/07/08)
- **Files:** `affiliate_service.py`, `notification_service.py`, `community_service.py`, `savings_service.py`, `gas_rate_service.py`
- **Action:** Add `try/except` with `await self._db.rollback()` to all write methods
- **LOE:** 1.5 hours

### S0-8: Fix ForecastObservationRepository write safety (08-P0-01/02)
- **File:** `backend/repositories/forecast_observation_repository.py:30-99,174-226`
- **Action:** Wrap write methods in try/except with rollback, consistent with other repos
- **LOE:** 45 minutes

### S0-9: Fix asyncio.gather with shared AsyncSession (07-P0-01)
- **File:** `backend/services/community_service.py:428-490`
- **Action:** Ensure AI calls are pure HTTP (no session access) or switch to sequential processing
- **LOE:** 30 minutes

### S0-10: Fix database migration issues (12-P0-*)
- **Action:** Fix migration numbering collision, A/B test UNIQUE constraint bug, missing FK references
- **LOE:** 1 hour

**Sprint 0 Total LOE: ~7 hours**

---

## Sprint 1: Security Hardening & Auth (Days 2-3)

### S1-1: Dedicate OAuth state HMAC secret (11-P1-3, 18-P1-1)
- **Action:** Add `OAUTH_STATE_SECRET` env var, stop reusing `INTERNAL_API_KEY` for HMAC signing
- **LOE:** 45 minutes

### S1-2: Production-only __Secure- cookie enforcement (11-P1-2)
- **File:** `backend/auth/neon_auth.py:36-38`
- **Action:** In production, reject session tokens from non-`__Secure-` cookie
- **LOE:** 30 minutes

### S1-3: Fail-hard on session cache encryption in production (11-P1-4)
- **File:** `backend/auth/neon_auth.py:65-79`
- **Action:** Raise on encryption failure in production instead of falling back to plaintext
- **LOE:** 20 minutes

### S1-4: Centralize ML_MODEL_SIGNING_KEY in settings.py (18-P1-2)
- **Action:** Move from `os.environ.get()` to `settings.py` with production validator
- **LOE:** 20 minutes

### S1-5: Expand log sanitizer patterns (18-P1-4)
- **File:** `backend/app_factory.py:63-68`
- **Action:** Add patterns for `re_`, `gsk_`, `AIza`, `sk_test_`, Bearer tokens, Authorization headers
- **LOE:** 30 minutes

### S1-6: Stop logging Stripe key prefix (18-P1-5)
- **File:** `backend/services/stripe_service.py:37`
- **Action:** Log only "live" or "test" classification, not key characters
- **LOE:** 10 minutes

### S1-7: Fix rate limiter identifier spoofing (11-P2-2)
- **File:** `backend/middleware/rate_limiter.py:475-484`
- **Action:** Always use IP-based identification at middleware level
- **LOE:** 30 minutes

### S1-8: Restrict backend CSP connect-src (11-P2-1)
- **File:** `backend/middleware/security_headers.py:68`
- **Action:** Replace `https:` with specific allowed domains
- **LOE:** 20 minutes

### S1-9: Add AES-256-GCM Associated Data (18-P1-6)
- **File:** `backend/utils/encryption.py:44,65`
- **Action:** Pass field name + record ID as AAD. Requires re-encryption migration
- **LOE:** 2 hours (includes migration)

### S1-10: Add encryption key rotation mechanism (18-P1-7)
- **File:** `backend/utils/encryption.py`
- **Action:** Add key versioning, dual-key support, rotation script
- **LOE:** 3 hours

**Sprint 1 Total LOE: ~8 hours**

---

## Sprint 2: Test Quality & CI Reliability (Days 3-4)

### S2-1: Rewrite auth bypass tests to use cookie-based auth model (16-P0-1)
- **File:** `tests/security/test_auth_bypass.py`
- **Action:** Replace JWT fixtures with Better Auth session cookie testing, mirror `test_security_adversarial.py` patterns
- **LOE:** 2 hours

### S2-2: Remove HTTP 500 acceptance from 14 test assertions (16-P0-3)
- **File:** `backend/tests/test_api.py`
- **Action:** Replace `in [200, 500]` with explicit expected codes; add `pytest.skip()` for DB-absent scenarios
- **LOE:** 1 hour

### S2-3: Replace deprecated `datetime.utcnow()` (16-P0-2)
- **Files:** `tests/security/test_auth_bypass.py`, review `pyproject.toml` DeprecationWarning suppression
- **Action:** Use `datetime.now(UTC)` throughout; narrow global warning filter
- **LOE:** 30 minutes

### S2-4: Patch real `asyncio.sleep()` in timing tests (16-P1-1)
- **File:** `backend/tests/test_integrations.py:296,314,363,419,531`
- **Action:** Patch `asyncio.sleep` or expose `_clock` parameter on CircuitBreaker
- **LOE:** 45 minutes

### S2-5: Downscope module-level TestClient fixtures (16-P1-3)
- **Files:** `test_api.py:23`, `test_security_adversarial.py:174`
- **Action:** Change `scope="module"` to `scope="function"`
- **LOE:** 20 minutes

### S2-6: Remove deprecated session-scoped event_loop fixture (16-P1-4)
- **File:** `backend/tests/conftest.py:34-39`
- **Action:** Delete fixture (redundant with `asyncio_mode = "auto"`)
- **LOE:** 10 minutes

### S2-7: Pin time-dependent fixture base_time (16-P1-5)
- **File:** `backend/tests/conftest.py:176-196`
- **Action:** Use `datetime(2024, 1, 15, 0, 0, tzinfo=UTC)` instead of `datetime.now(UTC)`
- **LOE:** 10 minutes

### S2-8: Add rate limiter conftest for top-level security tests (16-P1-6)
- **File:** `tests/security/test_rate_limiting.py`
- **Action:** Add `conftest.py` to `tests/security/` with rate limiter reset fixture
- **LOE:** 30 minutes

### S2-9: Replace weak E2E assertions (16-P2-1/2/3)
- **Files:** `authentication.spec.ts`, `page-load.spec.ts`, `missing-pages.spec.ts`
- **Action:** Replace `body.toBeVisible()` and OR-condition assertions with semantic checks
- **LOE:** 2 hours

### S2-10: Add proxy.ts unit tests (16-P3-4)
- **File:** New `workers/api-gateway/test/proxy.test.ts`
- **Action:** Test 2-tier caching, CORS, graceful KV degradation, per-isolate metrics
- **LOE:** 2 hours

**Sprint 2 Total LOE: ~9 hours**

---

## Sprint 3: Backend Services Hardening (Days 4-5)

### S3-1: Missing try/except/rollback — batch 2 (07-P0-06/07/08 + remaining)
- **Files:** All remaining service write methods without error handling
- **Action:** Systematic sweep adding rollback to every `commit()` call
- **LOE:** 2 hours

### S3-2: Fix Groq empty choices IndexError (17-P0-1)
- **File:** `backend/services/agent_service.py:305`
- **Action:** Guard `response.choices[0]` with empty-list check
- **LOE:** 10 minutes

### S3-3: Fix cache stampede None fallthrough (17-P0-2)
- **File:** `backend/services/analytics_service.py:137-145`
- **Action:** Return empty result or raise when cache lock is held and re-check fails
- **LOE:** 20 minutes

### S3-4: Fix agent TOCTOU race in rate limiting (07-P0-03)
- **File:** `backend/services/agent_service.py:120-163`
- **Action:** Combine check+increment into atomic `UPDATE ... WHERE count < :limit RETURNING count`
- **LOE:** 30 minutes

### S3-5: Fix background task session lifecycle (07-P0-02)
- **File:** `backend/services/agent_service.py:307-335`
- **Action:** Document no-DB-session contract; add new session creation if DB writes are needed
- **LOE:** 20 minutes

### S3-6: Replace stdlib logging with structlog in inconsistent services (07-P1-*)
- **Action:** 19 services use stdlib `logging`; replace with `structlog.get_logger()` for consistent JSON output
- **LOE:** 2 hours

### S3-7: Convert row-by-row INSERTs to batch inserts (07-P1-*)
- **Action:** Several services use row-by-row INSERT patterns where `bulk_create()` would be safer and faster
- **LOE:** 1.5 hours

### S3-8: Fix EnsemblePredictor blocking I/O (19-P0-1)
- **Files:** `ml/inference/ensemble_predictor.py:121-222`, `backend/services/price_service.py:196`
- **Action:** Pre-load weights eagerly via `asyncio.to_thread` at construction; replace psycopg2 with async engine
- **LOE:** 1.5 hours

### S3-9: Compile log sanitizer regex at module load (19-P0-2)
- **File:** `backend/app_factory.py` log sanitizer
- **Action:** Pre-compile regex patterns; store as module-level `_COMPILED_PATTERNS`
- **LOE:** 20 minutes

### S3-10: Fix CNN-LSTM fabricated prediction intervals (13-P0-2)
- **File:** `ml/training/cnn_lstm_trainer.py:121-124`
- **Action:** Replace ±10% fabricated bounds with empirical rolling quantiles or conformal prediction
- **LOE:** 3 hours

**Sprint 3 Total LOE: ~11.5 hours**

---

## Sprint 4: Frontend & Accessibility (Days 5-6)

### S4-1: Fix modal hardcoded ID collision (01-P0-1)
- **File:** `frontend/components/ui/modal.tsx:67`
- **Action:** Use `React.useId()` for dynamic `aria-labelledby` association
- **LOE:** 15 minutes

### S4-2: Add keyboard support to clickable div cards (01-P0-2)
- **Files:** `HeatingOilDashboard.tsx:98-99`, `PropaneDashboard.tsx:98-99`
- **Action:** Add `role="button"`, `tabIndex={0}`, `onKeyDown` handler
- **LOE:** 20 minutes

### S4-3: Replace array index keys with stable keys (01-P0-3/5/6/7)
- **Files:** `RatePageContent.tsx:100`, `GasRatesContent.tsx:184`, `OptimizationReport.tsx:114`, `AgentChat.tsx:160`
- **Action:** Use unique identifiers (supplier name, composite key, message ID)
- **LOE:** 30 minutes

### S4-4: Fix BillUploadForm polling race condition (01-P0-4)
- **File:** `frontend/components/connections/BillUploadForm.tsx:100-161`
- **Action:** Add AbortController cleanup; cancel in-flight requests on unmount
- **LOE:** 30 minutes

### S4-5: Fix useAuth stale closure (02-P0-1)
- **Action:** Ensure auth hook callbacks reference current state
- **LOE:** 30 minutes

### S4-6: Fix useGeocoding race condition (02-P0-2)
- **Action:** Cancel pending geocoding requests when input changes
- **LOE:** 30 minutes

### S4-7: Add focus traps to inline modal dialogs (01-P1-8)
- **File:** `SuppliersContent.tsx` — SwitchWizard and SetSupplierDialog
- **Action:** Use Modal component or add focus trap, Escape handling, scroll lock
- **LOE:** 45 minutes

### S4-8: Fix ARIA violations (01-P1-10, 15, 16)
- **Files:** `SetSupplierDialog.tsx` (missing listbox role), `DataExport.tsx`, `ForecastWidget.tsx` (missing labels)
- **Action:** Add `role="listbox"`, `aria-label` associations
- **LOE:** 30 minutes

### S4-9: Validate external URLs with isSafeHref (01-P1-12/13)
- **Files:** `CCAAlert.tsx:48`, `DealerList.tsx:49-55`
- **Action:** Add `isSafeHref()` validation on external URLs
- **LOE:** 15 minutes

### S4-10: Deduplicate US_STATES arrays (01-P1-14)
- **Files:** `AnalyticsDashboard.tsx`, `WaterDashboard.tsx`, `HeatingOilDashboard.tsx`, `PropaneDashboard.tsx`
- **Action:** Import from shared `@/lib/constants/regions`
- **LOE:** 20 minutes

**Sprint 4 Total LOE: ~4.5 hours**

---

## Sprint 5: Database & Schema Fixes (Day 6)

### S5-1: Fix remaining database schema issues (12-P0-*)
- **Action:** Fix empty string NOT NULL bypass, unbounded VARCHAR PK, missing foreign keys
- **LOE:** 2 hours

### S5-2: Add missing indexes identified in audit (12-P1-*)
- **Action:** Create migration for missing composite indexes on high-cardinality query paths
- **LOE:** 1 hour

### S5-3: Fix Pydantic model / DB schema mismatches (08-P0-03/04)
- **Action:** Align model validators with database constraints; add missing field validations
- **LOE:** 1 hour

### S5-4: Fix repository N+1 query patterns (08-P1-*)
- **Action:** Add eager loading / joinedload for identified N+1 patterns
- **LOE:** 1.5 hours

### S5-5: Fix Dockerfile conflicts (20-P0-01)
- **Action:** Consolidate to single production Dockerfile; remove stale backend/Dockerfile
- **LOE:** 30 minutes

### S5-6: Fix E2E migration coverage gap (20-P0-03)
- **Action:** Ensure E2E environment applies all 60 migrations, not just first 3
- **LOE:** 30 minutes

### S5-7: Fix ORIGIN_URL exposure (20-P0-02)
- **Action:** Remove ORIGIN_URL from public-facing config
- **LOE:** 15 minutes

**Sprint 5 Total LOE: ~7 hours**

---

## Sprint 6: Dependencies & Infrastructure (Week 2)

### S6-1: Pin floating dependency versions (10-P0-*)
- **Action:** Pin all `>=` constraints to exact versions in requirements.txt
- **LOE:** 1 hour

### S6-2: Resolve dependency conflicts (10-P1-*)
- **Action:** Address version incompatibilities flagged by pip-audit
- **LOE:** 2 hours

### S6-3: Fix CI/CD workflow gaps (20-P1-*)
- **Action:** Add missing CI checks, fix workflow permissions, add timeout guards
- **LOE:** 2 hours

### S6-4: Add .mcp.json and .composio.lock to .gitignore (18-P2-4/5)
- **Action:** Add to .gitignore, remove from tracking
- **LOE:** 10 minutes

### S6-5: Remove stale docker-compose.prod.yml (18-P2-3)
- **Action:** Delete or update vestigial pre-Neon Docker Compose
- **LOE:** 15 minutes

**Sprint 6 Total LOE: ~5.5 hours**

---

## Sprint 7: P2 Housekeeping Batch (Week 2-3)

### S7-1: Frontend P2 fixes — CSS class assertions, test IDs (16-P2-5, 05-P2-*)
### S7-2: Backend P2 fixes — internal endpoint error sanitization (18-P2-6)
### S7-3: ML P2 fixes — MockForecaster tests for CI without TF (16-P2-6)
### S7-4: Middleware P2 fixes — XFF validation, webhook rate limits (11-P2-3/4)
### S7-5: Performance P2 fixes — connection pooling, caching improvements (19-P2-*)

**Sprint 7 Total LOE: ~12 hours**

---

## Sprint 8: P3 Housekeeping Batch (Week 3)

### S8-1: Convert unconditional test.skip to test.fixme with issue refs (16-P3-1)
### S8-2: Remove redundant @pytest.mark.asyncio decorators (16-P3-2)
### S8-3: Add migration content assertions for 056-060 (16-P3-3)
### S8-4: Document asyncio.sleep(0) calls (16-P3-5)
### S8-5: Fix frontend mutable module-level test state (16-P3-6)
### S8-6: Align Permissions-Policy between CF Worker and backend (11-P3-4)
### S8-7: Gunicorn access log path-only format (11-P3-6)
### S8-8: Docstring placeholder cleanups (18-P3-1/2)

**Sprint 8 Total LOE: ~6 hours**

---

## Effort Summary

| Sprint | Focus | Tasks | LOE |
|--------|-------|-------|-----|
| **0** | Critical Security & Data Integrity | 10 | ~7h |
| **1** | Security Hardening & Auth | 10 | ~8h |
| **2** | Test Quality & CI Reliability | 10 | ~9h |
| **3** | Backend Services Hardening | 10 | ~11.5h |
| **4** | Frontend & Accessibility | 10 | ~4.5h |
| **5** | Database & Schema Fixes | 7 | ~7h |
| **6** | Dependencies & Infrastructure | 5 | ~5.5h |
| **7** | P2 Housekeeping Batch | 5 | ~12h |
| **8** | P3 Housekeeping Batch | 8 | ~6h |
| **Total** | | **75 tasks** | **~70.5h** |

---

## Top 10 Critical Findings (Ordered by Risk)

| # | ID | Finding | Report | Risk |
|---|-----|---------|--------|------|
| 1 | 13-P0-1 | PyTorch `weights_only=False` — arbitrary code execution via pickle | ML Pipeline | RCE |
| 2 | 13-P0-3 | joblib.load without HMAC integrity verification | ML Pipeline | RCE |
| 3 | 06-P0-2 | IDOR on PATCH `/connections/{id}` — missing user_id in WHERE | API Routes | Data breach |
| 4 | 11-P0-1 | UtilityAPI callback state replay — no timestamp expiry | Auth & Security | Account takeover |
| 5 | 06-P0-1 | Plaintext account numbers stored via `.encode()` not `encrypt_field()` | API Routes | PII exposure |
| 6 | 18-P0-1 | Exception details (incl DATABASE_URL) leaked in prediction responses | Config & Secrets | Info disclosure |
| 7 | 07-P0-01 | asyncio.gather with shared AsyncSession — silent data corruption | Backend Services | Data corruption |
| 8 | 08-P0-01 | ForecastObservationRepo write methods — no rollback on failure | Repositories | Data corruption |
| 9 | 16-P0-1 | Auth bypass tests test JWT model, not actual cookie-based auth | Test Quality | False security |
| 10 | 19-P0-1 | EnsemblePredictor blocking sync I/O on async event loop | Performance | Cascading timeouts |

---

## 3 Most Dangerous Cross-Cutting Patterns

### 1. Transaction Safety Gap (12+ write paths without rollback)
Affects: affiliate_service, notification_service, community_service, savings_service, gas_rate_service, forecast_observation_repository, and 6+ more. A single constraint violation in any of these paths leaves the AsyncSession in a dirty state, causing cascading failures for all subsequent database operations in the same request lifecycle.

### 2. Information Disclosure via Exception Propagation (15+ endpoints)
Affects: predictions router (3 endpoints), app_factory general handler, portal_scan, email_scan, data_pipeline, and internal endpoints. Raw Python exceptions containing DATABASE_URL, file paths, and crypto algorithm details are returned to HTTP clients. The development-mode exception handler in `app_factory.py` returns full tracebacks to any client if `ENVIRONMENT=development` is set.

### 3. Unsafe Deserialization / Missing Model Integrity (3 load paths)
Affects: PyTorch model loading (legacy path), LightGBM model loading, scikit-learn scaler loading. All three paths execute arbitrary Python during deserialization. The HMAC verification infrastructure exists for PyTorch but was not applied to LightGBM or scaler files. A supply-chain attack on any model artifact → full server compromise.

---

## First 5 Recommended Tasks

1. **Fix IDOR in connection PATCH** (S0-4) — 15 minutes, prevents unauthorized data modification
2. **Fix UtilityAPI callback state timestamp expiry** (S0-1) — 15 minutes, prevents replay attacks
3. **Remove unsafe pickle deserialization** (S0-2) — 30 minutes, eliminates RCE vector
4. **Encrypt plaintext account numbers** (S0-5) — 30 minutes, protects PII at rest
5. **Sanitize exception-to-client leaks** (S0-6) — 45 minutes, stops info disclosure

These 5 tasks address the highest-risk vulnerabilities in under 2.5 hours combined.
