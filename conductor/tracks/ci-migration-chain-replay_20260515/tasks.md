# Tasks — ci-migration-chain-replay_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.
> **Triage required before execution** — see Phase 1.

## Phase 1: Triage
- [x] Task 1.1: Decide A vs B vs C — chose **B** (fix in-track; failures were independent, no shared root cause requiring split)
- [x] Task 1.2: Continue in this track (B)

## Phase 2: Fix (all validated on Neon ephemeral branch, fresh-chain 68/68)
- [x] Task 2.1: `017` — `idx_bill_uploads_user_status`: `status`→`parse_status` (008 created the table with `parse_status`; matches prod index; 055 corroborates)
- [x] Task 2.2: `017` — `idx_forecast_observations_region`: drop phantom `utility_type` (never defined on that table; prod confirms absent) → `(region, created_at DESC)`
- [x] Task 2.3: `035` — guard `neon_auth.user` backfill + sanity block with `to_regclass(...) IS NULL → RETURN` (Neon-managed schema, absent in fresh DB)
- [x] Task 2.4: `053` — `DATE(created_at)`→`((created_at AT TIME ZONE 'UTC')::date)` (IMMUTABLE; empirically verified accepted in CREATE INDEX)
- [x] Task 2.5: `056` — prepend `ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255)` (added in 057; needed at 056)
- [x] Task 2.6: `061` — `model_name`→`model_version` (no `model_name` column exists anywhere; **INFERRED INTENT — confirm semantics**)
- [x] Task 2.7: `062` — both dedup indexes `DATE(fetched_at)`→`((fetched_at AT TIME ZONE 'UTC')::date)`

## Phase 3: Validate
- [x] Task 3.1: Fresh full-chain replay (init_neon + 067 numbered) on Neon branch → **68/68 applied, 0 failed**
- [x] Task 3.2: Confirm all 7 intended objects now created (each count=1) in replayed DB
- [x] Task 3.3: Confirm edits are prod-safe (additive/guarded; prod won't re-run history-tracked migrations)

## Phase 4: Ship (PENDING)
- [~] Task 4.1: Commit + push the 6 migration files; confirm CI "Apply all migrations sequentially" job green on main — **awaits user authorization to push**
- [ ] Task 4.2: (separate finding) idempotency re-run surfaced 6 NON-re-runnable migrations (init_neon, 049, 051, 059, 063, 064) — pre-existing, untouched by this fix, NOT tested by CI's one-shot replay. Decide whether to open a follow-up track.
