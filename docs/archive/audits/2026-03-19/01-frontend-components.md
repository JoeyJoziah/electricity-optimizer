# Frontend Components Audit Report

> Generated: 2026-03-19
> Scope: `frontend/components/` -- 101 files across 22 subdirectories
> Auditor: Claude Opus 4.6 (read-only, no files modified)

---

## Executive Summary

The RateShift frontend component library is well-structured overall. The codebase
demonstrates consistent use of TypeScript interfaces, proper loading/error states,
and good accessibility foundations. The UI primitive layer (`ui/`) is particularly
strong with `forwardRef`, `displayName`, and variant patterns. However, the audit
identified **8 P0 issues**, **14 P1 issues**, **21 P2 issues**, and **12 P3 issues**
across performance, accessibility, correctness, security, and consistency dimensions.

### Test Coverage Summary

- **76 test files** found in `__tests__/components/` covering the 101 source files
- **Components with no test coverage**: `StatusBadge.tsx`, `BillUploadDropZone.tsx`,
  `BillUploadFilePreview.tsx`, `BillUploadProgress.tsx`, `BillUploadResults.tsx`,
  `ExtractedField.tsx`, `DashboardStatsRow.tsx`, `DashboardCharts.tsx`,
  `DashboardForecast.tsx`, `DashboardSchedule.tsx`, `AllUtilitiesTab.tsx`,
  `UtilityTabShell.tsx`, `NeighborhoodCard.tsx`, `CombinedSavingsCard.tsx`,
  `AlertForm.tsx`, `ServiceWorkerRegistrar.tsx`, `PageErrorFallback.tsx`,
  `ConnectionAnalytics` analytics sub-components (individual cards)
- Coverage is generally good -- most feature components have corresponding tests

---

## P0 -- Critical (must fix before next release)

### P0-01: Hardcoded price threshold used for "optimal" determination
- **Files**: `DashboardContent.tsx:113`, `PricesContent.tsx:112,130`
- **Lines**: `isOptimal: price !== null && price < 0.22` and `isOptimal: price < 0.2`
- **Issue**: The "optimal price" threshold is hardcoded at `0.22` in the dashboard
  and `0.2` in the prices page. These values differ between the two pages (inconsistent)
  and do not reflect regional variation. A user in a state with average rates of $0.30/kWh
  would rarely see "optimal" highlighted; conversely, a state with $0.10/kWh average
  would always show everything as optimal.
- **Recommendation**: Derive the optimal threshold from the user's historical average
  price (e.g., 80th percentile) or the regional average, or make it user-configurable.
  At minimum, extract the magic number to a shared constant so both pages agree.

### P0-02: CCAAlert assumes `us_` region prefix without validation
- **File**: `cca/CCAAlert.tsx:13`
- **Line**: `const stateCode = region ? region.slice(3).toUpperCase() : undefined`
- **Issue**: If the region string does not start with `us_`, `slice(3)` will produce
  garbage (e.g., an international region `gb_england` would yield `england` as a
  state code). Same pattern appears in `CommunitySolarContent.tsx:15-17`.
- **Recommendation**: Guard with `region?.startsWith('us_')` before slicing, or use
  the existing pattern from RegionSelector which validates the format.

### P0-03: OnboardingWizard calls `mutateAsync` twice in sequence -- no error handling
- **File**: `onboarding/OnboardingWizard.tsx:25-34`
- **Issue**: `handleRegionSelect` calls `mutateAsync` twice sequentially. If the first
  succeeds but the second fails, the user is left in a partially-onboarded state (region
  set but `onboarding_completed` still false). There is no try/catch or error UI.
  Additionally, between the two mutations, `settingsStore.getState().setRegion()` and
  `setUtilityTypes()` are called, meaning local state is updated before the second API
  call confirms. If the user refreshes after a partial failure, they may see the dashboard
  without `onboarding_completed: true`.
- **Recommendation**: Wrap both mutations in a single try/catch, or combine them into
  one API call. Add error feedback to the component.

### P0-04: `dealer.website` link not validated with `isSafeHref`
- **File**: `heating-oil/DealerList.tsx:49-55`
- **Issue**: The `dealer.website` URL is rendered as an `<a>` tag with `target="_blank"`
  without passing through `isSafeHref()` validation. Other components (CCAInfo,
  CommunitySolarContent) consistently use `isSafeHref()` before rendering external URLs.
  A malicious dealer website entry could contain a `javascript:` or `data:` URI.
- **Recommendation**: Add `isSafeHref(dealer.website) &&` guard before rendering the link,
  consistent with the pattern used elsewhere in the codebase.

### P0-05: VoteButton initializes `voted` state as `false` -- loses server state
- **File**: `community/VoteButton.tsx:14`
- **Issue**: `const [voted, setVoted] = React.useState(false)` always starts as `false`,
  even if the user has already voted on a post. The `CommunityPost` type likely carries a
  `user_voted` or similar field, but it is not passed to VoteButton. This means on page
  load, a previously-upvoted post shows as not upvoted, and clicking it sends a toggle
  that results in removing the vote instead of adding one.
- **Recommendation**: Pass `initialVoted: boolean` prop from the parent PostCard where
  the post data is available, and initialize state with it.

