# Frontend lib/ & types/ Audit

**Date**: 2026-03-16
**Scope**: `/frontend/lib/` (all `.ts`/`.tsx`), `/frontend/types/` (all `.ts`), `/frontend/app/api/` (all route files)
**Auditor**: TypeScript-pro agent

---

## Summary

| Severity | Count |
|----------|-------|
| P0 (Critical — data loss / security) | 3 |
| P1 (High — incorrect behavior / security gap) | 8 |
| P2 (Medium — reliability / type safety) | 14 |
| P3 (Low — DX / consistency) | 9 |
| **Total** | **34** |

---

## P0 — Critical

---

### P0-01: queryAgent SSE stream reader never released on abort / component unmount

**File**: `/frontend/lib/api/agent.ts`
**Lines**: 54–98

The `queryAgent` async generator opens a `ReadableStreamDefaultReader` via `response.body?.getReader()` but never calls `reader.cancel()` or `reader.releaseLock()`. If the calling component unmounts mid-stream (user navigates away), the generator is garbage-collected but the underlying HTTP body stream and its lock are not explicitly released. In Chromium-based runtimes this causes a `ReadableStream is locked` error on the next request for the same body, and the byte counter in the server-side SSE endpoint never decrements, keeping the connection open until the 30-second request timeout fires.

Additionally `useAgentQuery` in `frontend/lib/hooks/useAgent.ts` (line 18) creates an `AbortController` reference (`abortRef`) but the `AbortController` is never passed to the `queryAgent` generator, so `cancel()` (line 47) only sets `isStreaming = false` — it does not abort the underlying fetch.

**Fix**:

```typescript
// agent.ts — pass AbortSignal and release reader
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
    signal,
  })
  // ...existing error handling...
  const reader = response.body?.getReader()
  if (!reader) { yield { role: 'error', content: 'Streaming not supported' }; return }
  try {
    // ...existing read loop...
  } finally {
    reader.cancel().catch(() => {/* best effort */})
  }
}

// useAgent.ts — wire signal through
const sendQuery = useCallback(async (prompt: string) => {
  const ctrl = new AbortController()
  abortRef.current = ctrl
  // ...
  for await (const msg of queryAgent(prompt, undefined, ctrl.signal)) {
    // ...
  }
}, [])

const cancel = useCallback(() => {
  abortRef.current?.abort()
  setIsStreaming(false)
}, [])
```

---

### P0-02: checkout API route forwards raw `Authorization` header from client — SSRF / header injection risk

**File**: `/frontend/app/api/checkout/route.ts`
**Lines**: 8–14

The route reads the `Authorization` header verbatim from the incoming `NextRequest` and forwards it directly to the backend:

```typescript
const authHeader = request.headers.get('authorization')
// ...
Authorization: authHeader,
```

Any value the browser sends is reflected without validation. A crafted header value (e.g., one containing newline characters) could inject additional headers into the backend request (HTTP header injection). The route also constructs `success_url` / `cancel_url` from `request.nextUrl.origin` without confirming the origin matches the app's expected domain, which combined with host-header spoofing could redirect users to attacker-controlled pages after checkout.

Additionally, the route accepts an unauthenticated `BACKEND_URL` fallback of `http://localhost:8000` — if `BACKEND_URL` is absent in production the route silently proxies to localhost, potentially bypassing network policy.

**Fix**:

```typescript
// Validate header format and reject anything containing CR/LF
const authHeader = request.headers.get('authorization')
if (authHeader && !/^Bearer [A-Za-z0-9\-._~+/]+=*$/.test(authHeader)) {
  return NextResponse.json({ error: 'Invalid authorization header' }, { status: 400 })
}

// Verify origin matches the configured app URL, not just whatever the host header says
const allowedOrigins = new Set([process.env.NEXT_PUBLIC_APP_URL, 'https://rateshift.app'])
if (!allowedOrigins.has(request.nextUrl.origin)) {
  return NextResponse.json({ error: 'Invalid origin' }, { status: 400 })
}
```

---

### P0-03: `redirectInFlight` module-level flag is process-scoped, not per-user — can permanently suppress 401 redirects for all concurrent users in SSR context

**File**: `/frontend/lib/api/client.ts`
**Lines**: 49, 67–95

`redirectInFlight` is declared as a module-level `let` at line 49. In Next.js server-side rendering (including Server Components and API routes that import this module), module state is shared across all requests within the same Node.js process. If one user's request sets `redirectInFlight = true`, subsequent 401 responses for *all* users processed by the same module instance will silently skip the redirect, leaking data or showing a blank authenticated page to unauthenticated users.

The comment says "client-side only" and checks `typeof window !== 'undefined'`, but Server Components can import client modules during the compilation of hybrid pages, and the module is evaluated once per process.

The guard is sound for pure browser usage, but the module-level mutable state is an architectural risk that should be explicitly documented with a server-side guard or converted to a closure per-request pattern.

**Fix**:

Add an explicit SSR bailout at the top of `handleResponse` so the flag is never touched in server context:

```typescript
async function handleResponse<T>(response: Response): Promise<T> {
  if (typeof window === 'undefined') {
    // SSR path — never redirect, never touch module-level state
    if (!response.ok) {
      // ... parse error and throw ...
    }
    return response.json()
  }
  // ...existing browser logic...
}
```

---

## P1 — High

---

### P1-01: `portal.ts` uses raw `fetch` with hardcoded `/api/v1` base — bypasses circuit breaker, retry logic, and auth 401 handler

**File**: `/frontend/lib/api/portal.ts`
**Lines**: 8, 50–80

`createPortalConnection` and `triggerPortalScrape` use a hardcoded `const API_BASE = '/api/v1/connections'` and call the native `fetch` API directly, bypassing `apiClient`. This means:

1. No exponential-backoff retry on 5xx/network errors
2. No circuit breaker fallback to Render when the CF Worker is down
3. No automatic 401 redirect (users see a raw thrown `Error` instead of being redirected to `/auth/login`)
4. No `X-Fallback-Mode` header when in circuit-breaker fallback mode
5. The hardcoded `/api/v1` prefix will break if `NEXT_PUBLIC_API_URL` is set to a full URL (e.g., `https://api.rateshift.app/api/v1`)

**Fix**:

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
  return apiClient.post<PortalScrapeResponse>(`/connections/portal/${connectionId}/scrape`, {})
}
```

---

### P1-02: `useGeocoding` hook calls `/internal/geocode` without session credentials — exposes internal endpoint to unauthenticated requests

**File**: `/frontend/lib/hooks/useGeocoding.ts`
**Lines**: 21–27

The geocode request is made with a bare `fetch` that omits `credentials: 'include'` and does not include the `X-API-Key` header. Internal endpoints require `X-API-Key` per project conventions (CLAUDE.md "Internal endpoints" reminder). A request missing both will receive a 401 or 403 depending on how the internal router is configured.

More critically, if the backend's internal endpoint is misconfigured to not require auth, the geocoding endpoint is being called from the browser with no protection, potentially exposing user address data to CSRF.

**Fix**:

```typescript
const resp = await fetch(`${API_URL}/internal/geocode`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    // Internal endpoints require API key; use a dedicated client-safe key or
    // route geocoding through a public-facing proxy endpoint instead
  },
  credentials: 'include',
  body: JSON.stringify({ address }),
  signal: AbortSignal.timeout(10_000), // prevent hanging
})
```

If `/internal/geocode` is truly internal-only, this call should be moved to a Next.js API route that adds the `X-API-Key` server-side from `process.env.INTERNAL_API_KEY`.

---

### P1-03: `useAuth` initAuth calls `router.replace('/onboarding')` then `return` inside an async `useEffect` callback — `router` is not stable across renders and is not in the dependency array

**File**: `/frontend/lib/hooks/useAuth.tsx`
**Lines**: 65–147

`router` is obtained from `useRouter()` at line 60 and used inside `initAuth` at line 133. The `useEffect` dependency array at line 147 is `[]` (empty), so `router` is captured via closure at mount time. In Next.js App Router, `useRouter()` can return a new object on each render; the stale captured reference might point to an unmounted router instance after a fast navigation away from the page on which `AuthProvider` first mounted.

Additionally, `getSettingsStore.getState()` is called at lines 101 and 118 from inside the `useEffect` callback — this correctly reads from the Zustand singleton, but calling `useSettingsStore.getState()` inside an effect (not at the top of the hook render) violates the rules of hooks. It works at runtime because `useSettingsStore.getState()` is a static store accessor (not a React hook call), but linters will flag this and it creates confusion.

**Fix**:

Capture router in a ref so the effect always uses the current value:

```typescript
const routerRef = useRef(router)
useEffect(() => { routerRef.current = router }, [router])

