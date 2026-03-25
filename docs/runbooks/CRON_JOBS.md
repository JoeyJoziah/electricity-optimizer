# Cron Jobs Runbook

> Last updated: 2026-03-25 | 4 CF Worker crons + 14 GHA crons = 18 scheduled jobs

## CF Worker Cron Triggers (Zero GHA Cost)

Defined in `workers/api-gateway/wrangler.toml`. Handler: `workers/api-gateway/src/handlers/scheduled.ts`. All use INTERNAL_API_KEY for auth. Include one retry after 35s for Render cold starts.

### keep-alive

| Field | Value |
|-------|-------|
| **Schedule** | `*/10 * * * *` (every 10 minutes) |
| **Method** | `GET /` |
| **Purpose** | Prevent Render free-tier cold starts (15-min spin-down) |
| **Auth** | None (public health endpoint) |
| **Expected** | 200 OK. Any status logged; errors are non-fatal |
| **Failure symptoms** | Other cron jobs return 502/503. First request to site takes 30s+ |
| **Recovery** | Verify `ORIGIN_URL` secret is set: `npx wrangler secret list` |

### check-alerts

| Field | Value |
|-------|-------|
| **Schedule** | `0 */3 * * *` (every 3 hours) |
| **Method** | `POST /api/v1/internal/check-alerts` |
| **Purpose** | Evaluate price alert configs, send email/push notifications with dedup |
| **Auth** | `X-API-Key` header |
| **Dedup cooldowns** | Immediate: 1 hour, Daily: 24 hours, Weekly: 7 days |
| **Failure symptoms** | Users stop receiving price alerts |
| **Recovery** | 1. Check `INTERNAL_API_KEY` secret matches Render. 2. Check Render logs for alert_service errors. 3. Manual trigger: `npx wrangler tail` then POST via curl |

### price-sync

| Field | Value |
|-------|-------|
| **Schedule** | `0 */6 * * *` (every 6 hours) |
| **Method** | `POST /api/v1/prices/refresh` |
| **Purpose** | Scrape electricity rate data from EIA/NREL/Diffbot |
| **Auth** | `X-API-Key` header |
| **Failure symptoms** | Stale price data, forecasts degrade |
| **Recovery** | 1. Check EIA/NREL API key validity. 2. Manual: `price-sync.yml` workflow_dispatch |

### observe-forecasts

| Field | Value |
|-------|-------|
| **Schedule** | `30 */6 * * *` (30 min after price-sync) |
| **Method** | `POST /api/v1/internal/observe-forecasts` |
| **Purpose** | Backfill actual prices into forecast observations for ML accuracy tracking |
| **Auth** | `X-API-Key` header |
| **Depends on** | price-sync (needs fresh prices to compare against forecasts) |
| **Failure symptoms** | Model accuracy metrics stale, retraining decisions uninformed |
| **Recovery** | Run price-sync first, then trigger manually via `observe-forecasts.yml` |

---

## GHA Cron Workflows (14 active schedules)

All GHA crons support `workflow_dispatch` for manual triggering. Most use `retry-curl` composite action (exponential backoff, 3 retries) and `notify-slack` (alerts to `#incidents`).

### Daily Jobs

#### daily-data-pipeline

| Field | Value |
|-------|-------|
| **Schedule** | `0 3 * * *` (daily 3am UTC) |
| **File** | `daily-data-pipeline.yml` |
| **Purpose** | Consolidated pipeline: scrape-rates, scan-emails, nightly-learning, detect-rate-changes |
| **Endpoints** | `POST /internal/scrape-rates`, `POST /internal/scan-emails`, `POST /internal/learn`, `POST /internal/detect-rate-changes` (sequential) |
| **Auth** | `INTERNAL_API_KEY` GHA secret |
| **Failure symptoms** | Stale rate data, missed email imports, ML not learning |
| **Recovery** | Check Render logs. Run individual steps via their standalone `workflow_dispatch` |

#### market-research

| Field | Value |
|-------|-------|
| **Schedule** | `0 2 * * *` (daily 2am UTC) |
| **File** | `market-research.yml` |
| **Purpose** | Tavily + Diffbot market intelligence scraping |
| **Endpoint** | `POST /internal/market-research` |
| **Failure symptoms** | Market intelligence data stale |
| **Recovery** | Check `TAVILY_API_KEY` and `DIFFBOT_API_TOKEN` validity |

#### kpi-report

| Field | Value |
|-------|-------|
| **Schedule** | `0 6 * * *` (daily 6am UTC) |
| **File** | `kpi-report.yml` |
| **Purpose** | Business metrics aggregation (MRR, user growth, churn) |
| **Endpoint** | `POST /internal/kpi-report` |
| **Failure symptoms** | Missing daily KPI snapshots |

#### dunning-cycle

| Field | Value |
|-------|-------|
| **Schedule** | `0 7 * * *` (daily 7am UTC) |
| **File** | `dunning-cycle.yml` |
| **Purpose** | Overdue payment escalation (7-day grace period) |
| **Endpoint** | `POST /internal/dunning-cycle` |
| **Failure symptoms** | Overdue accounts not receiving dunning emails |
| **Recovery** | Check `payment_retry_history` table. Verify Resend API key |

#### data-health-check

