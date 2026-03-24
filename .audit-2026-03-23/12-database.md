# Audit Report: Database Layer
**Date:** 2026-03-23
**Scope:** Schema, migrations, models, indexing, query patterns
**Files Reviewed:**
- `backend/migrations/init_neon.sql`
- `backend/migrations/002_gdpr_auth_tables.sql`
- `backend/migrations/003_reconcile_schema.sql`
- `backend/migrations/004_performance_indexes.sql`
- `backend/migrations/005_observation_tables.sql`
- `backend/migrations/006_multi_utility_expansion.sql`
- `backend/migrations/007_user_supplier_accounts.sql`
- `backend/migrations/008_connection_feature.sql`
- `backend/migrations/009_email_oauth_tokens.sql`
- `backend/migrations/010_utility_type_index.sql` (note: duplicate filename prefix with 011)
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
- `backend/migrations/056_stripe_customer_id_unique.sql`
- `backend/migrations/057_ghost_columns.sql`
- `backend/migrations/058_deletion_log_fk_fix.sql`
- `backend/migrations/059_oauth_tokens_bytea.sql`
- `backend/migrations/060_updated_at_triggers.sql`
- `backend/models/__init__.py`
- `backend/models/user.py`
- `backend/models/supplier.py`
- `backend/models/price.py`
- `backend/models/notification.py`
- `backend/models/connections.py`
- `backend/models/consent.py`
- `backend/models/observation.py`
- `backend/models/community.py`
- `backend/models/utility_account.py`
- `backend/models/model_config.py`
- `backend/models/model_version.py`
- `backend/models/region.py`
- `backend/models/regulation.py`
- `backend/models/user_supplier.py`
- `backend/models/utility.py`
- `backend/compliance/repositories.py`
- `backend/repositories/base.py`
- `backend/repositories/user_repository.py`
- `backend/repositories/supplier_repository.py`
- `backend/repositories/notification_repository.py`
- `backend/repositories/utility_account_repository.py`
- `backend/repositories/forecast_observation_repository.py`
- `backend/scripts/db_maintenance.py`

---

## P0 — Critical (Fix Immediately)

### P0-1: Migration numbering collision — two files prefixed `010_`
**Files:** `backend/migrations/010_utility_type_index.sql`, `backend/migrations/011_utilityapi_sync_columns.sql`

The filesystem listing shows `010_utility_type_index.sql` and `011_utilityapi_sync_columns.sql`. However, the header comment inside `011_utilityapi_sync_columns.sql` reads "Migration 010: Add UtilityAPI sync columns" — meaning two distinct migrations were both authored as migration 010. They have different filenames (010 vs 011) so the runner applies them in order, but the internal comment of 011 claiming to be "010" is misleading and indicates that 011 was created without incrementing the counter. This creates an ambiguity: if a developer searches git history or documentation for "migration 010", they will find two candidates.

More critically, the actual sequence jump means there is no migration formally numbered and titled "010" for the utility_type_index work other than the file name. If a migration runner relies on the number embedded in the file comment rather than the filename, 011 would be treated as a re-run of 010, causing it to be skipped or double-applied depending on the runner's deduplication logic.

**Risk:** Depending on how migrations are tracked (by filename vs. comment), migration 011 could be silently skipped or double-applied in environments that parse the migration number from the SQL comment rather than the filename.

**Fix:** Correct the comment in `011_utilityapi_sync_columns.sql` to read "Migration 011". Audit the migration runner to confirm it uses filenames (not comment headers) as the version key.

---

### P0-2: `users.name` column allows empty string on UPDATE — NOT NULL not enforced at DB level
**Files:** `backend/migrations/init_neon.sql`, `backend/migrations/035_backfill_neon_auth_users.sql`, `backend/repositories/user_repository.py`

The `users` table declares `name VARCHAR(200) NOT NULL`. Migration 035 backfills `name` with `COALESCE(u.name, '')`, inserting empty string `''` when the neon_auth user has no name. An empty string satisfies `NOT NULL` but violates the application invariant expressed in `models/user.py`: `name: str = Field(..., min_length=1, max_length=200)`.

The result is that rows with `name = ''` exist in the database and can be retrieved through the repository. When such a row is passed to `_row_to_user()` in `user_repository.py`, it bypasses Pydantic validation (validation only occurs at construction time with user-supplied data, not when constructing from a DB row via `data.get("name", "")`).

**Risk:** Downstream code that assumes `user.name` is non-empty (e.g., personalized emails, display name rendering) receives an empty string, producing blank greetings. The Pydantic model's `min_length=1` guard is bypassed for DB-originated data.

**Fix:** Add a `CHECK (length(trim(name)) > 0)` constraint to the `users` table. Replace the `COALESCE(u.name, '')` backfill in migration 035 with `COALESCE(NULLIF(trim(u.name), ''), 'Unknown User')`. Add a companion migration to update existing empty-name rows.

---

### P0-3: `stripe_processed_events.event_id` declared as unbounded `VARCHAR` (no length)
**File:** `backend/migrations/054_stripe_processed_events.sql`

The primary key `event_id VARCHAR PRIMARY KEY` has no length constraint. In PostgreSQL, bare `VARCHAR` without a length is equivalent to `TEXT`, which is fine for storage but: (1) it bypasses any implicit length limit that would guard against pathologically large values being inserted by a buggy or adversarial caller, and (2) the lack of a length annotation is inconsistent with every other `VARCHAR` column in the schema and makes the schema intention unclear.

