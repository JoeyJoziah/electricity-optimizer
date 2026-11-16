# 05 - CSS & Styling Audit

> Audit date: 2026-03-18
> Scope: `frontend/app/globals.css`, `frontend/tailwind.config.ts`, `frontend/postcss.config.js`, all component files in `frontend/components/` and `frontend/app/`
> Auditor: Claude Opus 4.6 (read-only)

---

## Summary

The RateShift frontend uses Tailwind CSS v3 with a well-structured design token system (`globals.css` custom properties + `tailwind.config.ts` theme extensions). The codebase demonstrates strong foundations: a `cn()` utility (clsx + tailwind-merge), semantic color palettes, centralized chart tokens, GPU-composited progress bars (`transform: scaleX`), and proper print styles. However, there are several significant findings: **undefined Tailwind classes being used in production code** (P0), **zero dark mode implementation** despite `darkMode: 'class'` being configured (P1), **complete absence of `prefers-reduced-motion` support** (P1), and multiple z-index conflicts where sidebar, modals, dropdowns, and toasts all compete at `z-50`.

**Finding counts**: P0: 3 | P1: 8 | P2: 12 | P3: 7

---

## P0 - Critical (Broken or Incorrect Rendering)

### P0-01: Undefined Tailwind Classes in Production Components

**Files affected**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/RateChangeCard.tsx` (lines 34, 50, 54, 71)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/RateChangeFeed.tsx` (line 36, 79)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/AlertPreferences.tsx` (lines 23, 93)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/seo/RatePageContent.tsx` (lines 49, 67, 74, 75, 78, 80, 106, 122, 125, 141, 162)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/affiliate/FTCDisclosure.tsx` (line 29)

**Issue**: The following Tailwind utility classes are used but **not defined** anywhere in `tailwind.config.ts` or `globals.css`:
- `text-muted-foreground` -- used 15+ times across 4 components
- `bg-muted` -- used 2 times (loading skeletons in AlertPreferences and RateChangeFeed)
- `bg-card` -- used 1 time (RatePageContent line 74)
- `hover:bg-accent` -- used 2 times (RatePageContent lines 141, 162)

These are shadcn/ui naming conventions that were never added to this project's Tailwind configuration. Since Tailwind v3 purges unknown classes, **these classes produce no CSS output** and the affected elements have no background/text color applied at all.

**Impact**: The `text-muted-foreground` issue is particularly severe on the SEO rate pages (`/rates/[state]/[utility]/`) which are public-facing, ISR-rendered pages. All secondary text on these pages has no color applied, falling back to the body `color` (dark gray) instead of the intended muted gray. The `bg-card` on the average price card renders with no background. The `bg-muted` skeleton loaders show no background color (invisible loading states).

**Fix**: Either add the missing color tokens to `tailwind.config.ts`:
```ts
colors: {
  muted: { DEFAULT: '#f1f5f9', foreground: '#64748b' },
  card: { DEFAULT: '#ffffff' },
  accent: { DEFAULT: '#f1f5f9' },
}
```
Or replace all occurrences with the project's existing semantic classes (`text-gray-500`, `bg-gray-100`, `bg-white`, `hover:bg-gray-100`).

---

### P0-02: Tailwind Content Config Missing `lib/` Directory

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/tailwind.config.ts` (lines 5-9)

**Issue**: The Tailwind `content` array scans:
```ts
content: [
  './pages/**/*.{js,ts,jsx,tsx,mdx}',
  './components/**/*.{js,ts,jsx,tsx,mdx}',
  './app/**/*.{js,ts,jsx,tsx,mdx}',
]
```
But `./lib/**/*.{tsx}` is **not included**. The file `frontend/lib/contexts/toast-context.tsx` (line 106) uses Tailwind classes:
```tsx
className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"
```

Because the toast container rendering is in `lib/`, Tailwind's JIT compiler may not detect these class usages. In practice, these specific classes are likely preserved because they also appear in `components/` or `app/` files, but this is fragile -- any future class used exclusively in `lib/` will be silently purged.

**Fix**: Add `'./lib/**/*.{js,ts,jsx,tsx}'` to the `content` array.

