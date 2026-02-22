-- =============================================================================
-- Migration: Reconcile Schema Divergence Between init_neon.sql and 002_gdpr_auth_tables.sql
-- Version: 003
-- Date: 2026-02-22
-- Issue: GitHub Issue #3
-- =============================================================================
--
-- BACKGROUND
-- ----------
-- init_neon.sql created consent_records and deletion_logs with an early schema
-- design. Migration 002_gdpr_auth_tables.sql later defined these same tables
-- with a more complete GDPR-compliant schema. Because 002 uses CREATE TABLE IF
-- NOT EXISTS, it silently no-ops when the tables already exist from init_neon,
-- leaving the production schema stuck on the older, incomplete column set.
--
-- This migration reconciles the live schema (init_neon state) with the schema
-- that the application code in compliance/repositories.py and models/consent.py
-- actually expects (002 state). Every step uses IF NOT EXISTS / IF EXISTS guards
-- so this migration is safe to re-run.
--
-- APPLICATION COLUMN EXPECTATIONS (source of truth)
-- --------------------------------------------------
-- ConsentRecordORM (repositories.py):
--   id, user_id, purpose, consent_given, timestamp, ip_address,
--   user_agent (String(500)), consent_version, withdrawal_timestamp,
--   metadata_json (JSON)
--
-- DeletionLogORM (repositories.py):
--   id, user_id, deleted_at, deleted_by, deletion_type, ip_address,
--   user_agent (String(500)), data_categories_deleted (JSON),
--   legal_basis, metadata_json (JSON)
-- =============================================================================


-- =============================================================================
-- SECTION 1: consent_records
-- =============================================================================
-- The init_neon schema for consent_records differs from what the ORM expects
-- in the following ways:
--   1. Column "metadata" exists but the ORM references "metadata_json"
--   2. Column "user_agent" is TEXT but the ORM declares String(500)
--   3. Column "purpose" is VARCHAR(100) but the ORM declares String(50)
--   4. FK constraint fk_consent_user (user_id -> users.id) is absent
--   5. Index idx_consent_user_purpose is absent

-- 1a. Rename metadata -> metadata_json
--     The ORM exclusively reads and writes via the "metadata_json" column name
--     (see repositories.py lines 42, 103, 233). The old "metadata" column name
--     is not referenced anywhere in application code.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'consent_records' AND column_name = 'metadata'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'consent_records' AND column_name = 'metadata_json'
    ) THEN
        ALTER TABLE consent_records RENAME COLUMN metadata TO metadata_json;
        RAISE NOTICE 'consent_records.metadata renamed to metadata_json';
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'consent_records' AND column_name = 'metadata_json'
    ) THEN
        RAISE NOTICE 'consent_records.metadata_json already exists, skipping rename';
    ELSE
        RAISE NOTICE 'consent_records.metadata column not found; no rename performed';
    END IF;
END $$;

-- 1b. Add metadata_json if it was absent entirely (edge case: neither name exists)
ALTER TABLE consent_records
    ADD COLUMN IF NOT EXISTS metadata_json JSONB;

-- 1c. Narrow user_agent from TEXT to VARCHAR(500) to match ORM String(500).
--     ALTER TYPE requires no data change since VARCHAR(500) is more restrictive
--     only for future inserts; existing values up to 500 chars are unaffected.
--     Values longer than 500 characters (highly unlikely for a UA string) would
--     cause this step to fail — leaving them as TEXT is acceptable if that
--     occurs; the ORM will still function correctly with TEXT.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'consent_records'
          AND column_name = 'user_agent'
          AND data_type = 'text'
    ) THEN
        ALTER TABLE consent_records
            ALTER COLUMN user_agent TYPE VARCHAR(500);
        RAISE NOTICE 'consent_records.user_agent narrowed from TEXT to VARCHAR(500)';
    ELSE
        RAISE NOTICE 'consent_records.user_agent is not TEXT, skipping type change';
    END IF;
