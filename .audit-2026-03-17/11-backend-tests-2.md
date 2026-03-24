# Audit Report: Backend Tests (N-Z)
## Date: 2026-03-17

---

### Executive Summary

**Scope**: 50 backend test files matching `backend/tests/test_[n-z]*.py` plus 6 files in `tests/security/`, `tests/performance/`, and `tests/load/`. Full read of 20 representative files; pattern scan of the remaining 36.

**Overall assessment**: The in-scope test suite is generally of high quality. The newer files — `test_race_condition_fixes.py`, `test_notification_dispatcher.py`, `test_tier_gating.py`, `test_security_adversarial.py`, `test_resilience.py`, `test_performance.py` (backend), `test_webhooks.py`, `test_neon_auth.py` — represent production-grade testing: precise mock contracts, focused assertions on real security invariants, explicit boundary conditions, and self-contained fixtures. Several older files in `tests/security/` and `tests/performance/` (the project-root suite) are significantly weaker and contain hollow or structurally broken tests. Three P0 issues and multiple P1/P2 concerns are catalogued below.

**Test count in scope**: ~800–900 individual test cases across 56 files.

---

### Findings

---

#### P0 — Critical

---

**P0-1: `tests/security/test_auth_bypass.py` — Empty test body passes silently; session and logout tests are no-ops**

File: `/Users/devinmcgrath/projects/electricity-optimizer/tests/security/test_auth_bypass.py`

Two tests in `TestSessionSecurity` contain only `pass` or trivially accept every outcome:

```python
def test_logout_invalidates_token(self, client, valid_token):
    headers = {"Authorization": f"Bearer {valid_token}"}
    logout_response = client.post("/api/v1/auth/signout", headers=headers)
    if logout_response.status_code == 200:
        # "This is a weak test since stateless JWTs can't be truly revoked..."
        pass  # NO ASSERTION

def test_sensitive_headers_not_logged(self, client, valid_token):
    # "This is a code review item more than a test"
    pass  # NO ASSERTION
```

These are counted in the test total but verify nothing at all. Any CI run that includes these files will show green for security coverage that does not exist. The `test_login_rate_limiting` and `test_account_lockout_after_failed_attempts` tests also accept `response.status_code in [401, 429]` or `in [401, 403, 423, 429]` for a real brute-force test — too wide to be meaningful, and the `valid_token` fixture uses a hardcoded `"test_secret_key"` that will never match the application's actual signing secret. These tokens will be rejected at the real auth layer, so every "protected endpoint with valid token" test is actually testing the _unauthenticated_ code path while the test name implies authenticated access.

**Remediation**:
- Delete `test_sensitive_headers_not_logged` or replace with an actual log-scraping assertion.
- For `test_logout_invalidates_token`: implement token-blacklist verification or document explicitly as skipped with `pytest.mark.skip(reason="Stateless JWT — track with issue #...")`.
- Replace the hardcoded `"test_secret_key"` in token factories with the actual app signing secret (via env var), or wire tests through the real `TestClient` authenticated dependency-override pattern used in `test_tier_gating.py`.

---

**P0-2: `tests/security/test_sql_injection.py` — Assertions accept HTTP 500, masking real injection leaks**

File: `/Users/devinmcgrath/projects/electricity-optimizer/tests/security/test_sql_injection.py`

Multiple assertions across the file explicitly permit `500` as a passing status:

```python
assert response.status_code in [200, 400, 422, 500], \
    f"Unexpected response for payload: {payload}"

assert response.status_code in [200, 400, 401, 422, 500]
```

An HTTP 500 on a SQL injection payload could mean the payload reached the database layer and triggered an unhandled exception — the very failure mode this test suite is meant to detect. By accepting 500, these tests will pass even if the application is vulnerable. The `test_region_parameter_sql_injection` test does attempt to check `response_text` for SQL error indicators, but the status-code assertion nullifies the value of that check because a 500 with sanitized text is still accepted.

Additionally, the `auth_headers` fixture uses `{"Authorization": "Bearer mock_test_token"}` — a token that will always be rejected by the real auth middleware, so all "auth required" injection points are tested in the _unauthenticated_ state. The `TestSecondOrderInjection.test_stored_value_injection` test does nothing if the first POST returns non-200, so the second-order path is essentially never exercised.

**Remediation**:
- Change assertions to `assert response.status_code in (400, 422)` for typed parameters (enum, int). A 500 must fail the test, not pass it.
- Use the authenticated dependency override pattern (as in `test_tier_gating.py`) rather than a fake Bearer token.
- For second-order injection: require `response.status_code == 200` before proceeding to the GET, and add an explicit check that the stored payload is returned verbatim (not executed).

