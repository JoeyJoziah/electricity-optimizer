# API Route Handler Audit Report

**Date**: 2026-03-18
**Scope**: All backend API route handlers — `backend/api/v1/`, `backend/api/v1/connections/`, `backend/api/v1/internal/`, `backend/routers/`
**Files Reviewed**: 61 Python files across 4 directories (see complete file list at end of report)
**Audit Type**: READ-ONLY — no source files modified

***

## Executive Summary

The RateShift backend exposes approximately 180 route handlers across 61 files. The core architectural patterns are sound: session-based auth via `get_current_user` / `SessionData`, subscription gating via `require_tier()`, internal endpoint protection via `verify_api_key`, and structured error handling with structlog. The connections sub-package demonstrates excellent route registration discipline with a well-documented ordering strategy.

However, this audit identified **3 P0-Critical**, **14 P1-High**, **18 P2-Medium**, and **12 P3-Low** findings. The most severe issues involve a plaintext account number stored as bytes masquerading as encrypted data, a utility account credential storage bug, unauthenticated affiliate click attribution that accepts arbitrary `user_id` values from callers, and an OAuth callback state timer that is defined but never enforced.

**Route Handlers Audited**: ~180 | **Findings Identified**: 47 | **Critical/High Issues**: 17

---

## P0 — Critical (Fix Immediately)

### P0-01: Account Number "Encryption" Is Plaintext Bytes Encoding

**File**: `backend/api/v1/utility_accounts.py`, line 63

```python
account_number_encrypted=body.account_number.encode()
```

The field name `account_number_encrypted` implies AES-256-GCM encryption (as used everywhere else via `utils/encryption.py`). Instead, `.encode()` converts the string to UTF-8 bytes — completely reversible and providing zero confidentiality. Any attacker with database read access retrieves plaintext account numbers immediately.

The rest of the codebase uses `encrypt_field()` from `utils/encryption.py` (verified in `user_supplier.py` line 58 and `portal_scrape.py`). This is a one-off deviation from established pattern.

**Impact**: Breach of stored utility account numbers for all users who have linked utility accounts.

**Remediation**:
```python
from utils.encryption import encrypt_field
account_number_encrypted=encrypt_field(body.account_number)
```
Add a one-time migration to re-encrypt existing rows.

---

### P0-02: OAuth Callback State Has No Expiry Enforcement

**File**: `backend/api/v1/connections/common.py`, lines 40-90

`OAUTH_STATE_TIMEOUT_SECONDS = 600` is defined at line 42 but is **never checked** in `verify_callback_state()`. The function unpacks the HMAC-signed state and returns `(connection_id, user_id)` without validating the embedded timestamp against the timeout constant.

```python
# common.py — sign_callback_state embeds timestamp (line 58):
payload = f"{connection_id}:{user_id}:{int(time.time())}"

# verify_callback_state (lines 70-89) extracts parts but NEVER checks timestamp age:
connection_id, user_id, _ts = parts  # _ts is discarded
```

This allows replay of intercepted or leaked OAuth callback state values indefinitely. The `state` parameter in both `email_oauth_callback` (`email_oauth.py`) and `utilityapi_callback` (`direct_sync.py`) is verified for authenticity but not freshness.

**Impact**: An attacker who obtains a valid signed state token (e.g., via log exposure, redirect interception, or phishing) can replay it to activate a connection under a victim's account at any future time.

**Remediation**: In `verify_callback_state`, after extracting `ts`, add:
```python
if int(time.time()) - int(ts) > OAUTH_STATE_TIMEOUT_SECONDS:
    raise HTTPException(status_code=400, detail="OAuth state token has expired.")
```

---

### P0-03: `DELETE /gdpr/delete` Destroys All User Data Without Explicit Confirmation

**File**: `backend/api/v1/compliance.py`, lines 300-349

The `DELETE /gdpr/delete` endpoint ("no-body variant") accepts no request body and has no confirmation field. The docstring states: *"Confirmation is considered given by the act of calling this endpoint."* This is a single-request, irreversible deletion of all user data.

The primary endpoint `DELETE /gdpr/delete-my-data` (lines 231-293) correctly requires `confirmation: true` in the request body and rejects requests without it. The alias endpoint removes this guard entirely.

**Impact**: Any authenticated session (including XSS, CSRF, or compromised token) can permanently delete the user's account and all data with a single unauthenticated DELETE request. No 2FA, no confirmation token, no email confirmation step.

**Remediation**: Either (a) remove the `/gdpr/delete` alias entirely and document only `/gdpr/delete-my-data`, or (b) require the same `confirmation: true` body field. Consider adding a short-lived deletion token sent via email before executing the deletion.

---

## P1 — High (Fix This Sprint)

### P1-01: Unauthenticated Affiliate Click Attribution Accepts Arbitrary `user_id`

**File**: `backend/api/v1/affiliate.py`, lines 30-80 (approximate)

`POST /affiliate/click` requires no authentication (`current_user` dependency is absent). The `user_id` field in the request body is supplied entirely by the caller with no server-side binding to the authenticated session. Any client can submit arbitrary `user_id` values, attributing affiliate clicks to any user in the system.

**Impact**: Affiliate fraud — an attacker can inflate click counts for any user ID or fabricate conversion data for commission manipulation.

**Remediation**: Either make the endpoint unauthenticated and ignore `user_id` from the body (track by IP/session cookie), or add `current_user: SessionData = Depends(get_current_user)` and ignore the body's `user_id` entirely.

---