Stripe event IDs follow the format `evt_XXXXXXXXXXXXXXXXXXXXXXXX` and are at most ~255 characters. The absence of a length means a malformed or injected event ID of arbitrary length could consume excessive index space on the primary key B-tree.

**Fix:** Alter to `event_id VARCHAR(255) PRIMARY KEY`. Add a `CHECK (event_id LIKE 'evt_%' OR event_id LIKE 'ch_%' OR event_id LIKE 'cs_%')` constraint to enforce the Stripe ID prefix format.

---

### P0-4: `model_ab_assignments` has no FK to `users` enforced prior to migration 052, and the UNIQUE constraint on `user_id` alone is semantically wrong for multi-test scenarios
**Files:** `backend/migrations/033_model_predictions_ab_assignments.sql`, `backend/migrations/052_fk_gdpr_cascade_round2.sql`

Migration 033 creates `model_ab_assignments` with `CONSTRAINT uq_model_ab_assignments_user_id UNIQUE (user_id)`. This means a single user can only ever be assigned to ONE model version across ALL A/B tests simultaneously. The moment a second A/B test is started with a different `model_name`, any attempt to assign a user to a version in the new test will violate the unique constraint.

The correct uniqueness domain is `(user_id, model_name)` — one assignment per user per model. The current schema makes the entire A/B testing infrastructure non-functional for more than one concurrent test.

**Risk:** Any attempt to run a second A/B test for a different model will produce `UNIQUE constraint violation` for every user that was previously assigned in any earlier test.

**Fix:** Drop the current unique constraint and replace it with `UNIQUE (user_id, model_name)`. Add a migration that drops the old index and creates the correct composite unique index.

---

### P0-5: `notifications` table missing FK on `user_id` at initial creation — added by migration 051, but window of inconsistency leaves orphan rows possible
**Files:** `backend/migrations/015_notifications.sql`, `backend/migrations/051_gdpr_cascade_fixes.sql`

Migration 015 creates `notifications` with `user_id UUID NOT NULL` but **no** foreign key constraint referencing `users(id)`. The FK was only added in migration 051. In environments where the database received notifications between migrations 015 and 051, rows for deleted users would persist without the FK preventing them. Migration 052 re-runs the FK addition idempotently to handle non-idempotent migration 051, but no migration performs a `DELETE FROM notifications WHERE user_id NOT IN (SELECT id FROM users)` cleanup.

**Risk:** Orphan notification rows may exist for users that were deleted before migration 051 was applied. These rows would cause FK constraint errors if a future migration attempts to add a `DEFERRABLE` constraint or reconstruct the table.

**Fix:** Add a cleanup migration: `DELETE FROM notifications WHERE user_id NOT IN (SELECT id FROM users)` before applying the FK if it does not already exist. This should have been part of migration 051.

---

## P1 — High (Fix This Sprint)

### P1-1: `user_savings` table has no FK on `user_id` at creation — added retroactively in migration 052
**Files:** `backend/migrations/012_user_savings.sql`, `backend/migrations/052_fk_gdpr_cascade_round2.sql`

Migration 012 creates `user_savings` without a FK constraint on `user_id`. The FK with `ON DELETE CASCADE` was not added until migration 052. As with P0-5, any saves created for deleted users between migrations 012 and 052 are orphan rows. No cleanup query was added.

**Fix:** Add orphan-row cleanup migration: `DELETE FROM user_savings WHERE user_id NOT IN (SELECT id FROM users)`.

---

### P1-2: `recommendation_outcomes` table has no FK on `user_id` at creation — same retroactive pattern
**Files:** `backend/migrations/005_observation_tables.sql`, `backend/migrations/052_fk_gdpr_cascade_round2.sql`

Same issue as P1-1. `recommendation_outcomes` was created in migration 005 without a FK on `user_id`. Migration 052 added the FK with CASCADE. Orphan rows may exist. No cleanup migration was ever added.

**Fix:** Same as P1-1 — add cleanup migration for this table.

---

### P1-3: `model_predictions` table has no FK on `user_id` at creation — same pattern
**Files:** `backend/migrations/033_model_predictions_ab_assignments.sql`, `backend/migrations/052_fk_gdpr_cascade_round2.sql`

Same retroactive FK issue. The table was created in migration 033 without a `user_id` FK, and the CASCADE FK was added in migration 052 without a preceding cleanup step.

**Fix:** Same cleanup migration pattern.

---

### P1-4: `referrals` table: `referrer_id` has no FK at creation, added in migration 052 without orphan cleanup
**Files:** `backend/migrations/039_referrals.sql`, `backend/migrations/052_fk_gdpr_cascade_round2.sql`

Migration 039 creates `referrals` with `referrer_id UUID NOT NULL` and no FK. The FK (with CASCADE) was added in migration 052. No orphan cleanup was performed. Additionally, `referee_id` is nullable with no FK at creation. The `SET NULL` FK was also only added in migration 052.

**Fix:** Add orphan cleanup for `referrals` where `referrer_id NOT IN (SELECT id FROM users)`.

---

### P1-5: `users.utility_types` column stored as `TEXT` (comma-separated string) — type mismatch with application model
**Files:** `backend/migrations/013_user_profile_columns.sql`, `backend/models/user.py`

