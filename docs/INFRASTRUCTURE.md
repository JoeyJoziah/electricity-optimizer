# Infrastructure Documentation - RateShift

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
                          +------- ----+---- -------+
                          |   Cloudflare        |
                          |   (Edge Layer)      |
                          | api.rateshift.app   |
                          +--------+------------+
                                   |
                    +------------------+------------------+
                    |                                     |
           +--------+--------+                   +--------+--------+
           |    Frontend     |                   |    Backend API   |
           |   (Vercel)      |                   |   (Render)       |
           | rateshift.app   |                   |   FastAPI        |
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
           |  31 workflows: CI/CD, deploy, cron jobs      |
           |  price-sync, check-alerts, kpi-report, etc.  |
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
| ci.yml | On push/PR to main/develop | Unified CI: path-filtered backend/frontend/ML tests, security scan, Docker build |
| e2e-tests.yml | Daily + on push/PR | Playwright E2E + Lighthouse audits + load/security tests |
| deploy-production.yml | On release publish | Multi-stage security gate (Bandit + npm audit + OWASP) + GHCR multi-platform builds (linux/amd64 + linux/arm64) + parallel backend/frontend deploy hooks + migration-gate validation + progressive retry (15s/30s/60s) + Slack/webhook notification + rollback automation |
| deploy-staging.yml | On push to develop | GHCR push + Render deploy hooks + smoke tests |
| deploy-worker.yml | Manual trigger or release | Cloudflare Worker deployment via `wrangler deploy` + smoke tests to api.rateshift.app |
| price-sync.yml | `0 */6 * * *` | Electricity price data ingestion |
| observe-forecasts.yml | `30 */6 * * *` | Backfill actual prices into forecast observations |
| nightly-learning.yml | `0 4 * * *` | Adaptive learning: accuracy, bias detection, weight tuning |
| model-retrain.yml | Weekly Sun 2AM UTC | ML model retraining pipeline |
| keepalive.yml | Hourly | Render backend keep-alive ping |
| code-analysis.yml | PRs to main | Claude Flow diff risk, complexity, security analysis |
| check-alerts.yml | Every 30 min | Price alert pipeline (Phase 2) |
| fetch-weather.yml | Every 6 hours | Weather data ingestion for all 51 US regions (Phase 2) |
| market-research.yml | Daily 2am UTC | Top 10 regions market intelligence (Phase 2) |
| sync-connections.yml | Every 2 hours | UtilityAPI connection sync (Phase 2) |
| scrape-rates.yml | Daily 3am UTC | Auto-discover suppliers and scrape rates (Phase 2) |
| dunning-cycle.yml | Daily 7am UTC | Overdue payment escalation — find failing accounts, send final dunning email, downgrade (Phase 3) |
| kpi-report.yml | Daily 6am UTC | Nightly business metrics aggregation (Phase 3) |
| data-health-check.yml | Daily | Data pipeline health check — row counts, last-write timestamps, empty table flags |
| self-healing-monitor.yml | Daily 9am UTC | Monitors 16 workflows for repeated failures; auto-creates/closes GitHub issues |
| db-maintenance.yml | Weekly Sunday 3am UTC | Database optimization — vacuum, analyze, index maintenance |
| secret-scan.yml | PRs + push to main | Gitleaks secret scanning |
| owasp-zap.yml | Weekly Sunday 4am UTC | OWASP ZAP baseline security scan against Render backend |
| scan-emails.yml | Daily 4am UTC | Batch scan active email_import connections, extract rates |
| scrape-portals.yml | Weekly Sunday 5am UTC | Batch scrape portal_scrape connections |
| fetch-gas-rates.yml | Scheduled | Natural gas rate fetching |
| fetch-heating-oil.yml | Scheduled | Heating oil price fetching from EIA |
| detect-rate-changes.yml | Scheduled | Multi-utility rate change detection and alerting |
| utility-type-tests.yml | On push/PR | Utility-type-specific test suite |
| deploy-staging.yml | On push to develop | GHCR push + Render deploy hooks + smoke tests |
| _backend-tests.yml | (callable) | Reusable backend test job (postgres + redis services) |
| _docker-build-push.yml | (callable) | Reusable Docker build + GHCR push |

**Composite Actions** (`.github/actions/`):

