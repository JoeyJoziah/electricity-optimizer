# Audit Report: Frontend Lib & Types
**Date:** 2026-03-23
**Scope:** Shared utilities, TypeScript types, API client, helper functions
**Files Reviewed:**

- `frontend/types/index.ts`
- `frontend/types/generated/api.ts`
- `frontend/types/api-helpers.ts`
- `frontend/lib/api/client.ts`
- `frontend/lib/api/circuit-breaker.ts`
- `frontend/lib/api/agent.ts`
- `frontend/lib/api/alerts.ts`
- `frontend/lib/api/community-solar.ts`
- `frontend/lib/api/forecast.ts`
- `frontend/lib/api/gas-rates.ts`
- `frontend/lib/api/notifications.ts`
- `frontend/lib/api/optimization.ts`
- `frontend/lib/api/prices.ts`
- `frontend/lib/api/profile.ts`
- `frontend/lib/api/rate-changes.ts`
- `frontend/lib/api/reports.ts`
- `frontend/lib/api/savings.ts`
- `frontend/lib/api/suppliers.ts`
- `frontend/lib/api/utility-discovery.ts`
- `frontend/lib/api/export.ts`
- `frontend/lib/api/neighborhood.ts`
- `frontend/lib/api/community.ts`
- `frontend/lib/api/heating-oil.ts`
- `frontend/lib/api/propane.ts`
- `frontend/lib/api/water.ts`
- `frontend/lib/api/cca.ts`
- `frontend/lib/api/affiliate.ts`
- `frontend/lib/api/portal.ts`
- `frontend/lib/utils/cn.ts`
- `frontend/lib/utils/calculations.ts`
- `frontend/lib/utils/format.ts`
- `frontend/lib/utils/url.ts`
- `frontend/lib/utils/devGate.ts`
- `frontend/lib/analytics/clarity.tsx`
- `frontend/lib/email/send.ts`
- `frontend/lib/config/env.ts`
- `frontend/lib/config/seo.ts`
- `frontend/lib/auth/client.ts`
- `frontend/lib/auth/server.ts`
- `frontend/lib/constants/regions.ts`
- `frontend/lib/constants/chartTokens.ts`
- `frontend/lib/store/settings.ts`
- `frontend/lib/notifications/onesignal.ts`
- `frontend/lib/hooks/useAuth.tsx`
- `frontend/lib/hooks/useProfile.ts`
- `frontend/lib/hooks/usePrices.ts`
- `frontend/lib/hooks/useSuppliers.ts`
- `frontend/lib/hooks/useSavings.ts`
- `frontend/lib/hooks/useAlerts.ts`
- `frontend/lib/hooks/useConnections.ts`
- `frontend/lib/hooks/useAgent.ts`
- `frontend/lib/hooks/useRealtime.ts`
- `frontend/lib/hooks/useNotifications.ts`
- `frontend/lib/hooks/useDiagrams.ts`
- `frontend/lib/hooks/useOptimization.ts`
- `frontend/lib/hooks/useGeocoding.ts`
- `frontend/lib/hooks/useForecast.ts`
- `frontend/lib/hooks/useGasRates.ts`
- `frontend/lib/hooks/useRateChanges.ts`
- `frontend/lib/hooks/useReports.ts`
- `frontend/lib/hooks/useExport.ts`
- `frontend/lib/hooks/useNeighborhood.ts`
- `frontend/lib/hooks/useHeatingOil.ts`
- `frontend/lib/hooks/usePropane.ts`
- `frontend/lib/hooks/useWater.ts`
- `frontend/lib/hooks/useCCA.ts`
- `frontend/lib/hooks/useCombinedSavings.ts`
- `frontend/lib/hooks/useCommunity.ts`
- `frontend/lib/hooks/useUtilityDiscovery.ts`
- `frontend/lib/hooks/useCommunitySolar.ts`
- `frontend/lib/contexts/toast-context.tsx`
- `frontend/lib/contexts/sidebar-context.tsx`

---

## P0 -- Critical (Fix Immediately)

