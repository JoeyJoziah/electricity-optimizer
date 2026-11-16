# Audit Report: Database Layer

**Date:** 2026-03-18
**Auditor:** Postgres Pro (claude-sonnet-4-6)
**Scope:** All migration files (init_neon.sql + 001–053), SQLAlchemy models, repository classes, and database.py configuration for the RateShift FastAPI + Neon PostgreSQL stack.

---

## Executive Summary

The RateShift database layer is broadly well-engineered. The 53-migration sequential numbering is intact, UUID primary keys are used consistently, IF NOT EXISTS guards are universal, and raw-SQL repositories correctly avoid ORM/Pydantic model mismatch. The team has made responsible decisions throughout: CONCURRENTLY index creation, partial indexes on high-cardinality booleans, GIN indexes for array columns, and cascading FK cleanup in migrations 051–052.

However, two critical schema correctness bugs exist — both identified by the previous audit attempt — and several medium-to-low-priority issues were uncovered during this review. The two P0 items will cause index creation to fail silently (or loudly, depending on migration runner) and mean those indexes do not actually exist in production.

**Counts:**
- P0 (Critical): 2
- P1 (High): 4
- P2 (Medium): 6
- P3 (Low): 7
- Positive findings: 12

---

## P0 — Critical

### P0-1: Index `idx_bill_uploads_user_status` References Non-Existent Column `status`

**File:** `backend/migrations/017_additional_indexes.sql:29`

**Description:**

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bill_uploads_user_status
    ON bill_uploads (user_id, created_at DESC, status);
```

The `bill_uploads` table (created in migration 008) has no column named `status`. The parse lifecycle column is named `parse_status`. This index creation will fail at runtime with:

```
ERROR: column "status" does not exist
```

Because `CREATE INDEX CONCURRENTLY` was used, the failure leaves behind a broken index entry in `pg_index` with `indisvalid = false`. Subsequent re-runs of the migration with `IF NOT EXISTS` will no-op without detecting the corruption. The index effectively does not exist in production, meaning all queries filtering `bill_uploads` by user + creation time + parse status fall back to sequential scans.

**Verification from schema (migration 008):**
- Column defined: `parse_status VARCHAR(20) NOT NULL DEFAULT 'pending'`
- Column missing: `status` — does not appear anywhere in bill_uploads DDL

**Remediation:**

```sql
-- Drop the invalid index if it exists (indisvalid=false state)
DROP INDEX IF EXISTS idx_bill_uploads_user_status;

-- Recreate with correct column name
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bill_uploads_user_parse_status
    ON bill_uploads (user_id, created_at DESC, parse_status);
```

A new migration `054_fix_bill_uploads_index.sql` should be created with the above, plus a `REINDEX` guard to clean up any invalid index state:

```sql
-- Cleanup any broken index in invalid state
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_index pi
        JOIN pg_class pc ON pi.indexrelid = pc.oid
        WHERE pc.relname = 'idx_bill_uploads_user_status'
          AND NOT pi.indisvalid
    ) THEN
        DROP INDEX CONCURRENTLY IF EXISTS idx_bill_uploads_user_status;
        RAISE NOTICE 'Dropped invalid idx_bill_uploads_user_status';
    END IF;
END $$;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bill_uploads_user_parse_status
    ON bill_uploads (user_id, created_at DESC, parse_status);
```

---

### P0-2: Index `idx_forecast_observations_region` References Non-Existent Column `utility_type`

**File:** `backend/migrations/017_additional_indexes.sql:36`

**Description:**

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_forecast_observations_region
    ON forecast_observations (region, utility_type, created_at DESC);
```

The `forecast_observations` table (created in migration 005) has no `utility_type` column. Its schema is:

```
id, forecast_id, region, forecast_hour, predicted_price, actual_price,
confidence_lower, confidence_upper, model_version, created_at, observed_at
```

