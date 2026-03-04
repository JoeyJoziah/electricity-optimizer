# Deployment Guide - Electricity Optimizer

This guide covers how to deploy the Electricity Optimizer platform in different environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development](#local-development)
3. [Staging Deployment](#staging-deployment)
4. [Production Deployment](#production-deployment)
5. [Rollback Procedures](#rollback-procedures)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools

- **Docker**: 20.10+ with Docker Compose 2.0+
- **Git**: For version control
- **Make**: For running common commands (optional but recommended)

### Required Accounts

- **Neon**: For serverless PostgreSQL (project: holy-pine-81107663)
- **GitHub**: For CI/CD and container registry
- **Render.com**: For backend hosting
- **Vercel**: For frontend hosting

### Authentication

Authentication uses **Neon Auth (Better Auth)** with session-based cookies:

```
BETTER_AUTH_SECRET=        # Signing key (openssl rand -hex 32)
BETTER_AUTH_URL=           # Base URL for Better Auth (e.g., https://your-app.com)
```

### API Keys

Obtain API keys from the following providers:
- Flatpeak API (UK/EU electricity prices)
- NREL API (US utility rates)
- EIA API (US energy data — gas, oil, propane)

```
# Email Service — Backend (Resend primary, SMTP fallback)
RESEND_API_KEY=            # Resend API key for transactional emails
SMTP_HOST=                 # SMTP server hostname (fallback)
SMTP_PORT=587              # SMTP port (fallback)
SMTP_USERNAME=             # SMTP username (fallback)
SMTP_PASSWORD=             # SMTP password (fallback)
EMAIL_FROM_ADDRESS=Electricity Optimizer <onboarding@resend.dev>

# Email Service — Frontend (Resend for auth emails)
RESEND_API_KEY=            # Resend API key for email verification, magic links, password reset

# ML Model Path
MODEL_PATH=                # Path to trained model directory (optional)
```

### New Environment Variables (2026-03-02)

```
# Allowed redirect domains for Stripe checkout/portal
# Accepts JSON array or comma-separated values
ALLOWED_REDIRECT_DOMAINS=["electricity-optimizer.vercel.app","electricity-optimizer-frontend.onrender.com","localhost"]

# Field-level encryption key for user account/meter numbers (AES-256-GCM)
# REQUIRED in production. Generate with: python -c "import secrets; print(secrets.token_hex(32))"
# Must be exactly 64 hex characters (32 bytes)
FIELD_ENCRYPTION_KEY=your-64-hex-char-key-here
```

---

## Local Development

### Application Architecture

The FastAPI backend uses an app factory pattern (`backend/app_factory.py`) to construct the application. The entry point `backend/main.py` imports and launches the app via `app, _app_rate_limiter = create_app()`. This pattern enables proper testing and configuration isolation while maintaining backward compatibility with existing import paths.

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/electricity-optimizer.git
cd electricity-optimizer

# 2. Copy environment file and configure
cp .env.example .env
# Edit .env with your credentials

# 3. Start all services
make setup

# Or manually:
docker compose up -d
```

### Verify Services

```bash
# Run health checks
make health

# Or manually:
./scripts/health-check.sh
```

### Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | - |
| Backend API | http://localhost:8000 | - |
| API Docs | http://localhost:8000/docs | Dev only (disabled in production) |

> **Note:** The backend includes a live email service at `backend/services/email_service.py` that handles welcome and notification emails via Resend (with SMTP fallback). Ensure the email environment variables above are configured before using email features.

### Development Workflow

```bash
# View logs
make logs

# Run tests
make test

# Format code
make format

# Restart services
make restart
```

---

## Staging Deployment

Staging deployment is triggered automatically when code is merged to the `develop` branch.

### Manual Staging Deployment

```bash
# Deploy to staging
make deploy-staging

# Or trigger via GitHub Actions
gh workflow run deploy-staging.yml
```

### Staging Environment

- URL: https://staging.electricity-optimizer.com
- Container Registry: ghcr.io/your-org/electricity-optimizer

### Verification

1. Check GitHub Actions workflow status
2. Verify health endpoints
3. Run smoke tests
4. Check Grafana dashboards

---

## Production Deployment

Production deployment is triggered when a release is published on GitHub.

### Deployment Steps

1. **Create a Release**
   ```bash
   # Create and push a tag
   git tag -a v1.0.0 -m "Release v1.0.0"
   git push origin v1.0.0

   # Create release on GitHub
   gh release create v1.0.0 --title "v1.0.0" --notes "Release notes here"
   ```

2. **Monitor Deployment**
   - Watch GitHub Actions workflow
   - Monitor Grafana dashboards
   - Check error tracking (Sentry)

3. **Verify Deployment**
   ```bash
   # Check production health
   curl https://electricity-optimizer.com/api/v1/health
   ```

### Production Checklist

Before deploying to production:

- [ ] All tests passing in CI
- [ ] Security scan passed
- [ ] Database migrations tested
- [ ] Backup created
- [ ] Rollback plan documented
- [ ] Team notified
- [ ] Vercel environment variables verified with `vercel env pull` (all values non-empty, especially `BETTER_AUTH_SECRET` and `RESEND_API_KEY`)
- [ ] Render environment variables verified (all 26 present and non-empty)
- [ ] 1Password vault in sync with production secrets

### Render Deploy Hooks

The CI/CD pipeline triggers Render deployments via deploy hooks:

1. `deploy-production.yml` runs a security gate (Bandit high-severity + npm audit critical)
2. GHCR images built and pushed for archival
3. Render deploy hooks triggered for both backend and frontend services
4. Self-healing smoke tests poll health endpoints (300s timeout, 15s interval)
5. On smoke test failure, deploy hooks are re-triggered once automatically
6. All workflows have concurrency groups to prevent overlapping deploys

**GitHub Secrets Required**:
- `RENDER_DEPLOY_HOOK_BACKEND` — deploy hook URL for backend service
- `RENDER_DEPLOY_HOOK_FRONTEND` — deploy hook URL for frontend service
- `PROD_API_URL` — production backend URL for smoke tests
- `PROD_FRONTEND_URL` — production frontend URL for smoke tests

---

## Rollback Procedures

### Automatic Rollback

If smoke tests fail, the CI/CD pipeline automatically rolls back to the previous version.

### Manual Rollback

```bash
# SSH to production server
ssh user@production-server

# Rollback to previous version
cd /app/electricity-optimizer

# Option 1: Use previous image tag
docker compose -f docker-compose.prod.yml pull
export VERSION=v0.9.0  # Previous version
docker compose -f docker-compose.prod.yml up -d

# Option 2: Restore from backup
./scripts/restore.sh
```

### Database Rollback

```bash
# Neon PostgreSQL supports point-in-time recovery and branching.
# Create a branch from a past point for recovery:
# See https://neon.tech/docs/manage/branches

# For local dev, restore from a pg_dump backup:
psql "$DATABASE_URL" < /backups/neon_YYYYMMDD.sql
```

---

## Troubleshooting

### Common Issues

#### Services Not Starting

```bash
# Check logs
docker compose logs backend
docker compose logs frontend

# Check health status
docker compose ps

# Restart specific service
docker compose restart backend
```

#### Database Connection Issues

```bash
# Test Neon PostgreSQL connection from backend
docker compose exec backend python -c "from config.database import db_manager; print('OK')"

# Or verify directly with psql (requires DATABASE_URL env var)
psql "$DATABASE_URL" -c "SELECT 1"
```

#### Redis Connection Issues

```bash
# Test Redis connection
docker compose exec redis redis-cli -a $REDIS_PASSWORD ping

# Check Redis memory
docker compose exec redis redis-cli -a $REDIS_PASSWORD INFO memory
```

#### GitHub Actions Workflows Not Running

```bash
# Check workflow status
gh run list --workflow=price-sync.yml

# Trigger workflow manually
gh workflow run price-sync.yml

# View workflow logs
gh run view [run-id] --log
```

### Performance Issues

```bash
# Check resource usage
docker stats

# Check Render logs
render logs --service srv-d649uhur433s73d557cg
```

### Getting Help

1. Check the logs: `make logs` or `render logs`
2. Check Sentry for error tracking
3. Check GitHub Issues
4. Contact the development team

---

## Security Considerations

### Secrets Management

- Never commit secrets to version control
- All production secrets stored in 1Password vault "Electricity Optimizer" (21 items, 27 SecretsManager mappings)
- `SecretsManager` in `backend/config/secrets.py` has 27 mappings covering all environment variables
- Rotate keys every 90 days
- INTERNAL_API_KEY required for service-to-service auth (price-sync workflow)

### Network Security

- All services communicate over internal Docker network
- Only frontend and backend ports exposed
- TLS/SSL required for production

### Access Control

- Use environment-specific credentials
- Limit production access to authorized personnel
- Enable audit logging

---

## Backup Schedule

| Backup Type | Frequency | Retention |
|-------------|-----------|-----------|
| Neon PostgreSQL | Continuous (managed) | Point-in-time via Neon branching |
| Redis | Daily | 7 days |

Run manual backup:
```bash
make backup
make backup-full  # Full backup of all databases
```

---

## Monitoring

### Key Metrics

| Metric | Warning | Critical |
|--------|---------|----------|
| API Latency (p95) | > 500ms | > 1s |
| Error Rate | > 1% | > 5% |
| DB Connections | > 80% | > 95% |
| Memory Usage | > 80% | > 95% |
| Price Data Age | > 15min | > 30min |
| Model MAPE | > 10% | > 15% |

### Alerts

Alerts are configured in `monitoring/alerts.yml` and sent to:
- Slack (if configured)
- Email (if configured)
- Grafana notification channels

---

**Last Updated**: 2026-03-03

## Production Services (Live)

| Service | URL | Platform |
|---------|-----|----------|
| Backend API | https://electricity-optimizer-api.onrender.com | Render (srv-d649uhur433s73d557cg) |
| Frontend | https://electricity-optimizer.vercel.app | Vercel |
| Database | Neon PostgreSQL (holy-pine-81107663) | Neon |

Backend auto-deploys on push to `main` via Render (~2 minutes). Frontend auto-deploys on push to `main` via Vercel.

### Authentication in Production

- Neon Auth (Better Auth) with session-based httpOnly cookies
- On HTTPS, cookies are auto-prefixed with `__Secure-` by Better Auth
- Backend and frontend both check for `better-auth.session_token` and `__Secure-better-auth.session_token`
- `BETTER_AUTH_SECRET` and `BETTER_AUTH_URL` must match between backend and frontend env vars

### Render Environment Variables (Backend)

The backend service has **26 env vars** on Render, all mapped to 1Password via `SecretsManager` in `backend/config/secrets.py` (27 total mappings, including one local-only mapping). Key categories:

- **Database**: `DATABASE_URL` (Neon pooler endpoint `ep-withered-morning`)
- **Auth**: `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`
- **Stripe**: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`
- **APIs**: `NREL_API_KEY`, `EIA_API_KEY`, `FLATPEAK_API_KEY`
- **Email**: `RESEND_API_KEY`, SMTP fallback vars
- **Security**: `INTERNAL_API_KEY`, `FIELD_ENCRYPTION_KEY`, `GITHUB_WEBHOOK_SECRET`
- **OAuth**: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`
- **Services**: `REDIS_URL`, `UTILITYAPI_TOKEN`, `OPENWEATHERMAP_API_KEY`
- **Config**: `ENVIRONMENT`, `ALLOWED_REDIRECT_DOMAINS`

### Vercel Environment Variables (Frontend)

The frontend service has **11 env vars** on Vercel:

| Variable | Visibility | Purpose |
|----------|-----------|---------|
| `NEXT_PUBLIC_API_URL` | Client | Backend API base URL — **default is `/api/v1` (relative, proxied through Next.js)** |
| `NEXT_PUBLIC_APP_URL` | Client | Frontend app base URL |
| `NEXT_PUBLIC_SITE_URL` | Client | Canonical site URL |
| `BACKEND_URL` | Server only | Production backend URL (`https://electricity-optimizer.onrender.com`) for server-side API calls |
| `BETTER_AUTH_SECRET` | Server only | Auth signing key |
| `BETTER_AUTH_URL` | Server only | Better Auth base URL |
| `DATABASE_URL` | Server only | Neon DB connection string |
| `RESEND_API_KEY` | Server only | Resend API key for email verification, magic links |
| `EMAIL_FROM_ADDRESS` | Server only | Email sender address (`onboarding@resend.dev`) — temporary Resend sandbox sender until a custom domain is purchased and verified |
| `GOOGLE_CLIENT_ID` | Server only | Google OAuth client ID |
| `GITHUB_CLIENT_ID` | Server only | GitHub OAuth client ID |

**CRITICAL**: Both `BETTER_AUTH_SECRET` and `RESEND_API_KEY` must be explicitly set in Vercel with non-empty values:
- If `BETTER_AUTH_SECRET` is missing, Better Auth falls back to an insecure `DEFAULT_SECRET`, compromising session signing.
- If `RESEND_API_KEY` is missing or empty, email verification and magic links will fail silently.

**Verification**: After setting environment variables, use `vercel env pull` to verify the values are correctly populated (not empty or malformed). The environment variable names and values must match exactly between Vercel and 1Password.

`NEXT_PUBLIC_` prefixed variables are client-visible and bundled into the JavaScript output. They contain only URLs -- no secrets should ever use this prefix.

### Same-Origin Proxy Pattern (2026-03-04)

Cross-origin cookies fail when the frontend (Vercel) makes direct requests to the backend (Render) due to browser CORS and cookie policies. The solution uses Next.js rewrites to proxy API calls:

**next.config.js:**
```javascript
rewrites: async () => ({
  beforeFiles: [
    {
      source: '/api/v1/:path*',
      destination: `${process.env.BACKEND_URL}/api/v1/:path*`,
    },
  ],
}),
```

**Benefits:**
- Client requests go to `https://electricity-optimizer.vercel.app/api/v1/*` (same-origin)
- Next.js server rewrites to `https://electricity-optimizer.onrender.com/api/v1/*` (server-to-server)
- Cookies are automatically included in same-origin requests
- No CORS issues; session tokens work transparently

**Environment Variables:**
- `NEXT_PUBLIC_API_URL=/api/v1` (client uses relative path)
- `BACKEND_URL=https://electricity-optimizer.onrender.com` (server uses absolute URL for rewrites)

> For a comprehensive audit of all environment variables across services, see `.swarm-reports/ENV_VAR_AUDIT_FINAL.md`.