### P0-01: Unsafe `undefined as T` cast hides missing response body
**File:** `frontend/lib/api/client.ts`, line 154
**Code:**
```typescript
if (isEmptyResponse(response)) {
  return undefined as T
}
```
**Issue:** When the generic type parameter `T` is not `undefined` or `void` (e.g., `apiClient.delete<{deleted: boolean; alert_id: string}>('/alerts/123')`), a 204 response will return `undefined` cast to `{deleted: boolean; alert_id: string}`. Downstream code that destructures the return value (e.g., `const { deleted } = await deleteAlert(id)`) will crash with "Cannot destructure property 'deleted' of undefined." This is a type-system lie that TypeScript cannot catch because the cast forces it through.
**Impact:** Any endpoint that returns 204/205 when the caller expects a body will silently produce `undefined` typed as `T`, causing runtime crashes when properties are accessed.
**Fix:** Return `undefined as unknown as T` and document the contract, OR change the return type of the wrapper to `Promise<T | undefined>`, OR add a type-level constraint that 204-returning endpoints must use `void` as the type parameter. Alternatively, use separate method overloads for endpoints that return no body (`deleteNoBody<void>()`).

### P0-02: `Supplier.rating` type mismatch between `types/index.ts` and `types/generated/api.ts`
**File:** `frontend/types/index.ts`, line 136 vs `frontend/types/generated/api.ts`, line 216
**Code:**
```typescript
// types/index.ts
rating: number     // non-nullable

// types/generated/api.ts
rating: number | null  // nullable
```
**Issue:** The hand-authored `Supplier` type in `types/index.ts` declares `rating` as `number` (required, non-nullable), but the backend API returns `rating: number | null`. Code that constructs a `Supplier` from API data must coerce `null` to a number, and any place that forgets this coercion will silently assign `null` to a `number` field. The `useAuth.tsx` hook at line 183 already does `rating: supplier.rating ?? 0` as a patch, but any other normalization path that doesn't will break.
**Impact:** Runtime `null` in a field typed as `number` causes NaN propagation in calculations (e.g., `formatCurrency(supplier.rating)` or supplier comparison logic).
**Fix:** Change `rating` in `types/index.ts` to `number | null` and update all consumers to handle `null`. Alternatively, always normalize via `api-helpers.ts`.

### P0-03: Agent SSE endpoint bypasses circuit breaker
**File:** `frontend/lib/api/agent.ts`, line 56
**Code:**
```typescript
const response = await fetch(`${API_URL}/agent/query`, {
```
**Issue:** The `queryAgent` function directly calls `fetch()` using the raw `API_URL` instead of routing through `apiClient` or `circuitBreaker.getBaseUrl()`. When the CF Worker gateway is down and the circuit breaker has tripped (OPEN state), all `apiClient.*` calls are routed to the Render fallback, but agent SSE requests continue hitting the dead gateway URL.
**Impact:** Agent chat is completely broken during gateway outages, even though all other features gracefully fall back to the Render backend.
**Fix:** Replace `API_URL` with `circuitBreaker.getBaseUrl()` and ideally record success/failure against the circuit breaker for the SSE request as well.

---

## P1 -- High (Fix This Sprint)

### P1-01: `getAlertHistory` double-coerces numeric params to string
**File:** `frontend/lib/api/alerts.ts`, lines 121-124
**Code:**
```typescript
return apiClient.get<GetAlertHistoryResponse>('/alerts/history', {
  page: page.toString(),
  page_size: pageSize.toString(),
}, { signal })
```
**Issue:** The `apiClient.get()` method already calls `String(v)` on all param values (client.ts line 235). Calling `.toString()` here is redundant but harmless. However, the deeper issue is that the `params` type on `apiClient.get` is `Record<string, string | number | boolean | (...)[]>`, so passing numbers directly is the correct pattern. Passing pre-stringified values works but is inconsistent with every other API module that passes numbers directly (e.g., `community.ts` line 72: `page, per_page: perPage`). This inconsistency makes the codebase harder to grep for param handling bugs.
**Severity context:** Low functional risk but elevates to P1 because the pattern mismatch obscures audit findings.
**Fix:** Pass `page` and `pageSize` directly as numbers, matching the pattern used in all other API modules.

