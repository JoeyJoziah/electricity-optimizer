-- =============================================================================
-- Migration 036: Performance indexes from database audit
-- Date: 2026-03-12
-- =============================================================================
--
-- Adds 4 missing indexes identified during Zenith Section 1 audit.
-- All indexes are CONCURRENTLY + IF NOT EXISTS for idempotency.
--
-- 1. alert_history — composite for dedup queries in check-alerts cron
-- 2. price_alert_configs — partial index for active configs
-- 3. user_connections — partial index for active connection scans
-- 4. consent_records — composite for GDPR latest-consent query
-- =============================================================================

-- Note: CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
-- When applying via psql, use:  psql -f 036_performance_indexes.sql
-- (not wrapped in BEGIN/COMMIT)

-- 1. alert_history composite for dedup queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alert_history_dedup
    ON alert_history (user_id, alert_type, region, triggered_at DESC);

-- 2. price_alert_configs for check-alerts cron (partial index on active only)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_alert_configs_active_created
    ON price_alert_configs (is_active, created_at)
    WHERE is_active = TRUE;

-- 3. user_connections for email/portal scan crons (partial index on active only)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_connections_type_status_updated
    ON user_connections (connection_type, status, updated_at ASC)
    WHERE status = 'active';

-- 4. consent_records for GDPR latest-consent-per-purpose query
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_consent_records_user_purpose_time
    ON consent_records (user_id, purpose, timestamp DESC);
