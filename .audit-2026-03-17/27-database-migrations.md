# Audit Report: Database Migrations
## Date: 2026-03-17

---

### Executive Summary

All 51 migration files were read and analyzed (`init_neon.sql` through `051_gdpr_cascade_fixes.sql`). The migration set covers 44 public schema tables and is generally well-engineered. Strengths include consistent UUID primary keys, IF NOT EXISTS guards on the vast majority of DDL, thorough use of partial indexes, and a disciplined pattern of wrapping GRANTs in exception-safe DO blocks. Migration 003 is a particularly exemplary piece of schema reconciliation work.

However, **8 actionable findings were identified** across all severity levels. The most significant is a missing FK constraint on `user_savings.user_id`, which means user deletion does not cascade to savings records — a GDPR compliance gap similar to what migration 051 was written to fix. Several other tables also lack FK enforcement, and migration 051 itself contains a non-idempotent `ADD CONSTRAINT` that will fail on a second run. There are also two index-duplication issues from multiple migrations targeting the same column definitions, and a mislabeled version comment.

---

### Strengths

- UUID PKs (`gen_random_uuid()`) used consistently across all 51 migrations. No SERIAL or BIGSERIAL found.
- `CREATE TABLE IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS` used throughout — safe to replay.
- FK constraints carry explicit `ON DELETE` policies in the majority of cases; cascade semantics are intentional and documented.
- Partial indexes (`WHERE is_active = TRUE`, `WHERE read_at IS NULL`, `WHERE status = 'active'`, etc.) are used extensively and correctly.
- `CONCURRENTLY` is used for index creation on large/live tables to avoid table locks.
- GDPR immutability trigger on `deletion_logs` is correctly implemented and the schema migration in 003 correctly disables/re-enables it during column type conversion.
- Migration 003 correctly guards every column rename and FK change with `information_schema` checks — a robust pattern.
- `ON CONFLICT DO NOTHING` / `ON CONFLICT (col) DO NOTHING` used for all seed data, making seeds idempotent.
- DO blocks catch `WHEN undefined_object` for neondb_owner GRANTs, making migrations portable between Neon environments.
- The `consent_purpose` enum is created with `EXCEPTION WHEN duplicate_object THEN NULL` guard in both 002 and 003.

---

### P0 — Critical

**Finding P0-1: `user_savings.user_id` has no FK constraint — orphaned rows on user deletion (GDPR gap)**

- File: `012_user_savings.sql`
- Lines: 13–24
- Description: The `user_savings` table declares `user_id UUID NOT NULL` but has no `FOREIGN KEY (user_id) REFERENCES users(id)` constraint and no `ON DELETE` policy. When a user is deleted, their savings records will remain as orphaned rows permanently, violating GDPR Article 17 (right to erasure). This is exactly the class of bug that migration 051 was created to fix for community and notifications tables, but `user_savings` was missed.
- Impact: User data survives deletion. Orphaned rows can be queried, aggregated, and potentially leaked.
- Fix:
  ```sql
  ALTER TABLE user_savings
      ADD CONSTRAINT fk_user_savings_user
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
  ```
  Add as migration 052.

---

**Finding P0-2: `recommendation_outcomes.user_id` has no FK constraint — orphaned rows on user deletion (GDPR gap)**

- File: `005_observation_tables.sql`
- Lines: 22–32
- Description: `recommendation_outcomes` stores per-user recommendation data with `user_id UUID NOT NULL` but no FK to `users(id)`. No ON DELETE policy exists. Same GDPR Article 17 exposure as P0-1. This table was also not included in migration 051's remediation pass.
- Fix:
  ```sql
  ALTER TABLE recommendation_outcomes
      ADD CONSTRAINT fk_recommendation_outcomes_user
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
  ```

---

### P1 — High

**Finding P1-1: Migration 051 ADD CONSTRAINT on `notifications` is not idempotent — will fail on re-run**

- File: `051_gdpr_cascade_fixes.sql`
- Lines: 27–29
- Description: The notifications FK addition uses bare `ADD CONSTRAINT notifications_user_id_fkey` without a preceding `DROP CONSTRAINT IF EXISTS` guard, unlike the three community table blocks immediately above it which correctly use `DROP CONSTRAINT IF EXISTS` before re-adding. If migration 051 is ever replayed (e.g., in a branched Neon environment or during a test suite reset), line 28 will throw `ERROR: constraint "notifications_user_id_fkey" for relation "notifications" already exists` and abort the transaction.
- Contrast with the correct pattern used in the same file (line 7):
  ```sql
  ALTER TABLE community_posts DROP CONSTRAINT IF EXISTS community_posts_user_id_fkey;
  ```
