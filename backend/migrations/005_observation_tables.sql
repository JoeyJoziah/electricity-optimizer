-- Migration 005: Observation tables for adaptive learning
-- Closes the feedback gap: tracks predicted vs actual prices, and recommendation outcomes.

-- forecast_observations: tracks predicted vs actual prices
CREATE TABLE IF NOT EXISTS forecast_observations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    forecast_id      TEXT NOT NULL,
    region           VARCHAR(50) NOT NULL,
    forecast_hour    INT NOT NULL,
    predicted_price  DECIMAL(12,6) NOT NULL,
    actual_price     DECIMAL(12,6),
    confidence_lower DECIMAL(12,6),
    confidence_upper DECIMAL(12,6),
    model_version    VARCHAR(50),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    observed_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_fobs_region_created ON forecast_observations(region, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fobs_unobserved ON forecast_observations(region, observed_at) WHERE observed_at IS NULL;

-- recommendation_outcomes: tracks user response to recommendations
CREATE TABLE IF NOT EXISTS recommendation_outcomes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    recommendation_type VARCHAR(50) NOT NULL,
    recommendation_data JSONB NOT NULL,
    was_accepted        BOOLEAN,
    actual_savings      DECIMAL(12,6),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_recout_user ON recommendation_outcomes(user_id, created_at DESC);

-- Grant permissions to application role
GRANT SELECT, INSERT, UPDATE, DELETE ON forecast_observations TO neondb_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON recommendation_outcomes TO neondb_owner;
