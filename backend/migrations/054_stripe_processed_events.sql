-- =============================================================================
-- Migration 054: Stripe webhook event idempotency table
-- =============================================================================
--
-- Problem: Stripe may deliver the same webhook event more than once due to
-- network retries or Stripe's at-least-once delivery guarantee.  Without a
-- deduplication guard, a single checkout.session.completed or
-- invoice.payment_failed event could be processed multiple times, resulting
-- in duplicate subscription activations or duplicate dunning emails.
--
-- Fix: create a lightweight ``stripe_processed_events`` table that records
-- every Stripe event ID the moment it is first seen.  Before processing any
-- webhook payload the handler performs:
--
--   INSERT INTO stripe_processed_events (event_id, event_type)
--   VALUES (:event_id, :event_type)
--   ON CONFLICT (event_id) DO NOTHING
--
-- The INSERT returns rowcount=0 when the event_id already exists, which
-- signals "already processed — return 200 immediately without re-applying
-- business logic."
--
-- Retention: processed events are only needed for as long as Stripe may
-- re-deliver them (Stripe retries for up to 72 hours).  A weekly maintenance
-- job deletes rows older than 72 hours to keep the table small.
--
-- Columns:
--   event_id     — Stripe event identifier (e.g. evt_1Abc...), PRIMARY KEY.
--                  VARCHAR chosen over UUID because Stripe IDs are opaque
--                  strings, not UUID format.
--   event_type   — Stripe event type (e.g. checkout.session.completed).
--                  Stored for observability / debugging queries.
--   processed_at — Timestamp of first successful receipt, defaults to NOW().
--                  Used by the cleanup job to prune old rows.
--
-- Safe to re-run: CREATE TABLE IF NOT EXISTS.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. Create the idempotency table
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS stripe_processed_events (
    event_id     VARCHAR PRIMARY KEY,
    event_type   VARCHAR NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);


-- ---------------------------------------------------------------------------
-- 2. Index on processed_at for efficient cleanup queries
-- ---------------------------------------------------------------------------
--
-- The weekly retention job runs:
--   DELETE FROM stripe_processed_events WHERE processed_at < NOW() - INTERVAL '72 hours'
--
-- Without this index that DELETE would do a full sequential scan.  With rows
-- typically numbering in the low thousands and a 72-hour window the index
-- pays for itself immediately.

CREATE INDEX IF NOT EXISTS idx_stripe_processed_events_processed_at
    ON stripe_processed_events (processed_at);


-- ---------------------------------------------------------------------------
-- 3. Grants
-- ---------------------------------------------------------------------------

GRANT ALL ON stripe_processed_events TO neondb_owner;
