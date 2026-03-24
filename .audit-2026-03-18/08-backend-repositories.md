# Audit Report 08 — Backend Repositories, Models & Database Interaction Patterns

**Date**: 2026-03-18
**Auditor**: Claude Code (automated read-only audit)
**Scope**: `backend/repositories/`, `backend/models/`, DB interaction patterns in `backend/services/`

---

## Executive Summary

The repository layer is well-structured — it avoids ORM/Pydantic conflicts through raw SQL `text()` throughout. SQL injection risk from user input is low due to consistent parameterization. The dominant risks are (1) a missing transaction boundary in the dunning flow that leaves payment records uncommitted before an early return, (2) a SQL injection vector in `feature_flag_service.py` where field names are assembled via f-string from constant lists but the pattern is not guarded against, (3) several services that commit partially without rollback on exceptions, (4) two concrete missing-index gaps for high-frequency queries on `payment_retry_history` and `alert_history`, and (5) the `_USER_COLUMNS` sentinel silently omitting `consent_given`, `consent_date`, and `data_processing_agreed` from every SELECT, causing silent GDPR data loss on reads.

---

## P0 — Critical (Data Loss, Security, Crashes)

### P0-01: `_USER_COLUMNS` Silently Excludes GDPR Consent Fields on Every User SELECT