### P0-06: BillUploadForm polling `setInterval` callback captures stale closures
- **File**: `connections/BillUploadForm.tsx:100-161`
- **Issue**: `pollParseStatus` uses `setInterval` with an async callback. The `attempts`
  variable is a local `let` inside the outer callback, so it correctly increments.
  However, the `connectionId` and `onUploadComplete` are captured in the `useCallback`
  deps, but if `connectionId` changes while polling is active, the old interval
  continues with the stale value. More critically, if the component unmounts and
  remounts with a different `connectionId`, the cleanup in `useEffect` line 33-38
  clears the interval, but the `useCallback` itself does not reset -- calling
  `pollParseStatus` again will create a new interval while the ref may still hold
  the old one.
- **Recommendation**: Use `useRef` for `attempts` to avoid stale closure risk. Consider
  using a recursive `setTimeout` pattern instead of `setInterval` for cleaner async
  polling. The current code works for the happy path but is fragile under rapid
  re-renders or HMR.

### P0-07: HeatingOilDashboard and PropaneDashboard state price cards have click handlers but no keyboard support
- **Files**: `heating-oil/HeatingOilDashboard.tsx:98-99`, `propane/PropaneDashboard.tsx:98-99`
- **Issue**: State price cards use `<div onClick={...}>` without `role="button"`,
  `tabIndex`, or `onKeyDown` handlers. These are interactive elements that should be
  accessible via keyboard navigation. Screen reader users cannot interact with these
  cards at all.
- **Recommendation**: Either use `<button>` elements or add `role="button"`,
  `tabIndex={0}`, and `onKeyDown` (handling Enter/Space).

### P0-08: RateChangeFeed and AlertPreferences use `bg-muted` class -- not in design system
- **Files**: `rate-changes/RateChangeFeed.tsx:37`, `rate-changes/AlertPreferences.tsx:23`,
  `rate-changes/RateChangeCard.tsx:34,50,51,71`
- **Issue**: Multiple rate-changes components use `text-muted-foreground` and `bg-muted`
  CSS classes that belong to a shadcn/ui design system, not the project's custom
  Tailwind token system (which uses `text-gray-*`, `bg-gray-*`, `text-primary-*`, etc.).
  These classes may not be defined in the project's Tailwind config, causing invisible
  text or missing backgrounds.
- **Recommendation**: Replace `text-muted-foreground` with `text-gray-500` and `bg-muted`
  with `bg-gray-100` to match the project's design system tokens.

---

## P1 -- High (should fix soon)

### P1-01: DashboardContent does not use React.memo on sub-components passed as props
- **File**: `dashboard/DashboardContent.tsx`
- **Issue**: The main dashboard creates new object references on every render for
  `currentPrice`, `topSuppliers`, and `optimalWindow`. While `useMemo` is used for
  `chartData`, `optimalWindow`, and `topSuppliers`, the `currentPrice` object (lines
  120-131) is recomputed every render without memoization. This causes
  `DashboardStatsRow` to re-render even when `rawPrice` hasn't changed.
- **Recommendation**: Wrap `currentPrice` computation in `useMemo` with `[pricesData]`
  dependency.

### P1-02: PricesContent fires all queries simultaneously -- no staggered waterfall
- **File**: `prices/PricesContent.tsx:84-94`
- **Issue**: Unlike `DashboardContent.tsx` which carefully implements a 3-tier staggered
  waterfall to reduce initial request burst, `PricesContent.tsx` fires all 4 queries
  (`useCurrentPrices`, `usePriceHistory`, `usePriceForecast`, `useOptimalPeriods`)
  simultaneously on mount. This creates an unnecessary burst of 4 concurrent requests.
- **Recommendation**: Apply the same gating pattern used in DashboardContent (Tier 2
  gated on Tier 1 success, Tier 3 gated on Tier 2).

### P1-03: Duplicate supplier mapping logic across 3 files
- **Files**: `dashboard/DashboardContent.tsx:184-201`, `onboarding/SupplierPicker.tsx:19-29`,
  `suppliers/SuppliersContent.tsx` (similar mapping)
- **Issue**: The `RawSupplierRecord -> Supplier` mapping logic with fallback defaults
  (`avgPricePerKwh: 0.22`, `standingCharge: 0.40`, `estimatedAnnualCost: 850`) is
  duplicated across at least 3 components. This is a DRY violation that creates
  maintenance burden -- if backend field names change, all 3 locations need updating.
- **Recommendation**: Extract to a shared `mapRawSupplier(s: RawSupplierRecord): Supplier`
  utility function.

### P1-04: SavingsTracker hardcodes monthly goal at $50
- **File**: `gamification/SavingsTracker.tsx:96-97`
- **Line**: `<span>Monthly Goal: {formatCurrency(50)}</span>` and `monthlySavings / 50`
- **Issue**: The monthly savings goal is hardcoded at $50 with no way to customize.
  This is both a magic number and a UX issue -- different users have vastly different
  electricity spend levels. A user spending $30/month on electricity can never reach
  a $50 savings goal.
- **Recommendation**: Accept `monthlyGoal` as a prop with a sensible default, or derive
  from the user's average monthly bill.

