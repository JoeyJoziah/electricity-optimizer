# Test Quality Audit — RateShift
**Date**: 2026-03-16  
**Auditor**: QA Expert  
**Scope**: Backend `backend/tests/` and Frontend `frontend/__tests__/`  
**Files sampled**: 22 (11 backend + 11 frontend), representing ~35,000 lines of test code  
**Test baseline**: 2,490 backend tests, 1,841 frontend tests

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| P0       | 3     | Critical — tests pass but assert nothing / mask real bugs |
| P1       | 9     | High — significant gaps that allow real defects through |
| P2       | 18    | Medium — quality weaknesses that reduce confidence |
| P3       | 11    | Low — style / parameterization improvements |
| **Total**| **41**| |

---

## P0 — Critical

### P0-1: Empty Test Bodies in `test_auth.py` — 12 Tests That Never Execute
**File**: `backend/tests/test_auth.py`  
**Lines**: 516–529 (`TestAuthRateLimiting`), 591–608 (`TestSecurityHeaders`), 620–635 (`TestAuthIntegration`)

Twelve async test methods have descriptive docstrings covering important security behaviors but contain **no executable code**. pytest collects and counts them as passing, inflating the "2,490 passing" count while providing zero coverage.

```python
class TestAuthRateLimiting:
    @pytest.mark.asyncio
    async def test_login_rate_limit_after_failures(self):
        """Test account lockout after failed attempts"""
        # 5 failed attempts should trigger 15 min lockout
        # <-- body is entirely a comment; no assertions, no setup>

    async def test_rate_limit_per_ip(self):
        """Test rate limiting per IP address"""

    async def test_rate_limit_reset_after_success(self):
        """Test rate limit resets after successful login"""

class TestSecurityHeaders:
    async def test_csp_header_present(self): ...   # no body
    async def test_xfo_header_deny(self): ...       # no body
    async def test_hsts_header_present(self): ...   # no body
    async def test_xcto_header_nosniff(self): ...   # no body

class TestAuthIntegration:
    async def test_session_validation_flow(self): ...
    async def test_me_endpoint_with_valid_session(self): ...
    async def test_expired_session_rejected(self): ...
```

**Risk**: Account lockout, rate limiting per IP, session expiry enforcement, and four critical security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options) have zero test coverage despite appearing in the test inventory.

**Fix**: Implement the tests or mark them `@pytest.mark.skip(reason="not yet implemented")` to make the gap visible in CI output. The security header tests can reuse the `full_app_client` fixture from `test_security_adversarial.py` in ~20 lines.

---

### P0-2: Contract Test Suite Tests Only Hardcoded Literals — Never Catches Schema Drift
**File**: `frontend/__tests__/contracts/api-schemas.test.ts`  
**Lines**: 20–541 (entire file)

Every test constructs a local hardcoded object and then immediately asserts the object has the properties just set on it. No real API call is made; no TypeScript interface is validated against any Pydantic model output. Tests are structurally tautological.

```typescript
// Lines 40–66 — representative example
it('current prices response has expected fields', () => {
  const response = {              // <-- hardcoded locally, not from API
    prices: [{ id: 'a1b2...', region: 'us_ct', price_per_kwh: '0.2500', ... }],
    region: 'us_ct',
    timestamp: '2026-01-01T00:00:00Z',
  }
  expect(response).toHaveProperty('prices')    // always true — we just set it
  expect(response.prices[0]).toHaveProperty('id') // always true
  // ... pattern repeats for all 8 API groups
})
```

**Risk**: The wave-5 connection feature bug (backend returning `connection_type` while frontend expected `method`) is exactly this kind of contract mismatch. This file gave false confidence the contract was tested. Any schema drift between FastAPI Pydantic models and frontend TypeScript interfaces will NOT be caught.

**Fix**: Replace with Zod schema validation against real fixture snapshots, or use TypeScript interface type assertions:
```typescript
// Approach A: type-level validation catches drift at compile time
import type { ConnectionResponse } from '@/lib/api/client'
const response: ConnectionResponse = buildMockResponse()  // fails if shape wrong

// Approach B: Zod runtime validation
const parsed = ConnectionResponseSchema.safeParse(fixture)
expect(parsed.success).toBe(true)
```

---