// Inside initAuth:
routerRef.current.replace('/onboarding')
```

The `useSettingsStore.getState()` calls are fine functionally; add a comment clarifying they are store accessors, not hook calls, to prevent future linter suppression confusion.

---

### P1-04: `fetchWithRetry` records circuit breaker failure only on the final attempt, but `recordSuccess` is called on *every* successful response — a single success immediately resets a partially-open circuit that had 2 out of 3 required failures

**File**: `/frontend/lib/api/client.ts`
**Lines**: 134–166
**File**: `/frontend/lib/api/circuit-breaker.ts`
**Lines**: 54–71

In `CircuitBreaker.recordFailure()`, the counter increments each call, so it takes `failureThreshold` (3) consecutive recorded failures to trip the circuit. But in `fetchWithRetry`, the failure is only recorded on the *last* attempt (`attempt === MAX_RETRIES`). This means each invocation of `fetchWithRetry` that fails counts as exactly one failure regardless of how many retries were attempted — correct.

However `recordSuccess()` unconditionally resets `_failureCount = 0` AND sets `_state = CircuitState.CLOSED`. This means:

- 2 failed requests (failure count = 2, circuit still CLOSED)
- 1 successful request → `_failureCount` resets to 0

The circuit never opens unless all 3 failures happen with no successes in between. On flaky infrastructure where 2 out of 3 requests succeed, the circuit will never open even though gateway health is degraded. This defeats the purpose of the circuit breaker for partial-failure scenarios.

**Fix**:

Only reset the failure count in `HALF_OPEN → CLOSED` transition; in `CLOSED` state, decay the count rather than resetting to zero:

```typescript
recordSuccess(): void {
  if (this._state === CircuitState.HALF_OPEN) {
    // Probe succeeded — fully close
    this._failureCount = 0
    this._state = CircuitState.CLOSED
  } else {
    // Gradual recovery: decrement rather than hard reset
    this._failureCount = Math.max(0, this._failureCount - 1)
  }
}
```

---

### P1-05: `handleResponse` reads `response.json()` to parse error body but does not check `Content-Type` — binary or HTML error responses throw an uncaught `SyntaxError` that is swallowed silently

**File**: `/frontend/lib/api/client.ts`
**Lines**: 101–107

The `catch` block at line 105 catches JSON parse failures and falls back to `response.statusText`. This is intentional. However the `details` object is set to the raw `errorData` (line 103) regardless of its shape, meaning `details` could be a string (`"Not Found"`) rather than `Record<string, unknown>` for non-standard backends.

More importantly, when the CF Worker gateway returns a Cloudflare HTML error page (e.g., `Error 1027: Zone is offline`), the JSON parse throws and `errorMessage` falls back to `response.statusText`. `CircuitBreaker.isGatewayError(1027)` will never be called because `error.status` is `1027` only when `ApiClientError` is thrown with that status, but Cloudflare returns it as the HTTP status code — and HTTP status `1027` is not a valid HTTP status, so fetch will typically surface it as a network error (TypeError), not a 1027 status. The `GATEWAY_ERROR_CODES` set including `1027` is therefore unreachable.

**Fix**:

Remove `1027` from `GATEWAY_ERROR_CODES` (it is not a valid HTTP status), or map CF's non-standard error indicators from response headers/body patterns. Also guard `details` assignment:

```typescript
try {
  const errorData = await response.json()
  errorMessage = (typeof errorData.detail === 'string' ? errorData.detail : null)
    ?? (typeof errorData.message === 'string' ? errorData.message : null)
    ?? errorMessage
  if (typeof errorData === 'object' && errorData !== null) {
    details = errorData as Record<string, unknown>
  }
} catch {
  errorMessage = response.statusText || errorMessage
}
```

---

### P1-06: `isSafeRedirect` calls `new URL(url, window.location.origin)` — always safe for same-origin relative paths, but `isSafeOAuthRedirect` calls `new URL(url)` without a base — relative paths throw and return `false`

**File**: `/frontend/lib/utils/url.ts`
**Lines**: 17–24, 33–46

`isSafeOAuthRedirect` at line 38 calls `new URL(url)` without a base. For a relative URL like `/dashboard`, this throws `TypeError: Failed to construct 'URL'`, which is caught and returns `false`. Any OAuth callback that passes a relative URL will fail the safety check and result in a rejected redirect, breaking OAuth flows in environments where `callbackURL` is constructed as a path.

**Fix**:

```typescript
export function isSafeOAuthRedirect(
  url: string,
  allowedExternalOrigins: string[]
): boolean {
  try {
    const parsed = new URL(url, window.location.origin) // add base for relative URLs
    if (parsed.origin === window.location.origin) return true
    return parsed.protocol === 'https:' && allowedExternalOrigins.includes(parsed.origin)
  } catch {
    return false
  }
}
```

---

### P1-07: `useAuth` `initAuth` calls `getUserSupplier()` and `getUserProfile()` with `Promise.allSettled` on public pages after the explicit `isPublicPage` check, but `isPublicPage` does NOT include `/community`, `/rates/*`, `/water`, `/propane`, `/heating-oil`, `/gas`, or any SEO rate pages — these pages will fire unnecessary authenticated API calls on every load even for anonymous visitors

**File**: `/frontend/lib/hooks/useAuth.tsx`
**Lines**: 70–76

```typescript
const isPublicPage = isAuthPage || pathname === '/' || pathname === '/pricing'
  || pathname === '/privacy' || pathname === '/terms'
```

The project has ISR-generated SEO pages at `/rates/[state]/[utilityType]` (153 pages), `/community`, `/water`, `/propane`, etc. These are accessible without authentication. When an anonymous user visits them, `initAuth` fires `getUserSupplier()` and `getUserProfile()` which both call `apiClient.get()`. These will receive 401 responses, triggering the 401-redirect guard in `handleResponse`. The guard suppresses the redirect only for paths starting with `/auth/` — all other paths including `/rates/*` will potentially be redirected to login.

The guard in `handleResponse` re-checks `pathname` but the auth `initAuth` already has the pathname. The fix should broaden the `isPublicPage` check:

**Fix**:

```typescript
const PUBLIC_PATH_PREFIXES = ['/auth/', '/rates/', '/community', '/water',
  '/propane', '/heating-oil', '/gas', '/pricing', '/privacy', '/terms']

const isPublicPage = pathname === '/'
  || PUBLIC_PATH_PREFIXES.some((p) => pathname.startsWith(p))
```

---

### P1-08: `useOptimalSchedule` passes the entire `request` object as a React Query key — if `request.appliances` contains objects with non-stable references (new array on each render), the query refires on every render

**File**: `/frontend/lib/hooks/useOptimization.ts`
**Lines**: 17–24

```typescript
queryKey: ['optimization', 'schedule', request],
```

`request` is typed as `GetOptimalScheduleRequest` containing `appliances: Appliance[]`. If the caller constructs `appliances` inline (e.g., `useOptimalSchedule({ appliances: [...someState] })`), React Query performs a deep-equal check on the key, but that check is performed every render. With a large appliance array, the structural comparison on every render is a performance issue. More critically, if `Appliance` objects include non-serializable values in the future, the comparison will behave incorrectly.

**Fix**: Serialize the key to a stable string or require callers to memoize the request object:

```typescript
queryKey: ['optimization', 'schedule', JSON.stringify(request)],
```

---

## P2 — Medium

---

### P2-01: `queryAgent` async generator has no timeout — a hanging SSE connection will block the generator indefinitely

**File**: `/frontend/lib/api/agent.ts`
**Lines**: 54–98

There is no timeout on the initial `fetch` or on individual `reader.read()` calls. If the backend stalls mid-stream, `reader.read()` will `await` forever. The `useAgentQuery` hook will show `isStreaming: true` with no way for the user to recover except a full page reload (since `cancel()` does not abort the fetch — see P0-01).

**Fix**: Use `AbortSignal.timeout` on the initial fetch and wrap `reader.read()` in a race:

```typescript
const timeoutSignal = AbortSignal.timeout(120_000) // 2 min max
const combinedSignal = signal
  ? AbortSignal.any([signal, timeoutSignal])
  : timeoutSignal
const response = await fetch(url, { ..., signal: combinedSignal })
```

---

### P2-02: `useRefreshPrices` returns a plain function, not a stable callback — callers will recreate it on every render

**File**: `/frontend/lib/hooks/usePrices.ts`
**Lines**: 72–78

```typescript
export function useRefreshPrices() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ['prices'] })
  }
}
```

A new function reference is returned on every call to `useRefreshPrices()`. If passed as a prop or used in a `useEffect` dependency array, it will cause unnecessary re-renders or effect re-runs.

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

### P2-03: `useNotificationCount` has `refetchInterval: 30_000` but no `refetchIntervalInBackground: false` guard — polls even when the document is hidden, wasting bandwidth and server connections on backgrounded tabs

**File**: `/frontend/lib/hooks/useNotifications.ts`
**Lines**: 41–48

React Query's `refetchInterval` fires regardless of document visibility by default when `refetchIntervalInBackground` is not explicitly set to `false`. Combined with the SSE connection in `useRealtimePrices`, a backgrounded tab can maintain multiple active polling loops.

**Fix**:

```typescript
export function useNotificationCount() {
  return useQuery({
    queryKey: notificationKeys.count,
    queryFn: () => getNotificationCount(),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    staleTime: 30_000,
  })
}
```

---

### P2-04: `useAlertHistory` query key includes `page` but not `pageSize` — changing `pageSize` with the same `page` will serve stale cached data

**File**: `/frontend/lib/hooks/useAlerts.ts`
**Lines**: 27–33

```typescript
queryKey: ['alerts', 'history', page],
```

`pageSize` is a parameter but is absent from the query key. If a component calls `useAlertHistory(1, 20)` and then `useAlertHistory(1, 50)`, both requests share the same cache entry. The second call returns the 20-item cached response.

**Fix**:

```typescript
queryKey: ['alerts', 'history', page, pageSize],
```

---

### P2-05: `useConnections` error handler swallows the original `ApiClientError` for non-403 errors and replaces it with a generic message — callers cannot distinguish 401 from 500

**File**: `/frontend/lib/hooks/useConnections.ts`
**Lines**: 33–38

```typescript
} catch (err) {
  if (err instanceof ApiClientError && err.status === 403) {
    throw Object.assign(new Error('upgrade'), { status: 403 })
  }
  throw new Error('Failed to load connections')  // all other errors collapsed
}
```

A 401 (session expired) or 500 (backend error) both become `Error('Failed to load connections')` with no status code, preventing the UI from showing context-appropriate error messages.

**Fix**:

```typescript
} catch (err) {
  if (err instanceof ApiClientError) {
    if (err.status === 403) {
      throw Object.assign(new Error('upgrade'), { status: 403 })
    }
    throw err // preserve original ApiClientError with status
  }
  throw new Error('Failed to load connections')
}
```

---

### P2-06: `useProfile` queryFn calls `useSettingsStore.getState()` inside the async function body — this is a store accessor call (not a hook call) but is undocumented; future developers may extract the logic and accidentally call it conditionally or inside a render function

**File**: `/frontend/lib/hooks/useProfile.ts`
**Lines**: 16–29

The pattern is correct at runtime, but the code comment is absent. Additionally, if `useProfile` is called in a Server Component by accident (since it lacks `'use client'`), `useSettingsStore` will throw because Zustand's localStorage persistence requires a browser environment.

**Fix**: Add `'use client'` directive and a comment:

```typescript
'use client'

// ...in queryFn:
// useSettingsStore.getState() is a Zustand store accessor, NOT a React hook call.
// Safe to call inside async functions, effects, and queryFns.
const store = useSettingsStore.getState()
```

---

### P2-07: `getGasRates` appends a trailing slash to the URL — `/rates/natural-gas/` — which may not match backend route

**File**: `/frontend/lib/api/gas-rates.ts`
**Line**: 110

```typescript
return apiClient.get<GasRatesResponse>('/rates/natural-gas/', query)
```

All other API calls use paths without trailing slashes (e.g., `/rates/heating-oil`, `/rates/propane`). FastAPI routes are exact-match by default; `/rates/natural-gas/` will return a 307 redirect to `/rates/natural-gas` in production if FastAPI's `redirect_slashes=True` (the default). This works but adds an unnecessary redirect roundtrip and is inconsistent with all other API clients.

**Fix**:

```typescript
return apiClient.get<GasRatesResponse>('/rates/natural-gas', query)
```

---

### P2-08: `useRateChanges` query key uses the `params` object directly — `params` is an optional reference that changes identity on every render if constructed inline

**File**: `/frontend/lib/hooks/useRateChanges.ts`
**Lines**: 17–22

```typescript
queryKey: ['rate-changes', params],
```

If callers pass `useRateChanges({ utility_type: 'electricity' })` inline, a new object literal is created on every render. React Query performs structural comparison on query keys, which prevents duplicate fetches, but the structural comparison has a cost proportional to the object depth on every render cycle.

**Fix**: Destructure to primitives in the query key:

```typescript
queryKey: ['rate-changes', params?.utility_type, params?.region, params?.days, params?.limit],
```

---

### P2-09: `useOptimizationResult` passes a non-null-asserted `region!` to `getOptimizationResult` but `region` could be `null` at query execution if region changes between the `enabled` check and the `queryFn` invocation

**File**: `/frontend/lib/hooks/useOptimization.ts`
**Lines**: 29–36

React Query evaluates `enabled` and `queryFn` in the same synchronous frame, so this is safe in practice. However the non-null assertion `region!` throughout many hooks is a pattern that will fail if a hook is ever called without the `enabled` guard being correctly maintained. This is a class of latent bugs across 15+ hooks.

Affected hooks (non-exhaustive): `usePriceHistory`, `usePriceForecast`, `useOptimalPeriods`, `useSuppliers`, `useGasRates`, `useGasHistory`, `useGasStats`, `useGasSupplierComparison`, `useCCADetect`, `useCCACompare`, `useCCAInfo`, `useHeatingOilHistory`, `usePropaneHistory`, `usePropaneComparison`, `usePropaneTiming`, `useNeighborhoodComparison`.

**Fix**: Use a typed factory helper that enforces the guard:

```typescript
// lib/utils/queryHelpers.ts
export function whenDefined<T, R>(
  value: T | null | undefined,
  fn: (v: T) => R,
): () => R {
  return () => fn(value as T) // only called when enabled: !!value
}

// Usage:
queryFn: whenDefined(region, (r) => getGasRates({ region: r, limit })),
enabled: !!region,
```

---

### P2-10: `usePotentialSavings` uses a mutable `appliances` array as part of the React Query key — large appliance arrays cause expensive deep equality checks on every render

**File**: `/frontend/lib/hooks/useOptimization.ts`
**Lines**: 67–74

```typescript
queryKey: ['potential-savings', appliances, region],
```

See P1-08 for the pattern. For `usePotentialSavings` this is worse because `appliances` could have many items each with nested `preferredTimeRange` objects.

**Fix**: Stabilize the key:

```typescript
queryKey: ['potential-savings', appliances.map(a => a.id).join(','), region],
```

---

### P2-11: `normaliseSupplierResponse` hardcodes `logoUrl: null` and `reviewCount: null` even though the list endpoint (`ApiSupplierResponse`) does not include those fields — silently drops `logo_url` that may exist in future list endpoint responses

**File**: `/frontend/types/api-helpers.ts`
**Lines**: 173–189

`ApiSupplierResponse` (the list type) does not have `logo_url`. This is correct per the current generated API types. However `normaliseSupplierResponse` explicitly hard-codes `null` values without a comment explaining that the list endpoint does not return those fields. Future developers adding `logo_url` to `ApiSupplierResponse` will correctly update the generated type but may miss the normalizer.

**Fix**: Add a `TODO` comment:

```typescript
// logo_url, reviewCount, and description are only available from the detail endpoint.
// Update normaliseSupplierDetailResponse when adding fields here.
logoUrl: null,
reviewCount: null,
```

---

### P2-12: `CommunitySolarSavingsResponse` fields are `string` (representing Decimal), but there is no `parseDecimal` call in `useCommunitySolarSavings` or the callers — arithmetic on these values at the UI layer will silently do string concatenation

**File**: `/frontend/lib/api/community-solar.ts`
**Lines**: 35–43

```typescript
export interface CommunitySolarSavingsResponse {
  current_monthly_bill: string   // Decimal string
  savings_percent: string
  monthly_savings: string
  annual_savings: string
  five_year_savings: string
  new_monthly_bill: string
}
```

All fields are raw decimal strings from the backend. If UI components perform `monthly_savings + annual_savings` they will get string concatenation instead of numeric addition. The `parseDecimal` helper from `types/api-helpers.ts` exists but is not referenced in any community solar type.

**Fix**: Add `DecimalStr` branded type aliases or document parsing requirement:

```typescript
import type { DecimalStr } from '@/types/generated/api'

export interface CommunitySolarSavingsResponse {
  /** Decimal string — parse with parseDecimal() before arithmetic */
  current_monthly_bill: DecimalStr
  // ...
}
```

---

### P2-13: `useRealtimeSubscription` polling hook calls `onUpdateRef.current?.()` with a payload that includes only `table` and `event` — the `filter` field from `RealtimeConfig` is never included in the payload

**File**: `/frontend/lib/hooks/useRealtime.ts`
**Lines**: 187–202

```typescript
onUpdateRef.current?.({ table: config.table, event: config.event })
```

`config.filter` is part of `RealtimeConfig` but is silently dropped from the payload. Callers that depend on the filter value in their `onUpdate` handler will receive an incomplete payload.

**Fix**:

```typescript
onUpdateRef.current?.({ table: config.table, event: config.event, filter: config.filter })
```

Also update the payload type:

```typescript
onUpdate?: (payload: { table: string; event?: string; filter?: string }) => void
```

---

### P2-14: `useAuth` `signInWithGoogle` and `signInWithGitHub` set `isLoading = true` but never set it back to `false` on the happy path — the social sign-in redirect leaves `isLoading` as `true` permanently

**File**: `/frontend/lib/hooks/useAuth.tsx`
**Lines**: 270–303

Both `signInWithGoogle` (line 274–284) and `signInWithGitHub` (line 288–303) call `authClient.signIn.social()`. On success, Better Auth redirects the browser to the OAuth provider, so the component unmounts immediately. `isLoading` is set to `true` at the start but is only reset in the `catch` block. If the redirect happens, `isLoading` stays `true`. When the user returns from OAuth and `AuthProvider` remounts, `initAuth` will set `isLoading` correctly (to `true` then `false`), so this is recoverable. However, a failed redirect that doesn't throw (e.g., blocked popup) leaves a permanently stuck spinner.

The `finally { setIsLoading(false) }` pattern used by `signIn`, `signUp`, and `sendMagicLink` should be applied here too, with the understanding that the component will unmount on successful redirect before `finally` runs.

**Fix**:

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
    // If still mounted (redirect failed), reset loading state
    setIsLoading(false)
  }
}, [])
```

