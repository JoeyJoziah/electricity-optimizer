# DISCOVERY SUMMARY — RateShift Launch-Gap Analysis

> Generated: 2026-03-23 | Phase 0 of 5 | Source: Full codebase + docs + orchestrator state

---

## 1. Sources Ingested

| Source | Count | Key Findings |
|--------|-------|--------------|
| **Docs (plans, launch, security)** | 80+ files | Roadmap (5 sprints done), capacity audit, monitoring runbook, PH/HN launch materials |
| **CLAUDE.md (project root)** | 1 | 44 Render env vars, 58 tables, 63 migrations, 33 GHA workflows, 18 conductor tracks |
| **MASTER_TODO_REGISTRY** | 28 tasks | All 28 marked "completed" across 7 epics |
| **Conductor tracks** | 19 dirs | All 19 tracks marked complete (audit-remediation x4, dependency-upgrade, verification-gates, etc.) |
| **Loki PRDs** | 5 PRDs | Full-gap-remediation PRD (Feb 25) — many items since resolved |
| **Frontend routes** | 29 page.tsx | 23 loading.tsx, 29 error.tsx — good boundary coverage |
| **Backend services** | 51 files | Full service layer for alerts, billing, connections, ML, agent, community, etc. |
| **Backend API routes** | 38 files | v1 API fully wired |
| **GHA workflows** | 32 files | 3 cron triggers on CF Worker, 12+ cron workflows, self-healing monitor |
| **Codebase TODOs** | 3 total | 1 backend (FRONTEND_URL Render), 2 frontend E2E (magic link auth, constraint validation) |

---

## 2. Brand Consistency

| Check | Status |
|-------|--------|
| Frontend source code | **CLEAN** — Only 2 "Electricity Optimizer" refs remain: `types/index.ts` comment (line 2), `DirectLoginForm.test.tsx` comment (line 105). Both are code comments, not user-facing |
| Legal pages (terms, privacy) | **CLEAN** — Both branded "RateShift", dated Feb 12 2026 |
| Pricing page | **CLEAN** — "RateShift" branding, correct tier pricing ($0/Free, $4.99/Pro, $14.99/Business) |
| `manifest.ts` / metadata | Verified "RateShift" in prior Sprint 0 brand sweep |

---

## 3. Route & Boundary Coverage

### App Routes (29 pages)
- `(app)/`: dashboard, prices, connections, alerts, suppliers, optimize, analytics, assistant, community, settings, onboarding, beta-signup, gas-rates, heating-oil, propane, community-solar, water
- `(auth)/`: login, signup, callback, forgot-password, reset-password, verify-email
- Public: terms, privacy, pricing, rates/[state]/[utility], home (/)
- Dev: (dev)/architecture (blocked in production via middleware)

### Error Boundaries: 29 error.tsx files
- Every `(app)/*` route has error.tsx
- Every `(auth)/*` route has error.tsx
- Public routes (terms, privacy, pricing, rates) have error.tsx
- Root error.tsx exists
- Layout-level `(app)/error.tsx` catches uncaught app errors

### Loading States: 23 loading.tsx files
- All `(app)/*` routes covered
- All `(auth)/*` routes covered
- **GAP**: No loading.tsx for `terms/`, `privacy/`, `pricing/`, `rates/[state]/[utility]/` — acceptable (static/SSG pages)

---

## 4. Dashboard & Data Wiring

| Component | Status | Notes |
|-----------|--------|-------|
| DashboardTabs | **WIRED** | Multi-utility tab bar with dynamic tabs from user settings |
| DashboardContent (electricity) | **WIRED** | Lazy-loaded, primary utility |
| HeatingOilDashboard | **WIRED** | Lazy-loaded in UtilityTabShell |
| PropaneDashboard | **WIRED** | Lazy-loaded in UtilityTabShell |
| WaterDashboard | **WIRED** | Lazy-loaded in UtilityTabShell |
| CommunitySolarContent | **WIRED** | Lazy-loaded in UtilityTabShell |
| **Natural Gas tab** | **PLACEHOLDER** | `natural_gas` key exists in DashboardTabs but NOT in `UTILITY_DASHBOARDS` map → shows "Dashboard coming soon" |
| SetupChecklist | **WIRED** | `useConnections()` hook wired for dynamic status (Sprint 0.2 fix) |
| No hardcoded/mock data in dashboard | **CONFIRMED** | Grep for hardcoded/static/sample/demo returned zero matches |

