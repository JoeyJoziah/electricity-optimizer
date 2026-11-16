-- 070_payment_retry_resolved.sql
-- Dunning correctness: record when a payment failure has been resolved.
--
-- payment_retry_history had no way to tell a failure the customer has since
-- paid from one that is still outstanding, so the daily dunning cycle sent the
-- final notice to, and downgraded, customers whose latest failure was older
-- than the grace period even after a later invoice.payment_succeeded.
--
-- resolved_at is stamped on every outstanding row for a user when a payment
-- succeeds; the overdue query only considers rows WHERE resolved_at IS NULL.
-- Existing rows stay NULL (unresolved), which preserves current behaviour for
-- them. Apply this migration BEFORE deploying the code that reads the column.

ALTER TABLE payment_retry_history
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;

-- Partial index so the overdue scan and the resolve-on-payment UPDATE only
-- touch outstanding failures.
CREATE INDEX IF NOT EXISTS idx_payment_retry_unresolved
    ON payment_retry_history (user_id)
    WHERE resolved_at IS NULL;
