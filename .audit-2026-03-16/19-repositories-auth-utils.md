# Audit: Repositories, Auth, Compliance, Integrations, Utils

**Date**: 2026-03-16
**Auditor**: Claude Sonnet 4.6
**Scope**: `backend/repositories/`, `backend/auth/`, `backend/compliance/`, `backend/integrations/`, `backend/utils/`, `backend/routers/predictions.py`, `backend/templates/`

---

## Summary

| Severity | Count |
|----------|-------|
| P0 — Critical (must fix before next deploy) | 3 |
| P1 — Major (fix within current sprint) | 8 |
| P2 — Moderate (fix within next sprint) | 7 |
| P3 — Minor (tech debt / next cycle) | 6 |
| **Total** | **24** |

---

## P0 — Critical

### P0-1: Python repr used as JSON serializer — invalid JSONB, potential injection

**File**: `backend/repositories/utility_account_repository.py`
**Lines**: 77, 103

**Description**: The `metadata` field (a Python dict) is serialized to JSONB using `str(entity.metadata).replace("'", '"')`. Python's `str()` on a dict produces Python repr, not JSON: `True` becomes `True` (not `true`), `None` becomes `None` (not `null`), single-quoted strings become double-quoted but nested quotes may not survive the replace. This can silently write invalid JSONB to the database or, if a metadata value contains a single quote followed by SQL-relevant characters, produce malformed but potentially exploitable SQL parameter values. The parameterized query prevents direct SQL injection, but PostgreSQL will reject or misparse the JSONB string at cast time, causing silent data loss or a 500 error.

**Affected calls**: `create()` (line 77) and `update()` (line 103).

```python
# CURRENT (line 77) — broken
"metadata": str(entity.metadata).replace("'", '"') if entity.metadata else "{}",

# CURRENT (line 103) — broken
"metadata": str(entity.metadata).replace("'", '"') if entity.metadata else None,
```

**Fix**: Use `json.dumps()` from the standard library:

```python
import json

# In create():
"metadata": json.dumps(entity.metadata) if entity.metadata else "{}",

# In update():
"metadata": json.dumps(entity.metadata) if entity.metadata else None,
```

The SQL cast `::jsonb` will then receive well-formed JSON in all cases.

---

### P0-2: ORM query against a Pydantic model — guaranteed runtime crash

**File**: `backend/routers/predictions.py`
**Line**: 283 (approximate — `select(Price)` call inside `_load_ml_model`)

**Description**: The code calls `select(Price).where(Price.region == region)` where `Price` is a Pydantic model, not a SQLAlchemy ORM model. SQLAlchemy's `select()` expects a mapped class; when called with a Pydantic model it either raises `ArgumentError` or returns a clause that will fail when executed. This path is reached when the ML model is loaded and historical prices are fetched for training — meaning the ensemble predictor will crash on first use after a cold start, silently falling through to the simulation fallback without logging the root cause clearly.

**Fix**: Replace the ORM query with a raw SQL `text()` query consistent with the rest of the codebase:

```python
result = await db.execute(
    text(
        "SELECT region, timestamp, price, unit, currency "
        "FROM electricity_prices "
        "WHERE region = :region "
        "ORDER BY timestamp DESC LIMIT 500"
    ),
    {"region": region.value},
)
rows = result.mappings().all()
```

Then construct `PriceData` objects from the row mappings. Also add a test that exercises the model-loading path with a real (mocked) DB session to catch this class of regression.

---

### P0-3: GDPR deletion audit log is created in memory but never persisted to the database

**File**: `backend/compliance/gdpr.py`
**Line**: ~802 (inside `delete_user_data`)

**Description**: `delete_user_data()` constructs a `DeletionLog` Pydantic object to record the GDPR Article 17 erasure event, then returns it. However, there is no call to `DeletionLogRepository.create()` or any equivalent `db.execute(INSERT ...)` to persist this record. The log exists only for the duration of the request and is silently discarded. Under GDPR Article 5(2) (accountability principle) and Article 17(3), data controllers must be able to demonstrate that erasure was performed. An audit log that is never written to durable storage fails this requirement entirely.

