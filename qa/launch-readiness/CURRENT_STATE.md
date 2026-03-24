# CURRENT STATE — RateShift as of 2026-03-23

> Phase 2 | Generated: 2026-03-23
> Sources: Codebase inspection, CLAUDE.md, test results, deployment logs

---

## 1. Core Product Features

### 1.1 Authentication & Onboarding
| Feature | Status | Evidence |
|---------|--------|----------|
| Email signup + verification | WORKING | `auth/signup/page.tsx`, `auth/verify-email/page.tsx`, Better Auth wired |
| GitHub OAuth | WORKING | App ID 3466397, creds on Render + Vercel + 1Password |
| Google OAuth | BROKEN | Client ID exists but **secret never captured** from GCP. Placeholder on Render |
| Password reset flow | WORKING | `auth/forgot-password/page.tsx`, `auth/reset-password/page.tsx` exist |
| Onboarding wizard | WORKING | `(app)/onboarding/page.tsx` with region, utility type, supplier steps |
| Session expiry UX | WORKING | 401 handling in API client |

### 1.2 Dashboard
| Feature | Status | Evidence |
|---------|--------|----------|
| Multi-utility tabs | WORKING | DashboardTabs.tsx: 7 tabs (all, electricity, natural_gas, heating_oil, propane, community_solar, water) |
| Electricity dashboard | WORKING | `DashboardContent` wired via `UtilityTabShell` |
| Heating Oil dashboard | WORKING | `HeatingOilDashboard` component exists |
| Propane dashboard | WORKING | `PropaneDashboard` component exists |
| Water dashboard | WORKING | `WaterDashboard` component exists |
| Community Solar dashboard | WORKING | `CommunitySolarContent` component exists |
| **Natural Gas dashboard tab** | **PLACEHOLDER** | `natural_gas` key NOT in `UTILITY_DASHBOARDS` map -> shows "Dashboard coming soon" |
| Setup checklist | WORKING | `useConnections()` wired (Sprint 0.2 fix) |
| Real data (no hardcoded) | CONFIRMED | Grep returned zero hardcoded/mock matches in dashboard |
| Savings tracking | WORKING | `savings_service.py`, `savings_aggregator.py`, `savings.py` API route all exist |

### 1.3 Price Monitoring & Forecasting
| Feature | Status | Evidence |
|---------|--------|----------|
| Real-time prices (SSE) | WORKING | `useRealtimePrices` with `fetchEventSource`, exponential backoff |
| ML forecasts | WORKING | Ensemble predictor, 676 ML tests |
| Weather-aware predictions | WORKING | `weather_service.py` with circuit breaker |
| Price analytics endpoints | WORKING | `/prices/analytics/*` (statistics, optimal-windows, trends, peak-hours) |

### 1.4 Supplier Comparison & Switching
| Feature | Status | Evidence |
|---------|--------|----------|
| Supplier data from DB | WORKING | `suppliers.py` queries `tariffs` table (not hardcoded since audit fix) |
| Tariff comparison | WORKING | `get_supplier_tariffs` reads from DB with `TariffType` enum |
| Switching flow | WORKING | E2E tests exist |
| Supplier filtering | WORKING | Region-based filtering in API |

### 1.5 Connections
| Feature | Status | Evidence |
|---------|--------|----------|
| Bill upload | WORKING | All 5 connection types repaired (2026-03-16) |
| UtilityAPI OAuth | WORKING | HMAC state tokens, callback verified |
| Email connection | PARTIAL | Works for Pro/Business but shows "not yet available" on 503 fallback |
| Direct login | PARTIAL | Shows "not yet available" on 503 fallback |
| Portal scraping | WORKING | 5 utilities (Duke, PG&E, ConEd, ComEd, FPL) |
| Connection analytics | WORKING | ConnectionAnalytics component exists |

### 1.6 Alerts & Notifications
| Feature | Status | Evidence |
|---------|--------|----------|
| Alert CRUD | WORKING | `/alerts` page + AlertForm + API routes |
| Alert history | WORKING | History tab in alerts page |
| Email notifications | WORKING | Resend + Gmail SMTP fallback |
| In-app notifications | WORKING | `notification_service.py`, `notification_repository.py`, `notifications.py` API |
| Push notifications (OneSignal) | WORKING | `push_notification_service.py` exists |
| Alert dedup cooldowns | WORKING | CF Worker cron every 3h |

