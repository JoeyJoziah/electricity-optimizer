# Frontend Components Audit

**Date**: 2026-03-23
**Scope**: All 101 files in `frontend/components/` and subdirectories
**Auditor**: Claude Opus 4.6 (automated)

---

## P0 Critical

### 1. Modal uses hardcoded `id="modal-title"` -- breaks with multiple concurrent modals
**File**: `/frontend/components/ui/modal.tsx` (line 67)
The Modal component hardcodes `id="modal-title"` for `aria-labelledby`. If two modals are ever rendered simultaneously (even briefly during transitions), both will share the same ID, violating the HTML spec (IDs must be unique) and breaking screen reader association. The ID should be generated dynamically (e.g., `useId()` from React 19).

### 2. HeatingOilDashboard and PropaneDashboard: clickable `<div>` cards lack keyboard support
**File**: `/frontend/components/heating-oil/HeatingOilDashboard.tsx` (line 98-99)
**File**: `/frontend/components/propane/PropaneDashboard.tsx` (line 98-99)
State price cards use `<div onClick={() => setSelectedState(p.state)}>` with `cursor-pointer` styling, but they are not keyboard-accessible -- no `role="button"`, no `tabIndex`, no `onKeyDown` handler. Keyboard-only and screen reader users cannot interact with these cards at all.

### 3. RatePageContent: supplier table rows keyed by array index `i`
**File**: `/frontend/components/seo/RatePageContent.tsx` (line 100)
`{rateData.suppliers.map((s, i) => <tr key={i}>` uses array index as React key. When suppliers are reordered (e.g., by sorting or data refresh), React will mismatch DOM elements, potentially showing stale data in the wrong rows. Should use `s.supplier` or a composite key.

### 4. BillUploadForm: polling via `setInterval` with async callback creates race conditions
**File**: `/frontend/components/connections/BillUploadForm.tsx` (lines 100-161)
`pollParseStatus` uses `setInterval` with an `async` callback. If a polling response arrives after the component unmounts and the interval is cleared, `setParseResult` will be called on an unmounted component. While React 18+ suppresses the warning, it can still cause state corruption if `onUploadComplete()` triggers navigation mid-poll. The polling should use AbortController to cancel in-flight requests on cleanup.

### 5. GasRatesContent: price history items keyed by array index
**File**: `/frontend/components/gas/GasRatesContent.tsx` (line 184)
`{historyData.prices.slice(0, 20).map((p, i) => <div key={i}>` uses index keys for a list that can change order between renders (new prices prepended). This causes incorrect DOM reuse.

### 6. OptimizationReport: savings opportunities keyed by array index
**File**: `/frontend/components/analytics/OptimizationReport.tsx` (line 114)
`{report.savings_opportunities.map((opp, i) => <div key={i}>` uses index keys for a dynamic list. If opportunities reorder between renders, React will reuse the wrong DOM nodes.

### 7. AgentChat: message list keyed by array index
**File**: `/frontend/components/agent/AgentChat.tsx` (line 160)
`{messages.map((msg, i) => <MessageBubble key={i} message={msg} />)}` uses index keys. As messages stream in and the array grows, this works for append-only patterns. However, the `reset()` function clears all messages, meaning keys `0, 1, 2...` will be reused for entirely different messages, which can cause animation glitches and stale renders if MessageBubble has internal state.

---

## P1 High

### 8. SuppliersContent: inline modal dialogs lack focus trap
**File**: `/frontend/components/suppliers/SuppliersContent.tsx`
The `SwitchWizard` and `SetSupplierDialog` components are rendered as inline overlays within `SuppliersContent` but do not use the `Modal` component. This means they lack focus trapping, Escape key handling, and scroll lock. A keyboard user can Tab out of the wizard into the background content.

### 9. NotificationBell: dropdown panel lacks keyboard navigation
**File**: `/frontend/components/layout/NotificationBell.tsx` (lines 113-157)
The notification dropdown opens via button click with `aria-expanded`, but once open, there is no keyboard navigation for the notification items. The panel should support ArrowUp/ArrowDown navigation and Escape to close. Currently, users must Tab through each notification sequentially with no way to quickly dismiss the panel via keyboard.

### 10. SetSupplierDialog: options use `role="option"` without parent `role="listbox"`
**File**: `/frontend/components/suppliers/SetSupplierDialog.tsx`
Individual supplier options use `role="option"` and `aria-selected`, but the containing `<div>` does not have `role="listbox"`. This is an ARIA violation -- `role="option"` must be a direct child of a `role="listbox"` container. Screen readers will not announce the selection pattern correctly.

