-- Migration 066: Auto Rate Switcher tables
-- 6 new tables for autonomous electricity plan switching agent.
-- user_plans, available_plans, meter_readings (partitioned by month),
-- switch_audit_log, switch_executions, user_agent_settings.

-- 1. user_plans — tracks user's current and historical electricity plans
CREATE TABLE IF NOT EXISTS user_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_name VARCHAR NOT NULL,
    provider_name VARCHAR NOT NULL,
    rate_kwh DECIMAL(10,6),
    fixed_charge DECIMAL(10,2),
    term_months INTEGER,
    etf_amount DECIMAL(10,2) DEFAULT 0,
    contract_start TIMESTAMP WITH TIME ZONE,
    contract_end TIMESTAMP WITH TIME ZONE,
    status VARCHAR NOT NULL DEFAULT 'active',
    source VARCHAR NOT NULL,
    raw_plan_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_plans_user
    ON user_plans(user_id, status, created_at DESC);

GRANT ALL ON user_plans TO neondb_owner;

-- 2. available_plans — cached marketplace plans per zip/utility
CREATE TABLE IF NOT EXISTS available_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zip_code VARCHAR(10) NOT NULL,
    utility_code VARCHAR(50),
    region VARCHAR(50) NOT NULL,
    plan_name VARCHAR NOT NULL,
    provider_name VARCHAR NOT NULL,
    rate_kwh DECIMAL(10,6) NOT NULL,
    fixed_charge DECIMAL(10,2) DEFAULT 0,
    term_months INTEGER,
    etf_amount DECIMAL(10,2) DEFAULT 0,
    renewable_pct INTEGER DEFAULT 0,
    plan_url VARCHAR,
    energybot_id VARCHAR,
    raw_plan_data JSONB,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    expires_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_available_plans_zip
    ON available_plans(zip_code, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_available_plans_region
    ON available_plans(region);

GRANT ALL ON available_plans TO neondb_owner;

-- 3. meter_readings — interval usage data (partitioned by month, 90-day retention)
CREATE TABLE IF NOT EXISTS meter_readings (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    connection_id UUID,
    reading_time TIMESTAMP WITH TIME ZONE NOT NULL,
    kwh DECIMAL(10,4) NOT NULL,
    interval_minutes INTEGER NOT NULL DEFAULT 60,
    source VARCHAR NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    PRIMARY KEY (id, reading_time)
) PARTITION BY RANGE (reading_time);

CREATE INDEX IF NOT EXISTS idx_meter_readings_user
    ON meter_readings(user_id, reading_time DESC);

GRANT ALL ON meter_readings TO neondb_owner;

-- Create initial monthly partitions (current + next 3 months)
CREATE TABLE IF NOT EXISTS meter_readings_2026_04 PARTITION OF meter_readings
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE IF NOT EXISTS meter_readings_2026_05 PARTITION OF meter_readings
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE IF NOT EXISTS meter_readings_2026_06 PARTITION OF meter_readings
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE TABLE IF NOT EXISTS meter_readings_2026_07 PARTITION OF meter_readings
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

GRANT ALL ON meter_readings_2026_04 TO neondb_owner;
GRANT ALL ON meter_readings_2026_05 TO neondb_owner;
GRANT ALL ON meter_readings_2026_06 TO neondb_owner;
GRANT ALL ON meter_readings_2026_07 TO neondb_owner;

-- 4. switch_audit_log — every decision engine run (including holds)
CREATE TABLE IF NOT EXISTS switch_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trigger_type VARCHAR NOT NULL,
    decision VARCHAR NOT NULL,
    reason TEXT NOT NULL,
    current_plan_id UUID REFERENCES user_plans(id),
    proposed_plan_id UUID REFERENCES available_plans(id),
    savings_monthly DECIMAL(10,2),
    savings_annual DECIMAL(10,2),
    etf_cost DECIMAL(10,2) DEFAULT 0,
    net_savings_year1 DECIMAL(10,2),
    confidence_score DECIMAL(3,2),
    data_source VARCHAR,
    tier VARCHAR NOT NULL,
    executed BOOLEAN DEFAULT FALSE,
    enrollment_id VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_switch_audit_user
    ON switch_audit_log(user_id, created_at DESC);

GRANT ALL ON switch_audit_log TO neondb_owner;

-- 5. switch_executions — tracks enrollment lifecycle state machine
CREATE TABLE IF NOT EXISTS switch_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    audit_log_id UUID NOT NULL REFERENCES switch_audit_log(id),
    old_plan_id UUID REFERENCES user_plans(id),
    new_plan_id UUID REFERENCES user_plans(id),
    idempotency_key UUID NOT NULL UNIQUE,
    enrollment_id VARCHAR,
    executor_type VARCHAR NOT NULL DEFAULT 'energybot',
    status VARCHAR NOT NULL DEFAULT 'initiating',
    initiated_at TIMESTAMP WITH TIME ZONE,
    confirmed_at TIMESTAMP WITH TIME ZONE,
    enacted_at TIMESTAMP WITH TIME ZONE,
    rescission_ends TIMESTAMP WITH TIME ZONE,
    cooldown_ends TIMESTAMP WITH TIME ZONE,
    failure_reason TEXT,
    rolled_back_from UUID REFERENCES switch_executions(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_switch_exec_user
    ON switch_executions(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_switch_exec_status
    ON switch_executions(status)
    WHERE status IN ('initiating', 'initiated', 'submitted', 'accepted');

GRANT ALL ON switch_executions TO neondb_owner;

-- 6. user_agent_settings — per-user auto-switcher configuration
CREATE TABLE IF NOT EXISTS user_agent_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    enabled BOOLEAN DEFAULT FALSE,
    savings_threshold_pct DECIMAL(5,2) DEFAULT 10.0,
    savings_threshold_min DECIMAL(10,2) DEFAULT 10.0,
    cooldown_days INTEGER DEFAULT 5,
    paused_until TIMESTAMP WITH TIME ZONE,
    loa_signed_at TIMESTAMP WITH TIME ZONE,
    loa_document_s3_key VARCHAR,
    loa_revoked_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

GRANT ALL ON user_agent_settings TO neondb_owner;
