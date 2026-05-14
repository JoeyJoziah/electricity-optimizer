# Render Starter Upgrade + Cold-Start Verification Runbook

**Scope**: PRD Scope #2 — PH relaunch Jun 2 2026
**Deadline**: 2026-05-16
**Service**: `electricity-optimizer-backend` (srv-d649uhur433s73d557cg)
**Plan path**: Free → **Starter $7/mo** → (conditional) Standard $25/mo if Starter saturates load test

## Why

Render Free tier spins down after 15 min idle → cold-starts add 30-90s on first request.
At PH launch, first 100+ visitors would hit a cold backend simultaneously and bounce.
Starter ($7/mo) keeps the instance warm 24/7 and gives 0.5 CPU / 512 MB (vs Free 0.1 CPU / 512 MB).
Standard ($25/mo) bumps to 1 CPU / 2 GB if load test indicates saturation.

## Pre-checks (before clicking upgrade)

- [ ] Auto-build pipeline green ≥3 deploys (PRD Scope #10) — confirms revert path works
- [ ] `gh run list --workflow=build-and-push-backend.yml --status=success --limit=10` shows recent successes
- [ ] `/health` returning 200 HEAD with fresh `version` field (sanity: pipeline is publishing)
- [ ] 1Password "Render Service Account" credentials accessible
- [ ] CF Worker `gateway-health` workflow green within last 12h

## Upgrade procedure

1. Log in to Render dashboard → `electricity-optimizer-backend` → **Settings → Instance Type**
2. Select **Starter** ($7/mo). Confirm. Render rolls a new instance — ~3-5 min.
3. While rolling: monitor `https://api.rateshift.app/health` from a second terminal:
   ```bash
   while true; do curl -sw "\n%{http_code} %{time_total}s\n" -o /dev/null -X HEAD https://api.rateshift.app/health; sleep 5; done
   ```
4. Watch CF Worker `/internal/gateway-stats` for 502/503 spikes during cutover.

## Cold-start verification (post-upgrade)

Starter should NOT spin down. Verify by leaving the service idle 20 min then probing:

```bash
# Idle wait
sleep 1200

# Cold probe — should be <500ms on Starter
time curl -sw "%{http_code} %{time_total}s" -o /dev/null https://api.rateshift.app/health
```

**Pass**: response < 500ms AND HTTP 200
**Fail (spin-down occurred)**: response > 5s → escalate; Starter spec changed or misconfig

## Load profile capture

Run small load probe to baseline Starter:

```bash
# 30 RPS for 60s against /health (cached at CF, light origin touch)
hey -z 60s -q 30 -c 10 https://api.rateshift.app/health
```

Capture p50 / p95 / p99 + max RPS. Store in `docs/launch/load-test-results.md`.

## Standard $25/mo trigger criteria

Pre-commit to Standard upgrade if ANY of:
- 300 RPS load test (PRD Scope #8) sees p95 > baseline × 2 on Starter
- CPU usage > 70% sustained 5 min during synthetic load
- Memory > 80% sustained 5 min during synthetic load
- 5xx error rate > 0.5% during 300 RPS probe

If triggered: bump to Standard same procedure (Settings → Instance Type → Standard).
No rollback needed; Standard is strictly more resource than Starter.

## Rollback (if Starter introduces regression)

1. Render dashboard → Settings → Instance Type → **Free** → Confirm
2. Render rolls back to Free instance — ~3-5 min
3. Verify `/health` 200 from CF Worker side
4. Document failure mode in `docs/launch/INFRA_UPGRADE_RUNBOOK.md` post-mortem

## Acceptance

- [ ] Plan upgraded to Starter
- [ ] Cold-start probe < 500ms after 20-min idle
- [ ] Load profile captured in `docs/launch/load-test-results.md`
- [ ] No `/health` 5xx during cutover window
- [ ] Decision recorded: stay on Starter OR upgrade to Standard

**Verified by**: Devin McGrath
**Verified on**: ____________
