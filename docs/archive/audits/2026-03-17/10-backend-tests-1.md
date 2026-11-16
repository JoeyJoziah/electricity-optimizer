# Audit Report: Backend Tests (A-M)
## Date: 2026-03-17

---

### Executive Summary

**Scope**: 66 files matching `backend/tests/test_[a-m]*.py` plus `backend/tests/conftest.py`. A total of 1,654 test functions were counted across these files.

**Overall impression**: The test suite is large, well-organized, and reflects genuine engineering investment. The `conftest.py` infrastructure — particularly `mock_sqlalchemy_select`, `reset_tier_cache`, and `reset_rate_limiter` — is sophisticated and correctly addresses cross-test state leakage. The billing, authentication, dunning, alert, and integration path tests are exemplary in depth and coverage of edge cases.

The primary risk areas are: (1) a cluster of empty test stubs that pass trivially (especially in the GDPR compliance module), (2) several internal API endpoints that expose raw exception messages verbatim in 500 responses without any test asserting the message is sanitized in production mode, (3) the `conftest.py` model attribute list being brittle and not automatically maintained, and (4) a handful of time-sensitive assertions in `conftest.py` that introduce low but non-zero flakiness potential.

---

### Findings

---

#### P0 — Critical

**P0-1: Empty async test stubs that pass silently — GDPR compliance (14 tests)**

File: `backend/tests/test_gdpr_compliance.py`

The following 14 async test methods contain only a comment or `pass` — they execute, yield no assertion failure, and pytest counts them as passed. This creates a false sense of coverage for GDPR features that are legally significant (Article 15, 17, 20, 21):

- `TestGDPRComplianceAPI.test_consent_endpoint_requires_auth` (line 776) — body ends with `# For now, just verify the endpoint exists`, no assertions
- `TestGDPRComplianceAPI.test_record_consent_endpoint` (line 785) — body is only a comment
- `TestGDPRComplianceAPI.test_export_data_endpoint` (line 790) — body is only a comment
- `TestGDPRComplianceAPI.test_delete_data_endpoint` (line 795) — body is only a comment
- `TestGDPRComplianceAPI.test_consent_history_endpoint` (line 800) — body is only a comment
- `TestDataRetention.test_identify_expired_data` (line 821) — body is only a comment
- `TestDataRetention.test_purge_expired_data` (line 826) — body is only a comment
- `TestDataRetention.test_retention_respects_legal_holds` (line 831) — body is only a comment
- `TestGDPRIntegration.test_full_consent_flow` (line 885) — body is only a comment
- `TestGDPRIntegration.test_full_data_export_flow` (line 890) — body is only a comment
- `TestGDPRIntegration.test_full_deletion_flow` (line 895) — body is only a comment
- `TestGDPRIntegration.test_consent_persists_across_sessions` (line 900) — body is only a comment
- `TestGDPRComplianceService.test_withdraw_all_consents` (line 580) — invokes the service method but asserts nothing; the comment `# Should create withdrawal records for all consent types` is the only indication of intent
- `TestDeletionLog.test_deletion_log_immutable` (line 744) — creates a `DeletionLog` instance but tests nothing about immutability (Pydantic models are not immutable by default unless `model_config = ConfigDict(frozen=True)`)

All of these tests pass when run but assert nothing. The `DataRetentionService` and `TestGDPRIntegration` classes particularly mask a gap: there are zero real assertions verifying that data retention enforcement works or that the integration between consent, export, and deletion is correct end-to-end.

**Remediation**: Either implement the test bodies or mark them with `@pytest.mark.skip(reason="not implemented")` so they are clearly visible as gaps rather than appearing as passed coverage.

---

**P0-2: Internal alert 500 response leaks raw exception message in detail field — test validates the leak**

File: `backend/tests/test_internal_alerts.py`, method `TestCheckAlerts.test_service_exception_returns_500` (line 314)

```python
assert "Alert check failed" in response.json()["detail"]
assert "Neon connection lost" in response.json()["detail"]
```

