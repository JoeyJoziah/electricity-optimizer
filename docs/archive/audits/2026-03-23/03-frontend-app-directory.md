# Frontend App Directory Audit

> Auditor: Claude Opus 4.6
> Date: 2026-03-23
> Scope: Every file under `frontend/app/` plus `frontend/middleware.ts` and `frontend/components/auth/AuthGuard.tsx`
> Framework: Next.js 16 App Router + React 19

---

## Files Reviewed

### Root-level (`frontend/app/`)
1. `layout.tsx` -- Root layout (async server component)
2. `page.tsx` -- Landing page (server component)
3. `error.tsx` -- Root error boundary
4. `global-error.tsx` -- Global error boundary
5. `not-found.tsx` -- 404 page
6. `globals.css` -- Design system CSS custom properties
7. `manifest.ts` -- PWA manifest
8. `robots.ts` -- Robots configuration
9. `sitemap.ts` -- Sitemap generation
10. `icon.tsx` -- Favicon (ImageResponse)
11. `apple-icon.tsx` -- Apple touch icon (ImageResponse)

### Public pages (no route group)
12. `pricing/page.tsx` -- Pricing page (server component)
13. `privacy/page.tsx` -- Privacy policy (server component)
14. `terms/page.tsx` -- Terms of service (server component)
15. `rates/[state]/[utility]/page.tsx` -- Dynamic ISR rate pages (async server component)

### API routes
16. `api/auth/[...all]/route.ts` -- Better Auth catch-all handler
17. `api/checkout/route.ts` -- Stripe checkout proxy
18. `api/pwa-icon/route.tsx` -- Dynamic PWA icon generation
19. `api/dev/diagrams/route.ts` -- Dev-only diagram CRUD
20. `api/dev/diagrams/[name]/route.ts` -- Dev-only diagram detail

### `(app)` route group (authenticated pages)
21. `(app)/layout.tsx` -- App layout (AuthGuard + Sidebar)
22. `(app)/error.tsx` -- App route group error boundary
23. `(app)/dashboard/page.tsx` -- Dashboard (server component)
24. `(app)/dashboard/loading.tsx` -- Dashboard loading skeleton
25. `(app)/dashboard/error.tsx` -- Dashboard error boundary
26. `(app)/alerts/page.tsx` -- Alerts page (server component)
27. `(app)/alerts/loading.tsx`
28. `(app)/alerts/error.tsx`
29. `(app)/analytics/page.tsx` -- Analytics page (server component)
30. `(app)/analytics/loading.tsx`
31. `(app)/analytics/error.tsx`
32. `(app)/assistant/page.tsx` -- AI assistant page (server component)
33. `(app)/assistant/loading.tsx`
34. `(app)/assistant/error.tsx`
35. `(app)/beta-signup/page.tsx` -- Beta signup form ('use client')
36. `(app)/beta-signup/loading.tsx`
37. `(app)/beta-signup/error.tsx`
38. `(app)/community/page.tsx` -- Community page ('use client')
39. `(app)/community/loading.tsx`
40. `(app)/community/error.tsx`
41. `(app)/community-solar/page.tsx` -- Community solar (server component)
42. `(app)/community-solar/loading.tsx`
43. `(app)/community-solar/error.tsx`
44. `(app)/connections/page.tsx` -- Connections page (server component)
45. `(app)/connections/loading.tsx`
46. `(app)/connections/error.tsx`
47. `(app)/gas-rates/page.tsx` -- Gas rates (server component)
48. `(app)/gas-rates/loading.tsx`
49. `(app)/gas-rates/error.tsx`
50. `(app)/heating-oil/page.tsx` -- Heating oil (server component)
51. `(app)/heating-oil/loading.tsx`
52. `(app)/heating-oil/error.tsx`
53. `(app)/onboarding/page.tsx` -- Onboarding wizard ('use client')
54. `(app)/onboarding/loading.tsx`
55. `(app)/onboarding/error.tsx`
56. `(app)/optimize/page.tsx` -- Schedule optimization ('use client')
57. `(app)/optimize/loading.tsx`
58. `(app)/optimize/error.tsx`
59. `(app)/prices/page.tsx` -- Electricity prices (server component)
60. `(app)/prices/loading.tsx`
61. `(app)/prices/error.tsx`
62. `(app)/propane/page.tsx` -- Propane prices (server component)
63. `(app)/propane/loading.tsx`
64. `(app)/propane/error.tsx`
65. `(app)/settings/page.tsx` -- Settings ('use client')
66. `(app)/settings/loading.tsx`
67. `(app)/settings/error.tsx`
68. `(app)/suppliers/page.tsx` -- Suppliers (server component)
69. `(app)/suppliers/loading.tsx`
70. `(app)/suppliers/error.tsx`
71. `(app)/water/page.tsx` -- Water rates (server component)
72. `(app)/water/loading.tsx`
73. `(app)/water/error.tsx`