### P1-02: All `connection_id` Path Parameters Are Unvalidated Strings (Not UUID)

**Files**:
- `backend/api/v1/connections/crud.py` — all routes
- `backend/api/v1/connections/bill_upload.py` — all routes
- `backend/api/v1/connections/direct_sync.py` — `/{connection_id}/sync`, `/{connection_id}/sync-status`
- `backend/api/v1/connections/email_oauth.py` — `/email/{connection_id}/scan`
- `backend/api/v1/connections/portal_scrape.py` — `/portal/{connection_id}/scrape`
- `backend/api/v1/connections/rates.py` — all routes
- `backend/api/v1/connections/analytics.py` — all routes (use `connection_id` implicitly via analytics queries)

All `connection_id` path parameters are typed as `str`. The codebase pattern — established in `backend/api/v1/alerts.py` and confirmed in `backend/api/v1/user_supplier.py` — uses `uuid.UUID` type annotations for free 422 validation before any handler logic executes.

**Impact**: Malformed path values (e.g., `../../../../etc/passwd`, SQL fragments, or extremely long strings) reach handler code and are passed directly into parameterized SQL queries. While parameterized queries prevent SQL injection, the UUIDs are passed as raw strings to the database, which may cause unexpected behavior on invalid input.

**Remediation**: Change all `connection_id: str` parameters to `connection_id: uuid.UUID` and convert to string when passing to SQL: `str(connection_id)`.

Example fix pattern (from `alerts.py`):
```python
async def get_connection(connection_id: uuid.UUID, ...):
    result = await db.execute(text("SELECT ... WHERE id = :cid"), {"cid": str(connection_id)})
```

---

### P1-03: Internal Exception Messages Leaked in Production Error Responses

**Files and lines**:
- `backend/api/v1/compliance.py`: lines 104, 134, 164, 221, 393 — `detail=f"Failed to record consent: {str(e)}"`
- `backend/api/v1/billing.py`: line 376 — `detail=str(e)` in `ValueError` handler
- `backend/api/v1/internal/billing.py`: line 101 — `detail=f"Dunning cycle failed: {str(exc)}"`
- `backend/api/v1/internal/ml.py`: lines 109, 136 — `detail=f"Learning cycle failed: {str(e)}"` and `detail=str(e)`
- `backend/api/v1/internal/operations.py`: line 219 — `detail=f"KPI report failed: {str(exc)}"`
- `backend/routers/predictions.py`: line 456 — `detail=f"Failed to generate forecast: {str(e)}"`

Each of these passes raw `str(exception)` into the HTTP response body. Python exceptions routinely include file paths, SQL fragments, internal variable names, and library version strings. Internal endpoints (`/internal/*`) are behind API key auth, reducing exposure, but compliance.py, billing.py, and predictions.py are user-facing.

**Impact**: Information disclosure — stack traces and internal error messages visible to end users and API consumers can reveal architecture details useful for targeted attacks.

**Remediation**: Log the full exception with structlog, return a generic message:
```python
except Exception as e:
    logger.error("consent_record_failed", error=str(e), exc_info=True)
    raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
```
The `internal/alerts.py` file demonstrates the correct pattern: `"Alert check failed. See server logs for details."`.

---

### P1-04: `POST /direct/authorize` Accepts Unvalidated Raw `dict` Body

**File**: `backend/api/v1/connections/direct_sync.py`, lines 43-131

```python
async def initiate_utilityapi_authorization(
    payload: dict,  # No Pydantic model
    ...
):
    supplier_id = payload.get("supplier_id")
    consent_given = payload.get("consent_given", False)
```

The endpoint accepts an arbitrary `dict` with manual `.get()` extraction and manual validation. This bypasses Pydantic's type coercion, OpenAPI schema generation, and request validation. FastAPI will accept any JSON body — including arrays, null, or deeply nested objects — without error.

**Impact**: Missing schema documentation, no automatic 422 validation responses, potential for unexpected type handling (e.g., `supplier_id` could be a nested dict or list, which is then passed to a SQL query).

**Remediation**: Define a Pydantic model:
```python
class InitiateAuthorizationRequest(BaseModel):
    supplier_id: uuid.UUID
    consent_given: bool

async def initiate_utilityapi_authorization(
    payload: InitiateAuthorizationRequest,
    ...
):
```

---

### P1-05: Dynamic SQL f-String Construction in `health-data` Internal Endpoint

**File**: `backend/api/v1/internal/operations.py`, lines 153-167

```python
count_result = await db.execute(
    text(f"SELECT COUNT(*) FROM {table_name}")
)
# ...
ts_result = await db.execute(
    text(f"SELECT MAX({ts_col}) FROM {table_name}")
)
```

Table names and column names are interpolated directly into SQL strings via f-strings. The values originate from a hardcoded `tables` tuple defined 10 lines above, and an allowlist check exists via `assert`. However, the `assert` check is the guard:

```python
assert table_name in _HEALTH_TABLES and ts_col in _HEALTH_COLS, ...
```

`assert` statements are stripped when Python runs with optimization flags (`python -O` or `PYTHONOPTIMIZE=1`). If the deployment ever sets optimization flags, the allowlist check disappears entirely, and the f-string SQL construction becomes an injection point. Furthermore, the `_HEALTH_COLS` frozenset contains mixed column names (`timestamp`, `updated_at`, `fetched_at`, `created_at`) that are not validated per-table — a column valid for one table is accepted for any table in the allowlist check.

**Impact**: The `assert`-based allowlist is not a reliable security control. Under `-O` flag, this becomes a SQL injection vector.