**Fix**: After all anonymization/deletion steps succeed, persist the log before returning:

```python
deletion_log_repo = DeletionLogRepository(session)
await deletion_log_repo.create(deletion_log)
```

Alternatively, if `DeletionLogRepository.create()` does its own commit, ensure it is called inside the existing transaction block. Add an integration test that verifies a `deletion_logs` row exists after `delete_user_data()` completes.

---

## P1 — Major

### P1-1: `get_by_id` in NotificationRepository has no user_id ownership check — IDOR

**File**: `backend/repositories/notification_repository.py`
**Line**: ~81 (`get_by_id` method)

**Description**: `get_by_id(notification_id)` fetches a notification by its UUID with no filter on `user_id`. Any caller that has a notification UUID (e.g., obtained by brute-force, timing attack, or a different user's leaked ID) can read arbitrary notifications belonging to other users. The `get_by_delivery_status()` and `get_by_channel()` methods correctly scope by `user_id`, so the ownership model is understood — it's simply missing from `get_by_id`.

**Fix**: Add a `user_id` parameter and include it in the WHERE clause:

```python
async def get_by_id(self, notification_id: str, user_id: str) -> Optional[Notification]:
    result = await self._db.execute(
        text(
            f"SELECT {_COLUMNS} FROM notifications "
            "WHERE id = :id AND user_id = :user_id"
        ),
        {"id": notification_id, "user_id": user_id},
    )
    row = result.mappings().first()
    return _row_to_notification(row) if row else None
```

Update all call sites to pass the authenticated user's ID. Any call site that cannot supply a `user_id` (e.g., internal admin path) should use a separate method that is explicitly marked as admin-only and protected by an admin role check.

---

### P1-2: No authentication on prediction endpoints — publicly accessible

**File**: `backend/routers/predictions.py`
**Lines**: All route decorators (`@router.get("/predict/price")`, `/predict/optimal-times`, `/predict/savings`, `/predict/model-info`)

**Description**: None of the four prediction endpoints require authentication. The ML inference routes accept arbitrary `region` and `appliances` parameters, run forecast generation, and return detailed price/savings data without any session check. At minimum this leaks proprietary ML model outputs and pricing intelligence to unauthenticated parties. At worst, the `estimate_savings()` endpoint (see P1-3) can be abused for compute-intensive denial of service without authentication.

**Fix**: Add the `get_current_user` dependency to each endpoint:

```python
from auth.neon_auth import get_current_user, SessionData

@router.get("/predict/price")
async def predict_price(
    region: str,
    current_user: SessionData = Depends(get_current_user),
    ...
):
```

For plan-gated endpoints (forecast is Pro-only per CLAUDE.md), also add `require_tier("pro")`.

---

### P1-3: N+1 forecast generation in `estimate_savings` — one full 24h forecast per appliance

**File**: `backend/routers/predictions.py`
**Lines**: `estimate_savings()` implementation (~lines 583-604)

**Description**: `estimate_savings()` accepts a list of appliances and, for each appliance, calls `find_optimal_times()` which in turn calls `generate_price_forecast()` to produce a 24-hour price forecast. With a list of 10 appliances, this generates 10 independent forecast calls, each potentially hitting the pricing API or running the ML ensemble. The forecast for a given `(region, hours)` pair is identical for every appliance — only the appliance-specific shift window calculation differs.

**Fix**: Generate the forecast once outside the loop, then pass it into each appliance calculation:

```python
forecast = await generate_price_forecast(region, hours=24, db=db)
savings_results = []
for appliance in appliances:
    optimal = _find_optimal_window_from_forecast(forecast, appliance)
    savings_results.append(optimal)
```

Extract the per-appliance window selection into a synchronous helper `_find_optimal_window_from_forecast(forecast, appliance)` that operates on the already-computed `PriceForecast` object.

---

### P1-4: API keys exposed in URL query parameters — appear in access logs

**Files**:
- `backend/integrations/pricing_apis/eia.py`, line ~147: `params["api_key"] = self.api_key`
- `backend/integrations/pricing_apis/nrel.py`, lines ~287, 421, 458, 491: `params = {"api_key": self.api_key}`
- `backend/integrations/weather_service.py`, line ~238: `params["appid"] = self.api_key`

**Description**: All three integrations pass API keys as URL query parameters. These keys will appear verbatim in:
- The backend's HTTP access logs (Render logs, Cloudflare access logs)
- httpx request debug logs if enabled
- Any HTTP proxy or CDN access logs
- Error response bodies if the external API reflects the request URL in error messages

NREL additionally passes `"lat": None, "lon": None` as explicit null query params (nrel.py lines 289-290), which may confuse the NREL API or cause unexpected query string characters.

**Fix for EIA/NREL**: Pass the key in an `X-Api-Key` header (if the API supports it) or use the `Authorization` header. If the API only accepts query params, ensure the httpx client does not log params at the request level. At minimum, mask the key in any structured log entries:

```python
# In _get_default_headers() — if API supports header auth
return {
    "X-Api-Key": self.api_key,
    "Accept": "application/json",
}
# Remove api_key from params dict entirely
```

For NREL specifically, also remove the `"lat": None, "lon": None` entries from the params dict — only include keys with non-None values:

```python
params = {k: v for k, v in raw_params.items() if v is not None}
```

---

### P1-5: Non-atomic Redis rate limiter — TOCTOU race condition

**File**: `backend/integrations/pricing_apis/rate_limiter.py`
**Lines**: `RedisRateLimiter.acquire()` implementation (~lines 395-433)

**Description**: The Redis rate limiter uses a two-phase pipeline: (1) read current count, (2) conditionally increment. Between the read and the increment, another concurrent request can pass the count check and also increment, allowing the limit to be exceeded by the number of concurrent requests at the boundary. Under high concurrency (e.g., multiple async tasks firing simultaneously), the actual request rate can exceed the configured limit.

**Fix**: Use a Lua script for atomic check-and-increment, which Redis executes atomically:

```lua
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local count = redis.call('ZCOUNT', key, now - window, now)
if count < limit then
    redis.call('ZADD', key, now, now .. math.random())
    redis.call('EXPIRE', key, window)
    return 1
else
    return 0
end
```

Load this script with `redis.register_script()` on client initialization and call it atomically via `evalsha`. Alternatively, use `redis-py`'s built-in `pipeline()` with `WATCH`/`MULTI`/`EXEC` for optimistic locking.

---

### P1-6: `withdraw_all_consents()` is non-atomic — partial withdrawal is possible

**File**: `backend/compliance/gdpr.py`
**Lines**: `withdraw_all_consents()` implementation (~lines 322-338)

**Description**: `withdraw_all_consents()` iterates over all consent types and calls `record_consent()` for each, where `record_consent()` issues a separate `COMMIT` per consent type. If the process fails or is interrupted mid-loop (network error, timeout, unhandled exception on the 3rd of 5 consent types), the user ends up in a partially-withdrawn state with some consents still active. Under GDPR Article 7(3), withdrawal of consent must be "as easy" to give as to withdraw — a partially-applied withdrawal that leaves lingering consents is a compliance violation.

**Fix**: Gather all consent updates in a single transaction:

```python
async def withdraw_all_consents(self, user_id: str) -> None:
    consent_repo = ConsentRepository(self.session)
    for consent_type in ConsentType:
        await consent_repo.create_without_commit(
            user_id=user_id,
            consent_type=consent_type,
            granted=False,
            ...
        )
    await self.session.commit()
```

Add a `create_without_commit()` variant to `ConsentRepository` that stages the INSERT without committing, relying on the caller to commit. Wrap the loop in a try/except with `await self.session.rollback()` on failure.

---

### P1-7: `backfill_actuals()` performs unbounded full-table UPDATE when region is None

**File**: `backend/repositories/forecast_observation_repository.py`
**Line**: ~117 (`backfill_actuals` with `region=None`)

**Description**: When called without a `region` argument, `backfill_actuals()` constructs an UPDATE statement with no WHERE clause on `region`, updating every unresolved observation in the table. On a large table this will: (a) acquire row-level locks on a very large number of rows, (b) produce a massive WAL write, (c) block concurrent reads/writes on those rows for the duration of the operation. There is also no LIMIT, so if millions of observations are pending, a single call could run for many minutes and starve other queries.

**Fix**: Add a `batch_size` cap and always log the count:

```python
async def backfill_actuals(
    self,
    region: Optional[str] = None,
    cutoff: datetime = ...,
    batch_size: int = 1000,  # new param
) -> int:
    where_clauses = ["resolved_at IS NULL", "timestamp < :cutoff"]
    params = {"cutoff": cutoff, "batch_size": batch_size}
    if region:
        where_clauses.append("region = :region")
        params["region"] = region
    where = " AND ".join(where_clauses)
    result = await self._db.execute(
        text(
            f"UPDATE forecast_observations SET ... "
            f"WHERE {where} "
            f"LIMIT :batch_size"  # or use a CTE with ctid
        ),
        params,
    )
    return result.rowcount
```

Callers (cron jobs) should loop until `rowcount == 0` to handle large backlogs in safe increments.

---

### P1-8: `SlidingWindowRateLimiter._windows` grows without bound

**File**: `backend/integrations/pricing_apis/rate_limiter.py`
**Line**: `SlidingWindowLimiter` class, `_windows` dict initialization and usage

**Description**: The in-process sliding window rate limiter stores a deque of timestamps per key in `self._windows: dict[str, deque]`. Keys are added as new API endpoints or regions are encountered but are never evicted. In a long-running process that cycles through many regions or API paths, this dict grows indefinitely. On a server running for weeks with 50+ US states as distinct keys, the leak is small but present. More importantly, stale entries for keys that are no longer active are never cleaned up.

**Fix**: Add a TTL-based eviction sweep triggered on acquire or periodically:

```python
def _evict_stale_keys(self, now: float) -> None:
    stale = [
        k for k, dq in self._windows.items()
        if not dq or (now - dq[-1]) > self._window_seconds * 2
    ]
    for k in stale:
        del self._windows[k]
```

Call `_evict_stale_keys(now)` at the start of `acquire()`. This is O(keys) but keys is bounded by the number of distinct rate-limited entities, which is small.

---

## P2 — Moderate

### P2-1: `get_by_user()` and `get_by_user_and_type()` silently truncate at 100 accounts

**File**: `backend/repositories/utility_account_repository.py`
**Lines**: 186, 192-194

**Description**: Both convenience methods call `self.list(page_size=100, ...)`. A user with more than 100 utility accounts (uncommon today, but possible for business/multi-property users) will silently receive a truncated result set. Callers have no way to detect the truncation because the return type is `List[UtilityAccount]` with no pagination metadata.

```python
async def get_by_user(self, user_id: str) -> List[UtilityAccount]:
    return await self.list(page=1, page_size=100, user_id=user_id)  # silent cap
```

**Fix**: Either (a) implement true pagination and propagate it to callers, or (b) use a high-enough safety cap with an explicit warning log:

```python
async def get_by_user(self, user_id: str) -> List[UtilityAccount]:
    results = await self.list(page=1, page_size=500, user_id=user_id)
    if len(results) == 500:
        logger.warning("get_by_user_truncated", user_id=user_id, cap=500)
    return results
```

Option (b) is acceptable short-term. Long-term, expose a paginated API endpoint rather than fetching all records at once.

---

### P2-2: `_UPDATABLE_COLUMNS` excludes consent and login fields — those fields can never be updated

**File**: `backend/repositories/user_repository.py`
**Lines**: ~177-186 (the `_UPDATABLE_COLUMNS` frozenset definition)

**Description**: The `_UPDATABLE_COLUMNS` whitelist (which prevents SQL injection in the dynamic UPDATE) does not include `consent_given`, `consent_date`, `data_processing_agreed`, or `last_login`. Any call to `user_repo.update(user_id, user)` that sets these fields will silently drop them — the whitelist filter strips unknown columns before building the SET clause. The GDPR consent fields are particularly important: if the consent service writes consent state to the `User` model and then calls `user_repo.update()`, the consent is never persisted.

**Fix**: Add the missing columns to the whitelist and verify that consent_date / last_login update paths are tested:

```python
_UPDATABLE_COLUMNS = frozenset({
    "name",
    "email",
    "region",
    "preferences",
    "is_active",
    "consent_given",       # add
    "consent_date",        # add
    "data_processing_agreed",  # add
    "last_login",          # add
    "stripe_customer_id",
    "subscription_tier",
    "subscription_expires_at",
})
```

Verify the `users` table schema has these columns (cross-check with the latest migration).

---

### P2-3: `ConsentRepository.get_by_user_id()` and `DeletionLogRepository.get_by_user_id()` have no LIMIT

**File**: `backend/compliance/repositories.py`
**Lines**: ~144-151 (ConsentRepository), ~317-324 (DeletionLogRepository)

**Description**: Both `get_by_user_id()` methods issue `SELECT ... WHERE user_id = :user_id ORDER BY created_at DESC` with no LIMIT clause. For a user who has changed consent preferences hundreds of times or has multiple deletion records, this returns an unbounded result set into application memory. While unlikely to cause problems today, it is a latent memory and performance issue.

**Fix**: Add a configurable limit with a reasonable default:

```python
async def get_by_user_id(self, user_id: str, limit: int = 200) -> list[ConsentRecord]:
    result = await self.session.execute(
        text(
            "SELECT ... FROM consent_records "
            "WHERE user_id = :user_id "
            "ORDER BY created_at DESC "
            "LIMIT :limit"
        ),
        {"user_id": user_id, "limit": limit},
    )
    ...
```

---

### P2-4: `ensure_user_profile()` has no rollback handler — dirty session on commit failure

**File**: `backend/auth/neon_auth.py`
**Lines**: ~254-272 (`ensure_user_profile` implementation)

**Description**: `ensure_user_profile()` executes an INSERT ... ON CONFLICT DO UPDATE and then calls `await db.commit()`. If the commit raises (e.g., network blip, constraint violation added later), the SQLAlchemy `AsyncSession` is left in a dirty/failed state. Subsequent uses of the same session within the same request lifecycle will fail with `sqlalchemy.exc.InvalidRequestError`. There is no `try/except` with `await db.rollback()`.

**Fix**:

```python
try:
    result = await db.execute(insert, {...})
    await db.commit()
except Exception:
    await db.rollback()
    raise
```

Alternatively, let the session lifecycle management in the FastAPI dependency (`get_timescale_session`) handle rollbacks — but only if the dependency is configured to do so on exception (verify this in `config/database.py`).

---

### P2-5: `_fetch_series` and equivalent methods trip the circuit breaker on 401/403 — incorrect behavior

**File**: `backend/integrations/pricing_apis/base.py`
**Lines**: `_execute_with_retry()`, the block that calls `self._circuit_breaker.record_failure()` on error

**Description**: The base pricing client records a circuit breaker failure for any HTTP error response, including 401 (invalid API key) and 403 (forbidden/quota exceeded). A 401 indicates a configuration error — the API key is wrong or expired. This is not an infrastructure failure; it will not resolve by retrying. Tripping the circuit breaker on 401/403 means the breaker opens unnecessarily, blocking all subsequent requests (including ones that might succeed with a refreshed key) and triggering false alerts.

The `UtilityAPIClient._request()` correctly handles this — it only calls `cb.record_failure()` on 5xx, not 4xx. The pricing API base client should follow the same pattern.

**Fix**: Distinguish auth failures from infrastructure failures in `_execute_with_retry()`:

```python
if response.status_code in (401, 403):
    # Config error — do not trip circuit breaker; raise immediately
    raise APIError(
        f"Authentication failure ({response.status_code}): check API key",
        api_name=self.client_name,
        status_code=response.status_code,
    )
elif response.status_code >= 500:
    await self._circuit_breaker.record_failure()
    # ... retry logic
```

---

### P2-6: Silent UUID generation when database row has NULL id

**File**: `backend/repositories/user_repository.py`
**Line**: ~49

**Description**: In `_row_to_user()` (or equivalent row mapping helper), the code reads the `id` column as `data.get("id", str(uuid4()))`. If the database returns a row where `id` is NULL (which should never happen given the NOT NULL constraint, but could occur during a migration or if a column alias is wrong), a fresh random UUID is generated silently. The caller receives a `User` object with an ID that does not match anything in the database. Any subsequent write using this ID will create a phantom record.

**Fix**: Remove the default and raise an explicit error:

```python
user_id = data["id"]
if user_id is None:
    raise RepositoryError("Database returned NULL user id — schema invariant violated")
```

This surfaces the true problem (a schema or query bug) rather than hiding it behind a random UUID.

---

### P2-7: `anonymize_ip()` only handles IPv4 — IPv6 addresses passed through unmodified

**File**: `backend/compliance/gdpr.py`
**Line**: `anonymize_ip()` implementation (~line 110)

**Description**: The `anonymize_ip()` function uses a regex or split approach that targets `x.x.x.x` format IPv4 addresses (zeroing the last octet). IPv6 addresses (e.g., `2001:db8:85a3::8a2e:370:7334`) are returned unchanged because the IPv4 pattern does not match them. With IPv6 adoption growing, logging any user's full IPv6 address is equivalent to logging a globally-unique identifier — it is personal data under GDPR Article 4(1).

**Fix**: Handle both address families:

```python
import ipaddress

def anonymize_ip(ip_str: str) -> str:
    try:
        addr = ipaddress.ip_address(ip_str)
        if isinstance(addr, ipaddress.IPv4Address):
            # Zero last octet
            parts = ip_str.split(".")
            return ".".join(parts[:3] + ["0"])
        else:
            # IPv6: zero last 80 bits (keep first 48 bits / first 3 groups)
            network = ipaddress.IPv6Network(f"{ip_str}/48", strict=False)
            return str(network.network_address)
    except ValueError:
        return "invalid_ip"
```

---

## P3 — Minor

### P3-1: Deprecated `SupplierRepository` (ORM-based) still present in codebase

**File**: `backend/repositories/supplier_repository.py`
**Lines**: `SupplierRepository` class definition

**Description**: `SupplierRepository` is marked with a deprecation comment and uses SQLAlchemy ORM (`select(Supplier)`), inconsistent with the rest of the codebase which uses raw SQL. `SupplierRegistryRepository` is the production replacement. The deprecated class remains importable and could be used accidentally by new contributors.

**Fix**: Remove `SupplierRepository` entirely. Search for any remaining import sites:

```bash
grep -r "SupplierRepository" backend/ --include="*.py"
```

If no active import sites remain (only the class definition itself), delete the class. If any sites still use it, migrate them to `SupplierRegistryRepository` first.

---

### P3-2: `StateRegulationRepository.get_by_state()` uses `SELECT *`

**File**: `backend/repositories/supplier_repository.py`
**Line**: `get_by_state()` implementation

**Description**: `SELECT *` fetches all columns including any future columns added by migrations, which may include sensitive or large JSONB fields not intended for this query path. It also makes the query's output schema implicit — a migration that adds a column silently changes what this function returns.

**Fix**: Enumerate the columns explicitly, consistent with other repositories' `_COLUMNS` pattern:

```python
_REGULATION_COLUMNS = "id, state, regulation_type, description, effective_date, updated_at"
```

---

### P3-3: `_get_key()` re-reads settings on every encrypt/decrypt call

**File**: `backend/utils/encryption.py`
**Lines**: `_get_key()` function, called from `encrypt_field()` and `decrypt_field()`

**Description**: `_get_key()` reads `settings.encryption_key` and runs key derivation (or base64 decode) on every invocation. Settings access is fast, but key derivation (if PBKDF2 or similar) is intentionally slow. Even if the current implementation is just a base64 decode (cheap), it is an unnecessary repeated operation.

**Fix**: Cache the derived key at module load time or on first call:

```python
_derived_key: Optional[bytes] = None

def _get_key() -> bytes:
    global _derived_key
    if _derived_key is None:
        raw = settings.encryption_key
        _derived_key = base64.b64decode(raw)  # or PBKDF2 etc.
    return _derived_key
```

If key rotation is ever added, invalidate the cache by setting `_derived_key = None`.

---

### P3-4: No maximum password length — potential bcrypt DoS

**File**: `backend/auth/password.py`
**Lines**: `validate_password()` implementation

**Description**: `validate_password()` enforces a minimum length (8 chars) but no maximum. bcrypt has an internal input limit of 72 bytes and silently truncates longer inputs. An attacker submitting a 1 MB "password" forces the server to hash 1 MB of data, stressing CPU. While not a severe DoS risk on its own, it is an unnecessary attack surface.

**Fix**: Add a maximum length check before passing to bcrypt:

```python
MAX_PASSWORD_BYTES = 72  # bcrypt's internal limit

def validate_password(password: str) -> bool:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError("Password must be at most 72 characters")
    return True
```

72 bytes is the effective limit; a UX-friendly message might say "64 characters" to account for multi-byte UTF-8.

---

### P3-5: `get_authorization_status` `state` parameter has no HMAC signing — weak CSRF protection

**File**: `backend/integrations/utilityapi.py`
**Lines**: `create_authorization_form()` (~lines 259-268)

**Description**: The `state` parameter passed to UtilityAPI's authorization URL is documented as "opaque value echoed back in the callback". The current implementation passes `state` directly as provided by the caller with no HMAC signature. If `state` contains a `connection_id` (which is the documented intent — to bind the callback to a connection), an attacker who can predict connection IDs can forge a callback by submitting the correct `?state=` value to the callback endpoint. The risk is mitigated if connection IDs are UUIDs (hard to predict), but defence-in-depth requires signing.

**Fix**: Sign the state value with an HMAC:

```python
import hmac, hashlib, json

def _sign_state(self, state_data: dict) -> str:
    payload = json.dumps(state_data, sort_keys=True)
    sig = hmac.new(
        settings.secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    return f"{payload}:{sig}"

def _verify_state(self, state: str) -> dict:
    payload, sig = state.rsplit(":", 1)
    expected = hmac.new(
        settings.secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Invalid state signature")
    return json.loads(payload)
```

Use `_sign_state({"connection_id": connection_id})` when generating the URL and `_verify_state(state)` in the callback handler.

---

### P3-6: NREL `get_current_price()` sends `lat=None` and `lon=None` as URL parameters

**File**: `backend/integrations/pricing_apis/nrel.py`
**Lines**: 289-290

**Description**: The params dict passed to `self.get()` includes `"lat": None` and `"lon": None`. httpx serializes `None` as the string `"None"` in query strings (or may omit it depending on version). Sending `?lat=None&lon=None` to the NREL API is semantically incorrect and may cause the API to return an error or fall back to unexpected behavior. The comment says "Will be looked up from ZIP" but the lat/lon keys are still present.

**Fix**: Remove the None-valued keys from the params dict entirely:

```python
params = {
    "api_key": self.api_key,
    "address": zip_code,
}
# lat/lon omitted — NREL will geocode from the address
```

---

## Notes on Files With No Significant Issues

- `backend/repositories/base.py` — Clean abstract base. Error hierarchy (RepositoryError, NotFoundError, DuplicateError, ValidationError) is appropriate and consistently used.
- `backend/repositories/price_repository.py` — Well-implemented cache stampede prevention, proper chunked bulk insert, paginated historical query with parallel COUNT. No issues found.
- `backend/repositories/model_config_repository.py` — Atomic deactivate-then-insert pattern is correct.
- `backend/integrations/utilityapi.py` — Circuit breaker integration, 4xx vs 5xx failure discrimination, clean async context manager pattern. Well-structured.
- `backend/integrations/pricing_apis/cache.py` — Background refresh with `finally` cleanup is correct. No issues found.
- `backend/integrations/pricing_apis/base.py` — Request deduplication with `_pending_requests` + `finally` cleanup is correct. The 401/403 circuit breaker issue is noted in P2-5.
- `backend/templates/emails/dunning_soft.html`, `dunning_final.html` — Jinja2 auto-escaping applies; `{{ billing_url }}` is safe assuming the template engine is configured with `autoescape=True`. Verify this in the email service that renders these templates.
