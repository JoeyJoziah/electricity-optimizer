# Audit Report: CSS & Styling
**Date:** 2026-03-23
**Scope:** Tailwind config, global styles, design system, component styling patterns
**Files Reviewed:**
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/tailwind.config.ts`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/constants/chartTokens.ts`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/utils/cn.ts`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/layout.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/layout.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/button.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/card.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/modal.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/input.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/badge.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/toast.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/skeleton.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/Sidebar.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/Header.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/charts/PriceLineChart.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/charts/SavingsDonut.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/charts/ForecastChart.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/charts/ScheduleTimeline.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/DashboardStatsRow.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/DashboardCharts.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/CombinedSavingsCard.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/UtilityDiscoveryCard.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/SetupChecklist.tsx` (via inline style search)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/NeighborhoodCard.tsx` (via inline style search)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/alerts/AlertForm.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/agent/AgentChat.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/ConnectionMethodPicker.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/EmailConnectionFlow.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/pwa/InstallPrompt.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/gamification/SavingsTracker.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAAlert.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/cca/CCAInfo.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/seo/RatePageContent.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/error-boundary.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/auth/LoginForm.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/auth/SignupForm.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/feedback/FeedbackWidget.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/community/PostForm.tsx`

Additionally performed project-wide `grep` searches across all `*.tsx` and `*.css` files for: `!important`, `z-index` classes, `prefers-reduced-motion`, hardcoded hex colors, `dark:` prefixes, `style={`, `bg-blue-`/`text-blue-`/`bg-red-`/etc. raw Tailwind palette usage, `text-[`/`bg-[`/`border-[` arbitrary values, `text-muted-foreground`/`bg-card`/`hover:bg-accent` undefined tokens, and focus ring patterns.

---

## P0 -- Critical (Fix Immediately)

### P0-1: Undefined Tailwind Color Tokens (`bg-card`, `hover:bg-accent`, `text-muted-foreground`)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/seo/RatePageContent.tsx`
**Lines:** 49, 67, 74, 75, 78, 80, 106, 122, 125, 141, 162

**Also:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/RateChangeCard.tsx` (lines 34, 50, 54, 71), `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/RateChangeFeed.tsx` (line 79), `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/rate-changes/AlertPreferences.tsx` (line 93), `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/affiliate/FTCDisclosure.tsx` (line 29)

The classes `text-muted-foreground`, `bg-card`, and `hover:bg-accent` are used in 5+ components but **none of these are defined in `tailwind.config.ts`** as color tokens. `muted` IS defined with `DEFAULT` and `foreground`, so `text-muted-foreground` resolves correctly. However:

- **`bg-card`**: Only `card` exists as a `boxShadow` entry (line 78 of config), NOT as a color. `bg-card` generates no style output. The elements relying on this have no background color applied.
- **`hover:bg-accent`**: `accent` is not defined anywhere in the config or CSS. These link pill elements on the SEO rate pages have no hover state.

**Impact:** Visual bug on production SEO pages -- the average rate card at `/rates/[state]/[utility]` has no background, and cross-link pills have no hover feedback.

**Fix:** Add `card` and `accent` to the `colors` section of `tailwind.config.ts`:
```ts
card: {
  DEFAULT: '#ffffff',
  foreground: '#111827',
},
accent: {
  DEFAULT: '#f3f4f6',
  foreground: '#111827',
},
```

### P0-2: No `prefers-reduced-motion` Respect Anywhere

**Files:** All animation-bearing components (entire frontend)
**Config:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/tailwind.config.ts` (lines 82-121), `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (lines 157-176)

A project-wide search for `prefers-reduced-motion` returned **zero results** across all `.tsx`, `.ts`, and `.css` files. The project uses extensive animations:
- `animate-spin` (loading spinners in Button, LoginForm, SignupForm, AgentChat)
- `animate-bounce` (AgentChat typing indicator, line 166)
- `animate-ping` (Header live indicator, line 57)
- `animate-pulse` (Skeleton shimmer)
- `animate-slideDown`, `animate-fadeIn`, `animate-scaleIn` (custom keyframes)
- `shimmer` animation on skeleton loaders

Users who have enabled "Reduce Motion" in their OS settings will still see all animations, which is a WCAG 2.1 Level AA violation (Success Criterion 2.3.3) and can cause vestibular discomfort.

**Fix:** Add a `@media (prefers-reduced-motion: reduce)` block to `globals.css`:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```
Additionally, Tailwind's `motion-reduce:` prefix should be used on critical animations (e.g., `motion-reduce:animate-none` on spinners).