**Remediation**: Replace `assert` with an explicit check and `raise HTTPException`:
```python
if table_name not in _HEALTH_TABLES or ts_col not in _HEALTH_COLS:
    raise HTTPException(status_code=500, detail="Internal configuration error")
```
Alternatively, use a hardcoded list of `text()` objects (one per table) instead of f-string construction.

---

### P1-06: `no response_model` on All Three Recommendation Endpoints

**File**: `backend/api/v1/recommendations.py`

None of the three endpoints (`GET /recommendations`, `GET /recommendations/appliance`, `GET /recommendations/schedule`) declare a `response_model`. All return raw `dict` objects. This means:
- No automatic response schema validation — the handler can accidentally return extra fields (e.g., internal state, credentials)
- No OpenAPI schema generation for API consumers
- No automatic 422 response documentation

**Impact**: Inadvertent data leakage via extra response fields; poor developer experience for API consumers.

**Remediation**: Define `RecommendationResponse`, `ApplianceRecommendationResponse`, and `ScheduleRecommendationResponse` Pydantic models and add `response_model=` to each route decorator.

---

### P1-07: `suppliers.py` Constructs SQL WHERE Clause via String Concatenation

**File**: `backend/api/v1/suppliers.py`, `get_supplier_tariffs` function, lines 270-279 (approximate)

```python
where_clauses = []
params = {"sid": str(supplier_id)}
if tariff_code:
    where_clauses.append("tariff_code = :tc")
    params["tc"] = tariff_code
where_sql = " AND ".join(where_clauses) or "1=1"
query = text(f"SELECT ... FROM supplier_tariffs WHERE supplier_id = :sid AND {where_sql}")
```

The `where_sql` variable is built from validated query parameters, so the values themselves are parameterized correctly. However, the clause structure (column names, operators) is assembled via string concatenation. If additional filter parameters are added in the future without careful review, a developer might accidentally include a user-supplied column name directly in `where_clauses`.

Additionally, `get_suppliers_by_region` contains `return page_size=total or 20` — the effective cap disappears when `total` is large, returning unbounded result sets.

**Impact**: Medium — current code is safe but the pattern is a maintainability hazard. Unbounded result set is a DoS vector.

**Remediation**: Use ORM-style query builders (SQLAlchemy `select().where()`) or a fixed parameterized query covering all filter combinations. For the region query, enforce `LIMIT :limit` in the SQL.

---

### P1-08: `public_rates.py` Accepts Any String for `state` and `utility_type` Path Params

**File**: `backend/api/v1/public_rates.py`

Path parameters `state` and `utility_type` are typed as bare `str` with no format validation (no regex, no enum, no min/max length). The `state.upper()` normalization is the only processing before the value is passed to database queries.

**Impact**: While parameterized SQL prevents injection, values like empty string, 200-character strings, or special characters reach service-layer code and produce unexpected errors. Missing format validation also prevents meaningful 422 responses.

**Remediation**:
```python
state: str = Path(..., pattern=r"^[A-Z]{2}$", description="Two-letter state code")
utility_type: str = Path(..., pattern=r"^[a-z_]{2,30}$")
```

---

### P1-09: `community.py` — `post_id` Path Parameters Are Unvalidated Strings

**File**: `backend/api/v1/community.py`

All community post operation routes (`GET /community/posts/{post_id}`, `POST /community/posts/{post_id}/vote`, `POST /community/posts/{post_id}/report`) accept `post_id: str` with no UUID validation.

Additionally, `POST /community/posts` performs manual enum validation for `post_type` using an `if` check against a hardcoded list rather than a Pydantic `Literal` or `Enum` type.

No endpoint in `community.py` declares a `response_model`.

**Impact**: Invalid IDs reach DB queries; missing response models allow data leakage.

**Remediation**: `post_id: uuid.UUID` on all routes. Define `PostTypeEnum(str, Enum)` and use it in the request model. Add `response_model=CommunityPostResponse` to each endpoint.

---

### P1-10: `beta.py` — `GET /beta/signups/stats` Accepts Pagination Params But Ignores Them

**File**: `backend/api/v1/beta.py`

```python
async def get_beta_stats(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ...
):
    # DB query uses no LIMIT/OFFSET — returns all rows regardless of params
    result = await db.execute(text("SELECT * FROM beta_signups ORDER BY created_at DESC"))
```

The function signature advertises pagination parameters, the caller sends them, but they are silently ignored. The endpoint returns all beta signups. For a large beta program, this is an unbounded result set.

**Impact**: API contract violation (callers expect pagination to work), potential DoS via large result set, information disclosure of all beta signup records.

**Remediation**: Apply the `page` and `page_size` parameters to the DB query with `LIMIT :limit OFFSET :offset`, and return a paginated response with `total` / `pages` fields.

---

### P1-11: `POST /beta/verify-code` Uses LIKE Pattern Match on Compound Interest Field

**File**: `backend/api/v1/beta.py`, line 229 (approximate)

```python
result = await db.execute(
    text("SELECT ... FROM beta_signups WHERE interest LIKE :pattern"),
    {"pattern": f"%code={code}%"}
)
```

The `interest` column stores a compound string (e.g., `"code=ABC123,source=email"`). The LIKE match uses a user-supplied `code` value embedded in the pattern. While the value is parameterized (preventing SQL injection), LIKE patterns with user input can produce false positives or false negatives. A `code` value of `"A"` matches any interest string containing `"code=A"` anywhere.

**Impact**: Code verification bypass — a short or partial code value matches records it should not.