### P0-3: Responsive Layout Test Asserts Imaginary CSS State in jsdom
**File**: `frontend/__tests__/integration/dashboard.test.tsx`  
**Lines**: 374–385

```typescript
it('is responsive on mobile devices', async () => {
  Object.defineProperty(window, 'innerWidth', { value: 375 })
  window.dispatchEvent(new Event('resize'))
  render(<DashboardPage />, { wrapper })
  await waitFor(() => {
    const container = screen.getByTestId('dashboard-container')
    expect(container).toHaveClass('flex-col')
  })
})
```

jsdom does not evaluate CSS media queries. `window.innerWidth = 375` has no effect on Tailwind responsive prefixes (`md:flex-row`). The test passes only if `flex-col` is part of the component's static (non-responsive) class list, meaning it is testing desktop layout behavior while believing it is testing mobile. This test provides false confidence about responsive behavior.

**Risk**: Mobile layout regressions pass CI silently.

**Fix**: Remove the `innerWidth` manipulation (it does nothing). Either test the static class list honestly, or move responsive layout assertions to Playwright E2E where real viewport sizing works:
```typescript
// Playwright approach (e2e test)
await page.setViewportSize({ width: 375, height: 812 })
await expect(page.locator('[data-testid="dashboard-container"]')).toHaveClass(/flex-col/)
```

---

## P1 — High

### P1-1: `assert result is not None` After Mocked Call Proves Nothing
**Files**: Multiple backend test files  
**Line count**: 90+ instances across the test suite

After a mock is configured to return a mock object (which is never `None` by default), asserting `result is not None` is always true. It does not verify return shape, correctness, or business rules.

Representative instances (non-exhaustive):
- `backend/tests/test_stripe_service.py:310` — after `verify_webhook_signature` succeeds
- `backend/tests/test_geocoding_service.py:59,85,114,135,160` — 5 consecutive instances
- `backend/tests/test_learning_service.py:155,171,192,215,231,259,274` — 7 instances
- `backend/tests/test_community_service.py:130` — `assert post["id"] is not None`
- `backend/tests/test_cca_service.py:58,77,94,147` — 4 instances
- `backend/tests/test_repositories.py:117,150,205,340,355,376,396,461` — 8 instances

```python
# test_stripe_service.py:310 — example of the pattern
with patch("stripe.Webhook.construct_event", return_value=mock_event):
    event = stripe_service.verify_webhook_signature(payload=b"test_payload", signature="test_signature")
    assert event is not None   # always true; mock_event is never None
```

**Fix**: Replace with specific field verification:
```python
assert event is mock_event
stripe.Webhook.construct_event.assert_called_once_with(
    b"test_payload", "test_signature", "whsec_test_mock"
)
```

---

### P1-2: Always-True Boundary Assertion: `len(prices) >= 0`
**File**: `backend/tests/test_repositories.py`  
**Line**: 75

```python
prices = await repo.get_current_prices(region=PriceRegion.UK)
assert isinstance(prices, list)
assert len(prices) >= 0   # always true for any list, including empty []
```

The test sets up a mock that returns exactly one row, yet asserts `>= 0` rather than `== 1`. A bug that returns an empty list would pass this assertion.

**Fix**:
```python
assert len(prices) == 1
assert prices[0]["region"] == "us_ct"
assert prices[0]["supplier"] == "Eversource Energy"
```

---

### P1-3: Tier Gating "Allowed" Tests Assert `!= 403` Instead of Expected Status
**File**: `backend/tests/test_tier_gating.py`  
**Lines**: 163, 169, 195, 214, 242, 270, 296, 330, 340 (9 occurrences)

```python
def test_pro_user_allowed(self):
    _install("pro")
    client = _client()
    resp = client.get("/api/v1/prices/forecast?region=us_ct")
    assert resp.status_code != 403   # passes for 500, 503, 404 — all broken states
```

This pattern appears 9 times. A 500 Internal Server Error on a pro endpoint makes all these pass. The tests only verify the tier gate was not triggered, not that the feature works.

**Fix**:
```python
assert resp.status_code in (200, 404)   # 404 acceptable if DB is mocked away
# For fully-mocked endpoints:
assert resp.status_code == 200
data = resp.json()
assert "region" in data
```

---

### P1-4: Stripe Webhook Verification Test Does Not Assert Correct Arguments Were Passed
**File**: `backend/tests/test_stripe_service.py`  
**Lines**: 299–311

