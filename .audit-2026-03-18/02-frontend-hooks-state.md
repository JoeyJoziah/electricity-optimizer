# Frontend Hooks & State Management Audit

**Scope**: `frontend/lib/hooks/`, `frontend/lib/store/`, `frontend/lib/contexts/`, `frontend/components/providers/`
**Date**: 2026-03-18
**Auditor**: react-specialist agent
**Files examined**: 27 hook files, 1 store, 2 context files, 1 provider — 31 total

---

## Files Audited

| File | Lines | Category |
|------|-------|----------|
| `frontend/lib/hooks/useAuth.tsx` | 483 | Auth / Context |
| `frontend/lib/hooks/useAgent.ts` | 84 | SSE Streaming |
| `frontend/lib/hooks/useAlerts.ts` | 79 | React Query |
| `frontend/lib/hooks/useCCA.ts` | 42 | React Query |
| `frontend/lib/hooks/useCombinedSavings.ts` | 10 | React Query |
| `frontend/lib/hooks/useCommunity.ts` | 59 | React Query / Mutations |
| `frontend/lib/hooks/useCommunitySolar.ts` | 87 | React Query |
| `frontend/lib/hooks/useConnections.ts` | 51 | React Query |
| `frontend/lib/hooks/useDiagrams.ts` | 87 | React Query |
| `frontend/lib/hooks/useExport.ts` | 24 | React Query |
| `frontend/lib/hooks/useForecast.ts` | 23 | React Query |
| `frontend/lib/hooks/useGasRates.ts` | 54 | React Query |
| `frontend/lib/hooks/useGeocoding.ts` | 36 | Async state |
| `frontend/lib/hooks/useHeatingOil.ts` | 42 | React Query |
| `frontend/lib/hooks/useNeighborhood.ts` | 11 | React Query |
| `frontend/lib/hooks/useNotifications.ts` | 83 | React Query |
| `frontend/lib/hooks/useOptimization.ts` | 105 | React Query |
| `frontend/lib/hooks/usePrices.ts` | 81 | React Query |
| `frontend/lib/hooks/useProfile.ts` | 47 | React Query |
| `frontend/lib/hooks/usePropane.ts` | 42 | React Query |
| `frontend/lib/hooks/useRateChanges.ts` | 52 | React Query |
| `frontend/lib/hooks/useRealtime.ts` | 209 | SSE / Polling |
| `frontend/lib/hooks/useReports.ts` | 11 | React Query |
| `frontend/lib/hooks/useSavings.ts` | 28 | React Query |
| `frontend/lib/hooks/useSuppliers.ts` | 192 | React Query / Mutations |
| `frontend/lib/hooks/useUtilityDiscovery.ts` | 30 | React Query |
| `frontend/lib/hooks/useWater.ts` | 31 | React Query |
| `frontend/lib/store/settings.ts` | 221 | Zustand |
| `frontend/lib/contexts/sidebar-context.tsx` | 70 | Context |
| `frontend/lib/contexts/toast-context.tsx` | 120 | Context |
| `frontend/components/providers/QueryProvider.tsx` | 39 | React Query Config |

---

## P0 — Critical (Crashes, Data Loss, Security)

### P0-01: React Query Cache NOT Cleared on Sign-Out — User Data Leakage

**File**: `frontend/lib/hooks/useAuth.tsx`, lines 333–367
**Also**: `frontend/components/providers/QueryProvider.tsx`

The `signOut` callback clears Zustand settings (`resetSettings()`) and the local `user` state, then does a full-page navigation via `window.location.href = '/auth/login'`. The full-page navigation does destroy the React component tree but it does **not** call `queryClient.clear()` before navigation. On the next sign-in (same browser session, same tab, no full reload), if the `QueryClient` instance survives (e.g. re-use in tests, React Fast Refresh in development, or a future architecture change that wraps `QueryProvider` inside `AuthProvider`), all cached data from the previous user (alerts, notifications, savings, profile, suppliers) would be served instantly to the next user before refetch.

The current architecture saves this in production because `window.location.href` triggers a full document reload, destroying the singleton `QueryClient`. However:
1. In development with Fast Refresh this is a latent bug.
2. If the architecture ever changes (e.g. moving `QueryProvider` outside the page component tree), it becomes a data-leak P0.
3. The `signOut` function has no `queryClient` reference and cannot call `clear()` even if the concern were identified.

**Recommendation**: Call `queryClient.clear()` in `signOut` before navigation. This requires either receiving `queryClient` as a prop to `AuthProvider`, using a module-level singleton ref, or subscribing to a sign-out event from within a React Query-aware hook.

---

### P0-02: Unguarded `window.location.pathname` Access in SSR Context

**File**: `frontend/lib/hooks/useAuth.tsx`, line 226

Inside the `initAuth` async function (called from a `useEffect` with `[]` deps), there is a second access of `window.location.pathname` on line 226 that is **not** guarded with `typeof window !== 'undefined'`:

```typescript
// Line 143 — correctly guarded
const pathname = typeof window !== 'undefined' ? window.location.pathname : '/'

// ... async operations ...

// Line 226 — NOT guarded
const path = window.location.pathname
```

The first guard on line 143 protects the function entry. However, this `useEffect` runs only on the client (effects never run on the server in Next.js App Router), so in practice it does not crash in standard RSC usage. But the file has `'use client'` at the top, meaning it is always a client component — the risk is low in the current architecture. Regardless, defensive consistency demands the guard be present. An SSR rendering context (e.g. Next.js middleware, a custom server, or a testing environment that does not stub `window`) would throw `ReferenceError: window is not defined`.

---

### P0-03: Agent SSE Stream — Reader Not Released on Abort

