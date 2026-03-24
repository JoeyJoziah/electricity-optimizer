# Audit Report: Test Quality

**Date**: 2026-03-19
**Scope**: backend/tests, frontend/__tests__, frontend/e2e, ml/tests, workers/api-gateway/test, tests/security, tests/performance
**Files Reviewed**: 42

## Files Sampled

### Backend (14 files)
1. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/conftest.py`
2. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_api.py`
3. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_agent_service.py`
4. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_alert_service.py`
5. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_race_condition_fixes.py`
6. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_forecast_service.py`
7. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_gdpr_compliance.py`
8. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_notification_dispatcher.py`
9. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_circuit_breaker.py`
10. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_savings_service.py`
11. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_portal_scraper_service.py`
12. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_encryption.py`
13. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_security.py`
14. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_notification_repository.py`

### Frontend (10 files)
15. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/components/alerts/AlertsContent.test.tsx`
16. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/hooks/useAlerts.test.ts`
17. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/components/connections/ConnectionCard.test.tsx`
18. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/store/settings.test.ts`
19. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/components/community/Community.test.tsx`
20. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/hooks/useProfile.test.ts`
21. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/components/prices/PricesContent.test.tsx`
22. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/components/analytics/AnalyticsDashboard.test.tsx`
23. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/contracts/api-schemas.test.ts`
24. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/components/auth/LoginForm.test.tsx`

### E2E (5 files)
25. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/e2e/edge-cases.spec.ts`
26. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/e2e/fixtures.ts`
27. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/e2e/accessibility.spec.ts`
28. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/e2e/helpers/api-mocks.ts` (referenced via fixtures.ts)
29. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/e2e/helpers/auth.ts` (referenced via accessibility.spec.ts)

### ML (5 files)
30. `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_switching_decision.py`
31. `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_metrics.py`
32. `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_optimization.py`
33. `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_scheduler.py`
34. `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_models.py`

### Worker (3 files)
35. `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/test/security.test.ts`
36. `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/test/scheduled.test.ts`
37. `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/conftest.py` (referenced via test_models.py fixtures)

### Security/Performance (5 files)
38. `/Users/devinmcgrath/projects/electricity-optimizer/tests/security/test_sql_injection.py`
39. `/Users/devinmcgrath/projects/electricity-optimizer/tests/performance/test_api_latency.py`
40. `/Users/devinmcgrath/projects/electricity-optimizer/tests/security/test_auth_bypass.py` (referenced)
41. `/Users/devinmcgrath/projects/electricity-optimizer/tests/security/test_rate_limiting.py` (referenced)
42. `/Users/devinmcgrath/projects/electricity-optimizer/tests/performance/test_model_inference.py` (referenced)

---

## P0 - Critical (must fix)

### P0-1: Performance tests silently pass when server is unavailable

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/tests/performance/test_api_latency.py`
**Lines**: 75-88

The `measure_latencies()` function catches all exceptions silently and only appends latencies for successful (200) responses. When the server at `localhost:8000` is not running, the function returns an empty list. The `PerformanceMetrics` class then operates on an empty list, which will raise `statistics.StatisticsError` on `mean()` with an empty dataset -- but this only happens if the test reaches the assertion. If no 200 responses are collected, the test either crashes with an unclear error or (worse) the assertion is never reached.

```python
# Lines 75-88
for _ in range(num_requests):
    start = time.perf_counter()
    try:
        if method == "GET":
            response = client.get(url)
        else:
            response = client.post(url, json=json_data)
        latency = time.perf_counter() - start
        if response.status_code == 200:
            latencies.append(latency)
    except Exception:
        pass  # <-- Silently swallows ALL exceptions
```

**Impact**: Performance SLA tests provide zero assurance when run in CI without a live server. A test suite that silently produces no data gives false confidence.

**Recommendation**: Add a guard at the end of `measure_latencies()` that fails explicitly when too few successful responses are collected (e.g., `assert len(latencies) >= num_requests * 0.5, "Fewer than 50% of requests succeeded"`). Alternatively, mark these tests with `@pytest.mark.integration` and skip them when the server is not reachable.

---

### P0-2: Broad status-code assertions create always-pass tests

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_api.py`
**Lines**: 88, 111, 125-126

Multiple API tests accept almost every possible HTTP status code, making them incapable of detecting regressions:

```python
# Line 88
assert response.status_code in [200, 404, 422, 500]

# Line 111
assert response.status_code in [200, 404, 500]