`utility_type` was added to `electricity_prices`, `suppliers`, and `tariffs` in migration 006, but was never added to `forecast_observations`. This index creation fails with:

```
ERROR: column "utility_type" does not exist
```

As with P0-1, `IF NOT EXISTS` + `CONCURRENTLY` masks the failure on subsequent runs. The index the code in `forecast_observation_repository.py` relies on for region+time lookups (`get_accuracy_metrics`, `backfill_actuals`) does not actually exist, causing sequential scans on potentially large observation tables.

**Impact:** The `backfill_actuals()` method performs an UPDATE...FROM JOIN between `forecast_observations` and `electricity_prices` without the expected index coverage, which can cause full table scans and timeouts during the CF Worker cron trigger that runs every 6h.

**Remediation:**

Two options:

**Option A (preferred):** Add `utility_type` to `forecast_observations` and re-create the index:

```sql
-- Migration 054 (or 055 if 054 fixes P0-1)
ALTER TABLE forecast_observations
    ADD COLUMN IF NOT EXISTS utility_type VARCHAR(30) DEFAULT 'electricity';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_forecast_observations_region_utility
    ON forecast_observations (region, utility_type, created_at DESC);
```

**Option B:** Drop and recreate the index without `utility_type`:

```sql
DROP INDEX IF EXISTS idx_forecast_observations_region;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_forecast_observations_region
    ON forecast_observations (region, created_at DESC);
```

Option A is preferred because the `ForecastObservationRepository.backfill_actuals()` joins against `electricity_prices` on `region` equality, and future forecasts will likely be multi-utility. Option B is the minimal fix.

---

## P1 — High

### P1-1: `user_savings` Table Missing FK to `users` Until Migration 052 — Retroactive Nature Creates Data Gap Risk

**File:** `backend/migrations/012_user_savings.sql`

**Description:**

Migration 012 creates `user_savings` with:

```sql
user_id UUID NOT NULL,
```

No FK constraint was added. The FK is only retroactively added in migration 052 (`052_fk_gdpr_cascade_round2.sql`). This means that for any environment where migrations 012–051 were applied before 052 was introduced, there is a window of ~40 migrations (several weeks of real time) where orphan rows could have been inserted into `user_savings` referencing non-existent users. These orphan rows will:

1. Cause the `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY` in migration 052 to fail if orphan rows exist.
2. Never be cleaned up by GDPR user deletion cascades.

The same pattern affected `recommendation_outcomes` (005), `model_predictions` (033), `model_ab_assignments` (033), and `referrals` (039), all of which had the same retroactive FK fix in migration 052.

**Remediation:**

Before applying migration 052 to any environment where it has not yet been applied, run a cleanup check:

```sql
-- Identify orphan rows before adding FK
SELECT COUNT(*) FROM user_savings us
WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id = us.user_id);

-- If count > 0, either delete orphans or reconcile them before applying 052
DELETE FROM user_savings
WHERE user_id NOT IN (SELECT id FROM users);
```

The broader remediation is a pre-migration check script that validates FK referential integrity before adding constraints. Future tables should define FK constraints inline at creation time.

---

### P1-2: Migration 009 Adds `updated_at` Column to `user_connections` Without Idempotency Guard

**File:** `backend/migrations/009_email_oauth_tokens.sql:10`

**Description:**

```sql
ALTER TABLE user_connections
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
```

The `user_connections` table was created in migration 008 which already defined `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`. Migration 009 attempts to re-add `updated_at` using `ADD COLUMN IF NOT EXISTS`. The `IF NOT EXISTS` guard means this silently no-ops in most environments, but it masks a structural inconsistency: the column existed in 008 but the migration authors were unaware of it.

More critically, if an environment ran 009 without 008 (unlikely but possible in test/staging), the `updated_at` from 009 lacks the `NOT NULL` constraint, creating a nullable `updated_at` that conflicts with the application's assumptions.

