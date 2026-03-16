# API Routes Audit — 2026-03-16

**Scope**: All `.py` files in `backend/api/v1/` and subdirectories (38 files)
**Auditor**: Claude Code (claude-sonnet-4-6)

---

## Summary Counts

| Severity | Count |
|----------|-------|
| P0 — Critical (bugs / security) | 4 |
| P1 — High (performance / design flaws) | 7 |
| P2 — Medium (correctness risks, missing validation) | 10 |
| P3 — Low (style, maintainability, minor gaps) | 6 |
| **Total** | **27** |

---

## P0 — Critical

### P0-01 · SQL injection via f-string column names in `users.py`

**File**: `backend/api/v1/users.py`
**Lines**: 196–200 (`update_profile`)

`update_profile` builds a `SET` clause by joining column names from a `dict`
whose keys come from Pydantic field names. Because the interpolated keys are
controlled by the Pydantic model definition and not by user input, this is not
directly exploitable today. However, the pattern is dangerous: if any future
developer adds a field to `UserProfileUpdate` that could carry an attacker-
influenced name (e.g., through dynamic field construction or model inheritance),
the resulting SQL would be structurally injectable. It also bypasses the
intended separation of parameterisation and structure.

More critically, the column names are constructed from `updates.keys()` which
include anything that was not `None` in the request. If the Pydantic model
were to be extended to accept a `tier_required` or `subscription_tier` field
(even accidentally), that would become an unpermissioned column update.

```python
# Current code (lines 196–200):
set_clause = ", ".join(f"{k} = :{k}" for k in updates)
updates["uid"] = current_user.user_id
await db.execute(
    text(f"UPDATE users SET {set_clause}, updated_at = now() WHERE id = :uid"),
    updates,
)
```

**Suggested fix**: Use an explicit allowlist and build the SET clause from it:

```python
UPDATABLE_COLUMNS = frozenset({
    "name", "region", "utility_types", "current_supplier_id",
    "annual_usage_kwh", "onboarding_completed",
})

# Verify nothing outside the allowlist sneaked in (defence-in-depth)
assert updates.keys() <= UPDATABLE_COLUMNS, "Unexpected column in update"

set_clause = ", ".join(f"{k} = :{k}" for k in updates if k in UPDATABLE_COLUMNS)
```

---

### P0-02 · SQL injection via f-string table/column names in `internal/operations.py`

**File**: `backend/api/v1/internal/operations.py`
**Lines**: 148–157 (`data_health_check`)

`data_health_check` iterates a hard-coded list of `(table_name, ts_col)` tuples
and builds queries by interpolating both values directly into `text()` f-strings:

```python
count_result = await db.execute(
    text(f"SELECT COUNT(*) FROM {table_name}")
)
...
ts_result = await db.execute(
    text(f"SELECT MAX({ts_col}) FROM {table_name}")
)
```

The list at lines 132–143 is fully hard-coded and not user-supplied, so there is
no immediate injection path. However:

1. The pattern establishes an anti-pattern that is visually indistinguishable
   from a genuine injection risk; code reviewers and static analysis tools will
   flag it.
2. If an operator ever extends this endpoint to accept a `table` query parameter
   (e.g., for diagnostics), the pattern would become directly exploitable.
3. SQLAlchemy's `text()` function is documented for use with static SQL or bind
   parameters; identifier interpolation requires `sqlalchemy.sql.expression.text`
   with explicit quoting via `sa.literal_column` or `sa.table`.

**Suggested fix**: Use `sqlalchemy.text` with fully-qualified literals kept
inside Python constants, not interpolated at runtime:

```python
from sqlalchemy import text, func, literal_column, table as sa_table, column

# Pre-validated constant mapping — never user-supplied
HEALTH_TABLES: list[tuple[str, str]] = [
    ("electricity_prices", "timestamp"),
    ...
]

for table_name, ts_col in HEALTH_TABLES:
    # Acceptable because both values are module-level constants, not request data.
    # Add a type-safe query builder if this ever needs to become dynamic.
    stmt = text(f"SELECT COUNT(*) FROM {table_name}")
    ...
```

