-- =============================================================================
-- Electricity Optimizer - PostgreSQL Init Script for Neon.tech
-- =============================================================================
--
-- Target:  Neon.tech (standard PostgreSQL 16+)
-- NOTE:    This script uses ONLY standard PostgreSQL features.
--          NO TimescaleDB or other non-default extensions are required.
--
-- Tables:
--   1. users
--   2. electricity_prices
--   3. suppliers
--   4. tariffs
--   5. consent_records
--   6. deletion_logs
--   7. beta_signups
--
-- Run once to initialize the database schema.
-- All statements use CREATE TABLE IF NOT EXISTS for safe re-runs.
-- =============================================================================

-- gen_random_uuid() is available natively in PostgreSQL 13+, which Neon
-- supports. Enable pgcrypto as a fallback guarantee.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 1. users
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email             VARCHAR(255) NOT NULL UNIQUE,
    name              VARCHAR(200) NOT NULL,
    region            VARCHAR(50)  NOT NULL,
    preferences       JSONB        NOT NULL DEFAULT '{}',
    current_supplier  VARCHAR(200),
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    is_verified       BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- email is already indexed via the UNIQUE constraint
CREATE INDEX IF NOT EXISTS idx_users_region     ON users (region);
CREATE INDEX IF NOT EXISTS idx_users_is_active  ON users (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at DESC);

-- =============================================================================
-- 2. electricity_prices
-- =============================================================================
CREATE TABLE IF NOT EXISTS electricity_prices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region          VARCHAR(50)    NOT NULL,
    supplier        VARCHAR(200)   NOT NULL,
    price_per_kwh   DECIMAL(12, 6) NOT NULL CHECK (price_per_kwh >= 0),
    currency        CHAR(3)        NOT NULL,
    timestamp       TIMESTAMPTZ    NOT NULL,
    is_peak         BOOLEAN,
    source_api      VARCHAR(200),
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- Primary query pattern: prices by region within a time range
CREATE INDEX IF NOT EXISTS idx_prices_region_timestamp
    ON electricity_prices (region, timestamp DESC);

-- Supplier-specific price lookups
CREATE INDEX IF NOT EXISTS idx_prices_supplier
    ON electricity_prices (supplier);

-- Recent prices across all regions
CREATE INDEX IF NOT EXISTS idx_prices_timestamp
    ON electricity_prices (timestamp DESC);

-- Peak/off-peak filtering within a region
CREATE INDEX IF NOT EXISTS idx_prices_region_is_peak
    ON electricity_prices (region, is_peak)
    WHERE is_peak IS NOT NULL;

-- =============================================================================
-- 3. suppliers
-- =============================================================================
CREATE TABLE IF NOT EXISTS suppliers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL UNIQUE,
    regions     TEXT[]       NOT NULL DEFAULT '{}',
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    website     VARCHAR(500),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_suppliers_is_active ON suppliers (is_active)
    WHERE is_active = TRUE;

-- GIN index for efficient array-contains queries (e.g. WHERE 'uk' = ANY(regions))
CREATE INDEX IF NOT EXISTS idx_suppliers_regions ON suppliers USING GIN (regions);

-- =============================================================================
-- 4. tariffs
-- =============================================================================
CREATE TABLE IF NOT EXISTS tariffs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id     UUID           NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    name            VARCHAR(200)   NOT NULL,
    price_per_kwh   DECIMAL(12, 6) NOT NULL CHECK (price_per_kwh >= 0),
    standing_charge DECIMAL(12, 6) NOT NULL CHECK (standing_charge >= 0),
    is_available    BOOLEAN        NOT NULL DEFAULT TRUE,
    tariff_type     VARCHAR(50)    NOT NULL DEFAULT 'variable',
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- FK index for join performance
CREATE INDEX IF NOT EXISTS idx_tariffs_supplier_id ON tariffs (supplier_id);

-- Filter by tariff type
CREATE INDEX IF NOT EXISTS idx_tariffs_tariff_type ON tariffs (tariff_type);

-- Common query: available tariffs for a given supplier
CREATE INDEX IF NOT EXISTS idx_tariffs_supplier_available
    ON tariffs (supplier_id, is_available)
    WHERE is_available = TRUE;

-- =============================================================================
-- 5. consent_records
-- =============================================================================
CREATE TABLE IF NOT EXISTS consent_records (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID         NOT NULL,
    purpose                 VARCHAR(100) NOT NULL,
    consent_given           BOOLEAN      NOT NULL,
    timestamp               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ip_address              VARCHAR(45)  NOT NULL,
    user_agent              TEXT         NOT NULL,
    consent_version         VARCHAR(20)  DEFAULT '1.0',
    withdrawal_timestamp    TIMESTAMPTZ,
    metadata                JSONB
);

-- All consent records for a user (chronological audit trail)
CREATE INDEX IF NOT EXISTS idx_consent_user_id ON consent_records (user_id);
CREATE INDEX IF NOT EXISTS idx_consent_user_timestamp
    ON consent_records (user_id, timestamp DESC);

-- Audit by purpose (e.g. all marketing consents)
CREATE INDEX IF NOT EXISTS idx_consent_purpose ON consent_records (purpose);

-- =============================================================================
-- 6. deletion_logs
-- =============================================================================
CREATE TABLE IF NOT EXISTS deletion_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID         NOT NULL,
    deleted_by          VARCHAR(100) NOT NULL,
    deleted_categories  TEXT[]       NOT NULL DEFAULT '{}',
    ip_address          VARCHAR(45)  NOT NULL,
    user_agent          TEXT         NOT NULL,
    timestamp           TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_deletion_logs_user_id   ON deletion_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_deletion_logs_timestamp ON deletion_logs (timestamp DESC);

-- Deletion logs are an immutable GDPR audit trail. Prevent updates and deletes.
CREATE OR REPLACE FUNCTION prevent_deletion_log_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Deletion logs are immutable and cannot be modified or deleted';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_prevent_deletion_log_update ON deletion_logs;
CREATE TRIGGER tr_prevent_deletion_log_update
    BEFORE UPDATE OR DELETE ON deletion_logs
    FOR EACH ROW
    EXECUTE FUNCTION prevent_deletion_log_modification();

-- =============================================================================
-- 7. beta_signups
-- =============================================================================
CREATE TABLE IF NOT EXISTS beta_signups (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       VARCHAR(255) NOT NULL UNIQUE,
    name        VARCHAR(200),
    interest    TEXT,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- email is already indexed via the UNIQUE constraint
CREATE INDEX IF NOT EXISTS idx_beta_signups_created_at ON beta_signups (created_at DESC);

-- =============================================================================
-- Auto-update trigger: set updated_at on row modification
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to the users table
DROP TRIGGER IF EXISTS trigger_users_updated_at ON users;
CREATE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- Schema initialization complete.
-- =============================================================================