### P1-02: Falsy parameter values silently dropped across multiple API modules
**Files:** `frontend/lib/api/forecast.ts` line 33, `frontend/lib/api/rate-changes.ts` lines 73-76, `frontend/lib/api/gas-rates.ts` line 110, `frontend/lib/api/export.ts` lines 36-38
**Code (representative example from forecast.ts):**
```typescript
if (state) params.state = state
if (horizonDays) params.horizon_days = String(horizonDays)
```
**Issue:** Using truthiness checks (`if (state)`, `if (horizonDays)`) drops valid falsy values. For `horizonDays`, the value `0` is falsy and would be silently omitted, but the backend would return the default (24h). While `0` days is arguably nonsensical, `params.limit` checks have the same pattern and `0` limit would silently be omitted when it should arguably be sent. For `params.days`, passing `0` explicitly would be dropped. The checks `if (params.days)` (rate-changes line 75), `if (params.limit)` (line 76) are the most concerning because a consumer passing `{days: 0, limit: 0}` would get unfiltered results.
**Impact:** Subtle data correctness issues when `0` is a meaningful value for numeric params.
**Fix:** Use `!== undefined` checks instead of truthiness: `if (horizonDays !== undefined) params.horizon_days = String(horizonDays)`.

### P1-03: `useRealtimePrices` mutates cache with `number` where `DecimalStr` is expected
**File:** `frontend/lib/hooks/useRealtime.ts`, line 87
**Code:**
```typescript
? { ...entry, price_per_kwh: Number(data.price_per_kwh), timestamp: data.timestamp, is_peak: data.is_peak }
```
**Issue:** The SSE price update stores `Number(data.price_per_kwh)` (a JS number) into the React Query cache for the `prices/current` query. However, the `ApiPriceResponse.current_price` field is typed as `DecimalStr` (string). Any component that calls `parseDecimal()` on the cached value will receive `NaN` because `parseFloat(123)` on a number technically works, but `typeof` checks in downstream code may fail, and mixed types in the cache break type safety guarantees.
**Impact:** After the first SSE update, cached price data has `number` where `string` is expected, causing potential rendering bugs in components that rely on `parseDecimal()` string input.
**Fix:** Store as string: `price_per_kwh: data.price_per_kwh` (keep the string) or `price_per_kwh: String(data.price_per_kwh)`.

### P1-04: `handleResponse` does not handle HTTP 1xx or 3xx responses
**File:** `frontend/lib/api/client.ts`, lines 117-158
**Issue:** `response.ok` is only true for 2xx status codes. If the backend returns a redirect (301/302/307/308), `response.ok` is false and the code falls into the error handling path, trying to parse JSON from a redirect body and throwing `ApiClientError` with an unhelpful message. While `fetch()` follows redirects automatically by default (`redirect: 'follow'`), if the redirect response is opaque or the final redirect is to a non-JSON resource, the error path produces a confusing error.
**Impact:** Edge case, but any misconfigured proxy returning a redirect instead of the API response produces a confusing error message rather than a clear "unexpected redirect" diagnostic.
**Fix:** Add explicit handling for redirect status codes (3xx) with a clear error message.

### P1-05: Email HTML template injection vulnerability
**File:** `frontend/lib/auth/server.ts`, lines 42-47, 56-63, 71-75
**Code (line 42-47):**
```typescript
sendResetPassword: async ({ user, url }) => {
  await sendEmail({
    to: user.email,
    subject: "Reset your password -- RateShift",
    html: `<p>Hi${user.name ? ` ${user.name}` : ""},</p><p>Click the link below to reset your password:</p><p><a href="${url}">Reset password</a></p>...`,
  });
},
```
**Issue:** `user.name` and `url` are interpolated directly into HTML without escaping. If a user sets their name to `<script>alert(1)</script>` or `" onclick="alert(1)`, the raw HTML is sent in the email. While most email clients strip `<script>` tags, attribute injection (`" style="background:url(...)`) and phishing-style HTML injection remain possible. The `url` parameter comes from Better Auth internals and is likely safe, but `user.name` is user-controlled.
**Impact:** Stored XSS/HTML injection in emails. A malicious user could set their name to HTML that renders differently in email clients, potentially for phishing.
**Fix:** HTML-escape `user.name` before interpolation. Use a helper: `function escapeHtml(s: string) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') }`.

