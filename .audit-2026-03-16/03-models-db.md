# Models & Database Layer Audit

**Date**: 2026-03-16
**Auditor**: postgres-pro
**Scope**: `backend/models/*.py`, `backend/config/database.py`, `backend/config/settings.py`, `backend/repositories/*.py`, `backend/services/community_service.py`, migrations 046–050

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 3 |
| HIGH | 7 |
| MEDIUM | 9 |
| LOW | 6 |
| INFO | 5 |
| **Total** | **30** |

---

## CRITICAL

---

### CRIT-01 — Deprecated ORM repository used on Pydantic models (runtime crash path)

**File**: `backend/repositories/supplier_repository.py`, lines 121–127, 155–165, 184, 213–219, 244, 274–281, 376–383

**Description**: `SupplierRepository` calls `select(Supplier)`, `self._db.add(entity)`, `self._db.refresh(entity)`, and `self._db.delete(existing)` using SQLAlchemy ORM operations against `Supplier`, which is a `pydantic.BaseModel`, not a SQLAlchemy ORM model. SQLAlchemy's `Session.add()` requires an ORM-mapped object; passing a Pydantic model raises `UnmappedInstanceError` at runtime. The docstring on lines 36–47 explicitly labels this repository **deprecated** and broken, yet it remains in the active codebase with no runtime guard and is exercised by tests.

**Impact**: Any call path that instantiates `SupplierRepository` (rather than `SupplierRegistryRepository`) and hits `get_by_id`, `get_by_name`, `list_by_region`, `create`, `update`, or `delete` will raise an unhandled exception. The `list()` method uses `select(Supplier)` with `result.scalars()`, which will either return empty results silently or crash depending on the SQLAlchemy version.

**Fix**:
1. Add a hard runtime guard to the class constructor:
   ```python
   def __init__(self, db_session, cache=None):
       raise RuntimeError(
           "SupplierRepository is broken and deprecated. "
           "Use SupplierRegistryRepository instead."
       )
   ```
2. Migrate all remaining test-only callers to `SupplierRegistryRepository`.
3. Delete `SupplierRepository` in a follow-up PR once tests are migrated.

---

### CRIT-02 — `community_posts` has no NOT NULL constraint on `created_at` / `updated_at`

**File**: `backend/migrations/049_community_tables.sql`, lines 23–24

**Description**: The `community_posts` table defines `created_at TIMESTAMPTZ DEFAULT now()` and `updated_at TIMESTAMPTZ DEFAULT now()` without `NOT NULL`. This means an explicit `INSERT ... (created_at) VALUES (NULL)` would succeed, storing a NULL timestamp. The Pydantic model at `backend/models/community.py` line 54 uses `default_factory=lambda: datetime.now(timezone.utc)`, providing a default from Python, but this does not protect against direct SQL inserts or future service-layer bugs that pass `NULL` explicitly.

**Impact**: NULL timestamps silently corrupt sort queries (`ORDER BY created_at DESC`) and break the `idx_community_posts_visible` partial index scan order. The rate-limit query in `community_service.py` line 55 (`WHERE created_at >= NOW() - INTERVAL '1 hour'`) would include posts with NULL `created_at` unpredictably.

**Fix**:
```sql
-- Migration 051
ALTER TABLE community_posts
    ALTER COLUMN created_at SET NOT NULL,
    ALTER COLUMN created_at SET DEFAULT now(),
    ALTER COLUMN updated_at SET NOT NULL,
    ALTER COLUMN updated_at SET DEFAULT now();

ALTER TABLE community_votes
    ALTER COLUMN created_at SET NOT NULL,
    ALTER COLUMN created_at SET DEFAULT now();

ALTER TABLE community_reports
    ALTER COLUMN created_at SET NOT NULL,
    ALTER COLUMN created_at SET DEFAULT now();
```

---

### CRIT-03 — Double-commit in `_run_moderation` shares a session after the outer `create_post` commit

**File**: `backend/services/community_service.py`, lines 93–113

