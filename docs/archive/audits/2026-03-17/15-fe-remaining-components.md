# Audit Report: Frontend Remaining Components
## Date: 2026-03-17
## Auditor: Automated Code Review (Claude Sonnet 4.6)

---

## Scope

Files reviewed (37 total across 13 directories):

| Directory | Files |
|-----------|-------|
| `frontend/components/agent/` | AgentChat.tsx |
| `frontend/components/affiliate/` | FTCDisclosure.tsx |
| `frontend/components/alerts/` | AlertForm.tsx, AlertsContent.tsx |
| `frontend/components/gas/` | GasRatesContent.tsx |
| `frontend/components/propane/` | PropaneDashboard.tsx, PropanePriceHistory.tsx, FillUpTiming.tsx |
| `frontend/components/water/` | WaterDashboard.tsx, WaterTierCalculator.tsx, ConservationTips.tsx, WaterRateBenchmark.tsx |
| `frontend/components/suppliers/` | SuppliersContent.tsx, ComparisonTable.tsx, SupplierCard.tsx, SupplierAccountForm.tsx, SupplierSelector.tsx, SetSupplierDialog.tsx, SwitchWizard.tsx |
| `frontend/components/pwa/` | ServiceWorkerRegistrar.tsx, InstallPrompt.tsx |
| `frontend/components/heating-oil/` | HeatingOilDashboard.tsx, OilPriceHistory.tsx, DealerList.tsx |
| `frontend/components/community-solar/` | CommunitySolarContent.tsx, SavingsCalculator.tsx |
| `frontend/components/gamification/` | SavingsTracker.tsx |
| `frontend/components/feedback/` | FeedbackWidget.tsx |
| `frontend/components/rate-changes/` | RateChangeCard.tsx, AlertPreferences.tsx, RateChangeFeed.tsx |
| `frontend/components/cca/` | CCAAlert.tsx, CCAInfo.tsx, CCAComparison.tsx |

Note: No `billing/` or `heating/` directories exist; `heating-oil/` is the correct path.

---

## Executive Summary

Overall code quality across this surface area is good. Components follow consistent patterns: React Query for data fetching, graceful loading/error states, and accessible form labels. The codebase shows evidence of prior quality hardening. No XSS vectors were found (no `dangerouslySetInnerHTML` usage anywhere in these components). No credential exposure or data leaks were identified.

There are no P0 (Critical) findings.

Notable issues requiring attention are:

1. **Hardcoded price fallbacks** in `SuppliersContent.tsx` that could show misleading financial figures to users (P1).
2. **Silent error swallowing** in `SuppliersContent.tsx` that masks backend failures in a financial-action code path (P1).
3. **Missing character-limit enforcement** on AgentChat input submission (P1).
4. **Unvalidated external URLs** in DealerList and CCA components (P1).
5. **Incomplete focus trap** in FeedbackModal — the modal opens but keyboard focus is not trapped within it (P1).
6. A cluster of **P2 accessibility and UX gaps** spread across several components.

---

## Findings

### P0 — Critical

None identified.

No `dangerouslySetInnerHTML` calls, no secret/credential exposure in component logic, no direct SQL/command injection vectors. All server-rendered content goes through React's JSX which escapes by default.

---

### P1 — High

#### P1-01: Hardcoded Price Fallbacks Mask Real Data Gaps — `SuppliersContent.tsx` lines 60–64

```tsx
// Lines 60-64
avgPricePerKwh: s.avgPricePerKwh ?? (s.id === 'supplier_001' ? 0.21 : s.id === 'supplier_002' ? 0.24 : 0.22),
standingCharge: s.standingCharge ?? 0.40,
estimatedAnnualCost: s.estimatedAnnualCost ?? Math.round((s.avgPricePerKwh ?? 0.22) * annualUsage + 365 * 0.40),
```

**Problem:** When the backend returns suppliers without pricing data (null/undefined fields), the component silently substitutes hardcoded prices (e.g., `$0.21/kWh`, `$0.40/day standing charge`). Because these are used directly in the `estimatedAnnualCost` calculation and displayed in `ComparisonTable` and `SupplierCard`, a user could make a supplier switch decision based on fabricated financial data. The supplier ID string comparisons (`supplier_001`, `supplier_002`) are also indicative of development test data leaking into production logic.

