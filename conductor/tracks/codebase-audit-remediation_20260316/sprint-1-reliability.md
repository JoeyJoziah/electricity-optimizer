# Sprint 1: Auth, Reliability & Race Conditions — COMPLETE

**Status**: COMPLETE
**Started**: 2026-03-16
**Completed**: 2026-03-16
**Commit**: `47617f5` (30 files, +1,496/-239)
**Agents**: 6 parallel workstreams + 1 fix agent (WS-1G)
**Result**: Backend 2,536 passed (+23), Frontend 1,857 passed (+3), 0 failures

## Workstreams

| WS | Agent Type | Tasks | Status |
|----|-----------|-------|--------|
| WS-1A-race | general-purpose | S1-01, S1-02, S1-11 | COMPLETE |
| WS-1B-auth | frontend-developer | S1-03, S1-14, S1-15 | COMPLETE |
| WS-1C-alerts | general-purpose | S1-04, S1-05, S1-06 | COMPLETE |
| WS-1D-payments | general-purpose | S1-07, S1-16, S1-17 | COMPLETE |
| WS-1E-apikeys | general-purpose | S1-08, S1-09, S1-10 | COMPLETE |
| WS-1F-frontend | frontend-developer | S1-12, S1-13 | COMPLETE |
| WS-1G-fixtest | frontend-developer | Fix circuit breaker test regressions | COMPLETE |

## Task Detail

| # | Task | Source | Status |
|---|------|--------|--------|
| S1-01 | Make Redis rate limiter atomic (Lua script) | T3 | DONE |
| S1-02 | Fix SSE connection counter drift (decrement in finally) | T3 | DONE |
| S1-03 | Block context dict from overriding tier in agent.py | 02-P1-01 | DONE |
| S1-04 | Fix check_alerts email_sent=True when no emails sent | 02-P1-02 | DONE |
| S1-05 | Fix free-tier alert count to exclude soft-deleted | 02-P1-03 | DONE |
| S1-06 | Validate utility_type against enum in forecast+neighborhood | 02-P1-04/05 | DONE |
| S1-07 | Fix Stripe webhook bare except | 02-P1-07 | DONE |
| S1-08 | Move API keys from URL params to headers | T9 | DONE |
| S1-09 | Make withdraw_all_consents() atomic | T8 | DONE |
| S1-10 | Add LIMIT to backfill_actuals when region=None | 19-P1-07 | DONE |
| S1-11 | Add SlidingWindowLimiter eviction (LRU/TTL sweep) | 19-P1-08 | DONE |
| S1-12 | Fix portal.ts to use apiClient | 14-P1-07 | DONE |
| S1-13 | Fix useGeocoding to use apiClient | 14-P1-04 | DONE |
| S1-14 | Fix useAuth OAuth to use finally for isLoading | 14-P1-05 | DONE |
| S1-15 | Add useCallback to useRefreshPrices return | 20-P0-02 | DONE |
| S1-16 | Fix CircuitBreaker.recordSuccess() hard-reset | 20-P1-04 | DONE |
| S1-17 | Fix 401/403 tripping circuit breaker | 19-P2-06 | DONE |

## Cross-Agent Issue Found (WS-1G)
- WS-1B accidentally imported `useCallback` from `@tanstack/react-query` instead of `react`
- This caused 44 page-level test failures (ErrorBoundary caught the runtime error)
- WS-1G fixed the import and updated circuit breaker test for gradual HALF_OPEN recovery

## Verification Criteria

- [x] Backend test count: 2,536 passed (increased from 2,513)
- [x] Frontend test count: 1,857 passed (increased from 1,854)
- [x] All existing passing tests still pass
- [x] 17 new tests added (race conditions, billing, integrations, circuit breaker)
- [x] EIA/NREL API keys moved to headers (OWM stays as appid — no header auth)
- [x] GDPR consent withdrawal is atomic (single transaction, rollback on failure)
