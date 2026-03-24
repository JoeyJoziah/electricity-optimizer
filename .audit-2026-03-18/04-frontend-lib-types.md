# Audit Report: Frontend Shared Utilities, Types, and Configuration
## Date: 2026-03-18
## Auditor: typescript-pro (Claude Sonnet 4.6)

### Scope

Files audited (47 total — every `.ts` / `.tsx` file in scope):

**`frontend/lib/utils/`** — calculations.ts, cn.ts, devGate.ts, format.ts, url.ts (+ 2 test files)
**`frontend/lib/config/`** — env.ts, seo.ts
**`frontend/lib/constants/`** — chartTokens.ts, regions.ts
**`frontend/lib/analytics/`** — clarity.tsx
**`frontend/lib/email/`** — send.ts
**`frontend/lib/notifications/`** — onesignal.ts
**`frontend/types/`** — index.ts, api-helpers.ts, generated/api.ts
**`frontend/lib/api/`** — affiliate.ts, agent.ts, alerts.ts, cca.ts, circuit-breaker.ts, client.ts, community-solar.ts, community.ts, export.ts, forecast.ts, gas-rates.ts, heating-oil.ts, neighborhood.ts, notifications.ts, optimization.ts, portal.ts, prices.ts, profile.ts, propane.ts, rate-changes.ts, reports.ts, savings.ts, suppliers.ts, utility-discovery.ts, water.ts (+ 5 test files)

---

### Executive Summary

The frontend library layer is in solid shape overall. The generated API types (`types/generated/api.ts`) align well with the backend Pydantic models for the core pricing and supplier surfaces. The `apiClient` implementation has well-tested retry logic, circuit breaking, and 401 redirect protection. The utility functions are clean and well-tested (calculations and format have comprehensive test suites).

The most significant findings are: (1) a **hard type mismatch** between `TariffType` in `generated/api.ts` (`time_of_use`) and `Supplier` in `types/index.ts` (`time-of-use`) that can silently break supplier filtering and rendering; (2) **`water` is absent from the `UtilityType` enum** in `generated/api.ts` despite having a live API client (`lib/api/water.ts`) and backend support; (3) **three format utility functions lack error handling for invalid date strings** and will throw uncaught exceptions at runtime; (4) **`lib/config/seo.ts` duplicates `NEXT_PUBLIC_SITE_URL` access** instead of importing from `env.ts`, creating a maintenance split; (5) **the agent SSE function bypasses `apiClient` entirely**, losing circuit-breaker, retry, and 401-redirect guarantees; (6) **`UserSettings` in `types/index.ts` is a diverged dead type** no longer matching the actual backend user profile shape. Eleven medium/low-severity issues round out the report.

---

### Findings

---

#### P0 — Critical

No P0 findings. No SQL injection vectors, no XSS sinks, no credential exposure found in this layer.

---

#### P1 — High

**[P1-01] TariffType value mismatch between `types/index.ts` and `generated/api.ts` — silent runtime breakage**

- **Files**: `frontend/types/index.ts:88,139` and `frontend/types/generated/api.ts:33`
- **Detail**: `types/index.ts` defines `Supplier.tariffType` as `'fixed' | 'variable' | 'time-of-use'` (hyphen). The generated type `TariffType` in `generated/api.ts` (which derives from the backend Python enum) uses `'time_of_use'` (underscore). These are different string literals. Any code that receives a backend `TariffType.time_of_use` value and assigns it to a `Supplier` typed field (as done in `suppliers.ts` via `RawSupplierRecord.tariffType`) will produce TypeScript values that do not match the union — conditional rendering branches like `tariffType === 'time-of-use'` will silently never match for time-of-use tariffs received from the backend. The mismatch also means the normalization mappers in `api-helpers.ts` cannot bridge this gap because `NormalisedTariff.type` correctly uses `TariffType` (underscore) while the old `Supplier` type uses the hyphen variant.
- **Risk**: Silent feature regression — time-of-use tariff cards/badges will not render correctly. TypeScript does not catch this because `RawSupplierRecord.tariffType` is typed with the hyphen variant, masking the mismatch from the compiler.
- **Fix**: Reconcile the two types. Options: (a) delete `Supplier.tariffType` from `index.ts` and replace all usages with `NormalisedSupplier` + `NormalisedTariff`; (b) update `types/index.ts` Supplier to use `TariffType` from generated types; (c) add a normalizer that maps `'time_of_use'` → `'time-of-use'` explicitly in `RawSupplierRecord`.

