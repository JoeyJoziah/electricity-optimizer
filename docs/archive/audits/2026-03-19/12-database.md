# Audit Report: Database Layer

**Date:** 2026-03-19
**Scope:** Migrations (55 SQL files), schema design, Pydantic models (16 files), repository query patterns (9 files), ORM compliance layer (1 file)
**Files Reviewed:**

**Migrations (55 files):**
- `backend/migrations/init_neon.sql`
- `backend/migrations/002_gdpr_auth_tables.sql`
- `backend/migrations/003_reconcile_schema.sql`
- `backend/migrations/004_performance_indexes.sql`
- `backend/migrations/005_observation_tables.sql`
- `backend/migrations/006_multi_utility_expansion.sql`
- `backend/migrations/007_user_supplier_accounts.sql`
- `backend/migrations/008_connection_feature.sql`
- `backend/migrations/009_email_oauth_tokens.sql`
- `backend/migrations/010_utility_type_index.sql`
- `backend/migrations/011_utilityapi_sync_columns.sql`
- `backend/migrations/012_user_savings.sql`
- `backend/migrations/013_user_profile_columns.sql`
- `backend/migrations/014_alert_tables.sql`
- `backend/migrations/015_notifications.sql`
- `backend/migrations/016_feature_flags.sql`
- `backend/migrations/017_additional_indexes.sql`
- `backend/migrations/018_nationwide_defaults.sql`
- `backend/migrations/019_nationwide_suppliers.sql`
- `backend/migrations/020_price_query_indexes.sql`
- `backend/migrations/021_fix_supplier_api_available.sql`
- `backend/migrations/022_user_supplier_composite_index.sql`
- `backend/migrations/023_db_audit_indexes.sql`
- `backend/migrations/024_payment_retry_history.sql`
- `backend/migrations/025_data_cache_tables.sql`
- `backend/migrations/026_notifications_metadata.sql`
- `backend/migrations/027_model_config.sql`
- `backend/migrations/028_feedback_table.sql`
- `backend/migrations/029_notification_delivery_tracking.sql`
- `backend/migrations/030_model_versioning_ab_tests.sql`
- `backend/migrations/031_agent_tables.sql`
- `backend/migrations/032_notification_error_message.sql`
- `backend/migrations/033_model_predictions_ab_assignments.sql`
- `backend/migrations/034_portal_credentials.sql`
- `backend/migrations/035_backfill_neon_auth_users.sql`
- `backend/migrations/036_performance_indexes.sql`
- `backend/migrations/037_additional_performance_indexes.sql`
- `backend/migrations/038_utility_accounts.sql`
- `backend/migrations/039_referrals.sql`
- `backend/migrations/040_gas_supplier_seed.sql`
- `backend/migrations/041_community_solar_programs.sql`
- `backend/migrations/042_cca_programs.sql`
- `backend/migrations/043_heating_oil.sql`
- `backend/migrations/044_multi_utility_alerts.sql`
- `backend/migrations/045_affiliate_tracking.sql`
- `backend/migrations/046_propane_prices.sql`
- `backend/migrations/047_water_rates.sql`
- `backend/migrations/048_utility_feature_flags.sql`
- `backend/migrations/049_community_tables.sql`
- `backend/migrations/050_community_posts_indexes.sql`
- `backend/migrations/051_gdpr_cascade_fixes.sql`
- `backend/migrations/052_fk_gdpr_cascade_round2.sql`
- `backend/migrations/053_notification_dedup_index.sql`
- `backend/migrations/054_stripe_processed_events.sql`
- `backend/migrations/055_fix_invalid_indexes.sql`

**Models (16 files):**
- `backend/models/__init__.py`
- `backend/models/community.py`
- `backend/models/connections.py`
- `backend/models/consent.py`
- `backend/models/model_config.py`
- `backend/models/model_version.py`
- `backend/models/notification.py`
- `backend/models/observation.py`
- `backend/models/price.py`
- `backend/models/region.py`
- `backend/models/regulation.py`
- `backend/models/supplier.py`
- `backend/models/user.py`
- `backend/models/user_supplier.py`
- `backend/models/utility.py`
- `backend/models/utility_account.py`

**Repositories (9 files):**
- `backend/repositories/__init__.py`
- `backend/repositories/base.py`
- `backend/repositories/forecast_observation_repository.py`
- `backend/repositories/model_config_repository.py`
- `backend/repositories/notification_repository.py`
- `backend/repositories/price_repository.py`
- `backend/repositories/supplier_repository.py`
- `backend/repositories/user_repository.py`
- `backend/repositories/utility_account_repository.py`

**Compliance ORM (1 file):**
- `backend/compliance/repositories.py`

---

## P0 -- Critical (Fix Immediately)

### P0-01: Ghost columns -- `stripe_customer_id` and `subscription_tier` never created in any migration

**Files:** `backend/repositories/user_repository.py` (lines 28, 57-58, 136-160, 189-190, 415-421), `backend/models/user.py` (User model), `backend/migrations/004_performance_indexes.sql` (lines 10-12)

