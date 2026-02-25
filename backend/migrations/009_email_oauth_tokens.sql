-- Migration 009: Add OAuth token storage to user_connections
-- Required for Phase 3: Email OAuth Import

ALTER TABLE user_connections
    ADD COLUMN IF NOT EXISTS oauth_access_token TEXT,
    ADD COLUMN IF NOT EXISTS oauth_refresh_token TEXT,
    ADD COLUMN IF NOT EXISTS oauth_token_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_scan_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS scan_results_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