**File**: `frontend/lib/api/agent.ts`, lines 80–108

The `queryAgent` async generator function acquires a `ReadableStream` reader on line 80 (`response.body?.getReader()`). When the generator is aborted (the `signal` fires), the `for await ... of queryAgent(...)` loop in `useAgentQuery` (`useAgent.ts:38`) exits via the `AbortError` catch branch. The generator function itself is abandoned without ever calling `reader.cancel()` or `reader.releaseLock()`.

```typescript
// agent.ts:80
const reader = response.body?.getReader()
// No try/finally — reader.cancel() never called on abort
while (true) {
  const { done, value } = await reader.read()  // Hangs or leaks on abort
  ...
}
```

A locked `ReadableStream` reader holds the underlying network connection open. In browsers, this means the HTTP/2 or HTTP/1.1 connection may not be reused, and the stream remains open until the server closes it or a browser timeout fires. If users frequently cancel agent queries (the `cancel` button calls `abortRef.current.abort()`), this creates accumulating connection leaks per session.

**Recommendation**: Wrap the generator body in `try/finally` and call `reader.cancel()` in the finally block.

---

## P1 — High (Broken Functionality, Bad UX)

### P1-01: `useRealtimePrices` — `retryDelayRef` Not Reset Between Region Changes

**File**: `frontend/lib/hooks/useRealtime.ts`, lines 34–133

`retryDelayRef` tracks the exponential backoff delay. It is initialized to `1000` on mount (line 39) and reset to `1000` on a successful connection (line 60). However, the `useEffect` cleanup function does **not** reset `retryDelayRef.current`. When `region` changes (the effect dependency), the cleanup runs and a new effect starts — but `retryDelayRef.current` may still hold a large value (up to 30,000ms) from a previous failed connection cycle on a different region.

```typescript
const retryDelayRef = useRef(1000)  // Line 39

// Cleanup (lines 127-131)
return () => {
  mountedRef.current = false
  ctrl.abort()
  setIsConnected(false)
  // retryDelayRef.current NOT reset here
}
```

If the user switches regions after a connection failure, the next region's SSE connection will retry with up to 30-second delays instead of starting fresh at 1 second. This results in a very slow reconnect experience with no visual indication of why data is delayed.

**Recommendation**: Add `retryDelayRef.current = 1000` to the effect cleanup block.

---

### P1-02: `useRealtimeOptimization` and `useRealtimeSubscription` — `setIsConnected(true)` Fires Synchronously Before Actual Connection

**File**: `frontend/lib/hooks/useRealtime.ts`, lines 150–168 and 178–208

Both `useRealtimeOptimization` (line 160) and `useRealtimeSubscription` (line 198) call `setIsConnected(true)` synchronously in the effect body, before any actual network connection is established. These hooks use polling (`setInterval`), not SSE, so there is no real "connected" concept. Reporting `isConnected = true` immediately is misleading — the UI shows a "connected" badge when no data has yet been fetched and the first poll has not completed.

```typescript
// useRealtimeOptimization (lines 154-167)
useEffect(() => {
  const timer = setInterval(() => {
    queryClient.invalidateQueries({ queryKey: ['optimization'] })
  }, 60_000)
  setIsConnected(true)  // Fires before first poll
  return () => { clearInterval(timer); setIsConnected(false) }
}, [queryClient])
```

This is architecturally dishonest and may confuse consumers that use `isConnected` to gate UI elements.

---

### P1-03: `useProfile` — Side Effect (Zustand Sync) Inside `queryFn` Violates React Query Contract

**File**: `frontend/lib/hooks/useProfile.ts`, lines 16–28

The `queryFn` for `useProfile` performs a side effect — syncing the region to the Zustand store — inside the function:

```typescript
queryFn: async ({ signal }) => {
  const profile = await getUserProfile(signal)
  // Side effect inside queryFn:
  if (profile.region) {
    const store = useSettingsStore.getState()
    if (store.region !== profile.region) {
      store.setRegion(profile.region)  // State mutation during React Query fetch
    }
  }
  return profile
},
```

React Query's `queryFn` is designed to be a pure async function that fetches and returns data. Performing Zustand state mutations inside `queryFn` creates several problems:

1. **React Query may call `queryFn` multiple times in parallel** during deduplication or prefetch scenarios. Each call triggers a Zustand mutation, potentially causing a render cascade.
2. **Retry logic**: If `getUserProfile` fails and React Query retries, the partial execution history can leave the Zustand store in an inconsistent state.
3. **Background refetches** silently update Zustand without any component having explicitly requested the update, making data flow hard to trace.
4. **Testing**: The `queryFn` is not pure, making snapshot and unit testing unreliable without mocking Zustand.

The same pattern is repeated in `useAuth.tsx` (lines 216–220) though in that case it occurs in a direct effect handler, which is acceptable. In `useProfile`, the side effect belongs in an `onSuccess` callback.

**Recommendation**: Move the Zustand sync to `onSuccess` in the query options (or use the `select` option to transform, and handle Zustand sync in a dedicated `useEffect` watching the query data).

---

### P1-04: `useGeocoding` — No AbortController, Potential State Update on Unmounted Component

**File**: `frontend/lib/hooks/useGeocoding.ts`, lines 17–36

The `geocode` callback uses `apiClient.post()` with no abort signal. If the component calling `useGeocoding` unmounts while a geocoding request is in flight, the promise resolves and calls `setLoading(false)` and `setError(...)` on a component that no longer exists. While React 18 suppresses the "Can't perform state update on unmounted component" warning, this still represents:

