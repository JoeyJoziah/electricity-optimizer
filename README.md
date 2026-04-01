# RateShift

Automatically shift consumers to lower utility rates across all 50 US states. Multi-utility price comparison (electricity, natural gas, propane, heating oil, water), AI-powered recommendations, smart alerts, and real-time price tracking.

[![CI Status](https://github.com/JoeyJoziah/electricity-optimizer/workflows/test/badge.svg)](https://github.com/JoeyJoziah/electricity-optimizer/actions)
[![Backend Tests](https://img.shields.io/badge/backend%20tests-2976%20passing-brightgreen)](docs/TESTING.md)
[![Frontend Tests](https://img.shields.io/badge/frontend%20tests-2015%20passing-brightgreen)](docs/TESTING.md)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## What is RateShift?

RateShift is a full-stack multi-utility optimization platform that helps US consumers save money on energy bills by automatically comparing rates, switching to lower-cost suppliers, and optimizing usage timing. The platform covers electricity, natural gas, propane, heating oil, and water -- combining nationwide price monitoring, AI-powered recommendations, community features, and machine learning predictions to deliver effortless savings.

## Key Features

- **Multi-utility dashboard** — Tabbed dashboard covering electricity, natural gas, propane, heating oil, and water rates across all 50 US states + DC
- **AI-powered assistant** — RateShift AI powered by Gemini 3 Flash + Groq Llama 3.3 70B + Composio tools for energy recommendations with SSE streaming
- **Smart alerts** — Configurable price threshold alerts with intelligent dedup, multiple channels (email, push), and rate change detection across utility types
- **5 connection types** — Direct login, email scan (OAuth), bill upload (OCR), portal scraping (5 utilities), and UtilityAPI sync for importing existing rates
- **Community features** — Community posts, voting, and reporting with AI moderation (Groq + Gemini) and XSS sanitization
- **SEO rate pages** — 153 ISR-generated pages at `/rates/[state]/[utility]` for organic discovery
- **ML predictions** — Ensemble predictor with HNSW vector search for demand forecasting and price optimization
- **CCA detection** — Community Choice Aggregation program detection and savings comparison
- **Savings estimates** — Real-time savings calculations with neighborhood comparisons
- **Stripe billing** — Free / Pro ($4.99/mo) / Business ($14.99/mo) tiers with dunning/retry and upgrade CTAs
- **Push notifications** — OneSignal integration for real-time customer engagement
- **Production-grade ML** — Adaptive learning, model versioning, A/B testing framework, and performance tracking

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS |
| **Backend** | FastAPI, Python 3.12, asyncpg + SQLAlchemy ORM |
| **Database** | Neon PostgreSQL (serverless), 64 migrations, 58 tables, UUID PKs |
| **Auth** | Neon Auth (Better Auth) — session-based, httpOnly cookies |
| **Edge Layer** | Cloudflare Worker — 2-tier caching, native rate limiting, bot detection, CORS |
| **ML** | Python ensemble predictor, HNSW vector store, XGBoost |
| **AI Agent** | Gemini 3 Flash + Groq Llama 3.3 70B + Composio tools |
| **Payments** | Stripe checkout, webhooks, subscription management, dunning |
| **Email** | Resend (primary, custom domain) + Gmail SMTP (fallback) |
| **Hosting** | Render (backend), Vercel (frontend), Cloudflare (edge/DNS) |
| **Notifications** | OneSignal (push), Email (Resend + SMTP) |
| **Observability** | OpenTelemetry + Grafana Cloud Tempo (distributed tracing) |
| **CI/CD** | GitHub Actions (33 workflows), self-healing automation |
| **Security** | OWASP ZAP, pip-audit, npm audit, Gitleaks, 1Password |

## Getting Started

### Prerequisites

- Python 3.12+ (`brew install python@3.12`)
- Node.js 18+
- Neon database URL (free tier available)

### Backend Setup

```bash
# Create and activate virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Set up environment variables (see .env.example)
cp .env.example .env
# Edit .env with your API keys (Stripe, Resend, NREL, etc.)

# Run migrations (apply SQL files in backend/migrations/ against your DATABASE_URL)
# Migrations are raw SQL, not Alembic. Apply sequentially via psql or your migration tool.

# Start development server
.venv/bin/python -m uvicorn backend.main:app --reload --port 8000
```

Backend API available at `http://localhost:8000`

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend available at `http://localhost:3000`

### Environment Variables

Key variables needed for local development:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `BETTER_AUTH_SECRET` | Better Auth signing key (32+ chars) |
| `BETTER_AUTH_URL` | Base URL for auth callbacks |
| `RESEND_API_KEY` | Resend email service (verification, password reset) |
| `EMAIL_FROM_ADDRESS` | Sender address (e.g., `noreply@rateshift.app`) |
| `STRIPE_SECRET_KEY` | Stripe API secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `INTERNAL_API_KEY` | Service-to-service auth for cron jobs |
| `GEMINI_API_KEY` | Google Gemini 3 Flash for AI agent |
| `GROQ_API_KEY` | Groq Llama 3.3 70B fallback |
| `COMPOSIO_API_KEY` | Composio tools integration (1K actions/month free) |
| `OPENWEATHERMAP_API_KEY` | Weather data for demand forecasting |

See `.env.example` and `backend/.env.example` for the complete list.

## Project Structure

```
electricity-optimizer/
  backend/                   FastAPI application (Python 3.12)
    api/v1/                  API route handlers (38 route files)
    models/                  Database and Pydantic models
    services/                Business logic (52 services)
    repositories/            Data access layer
    integrations/            External APIs (weather, market research, utility sync, ...)
    migrations/              SQL migrations (64 total, init_neon through 064)
    tests/                   Unit and integration tests (2,976 total)
  frontend/                  Next.js 16 application
    app/                     App Router structure
      (app)/                 Authenticated pages (15 sidebar nav items)
      (dev)/                 Dev-only pages (architecture editor)
    components/              React components (charts, forms, layouts, auth, ...)
    lib/                     Utilities, hooks, API clients, state
    __tests__/               Jest unit tests (2,015 total, 153 suites)
    e2e/                     Playwright E2E tests (1,605 total, 25 specs)
  ml/                        Machine learning pipelines
    models/                  Predictor definitions, HNSW indexing
    training/                Model training and evaluation
    inference/               Serving and prediction batching
  workers/                   Cloudflare Worker edge layer (API gateway, 90 tests)
  scripts/                   Deployment and utility scripts
  docs/                      Project documentation (ARCHITECTURE, DEVELOPER_GUIDE, 5 ADRs, ...)
  .github/workflows/         CI/CD automation (33 GitHub Actions workflows)
```

## Testing

### Backend (2,976 tests)

```bash
.venv/bin/python -m pytest backend/tests/ -v
```

Always use `.venv/bin/python` (system Python lacks required dependencies).

### Frontend (2,015 tests, 153 suites)

```bash
cd frontend
npm test                    # Watch mode
npm run test:ci            # Full coverage
```

### ML (676 tests)

```bash
.venv/bin/python -m pytest ml/tests/ -v
```

### E2E (1,605 tests, 25 specs, 5 browsers)

```bash
cd frontend
npx playwright test
npx playwright test --ui    # Interactive mode
```

### CF Worker (90 tests)

```bash
cd workers/api-gateway
npm test
```

**Total test count:** ~7,362 across all suites (2,976 backend + 2,015 frontend + 676 ML + 1,605 E2E + 90 CF Worker). See [docs/TESTING.md](docs/TESTING.md) for testing guides and coverage targets.

## API Documentation

When backend is running locally, interactive docs available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

(Disabled in production for security)

### Main API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/v1/prices/*` | GET/SSE | Real-time and historical prices, SSE streaming |
| `/api/v1/suppliers/*` | GET | Supplier details and registry |
| `/api/v1/recommendations/*` | GET | Switching recommendations |
| `/api/v1/connections/*` | GET/POST | Utility account connections (5 types) |
| `/api/v1/alerts/*` | GET/POST/DELETE | Price threshold alerts (multi-utility) |
| `/api/v1/agent/*` | GET/POST/SSE | AI assistant queries and streaming |
| `/api/v1/community/*` | GET/POST | Community posts, voting, reporting |
| `/api/v1/billing/*` | POST/GET | Stripe checkout, portal, webhooks |
| `/api/v1/rates/*` | GET | Propane, heating oil, water rates |
| `/api/v1/auth/*` | GET/POST | User profile, auth callbacks |
| `/api/v1/internal/*` | POST | Internal cron job endpoints (API-key protected) |

## Deployment

| Service | Platform | URL |
|---------|----------|-----|
| Backend | Render | `https://api.rateshift.app` |
| Frontend | Vercel | `https://rateshift.app` |
| Edge Layer | Cloudflare Workers | `https://api.rateshift.app/*` |
| Database | Neon | Serverless PostgreSQL |

Configuration:
- `render.yaml` — Render service definitions
- `vercel.json` — Vercel routing and environment
- `workers/` — Cloudflare Worker source code
- `deploy-worker.yml` — Worker deployment workflow

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed deployment instructions.

## CI/CD

33 GitHub Actions workflows including:

- **Test workflows** — Backend (pytest), Frontend (Jest, Playwright), ML (pytest), utility-type tests, CF Worker tests
- **Cron automation** — Price sync, alerts (30min), weather fetch (6h), market research (daily), dunning cycle (daily), KPI reports (daily), email scan (daily), portal scrape (weekly), gas/heating-oil/propane fetch, rate change detection
- **Deployment** — Production deploy with migration gate, staging deploy with rollback, CF Worker deploy
- **Self-healing** — Automated issue creation on repeated failures, CI auto-format, retry logic with exponential backoff
- **Security** — OWASP ZAP (weekly), pip-audit, npm audit, Gitleaks, code analysis
- **Observability** — Gateway health checks (6h), data health checks

See [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) for the full workflow inventory.

## Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, design decisions |
| [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Developer onboarding and workflow guide |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deployment guide (local, staging, production) |
| [INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) | Service catalog, CI/CD workflow inventory |
| [TESTING.md](docs/TESTING.md) | Test suites, coverage targets, running tests |
| [DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | All 58 tables, migration history |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | Complete API endpoint reference |
| [OBSERVABILITY.md](docs/OBSERVABILITY.md) | OpenTelemetry tracing, Grafana Cloud |
| [STRIPE_ARCHITECTURE.md](docs/STRIPE_ARCHITECTURE.md) | Payment flow, webhooks, dunning cycle |
| [REDEPLOYMENT_RUNBOOK.md](docs/REDEPLOYMENT_RUNBOOK.md) | Emergency redeployment procedures |
| [AUTOMATION_PLAN.md](docs/AUTOMATION_PLAN.md) | Cron workflow specifications and phase tracking |
| [ADRs](docs/adr/) | 5 Architecture Decision Records |

## License

MIT (see [LICENSE](LICENSE) file for details)