---

**P0-3: `tests/security/test_rate_limiting.py` — Core rate-limit enforcement test is structurally broken; several tests assert nothing**

File: `/Users/devinmcgrath/projects/electricity-optimizer/tests/security/test_rate_limiting.py`

`test_rate_limit_resets_after_window` calls `time.sleep(1)` and then asserts `response.status_code in [200, 429]`. This passes unconditionally regardless of behavior:

```python
def test_rate_limit_resets_after_window(self, client):
    for _ in range(150):
        client.get("/api/v1/prices/current?region=UK")
    time.sleep(1)  # 1s is not a rate-limit window reset
    response = client.get("/api/v1/prices/current?region=UK")
    assert response.status_code in [200, 429]  # always true
```

`TestRateLimitHeaders.test_rate_limit_headers_present` has its assertion commented out:
```python
# assert len(present_headers) > 0, "Rate limit headers should be present"
```
This test passes and records zero assertions.

`TestRateLimitBypass.test_rate_limit_cannot_be_bypassed_by_headers` loops 150 requests per header variant (total: 750 live requests to the running server), has no assertion if 429 is never returned (`if 429 in responses: continue`), and accepts header bypass as "also acceptable." It will always pass.

`TestRateLimitBypass.test_rate_limit_applies_to_all_methods` has no assertion at all after its request loop.

**Remediation**:
- `test_rate_limit_resets_after_window`: Use a dependency-overridden rate limiter with a test-appropriate window (e.g., 1-second), or mock `time.monotonic` to advance the clock. Require `status_code == 200` after the window resets.
- Uncomment the `test_rate_limit_headers_present` assertion.
- Rewrite bypass tests to assert that 429 is _always_ reached and that the identifier observed during the 429 response is not the spoofed IP.

---

#### P1 — High

---

**P1-1: `tests/performance/test_api_latency.py` — Requires a live server on `localhost:8000`; will fail in CI with zero informative output**

File: `/Users/devinmcgrath/projects/electricity-optimizer/tests/performance/test_api_latency.py`

```python
BASE_URL = "http://localhost:8000"
# ...
@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        yield client
```

There is no `@pytest.mark.skipif` guard and no mock fallback. If no server is running, every test in this file raises a `httpx.ConnectError` which pytest catches as an error, not a skip. This likely means these tests are excluded from the standard pytest run (no `conftest.py` marker integration observed), but if included they fail hard without a useful message.

The `auth_headers` fixture silently falls back to `"Bearer mock_token"` on any error, meaning the "authenticated" performance tests are also exercising the unauthenticated path — measuring latency for 401 responses, not business-logic responses.

**Remediation**:
- Add `@pytest.mark.integration` and a `conftest.py`-level skip: `pytest.mark.skipif(not os.getenv("PERF_TEST_HOST"), reason="No live server configured")`.
- Replace `BASE_URL = "http://localhost:8000"` with `os.getenv("PERF_TEST_HOST", "")`.
- Either require a proper auth token from the environment or document that these tests require a seeded test database.

---

**P1-2: `tests/security/test_auth_bypass.py` — `TestRoleBasedAccessControl` tests accept 401/403/404 indiscriminately, masking missing RBAC enforcement**

File: `/Users/devinmcgrath/projects/electricity-optimizer/tests/security/test_auth_bypass.py`, lines 197–223.

```python
assert response.status_code in [401, 403, 404], \
    f"{endpoint} should restrict admin access"
```

A 404 ("not found") is indistinguishable from a properly enforced 403. If the `/api/v1/admin/*` routes simply do not exist, all tests pass. Because the project is now past MVP with 53 tables and a full permission model, admin-endpoint access control should be tested with precision: a valid non-admin token should receive exactly 403, not any of {401, 403, 404}.

**Remediation**: Assert `response.status_code == 403` after injecting a valid non-admin session (use the dependency override pattern). If admin routes truly do not exist, add a comment documenting why and mark with `pytest.mark.skip`.

---

**P1-3: `tests/security/test_sql_injection.py` — NoSQL injection tests are architecturally misaligned with the actual stack**

File: `/Users/devinmcgrath/projects/electricity-optimizer/tests/security/test_sql_injection.py`, lines 174–200.

