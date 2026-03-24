# CURRENT vs INTENDED MATRIX — RateShift Launch Readiness (v2)

> Generated: 2026-03-24 | Supersedes: 2026-03-23 version
> Reflects 7 code fixes completed in LG sprint (LG-002/003/004/007/008/014/015)
> New gaps discovered: OG image, sitemap /dashboard

---

## Legend

| Symbol | Meaning |
|--------|---------|
| MATCH | Matches intended state |
| PARTIAL | Works but has gaps |
| GAP | Not matching intended state |
| FIXED | Was a gap in v1, now resolved |

---

## Domain 1: Authentication & Onboarding

| Intended | Current | Status | ID |
|----------|---------|--------|----|
| Email signup + verification | Working | MATCH | -- |
| GitHub OAuth fully functional | Working, creds deployed | MATCH | -- |
| Google OAuth fully functional | Client ID only, **secret never captured** | **GAP** | LG-001 |
| Password reset flow | Working | MATCH | -- |
| Onboarding wizard | Working | MATCH | -- |
| Session expiry UX | Working | MATCH | -- |

**Domain Score: 90/100** (Google OAuth is the only gap)

---

## Domain 2: Dashboard & Data

| Intended | Current | Status | ID |
|----------|---------|--------|----|
| All utility tabs show real dashboards | All 7 tabs wired (Natural Gas fixed) | MATCH | LG-002 FIXED |
| No hardcoded/mock data | Confirmed clean | MATCH | -- |
| Setup checklist dynamic | useConnections() wired | MATCH | -- |
| Loading skeletons on all areas | 22 loading.tsx | MATCH | -- |

**Domain Score: 100/100**

---

## Domain 3: Core Features

| Intended | Current | Status | ID |
|----------|---------|--------|----|
| Real-time prices (SSE) | Working with resilience | MATCH | -- |
| ML forecasts | Working (676 tests) | MATCH | -- |
| Supplier comparison from DB | Working | MATCH | -- |
| Price analytics | Working | MATCH | -- |
| Load optimization | Working | MATCH | -- |
| AI Agent with fallback | Working (Gemini + Groq) | MATCH | -- |
| Community with moderation | Working | MATCH | -- |
| Alerts CRUD + history | Working | MATCH | -- |
| Billing + tier gating | Working | MATCH | -- |

**Domain Score: 100/100**

---

## Domain 4: Connections

| Intended | Current | Status | ID |
|----------|---------|--------|----|
| Bill upload functional | Working | MATCH | -- |
| UtilityAPI OAuth functional | Working (needs UTILITYAPI_KEY for prod) | PARTIAL | LG-005 |
| Email connection graceful | "Temporarily unavailable" message | MATCH | LG-003 FIXED |
| Direct login graceful | "Temporarily unavailable" message | MATCH | LG-004 FIXED |
| Portal scraping | Working (5 utilities) | MATCH | -- |
| UTILITYAPI_KEY set | **MISSING** on Render | **GAP** | LG-005 |
| Gmail/Outlook creds set | **MISSING** on Render | **GAP** | LG-006 |

**Domain Score: 75/100** (Connection env vars missing — features degraded but gracefully handled)

---

## Domain 5: UX Quality

| Intended | Current | Status | ID |
|----------|---------|--------|----|
| Error boundaries on all routes | 28 error.tsx files | MATCH | -- |
| Loading states on all app routes | 22 loading.tsx (static pages OK) | MATCH | -- |
| Toast notifications | Wired in root layout | MATCH | -- |
| Custom confirmation modals | Modal component used (not window.confirm) | MATCH | LG-007 FIXED |
| No beta artifacts | Beta signup page deleted | MATCH | LG-008 FIXED |
| No "coming soon" placeholders | Natural Gas wired | MATCH | LG-002 FIXED |
| Brand consistency | Clean ("RateShift" everywhere) | MATCH | -- |
| Responsive + accessible | E2E 5 browsers + jest-axe | MATCH | -- |
| **OG image for social sharing** | **No og-image file; no `images` in OG metadata** | **GAP** | LG-020 (NEW) |

**Domain Score: 90/100** (OG image missing — critical for PH social cards)

---

## Domain 6: Security

| Intended | Current | Status | ID |
|----------|---------|--------|----|
| Session-based auth | Working | MATCH | -- |
| OAuth HMAC state tokens | Working | MATCH | -- |
| 3-tier rate limiting | Working | MATCH | -- |
| CSP headers | unsafe-inline accepted, documented | MATCH | -- |
| OWASP ZAP weekly | Working | MATCH | -- |
| pip-audit + npm audit | Working | MATCH | -- |
| HMAC model signing | Working (key set) | MATCH | -- |
| AES-256-GCM encryption | Working (portal creds) | MATCH | -- |
| GDPR compliance | Working (export + delete + CASCADE) | MATCH | -- |