---

## P1 -- High (Fix This Sprint)

### P1-1: Widespread Use of Raw Tailwind Palette Colors Instead of Design Tokens

Multiple components bypass the custom color palette (`primary`, `success`, `warning`, `danger`) and use raw Tailwind colors (`blue-*`, `green-*`, `red-*`, `yellow-*`, `purple-*`, `amber-*`, `emerald-*`). This undermines the design system and will cause inconsistencies if the brand palette changes.

**Offending files and raw color counts:**

| File | Raw Colors Used |
|------|----------------|
| `components/cca/CCAAlert.tsx` (lines 22-61) | `blue-200`, `blue-50`, `blue-900`, `blue-700`, `blue-400`, `blue-600`, `green-700` |
| `components/cca/CCAInfo.tsx` (lines 12-106) | `yellow-400`, `blue-400`, `purple-400`, `green-100`, `green-800`, `amber-100`, `amber-800`, `blue-700`, `blue-900` |
| `components/pwa/InstallPrompt.tsx` (lines 62-78) | `blue-600`, `blue-50`, `blue-600` |
| `components/dashboard/UtilityDiscoveryCard.tsx` (lines 26-86) | `green-100`, `green-700`, `blue-100`, `blue-700`, `blue-200`, `blue-50`, `blue-900`, `blue-400`, `blue-600`, `blue-300` |
| `components/dashboard/CombinedSavingsCard.tsx` (lines 8-13) | `yellow-400`, `blue-400`, `orange-400`, `red-400`, `green-400`, `cyan-400` |
| `components/seo/RatePageContent.tsx` (lines 171-180) | `blue-50`, `blue-900`, `blue-700`, `blue-600`, `blue-700` |
| `components/heating-oil/DealerList.tsx` (lines 35-54) | `yellow-100`, `yellow-800`, `blue-700`, `blue-900` |
| `components/gamification/SavingsTracker.tsx` (lines 35-38) | `amber-*`, `yellow-*`, `purple-*` |
| `components/connections/EmailConnectionFlow.tsx` (lines 345-369) | `red-100`, `red-600`, `blue-100`, `blue-600` |
| `components/onboarding/SupplierPicker.tsx` (lines 34-35) | `green-100`, `green-600` |
| `components/onboarding/UtilityTypeSelector.tsx` (lines 36-37) | `amber-100`, `amber-600` |
| `components/onboarding/AccountLinkStep.tsx` (lines 40-41) | `purple-100`, `purple-600` |
| `components/charts/PriceLineChart.tsx` (line 161) | `emerald-700` |
| `components/dashboard/NeighborhoodCard.tsx` (line 89) | `green-600` |

