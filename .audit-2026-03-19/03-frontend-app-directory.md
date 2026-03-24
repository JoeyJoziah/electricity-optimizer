# 03 - Frontend App Directory Audit

**Auditor**: Claude Opus 4.6
**Date**: 2026-03-19
**Scope**: All files in `frontend/app/` (84 files across root, (app), (dev), api, rates, pricing, privacy, terms)
**Method**: Manual read-only review of every file; grep-based cross-validation of patterns

---

## Files Reviewed (84 total)

### Root-level (10 files)
| File | Type | Lines |
|------|------|-------|
| `frontend/app/layout.tsx` | Root layout (Server Component) | 62 |
| `frontend/app/page.tsx` | Landing page (Server Component) | ~200 |
| `frontend/app/error.tsx` | Root error boundary (Client) | 18 |
| `frontend/app/global-error.tsx` | Global error boundary (Client) | 56 |
| `frontend/app/not-found.tsx` | 404 page (Server Component) | 19 |
| `frontend/app/globals.css` | Global CSS + design tokens | ~400 |
| `frontend/app/manifest.ts` | PWA manifest | ~30 |
| `frontend/app/robots.ts` | robots.txt generation | 15 |
| `frontend/app/sitemap.ts` | Sitemap generation | 61 |
| `frontend/app/icon.tsx` / `apple-icon.tsx` | Dynamic OG icons | ~40 each |

### (app) Route Group (55 files)
| Route | page.tsx | loading.tsx | error.tsx | Notes |
|-------|----------|-------------|-----------|-------|
| `(app)/layout.tsx` | - | - | `error.tsx` | App shell with Sidebar |
| `(app)/dashboard/` | Server | Yes | Yes | |
| `(app)/alerts/` | Server | Yes | Yes | |
| `(app)/analytics/` | Server | Yes | Yes | |
| `(app)/assistant/` | Server | Yes | Yes | |
| `(app)/beta-signup/` | Client | Yes | Yes | |
| `(app)/community/` | Client | Yes | Yes | |
| `(app)/community-solar/` | Server | Yes | Yes | |
| `(app)/connections/` | Server | Yes | Yes | |
| `(app)/gas-rates/` | Server | Yes | Yes | |
| `(app)/heating-oil/` | Server | Yes | Yes | |
| `(app)/onboarding/` | Client | Yes | Yes | |
| `(app)/optimize/` | Client | Yes | Yes | |
| `(app)/prices/` | Server | Yes | Yes | |
| `(app)/propane/` | Server | Yes | Yes | |
| `(app)/settings/` | Client | Yes | Yes | |
| `(app)/suppliers/` | Server | Yes | Yes | |
| `(app)/water/` | Server | Yes | Yes | |
| `(app)/auth/login/` | Client | Yes | Yes | |
| `(app)/auth/signup/` | Client | Yes | Yes | |
| `(app)/auth/callback/` | Client | **NO** | **NO** | Missing both |
| `(app)/auth/forgot-password/` | Client | **NO** | **NO** | Missing both |
| `(app)/auth/reset-password/` | Client | **NO** | **NO** | Missing both |
| `(app)/auth/verify-email/` | Client | **NO** | **NO** | Missing both |

### (dev) Route Group (2 files)
| File | Type |
|------|------|
| `(dev)/layout.tsx` | Dev guard layout (Server Component) |
| `(dev)/architecture/page.tsx` | Excalidraw editor (Client) |

### API Routes (5 files)
| File | Method | Auth |
|------|--------|------|
| `api/auth/[...all]/route.ts` | GET/POST | Better Auth handler |
| `api/checkout/route.ts` | POST | Bearer token validated |
| `api/pwa-icon/route.tsx` | GET | None (public) |
| `api/dev/diagrams/route.ts` | GET/POST | isDev() guard |
| `api/dev/diagrams/[name]/route.ts` | GET/PUT/DELETE | isDev() guard |

