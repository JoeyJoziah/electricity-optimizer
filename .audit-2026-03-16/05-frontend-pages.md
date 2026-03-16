# Frontend Pages Audit — RateShift
**Date**: 2026-03-16
**Auditor**: nextjs-developer agent
**Scope**: `frontend/app/**` pages, layouts, loading/error boundaries, `frontend/lib/api/`, `frontend/lib/hooks/`

---

## Summary

| Severity | Count |
|----------|-------|
| P0 (Critical) | 3 |
| P1 (High) | 9 |
| P2 (Medium) | 14 |
| P3 (Low) | 10 |
| **Total** | **36** |

---

## P0 — Critical (production correctness / security at risk)

### P0-01: `optimize/page.tsx` is `'use client'` but has no `export const metadata` and is a full client component with no server fallback

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/optimize/page.tsx`
**Line**: 1 (`'use client'`)

**Description**: The entire optimize page is a single monolithic client component (542 lines). Because the file is marked `'use client'`, `export const metadata` at the module level is silently ignored by Next.js — the metadata object is not exported and the page has no SEO title/description. This is distinct from other pages that correctly export metadata from a server component wrapper. Additionally, the entire page re-renders on every state change (multiple `useState` hooks) including heavy chart-like components.

**Fix**:
```tsx
// app/(app)/optimize/page.tsx  — server component wrapper
import { Suspense } from 'react'
import type { Metadata } from 'next'
import OptimizeClient from '@/components/optimize/OptimizeClient'

export const metadata: Metadata = {
  title: 'Load Optimization | RateShift',
  description: 'Schedule appliances during off-peak hours to maximize electricity savings.',
}

export default function OptimizePage() {
  return (
    <Suspense fallback={<OptimizeLoadingFallback />}>
      <OptimizeClient />
    </Suspense>
  )
}
```
Move all client logic into `components/optimize/OptimizeClient.tsx`.

---

### P0-02: `settings/page.tsx` uses raw `fetch('/api/v1/compliance/gdpr/export')` bypassing `apiClient` — no auth headers, no circuit breaker, no error normalization

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/settings/page.tsx`
**Lines**: 138, 161

**Description**: The GDPR export (`handleExportData`) and account-delete (`handleDeleteAccount`) handlers call `fetch('/api/v1/compliance/gdpr/export')` and `fetch('/api/v1/compliance/gdpr/delete')` directly. These calls skip the `apiClient` wrapper entirely, meaning: (1) the circuit breaker is not consulted — if the CF Worker gateway is down, requests will silently fail or hit the wrong origin; (2) no automatic retry on 5xx; (3) 401 handling is custom and inconsistent (no redirect-loop guard); (4) response body is not normalized through `handleResponse`. The delete path calls `response.ok` check but does nothing with a non-200 body on failure beyond throwing a generic Error.

**Fix**: Replace both raw `fetch` calls with `apiClient.get` / `apiClient.delete`:
```tsx
// Export
const data = await apiClient.get<Record<string, unknown>>('/compliance/gdpr/export')

// Delete
await apiClient.delete<{ message: string }>('/compliance/gdpr/delete')
```

---

### P0-03: `middleware.ts` does not protect new Wave 3–5 routes — `analytics`, `community`, `gas-rates`, `heating-oil`, `propane`, `water`, `community-solar`, `assistant` are accessible without a session cookie

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/middleware.ts`
**Lines**: 12, 54–65

**Description**: The `protectedPaths` array and the `matcher` config cover the original Wave 1 routes only:
```ts
const protectedPaths = ['/dashboard', '/prices', '/suppliers', '/connections', '/optimize', '/settings', '/onboarding', '/alerts', '/assistant']
```
`/assistant` is in `protectedPaths` but NOT in the `matcher` config (line 55–66 omits it), so middleware never runs for that path. Routes `/analytics`, `/community`, `/gas-rates`, `/heating-oil`, `/propane`, `/water`, and `/community-solar` are absent from both lists. An unauthenticated user can navigate directly to any of these URLs; Next.js will render the page and the backend will return 401s, but there is no server-side redirect — this leaks UI chrome and triggers the client-side 401 redirect waterfall instead of a clean server redirect.

**Fix**:
```ts
// middleware.ts
const protectedPaths = [
  '/dashboard', '/prices', '/suppliers', '/connections',
  '/optimize', '/settings', '/onboarding', '/alerts',
  '/assistant', '/analytics', '/community', '/gas-rates',
  '/heating-oil', '/propane', '/water', '/community-solar',
]

