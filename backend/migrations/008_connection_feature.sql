-- Migration 008: Connection Feature
-- Date: 2026-02-25
-- Description: Adds support for multi-method utility bill connections — direct account-number
--              entry, email-import (OAuth redirect), and manual file upload. Captures encrypted
--              credentials, parsed bill data, and a normalized rate table for cross-method analytics.
--
-- Prerequisites: migration 006 (supplier_registry), migration 007 (user_supplier_accounts)

-- =============================================================================
-- 1. Create user_connections table
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_connections (
    id                          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Connection method: 'direct', 'email_import', 'manual_upload'
    connection_type             VARCHAR(50)  NOT NULL,

    -- Supplier reference (nullable for email / upload that hasn't been resolved yet)
    supplier_id                 UUID         REFERENCES supplier_registry(id),
    supplier_name               VARCHAR(200),

    -- Status: 'active', 'pending', 'error', 'disconnected'
    status                      VARCHAR(30)  NOT NULL DEFAULT 'pending',

    -- Direct connection fields (account-number entry)
    account_number_encrypted    BYTEA,
    account_number_masked       VARCHAR(30),

    -- Email-import fields
    email_provider              VARCHAR(50),    -- 'gmail' or 'outlook'

    -- Manual upload label
    label                       VARCHAR(100),

    -- Consent tracking
    consent_given               BOOLEAN      NOT NULL DEFAULT FALSE,
    consent_given_at            TIMESTAMPTZ,

    created_at                  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_connections_user
    ON user_connections (user_id);

CREATE INDEX IF NOT EXISTS idx_user_connections_user_status
    ON user_connections (user_id, status);

CREATE INDEX IF NOT EXISTS idx_user_connections_user_supplier
    ON user_connections (user_id, supplier_id)
    WHERE supplier_id IS NOT NULL;

-- =============================================================================
-- 2. Create bill_uploads table (Phase 2: OCR parsing via Google Document AI)
-- =============================================================================

CREATE TABLE IF NOT EXISTS bill_uploads (
    id                              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id                   UUID         NOT NULL REFERENCES user_connections(id) ON DELETE CASCADE,
    user_id                         UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- File metadata
    file_name                       VARCHAR(255) NOT NULL,
    file_type                       VARCHAR(50)  NOT NULL,
    file_size_bytes                 INT          NOT NULL,
    storage_key                     VARCHAR(500) NOT NULL,

    -- Parse lifecycle
    parse_status                    VARCHAR(20)  NOT NULL DEFAULT 'pending',
    parsed_data                     JSONB,
    parse_error                     TEXT,
    parsed_at                       TIMESTAMPTZ,

    -- Denormalized extracted fields for fast access
    detected_supplier               VARCHAR(200),
    detected_rate_per_kwh           DECIMAL(10,6),
    detected_billing_period_start   DATE,
    detected_billing_period_end     DATE,
    detected_total_kwh              DECIMAL(12,2),
    detected_total_amount           DECIMAL(10,2),

    created_at                      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at                      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bill_uploads_connection
    ON bill_uploads (connection_id);

CREATE INDEX IF NOT EXISTS idx_bill_uploads_user
    ON bill_uploads (user_id);

-- =============================================================================
-- 3. Create connection_extracted_rates table
-- =============================================================================

CREATE TABLE IF NOT EXISTS connection_extracted_rates (
    id                  UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id       UUID           NOT NULL REFERENCES user_connections(id) ON DELETE CASCADE,

    -- Rate details
    rate_per_kwh        DECIMAL(10,6)  NOT NULL,
    effective_date      TIMESTAMPTZ    NOT NULL DEFAULT now(),

    -- Provenance
    source              VARCHAR(50)    NOT NULL,   -- 'bill_parse', 'api_pull', 'manual_entry'
    raw_label           VARCHAR(200),              -- Original label from source

    created_at          TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_extracted_rates_connection
    ON connection_extracted_rates (connection_id);

CREATE INDEX IF NOT EXISTS idx_extracted_rates_date
    ON connection_extracted_rates (connection_id, effective_date DESC);

-- =============================================================================
-- 4. Grant permissions
-- =============================================================================

GRANT ALL ON user_connections           TO neondb_owner;
GRANT ALL ON bill_uploads               TO neondb_owner;
GRANT ALL ON connection_extracted_rates TO neondb_owner;
