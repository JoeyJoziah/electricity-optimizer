# Execution Log — ci-pydantic-import_20260515

## 2026-05-15 — Track created from latent-red triage

Surfaced while verifying the E2E run on `0a7c6de1`. Same diagnostic pattern as the 2026-05-14 pytest-asyncio fix: a CI-only resolver conflict masked by the local venv's pre-installed newer minor version.

Diagnosis path:
1. E2E run `25931993759` failed; backend timed out on `/health` (60s)
2. Stack trace from log: `from pydantic import Field, field_validator, model_validator` → `ImportError`
3. `field_validator` is pydantic v2; we pin `pydantic==2.12.5`
4. CI install log shows `Successfully installed ... pydantic-1.10.26` — pydantic was downgraded
5. Downgrader = `safety==3.0.0` → `safety-schemas==0.0.5` → `pydantic<2`
6. Local: `safety 3.7.0` + `safety-schemas 0.0.16` (both pydantic-2 compatible) — newer minor resolved at install time, never re-evaluated
7. `safety` is unreferenced in CI workflows + Makefile (verified via grep). pip-audit covers the same role.

Decision: delete `safety` from `requirements-dev.txt`.
