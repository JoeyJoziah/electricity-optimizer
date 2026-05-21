# Execution Log — ci-migration-chain-replay_20260515

## 2026-05-15 — Track created from agent full-chain replay

Discovered when the `ci-migration-004-stripe-customer-id_20260515` agent attempted full-chain `psql -f` replay against `postgres:16-alpine`. After fixing 003 + 004 + 037 (stripe block), the chain still failed at 6 more independent points.

Captured as a single tracking entry rather than 6 separate tracks because:
1. Several errors cluster (049/051/053/059/061 are all schema-shape / constraint conflicts that may share a root cause)
2. Strategic choice required first: do we keep investing in fresh-replay as a quality bar (paths A/B), or switch CI to dump-based apply (path C)
3. Don't want to spawn 6 conductor tracks before the strategic interview happens

Inventory captured in plan.md from agent report.

Launch-blocker (or scope-changer) per "tests are sacred" — `ph-relaunch-jun2_20260515` depends on either Migration Validation being green OR the strategic decision to redefine what "green" means for that workflow.

## 2026-05-21 — Triaged with authoritative replay, then FIXED (chose option B)

Created an ephemeral Neon branch (`br-green-tooth-air3100h`, forked from prod, deleted after) and replayed the chain against a fresh database inside it using `psql -v ON_ERROR_STOP=1 -f` — **byte-identical to CI's "Apply all migrations sequentially" step**, and on real Neon (so the Docker-only `role "neondb_owner" does not exist` artifact from the original report does not apply).

**Authoritative pre-fix result: 62/68, 6 real failures** (the original report's 6, refined): `017:30` (status), `017:41` (utility_type — second bug in same file, hidden behind the first), `035:74` (neon_auth.user), `053:68` (IMMUTABLE), `056:53` (stripe_customer_id), `061:191` (model_name), `062:154` (IMMUTABLE). The original report's `049/051/059` were CONCURRENTLY false-positives from the Docker harness, not real (they apply fine).

Used the prod fork as ground truth (queried real schema): confirmed `forecast_observations` has no `utility_type`, `model_ab_assignments` has `model_version` (not `model_name`), prod's `idx_bill_uploads_user_status` is on `parse_status`, and the 053/061/062/056 objects never existed in prod (errored historically there too).

**Fixed all 7 across 6 files** (see tasks.md Phase 2). Re-replayed → **68/68, 0 failed**. Verified all 7 intended objects are created (count=1). All edits are additive/guarded → no-ops on production (which won't re-run history-tracked migrations).

Two flags:
1. **061 is an inferred-intent fix** (`model_name`→`model_version`). It creates a UNIQUE(user_id, model_version) constraint that does NOT exist in prod today. On a fresh/empty replay it applies fine; if ever applied to populated data it could fail on duplicates. Confirm the constraint is actually wanted before relying on it.
2. **Idempotency (re-run) is a separate, pre-existing problem**: re-applying the full chain on an already-migrated DB fails on 6 OTHER migrations I did not touch (init_neon, 049, 051, 059, 063, 064). CI does a one-shot fresh replay (not a re-run), so this does not block CI — but it's real tech debt worth a follow-up track.

The 6 edited migration files are LOCAL/uncommitted. "CI green on main" is pending commit+push (awaiting user authorization).

## 2026-05-21 (later) — pushed, then CI exposed a validation blind spot I had to fix

Pushed the 6 migration fixes + test-assertion updates (commit `7e5485cd`). CI's **Migration Validation** job still FAILED: `005_observation_tables.sql:35: ERROR: role "neondb_owner" does not exist`.

**My Neon-branch replay had a blind spot**: Neon's database owner *is* `neondb_owner`, so it always exists there — every `GRANT ... TO neondb_owner` succeeded silently. CI uses a vanilla `postgres:15-alpine` service with no such role. ~50 migrations reference `neondb_owner`; some wrap the GRANT in `EXCEPTION WHEN undefined_object` (002), many do not (005, …). This is exactly the original report's "pervasive `role neondb_owner does not exist`" item that I had **wrongly dismissed as a Docker-only artifact** — it is a real CI failure.

**Fix (correct layer):** rather than edit ~50 migrations, provision the role in CI to mirror the Neon target. Added an idempotent `DO $$ BEGIN CREATE ROLE neondb_owner; EXCEPTION WHEN duplicate_object THEN NULL; END $$;` to `.github/workflows/ci.yml`'s "Apply all migrations sequentially" step, before init_neon. Since my Neon replay already proved the full chain applies 68/68 *with the role present*, providing it in CI should make the job green (pg15-vs-pg17 delta is irrelevant for these column/IMMUTABLE/guard fixes).

**Status correction:** the schema fixes are done + replay-validated, but "CI green on main" is NOT yet confirmed — it requires this ci.yml change to be pushed and the Migration Validation job re-run. Lesson banked: when validating fresh-replay, replicate the CI role environment (no `neondb_owner`), not just Neon.
