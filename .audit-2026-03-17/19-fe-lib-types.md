# Audit Report: Frontend Lib, Types & API Clients
## Date: 2026-03-17

---

### Executive Summary

This audit covers **79 files** across `frontend/lib/` (api clients, hooks, utils, stores, constants, auth, config, email, notifications) and `frontend/types/`. The codebase is in strong overall shape. The architecture is well-layered: a single typed `apiClient` object wraps all fetch calls with retry, circuit-breaker, and 401 redirect logic; React Query hooks wrap every API function cleanly; and the generated `types/generated/api.ts` plus normalisation helpers in `types/api-helpers.ts` form a solid contract boundary. No hardcoded credentials or plaintext secrets were found.

The most significant issue is a **P1 security concern** in `useAuth.tsx` where the callbackUrl redirect validation is implemented inline with a subtly weaker check than the canonical `isSafeRedirect()` utility that already exists for this exact purpose, creating a maintenance divergence point. Several P2 type-safety gaps were identified — the most impactful being a missing explicit type annotation that results in an implicit `unknown[]` cache write, and two API functions that omit generic type parameters and silently infer `unknown`.

---

### Strengths

- **No credentials in source.** All secrets go through `process.env.*` and are read lazily. `env.ts` provides a clean, documented single source of truth for all `NEXT_PUBLIC_*` vars with production-fail-fast guards.
- **Circuit breaker is production-grade.** `circuit-breaker.ts` correctly implements CLOSED/OPEN/HALF_OPEN state machine with a configurable multi-success recovery threshold, lazy OPEN→HALF_OPEN transition, and a separate `_resetForTesting` escape hatch.
- **401 redirect loop prevention.** `client.ts` uses sessionStorage counters + an in-flight deduplication flag to prevent infinite 401 redirect loops, with correct 10-second window expiry.
- **React Query queryKey stability.** Hooks that accept objects or arrays (e.g. `useOptimalSchedule`, `useCompareSuppliers`, `usePotentialSavings`) correctly destructure or serialise queryKey parts to avoid stale-reference infinite refetch bugs.
- **AbortSignal propagation.** Every API function and hook passes `signal` through consistently, enabling proper request cancellation.
- **isSafeRedirect is correct.** `url.ts` uses `new URL(url, window.location.origin)` + origin comparison which correctly handles protocol-relative URLs, `javascript:` schemes, and path-only inputs.
- **`parseDecimal` helpers** in `api-helpers.ts` guard all Decimal-string-to-number conversions at the boundary, preventing arithmetic on raw strings.
- **Email send.ts dual-provider fallback** is well-structured and properly lazy-initialises clients to avoid build-time env var issues.
- **SSR storage stub** in `settings.ts` uses `satisfies Storage` (all 6 members present) — correctly avoids the `as Storage` cast anti-pattern.
- **Normalisation layer** (`api-helpers.ts`) provides a clean separation between the snake_case backend contract and the camelCase UI layer, with type guards and extraction helpers.
- **`useRealtimePrices`** correctly uses `@microsoft/fetch-event-source` over native `EventSource` to include `credentials: 'include'` for httpOnly session cookies, and implements exponential backoff with a 30s cap.

---

### P0 — Critical

No P0 findings. No hardcoded API keys, credentials, unsafe URL construction from user input, or XSS via unescaped template literals were found in this scope.

---

### P1 — High

**P1-1: Duplicate, weaker redirect validation in `useAuth.tsx` vs `isSafeRedirect()`**

File: `frontend/lib/hooks/useAuth.tsx`, lines 269–277

The `signIn` callback in `useAuth.tsx` re-implements redirect validation inline:

```typescript
try {
  const parsed = new URL(callback, window.location.origin)
  if (parsed.origin === window.location.origin && parsed.pathname.startsWith('/')) {
    destination = parsed.pathname + parsed.search + parsed.hash
  }
} catch {
  // Malformed URL — fall back to dashboard
}
```

The `isSafeRedirect()` function in `lib/utils/url.ts` already does origin comparison correctly, and is what `client.ts` uses for the same purpose. The inline version adds an extra `pathname.startsWith('/')` guard that `isSafeRedirect()` does not need (because `new URL(relative, base).pathname` always starts with `/`), making the check slightly inconsistent and creating a maintenance fork — if the redirect logic in `url.ts` is ever tightened (e.g. blocking `/\evil.com` edge cases), the inline version in `useAuth.tsx` will not benefit automatically.

