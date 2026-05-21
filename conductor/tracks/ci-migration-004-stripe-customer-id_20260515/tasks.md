# Tasks — ci-migration-004-stripe-customer-id_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.

## Phase 1: Diagnose
- [x] Task 1.1: Read `004_performance_indexes.sql:12` + surrounding context
- [x] Task 1.2: Grep for `stripe_customer_id` across migrations — find creator
- [x] Task 1.3: Query prod for column current state
- [x] Task 1.4: Decide reorder vs guard vs merge

## Phase 2: Patch
- [x] Task 2.1: Apply chosen fix (guarded DO block or move index)
- [x] Task 2.2: Header comment + track link

## Phase 3: Ship
- [x] Task 3.1: Docker fresh-replay green
- [x] Task 3.2: Commit + push, CI green
- [x] Task 3.3: Prod schema unchanged post-deploy
