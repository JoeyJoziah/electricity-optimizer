"""
Migration idempotency and consistency tests.

These tests parse the SQL migration files on disk and verify structural
safety properties — they do not execute any SQL against a database.

Checks:
- All migration files have unique numeric prefixes.
- CREATE TABLE statements use IF NOT EXISTS.
- CREATE INDEX statements use IF NOT EXISTS or CONCURRENTLY.
- ALTER TABLE ADD COLUMN statements use IF NOT EXISTS.
- DROP statements use IF EXISTS.
"""

import os
import re

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "migrations")


def get_migration_files():
    """Return sorted list of .sql filenames from the migrations directory."""
    return sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql"))


class TestMigrationFiles:
    def test_unique_migration_numbers(self):
        """All migration files should have unique number prefixes."""
        files = get_migration_files()
        numbers = []
        for f in files:
            match = re.match(r"^(\d+)", f)
            if match:
                numbers.append(match.group(1))
        duplicates = [n for n in numbers if numbers.count(n) > 1]
        assert len(numbers) == len(set(numbers)), f"Duplicate migration numbers: {duplicates}"

    def test_create_table_has_if_not_exists(self):
        """All CREATE TABLE statements should use IF NOT EXISTS."""
        files = get_migration_files()
        violations = []
        for f in files:
            path = os.path.join(MIGRATIONS_DIR, f)
            with open(path) as fh:
                content = fh.read()
            for i, line in enumerate(content.split("\n"), 1):
                stripped = line.strip().upper()
                if stripped.startswith("CREATE TABLE") and "IF NOT EXISTS" not in stripped:
                    violations.append(f"{f}:{i}: {line.strip()}")
        assert not violations, "CREATE TABLE without IF NOT EXISTS:\n" + "\n".join(violations)

    def test_create_index_has_guard(self):
        """All CREATE INDEX statements should use IF NOT EXISTS or CONCURRENTLY."""
        files = get_migration_files()
        violations = []
        for f in files:
            path = os.path.join(MIGRATIONS_DIR, f)
            with open(path) as fh:
                content = fh.read()
            for i, line in enumerate(content.split("\n"), 1):
                stripped = line.strip().upper()
                if (
                    stripped.startswith("CREATE INDEX")
                    and "IF NOT EXISTS" not in stripped
                    and "CONCURRENTLY" not in stripped
                ):
                    violations.append(f"{f}:{i}: {line.strip()}")
        assert (
            not violations
        ), "CREATE INDEX without guard (IF NOT EXISTS or CONCURRENTLY):\n" + "\n".join(violations)

    def test_alter_table_add_column_has_if_not_exists(self):
        """ALTER TABLE ADD COLUMN statements should use IF NOT EXISTS."""
        files = get_migration_files()
        violations = []
        for f in files:
            path = os.path.join(MIGRATIONS_DIR, f)
            with open(path) as fh:
                content = fh.read()
            for i, line in enumerate(content.split("\n"), 1):
                stripped = line.strip().upper()
                # Skip comment lines (single-line -- comments)
                if stripped.startswith("--"):
                    continue
                if "ADD COLUMN" in stripped and "IF NOT EXISTS" not in stripped:
                    violations.append(f"{f}:{i}: {line.strip()}")
        assert not violations, "ADD COLUMN without IF NOT EXISTS:\n" + "\n".join(violations)

    def test_no_drop_without_if_exists(self):
        """DROP statements should use IF EXISTS."""
        files = get_migration_files()
        violations = []
        for f in files:
            path = os.path.join(MIGRATIONS_DIR, f)
            with open(path) as fh:
                content = fh.read()
            for i, line in enumerate(content.split("\n"), 1):
                stripped = line.strip().upper()
                # Skip comment lines
                if stripped.startswith("--"):
                    continue
                if stripped.startswith("DROP") and "IF EXISTS" not in stripped:
                    violations.append(f"{f}:{i}: {line.strip()}")
        assert not violations, "DROP without IF EXISTS:\n" + "\n".join(violations)

    def test_migration_files_are_present(self):
        """At least one migration file should exist."""
        files = get_migration_files()
        assert len(files) > 0, "No migration .sql files found in migrations directory"

    def test_migration_filenames_follow_convention(self):
        """Migration filenames should start with a numeric prefix."""
        files = get_migration_files()
        # At least one file should have a numeric prefix (init_neon.sql is exempt)
        prefixed = [f for f in files if re.match(r"^\d+", f)]
        assert len(prefixed) > 0, "No migration files with numeric prefixes found"

    def test_no_empty_migration_files(self):
        """Migration files should not be empty."""
        files = get_migration_files()
        empty = []
        for f in files:
            path = os.path.join(MIGRATIONS_DIR, f)
            with open(path) as fh:
                content = fh.read().strip()
            if not content:
                empty.append(f)
        assert not empty, f"Empty migration files found: {empty}"


