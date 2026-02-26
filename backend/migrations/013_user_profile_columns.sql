-- =============================================================================
-- Migration 013: Add extended profile columns to users table
-- Date: 2026-02-25
-- =============================================================================
--
-- Adds columns required by the /api/v1/users/profile endpoints:
--   • utility_types         — comma-separated list of energy types the user monitors
--   • current_supplier_id   — UUID FK to suppliers.id (nullable)
--   • annual_usage_kwh      — estimated annual electricity usage in kWh
--   • onboarding_completed  — flag set once the user finishes onboarding
--
-- NOTE: The `region` column already exists from init_neon.sql (NOT NULL).
--       No change is made to that column.
--
-- All statements use ADD COLUMN IF NOT EXISTS so this migration is safe to re-run.
-- =============================================================================

-- utility_types: stored as a comma-separated string (e.g. 'electricity,natural_gas').
-- Kept as TEXT rather than an array type for simplicity; the application layer
-- splits/joins the value on read and write.
ALTER TABLE users ADD COLUMN IF NOT EXISTS utility_types TEXT;

-- current_supplier_id: optional FK to the suppliers table.
-- ON DELETE SET NULL so deleting a supplier row does not cascade-delete the user.
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_supplier_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'users'
          AND constraint_name = 'fk_users_current_supplier'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT fk_users_current_supplier
            FOREIGN KEY (current_supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL;
        RAISE NOTICE 'FK constraint fk_users_current_supplier added to users';
    ELSE
        RAISE NOTICE 'FK constraint fk_users_current_supplier already exists, skipping';
    END IF;
END $$;

-- annual_usage_kwh: non-negative integer.
ALTER TABLE users ADD COLUMN IF NOT EXISTS annual_usage_kwh INT;

-- onboarding_completed: defaults to FALSE for all existing rows.
ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT FALSE;

-- Index to support queries filtering users who have completed onboarding.
CREATE INDEX IF NOT EXISTS idx_users_onboarding
    ON users (onboarding_completed) WHERE onboarding_completed = TRUE;

-- =============================================================================
-- Grants
-- =============================================================================
DO $$ BEGIN
    GRANT SELECT, UPDATE ON users TO neondb_owner;
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'neondb_owner role not found, skipping grant';
END $$;

-- =============================================================================
-- Migration complete.
-- Verify with:
--   SELECT column_name, data_type
--   FROM information_schema.columns
--   WHERE table_name = 'users'
--   ORDER BY ordinal_position;
-- =============================================================================