**Recommendation:** Remove hardcoded per-supplier price overrides. If a supplier record is missing required pricing fields, filter it out entirely before display, or show a "pricing unavailable" state for that card. Never display fabricated financial figures.

```tsx
// Preferred approach — exclude incomplete supplier records
const suppliers: Supplier[] = (suppliersData?.suppliers || [])
  .filter((s: RawSupplierRecord) =>
    s.avgPricePerKwh != null && s.estimatedAnnualCost != null
  )
  .map((s: RawSupplierRecord) => ({
    id: s.id,
    name: s.name,
    avgPricePerKwh: s.avgPricePerKwh!,
    standingCharge: s.standingCharge ?? 0,
    estimatedAnnualCost: s.estimatedAnnualCost!,
    // ...rest
  }))
```

---

#### P1-02: Silent Swallowing of Backend Errors in Financial Action Path — `SuppliersContent.tsx` lines 86–120

```tsx
// Lines 86-94
const handleSetSupplier = useCallback(async (supplier: Supplier) => {
  try {
    await setSupplierMutation.mutateAsync(supplier.id)
  } catch {
    // Backend save failed — still update local state for offline-first UX
  }
  setCurrentSupplierStore(supplier)  // always runs
  ...
}, ...)

// Lines 98-115 — same pattern for handleSwitchComplete
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

**Problem:** Two separate backend calls are silently swallowed. The user sees the UI update as if the switch succeeded. However:
- If `setSupplierMutation` fails, the user's supplier preference is not persisted to the backend — it only exists in Zustand (which may be cleared on page reload).
- If `initiateSwitch` fails, no switch is actually initiated with the supplier — but the user sees a "success" state.

For a financial action (switching electricity supplier), silent failure is unacceptable. The user believes they have switched but has not.

**Recommendation:** Surface backend errors to the user for these critical operations. At minimum, show a toast or inline error when persistence fails. The "offline-first" pattern is inappropriate for supplier switching, which requires backend coordination.

```tsx
const handleSetSupplier = useCallback(async (supplier: Supplier) => {
  try {
    await setSupplierMutation.mutateAsync(supplier.id)
    setCurrentSupplierStore(supplier)
    setShowSetDialog(false)
    setSelectedSupplier(null)
  } catch (err) {
    // Do NOT silently swallow — surface to user
    toast.error('Failed to save your supplier selection. Please try again.')
  }
}, [setSupplierMutation, setCurrentSupplierStore])
```

---

#### P1-03: Character Limit Not Enforced on AgentChat Submission — `AgentChat.tsx` lines 76–82, 97–98, 226

```tsx
// Line 97
const isOverLimit = charCount > 2000

// Line 79 — handleSubmit only checks trimmed/isStreaming:
if (!trimmed || isStreaming) return
sendQuery(trimmed)

// Line 226 — submit button correctly disables:
disabled={!input.trim() || isOverLimit}
```

**Problem:** The submit button is correctly disabled when over the 2000-character limit. However, `handleSubmit` (line 79) and `handleExampleClick` (line 84) do not guard against the limit. A user who bypasses the button (e.g., presses Enter via `handleKeyDown`) will successfully send a query even when `isOverLimit` is true, because `handleKeyDown` calls `handleSubmit` which has no `isOverLimit` check. Example prompts also bypass the limit check entirely.

**Recommendation:** Add the `isOverLimit` guard to `handleSubmit`:

```tsx
const handleSubmit = (e: React.FormEvent) => {
  e.preventDefault()
  const trimmed = input.trim()
  if (!trimmed || isStreaming || isOverLimit) return
  setInput('')
  sendQuery(trimmed)
}
```

---

#### P1-04: Unvalidated External URLs in DealerList — `DealerList.tsx` lines 49–54

```tsx
{dealer.website && (
  <a
    href={dealer.website}
    target="_blank"
    rel="noopener noreferrer"
  >
    Website
  </a>
)}
```

**Problem:** `dealer.website` is rendered directly from API response data as an `href` without URL validation. A malicious or corrupted backend record could inject a `javascript:` URI. While the project uses React which escapes attribute values, `javascript:` URIs in anchor `href` attributes are not blocked by React's XSS protection — they are valid URI scheme values.

The same concern applies to `CCAInfo.tsx` lines 101 and 110 (`data.program_url`, `data.opt_out_url`), `CCAAlert.tsx` line 49 (`program.program_url`), and `CommunitySolarContent.tsx` line 204 (`program.enrollment_url`).

**Recommendation:** Add a URL validation helper before rendering external links:

```tsx
function isSafeUrl(url: string | null | undefined): boolean {
  if (!url) return false
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:'
  } catch {
    return false
  }
}