# Lines 125-126
assert response.status_code in [200, 500]
```

Accepting `500` as a valid response alongside `200` means the test will pass even if the endpoint raises an unhandled exception. This pattern appears in at least 8 test methods in this file.

**Impact**: These tests cannot detect server errors, broken endpoints, or regressions. They provide a false green signal.

**Recommendation**: Remove `500` from accepted status codes. If the endpoint legitimately returns different codes under different conditions (e.g., no data vs. data), split into separate test cases that assert the exact expected code for each scenario (e.g., `assert response.status_code == 200` when data exists, `assert response.status_code == 404` when region has no prices).

---

### P0-3: SQL injection tests accept 500 as safe handling

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/tests/security/test_sql_injection.py`
**Lines**: 60-62, 86, 94, 105, 136, 157, 172, 201

Every SQL injection test accepts `500` as a valid "safely handled" response:

```python
# Line 60-62
assert response.status_code in [200, 400, 422, 500], (
    f"Unexpected response for payload: {payload}"
)
```

A 500 response to a SQL injection payload could indicate that the injection reached the database layer and caused an unhandled error, which is precisely the scenario these tests should detect. The test at line 267-285 (`test_error_messages_dont_leak_schema`) partially compensates by checking the response body, but only for 400+ responses and only for a limited set of indicators.

**Impact**: An actual SQL injection vulnerability that causes a server error would be marked as "safely handled." The security test suite would not catch it.

**Recommendation**: Remove `500` from the accepted status codes. SQL injection payloads should result in `400` (bad input) or `422` (validation error), never `500`. If any currently return `500`, that is a finding to investigate, not to accept.

---

## P1 - Major (should fix soon)

### P1-1: Deprecated session-scoped event_loop fixture

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/conftest.py`
**Lines**: 34-39

```python
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

This pattern is deprecated in `pytest-asyncio >= 0.21` (current versions use `loop_scope` configuration instead). It will produce a deprecation warning and may break in future pytest-asyncio releases.

**Impact**: Will cause test failures on next pytest-asyncio major version upgrade. Produces noisy deprecation warnings that obscure real issues.

**Recommendation**: Remove this fixture entirely and configure `asyncio_mode = "auto"` with `loop_scope = "session"` in `pyproject.toml` under `[tool.pytest.ini_options]`.

---

### P1-2: ML MAPE target test is disabled with a comment

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_models.py`
**Lines**: 697-703

The critical MAPE < 10% accuracy test is commented out:

```python
# For real data with proper training, uncomment:
# assert metrics['mape'] < 10.0, f"MAPE {metrics['mape']:.2f}% exceeds 10% target"
```

The test only asserts `metrics["mape"] >= 0` (line 698), which is trivially true for any non-negative number. The test description says "CRITICAL" and the class docstring states "Critical tests for MAPE < 10% requirement" but the actual assertion does nothing.

**Impact**: The stated ML accuracy target (MAPE < 10%) is never validated. A model that produces 90% MAPE would pass this test.

**Recommendation**: Either enable the real assertion with appropriate test data, or mark the test with `@pytest.mark.skip(reason="Requires real training data")` and create a tracking issue. A silently passing placeholder test is worse than an explicitly skipped one.

---

### P1-3: E2E tests swallow errors with empty catch blocks

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/e2e/edge-cases.spec.ts`
**Lines**: 97-99 (and similar patterns throughout)

```typescript
await expect(modal.first())
    .toBeHidden({ timeout: 5000 })
    .catch(() => {
      /* dialog may already be gone */
    });
```

This pattern appears in the accessibility spec at line 484 as well:

```typescript
.catch(() => {
    /* dialog may already be gone */
});
```

Swallowing Playwright assertion failures means the test will pass even when the modal is unexpectedly visible or the assertion itself throws for an unrelated reason.

**Impact**: Real UI regressions (e.g., modal stays visible after Escape) would be silently ignored.

**Recommendation**: Replace `.catch(() => {})` with explicit state checks. For example:
```typescript
const isHidden = await modal.first().isHidden();
if (!isHidden) {
  // Modal still visible -- skip remaining assertions or fail
}
```

---

### P1-4: Module-level environment mutation without guaranteed cleanup

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_race_condition_fixes.py`
**Lines**: 1-10 (at module top level, before imports)

```python
os.environ.setdefault("ENVIRONMENT", "test")
sys.path.insert(0, ...)
```

Multiple test files perform `os.environ.setdefault()` and `sys.path.insert()` at module level without cleanup. While `conftest.py` also does this (line 11), the duplication means these mutations accumulate across test collection. The `sys.path.insert(0, ...)` calls in individual test files can cause import resolution order issues when tests are collected in different orders.

**Impact**: Test execution order sensitivity. Running test files individually may behave differently from running the full suite. sys.path pollution can cause wrong module imports.

**Recommendation**: Centralize all path manipulation in `conftest.py` only. Remove duplicate `os.environ.setdefault` and `sys.path.insert` calls from individual test files. Use `monkeypatch` for environment variables that need test-specific values.

---

### P1-5: Over-mocking in frontend component tests obscures integration bugs

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/components/prices/PricesContent.test.tsx`
**Lines**: 8-107

