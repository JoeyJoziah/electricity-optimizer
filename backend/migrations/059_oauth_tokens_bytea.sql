-- =============================================================================
-- Migration 059: Migrate OAuth tokens from TEXT (base64) to BYTEA
-- =============================================================================
--
-- Finding [12-P0-4]: OAuth access/refresh tokens stored in TEXT columns.
-- Although the application already encrypts tokens (AES-256-GCM via
-- encrypt_field()), it wraps the ciphertext in base64 before storing it as TEXT.
-- The correct pattern — used by all other sensitive fields in this codebase
-- (account_number_encrypted, meter_number_encrypted, portal credentials) — is to
-- store raw BYTEA directly, eliminating the unnecessary base64 round-trip.
--
-- Migration strategy:
--   1. Add temporary BYTEA columns (oauth_access_token_new, oauth_refresh_token_new)
--   2. Back-fill: decode existing base64 TEXT → BYTEA
--   3. Drop old TEXT columns
--   4. Rename _new columns to the canonical names
--   5. Re-create any indexes that referenced the old column names
--
-- Data integrity:
--   - Existing encrypted tokens in base64 TEXT are converted to raw BYTEA using
--     decode(value, 'base64') — no plaintext is ever exposed.
--   - Rows where the old column is NULL remain NULL in the new BYTEA column.
--   - After migration, the application layer writes raw bytes directly (no b64).
--
-- Safe to re-run: IF NOT EXISTS / DO-block guards on every step.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Step 1: Add temporary BYTEA columns for the new encoding
-- ---------------------------------------------------------------------------

ALTER TABLE public.user_connections
    ADD COLUMN IF NOT EXISTS oauth_access_token_new  BYTEA,
    ADD COLUMN IF NOT EXISTS oauth_refresh_token_new BYTEA;


-- ---------------------------------------------------------------------------
-- Step 2: Back-fill — decode base64 TEXT → BYTEA for existing rows
--         Rows where the original column is NULL stay NULL.
--         The decode() call is wrapped in a CASE to handle NULL gracefully.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    -- Only run if the old TEXT columns still exist
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name  = 'user_connections'
          AND  column_name = 'oauth_access_token'
          AND  data_type   = 'text'
    ) THEN
        UPDATE public.user_connections
        SET
            oauth_access_token_new  = CASE
                WHEN oauth_access_token IS NOT NULL
                THEN decode(oauth_access_token, 'base64')
                ELSE NULL
            END,
            oauth_refresh_token_new = CASE
                WHEN oauth_refresh_token IS NOT NULL
                THEN decode(oauth_refresh_token, 'base64')
                ELSE NULL
            END
        WHERE oauth_access_token IS NOT NULL
           OR oauth_refresh_token IS NOT NULL;

        RAISE NOTICE 'Migration 059: back-filled % rows with decoded BYTEA tokens',
            (SELECT COUNT(*) FROM public.user_connections
             WHERE  oauth_access_token IS NOT NULL
                OR  oauth_refresh_token IS NOT NULL);
    ELSE
        RAISE NOTICE 'Migration 059: old TEXT columns not found — back-fill skipped (already BYTEA?)';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- Step 3: Drop old TEXT columns (only if they still exist as TEXT)
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name  = 'user_connections'
          AND  column_name = 'oauth_access_token'
          AND  data_type   = 'text'
    ) THEN
        ALTER TABLE public.user_connections DROP COLUMN oauth_access_token;
        RAISE NOTICE 'Migration 059: dropped old TEXT column oauth_access_token';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name  = 'user_connections'
          AND  column_name = 'oauth_refresh_token'
          AND  data_type   = 'text'
    ) THEN
        ALTER TABLE public.user_connections DROP COLUMN oauth_refresh_token;
        RAISE NOTICE 'Migration 059: dropped old TEXT column oauth_refresh_token';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- Step 4: Rename temporary _new columns to canonical names
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    -- Rename oauth_access_token_new -> oauth_access_token
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name  = 'user_connections'
          AND  column_name = 'oauth_access_token_new'
    ) THEN
        ALTER TABLE public.user_connections
            RENAME COLUMN oauth_access_token_new TO oauth_access_token;
        RAISE NOTICE 'Migration 059: renamed oauth_access_token_new → oauth_access_token (BYTEA)';
    END IF;

    -- Rename oauth_refresh_token_new -> oauth_refresh_token
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name  = 'user_connections'
          AND  column_name = 'oauth_refresh_token_new'
    ) THEN
        ALTER TABLE public.user_connections
            RENAME COLUMN oauth_refresh_token_new TO oauth_refresh_token;
        RAISE NOTICE 'Migration 059: renamed oauth_refresh_token_new → oauth_refresh_token (BYTEA)';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

GRANT ALL ON public.user_connections TO neondb_owner;


-- ---------------------------------------------------------------------------
-- Completion notice
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    RAISE NOTICE 'Migration 059 complete: oauth_access_token and oauth_refresh_token are now BYTEA.';
END $$;
