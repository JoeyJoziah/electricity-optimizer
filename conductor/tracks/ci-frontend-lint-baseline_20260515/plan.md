# Implementation Plan: Frontend Lint Baseline Cleanup

**Track ID:** ci-frontend-lint-baseline_20260515
**Created:** 2026-05-15
**Status:** [x] Fixed + validated 2026-05-21, PUSH PENDING. `npm run lint` → 0 errors (from 91); 15 `no-console` warnings intentionally retained. Full FE suite 3437/3437. ESLint config untouched, no rules disabled, no tests weakened. Merged to LOCAL main; push gated to a separate user authorization (was not covered by the migration-push approval).
**Predecessor:** `ci-frontend-lint-workflow_20260515` (ESLint 9 + flat-config migration)

## Background

The ESLint 9 + flat-config migration (`ci-frontend-lint-workflow_20260515`) restored the lint pipeline after Next 16 removed the `next lint` subcommand. With lint actually running again for the first time in ≥15 days, **95 errors and 16 warnings** surfaced that had been masked by the crash.

These are not new code issues introduced by the migration — they're pre-existing latent errors that the broken `next lint` crash was hiding. The audit trail is unambiguous: the prior CI never reported these, so they accumulated.

## Lint findings inventory (post-migration, 2026-05-15)

After running `npx eslint .` against the migrated flat-config in `frontend/`:

### Errors (95 total)

- **39 × `@typescript-eslint/no-unused-vars`** — unused imports, parameters, destructured vars. Already an error rule under the old config; latent because old lint was crashing.
- **35 × `react/display-name`** — anonymous arrow-function components that should have `displayName` set. New visibility under `next/core-web-vitals`.
- **15 × `@typescript-eslint/no-require-imports`** — `require()` calls inside test files. New rule in `@typescript-eslint/eslint-plugin` 8.x. **Auto-fixable** via `--fix`.
- **3 × `react-hooks/rules-of-hooks`** — REAL hook misuse bugs. Highest priority.
- **1 × `import/no-anonymous-default-export`** — unnamed default export.
- **1 × `@next/next/no-assign-module-variable`** — Next.js bundle hazard.
- **1 × `prefer-const`** — `let` for never-reassigned binding.

### Warnings (16 total)

- **15 × `no-console`** — `console.log` calls in non-error contexts. Allowed list: `[error, warn]`. Several are in `scripts/patch-jsdom-location.js` (post-install patch script — legitimate; consider an override file).
- **1 × misc**

## Approach

### Phase 1: Auto-fix what's safe

- [ ] Task 1.1: Run `cd frontend && npm run lint:fix`. Expected: cleans up the 15 `no-require-imports` errors plus the 19 unused-eslint-disable directives. Verify diff is mechanical (no logic changes).
- [ ] Task 1.2: Run `npm test -- --testPathPattern=__tests__ --ci` to confirm no regression from auto-fix changes.

### Phase 2: Fix real bugs

- [ ] Task 2.1: Fix the 3 `react-hooks/rules-of-hooks` violations. These are hook calls inside conditionals or loops — actual bugs.
- [ ] Task 2.2: Fix `@next/next/no-assign-module-variable` — Next.js bundle hazard.
- [ ] Task 2.3: Fix `import/no-anonymous-default-export` (name the default export).
- [ ] Task 2.4: Fix `prefer-const`.

### Phase 3: Mechanical cleanup

- [ ] Task 3.1: Remove the 39 `@typescript-eslint/no-unused-vars` errors. Either delete the unused symbols or prefix with `_`. Files cluster in `frontend/__tests__/`, `frontend/app/`, `frontend/lib/`.
- [ ] Task 3.2: Address the 35 `react/display-name` errors. Decision: either give every anonymous component a `displayName`, OR (more pragmatic) add a `react/display-name: off` rule with a follow-up to revisit. Recommended: relax this rule project-wide — display-name only matters for React DevTools debugging and noticeably hurts JSX readability.

### Phase 4: Console warnings

- [ ] Task 4.1: For legitimate `console.log` in build/postinstall scripts (`scripts/patch-jsdom-location.js`), add a per-file `eslint-disable` OR a `files: ['scripts/**']` block in `eslint.config.mjs` with `no-console: 'off'`.
- [ ] Task 4.2: Convert app-code `console.log` to `console.warn`/`console.error` where the call is genuinely error reporting; remove or replace with structured logging where not.

### Phase 5: Ship

- [ ] Task 5.1: Run `npm run lint` — confirm 0 errors. Warnings OK if intentional.
- [ ] Task 5.2: Commit + push, verify Frontend Lint CI job turns green.

## Completion Criteria

- [ ] `npm run lint` exits 0 with 0 errors
- [ ] No silent rule disabling at config level beyond documented exceptions
- [ ] Frontend Lint CI job green on main
- [ ] Test suite still passes

## Out of scope

- Prettier formatting changes
- ESLint rule additions beyond what flat-config / next 16 already brings
- Refactoring identified by lint hits beyond what the rule requires

## Related

- `ci-frontend-lint-workflow_20260515` — predecessor; this track addresses the debt it exposed
- `ci-red-triage_20260515` — grandparent
- `ph-relaunch-jun2_20260515` — launch-blocker until CI Frontend Lint green
