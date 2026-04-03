# RateShift — System Architecture

**Last Updated**: 2026-04-03 (Migration 066, 3,325 backend tests, 2,022 frontend tests, 35 GHA workflows)

## System Topology

```
                          ┌─────────────────────┐
                          │     User Browser     │
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │   Vercel (CDN/SSR)   │
                          │   Next.js 16 + React │
                          │   19 + TypeScript    │
                          └──────────┬──────────┘
                                     │  /api/v1/* proxied
                          ┌──────────▼──────────┐
                          │ Cloudflare Worker    │
                          │ api.rateshift.app    │
                          │ ┌──────────────────┐ │
                          │ │ Rate Limiting    │ │
                          │ │ 2-Tier Cache     │ │
                          │ │ Bot Detection    │ │
                          │ │ CORS/Security    │ │
                          │ └──────────────────┘ │
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │   Render (Backend)   │
                          │   FastAPI + Python   │
                          │   3.12 + Gunicorn    │
                          └───┬──────┬──────┬───┘
                              │      │      │
                 ┌────────────┘      │      └────────────┐
                 │                   │                   │
      ┌──────────▼──┐    ┌──────────▼──┐    ┌──────────▼──┐
      │    Neon      │    │   Grafana   │    │  External   │
      │  PostgreSQL  │    │   Cloud     │    │   APIs      │
      │  58 tables   │    │   Tempo     │    │ Stripe,     │
      │  64 migrations│   │   (OTel)    │    │ Resend,     │
      └──────────────┘    └─────────────┘    │ Gemini,     │
                                             │ Groq, etc.  │
                                             └─────────────┘
```

## Request Flow

1. **User** visits `rateshift.app` → served by **Vercel** (Next.js SSR/ISR)
2. Frontend API calls go to `/api/v1/*` → Next.js rewrites proxy to `api.rateshift.app`
3. **CF Worker** intercepts at edge:
   - Cache lookup (Cache API → KV fallback, `cacheTtl` on KV reads)
   - Native rate limiting (120/30/600 req/min tiers, zero KV cost)
   - Bot detection, CORS headers, security headers
   - Fail-open degradation: if KV is down, requests pass through
4. **FastAPI backend** on Render processes the request:
   - Auth via Better Auth session cookie (Neon Auth integration)
   - Internal endpoints require `X-API-Key` header
   - OTel spans for distributed tracing → Grafana Cloud Tempo
5. **Neon PostgreSQL** handles persistence (pooled endpoint for app, direct for migrations)
6. Response flows back through CF Worker (cache population) → Vercel → User

### Frontend Circuit Breaker

If the CF Worker returns 502/503, the frontend `circuitBreaker` (CLOSED → OPEN → HALF_OPEN) auto-falls back to the Render backend directly for public endpoints only. This ensures resilience against edge-layer outages.

## Authentication

```
Browser ─── POST /api/auth/sign-in ──► Better Auth (Next.js API route)
                                            │
                                            ▼
                                     Neon Auth (neon_auth schema)
                                     9 tables: user, account, session,
                                     verification, passkey, organization,
                                     member, twoFactor, jwks
                                            │
                                            ▼
                                     Set httpOnly cookie:
                                     better-auth.session_token
                                            │
Browser ◄── 200 + Set-Cookie ───────────────┘
    │
    │  Subsequent API calls include cookie automatically
    ▼
CF Worker ──► FastAPI ──► get_current_user() dependency
                          (validates session via Neon Auth)
```

- **Session-based**: `better-auth.session_token` httpOnly cookie
- **OAuth**: Google, GitHub via Better Auth callbacks
- **Magic Link**: Email-based passwordless auth
- **Internal**: `X-API-Key` header for service-to-service (GHA cron workflows)
- **Returns**: `{data, error}` pattern — Better Auth NEVER throws

## Payment Processing

```
User clicks "Upgrade to Pro"
    │
    ▼
POST /api/v1/billing/checkout
    │  (requires auth, creates Stripe Checkout Session)
    ▼
Redirect to Stripe Checkout ──► Payment ──► Stripe Webhook
                                                │
                                                ▼
                                   POST /api/v1/webhooks/stripe
                                   (validates signature, updates subscription)
                                                │
                                   ┌────────────┼────────────┐
                                   │            │            │
                              checkout.    invoice.      customer.
                              completed    payment_      subscription.
                                          failed         updated
                                              │
                                              ▼
                                     DunningService
                                     (7-day grace, soft/final emails)
```