---

**[P1-02] `UtilityType` enum in `generated/api.ts` is missing `water`**

- **File**: `frontend/types/generated/api.ts:51-57`
- **Detail**: The `UtilityType` union type lists `'electricity' | 'natural_gas' | 'heating_oil' | 'propane' | 'community_solar'` but omits `'water'`. The backend has a complete water API (`/rates/water`) with its own live client module (`frontend/lib/api/water.ts`) and backend endpoints. The `lib/api/water.ts` types do not reference `UtilityType` at all — they use bare `string` types for `unit` — but `lib/constants/regions.ts` in `UTILITY_TYPES` also omits water (only `electricity`, `natural_gas`, `heating_oil`, `propane`, `water` appears in `lib/config/seo.ts` via `UTILITY_TYPES`). The generated type is stale relative to the live codebase.
- **Risk**: Any code that validates against `UtilityType` (e.g. `switch` statements, API contract checkers) will treat water responses as invalid. If `ApiPrice.utility_type` is typed as `UtilityType`, TypeScript will flag water price records as errors when the type regeneration script is eventually run.
- **Fix**: Add `'water'` to `UtilityType` in `generated/api.ts`. Also add `water` to `lib/constants/regions.ts` `UTILITY_TYPES` record (currently absent). Regenerate types from the OpenAPI spec.

---

**[P1-03] `format.ts` — three date format functions throw uncaught exceptions on invalid input**

- **File**: `frontend/lib/utils/format.ts:57-76`
- **Detail**: `formatTime` (line 58) and `formatDate` (line 66) and `formatRelativeTime` (line 74) call `parseISO(dateString)` and then immediately call `format()` or `formatDistanceToNow()` without a try/catch. `parseISO` on an invalid string returns an `Invalid Date` object (not an exception), but `date-fns/format` called with `Invalid Date` **throws a `RangeError: Invalid time value`** at runtime. Only `formatDateTime` (line 43-52) has a try/catch. Calling `formatTime('')`, `formatDate('bad-date')`, or `formatRelativeTime('not-a-date')` will throw an unhandled exception that, if not caught by a React error boundary, crashes the component tree.
- **Risk**: Production crash. Any component that calls these functions with data from an API response (where a missing timestamp field could be `null`, `undefined`, or an empty string coerced to string) will throw.
- **Mitigation in tests**: The `format.test.ts` file tests `formatDateTime` with an invalid date but does NOT test `formatTime`, `formatDate`, or `formatRelativeTime` with invalid inputs — the regression is uncovered.
- **Fix**: Wrap all three in the same try/catch pattern as `formatDateTime`. Alternatively, add a shared `safeParseISO` helper that returns `null` on invalid input and handle `null` in each formatter.

---

**[P1-04] `agent.ts` — SSE `queryAgent` bypasses `apiClient`, losing circuit-breaker, retry, and 401 protections**

- **File**: `frontend/lib/api/agent.ts:55-109`
- **Detail**: `queryAgent` makes a raw `fetch()` call directly to `${API_URL}/agent/query` (line 55) instead of going through `apiClient`. This means: (1) the circuit breaker is never consulted, so if the CF Worker gateway goes down, SSE agent requests continue hitting the dead primary URL instead of switching to the Render fallback; (2) the exponential-backoff retry logic (MAX_RETRIES=2, RETRY_BASE_MS=500) is not applied; (3) the 401 redirect loop counter and deduplication (`redirectInFlight`) in `handleResponse` are bypassed — the manual 401 handler at line 65-70 is a simplified reinvention that does not preserve the `callbackUrl` extraction logic, does not check `isSafeRedirect`, and does not enforce the `MAX_401_REDIRECTS` safety valve.
- **Risk**: The agent page can get stuck in a redirect loop without the safety valve, or fail silently during a CF Worker outage without switching to the fallback. The 401 handler also does not validate the `callbackUrl` for open-redirect attacks.
- **Fix**: Refactor the SSE path to use a shared `fetchWithRetry`-compatible helper that consults the circuit breaker for the base URL, or at minimum use `circuitBreaker.getBaseUrl()` to compute the URL and apply `isSafeRedirect` to the callback URL.

