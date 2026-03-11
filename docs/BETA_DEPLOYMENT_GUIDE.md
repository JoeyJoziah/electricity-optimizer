# RateShift - Deployment & Launch Guide

**Project**: RateShift (Automated Electricity Supplier Price Optimizer)
**Deployment Type**: Public Launch (Early Access / Freemium)
**Infrastructure Budget**: <$50/month (Render.com + Neon PostgreSQL + Cloudflare Worker)

> **NOTE (2026-03-11):** This guide covers production deployment. The project has transitioned from "beta" to "public signup" with a freemium model.
> Domain `rateshift.app` purchased via Cloudflare Registrar. Email verified on Resend with full DKIM/SPF/DMARC.
> Edge layer: Cloudflare Worker `rateshift-api-gateway` deployed at `api.rateshift.app` with 2-tier caching, KV rate limiting, and bot detection.
> For deployment mechanics and infrastructure details, see [DEPLOYMENT.md](DEPLOYMENT.md) and [INFRASTRUCTURE.md](INFRASTRUCTURE.md).

---

## Overview

This guide covers the public launch and ongoing operations for RateShift. For detailed deployment and infrastructure architecture, see the companion documents:
- **DEPLOYMENT.md**: Step-by-step deployment, environment variables, rollback procedures
- **INFRASTRUCTURE.md**: Architecture diagrams, service catalog, networking, scaling
- **SCALING_PLAN.md**: Scaling thresholds, cost projections, performance tuning

---

## Pre-Launch Checklist (2026-03-11)

### ✅ Infrastructure Readiness

- [x] Backend: Render (srv-d649uhur433s73d557cg, 38 env vars)
- [x] Frontend: Vercel (rateshift.app + www.rateshift.app)
- [x] Database: Neon PostgreSQL (cold-rice-23455092, 33 migrations, all applied)
- [x] Edge Layer: Cloudflare Worker (rateshift-api-gateway, 2-tier caching, rate limiting)
- [x] Domain: rateshift.app (Cloudflare Registrar)
- [x] Email: Resend (custom domain verified, DKIM/SPF/DMARC, TLS enforced)
- [x] DNS: Cloudflare zone configured (A → Vercel, CNAME api → Worker)
- [x] CI/CD: 24 GHA workflows (testing, deployment, cron jobs, self-healing)
- [x] Monitoring: Prometheus + Grafana, Sentry integration
- [x] Backup strategy: Neon point-in-time recovery, automated snapshots

### ✅ Application Readiness

- [x] All tests passing (4,500+ across backend/frontend/ML/E2E)
- [x] Security scan clean (Bandit, npm audit, container scan)
- [x] Performance targets met (API p95 <500ms, Lighthouse 90+)
- [x] Documentation complete (8 deployment docs, codemaps)
- [x] Privacy policy published (`/privacy`)
- [x] Terms of service published (`/terms`)

### ✅ Product Readiness (2026-03-10+)

- [x] Freemium billing (Free/$4.99 Pro/$14.99 Business)
- [x] AI Agent (RateShift AI, Gemini 3 Flash + Groq fallback, Composio tools)
- [x] Notification system (OneSignal push + email alerts)
- [x] A/B testing framework (model versioning, consistent hashing)
- [x] Alert dedup system (cooldown windows: immediate=1h, daily=24h, weekly=7d)
- [x] Beta→Early Access transition (validate_postcode backward compat)
- [x] Launch marketing materials (Product Hunt, HN, Reddit post templates)

---

## Current Production Setup (2026-03-11)

**Architecture:**
- **Frontend**: Vercel (Next.js 16, React 19, TypeScript)
- **Backend**: Render.com (FastAPI, Python 3.12)
- **Edge Layer**: Cloudflare Worker (rateshift-api-gateway)
- **Database**: Neon PostgreSQL (serverless, production branch)
- **Cache/Queue**: Redis (Upstash or self-hosted)
- **Scheduling**: GitHub Actions (24 workflows)
- **Monitoring**: Prometheus + Grafana, Sentry (error tracking)
- **Email**: Resend (primary) + Gmail SMTP (fallback)
- **Push notifications**: OneSignal
- **Payments**: Stripe (webhook-driven, async billing)
- **AI**: Gemini 3 Flash (primary) + Groq Llama 3.3 (fallback)