### P1-06: `formatTime` and `formatDate` throw on invalid date strings
**File:** `frontend/lib/utils/format.ts`, lines 57-68
**Code:**
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
**Issue:** Unlike `formatDateTime` (line 42-52) which wraps `parseISO` + `format` in a try/catch and returns the raw string on failure, `formatTime` and `formatDate` have no error handling. If backend data contains a null/empty/malformed date string, `parseISO` returns `Invalid Date` and `format()` throws `RangeError: Invalid time value`.
**Impact:** UI crash when rendering any component that calls `formatTime()` or `formatDate()` with malformed backend data.
**Fix:** Wrap both functions in try/catch like `formatDateTime` does, returning a fallback string on failure.

### P1-07: Dual type system for suppliers creates maintenance burden and silent mismatch risk
**Files:** `frontend/types/index.ts` (`Supplier`, `RawSupplierRecord`), `frontend/types/generated/api.ts` (`ApiSupplierResponse`, `ApiSupplierDetailResponse`), `frontend/types/api-helpers.ts` (`NormalisedSupplier`)
**Issue:** There are three separate type hierarchies for a single domain concept (supplier):
1. Hand-authored `Supplier` in `types/index.ts` (camelCase, `rating: number`)
2. Generated `ApiSupplierResponse` in `types/generated/api.ts` (snake_case, `rating: number | null`)
3. Normalized `NormalisedSupplier` in `types/api-helpers.ts` (camelCase, `rating: number | null`)
The `Supplier` type is used by `useSuppliers.ts`, `optimization.ts`, `calculations.ts`, and the settings store. `NormalisedSupplier` is available but appears underutilized. Meanwhile, `getSupplier()` in `suppliers.ts` line 60 returns `Promise<Supplier>` directly from the API -- but the backend returns snake_case fields, meaning this cast silently produces an object where `avgPricePerKwh` is undefined (the backend sends `avg_price_per_kwh`).
**Impact:** `getSupplier()` returns data typed as `Supplier` but with snake_case field names, causing silent `undefined` values on camelCase fields.
**Fix:** `getSupplier()` should return the generated type and normalize via `normaliseSupplierDetailResponse()`. The hand-authored `Supplier` type should be deprecated in favor of `NormalisedSupplier`.

---

## P2 -- Medium (Fix Soon)

### P2-01: `isSafeHref` rejects relative URLs that may be legitimate
**File:** `frontend/lib/utils/url.ts`, lines 34-42
**Code:**
```typescript
export function isSafeHref(href: string): boolean {
  try {
    const parsed = new URL(href)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:'
  } catch {
    // Relative URLs or malformed strings -- reject
    return false
  }
}
```
**Issue:** Relative URLs like `/programs/123` will throw in the `URL` constructor (no base) and return `false`. If any code uses `isSafeHref` to validate internal links (e.g., CCA program URLs that are relative paths), they will be incorrectly rejected.
**Fix:** Accept a second `allowRelative` parameter, or use `new URL(href, window.location.origin)` and check that the result is same-origin or http/https.

### P2-02: `calculatePriceTrend` division by zero when all prices are 0
**File:** `frontend/lib/utils/calculations.ts`, line 24
**Code:**
```typescript
const changePercent = ((avgSecond - avgFirst) / avgFirst) * 100
```
**Issue:** If all recent prices are `0`, `avgFirst` is `0` and the division produces `NaN` (0/0) or `Infinity` (-X/0). The comparisons on lines 26-27 (`changePercent > 2`, `changePercent < -2`) will both be false for `NaN`, so it returns `'stable'`, which is accidentally correct but only by luck.
**Fix:** Add a guard: `if (avgFirst === 0) return 'stable'` before the division.

### P2-03: `getPriceCategory` division by zero when `avgPrice` is 0
**File:** `frontend/lib/utils/calculations.ts`, lines 152-161
**Code:**
```typescript
const ratio = currentPrice / avgPrice
```
**Issue:** If `avgPrice` is `0`, `ratio` is `Infinity` (or `NaN` if both are 0), and the function returns `'expensive'` because `Infinity > 1.2` is true. This may not be the desired behavior when there is no price data.
**Fix:** Guard against zero: `if (avgPrice === 0) return 'moderate'` or throw.