Migration 013 adds `utility_types TEXT` to the users table. The Pydantic model `User` declares `utility_types: list[str] | None`. The repository `_row_to_user()` passes the raw `TEXT` value directly from the database to `User(utility_types=...)`. This means the model receives a comma-separated string like `"electricity,natural_gas"` rather than `["electricity", "natural_gas"]`.

Migration 013's comment acknowledges this: "Kept as TEXT rather than an array type for simplicity; the application layer splits/joins the value on read and write." However, `_row_to_user()` in `user_repository.py` does **not** perform any split — it passes the raw TEXT value verbatim.

**Risk:** Every time a user with `utility_types` set is fetched from the database, the Pydantic model receives a string where a list is expected. Code that iterates `user.utility_types` will iterate over characters rather than utility type strings, silently producing wrong results.

**Fix:** Either (a) change the column to `TEXT[]` (array type) via a migration and use proper array binding in the repository, or (b) add explicit string-splitting in `_row_to_user()`: `utility_types=[t.strip() for t in data["utility_types"].split(",")]` when the value is a non-empty string. Option (a) is strongly preferred for type safety. This is a data integrity issue affecting every user that has utility types set.

---

### P1-6: `community_posts.created_at` and `updated_at` defined WITHOUT `NOT NULL` — default only
**File:** `backend/migrations/049_community_tables.sql`

```sql
created_at TIMESTAMPTZ DEFAULT now(),
updated_at TIMESTAMPTZ DEFAULT now()
```

Both timestamp columns lack `NOT NULL`. This is inconsistent with every other table in the schema where timestamp columns are declared `NOT NULL DEFAULT now()`. A NULL `created_at` value on a community post would crash any ordering query that relies on the column being non-null, and would violate the implicit contract in `models/community.py` where `created_at: datetime` is non-optional.

**Fix:** Add a migration to alter these columns: `ALTER TABLE community_posts ALTER COLUMN created_at SET NOT NULL; ALTER TABLE community_posts ALTER COLUMN updated_at SET NOT NULL;`. Also applies to `community_votes.created_at` and `community_reports.created_at` which have the same defect.

---

### P1-7: `alert_history` table is missing an `ON DELETE CASCADE` FK for `user_id`
**Files:** `backend/migrations/014_alert_tables.sql`

`alert_history` has `CONSTRAINT fk_alert_history_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`. This was part of the original creation in migration 014. However, migration 052's comment states it fixes "missing ON DELETE CASCADE foreign keys" and explicitly lists tables that were missing them — but `alert_history` is not listed. This is inconsistent: the table was created with a CASCADE FK in migration 014 but no migration verifies that this FK was actually applied in environments that ran migration 014 before the FK was present in init_neon.

More concretely: the audit of 051/052 shows the team discovered many FK gaps after the fact. It is worth verifying `alert_history.user_id` has the CASCADE FK in production via `SELECT conname, confupdtype, confdeltype FROM pg_constraint WHERE conrelid = 'alert_history'::regclass`.

**Recommended Action:** Add an idempotent verification in a future migration to confirm the constraint exists and recreate it if absent, following the pattern of migration 052.

---

### P1-8: `rate_change_alerts` and `alert_preferences` missing FK on `user_id`
**File:** `backend/migrations/044_multi_utility_alerts.sql`

`rate_change_alerts` has no `user_id` column (it is a system-level table, acceptable). However, `alert_preferences` has `CONSTRAINT fk_alert_pref_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`. This FK exists in the original DDL. The concern is whether migration 044 was applied before migration 051/052 cleaned up missing FKs — similar to P1-7. The FK should be verified in production.

Additionally, `rate_change_alerts` has no retention mechanism. Unlike `weather_cache`, `scraped_rates`, and `market_intelligence` (which have cleanup jobs in `db_maintenance.py`), `rate_change_alerts` will grow indefinitely as rate changes are detected. There is no index on `detected_at` for efficient deletion and no cleanup job.

**Fix:** Add `rate_change_alerts` to the `db_maintenance.py` retention cleanup (e.g., delete rows older than 90 days). The index `idx_rate_change_alerts_recent ON rate_change_alerts(detected_at DESC)` already exists for efficient deletions.

---

### P1-9: `db_maintenance.py` uses `conn.fetchval()` for DELETE statements — returns None instead of row count
**File:** `backend/scripts/db_maintenance.py`

Lines 57-69 use `await conn.fetchval("DELETE FROM weather_cache WHERE ...")`. `asyncpg`'s `fetchval()` returns the value of the first column of the first row of the result. For a `DELETE` statement that returns no rows (zero deletions) this returns `None`, not `0`. The print statement `print(f"weather_cache retention (30d): deleted {weather_result} rows")` will print `"deleted None rows"` when no rows are deleted, which is misleading.

The correct method for DML statements that return a row count is `conn.execute()`, which returns the command tag string (e.g., `"DELETE 42"`), from which the count can be extracted.

**Fix:** Replace `fetchval()` with `execute()` for all three cache-table DELETE statements, and parse the command tag: `result = await conn.execute(...); count = int(result.split()[-1])`.

---

### P1-10: `model_config` table has no UNIQUE constraint on `(model_name, model_version)` — duplicate versions possible
**File:** `backend/migrations/027_model_config.sql`

