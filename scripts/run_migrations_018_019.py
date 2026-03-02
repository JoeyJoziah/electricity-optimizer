#!/usr/bin/env python3
"""
Production Migration Runner for 018 + 019
==========================================
Runs migrations 018 (nationwide defaults) and 019 (nationwide suppliers)
against the production database with full pre-flight checks and validation.

CRITICAL: Uses DATABASE_URL from environment (ep-withered-morning endpoint).
         Do NOT use Neon MCP — it targets a different endpoint.

Usage:
    # Dry run (pre-flight checks only, no changes):
    DATABASE_URL="postgres://..." python3 scripts/run_migrations_018_019.py --dry-run

    # Full run:
    DATABASE_URL="postgres://..." python3 scripts/run_migrations_018_019.py

    # Or source from .env:
    source backend/.env && python3 scripts/run_migrations_018_019.py
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
MIGRATION_018 = PROJECT_ROOT / "backend" / "migrations" / "018_nationwide_defaults.sql"
MIGRATION_019 = PROJECT_ROOT / "backend" / "migrations" / "019_nationwide_suppliers.sql"


class MigrationRunner:
    def __init__(self, database_url: str, dry_run: bool = False):
        self.database_url = database_url
        self.dry_run = dry_run
        self.conn: asyncpg.Connection | None = None
        self.pre_state: dict = {}
        self.errors: list[str] = []

    async def connect(self):
        print("\n[1/6] Connecting to database...")
        self.conn = await asyncpg.connect(self.database_url)
        # Verify we're on the correct endpoint
        server = await self.conn.fetchval("SELECT current_setting('server_version')")
        db_name = await self.conn.fetchval("SELECT current_database()")
        print(f"  Connected: {db_name} (PostgreSQL {server})")

        # Safety check — verify this is the app endpoint, not the Neon MCP one
        if "ep-withered-morning" not in self.database_url and "ep-lingering-forest" in self.database_url:
            print("  WARNING: This looks like the Neon MCP endpoint, not the app endpoint!")
            print("  The app uses ep-withered-morning. Aborting.")
            sys.exit(1)

    async def pre_flight_checks(self):
        """Check schema state before running migrations."""
        print("\n[2/6] Pre-flight checks...")

        # Check if users table exists
        exists = await self.conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users')"
        )
        if not exists:
            self.errors.append("users table does not exist!")
            return

        # Check region column nullability (018 changes this)
        region_nullable = await self.conn.fetchval("""
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'region'
        """)
        self.pre_state["region_nullable"] = region_nullable
        print(f"  users.region nullable: {region_nullable}")

        if region_nullable == "YES":
            print("  -> Migration 018 may have already been applied (region is already nullable)")

        # Check if onboarding_completed column exists
        onboarding_col = await self.conn.fetchval("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'onboarding_completed'
        """)
        self.pre_state["has_onboarding_col"] = onboarding_col is not None
        print(f"  users.onboarding_completed exists: {onboarding_col is not None}")

        if not onboarding_col:
            self.errors.append(
                "onboarding_completed column missing! Migration 013 must be applied first."
            )

        # Check price_alert_configs table
        pac_exists = await self.conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'price_alert_configs')"
        )
        self.pre_state["has_alert_configs"] = pac_exists
        print(f"  price_alert_configs table exists: {pac_exists}")

        # Check supplier_registry
        sr_exists = await self.conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'supplier_registry')"
        )
        self.pre_state["has_supplier_registry"] = sr_exists
        print(f"  supplier_registry table exists: {sr_exists}")

        if not sr_exists:
            self.errors.append(
                "supplier_registry table missing! Migration 006 must be applied first."
            )

        # Count existing suppliers
        if sr_exists:
            count = await self.conn.fetchval("SELECT count(*) FROM supplier_registry")
            self.pre_state["supplier_count_before"] = count
            print(f"  supplier_registry row count: {count}")

        # Count users and their onboarding status
        user_count = await self.conn.fetchval("SELECT count(*) FROM users")
        self.pre_state["user_count"] = user_count
        print(f"  Total users: {user_count}")

        if onboarding_col:
            onboarded = await self.conn.fetchval(
                "SELECT count(*) FROM users WHERE onboarding_completed = TRUE"
            )
            not_onboarded_with_region = await self.conn.fetchval(
                "SELECT count(*) FROM users WHERE region IS NOT NULL AND (onboarding_completed IS NULL OR onboarding_completed = FALSE)"
            )
            self.pre_state["already_onboarded"] = onboarded
            self.pre_state["will_be_backfilled"] = not_onboarded_with_region
            print(f"  Already onboarded: {onboarded}")
            print(f"  Will be backfilled by 018: {not_onboarded_with_region}")

        if self.errors:
            print("\n  ERRORS found — cannot proceed:")
            for e in self.errors:
                print(f"    - {e}")
            return False

        print("  All pre-flight checks passed.")
        return True

    async def run_migration_018(self):
        """Run migration 018: nationwide defaults."""
        print("\n[3/6] Running migration 018 (nationwide defaults)...")

        if self.dry_run:
            print("  [DRY RUN] Would execute:")
            print(f"    {MIGRATION_018.read_text().strip()}")
            return True

        sql = MIGRATION_018.read_text()
        try:
            await self.conn.execute(sql)
            print("  Migration 018 applied successfully.")
            return True
        except Exception as e:
            # Check if it's a "column already nullable" type situation
            err_str = str(e)
            if "already" in err_str.lower():
                print(f"  Migration 018 partially applied (idempotent): {e}")
                return True
            print(f"  ERROR: {e}")
            self.errors.append(f"Migration 018 failed: {e}")
            return False

    async def run_migration_019(self):
        """Run migration 019: nationwide suppliers."""
        print("\n[4/6] Running migration 019 (nationwide suppliers)...")

        if self.dry_run:
            print("  [DRY RUN] Would insert ~33 suppliers across 13 states")
            return True

        sql = MIGRATION_019.read_text()
        try:
            result = await self.conn.execute(sql)
            print(f"  Migration 019 applied successfully. Result: {result}")
            return True
        except Exception as e:
            print(f"  ERROR: {e}")
            self.errors.append(f"Migration 019 failed: {e}")
            return False

    async def validate(self):
        """Post-migration validation."""
        print("\n[5/6] Post-migration validation...")
        all_good = True

        # 1. Verify region is nullable
        nullable = await self.conn.fetchval("""
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'region'
        """)
        status = "PASS" if nullable == "YES" else "FAIL"
        if status == "FAIL":
            all_good = False
        print(f"  [{status}] users.region nullable = {nullable} (expected: YES)")

        # 2. Verify onboarding backfill
        not_backfilled = await self.conn.fetchval("""
            SELECT count(*) FROM users
            WHERE region IS NOT NULL AND (onboarding_completed IS NULL OR onboarding_completed = FALSE)
        """)
        status = "PASS" if not_backfilled == 0 else "FAIL"
        if status == "FAIL":
            all_good = False
        print(f"  [{status}] Users with region but not onboarded: {not_backfilled} (expected: 0)")

        # 3. Verify supplier count increased
        supplier_count = await self.conn.fetchval("SELECT count(*) FROM supplier_registry")
        before = self.pre_state.get("supplier_count_before", 0)
        status = "PASS" if supplier_count > before else "WARN"
        print(f"  [{status}] supplier_registry: {before} -> {supplier_count}")

        # 4. Verify specific state suppliers exist
        states_to_check = ["us_tx", "us_ny", "us_ca", "us_fl", "us_pa"]
        for state in states_to_check:
            count = await self.conn.fetchval(
                "SELECT count(*) FROM supplier_registry WHERE $1 = ANY(regions) AND is_active = true",
                state,
            )
            status = "PASS" if count > 0 else "FAIL"
            if status == "FAIL":
                all_good = False
            print(f"  [{status}] Suppliers for {state}: {count}")

        # 5. Verify total supplier count is reasonable
        status = "PASS" if supplier_count >= 30 else "WARN"
        print(f"  [{status}] Total active suppliers: {supplier_count} (expected: 30+)")

        # 6. List suppliers by state for visual confirmation
        print("\n  Supplier distribution by state:")
        rows = await self.conn.fetch("""
            SELECT unnest(regions) as state, count(*) as cnt
            FROM supplier_registry WHERE is_active = true
            GROUP BY state ORDER BY state
        """)
        for row in rows:
            print(f"    {row['state']}: {row['cnt']} suppliers")

        return all_good

    async def summary(self, validation_passed: bool):
        """Print final summary."""
        print("\n[6/6] Summary")
        print("=" * 50)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"  Timestamp: {ts}")
        print(f"  Dry run: {self.dry_run}")
        print(f"  Migration 018: {'applied' if not self.dry_run else 'skipped (dry run)'}")
        print(f"  Migration 019: {'applied' if not self.dry_run else 'skipped (dry run)'}")
        print(f"  Validation: {'PASSED' if validation_passed else 'FAILED'}")
        if self.errors:
            print(f"  Errors: {len(self.errors)}")
            for e in self.errors:
                print(f"    - {e}")
        print("=" * 50)

    async def run(self):
        """Execute the full migration pipeline."""
        print("=" * 50)
        print("Production Migration Runner: 018 + 019")
        print("=" * 50)

        await self.connect()

        ok = await self.pre_flight_checks()
        if not ok:
            print("\nAborting due to pre-flight check failures.")
            await self.conn.close()
            return False

        if not await self.run_migration_018():
            print("\nMigration 018 failed. Stopping before 019.")
            await self.conn.close()
            return False

        if not await self.run_migration_019():
            print("\nMigration 019 failed.")
            await self.conn.close()
            return False

        validation_passed = True
        if not self.dry_run:
            validation_passed = await self.validate()

        await self.summary(validation_passed)
        await self.conn.close()
        return validation_passed


async def main():
    parser = argparse.ArgumentParser(description="Run migrations 018 + 019")
    parser.add_argument("--dry-run", action="store_true", help="Pre-flight checks only, no changes")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set.")
        print("  Set it with: export DATABASE_URL='postgres://...'")
        print("  Or source from: source backend/.env")
        sys.exit(1)

    runner = MigrationRunner(database_url, dry_run=args.dry_run)
    success = await runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
