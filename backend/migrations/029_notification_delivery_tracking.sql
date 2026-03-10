-- =============================================================================
-- Migration: Notification Delivery Tracking
-- Version: 029
-- Date: 2026-03-10
-- =============================================================================
--
-- Extends the notifications table with multi-channel delivery tracking columns.
-- These columns allow the NotificationDispatcher service to record which channel
-- delivered each notification, its current delivery status, when delivery was
-- confirmed, provider-specific metadata, and how many attempts were made.
--
-- New columns:
--   delivery_channel  — which channel delivered this (email, push, in_app)
--   delivery_status   — pending, sent, delivered, failed, bounced
--   delivered_at      — timestamp when delivery was confirmed
--   delivery_metadata — provider-specific data (message_id, bounce reason, etc.)
--   retry_count       — number of delivery attempts made
--
-- Index:
--   idx_notifications_user_delivery_status — supports efficient querying
--   by (user_id, delivery_status) for dashboard views and retry logic.
--
-- =============================================================================


-- =============================================================================
-- ADD DELIVERY TRACKING COLUMNS
-- =============================================================================

ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS delivery_channel   VARCHAR(20),
    ADD COLUMN IF NOT EXISTS delivery_status    VARCHAR(20) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS delivered_at       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS delivery_metadata  JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS retry_count        INTEGER NOT NULL DEFAULT 0;


-- =============================================================================
-- INDEX: Efficient querying by user + delivery status
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_notifications_user_delivery_status
    ON notifications (user_id, delivery_status);


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
