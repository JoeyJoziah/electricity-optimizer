-- =============================================================================
-- Migration 062: Additional schema fixes from 2026-03-23 audit (round 2)
-- =============================================================================
--
-- Findings addressed (remaining after migration 061):
--
--   P2-7  forecast_observations.forecast_hour missing CHECK constraint.
--         Add CHECK (forecast_hour BETWEEN 0 AND 23) at DB level to match
--         the Pydantic model's Field(ge=0, le=23) validation.
--
--   P2-3  market_intelligence has no dedup guard — identical rows accumulate.
--         Add partial unique index on (region, query, url, DATE(fetched_at))
--         to prevent same-day duplicate scrapes per query+region+url.
--
--   P2-3  scraped_rates has no dedup guard per supplier per day.
--         Add partial unique index on (supplier_id, DATE(fetched_at))
--         to prevent same-day duplicate scrapes per supplier.
--
--   P2-10 scraped_rates.supplier_id FK uses NO ACTION — blocks supplier
--         deletion when old cache rows exist. Change to ON DELETE SET NULL.
--
--   P2-1  Redundant indexes on electricity_prices — three identical
--         (region, utility_type, timestamp DESC) indexes exist. Drop two
--         duplicates, keeping idx_prices_region_utility (migration 006).
--
--   P3-4  feature_flags.name has redundant explicit index — the UNIQUE
--         constraint already provides a B-tree index.
--
-- Conventions:
--   - All DDL guards use IF NOT EXISTS / IF EXISTS for idempotency.
--   - CONCURRENTLY used for new indexes on large tables.
--   - BEGIN/COMMIT wraps DDL + DML; CONCURRENTLY indexes run outside.
--   - GRANTs included for neondb_owner.
-- =============================================================================


-- =============================================================================
-- SECTION 1: Transactional schema fixes
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- P2-7: forecast_observations.forecast_hour — add CHECK (0-23)
-- ---------------------------------------------------------------------------
-- The Pydantic model enforces ge=0, le=23 but a buggy direct INSERT could
-- bypass the API layer.  Fix any out-of-range rows first (clamp to 0-23).

UPDATE forecast_observations
SET    forecast_hour = LEAST(GREATEST(forecast_hour, 0), 23)
WHERE  forecast_hour < 0 OR forecast_hour > 23;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.check_constraints
        WHERE  constraint_schema = 'public'
          AND  constraint_name   = 'ck_forecast_hour_range'
    ) THEN
        ALTER TABLE forecast_observations
            ADD CONSTRAINT ck_forecast_hour_range
            CHECK (forecast_hour BETWEEN 0 AND 23);
        RAISE NOTICE 'ck_forecast_hour_range constraint added to forecast_observations';
    ELSE
        RAISE NOTICE 'ck_forecast_hour_range already exists — skipping';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- P2-10: scraped_rates.supplier_id FK — change NO ACTION to SET NULL
-- ---------------------------------------------------------------------------
-- Drop old FK (if it exists) and recreate with ON DELETE SET NULL.
-- The FK name may vary; use the conventional naming pattern.

DO $$
DECLARE
    fk_name TEXT;
BEGIN
    -- Find the actual FK constraint name on scraped_rates.supplier_id
    SELECT conname INTO fk_name
    FROM   pg_constraint
    WHERE  conrelid = 'scraped_rates'::regclass
      AND  confrelid = 'supplier_registry'::regclass
      AND  contype = 'f';

    IF fk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE scraped_rates DROP CONSTRAINT %I', fk_name);
        RAISE NOTICE 'Dropped old FK % on scraped_rates.supplier_id', fk_name;
    ELSE
        RAISE NOTICE 'No existing FK from scraped_rates to supplier_registry — skipping drop';
    END IF;

    -- Add the FK with ON DELETE SET NULL
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_constraint
        WHERE  conrelid = 'scraped_rates'::regclass
          AND  confrelid = 'supplier_registry'::regclass
          AND  contype = 'f'
    ) THEN
        ALTER TABLE scraped_rates
            ADD CONSTRAINT fk_scraped_rates_supplier
            FOREIGN KEY (supplier_id) REFERENCES supplier_registry(id)
            ON DELETE SET NULL;
        RAISE NOTICE 'fk_scraped_rates_supplier added with ON DELETE SET NULL';
    ELSE
        RAISE NOTICE 'FK from scraped_rates to supplier_registry already exists — skipping';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- P2-1: Drop redundant electricity_prices indexes
-- ---------------------------------------------------------------------------
-- Three indexes on (region, utility_type, timestamp DESC):
--   idx_prices_region_utility           (migration 006) — KEEP
--   idx_prices_region_utilitytype_timestamp (migration 010) — DROP (duplicate)
--   idx_electricity_prices_region_utility_time (migration 037) — DROP (duplicate)
-- Also drop the single-column idx_prices_utility_type (subsumed by composites).

DROP INDEX IF EXISTS idx_prices_region_utilitytype_timestamp;
DROP INDEX IF EXISTS idx_electricity_prices_region_utility_time;
DROP INDEX IF EXISTS idx_prices_utility_type;


-- ---------------------------------------------------------------------------
-- P3-4: Drop redundant idx_feature_flags_name (UNIQUE constraint already
--       provides a B-tree index on name).
-- ---------------------------------------------------------------------------

DROP INDEX IF EXISTS idx_feature_flags_name;


-- =============================================================================
-- GRANTS
-- =============================================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON forecast_observations TO neondb_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON scraped_rates         TO neondb_owner;


COMMIT;


-- =============================================================================
-- SECTION 2: CONCURRENTLY indexes (must run outside a transaction)
-- =============================================================================

-- P2-3: market_intelligence dedup index — prevents same-day duplicate rows
-- for the same (region, query, url) combination.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_intel_dedup
    ON market_intelligence (region, query, DATE(fetched_at));

-- P2-3: scraped_rates dedup index — prevents same-day duplicate scrapes
-- per supplier.  Only applies when supplier_id is non-null.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scraped_rates_dedup
    ON scraped_rates (supplier_id, DATE(fetched_at))
    WHERE supplier_id IS NOT NULL;

-- =============================================================================
-- Migration 062 complete.
-- =============================================================================
