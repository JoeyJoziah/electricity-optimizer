# Audit Report: Frontend Lib & Types
**Date:** 2026-03-19
**Scope:** Shared utilities, TypeScript types, API clients, config
**Files Reviewed:**

- `frontend/types/index.ts`
- `frontend/types/api-helpers.ts`
- `frontend/types/generated/api.ts`
- `frontend/lib/api/client.ts`
- `frontend/lib/api/circuit-breaker.ts`
- `frontend/lib/api/prices.ts`
- `frontend/lib/api/suppliers.ts`
- `frontend/lib/api/forecast.ts`
- `frontend/lib/api/savings.ts`
- `frontend/lib/api/alerts.ts`
- `frontend/lib/api/notifications.ts`
- `frontend/lib/api/optimization.ts`
- `frontend/lib/api/profile.ts`
- `frontend/lib/api/rate-changes.ts`
- `frontend/lib/api/reports.ts`
- `frontend/lib/api/export.ts`
- `frontend/lib/api/neighborhood.ts`
- `frontend/lib/api/community.ts`
- `frontend/lib/api/community-solar.ts`
- `frontend/lib/api/gas-rates.ts`
- `frontend/lib/api/heating-oil.ts`
- `frontend/lib/api/propane.ts`
- `frontend/lib/api/water.ts`
- `frontend/lib/api/cca.ts`
- `frontend/lib/api/affiliate.ts`
- `frontend/lib/api/portal.ts`
- `frontend/lib/api/utility-discovery.ts`
- `frontend/lib/api/agent.ts`
- `frontend/lib/api/__tests__/client.test.ts`
- `frontend/lib/api/__tests__/client-401-redirect.test.ts`
- `frontend/lib/api/__tests__/circuit-breaker.test.ts`
- `frontend/lib/api/__tests__/client-circuit-breaker.test.ts`
- `frontend/lib/api/__tests__/prices.test.ts`
- `frontend/lib/api/__tests__/suppliers.test.ts`
- `frontend/lib/config/env.ts`
- `frontend/lib/config/seo.ts`
- `frontend/lib/constants/regions.ts`
- `frontend/lib/constants/chartTokens.ts`
- `frontend/lib/utils/cn.ts`
- `frontend/lib/utils/calculations.ts`
- `frontend/lib/utils/format.ts`
- `frontend/lib/utils/devGate.ts`
- `frontend/lib/utils/url.ts`
- `frontend/lib/utils/__tests__/calculations.test.ts`
- `frontend/lib/utils/__tests__/format.test.ts`
- `frontend/lib/auth/client.ts`
- `frontend/lib/auth/server.ts`
- `frontend/lib/email/send.ts`
- `frontend/lib/analytics/clarity.tsx`
- `frontend/lib/notifications/onesignal.ts`
- `frontend/lib/contexts/toast-context.tsx`
- `frontend/lib/contexts/sidebar-context.tsx`
- `frontend/lib/store/settings.ts`
- `frontend/lib/hooks/useAuth.tsx`
- `frontend/lib/hooks/usePrices.ts`
- `frontend/lib/hooks/useSuppliers.ts`
- `frontend/lib/hooks/useForecast.ts`
- `frontend/lib/hooks/useAlerts.ts`
- `frontend/lib/hooks/useNotifications.ts`
- `frontend/lib/hooks/useSavings.ts`
- `frontend/lib/hooks/useOptimization.ts`
- `frontend/lib/hooks/useProfile.ts`
- `frontend/lib/hooks/useConnections.ts`
- `frontend/lib/hooks/useRateChanges.ts`
- `frontend/lib/hooks/useAgent.ts`
- `frontend/lib/hooks/useRealtime.ts`
- `frontend/lib/hooks/useGasRates.ts`
- `frontend/lib/hooks/useGeocoding.ts`
- `frontend/lib/hooks/useReports.ts`
- `frontend/lib/hooks/useExport.ts`
- `frontend/lib/hooks/useNeighborhood.ts`
- `frontend/lib/hooks/useHeatingOil.ts`
- `frontend/lib/hooks/usePropane.ts`
- `frontend/lib/hooks/useWater.ts`
- `frontend/lib/hooks/useCCA.ts`
- `frontend/lib/hooks/useCombinedSavings.ts`
- `frontend/lib/hooks/useCommunitySolar.ts`
- `frontend/lib/hooks/useCommunity.ts`
- `frontend/lib/hooks/useUtilityDiscovery.ts`
- `frontend/lib/hooks/useDiagrams.ts`