Additionally, the inline version strips query params from the final `destination` only if they were part of the original `callback` URL, but the user may arrive at `/auth/login?callbackUrl=%2Fdashboard%3Ftab%3Dalerts` — the current logic preserves `parsed.search` which is correct, but the redundant guard makes future audits harder.

**Fix:** Replace the inline validation block with a call to `isSafeRedirect()`:

```typescript
import { isSafeRedirect } from '@/lib/utils/url'

// In signIn():
const params = new URLSearchParams(window.location.search)
const callback = params.get('callbackUrl') || '/dashboard'
const destination = isSafeRedirect(callback) ? callback : '/dashboard'
window.location.href = destination
```

This is exactly the pattern used in `client.ts` lines 83–86 and should be consistent.

---

**P1-2: SSE URL in `useRealtime.ts` does not encode the `region` parameter**

File: `frontend/lib/hooks/useRealtime.ts`, line 46

```typescript
const url = `${API_URL}/prices/stream?region=${region}&interval=${interval}`
```

`region` is a user-derived string (e.g. `us_ct`, `uk`). While the current Region enum values are safe, the parameter is not `encodeURIComponent`-encoded. If a region value containing `&`, `=`, `#`, or `%` were ever passed (via a future code path, external link, or a bug in region parsing), the constructed URL would be malformed or could inject additional query parameters. `interval` is typed as `number` so it is safe.

**Fix:**

```typescript
const url = `${API_URL}/prices/stream?region=${encodeURIComponent(region)}&interval=${interval}`
```

This is consistent with how `client.ts` builds query strings (via `URLSearchParams.append` which encodes automatically).

---

**P1-3: `queryAgent` in `agent.ts` bypasses the shared `apiClient` — no retry, no circuit breaker, no 401 redirect**

File: `frontend/lib/api/agent.ts`, lines 55–60

```typescript
const response = await fetch(`${API_URL}/agent/query`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({ prompt, context }),
  signal,
})
```

This is intentional (SSE streaming requires direct `fetch`), but the consequence is:
- A 401 response from the agent endpoint will **not** trigger the 401 redirect-to-login flow that all other endpoints use.
- The 401 is converted to an `error` role message silently shown in the chat, potentially leaving the user confused about why their session expired rather than being redirected to re-authenticate.
- There is no retry on transient 5xx errors (the circuit breaker is also bypassed).

For SSE streaming, the constraint is real — you cannot use `apiClient.get()` for a streaming response. But the 401 handling can be made explicit:

**Fix:**

```typescript
if (!response.ok) {
  if (response.status === 401 && typeof window !== 'undefined') {
    // Mirror client.ts: redirect to login on session expiry
    window.location.href = `/auth/login?callbackUrl=${encodeURIComponent(window.location.pathname)}`
    return
  }
  const errorData = await response.json().catch(() => ({}))
  yield {
    role: 'error',
    content: errorData.detail || `Request failed (${response.status})`,
  }
  return
}
```

---

**P1-4: `useGeocoding.ts` calls an internal endpoint from the frontend**

File: `frontend/lib/hooks/useGeocoding.ts`, line 25

```typescript
const data = await apiClient.post<GeocodeResponse>('/internal/geocode', { address })
```

Per `CLAUDE.md`: "All `/api/v1/internal/*` routes require `X-API-Key` header." The frontend API client (`client.ts`) does **not** attach an `X-API-Key` header — it only sets `Content-Type` and optionally `X-Fallback-Mode`. Calling this endpoint from the browser will either fail with 401/403 (if the backend properly guards it) or succeed without auth (if the internal check is misconfigured).

If the geocode endpoint is intentionally public-facing (authenticated via session cookie rather than API key), its path should be `/geocode` not `/internal/geocode`. If it requires the API key, this frontend call is architecturally wrong and should proxy through a Next.js API route.

**Fix:** Verify the backend auth requirement. If the endpoint uses session-cookie auth (not API-key), rename it to a non-internal path. If it requires `X-API-KEY`, add a Next.js API route proxy at `/api/geocode` that adds the key server-side.

