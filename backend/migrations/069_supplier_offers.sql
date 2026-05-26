-- 069_supplier_offers.sql
-- Vendor-neutral supplier pricing read model.
--
-- The /suppliers and /suppliers/recommend endpoints must show real, source-
-- agnostic pricing without coupling to any single provider. supplier_offers is
-- the canonical store that pluggable source adapters (regional_estimate,
-- ct_rate_board, arcadia, energybot, manual) all write into in one normalized
-- shape, and that the read path consumes without knowing the source.
--
-- This supersedes the legacy `tariffs` table (supplier-keyed, no region/
-- provenance/lifecycle) which is left in place but DEPRECATED — do not add new
-- writers to it.

CREATE TABLE IF NOT EXISTS supplier_offers (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Where the offer applies.
    region             TEXT          NOT NULL,                       -- e.g. 'us_ct'
    zip_code           TEXT          NULL,                           -- optional finer grain (zip-keyed sources)
    utility_type       utility_type  NOT NULL DEFAULT 'electricity',
    utility_territory  TEXT          NULL,                           -- e.g. 'Eversource' / 'United Illuminating'

    -- Who is offering. supplier_id is nullable: some offers' suppliers may not
    -- be in supplier_registry. supplier_name is denormalized for display.
    supplier_id        UUID          NULL REFERENCES supplier_registry(id) ON DELETE SET NULL,
    supplier_name      TEXT          NOT NULL,

    -- Rate structure (a single rate is insufficient — intro/variable/fees matter).
    rate_per_kwh       NUMERIC(12, 6) NOT NULL CHECK (rate_per_kwh >= 0),
    standing_charge    NUMERIC(12, 6) NOT NULL DEFAULT 0 CHECK (standing_charge >= 0),
    tariff_type        TEXT          NOT NULL DEFAULT 'fixed',       -- fixed | variable | fixed_tiered
    intro_term_months  INT           NULL,
    post_intro_rate    NUMERIC(12, 6) NULL,
    cancellation_fee   NUMERIC(12, 2) NULL,
    enrollment_fee     NUMERIC(12, 2) NULL,
    renewable_pct      INT           NULL,
    enroll_url         TEXT          NULL,

    -- Provenance + lifecycle.
    source             TEXT          NOT NULL,                       -- 'regional_estimate'|'ct_rate_board'|'arcadia'|'energybot'|'manual'
    source_ref         TEXT          NULL,                           -- external id from the source
    is_estimate        BOOLEAN       NOT NULL DEFAULT FALSE,         -- true = derived/uniform, not an obtainable offer
    is_available       BOOLEAN       NOT NULL DEFAULT TRUE,
    effective_date     DATE          NULL,
    expires_at         DATE          NULL,
    fetched_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
    raw                JSONB         NULL
);

-- Primary read pattern: cheapest available per region/utility.
CREATE INDEX IF NOT EXISTS idx_offers_region_util
    ON supplier_offers (region, utility_type, is_available);

-- Lookups by supplier (recommendation: current vs alternatives).
CREATE INDEX IF NOT EXISTS idx_offers_supplier
    ON supplier_offers (supplier_id);

-- Idempotent upserts from sources that carry a stable external id.
CREATE UNIQUE INDEX IF NOT EXISTS uq_offers_source_ref
    ON supplier_offers (source, source_ref, region)
    WHERE source_ref IS NOT NULL;