END $$;

-- 1d. Narrow purpose from VARCHAR(100) to VARCHAR(50) to match ORM String(50)
--     and the consent_purpose enum values (max length ~20 chars). All existing
--     purposes in the ConsentPurpose enum fit within 50 characters.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'consent_records'
          AND column_name = 'purpose'
          AND character_maximum_length = 100
    ) THEN
        ALTER TABLE consent_records
            ALTER COLUMN purpose TYPE VARCHAR(50);
        RAISE NOTICE 'consent_records.purpose narrowed from VARCHAR(100) to VARCHAR(50)';
    ELSE
        RAISE NOTICE 'consent_records.purpose is not VARCHAR(100), skipping type change';
    END IF;
END $$;

-- 1e. Add FK constraint on consent_records.user_id -> users.id ON DELETE CASCADE.
--     The ORM and 002 migration both define this constraint as fk_consent_user.
--     init_neon omitted it entirely.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'consent_records'
          AND constraint_name = 'fk_consent_user'
          AND constraint_type = 'FOREIGN KEY'
    ) THEN
        ALTER TABLE consent_records
            ADD CONSTRAINT fk_consent_user
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
        RAISE NOTICE 'FK constraint fk_consent_user added to consent_records';
    ELSE
        RAISE NOTICE 'FK constraint fk_consent_user already exists on consent_records';
    END IF;
END $$;

-- 1f. Add missing index idx_consent_user_purpose (defined in 002, absent from init_neon).
--     Supports the ConsentRepository.get_by_user_and_purpose() query path.
CREATE INDEX IF NOT EXISTS idx_consent_user_purpose
    ON consent_records (user_id, purpose);

-- 1g. Add missing index idx_consent_timestamp (defined in 002, absent from init_neon).
CREATE INDEX IF NOT EXISTS idx_consent_timestamp
    ON consent_records (timestamp DESC);


-- =============================================================================
-- SECTION 2: deletion_logs
-- =============================================================================
-- The init_neon schema for deletion_logs differs from what the ORM expects
-- in the following ways:
--   1. Column "timestamp" exists but the ORM references "deleted_at"
--   2. Column "deleted_categories" is TEXT[] but the ORM expects
--      "data_categories_deleted" as JSON/JSONB
--   3. Column "user_agent" is TEXT but the ORM declares String(500)
--   4. Columns "deletion_type", "legal_basis", and "metadata_json" are absent
--   5. Index idx_deletion_timestamp references deleted_at (absent from init_neon)
--
-- NOTE: deletion_logs has an immutability trigger (tr_prevent_deletion_log_update)
-- that blocks UPDATE and DELETE on rows. Schema DDL (ALTER TABLE, ADD COLUMN,
-- RENAME COLUMN) is not subject to row-level triggers and will succeed normally.

-- 2a. Rename timestamp -> deleted_at
--     The ORM exclusively references "deleted_at" (repositories.py lines 52, 309).
--     The old "timestamp" column name is not used anywhere in application code.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'deletion_logs' AND column_name = 'timestamp'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'deletion_logs' AND column_name = 'deleted_at'
    ) THEN
        ALTER TABLE deletion_logs RENAME COLUMN timestamp TO deleted_at;
        RAISE NOTICE 'deletion_logs.timestamp renamed to deleted_at';
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'deletion_logs' AND column_name = 'deleted_at'
    ) THEN
        RAISE NOTICE 'deletion_logs.deleted_at already exists, skipping rename';
    ELSE
        RAISE NOTICE 'deletion_logs.timestamp column not found; no rename performed';
    END IF;
END $$;