This 107-line test file header mocks 6 modules (next/dynamic, PriceLineChart, ForecastChart, Header, settings store, and the prices API) before testing a single component. The mock implementations are substantial -- the PriceLineChart mock alone (lines 31-57) is a 26-line React component.

Similar patterns appear in:
- `AnalyticsDashboard.test.tsx` (lines 6-20): 3 child component mocks
- `Community.test.tsx`: module-level mock variables for loading/error state

**Impact**: When the real PriceLineChart API changes (e.g., prop names change), these tests will continue to pass because they test against the mock, not the real component. Integration-level bugs between parent and child components are invisible.

**Recommendation**: Consider adding a small number of integration tests that render the real child components with mock data (not mock components). For unit tests, keep the mock stubs but use TypeScript interfaces to ensure mock props match real component signatures.

---

### P1-6: Missing negative test coverage for API contract tests

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/contracts/api-schemas.test.ts`
**Lines**: 1-712

The contract test file is well-designed for happy-path validation -- it mocks realistic backend payloads and asserts the client parses them correctly. However, it has no tests for:
- Malformed responses (missing required fields)
- Empty responses
- Type mismatches (e.g., `price_per_kwh` as number instead of string)
- Null values in non-nullable fields
- HTTP error responses (4xx, 5xx)

**Impact**: The API client's error handling and resilience to backend contract changes is untested. When the backend removes or renames a field, these tests will not catch the failure.

**Recommendation**: Add a "Contract Violations" describe block with tests that verify the client handles missing fields, wrong types, and error responses gracefully (either by throwing typed errors or returning sensible defaults).

---

### P1-7: Accessibility tests have conditional skip that hides missing UI elements

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/e2e/accessibility.spec.ts`
**Lines**: 462-468

```typescript
const createButtonExists = await createButton.count();
if (createButtonExists === 0) {
    // If no modal trigger exists on this page, skip gracefully
    test.skip();
    return;
}
```

This pattern silently skips the focus management test if the "Create Alert" button is not found. If the UI changes to remove or rename this button, the test disappears from the suite without any visible signal.

**Impact**: Accessibility regressions in modal focus management could go undetected if the triggering button is removed or renamed.

**Recommendation**: Add a separate test that asserts the button exists, or use `test.fixme()` instead of `test.skip()` so skipped tests are reported as known issues.

---

## P2 - Minor (nice to have)

### P2-1: Keyboard navigation test has fragile tab-counting

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/e2e/accessibility.spec.ts`
**Lines**: 350-380

The login form keyboard navigation test tabs a fixed number of times (up to 5) to reach the submit button:

```typescript
for (let i = 0; i < 5; i++) {
    await page.keyboard.press("Tab");
    submitReached = await page.evaluate(() =>
        document.activeElement?.tagName === "BUTTON" &&
        (document.activeElement as HTMLButtonElement).type === "submit",
    );
    if (submitReached) break;
}
expect(submitReached).toBe(true);
```

Adding a new interactive element (e.g., a "Remember me" checkbox) between the password field and the submit button could push the tab count beyond 5 and cause a false failure.

**Impact**: Low-severity flakiness risk when the form structure changes.

**Recommendation**: Increase the loop limit to 10 or use a locator-based approach (`page.locator('button[type="submit"]').focus()` followed by verifying `document.activeElement`).

---

### P2-2: Test data not extracted into shared fixtures (ML tests)

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_optimization.py`
**Lines**: 44-146

The test file defines 8 fixtures that create various appliances and price profiles. Many of these (dishwasher, EV charger, flat/TOU price profiles) are duplicated across `test_switching_decision.py` and `test_scheduler.py`. Each file independently creates similar test objects.

**Impact**: Maintenance burden. When the `Appliance` or `PriceProfile` constructor signature changes, all three files need updating independently.

**Recommendation**: Extract shared ML test fixtures into `ml/tests/conftest.py` for reuse across test files.

---

### P2-3: Print statements in production test assertions

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_optimization.py`
**Lines**: 615-618, 663, 731-732

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/tests/performance/test_api_latency.py`
**Lines**: 124-128, 159-162

Multiple test methods use `print()` for output:

```python
print(f"\nTOU Scenario Savings: {result.savings_percent:.1f}%")
print(f"Baseline: ${result.baseline_cost:.2f}")
```

