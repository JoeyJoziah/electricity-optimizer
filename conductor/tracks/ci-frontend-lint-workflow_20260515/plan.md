# Implementation Plan: Frontend Lint — Next 16 + ESLint 9 Migration

**Track ID:** ci-frontend-lint-workflow_20260515
**Created:** 2026-05-15
**Updated:** 2026-05-15 (scope expanded after agent investigation)
**Status:** [ ] Not Started — original 1-line hypothesis disproved
**Source:** `ci-red-triage_20260515` plan.md — Discovered Latent Red #8

## Problem

Frontend Lint CI job errors with:

```
Invalid project directory provided, no such directory: .../frontend/lint
```

## Original Hypothesis (WRONG)

Workflow shell-quoting bug — `npm run lint` rendered as `npm run` + positional `lint`. Investigation 2026-05-15 disproved this; YAML is structurally correct.

## Actual Root Cause

**`next lint` was REMOVED in Next 16.** Both invocations in `.github/workflows/ci.yml` resolve to `next lint`:
- Line 203: `npx next lint --fix` (direct)
- Line 226: `cd frontend && npm run lint` where `package.json:scripts.lint = "next lint"` (indirect)

The Next 16 CLI no longer recognizes `lint` as a subcommand. It falls back to treating `lint` as a positional project-directory argument → `Invalid project directory provided`. The error message is misleading; it pointed everyone at the workflow.

## Why a Workflow-Only Fix Doesn't Work

The straightforward replacement is `npx eslint . --ext .js,.jsx,.ts,.tsx`. But:

- `frontend/package.json` pins `eslint@8.57.1`
- `eslint-config-next@16.0.7` ships **flat-config only**
- ESLint 8.x cannot consume flat-config; running `npx eslint app/page.tsx` crashes with `TypeError: Converting circular structure to JSON` in `@eslint/eslintrc`

So patching just the workflow swaps one red for another.

## Required Migration (full scope)

1. **Bump `eslint` 8.57.1 → 9.x** in `frontend/package.json`
2. **Migrate `.eslintrc.json` (or `.eslintrc.js`) → `eslint.config.mjs`** (flat config format)
3. **Update workflow** to call `npx eslint .` (or equivalent) instead of `next lint`
4. **Update `package.json:scripts.lint`** to point to direct eslint invocation
5. **Verify** all current lint rules still apply (config translation can drop rules silently)

Estimated effort: medium. ESLint 9 + flat config is a real migration, not a config-tweak. Existing rules from `eslint-config-next` should map 1:1, but custom rules / overrides need re-expression in flat-config shape.

## Phase 1: Investigate scope

- [ ] Task 1.1: Read `frontend/package.json` for current eslint version + scripts + dependencies
- [ ] Task 1.2: Read `frontend/.eslintrc.json` (or `.eslintrc.js`) — enumerate every rule, plugin, override
- [ ] Task 1.3: Identify all consumers of `npm run lint` across the codebase (workflows, husky hooks, pre-commit, package.json scripts)
- [ ] Task 1.4: Decide single-PR vs split (eslint 9 bump first, then flat config migration)

## Phase 2: ESLint 9 + flat config migration

- [ ] Task 2.1: Bump `eslint` to `^9.x` in `frontend/package.json`. Add `@eslint/eslintrc` for legacy compat if needed
- [ ] Task 2.2: Create `frontend/eslint.config.mjs` translating all existing rules. Use `@eslint/compat`'s `fixupConfigRules` for any plugin not yet flat-config native
- [ ] Task 2.3: Delete `frontend/.eslintrc.*`
- [ ] Task 2.4: Update `package.json:scripts.lint` to `"lint": "eslint . --ext .js,.jsx,.ts,.tsx"` (or `"eslint ."` with flat config covering ext via `files: [...]`)
- [ ] Task 2.5: Run `npm run lint` locally — confirm same set of warnings/errors as before the migration (no rule silently dropped)

## Phase 3: Workflow fix

- [ ] Task 3.1: Update `.github/workflows/ci.yml` line 203 — `npx next lint --fix` → `npx eslint . --fix` (or remove if redundant)
- [ ] Task 3.2: Confirm line 226 (`npm run lint`) now works because `package.json` script is fixed
- [ ] Task 3.3: Audit other workflows for `next lint` references; fix any twins

## Phase 4: Ship + verify

- [ ] Task 4.1: Commit + push on a branch, verify Frontend Lint CI job turns green
- [ ] Task 4.2: Confirm husky pre-commit hooks still work (they invoke `npm run lint`)
- [ ] Task 4.3: Confirm any lint rule changes are intentional (no silent regressions)

## Completion Criteria

- [ ] Frontend Lint CI job green on main
- [ ] `npm run lint` works locally
- [ ] Husky pre-commit hooks still fire and pass
- [ ] No silent rule drops (lint output identical before/after migration)

## Out of scope

- Migrating to a different linter (Biome, etc.)
- Cleaning up existing lint warnings beyond what's required to pass
- Touching backend / ruff configuration

## Halt point

If `eslint-config-next@16.0.7` has known migration issues (peer deps, missing rules in flat-config form), STOP and surface — may need to pin to a 15.x line as an interim.

## Related

- `ci-red-triage_20260515` — parent
- Original 2026-05-15 agent investigation: ruled out workflow-only fix, refused to commit a half-fix (correct call)
- `ph-relaunch-jun2_20260515` — launch-blocker until CI fully green
