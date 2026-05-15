# Implementation Plan: Migration Chain Full-Replay Cleanup

**Track ID:** ci-migration-chain-replay_20260515
**Created:** 2026-05-15
**Status:** [ ] Not Started — needs triage interview before execution
**Source:** Agent discoveries while verifying `ci-migration-004-stripe-customer-id_20260515` via full-chain Docker postgres:16-alpine replay

## Background

Once 003 + 004 + 037 were fixed (jsonb cast guard + stripe_customer_id index guards), the agent attempted full-chain `psql -f` replay of all 68 migrations against an empty postgres. The chain still doesn't replay end-to-end. Six distinct latent reds remain.

These have been hidden by the same `paths:` filter + crashed-lint cascade that hid the original 5 latent reds; the apply-from-scratch CI step has been red for the duration.

## Inventory

| # | Migration | Error | Notes |
|---|-----------|-------|-------|
| 1 | `init_neon.sql:160` | `column "timestamp" does not exist` | Pre-existing in init |
| 2 | `017:30` | `column "status" does not exist` | Schema-order issue |
| 3 | `035` | `neon_auth.user` relation missing | Neon-platform-only schema; needs guarded skip outside Neon |
| 4 | `037:15` | `column "utility_type" does not exist` on `electricity_prices` | Independent composite-index failure (separate from the 037 stripe block already guarded) |
| 5a | `049` | schema-shape error (existing-constraint conflict) | Likely `ADD CONSTRAINT` without `IF NOT EXISTS` |
| 5b | `051` | trigger/constraint conflict | |
| 5c | `053` | trigger/constraint conflict | |
| 5d | `059` | trigger/constraint conflict | |
| 5e | `061` | non-IMMUTABLE function in index | Probably `NOW()` or similar in a partial index |
| 6 | (env) | `role "neondb_owner" does not exist` | Environment-level, not migration. CI Postgres setup needs `CREATE ROLE neondb_owner` before replay |

## Triage Question (BEFORE execution)

Two strategic choices:

**A. One-track-per-migration** (5+ tracks)
- Tighter audit trail, smaller commits, parallel-agent friendly
- Higher conductor overhead; each needs its own plan.md / tasks.md / execution.md

**B. Single-track sequential phasing**
- One plan.md with phases by error category (env setup, schema-order, neon-platform, idempotency, non-IMMUTABLE)
- One branch + one PR (or 5 commits on one branch)
- Less ceremony, harder to delegate

**C. Stop fighting the full-chain replay; accept that fresh-from-scratch isn't a real CI gate**
- Switch Migration Validation CI to apply against a dump of current prod schema instead of from-scratch
- Keep convention checks (Phase 2 of `ci-red-triage`)
- Larger workflow change but stops chasing a non-prod replay mode
- **Pros**: avoids hand-editing 5+ already-applied migrations
- **Cons**: defers the "is our migration history actually replayable?" question forever; new dev environments still hit these issues when spinning up fresh DBs

**Recommended:** B (single track, phased) for executor efficiency, OR C if the user wants to stop investing in fresh-replay as a quality bar.

## Phase 1: Triage interview

- [ ] Task 1.1: Decide A vs B vs C (above)
- [ ] Task 1.2: If A: spawn per-migration tracks. If B: continue in this track. If C: rewrite plan to target ci.yml Migration Validation workflow change.

## Phase 2+: TBD based on Phase 1

## Completion Criteria (assumes B path)

- [ ] All 68 migrations apply cleanly to fresh empty postgres
- [ ] Prod schema unchanged
- [ ] Migration Validation CI step green on main

## Out of scope

- Auditing migrations 062-068 (the most recent batch — assume green since they were authored under the new rigor)
- Rewriting the migration system to a proper tool (Alembic/Flyway)

## Related

- `ci-migration-apply-jsonb_20260515` — sibling (003 jsonb cast)
- `ci-migration-004-stripe-customer-id_20260515` — sibling (004 + 037 stripe index)
- `ci-red-triage_20260515` — grandparent
- `ph-relaunch-jun2_20260515` — launch-blocker if path A/B; bypasses gate if path C