---

## P3 — Low

---

### P3-01: `ApiSuppliersListResponse` is missing a `pages` field despite the backend returning it — `extractPaginationMeta` has to compute it via `Math.ceil`

**File**: `/frontend/types/generated/api.ts`
**Lines**: 246–253

The `ApiSuppliersListResponse` type does not include a `pages` field. `ApiPriceHistoryResponse` does include `pages`. The `extractPaginationMeta` helper in `types/api-helpers.ts` handles the missing `pages` gracefully, but if the backend starts returning `pages` in the suppliers list response, it will be silently ignored.

**Fix**: Add `pages?: number` to `ApiSuppliersListResponse`.

---

### P3-02: `GasPrice.price` is typed as `string` (Decimal), but the parallel types `HeatingOilPrice.price_per_gallon` and `PropanePrice.price_per_gallon` are typed as `number` — inconsistent Decimal handling across utility modules

**File**: `/frontend/lib/api/gas-rates.ts` line 16, `/frontend/lib/api/heating-oil.ts` line 5, `/frontend/lib/api/propane.ts` line 5

Gas prices use `price: string` (consistent with Decimal-string convention). Heating oil and propane use `price_per_gallon: number` (numeric). If the backend returns Decimal strings for all three, the heating-oil and propane types will silently overflow on large values and produce float arithmetic errors.