export const config = {
  matcher: [
    '/architecture/:path*',
    '/dashboard/:path*',
    '/prices/:path*',
    '/suppliers/:path*',
    '/connections/:path*',
    '/optimize/:path*',
    '/settings/:path*',
    '/onboarding/:path*',
    '/alerts/:path*',
    '/assistant/:path*',   // ADD
    '/analytics/:path*',   // ADD
    '/community/:path*',   // ADD
    '/gas-rates/:path*',   // ADD
    '/heating-oil/:path*', // ADD
    '/propane/:path*',     // ADD
    '/water/:path*',       // ADD
    '/community-solar/:path*', // ADD
    '/auth/:path*',
  ],
}
```

---

## P1 — High (functionality broken or significant UX regression)

### P1-01: Nine app pages lack `error.tsx` boundaries — unhandled component errors crash the full app layout

**Files affected** (no `error.tsx` present):
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/gas-rates/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/heating-oil/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/propane/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/water/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/community-solar/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/analytics/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/onboarding/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/beta-signup/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/community/`  *(has loading.tsx but no error.tsx)*

**Description**: When a client component inside these routes throws (e.g., API 500, malformed data, missing env var), Next.js has no route-level error boundary. The error bubbles to the root `app/error.tsx` which wraps the entire shell, causing the sidebar and layout to disappear. The five older routes (dashboard, prices, suppliers, connections, settings) all have `error.tsx` — the newer routes do not follow the same pattern.

**Fix**: Add a minimal `error.tsx` to each directory. Reusable template:
```tsx
// app/(app)/[route]/error.tsx
'use client'
import { Button } from '@/components/ui/button'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="flex h-96 items-center justify-center">
      <div className="text-center">
        <h2 className="text-lg font-semibold text-gray-900">
          Something went wrong
        </h2>
        <p className="mt-2 text-sm text-gray-500">
          {error.message || 'An unexpected error occurred'}
        </p>
        <Button onClick={reset} className="mt-4">Try again</Button>
      </div>
    </div>
  )
}
```

---

### P1-02: Nine app pages lack `loading.tsx` files — route transitions show blank content with no skeleton

**Files affected** (no `loading.tsx` present):
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/gas-rates/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/heating-oil/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/propane/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/water/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/community-solar/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/analytics/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/onboarding/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/beta-signup/`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/settings/` *(has loading.tsx — already covered)*

**Description**: The nine routes listed above do not have `loading.tsx` files. When users navigate to these pages, the sidebar renders immediately but the main content area is blank until the component mounts and data loads. This causes cumulative layout shift (CLS) and poor perceived performance. The existing pages with `loading.tsx` (dashboard, prices, suppliers, connections, optimize, settings, alerts, assistant, community) provide skeleton loaders — consistency requires all routes follow the same pattern.

**Note**: `/settings` has a `loading.tsx` already. The gap is specifically the newer utility pages and onboarding/beta-signup.

**Fix**: Add skeleton `loading.tsx` matching each page's content structure. Example for gas-rates:
```tsx
// app/(app)/gas-rates/loading.tsx
import { Skeleton, ChartSkeleton } from '@/components/ui/skeleton'

export default function GasRatesLoading() {
  return (
    <div className="flex flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-40" />
      </div>
      <div className="p-6 space-y-6">
        <div className="grid gap-4 md:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} variant="rectangular" height={100} />
          ))}
        </div>
        <ChartSkeleton height={320} />
      </div>
    </div>
  )
}
```

---

### P1-03: `dashboard/page.tsx` uses bare `<Suspense>` with no fallback — during streaming, React renders nothing

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/dashboard/page.tsx`
**Line**: 8

**Description**:
```tsx
export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardTabs />
    </Suspense>
  )
}
```
The `<Suspense>` boundary has no `fallback` prop. While the `dashboard/loading.tsx` file handles route-level Suspense (triggered by Next.js before the page renders), if `DashboardTabs` or any child component suspends mid-render (e.g., via `use()`, lazy imports, or a data-fetching Server Component), React will render nothing — a blank white area — instead of the skeleton. The `loading.tsx` only covers the initial navigation, not in-page Suspense.

**Fix**:
```tsx
import { Suspense } from 'react'
import DashboardTabs from '@/components/dashboard/DashboardTabs'
import DashboardLoading from './loading'

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardLoading />}>
      <DashboardTabs />
    </Suspense>
  )
}
```

---

### P1-04: `community/page.tsx` and `analytics/page.tsx` are `'use client'` with missing `export const metadata` — SEO completely broken for these pages

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/community/page.tsx` (line 1: `'use client'`, no metadata export)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/analytics/page.tsx` (line 1 import, no description in metadata)

**Description**: `community/page.tsx` is marked `'use client'` at the file level, which prevents any `export const metadata` on that file from being processed by Next.js. The page has zero metadata — no title, description, Open Graph tags, or Twitter card. This means the page will be titled using the root `%s | RateShift` template with an empty `%s`, rendering as ` | RateShift` in browser tabs. `analytics/page.tsx` has `export const metadata = { title: ... }` but no `description`, which is required for SEO score > 95.

**Fix for community/page.tsx**: Extract client logic to a `CommunityContent` component, keep `page.tsx` as a server component:
```tsx
// app/(app)/community/page.tsx
import type { Metadata } from 'next'
import { Suspense } from 'react'
import CommunityContent from '@/components/community/CommunityContent'

