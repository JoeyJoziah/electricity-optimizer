# Tasks — ci-migration-apply-jsonb_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.

## Phase 1: Reproduce
- [x] Task 1.1: Spin up empty postgres, replay all migrations, confirm 003:252 fails
- [x] Task 1.2: Query prod for current `data_categories_deleted` column state

## Phase 2: Patch migration 003
- [x] Task 2.1: Wrap `ALTER COLUMN ... TYPE jsonb` in `DO` block with type-check guard
- [x] Task 2.2: Add header comment + ADR linking to this track
- [x] Task 2.3: Verify fresh-replay 001 → 068 succeeds locally
- [x] Task 2.4: Verify replay-against-prod-dump is a no-op

## Phase 3: Ship
- [x] Task 3.1: Commit + push, confirm CI green
- [x] Task 3.2: Spot-check prod schema unchanged post-deploy
