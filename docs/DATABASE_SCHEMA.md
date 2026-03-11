# Database Schema Reference

RateShift PostgreSQL schema — Neon project `cold-rice-23455092`, 34 migrations, 33 public tables plus 9 neon_auth tables.

Last updated: 2026-03-10 (Migration 034: portal_credentials)

## Overview

- **Database**: Neon PostgreSQL (Serverless, us-east-1)
- **Project ID**: `cold-rice-23455092`
- **Endpoint (Pooled)**: `ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech` (application use)
- **Endpoint (Direct)**: `ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech` (migrations only)
- **Migrations**: Sequential 001-034 (init_neon + 34 migrations)
- **Schema**: `public` + `neon_auth` (Better Auth)
- **Primary Keys**: All UUID type via `gen_random_uuid()`
- **Ownership**: `neondb_owner` role (via GRANT statements)

## Public Schema Tables (33 tables)

### User & Authentication

#### `users` (migration: init_neon)
Core user account data. Better Auth manages session/account details separately in `neon_auth` schema.

```
id                      UUID PRIMARY KEY
email                   VARCHAR(255) NOT NULL UNIQUE
name                    VARCHAR(200) NOT NULL
region                  VARCHAR(50) NOT NULL
preferences             JSONB DEFAULT '{}'
current_supplier        VARCHAR(200)
is_active               BOOLEAN DEFAULT TRUE
is_verified             BOOLEAN DEFAULT FALSE
email_verified          BOOLEAN (via Better Auth)
subscription_tier       VARCHAR(20) — 'free'|'pro'|'business'
stripe_customer_id      VARCHAR(255)
created_at              TIMESTAMPTZ DEFAULT now()
updated_at              TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_users_region`, `idx_users_is_active`, `idx_users_created_at`

**Relations**: Foreign key parent for connections, alerts, consent, notifications, agent conversations, etc.

#### `price_alert_configs` (migration 014)
User-defined price alert rules.

```
id                      UUID PRIMARY KEY
user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
region                  VARCHAR(50) DEFAULT 'us_ct'
currency                VARCHAR(10) DEFAULT 'USD'
price_below             NUMERIC(10,6) — optional lower threshold
price_above             NUMERIC(10,6) — optional upper threshold
notify_optimal_windows  BOOLEAN DEFAULT TRUE
is_active               BOOLEAN DEFAULT TRUE
created_at              TIMESTAMPTZ DEFAULT NOW()
updated_at              TIMESTAMPTZ DEFAULT NOW()
```

Indexes: `idx_alert_configs_user_id`, `idx_alert_configs_active`

#### `alert_history` (migration 014)
Immutable log of triggered price alerts.

```
id                      UUID PRIMARY KEY
user_id                 UUID NOT NULL REFERENCES users(id)
alert_config_id         UUID REFERENCES price_alert_configs(id) ON DELETE SET NULL
alert_type              VARCHAR(30) — 'price_drop'|'price_spike'|'optimal_window'
current_price           NUMERIC(10,6)
threshold               NUMERIC(10,6)
region                  VARCHAR(50)
supplier                VARCHAR(200)
currency                VARCHAR(10) DEFAULT 'USD'
optimal_window_start    TIMESTAMPTZ
optimal_window_end      TIMESTAMPTZ
estimated_savings       NUMERIC(10,6)
triggered_at            TIMESTAMPTZ DEFAULT NOW()
email_sent              BOOLEAN DEFAULT FALSE
```

Indexes: `idx_alert_history_user_id`, `idx_alert_history_triggered_at`

### Consent & Privacy

#### `consent_records` (migration: init_neon)
GDPR compliance audit trail.

```
id                      UUID PRIMARY KEY
user_id                 UUID NOT NULL (nullable for SET NULL on user deletion)
purpose                 VARCHAR(100) — purpose of data processing
consent_given           BOOLEAN NOT NULL
timestamp               TIMESTAMPTZ DEFAULT now()
ip_address              VARCHAR(45)
user_agent              TEXT
consent_version         VARCHAR(20) DEFAULT '1.0'
withdrawal_timestamp    TIMESTAMPTZ — when consent was withdrawn
metadata                JSONB — arbitrary context
```

Indexes: `idx_consent_user_id`, `idx_consent_user_timestamp`, `idx_consent_purpose`

#### `deletion_logs` (migration: init_neon)
Immutable audit log of data deletions.

