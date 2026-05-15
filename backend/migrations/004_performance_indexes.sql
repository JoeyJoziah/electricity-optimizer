-- Performance indexes for common query patterns
-- Applied: 2026-02-23
--
-- =============================================================================
-- RETROACTIVE EDIT 2026-05-15 — track ci-migration-004-stripe-customer-id_20260515
-- =============================================================================
-- The original migration unconditionally created an index on
-- users.stripe_customer_id, but that column is not added until migration 057
-- (057_ghost_columns.sql). The migration succeeded in prod because the column
-- was added out-of-band before this file ran, but fresh `psql -f` replay from
-- an empty DB fails at line 12 with `column "stripe_customer_id" does not exist`.
--
-- Fix: wrap the stripe_customer_id index in a DO block guarded by a check
-- against information_schema.columns. On fresh replay the column does not
-- yet exist here, so the block no-ops and migration 057 (or 037) creates the
-- index later. In prod the column exists, IF NOT EXISTS makes the index
-- creation idempotent, and the partial-index predicate is preserved.
--
-- CONCURRENTLY is dropped inside the DO block because CREATE INDEX
-- CONCURRENTLY cannot run inside a transaction/PL block. For fresh-replay
-- against a brand-new DB this is harmless (no concurrent traffic); for prod
-- the index already exists and the IF NOT EXISTS skips the statement.
-- =============================================================================

-- Compound index for get_latest_by_supplier queries:
-- SELECT ... FROM electricity_prices WHERE region = ? AND supplier = ? ORDER BY timestamp DESC LIMIT 1
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prices_region_supplier_timestamp
    ON electricity_prices (region, supplier, timestamp DESC);

-- Index for Stripe customer lookups on users table
-- Guarded: column is created by migration 057 (out-of-band in prod history).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM   information_schema.columns
        WHERE  table_schema = 'public'
        AND    table_name   = 'users'
        AND    column_name  = 'stripe_customer_id'
    ) THEN
        EXECUTE $sql$
            CREATE INDEX IF NOT EXISTS idx_users_stripe_customer_id
                ON users (stripe_customer_id)
                WHERE stripe_customer_id IS NOT NULL
        $sql$;
        RAISE NOTICE 'Migration 004: created idx_users_stripe_customer_id';
    ELSE
        RAISE NOTICE 'Migration 004: users.stripe_customer_id not yet present — index deferred to migration 057';
    END IF;
END $$;
