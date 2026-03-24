# DISCOVERY SUMMARY — RateShift Launch Gap Analysis (v2)

> Generated: 2026-03-24 | Supersedes: 2026-03-23 analysis
> Analyst: Claude Opus 4.6 (direct tools, no subagents)
> Previous analysis found 19 gaps (7 completed, 12 remaining). This v2 is more exhaustive.

---

## 1. Sources Consulted

### Primary Sources (Code — highest trust)

| Source | Path | Key Data |
|--------|------|----------|
| Project CLAUDE.md | `./CLAUDE.md` | Architecture, 44 env vars, cron jobs, 17 critical reminders |
| Backend settings | `backend/config/settings.py` | FRONTEND_URL default `localhost:3000`, CORS config |
| Frontend routes | `frontend/app/**/page.tsx` | 28 page routes (beta-signup deleted in v1 sprint) |
| Frontend layout | `frontend/app/layout.tsx` | Metadata (OG, Twitter), no GA4, has Clarity |
| robots.ts | `frontend/app/robots.ts` | Proper disallow rules, sitemap reference |
| sitemap.ts | `frontend/app/sitemap.ts` | Static + programmatic rate pages; includes /dashboard (issue) |
| Error boundaries | `frontend/app/**/error.tsx` | 28 files — comprehensive |
| Loading states | `frontend/app/**/loading.tsx` | 22 files — missing for public pages |
| Backend routers | `backend/api/v1/` | 41+ router files |
| CF Worker | `workers/api-gateway/` | 18 files, 3 cron triggers |
| Migrations | `backend/migrations/` | 063 files, all deployed to Neon |
| GHA workflows | `.github/workflows/` | 33 workflows |
| App factory | `backend/app_factory.py` | CORS middleware, all middleware stack |

### Secondary Sources (Docs — high trust, maintained with code)

| Source | Path | Key Data |
|--------|------|----------|
| Launch Checklist | `docs/LAUNCH_CHECKLIST.md` | PH launch plan — marketing/content sections unchecked |
| PH Launch Materials | `docs/launch/PRODUCT_HUNT.md` | Taglines, screenshots needed, hour-by-hour plan |
| Monitoring Runbook | `docs/launch/MONITORING_RUNBOOK.md` | Dashboards, incident playbooks, pre-launch upgrades |
| HN/Reddit Posts | `docs/launch/HN_REDDIT_POSTS.md` | Show HN template, 5 Reddit posts |
| Capacity Audit | `docs/CAPACITY_AUDIT.md` | Free tier limits, risk ratings |
| Stripe Architecture | `docs/STRIPE_ARCHITECTURE.md` | Billing flows, webhooks |
| Disaster Recovery | `docs/DISASTER_RECOVERY.md` | RTO <1h, RPO <7d |
| Automation Plan | `docs/AUTOMATION_PLAN.md` | 9 workflows, all complete |
| Cost Analysis | `docs/COST_ANALYSIS.md` | ~1,283 GHA min/mo |

### Tertiary Sources (Tracking — medium trust)

| Source | Path | Key Data |
|--------|------|----------|
| Master TODO Registry | `.project-intelligence/MASTER_TODO_REGISTRY.json` | 47 tasks, 19 launch gaps tracked |
| Previous Gap Backlog | `qa/launch-readiness/` (2026-03-23) | 19 gaps, 7 code items completed |
| Loki Continuity | `.loki/CONTINUITY.md` | Historical only (through 2026-03-11) |
| Memory files | `.claude/projects/.../memory/` | Cross-session patterns |

---

## 2. Discovery Methods

| Method | Tool | Queries |
|--------|------|---------|
| Route enumeration | Glob | `frontend/app/**/page.tsx`, `error.tsx`, `loading.tsx` |
| Analytics check | Grep | `NEXT_PUBLIC_GA`, `gtag`, `google.*analytics`, `GA_MEASUREMENT` |
| Social image check | Grep + Glob | `og:image`, `opengraph-image`, `frontend/public/og-*.{png,jpg}` |
| Status page check | Grep | `statuspage`, `status.rateshift`, `betteruptime` |
| FRONTEND_URL audit | Grep | `FRONTEND_URL` in backend/config |
| CORS review | Grep | `CORS`, `cors_origins`, `allow_origins` |
| SEO audit | Grep + Read | `robots.txt`, `sitemap.xml`, `meta.*description`, `og:image` |
| TODO/FIXME scan | Grep | `TODO\|FIXME\|HACK\|XXX` in `*.py` and `*.{ts,tsx}` |
| Env var gap check | Read + Grep | CLAUDE.md env var sections, settings.py |
| Seed data check | Grep | `seed`, `backfill`, `populate` in backend |
| Rate limiting review | Grep | `rate.limit`, `rateLimit`, `RATE_LIMIT` — 62 files |
| Onboarding check | Grep | `onboarding`, `welcome.*email` |

---

## 3. Verified Working (No Gaps)