export const metadata: Metadata = {
  title: 'Community',
  description: 'Share electricity savings tips, report rates, and connect with neighbors in your region.',
}

export default function CommunityPage() {
  return (
    <Suspense>
      <CommunityContent />
    </Suspense>
  )
}
```

**Fix for analytics/page.tsx**: Add description:
```tsx
export const metadata: Metadata = {
  title: 'Premium Analytics',
  description: 'Rate forecasts, spend optimization, and data export across all utility types for Pro and Business subscribers.',
}
```

---

### P1-05: `beta-signup/page.tsx` POSTs to `/api/beta-signup` — this route does not exist anywhere in the codebase

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/beta-signup/page.tsx`
**Line**: 27

**Description**:
```tsx
const response = await fetch('/api/beta-signup', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(formData),
})
```
The path `/api/beta-signup` is not defined in `frontend/app/api/` and does not appear to be proxied to the backend. No `route.ts` file exists at `app/api/beta-signup/route.ts`. Every form submission on this page will receive a 404 response, triggering the generic error message. The page also contains a development-era personal email contact (`autodailynewsletterintake@gmail.com`) that should be replaced with a branded RateShift domain email.

**Fix**: Either create the route handler or update the endpoint to use an existing backend endpoint:
```ts
// Option A: Create app/api/beta-signup/route.ts
import { NextRequest, NextResponse } from 'next/server'
export async function POST(request: NextRequest) {
  const data = await request.json()
  // forward to backend or handle directly
  const res = await fetch(`${process.env.BACKEND_URL}/api/v1/beta/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) return NextResponse.json({ error: 'Failed' }, { status: res.status })
  return NextResponse.json({ ok: true })
}
```
Also replace `autodailynewsletterintake@gmail.com` with `support@rateshift.app` or `hello@rateshift.app`.

---

### P1-06: `useAuth.tsx` `initAuth` `useEffect` has no dependency on router but uses `router.replace()` — React strict mode double-invocation can cause duplicate redirects

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/hooks/useAuth.tsx`
**Lines**: 65, 147

**Description**:
```tsx
useEffect(() => {
  const initAuth = async () => { ... }
  initAuth()
}, [])   // empty deps — router is used inside but not listed
```
The `useEffect` dependency array is empty but `router` is captured in closure on line 133 (`router.replace('/onboarding')`). In React Strict Mode (Next.js 14+ dev mode), effects fire twice. The `redirectedRef` pattern in `onboarding/page.tsx` guards against this, but `useAuth`'s `initAuth` has no such guard — two concurrent calls can race on `router.replace`. Additionally, ESLint `react-hooks/exhaustive-deps` would flag this. In production (single invocation), this is lower risk, but it is a latent bug.

**Fix**: Add a `hasInitialized` ref:
```tsx
const hasInitialized = useRef(false)
useEffect(() => {
  if (hasInitialized.current) return
  hasInitialized.current = true
  initAuth()
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [])
```

---

### P1-07: `rates/[state]/[utility]/page.tsx` — `generateMetadata` returns empty `{}` on invalid params instead of calling `notFound()`

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/rates/[state]/[utility]/page.tsx`
**Lines**: 17–23

**Description**:
```tsx
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { state: stateSlug, utility: utilitySlug } = await params
  const stateCode = slugToStateCode(stateSlug)
  const utilityKey = slugToUtilityKey(utilitySlug)

  if (!stateCode || !utilityKey) return {}  // returns empty metadata
  ...
}
```
When an invalid state/utility slug is requested (e.g., `/rates/invalid-state/electricity`), `generateMetadata` returns `{}`. This means the page renders with the root layout's default metadata instead of a proper 404 response. The page component itself correctly calls `notFound()` on line 62, but the metadata function has already returned and Next.js has started building the HTML frame. This can lead to Google indexing 404 pages with misleading metadata.

**Fix**: Call `notFound()` inside `generateMetadata` for invalid params:
```tsx
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { state: stateSlug, utility: utilitySlug } = await params
  const stateCode = slugToStateCode(stateSlug)
  const utilityKey = slugToUtilityKey(utilitySlug)

  if (!stateCode || !utilityKey) notFound()  // throw 404 early
  ...
}
```

---

### P1-08: `settings/page.tsx` uses `window.confirm()` for the account-delete flow — blocked by CSP and unavailable in SSR

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/settings/page.tsx`
**Line**: 156

