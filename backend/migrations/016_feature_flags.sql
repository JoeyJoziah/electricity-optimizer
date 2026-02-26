-- Migration 016: Feature flags
CREATE TABLE IF NOT EXISTS feature_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    tier_required VARCHAR(50),
    percentage INT NOT NULL DEFAULT 100 CHECK (percentage >= 0 AND percentage <= 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feature_flags_name ON feature_flags (name);

-- Seed default flags
INSERT INTO feature_flags (name, description, enabled, tier_required, percentage) VALUES
  ('connections', 'Utility connection feature', true, 'pro', 100),
  ('analytics_dashboard', 'Advanced analytics dashboard', true, 'pro', 100),
  ('email_import', 'Email bill import', true, 'pro', 100),
  ('bill_upload', 'Bill upload and OCR', true, 'pro', 100),
  ('optimization_schedule', 'Appliance scheduling', false, null, 0)
ON CONFLICT (name) DO NOTHING;
