# LAUNCH GAP BACKLOG — RateShift (v2)

> Generated: 2026-03-24 | Supersedes: 2026-03-23 backlog
> Total gaps: 21 | Completed: 10 | Active: 11 | New in v2: LG-020, LG-021
> Skipped: LG-016 (GA4 — needs Measurement ID from user)

---

## P0 — Launch Blockers (must fix before PH post goes live)

### ~~LG-009: Set FRONTEND_URL on Render~~ DONE
- **Status**: COMPLETED (2026-03-24) — Set `FRONTEND_URL=https://rateshift.app` via Render API (1Password credential + curl PUT). Verified in env vars listing.
- **Domain**: Infrastructure
- **Type**: Configuration

---

## P1 — High Priority (should fix before launch)

### LG-001: Google OAuth incomplete
- **Domain**: Authentication
- **Type**: Configuration (manual)
- **Description**: Google OAuth Client ID exists in GCP but the client secret was never captured (GCP permanently hashes secrets after dialog dismissed). Google login button will fail.
- **Evidence**: `CLAUDE.md` — "Google OAuth IN PROGRESS — secret NOT yet captured". Render has placeholder values.
- **Fix**: Create new OAuth client in GCP Console > APIs & Services > Credentials. **Download JSON immediately before dismissing.** Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET on Render.
- **Effort**: 15 minutes
- **Dependencies**: None
- **Verification**: Complete Google OAuth login flow end-to-end.

### LG-010: Render free tier cold starts
- **Domain**: Infrastructure
- **Type**: Configuration (manual)
- **Description**: Render free tier auto-sleeps after 15min idle. First visitor after sleep waits 20-30s. On PH launch day, this is a terrible first impression.
- **Evidence**: `docs/CAPACITY_AUDIT.md` — Risk rated CRITICAL
- **Fix**: Upgrade to Render Starter ($7/mo) in dashboard, or accept risk with keepalive mitigation
- **Effort**: 2 minutes + $7/mo
- **Dependencies**: None
- **Verification**: Backend stays warm between requests with no 20-30s delays

### LG-011: Resend email capacity for launch day
- **Domain**: Infrastructure
- **Type**: Configuration (manual)
- **Description**: Resend free tier caps at 100 emails/day. Conservative 100-signup scenario exceeds this (verification + welcome = 2 per signup). Gmail SMTP fallback adds ~500/day buffer but is less reliable.
- **Evidence**: `docs/CAPACITY_AUDIT.md` — Risk rated CRITICAL for Scenario B
- **Fix**: Upgrade to Resend Starter ($20/mo) or accept risk with Gmail SMTP fallback
- **Effort**: 5 minutes + $20/mo
- **Dependencies**: None
- **Verification**: Resend dashboard shows increased limit.

### LG-016: GA4 analytics not configured
- **Domain**: Analytics
- **Type**: Code + configuration
- **Description**: No Google Analytics integration in frontend. Cannot measure signups, conversions, retention, or any launch success metrics. Only Microsoft Clarity is present (heatmaps/session recording, not event analytics).
- **Evidence**: `grep` for GA4/gtag/google.*analytics returned only package-lock.json
- **Fix**: (a) Create GA4 property, (b) add GA4 script tag to `frontend/app/layout.tsx`, (c) configure events for signup, login, forecast, switch, upgrade
- **Effort**: 1-2 hours
- **Dependencies**: Need GA4 Measurement ID from user
- **Verification**: GA4 real-time dashboard shows events from test clicks

### ~~LG-020: No OG image for social sharing~~ DONE
- **Status**: COMPLETED (2026-04-07) — Created `frontend/app/opengraph-image.tsx` using Next.js ImageResponse (1200x630, blue gradient, bolt icon, "RateShift" branding). Added `images` to `openGraph` and `twitter` metadata in `layout.tsx`.
- **Domain**: SEO / Marketing
- **Type**: Code + asset creation

---

## P2 — Medium Priority (polish before launch)

### LG-012: Missing Render environment variables
- **Domain**: Infrastructure
- **Type**: Configuration (manual)
- **Description**: 6 environment variables on Render are missing or placeholder. These affect Google OAuth, UtilityAPI sync, and email scanning features.
- **Evidence**: `CLAUDE.md` "Remaining env var gaps" section
- **Fix**: Obtain each credential from respective services and set on Render dashboard
- **Effort**: 30-60 minutes per credential
- **Dependencies**: LG-001 (Google OAuth) is a subset
- **Verification**: Each connection type tested end-to-end
- **Env vars**: GOOGLE_CLIENT_ID/SECRET (placeholder), UTILITYAPI_KEY (missing), GMAIL_CLIENT_ID/SECRET (missing), OUTLOOK_CLIENT_ID/SECRET (missing)

### LG-017: Status page not created
- **Domain**: Operations
- **Type**: Configuration (manual)
- **Description**: `docs/LAUNCH_CHECKLIST.md` references a status page. Users have no way to check if service is down.
- **Evidence**: `grep statuspage` matches only docs and previous qa/ files — no actual page exists
- **Fix**: Create on Statuspage.io, Better Uptime, or Instatus. Configure monitors for backend, frontend, CF Worker.
- **Effort**: 30 minutes
- **Dependencies**: None
- **Verification**: Status page URL loads and shows all systems green

### ~~LG-021: Sitemap includes protected /dashboard route~~ DONE
- **Status**: COMPLETED (2026-04-07) — Removed `/dashboard` entry from `staticPages` in `frontend/app/sitemap.ts`. Sitemap now has 4 static pages (/, /pricing, /privacy, /terms) + programmatic rate pages.
- **Domain**: SEO
- **Type**: Code fix