- Fix:
  ```sql
  -- Replace lines 27-29 with:
  ALTER TABLE notifications
      DROP CONSTRAINT IF EXISTS notifications_user_id_fkey;
  ALTER TABLE notifications
      ADD CONSTRAINT notifications_user_id_fkey
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
  ```

---

**Finding P1-2: `referrals.referrer_id` and `referrals.referee_id` have no FK constraints**

- File: `039_referrals.sql`
- Lines: 9–18
- Description: Both `referrer_id UUID NOT NULL` and `referee_id UUID` reference user identities but have no `FOREIGN KEY ... REFERENCES users(id)` constraint. If a referrer is deleted, the referral row persists with a dangling `referrer_id`. There is no cascade or SET NULL policy, so the referral system will show phantom referrers. This is also a GDPR data retention risk.
- Fix:
  ```sql
  ALTER TABLE referrals
      ADD CONSTRAINT fk_referrals_referrer
      FOREIGN KEY (referrer_id) REFERENCES users(id) ON DELETE CASCADE;
  ALTER TABLE referrals
      ADD CONSTRAINT fk_referrals_referee
      FOREIGN KEY (referee_id) REFERENCES users(id) ON DELETE SET NULL;
  ```

---

**Finding P1-3: `model_predictions.user_id` and `model_ab_assignments.user_id` have no FK constraints**

- File: `033_model_predictions_ab_assignments.sql`
- Lines: 31–39, 59–68
- Description: Both tables store `user_id UUID NOT NULL` with no FK to `users(id)`. `model_ab_assignments` has a UNIQUE constraint on `user_id` (line 66–68) but no referential integrity. Stale A/B assignment and prediction records for deleted users cannot be cleaned up automatically. Unlike ML-internal tables (e.g., `model_config`), these tables directly link to user identities and should participate in the GDPR deletion cascade.
- Fix:
  ```sql
  ALTER TABLE model_predictions
      ADD CONSTRAINT fk_model_predictions_user
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
  ALTER TABLE model_ab_assignments
      ADD CONSTRAINT fk_model_ab_assignments_user
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
  ```

---

**Finding P1-4: Duplicate index definitions — `idx_users_stripe_customer_id` created in both 004 and 037**

- Files: `004_performance_indexes.sql` (line 10) and `037_additional_performance_indexes.sql` (line 19)
- Description: Both migrations create `idx_users_stripe_customer_id ON users (stripe_customer_id) WHERE stripe_customer_id IS NOT NULL`. Because both use `IF NOT EXISTS`, the second creation is a silent no-op, so there is no runtime failure. However, this represents schema drift: the intent of 037 was to add this as a new index per the Clarity Gate audit (note "MED-27"), implying 004 was not accounted for during that audit. The comment in 037 says it is a new missing index, which is inaccurate. Any future tooling that diffs expected vs actual migration DDL will flag this inconsistency.
- Fix: Add a note in 037's comment block acknowledging that 004 already created this index. No DDL change required (IF NOT EXISTS handles runtime safety). Alternatively, remove the statement from 037 and document the reason.

---

**Finding P1-5: `model_config` table has missing NOT NULL on `is_active`, `created_at`, and `updated_at`**

- File: `027_model_config.sql`
- Lines: 16–18
- Description: Three columns in `model_config` omit NOT NULL:
  - `is_active BOOLEAN DEFAULT false` — nullable boolean creates three-valued logic (TRUE / FALSE / NULL) where only TRUE/FALSE is meaningful. The service code likely assumes a two-valued field.
  - `created_at TIMESTAMPTZ DEFAULT NOW()` — nullable timestamp; `created_at` should never be NULL.
  - `updated_at TIMESTAMPTZ DEFAULT NOW()` — same concern as `created_at`.
  All other tables in the schema correctly declare these columns NOT NULL. This table was authored inconsistently.
- Fix:
  ```sql
  ALTER TABLE model_config
      ALTER COLUMN is_active   SET NOT NULL,
      ALTER COLUMN created_at  SET NOT NULL,
      ALTER COLUMN updated_at  SET NOT NULL;
  ```
  Add as migration 052 alongside the FK fixes above.

---

### P2 — Medium

**Finding P2-1: `028_feedback_table.sql` carries incorrect version header "Version: 026"**