### Public Pages (4 files)
| File | Type |
|------|------|
| `pricing/page.tsx` | Server Component with metadata |
| `privacy/page.tsx` | Server Component with metadata |
| `terms/page.tsx` | Server Component with metadata |
| `rates/[state]/[utility]/page.tsx` | Server Component with ISR |

---

## Findings

### P0 - Critical (must fix before next deploy)

#### P0-1: Auth pages render inside app layout with Sidebar

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/login/page.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/signup/page.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/callback/page.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/forgot-password/page.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/reset-password/page.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/verify-email/page.tsx`

**Issue**: All 6 auth pages are nested under the `(app)/` route group, which renders them inside `(app)/layout.tsx`. That layout wraps children with `<Sidebar />` (line 21) and a `<div className="flex min-h-screen">` app shell (line 20). This means login, signup, forgot-password, reset-password, verify-email, and callback all show the authenticated app sidebar.

Auth flows should render in a clean, distraction-free layout (no sidebar, no app chrome). A pre-auth user seeing the sidebar creates UX confusion and exposes authenticated navigation structure to unauthenticated visitors.

**Impact**: UX breakage for all unauthenticated users. The sidebar may show user-specific elements (profile, notifications) that fail or flash incorrectly for logged-out users. The `min-h-screen` style on auth pages' own containers also fights with the parent layout's `min-h-screen`.

**Recommendation**: Move `auth/` routes out of `(app)/` into their own route group `(auth)/` with a minimal layout that has no sidebar:
```
app/
  (auth)/
    layout.tsx        <- minimal layout, no sidebar
    login/page.tsx
    signup/page.tsx
    callback/page.tsx
    forgot-password/page.tsx
    reset-password/page.tsx
    verify-email/page.tsx
```

#### P0-2: No layout-level auth guard for protected routes

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/layout.tsx` (lines 7-31)

**Issue**: The `(app)/layout.tsx` has no authentication check whatsoever. It renders `<Sidebar />` and `{children}` unconditionally. There is no redirect to `/auth/login` for unauthenticated users, no session check, and no middleware-based route protection visible in the app directory.

This means every route under `(app)/` -- including `/dashboard`, `/settings`, `/connections`, `/alerts`, `/analytics`, `/assistant` -- is accessible to unauthenticated users at the layout level. Protection is presumably delegated to individual components or client-side hooks, but this creates a window where protected page shells and layout elements render before auth state is determined.

**Impact**: Unauthenticated users can access the app shell of all protected routes. API calls from those pages will fail with 401, but the page structure, navigation, and component scaffolding are visible. This is both a UX issue (flashing content) and a minor information disclosure issue.

**Recommendation**: Add an auth guard in `(app)/layout.tsx` or create a Next.js middleware (`middleware.ts`) that redirects unauthenticated users for protected paths. Example middleware approach:
```typescript
// middleware.ts
import { auth } from '@/lib/auth/server'
export async function middleware(request) {
  const session = await auth()
  if (!session && !request.nextUrl.pathname.startsWith('/auth')) {
    return NextResponse.redirect(new URL('/auth/login', request.url))
  }
}
export const config = { matcher: ['/(app)/:path*'] }
```

#### P0-3: `export const dynamic = 'force-dynamic'` in 6 client components (no-op)

**Files and lines**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/login/page.tsx` line 9
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/signup/page.tsx` line 9
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/callback/page.tsx` line 14
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/forgot-password/page.tsx` line 17
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/reset-password/page.tsx` line 20
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/verify-email/page.tsx` line 21

**Issue**: All 6 files have `'use client'` at line 1 AND `export const dynamic = 'force-dynamic'`. The `dynamic` route segment config is a **server-only** export. In a client component, this export is silently ignored by Next.js. It provides no actual functionality and gives a false sense of security -- developers may believe these pages are excluded from static generation when in fact the export does nothing.

In Next.js App Router, `dynamic`, `revalidate`, `generateStaticParams`, `generateMetadata`, and `metadata` are all server-only segment config exports. When placed in a `'use client'` file, they are bundled into the client JS but have zero effect on rendering behavior.