This only produces output with `-s` flag and adds noise to verbose test runs.

**Impact**: Minor noise. No functional impact.

**Recommendation**: Use `pytest.approx` assertions for numerical targets and rely on the assertion message for diagnostic info. Alternatively, use Python's `logging` module which integrates with pytest's `--log-cli-level` flag.

---

### P2-4: Unnecessary `if __name__ == "__main__"` blocks

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/tests/security/test_sql_injection.py` (lines 300-301)
- `/Users/devinmcgrath/projects/electricity-optimizer/tests/performance/test_api_latency.py` (lines 363-364)
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_optimization.py` (lines 1134-1136)
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_scheduler.py` (lines 741-742)

These blocks call `pytest.main([__file__, ...])` and are never used in CI (tests are always run via `pytest` directly). They add 2-3 lines of dead code per file.

**Impact**: Negligible. Cosmetic noise.

**Recommendation**: Remove during next cleanup pass.

---

### P2-5: Frontend test mock variable state not type-safe

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/components/auth/LoginForm.test.tsx`
**Lines**: 13-14

```typescript
let mockIsLoading = false
let mockError: string | null = null
```

Module-level mutable variables control mock behavior. The `jest.mock()` closure captures these by reference, which works but bypasses TypeScript's type checking of the mock shape vs. the real hook interface.

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/components/community/Community.test.tsx`

Same pattern with `let mockLoading = false`, `let mockError: string | null = null`.

**Impact**: If the real `useAuth` hook changes its return type (e.g., `error` becomes an Error object instead of a string), these tests will not catch the mismatch.

**Recommendation**: Define mock return values using the real hook's return type:
```typescript
const defaultMockReturn: ReturnType<typeof useAuth> = { ... }
```

---

### P2-6: QueryClient cleanup is inconsistent across frontend tests

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/hooks/useProfile.test.ts`
**Lines**: 30-41 -- creates wrapper per test via `createWrapper()` function (correct pattern)

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/components/prices/PricesContent.test.tsx`
**Lines**: 219-241 -- creates QueryClient in `beforeEach` and calls `queryClient.clear()` in `afterEach` (correct pattern)

However, `useAlerts.test.ts` and other hook test files use different wrapper creation patterns. Some use factory functions, others use `beforeEach`. The inconsistency is not a bug (each is correct in isolation) but makes the test codebase harder to navigate.

**Impact**: Developer friction when writing new tests. No functional impact.

**Recommendation**: Standardize on the `createWrapper()` factory pattern used in `useProfile.test.ts` and document it in a testing conventions file.

---

### P2-7: Onboarding keyboard test assertion is too permissive

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/e2e/accessibility.spec.ts`
**Lines**: 416-422

```typescript
const focused = await authenticatedPage.evaluate(
    () => document.activeElement?.tagName,
);
expect(["INPUT", "SELECT", "BUTTON", "A", "TEXTAREA", "BODY"]).toContain(focused);
```

Including `"BODY"` in the expected set means the assertion passes even when focus is not on any interactive element, which defeats the purpose of testing keyboard navigation.

**Impact**: The test cannot detect focus trap or focus loss bugs.

**Recommendation**: Remove `"BODY"` from the expected set. If focus legitimately remains on body (e.g., the page has no interactive elements), that is a separate issue to address.

---

## P3 - Informational

### P3-1: Contract tests validate structure but not transformation logic

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/contracts/api-schemas.test.ts`

The contract tests verify that `response.prices[0]` has properties like `ticker`, `region`, `current_price`. This confirms the API client passes through JSON fields correctly. However, the test mocks `global.fetch` with hand-crafted payloads, so it cannot detect if the real backend changes its field names.

To truly validate backend-frontend contract compatibility, consider running the AST-based `scripts/api-contract-check.py` (mentioned in CLAUDE.md) as a CI step, not just as a manual check.

---

### P3-2: ML model tests gated behind `@pytest.mark.requires_tf`

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_models.py`

All CNN-LSTM tests are gated behind `@pytest.mark.requires_tf`. If TensorFlow is not installed in the CI environment, the entire ML model test suite (26+ tests) is silently skipped. This is a correct pattern for optional dependencies, but the CI configuration should explicitly log how many tests were skipped and for what reason.

---

### P3-3: Good patterns worth preserving

The following test quality patterns are noteworthy and should be maintained:

**IDOR protection tests**: `test_agent_service.py` (lines testing user_id ownership checks) and `test_notification_repository.py` (IDOR protection via user_id filtering). These explicitly verify that one user cannot access another user's data.