```
id                      UUID PRIMARY KEY
user_id                 UUID NOT NULL
deleted_at              TIMESTAMPTZ
deleted_by              VARCHAR(255)
deletion_type           VARCHAR(50) — 'full'|'partial'|'anonymization'
ip_address              VARCHAR(45)
user_agent              TEXT
data_categories_deleted TEXT[] — array of deleted categories
legal_basis             VARCHAR(100) DEFAULT 'user_request'
metadata                JSONB
```

### Energy Pricing

#### `electricity_prices` (migration: init_neon)
Historical electricity price data by region/supplier.

```
id                      UUID PRIMARY KEY
region                  VARCHAR(50) NOT NULL
supplier                VARCHAR(200) NOT NULL
price_per_kwh           DECIMAL(12,6) NOT NULL CHECK >= 0
currency                CHAR(3) NOT NULL
timestamp               TIMESTAMPTZ NOT NULL
is_peak                 BOOLEAN
source_api              VARCHAR(200)
created_at              TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_prices_region_timestamp`, `idx_prices_supplier`, `idx_prices_timestamp`, `idx_prices_region_is_peak`

**Note**: Used by forecast observation backfill and price query endpoints.

#### `suppliers` (migration: init_neon)
Energy suppliers (basic directory).

```
id                      UUID PRIMARY KEY
name                    VARCHAR(200) NOT NULL UNIQUE
regions                 TEXT[] DEFAULT '{}'
is_active               BOOLEAN DEFAULT TRUE
website                 VARCHAR(500)
created_at              TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_suppliers_is_active`, `idx_suppliers_regions` (GIN)

#### `supplier_registry` (migration 006)
Canonical supplier registry with full metadata.

```
id                      UUID PRIMARY KEY
name                    VARCHAR(200) NOT NULL UNIQUE
api_available           BOOLEAN DEFAULT FALSE
api_name                VARCHAR(100)
regions                 TEXT[]
utility_types           VARCHAR(50)[] DEFAULT '{"electricity"}'
tariff_types            VARCHAR(50)[]
contact_email           VARCHAR(255)
contact_phone           VARCHAR(50)
website                 VARCHAR(500)
rating                  NUMERIC(3,2)
review_count            INT
green_energy_provider   BOOLEAN DEFAULT FALSE
average_renewable_pct   INT CHECK (0 <= average_renewable_pct AND average_renewable_pct <= 100)
created_at              TIMESTAMPTZ DEFAULT now()
updated_at              TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_supplier_registry_name`, `idx_supplier_registry_api_available`

#### `tariffs` (migration: init_neon)
Electricity tariffs per supplier.

```
id                      UUID PRIMARY KEY
supplier_id             UUID NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE
name                    VARCHAR(200) NOT NULL
price_per_kwh           DECIMAL(12,6) NOT NULL CHECK >= 0
standing_charge         DECIMAL(12,6) NOT NULL CHECK >= 0
is_available            BOOLEAN DEFAULT TRUE
tariff_type             VARCHAR(50) DEFAULT 'variable'
created_at              TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_tariffs_supplier_id`, `idx_tariffs_tariff_type`, `idx_tariffs_supplier_available`

### Connections

#### `user_connections` (migration 008)
Links user accounts to utility suppliers (direct, email, or manual upload).

```
id                              UUID PRIMARY KEY
user_id                         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
connection_type                 VARCHAR(50) — 'direct'|'email_import'|'manual_upload'
supplier_id                     UUID REFERENCES supplier_registry(id)
supplier_name                   VARCHAR(200)
status                          VARCHAR(30) DEFAULT 'pending' — 'active'|'pending'|'error'|'disconnected'
account_number_encrypted        BYTEA — AES-256-GCM encrypted
account_number_masked           VARCHAR(30)
meter_number_encrypted          BYTEA
meter_number_masked             VARCHAR(30)
email_provider                  VARCHAR(50) — 'gmail'|'outlook'
label                           VARCHAR(100) — manual upload label
consent_given                   BOOLEAN DEFAULT FALSE
consent_given_at                TIMESTAMPTZ
last_sync_at                    TIMESTAMPTZ (migration 011)
last_sync_error                 VARCHAR(500) (migration 011)
next_sync_at                    TIMESTAMPTZ (migration 011)
utilityapi_account_id           VARCHAR(255) (migration 011)
created_at                      TIMESTAMPTZ DEFAULT now()
updated_at                      TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_user_connections_user`, `idx_user_connections_user_status`, `idx_user_connections_user_supplier`