**Description**:
```tsx
const confirmed = window.confirm(
  'Are you sure you want to delete your account? ...'
)
```
`window.confirm()` is a blocking synchronous call. It (1) can be suppressed or blocked by Content Security Policy directives in some browsers/iframes; (2) does not integrate with the existing `modal.tsx` design system component; (3) is an abrupt UX step for a destructive irreversible operation that warrants a dedicated confirmation modal with explicit typed confirmation; (4) is inaccessible to screen readers in some browsers.

**Fix**: Replace with a modal confirmation using the existing `modal.tsx` component. A minimum confirmation dialog should require the user to type "DELETE" before proceeding.

---

### P1-09: `app/(app)/layout.tsx` has no auth guard — renders sidebar and `FeedbackWidget` for unauthenticated users before middleware redirect completes

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/layout.tsx`

**Description**: The `(app)` layout renders `<Sidebar />` and `<FeedbackWidget />` immediately without checking auth state. While the middleware redirects unauthenticated requests for routes in the matcher, routes NOT in the middleware matcher (e.g., the Wave 3–5 routes identified in P0-03) will render the full authenticated layout shell (sidebar, skip-to-main link, feedback widget) for unauthenticated users. Even after P0-03 is fixed with middleware, there is a brief flash of the authenticated layout on slow connections while the middleware response is in flight, since the client-side router may pre-render the layout.

**Fix**: Add an `AuthGuard` component to the `(app)` layout that checks session state and renders a loading state or redirects:
```tsx
// app/(app)/layout.tsx
import { AuthGuard } from '@/components/auth/AuthGuard'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <AuthGuard>
        <a href="#main-content" className="sr-only focus:not-sr-only ...">
          Skip to main content
        </a>
        <div className="flex min-h-screen">
          <Sidebar />
          <main id="main-content" className="flex-1 lg:pl-64">{children}</main>
        </div>
        <FeedbackWidget />
      </AuthGuard>
    </SidebarProvider>
  )
}
```

---

## P2 — Medium (SEO, consistency, or maintainability issues)

### P2-01: Landing page `app/page.tsx` still uses old brand name "Electricity Optimizer" throughout — brand mismatch with "RateShift"

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/page.tsx`
**Lines**: 93, 217, 225

**Description**: The landing page renders "Electricity Optimizer" in the `<nav>` logo, the footer copyright, and multiple CTAs. The `app/layout.tsx` metadata correctly says "RateShift" but the visible page content contradicts it. This creates a jarring user experience when the page title says "RateShift" but the hero content says "Electricity Optimizer". The same issue exists in `pricing/page.tsx`, `privacy/page.tsx`, and `terms/page.tsx`.

**Affected files**:
- `frontend/app/page.tsx` lines 93, 217, 225
- `frontend/app/pricing/page.tsx` lines 78, 197
- `frontend/app/privacy/page.tsx` lines 17, 84
- `frontend/app/terms/page.tsx` lines 17, 96

**Fix**: Do a codebase-wide replacement of "Electricity Optimizer" with "RateShift" in display strings (not in CLAUDE.md or comments where the old name is intentionally retained).

---

### P2-02: `prices/page.tsx`, `suppliers/page.tsx`, `gas-rates/page.tsx`, `heating-oil/page.tsx`, `propane/page.tsx`, `water/page.tsx`, `community-solar/page.tsx`, `analytics/page.tsx`, `alerts/page.tsx` — metadata uses old brand name

**Files**: Seven `page.tsx` files (listed above)
**Description**: `metadata.title` values use "Electricity Optimizer" instead of "RateShift":
- `prices/page.tsx`: `'Electricity Prices | Electricity Optimizer'`
- `suppliers/page.tsx`: `'Compare Suppliers | Electricity Optimizer'`
- `connections/page.tsx`: `'Connections | Electricity Optimizer'`
- `alerts/page.tsx`: `'Alerts | Electricity Optimizer'`

These differ from newer pages that correctly use "RateShift". The inconsistency means browser tabs and search results show different brand names depending on which page is active.

**Fix**: Standardize all metadata titles to the `'Page Name | RateShift'` format.

---

### P2-03: `prices/page.tsx`, `suppliers/page.tsx`, `gas-rates/page.tsx`, `heating-oil/page.tsx`, `propane/page.tsx`, `water/page.tsx`, `community-solar/page.tsx` — missing `description` in metadata

**Files**: All listed above
**Description**: These pages export `metadata` with only a `title` field:
```tsx
export const metadata = { title: 'Natural Gas Rates | RateShift' }
```
A missing `description` means search engines use the first paragraph of visible text as the description snippet, which is not optimized. Google's recommended snippet length is 120–158 characters. SEO score > 95 requires explicit descriptions on all pages.

**Fix**: Add a `description` to each page's metadata:
```tsx
export const metadata: Metadata = {
  title: 'Natural Gas Rates',
  description: 'Compare natural gas rates across suppliers in your state. Find the cheapest rates and switch in minutes.',
}
```