The test asserts that the raw exception string `"Neon connection lost"` appears verbatim in the API response body. This is testing that the production code leaks internal infrastructure error messages to callers. While the internal endpoint is API-key gated (not user-facing), the same pattern likely exists across other internal endpoints and should not be the intended behavior even for internal consumers. Grafana/Sentry should be the channel for raw exception details, not response bodies.

**Remediation**: The endpoint should log `str(e)` but return a generic message like `"Alert check failed: internal error"`. The test should be updated to assert only on the "Alert check failed" prefix, not the raw exception message.

---

#### P1 — High

**P1-1: `conftest.py` model attribute list is a manual registry with no compile-time safety**

File: `backend/tests/conftest.py`, lines 477-492

The `mock_sqlalchemy_select` fixture manually lists model class attributes for `Price`, `User`, `Supplier`, and `Tariff`. The project CLAUDE.md explicitly warns: "MUST add new fields when adding columns." This creates a silent failure mode: if a new column is added to `Price` or `User` but not added to this list, tests that use those columns in SQLAlchemy expressions will silently use the real Pydantic descriptor instead of `_ColumnMock`, potentially raising `AttributeError` at import time or during comparison operations — but only in certain test orderings. This is order-dependent flakiness.

Current patched fields for `User` (line 484):
```python
"User": [
    "id", "email", "name", "region", "created_at", "is_active",
    "current_supplier_id", "utility_types", "annual_usage_kwh",
    "onboarding_completed",
],
```

Fields visible in the project that may be missing: `stripe_customer_id`, `subscription_tier`, `preferences`, `notification_settings`. These are referenced in billing and user tests but are not patched here — if any repository test exercises `User.subscription_tier` in a `select()` expression this will break.

**Remediation**: Add a pytest plugin or `conftest.py` check that introspects all Pydantic model fields at test session start and warns if the patched set is a strict subset of actual fields. Alternatively, use `vars(cls)` to enumerate `FieldInfo` descriptors automatically rather than maintaining a static list.

---

**P1-2: `flatpeak_forecast_response` fixture uses `datetime.now()` — time-sensitive test data**

File: `backend/tests/conftest.py`, lines 179-195

```python
base_time = datetime.now(timezone.utc)
return {
    "data": {
        ...
        "prices": [
            {
                "timestamp": (base_time + timedelta(hours=i)).isoformat(),
                ...
                "is_peak": 16 <= (base_time.hour + i) % 24 <= 21,
            }
            for i in range(24)
        ],
    }
}
```

The `is_peak` value in this fixture is computed relative to the actual wall-clock hour at test execution time. Any test that asserts on peak/off-peak outcomes using this fixture will produce different results depending on when the tests run, making them intermittently flaky. If tests run between 16:00-21:00 UTC the peak window shifts compared to off-hours execution.

**Remediation**: Pin `base_time` to a fixed timestamp, e.g., `datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)`, mirroring what `sample_forecast_data` does correctly at line 120.

---

**P1-3: `test_api_user.py` has no coverage of `PUT /users/profile` (name update endpoint)**

File: `backend/tests/test_api_user.py`

The file covers only `GET /preferences` and `POST /preferences`. The MEMORY.md and CLAUDE.md describe a profile name update via `PUT /users/profile` with `{ name }`. There are no tests for:
- Successful name update
- Empty name rejection
- Name update requiring auth (401 without credentials)
- Name update returning the updated user object

This is a user-data mutation endpoint with no test coverage, which is a meaningful gap.

---

**P1-4: `test_auth.py` does not test the `ensure_user_profile` best-effort sync path**

File: `backend/tests/test_auth.py`, `TestAuthIntegration.test_me_endpoint_with_valid_session` (line 781)

The test comments say `# for ensure_user_profile best-effort sync` but the mock `mock_db` is only configured to not crash. There are no assertions that:
- `ensure_user_profile` is called
- DB errors in `ensure_user_profile` do not propagate to the caller (it should be best-effort/fire-and-forget)
- The `/me` response is correct even when `ensure_user_profile` fails

