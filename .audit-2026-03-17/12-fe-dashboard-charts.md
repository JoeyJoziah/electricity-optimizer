# Audit Report: Frontend Dashboard, Charts & Analytics
## Date: 2026-03-17

### Executive Summary

21 files were audited across three component directories:
- `frontend/components/dashboard/` — 13 files
- `frontend/components/charts/` — 4 files
- `frontend/components/analytics/` — 4 files

The overall code quality is high. The team has already applied several best practices proactively: `React.memo` on every expensive component, `useMemo`/`useCallback` for derived data, CLS mitigation with `minHeight` reservations and `transform:scaleX()` progress bars, CSS custom property chart tokens, dynamic imports with SSR disabled for chart bundles, and consistent loading/error state handling. No P0 security issues were found.

Seven findings are documented below: two P1, three P2, and two P3.

---

### Findings

#### P0 — Critical

None found.

No `dangerouslySetInnerHTML` usage, no client-side credential embedding, no unvalidated user input injected into the DOM, no XSS vectors.

---

#### P1 — High

**P1-01: Side effect (DOM mutation + URL.createObjectURL) executed during render in `DataExport.tsx`**

File: `frontend/components/analytics/DataExport.tsx`, lines 35–44

```tsx
// CURRENT — this block runs unconditionally during render
if (exportData && format === 'csv' && typeof exportData.data === 'string') {
  const blob = new Blob([exportData.data], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `rateshift_${selectedUtility}_rates.csv`
  a.click()
  URL.revokeObjectURL(url)
  setExportTriggered(false)  // <-- setState during render = React violation
}
```

This is a React rules violation. Side effects and `setState` calls must not occur during the render phase. If React renders this component more than once in a single pass (Strict Mode double-invoke, Concurrent Mode rerender due to suspense, etc.) the download fires multiple times and the final `setExportTriggered(false)` will cause an infinite loop risk. The `URL.revokeObjectURL` is also called synchronously before the browser has had a chance to initiate the download on some browsers.

Recommended fix — move the side effect into `useEffect`:

```tsx
useEffect(() => {
  if (!exportData || format !== 'csv' || typeof exportData.data !== 'string') return
  const blob = new Blob([exportData.data], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `rateshift_${selectedUtility}_rates.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  // Defer revoke to give browser time to start the download
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  setExportTriggered(false)
}, [exportData, format, selectedUtility])
```

Appending and removing the `<a>` element from the DOM is also more cross-browser reliable than clicking a detached element.

---

**P1-02: `currentTimePosition` memoized on `showCurrentTime` only — stale clock position**

File: `frontend/components/charts/ScheduleTimeline.tsx`, lines 60–65

```tsx
const currentTimePosition = useMemo(() => {
  if (!showCurrentTime) return null
  const now = new Date()
  const minutesSinceMidnight = now.getHours() * 60 + now.getMinutes()
  return (minutesSinceMidnight / (24 * 60)) * 100
}, [showCurrentTime])   // <-- no time-based invalidation
```

`useMemo` runs once at mount. The time marker will be stuck at the render-time position for the entire component lifetime — it never advances. For a "Today's Schedule" view where users leave the dashboard open, the marker position will be visibly wrong within minutes.

Recommended fix — use `useState` + `useEffect` with an interval:

```tsx
const [currentTimePosition, setCurrentTimePosition] = useState<number | null>(null)

useEffect(() => {
  if (!showCurrentTime) {
    setCurrentTimePosition(null)
    return
  }
  const getPosition = () => {
    const now = new Date()
    return ((now.getHours() * 60 + now.getMinutes()) / (24 * 60)) * 100
  }
  setCurrentTimePosition(getPosition())
  const id = setInterval(() => setCurrentTimePosition(getPosition()), 60_000)
  return () => clearInterval(id)
}, [showCurrentTime])
```

---

#### P2 — Medium

**P2-01: Stacked confidence-band Areas render with incorrect fill semantics in `ForecastChart.tsx`**

File: `frontend/components/charts/ForecastChart.tsx`, lines 152–169

```tsx
<Area
  type="monotone"
  dataKey="confidenceHigh"
  stackId="confidence"
  stroke="none"
  fill={chartColor.confidence}
  fillOpacity={0.2}
/>
<Area
  type="monotone"
  dataKey="confidenceLow"
  stackId="confidence"
  stroke="none"
  fill={chartColor.tooltipBg}   // <-- tooltip background color used as erasure
  fillOpacity={1}