### `(auth)` route group
74. `(auth)/layout.tsx` -- Auth layout (pass-through fragment)
75. `(auth)/auth/login/page.tsx` -- Login ('use client')
76. `(auth)/auth/login/loading.tsx`
77. `(auth)/auth/login/error.tsx`
78. `(auth)/auth/signup/page.tsx` -- Signup ('use client')
79. `(auth)/auth/signup/loading.tsx`
80. `(auth)/auth/signup/error.tsx`
81. `(auth)/auth/callback/page.tsx` -- OAuth callback ('use client')
82. `(auth)/auth/forgot-password/page.tsx` -- Forgot password ('use client')
83. `(auth)/auth/reset-password/page.tsx` -- Reset password ('use client')
84. `(auth)/auth/verify-email/page.tsx` -- Email verification ('use client')

### `(dev)` route group
85. `(dev)/layout.tsx` -- Dev layout (server component, gates on NODE_ENV)
86. `(dev)/architecture/page.tsx` -- Architecture diagrams ('use client')

### Supporting files
87. `frontend/middleware.ts` -- CSP nonce + route protection
88. `frontend/components/auth/AuthGuard.tsx` -- Client-side auth gate

---

## P0 -- Critical (Fix Immediately)

### P0-01: `export const dynamic` is invalid in 'use client' components

**Severity**: P0 -- Build/runtime correctness
**Files**:
- `frontend/app/(auth)/auth/login/page.tsx` (line 9)
- `frontend/app/(auth)/auth/signup/page.tsx` (line 9)
- `frontend/app/(auth)/auth/callback/page.tsx` (line 14)
- `frontend/app/(auth)/auth/forgot-password/page.tsx` (line 17)
- `frontend/app/(auth)/auth/reset-password/page.tsx` (line 20)
- `frontend/app/(auth)/auth/verify-email/page.tsx` (line 21)

**Problem**: `export const dynamic = 'force-dynamic'` is a Next.js Route Segment Config option. In Next.js 16, these config exports are only valid in server components (page.tsx without 'use client'), layout.tsx, or route.ts files. When placed in a client component marked with `'use client'`, these exports are silently ignored by the framework. The code suggests the developer believed this would prevent static generation of these pages, but it has no effect.

**Impact**: These auth pages may be incorrectly statically optimized at build time, or they may just happen to work because they contain hooks (`useState`, `useEffect`, `useSearchParams`) which force client rendering anyway. The primary concern is that the intent is not enforced -- if Next.js were to ever partially pre-render the server shell of these pages, the `force-dynamic` annotation would not apply.

**Fix**: Either:
1. Remove the `export const dynamic` lines from all 6 client component pages (they are no-ops), OR
2. Restructure these pages so the page.tsx is a server component that exports `dynamic` and wraps a client child component (similar to how `reset-password/page.tsx` already properly uses Suspense wrapping for `useSearchParams`)

---

### P0-02: Sitemap includes authenticated route `/dashboard`

**Severity**: P0 -- SEO / user experience
**File**: `frontend/app/sitemap.ts` (lines 21-26)

**Problem**: The sitemap includes `/dashboard` (priority 0.9, changeFrequency 'daily') which is behind authentication. When search engine crawlers attempt to visit this URL, they will be redirected to `/auth/login` by the middleware. This causes:
1. Crawl budget waste on redirect chains
2. Potential indexing of the login page under the `/dashboard` canonical URL
3. Google Search Console warnings about redirected URLs in the sitemap

**Fix**: Remove `/dashboard` from the `staticPages` array. Only public routes should appear in the sitemap.

---

### P0-03: Missing `fallback` prop on Suspense boundary in dashboard

**Severity**: P0 -- User experience / layout shift
**File**: `frontend/app/(app)/dashboard/page.tsx` (line 10)

**Problem**: The `<Suspense>` boundary wrapping `<DashboardTabs />` has no `fallback` prop:
```tsx
<Suspense>
  <DashboardTabs />
</Suspense>
```

Without a fallback, React renders nothing while the suspended content loads. This creates an empty white flash between the loading.tsx skeleton completing and the component actually mounting. The dashboard has a `loading.tsx` that provides a full-page skeleton, but the `<Suspense>` boundary operates independently -- it applies to React.lazy or data fetching suspense within `DashboardTabs` itself, not the route-level loading state.

**Fix**: Add a fallback that matches the loading skeleton:
```tsx
<Suspense fallback={<DashboardLoading />}>
  <DashboardTabs />
</Suspense>
```
Or import and reuse the skeleton from `dashboard/loading.tsx`.

---

## P1 -- High (Fix This Sprint)

### P1-01: 5 'use client' pages cannot export metadata -- no SEO for these routes

