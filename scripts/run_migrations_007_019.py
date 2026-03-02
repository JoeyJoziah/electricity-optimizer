#!/usr/bin/env python3
"""
Comprehensive Production Migration Runner: 007 → 019
=====================================================
Applies ALL missing migrations (007-019) to the production database.
Handles CONCURRENTLY indexes with autocommit and fixes known issues.

CRITICAL: Uses DATABASE_URL from environment (ep-withered-morning endpoint).
         Do NOT use Neon MCP — it targets a different endpoint.

Usage:
    # Dry run (pre-flight checks only):
    DATABASE_URL="postgres://..." python3 scripts/run_migrations_007_019.py --dry-run

    # Full run:
    DATABASE_URL="postgres://..." python3 scripts/run_migrations_007_019.py
"""

import asyncio
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

try:
    import asyncpg
except ImportError:
    print("ERROR: asyncpg not installed. Run: pip install asyncpg")
    sys.exit(1)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "backend" / "migrations"

# Migrations that use CREATE INDEX CONCURRENTLY (cannot run inside transaction)
CONCURRENT_MIGRATIONS = {"010_utility_type_index.sql", "017_additional_indexes.sql", "020_price_query_indexes.sql"}

# Known fixes for migration bugs
MIGRATION_FIXES = {
    "017_additional_indexes.sql": {
        # Bug: column is 'connection_type' not 'connection_method'
        "connection_method": "connection_type",
    }
}

# Ordered list of migrations to apply
MIGRATION_FILES = [
    "007_user_supplier_accounts.sql",
    "008_connection_feature.sql",
    "009_email_oauth_tokens.sql",
    "010_utility_type_index.sql",
    "011_utilityapi_sync_columns.sql",
    "012_user_savings.sql",
    "013_user_profile_columns.sql",
    "014_alert_tables.sql",
    "015_notifications.sql",
    "016_feature_flags.sql",
    "017_additional_indexes.sql",
    "018_nationwide_defaults.sql",
    "019_nationwide_suppliers.sql",
    "020_price_query_indexes.sql",
]