**Fix**: Audit backend serialization for `heating_oil_prices.price_per_gallon` and `propane_prices.price_per_gallon`. If they are Decimal columns, change to `DecimalStr` and add `parseDecimal` at usage sites.

---

### P3-03: `WaterRatesResponse.count` is typed as `count?: number` (optional) but `WaterBenchmark.municipalities` is `municipalities: number` (required) — minor inconsistency in optional vs required count fields

**File**: `/frontend/lib/api/water.ts`
**Lines**: 21, 38

No bug, but `count` in responses should be consistently typed as required `number` if the backend always returns it.

---

### P3-04: `useExportRates` is a useQuery with `enabled = false` by default — it will never auto-fetch, but is set up as a query rather than a mutation/imperative call, making the intent unclear

**File**: `/frontend/lib/hooks/useExport.ts`
**Lines**: 4–16

Export operations (user-triggered, not background refetches) typically use `useMutation`. Using `useQuery` with `enabled: false` works but is semantically wrong — queries are for reading data that can be cached and revalidated, mutations are for user-triggered operations. With `useQuery` + `enabled=false`, calling `refetch()` does not track loading state correctly in all React Query versions.

**Fix**: Convert to `useMutation` or use `useQuery` with `enabled` wired to a state variable, documented with a comment explaining the polling-vs-manual-trigger trade-off.