At minimum, document that `table_name` and `ts_col` must never be derived from
request parameters, and add an assertion:

```python
assert table_name in {t for t, _ in HEALTH_TABLES}
assert ts_col in {c for _, c in HEALTH_TABLES}
```

---

### P0-03 · IDOR — async job results accessible by any authenticated user in `agent.py`

**File**: `backend/api/v1/agent.py`
**Lines**: 215–232 (`get_task_result`)

`GET /agent/task/{job_id}` retrieves an async job result from the in-memory
job store using only the `job_id`:

```python
async def get_task_result(
    job_id: str,
    current_user: SessionData = Depends(get_current_user),
) -> Dict[str, Any]:
    service = AgentService()
    result = await service.get_job_result(job_id)
    return result
```

`AgentService.get_job_result` (in `agent_service.py`) fetches from the in-memory
`_jobs` dict keyed by `job_id` only — it does **not** check that the requesting
user owns that job. Any authenticated user who knows (or can enumerate) another
user's `job_id` can retrieve their AI response, which may contain personal
energy usage data, supplier details, or financial information.

**Suggested fix**: Store the owning `user_id` alongside the job entry and verify
ownership in `get_job_result`:

```python
# In agent_service.py: _jobs[job_id] = {"user_id": user_id, "status": "processing", ...}

async def get_job_result(self, job_id: str, requesting_user_id: str) -> dict:
    job = self._jobs.get(job_id)
    if not job:
        return {"status": "not_found"}
    if job.get("user_id") != requesting_user_id:
        return {"status": "not_found"}  # don't reveal existence to other users
    return job
```

And in the route:

```python
result = await service.get_job_result(job_id, current_user.user_id)
```

---

### P0-04 · Race condition: free-tier alert limit check is non-atomic in `alerts.py`

**File**: `backend/api/v1/alerts.py`
**Lines**: 140–155 (`create_alert`)

The free-tier limit check is a classic TOCTOU (Time-of-Check / Time-of-Use)
race:

```python
count_result = await db.execute(
    text("SELECT COUNT(*) FROM user_alert_configs WHERE user_id = :id"),
    {"id": current_user.user_id},
)
alert_count = count_result.scalar() or 0
if alert_count >= 1:
    raise HTTPException(...)
# ... gap ...
alert = await service.create_alert(...)
```

Two concurrent `POST /alerts` requests from a free-tier user can both pass the
`alert_count >= 1` check simultaneously before either INSERT is committed, both
inserting successfully and leaving the user with 2+ alerts.

**Suggested fix**: Enforce the limit atomically inside the INSERT via a
constraint or a CTE guard:

```sql
WITH guard AS (
    SELECT COUNT(*) AS cnt
    FROM user_alert_configs
    WHERE user_id = :user_id
)
INSERT INTO user_alert_configs (...)
SELECT :user_id, ...
FROM guard
WHERE cnt < :limit
RETURNING id
```

Check whether the INSERT returned a row; raise 403 if not. This moves the
concurrency guard inside the database transaction where it can be enforced
atomically.

---

## P1 — High

### P1-01 · `context` dict from user request merged into system context without sanitisation in `agent.py`

**File**: `backend/api/v1/agent.py`
**Lines**: 121–123 (`query_agent`), 188–191 (`submit_agent_task`)

User-supplied `body.context` is merged **directly** into the system-built
context dict:

```python
context = await _get_user_context(current_user.user_id, db)
if body.context:
    context.update(body.context)
tier = context.get("tier", "free")
```

An attacker can supply `{"tier": "business"}` in the `context` field and
immediately read `tier = "business"` at line 123. The actual rate-limit check
uses this value:

```python
allowed, used, limit = await service.check_rate_limit(current_user.user_id, tier, db)
```

This allows a free-tier user to claim Business-tier query limits (200/day
instead of 3/day) by including `{"tier": "business"}` in the `context` body.

