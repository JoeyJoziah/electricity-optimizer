# CSS & Tailwind Audit — 2026-03-16

## Summary

| Severity | Count | Category |
|----------|-------|----------|
| P0 | 1 | Missing `darkMode` config key — dark mode opt-in silently disabled |
| P1 | 5 | Hardcoded raw-color classes bypass design system tokens |
| P1 | 1 | `scrollbar-hide` utility used but no plugin registered |
| P1 | 1 | Duplicate keyframe definitions across globals.css + tailwind.config.ts |
| P2 | 4 | Arbitrary Tailwind values mixed with scale values |
| P2 | 3 | Inline `style={}` for things that belong in utility classes |
| P2 | 3 | Inconsistent `animate-bounce` on layout property (height shift) |
| P2 | 2 | Sticky/fixed containers missing `overflow: hidden` on parent |
| P2 | 1 | Modal missing `sm:` width breakpoint — full-screen on mobile |
| P2 | 1 | `tailwind.config.ts` content paths do not include `frontend/src/` prefix |
| P3 | 2 | Duplicate inline button styling that should use `<Button>` primitive |
| P3 | 1 | Chart tooltip CSS-in-JS object conflicts with Tailwind border tokens |
| P3 | 2 | Progress bars use `style={{ width: X% }}` correctly but lack `will-change` |
| P3 | 0 | Print styles — no `@media print` rules anywhere (low impact for a web app) |

**Total issues: 27 across 18 files**

---

## P0 — Critical

### P0-01: No `darkMode` config key — dark mode is permanently disabled with no enforcement

**File:** `frontend/tailwind.config.ts` line 2–3 and `frontend/app/globals.css` lines 6–16

**Description:** `tailwind.config.ts` has no `darkMode` key, which means Tailwind defaults to the `media` strategy. The app simultaneously forces `color-scheme: light` in `:root` to prevent browser dark mode from breaking hardcoded light-color classes. These two choices are in direct tension: the config says "respect the OS preference," but the CSS overrides the browser and forces light. The comment in `globals.css` is accurate and documents the intent, but the correct fix is to set `darkMode: 'class'` in the config so the behavior is explicit, predictable, and ready for the future implementation that is called out in the comment. Without it, any Tailwind `dark:` classes a developer writes will either silently apply (if the OS is in dark mode and the browser honours `prefers-color-scheme`) or do nothing, making the system unpredictable.

**Fix:**
```ts
// tailwind.config.ts
const config: Config = {
  darkMode: 'class',   // add this — locks the strategy to explicit class toggling
  content: [...],
  ...
}
```

And update `globals.css` `:root` comment to reflect that `darkMode: 'class'` is now the explicit opt-in mechanism, not a future TODO.

---

## P1 — High

### P1-01: Hardcoded raw Tailwind color classes bypass semantic design-system tokens — 30+ occurrences

**Files (representative sample):**
- `frontend/components/propane/PropaneDashboard.tsx` lines 35, 50–56, 107
- `frontend/components/heating-oil/HeatingOilDashboard.tsx` lines 36, 51–54, 73, 98–99, 108
- `frontend/components/water/WaterDashboard.tsx` line 29 (`bg-cyan-50`, `text-cyan-900`, `text-cyan-700`, `focus:border-cyan-500`, `focus:ring-cyan-500`)
- `frontend/components/cca/CCAAlert.tsx` lines 22, 25, 28, 33, 41, 51, 61 (`text-blue-*`, `bg-blue-*`, `border-blue-*`)
- `frontend/components/layout/NotificationBell.tsx` lines 101, 124 (`bg-red-600`, `text-blue-600`, `text-blue-800`)
- `frontend/components/ui/toast.tsx` lines 37–39 (`bg-blue-50`, `border-blue-200`, `text-blue-600`)
- `frontend/components/onboarding/RegionSelector.tsx` lines 43, 80 (`text-blue-600`, `bg-blue-50`, `text-blue-700`)
- `frontend/components/dashboard/UtilityDiscoveryCard.tsx` lines 26–28, 55, 57, 63, 70, 83, 86 (`text-blue-*`, `bg-blue-*`, `border-blue-*`, `text-green-*`)
- `frontend/components/rate-changes/RateChangeCard.tsx` lines 41, 60–64 (`bg-green-100`, `text-green-700`, `bg-blue-50`, `text-blue-*`)
- `frontend/components/seo/RatePageContent.tsx` lines 171–175 (`bg-blue-50`, `text-blue-900`, `text-blue-700`)
- `frontend/components/water/WaterRateBenchmark.tsx` lines 38–40, 44, 84 (`bg-green-50`, `text-green-*`, `bg-red-50`, `text-red-*`, `text-green-600`)

