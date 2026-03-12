# Tech Stack

## Languages

| Language | Version | Usage |
|----------|---------|-------|
| Python | 3.12 | Backend API, ML pipeline, data processing |
| TypeScript | 5.x | Frontend application, API client |
| SQL | PostgreSQL 15+ | Database migrations, queries |
| Shell/Bash | POSIX + Bash 5 | CI/CD workflows, automation scripts |

## Frontend

- **Framework:** Next.js 16 (App Router, server components)
- **UI:** React 19, Tailwind CSS, custom design system
- **State:** TanStack Query (server state), Zustand (client state)
- **Testing:** Jest (1,835 tests, 136 suites), Playwright (E2E), jest-axe (a11y)
- **Auth:** Better Auth (session-based, httpOnly cookies)

## Backend

- **Framework:** FastAPI (Python 3.12, async)
- **ORM:** SQLAlchemy 2.0 (async) + asyncpg
- **Testing:** pytest (2,478 tests), 80% coverage threshold
- **Auth:** Neon Auth (Better Auth), session-based
- **Formatting:** Black (line-length 100) + isort
- **Linting:** Ruff (pycodestyle, pyflakes, bugbear, comprehensions, pyupgrade)
- **Type Checking:** mypy (strict_optional, pydantic plugin)
- **Security:** nh3 (XSS sanitization, Rust-based), pip-audit (dependency scanning)

## Database

- **Provider:** Neon PostgreSQL (serverless)
- **Project:** `cold-rice-23455092` ("energyoptimize")
- **Connection:** asyncpg with PgBouncer (statement_cache_size=0)
- **Migrations:** 49 sequential SQL migrations (init_neon through 049_community_tables)
- **Schema:** 44 public + 9 neon_auth = 53 tables, UUID primary keys

## ML

- **Ensemble predictor** with HNSW vector search
- **Adaptive learning** with nightly retraining
- **611 tests** covering models, inference, optimization, evaluation

## Infrastructure

| Service | Purpose |
|---------|---------|
| **Render** | Backend hosting (srv-d649uhur433s73d557cg) |
| **Vercel** | Frontend hosting + Next.js edge functions |
| **Neon** | Serverless PostgreSQL database |
| **Cloudflare Workers** | API Gateway (rate limiting, caching, bot detection) |
| **Stripe** | Payments (Free/$4.99 Pro/$14.99 Business) |
| **Resend** | Primary email delivery |
| **OneSignal** | Push notifications |
| **Slack** | Team alerts (electricityoptimizer.slack.com) |
| **Sentry** | Error tracking and monitoring |
| **Grafana Cloud** | Distributed tracing (OpenTelemetry + Tempo) |
| **UptimeRobot** | Uptime monitoring |
| **Better Stack** | Incident management |
| **GitHub Actions** | CI/CD (28 workflows + Dependabot) |
| **OWASP ZAP** | Weekly security baseline scan |

## Key Dependencies

### Backend (Python)
- fastapi, uvicorn, sqlalchemy[asyncio], asyncpg
- pydantic, structlog, sentry-sdk
- stripe, resend, httpx
- nh3 (XSS sanitization)

### Frontend (Node)
- next, react, tailwindcss
- @tanstack/react-query, better-auth, zustand
- nodemailer (Gmail SMTP fallback)