```python
def test_verify_webhook_signature_success(stripe_service):
    mock_event = Mock(spec=stripe.Event)
    with patch("stripe.Webhook.construct_event", return_value=mock_event):
        event = stripe_service.verify_webhook_signature(
            payload=b"test_payload",
            signature="test_signature",
        )
        assert event is not None   # only verifies mock returned something
```

The test does not verify that `construct_event` was called with the correct webhook secret, the correct payload bytes, or the correct signature string.

**Fix**:
```python
assert event is mock_event
stripe.Webhook.construct_event.assert_called_once_with(
    b"test_payload", "test_signature", "whsec_test_mock"
)
```

---

### P1-5: XSS Test Accepts 200 Without Verifying Sanitization in Response Body
**File**: `backend/tests/test_security_adversarial.py`  
**Lines**: 310–341 (`TestXSSInputHandling`)

```python
def test_xss_in_name_field_accepted_or_rejected_cleanly(self, client):
    for payload in XSS_PAYLOADS:
        response = client.post("/echo-name", json={"name": payload})
        assert response.status_code in (200, 422, 400)
        if response.status_code == 200:
            assert "application/json" in response.headers.get("content-type", "")
            # Missing: assert "<script>" not in response.json()["name"]
```

The `/echo-name` endpoint echoes the payload verbatim. The test verifies JSON content-type but not that XSS was sanitized in the returned data.

**Fix**:
```python
if response.status_code == 200:
    body = response.json()
    assert "<script>" not in body.get("name", "")
    assert "onerror" not in body.get("name", "")
    assert "javascript:" not in body.get("name", "")
```

---

### P1-6: Banned User Session Test Is Identical to Expired Token Test
**File**: `backend/tests/test_auth.py`  
**Lines**: 87–99

```python
async def test_get_session_from_token_banned_user(self, mock_db_session):
    """Test banned user session returns None (query filters banned users)"""
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None   # identical to expired test
    mock_db_session.execute.return_value = mock_result
    result = await _get_session_from_token("banned-user-token", mock_db_session)
    assert result is None
```

The test for banned users and the test for expired tokens (lines 74–86) have identical mock setup and identical assertions. There is no way to distinguish whether a banned-user-specific WHERE clause exists in the SQL, because both return `fetchone() == None`. The test title claims to verify the ban filter but only verifies null result handling.

**Fix**: Verify the SQL emitted contains the banned-user predicate:
```python
call_args = mock_db_session.execute.call_args
sql_text = str(call_args[0][0])
assert "banned" in sql_text.lower() or "ban" in sql_text.lower()
```

---

### P1-7: Integration Tests Use `getAllByText(...).length > 0` Masking Missing Elements
**File**: `frontend/__tests__/integration/dashboard.test.tsx`  
**Lines**: 250–268, 276, 284, 312, 356, 422

```typescript
await waitFor(() => {
  expect(screen.getAllByText(/current price/i).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/0\.25/).length).toBeGreaterThan(0)  // passes for error messages too
  expect(screen.getAllByTestId('price-trend').length).toBeGreaterThan(0)
})
```

`getAllByText` throws if no elements are found, making `.length > 0` redundant. More critically, partial text matches mean the test passes if `price_change_24h` appears anywhere — even in an error message or hidden element. The test does not verify the correct value is shown in the correct element.

**Fix**:
```typescript
expect(screen.getByTestId('current-price')).toHaveTextContent('$0.25')
expect(screen.getByTestId('price-trend')).toBeInTheDocument()
```

---

### P1-8: Community XSS Sanitization Test Mocks Away the Sanitized Value
**File**: `backend/tests/test_community_service.py`  
**Lines**: 134–179 (`test_create_post_sanitizes_xss`)

```python
async def capture_execute(stmt, *args, **kwargs):
    result = MagicMock()
    result.mappings.return_value.fetchone.return_value = {
        "title": "My Great Tip",       # hardcoded clean value in mock
        "body": "Check this out  ...",  # hardcoded clean value in mock
        ...
    }
    return result

post = await service.create_post(mock_db, user_id, data, mock_agent_service)
assert "<script>" not in post["title"]   # always true — mock returns clean value
assert "onerror" not in post["body"]     # always true — mock returns clean value
```

