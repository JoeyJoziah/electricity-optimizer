# Implementation Plan: Product Hunt Relaunch — Jun 2 2026

**Track ID:** ph-relaunch-jun2_20260515
**Created:** 2026-05-15
**Status:** [~] In Progress
**Target launch:** Tuesday 2026-06-02 12:01am PT (T-18 days)
**Source PRD:** `.loki/prds/ph-relaunch-jun2-2026.md` (v3.2, multi-agent reviewed × 3 rounds + clarity-gate 9/9)
**Slip rule:** At Fri 2026-05-29 gate, ANY in-scope item incomplete or not formally waived → slip exactly 1 week to Jun 9. Second slip → archive PRD, write v4.
**Depends on:**
  - `ci-red-triage_20260515` (CI must be green before launch — "tests are sacred")
  - `pre-launch-completion_20260407` Task 2.3 (social media accounts) — overlaps with Phase 1 here
  - `launch-execution_20260407` is the prior PH launch track (POSTPONED INDEFINITELY); this track supersedes it for the Jun 2 attempt

## Overview

Wraps the 6 remaining in-scope items from the relaunch PRD plus the dress rehearsal and the residual compliance follow-up. The PRD's other 12 scope items (#4 impl, #5, #6, #7, #9, #13 CAN-SPAM, #14, #15, #17, #18) are already closed per MEMORY.md; this track owns the rest plus go/no-go gate.

**Phase organization** mirrors PRD's 5 buckets (Identity / Infra / Comms / Verification / Governance) collapsed onto T-minus weeks.

---

## Phase 1: Identity (T-17 to T-15, primarily human-gated)

- [ ] Task 1.1: Claim social handles — `@rateshift` on X, Bluesky, LinkedIn
  - **Source:** PRD Scope #1 (overdue from 2026-05-13)
  - **Action:** Sign up + verify each handle. If `@rateshift` taken, fall back to `@rateshiftapp` consistently AND run a 1-day copy sweep across `docs/launch/FINAL_COPY.md`, `docs/launch/SOCIAL_MEDIA_DRAFTS.md`, `docs/launch/HN_REDDIT_POSTS.md`
  - **Blocked on:** human action — can't be automated
  - **Coordination:** also closes `pre-launch-completion_20260407` Task 2.3
  - **Verify:** all 3 handles accessible, branded (avatar + bio + link to rateshift.app)

- [ ] Task 1.2: Refresh PH gallery screenshots
  - **Source:** PRD Scope #12 (unconditional — UI drifted after audit sprint)
  - **Action:** Capture 6 fresh PH gallery shots: dashboard, price forecast, supplier comparison, savings calculator, mobile view, auto-switcher. Use `claude-in-chrome` against staging or local with seeded demo data (NOT a fresh signup).
  - **Demo-data dep:** test account with pre-populated forecasts and a savings number visible
  - **Output:** `docs/launch/assets/gallery-{1..6}.png` (1920x1080)
  - **Verify:** visual diff against April baselines; nothing showing empty states

---

## Phase 2: Infra (T-17 to T-13, mostly human-gated dashboard work)