| Field | Value |
|-------|-------|
| **Schedule** | `0 8 * * *` (daily 8am UTC) |
| **File** | `data-health-check.yml` |
| **Purpose** | Data freshness, anomaly detection, source availability |
| **Endpoints** | `GET /internal/freshness`, `GET /internal/anomalies`, `GET /internal/sources` |
| **Failure symptoms** | Stale data goes undetected |

#### self-healing-monitor

| Field | Value |
|-------|-------|
| **Schedule** | `0 9 * * *` (daily 9am UTC) |
| **File** | `self-healing-monitor.yml` |
| **Purpose** | Check 18 workflows for repeated failures, auto-create GitHub issues |
| **Auto-actions** | Creates issues with `self-healing` label after 3+ failures; closes on recovery |
| **Failure symptoms** | Broken workflows go unnoticed |

### Periodic Jobs (Every N Hours)

#### fetch-weather

| Field | Value |
|-------|-------|
| **Schedule** | `15 */12 * * *` (every 12h, offset :15) |
| **File** | `fetch-weather.yml` |
| **Purpose** | Weather data for ML features (asyncio.gather + Semaphore(10)) |
| **Endpoint** | `POST /internal/fetch-weather` |

#### sync-connections

| Field | Value |
|-------|-------|
| **Schedule** | `0 */6 * * *` (every 6h) |
| **File** | `sync-connections.yml` |
| **Purpose** | UtilityAPI auto-sync for direct_sync connections |
| **Endpoint** | `POST /internal/sync-connections` |
| **Failure symptoms** | Connection data out of date |
| **Recovery** | Check `UTILITYAPI_KEY` validity |

#### gateway-health

| Field | Value |
|-------|-------|
| **Schedule** | `0 */12 * * *` (every 12h) |
| **File** | `gateway-health.yml` |
| **Purpose** | CF Worker gateway health check (UptimeRobot handles real-time) |

### Weekly Jobs (Sundays / Mondays)

#### db-backup

| Field | Value |
|-------|-------|
| **Schedule** | `0 2 * * 0` (Sunday 2am UTC) |
| **File** | `db-backup.yml` |
| **Purpose** | Database backup (before retention cleanup) |

#### secret-scan

| Field | Value |
|-------|-------|
| **Schedule** | `0 3 * * 1` (Monday 3am UTC) |
| **File** | `secret-scan.yml` |
| **Purpose** | Scan codebase for leaked secrets |

#### data-retention

| Field | Value |
|-------|-------|
| **Schedule** | `0 4 * * 0` (Sunday 4am UTC) |
| **File** | `data-retention.yml` |
| **Purpose** | GDPR data cleanup (730-day retention) |

#### owasp-zap

| Field | Value |
|-------|-------|
| **Schedule** | `0 4 * * 0` (Sunday 4am UTC) |
| **File** | `owasp-zap.yml` |
| **Purpose** | OWASP ZAP baseline security scan against Render backend |
| **Failure symptoms** | New vulnerabilities go undetected |
| **Config** | `.zap/rules.tsv` (5 false-positive suppressions) |

#### fetch-gas-rates

| Field | Value |
|-------|-------|
| **Schedule** | `0 4 * * 1` (Monday 4am UTC) |
| **File** | `fetch-gas-rates.yml` |
| **Purpose** | EIA natural gas price data (updates monthly, weekly scrape is sufficient) |

#### fetch-heating-oil

| Field | Value |
|-------|-------|
| **Schedule** | `0 14 * * 1` (Monday 2pm UTC) |
| **File** | `fetch-heating-oil.yml` |
| **Purpose** | EIA heating oil data (publishes Wed, scraped Mon after) |

#### scrape-portals

| Field | Value |
|-------|-------|
| **Schedule** | `0 5 * * 0` (Sunday 5am UTC) |
| **File** | `scrape-portals.yml` |
| **Purpose** | Batch scrape portal_scrape connections (Semaphore(2), 5 utilities) |
| **Endpoint** | `POST /internal/scrape-portals` |

---

## Troubleshooting

### CF Worker crons not firing

1. Verify deployment: `npx wrangler deployments list --name rateshift-api-gateway`
2. Check cron config: `npx wrangler tail --format=json` (wait for next trigger)
3. Verify secrets: `npx wrangler secret list --name rateshift-api-gateway` (expect 3: ORIGIN_URL, INTERNAL_API_KEY, RATE_LIMIT_BYPASS_KEY)
4. If ORIGIN_URL missing: `npx wrangler secret put ORIGIN_URL` (enter Render URL)

### GHA crons not firing

1. Check Actions tab for workflow run history
2. GitHub disables crons on repos with no activity for 60 days — push a commit to re-enable
3. Check `INTERNAL_API_KEY` repository secret matches Render

### Backend returns 502/503

1. Render cold start (free tier): keep-alive cron should prevent this. If still happening, check keep-alive in `npx wrangler tail`
2. If persistent: check Render dashboard for deploy errors or resource limits

### Slack alerts not arriving

1. Verify `SLACK_INCIDENTS_WEBHOOK_URL` GHA secret is set
2. Test webhook: `curl -X POST $WEBHOOK_URL -d '{"text":"test"}'`
3. Check `#incidents` channel (C0AKV2TK257) isn't muted