| Action | Purpose |
|--------|---------|
| `setup-python-env` | Python + pip cache + requirements install (replaces duplicated setup across 5+ workflows) |
| `setup-node-env` | Node.js + npm cache + `npm ci` in frontend/ |
| `wait-for-service` | Health-check polling with configurable timeout/interval (replaces all `sleep` calls) |
| `retry-curl` | Curl with exponential backoff and jitter; 4xx fail-fast (except 429/408); retries on 5xx/429/408/000 |
| `notify-slack` | Color-coded Slack failure alerts (critical=danger, warning, info=blue) via incoming webhook to `#incidents` |
| `validate-migrations` | Convention checks: sequential numbering, IF NOT EXISTS on CREATE TABLE, GRANT TO neondb_owner, no SERIAL/BIGSERIAL |

**Concurrency Controls**: All 31 GHA workflows have concurrency groups. CI and analysis workflows cancel in-progress runs on new pushes. Deploy and scheduled workflows do not cancel (to prevent partial deploys). All jobs have explicit `timeout-minutes`.

**Render Deploy Hooks**: Production and staging deploy workflows trigger Render builds via deploy hook URLs stored in GitHub secrets (`RENDER_DEPLOY_HOOK_BACKEND`, `RENDER_DEPLOY_HOOK_FRONTEND`). Deploy workflows include self-healing smoke tests that auto-retry on failure.

### Board Sync (Local Automation)

The board-sync system keeps GitHub Projects board #4 in sync with development activity. It runs locally via git hooks and Claude Code hooks. **Notion sync is handled exclusively by Rube recipe `rcp_73Kc9K65YC5T` (every 6h) — no local hooks or GHA workflows.**

**Orchestrator:** `.claude/hooks/board-sync/sync-boards.sh`

| Subcommand | Description |
|------------|-------------|
| `all` | Sync GitHub Projects (default) |
| `github` | Sync GitHub Projects only |
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

**Notion Integration (2026-03-06 Rebuild):**

Notion sync was rebuilt on 2026-03-06. The old local sync scripts (`notion_sync.py`, `github_notion_sync.py`, `notion_setup_schema.py`) and GHA workflow (`notion-sync.yml`) were deleted. Notion is now synced exclusively via Rube recipe `rcp_73Kc9K65YC5T` (every 6h, GitHub -> Notion).

| Resource | ID |
|----------|-----|
| Hub Page | `31bb9fc9-1d9d-813e-a108-fd7d4ef49fd7` |
| Project Tracker DB | `31bb9fc9-1d9d-81ed-815a-d6fb35ec0d3f` (32 entries) |
| Automation Workflows DB | `31bb9fc9-1d9d-81ba-bb42-cf59a7abe679` (11 entries) |
| Architecture Decisions DB | `31bb9fc9-1d9d-8174-bb56-c73d65fc3a0e` (15 entries) |
| Old Database (archived) | `24bcbe22-37de-449f-b694-3544f0d864e3` |

**Setup script:** `scripts/notion_hub_setup.py` (rerunnable — detects existing hub page).

### Supplier Registry Caching

**Repository:** `backend/repositories/supplier_repository.py`

The supplier registry (both `SupplierRepository` and `SupplierRegistryRepository`) uses Redis caching with a 1-hour TTL to optimize semi-static supplier data lookups.

| Property | Value |
|----------|-------|
| Cache TTL | 3600 seconds (1 hour) |
| Key Pattern | `supplier:<method>:<args...>` |
| Fallback | Automatic database fallback if Redis is unavailable |
| Invalidation | Explicit via `clear_cache()` / `clear_registry_cache()` on write operations |
| Serialization | JSON (handles datetime via `default=str` fallback) |

**Cache-backed Methods:**
- `get_by_name()` — single supplier lookup
- `list_by_region()` — regional supplier listings
- All other write paths call `clear_cache()` to maintain consistency

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

### Service Discovery & API URLs (2026-03-04)

**Local Development (Docker):**
- `http://backend:8000` - Backend API
- `redis://redis:6379` - Redis

**Production (Client → Server):**
- Client requests: `https://rateshift.app/api/v1/*` (same-origin via Next.js rewrites to `BACKEND_URL`)
- Edge proxy: `api.rateshift.app/api/v1/*` (Cloudflare Worker `rateshift-api-gateway`)
- Origin backend: Render FastAPI at `electricity-optimizer.onrender.com` (routed through Worker)
- Database: Neon PostgreSQL (serverless, accessed via connection string — no local container)