The project uses PostgreSQL/Neon exclusively. `TestNoSQLInjection` tests MongoDB-style operators (`$gt`, `$where`, `$regex`) sent as URL query parameters. These payloads will always receive 422 (Pydantic enum validation) from the region parameter, making the tests trivially pass while giving false confidence about a non-existent attack surface.

**Remediation**: Remove `TestNoSQLInjection` entirely or rename to `TestJSONInjection` and test JSON body injection vectors that are relevant to the actual stack (e.g., injecting operator-like strings into JSONB fields stored in the database, or testing the AI agent query endpoint for prompt injection).

---

**P1-4: `tests/load/stress_test.py` and `tests/load/locustfile.py` — Not integrated into the pytest runner; `locustfile.py` targets stale endpoint paths**

Files: `/Users/devinmcgrath/projects/electricity-optimizer/tests/load/`

Both load test files use endpoint paths that are inconsistent with the current API:
- `locustfile.py` uses `regions = ['UK', 'EU', 'US']` but the project uses the `PriceRegion` enum with values like `us_ct`, `us_ny`, etc. Requests to `?region=UK` will receive 422 from the real API, meaning load test "success" metrics actually measure 422 response throughput.
- `locustfile.py` uses `/api/v1/prices/overview` which does not appear in the backend router based on other test evidence (endpoint references use `/api/v1/prices/current`).
- `stress_test.py` has no pytest entry point — it is a `__main__` script. CI cannot run it via `pytest`.

**Remediation**:
- Update `regions` to use valid enum values (`us_ct`, `us_ma`, etc.).
- Verify `/api/v1/prices/overview` exists or replace with `/api/v1/prices/current`.
- Add a `pytest` wrapper test (e.g., `test_stress_smoke.py`) that runs a reduced concurrency smoke version of `stress_test_endpoint` against a mock server, allowing the load test logic to be regression-tested.

---

**P1-5: `test_services.py` — Relic TDD "RED phase" tests still present and likely redundant**

File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_services.py`, line 9.

```python
"""
RED phase: These tests should FAIL initially until services are implemented.
"""
```

The codebase has ~2,663 backend tests and is production-live. Any tests that "should fail initially" are either now passing (fine) or still failing (a problem). The RED phase comment is misleading to any engineer reviewing test failures in CI. Additionally, `PriceService` is tested here with `get_current_price` (singular) but other tests use `get_current_prices` (plural), suggesting some drift between the service interface tested here and the current implementation.

**Remediation**: Remove the RED phase comment. Audit `test_services.py` to confirm each test maps to the current service API; delete or update any tests that no longer reflect the real interface.

---

#### P2 — Medium

---

**P2-1: `test_security_adversarial.py` — `TestOpenRedirect` assertion whitelist is too permissive; 503 accepted silently**

File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_security_adversarial.py`, lines 778–799.

```python
assert response.status_code in (422, 400, 401, 503), (
    f"External success_url accepted in checkout. Got {response.status_code}."
)
```

A 503 means the DB is unavailable in the test environment. When the DB is always unavailable (which can happen with `module`-scoped `full_app_client`), every checkout test passes as a 503 regardless of whether URL validation is implemented or not. The security property (rejecting external URLs) is never verified.

**Remediation**: Mock the checkout service so the DB layer is bypassed and the 422/400 URL validation response is the one being tested. Alternatively, patch `StripeService.create_checkout_session` to return a known response and then assert the route-level URL validation raises 422 before the service is invoked.

---

**P2-2: `test_security_adversarial.py` — `module`-scoped `full_app_client` with `importlib.reload(main)` is fragile and order-dependent**

File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_security_adversarial.py`, lines 177–227.

The `full_app_client` fixture calls `importlib.reload(_main_mod)` to get a fresh app. Module-level reload affects all cached imports (middleware singletons, rate limiter in-memory state, etc.). If other tests in the same pytest session have already mutated module-level state (e.g., `_app_rate_limiter`), the reload may not fully reset it. This is why `test_tier_gating.py` uses a per-test `autouse` fixture to clear `dependency_overrides` — a safer pattern.

**Remediation**: Replace `module` scope with `function` scope, or extract app construction into a dedicated factory function (already done in `app_factory` per CLAUDE.md). Remove the `importlib.reload` call and use the factory instead.

---

**P2-3: `test_stripe_service.py` — `apply_webhook_action` test coverage gap: `update_subscription` and `deactivate_subscription` actions not tested**

File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_stripe_service.py`