1. A potential memory reference to a deallocated component subtree.
2. Incorrect state being written to a stale closure that persists until GC.
3. No ability to cancel the network request when the user navigates away mid-geocode.

```typescript
const geocode = useCallback(async (address: string): Promise<GeocodeResult | null> => {
  setLoading(true)
  setError(null)
  try {
    // No signal passed — request cannot be cancelled
    const data = await apiClient.post<GeocodeResponse>('/geocode', { address })
    return data.result ?? null
  } catch (e) {
    setError(e instanceof Error ? e.message : 'Geocoding failed')
    return null
  } finally {
    setLoading(false)  // Called even if component unmounted
  }
}, [])
```

**Recommendation**: Use `useRef<AbortController>` to track an in-flight request and cancel it in a `useEffect` cleanup, or accept an `AbortSignal` from the caller.

---

### P1-05: `useAuth` — `initAuth` Not Protected Against Concurrent Execution or Unmount

**File**: `frontend/lib/hooks/useAuth.tsx`, lines 140–248

The `initAuth` async function is called in a `useEffect` with `[]` deps. In React Strict Mode (development), effects are intentionally mounted, unmounted, and re-mounted. This means `initAuth` runs **twice** in development. The second run fires while the first may still be awaiting `Promise.allSettled` or the 1-second retry delay:

```typescript
useEffect(() => {
  const initAuth = async () => {
    // ... await Promise.allSettled(...)
    // ... await delay(PROFILE_RETRY_DELAY_MS)  // 1 second delay
    setUser(...)
    setIsLoading(false)
  }
  initAuth()
  // No cleanup, no AbortController, no isMounted guard
}, [])
```

There is no cancellation mechanism. On Strict Mode's second mount, a second `initAuth` runs, resulting in:
1. Two parallel calls to `authClient.getSession()`, `getUserSupplier()`, and `getUserProfile()`.
2. Two `setUser(...)` calls racing to update state with the same data (benign in production, noisy in development).
3. Two `loginOneSignal(session.user.id)` calls which may register the push subscription twice.
4. Two fire-and-forget `fetch(...auth/me...)` calls.

Additionally, if the component unmounts mid-`initAuth` (e.g. during a fast navigation), `setIsLoading(false)` and `setUser(...)` are called on an unmounted provider. There is no `isMounted` ref or cleanup return value.

**Recommendation**: Add an `AbortController` or `isMounted` ref, and clean it up in the effect return function.

---

### P1-06: `useSwitchStatus` — Missing `staleTime`, Polling Without Guard Causes Redundant Requests

**File**: `frontend/lib/hooks/useSuppliers.ts`, lines 102–109

`useSwitchStatus` uses `refetchInterval: 60000` but has no `staleTime` configured. React Query's default `staleTime` is whatever is set in `QueryProvider` (60 seconds). This means the query is immediately considered stale on mount, triggering an initial fetch, then polling every 60 seconds. When the window regains focus (even with `refetchOnWindowFocus: false` at the provider level), the stale check still applies.

More critically, there is no `enabled` guard — `useSwitchStatus` always runs even when `referenceNumber` is an empty string (the `enabled: !!referenceNumber` check is present, but this only stops the query when falsy; the hook is always instantiated). The query also has no `retry` override, inheriting the global retry policy (up to 2 retries on 5xx). For a switch status endpoint, retrying on failure may be appropriate, but polling without a terminal condition (e.g. `enabled` becoming `false` when status is "completed") means the poll runs indefinitely.

---

### P1-07: `useDiagrams` — Dev-Only API Routes Exposed Without Auth Check

**File**: `frontend/lib/hooks/useDiagrams.ts`, lines 15–48

The `fetchDiagramList`, `fetchDiagram`, `saveDiagram`, and `createDiagram` functions call `/api/dev/diagrams` routes using raw `fetch` with no credentials, no authentication headers, and no error handling beyond generic string messages:

```typescript
async function fetchDiagramList(): Promise<DiagramEntry[]> {
  const res = await fetch('/api/dev/diagrams')  // No credentials, no auth
  if (!res.ok) throw new Error('Failed to fetch diagrams')
  const json = await res.json()
  return json.diagrams
}
```

The hooks `useDiagramList` and `useDiagram` have no `staleTime` configured (defaulting to the global 60s). The `useSaveDiagram` and `useCreateDiagram` mutations have no `onError` handlers — failures are silently swallowed from the UI perspective unless the caller explicitly handles the mutation's `error` state.

The `/api/dev/` prefix suggests these are development-only routes, but there is no environment guard in the hook itself. If these routes exist in production (even gated by a route-level auth check), the hook provides no client-side protection.

---

### P1-08: `useAgentQuery` — Concurrent `sendQuery` Calls Not Guarded

**File**: `frontend/lib/hooks/useAgent.ts`, lines 27–58

When `sendQuery` is called while `isStreaming` is already `true`, the function creates a new `AbortController` and assigns it to `abortRef.current`, which **aborts the prior request**:

```typescript
abortRef.current = new AbortController()  // Line 32 — overwrites previous controller
```

This is an implicit abort of the previous query without user intent. However, there is no check at the start of `sendQuery` to guard against a second call while streaming. A UI race condition (e.g., rapid double-click on the submit button, or a programmatic call) will abort the in-flight stream and start a new one, leaving the message list in a half-written state (partial assistant message from the aborted stream, then a new user message appended).

The `isStreaming` state is checked in the UI (`AgentChat.tsx:81`), but since `sendQuery` itself does not guard against re-entry, any caller not going through the UI can trigger this condition.

---

### P1-09: `useAuth` — `signOut` Sets `isLoading = true` But Never Uses It to Block UI If Auth Client Throws

