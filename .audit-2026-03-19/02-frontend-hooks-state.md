# Audit Report: Frontend Hooks & State Management
**Date:** 2026-03-19
**Scope:** Hooks, stores, contexts, providers
**Files Reviewed:**
- `frontend/lib/hooks/useAuth.tsx`
- `frontend/lib/hooks/usePrices.ts`
- `frontend/lib/hooks/useSavings.ts`
- `frontend/lib/hooks/useSuppliers.ts`
- `frontend/lib/hooks/useAlerts.ts`
- `frontend/lib/hooks/useConnections.ts`
- `frontend/lib/hooks/useNotifications.ts`
- `frontend/lib/hooks/useForecast.ts`
- `frontend/lib/hooks/useAgent.ts`
- `frontend/lib/hooks/useRealtime.ts`
- `frontend/lib/hooks/useOptimization.ts`
- `frontend/lib/hooks/useCommunity.ts`
- `frontend/lib/hooks/useProfile.ts`
- `frontend/lib/hooks/useGasRates.ts`
- `frontend/lib/hooks/useUtilityDiscovery.ts`
- `frontend/lib/hooks/useReports.ts`
- `frontend/lib/hooks/useExport.ts`
- `frontend/lib/hooks/useNeighborhood.ts`
- `frontend/lib/hooks/useHeatingOil.ts`
- `frontend/lib/hooks/usePropane.ts`
- `frontend/lib/hooks/useWater.ts`
- `frontend/lib/hooks/useCCA.ts`
- `frontend/lib/hooks/useCombinedSavings.ts`
- `frontend/lib/hooks/useRateChanges.ts`
- `frontend/lib/hooks/useCommunitySolar.ts`
- `frontend/lib/hooks/useGeocoding.ts`
- `frontend/lib/hooks/useDiagrams.ts`
- `frontend/lib/store/settings.ts`
- `frontend/lib/contexts/toast-context.tsx`
- `frontend/lib/contexts/sidebar-context.tsx`
- `frontend/components/providers/QueryProvider.tsx`

Additionally consulted for cross-reference:
- `frontend/lib/api/client.ts`
- `frontend/lib/api/profile.ts`
- `frontend/lib/api/cca.ts`
- `frontend/lib/api/heating-oil.ts`
- `frontend/node_modules/@microsoft/fetch-event-source/lib/esm/fetch.js` (library internals)

---

## P0 -- Critical (Fix Immediately)

### 1. SidebarContext provides a non-null default that silently masks missing providers

**File:** `frontend/lib/contexts/sidebar-context.tsx`, line 11-15

```typescript
const SidebarContext = createContext<SidebarContextValue>({
  isOpen: false,
  toggle: () => {},
  close: () => {},
})
```

The context is created with a non-null default value. This means any component calling `useSidebar()` outside a `<SidebarProvider>` will silently receive no-op functions and a frozen `isOpen: false` state, rather than throwing an error. Unlike `useAuth()` and `useToast()` which correctly throw when used outside their providers, `useSidebar()` (line 68-70) returns the default context without warning.

This is a P0 because it masks integration errors during development and testing. A component using `useSidebar().toggle()` outside the provider tree would appear to work but do nothing -- a silent failure that is extremely hard to diagnose.

**Recommendation:** Use `null` as the default and add a guard in `useSidebar()`:
```typescript
const SidebarContext = createContext<SidebarContextValue | null>(null)

export function useSidebar() {
  const ctx = useContext(SidebarContext)
  if (!ctx) throw new Error('useSidebar must be used within SidebarProvider')
  return ctx
}
```

### 2. SidebarProvider value object creates new reference on every render -- cascading re-renders to all consumers

**File:** `frontend/lib/contexts/sidebar-context.tsx`, line 62

```typescript
<SidebarContext.Provider value={{ isOpen, toggle, close }}>
```

The `value` prop is an inline object literal, creating a new reference on every render of `SidebarProvider`. Every component consuming `useSidebar()` will re-render whenever `SidebarProvider` re-renders -- even if `isOpen`, `toggle`, and `close` have not changed. While `toggle` and `close` are memoized with `useCallback`, the wrapping object is not memoized.