---

### P2 — Medium

**P2-1: `useRealtime.ts` cache write uses `unknown[]` type assertion without shape validation**

File: `frontend/lib/hooks/useRealtime.ts`, lines 76–84

```typescript
queryClient.setQueryData<unknown>(
  ['prices', 'current', region],
  (old: unknown) => {
    if (!old || !Array.isArray(old)) return old
    return old.map((entry: Record<string, unknown>) =>
      entry.supplier === data.supplier
        ? { ...entry, price_per_kwh: Number(data.price_per_kwh), timestamp: data.timestamp, is_peak: data.is_peak }
        : entry
    )
  }
)
```

The cache stores `ApiCurrentPriceResponse` (which has a `prices: ApiPriceResponse[] | null` field, **not** a bare array at the top level). The `Array.isArray(old)` check will always be false for the real cached data structure, meaning the SSE partial-merge silently no-ops every time. The real data shape is `{ prices: [...], region, timestamp, source }`, not a bare array.

The type annotation `<unknown>` hides this bug — if the generic were `<ApiCurrentPriceResponse>`, TypeScript would reject `Array.isArray(old)` as a type narrowing error on the wrong shape.

**Fix:**

```typescript
import type { ApiCurrentPriceResponse, ApiPriceResponse } from '@/types/generated/api'

queryClient.setQueryData<ApiCurrentPriceResponse>(
  ['prices', 'current', region],
  (old) => {
    if (!old?.prices) return old
    return {
      ...old,
      prices: old.prices.map((entry: ApiPriceResponse) =>
        entry.supplier === data.supplier
          ? { ...entry, current_price: data.price_per_kwh, timestamp: data.timestamp, is_peak: data.is_peak }
          : entry
      ),
    }
  }
)
```

Note: `ApiPriceResponse.current_price` is `DecimalStr` (string), so `data.price_per_kwh` (also a string from `PriceUpdate`) should be assigned directly, not wrapped in `Number()` which would produce a numeric type mismatch against the `DecimalStr` field.

---

**P2-2: `optimization.ts` — two functions return untyped responses**

File: `frontend/lib/api/optimization.ts`, lines 52–54 and 60–62

```typescript
export async function saveAppliances(
  appliances: Appliance[]
): Promise<{ success: boolean }> {
  return apiClient.post('/optimization/appliances', { appliances })
//               ^^^^ missing generic type parameter
}

export async function getAppliances(signal?: AbortSignal): Promise<{ appliances: Appliance[] }> {
  return apiClient.get('/optimization/appliances', undefined, { signal })
//               ^^^^ missing generic type parameter
}
```

Both `apiClient.post` and `apiClient.get` are generic. Without the type argument, TypeScript infers the return as `unknown` (or the declared Promise return type is accepted via structural coercion without being verified). The declared return types in the function signatures are correct, but the type parameter on the client call should be explicit to ensure the return value is actually checked against the expected shape. Compare with `calculatePotentialSavings` on line 77 which correctly passes the type argument.

**Fix:**

```typescript
return apiClient.post<{ success: boolean }>('/optimization/appliances', { appliances })
return apiClient.get<{ appliances: Appliance[] }>('/optimization/appliances', undefined, { signal })
```

---

**P2-3: `suppliers.ts` — `getSupplier` return type is the camelCase `Supplier` but backend returns `RawSupplierRecord` (snake_case)**

File: `frontend/lib/api/suppliers.ts`, line 60–62

```typescript
export async function getSupplier(supplierId: string, signal?: AbortSignal): Promise<Supplier> {
  return apiClient.get<Supplier>(`/suppliers/${supplierId}`, undefined, { signal })
}
```

The backend's `GET /suppliers/{id}` endpoint returns `ApiSupplierDetailResponse` (snake_case, from `types/generated/api.ts`). The camelCase `Supplier` type in `types/index.ts` does not have fields like `tariff_types`, `green_energy_provider`, etc. This means consumers of `getSupplier()` receive a snake_case object typed as camelCase `Supplier`, and any code accessing `supplier.tariffType` (camelCase) will get `undefined` at runtime while TypeScript says it's a valid `string`. The detail endpoint should use `ApiSupplierDetailResponse` as the return type and then be normalised via `normaliseSupplierDetailResponse()`.

