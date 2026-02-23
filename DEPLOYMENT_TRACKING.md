# LIVE DEPLOYMENT TRACKING

**Started**: 2026-02-07
**Platform**: Render.com (Frontend static site + Backend web service)
**Target Cost**: $11/month
**Status**: IN PROGRESS

---

## Prerequisites Checklist

### Tools Installed
- [x] Docker
- [x] Render account (render.yaml in repo root)

### Accounts Needed
- [ ] Neon PostgreSQL account (free tier) - https://neon.tech
- [ ] Render account (paid) - https://render.com
- [ ] Flatpeak API key (UK prices) - https://flatpeak.com
- [ ] NREL API key (US prices) - https://developer.nrel.gov
- [ ] IEA API key (optional) - https://iea.org

---

## Deployment Steps

### Step 1: Neon PostgreSQL Setup (5 min)
- [ ] Create account at https://neon.tech
- [ ] Create new project: "electricity-optimizer" (project ID: holy-pine-81107663)
- [ ] Copy connection string from Dashboard
- [ ] Note the branch: main (br-broad-queen-aemirrrs)

**Notes**:
```
DATABASE_URL=postgresql://neondb_owner:***@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
```

### Step 2: API Keys Setup (10 min)
- [ ] **Flatpeak** (UK electricity prices):
  - Register at https://flatpeak.com
  - Get API key from dashboard
  - Copy: `FLATPEAK_API_KEY=fp_xxx`

- [ ] **NREL** (US utility rates):
  - Register at https://developer.nrel.gov/signup
  - Get API key from dashboard
  - Copy: `NREL_API_KEY=xxx`

- [ ] **IEA** (optional, global data):
  - Register at https://iea.org/api
  - Copy: `IEA_API_KEY=xxx`

### Step 3: Generate Secrets (1 min)
- [ ] Generate JWT secret:
```bash
openssl rand -hex 32
```
Copy: `JWT_SECRET=xxx`

- [ ] Generate Redis password:
```bash
openssl rand -hex 16
```
Copy: `REDIS_PASSWORD=xxx`

### Step 4: Render.com Deployment (10 min)
- [ ] Push code to GitHub (Render deploys from repo)
- [ ] Create new Web Service on Render Dashboard for backend
- [ ] Render auto-detects `render.yaml` blueprint
- [ ] Configure environment variables in Render Dashboard
- [ ] Deploy backend web service
- [ ] Copy backend URL (e.g., `https://electricity-optimizer-api.onrender.com`)

### Step 5: Render.com Static Site Deployment (5 min)
- [ ] Create new Static Site on Render Dashboard for frontend
- [ ] Set build command: `cd frontend && npm install && npm run build`
- [ ] Set publish directory: `frontend/out` or `frontend/.next`
- [ ] Configure environment variables (NEXT_PUBLIC_API_URL)
- [ ] Copy frontend URL (e.g., `https://electricity-optimizer.onrender.com`)

### Step 6: Verification (5 min)
- [ ] Test backend health: `curl https://electricity-optimizer-api.onrender.com/health`
- [ ] Test frontend: Open frontend URL in browser
- [ ] Test API: Try dashboard
- [ ] Check logs in Render Dashboard

### Step 7: Beta Signup (1 min)
- [ ] Navigate to: `https://electricity-optimizer.onrender.com/beta-signup`
- [ ] Test signup flow
- [ ] Verify welcome email sent

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

# Email (SendGrid primary)
SENDGRID_API_KEY=
# Email (SMTP fallback)
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
EMAIL_FROM_ADDRESS=noreply@electricity-optimizer.app
# ML Model
MODEL_PATH=

# Security
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
- Status: Pending
- URL: Not deployed yet
- Services: FastAPI, Redis (via render.yaml)
- Database: Neon PostgreSQL (serverless, external)

### Frontend (Render.com Static Site)
- Status: Pending
- URL: Not deployed yet
- Framework: Next.js 14

### Cost Tracking
- Render.com: $7/month (backend web service)
- Render.com: $0/month (static site, free tier)
- Neon PostgreSQL: $0/month (free tier, 0.5 GB)
- Redis Cloud: $0/month (free tier via Render)
- **Total**: $7-11/month

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

- [ ] Backend responding at /health endpoint
- [ ] Frontend loads without errors
- [ ] Can sign up for beta at /beta-signup (welcome email sends via SendGrid/SMTP)
- [ ] Dashboard displays mock data
- [ ] API endpoints return 200 OK
- [ ] Monitoring dashboards accessible
- [ ] Cost under $15/month

---

**Last Updated**: 2026-02-23
**Next Step**: Set up Neon PostgreSQL account and configure Render.com services