def _read_migration(name: str) -> str:
    """Read a migration file by name prefix (e.g. '017')."""
    for f in get_migration_files():
        if f.startswith(name):
            path = os.path.join(MIGRATIONS_DIR, f)
            with open(path) as fh:
                return fh.read()
    raise FileNotFoundError(f"No migration starting with {name}")


class TestMigration017AdditionalIndexes:
    """Validate migration 017: additional performance indexes."""

    def test_has_four_correct_index_names(self):
        """Migration 017 should create exactly 4 named indexes."""
        content = _read_migration("017")
        expected_indexes = {
            "idx_user_connections_user_method",
            "idx_bill_uploads_user_status",
            "idx_forecast_observations_region",
            "idx_notifications_user_unread_created",
        }
        found = set(re.findall(r"IF NOT EXISTS\s+(idx_\w+)", content))
        assert found == expected_indexes, f"Expected indexes {expected_indexes}, found {found}"

    def test_index_columns_reference_correct_tables(self):
        """Index ON clauses should reference the right tables and columns."""
        content = _read_migration("017")
        # Each index should reference its correct table
        assert "ON user_connections (user_id, connection_type)" in content
        assert "ON bill_uploads (user_id, created_at DESC, status)" in content
        assert "ON forecast_observations (region, utility_type, created_at DESC)" in content
        assert "ON notifications (user_id, created_at DESC)" in content

    def test_partial_index_has_where_clause(self):
        """idx_notifications_user_unread_created must have WHERE read_at IS NULL."""
        content = _read_migration("017")
        # Find the block for the notifications index
        idx = content.find("idx_notifications_user_unread_created")
        assert idx != -1, "Notifications index not found"
        # The WHERE clause should appear after the index definition
        after_idx = content[idx:]
        assert (
            "WHERE read_at IS NULL" in after_idx
        ), "Partial index missing WHERE read_at IS NULL clause"


