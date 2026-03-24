# CURRENT STATE — RateShift as of 2026-03-24 (v2)

> Generated: 2026-03-24 | Supersedes: 2026-03-23 version
> Sources: Codebase inspection, CLAUDE.md, test results, deployment verification
> Note: 7 code gaps from v1 analysis were fixed in 2026-03-23 sprint

---

## 1. Core Product Features

### 1.1 Authentication & Onboarding
| Feature | Status | Evidence |
|---------|--------|----------|
| Email signup + verification | WORKING | `auth/signup/page.tsx`, `auth/verify-email/page.tsx`, Better Auth |
| GitHub OAuth | WORKING | App ID 3466397, creds on Render + Vercel + 1Password |
| Google OAuth | **BROKEN** | Client ID exists but **secret never captured** from GCP. Placeholder on Render |
| Password reset flow | WORKING | `auth/forgot-password/page.tsx`, `auth/reset-password/page.tsx` |
| Onboarding wizard | WORKING | `(app)/onboarding/page.tsx` |
| Session expiry UX | WORKING | 401 handling in API client |

### 1.2 Dashboard
| Feature | Status | Evidence |
|---------|--------|----------|
| Multi-utility tabs | WORKING | DashboardTabs.tsx: 7 tabs |
| Electricity dashboard | WORKING | `DashboardContent` in `UtilityTabShell` |
| Natural Gas dashboard | WORKING | Fixed 2026-03-23 (LG-002) — `GasRatesContent` added to `UTILITY_DASHBOARDS` |
| Heating Oil dashboard | WORKING | `HeatingOilDashboard` |
| Propane dashboard | WORKING | `PropaneDashboard` |
| Water dashboard | WORKING | `WaterDashboard` |
| Community Solar dashboard | WORKING | `CommunitySolarContent` |
| Setup checklist | WORKING | `useConnections()` wired |
| Real data (no hardcoded) | CONFIRMED | Zero mock/hardcoded matches in dashboard |

### 1.3 Price Monitoring & Forecasting
| Feature | Status | Evidence |
|---------|--------|----------|
| Real-time prices (SSE) | WORKING | `useRealtimePrices`, exponential backoff |
| ML forecasts | WORKING | Ensemble predictor, 676 ML tests |
| Weather-aware predictions | WORKING | `weather_service.py` with circuit breaker |
| Price analytics | WORKING | `/prices/analytics/*` endpoints |

### 1.4 Supplier Comparison & Switching
| Feature | Status | Evidence |
|---------|--------|----------|
| Supplier data from DB | WORKING | Queries `tariffs` table |
| Switching flow | WORKING | E2E tested |
| Region filtering | WORKING | Region-based API filtering |

### 1.5 Connections
| Feature | Status | Evidence |
|---------|--------|----------|
| Bill upload | WORKING | All 5 types repaired 2026-03-16 |
| UtilityAPI OAuth | WORKING | HMAC state tokens |
| Email connection | GRACEFUL | Shows "temporarily unavailable" on 503 (LG-003 fix) |
| Direct login | GRACEFUL | Shows "temporarily unavailable" on 503 (LG-004 fix) |
| Portal scraping | WORKING | 5 utilities |
| Connection analytics | WORKING | ConnectionAnalytics component |

### 1.6 Alerts & Notifications
| Feature | Status | Evidence |
|---------|--------|----------|
| Alert CRUD + history | WORKING | `/alerts` page, AlertForm, API routes |
| Email notifications | WORKING | Resend + Gmail SMTP fallback |
| In-app notifications | WORKING | notification_service.py, bell icon |
| Push (OneSignal) | WORKING | push_notification_service.py |
| CF Worker cron (3h) | WORKING | check-alerts cron trigger |

### 1.7 AI Agent
| Feature | Status | Evidence |
|---------|--------|----------|
| Conversational AI | WORKING | `/assistant`, AgentChat |
| SSE streaming | WORKING | `POST /agent/query` |
| Gemini + Groq failover | WORKING | Auto-fallback on 429 |
| Tier rate limits | WORKING | Free=3/day, Pro=20, Business=unlimited |

### 1.8 Community
| Feature | Status | Evidence |
|---------|--------|----------|
| Posts + voting | WORKING | `/community` page |
| AI moderation | WORKING | Groq → Gemini fallback, fail-closed |
| Report system | WORKING | 5 reporters auto-hides |

### 1.9 Billing
| Feature | Status | Evidence |
|---------|--------|----------|
| Stripe tiers | WORKING | Free/$4.99 Pro/$14.99 Business |
| Tier gating | WORKING | `require_tier()` on 7+ endpoints |
| Dunning | WORKING | Daily 7am cron + email templates |
| Pricing page | WORKING | Correct tiers, CTAs |

---

## 2. User Experience

### 2.1 Error & Loading Coverage
| Metric | Count | Notes |
|--------|-------|-------|
| page.tsx (routes) | 28 | Beta-signup deleted in LG-008 sprint |
| error.tsx | 28 | Root + app layout + all app/auth/public routes |
| loading.tsx | 22 | All app + auth routes. **Missing**: pricing, privacy, terms, rates/[state]/[utility] (static pages — acceptable gap) |

### 2.2 Brand
| Check | Status |
|-------|--------|
| "RateShift" everywhere user-facing | CLEAN |
| No beta artifacts | CLEAN — beta-signup page deleted (LG-008) |
| Legal pages (terms, privacy) | Branded, dated Feb 12 2026 |
| `window.confirm` replaced | YES — custom Modal used for account deletion (LG-007) |

