# Monitoring & Status Page

## Overview

The RateShift uses a multi-layer monitoring stack, all on free tiers.

## UptimeRobot (Primary External Uptime Monitoring)

**Free tier**: 50 monitors, 5-minute checks, email/webhook alerts. No card required.
**Composio connection**: Active (`uptimerobot` toolkit in `.composio.lock`).

### SLA Target

**99.5% monthly uptime** across all three production monitors.

| Period | Max allowable downtime |
|--------|------------------------|
| Monthly | 219 min (~3h 39m) |
| Weekly | 50 min |
| Daily | 7 min (~432s) |

A monitor check interval of 5 minutes means a single missed check represents 0.35% of daily budget. Alert threshold is set to **2 consecutive failures** before paging to avoid noise from transient probe errors.

### Monitors

Three monitors cover the full request path from end user to database.

| # | Name | URL | Type | Keyword | Alert Threshold |
|---|------|-----|------|---------|-----------------|
| 1 | RateShift Frontend | `https://rateshift.app` | Keyword | `RateShift` (must exist) | 2 consecutive failures |
| 2 | RateShift API Health | `https://api.rateshift.app/api/v1/health` | Keyword | `healthy` (must exist) | 2 consecutive failures |
| 3 | RateShift API Prices | `https://api.rateshift.app/api/v1/prices/current?region=CT` | HTTP | HTTP 200 or 422 accepted | 2 consecutive failures |

**Monitor type rationale:**

- **Frontend (Keyword)**: Checks that the Vercel CDN returns the page AND that it contains the string "RateShift". A bare HTTP check would pass even if Vercel served a generic error page. The keyword check verifies the Next.js app actually rendered.

- **API Health (Keyword)**: The `/api/v1/health` endpoint returns `{"status": "healthy", ...}` when the FastAPI process, database connection, and core systems are operational. Checking for the keyword `healthy` distinguishes a real healthy response from an HTTP 200 with an error body (e.g., a misconfigured reverse proxy returning a 200 splash page).

- **API Prices (HTTP)**: An unauthenticated probe to the prices endpoint returns HTTP 422 (Unprocessable Entity — missing auth token). On UptimeRobot's HTTP monitor type, 4xx responses are counted as UP by default because they prove the application received, parsed, and responded to the request. A 5xx or connection error means the Render service or routing layer has failed.

### Setup (Automated)

Use the setup script to create all three monitors idempotently:

```bash
# 1. Get your Read/Write API key from:
#    https://dashboard.uptimerobot.com -> Account -> API Settings

export UPTIMEROBOT_API_KEY="ur1234567-abcdefghijklmnopqrstuvwx"

# 2. Optional: route alerts to Slack #incidents
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../..."

# 3. Dry run first to verify the plan:
python3 scripts/setup_uptimerobot.py --dry-run

# 4. Apply:
python3 scripts/setup_uptimerobot.py
```

The script (`scripts/setup_uptimerobot.py`) is idempotent — re-running it detects existing monitors by URL and skips creation. It will update alert contacts on existing monitors if a new Slack webhook is provided.

### Alert Routing

UptimeRobot alerts flow to Slack `#incidents` (C0AKV2TK257):

```
UptimeRobot probe fails (2x consecutive)
    → UptimeRobot outgoing webhook
        → Slack #incidents channel
```

Alert contact type: Slack (type 11). Alert threshold: 2 consecutive failures before notification. Recurrence: notify on status change only (no repeat spam while down).

**To verify routing is active**: In the UptimeRobot dashboard, navigate to Alert Contacts and confirm a contact named "RateShift Slack #incidents" exists with type Slack.

### Viewing Status

| Method | URL |
|--------|-----|
| UptimeRobot dashboard | https://dashboard.uptimerobot.com |
| Public status page (if configured) | https://status.rateshift.app (set up via UptimeRobot dashboard) |
| Programmatic (API) | `GET https://api.uptimerobot.com/v2/getMonitors` with API key |

To check current monitor status via the API:

```bash
curl -X POST https://api.uptimerobot.com/v2/getMonitors \
  -d "api_key=$UPTIMEROBOT_API_KEY&format=json&logs=1" \
  | python3 -m json.tool
```

### SLA Calculation

UptimeRobot calculates uptime ratio over rolling windows (7d, 30d, 3m, 6m, 1y). To check compliance against the 99.5% target:

1. Open the UptimeRobot dashboard
2. Select each monitor
3. Check the "Last 30 days" ratio in the monitor detail view
4. All three monitors must show >= 99.5% to be SLA-compliant

