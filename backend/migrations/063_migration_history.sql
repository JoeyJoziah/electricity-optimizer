-- =============================================================================
-- Migration 063: Migration history tracking table
-- =============================================================================
--
-- Tracks which migrations have been applied, when, and by whom.
-- Backfills all 62 prior migration files for full history.
-- Uses ON CONFLICT DO NOTHING for idempotent re-runs.
-- =============================================================================

CREATE TABLE IF NOT EXISTS migration_history (
    id              SERIAL PRIMARY KEY,
    migration_name  VARCHAR(255) NOT NULL UNIQUE,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_by      VARCHAR(100) NOT NULL DEFAULT 'system',
    checksum        VARCHAR(64),
    execution_ms    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_migration_history_name
    ON migration_history (migration_name);

GRANT SELECT, INSERT, UPDATE, DELETE ON migration_history TO neondb_owner;
GRANT USAGE, SELECT ON SEQUENCE migration_history_id_seq TO neondb_owner;

-- Backfill all prior migrations
INSERT INTO migration_history (migration_name, applied_by) VALUES
    ('init_neon', 'backfill'),
    ('002_gdpr_auth_tables', 'backfill'),
    ('003_electricity_prices', 'backfill'),
    ('004_ml_models', 'backfill'),
    ('005_alerts', 'backfill'),
    ('006_multi_utility_types', 'backfill'),
    ('007_heating_oil', 'backfill'),
    ('008_water_rates', 'backfill'),
    ('009_propane', 'backfill'),
    ('010_community_solar', 'backfill'),
    ('011_cca_programs', 'backfill'),
    ('012_state_regulations', 'backfill'),
    ('013_tariffs', 'backfill'),
    ('014_forecast_observations', 'backfill'),
    ('015_beta_signups', 'backfill'),
    ('016_stripe_subscriptions', 'backfill'),
    ('017_feature_flags', 'backfill'),
    ('018_bill_uploads', 'backfill'),
    ('019_user_savings', 'backfill'),
    ('020_recommendations', 'backfill'),
    ('021_model_ab_testing', 'backfill'),
    ('022_scraped_rates', 'backfill'),
    ('023_supplier_registry', 'backfill'),
    ('024_payment_retry_history', 'backfill'),
    ('025_user_connections', 'backfill'),
    ('026_connection_extracted_rates', 'backfill'),
    ('027_market_intelligence', 'backfill'),
    ('028_weather_cache', 'backfill'),
    ('029_price_alert_configs', 'backfill'),
    ('030_rate_change_alerts', 'backfill'),
    ('031_agent_conversations', 'backfill'),
    ('032_agent_usage_daily', 'backfill'),
    ('033_agent_rate_limits', 'backfill'),
    ('034_user_supplier_accounts', 'backfill'),
    ('035_affiliate_clicks', 'backfill'),
    ('036_heating_oil_dealers', 'backfill'),
    ('037_geocoding_cache', 'backfill'),
    ('038_utility_accounts', 'backfill'),
    ('039_referrals', 'backfill'),
    ('040_otel_tracing', 'backfill'),
    ('041_feedback', 'backfill'),
    ('042_model_config', 'backfill'),
    ('043_model_predictions', 'backfill'),
    ('044_model_versions', 'backfill'),
    ('045_alert_history', 'backfill'),
    ('046_notification_preferences', 'backfill'),
    ('047_notifications', 'backfill'),
    ('048_kpi_daily_metrics', 'backfill'),
    ('049_community', 'backfill'),
    ('050_community_indexes', 'backfill'),
    ('051_gdpr_cascade_fixes', 'backfill'),
    ('052_ab_tests', 'backfill'),
    ('053_notification_dedup_index', 'backfill'),
    ('054_stripe_processed_events', 'backfill'),
    ('055_audit_remediation_security', 'backfill'),
    ('056_stripe_customer_id_unique', 'backfill'),
    ('057_remove_ghost_columns', 'backfill'),
    ('058_fix_foreign_keys', 'backfill'),
    ('059_oauth_bytea_columns', 'backfill'),
    ('060_updated_at_triggers', 'backfill'),
    ('061_audit_schema_fixes', 'backfill'),
    ('062_audit_schema_fixes_round2', 'backfill'),
    ('063_migration_history', 'migration')
ON CONFLICT (migration_name) DO NOTHING;
