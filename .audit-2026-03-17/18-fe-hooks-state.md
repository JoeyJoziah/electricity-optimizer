# Audit Report: Frontend Hooks, Stores & Contexts
## Date: 2026-03-17
## Auditor: Code Review Agent (claude-sonnet-4-6)

---

### Executive Summary

27 files were audited across `frontend/lib/hooks/` (26 files), `frontend/lib/store/` (1 file), and `frontend/lib/contexts/` (2 files). The codebase is in genuinely strong shape: React Query is used correctly throughout with `AbortSignal` threading, `enabled` guards, and stable `queryKey` construction. The Zustand store uses the `satisfies Storage` SSR stub pattern per project conventions. The `useRealtimePrices` SSE hook has careful `mountedRef` discipline. Two-thirds of hooks have `'use client'` directives where appropriate.

There are **no P0 auth token storage issues** (Better Auth uses httpOnly cookies as documented). Two significant findings stand out: the Zustand settings store is **not cleared on sign-out**, which leaks the previous user's region, supplier, and appliance data to the next user on a shared browser. Second, `useGeocoding` calls a backend `/internal/geocode` route that is protected by `verify_api_key` (the `X-API-KEY` header used by GHA workflows), so every client-side geocode call will receive a 403 that surfaces confusingly to end users. Most other findings are medium-to-low severity style or robustness issues.

---

### Findings

---

#### P0 — Critical

_No critical auth token storage or session mismanagement issues found._ Better Auth's httpOnly cookie model is correctly relied upon — no tokens are written to `localStorage` or exposed in global state. The `signOut` flow calls both the backend Redis cache invalidation endpoint and `authClient.signOut()` before clearing local state.

---

#### P1 — High

**H1 — Zustand settings store not cleared on sign-out (data leakage between accounts)**

File: `frontend/lib/hooks/useAuth.tsx` lines 321–347; `frontend/lib/store/settings.ts` line 189

The `signOut` callback in `AuthProvider` clears `user` state and calls `authClient.signOut()`, but never calls `useSettingsStore.getState().resetSettings()` or `queryClient.clear()`. The Zustand store is `persist`-backed to `localStorage`, so it survives sign-out. The React Query cache also survives. If a second user signs in on the same browser (or the original user signs back in as a different account — e.g. switching Google accounts), they will immediately see the previous user's `region`, `currentSupplier`, `appliances`, `priceAlerts`, `annualUsageKwh`, and all other persisted preferences. The supplier data is particularly sensitive because it identifies a specific account's energy provider and consumption profile.

`resetSettings()` exists on the store but is only wired to the Settings page "Reset Settings" button and the GDPR account-deletion flow — not to `signOut`.

Recommendation:

```typescript
// In useAuth.tsx signOut callback, add before router.push:
useSettingsStore.getState().resetSettings()
queryClient.clear()  // requires queryClient from useQueryClient() passed in or from context
```

Because `signOut` is a `useCallback` without `useQueryClient` in scope, the cleanest fix is to pull `queryClient` from `useQueryClient()` at the top of `AuthProvider` and reference it inside the callback:

```typescript
const queryClient = useQueryClient()

const signOut = useCallback(async () => {
  // ... existing fetch + authClient.signOut() ...
  useSettingsStore.getState().resetSettings()
  queryClient.clear()
  setUser(null)
  setIsLoading(false)
  router.push('/auth/login')
}, [router, queryClient])
```

---

**H2 — `useGeocoding` calls an internal backend route that requires `X-API-Key`**

File: `frontend/lib/hooks/useGeocoding.ts` line 25

The hook calls `apiClient.post('/internal/geocode', { address })`. The backend registers all `/internal/*` routes under a shared `APIRouter(dependencies=[Depends(verify_api_key)])` — confirmed in `backend/api/v1/internal/__init__.py` line 25. The `verify_api_key` dependency checks for the `X-API-Key` header, which is only set by GHA workflows and the CF Worker (not by the browser `apiClient`). Every call from the frontend will therefore receive a `403 Forbidden`, which the `apiClient` converts to an `ApiClientError` with status 403 — not caught by the current error handler in `useGeocoding`, which only displays a generic "Geocoding failed" message.

