# Audit Report: CSS & Styling
**Date:** 2026-03-19
**Scope:** Tailwind config, global CSS, design system, component styling patterns
**Files Reviewed:**
- `frontend/tailwind.config.ts`
- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/app/page.tsx` (landing page)
- `frontend/app/(app)/layout.tsx`
- `frontend/app/(app)/dashboard/loading.tsx`
- `frontend/app/(app)/dashboard/error.tsx`
- `frontend/lib/utils/cn.ts`
- `frontend/lib/constants/chartTokens.ts`
- `frontend/components/ui/badge.tsx`
- `frontend/components/ui/button.tsx`
- `frontend/components/ui/card.tsx`
- `frontend/components/ui/input.tsx`
- `frontend/components/ui/modal.tsx`
- `frontend/components/ui/skeleton.tsx`
- `frontend/components/ui/toast.tsx`
- `frontend/components/layout/Sidebar.tsx`
- `frontend/components/layout/Header.tsx`
- `frontend/components/layout/StatusBadge.tsx`
- `frontend/components/auth/LoginForm.tsx`
- `frontend/components/auth/SignupForm.tsx`
- `frontend/components/dashboard/DashboardStatsRow.tsx`
- `frontend/components/dashboard/DashboardCharts.tsx`
- `frontend/components/charts/PriceLineChart.tsx`
- `frontend/components/charts/ForecastChart.tsx`
- `frontend/components/alerts/AlertForm.tsx`
- `frontend/components/connections/ConnectionCard.tsx`
- `frontend/components/connections/BillUploadDropZone.tsx`
- `frontend/components/agent/AgentChat.tsx`
- `frontend/components/gamification/SavingsTracker.tsx`
- `frontend/components/suppliers/ComparisonTable.tsx`
- `frontend/components/community/PostForm.tsx`
- `frontend/components/water/WaterDashboard.tsx`
- `frontend/components/propane/PropaneDashboard.tsx`
- `frontend/components/feedback/FeedbackWidget.tsx`
- `frontend/components/community-solar/SavingsCalculator.tsx`
- `frontend/components/analytics/AnalyticsDashboard.tsx`
- `frontend/components/rate-changes/RateChangeFeed.tsx`
- `frontend/components/seo/RatePageContent.tsx`
- `frontend/components/pwa/InstallPrompt.tsx`
- `frontend/components/error-boundary.tsx`

Additionally performed codebase-wide grep scans across all `frontend/components/**/*.tsx` and `frontend/app/**/*.tsx` for: z-index values, hardcoded hex colors, raw Tailwind color usage bypassing design tokens, `dark:` prefixes, inline `style={}`, `!important`, `bg-muted`/`text-muted-foreground`, `rounded-md` vs `rounded-lg`, and `<select>` element styling patterns.

***

## P0 -- Critical (Fix Immediately)

### P0-1: Undefined `bg-muted` / `text-muted-foreground` CSS classes render as invisible no-ops

Multiple components use `bg-muted` and `text-muted-foreground` classes that are not defined in `tailwind.config.ts` or `globals.css`. These are shadcn/ui token names that were never registered. Tailwind will silently ignore them, producing **no background color** on skeleton loading states and **invisible text** on content.

**Affected files (15+ usages):**
- `frontend/components/rate-changes/RateChangeFeed.tsx` line 36: `bg-muted` on skeleton placeholder -- renders transparent instead of gray
- `frontend/components/rate-changes/RateChangeFeed.tsx` line 79: `text-muted-foreground` on "No rate changes" message -- renders default body color instead of muted gray
- `frontend/components/rate-changes/AlertPreferences.tsx` line 23: `bg-muted` on skeleton -- transparent
- `frontend/components/rate-changes/AlertPreferences.tsx` line 93: `text-muted-foreground` on "Saving..." indicator
- `frontend/components/rate-changes/RateChangeCard.tsx` lines 34, 50, 54: `text-muted-foreground` on utility label and price labels
- `frontend/components/seo/RatePageContent.tsx` lines 49, 67, 75, 80, 106, 122, 125: `text-muted-foreground` on breadcrumbs, descriptions, table cells

**Impact:** Loading skeleton states are invisible (no background). Muted text labels may render in default foreground color rather than the intended subdued gray, breaking visual hierarchy. On the SEO pages (`/rates/[state]/[utility]`), this affects public-facing content.

**Fix:** Either define `muted` and `muted-foreground` in the Tailwind theme `extend.colors` (e.g., `muted: { DEFAULT: '#f1f5f9', foreground: '#64748b' }`), or replace all usages with the existing design system equivalents (`bg-gray-100` / `text-gray-500`).

***

## P1 -- High (Fix This Sprint)

### P1-1: Landing page and public pages use raw `blue-*` instead of design system `primary-*`

The Tailwind config defines a `primary` color palette (lines 13-24) that maps to the same blue values. However, the landing page (`frontend/app/page.tsx`), pricing page (`frontend/app/pricing/page.tsx`), terms page (`frontend/app/terms/page.tsx`), privacy page (`frontend/app/privacy/page.tsx`), and PWA install prompt (`frontend/components/pwa/InstallPrompt.tsx`) all use raw `text-blue-600`, `bg-blue-600`, `hover:bg-blue-700`, and `border-blue-600` instead of `primary-600`/`primary-700`.

**Specific locations (19+ instances on landing page alone):**
- `frontend/app/page.tsx` line 91: `text-blue-600` on Zap icon
- `frontend/app/page.tsx` line 103: `bg-blue-600` on CTA button
- `frontend/app/page.tsx` line 116: `text-blue-600` on hero highlight
- `frontend/app/page.tsx` line 125: `bg-blue-600` on hero CTA
- `frontend/app/page.tsx` lines 153, 177, 190, 199, 216: various `blue-*` usages
- `frontend/components/pwa/InstallPrompt.tsx` line 62: `bg-blue-600` on install banner
- `frontend/components/pwa/InstallPrompt.tsx` line 77: `text-blue-600` on install button

**Impact:** If the brand color is ever updated (e.g., changing `primary-600` to a different shade), these pages will be left behind, creating a split-brand appearance. The `primary` palette exists specifically for this purpose but is bypassed on the most visible public pages.

**Fix:** Replace all `blue-*` references with `primary-*` equivalents on these pages.

### P1-2: No dark mode implementation despite `darkMode: 'class'` being configured

`tailwind.config.ts` line 4 sets `darkMode: 'class'`, and `globals.css` lines 5-12 include a comment acknowledging dark mode is not yet implemented. However, across all 40+ component files reviewed, **zero** `dark:` prefixed classes were found anywhere in the component tree. The `:root` CSS custom properties define only light-mode values with no `.dark` counterpart.

**Impact:** This is not a bug per se -- the comment acknowledges it explicitly. However, all hardcoded `bg-white`, `text-gray-900`, `border-gray-200`, etc. throughout every component will require systematic updates when dark mode is built. The longer this is deferred, the more files will need touching. The CSS custom property architecture in `globals.css` (lines 14-90) is well-positioned for dark mode -- the variables just need `.dark` overrides.

**Recommendation:** This is noted as a design debt item. When dark mode is prioritized, add `.dark` overrides to globals.css for all `--color-*`, `--shadow-*`, and `--chart-*` variables, then add `dark:` prefixes to the 7 `components/ui/` primitives first (Card, Button, Input, Badge, Modal, Toast, Skeleton). Components using these primitives will largely inherit.

### P1-3: `<select>` elements have 5+ distinct styling patterns with no shared primitive

The design system provides `Input`, `Checkbox`, and `Button` primitives but no `Select` component. Across 18+ `<select>` elements in the codebase, at least 5 distinct styling patterns were found:

1. **AlertForm pattern** (`frontend/components/alerts/AlertForm.tsx` line 90): `rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-gray-900 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500 transition-all duration-200 hover:border-gray-400` -- matches the Input component style
2. **PostForm pattern** (`frontend/components/community/PostForm.tsx` line 117): `w-full rounded-lg border px-3 py-2 text-sm` -- minimal, missing focus ring and explicit colors
3. **AnalyticsDashboard pattern** (`frontend/components/analytics/AnalyticsDashboard.tsx` line 31): `rounded-md border border-gray-300 px-3 py-1.5 text-sm` -- uses `rounded-md` instead of `rounded-lg`
4. **WaterDashboard pattern** (`frontend/components/water/WaterDashboard.tsx` line 48): `mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-cyan-500 focus:ring-cyan-500 sm:text-sm` -- uses off-brand `cyan` focus ring
5. **RateChangeFeed pattern** (`frontend/components/rate-changes/RateChangeFeed.tsx` line 54): `rounded border px-3 py-1.5 text-sm` -- uses `rounded` (4px) instead of `rounded-lg` (8px), no focus styles

**Impact:** Inconsistent select styling creates visual discord when users navigate between pages. Focus ring colors differ (primary-500 vs cyan-500 vs none), border radii differ (rounded vs rounded-md vs rounded-lg), and padding differs.

**Fix:** Create a `Select` primitive in `frontend/components/ui/select.tsx` mirroring the Input component's styling patterns, then migrate all raw `<select>` elements.

### P1-4: Water utility components use off-brand `cyan-*` focus ring colors

`frontend/components/water/WaterDashboard.tsx` line 48, `frontend/components/water/WaterTierCalculator.tsx` lines 78 and 100 all use `focus:border-cyan-500 focus:ring-cyan-500` instead of the design system's `focus:border-primary-500 focus:ring-primary-500`.

**Impact:** Users tabbing through water utility forms see a cyan focus ring, while every other form in the app shows a blue/primary focus ring. This breaks the consistent interaction pattern established by the Input primitive.

**Fix:** Replace `focus:border-cyan-500 focus:ring-cyan-500` with `focus:border-primary-500 focus:ring-primary-500`. The cyan color is appropriate for decorative/informational backgrounds (`bg-cyan-50`) but not for interactive focus indicators.

***

## P2 -- Medium (Fix Soon)

### P2-1: Border radius inconsistency (`rounded` vs `rounded-md` vs `rounded-lg` vs `rounded-xl`)

The design system's CSS variables define `--radius-sm: 0.375rem` (6px), `--radius-md: 0.5rem` (8px), `--radius-lg: 0.75rem` (12px), `--radius-xl: 1rem` (16px). In practice, components use Tailwind's native radius classes inconsistently:

- **Cards** use `rounded-xl` (16px) -- `Card` component line 30, `ConnectionCard` line 203
- **Buttons** use `rounded-lg` (8px) -- `Button` component line 53
- **Inputs** use `rounded-lg` (8px) -- `Input` component line 47
- **Analytics selects** use `rounded-md` (6px) -- `AnalyticsDashboard.tsx` line 31, `DataExport.tsx` lines 76/92
- **RateChangeFeed selects** use `rounded` (4px) -- `RateChangeFeed.tsx` line 54
- **Error boundary button** uses `rounded-md` (6px) -- `error-boundary.tsx` line 75

**Impact:** Subtle visual inconsistency. Interactive elements should share the same border radius. The design system defines radius tokens but they are CSS custom properties, not Tailwind utilities, so they go unused in class strings.

**Recommendation:** Establish a convention: `rounded-lg` for all interactive elements (buttons, inputs, selects), `rounded-xl` for card containers. Consider extending the Tailwind `borderRadius` config to map the CSS custom property names.

### P2-2: Inline submit buttons duplicate Button component styling

The LoginForm (`frontend/components/auth/LoginForm.tsx` line 232-244), SignupForm (`frontend/components/auth/SignupForm.tsx` line 339-351), AlertForm (`frontend/components/alerts/AlertForm.tsx` line 173-180), PostForm (`frontend/components/community/PostForm.tsx` line 224-231), and SavingsCalculator (`frontend/components/community-solar/SavingsCalculator.tsx` line 81-85) all create inline `<button>` elements with manually composed Tailwind classes that partially replicate the `Button` component.

For example, `LoginForm.tsx` line 235:
```
className="w-full bg-primary-600 text-white py-2.5 px-4 rounded-lg hover:bg-primary-700 active:bg-primary-800 transition-all duration-200 font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
```

This mirrors `Button variant="primary"` but adds `active:bg-primary-800` and `w-full` that the Button primitive does not include by default. The Button component exists and supports `className` overrides.

**Impact:** When the Button primitive is updated (e.g., changing hover state, adding focus-visible ring, adjusting padding), these inline buttons will be missed.

**Fix:** Replace with `<Button variant="primary" className="w-full" loading={isLoading}>`.

### P2-3: CSS custom properties in `globals.css` use space-separated RGB format but some vars use hex

The `:root` block uses two different color formats:
- **Space-separated RGB** (lines 18-41): `--color-background: 249 250 251;` -- designed for `rgb(var(--color-*) / alpha)` usage
- **Hex values** (lines 77-89): `--chart-1: #3b82f6;` -- used directly as color strings