**Description:** The design system defines semantic tokens: `primary-*`, `success-*`, `warning-*`, `danger-*`, plus theme CSS custom properties. Dozens of components bypass these and write raw `bg-blue-*`, `text-green-*`, `bg-red-*`, `text-cyan-*`, etc. This means:
1. If the brand primary color changes from blue, all raw `blue-*` classes must be hunted down manually.
2. The `electricity.cheap/moderate/expensive` tokens defined in `tailwind.config.ts` lines 61–63 are unused in all audited files — the same green/amber/red values are re-inlined.
3. "Blue" is used inconsistently for "info" state — sometimes `primary-*`, sometimes raw `blue-*`, even `text-blue-600` next to `focus:ring-primary-500` in the same component.

**Fix (pattern):**
```tsx
// Before
<div className="rounded-lg border bg-blue-50 p-4">
  <p className="text-sm font-medium text-blue-900">National Average</p>

// After — use the primary token for informational/brand blue
<div className="rounded-lg border bg-primary-50 p-4">
  <p className="text-sm font-medium text-primary-900">National Average</p>
```

For danger/error states use `danger-*`, for positive/savings use `success-*`, for warnings use `warning-*`. For cyan-flavored water UI, add a `utility.water` semantic token in `tailwind.config.ts` rather than embedding `cyan-*` values directly.

---

### P1-02: `scrollbar-hide` utility used but no plugin provides it

**File:** `frontend/components/dashboard/DashboardTabs.tsx` line 65

**Description:** `className="flex gap-0 overflow-x-auto scrollbar-hide px-4 sm:px-6"` uses `scrollbar-hide` which is a custom utility provided by `tailwindcss-scrollbar-hide` or similar plugin. `tailwind.config.ts` has `plugins: []` — empty. The class will be silently ignored in production, leaving a visible scrollbar on mobile in the tab row. It works locally only if the class happens to be injected through some other stylesheet.

**Fix:**
```bash
npm install tailwindcss-scrollbar-hide
```
```ts
// tailwind.config.ts
plugins: [require('tailwindcss-scrollbar-hide')],
```

Or replace with an inline CSS approach since this is a single usage:
```tsx
className="flex gap-0 overflow-x-auto [&::-webkit-scrollbar]:hidden px-4 sm:px-6"
```

---

### P1-03: Keyframe definitions duplicated between `globals.css` and `tailwind.config.ts`

**Files:**
- `frontend/app/globals.css` lines 125–196 define `slideDown`, `fadeIn`, `slideUp`, `scaleIn`, `shimmer`
- `frontend/tailwind.config.ts` lines 86–113 define the identical set: `flashGreen`, `flashRed`, `slideDown`, `slideUp`, `fadeIn`, `scaleIn`, `shimmer`

**Description:** `slideDown`, `slideUp`, `fadeIn`, `scaleIn`, and `shimmer` are each defined twice — once in the CSS file and once in the Tailwind config keyframes. The CSS file also adds hand-rolled `.animate-slideDown`, `.animate-slideUp`, etc. class aliases (lines 177–196) alongside the Tailwind `animation-*` tokens. This means:
1. Two separate `@keyframes slideDown` blocks in the final CSS output (one from Tailwind JIT, one from globals).
2. The globals `.animate-fadeIn` differs from Tailwind's `animate-fade-in` name — the CSS definition on line 136–143 has an erroneous `transform: translateY(0)` in the `to` state that the config version (lines 102–104) lacks, creating a subtle behaviour divergence.
3. Developers must maintain two sources of truth.

**Fix:** Remove the duplicated `@keyframes` blocks and `.animate-*` classes from `globals.css` lines 124–196. Use only the Tailwind config definitions and their generated `animate-*` utilities. Keep the `.skeleton` class and chart tooltip overrides in globals as they serve a different purpose.