**Problem:** The `users` table is created in `init_neon.sql` (line 29) with columns: `id`, `email`, `name`, `region`, `preferences`, `current_supplier`, `is_active`, `is_verified`, `created_at`, `updated_at`. No migration ever adds `stripe_customer_id` or `subscription_tier` columns to the `users` table via `ALTER TABLE ADD COLUMN`. However:

- `user_repository.py` line 28 includes both in `_USER_COLUMNS`
- `user_repository.py` lines 57-58 reads them in `_row_to_user()`
- `user_repository.py` lines 136-160 inserts/selects them in `create()`
- `user_repository.py` lines 189-190 includes them in `_UPDATABLE_COLUMNS`
- `user_repository.py` line 415 queries `WHERE stripe_customer_id = :customer_id` in `get_by_stripe_customer_id()`
- `004_performance_indexes.sql` line 10 creates an index on `stripe_customer_id` -- an index on a column that has no CREATE/ALTER statement in the migration history

**Impact:** If these columns were added out-of-band (e.g., manually in production), the migration history is incomplete and unreproducible. A fresh database deployed from migrations alone will fail at migration 004 (index on non-existent column) and at runtime when the repository queries these columns. This breaks deployment reproducibility.

**Fix:** Add a migration that creates both columns:
```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(20) NOT NULL DEFAULT 'free';
```

---

### P0-02: Ghost column -- `carbon_intensity` never created on `electricity_prices`

**Files:** `backend/repositories/price_repository.py` (lines 24-26, 42-44, 164-181, 216-231, 659-672), `backend/models/price.py` (Price model), `backend/migrations/init_neon.sql` (lines 50-60)

**Problem:** The `electricity_prices` table (init_neon.sql line 50) does not include a `carbon_intensity` column. No migration adds it via `ALTER TABLE`. However:

- `price_repository.py` line 26 includes `carbon_intensity` in `_PRICE_COLUMNS`
- `price_repository.py` lines 42-44 reads it in `_row_to_price()`
- `price_repository.py` lines 164-181 inserts it in `create()`
- `price_repository.py` lines 216-231 updates it in `update()`
- `price_repository.py` lines 659-672 batch-inserts it in `bulk_create()`
- `models/price.py` declares `carbon_intensity: float | None = None`

**Impact:** Same as P0-01. A fresh database will fail at runtime with `column "carbon_intensity" does not exist` on any price insert/select. The column also lacks a NOT NULL constraint rationale and has no type documented in any migration.

**Fix:** Add a migration:
```sql
ALTER TABLE electricity_prices ADD COLUMN IF NOT EXISTS carbon_intensity DECIMAL(8, 4);
```

---

### P0-03: ORM FK mismatch -- `ConsentRecordORM` declares `CASCADE` but live schema uses `SET NULL`

**Files:** `backend/compliance/repositories.py` (line 30), `backend/migrations/023_db_audit_indexes.sql` (lines 30-57)

**Problem:** The ORM model at `compliance/repositories.py` line 30 declares:
```python
String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
```

But migration 023 (lines 30-57) explicitly changed this FK from `CASCADE` to `SET NULL` and made `user_id` nullable. The migration comment on line 32 explains: "ON DELETE CASCADE destroys consent audit trail when user is erased."

This is a semantic conflict: the ORM says "cascade delete consent records when user is deleted" while the actual database says "set user_id to NULL and preserve the audit trail." If SQLAlchemy's ORM ever issues DDL based on this model (e.g., `create_all()` in tests), it will create the wrong constraint.

**Impact:** GDPR Article 7 compliance requires preserving consent audit trail after user erasure. The ORM model would silently destroy that trail if used for schema creation.

**Fix:** Update `compliance/repositories.py` line 30 to match the live schema:
```python
String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
```

---

### P0-04: OAuth tokens stored as plaintext TEXT while other credentials use BYTEA encryption

**Files:** `backend/migrations/009_email_oauth_tokens.sql` (lines 5-6), `backend/migrations/007_user_supplier_accounts.sql` (lines 14-15), `backend/migrations/034_portal_credentials.sql` (line 31), `backend/migrations/008_connection_feature.sql` (line 28)

**Problem:** Migration 009 adds OAuth token columns as plaintext `TEXT`:
```sql
ADD COLUMN IF NOT EXISTS oauth_access_token TEXT,
ADD COLUMN IF NOT EXISTS oauth_refresh_token TEXT,
```

Meanwhile, all other sensitive credential columns use `BYTEA` with AES-256-GCM encryption:
- `007`: `account_number_encrypted BYTEA`, `meter_number_encrypted BYTEA`
- `008`: `account_number_encrypted BYTEA`
- `034`: `portal_password_encrypted BYTEA`
- `011`: `utilityapi_auth_uid_encrypted BYTEA`

OAuth access/refresh tokens grant full API access to user email accounts (Gmail/Outlook). Storing them as plaintext TEXT is inconsistent with the project's encryption-at-rest strategy and represents a credential exposure risk if the database is compromised.

**Impact:** Database breach exposes all OAuth tokens in cleartext, enabling email account takeover.

