# Environment Variable Reference

> Last updated: 2026-04-27 | Source: `backend/config/settings.py`, `render.yaml`, `wrangler.toml`, `frontend/lib/config/env.ts`
> Note: `OAUTH_STATE_SECRET` is required in production (separate from `INTERNAL_API_KEY` per security audit H-4).

## Backend (Render — 52 env vars in production)

Settings loaded via pydantic-settings from env vars (dev) or 1Password (prod). Source: `backend/config/settings.py`.

### Core Application

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENVIRONMENT` | Yes | `development` | `development`, `staging`, `production`, or `test` |
| `BACKEND_PORT` | No | `8000` | Port for the FastAPI server |
| `CORS_ORIGINS` | Yes (prod) | `["http://localhost:3000"]` | JSON array or comma-separated origins |
| `FRONTEND_URL` | Yes (prod) | `http://localhost:3000` | Frontend origin for OAuth redirects |
| `DEBUG` | No | `false` | Enable debug mode |

### Database & Cache

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes (prod) | None | Neon PostgreSQL connection string. Must start with `postgresql://` |
| `DB_POOL_SIZE` | No | `5` | SQLAlchemy connection pool size |
| `DB_MAX_OVERFLOW` | No | `10` | Max overflow connections |
| `REDIS_URL` | No | None | Redis connection string (Upstash) |
| `REDIS_PASSWORD` | No | None | Redis auth password |
| `REDIS_MAX_CONNECTIONS` | No | `20` | Redis connection pool size |

### Authentication & Security

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_SECRET` | Yes (prod) | Auto-generated | Session signing secret. Min 32 chars in prod |
| `BETTER_AUTH_SECRET` | Yes (prod) | None | Better Auth session secret. Min 32 chars |
| `BETTER_AUTH_URL` | Yes (prod) | None | Better Auth server URL |
| `INTERNAL_API_KEY` | Yes (prod) | None | Service-to-service auth (X-API-Key header). Min 32 chars. Must differ from JWT_SECRET |
| `OAUTH_STATE_SECRET` | Yes (prod) | None | HMAC signing for OAuth state params. Min 32 chars. Must differ from INTERNAL_API_KEY |
| `FIELD_ENCRYPTION_KEY` | Yes (prod) | None | AES-256-GCM key for account numbers. Exactly 64 hex chars (32 bytes) |
| `FIELD_ENCRYPTION_KEY_PREVIOUS` | No | None | Previous encryption key for rotation (decryption-only fallback) |
| `ML_MODEL_SIGNING_KEY` | Yes (prod) | None | HMAC-SHA256 model integrity signing. Min 32 chars |

### OAuth Providers (Social Login)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | No | None | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | No | None | Google OAuth client secret |
| `GITHUB_CLIENT_ID` | No | None | GitHub OAuth client ID (App ID 3466397) |
| `GITHUB_CLIENT_SECRET` | No | None | GitHub OAuth client secret |
| `OAUTH_REDIRECT_BASE_URL` | No | `http://localhost:8000` | Base URL for OAuth callbacks |

### Email OAuth (Connection Bill Import)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GMAIL_CLIENT_ID` | No | None | Gmail OAuth for email bill import |
| `GMAIL_CLIENT_SECRET` | No | None | Gmail OAuth secret |
| `OUTLOOK_CLIENT_ID` | No | None | Outlook OAuth for email bill import |
| `OUTLOOK_CLIENT_SECRET` | No | None | Outlook OAuth secret |

### Email (Transactional)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RESEND_API_KEY` | Yes (prod) | None | Resend API key (primary). Must start with `re_` |
| `EMAIL_FROM_ADDRESS` | No | `noreply@rateshift.app` | Sender email address |
| `EMAIL_FROM_NAME` | No | `RateShift` | Sender display name |
| `SMTP_HOST` | No | None | SMTP fallback host |
| `SMTP_PORT` | No | `587` | SMTP port |
| `SMTP_USERNAME` | No | None | SMTP username |
| `SMTP_PASSWORD` | No | None | SMTP password (Gmail app password) |