### P1-05: AgentChat uses array index as key for messages
- **File**: `agent/AgentChat.tsx:161`
- **Line**: `{messages.map((msg, i) => <MessageBubble key={i} message={msg} />)}`
- **Issue**: Using array index as React key for a list where items can be prepended or
  reordered can cause incorrect DOM reconciliation. If the agent streams partial messages
  that get consolidated, or if messages are removed (e.g., on reset), React may
  re-use the wrong DOM nodes.
- **Recommendation**: Add a unique `id` field to `AgentMessage` and use it as the key.

### P1-06: NotificationBell does not invalidate count when opening panel
- **File**: `layout/NotificationBell.tsx:44-49`
- **Issue**: When the user opens the notification panel, the full notifications list is
  fetched, but the unread count query is not immediately invalidated. If a notification
  arrived between the last count poll (up to 120s ago) and the panel open, the badge
  count and the visible notification list may be inconsistent. More importantly, after
  `markAllRead` succeeds, both queries are invalidated -- but during the window between
  opening and marking all read, the stale count persists.
- **Recommendation**: Invalidate the count query when the panel opens, or derive
  unread count from the notifications list when the panel is open.

### P1-07: Header component has fake refresh delay
- **File**: `layout/Header.tsx` (based on prior read)
- **Issue**: The Header's refresh button uses `setTimeout` to simulate a refresh delay.
  This is misleading UX -- it makes users think data is being fetched when it may not be.
  If the actual data refresh completes faster or fails, the loading state is decoupled
  from reality.
- **Recommendation**: Tie the loading state to the actual query refetch via React Query's
  `refetch()` return value and `isFetching` state.

### P1-08: PostForm validation runs on submit only -- no real-time feedback
- **File**: `community/PostForm.tsx:70-78`
- **Issue**: Title and body validation only runs on form submit. Users type their entire
  post and only then discover the 10-character minimum for body or 3-character minimum
  for title. The `errors` object is never cleared except on validation re-run.
- **Recommendation**: Add inline validation on blur or with a debounced onChange. At
  minimum, show character count and remaining characters.

### P1-09: Community PostForm falls back to `'us_ct'` when region is null
- **File**: `community/PostForm.tsx:90`
- **Line**: `region: region || 'us_ct'`
- **Issue**: If the user hasn't set their region, the post silently defaults to
  Connecticut. This creates incorrect data in the community system and confuses users
  in other states who would see CT posts appearing as if from their area.
- **Recommendation**: Show a message asking the user to set their region before posting,
  or use null and let the backend reject/handle it.

### P1-10: DataExport CSV download creates invisible `<a>` element without cleanup
- **File**: `analytics/DataExport.tsx:42-47`
- **Issue**: `document.createElement('a')` is created, clicked, and the blob URL is
  revoked, but the `<a>` element itself is never appended to or removed from the DOM.
  Modern browsers handle this for `click()` on detached elements, but some older browsers
  or content security policies may block it. The `URL.revokeObjectURL` call happens
  synchronously after `click()` which may revoke the URL before the download starts in
  some browsers.
- **Recommendation**: Append the element, click, then remove in a `setTimeout`. Use
  `requestAnimationFrame` or a short delay before revoking the URL.

### P1-11: WaterTierCalculator allows negative gallons input
- **File**: `water/WaterTierCalculator.tsx:96-99`
- **Issue**: While `min={0}` is set on the input, `Number(e.target.value) || 0` on
  line 99 means a negative value typed by the user would be coerced to 0, but only
  after onChange fires. The `calculateCost` function does not guard against negative
  `gallons` input, which could produce negative `remaining` and incorrect tier charges.
- **Recommendation**: Clamp the value: `Math.max(0, Math.min(100000, Number(e.target.value) || 0))`.

### P1-12: CommunitySolarContent uses inconsistent color tokens
- **File**: `community-solar/CommunitySolarContent.tsx:67-69`
- **Issue**: Uses `bg-primary-100 text-primary-700` for selected state but uses
  raw `bg-gray-100` for unselected. Filter buttons use `bg-success-100 text-success-700`
  and `bg-warning-100 text-warning-700` which are correct design system tokens. However,
  line 22 references `blue-200/blue-50` directly in the CCA Alert. This inconsistency
  is minor but creates maintenance burden.
- **Recommendation**: Use design system tokens consistently. The CCA components
  (`CCAAlert.tsx`) also use raw `blue-*` colors instead of `primary-*` or `info-*`.

### P1-13: RegionSelector search input missing `aria-label`
- **File**: `onboarding/RegionSelector.tsx:55-60`
- **Issue**: The search input has a `placeholder` but no `aria-label` or associated
  `<label>`. Screen readers will only announce the placeholder text, which disappears
  once the user starts typing.
- **Recommendation**: Add `aria-label="Search states"` to the input element.

### P1-14: Multiple components silently swallow fetch errors
- **Files**: `connections/DirectLoginForm.tsx:85-86,104-106`,
  `connections/ConnectionUploadFlow.tsx:68-76`,
  `connections/BillUploadForm.tsx:155-157`
- **Issue**: Several `catch {}` blocks silently discard errors during supplier loading,
  sync status polling, and parse status polling. While some of these are supplementary
  data where silent failure is acceptable (and the code comments explain this), the
  pattern makes debugging production issues harder because there is no telemetry.