---

#### P2 — Medium

**[P2-01] `types/index.ts` — `UserSettings` type is diverged and dead relative to actual backend shape**

- **File**: `frontend/types/index.ts:188-204`
- **Detail**: `UserSettings` models a full user-settings object with `currentSupplier: Supplier | null`, `annualUsageKwh`, `peakDemandKw`, `appliances`, and nested `notificationPreferences` / `displayPreferences`. The actual backend user profile endpoint (`GET /users/profile`) returns the `UserProfile` shape in `frontend/lib/api/profile.ts` (email, name, region, utility_types, current_supplier_id, annual_usage_kwh, onboarding_completed) with no `peakDemandKw`, no `appliances`, and no nested preferences objects. `UserSettings` is never imported by any API function — it appears to be legacy from a pre-backend design and is now exclusively a frontend fantasy type. If any component still relies on it, it will receive runtime data that does not match.
- **Risk**: If `UserSettings` is still used as a type annotation anywhere in the component layer (not audited here), the TypeScript types will pass but runtime values will be structurally incompatible.
- **Fix**: Deprecate and eventually remove `UserSettings` from `types/index.ts`. Replace usages with the actual `UserProfile` type from `lib/api/profile.ts`. Add a `// @deprecated` comment and a TODO immediately.

---

**[P2-02] `lib/config/seo.ts` — `BASE_URL` duplicates `NEXT_PUBLIC_SITE_URL` access outside `env.ts`**

- **File**: `frontend/lib/config/seo.ts:61`
- **Detail**: `seo.ts` reads `process.env.NEXT_PUBLIC_SITE_URL` directly on line 61 (`export const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://rateshift.app'`) rather than importing `SITE_URL` from `@/lib/config/env`. This violates the stated design principle of `env.ts` ("All NEXT_PUBLIC_* env vars should be accessed through this module"). The `env.ts` module has an `APP_URL` production warning and centralised fallback logic that `seo.ts`'s raw `||` bypass does not get. The two default values are identical (`'https://rateshift.app'`) but could drift independently.
- **Fix**: Replace line 61 with `import { SITE_URL } from '@/lib/config/env'; export const BASE_URL = SITE_URL`.

---

**[P2-03] `lib/api/suppliers.ts` — `GetSuppliersResponse` wraps `RawSupplierRecord` instead of the generated `ApiSupplierResponse`, causing a type layer violation**

- **File**: `frontend/lib/api/suppliers.ts:18-24`
- **Detail**: `GetSuppliersResponse.suppliers` is typed as `RawSupplierRecord[]` (from `types/index.ts`) — a legacy union type that contains both snake_case and camelCase variants of every field. The generated `ApiSuppliersListResponse` in `types/generated/api.ts:246-253` is the correct type for the backend `/suppliers` response. `suppliers.ts` imports from `@/types` instead of `@/types/generated/api`, meaning the type checker can not enforce that returned data actually matches the backend contract. The `getSupplier` function at line 60 returns `Promise<Supplier>` (the camelCase UI type) but the backend returns snake_case — this is only safe if a normalizer is applied, which it is not in the current code path.
- **Fix**: Replace `RawSupplierRecord` usage in `GetSuppliersResponse` with `ApiSupplierResponse` from the generated types. Apply `normaliseSupplierResponse()` from `api-helpers.ts` at the call site. Change `getSupplier` return type to `Promise<ApiSupplierDetailResponse>` and normalize in the caller.

---

**[P2-04] `lib/utils/calculations.ts` — `getPriceCategory` divides by `avgPrice` with no zero guard**

- **File**: `frontend/lib/utils/calculations.ts:157`
- **Detail**: `getPriceCategory(currentPrice, avgPrice)` computes `ratio = currentPrice / avgPrice` with no check for `avgPrice === 0`. If called with `avgPrice = 0` (valid when there is no historical data), `ratio` becomes `Infinity` (or `NaN` if both are `0`). The function then evaluates `Infinity < 0.8` → false, `Infinity > 1.2` → true → returns `'expensive'`. While JavaScript doesn't throw, returning `'expensive'` when there is no historical baseline is misleading UX. `NaN > 1.2` → false, `NaN < 0.8` → false → falls through to `'moderate'`, which is equally misleading.
- **Fix**: Add a guard: `if (avgPrice === 0) return 'moderate'` (or a dedicated `'unknown'` category).

