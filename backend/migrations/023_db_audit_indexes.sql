-- Migration 023: Database Audit Fixes
-- Covers: missing indexes, meter_number columns, consent FK fix, retention functions
-- Risk: LOW (all DDL is idempotent or guarded)

-- =============================================================================
-- SECTION 1: Missing Indexes
-- =============================================================================

-- 1a. Index for sync_all_due() in connection_sync_service.py
--     Covers: status='active', utilityapi_auth_uid_encrypted IS NOT NULL, ORDER BY last_sync_at
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_connections_sync_due
    ON user_connections (status, last_sync_at NULLS FIRST)
    WHERE utilityapi_auth_uid_encrypted IS NOT NULL;

-- 1b. Index for check_thresholds() loading configs by region
--     Existing index is (user_id) only; region-based lookups have no coverage
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alert_configs_region_active
    ON price_alert_configs (region)
    WHERE alert_enabled = TRUE;

-- =============================================================================
-- SECTION 2: meter_number columns on user_connections
-- =============================================================================

ALTER TABLE user_connections
    ADD COLUMN IF NOT EXISTS meter_number_encrypted BYTEA,
    ADD COLUMN IF NOT EXISTS meter_number_masked VARCHAR(30);

-- =============================================================================
-- SECTION 3: consent_records FK fix (CASCADE → SET NULL)
-- =============================================================================
-- Problem: ON DELETE CASCADE destroys consent audit trail when user is erased.
-- Fix: Make user_id nullable, change to ON DELETE SET NULL.

-- 3a. Make user_id nullable
ALTER TABLE consent_records
    ALTER COLUMN user_id DROP NOT NULL;

-- 3b. Replace the FK constraint
DO $$
BEGIN
    -- Drop the existing CASCADE constraint (may be named fk_consent_user or auto-generated)
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'consent_records'
          AND constraint_name = 'fk_consent_user'
          AND constraint_type = 'FOREIGN KEY'
    ) THEN
        ALTER TABLE consent_records DROP CONSTRAINT fk_consent_user;
    END IF;

    -- Add the SET NULL constraint
    ALTER TABLE consent_records
        ADD CONSTRAINT fk_consent_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;

    RAISE NOTICE 'consent_records FK changed from CASCADE to SET NULL';
END $$;

-- =============================================================================
-- SECTION 4: Data Retention Functions
-- =============================================================================

-- 4a. Clean up old electricity prices
CREATE OR REPLACE FUNCTION cleanup_old_prices(retention_days INTEGER DEFAULT 365)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM electricity_prices
    WHERE timestamp < NOW() - (retention_days || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    RAISE NOTICE 'cleanup_old_prices: deleted % rows older than % days',
        deleted_count, retention_days;

    RETURN deleted_count;
END;
$$;

-- 4b. Clean up old forecast observations
CREATE OR REPLACE FUNCTION cleanup_old_observations(retention_days INTEGER DEFAULT 90)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM forecast_observations
    WHERE observed_at < NOW() - (retention_days || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    RAISE NOTICE 'cleanup_old_observations: deleted % rows older than % days',
        deleted_count, retention_days;

    RETURN deleted_count;
END;
$$;

-- =============================================================================
-- GRANTs
-- =============================================================================
DO $$
BEGIN
    GRANT EXECUTE ON FUNCTION cleanup_old_prices(INTEGER) TO neondb_owner;
    GRANT EXECUTE ON FUNCTION cleanup_old_observations(INTEGER) TO neondb_owner;
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'Role neondb_owner does not exist, skipping GRANTs';
END $$;