class ComprehensiveMigrationRunner:
    def __init__(self, database_url: str, dry_run: bool = False):
        self.database_url = database_url
        self.dry_run = dry_run
        self.conn: asyncpg.Connection | None = None
        self.results: dict[str, str] = {}  # migration -> status
        self.errors: list[str] = []

    async def connect(self):
        print("\n[CONNECT] Connecting to database...")
        # Safety check
        if "ep-lingering-forest" in self.database_url and "ep-withered-morning" not in self.database_url:
            print("  ABORT: Detected Neon MCP endpoint (ep-lingering-forest).")
            print("  Must use app endpoint (ep-withered-morning).")
            sys.exit(1)

        self.conn = await asyncpg.connect(self.database_url)
        server = await self.conn.fetchval("SELECT current_setting('server_version')")
        db_name = await self.conn.fetchval("SELECT current_database()")
        print(f"  Connected: {db_name} (PostgreSQL {server})")

    async def pre_flight(self):
        print("\n[PRE-FLIGHT] Checking current schema state...")

        # Check prerequisite tables
        for table in ["users", "suppliers", "electricity_prices", "supplier_registry", "state_regulations"]:
            exists = await self.conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)", table
            )
            status = "OK" if exists else "MISSING"
            print(f"  {table}: {status}")
            if not exists and table in ("users", "supplier_registry"):
                self.errors.append(f"Required table '{table}' missing — run init + 006 first")

        # Check what's already applied
        check_tables = {
            "007": "user_supplier_accounts",
            "008": "user_connections",
            "012": "user_savings",
            "014": "price_alert_configs",
            "015": "notifications",
            "016": "feature_flags",
        }
        print("\n  Migration table presence:")
        for mig, table in check_tables.items():
            exists = await self.conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)", table
            )
            print(f"    {mig} ({table}): {'already exists' if exists else 'needs creation'}")

        # Check users columns from 013
        for col in ["utility_types", "current_supplier_id", "annual_usage_kwh", "onboarding_completed"]:
            exists = await self.conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = $1)", col
            )
            print(f"    013 (users.{col}): {'exists' if exists else 'needs adding'}")

        # Counts
        user_count = await self.conn.fetchval("SELECT count(*) FROM users")
        supplier_count = await self.conn.fetchval("SELECT count(*) FROM supplier_registry")
        print(f"\n  Users: {user_count}, Suppliers in registry: {supplier_count}")

        if self.errors:
            print("\n  BLOCKING ERRORS:")
            for e in self.errors:
                print(f"    - {e}")
            return False

        print("  Pre-flight checks passed.")
        return True

    async def run_migration(self, filename: str) -> bool:
        filepath = MIGRATIONS_DIR / filename
        if not filepath.exists():
            print(f"    WARNING: {filename} not found, skipping")
            self.results[filename] = "SKIPPED (file not found)"
            return True

        sql = filepath.read_text()

        # Apply known fixes
        if filename in MIGRATION_FIXES:
            for old, new in MIGRATION_FIXES[filename].items():
                if old in sql:
                    sql = sql.replace(old, new)
                    print(f"    FIX applied: '{old}' -> '{new}'")

        if self.dry_run:
            print(f"    [DRY RUN] Would execute {filename} ({len(sql)} bytes)")
            self.results[filename] = "DRY RUN"
            return True

        is_concurrent = filename in CONCURRENT_MIGRATIONS

        try:
            if is_concurrent:
                # CONCURRENTLY indexes cannot run inside a transaction.
                # Close current connection, open a new one with autocommit.
                # Split SQL into individual statements and run each.
                statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]
                for stmt in statements:
                    if not stmt:
                        continue
                    try:
                        # For CONCURRENTLY, we need a fresh connection outside a transaction
                        temp_conn = await asyncpg.connect(self.database_url)
                        await temp_conn.execute(stmt)
                        await temp_conn.close()
                    except asyncpg.exceptions.DuplicateObjectError:
                        print(f"    (index already exists, continuing)")
                        if temp_conn and not temp_conn.is_closed():
                            await temp_conn.close()
                    except Exception as e:
                        err_str = str(e).lower()
                        if "already exists" in err_str or "does not exist" in err_str:
                            print(f"    (skipping: {e})")
                            if temp_conn and not temp_conn.is_closed():
                                await temp_conn.close()
                        else:
                            raise
            else:
                await self.conn.execute(sql)

            self.results[filename] = "APPLIED"
            return True

        except Exception as e:
            err_str = str(e).lower()
            if "already exists" in err_str or "already" in err_str:
                print(f"    (idempotent — already applied: {e})")
                self.results[filename] = "ALREADY APPLIED"
                return True
            print(f"    ERROR: {e}")
            self.errors.append(f"{filename}: {e}")
            self.results[filename] = f"FAILED: {e}"
            return False

    async def run_all_migrations(self):
        total = len(MIGRATION_FILES)
        for i, filename in enumerate(MIGRATION_FILES, 1):
            print(f"\n[{i}/{total}] {filename}")
            success = await self.run_migration(filename)
            if not success:
                # Non-blocking tables: continue even if one fails
                # But block on critical migrations
                critical = filename.startswith(("007_", "008_", "013_", "014_"))
                if critical:
                    print(f"  CRITICAL migration failed. Stopping.")
                    return False
                print(f"  Non-critical failure, continuing...")
        return True

    async def validate(self):
        print("\n[VALIDATE] Post-migration validation...")
        all_good = True

        # 1. Check all expected tables exist
        expected_tables = [
            "user_supplier_accounts", "user_connections", "bill_uploads",
            "connection_extracted_rates", "user_savings", "price_alert_configs",
            "alert_history", "notifications", "feature_flags",
        ]
        for table in expected_tables:
            exists = await self.conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)", table
            )
            status = "PASS" if exists else "FAIL"
            if status == "FAIL":
                all_good = False
            print(f"  [{status}] Table: {table}")

        # 2. Check users columns from 013
        for col in ["utility_types", "current_supplier_id", "annual_usage_kwh", "onboarding_completed"]:
            exists = await self.conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = $1)", col
            )
            status = "PASS" if exists else "FAIL"
            if status == "FAIL":
                all_good = False
            print(f"  [{status}] users.{col}")

        # 3. Check region is nullable (018)
        nullable = await self.conn.fetchval("""
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'region'
        """)
        status = "PASS" if nullable == "YES" else "FAIL"
        if status == "FAIL":
            all_good = False
        print(f"  [{status}] users.region nullable = {nullable} (expected: YES)")

        # 4. Check onboarding backfill
        not_backfilled = await self.conn.fetchval("""
            SELECT count(*) FROM users
            WHERE region IS NOT NULL AND (onboarding_completed IS NULL OR onboarding_completed = FALSE)
        """)
        status = "PASS" if not_backfilled == 0 else "FAIL"
        if status == "FAIL":
            all_good = False
        print(f"  [{status}] Users with region but not onboarded: {not_backfilled} (expected: 0)")

        # 5. Supplier count
        supplier_count = await self.conn.fetchval("SELECT count(*) FROM supplier_registry WHERE is_active = true")
        status = "PASS" if supplier_count >= 30 else "WARN"
        print(f"  [{status}] Active suppliers: {supplier_count} (expected: 30+)")

        # 6. Supplier distribution
        rows = await self.conn.fetch("""
            SELECT unnest(regions) as state, count(*) as cnt
            FROM supplier_registry WHERE is_active = true
            GROUP BY state ORDER BY state
        """)
        print(f"\n  Supplier distribution ({len(rows)} states):")
        for row in rows:
            print(f"    {row['state']}: {row['cnt']} suppliers")

        # 7. Feature flags
        ff_count = await self.conn.fetchval("SELECT count(*) FROM feature_flags")
        print(f"\n  [{('PASS' if ff_count >= 5 else 'WARN')}] Feature flags: {ff_count}")

        return all_good

    async def summary(self, validation_passed: bool):
        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"  Timestamp:  {ts}")
        print(f"  Dry run:    {self.dry_run}")
        print(f"  Validation: {'PASSED' if validation_passed else 'FAILED'}")
        print()
        for filename, status in self.results.items():
            icon = "+" if "APPLIED" in status else ("~" if "DRY" in status or "ALREADY" in status else "!")
            print(f"  [{icon}] {filename}: {status}")
        if self.errors:
            print(f"\n  Errors ({len(self.errors)}):")
            for e in self.errors:
                print(f"    - {e}")
        print("=" * 60)

    async def run(self):
        print("=" * 60)
        print("Comprehensive Production Migration Runner: 007 → 019")
        print("=" * 60)

        await self.connect()

        if not await self.pre_flight():
            print("\nAborting due to pre-flight failures.")
            await self.conn.close()
            return False

        if not await self.run_all_migrations():
            print("\nMigration sequence failed.")
            validation = await self.validate() if not self.dry_run else True
            await self.summary(validation)
            await self.conn.close()
            return False

        validation = True
        if not self.dry_run:
            validation = await self.validate()

        await self.summary(validation)
        await self.conn.close()
        return validation


async def main():
    parser = argparse.ArgumentParser(description="Run migrations 007-019 (comprehensive)")
    parser.add_argument("--dry-run", action="store_true", help="Pre-flight checks only, no changes")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set.")
        sys.exit(1)

    runner = ComprehensiveMigrationRunner(database_url, dry_run=args.dry_run)
    success = await runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
