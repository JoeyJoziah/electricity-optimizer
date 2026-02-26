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
        assert len(numbers) == len(set(numbers)), (
            f"Duplicate migration numbers: {duplicates}"
        )

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
        assert not violations, (
            "CREATE TABLE without IF NOT EXISTS:\n" + "\n".join(violations)
        )

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
        assert not violations, (
            "CREATE INDEX without guard (IF NOT EXISTS or CONCURRENTLY):\n"
            + "\n".join(violations)
        )

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
        assert not violations, (
            "ADD COLUMN without IF NOT EXISTS:\n" + "\n".join(violations)
        )

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
        assert not violations, (
            "DROP without IF EXISTS:\n" + "\n".join(violations)
        )

    def test_migration_files_are_present(self):
        """At least one migration file should exist."""
        files = get_migration_files()
        assert len(files) > 0, "No migration .sql files found in migrations directory"

    def test_migration_filenames_follow_convention(self):
        """Migration filenames should start with a numeric prefix."""
        files = get_migration_files()
        # At least one file should have a numeric prefix (init_neon.sql is exempt)
        prefixed = [f for f in files if re.match(r"^\d+", f)]
        assert len(prefixed) > 0, (
            "No migration files with numeric prefixes found"
        )

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
