# CF Worker Cache 7-Day Soak Checkpoint — 2026-05-19

**Scope**: PRD Scope #11 — PH relaunch Jun 2 2026
**Deadline**: 2026-05-19 (7 days after 2026-05-11 worker tuning landed)
**Worker**: `rateshift-api-gateway` at `api.rateshift.app/*`
**Soak start**: 2026-05-11 — commits `881635aa` / `c7f95b3a` / subsequent cache-control / origin timeout / sampling rate tuning passes
**Soak end**: 2026-05-19 (checkpoint date)

## What we're confirming

The 2026-05-11 worker tuning pass shipped four cache-correctness changes:
1. `/health` excluded from cache (was poisoning cache with HEAD/GET key collision)
2. `storeInCache` gated to `method === "GET"` (prevents HEAD-cached body reuse)
3. Origin fetch wrapped in `AbortSignal.timeout(25s)` + `AbortSignal.any([..., request.signal])` — emits 504 on origin timeout, 499 on client disconnect
4. `head_sampling_rate = 0.25` for observability cost control

After 7 days in production, validate steady-state behavior is healthy before PH launch.

## Metrics to capture on 2026-05-19

Run from local workstation against CF dashboard + `/internal/gateway-stats`:

```bash
# Per-isolate counters
curl -H "X-Internal-API-Key: $INTERNAL_API_KEY" https://api.rateshift.app/internal/gateway-stats | jq

# CF analytics (last 7 days)
# Dashboard → Workers → rateshift-api-gateway → Metrics tab
```

### Pass criteria (all required)

| Metric | Target | Source |
|---|---|---|
| Cache hit rate (overall) | ≥ 60% | CF dashboard → Cache analytics |
| Cache hit rate (`/api/v1/prices`) | ≥ 80% | gateway-stats per-route counters |
| Cache hit rate (`/health`) | **0%** (must be bypass) | gateway-stats |
| 504 rate (origin timeout) | < 0.1% of requests | CF logs filter `status:504` |
| 499 rate (client disconnect) | < 1% of requests | CF logs filter `status:499` |
| KV reads/day | stable trend, no growth spike | CF dashboard → KV metrics |
| KV writes/day | stable trend | CF dashboard → KV metrics |
| Worker CPU time p99 | < 30ms | CF dashboard → Workers metrics |
| 5xx rate (origin) | < 0.5% | CF dashboard |

### Findings (fill in on 2026-05-19)

- Cache hit rate (overall): ____
- Cache hit rate (`/api/v1/prices`): ____
- `/health` cache hit rate: ____ (must be 0%)
- 504 rate: ____
- 499 rate: ____
- KV reads/day (7-day trend): ____
- KV writes/day (7-day trend): ____
- Worker CPU p99: ____
- 5xx rate: ____
- Spurious cache invalidations observed: ____
- Origin timeout incidents: ____

## Decision

- [ ] **PASS** — all targets met, soak validated, proceed to dress rehearsal 2026-05-26
- [ ] **CONDITIONAL PASS** — 1-2 metrics borderline; document mitigation and proceed
- [ ] **FAIL** — rollback worker tuning or block launch until investigated

**Validated by**: ____________
**Validated on**: ____________
**Commit SHA at checkpoint**: ____________

## Related artifacts

- Pipeline soak tracker: [pipeline-soak-tracker.md](pipeline-soak-tracker.md)
- Initial cache-fix postmortem (2026-05-11): commit `881635aa`
- Soak results log: [cf-worker-soak-results.md](cf-worker-soak-results.md)