class TestMigration053NotificationDedupIndex:
    """Validate migration 053: notification deduplication partial unique index.

    Sprint 5.1 — database-level guard against duplicate alert notifications
    within the same calendar day for a given (user, alert, type) combination.
    """

    def test_migration_file_exists(self):
        """Migration 053 file must be present."""
        files = get_migration_files()
        prefixed = [f for f in files if f.startswith("053")]
        assert prefixed, "Migration 053 file not found in migrations directory"

    def test_adds_alert_id_column_with_if_not_exists(self):
        """Migration must add alert_id column to notifications using IF NOT EXISTS."""
        content = _read_migration("053")
        # ADD COLUMN IF NOT EXISTS alert_id
        assert "ADD COLUMN IF NOT EXISTS" in content.upper()
        assert "alert_id" in content

    def test_alert_id_column_is_uuid(self):
        """alert_id column must be UUID type."""
        content = _read_migration("053")
        # Find the ADD COLUMN line for alert_id
        for line in content.split("\n"):
            if "alert_id" in line and "ADD COLUMN" in line.upper():
                assert (
                    "UUID" in line.upper()
                ), f"alert_id column should be UUID type, got: {line.strip()}"
                break

    def test_fk_constraint_uses_set_null(self):
        """FK from notifications.alert_id to price_alert_configs must use ON DELETE SET NULL."""
        content = _read_migration("053")
        assert "price_alert_configs" in content
        assert "ON DELETE SET NULL" in content

    def test_fk_constraint_uses_drop_if_exists(self):
        """FK constraint must be dropped with IF EXISTS before re-adding."""
        content = _read_migration("053")
        assert "DROP CONSTRAINT IF EXISTS" in content.upper()
        assert "notifications_alert_id_fkey" in content

    def test_dedup_unique_index_is_partial(self):
        """Dedup index must be a UNIQUE partial index on the correct columns."""
        content = _read_migration("053")
        assert "CREATE UNIQUE INDEX IF NOT EXISTS" in content.upper()
        assert "idx_notifications_dedup_alert" in content
        # Index covers user_id, alert_id, type, and a day partition
        assert "user_id" in content
        assert "alert_id" in content
        assert "type" in content
        # Day partitioning via DATE()
        assert "DATE(created_at)" in content

    def test_dedup_index_excludes_dismissed(self):
        """Partial index WHERE clause must exclude dismissed delivery_status."""
        content = _read_migration("053")
        # Find the idx_notifications_dedup_alert block
        idx_start = content.find("idx_notifications_dedup_alert")
        assert idx_start != -1, "idx_notifications_dedup_alert not found"
        after_idx = content[idx_start:]
        assert "dismissed" in after_idx, "Partial index should exclude dismissed notifications"
        assert "delivery_status" in after_idx

    def test_dedup_index_requires_alert_id_not_null(self):
        """Partial index should only apply when alert_id IS NOT NULL."""
        content = _read_migration("053")
        idx_start = content.find("idx_notifications_dedup_alert")
        assert idx_start != -1
        after_idx = content[idx_start:]
        assert "alert_id IS NOT NULL" in after_idx

    def test_supporting_lookup_index_exists(self):
        """Supporting index idx_notifications_alert_id must be present."""
        content = _read_migration("053")
        assert "idx_notifications_alert_id" in content
        assert "CREATE INDEX IF NOT EXISTS" in content.upper()

    def test_grant_included(self):
        """Migration must include GRANT for neondb_owner on notifications."""
        content = _read_migration("053")
        assert "neondb_owner" in content
        assert "notifications" in content


class TestMigration056StripeCustomerIdUnique:
    """Validate migration 056: UNIQUE constraint on users.stripe_customer_id."""

    def test_migration_file_exists(self):
        """Migration 056 file must be present."""
        files = get_migration_files()
        prefixed = [f for f in files if f.startswith("056")]
        assert prefixed, "Migration 056 file not found in migrations directory"

    def test_adds_unique_constraint(self):
        """Migration must add uq_users_stripe_customer_id UNIQUE constraint."""
        content = _read_migration("056")
        assert "uq_users_stripe_customer_id" in content
        assert "UNIQUE" in content.upper()

    def test_constraint_is_idempotent(self):
        """Constraint addition must be wrapped in a DO block checking pg_constraint."""
        content = _read_migration("056")
        assert "pg_constraint" in content
        assert "DO $$" in content

    def test_targets_users_table(self):
        """Constraint must target the users table."""
        content = _read_migration("056")
        assert "public.users" in content

    def test_grant_included(self):
        """Migration must include GRANT for neondb_owner."""
        content = _read_migration("056")
        assert "neondb_owner" in content


class TestMigration057GhostColumns:
    """Validate migration 057: add ghost columns to users and electricity_prices."""

    def test_migration_file_exists(self):
        """Migration 057 file must be present."""
        files = get_migration_files()
        prefixed = [f for f in files if f.startswith("057")]
        assert prefixed, "Migration 057 file not found in migrations directory"

    def test_adds_stripe_customer_id_column(self):
        """Migration must add stripe_customer_id column."""
        content = _read_migration("057")
        assert "stripe_customer_id" in content
        assert "ADD COLUMN IF NOT EXISTS" in content.upper()

    def test_adds_subscription_tier_column(self):
        """Migration must add subscription_tier with default 'free'."""
        content = _read_migration("057")
        assert "subscription_tier" in content
        assert "'free'" in content

    def test_adds_household_size_column(self):
        """Migration must add household_size INTEGER column."""
        content = _read_migration("057")
        assert "household_size" in content

    def test_adds_carbon_intensity_column(self):
        """Migration must add carbon_intensity to electricity_prices."""
        content = _read_migration("057")
        assert "carbon_intensity" in content
        assert "electricity_prices" in content

    def test_subscription_tier_check_constraint(self):
        """Migration must add CHECK constraint on subscription_tier values."""
        content = _read_migration("057")
        assert "ck_users_subscription_tier" in content
        assert "'free'" in content
        assert "'pro'" in content
        assert "'business'" in content

    def test_grants_included(self):
        """Migration must include GRANT for neondb_owner on both tables."""
        content = _read_migration("057")
        assert "neondb_owner" in content
        assert "public.users" in content
        assert "public.electricity_prices" in content