**Request Flow:**
```
Client → https://rateshift.app/api/v1/* (Next.js rewrite)
         ↓
Next.js Server → BACKEND_URL=https://api.rateshift.app (server-to-server)
                 ↓
                 Cloudflare Worker (rateshift-api-gateway)
                 ├─ Cache API (2-tier caching)
                 ├─ KV store (rate limiting state)
                 ├─ Bot detection (heuristic scoring)
                 ├─ Internal auth (X-API-Key compare)
                 └─ Origin: https://electricity-optimizer.onrender.com
                    ↓
                    Render Backend (FastAPI)
                    ↓
                    Neon Database
```

**Cross-Service Communication:**
- `NEXT_PUBLIC_API_URL=/api/v1` (frontend client-side, relative URL)
- `BACKEND_URL=https://api.rateshift.app` (frontend server-side, for rewrites and server-only calls)

### Cloudflare Worker (Edge Layer)

**Service:** `rateshift-api-gateway` (Worker deployed via `wrangler deploy` or GHA)

| Property | Value |
|----------|-------|
| Endpoint | `api.rateshift.app` (orange cloud proxied) |
| Account ID | `b41be0d03c76c0b2cc91efccdb7a10df` |
| Zone | `ac03dd28616da6d1c4b894c298c1da58` (Cloudflare Registrar for rateshift.app) |
| SSL Mode | Full (Strict) |
| Source | `workers/api-gateway/` (17 files, 77 vitest tests) |
| Bundle Size | 20.35 KiB / gzip 5.31 KiB |
| KV CACHE | `6946d19ce8264f6fae4481d6ad8afcd1` |
| KV RATE_LIMIT | `c9be3741ee784956a0d99b3fa0c1d6c4` |

**Capabilities:**
- **2-tier caching**: Cache API (longer TTL) + KV store (state management)
- **Rate limiting**: Standard (120/min), Strict (30/min), Internal (600/min)
- **Bot detection**: Heuristic scoring on TLS fingerprint, headers, patterns
- **Internal auth**: Constant-time X-API-Key comparison for `/internal/*` routes
- **CORS & security headers**: Origin allowlist, HSTS, X-Content-Type-Options, X-Frame-Options
- **Structured JSON logging**: All requests logged to Worker analytics
- **Request/response modification**: Headers, redirects, streaming support

**Deployment via GHA:**
- Workflow: `.github/workflows/deploy-worker.yml`
- Secrets: `CF_API_TOKEN`, `CF_ACCOUNT_ID`, `CF_ZONE_ID` (in GitHub)
- Trigger: Manual or on release publish
- Post-deploy: Smoke tests to `https://api.rateshift.app/*`

**Free Tier Limits:**
- 100K requests/day (typically uses 5-10K/day)
- 1GB storage in KV
- 1M KV writes/day
- All traffic routed through Worker regardless of tier

### Neon PostgreSQL (Production Database)

**Project ID:** `cold-rice-23455092` (Neon project name: "energyoptimize")

| Property | Value |
|----------|-------|
| Production Branch | `production` (br-shy-sun-aibo9dns) — default |
| Preview Branch | `vercel-dev` (br-little-salad-ainqjnuj) — for Vercel preview deployments |
| Pooled Endpoint | `ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech` (PgBouncer) |
| Direct Endpoint | `ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech` (for DDL/migrations) |
| Public Tables | 44 (see CODEMAP_BACKEND.md for full list) |
| Auth Tables | 9 (neon_auth schema — managed by Better Auth) |
| Total Tables | 53 (44 public + 9 neon_auth) |
| Migrations | 50 files total (init_neon through 050_community_posts_indexes), 49 deployed to production (through 049_community_tables) |
| PK Type | UUID (all tables) |
| App Role | `neondb_owner` |

**Neon MCP:** Always use `projectId: "cold-rice-23455092"` when calling `mcp__Neon__*` tools. The previous stale project `holy-pine-81107663` was deleted (0 users, missing tables, wrong region).

