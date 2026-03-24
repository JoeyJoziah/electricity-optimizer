# Audit Report: Test Quality

**Date:** 2026-03-23
**Scope:** Test patterns, coverage gaps, flaky tests, mock quality across all layers
**Auditor:** QA Expert (Claude Opus 4.6)

**Files Reviewed:** 52 files (23 backend, 4 top-level security/perf, 9 frontend unit, 12 E2E, 4 ML, 3 worker)

---

## P0 -- Critical (Fix Immediately)

### 16-P0-1: `tests/security/test_auth_bypass.py` Tests a Non-Existent Auth Model

**File:** `tests/security/test_auth_bypass.py` lines 37, 50, 63, 175

The entire top-level security test suite constructs JWTs signed with `"test_secret_key"` and sends them as `Authorization: Bearer <token>` headers to protected endpoints. The actual application uses Better Auth / Neon Auth, which operates on opaque session cookies managed by the auth library -- not HS256 JWTs decoded by the application. These tests:

1. Sign tokens with a hardcoded secret that has no relation to the production auth system.
2. Send `Authorization: Bearer` headers to endpoints that use cookie-based session validation.
3. Expect HTTP 401 rejections as proof that the auth system is working.

In practice, the 401 responses are produced not because the JWT is invalid but because no session cookie is present. The "expired token" test, the "wrong algorithm" test, and the "tampered payload" test all pass for the wrong reason -- the app ignores the Authorization header entirely and returns 401 for the missing cookie.

This means the entire `TestTokenValidation` and most of `TestProtectedEndpoints` do not verify the actual authentication mechanism. A real JWT bypass (e.g., algorithm confusion attack, `alg=none` acceptance) would not be caught by these tests.

**Impact:** Critical security coverage gap. Authentication bypass vulnerabilities in the real auth layer are untested.

**Fix:** Rewrite this file to use Better Auth's session cookie model. Use `TestClient` with a patched `get_current_user` dependency (like `backend/tests/test_security_adversarial.py` does) or test the actual Neon Auth session validation. Remove JWT fixture infrastructure that does not correspond to the real system.

### 16-P0-2: `datetime.utcnow()` in Security Test Fixtures (Deprecated, Timezone-Naive)

**File:** `tests/security/test_auth_bypass.py` lines 32, 33, 46, 47, 59, 60, 140, 172, 173

Nine uses of `datetime.utcnow()` in token-building fixtures. This function is deprecated since Python 3.12 and returns timezone-naive datetimes. The `pyproject.toml` suppresses all `DeprecationWarning` with `"ignore::DeprecationWarning"` (line 104), which hides this warning in the test output.

The combination -- a deprecated function whose warnings are globally suppressed -- means this class of bug will not surface until Python 4.0 removes the function entirely.

**Impact:** Silent tech debt accumulation. The `filterwarnings` global suppression masks other deprecation warnings across all 2,686+ backend tests.

**Fix:** Replace `datetime.utcnow()` with `datetime.now(UTC)` throughout `tests/security/test_auth_bypass.py`. Consider removing the global `DeprecationWarning` suppression in `pyproject.toml` and handling specific known warnings with targeted `filterwarnings` marks.

### 16-P0-3: `test_api.py` Accepts HTTP 500 as a Valid Test Outcome in 14 Tests

**File:** `backend/tests/test_api.py` lines 88, 111, 125, 146, 158, 171, 208, 220, 240, 259, 270, 278, 289; `backend/tests/test_api_predictions.py` line 244

Fourteen assertions in `test_api.py` use the pattern:

```python
assert response.status_code in [200, 500]
assert response.status_code in [200, 404, 500]
```

HTTP 500 is an unhandled server exception. Accepting it as valid means these tests will pass even when the endpoint throws a traceback. Examples:

- `test_get_price_history` -- accepts 500
- `test_price_history_pagination_metadata_present` -- accepts 500
- `test_price_history_default_page_size_is_24` -- line 158: `in [200, 500]`
- `test_get_suppliers_for_region` -- accepts 500

The module-level `TestClient` fixture (`scope="module"`, line 23) re-uses a single ASGI application instance across all tests in the file. State mutations in one test can corrupt the ASGI state for subsequent tests in the same module, compounding the unreliability.