### 11. ConnectionCard: 407 lines of complex state management in a single component
**File**: `/frontend/components/connections/ConnectionCard.tsx`
This component handles: inline label editing, sync triggers, delete confirmation modal, status display, error states, and multiple API calls. The state machine logic (editing, syncing, deleting, confirming) should be extracted into a custom hook or split into subcomponents to reduce cognitive complexity.

### 12. CCAAlert: external URL not validated with `isSafeHref`
**File**: `/frontend/components/cca/CCAAlert.tsx` (line 48)
The `program.program_url` is rendered as a raw `<a href>` without `isSafeHref()` validation, unlike other components in the codebase (CommunitySolarContent, CCAInfo) that properly validate external URLs. A compromised backend could inject a `javascript:` URL.

### 13. DealerList: external `dealer.website` URLs not validated
**File**: `/frontend/components/heating-oil/DealerList.tsx` (line 49-55)
`<a href={dealer.website}>` renders untrusted dealer URLs without any validation. Should use `isSafeHref()` consistent with the rest of the codebase.

### 14. AnalyticsDashboard: duplicates US_STATES array locally
**File**: `/frontend/components/analytics/AnalyticsDashboard.tsx` (lines 8-15)
Hardcodes a `US_STATES` array with 51 entries. This is also duplicated in `WaterDashboard.tsx` (lines 8-21), `HeatingOilDashboard.tsx` (lines 8-18), and `PropaneDashboard.tsx` (lines 8-17). The Region enum and `US_REGIONS` constants already exist in `@/lib/constants/regions`. These should use the shared constants.

### 15. DataExport: select elements lack label associations
**File**: `/frontend/components/analytics/DataExport.tsx` (lines 70-96)
Two `<select>` elements for utility type and format have no associated `<label>` or `aria-label`. Screen readers will announce them as unlabeled controls.

### 16. ForecastWidget: select elements lack label associations
**File**: `/frontend/components/analytics/ForecastWidget.tsx` (lines 50-72)
Two `<select>` elements for utility type and forecast horizon have no associated `<label>` or `aria-label`.

### 17. Connection flow components use raw `fetch()` instead of `apiClient`
**Files**:
- `/frontend/components/connections/DirectLoginForm.tsx` (lines 78, 96, 125, 186)
- `/frontend/components/connections/EmailConnectionFlow.tsx`
- `/frontend/components/connections/PortalConnectionFlow.tsx`
- `/frontend/components/connections/ConnectionUploadFlow.tsx` (line 41)

These components bypass the shared `apiClient` and use raw `fetch()` calls with `credentials: 'include'`. This means they miss the centralized 401 handler, circuit breaker fallback, and consistent error parsing provided by `apiClient`. If the backend session expires, these components will fail silently or show raw error messages instead of redirecting to login.

---

## P2 Medium

### 18. Skeleton components missing `aria-busy` and `role="status"` attributes
**File**: `/frontend/components/ui/skeleton.tsx`
The base `Skeleton`, `CardSkeleton`, `ChartSkeleton`, and `TableRowSkeleton` components lack `aria-busy="true"` and `role="status"` attributes. Screen readers will not announce that content is loading. The parent containers using these skeletons should also set `aria-busy="true"` while loading.

### 19. NeighborhoodCard and CombinedSavingsCard: hardcoded "$" currency symbol
**File**: `/frontend/components/dashboard/NeighborhoodCard.tsx`
**File**: `/frontend/components/dashboard/CombinedSavingsCard.tsx`
Multiple instances of hardcoded `$` symbols followed by `.toFixed(2)` instead of using the shared `formatCurrency()` utility. This breaks if the app ever supports non-USD currencies and is inconsistent with other components that properly use `formatCurrency()`.

### 20. PricesContent and GasRatesContent: all queries fire in parallel on mount
**Files**:
- `/frontend/components/prices/PricesContent.tsx` (lines 84-94)
- `/frontend/components/gas/GasRatesContent.tsx` (lines 23-28)

Unlike `DashboardContent.tsx` which carefully staggers queries in tiers, these pages fire 4-5 queries simultaneously on mount. This creates an initial burst of HTTP requests that can compete with each other on slow connections.