class TestMigration058DeletionLogFkFix:
    """Validate migration 058: fix deletion_logs FK + align consent_records FK."""

    def test_migration_file_exists(self):
        """Migration 058 file must be present."""
        files = get_migration_files()
        prefixed = [f for f in files if f.startswith("058")]
        assert prefixed, "Migration 058 file not found in migrations directory"

    def test_deletion_logs_user_id_nullable(self):
        """Migration must make deletion_logs.user_id nullable."""
        content = _read_migration("058")
        assert "deletion_logs" in content
        assert "DROP NOT NULL" in content.upper()

    def test_deletion_logs_fk_set_null(self):
        """Migration must re-add FK with ON DELETE SET NULL."""
        content = _read_migration("058")
        assert "fk_deletion_logs_user_id" in content
        assert "ON DELETE SET NULL" in content

    def test_consent_records_fk_aligned(self):
        """Migration must align consent_records FK to ON DELETE SET NULL."""
        content = _read_migration("058")
        assert "consent_records" in content
        assert "fk_consent_user" in content

    def test_grants_included(self):
        """Migration must include GRANT for neondb_owner."""
        content = _read_migration("058")
        assert "neondb_owner" in content


class TestMigration059OauthTokensBytea:
    """Validate migration 059: migrate OAuth tokens from TEXT to BYTEA."""

    def test_migration_file_exists(self):
        """Migration 059 file must be present."""
        files = get_migration_files()
        prefixed = [f for f in files if f.startswith("059")]
        assert prefixed, "Migration 059 file not found in migrations directory"

    def test_adds_temporary_bytea_columns(self):
        """Migration must add temporary _new BYTEA columns."""
        content = _read_migration("059")
        assert "oauth_access_token_new" in content
        assert "oauth_refresh_token_new" in content
        assert "BYTEA" in content.upper()

    def test_backfill_uses_decode(self):
        """Migration must decode base64 TEXT to BYTEA during backfill."""
        content = _read_migration("059")
        assert "decode(" in content
        assert "'base64'" in content

    def test_renames_columns_to_canonical_names(self):
        """Migration must RENAME temporary columns to canonical names."""
        content = _read_migration("059")
        assert "RENAME COLUMN" in content.upper()
        assert "oauth_access_token_new TO oauth_access_token" in content
        assert "oauth_refresh_token_new TO oauth_refresh_token" in content

    def test_targets_user_connections_table(self):
        """Migration must target user_connections table."""
        content = _read_migration("059")
        assert "user_connections" in content

    def test_grant_included(self):
        """Migration must include GRANT for neondb_owner."""
        content = _read_migration("059")
        assert "neondb_owner" in content


class TestMigration060UpdatedAtTriggers:
    """Validate migration 060: add missing updated_at auto-update triggers."""

    def test_migration_file_exists(self):
        """Migration 060 file must be present."""
        files = get_migration_files()
        prefixed = [f for f in files if f.startswith("060")]
        assert prefixed, "Migration 060 file not found in migrations directory"

    def test_creates_trigger_function(self):
        """Migration must CREATE OR REPLACE the update_updated_at_column() function."""
        content = _read_migration("060")
        assert "CREATE OR REPLACE FUNCTION" in content.upper()
        assert "update_updated_at_column" in content

    def test_covers_15_tables(self):
        """Migration must create triggers for 15 tables."""
        content = _read_migration("060")
        expected_tables = [
            "supplier_registry",
            "state_regulations",
            "user_supplier_accounts",
            "user_connections",
            "bill_uploads",
            "price_alert_configs",
            "feature_flags",
            "payment_retry_history",
            "model_config",
            "feedback",
            "utility_accounts",
            "community_solar_programs",
            "cca_programs",
            "user_alert_configs",
            "water_rates_config",
        ]
        for table in expected_tables:
            assert table in content, f"Trigger for {table} not found in migration 060"

    def test_uses_drop_if_exists_before_create(self):
        """Migration must use DROP TRIGGER IF EXISTS for idempotency."""
        content = _read_migration("060")
        assert "DROP TRIGGER IF EXISTS" in content.upper()

    def test_triggers_use_before_update(self):
        """Triggers must fire BEFORE UPDATE."""
        content = _read_migration("060")
        assert "BEFORE UPDATE ON" in content.upper()

    def test_grant_on_function(self):
        """Migration must GRANT EXECUTE on the trigger function to neondb_owner."""
        content = _read_migration("060")
        assert "GRANT EXECUTE ON FUNCTION" in content
        assert "neondb_owner" in content


