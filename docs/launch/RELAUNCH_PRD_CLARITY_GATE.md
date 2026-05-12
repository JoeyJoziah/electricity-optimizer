# Clarity Gate Audit — RELAUNCH_PRD.md v2

Date: 2026-05-12
Auditor: Clarity-Gate process (9-point epistemic verification)
Scoring: ✅ PASS / ⚠️ PARTIAL / ❌ FAIL

## 1. Claims Grounded
Every factual claim sourced or marked PROVISIONAL/TBD.

- ✅ Backend 34 days stale — sourced to 2026-05-11 commit
- ✅ Auto-build pipeline 1 deploy — explicit count given
- ✅ Audit sprint 29 items — sourced to MEMORY.md
- ✅ Metrics flagged PROVISIONAL with re-baseline date
- ✅ p95 marked "TBD by May 19"
- ⚠️ "PH median peak ~150 RPS B2C" — asserted in Scope #8 without citation. **GAP**: needs a source or removal of the multiplier.
- ⚠️ "Floor 50 upvotes = self-hunted non-trendy median" — no citation. Same gap as metrics OQ#4. **GAP**: should be confirmed during the May 15 spot-check.

**Status**: ⚠️ PARTIAL — 2 unsourced quantitative claims (sizing rationale, upvote floor).

## 2. Assumptions Explicit
Implicit assumptions surfaced.