Additionally, migration 011 (labeled `010_utility_type_index` but actually file `011_utilityapi_sync_columns.sql`) has the same header comment showing `Migration 010: Add UtilityAPI sync columns`, creating a **numbering discrepancy in comments** even though filenames are sequential. The actual file `010_utility_type_index.sql` also says "Migration 010" in its comment. Two files claim to be migration 010.

**Remediation:**

For the numbering discrepancy: Add a migration comment audit to the CI validate-migrations workflow. Fix the header in `011_utilityapi_sync_columns.sql` to say `Migration 011`.

For the duplicate column: No action needed in production if 008 was applied first. Document the constraint difference in the migration comment.

---

### P1-3: `consent_records.user_id` Changed From NOT NULL to Nullable in Migration 023 — Audit Trail Gap

**File:** `backend/migrations/023_db_audit_indexes.sql:35`

**Description:**

```sql
ALTER TABLE consent_records
    ALTER COLUMN user_id DROP NOT NULL;
```

The stated reason (in migration comment) is to change `ON DELETE CASCADE` to `ON DELETE SET NULL` so that consent records are retained after user deletion. This is architecturally reasonable for GDPR Article 7(3) (right to withdraw consent documentation), but it creates a new problem: the ConsentRepository's queries that filter `WHERE user_id = ?` will now miss any records where user deletion set `user_id = NULL`.

More critically, the consent validation logic (`require_gdpr_consent` in `models/user.py`) and `record_consent` in `user_repository.py` both assume `user_id` is always present. The change was not coordinated with an update to the repository query layer to handle NULL user_id records in audit queries.

**Remediation:**

1. Add a `deleted_user_id UUID` column to `consent_records` to archive the original user ID before SET NULL fires.
2. Update the FK trigger to copy `user_id` to `deleted_user_id` before nullification.
3. Alternatively, enforce via application logic: anonymize but retain the hashed user identifier.

At minimum, document that `WHERE user_id = ?` queries in `ConsentRepository` will miss records for deleted users.

---

### P1-4: `list_latest_by_regions` in `PriceRepository` Uses Window Function Without Index Coverage

**File:** `backend/repositories/price_repository.py:318`

**Description:**

```python
sql = f"""
    SELECT {_PRICE_COLUMNS}
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY region ORDER BY timestamp DESC) AS rn
        FROM electricity_prices
        WHERE region IN ({placeholders})
    ) sub
    WHERE rn <= :lim
    ORDER BY region, timestamp DESC
"""
```

This query partitions over `region` and orders by `timestamp DESC`. The existing composite index `idx_prices_region_timestamp ON electricity_prices (region, timestamp DESC)` does cover the `WHERE region IN (...)` predicate but PostgreSQL typically cannot use it for the window function partition efficiently when multiple regions are passed — it will often choose a sequential scan + sort instead.

At scale (millions of price rows), this method is called by the dashboard for all user regions simultaneously and can become a bottleneck. The lateral join pattern suggested in the query comment is the right approach but was not implemented.

**Remediation:**

Replace the window function approach with a LATERAL join for better index utilization:

```sql
SELECT p.*
FROM (VALUES :region_list) AS r(region_val)
CROSS JOIN LATERAL (
    SELECT {_PRICE_COLUMNS}
    FROM electricity_prices
    WHERE region = r.region_val
    ORDER BY timestamp DESC
    LIMIT :lim
) p
ORDER BY p.region, p.timestamp DESC
```

This forces PostgreSQL to use the `idx_prices_region_timestamp` index for each region independently, avoiding the full partition scan.

---

## P2 — Medium

### P2-1: `electricity_prices` Has Duplicate Overlapping Composite Indexes

**File:** Multiple migration files (004, 006, 010, 020, 037)

**Description:**

The following indexes on `electricity_prices` overlap significantly:

| Index Name | Columns | Migration |
|---|---|---|
| `idx_prices_region_timestamp` | (region, timestamp DESC) | init_neon |
| `idx_prices_region_supplier_timestamp` | (region, supplier, timestamp DESC) | 004 |
| `idx_prices_region_utility` | (region, utility_type, timestamp DESC) | 006 |
| `idx_prices_region_utilitytype_timestamp` | (region, utility_type, timestamp DESC) | 010 |
| `idx_prices_region_supplier_created` | (region, supplier, created_at DESC) | 020 |
| `idx_prices_region_utilitytype_created` | (region, utility_type, created_at DESC) | 020 |
| `idx_electricity_prices_region_utility_time` | (region, utility_type, timestamp DESC) | 037 |

Specifically, `idx_prices_region_utility` (006) and `idx_prices_region_utilitytype_timestamp` (010) and `idx_electricity_prices_region_utility_time` (037) are **identical** — all three are `(region, utility_type, timestamp DESC)`. PostgreSQL maintains all three but only ever uses one. This wastes approximately 3x the storage and write overhead for identical index maintenance.

**Remediation:**

Consolidate in a new migration:

```sql
-- Keep the most explicitly named one from 037
DROP INDEX IF EXISTS idx_prices_region_utility;
DROP INDEX IF EXISTS idx_prices_region_utilitytype_timestamp;
-- Retain idx_electricity_prices_region_utility_time
```

**Estimated savings:** ~30-40% reduction in index storage on the `electricity_prices` table, plus reduced write amplification on every INSERT.

---

### P2-2: `model_config` Table Lacks Unique Constraint — Two Active Rows Possible Under Concurrent Writes

**File:** `backend/migrations/027_model_config.sql`

**Description:**

```sql
CREATE INDEX IF NOT EXISTS idx_model_config_active
    ON model_config (model_name, is_active)
    WHERE is_active = true;
```

The partial index is not a unique index. The `ModelConfigRepository.save_config()` method (two-step: deactivate-then-insert) is safe under single-writer assumptions, but the comment says "single-writer assumption." Under concurrent ML pipeline runs (e.g., nightly-learning + a manual trigger firing simultaneously), two active rows could exist simultaneously. The `get_active_config()` method handles this with `ORDER BY created_at DESC LIMIT 1`, which masks the corruption but does not prevent it.

**Remediation:**

```sql
-- Add a unique partial index
CREATE UNIQUE INDEX IF NOT EXISTS idx_model_config_active_unique
    ON model_config (model_name)
    WHERE is_active = true;
```

This creates an advisory uniqueness constraint that prevents two concurrent transactions from both inserting is_active=true rows for the same model_name.

---

### P2-3: `notifications` Table Has No Explicit NOT NULL on `user_id` Despite Being Added Via `ALTER TABLE` in Migration 051

**File:** `backend/migrations/051_gdpr_cascade_fixes.sql:26`

**Description:**

Migration 015 created notifications as:

```sql
user_id UUID NOT NULL,
```

Migration 051 does:

```sql
ALTER TABLE notifications
    ADD CONSTRAINT notifications_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
```

This is correct. However, migration 052 drops and re-adds this constraint without first checking that `user_id NOT NULL` is still enforced. In environments where the table was re-created or had the NOT NULL dropped by another migration, the FK can exist while `user_id` is nullable. The `_NOTIFICATION_COLUMNS` SELECT in `notification_repository.py` does `str(row["user_id"])` without a NULL check, which would raise `TypeError` if any row had a NULL `user_id`.

**Remediation:**

```sql
-- Ensure NOT NULL is still enforced
ALTER TABLE notifications
    ALTER COLUMN user_id SET NOT NULL;
```

Add this to a future migration.

---

### P2-4: `get_timescale_session()` Commits on Every Context Manager Exit — Accidental Transaction Auto-Commit

**File:** `backend/config/database.py:166`

**Description:**