---

## 5. Infrastructure & Env Var Status

### Render Backend (44 env vars)
| Env Var | Status |
|---------|--------|
| FRONTEND_URL | **NOT SET** — still `http://localhost:3000` default. Must be `https://rateshift.app` |
| GOOGLE_CLIENT_ID | **PLACEHOLDER** — secret not captured from GCP |
| GOOGLE_CLIENT_SECRET | **PLACEHOLDER** — secret not captured from GCP |
| UTILITYAPI_KEY | **MISSING** — needed for utility data connections |
| GMAIL_CLIENT_ID/SECRET | **MISSING** — needed for email scanning feature |
| OUTLOOK_CLIENT_ID/SECRET | **MISSING** — needed for Outlook email scanning |
| OAUTH_STATE_SECRET | SET (2026-03-23) |
| ML_MODEL_SIGNING_KEY | SET (2026-03-23) |
| All 34 core + 4 AI + 3 OTel vars | SET |

### Cloudflare Worker
| Item | Status |
|------|--------|
| Worker deployed | **YES** — Version 93c9a1f2, rateshift.workers.dev |
| 3 cron triggers | **ACTIVE** (check-alerts/3h, price-sync/6h, observe-forecasts/6h) |
| KV namespace (CACHE) | Active |
| Rate limiting bindings | Active (native, zero-cost) |

### Free Tier Risks (from Capacity Audit)
| Service | Limit | Launch Risk | Mitigation |
|---------|-------|-------------|------------|
| Render | Free (cold starts) | **HIGH** | keepalive.yml + circuit breaker |
| Resend | 100 emails/day | **MEDIUM** | Gmail SMTP fallback (~600 total/day) |
| Gemini | 250 RPD, 10 RPM | **HIGH** | Auto-fallback to Groq |
| Neon | 100h compute/mo | **LOW** | Monitor, upgrade at 60h |
| Composio | 1,000 actions/mo | **MEDIUM** | Launch day could use 30% |
| GHA | 2,000 min/mo | **LOW** | Current ~1,283 min/mo estimate |

---

## 6. Security & Auth

| Area | Status |
|------|--------|
| GitHub OAuth | **COMPLETE** — App ID 3466397, creds in 1Password + Render + Vercel |
| Google OAuth | **INCOMPLETE** — Client ID exists but secret never captured from GCP |
| CSP | `unsafe-inline` accepted (risk doc: `docs/security/CSP_RISK_ACCEPTANCE.md`) |
| CORS | Configured via CF Worker + backend |
| Rate limiting | 3-tier: CF Worker edge + Redis backend + application-level |
| Swagger/ReDoc | Disabled in production |
| OWASP ZAP | Weekly scan configured |
| pip-audit | In CI pipeline |
| npm audit | In CI pipeline |
| Secret scanning | `secret-scan.yml` workflow |
| Account deletion | Uses `window.confirm()` (native, no custom modal) |

---

## 7. UX / Feature Gaps Found

| Gap | Severity | Location | Detail |
|-----|----------|----------|--------|
| Natural Gas dashboard tab shows "coming soon" | P2 | `UtilityTabShell.tsx:61-74` | `natural_gas` not in `UTILITY_DASHBOARDS` map, but `GasRatesContent` component exists at `/gas-rates` page |
| Beta signup page still accessible | P3 | `(app)/beta-signup/page.tsx` | Posts to `/api/v1/beta/signup` — should be removed or redirected for public launch |
| `window.confirm` for account deletion | P3 | `settings/page.tsx:214` | Native confirm dialog, not custom modal — noted as deferred in roadmap |
| Email/Direct Login connection flows show fallback messages | P2 | `EmailConnectionFlow.tsx:127`, `DirectLoginForm.tsx:163` | "not yet available" messages for email and direct login connections |