### P2-04: `markAllRead` is O(N) individual API calls without concurrency limit
**File:** `frontend/lib/api/notifications.ts`, lines 73-78
**Code:**
```typescript
export async function markAllRead(): Promise<void> {
  const data = await getNotifications()
  await Promise.allSettled(
    data.notifications.map((n) => markNotificationRead(n.id))
  )
}
```
**Issue:** If a user has 50 unread notifications, this fires 50 concurrent HTTP requests. There is no concurrency limit, which could trigger the API rate limiter (120 req/min) and cause 429 responses.
**Fix:** Either implement a backend bulk-mark-all endpoint (preferred), or add a concurrency limiter (e.g., `p-limit` with concurrency of 5-10).

### P2-05: `useRealtimePrices` SSE cache mutation uses `Record<string, unknown>` instead of typed data
**File:** `frontend/lib/hooks/useRealtime.ts`, lines 77-92
**Code:**
```typescript
queryClient.setQueryData<Record<string, unknown>>(
  ['prices', 'current', region],
  (old) => {
    if (!old) return old
    const prices = old.prices
    if (!Array.isArray(prices)) return old
    return {
      ...old,
      prices: prices.map((entry: Record<string, unknown>) =>
        entry.supplier === data.supplier
          ? { ...entry, price_per_kwh: Number(data.price_per_kwh), ... }
          : entry
      ),
    }
  }
)
```
**Issue:** The cache update uses `Record<string, unknown>` instead of the actual `ApiCurrentPriceResponse` type. This bypasses all type checking for the cache shape. If the backend response shape changes, the cache mutation will silently produce corrupted data rather than triggering a compile error.
**Fix:** Import and use `ApiCurrentPriceResponse` as the generic parameter: `queryClient.setQueryData<ApiCurrentPriceResponse>(...)`.

### P2-06: `useDiagrams` hook uses raw `fetch()` without auth or error typing
**File:** `frontend/lib/hooks/useDiagrams.ts`, lines 15-48
**Issue:** All four fetch calls in this file (`fetchDiagramList`, `fetchDiagram`, `saveDiagram`, `createDiagram`) use raw `fetch()` instead of `apiClient`. This bypasses:
- 401 redirect handling
- Retry logic
- Circuit breaker
- Consistent error typing (`ApiClientError`)
- Credentials inclusion (no `credentials: 'include'`)

The endpoints are `/api/dev/diagrams/*` which may be dev-only, but if they are used in production they have no auth protection from the client side.
**Fix:** Either route through `apiClient` or mark these as dev-only with a guard.

### P2-07: `SidebarContext` default value allows silent failures
**File:** `frontend/lib/contexts/sidebar-context.tsx`, lines 11-15
**Code:**
```typescript
const SidebarContext = createContext<SidebarContextValue>({
  isOpen: false,
  toggle: () => {},
  close: () => {},
})
```
**Issue:** Unlike `AuthContext` and `ToastContext` which use `null`/`undefined` defaults and throw on missing provider, `SidebarContext` provides a no-op default. If a component uses `useSidebar()` outside of `SidebarProvider`, it silently gets `isOpen: false` and no-op handlers instead of an error. This masks integration bugs.
**Fix:** Use `createContext<SidebarContextValue | null>(null)` and throw in `useSidebar()` if context is null.

### P2-08: `formatCompactNumber` loses precision at exactly 1000 and 1000000
**File:** `frontend/lib/utils/format.ts`, lines 81-89
**Code:**
```typescript
if (num >= 1000000) {
  return `${(num / 1000000).toFixed(1)}M`
}
if (num >= 1000) {
  return `${(num / 1000).toFixed(1)}K`
}
return num.toString()
```
**Issue:** `formatCompactNumber(1000)` returns `"1.0K"` which is correct, but `formatCompactNumber(999.5)` returns `"999.5"` (no abbreviation). The boundary is fine, but `formatCompactNumber(-5000)` returns `"-5000"` because negative numbers never trigger the `>= 1000` branch. The function silently ignores negative values.
**Fix:** Use `Math.abs(num)` for the threshold checks and prepend the sign: `const abs = Math.abs(num); const sign = num < 0 ? '-' : ''`.

