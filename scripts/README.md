# Scripts Directory — RateShift Utility Scripts

Utility scripts for managing infrastructure, testing, data migration, and operational tasks for the RateShift project.

## Script Index

| Script | Type | Description | Prerequisites |
|--------|------|-------------|---------------|
| `dsp_bootstrap.py` | Python | Build codebase dependency graph (363 entities, 741 imports, 0 cycles) | `dsp-cli.py` in root |
| `webapp_test.py` | Python | Playwright E2E tests for live production site (25 tests) | System `python3` + Playwright |
| `scale_check.py` | Python | Infrastructure scaling diagnostic with threshold alerts | Optional: RENDER_API_KEY |
| `health-check.sh` | Bash | Service health verification (backend, frontend, Redis) | curl, redis-cli |
| `deploy.sh` | Bash | Deployment orchestrator (dev/staging/production) | Docker, Docker Compose, .env |
| `notion_hub_setup.py` | Python | Create/initialize Notion workspace with 3 databases | Notion API key |
| `backup.sh` | Bash | PostgreSQL and Redis backup with retention policy | psql, redis-cli |
| `restore.sh` | Bash | Restore PostgreSQL and Redis from backups | psql, redis-cli |
| `docker-entrypoint.sh` | Bash | Docker container startup orchestrator | Docker |
| `install-hooks.sh` | Bash | Git hook installation for local dev | Git |
| `production-deploy.sh` | Bash | Render production deployment with migration validation | Render CLI, git |
| `project-intelligence-sync.sh` | Bash | Sync project state to external intelligence system | curl, jq |
| `verification-loop-full.sh` | Bash | Full verification and testing loop | `.venv`, Docker |
| `stream-chain-run.sh` | Bash | Stream-chain pipeline runner (data processing) | Node.js/npm |
| `loki-feature.sh` | Bash | Loki Mode feature scaffolding | Python 3 |
| `loki-verify.sh` | Bash | Verify Loki memory index integrity | Python 3 |
| `loki-decompose.py` | Python | Decompose Loki RARV cycles into tasks | Loki Python SDK |
| `run_migrations_*.py` | Python | Database migration runners (direct Neon connect) | `.venv`, psycopg2 |
| `load_test.js` | JavaScript | K6 load testing script (10K RPS simulation) | Node.js, k6 |
| `setup_uptimerobot.py` | Python | Configure UptimeRobot monitoring for endpoints | UptimeRobot API key |
| `init_timescaledb.sql` | SQL | Legacy TimescaleDB initialization (archived, now using Neon PostgreSQL) | psql |

## Core Scripts

### dsp_bootstrap.py

Build and maintain the DSP (Data Structure Protocol) codebase graph -- a map of 363 entities with 741 import relationships and 0 circular dependencies.

```bash
# Run full bootstrap (registers all entities)
python3 scripts/dsp_bootstrap.py

# Query the DSP graph
python3 dsp-cli.py --root . search "ensemble"     # Find entities matching term
python3 dsp-cli.py --root . get-recipients <uid>  # Show who imports this entity
python3 dsp-cli.py --root . get-children <uid> --depth 3  # Show dependencies
```

Output: `.dsp/uid_map.json` (source path → UID mapping)

### webapp_test.py

Comprehensive Playwright test suite for the live production site. Tests page loads, navigation, auth flows, and API health.

```bash
# Run all tests (requires system Python with Playwright)
python3 scripts/webapp_test.py

# Expected output
# [PASS] Homepage loads
# [PASS] Pricing page accessible
# [PASS] Auth form renders
# ... (25 total tests)
# Summary: 23 pass, 0 fail, 2 warn
```

Prerequisites:
- System `python3` (not `.venv`) because Playwright needs separate browser binary
- Run with: `python3 scripts/webapp_test.py`, not `.venv/bin/python`

### scale_check.py

Infrastructure diagnostic tool that reports current utilization and identifies scaling triggers based on thresholds in `docs/SCALING_PLAN.md`.

```bash
# Run scaling check
python3 scripts/scale_check.py

# Machine-readable output (for CI)
python3 scripts/scale_check.py --json

# Include Render API diagnostics (requires RENDER_API_KEY)
python3 scripts/scale_check.py --check-render

# Output includes:
# - Backend latency (vs 1000ms warning / 2000ms critical thresholds)
# - Neon active hours (vs 80% of plan limit)
# - Neon storage (vs 80% of plan limit)
# - Render instance CPU/memory
# - Redis memory usage
```

Environment variables:
- `RENDER_API_KEY`: Optional, for service metadata
- `RENDER_SERVICE_ID`: Default `srv-d649uhur433s73d557cg`
- `BACKEND_URL`: Default `https://api.rateshift.app`
- `DATABASE_URL`: Optional, for database diagnostics
- `REDIS_URL`: Optional, for Redis diagnostics

### health-check.sh

Verify all services are running and responding:

```bash
# Quick health check
./scripts/health-check.sh

# Verbose output with response times
./scripts/health-check.sh --verbose

# Checks:
# - Backend API (http://localhost:8000/health → 200)
# - Frontend (http://localhost:3000 → 200)
# - Redis (PING → PONG)
```

Exit codes: 0 (all healthy), 1 (failures detected)

### deploy.sh

Deployment orchestrator supporting dev, staging, and production environments:

```bash
# Deploy to development (default)
./scripts/deploy.sh

# Deploy to staging
./scripts/deploy.sh staging

# Deploy to production (requires Docker, .env file, DB migration gate)
./scripts/deploy.sh production

# Steps:
# 1. Pre-deployment checks (.env, Docker running, required vars)
# 2. Build Docker images
# 3. Run backend + ML tests (skip in development)
# 4. Start services with docker-compose
# 5. Health checks
# 6. Post-deployment tasks
```