---

### P2-04: `rates/[state]/[utility]/page.tsx` — Open Graph metadata missing `og:image` and Twitter card has no image

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/rates/[state]/[utility]/page.tsx`
**Lines**: 31–42

**Description**: The `generateMetadata` function builds OG metadata with `title`, `description`, and `url` but omits `openGraph.images`. Without an OG image, social sharing previews for the 153 ISR pages will show no image, degrading click-through rates from social media. Similarly there is no `twitter` metadata object on these pages.

**Fix**: Add a dynamic OG image route or a static fallback:
```tsx
openGraph: {
  title,
  description,
  url: `${BASE_URL}/rates/${stateSlug}/${utilitySlug}`,
  type: 'website',
  images: [
    {
      url: `${BASE_URL}/api/og?title=${encodeURIComponent(title)}`,
      width: 1200,
      height: 630,
      alt: title,
    },
  ],
},
twitter: {
  card: 'summary_large_image',
  title,
  description,
},
```

---

### P2-05: `app/layout.tsx` root metadata — `openGraph.images` is missing; Twitter card has no image

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/layout.tsx`
**Lines**: 21–31

**Description**:
```tsx
openGraph: {
  title: 'RateShift',
  description: 'Save money on utilities with AI-powered optimization — all 50 states',
  type: 'website',
  locale: 'en_US',
},
twitter: {
  card: 'summary_large_image',
  title: 'RateShift',
  description: 'AI-powered utility savings for all 50 states',
},
```
Both blocks lack `images`. The root OG metadata propagates to child pages that do not override it. A `summary_large_image` Twitter card without an image URL is invalid — Twitter will fall back to `summary` rendering.

**Fix**: Add a static OG image to both:
```tsx
openGraph: {
  ...existingFields,
  images: [{ url: 'https://rateshift.app/og-image.png', width: 1200, height: 630 }],
},
twitter: {
  ...existingFields,
  images: ['https://rateshift.app/og-image.png'],
},
```

---

### P2-06: `not-found.tsx` links to `/dashboard` which requires authentication — unauthenticated 404 visits cause an extra redirect loop

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/not-found.tsx`
**Line**: 12

**Description**: The 404 page's "Back to Dashboard" CTA links to `/dashboard`. If an unauthenticated user lands on a 404 (e.g., by mistyping a URL on the marketing site), clicking the CTA redirects them through middleware to `/auth/login?callbackUrl=%2Fdashboard` — a confusing double-redirect that does not serve the user. The 404 page should be context-aware: link to `/` for unauthenticated users and `/dashboard` for authenticated ones, or simply link to `/` universally.

**Fix**: Change the fallback link to the home page:
```tsx
<Link href="/">Back to Home</Link>
```
Optionally render a client component that checks auth state and conditionally shows the appropriate CTA.

---

### P2-07: `app/(app)/auth/login/page.tsx` — `export const dynamic = 'force-dynamic'` on a client component is redundant and misleading

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/login/page.tsx`
**Lines**: 1, 9

**Description**:
```tsx
'use client'
...
export const dynamic = 'force-dynamic'
```
`export const dynamic` is a route segment configuration option that only applies to Server Components and Server Actions. When used with `'use client'` files, it has no effect — the rendering strategy is always client-side for client components. This false declaration misleads developers into believing the page is dynamically server-rendered. The same issue exists in `signup/page.tsx`, `forgot-password/page.tsx`, `reset-password/page.tsx`, and `verify-email/page.tsx`.

**Fix**: Remove `export const dynamic = 'force-dynamic'` from all `'use client'` auth page files, or convert them to server component wrappers (recommended) to enable server-side metadata and leverage the `dynamic` config properly.

---

### P2-08: `beta-signup/page.tsx` — no `metadata` export, no Suspense, page inside the `(app)` group renders with the authenticated sidebar for unauthenticated users

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/beta-signup/page.tsx`
**Lines**: 1, 8

**Description**: The beta-signup page: (1) has no `export const metadata` object — the page title will fall back to the root "RateShift - Save on Your Utility Bills" default; (2) is placed inside the `(app)` route group and therefore rendered with the `Sidebar` and authenticated shell, even though it is a pre-signup page that should be accessible without authentication; (3) is not protected by middleware (no entry in `protectedPaths`), meaning the sidebar renders for unauthenticated visitors.

**Fix**: Move `beta-signup` out of the `(app)` route group to the root app directory, similar to how `pricing`, `privacy`, and `terms` are structured. Add metadata.

---

### P2-09: `optimize/page.tsx` — `Appliance` IDs generated with `Date.now().toString()` — not collision-safe when adding multiple appliances rapidly

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/optimize/page.tsx`
**Lines**: 99, 122

