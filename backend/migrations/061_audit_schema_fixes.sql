-- =============================================================================
-- Migration 061: Fix schema issues identified in 2026-03-23 audit (12-P0-*)
-- =============================================================================
--
-- Findings addressed (ordered by severity):
--
--   P0-2  users.name CHECK constraint — empty string bypasses NOT NULL.
--         Add CHECK (length(trim(name)) > 0); fix empty-name rows.
--
--   P0-3  stripe_processed_events.event_id unbounded VARCHAR.
--         Add VARCHAR(255) length limit and Stripe-prefix CHECK constraint.
--         Also bounds event_type to VARCHAR(100) (P2-2).
--
--   P0-4  model_ab_assignments UNIQUE (user_id) breaks multi-test scenarios.
--         Drop single-column unique constraint; replace with UNIQUE (user_id, model_name).
--
--   P0-5  Orphan notifications rows for users deleted before migration 051 added FK.
--         Delete notifications WHERE user_id not in users before enforcing FK.
--
--   P1-1  Orphan user_savings rows for users deleted before migration 052 added FK.
--   P1-2  Orphan recommendation_outcomes rows — same retroactive FK pattern.
--   P1-3  Orphan model_predictions rows — same retroactive FK pattern.
--   P1-4  Orphan referrals rows (referrer_id) — same retroactive FK pattern.
--
--   P1-6  community_posts/votes/reports timestamp columns missing NOT NULL.
--         ALTER to SET NOT NULL (DEFAULT now() ensures no NULLs exist).
--
--   P1-10 model_config missing UNIQUE (model_name, model_version).
--         Add constraint; deduplicate any existing duplicate rows first.
--
--   P2-8  cleanup_old_prices() uses `timestamp` column for retention — risks
--         deleting valid historical data.  Replace with `created_at`.
--
--   P2-9  Missing standalone index on electricity_prices.created_at for the
--         retention function and unfiltered recent-data queries.
--
--   P2-11 Missing post_id indexes on community_votes and community_reports —
--         COUNT(*) WHERE post_id = ? scans the trailing column of composite PK.
--
--   P3-6  heating_oil_dealers missing updated_at column — inconsistent with
--         all other reference tables.
--
-- Conventions:
--   - All DDL guards use IF NOT EXISTS / IF EXISTS for idempotency.
--   - CONCURRENTLY used for new indexes on large tables.
--   - BEGIN/COMMIT wraps DDL + DML; CONCURRENTLY indexes run outside the
--     transaction (they cannot run inside one).
--   - GRANTs included for neondb_owner.
--   - Note: CONCURRENTLY index creation statements are placed outside the
--     main transaction block because PostgreSQL does not allow CONCURRENTLY
--     inside a transaction. They are idempotent via IF NOT EXISTS.
-- =============================================================================


-- =============================================================================
-- SECTION 1: Transactional schema fixes
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- P0-2: users.name empty-string bypass
-- ---------------------------------------------------------------------------

-- Fix existing rows that have name = '' before adding the CHECK constraint.
-- Replace with 'Unknown User' to satisfy min_length=1 invariant in User model.
UPDATE users
SET    name       = 'Unknown User',
       updated_at = NOW()
WHERE  length(trim(name)) = 0;

-- Add the CHECK constraint if it does not already exist.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.check_constraints
        WHERE  constraint_schema = 'public'
          AND  constraint_name   = 'ck_users_name_nonempty'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT ck_users_name_nonempty
            CHECK (length(trim(name)) > 0);
        RAISE NOTICE 'ck_users_name_nonempty constraint added to users table';
    ELSE
        RAISE NOTICE 'ck_users_name_nonempty already exists — skipping';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- P0-3: stripe_processed_events.event_id — unbounded VARCHAR
-- ---------------------------------------------------------------------------
-- Alter event_id to VARCHAR(255) and event_type to VARCHAR(100) using
-- idempotent DO block because ALTER COLUMN TYPE has no IF NOT EXISTS syntax.

DO $$
DECLARE
    id_max   INT;
    type_max INT;
BEGIN
    SELECT character_maximum_length
    INTO   id_max
    FROM   information_schema.columns
    WHERE  table_schema = 'public'
      AND  table_name   = 'stripe_processed_events'
      AND  column_name  = 'event_id';

    IF id_max IS NULL THEN
        -- Column is unbounded TEXT/VARCHAR — set the length limit.
        ALTER TABLE stripe_processed_events
            ALTER COLUMN event_id TYPE VARCHAR(255);
        RAISE NOTICE 'stripe_processed_events.event_id set to VARCHAR(255)';
    ELSE
        RAISE NOTICE 'stripe_processed_events.event_id already bounded (%)', id_max;
    END IF;

    SELECT character_maximum_length
    INTO   type_max
    FROM   information_schema.columns
    WHERE  table_schema = 'public'
      AND  table_name   = 'stripe_processed_events'
      AND  column_name  = 'event_type';

    IF type_max IS NULL THEN
        ALTER TABLE stripe_processed_events
            ALTER COLUMN event_type TYPE VARCHAR(100);
        RAISE NOTICE 'stripe_processed_events.event_type set to VARCHAR(100)';
    ELSE
        RAISE NOTICE 'stripe_processed_events.event_type already bounded (%)', type_max;
    END IF;
