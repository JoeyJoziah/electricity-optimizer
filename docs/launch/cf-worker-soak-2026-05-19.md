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

Run from local workstation against CF dashboard + the gateway-stats endpoint:

```bash
# Per-isolate counters — CORRECTED path + header (2026-05-27):
#   path:   /api/v1/internal/gateway-stats   (NOT /internal/gateway-stats)
#   header: X-API-Key                        (NOT X-Internal-API-Key)
# Source of truth: workers/api-gateway/src/config.ts (route regex) +
#                  src/middleware/internal-auth.ts (header name)
KEY=$(op item get "API Secrets" --vault "Electricity Optimizer" --fields label=internal_api_key --reveal)
curl -H "X-API-Key: $KEY" https://api.rateshift.app/api/v1/internal/gateway-stats | jq

# CF analytics (last 7 days)
# Dashboard → Workers → rateshift-api-gateway → Metrics tab
```

> **Doc-path correction (2026-05-27)**: the original command above (and the `/internal/gateway-stats`
> + `X-Internal-API-Key` references in CLAUDE.md) were wrong — they reached the FastAPI origin and
> returned `{"detail":"Not Found"}` (404). The worker only intercepts `/api/v1/internal/gateway-stats`
> and authenticates via `X-API-Key`. The 1Password item is `API Secrets` (field `internal_api_key`)
> in the **Electricity Optimizer** vault — there is no `op://RateShift/INTERNAL_API_KEY` path.

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

### Findings (partial capture 2026-05-27 — checkpoint run 8 days late; soak window now ~16 days)

**gateway-stats snapshot** (`/api/v1/internal/gateway-stats`, 200 OK):
```json
{ "counters": { "cacheReads": 0, "cacheWrites": 0, "cacheHits": 0, "cacheMisses": 0,
                "rateLimitChecks": 0, "degradedResponses": 0, "totalRequests": 1 },
  "startedAt": "1970-01-01T00:00:00.000Z", "degraded": false, "cacheHitRate": 0 }
```

> **Critical methodology finding**: this endpoint returns **per-isolate, in-memory** counters that
> reset on every cold start (`startedAt` is epoch-0 = uninitialized). The snapshot above hit a *cold*
> isolate that had served exactly 1 request — my own. It is therefore **NOT a valid source of
> aggregate cache-hit-rate or traffic metrics**. The checkpoint's per-route cache-hit-rate rows
> (e.g. `/api/v1/prices`) cannot be sourced here. **All 9 pass-criteria metrics below must come from
> the Cloudflare dashboard** (Workers Analytics / Cache Analytics / KV metrics), which requires
> dashboard login — not capturable programmatically from this workstation.

- Cache hit rate (overall): ____ **(REQUIRES CF DASHBOARD — operator)**
- Cache hit rate (`/api/v1/prices`): ____ **(REQUIRES CF DASHBOARD — per-isolate counter invalid)**
- `/health` cache hit rate: ____ (must be 0%) **(REQUIRES CF DASHBOARD)**
- 504 rate: ____ **(REQUIRES CF logs filter `status:504`)**
- 499 rate: ____ **(REQUIRES CF logs filter `status:499`)**
- KV reads/day (7-day trend): ____ **(REQUIRES CF DASHBOARD → KV metrics)**
- KV writes/day (7-day trend): ____ **(REQUIRES CF DASHBOARD → KV metrics)**
- Worker CPU p99: ____ **(REQUIRES CF DASHBOARD → Workers metrics)**
- 5xx rate: ____ **(REQUIRES CF DASHBOARD)**
- Spurious cache invalidations observed: ____ **(REQUIRES CF DASHBOARD)**
- Origin timeout incidents: ____ **(REQUIRES CF DASHBOARD / Sentry)**

**What WAS confirmed programmatically (2026-05-27)**:
- gateway-stats endpoint is live and auth works (`X-API-Key`, path `/api/v1/internal/gateway-stats`) — 200 OK
- worker is **not degraded** (`degraded: false`)
- `/health` returns 200 (HEAD probe) — cache-bypass behavior not independently re-verified here

## Decision

- [ ] **PASS** — all targets met, soak validated, proceed to dress rehearsal 2026-05-26
- [ ] **CONDITIONAL PASS** — 1-2 metrics borderline; document mitigation and proceed
- [ ] **FAIL** — rollback worker tuning or block launch until investigated
- [x] **INCOMPLETE (2026-05-27)** — endpoint health + auth confirmed; 9 dashboard-sourced metrics
      still pending operator capture from the Cloudflare dashboard. Soak window is now ~16 days
      (well past the 7-day minimum), so steady-state is amply established — only the *measurement*
      remains. **Operator action**: log into CF dashboard, fill the 9 rows, render PASS/FAIL before
      the Fri 2026-05-29 Go/No-Go gate.

**Validated by**: Loki interactive session (partial — programmatic slice only)
**Validated on**: 2026-05-27
**Commit SHA at checkpoint**: see `git rev-parse HEAD` at commit time

## Related artifacts

- Pipeline soak tracker: [pipeline-soak-tracker.md](pipeline-soak-tracker.md)
- Initial cache-fix postmortem (2026-05-11): commit `881635aa`
- Soak results log: [cf-worker-soak-results.md](cf-worker-soak-results.md)