- ✅ Self-hunt assumption stated (Decision Log #13)
- ✅ Solo on-call burden explicitly accepted (Risk #8)
- ✅ Anonymous demo top-of-funnel leak explicitly accepted (Out scope)
- ⚠️ "~20 hours/week available" — assumed without history. **GAP**: how was 20h validated? Last 4 weeks' commit pace would back this up; not cited.
- ⚠️ Drip email #2 "branches on connection state" assumes Resend supports conditional template logic OR backend dispatches the right template. Not specified.
- ⚠️ Assumes Stripe Checkout, UtilityAPI OAuth, Better Auth flows all work at launch volume — these are stated but not load-tested as a unit.

**Status**: ⚠️ PARTIAL — 3 implicit assumptions.

## 3. Metrics Measurable
Every metric has an instrument and a threshold.

- ✅ PH upvotes — instrument: PH dashboard; thresholds: 50 / 250
- ✅ Signups — instrument: Better Auth / DB query; threshold: 500
- ✅ Activation 40% — instrument: DB query (savings_forecasts.user_id WHERE created_at - signup_at <= 24h). **GAP**: query not actually specified anywhere; risk of inconsistent measurement.
- ✅ Paid conversions — instrument: Stripe; threshold: 5 launch / 5% 90d
- ✅ /health uptime — instrument: UptimeRobot; threshold: 99.9%
- ✅ p95 latency — instrument: CF Worker analytics; threshold: baseline × 1.5
- ✅ Drip open rate — instrument: Resend; threshold: 40%

**Status**: ⚠️ PARTIAL — activation metric definition needs concrete SQL or unambiguous spec.

## 4. Scope Unambiguous
In/Out items mutually exclusive and binary.

- ✅ In and Out lists are disjoint
- ✅ Each In item is binary (done/not done)
- ⚠️ Scope #1 has a conditional fork ("if unavailable → copy sweep"). Binary at the gate but ambiguous in capacity planning (was 2–4h estimated; the copy-sweep branch alone is closer to 4h).
- ⚠️ Scope #5 has a conditional fork (warm-up dependent on waitlist ≥200). Acceptable for runtime, but capacity table doesn't reflect either branch.

**Status**: ⚠️ PARTIAL — 2 conditional branches with unclear capacity impact.

## 5. Risks Mitigated
Every risk has a mitigation or accepted-risk label.

- ✅ All 8 risks have mitigation or "Accepted risk" label
- ⚠️ Risk #6 (date slips again) — second slip says "reopen the whole PRD", but no criteria for what triggers reopen vs. third-slip ban. **GAP**: still has a soft edge.

**Status**: ⚠️ PARTIAL — one risk has a soft fallback path.

## 6. Dependencies Named
External systems, people, services explicit.

- ✅ External services named: Product Hunt, X, Bluesky, LinkedIn, Resend, Render, Vercel, Cloudflare, Neon, Stripe, UtilityAPI, Better Auth, OneSignal, UptimeRobot
- ✅ Internal docs referenced: LAUNCH_DAY_RUNBOOK.md, DR runbook, FINAL_COPY.md, etc.
- ⚠️ No explicit dependency on Render approving the Starter upgrade in time (billing/account state). Trivial in practice but not stated.
- ⚠️ Implicit dependency: existing waitlist mechanism (where IS the waitlist stored — DB table? Mailchimp? Form?). Not specified.

**Status**: ⚠️ PARTIAL — 2 minor unnamed deps.

## 7. Falsifiable Success Criteria
Pass/fail definable without judgment.

- ✅ Metrics table = numeric thresholds, falsifiable
- ✅ Abort thresholds (Scope #15) = numeric, falsifiable
- ✅ Go/no-go gate (Fri May 29) = binary per scope item
- ⚠️ "Existing material becomes worthless" (Problem statement) — not falsifiable. Belongs in rationale, but the word "worthless" overstates. **GAP**: minor.

**Status**: ⚠️ PARTIAL — one rhetorical claim in Problem section.

## 8. Internally Consistent
No contradictions between sections.

- ✅ Timeline matches scope deadlines
- ✅ Metrics table matches Risk framing (50 floor, 250 stretch)
- ✅ Capacity table totals match individual rows (49–51h)
- ❌ Solution section says "close 5 prerequisites" but Scope lists **17 In-items**. **CONTRADICTION**.
- ⚠️ Scope #15 puts abort thresholds in LAUNCH_DAY_RUNBOOK.md but lists them inside the PRD too. Acceptable as preview, but should be clear which is canonical.

**Status**: ❌ FAIL — Solution/Scope item-count contradiction is a real defect.

## 9. Free of Hidden Requirements
Nothing assumed that isn't stated.

- ⚠️ Activation metric (40%) implies the forecast page reliably renders a savings number within 24h of signup → requires UtilityAPI or bill OCR to complete same-day for 40% of users. That's a product capability claim not validated anywhere in the PRD.
- ⚠️ Drip #2 "personalized savings preview" requires forecast data exists by day 2 — same dependency.
- ⚠️ "Email blast to existing signups" implies a mailing list of existing signups exists and is segmentable — not specified.

**Status**: ⚠️ PARTIAL — 3 hidden product capability dependencies.

---

## Overall Score: 1 PASS / 7 PARTIAL / 1 FAIL — **DOES NOT PASS at 100% flawless**

Required fixes for clean pass:
1. **(FAIL, must fix)** Solution section: change "5 prerequisites" to match the actual 17-item scope, or restructure scope into 5 buckets.
2. **(GAP)** Cite or remove "~150 RPS PH median" and "50 upvote floor" — or convert both to "to be validated during 2026-05-15 spot-check".
3. **(GAP)** Specify activation metric query/instrument unambiguously.
4. **(GAP)** Validate "20h/week" availability against last-4-week commit history or restate as planned allocation.
5. **(GAP)** Specify whether Resend conditional templates or backend dispatch handles Drip #2 branching.
6. **(GAP)** Capacity table: account for both branches of Scope #1 and #5.
7. **(GAP)** Risk #6: define reopen-criteria for second slip.
8. **(GAP)** Name waitlist storage mechanism.
9. **(GAP)** "Worthless" → softer language ("loses relevance" or "must be rewritten").
10. **(GAP)** Document activation prerequisite: forecast availability within 24h of signup is a product claim that needs explicit validation step OR target reduction.
11. **(GAP)** Clarify canonical location for abort thresholds (PRD or runbook).

Will produce v3.
