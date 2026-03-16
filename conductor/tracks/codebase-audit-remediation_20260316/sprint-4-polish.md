# Sprint 4: Polish & Forward-Compat — COMPLETE

**Status**: COMPLETE
**Started**: 2026-03-16
**Completed**: 2026-03-16
**Commit**: `cd42a7d` (32 files, +745/-872)
**Agents**: 3 parallel workstreams
**Result**: Backend 2,534 passed, Frontend 1,898 passed (+19 net), 0 failures

## Workstreams

| WS | Agent Type | Tasks | Status |
|----|-----------|-------|--------|
| WS-4A-naming | frontend-developer | S4-01, S4-02, S4-03, S4-04 | COMPLETE |
| WS-4B-ux | frontend-developer | S4-05, S4-06, S4-07, S4-08 | COMPLETE |
| WS-4C-cleanup | general-purpose | S4-09, S4-10, S4-11, S4-12 | COMPLETE |

## Task Detail

| # | Task | Source | Status |
|---|------|--------|--------|
| S4-01 | Rename duplicate useAppliances → useStoredAppliances / useSavedAppliances | 20-P3 | DONE |
| S4-02 | Widen apiClient.get params to accept arrays | 20-P3 | DONE |
| S4-03 | Separate onboarding vs missing-region redirect logic | 14-P3 | DONE |
| S4-04 | Add numeric validation to community solar hooks | 14-P3 | DONE |
| S4-05 | Remove useRealtimeBroadcast no-op stub | 14-P3 | DONE |
| S4-06 | Add print styles for cost reports | 18-P3 | DONE |
| S4-07 | Fix progress bar animations (width → transform:scaleX) | 18-P3 | DONE |
| S4-08 | Replace hardcoded chart colors with CSS custom properties | 18-P3 | DONE |
| S4-09 | Mark NEXT_PUBLIC_APP_URL as required in production | 06-P3 | DONE |
| S4-10 | Add common password check to password.py | 19-P3 | DONE |
| S4-11 | Clean up deprecated SupplierRepository (420 lines removed) | 03-P3 | DONE |
| S4-12 | Document cross-cutting ADRs (008-semantic-tokens, 009-atomic-rate-limiting) | 11-P3 | DONE |

## Key Decisions

- **S4-01**: Both old `useAppliances` names kept as deprecated aliases for backward compatibility. New names: `useStoredAppliances` (Zustand local) and `useSavedAppliances` (React Query API).
- **S4-02**: Array params serialized as repeated keys (`?ids=a&ids=b`), matching standard form encoding.
- **S4-03**: Extracted pure functions `checkNeedsOnboarding()` and `checkNeedsRegion()` for independent testability. Declarative `PROFILE_REQUIRED_PREFIXES` array.
- **S4-07**: Only animated progress bars migrated to `transform:scaleX`. Proportional width segments (CCAInfo, CombinedSavingsCard) and timeline positioning (ScheduleTimeline) intentionally left as `width`.
- **S4-08**: Created `chartTokens.ts` with CSS custom properties (--chart-1 through --chart-6 plus semantic aliases). Dark mode override possible by redefining vars in `.dark` scope.
- **S4-11**: Deprecated `SupplierRepository` replaced with `_RemovedSupplierRepository` stub that raises `ImportError` with migration guide. 420 lines of broken ORM code removed, 230+ lines of dead tests cleaned up.

## Verification Criteria

- [x] Backend test count: 2,534 passed (unchanged from Sprint 3)
- [x] Frontend test count: 1,898 passed (net +19 from Sprint 3's 1,879)
- [x] All existing passing tests still pass
- [x] 23+ new frontend tests added (community solar validation, deprecated alias verification)
- [x] 3 new backend tests added (common password check)
- [x] Dead code removed: useRealtimeBroadcast stub, SupplierRepository class, 230+ dead test lines
- [x] 2 new ADRs created (008, 009)
- [x] Chart color tokens centralized in chartTokens.ts with CSS custom properties
- [x] Print stylesheet added to globals.css
