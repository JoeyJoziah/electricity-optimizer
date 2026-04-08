# Implementation Plan: Pre-Launch Completion

**Track ID:** pre-launch-completion_20260407
**Created:** 2026-04-07
**Status:** [ ] In Progress

## Overview

Complete all remaining code work, infrastructure configuration, and tooling gaps before Product Hunt launch. 11 tasks across 3 sprints (1 deleted, 1 moved to Track 3, 3 new from multi-agent review). Mix of automatable code tasks and manual infrastructure actions.

**Categories covered:** A (Manual Infrastructure) + B (Code Work) + F (Pending Verification)

---

## Sprint 0: Critical Infrastructure (Manual — Day 1, ~1h hands-on)

These tasks require manual dashboard access. Cannot be automated by agents.

- [x] Task 0.1: Set `FRONTEND_URL` and `OAUTH_REDIRECT_BASE_URL` on Render dashboard
  - **Source:** LAUNCHGAP-001, Roadmap 0.4, `backend/config/settings.py:220` TODO
  - **Priority:** P0 — OAuth callbacks redirect to wrong URL without this
  - **Action:** Render dashboard → srv-d649uhur433s73d557cg → Environment → Add both:
    - `FRONTEND_URL=https://rateshift.app`
    - `OAUTH_REDIRECT_BASE_URL=https://api.rateshift.app` (defaults to localhost:8000 — OAuth state HMAC validation fails without this)
  - Save → Trigger redeploy
  - **Verify:** `curl -s https://api.rateshift.app/api/v1/auth/callback/github | grep rateshift.app`

- [x] Task 0.2: Recover or recreate Google OAuth client secret
  - **Source:** LAUNCHGAP-004
  - **Priority:** P1 — Google login non-functional until done
  - **Resolution:** New GCP OAuth client created (542073657021-...). Secret provided by user, set on Render via API + stored in 1Password (qrtmbt4use5zeijzx4crdzqtsm). GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET both live on Render (50 env vars). Feature flag (Task 1.6) keeps button hidden until verified working.
  - **Verify:** Enable `NEXT_PUBLIC_ENABLE_GOOGLE_AUTH=true` on Vercel after testing Google OAuth flow

- [x] Task 0.3a: Set UtilityAPI key on Render
  - **Source:** LAUNCHGAP-013
  - **Priority:** P2
  - **Resolution:** UTILITYAPI_KEY set via Render API (value from 1Password item 6fanzg65um6m3scmqwxzewixuy). Live on Render (50 env vars total).

- [x] Task 0.3b: Set email scanning OAuth credentials on Render
  - **Source:** LAUNCHGAP-013
  - **Priority:** P3
  - **Resolution:** GMAIL_CLIENT_ID + GMAIL_CLIENT_SECRET set via Render API (same Google OAuth client 542073657021-... from 1Password qrtmbt4use5zeijzx4crdzqtsm). OUTLOOK_CLIENT_ID + OUTLOOK_CLIENT_SECRET were already present on Render. All 4 verified via API listing. Render env vars now 52 total.

---

## Sprint 1: Code Work (Automatable — Day 1-2, ~4h)

These tasks can be implemented by agents or manually.

- [x] Task 1.1: Add GA4 analytics to frontend
  - **Source:** LAUNCHGAP-005, Launch checklist line 68
  - **Priority:** P1
  - **Est. effort:** 1.5h
  - **Spec:**
    - Add `GA_MEASUREMENT_ID` env var to `.env.local` and Vercel
    - Create `frontend/lib/analytics/ga4.tsx` — Google Analytics 4 Script component using `next/script` with `strategy="lazyOnload"` (same pattern as Clarity in `clarity.tsx`)
    - Add to `frontend/app/layout.tsx`
    - Configure events: `signup`, `login`, `forecast_view`, `switch_initiated`, `plan_upgrade`, `connection_added`
    - Add `useGA4Event()` hook for component-level tracking
    - **Do NOT use `afterInteractive`** — use `lazyOnload` per web performance audit findings
  - **Test:** Unit test for GA4 component rendering, verify `gtag` calls in event hook
  - **Verify:** Chrome DevTools → Network → filter `google-analytics` after deploy

- [x] Task 1.2: Rewrite 2 skipped E2E auth tests
  - **Source:** `frontend/e2e/authentication.spec.ts` lines 111, 165
  - **Priority:** P2
  - **Est. effort:** 1h
  - **Spec:**
    - Line 111: `TODO(#GH-needs-issue): Rewrite to test native constraint validation API` — Replace skip with actual constraint validation test using `page.evaluate(() => document.querySelector('input[type=email]').validity)`
    - Line 165: `TODO(#GH-needs-issue): Remove or rewrite once magic link auth is implemented` — Either implement magic link test or replace with current auth flow test
  - **Test:** `cd frontend && npx playwright test e2e/authentication.spec.ts`