**Impact:** ~15 components use 30+ instances of raw palette colors. If the brand blue shifts from `blue-500` (#3b82f6) to something different, these will remain unchanged while `primary-*` updates automatically.

**Fix:** Map all raw colors to semantic tokens:
- `blue-*` -> `primary-*`
- `green-*` -> `success-*`
- `red-*` -> `danger-*`
- `yellow-*`/`amber-*` -> `warning-*`
- For truly semantic one-offs (energy mix colors in CCAInfo, utility type colors in CombinedSavingsCard), extract to a constants file like `chartTokens.ts` was done for charts.

### P1-2: Dark Mode Configuration Exists but Zero Implementation

**Config:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/tailwind.config.ts` (line 4: `darkMode: 'class'`)
**CSS:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (lines 8-12: comment about dark mode)

A project-wide search for the `dark:` Tailwind prefix across all `.tsx` files returned **zero results**. The `darkMode: 'class'` configuration and the comment in `globals.css` confirm dark mode was planned but never implemented. Meanwhile:

- Every component hardcodes `bg-white`, `text-gray-900`, `border-gray-200` etc.
- The CSS variables in `:root` (lines 14-90) have no `.dark` counterpart
- `color-scheme: light` is explicitly forced (line 15)

**Impact:** This is not a bug per se since the comment acknowledges it, but the `darkMode: 'class'` config entry creates a false impression of support. If dark mode is not planned soon, this should be documented as a known limitation. If it IS planned, a `.dark` CSS variable set should be prepared now so components using CSS vars automatically adapt.

**Recommendation:** Either:
1. Remove `darkMode: 'class'` from config and add a comment in the config file that dark mode is not supported, OR
2. Add a `.dark` class override block in `globals.css` with inverted CSS custom properties so the token-based components (body, inputs, skeleton) adapt. The hardcoded `bg-white` / `text-gray-900` in 80+ components would still need individual `dark:` prefixes.

### P1-3: Inconsistent Button/Submit Patterns -- Some Components Use `<Button>`, Others Use Raw `<button>`

The project has a well-designed `<Button>` component (`components/ui/button.tsx`) with consistent variants, focus rings, disabled states, and loading spinners. However, several components bypass it and use raw `<button>` elements with duplicated inline Tailwind classes:

| File | Line | Issue |
|------|------|-------|
| `components/alerts/AlertForm.tsx` | 173-179 | Raw `<button>` with hand-rolled `bg-primary-600 ... hover:bg-primary-700 disabled:opacity-50` instead of `<Button>` |
| `components/auth/LoginForm.tsx` | 232-244 | Raw `<button>` with duplicate primary button styles + inline SVG spinner |
| `components/auth/SignupForm.tsx` | 339-351 | Same pattern as LoginForm |
| `components/community/PostForm.tsx` | 224-231 | Raw `<button>` with `bg-primary-600` styles |
| `components/agent/AgentChat.tsx` | 216-228 | Raw `<button>` for send button |

**Impact:** These raw buttons miss features the `<Button>` provides (consistent focus ring via `focus-visible:ring-2 focus-visible:ring-offset-2`, `gap-2` icon spacing, `transition-colors duration-200`). The LoginForm and SignupForm buttons also lack `focus-visible:ring-*` entirely, which is an accessibility gap.

**Fix:** Replace raw `<button>` elements with the `<Button>` component. For the auth forms' loading spinner, use `<Button loading={isLoading}>`.

### P1-4: Inconsistent Form Element Styling

The `<Input>` component provides consistent form styling, but several components create `<select>` and `<textarea>` elements with minimal, inconsistent classes:

| File | Line | Element | Classes |
|------|------|---------|---------|
| `components/community/PostForm.tsx` | 117 | `<select>` | `"w-full rounded-lg border px-3 py-2 text-sm"` -- no focus ring, no hover, no border color |
| `components/community/PostForm.tsx` | 131 | `<select>` | Same minimal classes |
| `components/community/PostForm.tsx` | 149 | `<input>` | Same minimal classes |
| `components/community/PostForm.tsx` | 165 | `<textarea>` | Same minimal classes |
| `components/community/PostForm.tsx` | 185 | `<input>` | Same minimal classes |

Compare these to the fully-styled `<select>` in `AlertForm.tsx` (line 90: full border color, focus ring, hover state, transition). The PostForm inputs will look visually different from the rest of the application.

**Fix:** Create a shared `<Select>` component in `components/ui/` matching `<Input>` styling, or use the same class composition. At minimum, add `border-gray-300 focus:border-primary-500 focus:ring-2 focus:ring-primary-500 hover:border-gray-400 transition-all duration-200` to all form elements.

---

## P2 -- Medium (Fix Soon)

### P2-1: Z-Index Values Are Not Centralized

The project uses `z-*` classes in 18+ locations with values: `z-10`, `z-20`, `z-30`, `z-40`, `z-50`. These are scattered across components without a documented scale:

| Z-Index | Components |
|---------|------------|
| `z-10` | `ScheduleTimeline.tsx` (hovered schedule block) |
| `z-20` | `ScheduleTimeline.tsx` (tooltip) |
| `z-30` | `ScheduleTimeline.tsx` (current time marker) |
| `z-40` | `Header.tsx` (sticky header), `FeedbackWidget.tsx` (FAB) |
| `z-50` | `Sidebar.tsx` (desktop + mobile), `Modal.tsx`, `NotificationBell.tsx` dropdown, `SupplierSelector.tsx` dropdown, `SuppliersContent.tsx` dialogs, `InstallPrompt.tsx`, `ToastProvider`, `FeedbackWidget.tsx` (modal) |

**Issue:** Everything at `z-50` competes. The sidebar, modal, toast container, notification dropdown, supplier selector dropdown, install prompt, and feedback modal all share `z-50`. If a modal opens while the notification dropdown is visible, or if the install prompt overlaps the feedback FAB, stacking will be unpredictable.

**Fix:** Define a z-index scale in `tailwind.config.ts` or a constants file:
```
dropdown: 30
sticky: 40
overlay: 50
modal: 60
toast: 70
tooltip: 80
```

### P2-2: Inline `style={}` Used Where Tailwind Classes Would Suffice

Some inline styles are necessary (dynamic chart heights, percentage positions in timeline), but several could be replaced with Tailwind utilities:

| File | Line | Current | Could Be |
|------|------|---------|----------|
| `AgentChat.tsx` | 166 | `style={{ animationDelay: '0ms' }}` | `delay-0` (or remove -- 0ms is default) |
| `AgentChat.tsx` | 167 | `style={{ animationDelay: '150ms' }}` | `delay-150` (Tailwind default) |
| `AgentChat.tsx` | 168 | `style={{ animationDelay: '300ms' }}` | `delay-300` (Tailwind default) |
| `DashboardContent.tsx` | 268 | `style={{ minHeight: "48px", contain: "layout" }}` | `min-h-12` + custom `contain-layout` utility |

The remaining inline styles (chart heights, percentage-based positioning in ScheduleTimeline, dynamic `scaleX` transforms on progress bars) are legitimate uses of inline styles since their values are computed at runtime.

### P2-3: `!important` Usage in Global CSS

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css`

The `!important` flag appears 11 times, all within two contexts:

1. **Recharts tooltip override** (line 180): `z-index: 100 !important;` -- Necessary to override Recharts' inline styles. Acceptable.

2. **Print styles** (lines 213-251): 9 uses of `!important` -- All within `@media print {}`. This is standard practice since print styles must override everything. Acceptable.

**Verdict:** All `!important` usages are justified. No action needed, but the Recharts z-index value of `100` conflicts with the z-index system documented in P2-1 (all component z-indexes are <= 50, but Recharts tooltip forces 100). This is fine in practice because tooltips are transient, but it should be noted.

### P2-4: Scrollbar Styling Uses Hardcoded Hex Values Instead of CSS Variables

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (lines 115-131)

```css
::-webkit-scrollbar-track {
  background: #f1f5f9;  /* slate-100 */
}
::-webkit-scrollbar-thumb {
  background: #cbd5e1;  /* slate-300 */
}
::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;  /* slate-400 */
}
```

These hardcoded hex values come from the `slate` palette, while the rest of the app uses `gray`. They also cannot be themed via CSS variables.

**Fix:** Use the existing CSS custom properties:
```css
::-webkit-scrollbar-track {
  background: rgb(var(--color-surface-secondary));
}
::-webkit-scrollbar-thumb {
  background: rgb(var(--color-border));
}
```

### P2-5: Duplicate Animation Definitions in Config and CSS

**Files:** `tailwind.config.ts` (lines 90, 117-120) and `globals.css` (lines 173-176)

The `shimmer` animation is defined in both places with slightly different timing:
- Config: `'shimmer': 'shimmer 1.5s ease-in-out infinite'` (line 90)
- CSS: `.animate-shimmer { animation: shimmer 2s linear infinite; }` (line 174)
- CSS `.skeleton` class: `animation: shimmer 1.5s ease-in-out infinite;` (line 192)

This means `animate-shimmer` Tailwind utility uses 1.5s ease-in-out, the CSS class `.animate-shimmer` uses 2s linear, and `.skeleton` uses 1.5s ease-in-out. Three different timings for the same visual effect.

**Fix:** Remove the CSS-level `.animate-shimmer` class and always use Tailwind's `animate-shimmer` utility, or consolidate to one definition.

### P2-6: CSS Custom Property Format Inconsistency (RGB Channels vs Hex)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css`

Surface/semantic colors use the space-separated RGB channel format (lines 18-45):
```css
--color-primary: 59 130 246;
--color-success: 16 185 129;
```

Chart colors use hex format (lines 77-89):
```css
--chart-1: #3b82f6;
--chart-grid: #e5e7eb;
```

The RGB-channel format enables `rgb(var(--color-primary) / 0.5)` opacity modifiers. The hex format does not. This inconsistency means chart colors cannot use the alpha channel trick, and the two groups of variables require different usage patterns.

**Impact:** Low -- chart colors are consumed by Recharts which accepts hex strings directly. But if a component tries to use `rgb(var(--chart-1) / 0.3)`, it will fail silently.

**Recommendation:** Document this intentional divergence in `chartTokens.ts` header comment, or convert chart colors to RGB channel format for consistency.

### P2-7: Card Component Default Has No Shadow or Border for `default` Variant

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/card.tsx` (lines 11-15)

```ts
const variantStyles = {
  default: 'bg-white',  // no border, no shadow
  bordered: 'bg-white border border-gray-200',
  elevated: 'bg-white shadow-lg',
}
```

The `default` variant has only `bg-white` -- no border, no shadow. On a `bg-gray-50` page background, this creates very subtle card boundaries that may be hard to distinguish. Multiple dashboard components use `<Card>` without specifying a variant (which defaults to `bordered`), so this is not currently a visible issue. However, the `default` variant's lack of any visual boundary means it is functionally identical to a bare `<div>` with `bg-white rounded-xl`.

**Recommendation:** Either add a subtle shadow to `default` (`shadow-sm`) or remove the variant if unused.

---

## P3 -- Low / Housekeeping

### P3-1: Arbitrary Value `text-[10px]` Used in Sidebar

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/Sidebar.tsx` (line 154)

```tsx
<p className="px-3 py-1 text-[10px] text-gray-300">v1.0.0</p>
```

This is the only instance of an arbitrary font size value in the entire component library. Tailwind provides `text-[10px]` which works, but this creates a one-off size outside the type scale (`text-xs` = 12px is the smallest standard size).

**Impact:** Negligible. Version text at 10px is intentionally de-emphasized.

**Recommendation:** Use `text-xs` (12px) for consistency, or add `'2xs': '0.625rem'` to `fontSize` in config if the smaller size is intentional.

### P3-2: Template Literal Class Names Instead of `cn()` in Several Components

Several components use template literal string concatenation for conditional classes instead of the `cn()` utility:

| File | Line | Pattern |
|------|------|---------|
| `AgentChat.tsx` | 20 | `` `flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}` `` |
| `AgentChat.tsx` | 27-33 | Template literal with ternary for message bubble colors |
| `AgentChat.tsx` | 208 | Template literal for character count color |
| `CCAInfo.tsx` | 57-63 | Template literal for rate badge colors |
| `SignupForm.tsx` | 260 | Template literal for password strength bar |

While these work, they bypass `tailwind-merge`'s deduplication. If a parent ever passes conflicting classes via `className`, `cn()` would correctly resolve the conflict while template literals would not.

**Fix:** Replace template literals with `cn()` for consistency:
```tsx
// Before
className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
// After
className={cn('flex gap-3', isUser ? 'justify-end' : 'justify-start')}
```

### P3-3: Inconsistent Focus Ring Patterns

Across 28 components, there are 55 instances of focus ring styling with two different patterns:

1. **`focus-visible:ring-2 focus-visible:ring-offset-2`** -- Used by `<Button>`, `<ConnectionMethodPicker>`, `<FeedbackWidget>`, `<ErrorBoundary>` (6 components)
2. **`focus:ring-2 focus:ring-offset-0`** -- Used by `<Input>`, `<Checkbox>`, `<FeedbackWidget>` textarea (3 components)
3. **`focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2`** -- Used by `<EmailConnectionFlow>`, `<ConnectionsOverview>`, `<Sidebar>` close button (5 components)
4. **No focus indicator at all** -- Auth form submit buttons (LoginForm line 235, SignupForm line 342), AgentChat buttons (lines 121-128, 216-228)

The `focus-visible` vs `focus` distinction is meaningful: `focus-visible` only shows the ring on keyboard navigation, while `focus` shows it on mouse clicks too. The project should standardize on `focus-visible` for buttons (matching the global `*:focus-visible` rule in globals.css line 145) and `focus` for inputs (which need visible focus for accessibility).

Some buttons lack any focus indicator beyond the global `*:focus-visible` outline. Since that global rule uses `outline` (not `ring`), and some buttons have `focus:outline-none` or `focus-visible:outline-none` followed by ring styles, the patterns should be reconciled.

### P3-4: Content Paths in `tailwind.config.ts` Missing `lib/` Directory

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/tailwind.config.ts` (lines 5-9)

```ts
content: [
  './pages/**/*.{js,ts,jsx,tsx,mdx}',
  './components/**/*.{js,ts,jsx,tsx,mdx}',
  './app/**/*.{js,ts,jsx,tsx,mdx}',
],
```

The `lib/` directory is not included. Files like `lib/contexts/toast-context.tsx` (which contains `className="fixed bottom-4 right-4 z-50..."`) are not in the content path. Tailwind relies on the content paths to detect which utility classes to include in the build.

**Impact:** In practice, Next.js + Tailwind with PostCSS may still detect these through imports, and the toast context classes are likely already used elsewhere. But to be safe, `./lib/**/*.{ts,tsx}` should be added.

### P3-5: OAuth Button SVGs Use Hardcoded Brand Colors

**Files:** `LoginForm.tsx` (lines 160-163), `SignupForm.tsx` (lines 178-183)

The Google OAuth button SVG paths use hardcoded brand colors (`#4285F4`, `#34A853`, `#FBBC05`, `#EA4335`). This is intentional and correct -- these are Google's official brand colors and should NOT be tokenized. No action needed.

### P3-6: Skeleton Component Uses `animate-pulse` Instead of Custom `shimmer`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/skeleton.tsx` (line 24)

The `Skeleton` component uses Tailwind's built-in `animate-pulse` (a simple opacity fade), while the `.skeleton` CSS class in `globals.css` uses a gradient shimmer animation. These are visually different loading indicators used in different contexts.

**Recommendation:** Standardize on one loading animation style. The shimmer gradient is more polished. Consider using `className="skeleton"` or applying the shimmer keyframe as the skeleton animation.

### P3-7: Print Styles Hide All Buttons Unconditionally

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/globals.css` (lines 209-210)

```css
button,
[role="button"],
```

All buttons are hidden in print. This is generally correct, but if a page ever needs a "Print this page" button to remain visible, there is no escape hatch. Consider adding a `.print:block` utility or a `data-print-visible` attribute exception.

---

## Files With No Issues Found

The following reviewed files demonstrated clean, consistent styling patterns:

- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/constants/chartTokens.ts` -- Excellent design token module with semantic aliases, JSDoc, and proper CSS variable references
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/utils/cn.ts` -- Clean clsx + tailwind-merge composition
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/badge.tsx` -- Consistent use of design tokens, proper forwardRef pattern
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/toast.tsx` -- Good ARIA attributes, semantic color tokens, proper icon accessibility
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/modal.tsx` -- Full focus trap, escape key handling, proper ARIA, `z-50` overlay
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/input.tsx` -- Comprehensive accessibility (aria-invalid, aria-describedby, role="alert"), consistent styling
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/charts/PriceLineChart.tsx` -- Proper use of `chartTokens`, ARIA labels, responsive container
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/charts/SavingsDonut.tsx` -- Uses `CHART_COLORS` from tokens, ARIA labels on chart container
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/charts/ForecastChart.tsx` -- Consistent token usage, empty state handling
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/DashboardStatsRow.tsx` -- Clean use of semantic colors, responsive grid
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/DashboardCharts.tsx` -- Dynamic import with skeleton fallback, proper tier gating UI
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/ConnectionMethodPicker.tsx` -- Excellent card pattern with focus rings, group hover, consistent spacing
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/error-boundary.tsx` -- Proper error UI with focus-visible ring on retry button
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/feedback/FeedbackWidget.tsx` -- Full focus trap, ARIA, proper z-index layering, consistent token usage
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/layout.tsx` -- Skip-to-content link, proper sidebar layout, error boundary wrapping
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/layout.tsx` -- Proper font loading via `next/font`, provider hierarchy

---

## Summary

### Overall Assessment

The RateShift frontend has a **well-architected design system foundation** with CSS custom properties, a dedicated chart token module, a `cn()` utility for class composition, and a set of reusable UI primitives (Button, Card, Input, Badge, Toast, Modal, Skeleton). The Tailwind configuration is clean with a purposeful custom color palette that maps to energy/utility domain semantics.

### Strengths
- Chart token architecture (`chartTokens.ts` + CSS variables) is best-in-class
- Global CSS is well-organized with clear sections (base, utilities, animations, print)
- UI components use `forwardRef` consistently and expose `className` for composition
- Accessibility is strong in core components (Input, Modal, Toast, FeedbackWidget)
- Skip-to-content link is present in the app layout
- Print styles are thoughtfully implemented
- `cn()` (clsx + tailwind-merge) used in most components

### Key Metrics
| Category | Count |
|----------|-------|
| P0 (Critical) | 2 |
| P1 (High) | 4 |
| P2 (Medium) | 7 |
| P3 (Low) | 7 |
| Files with no issues | 16 |
| Total files reviewed | 39 (plus project-wide grep across all .tsx/.css) |

### Top Priorities
1. **P0-1:** Fix undefined `bg-card` and `hover:bg-accent` tokens -- broken styles on SEO pages
2. **P0-2:** Add `prefers-reduced-motion` support -- WCAG accessibility violation
3. **P1-1:** Migrate 30+ raw palette color usages to semantic design tokens
4. **P1-3:** Replace raw `<button>` elements in auth/form components with `<Button>` component
5. **P1-4:** Standardize form element styling (create `<Select>` component or use consistent classes)