// Usage:
{isSafeUrl(dealer.website) && (
  <a href={dealer.website} target="_blank" rel="noopener noreferrer">Website</a>
)}
```

Note: `isSafeRedirect()` already exists in the project per CLAUDE.md patterns — a similar `isSafeExternalUrl()` utility should be added to `lib/utils/`.

---

#### P1-05: Incomplete Focus Trap in FeedbackModal — `FeedbackWidget.tsx` lines 53–62, 85–108

```tsx
// Lines 53-62
useEffect(() => {
  firstFocusRef.current?.focus()  // focuses first radio only
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
  }
  document.addEventListener('keydown', handleKeyDown)
  return () => document.removeEventListener('keydown', handleKeyDown)
}, [onClose])
```

**Problem:** The modal correctly sets initial focus and handles Escape, but does not trap focus. A keyboard-only user can Tab past the last focusable element in the modal, reaching page content beneath the backdrop. This is a WCAG 2.1 AA violation (Success Criterion 2.1.2 — No Keyboard Trap, and success criterion for modal dialog patterns per ARIA Authoring Practices Guide).

**Recommendation:** Implement a proper focus trap. The project already uses Radix UI primitives for other dialogs — if FeedbackModal can be migrated to use a Radix `Dialog.Root`, the focus trap is handled automatically. Alternatively, use the `focus-trap-react` library or implement manually:

```tsx
// Trap focus within the modal panel
useEffect(() => {
  const modal = modalRef.current
  if (!modal) return
  const focusable = modal.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const handleTab = (e: KeyboardEvent) => {
    if (e.key !== 'Tab') return
    if (e.shiftKey ? document.activeElement === first : document.activeElement === last) {
      e.preventDefault()
      ;(e.shiftKey ? last : first).focus()
    }
  }
  document.addEventListener('keydown', handleTab)
  return () => document.removeEventListener('keydown', handleTab)
}, [])
```

---

### P2 — Medium

#### P2-01: AlertsContent Tab Buttons Missing `role="tab"` and ARIA Tablist — `AlertsContent.tsx` lines 319–344

```tsx
<nav className="-mb-px flex gap-6" aria-label="Alert tabs">
  <button onClick={() => setActiveTab('alerts')} ...>My Alerts</button>
  <button onClick={() => setActiveTab('history')} ...>History</button>
</nav>
```

**Problem:** The tab navigation uses plain `<button>` elements without `role="tab"`, `role="tablist"` on the parent, or `aria-selected` attributes. Screen readers will announce these as generic buttons, not as part of a tab pattern. The `<nav>` wrapper adds unneeded landmark semantics for what is logically a tablist.

**Recommendation:**

```tsx
<div role="tablist" aria-label="Alert sections" className="-mb-px flex gap-6">
  <button
    role="tab"
    aria-selected={activeTab === 'alerts'}
    aria-controls="tab-panel-alerts"
    id="tab-alerts"
    onClick={() => setActiveTab('alerts')}
    ...
  >My Alerts</button>
  <button
    role="tab"
    aria-selected={activeTab === 'history'}
    aria-controls="tab-panel-history"
    id="tab-history"
    onClick={() => setActiveTab('history')}
    ...
  >History</button>
