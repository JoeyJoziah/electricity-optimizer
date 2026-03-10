-- Migration 026: ML model configuration and weight persistence
-- Replaces ephemeral Redis storage with durable PostgreSQL-backed weight store.
-- The ensemble predictor (CNN-LSTM 0.5 + XGBoost 0.25 + LightGBM 0.25) loses
-- trained weights on every Render restart because Render free-tier Redis is
-- ephemeral and silently fails.  This table provides a persistent fallback so
-- that LearningService can write weights after every nightly cycle and
-- EnsemblePredictor can reload them on startup.

CREATE TABLE IF NOT EXISTS model_config (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name       VARCHAR(100) NOT NULL,
    model_version    VARCHAR(50)  NOT NULL,
    weights_json     JSONB        NOT NULL,
    training_metadata JSONB       DEFAULT '{}',
    accuracy_metrics  JSONB       DEFAULT '{}',
    is_active        BOOLEAN      DEFAULT false,
    created_at       TIMESTAMPTZ  DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  DEFAULT NOW()
);

-- Partial index: at most one active row per model_name is expected.
-- Filtering on is_active = true keeps the index small for the hot read path.
CREATE INDEX IF NOT EXISTS idx_model_config_active
    ON model_config (model_name, is_active)
    WHERE is_active = true;

-- Full index for version history look-ups (list_versions query).
CREATE INDEX IF NOT EXISTS idx_model_config_version
    ON model_config (model_name, model_version);

GRANT SELECT, INSERT, UPDATE, DELETE ON model_config TO neondb_owner;