**File**: `frontend/lib/hooks/useAuth.tsx`, lines 333–367

In `signOut`, `setIsLoading(true)` is called at the top. The subsequent code in the `finally` block calls `setIsLoading(false)`. However, the code between these two calls includes:

```typescript
await authClient.signOut()   // Can throw
```

And the error is swallowed:

```typescript
try {
  await authClient.signOut()
} catch {
  // Swallow signOut errors — always clear local state
}
```

The design intent is correct (always sign out locally even if the server call fails). But `isLoading: true` is visible to any `useAuth()` consumer during this window. Components that render differently based on `isLoading` will show a loading state during sign-out, then immediately receive a full-page navigation. This is a minor race condition in practice, but reflects inconsistent state semantics.

---

## P2 — Medium (Inconsistencies, Maintainability)

### P2-01: `useSettingsStore` — Full-Store Subscription in Settings Page Causes Excessive Re-Renders

**File**: `frontend/app/(app)/settings/page.tsx`, line 64
**Store**: `frontend/lib/store/settings.ts`

The Settings page uses `useSettingsStore()` without a selector, subscribing to the entire store:

```typescript
const {
  region, utilityTypes, currentSupplier, annualUsageKwh, peakDemandKw,
  notificationPreferences, displayPreferences, setRegion, setUtilityTypes,
  setCurrentSupplier: setCurrentSupplierStore, setAnnualUsage, setPeakDemand,
  setNotificationPreferences, setDisplayPreferences, resetSettings,
} = useSettingsStore()  // No selector — full store subscription
```

Every write to ANY field in the settings store (from any component in the tree, including background region syncs from `useProfile`) will trigger a re-render of the entire Settings page. The page is complex (multiple form sections, multiple state updates) so this compounds to unnecessary renders. The exported selector hooks (`useRegion`, `useCurrentSupplier`, etc.) exist in `settings.ts` lines 210–218 but are not used in the Settings page itself.

**Recommendation**: Replace the destructured `useSettingsStore()` call with individual selector hooks or create a `useSettingsForm` custom hook that composes only the fields needed.

---

### P2-02: `useCommunity` — `useToggleVote` Lacks Optimistic Update, Vote Feels Laggy

**File**: `frontend/lib/hooks/useCommunity.ts`, lines 31–39

`useToggleVote` invalidates the entire `['community', 'posts']` query on success, which refetches the full page of posts from the server. Vote interactions typically expect instant UI feedback (toggle state on click, then confirm or revert on server response). The current implementation:

1. User clicks vote.
2. Network request fires (~100-500ms).
3. On success, full post list refetches (~100-500ms more).
4. UI updates.

Total latency: 200-1000ms with a visible flash as the list refetches. Optimistic updates using `onMutate` / `onError` / `onSettled` would make this instant.

---

### P2-03: `useCommunity` — Missing `'use client'` Directive

**File**: `frontend/lib/hooks/useCommunity.ts`

This file uses `useQuery`, `useMutation`, and `useQueryClient` — all client-only React Query hooks — but lacks a `'use client'` directive at the top. In Next.js App Router, any file that uses client hooks must declare `'use client'`. Without it, Next.js may attempt to bundle this as a Server Component, causing runtime errors if the component tree imports it in a server context.

The same issue affects: `useCCA.ts`, `useCombinedSavings.ts`, `useCommunitySolar.ts`, `useExport.ts`, `useForecast.ts`, `useHeatingOil.ts`, `useNeighborhood.ts`, `usePropane.ts`, `useReports.ts`, `useUtilityDiscovery.ts`, `useWater.ts` — **12 files total** missing `'use client'`.

While these hooks are currently only called from components that already have `'use client'`, the missing directive means:
1. A refactor moving the import into a Server Component boundary will silently fail or cause cryptic errors.
2. Tree-shaking analysis tools may misclassify these modules.
3. The Next.js linter/type checker may emit warnings.

---

### P2-04: `useCCAPrograms` and `useWaterRates` — Always-Fetch Without `enabled` Guard

**File**: `frontend/lib/hooks/useCCA.ts`, line 36
**File**: `frontend/lib/hooks/useWater.ts`, line 8

Both `useCCAPrograms` and `useWaterRates` accept an optional `state` parameter but do NOT include an `enabled` guard:

```typescript
// useCCA.ts:36
export function useCCAPrograms(state?: string) {
  return useQuery({
    queryKey: ['cca', 'programs', state],
    queryFn: ({ signal }) => listCCAPrograms(state, signal),
    staleTime: 1000 * 60 * 60,
    // No enabled guard — fires even when state is undefined
  })
}

// useWater.ts:8
export function useWaterRates(state?: string) {
  return useQuery({
    queryKey: ['water', 'rates', state],
    queryFn: ({ signal }) => getWaterRates(state, signal),
    staleTime: 1000 * 60 * 60 * 24,
    // No enabled guard — fires even when state is undefined
  })
}
```

When called without a `state` argument, these hooks fire network requests with `state = undefined`, which is then serialized as the string `"undefined"` or omitted in the API call. This is confirmed by `usePropanePrices` having the same pattern. The API endpoint may return national averages or an error depending on backend logic, but the intent is likely to not fetch until a state is known.

Compare with `useGasRates` which correctly guards with `enabled: !!region`.

---

### P2-05: `useAuth` — `delay()` Helper Creates Non-Cancellable Timeout During Component Lifecycle

**File**: `frontend/lib/hooks/useAuth.tsx`, lines 109–114, 202