**Description**:
```tsx
addAppliance({
  id: Date.now().toString(),
  ...
})
```
`Date.now()` returns millisecond precision. Two rapid consecutive calls (e.g., double-click or programmatic batch add) can generate identical IDs, causing React key collisions, broken `updateAppliance`/`removeAppliance` operations, and test flakiness. This should use `crypto.randomUUID()` which is available in all modern browsers and Node 19+.

**Fix**:
```tsx
id: crypto.randomUUID(),
```

---

### P2-10: `app/(app)/settings/page.tsx` — whole settings page is a single 567-line client component; all supplier, profile, and notification state loads client-side, adding unnecessary waterfalls

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/settings/page.tsx`
**Lines**: 1–567

**Description**: The settings page mounts and then fires five separate API calls: `useSuppliers`, `useSetSupplier`, `useLinkAccount`, `useUserSupplierAccounts`, `useUpdateProfile` — all React Query hooks triggered after the component hydrates. A server component approach could pre-fetch the profile and supplier data server-side, reducing the time-to-interactive by eliminating the initial loading waterfall. Currently a user sees the settings form immediately but with empty/loading supplier fields until React Query resolves.

**Fix**: Convert the page to a thin server component wrapper that fetches the profile server-side and passes it as initial data, using `dehydrate`/`HydrationBoundary` from `@tanstack/react-query`. This is already configured in the app via `QueryProvider`.

---

### P2-11: `app/(app)/auth/callback/page.tsx` — `router.replace()` failure is caught but the catch block swallows the error silently; fallback shows after 5s even on success

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/callback/page.tsx`
**Lines**: 22–33