**Tiers**: Free / Pro ($4.99/mo) / Business ($14.99/mo)

**Gated endpoints** (7 total via `require_tier()` dependency):
- Pro: forecast, savings, recommendations
- Business: prices/stream, reports, export, optimization

## AI Agent Architecture

```
User sends query via /assistant page
    │
    ▼
POST /api/v1/agent/query (SSE streaming)
    │
    ├── Rate limit check (Free: 3/day, Pro: 20/day, Business: unlimited)
    │
    ▼
AgentService
    │
    ├── Primary: Gemini 3 Flash Preview (free 10 RPM / 250 RPD)
    │   │
    │   └── On 429 ──► Fallback: Groq Llama 3.3 70B
    │
    ├── Composio Tools (1K actions/month)
    │   ├── Price lookups
    │   ├── Supplier comparison
    │   └── Rate analysis
    │
    └── SSE Response Stream ──► AgentChat component
```

- **Feature flag**: `ENABLE_AI_AGENT=true`
- **Async jobs**: `POST /agent/task` for long-running queries
- **Usage tracking**: `agent_usage_daily` table, per-user daily counters

## Multi-Utility Data Model

RateShift supports 6 utility types, each following the same service/route/model pattern:

| Utility | Service | Table(s) | CTA | Tier |
|---------|---------|----------|-----|------|
| Electricity | `price_service` | `electricity_prices`, `suppliers` | Switch supplier | Free |
| Natural Gas | `gas_rate_service` | `gas_prices` | Switch supplier | Free |
| Community Solar | `community_solar_service` | `community_solar_programs` | Enroll | Free |
| Heating Oil | `heating_oil_service` | `heating_oil_prices`, `heating_oil_dealers` | Compare dealers | Free |
| Propane | `propane_service` | `propane_prices` | Fill-up timing | Free |
| Water | `water_rate_service` | `water_rates` | Monitor only | Free |

**Design principles**:
- Water is monitoring-only (geographic monopoly, no switching)
- Each utility has its own service, API routes, frontend page, and sidebar nav item
- `UtilityType` enum in `backend/models/utility.py` is the single source of truth
- SEO: ISR pages generated at `/rates/[state]/[utility_type]` (153 pages)

## Edge Layer (CF Worker)

**Worker**: `rateshift-api-gateway` at `api.rateshift.app`
**Source**: `workers/api-gateway/` (17 files, 77 tests)

| Feature | Implementation |
|---------|---------------|
| Caching | 2-tier: Cache API (primary) + KV (fallback), `cacheTtl` on reads |
| Rate Limiting | Native CF bindings (120/30/600 per min), zero KV cost |
| Bot Detection | User-Agent analysis, block known bot patterns |
| Auth | Pass-through for session cookies, validate `X-API-Key` for internal |
| CORS | Origin whitelist, preflight caching |
| Security Headers | CSP, HSTS, X-Frame-Options, X-Content-Type-Options |
| Degradation | Fail-open on KV errors, `X-Gateway-Degraded` header |
| Observability | 7 per-isolate counters, `/internal/gateway-stats` |

## Observability

**Stack**: OpenTelemetry → Grafana Cloud Tempo (OTLP/HTTP)

```
FastAPI Request
  │
  ├── OTelMiddleware (user_id, request_id)
  ├── FastAPI auto-instrumentor (method, route, status)
  │     │
  │     ├── Service spans via traced() helper
  │     │   (price.get, stripe.webhook, agent.query, ml.train, etc.)
  │     │
  │     ├── SQLAlchemy auto-instrumentor (DB queries)
  │     └── httpx auto-instrumentor (outbound HTTP)
  │
  └── BatchSpanProcessor → OTLPSpanExporter → Grafana Cloud Tempo
```