The `delay(PROFILE_RETRY_DELAY_MS)` call (1 second) is awaited inside `initAuth`, which runs in a `useEffect`. If `AuthProvider` unmounts during this 1-second window (e.g. fast navigation, test teardown), the `setTimeout` inside `delay` cannot be cleared because there is no ref tracking it. The async continuation after `await delay(...)` calls `getUserProfile()` and then potentially `setProfileFetchFailed(true)` and `setIsLoading(false)` on an unmounted component.

This is the same root cause as P1-05 but affects the retry path specifically.

---

### P2-06: `SidebarContext` — `value` Prop Not Memoized with `useMemo`

**File**: `frontend/lib/contexts/sidebar-context.tsx`, lines 61–63

```typescript
return (
  <SidebarContext.Provider value={{ isOpen, toggle, close }}>
    {children}
  </SidebarContext.Provider>
)
```

The `value` object `{ isOpen, toggle, close }` is created as a new object reference on every render of `SidebarProvider`. `toggle` and `close` are correctly memoized with `useCallback`, but the containing object is not memoized. Any component consuming `useSidebar()` will re-render on every `SidebarProvider` re-render, even if `isOpen`, `toggle`, and `close` have not changed.

In the current app, `SidebarProvider` is mounted in `frontend/app/(app)/layout.tsx` and wraps the entire app layout. It re-renders on every navigation event (because `layout.tsx` re-renders on each route change). Every `useSidebar()` consumer (Header, Sidebar) will receive a new context value object reference on every page navigation, triggering unnecessary re-renders.

**Recommendation**: Wrap the value in `useMemo`:

```typescript
const value = useMemo(() => ({ isOpen, toggle, close }), [isOpen, toggle, close])
return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>
```

---

### P2-07: `useRealtime` — `useRealtimeSubscription` Config Object Dependency Causes Interval Restart

**File**: `frontend/lib/hooks/useRealtime.ts`, lines 178–208

The hook's `useEffect` depends on `[config.table, config.event, config.filter]` (line 206) — correctly destructured to primitives to avoid object reference instability. However, the `config` parameter type is `RealtimeConfig` — an object. If callers pass an inline object literal:

```typescript
useRealtimeSubscription({ table: 'prices', event: 'INSERT' }, handleUpdate)
```

...React will create a new `config` object reference on every render of the caller component. The effect's dependency array uses `config.table`, `config.event`, `config.filter` (not `config` itself), so the destructuring correctly prevents restarts when the primitive values are the same. This is well-handled.

However, `_queryClient` (line 182) is declared but never used — a dead variable that adds noise and may confuse future contributors about the hook's intent.

---

### P2-08: `useAuth` — Duplicate `loginOneSignal` Logic Between `initAuth` and `signIn`

**File**: `frontend/lib/hooks/useAuth.tsx`, lines 164 and 275

`loginOneSignal(session.user.id)` is called in two places:
1. Inside `initAuth` (line 164) — the session-restore path.
2. Inside `signIn` (line 275) — the explicit email/password sign-in path.

If a user signs in via email/password, the `signIn` callback succeeds, calls `loginOneSignal`, then does a `window.location.href = destination` which triggers a full page reload. The reload re-runs `initAuth`, which will call `loginOneSignal` again. This double-binds the OneSignal user subscription on every email/password sign-in.

For social OAuth and magic link flows (which bypass `signIn`), only `initAuth` calls `loginOneSignal`. The OneSignal `login()` call is idempotent for the same userId, so this does not currently cause visible errors, but it is unnecessary work and may cause duplicate subscription API calls.

---

### P2-09: `QueryProvider` — Global `refetchOnWindowFocus: false` May Mask Stale Data Issues

**File**: `frontend/components/providers/QueryProvider.tsx`, line 14

The global configuration disables `refetchOnWindowFocus` for all queries. This means users who switch away from the RateShift tab for extended periods (beyond `staleTime`) and return will see stale price data until the next scheduled `refetchInterval` fires or they manually refresh. For a price-monitoring application where real-time accuracy is a core value proposition, this is a user experience concern.

Price-related hooks (`useCurrentPrices`, `usePriceForecast`) already use `refetchInterval`, so they would eventually update. But hooks without `refetchInterval` (savings, suppliers, profile) will show data that may be many minutes old after a long tab switch.

This is a product decision rather than a clear bug, but the blanket `false` is overly broad. Per-query opt-in to `refetchOnWindowFocus: true` for price-sensitive queries would be more appropriate.

---

### P2-10: `useOptimization` — `useOptimalSchedule` Request Object Rebuilt on Every Render Without Memoization at Call Site

**File**: `frontend/app/(app)/optimize/page.tsx`, lines 65–70
**Hook**: `frontend/lib/hooks/useOptimization.ts`, lines 23–37

In `optimize/page.tsx`, `useOptimalSchedule` is called with an inline object:

```typescript
useOptimalSchedule({
  appliances,
  region: region ?? undefined,
  date: new Date().toISOString().split('T')[0],  // New string on every render
})
```