-- 2b. Rename deleted_categories (TEXT[]) -> data_categories_deleted, then retype to JSONB.
--
--     The ORM column data_categories_deleted is declared as JSON (repositories.py
--     line 57) and populated with a Python list (gdpr.py line 553). TEXT[] cannot
--     be assigned a JSON list from SQLAlchemy's JSON type without an explicit cast.
--
--     Strategy:
--       i.  Rename the column to the correct name if it still has the old name.
--       ii. Add the correctly-typed JSONB column if neither name exists yet.
--       iii. If the old TEXT[] column was already renamed but is still TEXT[],
--            migrate data and retype.
--
-- Step i: rename deleted_categories -> data_categories_deleted
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'deletion_logs' AND column_name = 'deleted_categories'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'deletion_logs' AND column_name = 'data_categories_deleted'
    ) THEN
        ALTER TABLE deletion_logs
            RENAME COLUMN deleted_categories TO data_categories_deleted;
        RAISE NOTICE 'deletion_logs.deleted_categories renamed to data_categories_deleted';
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'deletion_logs' AND column_name = 'data_categories_deleted'
    ) THEN
        RAISE NOTICE 'deletion_logs.data_categories_deleted already exists, skipping rename';
    ELSE
        RAISE NOTICE 'deletion_logs.deleted_categories not found; skipping rename';
    END IF;
END $$;

-- Step ii: add data_categories_deleted as JSONB if the column does not exist at all
ALTER TABLE deletion_logs
    ADD COLUMN IF NOT EXISTS data_categories_deleted JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Step iii: convert data_categories_deleted from TEXT[] to JSONB if it is still an array type.
--     Converts each existing TEXT[] value to a JSON array via array_to_json().
--     Example: '{"consents","profile"}'::text[] -> '["consents","profile"]'::jsonb
DO $$
DECLARE
    col_udt TEXT;
BEGIN
    SELECT udt_name INTO col_udt
    FROM information_schema.columns
    WHERE table_name = 'deletion_logs' AND column_name = 'data_categories_deleted';

    IF col_udt = '_text' THEN  -- _text is the udt_name for TEXT[]
        -- Temporarily disable the immutability trigger so we can backfill the column
        ALTER TABLE deletion_logs DISABLE TRIGGER tr_prevent_deletion_log_update;

        ALTER TABLE deletion_logs
            ALTER COLUMN data_categories_deleted
            TYPE JSONB USING array_to_json(data_categories_deleted)::jsonb;

        ALTER TABLE deletion_logs ENABLE TRIGGER tr_prevent_deletion_log_update;

        RAISE NOTICE 'deletion_logs.data_categories_deleted retyped from TEXT[] to JSONB';
    ELSIF col_udt = 'jsonb' THEN
        RAISE NOTICE 'deletion_logs.data_categories_deleted is already JSONB, skipping retype';
    ELSE
        RAISE NOTICE 'deletion_logs.data_categories_deleted has unexpected type: %; skipping retype', col_udt;
    END IF;
END $$;

-- 2c. Narrow user_agent from TEXT to VARCHAR(500) to match ORM String(500).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'deletion_logs'
          AND column_name = 'user_agent'
          AND data_type = 'text'
    ) THEN
        ALTER TABLE deletion_logs
            ALTER COLUMN user_agent TYPE VARCHAR(500);
        RAISE NOTICE 'deletion_logs.user_agent narrowed from TEXT to VARCHAR(500)';
    ELSE
        RAISE NOTICE 'deletion_logs.user_agent is not TEXT, skipping type change';
    END IF;
END $$;

-- 2d. Add missing column: deletion_type
--     Required by DeletionLogORM (repositories.py line 54) and populated in
--     gdpr.py line 550 with "anonymization" or "full".
ALTER TABLE deletion_logs
    ADD COLUMN IF NOT EXISTS deletion_type VARCHAR(20);