`model_config` has no uniqueness constraint on `(model_name, model_version)`. The analogous `model_versions` table (migration 030) correctly uses `CONSTRAINT uq_model_versions_name_tag UNIQUE (model_name, version_tag)`. Without the constraint, two concurrent nightly learning jobs could insert two rows with the same `model_name` and `model_version`, making the `is_active` partial index ambiguous and breaking the "at most one active version per model" invariant.

**Fix:** Add a migration: `ALTER TABLE model_config ADD CONSTRAINT uq_model_config_name_version UNIQUE (model_name, model_version);`. Include orphan-dedup cleanup for any existing duplicate rows.

---

### P1-11: `agent_usage_daily` count increment is NOT atomic at the SQL level
**File:** `backend/migrations/031_agent_tables.sql`, and the service that writes to it

The table uses `query_count INT NOT NULL DEFAULT 0` with a `UNIQUE(user_id, date)` constraint. The documented pattern in `CLAUDE.md` is `INSERT ... ON CONFLICT DO UPDATE SET count=count+1 RETURNING count` for atomic TOCTOU-safe rate limiting. However, the table itself only has the structural constraint — whether the application uses the atomic upsert pattern is a code concern. The schema does not prevent a non-atomic read-increment-write cycle which could under-count queries under concurrent requests.

This is noted as a reminder because the pattern is documented in CLAUDE.md as a learned pattern — the schema supports it but the enforcement is entirely in application code.

**Recommended Action:** Confirm `agent_service.py` uses `INSERT ... ON CONFLICT DO UPDATE SET query_count = agent_usage_daily.query_count + 1` rather than a SELECT followed by UPDATE.

---

## P2 — Medium (Fix Soon)

### P2-1: Multiple duplicate/redundant indexes on `electricity_prices` — maintenance overhead and storage waste
**Files:** `backend/migrations/init_neon.sql`, `004_performance_indexes.sql`, `006_multi_utility_expansion.sql`, `010_utility_type_index.sql`, `020_price_query_indexes.sql`, `037_additional_performance_indexes.sql`

The `electricity_prices` table has accumulated at least 8 indexes across multiple migrations. Several overlap significantly:

- `idx_prices_region_timestamp` — `(region, timestamp DESC)` from init_neon
- `idx_prices_region_supplier_timestamp` — `(region, supplier, timestamp DESC)` from migration 004
- `idx_prices_region_utility` — `(region, utility_type, timestamp DESC)` from migration 006
- `idx_prices_region_utilitytype_timestamp` — `(region, utility_type, timestamp DESC)` from migration 010 (identical to above — duplicate)
- `idx_prices_region_supplier_created` — `(region, supplier, created_at DESC)` from migration 020
- `idx_prices_region_utilitytype_created` — `(region, utility_type, created_at DESC)` from migration 020
- `idx_electricity_prices_region_utility_time` — `(region, utility_type, timestamp DESC)` from migration 037 (third copy of this exact index)
- `idx_prices_utility_type` — `(utility_type)` from migration 006

`idx_prices_region_utility`, `idx_prices_region_utilitytype_timestamp`, and `idx_electricity_prices_region_utility_time` are functionally identical (same columns, same sort order). All three will be maintained on every INSERT/UPDATE, consuming WAL and slowing writes.

Additionally, `idx_prices_region_timestamp` is made redundant by `idx_prices_region_supplier_timestamp` for all queries that also filter on supplier. The single-column `idx_prices_utility_type` is subsumed by the compound utility_type indexes.

**Fix:** Run `SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'electricity_prices' ORDER BY indexname` to confirm the exact set. Drop the two redundant `(region, utility_type, timestamp DESC)` duplicates (keep only one, preferably the one created by migration 006). Evaluate dropping `idx_prices_utility_type` (subsumed by compound indexes). This reduces write amplification on the highest-write table in the schema.

---

### P2-2: `stripe_processed_events` has no `NOT NULL` on `event_type`
**File:** `backend/migrations/054_stripe_processed_events.sql`

The DDL is `event_type VARCHAR NOT NULL` — this is actually fine. However, `event_type` also lacks a length constraint (same as P0-3 for `event_id`). Stripe event types follow a known format (e.g., `checkout.session.completed`, max ~50 characters). An unbounded VARCHAR on a frequently-queried column is a minor concern.

**Fix:** Alter to `event_type VARCHAR(100)` to bound the column and make schema intent explicit.

---

### P2-3: `weather_cache`, `market_intelligence`, `scraped_rates` have no FK or user linkage — uncontrolled growth
**File:** `backend/migrations/025_data_cache_tables.sql`

These three cache tables have no user_id FK (intentional, they are system-level caches). However, `market_intelligence` has no unique constraint and no deduplication guard: identical `(query, region, url)` combinations can be inserted on every cron run, growing the table unboundedly until the 180-day retention fires. For a neon free tier with storage limits, this could cause storage exhaustion.

`scraped_rates` has no unique constraint on `(supplier_id, fetched_at)` period-level granularity, meaning multiple scrape runs in the same hour produce duplicate rows.

**Fix:** Add `UNIQUE (query, region, url)` (with `ON CONFLICT DO UPDATE`) to `market_intelligence`. Add a partial unique index to `scraped_rates` on `(supplier_id, DATE(fetched_at))` to prevent same-day duplicate scrapes per supplier.

---

