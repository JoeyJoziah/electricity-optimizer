-- Migration 037: Additional Performance Indexes
-- Date: 2026-03-12
-- Author: Project Zenith (Section 1 remediation round 2)
--
-- Adds two missing performance indexes identified in Clarity Gate audit:
--   1. electricity_prices composite for region+utility_type+timestamp lookups (HIGH-18)
--   2. users.stripe_customer_id for payment webhook lookups (MED-27)
--
-- NOTE: CONCURRENTLY indexes cannot run inside a transaction block.
-- Run via psql or a migration runner that supports non-transactional DDL.

-- HIGH-18: Composite index for price lookup queries
-- Covers: WHERE region = ? AND utility_type = ? ORDER BY timestamp DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_electricity_prices_region_utility_time
    ON electricity_prices (region, utility_type, timestamp DESC);

-- MED-27: Index for Stripe webhook customer lookup
-- Covers: WHERE stripe_customer_id = ? (payment_failed, invoice.paid webhooks)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_stripe_customer_id
    ON users (stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

-- Grant access to neondb_owner
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO neondb_owner;