**Remediation**: Store `invite_code` in a dedicated indexed column with an exact-match query: `WHERE invite_code = :code`.

---

### P1-12: `predictions.py` — `estimate_savings` Calls Route Handler as a Python Function

**File**: `backend/routers/predictions.py`, lines 601-611 (approximate)

```python
# Inside estimate_savings handler:
optimal_result = await find_optimal_times(
    region=region,
    hours=hours,
    current_user=current_user,
    db=db,
)
```

`find_optimal_times` is a FastAPI route handler function called directly as a coroutine, bypassing the FastAPI dependency injection lifecycle. If `find_optimal_times` is ever refactored to use additional `Depends()` parameters beyond what is passed here, those dependencies will silently receive `None` or cause a `TypeError`.

**Impact**: Brittle coupling between handlers; dependency injection contract broken; potential `None` dependency bugs if `find_optimal_times` signature changes.

**Remediation**: Extract the shared business logic into a service function (e.g., `OptimalTimesService.find_optimal_times()`), call the service from both handlers independently.

---

### P1-13: `gas_rates.py` — Dead Imports of Auth Dependencies

**File**: `backend/api/v1/gas_rates.py`, line 9

```python
from api.dependencies import get_current_user, SessionData
```

`get_current_user` and `SessionData` are imported but never used in the file. All endpoints in this file are unauthenticated. The dead imports suggest authentication was planned or previously wired and then removed, leaving endpoints publicly accessible.

**Impact**: If these endpoints are intended to be authenticated (the import suggests they were at some point), they are currently open to unauthenticated access.

**Remediation**: If endpoints are intentionally public, remove the unused imports. If they should require authentication, wire `current_user: SessionData = Depends(get_current_user)` into the handlers.

---

### P1-14: `module-level _model_cache` in `predictions.py` Is Not Multi-Worker Safe

**File**: `backend/routers/predictions.py`, module level

```python
_model_cache: dict[str, Any] = {}
```

This module-level dict is used to cache loaded ML models. In a Gunicorn/Uvicorn multi-worker deployment (Render uses multiple workers by default), each worker process has its own in-process `_model_cache`. Cache invalidation, eviction, and memory limits are not coordinated across workers. Under high load, all workers independently load the same models, multiplying memory usage.

**Impact**: Memory pressure in multi-worker deployments; inconsistent cache state across workers.

**Remediation**: Use Redis for shared model metadata caching (model version IDs), load models lazily per-worker, or use Render's single-worker setting for the predictions service if memory is constrained.

---

## P2 — Medium (Fix Next Sprint)

### P2-01: OAuth Callback Redirect Validation Uses Hardcoded `_ALLOWED_FRONTENDS` Set

**File**: `backend/api/v1/connections/email_oauth.py`, lines 195-201 (approximate)

```python
_ALLOWED_FRONTENDS = frozenset({
    "https://rateshift.app",
    "https://www.rateshift.app",
    "http://localhost:3000",
})
```

This hardcoded set does not include Vercel preview deployment URLs (e.g., `https://electricity-optimizer-git-feature-xyz.vercel.app`), staging environments, or any dynamically configured allowed origins. Preview deployments cannot complete the OAuth flow without a code change.

**Remediation**: Load allowed frontends from `settings.allowed_redirect_domains` (already defined in `config/settings.py`) so the list is configuration-driven, not hardcoded.

---

### P2-02: `health.py` — Public `/health` Exposes Environment and Version Metadata

**File**: `backend/api/v1/health.py`

`GET /health` is fully public and returns:
```json
{
  "environment": "production",
  "version": "1.0.0",
  "uptime_seconds": 3847,
  "database_status": "connected"
}
```

`environment` confirms the production/staging context; `version` pins the deployed software version (useful for targeting known CVEs in older versions). `/health/ready` similarly exposes `database_connected`, `redis_connected`, and Redis latency.

`GET /health/integrations` is correctly protected by `verify_api_key`.

**Remediation**: Remove `environment` and `version` from the public endpoint. Return only `{"status": "ok"}` at `/health`. Move detailed health data behind `/health/integrations` (API key protected).

---

### P2-03: `recommendations.py` Uses stdlib `logging` Instead of `structlog`

**File**: `backend/api/v1/recommendations.py`

```python
import logging
logger = logging.getLogger(__name__)
```

Every other backend module uses `structlog.get_logger(__name__)`. Using stdlib `logging` in `recommendations.py` means log events from this module skip structured JSON formatting, context binding (request IDs, user IDs), and integration with the OTel tracing pipeline.

**Remediation**: Replace `import logging` with `import structlog` and `logger = structlog.get_logger(__name__)`.

---

### P2-04: `connections/common.py` — `_UPLOADS_DIR` Is a Relative Path

**File**: `backend/api/v1/connections/common.py`, line ~20

```python
_UPLOADS_DIR = Path("uploads")
```

Relative paths resolve relative to the process working directory, which varies between local development, Docker containers, and Render's deployment environment. If the process is started from a different directory, uploaded files are written to an unexpected location or fail silently.

**Remediation**: Use an absolute path from settings:
```python
_UPLOADS_DIR = Path(settings.uploads_dir).resolve()
```
Or construct from `__file__`:
```python
_UPLOADS_DIR = Path(__file__).parent.parent.parent.parent / "uploads"
```

---

### P2-05: `cca.py` — `cca_id` Path Parameters Are Unvalidated Strings

**File**: `backend/api/v1/cca.py`