**Fix:** Add a migration to convert these columns to `BYTEA` and encrypt existing values using the same AES-256-GCM scheme used for other credentials. Update the connection models and services to encrypt/decrypt on read/write.

---

## P1 -- High (Fix This Sprint)

### P1-01: Missing `updated_at` auto-update triggers on 15+ tables

**Files:** `backend/migrations/init_neon.sql` (lines 194-207), `backend/migrations/049_community_tables.sql` (lines 52-62)

**Problem:** The `update_updated_at_column()` trigger function is created in `init_neon.sql` (line 194), but triggers are only attached to 2 tables:
1. `users` -- `trigger_users_updated_at` (init_neon.sql line 204)
2. `community_posts` -- `trg_community_posts_updated_at` (049 line 60)

The following tables have `updated_at TIMESTAMPTZ` columns but **no auto-update trigger**:
- `supplier_registry` (006 line 52)
- `state_regulations` (006 line 77)
- `user_supplier_accounts` (007 line 21)
- `user_connections` (008 line 42)
- `bill_uploads` (008 line 85)
- `feature_flags` (016 line 10)
- `price_alert_configs` (014 line 36)
- `model_config` (027 line 18)
- `feedback` (028 line 27)
- `alert_preferences` (044 line 68)
- `payment_retry_history` (024 line 33)
- `utility_accounts` (038 line 18)
- `water_rates` (047 line 15)
- `cca_programs` (042 line 17)
- `community_solar_programs` (041 line 18)

**Impact:** `updated_at` values are stale for most tables unless the application layer explicitly sets them. Some repositories do set `updated_at = now()` in their SQL (e.g., `utility_account_repository.py` line 95, `user_repository.py` line 211), but this is inconsistent and easy to forget. Any UPDATE path that does not explicitly set `updated_at` will leave a stale value, making audit trails and cache invalidation unreliable.

**Fix:** Add a single migration that attaches the existing `update_updated_at_column()` trigger to all tables with an `updated_at` column.

---

### P1-02: Missing `NOT NULL` on timestamp columns in community tables

**Files:** `backend/migrations/049_community_tables.sql` (lines 23-24, 30, 38)

**Problem:** The `community_posts`, `community_votes`, and `community_reports` tables define timestamp columns with `DEFAULT now()` but without `NOT NULL`:
```sql
-- community_posts (line 23-24)
created_at TIMESTAMPTZ DEFAULT now(),
updated_at TIMESTAMPTZ DEFAULT now()

-- community_votes (line 30)
created_at TIMESTAMPTZ DEFAULT now(),

-- community_reports (line 38)
created_at TIMESTAMPTZ DEFAULT now(),
```

Every other table in the schema that has `created_at` or `updated_at` uses `NOT NULL DEFAULT now()`. Without `NOT NULL`, an explicit `INSERT ... (created_at) VALUES (NULL)` succeeds and stores NULL, which breaks ORDER BY queries, reporting, and the `idx_community_posts_region_utility` partial index (which includes `created_at DESC`).

**Impact:** NULL timestamps break pagination ordering, analytics queries, and index-only scans on the community posts index.

**Fix:**
```sql
ALTER TABLE community_posts ALTER COLUMN created_at SET NOT NULL;
ALTER TABLE community_posts ALTER COLUMN updated_at SET NOT NULL;
ALTER TABLE community_votes ALTER COLUMN created_at SET NOT NULL;
ALTER TABLE community_reports ALTER COLUMN created_at SET NOT NULL;
```

---

### P1-03: Data type mismatch -- `users.annual_usage_kwh` is `INT` in migration but `Decimal` in model

**Files:** `backend/migrations/013_user_profile_columns.sql` (line 44), `backend/models/user.py` (User model)

**Problem:** Migration 013 creates the column as:
```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS annual_usage_kwh INT;
```

But the Pydantic model declares:
```python
annual_usage_kwh: Decimal | None = None
```

PostgreSQL `INT` is a 32-bit integer (range -2,147,483,648 to 2,147,483,647). Python `Decimal` can represent arbitrary precision fractional values. If a user submits `annual_usage_kwh = 12500.5`, the repository will attempt to store a decimal in an INT column, which PostgreSQL will silently truncate to `12500` (or raise an error depending on the driver).

**Impact:** Silent data truncation on fractional kWh values. While annual kWh is typically an integer, the model contract promises Decimal precision that the database does not support.

**Fix:** Either change the model type to `int | None` to match the DB, or alter the column to `DECIMAL(10, 2)` if fractional values are needed.

---

### P1-04: Duplicate index creation across migrations

**Files:** `backend/migrations/004_performance_indexes.sql` (lines 10-12), `backend/migrations/037_additional_performance_indexes.sql` (lines 18-21)

**Problem:** Both migrations create the exact same index:
```sql
-- 004 (line 10-12)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_stripe_customer_id
    ON users (stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

-- 037 (lines 18-21)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_stripe_customer_id
    ON users (stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;
```

