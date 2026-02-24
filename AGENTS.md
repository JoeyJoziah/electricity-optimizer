# AGENTS.md -- Electricity Optimizer

> Canonical reference for AI coding tools working in this codebase.
> Cross-tool standard: works with Claude Code, Cursor, Copilot, Cody, Windsurf, and others.

## Project Overview

Electricity Optimizer is a Connecticut-focused energy price comparison and optimization platform. Users compare electricity (and other utility) prices across suppliers, receive ML-powered switching recommendations, and track savings over time. The platform supports all 50 US states + DC + select international regions, with Connecticut as the primary market.

**Repository**: `electricity-optimizer`
**Primary market**: Connecticut (Eversource Energy, United Illuminating, NextEra Energy)
**Billing tiers**: Free / $4.99 Pro / $14.99 Business (Stripe)

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend API | FastAPI + Python | 3.12 |
| Frontend | Next.js (App Router) + TypeScript | 14 |
| Database | Neon PostgreSQL (serverless) | -- |
| Auth | Neon Auth (Better Auth) | session-based |
| Payments | Stripe | async SDK |
| ML | Ensemble predictor + HNSW vector search | hnswlib 0.8+ |
| Cache | Redis (Upstash) | -- |
| Hosting | Render | -- |
| CI | GitHub Actions | 18 workflows |

## Build, Test, and Run Commands

### Backend

```bash
# CRITICAL: Always use the project venv, never system Python
.venv/bin/python -m pytest backend/tests/              # all backend tests (687+)
.venv/bin/python -m pytest backend/tests/test_auth.py  # single file
.venv/bin/python -m pytest backend/tests/ -x           # stop on first failure
.venv/bin/python -m pytest backend/tests/ -k "test_name"  # by name

# ML tests
.venv/bin/python -m pytest ml/tests/                   # ML suite (105+)

# Run dev server
.venv/bin/python -m uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm test                    # Jest unit tests (346+, 17 suites)
npm run build               # production build
npm run dev                 # dev server (port 3000)
npx playwright test         # E2E tests (11 specs)
npx playwright test --ui    # E2E with interactive UI
```

### Full Suite

```bash
# Backend + ML
.venv/bin/python -m pytest backend/tests/ ml/tests/

# Frontend
cd frontend && npm test -- --watchAll=false

# E2E (requires frontend dev server running)
cd frontend && npx playwright test
```

## Architecture

### Directory Structure