---

### P1-04: `tailwind.config.ts` content paths missing `frontend/src/` prefix — classes potentially purged in some build environments

**File:** `frontend/tailwind.config.ts` lines 4–8

```ts
content: [
  './pages/**/*.{js,ts,jsx,tsx,mdx}',
  './components/**/*.{js,ts,jsx,tsx,mdx}',
  './app/**/*.{js,ts,jsx,tsx,mdx}',
],
```

**Description:** The repo uses a flat `frontend/` layout where source files live directly in `frontend/components/`, `frontend/app/`, etc. (confirmed by directory listing). The content globs use relative paths starting with `./`, which resolve relative to wherever Tailwind is invoked. This works when Tailwind is run from inside `frontend/`. However, if any toolchain invokes Tailwind from the monorepo root (e.g., a CI script that runs `npx tailwindcss` from `/`), none of these globs will match and all JIT classes will be purged. The Next.js build currently works because Next invokes Tailwind from the `frontend/` dir. This is a latent risk.

More concretely: the `src/` directory referenced in the original project skeleton (`./pages/**` is a Pages Router path, the repo uses App Router under `app/`) means `./pages/**` is dead weight. The actual source is under `app/` and `components/`, which are covered, but adding explicit absolute paths or a `src` entry would be safer.

**Fix:**
```ts
content: [
  './app/**/*.{js,ts,jsx,tsx,mdx}',
  './components/**/*.{js,ts,jsx,tsx,mdx}',
  './lib/**/*.{js,ts,jsx,tsx}',   // captures cn() class strings in utility files
],
```

---

### P1-05: Hardcoded color hex values in Recharts configuration bypass tokens entirely

**File:** `frontend/components/charts/PriceLineChart.tsx` lines 24–29, 234, 263–265, 270, 283

**Description:**
```tsx
const tooltipStyle = {
  backgroundColor: 'white',
  border: '1px solid #e5e7eb',   // hardcoded — should be var(--color-border)
  borderRadius: '8px',            // hardcoded — should be var(--radius-lg)
  boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',  // hardcoded shadow-md value
}
// ...
<CartesianGrid stroke="#e5e7eb" />       // same hardcoded gray-200
<ReferenceArea fill="#22c55e" />         // hardcoded success-500
<Line stroke="#3b82f6" />               // hardcoded primary-500
<Line stroke="#f59e0b" />               // hardcoded warning-500
```

Recharts does not accept Tailwind classes; inline objects are required. But the values should reference CSS custom properties so they stay in sync with the design system:

**Fix:**
```tsx
const tooltipStyle = {
  backgroundColor: 'rgb(var(--color-surface))',
  border: '1px solid rgb(var(--color-border))',
  borderRadius: 'var(--radius-lg)',
  boxShadow: 'var(--shadow-md)',
}
// and use CSS var() references for stroke/fill values, or define a CHART_COLORS
// const in a shared file:
const CHART_COLORS = {
  price: '#3b82f6',     // primary-500
  forecast: '#f59e0b',  // warning-500
  optimal: '#22c55e',   // success-500
  grid: '#e5e7eb',      // gray-200
} as const
```

This is a P1 because the tooltip background is hardcoded as `'white'` — if the surface variable is ever changed or dark mode is added, chart tooltips will have a mismatched background while everything else updates.

---

## P2 — Medium

### P2-01: Arbitrary Tailwind values mixed with scale values — `max-w-[80%]`, `max-h-[400px]`, `max-h-[90vh]`, `min-h-[80px]`, `max-w-[150px]`

**Files:**
- `frontend/components/agent/AgentChat.tsx` line 27: `max-w-[80%]`
- `frontend/components/suppliers/SetSupplierDialog.tsx` line 41: `max-h-[400px]`
- `frontend/components/suppliers/SuppliersContent.tsx` lines 351, 367: `max-h-[90vh]`, `max-w-2xl`, `max-w-lg`
- `frontend/components/charts/ScheduleTimeline.tsx` line 191: `min-h-[80px]`
- `frontend/components/connections/analytics/RateHistoryCard.tsx` line 110: `max-w-[150px]`

