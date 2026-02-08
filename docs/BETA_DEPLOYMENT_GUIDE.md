# 🚀 Beta Deployment Guide

**Project**: Automated Electricity Supplier Price Optimizer
**Deployment Type**: Beta (50+ users)
**Infrastructure Budget**: $11/month (target: <$50/month)

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

### Option 1: Railway (Recommended) - $10/month

**Pros:**
- Simple deployment
- Built-in CI/CD
- Free PostgreSQL (500MB)
- Automatic HTTPS
- Easy scaling

**Setup:**

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Create project
railway init

# 4. Add services
railway add --template postgresql
railway add --template redis

# 5. Deploy backend
railway up --service backend

# 6. Deploy frontend
railway up --service frontend

# 7. Set environment variables
railway variables set SUPABASE_URL=xxx
railway variables set JWT_SECRET=xxx
# (see .env.example for full list)
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
fly secrets set SUPABASE_URL=xxx JWT_SECRET=xxx
```

### Option 3: Vercel + Supabase + Railway - $11/month

**Current Setup** (Recommended for MVP):

- **Frontend**: Vercel (Free hobby tier)
- **Backend**: Railway ($5/month)
- **ML/Airflow**: Railway ($5/month)
- **Database**: Supabase (Free tier, 500MB)
- **Redis**: Redis Cloud (Free tier, 30MB)
- **Monitoring**: Self-hosted (Railway, $1/month)

**Total**: $11/month (78% under budget!)

---

## Step-by-Step Deployment (Vercel + Railway)

### Step 1: Prepare Environment Variables

Create `.env.production`:

```bash
# Supabase (already have account)
SUPABASE_URL=https://[project-id].supabase.co
SUPABASE_ANON_KEY=[anon-key]
SUPABASE_SERVICE_KEY=[service-key]

# JWT (generate secure secrets)
JWT_SECRET=$(openssl rand -base64 32)
JWT_ALGORITHM=HS256

# External APIs (sign up for free tiers)
FLATPEAK_API_KEY=[sign up at flatpeak.energy]
NREL_API_KEY=[sign up at developer.nrel.gov]
IEA_API_KEY=[sign up at iea.org]

# Redis (use Redis Cloud free tier)
REDIS_URL=redis://[username]:[password]@[host]:6379

# Airflow
AIRFLOW_FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Monitoring
GRAFANA_PASSWORD=$(openssl rand -base64 16)

# Environment
NODE_ENV=production
ENVIRONMENT=beta
```

### Step 2: Deploy Backend to Railway

```bash
# 1. Create Railway project
cd ~/projects/electricity-optimizer
railway init

# 2. Create backend service
railway add

# 3. Link to GitHub (auto-deploy on push)
railway link

# 4. Add environment variables
cat .env.production | while read line; do
  key=$(echo $line | cut -d'=' -f1)
  value=$(echo $line | cut -d'=' -f2)
  railway variables set $key="$value"
done

# 5. Deploy
git push railway main

# 6. Get backend URL
railway domain
# Save this as BACKEND_URL for frontend
```

### Step 3: Deploy Frontend to Vercel

```bash
# 1. Install Vercel CLI
npm i -g vercel

# 2. Login
vercel login

# 3. Link project
cd frontend
vercel link

# 4. Set environment variables
vercel env add NEXT_PUBLIC_API_URL production
# Enter: https://[backend-url]

vercel env add NEXT_PUBLIC_SUPABASE_URL production
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY production

# 5. Deploy
vercel --prod

# 6. Get frontend URL
vercel inspect [deployment-url]
```

### Step 4: Deploy ML/Airflow to Railway

```bash
# 1. Create ML service
railway add --service ml

# 2. Deploy Airflow
railway add --service airflow

# 3. Set environment variables
railway variables set --service airflow AIRFLOW_FERNET_KEY="$AIRFLOW_FERNET_KEY"

# 4. Initialize Airflow database
railway run --service airflow airflow db init
railway run --service airflow airflow users create \
    --username admin \
    --password admin123 \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com

# 5. Start scheduler
railway up --service airflow
```

### Step 5: Set Up Monitoring

```bash
# 1. Create monitoring service on Railway
railway add --service monitoring

# 2. Deploy Prometheus + Grafana
railway up --service monitoring

# 3. Configure Grafana
# Visit https://[monitoring-url]:3001
# Login: admin / [GRAFANA_PASSWORD from .env]

# 4. Import dashboards
# Dashboards → Import → monitoring/grafana/dashboards/overview.json
```

### Step 6: Configure Custom Domain (Optional)

```bash
# Frontend (Vercel)
vercel domains add electricity-optimizer.app
# Follow DNS instructions

# Backend (Railway)
railway domain add api.electricity-optimizer.app
# Update frontend env: NEXT_PUBLIC_API_URL
```

### Step 7: Verify Deployment

```bash
# Health checks
curl https://api.electricity-optimizer.app/health
curl https://electricity-optimizer.app

# Test API endpoints
curl https://api.electricity-optimizer.app/api/v1/prices/current?region=UK

# Check logs
railway logs --service backend
railway logs --service frontend
railway logs --service airflow

# Monitor metrics
# Visit: https://[monitoring-url]:3001
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
1. Check Airflow DAG status
2. Verify ML model deployed
3. Check TimescaleDB connection

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
- **Database**: 500MB (Supabase free tier)
- **Redis**: 30MB (Redis Cloud free)
- **Cost**: $11/month

### Scaling Triggers

**At 100 users**:
- Monitor database size
- Watch Redis memory usage
- Track API latency

**At 500 users**:
- Upgrade Supabase to Pro ($25/month)
- Upgrade Redis to paid tier ($5/month)
- Add load balancer
- **Estimated cost**: $41/month

**At 1000 users**:
- Scale Railway instances (2x)
- Upgrade database to 2GB
- Implement CDN (Cloudflare)
- **Estimated cost**: $75/month

**At 5000 users**:
- Multi-region deployment
- Database read replicas
- Auto-scaling groups
- **Estimated cost**: $200-300/month

---

## Rollback Procedure

### If Critical Issues Occur

**Immediate Response** (within 5 minutes):

```bash
# 1. Stop accepting new traffic
railway scale --service backend --replicas 0

# 2. Notify users
# Send status email: "We're experiencing issues, investigating..."

# 3. Check last known good version
git log --oneline

# 4. Rollback
git checkout [previous-stable-commit]
git push railway main --force

# 5. Restore database if needed
./scripts/restore.sh [backup-timestamp]

# 6. Verify rollback
make health
make smoke-test

# 7. Resume traffic
railway scale --service backend --replicas 2

# 8. Send all-clear
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
# Deploy to production
make deploy-production

# Check health
make health

# View logs
railway logs --service backend
railway logs --service frontend

# Scale services
railway scale --service backend --replicas 2

# Database backup
./scripts/backup.sh

# Rollback
git checkout [previous-commit]
make deploy-production

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

**Last Updated**: 2026-02-06
**Deployment Status**: Ready for beta
**Current Users**: 0 (pre-launch)
**Target Users**: 50+ (week 1)

**Next Steps**:
1. ✅ Complete deployment checklist
2. 🟡 Recruit beta users
3. 🔴 Deploy to production
4. 🔴 Send welcome emails
5. 🔴 Monitor and iterate
