# Developer Guide

**Last Updated**: 2026-03-25

Quick-start guide for contributing to RateShift. For architecture details see `ARCHITECTURE.md`.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ | Backend (FastAPI) |
| Node.js | 20+ | Frontend (Next.js 16) |
| npm | 10+ | Package management |
| Git | 2.40+ | Version control |
| Wrangler | 3+ | Cloudflare Worker development |
| Docker | 24+ | Optional: containerized dev |

**Accounts needed** (for full local dev):
- Neon (database): Project `cold-rice-23455092`
- Stripe (payments): Test mode keys (`sk_test_*`)
- 1Password CLI (secrets): Vault "RateShift"

> For the complete list of 44 backend env vars, 4 CF Worker secrets, and 6 frontend vars, see `docs/ENV_REFERENCE.md`.

---

## Quick Start

### 1. Clone & Install

```bash
git clone git@github.com:JoeyJoziah/electricity-optimizer.git
cd electricity-optimizer

# Backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Frontend
cd frontend
npm install --legacy-peer-deps   # required: eslint 8 + eslint-config-next 16.x compat
cd ..
```

### 2. Environment Variables

Backend reads from env vars (dev) or 1Password (prod). Minimum for local dev:

```bash
# backend/.env (create this file)
DATABASE_URL=postgresql://neondb_owner:***@ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require
ENVIRONMENT=development
JWT_SECRET=dev-local-jwt-secret-at-least-32-characters-long
BETTER_AUTH_SECRET=dev-local-better-auth-secret-at-least-32-chars
INTERNAL_API_KEY=dev-local-internal-api-key-at-least-32-chars
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
FRONTEND_URL=http://localhost:3000

# Optional — enable features incrementally
# REDIS_URL=redis://localhost:6379
# FIELD_ENCRYPTION_KEY=<64-hex-chars>
# RESEND_API_KEY=re_...
# STRIPE_SECRET_KEY=sk_test_...
# EIA_API_KEY=...
# ENABLE_AI_AGENT=false
```

> Generate secrets: `python -c "import secrets; print(secrets.token_hex(32))"`

Frontend uses `NEXT_PUBLIC_*` env vars in `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=/api/v1
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

### 3. Run Locally

```bash
# Terminal 1: Backend
source .venv/bin/activate
cd backend && uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

Frontend at `http://localhost:3000`, API at `http://localhost:8000`.

---

## Running Tests

### Backend (pytest)

```bash
# ALWAYS use venv Python — system Python is missing dependencies
.venv/bin/python -m pytest backend/tests/ -v
.venv/bin/python -m pytest backend/tests/ -v --cov=backend --cov-report=html

# Run a single test file
.venv/bin/python -m pytest backend/tests/test_price_service.py -v

# Run ML tests
.venv/bin/python -m pytest ml/tests/ -v
```

Coverage threshold: 80%+. Current: 86%+ (2,976 tests).

> **Module-level cache isolation**: When adding module-level cache dicts (e.g., `_tier_cache`), always add a corresponding `autouse` fixture in `conftest.py` to clear the cache between tests. Detection signal: tests pass individually (`pytest test_foo.py`) but fail when run as a full suite (`pytest backend/tests/`).

### Frontend (Jest)

```bash
cd frontend
npm test              # Watch mode
npm run test:ci       # CI mode with coverage
```

Coverage threshold: 80% branches/functions/lines/statements. Current: 2,015 tests across 153 suites.

### E2E (Playwright)

```bash
cd frontend
npx playwright install    # First time only
npx playwright test       # All 5 browsers
npx playwright test --project=chromium  # Single browser
npx playwright test --ui  # Interactive UI mode
```

Current: 1,605 tests across 25 specs, 5 browser projects.

### CF Worker (vitest)

```bash
cd workers/api-gateway
npm test
```

Current: 90 tests.

---

## Database

### Neon PostgreSQL

- **Project**: `cold-rice-23455092` ("energyoptimize")
- **Tables**: 58 (49 public + 9 neon_auth)
- **Migrations**: 64 (init_neon through 064_migration_history_uuid_pk), all deployed to production

### Running Migrations

Migrations go through the **direct** endpoint (not pooled):

```bash
# Via Neon MCP tools (preferred)
# Use projectId: "cold-rice-23455092"

# Via psql
psql "postgresql://...@ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require" -f backend/migrations/NNN_name.sql
```

### Migration Conventions

1. Sequential numbering: `NNN_description.sql`
2. Always use `IF NOT EXISTS` for idempotency
3. UUID primary keys via `gen_random_uuid()` (never SERIAL)
4. `GRANT ... TO neondb_owner` for all new tables
5. Named indexes with `idx_*` prefix
6. Update `conftest.py` `mock_sqlalchemy_select` fixture when adding columns

---

## Code Conventions

### Backend (Python)

