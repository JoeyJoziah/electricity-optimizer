# LAUNCH GAP BACKLOG — RateShift

> Phase 3-5 | Generated: 2026-03-23 | Updated: 2026-03-23
> Total gaps: 19 | Completed: 7 (LG-002, LG-003, LG-004, LG-007, LG-008, LG-014, LG-015) | Remaining: 12
> Skipped: LG-016 (GA4 — needs Measurement ID)

---

## P0 — Launch Blockers (must fix before PH post goes live)

### LG-009: Set FRONTEND_URL on Render
- **Domain**: Infrastructure
- **Type**: Configuration
- **Description**: Backend `FRONTEND_URL` defaults to `http://localhost:3000`. This breaks email links (verification, password reset, dunning), OAuth redirect validation, and CORS headers in production.
- **Evidence**: `backend/config/settings.py:213` — `frontend_url: str = Field(default="http://localhost:3000", validation_alias="FRONTEND_URL")` with TODO comment
- **Fix**: Set `FRONTEND_URL=https://rateshift.app` in Render dashboard > Environment
- **Effort**: 2 minutes (manual dashboard action)
- **Dependencies**: None
- **Verification**: `curl -s https://api.rateshift.app/health | jq .frontend_url` should return `https://rateshift.app`. Send test password reset email and verify link domain.

---

## P1 — High Priority (should fix before launch)

### LG-010: Render free tier cold starts
- **Domain**: Infrastructure
- **Type**: Configuration
- **Description**: Render free tier auto-sleeps after 15min idle. First visitor after sleep waits 20-30s. On Product Hunt launch day, this creates a terrible first impression for early visitors.
- **Evidence**: `docs/CAPACITY_AUDIT.md` — Risk rated CRITICAL. keepalive.yml mitigates but doesn't eliminate (hourly only, gaps possible).
- **Fix**: Upgrade to Render Starter ($7/mo) in dashboard, or accept risk with keepalive mitigation
- **Effort**: 2 minutes + $7/mo
- **Dependencies**: None
- **Verification**: Backend stays warm between requests with no 20-30s delays

### LG-011: Resend email capacity for launch day
- **Domain**: Infrastructure
- **Type**: Configuration
- **Description**: Resend free tier caps at 100 emails/day. Conservative launch scenario (100 signups) exceeds this. Gmail SMTP fallback adds ~500/day buffer but is not reliable for transactional email at scale.
- **Evidence**: `docs/CAPACITY_AUDIT.md` — Risk rated CRITICAL for Scenario B (500 signups = 600 emails).
- **Fix**: Upgrade to Resend Starter ($20/mo) or accept risk with Gmail SMTP fallback
- **Effort**: 5 minutes + $20/mo
- **Dependencies**: None
- **Verification**: Resend dashboard shows Starter plan. Send test batch of 10 emails.

### LG-001: Google OAuth incomplete
- **Domain**: Authentication
- **Type**: Feature gap
- **Description**: Google OAuth Client ID exists in GCP but the client secret was never captured (GCP permanently hashes secrets after dialog dismissed). Google login button exists conditionally but will fail with placeholder secret.
- **Evidence**: `backend/config/secrets.py:68-69` maps `google_client_id` and `google_client_secret`. Render has GOOGLE_CLIENT_ID/SECRET as placeholder values.
- **Fix**: Create new OAuth client in GCP Console > APIs & Services > Credentials. Download JSON immediately. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET on Render.
- **Effort**: 15 minutes (manual GCP console work)
- **Dependencies**: None
- **Verification**: Test Google OAuth login flow end-to-end. `NEXT_PUBLIC_OAUTH_GOOGLE_ENABLED` shows Google button.

### ~~LG-014: Launch checklist not walked through~~ DONE
- **Status**: COMPLETED (2026-03-23) — Walked through all sections. Checked off all product readiness, infrastructure (except GA4), product polish, and team coordination items with codebase evidence. Left unchecked: GA4 analytics, content assets, social media, PH page setup, launch-day execution items, post-launch items.
- **Domain**: Documentation
- **Type**: Process

