-- =============================================================================
-- Migration 053: Notification deduplication partial unique index
-- =============================================================================
--
-- Problem: the existing dedup_key mechanism in NotificationDispatcher prevents
-- duplicate notifications within a rolling cooldown window stored in metadata
-- JSONB.  However, there is no database-level constraint preventing two rows
-- from being inserted for the same (user, alert, type) combination on the same
-- calendar day — e.g. if two CF Worker cron runs fire within seconds of each
-- other before the in-memory cooldown is hydrated.
--
-- Fix: add an optional ``alert_id`` FK column that links a notification row
-- back to its originating ``price_alert_configs`` row, then enforce a partial
-- unique index over (user_id, alert_id, type, DATE(created_at)) restricted to
-- non-dismissed notifications.  Dismissed notifications are excluded from the
-- uniqueness constraint so that a user can dismiss a notification and receive a
-- fresh one for the same alert later that day.
--
-- The column is nullable:
--   - Notifications not triggered by a price alert config (e.g. system info
--     messages) leave alert_id NULL and are unaffected by the constraint.
--   - The partial unique index is only evaluated when alert_id IS NOT NULL.
--
-- Index strategy:
--   idx_notifications_dedup_alert — enforces uniqueness per
--       (user_id, alert_id, type, day) WHERE alert_id IS NOT NULL
--                                      AND delivery_status != 'dismissed'
--
-- This complement to idx_notifications_dedup_key (metadata-based, migration
-- 026) adds a hard uniqueness guarantee at the storage layer.
--
-- Safe to re-run: ADD COLUMN IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. Add alert_id column to notifications
-- ---------------------------------------------------------------------------

ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS alert_id UUID;

-- Soft FK reference: alerts can be deleted (config rows cascade away on user
-- delete).  We use SET NULL so that deleting an alert config does not cascade-
-- delete the notification history — the user still saw those notifications.
ALTER TABLE notifications
    DROP CONSTRAINT IF EXISTS notifications_alert_id_fkey;
ALTER TABLE notifications
    ADD CONSTRAINT notifications_alert_id_fkey
    FOREIGN KEY (alert_id) REFERENCES price_alert_configs(id) ON DELETE SET NULL;


-- ---------------------------------------------------------------------------
-- 2. Partial unique index — one active notification per (user, alert, type, day)
-- ---------------------------------------------------------------------------
--
-- Partial condition logic:
--   alert_id IS NOT NULL       — only constrain alert-linked rows
--   delivery_status != 'dismissed' — allow re-notification after dismissal
--
-- Using DATE(created_at) keeps the constraint within a single calendar day
-- (server timezone UTC).  If a user dismisses the notification they can
-- receive a new one the same day for a re-triggered alert.

CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_dedup_alert
    ON notifications (user_id, alert_id, type, DATE(created_at))
    WHERE alert_id IS NOT NULL
      AND delivery_status != 'dismissed';


-- ---------------------------------------------------------------------------
-- 3. Supporting lookup index — find all notifications for an alert config
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_notifications_alert_id
    ON notifications (alert_id)
    WHERE alert_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- 4. Grants
-- ---------------------------------------------------------------------------

GRANT ALL ON notifications TO neondb_owner;
