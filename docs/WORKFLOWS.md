# GitHub Actions Workflows

**Last Updated**: 2026-03-25

Complete catalog of all 32 GHA workflow files and 7 composite actions used by RateShift.

---

## Summary

| Category | Count | Description |
|----------|-------|-------------|
| CI / Testing | 4 | Core CI pipeline, backend tests, E2E tests, utility type matrix |
| Deploy | 2 | Production deploy, CF Worker deploy |
| Cron -- Data Pipelines | 1 | Daily consolidated pipeline |
| Cron -- Business Operations | 4 | Dunning, KPI, sync-connections, market research |
| Cron -- Data Ingestion | 4 | Weather, gas rates, heating oil, portal scraping |
| Cron -- Monitoring | 3 | Self-healing monitor, gateway health, data health check |
| Cron -- Maintenance | 2 | Database backup, data retention cleanup |
| Security | 3 | Secret scanning, OWASP ZAP, code analysis |
| Manual-Only | 7 | Formerly cron, now CF Worker triggers or consolidated |
| Utility | 2 | Visual baselines, model retrain |
| **Composite Actions** | **7** | Reusable action components |

**Total**: 32 workflows + 7 composite actions = 39 GHA definitions

---

## CI / Testing

### `ci.yml` -- Unified CI Pipeline

- **Trigger**: Push/PR to `main` or `develop`
- **Purpose**: Primary CI gate. Detects changed files to skip irrelevant jobs. Runs linting, backend tests (via `_backend-tests.yml` reusable workflow), frontend tests, security scanning (`npm audit --audit-level=high`, `pip-audit`), and Docker build validation.
- **Concurrency**: Per-ref, cancel in-progress

### `_backend-tests.yml` -- Backend Tests (Reusable)

- **Trigger**: `workflow_call` (called by `ci.yml` and other workflows)
- **Purpose**: Reusable backend test job with PostgreSQL service container, coverage reporting, and optional Codecov upload. Runs `pytest` with coverage thresholds.
- **Inputs**: `coverage` (bool), `upload-codecov` (bool)

### `e2e-tests.yml` -- E2E Tests (Playwright)

- **Trigger**: Push/PR to `main` or `develop`
- **Purpose**: Runs Playwright E2E tests across 5 browser projects (chromium, firefox, webkit, mobile-chrome, mobile-safari). Detects changes to skip if frontend unchanged. Includes Lighthouse performance checks and load testing.
- **Concurrency**: Per-ref, cancel in-progress

### `utility-type-tests.yml` -- Utility Type Test Matrix

- **Trigger**: Push/PR to `main` or `develop` (backend path filter)
- **Purpose**: Runs backend tests filtered to utility-type-specific test files, ensuring multi-utility features work in isolation.
- **Concurrency**: Per-ref, cancel in-progress

---

## Deploy

### `deploy-production.yml` -- Deploy to Production

- **Trigger**: Release published, or `workflow_dispatch` with version input
- **Purpose**: Production deployment pipeline. Validates release, runs migration gate (`validate-migrations` action), builds Docker image, deploys to Render. Includes Slack rollback notification on failure.
- **Concurrency**: `deploy-production`, no cancel (ensures atomic deploys)

### `deploy-worker.yml` -- Deploy Cloudflare Worker

- **Trigger**: Push to `main` (path filter: `workers/api-gateway/**`), or `workflow_dispatch`
- **Purpose**: Tests and deploys the CF Worker API gateway via Wrangler. Runs vitest suite first, deploys only on success.
- **Concurrency**: `deploy-worker`, no cancel

---

## Cron -- Data Pipelines

### `daily-data-pipeline.yml` -- Consolidated Daily Pipeline

- **Schedule**: Daily 3am UTC
- **Purpose**: Single consolidated workflow that runs 4 previously separate jobs sequentially: scrape-rates, scan-emails, nightly-learning, and detect-rate-changes. Single checkout and backend warmup step saves GHA minutes.
- **Endpoint**: Multiple internal endpoints via `retry-curl`
- **Notify**: Slack on failure

