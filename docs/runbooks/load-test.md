# Load Test Runbook — PRD Scope #8

**Must complete by**: 2026-05-22 (gates Jun 2 PH rehearsal)
**Script**: `loadtest/rateshift-staging.js`
**Runner**: `loadtest/run.sh`

---

## Overview

300 RPS × 5 minutes against the live CF Worker → Render Starter stack.

- **Target**: `https://api.rateshift.app` (CF Worker in front of Render Starter)
- **Safety margin**: 2× estimated PH-day peak (~150 RPS for a B2C non-featured launch)
- **Cache-miss ratio**: ~30% → ~90 RPS reaches Render origin
- **Pass criteria** (both required to gate rehearsal):
  - `http_req_duration p95 < 3 000 ms`
  - `http_req_failed rate < 5%`

---

## Prerequisites

```bash
brew install k6              # macOS
# or
sudo apt install k6          # Debian/Ubuntu
```

Obtain `RATE_LIMIT_BYPASS_KEY` from 1Password ("RateShift Staging Keys") or Render env vars.

---

## Running the test

### Smoke test first (30 VUs × 30s)
```bash
BASE_URL=https://api.rateshift.app \
STAGING_KEY=<bypass_key> \
./loadtest/run.sh --quick
```

### Full load test (300 VUs × 5 min)
```bash
BASE_URL=https://api.rateshift.app \
STAGING_KEY=<bypass_key> \
./loadtest/run.sh
```

Results are written to `loadtest/results/run-<timestamp>.json` and symlinked as `latest.json`.

---

## Interpreting results

The summary table prints automatically at the end:

```
═══════════════════════════════════════════════════════
 RateShift Load Test — PRD Scope #8 Results
═══════════════════════════════════════════════════════
  http p95 latency  : 412 ms   ✅ PASS
  http error rate   : 0.12%    ✅ PASS
  CF cache hit rate : 71.4%
  origin p95        : 1840 ms  (cache-miss requests only)
  🚀 OVERALL: PASS — proceed to PRD §11 telemetry check
═══════════════════════════════════════════════════════
```

Record these values in the PRD success metrics table under "p95 baseline".

---

## Failure scenarios and remediation

### p95 > 3 000 ms

1. Check CF Worker gateway stats:
   ```bash
   curl -H "X-API-Key: $INTERNAL_API_KEY" \
     https://api.rateshift.app/api/v1/internal/gateway-stats
   ```
   Look for: `cache_hits`, `cache_misses`, `rate_limit_count`

2. If CF cache hit rate < 60% → cache warm-up issue. Run a 50 VU warm-up pass first:
   ```bash
   k6 run --vus 50 --duration 60s loadtest/rateshift-staging.js
   ```
   Then re-run the full test.

3. If origin p95 > 2 500 ms → Render Starter CPU saturating. Options:
   - Upgrade to Render Standard ($25/mo) — Scope #2 action
   - Reduce VUs to find max sustainable RPS; report as constraint

4. If error rate > 5% → check Render deploy logs and Sentry for 5xx root cause.

### CF Worker 429s distorting results

If you see many 429 responses:
- Confirm `STAGING_KEY` is set and matches Render's `RATE_LIMIT_BYPASS_KEY`
- Verify the bypass key is being forwarded correctly: `X-Rate-Limit-Bypass: <key>`

### Neon connection pool exhaustion

If backend returns 503 "connection pool exhausted":
- Check active connections: `SELECT count(*) FROM pg_stat_activity WHERE state='active';`
- Neon pooler cap: 901 connections; 2 workers × 15 = 30 steady-state (97% headroom per Scope #9 audit)
- If pool exhausts under 300 RPS, reduce `db_max_overflow` in `backend/config/settings.py`

---

## Recording the baseline

After a passing run, update the PRD success metrics table:

1. Open `.loki/prds/ph-relaunch-jun2-2026.md`
2. Find the `p95 latency` row in the success metrics table
3. Replace `TBD by May 19` with the actual p95 value from the test
4. Update the target: `baseline × 1.5`

Example:
```
| p95 latency at ~100 RPS origin | **412 ms** | baseline × 1.5 (618 ms) | baseline × 1.5 |
```

---

## Post-test checklist

- [ ] `http_req_duration p95 < 3 000 ms` ✅
- [ ] `http_req_failed rate < 5%` ✅
- [ ] CF cache hit rate recorded
- [ ] Origin p95 recorded (cache-miss baseline)
- [ ] PRD success metrics table updated with p95 baseline
- [ ] Result file committed: `loadtest/results/run-<date>.json`
- [ ] Scope #8 marked complete in `.loki/prds/ph-relaunch-jun2-2026.md`
- [ ] If Render Starter saturates → trigger Scope #2 (upgrade to Standard)