The hook itself correctly handles this by destructuring `applianceIds` and `region` into the queryKey. However, `date` is computed inline as `new Date().toISOString().split('T')[0]` — a new string value computed on every render. Since strings are compared by value in JavaScript, and React Query compares queryKey arrays by value, this is actually handled correctly (same date string = same key). But on a midnight boundary (11:59 PM to midnight), the `date` string changes across renders without user action, causing a silent query key change and a new fetch. This is likely intentional (fetch new day's schedule at midnight) but undocumented.

More importantly, the `request` object inside `queryFn` closes over the full `request` parameter, not the destructured primitives used in `queryKey`. If `appliances` changes reference (e.g. after `addAppliance`), the `queryFn` correctly receives the new `request` because `applianceIds` in the queryKey changes.

---

### P2-11: `useNotifications` and `useAlerts` — No `retry: false` Override for Auth-Gated Endpoints

**File**: `frontend/lib/hooks/useNotifications.ts`, `frontend/lib/hooks/useAlerts.ts`

These hooks fetch auth-required endpoints but rely entirely on the global retry policy in `QueryProvider`. The global policy retries up to 2 times on 5xx errors. When a user is not authenticated and the server returns 401, the `apiClient` redirects to login (so the query never actually resolves as an error). But for 403 (non-Pro tier) or 503 (temporary backend unavailability), the global retry policy fires 2 additional requests before failing.

`useConnections` correctly sets `retry: false` (line 49). `useSavings` sets `retry: 1`. The inconsistency across auth-gated hooks means some endpoints are retried unnecessarily.

---

### P2-12: Dual Price Alert Systems Are Not Synchronized

**File**: `frontend/lib/store/settings.ts` (Zustand `priceAlerts`) vs `frontend/lib/hooks/useAlerts.ts` (server-side alerts)

The Zustand settings store contains a `priceAlerts` array (line 24) representing local alert configurations. The `useAlerts` hook fetches server-side alert configurations from `/alerts`. These are two completely separate systems that are never synchronized:

1. `PricesContent.tsx` uses `useSettingsStore((s) => s.priceAlerts)` — the local Zustand list.
2. `AlertsContent.tsx` uses `useAlerts()` — the server list.

A user creating an alert in the Alerts UI (`/alerts` page, `AlertsContent.tsx`) creates a server-side alert. This does not appear in the Zustand `priceAlerts`. A user adding a price alert in the Prices UI uses Zustand only and does not persist to the server. This dual system means:
- Server alerts survive logout/login; local alerts do not.
- The `resetSettings()` call on sign-out clears local alerts permanently.
- Backend alert processing (cron triggers for email/push) uses server alerts only — local Zustand alerts are never evaluated.

**Recommendation**: The local Zustand `priceAlerts` should either be deprecated in favor of the server-side system, or a sync mechanism should be implemented. The current state is confusing and results in users losing locally created alerts on sign-out.

---

### P2-13: `useProfile` — `useUpdateProfile` Does Not Invalidate `['user-profile']` — Uses `setQueryData` Instead

**File**: `frontend/lib/hooks/useProfile.ts`, lines 34–47

`useUpdateProfile` uses `queryClient.setQueryData(['user-profile'], profile)` on success (line 40). This is a direct cache write instead of an invalidation. While this is a valid pattern, it means the cached data is replaced with the server response from the mutation (which may have a different shape than the `GET /profile` response, depending on API contract). If the PUT response shape differs from the GET shape — for example, if PUT returns a partial profile — the React Query cache will hold a partial profile object that `useProfile` consumers then receive.

Furthermore, if `useAuth`'s `initAuth` and `useProfile` both fetch the profile independently at startup, they use different code paths (`getUserProfile()` directly vs. React Query), leading to potential inconsistency.

---

## P3 — Low (Style, Minor Improvements)

### P3-01: `useRealtimeSubscription` — Dead `_queryClient` Variable

**File**: `frontend/lib/hooks/useRealtime.ts`, line 182

```typescript
const _queryClient = useQueryClient()
```

This variable is prefixed with `_` (indicating intentionally unused) but is never referenced in the function body. It adds a dependency to `useQueryClient()` without purpose, creating an unnecessary React Query subscription context lookup on every render.

---

### P3-02: `useRealtime` — `mountedRef` Pattern Is Outdated for React 18

**File**: `frontend/lib/hooks/useRealtime.ts`, lines 40–43, 128

The `mountedRef` pattern (`mountedRef.current = true` at effect start, `mountedRef.current = false` at cleanup) is a common pattern for guarding state updates after unmount. In React 18, `useState` setters are no-ops after unmount (they do not throw and are silently ignored). The `mountedRef` guards are still useful for preventing unnecessary work (e.g., not calling `setIsConnected(true)` when the component has already unmounted), but the comments in the code do not reflect this nuance.

More problematically, `mountedRef.current` is set to `true` at the TOP of the effect body on line 43, before the `if (!region) return` early return on line 44. This means `mountedRef.current` is set to `true` even when the effect exits early due to no region. This is functionally harmless but logically incorrect.

---

### P3-03: `useForecast` — Missing `'use client'` and Non-Null Assertion Without `enabled` Guard

**File**: `frontend/lib/hooks/useForecast.ts`, lines 4–15

```typescript
queryFn: ({ signal }) => getForecast(utilityType!, state, horizonDays, signal),
enabled: !!utilityType,
```

The non-null assertion `utilityType!` is safe because `enabled: !!utilityType` prevents the query from running when `utilityType` is falsy. This is a correct pattern but the non-null assertion still reads as potentially unsafe to maintainers. A comment explaining the safety guarantee would aid readability.

---

### P3-04: `useAgent` — `useAgentStatus` Has `retry: false` But No `staleTime` Alignment Comment

**File**: `frontend/lib/hooks/useAgent.ts`, lines 77–84

`useAgentStatus` has `staleTime: 60000` and `retry: false`. The `retry: false` is appropriate (usage stats failing should not be retried — it's not critical path). However, there is no `refetchInterval` — usage stats are only refetched on mount and when explicitly invalidated. If the user sends a query that consumes their daily limit, `useAgentStatus` will not update until the next mount (or a manual invalidation). The `useCreatePost` → `useAgentQuery` flow does not invalidate the `['agent', 'usage']` query after a message is sent.

---

### P3-05: `useDiagrams` — No `staleTime` on `useDiagramList` and `useDiagram`

**File**: `frontend/lib/hooks/useDiagrams.ts`, lines 50–63

Neither `useDiagramList` nor `useDiagram` specifies `staleTime`. They inherit the global 60-second staleTime from `QueryProvider`. For dev-only diagram data that changes infrequently (only on `useSaveDiagram`), this is fine, but an explicit `staleTime` would make the intent clear and prevent confusion when the global default changes.

---

### P3-06: `useCommunitySolar` — `useCommunitySolarSavings` QueryKey Uses Raw String Inputs

**File**: `frontend/lib/hooks/useCommunitySolar.ts`, lines 61–69

```typescript
queryKey: ['community-solar', 'savings', monthlyBill, savingsPercent],
```

`monthlyBill` and `savingsPercent` are strings (possibly `null`). React Query stringifies queryKey entries for cache key comparison, so two calls with `"100"` vs `"100.0"` would be treated as different queries even if they produce the same result. For numeric inputs, normalizing to `Number(...)` before including in the queryKey would prevent duplicate cache entries for semantically identical queries.

---

### P3-07: `useSuppliers` — `useInitiateSwitch` Should Invalidate `user-supplier` After Switch

**File**: `frontend/lib/hooks/useSuppliers.ts`, lines 86–97

`useInitiateSwitch.onSuccess` invalidates `['suppliers']` and `['recommendation']` but not `['user-supplier']`. After initiating a switch, the user's current supplier may change (or at least be in a "pending switch" state). The `useUserSupplier` hook's cache would remain stale until its 60-second `staleTime` expires.

---

### P3-08: `useAlerts` — Missing `onError` Handler in All Mutations

**File**: `frontend/lib/hooks/useAlerts.ts`, lines 41–79

`useCreateAlert`, `useUpdateAlert`, and `useDeleteAlert` have no `onError` handler. When mutations fail, the error is available via the mutation result's `error` property, but there is no centralized error handling. Callers must individually check `mutation.error` and render error UI. This is a minor pattern inconsistency compared to the Toast context being available app-wide.

---

### P3-09: `useAuth` — `useRequireAuth` Does Not Pass `callbackUrl`

**File**: `frontend/lib/hooks/useAuth.tsx`, lines 471–482

`useRequireAuth` redirects to `/auth/login` without preserving the current pathname as a `callbackUrl`:

```typescript
router.push('/auth/login')  // No callbackUrl — user loses their destination
```

The API client's 401 handler (`client.ts:91`) correctly includes `callbackUrl` in the redirect URL. `useRequireAuth`'s redirect does not, meaning users who get redirected by the hook (rather than by an API 401) will land on the dashboard after login instead of their original destination.

---

### P3-10: `settings.ts` — `resetSettings` Does Not Clear `priceAlerts`

**File**: `frontend/lib/store/settings.ts`, lines 189

`resetSettings: () => set(defaultSettings)` replaces state with `defaultSettings`, which includes `priceAlerts: []`. This correctly clears alerts. However, this observation needs pairing with P2-12: since these Zustand-only alerts are never synced to the server, clearing them on sign-out means locally created alerts are permanently lost on the next sign-in. This is a data loss path for users of the local alert feature.

---

## Summary Table

| ID | Severity | File | Issue |
|----|----------|------|-------|
| P0-01 | Critical | `useAuth.tsx` | React Query cache not cleared on sign-out — data leakage risk |
| P0-02 | Critical | `useAuth.tsx:226` | Unguarded `window.location.pathname` access post-async |
| P0-03 | Critical | `api/agent.ts:80` | ReadableStream reader not released on abort — connection leak |
| P1-01 | High | `useRealtime.ts:39` | `retryDelayRef` not reset on region change |
| P1-02 | High | `useRealtime.ts:160,198` | `isConnected` misreported as `true` before first poll |
| P1-03 | High | `useProfile.ts:22` | Side effect (Zustand sync) inside `queryFn` — breaks React Query contract |
| P1-04 | High | `useGeocoding.ts` | No AbortController — state update on unmounted component |
| P1-05 | High | `useAuth.tsx:140` | `initAuth` not protected against Strict Mode double-mount or unmount |
| P1-06 | High | `useSuppliers.ts:102` | `useSwitchStatus` missing `staleTime`, no terminal condition for poll |
| P1-07 | High | `useDiagrams.ts` | Dev API routes without auth, no `onError` on mutations |
| P1-08 | High | `useAgent.ts:32` | `sendQuery` overwrites `AbortController` mid-stream without guard |
| P1-09 | High | `useAuth.tsx:333` | `isLoading` semantics during sign-out are inconsistent |
| P2-01 | Medium | `settings/page.tsx:64` | Full-store `useSettingsStore()` subscription causes excessive re-renders |
| P2-02 | Medium | `useCommunity.ts:31` | `useToggleVote` lacks optimistic update — laggy vote UX |
| P2-03 | Medium | 12 hook files | Missing `'use client'` directive on client-only hook files |
| P2-04 | Medium | `useCCA.ts:36`, `useWater.ts:8` | Always-fetch queries without `enabled` guard when state is optional |
| P2-05 | Medium | `useAuth.tsx:202` | Non-cancellable `delay()` timeout during component lifecycle |
| P2-06 | Medium | `sidebar-context.tsx:62` | Context `value` object not memoized — unnecessary re-renders |
| P2-07 | Medium | `useRealtime.ts:182` | Dead `_queryClient` variable in `useRealtimeSubscription` |
| P2-08 | Medium | `useAuth.tsx:164,275` | Duplicate `loginOneSignal` call on email/password sign-in |
| P2-09 | Medium | `QueryProvider.tsx:14` | Global `refetchOnWindowFocus: false` too broad for price app |
| P2-10 | Medium | `optimize/page.tsx:69` | `new Date()` in query call site — undocumented midnight boundary behavior |
| P2-11 | Medium | `useNotifications.ts`, `useAlerts.ts` | Inconsistent `retry` configuration across auth-gated hooks |
| P2-12 | Medium | `settings.ts:24` + `useAlerts.ts` | Dual alert systems (Zustand vs server) are never synchronized |
| P2-13 | Medium | `useProfile.ts:40` | `setQueryData` on mutation may cause cache shape mismatch |
| P3-01 | Low | `useRealtime.ts:182` | Dead `_queryClient` variable |
| P3-02 | Low | `useRealtime.ts:43` | `mountedRef.current = true` set before early-return guard |
| P3-03 | Low | `useForecast.ts:11` | Non-null assertion without clarifying comment |
| P3-04 | Low | `useAgent.ts:79` | `useAgentStatus` not invalidated after messages sent |
| P3-05 | Low | `useDiagrams.ts:50` | No `staleTime` on diagram list/detail queries |
| P3-06 | Low | `useCommunitySolar.ts:62` | String queryKey entries for numeric inputs — duplicate cache entries |
| P3-07 | Low | `useSuppliers.ts:90` | `useInitiateSwitch` doesn't invalidate `user-supplier` |
| P3-08 | Low | `useAlerts.ts` | No `onError` handlers on alert mutations |
| P3-09 | Low | `useAuth.tsx:477` | `useRequireAuth` redirect drops `callbackUrl` |
| P3-10 | Low | `settings.ts:189` | Local `priceAlerts` cleared on sign-out — permanent data loss |

---

## Positive Observations

The following patterns are well-implemented and should be preserved:

1. **React Query AbortSignal threading**: The `queryFn: ({ signal }) => ...` pattern is consistently used across all React Query hooks, correctly threading cancellation through to `apiClient` methods.

2. **Zustand selector hooks**: `frontend/lib/store/settings.ts` exports fine-grained selector hooks (`useRegion`, `useCurrentSupplier`, etc.) that most consumers correctly use. The full-store subscription in `settings/page.tsx` is the one exception.

3. **SSR-safe storage factory**: The `getStorage()` function in `settings.ts` (lines 106–120) correctly handles SSR by returning a no-op storage when `window` is undefined, satisfying the `Storage` interface with `satisfies Storage`.

4. **QueryProvider retry policy**: The global retry policy in `QueryProvider.tsx` (lines 17–24) correctly distinguishes 4xx errors (no retry) from 5xx (retry up to 2x), preventing unnecessary retries on auth/permission failures.

5. **SSE auth error stop**: `useRealtimePrices` correctly throws on 401/403 (`onerror` handler, line 108–110), stopping the exponential backoff retry loop on auth failures rather than retrying indefinitely.

6. **Toast cleanup**: `ToastContext` correctly captures the `timersRef.current` reference in the `useEffect` cleanup (line 38) to avoid the stale-ref cleanup pattern. Timer cleanup on unmount is thorough.

7. **Stable queryKey construction**: Multiple hooks (`useOptimalSchedule`, `useCompareSuppliers`, `usePotentialSavings`) correctly serialize array/object queryKey parts to stable primitives (sorted join, `JSON.stringify`) to prevent infinite refetch loops.

8. **`routerRef` pattern in `useAuth`**: The router ref pattern (lines 132–135) correctly addresses the stale closure problem with `useRouter()` in the mount-only `initAuth` effect.

9. **Rate-change queryKey destructuring**: `useRateChanges` (lines 24–27) correctly destructures the `params` object into primitive queryKey entries, with an explanatory comment documenting why.

10. **Toast context `useMemo`**: `ToastContext` (line 96–98) correctly memoizes the context value with `useMemo`, preventing unnecessary re-renders of all toast consumers.

---

## Recommendations by Priority

### Immediate (P0)

1. Add `queryClient.clear()` call in `signOut` before `window.location.href` navigation. This requires passing `queryClient` into the AuthProvider or using a module-level event emitter.
2. Add `typeof window !== 'undefined'` guard around the unguarded `window.location.pathname` access in `useAuth.tsx:226`.
3. Wrap `queryAgent` generator body in `try/finally` and call `reader.cancel()` in the finally block to release the locked stream reader on abort.

### Short-term (P1 — within 1 sprint)

4. Reset `retryDelayRef.current = 1000` in `useRealtimePrices` cleanup.
5. Remove false `isConnected = true` in polling-based realtime hooks; return `false` or rename to `isPolling`.
6. Move Zustand sync in `useProfile.queryFn` to an `onSuccess` callback.
7. Add `AbortController` to `useGeocoding` with cleanup in `useEffect`.
8. Add `isMounted` ref or `AbortController` to `initAuth` in `useAuth`.
9. Add `staleTime` and a terminal `enabled` condition to `useSwitchStatus`.
10. Add `isStreaming` guard to the beginning of `sendQuery` in `useAgentQuery`.

### Medium-term (P2 — within 2 sprints)

11. Replace full-store `useSettingsStore()` in `settings/page.tsx` with individual selectors.
12. Add optimistic updates to `useToggleVote` using `onMutate`/`onError`/`onSettled`.
13. Add `'use client'` directive to all 12 hook files that are missing it.
14. Add `enabled` guards to `useCCAPrograms`, `useWaterRates`, `usePropanePrices`.
15. Memoize `SidebarContext` value with `useMemo`.
16. Decide on a single alert system (server-side) and deprecate Zustand `priceAlerts`.
17. Align retry configuration across all auth-gated query hooks.