These areas were checked and found launch-ready:

- **28 page routes** properly structured in Next.js App Router
- **28 error.tsx** boundaries (root, app layout, all app/auth/public routes)
- **22 loading.tsx** states (all app and auth routes covered)
- **robots.ts** with proper disallow rules (/api/, /dashboard/, /settings/, /onboarding/)
- **sitemap.ts** generating static + 50-state x N-utility programmatic pages
- **Root layout metadata**: title template, description, keywords, OG, Twitter card, robots
- **CORS**: Env-based origins, properly configured in app_factory.py
- **Rate limiting**: 62 files, 3-tier (CF edge + Redis backend + application)
- **7,362 tests** all passing (backend 2,976, frontend 2,015, E2E 1,605, ML 676, Worker 90)
- **33 GHA workflows** with self-healing, retry-curl, notify-slack
- **3 CF Worker cron triggers** active (check-alerts, price-sync, observe-forecasts)
- **Stripe billing**: 3 tiers, plan gating on 7+ endpoints, dunning, webhooks
- **PWA**: manifest.json, service worker, install prompt
- **Microsoft Clarity** analytics present
- **Brand**: "RateShift" consistent across user-facing surfaces
- **GitHub OAuth**: Complete and working
- **OWASP ZAP + pip-audit + npm audit**: In CI pipeline
- **Email**: Resend primary (domain verified, DKIM/SPF/DMARC) + Gmail SMTP fallback
- **Disaster Recovery**: Weekly backups to R2, documented runbook

---

## 4. Gaps Found

### Category A: Infrastructure / Configuration (manual actions needed)

| # | Gap | Evidence | Severity |
|---|-----|----------|----------|
| 1 | FRONTEND_URL = localhost:3000 on Render | `settings.py:213-216` TODO comment | **P0 BLOCKER** |
| 2 | Render free tier cold starts (20-30s) | `docs/CAPACITY_AUDIT.md` CRITICAL rating | P1 |
| 3 | Resend 100 emails/day cap | `docs/CAPACITY_AUDIT.md` CRITICAL for 100+ signups | P1 |
| 4 | Google OAuth secret not captured | `CLAUDE.md` — placeholder on Render | P1 |
| 5 | Missing env vars (UTILITYAPI_KEY, GMAIL_*, OUTLOOK_*) | `CLAUDE.md` env var gaps section | P1 |
| 6 | No status page | Referenced in `docs/LAUNCH_CHECKLIST.md` but doesn't exist | P2 |

### Category B: Analytics / SEO / Marketing

| # | Gap | Evidence | Severity |
|---|-----|----------|----------|
| 7 | No GA4 analytics | Zero matches for gtag/GA4 in frontend (only Clarity) | P1 |
| 8 | No OG image file | layout.tsx has OG metadata but no `images` property, no og-*.png | P1 |
| 9 | Sitemap includes /dashboard | `sitemap.ts:23-26` — protected route, search engines can't access | P2 |
| 10 | Content assets (screenshots, video) not created | `docs/LAUNCH_CHECKLIST.md` Content Assets unchecked | P2 |
| 11 | Social media accounts not verified | `docs/LAUNCH_CHECKLIST.md` Network Building unchecked | P3 |

### Category C: Code / Feature Gaps (resolved in v1 sprint)

These were found and fixed in the 2026-03-23 sprint:
- ~~Natural Gas dashboard tab~~ DONE (LG-002)
- ~~Email/Direct Login "not yet available" messages~~ DONE (LG-003, LG-004)
- ~~Beta signup page still accessible~~ DONE (LG-008)
- ~~window.confirm for account deletion~~ DONE (LG-007)
- ~~MVP checklist stale~~ DONE (LG-015)
- ~~Launch checklist not walked through~~ DONE (LG-014)

### Category D: Architecture / Deferred

| # | Gap | Evidence | Severity |
|---|-----|----------|----------|
| 12 | No background job queue (arq/celery) | Grep returned zero matches | P3 (deferred) |
| 13 | E2E test TODOs (2 items) | `authentication.spec.ts:111,165` | P3 |
| 14 | TODO in settings.py | `settings.py:213` | P3 (informational) |

---

## 5. Delta from Previous Analysis (2026-03-23)

| Change | Detail |
|--------|--------|
| **Removed** | LG-002, LG-003, LG-004, LG-007, LG-008, LG-014, LG-015 (7 items completed) |
| **New gap found** | OG image missing — not in previous analysis |
| **New gap found** | Sitemap includes protected /dashboard route |
| **Reclassified** | GA4 was "skipped (needs ID)" — now classified as P1 |
| **Unchanged** | FRONTEND_URL (P0), Render cold starts (P1), Resend cap (P1), Google OAuth (P1), missing env vars (P1), status page (P2), content assets (P2), social media (P3), job queue (P3) |
| **Total** | Previous: 19 (12 remaining). New: 14 gaps (9 remaining code/config + 5 manual/process) |