### LG-016: GA4 analytics not configured
- **Domain**: Documentation / Launch Prep
- **Type**: Feature gap
- **Description**: Launch checklist requires GA4 event tracking for signup, login, forecast, switch, upgrade. No `gtag`, `NEXT_PUBLIC_GA`, or Google Analytics integration found in frontend codebase.
- **Evidence**: `grep` for GA4/gtag/google.*analytics returned zero matches in frontend
- **Fix**: Add GA4 script tag to root layout, configure events for key user actions
- **Effort**: 1-2 hours
- **Dependencies**: Need GA4 property ID
- **Verification**: GA4 real-time dashboard shows events from test clicks

### LG-012: Missing Render environment variables
- **Domain**: Infrastructure
- **Type**: Configuration
- **Description**: 6 environment variables on Render are missing or placeholder: GOOGLE_CLIENT_ID/SECRET (placeholder), UTILITYAPI_KEY (missing), GMAIL_CLIENT_ID/SECRET (missing), OUTLOOK_CLIENT_ID/SECRET (missing). These affect Google OAuth, UtilityAPI sync, and email scanning features.
- **Evidence**: CLAUDE.md "Remaining env var gaps" section
- **Fix**: Obtain each credential from respective services and set on Render dashboard
- **Effort**: 30-60 minutes per credential
- **Dependencies**: LG-001 (Google OAuth) is a subset
- **Verification**: Each connection type tested end-to-end

---

## P2 — Medium Priority (polish before launch)

### ~~LG-002: Natural Gas dashboard tab shows "coming soon"~~ DONE
- **Status**: COMPLETED (2026-03-23) — Added `natural_gas: GasRatesContent` to `UTILITY_DASHBOARDS` with lazy-load dynamic import in `UtilityTabShell.tsx`. Test updated.
- **Domain**: Dashboard
- **Type**: Feature gap

### ~~LG-008: Beta signup page still accessible~~ DONE
- **Status**: COMPLETED (2026-03-23) — Deleted `frontend/app/(app)/beta-signup/` directory (page.tsx, loading.tsx, error.tsx) and corresponding test file. API endpoint left intact (harmless).
- **Domain**: UX
- **Type**: Cleanup

### ~~LG-003: Email connection "not yet available" message~~ DONE
- **Status**: COMPLETED (2026-03-23) — Changed 503 fallback to "temporarily unavailable -- please try again later or use bill upload" in `EmailConnectionFlow.tsx`.
- **Domain**: Connections
- **Type**: UX

### ~~LG-004: Direct login "not yet available" message~~ DONE
- **Status**: COMPLETED (2026-03-23) — Changed 503 fallback to "temporarily unavailable -- please try again later or use bill upload" in `DirectLoginForm.tsx`.
- **Domain**: Connections
- **Type**: UX

### LG-017: Status page not created
- **Domain**: Documentation / Launch Prep
- **Type**: Feature gap
- **Description**: `docs/LAUNCH_CHECKLIST.md` references `rateshift.statuspage.io` and launch emails reference a status page. Neither exists.
- **Evidence**: Launch checklist mentions status page; URL not configured
- **Fix**: Create status page on Statuspage.io, Better Uptime, or similar. Configure monitors for backend, frontend, CF Worker.
- **Effort**: 30 minutes
- **Dependencies**: None
- **Verification**: Status page URL loads and shows all systems green

### ~~LG-015: MVP launch checklist stale~~ DONE
- **Status**: COMPLETED (2026-03-23) — Updated header with current counts (7,390 tests, 58 tables, 63 migrations) and marked as historical document.
- **Domain**: Documentation
- **Type**: Cleanup

### LG-018: Content assets (screenshots, video) not verified
- **Domain**: Launch Prep
- **Type**: Process
- **Description**: Launch checklist requires 4-6 gallery screenshots, hero image, logo, and optional demo video. No evidence these have been created.
- **Evidence**: `docs/LAUNCH_CHECKLIST.md` Content Assets section all unchecked
- **Fix**: Create screenshots of dashboard, forecast, suppliers, pricing, mobile view. Create hero image. Prepare logo (500x500 PNG).
- **Effort**: 2-4 hours
- **Dependencies**: Product should be fully polished first
- **Verification**: All content assets uploaded to PH draft page