### LG-018: Content assets (screenshots, video) not verified
- **Domain**: Launch Prep
- **Type**: Content creation (manual)
- **Description**: PH launch requires 4-6 gallery screenshots, hero image, logo (500x500 PNG), and optional demo video. No evidence these have been created.
- **Evidence**: `docs/LAUNCH_CHECKLIST.md` Content Assets section unchecked
- **Fix**: Create screenshots of dashboard, forecast, suppliers, pricing, mobile view. Prepare logo. Optional: 30-60s demo video.
- **Effort**: 2-4 hours
- **Dependencies**: Product should be fully polished first. LG-020 (OG image) can share assets.
- **Verification**: All content assets ready for PH draft page upload

---

## P3 — Low Priority (nice-to-have / deferred)

### LG-005 + LG-006: Missing connection credentials
- **Domain**: Connections / Infrastructure
- **Type**: Configuration (manual)
- **Description**: UTILITYAPI_KEY, GMAIL_CLIENT_ID/SECRET, OUTLOOK_CLIENT_ID/SECRET missing from Render. These affect UtilityAPI auto-sync, Gmail email scanning, and Outlook email scanning. For launch, bill upload and portal scraping are primary — these can be deferred.
- **Evidence**: `CLAUDE.md` env var gaps
- **Fix**: Obtain credentials from each service and set on Render
- **Effort**: 30 minutes per credential
- **Dependencies**: Service accounts need to be created
- **Verification**: Each connection type tested end-to-end

### LG-013: No background job queue
- **Domain**: Architecture
- **Type**: Deferred
- **Description**: PRD called for arq-based async task queue. Not implemented — bill uploads are synchronous, email scanning is cron-triggered. Current approach works fine at launch scale.
- **Evidence**: Grep for arq/celery/dramatiq returned zero matches
- **Fix**: Defer to post-launch. Revisit at 200+ DAU.
- **Effort**: 2-3 days
- **Dependencies**: None for launch
- **Verification**: N/A — deferred

### LG-019: Social media accounts not verified
- **Domain**: Launch Prep
- **Type**: Process (manual)
- **Description**: Launch checklist requires active Twitter, LinkedIn, 7 drafted tweets. Cannot verify from codebase.
- **Evidence**: `docs/LAUNCH_CHECKLIST.md` Network Building section unchecked
- **Fix**: Verify accounts, draft tweets, update LinkedIn
- **Effort**: 1-2 hours
- **Dependencies**: None
- **Verification**: All social accounts accessible and content drafted

---

## Completed Items (from v1 sprint, 2026-03-23)

| ID | Description | Completion |
|----|-------------|------------|
| LG-002 | Natural Gas dashboard tab "coming soon" | DONE — `GasRatesContent` added to `UTILITY_DASHBOARDS`, dynamic import, test updated |
| LG-003 | Email connection "not yet available" message | DONE — Changed to "temporarily unavailable — please try again later or use bill upload" |
| LG-004 | Direct login "not yet available" message | DONE — Same wording change as LG-003 |
| LG-007 | Native window.confirm for account deletion | DONE — Replaced with `<Modal variant="danger">`, tests updated |
| LG-008 | Beta signup page still accessible | DONE — Deleted `frontend/app/(app)/beta-signup/` directory + test |
| LG-014 | Launch checklist not walked through | DONE — All product readiness items verified against codebase |
| LG-015 | MVP launch checklist stale | DONE — Updated header with current numbers (7,390 tests, 58 tables, 63 migrations) |

---

## Summary

| Priority | Total | Completed | Active | Code Work | Manual Only |
|----------|-------|-----------|--------|-----------|-------------|
| P0 | 1 | 1 | 0 | 0 | 1 |
| P1 | 5 | 1 | 4 | 1 | 3 |
| P2 | 7 | 5 | 2 | 1 | 1 |
| P3 | 8 | 3 | 5 | 0 | 5 |
| **Total** | **21** | **10** | **11** | **2** | **9** |

### Effort Estimate (active items only)

| Priority | Count | Effort | Monthly Cost |
|----------|-------|--------|--------------|
| P0 | 0 | — | $0 |
| P1 | 4 | 2-4 hours | $27/mo (Render + Resend) |
| P2 | 2 | 2.5-4.5 hours | $0 (optional Statuspage) |
| P3 | 5 | 5-7 hours | $0 |
| **Total active** | **11** | **~9-15 hours** | **$27/mo** |

---

## Critical Path to Launch

```
IMMEDIATE (parallel, 30 min):
  LG-009 (FRONTEND_URL)       ──┐
  LG-010 (Render upgrade)     ──┼── All Render dashboard actions
  LG-011 (Resend upgrade)     ──┘
  LG-021 (Sitemap fix)        ──── 2 min code change

THEN (parallel, 2-3 hours):
  LG-001 (Google OAuth)       ──── 15 min GCP console
  LG-020 (OG image)           ──── 30-60 min design + code
  LG-016 (GA4 analytics)      ──── 1-2 hours (needs Measurement ID)

THEN (parallel, 3-5 hours):
  LG-017 (Status page)        ──── 30 min
  LG-018 (Screenshots/video)  ──── 2-4 hours
  LG-019 (Social accounts)    ──── 1-2 hours

                          LAUNCH READY
```

**Estimated time from now to launch-ready: 1-2 working days** (assuming manual config actions done promptly and GA4 Measurement ID provided).

**Code changes needed: 1 item remaining**
1. ~~LG-021: Remove /dashboard from sitemap.ts~~ DONE
2. ~~LG-020: Add OG image + metadata~~ DONE
3. LG-016: GA4 integration (1-2 hours, needs Measurement ID)