#### `bill_uploads` (migration 008)
Uploaded utility bills pending OCR parsing.

```
id                              UUID PRIMARY KEY
connection_id                   UUID NOT NULL REFERENCES user_connections(id) ON DELETE CASCADE
user_id                         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
file_name                       VARCHAR(255) NOT NULL
file_type                       VARCHAR(50)
file_size_bytes                 INT
storage_key                     VARCHAR(500)
parse_status                    VARCHAR(20) DEFAULT 'pending' — 'pending'|'processing'|'complete'|'failed'
parsed_data                     JSONB
parse_error                     TEXT
parsed_at                       TIMESTAMPTZ
detected_supplier               VARCHAR(200)
detected_rate_per_kwh           DECIMAL(10,6)
detected_billing_period_start   DATE
detected_billing_period_end     DATE
detected_total_kwh              DECIMAL(12,2)
detected_total_amount           DECIMAL(10,2)
created_at                      TIMESTAMPTZ DEFAULT now()
updated_at                      TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_bill_uploads_connection`, `idx_bill_uploads_user`

#### `connection_extracted_rates` (migration 008)
Normalized rates extracted from connected accounts.

```
id                              UUID PRIMARY KEY
connection_id                   UUID NOT NULL REFERENCES user_connections(id) ON DELETE CASCADE
rate_per_kwh                    DECIMAL(10,6) NOT NULL
effective_date                  TIMESTAMPTZ NOT NULL DEFAULT now()
source                          VARCHAR(50) — 'bill_parse'|'api_pull'|'manual_entry'
raw_label                       VARCHAR(200)
supplier_name                   VARCHAR(200) (migration 008)
created_at                      TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_extracted_rates_connection`, `idx_extracted_rates_date`

### Notifications & Feedback

#### `notifications` (migration 015 + enhancements 026, 029, 032)
In-app and multi-channel notifications.

```
id                      UUID PRIMARY KEY
user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
type                    VARCHAR(50) DEFAULT 'info'
title                   TEXT NOT NULL
body                    TEXT
read_at                 TIMESTAMPTZ
metadata                JSONB (migration 026)
delivery_channel        VARCHAR(20) — 'email'|'push'|'in_app' (migration 029)
delivery_status         VARCHAR(20) DEFAULT 'pending' — 'pending'|'sent'|'delivered'|'failed'|'bounced' (migration 029)
delivered_at            TIMESTAMPTZ (migration 029)
delivery_metadata       JSONB DEFAULT '{}' (migration 029) — provider-specific data
retry_count             INTEGER DEFAULT 0 (migration 029)
error_message           TEXT (migration 032) — human-readable failure reason
created_at              TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_notifications_user_unread`, `idx_notifications_user_created`, `idx_notifications_user_delivery_status` (mig 029), `idx_notifications_channel_created` (mig 032)

#### `feedback` (migration 028)
User feedback on recommendations.

```
id                      UUID PRIMARY KEY
user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
recommendation_id       UUID
feedback_type           VARCHAR(50) — 'upvote'|'downvote'|'report'
comment                 TEXT
created_at              TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_feedback_user_id`, `idx_feedback_created_at`

### Machine Learning

#### `model_config` (migration 027)
Ensemble model weights (CNN-LSTM/XGBoost/LightGBM).

```
id                      UUID PRIMARY KEY
model_name              VARCHAR(100) NOT NULL
model_version           VARCHAR(50) NOT NULL
weights_json            JSONB NOT NULL
training_metadata       JSONB DEFAULT '{}'
accuracy_metrics        JSONB DEFAULT '{}'
is_active               BOOLEAN DEFAULT FALSE
created_at              TIMESTAMPTZ DEFAULT NOW()
updated_at              TIMESTAMPTZ DEFAULT NOW()
```

Indexes: `idx_model_config_active`, `idx_model_config_version`

#### `model_versions` (migration 030)
Versioned ML model configurations with promotion tracking.

```
id                      UUID PRIMARY KEY
model_name              VARCHAR(100) NOT NULL
version_tag             VARCHAR(50) NOT NULL
config                  JSONB DEFAULT '{}' — hyperparameters, ensemble weights, features
metrics                 JSONB DEFAULT '{}' — mape, rmse, coverage, etc.
is_active               BOOLEAN DEFAULT FALSE
created_at              TIMESTAMPTZ DEFAULT NOW()
promoted_at             TIMESTAMPTZ
UNIQUE (model_name, version_tag)
```

