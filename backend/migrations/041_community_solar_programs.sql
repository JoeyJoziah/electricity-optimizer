-- Migration 041: Community Solar Programs table
-- Stores community solar program listings by state for marketplace discovery.

CREATE TABLE IF NOT EXISTS community_solar_programs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state TEXT NOT NULL,
    program_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    savings_percent NUMERIC(5,2),
    capacity_kw NUMERIC(10,2),
    spots_available INTEGER,
    enrollment_url TEXT,
    enrollment_status TEXT NOT NULL DEFAULT 'open',
    description TEXT,
    min_bill_amount NUMERIC(8,2),
    contract_months INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT enrollment_status_check CHECK (enrollment_status IN ('open', 'waitlist', 'closed'))
);

CREATE INDEX IF NOT EXISTS idx_community_solar_state ON community_solar_programs (state);
CREATE INDEX IF NOT EXISTS idx_community_solar_enrollment ON community_solar_programs (enrollment_status);

-- Seed initial community solar programs for top 10 states
INSERT INTO community_solar_programs (state, program_name, provider, savings_percent, capacity_kw, spots_available, enrollment_url, enrollment_status, description, min_bill_amount, contract_months)
VALUES
    ('NY', 'NY Community Solar', 'Nexamp', 10.00, 5000.00, 150, 'https://www.nexamp.com/ny', 'open', 'Save 10% on your electricity bill with local solar farm subscription.', 50.00, 12),
    ('NY', 'Clean Choice Community Solar', 'CleanChoice Energy', 5.00, 3000.00, 80, 'https://cleanchoiceenergy.com/community-solar/ny', 'open', 'No rooftop panels needed. Subscribe to a local solar farm and save.', 40.00, NULL),
    ('MA', 'MA Community Shared Solar', 'Clearway Energy', 15.00, 4000.00, 120, 'https://www.clearwayenergy.com/community-solar', 'open', 'Massachusetts community solar credits applied directly to your bill.', 60.00, 24),
    ('MA', 'Eversource Solar MA', 'EnergySage', 12.00, 2500.00, 50, 'https://communitysolar.energysage.com/ma', 'waitlist', 'Join waitlist for Eversource territory community solar projects.', 45.00, 12),
    ('MN', 'Xcel Community Solar Garden', 'Xcel Energy', 8.00, 10000.00, 300, 'https://www.xcelenergy.com/community_solar', 'open', 'Minnesota pioneered community solar. Xcel manages the largest garden network.', 30.00, NULL),
    ('CO', 'Colorado Community Solar Gardens', 'SunShare', 10.00, 6000.00, 200, 'https://www.mysunshare.com', 'open', 'Lock in solar savings with no upfront cost in Colorado.', 50.00, 12),
    ('IL', 'Illinois Shines Community Solar', 'Trajectory Energy', 15.00, 3500.00, 100, 'https://www.trajectoryenergy.com', 'open', 'Illinois Shines program delivers guaranteed savings on electricity.', 40.00, 24),
    ('NJ', 'NJ Community Solar Energy Pilot', 'Summit Ridge Energy', 20.00, 5000.00, 75, 'https://www.srenergy.com/new-jersey', 'open', 'New Jersey pilot program offering up to 20% bill savings.', 50.00, 12),
    ('MD', 'Maryland Community Solar', 'Neighborhood Sun', 10.00, 2000.00, 60, 'https://www.neighborhoodsun.com', 'open', 'Subscribe to local solar and save on your BGE or Pepco bill.', 35.00, NULL),
    ('ME', 'Maine Community Solar', 'ReVision Energy', 10.00, 1500.00, 40, 'https://www.revisionenergy.com/community-solar', 'open', 'Maine residents can benefit from community solar farm credits.', 30.00, 12),
    ('CT', 'CT Shared Clean Energy', 'Arcadia', 5.00, 2500.00, 90, 'https://www.arcadia.com/community-solar/ct', 'open', 'Connecticut shared clean energy facility credits on your bill.', 40.00, NULL),
    ('CA', 'CPUC Community Solar', 'MCE Clean Energy', 8.00, 8000.00, 500, 'https://www.mcecleanenergy.org/community-solar', 'open', 'California community solar for renters and homeowners alike.', 60.00, NULL),
    ('OR', 'Oregon Community Solar', 'Pine Gate Renewables', 10.00, 3000.00, 100, 'https://www.pinegaterenewables.com', 'waitlist', 'Oregon community solar program with bill credit savings.', 45.00, 12),
    ('FL', 'FPL SolarTogether', 'Florida Power & Light', 5.00, 15000.00, 1000, 'https://www.fpl.com/solartogether', 'open', 'FPL SolarTogether: affordable solar for all FPL customers.', 30.00, NULL),
    ('VA', 'Virginia Shared Solar', 'Dominion Energy', 10.00, 4000.00, 150, 'https://www.dominionenergy.com/sharedsolar', 'open', 'Dominion shared solar program for Virginia residents.', 50.00, 12)
ON CONFLICT DO NOTHING;

GRANT SELECT, INSERT, UPDATE, DELETE ON community_solar_programs TO neondb_owner;
