# Audit Report: Frontend App Directory

**Scope**: `frontend/app/` — all page.tsx, layout.tsx, loading.tsx, error.tsx, route.ts files
**Date**: 2026-03-18
**Auditor**: Next.js Developer Agent
**Files Read**: 82 files total (every file in the directory tree)

---

## Executive Summary

The App Router directory is well-structured and largely follows Next.js 14+ conventions. The middleware implements proper session-cookie-based route protection with CSP nonce generation. Every protected route has both `loading.tsx` and `error.tsx` boundaries. The main weaknesses are: (1) auth pages are inside the `(app)` group layout which wraps unauthenticated pages in the sidebar shell unintentionally; (2) several `page.tsx` files are forced to be client components when they could be server components; (3) the checkout API route does not validate the `tier` field; (4) the landing page has two CTAs that navigate to the same URL; (5) the `not-found.tsx` default link targets `/dashboard` which requires auth, bouncing unauthenticated visitors.

---

## P0 — Critical (Must Fix Before Next Deployment)

### P0-01: Auth Pages Nested Inside App Layout — Sidebar Rendered on Login/Signup

**Files**: `frontend/app/(app)/layout.tsx`, `frontend/app/(app)/auth/login/page.tsx`, `frontend/app/(app)/auth/signup/page.tsx`, `frontend/app/(app)/auth/forgot-password/page.tsx`, `frontend/app/(app)/auth/reset-password/page.tsx`, `frontend/app/(app)/auth/verify-email/page.tsx`, `frontend/app/(app)/auth/callback/page.tsx`