---

### P0-03: CombinedSavingsCard and CCAInfo Use `width` Instead of `transform: scaleX` for Progress Bars

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/CombinedSavingsCard.tsx` (line 55)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAInfo.tsx` (line 82)

**Issue**: These components use `style={{ width: '${pct}%' }}` for animated/dynamic bar segments. This triggers **layout recalculation** (reflow) on every frame if animated, and causes **CLS** when the data loads and the bar renders from zero to its final width.

The project's own established pattern (documented in CLAUDE.md: "Progress bar GPU compositing: use `transform:scaleX()` + `origin-left` instead of `width` transitions") is followed correctly in `SavingsTracker.tsx`, `BillUploadProgress.tsx`, `NeighborhoodCard.tsx`, `SetupChecklist.tsx`, and `SwitchWizard.tsx` -- but these two components violate it.

**Impact**: On the dashboard, `CombinedSavingsCard` renders a stacked bar where segment widths change from 0 to their computed percentages when data loads. Without `contain: layout` or a reserved height, this contributes to CLS. On CCA pages, the generation mix bar has the same issue.

**Fix**: Replace `style={{ width: '${pct}%' }}` with `style={{ transform: 'scaleX(${pct/100})' }}` and add `origin-left` class to each bar segment, matching the project's own established pattern.

---

## P1 - High (Significant UX/Maintainability Issues)

### P1-01: Zero Dark Mode Implementation

**Files**: Every component file in `frontend/components/` and `frontend/app/`

**Issue**: `tailwind.config.ts` configures `darkMode: 'class'` (line 4), and `globals.css` has a comment acknowledging this (lines 5-11: "Force light color scheme until dark mode UI is fully implemented"). However, a grep for `dark:` across all `.tsx` and `.css` files returns **zero matches** (only comments in `globals.css`). Not a single component uses a `dark:` prefix.

**Impact**: This means:
1. Users with OS-level dark mode preferences see a light-only interface
2. The CSS custom property system in `:root` has no `.dark` counterpart
3. The chart tokens (`--chart-grid`, `--chart-tooltip-bg`, etc.) are hardcoded to light values with no dark variants
4. If a `dark` class is ever added to `<html>`, background and text colors will become unreadable because there are no `dark:` overrides

**Recommendation**: This is documented as intentional ("force light until dark mode UI is built"), but it should be escalated because:
- The `color-scheme: light` directive in `:root` forces light scrollbars, which is correct
- But no `@media (prefers-color-scheme: dark)` meta tag or `<meta name="color-scheme">` prevents the browser from applying its own dark mode heuristics on some mobile browsers

### P1-02: No `prefers-reduced-motion` Support Anywhere

**Files**: All animation usage across `globals.css` and components

**Issue**: A search for both `prefers-reduced-motion` (CSS media query) and `motion-reduce`/`motion-safe` (Tailwind utilities) returns **zero results** across the entire frontend codebase.

The codebase uses animations extensively:
- `animate-spin` (loading spinners): 10+ usages
- `animate-bounce` (chat typing indicator): `AgentChat.tsx` line 166-168
- `animate-pulse` (skeleton loaders): 20+ usages
- `animate-ping` (realtime indicator): `Header.tsx` line 57
- `animate-shimmer` (skeleton shimmer): `globals.css` line 174
- Custom `slideDown`, `slideUp`, `fadeIn`, `scaleIn` animations
- `transition-colors`, `transition-all`, `transition-transform`, `transition-opacity`: 50+ usages

**Impact**: Users who have enabled "Reduce motion" in their OS accessibility settings still see all animations, including:
- Continuous `animate-ping` pulsing dot in the header (vestibular trigger)
- Bouncing dots in the AI chat typing indicator
- Shimmer effects on skeleton loaders

This is a **WCAG 2.1 Level AA violation** (Success Criterion 2.3.3 - Animation from Interactions).

