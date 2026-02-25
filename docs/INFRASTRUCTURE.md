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
8. [Loki Mode Orchestration](#loki-mode-orchestration)

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

### Neon PostgreSQL (Production Database)

**Project ID:** `holy-pine-81107663`

| Property | Value |
|----------|-------|
| Branch | `main` (br-broad-queen-aemirrrs) |
| Compute Endpoint | `ep-withered-morning-aix83cfw` (us-east-1) |
| Tables | 14 (see CODEMAP_BACKEND.md for full list) |
| PK Type | UUID (all tables) |
| App Role | `neondb_owner` |

**CRITICAL:** The Neon project has multiple compute endpoints. The app's `DATABASE_URL` uses `ep-withered-morning-aix83cfw` (us-east-1). The Neon MCP tool may connect to a different endpoint (`ep-lingering-forest-aebmj5t0`, us-east-2). Always verify which endpoint you're targeting when running migrations. Use the app's `DATABASE_URL` directly for production migrations.

### Render Deployment

**Service:** `electricity-optimizer-api`

| Property | Value |
|----------|-------|
| Dockerfile | `./Dockerfile` (root, not backend/) |
| Python | 3.11-slim (multi-stage build) |
| User | `appuser` (non-root, UID 1000) |
| Health Check | `curl -f http://localhost:${PORT:-8000}/health` |
| Auto-deploy | On push to `main` |
| Deploy Hook | Stored in 1Password |

**Dockerfile Notes:**
- Builder stage requires both `gcc` and `g++` for hnswlib C++ compilation
- Runtime stage only needs `curl` (for health checks)
- HNSW vector store uses ephemeral filesystem on Render; repopulated by nightly learning

**Required Environment Variables (Render):**

| Variable | Source | Notes |
|----------|--------|-------|
| `DATABASE_URL` | Neon | Must use `ep-withered-morning-aix83cfw` endpoint |
| `REDIS_URL` | Redis provider | |
| `BETTER_AUTH_SECRET` | Generated | `openssl rand -hex 32` |
| `BETTER_AUTH_URL` | App URL | Base URL for Better Auth |
| `JWT_SECRET` | Generated | 32+ chars (internal API key validation only) |
| `ENVIRONMENT` | `production` | |
| `INTERNAL_API_KEY` | Generated | `openssl rand -hex 32` |

**Render CLI:**
```bash
brew install render    # Install
render login           # Authenticate (opens browser)
render services list   # List services
render deploys list    # List recent deploys
```

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
   - Neon PostgreSQL free tier for database

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
- 1Password for production secrets (vault: "Electricity Optimizer")
- Never commit secrets to Git
- INTERNAL_API_KEY for service-to-service authentication (GitHub Actions + Render)

**1Password Vault** ("Electricity Optimizer"):

| Item | Category | Purpose |
|------|----------|---------|
| Neon PostgreSQL | Login | DATABASE_URL connection string |
| Redis | Login | REDIS_URL connection string |
| JWT Secret | Login | JWT_SECRET (internal API validation only) |
| Better Auth Secret | Login | BETTER_AUTH_SECRET signing key |
| Internal API Key | Login | INTERNAL_API_KEY for service-to-service auth |
| Stripe Keys | Login | stripe_secret_key, stripe_webhook_secret |
| Render Deploy Hook | Login | Render deploy hook URL |
| Notion API Key | Login | Notion integration API key |

**GitHub Actions Secrets** (required for adaptive learning workflows):
- `INTERNAL_API_KEY` — same key as Render env var
- `BACKEND_URL` — production API URL (no trailing slash)

### Access Control

- Grafana behind VPN or IP whitelist
- Neon Auth (Better Auth) session-based authentication with httpOnly cookies
- Internal API key authentication for service-to-service calls
- Role-based access control
- API documentation (Swagger/ReDoc) disabled in production
- Price refresh endpoint requires API key authentication

---

## Loki Mode Orchestration

Loki Mode is an agent orchestration layer that manages session lifecycle, memory persistence, and event-driven coordination for Claude Code sessions in this project.

**Version:** v5.53.0 (npm global install + skill at `~/.claude/skills/loki-mode/`)

### MCP Server Registration

Loki Mode is registered as an MCP server in the project's `.mcp.json`. This allows Claude Code to invoke Loki capabilities (memory, events, orchestration commands) through the standard MCP tool interface.

### Session Lifecycle Hooks

| Hook Type | Script | Purpose |
|-----------|--------|---------|
| `PreToolUse` | `activate-orchestration.sh` | Auto-initializes Loki Mode at the start of each Claude Code session. Creates `/tmp/claude-orchestration-active` marker to prevent re-initialization. |
| `Stop` | `session-end-orchestration.sh` | Graceful shutdown: persists session state, flushes memory, cleans up the orchestration marker. |

**Logs:**
- Initialization: `.claude/logs/orchestration-init.log`
- Shutdown: `.claude/logs/orchestration-shutdown.log`

### Event Bus

Loki Mode uses a file-based event bus at `.loki/events/` for inter-component communication.

| Component | Path | Purpose |
|-----------|------|---------|
| Event directory | `.loki/events/` | Stores event payloads as JSON files |
| Event bridge | `loki-event-sync.sh` | Bridges Loki events to external consumers (supports `--dry-run` for testing) |

Events are produced by Loki Mode during orchestration (e.g., session start, memory writes, task completions) and consumed by the sync bridge for integration with other tooling.

### Memory Layer

Loki Mode provides an IndexLayer memory system that persists knowledge across sessions.

| Property | Value |
|----------|-------|
| Namespace | `electricity-optimizer` |
| Backend | IndexLayer (embedded vector index) |
| Persistence | Survives session restarts via Loki's memory store |
| Access | `mcp__loki__memory_store`, `mcp__loki__memory_retrieve` (via MCP) |

Memory is used to store learned patterns, session context, and cross-session state that supplements the project's MEMORY.md file.

### Dashboard

Loki Mode includes an optional web dashboard for inspecting orchestration state, memory contents, and event history.

| Property | Value |
|----------|-------|
| Port | 57374 |
| Start | Manual (`loki dashboard` or equivalent) |
| URL | `http://localhost:57374` |

The dashboard is not started automatically. It is intended for debugging and inspection during development, not for production use.

---

## Claude Flow Orchestration

Claude Flow is a multi-agent orchestration platform that provides MCP tools, code analysis, and session lifecycle intelligence.

**Version:** v3.1.0-alpha.44 (npm global install, `npx claude-flow`)

### MCP Server Registration

Registered in `.mcp.json` as `claude-flow`. Starts via `npx claude-flow mcp start` (stdio mode). Exposes 221 MCP tools across categories: agents, swarms, memory, hooks, neural, security, config.

| Property | Value |
|----------|-------|
| Package | `claude-flow@3.1.0-alpha.44` |
| MCP Transport | stdio |
| Shared State | `.swarm/memory.db` (sql.js + HNSW, 384-dim vectors) |
| Config Dir | `.claude-flow/` (gitignored) |

### Session Lifecycle Integration

The activation and shutdown hooks coordinate Claude Flow alongside Loki Mode:

| Hook | Script | Claude Flow Actions |
|------|--------|---------------------|
| `PreToolUse` | `activate-orchestration.sh` | Detect MCP server (skip CLI daemon if active), verify memory, bootstrap hooks intelligence (one-time pretrain) |
| `Stop` | `session-end-orchestration.sh` | Persist state, export SONA metrics to `.claude-flow/logs/sona-metrics-*.json`, sync Loki learnings |

**MCP vs CLI fallback:** If the MCP server is running (detected via `npx claude-flow mcp status`), the activation hook skips CLI daemon startup. Otherwise, it falls back to `npx claude-flow hooks session-start` for environments where MCP isn't available.

### CI Integration

Two GitHub Actions workflows use Claude Flow for code analysis:

| Workflow | Trigger | Analysis |
|----------|---------|----------|
| `code-analysis.yml` | PRs to `main` | Diff risk, complexity (threshold 15), circular deps, security scan |
| `backend-ci.yml` | Push/PR to `main`/`develop` (backend paths) | Security scan + dependency audit (added to existing security-scan job) |

All analysis steps use `continue-on-error: true` to prevent blocking CI on tool failures. Reports are uploaded as JSON artifacts with 30-day retention.

### Workflow Templates

Local orchestration templates in `.claude-flow/workflows/` (gitignored):

| Template | Chain | Schedule |
|----------|-------|----------|
| `price-pipeline.yaml` | price-sync -> observe-forecasts -> verify-accuracy | Every 6 hours |
| `nightly-learning.yaml` | run-learning -> validate-weights -> persist-memory + update-vectors | 4 AM UTC |

### Hooks Intelligence

One-time bootstrap via `npx claude-flow hooks pretrain --directory .` populates the ReasoningBank from repo history. Marker file `.claude-flow/.hooks-pretrained` prevents re-running.

### Key Caveats

- **GitHub tools are stubs:** `github_workflow`, `github_repo_analyze`, etc. generate local mock data. Use `gh` CLI for real GitHub operations.
- **Package name:** Always use `claude-flow`, NOT `@claude-flow/cli@v3alpha` (doesn't exist on npm).
- **Permissions:** 5 MCP tool permissions pre-granted in `settings.local.json`; remaining 216 prompt on first use.

---

**Last Updated**: 2026-02-25
