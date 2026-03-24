# Audit Report 06: API Routes Layer

**Scope**: `backend/api/v1/` -- All FastAPI route handlers, request validation, authorization guards, error handling, and API contract correctness.

**Auditor**: Claude Opus 4.6 (automated security audit)
**Date**: 2026-03-23
**Files reviewed**: 40+ files across `backend/api/v1/`, `backend/api/v1/connections/`, `backend/api/v1/internal/`

---

## Methodology

Every `.py` file under `backend/api/v1/` was read in full. Each endpoint was evaluated against the following checklist:

1. **Authentication / Authorization** -- Is auth required? Is tier gating correct? Are ownership checks present?
2. **Input Validation** -- Are Pydantic models used? Are path params typed? Are query params bounded?
3. **IDOR (Insecure Direct Object Reference)** -- Can user A access user B's resources?
4. **Error Handling** -- Are exceptions caught? Are internal details leaked?
5. **Rate Limiting** -- Are abuse-prone endpoints rate-limited?
6. **Information Disclosure** -- Are secrets, PII, or internal state exposed in responses?
7. **Injection Risks** -- Is SQL parameterized? Are f-strings used in queries?
8. **API Contract** -- Do response models match expectations? Are status codes correct?

---

## P0 -- Critical (must fix before next deployment)

### P0-01: Account number stored as plaintext bytes instead of AES-256-GCM encryption

**File**: `backend/api/v1/utility_accounts.py:61`

```python
account_number_encrypted=body.account_number.encode() if body.account_number else None,
```

The `create_utility_account` endpoint stores account numbers using Python's `.encode()` (UTF-8 bytes), NOT the project-standard `encrypt_field()` (AES-256-GCM). This means account numbers are stored as readable plaintext bytes in the `utility_accounts` table. Every other endpoint in the codebase that handles account numbers (e.g., `connections/crud.py:129`, `user_supplier.py`) correctly uses `encrypt_field()`.

The inline comment on line 60 reads `# account_number encryption would happen here in a real flow`, which suggests this was left as a TODO that was never completed.

**Impact**: PII data exposure. If the database is breached, all utility account numbers are readable in cleartext. This violates the project's encryption-at-rest standard and likely violates GDPR Article 32 (appropriate technical measures).

**Recommendation**: Replace `.encode()` with `encrypt_field()` from `utils.encryption`:
```python
from utils.encryption import encrypt_field
account_number_encrypted=encrypt_field(body.account_number) if body.account_number else None,
```

---

### P0-02: IDOR in connection PATCH -- UPDATE query missing user_id in WHERE clause

**File**: `backend/api/v1/connections/crud.py:294-296`

```python
await db.execute(
    text(f"UPDATE user_connections SET {', '.join(updates)} WHERE id = :cid"),
    params,
)
```

The `update_connection` endpoint correctly verifies ownership at lines 277-282 (SELECT with `user_id = :uid`). However, the subsequent UPDATE at line 295 only uses `WHERE id = :cid` without including `AND user_id = :uid`. This creates a TOCTOU (time-of-check-time-of-use) race condition: between the SELECT ownership check and the UPDATE, the connection could theoretically be reassigned or a concurrent request could exploit the gap.

While the practical exploitability is limited (the ownership check happens milliseconds before the UPDATE in the same request), this violates defense-in-depth principles. Every other DELETE and UPDATE in the connections module includes `user_id` in the WHERE clause (e.g., `crud.py:248-249` for DELETE).

**Impact**: Theoretical IDOR allowing modification of another user's connection if exploited via race condition. Inconsistent with the security pattern used by every other mutation in this module.

**Recommendation**: Add `AND user_id = :uid` to the UPDATE WHERE clause and include `current_user.user_id` in `params`:
```python
params["uid"] = current_user.user_id
await db.execute(
    text(f"UPDATE user_connections SET {', '.join(updates)} WHERE id = :cid AND user_id = :uid"),
    params,
)
```

---

### P0-03: OAuth callback state parameter has no timestamp expiry enforcement

**File**: `backend/api/v1/connections/common.py:75-100`