### P2-4: `users.current_supplier_id` FK references `suppliers` (migration 013) but `users.current_supplier_id` from migration 007 references `supplier_registry`
**Files:** `backend/migrations/007_user_supplier_accounts.sql`, `backend/migrations/013_user_profile_columns.sql`

Migration 007 adds `current_supplier_id UUID REFERENCES supplier_registry(id)` to users. Migration 013 then adds a **second** `current_supplier_id` column (using `ADD COLUMN IF NOT EXISTS`) with a different FK: `REFERENCES suppliers(id) ON DELETE SET NULL`.

Since migration 007 already created the column, migration 013's `ADD COLUMN IF NOT EXISTS` silently does nothing — the column already exists referencing `supplier_registry`. The `fk_users_current_supplier` constraint in migration 013 is added against the already-existing column but now references the `suppliers` (tariffs-style) table instead of `supplier_registry`. This means the FK constraint name `fk_users_current_supplier` references a different table than the column's original FK.

**Risk:** The actual referential integrity enforced depends on which FK was applied first, creating ambiguity. Queries that JOIN `users.current_supplier_id` to either `suppliers` or `supplier_registry` may silently produce wrong results if the column references one table but is joined to the other.

**Fix:** Audit production DB with `SELECT conname, confrelid::regclass FROM pg_constraint WHERE conrelid = 'users'::regclass AND conname LIKE '%supplier%'`. Remove the duplicate/conflicting FK and standardize on `supplier_registry(id)` as the canonical table per the migration 006/007 design intent.

---

### P2-5: `consent_records.user_id` has inconsistent nullability across ORM, model, and API layer
**Files:** `backend/migrations/023_db_audit_indexes.sql`, `backend/migrations/058_deletion_log_fk_fix.sql`, `backend/compliance/repositories.py`, `backend/models/consent.py`

The GDPR consent audit trail design is correct (SET NULL preserves records after user erasure), but the Pydantic model `ConsentResponse` in `models/consent.py` declares `user_id: str` (NOT Optional), while `ConsentRecord` declares `user_id: str | None`. When a consent record for a deleted user (user_id = NULL) is returned via the API, `ConsentResponse` will fail validation because `user_id` is non-optional in that schema.

**Fix:** Update `ConsentResponse.user_id` to `str | None` to match the nullable DB schema. Consider whether the API should expose nullable user_ids or filter them out before serialization.

---

### P2-6: `deletion_logs` immutability trigger does not prevent DDL + DML bypass via `DISABLE TRIGGER`
**Files:** `backend/migrations/init_neon.sql`, `backend/migrations/003_reconcile_schema.sql`, `backend/migrations/058_deletion_log_fk_fix.sql`

The immutability trigger `tr_prevent_deletion_log_update` is a good design, but migrations 003 and 058 both demonstrate the bypass pattern: `ALTER TABLE deletion_logs DISABLE TRIGGER tr_prevent_deletion_log_update; UPDATE ...; ALTER TABLE deletion_logs ENABLE TRIGGER tr_prevent_deletion_log_update;`. Any database superuser or role with the `TRIGGER` privilege can disable the trigger and modify rows.

For true immutability, the correct protection is Row-Level Security (RLS) or a separate schema owned by an audit-only role. The trigger approach is better than nothing but cannot prevent privilege-escalated modifications.

**Recommended Action:** Document this limitation in the compliance runbook. If GDPR audit log integrity is a compliance requirement, evaluate enabling RLS on `deletion_logs` with a policy that allows INSERT but denies UPDATE and DELETE to all roles including `neondb_owner`.

---

### P2-7: `forecast_observations.forecast_hour` constrained to `INT` but not range-checked at DB level
**Files:** `backend/migrations/005_observation_tables.sql`, `backend/models/observation.py`

`forecast_observations.forecast_hour INT NOT NULL` stores the hour of day (0-23). The Pydantic model enforces `forecast_hour: int = Field(..., ge=0, le=23)`. However, there is no `CHECK (forecast_hour BETWEEN 0 AND 23)` constraint at the database level. A buggy INSERT bypassing the Pydantic layer could store hour values outside the valid range (e.g., 25, -1), causing the `backfill_actuals` JOIN condition `fo.forecast_hour = EXTRACT(HOUR FROM ep.timestamp)` to never match.

**Fix:** Add migration: `ALTER TABLE forecast_observations ADD CONSTRAINT ck_forecast_hour CHECK (forecast_hour BETWEEN 0 AND 23);`

---

### P2-8: `electricity_prices` — `cleanup_old_prices()` function deletes by `timestamp` column but prices may only have a `created_at` column for recent inserts
**Files:** `backend/migrations/023_db_audit_indexes.sql`, `backend/migrations/init_neon.sql`

`cleanup_old_prices(retention_days)` in migration 023 deletes rows where `timestamp < NOW() - (retention_days || ' days')`. The `timestamp` column in `electricity_prices` represents the *price observation time*, not the insertion time. EIA data from historical backfills may have `timestamp` values years in the past while `created_at` is recent. This means the retention function could delete legitimately kept historical price data that the ML pipeline needs for training, while leaving recently-inserted rows with stale timestamps.

**Risk:** Historical price data used for ML training (365-day window referenced in `db_maintenance.py`) could be prematurely deleted if the observation timestamp predates the insertion by more than 365 days.

