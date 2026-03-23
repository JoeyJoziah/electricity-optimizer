-- =============================================================================
-- Migration 056: Add UNIQUE constraint on users.stripe_customer_id
-- =============================================================================
--
-- Problem [14-P0-2]: The ``stripe_customer_id`` column on the ``users`` table
-- has no uniqueness constraint.  A bug or race condition could associate the
-- same Stripe customer with two user rows, causing one user's subscription
-- changes to silently bleed into another user's account (wrong tier activated,
-- double dunning emails, etc.).
--
-- Fix: Add a UNIQUE constraint on ``users.stripe_customer_id``.
--
-- PostgreSQL unique constraints exclude NULL values by default, so free-tier
-- users (stripe_customer_id IS NULL) are unaffected — multiple NULL rows are
-- allowed.  Only rows where stripe_customer_id IS NOT NULL are constrained.
--
-- Pre-flight check:
--   If duplicates already exist in production (should not — each Stripe
--   customer maps to one account) the ALTER TABLE will fail.  Before
--   applying, run the diagnostic query below and resolve any duplicates
--   found by merging or nulling out the conflicting rows.
--
--   SELECT stripe_customer_id, COUNT(*) AS n
--   FROM public.users
--   WHERE stripe_customer_id IS NOT NULL
--   GROUP BY stripe_customer_id
--   HAVING COUNT(*) > 1;
--
-- Safe to re-run: DO block checks for constraint existence before adding.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. Add UNIQUE constraint on stripe_customer_id (NULLs excluded by default)
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_constraint
        WHERE  conrelid = 'public.users'::regclass
        AND    conname   = 'uq_users_stripe_customer_id'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT uq_users_stripe_customer_id
            UNIQUE (stripe_customer_id);

        RAISE NOTICE 'Migration 056: added UNIQUE constraint uq_users_stripe_customer_id';
    ELSE
        RAISE NOTICE 'Migration 056: constraint uq_users_stripe_customer_id already exists — skipped';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- 2. Supporting index (the constraint creates one implicitly, but name it
--    explicitly for observability in pg_stat_user_indexes)
-- ---------------------------------------------------------------------------
--
-- PostgreSQL automatically creates an index to back a UNIQUE constraint, so
-- no separate CREATE INDEX is needed.  The constraint index will be named
-- ``uq_users_stripe_customer_id`` and is already a partial index by virtue of
-- NULL exclusion in Postgres's constraint semantics.


-- ---------------------------------------------------------------------------
-- 3. Grants
-- ---------------------------------------------------------------------------

GRANT ALL ON public.users TO neondb_owner;


-- ---------------------------------------------------------------------------
-- 4. Completion notice
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    RAISE NOTICE 'Migration 056 complete: stripe_customer_id UNIQUE constraint enforced on public.users.';
END $$;
