# Execution Log — ci-frontend-lint-baseline_20260515

## 2026-05-15 — Track created from migration-exposed debt

Created immediately after `ci-frontend-lint-workflow_20260515` landed. The flat-config migration restored ESLint after Next 16 removed `next lint`. With lint actually running for the first time in ≥15 days, 95 errors + 16 warnings surfaced that the prior crash had been silently hiding.

These are pre-existing debt, not migration regressions. Captured as a separate track because:
1. Migration commit needs to remain mechanical/auditable (config files only, no behavior changes)
2. The cleanup has its own phasing — auto-fix safe, then bug fixes, then mechanical cleanup
3. Some decisions (e.g., disable `react/display-name` vs fix all 35) want a small interview before execution

Inventory captured in plan.md. Will be the **last** Frontend Lint CI green gate for `ph-relaunch-jun2_20260515`.

Launch-blocker per "tests are sacred" — `ph-relaunch-jun2_20260515` depends on Frontend Lint CI being fully green.
