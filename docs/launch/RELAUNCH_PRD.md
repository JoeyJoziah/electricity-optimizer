# Product Hunt Relaunch — PRD v3.2

**Date**: 2026-05-12 (v3.2 = Round 2 multi-agent fixes applied)
**Author**: Devin McGrath
**Status**: Draft — pending Round 2 multi-agent review + clarity-gate
**Decision log**: `RELAUNCH_PRD_DECISIONS.md`
**Clarity-gate**: `RELAUNCH_PRD_CLARITY_GATE.md`

## Problem

RateShift's original Product Hunt launch was scheduled for 2026-04-14 and passed without execution. Since then, the production backend was discovered to be 34 days stale (fixed 2026-05-11 via auto-build pipeline), social handles are still unclaimed, and launch posts/screenshots drafted in April were never shipped. Existing launch material (6 docs, 197KB) is losing relevance as the UI drifts and copy goes stale. We need a credible, dated relaunch — not another open-ended postponement — to convert the carry-over work into actual signups before the material requires a full rewrite.

## Solution

Pick a single firm PH launch date 3 weeks out (Tue Jun 2 2026 12:01am PT), close the 18 in-scope prerequisites (organized into 5 buckets: identity, infra, comms, verification, governance), do a dress-rehearsal Tue May 26, then ship. Everything else (full drip sequence, pricing A/B, Growth agent, P1-7/20, tech-debt cleanups) is post-launch.

