# Tasks — ci-pydantic-import_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.

- [x] Task 1.1: Delete `safety==3.0.0` line from `backend/requirements-dev.txt`
- [x] Task 1.2: Commit + push, verify CI green — pydantic 2.12.5 installs cleanly, backend boots, downstream failures are unrelated (separate latent reds #9 + new #11)
