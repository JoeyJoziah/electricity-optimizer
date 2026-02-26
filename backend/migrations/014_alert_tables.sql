-- =============================================================================
-- Migration: Alert Tables
-- Version: 014
-- Date: 2026-02-25
-- =============================================================================
--
-- Creates persistent storage for user-defined price alert configurations
-- (price_alert_configs) and a history log of every alert that fired
-- (alert_history).
--
-- The existing AlertService is in-memory only.  These tables back the new
-- CRUD API endpoints in api/v1/alerts.py and are referenced by the updated
-- AlertService DB methods (get_user_alerts, get_alert_history, etc.).
--
-- Alert config columns mirror AlertThreshold fields so the service layer can
-- round-trip cleanly between the DB and the in-memory class.
-- =============================================================================


-- =============================================================================
-- TABLE: price_alert_configs
-- One row per user-defined price alert rule.
-- =============================================================================

CREATE TABLE IF NOT EXISTS price_alert_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL,
    region          VARCHAR(50) NOT NULL DEFAULT 'us_ct',
    currency        VARCHAR(10) NOT NULL DEFAULT 'USD',
    -- At least one of price_below / price_above must be set; enforced at app level
    price_below     NUMERIC(10, 6),          -- alert when price drops to/below this
    price_above     NUMERIC(10, 6),          -- alert when price rises to/above this
    notify_optimal_windows BOOLEAN NOT NULL DEFAULT TRUE,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_alert_config_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_alert_configs_user_id
    ON price_alert_configs(user_id);

CREATE INDEX IF NOT EXISTS idx_alert_configs_active
    ON price_alert_configs(user_id, is_active)
    WHERE is_active = TRUE;


-- =============================================================================
-- TABLE: alert_history
-- Immutable log of every triggered alert event.
-- =============================================================================

CREATE TABLE IF NOT EXISTS alert_history (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL,
    alert_config_id UUID,                    -- NULL when config was deleted
    alert_type      VARCHAR(30) NOT NULL,    -- 'price_drop', 'price_spike', 'optimal_window'
    current_price   NUMERIC(10, 6) NOT NULL,
    threshold       NUMERIC(10, 6),
    region          VARCHAR(50) NOT NULL,
    supplier        VARCHAR(200),
    currency        VARCHAR(10) NOT NULL DEFAULT 'USD',
    -- Optimal window fields (NULL for price_drop / price_spike)
    optimal_window_start TIMESTAMPTZ,
    optimal_window_end   TIMESTAMPTZ,
    estimated_savings    NUMERIC(10, 6),
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    email_sent      BOOLEAN     NOT NULL DEFAULT FALSE,

    CONSTRAINT fk_alert_history_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_alert_history_config
        FOREIGN KEY (alert_config_id) REFERENCES price_alert_configs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_alert_history_user_id
    ON alert_history(user_id);

CREATE INDEX IF NOT EXISTS idx_alert_history_triggered_at
    ON alert_history(user_id, triggered_at DESC);


-- =============================================================================
-- GRANTS
-- =============================================================================

DO $$ BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON price_alert_configs TO neondb_owner;
    GRANT SELECT, INSERT ON alert_history TO neondb_owner;
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'neondb_owner role not found, skipping grants';
END $$;


-- =============================================================================
-- Migration complete.
-- =============================================================================