The mock returns pre-sanitized strings. If `nh3.clean()` were removed from `create_post`, the INSERT SQL would contain the XSS payload but this test would still pass because the mock hardcodes the clean result.

**Fix**: Capture the SQL parameters passed to the INSERT and assert sanitization occurred before the DB write:
```python
async def capture_execute(stmt, params=None, **kwargs):
    if params and "title" in params:
        assert "<script>" not in str(params.get("title", ""))
        assert "onerror" not in str(params.get("body", ""))
    result = MagicMock()
    ...
```

---

### P1-9: Missing Negative/Idempotency Tests for Stripe Webhook Events
**File**: `backend/tests/test_stripe_service.py` and `backend/tests/test_webhooks.py`

No tests exist for:
- Duplicate webhook delivery (same `evt_` ID sent twice) — Stripe guarantees at-least-once
- `invoice.payment_failed` when the subscription is already in `canceled` state
- `customer.subscription.updated` downgrading from `business` to `free` tier
- Webhook with `user_id` in metadata that does not match any database record for the `customer_id`

Stripe's at-least-once delivery guarantee makes idempotency critical. If `apply_webhook_action` is not idempotent, duplicate delivery could corrupt subscription state.

**Fix**: Add tests using the same `evt_` ID twice:
```python
async def test_duplicate_webhook_event_is_idempotent():
    result = {"handled": True, "action": "activate_subscription",
              "user_id": "user_123", "tier": "pro", "event_id": "evt_001", ...}
    applied_first = await apply_webhook_action(result, user_repo)
    applied_second = await apply_webhook_action(result, user_repo)
    assert applied_first is True
    assert applied_second is False   # or True with no side effects
    assert user_repo.update.call_count == 1   # only called once
```

---

## P2 — Medium

### P2-1: Auth API Tests Reconstruct FastAPI App Inside Each Test Method
**File**: `backend/tests/test_auth.py`  
**Lines**: 431–504 (`TestAuthAPI`)

Three test methods each independently construct `FastAPI()`, include the router, and create a `TestClient` — identical boilerplate copy-pasted three times.

```python
async def test_password_check_strength_strong(self):
    from api.v1.auth import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/auth")
    with TestClient(app) as client:
        response = client.post(...)
# Identical pattern in test_password_check_strength_weak and test_password_check_strength_empty_rejected
```

**Fix**: Extract to a class-scoped fixture:
```python
@pytest.fixture(scope="class")
def auth_client(self):
    from api.v1.auth import router
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/auth")
    with TestClient(app) as client:
        yield client
```

---

### P2-2: Password Validation Missing Boundary Values at Minimum Length
**File**: `backend/tests/test_auth.py`  
**Lines**: 539–579

`test_password_min_length` tests `"Short1!"` (7 chars) against what is presumably an 8-char minimum. There are no tests for:
- Exactly at the minimum length boundary (should pass)
- Unicode characters and how they count toward length
- Maximum length limit (bcrypt has a 72-byte input limit — truncation is a security concern)

**Fix**:
```python
@pytest.mark.parametrize("pw,valid", [
    ("Ab1!xxxX", True),   # exactly 8 chars — at boundary
    ("Ab1!xxx", False),   # 7 chars — one below boundary
    ("Ab1!" + "x" * 68, True),   # 72 chars — bcrypt limit
])
def test_password_length_boundaries(pw, valid): ...
```

---

### P2-3: Tier Alert Limit Tests Missing "Beyond Limit" and Negative Count Cases
**File**: `backend/tests/test_tier_gating.py`  
**Lines**: 354–401

Tests cover `alert_count=0` (allowed) and `alert_count=1` (blocked). Missing:
- `alert_count=2` — should also be blocked (verifies the condition is `>= 1` not `== 1`)
- `alert_count=-1` — how does the system handle corrupt data?

---

### P2-4: `test_duplicate_day_does_not_inflate_streak` Locks In Implementation Detail
**File**: `backend/tests/test_savings_service.py`  
**Lines**: 856–864

```python
def test_duplicate_day_does_not_inflate_streak(self):
    today = self._today()
    rows = [(today,), (today,), (today - timedelta(days=1),)]
    result = SavingsService._compute_streak(rows)
    # The streak breaks at the second element (another 'today' != yesterday)
    assert result == 1
```

