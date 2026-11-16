# Frontend Components Audit — RateShift

**Date:** 2026-03-16
**Scope:** `/frontend/components/` — 98 TSX files across 22 directories
**Auditor:** React Specialist (Claude Sonnet 4.6)

---

## Summary

| Severity | Count | Categories |
|----------|-------|-----------|
| P0 | 3 | No error boundaries, unguarded `__UPGRADE__` sentinel string, modal focus traps missing |
| P1 | 9 | Uncleared setTimeout leaks, console.log in production, index-as-key on dynamic lists, missing aria on interactive elements, hardcoded fallback defaults in mapping logic |
| P2 | 14 | Inline object/array creation in JSX, missing aria-label on icon buttons, prop drilling candidates, `window.location.href` instead of router, duplicated state mapping logic |
| P3 | 8 | Missing `displayName` on memo'd components, hardcoded strings/magic numbers, `any` casts, stale `Electricity Optimizer` brand name in sidebar |

**Total findings: 34**

No `dangerouslySetInnerHTML` issues were found in component code (the one usage in `app/rates/.../page.tsx` is JSON-LD structured data, not user content — acceptable). No XSS vulnerabilities found.

---

## P0 — Critical

### P0-01: No error boundaries anywhere in the component tree

**Files:** All page-level components — `DashboardContent.tsx`, `SuppliersContent.tsx`, `AgentChat.tsx`, `ConnectionsOverview.tsx`, `PostList.tsx`, etc.

**Description:** Zero `ErrorBoundary` components exist in the entire frontend codebase (confirmed by grep — only node_modules contain the term). Any uncaught render-time exception in a child component will crash the whole React tree and show a blank page. This includes: Recharts throwing on malformed data, `parseISO` on a non-ISO timestamp, a null-deref in `PriceLineChart`, or an API response that doesn't match the assumed shape.

**Fix:** Create a shared `ErrorBoundary` class component and wrap at least the top-level page shells and the chart/community subtrees.

```tsx
// components/ui/ErrorBoundary.tsx
'use client'
import React from 'react'

interface Props { fallback?: React.ReactNode; children: React.ReactNode }
interface State { hasError: boolean; error: Error | null }

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Wire to Sentry when available
    console.error('[ErrorBoundary]', error, info)
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div role="alert" className="p-6 text-center text-gray-500">
          Something went wrong. Please refresh the page.
        </div>
      )
    }
    return this.props.children
  }
}
```

Then wrap page content:
```tsx
// In DashboardContent, SuppliersContent, etc.
<ErrorBoundary fallback={<DashboardErrorFallback />}>
  <DashboardCharts ... />
</ErrorBoundary>
```

---

### P0-02: `__UPGRADE__` magic sentinel string used as an error signal across an async boundary

**File:** `frontend/components/connections/BillUploadForm.tsx`, lines 184 and 219

**Description:** The upload XHR handler throws `new Error('__UPGRADE__')` on a 403 response, and the catch block checks `if (message === '__UPGRADE__')` to display an upgrade prompt. This is a fragile contract: the sentinel string is undocumented, easy to accidentally match or miss in refactors, and will silently swallow any other 403 cause (e.g., CSRF failure, permission error for a different resource).

```tsx
// Line 184 — inside XHR load handler
reject(new Error('__UPGRADE__'))

// Line 219 — in the catch block
if (message === '__UPGRADE__') {
  setError('Bill upload is available on Pro...')
}
```

**Fix:** Introduce a typed error class and throw/catch it cleanly:

```tsx
class UpgradeRequiredError extends Error {
  constructor() { super('Upgrade required'); this.name = 'UpgradeRequiredError' }
}

// In XHR handler:
if (xhr.status === 403) reject(new UpgradeRequiredError())

// In catch:
if (err instanceof UpgradeRequiredError) {
  setError('Bill upload is available on Pro and Business plans...')
}
```

---

### P0-03: Modal dialogs in `SuppliersContent.tsx` have no focus trap or focus restoration

**File:** `frontend/components/suppliers/SuppliersContent.tsx`, lines 349–379

