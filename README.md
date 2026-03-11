# RateShift

Automatically shift consumers to lower electricity rates across all 50 US states. Effortless cost reduction with AI-powered recommendations, smart alerts, and real-time price tracking.

[![CI Status](https://github.com/JoeyJoziah/electricity-optimizer/workflows/test/badge.svg)](https://github.com/JoeyJoziah/electricity-optimizer/actions)
[![Backend Tests](https://img.shields.io/badge/backend%20tests-1917%20passing-brightgreen)](docs/TESTING.md)
[![Frontend Tests](https://img.shields.io/badge/frontend%20tests-1475%20passing-brightgreen)](docs/TESTING.md)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## What is RateShift?

RateShift is a full-stack energy optimization platform that helps US consumers save money on electricity bills by automatically switching to lower-cost suppliers and times. The platform combines nationwide price monitoring, AI-powered recommendations, and machine learning predictions to deliver effortless savings.

## Key Features

- **Nationwide coverage** — All 50 US states + DC with real-time rate comparison and optimization
- **AI-powered assistant** — RateShift AI powered by Gemini 3 Flash + Groq for energy recommendations
- **Smart alerts** — Configurable price threshold alerts with intelligent dedup and multiple channels (email, push)
- **Utility connections** — Direct login, email OAuth, and bill OCR to sync existing rates
- **ML predictions** — Ensemble predictor with HNSW vector search for demand forecasting and price optimization
- **Notification tracking** — Delivery outcome monitoring and error handling per notification
- **A/B testing framework** — Deterministic model variant assignment for A/B experimentation
- **Stripe billing** — Free / Pro ($4.99/mo) / Business ($14.99/mo) tiers with dunning/retry
- **Push notifications** — OneSignal integration for real-time customer engagement
- **Production-grade ML** — Adaptive learning, model versioning, and performance tracking

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS |
| **Backend** | FastAPI, Python 3.12, asyncpg + SQLAlchemy ORM |
| **Database** | Neon PostgreSQL (serverless), 34 migrations, UUID PKs |
| **Auth** | Neon Auth (Better Auth) — session-based, httpOnly cookies |
| **Edge Layer** | Cloudflare Worker — caching, rate limiting, bot detection, CORS |
| **ML** | Python ensemble predictor, HNSW vector store, XGBoost |
| **Payments** | Stripe checkout, webhooks, subscription management |
| **Email** | Resend (primary) + Gmail SMTP (fallback) |
| **Hosting** | Render (backend), Vercel (frontend), Cloudflare (edge/DNS) |
| **Notifications** | OneSignal (push), Email (Resend + SMTP) |
| **CI/CD** | GitHub Actions (24 workflows), self-healing automation |
| **Secrets** | 1Password SecretsManager integration |

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

# Run migrations (local SQLite, or connect to Neon)
cd backend
alembic upgrade head

# Start development server
uvicorn main:app --reload
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
    api/v1/                  API route handlers (auth, billing, prices, agent, alerts, ...)
    models/                  Database and Pydantic models
    services/                Business logic (stripe, alerts, agent, ml, notifications, ...)
    repositories/            Data access layer
    integrations/            External APIs (weather, market research, utility sync, ...)
    migrations/              Alembic database migrations (34 total)
    tests/                   Unit and integration tests (1,917 total)
  frontend/                  Next.js 16 application
    app/                     App Router structure
      (app)/                 Authenticated pages (dashboard, alerts, connections, optimize, settings, assistant)
      (dev)/                 Dev-only pages (architecture editor)
    components/              React components (charts, forms, layouts, auth, ...)
    lib/                     Utilities, hooks, API clients, state
    __tests__/               Jest unit tests (1,475 total)
    e2e/                     Playwright E2E tests (634 total)
  ml/                        Machine learning pipelines
    models/                  Predictor definitions, HNSW indexing
    training/                Model training and evaluation
    inference/               Serving and prediction batching
  workers/                   Cloudflare Worker edge layer (API gateway)
  scripts/                   Deployment and utility scripts
  docs/                      Project documentation
  .github/workflows/         CI/CD automation (24 GitHub Actions workflows)
```

## Testing

### Backend (1,917 tests)

```bash
source .venv/bin/activate
cd backend
.venv/bin/python -m pytest tests/ -v
```

Always use the project venv (system Python lacks required dependencies).

### Frontend (1,475 tests, 99 suites)

```bash
cd frontend
npm test                    # Watch mode
npm run test:ci            # Full coverage
```

### ML (611 tests)

```bash
source .venv/bin/activate
cd ml
.venv/bin/python -m pytest tests/ -v
```

### E2E (634 tests)

```bash
cd frontend
npx playwright test
npx playwright test --ui    # Interactive mode
```

**Total test count:** ~4,600+ across all suites. See [docs/TESTING.md](docs/TESTING.md) for testing guides and coverage targets.

## API Documentation

When backend is running locally, interactive docs available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

(Disabled in production for security)

### Main API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/v1/prices/*` | GET/SSE | Real-time and historical prices |
| `/api/v1/suppliers/*` | GET | Supplier details and registry |
| `/api/v1/recommendations/*` | GET | Switching recommendations |
| `/api/v1/connections/*` | GET/POST | Utility account connections |
| `/api/v1/alerts/*` | GET/POST/DELETE | Price threshold alerts |
| `/api/v1/agent/*` | GET/POST/SSE | AI assistant queries and streaming |
| `/api/v1/billing/*` | POST/GET | Stripe checkout, portal, webhooks |
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

24 GitHub Actions workflows including:

- **Test workflows** — Backend (pytest), Frontend (Jest, Playwright), ML (pytest)
- **Cron automation** — Price sync (30min), alerts (30min), weather fetch (6h), market research (daily), dunning cycle (daily), KPI reports (daily)
- **Deployment** — Production deploy with migration gate, staging deploy with rollback
- **Self-healing** — Automated issue creation on repeated failures, CI auto-format, retry logic with exponential backoff
- **Security** — Secret scanning (Gitleaks), code analysis, container scanning (Trivy)

See [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) for the full workflow inventory.

## Documentation

| Document | Purpose |
|----------|---------|
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deployment guide (local, staging, production) |
| [INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) | Architecture overview, service catalog, CI/CD |
| [TESTING.md](docs/TESTING.md) | Test suites, coverage targets, running tests |
| [STRIPE_ARCHITECTURE.md](docs/STRIPE_ARCHITECTURE.md) | Payment flow, webhooks, dunning cycle |
| [REDEPLOYMENT_RUNBOOK.md](docs/REDEPLOYMENT_RUNBOOK.md) | Emergency redeployment procedures |
| [AUTOMATION_PLAN.md](docs/AUTOMATION_PLAN.md) | Cron workflow specifications and phase tracking |

## License

MIT (see [LICENSE](LICENSE) file for details)
