# Tasks — ci-frontend-lint-workflow_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.
> **Scope expanded 2026-05-15**: original 1-line workflow fix replaced with ESLint 9 + flat-config migration.

## Phase 1: Investigate
- [ ] Task 1.1: Read frontend package.json eslint state
- [ ] Task 1.2: Enumerate rules/plugins/overrides in .eslintrc.json
- [ ] Task 1.3: Find all consumers of `npm run lint`
- [ ] Task 1.4: Decide single PR vs split

## Phase 2: ESLint 9 + flat config
- [ ] Task 2.1: Bump eslint to ^9.x
- [ ] Task 2.2: Create eslint.config.mjs translating rules
- [ ] Task 2.3: Delete .eslintrc.*
- [ ] Task 2.4: Update package.json `scripts.lint`
- [ ] Task 2.5: Local lint output parity check

## Phase 3: Workflow fix
- [ ] Task 3.1: ci.yml line 203 `next lint --fix` → `eslint . --fix`
- [ ] Task 3.2: Confirm line 226 works via fixed npm script
- [ ] Task 3.3: Audit other workflows for `next lint` twins

## Phase 4: Ship
- [ ] Task 4.1: Commit + push, Frontend Lint CI green
- [ ] Task 4.2: Husky pre-commit still passes
- [ ] Task 4.3: No silent rule regressions