**Description:** Five components use arbitrary bracket values for dimensions. The core issue is not the use of arbitrary values per se (Tailwind permits them), but inconsistency — `max-w-2xl` (a scale value) sits next to `max-h-[90vh]` (arbitrary) in the same element in SuppliersContent. The `max-h-[400px]` in SetSupplierDialog is a magic number with no comment explaining why 400px. The `max-w-[80%]` in AgentChat chat bubbles could use `max-w-4/5` (if using Tailwind v4) or a responsive value.

**Fix:** For `max-h-[400px]`, add to the Tailwind `theme.extend` if this constraint is reused:
```ts
// tailwind.config.ts
theme: {
  extend: {
    maxHeight: {
      'dialog': '400px',
      'modal': '90vh',
    }
  }
}
```
Or accept the arbitrary values and add an explanatory comment inline.

---

### P2-02: Inline `style={}` for things that belong in utility classes — three animation delay instances

**File:** `frontend/components/agent/AgentChat.tsx` lines 166–168

```tsx
<span ... style={{ animationDelay: '0ms' }} />
<span ... style={{ animationDelay: '150ms' }} />
<span ... style={{ animationDelay: '300ms' }} />
```

**Description:** Tailwind does not have built-in animation delay utilities in v3 but this is trivially solved with arbitrary values or a small extension. Using `style={}` for animation delays in three adjacent JSX elements creates three inline style objects per render, bypasses Tailwind's JIT cache, and cannot be controlled by Tailwind's `motion-safe:` / `motion-reduce:` variants.

**Fix:**
```ts
// tailwind.config.ts — add to theme.extend
animationDelay: {
  '0': '0ms',
  '150': '150ms',
  '300': '300ms',
},
```
Or use arbitrary values (which also get JIT-cached and support variants):
```tsx
<span className="h-2 w-2 animate-bounce rounded-full bg-primary-400 [animation-delay:0ms]" />
<span className="h-2 w-2 animate-bounce rounded-full bg-primary-400 [animation-delay:150ms]" />
<span className="h-2 w-2 animate-bounce rounded-full bg-primary-400 [animation-delay:300ms]" />
```

---

### P2-03: `animate-bounce` on the typing indicator animates `transform: translateY` — this is GPU-composited and fine, but `animate-ping` in Header uses `opacity` + `transform` simultaneously which can cause repaints on some browsers

**File:** `frontend/components/layout/Header.tsx` lines 56–59

```tsx
<span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success-400 opacity-75" />
```

**Description:** `animate-ping` from Tailwind animates `transform: scale` + `opacity` simultaneously. This is correct and GPU-composited. However, the outer `<span className="relative flex h-2 w-2">` has no explicit `width`/`height` constraint on the child — the `h-full w-full` on the ping span will render at whatever size the parent reports, and if the `flex` layout shifts (e.g., during SSR/hydration), there can be a brief CLS event. The live indicator has no `aria-hidden` and will be announced by screen readers as an empty element. Minor but worth fixing.

Additionally, `animate-bounce` (used in AgentChat, lines 166–168) animates `transform: translateY` — this is correct and composited. No change needed for the bounce.

**Fix for Header ping indicator:**
```tsx
<div
  data-testid="realtime-indicator"
  className="hidden items-center gap-2 text-sm text-gray-500 sm:flex"
>
  <span className="relative flex h-2 w-2" aria-hidden="true">  {/* add aria-hidden */}
    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success-400 opacity-75" />
    <span className="relative inline-flex h-2 w-2 rounded-full bg-success-500" />
  </span>
  <span>Live</span>
</div>
```

---

### P2-04: Modal component has no responsive width — renders as fixed `max-w-md` even on mobile

**File:** `frontend/components/ui/modal.tsx` line 95

```tsx
<div className={cn('w-full max-w-md rounded-lg bg-white p-6 shadow-xl')}>
```

**Description:** `w-full max-w-md` means the modal is constrained to 28rem (448px) on all viewport sizes. On mobile (320–375px), this renders correctly because `w-full` takes the viewport width. However there is no horizontal margin — the modal content sits edge-to-edge on narrow screens with `p-6` (24px) padding. The overlay is `flex items-center justify-center` with no padding, so the modal bleeds to viewport edges on very narrow screens (under 360px). Compare with the SuppliersContent inline modals which correctly add `mx-auto` and use `max-h-[90vh] overflow-y-auto`.

