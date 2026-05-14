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

**Current**: 1/4 deploys complete. Rollback drill: NOT done.
**Gate**: All 4 + rollback required before 2026-05-26 dress rehearsal.