**Description:** Two inline modal divs (`showWizard` and `showSetDialog`) use `role="dialog"` and `aria-modal="true"` but do not implement a focus trap. When opened, keyboard focus remains in the background document. Screen reader users get no indication the dialog is open. When closed, focus is not returned to the triggering element (the "Switch Now" or "Select Supplier" button). This is a WCAG 2.1 SC 2.1.2 violation.

```tsx
// Line 350 — inline modal with no focus management
<div className="fixed inset-0 z-50 ..." role="dialog" aria-modal="true" aria-label="Switch supplier">
  <div className="...">
    <SwitchWizard ... />
  </div>
</div>
```

**Fix:** The `FeedbackModal` component (line 54–62 of `FeedbackWidget.tsx`) already implements Escape handling correctly. Apply the same pattern here, and add a `useRef` to track the trigger element for focus restoration. Alternatively, move these to a proper `Modal` portal component (the `components/ui/modal.tsx` file already exists — check if it handles focus trapping).

---

## P1 — High

### P1-01: `setTimeout` leaks in `Header.tsx` — timer not cleared on unmount

**File:** `frontend/components/layout/Header.tsx`, line 30

**Description:** `handleRefresh` sets a 1-second `setTimeout` to clear the spinner. If the component unmounts before the timer fires (e.g., navigation), the callback attempts to call `setIsRefreshing(false)` on an unmounted component. In React 18 this no longer throws, but it is still a resource leak and will produce a stale closure that cannot be GC'd.

```tsx
// Line 26–31
const handleRefresh = async () => {
  setIsRefreshing(true)
  refreshPrices()
  // Simulate delay for UX
  setTimeout(() => setIsRefreshing(false), 1000)  // leaked timer
}
```

**Fix:**
```tsx
const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

React.useEffect(() => {
  return () => { if (timerRef.current) clearTimeout(timerRef.current) }
}, [])

const handleRefresh = () => {
  setIsRefreshing(true)
  refreshPrices()
  timerRef.current = setTimeout(() => setIsRefreshing(false), 1000)
}
```

---

### P1-02: `console.log` and `console.warn` left in production bundle

**Files:**
- `frontend/components/pwa/ServiceWorkerRegistrar.tsx`, lines 17 and 20
- `frontend/components/pwa/InstallPrompt.tsx`, line 46

**Description:** Three production `console` calls will appear in user browser devtools and bloat the bundle output.

```tsx
// ServiceWorkerRegistrar.tsx line 17
console.log('[SW] Registered:', reg.scope)
// ServiceWorkerRegistrar.tsx line 20
console.warn('[SW] Registration failed:', err)
// InstallPrompt.tsx line 46
console.log('[PWA] Install result:', result.outcome)
```

**Fix:** Remove all three. SW registration is observable in browser devtools natively. If logging is needed for debugging use a `DEBUG` env-gated logger utility, not bare console calls.

---

### P1-03: Index used as React `key` for dynamic (non-stable) lists

**Files:**
- `frontend/components/agent/AgentChat.tsx`, lines 46 and 161 — `key={i}` for both tool badges and message bubbles
- `frontend/components/charts/PriceLineChart.tsx`, line 260 — `key={i}` for `ReferenceArea` elements
- `frontend/components/charts/ScheduleTimeline.tsx`, line 181
- `frontend/components/prices/PricesContent.tsx`, line 281
- `frontend/components/gas/GasRatesContent.tsx`, line 186
- `frontend/components/seo/RatePageContent.tsx`, line 101 — supplier table rows

**Description:** Using array index as React `key` causes incorrect reconciliation when items are added, removed, or reordered. For `AgentChat.tsx` this is critical: when streaming adds messages, all subsequent `MessageBubble` instances will be re-mounted rather than updated, causing flicker and losing any internal state.

The skeleton loaders (`key={i}` on static arrays like `[1,2,3]`) are acceptable since they never reorder. The agent messages and rate table rows are the problematic cases.

**Fix for AgentChat:**
```tsx
// Messages have a role+content, use a stable identifier
{messages.map((msg, i) => (
  <MessageBubble key={`${msg.role}-${i}-${msg.content.slice(0, 20)}`} message={msg} />
))}
```
Better: add an `id` field to `AgentMessage` type and use it as key.

**Fix for RatePageContent supplier table:** Use `s.supplier` (the supplier name string) as key — it is unique within a single state/utility response.

---