The comment explains implementation behavior (the streak breaks at index 1 because it finds `today` instead of `yesterday`). The business rule should be "duplicate dates count as one day" which would yield streak=2. The test is asserting current buggy behavior as correct rather than testing the intended behavior.

**Fix**: Add a docstring explaining whether duplicates are expected to be deduplicated upstream (before `_compute_streak` is called), and test accordingly.

---

### P2-5: Dashboard Test Documents Known Bug as Correct Behavior
**File**: `frontend/__tests__/components/dashboard/DashboardContent.test.tsx`  
**Lines**: 740–763

```typescript
it('shows price dropping banner when trend is decreasing', () => {
  // The component derives trend as 'stable' regardless of price_change_24h.
  // With the current implementation, this banner never shows.
  ...
  // Component hardcodes trend='stable', so the decreasing banner does not appear.
  expect(screen.queryByText(/prices dropping/i)).not.toBeInTheDocument()
})
```

The test is titled "shows price dropping banner when trend is decreasing" but asserts the banner is NOT shown, citing a known bug. This test will pass forever while the feature remains broken and provides no pressure to fix it.

**Fix**: Either fix the component and update the test to assert the banner IS shown, or rename the test to `'banner_not_shown_due_to_hardcoded_trend_bug'` and create a tracking issue.

---

### P2-6: `full_app_client` Module Fixture Mutation Has No Exception Safety
**File**: `backend/tests/test_security_adversarial.py`  
**Lines**: 177–226

```python
@pytest.fixture(scope="module")
def full_app_client():
    _originals = {}
    for attr, val in [("internal_api_key", _TEST_INTERNAL_API_KEY), ...]:
        _originals[attr] = getattr(_settings, attr)
        object.__setattr__(_settings, attr, val)   # mutates global singleton
    ...
    yield c
    for attr, val in _originals.items():
        object.__setattr__(_settings, attr, val)   # only runs if no exception before yield
```

If an exception occurs between the first `object.__setattr__` call and `yield`, the settings restoration in the teardown never runs. Subsequent test modules inherit test credentials.

**Fix**:
```python
from contextlib import ExitStack
with ExitStack() as stack:
    for attr, val in patches:
        stack.callback(object.__setattr__, _settings, attr, originals[attr])
        object.__setattr__(_settings, attr, val)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
```

---

### P2-7: Community API Mock DB Dispatches SQL by Fragile String Matching
**File**: `backend/tests/test_community_api.py`  
**Lines**: 66–123 (`_MockCommunityDB._dispatch`)

The 57-line dispatch method routes queries to different mock behaviors based on uppercased SQL fragment matching:
```python
if "COMMUNITY_POSTS" in sql and "COUNT(*)" in sql and "CREATED_AT" in sql and "USER_ID" in sql:
    return self._rate_count(params)
```

Any production SQL change (CTE restructuring, whitespace, column renaming) silently falls through to `_empty_result()`. Tests pass with no data rather than failing, which is worse than a test error.

**Risk**: Refactored SQL with correct business logic breaks these tests silently.

**Fix**: Use explicit `AsyncMock(side_effect=[...])` sequences or a real in-memory SQLite DB for these API-level integration tests.

---

### P2-8: `TestComputeStreak` Clock Dependency Creates Midnight Flakiness Risk
**File**: `backend/tests/test_savings_service.py`  
**Lines**: 816–887

All `TestComputeStreak` tests use `datetime.now(tz=timezone.utc).date()` to derive "today". If a CI job starts before midnight and finishes after, rows built in test setup and rows built inside the test body could reference different "today" dates.

**Fix**: Use `freezegun` to freeze time:
```python
from freezegun import freeze_time

@freeze_time("2026-03-15")
def test_five_consecutive_days(self):
    rows = [(date(2026, 3, 15 - i),) for i in range(5)]
    assert SavingsService._compute_streak(rows) == 5
```

---

### P2-9: Frontend Contract Tests Use `toHaveProperty` Not Type Validation
**File**: `frontend/__tests__/contracts/api-schemas.test.ts`

In addition to the P0-2 issue, even if these tests used real data, `toHaveProperty` only verifies key existence:
```typescript
expect(response.prices[0]).toHaveProperty('price_per_kwh')
// passes even if price_per_kwh is null or a number, not the expected string
```

The backend serializes `Decimal` as a string. The frontend interface expects a string. This type mismatch is not caught.

