-- =============================================================================
-- Migration: Multi-Utility Alert Support
-- Version: 044
-- Date: 2026-03-11
-- =============================================================================
--
-- Extends price_alert_configs and alert_history with utility_type support.
-- Adds rate_change_alerts table for proactive rate change notifications.
-- Adds alert_preferences table for per-utility notification settings.
-- =============================================================================


-- =============================================================================
-- 1. Add utility_type to price_alert_configs
-- =============================================================================

ALTER TABLE price_alert_configs
    ADD COLUMN IF NOT EXISTS utility_type VARCHAR(30) NOT NULL DEFAULT 'electricity';

ALTER TABLE alert_history
    ADD COLUMN IF NOT EXISTS utility_type VARCHAR(30) NOT NULL DEFAULT 'electricity';

CREATE INDEX IF NOT EXISTS idx_alert_configs_utility_type
    ON price_alert_configs(user_id, utility_type)
    WHERE is_active = TRUE;


-- =============================================================================
-- 2. Rate change alerts table — stores detected rate changes
-- =============================================================================

CREATE TABLE IF NOT EXISTS rate_change_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    utility_type    VARCHAR(30) NOT NULL,
    region          VARCHAR(50) NOT NULL,
    supplier        VARCHAR(200),
    previous_price  NUMERIC(10, 6) NOT NULL,
    current_price   NUMERIC(10, 6) NOT NULL,
    change_pct      NUMERIC(8, 4) NOT NULL,
    change_direction VARCHAR(10) NOT NULL,   -- 'increase' or 'decrease'
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Optional recommendation
    recommendation_supplier  VARCHAR(200),
    recommendation_price     NUMERIC(10, 6),
    recommendation_savings   NUMERIC(10, 6),
    CONSTRAINT chk_change_direction CHECK (change_direction IN ('increase', 'decrease'))
);

CREATE INDEX IF NOT EXISTS idx_rate_change_alerts_lookup
    ON rate_change_alerts(utility_type, region, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_rate_change_alerts_recent
    ON rate_change_alerts(detected_at DESC);


-- =============================================================================
-- 3. Alert preferences — per-utility notification settings
-- =============================================================================

CREATE TABLE IF NOT EXISTS alert_preferences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    utility_type    VARCHAR(30) NOT NULL,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    channels        TEXT[] NOT NULL DEFAULT '{email}',     -- 'email', 'push', 'in_app'
    cadence         VARCHAR(20) NOT NULL DEFAULT 'daily',  -- 'realtime', 'daily', 'weekly'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_alert_pref_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_alert_pref_user_utility
        UNIQUE (user_id, utility_type)
);

CREATE INDEX IF NOT EXISTS idx_alert_preferences_user
    ON alert_preferences(user_id);


-- =============================================================================
-- GRANTS
-- =============================================================================

DO $$ BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON rate_change_alerts TO neondb_owner;
    GRANT SELECT, INSERT, UPDATE, DELETE ON alert_preferences TO neondb_owner;
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'neondb_owner role not found, skipping grants';
END $$;
