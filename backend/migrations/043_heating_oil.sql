-- Migration 043: Heating Oil Prices & Dealer Directory
-- Supports weekly EIA price tracking for 9 Northeast states + national average,
-- plus a curated dealer directory.

-- =============================================================================
-- 1. Heating oil prices table
-- =============================================================================

CREATE TABLE IF NOT EXISTS heating_oil_prices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state           VARCHAR(2) NOT NULL,          -- 2-letter state code or 'US' for national
    price_per_gallon DECIMAL(6,4) NOT NULL,       -- $/gallon
    source          VARCHAR(50) NOT NULL DEFAULT 'eia',
    period_date     DATE NOT NULL,                -- week ending date from EIA
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_heating_oil_state_period UNIQUE (state, period_date)
);

CREATE INDEX IF NOT EXISTS idx_heating_oil_state ON heating_oil_prices (state);
CREATE INDEX IF NOT EXISTS idx_heating_oil_fetched ON heating_oil_prices (fetched_at DESC);

-- =============================================================================
-- 2. Heating oil dealers table
-- =============================================================================

CREATE TABLE IF NOT EXISTS heating_oil_dealers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    state           VARCHAR(2) NOT NULL,
    city            VARCHAR(100),
    phone           VARCHAR(30),
    website         VARCHAR(500),
    rating          DECIMAL(3,2),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dealers_state ON heating_oil_dealers (state);
CREATE INDEX IF NOT EXISTS idx_dealers_active ON heating_oil_dealers (is_active) WHERE is_active = TRUE;

-- =============================================================================
-- 3. Seed top dealers for Northeast states
-- =============================================================================

INSERT INTO heating_oil_dealers (name, state, city, phone, website, rating) VALUES
    -- Connecticut
    ('Hocon Gas', 'CT', 'Danbury', '203-744-0555', 'https://hocongas.com', 4.5),
    ('Santa Energy', 'CT', 'Bridgeport', '203-367-3341', 'https://santaenergy.com', 4.3),
    -- Massachusetts
    ('Petro Home Services', 'MA', 'Boston', '800-645-4328', 'https://petrohomeservices.com', 4.2),
    ('Cubby Oil', 'MA', 'Springfield', '413-732-4151', 'https://cubbyoil.com', 4.4),
    -- New York
    ('Metro Energy', 'NY', 'New York', '212-475-5800', 'https://metroenergy.com', 4.1),
    ('Petro Home Services NY', 'NY', 'Long Island', '800-645-4328', 'https://petrohomeservices.com', 4.2),
    -- New Jersey
    ('Woodhull Fuel', 'NJ', 'Princeton', '609-924-0033', 'https://woodhullfuel.com', 4.6),
    ('Sippin Energy', 'NJ', 'Montclair', '973-744-0770', 'https://sippinenergy.com', 4.3),
    -- Pennsylvania
    ('Suburban Propane', 'PA', 'Philadelphia', '800-776-7263', 'https://suburbanpropane.com', 4.0),
    ('Penn Jersey Oil', 'PA', 'Allentown', '610-433-4357', NULL, 4.1),
    -- Maine
    ('Dead River Company', 'ME', 'Portland', '800-244-7511', 'https://deadriver.com', 4.5),
    ('Downeast Energy', 'ME', 'Brunswick', '207-729-9946', 'https://downeastenergy.com', 4.3),
    -- New Hampshire
    ('Rymes Propane & Oil', 'NH', 'Concord', '603-224-9700', 'https://rfrymes.com', 4.4),
    -- Vermont
    ('Dead River Company VT', 'VT', 'Burlington', '800-244-7511', 'https://deadriver.com', 4.5),
    -- Rhode Island
    ('Star Gas Partners', 'RI', 'Providence', '401-421-0500', 'https://stargas.com', 4.0)
ON CONFLICT DO NOTHING;

-- =============================================================================
-- 4. Permissions
-- =============================================================================

GRANT ALL ON heating_oil_prices TO neondb_owner;
GRANT ALL ON heating_oil_dealers TO neondb_owner;
