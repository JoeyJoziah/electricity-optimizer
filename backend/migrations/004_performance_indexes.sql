-- Performance indexes for common query patterns
-- Applied: 2026-02-23

-- Compound index for get_latest_by_supplier queries:
-- SELECT ... FROM electricity_prices WHERE region = ? AND supplier = ? ORDER BY timestamp DESC LIMIT 1
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prices_region_supplier_timestamp
    ON electricity_prices (region, supplier, timestamp DESC);

-- Index for Stripe customer lookups on users table
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_stripe_customer_id
    ON users (stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;
