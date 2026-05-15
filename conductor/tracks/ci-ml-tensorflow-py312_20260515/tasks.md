# Tasks — ci-ml-tensorflow-py312_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.

## Phase 1: Decide
- [ ] Task 1.1: Grep tensorflow/keras touch points across backend/ ml/
- [ ] Task 1.2: Pick Option A (bump TF), B (pin py3.11), or C (drop TF)

## Phase 2A (if bump): Tensorflow 2.17
- [ ] Task 2.1: Bump pin to `tensorflow==2.17.x`
- [ ] Task 2.2: Fix any Keras 3 import/API fallout in 729 tests
- [ ] Task 2.3: Smoke-test ensemble predictor end-to-end

## Phase 2B (if pin py): Python 3.11
- [ ] Task 2.1: Set `python-version: '3.11'` in ML workflow
- [ ] Task 2.2: Document EOL + follow-up migration track

## Phase 3: Ship
- [ ] Task 3.1: Commit + push, ML Tests green
- [ ] Task 3.2: Ensemble predictor smoke in CI green