This dual format is intentional for different use cases (RGB for alpha compositing, hex for chart libraries that need string values), but none of the RGB-format variables are actually consumed by Tailwind utility classes. They exist in the CSS but are only used in the `body` rule (line 93) and base layer inputs (lines 101-107). The component layer exclusively uses Tailwind's built-in `gray-*`, `primary-*`, etc. classes rather than `rgb(var(--color-*))`.

**Impact:** The CSS custom property infrastructure is well-designed but largely unused. When dark mode is implemented, the dual system will require maintaining both the Tailwind theme colors AND the CSS variables, doubling the maintenance surface.

**Recommendation:** For dark mode readiness, consider migrating the Tailwind theme to reference the CSS custom properties (e.g., `primary: { 600: 'rgb(var(--color-primary))' }`), so that overriding the CSS variable automatically updates all Tailwind classes.

### P2-4: z-index values are unmanaged -- 4 tiers found but no scale documented

Observed z-index tiers across the codebase:
- `z-10`: Hovered schedule items (`ScheduleTimeline.tsx` line 209)
- `z-20`: Schedule tooltips (`ScheduleTimeline.tsx` line 236)
- `z-30`: Current time marker (`ScheduleTimeline.tsx` line 257)
- `z-40`: Header (`Header.tsx` line 34), Feedback FAB (`FeedbackWidget.tsx` line 288)
- `z-50`: Desktop sidebar (`Sidebar.tsx` line 184), Mobile sidebar (`Sidebar.tsx` lines 190/199), Modal (`modal.tsx` line 87), Toast container (`toast-context.tsx` line 106), Skip link (`layout.tsx` line 16), Install prompt (`InstallPrompt.tsx` line 62), Notification dropdown (`NotificationBell.tsx` line 117), Supplier dialogs (`SuppliersContent.tsx` lines 350/366), Feedback modal (`FeedbackWidget.tsx` line 109), SupplierSelector dropdown (`SupplierSelector.tsx` line 67)