The `apply_webhook_action` tests cover `payment_failed`, `activate_subscription`, user-not-found, and the unhandled event case (lines 480–604). However, `update_subscription` (triggered by `customer.subscription.updated`) and `deactivate_subscription` (triggered by `customer.subscription.deleted`) are handled in `handle_webhook_event` but their corresponding `apply_webhook_action` paths are not covered. This is particularly important given the CLAUDE.md note about the Stripe subscription state bug: `trialing`/`past_due`/`incomplete` must not force `tier=free`.

**Remediation**: Add `test_apply_webhook_action_update_subscription_active`, `test_apply_webhook_action_update_subscription_trialing_does_not_downgrade`, and `test_apply_webhook_action_deactivate_subscription` test cases.

---

**P2-4: `tests/security/test_rate_limiting.py` — `TestConcurrentRequests` uses `ThreadPoolExecutor` against `TestClient` which serializes requests internally**

File: `/Users/devinmcgrath/projects/electricity-optimizer/tests/security/test_rate_limiting.py`, lines 191–208.

`TestClient` from `httpx` (via Starlette) runs the ASGI app in-process and is not thread-safe for concurrent access. Sending 200 requests through 20 threads via `ThreadPoolExecutor` will either serialize them (defeating the concurrency test) or trigger thread-safety issues in the in-memory rate limiter state. The test does not assert any specific outcome from the 200 requests anyway — it only checks that at least one 200 succeeds.

**Remediation**: Use `httpx.AsyncClient` with `anyio` task groups for real concurrency testing. The `test_concurrent_requests_do_not_exceed_limit` test in `test_race_condition_fixes.py` is a better model — it mocks the Redis layer and validates the count directly without a live server.

---

**P2-5: `test_webhooks.py` — GitHub webhook tests do not verify the response body for most event types**

File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_webhooks.py`, lines 132–146.

`TestWebhookEventTypes.test_various_events_accepted` only asserts `response.json()["event"] == event_type`. It does not verify that `ping` events receive a special `{"zen": ...}` pong response, nor that `push` events trigger any downstream action. If the webhook handler is a stub that returns `{"received": True, "event": event_type}` for all inputs, these tests pass even if zero processing occurs.

**Remediation**: Add at least one test per event type that verifies a side-effect (e.g., for `push`, confirm that the board sync hook is called; for `ping`, verify the response contains a `zen` field). For the audit scope, at minimum document what each event type _should_ do so future engineers know what to assert.

---

**P2-6: `test_notification_dispatcher.py` — Concurrent fan-out ordering not tested**

File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_notification_dispatcher.py`

The CLAUDE.md pattern note states: "Notification fan-out: run IN_APP first (creates notification_id), then PUSH+EMAIL via `asyncio.gather(return_exceptions=True)` concurrently." The dispatcher tests verify channel isolation (failure in one does not abort others) but do not verify the ordering invariant: that IN_APP always completes before PUSH/EMAIL are launched, and that the `notification_id` from IN_APP is correctly passed to PUSH and EMAIL. A refactor that reverses the order or runs all three concurrently would pass all existing tests while breaking the documented invariant.

**Remediation**: Add a test that asserts the IN_APP `db.execute` (INSERT) is awaited before `send_push` and `email_service.send` are called. Use `AsyncMock` call order tracking or a `side_effect` that records invocation timestamps.

---

**P2-7: `test_tier_gating.py` — `_make_db` SQL text matching is fragile: case-sensitive uppercase check on ORM-generated SQL**

File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_tier_gating.py`, lines 65–74.

```python
async def _execute(stmt, params=None):
    sql = str(stmt.text if hasattr(stmt, "text") else stmt).upper()
    if "SUBSCRIPTION_TIER" in sql:
        return _scalar_result(tier)
    if "COUNT(*)" in sql:
        return _count_result(alert_count)
```

SQLAlchemy may render column names in any case depending on the ORM version and dialect. If a future ORM update changes `subscription_tier` to a quoted identifier (`"subscription_tier"`), `"SUBSCRIPTION_TIER"` will not match and all tier tests will silently return `None` (treating every user as having no tier — which maps to free). This would cause free-tier 403 tests to pass but pro/business "allowed" tests to also 403, hiding the regression.

**Remediation**: Use case-insensitive matching (`"subscription_tier" in sql.lower()`) or switch to `mock_sqlalchemy_select` from `conftest.py` if it supports the required fields.

---

**P2-8: `test_security.py` — `TestRateLimiter` uses only in-memory fallback; Redis path is never exercised**

File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_security.py`, lines 111–190.