### P2-09: `getSuppliers` drops `annualUsage` when value is `0`
**File:** `frontend/lib/api/suppliers.ts`, line 51
**Code:**
```typescript
if (annualUsage) {
  params.annual_usage = annualUsage.toString()
}
```
**Issue:** `0` is falsy, so `annualUsage = 0` would not be sent. While 0 kWh annual usage is arguably nonsensical, it violates the principle of least surprise for callers.
**Fix:** Use `if (annualUsage !== undefined)`.

### P2-10: `useAuth` `initAuth` effect runs unconditionally but has no cleanup for the fire-and-forget fetch
**File:** `frontend/lib/hooks/useAuth.tsx`, line 171
**Code:**
```typescript
fetch(`${API_URL}/auth/me`, { credentials: 'include' }).catch(() => {/* non-fatal */})
```
**Issue:** This fire-and-forget fetch has no `AbortController` tied to the component lifecycle. If the component unmounts before the fetch resolves, it will attempt to write to state on an unmounted component. While this specific call only calls `.catch()` and doesn't update state, the pattern sets a bad example. The same pattern appears on line 282.
**Fix:** Create an `AbortController` in the effect and abort in the cleanup function, or verify this is truly fire-and-forget with no state updates.

### P2-11: `env()` helper swallows empty strings as valid values
**File:** `frontend/lib/config/env.ts`, line 37
**Code:**
```typescript
if (value) return value
```
**Issue:** An empty string `""` is falsy, so `NEXT_PUBLIC_API_URL=""` falls through to the default. This is likely intentional (empty = not set), but the semantics are implicit. If someone sets `NEXT_PUBLIC_FALLBACK_API_URL=""` to explicitly disable the fallback, the `|| ''` on line 88 has the same effect, so this is consistent.
**Fix:** Document that empty strings are treated as "not set" in the JSDoc.

### P2-12: `BASE_URL` in `seo.ts` duplicates `SITE_URL` from `env.ts`
**File:** `frontend/lib/config/seo.ts`, line 61 vs `frontend/lib/config/env.ts`, line 120-124
**Code:**
```typescript
// seo.ts
export const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://rateshift.app'

// env.ts
export const SITE_URL: string = env(
  process.env.NEXT_PUBLIC_SITE_URL,
  'https://rateshift.app',
  { name: 'NEXT_PUBLIC_SITE_URL' },
)
```
**Issue:** Two separate constants reading the same env var with the same fallback, but `env.ts`'s version includes production validation. If a consumer imports `BASE_URL` from `seo.ts`, they bypass the production validation that `SITE_URL` from `env.ts` provides.
**Fix:** Remove `BASE_URL` from `seo.ts` and re-export `SITE_URL` from `env.ts`, or have `seo.ts` import from `env.ts`.

---

## P3 -- Low / Housekeeping

### P3-01: `_resetRedirectState` and `_resetForTesting` are internal but exported
**Files:** `frontend/lib/api/client.ts` line 52, `frontend/lib/api/circuit-breaker.ts` line 143
**Issue:** Test-only functions prefixed with `_` are exported from production modules. While harmless, they appear in IDE autocomplete for all consumers and could be accidentally called in production code.
**Fix:** Consider isolating test helpers via a separate `__test-utils__` export or conditional exports.

### P3-02: Deprecated legacy price functions should have `@deprecated` JSDoc
**File:** `frontend/lib/api/prices.ts`, lines 146-170
**Issue:** These functions already have `@deprecated` JSDoc tags -- good. However, they could be removed if no call-sites remain, reducing the API surface area.
**Fix:** Grep for call-sites; if none, remove the deprecated functions.