**Deployment Flow:**
1. Code pushed to `main`
2. GitHub Actions CI runs tests, security scans, builds Docker images
3. Backend: Render auto-deploys via deploy hook (2min)
4. Frontend: Vercel auto-deploys
5. Worker: Deploy via GHA workflow (manual or release trigger)
6. Database: Migrations applied automatically by backend startup (Alembic)

For detailed deployment procedures, see **DEPLOYMENT.md**.

---

## Step-by-Step Deployment (Render.com)

### Step 1: Prepare Environment Variables

Create `.env.production`:

```bash
# Neon PostgreSQL (serverless database)
NEON_DATABASE_URL=postgresql://[user]:[password]@[host].neon.tech/neondb?sslmode=require
# Project: cold-rice-23455092 ("energyoptimize"), Branch: production

# Neon Auth (Better Auth) — session-based authentication
BETTER_AUTH_SECRET=$(openssl rand -base64 32)
BETTER_AUTH_URL=https://your-app-url.com

# External APIs (sign up for free tiers)
FLATPEAK_API_KEY=[sign up at flatpeak.energy]
NREL_API_KEY=[sign up at developer.nrel.gov]
IEA_API_KEY=[sign up at iea.org]

# Redis (use Redis Cloud free tier, used for caching and session store)
REDIS_URL=redis://[username]:[password]@[host]:6379

# Internal API Key (service-to-service auth, e.g. price-sync workflow)
INTERNAL_API_KEY=$(openssl rand -base64 32)

# Monitoring
GRAFANA_PASSWORD=$(openssl rand -base64 16)

# Environment
NODE_ENV=production
ENVIRONMENT=beta
```

### Step 2: Deploy Backend + Frontend to Render.com

```bash
# 1. Ensure render.yaml is in repo root (already present)
# render.yaml defines both backend and frontend services

# 2. Connect to Render.com
# Visit https://dashboard.render.com
# New → Blueprint → Connect your GitHub repo
# Render auto-detects services from render.yaml

# 3. Set environment variables in Render Dashboard
# For each service, add the variables from .env.production:
# - NEON_DATABASE_URL
# - BETTER_AUTH_SECRET, BETTER_AUTH_URL
# - REDIS_URL
# - INTERNAL_API_KEY
# - FLATPEAK_API_KEY, NREL_API_KEY, EIA_API_KEY
# (see .env.example for full list)

# 4. Deploy triggers automatically when you push to main
git push origin main

# 5. Get service URLs from Render Dashboard
# Backend: https://api.rateshift.app
# Frontend: https://rateshift.app
```

### Step 3: Verify Frontend Configuration

The frontend is deployed as part of the Render.com Blueprint (Step 2). If you need to configure additional environment variables:

```bash
# In Render Dashboard → Frontend Service → Environment:
# NEXT_PUBLIC_API_URL=https://[backend-service-url]
# NEXT_PUBLIC_ENVIRONMENT=beta
# BETTER_AUTH_SECRET=<same as backend>
# BETTER_AUTH_URL=https://[frontend-service-url]

# Auth uses Neon Auth (Better Auth) with session-based cookies (httpOnly)
# Sign-up/sign-in handled by Better Auth API routes in frontend
# Backend validates sessions by querying neon_auth.session table
```

### Step 4: Configure GitHub Actions Workflows

Scheduling and pipeline orchestration are handled by GitHub Actions (Airflow was removed 2026-02-12).

```bash
# 1. Verify workflows exist in .github/workflows/
ls .github/workflows/

# 2. Set required GitHub Actions secrets
# Go to: GitHub repo → Settings → Secrets and variables → Actions
# Add:
#   NEON_DATABASE_URL
#   INTERNAL_API_KEY (for price-sync workflow)
#   RENDER_API_KEY (for deploy triggers, if used)

# 3. Verify workflows are active
gh workflow list

# 4. Manually trigger price-sync to test
gh workflow run price-sync.yml

# 5. Check workflow run status
gh run list --workflow=price-sync.yml
```

### Step 5: Set Up Monitoring

