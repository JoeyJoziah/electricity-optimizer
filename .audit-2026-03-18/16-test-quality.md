# Audit Report: Test Quality — All Suites

**Date**: 2026-03-18
**Auditor**: QA Expert Agent
**Scope**: Backend (2,686 tests), Frontend unit/integration (2,039 tests), E2E Playwright (1,605 tests, 25 specs, 5 browsers), ML (611 tests), CF Worker (90 tests), Root-level tests (load/performance/security)

---

## Summary

~7,031 tests span 6 layers with generally high quality. The shared backend conftest.py is the project most valuable test asset — its mock_sqlalchemy_select autouse fixture cleanly solves Pydantic v2 descriptor conflicts. The E2E suite has a strong fixture architecture (fixtures.ts + api-mocks.ts). However, several P0 findings indicate that security and performance test stubs are shipping false confidence, and a conftest gap silently causes tier-gated test failures.

---

## P0 — Critical: False Confidence / Silent Test Failures

### P0-1: mock_sqlalchemy_select missing subscription_tier and stripe_customer_id

**File**: backend/tests/conftest.py, lines 481-491
**Impact**: Any test that exercises tier-gated logic via User.subscription_tier will fail or silently receive a _ColumnMock instead of a real attribute value. With 7+ endpoints gated by require_tier(), this gap affects a wide surface area.

**Current code (lines 481-491)**:

    "models.user": {
        "User": [
            "id", "email", "name", "region", "created_at", "is_active",
            "current_supplier_id", "utility_types", "annual_usage_kwh",
            "onboarding_completed",
        ],
    },

**Missing fields** (confirmed in backend/models/user.py):
- subscription_tier — used by require_tier() dependency on 7+ endpoints
- stripe_customer_id — used by Stripe webhook resolution

**Fix**: Add both fields to the model_attrs["models.user"]["User"] list in conftest.py.

---

### P0-2: Empty stub tests ship as passing in CI

**File**: tests/security/test_auth_bypass.py, lines 243-261

Two test methods have zero meaningful assertions and always pass:

    def test_logout_invalidates_token(self, client, valid_token):
        logout_response = client.post("/api/v1/auth/signout", headers=headers)
        if logout_response.status_code == 200:
            pass  # line 255 — ALWAYS passes regardless of response

    def test_sensitive_headers_not_logged(self, client, valid_token):
        pass  # line 261 — zero assertions

Both provide zero security coverage while appearing as passing tests in CI reports.

**Fix**: Implement test_logout_invalidates_token to verify that a signed-out token is rejected, or mark with @pytest.mark.skip(reason="stateless JWT — requires token blacklist"). Convert test_sensitive_headers_not_logged to a static config audit or remove it.

---

### P0-3: Performance tests require live server with no skip guard

**File**: tests/performance/test_api_latency.py

Hardcodes BASE_URL = "http://localhost:8000" and makes real HTTP requests. The auth fixture silently absorbs ConnectionRefusedError and returns a synthetic token:

    except Exception:
        return "mock_token"  # silent fallback — tests run against nothing

Latency assertions (assert elapsed < 2.0, assert p99 < 0.1) pass trivially when no server exists, or raise statistics.StatisticsError from empty latency lists. No pytestmark = pytest.mark.integration or skip guard is present.

**Fix**: Add module-level skip guard:
    pytestmark = pytest.mark.skipif(not os.getenv("API_BASE_URL"), reason="requires live server")

---

## P1 — High: Significant Test Reliability or Coverage Gaps

### P1-1: 50+ waitForTimeout() calls across E2E specs

**Files**: frontend/e2e/edge-cases.spec.ts (7 occurrences), frontend/e2e/visual-regression.spec.ts (12 occurrences, RENDER_SETTLE_MS = 1000), and 8 other spec files.

