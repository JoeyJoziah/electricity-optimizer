# Load Test Results — PH Relaunch (Scope #8)

**Status**: Awaiting first execution against staging.
**Owner**: @devmcgrath
**PRD reference**: `.loki/prds/ph-relaunch-jun2-2026.md` §Scope #8
**Deadline**: 2026-05-22 (≥10 days pre-launch soak)

## Test Profile

- **Tool**: k6 (script at `scripts/load-test/k6-launch.js` → `loadtest/rateshift-staging.js`)
- **Wrapper**: `loadtest/run.sh` (`--quick` smoke or full launch run)
- **Target**: 300 RPS sustained × 5 min, 30 % cache-miss ratio
- **Surface**: `https://api.rateshift.app` (CF Worker → Render Starter → Neon pooler)
- **Endpoint mix**: `/health` 35 %, `prices/current` 25 %, `prices/history` 15 %, `suppliers` 10 %, `public/rates` 5 %, `auth/session` 5 %, `unsubscribe` 5 %

## Pass Thresholds (mirrors PRD §15 abort rules)

| Metric                       | Threshold |
| ---------------------------- | --------- |
| `http_req_duration` p95      | < 3 000 ms |
| `http_req_failed` rate       | < 5 %      |
| Origin (Render) p95          | < 2 500 ms |
| CF Worker cache hit rate     | ≥ 70 %     |
| Neon pooler connection wait  | < 250 ms   |

## Activation Checklist

1. `brew install k6` (or `apt install k6`).
2. Obtain `STAGING_KEY` from 1Password (entry: "RateShift — RATE_LIMIT_BYPASS_KEY").
3. `STAGING_KEY=<key> ./loadtest/run.sh` (full run) or `./loadtest/run.sh --quick` (30 VU smoke).
4. Results JSON written to `loadtest/results/` (git-ignored).
5. Copy summary numbers into the "Run Log" table below.
6. Commit this file with results table populated; reference run timestamp.

## Run Log

| Date (UTC) | RPS | p95 (ms) | Fail rate | CF hit % | Notes |
| ---------- | --- | -------- | --------- | -------- | ----- |
| _pending_  |     |          |           |          | First run scheduled before 2026-05-22 |

## Failure Branch

If any threshold breaches:

1. Capture JSON + summary; attach to GitHub issue tagged `launch-blocker`.
2. Trigger PRD §15 abort threshold review.
3. Cross-link Neon connection-budget audit (Scope #9) and CF Worker soak (Scope #11).
4. Re-run after fix; require two consecutive green runs to clear blocker.

## References

- Runbook: `docs/runbooks/load-test.md`
- k6 script: `loadtest/rateshift-staging.js`
- Wrapper: `loadtest/run.sh`
- Abort thresholds: `docs/runbooks/LAUNCH_DAY_RUNBOOK.md` §Abort Thresholds