Monitoring runs via the `monitoring/` directory with docker-compose for local dev, or self-hosted alongside the application.

```bash
# 1. Start monitoring stack locally
docker compose up -d prometheus grafana

# 2. Configure Grafana
# Visit http://localhost:3001
# Login: admin / [GRAFANA_PASSWORD from .env]

# 3. Import dashboards
# Dashboards → Import → monitoring/grafana/dashboards/overview.json

# 4. For production, Prometheus + Grafana can be hosted on
#    the same Render.com instance or a separate service
```

### Step 6: Configure Custom Domain (Optional)

```bash
# In Render Dashboard:
# 1. Select Frontend service → Settings → Custom Domains
#    Add: rateshift.app
#    Follow DNS instructions (CNAME to .onrender.com)

# 2. Select Backend service → Settings → Custom Domains
#    Add: api.rateshift.app
#    Update frontend env: NEXT_PUBLIC_API_URL=https://api.rateshift.app
```

### Step 7: Verify Deployment

```bash
# Health checks
curl https://api.rateshift.app/health
curl https://rateshift.app

# Test API endpoints
curl https://api.rateshift.app/api/v1/prices/current?region=US_CT

# Check logs (via Render Dashboard or CLI)
# Render Dashboard → Service → Logs tab

# Check GitHub Actions workflow status
gh run list

# Monitor metrics
# Visit: http://localhost:3001 (Grafana)
```

---

## Public Launch & User Acquisition

### Phase 1: Launch & Awareness (Week 1)

**Target**: Initial signups via launch channels

**Launch Channels**:
1. Product Hunt (official launch post)
2. Hacker News (Show HN post)
3. Reddit (r/energy, r/personalfinance, r/homeautomation)
4. Twitter/LinkedIn announcement
5. Newsletter mentions (if applicable)

**Freemium Sign-Up Flow**:
- Public signup at `https://rateshift.app/auth/signup` (no gating)
- Email verification via Resend (magic link or verification code)
- Free tier includes: 1 alert, basic price tracking, 24-hour forecasts
- Pro tier ($4.99/mo): unlimited alerts, advanced forecasts, recommendations
- Business tier ($14.99/mo): API access, bulk operations, dedicated support

### Phase 2: Onboarding (Continuous)

**Welcome Email** (sent immediately after email verification):

```
Subject: Welcome to RateShift - Start Saving on Electricity

Hi [Name],

Welcome to RateShift! We're excited to help you reduce your electricity costs.

**Getting Started:**

1. **Complete Your Profile**: https://rateshift.app/onboarding
   - Region/ZIP code for accurate pricing
   - Utility provider (optional, for bill import)

2. **Explore Features**:
   - Real-time electricity prices for your region
   - 24-hour price forecasts (updated hourly)
   - Automatic supplier switching recommendations
   - Price alerts (1 free alert, Pro/Business for unlimited)

3. **Connect Your Meter** (Optional):
   - Import smart meter data via UtilityAPI
   - Upload bill PDFs for historical analysis
   - Track actual usage vs. forecasts

4. **Support & Feedback**:
   - Help center: https://rateshift.app/help
   - Direct email: support@rateshift.app
   - In-app feedback widget

**Pricing:**
- Free: Basic price tracking, 1 alert, 24-hour forecasts
- Pro ($4.99/mo): Unlimited alerts, advanced forecasts, recommendations
- Business ($14.99/mo): API access, bulk operations, priority support

Thank you for joining RateShift! 🚀

Best regards,
The RateShift Team
```

**Onboarding Checklist**:
- [ ] Account created
- [ ] Email verified
- [ ] Region/ZIP code set
- [ ] Dashboard accessed
- [ ] First price check done
- [ ] Pricing tier viewed (optional upgrade)

### Phase 3: Engagement & Retention (Ongoing)

**Communication Plan**:
- **Daily**: Price alerts (user-configured)
- **Weekly**: Savings report (if alerts triggered)
- **Monthly**: Feature updates, savings summary
- **On-demand**: Support via email, in-app widget

**Engagement Metrics**:
- Email open rate (target: 30%+)
- Alert effectiveness (savings attributed)
- Feature adoption (forecasts viewed, alerts set, upgrades)
- Support satisfaction (response time <24h)

