# Execution Log — ci-ml-tensorflow-py312_20260515

## 2026-05-15 — Track created from latent-red split

Split off from `ci-red-triage_20260515` "Discovered Latent Reds" #6. ML Tests has been failing at install with `No matching distribution found for tensorflow==2.15.0` because TF 2.15 has no Python 3.12 wheel. Masked by `paths:` filters for ≥15 days.

Local dev venv still on Python 3.11, which is why this didn't surface earlier.

Launch-blocker per "tests are sacred" — `ph-relaunch-jun2_20260515` depends on this closing.

## 2026-05-21 — Install fixed, but RUNTIME REGRESSION found — track stays OPEN (/conductor-validator follow-up)

The prior session's "✅ FIX MERGED … awaiting CI green" was optimistic. Validated against a fresh Python 3.12.12 venv (`pip install -r ml/requirements.txt`):

- **Install half: PASS.** Exit 0. `tensorflow-2.17.1`, `tf-keras-2.17.0`, `tensorboard-2.17.1`, `keras-3.14.1` all pull cp312 wheels and import. The original "no cp312 wheel for tf 2.15" blocker is genuinely gone.
- **Runtime half: FAIL.** Full ML suite = **30 failed, 694 passed, 9 skipped, 4 errors** (88s). Failures concentrate in:
  - `tests/test_models.py` (CNN-LSTM): e.g. `ValueError: Dimensions must be equal, but are 24 and 3 … input shapes: [?,24], [?,24,3]` — the model now emits a 3-wide (quantile?) output where the loss expects a 24-point vector. This is a **Keras 3 behavioral change** vs the Keras 2 the code was written against.
  - `tests/test_training.py`: callback/checkpoint/repro/MAPE failures (Keras 3 training API drift).
  - `tests/test_visualization.py`: 2 matplotlib savefig-mock failures (possibly a separate latent issue).
- **`TF_USE_LEGACY_KERAS=1` does NOT fix it** — re-ran the failing files with the env var set, still 30 failed. So the `tf-keras` shim in requirements is not, by itself, restoring Keras-2 semantics for this code. The shim was added but never wired (no env var in conftest or CI).

**Conclusion:** the bump to TF 2.17.1 is install-correct but not runtime-correct. Real options (need a decision):
1. Properly activate the legacy shim — set `TF_USE_LEGACY_KERAS=1` in `ml/tests/conftest.py` + CI and confirm `tf.keras` routes to `tf_keras`; re-run.
2. If the shim still won't restore behavior, migrate the CNN-LSTM model + training code to Keras 3 (fix the output-shape/loss mismatch).
3. Investigate whether the model genuinely changed output shape (quantile head) and the test expectation is stale.

Status stays **[~]** — `ph-relaunch-jun2_20260515`'s "ML Tests CI green" gate is NOT yet met.
