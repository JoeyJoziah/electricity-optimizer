-- Migration: GDPR Compliance and Authentication Tables
-- Version: 002
-- Date: 2024-01-15

-- =============================================================================
-- CONSENT RECORDS TABLE
-- Tracks user consent for GDPR Article 6, 7 compliance
-- =============================================================================

CREATE TABLE IF NOT EXISTS consent_records (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    consent_given BOOLEAN NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_address VARCHAR(45) NOT NULL,
    user_agent VARCHAR(500) NOT NULL,
    consent_version VARCHAR(20) DEFAULT '1.0',
    withdrawal_timestamp TIMESTAMPTZ,
    metadata_json JSONB,

    -- Indexes for efficient queries
    CONSTRAINT fk_consent_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_consent_user_id ON consent_records(user_id);
CREATE INDEX IF NOT EXISTS idx_consent_user_purpose ON consent_records(user_id, purpose);
CREATE INDEX IF NOT EXISTS idx_consent_timestamp ON consent_records(timestamp DESC);

-- Consent purposes enum type
DO $$ BEGIN
    CREATE TYPE consent_purpose AS ENUM (
        'data_processing',
        'marketing',
        'analytics',
        'price_alerts',
        'optimization',
        'third_party_sharing'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;


-- =============================================================================
-- DELETION LOGS TABLE
-- Immutable audit log for GDPR Article 17 compliance
-- =============================================================================

CREATE TABLE IF NOT EXISTS deletion_logs (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by VARCHAR(36) NOT NULL,
    deletion_type VARCHAR(20) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    user_agent VARCHAR(500) NOT NULL,
    data_categories_deleted JSONB NOT NULL,
    legal_basis VARCHAR(50) DEFAULT 'user_request',
    metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_deletion_user_id ON deletion_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_deletion_timestamp ON deletion_logs(deleted_at DESC);

-- Make deletion_logs immutable (no updates or deletes)
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
-- AUTH SESSIONS TABLE
-- Track active authentication sessions for token management
-- =============================================================================

CREATE TABLE IF NOT EXISTS auth_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    refresh_token_hash VARCHAR(64),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    ip_address VARCHAR(45) NOT NULL,
    user_agent VARCHAR(500) NOT NULL,
    is_revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMPTZ,

    CONSTRAINT fk_session_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_session_user_id ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_session_token_hash ON auth_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_session_expires ON auth_sessions(expires_at);


-- =============================================================================
-- LOGIN ATTEMPTS TABLE
-- Track failed login attempts for rate limiting and security
-- =============================================================================

CREATE TABLE IF NOT EXISTS login_attempts (
    id VARCHAR(36) PRIMARY KEY,
    identifier VARCHAR(255) NOT NULL,  -- email or IP
    identifier_type VARCHAR(20) NOT NULL,  -- 'email' or 'ip'
    attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    success BOOLEAN NOT NULL DEFAULT FALSE,
    ip_address VARCHAR(45) NOT NULL,
    user_agent VARCHAR(500),
    failure_reason VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_login_identifier ON login_attempts(identifier, identifier_type);
CREATE INDEX IF NOT EXISTS idx_login_attempt_time ON login_attempts(attempt_at DESC);

-- Cleanup old login attempts (keep only last 7 days)
CREATE OR REPLACE FUNCTION cleanup_old_login_attempts()
RETURNS void AS $$
BEGIN
    DELETE FROM login_attempts
    WHERE attempt_at < NOW() - INTERVAL '7 days';
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- ACTIVITY LOGS TABLE
-- Audit trail for user actions
-- =============================================================================

CREATE TABLE IF NOT EXISTS activity_logs (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(36),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    details JSONB,
    correlation_id VARCHAR(36),

    CONSTRAINT fk_activity_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_activity_user_id ON activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_activity_action ON activity_logs(action);

-- Convert to TimescaleDB hypertable for efficient time-series queries
-- (Only if TimescaleDB extension is available)
DO $$ BEGIN
    PERFORM create_hypertable('activity_logs', 'timestamp', if_not_exists => TRUE);
EXCEPTION
    WHEN undefined_function THEN
        RAISE NOTICE 'TimescaleDB not available, skipping hypertable creation';
END $$;


-- =============================================================================
-- UPDATE USERS TABLE
-- Add GDPR and auth fields if not present
-- =============================================================================

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS consent_given BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS consent_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS data_processing_agreed BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS login_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;


-- =============================================================================
-- DATA RETENTION POLICY
-- Automatically purge old data per GDPR Article 5(1)(e)
-- =============================================================================

-- Policy: Keep activity logs for 2 years
DO $$ BEGIN
    PERFORM add_retention_policy('activity_logs', INTERVAL '2 years', if_not_exists => TRUE);
EXCEPTION
    WHEN undefined_function THEN
        RAISE NOTICE 'TimescaleDB not available, skipping retention policy';
END $$;


-- =============================================================================
-- GRANTS
-- =============================================================================

-- Grant permissions to application role
GRANT SELECT, INSERT ON consent_records TO app_user;
GRANT SELECT, INSERT ON deletion_logs TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_sessions TO app_user;
GRANT SELECT, INSERT ON login_attempts TO app_user;
GRANT SELECT, INSERT, UPDATE ON activity_logs TO app_user;
