# Dress Rehearsal Runbook — Tue 2026-05-26 (Scope #16)

**PRD reference**: `.loki/prds/ph-relaunch-jun2-2026.md` §Scope #16
**Date**: Tuesday, 2026-05-26 (6 days before PH launch)
**Duration**: ~4–6 hours (morning block recommended)
**No PH submission today.** This is a dry run only.

## Pre-Conditions (must be true before starting)

| Item | Gate |
|------|------|
| All 6 PH gallery screenshots captured (Scope #12) | docs/launch/assets/ has 01–06 |
| Render Starter upgrade done + verified (Scope #2) | Dashboard shows "Starter" plan |
| Pipeline soak: 3+ green deploys + 1 rollback (Scope #10) | docs/launch/pipeline-soak-tracker.md all checked |
| CF Worker cache soak check complete (Scope #11) | docs/launch/cf-worker-soak-results.md all green |
| k6 installed + STAGING_KEY available | `k6 version` + `op read 'op://RateShift/RATE_LIMIT_BYPASS_KEY/credential'` |

If ANY pre-condition is not met, do not start. Fix blockers, then reschedule. Slip rule: first slip = Jun 9. See PRD §Risks #6.

---

## Phase 1: System State Verification (30 min)

### 1.1 Production health baseline

```bash
# Backend health (should be 200)
curl -sI https://api.rateshift.app/health | head -5

# Frontend (should render)
curl -sI https://www.rateshift.app/ | head -5

# Neon pooler (check via backend)
curl -s https://api.rateshift.app/health | jq '{db: .db, uptime: .uptime}'

# UptimeRobot: check all 4 monitors at https://stats.uptimerobot.com/d4sbPJ124X
```

- [ ] Backend `/health` 200 ✓
- [ ] Frontend 200 ✓
- [ ] DB connection healthy ✓
- [ ] All 4 UptimeRobot monitors UP ✓

### 1.2 Drip cron smoke-test

```bash
# Fire drip processor manually against staging (not prod — use staging DB if available).
# This verifies the GHA cron won't fail silently on launch day.
INTERNAL_KEY=$(op read 'op://RateShift/INTERNAL_API_KEY/credential')
curl -s -X POST https://api.rateshift.app/api/v1/internal/drip/process \
  -H "X-API-Key: ${INTERNAL_KEY}" | jq .
```

- [ ] Drip endpoint responds 200 (or 202) ✓
- [ ] No Sentry errors from the call ✓

---

## Phase 2: Synthetic Load Injection (60–90 min)

### 2.1 Pre-load state

```bash
# Record current /health SHA and Render deploy ID before load test
curl -s https://api.rateshift.app/health | jq '{version: .version, sha: .sha}'
```

### 2.2 Run k6 load test (full profile)

```bash
cd /Users/devinmcgrath/projects/electricity-optimizer
STAGING_KEY=$(op read 'op://RateShift/RATE_LIMIT_BYPASS_KEY/credential')
STAGING_KEY="${STAGING_KEY}" ./loadtest/run.sh
```

**Expected output**: Results JSON written to `loadtest/results/`. Copy summary to `docs/launch/load-test-results.md`.

**Pass thresholds** (from PRD Scope #8):
| Metric | Threshold |
|--------|-----------|
| p95 response time | < 3,000 ms |
| HTTP failure rate | < 5% |
| CF cache hit rate | ≥ 70% |

- [ ] k6 run completed ✓
- [ ] p95 < 3,000 ms ✓
- [ ] Fail rate < 5% ✓
- [ ] CF hit rate ≥ 70% ✓
- [ ] Results recorded in docs/launch/load-test-results.md ✓

### 2.3 Post-load health check

```bash
curl -sI https://api.rateshift.app/health | head -5
```

- [ ] Backend still 200 after load ✓
- [ ] No new Sentry errors from load test window ✓

---

## Phase 3: Rollback Drill (30–45 min)

> This serves double-duty: also satisfies the pipeline soak rollback requirement (Scope #10).

```bash
# 3.1 Record current good SHA
CURRENT_SHA=$(curl -s https://api.rateshift.app/health | jq -r '.sha // "unknown"')
echo "Good SHA: ${CURRENT_SHA}"

# 3.2 Pull previous image (substitute real previous SHA)
PREV_SHA="<sha-from-docker-hub-history>"   # fill in before running
docker pull dmpcg/electricity-optimizer-backend:${PREV_SHA}
docker tag  dmpcg/electricity-optimizer-backend:${PREV_SHA} \
            dmpcg/electricity-optimizer-backend:latest
docker push dmpcg/electricity-optimizer-backend:latest

# 3.3 Trigger Render redeploy
RENDER_HOOK=$(op read 'op://RateShift/Render Deploy Hook/credential')
curl -s -X POST "${RENDER_HOOK}"

# 3.4 Wait for /health 200
for i in {1..18}; do
  STATUS=$(curl -so /dev/null -w "%{http_code}" -I https://api.rateshift.app/health)
  echo "$(date -u +%H:%M:%S) → ${STATUS}"
  [ "${STATUS}" = "200" ] && break
  sleep 10
done

# 3.5 Confirm rollback SHA
curl -s https://api.rateshift.app/health | jq .sha

# 3.6 Re-deploy current tip
curl -s -X POST "${RENDER_HOOK}"
# Wait for 200
for i in {1..18}; do
  STATUS=$(curl -so /dev/null -w "%{http_code}" -I https://api.rateshift.app/health)
  echo "$(date -u +%H:%M:%S) → ${STATUS}"
  [ "${STATUS}" = "200" ] && break
  sleep 10
done
```

- [ ] Previous SHA identified and available on Docker Hub ✓
- [ ] Rollback triggered ✓
- [ ] `/health` returned 200 with old SHA ✓
- [ ] Tip SHA re-deployed ✓
- [ ] `/health` returned 200 with current SHA ✓
- [ ] Mark rollback complete in docs/launch/pipeline-soak-tracker.md ✓

---

## Phase 4: Product Hunt Draft Check (45 min)

> The PRD says "No PH submission" — this verifies the listing is ready, not that we publish.

### 4.1 Open PH draft

- Log in at producthunt.com
- Navigate to "Products" → draft listing for RateShift
- Verify every field (see `docs/launch/PRODUCT_HUNT.md` §PH Listing Checklist)

### 4.2 Gallery verification

All 6 gallery images from `docs/launch/assets/`:

| # | File | Status |
|---|------|--------|
| 1 | 01-landing.png | [ ] |
| 2 | 02-pricing.png | [ ] |
| 3 | 03-prices.png | [ ] |
| 4 | 04-dashboard.png | [ ] |
| 5 | 05-auto-switcher.png | [ ] |
| 6 | 06-alerts.png | [ ] |

- [ ] All 6 images uploaded and rendering correctly in PH draft ✓
- [ ] Tagline ≤ 60 chars ✓
- [ ] Description ≤ 260 chars ✓
- [ ] Topics: Artificial Intelligence, Productivity, FinTech, Climate Tech ✓
- [ ] Website URL has `?utm_source=producthunt&utm_medium=post` ✓
- [ ] Maker comment drafted (copy from `docs/launch/PRODUCT_HUNT.md`) ✓

---

## Phase 5: Abort-Threshold Validation (30 min)

Walk through each abort scenario from the PRD mentally. Confirm the kill-switch/rollback mechanics are understood:

| Scenario | Threshold | Response |
|----------|-----------|----------|
| Signup failure rate | > 5% over 10 min | Investigate, hold social posts |
| `/health` p95 | > 3s for 10 min | Page + roll back to last green SHA |
| Payment failure rate | > 10% over 15 min | Kill Stripe checkout, post status |
| Error rate | > 2% sustained 15 min | Roll back |
| Drip dispatch error | > 2% over 30 min | Suspend drip cron, investigate |

- [ ] Kill-switch runbook reviewed: `docs/runbooks/auto-rate-switcher-kill-switch.md` ✓
- [ ] Incident response reviewed: `docs/runbooks/incident-response.md` ✓
- [ ] Slip communication template reviewed: LAUNCH_DAY_RUNBOOK.md §Appendix D ✓

---

## Phase 6: Post-Rehearsal Debrief (15 min)

Record findings here or in a GitHub issue tagged `launch-rehearsal`:

- [ ] Load test p95: ________ ms (pass/fail)
- [ ] CF cache hit rate: ________ % (pass/fail)
- [ ] Rollback time: ________ min (acceptable < 5 min)
- [ ] Any blockers found? (Y/N) — if Y, file issue before Fri May 29 gate
- [ ] Confidence level (1–5): _____

### Go/No-Go Pre-Assessment

After rehearsal, answer these before the Fri May 29 gate:

1. Did the load test pass all thresholds? (Y/N)
2. Did the rollback complete in < 5 min? (Y/N)
3. Are all 6 gallery screenshots in the PH draft? (Y/N)
4. Is the drip cron clean (no silent errors)? (Y/N)
5. Any P0 issues found that need a fix before Jun 2? (Y/N)

If any answer is N: fix and re-run the specific phase. If a fix takes > 8h estimated: invoke the 1-week slip rule (Jun 9).

---

## Sign-Off

- [ ] Dress rehearsal complete: **2026-05-26**
- [ ] All phases passed (or issues filed with plans)
- [ ] Scope #16 marked COMPLETE in PRD
- [ ] Go/No-Go gate assessment ready for **Fri 2026-05-29**