**Description**: `create_post` calls `await db.commit()` at line 95 to persist the newly inserted post, then immediately passes the **same** `AsyncSession` object to `_run_moderation` (line 101). `_run_moderation` then calls `await db.commit()` again at line 170 on that shared session. Between the two commits the same session is in a state where the transaction has already been committed; SQLAlchemy's asyncpg driver issues an implicit `BEGIN` for the second operation, but this creates a window where `asyncio.wait_for` timeout (line 100–110) causes `_clear_pending_moderation` to also receive the same session — now potentially mid-transaction — and calls `await db.commit()` a third time (line 182). With Neon's PgBouncer transaction-mode pooling, the physical backend connection may have changed between commits, making the second UPDATE operate on a different backend than the first INSERT.

**Impact**: Under concurrent load or when the moderation timeout fires, the `is_pending_moderation = false` update may silently fail or be committed to a stale transaction, leaving posts permanently stuck in `is_pending_moderation = true` (invisible to users). This was already identified as a root-cause pattern in the 2026-03-16 connection bug fix (commit 4947cf9) for `asyncio.gather + shared AsyncSession`.

**Fix**: Open a fresh session for the moderation sub-operation rather than reusing the request session:
```python
# In create_post, after await db.commit() on line 95:
# Fire moderation using a NEW session to avoid shared-session corruption
from config.database import db_manager

post_id = post["id"]
try:
    async with db_manager.get_timescale_session() as mod_session:
        await asyncio.wait_for(
            self._run_moderation(mod_session, post_id, clean_title, clean_body, agent_service),
            timeout=MODERATION_TIMEOUT_SECONDS,
        )
except (asyncio.TimeoutError, Exception) as exc:
    async with db_manager.get_timescale_session() as clear_session:
        await self._clear_pending_moderation(clear_session, post_id)
```
Apply the same pattern to `edit_and_resubmit` (lines 536–544).

---

## HIGH

---

### HIGH-01 — No index on `notifications.delivery_status` — full table scan on retry queries

**File**: `backend/migrations/015_notifications.sql` (all notification migrations 015, 026, 029, 032)
**Related file**: `backend/repositories/notification_repository.py`, lines 107–143

**Description**: `NotificationRepository.get_by_delivery_status()` queries:
```sql
SELECT ... FROM notifications
WHERE user_id = :uid AND delivery_status = :status
ORDER BY created_at DESC LIMIT :lim
```
The existing indexes are:
- `idx_notifications_user_unread` — partial on `(user_id, read_at) WHERE read_at IS NULL`
- `idx_notifications_user_created` — on `(user_id, created_at DESC)`

Neither index includes `delivery_status`. For a user with hundreds of notifications, this query performs a full index scan on `idx_notifications_user_created` followed by a filter on `delivery_status`, materialising all rows for that user before applying the status predicate.

**Fix**:
```sql
-- Migration 051 (can be combined with CRIT-02 fix)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_user_status
    ON notifications (user_id, delivery_status, created_at DESC)
    WHERE delivery_status IN ('pending', 'failed');
```

---

### HIGH-02 — No index on `notifications.delivery_channel` — full scan on channel queries

**File**: `backend/repositories/notification_repository.py`, lines 145–182

**Description**: `get_by_channel()` queries `WHERE user_id = :uid AND delivery_channel = :channel`. No index covers `delivery_channel`. Same scan pattern as HIGH-01.

**Fix**: Add a composite index:
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_user_channel
    ON notifications (user_id, delivery_channel, created_at DESC)
    WHERE delivery_channel IS NOT NULL;