The `IF NOT EXISTS` guard means this is not a runtime error, but it clutters the migration history and wastes execution time on `CREATE INDEX CONCURRENTLY` (which takes a lock even when the index exists).

Additionally, the `electricity_prices` table has overlapping indexes across multiple migrations:
- `init_neon.sql`: `idx_prices_region_timestamp ON (region, timestamp)`
- `006`: `idx_prices_region_utility ON (region, utility_type, created_at)`
- `010`: `idx_prices_region_utilitytype_timestamp ON (region, utility_type, timestamp)`
- `020`: `idx_prices_region_util_time ON (region, utility_type, timestamp DESC)`
- `037`: `idx_electricity_prices_region_utility_time ON (region, utility_type, timestamp DESC)`

The last two (`020` and `037`) are functionally identical (same columns, same DESC ordering). The planner will only use one, and the other wastes disk space and slows writes.

**Impact:** Write performance degradation from maintaining redundant indexes. Disk space waste.

**Fix:** Add a migration that drops the duplicates: `DROP INDEX IF EXISTS idx_prices_region_util_time;` (keep the 037 version or vice versa). Also remove the duplicate `idx_users_stripe_customer_id` creation from 037.

---

### P1-05: Migration numbering conflict -- two files claim to be "Migration 010"

**Files:** `backend/migrations/010_utility_type_index.sql` (line 1), `backend/migrations/011_utilityapi_sync_columns.sql` (line 1)

**Problem:**
- `010_utility_type_index.sql` line 1: `-- Migration 010: Index for multi-utility price queries`
- `011_utilityapi_sync_columns.sql` line 1: `-- Migration 010: Add UtilityAPI sync columns to user_connections`

File 011 has the correct filename (011) but its header comment says "Migration 010". This indicates a copy-paste error during migration creation. While the file naming is correct (the files are sorted by filename, not by header comment), it creates confusion when auditing or debugging migration history.

**Impact:** Confusion during migration audits. Low runtime risk since migrations are applied by filename order.

**Fix:** Update the comment in `011_utilityapi_sync_columns.sql` line 1 to say `-- Migration 011`.

---

### P1-06: Overly broad `GRANT ALL` in migration 037

**Files:** `backend/migrations/037_additional_performance_indexes.sql` (end of file)

**Problem:** Migration 037 includes:
```sql
GRANT ALL ON ALL TABLES IN SCHEMA public TO neondb_owner;
```

This grants `SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER` on every table (including `deletion_logs` which has an immutability trigger, and `stripe_processed_events` which should be append-only) to the `neondb_owner` role. All other migrations use table-specific grants like `GRANT SELECT, INSERT, UPDATE ON <table> TO neondb_owner`.

**Impact:** Principle of least privilege violation. The `neondb_owner` role can now TRUNCATE or trigger-manage any table, bypassing immutability guards on audit tables.

**Fix:** Replace with table-specific grants. At minimum, remove `TRUNCATE` and `TRIGGER` from the grant for audit tables (`deletion_logs`, `consent_records`, `stripe_processed_events`).

---

### P1-07: `utility_accounts` table missing FK on `user_id`

**Files:** `backend/migrations/038_utility_accounts.sql` (lines 10-19), `backend/migrations/052_fk_gdpr_cascade_round2.sql`

**Problem:** Migration 038 creates the `utility_accounts` table:
```sql
CREATE TABLE IF NOT EXISTS utility_accounts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    ...
);
```

The `user_id` column is `NOT NULL` but has no `REFERENCES users(id)` foreign key constraint. Migration 052 (the GDPR cascade round 2) adds FKs for `user_savings`, `recommendation_outcomes`, `model_predictions`, `model_ab_assignments`, and `referrals` -- but does NOT add one for `utility_accounts`.

**Impact:** Orphaned utility_account rows can exist for deleted users. GDPR Article 17 erasure will not cascade to utility_accounts, leaving personal data behind. The `utility_account_repository.py` `delete()` method (line 112) only deletes by ID, not by user_id, so there is no programmatic cleanup path during user deletion unless the GDPR deletion service explicitly handles it.

**Fix:** Add a migration:
```sql
ALTER TABLE utility_accounts
    ADD CONSTRAINT utility_accounts_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
```

---

### P1-08: `feedback` table missing FK on `user_id`

**Files:** `backend/migrations/028_feedback_table.sql`

**Problem:** The `feedback` table has a `user_id UUID` column but no FK constraint to `users(id)`. This table was not addressed in either migration 051 or 052 (the GDPR cascade fix rounds).

**Impact:** Same GDPR Article 17 risk as P1-07. User deletion does not cascade to feedback records.

**Fix:** Add a FK with appropriate ON DELETE behavior (CASCADE if feedback should be deleted with user, SET NULL if feedback should be anonymized).

---

### P1-09: `alert_history` and `price_alert_configs` tables missing FK constraints

**Files:** `backend/migrations/014_alert_tables.sql`

**Problem:** Migration 014 creates `price_alert_configs` and `alert_history` tables with `user_id UUID NOT NULL` columns but no FK constraints to `users(id)`. Neither was addressed in migrations 051 or 052.

