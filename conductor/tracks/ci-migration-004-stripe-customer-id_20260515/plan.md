# Implementation Plan: Migration 004 — stripe_customer_id missing

**Track ID:** ci-migration-004-stripe-customer-id_20260515
**Created:** 2026-05-15
**Status:** [x] Complete — fix merged (`1fd2d1eb`) + VALIDATED 2026-05-21 via Neon ephemeral-branch replay: `004` AND `037` (both carry the stripe_customer_id DO-block guard) apply cleanly in a full fresh-from-scratch chain (68/68). The genuine `stripe_customer_id`-missing failure surfaced at `056` (a different file) and is fixed under `ci-migration-chain-replay_20260515`.
**Discovered by:** Verification work for `ci-migration-apply-jsonb_20260515` agent (Docker postgres:16-alpine replay)

## Problem

After the jsonb cast fix in 003 lands, the next migration in the chain fails on fresh replay:

```
backend/migrations/004_performance_indexes.sql:12: ERROR:
  column "stripe_customer_id" does not exist
```

Migration 004 references a column that doesn't yet exist at that point in history. It works in prod because prod was built incrementally; it fails on `psql -f` apply-from-scratch.

## Root Cause Hypotheses

1. **Out-of-order dependency** — column is added by a later migration (likely a billing/Stripe migration in the 020-040 range), but 004 tries to index it. Real ordering bug.
2. **Schema drift** — column was added manually in prod or via a hotfix that wasn't captured in version-controlled migrations. The index was retroactively added in 004 assuming the column exists.
3. **Conditional column** — column exists in some envs but not others; 004 should have a `CREATE INDEX IF NOT EXISTS ... WHERE EXISTS (...)` guard.

## Phase 1: Diagnose

- [x] Task 1.1: Read `backend/migrations/004_performance_indexes.sql:12` plus surrounding context (full statement)
- [x] Task 1.2: `grep -rn "stripe_customer_id" backend/migrations/` to find which migration actually creates the column. Note its sequence number.
- [x] Task 1.3: Query prod schema for `stripe_customer_id` column's current state (which table, type, nullable)
- [x] Task 1.4: Decide: reorder, guard, or merge migrations

## Phase 2: Patch

- [x] Task 2.1: Apply the chosen fix. Most likely shape:
  - Wrap the offending `CREATE INDEX` in a `DO` block that no-ops if column missing
  - OR move the index creation to the migration that adds the column
  - Preserve idempotency: prod (column exists) must not re-error
- [x] Task 2.2: Add header comment block + link to this track

## Phase 3: Verify + ship

- [x] Task 3.1: Docker postgres:16-alpine fresh replay of migrations 001..068 — all green
- [x] Task 3.2: Commit + push, Migration Validation apply-from-scratch step green
- [x] Task 3.3: Verify prod schema unchanged after next deploy

## Completion Criteria

- [x] `psql -v ON_ERROR_STOP=1 -f` cleanly applies migrations 001..068 against empty DB
- [x] Prod schema unchanged
- [x] Migration Validation CI job fully green on main

## Out of scope

- Auditing remaining migrations 005..068 for similar issues (separate audit if any surface)
- Refactoring the migration system to a proper tool (Alembic, Flyway, etc.)

## Related

- `ci-migration-apply-jsonb_20260515` — sibling fix; closing this finishes the apply-from-scratch story
- `ci-red-triage_20260515` — grandparent
- `ph-relaunch-jun2_20260515` — launch-blocked until CI fully green