```
electricity-optimizer/
  backend/
    api/v1/              # FastAPI route handlers
      auth.py            # GET /me, POST /password/check-strength
      billing.py         # Stripe checkout, portal, webhooks
      internal.py        # API-key-protected ML endpoints
      prices.py          # Price queries + SSE streaming
      recommendations.py # ML-powered recommendations
      regulations.py     # State regulation data
      suppliers.py       # Supplier CRUD
      user.py            # User profile management
    auth/
      neon_auth.py       # Session validation (queries neon_auth schema)
    config/
      database.py        # AsyncPG connection manager
      secrets.py         # 1Password integration
      settings.py        # Pydantic Settings (env-driven)
    integrations/
      pricing_apis/
        base.py          # PriceData, PriceForecast, RetryConfig, CircuitBreaker
        eia.py           # EIA API (gas, oil, propane prices)
        flatpeak.py      # FlatPeak API (electricity)
        iea.py           # IEA API (international)
        nrel.py          # NREL API (all 50 states + DC)
        cache.py         # InMemoryCache with TTL
        rate_limiter.py  # Token bucket + sliding window
        service.py       # Unified pricing service
      weather_service.py # OpenWeatherMap
    middleware/
      rate_limiter.py    # Per-IP rate limiting (in-memory or Redis)
      security_headers.py
    migrations/          # Raw SQL migrations (run against app DB, NOT Neon MCP)
    models/
      price.py           # Price (Pydantic BaseModel, used as SQLAlchemy-ish)
      user.py            # User model
      supplier.py        # Supplier + Tariff models
      region.py          # Region enum (all 50 states + DC + international)
      utility.py         # UtilityType + PriceUnit enums
      consent.py         # GDPR consent model
    repositories/
      base.py            # Base repository (asyncpg)
      price_repository.py
      user_repository.py
      supplier_repository.py
    services/
      alert_service.py         # Price threshold alerts
      analytics_service.py     # Cached analytics queries
      hnsw_vector_store.py     # HNSW-indexed vector search (hnswlib)
      learning_service.py      # Nightly model weight tuning
      observation_service.py   # Forecast tracking + outcome recording
      price_service.py         # Price aggregation + business logic
      recommendation_service.py # ML switching + usage recommendations
      stripe_service.py        # Async Stripe operations
      vector_store.py          # SQLite-backed base vector store
    tests/
      conftest.py        # CRITICAL: mock_sqlalchemy_select fixture (see below)
      test_*.py          # 24 test files, 687+ tests
  frontend/
    app/
      layout.tsx         # Root layout (marketing pages, no sidebar)
      page.tsx           # Landing page
      (app)/
        layout.tsx       # Authenticated layout (sidebar)
        dashboard/       # /dashboard
        prices/          # /prices
        suppliers/       # /suppliers
        optimize/        # /optimize
        settings/        # /settings
        auth/            # /auth/* (sign-in, sign-up)
      api/auth/[...all]/ # Better Auth API route handler
      pricing/           # /pricing (marketing)
      privacy/           # /privacy
      terms/             # /terms
    components/
    lib/
      auth/
        server.ts        # betterAuth server config
        client.ts        # createAuthClient (better-auth/react)
      hooks/
        useRealtime.ts   # SSE client hook
      utils/
        format.ts        # Currency formatting (Intl.NumberFormat, en-US)
    e2e/
      helpers/auth.ts    # mockBetterAuth(), setAuthenticatedState()
      *.spec.ts          # 11 Playwright specs
    middleware.ts         # Route protection (checks session cookie)
  ml/
    models/              # ML model definitions
    training/            # Training pipelines
    inference/           # Prediction logic
    evaluation/          # Model evaluation
    tests/               # 105+ tests
  docs/                  # DEPLOYMENT, TESTING, CODEMAP_BACKEND, etc.
  scripts/               # Utility scripts (Notion sync, setup)
  .github/workflows/     # 18 CI/CD workflows
```

### Request Flow

```
Client --> Next.js middleware (route protection)
  --> Next.js App Router (frontend pages)
  --> /api/auth/* (Better Auth handles sign-in/sign-up/sign-out)

Client --> FastAPI (backend API)
  --> RateLimitMiddleware --> SecurityHeadersMiddleware
  --> Router --> Dependency Injection (get_current_user, verify_api_key)
  --> Service Layer --> Repository Layer --> Neon PostgreSQL
                    --> External APIs (EIA, NREL, FlatPeak, IEA)
                    --> Redis (cache, ensemble weights)
                    --> ML Pipeline (ensemble predictor, vector search)
```

### Authentication Flow

The app uses **Neon Auth** (built on Better Auth), NOT JWT for user auth.

- **Frontend**: `better-auth` package handles sign-in/sign-up/sign-out via API routes
- **Session cookie**: `better-auth.session_token` (httpOnly, set by Better Auth)
- **Backend validation**: `backend/auth/neon_auth.py` queries `neon_auth.session` + `neon_auth.user` tables
- **Dependencies**: `get_current_user` (required auth), `get_current_user_optional` (optional auth)
- **JWT is only used for**: internal API key validation (`verify_api_key`), not user auth
- **Returns 503** if DB is unavailable (session validation requires DB, unlike offline JWT)

### ML Pipeline

- **Ensemble predictor**: multiple model weights, dynamically tuned nightly
- **HNSW vector store**: wraps SQLite-backed VectorStore with hnswlib for O(log n) ANN search; falls back to brute-force
- **Observation loop**: forecasts recorded at inference time, actuals backfilled 30min after price sync
- **Nightly learning**: runs at 4AM UTC via GitHub Actions; inverse-MAPE weight tuning + bias correction
- **Dynamic weights**: stored in Redis key `model:ensemble_weights`, fallback to `metadata.yaml`

## Domain Context

### Utility Types

Five supported utility types, defined in `backend/models/utility.py`:

| Type | Default Unit | Notes |
|------|-------------|-------|
| `electricity` | $/kWh | Primary focus |
| `natural_gas` | $/therm | EIA API |
| `heating_oil` | $/gallon | EIA API |
| `propane` | $/gallon | EIA API |
| `community_solar` | $/kWh credit | Credits model |

### Regions

The `Region` enum in `backend/models/region.py` is the **single source of truth**. Never use raw strings for regions.

- All 50 US states + DC: `US_CT`, `US_NY`, `US_CA`, etc. (format: `us_xx`)
- International: `UK`, `DE`, `FR`, `ES`, `JP`, `AU`
- Backward-compat aliases: `PricingRegion` and `PriceRegion` both resolve to `Region`

### Suppliers

Supplier data is **DB-backed** via the `supplier_registry` table (migration 006). Do not use hardcoded mock data. CT suppliers seeded: Eversource Energy, United Illuminating, NextEra Energy.

### State Regulations

The `state_regulations` table contains deregulation status and PUC info for all 50 states + DC. Exposed via `/api/v1/regulations`.

## Key Constraints and Gotchas

### Database Endpoint Quirk (CRITICAL)

The app uses endpoint `ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech` (us-east-1). The Neon MCP/console shows a DIFFERENT endpoint (`ep-lingering-forest-aebmj5t0`, us-east-2). Both connect to the same Neon project, but **migrations run via Neon MCP tools do not reach the app database**. Always run migrations via asyncpg against the app's `DATABASE_URL`.

### conftest.py mock_sqlalchemy_select (CRITICAL)

The `mock_sqlalchemy_select` autouse fixture in `backend/tests/conftest.py` patches Pydantic model class attributes so they work in SQLAlchemy-style expressions. **When you add a new column to Price, User, Supplier, or Tariff models, you MUST add the field name to the `model_attrs` dict in this fixture.** Failure to do so will cause obscure test failures.

The fixture also uses `type.__setattr__` for restoring Pydantic FieldInfo descriptors -- do not simplify this to plain `setattr`.

Current patched fields:

```python
model_attrs = {
    "models.price": {
        "Price": ["id", "region", "supplier", "price_per_kwh", "timestamp", "currency", "is_peak", "utility_type"],
    },
    "models.user": {
        "User": ["id", "email", "name", "region", "created_at", "is_active"],
    },
    "models.supplier": {
        "Supplier": ["id", "name", "regions", "is_active", "average_renewable_percentage"],
        "Tariff": ["id", "name", "supplier_id", "is_available"],
    },
}
```

### UUID Primary Keys

All database tables use UUID primary keys. GRANTs use the `neondb_owner` role. Never assume integer auto-increment IDs.

### Python Environment

Always use `.venv/bin/python` for pytest and any Python commands. The system Python (3.9.6) is missing venv dependencies and will fail. The venv was created with Python 3.12.12 via Homebrew.

### neon_auth Column Naming

The `neon_auth` schema tables use **camelCase** column names (`"userId"`, `"expiresAt"`, `"emailVerified"`). These require quoted identifiers in raw SQL queries.

### Rate Limiter State

The `RateLimitMiddleware` uses an in-memory dict when Redis is unavailable. The `reset_rate_limiter` autouse fixture in conftest.py clears this between tests. Without it, request counts accumulate and unrelated tests fail with 429.

### Security

- Swagger/ReDoc are disabled in production (`docs_url=None if settings.is_production`)
- `POST /prices/refresh` and `/api/v1/internal/*` require `X-API-Key` header
- `/metrics` requires API key (header or query param)
- Request body size limited to 1 MB (middleware)
- Request timeout: 30s for non-SSE endpoints
- CSP + HSTS headers on frontend via `next.config.js`
- `X-Process-Time` header only sent in non-production

## Code Style

### Python (Backend + ML)

- **Standard**: PEP 8
- **Type hints**: Required on all function signatures
- **Models**: Pydantic BaseModel (v2) for request/response schemas
- **Async**: All database and HTTP operations are async (`async def`, `await`)
- **Imports**: stdlib, third-party, then local (isort-compatible)
- **Docstrings**: Triple-quoted, on all public functions and classes
- **Error handling**: Raise `HTTPException` in route handlers; use structured logging (`structlog`) everywhere else
- **Settings**: Environment-driven via Pydantic Settings (`config/settings.py`); use `get_settings()` for dependency injection