**Description**:
```tsx
try {
  router.replace('/dashboard')
} catch {
  setShowFallback(true)
}
const timer = setTimeout(() => setShowFallback(true), 5000)
```
The `router.replace()` call itself rarely throws (it's fire-and-forget), so the `try/catch` has no practical effect. The 5-second fallback timer fires unconditionally — even when the redirect succeeds quickly — potentially showing the fallback link briefly on slow networks just before the navigation completes. More importantly, there is no error reporting mechanism if the redirect genuinely fails.

**Fix**: Use `router.replace()` directly and rely solely on the timeout as a UX guard. The catch block is misleading noise:
```tsx
useEffect(() => {
  router.replace('/dashboard')
  const timer = setTimeout(() => setShowFallback(true), 5000)
  return () => clearTimeout(timer)
}, [router])
```

---

### P2-12: `app/(dev)/architecture/page.tsx` — creates a new `QueryClient` instance inside the component body — new client on every render, breaks React Query cache isolation

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(dev)/architecture/page.tsx`
**Line**: 9

**Description**:
```tsx
const queryClient = new QueryClient()
```
This is defined at module scope (outside the component), which means it is shared across all renders of the file in the same module bundle — this is actually acceptable for Next.js but only because the module is a dev-only tool. However, creating a `QueryClient` at module level means the cache persists across test runs in Jest (since modules are cached). More critically, the `QueryClientProvider` wrapping a page component rather than using the app-level provider creates a separate isolated cache that cannot be pre-populated from server-side `dehydrate`.

**Fix**: Use `useState` to create the client once per component instance:
```tsx
const [queryClient] = useState(() => new QueryClient())
```

---

### P2-13: `app/(app)/community/page.tsx` — `useAuth()` hook is called at the page level but `user` is only used for `currentUserId` prop — causes the community page to flash "loading" state when the global auth state is not yet resolved

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/community/page.tsx`
**Lines**: 8, 12, 52

**Description**:
```tsx
const { user } = useAuth()
...
<PostList utilityType={activeUtility} currentUserId={user?.id} />
```
`user` is `null` during the auth initialization phase (before `initAuth()` resolves). This means `currentUserId` is initially `undefined`, and if `PostList` conditionally renders vote/edit controls based on `currentUserId`, they will flicker on after auth resolves. More importantly, the entire page component is already client-side due to `'use client'`, so every re-render of `AuthProvider` triggers a full community page re-render.

**Fix**: Pass `currentUserId` as `user?.id ?? undefined` and document that it is intentionally undefined during loading. Consider lifting the `user?.id` prop to a `useMemo` in `PostList` to avoid re-renders.

---

### P2-14: `app/sitemap.ts` and `app/robots.ts` — not audited but likely missing ISR page URLs for Wave 3–5 content

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/sitemap.ts`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/robots.ts`

**Description**: The `rates/[state]/[utility]/page.tsx` correctly generates 153 static params. However it was not possible to verify in this audit whether `sitemap.ts` includes these 153 ISR URLs, the community pages, the analytics page, and other new Wave 3–5 routes. Any routes omitted from `sitemap.ts` will have reduced search engine crawl priority. Noted as P2 pending direct read of `sitemap.ts`.

**Fix**: Read and verify `sitemap.ts` in a follow-up; ensure all public-facing pages and ISR rate pages are enumerated.

---

## P3 — Low (code quality, conventions, minor issues)

### P3-01: `app/(app)/optimize/page.tsx` — `useRequireAuth` hook exists but is not used; the page relies on middleware-only auth protection

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/optimize/page.tsx`
**Description**: `useRequireAuth` in `useAuth.tsx` (line 368) provides a client-side auth guard that redirects unauthenticated users. Optimize is protected by middleware, but having an explicit client-side guard as a defense-in-depth measure is a pattern used inconsistently. No app pages currently call `useRequireAuth`. The hook is defined but unused — either remove it or document where it should be applied.

---

### P3-02: `app/page.tsx` (landing) and `app/pricing/page.tsx` — duplicate inline pricing tier data, not shared with backend plan constants

**Files**: `frontend/app/page.tsx` lines 37–82, `frontend/app/pricing/page.tsx` lines 10–68
**Description**: The pricing tiers (Free/$0, Pro/$4.99, Business/$14.99) with their feature lists are copy-pasted across two files. When pricing changes (e.g., a new tier, feature addition), both files must be updated in sync. A centralized `lib/constants/plans.ts` would prevent drift.

---

### P3-03: `app/(app)/auth/login/page.tsx` and `signup/page.tsx` — page `<h1>` still reads "Electricity Optimizer" — brand inconsistency for SEO

**Files**: `auth/login/page.tsx` line 16, `auth/signup/page.tsx` line 14
**Description**: Both auth pages render `<h1>Electricity Optimizer</h1>`. Search engine crawlers use the `<h1>` as a strong relevance signal. This creates a disconnect between the page's canonical brand name (RateShift, per metadata) and its primary heading. Should be updated to "RateShift" or removed in favor of a logo image with proper alt text.

---

### P3-04: `app/(app)/beta-signup/page.tsx` contains literal emoji characters in JSX

**File**: `frontend/app/(app)/beta-signup/page.tsx` lines 273, 281, 290
**Description**: Three benefit cards use literal Unicode emoji (`💰`, `🤖`, `⚡`) rendered as `<span>{emoji}</span>`. These have inconsistent rendering across operating systems, browsers, and screen readers. Replace with SVG icons from the lucide-react library (already used throughout the codebase) or with the `aria-label` / `role="img"` pattern.

---

### P3-05: `app/(app)/settings/page.tsx` — `handleDeleteAccount` calls `router.push` via imported `authClient.signOut()` but then sets `window.location.href = '/'` — redundant navigation

**File**: `frontend/app/(app)/settings/page.tsx` lines 163–175
**Description**: The delete flow first calls `authClient.signOut()` (which internally does `router.push('/auth/login')` via `useAuth.signOut`) then calls `window.location.href = '/'`. The two navigations race and the `window.location.href` assignment wins with a hard reload. This is likely intentional (full page reload to clear React state) but the `authClient.signOut()` call inside a dynamic `import()` is redundant. The comment says "best-effort" but the pattern is confusing.

---

### P3-06: `lib/api/client.ts` — `handleResponse` does `response.json()` unconditionally for all non-error responses including DELETE 204s

**File**: `frontend/lib/api/client.ts` line 123
**Description**:
```tsx
return response.json()
```
Called for all successful responses. A `DELETE` that returns `204 No Content` will throw a JSON parse error (`SyntaxError: Unexpected end of JSON input`) because `204` bodies are empty. The `apiClient.delete` in several API files (e.g., `deleteAlert`, `removeUserSupplier`) returns typed objects assuming the response is JSON. Any backend endpoint that correctly returns `204` will cause a runtime error.

**Fix**:
```tsx
if (response.status === 204 || response.headers.get('content-length') === '0') {
  return undefined as T
}
return response.json()
```

---

### P3-07: `lib/api/agent.ts` `queryAgent` — SSE stream reader is never released on early abort

**File**: `frontend/lib/api/agent.ts` lines 70–98
**Description**: The `queryAgent` async generator reads from a `ReadableStream`. If the consuming `for await...of` loop is interrupted (e.g., component unmounts, user navigates away), the generator is abandoned without calling `reader.cancel()` or `reader.releaseLock()`. This holds the HTTP connection open until the server closes it or the next GC cycle. Over multiple navigations this can accumulate open connections.

**Fix**: Add a `try/finally` to release the reader:
```ts
try {
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    // ...process...
  }
} finally {
  reader.releaseLock()
}
```

---

### P3-08: `app/(app)/onboarding/page.tsx` — inline loading spinner using raw Tailwind instead of `<Skeleton>` component

**File**: `frontend/app/(app)/onboarding/page.tsx` lines 29–33
**Description**:
```tsx
<div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-primary-600" />
```
This hardcodes the spinner styling instead of using a reusable loading component. All other loading states in the app (dashboard, prices, suppliers, etc.) use the `<Skeleton>` component system. This inconsistency makes design-system changes harder to propagate.

---

### P3-09: `app/(app)/layout.tsx` — no `metadata` export on the app group layout — missed opportunity to set shared OG metadata for all authenticated pages

**File**: `frontend/app/(app)/layout.tsx`
**Description**: The `(app)` layout has no `metadata` export. While each page exports its own `title`, there is no inherited `description`, `openGraph.type`, or `robots` configuration at the authenticated section level. Adding metadata at this layout level would reduce per-page boilerplate.

---

### P3-10: `app/global-error.tsx` — uses inline styles instead of Tailwind utility classes, inconsistent with design system

**File**: `frontend/app/global-error.tsx` lines 9–52
**Description**: `global-error.tsx` correctly cannot use Tailwind or component imports (it must render with a minimal `<html>/<body>` since the normal layout is broken), so inline styles are the right choice here. However, the color values (`#111827`, `#6b7280`) should match the design system tokens. Document the constraint explicitly so developers do not incorrectly "fix" the inline styles in the future.

