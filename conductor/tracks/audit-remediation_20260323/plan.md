# Implementation Plan: Codebase Audit Remediation 2026-03-23

**Track ID:** audit-remediation_20260323
**Spec:** spec.md
**Full Details:** `.audit-2026-03-23/REMEDIATION-PLAN.md`
**Created:** 2026-03-23
**Status:** [x] Complete

## Overview

Remediate ~560 findings (64 P0, 151 P1, 172 P2, 173 P3) from 20-agent parallel audit sweep. Organized into 9 sprints by risk cluster. Target: P0->0, P1 critical-><20.

---

## Sprint 0: Critical Security & Data Integrity (Day 1, ~7h)

- [x] Task 0.1: Fix UtilityAPI callback state timestamp expiry [11-P0-1]
- [x] Task 0.2: Remove unsafe pickle deserialization path [13-P0-1]
- [x] Task 0.3: Add HMAC integrity verification to joblib.load sites [13-P0-3]
- [x] Task 0.4: Fix IDOR in connection PATCH endpoint [06-P0-2]
- [x] Task 0.5: Encrypt plaintext account numbers in utility_accounts [06-P0-1]
- [x] Task 0.6: Sanitize all exception-to-client leaks [18-P0-1/2/3]
- [x] Task 0.7: Fix missing try/except/rollback on write methods — batch 1 [07-P0-04/05/06/07/08]
- [x] Task 0.8: Fix ForecastObservationRepository write safety [08-P0-01/02]
- [x] Task 0.9: Fix asyncio.gather with shared AsyncSession [07-P0-01]
- [x] Task 0.10: Fix database migration issues [12-P0-*]

## Sprint 1: Security Hardening & Auth (Days 2-3, ~8h)

- [x] Task 1.1: Dedicate OAuth state HMAC secret [11-P1-3, 18-P1-1]
- [x] Task 1.2: Production-only __Secure- cookie enforcement [11-P1-2]
- [x] Task 1.3: Fail-hard on session cache encryption in production [11-P1-4]
- [x] Task 1.4: Centralize ML_MODEL_SIGNING_KEY in settings.py [18-P1-2]
- [x] Task 1.5: Expand log sanitizer patterns [18-P1-4]
- [x] Task 1.6: Stop logging Stripe key prefix [18-P1-5]
- [x] Task 1.7: Fix rate limiter identifier spoofing [11-P2-2]
- [x] Task 1.8: Restrict backend CSP connect-src [11-P2-1]
- [x] Task 1.9: Add AES-256-GCM Associated Data [18-P1-6]
- [x] Task 1.10: Add encryption key rotation mechanism [18-P1-7]

## Sprint 2: Test Quality & CI Reliability (Days 3-4, ~9h)

- [x] Task 2.1: Rewrite auth bypass tests to use cookie-based auth model [16-P0-1]
- [x] Task 2.2: Remove HTTP 500 acceptance from 14 test assertions [16-P0-3]
- [x] Task 2.3: Replace deprecated datetime.utcnow() [16-P0-2]
- [x] Task 2.4: Patch real asyncio.sleep() in timing tests [16-P1-1]
- [x] Task 2.5: Downscope module-level TestClient fixtures [16-P1-3]
- [x] Task 2.6: Remove deprecated session-scoped event_loop fixture [16-P1-4]
- [x] Task 2.7: Pin time-dependent fixture base_time [16-P1-5]
- [x] Task 2.8: Add rate limiter conftest for top-level security tests [16-P1-6]
- [x] Task 2.9: Replace weak E2E assertions [16-P2-1/2/3]
- [x] Task 2.10: Add proxy.ts unit tests [16-P3-4]

## Sprint 3: Backend Services Hardening (Days 4-5, ~11.5h)