This effectively means the onboarding geocoding feature is completely broken for end users without any visible indicator of why.

The fix depends on intent. If `/internal/geocode` is meant to be a public-facing convenience endpoint for authenticated users, it should be moved out of the internal router (or its `verify_api_key` dependency removed for that route specifically). If it must stay internal, a Next.js API route proxy at `/api/geocode` should call it server-side with the `INTERNAL_API_KEY` set from an env var.

---

**H3 — `useAgentQuery` does not cancel the in-flight streaming generator on unmount**

File: `frontend/lib/hooks/useAgent.ts` lines 14–65

`useAgentQuery` manages streaming via `abortRef`, but never registers a `useEffect` cleanup. If the component consuming `useAgentQuery` unmounts while a stream is in progress (e.g., the user navigates away from `/assistant`), the `for await` loop in `sendQuery` continues running, calling `setMessages` and `setError` on an unmounted component. In React 18+ strict mode and development, this raises "Can't perform a state update on an unmounted component" warnings. In production it wastes server resources completing the SSE stream.

The `cancel()` function exists but must be called manually by the consumer. An automatic cleanup effect is missing:

```typescript
// Add to useAgentQuery:
useEffect(() => {
  return () => {
    abortRef.current?.abort()
  }
}, [])
```

---

**H4 — `useHeatingOilPrices`, `usePropanePrices`, and `useWaterRates` fetch without `enabled` guard when `state` is `undefined`**

Files: `frontend/lib/hooks/useHeatingOil.ts` line 9–15; `frontend/lib/hooks/usePropane.ts` lines 9–15; `frontend/lib/hooks/useWater.ts` lines 8–13

These three "top-level" hooks in each file accept `state?: string` and make no `enabled` check:

```typescript
// useHeatingOilPrices — no enabled guard
export function useHeatingOilPrices(state?: string) {
  return useQuery({
    queryKey: ['heating-oil', 'prices', state],
    queryFn: ({ signal }) => getHeatingOilPrices(state, signal),
    staleTime: 1000 * 60 * 60,
  })
```

If `state` is `undefined`, the queryFn fires immediately with an `undefined` argument. Whether the API call succeeds depends on whether the backend route accepts a missing state param. It is inconsistent with all sibling hooks in the same files (e.g., `useHeatingOilHistory` has `enabled: !!state`). The `useWaterBenchmark` and `useWaterRates` have the same pattern. This can result in spurious API requests at page load before the user's state is resolved, and React Query will cache the `undefined`-state result under a key it may conflate with later valid results.

Fix: add `enabled: !!state` to the three unguarded hooks. For `useWaterRates` the state param is optional and the backend may return national averages, but if that is intentional it should be documented explicitly.

---

#### P2 — Medium

**M1 — Supplier object in Zustand store populated with placeholder zeros from auth init**

File: `frontend/lib/hooks/useAuth.tsx` lines 165–176

During auth initialization, `setCurrentSupplier` is called with hardcoded `avgPricePerKwh: 0`, `standingCharge: 0`, and `estimatedAnnualCost: 0`:

```typescript
setCurrentSupplier({
  id: supplier.supplier_id,
  name: supplier.supplier_name,
  avgPricePerKwh: 0,       // placeholder
  standingCharge: 0,       // placeholder
  greenEnergy: supplier.green_energy,
  rating: supplier.rating ?? 0,
  estimatedAnnualCost: 0,  // placeholder
  tariffType: 'variable',
})
```

If any component renders `currentSupplier.avgPricePerKwh` before `useUserSupplier()` finishes its own fetch, it will display 0 p/kWh. The fix is either to not set the supplier in auth init at all (letting `useUserSupplier` be the canonical source), or to mark these fields explicitly as `null` so consumers can distinguish "not yet loaded" from "genuinely free".