`GET /cca/{cca_id}` and related endpoints accept `cca_id: str`. No UUID validation is applied. `/cca/detect` accepts `zip_code` with no format validation (no 5-digit regex constraint).

**Remediation**: `cca_id: uuid.UUID` on all routes. Add `zip_code: str = Query(..., pattern=r"^\d{5}$")`.

---

### P2-06: `community_solar.py` — `program_id` Is Unvalidated String

**File**: `backend/api/v1/community_solar.py`

`GET /community-solar/{program_id}` accepts `program_id: str` with no UUID validation.

**Remediation**: `program_id: uuid.UUID`.

---

### P2-07: `rate_changes.py` — `channels` Field Has No Enum Validation

**File**: `backend/api/v1/rate_changes.py`, `UpsertPreferenceRequest` model

```python
class UpsertPreferenceRequest(BaseModel):
    channels: List[str]  # No validation — accepts any string
```

The system supports three channels: `email`, `push`, `in_app`. Arbitrary string values are accepted and persisted to the database. Invalid channel names would silently create preference records that the notification dispatcher never matches.

**Remediation**:
```python
class NotificationChannel(str, Enum):
    EMAIL = "email"
    PUSH = "push"
    IN_APP = "in_app"

class UpsertPreferenceRequest(BaseModel):
    channels: List[NotificationChannel]
```

---

### P2-08: `notifications.py` — GET Endpoints Missing `response_model`

**File**: `backend/api/v1/notifications.py`

`GET /notifications` and `GET /notifications/unread-count` do not declare `response_model`. Notification objects may contain internal fields (e.g., raw delivery metadata) that should not be exposed to users.

**Remediation**: Define `NotificationResponse` and `UnreadCountResponse` Pydantic models, add `response_model=` to each route.

---

### P2-09: `referrals.py` — No `response_model` on Any Endpoint

**File**: `backend/api/v1/referrals.py`

None of the referral endpoints (`GET /referrals/code`, `POST /referrals/apply`, `GET /referrals/stats`) declare `response_model`. Referral records may include internal fields.

**Remediation**: Define `ReferralCodeResponse`, `ReferralApplyResponse`, `ReferralStatsResponse` models.

---

### P2-10: `internal/ml.py` — `observation-stats` and `model-versions` Have No Query Param Constraints

**File**: `backend/api/v1/internal/ml.py`

```python
async def get_observation_stats(
    region: str = Query(None),     # No validation
    days: int = Query(30),         # No ge/le bounds
    ...
):
```

```python
async def list_model_versions(
    limit: int = Query(20),        # No le= max
    ...
):
```

`days` with no upper bound could trigger queries spanning years of data. `limit` with no max is an unbounded result set. Internal endpoints are protected by API key but large queries still impose database load.

**Remediation**: Add `ge=1, le=365` to `days` and `ge=1, le=100` to `limit`.

---

### P2-11: `prices_analytics.py` — Unauthenticated Analytics Endpoints with No `response_model`

**File**: `backend/api/v1/prices_analytics.py`

`GET /prices/analytics/optimal-windows`, `GET /prices/analytics/trends`, and `GET /prices/analytics/peak-hours` are fully public (no auth dependency) with no `response_model`. The public access appears intentional (same pattern as `/prices/current`), but is undocumented. None of the three endpoints declare `response_model`.

**Remediation**: Add a docstring comment confirming the public access is intentional. Add `response_model=` to each endpoint.

---

### P2-12: `neighborhood.py` — `region` Query Parameter Has No Format Validation

**File**: `backend/api/v1/neighborhood.py`

`region: str = Query(...)` accepts any string. The internal `_VALID_UTILITY_TYPES` set is checked for `utility_type`, but `region` has no corresponding validation against a known state code or region format pattern.

**Remediation**: Add `pattern=r"^[a-z]{2}(_[a-z]{2})?$"` to the region query parameter or validate against the `Region` enum.

---

### P2-13: `export.py` — Pydantic v1 `regex=` Deprecated, Should Be `pattern=`

**File**: `backend/api/v1/export.py`

```python
format: str = Query("json", regex=r"^(json|csv)$")
```

`regex=` is deprecated in Pydantic v2; the correct parameter is `pattern=`. While Pydantic v2 still accepts `regex=` with a deprecation warning, this will become an error in a future release.

**Remediation**: `format: str = Query("json", pattern=r"^(json|csv)$")`.

---

### P2-14: `user.py` — `POST /preferences` Should Use `PUT` or `PATCH` HTTP Method

**File**: `backend/api/v1/user.py`

```python
@router.post("/preferences")
async def update_preferences(...):
```

This endpoint updates/replaces user preferences (an upsert operation). REST convention uses `PUT` (full replacement) or `PATCH` (partial update) for state-modifying operations. Using `POST` for updates breaks HTTP caching, makes the API non-idempotent by convention, and confuses API consumers.

**Remediation**: Change to `@router.put("/preferences")` or `@router.patch("/preferences")`.

---

### P2-15: `savings.py` — `/combined` Endpoint Free-Tier While `/summary` and `/history` Are Pro-Gated

**File**: `backend/api/v1/savings.py`

`GET /savings/summary` and `GET /savings/history` both require `require_tier("pro")`. `GET /savings/combined` only requires `get_current_user` (free tier accessible). `combined` appears to return merged summary + history data, making the tier gate on the individual endpoints effectively bypassed by calling `/combined`.

**Impact**: Free-tier users can access pro-tier savings data via the `/combined` endpoint.

**Remediation**: Add `require_tier("pro")` to `GET /savings/combined`, or document that `/combined` is intentionally free-tier.

