-- Migration 047: Water rate benchmarking
-- Municipal water rates for top 50 US metros. Monitoring only (no switch CTA).
-- Rate tiers stored as JSONB array: [{"limit_gallons": 3000, "rate_per_gallon": 0.005}, ...]

CREATE TABLE IF NOT EXISTS water_rates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    municipality VARCHAR(100) NOT NULL,
    state VARCHAR(2) NOT NULL,
    rate_tiers JSONB NOT NULL DEFAULT '[]'::jsonb,
    base_charge NUMERIC(8, 2) NOT NULL DEFAULT 0,
    unit VARCHAR(20) NOT NULL DEFAULT 'gallon',
    effective_date DATE,
    source_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (municipality, state)
);

CREATE INDEX IF NOT EXISTS idx_water_rates_state
    ON water_rates (state);
CREATE INDEX IF NOT EXISTS idx_water_rates_municipality
    ON water_rates (municipality, state);

GRANT ALL ON water_rates TO neondb_owner;
