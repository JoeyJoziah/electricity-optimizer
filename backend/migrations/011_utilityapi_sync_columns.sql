-- Migration 010: Add UtilityAPI sync columns to user_connections
-- Required for Phase 4: UtilityAPI Direct Sync
--
-- These columns support the sync service's scheduling, error tracking,
-- and encrypted credential storage for UtilityAPI integrations.

ALTER TABLE user_connections
    ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_sync_error TEXT,
    ADD COLUMN IF NOT EXISTS sync_frequency_hours INT DEFAULT 24,
    ADD COLUMN IF NOT EXISTS utilityapi_auth_uid_encrypted BYTEA;