</div>
{activeTab === 'alerts'
  ? <div id="tab-panel-alerts" role="tabpanel" aria-labelledby="tab-alerts"><MyAlertsTab /></div>
  : <div id="tab-panel-history" role="tabpanel" aria-labelledby="tab-history"><HistoryTab /></div>
}
```

---

#### P2-02: Missing `aria-label` / `aria-labelledby` on Custom Toggle in AlertPreferences — `AlertPreferences.tsx` line 63

The ARIA switch pattern is correctly used (`role="switch"`, `aria-checked`), and `aria-label` is set. This is fine. However, the cadence `<select>` at line 77 is disabled when the utility is toggled off. When the toggle is off, the select becomes disabled — but there is no visual or ARIA indication that the cadence setting is irrelevant. Consider adding `aria-disabled` styling or hiding the control when disabled.

```tsx
// Current (functional but ambiguous)
<select disabled={!enabled} ...>

// Improvement: visually indicate disabled state with opacity
<select
  disabled={!enabled}
  className={`rounded border px-2 py-1 text-sm ${!enabled ? 'opacity-40 cursor-not-allowed' : ''}`}
  ...
>
```

---

#### P2-03: SavingsTracker Has Hardcoded Monthly Goal — `SavingsTracker.tsx` lines 96–97

```tsx
<span>Monthly Goal: {formatCurrency(50)}</span>
<span>{Math.min(Math.round((monthlySavings / 50) * 100), 100)}%</span>
```

**Problem:** The monthly savings goal is hardcoded to `$50`. The `SavingsTracker` component accepts detailed props but the goal is not configurable. Users with very different energy costs will see misleading goal progress (a high-usage business customer always at 100%; a low-usage apartment dweller always near 0%).

**Recommendation:** Add a `monthlyGoal` prop with a sensible default:

```tsx
interface SavingsTrackerProps {
  // ...existing props
  monthlyGoal?: number // dollars, default 50
}

export function SavingsTracker({ ..., monthlyGoal = 50 }: SavingsTrackerProps) {
  // Replace hardcoded 50 with monthlyGoal throughout
}
```

---

#### P2-04: `SupplierSelector` Dropdown Missing Keyboard Navigation Pattern — `SupplierSelector.tsx`

```tsx
// Lines 66-127
{isOpen && (
  <div className="absolute z-50 ...">
    ...options as <button> elements
  </div>
)}
```

**Problem:** The custom dropdown renders correctly and closes on outside click. However it lacks:
- Arrow key navigation between options (ARIA combobox/listbox pattern).
- `role="listbox"` on the options container.
- `role="option"` and `aria-selected` on each option button.
- Announcing the number of matches when the search filter changes.

The trigger button at line 45 also lacks `aria-expanded` and `aria-haspopup="listbox"`.

**Recommendation:** Add the ARIA combobox attributes:

```tsx
<button
  type="button"
  aria-expanded={isOpen}
  aria-haspopup="listbox"
  aria-controls="supplier-listbox"
  ...