```python
def verify_callback_state(state: str) -> tuple:
    parts = state.split(":")
    if len(parts) != 4:
        raise HTTPException(...)
    connection_id, user_id, timestamp, received_sig = parts
    key = _get_hmac_key()
    payload = f"{connection_id}:{user_id}:{timestamp}"
    expected_sig = hmac.HMAC(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_sig, expected_sig):
        raise HTTPException(...)
    return connection_id, user_id
```

The `verify_callback_state()` function extracts the `timestamp` from the signed state but never checks whether it has expired. The constant `OAUTH_STATE_TIMEOUT_SECONDS = 600` is defined on line 42 but is never referenced in `verify_callback_state()`.

This means a captured OAuth callback URL remains valid indefinitely as long as the HMAC key (INTERNAL_API_KEY) does not change. An attacker who intercepts or leaks a callback URL can replay it at any future time.

The email OAuth module (`email_oauth_service.py`) has its own `verify_oauth_state()` that DOES enforce timestamp expiry, creating an inconsistency.

**Impact**: Signed callback state tokens for UtilityAPI direct connections never expire, enabling replay attacks. The email OAuth flow is not affected (uses separate verification with expiry).

**Recommendation**: Add timestamp expiry check after HMAC verification:
```python
try:
    ts = int(timestamp)
except ValueError:
    raise HTTPException(status_code=400, detail="Invalid callback state: malformed timestamp.")

if time.time() - ts > OAUTH_STATE_TIMEOUT_SECONDS:
    raise HTTPException(status_code=400, detail="Callback state has expired.")
```

---

## P1 -- High (should fix in current sprint)

### P1-01: UtilityAPI authorization endpoint accepts raw dict instead of Pydantic model

**File**: `backend/api/v1/connections/direct_sync.py:45-46`

```python
async def initiate_utilityapi_authorization(
    payload: dict,
```

Every other POST endpoint in the codebase uses a typed Pydantic model for request validation (e.g., `CreateDirectConnectionRequest`, `CreatePortalConnectionRequest`, `CreateEmailConnectionRequest`). This endpoint accepts a raw `dict`, meaning:

- No type validation on `supplier_id` (could be any type, not checked as UUID)
- No validation on `consent_given` (retrieved via `.get()` with default `False`)
- No max_length constraints on any field
- No automatic 422 response from FastAPI for malformed input
- OpenAPI schema generation shows `{}` as the request body instead of a documented model

**Impact**: Bypasses FastAPI's built-in input validation. Malformed requests that should return 422 may instead cause 500 errors or unexpected behavior deeper in the handler logic.

**Recommendation**: Define and use a proper Pydantic model:
```python
class InitiateUtilityAPIRequest(BaseModel):
    supplier_id: uuid.UUID
    consent_given: bool = False
```

---

### P1-02: Portal connection response returns plaintext username

**File**: `backend/api/v1/connections/portal_scrape.py:141-148`

```python
return PortalConnectionResponse(
    connection_id=connection_id,
    supplier_id=str(payload.supplier_id),
    portal_username=payload.portal_username,  # <-- plaintext
    portal_login_url=payload.portal_login_url,
    portal_scrape_status="pending",
    portal_last_scraped_at=None,
)
```

The `create_portal_connection` endpoint correctly encrypts both the username and password before storing them in the database (lines 92-95). However, it then returns the plaintext `portal_username` in the response body. The username is a credential -- knowing it gives attackers half of a credential pair.

**Impact**: Credential exposure in API responses. If response logging is enabled, proxy/CDN caching captures responses, or the frontend stores the response, the plaintext username is persisted outside the encrypted database column.

**Recommendation**: Return a masked version of the username (e.g., first 2 chars + asterisks):
```python
masked_username = payload.portal_username[:2] + "***" if len(payload.portal_username) > 2 else "***"
```

---

### P1-03: Analytics connection_id parameter is unvalidated string, not UUID

**File**: `backend/api/v1/connections/analytics.py:37-38`

```python
async def get_rate_comparison(
    connection_id: str | None = Query(None),
```