Compare with `useAuth.tsx` line 435-448, which correctly wraps its context value in `useMemo`. The `ToastProvider` (line 96-99) also correctly uses `useMemo`.

**Recommendation:** Wrap the value in `useMemo`:
```typescript
const value = useMemo(() => ({ isOpen, toggle, close }), [isOpen, toggle, close])
return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>
```

---

## P1 -- High (Fix This Sprint)

### 3. useGeocoding has a race condition with concurrent calls -- stale loading/error state

**File:** `frontend/lib/hooks/useGeocoding.ts`, lines 17-36

The hook manages `loading` and `error` state via `useState`, but the `geocode` callback has no protection against concurrent invocations. If a user triggers two geocode calls in quick succession (e.g., typing fast and hitting enter twice), the first call's `finally` block (line 31) will set `loading = false` before the second call completes, causing the UI to briefly show a non-loading state while the second request is still in flight. Similarly, the second call's `setError(null)` at line 23 clears any error from the first call.

**Recommendation:** Either use an AbortController ref (like `useAgent.ts` does at line 18) to cancel the previous request, or track a request counter/version to discard stale results:
```typescript
const versionRef = useRef(0)
const geocode = useCallback(async (address: string) => {
  const version = ++versionRef.current
  setLoading(true)
  setError(null)
  try {
    const data = await apiClient.post<GeocodeResponse>('/geocode', { address })
    if (version !== versionRef.current) return null // stale
    return data.result ?? null
  } catch (e) {
    if (version !== versionRef.current) return null
    setError(e instanceof Error ? e.message : 'Geocoding failed')
    return null
  } finally {
    if (version === versionRef.current) setLoading(false)
  }
}, [])
```

### 4. useAgentQuery sendQuery accumulates unbounded message state -- memory leak in long sessions

**File:** `frontend/lib/hooks/useAgent.ts`, lines 35, 42, 51

The `messages` array grows without bound as the user sends queries. Each SSE chunk appends a new entry via `setMessages(prev => [...prev, msg])` (line 42). In the `/assistant` page with an `AgentChat` component, a user who sends many queries in a single session will accumulate arbitrarily large state. While the `reset` function (line 65-69) exists, it is only called explicitly, and there is no automatic pruning or pagination.

This is a P1 because the agent chat is an interactive feature that users may keep open for extended periods.

**Recommendation:** Add a maximum message cap (e.g., 200 messages) or implement windowed state that trims older messages when the array exceeds a threshold.

### 5. useDiagrams fetch functions bypass the apiClient -- no auth, no retry, no circuit breaker

**File:** `frontend/lib/hooks/useDiagrams.ts`, lines 15-48

All four API functions (`fetchDiagramList`, `fetchDiagram`, `saveDiagram`, `createDiagram`) use raw `fetch()` instead of the shared `apiClient`. This means:
- No automatic 401 redirect to login
- No retry with exponential backoff for 5xx errors
- No circuit breaker integration
- No `credentials: 'include'` for cookie-based auth
- No AbortSignal propagation (the `queryFn` in `useDiagram` at line 60 receives `signal` from React Query but never passes it to `fetchDiagram`)

While these are dev-only endpoints (`/api/dev/diagrams`), they still represent an inconsistency that will cause confusing auth failures in non-local environments.

**Recommendation:** Either use `apiClient` for these calls, or at minimum add `credentials: 'include'` to the fetch options and pass the abort signal through.

### 6. useRealtime SSE disconnect function sets mountedRef.current = false -- blocks reconnection without remount

**File:** `frontend/lib/hooks/useRealtime.ts`, lines 134-141

The `disconnect` callback sets `mountedRef.current = false` (line 135), which is the same flag used by the effect cleanup (line 128). Once called, even if the component remains mounted, the `mountedRef` will be `false` and all SSE event handlers will silently discard incoming data (lines 58, 73, 99, 116). There is no `reconnect` function exposed, and remounting is required to restore the SSE connection.

This is problematic because the `disconnect` function is exposed to consumers who may call it and later expect the SSE to resume -- but it cannot without a full remount.

**Recommendation:** Either: (a) do not set `mountedRef.current = false` in `disconnect()` -- only abort the controller; or (b) expose a `reconnect()` function that resets the ref and re-establishes the connection; or (c) document that `disconnect` is terminal and rename it to `disconnectPermanently`.