**Severity**: P1 -- SEO gap
**Files**:
- `frontend/app/(app)/beta-signup/page.tsx` (line 1 -- 'use client')
- `frontend/app/(app)/community/page.tsx` (line 1 -- 'use client')
- `frontend/app/(app)/onboarding/page.tsx` (line 1 -- 'use client')
- `frontend/app/(app)/optimize/page.tsx` (line 1 -- 'use client')
- `frontend/app/(app)/settings/page.tsx` (line 1 -- 'use client')

**Problem**: Client components cannot export `metadata` or `generateMetadata`. These 5 pages have no page-level metadata, so the browser tab shows only the root layout's default title ("RateShift - Save on Your Utility Bills") instead of a page-specific title. While these are authenticated routes (less SEO-critical), proper titles are important for:
1. Tab identification when users have multiple tabs open
2. Browser history readability
3. Accessibility -- screen readers announce page titles

All other `(app)` pages (alerts, analytics, assistant, connections, etc.) are server components that properly export metadata.

**Fix**: Refactor each page to be a thin server component wrapper that exports metadata and renders the client component as a child. Example for `settings`:
```tsx
// page.tsx (server component)
import SettingsContent from './SettingsContent'
export const metadata = { title: 'Settings | RateShift' }
export default function SettingsPage() {
  return <SettingsContent />
}
```

---

### P1-02: Missing loading.tsx and error.tsx for auth sub-routes

**Severity**: P1 -- User experience gap
**Directories missing both loading.tsx and error.tsx**:
- `frontend/app/(auth)/auth/forgot-password/` -- no loading.tsx, no error.tsx
- `frontend/app/(auth)/auth/reset-password/` -- no loading.tsx, no error.tsx
- `frontend/app/(auth)/auth/verify-email/` -- no loading.tsx, no error.tsx
- `frontend/app/(auth)/auth/callback/` -- no loading.tsx, no error.tsx

**Directories that DO have them**:
- `frontend/app/(auth)/auth/login/` -- has both loading.tsx and error.tsx
- `frontend/app/(auth)/auth/signup/` -- has both loading.tsx and error.tsx

**Problem**: The forgot-password, reset-password, verify-email, and callback pages have no route-level loading or error boundaries. If these pages fail to load (network error, chunk loading failure), the error bubbles up to the root `error.tsx` boundary, which renders the generic full-page error fallback without auth-page-appropriate styling or messaging. The verify-email and reset-password pages do have inline Suspense boundaries for `useSearchParams()`, which partially mitigates the loading case.

**Fix**: Add `loading.tsx` and `error.tsx` files to each of the 4 missing directories, following the same pattern as `login/loading.tsx` and `login/error.tsx`.

---

### P1-03: Missing loading.tsx and error.tsx for public pages

**Severity**: P1 -- User experience gap
**Directories missing both loading.tsx and error.tsx**:
- `frontend/app/pricing/` -- no loading.tsx, no error.tsx
- `frontend/app/privacy/` -- no loading.tsx, no error.tsx
- `frontend/app/terms/` -- no loading.tsx, no error.tsx
- `frontend/app/rates/[state]/[utility]/` -- no loading.tsx, no error.tsx

**Problem**: These public-facing pages have no route-level loading or error boundaries. This is most impactful for:
1. `rates/[state]/[utility]/page.tsx` -- this is an async server component that performs a `fetch()` to the backend (line 71). If that fetch fails or is slow, there is no loading skeleton and errors bubble to the root error boundary.
2. The pricing, privacy, and terms pages are static server components that are unlikely to error, but best practice requires error boundaries for chunk loading failures.

**Fix**: Add `loading.tsx` and `error.tsx` to each directory. The rates page is highest priority since it performs server-side data fetching.

---

### P1-04: `not-found.tsx` links to authenticated route

**Severity**: P1 -- User experience
**File**: `frontend/app/not-found.tsx` (lines 11-14)

**Problem**: The 404 page's only action is a link to `/dashboard`:
```tsx
<Link href="/dashboard" className="...">
  Back to Dashboard
</Link>
```

Unauthenticated users who hit a 404 (e.g., from a stale bookmark or typo) are presented with a link that will redirect them through the login flow. This is confusing -- users who have never signed up see "Back to Dashboard" as their only option.

**Fix**: Provide two links -- one to the homepage (for unauthenticated users) and one to the dashboard. Or link to `/` as the primary CTA ("Back to Home") since the middleware will handle authenticated users appropriately.

---

### P1-05: Middleware protects routes not present in file system

**Severity**: P1 -- Configuration drift
**File**: `frontend/middleware.ts` (lines 16-37)

**Problem**: The `protectedPaths` array includes routes that do not exist as pages in the `frontend/app/(app)/` directory:
- `/natural-gas` -- no corresponding `(app)/natural-gas/` directory (the actual page is at `/gas-rates`)
- `/solar` -- no corresponding `(app)/solar/` directory
- `/forecast` -- no corresponding `(app)/forecast/` directory

