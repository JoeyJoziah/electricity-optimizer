-- =============================================================================
-- Migration 030: Model versioning and A/B testing tables
-- =============================================================================
--
-- Adds three tables that underpin the ModelVersionService:
--
--   model_versions  – Versioned snapshots of ML model configurations with
--                     explicit is_active gating and promotion timestamps.
--                     Complements model_config (migration 027) which stores
--                     ensemble weights; model_versions stores richer metadata
--                     and supports programmatic promotion/demotion.
--
--   ab_tests        – An A/B test run pairing two model versions with a
--                     configurable traffic split.  Status lifecycle:
--                     running → completed | stopped.
--
--   ab_outcomes     – Per-user, per-test outcome events recorded by the
--                     service so that conversion / accuracy metrics can be
--                     computed after the test ends.
--
-- Conventions followed:
--   • UUID PKs via gen_random_uuid()
--   • IF NOT EXISTS on every CREATE TABLE / INDEX
--   • No SERIAL / BIGSERIAL
--   • GRANT … TO neondb_owner for each table
--
-- =============================================================================


-- =============================================================================
-- TABLE: model_versions
-- =============================================================================

CREATE TABLE IF NOT EXISTS model_versions (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name      VARCHAR(100)    NOT NULL,
    version_tag     VARCHAR(50)     NOT NULL,
    config          JSONB           NOT NULL DEFAULT '{}',
    metrics         JSONB           NOT NULL DEFAULT '{}',
    is_active       BOOLEAN         NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    promoted_at     TIMESTAMPTZ     NULL,

    CONSTRAINT uq_model_versions_name_tag
        UNIQUE (model_name, version_tag)
);

-- Hot read: find active version for a model (at most one row expected)
CREATE INDEX IF NOT EXISTS idx_model_versions_active
    ON model_versions (model_name, is_active)
    WHERE is_active = true;

-- Version history look-up (newest first)
CREATE INDEX IF NOT EXISTS idx_model_versions_name_created
    ON model_versions (model_name, created_at DESC);


-- =============================================================================
-- TABLE: ab_tests
-- =============================================================================

CREATE TABLE IF NOT EXISTS ab_tests (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name      VARCHAR(100)    NOT NULL,
    version_a_id    UUID            NOT NULL,
    version_b_id    UUID            NOT NULL,
    traffic_split   FLOAT           NOT NULL DEFAULT 0.5
                        CHECK (traffic_split > 0.0 AND traffic_split < 1.0),
    status          VARCHAR(20)     NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'completed', 'stopped')),
    started_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ     NULL,
    results         JSONB           NOT NULL DEFAULT '{}',

    CONSTRAINT fk_ab_tests_version_a
        FOREIGN KEY (version_a_id) REFERENCES model_versions(id) ON DELETE RESTRICT,
    CONSTRAINT fk_ab_tests_version_b
        FOREIGN KEY (version_b_id) REFERENCES model_versions(id) ON DELETE RESTRICT
);

-- Find active tests for a model quickly
CREATE INDEX IF NOT EXISTS idx_ab_tests_model_status
    ON ab_tests (model_name, status);

CREATE INDEX IF NOT EXISTS idx_ab_tests_started_at
    ON ab_tests (started_at DESC);


-- =============================================================================
-- TABLE: ab_outcomes
-- =============================================================================

CREATE TABLE IF NOT EXISTS ab_outcomes (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id         UUID            NOT NULL,
    version_id      UUID            NOT NULL,
    user_id         UUID            NOT NULL,
    outcome         VARCHAR(50)     NOT NULL,
    recorded_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_ab_outcomes_test
        FOREIGN KEY (test_id) REFERENCES ab_tests(id) ON DELETE CASCADE,
    CONSTRAINT fk_ab_outcomes_version
        FOREIGN KEY (version_id) REFERENCES model_versions(id) ON DELETE RESTRICT
);

-- Aggregate outcomes per test + version efficiently
CREATE INDEX IF NOT EXISTS idx_ab_outcomes_test_version
    ON ab_outcomes (test_id, version_id);

-- Prevent duplicate outcome recording for the same user+test combination
CREATE UNIQUE INDEX IF NOT EXISTS idx_ab_outcomes_test_user
    ON ab_outcomes (test_id, user_id);

CREATE INDEX IF NOT EXISTS idx_ab_outcomes_recorded_at
    ON ab_outcomes (recorded_at DESC);


-- =============================================================================
-- GRANTS
-- =============================================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON model_versions TO neondb_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON ab_tests       TO neondb_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON ab_outcomes    TO neondb_owner;


-- =============================================================================
-- Migration complete.
-- =============================================================================