**Fix**: At minimum, add to `globals.css`:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```
Or use Tailwind's `motion-reduce:` and `motion-safe:` utilities on individual elements.

### P1-03: Z-Index Layer Collision -- Everything is z-50

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/Sidebar.tsx` (lines 184, 190, 199) -- desktop sidebar: `z-50`, mobile overlay: `z-50`, mobile panel: `z-50`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/modal.tsx` (line 87) -- `z-50`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/feedback/FeedbackWidget.tsx` (line 109) -- modal: `z-50`, FAB: `z-40`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/contexts/toast-context.tsx` (line 106) -- `z-50`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/NotificationBell.tsx` (line 114) -- dropdown: `z-50`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/suppliers/SupplierSelector.tsx` (line 67) -- dropdown: `z-50`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/suppliers/SuppliersContent.tsx` (lines 350, 366) -- inline modals: `z-50`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/pwa/InstallPrompt.tsx` (line 62) -- install banner: `z-50`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/Header.tsx` (line 34) -- sticky header: `z-40`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (line 180) -- `.recharts-tooltip-wrapper`: `z-index: 100 !important`

**Issue**: Eight distinct UI layers all share `z-50`. The stacking order between simultaneous elements (e.g., a modal opened while sidebar is visible, or a toast appearing over a modal) depends on DOM order rather than intentional layering.

**Specific conflict scenarios**:
1. **Toast over Modal**: Both at `z-50`. The toast container is in the root layout (DOM order: after all modals). This works by accident, but if toast rendering order changes, toasts could appear behind modals.
2. **NotificationBell dropdown vs Sidebar**: Both `z-50`. On desktop, the notification dropdown opens from the header (`z-40`) but claims `z-50`, visually appearing above the sidebar which is also `z-50`.
3. **Recharts tooltip at z-100**: Uses `!important` in `globals.css` (line 180), which will appear above everything including modals if a chart is behind an overlay.
4. **PWA Install Prompt vs Feedback FAB**: Install prompt is `z-50`, feedback FAB is `z-40`. If both are visible, install prompt correctly appears above, but if a feedback modal (`z-50`) is open, the install prompt can overlap it.

**Fix**: Establish a z-index scale:
```
z-10: tooltips, popovers (chart tooltips, notification dropdown)
z-20: dropdowns (SupplierSelector)
z-30: sticky header
z-40: sidebar (desktop)
z-50: overlay backdrops
z-60: modal/dialog panels
z-70: toasts
z-80: skip-to-content link
```

### P1-04: Landing Page Uses `blue-600` Instead of `primary-600` (Design Token Bypass)

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/page.tsx`

**Issue**: The landing page uses raw Tailwind `blue-600` / `blue-700` classes instead of the project's custom `primary-600` / `primary-700` tokens. Occurrences:
- Line 91: `text-blue-600` (logo icon)
- Line 103: `bg-blue-600 ... hover:bg-blue-700` (Get Started button)
- Line 116: `text-blue-600` (hero accent text)
- Line 125: `bg-blue-600 ... hover:bg-blue-700` (hero CTA)
- Line 153: `text-blue-600` (feature icons)
- Line 176-178: `border-blue-600 ring-2 ring-blue-600` (pricing card highlight)
- Line 190: `text-blue-600` (checkmarks)
- Line 199: `bg-blue-600 ... hover:bg-blue-700` (pricing CTA)
- Line 216: `text-blue-600` (footer icon)

While `primary-500` happens to be `#3b82f6` (which is `blue-500`), and `primary-600` is `#2563eb` (which is `blue-600`), these are **not the same values**. The project's `primary-600` is `#2563eb`, but raw `blue-600` in Tailwind is also `#2563eb`. In this specific case the values happen to align because the project reuses Tailwind's blue palette, but using raw color names means the landing page will not update if the primary color is changed.

**Additional occurrences of `blue-*` bypass**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAInfo.tsx` (line 106): `text-blue-700 hover:text-blue-900`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/seo/RatePageContent.tsx` (lines 171-180): `bg-blue-50`, `text-blue-900`, `text-blue-700`, `bg-blue-600`, `hover:bg-blue-700`