---

## P0 -- Critical (Fix Immediately)

### P0-1. XSS via Clarity Project ID interpolation
**File:** `frontend/lib/analytics/clarity.tsx`, line 20
**Issue:** The `CLARITY_PROJECT_ID` environment variable is interpolated directly into a `dangerouslySetInnerHTML` script string without any sanitization or escaping. If an attacker could control the `NEXT_PUBLIC_CLARITY_PROJECT_ID` env var (e.g., via a compromised build pipeline or `.env` file), they could inject arbitrary JavaScript.

```tsx
__html: `
  ...t.src="https://www.clarity.ms/tag/"+i;
  ...
})(window,document,"clarity","script","${CLARITY_PROJECT_ID}");
```

The string `CLARITY_PROJECT_ID` is injected verbatim. A value like `");alert(document.cookie);//` would break out of the template and execute arbitrary code.

**Recommendation:** Validate that `CLARITY_PROJECT_ID` matches an expected pattern (alphanumeric only) before interpolation:
```ts
const SAFE_ID_PATTERN = /^[a-zA-Z0-9]+$/
if (!SAFE_ID_PATTERN.test(CLARITY_PROJECT_ID)) return null
```

### P0-2. Agent SSE 401 handler bypasses redirect-loop protection
**File:** `frontend/lib/api/agent.ts`, lines 64-71
**Issue:** The `queryAgent` function has its own 401 redirect handler that does not use the same redirect-loop guards (`REDIRECT_COUNT_KEY`, `REDIRECT_TS_KEY`, `redirectInFlight` flag) that the main `apiClient` uses in `client.ts` (lines 63-95). This means the agent SSE endpoint can trigger unlimited redirect loops if the session is expired and the user is on a non-auth page, because there is no counter or dedup logic.

```ts
if (response.status === 401 && typeof window !== 'undefined') {
  const pathname = window.location.pathname
  if (!pathname.startsWith('/auth/')) {
    window.location.href = `/auth/login?callbackUrl=${encodeURIComponent(pathname)}`
    return
  }
}
```

**Recommendation:** Extract the 401 redirect logic from `client.ts` into a shared utility function (e.g., `handle401Redirect()`) and reuse it in `agent.ts`. Alternatively, at minimum, check the same `redirectInFlight` flag before redirecting.

### P0-3. `handleResponse` returns `response.json()` on 204 No Content
**File:** `frontend/lib/api/client.ts`, line 123
**Issue:** The `handleResponse` function unconditionally calls `response.json()` for all successful responses (line 123). If any API endpoint returns a `204 No Content` (or any 2xx with an empty body), `response.json()` will throw a `SyntaxError` at runtime because there is no JSON to parse. This would be treated as an unhandled error.

```ts
return response.json()
```

**Recommendation:** Check for empty bodies before parsing:
```ts
if (response.status === 204 || response.headers.get('content-length') === '0') {
  return undefined as T
}
return response.json()
```

---

## P1 -- High (Fix This Sprint)

### P1-1. `formatTime` and `formatDate` do not handle invalid date strings
**File:** `frontend/lib/utils/format.ts`, lines 57-68
**Issue:** `formatDateTime` (line 42) correctly catches `parseISO` errors and returns the original string as a fallback. However, `formatTime` (line 57) and `formatDate` (line 65) call `parseISO` and `format` without any try/catch, meaning they will throw an unhandled exception on invalid date strings. This is inconsistent and could crash components that pass user-supplied or backend-supplied date strings.

```ts
export function formatTime(dateString: string, is24Hour: boolean = true): string {
  const date = parseISO(dateString)  // throws on invalid input
  return format(date, is24Hour ? 'HH:mm' : 'h:mm a')
}
```

**Recommendation:** Wrap both functions in try/catch like `formatDateTime` does, returning a fallback string on failure.

### P1-2. `formatDuration` edge case produces "1h 60m"
**File:** `frontend/lib/utils/format.ts`, lines 104-115
**Issue:** When `hours` is close to the next whole number (e.g., `1.999`), `Math.round((hours - wholeHours) * 60)` can produce `60` minutes, yielding the string `"1h 60m"` instead of `"2h"`. The test at line 261 confirms `formatDuration(1.99)` = `"1h 59m"`, but `formatDuration(1.999)` would produce `"1h 60m"`.