**Impact:** Silent regressions. Server errors in production-equivalent paths will not cause CI failure.

**Fix:** Replace permissive `in [200, 500]` patterns with explicit expected status codes. For tests that genuinely need to skip when a DB is absent, use `pytest.skip()` with a fixture guard. Narrow the `scope="module"` TestClient to `scope="function"`.

---

## P1 -- High (Fix This Sprint)

### 16-P1-1: Real `asyncio.sleep()` Calls in `test_integrations.py` Create Timing-Dependent Tests

**File:** `backend/tests/test_integrations.py` lines 296, 314, 363, 419, 531

Five tests use unpatched `await asyncio.sleep(0.1)` and `await asyncio.sleep(0.15)` to exercise circuit breaker timeout behavior. On a loaded CI runner (shared cores, container throttling), 100ms or 150ms real sleep is insufficient to guarantee the circuit breaker's internal timeout state has advanced.

**Impact:** Intermittent CI failures on slow runners. Test suite duration increases by real sleep time (~2+ seconds per affected test run).

**Fix:** Patch `asyncio.sleep` in circuit breaker timeout tests. Expose a `_clock` parameter on `CircuitBreaker` for test time injection.

### 16-P1-2: `test_load.py` Wall-Clock Time Assertions Are Environment-Dependent

**File:** `backend/tests/test_load.py` (marked `pytestmark = pytest.mark.slow`)

Load tests assert that 50 concurrent requests complete in under 2 seconds and that other concurrent operations complete within absolute millisecond bounds. These assertions pass on the author's hardware but can fail on free-tier CI runners with limited CPU/memory.

**Impact:** Flaky test results when run outside the standard CI pipeline.

**Fix:** Document the hardware baseline. Consider relative performance assertions rather than absolute millisecond bounds.

### 16-P1-3: Module-Scoped TestClient Fixtures Share State Across Tests

**Files:**
- `backend/tests/test_api.py` line 23: `@pytest.fixture(scope="module")`
- `backend/tests/test_security_adversarial.py` line 174: `@pytest.fixture(scope="module")`

Module-scoped fixtures are shared across all tests in the file. If any test patches a dependency, modifies a global singleton, or triggers a side effect on the ASGI app, subsequent tests inherit that mutated state.

**Impact:** Order-dependent test failures, hard-to-debug state bleed between tests.

**Fix:** Downscope to `scope="function"`. The additional ASGI startup/shutdown cycles add approximately 1.4 seconds total.

### 16-P1-4: Session-Scoped `event_loop` Fixture Is Deprecated in pytest-asyncio >= 0.21

**File:** `backend/tests/conftest.py` lines 34-39

The custom `event_loop` fixture is redundant with `asyncio_mode = "auto"` in `pyproject.toml` (line 90). A corrupted loop state in one test propagates to all subsequent async tests in the session. The global `"ignore::DeprecationWarning"` suppresses the deprecation warning.

**Impact:** Session-wide event loop corruption risk. A future pytest-asyncio upgrade will break all 1,188 async tests simultaneously.

**Fix:** Remove the `event_loop` fixture from `conftest.py`.

### 16-P1-5: `flatpeak_forecast_response` Fixture Uses `datetime.now(UTC)` Creating Time-Sensitive Test Data

**File:** `backend/tests/conftest.py` lines 176-196

The `is_peak` field's value depends on the wall-clock hour when the test runs. A test that asserts specific `is_peak` values will pass at 2am and fail at 4pm.

**Impact:** Flaky tests whose results differ between morning and evening CI runs.

**Fix:** Pin `base_time` to a fixed datetime: `datetime(2024, 1, 15, 0, 0, tzinfo=UTC)`.

### 16-P1-6: `tests/security/test_rate_limiting.py` Does Not Inherit Rate Limiter Reset Fixtures

**File:** `tests/security/test_rate_limiting.py`

This file lives in the top-level `tests/security/` directory, not `backend/tests/`, so it does NOT receive the autouse `reset_rate_limiter` fixture from `backend/tests/conftest.py`. Auth headers use literal `"Bearer test_token_user_1"` strings, not real session tokens.

**Impact:** Incorrect test results (testing 401 behavior instead of 429 behavior), potential state contamination.

**Fix:** Add a `conftest.py` to `tests/security/` that resets the rate limiter before each test. Replace literal bearer strings with proper mock authentication.

