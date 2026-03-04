-- Migration 022: Add composite index for user_supplier_accounts upsert performance
-- The ON CONFLICT (user_id, supplier_id) clause needs this composite index.
-- Migration 007 only created a single-column index on user_id.

CREATE INDEX IF NOT EXISTS idx_user_supplier_composite
ON user_supplier_accounts(user_id, supplier_id);