---

## P2 -- Medium (Fix Soon)

### 7. useAuth initAuth effect has an empty dependency array but reads window.location.pathname inline

**File:** `frontend/lib/hooks/useAuth.tsx`, line 248

```typescript
useEffect(() => {
  initAuth()
}, [])
```

The effect runs once on mount and reads `window.location.pathname` inside the async function (lines 143, 226). This is intentional (init-on-mount), and the `routerRef` pattern (lines 132-135) correctly handles stale router references. However, the `eslint-disable` comment is absent, meaning the linter may flag `setUser`, `setProfileFetchFailed`, etc. as missing dependencies (they are state setters and stable, but the lint rule does not know that without explicit annotation).

More importantly, the fire-and-forget `fetch` calls at lines 171 and 282 do not propagate the component's unmount signal. If `AuthProvider` unmounts during the fetch (e.g., fast navigation), the resolved `.then` will call `setUser` on an unmounted component. While React 18+ suppresses the warning, it wastes resources.

**Recommendation:** Either pass an `AbortController` from the effect's cleanup to cancel outstanding fire-and-forget fetches, or use an `isMounted` ref pattern.

### 8. useRealtimeSubscription creates a new Date object every 30 seconds with no consumer -- potential no-op overhead

**File:** `frontend/lib/hooks/useRealtime.ts`, line 194

```typescript
setLastUpdate(new Date())
```

The `lastUpdate` state is set every 30 seconds by the polling interval, but it is only returned to consumers (line 208). If consumers do not use `lastUpdate`, this still triggers a re-render of the component using `useRealtimeSubscription` every 30 seconds. For components that only care about the side effect (calling `onUpdate`), this is wasted work.

**Recommendation:** Consider making `lastUpdate` lazy (only track it if consumed) or move to a ref if the re-render trigger is not needed.

### 9. useCommunityPosts uses non-null assertion on region and utilityType even though they may be undefined

**File:** `frontend/lib/hooks/useCommunity.ts`, line 14

```typescript
queryFn: ({ signal }) => fetchPosts(region!, utilityType!, page, 20, signal),
enabled: !!region && !!utilityType,
```

The `enabled` guard at line 15 prevents the query from firing when `region` or `utilityType` are falsy, which is correct. However, the non-null assertions (`!`) on line 14 are still a code smell because TypeScript's type narrowing does not apply across the `enabled`/`queryFn` boundary. If React Query's behavior ever changes (e.g., a bug or version upgrade removes the `enabled` check before calling `queryFn`), the assertions would hide a runtime undefined access.

This same pattern appears across many hooks in this codebase:
- `usePrices.ts` line 20 (`region!`)
- `useGasRates.ts` lines 15, 23, 31, 50
- `useForecast.ts` line 11 (`utilityType!`)
- `useHeatingOil.ts` lines 20, 29, 39
- `usePropane.ts` lines 20, 29, 38
- `useWater.ts` line 19
- `useCCA.ts` lines 12, 21
- `useNeighborhood.ts` line 7
- `useReports.ts` line 7
- `useCommunity.ts` lines 14, 55
- `useOptimization.ts` lines 45, 101
- `useSuppliers.ts` lines 34, 63
- `useCommunitySolar.ts` lines 45-46

While this is a widespread established pattern, it relies on an invariant that is not enforced by the type system.

**Recommendation:** Consider a wrapper that narrows the type:
```typescript
queryFn: ({ signal }) => {
  if (!region || !utilityType) throw new Error('Invariant violated')
  return fetchPosts(region, utilityType, page, 20, signal)
}
```

### 10. useSavingsSummary and useCombinedSavings fetch unconditionally -- no auth check before calling protected endpoint

**File:** `frontend/lib/hooks/useSavings.ts`, lines 22-34
**File:** `frontend/lib/hooks/useCombinedSavings.ts`, lines 4-10

Both hooks will fire queries as soon as they are mounted, regardless of authentication state. While the API client's 401 handler (in `client.ts`) will redirect to login, this means:
1. On unauthenticated pages that import components using these hooks, a 401 will trigger.
2. The React Query retry logic will attempt the request twice before the 4xx guard kills it.
3. The redirect counter in `sessionStorage` increments unnecessarily.