**Impact**: Misleading code. Developers may rely on `force-dynamic` to prevent caching of auth pages, but the export is a no-op. The pages are already dynamic because they are client components with no server-side data fetching.

**Recommendation**: Remove `export const dynamic = 'force-dynamic'` from all 6 client component files. If dynamic rendering is truly needed (e.g., to prevent CDN caching of the HTML shell), implement it via a server component wrapper or Next.js middleware headers.

---

### P1 - High (should fix soon)

#### P1-1: 19 error.tsx files expose raw `error.message` to users

**Files** (all at line 19):
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/dashboard/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/alerts/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/analytics/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/assistant/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/login/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/signup/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/beta-signup/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/community/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/community-solar/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/connections/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/gas-rates/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/heating-oil/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/onboarding/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/optimize/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/prices/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/propane/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/settings/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/suppliers/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/water/error.tsx`

**Also**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/page-error-fallback.tsx` line 33

**Pattern**: `{error.message || 'An unexpected error occurred'}`

**Issue**: Raw `error.message` strings are displayed directly in the UI. In production, server errors may include stack traces, database error messages, internal paths, or dependency version information. Next.js does sanitize server-side error messages in production (replacing with a digest), but client-side errors (from React Query, fetch failures, etc.) pass through unmodified.

**Impact**: Potential information disclosure. A failed API call could surface messages like "ECONNREFUSED 127.0.0.1:8000" or "TypeError: Cannot read properties of undefined (reading 'id')" to end users.

**Recommendation**: Replace `error.message` rendering with a generic user-friendly message. Use `error.digest` for support reference (as `global-error.tsx` correctly does). Log the full error to console or an error reporting service:
```typescript
<p className="mt-2 text-sm text-gray-500">
  An unexpected error occurred while loading this page.
  {error.digest && <span className="block mt-1 text-xs text-gray-400">Reference: {error.digest}</span>}
</p>
```

#### P1-2: Auth sub-routes missing loading.tsx and error.tsx (4 routes)

**Missing files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/callback/loading.tsx` -- MISSING
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/callback/error.tsx` -- MISSING
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/forgot-password/loading.tsx` -- MISSING
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/forgot-password/error.tsx` -- MISSING
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/reset-password/loading.tsx` -- MISSING
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/reset-password/error.tsx` -- MISSING
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/verify-email/loading.tsx` -- MISSING
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/verify-email/error.tsx` -- MISSING

**Issue**: While the parent `(app)/error.tsx` catches errors at the group level, these 4 auth sub-routes have no route-specific loading or error boundaries. The `login/` and `signup/` routes do have both, showing this was an oversight in the auth sub-routes.

For client components that use `useSearchParams()` (reset-password, verify-email), the page already uses `<Suspense>` internally which partially addresses this, but the lack of error.tsx means unhandled exceptions in these routes will bubble up to the generic app-level error boundary which displays "Something went wrong" without auth-specific context.

**Impact**: Poor error UX on auth recovery flows. Users resetting passwords or verifying email who hit an error see a generic app error page instead of helpful auth-specific messaging.

**Recommendation**: Add `loading.tsx` and `error.tsx` to all 4 auth sub-routes with auth-appropriate messaging (e.g., "Unable to process password reset. Please try again or contact support@rateshift.app").

#### P1-3: Protected route `/dashboard` included in sitemap.xml

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/sitemap.ts` lines 22-26

```typescript
{
  url: `${baseUrl}/dashboard`,
  lastModified: new Date(),
  changeFrequency: 'daily',
  priority: 0.9,
},
```

**Issue**: The `/dashboard` URL is included in the public sitemap with priority 0.9 (second highest). This route is a protected page requiring authentication. The `robots.ts` (line 11) correctly disallows `/dashboard/` but the sitemap contradicts this by explicitly listing it. Search engine crawlers will discover the URL from the sitemap and attempt to crawl it despite the robots.txt disallow.

**Impact**: Search engines receive contradictory signals (sitemap includes it, robots.txt disallows it). Crawlers may still index the URL, leading to 401/redirect loops in search results. It also exposes the existence of internal route paths.

**Recommendation**: Remove `/dashboard` from `sitemap.ts`. Only include publicly accessible URLs. Also audit whether `/beta-signup` (another internal route) should be in the sitemap for SEO purposes.

#### P1-4: `optimize/page.tsx` is a 700+ line client component with no server-side metadata

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/optimize/page.tsx`