### 2.3 SEO & Social
| Feature | Status | Evidence |
|---------|--------|----------|
| Root metadata | WORKING | Title template, description, keywords, OG, Twitter card |
| **OG image** | **MISSING** | layout.tsx has `openGraph` but no `images` property; no `og-*.png` in public/ |
| robots.ts | WORKING | Disallows /api/, /dashboard/, /settings/, /onboarding/ |
| sitemap.ts | **ISSUE** | Includes /dashboard (protected route — search engines can't access) |
| Programmatic rate pages | WORKING | 50 states x N utilities |
| PWA manifest | WORKING | manifest.json, service worker, install prompt |

### 2.4 Analytics
| Feature | Status | Evidence |
|---------|--------|----------|
| Microsoft Clarity | WORKING | `lib/analytics/clarity` |
| **GA4** | **NOT CONFIGURED** | Zero matches for gtag/GA4 in frontend |

---

## 3. Security

| Area | Status | Evidence |
|------|--------|----------|
| Session auth (Better Auth) | WORKING | HttpOnly, Secure, SameSite=Strict |
| OAuth state HMAC | WORKING | 5-part, 10-min expiry |
| Tier gating | WORKING | `require_tier()` dependency |
| CSP | ACCEPTED RISK | `unsafe-inline` documented |
| 3-tier rate limiting | WORKING | CF Worker + Redis + application |
| OWASP ZAP | WORKING | Weekly Sunday 4am |
| pip-audit + npm audit | WORKING | In CI |
| HMAC model signing | WORKING | ML_MODEL_SIGNING_KEY set |
| AES-256-GCM encryption | WORKING | Portal credentials |
| GDPR | WORKING | Export + deletion + CASCADE |

---

## 4. Infrastructure

### 4.1 Deployment Status
| Component | Status | Details |
|-----------|--------|---------|
| Frontend (Vercel) | DEPLOYED | `rateshift.app`, auto-deploy on push |
| Backend (Render) | DEPLOYED | `api.rateshift.app`, commit 74795a5 |
| CF Worker | DEPLOYED | 3 cron triggers, native rate limiting |
| **FRONTEND_URL** | **NOT SET** | Defaults to `http://localhost:3000` — **P0 BLOCKER** |
| **Render tier** | **FREE** | Auto-sleeps 15min, 20-30s cold starts |
| **Resend tier** | **FREE** | 100 emails/day cap |

### 4.2 Environment Variables (Render: 44 total)
| Category | Status |
|----------|--------|
| 34 core + 4 AI + 3 OTel + FRONTEND_URL default + OAUTH_STATE_SECRET + ML_MODEL_SIGNING_KEY | SET |
| **FRONTEND_URL** | **NOT SET** (defaults localhost:3000) |
| **GOOGLE_CLIENT_ID/SECRET** | **PLACEHOLDER** |
| **UTILITYAPI_KEY** | **MISSING** |
| **GMAIL_CLIENT_ID/SECRET** | **MISSING** |
| **OUTLOOK_CLIENT_ID/SECRET** | **MISSING** |

### 4.3 Monitoring
| Component | Status |
|-----------|--------|
| OTel → Grafana Cloud Tempo | WORKING |
| UptimeRobot | WORKING |
| Sentry → Slack | WORKING |
| Self-healing CI monitor | WORKING |
| **Status page** | **NOT CREATED** |

### 4.4 Database
| Metric | Value |
|--------|-------|
| Tables | 58 (49 public + 9 neon_auth) |
| Migrations | 63 (through 063_migration_history) |
| All deployed | YES |
| Backup | Neon point-in-time recovery |

### 4.5 CI/CD
| Metric | Value |
|--------|-------|
| GHA workflows | 33 |
| CF Worker crons | 3 |
| Est. GHA min/mo | ~1,283 (within 2,000 free limit) |

### 4.6 Background Processing
| Feature | Status |
|---------|--------|
| Job queue (arq/celery) | NOT IMPLEMENTED |
| Bill uploads | Synchronous |
| Email scanning | Cron-triggered |

---

## 5. Tests

| Suite | Count | Status |
|-------|-------|--------|
| Backend (pytest) | 2,976 | Passing |
| Frontend (jest) | 2,015 (153 suites) | Passing |
| E2E (Playwright) | 1,605 (25 specs, 5 browsers) | Passing |
| ML | 676 | Passing |
| CF Worker | 90 | Passing |
| **Total** | **~7,362** | All passing |

TODOs: 2 in `authentication.spec.ts` (magic link, constraint validation)

---

## 6. Documentation & Launch Materials

| Document | Status |
|----------|--------|
| PH launch materials | READY (615 lines) |
| HN/Reddit posts | READY |
| Monitoring runbook | READY (846 lines) |
| Capacity audit | READY |
| Launch checklist | PARTIALLY WALKED (LG-014 complete; marketing/content unchecked) |
| **GA4 analytics** | **NOT CONFIGURED** |
| **Status page** | **NOT CREATED** |
| **Content assets** (screenshots, video, hero) | **NOT CREATED** |
| **Social accounts** | **NOT VERIFIED** |

---

## 7. Registries & Orchestration

| System | Status |
|--------|--------|
| MASTER_TODO_REGISTRY | 47 tasks, launch gaps tracked |
| Conductor tracks | 18/18 complete |
| DSP graph | 474 entities, 940+ imports |
| Board sync | GitHub Projects #4 + Notion (6h) |
