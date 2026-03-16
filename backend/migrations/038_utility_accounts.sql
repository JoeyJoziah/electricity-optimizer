-- Migration 038: Utility Accounts
-- Date: 2026-03-11
-- Purpose: User-utility-provider linking for multi-utility expansion (Wave 1)
--
-- Allows users to register their utility accounts (electricity, gas, etc.)
-- for personalized rate comparisons and provider tracking.

CREATE TABLE IF NOT EXISTS utility_accounts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL,
    utility_type            utility_type NOT NULL,
    region                  VARCHAR(50) NOT NULL,
    provider_name           VARCHAR(200) NOT NULL,
    account_number_encrypted BYTEA,
    is_primary              BOOLEAN NOT NULL DEFAULT FALSE,
    metadata                JSONB DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FK: cascade delete when the owning user is removed
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'utility_accounts'
          AND constraint_name = 'fk_utility_accounts_user'
          AND constraint_type = 'FOREIGN KEY'
    ) THEN
        ALTER TABLE utility_accounts
            ADD CONSTRAINT fk_utility_accounts_user
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;
END $$;

-- Prevent duplicate provider entries per user per utility type
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'utility_accounts'
          AND constraint_name = 'uq_user_utility_provider'
    ) THEN
        ALTER TABLE utility_accounts
            ADD CONSTRAINT uq_user_utility_provider UNIQUE (user_id, utility_type, provider_name);
    END IF;
END $$;

-- Query patterns
CREATE INDEX IF NOT EXISTS idx_utility_accounts_user_id
    ON utility_accounts (user_id);

CREATE INDEX IF NOT EXISTS idx_utility_accounts_user_type
    ON utility_accounts (user_id, utility_type);

CREATE INDEX IF NOT EXISTS idx_utility_accounts_region_type
    ON utility_accounts (region, utility_type);

-- Grant access
GRANT SELECT, INSERT, UPDATE, DELETE ON utility_accounts TO neondb_owner;