### P1-05: Mobile Sidebar Has No Slide-In Animation or Backdrop Transition

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/Sidebar.tsx` (lines 189-212)

**Issue**: The mobile sidebar renders conditionally (`{isOpen && (...)}`). When it appears, there is no entry/exit animation -- it pops in and out instantly. The backdrop has `transition-opacity` (line 193) but since the entire block mounts/unmounts with the `isOpen` conditional, the transition never plays (element goes from not-in-DOM to in-DOM, skipping the CSS transition).

**Impact**: Jarring UX on mobile. Users see an instant overlay/panel appearance with no visual cue of where the sidebar came from. All modern app sidebars use slide-in transitions.

**Fix**: Use CSS transforms and conditional class toggling instead of conditional rendering, or use a transition library (Headless UI `Transition`, Framer Motion `AnimatePresence`).

### P1-06: SuppliersContent Inline Modals Lack Focus Trap and Escape Key Handling

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/suppliers/SuppliersContent.tsx` (lines 349-378)

**Issue**: Two inline modal implementations use raw `<div>` elements with `role="dialog"` and `aria-modal="true"`, but unlike the `Modal` component in `ui/modal.tsx` and `FeedbackWidget.tsx`, they:
1. Have no focus trap (Tab can escape the modal to background content)
2. Have no Escape key handler to close
3. Have no backdrop click handler (clicking the `bg-black/50` overlay does nothing)
4. Have no stored-focus restoration on close

The reusable `Modal` component in `ui/modal.tsx` correctly implements all four of these. These inline implementations appear to have been written independently.

### P1-07: Font Family `JetBrains Mono` Declared But Never Loaded

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/tailwind.config.ts` (line 69)

**Issue**: The config declares `mono: ['JetBrains Mono', 'monospace']` but:
1. `JetBrains Mono` is not imported via `next/font/google` in `layout.tsx`
2. It is not loaded via a `<link>` tag or `@import`
3. The only usage of `font-mono` is in `settings/page.tsx` line 411 for masked account numbers

**Impact**: The `font-mono` class resolves to `JetBrains Mono, monospace`, but since the font file is never loaded, the browser falls back to the system monospace font. This is misleading in the config -- it suggests JetBrains Mono is part of the design system when it is not actually available.

### P1-08: Scrollbar Styles Are WebKit-Only

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (lines 114-131)

**Issue**: The custom scrollbar styles use `::-webkit-scrollbar` pseudo-elements which only work in Chromium-based browsers and Safari. Firefox is not covered.

Firefox supports `scrollbar-width` and `scrollbar-color` properties (standardized). The `scrollbar-hide` utility (line 137) correctly uses `scrollbar-width: none` for Firefox, but the visible scrollbar customization does not.

**Fix**: Add standardized scrollbar properties alongside the WebKit prefixed ones:
```css
* {
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 #f1f5f9;
}
```

---

## P2 - Medium (Potential Issues, Inconsistencies)

### P2-01: Duplicate CSS Custom Properties and Tailwind Theme for Same Values

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (lines 14-90)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/tailwind.config.ts` (lines 12-65)

**Issue**: The design system defines colors in two parallel systems:
1. CSS custom properties in `:root` (e.g., `--color-primary: 59 130 246`)
2. Tailwind theme `colors` object (e.g., `primary-500: '#3b82f6'`)

But the CSS custom properties are **not consumed by the Tailwind theme**. The Tailwind colors are hardcoded hex values. This means:
- Changing `--color-primary` in `:root` has no effect on any Tailwind `primary-*` classes
- The CSS custom properties are only used in `body { color: rgb(var(--color-foreground)) }` and the base `input` styles
- Two sources of truth exist that could diverge

The `--color-primary` value `59 130 246` corresponds to `rgb(59, 130, 246)` = `#3b82f6` = `blue-500`, but `primary.500` in the Tailwind config is `'#3b82f6'`. If someone changes one, they must manually update the other.

### P2-02: Hardcoded Hex Colors in SVG Paths (Google OAuth Icon)

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/auth/LoginForm.tsx` (lines 160-163)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/auth/SignupForm.tsx` (lines 179-182)

**Issue**: Google's brand colors (`#4285F4`, `#34A853`, `#FBBC05`, `#EA4335`) are hardcoded in inline SVG paths. While these are Google's official brand colors and should not change with the app's theme, they are duplicated across two files.