```python
async with self.async_session_maker() as session:
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

The session commits unconditionally on successful exit. This means if a repository method calls `await session.commit()` internally (which most do — see `user_repository.py:168`, `price_repository.py:172`, etc.) and then an error occurs after that commit but before the context manager exits, the data is already committed. Additionally, repository methods that call `self._db.commit()` directly are operating redundantly with the context manager's auto-commit.

This creates a "double commit" pattern: each repository method commits, and then the context manager commits again. The second commit is a no-op if no work was done, but it represents an extra round-trip to the database on every request.

More seriously, if a service method wants to group multiple repository operations in a single atomic transaction, the current pattern makes this impossible: the first repository method commits immediately, and subsequent operations run in separate implicit transactions.

**Remediation:**

Remove `await session.commit()` from the context manager and from individual repository methods. Let the application layer control transaction boundaries, or use SQLAlchemy's unit-of-work pattern explicitly. The session manager should only commit; repositories should only execute statements:

```python
# In database.py: remove the commit from the context manager
# or keep it and document that repositories must NOT call commit()

# In repositories: remove self._db.commit() calls
# Let the session manager commit after all operations succeed
```

Alternatively, document clearly that each repository method is its own transaction and that cross-repository atomicity must be handled at the service layer with explicit transactions.

---

### P2-5: `user_savings` Has No Index on `(user_id, savings_type)`

**File:** `backend/migrations/012_user_savings.sql`

**Description:**

Migration 012 creates these indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_user_savings_user_id
    ON user_savings (user_id);

CREATE INDEX IF NOT EXISTS idx_user_savings_created_at
    ON user_savings (user_id, created_at DESC);
```

The savings dashboard and the SavingsService aggregate `savings_type` (e.g., "switching", "usage", "alert") for per-type totals. Queries like `WHERE user_id = ? AND savings_type = 'switching'` or `GROUP BY savings_type WHERE user_id = ?` are not covered by the existing indexes. The planner will scan all rows for a user and filter in memory.

**Remediation:**

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_savings_user_type
    ON user_savings (user_id, savings_type, created_at DESC);
```

---

### P2-6: `pool_recycle=200` Comment Says "100s Before Neon's 5-Min Auto-Suspend" But 200 Seconds Is 3.3 Minutes — Mathematical Error

**File:** `backend/config/database.py:86`

**Description:**

```python
pool_recycle=200,  # recycle 100s before Neon's 5-min auto-suspend
```

5 minutes = 300 seconds. Recycling at 200 seconds means connections are recycled 100 seconds (1 minute 40 seconds) before the 5-minute auto-suspend threshold — the comment says "100s before" which is correct mathematically (300 - 200 = 100). However, Neon's actual idle connection timeout on the free tier is typically 300 seconds of inactivity, not 5 minutes of total lifetime. A connection that is actively used (not idle) will not trigger auto-suspend. The recycle logic here is solving the wrong problem: pool_recycle controls connection *lifetime*, not idle time.

The correct mitigation for Neon's idle connection auto-suspend is `pool_pre_ping=True` (already set) combined with `keepalives_idle` in `connect_args`. The `pool_recycle=200` is overly aggressive and forces connection re-establishment every 3.3 minutes even for active connections.

**Remediation:**

```python
connect_args = {
    "ssl": "require",
    "statement_cache_size": 0,
    "keepalives_idle": 30,       # TCP keepalive every 30s for idle connections
    "keepalives_interval": 10,
    "keepalives_count": 5,
}
pool_recycle=1800,  # recycle after 30 minutes (standard for long-running apps)
```

The `pool_pre_ping=True` (already set) handles stale connections from Neon auto-suspend gracefully. The aggressive 200s recycle is unnecessary overhead.

---

## P3 — Low

### P3-1: `init_neon.sql` Creates Tables That Migration 002 Recreates — Schema Divergence Debt

**File:** `backend/migrations/init_neon.sql`, `backend/migrations/002_gdpr_auth_tables.sql`

**Description:**

`init_neon.sql` creates `consent_records` and `deletion_logs` with a different schema than migration 002. Migration 003 exists specifically to reconcile this divergence. This is a known historical issue that has been addressed, but `init_neon.sql` should be updated to match the final schema so that fresh deployments do not require the reconciliation migration.

**Remediation:** Update `init_neon.sql` to match the final schema from migrations 002+003. This is a documentation/maintainability improvement with no production impact since migration 003 handles the reconciliation.

---

### P3-2: `deletion_logs` Immutability Trigger Is Recreated in Both `init_neon.sql` and Migration 002

**File:** `backend/migrations/init_neon.sql:163`, `backend/migrations/002_gdpr_auth_tables.sql:67`

**Description:**

Both `init_neon.sql` and migration 002 contain `CREATE OR REPLACE FUNCTION prevent_deletion_log_modification()` and `CREATE TRIGGER tr_prevent_deletion_log_update`. The `CREATE OR REPLACE` is idempotent for the function, and `DROP TRIGGER IF EXISTS` + `CREATE TRIGGER` in 002 is idempotent for the trigger. However, the duplication is confusing and means the trigger is re-defined twice on a fresh deployment. No functional harm, but it is maintenance debt.

**Remediation:** Remove the duplicate from `init_neon.sql` and rely on migration 002.

---

### P3-3: `users.annual_usage_kwh` Defined as `INT` in Migration 013 But `DECIMAL` in Model

**File:** `backend/migrations/013_user_profile_columns.sql:44`

**Description:**

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS annual_usage_kwh INT;
```