**Impact:** Orphaned alert records after user deletion. GDPR non-compliance for alert configuration data (which contains user-specific thresholds and preferences).

**Fix:** Add CASCADE FKs for both tables.

---

## P2 -- Medium (Fix Soon)

### P2-01: `DeletionLogORM` declares `user_id` as `nullable=False` -- deletion logs cannot survive user erasure

**Files:** `backend/compliance/repositories.py` (line 51)

**Problem:** The `DeletionLogORM` model declares:
```python
user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
```

By nature, deletion logs record that a user WAS deleted. If the `user_id` FK has CASCADE behavior and `nullable=False`, then deleting the user would either (a) cascade-delete the deletion log (destroying the audit trail) or (b) fail with a FK violation. The `deletion_logs` table has an immutability trigger (`prevent_deletion_log_changes` in init_neon.sql) that blocks DELETE/UPDATE, which would cause a FK violation error during user CASCADE deletion.

Looking at the actual migration (`init_neon.sql`), `deletion_logs.user_id` is defined as `VARCHAR(36) NOT NULL` with no FK constraint, so the ORM model's `ForeignKey("users.id")` declaration is adding a constraint that does not exist in the database.

**Impact:** If the ORM is used to create the schema (e.g., in tests), the FK constraint will conflict with the immutability trigger and break GDPR erasure flows.

**Fix:** Remove the `ForeignKey("users.id")` from the ORM model, or ensure it matches the production schema (no FK, just stores the user_id as a plain string for the audit record).

---

### P2-02: `model_config` missing `is_active NOT NULL` in original migration

**Files:** `backend/migrations/027_model_config.sql` (line 16), `backend/migrations/052_fk_gdpr_cascade_round2.sql` (lines 56-72)

**Problem:** Migration 027 creates `is_active BOOLEAN DEFAULT false` without NOT NULL. Migration 052 retroactively fixes this with `SET NOT NULL`. However, `created_at` and `updated_at` in 027 also lack NOT NULL (lines 17-18), and 052 fixes those too. This means there was a window where NULL values could be inserted.

**Status:** Fixed in migration 052. No remaining runtime risk. Noted for completeness.

---

### P2-03: `community_posts.user_id` FK originally lacked CASCADE

**Files:** `backend/migrations/049_community_tables.sql` (line 12), `backend/migrations/051_gdpr_cascade_fixes.sql`

**Problem:** Migration 049 creates `community_posts` with:
```sql
user_id UUID NOT NULL REFERENCES users(id),
```
This defaults to `ON DELETE NO ACTION`. Migration 051 fixes this by adding `ON DELETE CASCADE`.

**Status:** Fixed in migration 051. No remaining runtime risk. Noted for completeness.

---

### P2-04: `BaseRepository` abstract class not used by all repositories

**Files:** `backend/repositories/base.py` (lines 43-130), `backend/repositories/forecast_observation_repository.py`, `backend/repositories/model_config_repository.py`, `backend/repositories/notification_repository.py`, `backend/repositories/supplier_repository.py`

**Problem:** `BaseRepository[T]` defines abstract methods `get_by_id`, `create`, `update`, `delete`, `list`, `count`. However, only 2 of 7 concrete repository classes inherit from it:
- `PriceRepository(BaseRepository[Price])` -- yes
- `UserRepository(BaseRepository[User])` -- yes
- `UtilityAccountRepository(BaseRepository[UtilityAccount])` -- yes
- `ForecastObservationRepository` -- no, standalone class
- `ModelConfigRepository` -- no, standalone class
- `NotificationRepository` -- no, standalone class
- `SupplierRegistryRepository` -- no, standalone class

The non-inheriting repositories have different method signatures and capabilities. For example, `ForecastObservationRepository` has no `get_by_id` or `delete` methods, and `NotificationRepository` has `get_by_id` with a different signature (requires both `notification_id` and `user_id`).

**Impact:** Inconsistent API surface across repositories. Cannot substitute repositories polymorphically. Makes dependency injection harder.

**Fix:** This is partially by design (not all entities need full CRUD), but consider creating a smaller `ReadRepository[T]` base for read-only repositories, or documenting the intentional deviation.

---

### P2-05: `consent_records` model field name `metadata` vs DB column `metadata_json`

**Files:** `backend/models/consent.py` (ConsentRecord model), `backend/migrations/003_reconcile_schema.sql` (renames `metadata` to `metadata_json`)

**Problem:** Migration 003 renames the column from `metadata` to `metadata_json` on the `consent_records` table. The ORM in `compliance/repositories.py` handles this correctly with `Column("metadata_json", ...)`. However, the Pydantic model in `models/consent.py` uses the field name `metadata`, creating a naming divergence that requires mental mapping at every call site.

**Impact:** Developer confusion. Low runtime risk since the ORM mapping handles the translation.

**Fix:** Consider aliasing the Pydantic field: `metadata_json: dict = Field(default_factory=dict, alias="metadata")` to make the DB column name explicit.

---

### P2-06: `forecast_observation_repository.py` commits inside individual methods

