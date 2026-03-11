-- =============================================================================
-- Migration 033: Model predictions tracking and A/B assignment tables
-- =============================================================================
--
-- Adds two tables that support per-version prediction accuracy tracking and
-- persistent user assignment records for A/B testing:
--
--   model_predictions    – Per-user, per-version prediction accuracy events.
--                          Stores the predicted value, actual value, and
--                          computed error_pct so that version-level MAPE/MAE
--                          can be aggregated offline.
--
--   model_ab_assignments – Persistent mapping of user_id → model_version.
--                          Ensures the same user always receives the same
--                          model version during an A/B test window.
--                          last_prediction_at tracks user engagement.
--
-- Conventions followed:
--   • UUID PKs via gen_random_uuid()
--   • IF NOT EXISTS on every CREATE TABLE / INDEX
--   • No SERIAL / BIGSERIAL
--   • GRANT … TO neondb_owner for each table
--
-- =============================================================================


-- =============================================================================
-- TABLE: model_predictions
-- =============================================================================

CREATE TABLE IF NOT EXISTS model_predictions (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version   VARCHAR(100)    NOT NULL,
    user_id         UUID            NOT NULL,
    region          VARCHAR(50)     NOT NULL,
    predicted_value FLOAT           NOT NULL,
    actual_value    FLOAT           NULL,
    error_pct       FLOAT           NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Aggregate predictions per model version (for MAPE/MAE computation)
CREATE INDEX IF NOT EXISTS idx_model_predictions_version
    ON model_predictions (model_version, created_at DESC);

-- Look up all predictions by a specific user
CREATE INDEX IF NOT EXISTS idx_model_predictions_user
    ON model_predictions (user_id, created_at DESC);

-- Filter by region for regional accuracy reporting
CREATE INDEX IF NOT EXISTS idx_model_predictions_region
    ON model_predictions (region, model_version);


-- =============================================================================
-- TABLE: model_ab_assignments
-- =============================================================================

CREATE TABLE IF NOT EXISTS model_ab_assignments (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID            NOT NULL,
    model_version       VARCHAR(100)    NOT NULL,
    assigned_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_prediction_at  TIMESTAMPTZ     NULL,

    CONSTRAINT uq_model_ab_assignments_user_id
        UNIQUE (user_id)
);

-- Direct lookup by user_id (unique constraint covers this, but explicit index
-- makes query plan obvious)
CREATE INDEX IF NOT EXISTS idx_model_ab_assignments_user
    ON model_ab_assignments (user_id);

-- Reporting: how many users are assigned to each version
CREATE INDEX IF NOT EXISTS idx_model_ab_assignments_version
    ON model_ab_assignments (model_version);


-- =============================================================================
-- GRANTS
-- =============================================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON model_predictions    TO neondb_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON model_ab_assignments TO neondb_owner;


-- =============================================================================
-- Migration complete.
-- =============================================================================