---

### P2-16: `connections/analytics.py` — `days` Max of 1095 Has No Rate Limit Protection

**File**: `backend/api/v1/connections/analytics.py`

```python
days: int = Query(365, ge=1, le=1095)
```

A 3-year history window with no per-endpoint rate limiting. The `require_paid_tier` check gates access to paid users, but a paid user can repeatedly request 1095-day windows. The analytics queries involve multiple JOINs across `connection_extracted_rates` and `user_connections`.

**Remediation**: Reduce the `le=` cap to 365 (1 year) or add per-endpoint rate limiting. Cache expensive analytics responses with a short TTL.

---

### P2-17: `utility_accounts.py` — `utility_type` Filter Is Unvalidated

**File**: `backend/api/v1/utility_accounts.py`

```python
utility_type: Optional[str] = Query(None)
```

In `list_utility_accounts`, the `utility_type` filter is accepted as an arbitrary string and passed directly to the WHERE clause. While parameterized (no injection risk), any string produces a valid query that returns an empty result set, making typos and invalid types silently fail.

**Remediation**: Use `Optional[UtilityType]` where `UtilityType` is a `str` enum of valid utility types (electric, gas, water, etc.).

---

### P2-18: `api/v1/__init__.py` References Old Project Name

**File**: `backend/api/v1/__init__.py`

```python
"""Version 1 of the Energy Optimizer API."""
```

The project was rebranded to RateShift. The module docstring uses the old working name "Energy Optimizer". Minor but contributes to confusion for new developers.

**Remediation**: Update docstring to `"""Version 1 of the RateShift API."""`.

---

## P3 — Low (Address When Convenient)

### P3-01: Inconsistent Pagination Response Field Names Across Endpoints

**Files**: Multiple endpoints across `backend/api/v1/`

Pagination response shapes are inconsistent:
- `connections/rates.py`: `total`, `page`, `page_size`, `pages`
- `alerts.py`: `alerts`, `total`, `page`, `per_page`, `total_pages`
- `community.py`: no pagination metadata on list endpoint
- `suppliers.py` `get_suppliers_by_region`: returns flat list with no pagination metadata

**Remediation**: Define a shared `PaginatedResponse[T]` generic model and use it consistently:
```python
class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int
```

---

### P3-02: `connections/crud.py` — `PATCH /{connection_id}` Missing `response_model`

**File**: `backend/api/v1/connections/crud.py`

The `PATCH /{connection_id}` endpoint returns a raw dict instead of a typed `ConnectionResponse`. All other CRUD endpoints have `response_model` annotations.

**Remediation**: Add `response_model=ConnectionResponse` to the patch route decorator.

---

### P3-03: `agent.py` — `job_id` in `GET /agent/task/{job_id}` Is Unvalidated String

**File**: `backend/api/v1/agent.py`

`job_id: str` accepts any string. Background task IDs are generated as UUIDs by the service layer. Invalid job IDs produce 404 responses after a Redis lookup, but UUID validation at the route level would return 422 immediately with no Redis round-trip.

**Remediation**: `job_id: uuid.UUID = Path(...)`, then `str(job_id)` when querying Redis.

---

### P3-04: `heating_oil.py`, `propane.py`, `water.py` — No Auth, Undocumented Public Access

**Files**:
- `backend/api/v1/heating_oil.py`
- `backend/api/v1/propane.py`
- `backend/api/v1/water.py`

All endpoints in these three files are fully public (no auth dependency). The public access appears intentional (commodity price data), but no docstring or comment confirms this. Developers maintaining these files may accidentally add sensitive data assuming auth is in place.

**Remediation**: Add a module-level docstring explicitly stating: `# All endpoints in this module are intentionally public (no authentication required).`

---

### P3-05: `prices_sse.py` — SSE Connection Count Tracked in Redis But Not in health Endpoint

**File**: `backend/api/v1/prices_sse.py`

The per-user SSE connection limit (3 connections) uses Redis keys with 1-hour TTL. The connection count is not exposed in the `/health/integrations` endpoint, making it difficult to monitor SSE usage or diagnose connection limit issues.

**Remediation**: Add SSE active connection count to `/health/integrations` response via Redis `SCAN` or a dedicated counter key.

---

### P3-06: `utility_discovery.py` — Comma-Split `tracked` Param Values Not Validated

**File**: `backend/api/v1/utility_discovery.py`

```python
tracked: Optional[str] = Query(None, description="Comma-separated list of tracked utilities")
# Handler:
tracked_list = [t.strip() for t in tracked.split(",") if t.strip()]
```

Individual values after splitting are not validated against any allowlist. An input like `tracked=electric,,,,gas,;;;` is processed without error.

**Remediation**: After splitting, validate each value against `UtilityType` enum: `tracked_list = [UtilityType(t) for t in raw_split]` (raises `ValueError` → 422 if invalid).

---

### P3-07: `user.py` — `get_timescale_session` Imported Directly from `config.database`

**File**: `backend/api/v1/user.py`

```python
from config.database import get_timescale_session
```

All other endpoints import database session dependencies from `api.dependencies`. This direct import bypasses any middleware layering applied in `api.dependencies` and creates inconsistency.

**Remediation**: If TimescaleDB sessions need to be dependency-injected, expose `get_timescale_session` through `api.dependencies`.

---

### P3-08: `regulations.py` — No `response_model` on Regulation List Endpoint

**File**: `backend/api/v1/regulations.py`

`GET /regulations` returns a list of regulation objects without a `response_model`. Individual regulation records may contain internal database fields.

