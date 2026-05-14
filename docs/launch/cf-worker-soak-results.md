# CF Worker Cache Soak Results (Scope #11)

**PRD reference**: `.loki/prds/ph-relaunch-jun2-2026.md` §Scope #11
**Requirement**: 7-day soak; telemetry check at 2026-05-19.
**Soak started**: 2026-05-11 (CF Worker cache fixes — HEAD bypass, GET-only store, AbortSignal timeout, head_sampling_rate=0.25)
**Check script**: `scripts/cf-worker-soak-check.sh`

## Soak Window

| Milestone | Date | Status |
|-----------|------|--------|
| Soak start (cache tuning deployed) | 2026-05-11 | ✅ |
| 7-day telemetry check | 2026-05-19 | ⏳ pending |
| Scope #11 complete | after 2026-05-19 check | ⏳ pending |

## Changes That Started the Soak (2026-05-11)

The following CF Worker bugs were fixed before the soak window began:

1. **`/health` cache bypass** — previously `storeInCache` ran on HEAD requests, which could cache the health response and mask stale deployments. Fixed: `storeInCache` now gated to `method === "GET"`.
2. **HEAD/GET key collision** — HEAD requests shared the cache key with GET, poisoning GET caches. Fixed by method-prefixed cache keys.
3. **Origin timeout** — origin fetch wrapped in `AbortSignal.timeout(25s)` so hung origins return 504 instead of holding the isolate.
4. **Client disconnect** — `AbortSignal.any([...request.signal])` returns 499 on early client disconnect.
5. **Sampling rate** — `head_sampling_rate` reduced to 0.25 to limit observability overhead.

## Telemetry Check Results (to be populated 2026-05-19)

Run: `INTERNAL_API_KEY=$(op read 'op://RateShift/INTERNAL_API_KEY/credential') bash scripts/cf-worker-soak-check.sh`

| Metric | Target | Observed | Pass? |
|--------|--------|----------|-------|
| Cache hit rate | ≥ 70% | _pending_ | |
| `/health` CF-Cache-Status | BYPASS or MISS (not HIT) | _pending_ | |
| `prices/current` 2nd call | HIT | _pending_ | |
| p95 latency | < 3,000 ms | _pending_ | |
| 504 rate (7-day) | < 0.1% | _pending_ | |
| 499 rate (7-day) | < 0.5% | _pending_ | |
| KV cost trend | Stable or declining | _pending_ | |

## Failure Branch

If any metric breaches:
1. Capture full output of `cf-worker-soak-check.sh`.
2. File GitHub issue `launch-blocker: CF Worker soak check failed (Scope #11)`.
3. Diagnose via CF dashboard → Workers → analytics.
4. Fix, redeploy, restart the soak clock (new 7-day window required if cache logic changed).
5. Re-run check; require two consecutive green runs to clear.

## Sign-off

- [ ] 2026-05-19 check complete
- [ ] All metrics pass
- [ ] Scope #11 marked COMPLETE in PRD
- [ ] Results table populated above