These phantom routes in the middleware config mean:
1. If a user visits `/natural-gas`, the middleware redirects to `/auth/login`, but after login the callback redirects to `/natural-gas` which will 404
2. The middleware does unnecessary work checking paths that can never match real pages

**Fix**: Remove `/natural-gas`, `/solar`, and `/forecast` from the `protectedPaths` array unless these pages are planned and forthcoming.

---

### P1-06: AuthGuard + middleware create double-redirect for unauthenticated users

**Severity**: P1 -- Architecture redundancy / potential race condition
**Files**:
- `frontend/middleware.ts` (lines 84-91)
- `frontend/components/auth/AuthGuard.tsx` (lines 24-29)

**Problem**: Authentication is enforced in two layers:
1. **Middleware** (server-side, line 85): Checks for `better-auth.session_token` cookie and redirects to `/auth/login?callbackUrl=...`
2. **AuthGuard** (client-side, line 25): Checks `useAuth().isAuthenticated` and redirects via `router.replace('/auth/login?callbackUrl=...')`

These use different detection mechanisms:
- Middleware checks for cookie existence (a session token cookie present does NOT guarantee a valid, non-expired session)
- AuthGuard checks the actual auth state via the Better Auth client

This means: A user with an expired session token cookie will pass the middleware check but be redirected by AuthGuard, causing a flash of the loading spinner before redirect. Conversely, if cookies are somehow cleared client-side but the auth state is cached, the middleware will redirect before AuthGuard can render.

The dual-layer approach is not inherently wrong (defense in depth), but the inconsistent detection methods can cause confusing UX edge cases.

**Fix**: Document the intentional dual-layer approach. Consider making the middleware the primary gate (fast server redirect) and AuthGuard the fallback (catches expired sessions). Alternatively, use Next.js's `getServerSession` pattern in the middleware for a more authoritative check.

---

### P1-07: `(dev)/architecture/page.tsx` creates redundant QueryClient

**Severity**: P1 -- Potential data isolation bug
**File**: `frontend/app/(dev)/architecture/page.tsx` (lines 9, 60-65)

**Problem**: The architecture page creates its own `QueryClient` at module scope:
```tsx
const queryClient = new QueryClient()

export default function ArchitecturePage() {
  return (
    <QueryClientProvider client={queryClient}>
      <ArchitectureContent />
    </QueryClientProvider>
  )
}
```

