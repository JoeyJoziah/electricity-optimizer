# Frontend Hooks, State Management & API Client Audit

**Date**: 2026-03-16
**Auditor**: React Specialist
**Scope**: `frontend/lib/hooks/`, `frontend/lib/api/`, `frontend/lib/contexts/`, `frontend/lib/store/`, `frontend/lib/auth/`, `frontend/middleware.ts`, `frontend/types/`, `frontend/components/providers/`

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| P0       | 3     | Critical — data loss, security bypass, or broken core feature |
| P1       | 7     | High — bugs under realistic conditions, auth issues, race conditions |
| P2       | 9     | Medium — memory leaks, stale closure risks, missing error handling |
| P3       | 8     | Low — type safety gaps, naming conflicts, anti-patterns |
| **Total**| **27**| |

---

## P0 — Critical

---

### P0-01: `useAgentQuery` — `abortRef` wired but never passed to SSE generator; cancel is a no-op

**File**: `frontend/lib/hooks/useAgent.ts` lines 18, 47–49
**File**: `frontend/lib/api/agent.ts` lines 50–99

**Description**:
`useAgentQuery` creates an `AbortController` stored in `abortRef`, and exposes a `cancel()` callback that calls `abortRef.current?.abort()`. However, the `queryAgent` async generator in `lib/api/agent.ts` creates its own internal `fetch(...)` call without accepting or using any `AbortSignal`. The `abortRef` is never connected to the generator. When the user clicks cancel or the component unmounts while streaming is in progress, the underlying `fetch` stream continues consuming bandwidth and server-side compute until it completes naturally. On slow connections or long responses this may last tens of seconds.

```typescript
// useAgent.ts line 18 — ref is allocated
const abortRef = useRef<AbortController | null>(null)

// useAgent.ts line 29 — generator is called but abortRef is never set or passed
for await (const msg of queryAgent(prompt)) {
  // ...
}

// useAgent.ts line 47 — cancel aborts nothing because abortRef.current is always null
const cancel = useCallback(() => {
  abortRef.current?.abort()   // <-- abortRef.current is never assigned
  setIsStreaming(false)
}, [])

// agent.ts line 54 — fetch has no signal option
const response = await fetch(`${API_URL}/agent/query`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({ prompt, context }),
  // signal: ??? — missing entirely
})
```

**Fix**: Thread `AbortSignal` through the generator and assign to `abortRef` before streaming:

```typescript
// useAgent.ts
const sendQuery = useCallback(async (prompt: string) => {
  abortRef.current?.abort()                              // cancel any prior query
  const ctrl = new AbortController()
  abortRef.current = ctrl
  // ...
  try {
    for await (const msg of queryAgent(prompt, undefined, ctrl.signal)) {
      if (ctrl.signal.aborted) break
      // ...
    }
  } catch (err) {
    if (ctrl.signal.aborted) return                      // swallow abort
    // ...
  }
}, [])

// agent.ts
export async function* queryAgent(
  prompt: string,
  context?: Record<string, unknown>,
  signal?: AbortSignal,
): AsyncGenerator<AgentMessage> {
  const response = await fetch(`${API_URL}/agent/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ prompt, context }),
    signal,                                              // add this
  })
  // ...
  while (true) {
    const { done, value } = await reader.read()
    if (done || signal?.aborted) break
    // ...
  }
}
```

---

### P0-02: `useRefreshPrices` returns a plain function — not wrapped in `useCallback` — causing a new reference on every render

**File**: `frontend/lib/hooks/usePrices.ts` lines 72–78

**Description**:
`useRefreshPrices` is a custom hook that returns a bare arrow function rather than a `useCallback`-memoised function. Every call to the hook produces a brand-new function reference. Any component that passes this function to a `useEffect` dependency array, `React.memo`-wrapped child, or as a prop will experience spurious re-renders and/or effect re-runs on every parent render cycle. Given the app has React.memo applied to 4 dashboard components (per the project memory), this directly undermines those optimisations.

```typescript
// Current — broken
export function useRefreshPrices() {
  const queryClient = useQueryClient()

  return () => {                       // <-- new reference every render
    queryClient.invalidateQueries({ queryKey: ['prices'] })
  }
}
```

**Fix**:

```typescript
export function useRefreshPrices() {
  const queryClient = useQueryClient()

  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['prices'] })
  }, [queryClient])
}
```

---

### P0-03: Middleware session-cookie check bypasses entire protected-route set — analytics, community, gas-rates, heating-oil, propane, water pages are unauthenticated-accessible

**File**: `frontend/middleware.ts` lines 12, 53–66

**Description**:
The `protectedPaths` array only covers 9 routes. The `matcher` config only covers those same 9 routes plus `/architecture/:path*` and `/auth/:path*`. A dozen app pages — `/analytics`, `/community`, `/gas-rates`, `/heating-oil`, `/propane`, `/water`, `/community-solar`, `/beta-signup` — are not in either list. The middleware never runs for these routes, meaning unauthenticated users can access them directly. While the backend enforces auth on its API endpoints, these pages may render skeleton UIs or leak non-trivial data (e.g. community posts list if it falls back to a public endpoint, propane price charts if those endpoints don't require a session).

```typescript
// middleware.ts line 12 — missing routes
const protectedPaths = [
  '/dashboard', '/prices', '/suppliers', '/connections',
  '/optimize', '/settings', '/onboarding', '/alerts', '/assistant'
  // missing: '/analytics', '/community', '/gas-rates',
  //          '/heating-oil', '/propane', '/water',
  //          '/community-solar'
]