**Issue**: This page is a massive `'use client'` component (700+ lines based on the file size) with `"use client"` at line 1. It contains all the optimization UI logic, state management, data fetching hooks, and rendering in a single file. As a client component, it cannot export `metadata` for SEO. It also cannot leverage server-side data fetching or streaming.

The same pattern applies to several other client-component pages, but optimize is the most extreme case.

**Impact**: No SEO metadata for the optimize page. The entire page JavaScript bundle must be downloaded and hydrated before any content is visible. No code splitting within the page.

**Recommendation**: Extract the page into a server component shell + client component content:
```typescript
// page.tsx (server component)
import { OptimizeContent } from '@/components/optimize/OptimizeContent'
export const metadata = { title: 'Optimize Schedule | RateShift' }
export default function OptimizePage() {
  return <OptimizeContent />
}
```

---

### P2 - Medium (should address in upcoming sprint)

#### P2-1: 5 pages missing metadata exports

**Files with no metadata export** (confirmed via grep for `export const metadata` across all page.tsx):
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/optimize/page.tsx` -- `'use client'`, cannot export metadata
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/settings/page.tsx` -- `'use client'`, cannot export metadata
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/onboarding/page.tsx` -- `'use client'`, cannot export metadata
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/beta-signup/page.tsx` -- `'use client'`, cannot export metadata
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/community/page.tsx` -- `'use client'`, cannot export metadata

**Issue**: These 5 pages have no `title` or `description` metadata. They all use `'use client'` which prevents server-side metadata export. The root layout template is `'%s | RateShift'` but with no page-level title, the browser tab shows only "RateShift - Save on Your Utility Bills" (the default).

**Impact**: Poor browser tab labeling. Users with multiple tabs open cannot distinguish these pages. No SEO benefit for these routes (though most are behind auth and not indexed anyway).

**Recommendation**: Convert to server component shells that export metadata and delegate interactivity to client components (same pattern as P1-4). For pages behind auth where SEO is irrelevant, at minimum use `<title>` via a client-side `document.title` update or Next.js `useEffect`.

#### P2-2: `beta-signup/page.tsx` form posts to incorrect API path

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/beta-signup/page.tsx` line 27

```typescript
const response = await fetch('/api/v1/beta/signup', {
```

**Issue**: This fetches `/api/v1/beta/signup` which would be proxied to the backend via Next.js rewrites. However, this is a direct browser-side fetch from a `'use client'` component. If the Next.js proxy rewrite rules are not configured for this path, or if the backend endpoint structure differs, this will silently fail. The error handling (line 38) catches the failure but displays only "Something went wrong. Please try again." with no specific guidance.

Additionally, the form collects `postcode` and `currentSupplier` but the supplier dropdown options are hardcoded to Connecticut-specific utilities (Eversource, United Illuminating, Town utility) despite the app being marketed as nationwide for all 50 states.

**Impact**: Beta signup may not work if proxy rules are misconfigured. The hardcoded supplier list contradicts the nationwide messaging.

**Recommendation**: Verify the backend endpoint exists and the proxy route is configured. Update the supplier dropdown to either be dynamic (fetch from backend) or use generic options (e.g., "My local utility").

