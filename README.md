# Electricity Optimizer

AI-powered platform for electricity price monitoring, forecasting, and automated supplier switching. Built for Connecticut (US) residential and commercial customers, with USD as the default currency.

## Key Features

- **Real-time price monitoring** across Connecticut electricity suppliers via SSE streaming
- **ML-based price forecasting** using a CNN-LSTM model with XGBoost ensembles
- **Automated load shifting optimization** via mixed-integer linear programming (MILP)
- **Intelligent supplier switching** recommendations based on predicted savings
- **Stripe monetization** with Free / $4.99 Pro / $14.99 Business tiers
- **GDPR-compliant data management** with full audit trails
- **Interactive dashboards** for visualizing consumption, costs, and forecasts
- **Gamification** with savings tracking and achievement badges

## Tech Stack

| Layer          | Technologies                                                  |
|----------------|---------------------------------------------------------------|
| Backend        | FastAPI, Python 3.12 (3.11 in CI), Redis                      |
| Frontend       | Next.js 14, React 18, TypeScript, Tailwind CSS, Recharts      |
| Database       | Neon PostgreSQL (serverless)                                   |
| ML / Data      | TensorFlow, XGBoost, PuLP, scikit-learn                       |
| Auth           | Neon Auth (Better Auth) — session-based, httpOnly cookies      |
| Payments       | Stripe (checkout, webhooks, customer portal)                   |
| Infrastructure | Docker, Prometheus, Grafana                                    |
| CI/CD          | GitHub Actions (Python 3.11, Node 20)                          |

## Quick Start (Local Development)

### Prerequisites

- Python 3.12+ (Homebrew recommended: `brew install python@3.12`)
- Node.js 18+
- Docker and Docker Compose (for full stack)
- A Neon database URL

### Option 1: Docker Compose (full stack)

```bash
# Copy environment template and fill in values
cp .env.example .env

# Start all services (backend, frontend, redis, prometheus, grafana)
make up
# Or: docker compose up -d
```

Services will be available at:

| Service   | URL                        |
|-----------|----------------------------|
| Frontend  | http://localhost:3000       |
| Backend   | http://localhost:8000       |
| Grafana   | http://localhost:3001       |
| Prometheus| http://localhost:9090       |

### Option 2: Manual Setup

**Backend:**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn main:app --reload
```

The API server starts at `http://localhost:8000`. All database and API fields are optional for local dev -- endpoints return simulated data when external services are unavailable.

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

The development server starts at `http://localhost:3000`.

## Testing

### Backend (694 tests)

```bash
source .venv/bin/activate
cd backend
pytest tests/ -v
```

> **Important:** Always use the project venv at `.venv/`. System Python is missing required dependencies (fastapi, httpx, pydantic, pytest-asyncio).

### Frontend (346 tests, 17 suites)

```bash
cd frontend
npm test
npm run test:ci  # With coverage
```

> **Note:** The SwitchWizard test suite is occasionally flaky.

### E2E Tests

```bash
cd frontend
npx playwright test
npx playwright test --ui  # Interactive mode
```

### Additional Test Suites

The repository includes load, performance, and security tests under `tests/`. See [docs/TESTING.md](docs/TESTING.md) for the full testing guide.

## Deployment

| Service  | Platform |
|----------|----------|
| Backend  | Render   |
| Frontend | Vercel   |
| Database | Neon     |

Configuration files:

- `render.yaml` -- Render service definitions (backend + frontend)
- `frontend/vercel.json` -- Vercel project settings
- `docker-compose.prod.yml` -- Production Docker Compose
- `scripts/deploy.sh` / `scripts/production-deploy.sh` -- Deployment scripts