**Fix:**

```typescript
import type { ApiSupplierDetailResponse } from '@/types/generated/api'
import { normaliseSupplierDetailResponse } from '@/types/api-helpers'

export async function getSupplier(supplierId: string, signal?: AbortSignal): Promise<NormalisedSupplier> {
  const raw = await apiClient.get<ApiSupplierDetailResponse>(`/suppliers/${supplierId}`, undefined, { signal })
  return normaliseSupplierDetailResponse(raw)
}
```

---

**P2-4: `format.ts` — `formatTime` and `formatDate` do not catch `parseISO` exceptions**

File: `frontend/lib/utils/format.ts`, lines 57–68

```typescript
export function formatTime(dateString: string, is24Hour: boolean = true): string {
  const date = parseISO(dateString)
  return format(date, is24Hour ? 'HH:mm' : 'h:mm a')
}

export function formatDate(dateString: string): string {
  const date = parseISO(dateString)
  return format(date, 'dd MMM yyyy')
}
```

`formatDateTime` on line 42 wraps the same operations in a `try/catch` and returns `dateString` on failure. `formatTime` and `formatDate` do not, so they will throw `RangeError: Invalid time value` if `dateString` is null, undefined, or a non-ISO string. Both functions are called throughout the UI with API-sourced strings that could be `null` (e.g. `Alert.created_at: string | null`).

**Fix:** Apply the same try/catch pattern as `formatDateTime`:

```typescript
export function formatTime(dateString: string, is24Hour: boolean = true): string {
  try {
    return format(parseISO(dateString), is24Hour ? 'HH:mm' : 'h:mm a')
  } catch {
    return dateString
  }
}

export function formatDate(dateString: string): string {
  try {
    return format(parseISO(dateString), 'dd MMM yyyy')
  } catch {
    return dateString
  }
}
```

---

**P2-5: `calculations.ts` — division by zero risk in `calculatePriceTrend`**

File: `frontend/lib/utils/calculations.ts`, lines 18–22

```typescript
const avgFirst = recentPrices.slice(0, Math.floor(recentPrices.length / 2))
  .reduce((a, b) => a + b, 0) / Math.floor(recentPrices.length / 2)
```

When `recentPrices.length === 2`, `Math.floor(2 / 2) === 1` — safe. When `recentPrices.length === 3`, `Math.floor(3 / 2) === 1` and `Math.ceil(3 / 2) === 2` — safe. However, if after the initial length guards the slice returns an empty array (possible if all prices are null and the `.filter` removes them all, then `length < 2` guard fires — so this is actually covered). The guard at line 16 (`if (recentPrices.length < 2) return 'stable'`) means `length` is at least 2, so `Math.floor(length / 2)` is at least 1. This is safe as coded, but the pattern is fragile — any future caller who skips the guard path could trigger `NaN`. Consider adding a guard inside the function for defensive coding.

Additionally, line 24:

```typescript
const changePercent = ((avgSecond - avgFirst) / avgFirst) * 100
```

If `avgFirst === 0`, this produces `Infinity` or `NaN`. This would happen if all "first half" prices are exactly 0 (theoretically possible for subsidised/regulated regions). Guard: `if (avgFirst === 0) return 'stable'`.

---

**P2-6: `server.ts` — HTML email bodies constructed via template literals without sanitisation**

File: `frontend/lib/auth/server.ts`, lines 46, 62, 73

```typescript
html: `<p>Hi${user.name ? ` ${user.name}` : ""},</p>...`
```

`user.name` is interpolated directly into an HTML email body without any HTML encoding. If a user registers with a name containing `<script>alert(1)</script>` or `<img src=x onerror=...>`, the resulting email HTML will contain injected markup. Most email clients strip scripts, but this is still a hygiene issue and could cause visual corruption or phishing-style rendering in HTML-permissive clients.

**Fix:** Escape HTML special characters in `user.name` before interpolation:

```typescript
function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// Usage:
html: `<p>Hi${user.name ? ` ${escapeHtml(user.name)}` : ""},</p>...`
```

Alternatively, use a templating library (e.g. `htm`, `@react-email/components`) for email generation.

---

**P2-7: `useAuth.tsx` — `useSettingsStore.getState()` called inside `useEffect` (React hook rule boundary)**