**Fix:**
```tsx
<div className={cn(
  'w-full max-w-md rounded-lg bg-white p-6 shadow-xl',
  'mx-4 sm:mx-0'    // adds 16px horizontal breathing room on narrow screens
)}>
```

---

### P2-05: `flex-1 lg:pl-64` in the app shell — no `overflow-hidden` or `min-w-0` — can cause horizontal scroll with wide table content

**File:** `frontend/app/(app)/layout.tsx` line 20

```tsx
<main id="main-content" className="flex-1 lg:pl-64">{children}</main>
```

**Description:** `flex-1` inside a flex container without `min-w-0` can expand beyond the container bounds when children (like `ComparisonTable` or `ConnectionRates` which use `overflow-x-auto`) have wide content. The `overflow-x-auto` on the table wrapper prevents scrollbars inside the table, but if the `<main>` itself does not constrain its width, the outer page can develop a horizontal scrollbar on screens narrower than the table's minimum content width. This is a known "flex item min-size" gotcha.

**Fix:**
```tsx
<main id="main-content" className="flex-1 min-w-0 lg:pl-64">{children}</main>
```

---

### P2-06: Propane and HeatingOil dashboards use inconsistent focus colors on selects (`focus:border-blue-500 focus:ring-blue-500`) that differ from the rest of the app

**Files:**
- `frontend/components/propane/PropaneDashboard.tsx` line 72: `focus:border-blue-500 focus:ring-blue-500`
- `frontend/components/heating-oil/HeatingOilDashboard.tsx` line 73: `focus:border-blue-500 focus:ring-blue-500`

**Description:** Every other focusable element in the codebase uses `focus:border-primary-500 focus:ring-primary-500` (AlertForm, ConnectionCard label input, AgentChat textarea, etc.). These two dashboards use raw `blue-500` which happens to look the same (primary is also blue), but will break if the primary color ever changes, and they are semantically incorrect in the design system.

**Fix:**
```tsx
// Replace in both files
className="mt-1 block w-full rounded-md border-gray-300 shadow-sm
           focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
```

---

### P2-07: `WaterDashboard` select has missing border padding and inconsistent token usage

**File:** `frontend/components/water/WaterDashboard.tsx` lines 44–48

```tsx
className="mt-1 block w-full rounded-md border-gray-300 shadow-sm
           focus:border-cyan-500 focus:ring-cyan-500 sm:text-sm"
```

**Description:** Same issue as P2-06 but with `cyan-500` — the Water module introduces a brand-new color (`cyan`) for its select focus ring that exists nowhere else in the design system. The `WaterRateBenchmark` uses `bg-green-50` and `bg-red-50` for lowest/highest stats rather than `success-*` and `danger-*`. These two components together effectively invent a micro design system for the Water section.

**Fix:** Use `focus:border-primary-500 focus:ring-primary-500`. For the benchmark cards, use `success-50/success-700` and `danger-50/danger-700` tokens.

---

## P3 — Low

### P3-01: Duplicate inline primary button styling alongside `<Button>` component — two components write raw `<button>` with the same Tailwind classes as `Button variant="primary"`

**Files:**
- `frontend/components/auth/LoginForm.tsx` lines 232–244: raw `<button className="w-full bg-primary-600 text-white py-2.5 px-4 rounded-lg hover:bg-primary-700 ...">` instead of `<Button variant="primary" className="w-full">`
- `frontend/components/dashboard/DashboardContent.tsx` line 173: raw `<button className="mt-4 inline-flex items-center rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 transition-colors">` instead of `<Button variant="primary" size="sm">`
- `frontend/components/alerts/AlertForm.tsx` line 172: raw `<button className="inline-flex items-center rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50 transition-colors">` instead of `<Button variant="primary" size="sm">`

**Description:** These three raw buttons nearly exactly duplicate the styles generated by `variantStyles.primary + sizeStyles.md` in `button.tsx`. They also independently implement `disabled:cursor-not-allowed disabled:opacity-50` (which `Button` handles via the `disabled` prop), and `LoginForm` re-implements its own inline spinner SVG when `Button` already handles `loading` state. This is 3x maintenance surface.

