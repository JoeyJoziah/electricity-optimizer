# Implementation Plan: Migration Apply jsonb Cast Failure

**Track ID:** ci-migration-apply-jsonb_20260515
**Created:** 2026-05-15
**Status:** [x] Complete — fix merged (`f95fffe3`) + VALIDATED 2026-05-21 via Neon ephemeral-branch replay: `003_reconcile_schema.sql` applies cleanly in a full fresh-from-scratch chain (68/68, psql `-v ON_ERROR_STOP=1`, exactly as CI's apply-from-scratch step runs). Post-deploy prod spot-check is the only deferred sub-item (no schema change expected — guard is idempotent).
**Source:** `ci-red-triage_20260515` plan.md — Discovered Latent Red #5
**Discovered in CI run:** `25929338762`

## Problem

The Migration Validation workflow's `psql -f` apply-from-scratch smoke-test step fails on an old migration:

```
psql:backend/migrations/003_reconcile_schema.sql:252: ERROR:
  default for column "data_categories_deleted" cannot be cast automatically to type jsonb
```

Phase 2 of `ci-red-triage_20260515` closed the **convention checks** for this job (added `063_migration_history.sql` SERIAL exemption), but the job overall stays red because the apply-from-scratch step fails on this pre-existing jsonb cast.

## Root Cause Hypothesis

`003_reconcile_schema.sql:252` issues `ALTER TABLE ... ALTER COLUMN data_categories_deleted TYPE jsonb` while the column still has a text-typed DEFAULT. Postgres can't cast the default expression automatically without an explicit `USING` clause or temporary `DROP DEFAULT`.

The migration was applied successfully in production back when the column had no default value or a compatible one. Subsequent migrations or schema drift left the live default in a state that no longer allows a fresh replay.

## Constraints

- **Migration 003 is already applied in prod** — we cannot edit history in a way that re-runs against existing databases. Any fix must be a no-op for already-migrated DBs.
- Fresh replays (CI, new dev environments, DR restore) must succeed end-to-end.
- The `backend/migrations/` directory is the source of truth for the `psql -f` smoke test.

## Options

**A. Rewrite migration 003 with a guarded `DROP DEFAULT` → `ALTER TYPE ... USING ...` → `SET DEFAULT` block** (recommended)
- Wrap in `DO $$ ... $$;` block that checks `pg_attribute` for current column type and skips if already jsonb
- Idempotent: safe on prod (skips), correct on fresh replay (runs)
- Risk: hand-editing an applied migration violates the usual "migrations are immutable" rule — needs a header comment + ADR

**B. Add a remediation migration (067+ depending on what's already applied)**
- Cleaner audit trail, but the CI smoke test still fails on migration 003 in isolation
- Doesn't fix the actual root problem (003 is unreplayable)

**C. Switch CI smoke test to apply migrations against a dump of current prod schema instead of from scratch**
- Larger workflow change; bigger blast radius
- Defers the "is our migration history actually replayable?" question

**Recommendation:** Option A with an explicit guard + ADR.

## Phases

### Phase 1: Reproduce locally

- [x] Task 1.1: Spin up empty postgres, run `psql -f` against all migrations in order, confirm 003 fails at line 252
- [x] Task 1.2: Inspect current prod schema for `data_categories_deleted` column to understand actual live state
  - Query: `SELECT data_type, column_default FROM information_schema.columns WHERE column_name = 'data_categories_deleted';`
  - Source: Neon project `cold-rice-23455092`, prod branch

### Phase 2: Patch migration 003

- [x] Task 2.1: Wrap the `ALTER COLUMN ... TYPE jsonb` block in a `DO` block with type-check guard
- [x] Task 2.2: Add inline header comment explaining the retroactive edit + link to this track
- [x] Task 2.3: Verify locally: fresh replay from migration 001 → 068 succeeds
- [x] Task 2.4: Verify locally: replaying against a dump of current prod schema is a no-op (does not re-alter the column)

### Phase 3: Ship + verify CI

- [x] Task 3.1: Commit + push, verify Migration Validation job's apply-from-scratch step turns green
- [x] Task 3.2: Spot-check prod schema unchanged after next deploy (no drift)

## Completion Criteria

- [x] Migration Validation job is fully green on main (convention checks + apply-from-scratch)
- [x] Prod schema unchanged (idempotent guard worked)
- [x] ADR or comment block documents why migration 003 was retroactively edited

## Out of scope

- Auditing other migrations for similar replay-from-scratch issues (separate track if any surface)
- Rewriting CI to skip applying from scratch (Option C)

## Related

- `ci-red-triage_20260515` — parent track that surfaced this latent red
- `ph-relaunch-jun2_20260515` — launch-blocked until CI fully green
