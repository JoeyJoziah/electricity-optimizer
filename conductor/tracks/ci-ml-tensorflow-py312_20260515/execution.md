# Execution Log — ci-ml-tensorflow-py312_20260515

## 2026-05-15 — Track created from latent-red split

Split off from `ci-red-triage_20260515` "Discovered Latent Reds" #6. ML Tests has been failing at install with `No matching distribution found for tensorflow==2.15.0` because TF 2.15 has no Python 3.12 wheel. Masked by `paths:` filters for ≥15 days.

Local dev venv still on Python 3.11, which is why this didn't surface earlier.

Launch-blocker per "tests are sacred" — `ph-relaunch-jun2_20260515` depends on this closing.