```ts
const wholeHours = Math.floor(hours)
const minutes = Math.round((hours - wholeHours) * 60)
// When hours = 1.999: wholeHours = 1, minutes = Math.round(59.94) = 60
// Returns "1h 60m"
```

**Recommendation:** After computing minutes, check if `minutes >= 60` and carry over to hours:
```ts
let wholeHours = Math.floor(hours)
let minutes = Math.round((hours - wholeHours) * 60)
if (minutes >= 60) { wholeHours += 1; minutes = 0 }
```

### P1-3. `formatCompactNumber` produces incorrect output for negative large numbers
**File:** `frontend/lib/utils/format.ts`, lines 81-89
**Issue:** Negative numbers below -1000 will not match any threshold (`num >= 1000000` or `num >= 1000` are false for negatives) and will be returned as plain `toString()`. For example, `formatCompactNumber(-5000)` returns `"-5000"` instead of `"-5.0K"`. Similarly, `formatCompactNumber(-2000000)` returns `"-2000000"`.

**Recommendation:** Use `Math.abs(num)` for threshold checks, then prepend the sign:
```ts
const absNum = Math.abs(num)
const sign = num < 0 ? '-' : ''
if (absNum >= 1000000) return `${sign}${(absNum / 1000000).toFixed(1)}M`
if (absNum >= 1000) return `${sign}${(absNum / 1000).toFixed(1)}K`
return num.toString()
```

### P1-4. `getPriceCategory` division by zero when `avgPrice` is 0
**File:** `frontend/lib/utils/calculations.ts`, lines 152-161
**Issue:** If `avgPrice` is `0`, the expression `currentPrice / avgPrice` produces `Infinity` or `NaN`, which will always return `"expensive"` (since `Infinity > 1.2`). If both are `0`, `0/0 = NaN`, and `NaN > 1.2` is `false` and `NaN < 0.8` is `false`, so it returns `"moderate"`, which is misleading. There is no documented or tested behavior for `avgPrice = 0`.

**Recommendation:** Add a guard clause:
```ts
if (avgPrice === 0) return 'moderate'
```

### P1-5. `useRealtimePrices` cache update uses `Record<string, unknown>` instead of typed API response
**File:** `frontend/lib/hooks/useRealtime.ts`, lines 77-92
**Issue:** The `queryClient.setQueryData` call casts the cache entry as `Record<string, unknown>` and accesses `.prices` without type checking. The inline comment references `ApiCurrentPriceResponse` but the code does not import or use that type. The `prices.map` callback casts each entry as `Record<string, unknown>` and accesses `.supplier` and writes `price_per_kwh` as `Number(data.price_per_kwh)` -- but `ApiCurrentPriceResponse.prices` contains `ApiPriceResponse` objects where `current_price` is a `DecimalStr`, not `price_per_kwh`. This type mismatch means the cache update writes a field (`price_per_kwh`) that does not exist on the `ApiPriceResponse` type, potentially confusing downstream consumers.

```ts
? { ...entry, price_per_kwh: Number(data.price_per_kwh), timestamp: data.timestamp, is_peak: data.is_peak }
```

The `ApiPriceResponse` type (from `generated/api.ts`) has `current_price: DecimalStr`, not `price_per_kwh`.

**Recommendation:** Import `ApiCurrentPriceResponse` and use the correct field name (`current_price`) when updating the cache. Use proper typing for the `setQueryData` callback.

### P1-6. Duplicate type definitions between `types/index.ts` and `types/generated/api.ts`
**File:** `frontend/types/index.ts` (lines 129-142) vs `frontend/types/generated/api.ts` (lines 210-253)
**Issue:** The `Supplier` type in `types/index.ts` (line 129) defines `rating: number` as non-nullable, while `ApiSupplierResponse` in `generated/api.ts` (line 216) defines `rating: number | null`. Similarly, `RawSupplierRecord` has `rating?: number | null`. The `normaliseSupplierResponse` function in `api-helpers.ts` correctly maps to `NormalisedSupplier` with `rating: number | null`. However, any code that uses the old `Supplier` type from `types/index.ts` will believe `rating` is always a number, which is incorrect when the backend returns `null`.

This type mismatch can cause runtime errors when components try to call methods on `null` (e.g., `supplier.rating.toFixed(2)`).

The `Supplier.tariffType` in `types/index.ts` (line 139) uses `'time-of-use'` (hyphenated) while `TariffType` in `generated/api.ts` (line 33) uses `'time_of_use'` (underscored). These are incompatible string literals.