---

## Cron -- Business Operations

### `dunning-cycle.yml` -- Dunning Cycle

- **Schedule**: Daily 7am UTC
- **Purpose**: Overdue payment escalation. 7-day grace period, soft then final dunning emails.
- **Endpoint**: `POST /internal/dunning-cycle`

### `kpi-report.yml` -- Nightly KPI Report

- **Schedule**: Daily 6am UTC
- **Purpose**: Business metrics aggregation and reporting.
- **Endpoint**: `POST /internal/kpi-report`

### `sync-connections.yml` -- Sync User Connections

- **Schedule**: Every 6 hours
- **Purpose**: Auto-syncs UtilityAPI connections to pull latest bill/usage data.
- **Endpoint**: `POST /internal/sync-connections`

### `market-research.yml` -- Market Intelligence Scan

- **Schedule**: Daily 2am UTC
- **Purpose**: Tavily + Diffbot market research scan for competitive intelligence.
- **Endpoint**: `POST /internal/market-research`

---

## Cron -- Data Ingestion

### `fetch-weather.yml` -- Fetch Weather Data

- **Schedule**: Every 12 hours (offset :15)
- **Purpose**: Parallelized weather data fetch for all monitored regions (asyncio.gather with Semaphore(10)).
- **Endpoint**: `POST /internal/fetch-weather`

### `fetch-gas-rates.yml` -- Fetch Gas Rates

- **Schedule**: Weekly Monday 4am UTC
- **Purpose**: EIA natural gas rate data ingestion.
- **Endpoint**: `POST /internal/fetch-gas-rates`

### `fetch-heating-oil.yml` -- Fetch Petroleum Prices

- **Schedule**: Weekly Monday 2pm UTC
- **Purpose**: EIA heating oil and petroleum pricing data.
- **Endpoint**: `POST /internal/fetch-heating-oil`

### `scrape-portals.yml` -- Scrape Utility Portals

- **Schedule**: Weekly Sunday 5am UTC
- **Purpose**: Batch scrape all active portal_scrape connections (Semaphore(2), 5 supported utilities).
- **Endpoint**: `POST /internal/scrape-portals`

---

## Cron -- Monitoring

### `self-healing-monitor.yml` -- Self-Healing Monitor

- **Schedule**: Daily 9am UTC
- **Purpose**: Checks 18 monitored workflows for repeated failures (threshold: 3). Auto-creates GitHub issues with `self-healing` label after threshold, auto-closes when failures resolve.
- **Permissions**: `issues: write`, `actions: read`

### `gateway-health.yml` -- Gateway Health Check

- **Schedule**: Every 12 hours
- **Purpose**: Tests CF Worker API gateway health, cache status, and rate limiting endpoints.
- **Notify**: Slack on failure

### `data-health-check.yml` -- Data Health Check

- **Schedule**: Daily 8am UTC
- **Purpose**: Validates data freshness, anomaly detection, and source availability across all data pipelines.
- **Endpoint**: Internal data quality endpoints

---

## Cron -- Maintenance

### `db-backup.yml` -- Database Backup

- **Schedule**: Weekly Sunday 2am UTC
- **Purpose**: Neon database backup via `pg_dump`. Runs before data-retention (4am) and scrape-portals (5am).
- **Concurrency**: `db-backup`, no cancel

### `data-retention.yml` -- Weekly Data Retention Cleanup

- **Schedule**: Weekly Sunday 4am UTC
- **Purpose**: Purges old data per retention policies (prices > 365 days, observations > 90 days).
- **Endpoint**: `POST /internal/maintenance/cleanup`

---

## Security

### `secret-scan.yml` -- Secret Scanning

- **Trigger**: Push/PR to `main`/`develop`, plus weekly Monday 3am UTC
- **Purpose**: Scans for leaked secrets, API keys, and credentials in code.
- **Concurrency**: Per-ref, cancel in-progress

### `owasp-zap.yml` -- OWASP ZAP Baseline Scan