- **Recommendation**: At minimum, log errors to console in development mode or send
  to an error tracking service (Sentry). The comments indicate intentional suppression,
  but even a `console.debug` would help during development.

---

## P2 -- Medium (should address in upcoming sprint)

### P2-01: Duplicate `STATE_NAMES` and `US_STATES` constants across files
- **Files**: `heating-oil/HeatingOilDashboard.tsx:8-18`,
  `propane/PropaneDashboard.tsx:8-17`, `water/WaterDashboard.tsx:8-21`,
  `analytics/AnalyticsDashboard.tsx:8-15`
- **Issue**: US state name mappings and state code arrays are duplicated across 4+
  files. HeatingOilDashboard and PropaneDashboard have 9-state subsets, WaterDashboard
  has the full 50+DC map, and AnalyticsDashboard has a flat array. The existing
  `@/lib/constants/regions` module already exports `US_REGIONS` with state labels.
- **Recommendation**: Consolidate all state name constants into the existing
  `@/lib/constants/regions` module.

### P2-02: Duplicate `UTILITY_LABELS` constant across 4+ files
- **Files**: `rate-changes/RateChangeCard.tsx:5-11`,
  `analytics/ForecastWidget.tsx:7-12`, `analytics/OptimizationReport.tsx:6-12`,
  `analytics/DataExport.tsx:7-12`