**Issue:** 13+ elements all compete at `z-50`. While most are conditionally rendered (modals, overlays), the desktop sidebar (`z-50`), toast container (`z-50`), feedback FAB (`z-40`), and install prompt (`z-50`) can coexist simultaneously. If a toast fires while the feedback modal is open, both render at `z-50`.

**Fix:** Define a z-index scale constant (e.g., `Z_SIDEBAR=40, Z_HEADER=41, Z_DROPDOWN=45, Z_OVERLAY=48, Z_MODAL=50, Z_TOAST=55, Z_MAX=60`). The sidebar at `z-50` does not need to be above modals -- it should be below them (e.g., `z-30`). Toasts should be above modals.

### P2-5: Raw Tailwind color classes used outside design system for utility-specific theming

Several feature areas use raw Tailwind colors for domain-specific theming without defining them in the design system:

- **Water components**: `cyan-*` (`WaterDashboard.tsx`, `WaterTierCalculator.tsx`, `WaterRateBenchmark.tsx`, `ConservationTips.tsx`)
- **Gas components**: `orange-*` (`GasRatesContent.tsx` lines 84, 175)
- **CCA components**: `green-*`, `amber-*`, `yellow-*`, `purple-*`, `blue-*` (`CCAInfo.tsx`, `CCAAlert.tsx`)
- **Heating oil**: `yellow-*` (`DealerList.tsx` line 35)
- **Gamification**: `amber-*`, `yellow-*`, `purple-*` (`SavingsTracker.tsx` lines 35-38)
- **Onboarding**: `amber-*`, `purple-*`, `green-*` (`UtilityTypeSelector.tsx`, `AccountLinkStep.tsx`, `SupplierPicker.tsx`)
- **Combined savings**: `yellow-*`, `orange-*`, `red-*`, `green-*`, `cyan-*` (`CombinedSavingsCard.tsx` lines 8-13)

