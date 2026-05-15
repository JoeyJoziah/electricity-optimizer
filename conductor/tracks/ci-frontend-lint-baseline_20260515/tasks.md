# Tasks — ci-frontend-lint-baseline_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.

## Phase 1: Auto-fix
- [ ] Task 1.1: `npm run lint:fix` (cleans no-require-imports + unused-disable directives)
- [ ] Task 1.2: `npm test` smoke after auto-fix

## Phase 2: Real bugs
- [ ] Task 2.1: Fix 3 `react-hooks/rules-of-hooks` violations
- [ ] Task 2.2: Fix `@next/next/no-assign-module-variable`
- [ ] Task 2.3: Fix `import/no-anonymous-default-export`
- [ ] Task 2.4: Fix `prefer-const`

## Phase 3: Mechanical
- [ ] Task 3.1: Clean 39 `no-unused-vars` (delete or `_`-prefix)
- [ ] Task 3.2: Decide on 35 `react/display-name` (fix all OR disable rule)

## Phase 4: Console
- [ ] Task 4.1: Allow `console.*` in `scripts/**`
- [ ] Task 4.2: Audit/fix remaining app-code console hits

## Phase 5: Ship
- [ ] Task 5.1: `npm run lint` exits 0
- [ ] Task 5.2: CI Frontend Lint green