All four analytics endpoints accept `connection_id` as `str | None` rather than `uuid.UUID | None`. Every other connection endpoint in the module uses `uuid.UUID` path/query parameters, which gives free 422 validation from FastAPI when a non-UUID value is provided.

The same issue appears on lines 58 and 37 (both `get_rate_comparison` and `get_rate_history`).

**Impact**: Malformed connection_id values pass through to the service layer and database queries instead of being rejected at the API boundary. While SQL injection is not possible (parameterized queries are used), this can cause unexpected database errors or expose internal error details.

**Recommendation**: Change to `uuid.UUID | None`:
```python
connection_id: uuid.UUID | None = Query(None),
```

---

### P1-04: Community list_posts endpoint does not validate region against Region enum

**File**: `backend/api/v1/community.py:123-130`

```python
@router.get("/posts")
async def list_posts(
    region: str = Query(description="Region code"),
    utility_type: str = Query(description="Utility type"),
    ...
```

The `list_posts` (GET) endpoint requires `region` and `utility_type` as query parameters but performs no validation on either value. In contrast, `create_post` (POST, line 88-97) validates `post_type` and `utility_type` against defined allowlists -- but even there, `region` is passed through without validation.

The `community_stats` endpoint (line 233) similarly accepts `region` without validation.

**Impact**: Arbitrary strings passed as `region` are forwarded to the database query. While parameterized queries prevent SQL injection, this allows enumeration probing and may return empty results for regions that don't exist, leading to confusing UX. More importantly, it bypasses the project's standard Region enum validation.

**Recommendation**: Validate `region` against a regex or the Region enum at the API layer for both GET endpoints, matching what other modules do (e.g., `alerts.py` validates region format).

---

### P1-05: f-string SQL in data_health_check endpoint

**File**: `backend/api/v1/internal/operations.py:155-160`

```python
count_result = await db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
...
ts_result = await db.execute(text(f"SELECT MAX({ts_col}) FROM {table_name}"))
```

These lines use f-string interpolation to build SQL queries. The table names and column names DO come from a hardcoded list defined on lines 131-142, and the validation on lines 144-150 checks them against a `frozenset` derived from the same list. The validation uses `assert`, however, which is stripped when Python runs with `-O` (optimizations enabled).

The endpoint is protected by `verify_api_key` (internal only), which limits the attack surface. But the use of `assert` for security validation is a code smell -- assertions are development-time checks, not runtime security controls.

**Impact**: If Python is ever run with `-O` flag, the frozenset validation is silently bypassed, and any values in the `tables` list would be interpolated into SQL. Currently low risk because the list is fully hardcoded, but the pattern is fragile and should be refactored.

**Recommendation**: Replace `assert` with an explicit `if/raise` guard:
```python
if table_name not in _HEALTH_TABLES or ts_col not in _HEALTH_COLS:
    raise ValueError(f"Unexpected health check identifier: {table_name}.{ts_col}")
```

---

### P1-06: GeocodeRequest has no max_length constraint on address field

**File**: `backend/api/v1/user.py:24-27`

```python
class GeocodeRequest(BaseModel):
    """Geocode request body"""
    address: str
```

The `address` field has no `max_length` constraint. This field is passed directly to `GeocodingService().geocode()`, which forwards it to external APIs (OWM, Nominatim). An attacker could submit extremely long strings (megabytes) in the `address` field, causing:

1. Memory allocation issues
2. Excessive payload to external geocoding APIs
3. Potential for denial-of-service via oversized requests

Every other request model in the codebase uses `max_length` on string fields (e.g., `BetaSignupRequest.name` has `max_length=100`).

**Recommendation**: Add `max_length=500` (or similar reasonable limit):
```python
address: str = Field(..., min_length=1, max_length=500)
```

---

## P2 -- Medium (should fix in next sprint)

### P2-01: Public rates endpoint does not validate state parameter against allowlist

**File**: `backend/api/v1/public_rates.py:65-77`

```python
async def get_rate_summary(
    state: str,
    utility_type: str,
    ...
):
    state = state.upper()
```