- **Schedule**: Weekly Sunday 4am UTC
- **Purpose**: OWASP ZAP baseline scan against the Render backend (not CF Worker). Uses `.zap/rules.tsv` for 5 false-positive suppression rules.
- **Permissions**: `contents: read`, `issues: write`

### `code-analysis.yml` -- Code Analysis

- **Trigger**: PR to `main`
- **Purpose**: Claude Flow-powered code analysis on pull requests.
- **Concurrency**: Per-ref, cancel in-progress

---

## Manual-Only (Cron Moved to CF Worker or Consolidated)

These workflows retain `workflow_dispatch` triggers for ad-hoc runs but no longer have cron schedules:

### `check-alerts.yml` -- Check Price Alerts

- **Moved to**: CF Worker Cron Trigger (`0 */3 * * *`, every 3 hours)
- **Endpoint**: `POST /internal/check-alerts`

### `price-sync.yml` -- Sync Electricity Prices

- **Moved to**: CF Worker Cron Trigger (`0 */6 * * *`, every 6 hours)
- **Endpoint**: `POST /internal/scrape-rates`

### `observe-forecasts.yml` -- Observe Forecast Actuals

- **Moved to**: CF Worker Cron Trigger (`30 */6 * * *`, 30 min after price-sync)
- **Endpoint**: `POST /internal/observe-forecasts`

### `scrape-rates.yml` -- Scrape Supplier Rates

- **Moved to**: `daily-data-pipeline.yml` (consolidated)
- **Endpoint**: `POST /internal/scrape-rates`

### `scan-emails.yml` -- Scan Email Connections

- **Moved to**: `daily-data-pipeline.yml` (consolidated)
- **Endpoint**: `POST /internal/scan-emails`

### `nightly-learning.yml` -- Nightly Learning Cycle

- **Moved to**: `daily-data-pipeline.yml` (consolidated)
- **Endpoint**: `POST /internal/learn`

### `detect-rate-changes.yml` -- Detect Rate Changes

- **Moved to**: `daily-data-pipeline.yml` (consolidated)
- **Endpoint**: Internal rate change detection

---

## Utility

### `update-visual-baselines.yml` -- Update Visual Regression Baselines

- **Trigger**: `workflow_dispatch` only
- **Purpose**: Regenerates Playwright visual regression baseline screenshots for selected browser project (chromium/firefox/webkit/all).

### `model-retrain.yml` -- Weekly Model Retraining

- **Trigger**: `workflow_dispatch` only (cron disabled -- validates pipeline but no real retraining yet)
- **Purpose**: ML model retraining pipeline validation.

---

## Composite Actions (`.github/actions/`)

Reusable action components used across multiple workflows.

### `retry-curl`

Exponential backoff HTTP client for calling internal API endpoints.

| Input | Default | Description |
|-------|---------|-------------|
| `url` | (required) | URL to call |
| `method` | `POST` | HTTP method |
| `headers` | `''` | Newline-separated headers |
| `body` | `{}` | Request body |
| `max-retries` | `3` | Max retry attempts |
| `initial-delay` | `5` | Initial backoff delay (seconds) |
| `max-delay` | `60` | Maximum backoff delay (seconds) |
| `timeout` | `120` | Curl timeout (seconds) |

**Behavior**: Retries on 5xx, 429, 408, and 000 (connection error). Fails immediately on 4xx (except 429/408). Adds jitter to backoff delay.

**Outputs**: `status-code`, `attempts`

### `notify-slack`

Sends color-coded failure notifications to Slack.

| Input | Required | Description |
|-------|----------|-------------|
| `webhook-url` | Yes | Slack incoming webhook URL (note: hyphen, not underscore) |
| `workflow-name` | Yes | Name of the failed workflow |
| `severity` | Yes | `critical`, `warning`, or `info` |
| `run-url` | No | Link to the failed run (auto-populated) |

**Severity colors**: `critical` = red, `warning` = amber, `info` = blue.

### `validate-migrations`

Checks migration files for convention compliance.