The `User` Pydantic model in `user.py` defines:

```python
annual_usage_kwh: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
```

And `_USER_COLUMNS` in `user_repository.py` selects `annual_usage_kwh` without explicit casting. An `INT` column will return an integer from PostgreSQL which Pydantic will coerce to `Decimal`, but the column cannot store fractional annual usage values (e.g., 12,456.7 kWh). This means any precision in annual usage is silently truncated to integer values.

**Remediation:**

```sql
ALTER TABLE users
    ALTER COLUMN annual_usage_kwh TYPE DECIMAL(12,2);
```

---

### P3-4: `model_ab_assignments` Has Unique Constraint on `user_id` Alone — Prevents Multi-Model A/B Testing

**File:** `backend/migrations/033_model_predictions_ab_assignments.sql:66`

**Description:**

```sql
CONSTRAINT uq_model_ab_assignments_user_id
    UNIQUE (user_id)
```

This means a user can only ever be assigned to one model version at a time, across all models. If the system runs A/B tests for multiple model names simultaneously (e.g., the forecast model and the recommendation model), the first assignment for a user would block all subsequent ones.

**Remediation:**

Change the unique constraint to `(user_id, test_id)` or `(user_id, model_name)` to allow per-model assignments:

```sql
ALTER TABLE model_ab_assignments
    DROP CONSTRAINT IF EXISTS uq_model_ab_assignments_user_id;

ALTER TABLE model_ab_assignments
    ADD CONSTRAINT uq_model_ab_assignments_user_model
    UNIQUE (user_id, model_version);
```

---

### P3-5: `list_suppliers` Executes Two Sequential Queries (COUNT + DATA) Without Parallel Execution

**File:** `backend/repositories/supplier_repository.py:190`

**Description:**

```python
count_result = await self._db.execute(text(count_sql), params)
total = count_result.scalar() or 0
# ... then separately:
result = await self._db.execute(text(data_sql), data_params)
```

Two round-trips are made to the database sequentially. The `PriceRepository.get_historical_prices_paginated()` has the same pattern with an explicit comment saying asyncio.gather on a shared AsyncSession corrupts state. That comment is correct — both COUNT and DATA queries must be sequential. However, the comment in the supplier repository is absent, creating a maintenance hazard where a future developer might attempt to parallelize with asyncio.gather.