If `ensure_user_profile` is ever wired to raise on failure, this silent test would pass while masking the regression.

---

**P1-5: Agent rate limiting TOCTOU fix is not tested atomically**

File: `backend/tests/test_agent_service.py`, `test_rate_limit_free_tier` (line 225)

The CLAUDE.md specifically documents a prior P0 TOCTOU race condition fix for agent rate limiting: "use `INSERT ... ON CONFLICT DO UPDATE SET count=count+1 RETURNING count` for atomic TOCTOU-safe rate limiting." The test mocks `db.execute.return_value = MagicMock(scalar=MagicMock(return_value=3))` but does not verify that a single atomic statement is used (not a SELECT then INSERT). The mock makes both a two-query and a one-query implementation pass identically.

**Remediation**: Assert `mock_db.execute.call_count == 1` and inspect `mock_db.execute.call_args` to confirm the SQL uses `INSERT ... ON CONFLICT` rather than a separate `SELECT COUNT(*)`.

---

**P1-6: `test_gdpr_compliance.py` does not verify community/notification table deletion**

File: `backend/tests/test_gdpr_compliance.py`, `TestGDPRComplianceService.test_delete_user_data_deletes_all_categories` (line 491)

Migration 051 added GDPR CASCADE fixes specifically to cover `community_posts`, `community_votes`, `community_reports`, and `notifications` foreign keys. The test asserts `set(result.data_categories_deleted) == expected` where `expected` is:

```python
expected = {
    "consents", "price_alerts", "recommendations",
    "activity_logs", "extracted_rates", "bill_uploads",
    "connections", "supplier_accounts", "profile",
    "agent_data", "community_data", "notifications",
    "feedback",
}
```

The set includes `"community_data"` and `"notifications"` as strings, but the test verifies the returned label only — it does not assert that `db_session.execute` was called with SQL statements targeting `community_posts`, `community_votes`, `community_reports`, or `notifications` tables. The test at line 573 asserts `mock_db_session.execute.call_count >= 9` (a very loose lower bound), which would pass even if those tables were never touched.

**Remediation**: Add explicit inspection of `mock_db_session.execute.call_args_list` to assert that the SQL statements reference `community_posts`, `community_votes`, `community_reports`, and `notifications` tables.

---

#### P2 — Medium

**P2-1: `test_api_billing.py` webhook tests do not assert that `customer.subscription.updated` with `trialing` status does NOT trigger a downgrade**

File: `backend/tests/test_api_billing.py`

The CLAUDE.md documents a critical pattern: "Stripe subscription `customer.subscription.updated`: only force `tier=free` for terminal states (`canceled`, `unpaid`), NOT for `trialing`/`past_due`/`incomplete`." The billing test file has `TestSubscriptionStatus.test_subscription_trialing_is_active` (line 509) which confirms the GET endpoint reports trialing correctly, but there is no webhook test asserting that a `customer.subscription.updated` event with `status=trialing` does NOT call `repo_instance.update` with `tier=free`. The prior bug was that trialing triggered a downgrade — without a regression test for the webhook path, this could regress silently.

---

**P2-2: Duplicate `auth_client`/`unauth_client` fixture pattern repeated across 17+ test files without shared fixture module**

Files: `test_api_billing.py`, `test_internal_alerts.py`, `test_community_api.py`, `test_internal_billing.py`, and 13 others

Every internal API test file defines nearly identical `auth_client` and `unauth_client` fixtures: create `TestClient`, inject `verify_api_key` and `get_db_session` overrides, yield, pop overrides. This pattern is copy-pasted in 17+ files. Maintenance cost: when the fixture pattern needs to change (e.g., if a new dependency like `get_redis` becomes required everywhere), all 17 files must be updated. Additionally, missing a `pop` in one file's teardown leaks override state to subsequent tests (observed risk — the `unauth_client` in `test_api_billing.py` does not pop `get_current_user` in teardown since it was never set, which is fine, but a reviewer must verify this for every file).

**Remediation**: Extract the shared `auth_client`/`unauth_client` pattern into `conftest.py` as parameterized fixtures, allowing file-specific customization via indirect parametrize or fixture factories.