END $$;

-- Add Stripe event-ID prefix CHECK constraint.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.check_constraints
        WHERE  constraint_schema = 'public'
          AND  constraint_name   = 'ck_stripe_event_id_prefix'
    ) THEN
        ALTER TABLE stripe_processed_events
            ADD CONSTRAINT ck_stripe_event_id_prefix
            CHECK (
                event_id LIKE 'evt_%'
                OR event_id LIKE 'ch_%'
                OR event_id LIKE 'cs_%'
                OR event_id LIKE 'in_%'
                OR event_id LIKE 'sub_%'
                OR event_id LIKE 'pi_%'
            );
        RAISE NOTICE 'ck_stripe_event_id_prefix constraint added';
    ELSE
        RAISE NOTICE 'ck_stripe_event_id_prefix already exists — skipping';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- P0-4: model_ab_assignments — replace UNIQUE (user_id) with UNIQUE (user_id, model_name)
-- ---------------------------------------------------------------------------
-- The single-column unique constraint prevents a user being assigned to more
-- than one A/B test.  The correct domain is one assignment per user per model.

DO $$
BEGIN
    -- Drop the broken single-column unique constraint if it exists.
    -- Use IF EXISTS directly on the ALTER so the linter is satisfied, and
    -- also so the statement is safe if the constraint was already dropped.
    ALTER TABLE model_ab_assignments
        DROP CONSTRAINT IF EXISTS uq_model_ab_assignments_user_id;
    RAISE NOTICE 'Dropped uq_model_ab_assignments_user_id (if it existed)';

    -- Add the correct composite unique constraint if not already present.
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.table_constraints
        WHERE  table_schema    = 'public'
          AND  table_name      = 'model_ab_assignments'
          AND  constraint_name = 'uq_model_ab_assignments_user_model'
          AND  constraint_type = 'UNIQUE'
    ) THEN
        ALTER TABLE model_ab_assignments
            ADD CONSTRAINT uq_model_ab_assignments_user_model
            UNIQUE (user_id, model_name);
        RAISE NOTICE 'Added uq_model_ab_assignments_user_model (user_id, model_name)';
    ELSE
        RAISE NOTICE 'uq_model_ab_assignments_user_model already exists — skipping';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- P0-5: Orphan notifications rows (user deleted before migration 051 added FK)
-- ---------------------------------------------------------------------------
-- Delete orphan rows so that the existing FK constraint (added in migration 051)
-- is clean.  The FK already exists; this is a data-hygiene step only.

DELETE FROM notifications
WHERE  user_id NOT IN (SELECT id FROM users);


-- ---------------------------------------------------------------------------
-- P1-1: Orphan user_savings rows
-- ---------------------------------------------------------------------------

DELETE FROM user_savings
WHERE  user_id NOT IN (SELECT id FROM users);


-- ---------------------------------------------------------------------------
-- P1-2: Orphan recommendation_outcomes rows
-- ---------------------------------------------------------------------------

DELETE FROM recommendation_outcomes
WHERE  user_id NOT IN (SELECT id FROM users);


-- ---------------------------------------------------------------------------
-- P1-3: Orphan model_predictions rows
-- ---------------------------------------------------------------------------

DELETE FROM model_predictions
WHERE  user_id NOT IN (SELECT id FROM users);


-- ---------------------------------------------------------------------------
-- P1-4: Orphan referrals rows (referrer_id)
-- ---------------------------------------------------------------------------
-- referrer_id is NOT NULL, so only rows where the referrer was deleted need
-- cleanup.  referee_id is nullable — those rows are intentionally kept.

DELETE FROM referrals
WHERE  referrer_id NOT IN (SELECT id FROM users);


-- ---------------------------------------------------------------------------
-- P1-6: community_posts/votes/reports timestamp columns — add NOT NULL
-- ---------------------------------------------------------------------------
-- All rows inserted before this migration have DEFAULT now() values and
-- therefore cannot be NULL.  The ALTER is safe without a data backfill.

