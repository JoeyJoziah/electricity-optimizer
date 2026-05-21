# Tasks — ci-frontend-flaky-tests_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.
> All tasks verified complete 2026-05-21 via direct test execution (see execution.md).

## Phase 1: Triage + targeted fixes
- [x] Task 1.1: Investigate + fix `decisionPresentation.test.ts:95` (clock race) — fixed via `jest.useFakeTimers` (2 hooks; verified)
- [x] Task 1.2: Investigate + fix `ConnectionsOverview.test.tsx:392` (timeout) — `userEvent.setup({ delay: null })` (5 sites; verified)
- [x] Task 1.3: Investigate + fix `RateChangeFeed.test.tsx:117` (timeout) — `delay: null` (2 sites; verified)
- [x] Task 1.4: Investigate `SupplierSelector.test.tsx` flake mode + fix — `delay: null` (4 sites; verified)
- [x] Task 1.5: Investigate `ConnectionRates.test.tsx` flake mode + fix — `delay: null` (2 sites; verified)
- [x] Task 1.6: Investigate `CommunitySolarContent.test.tsx` flake mode + fix — no defect found; left untouched (verified passing)
- [x] Task 1.7: Investigate `useReports.test.ts` flake mode + fix — no defect found; left untouched (verified passing)
- [x] Task 1.8: Investigate `ComparisonTable.test.tsx` flake mode + fix — `delay: null` (4 sites; verified)

## Phase 2: Verification
- [x] Task 2.1: Run each fixed file 10× consecutively locally — 8-file set 10/10 green, 108 tests/run (2026-05-21)
- [x] Task 2.2: Run full FE suite 3× consecutively — 3/3 green, 3437/3437 each (2026-05-21)
- [x] Task 2.3: Commit + push, verify Loki hook passes without retry — fix commit `9340309e` in origin/main; local==origin, clean tree
