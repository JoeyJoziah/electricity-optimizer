# Audit Report: Frontend Hooks & State Management
**Date:** 2026-03-23
**Scope:** Custom hooks, Zustand stores, React Query patterns, API client layer, Context providers
**Files Reviewed:**

**Hooks (27 files):**
- `frontend/lib/hooks/useAuth.tsx`
- `frontend/lib/hooks/useProfile.ts`
- `frontend/lib/hooks/usePrices.ts`
- `frontend/lib/hooks/useSavings.ts`
- `frontend/lib/hooks/useSuppliers.ts`
- `frontend/lib/hooks/useAlerts.ts`
- `frontend/lib/hooks/useConnections.ts`
- `frontend/lib/hooks/useAgent.ts`
- `frontend/lib/hooks/useRealtime.ts`
- `frontend/lib/hooks/useNotifications.ts`
- `frontend/lib/hooks/useForecast.ts`
- `frontend/lib/hooks/useOptimization.ts`
- `frontend/lib/hooks/useGasRates.ts`
- `frontend/lib/hooks/useExport.ts`
- `frontend/lib/hooks/useRateChanges.ts`
- `frontend/lib/hooks/useReports.ts`
- `frontend/lib/hooks/useCommunity.ts`
- `frontend/lib/hooks/useCommunitySolar.ts`
- `frontend/lib/hooks/useNeighborhood.ts`
- `frontend/lib/hooks/useUtilityDiscovery.ts`
- `frontend/lib/hooks/useCCA.ts`
- `frontend/lib/hooks/useCombinedSavings.ts`
- `frontend/lib/hooks/useHeatingOil.ts`
- `frontend/lib/hooks/usePropane.ts`
- `frontend/lib/hooks/useWater.ts`
- `frontend/lib/hooks/useGeocoding.ts`
- `frontend/lib/hooks/useDiagrams.ts`

**Zustand Store (1 file):**
- `frontend/lib/store/settings.ts`

**API Client Layer (20 files):**
- `frontend/lib/api/client.ts`
- `frontend/lib/api/circuit-breaker.ts`
- `frontend/lib/api/agent.ts`
- `frontend/lib/api/prices.ts`
- `frontend/lib/api/suppliers.ts`
- `frontend/lib/api/alerts.ts`
- `frontend/lib/api/profile.ts`
- `frontend/lib/api/notifications.ts`
- `frontend/lib/api/savings.ts`
- `frontend/lib/api/optimization.ts`
- `frontend/lib/api/forecast.ts`
- `frontend/lib/api/gas-rates.ts`
- `frontend/lib/api/community.ts`
- `frontend/lib/api/community-solar.ts`
- `frontend/lib/api/rate-changes.ts`
- `frontend/lib/api/neighborhood.ts`
- `frontend/lib/api/utility-discovery.ts`
- `frontend/lib/api/export.ts`
- `frontend/lib/api/reports.ts`
- `frontend/lib/api/portal.ts`
- `frontend/lib/api/heating-oil.ts`
- `frontend/lib/api/propane.ts`
- `frontend/lib/api/water.ts`
- `frontend/lib/api/cca.ts`
- `frontend/lib/api/affiliate.ts`

**Context Providers & Supporting (6 files):**
- `frontend/lib/contexts/toast-context.tsx`
- `frontend/lib/contexts/sidebar-context.tsx`
- `frontend/lib/auth/client.ts`
- `frontend/lib/config/env.ts`
- `frontend/lib/notifications/onesignal.ts`
- `frontend/lib/utils/url.ts`

---

## P0 -- Critical (Fix Immediately)

### P0-1: `useAuth` initAuth effect has empty dependency array but reads `router` via stale closure path

**File:** `frontend/lib/hooks/useAuth.tsx`, lines 140-248

**Description:** The `initAuth` effect has an empty dependency array `[]` (line 248), which is intentional for mount-only execution. The `routerRef` pattern (lines 132-135) correctly mitigates the stale `router` closure. However, `useSettingsStore.getState()` is called directly inside the effect (lines 176, 216) which is safe because Zustand's `getState()` is always current. No issue with the ref pattern itself.

**However**, there is a real problem: the effect calls `setProfileFetchFailed(true)` and returns early on line 208-211 when the retry fails, but the `profileFetchFailed` state is never reset if the user navigates to a different page within the same AuthProvider mount. If the user goes to a public page and back to a protected page, the `profileFetchFailed` flag persists stale because `initAuth` only runs on mount (once). This means if the backend recovers, the user still sees the failure state until a full page reload.