The 5 buckets:
- **Identity** (Scope #1, #12): social handles, gallery screenshots
- **Infra** (Scope #2, #3, #4, #8, #9, #10, #11): Render upgrade, key rotation, origin auth, load test, Neon audit, pipeline soak, cache soak
- **Comms** (Scope #5, #6, #13, #17): drip MVP, waitlist count, compliance, slip-comms plan
- **Verification** (Scope #7, #16, #18): metrics re-baseline, dress rehearsal, forecast capability validation
- **Governance** (Scope #14, #15): cost caps, abort thresholds

## Why Now?

- Backend deploy pipeline is finally trustworthy (1 verified deploy 2026-05-11); largest pre-launch infra risk is resolved pending pipeline soak (3 deploys + 1 rollback drill required before rehearsal)
- Existing launch material drafted Apr 7–8 will become stale if not used soon
- Open-ended postponement masks a tactical blocker (social handles, date) as if strategic
- Status page live, visual regression baselines committed, audit P0s shipped — pre-launch posture is stronger than on Apr 14

## Success Metrics (PROVISIONAL — re-baseline by 2026-05-15 via competitor spot-check)

| Metric | Baseline | Launch-window (48h) target | Notes |
|---|---|---|---|
| PH upvotes | 0 | Floor TBD / Stretch TBD | Both numbers TBD via 2026-05-15 spot-check; placeholder 50/250 only |
| Signups | baseline | 500+ | Anchor metric; TBD-validated 2026-05-15 |
| **Activation: % signups reaching a savings number within 24h** | n/a | **40%** (adjustable per #18 rule) | Query: `SELECT COUNT(DISTINCT sf.user_id) FROM savings_forecasts sf JOIN users u ON u.id = sf.user_id WHERE sf.created_at - u.created_at <= interval '24 hours' AND u.created_at BETWEEN $launch_start AND $launch_end` divided by total signups in same window. Requires forecast-generation capability validated in Scope #18. **Adjustment rule**: target = floor(validated_pass_rate × 0.8), rounded to nearest 5%. Locked at 2026-05-19 once #18 completes |
| Paid conversions (launch-window) | 0 | 5+ (<1%) | Was 5% — recalibrated as launch-window number |
| Paid conversions (90-day cohort) | 0 | 5% of launch signups | Where the 5% target actually lives |
| Backend `/health` uptime, launch window | n/a | ≥99.9% | |
| p95 latency at 300 RPS (CF Worker) | TBD by May 19 | baseline × 1.5 | Measured during load test |
| Drip email open rate (#1 welcome) | n/a | ≥40% | Resend dashboard |

## Scope

**In** (all must complete or be explicitly waived before Jun 2 go/no-go):

1. **Social handles** — claim @rateshift on X, Bluesky, LinkedIn by 2026-05-13. If unavailable, use @rateshiftapp consistently AND run a 1-day copy sweep of FINAL_COPY.md, SOCIAL_MEDIA_DRAFTS.md, HN_REDDIT_POSTS.md to update references.
2. **Render Starter upgrade** + cold-start verification (load on Starter; if saturation → pre-committed Standard $25/mo). Complete by 2026-05-16.
3. **Key rotation (P0-6)** + firewall hardening. Complete by **2026-05-20** (≥13-day soak before launch). Rotation plan + rollback documented in DR runbook before execution. Sequenced BEFORE Scope #4 to avoid two concurrent secrets-management changes in a single soak window.
4. **Origin shared-secret header** (compensating control for deferred P1-7 CF-IP allowlist): Render env var + CF Worker injection. Complete by **2026-05-23** (≥3 days after key rotation soaks). Secret rotation cadence: documented but first rotation post-launch (90 days). Detection: shared-secret header value MUST be redacted in Render logs and CF Worker logs (verify with grep on log samples post-deploy). Leak response: rotate immediately + invalidate CF KV.
5. **Drip MVP — 3 emails** (specified). Implementation: backend dispatches the correct template per state (not Resend conditional logic); each state has its own Resend template ID. Required additions: (a) unit + integration tests for state-selection logic, (b) Sentry alerting on drip dispatch error rate >2% (added to abort thresholds), (c) **snapshot-time rule**: state evaluated at the moment the cron picks the user, NOT at send-queue time. Users who connect after snapshot get Template B (with hedged copy — see below); the corrective Day-3 follow-up is a re-trigger of Template A (NOT a 4th email — it reuses the same template once the forecast becomes available). The hedge prevents the "I just connected — why am I getting a sample?" failure.
   - **#1 Welcome (immediate on signup)**: confirms account, links to "connect utility OR upload bill", sets expectation: "Once you connect a meter or upload a bill, you'll see your savings number — typically within 24 hours." (hedged — no unconditional promise). One template.
   - **#2 Day-2 value**: backend selects template by connection state at snapshot time. Template A (connected, forecast available): personalized savings preview. Template B (not connected OR forecast pending): sample forecast for ZIP captured at signup, plus hedged copy: "If you've already connected, your real number is on its way — check the dashboard."
   - **#3 Day-7 upgrade nudge**: shows Pro feature value (forecast, recommendations). No discount code at launch — preserves pricing integrity. One template.
   - Domain warm-up: only execute if waitlist count (per #6) ≥200; otherwise drop warm-up and rely on existing rateshift.app reputation.
6. **Waitlist locate AND count** — split into two deadlines: (a) **locate by 2026-05-12 (today)** — grep frontend for waitlist form action, search Better Auth `users` table for relevant flag, check Resend/Mailchimp/ConvertKit accounts; document storage in this PRD's appendix. (b) **count by 2026-05-13**. Drives drip warm-up (#5) and email-blast scope.
7. **Metrics re-baseline** — spot-check 5 comparable PH launches (energy / fintech / utility B2C) by 2026-05-15; replace PROVISIONAL targets with grounded numbers.
8. **Load test** — 300 RPS for 5 min against staging (CF Worker + Render Starter + Neon pooler). Sizing rationale: assumption-based pending validation (assumed PH-day peak ~150 RPS for B2C tools × 2 safety margin); if 2026-05-15 spot-check shows comparable launches peaked higher/lower, adjust target. **Cache-miss ratio assumption**: test runs with 30% cache-miss rate (signup/forecast endpoints) to validate origin can absorb worst-case ratio of 90 RPS at Render Starter — adjust ratio after observing first 50 real signups in staging. Complete by 2026-05-22. Captures p95 baseline.
9. **Neon connection-budget audit** — verify max concurrent BE workers × pool size ≤ Neon compute limit; document headroom. **Failure branch**: if headroom <20%, pre-committed action = drop BE worker count by 1 OR upgrade Neon compute one tier (~$15/mo); decision in same audit document.
10. **Auto-build pipeline soak** — ≥3 additional green deploys + 1 rehearsed rollback before May 26 rehearsal.
11. **CF Worker cache 7-day soak** — telemetry check at 2026-05-19 (cache hit rate, 504/499 rates, KV cost trend stable).
12. **Screenshot/gallery refresh** — unconditional. UI has drifted (audit sprint shipped 29 items incl. AutoSwitcherContent split). Capture 6 PH gallery shots fresh.
13. **Compliance check** — verify ToS + Privacy Policy currency, drip emails include CAN-SPAM unsubscribe, UtilityAPI consent copy reviewed.
14. **Cost caps** — alerts at 50%/80%/100% for: CF Worker $20, Neon $30 (pre-commits one-tier upgrade if Scope #9 demands), Resend $20, Render Starter $7 (pre-commits Standard $25 upgrade if Scope #2 saturates). Stripe chargeback/dispute exposure noted as uncapped but tracked: alert if any dispute fires during launch window (rare, but warrants attention).
15. **Launch-day abort thresholds** — canonical location is LAUNCH_DAY_RUNBOOK.md; values listed here for review only:
    - Signup failure rate >5% over 10 min → investigate, hold social posts
    - `/health` p95 >3s for 10 min → page + roll back to last green SHA
    - Payment failure rate >10% over 15 min → kill Stripe checkout, post status
    - Error rate >2% sustained 15 min → roll back
    - Drip dispatch error rate >2% over 30 min → suspend drip cron, investigate
16. **Dress rehearsal Tue 2026-05-26** — end-to-end run of LAUNCH_DAY_RUNBOOK.md including synthetic load injection (k6 against staging) and rollback drill. No PH submission.
17. **Slip communication plan** — if launch slips at Fri May 29 gate, transparent email to signups + waitlist within 24h. Template prepared in advance (LAUNCH_DAY_RUNBOOK.md): 3-bullet structure — (a) what slipped, (b) new date, (c) what you get in the meantime (free-tier access remains, drip continues). Prevents reactive defensive copy under pressure.
18. **Forecast-on-signup capability validation** — confirm that a signup with a connected meter or uploaded bill can produce a savings number within 24h for ≥40% of test scenarios. Run during 2026-05-19 capacity work; if validation fails (<40%), reduce activation target proportionally rather than ship a metric we can't hit by product capability.

**Out**:
- Full 7-email drip sequence (3 is MVP; rest Q3)
- Pricing page A/B test infrastructure (A/B during launch confounds the conversion read)
- Growth agent / Paperclip Growth role deployment
- Full CF-IP allowlist lockdown (P1-7) — compensated via shared-secret header
- GitHub Team upgrade (P1-20)
- Anonymous demo / no-signup product preview — would require new feature build; explicitly accepted as a top-of-funnel leak
- Silent-fallback sweep, feature-flag consolidation, fat-router refactor
- Hunter outreach as a blocker (self-hunt confirmed — see Decision Log #13)

## User Flow (launch day, expanded)

```
PH post goes live 12:01am PT
  → Pre-queued social posts fire on X / Bluesky / LinkedIn
  → Email blast to waitlist (if count ≥200) and existing signups
  → Visitor lands on rateshift.app
  → CF Worker (cached) → Vercel frontend → marketing page
  → Signs up via Better Auth (Google OAuth or email)
  → Onboarding drip email #1 fires within 60s
  → User reaches /connect-utility, sees TWO paths with value framing:
       A. UtilityAPI OAuth — "Auto-sync your usage, real-time alerts,
          set-and-forget" (+$2.25/meter/mo disclosed up front)
       B. Upload bill PDF — "Free, one-time analysis. Re-upload monthly
          for fresh forecasts." (no auto-refresh, no real-time alerts)
  → Forecast page renders savings number (free tier)
  → User clicks Pro-gated tile (forecast detail / recommendations)
       → Locked-feature framing: "Unlock with Pro — $4.99/mo,
         cancel anytime, see your full forecast horizon"
         (copy uses "full forecast horizon" not "full year" —
          horizon depends on meter data availability; avoids
          bait-and-switch for users with <12 months data)
       → Upgrade flow → Stripe Checkout → Pro tier active
  → Free-tier user who doesn't upgrade still sees:
       — Their savings number
       — 1 alert (free tier cap)
       — Day-2 drip with sample ZIP forecast if no connection
       — Day-7 nudge with concrete Pro value

Error paths (linked in LAUNCH_DAY_RUNBOOK.md):
  — UtilityAPI down → fall back to bill upload, banner messaging
  — Region unsupported → set expectation, NOT a dead end:
      "We don't cover {utility} in {state} yet. We're adding utilities
       monthly — you'll be first notified when we add yours. In the
       meantime, upload a bill for a one-time analysis (free)."
       + waitlist capture + bill-upload offer
  — Bill OCR fails → manual entry form with 3 fields (kWh, $, dates)
  — Rate limit hit by legit user → friendly retry-after message
```

## Capacity (solo founder budget)

| Workstream | Min hrs | Max hrs (if conditional branches fire) | Window |
|---|---|---|---|
| Social handles (Scope #1 base) | 2 | 2 | Week 1 |
| Copy sweep (Scope #1 fallback branch if @rateshift taken) | 0 | 4 | Week 1 |
| Render Starter + load test | 6 | 8 (if Starter saturates → Standard upgrade) | Week 1–2 |
| Key rotation + shared-secret header | 8 | 10 | Week 1–2 |
| Drip MVP (3 templates incl. branched #2A/#2B) | 10 | 12 | Week 2 |
| Drip warm-up execution (only if waitlist ≥200) | 0 | 2 | Week 2 |
| Waitlist locate + count + metrics re-baseline | 3 | 5 | Week 1 |
| Neon audit + pipeline soak + cache soak | 4 (mostly waiting) | 4 | Week 1–2 |
| Screenshot refresh | 4 | 4 | Week 2 |
| Forecast capability validation (Scope #18) | 2 | 2 | Week 2 |
| Dress rehearsal + fixes | 8 | 12 | Week 3 |
| Compliance review (ToS + PP + CAN-SPAM + UtilityAPI consent) | 4 | 4 | Week 2 |
| Cost caps + abort thresholds wiring | 2 | 2 | Week 2 |
| **Total** | **53 hours** | **71 hours** | **3 weeks** |

Availability assumption: ~20 hrs/week (validated against 2026-04-27 audit sprint where 8 commits / 32 items shipped in ~3 working days, and 2026-05-11 session ran ~14 commits in one day). At 20 hrs/week × 3 weeks = 60 hrs. Min case fits with buffer; max case overruns by 11 hours and triggers the slip rule. Capacity buffer is intentionally the 1-week slip, not a fudge factor inside the table.

## Risks

1. **Backend regression during traffic spike** → Render Starter + auto-build pipeline (+3 soak deploys) + UptimeRobot + numeric abort thresholds
2. **CF Worker rate limits trip legit launch traffic** → Load test 300 RPS pre-launch; raise per-minute caps for launch window if data justifies
3. **Self-hunt under-performs vs. Top 10 ambition** → Floor metric (50 upvotes) is the actual gate; 250 is stretch
4. **Social handle squatters** → Day-0 task; @rateshiftapp fallback + copy sweep
5. **Drip deliverability** → Domain pre-verified (DKIM/SPF/DMARC); warm-up only if waitlist ≥200; otherwise rely on existing reputation
6. **Date slips again** → Hard rule: at Fri May 29 gate, ANY scope item #1–18 not done or formally waived → slip exactly 1 week to Jun 9. Second-slip trigger criteria (any one): (a) at the Jun 5 follow-up gate, any item still incomplete; (b) a regression discovered post-rehearsal whose fix budget — estimated by author and sanity-checked against the regression commit's blast radius (files touched, tests broken) — exceeds 8h; (c) external dependency outage (Resend, Stripe, Render) lasting >24h. Second slip → archive PRD, write v4 from scratch reflecting new reality. No third slip — second slip means the plan was wrong, not just late
7. **Key rotation causes outage** → 10-day soak window + rollback docs in DR runbook
8. **Solo on-call burnout / single-point-of-failure during 48h hyper-monitoring window** → Accepted risk; mitigations = automated abort thresholds + kill-switch runbooks + pre-committed sleep windows with paging

## Timeline

| Date | Milestone |
|---|---|
| Mon 2026-05-12 | Waitlist storage **located** (Scope #6a) |
| Tue 2026-05-13 | Social handles claimed (or fallback + copy-sweep started); waitlist **counted** (Scope #6b) |
| Wed 2026-05-14 | Copy sweep complete (if fallback fired) |
| Thu 2026-05-15 | Metrics re-baselined from comparable launches |
| Fri 2026-05-16 | Render Starter upgrade complete + verified |
| Mon 2026-05-19 | p95 baseline measured; CF Worker cache soak check; forecast-capability validation (#18); activation target locked |
| Wed 2026-05-20 | **Key rotation live** (Scope #3); 13-day soak begins |
| Fri 2026-05-22 | Load test complete; capacity validated or upgrade triggered |
| Sat 2026-05-23 | Shared-secret header live (Scope #4); 3-day soak begins after key-rotation soak |
| Mon 2026-05-25 | Screenshot refresh done; drip emails + tests + Sentry alerts ready in Resend |
| Tue 2026-05-26 | **Dress rehearsal** with synthetic load + rollback drill |
| Fri 2026-05-29 | **Go/no-go gate** — slip rule applies |
| Tue 2026-06-02 12:01am PT | **PH launch** |
| 2026-06-02 → 06-04 | 48h hyper-monitoring |
| 2026-06-09 | Post-launch retro |

## Resources

- Engineering: 1 (Devin) — solo founder
- Design: existing screenshots being refreshed (no new design work)
- QA: existing test suite (6,362 + ~1,642 E2E) + dress rehearsal

## Open Questions (now CLOSED or owned)

1. ~~Self-hunt or hunter?~~ **CLOSED — self-hunt** (Decision Log #13)
2. ~~Waitlist size?~~ **OWNED — count by 2026-05-13** (Scope #6)
3. ~~Day-7 discount code?~~ **CLOSED — no discount at launch** (preserves pricing)
4. ~~Metrics calibration?~~ **OWNED — re-baseline by 2026-05-15** (Scope #7)
