-- Migration 050: Optimized partial indexes for community_posts
-- Addresses: list_posts query scanning posts WHERE is_hidden = false AND is_pending_moderation = false
-- and retroactive_moderate scanning posts needing re-moderation.
--
-- Uses CONCURRENTLY to avoid locking the table during index creation.

-- Drop the old partial index that only covers is_hidden
DROP INDEX IF EXISTS idx_community_posts_region_utility;

-- Composite partial index for list_posts (covers region + utility_type + created_at ordering)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_community_posts_visible
    ON community_posts (region, utility_type, created_at DESC)
    WHERE is_hidden = false AND is_pending_moderation = false;

-- Partial index for retroactive_moderate (posts that timed out and need re-checking)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_community_posts_needs_remoderation
    ON community_posts (created_at ASC)
    WHERE is_pending_moderation = false AND is_hidden = false AND hidden_reason IS NULL;