DO $$
BEGIN
    -- community_posts.created_at
    IF EXISTS (
        SELECT 1
        FROM   information_schema.columns
        WHERE  table_schema   = 'public'
          AND  table_name     = 'community_posts'
          AND  column_name    = 'created_at'
          AND  is_nullable    = 'YES'
    ) THEN
        ALTER TABLE community_posts
            ALTER COLUMN created_at SET NOT NULL,
            ALTER COLUMN updated_at SET NOT NULL;
        RAISE NOTICE 'community_posts created_at/updated_at set to NOT NULL';
    END IF;

    -- community_votes.created_at
    IF EXISTS (
        SELECT 1
        FROM   information_schema.columns
        WHERE  table_schema   = 'public'
          AND  table_name     = 'community_votes'
          AND  column_name    = 'created_at'
          AND  is_nullable    = 'YES'
    ) THEN
        ALTER TABLE community_votes
            ALTER COLUMN created_at SET NOT NULL;
        RAISE NOTICE 'community_votes.created_at set to NOT NULL';
    END IF;

    -- community_reports.created_at
    IF EXISTS (
        SELECT 1
        FROM   information_schema.columns
        WHERE  table_schema   = 'public'
          AND  table_name     = 'community_reports'
          AND  column_name    = 'created_at'
          AND  is_nullable    = 'YES'
    ) THEN
        ALTER TABLE community_reports
            ALTER COLUMN created_at SET NOT NULL;
        RAISE NOTICE 'community_reports.created_at set to NOT NULL';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- P1-10: model_config — add UNIQUE (model_name, model_version)
-- ---------------------------------------------------------------------------
-- Remove duplicate rows first (keep the most recently created row per pair).

DELETE FROM model_config
WHERE  id NOT IN (
    SELECT DISTINCT ON (model_name, model_version) id
    FROM   model_config
    ORDER  BY model_name, model_version, created_at DESC
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.table_constraints
        WHERE  table_schema    = 'public'
          AND  table_name      = 'model_config'
          AND  constraint_name = 'uq_model_config_name_version'
          AND  constraint_type = 'UNIQUE'
    ) THEN
        ALTER TABLE model_config
            ADD CONSTRAINT uq_model_config_name_version
            UNIQUE (model_name, model_version);
        RAISE NOTICE 'Added uq_model_config_name_version to model_config';
    ELSE
        RAISE NOTICE 'uq_model_config_name_version already exists — skipping';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- P2-8: Fix cleanup_old_prices() to use created_at instead of timestamp
-- ---------------------------------------------------------------------------
-- The old retention function deleted rows by observation timestamp, which
-- could prematurely remove historical price data used for ML training.
-- The correct boundary is the insertion time (created_at).

CREATE OR REPLACE FUNCTION cleanup_old_prices(retention_days INTEGER DEFAULT 365)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM electricity_prices
    WHERE created_at < NOW() - (retention_days || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    RAISE NOTICE 'cleanup_old_prices: deleted % rows with created_at older than % days',
        deleted_count, retention_days;

    RETURN deleted_count;
END;
$$;

GRANT EXECUTE ON FUNCTION cleanup_old_prices(INTEGER) TO neondb_owner;


-- ---------------------------------------------------------------------------
-- P3-6: heating_oil_dealers — add missing updated_at column
-- ---------------------------------------------------------------------------

ALTER TABLE heating_oil_dealers
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Backfill updated_at to match created_at for existing rows where default
-- now() would incorrectly show the migration time instead of creation time.
UPDATE heating_oil_dealers
SET    updated_at = created_at
WHERE  updated_at > created_at + INTERVAL '1 minute';

-- Add updated_at trigger following the migration 060 pattern.
CREATE OR REPLACE FUNCTION update_heating_oil_dealers_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.triggers
        WHERE  trigger_schema = 'public'
          AND  event_object_table = 'heating_oil_dealers'
          AND  trigger_name       = 'trg_heating_oil_dealers_updated_at'
    ) THEN
        CREATE TRIGGER trg_heating_oil_dealers_updated_at
            BEFORE UPDATE ON heating_oil_dealers
            FOR EACH ROW EXECUTE FUNCTION update_heating_oil_dealers_updated_at();
        RAISE NOTICE 'trg_heating_oil_dealers_updated_at trigger created';
    ELSE
        RAISE NOTICE 'trg_heating_oil_dealers_updated_at already exists — skipping';
    END IF;
END $$;


-- =============================================================================
-- GRANTS
-- =============================================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON model_config           TO neondb_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON model_ab_assignments   TO neondb_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON stripe_processed_events TO neondb_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON heating_oil_dealers    TO neondb_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON users                  TO neondb_owner;


COMMIT;


-- =============================================================================
-- SECTION 2: CONCURRENTLY indexes (must run outside a transaction)
-- =============================================================================
-- These are placed outside the BEGIN/COMMIT block because CREATE INDEX
-- CONCURRENTLY cannot run inside a transaction.  They are idempotent via
-- IF NOT EXISTS and can be re-run safely.

-- P2-9: Standalone created_at index on electricity_prices for the fixed
--       cleanup_old_prices() function and unfiltered recent-data queries.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prices_created_at
    ON electricity_prices (created_at DESC);

-- P2-11: post_id lookup indexes on community vote/report tables.
--        PostgreSQL cannot efficiently scan the trailing column of a composite
--        PK index, so COUNT(*) WHERE post_id = ? benefits greatly from these.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_community_votes_post_id
    ON community_votes (post_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_community_reports_post_id
    ON community_reports (post_id);

-- =============================================================================
-- Migration 061 complete.
-- =============================================================================
