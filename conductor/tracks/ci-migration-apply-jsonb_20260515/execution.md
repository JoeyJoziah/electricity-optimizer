# Execution Log — ci-migration-apply-jsonb_20260515

## 2026-05-15 — Track created from latent-red split

Split off from `ci-red-triage_20260515` "Discovered Latent Reds" #5. The Migration Validation workflow's `psql -f` apply-from-scratch step has been failing on `003_reconcile_schema.sql:252` (jsonb default cast). Surfaced when commit `cc5b37dc` triggered workflows that `paths:` filters had been masking for ≥15 days.

Convention-check sub-step is already green via `ci-red-triage_20260515` Phase 2 (SERIAL exemption). This track addresses the orthogonal apply-from-scratch failure on the same job.

Launch-blocker per "tests are sacred" — `ph-relaunch-jun2_20260515` depends on this closing.