File: `frontend/lib/hooks/useAuth.tsx`, lines 165, 183

```typescript
const setCurrentSupplier = useSettingsStore.getState().setCurrentSupplier
setCurrentSupplier({ ... })

const store = useSettingsStore.getState()
if (!store.region) { store.setRegion(profileResult.value.region) }
```

Calling `useSettingsStore.getState()` outside a React component tree is technically valid for Zustand (it bypasses the hook subscription and reads current state directly). However, calling it inside an `async` function that runs after `await Promise.allSettled()` means the store reference is captured after a React render cycle may have occurred. If the user signs out during the `await`, the store could be in a reset state. This is a minor correctness edge case, not a crash — but it should be noted that these writes happen outside React's render cycle and won't trigger re-renders in consumers using `useSettingsStore()` hooks (they will re-render when Zustand notifies subscribers, which it does correctly). The pattern is safe but non-obvious; a comment noting why `getState()` is used here would help future maintainers.

---

**P2-8: `markAllRead` in `notifications.ts` — N+1 sequential fetch pattern is client-visible**

File: `frontend/lib/api/notifications.ts`, lines 73–78

```typescript
export async function markAllRead(): Promise<void> {
  const data = await getNotifications()
  await Promise.allSettled(
    data.notifications.map((n) => markNotificationRead(n.id))
  )
}
```

This is documented as a workaround for the absence of a backend bulk endpoint, but it generates `N` individual `PUT` requests (where N can be up to 50, per the docstring on `getNotifications`). `Promise.allSettled` is the right choice to avoid partial failure. This is acceptable given the constraint, but the implementation creates an observable "N parallel PUT requests" burst in browser DevTools which can look like bugs to developers. Consider adding a comment noting the 50-notification max and the intentional parallelism, and if the backend ever adds `PUT /notifications/read-all`, this is the single place to update.

---

**P2-9: `CCAProgram.generation_mix` typed as `Record<string, number> | null` — inconsistent with backend**

File: `frontend/lib/api/cca.ts`, line 9

```typescript
generation_mix: Record<string, number> | null
```

The backend stores `generation_mix` as JSONB. The type `Record<string, number>` assumes all values are numeric percentages (e.g. `{ solar: 0.4, wind: 0.6 }`), but JSONB can contain any value. If the backend ever returns `{ solar: "40%", other: null }` due to a data migration or data quality issue, this will silently mis-type the field. The type is reasonable as a documented assumption, but should be marked with a comment to make the assumption explicit.

---

**P2-10: `gas-rates.ts` — trailing slash in endpoint path**

File: `frontend/lib/api/gas-rates.ts`, line 111

```typescript
return apiClient.get<GasRatesResponse>('/rates/natural-gas/', query, { signal })
```

This endpoint has a trailing slash while all other endpoints in the codebase do not (e.g. `/rates/natural-gas/history` on line 120, `/rates/propane` on line 47 of `propane.ts`). The CF Worker or FastAPI router may or may not normalise trailing slashes. If the backend uses `redirect_slashes=False` (FastAPI default is `True`), this will cause an extra redirect on every gas-rates call, doubling the latency. The other natural-gas sub-paths (`/history`, `/stats`, `/deregulated-states`, `/compare`) correctly omit the trailing slash.

**Fix:** Remove the trailing slash: `'/rates/natural-gas'`

---

**P2-11: `types/index.ts` — `Supplier.rating` typed as `number` (required) but `RawSupplierRecord.rating` is `number | null`**

File: `frontend/types/index.ts`, line 131 vs `frontend/types/index.ts`, line 78

```typescript
// Supplier (camelCase UI type)
rating: number   // required, non-null

// RawSupplierRecord (backend shape)
rating?: number | null
```

The normalisation path in `useAuth.tsx` (line 172) sets `rating: supplier.rating ?? 0`, which patches the `null` case. But `getSupplier()` returns `Promise<Supplier>` while the actual backend response is `ApiSupplierDetailResponse` where `rating: number | null`. Without normalisation, any consumer of the detail endpoint that accesses `supplier.rating.toFixed(1)` will throw at runtime if `rating` is `null`. This compounds finding P2-3 above.

---

### P3 — Low

**P3-1: `chartTokens.ts` — `import type React` at bottom of file**