/>
```

The intent is to show a band between `confidenceLow` and `confidenceHigh`. With Recharts `stackId`, the second area paints from zero up to `confidenceLow`, using `chartColor.tooltipBg` (the tooltip background color) as a solid white/light mask to erase the region below the lower bound. This produces correct-looking output only when the chart background exactly matches `tooltipBg`. On non-white backgrounds (dark mode, card backgrounds that differ), the erasure color will be visually wrong.

The idiomatic Recharts approach for confidence bands is to use two `Area` components with explicit `base` (or the `ReferenceArea` approach), or compute the band width as a separate data series. Alternatively, use `referenceLine` + `ReferenceArea` for the low-to-high span.

Cleanest fix with two Areas (no stacking):

```tsx
// Add to chartData mapping:
bandWidth: point.confidenceHigh - point.confidenceLow,
bandBase: point.confidenceLow,

// Then in JSX — single Area with a custom base:
<Area
  type="monotone"
  dataKey="bandWidth"
  stroke="none"
  fill={chartColor.confidence}
  fillOpacity={0.25}
  baseValue="bandBase"  // Recharts v2.5+
/>
```

---

**P2-02: `DashboardContent.tsx` hardcodes the optimal-window threshold at `0.22 ¢/kWh`**

File: `frontend/components/dashboard/DashboardContent.tsx`, line 71

```tsx
isOptimal: price !== null && price < 0.22,
```

This magic number appears in production logic that affects what users see highlighted as "cheap periods." A threshold that makes sense for Connecticut or New York will be misleading for Texas (often < 0.12) or Hawaii (often > 0.40). The value is also independently hardcoded in `DashboardContent` while the supplier-mapping fallback on line 126 uses a different default (`avgPricePerKwh: s.avgPricePerKwh ?? 0.22`). Two separate magic numbers that could drift apart.

Recommended fix — derive the threshold from the loaded price data (e.g., the 25th percentile of `historyData.prices`) or pull it from a named constant shared with any other use site:

```ts
// frontend/lib/constants/priceThresholds.ts
export const OPTIMAL_PRICE_THRESHOLD_USD_KWH = 0.22

// In DashboardContent.tsx
import { OPTIMAL_PRICE_THRESHOLD_USD_KWH } from '@/lib/constants/priceThresholds'
isOptimal: price !== null && price < OPTIMAL_PRICE_THRESHOLD_USD_KWH,
```

A longer-term improvement is fetching the region-specific percentile from the API so the threshold adapts to the user's actual market.

---

**P2-03: `DashboardContent.tsx` trend is always `'stable'` — the field is never derived from real data**

File: `frontend/components/dashboard/DashboardContent.tsx`, lines 78–85

```tsx
const currentPrice: CurrentPriceInfo | null = rawPrice ? {
  price: parseFloat(rawPrice.current_price),
  trend: 'stable',             // <-- hardcoded, never changes
  changePercent: rawPrice.price_change_24h != null
    ? parseFloat(rawPrice.price_change_24h)
    : null,
  ...
} : null
```

`trend` is always `'stable'` regardless of `changePercent`. This means:
- The trend icon in `DashboardStatsRow` will always show `Minus` (neutral), even if `changePercent` is -15%.
- The price-alert banner in `DashboardContent` (`trend === 'decreasing'`) will never render.
- `PriceLineChart` internally computes its own trend from history data, so the chart header is correct — creating a visual inconsistency where the chart says "decreasing" but the stat card says "stable."

Note: `PriceLineChart` contains its own independent trend computation (lines 65–88 in `PriceLineChart.tsx`) which is correct. The bug is purely in the `CurrentPriceInfo` construction in `DashboardContent`.

Recommended fix — derive trend from `changePercent`:

```tsx
const changePercent = rawPrice.price_change_24h != null
  ? parseFloat(rawPrice.price_change_24h)
  : null

const trend: CurrentPriceInfo['trend'] =
  changePercent == null ? 'stable'
  : changePercent > 1   ? 'increasing'
  : changePercent < -1  ? 'decreasing'
  : 'stable'

const currentPrice: CurrentPriceInfo | null = rawPrice ? {
  price: parseFloat(rawPrice.current_price),
  trend,
  changePercent,
  ...
} : null
```

---

#### P3 — Low

**P3-01: Two `eslint-disable` comments suppress unused variables that represent genuinely incomplete features**

File: `frontend/components/charts/ScheduleTimeline.tsx`, lines 46–52

```tsx
// eslint-disable-next-line @typescript-eslint/no-unused-vars
onReschedule,
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const [draggedSchedule, setDraggedSchedule] = useState<string | null>(null)
```

`onReschedule` is accepted as a prop and destructured but never called. `draggedSchedule` state is set on drag start but never read. The drag-and-drop reschedule feature is partially scaffolded (prop types, handler, state, `draggable` attribute) but not wired up — the `onReschedule` callback is never invoked and there is no `onDrop` handler on the timeline to receive the drop. These suppressions hide real gaps rather than false positives.

Recommended action: Either complete the drag-and-drop implementation (add `onDrop`/`onDragOver` handlers and call `onReschedule`) or, if the feature is deferred, remove the dead code and the prop from `ScheduleTimelineProps` until it is ready to implement. A `// TODO:` comment with a linked issue would communicate intent clearly to future contributors.

