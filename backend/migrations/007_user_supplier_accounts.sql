-- Migration 007: User Supplier Accounts
-- Adds FK-based supplier selection and encrypted account linking
--
-- Prerequisites: migration 006 (supplier_registry table)

-- Add FK column to users (keep VARCHAR current_supplier for backward compat)
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_supplier_id UUID REFERENCES supplier_registry(id);

-- Create user_supplier_accounts table for account linking
CREATE TABLE IF NOT EXISTS user_supplier_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    supplier_id UUID NOT NULL REFERENCES supplier_registry(id),
    account_number_encrypted BYTEA,
    meter_number_encrypted BYTEA,
    service_zip VARCHAR(10),
    account_nickname VARCHAR(100),
    is_primary BOOLEAN NOT NULL DEFAULT TRUE,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, supplier_id)
);

CREATE INDEX IF NOT EXISTS idx_user_supplier_user ON user_supplier_accounts(user_id);

-- Grant permissions to neondb_owner role
GRANT ALL ON user_supplier_accounts TO neondb_owner;