- **Framework**: FastAPI with Pydantic v2 models
- **Services**: Business logic in `backend/services/`, not in route handlers
- **Models**: Pydantic schemas in `backend/models/` — separate from DB tables
- **Region**: Always use `Region` enum from `backend/models/region.py` (50 states + DC + international). Never raw strings.
- **UUID PKs**: All primary keys are UUID type
- **Batch inserts**: Use `bulk_create()` (500-row chunks) for mass inserts
- **Formatting**: Black + isort (auto-formatted in CI on PRs)

### Frontend (TypeScript)

- **Framework**: Next.js 16 App Router + React 19
- **State**: Zustand (persistent) + TanStack React Query v5 (server state)
- **Auth**: Better Auth returns `{data, error}` — NEVER throw
- **Redirects**: Use `isSafeRedirect()` for same-origin validation
- **API client**: `lib/api/client.ts` — 401 handler returns never-resolving promise (prevents React Query retry cascades)
- **Styling**: Tailwind CSS with design system tokens in `globals.css`
- **npm**: `.npmrc` has `legacy-peer-deps=true`

### API Design

- Prefix: `/api/v1/`
- Auth: Session cookie for user endpoints, `X-API-Key` for internal
- Tier gating: `require_tier("pro")` / `require_tier("business")` dependency
- Internal endpoints: `/api/v1/internal/*` — excluded from 30s timeout

---

## Performance Best Practices

### Backend: Push Computation to SQL

When Python code fetches rows only to compute a scalar (sum, average, count), push that computation into SQL using CTEs or aggregate functions. This avoids transferring unnecessary rows over the wire and reduces Python memory usage.

```python
# Bad: fetch all rows, compute in Python
rows = await db.fetch_all(select(savings))
total = sum(r.amount for r in rows)

# Good: compute in SQL
result = await db.fetch_one(select(func.sum(savings.c.amount)))
total = result[0] or 0
```

### Frontend: `React.memo` Usage

Before wrapping a component in `React.memo`, audit whether it is **prop-driven** (pure function of props) or **store-driven** (reads from Zustand/context). `React.memo` only prevents re-renders when props change; it has no effect if the component subscribes to a store that changes frequently.

### Frontend: SSE Cache Updates

When applying real-time SSE price updates to TanStack React Query caches, use `setQueryData` with an updater function to partial-merge the new data. Do **not** call `invalidateQueries`, which triggers a full refetch and defeats the purpose of streaming updates.

```typescript
// Good: partial merge via updater
queryClient.setQueryData(['prices', region], (old) => ({
  ...old,
  current_rate: event.rate,
  updated_at: event.timestamp,
}));

// Bad: triggers full refetch, wastes the SSE data
queryClient.invalidateQueries({ queryKey: ['prices', region] });
```

---

## Adding a New Utility Type

Follow the pattern from ADR-005 (`docs/adr/005-multi-utility-expansion.md`):

1. **Database**: New migration with table + `GRANT TO neondb_owner`
2. **Backend service**: `backend/services/{utility}_service.py`
3. **API routes**: `backend/api/v1/{utility}.py`
4. **Frontend page**: `frontend/app/(app)/{utility}/page.tsx`
5. **Frontend components**: Dashboard, comparison, hooks, API client
6. **Sidebar nav**: Add entry in `Sidebar.tsx` (currently 15 items)
7. **SEO**: Add to `UTILITY_TYPES` in public rates page
8. **Tests**: ~39 tests per utility type (backend + frontend)
9. **Update `conftest.py`**: Add new model fields to `mock_sqlalchemy_select`

---

## CI/CD

### GitHub Actions (33 workflows)

Key workflows:
- `ci.yml` — Unified CI: lint, test (backend + frontend + ML), security scan, Docker build
- `e2e-tests.yml` — Playwright E2E + Lighthouse + load tests
- `deploy.yml` — Deploy to Render (migration gate before deploy)
- `deploy-worker.yml` — Deploy CF Worker
- `daily-data-pipeline.yml` — Consolidated daily pipeline (scrape-rates, scan-emails, learn, detect-rate-changes)
- `owasp-zap.yml` — Weekly OWASP ZAP baseline scan

> For the full cron job schedule and per-job troubleshooting, see `docs/runbooks/CRON_JOBS.md`.

### Self-Healing

- `retry-curl` composite action: Exponential backoff, 4xx fail-fast, 3 retries
- `notify-slack` composite action: Color-coded alerts to `#incidents`
- `self-healing-monitor.yml`: Auto-creates GitHub issues after 3+ workflow failures

### Deployment

- **Frontend**: Vercel (auto-deploy on push to main)
- **Backend**: Render (deploy workflow with migration gate)
- **Edge**: Cloudflare Workers (manual deploy via `deploy-worker.yml`)
- **Secrets**: 1Password vault "RateShift" → Render env vars

---

## Troubleshooting

### "ModuleNotFoundError" when running pytest
You're using system Python. Fix: `source .venv/bin/activate`