**Recommendation:** Accept an `enabled` parameter (like `useSavingsSummary` already does) and wire it to authentication state at the call site. For `useCombinedSavings`, add an `enabled` parameter:
```typescript
export function useCombinedSavings(enabled = true) {
  return useQuery({
    queryKey: ['savings', 'combined'],
    queryFn: ({ signal }) => getCombinedSavings(signal),
    enabled,
    staleTime: 1000 * 60 * 5,
  })
}
```

### 11. Zustand store hydration flash -- client state differs from server-rendered defaults until rehydration completes

**File:** `frontend/lib/store/settings.ts`, lines 99-207

The Zustand store uses `persist` middleware with `localStorage`. During SSR, the store returns `defaultSettings` (line 79-97). After client-side hydration, the store rehydrates from `localStorage`, which may contain different values (e.g., a previously-set region). This causes a hydration mismatch for any component that renders Zustand state server-side.

The SSR-safe `getStorage()` function (lines 106-120) correctly returns a no-op during SSR, but the store still returns defaults during SSR and real values after hydration. Any component that conditionally renders based on `region`, `utilityTypes`, or `displayPreferences.theme` will flash between default and persisted values.

**Recommendation:** Use Zustand's `onRehydrateStorage` callback to track hydration status, and have consuming components defer rendering until hydration is complete. Alternatively, use `skipHydration: true` and manually call `useSettingsStore.persist.rehydrate()` inside a `useEffect`.

### 12. Notification count query key is a prefix of the notifications list query key -- potential unintended invalidation

**File:** `frontend/lib/hooks/useNotifications.ts`, lines 15-18

```typescript
export const notificationKeys = {
  all: ["notifications"] as const,
  count: ["notifications", "count"] as const,
}
```

The `all` key `["notifications"]` is a prefix of the `count` key `["notifications", "count"]`. When `invalidateQueries({ queryKey: notificationKeys.all })` is called (lines 73, 90), React Query uses prefix matching by default, which means it invalidates BOTH the list query AND the count query. This is likely intentional (mutations call both invalidations anyway), but it means the explicit `invalidateQueries({ queryKey: notificationKeys.count })` calls on lines 74 and 91 are redundant -- they are already covered by the prefix-matched invalidation on the previous line.

The double invalidation is harmless but creates confusion about intent. More importantly, any future hook that creates a query with key `["notifications", "something-else"]` will be unintentionally invalidated whenever the list is invalidated.

**Recommendation:** Either rename the base key to `["notifications", "list"]` to avoid prefix collisions:
```typescript
export const notificationKeys = {
  all: ["notifications", "list"] as const,
  count: ["notifications", "count"] as const,
  root: ["notifications"] as const, // for invalidating everything
}
```
Or remove the redundant explicit `count` invalidation calls and document the prefix-matching behavior.

---

## P3 -- Low / Housekeeping

### 13. useAuth signIn and signUp callbacks have eslint-invisible missing dependencies

**File:** `frontend/lib/hooks/useAuth.tsx`, lines 302, 330

The `signIn` and `signUp` callbacks are wrapped in `useCallback(async (...) => { ... }, [])` with empty dependency arrays. They call `setIsLoading`, `setError`, `setUser` -- these are React state setters and are guaranteed stable, so this is correct. However, they also call `loginOneSignal` (line 275) which is an imported function. If `loginOneSignal` were ever changed to a closure-captured value, the empty deps would cause a stale closure. The pattern is safe today but fragile to future changes.

**Recommendation:** No immediate action needed. Consider adding a comment explaining that the empty dependency array is intentional because all referenced functions are stable module-level imports or React state setters.

### 14. Toast counter uses a ref (counterRef) without consideration for concurrent React renders

**File:** `frontend/lib/contexts/toast-context.tsx`, line 65

```typescript
const id = `toast-${++counterRef.current}`
```

The `++counterRef.current` mutation inside a state updater callback is fine in practice because React processes state updates synchronously within a single render. However, under React 18 concurrent features (Suspense transitions, `startTransition`), this mutation is outside of React's control and could theoretically produce duplicate IDs if the render is interrupted and retried. The risk is extremely low in practice.