**Severity justification:** Critical because it can permanently degrade the user experience within a session -- the user cannot recover from a transient profile fetch failure without a manual page refresh.

**Recommendation:** Either (a) reset `profileFetchFailed` on subsequent route changes by subscribing to pathname changes, or (b) add a manual "retry" action to the auth context, or (c) run the profile fetch portion on route changes to protected pages (not the full auth init).

### P0-2: `useGeocoding` has no abort controller -- concurrent calls cause state corruption

**File:** `frontend/lib/hooks/useGeocoding.ts`, lines 17-36

**Description:** The `geocode` callback (line 21) does not use an `AbortController` and has no guard against concurrent invocations. If the user types quickly in a geocode input and triggers multiple `geocode()` calls, the `loading` and `error` state will be updated by whichever request finishes last, not necessarily the most recent one. The `finally` block on line 31 will set `loading = false` when the FIRST request completes, even though a SECOND request may still be in flight.

This is a race condition: two calls in flight means the first to resolve sets `loading = false`, and the second resolution then also sets `loading = false` and may overwrite `error` state set by the first call.

**Severity justification:** Critical because it can display wrong geocoding results to users if the earlier, stale request resolves after the later, correct one. This directly affects the region selection flow, which gates access to all price/supplier data.

**Recommendation:** Add an `AbortController` ref and abort the previous request when a new one starts:

```typescript
const abortRef = useRef<AbortController | null>(null)

const geocode = useCallback(async (address: string) => {
  abortRef.current?.abort()
  const ctrl = new AbortController()
  abortRef.current = ctrl
  setLoading(true)
  setError(null)
  try {
    const data = await apiClient.post<GeocodeResponse>('/geocode', { address }, { signal: ctrl.signal })
    if (!ctrl.signal.aborted) return data.result ?? null
    return null
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return null
    if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : 'Geocoding failed')
    return null
  } finally {
    if (!ctrl.signal.aborted) setLoading(false)
  }
}, [])
```

Also add cleanup on unmount: `useEffect(() => () => abortRef.current?.abort(), [])`.

### P0-3: `useAgentQuery` sendQuery can cause state updates after unmount

**File:** `frontend/lib/hooks/useAgent.ts`, lines 27-58

**Description:** The `sendQuery` callback creates a new `AbortController` on each call (line 32), and the unmount cleanup (lines 21-25) aborts the ref. However, the `for await...of` loop (line 38) calls `setMessages` and `setError` without checking whether the component is still mounted. If the component unmounts while the async generator is yielding messages, the abort fires but there is a timing window: the generator may have already yielded a message that is being processed by the `setMessages` call before the `AbortError` propagates.

More critically, if `sendQuery` is called a second time before the first stream completes, `abortRef.current` is overwritten (line 32) but the first stream's `for await` loop is still running against the old controller. The old stream is NOT aborted because the ref was silently replaced. Both streams will now concurrently update `messages` state, causing duplicated or interleaved messages.

**Severity justification:** Critical because users who quickly re-submit queries will see corrupted interleaved chat messages from both streams.

**Recommendation:** Abort the PREVIOUS controller before creating a new one:

```typescript
const sendQuery = useCallback(async (prompt: string) => {
  // Abort any prior in-flight stream
  abortRef.current?.abort()

  const ctrl = new AbortController()
  abortRef.current = ctrl
  // ... rest of the logic
}, [])
```

---

## P1 -- High (Fix This Sprint)

### P1-1: `useDiagram` queryFn does not pass signal to fetch -- requests are not cancellable

**File:** `frontend/lib/hooks/useDiagrams.ts`, line 60

**Description:** The `useDiagram` hook destructures `signal` from the query context but does NOT pass it through: `queryFn: () => fetchDiagram(name!)`. The underlying `fetchDiagram` function (lines 22-26) uses raw `fetch()` without accepting a signal parameter. This means React Query cannot cancel in-flight diagram fetches when the component unmounts or the query key changes.

The same issue applies to `fetchDiagramList` (line 15), `saveDiagram` (line 28), and `createDiagram` (line 37) -- none accept `AbortSignal`.