waitForTimeout() introduces fixed-duration sleeps that make tests slow and flaky. Representative examples:

    await page.waitForTimeout(2000)  // edge-cases.spec.ts: "wait for auth to process"

    const RENDER_SETTLE_MS = 1000
    await page.waitForTimeout(RENDER_SETTLE_MS)  // visual-regression.spec.ts: 12 times before screenshots

**Fix**: Replace each waitForTimeout with a stable signal — waitForSelector, expect(locator).toBeVisible(), or waitForLoadState("networkidle") for visual regression snapshots.

---

### P1-2: Tautological assertion in accessibility spec

**File**: frontend/e2e/accessibility.spec.ts, line 296

    expect(submitFocused || true).toBe(true)  // always true — can never fail

submitFocused || true evaluates to true regardless of submitFocused. The focus-trap check it claims to verify is completely unimplemented.

**Fix**: Use expect(submitFocused).toBe(true) or add a skip comment for the not-yet-implemented check.

---

### P1-3: Silent .catch() blocks swallowing assertion failures

**File**: frontend/e2e/edge-cases.spec.ts, 5 occurrences

    await expect(page.locator("[data-testid=price-card]")).toBeVisible({ timeout: 5000 })
      .catch(() => {
        // Fallback: at minimum the heading must exist  <- no actual fallback assertion
      })

When the primary assertion throws, the .catch() silently absorbs the error and the test passes. The comment promises a fallback assertion that does not exist.

**Fix**: Remove the .catch() (let the assertion fail) or implement the fallback assertion inside .catch().

---

### P1-4: Module-scoped security client vs. function-scoped autouse fixtures

**File**: backend/tests/test_security_adversarial.py, lines 177-222

The full_app_client fixture is scope="module" but conftest.py autouse fixtures (mock_sqlalchemy_select, reset_tier_cache, reset_rate_limiter) are scope="function". Function-scoped fixtures run between tests but cannot reset state inside a module-scoped client. Tier-cache or rate-limiter state can leak between security test methods.

Line 797 also accepts 503 as a valid security rejection:
    assert response.status_code in (422, 400, 401, 503)

503 indicates service unavailability, not a security rejection — this masks cases where the security check is not running at all.

**Fix**: Change full_app_client to scope="function". Remove 503 from security rejection status codes.

---

### P1-5: Load test uses stale region codes and retired auth endpoint

**File**: tests/load/locustfile.py

    self.region = random.choice(["UK", "EU", "US"])  # invalid Region enum values

Valid regions are from the Region enum (us_ct, us_ny, us_ca, etc.). These three codes produce 422 responses for every region-parameterized request, invalidating all latency measurements.

The login task uses POST /api/v1/auth/signin which was retired when auth migrated to Better Auth (Next.js frontend).

**Fix**: Replace region list with valid Region enum values. Replace the login task with pre-seeded session cookie or Bearer token injection.

---

### P1-6: Root-level tests/conftest.py provides no shared infrastructure

**File**: tests/conftest.py

The root-level test directory (tests/security/, tests/performance/, tests/load/) has a conftest.py with zero fixtures. Security and performance tests require a live server, have no database mocking, and no shared test client. This is structurally disconnected from backend/tests/conftest.py.

**Fix**: Add module-level skip guards and shared infrastructure to tests/conftest.py, or migrate root-level tests into backend/tests/ where the conftest provides proper isolation.

---

### P1-7: Session-scoped event_loop fixture deprecated in pytest-asyncio >= 0.22

**File**: backend/tests/conftest.py, lines 35-45

    @pytest.fixture(scope="session")
    def event_loop():
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

Deprecated in pytest-asyncio >= 0.22, scheduled for removal. Currently silenced by filterwarnings = ignore::DeprecationWarning in pytest.ini — when that filter is removed or the package is updated, this becomes a hard failure.

**Fix**: Remove the session-scoped event_loop fixture. asyncio_mode = "auto" is already set in pytest.ini; pytest-asyncio will manage event loop lifecycle per-test.

---