**Impact:** These are semantically meaningful (cyan for water, orange for gas) and intentional. However, if the Tailwind `content` purge configuration is ever tightened, or if these colors are ever modified for branding, the scattered usage makes it difficult to find and update all instances.

**Recommendation:** Define a `utilityTheme` map in a constants file (similar to `chartTokens.ts`) that maps each utility type to its color classes. This centralizes the color mapping and makes it searchable.

### P2-6: PriceLineChart uses `text-emerald-700` bypassing the design system

`frontend/components/charts/PriceLineChart.tsx` line 161 uses `text-emerald-700` for the "decreasing price" trend indicator, with a comment explaining it is for "WCAG AA contrast compliance." The design system defines `success-700` as `#15803d` (green-700) which is the same hue family but different shade.

**Impact:** If the `success` palette is adjusted, this one-off `emerald-700` usage will not follow. The WCAG concern is valid -- `text-success-500` (`#22c55e`) on white only achieves 2.9:1 contrast (fails AA for normal text) -- but the fix should be applied at the design system level by using `text-success-700` (`#15803d`, which achieves 5.0:1 on white).

**Fix:** Replace `text-emerald-700` with `text-success-700` and verify the contrast ratio meets 4.5:1.

***

## P3 -- Low / Housekeeping

### P3-1: Animation class duplication between `tailwind.config.ts` and `globals.css`

