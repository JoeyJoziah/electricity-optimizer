-- =============================================================================
-- Migration 057: Add ghost columns missing from schema
-- =============================================================================
--
-- Findings [12-P0-1, 12-P0-2]: The ORM and raw-SQL repositories reference
-- several columns that were never created by any prior migration:
--
--   users table:
--     - stripe_customer_id  (VARCHAR 255, nullable) — Stripe customer reference
--     - subscription_tier   (VARCHAR 20, default 'free') — plan tier
--     - household_size      (INTEGER, nullable) — number of people in household
--     - average_daily_kwh   (NUMERIC(10,4), nullable) — average daily usage
--     - current_tariff      (VARCHAR 200, nullable) — current tariff name
--
--   electricity_prices table:
--     - carbon_intensity    (NUMERIC(10,4), nullable) — gCO2eq/kWh
--
-- Migrations 004 and 037 already created indexes ON users(stripe_customer_id),
-- meaning these columns must exist in production already (PostgreSQL would have
-- rejected the CREATE INDEX otherwise).  However, there is no explicit ADD COLUMN
-- migration to create them — they may have been added out-of-band.
--
-- This migration uses ADD COLUMN IF NOT EXISTS to be idempotent: it is safe to
-- run whether the columns already exist or not.
--
-- All statements use IF NOT EXISTS guards so the migration is re-runnable.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. users.stripe_customer_id
--    Used by user_repository.py _USER_COLUMNS, create(), and update().
--    Indexed by migration 004 and 037; constrained UNIQUE by migration 056.
-- ---------------------------------------------------------------------------

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255);


-- ---------------------------------------------------------------------------
-- 2. users.subscription_tier
--    Used by user_repository.py _USER_COLUMNS, create(), and update().
--    Stripe service reads/writes this column for plan management.
-- ---------------------------------------------------------------------------

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(20) NOT NULL DEFAULT 'free';


-- ---------------------------------------------------------------------------
-- 3. users.household_size
--    Used by user_repository.py _USER_COLUMNS, create(), and update().
-- ---------------------------------------------------------------------------

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS household_size INTEGER;


-- ---------------------------------------------------------------------------
-- 4. users.average_daily_kwh
--    Used by user_repository.py _USER_COLUMNS, create(), and update().
-- ---------------------------------------------------------------------------

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS average_daily_kwh NUMERIC(10, 4);


-- ---------------------------------------------------------------------------
-- 5. users.current_tariff
--    Used by user_repository.py _USER_COLUMNS, create(), and update().
-- ---------------------------------------------------------------------------

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS current_tariff VARCHAR(200);


-- ---------------------------------------------------------------------------
-- 6. electricity_prices.carbon_intensity
--    Used by price_repository.py for SELECT, INSERT, and UPDATE queries.
--    gCO2eq/kWh; nullable because many data sources do not provide it.
-- ---------------------------------------------------------------------------

ALTER TABLE public.electricity_prices
    ADD COLUMN IF NOT EXISTS carbon_intensity NUMERIC(10, 4);


-- ---------------------------------------------------------------------------
-- 7. Add CHECK constraint on subscription_tier values
--    (idempotent: wrapped in DO block)
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_constraint
        WHERE  conrelid = 'public.users'::regclass
        AND    conname  = 'ck_users_subscription_tier'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT ck_users_subscription_tier
            CHECK (subscription_tier IN ('free', 'pro', 'business'));

        RAISE NOTICE 'Migration 057: added CHECK constraint ck_users_subscription_tier';
    ELSE
        RAISE NOTICE 'Migration 057: ck_users_subscription_tier already exists — skipped';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- 8. Add index on subscription_tier for plan-gating queries
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_users_subscription_tier
    ON public.users (subscription_tier);


-- ---------------------------------------------------------------------------
-- 9. Grants
-- ---------------------------------------------------------------------------

GRANT ALL ON public.users TO neondb_owner;
GRANT ALL ON public.electricity_prices TO neondb_owner;


-- ---------------------------------------------------------------------------
-- 10. Completion notice
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    RAISE NOTICE 'Migration 057 complete: ghost columns added to users and electricity_prices.';
END $$;