**Files:** `backend/repositories/forecast_observation_repository.py` (lines 98, 160, 198, 225)

**Problem:** Each repository method (`insert_forecasts`, `backfill_actuals`, `insert_recommendation`, `update_recommendation_response`) calls `await self._db.commit()` independently. This means the caller cannot compose multiple repository operations into a single transaction.

For example, if `ObservationService` wants to insert forecasts AND insert a recommendation atomically, it cannot -- each will commit independently. If the second operation fails, the first is already committed.

Compare with `model_config_repository.py` line 173 which correctly commits within a multi-step transaction (deactivate + insert), but `forecast_observation_repository.py` does not offer this option.

**Impact:** No transactional composition across repository methods. Partial writes on failure.

**Fix:** Accept an optional `auto_commit: bool = True` parameter, or move commit responsibility to a Unit of Work pattern at the service layer.

---

### P2-07: `notification_repository.py` `update_delivery` does not scope by `user_id`

**Files:** `backend/repositories/notification_repository.py` (lines 181-244)

**Problem:** The `update_delivery()` method updates notifications by `id` alone:
```sql
UPDATE notifications SET ... WHERE id = :nid
```

Unlike `get_by_id()` (line 87) which requires both `notification_id` AND `user_id`, `update_delivery()` only requires `notification_id`. This means if an attacker guesses or enumerates notification UUIDs, they could modify delivery status for notifications belonging to other users.

In practice, this method is only called by `NotificationDispatcher` (an internal service), not from API endpoints directly. But the asymmetry between read (scoped by user_id) and write (not scoped) is a defense-in-depth gap.

**Impact:** Low immediate risk (internal callers only), but violates defense-in-depth principles.

**Fix:** Add `AND user_id = :uid` to the WHERE clause, or document why this is intentionally unscoped (e.g., dispatcher operates across all users).

---

### P2-08: `user_repository.py` dynamic SET clause uses f-string interpolation for column names

**Files:** `backend/repositories/user_repository.py` (lines 218-238)

**Problem:** The `update()` method builds a dynamic SQL SET clause:
```python
for field, value in updates.items():
    param_name = f"p_{field}"
    set_clauses.append(f"{field} = :{param_name}")
    ...
set_sql = ", ".join(set_clauses)
result = await self._db.execute(
    text(f"UPDATE users SET {set_sql} WHERE id = :user_id ..."),
    params,
)
```

The column names (`field`) are interpolated into the SQL string via f-string, not parameterized. While `_UPDATABLE_COLUMNS` (line 180) acts as a whitelist, the pattern is fragile: if a future developer adds a column name containing SQL metacharacters (e.g., a column named `order`) to `_UPDATABLE_COLUMNS`, the query breaks or becomes exploitable.

**Impact:** The whitelist prevents current exploitation, but the pattern is inherently unsafe. Any expansion of `_UPDATABLE_COLUMNS` requires SQL-aware review.

**Fix:** Quote column names with double-quotes in the SQL: `f'"{field}" = :{param_name}'`. This is standard PostgreSQL identifier quoting and prevents reserved-word collisions.

---

### P2-09: `price_repository.py` `_PRICE_COLUMNS` used in f-string SQL without quoting

**Files:** `backend/repositories/price_repository.py` (lines 24-27, 48, 66, 96)

**Problem:** The `_PRICE_COLUMNS` constant is interpolated into SQL via f-string:
```python
text(f"SELECT {_PRICE_COLUMNS} FROM electricity_prices WHERE id = :id")
```

Since `_PRICE_COLUMNS` is a module-level constant (not user input), this is not a SQL injection risk. However, if any column name ever matches a PostgreSQL reserved word, the query will fail. Currently no column names are reserved words, but `timestamp` is a PostgreSQL type name (though not a reserved word in column context).

**Impact:** Low risk currently. Defensive improvement.

**Fix:** Consider quoting column names in the constant string, or using a list of columns that gets properly quoted when joined.

---

### P2-10: `backfill_actuals` logs warning unconditionally when no region filter supplied

**Files:** `backend/repositories/forecast_observation_repository.py` (lines 154-157)

**Problem:** When `region` is `None`, the method logs a WARNING before executing the query (line 154-157):
```python
logger.warning(
    "No region filter supplied; capping backfill at LIMIT=%d ...",
    self._BACKFILL_LIMIT,
)
```

This warning fires on every scheduled backfill call (cron trigger every 6 hours) even when the behavior is expected and intentional. This creates log noise and alert fatigue.

**Impact:** Log noise in production. Warning-level logs may trigger monitoring alerts.

**Fix:** Change to `logger.info()` for the pre-execution notice, keep `logger.warning()` only for the post-execution case where the limit was actually hit (line 164).

---

## P3 -- Low / Housekeeping

### P3-01: Missing migration number 001

The migration files jump from `init_neon.sql` to `002_gdpr_auth_tables.sql`. There is no `001_*.sql` file. This is cosmetic (init_neon serves as the initial migration), but breaking the sequential numbering pattern may confuse automated migration tooling.

---

### P3-02: `__init__.py` does not export `ModelConfigRepository` or `NotificationRepository`