### P3-03: `community.ts` and `community-solar.ts` numeric field types inconsistent
**File:** `frontend/lib/api/community-solar.ts`, lines 19-26 vs `frontend/lib/api/community.ts` line 16
**Issue:** Community solar fields like `savings_percent`, `capacity_kw`, and `min_bill_amount` are typed as `string | null` (Decimal strings from backend), while `community.ts` uses `number | null` for `rate_per_unit`. This inconsistency means consumers need to know which API module uses strings vs numbers for decimal values.
**Fix:** Use the `DecimalStr` type alias from `generated/api.ts` for all Decimal string fields across all API modules for consistency.

### P3-04: `chartTooltipStyle` references React type but import is at end of file
**File:** `frontend/lib/constants/chartTokens.ts`, line 66
**Code:**
```typescript
// React import needed for CSSProperties type above
import type React from 'react'
```
**Issue:** The import is placed at the bottom of the file with an explanatory comment. While this works because TypeScript processes imports before execution, it violates the standard convention of placing imports at the top of the file. This was likely done intentionally to keep the data declarations prominent, but it may confuse code formatters or linters.
**Fix:** Move the import to the top of the file.

### P3-05: `useAuth` has stale ESLint dependency warning suppressed
**File:** `frontend/lib/hooks/useAuth.tsx`, line 248
**Code:**
```typescript
}, [])
```
**Issue:** The `useEffect` on line 140 has an empty dependency array, which means it runs only once on mount. This is intentional (it replaces `componentDidMount`), but React's exhaustive-deps ESLint rule would flag the missing dependencies (`API_URL`, store selectors, etc.). The lack of a `// eslint-disable-next-line` comment suggests either the rule is disabled project-wide or the deps are genuinely stable module-level constants.
**Fix:** Add a comment explaining why the empty deps are correct: `// eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only initialization`.

### P3-06: `getHeatingOilHistory` spread pattern inconsistent with other modules
**File:** `frontend/lib/api/heating-oil.ts`, line 67
**Code:**
```typescript
{ state, ...(weeks ? { weeks } : {}) },
```
**Issue:** This spread pattern for optional params is used in heating-oil, propane, and water modules, while other modules (gas-rates, prices, forecast) use explicit `if` checks. Both patterns work, but the inconsistency makes the codebase harder to audit.
**Fix:** Standardize on one pattern across all API modules.

### P3-07: Several hooks missing `'use client'` directive
**Files:** `frontend/lib/hooks/useForecast.ts`, `frontend/lib/hooks/useReports.ts`, `frontend/lib/hooks/useExport.ts`, `frontend/lib/hooks/useNeighborhood.ts`, `frontend/lib/hooks/useCombinedSavings.ts`
**Issue:** These hooks use `useQuery` from `@tanstack/react-query` which is a client-side API, but they lack the `'use client'` directive. In Next.js App Router, this works because the calling component is a client component, but it is best practice to mark all files that use React hooks with `'use client'` for clarity and to prevent accidental server-side imports.
**Fix:** Add `'use client'` to the top of each file.

### P3-08: `useSettingsStore` persist key is the old project name
**File:** `frontend/lib/store/settings.ts`, line 192
**Code:**
```typescript
name: 'electricity-optimizer-settings',
```
**Issue:** The localStorage key uses the old project name "electricity-optimizer" rather than the current brand "rateshift". While changing this would clear all existing user settings (a migration concern), it should be noted for any future localStorage cleanup.
**Fix:** Track as tech debt. If localStorage is ever migrated, rename to `'rateshift-settings'`.

