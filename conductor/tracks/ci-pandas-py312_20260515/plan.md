# Implementation Plan: Pandas 2.1.0 — No Py3.12 wheels

**Track ID:** ci-pandas-py312_20260515
**Created:** 2026-05-15
**Status:** [ ] Not Started
**Discovered by:** `ci-ml-tensorflow-py312_20260515` agent during Py3.12 venv install verification

## Problem

`ml/requirements.txt` pins `pandas==2.1.0`. That release has no cp312 wheels on PyPI. After the tensorflow fix lands, ML Tests CI on Python 3.12 will move past the tensorflow install only to fail at the pandas install step.

## Resolution

Lowest cp312-compatible pandas is **2.1.1** (same minor, patch bump). Trivial 1-line change.

## Phases

### Phase 1: Bump + verify

- [ ] Task 1.1: Edit `ml/requirements.txt` — bump `pandas==2.1.0` → `pandas==2.1.1`
- [ ] Task 1.2: Verify locally: `python3.12 -m venv /tmp/pd && /tmp/pd/bin/pip install pandas==2.1.1` succeeds with cp312 wheel
- [ ] Task 1.3: Grep ML code for pandas API usage that might have minor-version-sensitive behavior: `grep -rn "import pandas\|from pandas" ml/`. 2.1.0 → 2.1.1 is a patch bump (only bugfixes per pandas release notes), so risk is minimal but worth a spot-check.

### Phase 2: Ship

- [ ] Task 2.1: Commit + push on a branch `fix/ci-pandas-py312`, message `fix(ml): pandas 2.1.0 -> 2.1.1 for py3.12 wheel availability (ci-pandas-py312_20260515)`
- [ ] Task 2.2: Verify ML Tests CI advances past pandas install (and ideally turns green if no further latent reds in ML)

## Completion Criteria

- [ ] `pip install -r ml/requirements.txt` succeeds in fresh Py3.12 venv
- [ ] ML Tests CI job advances past dependency install
- [ ] 729 ML tests still pass (or the surviving subset after any tensorflow-related test changes)

## Out of scope

- Major pandas version bump (2.1 → 2.2 has API changes)
- Auditing other ML deps for similar cp312 gaps (do that opportunistically while testing)

## Related

- `ci-ml-tensorflow-py312_20260515` — sibling fix; this completes the Py3.12 wheel-availability story
- `ci-red-triage_20260515` — grandparent
- `ph-relaunch-jun2_20260515` — launch-blocked until CI fully green