**Recommendation**: Extract the Google SVG icon into a shared component (low priority -- brand colors are inherently hardcoded).

### P2-03: Inconsistent Progress Bar Techniques

**Files**:
- `CombinedSavingsCard.tsx` (line 55): `style={{ width: '${pct}%' }}`
- `CCAInfo.tsx` (line 82): `style={{ width: '${pct}%' }}`
- `SavingsTracker.tsx` (line 102): `style={{ transform: scaleX(...) }}`
- `BillUploadProgress.tsx` (line 27): `style={{ transform: scaleX(...) }}`
- `NeighborhoodCard.tsx` (line 64): `style={{ transform: scaleX(...) }}`
- `SetupChecklist.tsx` (line 101): `style={{ transform: scaleX(...) }}`
- `SwitchWizard.tsx` (line 97): `style={{ transform: scaleX(...) }}`

**Issue**: Two different techniques are used for progress bars. The project has an explicit pattern note in CLAUDE.md preferring `transform: scaleX()` for GPU compositing. Two components (`CombinedSavingsCard`, `CCAInfo`) deviate from the standard.

### P2-04: Inline Modal Implementations vs Reusable Modal Component

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/modal.tsx` -- reusable Modal component with proper a11y
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/suppliers/SuppliersContent.tsx` (lines 349-378) -- inline modal divs
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/feedback/FeedbackWidget.tsx` (lines 104-267) -- custom modal with its own focus trap

**Issue**: Three different modal implementations exist:
1. `ui/modal.tsx`: Proper focus trap, Escape handler, backdrop click, focus restoration
2. `SuppliersContent.tsx`: Bare `div` with no interactivity (see P1-06)
3. `FeedbackWidget.tsx`: Custom implementation with its own focus trap

This creates inconsistency and increases maintenance burden. The `FeedbackWidget` modal could use the shared `Modal` component.

### P2-05: Template Literal Class Names Instead of `cn()` Utility

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/agent/AgentChat.tsx` (lines 20, 27, 208)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/community/VoteButton.tsx` (line 48)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/AlertPreferences.tsx` (line 63)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAInfo.tsx` (line 57)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/seo/RatePageContent.tsx` (line 175)

**Issue**: Several components use template literal string interpolation for conditional classes instead of the `cn()` utility:
```tsx
className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${
  isUser ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-900'
}`}
```

The `cn()` utility (clsx + tailwind-merge) handles class conflicts and deduplication. Template literals can produce conflicting classes that tailwind-merge would otherwise resolve.

### P2-06: Non-Responsive Grid Layouts on Small Screens

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/analytics/OptimizationReport.tsx` (line 58): `grid-cols-3` with no responsive prefix
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/gamification/SavingsTracker.tsx` (line 44): `grid-cols-3 gap-3` with no responsive prefix
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/community-solar/SavingsCalculator.tsx` (line 97): `grid-cols-3` with no responsive prefix
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/suppliers/SwitchWizard.tsx` (line 113): `grid-cols-2` with no responsive prefix
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAComparison.tsx` (line 26): `grid-cols-2` with no responsive prefix

**Issue**: These grids use `grid-cols-2` or `grid-cols-3` without a mobile-first approach (`grid-cols-1 sm:grid-cols-2`). On a 320px-wide phone screen, a 3-column grid produces columns approximately 93px wide, which is too narrow for text content. The `SavingsTracker` 3-column grid containing currency values may truncate or overflow.

### P2-07: CSS Custom Properties Use Space-Separated RGB But Chart Tokens Use Hex

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (lines 14-90)

**Issue**: The design system uses two incompatible color formats:
- Surface/semantic colors: space-separated RGB values (`--color-primary: 59 130 246`) for use with `rgb(var(--color-primary) / opacity)`
- Chart colors: hex values (`--chart-1: #3b82f6`)
- Shadow tokens: full `rgb()` expressions

This is intentional (chart colors are consumed by Recharts which expects hex/color strings, not RGB channels), but it creates confusion and means chart colors cannot use the Tailwind opacity modifier syntax.

