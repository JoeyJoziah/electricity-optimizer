-- Migration 006: Multi-State, Multi-Utility Expansion
-- Adds utility_type support, supplier registry, and state regulation tracking.

-- =============================================================================
-- 1. Create utility_type enum
-- =============================================================================

DO $$ BEGIN
    CREATE TYPE utility_type AS ENUM (
        'electricity',
        'natural_gas',
        'heating_oil',
        'propane',
        'community_solar'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- =============================================================================
-- 2. Add utility_type to existing tables
-- =============================================================================

ALTER TABLE electricity_prices
    ADD COLUMN IF NOT EXISTS utility_type utility_type NOT NULL DEFAULT 'electricity';

ALTER TABLE suppliers
    ADD COLUMN IF NOT EXISTS utility_types utility_type[] NOT NULL DEFAULT '{electricity}';

ALTER TABLE tariffs
    ADD COLUMN IF NOT EXISTS utility_type utility_type NOT NULL DEFAULT 'electricity';

-- =============================================================================
-- 3. Create supplier_registry table (replaces mock data)
-- =============================================================================

CREATE TABLE IF NOT EXISTS supplier_registry (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    utility_types   utility_type[] NOT NULL DEFAULT '{electricity}',
    regions         TEXT[] NOT NULL,
    website         VARCHAR(500),
    phone           VARCHAR(50),
    api_available   BOOLEAN NOT NULL DEFAULT FALSE,
    rating          DECIMAL(3,2),
    review_count    INT DEFAULT 0,
    green_energy    BOOLEAN NOT NULL DEFAULT FALSE,
    carbon_neutral  BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_supplier_reg_regions ON supplier_registry USING GIN (regions);
CREATE INDEX IF NOT EXISTS idx_supplier_reg_utility ON supplier_registry USING GIN (utility_types);
CREATE INDEX IF NOT EXISTS idx_supplier_reg_active ON supplier_registry (is_active) WHERE is_active = TRUE;

-- =============================================================================
-- 4. Create state_regulations table
-- =============================================================================

CREATE TABLE IF NOT EXISTS state_regulations (
    state_code              VARCHAR(2) PRIMARY KEY,
    state_name              VARCHAR(50) NOT NULL,
    electricity_deregulated BOOLEAN NOT NULL DEFAULT FALSE,
    gas_deregulated         BOOLEAN NOT NULL DEFAULT FALSE,
    oil_competitive         BOOLEAN NOT NULL DEFAULT FALSE,
    community_solar_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    licensing_required      BOOLEAN NOT NULL DEFAULT FALSE,
    bond_required           BOOLEAN NOT NULL DEFAULT FALSE,
    bond_amount             DECIMAL(12,2),
    puc_name                VARCHAR(200),
    puc_website             VARCHAR(500),
    comparison_tool_url     VARCHAR(500),
    notes                   TEXT,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- 5. Add index on utility_type for existing tables
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_prices_utility_type
    ON electricity_prices (utility_type);

CREATE INDEX IF NOT EXISTS idx_prices_region_utility
    ON electricity_prices (region, utility_type, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_tariffs_utility_type
    ON tariffs (utility_type);

-- =============================================================================
-- 6. Seed supplier_registry with existing CT suppliers
-- =============================================================================

INSERT INTO supplier_registry (name, utility_types, regions, website, api_available, rating, green_energy, is_active)
VALUES
    ('Eversource Energy', '{electricity,natural_gas}', '{us_ct,us_ma,us_nh}',
     'https://www.eversource.com', TRUE, 4.2, TRUE, TRUE),
    ('United Illuminating (UI)', '{electricity}', '{us_ct}',
     'https://www.uinet.com', TRUE, 3.8, FALSE, TRUE),
    ('NextEra Energy', '{electricity}', '{us_ct,us_ny,us_fl}',
     'https://www.nexteraenergy.com', TRUE, 4.0, TRUE, TRUE)
ON CONFLICT DO NOTHING;

-- =============================================================================
-- 7. Seed state_regulations for key deregulated states
-- =============================================================================

INSERT INTO state_regulations (state_code, state_name, electricity_deregulated, gas_deregulated, oil_competitive, community_solar_enabled, licensing_required, bond_required, bond_amount, puc_name, puc_website, comparison_tool_url) VALUES
-- Tier 1: Current + Largest deregulated markets
('CT', 'Connecticut', TRUE, TRUE, TRUE, TRUE, FALSE, FALSE, NULL, 'PURA', 'https://portal.ct.gov/pura', NULL),
('TX', 'Texas', TRUE, FALSE, FALSE, TRUE, TRUE, TRUE, 50000, 'PUCT', 'https://www.puc.texas.gov', 'https://www.powertochoose.org'),
('OH', 'Ohio', TRUE, TRUE, FALSE, TRUE, TRUE, FALSE, NULL, 'PUCO', 'https://puco.ohio.gov', 'https://www.energychoice.ohio.gov'),
('PA', 'Pennsylvania', TRUE, TRUE, FALSE, TRUE, TRUE, TRUE, 25000, 'PUC', 'https://www.puc.pa.gov', 'https://www.papowerswitch.com'),
('IL', 'Illinois', TRUE, TRUE, FALSE, TRUE, TRUE, FALSE, NULL, 'ICC', 'https://www.icc.illinois.gov', 'https://www.pluginillinois.org'),
('NY', 'New York', TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, NULL, 'PSC', 'https://www.dps.ny.gov', 'https://www.askpsc.com'),
('NJ', 'New Jersey', TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, NULL, 'BPU', 'https://www.nj.gov/bpu', NULL),
-- Tier 2: High-rate, underserved NE markets
('MA', 'Massachusetts', TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, NULL, 'DPU', 'https://www.mass.gov/orgs/dpu', 'https://www.energyswitchma.gov'),
('MD', 'Maryland', TRUE, TRUE, FALSE, TRUE, TRUE, FALSE, NULL, 'PSC', 'https://www.psc.state.md.us', 'https://www.mdelectricchoice.com'),
('RI', 'Rhode Island', TRUE, TRUE, TRUE, FALSE, FALSE, FALSE, NULL, 'PUC', 'https://www.ripuc.ri.gov', NULL),
('NH', 'New Hampshire', TRUE, FALSE, TRUE, FALSE, FALSE, FALSE, NULL, 'PUC', 'https://www.puc.nh.gov', 'https://www.puc.nh.gov/consumer'),
('ME', 'Maine', TRUE, FALSE, TRUE, TRUE, FALSE, FALSE, NULL, 'PUC', 'https://www.maine.gov/mpuc', NULL),
('DE', 'Delaware', TRUE, TRUE, FALSE, FALSE, TRUE, FALSE, NULL, 'PSC', 'https://depsc.delaware.gov', NULL),
-- Gas-only deregulated states (no electricity choice)
('GA', 'Georgia', FALSE, TRUE, FALSE, TRUE, FALSE, FALSE, NULL, 'PSC', 'https://psc.ga.gov', NULL),
('IN', 'Indiana', FALSE, TRUE, FALSE, FALSE, FALSE, FALSE, NULL, 'IURC', 'https://www.in.gov/iurc', NULL),
('KY', 'Kentucky', FALSE, TRUE, FALSE, FALSE, FALSE, FALSE, NULL, 'PSC', 'https://psc.ky.gov', NULL),
('FL', 'Florida', FALSE, TRUE, FALSE, TRUE, FALSE, FALSE, NULL, 'PSC', 'https://www.psc.state.fl.us', NULL),
-- Additional deregulated electricity states
('MI', 'Michigan', TRUE, TRUE, FALSE, TRUE, TRUE, FALSE, NULL, 'MPSC', 'https://www.michigan.gov/mpsc', NULL),
('VA', 'Virginia', TRUE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'SCC', 'https://scc.virginia.gov', NULL),
('DC', 'District of Columbia', TRUE, TRUE, FALSE, TRUE, TRUE, TRUE, 10000, 'PSC', 'https://dcpsc.org', NULL),
('OR', 'Oregon', TRUE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'PUC', 'https://www.oregon.gov/puc', NULL),
('MT', 'Montana', TRUE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'PSC', 'https://psc.mt.gov', NULL),
-- Large states (regulated electricity but important for gas/solar)
('CA', 'California', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'CPUC', 'https://www.cpuc.ca.gov', NULL),
('MN', 'Minnesota', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'PUC', 'https://mn.gov/puc', NULL),
-- Northeast heating oil states (non-deregulated elec)
('VT', 'Vermont', FALSE, FALSE, TRUE, TRUE, FALSE, FALSE, NULL, 'PUC', 'https://puc.vermont.gov', NULL),
-- Remaining states (regulated, minimal opportunity for now)
('AL', 'Alabama', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'PSC', 'https://www.psc.state.al.us', NULL),
('AK', 'Alaska', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'RCA', 'https://rca.alaska.gov', NULL),
('AZ', 'Arizona', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'ACC', 'https://www.azcc.gov', NULL),
('AR', 'Arkansas', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'PSC', 'https://www.arkansas.gov/psc', NULL),
('CO', 'Colorado', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'PUC', 'https://puc.colorado.gov', NULL),
('HI', 'Hawaii', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'PUC', 'https://puc.hawaii.gov', NULL),
('IA', 'Iowa', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'IUB', 'https://iub.iowa.gov', NULL),
('KS', 'Kansas', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'KCC', 'https://kcc.ks.gov', NULL),
('LA', 'Louisiana', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'LPSC', 'https://www.lpsc.louisiana.gov', NULL),
('MS', 'Mississippi', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'PSC', 'https://www.psc.ms.gov', NULL),
('MO', 'Missouri', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'PSC', 'https://psc.mo.gov', NULL),
('NE', 'Nebraska', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'NPP', 'https://www.neo.ne.gov', NULL),
('NV', 'Nevada', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'PUC', 'https://puc.nv.gov', NULL),
('NM', 'New Mexico', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'PRC', 'https://www.nmprc.state.nm.us', NULL),
('NC', 'North Carolina', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'UC', 'https://www.ncuc.net', NULL),
('ND', 'North Dakota', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'PSC', 'https://www.psc.nd.gov', NULL),
('OK', 'Oklahoma', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'OCC', 'https://oklahoma.gov/occ', NULL),
('SC', 'South Carolina', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'PSC', 'https://www.psc.sc.gov', NULL),
('SD', 'South Dakota', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'PUC', 'https://puc.sd.gov', NULL),
('TN', 'Tennessee', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'TRA', 'https://www.tn.gov/tra', NULL),
('UT', 'Utah', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'PSC', 'https://psc.utah.gov', NULL),
('WA', 'Washington', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'UTC', 'https://www.utc.wa.gov', NULL),
('WV', 'West Virginia', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'PSC', 'https://psc.wv.gov', NULL),
('WI', 'Wisconsin', FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, NULL, 'PSC', 'https://psc.wi.gov', NULL),
('WY', 'Wyoming', FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, NULL, 'PSC', 'https://psc.wyo.gov', NULL)
ON CONFLICT (state_code) DO NOTHING;

-- =============================================================================
-- 8. Grant permissions
-- =============================================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON supplier_registry TO neondb_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON state_regulations TO neondb_owner;