- [x] Task 3.1: Missing try/except/rollback — batch 2 [07-P0-06/07/08 + remaining]
- [x] Task 3.2: Fix Groq empty choices IndexError [17-P0-1]
- [x] Task 3.3: Fix cache stampede None fallthrough [17-P0-2]
- [x] Task 3.4: Fix agent TOCTOU race in rate limiting [07-P0-03]
- [x] Task 3.5: Fix background task session lifecycle [07-P0-02]
- [x] Task 3.6: Replace stdlib logging with structlog in inconsistent services [07-P1-*]
- [x] Task 3.7: Convert row-by-row INSERTs to batch inserts [07-P1-*]
- [x] Task 3.8: Fix EnsemblePredictor blocking I/O [19-P0-1]
- [x] Task 3.9: Compile log sanitizer regex at module load [19-P0-2]
- [x] Task 3.10: Fix CNN-LSTM fabricated prediction intervals [13-P0-2]

## Sprint 4: Frontend & Accessibility (Days 5-6, ~4.5h)

- [x] Task 4.1: Fix modal hardcoded ID collision [01-P0-1]
- [x] Task 4.2: Add keyboard support to clickable div cards [01-P0-2]
- [x] Task 4.3: Replace array index keys with stable keys [01-P0-3/5/6/7]
- [x] Task 4.4: Fix BillUploadForm polling race condition [01-P0-4]
- [x] Task 4.5: Fix useAuth stale closure [02-P0-1]
- [x] Task 4.6: Fix useGeocoding race condition [02-P0-2]
- [x] Task 4.7: Add focus traps to inline modal dialogs [01-P1-8]
- [x] Task 4.8: Fix ARIA violations [01-P1-10/15/16]
- [x] Task 4.9: Validate external URLs with isSafeHref [01-P1-12/13]
- [x] Task 4.10: Deduplicate US_STATES arrays [01-P1-14]

## Sprint 5: Database & Schema Fixes (Day 6, ~7h)

- [x] Task 5.1: Fix remaining database schema issues [12-P0-*]
- [x] Task 5.2: Add missing indexes identified in audit [12-P1-*]
- [x] Task 5.3: Fix Pydantic model / DB schema mismatches [08-P0-03/04]
- [x] Task 5.4: Fix repository N+1 query patterns [08-P1-*]
- [x] Task 5.5: Fix Dockerfile conflicts [20-P0-01]
- [x] Task 5.6: Fix E2E migration coverage gap [20-P0-03]
- [x] Task 5.7: Fix ORIGIN_URL exposure [20-P0-02]

## Sprint 6: Dependencies & Infrastructure (Week 2, ~5.5h)

- [x] Task 6.1: Pin floating dependency versions [10-P0-*]
- [x] Task 6.2: Resolve dependency conflicts [10-P1-*]
- [x] Task 6.3: Fix CI/CD workflow gaps [20-P1-*]
- [x] Task 6.4: Add .mcp.json and .composio.lock to .gitignore [18-P2-4/5]
- [x] Task 6.5: Remove stale docker-compose.prod.yml [18-P2-3]

## Sprint 7: P2 Housekeeping Batch (Week 2-3, ~12h)

- [x] Task 7.1: Frontend P2 fixes — CSS class assertions, test IDs [16-P2-5, 05-P2-*]
- [x] Task 7.2: Backend P2 fixes — internal endpoint error sanitization [18-P2-6]
- [x] Task 7.3: ML P2 fixes — MockForecaster tests for CI without TF [16-P2-6]
- [x] Task 7.4: Middleware P2 fixes — XFF validation, webhook rate limits [11-P2-3/4]
- [x] Task 7.5: Performance P2 fixes — connection pooling, caching improvements [19-P2-*]

## Sprint 8: P3 Housekeeping Batch (Week 3, ~6h)

- [x] Task 8.1: Convert unconditional test.skip to test.fixme with issue refs [16-P3-1]
- [x] Task 8.2: Remove redundant @pytest.mark.asyncio decorators [16-P3-2]
- [x] Task 8.3: Add migration content assertions for 056-060 [16-P3-3]
- [x] Task 8.4: Document asyncio.sleep(0) calls [16-P3-5]
- [x] Task 8.5: Fix frontend mutable module-level test state [16-P3-6]
- [x] Task 8.6: Align Permissions-Policy between CF Worker and backend [11-P3-4]
- [x] Task 8.7: Gunicorn access log path-only format [11-P3-6]
- [x] Task 8.8: Docstring placeholder cleanups [18-P3-1/2]