---

## 8. Test Coverage Summary

| Suite | Count | Status |
|-------|-------|--------|
| Backend (pytest) | 2,976 | Passing |
| Frontend (jest) | 2,043 (154 suites) | Passing |
| E2E (Playwright) | 1,605 (25 specs, 5 browsers) | Passing |
| ML | 676 | Passing |
| CF Worker | 90 | Passing |
| **Total** | **~7,390** | All passing |

### Skipped Tests
- No `@pytest.mark.skip` found in backend tests (all previously skipped tests were implemented in Sprint 1.4)
- 2 E2E TODOs: `authentication.spec.ts` lines 111, 165 — magic link auth and constraint validation tests

---

## 9. Documentation Readiness

| Doc | Status |
|-----|--------|
| Product Hunt materials | **READY** — `docs/launch/PRODUCT_HUNT.md` (615 lines) |
| HN/Reddit posts | **READY** — `docs/launch/HN_REDDIT_POSTS.md` |
| Monitoring runbook | **READY** — `docs/launch/MONITORING_RUNBOOK.md` (846 lines) |
| Capacity audit | **READY** — `docs/CAPACITY_AUDIT.md` |
| CSP risk acceptance | **READY** — `docs/security/CSP_RISK_ACCEPTANCE.md` |
| Launch checklist | **EXISTS BUT UNCHECKED** — `docs/LAUNCH_CHECKLIST.md` (587 lines, all items unchecked) |
| MVP checklist | **STALE** — `docs/MVP_LAUNCH_CHECKLIST.md` (test counts from 2026-03-04) |

---

## 10. Orchestrator / Registry State

| System | Status |
|--------|--------|
| MASTER_TODO_REGISTRY | 28/28 tasks complete, v2.0.0 |
| Conductor tracks | 19/19 complete |
| Loki CONTINUITY.md | Archived 2026-03-16, no active sessions |
| DSP graph | 474 entities, 940+ imports, 1 real cycle |
| Board sync | GitHub Projects #4 (local hooks), Notion (6h Rube recipe) |

---

## 11. Key Findings Summary

### Blockers (P0)
1. **FRONTEND_URL not set on Render** — Backend defaults to `localhost:3000`, breaking email links, OAuth redirects, CORS in production

### High Priority (P1)
2. **Google OAuth incomplete** — Client secret never captured; Google login non-functional
3. **Render cold starts on free tier** — 20-30s delay kills first impression (keepalive mitigates but not eliminates)
4. **Launch checklist entirely unchecked** — 587-line checklist with no items marked done despite work being complete
5. **Connection features show "not yet available"** — Email and Direct Login connection flows display error messages

### Medium Priority (P2)
6. **Natural Gas dashboard tab placeholder** — Shows "coming soon" even though `GasRatesContent` component exists
7. **Beta signup page still accessible** — Should be removed/redirected for public launch
8. **Missing Render env vars** — UTILITYAPI_KEY, GMAIL/OUTLOOK client IDs/secrets (4 connection types affected)
9. **Resend 100/day email limit** — Could exhaust on launch day (Gmail fallback mitigates)
10. **Gemini 10 RPM bottleneck** — AI queries will hit rate limit quickly under load

### Low Priority (P3)
11. **MVP checklist stale** — Test counts from March 4, significantly outdated
12. **Native `window.confirm` for account deletion** — Works but not polished
13. **2 E2E test TODOs** — Magic link auth and constraint validation tests not implemented
14. **types/index.ts has "Electricity Optimizer" in comment** — Code comment, not user-facing
