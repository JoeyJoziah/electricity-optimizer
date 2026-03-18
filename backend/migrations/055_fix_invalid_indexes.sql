-- =============================================================================
-- Migration 055: Fix invalid indexes referencing non-existent columns
-- =============================================================================
--
-- Problem: Migration 017 created two indexes that reference columns which do
-- not exist on their respective tables, causing them to be invalid/unusable:
--
--   1. idx_bill_uploads_user_status
--      Created on (user_id, created_at DESC, status) but the bill_uploads table
--      has no 'status' column — the correct column is 'parse_status'.
--      Source: migration 017 comment incorrectly references "status" while the
--      DDL in migration 008 defines the column as "parse_status".
--
--   2. idx_forecast_observations_region
--      Created on (region, utility_type, created_at DESC) but the
--      forecast_observations table (created in migration 005) has no
--      'utility_type' column. The utility_type column exists only on
--      electricity_prices and other tables, not on forecast_observations.
--
-- Fix: Drop both invalid indexes and recreate them against the correct columns.
--
-- Safe to re-run:
--   - DROP INDEX IF EXISTS guards against the index already being absent.
--   - CREATE INDEX CONCURRENTLY IF NOT EXISTS guards against duplicate creation.
--
-- Note: CONCURRENTLY cannot run inside an explicit transaction block.
-- Neon's pooled endpoint supports DDL outside transactions for index builds.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. Fix idx_bill_uploads_user_status
--    Old: (user_id, created_at DESC, status)     ← 'status' does not exist
--    New: (user_id, created_at DESC, parse_status) ← correct column name
-- ---------------------------------------------------------------------------

DROP INDEX IF EXISTS idx_bill_uploads_user_status;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bill_uploads_user_status
    ON bill_uploads (user_id, created_at DESC, parse_status);


-- ---------------------------------------------------------------------------
-- 2. Fix idx_forecast_observations_region
--    Old: (region, utility_type, created_at DESC) ← 'utility_type' does not exist
--    New: (region, created_at DESC)               ← column omitted, correct columns only
-- ---------------------------------------------------------------------------

DROP INDEX IF EXISTS idx_forecast_observations_region;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_forecast_observations_region
    ON forecast_observations (region, created_at DESC);


-- ---------------------------------------------------------------------------
-- 3. Completion notice
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    RAISE NOTICE 'Migration 055 complete: 2 invalid indexes dropped and recreated with correct columns.';
END $$;
