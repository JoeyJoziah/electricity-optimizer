-- 068_drip_unsubscribe.sql
-- CAN-SPAM compliance: add unsubscribe support to the drip state machine.
-- Users who click the unsubscribe link get unsubscribed_at stamped here;
-- batch processors exclude them via WHERE unsubscribed_at IS NULL.

ALTER TABLE user_drip_state
    ADD COLUMN IF NOT EXISTS unsubscribed_at TIMESTAMPTZ;

-- Partial index so batch queries skip unsubscribed users at index level.
CREATE INDEX IF NOT EXISTS idx_drip_active
    ON user_drip_state (enrolled_at)
    WHERE unsubscribed_at IS NULL;
