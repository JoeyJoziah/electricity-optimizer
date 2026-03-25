# Interactive QA Issues -- RateShift

> Created: 2026-03-25
> Updated: 2026-03-25

## Issue Index

| ID | Title | Charter | Severity | Area | Status |
|----|-------|---------|----------|------|--------|
| IQA-001 | Dashboard cascading reload loop after region change | TC-006 | P0 | FE | Resolved |

---

### IQA-001: Dashboard cascading reload loop after region change
- **Charter**: TC-006
- **Severity**: P0
- **Area**: FE (DashboardContent.tsx loading state)
- **Repro Steps**:
  1. Sign in to https://rateshift.app with test account
  2. Observe 3 separate load/refresh cycles (3-5s each) on initial dashboard load
  3. Set state to Connecticut in setup checklist
  4. Click back to dashboard
  5. Dashboard enters continuous load-reload loop (skeleton → content → skeleton → content)
  6. Loop repeats many times, slowly getting shorter between each cycle
- **Observed**: Dashboard shows cascading skeleton→content→skeleton flashes on every navigation, especially after region change. The loop eventually settles but takes 20-30+ seconds.
- **Expected**: Single loading skeleton until data is ready, then stable content render.
- **Evidence**: User manual testing on https://rateshift.app/dashboard, 2026-03-25
- **Suspected Cause**: Loading guard `if (pricesLoading && historyLoading)` on line 205 of DashboardContent.tsx required BOTH queries to be loading simultaneously. With the 3-tier waterfall design (prices → history+savings → forecast+suppliers), historyLoading is `false` (query disabled) while prices loads, and pricesLoading is `false` by the time history starts. So the skeleton never showed, and each tier resolving caused a visible re-render. Combined with Render free tier cold starts (3-5s per API call), this created the cascading reload appearance.
- **Status**: Resolved
- **Resolution**: Changed loading guard from `pricesLoading && historyLoading` to `pricesLoading`. Since all downstream queries are gated on pricesSuccess, nothing useful can render before prices arrive. This ensures a single stable skeleton until Tier 1 data resolves, then progressive enhancement as Tiers 2-3 populate. 55/55 DashboardContent tests pass.
- **Verified**: pending user re-test on production

---

## Issue Template

```
### IQA-NNN: <Title>
- **Charter**: TC-NNN
- **Severity**: P0/P1/P2/P3
- **Area**: UX / BE / FE / FE-BE contract / Data / Integration / Billing / Performance / Security
- **Repro Steps**:
  1. ...
- **Observed**: ...
- **Expected**: ...
- **Evidence**: (URLs, screenshots, console logs, Sentry events, stack traces)
- **Suspected Cause**: ...
- **Status**: Open / In Progress / Resolved / Won't Fix
- **Resolution**: ...
- **Verified**: date
```
