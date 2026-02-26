-- Migration 012: User savings tracking table
-- Date: 2026-02-25
-- Description: Adds a user_savings table to persist per-user savings records
--              generated from supplier switching, usage optimisation, and alert
--              events. Used by SavingsService and the /api/v1/savings endpoints.
--
-- Prerequisites: migration 001 (users table with UUID PK)

-- =============================================================================
-- 1. Create user_savings table
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_savings (
    id           UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID           NOT NULL,
    savings_type VARCHAR(50)    NOT NULL, -- 'switching', 'usage', 'alert'
    amount       DECIMAL(12, 6) NOT NULL,
    currency     VARCHAR(3)     NOT NULL DEFAULT 'USD',
    description  TEXT,
    region       VARCHAR(50),
    period_start TIMESTAMPTZ    NOT NULL,
    period_end   TIMESTAMPTZ    NOT NULL,
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- =============================================================================
-- 2. Indexes
-- =============================================================================

-- Fast lookup by user (list / summary queries)
CREATE INDEX IF NOT EXISTS idx_user_savings_user_id
    ON user_savings (user_id);

-- Time-ordered lookup for streak and window calculations
CREATE INDEX IF NOT EXISTS idx_user_savings_created_at
    ON user_savings (user_id, created_at DESC);