- File: `028_feedback_table.sql`
- Line: 3
- Description: The file header reads `-- Version: 026` but the file is numbered `028`. This is a cosmetic inconsistency from a copy-paste error, but it creates confusion during incident reviews when a developer searches migrations by version number. The file content and table name (`feedback`) are consistent with its being 028.
- Fix: Change line 3 from `-- Version: 026` to `-- Version: 028`.

---

**Finding P2-2: `init_neon.sql` lacks sequential numbering — breaks migration tooling assumptions**

- File: `init_neon.sql`
- Description: The project standard (per CLAUDE.md) requires sequential numbering. All 50 subsequent files are numbered 002 through 051, leaving `init_neon.sql` as an unnumbered outlier equivalent to 001. Automated migration runners (e.g., a future Alembic integration, a CI validation script, or the `validate-migrations` GHA composite action) that expect `NNN_*.sql` naming will not detect this file as migration 001, potentially skipping it entirely or running it out of sequence. The CLAUDE.md note "Migration numbering must be sequential" and the GHA `validate-migrations` action both imply this is a known standard.
- Fix: Rename to `001_init_neon.sql`. Update any migration runner configuration that references the filename by literal name. This is a low-risk rename since `init_neon.sql` is the foundation — it must run first regardless.

---

**Finding P2-3: `community_posts.created_at` and `updated_at` missing NOT NULL**

- File: `049_community_tables.sql`
- Lines: 23–24
- Description: `community_posts` declares `created_at TIMESTAMPTZ DEFAULT now()` and `updated_at TIMESTAMPTZ DEFAULT now()` without NOT NULL. The companion tables `community_votes` and `community_reports` have the same pattern on line 30 and 38 respectively. Every other timestamp column in the schema that has a DEFAULT also has NOT NULL (e.g., `users.created_at`, `feedback.created_at`, `notifications.created_at`). An application INSERT that explicitly passes NULL for `created_at` would succeed, creating rows with a NULL timestamp that would break ordering queries and the updated_at trigger.
- Fix:
  ```sql
  -- Add to a future migration:
  ALTER TABLE community_posts  ALTER COLUMN created_at SET NOT NULL;
  ALTER TABLE community_posts  ALTER COLUMN updated_at SET NOT NULL;
  ALTER TABLE community_votes  ALTER COLUMN created_at SET NOT NULL;
  ALTER TABLE community_reports ALTER COLUMN created_at SET NOT NULL;
  ```

---

**Finding P2-4: `037_additional_performance_indexes.sql` uses `GRANT ... ON ALL TABLES IN SCHEMA public` — overly broad**

- File: `037_additional_performance_indexes.sql`
- Line: 24
- Description: The grant statement `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO neondb_owner;` affects every table that exists at the time of execution, not just the tables introduced by that migration. This is inconsistent with every other migration, which grants only to specific named tables. While neondb_owner is the application role and generally needs broad access in this Neon project, the pattern is dangerous: if this migration were run against a multi-tenant Neon project or a branch with a different security model, it would silently over-grant. It also makes auditing harder because the effective permission set of neondb_owner after 037 cannot be determined by reading only that file.
- Fix: Replace with explicit grants on the two new indexes' underlying tables (no new tables are created in 037, so no grants are actually needed). The full-schema grant should be removed or moved to a dedicated permissions management script.

---

### P3 — Low

**Finding P3-1: `007_user_supplier_accounts.sql` — `supplier_id` FK lacks explicit ON DELETE policy**

- File: `007_user_supplier_accounts.sql`
- Line: 13
- Description: `supplier_id UUID NOT NULL REFERENCES supplier_registry(id)` has no explicit `ON DELETE` clause, so it defaults to `ON DELETE RESTRICT`. This means deleting a supplier from `supplier_registry` will fail if any `user_supplier_accounts` row references it — which is likely the intended behavior, but it is not documented, and the default PostgreSQL behavior is easy to overlook. The `user_id` FK on line 12 correctly specifies `ON DELETE CASCADE`. The inconsistency may mislead a future developer into thinking the missing clause is an oversight.
- Fix: Add an explicit `ON DELETE RESTRICT` (or the intended policy) to document intent:
  ```sql
  supplier_id UUID NOT NULL REFERENCES supplier_registry(id) ON DELETE RESTRICT,
  ```

---

**Finding P3-2: `forecast_observations.forecast_id` is `TEXT NOT NULL` rather than `UUID`**