```

---

### HIGH-03 — `users.utility_types` stored as `TEXT` — breaks array semantics and type safety

**File**: `backend/migrations/013_user_profile_columns.sql`, line 21
**Related file**: `backend/models/user.py`, line 91

**Description**: Migration 013 stores `utility_types` as plain `TEXT` with a comment "stored as a comma-separated string". The Pydantic model at `models/user.py` line 91 types this as `Optional[List[str]]`. The `_row_to_user` mapper at `user_repository.py` line 65 passes the raw `TEXT` value directly as `utility_types=data.get("utility_types")`, which means a round-tripped value like `"electricity,natural_gas"` arrives in Python as the string `"electricity,natural_gas"` rather than the list `["electricity", "natural_gas"]` — a silent type mismatch. Any downstream code iterating over `user.utility_types` would iterate over characters.

**Impact**: Filtering, display, and feature-flag checks on `utility_types` produce wrong results silently. The `UtilityType` enum in `models/utility.py` is never enforced for this field.

**Fix**:
1. Migrate the column to `TEXT[]`:
   ```sql
   -- Migration 051
   ALTER TABLE users
       ALTER COLUMN utility_types TYPE TEXT[]
       USING CASE
           WHEN utility_types IS NULL THEN NULL
           WHEN utility_types = '' THEN '{}'::TEXT[]
           ELSE string_to_array(utility_types, ',')
       END;
   ```
2. Update `_row_to_user` to parse the now-native array without string splitting.
3. Update the `UPDATE` path in `user_repository.py` to cast lists to `TEXT[]`.

---

### HIGH-04 — `SupplierRepository.update()` calls `get_by_id()` then ORM `setattr` — N+1 read before write

**File**: `backend/repositories/supplier_repository.py`, lines 208–222

**Description**: `update()` first calls `await self.get_by_id(id)` (line 208), which itself calls `select(Supplier)` — an ORM query on an unmapped Pydantic model. If this somehow returns a result (it won't in practice — see CRIT-01), the method calls `setattr(existing, field, value)` on the Pydantic model instance and then `await self._db.commit()` without re-adding the object to the session. This is a use-after-eviction pattern: the object was never tracked by SQLAlchemy's identity map, so `commit()` persists nothing.

**Fix**: Delete `SupplierRepository` (see CRIT-01). `SupplierRegistryRepository` uses raw SQL correctly.

---

### HIGH-05 — `price_alert_configs.user_id` lacks a foreign key to `neon_auth` users

**File**: `backend/migrations/014_alert_tables.sql`, lines 38–40

**Description**: `price_alert_configs` has `CONSTRAINT fk_alert_config_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`. However, the production auth system is Better Auth, which manages users in the `neon_auth` schema (`neon_auth.users`), not the public `users` table. The public `users` table is a separate profile table. If `user_id` in `price_alert_configs` references `neon_auth.users.id`, the FK points at the wrong table and referential integrity is never enforced by PostgreSQL. Orphaned alert configs accumulate for deleted auth users.

**Impact**: Alert cron job (`check-alerts.yml`) can fire alerts for users whose auth account was deleted, wasting AI/email quota and potentially re-activating stale data.

**Fix**: Audit which `user_id` value is actually stored in `price_alert_configs`. If it is the `neon_auth.users.id` UUID, the FK must be updated:
```sql
ALTER TABLE price_alert_configs
    DROP CONSTRAINT IF EXISTS fk_alert_config_user;
-- Add application-level orphan cleanup in the dunning/check-alerts workflows
-- until a cross-schema FK strategy is established.
```
Also apply to `alert_history`, `notifications`, `community_posts`, `community_votes`, `community_reports`, `user_connections`, and all other tables that carry a `user_id` column.

---

### HIGH-06 — `propane_prices.state` uses `VARCHAR(5)` but state codes are 2 characters; index on `(state, fetched_at DESC)` is suboptimal

**File**: `backend/migrations/046_propane_prices.sql`, lines 7, 14–15

**Description**: The `propane_prices` table indexes on `(state, fetched_at DESC)`. The primary query pattern in `PropaneService` is to get the latest price for a state over a date range, which filters on `(state, period_date)`. However `idx_propane_prices_state` orders by `fetched_at DESC`, not `period_date DESC`. The `UNIQUE (state, period_date)` constraint creates its own B-tree index, but the covering index for time-range queries should order by `period_date`, not `fetched_at`.

Additionally, `VARCHAR(5)` is over-wide for 2-character US state codes and `period_date` is a `DATE` (not `TIMESTAMPTZ`) which is inconsistent with `fetched_at TIMESTAMPTZ`.

**Fix**:
```sql
-- Migration 051
-- Replace the poorly ordered state index with one aligned to query patterns
DROP INDEX IF EXISTS idx_propane_prices_state;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_propane_prices_state_period
    ON propane_prices (state, period_date DESC);
```

---

### HIGH-07 — `water_rates` has no `updated_at` trigger — stale data undetectable

**File**: `backend/migrations/047_water_rates.sql`

**Description**: `water_rates` defines `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` but no trigger calls `update_updated_at_column()` on row updates (unlike `community_posts` which has `trg_community_posts_updated_at`). Manual `UPDATE` statements to the `water_rates` table will not update `updated_at`, making data freshness checks unreliable.

**Fix**:
```sql
-- Migration 051
CREATE TRIGGER trg_water_rates_updated_at
    BEFORE UPDATE ON water_rates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

