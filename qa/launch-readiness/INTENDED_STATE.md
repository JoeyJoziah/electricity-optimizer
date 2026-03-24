# INTENDED STATE — Launch-Ready RateShift (v2)

> Generated: 2026-03-24 | Supersedes: 2026-03-23 version
> Sources: LAUNCH_CHECKLIST.md, PRODUCT_HUNT.md, MONITORING_RUNBOOK.md, CAPACITY_AUDIT.md, CLAUDE.md architecture section, Stripe docs, previous gap analysis
> Definition: "Launch-ready" = safe to post on Product Hunt and acquire paying customers

---

## 1. Core Product Features

### 1.1 Authentication & Onboarding
- Email signup with verification flow
- OAuth: GitHub + Google fully functional (both producing real sessions)
- Password reset flow (forgot-password → email → reset-password)
- Onboarding wizard: region, utility type, supplier, annual usage
- Post-signup redirect to dashboard
- Session expiry UX with toast + redirect preservation

### 1.2 Dashboard
- Multi-utility tabs (Electricity, Natural Gas, Heating Oil, Propane, Community Solar, Water)
- All tabs render real dashboards (no "coming soon" placeholders)
- Real-time data from API (no hardcoded/mock data)
- Setup checklist with dynamic status from user connections
- Loading skeletons on all data-fetching areas

### 1.3 Price Monitoring & Forecasting
- Real-time electricity prices via SSE streaming
- ML-powered 24hr price forecasts (ensemble predictor)
- Weather-aware predictions
- Historical price data with filtering
- Price analytics (statistics, optimal windows, trends, peak hours)

### 1.4 Supplier Comparison & Switching
- Real supplier data from database
- Tariff comparison with contract details
- Switching wizard (4-step flow with GDPR consent)
- Region filtering

### 1.5 Connections
- Bill upload flow (primary, functional)
- UtilityAPI OAuth flow (functional when API key available)
- Email connection flow (graceful message when unavailable)
- Direct login connection flow (graceful message when unavailable)
- Portal scraping (5 utilities)
- Connection analytics with rate display

### 1.6 Alerts & Notifications
- Price threshold alerts with configurable parameters
- Alert CRUD + history
- Email notifications (sufficient capacity for launch volume)
- In-app notification bell
- Push notifications via OneSignal
- Dedup cooldowns

### 1.7 AI Agent
- Conversational assistant at `/assistant` with SSE streaming
- Dual-provider with automatic failover
- Per-tier rate limits
- Graceful degradation on provider failure

### 1.8 Community
- Posts with voting, moderation, reporting
- XSS sanitization

### 1.9 Billing
- Stripe: Free / $4.99 Pro / $14.99 Business
- Tier-gated features via `require_tier()`
- Dunning with escalation emails
- Pricing page with correct tiers

---

## 2. User Experience Standards

### 2.1 Error Handling
- Every route has `error.tsx` boundary
- Every app route has `loading.tsx` skeleton
- Toast notifications for mutations
- No silent failures
- Confirmation modals (not native `window.confirm`) for destructive actions

### 2.2 Brand
- "RateShift" branding consistently across all user-facing surfaces
- No "Electricity Optimizer" visible to users
- No beta artifacts (pages, language, placeholders)

### 2.3 SEO & Social
- Root metadata with OG tags, Twitter card, description
- OG image file for social sharing cards (Product Hunt, Twitter, LinkedIn)
- robots.txt disallowing private routes
- sitemap.xml with only publicly accessible routes
- Programmatic rate pages for SEO

### 2.4 Analytics
- GA4 event tracking for key actions (signup, login, forecast, switch, upgrade)
- Conversion funnels configured
- Real-time dashboard for launch-day monitoring

---

## 3. Security Posture

### 3.1 Authentication
- Session-based auth (Better Auth / Neon Auth)
- HttpOnly, Secure, SameSite=Strict cookies
- OAuth state tokens with HMAC-SHA256 + 10-min expiry
- Login attempt tracking
- Email verification required

### 3.2 Authorization
- Tier gating on premium endpoints
- User data isolation (userId on all queries)
- Internal endpoints require X-API-Key
- Swagger/ReDoc disabled in production

### 3.3 Infrastructure Security
- CSP, HSTS, X-Frame-Options headers
- 3-tier rate limiting
- OWASP ZAP + pip-audit + npm audit in CI
- HMAC model signing, AES-256-GCM encryption

### 3.4 Compliance
- GDPR export + deletion endpoints
- Privacy policy + Terms of Service
- Consent tracking, CASCADE deletes

---

## 4. Infrastructure

### 4.1 Deployment
- Frontend on Vercel (auto-deploy, CDN)
- Backend on Render — **always warm** (no 20-30s cold starts for first visitor)
- CF Worker gateway (caching, rate limiting, 3 cron triggers)
- **All environment variables set and validated** — no placeholders, no missing keys
- `FRONTEND_URL = https://rateshift.app` (not localhost)

### 4.2 Monitoring
- OTel distributed tracing to Grafana Cloud
- UptimeRobot on all endpoints
- Sentry → Slack bridge
- Self-healing CI monitor
- Status page accessible to users

### 4.3 Email Capacity
- Sufficient for launch-day: 500+ emails/day minimum
- Resend primary + fallback
- Domain verified (DKIM/SPF/DMARC)

### 4.4 CI/CD
- 33 workflows operational
- Self-healing, retry-curl, notify-slack
- Migration validation before deploy
- Sufficient GHA minutes

### 4.5 Database
- All migrations deployed
- Indexes optimized
- Backup strategy active
- Connection pooling configured

---

## 5. Launch Materials

### 5.1 Product Hunt
- Page materials: taglines, description, maker comment
- Gallery: 4-6 screenshots of key features, hero image, logo (500x500 PNG)
- Optional: demo video (30-60s)
- Hour-by-hour launch plan

### 5.2 Social Media
- HN Show post ready
- Reddit posts for 5 subreddits
- Twitter account active, 7+ launch tweets drafted
- LinkedIn profile updated

### 5.3 Operations
- Monitoring runbook (dashboards, thresholds, playbooks)
- Launch checklist walked through — all applicable items verified
- Capacity audit with scenario modeling
- Escalation process documented

---

## 6. Success Metrics (from LAUNCH_CHECKLIST.md)

| Metric | Target |
|--------|--------|
| PH Upvotes (Day 1) | 250+ |
| PH Comments | 50+ |
| New Signups (Week 1) | 1,000+ |
| Day-7 Retention | 30%+ |
| NPS Score | 50+ |
| System Uptime | 99.8%+ |
| API Latency p95 | <500ms |
| Error Rate | <0.5% |
| Pro Conversions (Week 1) | 30+ |