### Tests fail with 429 Too Many Requests
Rate limiter state leaking between tests. The `reset_rate_limiter` fixture (autouse) should handle this. If not, check `conftest.py`.

### Frontend build fails with peer dependency errors
Use `npm install --legacy-peer-deps` (configured in `.npmrc`).

### E2E tests timeout
1. Ensure backend is running
2. Use `domcontentloaded` not `networkidle` in Playwright (React Query apps)
3. Register Playwright route mocks in LIFO order (catch-all first, specific last)

### Database connection errors
- Use pooled endpoint for queries, direct endpoint for migrations
- Check `DATABASE_URL` env var points to Neon
- For local dev without DB, most backend tests use mocks

---

## Makefile Targets

The root `Makefile` provides common commands for development, testing, and deployment. Run `make help` for a self-documenting list of all targets.

### Development

| Target | Description |
|--------|-------------|
| `make setup` | First-time setup: copy `.env.example`, build images, start services |
| `make build` | Build all Docker images |
| `make build-prod` | Build production Docker images |
| `make up` | Start all services in development mode (frontend :3000, backend :8000, Grafana :3001) |
| `make up-prod` | Start production services |
| `make down` | Stop all services |
| `make down-prod` | Stop production services |
| `make restart` | Stop then start all services |
| `make install` | Install all dependencies locally (pip + npm for backend, frontend, ml) |
| `make logs` | View logs for all services |
| `make logs-backend` | View backend logs only |
| `make logs-frontend` | View frontend logs only |

### Testing

| Target | Description |
|--------|-------------|
| `make test` | Run all tests (backend + ML + frontend) |
| `make test-backend` | Run backend tests with coverage |
| `make test-ml` | Run ML tests with coverage |
| `make test-frontend` | Run frontend tests with coverage |
| `make test-e2e` | Run Playwright E2E tests |
| `make test-docker` | Run tests inside Docker containers |

### Code Quality

| Target | Description |
|--------|-------------|
| `make lint` | Run all linters (backend + frontend) |
| `make lint-backend` | Lint backend with ruff + mypy |
| `make lint-frontend` | Lint frontend with ESLint |
| `make format` | Format all code |
| `make format-backend` | Format backend with Black + isort |
| `make format-frontend` | Format frontend with Prettier |
| `make security-scan` | Run bandit (Python) + npm audit |

### Database

| Target | Description |
|--------|-------------|
| `make db-shell` | Open PostgreSQL shell |
| `make redis-shell` | Open Redis CLI |

### Deploy

| Target | Description |
|--------|-------------|
| `make deploy` | Deploy to development |
| `make deploy-staging` | Deploy to staging |
| `make deploy-prod` | Deploy to production (with warning) |

### Backup & Monitoring

| Target | Description |
|--------|-------------|
| `make backup` | Create database backup |
| `make backup-full` | Create full backup (all databases) |
| `make restore` | Restore from latest backup (destructive) |
| `make health` | Run health checks on all services |
| `make metrics` | Open Prometheus metrics UI |
| `make grafana` | Open Grafana dashboard |

### Cleanup

| Target | Description |
|--------|-------------|
| `make clean` | Remove all containers, volumes, and images (with confirmation) |
| `make clean-cache` | Clean Python and npm caches (`__pycache__`, `.pytest_cache`, `node_modules`, `.next`) |

### CI/CD

| Target | Description |
|--------|-------------|
| `make ci-test` | Run CI test suite (lint + test + security-scan) |
| `make ci-build` | Build and push production Docker images |

### Utilities

| Target | Description |
|--------|-------------|
| `make shell-backend` | Open shell in backend container |
| `make shell-frontend` | Open shell in frontend container |
| `make docs` | Open API documentation in browser |

---

## Key Documentation

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | Project instructions (architecture quick ref, critical reminders) |
| `docs/ARCHITECTURE.md` | System architecture overview |
| `docs/API_REFERENCE.md` | Full API endpoint documentation (~140 endpoints) |
| `docs/ENV_REFERENCE.md` | All environment variables (44 backend + 4 worker + 6 frontend) |
| `docs/DATABASE_SCHEMA.md` | Database tables (58) and migrations (64) |
| `docs/ML_PIPELINE.md` | ML pipeline architecture (ingestion → training → inference → learning) |
| `docs/CODEMAP_BACKEND.md` | Backend code structure |
| `docs/CODEMAP_FRONTEND.md` | Frontend code structure |
| `docs/CODEMAP_SERVICES.md` | Service layer overview (51 services by domain) |
| `docs/runbooks/CRON_JOBS.md` | Cron job runbook (4 CF Worker + 14 GHA schedules) |
| `docs/TESTING.md` | Test suite details and running instructions |
| `docs/OBSERVABILITY.md` | OpenTelemetry tracing architecture |
| `docs/AUTOMATION_PLAN.md` | CI/CD workflows and cron jobs |
| `docs/adr/` | Architecture Decision Records (9 ADRs) |
