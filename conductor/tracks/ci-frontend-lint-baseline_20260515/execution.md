# Execution Log — ci-frontend-lint-baseline_20260515

## 2026-05-15 — Track created from migration-exposed debt

Created immediately after `ci-frontend-lint-workflow_20260515` landed. The flat-config migration restored ESLint after Next 16 removed `next lint`. With lint actually running for the first time in ≥15 days, 95 errors + 16 warnings surfaced that the prior crash had been silently hiding.

These are pre-existing debt, not migration regressions. Captured as a separate track because:
1. Migration commit needs to remain mechanical/auditable (config files only, no behavior changes)
2. The cleanup has its own phasing — auto-fix safe, then bug fixes, then mechanical cleanup
3. Some decisions (e.g., disable `react/display-name` vs fix all 35) want a small interview before execution

Inventory captured in plan.md. Will be the **last** Frontend Lint CI green gate for `ph-relaunch-jun2_20260515`.

Launch-blocker per "tests are sacred" — `ph-relaunch-jun2_20260515` depends on Frontend Lint CI being fully green.

## 2026-05-21 — Fixed (isolated-worktree agent), validated on local main

Dispatched a frontend agent in an isolated git worktree (relative paths only; `npx jest --ci`, never `npm test`). Result: **0 errors (from 91)**, 15 `no-console` warnings retained. ESLint config untouched, no rules disabled, no blanket eslint-disable, no tests deleted.

**Actual breakdown differed from the 2026-05-15 prediction:**
- No `no-require-imports` errors (cleared in a prior phase).
- The "3 rules-of-hooks" prediction was wrong — eslint-config-next 16's react-hooks plugin surfaced **17** errors of newer kinds: `set-state-in-effect` ×10, `static-components` ×5, `purity` ×1, `refs` ×1. None were the Playwright `use`→`provide` false positive; **all 17 were genuine React-correctness bugs**, fixed at root cause (notably: a render-phase `ref.current` write in `useRealtime.ts`, render-phase `Date.now()` in `PricesContent.tsx`, a hoisted-to-module `SortIcon`, and several redundant/over-eager effects removed or guarded).
- 39 `no-unused-vars` removed; 35 `react/display-name` fixed by naming wrappers (rule kept ON).
- 3 weak `waitFor(getByTestId(card-wrapper))` test assertions corrected to await the real data element (they only passed before due to an incidental render flush from the old synchronous setState).

Validation on main after merge: `npm run lint` → 0 errors / 15 warnings; `npx jest --ci` → **3437/3437**. 73 files, +1307/-1017.

**Push pending**: merged to local main; the auto-mode classifier correctly gated the push as outside the migration-push authorization. Awaiting explicit OK to push (will turn Frontend Lint CI green on main).
