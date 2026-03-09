# Monitoring & Status Page

## Overview

The Electricity Optimizer uses a multi-layer monitoring stack, all on free tiers.

## UptimeRobot (Primary Uptime Monitoring)

**Free tier**: 50 monitors, 5-min checks, email/webhook alerts. No card required.

### Monitors

| # | Name | URL | Type |
|---|------|-----|------|
| 1 | Backend Health | `https://electricity-optimizer.onrender.com/health` | HTTP |
| 2 | Frontend | `https://electricity-optimizer.vercel.app` | HTTP |
| 3 | Neon DB Ping | `https://ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech` | Ping |
| 4 | API Smoke Test | `https://electricity-optimizer.onrender.com/api/v1/prices/current?region=US` | HTTP |
| 5 | SSL Certificate | Vercel domain | SSL expiry |

### Setup

1. Create account at https://uptimerobot.com (free, no card)
2. Add monitors from the table above
3. Configure email alerts for downtime
4. Optional: Set `UPTIMEROBOT_API_KEY` in backend `.env` for programmatic access

## Better Stack (Status Page + Incident Logs)

**Free tier**: 10 monitors, 1 status page, 3GB logs, 3-min checks. No card required.

### Monitors

| # | Name | URL | Check Interval |
|---|------|-----|----------------|
| 1 | Backend Health | `https://electricity-optimizer.onrender.com/health` | 3 min |
| 2 | Frontend | `https://electricity-optimizer.vercel.app` | 3 min |
| 3 | API Endpoint | `https://electricity-optimizer.onrender.com/api/v1/prices/current?region=US` | 3 min |

### Status Page

- Public URL: Set up via Better Stack dashboard
- Shows real-time status of all monitored services
- Incident history and maintenance windows

### Setup

1. Create account at https://betterstack.com (free, no card)
2. Create a status page with project branding
3. Add monitors from the table above

## Wachete (Supplier Rate Change Detection)

**Free tier**: 5 monitors, 24-hour check frequency. No card required.

### Monitors

Set up 5 monitors for the highest-traffic supplier rate pages. Wachete detects
text/content changes and can trigger webhooks.

### Setup

1. Create account at https://www.wachete.com (free, no card)
2. Select top 5 supplier rate pages from the `suppliers` table (where `api_available = true`)
3. Configure text change detection on pricing sections
4. Optional: Set webhook to `POST /api/v1/internal/scrape-rates` to trigger Diffbot extraction on change

## Automated Alert Workflows (Phase 1 — Live)

Three Rube MCP recipes provide automated monitoring notifications via Composio integrations.

| Workflow | Recipe ID | Schedule | Action |
|----------|-----------|----------|--------|
| Sentry→Slack Bridge | `rcp_sQ1NKouFdXIe` | Every 15 min | Fetches unresolved Sentry issues, classifies by severity, posts to Slack `#incidents` (C0AKV2TK257) |
| Deploy Notifications | `rcp_9f8mVE2Z_DSP` | Every hour | Checks Render backend + frontend status, posts to Slack `#deployments` (C0AKCN6T02Z), creates Better Stack incident on failures |
| GitHub→Notion Sync | `rcp_73Kc9K65YC5T` | Every 6 hours | Syncs open GitHub issues/PRs to Notion roadmap database |

**Rube session**: `drew` (16 active Composio connections)

**Slack channels**:
- `#incidents` (C0AKV2TK257) — Sentry error alerts + GHA cron workflow failure notifications (via `notify-slack` composite action)
- `#deployments` (C0AKCN6T02Z) — Deploy status + rollback notifications
- `#metrics` (C0AKDD7P2HX) — Nightly KPI report (business metrics digest)


## Self-Healing Monitor

**Workflow**: `.github/workflows/self-healing-monitor.yml` — Daily 9am UTC

The self-healing monitor automatically tracks workflow health across all cron and critical GHA workflows. It runs as a matrix job over 13 monitored workflows and manages a lifecycle of GitHub issues to surface repeated failures.

| Trigger | Action |
|---------|--------|
| 3+ failures in 24h | Creates a GitHub issue with `self-healing` + `automated` labels |
| 3 consecutive successes | Auto-closes the open issue |