---

### P3-05: `useAuth.tsx` has `router` in the `useCallback` dependency array for `signOut` but `signIn` and `signUp` use `window.location.href` directly — inconsistent navigation pattern

**File**: `/frontend/lib/hooks/useAuth.tsx`
**Lines**: 201, 229, 265

`signIn` and `signUp` use `window.location.href` for navigation (full page reload, intentional per comment). `signOut` uses `router.push` (client-side navigation). The inconsistency could confuse future developers who might switch `signOut` to `window.location.href` for parity, breaking the middleware session cookie check.

**Fix**: Add inline comments to each navigation call explaining the intentional choice.

---

### P3-06: `useAuth` `initAuth` fires `fetch(\`${API_URL}/auth/me\`, ...)` as fire-and-forget with `.catch(() => {})` — errors are completely silenced, preventing any visibility into profile sync failures

**File**: `/frontend/lib/hooks/useAuth.tsx`
**Lines**: 96, 181

The comment says "Fire-and-forget: auth init must not block on this." That is correct. However the empty catch swallows all errors including network failures and 500 errors. At minimum, errors should be logged at `console.warn` level so they appear in production error monitoring (Sentry).

**Fix**:

```typescript
fetch(`${API_URL}/auth/me`, { credentials: 'include' })
  .catch((err) => console.warn('[auth] /auth/me sync failed (non-fatal):', err))
```