---

**[P2-05] `lib/notifications/onesignal.ts` — `requestPermission` silently swallows errors, masking initialization failures**

- **File**: `frontend/lib/notifications/onesignal.ts:44-53`
- **Detail**: `requestPermission()` catches all errors and returns `false` without logging, making it impossible to distinguish between "user declined permission" and "OneSignal not initialized / module load failure". `loginOneSignal` and `logoutOneSignal` correctly log warnings via `console.warn`. The `requestPermission` function additionally does not guard on `!initialized` — it will attempt to call `OneSignal.Slidedown.promptPush()` even if `initOneSignal` has never been called and `initialized` is `false`, which will throw an error that is then silently swallowed.
- **Fix**: Add `if (!initialized || !ONESIGNAL_APP_ID) return false` guard at the top of `requestPermission`. Add `console.warn('[OneSignal] promptPush failed:', err)` in the catch block.

---

**[P2-06] `lib/api/suppliers.ts` — `getRecommendation` sends camelCase body to backend expecting snake_case**

- **File**: `frontend/lib/api/suppliers.ts:67-78`
- **Detail**: `getRecommendation` POSTs `{ currentSupplierId, annualUsage, region }` (camelCase JavaScript names) to `/suppliers/recommend`. If the backend `POST /suppliers/recommend` Pydantic request model uses snake_case field names (as is standard for this codebase), the keys `currentSupplierId` and `annualUsage` will be silently ignored and the fields will receive their Pydantic defaults (`None`). This is a known codebase pattern — the CLAUDE.md notes "Request model naming consistency: `consent_given` (backend field) vs `consent` (frontend field) mismatches silently break validation". The backend route was not audited here, but the asymmetry is a strong code smell.
- **Fix**: Check the backend Pydantic model for `/suppliers/recommend` and either: (a) change the POST body keys to snake_case (`current_supplier_id`, `annual_usage`), or (b) confirm the backend already accepts camelCase aliases. Also applies to `compareSuppliers` which POSTs `{ supplierIds, annualUsage }`.

---

**[P2-07] `lib/api/community-solar.ts` — monetary fields typed as `string` without documentation or parse helpers**

- **File**: `frontend/lib/api/community-solar.ts:13-51`
- **Detail**: `CommunitySolarProgram` and `CommunitySolarSavingsResponse` have multiple fields typed as `string | null` that are actually numeric: `savings_percent`, `capacity_kw`, `min_bill_amount`, `current_monthly_bill`, `monthly_savings`, `annual_savings`, `five_year_savings`, `new_monthly_bill`. These appear to be Decimal strings from the backend (matching the pattern in `generated/api.ts` for `DecimalStr`). However, they are typed as plain `string` with no `DecimalStr` alias and no JSDoc comment, and there is no `parseDecimal`/`parseDecimalOr` call-site guidance. Any component displaying these will render them as raw strings without arithmetic conversion, leading to "0.10" displayed instead of "$0.10" formatted, or arithmetic like `0.10 + 0.05` returning `"0.100.05"` (string concatenation).
- **Fix**: Type these fields as `DecimalStr` (imported from `types/generated/api.ts`) and add JSDoc comments identical to the pattern in `generated/api.ts`. Add a note to use `parseDecimalOr` before arithmetic.

---

**[P2-08] `lib/api/gas-rates.ts` — trailing slash in endpoint path may cause redirect overhead**

- **File**: `frontend/lib/api/gas-rates.ts:111`
- **Detail**: `getGasRates` calls `/rates/natural-gas/` (note the trailing slash). FastAPI by default redirects trailing-slash requests with a 307 Temporary Redirect to the canonical path. This means every gas rate request incurs an extra round-trip HTTP redirect before the actual response. The other gas endpoints (`/rates/natural-gas/history`, `/rates/natural-gas/stats`) correctly omit the trailing slash.
- **Fix**: Change line 111 from `'/rates/natural-gas/'` to `'/rates/natural-gas'`.