Indexes: `idx_model_versions_active` (WHERE is_active=true), `idx_model_versions_name_created`

#### `ab_tests` (migration 030)
A/B test runs pairing two model versions.

```
id                      UUID PRIMARY KEY
model_name              VARCHAR(100) NOT NULL
version_a_id            UUID NOT NULL REFERENCES model_versions(id) ON DELETE RESTRICT
version_b_id            UUID NOT NULL REFERENCES model_versions(id) ON DELETE RESTRICT
traffic_split           FLOAT DEFAULT 0.5 CHECK (0 < traffic_split < 1) — fraction to version A
status                  VARCHAR(20) DEFAULT 'running' — 'running'|'completed'|'stopped'
started_at              TIMESTAMPTZ DEFAULT NOW()
ended_at                TIMESTAMPTZ
results                 JSONB DEFAULT '{}' — aggregated metrics when concluded
```

Indexes: `idx_ab_tests_model_status`, `idx_ab_tests_started_at`

#### `ab_outcomes` (migration 030)
Per-user outcome events recorded during A/B tests.

```
id                      UUID PRIMARY KEY
test_id                 UUID NOT NULL REFERENCES ab_tests(id) ON DELETE CASCADE
version_id              UUID NOT NULL REFERENCES model_versions(id) ON DELETE RESTRICT
user_id                 UUID NOT NULL
outcome                 VARCHAR(50) NOT NULL
recorded_at             TIMESTAMPTZ DEFAULT NOW()
UNIQUE (test_id, user_id)
```

Indexes: `idx_ab_outcomes_test_version`, `idx_ab_outcomes_test_user` (UNIQUE), `idx_ab_outcomes_recorded_at`

#### `model_predictions` (migration 033)
Per-version prediction accuracy tracking.

```
id                      UUID PRIMARY KEY
model_version           VARCHAR(100) NOT NULL
user_id                 UUID NOT NULL
region                  VARCHAR(50) NOT NULL
predicted_value         FLOAT NOT NULL
actual_value            FLOAT
error_pct               FLOAT — computed error percentage
created_at              TIMESTAMPTZ DEFAULT NOW()
```

Indexes: `idx_model_predictions_version`, `idx_model_predictions_user`, `idx_model_predictions_region`

#### `model_ab_assignments` (migration 033)
Persistent user→version assignments during A/B tests.

```
id                      UUID PRIMARY KEY
user_id                 UUID NOT NULL UNIQUE
model_version           VARCHAR(100) NOT NULL
assigned_at             TIMESTAMPTZ DEFAULT NOW()
last_prediction_at      TIMESTAMPTZ
```

Indexes: `idx_model_ab_assignments_user`, `idx_model_ab_assignments_version`

### Payments & Billing

#### `payment_retry_history` (migration 024)
Dunning cycle audit trail for failed payments.

```
id                      UUID PRIMARY KEY
user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
invoice_id              VARCHAR(255) NOT NULL
stripe_event_id         VARCHAR(255)
retry_attempt           INT DEFAULT 1
email_sent_at           TIMESTAMPTZ — timestamp of dunning email
email_sent              BOOLEAN DEFAULT FALSE
escalation_level        INT DEFAULT 0 — 0=soft, 1=final
last_status             VARCHAR(50) — 'pending'|'retried'|'failed'|'recovered'
created_at              TIMESTAMPTZ DEFAULT now()
updated_at              TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_payment_retry_history_user_id`, `idx_payment_retry_history_invoice_id`, `idx_payment_retry_history_email_sent_at`

### AI Agent

#### `agent_conversations` (migration 031)
Agent conversation history.

```
id                      UUID PRIMARY KEY
user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
prompt                  TEXT NOT NULL
response                TEXT
model_used              VARCHAR(50)
tools_used              JSONB DEFAULT '[]'::jsonb
tokens_used             INT DEFAULT 0
duration_ms             INT DEFAULT 0
created_at              TIMESTAMPTZ DEFAULT NOW()
```

Indexes: `idx_agent_conversations_user_id`, `idx_agent_conversations_created_at`

#### `agent_usage_daily` (migration 031)
Daily usage counters for rate limiting.