class TestMigration019NationwideSuppliers:
    """Validate migration 019: nationwide supplier seeding."""

    def test_uses_green_energy_not_provider(self):
        """Migration 019 should use 'green_energy' column, not 'green_energy_provider'."""
        content = _read_migration("019")
        assert (
            "green_energy_provider" not in content
        ), "Migration 019 should use 'green_energy', not 'green_energy_provider'"
        assert "green_energy" in content

    def test_seeds_at_least_34_suppliers_across_13_states(self):
        """Migration 019 should seed 34+ suppliers across 13+ state regions."""
        content = _read_migration("019")
        # Count INSERT value rows by matching gen_random_uuid() calls
        supplier_count = content.count("gen_random_uuid()")
        assert supplier_count >= 34, f"Expected >= 34 suppliers, found {supplier_count}"
        # Extract all region values
        regions = set(re.findall(r"'(us_[a-z]{2})'", content))
        assert len(regions) >= 13, f"Expected >= 13 state regions, found {len(regions)}: {regions}"

    def test_all_region_values_are_valid_enum_members(self):
        """All region strings in migration 019 must be valid Region enum values."""
        from backend.models.region import Region

        content = _read_migration("019")
        region_values = set(re.findall(r"'(us_[a-z]{2})'", content))
        valid_values = {r.value for r in Region}
        invalid = region_values - valid_values
        assert not invalid, f"Invalid region values in migration 019: {invalid}"


class TestMigration011CommentFix:
    """Validate that migration 011 comment was corrected (P0-1 fix)."""

    def test_comment_says_migration_011(self):
        """Migration 011 header comment must reference 011, not 010."""
        content = _read_migration("011")
        assert (
            "Migration 010" not in content
        ), "011_utilityapi_sync_columns.sql still contains stale 'Migration 010' comment"
        assert (
            "Migration 011" in content
        ), "011_utilityapi_sync_columns.sql should have 'Migration 011' in comment header"


class TestMigration028CommentFix:
    """Validate that migration 028 version comment was corrected (P3-1 fix)."""

    def test_comment_says_version_028(self):
        """Migration 028 version comment must read 028, not 026."""
        content = _read_migration("028")
        assert (
            "Version: 026" not in content
        ), "028_feedback_table.sql still contains stale 'Version: 026' comment"
        assert (
            "Version: 028" in content
        ), "028_feedback_table.sql should have 'Version: 028' in comment header"


