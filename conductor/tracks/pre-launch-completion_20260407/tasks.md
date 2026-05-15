# Tasks — pre-launch-completion_20260407

> Extracted from plan.md, last reconciled 2026-05-15. plan.md remains source of truth; this mirrors actionable checkboxes for conductor validator compliance.

- [x] Task 0.1: Set `FRONTEND_URL` and `OAUTH_REDIRECT_BASE_URL` on Render dashboard
- [x] Task 0.2: Recover or recreate Google OAuth client secret
- [x] Task 0.3a: Set UtilityAPI key on Render
- [x] Task 0.3b: Set email scanning OAuth credentials on Render
- [x] Task 1.1: Add GA4 analytics to frontend
- [x] Task 1.2: Rewrite 2 skipped E2E auth tests
- [x] ~~Task 1.3: Resolve bill_parser.py TODOs~~ — **DELETED (phantom task)**
- [x] Task 1.5: Free-tier dashboard value-first redesign
- [x] Task 1.6: Feature-flag Google OAuth button
- [x] Task 1.7: Fix pricing page copy and geographic claims
- [x] Task 2.1: Run visual regression baseline workflow
- [x] Task 2.2: Create status page
- [ ] Task 2.3: Verify/create social media accounts
- [x] All P0 tasks (0.1) resolved
- [x] All P1 tasks (0.2, 1.1, 1.5, 1.6, 1.7) resolved
- [ ] All tests passing: backend 3,325+, frontend 2,022+, E2E 1,642+
- [ ] No new TypeScript errors (`tsc --noEmit`)
- [x] `settings.py` TODO on line 220 removed after Task 0.1
- [x] Free-tier dashboard shows teaser content before paywall (Task 1.5)
- [x] Google OAuth button hidden unless env var enabled (Task 1.6)
- [x] No misleading claims on pricing or landing pages (Task 1.7)
