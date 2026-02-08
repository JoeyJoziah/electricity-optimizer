# 🚀 LIVE DEPLOYMENT TRACKING

**Started**: 2026-02-07
**Platform**: Vercel (Frontend) + Railway (Backend)
**Target Cost**: $11/month
**Status**: IN PROGRESS

---

## ✅ Prerequisites Checklist

### Tools Installed
- [x] Docker
- [x] Railway CLI (`npm install -g @railway/cli`)
- [x] Vercel CLI (`npm install -g vercel`)

### Accounts Needed
- [ ] Supabase account (free tier) - https://supabase.com
- [ ] Railway account (paid) - https://railway.app
- [ ] Vercel account (free tier) - https://vercel.com
- [ ] Flatpeak API key (UK prices) - https://flatpeak.com
- [ ] NREL API key (US prices) - https://developer.nrel.gov
- [ ] IEA API key (optional) - https://iea.org

---

## 📋 Deployment Steps

### Step 1: Supabase Setup (5 min)
- [ ] Create account at https://supabase.com
- [ ] Create new project: "electricity-optimizer"
- [ ] Copy project URL (Settings → API)
- [ ] Copy anon key (Settings → API)
- [ ] Copy service_role key (Settings → API)

**Notes**:
```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...
SUPABASE_SERVICE_KEY=eyJhbGc...
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

- [ ] Generate Postgres password:
```bash
openssl rand -hex 16
```
Copy: `POSTGRES_PASSWORD=xxx`

### Step 4: Railway Deployment (10 min)
- [ ] Login: `railway login`
- [ ] Create project: `railway init`
- [ ] Add PostgreSQL: `railway add -d postgresql`
- [ ] Add Redis: `railway add -d redis`
- [ ] Configure environment variables
- [ ] Deploy backend: `railway up`
- [ ] Copy backend URL

### Step 5: Vercel Deployment (5 min)
- [ ] Login: `vercel login`
- [ ] Deploy frontend: `vercel --prod`
- [ ] Configure environment variables
- [ ] Copy frontend URL

### Step 6: Verification (5 min)
- [ ] Test backend health: `curl https://backend-url.railway.app/health`
- [ ] Test frontend: Open frontend URL in browser
- [ ] Test API: Try dashboard
- [ ] Check logs: `railway logs`

### Step 7: Beta Signup (1 min)
- [ ] Navigate to: `https://your-frontend-url.vercel.app/beta-signup`
- [ ] Test signup flow
- [ ] Verify welcome email sent

---

## 🔑 Environment Variables Template

Create `.env.production` with these values:

```env
# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_KEY=

# API Keys
FLATPEAK_API_KEY=
NREL_API_KEY=
IEA_API_KEY=

# Security
JWT_SECRET=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Database (Railway will provide)
DATABASE_URL=
REDIS_URL=

# Passwords
REDIS_PASSWORD=
POSTGRES_PASSWORD=

# Frontend (Vercel will provide)
NEXT_PUBLIC_API_URL=
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

---

## 📊 Deployment Status

### Backend (Railway)
- Status: ⏳ Pending
- URL: Not deployed yet
- Services: FastAPI, PostgreSQL, Redis, Airflow

### Frontend (Vercel)
- Status: ⏳ Pending
- URL: Not deployed yet
- Framework: Next.js 14

### Cost Tracking
- Railway: $5/month (backend + ML)
- Vercel: $0/month (free tier)
- Supabase: $0/month (free tier)
- Redis Cloud: $0/month (free tier via Railway)
- **Total**: $5-11/month

---

## 🚨 Common Issues

### Railway Deployment Fails
- Check Dockerfile paths
- Verify environment variables
- Check Railway logs: `railway logs`

### Frontend Can't Connect to Backend
- Verify NEXT_PUBLIC_API_URL is correct
- Check CORS settings in backend
- Verify backend is running: `curl backend-url/health`

### Database Connection Issues
- Check DATABASE_URL format
- Verify PostgreSQL is running on Railway
- Check connection limits

---

## 🎯 Success Criteria

- [ ] Backend responding at /health endpoint
- [ ] Frontend loads without errors
- [ ] Can sign up for beta at /beta-signup
- [ ] Dashboard displays mock data
- [ ] API endpoints return 200 OK
- [ ] Monitoring dashboards accessible
- [ ] Cost under $15/month

---

**Last Updated**: 2026-02-07
**Next Step**: Set up Supabase account