The `state` path parameter is uppercased but not validated against any allowlist (no Region enum check, no regex). The `utility_type` is validated at line 79-86 (if/elif chain), but `state` can be any arbitrary string.

While the SQL queries use parameterized `:state` (safe from injection), this allows:
- Enumeration probing with arbitrary state codes
- Cache pollution if caching is added later (arbitrary cache keys)

**Recommendation**: Validate `state` against a regex pattern (2-letter alpha) or the Region enum.

---

### P2-02: Beta verify-code endpoint uses LIKE query pattern that may return false positives

**File**: `backend/api/v1/beta.py:215-220`

```python
result = await db.execute(
    text("SELECT interest FROM beta_signups WHERE interest LIKE :pattern ESCAPE '\\'"),
    {"pattern": f"%code={escaped_code}%"},
)
```

While the code correctly escapes SQL LIKE wildcards (`%`, `_`, `\`) on line 212 and uses constant-time comparison on line 236, the LIKE query itself could return multiple rows. If one user's beta code is a substring of another row's interest field, the LIKE pattern could match unintended rows. The constant-time comparison loop on lines 225-238 mitigates this by checking exact matches, but the database is doing unnecessary work.

**Impact**: Low. The constant-time comparison provides correct behavior. The LIKE query is just less efficient than an exact-match approach would be.

**Recommendation**: Store beta codes in a dedicated column rather than embedding them in a semicolon-delimited `interest` field.

---

### P2-03: Beta signup endpoint lacks rate limiting

**File**: `backend/api/v1/beta.py:107-112`

```python
@router.post("/signup", response_model=BetaSignupResponse)
async def beta_signup(
    signup: BetaSignupRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
):
```

The beta signup endpoint is public (no auth) and has no rate limiting dependency. While the duplicate email check on line 131 prevents re-registration, an attacker could spam different email addresses to:

1. Flood the `beta_signups` table
2. Trigger welcome email sending (via `send_welcome_email` background task)
3. Potentially abuse Resend email quota

Other public endpoints in the codebase apply rate limiting (e.g., auth endpoints use `_login_attempt_limiter`).

**Recommendation**: Add IP-based rate limiting (e.g., 5 signups per IP per hour).

---

### P2-04: Community create_post does not validate region format

**File**: `backend/api/v1/community.py:88-113`

```python
@router.post("/posts", status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: CreatePostRequest,
    ...
):
    if payload.post_type not in VALID_POST_TYPES:
        raise HTTPException(...)
    if payload.utility_type not in VALID_UTILITY_TYPES:
        raise HTTPException(...)

    service = CommunityService()
    post = await service.create_post(
        ...
        data={
            ...
            "region": payload.region,  # no validation
```

The `post_type` and `utility_type` fields are validated against allowlists (lines 88-97), but `region` is passed through to the service layer without any validation. The `CreatePostRequest` Pydantic model (line 55) only specifies `str` with a description.

**Recommendation**: Add a regex pattern or allowlist validation for region, consistent with how `alerts.py` and `users.py` handle region validation.

---

### P2-05: Utility accounts list endpoint has no pagination

**File**: `backend/api/v1/utility_accounts.py:28-40`

```python
@router.get("/", response_model=list[UtilityAccountResponse])
async def list_utility_accounts(
    utility_type: str | None = None,
    ...
):
    accounts = await repo.list(page=1, page_size=100, **filters)
```

The endpoint hardcodes `page=1, page_size=100` with no user-controllable pagination. While 100 utility accounts per user is unlikely, this pattern is inconsistent with other list endpoints (e.g., `connections/rates.py` provides full pagination with `page` and `page_size` query params).

**Recommendation**: Add standard `page` and `page_size` query parameters matching the project's convention.

---

### P2-06: Utility accounts list does not validate utility_type query parameter

**File**: `backend/api/v1/utility_accounts.py:30`

```python
utility_type: str | None = None,
```

The `utility_type` filter is passed directly to the repository without validation against the `UtilityType` enum (which is imported on line 14 but never used for validation).

**Recommendation**: Validate against `UtilityType` enum or restrict to known values.

---

### P2-07: Email OAuth callback does not validate the `code` query parameter length

**File**: `backend/api/v1/connections/email_oauth.py:117`

```python
code: str = Query(..., description="Authorization code from OAuth provider"),
```

The `code` parameter has no `max_length` constraint. OAuth authorization codes are typically short (<256 chars), but without a bound, an attacker could submit extremely long strings that are forwarded to the OAuth token exchange endpoint.

Similarly, the `state` parameter on line 118 has no `max_length`.

**Recommendation**: Add `max_length=2048` (generous but bounded) to both `code` and `state` parameters.

---

### P2-08: Public community stats endpoint has no rate limiting

**File**: `backend/api/v1/community.py:231-239`

```python
@router.get("/stats")
async def community_stats(
    region: str = Query(description="Region code"),
    db: AsyncSession = Depends(get_db_session),
):
```

Both `list_posts` (line 123) and `community_stats` (line 231) are public endpoints (no auth dependency) with no rate limiting. They execute database queries (aggregations for stats, paginated queries for posts). An attacker could send high-volume requests to these endpoints to stress the database.

**Recommendation**: Add IP-based rate limiting to public endpoints that query the database.

---

### P2-09: Reparse endpoint does not verify the stored file still exists on disk

**File**: `backend/api/v1/connections/bill_upload.py:399-475`

The `reparse_bill_upload` endpoint resets `parse_status` to `pending` and schedules a background parse using the `storage_key` from the database. It does not check whether the file still exists at the `storage_key` path. If the file was deleted by the maintenance cleanup task (`cleanup_expired_uploads`), the background parse will fail silently.

**Impact**: Poor UX -- user triggers reparse, sees "pending", but the parse never completes because the file is gone. The error is only visible in server logs.

**Recommendation**: Check file existence before scheduling the reparse, or return a clear error if the file has been cleaned up.

---

## P3 -- Low (nice to have / informational)

### P3-01: Inconsistent error detail messages across connection endpoints

Multiple connection endpoints return slightly different error messages for the same condition:

- `crud.py:282`: `"Connection not found"` (no period)
- `crud.py:209`: `"Connection not found."` (with period)
- `bill_upload.py:190`: `"Connection not found."` (with period)
- `bill_upload.py:372`: `"Upload not found"` (no period)
- `direct_sync.py:329`: `"Connection not found."` (with period)
- `portal_scrape.py:87`: `"Supplier not found."` (with period)

**Recommendation**: Standardize error messages (with or without trailing period, consistently).

---

### P3-02: Beta signup stores structured data in a semicolon-delimited string

**File**: `backend/api/v1/beta.py:149`

```python
"interest": f"supplier={signup.currentSupplier};bill={signup.monthlyBill};source={signup.hearAbout};postcode={signup.postcode};code={beta_code}",
```

All beta signup metadata (supplier, bill amount, source, postcode, and generated code) is concatenated into a single semicolon-delimited string stored in the `interest` TEXT column. This makes querying individual fields difficult and fragile. The `verify-code` endpoint (line 215) has to use `LIKE` queries and string splitting to extract the code.

**Recommendation**: For future tables, use separate columns or a JSONB column for structured metadata.

---

### P3-03: Direct sync callback constructs redirect URL from settings.frontend_url

**File**: `backend/api/v1/connections/direct_sync.py:117`

```python
callback_url = f"{_settings.frontend_url}/api/v1/connections/direct/callback"
```

The UtilityAPI callback URL is constructed by concatenating `settings.frontend_url` with a path. Unlike the email OAuth callback (which validates `frontend_url` against `_ALLOWED_FRONTENDS`), this URL is not validated. If `frontend_url` is misconfigured, the callback could be sent to an unexpected domain.

**Impact**: Low. The `frontend_url` comes from server-side configuration, not user input. But the inconsistency with email OAuth's validation pattern is worth noting.

**Recommendation**: Apply the same `_ALLOWED_FRONTENDS` validation pattern used in `email_oauth.py:214-222`.

---

### P3-04: Health check endpoints expose database table names and row counts

**File**: `backend/api/v1/internal/operations.py:118-184`

The `data_health_check` endpoint returns exact row counts and last-write timestamps for 10 database tables. While protected by `verify_api_key`, this information could be useful for reconnaissance if the API key is compromised.

**Impact**: Information disclosure (table names, data volumes, write patterns). Mitigated by API key protection.

**Recommendation**: Acceptable for an internal endpoint. Ensure API key rotation procedures are documented.

---

### P3-05: List endpoints return `total` alongside full result sets

Multiple list endpoints (e.g., `crud.py:66-67`, `bill_upload.py:337`) compute `total=len(connections)` after fetching all rows. This is fine for small datasets but could become a performance concern if users accumulate many connections/uploads.

**Recommendation**: For endpoints that may grow large, consider separate COUNT queries with LIMIT/OFFSET pagination (already done correctly in `connections/rates.py`).

---

### P3-06: Community GET /posts requires both region and utility_type but has no defaults

**File**: `backend/api/v1/community.py:125-126`

```python
region: str = Query(description="Region code"),
utility_type: str = Query(description="Utility type"),
```

Both parameters are required (no default value) but have no validation. A user who omits either gets a FastAPI 422 error. This is correct behavior, but the 422 error message from FastAPI may not match the project's error format.

**Impact**: Minimal. Standard FastAPI behavior.

---

### P3-07: Utility accounts GET /types endpoint is unauthenticated

**File**: `backend/api/v1/utility_accounts.py:74-77`

```python
@router.get("/types")
async def list_utility_types():
```

This endpoint returns the list of supported utility types without requiring authentication. While the data is non-sensitive (it's just enum values), every other endpoint on the utility accounts router requires auth.

**Impact**: Minimal. The data is effectively public (it's an enum).

---

### P3-08: Bill upload background parse silently swallows all exceptions

**File**: `backend/api/v1/connections/bill_upload.py:86-91`

```python
except Exception as exc:
    logger.error(
        "background_parse_error",
        upload_id=upload_id,
        error=str(exc),
    )
```

The `_run_background_parse` function catches all exceptions and only logs them. The upload record stays in `pending` state indefinitely. While logging is present, there is no mechanism to update the record's `parse_status` to `error` when the background task fails.

**Recommendation**: Add error-status update in the except block:
```python
await db.execute(
    text("UPDATE bill_uploads SET parse_status = 'error', parse_error = :err WHERE id = :uid"),
    {"err": str(exc)[:500], "uid": upload_id},
)
await db.commit()
```

---

### P3-09: Portal scrape rate insertion loop lacks batch insert optimization

**File**: `backend/api/v1/connections/portal_scrape.py:242-270`

```python
for rate_entry in scrape_result["rates"]:
    rate_id = str(uuid4())
    await db.execute(
        text("""INSERT INTO connection_extracted_rates ..."""),
        {...},
    )
```

Extracted rates are inserted one at a time in a loop, with no batch INSERT or `executemany`. The commit happens outside the loop (line 286), so transactional correctness is maintained, but individual INSERT round-trips to the database are inefficient for large rate sets.

**Recommendation**: Use a batch INSERT pattern (e.g., `VALUES ... , ... , ...` with multiple value tuples) for better performance when scrapes return many rates.

---

## Files With No Issues Found

The following files were reviewed and no security issues were identified:

| File | Notes |
|------|-------|
| `backend/api/v1/__init__.py` | Router exports only, no logic |
| `backend/api/v1/connections/router.py` | Route registration order with correct precedence |
| `backend/api/v1/connections/rates.py` | Proper ownership via JOINs, correct pagination, UUID params |
| `backend/api/v1/auth.py` | Proper rate limiting, brute-force protection, no credential exposure |
| `backend/api/v1/billing.py` | Stripe webhook signature verification, redirect domain validation, idempotency guard |
| `backend/api/v1/agent.py` | Context keys overwritten from auth session, tier-based rate limits, prompt length bounded |
| `backend/api/v1/webhooks.py` | HMAC-SHA256 verification with constant-time comparison |
| `backend/api/v1/savings.py` | Proper tier gating, delegation to service layer |
| `backend/api/v1/forecast.py` | Pro tier gate, utility_type validated against FORECASTABLE_UTILITIES |
| `backend/api/v1/notifications.py` | User scoping via service layer, proper Pydantic models |
| `backend/api/v1/user_supplier.py` | AES-256-GCM encryption, masked account numbers, ownership checks |
| `backend/api/v1/recommendations.py` | Pro tier gate, graceful exception handling |
| `backend/api/v1/export.py` | Business tier gate, Content-Disposition header |
| `backend/api/v1/neighborhood.py` | Auth required, UtilityType enum validation |
| `backend/api/v1/feedback.py` | Auth required, Literal type validation, message length bounded |
| `backend/api/v1/compliance.py` | GDPR compliant: consent logging, IP/UA audit trail, explicit confirmation required |
| `backend/api/v1/users.py` | VALID_REGIONS allowlist, UPDATABLE_COLUMNS frozenset defense |
| `backend/api/v1/suppliers.py` | UUID validation helper, regex region validation, parameterized queries |
| `backend/api/v1/prices.py` | PriceRegion enum validation, internal refresh behind API key |
| `backend/api/v1/alerts.py` | Ownership via service layer, region regex validation |
| `backend/api/v1/health.py` | Public health endpoints (appropriate), integrations behind API key |
| `backend/api/v1/internal/__init__.py` | Router-level verify_api_key dependency, constant-time comparison |
| `backend/api/v1/internal/alerts.py` | Error sanitization ("See server logs") |
| `backend/api/v1/internal/data_pipeline.py` | API key protected, parameterized queries |
| `backend/api/v1/internal/email_scan.py` | Semaphore concurrency control, sequential session usage |
| `backend/api/v1/internal/portal_scan.py` | Credential decryption scoped to function, Semaphore(2) |
| `backend/api/v1/internal/sync.py` | ON CONFLICT DO UPDATE, proper API key protection |
| `backend/api/v1/internal/data_quality.py` | Parameterized queries, API key protected |
| `backend/api/v1/connections/bill_upload.py` | Triple file validation (extension+MIME+magic), size limits |
| `backend/api/v1/connections/email_oauth.py` | HMAC state verification, ownership check, redirect allowlist |
| `backend/api/v1/referrals.py` | Auth required, error handling |

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| **P0 Critical** | 3 | Plaintext account encryption, IDOR in PATCH, OAuth state no expiry |
| **P1 High** | 6 | Raw dict payload, plaintext username in response, untyped connection_id, missing region validation, assert-based SQL guard, unbounded address field |
| **P2 Medium** | 9 | Missing rate limits on public endpoints, unvalidated params, no file existence check, missing pagination |
| **P3 Low** | 9 | Inconsistent error messages, data model patterns, performance suggestions |
| **Total** | **27** | |

### Cross-Cutting Observations

1. **Authentication coverage is strong**: Every endpoint that should require auth does require it. Internal endpoints consistently use `verify_api_key`. Tier gating via `require_paid_tier` and `require_tier()` is correctly applied.

2. **SQL injection risk is minimal**: All queries use parameterized `:param` binding. The only f-string SQL (`operations.py:155-160`) is guarded by a hardcoded allowlist (though the `assert` guard should be replaced).

3. **Ownership checks are generally thorough**: Most endpoints verify `user_id` in WHERE clauses. The PATCH endpoint in `crud.py` is the notable exception.

4. **Encryption is consistently applied -- except `utility_accounts.py`**: The `.encode()` on line 61 is the only place in the codebase where `encrypt_field()` should be used but is not.

5. **Input validation is generally good**: Pydantic models are used for most request bodies. The `direct_sync.py` raw dict and several missing `max_length` constraints are the exceptions.

6. **Error handling is appropriate**: Internal details are not leaked in error responses. Background tasks log errors but could do better at updating database status.
