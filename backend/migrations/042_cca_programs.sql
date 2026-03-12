-- Migration 042: Community Choice Aggregation (CCA) programs table
-- Stores CCA program data by municipality for detection and rate comparison.

CREATE TABLE IF NOT EXISTS cca_programs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state TEXT NOT NULL,
    municipality TEXT NOT NULL,
    zip_codes TEXT[] NOT NULL DEFAULT '{}',
    program_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    generation_mix JSONB,
    rate_vs_default_pct NUMERIC(5,2),
    opt_out_url TEXT,
    program_url TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT cca_status_check CHECK (status IN ('active', 'inactive', 'pending'))
);

CREATE INDEX IF NOT EXISTS idx_cca_state ON cca_programs (state);
CREATE INDEX IF NOT EXISTS idx_cca_municipality ON cca_programs (state, municipality);
CREATE INDEX IF NOT EXISTS idx_cca_zip ON cca_programs USING gin (zip_codes);
CREATE INDEX IF NOT EXISTS idx_cca_status ON cca_programs (status);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON cca_programs TO neondb_owner;

-- Seed CCA programs for top 10 states
INSERT INTO cca_programs (state, municipality, zip_codes, program_name, provider, generation_mix, rate_vs_default_pct, opt_out_url, program_url, status)
VALUES
    -- California
    ('CA', 'San Jose', ARRAY['95101','95102','95103','95110','95112'], 'San Jose Clean Energy', 'City of San Jose', '{"solar": 40, "wind": 30, "hydro": 20, "other": 10}', -5.00, 'https://sanjosecleanenergy.org/opt-out', 'https://sanjosecleanenergy.org', 'active'),
    ('CA', 'Los Angeles', ARRAY['90001','90002','90003','90004','90005'], 'Clean Power Alliance', 'Clean Power Alliance', '{"solar": 50, "wind": 35, "hydro": 10, "other": 5}', -3.00, 'https://cleanpoweralliance.org/opt-out', 'https://cleanpoweralliance.org', 'active'),
    ('CA', 'San Francisco', ARRAY['94102','94103','94104','94105','94107'], 'CleanPowerSF', 'SF Public Utilities Commission', '{"solar": 45, "wind": 40, "hydro": 10, "other": 5}', -2.00, 'https://cleanpowersf.org/opt-out', 'https://cleanpowersf.org', 'active'),
    -- Massachusetts
    ('MA', 'Somerville', ARRAY['02143','02144','02145'], 'Somerville Community Choice Electricity', 'Dynegy', '{"wind": 50, "solar": 30, "hydro": 15, "other": 5}', -8.00, 'https://somervillecce.com/opt-out', 'https://somervillecce.com', 'active'),
    ('MA', 'Cambridge', ARRAY['02138','02139','02140','02141','02142'], 'Cambridge Community Electricity', 'Constellation', '{"wind": 45, "solar": 35, "hydro": 15, "other": 5}', -6.00, 'https://masspowerchoice.com/cambridge/opt-out', 'https://masspowerchoice.com/cambridge', 'active'),
    -- New York
    ('NY', 'Westchester County', ARRAY['10501','10502','10503','10504','10505'], 'Westchester Power', 'Sustainable Westchester', '{"wind": 40, "solar": 30, "hydro": 20, "other": 10}', -4.00, 'https://westchesterpower.org/opt-out', 'https://westchesterpower.org', 'active'),
    ('NY', 'Long Island', ARRAY['11001','11003','11010','11020','11030'], 'Long Island Community Choice', 'LIPA CCA Program', '{"solar": 35, "wind": 35, "hydro": 20, "other": 10}', -3.00, NULL, 'https://lipower.org/cca', 'active'),
    -- New Jersey
    ('NJ', 'Princeton', ARRAY['08540','08541','08542','08543','08544'], 'Princeton Community Energy Aggregation', 'Constellation', '{"wind": 50, "solar": 25, "hydro": 15, "other": 10}', -7.00, 'https://princetonnj.gov/cca/opt-out', 'https://princetonnj.gov/cca', 'active'),
    -- Illinois
    ('IL', 'Chicago Suburbs', ARRAY['60101','60103','60106','60108','60110'], 'Northern Illinois CCA', 'MC Squared Energy', '{"wind": 55, "solar": 20, "natural_gas": 15, "other": 10}', -5.00, NULL, 'https://www.mc2energyservices.com', 'active'),
    -- Ohio
    ('OH', 'Columbus Area', ARRAY['43001','43002','43004','43015','43016'], 'Central Ohio Energy Aggregation', 'AEP Energy', '{"natural_gas": 40, "wind": 30, "solar": 20, "other": 10}', -4.00, NULL, 'https://www.aepenergy.com', 'active'),
    -- New Hampshire
    ('NH', 'Nashua', ARRAY['03060','03061','03062','03063','03064'], 'Nashua Community Power', 'City of Nashua', '{"hydro": 40, "wind": 35, "solar": 20, "other": 5}', -6.00, 'https://nashuacommunitypower.com/opt-out', 'https://nashuacommunitypower.com', 'active'),
    -- Virginia
    ('VA', 'Fairfax County', ARRAY['22030','22031','22032','22033','22035'], 'Fairfax County Community Choice', 'Dominion Energy', '{"solar": 30, "wind": 25, "natural_gas": 30, "other": 15}', -2.00, NULL, 'https://www.fairfaxcounty.gov/energy', 'pending'),
    -- Rhode Island
    ('RI', 'Providence', ARRAY['02901','02902','02903','02904','02905'], 'Providence Community Choice', 'National Grid', '{"wind": 45, "solar": 30, "hydro": 15, "other": 10}', -5.00, 'https://www.providenceri.gov/cca/opt-out', 'https://www.providenceri.gov/cca', 'active'),
    -- Colorado
    ('CO', 'Boulder', ARRAY['80301','80302','80303','80304','80305'], 'Boulder Energy Future', 'City of Boulder', '{"solar": 50, "wind": 30, "hydro": 15, "other": 5}', -4.00, NULL, 'https://bouldercolorado.gov/energy', 'active');