---

## P3 — Low Priority (nice-to-have)

### ~~LG-007: Native window.confirm for account deletion~~ DONE
- **Status**: COMPLETED (2026-03-23) — Replaced `window.confirm()` with `<Modal variant="danger">` from `components/ui/modal`. Tests updated to use modal interaction (click Delete Account button in dialog).
- **Domain**: UX
- **Type**: Polish
- **Evidence**: `frontend/app/(app)/settings/page.tsx:214` — `window.confirm(...)`
- **Fix**: Replace with custom Dialog/Modal component (already in `components/ui/`)
- **Effort**: 20 minutes
- **Dependencies**: None
- **Verification**: Account deletion shows styled modal, not browser native dialog

### LG-013: No background job queue
- **Domain**: Infrastructure
- **Type**: Architecture
- **Description**: The full-gap-remediation PRD called for arq-based async task queue for bill uploads and email scanning. Not implemented — bill uploads are synchronous, email scanning is cron-triggered.
- **Evidence**: Grep for arq/celery/dramatiq returned zero files
- **Fix**: Defer — current approach works at launch scale. Revisit at 200+ DAU.
- **Effort**: 2-3 days (significant architectural change)
- **Dependencies**: None for launch
- **Verification**: N/A — deferred

### LG-019: Social media accounts not verified
- **Domain**: Launch Prep
- **Type**: Process
- **Description**: Launch checklist requires Twitter account active, LinkedIn profile updated, 7 launch tweets drafted. Cannot verify from codebase.
- **Evidence**: `docs/LAUNCH_CHECKLIST.md` Network Building section unchecked
- **Fix**: Create/verify social media accounts, draft launch tweets
- **Effort**: 1-2 hours
- **Dependencies**: None
- **Verification**: All social accounts accessible and content drafted

### LG-005 + LG-006: Missing connection credentials (UTILITYAPI_KEY, Gmail, Outlook)
- **Domain**: Connections / Infrastructure
- **Type**: Configuration
- **Description**: UTILITYAPI_KEY, GMAIL_CLIENT_ID/SECRET, and OUTLOOK_CLIENT_ID/SECRET are missing from Render. These affect UtilityAPI sync, Gmail email scanning, and Outlook email scanning respectively. For launch, bill upload and portal scraping are the primary connection methods — these can be deferred.
- **Evidence**: CLAUDE.md env var gaps section
- **Fix**: Obtain credentials from each service and set on Render
- **Effort**: 30 minutes per credential
- **Dependencies**: Service accounts need to be created
- **Verification**: Each connection type tested end-to-end

---

## Effort Summary

| Priority | Count | Total Effort | Cost Impact |
|----------|-------|-------------|-------------|
| P0 | 1 | 2 minutes | $0 |
| P1 | 6 | 2-4 hours | $27/mo (Render + Resend) |
| P2 | 8 | 4-7 hours | $0 (optional Statuspage) |
| P3 | 4 | 4-6 hours | $0 |
| **Total** | **19** | **~10-17 hours** | **$27/mo** |

---

## Critical Path to Launch

```
LG-009 (FRONTEND_URL)     ──┐
LG-010 (Render upgrade)   ──┤
LG-011 (Resend upgrade)   ──┼── All parallelizable, 30 min total
LG-001 (Google OAuth)     ──┤
LG-008 (Remove beta page) ──┘
                              │
LG-014 (Walk checklist)   ────── 30-60 min (after above)
                              │
LG-016 (GA4 analytics)    ────── 1-2 hours (parallel)
LG-002 (Natural Gas tab)  ────── 15 min (parallel)
LG-018 (Screenshots)      ────── 2-4 hours (parallel)
                              │
                         LAUNCH READY
```

**Estimated time from now to launch-ready: 1-2 working days** (assuming manual dashboard actions are done promptly).