**Fix:** Change the retention function to use `created_at` instead of `timestamp` for deletion: `WHERE created_at < NOW() - (retention_days || ' days')::INTERVAL`. The `created_at` column is the insertion time and is a safer retention boundary.

---

### P2-9: Missing index on `electricity_prices.created_at` for retention cleanup and recent-data queries
**Files:** `backend/migrations/init_neon.sql`, `backend/migrations/023_db_audit_indexes.sql`

`cleanup_old_prices()` deletes by `timestamp`. The `db_maintenance.py` retention job also deletes `weather_cache` by `fetched_at`, `scraped_rates` by `fetched_at`, and `market_intelligence` by `fetched_at`. All of these tables have appropriately named indexes on their time columns. However, `electricity_prices` has no standalone index on `created_at` — only compound indexes that include `created_at` as the trailing sort column (`idx_prices_region_supplier_created`, `idx_prices_region_utilitytype_created`). These compound indexes cannot be used for the unfiltered range scan in `cleanup_old_prices()`.

**Fix:** Add `CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prices_created_at ON electricity_prices (created_at DESC)` to support both the retention function and any unfiltered recent-data queries. Also change the retention function to use `created_at` (see P2-8).

---

### P2-10: `scraped_rates.supplier_id` FK references `supplier_registry` but is nullable — orphan protection incomplete
**File:** `backend/migrations/025_data_cache_tables.sql`

`scraped_rates.supplier_id UUID REFERENCES supplier_registry(id)` is nullable with no `ON DELETE` action. If a supplier is deleted from `supplier_registry`, the FK with no action will block the delete (PostgreSQL default is `NO ACTION`). This means deleting a supplier requires first clearing its scraped rates. However, since `scraped_rates` has a retention policy (90 days), operators may be surprised when a supplier delete fails because old scrape records are still present.

**Fix:** Add `ON DELETE SET NULL` to the FK or `ON DELETE CASCADE`. Given that scraped rates are cache data (not user-owned data), CASCADE is appropriate: `ALTER TABLE scraped_rates DROP CONSTRAINT scraped_rates_supplier_id_fkey; ALTER TABLE scraped_rates ADD CONSTRAINT scraped_rates_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES supplier_registry(id) ON DELETE SET NULL;`

---

### P2-11: `community_posts` — `upvote_count` and `report_count` are derived via `COUNT(*)` queries but no index on `community_votes.post_id` or `community_reports.post_id` exists
**Files:** `backend/migrations/049_community_tables.sql`

`community_votes` has a composite PK `(user_id, post_id)` and `community_reports` has a composite PK `(user_id, post_id)`. In PostgreSQL, composite PKs create an index on `(user_id, post_id)`. A `COUNT(*) WHERE post_id = ?` query will need a reverse scan of this composite index starting with `post_id`, which is the trailing column. PostgreSQL cannot efficiently index-scan on the trailing column of a composite index — it must do an index scan on `user_id` first.

For vote/report counts (the most common community query pattern), a separate index on `post_id` alone would be far more efficient.