**Fix**:
```typescript
expect(typeof response.prices[0].price_per_kwh).toBe('string')
expect(response.prices[0].price_per_kwh).toMatch(/^\d+\.\d+$/)
```

---

### P2-10: XSS Test Directly Manipulates Internal Rate Limiter State
**File**: `backend/tests/test_security_adversarial.py`  
**Lines**: 343–376

```python
from api.v1.auth import _password_check_limiter
_password_check_limiter.reset()
original_rpm = _password_check_limiter.requests_per_minute
_password_check_limiter.requests_per_minute = 100
```

This directly mutates a production singleton's internal state. If this test runs concurrently with another test exercising the password check endpoint, the artificially raised limit could hide a rate limiting regression.

---

### P2-11: `record_savings` Missing Negative Amount and Invalid Input Tests
**File**: `backend/tests/test_savings_service.py`

`TestRecordSavings` has 8 tests but none cover:
- `amount` as a negative number (reversals — is this intended behavior?)
- `period_end` before `period_start` (invalid date range — should raise ValueError?)
- Extremely large float amounts (Decimal precision / float overflow scenarios)
- `savings_type` as an unrecognized string (should the service validate this?)

---

### P2-12: `activate_subscription` Test Does Not Verify Updated Object Passed to `update()`
**File**: `backend/tests/test_stripe_service.py`  
**Lines**: 562–584

```python
applied = await apply_webhook_action(result, user_repo)
assert user.subscription_tier == "pro"    # verifies in-memory mock object
user_repo.update.assert_awaited_once()    # verifies update was called
```

The test verifies `user.subscription_tier == "pro"` on the mock object and that `update()` was called, but does NOT verify the modified user object was actually passed to `update()`. If `apply_webhook_action` mutated the user then called `user_repo.update(some_other_object)`, this test would still pass.

**Fix**:
```python
update_call_args = user_repo.update.call_args[0][0]
assert update_call_args.subscription_tier == "pro"
assert update_call_args.stripe_customer_id == "cus_test_456"
```

---

### P2-13: `useAuth` Tests Reset `window.location` Only in `afterAll`, Not `afterEach`
**File**: `frontend/__tests__/hooks/useAuth.test.tsx`  
**Lines**: 96–116

```typescript
beforeEach(() => {
  Object.defineProperty(window, 'location', {
    writable: true,
    value: { ...originalLocation, href: '...auth/login', ... },
  })
})
afterAll(() => {
  Object.defineProperty(window, 'location', { writable: true, value: originalLocation })
})
```

Multiple tests also reassign `window.location` inline. If a test fails before its inline reassignment, the next test in the suite inherits a stale location. `afterEach` should reset location to the `beforeEach` default.

---

### P2-14: Password Validation Tests Have Identical Structure and Should Be Parameterized
**File**: `backend/tests/test_auth.py`  
**Lines**: 539–579

Five tests in `TestPasswordValidation` each import the same function, call it with a slightly different invalid password, and check `pytest.raises(ValueError)`. The structure is copy-paste.

**Fix**:
```python
@pytest.mark.parametrize("pw,match", [
    ("Short1!",     "at least 8"),
    ("lowercase1!", "uppercase"),
    ("UPPERCASE1!", "lowercase"),
    ("NoDigits!",   "digit"),
    ("NoSpecial1",  "special character"),
])
def test_password_requirement_violated(pw, match):
    from auth.password import validate_password
    with pytest.raises(ValueError, match=match):
        validate_password(pw)
```

---

### P2-15: Missing Tests for Stripe Tier Downgrade Path
**File**: `backend/tests/test_stripe_service.py`

`apply_webhook_action` tests cover `activate_subscription` (free → pro) and `deactivate_subscription` (any → free), but not:
- `update_subscription` from `business` to `pro` (downgrade)
- `update_subscription` with `status="past_due"` (payment grace period)

---

### P2-16: Integration Test `realtime-indicator` testid May Not Exist With Mock `isConnected: false`
**File**: `frontend/__tests__/integration/dashboard.test.tsx`  
**Lines**: 387–393

```typescript
jest.mock('@/lib/hooks/useRealtime', () => ({
  useRealtimePrices: () => ({ latestPrice: null, isConnected: false, ... }),
}))

it('shows real-time update indicator', async () => {
  await waitFor(() => {
    expect(screen.getByTestId('realtime-indicator')).toBeInTheDocument()
  })
})
```

