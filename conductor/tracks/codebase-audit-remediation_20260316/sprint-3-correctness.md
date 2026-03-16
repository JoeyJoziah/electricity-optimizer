# Sprint 3: Correctness & UX — QUEUED

**Status**: QUEUED (blocked on Sprint 1 completion)
**Target**: Validation gaps, cache bugs, UX degradation
**Estimated files**: ~45

## Workstreams (Planned)

| WS | Tasks | Focus |
|----|-------|-------|
| WS-3A-querykeys | S3-01..S3-04 | React Query key correctness (pageSize, object-as-key, array serialization) |
| WS-3B-apiclient | S3-05..S3-07 | API client fixes (delete body, 401 fallthrough, notification polling) |
| WS-3C-hooks | S3-08..S3-10 | Hook state fixes (optimal schedule key, stale router, connection errors) |
| WS-3D-tailwind | S3-11..S3-14 | Design system (darkMode, semantic tokens, scrollbar, keyframes) |
| WS-3E-layout | S3-15..S3-17 | Layout fixes (modal margins, min-w-0, sidebar overflow) |

## Task Detail

| # | Task | Source |
|---|------|--------|
| S3-01 | Fix useAlertHistory missing pageSize in queryKey | 14-P2 |
| S3-02 | Fix useRateChanges object-as-key (destructure to primitives) | 14-P2 |
| S3-03 | Fix usePotentialSavings O(n) array serialization | 14-P2 |
| S3-04 | Fix useSettingsStore SSR localStorage guard | 14-P2 |
| S3-05 | Fix apiClient.delete to accept optional body | 20-P2 |
| S3-06 | Fix handleResponse 401 fallthrough (throw, don't return) | 20-P2 |
| S3-07 | Fix useNotificationCount background polling disable | 20-P2 |
| S3-08 | Fix useOptimalSchedule object-as-key instability | 14-P2 |
| S3-09 | Fix useAuth stale router reference in effect | 14-P2 |
| S3-10 | Fix useConnections swallowing non-403 errors | 14-P2 |
| S3-11 | Add darkMode: 'class' to tailwind.config.ts | 18-P0 |
| S3-12 | Replace 30+ hardcoded color classes with semantic tokens | 18-P1 |
| S3-13 | Add scrollbar-hide plugin or CSS fallback | 18-P2 |
| S3-14 | Remove duplicate keyframe definitions | 18-P2 |
| S3-15 | Fix Modal horizontal margins on narrow screens | 18-P2 |
| S3-16 | Add min-w-0 to app shell main element | 18-P2 |
| S3-17 | Fix SidebarProvider overflow:hidden on desktop | 18-P2 |