### notion_hub_setup.py

Initialize the Notion workspace with three interconnected databases:

```bash
# Create hub and all databases
python3 scripts/notion_hub_setup.py

# Creates:
# - Hub page (workspace root)
# - Project Tracker DB (tasks, milestones, dependencies)
# - Automation Workflows DB (recurring tasks, schedule info)
# - Architecture Decisions DB (decision logs, rationale)
# - Dashboard views (linked to each database)

# Output: `.notion_hub_ids.json` (database IDs for future updates)
```

Requires Notion API key in `~/.config/notion/api_key`

### backup.sh / restore.sh

Backup and restore databases with retention policy:

```bash
# Backup PostgreSQL and Redis
./scripts/backup.sh

# Full backup with compression
./scripts/backup.sh --full

# Restore from latest backup
./scripts/restore.sh

# Restore to specific date
./scripts/restore.sh 20260310_143022

# Retention: 7 days (configurable via RETENTION_DAYS env var)
# Backup location: /backups/ (configurable via BACKUP_DIR)
```

## Database Migration Scripts

### run_migrations_*.py

Direct migration runners using `psycopg2` for Neon PostgreSQL:

```bash
# Run specific migration batch
.venv/bin/python scripts/run_migrations_018_019.py

# Or run all migrations
.venv/bin/python scripts/run_migrations_007_019.py

# Prerequisites:
# - .venv activated
# - DATABASE_URL env var set (Neon connection string)
# - Direct endpoint (for DDL): ep-withered-morning-aix83cfw.c-4...
```

## CI/CD & Development Scripts

### production-deploy.sh

Render production deployment with migration validation:

```bash
./scripts/production-deploy.sh

# Steps:
# 1. Validate migration numbering (sequential, IF NOT EXISTS, GRANT)
# 2. Trigger Render deploy via Composio
# 3. Monitor rollout (5 min timeout)
# 4. Post success/failure to Slack #deployments
```

### verification-loop-full.sh

Run full verification suite locally:

```bash
./scripts/verification-loop-full.sh

# Runs:
# 1. Backend tests (.venv/bin/python -m pytest)
# 2. ML tests (.venv/bin/python -m pytest ml/)
# 3. Frontend tests (npm test)
# 4. E2E tests (Playwright)
# 5. Code linting + formatting checks
# 6. Security scans (gitleaks, Tripy in Docker)
```

### stream-chain-run.sh

Execute stream-chain data processing pipelines:

```bash
./scripts/stream-chain-run.sh <pipeline-name>

# Pipelines:
# - price-ingest: Fetch + validate electricity prices
# - feature-engineer: Generate 73-feature dataset
# - model-train: Run hyperparameter tuning + training
# - forecast-validate: Backtest + accuracy checks
```

### install-hooks.sh

Install Git hooks for local development:

```bash
./scripts/install-hooks.sh

# Installs hooks in .git/hooks/:
# - pre-commit: Code format + linting
# - pre-push: Run test suite before push
# - commit-msg: Validate commit message format
```

## Loki Mode Scripts

### loki-feature.sh

Scaffold a new Loki feature with boilerplate:

```bash
./scripts/loki-feature.sh <feature-name>

# Example:
./scripts/loki-feature.sh A/B-testing

# Creates:
# - Feature skeleton in .loki/features/
# - RARV cycle template
# - Metrics definition file
```

### loki-verify.sh

Verify Loki memory index integrity:

```bash
./scripts/loki-verify.sh

# Checks:
# - Memory database integrity
# - Vector embeddings alignment
# - Event queue consistency
# - PYTHONPATH workaround applied

# If stale, rebuilds memory index
```

### loki-decompose.py

Break down Loki RARV cycles into actionable tasks:

```bash
PYTHONPATH="$HOME/.claude/skills/loki-mode" python3 scripts/loki-decompose.py

# Reads: .loki/HUMAN_INPUT.md
# Outputs: Decomposed task breakdown with subtasks + dependencies
```

## Load Testing

### load_test.js

K6 load testing script for stress testing endpoints:

```bash
# Install K6 if needed
brew install k6  # macOS
# or
apt-get install k6  # Linux

# Run load test
k6 run scripts/load_test.js

# Configuration (in script):
# - 10K RPS target
# - 300s duration
# - /prices, /predict, /alerts endpoints
# - Gradual ramp-up and ramp-down
```

## Monitoring Setup

### setup_uptimerobot.py

Configure UptimeRobot monitoring for critical endpoints:

```bash
python3 scripts/setup_uptimerobot.py

# Creates monitors for:
# - Backend health endpoint
# - Frontend homepage
# - API Gateway (Cloudflare Worker)
# - Neon database
# - Redis

# Requires UptimeRobot API key in environment or 1Password
```

## Notes

- **Python scripts**: Always use `.venv/bin/python -m <module>` for consistency (Python 3.12)
- **Bash scripts**: Set `set -e` for fail-fast, include colored output for clarity
- **Neon connections**: Use pooled endpoint (`-pooler.`) for most connections, direct endpoint (`-aix83cfw.`) only for DDL
- **GHA integration**: Scripts callable from GitHub Actions workflows with retry logic via `retry-curl` composite action
- **Loki PYTHONPATH**: Always prefix Loki scripts with `PYTHONPATH="$HOME/.claude/skills/loki-mode"`
- **System vs venv Python**: Webapp test uses system `python3` (Playwright requirement), others use `.venv/bin/python`