---

**[P2-09] `types/generated/api.ts` — generated at `2026-03-10`, 8 days stale; `ApiUserResponse` missing `tier` field**

- **File**: `frontend/types/generated/api.ts:1-11,305-315`
- **Detail**: The generated types timestamp is `2026-03-10T00:00:00Z`. Since then, multiple migrations (011 through 053) have been applied, and the backend has grown substantially. Specifically: (a) `ApiUserResponse` (line 305-315) has no `tier` / `subscription_tier` field even though the backend user model tracks subscription tiers (`free`/`pro`/`business`) and the `SubscriptionTier` type is defined in the same file (line 58); (b) `ApiUserResponse` has no `avatar_url` or `profile_picture` field if those have been added; (c) The `UtilityType` enum is missing `water` (see P1-02). The stale generated types mean TypeScript type safety is degraded for any code that accesses user tier information via the typed API response.
- **Fix**: Regenerate types (`npm run generate-types:offline`) and commit the updated `generated/api.ts`. Add `tier: SubscriptionTier` to `ApiUserResponse`. Establish a CI check or pre-commit hook that fails if `generated/api.ts` is older than a configured threshold (e.g. 7 days) relative to the last backend API change.

---

#### P3 — Low / Informational

**[P3-01] `lib/utils/format.ts` — `formatCompactNumber` returns `"999999K"` for values near 1 million (not "1.0M")**

- **File**: `frontend/lib/utils/format.ts:81-89`
- **Detail**: The function checks `num >= 1000000` first, then `num >= 1000`. For `num = 999999`, this returns `"1000.0K"` (as confirmed by the test on line 199 of `format.test.ts`). The test acknowledges this with `'999999K'` but this is a visual display oddity — users will see "1000.0K" rather than "1.0M". The threshold check order should produce "1.0M" for exactly 1,000,000 (which it does), but 999,999 is visually awkward as "1000.0K".
- **Note**: This is known and tested. Consider whether `999999` should display as `"999.9K"` (by changing the threshold logic). This is a product decision.

---

**[P3-02] `lib/utils/calculations.ts` — `findOptimalPeriods` uses string comparison for time ordering, not Date comparison**

- **File**: `frontend/lib/utils/calculations.ts:56-86`
- **Detail**: The function iterates `pricesWithTime` in array order and uses `point.time` string values directly as `start` and `end` in the returned periods. String comparison works correctly if `point.time` is ISO-8601 formatted with consistent timezone suffixes (e.g. all UTC with `Z`), but will silently produce incorrect ordering if some timestamps have timezone offsets or are non-ISO strings. The function signature accepts `PriceDataPoint[]` where `time: string` has no format constraint. Real data from the backend is ISO-8601 UTC, so this is low risk in practice.
- **Fix**: Document that `PriceDataPoint.time` must be ISO-8601 UTC, or add a sort on the input array by `Date.parse(d.time)` at the start of `findOptimalPeriods`.

---

**[P3-03] `lib/api/client.ts` — `handleResponse<T>` calls `response.json()` unchecked for 204 No Content responses**

- **File**: `frontend/lib/api/client.ts:123`
- **Detail**: `handleResponse` unconditionally calls `return response.json()` after the `!response.ok` guard. If a backend endpoint returns HTTP 204 No Content (e.g. delete operations in some REST conventions), `response.json()` will throw `SyntaxError: Unexpected end of JSON input`. Currently the backend typically returns `200` with a JSON body even for deletes, but this is a fragile assumption. No test covers the 204 case.
- **Fix**: Add `if (response.status === 204) return undefined as T` before the `response.json()` call. Or check `response.headers.get('content-length') === '0'`.

---

**[P3-04] `lib/utils/url.ts` — `isSafeOAuthRedirect` references `window.location.origin` without SSR guard**

- **File**: `frontend/lib/utils/url.ts:58`
- **Detail**: `isSafeOAuthRedirect` accesses `window.location.origin` (line 58) inside the function body without a `typeof window !== 'undefined'` guard. `isSafeRedirect` (line 19) correctly uses `window.location.origin` with the implicit assumption it's client-side (same pattern), but `isSafeOAuthRedirect` is a separate export that could theoretically be called in a Server Component or in a test environment where `window` is undefined. The function has no `'use client'` directive and no SSR guard.
- **Fix**: Add `if (typeof window === 'undefined') return false` as the first statement in `isSafeOAuthRedirect`.