### P2-08: Button Component Lacks Explicit `type="button"` Default

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/button.tsx`

**Issue**: The Button component does not set a default `type` attribute. In HTML, a `<button>` inside a `<form>` defaults to `type="submit"`. Any `Button` without an explicit `type` prop that happens to be inside a form will submit the form when clicked.

Multiple components use `Button` without `type`:
- `SuppliersContent.tsx`: "Select Supplier" button inside a card (not in a form, safe)
- `DashboardCharts.tsx`: "View all prices" button wrapped in a Link (safe)
- But any future usage inside a form without `type="button"` would cause unintended submission.

### P2-09: No CSS `contain` Property on Chart Containers

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/charts/PriceLineChart.tsx` (line 221)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/charts/ForecastChart.tsx` (line 121)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/charts/SavingsDonut.tsx` (line 78)

**Issue**: Chart containers use `style={{ height }}` (set by prop) but do not use CSS `contain: layout size` or `content-visibility: auto`. Recharts' `ResponsiveContainer` recalculates on resize, and without containment, these recalculations can trigger layout thrashing on sibling elements.

The `DashboardContent.tsx` correctly uses `contain: layout` on the price alert banner (line 191), showing the pattern is known, but charts do not apply it.

### P2-10: Skeleton Components Use `animate-pulse` (bg-gray-200) But Custom `.skeleton` Class Exists

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/skeleton.tsx` (line 24): uses `animate-pulse bg-gray-200`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (lines 184-194): defines `.skeleton` class with shimmer gradient

**Issue**: Two skeleton animation systems exist:
1. The `Skeleton` component uses Tailwind's built-in `animate-pulse` (simple opacity fade)
2. The `.skeleton` CSS class in `globals.css` uses the `shimmer` keyframe with a gradient sweep (more visually polished)

The `animate-shimmer` class is also defined in both `globals.css` (line 173) and `tailwind.config.ts` (line 84). However, the `Skeleton` component does not use either of them -- it uses `animate-pulse` which is a different, simpler animation.

### P2-11: Print Styles Hide All Buttons Including Submit/Action Buttons

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (line 209)

**Issue**: The print styles include `button, [role="button"]` in the hide list (`display: none !important`). This hides ALL buttons, including any that might contain important text content (e.g., a "Current Plan: Pro" button badge). While hiding interactive elements in print is generally correct, the selector is overly broad.

### P2-12: Card Component Default Variant `bordered` Has No Shadow

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/card.tsx` (lines 11-15)

**Issue**: The Card component has three variants: `default` (bg-white only), `bordered` (bg-white + border), and `elevated` (bg-white + shadow-lg). The default variant is `bordered`, which means all Cards get a 1px gray border but no shadow. The `shadow-card` custom shadow defined in `tailwind.config.ts` (line 72) is never used by the Card component -- it is only referenced by `FeedbackWidget.tsx` (`shadow-card` class). This custom shadow goes unused in the Card component itself, which is its most natural home.

---

## P3 - Low (Cosmetic, Optimization Opportunities)

### P3-01: Color Contrast -- `text-gray-400` on White Background

**Files**: 30+ occurrences across components (see P1 grep results)

**Issue**: `text-gray-400` (`#9ca3af`) on a white background (`#ffffff`) has a contrast ratio of approximately 2.9:1, which fails WCAG AA for normal text (requires 4.5:1) and barely passes for large text (requires 3:1). While many of these are decorative icons (which are exempt), several are text content:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/Sidebar.tsx` (line 154): version text `text-[10px] text-gray-300` -- contrast ratio ~2.0:1
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/NeighborhoodCard.tsx` (line 34): informational text
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/community/PostForm.tsx` (line 219): consent text

The version label on line 154 uses `text-gray-300` (#d1d5db) which has a contrast ratio of approximately 1.6:1, well below any threshold.

### P3-02: `transition-all` Used Broadly (Performance)

**Files**: Multiple components use `transition-all duration-200`:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/input.tsx` (line 50)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/PortalConnectionFlow.tsx` (line 309)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/auth/LoginForm.tsx` (line 157, 174, 235)

