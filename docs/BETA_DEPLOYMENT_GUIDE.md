# 🚀 Beta Deployment Guide

**Project**: Automated Electricity Supplier Price Optimizer
**Deployment Type**: Beta (50+ users)
**Infrastructure Budget**: <$50/month (Render.com + Neon PostgreSQL)

---

## Overview

This guide covers the complete beta deployment process, from infrastructure setup to user onboarding and monitoring.

---

## Pre-Deployment Checklist

### ✅ Infrastructure Readiness

- [x] Docker containers built and tested
- [x] docker-compose.yml configured
- [x] Health checks implemented
- [x] Monitoring setup (Prometheus + Grafana)
- [x] CI/CD pipeline functional
- [x] Backup strategy defined
- [x] Rollback procedure documented

### ✅ Application Readiness

- [x] All tests passing (527+)
- [x] Security scan clean (0 vulnerabilities)
- [x] Performance targets met
- [x] Documentation complete
- [x] Privacy policy published
- [x] Terms of service published

### 🟡 Beta Program Setup

- [ ] Beta user recruitment (target: 50+ users)
- [ ] Beta signup form created
- [ ] Welcome email template
- [ ] Feedback collection system
- [ ] Support channels configured

---

## Deployment Options

### Option 1: Render.com (Current) - <$50/month

**Pros:**
- Simple deployment via `render.yaml` (Infrastructure as Code)
- Built-in CI/CD from GitHub
- Automatic HTTPS
- Easy scaling
- Supports backend + frontend services

**Current Setup:**

- **Frontend**: Render.com (Next.js static site or web service)
- **Backend**: Render.com (FastAPI web service)
- **Database**: Neon PostgreSQL (serverless, free tier)
- **Redis**: Redis Cloud (Free tier, 30MB) or Render Redis
- **Scheduling**: GitHub Actions workflows (price-sync, CI/CD)
- **Monitoring**: Prometheus + Grafana (self-hosted)

**Setup:**

```bash
# 1. Push render.yaml to GitHub (already in repo root)
# Render.com auto-detects services from render.yaml

# 2. Connect GitHub repo in Render Dashboard
# Visit https://dashboard.render.com → New → Blueprint → select repo

# 3. Set environment variables in Render Dashboard
# NEON_DATABASE_URL, JWT_SECRET, REDIS_URL, etc.
# (see .env.example for full list)

# 4. Deploy triggers automatically on push to main
```

### Option 2: Fly.io - $5/month

**Pros:**
- Global edge deployment
- Free allowance (3 shared CPUs)
- Automatic scaling
- Built-in load balancing

**Setup:**

```bash
# 1. Install Fly CLI
curl -L https://fly.io/install.sh | sh

# 2. Login
fly auth login

# 3. Create app
fly launch --name electricity-optimizer

# 4. Deploy
fly deploy

# 5. Add databases
fly postgres create --name electricity-db
fly redis create --name electricity-cache

# 6. Set secrets
fly secrets set NEON_DATABASE_URL=xxx JWT_SECRET=xxx
```

**Total**: Under $50/month target

---

## Step-by-Step Deployment (Render.com)

### Step 1: Prepare Environment Variables

Create `.env.production`:

```bash
# Neon PostgreSQL (serverless database)
NEON_DATABASE_URL=postgresql://[user]:[password]@[host].neon.tech/neondb?sslmode=require
# Project: holy-pine-81107663, Branch: main

# JWT Authentication (with Redis-backed token revocation)
JWT_SECRET=$(openssl rand -base64 32)
JWT_ALGORITHM=HS256

# External APIs (sign up for free tiers)
FLATPEAK_API_KEY=[sign up at flatpeak.energy]
NREL_API_KEY=[sign up at developer.nrel.gov]
IEA_API_KEY=[sign up at iea.org]

# Redis (use Redis Cloud free tier, also used for JWT token revocation)
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
# - JWT_SECRET
# - REDIS_URL
# - INTERNAL_API_KEY
# - FLATPEAK_API_KEY, NREL_API_KEY, IEA_API_KEY
# (see .env.example for full list)

# 4. Deploy triggers automatically when you push to main
git push origin main

# 5. Get service URLs from Render Dashboard
# Backend: https://electricity-optimizer-api.onrender.com
# Frontend: https://electricity-optimizer.onrender.com
```

### Step 3: Verify Frontend Configuration

The frontend is deployed as part of the Render.com Blueprint (Step 2). If you need to configure additional environment variables:

```bash
# In Render Dashboard → Frontend Service → Environment:
# NEXT_PUBLIC_API_URL=https://[backend-service-url]
# NEXT_PUBLIC_ENVIRONMENT=beta

# The frontend uses JWT-based auth (not a third-party auth provider)
# JWT tokens are issued by the FastAPI backend and validated via Redis
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
#    Add: electricity-optimizer.app
#    Follow DNS instructions (CNAME to .onrender.com)

# 2. Select Backend service → Settings → Custom Domains
#    Add: api.electricity-optimizer.app
#    Update frontend env: NEXT_PUBLIC_API_URL=https://api.electricity-optimizer.app
```

