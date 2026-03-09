# Production Readiness Plan

> Generated: 2026-03-09 | Status: PENDING
> Source: Multi-agent brainstorming (5 agents, 3-phase structured design review)
> Disposition: APPROVED — 2 launch blockers, 8 pre-launch, 10 post-launch

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

- [ ] **PL-3**: Add favicon files
  - File: `frontend/public/icon-192.png`, `frontend/public/icon-512.png`
  - Fix: Generate from app's Zap icon or create simple icon
  - Verify: Browser tab shows favicon, PWA manifest resolves icons

- [x] **PL-4**: Fix dead contact email in privacy page
  - File: `frontend/app/privacy/page.tsx` ~line 76
  - Fix: Replace `privacy@electricity-optimizer.com` with `autodailynewsletterintake@gmail.com`
  - Verify: Email address in page is valid and monitored

- [ ] **PL-5**: Verify email routing in production
  - Check: `EMAIL_FROM_ADDRESS` in Render/Vercel env vars matches Gmail SMTP sender
  - Check: Auth emails (verification, reset, magic link) deliver to test accounts
  - Verify: Send test signup → receive verification email within 60s

- [ ] **PL-6**: Git secrets audit
  - Run: `git log --all --full-history -- "*.env" "*.env.*"`
  - Run: Verify gitleaks GHA workflow passes on current commit
  - Verify: Zero results from both checks

- [x] **PL-7**: Remove dead gtag code
  - Files: `frontend/app/(app)/beta-signup/page.tsx:40-44`, `frontend/global.d.ts`
  - Fix: Delete `window.gtag` call and type definition
  - Verify: No `gtag` references remain in frontend source

- [ ] **PL-8**: Ensure Clarity is NOT enabled without cookie consent
  - Check: `NEXT_PUBLIC_CLARITY_PROJECT_ID` is unset in Vercel production env
  - Verify: No Clarity script loading on production site

### Phase X: Verification
- [ ] Run full backend test suite: `.venv/bin/python -m pytest`
- [ ] Run full frontend test suite: `cd frontend && npm test`
- [ ] Verify Render deployment healthy
- [ ] Verify Vercel deployment healthy
- [ ] Test full user flow: signup → onboarding → dashboard → pricing → upgrade

## Done When
- [ ] Both launch blockers fixed and verified
- [ ] All 8 pre-launch items addressed
- [ ] All tests pass (1,475 backend + 1,420 frontend)
- [ ] Production deployments healthy

## Notes
- Post-launch items (Sentry frontend, OG images, GDPR export, per-user rate limits, structlog migration, etc.) tracked separately — see findings.md for full list
- Custom domain purchase (`electricity-optimizer.app`) is the single highest-impact post-launch investment (enables Resend custom domain email, proper branding, SEO)