**Circuit breaker state machine tests**: `test_circuit_breaker.py` provides thorough coverage of CLOSED -> OPEN -> HALF_OPEN -> CLOSED transitions with threshold counts, reset behavior, and probe limiting. This is exemplary state machine testing.

**Encryption round-trip tests**: `test_encryption.py` covers AES-256-GCM encryption, tamper detection, different-key rejection, and masking. Good defense-in-depth testing.

**Atomic operation tests**: `test_race_condition_fixes.py` tests Redis Lua script atomicity, SSE connection counter finally-block guarantees, and sliding window eviction. These directly test concurrency safety.

**API contract tests**: `api-schemas.test.ts` documents expected backend response shapes with inline Pydantic model references. This serves as both a test and API documentation.

**Scheduler builder pattern tests**: `test_scheduler.py` tests fluent API chaining (`add_appliance().set_price().optimize()`) and verifies `returns self` for each method. Good API ergonomics testing.

---

## Files With No Issues Found

The following files were reviewed and found to have good test quality, appropriate assertions, proper setup/teardown, and adequate edge case coverage:

1. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_agent_service.py` -- Thorough rate-limit, fallback, IDOR, and prompt injection tests.
2. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_alert_service.py` -- Good dedup, threshold, and dispatcher integration coverage.
3. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_notification_dispatcher.py` -- Proper channel isolation, dedup, and fail-open testing.
4. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_circuit_breaker.py` -- Comprehensive state machine transition testing.
5. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_savings_service.py` -- Good pagination, streak computation, and serialization coverage.
6. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_portal_scraper_service.py` -- Clean httpx mock injection and context manager testing.
7. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_encryption.py` -- Thorough cryptographic round-trip and tamper detection.
8. `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_notification_repository.py` -- Migration checks, IDOR protection, delivery tracking.
9. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/hooks/useProfile.test.ts` -- Proper store sync, error handling, and query key validation.
10. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/store/settings.test.ts` -- Good SSR guard testing via jest.isolateModules.
11. `/Users/devinmcgrath/projects/electricity-optimizer/frontend/__tests__/components/auth/LoginForm.test.tsx` -- Magic link, OAuth visibility, error clearing covered.
12. `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_optimization.py` -- Comprehensive MILP solver testing with constraint satisfaction, savings validation, edge cases, and performance bounds.
13. `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_scheduler.py` -- Thorough builder API testing with chaining, presets, import/export, and error handling.
14. `/Users/devinmcgrath/projects/electricity-optimizer/ml/tests/test_switching_decision.py` -- TDD-style tariff and cost calculation tests.
15. `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/test/scheduled.test.ts` -- Good cron routing and cold-start retry testing with fake timers.

---

## Summary

**Overall Assessment**: The test suite is large (approximately 7,031 tests across 5 layers) and broadly covers the application's functionality. The ML optimization, backend service, and frontend hook tests demonstrate strong patterns including TDD discipline, edge case coverage, and IDOR protection. The E2E infrastructure with custom Playwright fixtures, accessibility scanning via axe-core, and API contract validation is well-architected.

**Critical Gaps**:

| ID | Category | Impact |
|----|----------|--------|
| P0-1 | Performance tests silently pass | False confidence in SLA compliance |
| P0-2 | Broad status-code acceptance | Cannot detect API regressions |
| P0-3 | Security tests accept 500 | Cannot detect SQL injection vulnerabilities |

**Priority Recommendations**:

1. **Immediate**: Fix P0-1 through P0-3. These three findings mean that an entire class of regressions (performance degradation, API errors, security vulnerabilities) could go undetected. The fixes are mechanical: remove `500` from accepted status codes, add empty-result guards to performance tests.

2. **Short-term**: Address P1-1 (deprecated fixture), P1-2 (disabled MAPE assertion), and P1-3 (swallowed E2E errors). These are ticking time-bombs that will cause failures or mask bugs eventually.

3. **Medium-term**: Address P1-5 (over-mocking), P1-6 (missing contract violation tests), and P1-7 (hidden test skips). These represent gaps in integration-level confidence.

4. **Ongoing**: Standardize test patterns (P2-6), remove dead code (P2-4), and strengthen accessibility assertions (P2-7).

**Strengths to Preserve**:
- IDOR protection testing pattern (agent service, notifications)
- Atomic operation testing (race conditions, Redis Lua)
- Circuit breaker state machine testing
- API contract documentation via test comments
- E2E fixture infrastructure with authenticatedPage, apiMocks, and ApiCallTracker
- ML savings validation tests with quantitative targets (15%+ savings)
- Comprehensive WCAG 2.1 AA axe-core scanning across all pages