### P1-04: Missing accessible label on icon-only buttons in `AgentChat`

**File:** `frontend/components/agent/AgentChat.tsx`, lines 121–128 (reset button), 215–222 (stop button), 223–231 (send button)

**Description:** Three icon-only buttons have no `aria-label`. Screen readers will announce them as "button" with no description.

```tsx
// Line 121 — no aria-label
<button onClick={reset} className="..." title="New conversation">
  <RotateCcw className="h-4 w-4" />
</button>

// Line 216 — stop button, no aria-label
<button type="button" onClick={cancel} className="...">
  <Square className="h-4 w-4" />
</button>

// Line 224 — submit, no aria-label
<button type="submit" disabled={...} className="...">
  <Send className="h-4 w-4" />
</button>
```

`title` is not sufficient for accessibility — it is not exposed by all screen readers and is not part of the accessibility tree on touch devices.

**Fix:** Add `aria-label` to all three:
```tsx
<button aria-label="Start new conversation" onClick={reset} title="New conversation">
<button type="button" aria-label="Stop generating" onClick={cancel}>
<button type="submit" aria-label="Send message" disabled={...}>
```

---

### P1-05: Missing accessible label and state on `VoteButton` and `ReportButton`

**Files:**
- `frontend/components/community/VoteButton.tsx`, lines 39–53
- `frontend/components/community/ReportButton.tsx`, lines 46–53

**Description:** `VoteButton` renders an upvote triangle with no `aria-label` — screen readers get only the count number. The voted/unvoted toggle state has no `aria-pressed`. `ReportButton` has no `aria-label` on the initial trigger or on the confirm/cancel buttons.

```tsx
// VoteButton — no aria-label, no aria-pressed
<button onClick={handleClick} disabled={mutation.isPending} className={...}>
  <span aria-hidden="true">{voted ? '▲' : '△'}</span>
  <span>{optimisticCount}</span>
</button>

// ReportButton — no aria-label
<button onClick={() => setShowConfirm(true)} className="...">
  Report
</button>
```

**Fix:**
```tsx
// VoteButton
<button
  onClick={handleClick}
  disabled={mutation.isPending}
  aria-label={`${voted ? 'Remove upvote' : 'Upvote'} (${optimisticCount})`}
  aria-pressed={voted}
>

// ReportButton — initial trigger
<button
  onClick={() => setShowConfirm(true)}
  aria-label="Report this post"
>

// ReportButton — confirm
<button onClick={handleReport} disabled={mutation.isPending} aria-label="Confirm report">Yes</button>
<button onClick={() => setShowConfirm(false)} aria-label="Cancel report">No</button>
```

---

### P1-06: `PostForm.tsx` labels not associated with select inputs via `htmlFor`

**File:** `frontend/components/community/PostForm.tsx`, lines 112–136

**Description:** The Post Type and Utility Type `<select>` elements are wrapped in `<label>` elements using generic `className` labels rather than the HTML label association mechanism. The labels use `<label className="block text-xs ...">` as visual labels but do not have `htmlFor` pointing to an `id` on the select, and the selects do not have `id` attributes. This means screen readers cannot programmatically associate labels to controls.

```tsx
// Line 112 — label without htmlFor
<label className="block text-xs font-medium text-gray-600 mb-1">Post Type</label>
<select
  value={postType}
  onChange={(e) => setPostType(e.target.value)}
  // No id attribute
```

**Fix:** Add matching `htmlFor`/`id` pairs:
```tsx
<label htmlFor="post-type-select" className="...">Post Type</label>
<select id="post-type-select" ...>

<label htmlFor="utility-type-select" className="...">Utility Type</label>
<select id="utility-type-select" ...>
```

---

### P1-07: Hardcoded fallback price constants and supplier IDs in data mapping

**Files:**
- `frontend/components/dashboard/DashboardContent.tsx`, lines 71, 126–127
- `frontend/components/suppliers/SuppliersContent.tsx`, lines 60–61, 64
- `frontend/components/onboarding/SupplierPicker.tsx`, lines 23–24

**Description:** Magic numbers `0.22` ($/kWh), `0.40` (standing charge), and the supplier IDs `'supplier_001'`/`'supplier_002'` are scattered across three components as fallback values when backend data is missing. If the business default changes (e.g., base rate is now $0.25), it must be updated in multiple places. The supplier ID strings are implementation details that should never appear in frontend component logic.