Issues:
1. The `queryClient` is created at module scope, meaning it persists across all renders and is shared across all users in a server environment (though this is a client component, so it's per-tab).
2. The root layout already wraps the entire app in `<QueryProvider>` (root layout.tsx line 51). This nested `QueryClientProvider` shadows the parent, creating an isolated cache that cannot share data with the rest of the app.
3. Module-level `new QueryClient()` in a client component is a known anti-pattern -- it should be created inside a component (e.g., via `useState` or `useRef`) to ensure one instance per mount.

**Fix**: Remove the local `QueryClientProvider` wrapper and use the existing root-level query client. If isolation is intentional (dev-only tool), move the `QueryClient` creation inside the component.

---

## P2 -- Medium (Fix Soon)

### P2-01: Design token inconsistency between landing page and public pages

**Severity**: P2 -- Visual consistency
**Files**:
- `frontend/app/page.tsx` -- uses `text-primary-600`, `bg-primary-600`, `text-primary-foreground` (design system tokens)
- `frontend/app/pricing/page.tsx` -- uses `text-blue-600`, `bg-blue-600`, `text-white` (hardcoded Tailwind colors)
- `frontend/app/privacy/page.tsx` -- uses `text-blue-600` (line 16, hardcoded)
- `frontend/app/terms/page.tsx` -- uses `text-blue-600` (line 16, hardcoded)

**Problem**: The landing page uses the custom `primary-600` design token (mapped to blue-500 via CSS custom properties in globals.css), while the pricing, privacy, and terms pages use Tailwind's raw `blue-600` class. This creates:
1. Inconsistent brand colors if the primary color is ever changed
2. The values are close but not identical (`--color-primary: 59 130 246` = blue-500, while `text-blue-600` = `rgb(37 99 235)`)
3. Buttons on the landing page: `bg-primary-600 text-primary-foreground` vs pricing page: `bg-blue-600 text-white`

**Fix**: Replace all `text-blue-600`, `bg-blue-600`, `bg-blue-100`, `text-blue-700` in pricing/privacy/terms pages with the corresponding `primary-*` design tokens.

---

### P2-02: Duplicated pricing tier data

**Severity**: P2 -- Maintainability
**Files**:
- `frontend/app/page.tsx` (lines 37-82) -- defines 3 tiers with features
- `frontend/app/pricing/page.tsx` (lines 10-68) -- defines 3 tiers with different feature lists

**Problem**: Pricing tier data is defined independently in two places with slightly different feature lists:
- Landing page Free tier: `['Basic price view', '1 price alert', 'Manual scheduling', 'Local supplier comparison']`
- Pricing page Free tier: `['Real-time electricity prices', '1 price alert', 'Manual schedule optimization', 'Local supplier comparison', 'Basic dashboard']`

The Pro and Business tiers also differ. This means a pricing change requires updating two files and risks inconsistency.

**Fix**: Extract pricing tier data into a shared module (e.g., `lib/constants/pricing.ts`) and import it in both pages.

---

### P2-03: `(auth)/layout.tsx` is a no-op wrapper

**Severity**: P2 -- Code clarity
**File**: `frontend/app/(auth)/layout.tsx` (lines 8-14)

**Problem**: The auth layout renders nothing but a fragment wrapper:
```tsx
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
```

This is technically harmless (Next.js requires a layout for route groups), but the file adds no value beyond the implicit layout that Next.js would generate. The comment explains the intent (no sidebar/app chrome), which is good documentation.

**Fix**: This is acceptable as-is since it documents the architectural decision. Optionally, add a shared auth-page container (centered layout, brand header) here to reduce duplication across the 6 auth pages that each independently render `min-h-screen bg-gray-50 flex flex-col items-center justify-center`.

---

### P2-04: Large 'use client' page components should be extracted

**Severity**: P2 -- Maintainability / bundle size
**Files**:
- `frontend/app/(app)/settings/page.tsx` -- ~700 lines, 'use client', 13 imports from lucide-react
- `frontend/app/(app)/optimize/page.tsx` -- ~612 lines, 'use client', 12 imports from lucide-react

**Problem**: These pages contain hundreds of lines of UI logic, state management, and API calls directly in the page file. This prevents:
1. Server-side metadata exports (see P1-01)
2. Code splitting -- the entire page must be loaded as one chunk
3. Independent testing of sub-sections

Other pages in the codebase demonstrate the better pattern: `alerts/page.tsx` is 7 lines and delegates to `<AlertsContent />`, `suppliers/page.tsx` is 7 lines and delegates to `<SuppliersContent />`.

**Fix**: Extract the content of settings/page.tsx into `components/settings/SettingsContent.tsx` and optimize/page.tsx into `components/optimize/OptimizeContent.tsx`, then make the page.tsx files thin server component wrappers.

---

### P2-05: Inconsistent ErrorBoundary usage across server component pages

**Severity**: P2 -- Consistency
**Files with inline ErrorBoundary wrapping**:
- `frontend/app/(app)/dashboard/page.tsx` -- wraps in `<ErrorBoundary><Suspense>...</Suspense></ErrorBoundary>`
- `frontend/app/(app)/analytics/page.tsx` -- wraps `<AnalyticsDashboard />` in `<ErrorBoundary>`
- `frontend/app/(app)/assistant/page.tsx` -- wraps `<AgentChat />` in `<ErrorBoundary>`
- `frontend/app/(app)/prices/page.tsx` -- wraps `<PricesContent />` in `<ErrorBoundary>`

**Files without inline ErrorBoundary (rely only on error.tsx)**:
- `frontend/app/(app)/alerts/page.tsx` -- bare `<AlertsContent />`
- `frontend/app/(app)/suppliers/page.tsx` -- bare `<SuppliersContent />`
- `frontend/app/(app)/connections/page.tsx` -- bare `<ConnectionsOverview />`
- `frontend/app/(app)/gas-rates/page.tsx` -- bare `<GasRatesContent />`
- `frontend/app/(app)/heating-oil/page.tsx` -- bare `<HeatingOilDashboard />`
- `frontend/app/(app)/water/page.tsx` -- bare `<WaterDashboard />`
- `frontend/app/(app)/propane/page.tsx` -- bare `<PropaneDashboard />`
- `frontend/app/(app)/community-solar/page.tsx` -- bare `<CommunitySolarContent />`

**Problem**: There is no consistent pattern for when to use inline `<ErrorBoundary>` in the page component vs. relying solely on the `error.tsx` file. Both approaches work, but the inconsistency suggests ad-hoc decisions rather than a deliberate architecture. Additionally, the `(app)/layout.tsx` already wraps all children in an `<ErrorBoundary>`, creating triple-layered error handling for pages like dashboard (layout ErrorBoundary > page ErrorBoundary > error.tsx).

**Fix**: Establish a convention. Recommendation: rely on `error.tsx` for page-level errors (this is the Next.js-idiomatic approach) and use inline `<ErrorBoundary>` only for sub-sections of a page where you want partial error isolation (e.g., a chart failing should not crash the entire page). Remove the page-level inline `<ErrorBoundary>` wrappers from dashboard, analytics, assistant, and prices pages.

---

### P2-06: Auth pages duplicate full-page layout boilerplate

**Severity**: P2 -- DRY violation
**Files**:
- `frontend/app/(auth)/auth/login/page.tsx` -- `min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8`
- `frontend/app/(auth)/auth/signup/page.tsx` -- identical layout wrapper
- `frontend/app/(auth)/auth/forgot-password/page.tsx` -- `min-h-screen ... items-center justify-center bg-gray-50 p-4`
- `frontend/app/(auth)/auth/reset-password/page.tsx` -- identical layout wrapper
- `frontend/app/(auth)/auth/verify-email/page.tsx` -- identical layout wrapper
- `frontend/app/(auth)/auth/callback/page.tsx` -- `min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4`

**Problem**: Every auth page independently renders its own full-page centered layout with `min-h-screen bg-gray-50`. The `(auth)/layout.tsx` is a no-op fragment that could instead provide this shared wrapper.

**Fix**: Move the common layout into `(auth)/layout.tsx`:
```tsx
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-4">
      {children}
    </div>
  )
}
```
Then simplify each auth page to render only its card content.

---

### P2-07: `robots.ts` disallows only a subset of authenticated routes

**Severity**: P2 -- SEO configuration gap
**File**: `frontend/app/robots.ts` (lines 8-12)

**Problem**: The robots.txt configuration disallows `/api/`, `/dashboard/`, `/settings/`, `/onboarding/` but does not disallow the other 13 authenticated routes: `/prices/`, `/suppliers/`, `/connections/`, `/optimize/`, `/alerts/`, `/assistant/`, `/community/`, `/water/`, `/propane/`, `/heating-oil/`, `/gas-rates/`, `/community-solar/`, `/analytics/`, `/beta-signup/`.

While the middleware redirects unauthenticated requests (including bots) to `/auth/login`, explicit disallow directives are better practice because:
1. They prevent crawl budget waste on redirect chains
2. They explicitly communicate to search engines which pages are not indexable
3. Not all crawlers respect redirects the same way

**Fix**: Add all authenticated routes to the `disallow` array, or use a wildcard pattern that covers the `(app)` route group.

---

### P2-08: JSON-LD `dangerouslySetInnerHTML` in rate pages

**Severity**: P2 -- Security (mitigated but worth noting)
**File**: `frontend/app/rates/[state]/[utility]/page.tsx` (lines 109-112)

**Problem**: The JSON-LD structured data is rendered using `dangerouslySetInnerHTML`:
```tsx
<script
  type="application/ld+json"
  dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
/>
```

The `jsonLd` object is constructed from `stateName` and `utilityInfo.label` which come from hardcoded lookup maps (`US_STATES`, `UTILITY_TYPES`), so there is no user-controlled input that could lead to XSS. However, `JSON.stringify` does not escape `</script>` sequences -- if any value contained `</script>`, it could break out of the script tag.

**Impact**: Low in this case since all values come from developer-controlled constants. But this is a fragile pattern.

**Fix**: Use a safe JSON serialization that escapes `</script>` and `<!--`:
```tsx
dangerouslySetInnerHTML={{
  __html: JSON.stringify(jsonLd).replace(/</g, '\\u003c')
}}
```

---

## P3 -- Low / Housekeeping

### P3-01: Duplicate nav and footer in public pages

**Severity**: P3 -- DRY / maintainability
**Files**:
- `frontend/app/page.tsx` (lines 88-109, 212-229) -- inline nav + footer
- `frontend/app/pricing/page.tsx` (lines 74-92, 193-206) -- inline nav + footer
- `frontend/app/privacy/page.tsx` (lines 13-20) -- inline nav (simplified)
- `frontend/app/terms/page.tsx` (lines 13-20) -- inline nav (simplified)

**Problem**: Each public page renders its own navigation and footer inline. The landing page and pricing page have full navs with different link sets; privacy and terms have simplified navs. Changes to the brand name, logo, or nav structure require updating 4 files.

**Fix**: Extract a `PublicNav` and `PublicFooter` component. Alternatively, create a `(public)` route group with a shared layout.

---

### P3-02: `global-error.tsx` uses hardcoded `#2563eb` instead of design tokens

**Severity**: P3 -- Consistency
**File**: `frontend/app/global-error.tsx` (line 42)

**Problem**: The global error boundary uses inline styles with hardcoded color `#2563eb` for the "Try again" button. This is intentionally correct -- `global-error.tsx` renders its own `<html><body>` and cannot rely on CSS custom properties from `globals.css` since those might have failed to load. This is a known trade-off of the global error boundary pattern.

**Note**: No fix needed. This is documented for completeness. The inline styles approach is the correct pattern for `global-error.tsx`.

---

### P3-03: `manifest.ts` `start_url` points to authenticated route

**Severity**: P3 -- PWA behavior
**File**: `frontend/app/manifest.ts` (line 9)

**Problem**: The PWA manifest's `start_url` is `/dashboard`, which requires authentication. When a user opens the PWA, they will be redirected to `/auth/login` first if their session has expired. While this is common for app-like PWAs, it creates a poor first-launch experience.

**Fix**: Acceptable as-is since the PWA is intended for returning users. Optionally set `start_url: '/'` and let the landing page's CTA guide users.

---

### P3-04: `(dev)/layout.tsx` uses `notFound()` for production guard

**Severity**: P3 -- DX improvement
**File**: `frontend/app/(dev)/layout.tsx` (lines 5-6)

**Problem**: The dev layout returns a 404 in production:
```tsx
if (process.env.NODE_ENV !== 'development') {
  notFound()
}
```

This is correctly blocking the routes in production. However, the middleware also separately blocks `/architecture` (middleware.ts line 65-69):
```tsx
if (pathname.startsWith('/architecture') && process.env.NODE_ENV !== 'development') {
  const response = NextResponse.rewrite(new URL('/404', request.url))
```

This creates a double-guard with slightly different behavior (middleware rewrites to 404, layout calls `notFound()`). Only the middleware guard runs in production since it intercepts before the layout renders.

**Fix**: Remove one guard or the other. The middleware guard is sufficient; the layout guard is defense-in-depth but adds maintenance surface.

---

### P3-05: `community/page.tsx` uses inline string utility formatting

**Severity**: P3 -- Code quality
**File**: `frontend/app/(app)/community/page.tsx` (line 44)

**Problem**: The utility type label formatting uses an inline regex chain:
```tsx
{ut.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
```

This same transformation is likely needed elsewhere in the app. It should be a shared utility function.

**Fix**: Extract to a shared formatting function in `lib/utils/format.ts` (e.g., `formatUtilityLabel()`).

---

### P3-06: `onboarding/page.tsx` mutates without error feedback

**Severity**: P3 -- Edge case UX
**File**: `frontend/app/(app)/onboarding/page.tsx` (lines 22-29)

**Problem**: The auto-fix mutation on line 23 catches errors and silently resets the redirect flag:
```tsx
updateProfile.mutateAsync({ onboarding_completed: true })
  .then(() => router.replace('/dashboard'))
  .catch(() => {
    redirectedRef.current = false
  })
```

If the auto-fix fails, the user sees the onboarding wizard again with no indication that an auto-fix was attempted and failed. This is acceptable behavior (the wizard is still functional), but a toast notification would improve transparency.

---

### P3-07: Inconsistent metadata format across pages

**Severity**: P3 -- Consistency
**Files**:
- `frontend/app/(app)/assistant/page.tsx` -- uses em dash: `title: 'AI Assistant \u2014 RateShift'`
- All other pages -- use pipe: `title: 'Dashboard | RateShift'`
- Root layout metadata template: `template: '%s | RateShift'`

**Problem**: The assistant page uses an em dash separator while all other pages use a pipe separator. Additionally, pages that export `title: 'Dashboard | RateShift'` manually include " | RateShift" when the root layout's `template: '%s | RateShift'` would add it automatically. This means the actual browser title for these pages is "Dashboard | RateShift | RateShift".

**Fix**: Pages should export just the page name (e.g., `title: 'Dashboard'`) and let the root layout template append " | RateShift". Or use the object form: `title: { absolute: 'Dashboard | RateShift' }` to override the template.

---

### P3-08: Middleware matcher excludes `OneSignalSDKWorker.js` by filename

**Severity**: P3 -- Fragility
**File**: `frontend/middleware.ts` (line 115)

**Problem**: The middleware matcher regex excludes `OneSignalSDKWorker.js` by exact filename. If OneSignal updates their SDK worker filename, the middleware would start processing it and inject CSP headers that could break the service worker.

**Fix**: Acceptable as-is since OneSignal's worker filename is a stable convention. Document the exclusion.

---

## Files With No Issues Found

The following files were reviewed and found to be well-structured, following Next.js App Router best practices, with no notable issues:

| File | Notes |
|------|-------|
| `frontend/app/layout.tsx` | Excellent: async server component, proper nonce handling, clean provider hierarchy |
| `frontend/app/error.tsx` | Correct: 'use client', proper error prop usage, delegates to PageErrorFallback |
| `frontend/app/global-error.tsx` | Correct: renders own html/body, inline styles (intentional), shows error digest |
| `frontend/app/globals.css` | Well-organized design tokens, proper light/dark mode preparation |
| `frontend/app/icon.tsx` | Correct ImageResponse usage with proper size/contentType exports |
| `frontend/app/apple-icon.tsx` | Correct ImageResponse usage |
| `frontend/app/rates/[state]/[utility]/page.tsx` | Excellent: generateStaticParams, generateMetadata, ISR, proper notFound(), JSON-LD, server-side fetch with timeout |
| `frontend/app/api/auth/[...all]/route.ts` | Good: lazy initialization, 5xx error logging, proper dynamic export |
| `frontend/app/api/checkout/route.ts` | Good: auth header validation, CRLF injection check, server-side URL construction, error sanitization |
| `frontend/app/api/pwa-icon/route.tsx` | Good: size validation via allowlist |
| `frontend/app/(app)/layout.tsx` | Good: AuthGuard wrapper, skip-to-content link, sidebar, ErrorBoundary, FeedbackWidget |
| `frontend/app/(app)/error.tsx` | Correct route group error boundary |
| `frontend/app/(app)/alerts/page.tsx` | Clean thin server component wrapper with metadata |
| `frontend/app/(app)/connections/page.tsx` | Clean server component with proper metadata object |
| `frontend/app/(app)/gas-rates/page.tsx` | Clean thin wrapper |
| `frontend/app/(app)/heating-oil/page.tsx` | Clean server component with header section |
| `frontend/app/(app)/water/page.tsx` | Clean server component |
| `frontend/app/(app)/propane/page.tsx` | Clean server component |
| `frontend/app/(app)/community-solar/page.tsx` | Clean thin wrapper |
| `frontend/app/(app)/suppliers/page.tsx` | Clean thin wrapper |
| `frontend/app/(auth)/auth/reset-password/page.tsx` | Good: proper Suspense wrapping for useSearchParams, token validation, min password length check |
| `frontend/app/(auth)/auth/verify-email/page.tsx` | Good: dual-mode (token verify + resend), Suspense wrapping, ref guard against double-verify |
| `frontend/app/(auth)/auth/forgot-password/page.tsx` | Good: email validation, security-safe messaging ("if an account exists"), proper loading state |
| `frontend/app/(auth)/auth/callback/page.tsx` | Good: timeout fallback link, proper redirect pattern |
| `frontend/app/(dev)/layout.tsx` | Correct: production guard with notFound() |
| `frontend/middleware.ts` | Solid: CSP nonce generation, cookie-based auth check (both prefixed and non-prefixed), proper matcher config |
| `frontend/components/auth/AuthGuard.tsx` | Clean: loading spinner with sr-only text, callbackUrl preservation, null render during redirect |
| All 17 `(app)/*/loading.tsx` files | Consistent skeleton loading patterns |
| All 18 `(app)/*/error.tsx` files | Consistent error boundary pattern |
| `frontend/app/(auth)/auth/login/loading.tsx` | Proper skeleton |
| `frontend/app/(auth)/auth/signup/loading.tsx` | Proper skeleton |
| `frontend/app/(auth)/auth/login/error.tsx` | Proper error boundary |
| `frontend/app/(auth)/auth/signup/error.tsx` | Proper error boundary |

---

## Summary

### Totals
- **Files reviewed**: 88 (all files in `frontend/app/` plus middleware.ts and AuthGuard.tsx)
- **P0 Critical**: 3 findings
- **P1 High**: 7 findings
- **P2 Medium**: 8 findings
- **P3 Low**: 8 findings
- **Total findings**: 26

### Architecture Assessment

**Strengths**:
- The `(app)` route group is exceptionally well-organized: 17 page directories each have a complete `page.tsx` + `loading.tsx` + `error.tsx` triplet
- Server component / client component boundary is generally well-drawn -- most pages are thin server component wrappers that delegate to client components
- The `rates/[state]/[utility]/` dynamic route is excellent: proper `generateStaticParams`, `generateMetadata`, ISR with `revalidate`, server-side data fetching, JSON-LD structured data
- CSP nonce generation in middleware with header-based propagation to server components is a strong security pattern
- The root layout provider hierarchy (QueryProvider > AuthProvider > ToastProvider) is clean and properly ordered
- API routes demonstrate good security practices (auth header validation, CRLF injection check, error sanitization)
- The `global-error.tsx` correctly uses inline styles since CSS may not be available

**Primary Concerns**:
1. **Invalid `export const dynamic` in 6 client components** (P0-01) -- these are no-ops and should be removed or restructured
2. **5 client-component pages lack metadata** (P1-01) -- reduces tab title clarity and accessibility
3. **Inconsistent patterns** across pages (ErrorBoundary usage, metadata format, design tokens) suggest the codebase grew organically and would benefit from a consistency pass
4. **Missing loading/error boundaries** for 8 routes (4 auth sub-routes + 4 public pages) leaves gaps in the error handling story
5. **Middleware/AuthGuard dual-auth** (P1-06) is not wrong but creates subtle edge cases that should be documented

### Recommended Priority Order
1. Fix P0-01 (remove invalid `dynamic` exports) -- 10 min, no risk
2. Fix P0-02 (remove `/dashboard` from sitemap) -- 2 min, no risk
3. Fix P0-03 (add Suspense fallback to dashboard) -- 5 min, no risk
4. Fix P1-01 + P2-04 simultaneously (extract settings/optimize/community/beta-signup/onboarding to server wrapper + client content pattern) -- 2-3 hours
5. Fix P1-03 (add loading/error files for public pages) -- 30 min
6. Fix P1-02 (add loading/error files for auth sub-routes) -- 30 min
7. Fix P1-05 (clean up phantom middleware routes) -- 5 min
8. Address P2 findings as part of regular development
