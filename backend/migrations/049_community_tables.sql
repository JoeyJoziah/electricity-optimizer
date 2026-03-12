-- Migration 049: Community tables (3 new tables, 42 → 45 total)
-- Supports community posts, voting, and reporting for Wave 5 community features.
-- Region uses VARCHAR(50) matching existing Region enum values (not PostgreSQL enum type).
-- No denormalized counters — upvotes and report counts derived via COUNT(*).

CREATE TABLE IF NOT EXISTS community_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    region VARCHAR(50) NOT NULL,
    utility_type VARCHAR(30) NOT NULL CHECK (utility_type IN (
        'electricity', 'natural_gas', 'heating_oil', 'propane',
        'community_solar', 'water', 'general'
    )),
    post_type VARCHAR(20) NOT NULL CHECK (post_type IN ('tip', 'rate_report', 'discussion', 'review')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    rate_per_unit NUMERIC(10,6),
    rate_unit VARCHAR(10),
    supplier_name TEXT,
    is_hidden BOOLEAN DEFAULT false,
    is_pending_moderation BOOLEAN DEFAULT true,
    hidden_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS community_votes (
    user_id UUID NOT NULL REFERENCES users(id),
    post_id UUID NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, post_id)
);

CREATE TABLE IF NOT EXISTS community_reports (
    user_id UUID NOT NULL REFERENCES users(id),
    post_id UUID NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, post_id)
);

-- Composite index for filtered queries (region + utility_type + recency, excluding hidden)
CREATE INDEX IF NOT EXISTS idx_community_posts_region_utility
    ON community_posts (region, utility_type, created_at DESC)
    WHERE is_hidden = false;

-- Index for user's own posts (profile view, edit/resubmit)
CREATE INDEX IF NOT EXISTS idx_community_posts_user
    ON community_posts (user_id, created_at DESC);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_community_posts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_community_posts_updated_at
    BEFORE UPDATE ON community_posts
    FOR EACH ROW EXECUTE FUNCTION update_community_posts_updated_at();

-- Grants
GRANT ALL ON community_posts TO neondb_owner;
GRANT ALL ON community_votes TO neondb_owner;
GRANT ALL ON community_reports TO neondb_owner;