Refer to [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed instructions.

### Environment Variables

Copy `.env.example` to `.env` and configure. Key variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `REDIS_URL` | Redis for caching and session storage |
| `BETTER_AUTH_SECRET` | Better Auth signing key |
| `BETTER_AUTH_URL` | Better Auth base URL |
| `INTERNAL_API_KEY` | Service-to-service auth (price-sync workflow) |
| `STRIPE_SECRET_KEY` | Stripe payments integration |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook verification |
| `NREL_API_KEY` | NREL utility rate data (US) |
| `EIA_API_KEY` | EIA energy data (gas, oil, propane) |
| `OPENWEATHERMAP_API_KEY` | Weather data for demand forecasting |

See `.env.example` and `backend/.env.example` for the complete list.

## API Documentation

When the backend is running locally, interactive API docs are available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

> **Note:** Swagger UI and ReDoc are disabled in production for security.

### API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/v1/prices/*` | GET/SSE | Price data, history, streaming updates |
| `/api/v1/suppliers/*` | GET | Supplier listings and details |
| `/api/v1/recommendations/*` | GET | Switching recommendations |
| `/api/v1/auth/*` | GET/POST | User profile, password strength check |
| `/api/v1/regulations/*` | GET | State deregulation and PUC data |
| `/api/v1/internal/*` | POST | Observation loop, learning (API-key protected) |
| `/api/v1/billing/*` | POST/GET | Stripe checkout, portal, subscriptions, webhooks |
| `/api/v1/compliance/*` | GET/POST/DELETE | GDPR data export, consent, deletion |
| `/api/v1/user/*` | GET/PATCH | User profile management |
| `/api/v1/beta/*` | POST | Beta signup |

## Project Structure

```
electricity-optimizer/
  backend/              Backend API (FastAPI + Python 3.12)
    api/v1/             API route handlers (auth, billing, prices, suppliers, ...)
    models/             Database and Pydantic models
    services/           Business logic (stripe, alerts, vector_store, analytics, ...)
    repositories/       Data access layer
    integrations/       External APIs (pricing_apis, smart_meters, weather_service)
    migrations/         Database migrations (Alembic)
    tests/              Backend unit and integration tests
  frontend/             Frontend application (Next.js 14 + TypeScript)
    app/                Next.js App Router
      (app)/            Authenticated pages (dashboard, prices, suppliers, optimize, settings)
      api/              API routes
      pricing/          Pricing page (marketing)
      privacy/          Privacy policy
      terms/            Terms of service
    components/         React components (charts, layout, auth, gamification, ...)
    lib/                Utilities, hooks, API clients, state store
    __tests__/          Frontend unit tests (Jest)
    e2e/                End-to-end tests (Playwright)
  ml/                   Machine learning pipelines
    models/             Model definitions (CNN-LSTM, XGBoost)
    training/           Training scripts and configs
    inference/          Inference and serving
    optimization/       MILP load shifting optimizer
    evaluation/         Model evaluation utilities
  monitoring/           Prometheus and Grafana configuration
  infrastructure/       Kubernetes manifests and monitoring configs
  scripts/              Deployment, backup, and utility scripts
  tests/                Load, performance, and security tests
  docs/                 Project documentation
```

## Database

Production database is **Neon PostgreSQL** with 14 tables. All primary keys use UUID type.

| Table | Purpose |
|-------|---------|
| `users` | User accounts and profiles |
| `electricity_prices` | Historical price records |
| `suppliers` | CT electricity suppliers (Eversource, United Illuminating, NextEra) |
| `tariffs` | Supplier tariff plans |
| `consent_records` | GDPR consent tracking |
| `deletion_logs` | GDPR deletion audit trail |
| `beta_signups` | Beta waitlist |
| `auth_sessions` | Active user sessions |
| `login_attempts` | Auth attempt tracking (rate limiting) |
| `activity_logs` | User activity audit trail |
| `forecast_observations` | Forecast vs actual price tracking (adaptive learning) |
| `recommendation_outcomes` | Recommendation success tracking |
| `supplier_registry` | Multi-state supplier catalog with utility types |
| `state_regulations` | Deregulation status and PUC info for all 50 states + DC |

## Key Services

| Service | File | Purpose |
|---------|------|---------|
| Stripe | `backend/services/stripe_service.py` | Checkout, portal, webhooks, subscription management |
| Alerts | `backend/services/alert_service.py` | Price threshold alerts with email notifications |
| HNSW Vector Store | `backend/services/hnsw_vector_store.py` | HNSW-indexed price pattern matching (singleton) |
| Observations | `backend/services/observation_service.py` | Forecast vs actual tracking, accuracy metrics |
| Learning | `backend/services/learning_service.py` | Nightly accuracy, bias detection, weight tuning |
| Weather | `backend/integrations/weather_service.py` | OpenWeatherMap integration for demand forecasting |
| Email | `backend/services/email_service.py` | SendGrid primary, SMTP fallback |
| Analytics | `backend/services/analytics_service.py` | Usage and savings analytics (with Redis caching) |
| SSE Streaming | `backend/api/v1/prices.py` | Real-time price update streaming (auth required) |
| Realtime Hook | `frontend/lib/hooks/useRealtime.ts` | SSE client-side consumption |
| Neon Auth | `backend/auth/neon_auth.py` | Session validation via neon_auth schema |

## CI/CD

GitHub Actions workflows:

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `test.yml` | PR, push to main/develop | Backend, ML, frontend tests + security scan |
| `price-sync.yml` | Scheduled (every 6h) | Automated price data refresh |
| `observe-forecasts.yml` | Scheduled (30min after price-sync) | Backfill actuals into forecast observations |
| `nightly-learning.yml` | Scheduled (4 AM UTC) | Adaptive learning: accuracy, bias, weight tuning |
| `deploy-production.yml` | Manual/tag | Production deployment |
| `deploy-staging.yml` | Push to develop | Staging deployment |
| `e2e-tests.yml` | Scheduled (daily) | Playwright E2E + Lighthouse audits |
| `model-retrain.yml` | Scheduled | ML model retraining pipeline |
| `keepalive.yml` | Scheduled | Render free-tier keep-alive pings |

CI runs with **Python 3.11** and **Node 20** on `ubuntu-latest`.

## Documentation

| Document | Description |
|----------|-------------|
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deployment guide (local, staging, production) |
| [INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) | Architecture, service catalog, monitoring |
| [TESTING.md](docs/TESTING.md) | Test suites, coverage targets, CI integration |
| [STRIPE_ARCHITECTURE.md](docs/STRIPE_ARCHITECTURE.md) | Stripe payment flow and webhook handling |
| [CODEMAP_BACKEND.md](docs/CODEMAP_BACKEND.md) | Backend architecture and integration map |
| [CODEMAP_FRONTEND.md](docs/CODEMAP_FRONTEND.md) | Frontend component and hook map |
| [MVP_LAUNCH_CHECKLIST.md](docs/MVP_LAUNCH_CHECKLIST.md) | Pre-launch validation checklist |
| [BETA_DEPLOYMENT_GUIDE.md](docs/BETA_DEPLOYMENT_GUIDE.md) | Beta deployment and user onboarding |
| [LOKI_INTEGRATION.md](docs/LOKI_INTEGRATION.md) | Loki Mode orchestration architecture |

## License

MIT (see LICENSE file for details)