### 21. ScheduleTimeline: complex component (~280 lines) with drag interaction logic
**File**: `/frontend/components/charts/ScheduleTimeline.tsx`
Combines rendering, drag event handling, time zone calculations, and price zone logic in a single component. The drag interaction logic should be extracted into a custom hook (`useDragHandle` or similar).

### 22. CommunitySolarContent: custom loading skeleton instead of shared `Skeleton` component
**File**: `/frontend/components/community-solar/CommunitySolarContent.tsx` (lines 116-125)
Builds custom `animate-pulse` div structures instead of using the shared `Skeleton` component from `@/components/ui/skeleton`. Multiple utility dashboards (heating-oil, propane, water) do the same thing, creating inconsistent loading patterns.

### 23. AlertsContent: hardcoded pagination page size
**File**: `/frontend/components/alerts/AlertsContent.tsx`
The alerts page uses a hardcoded page size of 10 with no user control. For users with many alerts, this creates unnecessary pagination without an option to change density.

### 24. PostList: timestamp display uses raw `new Date().toLocaleDateString()`
**File**: `/frontend/components/community/PostList.tsx`
Formats dates with `new Date(post.created_at).toLocaleDateString()` instead of using the shared `formatRelativeTime()` or `formatDateTime()` utilities. Inconsistent with other components that use the shared formatters.

### 25. SavingsCalculator (CommunitySolarService): no input validation for edge cases
**File**: `/frontend/components/community-solar/SavingsCalculator.tsx`
The bill and savings percent inputs use HTML `min`/`max` attributes but do not validate programmatically. Submitting with `bill=0` or `percent=0` would trigger an API call that returns meaningless results.

### 26. ComparisonTable: sorting uses button-in-th pattern without proper ARIA
**File**: `/frontend/components/suppliers/ComparisonTable.tsx`
Table header cells contain `<button>` elements for sorting. While the buttons have click handlers, they lack `aria-sort` attributes on the `<th>` elements to indicate current sort direction. Screen readers cannot determine which column is sorted or in what direction.

### 27. RegionSelector: state list buttons lack `aria-selected` or `aria-pressed`
**File**: `/frontend/components/onboarding/RegionSelector.tsx` (lines 73-96)
State selection buttons use visual highlighting (`bg-primary-50 text-primary-700`) but no ARIA state attributes. Screen readers cannot determine which state is currently selected.

### 28. UtilityTypeSelector: toggle buttons lack ARIA pressed state
**File**: `/frontend/components/onboarding/UtilityTypeSelector.tsx` (lines 49-88)
Multi-select utility buttons have visual checkmarks but no `aria-pressed` or `aria-checked` attributes. The custom checkbox visual (SVG checkmark) is not communicated to assistive technology.

### 29. DashboardContent: `trend` is always "stable"
**File**: `/frontend/components/dashboard/DashboardContent.tsx` (lines 120-132)
The `currentPrice` object hardcodes `trend: "stable"` on line 123. Unlike `PricesContent.tsx` which derives the trend from `price_change_24h`, the dashboard always shows stable trend. The `TrendIcon` selection logic on lines 133-138 is dead code for "increasing" and "decreasing" branches.

### 30. Connection analytics cards: each card independently fetches data with manual state management
**Files**: `/frontend/components/connections/analytics/RateComparisonCard.tsx`, `RateHistoryCard.tsx`, `ConnectionHealthCard.tsx`, `SavingsEstimateCard.tsx`
Each card independently manages `useState` + `useEffect` + `useCallback` for data fetching, creating 4 copies of the same loading/error/success pattern. These should use React Query hooks (like the rest of the app) instead of manual state management, gaining automatic caching, deduplication, and background refetching.

---

## P3 Low

### 31. Hardcoded English strings throughout -- no i18n preparation
**Every component** contains hardcoded English strings. While i18n may not be an immediate priority, the sheer volume (every button label, error message, heading, description) means an i18n retrofit will be extremely expensive. Consider at minimum extracting strings from high-traffic pages (Dashboard, Prices, Connections) into a constants file.

### 32. Multiple `formatDate` functions defined locally
**Files**:
- `/frontend/components/connections/BillUploadTypes.ts` (line 48)
- `/frontend/components/connections/analytics/types.ts` (line 76)

Two independent `formatDate` implementations exist in the connections module alongside the shared `formatDateTime` from `@/lib/utils/format`. Should consolidate to the shared utility.