The `rate_limiter` fixture instantiates `UserRateLimiter` without a `redis_client`, meaning all tests exercise only the in-memory code path. The production rate limiter, when Redis is available, runs through an entirely different code path (`_check_redis` / Lua eval). The in-memory path could diverge from the Redis path in behavior. The `test_race_condition_fixes.py` file does cover the Redis path well, but `test_security.py` adds no incremental Redis coverage.

**Remediation**: Either duplicate the key `test_rate_limit_exceeded` and `test_rate_limit_per_user_isolation` tests with a mocked `redis_client`, or add an explicit comment noting that Redis path coverage lives in `test_race_condition_fixes.py` so engineers do not assume `test_security.py` covers it.

---

**P2-9: `tests/performance/test_api_latency.py` — `measure_latencies` silently drops failed requests from the latency distribution**

File: `/Users/devinmcgrath/projects/electricity-optimizer/tests/performance/test_api_latency.py`, lines 83–88.

```python
if response.status_code == 200:
    latencies.append(latency)
# Non-200 responses are silently dropped
```

If the server is returning 401 (due to the mock_token fallback) for all 100 requests, `latencies` will be empty and `PerformanceMetrics([])` will raise a `statistics.StatisticsError` in `p95`, making the test error rather than fail. If some requests are 401 and some are 200, the p95 metric only reflects successful requests — potentially hiding latency introduced by auth failures being retried by the client.

**Remediation**: Assert `len(latencies) >= NUM_REQUESTS * 0.9` before computing metrics (fail fast on high error rates). Record the count of non-200 responses and fail if it exceeds 5%.

---

#### P3 — Low

---

**P3-1: `test_security_adversarial.py` — Section numbering gap in comments (4 is missing; comments jump 3→5)**

File: lines 454–460. The comment reads `# 5. CORS VALIDATION` after `# 3. RATE LIMIT BYPASS`. Section 4 is missing from the comment headers (though the content is complete). Minor but creates confusion when cross-referencing the docstring which lists 11 sections.

---

**P3-2: `tests/security/test_auth_bypass.py` — `datetime.utcnow()` used in token factory fixtures**

File: lines 32–51. `datetime.utcnow()` is deprecated since Python 3.12. Use `datetime.now(timezone.utc)` consistently (as done correctly in `test_security_adversarial.py`).

---

**P3-3: `test_stripe_service.py` — `mock_stripe_configured` fixture uses nested `with` blocks instead of `contextlib.ExitStack`**

File: lines 17–23. Four levels of nested `with patch.object(...)` contexts are hard to read and error-prone if a fifth attribute needs patching. Use `contextlib.ExitStack` or `@pytest.fixture` with multiple `patch` decorators for clarity.

---

**P3-4: `test_savings_aggregator.py` — `TestDisabledFlags` test documents behavior but does not verify the SQL WHERE clause**

File: lines 141–161. The test comment says "DB query should filter" but the mock simply returns pre-filtered results. The test does not verify that `enabled_utilities=["electricity"]` is forwarded to the SQL query as a filter parameter. If `SavingsAggregator.get_combined_savings` ignores the `enabled_utilities` argument, the test still passes.

**Remediation**: Capture `mock_db.execute.call_args` and assert that the SQL text includes an appropriate filter clause for the enabled utilities list.

---

**P3-5: `test_resilience.py` — `_cleanup` method is called in `finally` but teardown is not guaranteed if the fixture is function-scoped**

File: lines 119–122. The `TestDatabaseResilience` tests build a `TestClient` inside each method, install dependency overrides, and call `_cleanup()` in `finally`. This is functionally correct but duplicates the `autouse` teardown pattern used in `test_tier_gating.py`. If a future test is added without the `try/finally` block, overrides will leak across tests. Consider converting to a pytest fixture with `yield`.

---

**P3-6: `test_webhooks.py` — `_make_signature` uses `hmac.new` (deprecated alias) instead of `hmac.HMAC`**

File: line 25.

```python
digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
```

`hmac.new` is a deprecated alias for `hmac.HMAC`. Use `hmac.new(...)` correctly (it is not actually deprecated in the stdlib — this is actually `hmac.new` which is valid, but is less readable than `hmac.HMAC()`). The more modern idiom is:
```python
digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
```
This is functionally correct. However the module-level import `import hmac` and usage via `hmac.new(...)` is idiomatic. Low severity — no action required unless the team wishes to standardize on `hmac.HMAC`.

---

**P3-7: `tests/load/locustfile.py` — `UnauthenticatedBehavior` class is never registered as a standalone task weight**

