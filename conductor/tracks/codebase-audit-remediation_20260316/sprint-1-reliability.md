# Sprint 1: Auth, Reliability & Race Conditions — QUEUED

**Status**: QUEUED (blocked on Sprint 2 completion)
**Target**: Race conditions, auth gaps, data integrity
**Estimated files**: ~35

## Workstreams (Planned)

| WS | Tasks | Focus |
|----|-------|-------|
| WS-1A-race | S1-01, S1-02, S1-11 | Race conditions: Redis atomic, SSE counter, sliding window eviction |
| WS-1B-auth | S1-03, S1-14, S1-15 | Auth hardening: context override block, useAuth finally, useCallback |
| WS-1C-alerts | S1-04, S1-05, S1-06 | Alert correctness: email_sent flag, soft-delete count, utility_type validation |
| WS-1D-payments | S1-07, S1-16, S1-17 | Payment reliability: Stripe bare except, circuit breaker reset, 401/403 trip |
| WS-1E-apikeys | S1-08, S1-09, S1-10 | Security: API keys to headers, atomic consent withdrawal, backfill LIMIT |
| WS-1F-frontend | S1-12, S1-13 | Frontend fixes: portal.ts apiClient, useGeocoding apiClient |

## Task Detail

| # | Task | Source | Files |
|---|------|--------|-------|
| S1-01 | Make Redis rate limiter atomic (Lua script) | T3 | backend/lib/rate_limiter.py |
| S1-02 | Fix SSE connection counter drift (decrement in finally) | T3 | backend/services/ SSE handler |
| S1-03 | Block context dict from overriding tier in agent.py | 02-P1-01 | backend/api/v1/agent.py |
| S1-04 | Fix check_alerts email_sent=True when no emails sent | 02-P1-02 | backend/services/alert_service.py |
| S1-05 | Fix free-tier alert count to exclude soft-deleted | 02-P1-03 | backend/api/v1/alerts.py |
| S1-06 | Validate utility_type against enum in forecast+neighborhood | 02-P1-04/05 | backend/api/v1/forecast.py, neighborhood.py |
| S1-07 | Fix Stripe webhook bare except | 02-P1-07 | backend/services/stripe_service.py |
| S1-08 | Move API keys from URL params to headers | T9 | backend/services/eia_service.py, nrel_service.py, weather_service.py |
| S1-09 | Make withdraw_all_consents() atomic | T8 | backend/compliance/gdpr.py |
| S1-10 | Add LIMIT to backfill_actuals when region=None | 19-P1-07 | backend/services/price_service.py |
| S1-11 | Add SlidingWindowLimiter eviction (LRU/TTL sweep) | 19-P1-08 | backend/lib/rate_limiter.py |
| S1-12 | Fix portal.ts to use apiClient | 14-P1-07 | frontend/lib/api/portal.ts |
| S1-13 | Fix useGeocoding to use apiClient | 14-P1-04 | frontend/lib/hooks/useGeocoding.ts |
| S1-14 | Fix useAuth OAuth to use finally for isLoading | 14-P1-05 | frontend/lib/hooks/useAuth.ts |
| S1-15 | Add useCallback to useRefreshPrices return | 20-P0-02 | frontend/lib/hooks/useRefreshPrices.ts |
| S1-16 | Fix CircuitBreaker.recordSuccess() hard-reset | 20-P1-04 | frontend/lib/api/circuit-breaker.ts |
| S1-17 | Fix 401/403 tripping circuit breaker | 19-P2-06 | backend/services/pricing/base.py |

## Dependencies

- Sprint 2's improved tests will catch regressions from these changes
- S1-01 (Redis atomic) may need Sprint 0's rate limiter fix as prerequisite (DONE)
- S1-08 (API keys) requires verifying header auth support with EIA/NREL/OWM APIs