```tsx
// SuppliersContent.tsx line 60
avgPricePerKwh: s.avgPricePerKwh ?? (s.id === 'supplier_001' ? 0.21 : s.id === 'supplier_002' ? 0.24 : 0.22),
standingCharge: s.standingCharge ?? 0.40,
```

**Fix:** Extract to a shared constants module:
```tsx
// lib/constants/pricing.ts
export const DEFAULT_PRICE_PER_KWH = 0.22
export const DEFAULT_STANDING_CHARGE = 0.40
```
Remove supplier-ID-specific fallback pricing entirely — if the backend is not providing `avgPricePerKwh`, that is a data issue, not something to paper over in frontend mapping.

---

### P1-08: Hardcoded default region `'us_ct'` in `PostForm.tsx`

**File:** `frontend/components/community/PostForm.tsx`, line 90

**Description:** When no region is set in the settings store, the post falls back to Connecticut (`'us_ct'`). This is a silent data quality issue — posts from users who haven't set a region will appear under Connecticut's community feed.

```tsx
region: region || 'us_ct',
```

**Fix:** Either require region before enabling the form, or disable the submit button with a tooltip explaining that region must be set first:
```tsx
const canPost = !!region
// In form: disabled={!canPost || mutation.isPending}
// Show inline message: "Please set your region in Settings to post."
```

---

### P1-09: `SuppliersContent.tsx` modal dialogs rendered as inline divs — no portal, no scroll lock

**File:** `frontend/components/suppliers/SuppliersContent.tsx`, lines 349–362 and 365–379

**Description:** Both `SwitchWizard` and `SetSupplierDialog` modals are rendered as inline `position: fixed` divs inside the page's own render tree. This means they can be clipped by parent overflow constraints, are subject to stacking context issues, and do not lock body scroll when open. The existing `components/ui/modal.tsx` should be used instead.

**Fix:** Replace inline modal containers with the project's existing `Modal` component, or use `ReactDOM.createPortal` to render them at the document body level.

---

## P2 — Medium

### P2-01: Inline object creation for `CHART_MARGIN` and `tooltipStyle` not actually a problem, but inline `style` objects in JSX render ARE

**File:** `frontend/components/agent/AgentChat.tsx`, lines 166–168

**Description:** The three animated bounce dots use inline `style={{ animationDelay: '...' }}` objects created fresh on every render. While trivial in this case (3 static spans), the pattern sets a bad precedent.

```tsx
<span style={{ animationDelay: '0ms' }} />
<span style={{ animationDelay: '150ms' }} />
<span style={{ animationDelay: '300ms' }} />
```

**Fix:** Use Tailwind's `[animation-delay:...]` arbitrary value syntax or extract as a CSS module / static class. These are constant values and do not need to be in JSX.

---

### P2-02: `window.location.href` navigation instead of Next.js router

**File:** `frontend/components/dashboard/DashboardContent.tsx`, line 172

**Description:** The error state's retry/sign-in button uses `window.location.href = '/auth/login'` for navigation, which causes a full page reload and loses client-side state. This also bypasses Next.js prefetching and route middleware.

```tsx
onClick={() => is401 ? (window.location.href = '/auth/login') : window.location.reload()}
```

**Fix:** Use the Next.js `useRouter` hook:
```tsx
const router = useRouter()
// ...
onClick={() => is401 ? router.push('/auth/login') : router.refresh()}
```

Note: `window.location.reload()` is appropriate in the non-401 retry path since it forces a full data refresh; `router.refresh()` (Next.js 13+) is the preferred equivalent.

---

### P2-03: Duplicated `isValidEmail` regex defined identically in two auth forms

**Files:**
- `frontend/components/auth/LoginForm.tsx`, line 19
- `frontend/components/auth/SignupForm.tsx`, line 25

**Description:** Both files define `const isValidEmail = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)` identically, creating two separate RegExp compilations and a maintenance hazard if the validation rule needs to change.

**Fix:** Extract to `lib/utils/validation.ts`:
```ts
export const isValidEmail = (email: string): boolean =>
  /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
```

---

### P2-04: `NotificationBell.tsx` panel renders without accessible close mechanism for keyboard users