### P1-8: Visual regression screenshots taken before stable render state

**File**: frontend/e2e/visual-regression.spec.ts, 12 occurrences

    const RENDER_SETTLE_MS = 1000
    await page.waitForTimeout(RENDER_SETTLE_MS)
    await expect(page).toHaveScreenshot(...)

A 1000ms sleep does not guarantee stable render state on slower CI runners. Animated elements, loading skeletons, or chart rendering may still be in progress.

**Fix**: Replace with stable signals:
    await page.waitForSelector("[data-testid=chart-container][data-loaded=true]")
    await page.waitForLoadState("networkidle")
    await expect(page).toHaveScreenshot(...)

---

### P1-9: HNSW 100K cap boundary not tested in ML suite

**File**: ml/tests/ (17 files examined — no boundary test found)

The HNSWVectorStore enforces a 100,000-vector cap from audit remediation. No test verifies: insertion at 99,999 vectors (should succeed), insertion at 100,000 vectors (should reject or evict), or len() reporting at cap.

**Fix**: Add to ml/tests/test_hnsw_vector_store.py:

    def test_cap_boundary_rejects_at_100k(self):
        store = _make_store()
        store._index = MagicMock()
        store._index.get_current_count.return_value = 100_000
        with pytest.raises(CapacityError):
            store.add(np.random.randn(384))

---

### P1-10: CF Worker tests missing empty ORIGIN_URL edge case and gateway-stats coverage

**File**: workers/api-gateway/test/scheduled.test.ts and graceful-degradation.test.ts

scheduled.test.ts does not test what happens when env.ORIGIN_URL is empty or undefined — the worker would send requests to a malformed URL. The cold-start retry delay test verifies the mechanism but not the exact 34,999ms boundary.

graceful-degradation.test.ts tests rate-limiter fail-open but does not verify the 2-tier cache ordering (Cache API checked before KV) or Cache API TTL enforcement.

**Fix**: Add empty ORIGIN_URL describe block in scheduled tests. Add cache ordering verification in graceful-degradation tests.

---

## P2 — Medium: Coverage Gaps and Reliability Issues

### P2-1: ML MockForecaster.predict() is non-deterministic

**File**: ml/tests/conftest.py

sample_price_data and sample_training_data seed np.random.seed(42) for reproducibility. MockForecaster.predict() calls np.random.randn(len(X)) without a seed reset. Tests depending on MockForecaster output may produce different values on each run.

**Fix**: Add np.random.seed(42) inside MockForecaster.predict() or replace np.random.randn with a deterministic constant (e.g., np.ones(len(X)) * 0.15).

---

### P2-2: ML conftest uses country="GB" for US-focused product

**File**: ml/tests/conftest.py

    def feature_engine():
        return ElectricityPriceFeatureEngine(
            country="GB",  # Great Britain — wrong for US product
            climate_zone="temperate",
        )

UK bank holidays differ from US federal holidays; UK DST transitions differ from US. Feature engineering is tested against wrong reference data.

**Fix**: Change to country="US" and climate_zone="continental" (or "northeast" for the dominant CT/NY/CA market).

---

### P2-3: useAuth tests missing profileFetchFailed state and retry behavior

**File**: frontend/__tests__/hooks/useAuth.test.tsx

Auth remediation (commit 9b2c947) introduced profileFetchFailed state and retry-once-after-1s in useAuth.tsx. No tests cover:
- Profile fetch fails once, retries after 1s, succeeds (happy retry path)
- Profile fetch fails twice, profileFetchFailed = true (exhausted retry path)
- profileFetchFailed state visible in hook return value

**Fix**: Add three test cases using Jest fake timers and jest.advanceTimersByTime(1000).

---

### P2-4: E2E matrix tests receive identical mock data regardless of tier/region

**File**: frontend/e2e/helpers/api-mocks.ts

DEFAULT_PRICE always has region: "US_CT" and one hardcoded price. The matrix spec varies tier and region presets but receives identical API response data — cannot verify that different tiers/regions produce different UI states.