```
id                      UUID PRIMARY KEY
user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
date                    DATE DEFAULT CURRENT_DATE
query_count             INT DEFAULT 0
UNIQUE (user_id, date)
```

Indexes: `idx_agent_usage_daily_user_date`

### Caching & Data

#### `weather_cache` (migration 025)
Cached OpenWeather data for ML features.

```
id                      UUID PRIMARY KEY
state_code              VARCHAR(2) NOT NULL
temperature_f           DECIMAL(5,1)
humidity                INT
wind_speed_mph          DECIMAL(5,1)
conditions              VARCHAR(100)
raw_data                JSONB DEFAULT '{}'
fetched_at              TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_weather_cache_state_time`

#### `market_intelligence` (migration 025)
Cached Tavily search results.

```
id                      UUID PRIMARY KEY
query                   VARCHAR(500) NOT NULL
region                  VARCHAR(50)
title                   VARCHAR(500)
url                     VARCHAR(1000)
content                 TEXT
score                   DECIMAL(5,3)
raw_data                JSONB DEFAULT '{}'
fetched_at              TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_market_intel_region_time`

#### `scraped_rates` (migration 025)
Cached Diffbot-extracted supplier rates.

```
id                      UUID PRIMARY KEY
supplier_id             UUID REFERENCES supplier_registry(id)
supplier_name           VARCHAR(200)
source_url              VARCHAR(1000)
extracted_data          JSONB DEFAULT '{}'
success                 BOOLEAN DEFAULT TRUE
fetched_at              TIMESTAMPTZ DEFAULT now()
```

Indexes: `idx_scraped_rates_supplier_time`

### Feature Flags & Configuration

#### `feature_flags` (migration 016)
Runtime feature toggles.

```
id                      UUID PRIMARY KEY
name                    VARCHAR(100) NOT NULL UNIQUE
description             TEXT
is_enabled              BOOLEAN DEFAULT FALSE
rollout_percentage      INT DEFAULT 0 CHECK (0 <= rollout_percentage AND rollout_percentage <= 100)
config                  JSONB DEFAULT '{}'
created_at              TIMESTAMPTZ DEFAULT now()
updated_at              TIMESTAMPTZ DEFAULT now()
```

### Additional Tables (Migrations 005-013)

- **forecast_observations** (mig 005): Backfilled forecast predictions vs. actuals
- **recommendation_outcomes** (mig 005): User recommendation acceptance/savings tracking
- **user_supplier_accounts** (mig 007): Deprecated; use `user_connections` instead
- **email_oauth_tokens** (mig 009): OAuth tokens for Gmail/Outlook (encrypted at rest)
- **user_savings** (mig 012): Aggregated savings estimates
- **user_profile** (mig 013): Extended user profile columns (household_size, avg_daily_kwh, etc.)

## neon_auth Schema (9 Tables)

Managed by Better Auth (Neon Auth). Do NOT modify directly.

- **user**: User identity (id, email, emailVerified, name, image)
- **session**: Session tokens (userId, expiresAt, "updatedAt")
- **account**: OAuth account links (userId, provider, providerAccountId)
- **verification**: Email verification tokens (identifier, token, expires)
- **passkey**: Passwordless authentication keys
- Additional auth-related tables for JWT/MFA if configured

**Note**: Quoted identifiers required for some columns (e.g., `neon_auth.session."updatedAt"`).

## Migration History

