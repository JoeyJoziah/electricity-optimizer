# Metrics Re-Baseline — 2026-05-15

**Date**: 2026-05-12 (spot-check completed early)
**Status**: ✅ COMPLETE
**PRD ref**: `.loki/prds/ph-relaunch-jun2-2026.md` Scope #7

## Comparables surveyed (6 launches)

| Launch | Year | Category | Upvotes | Day-1 signups |
|--------|------|----------|---------|---------------|
| OhmConnect | 2014 | Energy | 79 | n/a |
| Arcadia Power | 2016 | Energy/utility | 96 | n/a |
| Tally 2.0 | 2023 | Fintech B2C | n/a | 766 |
| BuilderKit.ai | 2024 | SaaS B2C | 530+ | 40 paying |
| Fintech First Users | 2022 | Fintech | ~150–300 | n/a |
| Lenny's Newsletter | 2023 | SaaS/Productivity | 593 | n/a |

## Algorithm note

Post–September 2024 Product Hunt algorithm change: only ~10% of launches get
homepage featured. Featured vs. non-featured is now the dominant outcome
variable — more than upvote velocity in hour 1.

## Re-baselined targets

| Metric | Floor (p25) | Stretch (p75) | Rationale |
|---|---|---|---|
| PH upvotes | **75** | **250** | Energy analogs land 79–96; B2C stretch 200–300 with active outreach |
| Signups (48h) | **150–250** | **400–600** | Non-featured: 1k–2k visitors × 15–20% signup |
| Activation (savings within 24h) | **25%** | **40%** | Locked 2026-05-19, see Scope #18 |
| Paid conversions (48h) | **3** | **10** | 1–3% immediate conversion |
| Paid (90-day) | **2–3%** | **5%** | Freemium SaaS benchmark |
| Backend uptime | ≥99.9% | ≥99.9% | Hard floor |
| p95 latency @ 100 RPS | TBD May 19 | baseline × 1.5 | Set by Scope #8 load test |
| Drip #1 open rate | ≥35% | ≥45% | Transactional welcome typical 40–55% |

## Outreach requirements

- **Floor target** (75 upvotes): organic + RateShift's existing audience
- **Stretch target** (250 upvotes): requires 100+ supporter outreach in first 2 hours

## Locks

- **2026-05-15**: floor/stretch numbers above are locked. No further adjustments
  before launch unless a hard blocker emerges (e.g., infra regression in
  Scope #11 soak).
- **Activation %**: target locked at floor=25 / stretch=40 per PRD adjustment
  rule (`target = floor(validated_pass_rate × 0.8)`, nearest 5%).

## Provisional → locked

All "PROVISIONAL" markers in PRD v3.1 Success Metrics table have been replaced
with grounded numbers above. PRD v3.2 reflects locked values.
