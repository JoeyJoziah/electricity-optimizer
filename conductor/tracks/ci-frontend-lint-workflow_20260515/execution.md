# Execution Log — ci-frontend-lint-workflow_20260515

## 2026-05-15 — Track created from latent-red split

Split off from `ci-red-triage_20260515` "Discovered Latent Reds" #8. Frontend Lint job has been failing with `Invalid project directory provided, no such directory: .../frontend/lint`. Initial hypothesis: shell-quoting bug in workflow YAML. Probably 1-line fix.

## 2026-05-15 (later) — Original hypothesis disproved, scope expanded

Parallel-execution agent investigated and correctly HALTED rather than commit a half-fix:

- Workflow YAML is structurally correct. No shell-quoting bug.
- Real root cause: **`next lint` was removed in Next 16**. The Next CLI parses `lint` as a positional project-dir arg, producing the misleading directory error.
- Tried workflow-only patch (`npx eslint . --ext ...`) → exposed second blocker: `eslint@8.57.1` cannot consume `eslint-config-next@16.0.7` flat-config; crashes with `TypeError: Converting circular structure to JSON` in `@eslint/eslintrc`.
- Fix requires: ESLint 8→9 bump + flat-config migration + workflow + package.json scripts update. Medium-effort migration, not a 1-line fix.

Twin audit: only `ci.yml` references `next lint` (lines 203 + 226 via npm script). No other workflows affected.

Agent returned worktree clean, no commit. Plan.md and tasks.md rewritten to reflect the actual scope. Status stays `[ ]` — substantial new work.

Launch-blocker per "tests are sacred" — `ph-relaunch-jun2_20260515` depends on this closing.