| #   | Filename | Date       | Purpose |
|-----|----------|------------|---------|
| 000 | init_neon.sql | 2026-01-XX | Initial schema (users, prices, suppliers, tariffs, consent, deletion_logs, beta_signups) |
| 003 | 003_reconcile_schema.sql | 2026-02-XX | Schema alignment |
| 004 | 004_performance_indexes.sql | 2026-02-XX | Query optimization indexes |
| 005 | 005_observation_tables.sql | 2026-02-XX | Forecast observations, recommendation outcomes |
| 006 | 006_multi_utility_expansion.sql | 2026-02-XX | Supplier registry, multi-utility support |
| 007 | 007_user_supplier_accounts.sql | 2026-02-XX | User supplier linking (deprecated) |
| 008 | 008_connection_feature.sql | 2026-02-25 | Connections (direct/email/upload), bill uploads, extracted rates |
| 009 | 009_email_oauth_tokens.sql | 2026-02-XX | OAuth token storage (Gmail/Outlook) |
| 010 | 010_utility_type_index.sql | 2026-02-XX | Utility type filtering indexes |
| 011 | 011_utilityapi_sync_columns.sql | 2026-02-XX | UtilityAPI sync tracking |
| 012 | 012_user_savings.sql | 2026-02-XX | User savings aggregation |
| 013 | 013_user_profile_columns.sql | 2026-02-XX | Extended user profile |
| 014 | 014_alert_tables.sql | 2026-02-25 | Price alert configs, alert history |
| 015 | 015_notifications.sql | 2026-02-XX | In-app notifications |
| 016 | 016_feature_flags.sql | 2026-02-XX | Runtime feature toggles |
| 017 | 017_additional_indexes.sql | 2026-02-XX | Additional performance indexes |
| 018 | 018_nationwide_defaults.sql | 2026-02-XX | Default values for nationwide expansion |
| 019 | 019_nationwide_suppliers.sql | 2026-02-XX | Nationwide supplier seeding |
| 020 | 020_price_query_indexes.sql | 2026-02-XX | Price query optimization |
| 021 | 021_fix_supplier_api_available.sql | 2026-02-XX | Supplier API availability flag |
| 022 | 022_user_supplier_composite_index.sql | 2026-02-XX | Composite user+supplier indexing |
| 023 | 023_db_audit_indexes.sql | 2026-03-05 | SET NULL constraints, audit indexes |
| 024 | 024_payment_retry_history.sql | 2026-03-06 | Dunning cycle audit trail |
| 025 | 025_data_cache_tables.sql | 2026-03-06 | Weather, market intel, scraped rates cache |
| 026 | 026_notifications_metadata.sql | 2026-03-XX | Notification metadata JSONB column |
| 027 | 027_model_config.sql | 2026-03-XX | ML ensemble weight persistence |
| 028 | 028_feedback_table.sql | 2026-03-XX | User feedback on recommendations |
| 029 | 029_notification_delivery_tracking.sql | 2026-03-10 | Delivery channel, status, metadata, error tracking |
| 030 | 030_model_versioning_ab_tests.sql | 2026-03-10 | Model versions, A/B tests, outcomes |
| 031 | 031_agent_tables.sql | 2026-03-11 | Agent conversations, usage tracking |
| 032 | 032_notification_error_message.sql | 2026-03-10 | Notification error_message TEXT column |
| 033 | 033_model_predictions_ab_assignments.sql | 2026-03-11 | Model predictions, A/B user assignments |
| 034 | 034_portal_credentials.sql | 2026-03-10 | Portal scrape columns on user_connections (username, encrypted password, login URL, status, last scraped) |

## Migration Conventions

All migrations follow these patterns:

1. **Sequential Numbering**: `NNN_description.sql` (001-033)
2. **IF NOT EXISTS**: All CREATE TABLE/INDEX statements are idempotent
3. **Primary Keys**: UUID via `gen_random_uuid()` (no SERIAL/BIGSERIAL)
4. **Foreign Keys**: ON DELETE CASCADE or ON DELETE RESTRICT with explicit choices
5. **Constraints**: Named, explicit CHECK clauses for numeric ranges
6. **Indexes**: Named with `idx_*` prefix, partial indexes where applicable (WHERE clauses)
7. **Ownership**: `GRANT … TO neondb_owner` for all tables (Better Auth compatibility)
8. **Execution**: Via direct endpoint (not pooled) for DDL operations

## Execution Notes

- **Apply migrations**: Use `neon` CLI or direct endpoint connection
- **Pooled connections**: For queries only (statement cache disabled: `statement_cache_size=0`)
- **Direct connections**: For DDL/migrations
- **Branches**: `production` (default), `vercel-dev` (preview deployments)

## Key Constraints

- Users: No cascade on some FKs (to preserve audit trails)
- Notifications: Cascade on user delete (transient data)
- Connections: Cascade on user delete (user-owned)
- Payments: Cascade on user delete (transient)
- Agent: Cascade on user delete (transient)
- Model versions: RESTRICT delete (prevent orphaned A/B tests)
- Alert configs: Cascade on user delete

## Related Documentation

- `INFRASTRUCTURE.md`: Database connection pooling, scaling
- `SECURITY_AUDIT.md`: Encryption (AES-256-GCM for account numbers), password policies
- Backend models: `backend/models/*.py` (Pydantic validation layer)
- API routes: `backend/api/v1/*.py` (CRUD endpoints)