---

### P3-07: `email/send.ts` SMTP transporter is a module-level singleton with no connection pooling TTL — a long-lived serverless environment (Vercel Edge functions have a 50s timeout, but persistent Node.js processes can hold stale SMTP connections for hours)

**File**: `/frontend/lib/email/send.ts`
**Lines**: 65–81

`_transporter` is created once and cached indefinitely. SMTP connections have a server-side idle timeout (Gmail: 10 min). If the transporter's underlying TCP connection times out, the next `sendMail` call will fail with `ECONNRESET`. Nodemailer handles reconnection internally, but the connection state may be stale in long-lived processes.

**Fix**: Enable nodemailer's `pool` option and set a `maxConnections`/`idleTimeout`:

```typescript
_transporter = nodemailer.createTransport({
  host,
  port: parseInt(process.env.SMTP_PORT ?? '587', 10),
  secure: false,
  pool: true,
  maxConnections: 2,
  idleTimeout: 300_000, // 5 minutes
  auth: { user: process.env.SMTP_USERNAME, pass: process.env.SMTP_PASSWORD },
})
```

---

### P3-08: `Supplier` type in `types/index.ts` and `NormalisedSupplier` in `types/api-helpers.ts` are structurally divergent — `Supplier` has `estimatedAnnualCost: number` (required), `NormalisedSupplier` does not — callers of `normaliseSupplierResponse` cannot use the result where `Supplier` is expected

**File**: `/frontend/types/index.ts` line 113, `/frontend/types/api-helpers.ts` line 154

`Supplier` in `types/index.ts` is the legacy frontend type used by optimization, settings store, and supplier components. `NormalisedSupplier` in `types/api-helpers.ts` is the newer API-derived type. They serve overlapping purposes but are structurally incompatible. Code that calls `normaliseSupplierResponse()` and then tries to assign the result to a `Supplier`-typed variable will get a type error.

**Fix**: Either merge the types or add a `toSupplier(raw: NormalisedSupplier): Supplier` converter that fills in defaults for fields only in the legacy type (`estimatedAnnualCost: 0`, etc.).

---

### P3-09: `useRealtimeBroadcast` returns `isConnected: true` immediately and `broadcast` is a no-op — both are misleading stubs that could cause product code to make incorrect assumptions about broadcast availability

**File**: `/frontend/lib/hooks/useRealtime.ts`
**Lines**: 211–227

Setting `isConnected = true` for an unimplemented feature causes any UI that checks `isConnected` to show a "connected" indicator for functionality that doesn't exist.

**Fix**: Either return `isConnected: false` and mark the hook with `@deprecated` + `TODO`, or remove the hook until the WebSocket implementation is ready.

---

## Appendix: Files Reviewed