**Suggested fix**: Never allow user-supplied context to override security-
sensitive keys. Either:

```python
# Pull tier from DB, not from merged context
tier = await _get_user_tier(current_user.user_id, db)
# Then allow user context for non-sensitive keys only:
safe_context = {k: v for k, v in (body.context or {}).items()
                if k not in ("tier", "user_id", "subscription_tier")}
context.update(safe_context)
```

Or strip `tier` from context after the merge:

```python
context.update(body.context)
# Re-authoritative lookup — user cannot override this
tier = await _get_user_tier(current_user.user_id, db)
```

---

### P1-02 · `check_alerts` records `email_sent=True` for all alerts regardless of actual send outcome

**File**: `backend/api/v1/internal/alerts.py`
**Lines**: 152–168 (`check_alerts`)

The `check_alerts` endpoint calls `service.send_alerts(to_send)` which returns
a **count** of successful sends (not a per-item status list). It then iterates
`to_send` recording each with `email_sent=True`:

```python
sent = await service.send_alerts(to_send)
# sent is a count (int), not per-item success flags

for threshold, alert in to_send:
    try:
        await service.record_triggered_alert(
            ...
            email_sent=True,  # Always True — even if send_alerts returned 0!
            ...
        )
```

If `send_alerts` returns 0 (all emails failed), every alert is still recorded
with `email_sent=True`, which will suppress re-sending on the next run
(deduplication key includes the alert type and region). This silently suppresses
future alert deliveries for up to the cooldown window.

**Suggested fix**: Either refactor `send_alerts` to return a per-item success
list, or use a conservative `email_sent=False` default and only set `True` when
`sent > 0` and this is a 1:1 mapping:

```python
email_sent = (sent == len(to_send))  # conservative: only True if all succeeded
```

Better yet, have `send_alerts` return `list[bool]` corresponding to `to_send`.

---

### P1-03 · Free-tier alert limit uses `COUNT(*)` including inactive/deleted alerts

**File**: `backend/api/v1/alerts.py`
**Lines**: 146–151 (`create_alert`)

```python
count_result = await db.execute(
    text("SELECT COUNT(*) FROM user_alert_configs WHERE user_id = :id"),
    {"id": current_user.user_id},
)
```

This counts **all** records, including inactive alerts (`is_active = false`)
and soft-deleted ones. A user who creates 1 alert, deactivates it, and tries
to create another will be incorrectly blocked at the 1-alert limit even though
they have no active alerts. This is a usability bug that could cause support
confusion.

**Suggested fix**:

```sql
SELECT COUNT(*) FROM user_alert_configs
WHERE user_id = :id AND is_active = true
```

---

### P1-04 · `forecast.py` route passes unvalidated `utility_type` path parameter to service

**File**: `backend/api/v1/forecast.py`
**Lines**: 21–43 (`get_forecast`)

`utility_type` is a free-form string path parameter. The validation happens
inside `ForecastService.get_forecast()` (where it checks against
`FORECASTABLE_UTILITIES`). An invalid `utility_type` like `../../../etc/passwd`
does not cause a path traversal here, but the service raises a plain `Exception`
which FastAPI will return as a 500 rather than a 422, leaking internal error
details to the caller.

More significantly, as documented in the services audit (P0-02), `utility_type`
is ultimately interpolated into SQL table names inside `_forecast_from_table`.
The route should reject unknown values before they reach the service layer.

**Suggested fix**: Add a `Literal` type annotation or explicit validation:

```python
from typing import Literal
from services.forecast_service import FORECASTABLE_UTILITIES
from fastapi import Path

@router.get("/{utility_type}")
async def get_forecast(
    utility_type: str = Path(..., regex=r"^[a-z_]+$"),
    ...
):
    if utility_type not in FORECASTABLE_UTILITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown utility type '{utility_type}'. Supported: {sorted(FORECASTABLE_UTILITIES)}"
        )
```

---

### P1-05 · `neighborhood.py` accepts unvalidated `utility_type` query parameter

**File**: `backend/api/v1/neighborhood.py`
**Lines**: 24–37 (`neighborhood_compare`)