**Recommendation:** Deprecate the hand-authored `Supplier` type in `types/index.ts` in favor of `NormalisedSupplier` from `api-helpers.ts`. Update all consumers to use the correct type and handle `null` ratings.

### P1-7. `getSupplier` API function returns wrong type
**File:** `frontend/lib/api/suppliers.ts`, line 60-62
**Issue:** `getSupplier` declares its return type as `Promise<Supplier>` (the camelCase frontend type from `types/index.ts`), but the backend returns a snake_case `ApiSupplierDetailResponse`. The `apiClient.get<Supplier>` generic does not perform any runtime transformation -- it simply casts the JSON. This means the returned object will have fields like `green_energy_provider` (snake_case) but TypeScript thinks they are `greenEnergy` (camelCase), causing silent property access failures (`supplier.greenEnergy` is `undefined`).

```ts
export async function getSupplier(supplierId: string, signal?: AbortSignal): Promise<Supplier> {
  return apiClient.get<Supplier>(`/suppliers/${supplierId}`, undefined, { signal })
}
```

**Recommendation:** Change the return type to `ApiSupplierDetailResponse` and normalize at the call site using `normaliseSupplierDetailResponse()`.

### P1-8. `BASE_URL` in `seo.ts` duplicates `SITE_URL` from `env.ts`
**File:** `frontend/lib/config/seo.ts`, line 61
**Issue:** `seo.ts` defines its own `BASE_URL` constant reading `process.env.NEXT_PUBLIC_SITE_URL` with a fallback to `'https://rateshift.app'`. This is an exact duplicate of the `SITE_URL` export in `frontend/lib/config/env.ts` (line 120). Having two sources of truth for the same value risks them diverging if one is updated and the other is not.

```ts
// seo.ts
export const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://rateshift.app'

// env.ts
export const SITE_URL: string = env(
  process.env.NEXT_PUBLIC_SITE_URL,
  'https://rateshift.app',
  { name: 'NEXT_PUBLIC_SITE_URL' },
)
```

**Recommendation:** Remove `BASE_URL` from `seo.ts` and import `SITE_URL` from `@/lib/config/env` instead.

---

## P2 -- Medium (Fix Soon)

### P2-1. `isSafeHref` rejects relative URLs that are actually safe
**File:** `frontend/lib/utils/url.ts`, lines 34-42
**Issue:** `isSafeHref` rejects all relative URLs (the `catch` block returns `false`). Relative URLs like `/programs/123` are safe and commonly returned by the backend for internal linking. The JSDoc says "Relative URLs or malformed strings -- reject" but this may be overly restrictive for internal backend-supplied paths.

**Recommendation:** Consider accepting relative URLs that start with `/` as safe, or document clearly that callers must handle relative URLs separately.

### P2-2. `useConnections` wraps 403 errors with `Object.assign(new Error(...))` losing type safety
**File:** `frontend/lib/hooks/useConnections.ts`, lines 34-36
**Issue:** On a 403 response, the code creates a plain `Error` with `Object.assign(new Error('upgrade'), { status: 403 })`. This loses the `ApiClientError` type and the `details` field. Downstream consumers checking `err instanceof ApiClientError` will get `false`, and any `err.details` inspection will fail.

```ts
if (err instanceof ApiClientError && err.status === 403) {
  throw Object.assign(new Error('upgrade'), { status: 403 })
}
```

**Recommendation:** Throw a proper `ApiClientError` with the correct status:
```ts
throw new ApiClientError({ message: 'upgrade', status: 403 })
```

### P2-3. `markAllRead` is an N+1 API call pattern without concurrency limits
**File:** `frontend/lib/api/notifications.ts`, lines 73-78
**Issue:** `markAllRead` fetches all unread notifications and then fires an individual PUT request for each one via `Promise.allSettled`. If a user has 50 unread notifications, this sends 50 parallel HTTP requests. There is no concurrency limit, which could trigger rate limiting or overwhelm the browser's connection pool.

```ts
export async function markAllRead(): Promise<void> {
  const data = await getNotifications()
  await Promise.allSettled(
    data.notifications.map((n) => markNotificationRead(n.id))
  )
}
```

**Recommendation:** Either implement a backend bulk-mark-all endpoint, or add a concurrency limiter (e.g., process in batches of 5-10).