**File:** `frontend/components/layout/NotificationBell.tsx`, lines 110–156

**Description:** The notifications panel closes on `mousedown` outside (line 66–80) and can be toggled with the bell button. However, there is no keyboard mechanism to close it (no Escape key handler, no close button inside the panel). A keyboard user who opens the panel and then navigates into it cannot close it without tabbing back to the bell button.

```tsx
// Only mousedown handler — no keyboard close
useEffect(() => {
  if (!open) return
  function handleClickOutside(event: MouseEvent) { ... }
  document.addEventListener('mousedown', handleClickOutside)
  return () => document.removeEventListener('mousedown', handleClickOutside)
}, [open])
```

**Fix:** Add Escape key handling:
```tsx
useEffect(() => {
  if (!open) return
  function handleKey(e: KeyboardEvent) {
    if (e.key === 'Escape') { setOpen(false); /* return focus to bell button */ }
  }
  document.addEventListener('keydown', handleKey)
  return () => document.removeEventListener('keydown', handleKey)
}, [open])
```

---

### P2-05: `PortalConnectionFlow.tsx` — `scrapeController` and `AbortController` created but the scrape controller signal never passed to `triggerPortalScrape`

**File:** `frontend/components/connections/PortalConnectionFlow.tsx`, lines 113–133

**Description:** A second `AbortController` (`scrapeController`) is created for the scrape timeout, but its `signal` is never passed to `triggerPortalScrape`. The `clearTimeout(scrapeTimeout)` in the finally block also runs unconditionally. The net effect is that the scrape timeout has no effect — the request will run indefinitely even if `scrapeController.abort()` is called.

```tsx
const scrapeController = new AbortController()
const scrapeTimeout = setTimeout(() => scrapeController.abort(), 30_000)

try {
  setStep('scraping')
  // signal never used:
  const result = await triggerPortalScrape(connection.connection_id)
```

**Fix:** Pass the signal to `triggerPortalScrape` (update its signature to accept an optional `signal` parameter), or use a single `AbortController` for the whole flow with a 60-second total budget.

---

### P2-06: `SuppliersContent.tsx` — `handleSwitchComplete` swallows errors silently

**File:** `frontend/components/suppliers/SuppliersContent.tsx`, lines 98–120

**Description:** Both `setSupplierMutation.mutateAsync` and `initiateSwitch.mutateAsync` are called inside try/catch blocks with empty catch bodies. If either fails, the user sees the wizard close and their supplier marked as changed, but receives no feedback about what went wrong.

```tsx
try {
  await setSupplierMutation.mutateAsync(selectedSupplier.id)
} catch {
  // Backend save failed — still update local state
}
try {
  await initiateSwitch.mutateAsync({ ... })
} catch {
  // Switch endpoint may not exist yet — that's OK
}
```

**Fix:** At minimum, track a `switchError` state and display a dismissible error banner when the backend save fails. The comment "Backend save failed — still update local state for offline-first UX" is reasonable for the local state update, but the user should be told that cloud sync failed and will be retried.

---

### P2-07: `DashboardContent.tsx` — `optimalWindow` calculation uses `bestStart` as an array index to derive the time label

**File:** `frontend/components/dashboard/DashboardContent.tsx`, lines 95–119

**Description:** The optimal window label `fmtHour(bestStart)` interprets `bestStart` (an array index, i.e., position 0–n in the forecast array) as a literal hour-of-day offset. This works only if the forecast array starts at hour 0 and increments by 1 hour. If the forecast API returns data for a different time range or a non-hourly granularity, the labels will be wrong silently.

```tsx
const fmtHour = (h: number) => `${String(h % 24).padStart(2, '0')}:00`
return {
  startLabel: fmtHour(bestStart),  // bestStart = array index, not hour-of-day
  endLabel: fmtHour(bestStart + 4),
```

**Fix:** Derive the time label from the actual `timestamp` on the `ApiPrice` object:
```tsx
return {
  startLabel: prices[bestStart].timestamp
    ? format(parseISO(prices[bestStart].timestamp), 'HH:mm')
    : fmtHour(bestStart),
  endLabel: prices[bestStart + 3].timestamp
    ? format(parseISO(prices[bestStart + 3].timestamp), 'HH:mm')
    : fmtHour(bestStart + 4),
```

