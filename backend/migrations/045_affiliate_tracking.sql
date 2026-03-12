-- Migration 045: Affiliate click tracking
-- Tracks user clicks on supplier switch CTAs for revenue attribution.

CREATE TABLE IF NOT EXISTS affiliate_clicks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    supplier_id UUID,
    supplier_name VARCHAR(200),
    utility_type VARCHAR(30) NOT NULL,
    region VARCHAR(10),
    source_page VARCHAR(200),
    affiliate_url TEXT,
    clicked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    converted BOOLEAN DEFAULT FALSE,
    converted_at TIMESTAMPTZ,
    commission_cents INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_user
    ON affiliate_clicks (user_id, clicked_at DESC);
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_supplier
    ON affiliate_clicks (supplier_id, clicked_at DESC);
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_utility
    ON affiliate_clicks (utility_type, clicked_at DESC);

GRANT ALL ON affiliate_clicks TO neondb_owner;
