# Execution Log — ci-migration-chain-replay_20260515

## 2026-05-15 — Track created from agent full-chain replay

Discovered when the `ci-migration-004-stripe-customer-id_20260515` agent attempted full-chain `psql -f` replay against `postgres:16-alpine`. After fixing 003 + 004 + 037 (stripe block), the chain still failed at 6 more independent points.

Captured as a single tracking entry rather than 6 separate tracks because:
1. Several errors cluster (049/051/053/059/061 are all schema-shape / constraint conflicts that may share a root cause)
2. Strategic choice required first: do we keep investing in fresh-replay as a quality bar (paths A/B), or switch CI to dump-based apply (path C)
3. Don't want to spawn 6 conductor tracks before the strategic interview happens

Inventory captured in plan.md from agent report.

Launch-blocker (or scope-changer) per "tests are sacred" — `ph-relaunch-jun2_20260515` depends on either Migration Validation being green OR the strategic decision to redefine what "green" means for that workflow.
