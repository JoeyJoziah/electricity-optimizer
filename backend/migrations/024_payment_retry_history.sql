-- =============================================================================
-- Migration: Payment Retry History
-- Version: 024
-- Date: 2026-03-06
-- =============================================================================
--
-- Tracks failed payment attempts and dunning email history for the Stripe
-- dunning workflow (Phase 3 automation).  Each row represents one retry
-- event for a given invoice, allowing the DunningService to enforce
-- cooldown windows (24 h) and escalate after repeated failures.
--
-- =============================================================================


-- =============================================================================
-- TABLE: payment_retry_history
-- One row per failed-payment event or dunning email sent.
-- =============================================================================

CREATE TABLE IF NOT EXISTS payment_retry_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID            NOT NULL,
    stripe_invoice_id   VARCHAR(255)    NOT NULL,
    stripe_customer_id  VARCHAR(255)    NOT NULL,
    retry_count         INT             NOT NULL DEFAULT 1,
    retry_type          VARCHAR(30)     NOT NULL DEFAULT 'soft',
    amount_owed         NUMERIC(10, 2),
    currency            VARCHAR(10)     NOT NULL DEFAULT 'USD',
    email_sent          BOOLEAN         NOT NULL DEFAULT FALSE,
    email_sent_at       TIMESTAMPTZ,
    escalation_action   VARCHAR(50),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_payment_retry_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_payment_retry_user_invoice
    ON payment_retry_history(user_id, stripe_invoice_id);

CREATE INDEX IF NOT EXISTS idx_payment_retry_invoice
    ON payment_retry_history(stripe_invoice_id);

CREATE INDEX IF NOT EXISTS idx_payment_retry_created
    ON payment_retry_history(created_at DESC);


-- =============================================================================
-- GRANTS
-- =============================================================================

DO $$ BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON payment_retry_history TO neondb_owner;
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'neondb_owner role not found, skipping grants';
END $$;


-- =============================================================================
-- Migration complete.
-- =============================================================================