---

**P2-3: `TestRecordPaymentFailure.test_creates_row` does not assert on the returned value**

File: `backend/tests/test_dunning_service.py`, lines 73-115

```python
result = await dunning.record_payment_failure(...)
assert mock_db.execute.await_count == 2  # COUNT + INSERT
```

The test verifies only that `execute` was called twice. It does not assert on:
- The shape of the returned object (is it a dict? A dataclass?)
- That `retry_count` in the result reflects the correct value (1 for first failure)
- That the returned `retry_type` is `"soft"` (not `"final"`) for a first failure

The returned value is discarded entirely. If `record_payment_failure` starts returning `None` due to a bug, this test still passes.

---

**P2-4: `test_analytics_service.py` fixture `mock_repo.get_price_statistics_with_stddev` returns `None` values but some analytical functions may not handle `None` gracefully**

File: `backend/tests/test_analytics_service.py`, lines 77-80

```python
repo.get_price_statistics_with_stddev = AsyncMock(return_value={
    "min_price": None, "max_price": None, "avg_price": None,
    "stddev_price": None, "count": 0, ...
})
```

This represents an empty-database scenario. Without seeing the full test body, if `AnalyticsService.calculate_volatility` attempts arithmetic on `None` values (e.g., `float(stddev_price) / float(avg_price)`), it would raise a `TypeError`. If the service handles this with a guard, there should be explicit tests asserting the return value structure for the no-data case — which should be verified across all analytical methods, not just the happy path.

---

**P2-5: `test_connections.py` assigns `TEST_CONNECTION_ID = str(uuid4())` at module load time**

File: `backend/tests/test_connections.py`, line 35

```python
TEST_CONNECTION_ID = str(uuid4())
```

This is evaluated once per test session. If the test module is re-imported (e.g., in workers with parallel test execution), each worker will get a different UUID, making cross-worker assertions on this ID inconsistent. The pattern used elsewhere (e.g., `TEST_USER_ID = "aaaaaaaa-0000-0000-0000-000000000001"`) with a stable hardcoded UUID is preferable for test IDs that need to be referenced across multiple assertions within a test file.

---

**P2-6: `test_gdpr_compliance.py` — `TestConsentRepository.test_create_consent_record` asserts `commit` was called once but the CLAUDE.md notes the delete path does NOT commit**

File: `backend/tests/test_gdpr_compliance.py`, line 648

```python
mock_db_session.commit.assert_called_once()
```

The `create` method commits, but `delete_by_user_id` intentionally does NOT commit (line 712, "Note: delete_by_user_id does NOT commit — the caller (GDPR atomic deletion block) is responsible"). The asymmetry is documented in the test for delete but is worth an explicit cross-reference assertion: a test should confirm that calling `delete_by_user_id` followed by `create` results in exactly one commit (from `create`), not two, demonstrating the caller-managed transaction semantics work correctly.

---

**P2-7: `test_forecast_observation_repository.py` missing tests for concurrent insert behavior**

File: `backend/tests/test_forecast_observation_repository.py`

The repository has `insert_forecasts` with a batch-INSERT pattern. The tests cover the happy path and empty-guard, but there are no tests for:
- What happens when a duplicate `(region, forecast_hour)` key is inserted (INSERT ON CONFLICT DO NOTHING or DO UPDATE?)
- Partial batch failure rollback semantics
- Very large batch sizes that might exceed Postgres parameter limits

---

**P2-8: `conftest.py` `event_loop` fixture is deprecated in newer pytest-asyncio versions**

File: `backend/tests/conftest.py`, lines 35-40