- **16 span types** across 10 instrumented services
- **`traced()` context manager** in `backend/lib/tracing.py` (async + sync)
- **Dashboard**: `monitoring/grafana/dashboards/traces.json`
- **Docs**: `docs/OBSERVABILITY.md`

## Email System

**Primary**: Resend (domain `rateshift.app`, DKIM/SPF/DMARC verified, TLS enforced)
**Fallback**: Gmail SMTP (nodemailer for frontend)
**Sender**: `RateShift <noreply@rateshift.app>`

Templates: beta welcome, alert notification, dunning soft (amber), dunning final (red), rate change alert

## ML Pipeline

- **Ensemble predictor**: Multiple models (Prophet, XGBoost) with weighted averaging
- **HNSW vector store**: 384-dimension embeddings for similarity search
- **Observation loop**: Record forecast vs. actual, compute accuracy metrics
- **Nightly learning**: Adaptive weight updates based on observation data
- **A/B testing**: Model version comparison via `ab_tests` table

## CI/CD Pipeline

**35 GHA workflows** total:
- **CI**: Backend tests (Black + isort + flake8 + pytest), Frontend (ESLint + Jest + build), E2E (Playwright)
- **Deploy**: Migration-gate → deploy-production (Render), CF Worker deploy
- **Cron** (15 workflows): check-alerts (2h), fetch-weather (6h), market-research (daily), sync-connections (6h), daily-data-pipeline (daily 3am, consolidates scrape-rates+scan-emails+nightly-learning+detect-rate-changes), scrape-portals (weekly), dunning-cycle (daily), kpi-report (daily), fetch-heating-oil (weekly), db-maintenance (weekly), self-healing-monitor (daily), gateway-health (12h), agent-switcher-scan (daily), sync-available-plans (daily)
- **Self-healing**: `self-healing-monitor.yml` (daily) — auto-creates GitHub issues after 3+ failures
- **Security**: `owasp-zap.yml` (weekly), `pip-audit` in backend CI, `npm audit` in frontend CI
- **Composite actions**: `retry-curl` (exponential backoff), `notify-slack` (color-coded alerts), `validate-migrations`

## Security

- **OWASP ZAP**: Weekly baseline scan against Render backend
- **pip-audit**: Fail on known Python vulnerabilities
- **npm audit**: Fail on high/critical JS vulnerabilities
- **CSP**: Content Security Policy headers via CF Worker
- **HSTS**: Strict Transport Security
- **Encrypted credentials**: AES-256-GCM for portal connection passwords
- **XSS sanitization**: `nh3` library for community post content
- **AI content moderation**: Groq `classify_content()` primary, Gemini fallback, fail-closed (30s timeout)
- **1Password**: All production secrets in "RateShift" vault (28+ mappings)

## Performance Optimizations (2026-03-16)

| Area | Change | Impact |
|------|--------|--------|
| SQL aggregate refactoring | `get_price_trend_aggregates()` CTE replaces Python-side row fetching | 5,000 rows reduced to 2 scalars computed in SQL |
| React.memo audit | Prop-driven components memoized (`UtilityTabShell`, `DashboardStatsRow`, `DashboardCharts`, `DashboardForecast`); store-driven components intentionally left unmemoized | Eliminates unnecessary re-renders in the tabbed dashboard |
| SSE partial-merge | `setQueryData` updater function for real-time price updates | Replaces `invalidateQueries`, avoids full refetch on every SSE event |
| Tier caching | In-memory `_tier_cache` in `dependencies.py` for subscription tier lookups | Reduces per-request DB round-trips; autouse fixture ensures test isolation |
| Loading states | Added `loading.tsx` skeletons for all route groups | Instant perceived navigation between pages |

## Key Architecture Decisions

See `docs/adr/` for detailed Architecture Decision Records:
- [ADR-001](adr/001-neon-postgresql.md): Neon PostgreSQL as primary database
- [ADR-002](adr/002-cloudflare-worker-edge.md): Cloudflare Worker edge layer
- [ADR-003](adr/003-dual-provider-email.md): Dual-provider email system
- [ADR-004](adr/004-multi-model-ai-agent.md): Multi-model AI agent
- [ADR-005](adr/005-multi-utility-expansion.md): Multi-utility expansion pattern
