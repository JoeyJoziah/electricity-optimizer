-- Migration 026: Add metadata JSONB column to notifications table
-- Enables dedup_key storage and arbitrary per-notification context for
-- NotificationDispatcher (strategy-pattern routing layer).
ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS metadata JSONB;

CREATE INDEX IF NOT EXISTS idx_notifications_dedup_key
    ON notifications ((metadata ->> 'dedup_key'), user_id, created_at DESC)
    WHERE metadata IS NOT NULL;

GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO neondb_owner;
