-- Migration 025: Data cache tables for weather, market intelligence, and scraped rates
-- These tables persist data fetched by GHA cron workflows that was previously discarded.

-- Weather cache: stores OpenWeather data for ML features
CREATE TABLE IF NOT EXISTS weather_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_code      VARCHAR(2) NOT NULL,
    temperature_f   DECIMAL(5,1),
    humidity        INT,
    wind_speed_mph  DECIMAL(5,1),
    conditions      VARCHAR(100),
    raw_data        JSONB DEFAULT '{}',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_weather_cache_state_time ON weather_cache (state_code, fetched_at DESC);

-- Market intelligence: stores Tavily search results
CREATE TABLE IF NOT EXISTS market_intelligence (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query           VARCHAR(500) NOT NULL,
    region          VARCHAR(50),
    title           VARCHAR(500),
    url             VARCHAR(1000),
    content         TEXT,
    score           DECIMAL(5,3),
    raw_data        JSONB DEFAULT '{}',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_intel_region_time ON market_intelligence (region, fetched_at DESC);

-- Scraped rates: stores Diffbot-extracted supplier rate data
CREATE TABLE IF NOT EXISTS scraped_rates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id     UUID REFERENCES supplier_registry(id),
    supplier_name   VARCHAR(200),
    source_url      VARCHAR(1000),
    extracted_data  JSONB DEFAULT '{}',
    success         BOOLEAN NOT NULL DEFAULT TRUE,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scraped_rates_supplier_time ON scraped_rates (supplier_id, fetched_at DESC);

GRANT ALL ON weather_cache, market_intelligence, scraped_rates TO neondb_owner;