**Files:** `backend/repositories/__init__.py` (lines 14-33)

The `__init__.py` exports `PriceRepository`, `UserRepository`, `SupplierRegistryRepository`, `ForecastObservationRepository`, and `UtilityAccountRepository`. It does not export `ModelConfigRepository` or `NotificationRepository`, even though both are concrete repositories in the package. Consumers must use direct imports.

---

### P3-03: `utility_account_repository.py` uses `builtins.list` type annotation

**Files:** `backend/repositories/utility_account_repository.py` (lines 8, 183, 187)

The file imports `builtins` and uses `builtins.list[UtilityAccount]` for type annotations on `get_by_user()` and `get_by_user_and_type()`. This is unusual -- the standard `list[T]` syntax (PEP 585, Python 3.9+) works fine. Other methods in the same class already use `list[UtilityAccount]` (lines 130, 156). The `builtins` import appears to be a workaround for a name collision with the `list()` method on `BaseRepository`, but it is inconsistent within the same file.

---

### P3-04: `model_config_repository.py` `_row_to_model` uses `json.loads` for already-parsed JSONB

**Files:** `backend/repositories/model_config_repository.py` (lines 208-214)

The `_parse_json()` helper handles both dicts (from asyncpg) and raw strings. This dual handling is correct for portability, but the comment `"Handle both pre-parsed dicts (asyncpg) and raw JSON strings"` suggests uncertainty about the driver behavior. Since the project uses asyncpg exclusively via Neon, the string path is likely dead code.

---

### P3-05: `supplier_repository.py` `_RemovedSupplierRepository` stub pattern

**Files:** `backend/repositories/supplier_repository.py` (lines 39-46)

The deprecated `SupplierRepository` class is replaced with a stub that raises `ImportError` on instantiation. This is a good pattern for migration, but the stub will remain indefinitely. Consider removing it entirely once all call sites have been verified clean (the S4-11 audit remediation is complete).

---

### P3-06: Migration 009 re-adds `updated_at` to `user_connections`

**Files:** `backend/migrations/009_email_oauth_tokens.sql` (line 10), `backend/migrations/008_connection_feature.sql` (line 42)

Migration 008 creates `user_connections` with `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`. Migration 009 then adds `ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()`. The `IF NOT EXISTS` guard prevents an error, but the second declaration uses `DEFAULT NOW()` without `NOT NULL`, which would have been the actual constraint if migration 008 had not already created the column. This is a no-op but indicates a sloppy migration.

---

### P3-07: `community_solar_programs` uses `TEXT` for `state` column

**Files:** `backend/migrations/041_community_solar_programs.sql`

The `state` column is `TEXT`, while other tables use `VARCHAR(2)` or `VARCHAR(50)` for state/region codes. Since the Region enum validates values at the application layer, this is not a data integrity risk, but it is inconsistent with the rest of the schema.

---

### P3-08: `BaseRepository.get_by_id` parameter shadows built-in `id`

**Files:** `backend/repositories/base.py` (line 52)

The `get_by_id(self, id: str)` method parameter shadows Python's built-in `id()` function. While this is a common pattern in ORMs, it triggers linting warnings (B003/A002). Consider renaming to `entity_id` or `record_id`.

---

### P3-09: `forecast_observation_repository.py` batch insert does not validate prediction dict keys

**Files:** `backend/repositories/forecast_observation_repository.py` (lines 46-64)

The `insert_forecasts` method accesses `pred["predicted_price"]` (line 59) without a `.get()` guard, while other fields use `.get()` with defaults. If a prediction dict is missing the `predicted_price` key, a `KeyError` is raised with no context about which prediction failed. Consider wrapping in a `try/except KeyError` with a descriptive message, or validating the input shape upfront.

---

### P3-10: `notification_repository.py` uses `structlog` while other repositories use `logging`

**Files:** `backend/repositories/notification_repository.py` (line 22), `backend/repositories/forecast_observation_repository.py` (line 9), `backend/repositories/model_config_repository.py` (line 18)

`NotificationRepository` imports `structlog.get_logger()` while all other repositories use `logging.getLogger()`. This creates inconsistent log formatting across the repository layer.

---

## Files With No Issues Found