**Fix:** Replace with `<Button>` component. For LoginForm, pass `loading={isLoading}`:
```tsx
<Button
  type="submit"
  variant="primary"
  className="w-full"
  loading={isLoading}
>
  {showMagicLink ? 'Send magic link' : 'Sign in'}
</Button>
```

---

### P3-02: `PriceLineChart` Recharts inline tooltip `style` object defined at module scope — does not respond to design system changes

**File:** `frontend/components/charts/PriceLineChart.tsx` lines 24–29

```tsx
const tooltipStyle = {
  backgroundColor: 'white',
  border: '1px solid #e5e7eb',
  borderRadius: '8px',
  boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
}
```

**Description:** Already called out in P1-05 for hardcoded hex values. Additionally flagged here (P3) because this is a mixed CSS-in-JS vs. Tailwind approach concern. Recharts requires style objects for `contentStyle`, but the values use raw literals rather than CSS custom properties. The `globals.css` already defines `--shadow-md` and `--color-border` tokens that match exactly. Using `var()` references here would keep the chart synchronized with the design system at zero runtime cost.

**Fix:** See P1-05 fix.

---

### P3-03: Progress bar `width` dynamic styles are correct (`style={{ width: X% }}`) but lack `will-change: transform` for smoother animation

**Files:**
- `frontend/components/gamification/SavingsTracker.tsx` line 103: `style={{ width: \`${Math.min(...)}\` }}`  + `transition-all duration-500`
- `frontend/components/dashboard/CombinedSavingsCard.tsx` line 55: `style={{ width: \`${pct}%\` }}`
- `frontend/components/dashboard/SetupChecklist.tsx` line 99: `style={{ width: \`${(completedCount / items.length) * 100}%\` }}`
- `frontend/components/connections/BillUploadProgress.tsx` line 27: `style={{ width: \`${uploadProgress}%\` }}`
- `frontend/components/suppliers/SwitchWizard.tsx` line 97: `style={{ width: \`${(step / 4) * 100}%\` }}`

**Description:** These progress bars animate `width` — a layout property. Animating `width` triggers layout and paint on every frame. The correct pattern for a progress bar is to animate `transform: scaleX()` on a full-width inner div with `transform-origin: left`, which is GPU-composited and does not trigger layout. The `transition-all duration-500` class on SavingsTracker will also transition every CSS property (including `width`) rather than just the intended one, which is wasteful.

**Fix for SavingsTracker (applies to all):**
```tsx
{/* Outer container: overflow-hidden, full width */}
<div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
  {/* Inner: full width, use scaleX transform instead of width */}
  <div
    className="h-full origin-left rounded-full bg-success-500 transition-transform duration-500"
    style={{ transform: `scaleX(${Math.min(monthlySavings / 50, 1)})` }}
  />
</div>
```

This is P3 because the current `width` animation works — it is a performance improvement, not a correctness fix.

---

### P3-04: `SavingsTracker` uses `text-yellow-*` and `text-purple-*` for streak levels — these are not in the design token set

**File:** `frontend/components/gamification/SavingsTracker.tsx` lines 37–39

```tsx
const streakColors = {
  bronze: 'text-amber-600 bg-amber-50 border-amber-200',
  silver: 'text-gray-500 bg-gray-50 border-gray-200',
  gold: 'text-yellow-600 bg-yellow-50 border-yellow-200',
  legendary: 'text-purple-600 bg-purple-50 border-purple-200',
}
```

**Description:** `yellow-*` and `purple-*` have no entries in `tailwind.config.ts`. They are Tailwind's default color palette colors, so they will be generated by Tailwind (since `theme.extend` is used, defaults are preserved). However, the project design system explicitly defines `warning-*` (which IS amber/yellow-based) and has no `purple` token. Using `text-yellow-600` instead of `text-warning-600` is inconsistent, and `purple-*` is completely outside the system.

This is a gamification easter-egg feature so the intentional use of special colors makes some sense. The P3 recommendation is to either add `gamification` tokens to `tailwind.config.ts` or document these as intentional overrides.

**Fix (optional):** Add to `tailwind.config.ts`:
```ts
colors: {
  // ... existing
  gamification: {
    gold: '#ca8a04',     // yellow-600
    legendary: '#9333ea', // purple-600
  }
}
```

---

### P3-05: `globals.css` scrollbar styles use hardcoded hex values instead of CSS custom properties