**Severity justification:** High because uncancellable fetches cause wasted bandwidth and potential state updates after unmount. The diagram feature is dev-only, so the blast radius is limited, but the pattern is a bad example for future development.

**Recommendation:** Add `signal` parameter to all diagram fetch functions and pass it through from the query context:

```typescript
async function fetchDiagram(name: string, signal?: AbortSignal): Promise<DiagramData> {
  const res = await fetch(`/api/dev/diagrams/${name}`, { signal })
  // ...
}

export function useDiagram(name: string | null) {
  return useQuery({
    queryKey: ['diagrams', 'detail', name],
    queryFn: ({ signal }) => fetchDiagram(name!, signal),
    enabled: !!name,
  })
}
```

### P1-2: `useRealtimePrices` SSE sets state after unmount despite mountedRef guard

**File:** `frontend/lib/hooks/useRealtime.ts`, lines 42-132

**Description:** The `mountedRef` guard (line 58, 73, 99, 117) is a reasonable pattern, but there is a subtle issue: the cleanup function (lines 127-131) sets `mountedRef.current = false` and then calls `ctrl.abort()`. However, the `onerror` callback (line 98) checks `mountedRef` and then calls `setIsConnected(false)`. If the abort triggers the `onerror` callback synchronously (or nearly so), the guard works. But if `fetchEventSource` internally retries with a delay and the error callback fires from a microtask after the cleanup, `mountedRef` has already been set to false, so the guard catches it.

The real issue is the `disconnect` function (lines 134-141): it sets `mountedRef.current = false` (line 135), which is shared mutable state. If a user calls `disconnect()` and then the component re-renders with a new `region` value, the new effect instance will set `mountedRef.current = true` (line 43), but the old SSE connection may still be running. The old connection's callbacks will see `mountedRef.current = true` (from the new effect) and will attempt to update state, causing the new and old SSE connections to collide on shared state.

**Severity justification:** High because it can cause confusing price updates appearing from the wrong region if the user switches regions rapidly.

**Recommendation:** Instead of using a shared `mountedRef`, use a per-effect-instance flag:

```typescript
useEffect(() => {
  let active = true
  // Use `active` instead of `mountedRef.current` in all callbacks
  // ...
  return () => {
    active = false
    ctrl.abort()
  }
}, [region, interval, queryClient])
```

Remove the shared `mountedRef` or keep it only for the component-level unmount, not for per-effect cleanup.

### P1-3: `SidebarProvider` body scroll lock does not respond to viewport resize

**File:** `frontend/lib/contexts/sidebar-context.tsx`, lines 47-59

**Description:** The `isMobile` check (lines 48-49) is evaluated once when the effect runs (when `isOpen` changes), but does NOT re-evaluate on viewport resize. If the user opens the sidebar on mobile (overflow: hidden applied) and then resizes the browser to desktop width (e.g., rotating a tablet, or using browser devtools), the body remains locked because the effect only reruns when `isOpen` changes, not when `window.innerWidth` changes.

**Severity justification:** High because users on tablets or foldable devices frequently change viewport dimensions, and a locked body scroll on desktop width is a significant UX degradation.

**Recommendation:** Add a `resize` event listener or use a `matchMedia` query to reactively track viewport width:

```typescript
useEffect(() => {
  if (!isOpen) return

  const mql = window.matchMedia(`(max-width: ${LG_BREAKPOINT - 1}px)`)
  const update = () => {
    document.body.style.overflow = mql.matches ? 'hidden' : ''
  }
  update()
  mql.addEventListener('change', update)
  return () => {
    mql.removeEventListener('change', update)
    document.body.style.overflow = ''
  }
}, [isOpen])
```

### P1-4: `useAuth` initAuth fires `updateUserProfile` as fire-and-forget with no error boundary

**File:** `frontend/lib/hooks/useAuth.tsx`, line 235

**Description:** When the profile indicates onboarding is needed but region exists, the code calls `updateUserProfile({ onboarding_completed: true }).catch(() => {})`. This silently marks onboarding as complete even though the actual update may fail (network error, 500, etc.). If the update fails, the next page load will redirect the user back to onboarding, creating a confusing loop where the user believes they completed onboarding but keeps getting redirected.

**Severity justification:** High because this creates an invisible failure loop in the critical onboarding flow.

**Recommendation:** Either retry the update or remove the auto-completion logic. If the intent is to auto-migrate pre-region users, do it via a backend migration or a dedicated "mark migrated" endpoint that is idempotent and logged.