### 33. Duplicated `UTILITY_LABELS` mapping objects
**Files**:
- `/frontend/components/analytics/DataExport.tsx` (lines 7-12)
- `/frontend/components/analytics/ForecastWidget.tsx` (lines 7-12)
- `/frontend/components/analytics/OptimizationReport.tsx` (lines 6-12)
- `/frontend/components/rate-changes/RateChangeCard.tsx` (lines 5-11)
- `/frontend/components/rate-changes/AlertPreferences.tsx` (lines 8-14)

The same `UTILITY_LABELS` Record is duplicated 5 times. Should be extracted to a shared constant in `@/lib/constants/`.

### 34. Duplicated `STATE_NAMES` mapping objects
**Files**:
- `/frontend/components/heating-oil/HeatingOilDashboard.tsx` (lines 8-18)
- `/frontend/components/propane/PropaneDashboard.tsx` (lines 8-17)
- `/frontend/components/water/WaterDashboard.tsx` (lines 8-21)

Three copies of state name mappings with inconsistent coverage (HeatingOilDashboard has 9 states, WaterDashboard has 51). Should use the shared `US_REGIONS` from `@/lib/constants/regions`.

### 35. PropaneDashboard and HeatingOilDashboard are near-identical code
**Files**:
- `/frontend/components/heating-oil/HeatingOilDashboard.tsx` (134 lines)
- `/frontend/components/propane/PropaneDashboard.tsx` (133 lines)

These two components share approximately 95% of their structure. They could be refactored into a single `FuelPriceDashboard` component parameterized by fuel type, color scheme, and data hooks.

### 36. PropanePriceHistory and OilPriceHistory are near-identical
**Files**:
- `/frontend/components/propane/PropanePriceHistory.tsx` (76 lines)
- `/frontend/components/heating-oil/OilPriceHistory.tsx` (76 lines)

Same structure, different data hooks. Should be a shared `FuelPriceHistory` component.

### 37. DashboardContent at 327 lines with complex data transformations
**File**: `/frontend/components/dashboard/DashboardContent.tsx`
Data processing logic (chart data mapping, optimal window calculation, supplier mapping) is co-located with component rendering. The `useMemo` blocks on lines 104-201 could be extracted into a custom `useDashboardData` hook to separate data concerns from rendering.

### 38. SavingsDonut: uses modulo arithmetic for color cycling
**File**: `/frontend/components/charts/SavingsDonut.tsx`
The `CHART_COLORS` array uses `colors[i % colors.length]` for color assignment. If the data array has more entries than the color array, colors will repeat, making segments visually indistinguishable. Should either limit visible segments or generate distinct colors dynamically.

### 39. SwitchWizard: GDPR consent step lacks explicit data processing description
**File**: `/frontend/components/suppliers/SwitchWizard.tsx`
The consent step mentions "data processing" generically but does not detail what specific personal data will be shared with the new supplier, as required by GDPR Article 13. The consent text should enumerate the data categories.

### 40. InstallPrompt: uses `role="banner"` incorrectly
**File**: `/frontend/components/pwa/InstallPrompt.tsx` (line 59)
The `role="banner"` is a landmark role intended for site-wide header content. A PWA install prompt is not a banner landmark. Should use `role="complementary"` or `role="region"` with an `aria-label`, or simply remove the role.

### 41. FeedbackWidget firstFocusRef targets radio input instead of close button
**File**: `/frontend/components/feedback/FeedbackWidget.tsx` (line 181)
`firstFocusRef` is assigned to the first radio input. Per ARIA best practices for modal dialogs, focus should move to the first interactive element (the close button) or the modal container itself. Focusing on a radio button immediately selects it, which may not be the user's intent.

### 42. AgentChat: "New conversation" button uses `title` instead of `aria-label`
**File**: `/frontend/components/agent/AgentChat.tsx` (line 125)
The reset button uses `title="New conversation"` which is not reliably announced by screen readers. Should use `aria-label` instead of `title`.

### 43. SavingsTracker: hardcoded $50 monthly goal
**File**: `/frontend/components/gamification/SavingsTracker.tsx` (line 96)
The monthly savings goal is hardcoded to `$50`. This should be a prop or pulled from user settings.

### 44. ExcalidrawWrapper: uses `any` type casts
**File**: `/frontend/components/dev/ExcalidrawWrapper.tsx` (line 54)
Uses `as unknown as (elements: any, appState: any, files: any) => void` cast. While documented as dev-only, the `any` types bypass TypeScript safety. Since the component is triple-gated for dev, this is acceptable but should be documented in the component JSDoc.