**Remediation**: Define `RegulationResponse` model and use `response_model=List[RegulationResponse]`.

---

### P3-09: `connections/analytics.py` — No Ownership Verification on Analytics Comparison Endpoint

**File**: `backend/api/v1/connections/analytics.py`, `get_analytics_comparison`

The `/analytics/comparison` endpoint accepts `connection_ids: List[str]` from the request body or query. The handler verifies that the authenticated user owns each connection via a JOIN, but the error message reveals whether a connection exists at all (404 vs. 403 distinction). An authenticated user can probe for the existence of connection IDs owned by other users by observing error response types.

**Remediation**: Return 404 (not 403) uniformly for any connection not visible to the current user, to avoid confirming existence of IDs owned by others.

---

### P3-10: `suppliers.py` — `compare_suppliers` Returns Hardcoded Mock Rate Data

**File**: `backend/api/v1/suppliers.py`, `compare_suppliers` endpoint

```python
return {
    "comparison": [
        {"supplier_id": ..., "current_rate": "0.25", "six_month_avg": "0.40", ...},
        ...
    ]
}
```

Hardcoded string values `"0.25"` and `"0.40"` are returned as rate data regardless of the actual supplier, region, or time period. This appears to be stub/mock data never replaced with real implementation.

**Impact**: Users see incorrect rate comparison data, undermining trust in the platform's core value proposition.

**Remediation**: Implement real rate lookup from `supplier_registry` and `scraped_rates` tables, or remove the endpoint until it can be properly implemented.

---

### P3-11: `direct_sync.py` — `initiate_utilityapi_authorization` Uses Relative Callback URL

**File**: `backend/api/v1/connections/direct_sync.py`, line 115

```python
callback_url = f"{_settings.frontend_url}/api/v1/connections/direct/callback"
```

The callback URL is constructed using `frontend_url` (the Next.js app URL) as the base, but the callback handler is on the backend (`/api/v1/connections/direct/callback`). In production, `/api/v1/*` on the frontend domain is proxied to the backend via Cloudflare Worker and Next.js rewrites. This works in practice, but creates an indirect routing dependency. If the proxy configuration changes, the callback URL breaks silently.

**Remediation**: Use `settings.backend_url` directly for the callback URL construction:
```python
callback_url = f"{_settings.backend_url}/api/v1/connections/direct/callback"
```

---

### P3-12: `api/v1/__init__.py` — Stale `__all__` Export List

**File**: `backend/api/v1/__init__.py`

The `__init__.py` exports only 3 routers (`prices_router`, `suppliers_router`, `regulations_router`) via a comment listing. The actual router registration happens in `backend/app_factory.py` which imports and mounts all routers directly. The `__init__.py` is misleadingly sparse and confuses developers into thinking only 3 routers exist in `v1/`.

**Remediation**: Either update the module docstring to accurately list all v1 routers, or clear the `__init__.py` to a minimal package marker.

---

## Files Reviewed (Complete List)

### `backend/api/`
- `backend/api/__init__.py`
- `backend/api/dependencies.py`

### `backend/api/v1/` (43 files)
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
- `backend/api/v1/users.py`
- `backend/api/v1/user_supplier.py`
- `backend/api/v1/utility_accounts.py`
- `backend/api/v1/utility_discovery.py`
- `backend/api/v1/water.py`
- `backend/api/v1/webhooks.py`
- `backend/api/v1/health.py`
- `backend/api/v1/affiliate.py`
- `backend/api/v1/referrals.py`
- `backend/api/v1/rate_changes.py`
- `backend/api/v1/beta.py`
- `backend/api/v1/gas_rates.py`

### `backend/api/v1/connections/` (9 files)
- `backend/api/v1/connections/__init__.py`
- `backend/api/v1/connections/router.py`
- `backend/api/v1/connections/common.py`
- `backend/api/v1/connections/crud.py`
- `backend/api/v1/connections/analytics.py`
- `backend/api/v1/connections/bill_upload.py`
- `backend/api/v1/connections/direct_sync.py`
- `backend/api/v1/connections/email_oauth.py`
- `backend/api/v1/connections/portal_scrape.py`
- `backend/api/v1/connections/rates.py`

### `backend/api/v1/internal/` (9 files)
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

### `backend/routers/` (2 files)
- `backend/routers/__init__.py`
- `backend/routers/predictions.py`

---

## Summary Table