**Issue**: `transition-all` transitions every CSS property that changes, including `box-shadow`, `border-color`, `background-color`, `color`, and potentially layout properties. While modern browsers handle this efficiently, it is best practice to specify only the properties that actually change (e.g., `transition-colors` for hover states, `transition-shadow` for focus states) to reduce the compositor workload.

### P3-03: Recharts Tooltip `z-index: 100 !important` Override

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (line 180)

**Issue**: The Recharts tooltip wrapper is forced to `z-index: 100 !important`. This is necessary because Recharts generates inline styles, but 100 is higher than any other z-index in the system (everything else is z-50 max). If a chart is visible behind a modal overlay, the tooltip could poke through the overlay.

### P3-04: PostCSS Config Has No cssnano or Other Optimizations

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/postcss.config.js`

**Issue**: The PostCSS config only includes `tailwindcss` and `autoprefixer`. For production builds, Next.js handles CSS minification internally, so `cssnano` is not strictly needed. However, the config does not include any additional PostCSS plugins for:
- `postcss-preset-env` (modern CSS features polyfilling)
- `postcss-sort-media-queries` (deduplicating media queries)

This is acceptable as Next.js handles most of this, but noted for completeness.

### P3-05: `pages/` Directory in Tailwind Content Config But No `pages/` Directory Exists

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/tailwind.config.ts` (line 6)

**Issue**: The content array includes `'./pages/**/*.{js,ts,jsx,tsx,mdx}'` but this project uses Next.js App Router exclusively (the `app/` directory). There is no `pages/` directory. This entry is harmless (glob matches nothing) but is dead config from a Pages Router setup.

### P3-06: CSS Custom Properties for Spacing and Border Radius Are Defined But Not Used via Tailwind

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (lines 54-65)

**Issue**: Custom properties are defined for spacing (`--space-xs` through `--space-xl`) and border radius (`--radius-sm` through `--radius-xl`), but:
- They are not mapped to Tailwind's `spacing` or `borderRadius` theme config
- Components use Tailwind's built-in spacing (`p-4`, `gap-6`) and radius (`rounded-lg`, `rounded-xl`) utilities directly
- The only place these might be consumed is the `.skeleton` class (`border-radius: var(--radius-md)`)

These CSS custom properties are effectively dead code, creating false expectations about a design token system that is not actually wired up.

### P3-07: `text-emerald-700` Used Instead of `text-success-700` in PriceLineChart

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/charts/PriceLineChart.tsx` (line 161)

**Issue**: The trend color for "decreasing" uses `text-emerald-700` instead of `text-success-700`. The comment says "Use darker success color (text-success-700 / emerald-700) for WCAG AA contrast compliance", but the project's `success-700` is `#15803d` (the same as Tailwind's `green-700`, not `emerald-700` which is `#047857`). While both have adequate contrast, using `emerald-700` bypasses the project's design token system.

---

## Design System Health Summary

| Category | Status | Notes |
|---|---|---|
| Color tokens | Mixed | CSS vars defined but not wired to Tailwind; chart tokens well-organized in separate module |
| Typography | Good | Inter loaded via `next/font`, consistent `text-sm`/`text-lg` scale |
| Spacing | Unused | CSS var spacing tokens defined but never consumed; Tailwind defaults used everywhere |
| Component library | Good | `ui/` directory with Button, Card, Input, Modal, Badge, Skeleton, Toast |
| Dark mode | Not implemented | Config present, zero usage |
| Responsive design | Good with gaps | Most grids are responsive; 5 components have non-responsive multi-column grids |
| Animations | Good performance | GPU-composited transforms used; but no reduced-motion support |
| Accessibility | Mixed | Good: focus-visible rings, ARIA attributes, focus traps in modals. Bad: no motion reduction, color contrast issues, some modals lack traps |
| Print styles | Good | Well-structured print CSS with ink savings |
| Bundle size | Good | Dynamic imports for charts, proper tree-shaking setup |

---

## Files Reviewed