**Monitored workflows** (13): `check-alerts`, `fetch-weather`, `market-research`, `sync-connections`, `scrape-rates`, `dunning-cycle`, `kpi-report`, `price-sync`, `observe-forecasts`, `nightly-learning`, `data-retention`, `data-health-check`, `deploy-production`

**Issue permissions**: `issues: write`, `actions: read`

### Composite Actions (Self-Healing Infrastructure)

| Action | File | Purpose |
|--------|------|---------|
| `retry-curl` | `.github/actions/retry-curl/action.yml` | Exponential backoff for HTTP calls (4xx fail-fast, 5xx/429/408/000 retry up to 3x) |
| `notify-slack` | `.github/actions/notify-slack/action.yml` | Color-coded Slack failure alerts to `#incidents`; severity: critical/warning/info |
| `validate-migrations` | `.github/actions/validate-migrations/action.yml` | Convention checks: sequential numbering, IF NOT EXISTS, neondb_owner grants, no SERIAL |

**Secret required**: `SLACK_INCIDENTS_WEBHOOK_URL` — Slack incoming webhook URL pointing to `#incidents` (C0AKV2TK257)

All 12 cron workflows and `deploy-production` use `retry-curl` + `notify-slack`. The `migration-gate` job in `deploy-production` uses `validate-migrations` before any deploy proceeds.

## Data Health Check

**Workflow**: `.github/workflows/data-health-check.yml` — Daily cron

Calls `GET /internal/health-data` to verify data pipeline integrity:

- Checks row counts for key tables (`weather_cache`, `market_intelligence`, `scraped_rates`, `electricity_prices`, `user_alert_configs`)
- Reports last-write timestamps to detect stale data
- Flags critical empty tables that indicate a pipeline failure
- Uses `retry-curl` composite action with exponential backoff
- Sends Slack alert to `#incidents` on failure via `notify-slack`

## Nightly KPI Report

**Rube recipe**: `rcp_wu9mVLIZRM_n` — Daily 6:05am UTC (schedule ID: `51f1bdd6-b2a3-42a4-b5df-e936637aaf07`)

Fetches `POST /internal/kpi-report` from the backend, then delivers results to two destinations:

| Destination | Details |
|-------------|---------|
| Slack `#metrics` (C0AKDD7P2HX) | Formatted KPI summary with key metrics |
| Google Sheet "KPI Dashboard" | Appends a new row (`15JGyCAThhP2lUKLvuEsdarRXDBa5TjlWKDwD9mztITA`) |

**Metrics tracked**: Active Users (7d), Total Users, Prices Tracked, Alerts Sent, Pro Count, Business Count, Est. MRR ($), Weather Freshness (hrs), Connections Active, Connections Error

**GHA companion**: `.github/workflows/kpi-report.yml` runs the backend endpoint daily at 6am UTC; the Rube recipe fires 5 minutes later (6:05am) to consume and distribute the results.

## GHA Workflow Inventory

**Total workflows**: 23 (as of 2026-03-09)

| Category | Count | Workflows |
|----------|-------|-----------|
| CI/CD | 3 | `ci.yml`, `deploy-production.yml`, `e2e-tests.yml` |
| Cron — Data | 5 | `check-alerts`, `fetch-weather`, `market-research`, `sync-connections`, `scrape-rates` |
| Cron — Revenue | 2 | `dunning-cycle`, `kpi-report` |
| Cron — ML | 2 | `observe-forecasts`, `nightly-learning` |
| Cron — Ops | 3 | `price-sync`, `data-retention`, `data-health-check` |
| Self-Healing | 1 | `self-healing-monitor` |
| Security | 2 | `secret-scan`, `code-analysis` |
| Docker | 1 | `_docker-build-push` |
| Automation | 4 | `db-maintenance`, `notify-*, retry-curl`, `validate-migrations` (composite actions) |

All 12 cron workflows use the `retry-curl` + `notify-slack` composite actions for resilience and observability.

## Environment Variables

| Variable | Service | Location |
|----------|---------|----------|
| `UPTIMEROBOT_API_KEY` | UptimeRobot | `backend/.env` |

All monitoring services are configured via their respective dashboards. API keys
are optional and only needed for programmatic access.