File: lines 21–45, 225–232. `UnauthenticatedBehavior` is nested inside `MixedUserBehavior.tasks` with weight 2, but `WebsiteUser` directly references `MixedUserBehavior`. The `on_start` in `MixedUserBehavior` is never defined, so Locust will not call setup for nested task sets. This is a Locust API misuse that silently reduces test coverage of unauthenticated behavior.

---

### Statistics

| Category | Count |
|---|---|
| Files reviewed (full read) | 20 |
| Files scanned (pattern review) | 36 |
| Total files in scope | 56 |
| P0 (Critical) | 3 |
| P1 (High) | 5 |
| P2 (Medium) | 9 |
| P3 (Low) | 7 |
| **Total findings** | **24** |

---

### File Quality Matrix

| File | Quality | Notes |
|---|---|---|
| `test_race_condition_fixes.py` | Excellent | Precise Lua-atomicity assertions, cancellation/exception paths, boundary conditions |
| `test_notification_dispatcher.py` | Excellent | Full channel routing matrix, dedup, fail-open, metadata passthrough |
| `test_tier_gating.py` | Excellent | Clean dependency overrides, business-logic focused, autouse teardown |
| `test_security_adversarial.py` | Good | Real middleware tested; P2-1 on 503 acceptance, P2-2 on module reload |
| `test_resilience.py` | Good | HNSW fallback + DB error degradation well covered |
| `test_webhooks.py` | Good | HMAC verification path solid; event-type coverage thin (P2-5) |
| `test_stripe_service.py` | Good | Missing `apply_webhook_action` paths for update/deactivate (P2-3) |
| `test_security.py` | Good | In-memory rate limiter path only (P2-8); security headers thorough |
| `test_neon_auth.py` | Good | TTL invariant test is precise and well-motivated |
| `test_savings_aggregator.py` | Good | Coverage complete; WHERE clause not verified (P3-4) |
| `test_performance.py` (backend) | Good | Query-count and cache-hit assertions are precise and meaningful |
| `test_scraper_persistence.py` | Good | Rate extraction unit tests comprehensive |
| `test_portal_scraper_service.py` | Good | HTTP mock injection clean pattern |
| `test_sse_streaming.py` | Good | Generator exhaustion + cancel paths covered |
| `test_observation_service.py` | Good | All public methods documented and tested |
| `test_supplier_cache.py` | Good | Cache hit/miss/invalidation well structured |
| `tests/security/test_auth_bypass.py` | Poor | P0-1: hollow tests, wrong signing secret in fixtures |
| `tests/security/test_sql_injection.py` | Poor | P0-2: accepts 500; always-unauthenticated; NoSQL tests misaligned |
| `tests/security/test_rate_limiting.py` | Poor | P0-3: multiple no-op or always-passing tests |
| `tests/performance/test_api_latency.py` | Poor | P1-1: requires live server; fails silently; mock_token path |
| `tests/load/stress_test.py` | Adequate | Well-designed metrics; not pytest-integrated; stale endpoints |
| `tests/load/locustfile.py` | Adequate | Good task weight model; stale region values; TaskSet misuse |

---

### Recommendations

1. **Immediate (pre-next-deploy)**: Fix P0-2 in `tests/security/test_sql_injection.py` — the current suite would pass even if the backend returned HTTP 500 with SQL error text in the response body, because `500` is in the assertion whitelist.

2. **This sprint**: Quarantine or fix `tests/security/test_auth_bypass.py` and `tests/security/test_rate_limiting.py`. These files appear in the security test suite and give false CI confidence. Options: (a) delete the hollow no-op tests, (b) add `@pytest.mark.xfail(strict=False)` with a linked issue, or (c) rewrite using the dependency-override pattern.

3. **This sprint**: Add the missing `apply_webhook_action` paths for `update_subscription` and `deactivate_subscription`, with an explicit test for the `trialing` subscription state not downgrading to `free` (directly from CLAUDE.md critical pattern: "only force `tier=free` for terminal states (`canceled`, `unpaid`), NOT for `trialing`/`past_due`/`incomplete`").

4. **Next sprint**: Integrate `tests/performance/test_api_latency.py` into a `@pytest.mark.integration` run gate with an explicit env-var guard. Update endpoint paths in `tests/load/locustfile.py` to match the current PriceRegion enum values.

5. **Backlog**: Add notification fan-out ordering test (P2-6) and the SQL WHERE-clause assertion to `test_savings_aggregator.py` (P3-4). Both close coverage gaps that a silent refactor could exploit.