`globals.css` lines 157-176 define `.animate-slideDown`, `.animate-slideUp`, `.animate-fadeIn`, `.animate-scaleIn`, and `.animate-shimmer` as CSS classes that reference the same keyframes already defined in `tailwind.config.ts` lines 86-115. The comment (lines 150-155) acknowledges this is for backward compatibility.

**Impact:** No functional issue. The Tailwind `animate-*` utilities (e.g., `animate-slide-down`) are the canonical approach. The duplicate CSS classes add ~20 lines of CSS that could be removed if all usages are migrated to the Tailwind utility names.

**Recommendation:** Audit usage of `.animate-fadeIn` etc. in markup. If only Tailwind classes are used, remove the CSS duplicates.

### P3-2: Shimmer animation duration mismatch

`globals.css` line 174 defines `.animate-shimmer` with `animation: shimmer 2s linear infinite`, while `tailwind.config.ts` line 84 defines `'shimmer': 'shimmer 1.5s ease-in-out infinite'`. The `.skeleton` class on line 192 of globals.css uses `1.5s ease-in-out` (matching the Tailwind config). So the CSS `.animate-shimmer` class (2s linear) differs from both the Tailwind utility (`animate-shimmer`, 1.5s ease-in-out) and the `.skeleton` class (1.5s ease-in-out).