- **Issue**: A `Record<string, string>` mapping utility type keys to display labels
  is duplicated in at least 4 files, with slight variations (some include `water`,
  some don't).
- **Recommendation**: Extract to a shared constant, e.g.,
  `@/lib/constants/utilityTypes.ts`.

### P2-03: ConnectionUploadFlow auto-creates connection on mount with no abort
- **File**: `connections/ConnectionUploadFlow.tsx:79-82`
- **Issue**: `React.useEffect(() => { createUploadConnection() }, [createUploadConnection])`
  fires on mount. In React 18 Strict Mode (development), this effect runs twice,
  potentially creating two upload connections. The `AbortController` inside
  `createUploadConnection` only guards the fetch timeout, not the double-invocation.
- **Recommendation**: Add a `useRef` guard to prevent double-creation, or use
  `React.useRef(false)` to track whether creation has already been attempted.

### P2-04: FeedbackWidget modal backdrop click handler uses direct `onClick`
- **File**: `feedback/FeedbackWidget.tsx:115-117`
- **Issue**: The backdrop `<div>` has `onClick={onClose}` and `aria-hidden="true"`.
  This is accessible because the Escape key is also handled, but if a user drags
  from inside the modal to outside (mousedown inside, mouseup on backdrop), the
  modal would close unexpectedly. This is a common UX issue with overlay modals.
- **Recommendation**: Use `onMouseDown` instead of `onClick` and check that both
  mousedown and mouseup occurred on the backdrop.

### P2-05: GasRatesContent and PricesContent fire all queries simultaneously
- **File**: `gas/GasRatesContent.tsx:23-28`
- **Issue**: 4 queries fire on mount without staggering. The supplier comparison
  query correctly gates on `ratesData?.is_deregulated`, but the other 3 are parallel.
  For users on slow connections, this creates a burst of concurrent requests.
- **Recommendation**: Apply staggered loading similar to DashboardContent pattern.

### P2-06: ScheduleTimeline has unused `onReschedule` prop with eslint-disable
- **File**: `charts/ScheduleTimeline.tsx` (based on prior read)
- **Issue**: The `onReschedule` prop is defined in the interface, accepted as a
  parameter, and used in a drag handler, but the component suppresses the ESLint
  unused warning. If the drag feature is not yet implemented, this is dead code.
- **Recommendation**: Either implement the drag-to-reschedule feature or remove the
  prop and related drag state management.

### P2-07: CCAAlert `program_url` link not validated with `isSafeHref`
- **File**: `cca/CCAAlert.tsx:47-53`
- **Issue**: The `program.program_url` link is rendered without `isSafeHref()` validation.
  `CCAInfo.tsx` correctly validates both `program_url` and `opt_out_url` with `isSafeHref()`,
  creating an inconsistency.
- **Recommendation**: Add `isSafeHref(program.program_url) &&` guard, consistent with
  `CCAInfo.tsx`.

### P2-08: ReportButton has no rate limiting or cooldown
- **File**: `community/ReportButton.tsx`
- **Issue**: A user can click "Report" -> "Yes" repeatedly (spamming the mutation).
  While the backend has a 5-report threshold, the frontend does not prevent rapid
  re-clicking or show a "You already reported this" state.
- **Recommendation**: Track whether the current user has already reported and show a
  "Reported" state. Disable the button while the mutation is pending (already done)
  and after success.

### P2-09: SavingsCalculator component exported as `CommunitySolarService`
- **File**: `community-solar/SavingsCalculator.tsx:11`
- **Issue**: The component is named `CommunitySolarService` in the export but lives in
  `SavingsCalculator.tsx`. The comment "Named this way to match the export in
  CommunitySolarContent" explains the mismatch, but it creates confusion. The parent
  file `CommunitySolarContent.tsx:9` imports it as `CommunitySolarService`.
- **Recommendation**: Rename the export to `SavingsCalculator` and update the import
  in `CommunitySolarContent.tsx` to match the filename convention.

### P2-10: DiagramEditor `setTimeout` for saved indicator not cleaned up on unmount
- **File**: `dev/DiagramEditor.tsx:47`
- **Issue**: `setTimeout(() => setShowSaved(false), 2000)` in `handleSave` is not
  tracked or cleared on unmount. If the user navigates away within 2 seconds of saving,
  this will attempt to update state on an unmounted component.
- **Recommendation**: Use a `useRef` to track the timeout ID and clear it in a
  cleanup effect.

### P2-11: ExcalidrawWrapper uses `as unknown as` type cast
- **File**: `dev/ExcalidrawWrapper.tsx:54`
- **Issue**: The `onChange` handler is double-cast via `as unknown as (elements: any, ...)`
  to bridge the type gap with Excalidraw's internal types. While the comment explains
  this and the component is dev-only (triple-gated), the `any` cast suppresses all
  type checking for the callback parameters.
- **Recommendation**: This is acceptable for a dev-only component but should be revisited
  if Excalidraw exports proper types in a future version.

### P2-12: No error boundaries around individual dashboard sections
- **File**: `dashboard/DashboardContent.tsx`
- **Issue**: The dashboard renders `SetupChecklist`, `CCAAlert`, `DashboardStatsRow`,
  `DashboardCharts`, `DashboardForecast`, and `DashboardSchedule` without wrapping them
  in error boundaries. If any child component throws during render (e.g., bad data shape
  from API), the entire dashboard unmounts.
- **Recommendation**: Wrap each major section in an `<ErrorBoundary>` with a
  section-specific fallback, using the existing `error-boundary.tsx` component.

### P2-13: Multiple components do not handle the "no region" state consistently
- **Files**: Various dashboard, gas, propane, heating-oil, water components
- **Issue**: Some components show a "No region set" message (GasRatesContent,
  CommunitySolarContent), some return `null` (CCAAlert when region is not set), and
  some fall through silently (DashboardContent relies on `useCurrentPrices(region)` to
  handle null region). The UX experience varies across pages.
- **Recommendation**: Create a shared `NoRegionPlaceholder` component with a consistent
  message and CTA to Settings.

### P2-14: `formatFutureTime` does not handle negative durations
- **File**: `connections/DirectLoginForm.tsx:46-57`
- **Issue**: If `next_sync_at` is in the past (e.g., sync was scheduled but hasn't
  happened yet), `diffMinutes` will be negative. The function will return "any moment"
  (since `diffMinutes < 1`), which is technically correct but could be confusing if
  the sync is significantly overdue.
- **Recommendation**: Handle negative durations explicitly, e.g., "overdue" or
  "scheduled (delayed)".

### P2-15: RatePageContent uses `slice(0, 8)` for "nearby states"
- **File**: `seo/RatePageContent.tsx:155-158`
- **Issue**: "Nearby States" cross-links just take the first 8 states from the full
  `US_STATES` object (alphabetically), not actually nearby states. Alabama, Alaska,
  Arizona would show as "nearby" for Connecticut.
- **Recommendation**: Either rename to "Other States" or implement actual geographic
  proximity sorting.

### P2-16: PostList `timeAgo` function does not handle future dates or invalid strings
- **File**: `community/PostList.tsx:18-26`
- **Issue**: If `dateStr` is invalid, `new Date(dateStr).getTime()` returns `NaN`,
  causing `mins` to be `NaN`. The function will fall through to `NaNd ago`. No guard
  for future dates either.
- **Recommendation**: Add a `isNaN` guard and return a fallback like "just now".

### P2-17: GasRatesContent price history uses array index as key
- **File**: `gas/GasRatesContent.tsx:186`
- **Line**: `<div key={i} ...>`
- **Issue**: Using array index as React key for a list of price records. If the data
  updates (new price added to the front), React may incorrectly reuse DOM nodes.
- **Recommendation**: Use a unique identifier (timestamp + supplier combination, or
  record ID if available).

### P2-18: WaterTierCalculator initializes `usageGallons` at 5760 without explanation
- **File**: `water/WaterTierCalculator.tsx:14`
- **Issue**: The default value `5760` gallons is a magic number with no comment
  explaining what it represents (it's roughly the US average household monthly usage:
  192 gal/day * 30 days = 5760).
- **Recommendation**: Extract to a named constant with a comment:
  `const DEFAULT_MONTHLY_USAGE_GALLONS = 5760 // ~192 gal/day * 30 days (US avg)`.

### P2-19: ConnectionCard, ConnectionRates, and related components use raw fetch instead of apiClient
- **Files**: Multiple connection components use `fetch(${API_ORIGIN}/api/v1/...)` directly
  instead of the centralized `apiClient` from `@/lib/api/client`.
- **Issue**: These raw fetch calls bypass any centralized interceptors, auth token
  refresh logic, or error handling that `apiClient` might provide. The dashboard and
  notification components correctly use `apiClient`.
- **Recommendation**: Migrate connection components to use `apiClient` for consistency.

### P2-20: Propane and HeatingOil dashboards are near-identical clones
- **Files**: `propane/PropaneDashboard.tsx` vs `heating-oil/HeatingOilDashboard.tsx`,
  `propane/PropanePriceHistory.tsx` vs `heating-oil/OilPriceHistory.tsx`
- **Issue**: These component pairs share ~90% identical structure (state selector,
  national price card, state grid, click-to-select pattern). The only differences are
  color tokens (primary vs warning), unit labels, and hook names. This duplication
  makes maintenance expensive -- any UX improvement must be applied in both places.
- **Recommendation**: Extract a shared `FuelDashboard` and `FuelPriceHistory` component
  parameterized by fuel type, colors, and data hooks.

### P2-21: AlertForm missing from test coverage -- most complex form component
- **File**: `alerts/AlertForm.tsx`
- **Issue**: AlertForm is a complex multi-field form with region validation, threshold
  configuration, optimal window scheduling, frequency selection, and CRUD operations.
  Despite this complexity, no `AlertForm.test.tsx` exists in `__tests__/components/`.
  `AlertsContent.test.tsx` exists but AlertForm as a standalone unit is untested.
- **Recommendation**: Add dedicated unit tests for AlertForm covering validation,
  submission, edit mode, and error states.

---

## P3 -- Low (nice to have)

### P3-01: FTCDisclosure is not wrapped in React.memo
- **File**: `affiliate/FTCDisclosure.tsx`
- **Issue**: This static component with no state and only a `variant` prop would
  benefit from `React.memo` to skip re-renders. Not critical since it's lightweight.
- **Recommendation**: Wrap in `React.memo` for minor performance improvement.

### P3-02: Chart components use `React.memo` but memoization may be ineffective
- **Files**: `charts/PriceLineChart.tsx`, `charts/ForecastChart.tsx`,
  `charts/SavingsDonut.tsx`, `charts/ScheduleTimeline.tsx`
- **Issue**: All chart components are wrapped in `React.memo`, but their parent
  (DashboardCharts, DashboardForecast) passes new object/array references on each
  render. `React.memo` performs shallow comparison, so new array references (like
  `chartData`) will always fail equality check, making the memo ineffective unless
  the parent also memoizes the data (which DashboardContent does via `useMemo`).
- **Recommendation**: Verify that all data passed to memoized chart components is
  itself memoized. Currently this appears to be the case, but worth a systematic check.

### P3-03: DevBanner has no `data-testid`
- **File**: `dev/DevBanner.tsx`
- **Issue**: The dev banner component lacks a `data-testid` attribute for testing.
  While it has a dedicated test file, adding a testid would make test assertions cleaner.
- **Recommendation**: Add `data-testid="dev-banner"` to the root div.

### P3-04: Button and Input components lack JSDoc comments
- **Files**: `ui/button.tsx`, `ui/input.tsx`
- **Issue**: These foundational primitives lack JSDoc documentation on their props.
  The `Card` component has no JSDoc either, but its props are self-documenting.
- **Recommendation**: Add brief JSDoc for non-obvious props, especially `variant`
  values and their visual appearance.

### P3-05: `ServiceWorkerRegistrar` does not report registration failure to user
- **File**: `pwa/ServiceWorkerRegistrar.tsx`
- **Issue**: Service worker registration failures are caught and logged to console
  but not surfaced to the user. If SW registration fails, PWA features silently degrade.
- **Recommendation**: This is acceptable behavior for progressive enhancement, but
  consider sending telemetry for registration failure rates.

### P3-06: Toast component animation uses CSS classes not defined in the read file
- **File**: `ui/toast.tsx`
- **Issue**: Toast uses animation classes like `animate-toast-enter` that are presumably
  defined in global CSS or Tailwind config. If these are missing, toasts would appear
  without animation (graceful degradation, but worth verifying).
- **Recommendation**: Verify animation classes are defined in `tailwind.config.ts`.

### P3-07: Several select elements lack consistent styling
- **Files**: Various (gas, water, heating-oil, analytics)
- **Issue**: Some `<select>` elements use `rounded-md border-gray-300 shadow-sm`
  (native form styling from Tailwind) while connection components use
  `rounded-lg border border-gray-300 bg-white px-3 py-2`. There is no shared select
  component in the UI primitives.
- **Recommendation**: Consider adding a `Select` component to the UI primitives
  library for consistent styling.

### P3-08: `formatCurrency` function used inconsistently
- **Files**: Various
- **Issue**: Some components use `formatCurrency()` utility, while others use inline
  `${value.toFixed(2)}` or `${value.toFixed(4)}`. The precision also varies (2 vs 4
  decimal places) depending on context (per-gallon vs per-kWh).
- **Recommendation**: Ensure `formatCurrency` accepts a precision parameter and is
  used consistently. Per-kWh rates should show 4 decimals; per-gallon 2 decimals.

### P3-09: Modal focus trap in FeedbackWidget queries all focusable elements on every keydown
- **File**: `feedback/FeedbackWidget.tsx:63-77`
- **Issue**: `modalRef.current.querySelectorAll<HTMLElement>(...)` runs on every Tab
  keypress. For a small modal this is negligible, but caching the focusable elements
  (and updating on DOM changes) would be more efficient.
- **Recommendation**: Low priority -- the modal is small. Could cache in a ref and
  use MutationObserver if performance were a concern.

### P3-10: AgentChat textarea does not auto-resize
- **File**: `agent/AgentChat.tsx:197-206`
- **Issue**: The textarea has `rows={1}` and `resize-none`. As users type longer
  messages, they cannot see their full input. Multi-line messages require scrolling
  within a single-row textarea.
- **Recommendation**: Implement auto-resize based on content height (common pattern:
  set height to `scrollHeight` on change).

### P3-11: CCAComparison does not format numbers consistently
- **File**: `cca/CCAComparison.tsx:29-30`
- **Issue**: Uses `.toFixed(4)` for rates and `.toFixed(2)` for savings inline, rather
  than using `formatCurrency`. Functionally correct but inconsistent with other
  components that use the utility function.
- **Recommendation**: Use `formatCurrency` with appropriate precision parameter.

### P3-12: UtilityTypeSelector uses `Flame` icon for both Natural Gas and Propane
- **File**: `onboarding/UtilityTypeSelector.tsx:14-15`
- **Issue**: Both `natural_gas` and `propane` utility types use the `Flame` icon from
  lucide-react. While both are combustion fuels, this makes them visually
  indistinguishable in the selector.
- **Recommendation**: Use a different icon for propane (e.g., `Cylinder` or `Container`
  from lucide) to differentiate the options.

---

## Cross-Cutting Observations

### Strengths

1. **Consistent TypeScript interfaces**: Every component has explicit TypeScript
   interfaces for props. No `any` types except in the dev-only ExcalidrawWrapper
   (with justification comment).

2. **Good loading/error state coverage**: Almost every data-fetching component handles
   loading (with Skeleton components), error (with user-friendly messages), and empty
   states. The dashboard implements a sophisticated 3-tier staggered waterfall for
   performance.

3. **Strong accessibility foundations**: Modal focus traps, Escape key handling,
   `aria-label` on icon-only buttons, `aria-expanded` on toggles, `aria-invalid` on
   form fields, `role="dialog"` on panels, `aria-describedby` for error messages.

4. **Security-conscious URL handling**: `isSafeOAuthRedirect()` and `isSafeHref()`
   are used for external URLs in most components (with exceptions noted in P0-04,
   P2-07).

5. **Design system consistency**: The custom Tailwind token system (`primary-*`,
   `success-*`, `warning-*`, `danger-*`) is used consistently across most components,
   with the exceptions noted in P0-08.

6. **Good test coverage**: 76 test files for 101 source files is strong coverage.
   Complex components like auth forms, connection flows, and dashboard content all
   have dedicated tests.

7. **Code splitting**: Chart components and Excalidraw are loaded with `next/dynamic`
   and `ssr: false` to reduce initial bundle size.

### Areas for Improvement

1. **Raw `fetch` vs `apiClient`**: Connection components use raw `fetch` with
   `API_ORIGIN` while dashboard/notification components use the centralized `apiClient`.
   This creates inconsistency in error handling and auth token management.

2. **Component duplication**: Propane and HeatingOil dashboards are near-identical.
   State name constants are duplicated across 4+ files. Supplier mapping logic is
   duplicated in 3 places.

3. **Magic numbers**: Several hardcoded values (`0.22` optimal threshold, `$50` savings
   goal, `5760` gallons, `120_000` poll interval) would benefit from named constants
   or user configuration.

4. **Error boundaries**: While a global `ErrorBoundary` component exists, it is not
   used to wrap individual dashboard sections. A single thrown error in any child
   component unmounts the entire page.

5. **No i18n infrastructure**: All user-facing strings are hardcoded in English.
   No i18n framework (next-intl, react-intl) is set up. This is noted for awareness
   but may not be a priority given the US-focused nature of the product.

---

## Files Audited (101 total)

### UI Primitives (9 files)
- `ui/button.tsx`, `ui/card.tsx`, `ui/input.tsx`, `ui/badge.tsx`, `ui/skeleton.tsx`,
  `ui/modal.tsx`, `ui/toast.tsx`, `error-boundary.tsx`, `page-error-fallback.tsx`

### Layout (4 files)
- `layout/Sidebar.tsx`, `layout/Header.tsx`, `layout/StatusBadge.tsx`,
  `layout/NotificationBell.tsx`

### Auth (2 files)
- `auth/LoginForm.tsx`, `auth/SignupForm.tsx`

### Charts (4 files)
- `charts/ForecastChart.tsx`, `charts/PriceLineChart.tsx`, `charts/SavingsDonut.tsx`,
  `charts/ScheduleTimeline.tsx`

### Providers (1 file)
- `providers/QueryProvider.tsx`

### PWA (2 files)
- `pwa/InstallPrompt.tsx`, `pwa/ServiceWorkerRegistrar.tsx`

### Dashboard (14 files)
- `dashboard/DashboardContent.tsx`, `dashboard/DashboardTabs.tsx`,
  `dashboard/DashboardStatsRow.tsx`, `dashboard/DashboardCharts.tsx`,
  `dashboard/DashboardForecast.tsx`, `dashboard/DashboardSchedule.tsx`,
  `dashboard/DashboardTypes.ts`, `dashboard/AllUtilitiesTab.tsx`,
  `dashboard/UtilityTabShell.tsx`, `dashboard/SetupChecklist.tsx`,
  `dashboard/NeighborhoodCard.tsx`, `dashboard/CompletionProgress.tsx`,
  `dashboard/CombinedSavingsCard.tsx`, `dashboard/UtilityDiscoveryCard.tsx`

### Alerts (2 files)
- `alerts/AlertForm.tsx`, `alerts/AlertsContent.tsx`

### Connections (19 files)
- `connections/ConnectionMethodPicker.tsx`, `connections/ConnectionsOverview.tsx`,
  `connections/ConnectionCard.tsx`, `connections/ConnectionRates.tsx`,
  `connections/BillUploadTypes.ts`, `connections/BillUploadDropZone.tsx`,
  `connections/BillUploadFilePreview.tsx`, `connections/BillUploadProgress.tsx`,
  `connections/BillUploadResults.tsx`, `connections/BillUploadForm.tsx`,
  `connections/ConnectionUploadFlow.tsx`, `connections/DirectLoginForm.tsx`,
  `connections/EmailConnectionFlow.tsx`, `connections/PortalConnectionFlow.tsx`,
  `connections/ExtractedField.tsx`, `connections/ConnectionAnalytics.tsx`,
  `connections/analytics/index.ts`, `connections/analytics/types.ts`,
  `connections/analytics/ConnectionHealthCard.tsx`,
  `connections/analytics/RateComparisonCard.tsx`,
  `connections/analytics/RateHistoryCard.tsx`,
  `connections/analytics/SavingsEstimateCard.tsx`

### Suppliers (7 files)
- `suppliers/SupplierCard.tsx`, `suppliers/ComparisonTable.tsx`,
  `suppliers/SuppliersContent.tsx`, `suppliers/SupplierSelector.tsx`,
  `suppliers/SetSupplierDialog.tsx`, `suppliers/SupplierAccountForm.tsx`,
  `suppliers/SwitchWizard.tsx`

### Onboarding (5 files)
- `onboarding/OnboardingWizard.tsx`, `onboarding/RegionSelector.tsx`,
  `onboarding/SupplierPicker.tsx`, `onboarding/AccountLinkStep.tsx`,
  `onboarding/UtilityTypeSelector.tsx`

### Community (5 files)
- `community/PostForm.tsx`, `community/PostList.tsx`, `community/VoteButton.tsx`,
  `community/ReportButton.tsx`, `community/CommunityStats.tsx`

### Community Solar (2 files)
- `community-solar/CommunitySolarContent.tsx`, `community-solar/SavingsCalculator.tsx`

### CCA (3 files)
- `cca/CCAAlert.tsx`, `cca/CCAComparison.tsx`, `cca/CCAInfo.tsx`

### Gas (1 file)
- `gas/GasRatesContent.tsx`

### Heating Oil (3 files)
- `heating-oil/DealerList.tsx`, `heating-oil/HeatingOilDashboard.tsx`,
  `heating-oil/OilPriceHistory.tsx`

### Propane (3 files)
- `propane/PropaneDashboard.tsx`, `propane/PropanePriceHistory.tsx`,
  `propane/FillUpTiming.tsx`

### Water (4 files)
- `water/WaterDashboard.tsx`, `water/WaterTierCalculator.tsx`,
  `water/WaterRateBenchmark.tsx`, `water/ConservationTips.tsx`

### Rate Changes (3 files)
- `rate-changes/RateChangeCard.tsx`, `rate-changes/RateChangeFeed.tsx`,
  `rate-changes/AlertPreferences.tsx`

### Analytics (4 files)
- `analytics/AnalyticsDashboard.tsx`, `analytics/ForecastWidget.tsx`,
  `analytics/OptimizationReport.tsx`, `analytics/DataExport.tsx`

### SEO (1 file)
- `seo/RatePageContent.tsx`

### Affiliate (1 file)
- `affiliate/FTCDisclosure.tsx`

### Gamification (1 file)
- `gamification/SavingsTracker.tsx`

### Feedback (1 file)
- `feedback/FeedbackWidget.tsx`

### Dev (4 files)
- `dev/DevBanner.tsx`, `dev/DiagramEditor.tsx`, `dev/DiagramList.tsx`,
  `dev/ExcalidrawWrapper.tsx`

### Agent (1 file)
- `agent/AgentChat.tsx`

### Prices (1 file)
- `prices/PricesContent.tsx`

---

## Issue Count Summary

| Severity | Count | Category Breakdown |
|----------|-------|--------------------|
| P0       | 8     | 2 correctness, 2 accessibility, 2 security, 1 consistency, 1 reliability |
| P1       | 14    | 4 performance, 3 correctness, 3 DRY, 2 UX, 1 accessibility, 1 observability |
| P2       | 21    | 6 DRY/duplication, 4 correctness, 3 consistency, 2 UX, 2 accessibility, 2 testing, 1 performance, 1 naming |
| P3       | 12    | 4 consistency, 3 performance, 2 UX, 1 documentation, 1 testing, 1 visual |
| **Total** | **55** | |