- [x] ~~Task 1.3: Resolve bill_parser.py TODOs~~ — **DELETED (phantom task)**
  - **Reason:** `bill_parser.py` has zero TODO/FIXME markers. Verified via grep. Task was based on stale data.

- [x] Task 1.5: Free-tier dashboard value-first redesign
  - **Source:** Multi-agent review UX-6 (User Advocate)
  - **Priority:** P1 — Free tier shows 2 "Upgrade to Pro" CTAs before delivering any value; kills conversion
  - **Est. effort:** 2-3h
  - **Spec:**
    - Replace Pro-gated forecast chart with blurred/teaser version showing shape + date range (not exact values)
    - Replace Pro-gated savings card with estimated range ("You could save $X-$Y/year based on your region")
    - Move upgrade CTA below the teaser content, not in place of it
    - The "aha moment" (seeing potential savings) must come BEFORE the paywall
    - Reference: `frontend/components/dashboard/DashboardCharts.tsx` lines 67-86 (current Pro gate)
  - **Test:** Visual check on free-tier dashboard, E2E test for teaser rendering

- [x] Task 1.6: Feature-flag Google OAuth button
  - **Source:** Multi-agent review UX-9, S-2 (User Advocate + Skeptic)
  - **Priority:** P1 — Broken Google login on launch day is worse than no Google login
  - **Est. effort:** 30min
  - **Spec:**
    - Add `NEXT_PUBLIC_ENABLE_GOOGLE_AUTH=true|false` env var (default: `false`)
    - Conditionally render Google OAuth button in login/signup pages
    - If `false`: only GitHub OAuth shown (which is fully functional)
    - Set to `true` on Vercel only after Task 0.2 is verified working
  - **Test:** Unit test for conditional rendering

- [x] Task 1.7: Fix pricing page copy and geographic claims
  - **Source:** Multi-agent review TR-4, TR-7 (User Advocate)
  - **Priority:** P1 — Misleading claims at launch risk credibility
  - **Est. effort:** 30min
  - **Spec:**
    - Remove "Dedicated account manager" from Business tier features on `/pricing` (no team exists)
    - Replace with "Priority email support" or similar honest alternative
    - Change "all 50 states" claims to "deregulated electricity markets" or "17+ deregulated states" on landing page (`frontend/app/page.tsx` line 144) and wherever else it appears
    - Add tooltip or link explaining which states have deregulated markets
  - **Test:** Visual check on pricing and landing pages

---

## Sprint 2: Verification & Cleanup (Day 2, ~1h)

- [ ] Task 2.1: Run visual regression baseline workflow
  - **Source:** Roadmap 1.2 — "INFRA READY, needs CI trigger"
  - **Priority:** P2
  - **Action:** GitHub Actions UI → "Update Visual Regression Baselines" → Run workflow → Select `chromium`
  - **Verify:** Check that snapshot PNGs are committed to repo

- [ ] Task 2.2: Create status page
  - **Source:** LAUNCHGAP-009, Launch checklist line 166
  - **Priority:** P2
  - **Action:** Set up at statuspage.io or similar (Atlassian Statuspage free tier, or BetterStack status page). Configure monitors for: `rateshift.app` (frontend), `api.rateshift.app` (backend/CF Worker), Neon DB health
  - **Verify:** Visit status page URL, confirm all monitors green

- [ ] Task 2.3: Verify/create social media accounts
  - **Source:** LAUNCHGAP-015
  - **Priority:** P3
  - **Action:** Verify Twitter (@rateshift or similar), LinkedIn company page, configure profile/bio/links. Needed for launch day social media campaign
  - **Verify:** All accounts accessible and branded

---

## Completion Criteria

- [x] All P0 tasks (0.1) resolved
- [x] All P1 tasks (0.2, 1.1, 1.5, 1.6, 1.7) resolved
- [ ] All tests passing: backend 3,325+, frontend 2,022+, E2E 1,642+
- [ ] No new TypeScript errors (`tsc --noEmit`)
- [x] `settings.py` TODO on line 220 removed after Task 0.1
- [x] Free-tier dashboard shows teaser content before paywall (Task 1.5)
- [x] Google OAuth button hidden unless env var enabled (Task 1.6)
- [x] No misleading claims on pricing or landing pages (Task 1.7)