| File | Lines | Key Issues |
|---|---|---|
| `frontend/app/globals.css` | 261 | P1-02, P1-08, P2-01, P2-07, P2-10, P2-11, P3-03, P3-06 |
| `frontend/tailwind.config.ts` | 124 | P0-02, P1-07, P2-01, P3-05 |
| `frontend/postcss.config.js` | 7 | P3-04 |
| `frontend/components/ui/button.tsx` | 76 | P2-08 |
| `frontend/components/ui/card.tsx` | 132 | P2-12 |
| `frontend/components/ui/input.tsx` | 137 | P3-02 |
| `frontend/components/ui/modal.tsx` | 135 | P1-03 (z-index) |
| `frontend/components/ui/toast.tsx` | 72 | Clean |
| `frontend/components/ui/badge.tsx` | 44 | Clean |
| `frontend/components/ui/skeleton.tsx` | 71 | P2-10 |
| `frontend/components/layout/Sidebar.tsx` | 216 | P1-03, P1-05, P3-01 |
| `frontend/components/layout/Header.tsx` | 85 | P1-03 |
| `frontend/components/layout/NotificationBell.tsx` | 160 | P1-03 |
| `frontend/components/feedback/FeedbackWidget.tsx` | 305 | P1-03, P2-04 |
| `frontend/components/dashboard/DashboardContent.tsx` | 250 | Clean (good CLS prevention) |
| `frontend/components/dashboard/DashboardStatsRow.tsx` | 142 | Clean |
| `frontend/components/dashboard/DashboardCharts.tsx` | 103 | Clean |
| `frontend/components/dashboard/CombinedSavingsCard.tsx` | 81 | P0-03 |
| `frontend/components/dashboard/NeighborhoodCard.tsx` | 96 | Clean (uses scaleX correctly) |
| `frontend/components/dashboard/CompletionProgress.tsx` | 62 | Clean |
| `frontend/components/charts/PriceLineChart.tsx` | 301 | P3-07, P2-09 |
| `frontend/components/charts/ForecastChart.tsx` | 231 | P2-09 |
| `frontend/components/charts/SavingsDonut.tsx` | 142 | P2-09 |
| `frontend/components/charts/ScheduleTimeline.tsx` | 281 | Clean |
| `frontend/components/agent/AgentChat.tsx` | 237 | P2-05, P1-04 (minor) |
| `frontend/components/suppliers/SuppliersContent.tsx` | 384 | P1-03, P1-06, P2-04 |
| `frontend/components/suppliers/ComparisonTable.tsx` | 281 | Clean (good responsive table) |
| `frontend/components/suppliers/SwitchWizard.tsx` | 120+ | P2-06 |
| `frontend/components/connections/ConnectionMethodPicker.tsx` | 109 | Clean (good responsive) |
| `frontend/components/connections/PortalConnectionFlow.tsx` | 430 | P3-02 |
| `frontend/components/connections/BillUploadDropZone.tsx` | 92 | Clean |
| `frontend/components/connections/BillUploadProgress.tsx` | 67 | Clean (uses scaleX) |
| `frontend/components/gamification/SavingsTracker.tsx` | 111 | P2-06 (grid-cols-3) |
| `frontend/components/rate-changes/RateChangeCard.tsx` | 77 | P0-01 |
| `frontend/components/rate-changes/RateChangeFeed.tsx` | ~80 | P0-01 |
| `frontend/components/rate-changes/AlertPreferences.tsx` | ~93 | P0-01 |
| `frontend/components/seo/RatePageContent.tsx` | 188 | P0-01, P1-04 |
| `frontend/components/cca/CCAInfo.tsx` | 126 | P0-03, P1-04 |
| `frontend/components/auth/LoginForm.tsx` | 269 | P2-02, P3-02 |
| `frontend/components/auth/SignupForm.tsx` | ~200 | P2-02 |
| `frontend/app/page.tsx` | 233 | P1-04 |
| `frontend/app/layout.tsx` | 63 | Clean |
| `frontend/app/(app)/layout.tsx` | 32 | Clean (good skip-to-content) |
| `frontend/app/not-found.tsx` | 20 | Clean |
| `frontend/lib/utils/cn.ts` | 11 | Clean (proper clsx + tw-merge) |
| `frontend/lib/constants/chartTokens.ts` | 67 | Clean (good token centralization) |
| `frontend/lib/contexts/toast-context.tsx` | ~120 | P0-02 |
