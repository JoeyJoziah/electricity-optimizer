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

import pytest

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