**Domain Score: 100/100**

---

## Domain 7: Infrastructure

| Intended | Current | Status | ID |
|----------|---------|--------|----|
| FRONTEND_URL = rateshift.app | **defaults to localhost:3000** | **GAP** | LG-009 |
| Backend always-on (no cold starts) | **FREE TIER** — sleeps 15min | **GAP** | LG-010 |
| Email capacity 500+/day | **100/day free cap** | **GAP** | LG-011 |
| All env vars set and validated | 6 missing/placeholder | **GAP** | LG-012 |
| CF Worker deployed | Working, 3 crons | MATCH | -- |
| Database fully migrated | 63 migrations deployed | MATCH | -- |
| OTel tracing | Working (Grafana Cloud) | MATCH | -- |
| Monitoring dashboards | Working (UptimeRobot, Sentry) | MATCH | -- |
| GHA minutes sufficient | ~1,283/mo (within 2,000) | MATCH | -- |
| Status page for users | **NOT CREATED** | **GAP** | LG-017 |
| Background job queue | NOT IMPLEMENTED (acceptable at launch) | PARTIAL | LG-013 |

**Domain Score: 50/100** (4 clear gaps + 1 deferred)

---

## Domain 8: Analytics & SEO

| Intended | Current | Status | ID |
|----------|---------|--------|----|
| GA4 event tracking | **Zero GA4 integration** | **GAP** | LG-016 |
| Microsoft Clarity | Working | MATCH | -- |
| robots.ts | Working, proper disallow rules | MATCH | -- |
| sitemap.ts | **Includes /dashboard (protected)** | **GAP** | LG-021 (NEW) |
| Root metadata (OG, Twitter) | Present (but no image) | PARTIAL | LG-020 |
| Programmatic rate pages | Working (50 states x N utilities) | MATCH | -- |
| PWA manifest | Working | MATCH | -- |

**Domain Score: 65/100** (GA4 missing, sitemap issue, no OG image)

---

## Domain 9: Launch Materials & Operations

| Intended | Current | Status | ID |
|----------|---------|--------|----|
| PH materials | Ready (615 lines) | MATCH | -- |
| HN/Reddit posts | Ready | MATCH | -- |
| Monitoring runbook | Ready (846 lines) | MATCH | -- |
| Capacity audit | Ready | MATCH | -- |
| Launch checklist walked | Product sections verified | MATCH | LG-014 FIXED |
| MVP checklist updated | Header updated with current numbers | MATCH | LG-015 FIXED |
| Content assets (screenshots, video) | **NOT CREATED** | **GAP** | LG-018 |
| Social media accounts | **NOT VERIFIED** | **GAP** | LG-019 |

**Domain Score: 75/100** (Content assets and social accounts not prepared)

---

## Domain 10: Testing

| Intended | Current | Status | ID |
|----------|---------|--------|----|
| All tests passing | 7,362 tests passing | MATCH | -- |
| No skipped tests | 0 backend skips, 2 E2E TODOs | MATCH | -- |
| E2E coverage | 25 specs, 5 browsers, 1,605 tests | MATCH | -- |

**Domain Score: 100/100**

---

## Overall Readiness Score

| Domain | Score | Weight | Weighted |
|--------|-------|--------|----------|
| Auth & Onboarding | 90 | 8% | 7.2 |
| Dashboard & Data | 100 | 8% | 8.0 |
| Core Features | 100 | 12% | 12.0 |
| Connections | 75 | 8% | 6.0 |
| UX Quality | 90 | 10% | 9.0 |
| Security | 100 | 15% | 15.0 |
| Infrastructure | 50 | 15% | 7.5 |
| Analytics & SEO | 65 | 10% | 6.5 |
| Launch Materials | 75 | 9% | 6.75 |
| Testing | 100 | 5% | 5.0 |
| **TOTAL** | | **100%** | **82.95** |

---

## Readiness Verdict: **83/100 — NOT YET LAUNCH-READY**

Up from 80 in v1 analysis (7 code items fixed). The product is feature-complete, well-tested, and secure. Remaining gaps are:

- **1 P0 blocker** (FRONTEND_URL env var — 2 min manual fix)
- **5 P1 gaps** (Google OAuth, Render/Resend tier, GA4, OG image)
- **4 P2 gaps** (status page, sitemap fix, content assets, missing env vars)
- **3 P3 gaps** (social media, job queue, connection creds)

**No code work is required for P0.** P1 items are a mix of manual config (Render/Resend upgrades, GCP OAuth) and 1-2 hours of dev work (GA4 integration, OG image). To reach 95+, address all P0-P1 items.