| File | Lines | Notes |
|------|-------|-------|
| `lib/api/client.ts` | 237 | P0-03, P1-04, P1-05 |
| `lib/api/circuit-breaker.ts` | 113 | P1-04, P1-05 |
| `lib/api/agent.ts` | 124 | P0-01, P2-01 |
| `lib/api/alerts.ts` | 125 | P2-04 (via hook) |
| `lib/api/affiliate.ts` | 29 | Clean |
| `lib/api/cca.ts` | 64 | Clean |
| `lib/api/community-solar.ts` | 100 | P2-12 |
| `lib/api/community.ts` | 97 | Clean |
| `lib/api/export.ts` | 43 | Clean |
| `lib/api/forecast.ts` | 38 | Clean |
| `lib/api/gas-rates.ts` | 142 | P2-07, P3-02 |
| `lib/api/heating-oil.ts` | 86 | P3-02 |
| `lib/api/neighborhood.ts` | 23 | Clean |
| `lib/api/notifications.ts` | 79 | P2-03 (via hook) |
| `lib/api/optimization.ts` | 77 | Clean |
| `lib/api/portal.ts` | 81 | P1-01 |
| `lib/api/prices.ts` | 185 | Clean |
| `lib/api/profile.ts` | 38 | Clean |
| `lib/api/propane.ts` | 78 | P3-02 |
| `lib/api/rate-changes.ts` | 93 | P2-08 |
| `lib/api/reports.ts` | 38 | Clean |
| `lib/api/savings.ts` | 16 | Clean |
| `lib/api/suppliers.ts` | 186 | Clean |
| `lib/api/utility-discovery.ts` | 40 | Clean |
| `lib/api/water.ts` | 83 | P3-03 |
| `lib/auth/client.ts` | 17 | Clean |
| `lib/auth/server.ts` | 152 | Clean |
| `lib/config/env.ts` | 138 | Clean |
| `lib/config/seo.ts` | (not read) | — |
| `lib/constants/regions.ts` | (not read) | — |
| `lib/contexts/sidebar-context.tsx` | (not read) | — |
| `lib/contexts/toast-context.tsx` | (not read) | — |
| `lib/email/send.ts` | 155 | P3-07 |
| `lib/hooks/useAgent.ts` | 71 | P0-01 |
| `lib/hooks/useAlerts.ts` | 77 | P2-04 |
| `lib/hooks/useAuth.tsx` | 380 | P0-03, P1-03, P1-07, P2-14, P3-05, P3-06 |
| `lib/hooks/useCCA.ts` | 43 | P2-09 pattern |
| `lib/hooks/useCombinedSavings.ts` | 10 | Clean |
| `lib/hooks/useCommunity.ts` | 59 | Clean |
| `lib/hooks/useCommunitySolar.ts` | 60 | Clean |
| `lib/hooks/useConnections.ts` | 48 | P2-05 |
| `lib/hooks/useDiagrams.ts` | 87 | Clean |
| `lib/hooks/useExport.ts` | 24 | P3-04 |
| `lib/hooks/useForecast.ts` | 24 | Clean |
| `lib/hooks/useGasRates.ts` | 54 | P2-08 pattern |
| `lib/hooks/useGeocoding.ts` | 41 | P1-02 |
| `lib/hooks/useHeatingOil.ts` | 42 | Clean |
| `lib/hooks/useNeighborhood.ts` | 11 | Clean |
| `lib/hooks/useNotifications.ts` | 82 | P2-03 |
| `lib/hooks/useOptimization.ts` | 75 | P1-08, P2-09, P2-10 |
| `lib/hooks/usePrices.ts` | 78 | P2-02 |
| `lib/hooks/useProfile.ts` | 47 | P2-06 |
| `lib/hooks/usePropane.ts` | 43 | Clean |
| `lib/hooks/useRateChanges.ts` | 40 | P2-08 |
| `lib/hooks/useRealtime.ts` | 228 | P2-03 (pattern), P2-13, P3-09 |
| `lib/hooks/useReports.ts` | 12 | Clean |
| `lib/hooks/useSavings.ts` | 28 | Clean |
| `lib/hooks/useSuppliers.ts` | 186 | Clean |
| `lib/hooks/useUtilityDiscovery.ts` | 30 | Clean |
| `lib/hooks/useWater.ts` | 32 | Clean |
| `lib/notifications/onesignal.ts` | 57 | Clean |
| `lib/store/settings.ts` | 198 | Clean |
| `lib/utils/calculations.ts` | 173 | Clean |
| `lib/utils/cn.ts` | (not read) | — |
| `lib/utils/devGate.ts` | 3 | Clean |
| `lib/utils/format.ts` | 116 | Clean |
| `lib/utils/url.ts` | 47 | P1-06 |
| `types/api-helpers.ts` | 319 | P2-11, P3-08 |
| `types/generated/api.ts` | 426 | P3-01 |
| `types/index.ts` | 241 | P3-08 |
| `app/api/auth/[...all]/route.ts` | 57 | Clean |
| `app/api/checkout/route.ts` | 44 | P0-02 |
| `app/api/dev/diagrams/route.ts` | 82 | Clean |
| `app/api/dev/diagrams/[name]/route.ts` | 79 | Clean |

---

## Recommended Fix Priority

1. **P0-01** — agent stream reader leak + abort wiring (data loss, hanging connections)
2. **P0-02** — checkout route header injection (security)
3. **P0-03** — module-level redirect flag in SSR (silent auth bypass for concurrent users)
4. **P1-01** — portal.ts bypasses apiClient (reliability, auth gap)
5. **P1-02** — geocoding calls internal endpoint without credentials (security + reliability)
6. **P1-06** — `isSafeOAuthRedirect` breaks on relative URLs (OAuth flows fail silently)
7. **P1-07** — public pages fire unnecessary auth API calls triggering 401 redirect loops
8. **P1-04** — circuit breaker single-success hard-resets partial failure count
9. **P2-02** — `useRefreshPrices` unstable callback reference
10. **P2-03** — notification polling in backgrounded tabs