---

**P3-02: `AnalyticsDashboard.tsx` imports `React` implicitly but omits the import statement**

File: `frontend/components/analytics/AnalyticsDashboard.tsx`

```tsx
'use client'

import { useState } from 'react'   // React not imported
```

The other analytics components (`DataExport`, `ForecastWidget`, `OptimizationReport`) also omit the `React` import, which is fine with the React 17+ JSX transform. However, `AnalyticsDashboard.tsx` uses only named imports while the dashboard files all begin with `import React from 'react'`. This is a consistency issue rather than a bug, but it makes the analytics directory feel stylistically mismatched from the dashboard directory. With the React 19 target in this project, either convention is valid — pick one and apply it uniformly.

Additionally, `AnalyticsDashboard.tsx` hardcodes the initial state to `'CT'` (line 18). While Connecticut is a reasonable default for a US electricity optimizer, this should either come from the Zustand settings store (`useSettingsStore`) for personalization, or at minimum be a named constant. Users in California opening the `/analytics` route will see Connecticut data by default until they manually change the dropdown.

```tsx
// Better default — pull from user settings
import { useSettingsStore } from '@/lib/store/settings'

export function AnalyticsDashboard() {
  const region = useSettingsStore((s) => s.region)
  // Derive two-letter state code from "us_ca" → "CA" format
  const defaultState = region?.startsWith('us_')
    ? region.slice(3).toUpperCase()
    : 'CT'
  const [state, setState] = useState(defaultState)
  ...
}
```

---

### Statistics

| Severity | Count | Files Affected |
|----------|-------|----------------|
| P0 — Critical | 0 | — |
| P1 — High | 2 | `DataExport.tsx`, `ScheduleTimeline.tsx` |
| P2 — Medium | 3 | `ForecastChart.tsx`, `DashboardContent.tsx` (x2) |
| P3 — Low | 2 | `ScheduleTimeline.tsx`, `AnalyticsDashboard.tsx` |
| **Total** | **7** | **5 files** |

**Files with no findings (clean):** `DashboardSchedule.tsx`, `UtilityDiscoveryCard.tsx`, `CombinedSavingsCard.tsx`, `AllUtilitiesTab.tsx`, `DashboardTabs.tsx`, `UtilityTabShell.tsx`, `DashboardStatsRow.tsx`, `DashboardCharts.tsx`, `DashboardForecast.tsx`, `NeighborhoodCard.tsx`, `CompletionProgress.tsx`, `SetupChecklist.tsx`, `PriceLineChart.tsx`, `SavingsDonut.tsx`, `DataExport.tsx` (aside from P1-01), `ForecastWidget.tsx`, `OptimizationReport.tsx`

**Positive patterns observed across the codebase:**
- All chart components wrapped in `React.memo` with `displayName` set — correct.
- Expensive derivations consistently gated behind `useMemo` with accurate dependency arrays.
- CLS prevention applied in two places: `minHeight: '48px'` banner reservation in `DashboardContent.tsx` and `transform:scaleX()` progress bars in `NeighborhoodCard.tsx`, `SetupChecklist.tsx`, and `CompletionProgress.tsx` — consistent with project pattern standard.
- All chart colors sourced from `chartTokens.ts` CSS custom properties — no hardcoded hex values in chart components.
- `dynamic()` + `ssr: false` + inline `loading` skeletons on both `PriceLineChart` and `ForecastChart` correctly prevents SSR hydration mismatches for Recharts.
- Tier-gating UX is well handled: `ApiClientError` status 403 is intercepted in both `DashboardCharts` and `DashboardForecast` to show upgrade CTAs rather than generic error states.
- Loading, error, and empty states are present in every data-dependent component.
- `SetupChecklist` correctly defers localStorage read to `useEffect` and uses a `null` guard (`dismissed === null`) to suppress the checklist on initial render before hydration — solid SSR-safe pattern.
- `DashboardTabs` URL-driven tab state with `router.replace` + `{ scroll: false }` is the correct Next.js App Router pattern for tab persistence.
