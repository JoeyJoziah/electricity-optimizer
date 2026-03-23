-- =============================================================================
-- Migration 060: Add missing updated_at auto-update triggers
-- =============================================================================
--
-- Finding [12-P1]: 15+ tables have an `updated_at` column but no trigger to
-- automatically update it on row modification.  Without a trigger, application
-- code must explicitly set `updated_at = NOW()` in every UPDATE — a pattern
-- that is error-prone and frequently forgotten.
--
-- The init_neon.sql migration created the `update_updated_at_column()` function
-- and the `trigger_users_updated_at` trigger for the `users` table.
-- Migration 049 created a trigger for `community_posts`.
-- All other tables with `updated_at` are unguarded.
--
-- Tables receiving triggers in this migration:
--   1. supplier_registry           (migration 006)
--   2. state_regulations           (migration 006)
--   3. user_supplier_accounts      (migration 007)
--   4. user_connections            (migration 008)
--   5. bill_uploads                (migration 008)
--   6. price_alert_configs         (migration 014)
--   7. feature_flags               (migration 016)
--   8. payment_retry_history       (migration 024)
--   9. model_config                (migration 027)
--  10. feedback                    (migration 028)
--  11. utility_accounts            (migration 038)
--  12. community_solar_programs    (migration 041)
--  13. cca_programs                (migration 042)
--  14. user_alert_configs          (migration 044)
--  15. water_rates_config          (migration 047)
--
-- Already covered (no trigger needed):
--   - users                (init_neon trigger_users_updated_at)
--   - community_posts      (migration 049 trg_community_posts_updated_at)
--
-- Each trigger is wrapped in DROP TRIGGER IF EXISTS + CREATE TRIGGER so the
-- migration is idempotent.  The function itself uses CREATE OR REPLACE so
-- it is always up-to-date.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Ensure the trigger function exists (idempotent via CREATE OR REPLACE)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------------------
-- Helper macro: for each table, drop then recreate the trigger
-- (PostgreSQL does not have CREATE TRIGGER IF NOT EXISTS before v17)
-- ---------------------------------------------------------------------------

-- 1. supplier_registry
DROP TRIGGER IF EXISTS trg_supplier_registry_updated_at ON public.supplier_registry;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'supplier_registry' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_supplier_registry_updated_at
            BEFORE UPDATE ON public.supplier_registry
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to supplier_registry';
    END IF;
END $$;

-- 2. state_regulations
DROP TRIGGER IF EXISTS trg_state_regulations_updated_at ON public.state_regulations;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'state_regulations' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_state_regulations_updated_at
            BEFORE UPDATE ON public.state_regulations
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to state_regulations';
    END IF;
END $$;

-- 3. user_supplier_accounts
DROP TRIGGER IF EXISTS trg_user_supplier_accounts_updated_at ON public.user_supplier_accounts;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_supplier_accounts' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_user_supplier_accounts_updated_at
            BEFORE UPDATE ON public.user_supplier_accounts
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to user_supplier_accounts';
    END IF;
END $$;

-- 4. user_connections
DROP TRIGGER IF EXISTS trg_user_connections_updated_at ON public.user_connections;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_connections' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_user_connections_updated_at
            BEFORE UPDATE ON public.user_connections
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to user_connections';
    END IF;
END $$;

-- 5. bill_uploads
DROP TRIGGER IF EXISTS trg_bill_uploads_updated_at ON public.bill_uploads;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'bill_uploads' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_bill_uploads_updated_at
            BEFORE UPDATE ON public.bill_uploads
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to bill_uploads';
    END IF;
END $$;

-- 6. price_alert_configs
DROP TRIGGER IF EXISTS trg_price_alert_configs_updated_at ON public.price_alert_configs;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'price_alert_configs' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_price_alert_configs_updated_at
            BEFORE UPDATE ON public.price_alert_configs
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to price_alert_configs';
    END IF;
END $$;

-- 7. feature_flags
DROP TRIGGER IF EXISTS trg_feature_flags_updated_at ON public.feature_flags;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'feature_flags' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_feature_flags_updated_at
            BEFORE UPDATE ON public.feature_flags
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to feature_flags';
    END IF;
END $$;

-- 8. payment_retry_history
DROP TRIGGER IF EXISTS trg_payment_retry_history_updated_at ON public.payment_retry_history;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'payment_retry_history' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_payment_retry_history_updated_at
            BEFORE UPDATE ON public.payment_retry_history
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to payment_retry_history';
    END IF;
END $$;

-- 9. model_config
DROP TRIGGER IF EXISTS trg_model_config_updated_at ON public.model_config;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'model_config' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_model_config_updated_at
            BEFORE UPDATE ON public.model_config
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to model_config';
    END IF;
END $$;

-- 10. feedback
DROP TRIGGER IF EXISTS trg_feedback_updated_at ON public.feedback;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'feedback' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_feedback_updated_at
            BEFORE UPDATE ON public.feedback
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to feedback';
    END IF;
END $$;

-- 11. utility_accounts
DROP TRIGGER IF EXISTS trg_utility_accounts_updated_at ON public.utility_accounts;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'utility_accounts' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_utility_accounts_updated_at
            BEFORE UPDATE ON public.utility_accounts
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to utility_accounts';
    END IF;
END $$;

-- 12. community_solar_programs
DROP TRIGGER IF EXISTS trg_community_solar_programs_updated_at ON public.community_solar_programs;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'community_solar_programs' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_community_solar_programs_updated_at
            BEFORE UPDATE ON public.community_solar_programs
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to community_solar_programs';
    END IF;
END $$;

-- 13. cca_programs
DROP TRIGGER IF EXISTS trg_cca_programs_updated_at ON public.cca_programs;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'cca_programs' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_cca_programs_updated_at
            BEFORE UPDATE ON public.cca_programs
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to cca_programs';
    END IF;
END $$;

-- 14. user_alert_configs (multi-utility alerts, migration 044)
DROP TRIGGER IF EXISTS trg_user_alert_configs_updated_at ON public.user_alert_configs;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_alert_configs' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_user_alert_configs_updated_at
            BEFORE UPDATE ON public.user_alert_configs
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to user_alert_configs';
    END IF;
END $$;

-- 15. water_rates_config (migration 047)
DROP TRIGGER IF EXISTS trg_water_rates_config_updated_at ON public.water_rates_config;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'water_rates_config' AND column_name = 'updated_at'
    ) THEN
        CREATE TRIGGER trg_water_rates_config_updated_at
            BEFORE UPDATE ON public.water_rates_config
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        RAISE NOTICE 'Migration 060: trigger added to water_rates_config';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- Grants on the trigger function
-- ---------------------------------------------------------------------------

GRANT EXECUTE ON FUNCTION public.update_updated_at_column() TO neondb_owner;


-- ---------------------------------------------------------------------------
-- Completion notice
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    RAISE NOTICE 'Migration 060 complete: updated_at auto-update triggers applied to 15 tables.';
END $$;