**Fix**: Thread region and tier parameters into createMockApi() and vary DEFAULT_PRICE.region and price_per_kwh by input parameters.

---

### P2-5: api-schemas.test.ts missing error response contract tests

**File**: frontend/__tests__/contracts/api-schemas.test.ts

Contract tests validate happy-path response shapes for 8 endpoint groups but not:
- 401 shape (triggers client-side redirect, never-resolving promise)
- 403 ApiClientError structure
- 422 validation error { detail: [{ loc, msg, type }] } shape
- connection_type to method field mapping (root cause of connection API contract breakage fixed in commit 7706c6a)

**Fix**: Add error contract test cases using mockFetch with non-200 status codes.

---

### P2-6: test_security_adversarial.py accepts 503 as security rejection

**File**: backend/tests/test_security_adversarial.py, line 797

    assert response.status_code in (422, 400, 401, 503)

503 (Service Unavailable) is not a security rejection. Accepting it masks cases where security middleware is down or bypassed.

---

### P2-7: Migration tests do not check for sequential gaps

**File**: backend/tests/test_migrations.py

test_unique_migration_numbers() verifies no duplicates but not sequential ordering (001, 002, 004 would pass — gap at 003 undetected). Missing migration files cause deployment ordering failures.

**Fix**: Add gap detection:

    def test_no_sequential_gaps(self):
        files = get_migration_files()
        numbers = sorted(int(re.match(r"^(\d+)", f).group(1))
                         for f in files if re.match(r"^\d+", f))
        for i, n in enumerate(numbers[1:], 1):
            assert n == numbers[i-1] + 1, f"Gap between migration {numbers[i-1]:03d} and {n:03d}"

---

### P2-8: test_notification_dispatcher.py missing concurrent fan-out test

**File**: backend/tests/test_notification_dispatcher.py

The dispatcher runs IN_APP first (creates notification_id), then PUSH+EMAIL concurrently via asyncio.gather(return_exceptions=True). No test verifies:
- IN_APP runs before PUSH/EMAIL
- PUSH failure does not prevent EMAIL delivery
- notification_id from IN_APP is available to subsequent channels

---

### P2-9: CF Worker rate limiter tests do not verify per-isolate counter reset

**File**: workers/api-gateway/test/rate-limiter.test.ts

Native rate limiting bindings use per-isolate counters. Tests mock the binding but do not verify counter state isolation between distinct worker instances — relevant for canary/blue-green deployments where new isolates start with fresh counters.

---

### P2-10: LCP measurement adds 3-second minimum per test

**File**: frontend/e2e/helpers/assertions.ts

    export async function measureLCP(page: Page): Promise<number> {
      return new Promise((resolve) => {
        setTimeout(() => {
          page.evaluate(() => { /* collect LCP */ }).then(resolve)
        }, 3000)  // fixed 3-second delay
      })
    }

3 seconds added per LCP test. Performance spec calls it for 13 scenarios = 39+ seconds of unconditional sleep in CI.

**Fix**: Use page.waitForFunction() to detect when LCP entry exists rather than sleeping.

---

## P3 — Low: Improvement Opportunities

### P3-1: pytest.ini suppresses all DeprecationWarnings globally

**File**: backend/pytest.ini
filterwarnings = ignore::DeprecationWarning silences the deprecated event_loop warning and future deprecation signals from FastAPI, Pydantic, SQLAlchemy. Replace with targeted filters once P1-7 is resolved.

### P3-2: test_race_condition_fixes.py lacks timing assertions for finally-block

**File**: backend/tests/test_race_condition_fixes.py
Concurrent SSE connection counter tests verify correctness but not timing. A slow finally block would pass all assertions. Consider adding a timing budget assertion.

### P3-3: test_load.py wall-clock assertions flake on slow CI runners