### P3-09: `useCCADetect` enables query when either zipCode OR state is provided
**File:** `frontend/lib/hooks/useCCA.ts`, line 14
**Code:**
```typescript
enabled: !!zipCode || !!state,
```
**Issue:** If only `state` is provided but `zipCode` is undefined, the API call will be made with `zip_code: undefined`. The `detectCCA` function in `cca.ts` passes params directly, so `zip_code` would be omitted from the query string (since `apiClient.get` skips undefined values -- actually it doesn't, it would send `zip_code=undefined` as a string). This needs verification against the `apiClient.get` implementation.
**Fix:** Verify that `undefined` values in the params object are properly handled by `apiClient.get`. Currently, `Object.entries(params)` would include `zip_code: undefined`, and `String(undefined)` is `"undefined"`, which would be sent as a query param.

### P3-10: `ApiResponse<T>` in `types/index.ts` appears unused
**File:** `frontend/types/index.ts`, lines 221-226
**Issue:** The generic `ApiResponse<T>` wrapper type is defined but no API module uses it. All API functions return the unwrapped response type directly. This dead type adds confusion about the expected response shape.
**Fix:** Grep for usage; if unused, remove it.

---

## Files With No Issues Found

The following files were reviewed and found to be well-structured, properly typed, and free of notable issues:

- `frontend/lib/utils/cn.ts` -- Clean, minimal utility.
- `frontend/lib/utils/devGate.ts` -- Single-purpose, correct.
- `frontend/lib/api/profile.ts` -- Clean request/response types, proper signal forwarding.
- `frontend/lib/api/savings.ts` -- Minimal and correct.
- `frontend/lib/api/neighborhood.ts` -- Clean.
- `frontend/lib/api/affiliate.ts` -- Clean.
- `frontend/lib/api/portal.ts` -- Well-typed, proper signal handling.
- `frontend/lib/api/community.ts` -- Good type coverage.
- `frontend/lib/auth/client.ts` -- Minimal, correct SSR-safe pattern.
- `frontend/lib/notifications/onesignal.ts` -- Proper guard checks, lazy loading.
- `frontend/lib/hooks/useProfile.ts` -- Clean Zustand sync pattern.
- `frontend/lib/hooks/useSavings.ts` -- Proper retry config.
- `frontend/lib/hooks/useAlerts.ts` -- Good query key patterns.
- `frontend/lib/hooks/useNotifications.ts` -- Well-documented polling rationale.
- `frontend/lib/hooks/useOptimization.ts` -- Good queryKey stability patterns.
- `frontend/lib/hooks/useRateChanges.ts` -- Proper destructuring for queryKey stability.
- `frontend/lib/hooks/useGasRates.ts` -- Consistent patterns.
- `frontend/lib/hooks/useCombinedSavings.ts` -- Clean.
- `frontend/lib/hooks/useUtilityDiscovery.ts` -- Properly typed.
- `frontend/lib/hooks/useCommunitySolar.ts` -- Good input validation.
- `frontend/lib/contexts/toast-context.tsx` -- Proper cleanup, timer management.

---

## Summary

**Total findings:** 25 (3 P0, 7 P1, 12 P2, 10 P3)

**Critical themes:**

1. **Type safety gaps between hand-authored and generated types (P0-02, P1-07):** The dual type system for suppliers creates real mismatch risk. The `Supplier` type in `types/index.ts` is out of sync with the generated API types, and `getSupplier()` returns data typed as `Supplier` when the backend sends snake_case fields. The `api-helpers.ts` normalization layer is good but underutilized.

2. **Unsafe `undefined as T` cast (P0-01):** The 204 handling in `apiClient` lies to the type system. Any `delete` or `post` call that receives a 204 will get `undefined` typed as the expected response type.

3. **Circuit breaker bypass (P0-03):** Agent SSE calls bypass the circuit breaker, making the AI chat feature unreliable during gateway outages.

4. **HTML injection in email templates (P1-05):** User-controlled `name` field is interpolated into HTML emails without escaping.

5. **Inconsistent error handling in format utils (P1-06):** `formatTime` and `formatDate` throw on invalid input while `formatDateTime` gracefully degrades.

**Strengths:**

- The circuit breaker implementation is well-designed with proper state machine transitions, HALF_OPEN probing, and configurable thresholds.
- The 401 redirect loop prevention (counter + window + dedup flag) is thorough and well-documented.
- React Query hooks consistently use signal forwarding, proper `enabled` gates, and queryKey stability patterns.
- The `api-helpers.ts` normalization layer with `parseDecimal()` is a solid bridge between backend Decimal strings and frontend numbers.
- URL safety utilities (`isSafeRedirect`, `isSafeOAuthRedirect`) properly prevent open redirect attacks.
- The Zustand settings store uses SSR-safe storage with `satisfies Storage` pattern.
- The toast context has proper timer cleanup on unmount.
- Email sending has clean dual-provider fallback with proper error aggregation.
- Clarity analytics properly sanitizes the project ID to prevent XSS.