- [ ] Task 2.1: Render Starter upgrade + cold-start verification
  - **Source:** PRD Scope #2 (target 2026-05-16 — tomorrow)
  - **Action:** Render dashboard → srv-d649uhur433s73d557cg → Plan → Starter ($7/mo). Wait 2-3 min for restart. Validate cold-start gone with curl loop.
  - **Pre-committed escalation:** if Starter saturates under load test (Phase 3 / Scope #8), upgrade to Standard ($25/mo) without re-approval — already authorized in PRD
  - **Verify:** `curl -w "@curl-format" https://api.rateshift.app/health` shows no >2s cold-start delay across 5 requests after 30 min idle

- [ ] Task 2.2: Key rotation (P0-6) + firewall hardening
  - **Source:** PRD Scope #3 (target 2026-05-20 — ≥13-day soak before launch)
  - **Pre-req:** rotation plan + rollback documented in DR runbook (`docs/runbooks/DISASTER_RECOVERY.md`)
  - **Sequenced BEFORE 2.3** so two secrets-management changes don't share a soak window
  - **Action:** Rotate: Stripe webhook secret, Resend API key, Composio API key, OAUTH_STATE_SECRET, ML_MODEL_SIGNING_KEY, INTERNAL_API_KEY, RATE_LIMIT_BYPASS_KEY (CF), ORIGIN_SECRET (CF — see 2.3). Update on Render via API. Verify each service still works.
  - **Risk:** outage if rotation order wrong; do during low-traffic window
  - **Verify:** `/health` 200 throughout; webhook smoke-test fires; Composio agent test query returns

- [ ] Task 2.3: Activate origin shared-secret header (PRD Scope #4 activation)
  - **Source:** Implementation already complete (CFOriginSecretMiddleware shipped 2026-05-12). Activation is human-gated.
  - **Action:**
    ```
    openssl rand -hex 32   # capture value
    wrangler secret put ORIGIN_SECRET --name rateshift-api-gateway   # CF Worker
    # then on Render: set CF_ORIGIN_SECRET env var to same value
    ```
  - **Bypass paths confirmed:** `/health`, `/api/v1/webhooks/`, `/metrics`
  - **Safety:** middleware is no-op until both sides set; safe to deploy now, activate after key rotation completes
  - **Verify:** `curl https://api.rateshift.app/api/v1/prices/current` (via CF Worker) returns 200; `curl https://srv-d649uhur433s73d557cg.onrender.com/api/v1/prices/current` (direct origin bypass attempt) returns 403 with origin-secret error

---

## Phase 3: Verification (T-13 to T-7)

- [ ] Task 3.1: Load test 300 RPS for 5 min against staging
  - **Source:** PRD Scope #8 (target 2026-05-22)
  - **Pre-req:** `brew install k6` (script already exists per MEMORY); `STAGING_KEY` env var set
  - **Targets:** CF Worker → Render Starter → Neon pooler. 30% cache-miss ratio on signup/forecast endpoints. p95 baseline captured.
  - **Decision gate:** if Starter saturates, trigger pre-committed Standard upgrade (Phase 2.1 fallback)
  - **Output:** `docs/launch/load-test-results.md` updated with run telemetry
  - **Verify:** p95 < 1.5× baseline; no 5xx error rate; Neon connections stayed within budget (per Scope #9 audit: 30 connections / 901 max)

- [ ] Task 3.2: Auto-build pipeline soak — ≥3 green deploys + 1 rollback drill
  - **Source:** PRD Scope #10 (currently 2/3 honest deploys per memory: 5/14 batch + 5/15 pin fix)
  - **Action:** 1 more real backend/** push that triggers `build-and-push-backend.yml`, plus 1 rehearsed rollback (Render Manual Deploy → previous commit, verify `/health` 200 with old uptime)
  - **Verify:** `docs/launch/pipeline-soak-tracker.md` updated with 3rd green deploy + rollback drill outcome

- [ ] Task 3.3: CF Worker cache 7-day soak telemetry checkpoint
  - **Source:** PRD Scope #11 (target 2026-05-19)
  - **Action:** Pull last 7 days of CF Worker stats from `/internal/gateway-stats`. Confirm: cache hit rate stable, 504/499 rates trending down, KV cost not climbing
  - **Output:** `docs/launch/cf-worker-soak-2026-05-19.md` updated with snapshot
  - **Verify:** all 3 metrics within tolerance; if not, file regression issue

---

## Phase 4: Comms residual (T-10 to T-7, mixed)

- [ ] Task 4.1: ToS / Privacy Policy currency review
  - **Source:** PRD Scope #13 residual (CAN-SPAM portion already complete 2026-05-12; this is the manual review)
  - **Action:** Read `frontend/app/terms/page.tsx` + `frontend/app/privacy/page.tsx` + `frontend/components/auth/DirectLoginForm.tsx` consent links. Confirm: dates current, business address matches drip emails (PO Box 12345, Hartford CT 06101), all data-collection categories listed, third-party processors listed (Stripe, Resend, UtilityAPI, Composio, Sentry, Vercel, Render, Neon).
  - **Output:** updated ToS/PP if drift found; or short note in `docs/launch/compliance-review-2026-05.md` confirming currency
  - **Verify:** `/terms` and `/privacy` render; legal team review unnecessary for currency-only check

- [ ] Task 4.2: UtilityAPI consent copy review
  - **Source:** PRD Scope #13 residual
  - **Action:** Read consent screen presented when user authorizes UtilityAPI OAuth. Confirm: consent scope matches actual data accessed, retention policy stated, $2.25/meter/mo billing disclosed up front (matches PRD user-flow language)
  - **Output:** copy diff if needed; otherwise note in compliance review

---

## Phase 5: Dress Rehearsal + Go/No-Go (T-7 to T-0)

- [ ] Task 5.1: Dress rehearsal Tue 2026-05-26
  - **Source:** PRD Scope #16
  - **Action:** End-to-end run of `docs/launch/LAUNCH_DAY_RUNBOOK.md` including k6 synthetic load injection against staging + rollback drill. NO PH submission.
  - **Pre-req:** all Phase 1-4 tasks closed or formally waived
  - **Output:** rehearsal log captured in `docs/launch/dress-rehearsal-2026-05-26.md`. Any defects fed back as new tasks before Fri 5/29 gate.
  - **Verify:** runbook executable end-to-end; rollback drill restores health within target window

- [ ] Task 5.2: Fri 2026-05-29 go/no-go gate
  - **Source:** PRD slip rule
  - **Action:** Audit every PRD scope item. ANY incomplete or unwaived → slip exactly 1 week to Jun 9. Document decision in `docs/launch/go-nogo-2026-05-29.md`.
  - **Decision criteria:** all 18 scope items closed/waived AND `ci-red-triage_20260515` track closed (CI green) AND dress rehearsal clean
  - **Halt:** human-gated decision

- [ ] Task 5.3: Launch day execution Tue 2026-06-02 12:01am PT
  - **Source:** `docs/launch/LAUNCH_DAY_RUNBOOK.md`
  - **Pre-req:** Task 5.2 returned GO
  - **Action:** Follow runbook timeline (T-24h, T-1h, T-0, T+Nmin, hours 1-6, hours 6-18, hours 18-24)
  - **Halt rules:** abort-threshold trips per Scope #15 (signup failure >5%/10min, /health p95 >3s/10min, payment failure >10%/15min, error rate >2%/15min, drip dispatch >2%/30min)

---

## Completion Criteria

- [ ] All 18 PRD scope items closed or formally waived
- [ ] `ci-red-triage_20260515` track closed (CI fully green on main)
- [ ] Dress rehearsal completed without unresolved defects
- [ ] Go/no-go gate returned GO at Fri 2026-05-29
- [ ] Launch day runbook executed end-to-end
- [ ] 48h post-launch metrics captured against PRD targets (floor: 75 upvotes, 150-250 signups, 3 paid conversions, 99.9% uptime)
- [ ] Post-launch retro filed in `docs/launch/`

## Out of scope

- Full 7-email drip sequence (3 is MVP; rest Q3)
- Pricing A/B test infrastructure (would confound conversion read)
- Growth agent / Paperclip Growth role deployment
- P1-7 (CF site provisioning), P1-20 (GitHub Team)
- Anonymous demo / no-signup product preview
- Silent-fallback sweep, feature-flag consolidation, fat-router refactor

## Risks (from PRD §Risks, condensed)

1. Backend regression during traffic spike → Render Starter + auto-build + soak deploys + UptimeRobot + numeric abort thresholds (Phases 2.1, 3.2)
2. CF Worker rate limits trip legit launch traffic → load test 300 RPS pre-launch (Phase 3.1); raise per-minute caps for launch window if data justifies
3. Self-hunt under-performs vs. Top 10 ambition → floor metric (75 upvotes) is the actual gate; 250 is stretch
4. Social handle squatters → Phase 1.1 + @rateshiftapp fallback
5. Drip deliverability → domain pre-verified; warm-up unnecessary (waitlist count = 0)
6. Date slips again → hard rule, single 1-week slip max, then PRD v4 rewrite
7. Key rotation causes outage → 13-day soak window + DR runbook rollback (Phase 2.2)
8. Solo on-call burnout during 48h hyper-monitoring → accepted risk; mitigations = automated abort thresholds + kill-switch runbooks