### 1.7 AI Agent
| Feature | Status | Evidence |
|---------|--------|----------|
| Conversational AI | WORKING | `/assistant` page, `AgentChat` component |
| SSE streaming | WORKING | `POST /agent/query` |
| Gemini + Groq fallback | WORKING | Dual provider with auto-fallback on 429 |
| Composio tools | WORKING | 16 active connections |
| Tier rate limits | WORKING | Free=3, Pro=20, Business=unlimited |

### 1.8 Community
| Feature | Status | Evidence |
|---------|--------|----------|
| Posts + voting | WORKING | `/community` page, `community_service.py` |
| AI moderation | WORKING | Groq primary, Gemini fallback, fail-closed |
| Report system | WORKING | 5 unique reporters auto-hides |

### 1.9 Optimization
| Feature | Status | Evidence |
|---------|--------|----------|
| Load optimization | WORKING | `/optimize` page |
| Appliance scheduling | WORKING | E2E tests confirm form + schedule display |

### 1.10 Billing
| Feature | Status | Evidence |
|---------|--------|----------|
| Stripe integration | WORKING | Free/$4.99 Pro/$14.99 Business |
| Tier gating | WORKING | `require_tier()` on 7+ endpoints |
| Dunning service | WORKING | `dunning-cycle.yml` + email templates |
| Pricing page | WORKING | Correct tiers, CTAs link to signup with `?plan=` param |

---

## 2. User Experience

