# CURRENT vs INTENDED MATRIX — RateShift Launch Readiness

> Phase 3 | Generated: 2026-03-23

---

## Legend

| Symbol | Meaning |
|--------|---------|
| :white_check_mark: | Matches intended state |
| :warning: | Partial — works but has gaps |
| :x: | Not matching intended state |
| N/A | Not applicable for launch |

---

## Domain 1: Authentication & Onboarding

| Intended | Current | Gap? | ID |
|----------|---------|------|----|
| Email signup + verification | Working | :white_check_mark: | — |
| GitHub OAuth | Working, creds deployed | :white_check_mark: | — |
| Google OAuth fully functional | Client ID only, secret missing | :x: | LG-001 |
| Password reset flow | Working | :white_check_mark: | — |
| Onboarding wizard | Working | :white_check_mark: | — |
| Session expiry UX with toast | Working | :white_check_mark: | — |

**Domain Score: 90/100** (Google OAuth is the gap)

---

## Domain 2: Dashboard & Data

| Intended | Current | Gap? | ID |
|----------|---------|------|----|
| All utility tabs show real dashboards | Natural Gas shows "coming soon" | :warning: | LG-002 |
| No hardcoded/mock data | Confirmed clean | :white_check_mark: | — |
| Setup checklist dynamic | Wired to useConnections() | :white_check_mark: | — |
| Savings tracking real data | SavingsService + API exist | :white_check_mark: | — |
| Loading skeletons on all areas | 23 loading.tsx files | :white_check_mark: | — |

**Domain Score: 90/100** (Natural Gas tab placeholder)

---

## Domain 3: Core Features

| Intended | Current | Gap? | ID |
|----------|---------|------|----|
| Real-time prices (SSE) | Working with resilience | :white_check_mark: | — |
| ML forecasts | Working (676 tests) | :white_check_mark: | — |
| Supplier comparison from DB | Working (tariffs from DB) | :white_check_mark: | — |
| Price analytics endpoints | Working | :white_check_mark: | — |
| Load optimization | Working | :white_check_mark: | — |
| AI Agent with fallback | Working (Gemini + Groq) | :white_check_mark: | — |
| Community with moderation | Working | :white_check_mark: | — |
| Alert CRUD + history | Working | :white_check_mark: | — |
| Billing + tier gating | Working | :white_check_mark: | — |

**Domain Score: 100/100**

---

## Domain 4: Connections

| Intended | Current | Gap? | ID |
|----------|---------|------|----|
| Bill upload functional | Working | :white_check_mark: | — |
| UtilityAPI OAuth functional | Working | :white_check_mark: | — |
| Email connection functional | 503 fallback shows "not yet available" | :warning: | LG-003 |
| Direct login functional | 503 fallback shows "not yet available" | :warning: | LG-004 |
| Portal scraping | Working (5 utilities) | :white_check_mark: | — |
| Missing UTILITYAPI_KEY env | Not set on Render | :x: | LG-005 |
| Missing Gmail/Outlook creds | Not set on Render | :x: | LG-006 |

**Domain Score: 65/100** (Connection methods partially broken without env vars)

---

## Domain 5: UX Quality

| Intended | Current | Gap? | ID |
|----------|---------|------|----|
| Error boundaries on all routes | 29 error.tsx files | :white_check_mark: | — |
| Loading states on all routes | 23 loading.tsx (static pages acceptable) | :white_check_mark: | — |
| Toast notifications | toast.tsx + toast-context.tsx wired | :white_check_mark: | — |
| Custom confirmation modals | Account deletion uses native window.confirm | :warning: | LG-007 |
| No beta artifacts visible | Beta signup page still accessible | :warning: | LG-008 |
| No "coming soon" placeholders | Natural Gas tab shows placeholder | :warning: | LG-002 |
| Brand consistency | Clean (2 code comments only) | :white_check_mark: | — |
| Responsive + accessible | Working (E2E on 5 browsers + jest-axe) | :white_check_mark: | — |

**Domain Score: 80/100**

---

## Domain 6: Security

| Intended | Current | Gap? | ID |
|----------|---------|------|----|
| Session-based auth | Working | :white_check_mark: | — |
| OAuth HMAC state tokens | Working | :white_check_mark: | — |
| 3-tier rate limiting | Working | :white_check_mark: | — |
| CSP headers | unsafe-inline accepted with risk doc | :white_check_mark: | — |
| OWASP ZAP weekly | Working | :white_check_mark: | — |
| pip-audit + npm audit in CI | Working | :white_check_mark: | — |
| HMAC model signing | Working (key set) | :white_check_mark: | — |
| GDPR compliance | Working (export + delete) | :white_check_mark: | — |
| Feature flag system | Working (DB-backed) | :white_check_mark: | — |

