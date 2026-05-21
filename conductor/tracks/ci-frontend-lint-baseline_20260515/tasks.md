# Tasks — ci-frontend-lint-baseline_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.
> DONE 2026-05-21 (agent in isolated worktree, merged to local main; see execution.md).
> ACTUAL breakdown differed from the 2026-05-15 prediction: eslint-config-next 16's
> react-hooks plugin surfaced 17 errors (set-state-in-effect ×10, static-components ×5,
> purity ×1, refs ×1) — NOT 3 rules-of-hooks; NO no-require-imports errors; display-name
> fixed by naming wrappers (rule kept ON).

## Phase 1: Auto-fix
- [x] Task 1.1: `eslint --fix` run (no-require-imports already absent; auto-fixable subset cleared)
- [x] Task 1.2: jest `--ci` smoke after auto-fix — green

## Phase 2: Real bugs
- [x] Task 2.1: 17 react-hooks errors fixed at ROOT CAUSE (each evaluated individually; none Playwright false positives — all genuine React-correctness bugs incl. a render-phase ref write + render-phase Date.now())
- [x] Task 2.2: n/a — no `no-assign-module-variable` error in actual lint
- [x] Task 2.3: n/a — no anonymous-default-export error in actual lint
- [x] Task 2.4: n/a — no `prefer-const` error in actual lint

## Phase 3: Mechanical
- [x] Task 3.1: 39 `no-unused-vars` cleaned (deleted unused / `_`-prefixed intentional fixture args)
- [x] Task 3.2: 35 `react/display-name` — fixed by NAMING wrappers + displayName (rule kept ON, not disabled)

## Phase 4: Console
- [x] Task 4.1/4.2: 15 `no-console` left as WARNINGS (legit CLI/test tooling + log-level semantics); 0-errors met without changing log behavior

## Phase 5: Ship
- [x] Task 5.1: `npm run lint` → 0 errors (15 warnings) — verified on main; full FE suite 3437/3437
- [~] Task 5.2: CI Frontend Lint green — merged to LOCAL main; **push pending separate user authorization** (auto-mode gated it as outside the migration-push approval)