### Stripe Billing

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STRIPE_SECRET_KEY` | Yes (prod) | None | Stripe API secret. Must start with `sk_` |
| `STRIPE_WEBHOOK_SECRET` | No | None | Stripe webhook signing secret |
| `STRIPE_PRICE_PRO` | No | None | Stripe Price ID for Pro tier ($4.99/mo) |
| `STRIPE_PRICE_BUSINESS` | No | None | Stripe Price ID for Business tier ($14.99/mo) |
| `STRIPE_MRR_PRICE_PRO` | No | `4.99` | MRR calculation amount (KPI reports only) |
| `STRIPE_MRR_PRICE_BUSINESS` | No | `14.99` | MRR calculation amount (KPI reports only) |
| `ALLOWED_REDIRECT_DOMAINS` | No | `["rateshift.app","localhost"]` | Billing redirect domain allowlist |

### External Data APIs

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EIA_API_KEY` | No | None | U.S. Energy Information Administration API |
| `NREL_API_KEY` | No | None | National Renewable Energy Laboratory API |
| `IEA_API_KEY` | No | None | International Energy Agency API |
| `FLATPEAK_API_KEY` | No | None | FlatPeak energy data API |
| `UTILITYAPI_KEY` | No | None | UtilityAPI direct utility sync |
| `OPENWEATHERMAP_API_KEY` | No | None | Weather data (primary geocoding provider) |
| `DIFFBOT_API_TOKEN` | No | None | Rate scraping (free tier, 10K credits/mo) |
| `TAVILY_API_KEY` | No | None | Market research (free tier, 1K searches/mo) |
| `GOOGLE_MAPS_API_KEY` | No | None | Geocoding (dormant; OWM+Nominatim preferred) |

### AI Agent

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENABLE_AI_AGENT` | No | `false` | Enable the RateShift AI agent |
| `GEMINI_API_KEY` | Cond. | None | Required when `ENABLE_AI_AGENT=true` in prod |
| `GROQ_API_KEY` | No | None | Groq Llama 3.3 70B (fallback on Gemini 429) |
| `COMPOSIO_API_KEY` | No | None | Composio tool actions (1K actions/mo) |
| `AGENT_FREE_DAILY_LIMIT` | No | `3` | Free tier daily agent query limit |
| `AGENT_PRO_DAILY_LIMIT` | No | `20` | Pro tier daily agent query limit |

### Push Notifications

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ONESIGNAL_APP_ID` | No | None | OneSignal application ID |
| `ONESIGNAL_REST_API_KEY` | No | None | OneSignal REST API key |

### Monitoring & Observability

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SENTRY_DSN` | No | None | Sentry error tracking DSN |
| `OTEL_ENABLED` | No | `false` | Enable OpenTelemetry distributed tracing |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | None | OTLP collector endpoint (e.g. Grafana Cloud) |
| `OTEL_EXPORTER_OTLP_HEADERS` | No | None | OTLP auth headers |
| `PROMETHEUS_PORT` | No | `9090` | Prometheus metrics port |
| `UPTIMEROBOT_API_KEY` | No | None | UptimeRobot monitoring API |

### Feature Flags

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENABLE_AUTO_SWITCHING` | No | `false` | Auto-switch suppliers |
| `ENABLE_LOAD_OPTIMIZATION` | No | `true` | ML load optimization |
| `ENABLE_REAL_TIME_UPDATES` | No | `true` | SSE real-time price updates |

### Rate Limiting & Compliance

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RATE_LIMIT_PER_MINUTE` | No | `100` | Backend rate limit (per min) |
| `RATE_LIMIT_PER_HOUR` | No | `1000` | Backend rate limit (per hour) |
| `DATA_RETENTION_DAYS` | No | `730` | GDPR data retention (2 years) |
| `DATA_RESIDENCY` | No | `US` | Data residency region |
| `CONSENT_REQUIRED` | No | `true` | Require GDPR consent |

### ML Model

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MODEL_PATH` | No | None | Path to trained model file |
| `MODEL_FORECAST_HOURS` | No | `24` | Forecast horizon |
| `MODEL_RETRAIN_INTERVAL_DAYS` | No | `7` | Retrain frequency |
| `MODEL_ACCURACY_THRESHOLD_MAPE` | No | `10.0` | Accuracy threshold (MAPE %) |

### CI/CD Only (not in backend settings)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_WEBHOOK_SECRET` | No | None | GitHub webhook verification |
| `SLACK_INCIDENTS_WEBHOOK_URL` | GHA | None | Slack webhook for `#incidents` channel |

---

## Cloudflare Worker (3 secrets + 1 var)

