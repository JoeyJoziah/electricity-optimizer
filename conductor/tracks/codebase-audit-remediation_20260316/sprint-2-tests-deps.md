# Sprint 2: Test Integrity & Dependencies — IN PROGRESS

**Status**: IN PROGRESS
**Started**: 2026-03-16
**Agents**: 6 parallel workstreams
**Target**: Fix inflated test coverage, update critical dependencies, add error boundaries

## Workstreams

| WS | Agent Type | Tasks | Status |
|----|-----------|-------|--------|
| WS-2A-tests | test-automator | S2-01, S2-02, S2-05, S2-06 | RUNNING |
| WS-2B-contracts | qa-expert | S2-03, S2-04 | RUNNING |
| WS-2C-integration | test-automator | S2-07 | RUNNING |
| WS-2D-deps | dependency-manager | S2-08, S2-09, S2-10 | RUNNING |
| WS-2E-errorboundary | frontend-developer | S2-11 | RUNNING |
| WS-2F-abortsignal | frontend-developer | S2-12 | RUNNING |

## Task Detail

| # | Task | Source | Status |
|---|------|--------|--------|
| S2-01 | Fill 12 empty test bodies in test_auth.py | 08-P0-01 | IN PROGRESS |
| S2-02 | Replace 90+ `assert is not None` with meaningful assertions | 08-P1-01 | PENDING |
| S2-03 | Fix tautological contract tests | 08-P0-02 | IN PROGRESS |
| S2-04 | Fix mobile responsive test | 08-P0-03 | IN PROGRESS |
| S2-05 | Fix tier gating tests to reject 500 | 08-P1-02 | PENDING |
| S2-06 | Fix community XSS test (real sanitizer) | 08-P1-04 | PENDING |
| S2-07 | Add 5 missing integration test paths | 08-cross | IN PROGRESS |
| S2-08 | Upgrade sentry-sdk to latest 1.x | 10-P0-01 | IN PROGRESS |
| S2-09 | Upgrade pydantic to 2.9+ | 10-P0-02 | PENDING |
| S2-10 | Move dev tools out of requirements.txt | 10-P0-03 | PENDING |
| S2-11 | Add ErrorBoundary components | T6 | IN PROGRESS |
| S2-12 | Thread AbortSignal through apiClient | 14-cross | IN PROGRESS |

## Verification Criteria

- [ ] Test count does NOT decrease
- [ ] All existing passing tests still pass
- [ ] sentry-sdk stays on 1.x (NOT 2.x)
- [ ] pydantic upgrade doesn't break model validation
- [ ] ErrorBoundary wraps all major page subtrees
- [ ] AbortSignal cancels in-flight requests on navigation