---

**M2 — `useSwitchStatus` polls every 60 seconds with no maximum retry or terminal state check**

File: `frontend/lib/hooks/useSuppliers.ts` lines 102–109

```typescript
export function useSwitchStatus(referenceNumber: string) {
  return useQuery({
    queryKey: ['switch-status', referenceNumber],
    queryFn: ({ signal }) => getSwitchStatus(referenceNumber, signal),
    enabled: !!referenceNumber,
    refetchInterval: 60000,
  })
}
```

`refetchInterval` is constant — the query polls indefinitely regardless of the switch status returned. If the switch reaches a terminal state (`COMPLETED` or `FAILED`), the poll continues until the component unmounts. This is wasteful and causes unnecessary backend load. The fix is to use a `refetchInterval` function that stops when done:

```typescript
refetchInterval: (query) => {
  const status = query.state.data?.status
  if (status === 'COMPLETED' || status === 'FAILED') return false
  return 60_000
},
```

---

**M3 — `useRealtimeSubscription` config object causes dependency array instability if caller passes inline object**

File: `frontend/lib/hooks/useRealtime.ts` lines 174–204

The `useEffect` dependency array includes `config.table`, `config.event`, and `config.filter` (primitives — this part is correct). However, the function signature accepts `config: RealtimeConfig` as an object. If a caller passes an inline object `useRealtimeSubscription({ table: 'prices' })`, a new object reference is created on every render. The `useEffect` correctly destructures to primitives in its dependency array, so the interval itself is stable. However, the `_queryClient` variable declared at line 178 is unused (prefixed with `_` but never referenced in the effect body), indicating dead code that should be removed.

Also: `setIsConnected(true)` fires synchronously before the interval is set. Since `setIsConnected(false)` is in the cleanup, the `isConnected` value immediately becomes `true` without any actual connection being established — this is misleading for consumers expecting it to reflect a real connection state.

---

**M4 — `useProfile` queryFn performs a Zustand side effect inside React Query's executor**

File: `frontend/lib/hooks/useProfile.ts` lines 13–29

```typescript
queryFn: async ({ signal }) => {
  const profile = await getUserProfile(signal)
  if (profile.region) {
    const store = useSettingsStore.getState()
    if (store.region !== profile.region) {
      store.setRegion(profile.region)   // <-- side effect in queryFn
    }
  }
  return profile
},
```

React Query queryFns are supposed to be pure fetchers. Side effects here mean:
1. If `queryFn` is retried (on 5xx), `setRegion` may fire multiple times.
2. If the query is hydrated from SSR/cache without a network request, the side effect does not run — the Zustand store won't be in sync on initial hydration.
3. Testing is harder because tests must set up Zustand expectations inside a React Query mock.

The same pattern is used in `useUpdateProfile`'s `onSuccess` callback (line 43), which is the correct pattern. The fix is to move the Zustand sync to an `onSuccess` callback:

```typescript
export function useProfile() {
  return useQuery({
    queryKey: ['user-profile'],
    queryFn: ({ signal }) => getUserProfile(signal),
    staleTime: 60000,
  })
}

// In the consuming component or a wrapper:
useEffect(() => {
  if (profileData?.region) {
    const store = useSettingsStore.getState()
    if (store.region !== profileData.region) store.setRegion(profileData.region)
  }
}, [profileData?.region])
```

Or use React Query's `select` + a separate `useEffect` on the return value of `useProfile`.

---

**M5 — `sidebar-context.tsx` body scroll lock reads `window.innerWidth` at effect run time, not at resize time**

File: `frontend/lib/contexts/sidebar-context.tsx` lines 47–59

```typescript
useEffect(() => {
  const isMobile =
    typeof window !== 'undefined' && window.innerWidth < LG_BREAKPOINT

  if (isOpen && isMobile) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
  return () => {
    document.body.style.overflow = ''
  }
}, [isOpen])
```