---

## MEDIUM

---

### MED-01 — `pool_recycle=200` is shorter than Neon's idle timeout — unnecessary reconnects

**File**: `backend/config/database.py`, line 86

**Description**: The engine is configured with `pool_recycle=200` (seconds) with the comment "recycle 100s before Neon's 5-min auto-suspend". Neon's idle compute suspension is 5 minutes (300 s), so `pool_recycle=200` closes connections at 200 s and opens new ones immediately — well before Neon would suspend. This causes unnecessary `CREATE CONNECTION` overhead on Neon's pooler. The intent (avoid stale connections) is better served by `pool_pre_ping=True` (already set at line 85) which validates connections on checkout at zero extra round-trips.

**Fix**: Remove or increase `pool_recycle`:
```python
# pool_recycle=200 is redundant given pool_pre_ping=True.
# Increase to 1800 (30 min) to reduce unnecessary reconnects on Neon.
pool_recycle=1800,
```

---

### MED-02 — `get_timescale_session` commits unconditionally even on read-only queries

**File**: `backend/config/database.py`, lines 159–174

**Description**: The context manager at line 168–174 calls `await session.commit()` unconditionally in the `try` block for every yielded session, regardless of whether any writes occurred. For read-only request handlers (e.g., `GET /prices`, `GET /community/posts`), this issues a `COMMIT` to the database that is a no-op but adds latency and consumes a round-trip on Neon's pooler. Over thousands of read requests per hour this adds measurable overhead.

Additionally, the rollback on line 171 catches all exceptions including non-DB exceptions raised in the caller's `yield` block, which could mask application errors unrelated to database state.

**Fix**: Use SQLAlchemy's `session.in_transaction()` guard, or restructure to only commit when the session has pending writes. Consider accepting an explicit `autocommit=False` and letting individual repositories own commit timing — which they already do (every repository method calls `await self._db.commit()`). This means **sessions are double-committing**: once inside the repository method and once when the context manager exits. While harmless for asyncpg (a `COMMIT` on a clean transaction is a no-op), it is wasteful.

```python
@asynccontextmanager
async def get_timescale_session(self):
    if not self.async_session_maker:
        yield None
        return

    async with self.async_session_maker() as session:
        try:
            yield session
            # Repositories commit themselves; only commit here if session is dirty.
            if session.is_active and session.in_transaction():
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        # session.close() is called automatically by async_sessionmaker context manager
```

---

### MED-03 — `consent_records` column name drift between `init_neon.sql` and `002_gdpr_auth_tables.sql`

**File**: `backend/migrations/init_neon.sql` line 136 vs `backend/migrations/002_gdpr_auth_tables.sql` line 13