| Check | Rule |
|-------|------|
| Sequential numbering | No gaps from `init_neon.sql` (treated as #1) through latest |
| `IF NOT EXISTS` | All `CREATE TABLE` statements (except `init_neon.sql`) |
| `neondb_owner` | All `GRANT` statements reference `neondb_owner` role |
| No SERIAL | Flags any `SERIAL` or `BIGSERIAL` (UUID PKs required) |

**Input**: `migration-dir` (default: `backend/migrations`)
**Outputs**: `passed` (bool), `violations` (string)

### `warmup-backend`

Wakes the Render backend from cold sleep before making API calls.

| Input | Default | Description |
|-------|---------|-------------|
| `backend-url` | (required) | Backend base URL |
| `max-attempts` | `6` | Maximum warmup attempts |
| `delay-seconds` | `15` | Delay between attempts |

Polls the backend health endpoint, accepting 2xx or 4xx as "responsive". Issues a warning (not failure) if backend does not respond.

### `setup-python-env`

Sets up Python with pip caching and installs requirements.

| Input | Default | Description |
|-------|---------|-------------|
| `python-version` | `3.12` | Python version |
| `working-directory` | (required) | Directory with `requirements.txt` |
| `install-dev` | `false` | Also install `requirements-dev.txt` |

### `setup-node-env`

Sets up Node.js with npm caching and runs `npm ci` in `frontend/`.

| Input | Default | Description |
|-------|---------|-------------|
| `node-version` | `20` | Node.js version |

### `wait-for-service`

Polls a URL until it returns the expected HTTP status or times out.

| Input | Default | Description |
|-------|---------|-------------|
| `url` | (required) | URL to poll |
| `timeout` | `120` | Maximum wait time (seconds) |
| `interval` | `5` | Polling interval (seconds) |
| `expected-status` | `200` | Expected HTTP status code |

---

## Cron Schedule Reference

### CF Worker Cron Triggers (4 total, zero GHA cost)

| Cron | Frequency | Job |
|------|-----------|-----|
| `*/10 * * * *` | Every 10 min | Keep-alive (Render cold start prevention) |
| `0 */3 * * *` | Every 3 hours | Check price alerts |
| `0 */6 * * *` | Every 6 hours | Price sync |
| `30 */6 * * *` | Every 6 hours (+30min) | Observe forecasts |

### GHA Cron Workflows

| Cron | Day/Time (UTC) | Workflow |
|------|----------------|----------|
| `0 2 * * *` | Daily 2am | `market-research.yml` |
| `0 3 * * *` | Daily 3am | `daily-data-pipeline.yml` |
| `0 3 * * 1` | Mon 3am | `secret-scan.yml` |
| `0 4 * * 1` | Mon 4am | `fetch-gas-rates.yml` |
| `0 6 * * *` | Daily 6am | `kpi-report.yml` |
| `0 7 * * *` | Daily 7am | `dunning-cycle.yml` |
| `0 8 * * *` | Daily 8am | `data-health-check.yml` |
| `0 9 * * *` | Daily 9am | `self-healing-monitor.yml` |
| `15 */12 * * *` | Every 12h (+15m) | `fetch-weather.yml` |
| `0 */12 * * *` | Every 12h | `gateway-health.yml` |
| `0 */6 * * *` | Every 6h | `sync-connections.yml` |
| `0 14 * * 1` | Mon 2pm | `fetch-heating-oil.yml` |
| `0 2 * * 0` | Sun 2am | `db-backup.yml` |
| `0 4 * * 0` | Sun 4am | `data-retention.yml`, `owasp-zap.yml` |
| `0 5 * * 0` | Sun 5am | `scrape-portals.yml` |

---

## Cost Optimization Notes

- Estimated GHA usage: ~1,283 min/month
- 4 cron jobs moved to CF Worker Cron Triggers (saves ~480 min/month)
- 4 cron jobs consolidated into `daily-data-pipeline.yml` (single checkout + warmup)
- E2E tests removed from daily cron (push/PR only)
- Full cost analysis: `docs/COST_ANALYSIS.md`