---

**[P3-05] `lib/constants/regions.ts` — `DEREGULATED_ELECTRICITY_STATES` is a `Set<string>` of abbreviations while `StateOption.abbr` is the source of truth for abbreviations**

- **File**: `frontend/lib/constants/regions.ts:19-22`
- **Detail**: `DEREGULATED_ELECTRICITY_STATES` contains abbreviations like `'CT'`, `'TX'`, etc. The `ALL_STATES` array contains `StateOption.abbr` with identical values. These are maintained independently, meaning a new state added to `US_REGIONS` could be missed from `DEREGULATED_ELECTRICITY_STATES` without any compiler warning. Additionally `'MT'` appears in `DEREGULATED_ELECTRICITY_STATES` but Montana's deregulation status is contested and historically reversed. No test validates this set against the backend `DEREGULATED_STATES` source of truth.
- **Fix**: Derive `DEREGULATED_ELECTRICITY_STATES` from `ALL_STATES` or add a JSDoc reference to the source of truth. Add a test that cross-checks against the backend's region enum if there is an accessible list.

---

**[P3-06] `lib/analytics/clarity.tsx` — `CLARITY_PROJECT_ID` injected directly into a `dangerouslySetInnerHTML` script string**

- **File**: `frontend/lib/analytics/clarity.tsx:18`
- **Detail**: The Clarity project ID is interpolated via `"${CLARITY_PROJECT_ID}"` inside the `__html` string on line 18. If `CLARITY_PROJECT_ID` contained a closing script tag or other script-injection characters, this would create an XSS vector. In practice `CLARITY_PROJECT_ID` is a build-time env var (a Clarity project ID is alphanumeric), but the code does not validate or sanitize the value before interpolation.
- **Risk**: Low — Clarity IDs are alphanumeric only and come from a controlled env var, not user input. But the pattern is dangerous by construction.
- **Fix**: Add a validation guard: `if (!/^[a-zA-Z0-9_-]+$/.test(CLARITY_PROJECT_ID)) return null` before the JSX return.

---

**[P3-07] `lib/email/send.ts` — `FROM_ADDRESS` accepts any string from env with no validation; HTML content is not sanitized**

- **File**: `frontend/lib/email/send.ts:27-28,101-105`
- **Detail**: `FROM_ADDRESS` is constructed from `process.env.EMAIL_FROM_ADDRESS` with no validation of format. An incorrectly configured env var could cause Resend/SMTP to reject all emails silently (the error would be caught and logged, but the configured FROM address is never validated at startup). More significantly, the `html` parameter of `sendEmail` is passed directly to both Resend and nodemailer with no sanitization. Since `sendEmail` is a server-side utility called by backend logic, `html` is expected to come from trusted templates — but if a route handler ever passes user-controlled content, this becomes a stored XSS in email recipients' inboxes.
- **Fix**: (a) Validate `FROM_ADDRESS` with an email regex at module load time, throw in production if invalid. (b) Add a JSDoc comment on `SendEmailParams.html` explicitly stating the parameter must be trusted/pre-sanitized content.

---

**[P3-08] `lib/api/agent.ts` — no retry and no timeout for SSE connection; stale connections can hang indefinitely**

- **File**: `frontend/lib/api/agent.ts:89-108`
- **Detail**: The `queryAgent` generator does not set a `signal` timeout (it accepts one from the caller but does not create its own). If the caller does not pass a timeout signal, and the backend SSE stream stalls mid-response (e.g. during a model API timeout), the `reader.read()` call at line 91 will block indefinitely, holding the browser connection open. There is no keepalive, heartbeat check, or maximum stream duration guard.
- **Fix**: Create an internal `AbortController` with a 60-second timeout (`setTimeout → controller.abort()`), merged with any caller-supplied signal.

---

**[P3-09] `types/api-helpers.ts` — `normaliseSupplierResponse` hardcodes `logoUrl: null` for the list endpoint, losing data**