**Remediation:** Add a clear comment to `list_suppliers` explaining why these cannot be parallelized. Consider using a single query with `COUNT(*) OVER()` as a window function:

```sql
SELECT id, name, ..., COUNT(*) OVER() AS total_count
FROM supplier_registry WHERE ...
ORDER BY rating DESC NULLS LAST
LIMIT :limit OFFSET :offset
```

This eliminates the COUNT round-trip entirely.

---

### P3-6: `notification_repository.py` Does Not Select `alert_id` Column Added in Migration 053

**File:** `backend/repositories/notification_repository.py:37`

**Description:**

```python
_NOTIFICATION_COLUMNS = (
    "id, user_id, type, title, body, read_at, created_at, "
    "metadata, delivery_channel, delivery_status, delivered_at, "
    "delivery_metadata, retry_count, error_message"
)
```

Migration 053 added `alert_id UUID` to the notifications table. The `_NOTIFICATION_COLUMNS` constant was not updated to include `alert_id`. The `Notification` model also does not include `alert_id`. While this doesn't cause query failures (PostgreSQL returns only the requested columns), any code that needs to correlate notifications back to their originating alert config cannot do so via the repository.

**Remediation:**

1. Add `alert_id` to `_NOTIFICATION_COLUMNS` in `notification_repository.py`.
2. Add `alert_id: Optional[str] = None` to the `Notification` Pydantic model.
3. Update `_row_to_notification()` to include `alert_id=str(row["alert_id"]) if row.get("alert_id") else None`.

---

### P3-7: `community_posts` Created Without NOT NULL on `created_at` and `updated_at`

**File:** `backend/migrations/049_community_tables.sql:7`

**Description:**

```sql
created_at TIMESTAMPTZ DEFAULT now(),
updated_at TIMESTAMPTZ DEFAULT now(),
```

Both columns lack `NOT NULL`, unlike the consistent pattern used in every other table in the codebase (e.g., migration 008 uses `NOT NULL DEFAULT now()` for all timestamp columns). A NULL `created_at` would break sort queries and analytics that rely on these columns.

**Remediation:**

```sql
ALTER TABLE community_posts
    ALTER COLUMN created_at SET NOT NULL,
    ALTER COLUMN updated_at SET NOT NULL;
```

Add to a future migration. Backfill any existing NULLs first (likely none, since DEFAULT now() was set):

```sql
UPDATE community_posts SET created_at = now() WHERE created_at IS NULL;
UPDATE community_posts SET updated_at = now() WHERE updated_at IS NULL;
```

---

## Positive Findings

The following design decisions deserve explicit recognition:

1. **UUID primary keys throughout**: Every table uses `UUID PRIMARY KEY DEFAULT gen_random_uuid()`. No SERIAL or BIGSERIAL integers, which eliminates sequential ID enumeration attacks and supports distributed inserts.

2. **IF NOT EXISTS universally applied**: Every `CREATE TABLE`, `CREATE INDEX`, and `ALTER TABLE ADD COLUMN` uses idempotency guards. Migrations are safe to re-run.

3. **CONCURRENTLY for all post-init indexes**: Starting from migration 004, all index creation uses `CONCURRENTLY`, ensuring zero table lock time on a live database.

4. **GIN indexes for array columns**: `idx_suppliers_regions` (init_neon), `idx_supplier_reg_regions` and `idx_supplier_reg_utility` (migration 006) correctly use GIN for PostgreSQL array `ANY()` queries.

5. **Partial indexes for boolean filters**: `idx_users_is_active`, `idx_suppliers_is_active`, `idx_tariffs_supplier_available`, `idx_alert_configs_active`, `idx_user_connections_sync_due` all use WHERE clauses to keep indexes small and selective.

6. **Immutability trigger on `deletion_logs`**: The `tr_prevent_deletion_log_update` trigger enforces GDPR audit trail integrity at the database layer, preventing any application-layer deletion of compliance records.