**Impact:** If any element uses the CSS `.animate-shimmer` class directly, it will animate at a different speed and easing than elements using the Tailwind `animate-shimmer` utility or the `.skeleton` class.

**Fix:** Align `.animate-shimmer` in globals.css to `1.5s ease-in-out` to match the Tailwind config and skeleton class.

### P3-3: Hardcoded scrollbar colors in `globals.css`

`globals.css` lines 120-131 use hardcoded hex colors for the custom scrollbar (`#f1f5f9`, `#cbd5e1`, `#94a3b8`) instead of CSS custom properties or Tailwind color references. These are Tailwind's `slate-100`, `slate-300`, and `slate-400` -- which is the `slate` palette, not the `gray` palette used everywhere else in the app.

**Impact:** Minor visual inconsistency between the scrollbar tint (slate, slightly blue-tinted) and the rest of the UI (gray, neutral). Not visible on most browsers since `::-webkit-scrollbar` only applies to WebKit-based browsers.

**Fix:** Either change to gray palette equivalents (`#f3f4f6`, `#d1d5db`, `#9ca3af`) or replace with `rgb(var(--color-surface-secondary))` etc.

### P3-4: Google OAuth SVG logo has hardcoded brand colors

`frontend/components/auth/LoginForm.tsx` lines 159-163 and `frontend/components/auth/SignupForm.tsx` lines 178-182 embed the Google logo with hardcoded fills (`#4285F4`, `#34A853`, `#FBBC05`, `#EA4335`). These are Google's official brand colors and should NOT be changed -- they are required by Google's Brand Guidelines.

**Impact:** None. This is documented here only as a reminder that these hex values are intentional and mandated by Google's brand requirements.

### P3-5: Missing `aria-label` on some interactive elements

- `frontend/components/agent/AgentChat.tsx` line 121: Reset button uses `title="New conversation"` but no `aria-label`.
- `frontend/components/community/PostForm.tsx` line 232: Cancel button has no `aria-label`.
- `frontend/components/gamification/SavingsTracker.tsx`: The entire component renders interactive-looking content (streak card, score card) without any explicit ARIA roles or labels, though these are display-only.

**Impact:** Minor accessibility concern. Screen readers will announce "button" without context for the reset button.

### P3-6: Print styles hide all `button` and `[role="button"]` elements

`globals.css` lines 209-210 hide all `button` and `[role="button"]` elements in print. This is intentionally aggressive for "cost report" pages, but if a user prints any page, all interactive controls vanish -- including static-looking buttons that contain informational text (e.g., "Upgrade to Pro" CTAs that provide context).

**Impact:** Low. Print use case is primarily for cost reports. The current approach is reasonable for the stated purpose.

### P3-7: `recharts-tooltip-wrapper` z-index uses `!important`

`globals.css` line 180: `.recharts-tooltip-wrapper { z-index: 100 !important; }`. This is higher than any component z-index (`z-50` = 50) and uses `!important`.

**Impact:** The Recharts tooltip will render above modals and overlays if they happen to overlap. In practice this is unlikely since chart tooltips disappear on mouse-out, but it is a potential stacking context issue.

**Recommendation:** Reduce to `z-index: 10 !important` (above chart elements but below app-level overlays).

***

## Files With No Issues Found

