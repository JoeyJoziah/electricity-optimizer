-- 067_user_drip_state.sql
-- Drip email state machine: per-user progress for the 3-email onboarding sequence.
-- Enrolled on signup; Day-2 and Day-7 batches processed by drip-processor GHA cron.

CREATE TABLE IF NOT EXISTS user_drip_state (
    user_id          UUID        PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    enrolled_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    welcome_sent_at  TIMESTAMPTZ,
    day2_sent_at     TIMESTAMPTZ,
    day2_template    VARCHAR(20),   -- 'connected' | 'pending'
    day7_sent_at     TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Partial indexes optimise the two daily batch queries without scanning the full table.
CREATE INDEX IF NOT EXISTS idx_drip_day2_pending
    ON user_drip_state (enrolled_at)
    WHERE day2_sent_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_drip_day7_pending
    ON user_drip_state (enrolled_at)
    WHERE day7_sent_at IS NULL;

-- Auto-update updated_at on every row change.
CREATE OR REPLACE FUNCTION drip_state_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_drip_state_updated_at ON user_drip_state;
CREATE TRIGGER trg_drip_state_updated_at
    BEFORE UPDATE ON user_drip_state
    FOR EACH ROW EXECUTE FUNCTION drip_state_updated_at();