**File**: `backend/repositories/user_repository.py`, lines 23–33
**Check**: Model-schema mismatch (#8)

The column list used in every `SELECT` in `UserRepository` is:

```python
_USER_COLUMNS = """
    id::text, email, name, region, preferences,
    current_supplier, is_active, is_verified,
    created_at, updated_at,
    stripe_customer_id, subscription_tier,
    email_verified, current_tariff,
    average_daily_kwh, household_size,
    current_supplier_id::text,
    utility_types, annual_usage_kwh,
    onboarding_completed
"""
```

The `User` Pydantic model (`backend/models/user.py`, lines 97–99) declares:

```python
consent_given: bool = False
consent_date: Optional[datetime] = None
data_processing_agreed: bool = False
```

`consent_given`, `consent_date`, and `data_processing_agreed` are **never included in any SELECT query** (`get_by_id`, `get_by_email`, `get_by_stripe_customer_id`, `get_users_by_region`, `list`, `update`, all `RETURNING` clauses).

The `_row_to_user` converter (line 67–69) silently defaults these to `False`/`None` on every read:

```python
consent_given=data.get("consent_given", False),
consent_date=data.get("consent_date"),
data_processing_agreed=data.get("data_processing_agreed", False),
```

**Impact**:
- `require_gdpr_consent` model validator on `UserCreate` correctly enforces consent — but after the user is created, any subsequent read returns `consent_given=False` and `data_processing_agreed=False` regardless of what was written to the DB.
- `record_consent()` correctly writes these columns (line 386–399), but any code path that reads the user object afterwards will see stale `False` values.
- Any GDPR compliance check relying on `user.consent_given` reads stale data.
- The `update()` method's `_UPDATABLE_COLUMNS` frozenset (line 177–186) includes neither `consent_given` nor `consent_date` nor `data_processing_agreed`, so they can never be updated through the normal `update()` path.

**Fix**: Add `consent_given, consent_date, data_processing_agreed` to `_USER_COLUMNS`, and add them to `_UPDATABLE_COLUMNS`.

---

### P0-02: SQL Injection Vector in `FeatureFlagService.update_flag()`

**File**: `backend/services/feature_flag_service.py`, lines 106–124
**Check**: SQL injection vulnerabilities (#1)

```python
set_parts: list[str] = []
params: dict = {"name": name}

if enabled is not None:
    set_parts.append("enabled = :enabled")
    params["enabled"] = enabled
if tier_required is not None:
    set_parts.append("tier_required = :tier_required")
    params["tier_required"] = tier_required
if percentage is not None:
    set_parts.append("percentage = :percentage")
    params["percentage"] = percentage

set_parts.append("updated_at = NOW()")
sql = f"UPDATE feature_flags SET {', '.join(set_parts)} WHERE name = :name"
await self._db.execute(text(sql), params)
```

The `set_parts` list items are literal string constants — not user-supplied values — so there is no actual injection risk from the column names themselves. However, the **`name` parameter** used in `WHERE name = :name` is passed through from the API caller without validation. If a caller supplies a crafted `name` with a SQL delimiter, SQLAlchemy's `text()` parameterization protects the value. The structural risk here is that the `set_parts.append("updated_at = NOW()")` is always appended regardless of whether any caller-controlled fields were added — but since all caller-controlled values flow through `:param` placeholders, there is no actual injection.

**Downgrade to P2**: The pattern is structurally sound — all user values flow through named parameters. However, the `name` parameter is not validated against the set of actual flag names before the UPDATE runs, meaning a call with any string `name` silently succeeds with 0 rows affected. There is no existence check or 404 on the UPDATE. This is a logic bug, not a security issue.

**Actual P0 reclassification**: No exploitable SQL injection exists in this file due to parameterization.

---

### P0-03: Partial Commit in `DunningService.handle_payment_failure()` Without Rollback Guard

**File**: `backend/services/dunning_service.py`, lines 321–387
**Check**: Missing transaction management (#2)

```python
async def handle_payment_failure(self, ...):
    # 1. Record the failure — inserts a row but does NOT commit yet
    record = await self.record_payment_failure(...)

    # Commit the payment failure record before any early returns
    await self._db.commit()   # line 338 — first explicit commit

    # 2. Cooldown check — if inside cooldown, returns immediately
    should_send = await self.should_send_dunning(user_id, stripe_invoice_id)
    if not should_send:
        return result          # ← returns here; fine, commit already happened

    # 3. Send email
    email_sent = await self.send_dunning_email(...)

    # 4. Mark email sent
    if email_sent and record.get("id"):
        await self._db.execute(text("UPDATE payment_retry_history SET email_sent = TRUE ..."))

    # 5. Escalate
    escalation = await self.escalate_if_needed(...)
    if escalation and record.get("id"):
        await self._db.execute(text("UPDATE payment_retry_history SET escalation_action = ..."))

    await self._db.commit()   # line 387 — final commit for steps 4+5
```

`record_payment_failure()` (line 60–105) does NOT commit inside itself — it just executes the INSERT and returns. The comment on line 337 says "Commit the payment failure record before any early returns" — this is correct behavior.

However, **steps 4 and 5 have no `try/except` with `rollback`**. If the step-4 UPDATE or step-5 escalation UPDATE raises an exception between lines 363–386 and line 387, the email marking and escalation writes are left in an open transaction that the session manager may rollback or leave dirty for subsequent requests, depending on how the FastAPI `get_db` dependency is implemented.

**Impact**: If a database error occurs during `email_sent` or `escalation_action` update, the uncommitted row state could corrupt the next request that reuses the same session without explicit rollback.

**Fix**: Wrap steps 4+5 in `try/except Exception: await self._db.rollback(); raise`.

---

## P1 — High (Broken Functionality, Data Integrity)

### P1-01: `PriceRepository.update()` Performs an Extra SELECT Before Every UPDATE

**File**: `backend/repositories/price_repository.py`, lines 179–229
**Check**: N+1 query patterns (#3)

```python
async def update(self, id: str, entity: Price) -> Optional[Price]:
    existing = await self.get_by_id(id)   # SELECT query first
    if not existing:
        return None
    await self._db.execute(text("UPDATE ..."))
    await self._db.commit()
    ...
    return await self.get_by_id(id)       # SELECT again after update
```

Every `update()` executes 3 round-trips: `get_by_id` (pre-check), `UPDATE`, and another `get_by_id` (post-fetch). The final `get_by_id` re-read is unnecessary because the `UPDATE ... RETURNING *` pattern is already established in `UserRepository.update()`. The pre-check also creates a TOCTOU window: the row could be deleted between the `get_by_id` and the `UPDATE`.

**Fix**: Remove the pre-check `get_by_id`. Use `UPDATE ... RETURNING {_PRICE_COLUMNS}` and return `None` if `rowcount == 0`. This reduces the path from 3 round-trips to 1.

---

### P1-02: `UtilityAccountRepository.create()` Passes `account_number_encrypted` Without Rollback Guard on Failure

**File**: `backend/repositories/utility_account_repository.py`, lines 58–86
**Check**: Missing error handling (#6), Missing transaction management (#2)

The `_COLUMNS` constant used in `RETURNING` (line 19–22) does **not include** `account_number_encrypted`:

```python
_COLUMNS = (
    "id, user_id, utility_type, region, provider_name, "
    "is_primary, metadata, created_at, updated_at"
)
```

But the `INSERT` (line 62–79) writes `account_number_encrypted`:

```python
"INSERT INTO utility_accounts "
"(id, user_id, utility_type, region, provider_name, "
"account_number_encrypted, is_primary, metadata) "
"VALUES (:id, :user_id, :utility_type, :region, :provider_name, "
":account_number_encrypted, :is_primary, :metadata::jsonb) "
f"RETURNING {_COLUMNS}"
```

The `RETURNING` clause does not return `account_number_encrypted` so the returned `UtilityAccount` object always has `account_number_encrypted=None`. This is intentional for security (do not echo encrypted bytes to callers), but:

1. The `_row_to_account` function (line 25–37) instantiates `UtilityAccount` without `account_number_encrypted`, which means the returned model silently lacks the field even though it was persisted.
2. More critically: there is a mismatch — `UtilityAccount.account_number_encrypted: Optional[bytes]` is the model field, but the `INSERT` passes it as a raw bytes value. The asyncpg driver needs the `::bytea` cast, but no cast is applied. For Postgres this may cause a silent encoding issue or driver-level error on binary data.

**Also**: The `except` block (line 84–86) catches all `Exception` and rolls back — this is correct. But the `commit()` on line 81 and the `rollback()` on line 85 are adjacent without a `try/finally` pattern, meaning if `rollback()` itself raises, the session remains in a bad state.

---

### P1-03: `CommunityService._run_moderation()` Uses Stale Session After `db.commit()` in Parent

**File**: `backend/services/community_service.py`, lines 97–112
**Check**: Incorrect SQLAlchemy async patterns (#7)

```python
# In create_post():
result = await db.execute(insert_sql, params)
post = dict(result.mappings().fetchone())
await db.commit()             # ← commit closes the transaction

# ... immediately after:
post_id = post["id"]
try:
    await asyncio.wait_for(
        self._run_moderation(db, post_id, ...),  # ← passes same session
        timeout=MODERATION_TIMEOUT_SECONDS,
    )
```

After `await db.commit()` (line 95), the SQLAlchemy `AsyncSession` starts a new implicit transaction. `_run_moderation` then uses the same session to execute `UPDATE community_posts ...` and `await db.commit()` again (line 170). This is technically valid in SQLAlchemy autobegin mode, but it is fragile: if the `asyncio.wait_for` times out and the `_clear_pending_moderation` fallback at line 111 is called, **two coroutines are using the same `AsyncSession` in overlapping fashion** — the timeout-cancelled `_run_moderation` may have a pending state on the session while `_clear_pending_moderation` tries to use it.

From the SQLAlchemy docs: an `AsyncSession` is not safe for concurrent use. When `asyncio.wait_for` raises `TimeoutError`, the moderation coroutine is cancelled but the session may have a partially executed statement buffered internally. The `_clear_pending_moderation` call that follows then uses the same session — this can result in `InvalidRequestError` or a silent no-op.

**Fix**: Use a separate dedicated session for `_run_moderation` / `_clear_pending_moderation`, or use `async with db.begin_nested()` savepoints to isolate moderation from the post-creation transaction.

---

### P1-04: `AlertService.create_alert()` Commits But Does Not Rollback on `PermissionError`/`ValueError`

**File**: `backend/services/alert_service.py`, lines 697–744
**Check**: Missing transaction management (#2)

```python
tier_result = await db.execute(
    text("SELECT subscription_tier FROM public.users WHERE id = :id FOR UPDATE"),
    {"id": user_id},
)
user_tier = tier_result.scalar_one_or_none() or "free"
if user_tier not in ("pro", "business"):
    count_result = await db.execute(...)
    alert_count = count_result.scalar() or 0
    if alert_count >= 1:
        raise PermissionError(...)  # ← raises without rollback

result = await db.execute(text("INSERT INTO price_alert_configs ..."))
await db.commit()
```

When `PermissionError` is raised at line 715, the `FOR UPDATE` lock on the user row is held in an uncommitted transaction. The session is not rolled back, so the lock persists until the session is closed by FastAPI's dependency injection teardown. Under high concurrency, concurrent requests for the same user may queue behind this lock unnecessarily.

**Fix**: Add `try/except` wrapping with `await db.rollback()` before re-raising `PermissionError` or `ValueError`.

---

### P1-05: `ForecastObservationRepository.insert_recommendation()` Has No Rollback on Failure

**File**: `backend/repositories/forecast_observation_repository.py`, lines 172–193
**Check**: Missing error handling (#6)

```python
async def insert_recommendation(self, ...) -> str:
    outcome_id = str(uuid4())
    query = text("INSERT INTO recommendation_outcomes ...")
    await self._db.execute(query, {...})
    await self._db.commit()
    return outcome_id
```

There is no `try/except` with `rollback`. If the `execute` call raises (e.g., FK violation, unique constraint), `commit()` will not be called and the session is left in a state with an uncommitted transaction. Depending on whether FastAPI's `get_db` dependency rolls back on exception exit, this may or may not self-heal — but it is inconsistent with every other repository write method.

---

### P1-06: `MaintenanceService.cleanup_expired_uploads()` Has TOCTOU Window with Non-Atomic Delete

**File**: `backend/services/maintenance_service.py`, lines 63–106
**Check**: Race conditions (#5), Missing transaction management (#2)

```python
# SELECT old uploads
result = await self._db.execute(
    text("SELECT id, file_path FROM bill_uploads WHERE created_at < :cutoff"),
    {"cutoff": cutoff},
)
old_uploads = result.fetchall()

# DELETE extracted rates (FK)
await self._db.execute(text("DELETE FROM connection_extracted_rates WHERE bill_upload_id = ANY(:ids)"), ...)

# DELETE upload records
await self._db.execute(text("DELETE FROM bill_uploads WHERE created_at < :cutoff"), ...)
await self._db.commit()

# File system cleanup (post-commit)
for row in old_uploads:
    os.remove(row[1])
```

Between the `SELECT` and the two `DELETE` statements, new `connection_extracted_rates` rows could be inserted referencing those `bill_upload_id`s by a concurrent upload request. The two-step delete (rates first, then uploads) is correct for FK ordering, but the gap between SELECT and DELETE creates a TOCTOU window.

More critically: **file system cleanup happens after `db.commit()`**. If any `os.remove()` call fails (e.g., file was already deleted externally), the DB rows are already committed as deleted — this is acceptable (files are best-effort) — but the inverse is also true: if the DB commit fails, the files are not deleted but the code will still attempt `os.remove()` on the next run... except the IDs will not show up in the next SELECT because the cutoff has moved forward. Orphaned files may accumulate.

---

### P1-07: `NotificationService.create()` Has No Rollback on Failure

**File**: `backend/services/notification_service.py`, lines 19–35
**Check**: Missing error handling (#6)

```python
async def create(self, user_id, title, body=None, type="info") -> None:
    await self._db.execute(
        text("INSERT INTO notifications ..."),
        {...},
    )
    await self._db.commit()
```

No `try/except`. If `execute()` raises (e.g., FK violation if `user_id` doesn't exist), `commit()` is never called and the session carries a dirty transaction. Callers of `create()` assume notification creation is fire-and-forget, so exceptions will propagate up unexpectedly.

---

### P1-08: `SavingsService.get_savings_summary()` Uses f-String SQL with `region_clause` Variable

**File**: `backend/services/savings_service.py`, lines 59–103
**Check**: SQL injection vulnerabilities (#1)

```python
region_clause = ""
if region:
    region_clause = " AND region = :region"
    base_params["region"] = region

combined_sql = text(f"""
    WITH agg AS (
        ...
        WHERE user_id = :user_id
        {region_clause}          ← interpolated into SQL string
    ),
    ...
    active_days AS (
        ...
        WHERE user_id = :user_id
          AND created_at >= NOW() - INTERVAL '365 days'
        {region_clause}          ← same clause interpolated twice
    )
    ...
""")
```

`region_clause` is a constant string `" AND region = :region"` — the **actual `region` value** flows through the named parameter `:region`, not through the f-string. This is safe. However, the structural pattern of interpolating SQL fragments via f-string is a code smell that could be accidentally broken by future maintainers who add non-parameterized values to `region_clause`.

**Downgrade to P2 (pattern risk, not active vulnerability).**

---

### P1-09: `apply_webhook_action()` in `stripe_service.py` Has a Double SELECT for `payment_failed`

**File**: `backend/services/stripe_service.py`, lines 501–584
**Check**: N+1 query patterns (#3)

```python
if not user_id and action == "payment_failed" and result.get("customer_id"):
    resolved = await user_repo.get_by_stripe_customer_id(customer_id_for_lookup)
    if resolved:
        user_id = str(resolved.id)
    ...

user = await user_repo.get_by_id(user_id)   # ← second SELECT

# Further in the payment_failed branch:
elif action == "payment_failed":
    if db is not None:
        ...
        user = await user_repo.get_by_id(user_id)   # ← third SELECT (line 561)
        user_email = user.email if user else ""
```

For the `payment_failed` path, 3 user SELECTs are made:
1. `get_by_stripe_customer_id()` — resolves user from customer ID
2. `get_by_id(user_id)` — unconditional fetch at line 541
3. `get_by_id(user_id)` — again inside the `payment_failed` branch at line 561

The third fetch is completely redundant — `user` from line 541 is already in scope. This is a performance issue on every payment failure webhook, which is already a high-stakes code path.

---

## P2 — Medium (Performance, Maintainability)

### P2-01: `UserRepository.update()` Builds Dynamic SQL with f-String Field Names (Injection Pattern Risk)

**File**: `backend/repositories/user_repository.py`, lines 188–232
**Check**: SQL injection (#1)

```python
set_clauses = []
params: Dict[str, Any] = {"user_id": id}
for field, value in updates.items():
    param_name = f"p_{field}"
    if field == "preferences":
        set_clauses.append(f"{field} = :{param_name}::jsonb")
    ...
    set_clauses.append(f"{field} = :{param_name}")
    params[param_name] = value

set_sql = ", ".join(set_clauses)
result = await self._db.execute(
    text(f"UPDATE users SET {set_sql} WHERE id = :user_id RETURNING {_USER_COLUMNS}"),
    params,
)
```

The field names are interpolated directly into SQL. This is guarded by the `_UPDATABLE_COLUMNS` frozenset whitelist at line 198:

```python
updates = {k: v for k, v in updates.items() if k in self._UPDATABLE_COLUMNS}
```

The frozenset provides effective injection prevention for field names. **Values** all flow through named parameters. This is safe, but the pattern is fragile — any code path that calls this method with `exclude_unset=False` on a model containing extra fields would be filtered but not flagged.

**Severity**: P2 pattern risk (not exploitable with current whitelist).

---

### P2-02: Missing Index on `payment_retry_history(user_id, stripe_invoice_id)`

**File**: `backend/migrations/024_payment_retry_history.sql` (referenced)
**Check**: Missing indexes (#4)

`DunningService.should_send_dunning()` queries:

```sql
SELECT email_sent_at FROM payment_retry_history
WHERE user_id = :user_id
  AND stripe_invoice_id = :invoice_id
  AND email_sent = TRUE
  AND email_sent_at >= :cutoff
```

`DunningService.get_retry_count()` queries:

```sql
SELECT COUNT(*) FROM payment_retry_history
WHERE stripe_invoice_id = :invoice_id
```

`DunningService.get_overdue_accounts()` queries:

```sql
SELECT DISTINCT ON (prh.user_id) ...
FROM payment_retry_history prh
JOIN public.users u ON u.id = prh.user_id
WHERE prh.created_at <= :cutoff
  AND u.subscription_tier != 'free'
ORDER BY prh.user_id, prh.created_at DESC
```

No migration creates an index on `payment_retry_history(user_id, stripe_invoice_id)` or `payment_retry_history(stripe_invoice_id)` or `payment_retry_history(created_at)`. The existing migrations (`020`, `036`, `037`) do not cover this table. As payment failures accumulate, these queries will do full-table scans.

**Fix**: Add:
```sql
CREATE INDEX IF NOT EXISTS idx_payment_retry_user_invoice
    ON payment_retry_history (user_id, stripe_invoice_id, email_sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_retry_created
    ON payment_retry_history (created_at DESC);
```

---

### P2-03: Missing Index on `recommendation_outcomes(user_id)` and `forecast_observations(forecast_id)`

**File**: `backend/repositories/forecast_observation_repository.py`
**Check**: Missing indexes (#4)

`ForecastObservationRepository` batch-inserts rows into `forecast_observations` keyed on `forecast_id`, and `recommendation_outcomes` keyed on `user_id`. While `backfill_actuals` uses an efficient CTE, `update_recommendation_response` queries:

```sql
WHERE id = :outcome_id AND responded_at IS NULL
```

And `get_accuracy_metrics` / `get_hourly_bias` / `get_accuracy_by_version` all filter by `region` and `created_at`. Migration 036 creates `idx_alert_history_dedup` but does not add indexes on these tables.

**Recommended**:
```sql
CREATE INDEX IF NOT EXISTS idx_forecast_obs_region_created
    ON forecast_observations (region, created_at DESC)
    WHERE observed_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rec_outcomes_user_id
    ON recommendation_outcomes (user_id, created_at DESC);
```

---

### P2-04: `AlertService.get_active_alert_configs()` Hard-Codes `LIMIT 5000` Without Pagination

**File**: `backend/services/alert_service.py`, lines 514–551
**Check**: Performance (#3)

```sql
SELECT ... FROM price_alert_configs pac
JOIN public.users u ON u.id = pac.user_id
WHERE pac.is_active = TRUE
  AND u.is_active   = TRUE
ORDER BY pac.created_at
LIMIT 5000
```

This is a safety cap but as user count grows, `get_active_alert_configs` will load up to 5,000 full config+user rows into Python memory at once. The check-alerts cron calls this, constructs all `AlertThreshold` objects in-memory, then calls the batch dedup check. For a growing user base this pattern will cause memory pressure on Render's free tier (512 MB).

**Fix**: Process in pages of 500 or use a cursor/keyset approach.

---

### P2-05: `CommunityService.retroactive_moderate()` Loads All Posts From Last 24 Hours Without Limit

**File**: `backend/services/community_service.py`, lines 440–450
**Check**: Performance, missing limit (#3)

```sql
SELECT id, title, body FROM community_posts
WHERE is_pending_moderation = false
  AND is_hidden = false
  AND hidden_reason IS NULL
  AND created_at >= NOW() - INTERVAL '24 hours'
ORDER BY created_at ASC
```

No `LIMIT` clause. If 10,000 posts are created in a 24-hour window (possible during a viral event or spam attack), this loads all rows into memory and spawns 10,000 AI classification tasks (capped to 5 concurrent by the semaphore, but still memory-intense for the result list).

---

### P2-06: `DunningService.get_overdue_accounts()` Uses `DISTINCT ON` Without Supporting Index

**File**: `backend/services/dunning_service.py`, lines 391–422
**Check**: Missing indexes (#4)

```sql
SELECT DISTINCT ON (prh.user_id)
    prh.user_id, ...
FROM payment_retry_history prh
JOIN public.users u ON u.id = prh.user_id
WHERE prh.created_at <= :cutoff
  AND u.subscription_tier != 'free'
  AND u.is_active = TRUE
ORDER BY prh.user_id, prh.created_at DESC
```

`DISTINCT ON (prh.user_id)` requires ordering by `prh.user_id` first, then `prh.created_at DESC`. Without an index on `payment_retry_history(user_id, created_at DESC)`, this query requires a sort across all rows matching the cutoff. The `ORDER BY prh.user_id, prh.created_at DESC` cannot use a simple `created_at` index for both conditions simultaneously.

---

### P2-07: `UserRepository.get_users_by_region()` Returns Up to 5,000 Full User Objects in Memory

**File**: `backend/repositories/user_repository.py`, lines 425–450
**Check**: Performance (#3)

```python
async def get_users_by_region(self, region: str, active_only: bool = True) -> List[User]:
    ...
    result = await self._db.execute(
        text(f"SELECT {_USER_COLUMNS} FROM users WHERE {where_clause} LIMIT 5000"),
        {"region": region.lower()},
    )
    rows = result.mappings().all()
    return [_row_to_user(row) for row in rows]
```

This method is called to build `AlertThreshold` objects for the check-alerts cron. Loading 5,000 full `User` objects (with all their preference JSON) is memory-intensive. For the alert-checking use case only `user_id`, `email`, and `preferences->>'notification_frequency'` are needed — as already demonstrated by `get_active_alert_configs()` which fetches only those columns. The `get_users_by_region()` method is redundant and overfetches for its known callers.

---

### P2-08: `SupplierRegistryRepository.list_suppliers()` Runs Two Sequential Queries (COUNT + SELECT)

**File**: `backend/repositories/supplier_repository.py`, lines 128–221
**Check**: Performance (#3)

```python
count_result = await self._db.execute(text(count_sql), params)
total = count_result.scalar() or 0

result = await self._db.execute(text(data_sql), data_params)
rows = result.mappings().all()
```

Two sequential queries instead of `COUNT(*) OVER()` window function. For a table that is cached for 1 hour this is only a cold-path issue, but the pattern is inconsistent with `CommunityService.list_posts()` which correctly uses `COUNT(*) OVER()`.

---

### P2-09: `ModelConfigRepository.save_config()` Does Not Handle Concurrent Writes (Single-Writer Assumption Documented but Not Enforced)

**File**: `backend/repositories/model_config_repository.py`, lines 115–202
**Check**: Race conditions (#5)

```python
# Step 1: deactivate existing active configs
await self._db.execute(
    text("UPDATE model_config SET is_active = false ... WHERE model_name = :model_name AND is_active = true"),
    ...
)

# Step 2: insert the new active row
await self._db.execute(
    text("INSERT INTO model_config ... VALUES ..."),
    ...
)

await self._db.commit()
```

The docstring notes "single-writer assumption". If two learning processes run concurrently (e.g., a manual trigger overlaps with a scheduled run), both could pass the `UPDATE` step and then both `INSERT` new rows. The second `INSERT` would succeed, leaving two active rows despite the deactivation in step 1 (since step 1 only deactivates rows that were active *before* this transaction started — the other process's new row is not yet visible).

**Fix**: Use `SELECT ... FOR UPDATE` to lock the active row, or use a database unique partial index on `(model_name) WHERE is_active = TRUE`.

---

### P2-10: `NotificationRepository.update_delivery()` Builds Dynamic SQL with Varying `set_clauses` (Fragile Pattern)

**File**: `backend/repositories/notification_repository.py`, lines 188–257
**Check**: SQL injection risk pattern (#1)

```python
set_clauses: List[str] = ["delivery_status = :delivery_status"]
params: Dict[str, Any] = {"nid": notification_id, "delivery_status": update.delivery_status}

if update.delivery_channel is not None:
    set_clauses.append("delivery_channel = :delivery_channel")
    params["delivery_channel"] = update.delivery_channel
...
sql = (
    "UPDATE notifications"
    " SET " + ", ".join(set_clauses) +
    " WHERE id = :nid"
)
result = await self._db.execute(text(sql), params)
await self._db.commit()
```

All set clause fragments are hardcoded string literals — not user-controlled. Values flow through named parameters. This is safe. No rollback on exception. If `execute()` raises, `commit()` is skipped and the session carries a dirty transaction.

---

### P2-11: `ForecastObservationRepository.insert_forecasts()` Commits Once Outside Loop But Has No Rollback

**File**: `backend/repositories/forecast_observation_repository.py`, lines 64–97
**Check**: Missing transaction management (#2)

```python
for chunk_start in range(0, len(rows), self._INSERT_BATCH_SIZE):
    ...
    await self._db.execute(text("INSERT INTO forecast_observations ..."), params)

await self._db.commit()   # single commit after all chunks
```

No `try/except` wrapping the loop or the commit. If any intermediate chunk `execute()` fails, the session is left with committed partial chunks from earlier iterations that were flushed but not committed — wait, actually SQLAlchemy autoflush does not commit until `commit()` is called. However, if the last `commit()` fails, all inserted chunks are rolled back atomically. This is correct behavior, but without `try/except + rollback`, the exception propagates without releasing the connection cleanly.

---

### P2-12: `price_repository.bulk_create()` Does Not Use `INSERT ... ON CONFLICT DO NOTHING`

**File**: `backend/repositories/price_repository.py`, lines 612–670
**Check**: Race conditions (#5)

```python
await self._db.execute(
    text(
        "INSERT INTO electricity_prices "
        "(id, region, supplier, price_per_kwh, ...) "
        f"VALUES {', '.join(placeholders)}"
    ),
    params,
)
await self._db.commit()
```

If the price sync cron runs while a previous run is still in progress (e.g., CF Worker cron overlaps with a manual trigger), duplicate rows could be inserted for the same `(region, supplier, timestamp)`. There is no `ON CONFLICT` clause. The `id` column is a UUID generated at call time, so the PK conflict won't trigger — but if there is a unique constraint on `(region, supplier, timestamp)` it would raise an exception and roll back the entire batch.

**Checking migration 020**: The indexes are on `(region, supplier, created_at)` and `(region, utility_type, created_at)` — not unique constraints. So duplicate data rows can be silently inserted. This degrades analytics accuracy (double-counting).

---

## P3 — Low (Style, Minor Improvements)

### P3-01: `_row_to_user()` Uses `datetime.now(timezone.utc)` as Fallback for Missing DB Timestamps

**File**: `backend/repositories/user_repository.py`, lines 70–71

```python
created_at=data.get("created_at", datetime.now(timezone.utc)),
updated_at=data.get("updated_at", datetime.now(timezone.utc)),
```

If `created_at` or `updated_at` are `None` in the row (which should never happen for NOT NULL columns), they default to the current time at the moment of object construction. This would mask data quality issues. A missing-column should raise rather than silently substitute.

---

### P3-02: `_row_to_user()` Has a Silent Default for Missing `id`

**File**: `backend/repositories/user_repository.py`, line 49

```python
id=data.get("id", str(uuid4())),
```

If the `id` column were somehow absent, a new UUID is generated. A row without a PK is a data corruption signal and should raise immediately.

---

### P3-03: `StateRegulationRepository.get_by_state()` Uses `SELECT *`

**File**: `backend/repositories/supplier_repository.py`, line 294

```python
result = await self._db.execute(
    text("SELECT * FROM state_regulations WHERE state_code = :code"),
    {"code": state_code.upper()},
)
```

`SELECT *` fetches all columns including any future columns added to the table. This is a maintenance risk — schema changes silently add unexpected columns to the result set. Enumerate the needed columns explicitly.

---

### P3-04: `FeatureFlagService.update_flag()` Does Not Check Row Existence Before UPDATE

**File**: `backend/services/feature_flag_service.py`, lines 93–127
**Check**: Missing error handling (#6)

```python
await self._db.execute(text(sql), params)
await self._db.commit()
return True
```

Returns `True` even if the UPDATE matched 0 rows (flag name does not exist). The caller receives `True` indicating success when no update was actually applied. Should check `result.rowcount > 0`.

---

### P3-05: `SavingsService.get_savings_history()` Runs Two Sequential Queries (COUNT + Paginated SELECT) Instead of Window Function

**File**: `backend/services/savings_service.py`, lines 157–186
**Check**: Performance (#3)

```python
count_result = await self.db.execute(
    text("SELECT COUNT(*) FROM user_savings WHERE user_id = :user_id"),
    ...
)
rows_result = await self.db.execute(text("SELECT ... LIMIT :limit OFFSET :offset"), ...)
```

Can be replaced with a single query using `COUNT(*) OVER()`, consistent with `CommunityService.list_posts()`.

---

### P3-06: `NotificationService.get_unread()` Uses Positional Row Access Instead of Mapping

**File**: `backend/services/notification_service.py`, lines 37–59

```python
rows = result.fetchall()
return [
    {
        "id": str(r[0]),   # positional
        "type": r[1],
        "title": r[2],
        "body": r[3],
        "created_at": str(r[4]),
    }
    for r in rows
]
```

All other service methods use `.mappings()` for named column access. Positional access is fragile — inserting a column into the SELECT list breaks all subsequent indices. Should use `.mappings().all()`.

---

### P3-07: `CommunityPost` Model Has Non-DB Fields Inlined in Pydantic Model

**File**: `backend/models/community.py`, lines 57–59

```python
# Derived fields (not stored in DB — computed via COUNT queries)
upvote_count: int = 0
report_count: int = 0
```

Storing derived/computed fields on the DB-mapped model creates confusion about what is persisted. When `CommunityPost` is constructed from a DB row, these default to 0. Only `CommunityPostResponse` should carry these fields, and the model should document clearly which fields are DB columns vs. computed projections.

---

### P3-08: `UtilityAccountRepository.get_by_user()` Has a Hidden Limit of 100

**File**: `backend/repositories/utility_account_repository.py`, lines 185–187

```python
async def get_by_user(self, user_id: str) -> List[UtilityAccount]:
    """Get all utility accounts for a user."""
    return await self.list(page=1, page_size=100, user_id=user_id)
```

The method name `get_by_user` implies it returns *all* accounts, but it silently caps at 100. Users with more than 100 utility accounts (unlikely but theoretically possible) would see incomplete results without any indication of truncation.

---

### P3-09: `observation_service.py` Accesses Private `_db` Attribute on Repository

**File**: `backend/services/observation_service.py`, line 144

```python
await self._repo._db.commit()
```

This breaks encapsulation — the service reaches into the repository's private `_db` attribute to call `commit()`. The `ForecastObservationRepository` should expose a public `commit()` method, or the session should be managed at the service level and passed in.

---

### P3-10: `CommunityService.list_posts()` Does Not Handle Edge Case Where `rows` Is Empty

**File**: `backend/services/community_service.py`, lines 238–239

```python
total = rows[0]["_total_count"] if rows else 0
```

This is correct but relies on the window function being present in the first row. If the DB returns rows where `_total_count` is `NULL` (e.g., if the window function is not evaluated due to a Postgres quirk), `total` would be `None` which causes the `pages` calculation to fail. A `int(rows[0]["_total_count"] or 0)` guard is safer.

---

## Summary Table

| ID | Severity | Location | Category |
|----|----------|----------|----------|
| P0-01 | P0 — Critical | `repositories/user_repository.py:23` | Model-schema mismatch (GDPR fields missing from SELECT) |
| P0-02 | P0 → Reclassified P2 | `services/feature_flag_service.py:123` | f-string SQL (field names only, values parameterized — safe) |
| P0-03 | P0 — Critical | `services/dunning_service.py:321` | Missing rollback on payment failure steps 4+5 |
| P1-01 | P1 — High | `repositories/price_repository.py:179` | N+1: 3 round-trips per `update()` |
| P1-02 | P1 — High | `repositories/utility_account_repository.py:58` | `account_number_encrypted` type mismatch + missing rollback pattern |
| P1-03 | P1 — High | `services/community_service.py:97` | Shared AsyncSession across `asyncio.wait_for` cancellation boundary |
| P1-04 | P1 — High | `services/alert_service.py:697` | Missing rollback before `PermissionError` re-raise holding `FOR UPDATE` lock |
| P1-05 | P1 — High | `repositories/forecast_observation_repository.py:172` | No rollback on `insert_recommendation()` |
| P1-06 | P1 — High | `services/maintenance_service.py:63` | TOCTOU in upload cleanup; file delete after DB commit |
| P1-07 | P1 — High | `services/notification_service.py:19` | No rollback on `create()` |
| P1-08 | P1 → P2 | `services/savings_service.py:59` | f-string SQL (safe but pattern risk) |
| P1-09 | P1 — High | `services/stripe_service.py:501` | Triple user SELECT in `payment_failed` webhook path |
| P2-01 | P2 — Medium | `repositories/user_repository.py:188` | Dynamic SET clause via f-string (whitelist-guarded, safe) |
| P2-02 | P2 — Medium | `migrations/024*` | Missing indexes on `payment_retry_history` |
| P2-03 | P2 — Medium | `repositories/forecast_observation_repository.py` | Missing indexes on `forecast_observations` / `recommendation_outcomes` |
| P2-04 | P2 — Medium | `services/alert_service.py:514` | 5,000-row in-memory load without pagination |
| P2-05 | P2 — Medium | `services/community_service.py:440` | Unbounded `retroactive_moderate` query (no LIMIT) |
| P2-06 | P2 — Medium | `services/dunning_service.py:391` | `DISTINCT ON` without supporting composite index |
| P2-07 | P2 — Medium | `repositories/user_repository.py:425` | 5,000-row full user load in `get_users_by_region()` |
| P2-08 | P2 — Medium | `repositories/supplier_repository.py:128` | Two sequential queries instead of window function |
| P2-09 | P2 — Medium | `repositories/model_config_repository.py:115` | No concurrency guard for `save_config()` multi-writer scenario |
| P2-10 | P2 — Medium | `repositories/notification_repository.py:188` | No rollback in `update_delivery()` |
| P2-11 | P2 — Medium | `repositories/forecast_observation_repository.py:64` | No rollback in `insert_forecasts()` |
| P2-12 | P2 — Medium | `repositories/price_repository.py:612` | `bulk_create()` allows silent duplicate price data |
| P3-01 | P3 — Low | `repositories/user_repository.py:70` | `datetime.now()` fallback for NOT NULL columns |
| P3-02 | P3 — Low | `repositories/user_repository.py:49` | `uuid4()` fallback for missing PK |
| P3-03 | P3 — Low | `repositories/supplier_repository.py:294` | `SELECT *` in state regulations query |
| P3-04 | P3 — Low | `services/feature_flag_service.py:93` | Returns `True` even when UPDATE matches 0 rows |
| P3-05 | P3 — Low | `services/savings_service.py:157` | Two queries instead of window function for pagination |
| P3-06 | P3 — Low | `services/notification_service.py:37` | Positional row access instead of named mapping |
| P3-07 | P3 — Low | `models/community.py:57` | Derived fields inlined in DB model |
| P3-08 | P3 — Low | `repositories/utility_account_repository.py:185` | Silent 100-row cap in `get_by_user()` |
| P3-09 | P3 — Low | `services/observation_service.py:144` | Private `._db` access across abstraction boundary |
| P3-10 | P3 — Low | `services/community_service.py:238` | Potential `None` from `_total_count` window function |

---

## Positive Observations

The following patterns are well-implemented and should be preserved:

1. **No f-string SQL with user values**: All repositories use `text()` with named parameters. User-supplied values never appear inside SQL strings.
2. **`_UPDATABLE_COLUMNS` whitelist** in `UserRepository` provides effective injection prevention for the dynamic SET builder.
3. **`list_latest_by_regions()` lateral join** (price_repository.py:301) correctly avoids N+1 for multi-region queries.
4. **`_batch_should_send_alerts()`** (alert_service.py:428) uses a VALUES table approach to batch-check cooldown status — avoids N+1 on alert dedup.
5. **`get_price_statistics_with_stddev()`** and related aggregate methods correctly push computation into SQL rather than loading rows into Python.
6. **`toggle_vote()`** uses atomic `INSERT ... ON CONFLICT DO NOTHING` + CTE to avoid TOCTOU race on votes.
7. **`report_post()`** uses a single CTE to insert, count, and conditionally hide — correct atomicity.
8. **`ForecastObservationRepository.backfill_actuals()`** has a `_BACKFILL_LIMIT` cap and warning log for unbounded global updates.
9. **Migration 053** correctly adds a dedup partial unique index on notifications with `alert_id IS NOT NULL` guard.
10. **Stripe webhook `customer.subscription.updated`** correctly limits `tier=free` to terminal states only (`canceled`, `unpaid`), not `trialing`/`past_due`.