#### P2-3: `privacy/page.tsx` reveals infrastructure details

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/privacy/page.tsx` line 42

```typescript
Your data is stored on secure servers (Neon PostgreSQL) with encryption at rest
and in transit.
```

**Issue**: The privacy policy publicly reveals the specific database technology used (Neon PostgreSQL). This is unnecessary information disclosure that could assist targeted attacks.

**Impact**: Low-severity information disclosure. Attackers knowing the exact database technology can focus exploits.

**Recommendation**: Replace with generic language: "Your data is stored on secure, encrypted servers with encryption at rest and in transit."

#### P2-4: Pricing and public pages duplicate navigation components

**Files**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/pricing/page.tsx` lines 74-92 (nav), lines 193-205 (footer)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/privacy/page.tsx` lines 13-20 (nav), lines 81-93 (footer)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/terms/page.tsx` lines 13-20 (nav), lines 94-106 (footer)

**Issue**: All 3 public pages duplicate nav and footer markup inline rather than using shared components. The nav and footer are nearly identical but with slight variations (e.g., pricing nav has Sign In/Get Started buttons, privacy/terms nav has only the logo). This creates maintenance burden and inconsistency risk.

**Impact**: Any branding change or nav link update must be made in 3+ places. Footer links are slightly different across pages.

**Recommendation**: Create a `(public)/layout.tsx` route group with shared `PublicNav` and `PublicFooter` components:
```
app/
  (public)/
    layout.tsx     <- shared nav + footer
    pricing/page.tsx
    privacy/page.tsx
    terms/page.tsx
```

#### P2-5: `sitemap.ts` uses `lastModified: new Date()` for static pages

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/sitemap.ts` lines 10-38

**Issue**: Every entry in the sitemap uses `lastModified: new Date()`, including pages like `/privacy` and `/terms` that change rarely. This means every sitemap generation produces a new `lastModified` date, which misleads search engine crawlers into thinking content changed when it did not. This wastes crawl budget.

**Impact**: Search engines waste crawl budget re-crawling unchanged pages. Reduces the signal value of `lastModified` for pages that actually change frequently.

**Recommendation**: Use fixed dates for static pages:
```typescript
{
  url: `${baseUrl}/privacy`,
  lastModified: new Date('2026-02-12'), // actual last edit date
  changeFrequency: 'yearly',
  priority: 0.3,
},
```

#### P2-6: `rates/[state]/[utility]/page.tsx` has duplicate `revalidate` declarations

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/rates/[state]/[utility]/page.tsx`

```typescript
// Line 55
export const revalidate = 3600 // ISR: revalidate every hour

// Line 73
{ next: { revalidate: 3600 }, signal: AbortSignal.timeout(10_000) }
```

**Issue**: The page exports `revalidate = 3600` as a route segment config AND also passes `{ next: { revalidate: 3600 } }` in the `fetch()` options. These are redundant. The route-level `revalidate` already controls the ISR interval for the entire page. The fetch-level `revalidate` controls only that specific fetch call's caching. While not a bug (they happen to match), it creates confusion about which setting takes precedence and makes it easy for them to drift apart during maintenance.

**Impact**: Maintenance confusion. A developer might update one but not the other.

**Recommendation**: Keep only the route-level `export const revalidate = 3600` and remove the per-fetch revalidate (or vice versa, using only per-fetch for more granular control). Add a comment explaining the chosen approach.

#### P2-7: `(dev)/architecture/page.tsx` creates redundant QueryClient

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(dev)/architecture/page.tsx`

**Issue**: The dev architecture page creates its own `QueryClient` instance despite the root layout already providing `<QueryProvider>`. This is wasteful and could cause cache isolation issues if any data fetching hooks are used within this page.

**Impact**: Low -- this is a dev-only page. But it sets a bad pattern.

**Recommendation**: Remove the redundant `QueryClient` instantiation and rely on the root-level `QueryProvider`.

---

### P3 - Low (nice to have)

#### P3-1: `not-found.tsx` links to `/dashboard` (protected route)

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/not-found.tsx` line 12

```typescript
<Link href="/dashboard" className="...">
  Back to Dashboard
</Link>
```