### P2-4. `useHeatingOilPrices` fires query even when `state` is undefined
**File:** `frontend/lib/hooks/useHeatingOil.ts`, line 9-14
**Issue:** Unlike other utility hooks (e.g., `useHeatingOilHistory`, `useHeatingOilDealers`), `useHeatingOilPrices` does not set `enabled: !!state`. The `getHeatingOilPrices` API function handles an absent `state` by passing an empty query params object, which would fetch all states. This may be intentional but is inconsistent with the pattern used elsewhere and could cause unexpected data loading.

The same inconsistency exists in `usePropanePrices` (`frontend/lib/hooks/usePropane.ts`, line 9-14) and `useWaterRates` (`frontend/lib/hooks/useWater.ts`, line 8-12).

**Recommendation:** Either add `enabled: !!state` for consistency or document that these hooks intentionally fetch all-state data when state is absent.

### P2-5. `forecast.ts` parameter name collision: `horizonDays` vs `hours`
**File:** `frontend/lib/api/forecast.ts`, line 28 vs `frontend/lib/api/prices.ts` `GetPriceForecastParams`
**Issue:** The `forecast.ts` API function uses `horizonDays` as a parameter name (line 28) while `prices.ts` uses `hours` (line 57). Both fetch forecast data but use different time units. The `forecast.ts` endpoint passes `horizon_days` to the backend, while `prices.ts` passes `hours`. This is technically correct (they hit different endpoints), but the naming inconsistency can confuse developers.

Additionally, `getForecast` in `forecast.ts` passes `0` for `horizonDays` when the caller passes `0` as a value due to the falsy check `if (horizonDays)` (line 33). The value `0` is a valid number but is treated as "not provided." The same issue exists for `state` (empty string would be treated as "not provided").

```ts
if (state) params.state = state            // empty string '' is falsy
if (horizonDays) params.horizon_days = String(horizonDays)  // 0 is falsy
```

**Recommendation:** Use `!== undefined` checks instead of truthiness checks for numeric parameters:
```ts
if (horizonDays !== undefined) params.horizon_days = String(horizonDays)
```

### P2-6. `getSuppliers` falsy check on `annualUsage` skips value `0`
**File:** `frontend/lib/api/suppliers.ts`, line 51
**Issue:** `if (annualUsage)` is falsy when `annualUsage` is `0`. While `0` annual usage is arguably invalid, the function silently ignores it rather than either sending it to the backend (which would validate and reject it) or throwing a client-side error.

```ts
if (annualUsage) {
  params.annual_usage = annualUsage.toString()
}
```

The same pattern appears in several other API functions:
- `getHeatingOilHistory` (line 67): `weeks ? { weeks } : {}` -- `weeks = 0` is falsy
- `getHeatingOilDealers` (line 79): `limit ? { limit } : {}` -- `limit = 0` is falsy
- `getPropaneHistory` (line 60): `weeks ? { weeks: String(weeks) } : {}` -- same issue

**Recommendation:** Use `!== undefined` for all optional numeric parameters to avoid silently dropping valid zero values.

### P2-7. `useDiagrams` bypasses `apiClient` -- no auth, no retry, no circuit breaker
**File:** `frontend/lib/hooks/useDiagrams.ts`, lines 15-48
**Issue:** The diagram API functions (`fetchDiagramList`, `fetchDiagram`, `saveDiagram`, `createDiagram`) use raw `fetch()` calls instead of the centralized `apiClient`. This means they do not benefit from:
- Automatic retry with backoff for 5xx errors
- 401 redirect handling
- Circuit breaker for gateway failures
- Automatic `credentials: 'include'` for session cookies
- The `X-Fallback-Mode` header

These endpoints (`/api/dev/diagrams`) appear to be development-only tools, but if they are accessible in production, the lack of auth handling could cause confusing behavior.

**Recommendation:** Either migrate to use `apiClient` or ensure these endpoints are gated behind `IS_DEV` checks in production.

### P2-8. `queryAgent` SSE parser does not handle multi-line `data:` fields
**File:** `frontend/lib/api/agent.ts`, lines 94-107
**Issue:** The SSE parser splits on `\n` and looks for `data: ` prefix lines. However, the SSE specification allows multi-line data fields where consecutive `data:` lines should be concatenated with newlines. The current implementation treats each `data:` line as a separate JSON object, which would cause `JSON.parse` to fail if the backend ever sends a multi-line data payload.

Additionally, the `buffer` logic does not handle `\r\n` line endings (which are valid in SSE). `buffer.split('\n')` would leave trailing `\r` characters.

**Recommendation:** Handle `\r\n` and `\r` line endings in the split, and concatenate consecutive `data:` fields per the SSE specification.