### P1-5: `markAllRead` in notifications API has unbounded N+1 problem

**File:** `frontend/lib/api/notifications.ts`, lines 73-78

**Description:** The `markAllRead` function first fetches all notifications, then fires N individual `markNotificationRead` requests via `Promise.allSettled`. If a user has 50 unread notifications, this creates 51 HTTP requests (1 list + 50 mark). The backend comment acknowledges the lack of a bulk endpoint, but this is a significant performance concern and can be rate-limited by the API gateway.

**Severity justification:** High because it can trigger rate limiting (120 req/min from the CF Worker config) for power users who accumulate many notifications, causing subsequent API calls to fail.

**Recommendation:** Implement a `POST /notifications/mark-all-read` backend endpoint that marks all unread notifications in a single SQL UPDATE. Until then, add a client-side limit (e.g., mark at most 20 at a time with a batch approach).

### P1-6: `useUtilityCompletion` queryKey uses `trackedTypes.join(',')` which is order-dependent

**File:** `frontend/lib/hooks/useUtilityDiscovery.ts`, line 25

**Description:** The `trackedTypes` array is joined with a comma to create a stable string key, but the array is NOT sorted first. If the caller passes `['gas', 'electric']` on one render and `['electric', 'gas']` on the next, React Query treats these as different cache keys and triggers a new fetch, even though the API result would be identical.

This is inconsistent with the approach used in `useCompareSuppliers` (line 81 of `useSuppliers.ts`) which correctly sorts before stringifying.

**Severity justification:** High because it causes unnecessary network requests and cache fragmentation for a feature used on every utility dashboard page.

**Recommendation:** Sort before joining:

```typescript
queryKey: ['utility-completion', state, [...trackedTypes].sort().join(',')],
```

### P1-7: `usePotentialSavings` uses `JSON.stringify` on the full `Appliance[]` which includes mutable fields

**File:** `frontend/lib/hooks/useOptimization.ts`, lines 96-105

**Description:** `JSON.stringify(appliances)` is used as a queryKey component for cache stability. While this is documented in the code comments, `JSON.stringify` output depends on property insertion order, which varies across JavaScript engines and can change if the `Appliance` type has optional fields that are sometimes present and sometimes absent. More importantly, if `Appliance` objects contain volatile fields (e.g., `lastUpdated`, `selected`, UI-only state), the cache key will change even when the meaningful data has not.

This is contrasted with `useOptimalSchedule` (line 25-28) which extracts only IDs -- a better approach.

**Severity justification:** High because it can cause excessive refetches on pages where appliance objects are reconstructed from Zustand state on every render, each time with potentially different property ordering.

**Recommendation:** Extract only the semantically meaningful fields for the queryKey, similar to how `useOptimalSchedule` does it:

```typescript
const stableKey = appliances
  .map(a => `${a.id}:${a.powerWatts}:${a.usageHoursPerDay}`)
  .sort()
  .join('|')
```

---

## P2 -- Medium (Fix Soon)

### P2-1: `useAuth` initAuth uses `window.location.pathname` directly instead of Next.js router

**File:** `frontend/lib/hooks/useAuth.tsx`, lines 143-145, 226

**Description:** The effect reads `window.location.pathname` directly (lines 143, 226) instead of using the Next.js `usePathname()` hook. While this works on initial mount, it creates an inconsistency: the rest of the auth flow uses `routerRef.current.replace()` (Next.js router) while the path checks use the raw browser API. If Next.js performs a soft navigation before the effect runs (unlikely but possible in React 19 concurrent rendering), the `window.location.pathname` may be stale relative to the conceptual "current route."

**Recommendation:** Import `usePathname()` from `next/navigation` and use it instead of `window.location.pathname`. Store it in a ref if needed for the mount-only effect.

### P2-2: `useWaterRates` is always enabled even when `state` is undefined

**File:** `frontend/lib/hooks/useWater.ts`, lines 8-14

**Description:** `useWaterRates` does not have an `enabled` guard -- it will fire a request even when `state` is `undefined`. The API function `getWaterRates` handles this by passing an empty params object, but it means every mount of a water rates component fires an unfocused "all states" request before the region is loaded.

Contrast with `useWaterBenchmark` (line 20) which correctly has `enabled: !!state`.