**Recent Migrations (2026-03-10 to 2026-03-16):**
- Migration 026: NotificationDispatcher system (notification_history, notification_templates, error_message column)
- Migration 027: ModelConfigRepository (model_configs, model_versions tables)
- Migration 028: FeedbackWidget (feedback entries)
- Migration 029: Notification delivery tracking (notification_delivery_state, notification_error_message)
- Migration 030: Model versioning & A/B testing (model_versions, ab_tests, ab_outcomes, ab_assignments)
- Migration 031: Agent tables (agent_conversations, agent_usage_daily)
- Migration 032: Error message tracking (error_message column added)
- Migration 033: Model predictions & A/B assignments (model_predictions, model_ab_assignments)
- Migration 034: Portal credentials (portal credential columns on user_connections)
- Migration 035: Backfill neon_auth users
- Migration 036-037: Performance indexes
- Migration 038: Utility accounts
- Migration 039: Referrals
- Migration 040: Gas supplier seed (12 suppliers)
- Migration 041: Community solar programs (15 programs across 13 states)
- Migration 042: CCA programs
- Migration 043: Heating oil (prices, dealers)
- Migration 044: Multi-utility alerts
- Migration 045: Affiliate tracking
- Migration 046: Propane prices
- Migration 047: Water rates (JSONB rate_tiers)
- Migration 048: Utility feature flags
- Migration 049: Community tables (posts, votes, reports)
- Migration 050: Community posts indexes (not yet deployed to production)

**Migration 020 (2026-03-02): Price Query Indexes**
- Creates 3 composite indexes on `electricity_prices` table:
  - `idx_prices_region_supplier_created` — supports supplier comparison queries with `created_at DESC` ordering
  - `idx_prices_region_utilitytype_created` — supports multi-utility history queries with `created_at DESC` ordering
  - `idx_users_region` — supports region-based user lookups
- All indexes created with `CONCURRENTLY IF NOT EXISTS` for safe re-running on live databases
- No table locks; safe for production use

### Render Deployment

**Service:** `electricity-optimizer-api`

| Property | Value |
|----------|-------|
| Dockerfile | `./Dockerfile` (root, not backend/) |
| Python | 3.12-slim (multi-stage build) |
| User | `appuser` (non-root, UID 1000) |
| Health Check | `curl -f http://localhost:${PORT:-8000}/health` |
| Auto-deploy | On push to `main` |
| Deploy Hook | Stored in 1Password |
| App Factory | Uses `backend/app_factory.py` via `backend/main.py` |

**Dockerfile Notes:**
- Builder stage requires both `gcc` and `g++` for hnswlib C++ compilation
- Runtime stage only needs `curl` (for health checks)
- HNSW vector store uses ephemeral filesystem on Render; repopulated by nightly learning

**Application Factory Pattern:**
- `backend/main.py` delegates all construction to `app_factory.create_app()`
- Returns tuple: `(FastAPI app instance, rate limiter middleware instance)`
- Enables proper test isolation and environment-specific configuration
- Maintains backward compatibility: existing imports of `from main import app` continue to work

**Required Environment Variables (Render):**

| Variable | Source | Notes |
|----------|--------|-------|
| `DATABASE_URL` | Neon | Must use `ep-withered-morning-aix83cfw` endpoint |
| `REDIS_URL` | Redis provider | Upstash Redis for caching, rate limiting, ensemble weights |
| `BETTER_AUTH_SECRET` | Generated | `openssl rand -hex 32` |
| `BETTER_AUTH_URL` | App URL | Base URL for Better Auth |
| `JWT_SECRET` | Generated | 32+ chars (internal API key validation only) |
| `ENVIRONMENT` | `production` | |
| `INTERNAL_API_KEY` | Generated | `openssl rand -hex 32` |
| `ALLOWED_REDIRECT_DOMAINS` | Config | JSON array or comma-separated (Stripe redirect domains) |
| `FIELD_ENCRYPTION_KEY` | Generated | 64 hex chars / 32 bytes (AES-256-GCM, required in production) |
| `SMTP_HOST` | Config | Gmail SMTP fallback (`smtp.gmail.com`) |
| `SMTP_PORT` | Config | SMTP port (`587` for TLS) |
| `SMTP_USERNAME` | Gmail | Gmail address used as SMTP sender |
| `SMTP_PASSWORD` | Gmail | Gmail App Password (requires 2FA on Google account) |
| `EMAIL_FROM_ADDRESS` | Config | Sender address for outbound emails |

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
- 1Password for production secrets (vault: "RateShift")
- Never commit secrets to Git
- INTERNAL_API_KEY for service-to-service authentication (GitHub Actions + Render)
- `BETTER_AUTH_SECRET` field validator: enforces 32+ character minimum in production (`Settings` model)
- `INTERNAL_API_KEY != JWT_SECRET` model validator: prevents key reuse between internal API auth and JWT signing
- **Env var audit** (2026-03-03): 27 secrets reviewed — 27 PASS, 0 FAIL. Full report: `.swarm-reports/ENV_VAR_AUDIT_FINAL.md`