If `realtime-indicator` is conditionally rendered only when `isConnected: true`, this test will always fail. If it renders regardless of connection state, there is no accompanying test verifying the visual distinction between connected and disconnected states.

---

### P2-17: Test for Banned Session Is a Duplicate of Expired Session Test (see P1-6)
This is an amplification of P1-6: both tests count toward the "2,490 passing" total despite being identical. The passing count overstates actual coverage.

---

### P2-18: Missing Coverage for Session Token Near-Expiry and Race Conditions
**Files**: `backend/tests/test_auth.py`, `frontend/__tests__/hooks/useAuth.test.tsx`

Neither backend nor frontend tests cover:
- Session token approaching expiry (< 60s remaining in cache vs. still valid in neon_auth)
- Frontend: `getSession()` returns valid but backend `/auth/me` returns 401 (race condition)
- Two concurrent requests, one finds a fresh session in cache, the other finds it expired

These gaps are especially important given the session cache TTL was recently changed from 300s to 60s as a P0 security fix.

---

## P3 — Low

### P3-1: `db` and `service` Fixtures Duplicated Across Three Test Classes
**File**: `backend/tests/test_savings_service.py`  
**Lines**: 126–136, 281–292, 490–498

The `db` and `service` fixture definitions are copy-pasted identically inside `TestGetSavingsSummary`, `TestGetSavingsHistory`, and `TestRecordSavings`. Extract to module-level or a shared base class.

---

### P3-2: `test_savings_types_all_accepted` Loop Has Closure Risk If Parallelized
**File**: `backend/tests/test_savings_service.py`  
**Lines**: 688–707

The loop uses `_t=savings_type` default argument capture correctly, but reassigns `db.execute` inside the loop. If test parallelization is ever introduced, the shared `db` mock becomes a race condition.

---

### P3-3: `DashboardContent` Tests Create a New `QueryClient` Per Test Render
**File**: `frontend/__tests__/components/dashboard/DashboardContent.test.tsx`  
**Lines**: 357–364

`createWrapper()` builds a new `QueryClient` on every call, which is called inside every `render()`. 50+ test cases accumulate unreleased timer handles in jsdom. The integration test version correctly creates the client once per describe block.

---

### P3-4: Frontend Tests Use `require()` Inside Test Bodies for Mock References
**File**: `frontend/__tests__/integration/dashboard.test.tsx`  
**Lines**: 289, 340, 445

```typescript
it('handles API errors gracefully', async () => {
  const { getCurrentPrices } = require('@/lib/api/prices')
  getCurrentPrices.mockRejectedValueOnce(...)
})
```

`require()` inside test bodies is fragile. If the module path changes, the error is a runtime TypeError instead of a Jest mock error, making debugging harder.

**Fix**: Capture mock references at module scope:
```typescript
import { getCurrentPrices } from '@/lib/api/prices'
jest.mock('@/lib/api/prices')
const mockGetCurrentPrices = jest.mocked(getCurrentPrices)
```

---

### P3-5: `TestWebhookEventTypes` Parametrize Could Assert Response Body Structure
**File**: `backend/tests/test_webhooks.py`  
**Lines**: 130–146

```python
@pytest.mark.parametrize("event_type", ["push", "pull_request", "issues", "ping"])
def test_various_events_accepted(self, webhook_client, event_type):
    ...
    assert response.status_code == 200
    assert response.json()["event"] == event_type
```

This is already properly parametrized. Future improvement: also assert `response.json()["received"] is True` and `"delivery_id" in response.json()` to verify response structure, not just status.

---

### P3-6: Geocoding Tests 5× `assert result is not None` Without Coordinate Checks
**File**: `backend/tests/test_geocoding_service.py`  
**Lines**: 59, 85, 114, 135, 160

Each test returns a geocoded result but only checks `is not None`. For a geocoding service, the meaningful assertions are latitude/longitude values:
```python
assert result.latitude == pytest.approx(41.76, abs=0.5)
assert result.longitude == pytest.approx(-72.67, abs=0.5)
```

---

### P3-7: GDPR Compliance Tests Assert `export is not None` Without Field Validation
**File**: `backend/tests/test_gdpr_compliance.py`  
**Lines**: 292, 417, 465, 486

