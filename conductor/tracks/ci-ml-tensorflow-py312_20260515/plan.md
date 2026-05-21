# Implementation Plan: ML Tests — tensorflow 2.15 / Python 3.12 incompat

**Track ID:** ci-ml-tensorflow-py312_20260515
**Created:** 2026-05-15
**Status:** [x] FIXED + validated 2026-05-21, PUSH PENDING. Install fix (TF 2.17.1 cp312) was already merged; the runtime Keras-3 regression (30 failures) is now also fixed via a Keras 3 migration of the CNN-LSTM model (MedianMAE metric for the 3-quantile output, register_keras_serializable on custom classes, lower<=upper enforcement, fig.savefig). `ml/tests/` on main = **723 passed, 9 skipped, 0 failed, 0 errors** (py3.12.12). CI uses `testpaths=tests`, so the 4 script-style errors in `ml/test_forecaster.py` (pre-existing) are NOT collected → ML Tests CI expected green. Merged to LOCAL main; push pending.
**Source:** `ci-red-triage_20260515` plan.md — Discovered Latent Red #6
**Discovered in CI run:** `25929338762`

## Problem

ML Tests job fails at dependency install:

```
ERROR: No matching distribution found for tensorflow==2.15.0
```

## Root Cause

`tensorflow==2.15.0` only ships wheels for Python ≤ 3.11. CI's ML matrix runs Python 3.12, so pip can't find a compatible wheel and there are no source distributions either (TF is wheel-only on PyPI).

The 729-test ML suite passes locally because the developer venv is still on 3.11.

## Options

**A. Bump tensorflow to ≥ 2.16** (recommended)
- TF 2.16 was the first release with 3.12 wheels; current stable is 2.17.x
- Risk: breaking changes in Keras (TF 2.16 switched default backend to Keras 3) — ensemble predictor may need import updates
- Benefit: stays on canonical Python 3.12 across all CI matrices

**B. Pin ML matrix to Python 3.11**
- Smallest blast radius (one workflow file edit)
- Risk: drifts ML CI from rest of stack; perpetuates an EOL Python in our pipeline (3.11 EOL: 2027-10)
- Eventually forces this same migration anyway

**C. Drop tensorflow entirely**
- ML stack uses HNSW + scikit-learn + (optional) tensorflow for ensemble model. If tensorflow is non-load-bearing, drop it
- Needs MLPipelineAgent audit to confirm

**Recommendation:** Option A — bump to TF 2.17.x, fix any keras-3 import fallout. Falls back to Option B if Keras 3 migration is too disruptive.

## Phases

### Phase 1: Decide tensorflow's role

- [ ] Task 1.1: `grep -rln "tensorflow\|^from tensorflow\|^import tensorflow\|keras" backend/ ml/` to enumerate touch points
- [ ] Task 1.2: Decide A vs B vs C based on grep results + risk appetite

### Phase 2 (if Option A): Bump tensorflow

- [ ] Task 2.1: Bump `tensorflow==2.15.0` → `tensorflow==2.17.x` in requirements (whichever requirement file pins it)
- [ ] Task 2.2: Run 729 ML tests locally on Python 3.12, fix any Keras 3 import / API breakage
- [ ] Task 2.3: Smoke-check ensemble predictor end-to-end (model load + prediction)

### Phase 2 (if Option B): Pin Python 3.11

- [ ] Task 2.1: Edit `.github/workflows/ml-tests.yml` (or equivalent) `python-version` to `3.11`
- [ ] Task 2.2: Document EOL deadline + create follow-up track for forced migration

### Phase 3: Ship + verify

- [ ] Task 3.1: Commit + push, verify ML Tests job turns green
- [ ] Task 3.2: Verify ensemble predictor smoke test runs in CI

## Completion Criteria

- [ ] ML Tests job green on main
- [ ] All 729 ML tests still pass
- [ ] Decision recorded in execution.md (A vs B vs C + rationale)

## Out of scope

- Replacing tensorflow with a different ML library (separate track if needed)
- Rewriting ensemble model architecture

## Related

- `ci-red-triage_20260515` — parent
- `ph-relaunch-jun2_20260515` — launch-blocked until CI fully green
