-- =============================================================================
-- Migration: Notification Error Message Column
-- Version: 032
-- Date: 2026-03-10
-- =============================================================================
--
-- Extends the notifications table with:
--   1. error_message TEXT — human-readable failure diagnostic stored alongside
--      delivery_metadata JSONB for structured provider data.  Keeping a plain
--      TEXT column makes incident queries simpler (no JSONB extraction needed).
--   2. idx_notifications_channel_created — supports analytics queries that
--      filter by delivery_channel and order by created_at (e.g. "all email
--      notifications sent in the last 7 days").
--
-- This migration supplements migration 029 (delivery tracking) which added
-- delivery_channel, delivery_status, delivered_at, delivery_metadata, and
-- retry_count, plus idx_notifications_user_delivery_status.
--
-- =============================================================================


-- =============================================================================
-- ADD error_message COLUMN
-- =============================================================================

ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS error_message TEXT;


-- =============================================================================
-- INDEX: Analytics — filter by channel, order by recency
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_notifications_channel_created
    ON notifications (delivery_channel, created_at DESC);


-- =============================================================================
-- GRANTS
-- =============================================================================

DO $$ BEGIN
    GRANT ALL ON TABLE notifications TO neondb_owner;
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'neondb_owner role not found, skipping grants';
END $$;


-- =============================================================================
-- Migration complete.
-- =============================================================================