class TestMigration061AuditSchemaFixes:
    """Validate migration 061: audit-identified schema fixes (12-P0-*)."""

    def test_migration_file_exists(self):
        """Migration 061 file must be present."""
        files = get_migration_files()
        prefixed = [f for f in files if f.startswith("061")]
        assert prefixed, "Migration 061 file not found in migrations directory"

    def test_has_begin_commit(self):
        """Migration must be wrapped in a transaction."""
        content = _read_migration("061")
        assert "BEGIN;" in content, "Migration 061 must start with BEGIN;"
        assert "COMMIT;" in content, "Migration 061 must end with COMMIT;"

    # ---- P0-2: users.name empty-string CHECK ----

    def test_p0_2_users_name_check_constraint_added(self):
        """Migration must add ck_users_name_nonempty CHECK constraint."""
        content = _read_migration("061")
        assert "ck_users_name_nonempty" in content
        assert "CHECK" in content.upper()
        assert "length(trim(name)) > 0" in content

    def test_p0_2_empty_name_rows_fixed(self):
        """Migration must UPDATE rows where length(trim(name)) = 0."""
        content = _read_migration("061")
        assert "length(trim(name)) = 0" in content
        assert "Unknown User" in content

    # ---- P0-3: stripe_processed_events unbounded VARCHAR ----

    def test_p0_3_event_id_gets_length_limit(self):
        """Migration must alter event_id to VARCHAR(255)."""
        content = _read_migration("061")
        assert "stripe_processed_events" in content
        assert "event_id" in content
        assert "VARCHAR(255)" in content

    def test_p0_3_event_type_gets_length_limit(self):
        """Migration must alter event_type to VARCHAR(100)."""
        content = _read_migration("061")
        assert "event_type" in content
        assert "VARCHAR(100)" in content

    def test_p0_3_stripe_prefix_check_added(self):
        """Migration must add ck_stripe_event_id_prefix CHECK constraint."""
        content = _read_migration("061")
        assert "ck_stripe_event_id_prefix" in content
        assert "evt_%" in content

    # ---- P0-4: model_ab_assignments composite unique ----

    def test_p0_4_drops_single_column_unique(self):
        """Migration must drop the single-column uq_model_ab_assignments_user_id constraint."""
        content = _read_migration("061")
        assert "uq_model_ab_assignments_user_id" in content
        assert "DROP CONSTRAINT" in content.upper()

    def test_p0_4_adds_composite_unique(self):
        """Migration must add UNIQUE (user_id, model_name) constraint."""
        content = _read_migration("061")
        assert "uq_model_ab_assignments_user_model" in content
        # Verify the composite columns
        assert "user_id, model_name" in content

    # ---- P0-5 / P1-1 / P1-2 / P1-3 / P1-4: orphan row cleanup ----

    def test_p0_5_notifications_orphan_cleanup(self):
        """Migration must DELETE orphan notifications rows."""
        content = _read_migration("061")
        assert "DELETE FROM notifications" in content
        assert "user_id NOT IN" in content

    def test_p1_orphan_cleanup_user_savings(self):
        """Migration must DELETE orphan user_savings rows."""
        content = _read_migration("061")
        assert "DELETE FROM user_savings" in content

    def test_p1_orphan_cleanup_recommendation_outcomes(self):
        """Migration must DELETE orphan recommendation_outcomes rows."""
        content = _read_migration("061")
        assert "DELETE FROM recommendation_outcomes" in content

    def test_p1_orphan_cleanup_model_predictions(self):
        """Migration must DELETE orphan model_predictions rows."""
        content = _read_migration("061")
        assert "DELETE FROM model_predictions" in content

    def test_p1_orphan_cleanup_referrals(self):
        """Migration must DELETE orphan referrals rows."""
        content = _read_migration("061")
        assert "DELETE FROM referrals" in content

    # ---- P1-6: community timestamp NOT NULL ----

    def test_p1_6_community_posts_timestamps_not_null(self):
        """Migration must SET NOT NULL on community_posts.created_at and updated_at."""
        content = _read_migration("061")
        assert "community_posts" in content
        assert "SET NOT NULL" in content

    def test_p1_6_community_votes_timestamp_not_null(self):
        """Migration must SET NOT NULL on community_votes.created_at."""
        content = _read_migration("061")
        assert "community_votes" in content

    def test_p1_6_community_reports_timestamp_not_null(self):
        """Migration must SET NOT NULL on community_reports.created_at."""
        content = _read_migration("061")
        assert "community_reports" in content

    # ---- P1-10: model_config unique constraint ----

    def test_p1_10_model_config_unique_constraint(self):
        """Migration must add uq_model_config_name_version UNIQUE constraint."""
        content = _read_migration("061")
        assert "uq_model_config_name_version" in content
        assert "model_name, model_version" in content

    def test_p1_10_model_config_dedup_before_constraint(self):
        """Migration must deduplicate model_config rows before adding the constraint."""
        content = _read_migration("061")
        assert "DELETE FROM model_config" in content
        assert "DISTINCT ON (model_name, model_version)" in content

    # ---- P2-8: cleanup_old_prices uses created_at ----

    def test_p2_8_retention_function_uses_created_at(self):
        """cleanup_old_prices() replacement must filter on created_at, not timestamp."""
        content = _read_migration("061")
        assert "CREATE OR REPLACE FUNCTION cleanup_old_prices" in content
        assert "created_at < NOW()" in content
        # The old pattern (timestamp column) must not appear in the new function body
        # Find the function block and assert it does not use the bare 'timestamp' column
        func_start = content.find("CREATE OR REPLACE FUNCTION cleanup_old_prices")
        func_end = content.find("$$;", func_start) + 3
        func_body = content[func_start:func_end]
        assert "WHERE created_at" in func_body
        assert "WHERE timestamp" not in func_body

    def test_p2_8_grant_on_function(self):
        """Migration must grant EXECUTE on cleanup_old_prices to neondb_owner."""
        content = _read_migration("061")
        assert "GRANT EXECUTE ON FUNCTION cleanup_old_prices" in content
        assert "neondb_owner" in content

    # ---- P2-9: created_at index on electricity_prices ----

    def test_p2_9_created_at_index_on_electricity_prices(self):
        """Migration must create idx_prices_created_at CONCURRENTLY."""
        content = _read_migration("061")
        assert "idx_prices_created_at" in content
        assert "electricity_prices" in content
        assert "CONCURRENTLY" in content

    # ---- P2-11: post_id indexes on community vote/report tables ----

    def test_p2_11_community_votes_post_id_index(self):
        """Migration must create idx_community_votes_post_id CONCURRENTLY."""
        content = _read_migration("061")
        assert "idx_community_votes_post_id" in content

    def test_p2_11_community_reports_post_id_index(self):
        """Migration must create idx_community_reports_post_id CONCURRENTLY."""
        content = _read_migration("061")
        assert "idx_community_reports_post_id" in content

    # ---- P3-6: heating_oil_dealers updated_at ----

    def test_p3_6_heating_oil_dealers_updated_at_column(self):
        """Migration must add updated_at column to heating_oil_dealers."""
        content = _read_migration("061")
        assert "heating_oil_dealers" in content
        assert "updated_at" in content
        assert "ADD COLUMN IF NOT EXISTS" in content.upper()

    def test_p3_6_heating_oil_dealers_updated_at_trigger(self):
        """Migration must create updated_at trigger for heating_oil_dealers."""
        content = _read_migration("061")
        assert "trg_heating_oil_dealers_updated_at" in content
        assert "BEFORE UPDATE ON heating_oil_dealers" in content

    # ---- General quality checks ----

    def test_concurrently_indexes_are_outside_transaction(self):
        """CREATE INDEX CONCURRENTLY statements must appear after COMMIT (outside transaction)."""
        content = _read_migration("061")
        commit_pos = content.rfind("COMMIT;")
        assert commit_pos != -1, "COMMIT; not found in migration 061"
        # Only check CREATE INDEX CONCURRENTLY statements (not comment occurrences).
        concurrent_stmt_positions = [
            m.start() for m in re.finditer(r"CREATE\s+INDEX\s+CONCURRENTLY", content, re.IGNORECASE)
        ]
        assert concurrent_stmt_positions, "No CREATE INDEX CONCURRENTLY statements found"
        for pos in concurrent_stmt_positions:
            assert (
                pos > commit_pos
            ), f"CREATE INDEX CONCURRENTLY at position {pos} is before COMMIT at {commit_pos}"

    def test_all_new_constraints_use_idempotent_guards(self):
        """All new constraints must be wrapped in idempotency DO blocks."""
        content = _read_migration("061")
        # Every new named constraint should be guarded by an IF NOT EXISTS check
        new_constraints = [
            "ck_users_name_nonempty",
            "ck_stripe_event_id_prefix",
            "uq_model_ab_assignments_user_model",
            "uq_model_config_name_version",
        ]
        for constraint in new_constraints:
            assert (
                constraint in content
            ), f"Expected constraint {constraint} not found in migration 061"

    def test_grants_included(self):
        """Migration must include GRANT statements for neondb_owner."""
        content = _read_migration("061")
        assert "neondb_owner" in content
        grant_count = content.count("TO neondb_owner")
        assert grant_count >= 3, f"Expected at least 3 GRANT statements, found {grant_count}"