**File**: backend/tests/test_load.py
assert elapsed < 2.0 and assert p99 < 0.1 use real wall-clock time via time.monotonic(). Document expected baseline hardware next to these assertions.

### P3-4: useRealtimePrices test does not verify setQueryData merge function correctness

**File**: frontend/__tests__/hooks/useRealtime.test.ts, line 139
Test confirms setQueryData is called with expect.any(Function) but does not invoke the updater to verify it correctly merges new price into existing cached data.

### P3-5: ML ensemble does not test fallback when primary model fails

No test verifies that the ensemble falls back gracefully when a component model throws (e.g., LSTM timeout, HNSW lookup failure).

### P3-6: test_internal_alerts.py does not verify record_triggered_alert payload

**File**: backend/tests/test_internal_alerts.py, line 184
mock_svc.record_triggered_alert.assert_awaited_once() confirms the call but not payload contents. A regression corrupting user_id, alert_type, region, or price values would not be caught. Use assert_awaited_once_with(expected_payload).

### P3-7: E2E missing-pages.spec.ts does not test authenticated state for protected pages

**File**: frontend/e2e/missing-pages.spec.ts
Pages like /alerts, /connections, /assistant are tested unauthenticated. Use the authenticatedPage fixture for these routes to verify authenticated content.

### P3-8: CF Worker cold-start retry boundary not tested at exact threshold

**File**: workers/api-gateway/test/scheduled.test.ts
The 35,000ms cold-start retry logic is tested for mechanism existence but not the exact 34,999ms (should retry) vs 35,001ms (should skip) boundary.

---

## Coverage Summary by Layer

| Layer          | Tests | Key Strength                                        | Biggest Gap                                                    |
|----------------|-------|-----------------------------------------------------|----------------------------------------------------------------|
| Backend        | 2,686 | mock_sqlalchemy_select autouse, async isolation     | Missing subscription_tier/stripe_customer_id; deprecated event_loop |
| Frontend Unit  | 2,039 | Per-test QueryClient, hook isolation                | Missing profileFetchFailed retry tests; incomplete error contracts |
| E2E Playwright | 1,605 | fixtures.ts + ApiCallTracker, 5 browsers            | 50+ waitForTimeout(), tautological a11y assertion, silent .catch() |
| ML             |   611 | Seeded randomness, GPU guard                        | Wrong country code (GB vs US), no HNSW cap boundary test       |
| CF Worker      |    90 | Security/bot detection well covered                 | Missing empty ORIGIN_URL, cache ordering, gateway-stats tests  |
| Root-level     |   ~30 | Locust load framework present                       | Stale regions/endpoints, empty stub tests, no CI skip guards   |

---

## Recommended Fix Priority

| Priority | Finding                                               | Effort   | Impact                                    |
|----------|-------------------------------------------------------|----------|-------------------------------------------|
| P0-1     | Add subscription_tier/stripe_customer_id to conftest  | 5 min    | High — unblocks tier-gated test coverage  |
| P0-2     | Implement or skip empty security stubs                | 30 min   | High — removes false confidence           |
| P0-3     | Add skip guard to performance tests                   | 10 min   | High — prevents silent CI pass            |
| P1-1     | Replace waitForTimeout with deterministic waits       | 2-3 hrs  | High — reduces E2E flakiness              |
| P1-2     | Fix tautological assertion in a11y spec               | 5 min    | Medium — restores focus-trap coverage     |
| P1-3     | Fix silent .catch() blocks                            | 30 min   | Medium — restores assertion integrity     |
| P1-5     | Update locust region codes and auth endpoint          | 30 min   | Medium — makes load tests meaningful      |
| P1-7     | Remove deprecated session event_loop                  | 15 min   | Low now, High after pytest-asyncio update |
| P2-2     | Fix ML country code to US                             | 5 min    | Medium — correct feature engineering      |
| P2-7     | Add migration sequential gap detection                | 20 min   | Medium — deployment safety                |
