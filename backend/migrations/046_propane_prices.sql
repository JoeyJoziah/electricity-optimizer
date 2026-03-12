-- Migration 046: Propane price tracking
-- Weekly propane prices from EIA (national + 8 Northeast states).

CREATE TABLE IF NOT EXISTS propane_prices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state VARCHAR(5) NOT NULL,
    price_per_gallon NUMERIC(8, 4) NOT NULL,
    source VARCHAR(50) NOT NULL DEFAULT 'eia',
    period_date DATE NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (state, period_date)
);

CREATE INDEX IF NOT EXISTS idx_propane_prices_state
    ON propane_prices (state, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_propane_prices_period
    ON propane_prices (period_date DESC);

GRANT ALL ON propane_prices TO neondb_owner;
