# Tasks — ci-frontend-build-nextconfig_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.

## Phase 1: Diagnose
- [ ] Task 1.1: Read `frontend/next.config.js` lines 1-30
- [ ] Task 1.2: Pull exact CI error + stack from run `25929338762`
- [ ] Task 1.3: Match line 12 to likely cause list (ESM/env-var/syntax/path)

## Phase 2: Fix
- [ ] Task 2.1: Apply targeted fix
- [ ] Task 2.2: `npm run build` succeeds locally
- [ ] Task 2.3: Bundle output unchanged

## Phase 3: Ship
- [ ] Task 3.1: Commit + push, Frontend Build green
- [ ] Task 3.2: Vercel preview still builds
