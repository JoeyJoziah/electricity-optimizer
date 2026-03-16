# Sprint 3: Correctness & UX — COMPLETE

**Status**: COMPLETE
**Started**: 2026-03-16
**Completed**: 2026-03-16
**Commit**: `361edee` (46 files, +855/-219)
**Agents**: 5 parallel workstreams
**Result**: Backend 2,536 passed, Frontend 1,879 passed (+22), 0 failures

## Workstreams

| WS | Agent Type | Tasks | Status |
|----|-----------|-------|--------|
| WS-3A-querykeys | general-purpose | S3-01, S3-02, S3-03, S3-04 | COMPLETE |
| WS-3B-apiclient | general-purpose | S3-05, S3-06, S3-07 | COMPLETE |
| WS-3C-hooks | general-purpose | S3-08, S3-09, S3-10 | COMPLETE |
| WS-3D-tailwind | frontend-developer | S3-11, S3-12, S3-13, S3-14 | COMPLETE |
| WS-3E-layout | frontend-developer | S3-15, S3-16, S3-17 | COMPLETE |

## Task Detail

| # | Task | Source | Status |
|---|------|--------|--------|
| S3-01 | Fix useAlertHistory missing pageSize in queryKey | 14-P2 | DONE |
| S3-02 | Fix useRateChanges object-as-key (destructure to primitives) | 14-P2 | DONE |
| S3-03 | Fix usePotentialSavings/useCompareSuppliers array serialization | 14-P2 | DONE |
| S3-04 | Fix useSettingsStore SSR localStorage guard | 14-P2 | DONE |
| S3-05 | Fix apiClient.delete to accept optional body | 20-P2 | DONE |
| S3-06 | Verify handleResponse 401 handling (confirmed correct, +2 tests) | 20-P2 | DONE |
| S3-07 | Fix useNotificationCount background polling disable | 20-P2 | DONE |
| S3-08 | Fix useOptimalSchedule object-as-key instability | 14-P2 | DONE |
| S3-09 | Fix useAuth stale router reference in effect | 14-P2 | DONE |
| S3-10 | Fix useConnections swallowing non-403 errors | 14-P2 | DONE |
| S3-11 | Add darkMode: 'class' to tailwind.config.ts | 18-P0 | DONE |
| S3-12 | Replace 30+ hardcoded color classes with semantic tokens | 18-P1 | DONE |
| S3-13 | Add scrollbar-hide CSS utility | 18-P2 | DONE |
| S3-14 | Remove 5 duplicate keyframe definitions | 18-P2 | DONE |
| S3-15 | Fix Modal horizontal margins on narrow screens | 18-P2 | DONE |
| S3-16 | Add min-w-0 to app shell main element | 18-P2 | DONE |
| S3-17 | Fix SidebarProvider overflow:hidden on desktop | 18-P2 | DONE |

## Key Decisions

- **S3-06**: 401 handling in `handleResponse()` was verified correct as-is. The never-resolving promise pattern intentionally prevents React Query retry cascades. 2 new tests added to document the behavior.
- **S3-12**: Semantic token replacement was conservative — gray-*, cyan (water domain), streak tier colors, and marketing pages were intentionally left as raw Tailwind classes.
- **S3-03**: Arrays serialized via `JSON.stringify()` for stable queryKey comparison. Supplier IDs additionally sorted before serialization.
- **S3-04**: SSR guard returns no-op in-memory storage during SSR, no state persistence until client hydration.

## Verification Criteria

- [x] Backend test count: 2,536 passed (unchanged from Sprint 1)
- [x] Frontend test count: 1,879 passed (increased from 1,857)
- [x] All existing passing tests still pass
- [x] 22 new frontend tests added (queryKey stability, SSR guard, sidebar context, client 401)
- [x] Design system: 24 components migrated to semantic tokens
- [x] darkMode: 'class' configured in Tailwind
- [x] Duplicate keyframes removed (5 defs, canonical in tailwind.config.ts)