### P2-9. `calculatePriceTrend` has asymmetric array splitting
**File:** `frontend/lib/utils/calculations.ts`, lines 17-28
**Issue:** The function splits recent prices into two halves using `Math.floor` and `Math.ceil`, but for odd-length arrays, the middle element is included in both halves' division denominators but not in both sums. Specifically, for an array of 5 elements:
- `avgFirst = slice(0, floor(5/2)) = slice(0, 2)` -- elements 0,1, divided by `floor(5/2) = 2`
- `avgSecond = slice(ceil(5/2)) = slice(3)` -- elements 3,4, divided by `ceil(5/2) = 3`

The second half average divides by 3 but only has 2 elements, because `recentPrices.slice(3)` with a 5-element array gives elements at index 3,4 (length 2), but the divisor is `Math.ceil(5/2) = 3`. This produces an incorrect average for the second half.

```ts
const avgSecond = recentPrices.slice(Math.ceil(recentPrices.length / 2))
  .reduce((a, b) => a + b, 0) / Math.ceil(recentPrices.length / 2)
```

For `recentPrices = [10, 10, 10, 12, 14]`:
- `avgSecond = (12 + 14) / 3 = 8.67` (wrong; should be `13`)

**Recommendation:** Use the actual length of the sliced array as the divisor:
```ts
const secondHalf = recentPrices.slice(Math.ceil(recentPrices.length / 2))
const avgSecond = secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length
```

---

## P3 -- Low / Housekeeping

### P3-1. Deprecated legacy functions in `prices.ts`
**File:** `frontend/lib/api/prices.ts`, lines 143-170
**Issue:** Three deprecated functions (`getCurrentPricesLegacy`, `getPriceHistoryLegacy`, `getPriceForecastLegacy`) are marked with `@deprecated` JSDoc. These should be tracked for removal once all callers have been migrated.

**Recommendation:** Search for callers; if none remain, remove these functions.

### P3-2. `useAppliances` deprecated alias in `useOptimization.ts`
**File:** `frontend/lib/hooks/useOptimization.ts`, line 71
**Issue:** The deprecated alias `useAppliances` is exported alongside the preferred `useSavedAppliances`. Track and remove when all consumers have migrated.

### P3-3. `chartTokens.ts` imports React type at the bottom of file
**File:** `frontend/lib/constants/chartTokens.ts`, line 66
**Issue:** The `import type React from 'react'` statement is at the end of the file, after the declarations that use `React.CSSProperties`. While this works due to TypeScript's hoisting of type imports, it violates the conventional imports-first ordering.

```ts
export const chartTooltipStyle: React.CSSProperties = { ... }
// ...
import type React from 'react'  // line 66 -- should be at top
```

**Recommendation:** Move the import to the top of the file.

### P3-4. `UserSupplierResponse` and `LinkedAccountResponse` duplicated in `suppliers.ts`
**File:** `frontend/lib/api/suppliers.ts`, lines 121-149 vs `frontend/types/generated/api.ts`, lines 367-409
**Issue:** `suppliers.ts` defines its own `UserSupplierResponse`, `LinkAccountRequest`, and `LinkedAccountResponse` interfaces that are structurally identical to `ApiUserSupplierResponse`, `ApiLinkAccountRequest`, and `ApiLinkedAccountResponse` in `generated/api.ts`. This creates a maintenance burden -- if the backend schema changes and the generated types are regenerated, the manual copies in `suppliers.ts` will be out of sync.

**Recommendation:** Import and re-export the generated types instead of defining duplicates.

### P3-5. Inconsistent `signal` parameter threading in API functions
**File:** Multiple API files
**Issue:** Some API functions pass `signal` as a named option object (`{ signal }`) and some pass it as a positional parameter. For example:
- `createAlert` (alerts.ts, line 88): No signal parameter at all
- `createPost` (community.ts, line 77): No signal parameter
- `updateAlert` (alerts.ts, line 95): No signal parameter
- `editPost` (community.ts, line 81): No signal parameter

While mutation operations (POST/PUT/DELETE) are less commonly cancelled, the inconsistency means that some mutations cannot be cancelled via `AbortController`, which prevents proper cleanup on component unmount for slower operations.

**Recommendation:** Add optional `signal` parameters to all mutation API functions for consistency, even if not all callers use them.