**Domain Score: 100/100**

---

## Domain 7: Infrastructure

| Intended | Current | Gap? | ID |
|----------|---------|------|----|
| FRONTEND_URL set to rateshift.app | **NOT SET** — defaults to localhost:3000 | :x: | LG-009 |
| Backend always-on (no cold starts) | **FREE TIER** — sleeps after 15min | :x: | LG-010 |
| Email capacity for launch day | **100/day free cap** — need ~600 | :x: | LG-011 |
| All env vars set | 6 missing/placeholder vars | :x: | LG-012 |
| GHA minutes sufficient | ~1,283/mo estimated (within 2,000) | :white_check_mark: | — |
| CF Worker deployed | Working, 3 crons active | :white_check_mark: | — |
| Database migrated | 63 migrations deployed | :white_check_mark: | — |
| OTel tracing | Working (Grafana Cloud) | :white_check_mark: | — |
| Monitoring dashboards | Working (UptimeRobot, Sentry, Grafana) | :white_check_mark: | — |
| Background job queue | NOT IMPLEMENTED | :warning: | LG-013 |

**Domain Score: 55/100** (Multiple infra gaps)

---

## Domain 8: Documentation & Launch Prep

| Intended | Current | Gap? | ID |
|----------|---------|------|----|
| PH launch materials | Ready (615 lines) | :white_check_mark: | — |
| HN/Reddit posts | Ready | :white_check_mark: | — |
| Monitoring runbook | Ready (846 lines) | :white_check_mark: | — |
| Capacity audit | Ready | :white_check_mark: | — |
| Launch checklist verified | **ALL ITEMS UNCHECKED** | :x: | LG-014 |
| MVP checklist current | **STALE** (March 4 numbers) | :warning: | LG-015 |
| GA4 analytics configured | **NOT FOUND** in codebase | :x: | LG-016 |
| Status page created | **NOT CREATED** | :x: | LG-017 |
| Content assets (screenshots, video) | Unknown — no evidence of creation | :warning: | LG-018 |
| Social media accounts | Unknown — not verifiable from code | :warning: | LG-019 |

**Domain Score: 45/100** (Launch prep not started)

---

## Domain 9: Testing

| Intended | Current | Gap? | ID |
|----------|---------|------|----|
| All tests passing | 7,390 tests passing | :white_check_mark: | — |
| No skipped tests | 0 backend skips, 2 E2E TODOs | :white_check_mark: | — |
| Load testing validated | Load test in CI (1000 concurrent) | :white_check_mark: | — |

**Domain Score: 98/100**

---

## Overall Readiness Score

| Domain | Score | Weight | Weighted |
|--------|-------|--------|----------|
| Auth & Onboarding | 90 | 10% | 9.0 |
| Dashboard & Data | 90 | 10% | 9.0 |
| Core Features | 100 | 15% | 15.0 |
| Connections | 65 | 10% | 6.5 |
| UX Quality | 80 | 10% | 8.0 |
| Security | 100 | 15% | 15.0 |
| Infrastructure | 55 | 15% | 8.25 |
| Docs & Launch Prep | 45 | 10% | 4.5 |
| Testing | 98 | 5% | 4.9 |
| **TOTAL** | | **100%** | **80.15** |

### Readiness Verdict: **80/100 — NOT YET LAUNCH-READY**

The product is feature-complete and well-tested. The gaps are almost entirely in **infrastructure configuration** (env vars, tier upgrades) and **launch operations** (checklist execution, analytics, status page, content assets). No major code work is required — most gaps are manual dashboard actions and content creation.

### To reach 95+:
1. Set FRONTEND_URL on Render (P0 — 2 min)
2. Upgrade Render to Starter or accept cold-start risk (P1 — 2 min + $7/mo)
3. Upgrade Resend or accept email cap risk (P1 — 5 min + $20/mo)
4. Walk launch checklist and check off completed items (P1 — 30 min)
5. Set up GA4 analytics (P1 — 1 hour)
6. Create status page (P2 — 30 min)
7. Remove beta signup page (P2 — 5 min)
8. Wire Natural Gas tab to GasRatesContent (P2 — 15 min)