File: `frontend/lib/constants/chartTokens.ts`, line 66

```typescript
// React import needed for CSSProperties type above
import type React from 'react'
```

The import is placed at the **bottom** of the file, after the exported constants that depend on it. TypeScript hoists type imports, so this works correctly, but placing imports at the bottom is non-standard and will cause lint warnings with `import/first` rules. Move it to the top.

---

**P3-2: `useRealtimeOptimization` in `useRealtime.ts` — `isConnected` always returns `true` immediately**

File: `frontend/lib/hooks/useRealtime.ts`, lines 146–165

```typescript
export function useRealtimeOptimization() {
  const [isConnected, setIsConnected] = useState(false)
  useEffect(() => {
    const timer = setInterval(...)
    setIsConnected(true)  // set immediately, no actual connection
    return () => { clearInterval(timer); setIsConnected(false) }
  }, [queryClient])
  return { isConnected }
}
```

This hook sets `isConnected = true` immediately on mount even though it is a polling-only fallback (no actual SSE connection is established). Consumers that display a "Live" indicator based on `isConnected` will show "Live" for a polling fallback. Consider returning `{ isConnected: true, isPolling: true }` or removing `isConnected` from the return entirely for the polling hooks, to distinguish from the genuine SSE connection status in `useRealtimePrices`.

---

**P3-3: `electricity-optimizer-settings` — Zustand persist key has old product name**

File: `frontend/lib/store/settings.ts`, line 193

```typescript
name: 'electricity-optimizer-settings',
```

The product was rebranded to RateShift. The localStorage key retains the old working name. This is not a bug — localStorage data will persist under the old key, meaning existing users retain their settings without data loss — but the key name is inconsistent with the current branding and will cause confusion during debugging.

**Fix:** Retain the old key as-is to avoid breaking existing users' persisted state (changing the key would silently wipe all user preferences on next load). If a migration is desired, implement a Zustand migrate function. If no migration is needed, at minimum add a comment explaining why the old key is intentionally preserved.

---

**P3-4: `useConnections.ts` — error transformation creates a plain `Error` with an opaque message**

File: `frontend/lib/hooks/useConnections.ts`, lines 33–36

```typescript
if (err instanceof ApiClientError && err.status === 403) {
  throw Object.assign(new Error('upgrade'), { status: 403 })
}
```

The error message `'upgrade'` is a magic string that consuming UI components must match against to detect the upgrade prompt. This couples the hook's error format to the UI's string-matching logic. Consider exporting a typed error class or an error code enum:

```typescript
export class UpgradeRequiredError extends Error {
  readonly status = 403
  constructor() { super('upgrade_required') }
}
```

---

**P3-5: Legacy deprecated functions in `prices.ts` lack removal timeline**

File: `frontend/lib/api/prices.ts`, lines 143–170

`getCurrentPricesLegacy`, `getPriceHistoryLegacy`, and `getPriceForecastLegacy` are marked `@deprecated` but have no `@since` version or planned removal date in their JSDoc. As the codebase grows, deprecated symbols tend to linger indefinitely without a concrete removal target.

**Fix:** Add `@deprecated since 2026-03-xx — remove after confirming all callers migrated`.

---

**P3-6: `useDiagrams.ts` was in glob results but not read — verify this is intentional**

File: `frontend/lib/hooks/useDiagrams.ts`

This hook appeared in the file listing but its content was not examined as part of the batch reads. It should be reviewed in a subsequent pass for consistency with the patterns documented above.

---

**P3-7: `isSafeRedirect` relies on `window.location.origin` — not usable in SSR**

File: `frontend/lib/utils/url.ts`, line 19

```typescript
const parsed = new URL(url, window.location.origin)
return parsed.origin === window.location.origin
```

This function uses `window.location.origin` directly without an SSR guard. If imported in a server component or called during SSG, it will throw `ReferenceError: window is not defined`. The function is currently only called from client-side code (`client.ts` which has `typeof window !== 'undefined'` guards, and `useAuth.tsx` which is `'use client'`), so this does not currently cause runtime failures. Adding a guard makes the function safe to import universally:

```typescript
export function isSafeRedirect(url: string): boolean {
  if (typeof window === 'undefined') return false
  try {
    const parsed = new URL(url, window.location.origin)
    return parsed.origin === window.location.origin
  } catch {
    return false
  }
}
```