**Fix**: Add a comment explaining the constraint and verify colors match `gray-900` and `gray-500` Tailwind values (they do: `#111827` = `gray-900`, `#6b7280` = `gray-500`). No code change needed — add documentation.

---

## Appendix: File Coverage Matrix

| Route | `page.tsx` | `loading.tsx` | `error.tsx` | `metadata` | Auth Protected |
|-------|-----------|--------------|-------------|------------|----------------|
| `/(app)/dashboard` | Yes | Yes | Yes | Yes | MW + app |
| `/(app)/prices` | Yes | Yes | Yes | Partial (no desc) | MW |
| `/(app)/suppliers` | Yes | Yes | Yes | Partial (no desc) | MW |
| `/(app)/connections` | Yes | Yes | Yes | Yes | MW |
| `/(app)/optimize` | Yes | Yes | Yes | **MISSING** (client) | MW |
| `/(app)/settings` | Yes | Yes | Yes | **MISSING** (client) | MW |
| `/(app)/alerts` | Yes | Yes | **MISSING** | Partial (old brand) | MW |
| `/(app)/assistant` | Yes | Yes | **MISSING** | Yes | MW only (`/assistant`) |
| `/(app)/community` | Yes | Yes | **MISSING** | **MISSING** (client) | **NOT in MW** |
| `/(app)/analytics` | Yes | **MISSING** | **MISSING** | Partial (no desc) | **NOT in MW** |
| `/(app)/gas-rates` | Yes | **MISSING** | **MISSING** | Partial (no desc) | **NOT in MW** |
| `/(app)/heating-oil` | Yes | **MISSING** | **MISSING** | Partial (no desc) | **NOT in MW** |
| `/(app)/propane` | Yes | **MISSING** | **MISSING** | Partial (no desc) | **NOT in MW** |
| `/(app)/water` | Yes | **MISSING** | **MISSING** | Partial (no desc) | **NOT in MW** |
| `/(app)/community-solar` | Yes | **MISSING** | **MISSING** | Partial (no desc) | **NOT in MW** |
| `/(app)/onboarding` | Yes | **MISSING** | **MISSING** | **MISSING** (client) | MW |
| `/(app)/beta-signup` | Yes | **MISSING** | **MISSING** | **MISSING** (client) | NOT protected |
| `/rates/[state]/[utility]` | Yes | **MISSING** | **MISSING** | Yes (dynamic) | Public |
| `/pricing` | Yes | N/A | N/A | Yes | Public |
| `/privacy` | Yes | N/A | N/A | Yes | Public |
| `/terms` | Yes | N/A | N/A | Yes | Public |

**Legend**: MW = middleware-protected, `partial` = title only (no description)

---

## Appendix: API Client Assessment

| Check | Status | Notes |
|-------|--------|-------|
| Centralized error handling | PASS | `ApiClientError` with status + details |
| 401 redirect loop guard | PASS | `MAX_401_REDIRECTS`, `redirectInFlight` flag |
| Retry logic on 5xx | PASS | `MAX_RETRIES=2`, exponential backoff |
| Circuit breaker | PASS | `CircuitBreaker` with CLOSED/OPEN/HALF_OPEN states |
| Type safety | PASS | Generic `get<T>`, `post<T>`, etc. |
| `credentials: 'include'` on all calls | PASS | Cookie-based session |
| 204 No Content handling | FAIL | P3-06: `response.json()` unconditional |
| SSE stream cleanup | FAIL | P3-07: `agent.ts` reader never released |
| Raw `fetch` bypasses | FAIL | P0-02: `settings/page.tsx` GDPR calls |
| Token management | PASS | httpOnly cookies via Better Auth, no localStorage |
| CSRF protection | PASS | Better Auth handles CSRF via cookie validation |