### 45. RateChangeFeed and RateChangeCard: use `text-muted-foreground` Tailwind class
**Files**:
- `/frontend/components/rate-changes/RateChangeFeed.tsx` (line 37, 79)
- `/frontend/components/rate-changes/RateChangeCard.tsx` (line 34, 50, 71)
- `/frontend/components/rate-changes/AlertPreferences.tsx` (line 23, 93)

These components use `text-muted-foreground` and `bg-muted` classes which are shadcn/ui conventions, inconsistent with the rest of the codebase that uses the `text-gray-*` Tailwind scale. If the shadcn CSS variables are not defined, these classes resolve to nothing.

### 46. SavingsEstimateCard: local `formatCurrency` shadows shared import
**File**: `/frontend/components/connections/analytics/SavingsEstimateCard.tsx` (lines 66-73)
Defines a local `formatCurrency` function that behaves differently from the shared one in `@/lib/utils/format` (this one uses `minimumFractionDigits: 0`). Should use the shared function with options, or rename to avoid confusion.

### 47. OnboardingWizard: double `mutateAsync` calls without error handling
**File**: `/frontend/components/onboarding/OnboardingWizard.tsx` (lines 24-34)
Makes two sequential `updateProfile.mutateAsync()` calls without try/catch. If the first succeeds but the second fails (network error), the user will have their region saved but `onboarding_completed` will remain `false`, leaving them in a broken state where they see onboarding again with data already set.

---

## Files With No Issues

The following files were reviewed and found to have clean implementations with proper patterns:

- `/frontend/components/ui/badge.tsx` -- Clean variant/size system with forwardRef
- `/frontend/components/ui/button.tsx` -- Good loading, disabled, icon, variant handling
- `/frontend/components/ui/card.tsx` -- Well-structured compound component with forwardRef
- `/frontend/components/ui/toast.tsx` -- Proper `role="alert"` and `aria-atomic`
- `/frontend/components/error-boundary.tsx` -- Correct Error Boundary pattern
- `/frontend/components/page-error-fallback.tsx` -- Clean error fallback
- `/frontend/components/providers/QueryProvider.tsx` -- Good retry/stale config
- `/frontend/components/dashboard/DashboardTypes.ts` -- Clean type definitions
- `/frontend/components/dashboard/DashboardStatsRow.tsx` -- React.memo, clean props
- `/frontend/components/dashboard/DashboardCharts.tsx` -- Dynamic import, tier gating
- `/frontend/components/dashboard/DashboardForecast.tsx` -- Clean with upgrade CTA
- `/frontend/components/dashboard/DashboardSchedule.tsx` -- Simple placeholder
- `/frontend/components/dashboard/DashboardTabs.tsx` -- Proper ARIA tab roles
- `/frontend/components/dashboard/CompletionProgress.tsx` -- Clean SVG progress
- `/frontend/components/dashboard/UtilityDiscoveryCard.tsx` -- Clean implementation
- `/frontend/components/dashboard/AllUtilitiesTab.tsx` -- Clean tab content
- `/frontend/components/dashboard/UtilityTabShell.tsx` -- Clean shell
- `/frontend/components/connections/BillUploadDropZone.tsx` -- Excellent a11y (role, tabIndex, keyDown, aria-label)
- `/frontend/components/connections/BillUploadFilePreview.tsx` -- Clean, good aria-label on remove
- `/frontend/components/connections/BillUploadProgress.tsx` -- Proper progressbar role and aria-value*
- `/frontend/components/connections/BillUploadResults.tsx` -- Clean success/failure states
- `/frontend/components/connections/BillUploadTypes.ts` -- Well-organized shared types
- `/frontend/components/connections/ExtractedField.tsx` -- Clean presentational component
- `/frontend/components/connections/ConnectionMethodPicker.tsx` -- Good focus styles
- `/frontend/components/connections/ConnectionRates.tsx` -- Proper table semantics (scope, th)
- `/frontend/components/connections/analytics/index.ts` -- Clean barrel export
- `/frontend/components/connections/analytics/types.ts` -- Clean type definitions with fetch helper
- `/frontend/components/connections/analytics/RateComparisonCard.tsx` -- Good loading/error/success states, aria-hidden on icons
- `/frontend/components/connections/analytics/ConnectionHealthCard.tsx` -- Good aria-labels on sync buttons
- `/frontend/components/onboarding/AccountLinkStep.tsx` -- Clean delegation to SupplierAccountForm
- `/frontend/components/onboarding/SupplierPicker.tsx` -- Good loading state with role="status"
- `/frontend/components/charts/ForecastChart.tsx` -- React.memo, normalizes shapes
- `/frontend/components/community/VoteButton.tsx` -- Good optimistic update with rollback
- `/frontend/components/community/ReportButton.tsx` -- Clean two-step confirmation
- `/frontend/components/community/CommunityStats.tsx` -- Graceful error hiding
- `/frontend/components/cca/CCAComparison.tsx` -- Clean comparison display
- `/frontend/components/cca/CCAInfo.tsx` -- Proper `isSafeHref` on external URLs
- `/frontend/components/propane/FillUpTiming.tsx` -- Clean timing advice display
- `/frontend/components/water/ConservationTips.tsx` -- Well-organized tip categories
- `/frontend/components/water/WaterRateBenchmark.tsx` -- Clean benchmark display
- `/frontend/components/water/WaterTierCalculator.tsx` -- Good tier calculation logic with labels
- `/frontend/components/rate-changes/AlertPreferences.tsx` -- Good role="switch" with aria-checked
- `/frontend/components/rate-changes/RateChangeFeed.tsx` -- Clean feed with filter controls
- `/frontend/components/affiliate/FTCDisclosure.tsx` -- Proper role="note" and aria-label
- `/frontend/components/pwa/ServiceWorkerRegistrar.tsx` -- Clean side-effect component
- `/frontend/components/dev/DevBanner.tsx` -- Simple dev-only banner
- `/frontend/components/dev/DiagramEditor.tsx` -- Good Ctrl+S shortcut, clean states
- `/frontend/components/dev/DiagramList.tsx` -- Proper role="list" with clean empty state
- `/frontend/components/dev/ExcalidrawWrapper.tsx` -- Correct dynamic import with SSR disabled
- `/frontend/components/gamification/SavingsTracker.tsx` -- Clean presentational component

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| P0 Critical | 7 | Index keys on dynamic lists (5), accessibility trap (1), modal ID collision (1) |
| P1 High | 10 | Missing focus traps (1), ARIA violations (2), external URL validation (2), raw fetch bypassing apiClient (1), code complexity (1), label associations (2), duplicated constants (1) |
| P2 Medium | 13 | Missing ARIA states (4), inconsistent patterns (3), hardcoded values (2), stale trend logic (1), manual state management vs React Query (1), parallel query burst (1), complexity (1) |
| P3 Low | 17 | Code duplication (6), i18n preparation (1), hardcoded values (2), inconsistent styling (2), minor a11y (3), error handling (1), type safety (1), naming shadows (1) |
| No Issues | 49 | Clean implementations following established patterns |

**Total files reviewed**: 101
**Files with findings**: 52
**Files with no issues**: 49

### Top Recommendations (in priority order)

1. **Fix index keys**: Replace array index keys with stable identifiers in GasRatesContent, RatePageContent, OptimizationReport, and AgentChat. These are the most common P0 pattern.

2. **Generate unique Modal IDs**: Switch `modal.tsx` to use `React.useId()` for the title ID. This is a one-line fix that prevents a class of bugs.

3. **Add keyboard support to clickable divs**: HeatingOilDashboard and PropaneDashboard need `role="button"`, `tabIndex={0}`, and `onKeyDown` on price cards.

4. **Migrate connection flows to apiClient**: DirectLoginForm, EmailConnectionFlow, PortalConnectionFlow, and ConnectionUploadFlow should use `apiClient` instead of raw `fetch()` to get centralized auth handling.

5. **Validate external URLs consistently**: CCAAlert and DealerList should use `isSafeHref()` like the rest of the codebase.

6. **Extract shared constants**: Consolidate `UTILITY_LABELS`, `STATE_NAMES`, and `US_STATES` into `@/lib/constants/` to eliminate 10+ duplication instances.

7. **Migrate analytics cards to React Query**: The 4 connection analytics cards should use React Query hooks instead of manual useState/useEffect/useCallback state management.

8. **Add missing ARIA attributes**: Skeleton (aria-busy), RegionSelector (aria-selected), UtilityTypeSelector (aria-pressed), ComparisonTable (aria-sort), and DataExport/ForecastWidget selects (aria-label).