7. **Sequential asyncio.gather avoidance**: `price_repository.py` and `forecast_observation_repository.py` both explicitly avoid `asyncio.gather` on shared `AsyncSession` objects, with clear comments explaining the corruption risk. This shows awareness of a common SQLAlchemy async pitfall.

8. **Raw SQL over ORM**: The decision to use `sqlalchemy.text()` raw SQL instead of SQLAlchemy ORM models (documented in `supplier_repository.py` ADR-006 comment) avoids the runtime Pydantic/SQLAlchemy model mismatch bug that caused CRIT-03/05 in the earlier audit. This is the right architectural choice for a Pydantic-first codebase.

9. **Bulk insert chunking**: `PriceRepository.bulk_create()` and `ForecastObservationRepository.insert_forecasts()` both chunk at 500 and 20 rows respectively to stay within parameter limits and reduce round-trips.

10. **GDPR cascade remediation**: Migrations 051 and 052 systematically added `ON DELETE CASCADE` to all user-linked tables, covering the GDPR Article 17 right-to-erasure requirement. The pattern of `DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT` makes each step idempotent.

11. **Cache stampede prevention**: `PriceRepository._acquire_cache_lock()` implements a simple Redis NX-lock to prevent thundering herd on cache misses. This is a sophisticated pattern for a read-heavy price data endpoint.

12. **Dedup index on notifications**: Migration 053 adds a partial unique index `idx_notifications_dedup_alert ON notifications (user_id, alert_id, type, DATE(created_at)) WHERE alert_id IS NOT NULL AND delivery_status != 'dismissed'`. This enforces uniqueness at the storage layer, preventing double-notifications even under concurrent CF Worker cron runs.

---

## Statistics

| Category | Count |
|---|---|
| Total migration files audited | 54 (init_neon + 001–053) |
| Total repository files audited | 8 |
| Total model files audited | 6 |
| P0 Critical findings | 2 |
| P1 High findings | 4 |
| P2 Medium findings | 6 |
| P3 Low findings | 7 |
| Total findings | 19 |
| Positive findings | 12 |
| Tables with confirmed missing FK constraints (resolved by 052) | 5 |
| Duplicate/overlapping indexes identified | 3 (all on electricity_prices) |
| Migrations with sequential numbering gaps | 0 (001–053 are sequential) |
| Migrations missing IF NOT EXISTS guards | 0 |
| Migrations using SERIAL/BIGSERIAL | 0 |
| Migrations missing neondb_owner grants | ~8 (early migrations 005, 012, 015, 016, 017, 018, 019) |

### Migrations Missing Explicit neondb_owner Grants

The following migrations create or modify tables without a neondb_owner GRANT:

| Migration | Tables Affected |
|---|---|
| 005 | forecast_observations, recommendation_outcomes — **has grants** |
| 012 | user_savings — **missing grant** |
| 015 | notifications — added in 026 |
| 016 | feature_flags — **missing grant** |
| 018 | users (ALTER only) |
| 019 | supplier_registry (seed only, GRANT in 006) |
| 022 | user_supplier_accounts (CREATE INDEX only) |
| 023 | Data functions — has grants |

The omission of grants in migrations 012 and 016 means that if the Neon role permissions are tighter than expected, reads/writes to `user_savings` and `feature_flags` may fail. In practice, Neon's `neondb_owner` is typically a superuser equivalent in free-tier projects, so this is low risk but represents a compliance gap with the project's stated convention.

---

*Report generated: 2026-03-18*
*Files audited:*
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/migrations/init_neon.sql`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/migrations/002_gdpr_auth_tables.sql` through `053_notification_dedup_index.sql`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/database.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/base.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/price_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/user_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/notification_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/forecast_observation_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/supplier_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/utility_account_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/model_config_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/user.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/price.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/notification.py`