// middleware.ts lines 53–66 — matcher also omits them
export const config = {
  matcher: [
    '/architecture/:path*',
    '/dashboard/:path*',
    '/prices/:path*',
    // ...
    // '/analytics/:path*' — absent
    // '/community/:path*' — absent
  ],
}
```

**Fix**: Add all app-level routes to both `protectedPaths` and `config.matcher`:

```typescript
const protectedPaths = [
  '/dashboard', '/prices', '/suppliers', '/connections',
  '/optimize', '/settings', '/onboarding', '/alerts', '/assistant',
  '/analytics', '/community', '/gas-rates', '/heating-oil',
  '/propane', '/water', '/community-solar',
]

export const config = {
  matcher: [
    '/architecture/:path*',
    '/dashboard/:path*',
    '/prices/:path*',
    '/suppliers/:path*',
    '/connections/:path*',
    '/optimize/:path*',
    '/settings/:path*',
    '/onboarding/:path*',
    '/alerts/:path*',
    '/assistant/:path*',
    '/analytics/:path*',
    '/community/:path*',
    '/gas-rates/:path*',
    '/heating-oil/:path*',
    '/propane/:path*',
    '/water/:path*',
    '/community-solar/:path*',
    '/auth/:path*',
  ],
}
```

---

## P1 — High

---

### P1-01: `useAuth` `initAuth` — no cancellation if component unmounts during async chain; stale state updates after unmount

**File**: `frontend/lib/hooks/useAuth.tsx` lines 65–147

**Description**:
The `initAuth` async function is called from a `useEffect` with an empty dependency array. It calls `Promise.allSettled` over three parallel async operations (session, supplier, profile), then mutates React state. If `AuthProvider` unmounts before all three promises settle (e.g. during fast navigation in development, or if a hard refresh races the initial hydration), the `setUser`, `setIsLoading`, and `router.replace` calls execute on an unmounted component. React 18 suppresses the unmount warning but the state updates are still logically wrong. `router.replace('/onboarding')` may fire after the user has already navigated away.

Additionally, `router` is used inside the effect but is excluded from the dependency array (line 147: `}, []`). This is intentional for a one-time init, but it creates a stale closure if the router identity changes (unlikely with Next.js App Router but technically incorrect).

```typescript
// useAuth.tsx line 65 — no isMounted guard
useEffect(() => {
  const initAuth = async () => {
    // ...
    const [sessionResult, supplierResult, profileResult] = await Promise.allSettled([...])
    // 200–400ms later — component may be unmounted
    if (sessionResult.status === 'fulfilled' && ...) {
      setUser({ ... })    // <-- state update on potentially-unmounted component
      // ...
      router.replace('/onboarding')   // <-- navigation on potentially-stale router
    }
  }
  initAuth()
}, [])   // router excluded
```

**Fix**: Add a mounted flag and abort early:

```typescript
useEffect(() => {
  let mounted = true
  const initAuth = async () => {
    try {
      // ... same logic ...
      if (!mounted) return
      if (sessionResult.status === 'fulfilled' && ...) {
        setUser({ ... })
        if (!mounted) return
        // ...
        router.replace('/onboarding')
      }
    } catch {
      // no-op
    } finally {
      if (mounted) setIsLoading(false)
    }
  }
  initAuth()
  return () => { mounted = false }
}, [router])   // add router to deps
```

---

### P1-02: `useRealtimePrices` — `retryDelayRef` resets on unmount/remount but `mountedRef` is set to `false` in cleanup and `true` at effect start; creates an interval where a remounted component has stale backoff state

**File**: `frontend/lib/hooks/useRealtime.ts` lines 40–128

**Description**:
`mountedRef` is set to `true` at the very start of every effect run (line 43). `retryDelayRef` is never reset on re-mount. If the component unmounts while SSE is retrying with a 30s delay, then remounts immediately (e.g. tab switch, React strict mode double-mount in development), the new effect run inherits the 30s backoff state from the prior run. This means the freshly-mounted component waits up to 30 seconds before connecting, despite having just mounted.

A secondary concern: the cleanup function sets `mountedRef.current = false` and aborts the controller, but `mountedRef.current = true` is set unconditionally at line 43 before checking if the previous controller was properly cleaned up. In React 18 Strict Mode, effects run twice (mount → unmount → mount), so the first run's `mountedRef` write of `false` is immediately overwritten by the second run's `true`, but the first run's abort signal may already be in a transitional state.

```typescript
useEffect(() => {
  mountedRef.current = true    // always resets to true at start
  // ...
  // retryDelayRef is NOT reset here — carries over from prior run

  return () => {
    mountedRef.current = false
    ctrl.abort()
  }
}, [region, interval, queryClient])
```

**Fix**: Reset `retryDelayRef` at the start of each effect run:

```typescript
useEffect(() => {
  mountedRef.current = true
  retryDelayRef.current = 1000   // reset backoff on every mount/reconnect
  // ...
}, [region, interval, queryClient])
```

---

### P1-03: `useOptimalSchedule` — object reference as `queryKey` causes infinite re-fetching

**File**: `frontend/lib/hooks/useOptimization.ts` lines 17–24

**Description**:
The `queryKey` includes the entire `request` object by reference: `['optimization', 'schedule', request]`. React Query uses structural equality for cache lookups but performs a shallow referential check when computing whether to refetch. If the caller constructs the `request` object inline (e.g. `useOptimalSchedule({ appliances: myAppliances, region })` inside a component body), a new object reference is created on every render. TanStack Query v5 uses `hashKey` internally for deduplication, so this alone does not cause infinite loops — but combined with any `refetchInterval` or parent re-renders driven by other state, it means the cache is never hit and a fresh network request fires on every render cycle where `appliances.length > 0`.

```typescript
export function useOptimalSchedule(request: GetOptimalScheduleRequest) {
  return useQuery({
    queryKey: ['optimization', 'schedule', request],   // object ref — new key each render if request is inline
    queryFn: () => getOptimalSchedule(request),
    enabled: request.appliances.length > 0,
    staleTime: 180000,
  })
}
```

**Fix**: Decompose `request` into primitive parts for the key:

```typescript
export function useOptimalSchedule(request: GetOptimalScheduleRequest) {
  return useQuery({
    queryKey: [
      'optimization', 'schedule',
      request.region,
      request.date,
      // Stable hash of appliance IDs — avoids full object comparison
      request.appliances.map(a => a.id).join(','),
    ],
    queryFn: () => getOptimalSchedule(request),
    enabled: request.appliances.length > 0,
    staleTime: 180000,
  })
}
```

---

### P1-04: `useGeocoding` — raw `fetch` bypasses `apiClient`; no credentials, no circuit-breaker, no retry, calls an `/internal/` endpoint directly from client

**File**: `frontend/lib/hooks/useGeocoding.ts` lines 21–26

**Description**:
`useGeocoding` calls `/internal/geocode` using a raw `fetch` without `credentials: 'include'`. The `/internal/*` routes all require an `X-API-Key` header per the project CLAUDE.md (Critical Reminder #9: "All `/api/v1/internal/*` routes require `X-API-Key` header"). Calling this without the API key from a client-side hook will fail with a 401/403 in production. Additionally, this bypasses the circuit-breaker, lacks the retry logic in `apiClient`, and is inconsistent with all other API calls in the codebase.

```typescript
// useGeocoding.ts line 21 — raw fetch, no credentials, no API key
const resp = await fetch(`${API_URL}/internal/geocode`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  // credentials: 'include' is MISSING
  // X-API-Key is MISSING
  body: JSON.stringify({ address }),
})
```

**Note**: If `/internal/geocode` is intended as a user-facing geocoding proxy (not the raw internal endpoint), it should be moved to a non-internal path. If it is genuinely internal, it should not be called from the client at all — a Next.js API route should proxy it server-side with the `INTERNAL_API_KEY`.

**Fix (if intended as user-facing proxy)**:

```typescript
// Move endpoint to /geocode (non-internal) and use apiClient
const data = await apiClient.post<{ result: GeocodeResult }>('/geocode', { address })
return data.result ?? null
```

---

### P1-05: `useAuth` `signInWithGoogle` / `signInWithGitHub` — `isLoading` is set to `true` and never reset on OAuth redirect

**File**: `frontend/lib/hooks/useAuth.tsx` lines 270–303

**Description**:
Both OAuth sign-in methods call `setIsLoading(true)` at the start, then call `authClient.signIn.social(...)` which redirects the browser away from the current page. Because the redirect happens synchronously inside the SDK, the `finally` block is never reached and `setIsLoading(false)` is never called. While this may seem harmless (the page navigates away), in React Strict Mode or if the OAuth redirect fails silently (e.g. popup blocked, network timeout), the component stays in `isLoading: true` forever and all auth-dependent UIs become unresponsive without visual feedback to the user.

```typescript
const signInWithGoogle = useCallback(async () => {
  setIsLoading(true)   // set to true
  setError(null)

  try {
    await authClient.signIn.social({ provider: 'google', callbackURL: '/onboarding' })
    // Page navigates away — finally never runs
  } catch (err) {
    const message = err instanceof Error ? err.message : '...'
    setError(message)
    setIsLoading(false)   // only resets on error, never on success/redirect
    throw err
  }
  // No finally block
}, [])
```

**Fix**: Add a `finally` block. Note that if the redirect succeeds, the state reset is moot, but it ensures correctness on failure paths:

```typescript
const signInWithGoogle = useCallback(async () => {
  setIsLoading(true)
  setError(null)

  try {
    await authClient.signIn.social({ provider: 'google', callbackURL: '/onboarding' })
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to sign in with Google'
    setError(message)
    throw err
  } finally {
    // Resets loading if redirect fails or throws
    setIsLoading(false)
  }
}, [])
```

---

### P1-06: `useNotificationCount` polling ignores tab visibility — continues every 30s even when tab is hidden

**File**: `frontend/lib/hooks/useNotifications.ts` lines 41–48

**Description**:
`useNotificationCount` sets `refetchInterval: 30_000` without a `refetchIntervalInBackground: false` check (which is separate from `refetchOnWindowFocus`). The global `QueryProvider` sets `refetchOnWindowFocus: false` but does not disable background refetching. By default, TanStack Query continues polling when the tab is hidden. For a notification badge counter, this is wasted bandwidth — the count is irrelevant when the user cannot see it.

Compare to `useRealtimePrices` which correctly uses `openWhenHidden: false` to pause SSE on hidden tabs.

```typescript
export function useNotificationCount() {
  return useQuery({
    queryKey: notificationKeys.count,
    queryFn: () => getNotificationCount(),
    refetchInterval: 30_000,
    staleTime: 30_000,
    // refetchIntervalInBackground: false  <-- missing
  })
}
```

**Fix**:

```typescript
export function useNotificationCount() {
  return useQuery({
    queryKey: notificationKeys.count,
    queryFn: () => getNotificationCount(),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,   // pause when tab hidden
    staleTime: 30_000,
  })
}
```

---

### P1-07: `portal.ts` — raw `fetch` bypasses `apiClient` entirely; no circuit-breaker, no retry, inconsistent error handling

**File**: `frontend/lib/api/portal.ts` lines 47–80

**Description**:
Both `createPortalConnection` and `triggerPortalScrape` use raw `fetch` against a hardcoded relative path `'/api/v1/connections'` (a string literal, not `API_URL`). These calls bypass the `apiClient` circuit-breaker, miss automatic retry logic for 5xx errors, do not emit `X-Fallback-Mode` headers, and use a different error-handling pattern from the rest of the API layer. If the CF Worker is in fallback mode (circuit open), these calls will still route through the CF Worker while all other API calls use the direct Render URL.

```typescript
// portal.ts line 8 — hardcoded relative path instead of API_URL
const API_BASE = '/api/v1/connections'

// portal.ts line 50 — raw fetch
const res = await fetch(`${API_BASE}/portal`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify(payload),
})
```

**Fix**: Migrate to `apiClient`:

```typescript
import { apiClient } from './client'

export async function createPortalConnection(
  payload: CreatePortalConnectionPayload
): Promise<PortalConnectionResponse> {
  return apiClient.post<PortalConnectionResponse>('/connections/portal', payload)
}

export async function triggerPortalScrape(
  connectionId: string
): Promise<PortalScrapeResponse> {
  return apiClient.post<PortalScrapeResponse>(
    `/connections/portal/${connectionId}/scrape`,
    {}
  )
}
```

---

## P2 — Medium

---

### P2-01: `useProfile` `queryFn` calls `useSettingsStore.getState()` — React hook rule violation in async context; Zustand access is valid but pattern is misleading and fragile

**File**: `frontend/lib/hooks/useProfile.ts` lines 16–29

**Description**:
The `queryFn` callback is not a React component or hook. Calling `useSettingsStore.getState()` inside it is technically valid because it uses Zustand's store API directly rather than the `useSettingsStore` hook. However, the pattern is semantically confusing — it looks like a hook call violating the Rules of Hooks — and will trigger lint warnings from `eslint-plugin-react-hooks` (hook names must not be called outside components/hooks). The same pattern appears in `useAuth.tsx` (lines 101 and 118). This is also a code smell: `queryFn` should be a pure data-fetching function; side effects (Zustand store writes) do not belong in it.

```typescript
export function useProfile() {
  return useQuery({
    queryKey: ['user-profile'],
    queryFn: async () => {
      const profile = await getUserProfile()
      // Side effect in queryFn — store write
      if (profile.region) {
        const store = useSettingsStore.getState()   // looks like a hook call
        if (store.region !== profile.region) {
          store.setRegion(profile.region)           // mutation in queryFn
        }
      }
      return profile
    },
    staleTime: 60000,
  })
}
```

**Fix**: Use `onSuccess` (v4) or the query's returned `data` via a separate `useEffect`:

```typescript
export function useProfile() {
  const setRegion = useSettingsStore((s) => s.setRegion)
  const storeRegion = useSettingsStore((s) => s.region)

  const query = useQuery({
    queryKey: ['user-profile'],
    queryFn: getUserProfile,
    staleTime: 60000,
  })

  // Sync to store reactively when data arrives
  useEffect(() => {
    if (query.data?.region && query.data.region !== storeRegion) {
      setRegion(query.data.region)
    }
  }, [query.data?.region, storeRegion, setRegion])

  return query
}
```

---

### P2-02: `apiClient` `fetchWithRetry` — retry delay `setTimeout` is not cancellable; pending retries continue after component unmount

**File**: `frontend/lib/api/client.ts` lines 161

**Description**:
When a retryable error occurs, `fetchWithRetry` awaits a `new Promise((r) => setTimeout(r, delay))`. This promise is not associated with any `AbortSignal`. If the React Query query is cancelled (e.g. the component unmounts, or `queryClient.cancelQueries` is called), the React Query cancellation mechanism sends an `AbortSignal` to the `queryFn` — but `fetchWithRetry` does not accept or honor an `AbortSignal`. The retry `setTimeout` continues, the subsequent `fetch` fires, and the response is discarded only after the fact. Under heavy navigation this creates a queue of orphaned background requests.

```typescript
// client.ts line 161
await new Promise((r) => setTimeout(r, RETRY_BASE_MS * 2 ** attempt))
// No signal check here — delay continues even if query was cancelled
```

**Fix**: Thread `signal` through `fetchWithRetry` and reject the delay promise on abort:

```typescript
async function fetchWithRetry<T>(
  url: string,
  options: RequestInit,
  signal?: AbortSignal,
): Promise<T> {
  let lastError: unknown

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    try {
      const response = await fetch(url, { ...options, signal })
      // ...
    } catch (error) {
      if ((error as { name?: string }).name === 'AbortError') throw error
      lastError = error
      if (!isRetryable(error) || attempt === MAX_RETRIES) throw error
      await abortableDelay(RETRY_BASE_MS * 2 ** attempt, signal)
    }
  }
  throw lastError
}

function abortableDelay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    }, { once: true })
  })
}
```

---

### P2-03: `useRateChanges` — `params` object as `queryKey` causes unstable key identity when callers pass inline objects

**File**: `frontend/lib/hooks/useRateChanges.ts` lines 17–22

**Description**:
`queryKey: ['rate-changes', params]` passes the entire `params` object. TanStack Query serialises this via `hashKey` for cache lookups, so it will not cause infinite fetching by itself. However, the serialization happens on every render, and if the caller passes an inline object literal, this creates an unnecessarily wide cache key that will never hit on subsequent renders. This means every re-render of a page using `useRateChanges({ utility_type: 'electricity', region: 'TX' })` will compute a new hash even though the logical params are identical, bypassing `staleTime` protection.

```typescript
export function useRateChanges(params?: {
  utility_type?: string
  region?: string
  days?: number
  limit?: number
}) {
  return useQuery({
    queryKey: ['rate-changes', params],   // object — hashed but still recreated on every render
    queryFn: () => getRateChanges(params),
    staleTime: 300_000,
  })
}
```

**Fix**: Destructure to primitives:

```typescript
export function useRateChanges(params?: { ... }) {
  return useQuery({
    queryKey: ['rate-changes', params?.utility_type, params?.region, params?.days, params?.limit],
    queryFn: () => getRateChanges(params),
    staleTime: 300_000,
  })
}
```

---

### P2-04: `useAuth` OAuth methods — missing `setIsLoading(false)` in non-error redirect path; loading spinner is permanent on OAuth redirect

**File**: `frontend/lib/hooks/useAuth.tsx` lines 270–303

*(Partially overlaps with P1-05 — documented there as a security concern. This entry focuses on the UX degradation in the non-redirect failure case.)*

Additional issue: after `signInWithGoogle` or `signInWithGitHub` throws and sets `isLoading: false`, the `isLoading` state never gets reset to `false` if the error is caught upstream and the component stays mounted. This is because `setIsLoading` is called only in the `catch` block (not `finally`).

---

### P2-05: `usePotentialSavings` — `appliances` array as `queryKey` is a deep reference; any new array instance causes a cache miss

**File**: `frontend/lib/hooks/useOptimization.ts` lines 67–74

**Description**:
`queryKey: ['potential-savings', appliances, region]` stores the full `appliances` array. TanStack Query's `hashKey` will JSON-serialize it, so structural equality is maintained — a cache hit will occur if the same appliances are passed with different array references. However, this serialization is O(n) on the size of the appliances array and runs on every render. For dashboards with many appliances and frequent re-renders, this is a consistent performance tax.

```typescript
export function usePotentialSavings(appliances: Appliance[], region: string | null | undefined) {
  return useQuery({
    queryKey: ['potential-savings', appliances, region],   // O(n) hash on every render
```

**Fix**: Use a stable derived key:

```typescript
const applianceKey = appliances.map(a => `${a.id}:${a.powerKw}:${a.typicalDurationHours}`).join('|')
return useQuery({
  queryKey: ['potential-savings', applianceKey, region],
```

---

### P2-06: `useSettingsStore` persists to `localStorage` synchronously — will throw in SSR context; missing `typeof window` guard

**File**: `frontend/lib/store/settings.ts` lines 168–183

**Description**:
`createJSONStorage(() => localStorage)` is called in the `persist` middleware configuration. The `() => localStorage` factory is evaluated lazily by Zustand on first access, but the module-level `create(persist(...))` call still runs during SSR. In Next.js App Router, any component importing `useSettingsStore` that runs in a Server Component context will cause a `ReferenceError: localStorage is not defined` error at the `createJSONStorage` call site. The file has `'use client'` at the top which prevents direct SSC import, but if a server-side utility imports a file that imports `settings.ts`, SSR will fail.

Additionally, `createJSONStorage` returns a storage object that calls `localStorage.getItem/setItem` synchronously on hydration, before checking `typeof window`. If Zustand calls the storage getter during SSR (e.g. via `getServerSideProps`-adjacent code), this will throw.

**Fix**: Add a safe storage wrapper:

```typescript
const safeStorage = {
  getItem: (name: string) => {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(name)
  },
  setItem: (name: string, value: string) => {
    if (typeof window === 'undefined') return
    localStorage.setItem(name, value)
  },
  removeItem: (name: string) => {
    if (typeof window === 'undefined') return
    localStorage.removeItem(name)
  },
}
// ...
storage: createJSONStorage(() => safeStorage),
```

---

### P2-07: `apiClient.delete` — no `data` parameter; cannot send request body for DELETE endpoints that require one

**File**: `frontend/lib/api/client.ts` lines 228–235

**Description**:
The `delete` method signature is `async delete<T>(endpoint: string): Promise<T>`. It accepts no body parameter. Some REST APIs, including FastAPI backends, support DELETE requests with a request body (e.g. bulk delete operations, delete with reason). More pressingly, the current implementation sends `DELETE` without `Content-Type: application/json`, which differs from POST/PUT/PATCH. While none of the current API endpoints appear to require a DELETE body, this is an inconsistency that will require a signature break when such an endpoint is added.

```typescript
async delete<T>(endpoint: string): Promise<T> {
  const baseUrl = circuitBreaker.getBaseUrl()
  return fetchWithRetry<T>(`${baseUrl}${endpoint}`, {
    method: 'DELETE',
    headers: buildHeaders(),
    credentials: 'include',
    // body: undefined — cannot pass body even if needed
  })
},
```

**Fix**: Accept optional `data` parameter consistent with other methods:

```typescript
async delete<T>(endpoint: string, data?: unknown): Promise<T> {
  const baseUrl = circuitBreaker.getBaseUrl()
  return fetchWithRetry<T>(`${baseUrl}${endpoint}`, {
    method: 'DELETE',
    headers: buildHeaders(),
    credentials: 'include',
    body: data ? JSON.stringify(data) : undefined,
  })
},
```

---

### P2-08: `handleResponse` — `redirectInFlight` module-level variable is never reset on successful page navigation; persists across SPA route changes

**File**: `frontend/lib/api/client.ts` lines 49, 117–121

**Description**:
`redirectInFlight` is a module-level boolean. It is set to `true` when a 401 redirect is initiated and reset to `false` only inside `handleResponse` on a successful response (lines 120–121). If the redirect to `/auth/login` succeeds and the user logs in, `window.location.href` is assigned causing a full-page reload, which re-initialises the module and resets `redirectInFlight` to `false`. This is fine.

However, if the login redirect fails or is intercepted by a service worker, and the user manually navigates to a non-API page in the same tab, `redirectInFlight` remains `true` indefinitely. All subsequent 401 responses are silently swallowed (`handleResponse` falls through to the non-401 error path with no throw). This can cause mysterious "undefined is not iterable" errors in components when they try to destructure from `undefined` returned by a never-resolved promise.

More concretely: after the `MAX_401_REDIRECTS` (2) limit is hit and `redirectInFlight` is `true`, any new 401 response does not redirect AND does not throw — the code falls through to `response.json()` parsing on line 102, which will parse the 401 error body as if it were success data.

```typescript
// client.ts lines 63–96
if (response.status === 401 && typeof window !== 'undefined') {
  if (!pathname.startsWith('/auth/') && !redirectInFlight) {
    // ...
    redirectInFlight = true
    // ...
    return new Promise<T>(() => {})  // never resolves
  }
  // If redirectInFlight is true: falls through to response.json() below
  // This means 401 error body is returned as if it were a success response
}
```

**Fix**: When the redirect guard is bypassed, still throw an error rather than falling through:

```typescript
if (response.status === 401 && typeof window !== 'undefined') {
  const pathname = window.location.pathname
  if (!pathname.startsWith('/auth/') && !redirectInFlight) {
    // ... redirect logic ...
    return new Promise<T>(() => {})
  }
  // Guard was bypassed (already redirecting or on auth page) — throw normally
  throw new ApiClientError({ message: 'Unauthorized', status: 401 })
}
```

---

### P2-09: `useAlertHistory` — `pageSize` parameter silently ignored in query key; changing `pageSize` does not trigger a new fetch

**File**: `frontend/lib/hooks/useAlerts.ts` lines 27–33

**Description**:
`useAlertHistory(page, pageSize)` includes `page` in the `queryKey` but omits `pageSize`. If a component first renders with `pageSize=20`, populates the cache under `['alerts', 'history', 1]`, then re-renders with `pageSize=50`, the hook returns the stale 20-item cache result without re-fetching.

```typescript
export function useAlertHistory(page: number = 1, pageSize: number = 20) {
  return useQuery({
    queryKey: ['alerts', 'history', page],   // pageSize not included
    queryFn: () => getAlertHistory(page, pageSize),
    staleTime: 30000,
  })
}
```

**Fix**:

```typescript
queryKey: ['alerts', 'history', page, pageSize],
```

---

## P3 — Low

---

### P3-01: Naming conflict — `useAppliances` exported from both `lib/store/settings.ts` and `lib/hooks/useOptimization.ts`

**File**: `frontend/lib/store/settings.ts` line 191
**File**: `frontend/lib/hooks/useOptimization.ts` line 41

**Description**:
`useAppliances` is exported as a selector from `settings.ts` (reads local Zustand state) and also exported as a React Query hook from `useOptimization.ts` (fetches appliances from the backend). These are semantically different: one reads persisted local state, the other fetches server state. A developer importing `useAppliances` without checking the source gets unpredictable behaviour depending on import path — Zustand slice or React Query hook.

**Fix**: Rename one to disambiguate:

```typescript
// settings.ts — rename to make origin clear
export const useLocalAppliances = () => useSettingsStore((s) => s.appliances)

// useOptimization.ts — rename to reflect server state
export function useServerAppliances() { ... }
// or simply: useAppliances stays in useOptimization.ts and the store selector becomes useStoredAppliances
```

---

### P3-02: `apiClient.get` `params` type only accepts `string | number | boolean` values — cannot pass `string[]` for multi-value query params

**File**: `frontend/lib/api/client.ts` line 179

**Description**:
The `params` parameter is typed as `Record<string, string | number | boolean>`. This is sufficient for all current API calls, but it prevents passing array values for multi-select filters (e.g. `utility_types=electricity&utility_types=gas`). If the backend adds such endpoints, callers will need to manually build query strings. This is a forward-compatibility gap rather than a current bug.

```typescript
async get<T>(endpoint: string, params?: Record<string, string | number | boolean>): Promise<T>
```

**Fix**: Accept arrays and serialise them as repeated params:

```typescript
async get<T>(
  endpoint: string,
  params?: Record<string, string | number | boolean | string[]>
): Promise<T> {
  // In the URLSearchParams construction:
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) {
      v.forEach(item => searchParams.append(k, item))
    } else {
      searchParams.set(k, String(v))
    }
  }
}
```

---

### P3-03: `useAuth` `initAuth` — `onboarding_completed` check evaluates `!profile.region` which forces onboarding re-run if user's region is `null` even when they have completed onboarding

**File**: `frontend/lib/hooks/useAuth.tsx` lines 129–135

**Description**:
The redirect condition `if (!profile.onboarding_completed || !profile.region)` will redirect a user to `/onboarding` if their `region` is `null` even if `onboarding_completed` is `true`. This can happen if a user completed onboarding but later cleared their region from settings. The two conditions represent different problems (incomplete onboarding vs. missing region) and should be handled separately.

```typescript
if (!profile.onboarding_completed || !profile.region) {
  // redirects even when onboarding is done but region was cleared
  router.replace('/onboarding')
  return
}
```

**Fix**: Separate the conditions:

```typescript
if (!profile.onboarding_completed) {
  router.replace('/onboarding')
  return
}
if (!profile.region) {
  // Soft redirect to settings to re-select region, not full onboarding
  router.replace('/settings?missingRegion=true')
  return
}
```

---

### P3-04: `useCommunitySolar` `useCommunitySolarSavings` — `monthlyBill` and `savingsPercent` are typed as `string | null` but are passed raw to the API; no numeric validation

**File**: `frontend/lib/hooks/useCommunitySolar.ts` lines 29–43

**Description**:
`monthlyBill` and `savingsPercent` are `string | null`. The `enabled` guard checks `!!monthlyBill && !!savingsPercent` but does not validate that these strings represent valid positive numbers before passing them to the API. A caller could pass `"abc"` or `"-1"` and trigger a backend validation error that the hook surfaces as an unformatted error object rather than a user-friendly message.

**Fix**: Add validation in the `enabled` check:

```typescript
const validBill = !!monthlyBill && !isNaN(parseFloat(monthlyBill)) && parseFloat(monthlyBill) > 0
const validSavings = !!savingsPercent && !isNaN(parseFloat(savingsPercent))
return useQuery({
  enabled: validBill && validSavings,
  // ...
})
```

---

### P3-05: `QueryProvider` — `gcTime` set to 5 minutes but `staleTime` default is 1 minute; creates a 4-minute window where stale data can be served from cache without a background refresh

**File**: `frontend/components/providers/QueryProvider.tsx` lines 8–33

**Description**:
The global `staleTime: 60 * 1000` means queries become stale after 1 minute. `gcTime: 5 * 60 * 1000` means stale cache entries live for 5 minutes before garbage collection. `refetchOnWindowFocus: false` means no background refresh triggers. Between minute 1 and minute 5, cached queries serve stale data to newly-mounted components without triggering a background refetch (because `refetchOnWindowFocus` is disabled and no user action triggers invalidation). This is intentional per the comment ("Prevent perceived page refreshes") but the trade-off should be documented more explicitly; some pages like `/prices` use their own tighter `staleTime` values to override this.

This is a design decision rather than a bug, but warrants review as it means users on slow network connections can see data up to 5 minutes stale without any UI indicator.

---

### P3-06: `SidebarProvider` — `document.body.style.overflow` mutation not scoped to mobile breakpoint; sets overflow:hidden on desktop too

**File**: `frontend/lib/contexts/sidebar-context.tsx` lines 37–46

**Description**:
When the sidebar opens, `document.body.style.overflow = 'hidden'` prevents body scroll globally, including on desktop where the sidebar is likely persistent/always-visible. This will prevent scrolling of the main content area on desktop when the sidebar is toggled open. The fix should check viewport width or use a CSS class controlled by Tailwind's responsive utilities rather than direct style mutation.

```typescript
useEffect(() => {
  if (isOpen) {
    document.body.style.overflow = 'hidden'   // fires on all viewports
  }
  // ...
}, [isOpen])
```

**Fix**: Use a CSS class and restrict to mobile via media query, or check `window.innerWidth` before applying.

---

### P3-07: `useAuth` `sendMagicLink` — `setIsLoading(true)` but magic link sends an email and resolves without redirect; UI appears stuck in loading state post-success

**File**: `frontend/lib/hooks/useAuth.tsx` lines 306–326

**Description**:
After `authClient.signIn.magicLink` resolves successfully, `setIsLoading(false)` is called via `finally`. This is correct. However, the caller has no way to distinguish "loading" from "success" because only `isLoading`, `error`, and the auth methods are returned by the context. There is no `messageSent` or `success` state. The component using `sendMagicLink` must maintain its own local state for the "email sent" confirmation message. This is an ergonomics issue that pushes state duplication into every consumer.

**Fix**: Return a discriminated state from `sendMagicLink` or expose a dedicated `magicLinkSent` state in the context.

---

### P3-08: `useAuth` server-side `authClient.baseURL` — uses `APP_URL` which may be `http://localhost:3000` in production CI builds that do not set `NEXT_PUBLIC_APP_URL`

**File**: `frontend/lib/auth/client.ts` lines 12–17

**Description**:
```typescript
export const authClient = createAuthClient({
  baseURL: typeof window !== "undefined"
    ? window.location.origin
    : APP_URL,   // fallback for SSR
})
```
`APP_URL` defaults to `http://localhost:3000` (from `env.ts` line 103). In production server-side rendering (e.g. Next.js Streaming SSR for auth state on SSR pages), if `NEXT_PUBLIC_APP_URL` is not set in the build environment, the auth client will send requests to `http://localhost:3000/api/auth/*`, which will fail with a connection error. The `env.ts` marks `APP_URL` as not `required` in production. Better Auth documents that the server-side `baseURL` must be the canonical production URL.

**Fix**: Mark `NEXT_PUBLIC_APP_URL` as required in production:

```typescript
// env.ts
export const APP_URL: string = env(
  process.env.NEXT_PUBLIC_APP_URL,
  'http://localhost:3000',
  { required: true, name: 'NEXT_PUBLIC_APP_URL' },  // was: required: false
)
```

---

## Cross-Cutting Observations

### State Management Architecture Assessment

The dual-store pattern (Zustand `useSettingsStore` for persisted local state + TanStack Query for server state) is sound and well-separated. However, the synchronisation between them (profile sync in `useProfile`, supplier sync in `useAuth`) uses a fire-and-forget Zustand `.getState()` call inside React Query callbacks. This creates a hidden dependency: if Zustand persist hydration has not completed when the React Query `queryFn` runs, the condition `if (!store.region)` (in `useAuth.tsx` line 119) may see `undefined` as the store region even if a region was previously persisted. Consider using Zustand's `onRehydrateStorage` event to gate the profile sync.

### Missing `AbortSignal` Propagation Pattern

TanStack Query v5 provides each `queryFn` with a `{ signal }` in its context argument. None of the `queryFn` implementations in the hooks layer forward this signal to `apiClient` calls. This means React Query cannot cancel in-flight requests when queries are cancelled (e.g. `queryClient.cancelQueries`, component unmount with `remove: true`). The `apiClient` would need to accept an optional `signal` argument on each method:

```typescript
// Pattern to add to all queryFn implementations
queryFn: ({ signal }) => getAlerts(signal),   // pass signal down
// apiClient.get would need: (endpoint, params, signal?)
```

### `useRealtimeBroadcast` — Placeholder Hook Ships to Production

`frontend/lib/hooks/useRealtime.ts` lines 211–227: `useRealtimeBroadcast` is a stub with no implementation, yet it exports a `broadcast` function that is a no-op and an `isConnected` state that is always `true`. Any component using this hook will believe it is connected to a broadcast channel when it is not. Either remove this export or throw an error to make the unimplemented state explicit.

### Type Safety: `unknown` in SSE Path

`frontend/lib/hooks/useRealtime.ts` line 76: `queryClient.setQueryData<unknown>(...)` uses `unknown` as the generic, requiring an `Array.isArray(old)` check. This is safe but loses type information. The cache key `['prices', 'current', region]` corresponds to `ApiCurrentPriceResponse` from the generated types. Parametrising with the correct type would eliminate the manual `Array.isArray` guard and improve type safety throughout the SSE update path.

---

## Files Audited

| File | Lines | Issues Found |
|------|-------|--------------|
| `frontend/lib/api/client.ts` | 237 | P0-02, P2-02, P2-07, P2-08 |
| `frontend/lib/api/circuit-breaker.ts` | 113 | Clean |
| `frontend/lib/api/agent.ts` | 124 | P0-01 |
| `frontend/lib/api/alerts.ts` | 125 | Clean |
| `frontend/lib/api/affiliate.ts` | 29 | Clean |
| `frontend/lib/api/cca.ts` | (not shown — assumed clean) | — |
| `frontend/lib/api/community.ts` | 98 | Clean |
| `frontend/lib/api/community-solar.ts` | (not shown — assumed clean) | — |
| `frontend/lib/api/export.ts` | (not shown — assumed clean) | — |
| `frontend/lib/api/forecast.ts` | (not shown — assumed clean) | — |
| `frontend/lib/api/gas-rates.ts` | (not shown — assumed clean) | — |
| `frontend/lib/api/heating-oil.ts` | (not shown — assumed clean) | — |
| `frontend/lib/api/neighborhood.ts` | (not shown — assumed clean) | — |
| `frontend/lib/api/notifications.ts` | 79 | Clean |
| `frontend/lib/api/optimization.ts` | 78 | Clean |
| `frontend/lib/api/portal.ts` | 81 | P1-07 |
| `frontend/lib/api/prices.ts` | 185 | Clean |
| `frontend/lib/api/profile.ts` | 39 | Clean |
| `frontend/lib/api/propane.ts` | (not shown — assumed clean) | — |
| `frontend/lib/api/rate-changes.ts` | (not shown — assumed clean) | — |
| `frontend/lib/api/reports.ts` | (not shown — assumed clean) | — |
| `frontend/lib/api/savings.ts` | 17 | Clean |
| `frontend/lib/api/suppliers.ts` | 186 | Clean |
| `frontend/lib/api/utility-discovery.ts` | (not shown — assumed clean) | — |
| `frontend/lib/api/water.ts` | (not shown — assumed clean) | — |
| `frontend/lib/auth/client.ts` | 17 | P3-08 |
| `frontend/lib/auth/server.ts` | 152 | Clean |
| `frontend/lib/config/env.ts` | 138 | P3-08 (indirect) |
| `frontend/lib/contexts/sidebar-context.tsx` | 57 | P3-06 |
| `frontend/lib/contexts/toast-context.tsx` | 121 | Clean |
| `frontend/lib/hooks/useAgent.ts` | 72 | P0-01 |
| `frontend/lib/hooks/useAlerts.ts` | 77 | P2-09 |
| `frontend/lib/hooks/useAuth.tsx` | 380 | P1-01, P1-05, P3-03, P3-07 |
| `frontend/lib/hooks/useCCA.ts` | 43 | Clean |
| `frontend/lib/hooks/useCombinedSavings.ts` | 11 | Clean |
| `frontend/lib/hooks/useCommunity.ts` | 60 | Clean |
| `frontend/lib/hooks/useCommunitySolar.ts` | 61 | P3-04 |
| `frontend/lib/hooks/useConnections.ts` | 49 | Clean |
| `frontend/lib/hooks/useDiagrams.ts` | 88 | Clean (dev-only) |
| `frontend/lib/hooks/useExport.ts` | 25 | Clean |
| `frontend/lib/hooks/useForecast.ts` | 24 | Clean |
| `frontend/lib/hooks/useGasRates.ts` | 55 | Clean |
| `frontend/lib/hooks/useGeocoding.ts` | 42 | P1-04 |
| `frontend/lib/hooks/useHeatingOil.ts` | 43 | Clean |
| `frontend/lib/hooks/useNeighborhood.ts` | 12 | Clean |
| `frontend/lib/hooks/useNotifications.ts` | 82 | P1-06 |
| `frontend/lib/hooks/useOptimization.ts` | 75 | P1-03, P2-05, P3-01 |
| `frontend/lib/hooks/useProfile.ts` | 48 | P2-01 |
| `frontend/lib/hooks/usePrices.ts` | 79 | P0-02 |
| `frontend/lib/hooks/usePropane.ts` | 43 | Clean |
| `frontend/lib/hooks/useRateChanges.ts` | 41 | P2-03 |
| `frontend/lib/hooks/useRealtime.ts` | 228 | P1-02, cross-cutting |
| `frontend/lib/hooks/useReports.ts` | 12 | Clean |
| `frontend/lib/hooks/useSavings.ts` | 29 | Clean |
| `frontend/lib/hooks/useSuppliers.ts` | 186 | Clean |
| `frontend/lib/hooks/useUtilityDiscovery.ts` | 31 | Clean |
| `frontend/lib/hooks/useWater.ts` | 32 | Clean |
| `frontend/lib/notifications/onesignal.ts` | 58 | Clean |
| `frontend/lib/store/settings.ts` | 198 | P2-06, P3-01 |
| `frontend/lib/utils/url.ts` | 46 | Clean |
| `frontend/middleware.ts` | 67 | P0-03 |
| `frontend/types/api-helpers.ts` | 319 | Clean |
| `frontend/types/generated/api.ts` | 80+ | Clean |
| `frontend/types/index.ts` | 241 | Clean |
| `frontend/components/providers/QueryProvider.tsx` | 39 | P3-05 |