---

### P2-08: `SavingsTracker.tsx` — monthly goal hardcoded to `$50`

**File:** `frontend/components/gamification/SavingsTracker.tsx`, line 96

**Description:** The progress bar goal is hardcoded to `$50` and never exposed as a prop. There is no way to customize this goal, and the component will always show incorrect progress for users with different savings targets.

```tsx
<span>Monthly Goal: {formatCurrency(50)}</span>
<div style={{ width: `${Math.min((monthlySavings / 50) * 100, 100)}%` }} />
```

**Fix:** Add a `monthlyGoal?: number` prop defaulting to `50`, and use it throughout the component.

---

### P2-09: `ForecastWidget.tsx` — missing `aria-label` on both `<select>` elements

**File:** `frontend/components/analytics/ForecastWidget.tsx`, lines 50–72

**Description:** The utility type and horizon selects have no `label` elements and no `aria-label` attributes. A screen reader user navigating by form control cannot determine what these selects control.

```tsx
<select
  value={selectedUtility}
  onChange={(e) => setSelectedUtility(e.target.value)}
  className="..."
  // no label, no aria-label
>
```

**Fix:**
```tsx
<label htmlFor="forecast-utility" className="sr-only">Utility type</label>
<select id="forecast-utility" aria-label="Select utility type" ...>

<label htmlFor="forecast-horizon" className="sr-only">Forecast horizon</label>
<select id="forecast-horizon" aria-label="Select forecast period" ...>
```

---

### P2-10: `AnalyticsDashboard.tsx` — hardcoded `US_STATES` array duplicates the region constants

**File:** `frontend/components/analytics/AnalyticsDashboard.tsx`, lines 8–15

**Description:** A 51-item array of US state abbreviations is defined inline in the component file, duplicating similar data that exists in `lib/constants/regions.ts` (the `US_REGIONS` array already used in `AlertForm.tsx`). This creates a maintenance burden and a risk of the two lists diverging.

```tsx
const US_STATES = [
  'AL', 'AK', 'AZ', ... // 51 entries inline
]
```

**Fix:** Import from the shared regions constant:
```tsx
import { US_REGIONS } from '@/lib/constants/regions'
const US_STATE_CODES = US_REGIONS.flatMap(g => g.states.map(s => s.abbr))
```

---

### P2-11: `Sidebar.tsx` displays stale brand name "Electricity Optimizer"

**File:** `frontend/components/layout/Sidebar.tsx`, line 68

**Description:** The sidebar logo text reads "Electricity Optimizer" — the old working name. The project was rebranded to "RateShift" (confirmed in CLAUDE.md and all recent documentation). This is visible on every page for authenticated users.

```tsx
<span className="text-xl font-bold text-gray-900">
  Electricity Optimizer
</span>
```

**Fix:**
```tsx
<span className="text-xl font-bold text-gray-900">RateShift</span>
```

---

### P2-12: `ConnectionsOverview.tsx` — `onSuccess` callback creates a new inline function on every render

**File:** `frontend/components/connections/ConnectionsOverview.tsx`, lines 117–122

**Description:** The `PortalConnectionFlow` success handler is defined inline in JSX, creating a new function reference every render. While `PortalConnectionFlow` doesn't use `React.memo`, this is the pattern that compounds when components do.

```tsx
<PortalConnectionFlow
  onBack={handleBackToOverview}
  onSuccess={() => {
    queryClient.invalidateQueries({ queryKey: ['connections'] })
    setView('overview')
  }}
/>
```

**Fix:** Extract to `useCallback`:
```tsx
const handlePortalSuccess = useCallback(() => {
  queryClient.invalidateQueries({ queryKey: ['connections'] })
  setView('overview')
}, [queryClient])
```

---

### P2-13: `RatePageContent.tsx` — supplier table uses row index as `key`

**File:** `frontend/components/seo/RatePageContent.tsx`, line 101

**Description:** Supplier table rows use `key={i}` (array index). While this is an SSR-rendered static page and React reconciliation is less of a concern, the pattern is still incorrect — if the server-rendered HTML is hydrated and the list reorders, React will produce incorrect updates.

```tsx
{rateData.suppliers.map((s, i) => (
  <tr key={i} className="border-b">
```

