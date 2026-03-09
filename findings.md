# Production Readiness Brainstorming Findings

> 5 agents | 3 phases | 2026-03-09
> Disposition: **APPROVED** (2 launch blockers, 8 pre-launch, 10 post-launch)

## Frontend Audit (Exploration Agent)

### Confirmed Issues
- **Landing page**: "View Demo" button links to `/dashboard` — unauthenticated users bounce to login (LAUNCH BLOCKER)
- **Favicon**: `manifest.ts` references `icon-192.png` and `icon-512.png` but files don't exist in `/public/`
- **OG images**: Twitter card has `summary_large_image` but no actual image URL
- **Legal**: `privacy@electricity-optimizer.com` in privacy page — domain not purchased
- **Analytics**: `window.gtag` call in beta-signup page but gtag never loaded (silent no-op, data loss)
- **Monitoring**: Zero Sentry imports in frontend source — client errors are invisible
- **GDPR**: No cookie consent banner (required if Clarity is enabled)

### Overturned (Code Verified)
- ~~No mobile hamburger nav~~ — `Header.tsx` has `lg:hidden` button + `Sidebar.tsx` mobile overlay (lines 140-165)
- ~~No global error boundary~~ — `app/error.tsx` and `app/global-error.tsx` exist (Next.js App Router)
- ~~No onboarding flow~~ — `OnboardingWizard` at `/onboarding`, wired via `useAuth.tsx` callbackURL
- ~~Empty dashboard~~ — `SetupChecklist` component renders when region/supplier/connection incomplete

## Backend Audit (Exploration Agent)

### Confirmed Issues
- **CORS**: `settings.py` lines 38-39 default to `["http://localhost:3000"]` if `CORS_ORIGINS` env var missing — total auth failure in production (LAUNCH BLOCKER)
- **Logging**: 7 services use `logging.getLogger()` instead of structlog (learning_service, observation_service, vector_store, price_service, price_sync_service)
- **Backup**: No documented backup strategy (Neon free tier includes 7-day PITR)

### Overturned (Code Verified)
- ~~Stripe webhook signature not verified~~ — `stripe.Webhook.construct_event()` called at `stripe_service.py:341`, guarded by secret check at line 337
- ~~SSE no connection limit~~ — `_SSE_MAX_CONNECTIONS_PER_USER = 3` with Redis-backed tracking in `prices_sse.py:34-51`
- ~~DB connection exhaustion~~ — Single worker (`gunicorn_config.py:17`), pool=8 max, Neon free=25 connections. No risk at current scale
- ~~Secrets in .env~~ — `backend/.env` is `.gitignore`d and never appears in git history

## Skeptic Review

1. **CRITICAL (upheld)**: CORS defaults to localhost — launch-day total auth failure if env var missing
2. **REJECTED**: DB connection exhaustion — math doesn't support concern with 1 worker
3. **REJECTED**: Stripe webhook unverified — `construct_event()` IS called
4. **DEFERRED**: No frontend health check — Vercel is CDN-backed, UptimeRobot sufficient
5. **REJECTED**: SSE connection limits — 3-per-user limit implemented
6. **DEFERRED**: gtag broken — dead code, not runtime error. Clean up pre-launch
7. **DEFERRED**: Rate limiting bypass for auth users — acceptable, users are identified

## Constraint Guardian Review

1. **Minimum viable cost**: ~$7/month (domain $12/yr + Render Starter $7/mo)
2. **Scaling breakpoints**: 100 users OK, 1,000 hits Neon/SMTP/worker limits, 10,000 needs paid everything
3. **Launch blockers**: CORS env var (upheld), secrets audit (pre-launch), email deliverability (pre-launch)

## User Advocate Review

1. **ACCEPTED (blocker)**: "View Demo" dead end — worst first impression possible
2. **REJECTED**: No onboarding — OnboardingWizard exists and is wired
3. **ACCEPTED (pre-launch)**: Three 403 errors for free users — generic "unavailable" text instead of upgrade CTAs
4. **DEFERRED**: Empty dashboard — SetupChecklist mitigates this
5. **ACCEPTED (pre-launch)**: Alert limit not communicated to free users
6. **DEFERRED**: Time-to-first-value undefined — evaluate with real user data post-launch
7. **ACCEPTED (pre-launch)**: 403 errors should be upgrade CTAs (same as #3)

## Decision Log

| # | Decision | Alternatives Considered | Objections | Resolution |
|---|----------|------------------------|------------|------------|
| D1 | CORS_ORIGINS is a launch blocker (env var fix, not code) | Hardcode prod origins | Constraint Guardian: "just a checklist item" | Both right — checklist item AND blocker if missed |
| D2 | "View Demo" → signup or remove | Link to pricing, link to docs | None | Trivial fix, highest-visibility bug |
| D3 | 403→upgrade CTAs, not generic text | Hide features entirely, show blurred previews | Cost: ~2hrs vs benefit | Highest-ROI pre-launch fix for conversion |
| D4 | Gmail SMTP is launch-viable email provider | Wait for custom domain, use Resend sandbox | 500/day limit at scale | Acceptable for launch, domain is post-launch |
| D5 | Frontend Sentry is post-launch, not blocker | Add before launch | Time cost vs operational blind spot | Accept risk for 1 week, add in first sprint |
| D6 | GDPR data export deferred | Build before launch | Regulatory risk | Low risk at launch scale, document timeline |
| D7 | No Clarity without cookie consent | Enable Clarity at launch | EU legal requirement | Leave CLARITY_PROJECT_ID unset until banner built |
| D8 | Neon PITR is sufficient backup | Custom backup scripts | No pg_cron on Neon | Platform-managed, adequate for side-project |