- **File**: `frontend/types/api-helpers.ts:173-189`
- **Detail**: `normaliseSupplierResponse` (for the list/summary endpoint, `ApiSupplierResponse`) unconditionally sets `logoUrl: null` (line 178). The backend `ApiSupplierResponse` schema in `generated/api.ts:210-219` does not include a `logo_url` field (consistent with the backend `SupplierResponse` Pydantic model). However, this means that if the backend is updated to include `logo_url` in the list response (as it already does in the detail response), the normalizer will silently drop it. The hardcoded `null` is also accompanied by hardcoded `false` for `carbonNeutral` and `null` for `averageRenewablePercentage` and `description` — all valid omissions for the summary response, but they should be documented as deliberate.
- **Fix**: Add `// Not available in list response — use normaliseSupplierDetailResponse for full data` inline comments on the hardcoded `null`/`false` values so future developers don't silently fill them from undefined sources.

---

**[P3-10] `lib/utils/devGate.ts` — exported function is redundant with `IS_DEV` from `env.ts`**

- **File**: `frontend/lib/utils/devGate.ts`
- **Detail**: `isDevMode()` returns `process.env.NODE_ENV === 'development'`. The `env.ts` module already exports `IS_DEV = !isProduction && !isTest` which covers the same concept. Two functions now represent the same concept across two modules. `devGate.ts` does not import from `env.ts`, so the two can drift independently (e.g. if `env.ts` changes the definition of "dev mode" to include staging environments).
- **Fix**: Either (a) delete `devGate.ts` and update consumers to import `IS_DEV` from `@/lib/config/env`, or (b) rewrite `isDevMode()` as `export const isDevMode = () => IS_DEV` importing from `env.ts`.

---

**[P3-11] `lib/api/notifications.ts` — `markAllRead` fetches the full notification list in a non-atomic, best-effort manner; concurrent tabs can cause race conditions**

- **File**: `frontend/lib/api/notifications.ts:73-78`
- **Detail**: `markAllRead` calls `getNotifications()` to get the list of unread notifications, then maps over them calling `markNotificationRead(n.id)` in parallel. If two browser tabs are open and both call `markAllRead` simultaneously, each may see the same set and issue duplicate PUT requests (which will 404 on the second pass for already-read notifications — silently swallowed via `Promise.allSettled`). More importantly, any notification that arrives between the `getNotifications()` call and the `markNotificationRead` calls will be missed. The CLAUDE.md notes "The backend does not expose a bulk-mark-all endpoint" as the reason for this pattern.
- **Fix**: This is a known backend limitation. Add a JSDoc comment explaining the race condition and noting that the backend `PUT /notifications/{id}/read` returns 404 for already-read notifications (which is why `Promise.allSettled` with no error handling is used). If a bulk endpoint is added to the backend, update this function.

---

### Summary Table