**1Password Vault** ("RateShift" — 28+ items, mapped to SecretsManager):

| Item | Category | Fields | Purpose |
|------|----------|--------|---------|
| Neon PostgreSQL | Login | `database_url` | DATABASE_URL connection string (ep-withered-morning endpoint) |
| Redis Upstash | Login | `redis_url`, `redis_password` | Upstash Redis for caching, rate limiting, ensemble weights |
| API Secrets | Login | `jwt_secret`, `internal_api_key` | JWT (internal validation only) + service-to-service API key |
| Stripe Keys | Login | `secret_key`, `webhook_secret`, `price_pro`, `price_business` | Stripe payment integration |
| Pricing APIs | Login | `flatpeak`, `nrel`, `iea`, `eia` | API keys for FlatPeak, NREL, IEA, EIA pricing providers |
| OpenWeatherMap | Login | `api_key` | Weather data API key (free tier: 1000 calls/day) |
| Monitoring | Login | `sentry_dsn` | Sentry DSN for error tracking |
| Field Encryption | Login | `key` | AES-256-GCM key for account/meter number encryption |
| Render Deploy Hook | Login | `url` | Render.com deploy hook URL |
| Render Service | Login | `service_id` | Render service metadata (srv-d649uhur433s73d557cg) |
| GitHub Repository | Login | `token`, `webhook_secret` | GitHub token and webhook secret for CI/CD |
| Neon Auth | Login | `secret`, `auth_url`, `auth_database_url` | Better Auth signing key, auth endpoint, and database URL |
| Codecov | Login | `token` | Code coverage tracking |
| Notion Integration | Login | `api_token`, `database_id` | Notion API credentials for roadmap sync |
| Vercel Frontend | Login | `vercel_token`, `project_id` | Vercel deployment credentials for frontend |
| OAuth Providers | Login | `google_client_id`, `google_client_secret` | OAuth provider credentials for social login |
| Email OAuth | Login | `gmail_client_id`, `gmail_client_secret`, `outlook_client_id`, `outlook_client_secret` | Email OAuth credentials for connection import |
| Resend | Login | `resend_api_key`, `email_from_address` | Transactional email service (backend + frontend auth emails) |
| Gmail SMTP | Login | `smtp_host`, `smtp_port`, `smtp_username`, `smtp_password` | Gmail SMTP fallback (smtp.gmail.com:587, TLS, App Password) |
| CORS and Redirects | Login | `allowed_origins`, `allowed_redirect_domains` | CORS origin whitelist and Stripe redirect domain config |

**SecretsManager** (`backend/config/secrets.py`): 27 mappings covering all environment variables sourced from 1Password. Each mapping specifies the vault item, field name, and target env var.

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

### Request Tracing & Correlation

- **Tracing middleware** (`backend/middleware/tracing.py`) adds unique correlation IDs to all requests
- Correlation IDs propagated through logs, metrics, and error reports for end-to-end request tracking
- Enables faster debugging and performance analysis across distributed operations

### Feature Flags & Gradual Rollout

- Feature flags service for gradual rollout control of new functionality
- Enables A/B testing and safe feature validation in production without full deployment
- Flags stored in environment config, evaluated per-request with caching

### Data Retention & Maintenance

- **Maintenance service** automated data lifecycle management:
  - Activity logs: 365-day retention (auto-delete older records)
  - Bill uploads: 730-day retention (audit trail for billing disputes)
  - Connection sync records: Pruned based on user account lifecycle
- Scheduled purge jobs run nightly to enforce retention policies
- Ensures compliance with data minimization principles and reduces storage costs

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

One GitHub Actions workflow uses Claude Flow for code analysis:

| Workflow | Trigger | Analysis |
|----------|---------|----------|
| `code-analysis.yml` | PRs to `main` | Diff risk, complexity (threshold 15), circular deps, security scan |

Analysis steps use `continue-on-error: true` to prevent blocking CI on tool failures. Reports are uploaded as JSON artifacts with 30-day retention. The former `backend-ci.yml` Claude Flow integration was consolidated into `ci.yml`'s security-scan job.

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

**Last Updated**: 2026-03-16
