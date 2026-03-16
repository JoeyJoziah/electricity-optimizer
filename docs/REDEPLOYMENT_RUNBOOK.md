# RateShift Complete Redeployment Runbook

> **PURPOSE**: Executable step-by-step guide to fully redeploy the RateShift application from scratch across all four deployment layers (Database, Backend, Frontend, Edge Layer).
>
> **LAST UPDATED**: 2026-03-16
> **STATUS**: Production-ready
> **SCOPE**: Cold start redeployment, assumes DNS already configured per `/docs/DNS_EMAIL_SETUP.md`

---

## Table of Contents

1. [Prerequisites & Access](#prerequisites--access)
2. [Layer 1: Database (Neon PostgreSQL)](#layer-1-database-neon-postgresql)
3. [Layer 2: Backend (Render + FastAPI)](#layer-2-backend-render--fastapi)
4. [Layer 3: Frontend (Vercel + Next.js)](#layer-3-frontend-vercel--nextjs)
5. [Layer 4: Edge Layer (Cloudflare Worker)](#layer-4-edge-layer-cloudflare-worker)
6. [Post-Deployment Verification](#post-deployment-verification)
7. [Cron Jobs & Automation](#cron-jobs--automation)
8. [Rollback Procedures](#rollback-procedures)
9. [Troubleshooting](#troubleshooting)
10. [Known Gotchas](#known-gotchas)

---

## Prerequisites & Access

### Required Accounts & Credentials

Verify access to the following **before** starting redeployment:

1. **Neon Console** (https://console.neon.tech)
   - Project: `cold-rice-23455092` ("energyoptimize")
   - Auth: Neon account login (credentials in 1Password "Electricity Optimizer" vault)

2. **Render Dashboard** (https://dashboard.render.com)
   - Backend service: `srv-d649uhur433s73d557cg`
   - Auth: Render account login

3. **Vercel Dashboard** (https://vercel.com)
   - Frontend project: `electricity-optimizer`
   - Auth: Vercel account login (or GitHub OAuth)

4. **Cloudflare Dashboard** (https://dash.cloudflare.com)
   - Zone: `ac03dd28616da6d1c4b894c298c1da58` (rateshift.app)
   - CF Account ID: `b41be0d03c76c0b2cc91efccdb7a10df`
   - Auth: Cloudflare account login

5. **GitHub** (https://github.com/JoeyJoziah/electricity-optimizer)
   - Repo: `JoeyJoziah/electricity-optimizer`
   - Personal Access Token: For `gh` CLI commands

6. **1Password** (https://1password.com)
   - Vault: "RateShift"
   - Contains: 28+ secrets for all services

### Local Tools Required

```bash
# Verify installations
node --version          # expect v18+ (for frontend / wrangler)
python3 --version       # expect 3.12+
npm --version           # expect 9+
nvm --version           # optional, for Node version management
wrangler --version      # expect 3.0+
op --version            # 1Password CLI — expect 2.0+
gh --version            # GitHub CLI — expect 2.0+
psycopg2                # (Python) for Neon migrations: pip install psycopg2-binary
curl --version          # for health checks
dig --version           # for DNS verification
```

### Retrieve Secrets from 1Password

Use the 1Password CLI to fetch credentials securely:

```bash
# Example: fetch Neon password
op item get "Neon PostgreSQL" --vault "RateShift" --fields password

# Fetch all GitHub secrets
op item get "GitHub Secrets" --vault "RateShift" --fields INTERNAL_API_KEY,RENDER_DEPLOY_HOOK_BACKEND

# List all items in vault
op item list --vault "RateShift"
```

Store these in a secure `.env` file (never commit):

```bash
# Create temporary secrets file (example)
cat > /tmp/secrets.env <<EOF
NEON_PASSWORD=$(op item get "Neon PostgreSQL" --vault "RateShift" --fields password)
INTERNAL_API_KEY=$(op item get "GitHub Secrets" --vault "RateShift" --fields INTERNAL_API_KEY)
RENDER_DEPLOY_HOOK_BACKEND=$(op item get "GitHub Secrets" --vault "RateShift" --fields RENDER_DEPLOY_HOOK_BACKEND)
EOF

source /tmp/secrets.env
# Clean up after use
rm /tmp/secrets.env
```

---

## Layer 1: Database (Neon PostgreSQL)

### Overview

- **Project ID**: `cold-rice-23455092` ("energyoptimize")
- **Pooled endpoint** (for app connections): `ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech`
- **Direct endpoint** (for DDL/migrations): `ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech`
- **Region**: us-east-1
- **Branches**: `production` (default), `vercel-dev` (for preview deployments)
- **Total tables**: 44 public + 9 neon_auth = 53 total
- **All migrations**: 50 files in `backend/migrations/` (49 deployed to production through 049), using `IF NOT EXISTS` pattern (safe to re-run)

### Migration Files (Complete List)

The following 50 migrations must be applied **in order** to the `production` branch (49 deployed as of 2026-03-16, 050 pending):

```
1.  init_neon.sql                               (core schema, users, prices, suppliers)
2.  002_gdpr_auth_tables.sql                    (neon_auth schema, session/auth tables)
3.  003_reconcile_schema.sql                    (refactor, cleanup, add constraints)
4.  004_performance_indexes.sql                 (index optimization)
5.  005_observation_tables.sql                  (observation logs for ML)
6.  006_multi_utility_expansion.sql             (multi-utility support)
7.  007_user_supplier_accounts.sql              (user_supplier_accounts mapping)
8.  008_connection_feature.sql                  (connections, bill uploads, OCR)
9.  009_email_oauth_tokens.sql                  (email OAuth tokens)
10. 010_utility_type_index.sql                  (utility type indexing)
11. 011_utilityapi_sync_columns.sql             (UtilityAPI sync state)
12. 012_user_savings.sql                        (user savings tracking)
13. 013_user_profile_columns.sql                (user profile enrichment)
14. 014_alert_tables.sql                        (alert configs, history)
15. 015_notifications.sql                       (notification base table)
16. 016_feature_flags.sql                       (feature flags)
17. 017_additional_indexes.sql                  (additional query optimization)
18. 018_nationwide_defaults.sql                 (default values for all states)
19. 019_nationwide_suppliers.sql                (supplier registry for 50 states + DC + intl)
20. 020_price_query_indexes.sql                 (price query optimization)
21. 021_fix_supplier_api_available.sql          (supplier registry api_available column fix)
22. 022_user_supplier_composite_index.sql       (composite index on user_supplier_accounts)
23. 023_db_audit_indexes.sql                    (audit log indexes)
24. 024_payment_retry_history.sql               (Stripe dunning tracking)
25. 025_data_cache_tables.sql                   (weather, market research, rates cache)
26. 026_notifications_metadata.sql              (notification metadata enrichment)
27. 027_model_config.sql                        (ML model configuration)
28. 028_feedback_table.sql                      (user feedback collection)
29. 029_notification_delivery_tracking.sql      (notification delivery success/failure tracking)
30. 030_model_versioning_ab_tests.sql           (model versioning + A/B test assignments)
31. 031_agent_tables.sql                        (AI agent conversation history)
32. 032_notification_error_message.sql          (notification error message logging)
33. 033_model_predictions_ab_assignments.sql    (model predictions + AB test assignments)
34. 034_portal_credentials.sql                  (portal credentials columns on user_connections)
35. 035_backfill_neon_auth_users.sql            (backfill neon_auth users)
36. 036_performance_indexes.sql                 (additional performance indexes)
37. 037_additional_performance_indexes.sql      (further performance indexes)
38. 038_utility_accounts.sql                    (utility accounts)
39. 039_referrals.sql                           (referral tracking)
40. 040_gas_supplier_seed.sql                   (12 gas supplier seed data)
41. 041_community_solar_programs.sql            (15 community solar programs)
42. 042_cca_programs.sql                        (CCA programs)
43. 043_heating_oil.sql                         (heating oil prices, dealers)
44. 044_multi_utility_alerts.sql                (multi-utility alerting tables)
45. 045_affiliate_tracking.sql                  (affiliate click tracking)
46. 046_propane_prices.sql                      (propane price tracking)
47. 047_water_rates.sql                         (water rates with JSONB rate_tiers)
48. 048_utility_feature_flags.sql               (utility-specific feature flags)
49. 049_community_tables.sql                    (community posts, votes, reports)
50. 050_community_posts_indexes.sql             (community posts indexes — NOT YET DEPLOYED)
```

### Step 1.1: Connect to Neon

Use either **Neon MCP** (single statements only) or **1Password CLI + psycopg2** (batch migrations).

#### Option A: Neon MCP (Limited to Single Statements)

For interactive queries or single-statement testing:

```bash
# Query to verify database exists
mcp__Neon__run_sql \
  projectId="cold-rice-23455092" \
  sql="SELECT datname FROM pg_database WHERE datname = 'neondb';"

# Expected output: one row with datname='neondb'
```

#### Option B: 1Password CLI + psycopg2 (Recommended for Migrations)

For batch migration execution:

```bash
# 1. Install psycopg2
pip install psycopg2-binary

# 2. Fetch Neon password from 1Password
NEON_PASSWORD=$(op item get "Neon PostgreSQL" \
  --vault "RateShift" --fields password)

# 3. Set connection string (use DIRECT endpoint for DDL)
export PGPASSWORD="$NEON_PASSWORD"
export NEON_CONNECTION_STRING="postgresql://neondb_owner:${NEON_PASSWORD}@ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require"

# 4. Test connection
psql "$NEON_CONNECTION_STRING" -c "SELECT version();"

# Expected output: PostgreSQL 15.x (Neon)
```

### Step 1.2: Apply All 50 Migrations

**IMPORTANT**: Migrations use `IF NOT EXISTS`, so they are **safe to re-run** without data loss.

```bash
#!/bin/bash
# apply-all-migrations.sh

set -e  # Exit on error

NEON_PASSWORD=$(op item get "Neon PostgreSQL" \
  --vault "RateShift" --fields password)
export PGPASSWORD="$NEON_PASSWORD"
export NEON_CONNECTION="postgresql://neondb_owner:${NEON_PASSWORD}@ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require"

MIGRATIONS_DIR="/Users/devinmcgrath/projects/electricity-optimizer/backend/migrations"

echo "Applying all 50 migrations to Neon..."
echo "Connection: $(echo $NEON_CONNECTION | cut -d'@' -f2)"
echo ""

# Array of migration files in order
migrations=(
  "init_neon.sql"
  "002_gdpr_auth_tables.sql"
  "003_reconcile_schema.sql"
  "004_performance_indexes.sql"
  "005_observation_tables.sql"
  "006_multi_utility_expansion.sql"
  "007_user_supplier_accounts.sql"
  "008_connection_feature.sql"
  "009_email_oauth_tokens.sql"
  "010_utility_type_index.sql"
  "011_utilityapi_sync_columns.sql"
  "012_user_savings.sql"
  "013_user_profile_columns.sql"
  "014_alert_tables.sql"
  "015_notifications.sql"
  "016_feature_flags.sql"
  "017_additional_indexes.sql"
  "018_nationwide_defaults.sql"
  "019_nationwide_suppliers.sql"
  "020_price_query_indexes.sql"
  "021_fix_supplier_api_available.sql"
  "022_user_supplier_composite_index.sql"
  "023_db_audit_indexes.sql"
  "024_payment_retry_history.sql"
  "025_data_cache_tables.sql"
  "026_notifications_metadata.sql"
  "027_model_config.sql"
  "028_feedback_table.sql"
  "029_notification_delivery_tracking.sql"
  "030_model_versioning_ab_tests.sql"
  "031_agent_tables.sql"
  "032_notification_error_message.sql"
  "033_model_predictions_ab_assignments.sql"
  "034_portal_credentials.sql"
  "035_backfill_neon_auth_users.sql"
  "036_performance_indexes.sql"
  "037_additional_performance_indexes.sql"
  "038_utility_accounts.sql"
  "039_referrals.sql"
  "040_gas_supplier_seed.sql"
  "041_community_solar_programs.sql"
  "042_cca_programs.sql"
  "043_heating_oil.sql"
  "044_multi_utility_alerts.sql"
  "045_affiliate_tracking.sql"
  "046_propane_prices.sql"
  "047_water_rates.sql"
  "048_utility_feature_flags.sql"
  "049_community_tables.sql"
  "050_community_posts_indexes.sql"
)

for ((i=0; i<${#migrations[@]}; i++)); do
  migration="${migrations[$i]}"
  migration_num=$((i + 1))
  migration_file="$MIGRATIONS_DIR/$migration"

  if [ ! -f "$migration_file" ]; then
    echo "ERROR: Migration file not found: $migration_file"
    exit 1
  fi

  echo "[$migration_num/50] Applying: $migration"
  psql "$NEON_CONNECTION" -f "$migration_file" > /dev/null 2>&1

  if [ $? -eq 0 ]; then
    echo "  ✓ Success"
  else
    echo "  ✗ FAILED"
    psql "$NEON_CONNECTION" -f "$migration_file"  # Re-run with output for debugging
    exit 1
  fi
done

echo ""
echo "All 50 migrations applied successfully!"
```

Run the migration script:

```bash
chmod +x /tmp/apply-all-migrations.sh
/tmp/apply-all-migrations.sh
```

### Step 1.3: Verify Database Schema

After all migrations are applied, verify the schema:

```bash
# Count tables in public schema
psql "$NEON_CONNECTION" -c \
  "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = 'public';"

# Expected: 34 tables (or more if new tables added after schema stabilization)

# List all tables
psql "$NEON_CONNECTION" -c \
  "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"

# Expected output (sample):
# alert_configs
# alert_history
# ...
# users
# weather_cache
# ...

# Verify neon_auth schema exists and has session/user tables
psql "$NEON_CONNECTION" -c \
  "SELECT table_name FROM information_schema.tables WHERE table_schema = 'neon_auth' ORDER BY table_name;"

# Expected: account, session, user, verification, and other auth tables
```

### Step 1.4: Grant Permissions (If Needed)

Migrations use `GRANT` statements, but verify critical tables are owned by the correct role:

```bash
# Check table ownership
psql "$NEON_CONNECTION" -c \
  "SELECT tablename, tableowner FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"

# Expected: All tables owned by 'neondb_owner' or 'postgres'

# If a table is owned by the wrong role, grant it:
# psql "$NEON_CONNECTION" -c "GRANT SELECT, INSERT, UPDATE, DELETE ON <table_name> TO neondb_owner;"
```

### Step 1.5: Verify Indexes

Ensure all performance indexes are in place:

```bash
# Count indexes
psql "$NEON_CONNECTION" -c \
  "SELECT COUNT(*) as index_count FROM pg_indexes WHERE schemaname = 'public';"

# Expected: 40+ indexes (exact count varies with migrations)

# List all indexes
psql "$NEON_CONNECTION" -c \
  "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename, indexname;"
```

### Step 1.6: Database Verification Complete

You should see:
- 44 public tables
- 9 neon_auth tables (53 total)
- 100+ indexes
- All tables with `neondb_owner` ownership
- No errors in the migration logs

Clean up temporary secrets:

```bash
unset PGPASSWORD
unset NEON_CONNECTION
```

---

## Layer 2: Backend (Render + FastAPI)

### Overview

- **Service ID**: `srv-d649uhur433s73d557cg`
- **Platform**: Render (https://render.com)
- **Language**: Python 3.12 + FastAPI
- **Docker**: Multi-stage build from `backend/Dockerfile`
- **Deployment**: Via Render deploy hook (triggered by GitHub Actions) or manual Render dashboard
- **Health endpoint**: `GET /health` → returns `{"status":"healthy"}`
- **Environment variables**: 41 total (see list below)

### Backend Environment Variables (All 41)

Create these on the Render dashboard for service `srv-d649uhur433s73d557cg` **before** deploying.

#### Core / Deployment

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `ENVIRONMENT` | `production` | Manual | Sets log level, features |
| `BACKEND_PORT` | `8000` | Manual | Internal port (Render exposes via proxy) |
| `DEBUG` | `false` | Manual | Must be `false` in production |

#### Database

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `DATABASE_URL` | `postgresql://neondb_owner:PASSWORD@ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require` | Neon Console | **Pooled endpoint** (for app). Copy from Neon project settings. Use `?sslmode=require` for security. |
| `DB_POOL_SIZE` | `3` | Manual | asyncpg connection pool size |
| `DB_MAX_OVERFLOW` | `5` | Manual | Max additional connections beyond pool_size |

#### Redis (Optional)

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `REDIS_URL` | `rediss://default:PASSWORD@...upstash.io:6379` | Upstash Console | Optional — if not set, in-memory fallback used. **Warning**: In-memory not shared across Render instances. |

#### Authentication & Security

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `JWT_SECRET` | 64-hex-char string | Generate: `openssl rand -hex 32` | Used ONLY for internal API validation, not user auth |
| `INTERNAL_API_KEY` | 64-hex-char string | Generate: `openssl rand -hex 32` | Service-to-service API key (cron jobs, Composio, GHA) |
| `BETTER_AUTH_SECRET` | 64-hex-char string | Generate: `openssl rand -hex 32` | Session signing key for Neon Auth |
| `BETTER_AUTH_URL` | `https://rateshift.app` | Manual | Public frontend URL (used by Better Auth for CORS) |
| `FIELD_ENCRYPTION_KEY` | 64-hex-char string | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` | AES-256-GCM for user account numbers |
| `GITHUB_WEBHOOK_SECRET` | 64-hex-char string | Generate: `openssl rand -hex 32` | GitHub webhook signature verification |

#### OAuth Providers

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `GOOGLE_CLIENT_ID` | `xxx.apps.googleusercontent.com` | Google Cloud Console | For Google OAuth login (optional) |
| `GOOGLE_CLIENT_SECRET` | `GOCSPX-xxx` | Google Cloud Console | Keep secret! |
| `GITHUB_CLIENT_ID` | `Ov23li...` | GitHub App settings | For GitHub OAuth login (optional) |
| `GITHUB_CLIENT_SECRET` | `ghs_xxx` | GitHub App settings | Keep secret! |

#### External APIs

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `FLATPEAK_API_KEY` | `fp_xxx` | Flatpeak Developer Console | UK/EU electricity prices (optional) |
| `NREL_API_KEY` | String | NREL Developer Portal | US utility rates (optional) |
| `EIA_API_KEY` | String | EIA API Portal | Energy Information Admin (optional) |
| `OPENWEATHERMAP_API_KEY` | String | OpenWeather API | Weather data (optional, free tier 1K calls/day) |
| `UTILITYAPI_KEY` | String | UtilityAPI Dashboard | US smart meter data (optional) |
| `OPENVOLT_API_KEY` | String | OpenVolt Dashboard | UK smart meter data (optional) |
| `DIFFBOT_API_TOKEN` | String | Diffbot Dashboard | Rate scraping (optional, free tier) |
| `TAVILY_API_KEY` | `tvly-xxx` | Tavily Dashboard | Market research (optional, free tier 1K searches/month) |
| `GOOGLE_MAPS_API_KEY` | `AIza-xxx` | Google Cloud Console | Geocoding (optional, card required) |

#### Email

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `RESEND_API_KEY` | `re_xxxxxxxxxxxxx` | Resend Dashboard → API Keys | Primary email provider. **CRITICAL**: Must be non-empty for emails to work. |
| `SMTP_HOST` | `smtp.gmail.com` | Gmail Settings | SMTP fallback host. Use Gmail if Resend not yet verified. |
| `SMTP_PORT` | `587` | Gmail Settings | SMTP port (587 for TLS) |
| `SMTP_USERNAME` | `your-email@gmail.com` | Gmail Settings | SMTP username (Gmail address) |
| `SMTP_PASSWORD` | 16-char app password | Gmail App Passwords (myaccount.google.com/apppasswords) | **NOT** your regular Gmail password — must be App Password with 2FA enabled. |
| `EMAIL_FROM_ADDRESS` | `RateShift <noreply@rateshift.app>` | Manual | Display name and sender email. Must match verified domain in Resend OR Gmail SMTP will rewrite it. |
| `EMAIL_FROM_NAME` | `RateShift` | Manual | Display name fallback. |

#### Stripe (Payments)

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `STRIPE_SECRET_KEY` | `sk_live_xxx` | Stripe Dashboard → API Keys | Production secret key. Use `sk_test_xxx` for testing. |
| `STRIPE_WEBHOOK_SECRET` | `whsec_xxx` | Stripe Dashboard → Webhooks | Webhook signature verification (payment_intent.succeeded, invoice.payment_failed, etc.) |
| `STRIPE_PRICE_PRO` | `price_xxx` | Stripe Dashboard → Products | Pro tier price ID (e.g., $4.99/month) |
| `STRIPE_PRICE_BUSINESS` | `price_xxx` | Stripe Dashboard → Products | Business tier price ID (e.g., $14.99/month) |

#### CORS & Redirects

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `CORS_ORIGINS` | `["https://rateshift.app","https://www.rateshift.app","https://electricity-optimizer.vercel.app"]` | Manual | JSON array of allowed frontend origins. Include all Vercel preview domains + custom domains. |
| `ALLOWED_REDIRECT_DOMAINS` | `["rateshift.app","www.rateshift.app","localhost"]` | Manual | JSON array. Used by Stripe checkout/portal to validate redirects. |

#### Monitoring & Observability

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `SENTRY_DSN` | `https://key@o0.ingest.sentry.io/project-id` | Sentry Dashboard | Optional error tracking. If empty, errors not sent to Sentry. |
| `OTEL_ENABLED` | `true` | Manual | OpenTelemetry tracing. Set `true` in production for distributed tracing to Grafana Cloud Tempo. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `https://otlp-gateway-prod-us-east-2.grafana.net/otlp` | Grafana Cloud | OTLP gateway endpoint (Grafana Cloud Tempo). |
| `OTEL_EXPORTER_OTLP_HEADERS` | `Authorization=Basic <base64>` | Grafana Cloud / 1Password | OTLP auth header. Store in 1Password "Grafana Cloud OTLP". |

#### Notifications

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `ONESIGNAL_APP_ID` | String | OneSignal Dashboard | OneSignal app ID for push notifications. |
| `ONESIGNAL_REST_API_KEY` | String | OneSignal Dashboard → Settings → API Keys | OneSignal REST API key. Keep secret! |

#### AI Agent

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `GEMINI_API_KEY` | String | Google AI Studio | Gemini 3 Flash API key (free tier 10 RPM / 250 RPD). Get from https://aistudio.google.com. |
| `GROQ_API_KEY` | `gsk_xxx` | Groq Console | Groq Llama 3.3 70B API key (fallback, free tier 6K tok/min). Get from https://console.groq.com. |
| `COMPOSIO_API_KEY` | String | Composio Dashboard | Composio tools API key (free tier 1K actions/month). Get from https://composio.dev. |
| `ENABLE_AI_AGENT` | `true` | Manual | Feature flag. Set to `true` to enable AI agent endpoints. |

#### Compliance & Data

| Variable | Example | Source | Notes |
|----------|---------|--------|-------|
| `DATA_RESIDENCY` | `US` | Manual | Data residency region (US or EU) — affects compliance. |
| `CONSENT_REQUIRED` | `true` | Manual | Require user data consent before processing. |
| `DATA_RETENTION_DAYS` | `730` | Manual | Days to retain user data before cleanup (2 years). |

### Step 2.1: Create .env File

For local testing before deploying to Render, create a local `.env` file:

```bash
cat > backend/.env <<'EOF'
ENVIRONMENT=production
DEBUG=false
BACKEND_PORT=8000

DATABASE_URL=postgresql://neondb_owner:PASSWORD@ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require
DB_POOL_SIZE=3
DB_MAX_OVERFLOW=5
REDIS_URL=

JWT_SECRET=<32-byte-hex-from-1password>
INTERNAL_API_KEY=<32-byte-hex-from-1password>
BETTER_AUTH_SECRET=<32-byte-hex-from-1password>
BETTER_AUTH_URL=https://rateshift.app
FIELD_ENCRYPTION_KEY=<64-hex-from-openssl>
GITHUB_WEBHOOK_SECRET=<32-byte-hex>

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

FLATPEAK_API_KEY=
NREL_API_KEY=
EIA_API_KEY=
OPENWEATHERMAP_API_KEY=
UTILITYAPI_KEY=
OPENVOLT_API_KEY=
DIFFBOT_API_TOKEN=
TAVILY_API_KEY=
GOOGLE_MAPS_API_KEY=

RESEND_API_KEY=<from-1password>
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<gmail-address>
SMTP_PASSWORD=<app-password>
EMAIL_FROM_ADDRESS=RateShift <noreply@rateshift.app>
EMAIL_FROM_NAME=RateShift

STRIPE_SECRET_KEY=sk_live_<from-1password>
STRIPE_WEBHOOK_SECRET=<from-1password>
STRIPE_PRICE_PRO=price_<from-1password>
STRIPE_PRICE_BUSINESS=price_<from-1password>

CORS_ORIGINS=["https://rateshift.app","https://www.rateshift.app","https://electricity-optimizer.vercel.app"]
ALLOWED_REDIRECT_DOMAINS=["rateshift.app","www.rateshift.app","localhost"]

SENTRY_DSN=
OTEL_ENABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=

ONESIGNAL_APP_ID=
ONESIGNAL_REST_API_KEY=

GEMINI_API_KEY=
GROQ_API_KEY=
COMPOSIO_API_KEY=
ENABLE_AI_AGENT=true

DATA_RESIDENCY=US
CONSENT_REQUIRED=true
DATA_RETENTION_DAYS=730
EOF

# Never commit .env file
echo "backend/.env" >> .gitignore
```

### Step 2.2: Set Environment Variables on Render

Navigate to https://dashboard.render.com/services/srv-d649uhur433s73d557cg:

1. Click **Environment** tab
2. Add each variable from the list above
3. **Critical variables** (must be non-empty):
   - `DATABASE_URL`
   - `RESEND_API_KEY`
   - `STRIPE_SECRET_KEY`
   - `INTERNAL_API_KEY`
   - `JWT_SECRET`
   - `BETTER_AUTH_SECRET`
4. Click **Save** (Render will trigger an auto-redeploy)

Or use **Composio** to set env vars programmatically:

```bash
# Set multiple env vars via Composio RENDER_UPDATE_ENV_VAR
composio action execute RENDER_UPDATE_ENV_VAR \
  --input service_id=srv-d649uhur433s73d557cg \
  --input env_key=ENVIRONMENT \
  --input env_value=production

composio action execute RENDER_UPDATE_ENV_VAR \
  --input service_id=srv-d649uhur433s73d557cg \
  --input env_key=DATABASE_URL \
  --input env_value="postgresql://neondb_owner:PASSWORD@ep-withered-morning-aix83cfw-pooler..."
# ... repeat for each variable
```

### Step 2.3: Deploy Backend

**Option A: Manual Deploy via Render Dashboard**

1. Go to https://dashboard.render.com/services/srv-d649uhur433s73d557cg
2. Click **Manual Deploy** > **Deploy latest commit**
3. Wait for build to complete (5-10 minutes)
4. Check **Logs** tab for errors
5. Verify service status shows **Live**

**Option B: Trigger Deploy via GitHub Actions**

```bash
# Trigger the production deploy workflow with a version number
gh workflow run deploy-production.yml \
  --ref main \
  -f version=v1.0.0 \
  --repo JoeyJoziah/electricity-optimizer
```

**Option C: Trigger Deploy via Composio**

```bash
# Fetch the Render deploy hook URL
RENDER_DEPLOY_HOOK=$(op item get "GitHub Secrets" --vault "RateShift" --fields RENDER_DEPLOY_HOOK_BACKEND)

# Trigger the deploy
curl -X POST "$RENDER_DEPLOY_HOOK"
```

### Step 2.4: Verify Backend Health

```bash
# Wait for service to stabilize
sleep 30

# Health check
curl -fsS https://api.rateshift.app/health
# Expected output: {"status":"healthy","timestamp":"2026-03-11T00:00:00Z"}

# Check that API routes are reachable
curl -fsS https://api.rateshift.app/api/v1/prices/current \
  -H "Content-Type: application/json" \
  -d '{"region":"US_NY"}'
# Expected: 200 with price data (or 422 if region format is wrong — that's OK, means API works)

# Check logs on Render
open "https://dashboard.render.com/services/srv-d649uhur433s73d557cg"
# Look for "Application started" or similar success messages
```

---

## Layer 3: Frontend (Vercel + Next.js)

### Overview

- **Hosting**: Vercel (https://vercel.com)
- **Project**: `electricity-optimizer`
- **Custom domains**: `rateshift.app`, `www.rateshift.app`
- **Framework**: Next.js 16 + React 19 + TypeScript
- **Deployment**: Automatic on `main` branch push (or manual)
- **Environment variables**: 10+ (see list below)
- **Node version**: 18+ (Vercel uses latest LTS by default)

### Frontend Environment Variables (Vercel)

Create these on the Vercel dashboard under **Settings > Environment Variables**.

| Variable | Example | Scope | Source | Notes |
|----------|---------|-------|--------|-------|
| `NEXT_PUBLIC_APP_URL` | `https://rateshift.app` | Production | Manual | Public app URL (used by Better Auth) |
| `NEXT_PUBLIC_API_URL` | `/api/v1` | All | Manual | API path (proxied via Next.js rewrites to `BACKEND_URL`) |
| `NEXT_PUBLIC_CLARITY_PROJECT_ID` | String | Production | Microsoft Clarity Dashboard | Analytics project ID (optional) |
| `NEXT_PUBLIC_ONESIGNAL_APP_ID` | String | Production | OneSignal Dashboard | Push notification app ID (optional) |
| `NEXT_PUBLIC_OAUTH_GOOGLE_ENABLED` | `true` | Production | Manual | Show Google OAuth button (set to `true` if `GOOGLE_CLIENT_ID` is configured) |
| `NEXT_PUBLIC_OAUTH_GITHUB_ENABLED` | `true` | Production | Manual | Show GitHub OAuth button (set to `true` if `GITHUB_CLIENT_ID` is configured) |
| `BACKEND_URL` | `https://api.rateshift.app` | Production | Manual | Server-side backend URL (used by Next.js rewrites and API routes). **Production**: `https://api.rateshift.app`. **Development**: `http://localhost:8000`. |
| `DATABASE_URL` | `postgresql://neondb_owner:PASSWORD@ep-withered-morning-aix83cfw-pooler...` | Production | Neon Console | Neon connection string (used by Better Auth for session mgmt) |
| `BETTER_AUTH_SECRET` | 64-hex-char string | Production | Generate: `openssl rand -hex 32` | Session signing key (must match backend) |
| `BETTER_AUTH_URL` | `https://rateshift.app` | Production | Manual | Public frontend URL (for CORS/OAuth) |
| `RESEND_API_KEY` | `re_xxx` | Production | Resend Dashboard | Email API key (used for email verification, magic links, password reset) |
| `EMAIL_FROM_ADDRESS` | `RateShift <noreply@rateshift.app>` | Production | Manual | Sender email address (must match verified domain in Resend) |
| `GOOGLE_CLIENT_ID` | `xxx.apps.googleusercontent.com` | Production | Google Cloud Console | Google OAuth client ID (optional) |
| `GOOGLE_CLIENT_SECRET` | `GOCSPX-xxx` | Production | Google Cloud Console | Google OAuth client secret (optional) |
| `GITHUB_CLIENT_ID` | `Ov23li...` | Production | GitHub App settings | GitHub OAuth client ID (optional) |
| `GITHUB_CLIENT_SECRET` | `ghs_xxx` | GitHub App settings | GitHub OAuth client secret (optional) |
| `SMTP_HOST` | `smtp.gmail.com` | Production | Gmail Settings | SMTP host (for email fallback) |
| `SMTP_PORT` | `587` | Production | Gmail Settings | SMTP port |
| `SMTP_USERNAME` | `your-email@gmail.com` | Production | Gmail Settings | SMTP username |
| `SMTP_PASSWORD` | 16-char app password | Production | Gmail App Passwords | SMTP password (App Password, not Gmail password) |

### Step 3.1: Create .env.local for Local Development

```bash
cat > frontend/.env.local <<'EOF'
NEXT_PUBLIC_APP_URL=http://localhost:3000
NEXT_PUBLIC_API_URL=/api/v1
BACKEND_URL=http://localhost:8000
DATABASE_URL=postgresql://neondb_owner:PASSWORD@ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require
BETTER_AUTH_SECRET=<32-byte-hex>
BETTER_AUTH_URL=http://localhost:3000
RESEND_API_KEY=<from-1password>
EMAIL_FROM_ADDRESS=RateShift <noreply@rateshift.app>
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<gmail-address>
SMTP_PASSWORD=<app-password>
EOF

echo "frontend/.env.local" >> .gitignore
```

### Step 3.2: Set Environment Variables on Vercel

Navigate to https://vercel.com/electricity-optimizer/settings/environment-variables:

1. Click **+ Add New** for each variable
2. Set **Environment** to **Production** (separate from Preview/Development if needed)
3. Paste value
4. Click **Save**

Repeat for all variables in the table above.

### Step 3.3: Install Dependencies

```bash
cd frontend
npm install

# Verify .npmrc has legacy-peer-deps=true (required for eslint-config-next 16.x + eslint 8)
cat .npmrc
# Output should include: legacy-peer-deps=true
```

If `.npmrc` is missing the setting:

```bash
echo "legacy-peer-deps=true" >> frontend/.npmrc
```

### Step 3.4: Build & Test Locally

```bash
cd frontend

# Build (same as Vercel)
npm run build
# Expected: ✓ Compiled successfully. No TypeScript errors.

# Run local dev server
npm run dev
# Expected: ✓ Ready in 1.5s. Visit http://localhost:3000
```

### Step 3.5: Deploy to Vercel

**Option A: Automatic Deploy (Push to main)**

```bash
git add .
git commit -m "Deploy frontend to production"
git push origin main

# Vercel will automatically build and deploy.
# Watch progress: https://vercel.com/electricity-optimizer
```

**Option B: Manual Deploy via Vercel CLI**

```bash
# Install Vercel CLI
npm install -g vercel

# Run from repo root (NOT from frontend/ directory)
cd /Users/devinmcgrath/projects/electricity-optimizer

# Deploy to production
npx vercel --prod --archive=tgz

# Note: Use --archive=tgz to work around Vercel's 5000 requests rate limit on free plan
```

**Option C: Manual Deploy via Vercel Dashboard**

1. Go to https://vercel.com/electricity-optimizer
2. Find the latest commit in the deployment list
3. Click **Redeploy** or wait for automatic deployment
4. Check **Deployments** tab for progress

### Step 3.6: Verify Frontend Deployment

```bash
# Check that frontend is live
curl -sI https://rateshift.app | head -1
# Expected: HTTP/2 200

# Verify security headers are present
curl -sI https://rateshift.app | grep -E "(X-Frame|Content-Security|Strict-Transport)"
# Expected: X-Frame-Options, Content-Security-Policy, Strict-Transport-Security

# Check that API proxy works (redirects to backend)
curl -sI https://rateshift.app/api/v1/prices/current | head -1
# Expected: HTTP/2 200 or 422 (means proxy works)

# Open in browser
open https://rateshift.app
# Should see login page with no errors
```

---

## Layer 4: Edge Layer (Cloudflare Worker)

### Overview

- **Worker name**: `rateshift-api-gateway`
- **Route**: `api.rateshift.app/*`
- **Zone**: `ac03dd28616da6d1c4b894c298c1da58` (rateshift.app)
- **Account ID**: `b41be0d03c76c0b2cc91efccdb7a10df`
- **Language**: TypeScript + Cloudflare Workers API
- **KV Namespaces**: 2 (CACHE + RATE_LIMIT)
- **Build**: `npm run deploy` (wrangler v3)
- **Secrets**: 2 (INTERNAL_API_KEY, RATE_LIMIT_BYPASS_KEY)

### Worker Features

- **2-tier caching**: Cache API (long-lived responses) + KV (rate limit tokens)
- **Rate limiting**: 120/min standard, 30/min strict, 600/min internal
- **Bot detection**: Heuristic scoring (user-agent, headers, patterns)
- **Internal auth**: Constant-time comparison of X-API-Key header
- **CORS**: Origin allowlist (rateshift.app, www.rateshift.app)
- **Security headers**: HSTS, X-Content-Type-Options, X-Frame-Options
- **Structured logging**: JSON logs with timestamp, method, path, status, cache status

### Step 4.1: Verify Cloudflare Configuration

```bash
# Verify zone is correct
dig api.rateshift.app NS +short

# Expected output: Cloudflare nameservers (ns-xxx.ns.cloudflare.com)

# Verify DNS record for api subdomain
dig api.rateshift.app CNAME +short

# Expected: electricity-optimizer.onrender.com (proxied via orange cloud)

# Verify Worker is deployed
curl -sI https://api.rateshift.app/health | grep -i "cf-cache-status"

# Expected: CF-Cache-Status: HIT or MISS (confirms Worker is active)
```

### Step 4.2: Set Secrets

Store the following secrets in Cloudflare Workers:

```bash
# Install wrangler CLI
npm install -g wrangler

# Authenticate with Cloudflare (will open browser)
wrangler login

# Set secrets
cd workers/api-gateway

# INTERNAL_API_KEY (used to authenticate internal requests from GHA cron jobs)
wrangler secret put INTERNAL_API_KEY
# Paste the value from 1Password "GitHub Secrets" item

# RATE_LIMIT_BYPASS_KEY (optional — allows bypassing rate limits for internal requests)
wrangler secret put RATE_LIMIT_BYPASS_KEY
# Generate a new secret: openssl rand -hex 32
```

### Step 4.3: Create KV Namespaces (If Not Exists)

Check if KV namespaces already exist:

```bash
# List all KV namespaces in the account
wrangler kv:namespace list

# Expected output includes:
# - CACHE (id: 6946d19ce8264f6fae4481d6ad8afcd1)
# - RATE_LIMIT (id: c9be3741ee784956a0d99b3fa0c1d6c4)
```

If namespaces don't exist, create them:

```bash
# Create CACHE namespace
wrangler kv:namespace create "CACHE"

# Create RATE_LIMIT namespace
wrangler kv:namespace create "RATE_LIMIT"

# Note the IDs and update wrangler.toml
```

Update `workers/api-gateway/wrangler.toml`:

```toml
kv_namespaces = [
  { binding = "CACHE", id = "6946d19ce8264f6fae4481d6ad8afcd1" },
  { binding = "RATE_LIMIT", id = "c9be3741ee784956a0d99b3fa0c1d6c4" }
]
```

### Step 4.4: Configure Environment Variables

Verify `workers/api-gateway/wrangler.toml` has correct values:

```toml
[vars]
ORIGIN_URL = "https://electricity-optimizer.onrender.com"
ALLOWED_ORIGINS = "https://rateshift.app,https://www.rateshift.app"
RATE_LIMIT_STANDARD = "120"
RATE_LIMIT_STRICT = "30"
RATE_LIMIT_INTERNAL = "600"
RATE_LIMIT_WINDOW_SECONDS = "60"
```

### Step 4.5: Deploy Worker

```bash
cd workers/api-gateway

# Install dependencies
npm install

# Test locally (optional)
npm run test

# Deploy to production
npm run deploy

# Or use wrangler directly
wrangler deploy

# Expected output: "Uploading worker" and "SUCCESS"
```

### Step 4.6: Verify Worker Deployment

```bash
# Health check
curl -fsS https://api.rateshift.app/health
# Expected: {"status":"healthy","timestamp":"2026-03-11T00:00:00Z"}

# Check cache headers (should show CF cache status)
curl -sI https://api.rateshift.app/health | grep -i "cf-cache"

# Expected: CF-Cache-Status: HIT (after first request)

# Test rate limiting by making 121 rapid requests
for i in {1..121}; do
  curl -s -o /dev/null -w "%{http_code}\n" https://api.rateshift.app/health
done

# Expected: First 120 = 200, then 429 (Too Many Requests)

# Test internal authentication
curl -sI -H "X-API-Key: invalid" https://api.rateshift.app/health | head -1
# Expected: HTTP/2 401 Unauthorized

curl -sI -H "X-API-Key: $(op item get 'GitHub Secrets' --vault 'RateShift' --fields INTERNAL_API_KEY)" https://api.rateshift.app/health | head -1
# Expected: HTTP/2 200 OK
```

---

## Post-Deployment Verification

### Comprehensive Health Check

Run this script **after all 4 layers are deployed**:

```bash
#!/bin/bash
# verify-deployment.sh

set -e

echo "===== RateShift Deployment Verification ====="
echo ""

# 1. Database
echo "1. DATABASE (Neon PostgreSQL)"
echo "   Endpoint: ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech"
NEON_PASSWORD=$(op item get "Neon PostgreSQL" --vault "RateShift" --fields password)
export PGPASSWORD="$NEON_PASSWORD"
TABLE_COUNT=$(psql -h ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech -U neondb_owner -d neondb -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tail -1 | xargs)
echo "   ✓ Tables in public schema: $TABLE_COUNT (expected: 33+)"
unset PGPASSWORD

# 2. Backend
echo ""
echo "2. BACKEND (Render + FastAPI)"
echo "   URL: https://api.rateshift.app"
HEALTH=$(curl -fsS https://api.rateshift.app/health 2>/dev/null || echo '{"error":"unreachable"}')
echo "   ✓ Health response: $HEALTH"

# 3. Frontend
echo ""
echo "3. FRONTEND (Vercel + Next.js)"
echo "   URL: https://rateshift.app"
FE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://rateshift.app)
echo "   ✓ Status code: $FE_STATUS (expected: 200)"

# 4. Worker
echo ""
echo "4. EDGE LAYER (Cloudflare Worker)"
echo "   Route: api.rateshift.app/*"
WORKER_STATUS=$(curl -sI https://api.rateshift.app/health 2>/dev/null | grep "cf-cache-status" | awk '{print $2}' | tr -d '\r')
echo "   ✓ CF-Cache-Status: $WORKER_STATUS (expected: HIT or MISS)"

# 5. DNS
echo ""
echo "5. DNS VERIFICATION"
echo "   rateshift.app CNAME:"
dig rateshift.app CNAME +short
echo "   api.rateshift.app CNAME:"
dig api.rateshift.app CNAME +short

# 6. API Proxy
echo ""
echo "6. API PROXY (Frontend → Backend)"
PROXY_TEST=$(curl -sI https://rateshift.app/api/v1/prices/current 2>/dev/null | head -1)
echo "   ✓ Proxy test: $PROXY_TEST (expected: HTTP/2 200 or 422)"

echo ""
echo "===== All Layers Verified ====="
```

Run the verification script:

```bash
chmod +x /tmp/verify-deployment.sh
/tmp/verify-deployment.sh
```

### Expected Outcomes

After full deployment, you should see:

| Component | Check | Expected |
|-----------|-------|----------|
| Database | Table count | 33+ tables in public schema |
| Backend | `/health` endpoint | `200 OK`, `{"status":"healthy"}` |
| Frontend | Homepage | `200 OK`, login page renders |
| Worker | CF-Cache-Status | `HIT` or `MISS` header present |
| DNS | `dig rateshift.app` | Returns Vercel CNAME |
| DNS | `dig api.rateshift.app` | Returns orange cloud proxy |
| API Proxy | `/api/v1/prices/current` | `200` or `422` (not `404`) |

---

## Cron Jobs & Automation

### Overview

12 scheduled workflows in `.github/workflows/`:

| Workflow | Schedule | Purpose | Endpoint | Notes |
|----------|----------|---------|----------|-------|
| `check-alerts.yml` | Every 30 min | Price threshold alerts | `POST /internal/check-alerts` | Dedup with cooldown windows |
| `fetch-weather.yml` | Every 6 hours (offset :15) | Weather data sync | `POST /internal/fetch-weather` | Parallelized with Semaphore(10) |
| `market-research.yml` | Daily 2am UTC | Market intelligence | `POST /internal/market-research` | Tavily + Diffbot |
| `sync-connections.yml` | Every 2 hours | UtilityAPI auto-sync | `POST /internal/sync-connections` | Auto-discovers connections |
| `scrape-rates.yml` | Daily 3am UTC | Rate auto-discovery | `POST /internal/scrape-rates` | Auto-discovers suppliers |
| `dunning-cycle.yml` | Daily 7am UTC | Stripe payment escalation | `POST /internal/dunning-cycle` | 7-day grace period |
| `kpi-report.yml` | Daily 6am UTC | Business metrics | `POST /internal/kpi-report` | Posts to Slack #metrics |
| `db-maintenance.yml` | Weekly Sunday 3am | DB optimization | `POST /internal/maintenance/cleanup` | VACUUM, ANALYZE, reindex |
| `self-healing-monitor.yml` | Daily 9am UTC | Workflow health check | Matrix over 13 workflows | Auto-creates GitHub issues |
| `E2E-tests.yml` | Daily 1am UTC | Playwright E2E tests | N/A (local) | Runs against production |
| `model-retrain.yml` | Weekly Sunday 5am | ML model retraining | `POST /internal/model-retrain` | Adaptive learning |
| `data-health-check.yml` | Daily 4am | Table health metrics | `GET /internal/health-data` | Flags empty critical tables |

### Manual Workflow Triggers

Verify all cron workflows are enabled and correctly triggering:

```bash
# Fetch the workflow file to check schedule
cat .github/workflows/check-alerts.yml | grep -A 2 "schedule:"

# Expected output:
# schedule:
#   - cron: '*/30 * * * *'  # Every 30 minutes

# Manually trigger a workflow (useful for testing after deployment)
gh workflow run check-alerts.yml --repo JoeyJoziah/electricity-optimizer

# Check workflow run history
gh run list --workflow=check-alerts.yml --repo JoeyJoziah/electricity-optimizer

# Tail the latest run logs
gh run view $(gh run list --workflow=check-alerts.yml --limit 1 --json databaseId -q '.[0].databaseId' --repo JoeyJoziah/electricity-optimizer) --log --repo JoeyJoziah/electricity-optimizer
```

### Critical: Verify INTERNAL_API_KEY

All cron workflows use `X-API-Key: ${{ secrets.INTERNAL_API_KEY }}` header. If cron jobs return 401:

```bash
# Check that the secret is set in GitHub
gh secret list --repo JoeyJoziah/electricity-optimizer | grep INTERNAL_API_KEY

# Verify the value matches between:
# 1. 1Password vault "RateShift" → "GitHub Secrets" item
# 2. GitHub Actions secrets
# 3. Render env var INTERNAL_API_KEY
# 4. Cloudflare Worker secret INTERNAL_API_KEY

# If they don't match, update all:
INTERNAL_API_KEY=$(openssl rand -hex 32)

# GitHub Actions
gh secret set INTERNAL_API_KEY --body "$INTERNAL_API_KEY" --repo JoeyJoziah/electricity-optimizer

# Render backend
curl -X PATCH \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  https://api.render.com/v1/services/srv-d649uhur433s73d557cg \
  -d "{ \"envVars\": { \"INTERNAL_API_KEY\": \"$INTERNAL_API_KEY\" } }"

# Cloudflare Worker
cd workers/api-gateway
wrangler secret put INTERNAL_API_KEY
# Paste: $INTERNAL_API_KEY
```

### Cron Job Manual Testing

```bash
# Test a specific endpoint with internal auth
INTERNAL_API_KEY=$(op item get "GitHub Secrets" --vault "RateShift" --fields INTERNAL_API_KEY)

curl -X POST https://api.rateshift.app/internal/check-alerts \
  -H "X-API-Key: $INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{}"

# Expected: 200 OK with alert results

# Test with wrong key (should fail)
curl -X POST https://api.rateshift.app/internal/check-alerts \
  -H "X-API-Key: invalid" \
  -H "Content-Type: application/json" \
  -d "{}"

# Expected: 401 Unauthorized
```

---

## Rollback Procedures

### Database Rollback

**WARNING**: Database migrations use `IF NOT EXISTS` and cannot be automatically reversed. Always test migrations in a non-production branch first.

If a migration causes issues:

1. **Identify the problematic migration** by checking Neon logs or error messages
2. **Create a reverse migration** that undoes the change:

```bash
# Example: If migration 033_model_predictions_ab_assignments.sql added bad column
cat > backend/migrations/034_rollback_model_predictions.sql <<'EOF'
-- Rollback migration 033
BEGIN;

ALTER TABLE model_predictions DROP COLUMN IF EXISTS bad_column CASCADE;

COMMIT;
EOF
```

3. **Apply the reverse migration**:

```bash
psql "$NEON_CONNECTION" -f backend/migrations/034_rollback_model_predictions.sql
```

4. **Verify the schema is correct**:

```bash
psql "$NEON_CONNECTION" -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'model_predictions';"
```

### Backend Rollback

Render auto-rolls back if smoke tests fail, but you can also manually rollback:

**Option A: Automatic Rollback**

Smoke tests in `deploy-production.yml` automatically trigger rollback on failure:

```yaml
smoke-tests:
  - name: Verify health endpoint
    uses: ./.github/actions/retry-curl
    with:
      url: ${{ secrets.PROD_API_URL }}/health
      # If this fails, rollback job runs automatically
```

**Option B: Manual Rollback via Render Dashboard**

1. Go to https://dashboard.render.com/services/srv-d649uhur433s73d557cg
2. Click **Deployments** tab
3. Find the last **Live** (successful) deployment before the failed one
4. Click **Rollback**
5. Render will immediately serve the previous version

**Option C: Manual Rollback via Render API**

```bash
RENDER_API_KEY=$(op item get "Render API Key" --vault "RateShift" --fields api_key)

# Get the last successful deploy ID
DEPLOY_ID=$(curl -fsS \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  https://api.render.com/v1/services/srv-d649uhur433s73d557cg/deploys?limit=10 \
  | jq -r '[.[] | select(.deploy.status == "live")] | .[0].deploy.id')

# Rollback to that deploy
curl -X POST \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  https://api.render.com/v1/services/srv-d649uhur433s73d557cg/deploys/$DEPLOY_ID/rollback
```

### Frontend Rollback

**Option A: Vercel Dashboard**

1. Go to https://vercel.com/electricity-optimizer/deployments
2. Find the last **Ready** (successful) deployment
3. Click the **...** menu
4. Select **Rollback to this Deployment**
5. Vercel will immediately serve the previous version

**Option B: Vercel CLI**

```bash
# List recent deployments
vercel deployments --repo=electricity-optimizer

# Rollback to a specific deployment
vercel rollback <deployment-url>
```

### Worker Rollback

**Option A: Redeploy Previous Commit**

```bash
# Check out the previous commit
git log --oneline workers/api-gateway/ | head -5
git checkout <previous-commit> workers/api-gateway/

# Redeploy
cd workers/api-gateway
npm run deploy
```

**Option B: Cloudflare Dashboard**

1. Go to https://dash.cloudflare.com → Workers & Pages → rateshift-api-gateway
2. Click **Deployments**
3. Find the last successful deployment
4. Click **Rollback** or **Retry**

---

## Troubleshooting

### Common Issues & Solutions

#### Issue: Database Connection Timeout

**Symptoms**: Backend logs show `ConnectionRefusedError` or `timeout connecting to Neon`

**Cause**: DATABASE_URL is stale, pooled endpoint is overloaded, or network firewall blocking

**Solution**:

```bash
# 1. Verify DATABASE_URL format
echo $DATABASE_URL
# Expected: postgresql://neondb_owner:PASSWORD@ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require

# 2. Test connection locally
PGPASSWORD="<password>" psql -h ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech -U neondb_owner -d neondb -c "SELECT 1;"

# 3. If local connection fails:
#    - Check Neon console for active connections (Settings → Connections)
#    - Scale down pool size: DB_POOL_SIZE=2, DB_MAX_OVERFLOW=2
#    - Refresh Neon password if stale (>90 days)

# 4. Redeploy backend with updated DATABASE_URL
curl -X POST "$RENDER_DEPLOY_HOOK"
```

#### Issue: Cron Workflows Return 401 Unauthorized

**Symptoms**: Check logs show `401 Unauthorized` for `/internal/*` endpoints

**Cause**: `INTERNAL_API_KEY` secret mismatch between GitHub, Render, Cloudflare, and 1Password

**Solution**:

```bash
# 1. Verify the key in 1Password
op item get "GitHub Secrets" --vault "RateShift" --fields INTERNAL_API_KEY

# 2. Check GitHub Actions secret
gh secret list --repo JoeyJoziah/electricity-optimizer | grep INTERNAL_API_KEY

# 3. If they don't match, update GitHub
INTERNAL_API_KEY=$(op item get "GitHub Secrets" --vault "RateShift" --fields INTERNAL_API_KEY)
gh secret set INTERNAL_API_KEY --body "$INTERNAL_API_KEY" --repo JoeyJoziah/electricity-optimizer

# 4. Update Render (via dashboard or API)
# 5. Update Cloudflare Worker secret
cd workers/api-gateway && wrangler secret put INTERNAL_API_KEY

# 6. Re-trigger workflow
gh workflow run check-alerts.yml --repo JoeyJoziah/electricity-optimizer
```

#### Issue: Frontend 404 on API Routes

**Symptoms**: Requests to `/api/v1/*` return 404 instead of routing to backend

**Cause**: Next.js rewrites not configured, or `BACKEND_URL` incorrect

**Solution**:

```bash
# 1. Verify rewrites in next.config.js
cat frontend/next.config.js | grep -A 10 "rewrites"

# Expected: async rewrites() { return { beforeFiles: [ { source: '/api/v1/:path*', destination: ...

# 2. Check BACKEND_URL on Vercel
vercel env list --production

# Expected: BACKEND_URL=https://api.rateshift.app

# 3. If missing, set it:
vercel env add BACKEND_URL "https://api.rateshift.app" --production

# 4. Redeploy frontend
npx vercel --prod

# 5. Test proxy
curl -sI https://rateshift.app/api/v1/prices/current
# Expected: 200 or 422 (not 404)
```

#### Issue: Email Sending Fails Silently

**Symptoms**: No error logs, but emails never arrive

**Cause**: `RESEND_API_KEY` not set, or domain not verified in Resend

**Solution**:

```bash
# 1. Check RESEND_API_KEY on Render
curl -s https://api.rateshift.app/health | grep resend || echo "Check Render env vars directly"

# 2. Verify on Render dashboard
# Settings → Environment → RESEND_API_KEY should be non-empty

# 3. Verify domain is verified in Resend
# Go to https://resend.com/domains → check rateshift.app status

# 4. If domain not verified:
#    - Add DNS records: SPF, DKIM, DMARC (see DNS_EMAIL_SETUP.md Step 3)
#    - Click "Verify" in Resend dashboard
#    - Wait for verification (usually 5-10 min)

# 5. Test email sending
curl -X POST https://api.rateshift.app/api/v1/email/send \
  -H "Content-Type: application/json" \
  -d '{"to":"test@gmail.com","subject":"Test","body":"Hello"}'

# Expected: 200 OK with email sent message
```

#### Issue: Worker Rate Limiting Too Strict

**Symptoms**: Legitimate traffic gets 429 Too Many Requests

**Cause**: Rate limit thresholds too low, or legitimate traffic from single IP

**Solution**:

```bash
# 1. Check current limits in wrangler.toml
cat workers/api-gateway/wrangler.toml | grep RATE_LIMIT

# Expected:
# RATE_LIMIT_STANDARD = "120"    # 120 requests per minute
# RATE_LIMIT_STRICT = "30"
# RATE_LIMIT_INTERNAL = "600"

# 2. Increase limits if needed
# Edit wrangler.toml and redeploy:
sed -i 's/RATE_LIMIT_STANDARD = "120"/RATE_LIMIT_STANDARD = "500"/g' workers/api-gateway/wrangler.toml
cd workers/api-gateway && npm run deploy

# 3. For internal traffic, use X-API-Key to bypass limits
curl -H "X-API-Key: $INTERNAL_API_KEY" https://api.rateshift.app/health
```

#### Issue: TypeScript Errors During Build

**Symptoms**: `npm run build` fails with `TS errors` in frontend or `mypy` in backend

**Solution - Frontend**:

```bash
cd frontend

# 1. Check Node version
node --version  # expect 18+

# 2. Check .npmrc has legacy-peer-deps
cat .npmrc | grep legacy-peer-deps
# If missing, add it:
echo "legacy-peer-deps=true" >> .npmrc

# 3. Clean install
rm -rf node_modules package-lock.json
npm install

# 4. Build again
npm run build

# 5. If still failing, check tsconfig.json for strict=true
# Relax if needed for quick fix (but restore before commit):
cat tsconfig.json | grep strict
```

**Solution - Backend**:

```bash
cd backend

# 1. Check Python version
python3 --version  # expect 3.12

# 2. Install deps
.venv/bin/python -m pip install -e .

# 3. Run type check
.venv/bin/python -m mypy backend --ignore-missing-imports

# 4. If errors, check pyproject.toml [tool.mypy]
# Relax if needed for quick fix
```

---

## Known Gotchas

### 1. Neon MCP Limitation: One Statement Per Call

**Issue**: `mcp__Neon__run_sql` can only execute ONE SQL statement per call. Multi-statement transactions fail silently.

**Workaround**: Use 1Password CLI + psycopg2 for batch migrations:

```bash
# WRONG (will fail silently or run only first statement):
mcp__Neon__run_sql \
  projectId="cold-rice-23455092" \
  sql="BEGIN; CREATE TABLE foo (...); CREATE TABLE bar (...); COMMIT;"

# RIGHT (use psycopg2):
psql "$NEON_CONNECTION" -f migration.sql  # Handles multi-statement
```

### 2. GHA Deploy Requires Production Environment Approval

**Issue**: `deploy-production.yml` requires approval in the **production** environment before running.

**Workaround**:

```bash
# Set approval rules in GitHub repo Settings → Environments → production
# Add yourself as an approver (or use a team)

# When workflow runs, it will wait for approval before deploying
# Approve via: Actions tab → workflow → review deployments
```

### 3. Vercel CLI 5000-Request Limit (Free Plan)

**Issue**: `npx vercel --prod` may hit rate limit on free Vercel plan

**Workaround**: Use `--archive=tgz` flag to compress upload:

```bash
npx vercel --prod --archive=tgz

# Or use GitHub push (automatic deployment) instead
git push origin main
```

### 4. Render `render.yaml` sync:false

**Issue**: Environment variables declared in `render.yaml` with `sync: false` are NOT automatically synced. They must be set manually or via API.

**Workaround**: Never use `render.yaml` for secrets. Set all env vars in Render dashboard or via REST API:

```bash
# Render dashboard: Services → srv-d649uhur433s73d557cg → Environment

# Or API:
RENDER_API_KEY=$(op item get "Render API Key" --vault "RateShift" --fields api_key)

# API does NOT exist for bulk env var updates; use dashboard or CLI
```

### 5. Frontend `.npmrc` Legacy Peer Deps Required

**Issue**: eslint-config-next 16.x requires eslint 9, but eslint 8 is installed, causing `ERESOLVE` errors.

**Workaround**: Add `legacy-peer-deps=true` to `frontend/.npmrc`:

```
legacy-peer-deps=true
```

This allows eslint 8 to coexist with eslint-config-next 16.x.

### 6. Better Auth Session Cookie HTTPS-only

**Issue**: Session cookie (`__Secure-better-auth.session_token`) won't be set on HTTP, causing 401 on localhost.

**Workaround**: For local dev, use `http://localhost:3000` (cookie allows plain HTTP for localhost). For production, use HTTPS (automatic via Vercel + Cloudflare).

### 7. 1Password Vault Multi-Item Ambiguity

**Issue**: `op item get` by title fails if multiple items have the same name.

**Workaround**: Query by ID instead:

```bash
# List items with title "API Keys"
op item list --vault "RateShift" | grep "API Keys"

# Get by ID
op item get "<item-id>" --vault "RateShift"
```

### 8. Stripe Payment Failed Webhook User Resolution

**Issue**: Invoice webhook events don't include user ID, so webhook handler must look up user by `stripe_customer_id`.

**Workaround**: Backend has `UserRepository.get_by_stripe_customer_id(stripe_customer_id)` method. Use this in webhook handler:

```python
# backend/api/v1/webhooks.py
user = await user_repository.get_by_stripe_customer_id(invoice["customer"])
if not user:
    return {"error": "User not found"}
```

### 9. Data Retention: No pg_cron on Neon

**Issue**: Neon doesn't support `pg_cron` extension, so scheduled database cleanup must happen externally.

**Workaround**: Use GHA cron workflow to call `/internal/maintenance/cleanup` endpoint:

```yaml
# .github/workflows/db-maintenance.yml
schedule:
  - cron: '0 3 * * 0'  # Weekly Sunday 3am UTC

jobs:
  cleanup:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/retry-curl
        with:
          url: ${{ secrets.PROD_API_URL }}/internal/maintenance/cleanup
          method: POST
          headers: 'X-API-Key: ${{ secrets.INTERNAL_API_KEY }}'
```

### 10. Cloudflare Worker Secrets Not in Code

**Issue**: Worker secrets (INTERNAL_API_KEY, RATE_LIMIT_BYPASS_KEY) cannot be stored in the repository.

**Workaround**: Set secrets via `wrangler secret put` CLI, and reference by name in code:

```typescript
// workers/api-gateway/src/index.ts
const INTERNAL_API_KEY = env.INTERNAL_API_KEY;  // Set via wrangler secret put
```

### 11. CORS_ORIGINS JSON Array Parsing

**Issue**: Render's config parser accepts both JSON array and comma-separated string, but JSON is unambiguous.

**Workaround**: Always use JSON array format in env vars:

```
CORS_ORIGINS=["https://rateshift.app","https://www.rateshift.app"]

# NOT:
CORS_ORIGINS=https://rateshift.app,https://www.rateshift.app
```

### 12. Rate Limit Bypass for Cron Jobs

**Issue**: Internal cron jobs may legitimately trigger high request volume, causing rate limiting.

**Workaround**: Use X-API-Key header to identify internal requests and bypass rate limits:

```bash
# Cron job with internal key (bypasses rate limits)
curl -X POST \
  -H "X-API-Key: $INTERNAL_API_KEY" \
  https://api.rateshift.app/internal/fetch-weather

# User request (subject to rate limits)
curl -X GET https://api.rateshift.app/prices/current
```

---

## Summary Checklist

### Pre-Deployment

- [ ] Access verified to: Neon, Render, Vercel, Cloudflare, GitHub, 1Password
- [ ] All local tools installed: Node 18+, Python 3.12, psycopg2, wrangler, gh, op
- [ ] DNS configured per `/docs/DNS_EMAIL_SETUP.md`
- [ ] Cloudflare zone active for rateshift.app

### Layer 1: Database

- [ ] All 34 migrations applied to Neon production branch
- [ ] Database schema verified: 33+ public tables, 9 neon_auth tables
- [ ] Indexes verified: 40+ indexes present
- [ ] Permissions verified: All tables owned by neondb_owner

### Layer 2: Backend

- [ ] All 38 environment variables set on Render dashboard
- [ ] `RESEND_API_KEY` verified non-empty
- [ ] `STRIPE_SECRET_KEY` verified non-empty
- [ ] Backend deployed and health check passing
- [ ] `/health` endpoint returns 200 OK
- [ ] Logs show "Application started"

### Layer 3: Frontend

- [ ] All 10+ environment variables set on Vercel dashboard
- [ ] `BACKEND_URL=https://api.rateshift.app` verified
- [ ] Frontend built without TypeScript errors
- [ ] Frontend deployed and reachable at https://rateshift.app
- [ ] API proxy test passes: `/api/v1/prices/current` returns 200 or 422

### Layer 4: Edge Layer

- [ ] KV namespaces created: CACHE, RATE_LIMIT
- [ ] Secrets set: INTERNAL_API_KEY, RATE_LIMIT_BYPASS_KEY
- [ ] Worker deployed and health check passing
- [ ] CF-Cache-Status header present
- [ ] Rate limiting verified (120/min standard)

### Post-Deployment

- [ ] All 4 layers verified via comprehensive health check script
- [ ] Cron workflows manually triggered and passing
- [ ] Email sending tested end-to-end
- [ ] OAuth tested (if configured)
- [ ] Stripe webhooks tested (if configured)
- [ ] SSL certificates verified (HTTPS working)
- [ ] Security headers verified (HSTS, CSP, X-Frame-Options)

### Monitoring

- [ ] Monitoring dashboard open and healthy
- [ ] Slack notifications configured for deployments and incidents
- [ ] Sentry error tracking configured (if SENTRY_DSN set)
- [ ] Cron job monitoring enabled

---

## Appendix: Quick Reference

### Critical URLs

- Neon Console: https://console.neon.tech/app/projects/cold-rice-23455092
- Render Dashboard: https://dashboard.render.com/services/srv-d649uhur433s73d557cg
- Vercel Dashboard: https://vercel.com/electricity-optimizer
- Cloudflare Dashboard: https://dash.cloudflare.com (zone: ac03dd28616da6d1c4b894c298c1da58)
- GitHub Repo: https://github.com/JoeyJoziah/electricity-optimizer
- 1Password Vault: https://start.1password.com (vault: "RateShift")

### Critical Commands

```bash
# Fetch any secret from 1Password
op item get "<item-name>" --vault "RateShift" --fields "<field-name>"

# Trigger GitHub Actions workflow
gh workflow run <workflow-name> --repo JoeyJoziah/electricity-optimizer

# Deploy backend
curl -X POST "$RENDER_DEPLOY_HOOK_BACKEND"

# Deploy frontend
npx vercel --prod --archive=tgz

# Deploy worker
cd workers/api-gateway && npm run deploy

# Test API endpoint
curl -H "X-API-Key: $INTERNAL_API_KEY" https://api.rateshift.app/health
```

### Critical Endpoints

```
Health:       GET  https://api.rateshift.app/health
Prices:       GET  https://api.rateshift.app/api/v1/prices/current
Alerts:       POST https://api.rateshift.app/internal/check-alerts
Weather:      POST https://api.rateshift.app/internal/fetch-weather
Connections:  GET  https://api.rateshift.app/api/v1/connections
Settings:     GET  https://api.rateshift.app/api/v1/user/profile
```

---

**END OF REDEPLOYMENT RUNBOOK**

> **Last Updated**: 2026-03-11
> **Author**: Deployment Engineering Team
> **Status**: Production-Ready
> **Next Review**: 2026-04-11