---

## P2 -- Medium (Fix Soon)

### 16-P2-1: E2E `authentication.spec.ts` Has Permanently Skipped Tests and Weak Assertions

**File:** `frontend/e2e/authentication.spec.ts` lines 103, 108, 140, 156, 302, 427, 466

Two permanently skipped tests (`test.skip`) with no condition or issue reference. Multiple weak OR-condition assertions: `expect(errorVisible || stayedOnLogin).toBeTruthy()`. Trivial body assertion for token expiration: `await expect(page.locator("body")).toBeVisible()`.

**Fix:** Convert `test.skip` to `test.fixme` with linked GitHub issues. Replace OR-condition assertions with specific expected behaviors.

### 16-P2-2: E2E `page-load.spec.ts` Has 26 Trivial `body.toBeVisible()` Assertions

**File:** `frontend/e2e/page-load.spec.ts` (26 occurrences)

The `body` element is always present and always visible. These assertions verify only that the browser did not crash.

**Fix:** Replace with `page.getByRole('heading', ...)` or `page.getByTestId(...)` for each page's expected primary content element.

### 16-P2-3: E2E `missing-pages.spec.ts` Uses OR-Condition Assertions for 404 Behavior

**File:** `frontend/e2e/missing-pages.spec.ts`

Treats a still-loading spinner and a completed dashboard redirect as equivalent success outcomes.

**Fix:** Define the specific expected behavior for each scenario and assert directly.

### 16-P2-4: `conftest.py` `mock_sqlalchemy_select` Fixture Requires Manual Maintenance When Model Fields Change

**File:** `backend/tests/conftest.py` lines 480-513

The `model_attrs` dictionary hardcodes 22 field names across `Price`, `User`, `Supplier`, and `Tariff` models. When a new column is added, tests using that field will raise `AttributeError` with a confusing error message.

**Fix:** Replace hardcoded field lists with dynamic Pydantic v2 introspection using `cls.model_fields`.

### 16-P2-5: Frontend Unit Tests Assert CSS Classes Instead of Behavior

**Files:** `frontend/__tests__/integration/dashboard.test.tsx`, `frontend/__tests__/pages/auth-login.test.tsx` line 30

CSS class assertions are brittle to Tailwind refactors. The login page test uses `div.min-h-screen` as a locator.

**Fix:** Replace CSS class assertions with semantic assertions (ARIA roles, text content, test IDs).

### 16-P2-6: ML `test_models.py` Tests Are Conditionally Skipped When TensorFlow Is Not Installed

**File:** `ml/tests/test_models.py` with `@pytest.mark.requires_tf`

Standard CI runners and the Render backend container do not install TF. The entire model layer is effectively never tested in CI.

**Impact:** CI can pass a green build while the primary ML prediction model has architecture bugs.

**Fix:** Add `MockForecaster`-based tests that exercise the model's Python interface without TF dependency.

### 16-P2-7: `test_performance.py` Has Real `asyncio.sleep` Calls Mixed Into Timing Measurements

**File:** `backend/tests/test_performance.py` lines 394, 407

Real `asyncio.sleep` calls inside performance-measurement tests contaminate timing assertions.

**Fix:** Use `await asyncio.sleep(0)` for event loop yields without inflating wall-clock timings.

---

## P3 -- Low / Housekeeping

### 16-P3-1: Multiple E2E `test.skip()` Calls Without Issue Tracker References

**Files:** `authentication.spec.ts` lines 108, 156; `mobile.spec.ts` lines 305, 336; `accessibility.spec.ts` line 466

6 tests use unconditional `test.skip()` with no reason string and no issue reference.

**Fix:** Convert to `test.fixme('reason', async () => { ... })` with GitHub issue numbers.

### 16-P3-2: `@pytest.mark.asyncio` Decorators Are Redundant With `asyncio_mode = "auto"`

**Files:** 75 backend test files, 1,188 total occurrences

With `asyncio_mode = "auto"`, the decorator is completely redundant.

**Fix:** Low-priority cleanup. Add a ruff rule to flag redundant asyncio markers.

### 16-P3-3: `test_migrations.py` Does Not Validate Migrations 056-060 Content

**File:** `backend/tests/test_migrations.py`