Both `region` and `utility_type` are accepted as free-form strings with no
validation and passed directly to `NeighborhoodService.get_comparison()`, which
uses them as SQL bind parameters (safe for values) but also uses `utility_type`
to filter rows in `user_savings`. An attacker can supply arbitrary strings as
`utility_type` and while they cannot inject SQL (bind params are used), they
can probe the existence of utility types and enumerate the schema.

More practically, the service will return an empty/null result for any unknown
`utility_type` string without indicating to the caller that the input was
invalid, which is a silent failure mode.

**Suggested fix**: Validate against the known utility type enum:

```python
VALID_UTILITY_TYPES = frozenset({
    "electricity", "natural_gas", "heating_oil",
    "propane", "community_solar", "water",
})

if utility_type not in VALID_UTILITY_TYPES:
    raise HTTPException(
        status_code=422,
        detail=f"Invalid utility_type. Must be one of: {sorted(VALID_UTILITY_TYPES)}"
    )
```

---

### P1-06 · `prices_sse.py` SSE connection limit is per-user but not per-IP for unauthenticated users

**File**: `backend/api/v1/prices_sse.py`
**Lines**: 34–67

The SSE connection limit (`_SSE_MAX_CONNECTIONS_PER_USER = 3`) is enforced by
`user_id` (via `require_tier("business")`). However, the increment happens
**before** the connection limit check:

```python
count = await _sse_incr(user_id)
if count > _SSE_MAX_CONNECTIONS_PER_USER:
    await _sse_decr(user_id)
    raise HTTPException(...)
```

The increment happens unconditionally on every request. If the Redis INCR
succeeds but the subsequent limit check path raises due to an unrelated error
(e.g., the `StreamingResponse` constructor raises), the counter is incremented
but `_sse_decr` may not be called. This can cause the connection count to drift
upward over time, eventually soft-locking the user out of SSE for up to 1 hour
(the safety TTL) even though they have fewer than 3 active connections.

**Suggested fix**: Use an atomic compare-and-increment pattern, or always ensure
`_sse_decr` is called via a `try/finally`:

```python
count = await _sse_incr(user_id)
if count > _SSE_MAX_CONNECTIONS_PER_USER:
    await _sse_decr(user_id)
    raise HTTPException(...)

# Decrement is now guaranteed even if StreamingResponse setup raises
try:
    return StreamingResponse(event_stream(), ...)
except Exception:
    await _sse_decr(user_id)
    raise
```

---

### P1-07 · `billing.py` webhook: bare `except Exception` exposes internal error detail in 500 response

**File**: `backend/api/v1/billing.py`
**Lines**: 396–401 (`handle_stripe_webhook`)

```python
except Exception as e:
    logger.error("webhook_processing_error", error=str(e))
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to process webhook",
    )
```

The detail string here is safe (generic). However, the bare `except Exception`
is positioned after both the `ValueError` (signature check) and
`stripe.error.StripeError` handlers, meaning any unexpected exception from
`handle_webhook_event` or `apply_webhook_action` silently returns 500. This
makes Stripe retry the webhook up to its retry budget (72 hours), potentially
causing duplicate subscription state changes if the underlying DB operation
was partially applied.

Specifically, `apply_webhook_action` calls `user_repo.update_tier()` inside the
webhook handler. If `update_tier` succeeds but a subsequent operation raises,
the tier update is committed but the webhook returns 500, causing Stripe to
retry and potentially attempt the update again.

**Suggested fix**: Wrap `apply_webhook_action` in its own try/except that
returns 200 regardless if the webhook was already processed (idempotent check),
or ensure the overall handler returns 200 once the event is verified, regardless
of downstream processing errors:

```python
# Always acknowledge receipt to Stripe once signature is valid
event = stripe_service.verify_webhook_signature(payload, signature)

# Process asynchronously or return 200 immediately with background task
try:
    result = await stripe_service.handle_webhook_event(event)
    if result["handled"]:
        await apply_webhook_action(result, user_repo, db=db)
except Exception as e:
    logger.error("webhook_apply_failed", event_id=event["id"], error=str(e))
    # Still return 200 to prevent Stripe retry of already-verified event

return WebhookEventResponse(received=True, event_id=event["id"])
```

