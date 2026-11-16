# Frontend Components Audit

> Generated: 2026-03-18
> Scope: All `.tsx` / `.ts` files under `frontend/components/`
> Files audited: **100+ component files** across **22 subdirectories**
> Categories checked: error boundaries, loading states, accessibility, TypeScript types, memory leaks, dependency arrays, memoization, hardcoded strings, CSS consistency, test coverage

---

## Table of Contents

- [P0 - Critical (must fix before next release)](#p0---critical-must-fix-before-next-release)
- [P1 - High (fix within current sprint)](#p1---high-fix-within-current-sprint)
- [P2 - Medium (fix within next sprint)](#p2---medium-fix-within-next-sprint)
- [P3 - Low (backlog / nice-to-have)](#p3---low-backlog--nice-to-have)
- [Summary Statistics](#summary-statistics)

---

## P0 - Critical (must fix before next release)

### P0-01: SupplierAccountForm - Missing `await` on `Promise.race`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/suppliers/SupplierAccountForm.tsx`
**Line:** 46-47
**Category:** Bug / incorrect async handling

The `Promise.race` call is missing `await`, meaning the result is assigned as a `Promise` object, never resolved. All subsequent code that references `result` will see a pending Promise, not the resolved data.

```tsx
// Line 46-47 — missing await
const result = Promise.race([
  submitAccountLink(supplierId, accountNumber, consentGiven),
  timeoutPromise,
])
```

**Fix:** Add `await` before `Promise.race(...)`.

---

### P0-02: AgentChat - Array index used as React key for messages

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/agent/AgentChat.tsx`
**Line:** 160-161
**Category:** React correctness / potential data corruption

Messages can be added and removed (via `reset`), and when streaming completes the array is mutated. Using array index as key means React may reuse DOM nodes for the wrong messages, causing visual glitches or stale content.

```tsx
// Line 160-161
{messages.map((msg, i) => (
  <MessageBubble key={i} message={msg} />
))}
```

**Fix:** Add a unique `id` field to each `AgentMessage` (e.g., UUID or incrementing counter from the hook) and use it as the key.

---

### P0-03: GasRatesContent - Array index as key for price history items

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/gas/GasRatesContent.tsx`
**Line:** 184-187
**Category:** React correctness

Price history items are rendered with `key={i}` (array index). These items can change when the time range filter is modified, leading to incorrect DOM recycling.

```tsx
// Line 184-187
{historyData.prices.slice(0, 20).map((p, i) => (
  <div
    key={i}
    className="flex items-center justify-between ..."
```

**Fix:** Use a unique identifier such as `p.id` or a composite key like `${p.timestamp}-${p.supplier}`.

---

### P0-04: SuppliersContent - Inline modal without focus trap

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/suppliers/SuppliersContent.tsx`
**Lines:** ~350-378
**Category:** Accessibility (WCAG 2.1 AA violation)

The inline modal overlays (e.g., for `SetSupplierDialog` and `SwitchWizard`) are rendered inside a `fixed` overlay `div` with a backdrop click handler, but they lack:
- Focus trap (Tab can escape the modal)
- Escape key to close
- `role="dialog"` and `aria-modal="true"`
- Focus restoration on close

This is an accessibility barrier for keyboard-only and screen reader users.

**Fix:** Use the project's existing `<Modal>` component from `ui/modal.tsx` (which already implements focus trap, Escape key, and focus restoration) to wrap these dialogs, or add the missing ARIA attributes and focus management.

---

### P0-05: HeatingOilDashboard / PropaneDashboard - Clickable cards without keyboard access

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/heating-oil/HeatingOilDashboard.tsx`
**Line:** 98-99
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/propane/PropaneDashboard.tsx`
**Line:** 98-99
**Category:** Accessibility (WCAG 2.1 AA violation)

State price cards use `onClick` on a `div` element but lack `role="button"`, `tabIndex={0}`, and `onKeyDown` handlers. Keyboard-only users cannot interact with these controls.

```tsx
// HeatingOilDashboard.tsx line 98-99
<div
  key={p.state}
  className="rounded-lg border p-4 cursor-pointer hover:border-primary-300 transition-colors"
  onClick={() => setSelectedState(p.state)}
>
```

**Fix:** Add `role="button"`, `tabIndex={0}`, `onKeyDown` handler (Enter/Space), and `aria-label` to each card.

---

## P1 - High (fix within current sprint)

### P1-01: Header - Simulated refresh with setTimeout

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/Header.tsx`
**Line:** 29
**Category:** UX / misleading behavior

The refresh button uses `setTimeout(() => setIsRefreshing(false), 1000)` which is a visual-only spinner not tied to any actual data refresh operation. Users see a spinner that completes regardless of whether data was actually refreshed.

```tsx
// Line 29
setTimeout(() => setIsRefreshing(false), 1000)
```

**Fix:** Wire the refresh handler to actual data refetch (e.g., via React Query's `refetchQueries`) and clear the spinner when the fetch completes or fails.

---

### P1-02: NotificationBell - No Escape key handler for dropdown

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/NotificationBell.tsx`
**Category:** Accessibility

The notification dropdown has click-outside handling but no Escape key handler. Users who open the dropdown with keyboard cannot dismiss it with Escape.

**Fix:** Add a `useEffect` with a `keydown` listener for `Escape` that calls the close handler.

---

### P1-03: ConnectionAnalytics - Timer-based refresh spinner not tied to actual load

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/ConnectionAnalytics.tsx`
**Line:** 42
**Category:** UX / misleading behavior

```tsx
// Line 42 — spinner resets after 600ms regardless of actual data load status
setTimeout(() => setRefreshing(false), 600)
```

The refresh spinner runs for a fixed 600ms and stops regardless of whether the child cards have finished loading. This can mislead users into thinking data is refreshed when it is still loading.

**Fix:** Track loading state from child components (via callback or shared state) and clear the spinner when all cards complete.

---

### P1-04: DashboardContent - Hardcoded price threshold

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/DashboardContent.tsx`
**Line:** 71
**Category:** Hardcoded business logic

```tsx
// Line 71
isOptimal: price !== null && price < 0.22
```

The value `0.22` (22 cents/kWh) is a hardcoded US national average-ish threshold. It does not account for regional variation (e.g., Hawaii averages 40+ cents, many Southern states average 12 cents). This will incorrectly flag prices as "optimal" or "not optimal" depending on the user's region.

**Fix:** Make this threshold configurable per region, either from backend API response or from user settings.

---

### P1-05: PostForm - Hardcoded region fallback

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/community/PostForm.tsx`
**Line:** 90
**Category:** Hardcoded value / data integrity

```tsx
// Line 90
region: region || 'us_ct'
```

If the user has no region set, the post is silently attributed to Connecticut. This creates misleading location data in community posts.

**Fix:** Either require a region before allowing post creation, or use a null/empty value and handle it on the backend.

---

### P1-06: SavingsTracker - Hardcoded $50 monthly savings goal

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/gamification/SavingsTracker.tsx`
**Line:** ~96
**Category:** Hardcoded business logic

```tsx
Monthly Goal: ${formatCurrency(50)}
```

The $50 monthly savings goal is hardcoded. Users cannot customize it, and it may be unrealistic for many users (either too high or too low depending on their usage).

**Fix:** Allow users to set their savings goal in settings, or derive it from their actual usage data.

---

### P1-07: DataExport - Missing labels on select elements

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/analytics/DataExport.tsx`
**Lines:** 70-96
**Category:** Accessibility

Two `<select>` elements (utility type and format) have no associated `<label>` elements or `aria-label` attributes.

```tsx
// Line 70 — no label for utility type select
<select
  value={selectedUtility}
  onChange={(e) => { ... }}
  className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
>
```

**Fix:** Add `aria-label="Select utility type"` and `aria-label="Export format"` to the respective selects.

---

### P1-08: ForecastWidget - Missing labels on select elements

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/analytics/ForecastWidget.tsx`
**Lines:** 50-72
**Category:** Accessibility

Two `<select>` elements (utility type and forecast horizon) have no associated labels.

**Fix:** Add `aria-label` attributes or visible `<label>` elements.

---

### P1-09: CCAAlert - Missing role="alert" or aria-live for dynamic content

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAAlert.tsx`
**Category:** Accessibility

The CCA alert banner announces important information ("You're in a CCA Program") but lacks `role="alert"` or `aria-live="polite"`, so screen readers may not announce it when it dynamically appears.

**Fix:** Add `role="alert"` or `role="status"` to the container div.

---

### P1-10: DealerList - `dealer.website` rendered as href without URL validation

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/heating-oil/DealerList.tsx`
**Line:** 50-55
**Category:** Security

The dealer website URL is rendered directly as an `href` without validation via `isSafeHref()`. Since this data comes from a backend API that may aggregate third-party sources, it could contain `javascript:` or other dangerous URIs.

```tsx
// Line 50
{dealer.website && (
  <a
    href={dealer.website}
    target="_blank"
    rel="noopener noreferrer"
    ...
```

**Fix:** Use `isSafeHref(dealer.website)` (already imported elsewhere in the project) before rendering the link.

---

### P1-11: RateHistoryCard - Missing table accessibility attributes

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/analytics/RateHistoryCard.tsx`
**Lines:** 79-82
**Category:** Accessibility

The rate history table lacks `scope="col"` on its `<th>` elements. The `ConnectionRates.tsx` table correctly uses `scope="col"`, but this table does not.

```tsx
// Line 81-82 — missing scope="col"
<th className="px-4 py-2 font-medium text-gray-500">Date</th>
<th className="px-4 py-2 font-medium text-gray-500">Rate</th>
```

**Fix:** Add `scope="col"` to all `<th>` elements.

---

### P1-12: RatePageContent - Supplier table uses array index as key

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/seo/RatePageContent.tsx`
**Line:** 100-101
**Category:** React correctness

```tsx
// Line 100
{rateData.suppliers.map((s, i) => (
  <tr key={i} className="border-b">
```

Suppliers can be sorted or filtered, making array index an unstable key. Use `s.supplier` or a composite key.

---

### P1-13: OptimizationReport - Savings opportunities use array index as key

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/analytics/OptimizationReport.tsx`
**Line:** 114
**Category:** React correctness

```tsx
// Line 114
{report.savings_opportunities.map((opp, i) => (
  <div key={i} ...
```

**Fix:** Use a composite key like `${opp.utility_type}-${opp.action}` or ensure the backend provides an `id`.

---

### P1-14: ConnectionAnalytics - syncErrorTimeout ref never cleaned up on unmount

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/ConnectionAnalytics.tsx`
**Lines:** 35, 64-65
**Category:** Memory leak

```tsx
// Line 35
const syncErrorTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

// Line 64-65
if (syncErrorTimeout.current) clearTimeout(syncErrorTimeout.current)
syncErrorTimeout.current = setTimeout(() => setSyncError(null), 8000)
```

The timeout ref is cleared before setting a new timeout, but there is no `useEffect` cleanup. If the component unmounts while a timeout is pending, the callback will fire on an unmounted component.

**Fix:** Add cleanup:
```tsx
useEffect(() => {
  return () => {
    if (syncErrorTimeout.current) clearTimeout(syncErrorTimeout.current)
  }
}, [])
```

---

## P2 - Medium (fix within next sprint)

### P2-01: DashboardForecast - `unknown` type for forecastData prop

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/DashboardForecast.tsx`
**Category:** TypeScript typing

The `forecastData` prop is typed as `unknown`, which defeats TypeScript's type safety. All consumers must cast or use type guards to access properties.

**Fix:** Define a proper `ForecastData` interface based on the API response shape.

---

### P2-02: PricesContent - Fragile parseInt on timeRange strings

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/prices/PricesContent.tsx`
**Line:** ~57
**Category:** Fragile logic

```tsx
// Line ~57
parseInt(timeRange)
```

The `timeRange` values are strings like `'6h'`, `'12h'`, `'24h'`, `'7d'`, `'30d'`. `parseInt('6h')` returns `6`, `parseInt('7d')` returns `7`, which happens to work but is fragile and confusing. If a value like `'all'` is added, it returns `NaN`.

**Fix:** Use a proper mapping object (`{ '6h': 6, '12h': 12, ... }`) or parse with explicit format handling.

---

### P2-03: AnalyticsDashboard - Hardcoded default state 'CT'

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/analytics/AnalyticsDashboard.tsx`
**Line:** 18
**Category:** Hardcoded value

```tsx
// Line 18
const [state, setState] = useState('CT')
```

The default state is hardcoded to Connecticut. It should read from the user's settings store (`useSettingsStore`) to match their configured region.

**Fix:** Initialize from `useSettingsStore((s) => s.region)` and extract the state code.

---

### P2-04: HeatingOilDashboard / PropaneDashboard - Duplicated STATE_NAMES constant

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/heating-oil/HeatingOilDashboard.tsx`
**Lines:** 8-18
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/propane/PropaneDashboard.tsx`
**Lines:** 8-17
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/water/WaterDashboard.tsx`
**Lines:** 8-21
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/analytics/AnalyticsDashboard.tsx`
**Lines:** 8-15
**Category:** Hardcoded strings / duplication

The `US_STATES` and `STATE_NAMES` mappings are duplicated across at least 4 component files, each with slightly different subsets (heating oil/propane only list Northeast states). There is no shared constant file.

**Fix:** Create a shared `lib/constants/states.ts` with the full mapping and region-specific subsets.

---

### P2-05: Multiple select elements missing consistent styling

**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/analytics/DataExport.tsx` (lines 70-96)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/analytics/ForecastWidget.tsx` (lines 50-72)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/RateChangeFeed.tsx` (lines 52-75)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/AlertPreferences.tsx` (line 77)

**Category:** CSS inconsistency

Some `<select>` elements use the full Tailwind styling pattern from the design system (e.g., `DirectLoginForm.tsx` with `rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500`), while others use minimal styling (`rounded border px-2 py-1 text-sm` or `rounded-md border border-gray-300 px-3 py-1.5 text-sm`).

**Fix:** Extract a shared select component or use consistent Tailwind classes across all select elements.

---

### P2-06: CCAComparison / CCAInfo - Error state silently returns null

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAComparison.tsx`
**Line:** 18
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAInfo.tsx`
**Line:** 28
**Category:** Missing error states

```tsx
// CCAComparison.tsx line 18
if (error || !data) return null
```

When an API error occurs, both components silently return nothing instead of showing an error message. The user has no indication that something failed and no way to retry.

**Fix:** Add an error state with a retry button, similar to the pattern used in `ConnectionHealthCard.tsx`.

---

### P2-07: OilPriceHistory / PropanePriceHistory / DealerList - Silent error rendering

**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/heating-oil/OilPriceHistory.tsx` (line 17)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/heating-oil/DealerList.tsx` (line 17)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/propane/PropanePriceHistory.tsx` (line 17)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/propane/FillUpTiming.tsx` (line 37)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/water/ConservationTips.tsx` (line 24)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/water/WaterRateBenchmark.tsx` (line 23)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/water/WaterTierCalculator.tsx` (line 26)

**Category:** Missing error states

All of these components share the same pattern:
```tsx
if (error || !data) return null
```

Errors are silently swallowed and the component disappears from the page. Users see nothing and have no way to retry.

**Fix:** Show an inline error message with a retry option for each of these components.

---

### P2-08: InstallPrompt - `any` type cast for BeforeInstallPromptEvent

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/pwa/InstallPrompt.tsx`
**Category:** TypeScript typing

The `beforeinstallprompt` event is cast to `any` because the browser event type is not in the standard TypeScript DOM definitions.

**Fix:** Define a `BeforeInstallPromptEvent` interface extending `Event` with the `prompt()` method and `userChoice` property, which is a standard pattern for PWA TypeScript codebases.

---

### P2-09: Multiple components missing `aria-live` for dynamic content

**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/DirectLoginForm.tsx` - sync result success/error (lines 282-304)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/BillUploadProgress.tsx` - processing status (lines 44-66)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/gamification/SavingsTracker.tsx` - savings progress updates
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/agent/AgentChat.tsx` - streaming responses (line 163-171)

**Category:** Accessibility

Dynamic content that appears after user actions (sync results, upload progress, streaming chat responses) is not announced to screen readers because the containers lack `aria-live="polite"` or `aria-live="assertive"` attributes.

**Fix:** Add `aria-live="polite"` to containers that receive dynamic status updates.

---

### P2-10: AgentChat - Textarea missing aria-label

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/agent/AgentChat.tsx`
**Line:** 197-206
**Category:** Accessibility

The chat input textarea has a `placeholder` but no `aria-label` or `aria-labelledby` for screen reader users.

```tsx
// Line 202
placeholder="Ask RateShift AI..."
```

**Fix:** Add `aria-label="Type a message to RateShift AI"` to the textarea.

---

### P2-11: CommunitySolarContent - Filter buttons missing aria-pressed

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/community-solar/CommunitySolarContent.tsx`
**Lines:** 82-112
**Category:** Accessibility

The filter toggle buttons (All, Open, Waitlist) use visual styling to indicate the active state but lack `aria-pressed` attributes for screen reader users.

```tsx
// Line 82-88
<button
  onClick={() => setFilter(undefined)}
  className={`rounded-full px-3 py-1 text-xs font-medium ${
    !filter
      ? 'bg-primary-100 text-primary-700'
      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
  }`}
>
```

**Fix:** Add `aria-pressed={!filter}` (and corresponding values for the other buttons).

---

### P2-12: UTILITY_LABELS constant duplicated across 5+ files

**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/analytics/DataExport.tsx` (lines 7-12)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/analytics/ForecastWidget.tsx` (lines 7-12)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/analytics/OptimizationReport.tsx` (lines 6-12)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/RateChangeCard.tsx` (lines 5-11)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/RateChangeFeed.tsx` (lines 7-14)

**Category:** Hardcoded strings / DRY violation

The `UTILITY_LABELS` mapping (`electricity => 'Electricity'`, etc.) is duplicated verbatim in at least 5 files. Each copy has slightly different utility type coverage, creating maintenance risk when new utility types are added.

**Fix:** Extract to `lib/constants/utilities.ts` with all utility types and labels, and import everywhere.

---

### P2-13: DiagramEditor - setTimeout for "Saved" indicator not cleaned up

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dev/DiagramEditor.tsx`
**Line:** 47
**Category:** Memory leak (dev-only)

```tsx
// Line 47
setTimeout(() => setShowSaved(false), 2000)
```

The timeout is set without cleanup. If the component unmounts within 2 seconds of a save, the callback fires on an unmounted component.

**Fix:** Store the timeout ID in a ref and clear it in a cleanup effect. (Lower priority since this is dev-only.)

---

### P2-14: FTCDisclosure - Uses `text-muted-foreground` instead of Tailwind design system

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/affiliate/FTCDisclosure.tsx`
**Line:** 29
**Category:** CSS inconsistency

```tsx
// Line 29
<p className="text-xs text-muted-foreground" ...>
```

The class `text-muted-foreground` is a shadcn/ui CSS variable-based class, while the rest of the codebase uses Tailwind's `text-gray-500` pattern. This is the only component using this convention in the main component tree.

**Fix:** Replace with `text-gray-500` to match the project's established Tailwind pattern.

---

### P2-15: Multiple components using `text-muted-foreground` and `bg-muted` classes

**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/affiliate/FTCDisclosure.tsx` (line 29)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/RateChangeCard.tsx` (lines 34, 50, 71)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/RateChangeFeed.tsx` (line 79)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/AlertPreferences.tsx` (lines 23, 93)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/seo/RatePageContent.tsx` (lines 49, 68, 78, 81, 107, 125)

**Category:** CSS inconsistency

These components use shadcn/ui-style CSS variable classes (`text-muted-foreground`, `bg-muted`, `bg-card`, `bg-accent`) rather than the project's standard Tailwind utility classes (`text-gray-500`, `bg-gray-100`, `bg-white`). This creates a mixed styling approach.

**Fix:** Standardize on the project's Tailwind design tokens throughout. Either adopt shadcn/ui variables globally or replace with direct Tailwind classes.

---

### P2-16: CCAAlert - Hardcoded color classes instead of design system tokens

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAAlert.tsx`
**Lines:** 22, 25, 28, 34, 41, 46, 51, 59, 63
**Category:** CSS inconsistency

This component uses raw Tailwind colors (`border-blue-200`, `bg-blue-50`, `text-blue-900`, `text-green-700`) instead of the project's custom color tokens (`border-primary-200`, `bg-primary-50`, `text-success-700`).

Similarly in `CCAInfo.tsx` (lines 57-69) using `bg-green-100`, `text-green-800`, `bg-amber-100`, etc.

**Fix:** Replace with the project's design tokens (`primary-*`, `success-*`, `warning-*`, etc.).

---

### P2-17: Missing memoization on expensive computations

**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/water/WaterTierCalculator.tsx` - `calculateCost()` function (lines 31-60) is called on every render even when inputs haven't changed
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/community-solar/CommunitySolarContent.tsx` - program list filtering (line 86-87) runs on every render
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/gas/GasRatesContent.tsx` - price filtering and trend calculation (lines 30-43) runs on every render

**Category:** Performance / missing memoization

These components compute derived data on every render without `useMemo`. For small datasets this is fine, but if data grows (e.g., 100+ programs, extended price history), it will cause unnecessary recalculation.

**Fix:** Wrap with `useMemo` keyed on the input values:
```tsx
const cost = useMemo(
  () => selectedRate ? calculateCost(selectedRate, usageGallons) : null,
  [selectedRate, usageGallons]
)
```

---

### P2-18: BillUploadForm - XHR-based upload lacks AbortController cleanup

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/BillUploadForm.tsx`
**Lines:** 163-243
**Category:** Memory leak potential

The `handleUpload` function creates an `XMLHttpRequest` inside a `Promise` constructor. If the component unmounts during upload, there is no mechanism to abort the XHR request. The polling interval cleanup exists (lines 33-38), but the XHR itself is not aborted.

**Fix:** Store the XHR instance in a ref and call `xhr.abort()` in a cleanup effect.

---

## P3 - Low (backlog / nice-to-have)

### P3-01: Multiple formatDate / formatCurrency utility function duplications

**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/ConnectionRates.tsx` (lines 40-59)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/BillUploadTypes.ts` (lines 48-61)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/analytics/types.ts` (lines 76-87)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/DirectLoginForm.tsx` (lines 46-57)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/analytics/SavingsEstimateCard.tsx` (lines 66-73)

**Category:** DRY violation

The `formatDate()` function is defined identically in at least 3 files. The `formatCurrency()` function appears in at least 3 files with slight variations (some include `maximumFractionDigits: 4`, others use defaults). The project already has `lib/utils/format.ts` with these utilities.

**Fix:** Import from `@/lib/utils/format` consistently.

---

### P3-02: Loading skeleton inconsistencies

**Category:** UX consistency

Loading states use inconsistent patterns across the codebase:
- Some use the `<Skeleton>` component from `ui/skeleton.tsx` (e.g., `GasRatesContent.tsx`, `DiagramEditor.tsx`)
- Some use `<Loader2>` spinner icon (e.g., `ConnectionUploadFlow.tsx`, `AgentChat.tsx`)
- Some use plain `animate-pulse` divs (e.g., `CCAComparison.tsx`, `DealerList.tsx`, `PropanePriceHistory.tsx`)

All three patterns appear throughout the codebase. While not incorrect, the inconsistency creates a disjointed user experience.

**Fix:** Establish a convention: use `<Skeleton>` for content placeholders (data tables, cards), `<Loader2>` for action-triggered spinners (buttons, submit), and eliminate raw `animate-pulse` div patterns in favor of `<Skeleton>`.

---

### P3-03: ServiceWorkerRegistrar - No error reporting for SW registration failures

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/pwa/ServiceWorkerRegistrar.tsx`
**Category:** Error handling

Service worker registration failures are logged to `console.warn` but not reported to any error tracking service (e.g., Sentry). In production, these failures would be invisible.

**Fix:** Add Sentry error capture for SW registration failures.

---

### P3-04: QueryProvider - Retry logic uses type narrowing on `status` field

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/providers/QueryProvider.tsx`
**Lines:** 17-27
**Category:** TypeScript typing

The retry function uses verbose type narrowing to check `error.status`:
```tsx
if (
  error &&
  typeof error === 'object' &&
  'status' in error &&
  typeof (error as { status: unknown }).status === 'number' &&
  (error as { status: number }).status < 500
) {
```

This could be simplified using the project's `ApiClientError` class which has a typed `status` property.

**Fix:** Import `ApiClientError` and use `error instanceof ApiClientError && error.status < 500`.

---

### P3-05: ExcalidrawWrapper - `any` type casts in onChange handler

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dev/ExcalidrawWrapper.tsx`
**Line:** 54
**Category:** TypeScript typing (dev-only)

```tsx
// Line 54
onChange: handleChange as unknown as (elements: any, appState: any, files: any) => void,
```

The `any` casts are annotated with comments explaining the necessity (Excalidraw's internal types are not publicly exported), which is acceptable for a dev-only component.

**Impact:** Low -- this component is triple-gated and only available in development.

---

### P3-06: Error boundary does not report to Sentry

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/error-boundary.tsx`
**Category:** Error reporting

The `ErrorBoundary` class component catches errors and renders a fallback UI, but does not report the error to Sentry or any external monitoring service.

**Fix:** Add `Sentry.captureException(error)` in the `componentDidCatch` lifecycle method.

---

### P3-07: CCAInfo generation mix bar chart lacks text alternative

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAInfo.tsx`
**Lines:** 77-96
**Category:** Accessibility

The generation mix stacked bar chart uses `title` attributes on individual segments but lacks a text alternative for the overall chart. Screen readers will not convey the visual distribution.

**Fix:** Add a `role="img"` and `aria-label` describing the overall generation mix distribution.

---

### P3-08: RatePageContent table missing `aria-label` or `caption`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/seo/RatePageContent.tsx`
**Lines:** 91-116
**Category:** Accessibility

The suppliers table lacks `aria-label` or `<caption>` element. Screen reader users will not know the purpose of the table.

**Fix:** Add `aria-label="Supplier rate comparison"` or a `<caption>` element.

---

### P3-09: CCAAlert buttons missing `focus-visible` ring

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAAlert.tsx`
**Lines:** 39-44, 47-52
**Category:** Accessibility

The "View Details" and "Program Website" links/buttons lack `focus-visible:ring-*` styles, making keyboard focus invisible.

```tsx
// Line 41
className="text-sm font-medium text-blue-700 hover:text-blue-900"
```

**Fix:** Add `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 rounded` classes.

---

### P3-10: AlertPreferences - Toggle switch not semantically complete

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/AlertPreferences.tsx`
**Lines:** 57-72
**Category:** Accessibility

The custom toggle switch correctly uses `role="switch"` and `aria-checked`, which is good. However, the switch track (`span`) inside does not have `aria-hidden="true"`, and the visual toggle state animation relies solely on visual presentation.

**Fix:** Add `aria-hidden="true"` to the inner `span` element.

---

### P3-11: Missing test coverage for complex component logic

**Category:** Test coverage

The following components contain complex logic that would benefit from dedicated unit tests:

1. **WaterTierCalculator** (`calculateCost` function, lines 31-60) - Tiered pricing calculation with edge cases (multiple tiers, null limits, remaining gallons)
2. **BillUploadForm** (`pollParseStatus` function, lines 100-161) - Polling with timeout, field mapping, and state machine transitions
3. **AgentChat** (`handleSubmit` / `handleExampleClick` logic) - Input validation, streaming state management
4. **SavingsEstimateCard** (debounce logic, lines 45-57) - Debounced API calls with cleanup
5. **ConnectionAnalytics** (`handleSyncConnection`, lines 45-67) - Concurrent sync tracking with Set state
6. **RateHistoryCard** (change calculation, lines 89-97) - Rate delta computation between adjacent rows

These components have interactive logic that could have edge-case bugs not caught by integration tests.

---

### P3-12: No i18n infrastructure

**Category:** Internationalization

All user-facing strings are hardcoded in English throughout the component tree. There is no i18n framework (e.g., `next-intl`, `react-i18next`) configured. While not immediately needed (US-focused product), this will require significant refactoring if internationalization is ever needed.

Key hardcoded strings:
- "Connection Established", "Sync Now", "Done" (`DirectLoginForm.tsx`)
- "How can I help you save on electricity?" (`AgentChat.tsx`)
- "Upload Utility Bill" (`BillUploadForm.tsx`)
- "Send Feedback" (`FeedbackWidget.tsx`)
- Button labels, error messages, and status text across all components

**Impact:** Low for now, but creates tech debt for future expansion.

---

### P3-13: Multiple components use raw `fetch` instead of `apiClient`

**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/DirectLoginForm.tsx` (lines 78, 96, 125, 186)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/ConnectionUploadFlow.tsx` (line 41)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/ConnectionAnalytics.tsx` (line 48)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/feedback/FeedbackWidget.tsx` (line 22)

**Category:** Consistency / error handling

These components use raw `fetch()` with `${API_ORIGIN}/api/v1/...` instead of the project's `apiClient` from `@/lib/api/client`. The `apiClient` provides centralized error handling (401 redirect, etc.), while raw `fetch` requires each component to handle auth errors independently.

**Fix:** Migrate to `apiClient` where possible. Note: some uses (like XHR upload in `BillUploadForm`) cannot use `apiClient` due to progress tracking requirements.

---

### P3-14: FeedbackModal - firstFocusRef typed as button but assigned to radio input

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/feedback/FeedbackWidget.tsx`
**Line:** 51, 181
**Category:** TypeScript typing

```tsx
// Line 51
const firstFocusRef = useRef<HTMLButtonElement>(null)

// Line 181 — assigned to an input element, not a button
ref={index === 0 ? firstFocusRef as React.RefObject<HTMLInputElement> : undefined}
```

The ref is typed as `HTMLButtonElement` but is cast to `HTMLInputElement` at the assignment site. While functional, the type mismatch requires a cast.

**Fix:** Type the ref as `useRef<HTMLElement>(null)` to avoid the cast.

---

### P3-15: DevBanner - Minimal component with no error handling needed

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dev/DevBanner.tsx`
**Category:** N/A

This is a 13-line dev-only component. No issues found. Noted for completeness.

---

## Summary Statistics

| Severity | Count | Description |
|----------|-------|-------------|
| **P0** | 5 | Missing await, incorrect keys, a11y blockers |
| **P1** | 14 | UX bugs, a11y gaps, security, memory leaks |
| **P2** | 18 | Type safety, DRY violations, CSS inconsistency |
| **P3** | 15 | Tech debt, i18n, test coverage, minor typing |
| **Total** | **52** | |

### Category Breakdown

| Category | P0 | P1 | P2 | P3 | Total |
|----------|----|----|----|----|-------|
| Accessibility (a11y) | 2 | 4 | 3 | 4 | **13** |
| React correctness | 2 | 0 | 0 | 0 | **2** |
| Bug / incorrect logic | 1 | 0 | 1 | 0 | **2** |
| UX / misleading behavior | 0 | 2 | 0 | 1 | **3** |
| Hardcoded values | 0 | 3 | 2 | 1 | **6** |
| CSS inconsistency | 0 | 0 | 4 | 0 | **4** |
| TypeScript typing | 0 | 0 | 1 | 4 | **5** |
| Memory leak | 0 | 1 | 2 | 0 | **3** |
| Security | 0 | 1 | 0 | 0 | **1** |
| Missing error states | 0 | 1 | 2 | 1 | **4** |
| DRY / duplication | 0 | 0 | 2 | 2 | **4** |
| Performance / memoization | 0 | 0 | 1 | 0 | **1** |
| Test coverage | 0 | 0 | 0 | 1 | **1** |
| i18n | 0 | 0 | 0 | 1 | **1** |
| React key misuse | 0 | 2 | 0 | 0 | **2** |

### Files Audited (by subdirectory)

| Subdirectory | Files | Findings |
|-------------|-------|----------|
| `agent/` | 1 | 2 |
| `affiliate/` | 1 | 1 |
| `alerts/` | 2 | 0 |
| `analytics/` | 4 | 5 |
| `auth/` | 2 | 0 |
| `cca/` | 3 | 4 |
| `charts/` | 4 | 0 |
| `community/` | 5 | 1 |
| `community-solar/` | 2 | 1 |
| `connections/` | 15 | 6 |
| `connections/analytics/` | 6 | 3 |
| `dashboard/` | 11 | 1 |
| `dev/` | 4 | 2 |
| `feedback/` | 1 | 1 |
| `gamification/` | 1 | 1 |
| `gas/` | 1 | 1 |
| `heating-oil/` | 3 | 3 |
| `layout/` | 4 | 2 |
| `onboarding/` | 5 | 0 |
| `prices/` | 1 | 1 |
| `propane/` | 3 | 2 |
| `providers/` | 1 | 1 |
| `pwa/` | 2 | 2 |
| `rate-changes/` | 3 | 1 |
| `seo/` | 1 | 2 |
| `suppliers/` | 7 | 2 |
| `ui/` | 7 | 0 |
| `water/` | 4 | 3 |
| Root (`error-boundary`, `page-error-fallback`) | 2 | 1 |

### Positive Observations

Components and patterns that are well-implemented:

1. **FeedbackWidget** (`feedback/FeedbackWidget.tsx`) - Excellent accessibility: focus trap, Escape key handling, proper ARIA attributes, keyboard navigation, `aria-describedby` for error states.

2. **Modal component** (`ui/modal.tsx`) - Production-quality modal with focus trap, Escape key, scroll lock, backdrop click, and focus restoration. Should be used by other components (see P0-04).

3. **BillUploadDropZone** (`connections/BillUploadDropZone.tsx`) - Good keyboard accessibility with `role="button"`, `tabIndex={0}`, and `onKeyDown` handler for Enter/Space.

4. **ConnectionRates** (`connections/ConnectionRates.tsx`) - Comprehensive accessibility: `scope="col"` on table headers, `aria-label` on table, `role="status"` on loading, `role="alert"` on errors, `aria-hidden` on decorative icons.

5. **VoteButton** (`community/VoteButton.tsx`) - Well-implemented optimistic UI with error rollback pattern.

6. **BillUploadProgressBar** (`connections/BillUploadProgress.tsx`) - Proper `role="progressbar"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, and GPU-composited `transform:scaleX()` animation.

7. **DashboardTabs** (`dashboard/DashboardTabs.tsx`) - Proper `role="tab"`, `aria-selected`, and tab panel association.

8. **AlertPreferences** (`rate-changes/AlertPreferences.tsx`) - Custom toggle switch with proper `role="switch"` and `aria-checked`.

9. **Input component** (`ui/input.tsx`) - Auto-generated IDs, `aria-invalid`, `aria-describedby`, error and helper text support.

10. **Error boundary** (`error-boundary.tsx`) - Class-based ErrorBoundary with reset capability and user-friendly fallback UI.