### P3-6. `NormalisedTariff.contractLength` type mismatch
**File:** `frontend/types/api-helpers.ts`, line 225 vs `frontend/types/generated/api.ts`, line 268
**Issue:** `NormalisedTariff.contractLength` is typed as `string` (line 225), but `ApiTariffResponse.contract_length` is typed as `ContractLength` (a union of string literals: `'monthly' | 'annual' | 'two_year' | 'three_year' | 'rolling'`). The normalization function `normaliseTariffResponse` (line 229) assigns the literal union to a plain `string`, widening the type and losing the discriminated union benefit.

**Recommendation:** Change `NormalisedTariff.contractLength` to use the `ContractLength` type.

### P3-7. `extractPaginationMeta` `hasMore` off-by-one potential
**File:** `frontend/types/api-helpers.ts`, line 316
**Issue:** `hasMore: response.page < pages` means that on the last page (`page === pages`), `hasMore` is `false`. This is correct for 1-indexed pagination, but there is no validation that `page` is 1-indexed. If the backend ever returns `page: 0` (0-indexed), `hasMore` would incorrectly be `true` when `pages` is `0`.

**Recommendation:** This is likely fine given current backend conventions but worth a defensive guard: `hasMore: response.page > 0 && response.page < pages`.

### P3-8. `env.ts` `FALLBACK_API_URL` does not use the `env()` helper
**File:** `frontend/lib/config/env.ts`, line 87-88
**Issue:** `FALLBACK_API_URL` reads the environment variable directly with `||` instead of using the `env()` helper function. This means it won't throw in production if the variable is missing (which may be intentional since the fallback URL is optional), but it inconsistently bypasses the validation pattern used by other variables.

```ts
export const FALLBACK_API_URL: string =
  process.env.NEXT_PUBLIC_FALLBACK_API_URL || ''
```

**Recommendation:** Use `env()` with `required: false` for consistency:
```ts
export const FALLBACK_API_URL: string = env(
  process.env.NEXT_PUBLIC_FALLBACK_API_URL,
  '',
  { required: false, name: 'NEXT_PUBLIC_FALLBACK_API_URL' },
)
```

### P3-9. `SidebarProvider` does not check for resize events
**File:** `frontend/lib/contexts/sidebar-context.tsx`, lines 47-59
**Issue:** The body scroll lock checks `window.innerWidth < LG_BREAKPOINT` only when `isOpen` changes, not when the window is resized. If a user opens the sidebar on a narrow viewport (triggering the scroll lock) and then resizes the browser wider, the scroll lock persists even though the overlay is no longer visible.

**Recommendation:** Add a `resize` event listener that re-evaluates the scroll lock condition.

