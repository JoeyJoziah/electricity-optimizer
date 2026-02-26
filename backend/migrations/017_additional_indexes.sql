-- =============================================================================
-- Migration 017: Additional Performance Indexes
-- Date: 2026-02-25
-- =============================================================================
--
-- Adds compound indexes for the most common query patterns on connection,
-- bill upload, forecast observation, and notifications tables.
--
-- All indexes use CONCURRENTLY + IF NOT EXISTS so this migration is safe to
-- re-run on a live database without locking tables.
--
-- The notifications table (created in migration 015) already has two indexes:
--   idx_notifications_user_unread  (user_id, read_at) WHERE read_at IS NULL
--   idx_notifications_user_created (user_id, created_at DESC)
-- This migration adds the combined partial+ordering index that efficiently
-- serves: SELECT ... WHERE user_id = ? AND read_at IS NULL ORDER BY created_at DESC
-- =============================================================================


-- Compound index for connection lookups by user + method
-- Supports: SELECT ... FROM user_connections WHERE user_id = ? AND connection_method = ?
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_connections_user_method
    ON user_connections (user_id, connection_method);


-- Covering index for bill upload queries ordered by recency and filtered by status
-- Supports: SELECT ... FROM bill_uploads WHERE user_id = ? ORDER BY created_at DESC
--       and: SELECT ... FROM bill_uploads WHERE user_id = ? AND status = ? ...
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bill_uploads_user_status
    ON bill_uploads (user_id, created_at DESC, status);


-- Compound index for time-series forecast lookups by region and utility type
-- Supports: SELECT ... FROM forecast_observations
--           WHERE region = ? AND utility_type = ? ORDER BY created_at DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_forecast_observations_region
    ON forecast_observations (region, utility_type, created_at DESC);


-- Partial index on notifications for fast unread-by-user queries sorted by recency
-- Combines the partial filter (read_at IS NULL) with the ordering column so
-- Postgres can satisfy the WHERE + ORDER BY in a single index scan.
-- Supports: SELECT ... FROM notifications
--           WHERE user_id = ? AND read_at IS NULL ORDER BY created_at DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_user_unread_created
    ON notifications (user_id, created_at DESC)
    WHERE read_at IS NULL;


-- =============================================================================
-- GRANTS
-- =============================================================================

DO $$ BEGIN
    -- Indexes are owned by the table owner; no explicit grants needed.
    -- This block is a no-op placeholder so the pattern stays consistent.
    RAISE NOTICE 'Migration 017 complete: 4 indexes created.';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'neondb_owner role not found, skipping grants';
END $$;


-- =============================================================================
-- Migration complete.
-- =============================================================================
