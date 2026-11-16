# API Routes Audit Report

> Generated: 2026-03-19
> Scope: All files in `backend/api/` (v1/*.py, v1/connections/*.py, v1/internal/*.py), `backend/routers/`, `backend/main.py`
> Auditor: Claude Opus 4.6 (READ-ONLY)

---

## P0 -- Critical (must fix before next deploy)

### P0-01: OAuth callback state timestamp expiry is never enforced

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/common.py`
- **Lines**: 42, 75-100
- **Description**: `OAUTH_STATE_TIMEOUT_SECONDS = 600` is defined on line 42 but `verify_callback_state()` (lines 75-100) never checks whether the timestamp embedded in the state parameter has expired. An attacker who obtains a signed state value can replay it indefinitely.  The timestamp is parsed from the state string on line 88 (`connection_id, user_id, timestamp, received_sig = parts`) but is never compared against the current time.
- **Impact**: Replay attacks on OAuth callback endpoints (UtilityAPI and email OAuth flows).  A captured or leaked state parameter remains valid forever.
- **Recommendation**: After HMAC verification succeeds, compare `int(timestamp)` against `int(time.time())` and reject if the difference exceeds `OAUTH_STATE_TIMEOUT_SECONDS`.

### P0-02: `connection_id` path parameters are `str` throughout the connections package -- no UUID validation

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/crud.py`
- **Lines**: 186, 226, 269 (get_connection, delete_connection, update_connection)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/direct_sync.py`
- **Lines**: 299, 352 (trigger_sync, get_sync_status)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/rates.py`
- **Lines**: 41, 130 (get_rates, get_current_rate)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/portal_scrape.py`
- **Line**: 162 (trigger_portal_scrape)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/email_oauth.py`
- **Line**: 232 (trigger_email_scan)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/bill_upload.py`
- **Lines**: 148, 290, 348, 398 (upload_bill_file, list_bill_uploads, get_bill_upload, reparse_bill_upload)
- **Description**: All `connection_id` path parameters across the connections package are typed as `str`, not `uuid.UUID`.  Malformed values (e.g., SQL-injection-style strings, path traversal attempts) pass through to SQL queries.  Although parameterized queries prevent SQL injection, the lack of UUID validation means the database must handle the type mismatch, and error messages may leak schema details.
- **Impact**: Invalid connection IDs are not rejected at the API boundary. Database-level type errors may produce inconsistent HTTP status codes (500 instead of 422).
- **Recommendation**: Change all `connection_id: str` path parameters to `connection_id: uuid.UUID` (matching the pattern used in `alerts.py`, `notifications.py`, and `utility_accounts.py`).

### P0-03: `post_id` path parameters in community.py are `str` -- no UUID validation

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/community.py`
- **Lines**: 155, 187, 208 (edit_post, toggle_vote, report_post)
- **Description**: `post_id` is typed as `str` on all three mutation endpoints.  The `create_post` endpoint generates UUID primary keys, but the downstream endpoints accept arbitrary strings, so invalid values propagate to `CommunityService` and into SQL queries.
- **Impact**: Same as P0-02 -- invalid post IDs bypass API-level validation.
- **Recommendation**: Change `post_id: str` to `post_id: uuid.UUID` on all three endpoints.

### P0-04: `job_id` in agent.py is `str` -- no UUID validation

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/agent.py`
- **Line**: 237 (get_task_result)
- **Description**: `job_id: str` is not validated as a UUID.  The `query_async` method generates UUID job IDs, but the polling endpoint accepts arbitrary strings.
- **Impact**: Invalid job IDs are passed to `AgentService.get_job_result()` without type checking.
- **Recommendation**: Change to `job_id: uuid.UUID`.

### P0-05: `cca_id` in cca.py is `str` -- no UUID or format validation

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/cca.py`
- **Lines**: 52, 68 (compare_cca_rate, cca_info)
- **Description**: `cca_id` path parameter accepts arbitrary strings with no format validation.
- **Recommendation**: Add UUID type annotation or apply a regex pattern constraint.

### P0-06: `program_id` in community_solar.py is `str` -- no UUID or format validation

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/community_solar.py`
- **Line**: 86 (get_community_solar_program)
- **Description**: `program_id` path parameter accepts arbitrary strings with no format validation.
- **Recommendation**: Add UUID type annotation or apply a regex pattern constraint.

### P0-07: `payload: dict` on direct/authorize endpoint -- no Pydantic model

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/direct_sync.py`
- **Line**: 43 (`payload: dict`)
- **Description**: The `POST /direct/authorize` endpoint accepts a raw `dict` as the request body instead of a Pydantic model.  This means:
  1. No OpenAPI schema documentation is generated for the request body.
  2. No automatic type validation or coercion occurs.
  3. Arbitrary extra fields are silently accepted.
  4. The endpoint manually checks `payload.get("supplier_id")` and `payload.get("consent_given")` on lines 66-77, which is error-prone and inconsistent with every other endpoint in the codebase.
- **Impact**: Missing input validation, inconsistent API contracts, poor developer experience.
- **Recommendation**: Create a `CreateUtilityAPIAuthRequest` Pydantic model with `supplier_id: uuid.UUID` and `consent_given: bool` fields.

---

## P1 -- High (should fix soon, potential security or reliability risk)

### P1-01: `verify-code` endpoint uses SQL LIKE with user-controlled pattern characters

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/beta.py`
- **Lines**: 211-214
- **Description**: The verify-code endpoint builds a LIKE pattern from user input: `{"pattern": f"%code={code}%"}`.  If `code` contains `%` or `_` characters (SQL LIKE wildcards), the query will match unintended rows.  For example, `code="%"` matches all rows with any code.
- **Impact**: An attacker could submit `code=%` and the query would match every beta signup row, causing the endpoint to iterate through all of them and potentially find a valid code via `hmac.compare_digest`.  However, the constant-time comparison on line 230 prevents timing attacks, so the real risk is that `code=BETA-%` would match any signup and eventually succeed on the first extracted code.  This effectively allows brute-force bypass of the beta code verification.
- **Recommendation**: Escape LIKE wildcards in `code` before interpolation, or switch to an exact match (store beta codes in a dedicated indexed column rather than embedded in a serialized `interest` field).

### P1-02: UpdateAlertRequest has no region validation (unlike CreateAlertRequest)

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/alerts.py`
- **Lines**: 78-86
- **Description**: `CreateAlertRequest` validates the `region` field against `_REGION_RE` (line 58-62), but `UpdateAlertRequest` on lines 78-86 has `region: str | None = None` with no `@field_validator`.  An update request with `region="'; DROP TABLE--"` would pass Pydantic validation.
- **Impact**: While parameterized queries prevent SQL injection, invalid region codes would be persisted to the database, potentially causing downstream failures when alerts are evaluated.
- **Recommendation**: Add the same `@field_validator("region")` to `UpdateAlertRequest`.

### P1-03: Mock data returned in non-production environments on any exception

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/prices.py`
- **Lines**: 154-179 (get_current_prices), 297-334 (get_price_history), 376-401 (get_price_forecast), 454-486 (compare_prices)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/prices_analytics.py`
- **Lines**: 79-94 (get_price_statistics), 140-175 (get_optimal_usage_windows), 206-221 (get_price_trends), 257-267 (get_peak_hours_analysis)
- **Description**: Every price endpoint catches all exceptions and returns mock data when `settings.environment != "production"`.  In staging or preview environments, this masks real errors.  The `source: "fallback"` field is included but callers may not check it.
- **Impact**: Bugs in price services, database connection issues, and misconfigured queries are silently masked in non-production environments, making them harder to detect before production deployment.
- **Recommendation**: Consider logging the error at WARNING level and returning a 503 with the fallback data only when an explicit `ENABLE_MOCK_FALLBACK` flag is set, rather than basing it on environment name.

### P1-04: Affiliate click endpoint is fully unauthenticated with no rate limiting

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/affiliate.py`
- **Lines**: 35-66 (record_affiliate_click)
- **Description**: `POST /affiliate/click` has no authentication dependency and no per-endpoint rate limiting.  It accepts an arbitrary `user_id` field in the request body (line 32), meaning anyone can spoof affiliate clicks with fabricated user IDs.
- **Impact**: Click fraud, inflated affiliate metrics, potential financial impact if clicks are monetized.
- **Recommendation**: Either require authentication, or remove the `user_id` field from the public request body and rely solely on IP/session-based tracking.  Add per-endpoint rate limiting.

### P1-05: `list_posts` endpoint is fully unauthenticated with no input validation on region/utility_type

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/community.py`
- **Lines**: 121-145
- **Description**: `GET /community/posts` requires `region` and `utility_type` as mandatory query parameters but performs no validation on either.  Unlike `create_post` (which validates against `VALID_UTILITY_TYPES` and `VALID_POST_TYPES`), the list endpoint passes raw strings directly to `CommunityService.list_posts()`.  Additionally, the endpoint is fully unauthenticated, which is intentional for public community viewing but means there is no user-based rate limiting beyond the global middleware.
- **Impact**: Arbitrary strings in `region` and `utility_type` are passed to SQL queries (parameterized, so no injection risk, but inconsistent data filtering behavior).
- **Recommendation**: Validate `utility_type` against `VALID_UTILITY_TYPES` and `region` against a regex or enum.

### P1-06: `community/stats` endpoint has no region validation

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/community.py`
- **Lines**: 229-237
- **Description**: `GET /community/stats` accepts a `region` query parameter with no validation.  Arbitrary strings are passed to `CommunityService.get_stats()`.
- **Recommendation**: Validate against the region regex or enum.

### P1-07: Error message leaks internal exception details in predictions.py

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/routers/predictions.py`
- **Lines**: 483, 570, 666
- **Description**: All three prediction endpoints return the raw `str(e)` exception message in the HTTP response detail: `detail=f"Failed to generate forecast: {str(e)}"`.  This can leak internal implementation details (database errors, file paths, library versions) to clients.
- **Impact**: Information disclosure that aids attacker reconnaissance.
- **Recommendation**: Return a generic error message and log the full exception details server-side.

### P1-08: `get_beta_stats` has unused pagination parameters

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/beta.py`
- **Lines**: 178-201
- **Description**: The `get_beta_stats` endpoint accepts `page` and `page_size` parameters (line 179-180) but never uses them for actual pagination.  The response includes them on lines 199-200 (`"page": page, "pageSize": page_size`) suggesting pagination is planned but not implemented.  This is misleading for API consumers.
- **Impact**: Low -- confusing API contract.
- **Recommendation**: Either implement pagination or remove the parameters.

---

## P2 -- Medium (should address, code quality or consistency issue)

### P2-01: Inconsistent response shapes across similar endpoints

- **Description**: The API uses multiple inconsistent patterns for paginated responses:
  - `savings.py` (line 73): returns `{"items", "total", "page", "page_size", "pages"}`
  - `community.py` (line 139): returns `{"posts", "total", "page", "per_page", "pages"}`
  - `alerts.py` (line 123): returns `{"alerts", "total"}` (no pagination)
  - `connections/rates.py` (line 110): returns `{"rates", "total", "page", "page_size", "pages"}`
  - `suppliers.py` (line 122): returns `{"suppliers", "total", "page", "page_size", "region", "utility_type"}`
  - `notifications.py`: uses `{"notifications", "total", ...}`
- **Impact**: Inconsistent API contracts require frontend code to handle each endpoint differently.
- **Recommendation**: Standardize on a single pagination envelope shape (e.g., `{items, total, page, page_size, pages}`) across all list endpoints.

### P2-02: Public utility rate endpoints have no per-endpoint rate limiting

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/gas_rates.py` (all endpoints)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/heating_oil.py` (all endpoints)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/propane.py` (all endpoints)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/water.py` (all endpoints)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/community_solar.py` (all endpoints)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/cca.py` (all endpoints)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/public_rates.py` (all endpoints)
- **Description**: All public utility rate endpoints rely solely on the global rate limiter middleware.  There is no per-endpoint rate limiting like `auth.py` applies to the password-check endpoint (5 req/min).  These endpoints hit the database on every request.
- **Impact**: An attacker can make rapid requests to these public endpoints, increasing database load.  The global rate limiter (120 req/min per IP) provides some protection but is shared across all endpoints.
- **Recommendation**: Consider adding per-endpoint rate limiting on the most expensive public endpoints, or adding Redis caching to reduce database load.

### P2-03: `public_rates.py` path parameters have no validation

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/public_rates.py`
- **Lines**: 65-68
- **Description**: `GET /public/rates/{state}/{utility_type}` accepts `state` and `utility_type` as raw `str` path parameters with no pattern validation.  The `utility_type` is manually checked against a hardcoded list on lines 79-86, but `state` is only uppercased on line 77 with no format validation.  A request to `/public/rates/INVALID_STATE_CODE_THAT_IS_VERY_LONG/electricity` would hit the database.
- **Recommendation**: Add `Path(pattern=r"^[A-Z]{2}$")` for `state` and an enum or regex for `utility_type`.

### P2-04: `utility_accounts.py` list endpoint has no pagination parameters exposed

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/utility_accounts.py`
- **Lines**: 28-40
- **Description**: `GET /utility-accounts/` hardcodes `page=1, page_size=100` in the repository call (line 39).  For users with many utility accounts, all records are returned in a single response with no way to paginate.
- **Impact**: Potential large response payloads.
- **Recommendation**: Expose `page` and `page_size` as query parameters with defaults.

### P2-05: `utility_accounts.py` account creation stores account number as raw bytes, not encrypted

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/utility_accounts.py`
- **Lines**: 61
- **Description**: Line 61 stores the account number as `body.account_number.encode()` with the comment `# account_number encryption would happen here in a real flow`.  The `connections/crud.py` properly uses `encrypt_field()` for account numbers.
- **Impact**: Account numbers stored as plaintext bytes in the database -- PII exposure risk.
- **Recommendation**: Use `encrypt_field()` from `utils.encryption` as done in `connections/crud.py`.

### P2-06: Duplicate user profile endpoints across `user.py` and `users.py`

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/user.py` (GET/POST /preferences, POST /geocode)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/users.py` (GET/PUT /users/profile)
- **Description**: Two separate routers manage user data with different database access patterns (`users.py` uses raw SQL via `text()`, `user.py` uses `UserRepository`).  They use different database session dependencies (`users.py` uses `get_db_session`, `user.py` uses `get_timescale_session`).  This duplication creates confusion about which endpoint manages which data.
- **Impact**: Maintenance burden, potential data consistency issues.
- **Recommendation**: Consolidate into a single user router or clearly document the separation of concerns.

### P2-07: `export.py` uses deprecated `regex` parameter in `Query`

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/export.py`
- **Line**: 26
- **Description**: `format: str = Query("json", regex="^(json|csv)$", ...)` uses the deprecated `regex` parameter.  In Pydantic v2 / FastAPI 0.100+, this should be `pattern` instead.
- **Impact**: Deprecation warning, may break in future FastAPI versions.
- **Recommendation**: Change `regex=` to `pattern=`.

### P2-08: `utility_discovery.py` and `reports.py` endpoints have no authentication

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/utility_discovery.py`
- **Lines**: 15, 31 (discover_utilities, get_completion)
- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/reports.py`
- **Description**: `discover_utilities` and `get_completion` have no auth dependency.  While the discovery data is non-sensitive, `get_completion` exposes which utility types a user tracks (via the `tracked` query param) and could be considered profile-adjacent data.  Note: `reports.py` IS properly gated with `require_tier("business")`.
- **Impact**: Low -- discovery data is non-sensitive, but completion status may reveal user behavior.
- **Recommendation**: Review whether completion endpoint should require authentication.

### P2-09: `neighborhood.py` validates `utility_type` but not `region`

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/neighborhood.py`
- **Lines**: 28-42
- **Description**: The `neighborhood_compare` endpoint validates `utility_type` against the `UtilityType` enum (line 35) but passes `region` directly to the service without any validation.
- **Recommendation**: Add region validation (regex or enum check).

### P2-10: `create_post` in community.py does not validate `region` format

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/community.py`
- **Lines**: 79-113
- **Description**: While `utility_type` and `post_type` are validated (lines 86-95), the `region` field on `CreatePostRequest` (line 53) is passed through without validation.
- **Recommendation**: Add a `@field_validator("region")` matching the pattern used in `alerts.py`.

### P2-11: Inconsistent use of response models

- **Description**: Many endpoints define `response_model` (e.g., `suppliers.py`, `connections/crud.py`, `notifications.py`), while others return raw dicts (e.g., `community.py`, `alerts.py`, `agent.py`, `gas_rates.py`).  Endpoints without `response_model` lack automatic response validation and may expose internal fields.
- **Impact**: Inconsistent API documentation and potential data leakage through unfiltered response fields.
- **Recommendation**: Add `response_model` to all endpoints that return structured data.

---

## P3 -- Low (nice-to-have, minor improvements)

### P3-01: `compare_suppliers` returns hardcoded tariff data

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/suppliers.py`
- **Lines**: 388-390
- **Description**: The comparison endpoint returns hardcoded placeholder values: `"cheapest_tariff": "Standard Variable"`, `"unit_rate": "0.25"`, `"standing_charge": "0.40"`.  These do not reflect actual tariff data.
- **Impact**: API returns misleading data for supplier comparisons.
- **Recommendation**: Fetch actual tariff data from the `tariffs` table.

### P3-02: `get_suppliers_by_region` sets `page_size=total or 20` in response

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/suppliers.py`
- **Line**: 349
- **Description**: `page_size=total or 20` is a misleading value -- it sets page_size to the total result count rather than an actual page size value.  This doesn't match the semantics of pagination.
- **Recommendation**: Use a consistent page_size value or add actual pagination parameters to this endpoint.

### P3-03: `_app_rate_limiter` exported from main.py for test compatibility

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/main.py`
- **Lines**: 6-8, 14
- **Description**: The docstring explains this is for backward compatibility with test imports.  This couples the test suite to internal implementation details.
- **Recommendation**: Consider refactoring tests to not depend on this import.

### P3-04: `db is None` guards appear in some endpoints but not others

- **Description**: Some endpoints check `if db is None` and return 503 (e.g., `affiliate.py` line 41, `agent.py` line 117, `alerts.py` line 116), while most others rely on the dependency injection system to ensure `db` is never None.
- **Impact**: Inconsistent error handling patterns.
- **Recommendation**: Standardize on either always checking or never checking (the DI system should guarantee a valid session).

### P3-05: `PortalConnectionResponse` returns plaintext `portal_username`

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/portal_scrape.py`
- **Line**: 143
- **Description**: The create-portal-connection response includes `portal_username=payload.portal_username` in plaintext, even though the username is encrypted before storage.  While usernames are less sensitive than passwords, returning them in the response is inconsistent with the security posture of encrypting them.
- **Recommendation**: Return a masked version of the username (e.g., `d***@example.com`).

### P3-06: Multiple `from __future__ import annotations` usage inconsistency

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/portal_scrape.py`
- **Line**: 24
- **Description**: Only `portal_scrape.py` uses `from __future__ import annotations`.  All other files use the `X | Y` union syntax directly (Python 3.12+).
- **Recommendation**: Remove for consistency since the project targets Python 3.12+.

### P3-07: SSE connection counter race condition (minor)

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/prices_sse.py`
- **Lines**: 201-210
- **Description**: The SSE endpoint increments the connection counter, then checks if it exceeds the limit.  Between the `incr` and the `> limit` check, another request could also increment.  With Redis INCR this is atomic, but the decrement-on-rejection pattern means the counter is briefly inflated.  This is mitigated by the Redis TTL (1 hour) and the small window.
- **Impact**: Negligible -- could briefly allow `MAX + 1` connections in a race, but the TTL prevents counter drift.

### P3-08: `beta_signup` stores beta code inside a serialized string field

- **File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/beta.py`
- **Lines**: 149
- **Description**: The beta code is stored as part of a semicolon-delimited string in the `interest` field: `f"supplier={signup.currentSupplier};bill=...;code={beta_code}"`.  This requires LIKE queries and manual parsing to verify codes, which is the root cause of P1-01.
- **Recommendation**: Store the beta code in a dedicated indexed column.

---

## Files With No Issues Found

The following files were reviewed and found to have no significant issues:

| File | Notes |
|------|-------|
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/auth.py` | Well-structured. Per-endpoint rate limiter on password-check. Proper auth guards. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/billing.py` | Stripe webhook signature verification, idempotency guard, redirect URL domain validation. Solid implementation. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/compliance.py` | GDPR endpoints properly authenticated. Dual-delete endpoint design is intentional. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/forecast.py` | Pro tier gated. Multi-utility forecasting with proper validation. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/health.py` | Public basic health, protected integration deep-check via `verify_api_key`. Appropriate access control. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/notifications.py` | Uses `uuid.UUID` for `notification_id`. Proper auth and ownership checks. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/rate_changes.py` | Proper auth split (public list, authenticated preferences). |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/recommendations.py` | Pro tier gated. Proper validation. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/referrals.py` | All endpoints authenticated. Input validation on referral code (max_length=12). |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/regulations.py` | `state_code` has `pattern=r"^[A-Z]{2}$"` validation. Good example of path param validation. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/feedback.py` | Authenticated. Pydantic validation with min/max length. Proper 201 status code. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/savings.py` | Proper tier gating (pro for summary/history, auth-only for combined). |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/user_supplier.py` | Uses `uuid.UUID` for `supplier_id` in unlink. Encrypted account numbers. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/webhooks.py` | HMAC-SHA256 signature verification for GitHub webhooks. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/analytics.py` | All endpoints behind `require_paid_tier`. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/router.py` | Well-documented route registration order to prevent wildcard capture. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/__init__.py` | Shared `verify_api_key` dependency applied to all internal sub-routers. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/alerts.py` | Properly protected by API key. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/data_pipeline.py` | Properly protected by API key. Parallelized weather fetch with semaphore. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/billing.py` | Properly protected by API key. Dunning cycle implementation. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/email_scan.py` | Properly protected by API key. Batch scan with error handling. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/portal_scan.py` | Properly protected by API key. Semaphore-limited concurrency. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/ml.py` | Properly protected by API key. Observation pipeline. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/operations.py` | Health-data validates against hardcoded allowlist despite f-string SQL. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/sync.py` | Properly protected by API key. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/data_quality.py` | Properly protected by API key. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/dependencies.py` | HMAC constant-time API key comparison. Tier cache with 30s TTL. Solid auth implementation. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/__init__.py` | Simple re-exports. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/__init__.py` | Package-level re-exports for test patching. |
| `/Users/devinmcgrath/projects/electricity-optimizer/backend/routers/__init__.py` | Empty init. |

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| **P0 -- Critical** | 7 | UUID validation gaps on path parameters (6 instances), OAuth state replay, raw dict request body |
| **P1 -- High** | 8 | SQL LIKE wildcard injection, missing field validation on updates, mock data masking errors, unauthenticated endpoints without rate limiting, error message information disclosure |
| **P2 -- Medium** | 11 | Inconsistent response shapes, missing per-endpoint rate limiting on public endpoints, plaintext account number storage, deprecated API parameters, missing region validation |
| **P3 -- Low** | 8 | Hardcoded placeholder data, minor inconsistencies, serialized field design issues |

### Overall Assessment

The API layer demonstrates strong security fundamentals:

- **Authentication**: Consistent use of `get_current_user`, `require_tier()`, and `verify_api_key` dependencies.  Tier gating is properly applied to premium features.
- **SQL injection protection**: All database queries use parameterized `text()` bindings -- no raw string interpolation of user input into SQL (the `operations.py` f-string validates against a hardcoded allowlist).
- **IDOR prevention**: Connection, notification, and utility account endpoints consistently verify ownership via `WHERE user_id = :uid` clauses.
- **Encryption**: Portal credentials, OAuth tokens, and account numbers are properly encrypted with AES-256-GCM.
- **Internal endpoints**: All `/internal/*` routes are protected by API key with HMAC constant-time comparison.
- **Webhook security**: Stripe and GitHub webhooks verify signatures before processing.

The most actionable improvements are:

1. **Enforce UUID typing on all path parameters** (P0-02 through P0-06) -- this is a systematic gap affecting the entire connections package, community endpoints, agent, CCA, and community solar.  The fix is mechanical: change `param: str` to `param: uuid.UUID` in FastAPI path parameter declarations.
2. **Enforce OAuth state expiry** (P0-01) -- add a 3-line timestamp check in `verify_callback_state()`.
3. **Replace raw dict with Pydantic model** (P0-07) on the `POST /direct/authorize` endpoint.
4. **Escape SQL LIKE wildcards** (P1-01) in the beta verify-code endpoint.

### Files Reviewed

- `backend/main.py`
- `backend/api/dependencies.py`
- `backend/api/v1/__init__.py`
- `backend/api/v1/affiliate.py`
- `backend/api/v1/agent.py`
- `backend/api/v1/alerts.py`
- `backend/api/v1/auth.py`
- `backend/api/v1/beta.py`
- `backend/api/v1/billing.py`
- `backend/api/v1/cca.py`
- `backend/api/v1/community.py`
- `backend/api/v1/community_solar.py`
- `backend/api/v1/compliance.py`
- `backend/api/v1/export.py`
- `backend/api/v1/feedback.py`
- `backend/api/v1/forecast.py`
- `backend/api/v1/gas_rates.py`
- `backend/api/v1/health.py`
- `backend/api/v1/heating_oil.py`
- `backend/api/v1/neighborhood.py`
- `backend/api/v1/notifications.py`
- `backend/api/v1/prices.py`
- `backend/api/v1/prices_analytics.py`
- `backend/api/v1/prices_sse.py`
- `backend/api/v1/propane.py`
- `backend/api/v1/public_rates.py`
- `backend/api/v1/rate_changes.py`
- `backend/api/v1/recommendations.py`
- `backend/api/v1/referrals.py`
- `backend/api/v1/regulations.py`
- `backend/api/v1/reports.py`
- `backend/api/v1/savings.py`
- `backend/api/v1/suppliers.py`
- `backend/api/v1/user.py`
- `backend/api/v1/user_supplier.py`
- `backend/api/v1/users.py`
- `backend/api/v1/utility_accounts.py`
- `backend/api/v1/utility_discovery.py`
- `backend/api/v1/water.py`
- `backend/api/v1/connections/__init__.py`
- `backend/api/v1/connections/analytics.py`
- `backend/api/v1/connections/bill_upload.py`
- `backend/api/v1/connections/common.py`
- `backend/api/v1/connections/crud.py`
- `backend/api/v1/connections/direct_sync.py`
- `backend/api/v1/connections/email_oauth.py`
- `backend/api/v1/connections/portal_scrape.py`
- `backend/api/v1/connections/rates.py`
- `backend/api/v1/connections/router.py`
- `backend/api/v1/internal/__init__.py`
- `backend/api/v1/internal/alerts.py`
- `backend/api/v1/internal/billing.py`
- `backend/api/v1/internal/data_pipeline.py`
- `backend/api/v1/internal/data_quality.py`
- `backend/api/v1/internal/email_scan.py`
- `backend/api/v1/internal/ml.py`
- `backend/api/v1/internal/operations.py`
- `backend/api/v1/internal/portal_scan.py`
- `backend/api/v1/internal/sync.py`
- `backend/routers/__init__.py`
- `backend/routers/predictions.py`

**Total files reviewed**: 61
**Total findings**: 34 (7 P0, 8 P1, 11 P2, 8 P3)
