-- =============================================================================
-- Migration: Feedback Table
-- Version: 028
-- Date: 2026-03-10
-- =============================================================================
--
-- Creates the feedback table for the in-app feedback widget (TASK-GROWTH-004).
-- Users can submit bug reports, feature requests, or general feedback from
-- within the authenticated app. Feedback entries are linked to the submitting
-- user and carry a moderation status for the support team.
--
-- =============================================================================


-- =============================================================================
-- TABLE: feedback
-- One row per submitted feedback item.
-- =============================================================================

CREATE TABLE IF NOT EXISTS feedback (
    id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID            NOT NULL,
    type        VARCHAR(20)     NOT NULL CHECK (type IN ('bug', 'feature', 'general')),
    message     TEXT            NOT NULL,
    status      VARCHAR(20)     NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewed', 'resolved')),
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_feedback_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_feedback_user_id
    ON feedback(user_id);

CREATE INDEX IF NOT EXISTS idx_feedback_status
    ON feedback(status);

CREATE INDEX IF NOT EXISTS idx_feedback_created_at
    ON feedback(created_at DESC);


-- =============================================================================
-- GRANTS
-- =============================================================================

DO $$ BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON feedback TO neondb_owner;
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'neondb_owner role not found, skipping grants';
END $$;


-- =============================================================================
-- Migration complete.
-- =============================================================================