**Issue**: The 404 page links to `/dashboard`, which is a protected route. An unauthenticated user hitting a 404 will be directed to the dashboard, which they cannot access. The link text "Back to Dashboard" also assumes the user was authenticated.

**Recommendation**: Link to `/` (homepage) instead, or conditionally show different links based on auth state. Since `not-found.tsx` is a server component, consider linking to `/` as the universal fallback.

#### P3-2: `global-error.tsx` shows `error.digest` but not `error.message`

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/global-error.tsx` lines 31-34

**Issue**: The global error boundary correctly shows only `error.digest` (not `error.message`), which is the right security practice. However, none of the 19 route-level `error.tsx` files follow this same pattern -- they all show `error.message`. This inconsistency suggests the route-level error boundaries were created from a template that was not aligned with the global error boundary's security-conscious approach.

**Recommendation**: Align all error boundaries to follow `global-error.tsx`'s pattern (digest only, no message).

#### P3-3: No `loading.tsx` for public pages

**Missing**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/pricing/loading.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/privacy/loading.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/terms/loading.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/rates/[state]/[utility]/loading.tsx`

**Issue**: Public pages have no `loading.tsx` files. For static pages (`pricing`, `privacy`, `terms`) this is acceptable since they are server-rendered. For the ISR `rates/` page, which fetches from the backend with a 10-second timeout, a loading state would improve perceived performance during ISR revalidation.

**Recommendation**: Add `loading.tsx` for `rates/[state]/[utility]/` at minimum, since it has server-side data fetching.

#### P3-4: No `error.tsx` for public pages

**Missing**:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/pricing/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/privacy/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/terms/error.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/rates/[state]/[utility]/error.tsx`

**Issue**: Public pages have no route-level error boundaries. Errors will bubble up to the root `error.tsx`. For the `rates/` ISR page, if `generateMetadata()` or the page component throws, the user sees the generic root error with no SEO-page-specific context.

**Recommendation**: Add `error.tsx` for `rates/[state]/[utility]/` since it has server-side data fetching that could fail.

#### P3-5: `robots.ts` disallows `/dashboard/` but not other protected routes

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/robots.ts` line 11

```typescript
disallow: ['/api/', '/dashboard/', '/settings/', '/onboarding/'],
```

**Issue**: Several authenticated routes are missing from the robots disallow list: `/alerts/`, `/analytics/`, `/assistant/`, `/community/`, `/connections/`, `/optimize/`, `/prices/`, `/suppliers/`, `/gas-rates/`, `/heating-oil/`, `/propane/`, `/water/`, `/community-solar/`, `/beta-signup/`.

While crawlers typically cannot access these pages (they require auth), explicitly disallowing them prevents wasted crawl attempts and avoids indexing 401/redirect responses.

**Recommendation**: Add all authenticated routes to the disallow list, or use a wildcard pattern if the route structure supports it. Alternatively, add `<meta name="robots" content="noindex">` via metadata in the `(app)/layout.tsx`.

#### P3-6: `api/pwa-icon/route.tsx` allows only 2 sizes but has no rate limiting

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/api/pwa-icon/route.tsx`

**Issue**: The PWA icon endpoint validates the `size` parameter against `VALID_SIZES = new Set([192, 512])` (line 4), which is good. However, `ImageResponse` from `next/og` is computationally expensive (uses Satori for SVG-to-image conversion), and this endpoint has no caching headers or rate limiting. Repeated requests could cause CPU pressure.

**Recommendation**: Add `Cache-Control` headers (e.g., `public, max-age=86400, immutable`) since the icon content is deterministic.

#### P3-7: `checkout/route.ts` fallback URL uses `http://localhost:8000`

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/api/checkout/route.ts` line 3

```typescript
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'
```

**Issue**: If `BACKEND_URL` is not set in production, the checkout route will attempt to connect to `localhost:8000`. This same pattern appears in `rates/[state]/[utility]/page.tsx` line 70. While this should never happen in a properly configured deployment, the fallback to `localhost` in a payment flow is risky.

**Recommendation**: In production builds, throw an error if `BACKEND_URL` is not set rather than silently falling back to localhost:
```typescript
const BACKEND_URL = process.env.BACKEND_URL
if (!BACKEND_URL) throw new Error('BACKEND_URL environment variable is required')
```

#### P3-8: `manifest.ts` `start_url` points to `/dashboard` (auth-gated)

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/manifest.ts`

