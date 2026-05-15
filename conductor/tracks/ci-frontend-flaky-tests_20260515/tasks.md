# Tasks — ci-frontend-flaky-tests_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.

## Phase 1: Triage + targeted fixes
- [ ] Task 1.1: Investigate + fix `decisionPresentation.test.ts:95` (clock race) — fake timers
- [ ] Task 1.2: Investigate + fix `ConnectionsOverview.test.tsx:392` (timeout) — waitFor + deterministic mocks
- [ ] Task 1.3: Investigate + fix `RateChangeFeed.test.tsx:117` (timeout)
- [ ] Task 1.4: Investigate `SupplierSelector.test.tsx` flake mode + fix
- [ ] Task 1.5: Investigate `ConnectionRates.test.tsx` flake mode + fix
- [ ] Task 1.6: Investigate `CommunitySolarContent.test.tsx` flake mode + fix
- [ ] Task 1.7: Investigate `useReports.test.ts` flake mode + fix
- [ ] Task 1.8: Investigate `ComparisonTable.test.tsx` flake mode + fix

## Phase 2: Verification
- [ ] Task 2.1: Run each fixed file 10× consecutively locally — all pass
- [ ] Task 2.2: Run full FE suite 3× consecutively — all pass
- [ ] Task 2.3: Commit + push, verify Loki hook passes without retry
