# Section 11: Frontend State Management — Clarity Gate Audit

**Date:** 2026-03-12
**Auditor:** Claude Code (Direct)
**Score:** 79/90 (PASS)

---

## Aggregate Scores

| # | Dimension | Score |
|---|-----------|-------|
| 1 | Correctness | 9/10 |
| 2 | Coverage | 9/10 |
| 3 | Security | 9/10 |
| 4 | Performance | 8/10 |
| 5 | Maintainability | 9/10 |
| 6 | Documentation | 9/10 |
| 7 | Error Handling | 9/10 |
| 8 | Consistency | 8/10 |
| 9 | Modernity | 9/10 |
| | **TOTAL** | **79/90** |

---

## Files Analyzed (~800 lines across 12 state files)

`lib/store/settings.ts`, `lib/hooks/useAuth.tsx`, `lib/hooks/useProfile.ts`, `lib/hooks/usePrices.ts`, `lib/hooks/useSuppliers.ts`, `lib/hooks/useAlerts.ts`, `lib/hooks/useConnections.ts`, `lib/hooks/useOptimization.ts`, `lib/hooks/useAgent.ts`, `lib/hooks/useNotifications.ts`, `lib/hooks/useRealtime.ts`, `lib/contexts/sidebar-context.tsx`, `lib/contexts/toast-context.tsx`

---

## Architecture Assessment

Clean 3-layer state architecture: Zustand for persistent client settings (region, supplier, preferences), React Context for transient UI state (sidebar, toasts, auth), and React Query (via custom hooks) for server state (prices, suppliers, alerts). Each domain has a dedicated hook (`usePrices`, `useSuppliers`, `useAlerts`, etc.) that wraps API calls with caching and optimistic updates. AuthProvider initializes session + supplier + profile in parallel via `Promise.allSettled` to avoid waterfalls.

## HIGH Findings (2)

**H-01: useAuth initAuth triggers on every mount without deduplication**
- File: `lib/hooks/useAuth.tsx:65-147`
- `initAuth()` runs in a `useEffect(() => {}, [])` but if AuthProvider remounts (React Strict Mode, layout changes), it fires again
- Multiple `getSession()` + `getUserProfile()` calls race against each other
- Fix: Add a module-level `initPromise` ref to deduplicate parallel init calls

**H-02: settings store localStorage key still uses old brand name**
- File: `lib/store/settings.ts:169`
- `name: 'electricity-optimizer-settings'` — should be `rateshift-settings` after rebrand
- Users who clear their Zustand storage will lose their settings; existing users keep working
- Fix: Either rename (with migration logic) or leave as-is and document the legacy key

## MEDIUM Findings (2)

**M-01: No server-side settings sync — localStorage only**
- File: `lib/store/settings.ts`
- All user settings (region, supplier, preferences, appliances) persist only to localStorage
- If user switches browsers or clears storage, all settings are lost
- Backend has a profile endpoint but only syncs region and supplier — not all settings
- Fix: Periodic sync of critical settings to backend profile

**M-02: Toast provider lacks max toast limit**
- File: `lib/contexts/toast-context.tsx`
- No cap on simultaneous toasts — rapid errors could stack dozens of toast notifications
- Fix: Add `MAX_VISIBLE_TOASTS = 5` and remove oldest when exceeded

## Strengths

- **3-layer separation**: Zustand (client) + React Context (UI) + React Query (server) — no state layer confusion
- **Selective persistence**: `partialize` in Zustand ensures only user-facing settings go to localStorage
- **Granular selector hooks**: `useRegion()`, `useCurrency()`, `useTheme()` avoid unnecessary re-renders
- **Promise.allSettled auth init**: Parallel session + supplier + profile fetching with graceful degradation
- **Sidebar accessibility**: Escape key dismiss + body scroll lock on mobile
- **Toast timer cleanup**: Proper `useRef` timer management with cleanup on unmount
- **Auth context memoization**: `useMemo` on context value prevents unnecessary consumer re-renders
- **OneSignal binding**: Push subscription linked to user ID on sign-in, unbound on sign-out
- **Safe redirect validation**: `new URL()` + origin check on callbackUrl prevents open redirect

**Verdict:** PASS (79/90). Well-structured state management with clean separation of concerns. Main issues are auth init deduplication and lack of server-side settings sync.
