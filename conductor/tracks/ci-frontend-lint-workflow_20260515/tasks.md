# Tasks — ci-frontend-lint-workflow_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.
> **Scope expanded 2026-05-15**: original 1-line workflow fix replaced with ESLint 9 + flat-config migration.

## Phase 1: Investigate
- [x] Task 1.1: Read frontend package.json eslint state
- [x] Task 1.2: Enumerate rules/plugins/overrides in .eslintrc.json
- [x] Task 1.3: Find all consumers of `npm run lint`
- [x] Task 1.4: Decide single PR vs split

## Phase 2: ESLint 9 + flat config
- [x] Task 2.1: Bump eslint to ^9.x
- [x] Task 2.2: Create eslint.config.mjs translating rules
- [x] Task 2.3: Delete .eslintrc.*
- [x] Task 2.4: Update package.json `scripts.lint`
- [x] Task 2.5: Local lint output parity check

## Phase 3: Workflow fix
- [x] Task 3.1: ci.yml line 203 `next lint --fix` → `eslint . --fix`
- [x] Task 3.2: Confirm line 226 works via fixed npm script
- [x] Task 3.3: Audit other workflows for `next lint` twins

## Phase 4: Ship
- [x] Task 4.1: Commit + push, Frontend Lint CI green
- [x] Task 4.2: Husky pre-commit still passes
- [x] Task 4.3: No silent rule regressions