---

## P2 — Medium

### P2-01 · `community.py` passes `agent_service=None` disabling AI moderation silently

**File**: `backend/api/v1/community.py`
**Lines**: 108 (`create_post`), 172 (`edit_post`)

Both `create_post` and `edit_post` pass `agent_service=None` to
`CommunityService`:

```python
post = await service.create_post(
    ...
    agent_service=None,  # Moderation auto-clears if no agent available
)
```

The comment says "Moderation auto-clears if no agent available" — meaning posts
skip AI moderation when no agent is wired in. This is intentional for the
current implementation but is a deployment risk: if `ENABLE_AI_AGENT=false` or
the agent key rotates, all community posts will bypass moderation entirely
without any warning or counter-measure.

**Suggested fix**: Log a warning when `agent_service=None` is used in
production:

```python
from config.settings import settings
if settings.environment == "production" and settings.enable_ai_agent:
    from services.agent_service import AgentService
    agent_svc = AgentService()
else:
    agent_svc = None
    if settings.environment == "production":
        logger.warning("community_moderation_disabled", reason="ai_agent_not_enabled")
```

---

### P2-02 · `agent.py` does not validate `job_id` format before looking up in job store

**File**: `backend/api/v1/agent.py`
**Lines**: 220–232 (`get_task_result`)

`job_id` is a free-form path parameter with no format validation. The in-memory
`_jobs` dict lookup is safe, but an attacker can supply arbitrarily long strings
(DoS via memory for repeated enumeration) or path-traversal-style strings if
the job store is ever migrated to a filesystem-based backend.

**Suggested fix**: Validate UUID format at the route level:

```python
import re
_JOB_ID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

async def get_task_result(job_id: str, ...):
    if not _JOB_ID_RE.match(job_id):
        return {"status": "not_found"}
```

---

### P2-03 · `connections/crud.py` PATCH builds dynamic SET clause from Pydantic fields

**File**: `backend/api/v1/connections/crud.py`
**Lines**: 284–298 (`update_connection`)

`update_connection` builds a SET clause by concatenating Pydantic field names
into an f-string:

```python
updates = []
params: dict = {"cid": connection_id}
if payload.label is not None:
    updates.append("label = :label")
    params["label"] = payload.label
...
await db.execute(
    text(f"UPDATE user_connections SET {', '.join(updates)} WHERE id = :cid"),
    params,
)
```

The only updatable field today is `label`, so there is no injection risk in
the current form. However, the pattern is the same one flagged in P0-01 for
`users.py`. If a developer adds a new field to `UpdateConnectionRequest`
without updating the allowlist guards, a sensitive column (e.g., `status`,
`connection_type`, `supplier_id`) could become unpermissioned-update accessible.

**Suggested fix**: Use explicit column name strings rather than Pydantic field
names, and assert no unrecognised field names can appear:

```python
PATCHABLE_COLS = {"label"}
# Only construct set clause from the known-safe set
```

---

### P2-04 · `data_pipeline.py` directly exposes `raw_results` from Diffbot in API response

**File**: `backend/api/v1/internal/data_pipeline.py`
**Lines**: 309–317 (`scrape_supplier_rates`)

```python
return {
    ...
    "results": raw_results,
}
```

`raw_results` is the full output from `RateScraperService.scrape_supplier_rates`,
which may include the Diffbot API response body. This could expose internal
supplier pricing data structures, rate patterns, or authentication tokens if
any appear in the extracted JSONB. Although this endpoint requires
`X-API-Key`, principle of least disclosure suggests returning a trimmed
summary.

**Suggested fix**: Strip sensitive JSONB before returning:

```python
"results": [
    {
        "supplier_id": r.get("supplier_id"),
        "success": r.get("success"),
        "rate_kwh": r.get("_detected_rate_kwh"),
    }
    for r in raw_results
],
```