`window.innerWidth` is captured once when `isOpen` changes. If the sidebar is opened on a mobile viewport, then the window is resized to desktop width while the sidebar remains open, the body scroll lock persists. The sidebar overlay is then hidden by CSS (`lg:hidden`) but `overflow: hidden` on body remains. A `resize` event listener or `matchMedia` check would fix this:

```typescript
useEffect(() => {
  const mq = typeof window !== 'undefined'
    ? window.matchMedia(`(max-width: ${LG_BREAKPOINT - 1}px)`)
    : null
  const isMobile = mq?.matches ?? false

  if (isOpen && isMobile) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
  return () => {
    document.body.style.overflow = ''
  }
}, [isOpen])
```

For the resize-while-open case, a separate listener on `mq` would also be needed, though this is a minor UX edge case in practice.

---

**M6 — `useCommunityPosts` calls `fetchPosts(region!, utilityType!, ...)` but non-null asserts may still be undefined**

File: `frontend/lib/hooks/useCommunity.ts` lines 11–17

```typescript
export function useCommunityPosts(region?: string, utilityType?: string, page = 1) {
  return useQuery({
    queryKey: ['community', 'posts', region, utilityType, page],
    queryFn: ({ signal }) => fetchPosts(region!, utilityType!, page, 20, signal),
    enabled: !!region && !!utilityType,
    ...
  })
}
```

The `enabled` guard is correct, but the non-null assertions `region!` and `utilityType!` are misleading. TypeScript's `!` does not remove `undefined` at runtime — it only suppresses the TS error. If `enabled` is somehow bypassed (e.g., via `queryClient.fetchQuery` called externally), `fetchPosts` will receive `undefined` for both arguments. This is a general pattern across multiple hooks in this file. Consider narrowing types: extract a typed overload or use a helper that asserts and throws.

---

#### P3 — Low

**L1 — 12 hooks missing `'use client'` directive**

Files: `useForecast.ts`, `useReports.ts`, `useExport.ts`, `useNeighborhood.ts`, `useHeatingOil.ts`, `usePropane.ts`, `useWater.ts`, `useCCA.ts`, `useCombinedSavings.ts`, `useCommunitySolar.ts`, `useUtilityDiscovery.ts`, `useCommunity.ts`

These hooks use `useQuery`/`useMutation` from `@tanstack/react-query`, which depends on React context. They will throw "Missing QueryClientProvider" if accidentally imported into a Server Component. While in practice they are only consumed from `'use client'` component files, adding the directive is a defensive best practice and consistent with the 15 hooks that already have it.

---

**L2 — `useRealtimeOptimization` sets `isConnected: true` before any real connection**

File: `frontend/lib/hooks/useRealtime.ts` lines 146–165

```typescript
useEffect(() => {
  const timer = setInterval(() => {
    queryClient.invalidateQueries({ queryKey: ['optimization'] })
  }, 60_000)
  setIsConnected(true)   // fires synchronously — no SSE or WebSocket opened
  return () => { clearInterval(timer); setIsConnected(false) }
}, [queryClient])
```

The hook name implies a realtime connection but the implementation is polling. `isConnected` is always `true` as long as the component is mounted. If a consumer displays a "Connected" badge based on `isConnected`, it will always show green even if the backend is down. Consider renaming to `useOptimizationPoller` or changing `isConnected` to a more accurate `isPolling`.

---

**L3 — `useDiagrams` uses bare `fetch()` instead of `apiClient`, bypassing the circuit breaker and retry logic**

File: `frontend/lib/hooks/useDiagrams.ts` lines 15–35

All four fetch functions call `fetch('/api/dev/diagrams...')` directly without credentials handling or the circuit breaker. This is presumably intentional (the diagrams API is a Next.js API route, not the FastAPI backend), but it is inconsistent and the 403 error from `createDiagram` is handled correctly with `err.error` fallback while the others just rethrow. Add `signal` support to `fetchDiagramList` and `fetchDiagram` to allow React Query abort propagation:

```typescript
// fetchDiagramList currently ignores signal:
queryFn: fetchDiagramList   // no signal threading

// should be:
queryFn: ({ signal }) => fetchDiagramList(signal)
```

---

**L4 — `useCommunitySolar` query key uses raw string inputs for monetary values**

File: `frontend/lib/hooks/useCommunitySolar.ts` lines 53–69

```typescript
queryKey: ['community-solar', 'savings', monthlyBill, savingsPercent],
```

`monthlyBill` and `savingsPercent` are raw strings (e.g., `"149.99"`, `"10"`). React Query will treat `"149.99"` and `"149.990"` as different cache entries even though they represent the same computation. Since `isValidNumericInput` already parses these to numbers, the queryKey should use the parsed numeric values:

```typescript
const billNum = parseFloat(monthlyBill ?? '')
const pctNum = parseFloat(savingsPercent ?? '')
queryKey: ['community-solar', 'savings', billNum, pctNum],
```

---

**L5 — `useAlerts` / `useAlertHistory` share a `['alerts']` root key but `useAlerts` invalidates too broadly**

File: `frontend/lib/hooks/useAlerts.ts` lines 41–65

`useCreateAlert`, `useUpdateAlert`, and `useDeleteAlert` all call:
```typescript
queryClient.invalidateQueries({ queryKey: ['alerts'] })
```

This key matches both `['alerts']` (the config list) and `['alerts', 'history', page, pageSize]` (the history). Every create/update/delete therefore refetches the alert history as well as the config list. The history is unlikely to change immediately on a CRUD operation (it shows past triggers, not config). This causes an unnecessary extra API request on every alert mutation. The mutation `onSuccess` callbacks should target the config list specifically:

```typescript
queryClient.invalidateQueries({ queryKey: ['alerts'], exact: true })
```

---

**L6 — `useProfile` stale time (60s) is shorter than `useCurrentPrices` polling interval (60s), causing unnecessary profile refetches on window focus**

File: `frontend/lib/hooks/useProfile.ts` line 27

With `staleTime: 60000` and React Query's default `refetchOnWindowFocus: true`, the profile is refetched every time the user alt-tabs and returns within one minute. User profile data (name, region) changes rarely — a stale time of 5–10 minutes is more appropriate and consistent with the `useUserSupplier` hook's 60-second stale time, which also fetches user-specific backend data.

---

**L7 — `useSettingsStore` persists `currentSupplier` (including `Supplier` type) to `localStorage` but does not validate on rehydration**

File: `frontend/lib/store/settings.ts` lines 194–204

The `partialize` config persists `currentSupplier` which contains `Supplier` type fields. If the `Supplier` type schema changes (new required fields, renamed fields), stale `localStorage` data will be rehydrated as a partially-typed object without any validation or migration. Zustand's `persist` middleware supports a `version` + `migrate` option that should be used here since the schema has already evolved (the `tariffType` field with value `'variable'` is hardcoded in auth init, suggesting the persisted schema has been extended). Consider adding:

```typescript
version: 1,
migrate: (persistedState, version) => {
  // handle schema upgrades
  return persistedState as SettingsState
},
```

---

**L8 — `useCCAPrograms` has no `enabled` guard when `state` is undefined**

File: `frontend/lib/hooks/useCCA.ts` lines 36–42

```typescript
export function useCCAPrograms(state?: string) {
  return useQuery({
    queryKey: ['cca', 'programs', state],
    queryFn: ({ signal }) => listCCAPrograms(state, signal),
    staleTime: 1000 * 60 * 60,
  })
  // no enabled: !!state
}
```

If `state` is `undefined`, `listCCAPrograms(undefined, signal)` is called immediately on mount, which may return national CCA data (or an error if the backend requires a state param). This is inconsistent with the three sibling hooks (`useCCADetect` has `enabled: !!zipCode || !!state`, `useCCACompare` has `enabled: !!ccaId && ...`, `useCCAInfo` has `enabled: !!ccaId`). Adding `enabled: !!state` aligns behavior unless undefined-state is intentionally allowed.

---