**Fix:** Use `s.supplier` (the supplier name) as the key since it is unique per row in this context.

---

### P2-14: Missing `aria-label` on "Mark all read" button in `NotificationBell`

**File:** `frontend/components/layout/NotificationBell.tsx`, line 122

**Description:** The "Mark all read" button has no `aria-label`, relying solely on visible text. While visible text alone is usually fine, for consistency with other interactive elements in the panel and to support internationalization later, a descriptive label would be better. Minor but worth noting for a complete a11y review.

---

## P3 — Low

### P3-01: Missing `displayName` on several `React.memo`'d components

**Files:**
- `frontend/components/dashboard/DashboardStatsRow.tsx` — `React.memo(function DashboardStatsRow...)` — has name via function expression, OK
- `frontend/components/dashboard/DashboardCharts.tsx` — same pattern, OK
- `frontend/components/dashboard/DashboardForecast.tsx` — same pattern, OK
- `frontend/components/charts/PriceLineChart.tsx` — has explicit `PriceLineChart.displayName = 'PriceLineChart'` on line 306 — good

The pattern is consistently applied. No action needed, but note that `React.memo(ArrowFunction)` without a named function expression still shows "Anonymous" in React DevTools — always prefer the `React.memo(function Name() {...})` form already used here.

---

### P3-02: `PriceLineChart.tsx` — `tooltipStyle` constant object defined at module scope but contains a literal that should be a Tailwind class

**File:** `frontend/components/charts/PriceLineChart.tsx`, lines 24–30

**Description:** The Recharts tooltip style is defined as a module-level object constant, which is correct. However, the hardcoded `boxShadow` value duplicates a Tailwind shadow utility. Minor — no functional impact.

---

### P3-03: `InstallPrompt.tsx` uses `as any` cast for the BeforeInstallPromptEvent

**File:** `frontend/components/pwa/InstallPrompt.tsx`, line 43

**Description:** The deferred install prompt is cast with `as any` because the `BeforeInstallPromptEvent` type is not in the standard TypeScript DOM lib.

```tsx
const prompt = deferredPrompt as any
```

**Fix:** Define a local interface:
```tsx
interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}
const prompt = deferredPrompt as BeforeInstallPromptEvent
```

---

### P3-04: `ExcalidrawWrapper.tsx` uses `unknown as` triple cast

**File:** `frontend/components/dev/ExcalidrawWrapper.tsx`, line 54

**Description:** `onChange: handleChange as unknown as (elements: any, appState: any, files: any) => void` — triple-casting through `unknown` to `any`. The Excalidraw `onChange` type should be imported from the `@excalidraw/excalidraw` package and used directly.

---

### P3-05: `DashboardContent.tsx` — `trend` derived from `currentPrice.trend` is always `'stable'`

**File:** `frontend/components/dashboard/DashboardContent.tsx`, lines 78–85

**Description:** `currentPrice.trend` is hardcoded to `'stable'` when building the `CurrentPriceInfo` object (line 80), so the `TrendIcon` logic and the price-drop banner condition (line 192) can never trigger based on live data. The actual price change direction is available via `rawPrice.price_change_24h` but is only stored as `changePercent`, not converted to a trend direction.

```tsx
const currentPrice: CurrentPriceInfo | null = rawPrice ? {
  price: parseFloat(rawPrice.current_price),
  trend: 'stable',  // always stable — never decreasing/increasing
  changePercent: rawPrice.price_change_24h != null ? parseFloat(rawPrice.price_change_24h) : null,
  ...
} : null
```

**Fix:** Derive trend from `changePercent`:
```tsx
const changePercent = rawPrice.price_change_24h != null ? parseFloat(rawPrice.price_change_24h) : null
const trend: 'stable' | 'increasing' | 'decreasing' =
  changePercent === null ? 'stable'
  : changePercent > 2 ? 'increasing'
  : changePercent < -2 ? 'decreasing'
  : 'stable'
```

---

### P3-06: `SavingsEstimateCard.tsx` — `formatCurrency` defined locally, duplicating the shared utility

**File:** `frontend/components/connections/analytics/SavingsEstimateCard.tsx`, lines 66–73