**Retention Strategy**:
- Free tier users: Show path to Pro (alerts limitation)
- Pro users: Highlight advanced features + API access
- Business users: VIP support, beta features, API SLA
- Churned users: Re-engagement campaigns with feature updates

---

## Monitoring & Alerting

### Critical Metrics to Monitor

**System Health**:
- Uptime (target: 99%+)
- Error rate (target: <2% for beta)
- API latency (p95 <500ms)
- Database connections
- Redis hit rate

**User Metrics**:
- Signups per day
- Activation rate (complete onboarding)
- Daily/Weekly Active Users
- Feature usage rates
- NPS score

**Business Metrics**:
- Forecast accuracy (MAPE)
- Average savings per user
- Supplier switching rate
- Support tickets
- Bug reports

### Alert Rules (Grafana)

```yaml
# High Priority Alerts (PagerDuty/Email)
- name: ServiceDown
  condition: up == 0
  for: 5m

- name: HighErrorRate
  condition: error_rate > 0.05
  for: 10m

- name: HighLatency
  condition: p95_latency > 1000ms
  for: 15m

# Medium Priority (Email only)
- name: LowActivation
  condition: activation_rate < 0.5
  for: 24h

- name: ForecastInaccurate
  condition: mape > 0.15
  for: 1h
```

### Daily Standup Dashboard

Create Grafana dashboard showing:
1. **Yesterday's Metrics**:
   - New signups
   - Active users
   - Error rate
   - Average latency

2. **This Week**:
   - Cumulative signups
   - Retention rate (day 1, day 7)
   - NPS trend
   - Feature usage

3. **Alerts**:
   - Open incidents
   - Recent errors
   - Performance issues

---

## Support & Maintenance

### Support Channels

**Primary**: support@rateshift.app
- Response SLA: <24 hours
- Escalation: <4 hours for P0 issues

**Secondary**: In-app feedback widget
- For non-urgent feedback
- Integrated with Linear/GitHub Issues

**Knowledge Base**: /help
- FAQ
- Getting started guide
- Troubleshooting
- Video tutorials

### Common Issues & Fixes

**Issue**: Smart meter won't connect
**Fix**:
1. Verify UtilityAPI credentials
2. Check meter compatibility
3. Offer manual CSV upload alternative

**Issue**: Forecast not loading
**Fix**:
1. Check GitHub Actions workflow status (`gh run list`)
2. Verify ML model deployed
3. Check Neon PostgreSQL connection

**Issue**: Supplier comparison shows no results
**Fix**:
1. Verify user postcode valid
2. Check external API status (Flatpeak)
3. Refresh API cache

### Bug Reporting Process

1. **User reports bug** → Create Linear issue
2. **Triage** (within 4 hours):
   - P0 (Critical): Immediate fix
   - P1 (High): Fix within 24h
   - P2 (Medium): Fix within week
   - P3 (Low): Backlog
3. **Fix & deploy** → Notify user
4. **Follow-up** → Confirm resolved

---

## Scaling Plan

For detailed scaling guidance, cost projections, and performance tuning, see **SCALING_PLAN.md**.

### Current Capacity (2026-03-11)

- **Users**: Unlimited (freemium model, no beta gating)
- **Concurrent API**: 1000+ (Render Standard tier)
- **Database**: Neon PostgreSQL (production branch, serverless autoscaling)
- **Cache**: Redis (Upstash or self-hosted)
- **Edge**: Cloudflare Worker (free tier: 100K req/day)
- **Hosting**: Render.com + Vercel + Cloudflare
- **Cost**: <$50/month baseline (Render backend + Neon + domain)

### Scaling Triggers

**At 100 users**:
- Monitor Neon database compute usage
- Watch Redis memory usage
- Track API latency

**At 500 users**:
- Upgrade Neon to Launch plan ($19/month)
- Upgrade Redis to paid tier ($5/month)
- Scale Render.com backend instances
- **Estimated cost**: $50-60/month

**At 1000 users**:
- Scale Render.com instances (2x backend)
- Upgrade Neon compute
- Implement CDN (Cloudflare)
- **Estimated cost**: $75-100/month