GDPR Article 15 specifies exact fields required in a data subject access request export. Tests should verify required fields are present, not just that the export object is non-None.

---

### P3-8: Learning Service Tests Have 7 Bare `assert result is not None`
**File**: `backend/tests/test_learning_service.py`  
**Lines**: 155–274

The ML learning service is central to the adaptive model. Tests should verify prediction values, pattern extraction results, or model weight updates — not just existence of a return value.

---

### P3-9: Duplicate Password Strength Tests Already Covered in P2-14
(See P2-14 for fix.)

---

### P3-10: `test_create_post_triggers_moderation` Could Assert Classification Was Called With Correct Content
**File**: `backend/tests/test_community_service.py`  
**Lines**: 181–220

The test verifies `classify_content` was called but does not verify it was called with the actual post content (sanitized title + body), not some hardcoded string.

---

### P3-11: `TestAuthAPI` Password Strength Tests Missing Rate-Limiting Behavior
**File**: `backend/tests/test_auth.py`  
**Lines**: 449–504

The three password strength tests verify happy path, weak password, and empty rejection, but do not test the rate limit (which is bypassed by `_password_check_limiter.reset()` in the security tests). No test verifies that the 6th request in a minute receives a 429.

---

## Missing Critical Integration Test Coverage

The following high-risk scenarios have no integration tests in either backend or frontend:

1. **End-to-end Stripe payment flow**: No test drives `POST /billing/checkout` → `POST /billing/webhook` → tier-gated endpoint in a single test. Individual components are tested in isolation.

2. **Community rate limiting via HTTP**: `test_community_service.py` tests the service-level limit, but no test makes 11 sequential `POST /community/posts` HTTP calls to verify the 429 is returned.

3. **Alert deduplication cooldown**: No test verifies that a second alert for the same condition within the 1-hour cooldown window is suppressed at the HTTP API level.

4. **Dunning service full sequence**: No test drives `payment_failed` webhook → DunningService email → 7-day grace → escalation in sequence.

5. **Session cache invalidation on logout**: No test verifies that after `POST /auth/logout`, a cached session token no longer grants access.

---

## Test Infrastructure Concerns

### Session-Scoped Event Loop (Deprecated Pattern)
**File**: `backend/tests/conftest.py`, Lines 35–40

```python
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

Session-scoped event loops are deprecated in `pytest-asyncio >= 0.21`. This can cause async state leakage between test modules and order-dependent failures. Recommend function-scoped event loops or `asyncio_mode = "auto"` in `pytest.ini`.

### Global `mock_sqlalchemy_select` Autouse Patches Every Test
**File**: `backend/tests/conftest.py`, Lines 413–529

The `autouse=True` fixture patches SQLAlchemy internals for every test, including tests that never touch the database. This adds overhead and makes it impossible to write integration tests using real SQLAlchemy expressions without explicitly working around the fixture. Consider making it non-autouse (opt-in) for tests that require it.

---

## Positive Findings

The following patterns demonstrate good testing practice:

1. **`test_savings_service.py`**: Thorough boundary value analysis for streak computation (empty, today-missing, consecutive runs, gaps, duplicates, 30-day boundary). Docstrings explain the business rule, not just the implementation.

2. **`test_tier_gating.py`**: Correct `autouse` fixture to clean dependency overrides between tests, preventing cross-test contamination.

3. **`test_security_adversarial.py`**: SQL injection parametrization covers 7 distinct payloads. Rate limit bypass tests unit-test the middleware's `_get_identifier` method directly rather than through the HTTP layer.

4. **`useAuth.test.tsx`**: Correctly tests the open-redirect defense: protocol-relative `//evil.com` is rejected and falls back to `/dashboard`. Session initialization error handling is thorough (network failure, non-Error thrown).

5. **`test_webhooks.py`**: Tests signature verification via actual HMAC computation (`_make_signature`) rather than mocking the verification function itself — testing the right level of abstraction.

6. **`conftest.py`**: The `reset_tier_cache` and `reset_rate_limiter` autouse fixtures cleanly prevent cross-test state leakage.

7. **`DashboardContent.test.tsx`**: Tests for upgrade CTAs on 403 errors vs. non-403 errors show correct differentiation between tier-gating and server errors.

---

*End of audit. Total findings: 3 P0, 9 P1, 18 P2, 11 P3 = 41 issues.*