**Recommendation:** Add `enabled: !!state` to `useWaterRates`, consistent with the other water hooks.

### P2-3: `useHeatingOilPrices` is always enabled even when `state` is undefined

**File:** `frontend/lib/hooks/useHeatingOil.ts`, lines 9-15

**Description:** Same issue as P2-2. `useHeatingOilPrices` lacks an `enabled` guard, while `useHeatingOilHistory`, `useHeatingOilDealers`, and `useHeatingOilComparison` all correctly have `enabled: !!state`.

**Recommendation:** Add `enabled: !!state` to `useHeatingOilPrices`.

### P2-4: `usePropanePrices` is always enabled even when `state` is undefined

**File:** `frontend/lib/hooks/usePropane.ts`, lines 9-15

**Description:** Same pattern as P2-2 and P2-3. `usePropanePrices` lacks an `enabled` guard while the other propane hooks have it.

**Recommendation:** Add `enabled: !!state` to `usePropanePrices`.

### P2-5: `useCCAPrograms` fires queries without state filter -- potentially large response

**File:** `frontend/lib/hooks/useCCA.ts`, lines 36-42

**Description:** `useCCAPrograms` does not have an `enabled` guard on `state`. When `state` is `undefined`, the API call `listCCAPrograms(state, signal)` passes `undefined` and the API function sends an empty params object, fetching ALL CCA programs nationwide. This can be a large response and is likely unintended.

**Recommendation:** Add `enabled: !!state` or decide if the "all programs" view is intentional.

### P2-6: `useRealtimeSubscription` leaks `_queryClient` variable -- unused import

**File:** `frontend/lib/hooks/useRealtime.ts`, line 182

**Description:** The `_queryClient` variable is declared via `useQueryClient()` but never used in the function body. The underscore prefix suggests it was intentionally marked unused, but it still causes the `useQueryClient()` hook to run on every render, adding the component to the QueryClient's subscriber list unnecessarily.

**Recommendation:** Remove the `_queryClient` declaration and the `useQueryClient` import if it is the sole user.

### P2-7: `useCommunityPosts` requires both `region` AND `utilityType` -- confusing API contract

**File:** `frontend/lib/hooks/useCommunity.ts`, lines 11-18

**Description:** The `enabled` guard requires both `region` and `utilityType`, and the `queryFn` uses non-null assertions (`region!`, `utilityType!`). However, the parameter types are `string | undefined`, meaning callers pass optional values. If only one is available, the hook silently does nothing. The API layer `fetchPosts` requires both as positional params. This is not a bug, but the UX concern is that community pages may show a permanent loading spinner if `utilityType` is not set while `region` is.

**Recommendation:** Document the requirement more clearly, or provide a user-facing message when one of the required params is missing.

### P2-8: `useForecast` and `useExport` hooks are missing `'use client'` directive

**Files:**
- `frontend/lib/hooks/useForecast.ts` (line 1 starts with `import`)
- `frontend/lib/hooks/useExport.ts` (line 1 starts with `import`)
- `frontend/lib/hooks/useReports.ts` (line 1 starts with `import`)
- `frontend/lib/hooks/useNeighborhood.ts` (line 1 starts with `import`)
- `frontend/lib/hooks/useCombinedSavings.ts` (line 1 starts with `import`)

**Description:** These hook files use `useQuery` from `@tanstack/react-query` (a client-side hook) but do not include the `'use client'` directive at the top. In Next.js App Router, files without this directive are treated as Server Components by default. While the hooks likely work because they are imported into client components, the missing directive means they could be accidentally imported into a Server Component, causing a runtime error.

Most other hook files correctly include `'use client'` (e.g., `useAuth.tsx`, `usePrices.ts`, `useAlerts.ts`).

**Recommendation:** Add `'use client'` to the top of all five files for consistency and safety.

### P2-9: Circuit breaker state is a global singleton -- shared across all browser tabs

**File:** `frontend/lib/api/circuit-breaker.ts`, lines 39-152
**File:** `frontend/lib/api/client.ts`, lines 16-21

**Description:** The `circuitBreaker` is instantiated as a module-level singleton. Since Next.js bundles client code as a single entry, all instances of the app in different tabs share the same circuit breaker state (they are separate JS contexts, so actually they do NOT share state -- each tab gets its own module instance). However, within a single tab, a circuit that opens due to a transient 502 on one API call will cause ALL other API calls to route to the fallback URL for 30 seconds, even if those endpoints are healthy.