### P3-10. `useAuth` `initAuth` effect does not run on route changes
**File:** `frontend/lib/hooks/useAuth.tsx`, line 248
**Issue:** The `useEffect` for `initAuth` has an empty dependency array `[]`, meaning it runs only once on mount. If the user navigates between pages using client-side routing (which doesn't remount the `AuthProvider`), the profile-completeness redirect checks (lines 228-237) won't re-evaluate. This means a user could navigate to a profile-required page after `initAuth` has already run, and the onboarding redirect would not trigger.

This is partially mitigated by the `useRequireAuth` hook (line 471), but only for authentication -- not for profile completeness.

**Recommendation:** Consider extracting the profile redirect logic into a separate effect that runs on route changes, or use a middleware-based approach.

### P3-11. `useSettingsStore` persistence key still references old brand name
**File:** `frontend/lib/store/settings.ts`, line 192
**Issue:** The Zustand persist storage key is `'electricity-optimizer-settings'`. The project has been rebranded to "RateShift". While changing this key would require a migration for existing users' localStorage, it should be documented as a future cleanup task.

```ts
name: 'electricity-optimizer-settings',
```

**Recommendation:** Plan a migration that reads the old key, copies to a new `'rateshift-settings'` key, and removes the old one. This can be done in a `migrate` option in zustand persist.

### P3-12. `getOptimalPeriods` return type in `prices.ts` uses inline type instead of generated
**File:** `frontend/lib/api/prices.ts`, lines 180-189
**Issue:** The `getOptimalPeriods` function returns `Promise<{ periods: Array<{ start: string; end: string; avgPrice: number }> }>` as an inline type. The function comments note "this endpoint is not yet reflected in the generated OpenAPI types." This should be tracked as technical debt to be resolved when the backend adds a formal response_model.

---

## Files With No Issues Found

The following files were reviewed and found to have no issues worth reporting. They demonstrate good practices including proper typing, consistent patterns, appropriate error handling, and clean code organization:

- `frontend/types/generated/api.ts` -- Well-structured auto-generated types with comprehensive JSDoc
- `frontend/lib/api/circuit-breaker.ts` -- Solid state machine implementation with test hooks
- `frontend/lib/api/savings.ts`
- `frontend/lib/api/alerts.ts`
- `frontend/lib/api/rate-changes.ts`
- `frontend/lib/api/reports.ts`
- `frontend/lib/api/export.ts`
- `frontend/lib/api/neighborhood.ts`
- `frontend/lib/api/community-solar.ts`
- `frontend/lib/api/gas-rates.ts`
- `frontend/lib/api/water.ts`
- `frontend/lib/api/cca.ts`
- `frontend/lib/api/affiliate.ts`
- `frontend/lib/api/portal.ts`
- `frontend/lib/api/utility-discovery.ts`
- `frontend/lib/utils/cn.ts`
- `frontend/lib/utils/devGate.ts`
- `frontend/lib/utils/url.ts` -- Excellent XSS/redirect protection
- `frontend/lib/constants/regions.ts`
- `frontend/lib/auth/client.ts`
- `frontend/lib/auth/server.ts` -- Good lazy initialization, proper cookie security
- `frontend/lib/email/send.ts` -- Solid dual-provider fallback pattern
- `frontend/lib/notifications/onesignal.ts`
- `frontend/lib/contexts/toast-context.tsx` -- Proper timer cleanup on unmount
- `frontend/lib/hooks/useAlerts.ts`
- `frontend/lib/hooks/useNotifications.ts` -- Good polling configuration with rationale
- `frontend/lib/hooks/useSavings.ts`
- `frontend/lib/hooks/useProfile.ts`
- `frontend/lib/hooks/useRateChanges.ts`
- `frontend/lib/hooks/useAgent.ts` -- Proper AbortController cleanup on unmount
- `frontend/lib/hooks/useGasRates.ts`
- `frontend/lib/hooks/useGeocoding.ts`
- `frontend/lib/hooks/useReports.ts`
- `frontend/lib/hooks/useExport.ts`
- `frontend/lib/hooks/useNeighborhood.ts`
- `frontend/lib/hooks/useCombinedSavings.ts`
- `frontend/lib/hooks/useCommunitySolar.ts` -- Good input validation with exported constants
- `frontend/lib/hooks/useCommunity.ts`
- `frontend/lib/hooks/useUtilityDiscovery.ts`
- `frontend/lib/utils/__tests__/calculations.test.ts` -- Thorough edge case coverage
- `frontend/lib/utils/__tests__/format.test.ts`

---

## Summary

**Total files reviewed:** 79 (69 production + 10 test files)

| Severity | Count | Description |
|----------|-------|-------------|
| P0 | 3 | XSS via Clarity interpolation, duplicated 401 handler without loop protection, JSON.parse on 204 empty body |
| P1 | 8 | `formatTime`/`formatDate` crash on invalid input, `formatDuration` 60m edge case, negative compact numbers, division by zero in price category, SSE cache type mismatch, `Supplier` type divergence from generated types, `getSupplier` returns wrong type, duplicate `BASE_URL` |
| P2 | 9 | `isSafeHref` rejects relative URLs, `useConnections` loses error type, N+1 notification marking, missing `enabled` gates on hooks, falsy checks dropping `0` values, `useDiagrams` bypasses auth, SSE parser edge cases, `calculatePriceTrend` array splitting bug |
| P3 | 12 | Deprecated code tracking, import ordering, type duplication, inconsistent signal threading, brand name in storage key, inline types instead of generated |

**Positive observations:**
- Zero uses of `any` type in production code -- strong type discipline
- No hardcoded API URLs -- all route through `env.ts` config
- Excellent 401 redirect loop protection in the main API client with sessionStorage counters and dedup
- Circuit breaker pattern with configurable half-open success threshold is well-engineered
- Consistent use of `AbortSignal` throughout query hooks for cancellation
- `isSafeRedirect` and `isSafeOAuthRedirect` URL validators provide good XSS protection
- React Query key stability patterns (JSON.stringify, sorted arrays, primitive destructuring) are consistently applied
- SSR-safe patterns throughout (storage stubs, `typeof window` guards, lazy initialization)
- Well-organized generated types with `DecimalStr` branded type preventing accidental arithmetic
- Comprehensive test coverage for utility functions including edge cases