### 2.1 Error Handling
| Feature | Status | Evidence |
|---------|--------|----------|
| Error boundaries (error.tsx) | **29 files** | Every (app)/*, (auth)/*, and public route covered |
| Loading states (loading.tsx) | **23 files** | All (app)/* and (auth)/* routes. Missing: terms, privacy, pricing (acceptable — static) |
| Toast notifications | WORKING | `toast.tsx`, `toast-context.tsx` exist, wired in root layout |
| Confirmation for destructive actions | PARTIAL | Account deletion uses native `window.confirm`, not custom modal |

### 2.2 Brand Consistency
| Feature | Status | Evidence |
|---------|--------|----------|
| "RateShift" branding | CLEAN | Only 2 refs to "Electricity Optimizer" remain (both code comments, not user-facing) |
| Legal pages | CLEAN | Terms + Privacy branded "RateShift", dated Feb 12 2026 |
| Consistent design | WORKING | Zap icon + blue-600 scheme throughout |

### 2.3 Responsive & Accessible
| Feature | Status | Evidence |
|---------|--------|----------|
| Mobile responsive | WORKING | E2E tests on 5 browsers including mobile |
| WCAG compliance | WORKING | jest-axe accessibility tests |
| Keyboard navigation | WORKING | Tab, Enter, Escape supported |

### 2.4 Beta Artifacts
| Issue | Status | Evidence |
|-------|--------|----------|
| **Beta signup page** | **STILL ACCESSIBLE** | `(app)/beta-signup/page.tsx` posts to `/api/v1/beta/signup` |
| Beta language | MOSTLY CLEAN | No "beta" in main user flows |

---

## 3. Security

| Area | Status | Evidence |
|------|--------|----------|
| Session-based auth | WORKING | Better Auth + Neon Auth |
| OAuth state HMAC | WORKING | 5-part format with 10-min expiry |
| Tier gating | WORKING | `require_tier()` dependency |
| CSP headers | ACCEPTED RISK | `unsafe-inline` documented in `CSP_RISK_ACCEPTANCE.md` |
| Rate limiting (3-tier) | WORKING | CF Worker + Redis + application |
| OWASP ZAP scans | WORKING | Weekly Sunday 4am UTC |
| pip-audit + npm audit | WORKING | In CI pipeline |
| Secret scanning | WORKING | `secret-scan.yml` |
| HMAC model signing | WORKING | `ML_MODEL_SIGNING_KEY` set on Render |
| GDPR compliance | WORKING | Export + deletion endpoints, CASCADE deletes |
| Feature flags | WORKING | `feature_flag_service.py` with DB-backed flags |

---

## 4. Infrastructure

### 4.1 Deployment
| Component | Status | Details |
|-----------|--------|---------|
| Frontend (Vercel) | DEPLOYED | `rateshift.app`, auto-deploy on push |
| Backend (Render) | DEPLOYED | `api.rateshift.app`, srv-d649uhur433s73d557cg |
| CF Worker | DEPLOYED | 3 cron triggers active, v93c9a1f2 |
| **FRONTEND_URL env var** | **NOT SET** | Still defaults to `http://localhost:3000` on Render |
| **Render tier** | **FREE** | Auto-sleeps after 15min idle, 20-30s cold starts |
| **Resend tier** | **FREE** | 100 emails/day cap |

### 4.2 Environment Variables
| Var | Status |
|-----|--------|
| 34 core + 4 AI + 3 OTel + OAUTH_STATE_SECRET + ML_MODEL_SIGNING_KEY | SET |
| FRONTEND_URL | **NOT SET** (defaults to localhost:3000) |
| GOOGLE_CLIENT_ID/SECRET | **PLACEHOLDER** |
| UTILITYAPI_KEY | **MISSING** |
| GMAIL_CLIENT_ID/SECRET | **MISSING** |
| OUTLOOK_CLIENT_ID/SECRET | **MISSING** |

### 4.3 Monitoring
| Component | Status | Evidence |
|-----------|--------|----------|
| OTel tracing | WORKING | Grafana Cloud Tempo |
| UptimeRobot | WORKING | Monitors configured |
| Sentry | WORKING | Error tracking active |
| Self-healing monitor | WORKING | `self-healing-monitor.yml` |
| Slack integration | WORKING | `#incidents`, `#deployments`, `#metrics` channels |

### 4.4 Database
| Metric | Value |
|--------|-------|
| Tables | 58 (49 public + 9 neon_auth) |
| Migrations | 63 (through 063_migration_history) |
| All deployed | YES — verified via Neon MCP |

### 4.5 CI/CD
| Metric | Value |
|--------|-------|
| GHA workflows | 32 |
| CF Worker crons | 3 (check-alerts, price-sync, observe-forecasts) |
| Estimated GHA min/mo | ~1,283 (within 2,000 free limit after optimizations) |

### 4.6 Background Job Queue
| Feature | Status |
|---------|--------|
| Dedicated job queue (arq/celery) | **NOT IMPLEMENTED** |
| Bill uploads | Synchronous (not async 202 pattern) |
| Email scanning | Cron-triggered, not event-driven |

---

## 5. Documentation & Launch Materials

| Document | Status | Notes |
|----------|--------|-------|
| PH launch materials | READY | `docs/launch/PRODUCT_HUNT.md` (615 lines) |
| HN/Reddit posts | READY | `docs/launch/HN_REDDIT_POSTS.md` |
| Monitoring runbook | READY | `docs/launch/MONITORING_RUNBOOK.md` (846 lines) |
| Capacity audit | READY | `docs/CAPACITY_AUDIT.md` |
| **Launch checklist** | **ALL UNCHECKED** | 587-line checklist, zero items marked done |
| **MVP checklist** | **STALE** | Numbers from 2026-03-04 (3,395 tests → now 7,390) |
| GA4 analytics | **NOT CONFIGURED** | No `gtag` or `NEXT_PUBLIC_GA` found in frontend |
| Status page | **NOT CREATED** | `rateshift.statuspage.io` referenced in docs but doesn't exist |

---

## 6. Tests

| Suite | Count | Status |
|-------|-------|--------|
| Backend (pytest) | 2,976 | Passing |
| Frontend (jest) | 2,043 (154 suites) | Passing |
| E2E (Playwright) | 1,605 (25 specs, 5 browsers) | Passing |
| ML | 676 | Passing |
| CF Worker | 90 | Passing |
| **Total** | **~7,390** | All passing |

### Skipped/TODO Tests
- 2 E2E TODOs in `authentication.spec.ts` (magic link, constraint validation)
- No `@pytest.mark.skip` in backend

---

## 7. Registries & Orchestration

| System | Status |
|--------|--------|
| MASTER_TODO_REGISTRY | 28/28 complete |
| Conductor tracks | 19/19 complete |
| DSP graph | 474 entities, 940+ imports |
| Board sync | GitHub Projects #4 + Notion (6h recipe) |
