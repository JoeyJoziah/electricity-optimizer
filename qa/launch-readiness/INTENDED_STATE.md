# INTENDED STATE — Launch-Ready RateShift

> Phase 1 | Generated: 2026-03-23
> Sources: LAUNCH_CHECKLIST.md, MVP_LAUNCH_CHECKLIST.md, PRODUCT_HUNT.md, CAPACITY_AUDIT.md, MONITORING_RUNBOOK.md, full-gap-remediation PRD, whats-next-roadmap.md

---

## 1. Core Product Features

### 1.1 Authentication & Onboarding
- Email signup with verification (magic link + email/password)
- OAuth: GitHub + Google fully functional
- Password reset flow (forgot-password, reset-password pages)
- Onboarding wizard: region, utility type, supplier, annual usage
- Post-signup redirect to dashboard
- Session expiry UX with toast + redirect preservation

### 1.2 Dashboard
- Multi-utility tabs (Electricity, Natural Gas, Heating Oil, Propane, Community Solar, Water)
- All tabs render real dashboards (no "coming soon" placeholders)
- Real-time data from API (no hardcoded/mock data)
- Setup checklist with dynamic status from user state
- Savings tracking with computed data (SavingsService)
- Loading skeletons on all data-fetching areas

### 1.3 Price Monitoring & Forecasting
- Real-time electricity prices via SSE streaming
- ML-powered 24hr price forecasts (ensemble predictor)
- Weather-aware predictions
- Historical price data with filtering (supplier, peak, date range)
- Price analytics (statistics, optimal windows, trends, peak hours)

### 1.4 Supplier Comparison & Switching
- Real supplier data from database (not hardcoded tariffs)
- Tariff comparison with contract details
- Switching wizard (4-step flow with GDPR consent)
- Supplier filtering by region

### 1.5 Connections
- Bill upload flow (functional)
- UtilityAPI OAuth flow (functional)
- Email connection flow (functional for Pro/Business, graceful gate for Free)
- Direct login connection flow (functional for supported utilities)
- Portal scraping (5 utilities supported)
- Connection analytics with rate display

### 1.6 Alerts & Notifications
- Price threshold alerts with configurable region/thresholds
- Alert CRUD (create, read, update, delete)
- Alert history
- Email notifications (Resend primary + Gmail SMTP fallback)
- In-app notification bell with unread count
- Push notifications via OneSignal
- Dedup cooldowns (immediate=1h, daily=24h, weekly=7d)

### 1.7 AI Agent
- Conversational AI assistant at `/assistant`
- SSE streaming responses
- Gemini primary + Groq fallback
- Composio tool actions
- Per-tier rate limits (Free=3/day, Pro=20, Business=unlimited)
- Graceful degradation on provider failure

### 1.8 Community
- Community posts with voting
- AI content moderation (Groq primary, Gemini fallback)
- Report system with auto-hide threshold
- XSS sanitization (nh3)

### 1.9 Optimization
- Load optimization with appliance scheduling
- Optimal time window calculation from forecast data
- Smart schedule recommendations

### 1.10 Billing
- Stripe integration (Free/$4.99 Pro/$14.99 Business)
- Tier-gated features via `require_tier()`
- Dunning service with escalation emails
- Payment retry history tracking
- Pricing page with correct tiers and CTAs

---

## 2. User Experience Standards

### 2.1 Error Handling
- Every route has `error.tsx` boundary (contextual error + retry)
- Every app route has `loading.tsx` skeleton
- Toast notifications for all mutations (success/error/warning/info)
- No silent failures on any user action
- Confirmation modals for destructive actions

### 2.2 Brand Consistency
- "RateShift" branding everywhere user-facing
- Zero "Electricity Optimizer" references visible to users
- Consistent Zap icon + blue-600 color scheme
- Legal pages (terms, privacy) branded and dated

### 2.3 Responsive & Accessible
- Mobile responsive (375px, 768px, 1024px+)
- WCAG 2.1 AA compliance
- Keyboard navigation
- Screen reader compatible (aria-labels, roles)
- Color contrast AA 4.5:1 minimum

### 2.4 No Beta Artifacts
- No beta signup page accessible in production
- No "beta" language visible to public users
- No "coming soon" placeholders on shipped features

---

## 3. Security Posture

### 3.1 Authentication
- Session-based auth (Better Auth / Neon Auth)
- HttpOnly, Secure, SameSite=Strict cookies
- OAuth state tokens with HMAC-SHA256 + 10-min expiry
- Login attempt tracking with lockout
- Email verification required

### 3.2 Authorization
- Tier gating on premium endpoints
- User data isolation (userId filters on all queries)
- Internal endpoints require X-API-Key
- Swagger/ReDoc disabled in production

### 3.3 Infrastructure Security
- CSP headers (accept `unsafe-inline` with mitigations documented)
- HSTS, X-Frame-Options, X-Content-Type-Options
- 3-tier rate limiting (CF Worker edge + Redis backend + application)
- OWASP ZAP weekly scans
- pip-audit + npm audit in CI
- Secret scanning workflow
- HMAC model signing for ML artifacts
- AES-256-GCM encryption for portal credentials

### 3.4 Compliance
- GDPR export + deletion endpoints
- Privacy policy + Terms of Service pages
- Consent tracking with timestamps
- GDPR CASCADE deletes on user removal

---

## 4. Infrastructure Ready

### 4.1 Deployment
- Frontend on Vercel (CDN, auto-deploy)
- Backend on Render (always-on — no cold starts)
- CF Worker gateway (caching, rate limiting, cron triggers)
- All environment variables set and validated
- `FRONTEND_URL` pointing to `https://rateshift.app`

### 4.2 Monitoring & Observability
- OTel distributed tracing to Grafana Cloud Tempo
- UptimeRobot monitoring all endpoints
- Sentry error tracking with Slack bridge
- Self-healing CI monitor (auto-creates issues after 3+ failures)
- Grafana dashboards for latency, cache, DB, ML, errors

### 4.3 Email Delivery
- Sufficient capacity for launch-day volume (~600+ emails/day)
- Resend primary + Gmail SMTP fallback
- Domain verified (DKIM/SPF/DMARC)

### 4.4 CI/CD
- 33 GHA workflows operational
- Self-healing monitor, retry-curl, notify-slack
- Migration validation in deploy pipeline
- Sufficient GHA minutes for launch week

### 4.5 Database
- All migrations deployed and verified
- Indexes optimized for query patterns
- Backup strategy active (Neon point-in-time recovery)
- Connection pooling configured

---

## 5. Documentation & Launch Materials

### 5.1 Launch Materials
- Product Hunt page materials (taglines, descriptions, screenshots)
- HN/Reddit post templates
- Email templates for beta users, friends, advisors
- Social media post templates (7+ tweets, LinkedIn, etc.)
- Launch day hour-by-hour plan

### 5.2 Operations
- Monitoring runbook with per-service thresholds
- Emergency playbooks (email quota, cold starts, AI rate limits)
- Capacity audit with 3-scenario modeling
- Escalation process documented

### 5.3 Analytics
- GA4 event tracking configured (signup, login, forecast, switch, upgrade)
- Conversion funnels set up
- Real-time metrics dashboard
- Pre-launch baseline metrics established

### 5.4 Checklist
- Launch checklist systematically walked through and items verified
- All items checked off or documented as N/A with rationale

---

## 6. Success Metrics (PH Launch)

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