- `frontend/lib/utils/cn.ts` -- Clean utility, proper clsx + tailwind-merge composition
- `frontend/lib/constants/chartTokens.ts` -- Well-structured design token system using CSS custom properties
- `frontend/components/ui/button.tsx` -- Consistent variant/size system, proper disabled handling, loading state
- `frontend/components/ui/card.tsx` -- Clean variant system, proper forwardRef, display name
- `frontend/components/ui/input.tsx` -- Comprehensive with label, error, success, helper text, proper aria attributes
- `frontend/components/ui/modal.tsx` -- Focus trap, escape handling, aria-modal, backdrop click
- `frontend/components/ui/toast.tsx` -- Proper role="alert", aria-atomic, consistent variant styling
- `frontend/components/ui/badge.tsx` -- Clean variant map with design system colors
- `frontend/components/layout/Header.tsx` -- Responsive (mobile menu hidden on lg+), proper aria-labels
- `frontend/components/layout/Sidebar.tsx` -- Mobile overlay with backdrop, close on route change, proper ARIA
- `frontend/components/dashboard/DashboardStatsRow.tsx` -- Uses design system Card/Badge/cn correctly
- `frontend/components/dashboard/DashboardCharts.tsx` -- Proper dynamic import with loading skeleton
- `frontend/components/charts/ForecastChart.tsx` -- Uses chartTokens throughout, no hardcoded colors
- `frontend/components/connections/ConnectionCard.tsx` -- Good use of cn(), Badge, Button primitives
- `frontend/components/connections/BillUploadDropZone.tsx` -- Keyboard accessible (tabIndex, Enter/Space), proper focus ring
- `frontend/components/feedback/FeedbackWidget.tsx` -- Focus trap, escape handler, proper dialog role, responsive positioning
- `frontend/components/suppliers/ComparisonTable.tsx` -- Responsive overflow-x-auto table, proper scope attributes
- `frontend/app/(app)/layout.tsx` -- Skip-to-content link, ErrorBoundary wrapper, clean sidebar offset
- `frontend/app/(app)/dashboard/loading.tsx` -- Uses Skeleton/ChartSkeleton primitives correctly
- `frontend/app/(app)/dashboard/error.tsx` -- Uses Button primitive, clear error messaging

***

## Summary

The RateShift frontend has a **solid design system foundation** with 7 well-crafted UI primitives (`Button`, `Card`, `Input`, `Badge`, `Modal`, `Toast`, `Skeleton`), a proper `cn()` utility using `clsx` + `tailwind-merge`, and a centralized chart token system via CSS custom properties. The `globals.css` file demonstrates thoughtful architecture with custom properties for colors, spacing, radius, transitions, and shadows. Print styles and accessibility (skip-to-content, focus-visible outlines, ARIA attributes) are above average.

**Critical finding:** The `bg-muted` / `text-muted-foreground` classes used in 15+ locations are not defined anywhere in the theme, causing invisible skeleton states and broken text styling on the rate-changes and SEO pages. This needs immediate attention.

**Systematic issues to address this sprint:**
1. Standardize the landing/public pages to use `primary-*` instead of `blue-*` (19+ instances)
2. Create a `Select` UI primitive to replace 5+ inconsistent inline styling patterns (18 raw `<select>` elements)
3. Fix water component focus rings using off-brand `cyan-*` instead of `primary-*`

**Design debt to plan for:**
- Dark mode is configured but zero implementation exists -- all 40+ components use hardcoded light-mode colors
- z-index scale is ad-hoc with 13+ elements at `z-50`
- CSS custom properties are well-defined but largely unused by Tailwind classes (dual maintenance risk)
- 30+ instances of raw Tailwind colors (amber, purple, cyan, orange, etc.) bypass the design system for utility-specific theming

**Quantitative overview:**
- UI primitives: 7 (Button, Card, Input, Badge, Modal, Toast, Skeleton)
- Missing primitives: 1 (Select)
- Hardcoded `blue-*` bypassing `primary-*`: 19+ instances across 5 files
- Undefined CSS classes in use: 2 (`bg-muted`, `text-muted-foreground`) across 15+ locations
- Raw Tailwind colors bypassing theme: 30+ instances across 15+ files
- z-index tiers: 5 (`z-10` through `z-50`), with `z-50` overloaded by 13 elements
- `dark:` prefixed classes: 0 (zero dark mode implementation)
- `<select>` elements without a shared primitive: 18
- Inline buttons duplicating Button component: 5 files