**Fix:** Add migrations:
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_community_votes_post_id ON community_votes (post_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_community_reports_post_id ON community_reports (post_id);
```

---

### P2-12: `auth_sessions` and `login_attempts` tables (migration 002) have no FK on `user_id` with CASCADE delete
**File:** `backend/migrations/002_gdpr_auth_tables.sql`

`auth_sessions` has `CONSTRAINT fk_session_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE` — this is correct. However, `login_attempts` has `identifier VARCHAR(255)` (not a FK) which is expected since it tracks email/IP pairs. `activity_logs` has `CONSTRAINT fk_activity_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL` — also correct.

However, `auth_sessions` was not included in the migration 052 sweep of "missing CASCADE FKs", meaning it was either already correct (it was) or it was overlooked. Confirmed: this FK was part of the original DDL in migration 002 and is correctly implemented.

**Note:** `auth_sessions` appears to be largely superseded by Neon Auth's own session management (`neon_auth` schema). Verify whether this table is still actively used or if it is dead code that should be archived.

---

### P2-13: `alert_history` has no ON DELETE behavior for `alert_config_id` FK — defaults to NO ACTION / RESTRICT
**File:** `backend/migrations/014_alert_tables.sql`

The FK `CONSTRAINT fk_alert_history_config FOREIGN KEY (alert_config_id) REFERENCES price_alert_configs(id) ON DELETE SET NULL` is present and correctly uses SET NULL (history is preserved when config is deleted). However, this means alert configs cannot be bulk-deleted if there are associated history rows without first NULLing the FK. The current behavior is correct for audit purposes but imposes a constraint on bulk operations.

This is not a defect — it is correct design — but is worth noting for operational awareness.

---

## P3 — Low / Housekeeping

### P3-1: Migration 028 (`feedback_table.sql`) has an incorrect version comment
**File:** `backend/migrations/028_feedback_table.sql`

The file is named `028_feedback_table.sql` but the header comment reads `-- Version: 026`. This is a copy-paste error from an earlier migration template. The internal numbering `026` conflicts with `026_notifications_metadata.sql`.

**Fix:** Correct the comment to `-- Version: 028`.

---

### P3-2: Migration 019 (`nationwide_suppliers.sql`) uses `ON CONFLICT DO NOTHING` without a conflict target
**File:** `backend/migrations/019_nationwide_suppliers.sql`

All INSERTs use `ON CONFLICT DO NOTHING` without specifying which column(s) to conflict on. Without an explicit conflict target, PostgreSQL uses `ON CONFLICT ON CONSTRAINT` implicitly, which applies only if the inserted row would violate any unique constraint on the table. `supplier_registry` has no explicit UNIQUE constraint on `name` (only `id` is unique via primary key). This means re-running this migration will insert duplicate supplier rows rather than being a true no-op.

**Risk:** Re-running migration 019 on a live database (e.g., during disaster recovery from a fresh schema) will duplicate supplier entries because `ON CONFLICT DO NOTHING` without a target only catches PK conflicts.

**Fix:** Change to `ON CONFLICT (name) DO NOTHING` and add a `UNIQUE(name)` constraint to `supplier_registry`, or change to `ON CONFLICT ON CONSTRAINT <pk_name> DO NOTHING` (which is effectively a no-op for PK conflicts). Migration 006 uses the same pattern.

---

### P3-3: `consent_purpose` enum type created in both migration 002 and migration 003 — double-definition with DO EXCEPTION guard
**Files:** `backend/migrations/002_gdpr_auth_tables.sql`, `backend/migrations/003_reconcile_schema.sql`

Both migrations define `CREATE TYPE consent_purpose AS ENUM (...)` wrapped in `DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN NULL; END $$`. This is correct and idempotent, but the repeated definition in two migrations makes it unclear which is authoritative. If the enum ever needs a new value added, developers may look at only one migration and miss that two files must be updated.

**Fix:** Add a comment to migration 003's enum definition: `-- Re-declared here for environments that skipped migration 002; see 002 for the authoritative definition.`

---

### P3-4: `feature_flags.name` has a redundant index — the `UNIQUE` constraint already creates one
**File:** `backend/migrations/016_feature_flags.sql`

```sql
name VARCHAR(100) UNIQUE NOT NULL,
...
CREATE INDEX IF NOT EXISTS idx_feature_flags_name ON feature_flags (name);
```

The `UNIQUE` constraint automatically creates a B-tree index on `name`. The explicit `CREATE INDEX` creates a second, separate index on the same column. Both are maintained on every write but only one is used for query execution.

**Fix:** Drop the redundant `idx_feature_flags_name` index. The unique constraint index named `feature_flags_name_key` already provides all lookup and uniqueness enforcement.

---

### P3-5: `stripe_processed_events` uses `TIMESTAMP WITH TIME ZONE` rather than `TIMESTAMPTZ`
**File:** `backend/migrations/054_stripe_processed_events.sql`

All other timestamp columns in the schema use the `TIMESTAMPTZ` shorthand (e.g., `init_neon.sql`, `002`, `003`, etc.). Migration 054 uses the verbose `TIMESTAMP WITH TIME ZONE` form. While semantically identical in PostgreSQL, the inconsistency makes schema inspection slightly harder and is inconsistent with the project convention.

**Fix:** Change `processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL` to `processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` in a future migration or via a comment noting the equivalence.

---

### P3-6: `heating_oil_dealers` has no `updated_at` column — inconsistent with other reference tables
**File:** `backend/migrations/043_heating_oil.sql`

All other "reference" tables with dealer/program information (`community_solar_programs`, `cca_programs`, `water_rates`) include `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`. `heating_oil_dealers` lacks this column. This makes it impossible to query "dealers updated in the last N days" for cache invalidation.

**Fix:** Add `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` to `heating_oil_dealers` and add an `updated_at` trigger (following the migration 060 pattern).

---

### P3-7: `community_solar_programs` and `cca_programs` seed data uses `ON CONFLICT DO NOTHING` without conflict target
**Files:** `backend/migrations/041_community_solar_programs.sql`, `backend/migrations/042_cca_programs.sql`

Same issue as P3-2. No UNIQUE constraint on `program_name` or `(state, program_name)` for `community_solar_programs`, so `ON CONFLICT DO NOTHING` without a target only handles PK conflicts.

**Fix:** Add `UNIQUE (state, program_name)` to `community_solar_programs` and change the INSERT to `ON CONFLICT (state, program_name) DO NOTHING`. Similarly for `cca_programs`: add `UNIQUE (state, municipality, program_name)` and update the conflict target.

---

### P3-8: `model_config_repository.py` and `model_version_service.py` not reviewed — these are out of scope of reviewed files but should be checked
**Note:** The `repositories/model_config_repository.py` was not available in the directory listing shown. If it exists, it should be reviewed for the same issues identified in other raw-SQL repositories (column projection, injection safety, pagination limits).

---

### P3-9: No `CLUSTER` or `FILLFACTOR` strategy for high-churn tables
**Note:** Tables with high UPDATE rates (`user_connections`, `notifications`, `bill_uploads`) have no `FILLFACTOR` set, defaulting to 100%. For tables with frequent UPDATEs (especially `notifications.delivery_status` and `user_connections.updated_at`), setting `FILLFACTOR 80` allows in-page updates (HOT updates) which reduces index bloat and WAL generation. At current scale (free tier, small data) this is low priority, but worth documenting for when the platform scales.

---

### P3-10: `users.is_verified` and `users.email_verified` are semantically duplicate columns
**Files:** `backend/migrations/init_neon.sql`, `backend/migrations/002_gdpr_auth_tables.sql`, `backend/repositories/user_repository.py`

The `users` table has both `is_verified BOOLEAN NOT NULL DEFAULT FALSE` (from init_neon) and `email_verified BOOLEAN DEFAULT FALSE` (added in migration 002). The repository `set_email_verified()` sets both: `SET email_verified = TRUE, is_verified = TRUE`. They appear to track the same state (email verification). Having two columns for the same concept creates maintenance burden.

**Recommended Action:** Deprecate `is_verified` in favor of `email_verified` (which is the standard terminology). Keep `is_verified` as a derived view or application-level alias until the next major schema revision.

---

### P3-11: `ab_outcomes` unique index prevents recording multiple outcome types per user+test
**File:** `backend/migrations/030_model_versioning_ab_tests.sql`

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_ab_outcomes_test_user
    ON ab_outcomes (test_id, user_id);
```

This prevents recording more than one outcome per `(test_id, user_id)` combination. If the A/B test design calls for tracking multiple outcome events per user (e.g., "viewed forecast" + "accepted recommendation" as separate events), this constraint blocks the second event. The `outcome VARCHAR(50)` column suggests multiple distinct outcomes are intended.

**Recommended Action:** Review whether multi-event tracking is needed. If so, change the unique constraint to `(test_id, user_id, outcome)` to allow one record per outcome type per user per test.

---

## Files With No Issues Found

- `backend/models/region.py` — Clean enum definition with proper backward-compatible aliases. No schema mapping issues.
- `backend/models/regulation.py` — Simple Pydantic model; properly maps to `state_regulations` schema.
- `backend/models/utility.py` — Pure enum definitions. No DB interaction.
- `backend/models/model_version.py` — Correct representation of migration 030 tables. FKs and constraints properly mirrored.
- `backend/models/observation.py` — Clean, no issues. Column names match migration 005 exactly.
- `backend/repositories/base.py` — Abstract base; no SQL.
- `backend/repositories/forecast_observation_repository.py` — Excellent: uses batched INSERTs with explicit multi-row VALUES, uses CTE with LIMIT for backfill to prevent unbounded operations, aggregation pushed to SQL. No N+1 patterns.
- `backend/repositories/notification_repository.py` — Clean raw SQL with parameterized queries throughout. All queries use LIMIT. No N+1 patterns. Column list is explicit (no SELECT *).
- `backend/migrations/048_utility_feature_flags.sql` — Clean seed data with `ON CONFLICT (name) DO NOTHING` (uses correct conflict target via the UNIQUE constraint on `name`).
- `backend/migrations/054_stripe_processed_events.sql` — Correct design for idempotent event processing. Index on `processed_at` for efficient cleanup. Documentation is thorough.
- `backend/migrations/056_stripe_customer_id_unique.sql` — Correct idempotent pattern using `pg_constraint` lookup.
- `backend/migrations/059_oauth_tokens_bytea.sql` — Well-structured multi-step column migration with explicit guards at each step.
- `backend/migrations/060_updated_at_triggers.sql` — Comprehensive trigger coverage. Correct use of DROP TRIGGER IF EXISTS before CREATE TRIGGER for idempotency (PostgreSQL pre-17 workaround).
- `backend/migrations/053_notification_dedup_index.sql` — Sophisticated partial unique index design correctly handles dismissed notification re-delivery.

---

## Summary

**Total findings:** 30 (5 P0, 11 P1, 13 P2 [some re-classified from initial draft], 11 P3)

**Most critical pattern:** Retroactive FK addition without orphan cleanup. Migrations 051 and 052 added many missing `ON DELETE CASCADE` foreign keys, which is correct, but no companion migration cleaned up orphan rows that may have accumulated in `user_savings`, `recommendation_outcomes`, `model_predictions`, `model_ab_assignments`, and `referrals` between their creation migrations and migration 052. These orphan rows now violate the application's data integrity model even though the FK constraints allow them (orphans were inserted before the FK existed).

**Most impactful correctness defect:** `users.utility_types` stored as a raw comma-separated TEXT string but the Pydantic model expects `list[str]`, and `_row_to_user()` in the user repository does not perform the conversion. Every user with `utility_types` set is silently returning wrong data on every profile fetch (P1-5).

**Most impactful structural defect:** `model_ab_assignments` UNIQUE constraint on `user_id` alone rather than `(user_id, model_name)` makes the A/B testing system non-functional for more than one concurrent test (P0-4).

**Migration quality is generally high.** The use of `IF NOT EXISTS` guards, `DO $$ BEGIN ... EXCEPTION ... END $$` blocks, and `CONCURRENTLY` index builds demonstrates mature migration hygiene. The schema reconciliation work in migrations 003, 052, 055, 057, 058 shows good retrospective debt management. The ghost-columns issue (migration 057) highlights the risk of building indexes on columns that were added out-of-band — the team has now established a pattern of explicit ADD COLUMN IF NOT EXISTS for all schema additions.

**Index coverage is strong overall**, particularly for the `electricity_prices` table's primary query patterns. The main index concern is redundancy (P2-1) rather than missing coverage.

**GDPR compliance** is solid in design: `deletion_logs` immutability trigger, SET NULL cascade for consent/deletion audit records, CASCADE delete for user-owned data. The remaining gap is the lack of RLS enforcement on `deletion_logs` (P2-6) and the `consent_records`/`deletion_logs` GDPR audit window between table creation and FK addition.
