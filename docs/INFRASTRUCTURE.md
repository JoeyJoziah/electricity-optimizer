# Infrastructure Documentation - Electricity Optimizer

This document describes the infrastructure architecture, service dependencies, and operational procedures.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Service Catalog](#service-catalog)
3. [Network Architecture](#network-architecture)
4. [Resource Limits](#resource-limits)
5. [Monitoring Setup](#monitoring-setup)
6. [Scaling Guidelines](#scaling-guidelines)
7. [Cost Optimization](#cost-optimization)

---

## Architecture Overview

```
                              +------------------+
                              |    Internet      |
                              +--------+---------+
                                       |
                              +--------+---------+
                              |   Render.com     |
                              |   (Hosting)      |
                              +--------+---------+
                                       |
                    +------------------+------------------+
                    |                                     |
           +--------+--------+                   +--------+--------+
           |    Frontend     |                   |    Backend API   |
           |   (Next.js)     |                   |   (FastAPI)      |
           |   Port: 3000    |                   |   Port: 8000     |
           +--------+--------+                   +--------+--------+
                    |                                     |
                    |              +----------------------+
                    |              |                      |
           +--------+--------+                           +--------+--------+
           | Neon PostgreSQL |                           |     Redis       |
           |  (Serverless)   |                           |   Port: 6379    |
           +-----------------+                           +--------+--------+

           +-------------GitHub Actions------------------+
           |                                              |
           |  price-sync, CI/CD, scheduled workflows      |
           |  (replaces Airflow -- removed 2026-02-12)    |
           |                                              |
           +----------------------------------------------+

           +------------------Monitoring------------------+
           |                                              |
           |  +-------------+  +-------------+            |
           |  | Prometheus  |  |   Grafana   |            |
           |  | Port: 9090  |  | Port: 3001  |            |
           |  +-------------+  +-------------+            |
           |                                              |
           +----------------------------------------------+
```

---

## Service Catalog

### Core Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| backend | custom | 8000 | FastAPI REST API |
| frontend | custom | 3000 | Next.js web application |
| redis | redis:7-alpine | 6379 | Caching and message queue |

### Scheduling (GitHub Actions)

Pipeline orchestration is handled by GitHub Actions workflows (`.github/workflows/`), replacing the previously used Airflow setup (removed 2026-02-12).

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| price-sync.yml | `0 */6 * * *` | Electricity price data ingestion |
| observe-forecasts.yml | `30 */6 * * *` | Backfill actual prices into forecast observations |
| nightly-learning.yml | `0 4 * * *` | Adaptive learning: accuracy, bias detection, weight tuning |
| test.yml | On push/PR | Test suite (Python 3.11, Node 20, PostgreSQL 15, Redis 7) |
| backend-ci.yml | On push/PR | Backend-specific tests and lint |
| frontend-ci.yml | On push/PR | Frontend lint, test, build |
| e2e-tests.yml | Daily + on demand | Playwright E2E + Lighthouse audits |
| deploy-staging.yml | On merge to develop | Staging deployment to Render.com |
| deploy-production.yml | On release | Production deployment to Render.com |

### Board Sync (Local Automation)

The board-sync system keeps GitHub Projects board #4 and the Notion roadmap in sync with development activity. It runs locally via git hooks and Claude Code hooks.

**Orchestrator:** `.claude/hooks/board-sync/sync-boards.sh`

| Subcommand | Description |
|------------|-------------|
| `all` | Sync GitHub Projects + Notion (default) |
| `github` | Sync GitHub Projects only |
| `notion` | Sync Notion only (delegates to `scripts/github_notion_sync.py`) |
| `status` | Show last sync time, lock state, queue depth |
| `logs` | Tail sync log (`.claude/logs/board-sync.log`) |
| `queue` | Show queued sync requests |
| `drain` | Process queue then run full sync |

**Flags:** `--force` (bypass 30s debounce), `--bg` (background execution)

**Coordination:**
- PID-based lock file prevents concurrent syncs
- 30-second debounce between syncs (configurable)
- Queue file batches high-frequency edit triggers

**Triggers:**

| Event | Hook | Behavior |
|-------|------|----------|
| Git commit | `.git/hooks/post-commit` | Background sync |
| Git merge | `.git/hooks/post-merge` | Background sync |
| Branch switch | `.git/hooks/post-checkout` | Background sync (branch only, not file checkout) |
| Claude edit | `PostToolUse: Edit/Write/MultiEdit` | Queue sync request |
| Claude task update | `PostToolUse: TaskUpdate` | Drain queue + background sync |
| Session end | `Stop` | Drain queue + foreground forced sync |

**Setup after clone:** Run `scripts/install-hooks.sh` to install git hooks from templates.

**Config:** GitHub project number and owner stored in `.notion_sync_config.json` under the `github_project` key.

**Notion Database Schema:**

The Notion roadmap database has 13 properties, provisioned by `scripts/notion_setup_schema.py`:

| Property | Type | Notes |
|----------|------|-------|
| Title | title | Renamed from Notion default `Name` |
| Status | select | Not Started, Planning, In Progress, Blocked, Review, Done |
| Phase | select | Phase 1-5 (Backend, Frontend, Data/ML, Infrastructure, Security) |
| Priority | select | Critical, High, Medium, Low |
| Category | select | Backend, Frontend, Data/ML, Infrastructure, Security, Testing, Documentation |
| Milestone | select | MVP, Beta, v1.0 |
| Assignee | select | Dynamic |
| Start Date | date | -- |
| Due Date | date | -- |
| Progress | number | Percent format |
| Notes | rich_text | -- |
| GitHub Issue | url | Links to GitHub issue |
| Related PRs | url | Links to GitHub PR |

**Sync Scripts:**

| Script | Source | Trigger |
|--------|--------|---------|
| `scripts/notion_setup_schema.py` | -- | Manual (one-time setup, idempotent) |
| `scripts/notion_sync.py --once` | TODO.md | Board-sync orchestrator / manual |
| `scripts/github_notion_sync.py --mode full` | GitHub API | Scheduled (every 30 min) / manual |
| `scripts/github_notion_sync.py --mode event` | GitHub webhook | `notion-sync.yml` on issue/PR events |

**API Version:** All scripts use Notion API version `2022-06-28`. Version `2025-09-03` omits `properties` from database responses and must not be used.

### Monitoring Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| prometheus | prom/prometheus:v2.51.0 | 9090 | Metrics collection |
| grafana | grafana/grafana:10.3.1 | 3001 | Dashboards and alerting |
| node-exporter | prom/node-exporter:v1.7.0 | 9100 | System metrics |
| redis-exporter | oliver006/redis_exporter:v1.58.0 | 9121 | Redis metrics |
| postgres-exporter | prometheuscommunity/postgres-exporter:v0.15.0 | 9187 | PostgreSQL metrics |

---

## Network Architecture

### Docker Networks

```yaml
networks:
  electricity-optimizer:
    driver: bridge
    name: electricity-optimizer-network
```

All services communicate over the internal Docker bridge network. Only the following ports are exposed to the host:

| Port | Service | Access |
|------|---------|--------|
| 3000 | Frontend | Public |
| 8000 | Backend API | Public |
| 3001 | Grafana | Internal/VPN |
| 9090 | Prometheus | Internal only |

### Service Discovery

Services discover each other using Docker DNS:
- `http://backend:8000` - Backend API
- `redis://redis:6379` - Redis

In production, the database is Neon PostgreSQL (serverless, accessed via connection string — no local container).

---

## Resource Limits

### Production Resource Allocation

| Service | CPU Limit | Memory Limit | CPU Reserved | Memory Reserved |
|---------|-----------|--------------|--------------|-----------------|
| backend | 1.0 | 512MB | 0.25 | 256MB |
| frontend | 0.5 | 256MB | 0.1 | 128MB |
| redis | 0.25 | 128MB | 0.1 | 64MB |
| prometheus | 0.25 | 256MB | 0.1 | 128MB |
| grafana | 0.25 | 256MB | 0.1 | 128MB |

### Total Production Requirements

- **Minimum**: 1 CPU core, 2GB RAM (scheduling offloaded to GitHub Actions)
- **Recommended**: 2 CPU cores, 4GB RAM
- **Storage**: 50GB SSD (for databases and logs)
- **Database**: Neon PostgreSQL serverless (managed, no local resource cost in production)

---

## Monitoring Setup

### Metrics Collection

The `/metrics` endpoint requires an `X-API-Key` header (or `api_key` query param) matching `INTERNAL_API_KEY` to prevent information leakage.

Prometheus scrapes metrics from all services:

```yaml
scrape_configs:
  - job_name: 'backend-api'
    targets: ['backend:8000']
    metrics_path: '/metrics'

  - job_name: 'redis'
    targets: ['redis-exporter:9121']

  - job_name: 'postgres'
    targets: ['postgres-exporter:9187']
```

### Key Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| `http_requests_total` | Total HTTP requests | - |
| `http_request_duration_seconds` | Request latency | p95 < 500ms |
| `forecast_mape` | ML model accuracy | < 10% |
| `price_data_last_update_timestamp` | Data freshness | < 15min |
| `redis_keyspace_hits_total` | Cache hits | > 80% hit rate |
| `pg_stat_database_numbackends` | DB connections | < 80% max |

### Alert Rules

Alerts are configured in `monitoring/alerts.yml`:

| Alert | Condition | Severity |
|-------|-----------|----------|
| HighAPILatency | p95 > 1s for 5m | Warning |
| HighErrorRate | > 5% for 5m | Critical |
| PriceDataStaleness | > 30min old | Warning |
| ModelForecastAccuracyDegraded | MAPE > 15% for 1h | Warning |
| HighDatabaseConnections | > 80% for 5m | Warning |
| ServiceDown | up == 0 for 2m | Critical |

### Grafana Dashboards

Pre-configured dashboards:

1. **Overview** - High-level service health
2. **API Performance** - Request rates, latency, errors
3. **Database** - PostgreSQL performance
4. **ML Models** - Forecast accuracy and inference times
5. **System Resources** - CPU, memory, disk

---

## Scaling Guidelines

### Horizontal Scaling

#### Backend API
```bash
# Scale to 3 replicas
docker compose up -d --scale backend=3
```

### Vertical Scaling

Update resource limits in `docker-compose.prod.yml`:

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 1G
```

### When to Scale

| Condition | Action |
|-----------|--------|
| API latency > 500ms sustained | Scale backend horizontally |
| CPU > 80% sustained | Scale vertically or horizontally |
| DB connections > 80% | Increase connection pool |

---

## Cost Optimization

### Budget Target: $50/month

#### Current Allocation

| Component | Estimated Cost | Notes |
|-----------|----------------|-------|
| Neon PostgreSQL | $0 (free tier) | Serverless, 0.5 GB storage |
| Render.com | $15-35 | Backend + frontend services (render.yaml) |
| Domain + SSL | $0-10 | Let's Encrypt for SSL |
| **Total** | **$15-45** | Under $50/month budget |

### Cost-Saving Strategies

1. **Use Free Tiers**
   - Neon PostgreSQL free tier for serverless database
   - GitHub Actions free tier for CI/CD and scheduling
   - Let's Encrypt for SSL certificates

2. **Self-Host Where Possible**
   - Run Prometheus/Grafana locally
   - Use Redis as cache (no managed service)
   - TimescaleDB for local dev only (Neon in production)

3. **Resource Optimization**
   - Aggressive caching (5-min TTL)
   - Batch API calls
   - Compress data before storage

4. **Monitoring Costs**
   - Use `model-usage` skill to track costs
   - Set up alerts for cost anomalies
   - Review usage monthly

### Scaling Cost Impact

| Scale Action | Monthly Cost Impact |
|--------------|---------------------|
| Add 1 backend replica | +$10-15 |
| Double database size | +$5-10 |
| Add monitoring retention | +$0 (self-hosted) |

---

## Disaster Recovery

### Recovery Time Objectives

| Component | RTO | RPO |
|-----------|-----|-----|
| Frontend | 5 min | 0 |
| Backend API | 15 min | 0 |
| Neon PostgreSQL | N/A (managed) | Point-in-time (managed by Neon) |
| Redis | 15 min | 24 hours |

### Backup Strategy

```bash
# Daily backup (cron)
0 2 * * * /app/scripts/backup.sh

# Weekly full backup
0 3 * * 0 /app/scripts/backup.sh --full
```

### Recovery Procedures

1. **Service Failure**: Docker auto-restarts (unless-stopped policy)
2. **Data Corruption**: Restore from backup
3. **Complete Failure**: Redeploy from Git + restore backups

---

## Security

### Network Security

- Internal services not exposed to public
- All public traffic through reverse proxy
- TLS 1.3 for all external connections

### Secrets Management

- Environment variables for non-sensitive config
- 1Password for production secrets
- Never commit secrets to Git
- INTERNAL_API_KEY for service-to-service authentication

### Access Control

- Grafana behind VPN or IP whitelist
- JWT authentication for API (PyJWT with Redis-backed token revocation)
- Role-based access control
- API documentation (Swagger/ReDoc) disabled in production
- Price refresh endpoint requires API key authentication

---

**Last Updated**: 2026-02-23