---

### P2-05 · `check_alerts` hard-codes `email_sent=True` comment is misleading

**File**: `backend/api/v1/internal/alerts.py`
**Lines**: 158–162

The inline comment reads:

```python
# Mark email_sent conservatively; if sent < len(to_send)
# some emails failed but we don't have per-item status.
# Use True here — the send_alerts() logger captures failures.
```

Using `True` as the "conservative" choice is backwards from standard conservative
design: the conservative choice is `False` (assume not sent) to avoid
suppressing future sends. The current behaviour means failed sends are masked
from the deduplication check. This is the same underlying issue as P1-02 but
from a documentation correctness perspective the comment is directionally wrong.

**Suggested fix**: Change the comment and the default to `False` until per-item
send tracking is implemented:

```python
email_sent=False,  # Conservative: assume not sent until send API returns per-item status
```

---

### P2-06 · `prices.py` computes summary stats from page slice, not full result set

**File**: `backend/api/v1/prices.py`
**Lines**: 249–253 (`get_price_history`)

When prices are returned from the DB, the average/min/max are computed from
the current **page** only, not from the full result set:

```python
if prices:
    avg = sum(p.price_per_kwh for p in prices) / len(prices)
    avg_price = Decimal(str(round(avg, 4)))
    min_price = min(p.price_per_kwh for p in prices)
    max_price = max(p.price_per_kwh for p in prices)
```

For a user requesting page 2 of data for a 30-day window, the average/min/max
values will be computed from only 24 records on that page, not from all 720
records in the window. This can be misleading — the "average price" shown
changes as the user pages through results.

**Suggested fix**: Use the aggregate stats from the repository's SQL layer
(which returns stats over the full window), or at minimum document the
page-scoped behaviour clearly in the response schema and API docs:

```python
# Use full-window stats from DB aggregate instead of page stats
stats = await price_service.get_price_statistics(region, days)
avg_price = stats.get("avg_price")
```

---

### P2-07 · `billing.py` `PortalSessionRequest.return_url` validator duplicates `CheckoutSessionRequest` logic

**File**: `backend/api/v1/billing.py`
**Lines**: 37–51, 66–80

Both request models define an identical `validate_redirect_domain` classmethod.
This is a DRY violation: if `settings.allowed_redirect_domains` changes or the
validation logic is updated, both validators must be updated in sync. A missed
update could result in inconsistent domain allowlisting.

**Suggested fix**: Extract a shared base validator or standalone function:

```python
def _validate_redirect_url(v, allowed: list[str]) -> HttpUrl:
    parsed = urlparse(str(v))
    hostname = parsed.hostname or ""
    if not any(hostname == d or hostname.endswith(f".{d}") for d in allowed):
        raise ValueError(...)
    return v
```

---

### P2-08 · `community.py` `region` query parameter accepts any string without validation

**File**: `backend/api/v1/community.py`
**Lines**: 118–142 (`list_posts`), 226–233 (`community_stats`)

`region` is a free-form query string passed directly to `CommunityService` and
used as a SQL bind value. While bind parameters prevent injection, invalid
region strings (e.g., very long strings, special characters) will simply return
empty results without any feedback to the caller that the input was bad.

**Suggested fix**: Validate against the project's region enum or at minimum
add a length/format constraint:

```python
region: str = Query(
    description="Region code (e.g. 'us_ct')",
    min_length=2,
    max_length=20,
    regex=r'^[a-z0-9_]+$',
)
```

---

### P2-09 · `agent.py` increments usage counter before confirming streaming task completion

**File**: `backend/api/v1/agent.py`
**Lines**: 208–209 (`submit_agent_task`)

```python
job_id = await service.query_async(...)
# Increment usage now (async job already started)
await service.increment_usage(current_user.user_id, db)
```