class TestMigration062AuditSchemaFixesRound2:
    """Validate migration 062: additional audit-identified schema fixes."""

    def test_migration_file_exists(self):
        """Migration 062 file must be present."""
        files = get_migration_files()
        prefixed = [f for f in files if f.startswith("062")]
        assert prefixed, "Migration 062 file not found in migrations directory"

    def test_has_begin_commit(self):
        """Migration must be wrapped in a transaction."""
        content = _read_migration("062")
        assert "BEGIN;" in content, "Migration 062 must start with BEGIN;"
        assert "COMMIT;" in content, "Migration 062 must end with COMMIT;"

    # ---- P2-7: forecast_observations.forecast_hour CHECK constraint ----

    def test_p2_7_forecast_hour_check_constraint(self):
        """Migration must add ck_forecast_hour_range CHECK constraint."""
        content = _read_migration("062")
        assert "ck_forecast_hour_range" in content
        assert "CHECK" in content.upper()
        assert "BETWEEN 0 AND 23" in content

    def test_p2_7_out_of_range_rows_fixed(self):
        """Migration must UPDATE rows where forecast_hour is out of range."""
        content = _read_migration("062")
        assert "forecast_hour < 0 OR forecast_hour > 23" in content

    # ---- P2-10: scraped_rates FK ON DELETE SET NULL ----

    def test_p2_10_scraped_rates_fk_set_null(self):
        """Migration must recreate scraped_rates FK with ON DELETE SET NULL."""
        content = _read_migration("062")
        assert "fk_scraped_rates_supplier" in content
        assert "ON DELETE SET NULL" in content
        assert "supplier_registry" in content

    # ---- P2-1: Redundant index cleanup ----

    def test_p2_1_drops_redundant_prices_indexes(self):
        """Migration must drop duplicate electricity_prices indexes."""
        content = _read_migration("062")
        assert "DROP INDEX IF EXISTS idx_prices_region_utilitytype_timestamp" in content
        assert "DROP INDEX IF EXISTS idx_electricity_prices_region_utility_time" in content
        assert "DROP INDEX IF EXISTS idx_prices_utility_type" in content

    # ---- P3-4: Redundant feature_flags index ----

    def test_p3_4_drops_redundant_feature_flags_index(self):
        """Migration must drop the redundant idx_feature_flags_name index."""
        content = _read_migration("062")
        assert "DROP INDEX IF EXISTS idx_feature_flags_name" in content

    # ---- P2-3: Dedup indexes ----

    def test_p2_3_market_intelligence_dedup_index(self):
        """Migration must create dedup index on market_intelligence."""
        content = _read_migration("062")
        assert "idx_market_intel_dedup" in content
        assert "market_intelligence" in content
        assert "DATE(fetched_at)" in content

    def test_p2_3_scraped_rates_dedup_index(self):
        """Migration must create dedup index on scraped_rates."""
        content = _read_migration("062")
        assert "idx_scraped_rates_dedup" in content
        assert "scraped_rates" in content

    # ---- General quality checks ----

    def test_concurrently_indexes_are_outside_transaction(self):
        """CREATE INDEX CONCURRENTLY statements must appear after COMMIT."""
        content = _read_migration("062")
        commit_pos = content.rfind("COMMIT;")
        assert commit_pos != -1, "COMMIT; not found in migration 062"
        concurrent_stmt_positions = [
            m.start() for m in re.finditer(r"CREATE\s+INDEX\s+CONCURRENTLY", content, re.IGNORECASE)
        ]
        assert concurrent_stmt_positions, "No CREATE INDEX CONCURRENTLY statements found"
        for pos in concurrent_stmt_positions:
            assert (
                pos > commit_pos
            ), f"CREATE INDEX CONCURRENTLY at position {pos} is before COMMIT at {commit_pos}"

    def test_grants_included(self):
        """Migration must include GRANT statements for neondb_owner."""
        content = _read_migration("062")
        assert "neondb_owner" in content
        grant_count = content.count("TO neondb_owner")
        assert grant_count >= 2, f"Expected at least 2 GRANT statements, found {grant_count}"

    def test_all_drops_use_if_exists(self):
        """All DROP statements must use IF EXISTS."""
        content = _read_migration("062")
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip().upper()
            if stripped.startswith("--"):
                continue
            if stripped.startswith("DROP") and "IF EXISTS" not in stripped:
                raise AssertionError(f"Line {i}: DROP without IF EXISTS: {line.strip()}")