```python
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

`pytest-asyncio` >= 0.21 deprecated the `event_loop` fixture override at session scope. In `pytest-asyncio` >= 0.23 it was removed entirely, and in newer versions the correct approach is `asyncio_mode = "auto"` with `@pytest.mark.asyncio(loop_scope="session")` or a `pytest.ini` configuration. Given the project just upgraded to `pytest 9` (per MEMORY.md), this fixture override may generate deprecation warnings on every test run or silently fail if pytest-asyncio is also at a recent version. Deprecation warnings at scale (66 files) create noise that buries real warnings.

---

**P2-9: `test_internal_alerts.py` `test_service_exception_returns_500` tests that raw error message appears in detail**

File: `backend/tests/test_internal_alerts.py`, lines 326-329

See also P0-2. Beyond the security concern noted there, this test tightly couples to the exact exception message string `"Neon connection lost"`. If the exception message changes phrasing (e.g., "Neon DB connection lost" after a library upgrade), this test breaks even though the behavior is correct. Error message strings are fragile test anchors.

---

**P2-10: Missing coverage for `test_agent_service.py` — Groq client is None when Gemini raises 429**

File: `backend/tests/test_agent_service.py`, `test_gemini_429_falls_back_to_groq` (line 155)

The test covers the case where Gemini raises 429 and Groq is available. But there is no test for: Gemini raises 429 AND `groq_api_key` is `None` (no Groq configured). In this case the service should yield an appropriate error rather than attempting to call a `None` Groq client. If the fallback code path does `if self._groq_client:` this is fine, but if it unconditionally calls `self._groq_client.chat.completions.create()` it will raise `AttributeError`.

---

**P2-11: `test_auth.py` rate-limit tests (`TestAuthRateLimiting`) use in-memory state but the fixture is not reset between test methods**

File: `backend/tests/test_auth.py`, lines 517-581

`TestAuthRateLimiting` creates `UserRateLimiter` instances inside each test method, so there is no cross-test leakage. However, `test_login_rate_limit_after_failures` (line 517) loops 5 times but checks `locked is True` only on the return value of the 5th call, discarding the return values of calls 1-4:

```python
for i in range(5):
    locked = await limiter.record_login_attempt(identifier, success=False)
# 5th attempt should trigger lockout
assert locked is True
```

The comment says "5th attempt should trigger lockout" but the variable `locked` is reassigned on each iteration — it holds the return value of the 5th call, which is correct, but the first 4 return values are silently discarded. If the limiter incorrectly locks out on attempt 3, the test would still pass because it only checks attempt 5. A better pattern is to assert `locked is False` for the first 4 and `locked is True` only for the 5th.

---

#### P3 — Low

**P3-1: Inconsistent use of `assert isinstance(result, SessionData)` vs direct field assertion**

Files: `test_auth.py` (lines 67, 102, 285)

Some tests do `assert isinstance(result, SessionData)` followed by field assertions. Others skip the isinstance check and go directly to field assertions. The isinstance check is good defensive practice (ensures the return type contract is met) but is applied inconsistently. Standardize to always include it for functions with typed return values.

---

**P3-2: `test_dunning_service.py` fixture `mock_user_repo.get_by_id` returns a user with `subscription_tier = "pro"` but `test_no_op_if_already_free` mutates the return value inline**

File: `backend/tests/test_dunning_service.py`, lines 240-248

```python
async def test_no_op_if_already_free(self, dunning, mock_user_repo):
    user = mock_user_repo.get_by_id.return_value
    user.subscription_tier = "free"
    ...