>
```

```tsx
<div id="supplier-listbox" role="listbox" ...>
  {filtered.map((supplier) => (
    <button
      role="option"
      aria-selected={value?.id === supplier.id}
      key={supplier.id}
      ...
    >
```

---

#### P2-05: `SetSupplierDialog` Uses `role="option"` Without `role="listbox"` Parent — `SetSupplierDialog.tsx` lines 57–59

```tsx
role="option"
aria-selected={selected?.id === supplier.id}
tabIndex={0}
```

**Problem:** The supplier items have `role="option"` and `aria-selected`, which are the correct ARIA roles for a listbox item. However, the parent container (`<div className="max-h-[400px] space-y-2 overflow-y-auto">` at line 41) is missing `role="listbox"`. A `role="option"` without an ancestor `role="listbox"` is invalid per the ARIA spec and will result in screen reader announcement errors.

**Recommendation:** Add `role="listbox"` to the scrollable container:

```tsx
<div
  role="listbox"
  aria-label="Select your electricity supplier"
  className="max-h-[400px] space-y-2 overflow-y-auto"
>
```

---

#### P2-06: SuppliersContent Modals Missing `aria-describedby` — `SuppliersContent.tsx` lines 350–379

```tsx
<div className="fixed inset-0 z-50 ..."
  role="dialog"
  aria-modal="true"
  aria-label="Switch supplier"   // only aria-label, no description
>
```

Both the `SwitchWizard` modal and `SetSupplierDialog` modal have `role="dialog"` and `aria-modal="true"` and `aria-label` but no `aria-describedby`. The ARIA dialog pattern recommends providing a description element to give context to screen reader users. Additionally, neither modal implementation prevents background scrolling (`overflow: hidden` on `body`) or prevents pointer interaction with the page behind the backdrop.

**Recommendation:** The modals render a `bg-black/50` backdrop overlay but clicking outside the `max-w-2xl` panel container (the div child) would not dismiss the dialog — only clicking within the inner div. This may be intentional (user must explicitly cancel) but note that the backdrop does not receive an `onClick` to dismiss either, unlike `FeedbackModal` which has `onClick={onClose}` on the backdrop. This is fine for a destructive-action wizard but should be documented.

---

#### P2-07: `WaterTierCalculator` Accepts Negative Usage Input — `WaterTierCalculator.tsx` lines 93–102

```tsx
<input
  id="water-usage"
  type="number"
  min={0}
  max={100000}
  value={usageGallons}
  onChange={(e) => setUsageGallons(Number(e.target.value) || 0)}
  ...
/>
```

**Problem:** `min={0}` is a browser hint only, not enforced server-side. The `|| 0` coercion means typing `-1` results in `NaN || 0 = 0` (safe), but `Number(-50) = -50` (a valid non-NaN number), so negative values pass through to `calculateCost()`. The `calculateCost` function has no guard against negative `gallons`, and with a negative input the math would produce negative costs displayed to the user.

**Recommendation:** Clamp the value in the `onChange` handler:

```tsx
onChange={(e) => setUsageGallons(Math.max(0, Number(e.target.value) || 0))}
```

---

#### P2-08: `AgentChat` Messages Keyed by Array Index — `AgentChat.tsx` line 161

```tsx
{messages.map((msg, i) => (
  <MessageBubble key={i} message={msg} />
))}
```

**Problem:** React keys should be stable and unique identifiers, not array indices. When messages are streamed in or updated (e.g., the streaming content of the last message grows), React may not correctly identify which DOM node to update, causing unnecessary re-renders of all message bubbles. Depending on how the `useAgentQuery` hook appends streaming chunks, this could cause visible flicker or focus loss.

**Recommendation:** Add a stable `id` field to `AgentMessage`, or generate one client-side on creation:

```tsx
// If AgentMessage has no id, assign on creation in the hook
messages.map((msg) => (
  <MessageBubble key={msg.id} message={msg} />
))
```

---

#### P2-09: `HeatingOilDashboard` and `PropaneDashboard` Duplicate Nearly Identical Code — Multiple files

`HeatingOilDashboard.tsx` (134 lines) and `PropaneDashboard.tsx` (133 lines) are structurally identical: both fetch prices, display a national average, render a state selector, display state price cards with percentage-vs-national-average diff, and then show `<OilPriceHistory>` / `<PropanePriceHistory>` plus a detail sub-component. Even the state abbreviation lookup maps are similarly structured (both restricted to northeast US states).

Similarly, `OilPriceHistory.tsx` (75 lines) and `PropanePriceHistory.tsx` (75 lines) are nearly line-for-line identical, differing only in the hook they call and minor copy differences.

**Problem:** This is a significant duplication (~300 lines) that will lead to maintenance drift — any bug fix or feature addition must be applied in two places.

**Recommendation:** Extract a generic `FuelDashboard` and `FuelPriceHistory` component parameterized by fuel type:

```tsx
interface FuelDashboardProps {
  fuelType: 'heating_oil' | 'propane'
  useFuelPrices: () => UseQueryResult<FuelPricesData>
  useFuelHistory: (state: string, weeks: number) => UseQueryResult<FuelHistoryData>
  DetailComponent?: React.ComponentType<{ state: string }>
  stateNames: Record<string, string>
  unit: string
  accentColor: string // 'warning' | 'primary'
}
```

---

#### P2-10: `GasRatesContent` Missing Error State — `GasRatesContent.tsx`

```tsx
const { data: ratesData, isLoading: ratesLoading } = useGasRates(region)
const { data: statsData, isLoading: statsLoading } = useGasStats(region, 30)
const { data: historyData, isLoading: historyLoading } = useGasHistory(region, 90)
const { data: compareData, isLoading: compareLoading } = useGasSupplierComparison(...)
```

**Problem:** All four `useQuery` hooks destructure only `data` and `isLoading`. None destructure `isError`. If any of these queries fail, the component silently renders empty/null states (e.g., `priceNum` will be `null`, and the card will show `--`) with no indication to the user that an error occurred. The gas/stats/history failure modes are particularly silent because individual cards just show `--` with no error message.

**Recommendation:** Add error handling, at minimum for the primary `ratesData` query:

```tsx
const { data: ratesData, isLoading: ratesLoading, isError: ratesError } = useGasRates(region)

// Render a top-level error state if the primary query fails
if (ratesError) {
  return (
    <div className="rounded-lg border border-danger-200 bg-danger-50 p-6 text-center">
      <p className="text-sm text-danger-700">
        Failed to load natural gas rates. Please refresh and try again.
      </p>
    </div>
  )
}
```

---

#### P2-11: `CCAAlert` Region Slice Assumes `us_` Prefix Without Guard — `CCAAlert.tsx` line 13

```tsx
const stateCode = region ? region.slice(3).toUpperCase() : undefined
```

**Problem:** This assumes `region` always has the `us_` prefix (3 characters) without checking. If `region` is something like `international_ca` or is shorter than 3 characters (e.g., an edge case region value), `slice(3)` will produce an incorrect string or an empty string. The project's Region enum per CLAUDE.md includes "international" values.

**Recommendation:** Match the pattern used in `CommunitySolarContent.tsx` which is safer:

```tsx
// CommunitySolarContent.tsx (correct pattern):
const stateCode = region?.startsWith('us_')
  ? region.slice(3).toUpperCase()
  : null

// CCAAlert.tsx (current — missing startsWith guard):
const stateCode = region ? region.slice(3).toUpperCase() : undefined
```

Fix `CCAAlert.tsx` to match the `CommunitySolarContent` pattern.

---

#### P2-12: `InstallPrompt` Increments Visit Count on Every Mount — `InstallPrompt.tsx` lines 24–27

```tsx
const visits = parseInt(localStorage.getItem(VISIT_COUNT_KEY) || '0', 10) + 1
localStorage.setItem(VISIT_COUNT_KEY, String(visits))
```

**Problem:** The visit count increments every time the `InstallPrompt` component mounts. In Next.js App Router with React strict mode, components mount twice in development. More critically, if `InstallPrompt` is included in a layout that remounts frequently (e.g., on route changes in a non-persistent layout), the visit count could be artificially inflated. Each route navigation would count as a new "visit."

The intent appears to be "2 unique page loads/sessions," but the implementation counts component mounts. In a SPA, this distinction matters.

**Recommendation:** Store a session marker to differentiate actual sessions from re-renders:

```tsx
useEffect(() => {
  if (typeof window === 'undefined') return
  if (localStorage.getItem(DISMISSED_KEY) === 'true') return

  // Only count once per session (sessionStorage clears on tab close)
  if (!sessionStorage.getItem('rateshift_session_counted')) {
    sessionStorage.setItem('rateshift_session_counted', 'true')
    const visits = parseInt(localStorage.getItem(VISIT_COUNT_KEY) || '0', 10) + 1
    localStorage.setItem(VISIT_COUNT_KEY, String(visits))
  }

  if (parseInt(localStorage.getItem(VISIT_COUNT_KEY) || '0', 10) < MIN_VISITS) return
  // ...rest of handler
}, [])
```

---

### P3 — Low

#### P3-01: `console.log` Calls Left in Production PWA Components

- `InstallPrompt.tsx` line 46: `console.log('[PWA] Install result:', result.outcome)`
- `ServiceWorkerRegistrar.tsx` line 17: `console.log('[SW] Registered:', reg.scope)`
- `ServiceWorkerRegistrar.tsx` line 20: `console.warn('[SW] Registration failed:', err)`

These log calls expose internal implementation details in the browser console for production users. While not security-sensitive in this case, they are noise. The SW registration failure in particular should be logged via the project's observability layer (OTel) rather than just `console.warn`, as a failed SW registration is a meaningful production signal.

**Recommendation:** Remove `console.log` calls. For the SW failure, consider calling a monitoring endpoint or using the OTel error reporting pattern established elsewhere in the project.

---

#### P3-02: `SwitchWizard` GDPR Consent Copy References UK Law — `SwitchWizard.tsx` line 182

```tsx
"We comply with GDPR and UK data protection laws."
```

**Problem:** RateShift is a US-based product serving US electricity consumers. Referencing "UK data protection laws" is factually incorrect for a US product and could confuse or mislead users. This appears to be placeholder copy from a UK-market template.

**Recommendation:** Update copy to reference US data protection standards:

```
"We comply with applicable US data protection laws and privacy regulations.
Your information will only be shared with {supplier.name} for the purpose
of switching your energy supply."
```

---

#### P3-03: `WaterDashboard` Duplicates Full US State Map — `WaterDashboard.tsx` lines 8–21

```tsx
const US_STATES: Record<string, string> = {
  AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', ... (52 entries)
}
```

The project has a Region enum and constants in `backend/models/region.py`. On the frontend, a `STATE_LABELS` constant already exists (imported in `AlertsContent.tsx`). The water dashboard re-declares the full 50-state + DC map inline rather than importing from `@/lib/constants/regions`.

**Recommendation:** Import from the existing constants:

```tsx
import { STATE_LABELS } from '@/lib/constants/regions'
// Then use STATE_LABELS[code] instead of US_STATES[code]
```

Similarly, `HeatingOilDashboard.tsx` and `PropaneDashboard.tsx` both declare their own local `STATE_NAMES` records (both restricted to northeast states only). These should also use the shared constant and filter by the `trackedStates` array returned by the API, rather than hardcoding the available states.

---

#### P3-04: `CommunitySolarService` Export Name Mismatch — `SavingsCalculator.tsx` line 11

```tsx
/**
 * CommunitySolarService — Savings calculator component.
 * Named this way to match the export in CommunitySolarContent.
 */
export function CommunitySolarService() {
```

The exported function is named `CommunitySolarService` despite being a React component (not a service). The file is named `SavingsCalculator.tsx`. The comment acknowledges the naming inconsistency. This creates confusion when reading imports:

```tsx
// In CommunitySolarContent.tsx — looks like a service import, not a component:
import { CommunitySolarService } from './SavingsCalculator'
...
<CommunitySolarService />
```

**Recommendation:** Rename to `CommunitySolarCalculator` or `SavingsCalculator` to match the file name and React component naming conventions, updating the import in `CommunitySolarContent.tsx`.

---

#### P3-05: `AlertsContent` `formatDate` Relies on `toLocaleString()` Without Locale Parameter — `AlertsContent.tsx` line 41

```tsx
function formatDate(iso: string | null): string {
  if (!iso) return '--'
  return new Date(iso).toLocaleString()
}
```

`toLocaleString()` without a locale argument uses the browser's default locale, which will produce different date formats for different users (e.g., MM/DD/YYYY vs DD/MM/YYYY vs YYYY/MM/DD). This is inconsistent with the project's `formatDateTime` utility used in `GasRatesContent.tsx` which accepts an explicit format string.

**Recommendation:** Use the project's existing format utility for consistency:

```tsx
import { formatDateTime } from '@/lib/utils/format'
// Then: formatDateTime(iso, 'dd MMM yyyy, HH:mm')
```

---

#### P3-06: `RateChangeCard` Renders Internal Region Codes Without Display Name Lookup — `RateChangeCard.tsx` line 35

```tsx
<p className="font-semibold">{change.region} &mdash; {change.supplier}</p>
```

`change.region` is a raw Region enum value (e.g., `us_ny`, `us_ca`). `AlertsContent.tsx` correctly uses a `formatRegion()` helper that maps `us_ny` → "New York". `RateChangeCard` skips this and renders the raw code directly to users.

**Recommendation:** Apply the same `formatRegion()` pattern or import and use `STATE_LABELS` from constants.

---

#### P3-07: `FTCDisclosure` is Missing `'use client'` Directive

`FTCDisclosure.tsx` has no `'use client'` directive. This is fine if the component is purely presentational and never renders any client hooks. Confirm it is only rendered in server or client contexts. However, it's inconsistent with all other components in the codebase which explicitly declare `'use client'` at the top. If it is ever used in a client component tree (which it currently is — inside `SuppliersContent.tsx` which is client), this works fine but the lack of explicit directive could cause confusion for future developers.

This is a minor style issue, not a functional bug.

---

## Statistics

| Severity | Count | Files Affected |
|----------|-------|----------------|
| P0 (Critical) | 0 | — |
| P1 (High) | 5 | AgentChat, SuppliersContent (x2), DealerList/CCA/CommunitySolar, FeedbackWidget |
| P2 (Medium) | 12 | AlertsContent, AlertPreferences, SavingsTracker, SupplierSelector, SetSupplierDialog, SuppliersContent, WaterTierCalculator, AgentChat, HeatingOil+Propane (duplication), GasRatesContent, CCAAlert, InstallPrompt |
| P3 (Low) | 7 | ServiceWorkerRegistrar, InstallPrompt, SwitchWizard, WaterDashboard, SavingsCalculator, AlertsContent, RateChangeCard, FTCDisclosure |
| **Total** | **24** | **~20 files** |

### Files with Most Issues

| File | Findings |
|------|----------|
| `SuppliersContent.tsx` | P1-01, P1-02, P2-06 |
| `AlertsContent.tsx` | P2-01, P3-05 |
| `HeatingOilDashboard.tsx` / `PropaneDashboard.tsx` | P2-09, P3-03 |
| `AgentChat.tsx` | P1-03, P2-08 |
| `FeedbackWidget.tsx` | P1-05 |
| `DealerList.tsx` / `CCAAlert.tsx` / `CCAInfo.tsx` / `CommunitySolarContent.tsx` | P1-04 |

### Code Quality Observations

**Strengths (no findings required):**

- `AlertForm.tsx`: Excellent. Comprehensive validation, correct `role="alert"` on error states, proper tier-limit 403 handling surfaced as an upgrade prompt, all inputs labeled.
- `SwitchWizard.tsx`: Well-structured multi-step wizard with proper loading/error states, progress indicator, GPU-composited progress bar using `transform: scaleX()` (per project patterns).
- `FeedbackWidget.tsx`: Good modal implementation overall — backdrop click-to-close, Escape key handling, `aria-modal`, `aria-labelledby`, character count display. Only the focus trap is missing.
- `SupplierAccountForm.tsx`: Strong security messaging, regex validation with user-visible feedback, 15-second timeout on submission, consent checkbox required before submit, `autoComplete="off"` on sensitive fields.
- `GasRatesContent.tsx`: Well-organized multi-card layout, correct Skeleton placeholders per card, conditional supplier comparison only for deregulated states.
- `ComparisonTable.tsx`: Good use of `useMemo` for filtering/sorting/cheapest calculation, `useCallback` for sort handler, `role="table"` on the table, `scope="col"` on headers, keyboard-accessible sort buttons.

### Priority Fix Order

1. **P1-01** (Hardcoded prices in SuppliersContent) — Financial data integrity risk
2. **P1-02** (Silent error swallowing in supplier switch) — User trust + data consistency
3. **P1-04** (Unvalidated external URLs) — XSS mitigation across 4+ components
4. **P1-03** (AgentChat character limit bypass) — Rate limit circumvention
5. **P1-05** (FeedbackModal focus trap) — WCAG 2.1 AA compliance
6. **P2-05** (SetSupplierDialog missing role="listbox") — ARIA validity
7. **P2-01** (AlertsContent tab ARIA) — WCAG compliance
8. **P2-11** (CCAAlert region slice) — Correctness for international regions
9. **P2-10** (GasRatesContent silent error states) — UX quality
10. Remaining P2/P3 items in any order

---

*Report generated by automated code review. All line numbers reference the files as read on 2026-03-17.*