- `backend/models/__init__.py` -- Clean re-exports
- `backend/models/region.py` -- Comprehensive Region enum, well-structured
- `backend/models/utility.py` -- Clean UtilityType enum
- `backend/models/model_version.py` -- Clean Pydantic model
- `backend/models/supplier.py` -- Clean Pydantic model with validation
- `backend/models/user_supplier.py` -- Clean Pydantic model
- `backend/repositories/base.py` -- Well-designed abstract base (aside from P3-08 `id` shadowing)
- `backend/migrations/003_reconcile_schema.sql` -- Correct reconciliation logic
- `backend/migrations/005_observation_tables.sql` -- Clean table creation
- `backend/migrations/006_multi_utility_expansion.sql` -- Clean with proper enum/seed data
- `backend/migrations/012_user_savings.sql` -- Clean table creation
- `backend/migrations/015_notifications.sql` -- Clean table creation
- `backend/migrations/016_feature_flags.sql` -- Clean table creation
- `backend/migrations/018_nationwide_defaults.sql` -- Correct DEFAULT handling
- `backend/migrations/019_nationwide_suppliers.sql` -- Correct seed data
- `backend/migrations/020_price_query_indexes.sql` -- Correct index creation
- `backend/migrations/021_fix_supplier_api_available.sql` -- Correct column fix
- `backend/migrations/022_user_supplier_composite_index.sql` -- Correct composite index
- `backend/migrations/024_payment_retry_history.sql` -- Clean table creation
- `backend/migrations/025_data_cache_tables.sql` -- Clean cache table design
- `backend/migrations/026_notifications_metadata.sql` -- Clean column addition
- `backend/migrations/029_notification_delivery_tracking.sql` -- Clean schema extension
- `backend/migrations/030_model_versioning_ab_tests.sql` -- Clean multi-table creation
- `backend/migrations/031_agent_tables.sql` -- Clean with proper FKs
- `backend/migrations/032_notification_error_message.sql` -- Clean column addition
- `backend/migrations/033_model_predictions_ab_assignments.sql` -- Clean table creation
- `backend/migrations/034_portal_credentials.sql` -- Clean BYTEA column additions
- `backend/migrations/035_backfill_neon_auth_users.sql` -- Correct backfill logic
- `backend/migrations/036_performance_indexes.sql` -- Clean index additions
- `backend/migrations/039_referrals.sql` -- Clean table creation
- `backend/migrations/040_gas_supplier_seed.sql` -- Clean seed data
- `backend/migrations/042_cca_programs.sql` -- Clean table creation
- `backend/migrations/043_heating_oil.sql` -- Clean multi-table creation
- `backend/migrations/044_multi_utility_alerts.sql` -- Clean table creation
- `backend/migrations/045_affiliate_tracking.sql` -- Clean table creation
- `backend/migrations/046_propane_prices.sql` -- Clean table creation
- `backend/migrations/047_water_rates.sql` -- Clean table creation
- `backend/migrations/048_utility_feature_flags.sql` -- Clean table creation
- `backend/migrations/050_community_posts_indexes.sql` -- Correct partial indexes
- `backend/migrations/051_gdpr_cascade_fixes.sql` -- Correct CASCADE additions
- `backend/migrations/053_notification_dedup_index.sql` -- Clean index addition
- `backend/migrations/054_stripe_processed_events.sql` -- Clean idempotency table
- `backend/migrations/055_fix_invalid_indexes.sql` -- Correct index fix

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| P0 | 4 | Ghost columns missing from migration history (2), ORM/migration FK mismatch (1), plaintext OAuth tokens (1) |
| P1 | 9 | Missing updated_at triggers (1), missing NOT NULL (1), data type mismatch (1), duplicate indexes (1), numbering conflict (1), overly broad GRANT (1), missing GDPR cascade FKs (3) |
| P2 | 10 | ORM model inconsistencies (2), transaction boundary issues (1), defense-in-depth gaps (1), f-string SQL patterns (2), log noise (1), naming divergences (1), base class inconsistency (1), `_PRICE_COLUMNS` quoting (1) |
| P3 | 10 | Cosmetic/housekeeping: missing migration 001, unexported repos, shadowed builtins, dead code paths, inconsistent logging, schema style inconsistencies |

**Total findings: 33**

### Critical Path

The highest-impact items requiring immediate attention:

1. **P0-01 and P0-02 (ghost columns)**: The migration history is not self-contained. A fresh database deployed from migrations will fail at runtime. Add the missing `ALTER TABLE ADD COLUMN` statements.

2. **P0-03 (ORM FK mismatch)**: The compliance ORM contradicts the live database schema on a GDPR-critical table. Fix the ORM to match production.

3. **P0-04 (plaintext OAuth tokens)**: Credential storage inconsistency. All other sensitive fields use AES-256-GCM encryption; OAuth tokens should too.

4. **P1-07, P1-08, P1-09 (missing GDPR cascade FKs)**: Three tables with user_id columns lack FK constraints, meaning GDPR Article 17 erasure does not cascade to them. The GDPR cascade fix rounds (051, 052) missed these tables.

### Positive Observations

- All raw SQL uses parameterized queries via `text()` with named parameters. No string concatenation of user input into SQL was found across any repository.
- The batch INSERT pattern in `forecast_observation_repository.py` is well-implemented with chunking and multi-row VALUES.
- The `_UPDATABLE_COLUMNS` whitelist in `user_repository.py` is a solid defense-in-depth measure against unintended column writes.
- The `_RemovedSupplierRepository` stub pattern provides a clear migration path with actionable error messages.
- The `backfill_actuals` CTE with LIMIT is a smart bounded-memory pattern for large-table updates.
- Migration idempotency is well-maintained across the codebase with consistent use of `IF NOT EXISTS` / `IF EXISTS` guards.
- The Redis cache stampede prevention in `price_repository.py` (lock-based pattern with TTL) is production-quality.