---

### Statistics

| Category | Count |
|----------|-------|
| Files audited | 79 |
| P0 (Critical) | 0 |
| P1 (High) | 4 |
| P2 (Medium) | 11 |
| P3 (Low) | 7 |
| Total findings | 22 |

### Finding Index

| ID | Severity | File | Summary |
|----|----------|------|---------|
| P1-1 | High | `lib/hooks/useAuth.tsx:269` | Inline redirect validation diverges from `isSafeRedirect()` |
| P1-2 | High | `lib/hooks/useRealtime.ts:46` | SSE URL `region` param not `encodeURIComponent`-encoded |
| P1-3 | High | `lib/api/agent.ts:55` | SSE streaming bypasses 401 redirect + circuit breaker |
| P1-4 | High | `lib/hooks/useGeocoding.ts:25` | Frontend calls `/internal/` endpoint (API-key-gated route) |
| P2-1 | Medium | `lib/hooks/useRealtime.ts:76` | Cache write typed as `unknown[]` — wrong shape, merge silently no-ops |
| P2-2 | Medium | `lib/api/optimization.ts:52,60` | `apiClient` calls missing generic type parameter |
| P2-3 | Medium | `lib/api/suppliers.ts:60` | `getSupplier()` returns `Supplier` (camelCase) but backend sends `ApiSupplierDetailResponse` (snake_case) |
| P2-4 | Medium | `lib/utils/format.ts:57,65` | `formatTime`/`formatDate` throw on invalid date strings (no try/catch) |
| P2-5 | Medium | `lib/utils/calculations.ts:24` | Division by zero when `avgFirst === 0` |
| P2-6 | Medium | `lib/auth/server.ts:46,62,73` | `user.name` interpolated into HTML email without escaping |
| P2-7 | Medium | `lib/hooks/useAuth.tsx:165,183` | `useSettingsStore.getState()` called in async effect — valid but non-obvious |
| P2-8 | Medium | `lib/api/notifications.ts:73` | N+1 PUT requests in `markAllRead` (no backend bulk endpoint) |
| P2-9 | Medium | `lib/api/cca.ts:9` | `generation_mix: Record<string, number>` over-constrains JSONB field |
| P2-10 | Medium | `lib/api/gas-rates.ts:111` | Trailing slash on `/rates/natural-gas/` — inconsistent with all other endpoints |
| P2-11 | Medium | `types/index.ts:131` | `Supplier.rating: number` (required) conflicts with backend `rating: number | null` |
| P3-1 | Low | `lib/constants/chartTokens.ts:66` | `import type React` at bottom of file |
| P3-2 | Low | `lib/hooks/useRealtime.ts:146` | `useRealtimeOptimization` reports `isConnected=true` for polling fallback |
| P3-3 | Low | `lib/store/settings.ts:193` | Zustand persist key uses old product name `electricity-optimizer` |
| P3-4 | Low | `lib/hooks/useConnections.ts:34` | 403 error uses opaque magic string `'upgrade'` |
| P3-5 | Low | `lib/api/prices.ts:143` | Deprecated legacy functions lack removal timeline |
| P3-6 | Low | `lib/hooks/useDiagrams.ts` | File not reviewed in this pass |
| P3-7 | Low | `lib/utils/url.ts:19` | `isSafeRedirect` lacks SSR guard for `window` |

### Priority Recommendations

1. **Fix P1-1 immediately** (1 line change) — consolidate redirect validation to use `isSafeRedirect()` consistently.
2. **Fix P1-2 immediately** (1 line change) — add `encodeURIComponent` to SSE URL construction.
3. **Fix P2-6** before the next marketing email is sent — HTML escaping in email templates is a hygiene issue that could cause visual corruption in emails.
4. **Fix P2-1** (cache write shape mismatch) — the SSE partial-merge has been silently broken since it was added; the fix is straightforward.
5. **Clarify P1-4** (internal geocode endpoint) — requires a backend architect decision on auth model for that route.
6. **Fix P2-4** (date formatting crashes) — low effort, high protection for null date strings from API.
7. **Fix P2-10** (trailing slash) — 1 character fix that eliminates a potential redirect overhead.
