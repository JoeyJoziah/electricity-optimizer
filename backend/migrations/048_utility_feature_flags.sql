-- Migration 048: Seed utility-type feature flags
-- Each utility type gets a feature flag for visibility control.
-- All currently launched utilities default to enabled.
-- New utilities can be staged behind flags before launch.

INSERT INTO feature_flags (name, description, enabled, tier_required, percentage) VALUES
  ('utility_electricity', 'Electricity rates and pricing', true, null, 100),
  ('utility_natural_gas', 'Natural gas rates and pricing', true, null, 100),
  ('utility_heating_oil', 'Heating oil price tracking', true, null, 100),
  ('utility_propane', 'Propane price tracking', true, null, 100),
  ('utility_community_solar', 'Community solar programs', true, null, 100),
  ('utility_water', 'Water rate benchmarking', true, null, 100),
  ('utility_forecast', 'Rate forecasting (multi-utility)', true, 'pro', 100),
  ('utility_export', 'Data export (multi-utility)', true, 'business', 100)
ON CONFLICT (name) DO NOTHING;
