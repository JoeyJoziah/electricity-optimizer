-- Migration 052: GDPR FK cascade round 2
-- Adds missing ON DELETE CASCADE foreign keys for GDPR Article 17 compliance.
-- Tables: user_savings, recommendation_outcomes, model_predictions,
-- model_ab_assignments, referrals. Also fixes model_config NOT NULL constraints
-- and makes 051's notifications FK idempotent.

-- Fix 051 non-idempotent notifications FK (make safe to re-run)
ALTER TABLE notifications
    DROP CONSTRAINT IF EXISTS notifications_user_id_fkey;
ALTER TABLE notifications
    ADD CONSTRAINT notifications_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- user_savings: add FK with CASCADE
ALTER TABLE user_savings
    DROP CONSTRAINT IF EXISTS user_savings_user_id_fkey;
ALTER TABLE user_savings
    ADD CONSTRAINT user_savings_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- recommendation_outcomes: add FK with CASCADE
ALTER TABLE recommendation_outcomes
    DROP CONSTRAINT IF EXISTS recommendation_outcomes_user_id_fkey;
ALTER TABLE recommendation_outcomes
    ADD CONSTRAINT recommendation_outcomes_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- model_predictions: add FK with CASCADE
ALTER TABLE model_predictions
    DROP CONSTRAINT IF EXISTS model_predictions_user_id_fkey;
ALTER TABLE model_predictions
    ADD CONSTRAINT model_predictions_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- model_ab_assignments: add FK with CASCADE
ALTER TABLE model_ab_assignments
    DROP CONSTRAINT IF EXISTS model_ab_assignments_user_id_fkey;
ALTER TABLE model_ab_assignments
    ADD CONSTRAINT model_ab_assignments_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- referrals: referrer CASCADE, referee SET NULL (keep referral record even if referee deletes)
ALTER TABLE referrals
    DROP CONSTRAINT IF EXISTS referrals_referrer_id_fkey;
ALTER TABLE referrals
    ADD CONSTRAINT referrals_referrer_id_fkey
    FOREIGN KEY (referrer_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE referrals
    DROP CONSTRAINT IF EXISTS referrals_referee_id_fkey;
ALTER TABLE referrals
    ADD CONSTRAINT referrals_referee_id_fkey
    FOREIGN KEY (referee_id) REFERENCES users(id) ON DELETE SET NULL;

-- model_config: add NOT NULL constraints with safe defaults
ALTER TABLE model_config
    ALTER COLUMN is_active SET DEFAULT true;
UPDATE model_config SET is_active = true WHERE is_active IS NULL;
ALTER TABLE model_config
    ALTER COLUMN is_active SET NOT NULL;

ALTER TABLE model_config
    ALTER COLUMN created_at SET DEFAULT NOW();
UPDATE model_config SET created_at = NOW() WHERE created_at IS NULL;
ALTER TABLE model_config
    ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE model_config
    ALTER COLUMN updated_at SET DEFAULT NOW();
UPDATE model_config SET updated_at = NOW() WHERE updated_at IS NULL;
ALTER TABLE model_config
    ALTER COLUMN updated_at SET NOT NULL;

-- Grants
GRANT ALL ON user_savings TO neondb_owner;
GRANT ALL ON recommendation_outcomes TO neondb_owner;
GRANT ALL ON model_predictions TO neondb_owner;
GRANT ALL ON model_ab_assignments TO neondb_owner;
GRANT ALL ON referrals TO neondb_owner;
GRANT ALL ON model_config TO neondb_owner;
