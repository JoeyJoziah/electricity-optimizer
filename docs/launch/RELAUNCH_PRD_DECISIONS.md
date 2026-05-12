# PRD Decision Log — Relaunch (Round 1 Arbitration)

Date: 2026-05-12
Arbiter: Primary Designer
Source reviews: Skeptic (16 objections), Constraint Guardian (12), User Advocate (10)

Disposition codes: **A** = Accepted (PRD revised), **A-OP** = Accepted but lives in operational doc not PRD, **R** = Rejected with rationale, **D** = Deferred to later round.

| # | Source | Objection (compressed) | Sev | Disp | Resolution |
|---|---|---|---|---|---|
| 1 | Skeptic | Waitlist size unknown; drip warm-up depends on it | SER | A | New Day-0 task: count waitlist by 2026-05-13. If <200, drop "warm-up" framing; if 0, remove from plan entirely. De-coupled from launch gating. |
| 2 | Skeptic | Metrics pulled from thin air, self-flagged in OQ#4 | SER | A | Spot-check 5 comparable PH launches in energy/utility/fintech vertical by 2026-05-15; re-baseline numbers and replace table. Until then, metrics marked PROVISIONAL. |
| 3 | Skeptic | 5% paid conversion in 48h unrealistic | BLK | A | Target reset to <1% (5 paid) as launch-window number; 5% becomes 90-day target. |
| 4 | Skeptic | p95 latency target with "~?" baseline | SER | A | Measure baseline against staging by 2026-05-19; replace "?" with number; target = baseline × 1.5 at 300 RPS. |
| 5 | Skeptic | Auto-build pipeline only 1 deploy of track record | SER | A | Gate: 3+ green deploys AND 1 rehearsed rollback before May 26 rehearsal. |
| 6 | Skeptic | Load-test 300 RPS asserted without sizing | SER | A | State assumption explicitly: 300 RPS derived from PH median peak (~150 RPS for B2C launches) × 2 safety. Validate via spot-check. |
| 7 | Skeptic | Dress rehearsal 7d out with no buffer | SER | A | Add explicit "if rehearsal surfaces P0 → slip 1 week per Risk #6"; rule already exists, made explicit in timeline. |
| 8 | Skeptic | Capacity not budgeted for solo founder | SER | A | New Capacity section with hours estimate; pulled scope (see #9). |
| 9 | Skeptic | Screenshot refresh treated as optional but probably required | SER | A | Moved from "if drifted" to In-Scope unconditionally. |
| 10 | Skeptic | Key rotation bundled with launch is risky | SER | A | Rotation must complete + soak ≥10 days pre-launch (so by Fri May 23); rollback plan documented. |
| 11 | Skeptic | Render Starter cold-start claim unverified | MIN | A-OP | Verification step added to INFRA_UPGRADE_RUNBOOK.md; not PRD content. |
| 12 | Skeptic | No launch-day abort criteria | SER | A | Numeric abort thresholds added: signup failure rate >5%, /health p95 >3s for 10min, payment failure rate >10%, error rate >2% sustained 15min. |
| 13 | Skeptic | Organic-only metric assumed, not modeled | SER | A | Reframe: 250 upvotes is "stretch goal"; floor is "PH listing live + ≥50 upvotes (median for self-hunted non-trendy)". Open Q #1 promoted to decision: self-hunt confirmed. |
| 14 | Skeptic | Handle squatter fallback breaks copy | MIN | A | Add copy-sweep task triggered ONLY if @rateshift unavailable. |
| 15 | Skeptic | Open Questions are launch-blocking | SER | A | Each OQ now has a due date or is closed in this revision. |
| 16 | Skeptic | Legal/ToS/privacy/CAN-SPAM not referenced | MIN | A | New Compliance line: verify ToS + Privacy Policy currency, unsubscribe link in drip, UtilityAPI consent copy reviewed. |
| 17 | Guardian | Pipeline only one deploy track record | BLK | A | Same resolution as #5. |
| 18 | Guardian | No load-test data exists | BLK | A | Load test required before May 26 rehearsal; results attached to PRD before launch. |
| 19 | Guardian | Render Starter CPU/RAM unverified at load | SER | A | Load test on Starter plan; if saturation observed, pre-commit Standard ($25) upgrade as Plan B. |
| 20 | Guardian | Neon pooler max-connections unverified | SER | A | Connection budget audit added: count max concurrent BE workers × pool size; verify against Neon plan limit. |
| 21 | Guardian | P0-6 keys un-rotated, public footprint | SER | A | Bumped to "must complete by 2026-05-23" with soak window. |
| 22 | Guardian | Origin not CF-IP-locked (P1-7 deferred) | SER | A | Pulled BACK INTO scope as compensating control: shared-secret header at origin (Render env var, CF Worker injects). Full CF-IP allowlist remains deferred. |
| 23 | Guardian | Rehearsal excludes the spike path | SER | A | Add synthetic load injection (k6 against staging) during rehearsal window. |
| 24 | Guardian | CF Worker cache changes are 1 day old | SER | A | 7-day soak required pre-launch; metrics check at May 19. |
| 25 | Guardian | Solo founder, no on-call backup for 48h | SER | A | Documented acceptance: solo on-call. Mitigation = automated alerting + numeric rollback thresholds (#12) + pre-committed kill-switch (Auto Rate Switcher runbook). |
| 26 | Guardian | Drip warm-up depends on unspecified list | MIN | A | Resolved by #1. |
| 27 | Guardian | No launch-window budget ceiling | MIN | A | Cost caps: CF Worker $20, Neon $30, Resend $20, Render included, OneSignal free tier. Alerts at 50%/80%/100%. |
| 28 | Guardian | No rollback criteria | MIN | A | Resolved by #12. |
| 29 | Advocate | User flow stops at paywall | BLK | A | Flow expanded: free-user post-paywall experience explicitly described; locked-feature framing called out. |
| 30 | Advocate | UtilityAPI vs bill upload bundled | BLK | A | Flow split into two parallel paths with cost disclosure on UtilityAPI path. |
| 31 | Advocate | Metrics are vanity, no activation metric | SER | A | New activation metric: % of signups reaching a savings number within 24h. |
| 32 | Advocate | 5% paid in 48h rushed | SER | A | Resolved by #3. |
| 33 | Advocate | No anonymous demo path | SER | A | "Try without signup" — confirmed out of scope (would require new feature build); risk noted. ZIP-code lookup landing page bullet added to scope. |
| 34 | Advocate | Drip content unspecified | SER | A | 3 emails specified inline in PRD scope. |
| 35 | Advocate | Error/edge UX not described | SER | A-OP | Belongs in LAUNCH_DAY_RUNBOOK.md user-error handling section; PRD links to it. New runbook task. |
| 36 | Advocate | Waitlist unknown | SER | A | Resolved by #1. |
| 37 | Advocate | Screenshot refresh underweighted | MIN | A | Resolved by #9. |
| 38 | Advocate | No slip communication plan | MIN | A | Added: if slipped, send transparent email to signups/waitlist within 24h of slip decision. |

**Rejected objections**: 0 (one A-OP'd to operational doc rather than PRD body).

**Net change**: PRD grows from one page to ~1.5 pages. Acceptable — clarity beats brevity for a launch with this much carry-over risk.