**File:** `frontend/app/globals.css` lines 106, 110, 115

```css
::-webkit-scrollbar-track { background: #f1f5f9; }     /* slate-100 */
::-webkit-scrollbar-thumb { background: #cbd5e1; ... }  /* slate-300 */
::-webkit-scrollbar-thumb:hover { background: #94a3b8; } /* slate-400 */
```

**Description:** The `:root` block defines `--color-surface-secondary: 249 250 251` (gray-50) and `--color-border: 229 231 235` (gray-200), but the scrollbar styles use slate-100/300/400 hardcoded hex values that don't align with any defined token. These are effectively orphaned values.

**Fix:**
```css
::-webkit-scrollbar-track  { background: rgb(var(--color-surface-secondary)); }
::-webkit-scrollbar-thumb  { background: rgb(var(--color-border)); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgb(var(--color-border-hover)); }
```

---

### P3-06: `globals.css` `fadeIn` keyframe has a stray `transform` in its `to` state

**File:** `frontend/app/globals.css` lines 136–143

```css
@keyframes fadeIn {
  from { opacity: 0; }
  to {
    opacity: 1;
    transform: translateY(0);   /* <-- this should not be here */
  }
}
```

**Description:** A pure fade-in animation should only animate `opacity`. The `transform: translateY(0)` in the `to` state means any element currently being transformed (e.g., a child of a sliding container) will have its transform forcibly reset to `translateY(0)` at the end of the fade, potentially fighting with other transitions. The `tailwind.config.ts` version of `fadeIn` (lines 102–104) correctly only animates `opacity`:
```ts
fadeIn: {
  from: { opacity: '0' },
  to: { opacity: '1' },
},
```

This is another consequence of the duplicate keyframe issue flagged in P1-03. Resolving P1-03 removes this bug automatically.

**Fix:** Remove the stale `globals.css` keyframe (see P1-03 fix).

---

### P3-07: No print styles defined anywhere

**Files:** `frontend/app/globals.css` (entire file), no `@media print` rules in any component

**Description:** The app generates savings reports (`OptimizationReport.tsx`), data exports (`DataExport.tsx`), and tabular price comparisons (`ComparisonTable.tsx`, `AlertsContent.tsx`) that users may print. There are zero `@media print` rules. Common issues that would occur when printing:
- The fixed sidebar (`position: fixed`) will overlap the content area
- Background colors/gradients are stripped by default in print (progress bars, badges, the live indicator become invisible)
- The `h-screen` layout containers will overflow the print page

This is P3 because it is not a functional correctness issue for the primary web experience, but it degrades a use case that is likely (printing a cost comparison report).

**Fix — add to `globals.css`:**
```css
@media print {
  /* Hide non-content chrome */
  aside, nav, [data-testid="realtime-indicator"],
  button:not([type="submit"]) { display: none !important; }

  /* Restore layout for print */
  main { padding-left: 0 !important; }
  .flex.min-h-screen { display: block; }

  /* Force print-safe backgrounds on semantic color elements */
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
```

---

## Appendix: Design System Consistency Matrix

| Token category | Config defined | Used correctly | Raw overrides found |
|----------------|---------------|---------------|---------------------|
| `primary-*` | Yes (50–900) | Yes (most) | `text-blue-*` in ~15 files |
| `success-*` | Yes (50–900) | Yes (most) | `text-green-*`, `bg-green-*` in ~12 files |
| `warning-*` | Yes (50–900) | Yes (most) | `text-amber-*`, `text-yellow-*` in ~4 files |
| `danger-*` | Yes (50–900) | Yes (most) | `text-red-*`, `bg-red-*` in ~10 files |
| `electricity.*` | Yes (3 values) | Never used | Color values re-inlined manually |
| Scrollbar colors | In CSS vars | No | `#f1f5f9`, `#cbd5e1`, `#94a3b8` hardcoded |
| Chart colors | None | N/A | All hardcoded hex in PriceLineChart |
| `info` state | Not defined | N/A | `blue-*` used ad hoc (~20 occurrences) |

**Recommendation:** Add an `info` semantic color scale to `tailwind.config.ts` (alias of `primary-*` or a distinct blue) to give the `info` state a proper token, and retire all `bg-blue-*`/`text-blue-*` usage in favor of it.