This is a design choice, not necessarily a bug, but it means a single flaky endpoint can trip the circuit for all endpoints.

**Recommendation:** Consider per-endpoint circuit breakers if endpoint health is expected to diverge, or document the design intent explicitly.

### P2-10: `useAuth` context value includes stable callbacks but memoization depends on all of them

**File:** `frontend/lib/hooks/useAuth.tsx`, lines 435-448

**Description:** The `useMemo` for the context value includes all callbacks in its dependency array (line 448). Since all callbacks are wrapped in `useCallback` with empty dependency arrays `[]`, they are all referentially stable. The `useMemo` effectively only re-creates the context value when `user`, `isLoading`, `error`, or `profileFetchFailed` changes. This is correct and well-optimized. However, the stable callbacks are listed in the deps array for lint compliance -- this is fine but could be simplified with a comment explaining they never change.

**Recommendation:** No code change needed, but a comment would help future maintainers understand the pattern.

### P2-11: `redirectInFlight` module-level flag in API client is not reset on successful navigation

**File:** `frontend/lib/api/client.ts`, lines 49, 88, 149

**Description:** The `redirectInFlight` flag is set to `true` on line 88 when a 401 redirect is initiated, and reset to `false` on line 149 when a successful response is received. However, if the redirect succeeds and the user logs in again, the new page load creates a fresh module scope, so the flag is naturally reset. The concern is a narrow edge case: if the redirect navigation is blocked (e.g., by a `beforeunload` handler or browser extension), `redirectInFlight` remains `true` permanently, suppressing all future 401 redirects for the session.

**Recommendation:** Add a timeout (e.g., 5 seconds) to auto-reset `redirectInFlight` as a safety valve:

```typescript
if (redirectInFlight) return false
redirectInFlight = true
setTimeout(() => { redirectInFlight = false }, 5000)
```

---

## P3 -- Low / Housekeeping

### P3-1: Inconsistent `staleTime` values across hooks for similar data domains

**Description:** There is no centralized stale time configuration. Each hook defines its own `staleTime` inline:
- Prices: 55s (current), 60s (history), 180s (forecast)
- Gas rates: 300s
- Water: 86400s (24h)
- Heating oil: 3600s (1h)
- Propane: 3600s (1h)
- Community solar: 600s (10min)
- Alerts: 30s
- Notifications: 30s (list), 60s (count)
- Profile: 60s
- Suppliers: 300s

While these values are individually reasonable, there is no shared constant file or configuration layer. This makes it difficult to tune cache behavior globally.

**Recommendation:** Create a `frontend/lib/config/cache-config.ts` that exports named stale times:

```typescript
export const STALE_TIMES = {
  REALTIME: 30_000,
  FREQUENT: 60_000,
  STANDARD: 300_000,
  INFREQUENT: 3_600_000,
  STATIC: 86_400_000,
} as const
```

### P3-2: Several hooks use non-null assertions (`!`) on parameters guarded only by `enabled`

**Files:** Most hooks, e.g., `usePrices.ts` line 20 (`region!`), `useSuppliers.ts` line 34 (`region!`), etc.

**Description:** The pattern `enabled: !!region` combined with `queryFn: () => fn(region!)` is used throughout. While React Query guarantees `queryFn` is never called when `enabled` is `false`, the non-null assertion suppresses TypeScript's safety check. If a future refactor removes the `enabled` guard, the assertion would silently pass through `null` at runtime.

**Recommendation:** Consider a runtime guard inside `queryFn` as a defense-in-depth pattern:

```typescript
queryFn: ({ signal }) => {
  if (!region) throw new Error('region is required')
  return getGasRates({ region }, signal)
}
```

Or use a custom wrapper that narrows the type.

### P3-3: `useDiagramList` has no `staleTime` -- defaults to 0

**File:** `frontend/lib/hooks/useDiagrams.ts`, lines 50-55

**Description:** Unlike every other hook in the codebase, `useDiagramList` and `useDiagram` do not set `staleTime`. React Query v5 defaults to `staleTime: 0`, meaning data is always considered stale and refetched on every mount/focus. For a dev-only diagram feature this is low-priority but inconsistent.

**Recommendation:** Add `staleTime: 30_000` for consistency.

### P3-4: Zustand settings store key name is outdated

