# LIVE DEPLOYMENT TRACKING

**Started**: 2026-02-07
**Platform**: Backend on Render.com, Frontend on Vercel
**Target Cost**: $25-50/month
**Status**: LIVE IN PRODUCTION

---

## Prerequisites Checklist

### Tools Installed
- [x] Docker
- [x] Render account (render.yaml in repo root)

### Accounts Needed
- [x] Neon PostgreSQL account (free tier) - https://neon.tech
- [x] Render account (paid) - https://render.com
- [x] Flatpeak API key (UK prices) - https://flatpeak.com
- [x] NREL API key (US prices) - https://developer.nrel.gov
- [x] IEA API key (optional) - https://iea.org
- [x] Stripe account (payments) - https://stripe.com
- [x] Resend account (email) - https://resend.com
- [x] Vercel account (frontend) - https://vercel.com

---

## Deployment Steps

### Step 1: Neon PostgreSQL Setup (5 min)
- [x] Create account at https://neon.tech
- [x] Neon project: "energyoptimize" (project ID: cold-rice-23455092)
- [x] Connection string from 1Password vault "RateShift"
- [x] Production branch: `production` (br-shy-sun-aibo9dns), Preview branch: `vercel-dev`
- [x] 25 migrations deployed (latest: 025_data_cache_tables)
- [x] 21 public + 9 neon_auth + 3 cache = 33 tables total

**Notes**:
```
DATABASE_URL=postgresql://neondb_owner:***@ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require
```

### Step 2: API Keys Setup (10 min)
- [x] **Flatpeak** (UK electricity prices) — API key in 1Password
- [x] **NREL** (US utility rates) — API key in 1Password
- [x] **EIA** (US energy data) — API key in 1Password
- [x] **OpenWeatherMap** — API key in 1Password
- [x] **Stripe** — Secret key + webhook secret in 1Password
- [x] **Resend** — API key in 1Password
- [x] **Sentry** — DSN in 1Password

### Step 3: Generate Secrets (1 min)
- [x] JWT_SECRET generated (internal API key validation only)
- [x] INTERNAL_API_KEY generated
- [x] BETTER_AUTH_SECRET generated (32+ chars)
- [x] FIELD_ENCRYPTION_KEY generated (AES-256-GCM)

### Step 4: Render.com Backend Deployment (10 min)
- [x] Backend deployed as Web Service on Render
- [x] URL: https://api.rateshift.app (srv-d649uhur433s73d557cg)
- [x] 34 environment variables configured
- [x] Auto-deploy on push to `main` via deploy hooks

### Step 5: Vercel Frontend Deployment (5 min)
- [x] Frontend deployed to Vercel (migrated from Render static site)
- [x] URL: https://rateshift.app
- [x] Framework: Next.js 14 (auto-detected by Vercel)
- [x] Environment variables set on Vercel (including SMTP)
- [x] Preview deployments use `vercel-dev` Neon branch

### Step 6: Verification (5 min)
- [x] Backend health: `curl https://api.rateshift.app/health` → 200
- [x] Frontend: https://rateshift.app loads
- [x] API: Dashboard renders for authenticated users
- [x] Logs: Render Dashboard shows healthy service

### Step 7: Post-Launch Verification
- [x] Stripe checkout flow working (Free/Pro/Business)
- [x] Email delivery: Resend primary + Gmail SMTP fallback
- [x] Alert system: check-alerts cron running every 30 min
- [x] 7/7 automation workflows operational
- [x] Self-healing CI/CD monitoring 13 workflows

---

## Environment Variables Template

Create `.env.production` with these values:

```env
# Neon PostgreSQL
DATABASE_URL=

# API Keys
FLATPEAK_API_KEY=
NREL_API_KEY=
IEA_API_KEY=

# Email (Resend primary)
RESEND_API_KEY=
# Email (SMTP fallback)
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
EMAIL_FROM_ADDRESS=RateShift <noreply@rateshift.app>
# ML Model
MODEL_PATH=

# Security
# NOTE: JWT_SECRET is for internal API key validation only (price-refresh endpoint X-API-Key).
# User authentication is handled entirely by Better Auth (Neon Auth) via session cookies.
JWT_SECRET=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Database (Neon PostgreSQL provides connection string)
REDIS_URL=

# Passwords
REDIS_PASSWORD=

# Internal API Key (for price-refresh endpoint)
INTERNAL_API_KEY=

# Frontend
NEXT_PUBLIC_API_URL=
```

---

## Deployment Status

### Backend (Render.com Web Service)
- Status: LIVE
- URL: https://api.rateshift.app (srv-d649uhur433s73d557cg)
- Services: FastAPI, Redis (via render.yaml)
- Database: Neon PostgreSQL (serverless, external)

### Frontend (Vercel)
- Status: LIVE
- URL: https://rateshift.app
- Framework: Next.js 14

### Cost Tracking
- Render.com Backend: $10.50/month (web service, prod tier)
- Vercel Frontend: $0-20/month (depends on usage)
- Neon PostgreSQL: $0/month (free tier, 0.5 GB) or ~$19/month (Launch tier)
- Redis/Upstash: ~$7/month (basic tier)
- **Total**: ~$25-50/month (production)

---

## Common Issues

### Render.com Deployment Fails
- Check Dockerfile paths
- Verify environment variables in Render Dashboard
- Check logs in Render Dashboard (Service > Logs)

### Frontend Can't Connect to Backend
- Verify NEXT_PUBLIC_API_URL is correct
- Check CORS settings in backend
- Verify backend is running: `curl backend-url/health`

### Database Connection Issues
- Check DATABASE_URL format (Neon requires `?sslmode=require`)
- Verify Neon project is active (not suspended due to inactivity)
- Check connection limits (Neon free tier: 100 connections via pooler)

---

## Success Criteria

- [x] Backend responding at /health endpoint
- [x] Frontend loads without errors
- [x] API endpoints return 200 OK
- [x] Stripe checkout/portal/webhook functional
- [x] Alert system running (check-alerts every 15 min)
- [x] 7/7 automation workflows live
- [x] Self-healing CI/CD operational (23 GHA workflows)
- [ ] Custom domain purchased (rateshift.app)
- [ ] DKIM/SPF/DMARC configured for Resend
- [ ] Resend custom domain email (replace Gmail SMTP fallback)

---

**Last Updated**: 2026-03-09
**Next Step**: Purchase custom domain (rateshift.app), configure DKIM/SPF/DMARC for Resend, switch from Gmail SMTP fallback to Resend custom domain for production email delivery