| ID | Severity | File | Finding |
|----|----------|------|---------|
| P0-01 | CRITICAL | `utility_accounts.py:63` | Account number stored as bytes, not encrypted |
| P0-02 | CRITICAL | `connections/common.py` | OAuth state timeout constant defined but never enforced |
| P0-03 | CRITICAL | `compliance.py:300-349` | GDPR delete endpoint with no confirmation requirement |
| P1-01 | HIGH | `affiliate.py` | Unauthenticated click endpoint accepts arbitrary user_id |
| P1-02 | HIGH | connections/* | All connection_id path params are str, not uuid.UUID |
| P1-03 | HIGH | Multiple files | Internal exception messages leaked in HTTP responses |
| P1-04 | HIGH | `direct_sync.py` | `POST /direct/authorize` accepts raw dict, no Pydantic model |
| P1-05 | HIGH | `internal/operations.py` | assert-based allowlist guards f-string SQL construction |
| P1-06 | HIGH | `recommendations.py` | No response_model on any of 3 endpoints |
| P1-07 | HIGH | `suppliers.py` | Dynamic SQL WHERE clause via string concatenation |
| P1-08 | HIGH | `public_rates.py` | No format validation on state and utility_type path params |
| P1-09 | HIGH | `community.py` | post_id params unvalidated str, no response_model |
| P1-10 | HIGH | `beta.py` | Pagination params accepted but silently ignored |
| P1-11 | HIGH | `beta.py` | LIKE pattern match on compound interest field |
| P1-12 | HIGH | `predictions.py` | Route handler called directly as Python function |
| P1-13 | HIGH | `gas_rates.py` | Dead auth imports suggest accidentally public endpoints |
| P1-14 | HIGH | `predictions.py` | Module-level model cache not safe for multi-worker deployment |
| P2-01 | MEDIUM | `email_oauth.py` | Hardcoded allowed frontends, breaks preview deployments |
| P2-02 | MEDIUM | `health.py` | Public /health exposes environment and version metadata |
| P2-03 | MEDIUM | `recommendations.py` | Uses stdlib logging instead of structlog |
| P2-04 | MEDIUM | `connections/common.py` | _UPLOADS_DIR is a relative path |
| P2-05 | MEDIUM | `cca.py` | cca_id unvalidated str, zip_code no format validation |
| P2-06 | MEDIUM | `community_solar.py` | program_id unvalidated str |
| P2-07 | MEDIUM | `rate_changes.py` | channels field accepts arbitrary strings |
| P2-08 | MEDIUM | `notifications.py` | GET endpoints missing response_model |
| P2-09 | MEDIUM | `referrals.py` | No response_model on any endpoint |
| P2-10 | MEDIUM | `internal/ml.py` | No bounds on days and limit query params |
| P2-11 | MEDIUM | `prices_analytics.py` | Unauthenticated endpoints with no response_model |
| P2-12 | MEDIUM | `neighborhood.py` | region query param has no format validation |
| P2-13 | MEDIUM | `export.py` | Deprecated Pydantic v1 regex= parameter |
| P2-14 | MEDIUM | `user.py` | POST /preferences should use PUT or PATCH |
| P2-15 | MEDIUM | `savings.py` | /combined accessible to free tier, bypasses pro gate |
| P2-16 | MEDIUM | `connections/analytics.py` | days max 1095, no rate limiting on expensive queries |
| P2-17 | MEDIUM | `utility_accounts.py` | utility_type filter unvalidated string |
| P2-18 | MEDIUM | `api/v1/__init__.py` | Module docstring uses old project name |
| P3-01 | LOW | Multiple | Inconsistent pagination response field names |
| P3-02 | LOW | `connections/crud.py` | PATCH endpoint missing response_model |
| P3-03 | LOW | `agent.py` | job_id unvalidated str path param |
| P3-04 | LOW | heating_oil.py, propane.py, water.py | Public access undocumented |
| P3-05 | LOW | `prices_sse.py` | SSE connection count not in health endpoint |
| P3-06 | LOW | `utility_discovery.py` | tracked param values not validated after splitting |
| P3-07 | LOW | `user.py` | get_timescale_session imported directly from config |
| P3-08 | LOW | `regulations.py` | response_model missing on list endpoint |
| P3-09 | LOW | `connections/analytics.py` | 404 vs 403 distinction leaks connection existence |
| P3-10 | LOW | `suppliers.py` | compare_suppliers returns hardcoded mock rate data |
| P3-11 | LOW | `direct_sync.py` | Callback URL uses frontend_url instead of backend_url |
| P3-12 | LOW | `api/v1/__init__.py` | Stale __all__ export list |

---

## Positive Patterns Observed

These patterns are well-implemented and should be maintained as standards:

1. **Internal endpoint auth architecture** (`internal/__init__.py`): Single `APIRouter(dependencies=[Depends(verify_api_key)])` applies API key auth uniformly to all 9 sub-routers. Clean and impossible to accidentally bypass.

2. **UUID path parameter enforcement** (`alerts.py`, `user_supplier.py`): `connection_id: uuid.UUID` pattern with `str(connection_id)` conversion in SQL calls. Free 422 validation before any handler logic. Should be applied uniformly across the codebase (see P1-02).

3. **OAuth state HMAC signing** (`connections/common.py`): `sign_callback_state` embeds connection_id, user_id, and timestamp in an HMAC-SHA256 payload. Cryptographically sound pattern — just needs the timestamp validation wired in (P0-02).

4. **Stripe webhook signature verification** (`billing.py`): Uses `stripe.Webhook.construct_event()` with raw body bytes and signature header. Correct implementation.

5. **GitHub webhook HMAC-SHA256** (`webhooks.py`): Uses `hmac.compare_digest()` for constant-time comparison. Correct implementation.

6. **SSE connection limiting** (`prices_sse.py`): Per-user connection limit (3) with Redis backing and 1-hour TTL safety. Prevents connection exhaustion attacks.

7. **Bill upload magic byte validation** (`connections/bill_upload.py`): Checks file magic bytes in addition to MIME type and extension, preventing content-type spoofing.

8. **Error sanitization in internal endpoints** (`internal/alerts.py`): Returns `"Alert check failed. See server logs for details."` — the correct pattern that other files should follow (see P1-03).

9. **connections/router.py route ordering documentation**: Comprehensive docstring explaining registration order rationale for FastAPI route matching. Excellent maintainability documentation.

10. **Tier gating consistency** (`prices.py`, `forecast.py`, `billing.py`): `require_tier("pro"/"business")` applied correctly on forecasting, SSE streaming, and savings history endpoints. Exception at `/savings/combined` noted (P2-15).