**File:** `frontend/lib/store/settings.ts`, line 192

**Description:** The persist storage key is `'electricity-optimizer-settings'`, which is the old pre-rebrand project name. The application is now branded as "RateShift." While this does not affect functionality (changing the key would clear all users' persisted settings), it is a cosmetic inconsistency.

**Recommendation:** Plan a migration: read from both `'electricity-optimizer-settings'` and `'rateshift-settings'`, write to the new key, and eventually remove the old key reader after a release cycle.

### P3-5: `useRefreshPrices` is the only hook returning a raw callback -- inconsistent with other patterns

**File:** `frontend/lib/hooks/usePrices.ts`, lines 93-99

**Description:** `useRefreshPrices` returns a single `useCallback` rather than an object or a React Query result. This is not wrong, but it is the only hook in the codebase with this pattern. Every other hook returns a React Query result or an object with named properties.

**Recommendation:** Consider wrapping it as `{ refresh }` for consistency, or document why the bare callback is preferred.

### P3-6: `useAuth` type assertion `session.user.createdAt?.toString()` may not be ISO string

**File:** `frontend/lib/hooks/useAuth.tsx`, lines 160, 271

**Description:** `createdAt: session.user.createdAt?.toString() || ''` -- if `createdAt` is a `Date` object from Better Auth, `.toString()` produces a locale-dependent string like `"Mon Mar 23 2026 ..."` rather than an ISO 8601 string. The `AuthUser` interface declares `createdAt: string` without specifying the format.

**Recommendation:** Use `.toISOString()` for consistent formatting, or document the expected format.

### P3-7: `useConnections` hook has `retry: false` unlike most other hooks

**File:** `frontend/lib/hooks/useConnections.ts`, line 49

**Description:** `useConnections` explicitly disables retries (`retry: false`), while most other hooks use React Query's default retry behavior (3 retries). The 403 handling in `fetchConnections` explains this (upgrade prompts should not be retried), but it also means genuine 500 errors on the connections endpoint are not retried.

**Recommendation:** Use a custom `retry` function that only retries non-403 errors:

```typescript
retry: (failureCount, error) => {
  if (error instanceof Error && 'status' in error && (error as any).status === 403) return false
  return failureCount < 3
}
```

### P3-8: `useNotificationCount` polling interval is 120s but `staleTime` is 60s -- gap causes redundant fetches

**File:** `frontend/lib/hooks/useNotifications.ts`, lines 52-60

**Description:** `refetchInterval: 120_000` with `staleTime: 60_000` means the data becomes stale at 60s but the next poll is at 120s. When the user focuses the window between 60-120s, `refetchOnWindowFocus: true` triggers an extra fetch because the data is stale. This is actually desirable behavior (documented in the comments), so this is informational rather than a bug.

**Recommendation:** No change needed -- the behavior is intentional and well-documented. This note exists to confirm the auditor reviewed it.

### P3-9: `useAlertHistory` default `pageSize` of 20 is duplicated between hook and API layer

**File:** `frontend/lib/hooks/useAlerts.ts`, line 30 (default `pageSize = 20`)
**File:** `frontend/lib/api/alerts.ts`, line 117 (default `pageSize = 20`)

**Description:** The default page size is defined in both the hook and the API function. If one changes, they will silently diverge. The hook's default shadows the API function's default.

**Recommendation:** Remove the default from one layer (preferably the API layer, letting the hook be the canonical default).

### P3-10: `useSavingsSummary` uses the API client directly instead of a dedicated API function

**File:** `frontend/lib/hooks/useSavings.ts`, lines 22-34

**Description:** Most hooks call a function from the corresponding `lib/api/*.ts` module. `useSavingsSummary` instead calls `apiClient.get` directly. While functional, this breaks the consistent layering pattern where hooks only call API functions, and API functions are the sole consumers of `apiClient`.

**Recommendation:** Create a `getSavingsSummary` function in `lib/api/savings.ts` and call it from the hook.

---

## Files With No Issues Found

The following files were reviewed and found to have no issues requiring attention:

- `frontend/lib/hooks/useAlerts.ts` -- Clean CRUD pattern with proper cache invalidation
- `frontend/lib/hooks/useRateChanges.ts` -- Good destructuring of params into queryKey primitives
- `frontend/lib/hooks/useOptimization.ts` -- Excellent queryKey stability with sorted appliance IDs
- `frontend/lib/hooks/useGasRates.ts` -- Consistent pattern, all hooks have `enabled` guards
- `frontend/lib/hooks/useCombinedSavings.ts` -- Simple, clean pattern
- `frontend/lib/hooks/useProfile.ts` -- Good Zustand sync pattern with signal support
- `frontend/lib/hooks/useNotifications.ts` -- Well-documented polling rationale
- `frontend/lib/hooks/useCommunitySolar.ts` -- Good numeric validation helpers
- `frontend/lib/contexts/toast-context.tsx` -- Proper timer cleanup on unmount
- `frontend/lib/auth/client.ts` -- Clean SSR-safe initialization
- `frontend/lib/utils/url.ts` -- Solid URL safety utilities
- `frontend/lib/notifications/onesignal.ts` -- Proper SSR guards and lazy loading
- `frontend/lib/config/env.ts` -- Good fail-fast production validation
- `frontend/lib/api/prices.ts` -- Well-structured with proper signal threading
- `frontend/lib/api/suppliers.ts` -- Clean API layer
- `frontend/lib/api/alerts.ts` -- Clean API layer
- `frontend/lib/api/profile.ts` -- Clean API layer
- `frontend/lib/api/gas-rates.ts` -- Clean API layer
- `frontend/lib/api/community.ts` -- Clean API layer
- `frontend/lib/api/community-solar.ts` -- Clean API layer
- `frontend/lib/api/rate-changes.ts` -- Clean API layer
- `frontend/lib/api/neighborhood.ts` -- Clean API layer
- `frontend/lib/api/utility-discovery.ts` -- Clean API layer
- `frontend/lib/api/export.ts` -- Clean API layer
- `frontend/lib/api/reports.ts` -- Clean API layer
- `frontend/lib/api/portal.ts` -- Clean API layer
- `frontend/lib/api/heating-oil.ts` -- Clean API layer
- `frontend/lib/api/propane.ts` -- Clean API layer
- `frontend/lib/api/water.ts` -- Clean API layer
- `frontend/lib/api/cca.ts` -- Clean API layer
- `frontend/lib/api/affiliate.ts` -- Clean API layer
- `frontend/lib/api/circuit-breaker.ts` -- Well-implemented state machine with proper half-open logic

---

## Summary

### Overall Assessment

The frontend hooks and state management layer is well-architected overall. The codebase demonstrates strong patterns: consistent use of React Query with `signal` threading for cancellation, proper `enabled` guards on most queries, stable queryKey construction (sorted/stringified arrays), and clean separation between API functions and hook wrappers. The Zustand store is properly configured with SSR-safe storage, `partialize` for selective persistence, and focused selector hooks.

### Statistics
- **Total files reviewed:** 54
- **P0 (Critical):** 3 findings
- **P1 (High):** 7 findings
- **P2 (Medium):** 11 findings
- **P3 (Low):** 10 findings
- **Files with no issues:** 32

### Key Themes

1. **Race conditions in imperative hooks** (P0-2, P0-3): The `useGeocoding` and `useAgentQuery` hooks both have race conditions when invoked multiple times rapidly. The fix is consistent: abort the previous request before starting a new one.

2. **Missing `enabled` guards** (P2-2, P2-3, P2-4, P2-5): Four hooks (`useWaterRates`, `useHeatingOilPrices`, `usePropanePrices`, `useCCAPrograms`) fire queries without an `enabled` guard, unlike their sibling hooks. This is an inconsistency that causes unnecessary network requests.

3. **Missing `'use client'` directives** (P2-8): Five hook files lack the `'use client'` directive despite using client-only React hooks. This is a latent Server Component compatibility issue.

4. **SSE/realtime shared mutable state** (P1-2): The `useRealtimePrices` hook uses a shared `mountedRef` that can be corrupted when the effect re-runs with new dependencies.

5. **QueryKey stability** (P1-6, P1-7): Two hooks have suboptimal queryKey strategies -- one is order-dependent, the other serializes the full object graph. Both have correct patterns elsewhere in the codebase to reference.

### Priority Recommendation

Fix P0-2 and P0-3 first -- they cause user-visible data corruption (wrong geocoding result, interleaved chat messages). P0-1 is a UX degradation that requires a page refresh to recover but does not corrupt data. Then address P1-5 (N+1 notification marking) as it can trigger rate limiting under normal usage.