**L9 — `useGeocoding` does not debounce; callers can trigger rapid API calls**

File: `frontend/lib/hooks/useGeocoding.ts`

`useGeocoding` is an imperative hook (not React Query — it uses raw `useState`). The `geocode` callback is memoized with `useCallback` with no dependencies, which is correct. However, there is no built-in debounce. If it is wired to an address input field (the most common use case), every keypress triggers a call unless the consumer adds their own debounce. This is a design-level concern: either the hook should expose a debounced variant or the documentation should explicitly require consumers to debounce before calling.

Note: this concern is secondary to H2 above (the endpoint currently returns 403 regardless).

---

**L10 — TODO or attention comment in `useRealtimeSubscription`: unused `_queryClient`**

File: `frontend/lib/hooks/useRealtime.ts` line 178

```typescript
const _queryClient = useQueryClient()
```

`_queryClient` is declared but never used in `useRealtimeSubscription`. The leading `_` signals it was intentionally silenced. If it was removed as part of a refactor, the `useQueryClient()` call should be removed too to avoid creating a pointless subscription to the QueryClient context on every render.

---

### Statistics

| Severity | Count | Files Affected |
|----------|-------|---------------|
| P0 — Critical | 0 | — |
| P1 — High | 4 | `useAuth.tsx`, `useGeocoding.ts`, `useAgent.ts`, `useHeatingOil.ts` / `usePropane.ts` / `useWater.ts` |
| P2 — Medium | 6 | `useAuth.tsx`, `useSuppliers.ts`, `useRealtime.ts`, `useProfile.ts`, `sidebar-context.tsx`, `useCommunity.ts` |
| P3 — Low | 10 | Multiple |
| **Total** | **20** | **17 files** |

**Files with no issues found:** `useAlerts.ts` (queryKey design is solid), `useNotifications.ts` (notification key factory + tab-pause are well done), `usePrices.ts` (stale/refetch interval gap is correctly handled), `useRateChanges.ts` (param destructuring to primitives is correct), `useOptimization.ts` (appliance key stabilization via sort+join is correct), `useConnections.ts` (403 upgrade error handling is correct), `useCommunitySolar.ts` (input validation helpers are cleanly separated and exported for testing), `toast-context.tsx` (timer Map cleanup on unmount is correct), `settings.ts` (SSR stub uses `satisfies Storage` per project convention), `useCompareSuppliers`/`usePotentialSavings` (sort+JSON.stringify key stabilization patterns are correct).

**Test coverage:** 24 of 27 files have corresponding test files. Missing: `useForecast.ts` (no `__tests__/hooks/useForecast.test.ts` found), `usePropane.ts` (no test file found), `sidebar-context.tsx` and `toast-context.tsx` have tests.

---

### Recommendations

**Immediate (before next production deployment):**
1. Fix H2 — move `/internal/geocode` to a public authenticated endpoint or proxy via Next.js API route. This is currently a silent 403 in production affecting onboarding.
2. Fix H1 — add `resetSettings()` and `queryClient.clear()` to the `signOut` callback.

**Short-term (next sprint):**
3. Fix H3 — add unmount cleanup `useEffect` to `useAgentQuery`.
4. Fix H4 — add `enabled: !!state` guards to `useHeatingOilPrices`, `usePropanePrices`, `useWaterRates`.
5. Fix M2 — make `useSwitchStatus` polling self-terminate on terminal state.
6. Fix M4 — move Zustand side effect from `useProfile` queryFn to `onSuccess` callback.
7. Add `'use client'` to the 12 hooks missing it (L1).

**Backlog:**
8. Add Zustand `version`/`migrate` for `currentSupplier` schema evolution (L7).
9. Rename `useRealtimeOptimization` and fix `isConnected` semantics (L2, M3).
10. Remove `_queryClient` dead code from `useRealtimeSubscription` (L10).
11. Add `signal` threading to `useDiagramList` and `useDiagram` (L3).
12. Resolve `useCCAPrograms` guard inconsistency (L8).