**Recommendation:** Consider using `useId()` or `crypto.randomUUID()` for toast IDs if concurrent rendering is ever enabled for this provider.

### 15. useExportRates defaults enabled=false -- easy to misuse

**File:** `frontend/lib/hooks/useExport.ts`, line 8

```typescript
export function useExportRates(
  utilityType?: string,
  format: 'json' | 'csv' = 'json',
  state?: string,
  enabled = false,
)
```

The default for `enabled` is `false`, which is the opposite of every other hook in the codebase (they default to `true` or omit it entirely). A developer using `useExportRates('electricity')` without explicitly passing `enabled: true` would get a query that never fires, with no visible error. This is likely intentional (export is triggered on demand), but it breaks the principle of least surprise.

**Recommendation:** Add a JSDoc comment explaining why the default is `false`, or rename the parameter to something more descriptive like `triggerExport`.

### 16. useHeatingOilPrices and usePropanePrices and useWaterRates run without an enabled guard when state is omitted

**File:** `frontend/lib/hooks/useHeatingOil.ts`, line 9-15
**File:** `frontend/lib/hooks/usePropane.ts`, line 9-15
**File:** `frontend/lib/hooks/useWater.ts`, line 8-14

These hooks accept `state?: string` but do not have an `enabled: !!state` guard. When called without `state` (as `HeatingOilDashboard.tsx` does at line 22: `useHeatingOilPrices()`), the query fires with `state = undefined`, which the API functions handle by omitting the state param from the request. This is intentionally valid -- these endpoints return national data when no state is specified. However, it differs from the pattern used by `useHeatingOilHistory`, `useHeatingOilDealers`, and `useHeatingOilComparison` in the same file, which all require `state` and have `enabled: !!state`.

**Recommendation:** Add a brief comment to the hooks without `enabled` guards explaining that `state` is intentionally optional for national-level data.

### 17. useOptimization usePotentialSavings serializes entire appliances array into queryKey

**File:** `frontend/lib/hooks/useOptimization.ts`, line 97

```typescript
const stableAppliancesKey = JSON.stringify(appliances)
```

While this ensures value-based comparison for the queryKey (as the comment on line 94 explains), serializing a potentially large appliances array on every render has O(n) cost. For typical household appliance counts (5-20 items), this is negligible. However, if the appliance model grows in complexity or the array gets large, this could become a performance concern.

The `useOptimalSchedule` hook (line 25-28) handles this better by extracting and sorting only the IDs.

**Recommendation:** Consider using the same ID-extraction pattern as `useOptimalSchedule` for consistency:
```typescript
const stableAppliancesKey = appliances.map(a => a.id).sort().join(',')
```

### 18. QueryProvider retry function uses type assertions instead of type guards

**File:** `frontend/components/providers/QueryProvider.tsx`, lines 17-28

```typescript
retry: (failureCount, error) => {
  if (
    error &&
    typeof error === 'object' &&
    'status' in error &&
    typeof (error as { status: unknown }).status === 'number' &&
    (error as { status: number }).status < 500
  ) {
    return false
  }
  return failureCount < 2
},
```

The chain of type assertions (`error as { status: unknown }`, `error as { status: number }`) is verbose. This can be simplified using a type guard function, which also makes the logic reusable:

```typescript
function hasNumericStatus(err: unknown): err is { status: number } {
  return !!err && typeof err === 'object' && 'status' in err && typeof (err as Record<string, unknown>).status === 'number'
}
```

### 19. useAuth AuthProvider mixed concern -- profile-completeness redirect logic embedded in auth initialization

**File:** `frontend/lib/hooks/useAuth.tsx`, lines 189-238

The `initAuth` effect handles three conceptually distinct responsibilities:
1. Session validation and user state hydration (lines 147-164)
2. Zustand store synchronization (lines 174-220)
3. Profile-completeness redirect logic (lines 225-238)

The profile redirect logic in particular (checking `needsRegion`, `needsOnboarding`, calling `updateUserProfile`) is a page-routing concern rather than an auth concern. This makes `AuthProvider` harder to test in isolation, and changes to onboarding flow require modifying the auth provider.