**Problem**: All auth routes (`/auth/login`, `/auth/signup`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/verify-email`, `/auth/callback`) are nested inside the `(app)` route group. The `(app)/layout.tsx` renders `<Sidebar />`, `<SidebarProvider>`, `<FeedbackWidget />`, and an `<ErrorBoundary>` around all children. This means every auth page inherits the sidebar shell layout.

In practice the sidebar is hidden below `lg:pl-64` breakpoints and the auth pages use `min-h-screen` full-page centered layouts, so the visual impact may be masked — but the sidebar component is still mounted, its context is initialised, and `<FeedbackWidget />` is always rendered on login/signup pages. This is wasteful (imports, event listeners, DOM nodes), may trigger background API calls from sidebar component hooks, and is architecturally incorrect.

**Evidence**:
- `frontend/app/(app)/layout.tsx` line 7: `<Sidebar />` rendered unconditionally
- `frontend/app/(app)/layout.tsx` line 28: `<FeedbackWidget />` rendered unconditionally
- Auth pages are all under `frontend/app/(app)/auth/`

**Fix**: Move auth routes out of the `(app)` group. Create a separate `(auth)` route group with its own minimal layout (or no layout), or move auth pages to `frontend/app/auth/` alongside `pricing/`, `privacy/`, `terms/`. This also applies to `auth/callback/page.tsx`.

---

### P0-02: Checkout API Route — No Input Validation on `tier` Field

**File**: `frontend/app/api/checkout/route.ts`

**Problem**: The checkout route reads `body.tier` at line 46 and passes it directly to the backend without any validation. There is no check that `tier` is a string, is non-empty, or matches the allowed values (`pro`, `business`). While the backend likely validates this, the Next.js API layer should validate its own inputs, especially for a billing endpoint.

An attacker who can reach `/api/checkout` with a valid auth token can send arbitrary values in the `tier` field (e.g., very long strings, null, objects) which will be proxied to the billing backend.

**Evidence**:
- `frontend/app/api/checkout/route.ts` lines 6–9: `const body = await request.json()` — no schema validation
- `frontend/app/api/checkout/route.ts` line 43: `tier: body.tier` — unvalidated passthrough

**Fix**: Add explicit validation:
```typescript
const VALID_TIERS = new Set(['pro', 'business'])
if (!body.tier || typeof body.tier !== 'string' || !VALID_TIERS.has(body.tier)) {
  return NextResponse.json({ error: 'Invalid tier' }, { status: 400 })
}
```

---

### P0-03: `not-found.tsx` Default Link Targets `/dashboard` — Bounces Unauthenticated Users

**File**: `frontend/app/not-found.tsx`

**Problem**: The 404 page renders a "Back to Dashboard" link pointing to `/dashboard` (line 12). Unauthenticated visitors who hit a 404 (e.g., a broken public link) will be redirected through the middleware to `/auth/login`. This is a confusing UX: the user sees a 404 page, clicks "Back to Dashboard", and then gets redirected to login. For public visitors the correct fallback is `/` (the landing page) or a generic "Go Home" link.

**Evidence**:
- `frontend/app/not-found.tsx` lines 11–16: `<Link href="/dashboard">Back to Dashboard</Link>` — hard-coded protected route

**Fix**: Change the link to `/` and update the label to "Go to Home" so both authenticated and unauthenticated users land on the public landing page.

---

## P1 — High Priority (Fix Within Current Sprint)

### P1-01: `(app)/layout.tsx` Is a Server Component Without Auth Enforcement

**File**: `frontend/app/(app)/layout.tsx`

**Problem**: The `(app)` layout has no `'use client'` directive and no auth check. Route protection is fully delegated to middleware. This is architecturally correct for cookie-based middleware auth, but there is no server-side fallback if middleware is bypassed (e.g., via a misconfigured matcher, CDN, or direct Render access). A defence-in-depth approach would add a server-side auth check in the layout using `getAuth()` and redirect if the session is absent, providing a second layer.

The middleware matcher at line 112–116 of `middleware.ts` explicitly excludes many static paths but there is no explicit enumeration — a path not covered by the `protectedPaths` array would be accessible without auth even if it should be protected.

**Evidence**:
- `middleware.ts` lines 16–37: `protectedPaths` array is manually maintained — easy to miss when adding new routes
- `frontend/app/(app)/layout.tsx`: no auth verification

**Fix**: Either (a) add a server-side session check in `(app)/layout.tsx` via `getAuth()` as a second guard, or (b) convert to a catchall approach in middleware that protects everything under the `(app)` path prefix rather than an enumerated list.

---

### P1-02: Login and Signup Pages Are Forced to `'use client'` Unnecessarily — Prevent Static Rendering

**Files**: `frontend/app/(app)/auth/login/page.tsx`, `frontend/app/(app)/auth/signup/page.tsx`

**Problem**: Both files have `'use client'` at the top level AND set `export const dynamic = 'force-dynamic'`. The `'use client'` directive is present because `LoginForm` / `SignupForm` components use client-side state. However, the `page.tsx` files themselves do not need to be client components — they are simple wrappers that render a client component. Making a page a client component forces the entire page boundary to client, preventing any server-side rendering or static shell generation.

The correct pattern is: `page.tsx` remains a server component and renders the client component `<LoginForm />`. React will handle the client boundary at the component level. The `force-dynamic` export is necessary to prevent caching, but this can be set on a server component page.

**Evidence**:
- `frontend/app/(app)/auth/login/page.tsx` line 1: `'use client'` — unnecessary on the page wrapper
- `frontend/app/(app)/auth/signup/page.tsx` line 1: `'use client'` — unnecessary on the page wrapper
- The pages only render `<LoginForm />` or `<SignupForm />` with a static title/subtitle — no client hooks at page level

**Fix**: Remove `'use client'` from both page files. Keep `export const dynamic = 'force-dynamic'`. The child form components already have their own client boundary.

---

### P1-03: Missing Metadata on Multiple Protected Pages

**Files**: `frontend/app/(app)/community/page.tsx`, `frontend/app/(app)/beta-signup/page.tsx`, `frontend/app/(app)/onboarding/page.tsx`, `frontend/app/(app)/optimize/page.tsx`, `frontend/app/(app)/settings/page.tsx`

**Problem**: Five protected pages are missing `export const metadata` (or `generateMetadata`). While protected pages are excluded from search indexing via `robots.txt`, metadata is still used by browsers for the tab title, social preview links when sharing URLs directly, and Next.js page title template (`%s | RateShift`).

Without metadata on these pages:
- The browser tab shows the default title `RateShift - Save on Your Utility Bills` for all of them (no page-specific differentiation)
- The `title` template defined in the root layout is never applied for these pages
- Social share previews (when a logged-in user copies a URL) show the generic root metadata

**Evidence**:
- `frontend/app/(app)/community/page.tsx`: no `metadata` export — file is a client component so metadata must be at page level separately
- `frontend/app/(app)/beta-signup/page.tsx` line 1: `'use client'` — metadata export inside a client component is silently ignored by Next.js
- `frontend/app/(app)/onboarding/page.tsx` line 1: `'use client'` — same issue
- `frontend/app/(app)/optimize/page.tsx` line 1: `'use client'` — same issue; large 542-line client component
- `frontend/app/(app)/settings/page.tsx` line 1: `'use client'` — same issue

**Note**: Next.js does not allow `export const metadata` from client components. These pages need either (a) a thin server component wrapper page.tsx that exports metadata and renders the client component, or (b) use `<Head>` via a workaround. Approach (a) is the correct one.

**Fix**: For each affected page, create a server component `page.tsx` that exports `metadata` and renders the existing component (renamed to e.g. `CommunityPageContent`).

---

### P1-04: `community/page.tsx` Uses `useAuth()` Hook at Page Level — Unnecessary Client Boundary

**File**: `frontend/app/(app)/community/page.tsx`

**Problem**: The community page is a client component (`'use client'` implicit from hooks at line 9: `useAuth`, line 8: `useSettingsStore`) that calls `useAuth()` at the top level only to pass `user?.id` as a prop to `<PostList>`. This forces the entire page to be a client component just to get one piece of state.

Additionally, `user?.id` could be passed down from a server-side auth check if the page were a server component, which would be more efficient.

**Evidence**:
- `frontend/app/(app)/community/page.tsx` lines 8–14: page-level state hooks force client rendering
- `frontend/app/(app)/community/page.tsx` line 59: `currentUserId={user?.id}` — only usage of the auth hook

**Fix**: Move `currentUserId` retrieval into `<PostList>` itself (which is already a client component) so the page can be a server component.

---

### P1-05: `settings/page.tsx` — 700-Line Monolithic Client Component, Password Change Uses `window.confirm()`

**File**: `frontend/app/(app)/settings/page.tsx`

**Problem (a)**: The settings page is a single 700-line `'use client'` component that handles account settings, password change, supplier management, energy usage, notifications, display preferences, and GDPR operations. This is a large bundle that loads all settings logic upfront. It should be split into named sections — each as a smaller client component — rendered from a server component page wrapper.

**Problem (b)**: `handleDeleteAccount` at line 213 uses `window.confirm()` for a destructive, irreversible action (permanent GDPR account deletion). `window.confirm()` is a browser-native dialog that:
- Cannot be styled to match the design system
- Does not clearly communicate the consequences in the confirmation text
- Can be auto-dismissed by some browser settings or popup blockers
- Is inaccessible (no ARIA, no focus management)

**Evidence**:
- `frontend/app/(app)/settings/page.tsx` line 213–233: `window.confirm(...)` for account deletion
- `frontend/app/(app)/settings/page.tsx` line 1: `'use client'` — 700 lines of mixed concerns

**Fix**: (a) Extract each card section into its own component. (b) Replace `window.confirm()` with a proper confirmation modal that includes a typed confirmation field (e.g., "Type DELETE to confirm").

---

### P1-06: `rates/[state]/[utility]/page.tsx` — `dangerouslySetInnerHTML` with Unsanitised JSON-LD

**File**: `frontend/app/rates/[state]/[utility]/page.tsx`

**Problem**: The structured data script uses `dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}` at line 109. While `JSON.stringify` is safe for well-formed JSON objects, the `jsonLd` object incorporates values derived from `US_STATES[stateCode]` (state names), `UTILITY_TYPES[utilityKey].label` (utility labels), and URL construction. If these lookup tables ever include user-controlled or externally sourced values, the raw string injection into a `<script>` tag creates an XSS vector.

The current data comes from static config files (`@/lib/config/seo`), so the immediate risk is low. However, the pattern is wrong — any future addition of dynamic data to `jsonLd` (e.g., live rate values) would immediately be exploitable.

**Evidence**:
- `frontend/app/rates/[state]/[utility]/page.tsx` lines 108–112: `dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}`
- Values: `stateName`, `utilityInfo.label`, `utilityInfo.unit` all from static config — low current risk but dangerous pattern

**Fix**: Use Next.js's built-in `<JsonLd>` approach or sanitise with a dedicated JSON-LD helper. As a minimum, ensure `JSON.stringify` output is not double-encoded. Longer term, add a lint rule against `dangerouslySetInnerHTML` in page files except in a designated `JsonLd` wrapper component.

---

### P1-07: `beta-signup/page.tsx` — No Input Validation, Incorrect `fetch` URL

**File**: `frontend/app/(app)/beta-signup/page.tsx`

**Problem (a)**: The beta signup form at line 27 sends `fetch('/api/v1/beta/signup', ...)`. The `/api/v1` prefix is routed through Next.js rewrites to the FastAPI backend. The endpoint `POST /beta/signup` must exist in the backend — this is not verifiable from this file alone, but there is no mention of a `beta` endpoint in `CLAUDE.md` or the architecture docs, suggesting this may be a dead endpoint. The form will silently fail (catches the error and shows a generic message) if the backend returns 404.

**Problem (b)**: No client-side validation exists on the form other than HTML `required` attributes. The email field uses `type="email"` (browser validation only), the postcode field accepts any text (not validated against US ZIP format), and all three dropdown `required` fields can be bypassed via programmatic form submission.

**Problem (c)**: The form submits PII (name, email, postcode) without any CSRF protection beyond the default SameSite cookie behavior. The endpoint does not appear to require auth (beta signups are for pre-registration), so there is no session-based protection.

**Evidence**:
- `frontend/app/(app)/beta-signup/page.tsx` line 27: `fetch('/api/v1/beta/signup', ...)`
- `frontend/app/(app)/beta-signup/page.tsx` lines 120–153: no validation beyond `required` and `type="email"`
- `frontend/app/(app)/beta-signup/page.tsx` line 38: generic error catch with no status-specific handling

---

### P1-08: `(app)/layout.tsx` Missing `loading.tsx` at the Group Level

**File**: `frontend/app/(app)/`

**Problem**: The `(app)` group has an `error.tsx` at the group level (`frontend/app/(app)/error.tsx`) but no `loading.tsx`. This means if the layout itself has any async initialisation that takes time, there is no streaming fallback. While the current layout is synchronous, adding one now would be defensive.

More importantly, the root `frontend/app/` directory has `error.tsx` and `global-error.tsx` but no `loading.tsx`. The root layout is async (calls `await headers()`) and the absence of a root-level `loading.tsx` means there is no graceful fallback for the root layout's async operation.

**Evidence**:
- `frontend/app/layout.tsx` line 44: `const nonce = (await headers()).get('x-nonce') ?? undefined` — async
- No `frontend/app/loading.tsx` file exists
- No `frontend/app/(app)/loading.tsx` file exists

**Fix**: Add `frontend/app/loading.tsx` (even a minimal full-screen spinner) and `frontend/app/(app)/loading.tsx`.

---

## P2 — Medium Priority (Fix Within Next Sprint)

### P2-01: `(app)/layout.tsx` — No `loading.tsx` at Group Level, Redundant `ErrorBoundary` Wrapper

**File**: `frontend/app/(app)/layout.tsx`

**Problem (a)**: As noted in P1-08, no `loading.tsx` for the `(app)` group.

**Problem (b)**: The layout wraps `{children}` with both a Next.js `error.tsx` file at the group level AND an `<ErrorBoundary>` component at lines 22–24. The `(app)/error.tsx` already provides the Next.js error boundary for this route segment. Adding a React class-based `<ErrorBoundary>` inside the layout creates a double-layered error boundary. The inner `<ErrorBoundary>` will catch errors before Next.js's boundary, potentially suppressing the automatic reset mechanism provided by `reset()` in the `error.tsx` file.

**Evidence**:
- `frontend/app/(app)/layout.tsx` lines 22–25: `<ErrorBoundary fallback={<PageErrorFallback />}>{children}</ErrorBoundary>`
- `frontend/app/(app)/error.tsx` exists and provides the same fallback

### P2-02: Error Boundaries Expose `error.message` Directly to Users

**Files**: All per-route `error.tsx` files (14 files: dashboard, alerts, analytics, assistant, login, signup, beta-signup, community, community-solar, connections, onboarding, optimize, prices, suppliers, settings, water, gas-rates, heating-oil, propane — checked all present)

**Problem**: Every `error.tsx` displays `{error.message || 'An unexpected error occurred'}` directly to the user. Error messages from JavaScript exceptions can contain:
- Internal path information (`/app/lib/api/client.ts:42`)
- Network error details (`Failed to fetch: ECONNREFUSED 127.0.0.1:8000`)
- Backend error messages that were proxied through (stack traces, SQL details in dev)
- Sensitive field names or parameter values

The `error.message` from server actions or data fetches should never be shown directly to end users in production.

**Evidence** (representative):
- `frontend/app/(app)/dashboard/error.tsx` line 20: `{error.message || 'An unexpected error occurred'}`
- Same pattern repeated in all ~14 error boundary files

**Fix**: Show a generic user-friendly message and log the full error to the console (already done in some files) or to Sentry. Optionally display `error.digest` as a reference ID for support (already done in `global-error.tsx` at line 31).

---

### P2-03: `auth/callback/page.tsx` — Client Component for What Should Be a Server Redirect

**File**: `frontend/app/(app)/auth/callback/page.tsx`

**Problem**: The callback page is a full client component that uses `useEffect` + `useRouter` to redirect to `/dashboard`. This means:
1. The page ships JavaScript to the client for a route that exists solely to redirect
2. There is a visible flash of the spinner while React hydrates and `useEffect` fires
3. The 5-second fallback timer (`setTimeout`) runs on the client

Better Auth handles OAuth callbacks server-side via `/api/auth/callback/*`. If a user lands on `/auth/callback`, a simple server-side redirect using Next.js `redirect()` would be instant and require zero client JavaScript.

**Evidence**:
- `frontend/app/(app)/auth/callback/page.tsx` lines 1–50: full client component just to call `router.replace('/dashboard')`
- `export const dynamic = 'force-dynamic'` is set, so this could be a server component

**Fix**: Convert to a server component:
```typescript
import { redirect } from 'next/navigation'
export const dynamic = 'force-dynamic'
export default function AuthCallbackPage() {
  redirect('/dashboard')
}
```

---

### P2-04: `onboarding/page.tsx` — `useEffect` with `mutateAsync` in Render-Blocking Pattern

**File**: `frontend/app/(app)/onboarding/page.tsx`

**Problem**: The onboarding page at lines 21–29 calls `updateProfile.mutateAsync({ onboarding_completed: true })` inside a `useEffect` as an auto-fix for stale state. The `mutateAsync` call is fire-and-forget with a `.then()` chain inside `useEffect`. If the mutation is slow, the user sees the onboarding page for the duration of the API call even though they should be redirected to dashboard. The `redirectedRef.current = true` guard prevents re-entry but the pattern is complex with multiple interacting refs and conditions.

More critically, `updateProfile` is listed in the `useEffect` dependency array at line 37 (`[profile, isLoading, router, updateProfile]`). The `updateProfile` object comes from `useUpdateProfile()` (a React Query mutation). React Query mutation objects are stable across renders — but this dependency inclusion is still unexpected and could cause issues if the mutation object reference ever changes.

**Evidence**:
- `frontend/app/(app)/onboarding/page.tsx` lines 17–37: complex `useEffect` with mutation call
- `frontend/app/(app)/onboarding/page.tsx` line 37: `updateProfile` in deps array

**Fix**: Remove `updateProfile` from the dependency array (the mutation object is stable). Consider extracting the auto-redirect logic into a simpler pattern.

---

### P2-05: `sitemap.ts` — Includes Protected Page `/dashboard`

**File**: `frontend/app/sitemap.ts`

**Problem**: The sitemap at line 21–27 includes `/dashboard` with `priority: 0.9` and `changeFrequency: 'daily'`. The dashboard is a protected route that requires authentication. Search engines that crawl this URL will be redirected to `/auth/login` by middleware, which is unhelpful and wastes crawl budget. Protected pages should not appear in the sitemap.

**Evidence**:
- `frontend/app/sitemap.ts` lines 21–27: `url: ${baseUrl}/dashboard` included in sitemap

**Fix**: Remove `/dashboard` from the sitemap. Only public, crawlable pages should be included: `/`, `/pricing`, `/privacy`, `/terms`, and the programmatic `/rates/[state]/[utility]` pages.

---

### P2-06: `page.tsx` (Landing) — Two CTAs Navigate to the Same URL

**File**: `frontend/app/page.tsx`

**Problem**: The hero section at lines 123–135 has two CTA buttons: "Start Saving Today" and "Try It Free". Both links point to `/auth/signup`. Having two identically-linked CTAs in the same visual area provides no choice and is confusing — users expect different buttons to do different things. The second button should either link to `/pricing` to explain tiers, or be removed.

**Evidence**:
- `frontend/app/page.tsx` lines 123–135: Both links href `/auth/signup`

---

### P2-07: `dashboard/page.tsx` — `<Suspense>` Without Fallback

**File**: `frontend/app/(app)/dashboard/page.tsx`

**Problem**: The dashboard page at line 10 uses `<Suspense>` without a fallback prop. React will use the nearest ancestor Suspense boundary's fallback, which in this case will be the route-level `loading.tsx`. This is technically correct behavior, but the explicit `<Suspense>` without a fallback is confusing — it implies intentional streaming that is not actually configured. Either add a meaningful `fallback` (a skeleton matching the `DashboardTabs` layout) or remove the explicit `<Suspense>` wrapper and rely on the route-level `loading.tsx`.

**Evidence**:
- `frontend/app/(app)/dashboard/page.tsx` line 10: `<Suspense>` with no fallback prop

---

### P2-08: `robots.ts` — Incomplete Disallow List Misses App Routes

**File**: `frontend/app/robots.ts`

**Problem**: The `robots.ts` disallow list at line 11 includes only four paths: `/api/`, `/dashboard/`, `/settings/`, `/onboarding/`. It does not disallow the many other protected app routes: `/alerts/`, `/analytics/`, `/assistant/`, `/community/`, `/community-solar/`, `/connections/`, `/gas-rates/`, `/heating-oil/`, `/optimize/`, `/prices/`, `/propane/`, `/suppliers/`, `/water/`.

Search engines will attempt to crawl these URLs, be redirected to `/auth/login`, and may eventually index the login page under these URLs in their search results.

**Evidence**:
- `frontend/app/robots.ts` line 11: `disallow: ['/api/', '/dashboard/', '/settings/', '/onboarding/']` — only 4 of 14+ protected paths

**Fix**: Either disallow `/` and allow only specific public paths (`'/'`, `'/pricing'`, `'/privacy'`, `'/terms'`, `'/rates/'`), or enumerate all protected paths in the disallow list.

---

### P2-09: `(dev)/architecture/page.tsx` — Creates New `QueryClient` Inside Component, Leaks on Every Page Load

**File**: `frontend/app/(dev)/architecture/page.tsx`

**Problem**: Line 9 creates a `new QueryClient()` at module level outside the component, which is shared across all renders. However, for Next.js server-side rendering (even in dev mode), this is incorrect — a module-level `QueryClient` would be shared across requests on the server. For a dev-only page this is a low-risk issue, but it violates the React Query guidance to create a new `QueryClient` per request.

Additionally, the `ArchitecturePage` component wraps children in a new `QueryClientProvider` at line 62, but the parent `(app)` layout already provides `<QueryProvider>` from the root. This creates a nested `QueryClientProvider` with a fresh, isolated `QueryClient`, meaning all queries in the architecture page bypass the global cache.

**Evidence**:
- `frontend/app/(dev)/architecture/page.tsx` line 9: `const queryClient = new QueryClient()` — module-level
- `frontend/app/(dev)/architecture/page.tsx` lines 61–65: Nested `QueryClientProvider`

---

### P2-10: `optimize/page.tsx` and `settings/page.tsx` — Appliance IDs Generated with `Date.now()`

**File**: `frontend/app/(app)/optimize/page.tsx`

**Problem**: When adding appliances at line 98–104, the `id` field is set to `Date.now().toString()`. `Date.now()` in milliseconds means two rapid appliance additions within the same millisecond (possible via keyboard or programmatic submission) would produce duplicate IDs, causing React key conflicts and data corruption in the Zustand store.

**Evidence**:
- `frontend/app/(app)/optimize/page.tsx` line 99: `id: Date.now().toString()`
- `frontend/app/(app)/optimize/page.tsx` line 121: same pattern in `handleQuickAdd`

**Fix**: Use `crypto.randomUUID()` instead of `Date.now().toString()`.

---

## P3 — Low Priority / Improvements

### P3-01: `layout.tsx` (Root) — Open Graph Metadata Missing `url` and `images`

**File**: `frontend/app/layout.tsx`

**Problem**: The root layout metadata at lines 22–27 has an `openGraph` object that is missing the `url` and `images` fields. Without `og:url`, Open Graph scrapers will use the page URL they discover from, which may vary. Without `og:image`, social shares of the landing page will show no preview image.

**Evidence**:
- `frontend/app/layout.tsx` lines 22–27: No `url` or `images` in `openGraph`
- No `twitter.images` either (lines 29–32)

---

### P3-02: Error Boundary Files Lack Sentry Error Reporting

**Files**: All per-route `error.tsx` files

**Problem**: The route-level error boundaries use `console.error()` (e.g., `frontend/app/(app)/dashboard/error.tsx` uses no error reporting at all — only the root `frontend/app/error.tsx` calls `console.error('Application error:', error)`). Most per-route error boundaries do not call `console.error` or any error reporting service. The `(app)/error.tsx` at line 14 does log via `useEffect`, but individual route boundaries (dashboard, alerts, analytics, etc.) do not.

Sentry is listed as an active integration in project docs. Errors caught by these boundaries should be sent to Sentry.

**Evidence**:
- `frontend/app/(app)/dashboard/error.tsx`: No `useEffect` logging, no Sentry call
- `frontend/app/(app)/alerts/error.tsx`: No logging
- Same across 12+ error.tsx files

---

### P3-03: `pricing/page.tsx` — No `generateMetadata` with `openGraph.url`

**File**: `frontend/app/pricing/page.tsx`

**Problem**: The pricing page has `metadata` with `title` and `description` but no canonical URL, no `openGraph.url`, no `openGraph.images`, and no `twitter.images`. This is a high-value SEO page (linked from nav on landing) and should have complete Open Graph tags.

**Evidence**:
- `frontend/app/pricing/page.tsx` lines 5–8: Minimal metadata object

---

### P3-04: `auth/forgot-password/page.tsx` — No `loading.tsx` or `error.tsx`

**File**: `frontend/app/(app)/auth/forgot-password/page.tsx`

**Problem**: The forgot-password route is missing both `loading.tsx` and `error.tsx` files. The login and signup pages have both. The reset-password and verify-email pages also lack these files. This inconsistency means any error on these pages will bubble up to the `(app)` group error boundary or the root error boundary.

**Evidence**:
- `frontend/app/(app)/auth/forgot-password/`: No `loading.tsx`, no `error.tsx`
- `frontend/app/(app)/auth/reset-password/`: No `loading.tsx`, no `error.tsx`
- `frontend/app/(app)/auth/verify-email/`: No `loading.tsx`, no `error.tsx`

---

### P3-05: `community-solar/page.tsx` — Missing `description` in Metadata

**File**: `frontend/app/(app)/community-solar/page.tsx`

**Problem**: The metadata at line 3 is `{ title: 'Community Solar | RateShift' }` with no `description`. The `description` is used by search engines for the page snippet. While this is a protected page and not crawled by bots, the description appears in browser history and bookmarks.

Same issue: `alerts/page.tsx` (metadata has no `description`), `gas-rates/page.tsx`, `heating-oil/page.tsx`, `propane/page.tsx`, `suppliers/page.tsx`, `prices/page.tsx`, `water/page.tsx` — all have `title` only.

**Evidence**:
- `frontend/app/(app)/community-solar/page.tsx` line 3: `{ title: 'Community Solar | RateShift' }`
- Pattern repeated across 8 protected pages

---

### P3-06: `manifest.ts` — PWA Icons Served via Dynamic Route Instead of Static Files

**File**: `frontend/app/manifest.ts`

**Problem**: The PWA manifest at lines 13–22 references icons via `/api/pwa-icon?size=192` and `/api/pwa-icon?size=512`. These are dynamically generated `ImageResponse` routes. PWA icon specifications require the `src` to be a stable, cacheable URL. Dynamic API routes:
- May not be included in the PWA cache manifest generated by the service worker
- Require an active server to serve (cannot work offline)
- May not pass PWA install prompt validation in some browsers that require static icon files

**Evidence**:
- `frontend/app/manifest.ts` lines 13–22: Icon src references `/api/pwa-icon?size=...`

**Fix**: Generate static PNG icons at build time and serve them from `/icons/` (already excluded from middleware in the matcher). The existing `icon.tsx` and `apple-icon.tsx` conventions generate favicons correctly, but the PWA manifest needs static files.

---

### P3-07: `rates/[state]/[utility]/page.tsx` — Missing `loading.tsx` and `error.tsx`

**File**: `frontend/app/rates/[state]/[utility]/`

**Problem**: The SEO rates pages have `generateStaticParams` and ISR revalidation but no `loading.tsx` or `error.tsx`. At ISR revalidation time, the page serves stale content while regenerating in the background (correct behavior), but there is no error boundary if the server-side `fetch()` at line 69 throws a network exception and `rateData` ends up as `null`. The component must handle null data gracefully (noted in the comment at line 78), but without an error boundary, any uncaught render-time error on the static page will hit only the root `error.tsx`.

---

### P3-08: `middleware.ts` — CSP Missing `object-src` and `upgrade-insecure-requests`

**File**: `frontend/middleware.ts`

**Problem**: The CSP built by `buildCsp()` at lines 42–54 is missing two common directives:
- `object-src 'none'` — prevents `<object>`, `<embed>`, Flash exploitation
- `upgrade-insecure-requests` — upgrades HTTP sub-resources to HTTPS automatically

These are low-risk omissions but are standard hardening.

Additionally, the CSP `style-src 'unsafe-inline'` at line 46 is overly broad. This was likely set to support Tailwind CSS inline styles and PostCSS, but it bypasses the entire script-src nonce protection for stylesheets. Tailwind does not require `unsafe-inline` in production with the Tailwind CDN disabled — the CSS is compiled to a static stylesheet.

**Evidence**:
- `frontend/middleware.ts` lines 43–54: `buildCsp()` function

---

### P3-09: `dev/diagrams/[name]/route.ts` — `fs.existsSync` in Production Code Path

**File**: `frontend/app/api/dev/diagrams/[name]/route.ts`

**Problem**: The file correctly checks `if (!isDev())` and returns 404 in production. However, the `isDev()` check happens after the import statements that import `fs` and `path`. Node.js's `fs` module is available in the Next.js server runtime, so this is not a build error. But the pattern of having `fs.readFileSync` / `fs.writeFileSync` in a production-bundled API route file is fragile — if a future change removes the `isDev()` guard (or the guard has a bug), filesystem operations become accessible in production. These routes should be in a separate `dev/` directory that is excluded from the production build via Next.js configuration.

---

### P3-10: `checkout/route.ts` — No Rate Limiting

**File**: `frontend/app/api/checkout/route.ts`

**Problem**: The checkout API route that creates Stripe checkout sessions has no rate limiting. An authenticated user could rapidly create many checkout sessions. The Cloudflare Worker provides rate limiting for `api.rateshift.app/*` (backend routes), but the checkout route is a Next.js API route served through Vercel, which is not behind the CF Worker. Without rate limiting at this layer, an attacker with a valid session could spam Stripe with checkout session creation requests.

**Evidence**:
- `frontend/app/api/checkout/route.ts`: No rate limiting headers checked, no in-memory counter

**Fix**: Add rate limiting using a simple in-memory approach or check for `cf-ray` / Vercel edge rate limiting headers.

---

## Summary Table

| ID | Severity | File(s) | Issue |
|----|----------|---------|-------|
| P0-01 | Critical | `(app)/layout.tsx`, all auth pages | Auth pages inside app layout — sidebar rendered on login/signup |
| P0-02 | Critical | `api/checkout/route.ts` | No `tier` input validation in checkout API |
| P0-03 | Critical | `not-found.tsx` | 404 page links to `/dashboard` — bounces unauthenticated visitors to login |
| P1-01 | High | `(app)/layout.tsx` | No server-side auth fallback — enumerated `protectedPaths` can miss new routes |
| P1-02 | High | `auth/login/page.tsx`, `auth/signup/page.tsx` | Unnecessary `'use client'` on page wrappers — blocks static shell |
| P1-03 | High | 5 pages with `'use client'` | Metadata exports inside client components silently ignored by Next.js |
| P1-04 | High | `community/page.tsx` | `useAuth()` at page level forces unnecessary client boundary |
| P1-05 | High | `settings/page.tsx` | 700-line monolith + `window.confirm()` for irreversible account deletion |
| P1-06 | High | `rates/[state]/[utility]/page.tsx` | `dangerouslySetInnerHTML` with raw `JSON.stringify` output |
| P1-07 | High | `beta-signup/page.tsx` | No input validation, potentially dead API endpoint, no CSRF protection |
| P1-08 | High | `app/` root, `(app)/` group | Missing `loading.tsx` at root and `(app)` group level |
| P2-01 | Medium | `(app)/layout.tsx` | Redundant double error boundary (layout + route-level) |
| P2-02 | Medium | All 14+ `error.tsx` files | `error.message` exposed directly to users in UI |
| P2-03 | Medium | `auth/callback/page.tsx` | Client component for a pure redirect — should be server-side |
| P2-04 | Medium | `onboarding/page.tsx` | `mutateAsync` in `useEffect`, unstable `updateProfile` in deps |
| P2-05 | Medium | `sitemap.ts` | Protected route `/dashboard` included in sitemap |
| P2-06 | Medium | `page.tsx` (landing) | Two CTAs with identical href — confusing UX |
| P2-07 | Medium | `dashboard/page.tsx` | `<Suspense>` without fallback — confusing, defers to route loading.tsx |
| P2-08 | Medium | `robots.ts` | Disallow list missing 10+ protected app routes |
| P2-09 | Medium | `(dev)/architecture/page.tsx` | Module-level `QueryClient`, nested `QueryClientProvider` |
| P2-10 | Medium | `optimize/page.tsx` | `Date.now()` for appliance IDs — potential duplicate keys |
| P3-01 | Low | `layout.tsx` (root) | OG metadata missing `url` and `images` |
| P3-02 | Low | All route `error.tsx` files | No Sentry error reporting in per-route error boundaries |
| P3-03 | Low | `pricing/page.tsx` | Incomplete OG metadata on high-value public page |
| P3-04 | Low | `auth/forgot-password/`, `reset-password/`, `verify-email/` | No `loading.tsx` or `error.tsx` for 3 auth routes |
| P3-05 | Low | 8 protected pages | Metadata with `title` only, no `description` |
| P3-06 | Low | `manifest.ts` | PWA icons served via dynamic API route instead of static files |
| P3-07 | Low | `rates/[state]/[utility]/` | Missing `loading.tsx` and `error.tsx` for ISR pages |
| P3-08 | Low | `middleware.ts` | CSP missing `object-src 'none'`, `upgrade-insecure-requests`; `style-src 'unsafe-inline'` too broad |
| P3-09 | Low | `api/dev/diagrams/` | `fs` operations in production-bundled code (guarded but fragile) |
| P3-10 | Low | `api/checkout/route.ts` | No rate limiting on Stripe checkout session creation |

---

## Positive Findings (What Works Well)

1. **Middleware route protection is solid**: Cookie presence check with redirect to `?callbackUrl=` is correctly implemented. Auth pages are properly redirected away for authenticated users.

2. **CSP nonce architecture**: Per-request nonce generation with `crypto.randomUUID()` and propagation via `x-nonce` header to server components is correctly implemented.

3. **`loading.tsx` and `error.tsx` coverage**: Every protected route in `(app)/` has both files — this is excellent coverage. The skeleton screens are contextually appropriate per route.

4. **ISR configuration on rates pages**: `export const revalidate = 3600` with `generateStaticParams` is correctly configured for the SEO rates pages. The AbortSignal timeout on the backend fetch (10s) is good defensive coding.

5. **JSON-LD structured data on rates pages**: Correct use of BreadcrumbList schema with proper position indices.

6. **Auth API route lazy handler pattern**: The lazy `getHandler()` pattern in `api/auth/[...all]/route.ts` correctly avoids evaluating Better Auth at build time.

7. **Checkout URL construction**: Redirect URLs are constructed server-side from `request.nextUrl.origin` rather than accepted from the client — correct SSRF prevention.

8. **Dev routes gated by `NODE_ENV`**: The `(dev)` layout, dev API routes, and architecture page all check `process.env.NODE_ENV !== 'development'` and return 404 in production.

9. **`global-error.tsx`**: Correctly wraps the full `<html><body>` for catastrophic errors that bypass the root layout.

10. **Password security**: `forgot-password/page.tsx` correctly avoids revealing whether an email exists in the system ("If an account exists...").

11. **`reset-password/page.tsx` Suspense wrapping**: Correctly wraps `useSearchParams()` consumer in `<Suspense>` to avoid Next.js build-time errors — same pattern used in `verify-email/page.tsx`.

12. **GDPR export/delete in settings**: Both operations are implemented correctly — export downloads as JSON blob, delete calls the backend endpoint, signs out, clears local state before redirect.
