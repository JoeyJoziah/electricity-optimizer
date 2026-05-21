# Tasks — ci-pandas-py312_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.

## Phase 1: Bump
- [x] Task 1.1: `pandas==2.1.0` → `pandas==2.1.1` in `ml/requirements.txt`
- [x] Task 1.2: Verify cp312 wheel installs in fresh py3.12 venv
- [x] Task 1.3: Spot-check pandas API usage in ml/

## Phase 2: Ship
- [x] Task 2.1: Commit + push on `fix/ci-pandas-py312`
- [x] Task 2.2: ML Tests advances past pandas install