**Description**: `init_neon.sql` creates `consent_records` with column `metadata JSONB`. Migration 002 re-creates `consent_records` with `CREATE TABLE IF NOT EXISTS` and uses `metadata_json JSONB` instead. If both migrations ran in order on a fresh database, the table would have `metadata JSONB` (from `init_neon.sql`, since 002's `IF NOT EXISTS` is skipped), not `metadata_json`. On a database where `init_neon.sql` was not applied first (e.g., CI environments), it would have `metadata_json`. The `ConsentRecord` Pydantic model at `models/consent.py` line 46 uses the field name `metadata`, not `metadata_json`.

**Impact**: Services reading `consent_records.metadata` on a database initialized via migration 002 only will find `NULL` for that column, silently dropping consent metadata.

**Fix**: Add a reconciliation migration:
```sql
-- Migration 051
ALTER TABLE consent_records
    ADD COLUMN IF NOT EXISTS metadata JSONB,
    ADD COLUMN IF NOT EXISTS metadata_json JSONB;

-- Merge: copy metadata_json into metadata where metadata is null
UPDATE consent_records
    SET metadata = metadata_json
    WHERE metadata IS NULL AND metadata_json IS NOT NULL;
```
Then update all query strings to reference only `metadata`.

---

### MED-04 — `deletion_logs` column name drift: `timestamp` vs `deleted_at`

**File**: `backend/migrations/init_neon.sql` line 156 vs `backend/migrations/002_gdpr_auth_tables.sql` line 53; comment in 002 line 63

**Description**: `init_neon.sql` creates `deletion_logs` with `timestamp TIMESTAMPTZ`. Migration 002 creates it with `deleted_at TIMESTAMPTZ`. Migration 002's comment on line 63 acknowledges this: "idx_deletion_timestamp index is created by migration 003 after renaming the 'timestamp' column". The `DeletionLog` Pydantic model at `models/consent.py` line 163 uses `deleted_at`. If a database was seeded from `init_neon.sql` only, queries that reference `deleted_at` will fail at runtime.

**Impact**: `DeletionLog` queries fail with `column "deleted_at" does not exist` on databases initialized from `init_neon.sql`.

**Fix**: Migration 003 (`003_reconcile_schema.sql`) should contain the column rename. Verify it does and that it is idempotent:
```sql
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'deletion_logs' AND column_name = 'timestamp'
    ) THEN
        ALTER TABLE deletion_logs RENAME COLUMN "timestamp" TO deleted_at;
    END IF;
END $$;
```

---

### MED-05 — `CommunityPost` Pydantic model uses raw `str` for `post_type` and `utility_type` — duplicated validation logic

**File**: `backend/models/community.py`, lines 43–110

**Description**: `CommunityPost`, `CommunityPostCreate`, and the service layer all duplicate validation using hardcoded `set` literals (`{"tip", "rate_report", "discussion", "review"}` and `{"electricity", "natural_gas", ...}`). The canonical enums `PostType` (line 17) and `CommunityUtilityType` (line 25) are defined but unused by the model fields themselves, which are typed as `str`. This means the enums could diverge from the validation sets without any compile-time or test-time error. `UtilityType` in `models/utility.py` does not include `"water"` or `"general"`, creating a third source of truth for valid utility type values.

**Fix**: Replace `str` field types with the enum types on model fields:
```python
# models/community.py
utility_type: CommunityUtilityType = Field(..., max_length=30)
post_type: PostType = Field(..., max_length=20)
```
Remove the redundant `@field_validator` methods for `post_type` and `utility_type` in both `CommunityPost` and `CommunityPostCreate` — Pydantic enum validation replaces them. Add `"water"` and `"general"` to `UtilityType` in `models/utility.py` or keep `CommunityUtilityType` as the standalone source of truth for community-specific types.

---

### MED-06 — `retroactive_moderate` in `community_service.py` has no LIMIT — full table scan on large deployments

**File**: `backend/services/community_service.py`, lines 440–449

**Description**: `retroactive_moderate` selects `WHERE is_pending_moderation = false AND is_hidden = false AND hidden_reason IS NULL AND created_at >= NOW() - INTERVAL '24 hours'` with `ORDER BY created_at ASC` and **no LIMIT clause**. On a busy community with thousands of daily posts, this returns an unbounded result set into Python memory, then spawns up to N concurrent AI classification tasks limited only by `asyncio.Semaphore(5)`.

The partial index `idx_community_posts_needs_remoderation` (migration 050, line 17) matches this predicate but the query adds `created_at >= NOW() - INTERVAL '24 hours'` which is not in the partial index predicate — the planner will use the partial index for the boolean filters but still scan all matching rows within 24 hours.

**Fix**:
```python
# Add LIMIT 100 to cap the batch size per cron run
select_sql = text("""
    SELECT id, title, body FROM community_posts
    WHERE is_pending_moderation = false
      AND is_hidden = false
      AND hidden_reason IS NULL
      AND created_at >= NOW() - INTERVAL '24 hours'
    ORDER BY created_at ASC
    LIMIT 100
""")
```
Update the partial index in a new migration to include the 24-hour recency bound as a periodic-refresh window rather than an unbounded scan.

---

### MED-07 — `users.annual_usage_kwh` stored as `INT` in DB but as `Decimal` in Pydantic model

**File**: `backend/migrations/013_user_profile_columns.sql`, line 44
**Related file**: `backend/models/user.py`, line 89

**Description**: The column is `INT` in the database but the Pydantic model field is `Optional[Decimal]`. The `_USER_COLUMNS` SELECT in `user_repository.py` line 30 fetches `annual_usage_kwh` as-is. SQLAlchemy/asyncpg returns an `int` for an `INT` column. Pydantic will coerce `int` → `Decimal` silently, but the reverse (writing a `Decimal` value with fractional digits back to an `INT` column) will silently truncate or raise a DB error. Furthermore, other usage columns like `average_daily_kwh` are `NUMERIC` in the DB (added by an earlier migration) — the inconsistency suggests `annual_usage_kwh` was intended to be `NUMERIC` too.

**Fix**:
```sql
-- Migration 051
ALTER TABLE users
    ALTER COLUMN annual_usage_kwh TYPE NUMERIC(12, 2);
```

---

### MED-08 — `nrel_api_base_url` default contains a typo (`nlr.gov` instead of `nrel.gov`)

**File**: `backend/config/settings.py`, line 74

**Description**: The default value for `nrel_api_base_url` is `"https://developer.nlr.gov/api/utility_rates/v3"`. The correct NREL Developer API base URL is `https://developer.nrel.gov/api/utility_rates/v3`. `nlr.gov` does not resolve to NREL. This default is overridden by the `NREL_API_BASE_URL` environment variable on Render, so it does not break production, but it will silently fail in any environment where `NREL_API_BASE_URL` is not explicitly set (e.g., developer local environments, CI, staging).

**Fix**:
```python
nrel_api_base_url: str = Field(
    default="https://developer.nrel.gov/api/utility_rates/v3",
    validation_alias="NREL_API_BASE_URL",
)
```

---

### MED-09 — `user_connections` has no index on `(user_id, connection_type)` — connection-type filters scan all user rows

**File**: `backend/migrations/008_connection_feature.sql`

**Description**: The connection feature queries frequently filter by both `user_id` and `connection_type` (e.g., "get all email_import connections for this user", "get all portal_scrape connections"). The existing indexes are:
- `idx_user_connections_user` on `(user_id)`
- `idx_user_connections_user_status` on `(user_id, status)`
- `idx_user_connections_user_supplier` on `(user_id, supplier_id) WHERE supplier_id IS NOT NULL`

There is no composite index on `(user_id, connection_type)`. A user with mixed connection types (e.g., 3 email, 2 direct, 1 portal) requires a filtered scan through all their connections to find connections of a specific type.

**Fix**:
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_connections_user_type
    ON user_connections (user_id, connection_type);
```

---

## LOW

---

### LOW-01 — `consent_records` FK in migration 002 uses `ON DELETE CASCADE` but `init_neon.sql` version has no FK

**File**: `backend/migrations/init_neon.sql`, lines 125–141 vs `backend/migrations/002_gdpr_auth_tables.sql`, lines 22–23

**Description**: The `consent_records` table in `init_neon.sql` has no foreign key to `users`. Migration 002 adds `CONSTRAINT fk_consent_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`. These two definitions exist independently, and the FK is only present on databases initialized via migration 002. GDPR audit trails require that consent records are preserved even after user deletion (right to erasure ≠ right to destroy consent evidence), but `ON DELETE CASCADE` silently removes consent records when a user row is deleted.

**Fix**: Change to `ON DELETE SET NULL` with a non-null `user_id` preserved in an audit column, or enforce consent record retention at the application layer before user deletion.

---

### LOW-02 — `ForecastObservation.forecast_hour` is validated `ge=0, le=23` but the DB has no CHECK constraint

**File**: `backend/models/observation.py`, line 18
**Related migration**: `backend/migrations/005_observation_tables.sql` (not read — inferred)

**Description**: The Pydantic model enforces `0 <= forecast_hour <= 23` but there is no corresponding `CHECK` constraint in the database. Direct SQL inserts can store values outside this range, which will then pass through the model without re-validation (since `from_attributes=True` skips validators in some Pydantic v2 modes).

**Fix**: Add a CHECK constraint in the next migration:
```sql
ALTER TABLE forecast_observations
    ADD CONSTRAINT chk_forecast_hour CHECK (forecast_hour BETWEEN 0 AND 23);
```

---

### LOW-03 — `price_alert_configs.region` defaults to `'us_ct'` — inappropriate hardcoded default

**File**: `backend/migrations/014_alert_tables.sql`, line 29

**Description**: `region VARCHAR(50) NOT NULL DEFAULT 'us_ct'` means any alert config inserted without an explicit region silently gets `us_ct` (Connecticut). Users in other states who trigger alert creation without specifying a region will receive incorrect region-specific alerts.

**Fix**: Remove the default and enforce NOT NULL without a default, ensuring the application layer always supplies an explicit region:
```sql
ALTER TABLE price_alert_configs
    ALTER COLUMN region DROP DEFAULT;
```

---

### LOW-04 — `Notification` model has no `max_length` on `title` field

**File**: `backend/models/notification.py`, lines 60, 95

**Description**: `NotificationCreate.title` has `min_length=1` but no `max_length`. The database column is `TEXT NOT NULL` with no length limit. A malformed or adversarial API call can store arbitrarily large strings in the notifications table, wasting storage and causing rendering issues in the frontend notification bell.

**Fix**:
```python
# models/notification.py
title: str = Field(..., min_length=1, max_length=500)
```

---

### LOW-05 — `UserCreate.password` field validated only for `min_length=8` — no complexity requirements

**File**: `backend/models/user.py`, lines 137

**Description**: `UserCreate.password` only enforces `min_length=8`. There is no check for character complexity, common password patterns, or bcrypt round-trip validation. While this is a Pydantic schema for the legacy custom auth path (Better Auth is primary), any code paths that still use `UserCreate` could accept `password="password"` or `password="12345678"`.

**Fix**: Add a strength validator or explicitly document that this schema is not used in the production auth flow and should be deleted.

---

### LOW-06 — `SupplierRegistryRepository.list_suppliers` issues two sequential DB queries (count + data) instead of using window function

**File**: `backend/repositories/supplier_repository.py`, lines 588–594

**Description**: The method executes `SELECT COUNT(*)` followed by a separate `SELECT ... LIMIT :limit OFFSET :offset`. These are sequential, adding a second round-trip for every paginated list request. The community service uses `COUNT(*) OVER()` window function to obtain total and rows in one query (the correct approach). Supplier lists are cached for 1 hour so the impact is bounded to cache misses, but it is still wasteful.

**Fix**: Use `COUNT(*) OVER()` or `asyncio.gather` to parallelize the two queries (as done in `price_repository.py` `get_historical_prices_paginated` line 565).

---

## INFO

---

### INFO-01 — `DatabaseManager` class name still references "timescale" — misleading nomenclature

**File**: `backend/config/database.py`, lines 32, 33, 80, 147, 151, 159, 201

**Description**: Fields `timescale_engine` and `timescale_pool`, and the method `get_timescale_session` all use the "timescale" prefix. The database is plain Neon PostgreSQL with no TimescaleDB extension; the `init_neon.sql` comment on line 161 also notes "TimescaleDB hypertable removed". This causes confusion for new contributors.

**Recommendation**: Rename to `engine`, `raw_pool`, and `get_session` in a non-breaking refactor.

---

### INFO-02 — `asyncpg.create_pool` branch is dead code for Neon deployments

**File**: `backend/config/database.py`, lines 100–110

**Description**: Lines 100–110 create an `asyncpg` raw pool only when `"neon.tech" not in db_url`. In production, `DATABASE_URL` always contains `neon.tech`. This branch is only exercised by local non-Neon PostgreSQL instances. The `_execute_raw_query` method at line 176 prefers the raw pool when available, but it is never used in production. The asyncpg pool configuration (`max_inactive_connection_lifetime=300`) is also redundant with `pool_recycle`.

**Recommendation**: Document this as a local-dev-only code path and add a comment in `_execute_raw_query` to indicate it is unreachable in production.

---

### INFO-03 — `model_version.py` not present — referenced in `models/__init__.py` or elsewhere?

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/model_version.py`

**Description**: `ls` output shows `model_version.py` in `backend/models/`. This file was not read during this audit. It should be reviewed in a follow-up to ensure it does not contain SQLAlchemy ORM models (same issue as CRIT-01) or undocumented schema drift.

**Recommendation**: Read and audit `model_version.py` in a follow-up pass.

---

### INFO-04 — `get_users_by_region` in `UserRepository` has a hardcoded `LIMIT 5000` with no pagination

**File**: `backend/repositories/user_repository.py`, lines 425–450

**Description**: The method returns up to 5,000 users per call with no pagination support. This is used by the check-alerts cron job to find users to notify. For regions with more than 5,000 users, alerts will silently not be sent to users beyond the limit.

**Recommendation**: Add cursor-based or keyset pagination:
```python
# Use OFFSET pagination as a minimum, keyset preferred:
# WHERE region = :region AND id > :last_seen_id ORDER BY id LIMIT 1000
```

---

### INFO-05 — `water_rates` has no `effective_date` NOT NULL constraint — `NULL` dates accepted

**File**: `backend/migrations/047_water_rates.sql`, line 11

**Description**: `effective_date DATE` (nullable) allows water rate rows without an effective date, making it impossible to determine when a rate became valid. The `WaterRateService` may return rates with no effective date, which the frontend displays as "Unknown date."

**Recommendation**: Add a `NOT NULL DEFAULT CURRENT_DATE` constraint or require `effective_date` to be supplied by the data ingestion pipeline.

---

## Migration-Specific Findings (046–050)

### M-01 — Migration 050 uses `CREATE INDEX CONCURRENTLY` without a transaction guard

**File**: `backend/migrations/050_community_posts_indexes.sql`, lines 11–18
**Severity**: LOW

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction. If the migration runner wraps each file in a `BEGIN`/`COMMIT`, this migration will fail with:
```
ERROR: CREATE INDEX CONCURRENTLY cannot run inside a transaction block
```
The `DROP INDEX IF EXISTS` on line 8 is safe inside a transaction but creates an asymmetry: the DROP succeeds but the CREATE fails, leaving `community_posts` without the `idx_community_posts_region_utility` index and no replacement — making all `list_posts` queries do a full sequential scan.

**Fix**: Add a migration comment and ensure the runner uses `autocommit=True` for this file, or replace `CONCURRENTLY` with a standard `CREATE INDEX IF NOT EXISTS` for migrations run in transactional mode:
```sql
-- NOTE: This migration must be run outside a transaction block.
-- Use: psql --single-transaction=off -f 050_community_posts_indexes.sql
```

---

### M-02 — Migration 048 has no `IF NOT EXISTS` guard on INSERT — relies solely on `ON CONFLICT (name) DO NOTHING`

**File**: `backend/migrations/048_utility_feature_flags.sql`
**Severity**: LOW

This is acceptable only because the `feature_flags.name` column has a UNIQUE constraint (from migration 016). However, if the `feature_flags` table does not exist (e.g., migration 016 was not applied), this migration will fail with `relation "feature_flags" does not exist` rather than a friendly error. A dependency comment would make the ordering explicit.

**Recommendation**: Add a header comment:
```sql
-- Requires: migration 016 (feature_flags table)
```

---

### M-03 — No rollback/down migration exists for any of migrations 046–050

**Files**: All five migration files
**Severity**: INFO

None of the 046–050 migrations include a rollback section or a corresponding `down_*.sql` file. In a failure scenario (e.g., a migration is partially applied before a deployment fails), there is no automated path to restore the previous schema state.

**Recommendation**: For each migration, add a commented-out rollback block:
```sql
-- ROLLBACK:
-- DROP TABLE IF EXISTS propane_prices;
```
Or maintain a parallel `down/046_propane_prices_down.sql` for use with a migration tool like `golang-migrate` or `Flyway`.

---

## Verification Queries

Run these against the Neon production database to validate the most critical issues:

```sql
-- Verify community_posts column nullability (CRIT-02)
SELECT column_name, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'community_posts'
  AND column_name IN ('created_at', 'updated_at');

-- Verify notification indexes (HIGH-01, HIGH-02)
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'notifications';

-- Check for orphaned alert configs (HIGH-05)
SELECT COUNT(*) FROM price_alert_configs
WHERE user_id NOT IN (SELECT id FROM users);

-- Verify utility_types column type (HIGH-03)
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'users' AND column_name = 'utility_types';

-- Check annual_usage_kwh type (MED-07)
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users' AND column_name = 'annual_usage_kwh';

-- Verify updated_at trigger on water_rates (HIGH-07)
SELECT trigger_name, event_manipulation, action_statement
FROM information_schema.triggers
WHERE event_object_table = 'water_rates';
```