An error budget burn rate > 1x (consuming budget faster than it accrues) triggers escalation. See the error budget policy below.

### Error Budget Policy

| Burn rate | Remaining budget | Action |
|-----------|-----------------|--------|
| < 1x | > 50% remaining | No action — healthy |
| 1–2x | 25–50% remaining | Awareness — review in weekly SRE meeting |
| 2–5x | 10–25% remaining | Warning — investigate root cause, post-mortem if incident |
| > 5x | < 10% remaining | Feature freeze on infrastructure changes; focus on reliability |
| Budget exhausted | 0% | Incident bridge until budget restores; stakeholder communication |

### Composio Integration

The UptimeRobot Composio toolkit (`uptimerobot` in `.composio.lock`) can be used for automated monitor management via Rube recipes or direct MCP tool calls. For manual programmatic access, `scripts/setup_uptimerobot.py` uses the UptimeRobot REST API v2 directly (no Composio dependency) to keep the setup self-contained.

### Environment Variables

| Variable | Purpose | Where to store |
|----------|---------|----------------|
| `UPTIMEROBOT_API_KEY` | UptimeRobot Read/Write API key | 1Password vault "RateShift", GHA secret |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook for alert routing | GHA secret `SLACK_INCIDENTS_WEBHOOK_URL` (already set) |

## Better Stack (Status Page + Incident Logs)

**Free tier**: 10 monitors, 1 status page, 3GB logs, 3-min checks. No card required.

### Monitors

| # | Name | URL | Check Interval |
|---|------|-----|----------------|
| 1 | Backend Health | `https://api.rateshift.app/health` | 3 min |
| 2 | Frontend | `https://rateshift.app` | 3 min |
| 3 | API Endpoint | `https://api.rateshift.app/api/v1/prices/current?region=US` | 3 min |

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

The self-healing monitor automatically tracks workflow health across all cron and critical GHA workflows. It runs as a matrix job over 16 monitored workflows and manages a lifecycle of GitHub issues to surface repeated failures.

| Trigger | Action |
|---------|--------|
| 3+ failures in 24h | Creates a GitHub issue with `self-healing` + `automated` labels |
| 3 consecutive successes | Auto-closes the open issue |

**Monitored workflows** (16): `check-alerts`, `fetch-weather`, `market-research`, `sync-connections`, `scrape-rates`, `dunning-cycle`, `kpi-report`, `price-sync`, `observe-forecasts`, `nightly-learning`, `data-retention`, `data-health-check`, `deploy-production`, `fetch-heating-oil`, `detect-rate-changes`, `scan-emails`

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

**Total workflows**: 31 (as of 2026-03-16)

| Category | Count | Workflows |
|----------|-------|-----------|
| CI/CD | 5 | `ci.yml`, `deploy-production.yml`, `deploy-staging.yml`, `deploy-worker.yml`, `e2e-tests.yml` |
| Cron — Data | 5 | `check-alerts`, `fetch-weather`, `market-research`, `sync-connections`, `scrape-rates` |
| Cron — Revenue | 2 | `dunning-cycle`, `kpi-report` |
| Cron — ML | 3 | `observe-forecasts`, `nightly-learning`, `model-retrain` |
| Cron — Ops | 3 | `price-sync`, `data-retention`, `data-health-check` |
| Cron — Multi-Utility | 3 | `fetch-gas-rates`, `fetch-heating-oil`, `detect-rate-changes` |
| Cron — Utility Integration | 2 | `scan-emails`, `scrape-portals` |
| Self-Healing | 1 | `self-healing-monitor` |
| Security | 3 | `secret-scan`, `code-analysis`, `owasp-zap` |
| Reusable | 2 | `_backend-tests`, `_docker-build-push` |
| Specialized | 2 | `gateway-health`, `utility-type-tests` |

All 12 cron workflows use the `retry-curl` + `notify-slack` composite actions for resilience and observability.

## Environment Variables

| Variable | Service | Where to set |
|----------|---------|--------------|
| `UPTIMEROBOT_API_KEY` | UptimeRobot API access | 1Password "RateShift" vault + GHA secret |
| `SLACK_INCIDENTS_WEBHOOK_URL` | Slack `#incidents` incoming webhook | GHA secret (already configured) |
| `BACKEND_URL` | Backend origin for internal cron calls | GHA secret + Render env var |
| `INTERNAL_API_KEY` | Internal endpoint authentication | GHA secret + 1Password vault |

All monitoring services are configured via their respective dashboards. The UptimeRobot
monitors can be provisioned programmatically via `scripts/setup_uptimerobot.py`.