**Recommendation:** Extract the profile-completeness check into a separate `useProfileGuard()` hook or a `ProfileGuardProvider` that wraps pages requiring complete profiles. The `PROFILE_REQUIRED_PREFIXES` array (lines 62-78) and helper functions (lines 83-106) are already well-factored for extraction.

---

## Files With No Issues Found

- `frontend/lib/hooks/usePrices.ts` -- Clean React Query patterns with appropriate staleTime/refetchInterval. QueryKey stability is good with primitive values.
- `frontend/lib/hooks/useAlerts.ts` -- Straightforward CRUD hooks with correct cache invalidation patterns.
- `frontend/lib/hooks/useRateChanges.ts` -- Good destructuring of params into primitives for queryKey stability.
- `frontend/lib/hooks/useGasRates.ts` -- Consistent patterns, correct enabled guards.
- `frontend/lib/hooks/useUtilityDiscovery.ts` -- Clean with appropriate long staleTime for infrequently-changing data.
- `frontend/lib/hooks/useNeighborhood.ts` -- Simple and correct.
- `frontend/lib/hooks/useReports.ts` -- Simple and correct.
- `frontend/lib/hooks/useCombinedSavings.ts` -- Clean (noted the missing auth guard under P2 but the hook itself is well-formed).
- `frontend/lib/hooks/useProfile.ts` -- Good Zustand sync pattern in queryFn. Correct use of `setQueryData` for optimistic update in mutation.
- `frontend/lib/hooks/useForecast.ts` -- Clean with appropriate staleTime values.
- `frontend/lib/hooks/useCommunitySolar.ts` -- Good input validation helpers exported for testing. Correct enabled guards.

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| P0 | 2 | SidebarContext silent failure on missing provider; cascading re-renders from unmemoized context value |
| P1 | 4 | Race condition in useGeocoding; unbounded message growth in useAgent; raw fetch bypassing apiClient in useDiagrams; permanent disconnect in useRealtime |
| P2 | 6 | Fire-and-forget fetch without abort in useAuth; polling overhead in useRealtimeSubscription; non-null assertions across 15+ hooks; unguarded auth-required queries; Zustand hydration flash; notification key prefix collision |
| P3 | 7 | Missing dependency comments; toast ID concurrent rendering edge case; export hook default; missing enabled comments; queryKey serialization cost; retry function verbosity; mixed concerns in AuthProvider |

**Overall Assessment:**

The hooks and state management layer is well-architected. The codebase demonstrates mature React Query patterns: consistent use of `staleTime`, correct `enabled` guards, proper queryKey stability (destructuring objects, sorting arrays, `JSON.stringify`), and appropriate cache invalidation after mutations. The Zustand store is properly SSR-safe with the `satisfies Storage` pattern. The SSE integration in `useRealtime` is sophisticated with exponential backoff and visibility-aware connection management.

The two P0 findings in `SidebarContext` are straightforward fixes (add `useMemo`, use null default). The P1 items are real but bounded in impact -- the race condition in `useGeocoding` only affects double-submit scenarios, and the unbounded agent messages only matter in very long sessions.

The most systemic pattern to address is the widespread reliance on non-null assertions (`!`) after `enabled` guards (P2 #9). While this is safe under current React Query behavior, it is a class of implicit invariant that could break silently. A utility wrapper or TypeScript branded type could enforce the narrowing at compile time.

**Test coverage note:** Cross-referencing with existing test files, hooks with tests include: `useRealtime`, `useDiagrams`, `useNotifications`, `useAgent`, `useHeatingOil`. Hooks without dedicated test files include: `useGeocoding`, `useCommunity`, `useProfile`, `useRateChanges`, `useCommunitySolar`, `useCCA`, `usePropane`, `useWater`, `useExport`, `useReports`, `useNeighborhood`, `useOptimization`, `useConnections`, `useSavings`, `useCombinedSavings`, `useSuppliers`, `useUtilityDiscovery`, `useGasRates`, `useForecast`. The untested hooks are primarily thin React Query wrappers (low risk), but `useGeocoding` in particular has the race condition (P1 #3) and would benefit from targeted tests.