### Step 7: Verify Deployment

```bash
# Health checks
curl https://api.electricity-optimizer.app/health
curl https://electricity-optimizer.app

# Test API endpoints
curl https://api.electricity-optimizer.app/api/v1/prices/current?region=US_CT

# Check logs (via Render Dashboard or CLI)
# Render Dashboard → Service → Logs tab

# Check GitHub Actions workflow status
gh run list

# Monitor metrics
# Visit: http://localhost:3001 (Grafana)
```

---

## Beta User Onboarding

### Phase 1: Recruitment (Week 1)

**Target**: 50+ beta users

**Recruitment Channels**:
1. Personal network (10-15 users)
2. Twitter/LinkedIn announcement (15-20 users)
3. UK energy forums/Reddit (10-15 users)
4. Product Hunt "Coming Soon" (5-10 users)

**Beta Signup Form**:
```html
<!-- Create at: /beta-signup -->
<form action="/api/beta-signup" method="POST">
  <input name="email" type="email" required>
  <input name="name" type="text" required>
  <input name="zipcode" placeholder="ZIP Code">
  <select name="current_supplier">
    <option>Eversource Energy</option>
    <option>United Illuminating (UI)</option>
    <option>Town utility</option>
    <option>Other</option>
  </select>
  <label>
    <input type="checkbox" name="agree_nda" required>
    I agree to the Beta NDA and Terms
  </label>
  <button type="submit">Join Beta</button>
</form>
```

### Phase 2: Onboarding (Week 1-2)

**Welcome Email** (send immediately after signup):

```
Subject: Welcome to Electricity Optimizer Beta! 🎉

Hi [Name],

Congratulations! You've been accepted to the Electricity Optimizer beta program.

Here's what to expect:

1. **Get Started**: Visit https://electricity-optimizer.app/auth/signup
   Use this beta code: BETA-2026-[unique-code]

2. **Connect Your Data**: We support smart meters via UtilityAPI
   (Optional - you can skip and see demo data)

3. **Explore Features**:
   - Real-time electricity price tracking
   - 24-hour price forecasting
   - Automatic supplier switching recommendations
   - Smart appliance scheduling

4. **Share Feedback**: Your feedback shapes the product!
   - In-app feedback widget (bottom-right corner)
   - Direct email: feedback@electricity-optimizer.app
   - Weekly survey (5 min)

**Support**:
- Email: support@electricity-optimizer.app
- Response time: <24 hours
- Known issues: [link to changelog]

**What We're Testing**:
- Forecast accuracy (target: <10% error)
- Savings recommendations (target: $200+/year)
- User experience and onboarding

Thank you for being an early supporter! 🚀

Best regards,
The Electricity Optimizer Team

P.S. First 50 beta users get lifetime 50% discount when we launch!
```

**Onboarding Checklist** (track in dashboard):
- [ ] Account created
- [ ] Email verified
- [ ] Profile completed (postcode, supplier)
- [ ] Smart meter connected (optional)
- [ ] Dashboard viewed
- [ ] First forecast generated
- [ ] Feedback submitted

### Phase 3: Engagement (Week 2-4)

**Weekly Updates**:
- Monday: Feature spotlight email
- Wednesday: Savings report (personalized)
- Friday: Beta changelog + upcoming features

**Feedback Collection**:
- **In-app widget**: Continuous feedback
- **Weekly survey**: NPS + feature requests
- **User interviews**: 10 users (30 min each)
- **Usage analytics**: Mixpanel/Amplitude

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

**Primary**: support@electricity-optimizer.app
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

### Current Capacity

- **Users**: 50-100 (beta)
- **API**: 1000+ concurrent users
- **Database**: Neon PostgreSQL free tier (0.5 GB storage, serverless autoscaling)
- **Redis**: 30MB (Redis Cloud free)
- **Hosting**: Render.com (render.yaml Blueprint)
- **Cost**: <$50/month target

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

## Success Criteria (Week 1)

### Must Have ✅
- [ ] 50+ beta users signed up
- [ ] 70%+ activation rate
- [ ] 0 critical bugs (P0)
- [ ] 99%+ uptime
- [ ] <24h support response time

### Should Have 🎯
- [ ] 50%+ retention (day 2)
- [ ] NPS 40+
- [ ] <2% error rate
- [ ] API p95 <500ms
- [ ] Forecast MAPE <10%

### Nice to Have 🌟
- [ ] 10+ user testimonials
- [ ] 5+ supplier switches
- [ ] $150+ average savings shown
- [ ] 30%+ daily active rate

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
**Support Email**: support@electricity-optimizer.app
**Feedback Email**: feedback@electricity-optimizer.app
**Security Issues**: security@electricity-optimizer.app

---

**Last Updated**: 2026-02-23
**Deployment Status**: Ready for beta
**Current Users**: 0 (pre-launch)
**Target Users**: 50+ (week 1)

**Next Steps**:
1. ✅ Complete deployment checklist
2. 🟡 Recruit beta users
3. 🔴 Deploy to production
4. 🔴 Send welcome emails
5. 🔴 Monitor and iterate