### TypeScript (Frontend)

- **Standard**: Strict mode enabled in `tsconfig.json`
- **Framework**: Next.js 14 App Router (server components by default, `"use client"` where needed)
- **Styling**: Tailwind CSS + `postcss`
- **Currency formatting**: `Intl.NumberFormat` with `en-US` locale (see `lib/utils/format.ts`)
- **Auth client**: `better-auth/react` (NOT `@neondatabase/auth`)
- **Testing**: Jest for unit tests, Playwright for E2E
- **E2E auth mocking**: Use helpers in `frontend/e2e/helpers/auth.ts`

### SQL (Migrations)

- Raw SQL files in `backend/migrations/`
- Sequential numbering: `001_`, `002_`, etc.
- Always include `IF NOT EXISTS` / `IF EXISTS` guards
- UUID PKs, `neondb_owner` role for GRANTs
- Run against the app's `DATABASE_URL`, never via Neon MCP

## Environment Variables

Key variables (see `.env.example` and `backend/.env.example` for full list):

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Neon PostgreSQL connection string (must use `ep-withered-morning` endpoint) |
| `INTERNAL_API_KEY` | Protects internal ML endpoints and `/metrics` |
| `STRIPE_SECRET_KEY` | Stripe server-side key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature verification |
| `NREL_API_KEY` | NREL utility rates API |
| `EIA_API_KEY` | EIA energy data API |
| `FLATPEAK_API_KEY` | FlatPeak electricity pricing API |
| `OPENWEATHERMAP_API_KEY` | Weather data for predictions |
| `REDIS_URL` | Upstash Redis (cache + ensemble weights) |
| `BETTER_AUTH_SECRET` | Better Auth session signing |
| `BETTER_AUTH_URL` | Frontend auth URL |

## GitHub Actions Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `backend-ci.yml` | Push/PR | Backend tests + lint |
| `frontend-ci.yml` | Push/PR | Frontend tests + build |
| `e2e-tests.yml` | Push/PR | Playwright E2E suite |
| `price-sync.yml` | Schedule | Fetch latest prices from APIs |
| `observe-forecasts.yml` | After price-sync | Backfill actuals for forecast observations |
| `nightly-learning.yml` | 4AM UTC daily | ML weight tuning + bias correction |
| `deploy-production.yml` | Push to main | Deploy to Render |
| `deploy-staging.yml` | Push to staging | Deploy staging |
| `model-retrain.yml` | Manual/schedule | Full model retraining |

## Common Tasks

### Adding a new API endpoint

1. Create route handler in `backend/api/v1/your_endpoint.py`
2. Register the router in `backend/main.py`
3. Add service logic in `backend/services/`
4. Add repository methods if DB access needed in `backend/repositories/`
5. Write tests in `backend/tests/test_your_endpoint.py`
6. If the endpoint needs auth: use `get_current_user` dependency
7. If internal-only: use `verify_api_key` dependency

### Adding a new database column

1. Add field to the Pydantic model in `backend/models/`
2. Write a migration SQL file in `backend/migrations/`
3. Run migration against the app's `DATABASE_URL` (not Neon MCP)
4. **Update `mock_sqlalchemy_select` in `backend/tests/conftest.py`** -- add the new field name to the model's attr list
5. Update affected repository queries
6. Write/update tests

### Adding a new pricing API integration

1. Create client class in `backend/integrations/pricing_apis/` extending the base
2. Implement `get_current_price()` and `get_price_forecast()` methods
3. Use `RetryConfig` and `CircuitBreakerConfig` from `base.py`
4. Register in `backend/integrations/pricing_apis/service.py`
5. Map regions in the new client (see `nrel.py` for all-states example)
6. Write tests with mock HTTP responses (see `conftest.py` fixtures)

### Adding a new frontend page

1. Create page in `frontend/app/(app)/your-page/page.tsx` (authenticated) or `frontend/app/your-page/page.tsx` (public)
2. Authenticated pages get the sidebar layout automatically via `(app)/layout.tsx`
3. Add route protection in `frontend/middleware.ts` if needed
4. Write Jest tests in `frontend/__tests__/`
5. Write Playwright E2E spec in `frontend/e2e/` if user-facing flow