| ID | Severity | File | Issue |
|----|----------|------|-------|
| P1-01 | High | `types/index.ts:88,139` + `generated/api.ts:33` | `TariffType` hyphen vs underscore mismatch — silent runtime breakage |
| P1-02 | High | `types/generated/api.ts:51-57` | `UtilityType` missing `'water'` — live API client has no type backing |
| P1-03 | High | `lib/utils/format.ts:57-76` | `formatTime`, `formatDate`, `formatRelativeTime` throw on invalid date strings |
| P1-04 | High | `lib/api/agent.ts:55-109` | SSE `queryAgent` bypasses circuit-breaker, retry, and safe 401 redirect |
| P2-01 | Medium | `types/index.ts:188-204` | `UserSettings` is diverged/dead — does not match actual backend profile shape |
| P2-02 | Medium | `lib/config/seo.ts:61` | `BASE_URL` reads `process.env` directly, bypassing `env.ts` centralisation |
| P2-03 | Medium | `lib/api/suppliers.ts:18-24` | `GetSuppliersResponse` uses legacy `RawSupplierRecord` instead of generated types |
| P2-04 | Medium | `lib/utils/calculations.ts:157` | `getPriceCategory` divides by `avgPrice` with no zero guard |
| P2-05 | Medium | `lib/notifications/onesignal.ts:44-53` | `requestPermission` swallows errors silently; no `initialized` guard |
| P2-06 | Medium | `lib/api/suppliers.ts:67-78` | `getRecommendation` POSTs camelCase keys to snake_case backend |
| P2-07 | Medium | `lib/api/community-solar.ts:13-51` | Decimal monetary fields typed as `string`, no `DecimalStr` alias or parse guidance |
| P2-08 | Medium | `lib/api/gas-rates.ts:111` | Trailing slash in `/rates/natural-gas/` causes 307 redirect on every request |
| P2-09 | Medium | `types/generated/api.ts:1-11` | Generated types 8 days stale; missing `tier` on `ApiUserResponse` |
| P3-01 | Low | `lib/utils/format.ts:81` | `formatCompactNumber(999999)` returns `"1000.0K"` not `"1.0M"` |
| P3-02 | Low | `lib/utils/calculations.ts:56-86` | `findOptimalPeriods` relies on string ordering for time; not timezone-safe |
| P3-03 | Low | `lib/api/client.ts:123` | `handleResponse` throws on 204 No Content (`response.json()` on empty body) |
| P3-04 | Low | `lib/utils/url.ts:58` | `isSafeOAuthRedirect` accesses `window.location.origin` without SSR guard |
| P3-05 | Low | `lib/constants/regions.ts:19-22` | `DEREGULATED_ELECTRICITY_STATES` maintained independently of `ALL_STATES` |
| P3-06 | Low | `lib/analytics/clarity.tsx:18` | `CLARITY_PROJECT_ID` interpolated into `dangerouslySetInnerHTML` without validation |
| P3-07 | Low | `lib/email/send.ts:27,101` | `FROM_ADDRESS` unvalidated; `html` parameter not documented as trusted-only |
| P3-08 | Low | `lib/api/agent.ts:89` | No timeout on SSE `reader.read()` loop — stale connections hang indefinitely |
| P3-09 | Low | `types/api-helpers.ts:178` | `normaliseSupplierResponse` silently hardcodes `logoUrl: null` without comment |
| P3-10 | Low | `lib/utils/devGate.ts` | `isDevMode()` duplicates `IS_DEV` from `env.ts` — dual sources of truth |
| P3-11 | Low | `lib/api/notifications.ts:73-78` | `markAllRead` is non-atomic; concurrent tabs can miss notifications |

---

### Positive Observations

The following are notable strengths that should be preserved:

1. **Circuit breaker implementation** (`lib/api/circuit-breaker.ts`) is well-designed with `CLOSED → OPEN → HALF_OPEN` state machine, configurable `halfOpenSuccessThreshold`, and comprehensive tests (35+ cases in `circuit-breaker.test.ts`).

2. **401 redirect loop prevention** (`lib/api/client.ts:41-93`) correctly implements: per-session counter with expiry window, deduplication via `redirectInFlight`, auth-page suppression, and `isSafeRedirect` for callbackUrl validation. The 8 dedicated test cases in `client-401-redirect.test.ts` are excellent.

3. **`env.ts` centralisation** is the right pattern — single import point, production validation, sensible fallbacks. The design principle stated in the file comment should be enforced (see P2-02).

4. **`api-helpers.ts` normalization layer** correctly separates raw backend types (`generated/api.ts`) from UI types (`types/index.ts`) via dedicated normalizers with `parseDecimal`/`parseDecimalOr` helpers. The `isValidationError`/`isApiErrorDetail`/`extractApiErrorMessage` type guards are type-safe and follow the `unknown`-based narrowing pattern.

5. **`url.ts` security utilities** (`isSafeRedirect`, `isSafeHref`, `isSafeOAuthRedirect`) are correctly implemented and well-documented. The `new URL(url, window.location.origin)` pattern for `isSafeRedirect` correctly handles relative paths.

6. **`format.ts` test coverage** is comprehensive — 8 describe blocks covering all exported functions with edge cases including negatives, zero values, rounding, and locale separators.

7. **`chartTokens.ts` CSS variable approach** — using `var(--chart-N)` rather than hex values is the correct theming pattern. The `as const` assertions ensure the arrays are literal types preventing accidental mutation.

8. **`isSafeHref` rejection of relative URLs** (catching `new URL(href)` that throws for relative strings) is the correct behavior for server-supplied external links.