Set via `npx wrangler secret put <NAME>`. Source: `workers/api-gateway/wrangler.toml`.

| Variable | Type | Description |
|----------|------|-------------|
| `ORIGIN_URL` | Secret | Render backend URL. Must be set — missing causes 502 |
| `INTERNAL_API_KEY` | Secret | Same as backend INTERNAL_API_KEY |
| `RATE_LIMIT_BYPASS_KEY` | Secret | Bypass rate limiting for internal calls |
| `ALLOWED_ORIGINS` | Var | CORS origins: `https://rateshift.app,https://www.rateshift.app` |

**Verify secrets**: `npx wrangler secret list --name rateshift-api-gateway`

---

## Frontend (Vercel — 6 public vars)

Build-time inlined via `NEXT_PUBLIC_*`. Source: `frontend/lib/config/env.ts`.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | No | `/api/v1` | API base URL (relative = same-origin proxy) |
| `NEXT_PUBLIC_FALLBACK_API_URL` | No | `""` | Direct-to-Render fallback (circuit breaker) |
| `NEXT_PUBLIC_APP_URL` | Warn | `http://localhost:3000` | App origin for auth redirects, SEO |
| `NEXT_PUBLIC_SITE_URL` | No | `https://rateshift.app` | Canonical URL for sitemap/robots |
| `NEXT_PUBLIC_CLARITY_PROJECT_ID` | No | `""` | Microsoft Clarity analytics |
| `NEXT_PUBLIC_ONESIGNAL_APP_ID` | No | `""` | OneSignal web push notifications |

---

## Local Development (.env template)

Create `backend/.env` for local dev:

```bash
# === Required for local dev ===
DATABASE_URL=postgresql://neondb_owner:***@ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require
ENVIRONMENT=development

# === Recommended ===
JWT_SECRET=dev-local-jwt-secret-at-least-32-characters-long
BETTER_AUTH_SECRET=dev-local-better-auth-secret-at-least-32-chars
INTERNAL_API_KEY=dev-local-internal-api-key-at-least-32-chars
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
FRONTEND_URL=http://localhost:3000

# === Optional (enable features incrementally) ===
# RESEND_API_KEY=re_...
# STRIPE_SECRET_KEY=sk_test_...
# EIA_API_KEY=...
# OPENWEATHERMAP_API_KEY=...
# ENABLE_AI_AGENT=false
# OTEL_ENABLED=false
```

Create `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=/api/v1
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

---

## 1Password Mapping

Production secrets are managed via 1Password vault "RateShift". The `SecretsManager` class (`backend/config/secrets.py`) maps secret names to 1Password item/field paths:

| Secret | 1Password Path |
|--------|---------------|
| `jwt_secret` | `API Secrets/jwt_secret` |
| `internal_api_key` | `API Secrets/internal_api_key` |
| `database_url` | `Neon PostgreSQL/database_url` |
| `stripe_secret_key` | `Stripe Keys/secret_key` |
| `resend_api_key` | `Resend/resend_api_key` |
| `gemini_api_key` | `Gemini API Key/credential` |
| `groq_api_key` | `Groq API Key/credential` |
| `field_encryption_key` | `Field Encryption/key` |
| `sentry_dsn` | `Monitoring/sentry_dsn` |

Full mapping: 28+ entries in `SecretsManager.SECRET_MAPPINGS`.

---

## Production Validation

Settings.py enforces these production-only validators:

- `DATABASE_URL` must be set and start with `postgresql://`
- `JWT_SECRET` must be set, min 32 chars, not in insecure defaults list
- `BETTER_AUTH_SECRET` must be set, min 32 chars
- `INTERNAL_API_KEY` must be set, min 32 chars, must differ from JWT_SECRET
- `OAUTH_STATE_SECRET` must be set, min 32 chars, must differ from INTERNAL_API_KEY
- `ML_MODEL_SIGNING_KEY` must be set, min 32 chars
- `FIELD_ENCRYPTION_KEY` must be set, exactly 32 bytes (64 hex chars)
- `STRIPE_SECRET_KEY` must be set and start with `sk_`
- `RESEND_API_KEY` must be set and start with `re_`
- `GEMINI_API_KEY` must be set when `ENABLE_AI_AGENT=true`

Generate secrets: `python -c "import secrets; print(secrets.token_hex(32))"`