Usage is incremented after `query_async` starts the background task but before
the task completes. If `query_async` raises (e.g., the job store is full),
the usage counter is not incremented. But if `increment_usage` raises after
`query_async` succeeds, the job runs without consuming a quota slot — the user
can retry until `increment_usage` reliably fails (e.g., DB degradation window)
to bypass daily limits.

The streaming endpoint (`query_agent`) does not call `increment_usage` at all —
usage tracking relies on the service's internal call within `query_streaming`.
The async task endpoint adds a duplicate increment, meaning each async task
call increments usage **twice** (once inside `query_async` via the background
task and once explicitly here), effectively halving the user's daily limit for
async tasks.

**Suggested fix**: Verify the increment path in `query_async` and remove the
explicit `increment_usage` call from the route if the background task already
handles it.

---

### P2-10 · `connections/email_oauth.py` OAuth callback does not validate `state` parameter expiry client-side

**File**: `backend/api/v1/connections/email_oauth.py`
**Lines**: 60+ (GET `/email/callback`)

The OAuth callback handler (not shown in the excerpt but present in the file)
should validate the `state` parameter against a time-limited store to prevent
CSRF and replay attacks. If the state store in `email_oauth_service.py` only
checks for presence (not expiry), replayed OAuth codes from expired sessions
could be accepted.

This is a partial concern — verification of the implementation would require
reading `email_oauth_service.py` in full — but the route should enforce
state expiry at the boundary.

**Suggested fix**: Document in the callback route that state expiry is enforced
(or add an explicit `created_at` check if not already present in the service).

---

## P3 — Low

### P3-01 · `auth.py` `logout` silently succeeds if Redis is unavailable

**File**: `backend/api/v1/auth.py`
**Lines**: 142–152 (`logout`)

```python
redis = None
try:
    redis = await db_manager.get_redis_client()
except Exception:
    pass
invalidated = await invalidate_session_cache(session_token, redis)
```

If Redis is unavailable, `redis` remains `None` and `invalidate_session_cache`
is called with `None`. The endpoint returns `{"status": "ok"}` regardless,
giving the client a false sense that the server-side session was invalidated.
In production, this means a user who logs out during a Redis outage retains an
active server-side cache entry for up to the TTL (60 seconds), potentially
allowing session fixation if the token is intercepted.

**Suggested fix**: Return a warning in the response if cache invalidation was
not possible (not an error — the user is still logged out client-side via
Better Auth):

```python
return {"status": "ok", "cache_cleared": invalidated, "cache_available": redis is not None}
```

---

### P3-02 · `forecast.py` returns route list with `set()` — unstable ordering

**File**: `backend/api/v1/forecast.py`
**Lines**: 54–58 (`list_forecast_types`)

```python
return {
    "supported_types": list(FORECASTABLE_UTILITIES),
    ...
}
```

`FORECASTABLE_UTILITIES` is a `set`. Converting a set to a list produces
non-deterministic ordering across Python versions. API consumers who render
this list in a UI will see inconsistent ordering between calls.

**Suggested fix**:

```python
"supported_types": sorted(FORECASTABLE_UTILITIES),
```

---

### P3-03 · `connections/portal_scan.py` uses sequential loop instead of documented asyncio.gather pattern

**File**: `backend/api/v1/internal/portal_scan.py`
**Lines**: 99–113

The docstring says "Run up to `_SEMAPHORE_LIMIT` scrapes concurrently via
`asyncio.gather` + `asyncio.Semaphore`", but the implementation uses a
sequential `for` loop with `await`:

```python
results = []
for row in rows:
    try:
        result = await _scrape_one(...)
        results.append(result)
    except Exception as exc:
        results.append(exc)
```

The same pattern appears in `email_scan.py`. The comment explains that
sequential execution is intentional to avoid shared `AsyncSession` corruption
— which is correct and the right choice. However, the docstring is misleading
(it describes `asyncio.gather` which is not used). The semaphore inside
`_scrape_one` provides external HTTP concurrency control for the sequential
design.

**Suggested fix**: Update the docstring to accurately describe the sequential
design:

```
# Connections are processed sequentially to avoid AsyncSession corruption.
# The Semaphore inside _scrape_one limits external HTTP concurrency to
# _SEMAPHORE_LIMIT regardless of the outer loop behaviour.
```

---

### P3-04 · `prices.py` mock fallback in `compare_prices` is triggered by raising `Exception` not just `HTTPException`

**File**: `backend/api/v1/prices.py`
**Lines**: 403–407 (`compare_prices`)

```python
if not prices:
    raise Exception("No prices from DB")
```

Raising a plain `Exception` to trigger the fallback code path (lines 434–465)
via the outer `except Exception as e` block is a code smell. It is invisible in
stack traces and conflates "no data" with "service failure". The fallback is
also triggered by legitimate errors (DB connection failure, etc.) producing mock
data in production.

The production gate at line 437 (`if settings.environment == "production":`)
correctly raises 503 in production, but the plain `Exception` approach means
the no-data case in development is handled identically to a real failure — both
log `using_mock_comparison` at WARNING level.

**Suggested fix**: Use a dedicated empty-data code path:

```python
if not prices:
    if settings.environment == "production":
        raise HTTPException(status_code=503, detail="No prices available")
    # Development fallback only
    return _mock_comparison_response(region)
```

---

### P3-05 · `savings.py` `GET /savings/combined` does not require any tier (inconsistent with `/summary`)

**File**: `backend/api/v1/savings.py`
**Lines**: 86–96 (`get_combined_savings`)

`GET /savings/summary` requires `pro` tier via `require_tier("pro")`.
`GET /savings/combined` only requires `get_current_user` — any authenticated
user (including free tier) can access it. Both endpoints return savings data;
the access control inconsistency may be intentional (combined view is broader
but less detailed) but is not documented.

**Suggested fix**: Add a comment or enforce the same tier requirement:

```python
current_user: SessionData = Depends(require_tier("pro")),  # Consistent with /summary
```

Or explicitly document why free users can access `/combined`.

---

### P3-06 · `data_pipeline.py` regex in `_extract_rate_from_diffbot_data` does not anchor to word boundary

**File**: `backend/api/v1/internal/data_pipeline.py`
**Lines**: 64–68

```python
rate_match = re.search(
    r"(?:rate|price|cost|charge)[:\s]*\$?([\d]+\.[\d]{2,4})\s*(?:/\s*)?(?:per\s+)?(?:kWh|kwh|KWH)",
    text_content,
    re.IGNORECASE,
)
```

The pattern matches `charge` which would also match `surcharge`. A text like
"surcharge: $0.12/kWh (distribution fee)" would match `rge: $0.12/kWh` if the
regex engine finds `charge` within `surcharge`, potentially extracting a
surcharge as the main rate.

**Suggested fix**: Add a word boundary:

```python
r"(?<!\w)(?:rate|price|cost|charge)[:\s]*\$?([\d]+\.[\d]{2,4})\s*(?:/\s*)?(?:per\s+)?(?:kWh|kwh|KWH)"
```

---

## Strengths

The routes layer is generally well-structured. Notable positives:

- **Redirect URL validation** in `billing.py` is correct — both checkout and
  portal session URLs are validated against `allowed_redirect_domains` with
  subdomain support.
- **Webhook signature verification** in `billing.py` and `webhooks.py` uses
  constant-time comparison (`hmac.compare_digest`) and rejects missing headers
  early. The raw body is read before Pydantic parsing (correct for HMAC).
- **Free-tier alert limit** in `alerts.py` is a good pattern even if the
  specific implementation has the race condition noted in P0-04.
- **Connection route ordering** in `connections/router.py` is carefully
  documented and correct — static paths are registered before wildcards to
  prevent route capture bugs.
- **Parameterized SQL** is used in the vast majority of routes. The f-string
  injections (P0-01, P0-02) are the exception rather than the rule.
- **Sequential loop in email/portal scan** correctly avoids shared-session
  corruption, even though this differs from the documented pattern.
- **SSE connection tracking** uses Redis with in-memory fallback and an
  auto-expire safety TTL — a well-considered resilience design.