- File: `005_observation_tables.sql`
- Line: 7
- Description: All other identity columns in the schema use UUID. `forecast_id TEXT NOT NULL` is an opaque string handle from the ML pipeline, not a FK to another table, so it cannot be converted to UUID without application-layer changes. However, the inconsistency should be noted: if this field will ever reference a `forecasts` table, it will need to be retyped. A comment explaining why TEXT is used here (e.g., "forecast_id is a string key generated by the ML pipeline, not a DB-managed UUID") would prevent future confusion.
- Fix: Add an inline comment explaining the design choice. No DDL change required.

---

**Finding P3-3: `026_notifications_metadata.sql` — GRANT added separately from table creation (migration 015)**

- Files: `015_notifications.sql` and `026_notifications_metadata.sql`
- Description: Migration 015 creates the `notifications` table but includes no GRANT statement. The first GRANT on `notifications` appears in migration 026. This means there is a window (migrations 015–025) in which the `notifications` table exists but neondb_owner has not been explicitly granted access. In practice this is harmless because neondb_owner is the table owner on Neon and has implicit full access — but it breaks the audit trail pattern of "every table has a GRANT in the same migration that creates it."
- Fix: No production action required. For consistency in future migrations, add GRANT in the same file that creates the table.

---

**Finding P3-4: `011_utilityapi_sync_columns.sql` header comment says "Migration 010"**

- File: `011_utilityapi_sync_columns.sql`
- Lines: 1–2
- Description: The comment block reads `-- Migration 010: Add UtilityAPI sync columns to user_connections`. The file is numbered `011`. This is identical in nature to the 028/026 mislabeling in P2-1, but both occurrences should be fixed together for consistency.
- Fix: Change the comment on line 1 from `-- Migration 010:` to `-- Migration 011:`.

---

### Statistics

| Metric | Value |
|--------|-------|
| Total migration files reviewed | 51 |
| Sequential numbering coverage | 50/51 (init_neon.sql unnumbered) |
| Tables with FK on user_id (of tables that have user_id) | ~18 of 22 |
| Tables missing FK on user_id (GDPR risk) | 4 (`user_savings`, `recommendation_outcomes`, `model_predictions`, `model_ab_assignments`) |
| Migrations using IF NOT EXISTS on all CREATE TABLE/INDEX | 51/51 |
| Migrations using CONCURRENTLY for live-safe index creation | ~14 (all post-004 index-only migrations) |
| Migrations with explicit GRANT | 37/51 |
| Duplicate index definitions (same name, same columns) | 1 pair (004 + 037: `idx_users_stripe_customer_id`) |
| Non-idempotent ADD CONSTRAINT (no prior DROP IF EXISTS) | 1 (051 notifications FK) |
| SERIAL/BIGSERIAL usage | 0 |
| Tables using TEXT[] for array fields (instead of typed enum[]) | 3 (`suppliers.regions`, `supplier_registry.regions`, `cca_programs.zip_codes`) |
| Tables using VARCHAR for utility_type instead of the `utility_type` enum | 6+ (`price_alert_configs`, `alert_history`, `rate_change_alerts`, `alert_preferences`, `community_posts`, `affiliate_clicks`) |

| Severity | Count |
|----------|-------|
| P0 — Critical | 2 |
| P1 — High | 5 |
| P2 — Medium | 4 |
| P3 — Low | 4 |
| **Total** | **15** |

---

### Recommended Next Steps

1. **Immediate (add migration 052):** Add FK constraints with `ON DELETE CASCADE` to `user_savings`, `recommendation_outcomes`, `model_predictions`, and `model_ab_assignments`. Add NOT NULL to `model_config.is_active/created_at/updated_at`. This single migration closes all P0/P1 GDPR gaps found in this audit.

2. **Short-term:** Fix the non-idempotent ADD CONSTRAINT in 051 by adding `DROP CONSTRAINT IF EXISTS notifications_user_id_fkey` before the ADD. This can be done as a hotfix to 051 if it has not yet been deployed to any branch database, or as a new migration if it has.

3. **Housekeeping:** Fix the two mislabeled version comments (028 says "Version: 026", 011 says "Migration 010"). Rename `init_neon.sql` to `001_init_neon.sql` if the migration runner relies on glob ordering.

4. **Consider:** Standardize `utility_type` references to use the PostgreSQL `utility_type` enum (created in migration 006) rather than `VARCHAR(30)` with in-application validation. Currently 6+ tables use the string form, meaning the enum constraint is only enforced at the application layer, not at the database layer. This creates a data quality risk if records are ever inserted via psql or migration scripts directly.