**Issue**: The PWA manifest sets `start_url: '/dashboard'`. When a user installs the PWA and opens it while logged out, they will land on the dashboard which requires authentication. This creates a poor first-launch experience if the session has expired.

**Recommendation**: Consider using `start_url: '/'` or implementing a redirect flow that gracefully handles expired sessions on PWA launch.

#### P3-9: `(app)/error.tsx` does not log errors

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/error.tsx`

**Issue**: Unlike the root `error.tsx` (which uses `useEffect` to `console.error` the error), the `(app)/error.tsx` and all 19 route-level error boundaries do not log errors. Errors caught by these boundaries are displayed but not logged to console or any error reporting service.

**Recommendation**: Add error logging in all error boundaries:
```typescript
useEffect(() => {
  console.error('Route error:', error)
  // optionally: Sentry.captureException(error)
}, [error])
```

#### P3-10: Landing page `/` has no error.tsx specific to it

**Issue**: The root `page.tsx` (landing page) shares the root `error.tsx`. If the landing page throws (e.g., due to a rendering error in the feature list), the error boundary wraps it with `PageErrorFallback` which may not match the landing page's visual style (it uses the app's design system rather than the landing page's standalone layout).

**Recommendation**: Low priority since the landing page is a static server component with no data fetching, making errors very unlikely.

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Total files reviewed | 84 |
| P0 Critical findings | 3 |
| P1 High findings | 4 |
| P2 Medium findings | 7 |
| P3 Low findings | 10 |
| **Total findings** | **24** |

### Category Breakdown

| Analysis Area | Findings |
|---------------|----------|
| Layout nesting / route structure | P0-1, P2-4 |
| Auth guards | P0-2 |
| Server/client component boundaries | P0-3, P1-4, P2-1, P2-7 |
| Missing loading.tsx/error.tsx | P1-2, P3-3, P3-4 |
| Error handling / information disclosure | P1-1, P2-3, P3-2, P3-9 |
| SEO / metadata | P1-3, P2-1, P2-5, P2-6, P3-5, P3-8 |
| Data fetching patterns | P2-2 |
| API route security | P3-6, P3-7 |
| Code quality / DRY | P2-4, P2-6, P2-7, P3-1 |

### Strengths

1. **Consistent loading/error boundaries**: 18 of 22 route directories under `(app)/` have both `loading.tsx` and `error.tsx`, showing good discipline.
2. **Strong SEO for rates pages**: The `rates/[state]/[utility]/page.tsx` uses `generateStaticParams`, `generateMetadata`, JSON-LD structured data, canonical URLs, and ISR -- exemplary Next.js SEO implementation.
3. **Good API route security**: The `checkout/route.ts` properly validates auth headers, constructs redirect URLs server-side (preventing SSRF), and sanitizes error responses. Dev API routes use `isDev()` guards.
4. **Accessibility**: The `(app)/layout.tsx` includes a skip-to-content link (line 14-18). The callback page has proper `role="status"` and `aria-label` attributes.
5. **Dev route protection**: The `(dev)/layout.tsx` calls `notFound()` in production, preventing dev tools from being accessible.
6. **PWA implementation**: Proper manifest, icon generation, service worker registration, and install prompt.
7. **Root error boundary**: `global-error.tsx` correctly uses inline styles (no CSS dependency), wraps in `<html>/<body>`, and shows only `error.digest` (not `error.message`).
8. **ISR with graceful degradation**: The rates page fetches with `AbortSignal.timeout(10_000)` and renders with `null` data if the backend is unavailable.