The five most recent migrations have no specific content assertions.

**Fix:** Add specific structural assertions for migrations 056-060.

### 16-P3-4: Worker Tests Have No Coverage for `proxy.ts` Handler

**File:** `workers/api-gateway/src/handlers/proxy.ts` (no corresponding test file)

The main request proxy -- containing 2-tier caching, graceful KV degradation, per-isolate metrics, and CORS logic -- has no unit tests.

**Fix:** Add `test/proxy.test.ts` using `vi.stubGlobal('caches', ...)` to mock the Cache API.

### 16-P3-5: `asyncio.sleep(0)` Calls Without Explanatory Comments

**Files:** `backend/tests/test_bill_upload.py`, `backend/tests/test_rate_scraper_service.py` lines 245, 263, 290, 316, 337, 362

**Fix:** Add a one-line comment: `# yield to allow queued coroutines to advance`.

### 16-P3-6: `frontend/__tests__/components/auth/LoginForm.test.tsx` Uses Mutable Module-Level State

Module-level mutable variables reset in `beforeEach` but can bleed if `beforeEach` is bypassed.

**Fix:** Move state initialization inside `beforeEach` or use `jest.clearAllMocks()`.

---

## Files With No Issues Found

- `backend/tests/test_agent_service.py` -- Thorough coverage including IDOR protection, cross-tier rate limits, Gemini 429 fallback
- `backend/tests/test_savings_service.py` -- Excellent granularity: streak computation, serialization, pagination math
- `backend/tests/test_race_condition_fixes.py` -- Sophisticated: directly manipulates `limiter._windows` internals
- `backend/tests/test_webhook_payment_integrity.py` -- Sprint-organized, tests idempotency race condition
- `backend/tests/test_migrations.py` -- Validates SQL structural safety without requiring a database connection
- `backend/tests/test_encryption.py` -- Complete: encrypt/decrypt roundtrip, key rotation, HMAC verification
- `backend/tests/test_circuit_breaker.py` -- State machine transitions fully covered
- `workers/api-gateway/test/router.test.ts` -- Pure function testing with clear input/output
- `workers/api-gateway/test/security.test.ts` -- Straightforward pure function coverage
- `workers/api-gateway/test/scheduled.test.ts` -- Excellent `vi.useFakeTimers()` usage
- `ml/tests/test_optimization.py` -- MILP solver tests with practical constraints
- `tests/security/test_sql_injection.py` -- Well-documented with clear security contract
- `backend/tests/conftest.py` -- Sophisticated `_ColumnMock` + `_ChainableMock` + `type.__setattr__` restore pattern

---

## Summary

| Severity | Count | Key Theme |
|----------|-------|-----------|
| P0 | 3 | Auth bypass tests test wrong auth model; deprecated timezone-naive datetimes; silent 500 acceptance |
| P1 | 6 | Real sleep in timing tests; wall-clock load assertions; module-scoped shared state; deprecated event_loop; time-dependent fixture; rate limiter isolation |
| P2 | 7 | Weak E2E assertions; body.toBeVisible() pattern; OR-condition toBeTruthy(); manual conftest maintenance; CSS class assertions; TF-gated ML tests never run in CI; asyncio.sleep in perf tests |
| P3 | 6 | Unconditional test.skip; redundant asyncio markers; migration coverage gaps; missing proxy.ts tests; undocumented sleep(0); mutable module-level state |

**Overall Assessment:** The backend conftest infrastructure is genuinely well-engineered. The `_ColumnMock` / `_ChainableMock` approach to SQLAlchemy expression mocking and the autouse tier-cache / rate-limiter reset fixtures represent solid test engineering. The worker tests with `vi.useFakeTimers()` are exemplary.

**Highest priority:** P0-1 -- the top-level security auth bypass tests test a JWT-based authentication model that does not exist in the actual application. All tests pass for the wrong reason.

**Most impactful quick win:** P0-3 -- 14 tests accepting HTTP 500 as valid can be fixed in a single pass.

**Coverage gaps:** CF Worker proxy handler (`proxy.ts`) untested despite being the most complex worker component. ML model architecture tests only run when TF is installed (never in CI).

**Estimated remediation effort:** P0: 2-3 hours. P1: 3-4 hours. P2/P3: housekeeping batches.
