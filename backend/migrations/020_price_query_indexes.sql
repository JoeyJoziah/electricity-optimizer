-- =============================================================================
-- Migration 020: Price Query Indexes
-- Date: 2026-03-02
-- Purpose: Add composite indexes for the two highest-frequency electricity_prices
--          query patterns and a region lookup index on the users table.
-- =============================================================================
--
-- Background
-- ----------
-- electricity_prices is the most-queried table. Two query shapes dominate:
--
--   1. Supplier comparison for a region (sorted by insertion recency):
--      SELECT ... FROM electricity_prices
--      WHERE region = ? AND supplier = ?
--      ORDER BY created_at DESC
--
--   2. Multi-utility price history for a region (sorted by insertion recency):
--      SELECT ... FROM electricity_prices
--      WHERE region = ? AND utility_type = ?
--      ORDER BY created_at DESC
--
-- Existing indexes (004, 006, 010) cover the same predicates but order by
-- `timestamp DESC` (the price observation time). These new indexes satisfy
-- the `created_at DESC` ordering variant without forcing a filesort.
--
-- The users(region) index supports region-based user lookups (e.g., finding
-- all users in a region to send price alerts or build regional summaries).
-- init_neon.sql created idx_users_region with the same definition; using
-- IF NOT EXISTS makes this migration safe whether or not that baseline index
-- survived schema reconciliation in later migrations.
--
-- All indexes use CONCURRENTLY + IF NOT EXISTS so this migration is safe to
-- re-run on a live database without table locks.
-- =============================================================================


-- Composite index for supplier-comparison queries ordered by insertion time.
-- Supports: SELECT ... FROM electricity_prices
--           WHERE region = ? AND supplier = ? ORDER BY created_at DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prices_region_supplier_created
    ON electricity_prices (region, supplier, created_at DESC);


-- Composite index for multi-utility history queries ordered by insertion time.
-- Supports: SELECT ... FROM electricity_prices
--           WHERE region = ? AND utility_type = ? ORDER BY created_at DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prices_region_utilitytype_created
    ON electricity_prices (region, utility_type, created_at DESC);


-- Index for region-based user lookups.
-- Supports: SELECT ... FROM users WHERE region = ?
-- (guards against the case where init_neon.sql's idx_users_region was dropped
-- or not applied during schema reconciliation)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_region
    ON users (region);


-- =============================================================================
-- GRANTS
-- =============================================================================

DO $$ BEGIN
    -- Indexes are owned by the table owner; no explicit grants needed.
    -- This block is a no-op placeholder so the pattern stays consistent.
    RAISE NOTICE 'Migration 020 complete: 3 indexes created (or already existed).';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'neondb_owner role not found, skipping grants';
END $$;


-- =============================================================================
-- Migration complete.
-- =============================================================================