-- Back-fill existing rows conservatively: treat any pre-existing row as a
-- full deletion since we have no other signal.
-- The immutability trigger blocks UPDATE on rows, so we must disable it for
-- this one-time schema back-fill, then re-enable it immediately.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM deletion_logs WHERE deletion_type IS NULL LIMIT 1
    ) THEN
        ALTER TABLE deletion_logs DISABLE TRIGGER tr_prevent_deletion_log_update;

        UPDATE deletion_logs
            SET deletion_type = 'full'
            WHERE deletion_type IS NULL;

        ALTER TABLE deletion_logs ENABLE TRIGGER tr_prevent_deletion_log_update;

        RAISE NOTICE 'deletion_logs.deletion_type back-filled to ''full'' for pre-existing rows';
    ELSE
        RAISE NOTICE 'deletion_logs.deletion_type: no NULL rows to back-fill';
    END IF;
END $$;

-- Now enforce NOT NULL to match 002's intent and the ORM's non-optional mapping.
-- Wrapped in a DO block to tolerate databases where the column was already NOT NULL.
DO $$
BEGIN
    ALTER TABLE deletion_logs ALTER COLUMN deletion_type SET NOT NULL;
    RAISE NOTICE 'deletion_logs.deletion_type set to NOT NULL';
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Could not set deletion_type NOT NULL (may already be set): %', SQLERRM;
END $$;

-- 2e. Add missing column: legal_basis
--     Optional in DeletionLogORM (repositories.py line 58), defaulting to
--     'user_request' in both 002 and gdpr.py line 554.
ALTER TABLE deletion_logs
    ADD COLUMN IF NOT EXISTS legal_basis VARCHAR(50) DEFAULT 'user_request';

-- 2f. Add missing column: metadata_json
--     Optional in DeletionLogORM (repositories.py line 59), stores supplementary
--     audit data passed via DeletionLog.metadata (models/consent.py line 170).
ALTER TABLE deletion_logs
    ADD COLUMN IF NOT EXISTS metadata_json JSONB;

-- 2g. Drop the now-redundant index on the old column name (timestamp) if it
--     survived the rename, and ensure the correctly-named index exists.
DROP INDEX IF EXISTS idx_deletion_logs_timestamp;

CREATE INDEX IF NOT EXISTS idx_deletion_timestamp
    ON deletion_logs (deleted_at DESC);

-- The idx_deletion_user_id index from 002 may differ from init_neon's
-- idx_deletion_logs_user_id; create the canonical name if absent.
CREATE INDEX IF NOT EXISTS idx_deletion_user_id
    ON deletion_logs (user_id);


-- =============================================================================
-- SECTION 3: Verify consent_purpose enum type
-- =============================================================================
-- 002 defines a consent_purpose ENUM type used for documentation; it is not
-- referenced by a column constraint in the current ORM (which stores purpose as
-- VARCHAR). Ensure the type exists so tooling that depends on it does not fail.
DO $$ BEGIN
    CREATE TYPE consent_purpose AS ENUM (
        'data_processing',
        'marketing',
        'analytics',
        'price_alerts',
        'optimization',
        'third_party_sharing'
    );
EXCEPTION
    WHEN duplicate_object THEN
        RAISE NOTICE 'consent_purpose enum type already exists, skipping';
END $$;


-- =============================================================================
-- SECTION 4: Grants
-- =============================================================================
-- Re-apply the grants from 002 in case they were not applied because the tables
-- already existed (the 002 GRANT block ran unconditionally, but some environments
-- may have missed it if the migration was skipped).
DO $$ BEGIN
    GRANT SELECT, INSERT ON consent_records TO neondb_owner;
    GRANT SELECT, INSERT ON deletion_logs TO neondb_owner;
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'neondb_owner role not found, skipping grants';
END $$;


-- =============================================================================
-- Migration complete.
-- Run "SELECT column_name, data_type, character_maximum_length
--      FROM information_schema.columns
--      WHERE table_name IN ('consent_records','deletion_logs')
--      ORDER BY table_name, ordinal_position;"
-- to verify the resulting schema matches the ORM expectations.
-- =============================================================================
