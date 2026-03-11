-- Migration 039: Referrals
-- Date: 2026-03-11
-- Purpose: Referral code system for user growth (Wave 1, Phase 2)
--
-- Double-sided incentive: referrer gets credit, referee gets extended trial.
-- Reward redemption in Wave 3 (Stripe integration).

CREATE TABLE IF NOT EXISTS referrals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id     UUID NOT NULL,
    referee_id      UUID,
    referral_code   VARCHAR(12) NOT NULL UNIQUE,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'completed', 'expired')),
    reward_applied  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

-- Query patterns
CREATE INDEX IF NOT EXISTS idx_referrals_code
    ON referrals (referral_code);

CREATE INDEX IF NOT EXISTS idx_referrals_referrer
    ON referrals (referrer_id);

CREATE INDEX IF NOT EXISTS idx_referrals_referee
    ON referrals (referee_id)
    WHERE referee_id IS NOT NULL;

-- Grant access
GRANT SELECT, INSERT, UPDATE, DELETE ON referrals TO neondb_owner;
