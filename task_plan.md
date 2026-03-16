# Production Readiness Plan

> **STATUS: COMPLETE** -- All tasks resolved. Production deployments verified and healthy as of 2026-03-16.
>
> Generated: 2026-03-09 | Status: ALL TASKS COMPLETE
> Source: Multi-agent brainstorming (5 agents, 3-phase structured design review)
> Disposition: APPROVED -- 2 launch blockers, 8 pre-launch, 10 post-launch

## Goal
Fix the 2 launch blockers and 8 pre-launch items to make the app ready for real users.

## Tasks

### Launch Blockers (must fix first)

- [x] **LB-1**: Set CORS_ORIGINS in Render env vars to include production Vercel domain
  - File: Render dashboard + verify `backend/config/settings.py:29-46`
  - Verify: `curl -I -H "Origin: https://your-vercel.app" https://electricity-optimizer.onrender.com/api/v1/health` returns `Access-Control-Allow-Origin`

- [x] **LB-2**: Fix "View Demo" dead link on landing page
  - File: `frontend/app/page.tsx` ~line 130 — change `href="/dashboard"` to `href="/auth/signup"` or remove
  - Verify: Click "View Demo" as unauthenticated user → goes to signup, not login redirect

### Pre-Launch (fix before promoting)

- [x] **PL-1**: 403→upgrade CTAs for free-tier dashboard (highest ROI)
  - Files: `frontend/components/dashboard/DashboardForecast.tsx:60-63`, savings component
  - Fix: Detect 403 response, render upgrade card ("Unlock forecasts with Pro") instead of "Forecast unavailable"
  - Verify: Free user sees upgrade prompt, Pro user sees forecast data

- [x] **PL-2**: Show free-tier alert limit on alerts page
  - File: `frontend/app/(app)/alerts/page.tsx` or `AlertForm.tsx`
  - Fix: Add badge/note: "Free plan: 1 alert. Upgrade for unlimited."
  - Verify: Free user sees limit info before hitting 403

- [x] **PL-3**: Add favicon files
  - Fix: Created `app/icon.tsx` (32x32 browser favicon), `app/apple-icon.tsx` (180x180), `app/api/pwa-icon/route.tsx` (192/512 dynamic). Updated `manifest.ts` to reference `/api/pwa-icon?size=N`
  - Verify: Browser tab shows favicon, PWA manifest resolves icons

- [x] **PL-4**: Fix dead contact email in privacy page
  - File: `frontend/app/privacy/page.tsx` ~line 76
  - Fix: Replace `privacy@electricity-optimizer.com` with `autodailynewsletterintake@gmail.com`
  - Verify: Email address in page is valid and monitored

- [x] **PL-5**: Verify email routing in production
  - Check: `EMAIL_FROM_ADDRESS` defaults to `autodailynewsletterintake@gmail.com` in code, set on Render (34 vars) and Vercel
  - Check: Resend primary → Gmail SMTP fallback chain confirmed in `frontend/lib/email/send.ts`
  - Note: Manual email delivery test recommended post-deploy

- [x] **PL-6**: Git secrets audit
  - Run: `git log` shows `.env.test` removed in commit `4115aa4` (security fix). No .env files currently tracked
  - Run: Gitleaks GHA workflow passes on latest main commit (3 consecutive successes)
  - Verify: Clean — no secrets in current tree, full-history scan passing

- [x] **PL-7**: Remove dead gtag code
  - Files: `frontend/app/(app)/beta-signup/page.tsx:40-44`, `frontend/global.d.ts`
  - Fix: Delete `window.gtag` call and type definition
  - Verify: No `gtag` references remain in frontend source

- [x] **PL-8**: Ensure Clarity is NOT enabled without cookie consent
  - Check: `NEXT_PUBLIC_CLARITY_PROJECT_ID` defaults to `''` in env.ts, only in `.env.example` as comment
  - Verify: `ClarityScript` returns null when env var empty (line 7). Safe unless explicitly enabled

### Phase X: Verification
- [x] Run full backend test suite: 2,480 passed, 0 failures
- [x] Run full frontend test suite: 1,841 passed, 0 failures
- [x] Verify Render deployment healthy
- [x] Verify Vercel deployment healthy
- [x] Test full user flow: signup, onboarding, dashboard, pricing, upgrade

## Done When
- [x] Both launch blockers fixed and verified
- [x] All 8 pre-launch items addressed
- [x] All tests pass (2,480 backend + 1,841 frontend, 0 failures)
- [x] Production deployments healthy (Render + Vercel + CF Worker all operational)

## Notes
- Post-launch items (Sentry frontend, OG images, per-user rate limits, structlog migration, etc.) tracked separately -- see TODO.md for remaining items
- Custom domain `rateshift.app` purchased and fully configured (DKIM/SPF/DMARC, Resend custom domain email active)
