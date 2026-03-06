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
| Sentry→Slack Bridge | `rcp_sQ1NKouFdXIe` | Every 15 min | Fetches unresolved Sentry issues, classifies by severity, posts to Slack `#incidents` (C0AJPR769H9) |
| Deploy Notifications | `rcp_9f8mVE2Z_DSP` | Every hour | Checks Render backend + frontend status, posts to Slack `#deployments` (C0AJPR7MQV9), creates Better Stack incident on failures |
| GitHub→Notion Sync | `rcp_73Kc9K65YC5T` | Every 6 hours | Syncs open GitHub issues/PRs to Notion roadmap database |

**Rube session**: `drew` (16 active Composio connections)

**Slack channels**:
- `#incidents` (C0AJPR769H9) — Sentry error alerts
- `#deployments` (C0AJPR7MQV9) — Deploy status notifications

## Environment Variables

| Variable | Service | Location |
|----------|---------|----------|
| `UPTIMEROBOT_API_KEY` | UptimeRobot | `backend/.env` |

All monitoring services are configured via their respective dashboards. API keys
are optional and only needed for programmatic access.
