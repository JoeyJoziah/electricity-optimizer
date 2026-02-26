-- Migration 018: Nationwide defaults
-- Remove CT-specific defaults to support all 50 states
--
-- Changes:
--   1. Allow NULL region on users (new signups pick their state during onboarding)
--   2. Drop region default on price_alert_configs
--   3. Backfill onboarding_completed = TRUE for existing users who already have a region

-- Allow new users to start without a region (set during onboarding)
ALTER TABLE users ALTER COLUMN region DROP NOT NULL;

-- Remove CT default from alert configs (region is now always explicit)
ALTER TABLE price_alert_configs ALTER COLUMN region DROP DEFAULT;

-- Existing users who already have a region are considered onboarded
UPDATE users SET onboarding_completed = TRUE WHERE region IS NOT NULL AND (onboarding_completed IS NULL OR onboarding_completed = FALSE);
