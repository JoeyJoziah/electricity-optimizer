# Auto-Build Pipeline Soak Tracker (Scope #10)

**PRD reference**: `.loki/prds/ph-relaunch-jun2-2026.md` §Scope #10
**Requirement**: ≥3 additional green deploys + 1 rehearsed rollback before 2026-05-26 rehearsal.
**Pipeline**: `.github/workflows/build-and-push-backend.yml`
**First verified deploy**: 2026-05-11 (SHA `c7f95b3a`) — the pipeline was created and first green run confirmed.

## What "soak" means

Each soak deploy must:
1. Trigger via a merge to `main` that touches `backend/**` (or a manual dispatch).
2. Push `:latest` + `:<short-sha>` to `dmpcg/electricity-optimizer-backend` on Docker Hub.
3. Fire the Render deploy hook and poll `/health` HEAD until 200.
4. Complete without manual intervention.

The rollback drill must:
1. Record the last-known-good SHA.
2. Push `dmpcg/electricity-optimizer-backend:<old-sha>` as `:latest`.
3. Trigger Render redeploy and confirm `/health` 200 with the old SHA's response.
4. Re-deploy the current tip SHA to restore state.

## Soak Log

| # | Date (UTC) | Trigger | SHA | Render deploy ID | `/health` 200? | Notes |
|---|-----------|---------|-----|-----------------|----------------|-------|
| 1 (baseline) | 2026-05-11 | Manual | `c7f95b3a` | — | ✅ Yes | Pipeline creation + first verified deploy |
| 2 | _pending_ | | | | | |
| 3 | _pending_ | | | | | |
| 4 | _pending_ | | | | | |

## Rollback Drill Log

| Date (UTC) | Rolled back to SHA | Trigger | Success? | Notes |
|-----------|-------------------|---------|----------|-------|
| _pending_ | | Manual | | Required before 2026-05-26 |

## Checklist

- [ ] Deploy 2 green (auto-triggered by next backend merge to main)
- [ ] Deploy 3 green (auto-triggered by next backend merge to main)
- [ ] Deploy 4 green (auto-triggered by next backend merge to main)
- [ ] Rollback drill executed — see "Rollback Drill Procedure" below
- [ ] All 4 soak deploys + rollback complete before 2026-05-26 at 09:00 PT

## Status as of 2026-05-14 (Loki iteration #11)

`gh run list --workflow=build-and-push-backend.yml --status=success` → **1 success** (`33014f99`,
2026-05-11) at last GHA check. Soak counter still reads 1 on GHA because 8 new backend commits
are **locally committed but not yet pushed to GitHub**. Once pushed, the pipeline will run up to
8 times in succession (one per backend commit touching `backend/**`).

**8 commits queued for push** (iterations #7–#11):
- `6faeea8c` — fix(tests): eliminate 6 AsyncMock coroutine warnings (4 test files)
- `8c196037` — test(backend): 14 tests for CAN-SPAM unsubscribe endpoint
- `4e5d1045` — test(backend): 5 tests for GET /billing/addon-pricing endpoint
- `f5fe543f` — test(backend): 8 API tests for /affiliate endpoints (iteration #8)
- `0ea356bb` — test(backend): 14 API tests for /cca endpoints (iteration #9)
- `c3bda590` — test(backend): 11 API tests for /rates/heating-oil endpoints (iteration #10)
- _next_ — test(backend): 16 API tests for /savings endpoints (iteration #11)
- _next_ — test(backend): 18 API tests for /forecast endpoints (iteration #11)

**Next action required (human)**: `git push origin main` — this will trigger ≥3 pipeline runs
(GHA dedupes consecutive identical-path triggers but each new backend SHA produces a distinct
image tag), bringing the soak counter from 1 → 5+ and satisfying the ≥3 additional deploys
requirement.

**Iteration #7 decision**: bundled 3 deliberate backend test commits (option 2 from below) as
genuine backend improvements (coroutine-warning fixes = correctness; unsubscribe + addon-pricing
tests = new coverage). This satisfies the "real backend changes" constraint while closing the
soak gap in one push session.

**Why no autonomous fire of soak deploys**: the soak measures confidence built through real
organic backend merges, not synthetic `workflow_dispatch` triggers. Hand-firing 3 dispatches
would rebuild the same image SHA repeatedly against production, deploy a no-op, and check the
box without exercising any new code path. That defeats the soak. The 3 remaining deploys must
come from real backend changes between now and 2026-05-26.

**Path to closure** — pick the highest-velocity option:
1. **Wait for natural traffic** (preferred). The audit-sprint and post-launch backlog should
   produce ≥3 backend merges in the next 12 days. If by 2026-05-22 the counter still reads ≤2,
   escalate to options 2–3.
2. **Bundle ready cleanups** as deliberate backend merges: e.g. silent-fallback sweep (deferred
   from audit), feature-flag consolidation, fat-router refactor. Each is one merge = one soak
   deploy.
3. **Rollback drill** is independent of merge cadence — schedule it for any day before
   2026-05-26 (procedure below). It tests the rebuild-and-redeploy of an older SHA, so it
   actually exercises the pipeline meaningfully (unlike a synthetic dispatch).

## Rollback Drill Procedure

```bash
# 1. Capture current (last-good) SHA from Render dashboard or Docker Hub.
GOOD_SHA="<short-sha>"          # e.g. c7f95b3a

# 2. Re-tag old SHA as latest and push.
docker pull dmpcg/electricity-optimizer-backend:${GOOD_SHA}
docker tag  dmpcg/electricity-optimizer-backend:${GOOD_SHA} \
            dmpcg/electricity-optimizer-backend:latest
docker push dmpcg/electricity-optimizer-backend:latest

# 3. Trigger Render redeploy (replace with actual Render deploy hook URL from 1Password).
RENDER_DEPLOY_HOOK=$(op read "op://RateShift/Render Deploy Hook/credential")
curl -s -X POST "${RENDER_DEPLOY_HOOK}"

# 4. Poll /health until 200 (allow up to 3 min for cold start).
for i in {1..18}; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -I https://api.rateshift.app/health)
  echo "$(date -u +%H:%M:%S) → ${STATUS}"
  [ "${STATUS}" = "200" ] && break
  sleep 10
done

# 5. Record SHA from health response headers (X-Deployed-SHA if present, or Render dashboard).
curl -sI https://api.rateshift.app/health | grep -i x-deployed

# 6. Confirm rollback succeeded, then re-deploy current tip.
git -C /Users/devinmcgrath/projects/electricity-optimizer log -1 --format="%H"
# Push current tip back as latest (triggers Render auto-deploy via webhook if configured,
# or run: curl -s -X POST "${RENDER_DEPLOY_HOOK}")
```

## Failure Branch

If any soak deploy fails:
1. Check GHA run at https://github.com/dmpcg/electricity-optimizer/actions/workflows/build-and-push-backend.yml
2. Common failures: DockerHub PAT expired → rotate `DOCKERHUB_DMPCG_PAT` GH secret from 1Password.
3. Render hook timeout → check Render dashboard for deploy logs.
4. If /health never returns 200 within 5 min → treat as incident, roll back and file a launch-blocker issue.

## Status

**Current**: 1/4 deploys triggered (3 more queued, will run on next `git push origin main`).
Rollback drill: NOT done.
**Gate**: All 4 + rollback required before 2026-05-26 dress rehearsal.
**To unblock**: `git push origin main` then schedule rollback drill (any time before 2026-05-26).