**At 5000 users**:
- Multi-region deployment
- Neon database read replicas
- Auto-scaling groups on Render.com
- **Estimated cost**: $200-300/month

---

## Rollback Procedure

### If Critical Issues Occur

**Immediate Response** (within 5 minutes):

```bash
# 1. Rollback via Render Dashboard
# Services → Backend → Deploys → select previous deploy → "Rollback"
# (Render keeps deploy history for instant rollback)

# 2. Notify users
# Send status email: "We're experiencing issues, investigating..."

# 3. Check last known good version
git log --oneline

# 4. Alternative: rollback via Git
git revert HEAD
git push origin main
# Render auto-deploys on push to main

# 5. Restore database if needed
./scripts/restore.sh [backup-timestamp]

# 6. Verify rollback
make health
make smoke-test

# 7. Send all-clear
# Email: "Issue resolved, service restored"
```

### Post-Mortem Template

```markdown
# Incident Post-Mortem: [Date]

## Summary
[What happened, impact, duration]

## Timeline
- [Time]: Issue detected
- [Time]: Investigation started
- [Time]: Root cause identified
- [Time]: Fix deployed
- [Time]: Service restored

## Root Cause
[Technical details]

## Impact
- Users affected: [count]
- Duration: [minutes]
- Data loss: [none/details]

## Resolution
[What fixed it]

## Prevention
- [ ] Action item 1
- [ ] Action item 2
- [ ] Monitoring improvement
- [ ] Documentation update
```

---

## Launch Success Metrics (Target: Week 1-4)

### Must Have (Launch Blocking) ✅
- [ ] 0 critical bugs (P0) in production
- [ ] 99%+ uptime (monitoring via Sentry, Grafana)
- [ ] All 24 GHA workflows passing (CI/CD, cron jobs, deploys)
- [ ] Email delivery working (Resend primary + Gmail fallback)
- [ ] Stripe payments processing (checkout + webhook)

### Should Have (Week 1 Goals) 🎯
- [ ] 100+ signups from launch channels
- [ ] 30%+ email verification rate
- [ ] 20%+ activation rate (alert created)
- [ ] <2% error rate (API)
- [ ] API p95 latency <500ms
- [ ] Forecast accuracy MAPE <10%
- [ ] <24h support response time

### Nice to Have (Growth) 🌟
- [ ] 10+ Pro/Business trial conversions
- [ ] 20+ user feedback submissions
- [ ] 5+ testimonials/reviews
- [ ] 50+ social media mentions
- [ ] 500+ monthly active users by month end

---

## Quick Reference Commands

```bash
# Deploy to production (push to main triggers Render.com auto-deploy)
git push origin main

# Check health
make health

# View logs (Render Dashboard or GitHub Actions)
gh run list
# Or: Render Dashboard → Service → Logs

# Database backup
./scripts/backup.sh

# Rollback (use Render Dashboard → Deploys → Rollback)
# Or via Git:
git revert HEAD && git push origin main

# Trigger price-sync manually
gh workflow run price-sync.yml

# Monitor
make grafana  # Open dashboards
make metrics  # View key metrics
```

---

## Contact Information

**Technical Lead**: [Your name/email]
**Support Email**: support@rateshift.app
**Feedback Email**: feedback@rateshift.app
**Security Issues**: security@rateshift.app

---

**Last Updated**: 2026-03-11
**Deployment Status**: Production (public launch)
**Current Users**: Growing (freemium)
**Architecture**: Vercel + Render + Cloudflare Worker + Neon

**Quick Links**:
- **DEPLOYMENT.md**: Detailed deployment procedures, environment setup, troubleshooting
- **INFRASTRUCTURE.md**: Architecture diagrams, service details, monitoring
- **SCALING_PLAN.md**: Performance targets, cost projections, scaling decisions
- **REDEPLOYMENT_RUNBOOK.md**: Emergency redeployment procedures (if needed)

**Monitoring Dashboards**:
- Grafana: `http://localhost:3001` (local) or production instance
- Sentry: Error tracking and performance monitoring
- GitHub Actions: Workflow status, deployment logs
- Render: Backend service logs and metrics
- Vercel: Frontend deployment status
- Cloudflare: Worker analytics and performance
