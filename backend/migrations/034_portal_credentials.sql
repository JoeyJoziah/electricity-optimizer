-- =============================================================================
-- Migration: Portal Credential Scraping
-- Version: 034
-- Date: 2026-03-10
-- =============================================================================
--
-- Extends user_connections with columns needed for credential-based utility
-- portal scraping (Phase 3 of Utility Account Integration).
--
-- New columns on user_connections:
--   portal_username             — plaintext username for portal login
--   portal_password_encrypted   — AES-256-GCM encrypted password (BYTEA)
--   portal_login_url            — override login URL (optional; falls back to
--                                 known utility defaults in PortalScraperService)
--   portal_scrape_status        — lifecycle: pending | in_progress | success | failed
--   portal_last_scraped_at      — timestamp of the most recent completed scrape
--
-- =============================================================================


-- =============================================================================
-- ADD PORTAL SCRAPE COLUMNS
-- =============================================================================

ALTER TABLE user_connections
    ADD COLUMN IF NOT EXISTS portal_username           VARCHAR(255),
    ADD COLUMN IF NOT EXISTS portal_password_encrypted BYTEA,
    ADD COLUMN IF NOT EXISTS portal_login_url          VARCHAR(1000),
    ADD COLUMN IF NOT EXISTS portal_scrape_status      VARCHAR(50) DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS portal_last_scraped_at    TIMESTAMPTZ;


-- =============================================================================
-- INDEX: Efficient lookup of active portal connections due for scraping
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_user_connections_portal_scrape_status
    ON user_connections (portal_scrape_status)
    WHERE connection_type = 'portal_scrape';


-- =============================================================================
-- GRANTS
-- =============================================================================

DO $$ BEGIN
    GRANT ALL ON TABLE user_connections TO neondb_owner;
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'neondb_owner role not found, skipping grants';
END $$;


-- =============================================================================
-- Migration complete.
-- =============================================================================