**Description:** A local `formatCurrency` function is defined using `Intl.NumberFormat`. The project already has a shared `formatCurrency` in `lib/utils/format.ts` used across 15+ components. This creates divergence if the formatting behavior needs to change.

**Fix:** Replace with the shared import:
```tsx
import { formatCurrency } from '@/lib/utils/format'
// Remove local formatCurrency definition
```

---

### P3-07: `SwitchWizard.tsx` step progress bar has no accessible announcement

**File:** `frontend/components/suppliers/SwitchWizard.tsx`, lines 87–99

**Description:** The step progress indicator has no `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, or `role="progressbar"`. Screen reader users navigating the wizard get no indication of progress.

```tsx
<div className="h-2 w-full rounded-full bg-gray-200">
  <div
    className="h-2 rounded-full bg-primary-600 transition-all duration-300"
    style={{ width: `${(step / 4) * 100}%` }}
  />
</div>
```

**Fix:**
```tsx
<div
  role="progressbar"
  aria-valuenow={step}
  aria-valuemin={1}
  aria-valuemax={4}
  aria-label={`Step ${step} of 4: ${STEP_TITLES[step]}`}
  className="h-2 w-full rounded-full bg-gray-200"
>
```

---

### P3-08: `PostList.tsx` — `timeAgo` function defined at module scope creates new Date objects on every call without memoization

**File:** `frontend/components/community/PostList.tsx`, lines 18–26

**Description:** `timeAgo` is called once per post per render cycle. For a list of 20 posts with 3-second re-render intervals, this is 20 `new Date()` and `Date.now()` calls per render. Low impact in practice but extractable to a `useMemo` inside `PostCard`, or the result could be computed once in the `PostCard` render. Minor optimization opportunity.

---

## Cross-Cutting Issues Not Tied to a Single File

### Prop drilling for `region` and `currentSupplier`

Multiple component subtrees independently read from `useSettingsStore` to obtain `region` and `currentSupplier`. This is actually the correct approach (Zustand store is the single source of truth, and selector reads are cheap). No change needed — noted here to confirm it is intentional.

### No `Suspense` boundaries for lazily-loaded charts

`DashboardCharts.tsx` and `DashboardForecast.tsx` use `next/dynamic` with `ssr: false` and a `loading` fallback for `PriceLineChart` and `ForecastChart`. This is correct for Next.js client components. The `loading` prop provides the Suspense-equivalent fallback. No change needed.

### No XSS risks found in component code

All user-generated content (`post.title`, `post.body`, `n.title`, `n.body`, supplier names, error messages) is rendered using React's text interpolation (`{variable}`), which automatically escapes HTML entities. No `dangerouslySetInnerHTML` usage exists in component files. The one `dangerouslySetInnerHTML` in `app/rates/[state]/[utility]/page.tsx` is for JSON-LD structured data (`JSON.stringify(jsonLd)`) which is safe as long as `jsonLd` does not contain user input — it is server-constructed from URL params and database records, and `JSON.stringify` produces valid JSON regardless.

---

## Remediation Priority

| Priority | Action | Effort |
|----------|--------|--------|
| P0-01 | Add `ErrorBoundary` wrapper to 4–5 page shells | 2h |
| P0-02 | Replace `__UPGRADE__` string sentinel with typed error class | 30m |
| P0-03 | Add focus trap + restoration to `SuppliersContent` modals | 1h |
| P1-01 | Fix `setTimeout` leak in `Header.tsx` | 15m |
| P1-02 | Remove 3 `console.*` calls from PWA components | 5m |
| P1-03 | Fix `key={i}` on agent messages and supplier rows | 30m |
| P1-04 | Add `aria-label` to 3 icon buttons in `AgentChat` | 15m |
| P1-05 | Add `aria-label` + `aria-pressed` to `VoteButton`/`ReportButton` | 20m |
| P1-06 | Add `htmlFor`/`id` to `PostForm` selects | 10m |
| P1-07 | Extract magic number price constants to `lib/constants/pricing.ts` | 30m |
| P1-08 | Guard `PostForm` against missing region | 20m |
| P1-09 | Move `SuppliersContent` modals to portal / `Modal` component | 1h |
| P2 batch | All P2 items | 4–6h total |
| P3 batch | All P3 items | 2h total |

**Total estimated remediation effort: ~12–14 hours**
