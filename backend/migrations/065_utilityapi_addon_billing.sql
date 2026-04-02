-- Migration 065: UtilityAPI add-on billing columns
-- Adds per-connection Stripe subscription item tracking for UtilityAPI meter monitoring add-on.

ALTER TABLE user_connections
    ADD COLUMN IF NOT EXISTS stripe_subscription_item_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS utilityapi_meter_count INT DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_user_connections_utilityapi_billing
    ON user_connections (user_id, connection_type)
    WHERE connection_type = 'direct' AND status = 'active'
      AND stripe_subscription_item_id IS NOT NULL;

GRANT ALL ON user_connections TO neondb_owner;