```

This works but mutates the shared fixture state. If test ordering changes and another test in the same class runs after `test_no_op_if_already_free`, the `mock_user_repo` fixture will have `subscription_tier = "free"` instead of `"pro"`. However, because `mock_user_repo` has function scope (via the `@pytest.fixture` default), this is safe today. A comment clarifying this would prevent future confusion when someone changes the fixture scope.

---

**P3-3: `test_api_billing.py` `TEST_USER`, `ALLOWED_SUCCESS_URL` constants are module-level but could be conftest fixtures**

File: `backend/tests/test_api_billing.py`, lines 21-29

These constants are fine as module-level values but `ALLOWED_SUCCESS_URL = "https://rateshift.app/success"` is hardcoded. If the domain changes (e.g., the app is renamed again), this must be updated manually. The allowed URL list is presumably validated in the production code from `settings.ALLOWED_REDIRECT_DOMAINS`. A test that reads the allowed list from settings would be more robust against domain drift.

---

**P3-4: Missing `__all__` or module docstrings on approximately 12 test files in the A-M range**

Files: `test_ab_test_service.py`, `test_affiliate_service.py`, `test_bill_parser.py`, `test_circuit_breaker.py`, `test_data_quality_service.py`, `test_geocoding_service.py`, and others

While the more recently written files (especially everything from the Quality Hardening sprint) have thorough module docstrings, older files lack them. This is a minor documentation gap with no functional impact.

---

**P3-5: `test_community_api.py` uses an elaborate in-memory `_MockCommunityDB` class that duplicates SQL routing logic**

File: `backend/tests/test_community_api.py`, lines 41-100+

The `_MockCommunityDB` class implements string-matching dispatch on SQL text to simulate the community tables. This is a creative approach that enables full-API testing without a database, but the SQL-text matching (e.g., `if "INSERT INTO COMMUNITY_VOTES" in sql and "DELETE FROM COMMUNITY_VOTES" in sql`) is fragile: if the CTE query structure changes in the service layer, the mock's dispatch will silently match the wrong branch. A simpler `AsyncMock` approach with pre-canned return values would be more maintainable, or the test could use `pytest-postgresql` for an in-process test DB.

---

**P3-6: `test_integrations.py` imports both `ForecastData` and `PriceForecast` from the same module for backward compatibility but the alias creates confusion**

File: `backend/tests/test_integrations.py`, lines 27-28

```python
from integrations.pricing_apis.base import (
    ForecastData,
    ForecastData as PriceForecast,  # backward-compat alias used in tests below
)
```

This dual import is explained by a comment but signals that the codebase has a naming inconsistency that has leaked into tests. If `PriceForecast` is the public-facing name but `ForecastData` is the internal class, the test should use one canonical name. If the alias is temporary, a `TODO: remove alias after all references updated` comment would clarify intent.

---

### Statistics

| Metric | Value |
|---|---|
| Total test files audited (A-M range) | 66 |
| Total test functions | 1,654 |
| Files with `app.dependency_overrides` usage | 30 |
| Files with in-memory mock DB classes | 2 (`test_community_api.py`, `test_api_alerts.py`) |
| Empty test stubs (no assertions) | 14 (all in `test_gdpr_compliance.py`) |
| P0 findings | 2 |
| P1 findings | 6 |
| P2 findings | 11 |
| P3 findings | 6 |
| Total findings | 25 |

**Priority remediation order**:
1. Implement or skip the 14 empty GDPR test stubs (P0-1) — GDPR compliance is legally significant
2. Fix the internal endpoint exception message leak test pattern (P0-2)
3. Add `subscription_tier` and related fields to `conftest.py` model_attrs list (P1-1)
4. Pin `flatpeak_forecast_response` base_time to a fixed timestamp (P1-2)
5. Add webhook regression test for `trialing` status not triggering downgrade (P2-1)
6. Extract shared `auth_client`/`unauth_client` pattern to conftest (P2-2)
7. Migrate `event_loop` fixture to pytest-asyncio >= 0.21 pattern (P2-8)

---

*Generated by Claude Code on 2026-03-17. Files read: `conftest.py`, `test_auth.py`, `test_api_billing.py`, `test_gdpr_compliance.py`, `test_agent_service.py`, `test_alert_service.py`, `test_dunning_service.py`, `test_community_api.py` (partial), `test_internal_billing.py` (partial), `test_forecast_service.py` (partial), `test_analytics_service.py` (partial), `test_community_service.py` (partial), `test_migrations.py` (partial), `test_encryption.py` (partial), `test_integration_paths.py` (partial), `test_api_compliance.py` (partial), `test_connections.py` (partial), `test_internal_alerts.py`, `test_integrations.py` (partial), `test_api_user.py`, `test_feature_flags.py` (partial), `test_internal_ml.py` (partial), `test_forecast_observation_repository.py` (partial), `test_internal_data_pipeline.py` (partial). Remaining ~43 files scanned for structural patterns via grep.*
