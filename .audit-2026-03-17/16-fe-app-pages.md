# 16 — Frontend: App Pages

## Scope

All `page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`, and `not-found.tsx` files under
`frontend/app/` (excluding `frontend/app/api/`). 71 files across 28 routes.

```
frontend/app/layout.tsx
frontend/app/page.tsx                          (landing)
frontend/app/error.tsx
frontend/app/not-found.tsx
frontend/app/pricing/page.tsx
frontend/app/privacy/page.tsx
frontend/app/terms/page.tsx
frontend/app/rates/[state]/[utility]/page.tsx  (ISR SEO pages)
frontend/app/(dev)/layout.tsx
frontend/app/(dev)/architecture/page.tsx
frontend/app/(app)/layout.tsx
frontend/app/(app)/error.tsx
frontend/app/(app)/dashboard/{page,loading,error}.tsx
frontend/app/(app)/alerts/{page,loading,error}.tsx
frontend/app/(app)/analytics/{page,loading,error}.tsx
frontend/app/(app)/assistant/{page,loading,error}.tsx
frontend/app/(app)/auth/callback/page.tsx
frontend/app/(app)/auth/forgot-password/page.tsx
frontend/app/(app)/auth/login/{page,loading,error}.tsx
frontend/app/(app)/auth/reset-password/page.tsx
frontend/app/(app)/auth/signup/{page,loading,error}.tsx
frontend/app/(app)/auth/verify-email/page.tsx
frontend/app/(app)/beta-signup/{page,loading,error}.tsx
frontend/app/(app)/community-solar/{page,loading,error}.tsx
frontend/app/(app)/community/{page,loading,error}.tsx
frontend/app/(app)/connections/{page,loading,error}.tsx
frontend/app/(app)/gas-rates/{page,loading,error}.tsx
frontend/app/(app)/heating-oil/{page,loading,error}.tsx
frontend/app/(app)/onboarding/{page,loading,error}.tsx
frontend/app/(app)/optimize/{page,loading,error}.tsx
frontend/app/(app)/prices/{page,loading,error}.tsx
frontend/app/(app)/propane/{page,loading,error}.tsx
frontend/app/(app)/settings/{page,loading,error}.tsx
frontend/app/(app)/suppliers/{page,loading,error}.tsx
frontend/app/(app)/water/{page,loading,error}.tsx
```

---

## P0 — Critical

### P0-1: Middleware does not protect `/gas-rates`, `/community-solar`, `/analytics`, or `/beta-signup`

**Files:** `frontend/middleware.ts`, `frontend/app/(app)/gas-rates/page.tsx`,
`frontend/app/(app)/community-solar/page.tsx`,
`frontend/app/(app)/analytics/page.tsx`,
`frontend/app/(app)/beta-signup/page.tsx`

The `protectedPaths` array in `middleware.ts` and the `matcher` config list do not include
`/gas-rates`, `/community-solar`, `/analytics`, or `/beta-signup`. These four routes sit
inside the `(app)` route group (which renders the authenticated sidebar layout) but are not
guarded at the middleware layer. An unauthenticated visitor who navigates directly to
`/gas-rates` or `/community-solar` will be served the page without being redirected to login.
The `analytics` page additionally gates on a paid tier (`AnalyticsDashboard` likely enforces
a Pro/Business check), so unauthenticated access could expose the component's fetch logic.

**Fix:** Add each missing route to both `protectedPaths` and the `matcher` export in
`middleware.ts`:

```ts
// middleware.ts — protectedPaths array
const protectedPaths = [
  ...
  '/gas-rates',
  '/community-solar',
  '/analytics',
  '/beta-signup',
]

// middleware.ts — config.matcher
export const config = {
  matcher: [
    ...
    '/gas-rates/:path*',
    '/community-solar/:path*',
    '/analytics/:path*',
    '/beta-signup/:path*',
  ],
}
```

### P0-2: `beta-signup` page submits to a non-existent internal API route and leaks a personal Gmail address

**File:** `frontend/app/(app)/beta-signup/page.tsx` (lines 27, 86)

The form `POST`s to `/api/beta-signup` which does not appear to exist as a Next.js API
route under `frontend/app/api/` — this will produce a 404 on every submission, silently
failing if the error handling only catches network errors. Additionally, line 86 hard-codes
`autodailynewsletterintake@gmail.com` as the support contact in a publicly-accessible
page. The same address appears in `privacy/page.tsx` (section 8). This is a personal Gmail
account, not a professional `@rateshift.app` address, and it should be replaced with
`support@rateshift.app` (or whichever Resend-verified address is in use).

**Fix:**
1. Create `frontend/app/api/beta-signup/route.ts` that proxies to the backend, OR
   redirect the form to the existing `/auth/signup` flow.
2. Replace `autodailynewsletterintake@gmail.com` with `support@rateshift.app` everywhere
   it appears.

---

## P1 — High

### P1-1: `(dev)/architecture/page.tsx` creates its own `QueryClient` inside the component tree, bypassing the root `QueryProvider`

**File:** `frontend/app/(dev)/architecture/page.tsx` (lines 9, 62-65)

A fresh `QueryClient` is instantiated at module scope (line 9) and wrapped in a provider
at the page level. This means every server render or hot-reload creates a new client
instance. The root `QueryProvider` (which has deduplication and caching configured) is
bypassed, so queries on this page cannot share the cache with the rest of the app. For a
dev-only page this is low risk in production (the layout already calls `notFound()` in
non-development), but the pattern should not become a template.

**Fix:** Remove the local `QueryClient` and the `QueryClientProvider` wrapper. The page
already inherits the root `QueryProvider` via `app/layout.tsx`. If the dev architecture
page needs isolation, use a separate React Query config key rather than a brand-new
client.

### P1-2: `settings/page.tsx` minimum password length (8 chars) conflicts with `reset-password/page.tsx` minimum (12 chars) and the backend server config

**File:** `frontend/app/(app)/settings/page.tsx` (line 168),
`frontend/app/(app)/auth/reset-password/page.tsx` (line 22)

`handleChangePassword` in `settings/page.tsx` validates `newPassword.length < 8` before
calling `authClient.changePassword`. The reset-password page uses `MIN_PASSWORD_LENGTH = 12`
which matches the Better Auth server config (`minPasswordLength: 12` per CLAUDE.md). A user
setting a password of length 8-11 via Settings will pass client-side validation but be
rejected by the server, producing an opaque error message rather than a helpful "password
must be at least 12 characters" hint.

**Fix:** Define a shared constant (e.g. `lib/constants/auth.ts`):
```ts
export const MIN_PASSWORD_LENGTH = 12
```
Import and use it in both `settings/page.tsx` and `reset-password/page.tsx`.

### P1-3: `onboarding/page.tsx` calls `updateProfile.mutateAsync` without awaiting an error boundary; a failed mutation silently redirects the user to `/dashboard` with an unrepaired inconsistent profile state

**File:** `frontend/app/(app)/onboarding/page.tsx` (lines 21-26)

The self-healing auto-complete logic calls `updateProfile.mutateAsync({ onboarding_completed: true })`
and `.catch(() => router.replace('/dashboard'))`. If the mutation fails the user is still
redirected to the dashboard, but their `onboarding_completed` flag remains `false`. On
the next page load they will be bounced back to `/onboarding` again, creating a redirect
loop. The original dashboard-redirect loop fix (commit `85b884d` era) added the
`redirectedRef`, but the fix only prevents repeat redirects within the same React lifecycle;
it does not prevent re-entry on the next full navigation.

**Fix:** On mutation failure, either retry once or display an error state rather than
silently redirecting. Do not set `redirectedRef.current = true` until the mutation
actually succeeds.

### P1-4: `not-found.tsx` hard-codes a redirect to `/dashboard` for unauthenticated users

**File:** `frontend/app/not-found.tsx` (line 13)

The 404 page's CTA button links directly to `/dashboard`. An unauthenticated visitor
who hits a 404 will click "Back to Dashboard", be silently redirected by middleware to
`/auth/login?callbackUrl=/dashboard`, and feel confused by the unexpected auth page. A
more appropriate default is either `/` (the landing page) or a conditional link based on
auth state.

**Fix:**
```tsx
// Option A: Always link to landing
<Link href="/">Back to Home</Link>

// Option B: Conditional (requires 'use client' + useAuth hook)
const { user } = useAuth()
<Link href={user ? '/dashboard' : '/'}>
  {user ? 'Back to Dashboard' : 'Back to Home'}
</Link>
```

### P1-5: `rates/[state]/[utility]/page.tsx` fetches from the backend using `process.env.BACKEND_URL` with no fallback timeout and no authentication — a slow or unavailable backend silently renders null data

**File:** `frontend/app/rates/[state]/[utility]/page.tsx` (lines 70-80)

The server-side fetch has no `signal` / `AbortController` timeout. If the Render backend
is cold-starting (which can take 30-60 seconds on a free tier), this ISR page will hang
during the revalidation cycle, blocking the Next.js prerender worker for up to the full
default timeout. The `catch` silently discards the error and renders with `rateData = null`,
which is acceptable for display but leaves no observability.

**Fix:** Add an explicit timeout and log on error:
```ts
const controller = new AbortController()
const timeout = setTimeout(() => controller.abort(), 5000) // 5 s
try {
  const res = await fetch(url, {
    signal: controller.signal,
    next: { revalidate: 3600 },
  })
  if (res.ok) rateData = await res.json()
} catch (err) {
  console.error('[RatePage] fetch failed:', err)
} finally {
  clearTimeout(timeout)
}
```

---

## P2 — Medium

### P2-1: Six authenticated `page.tsx` files that are `'use client'` components export no `metadata`

**Files:**
- `frontend/app/(app)/optimize/page.tsx` (no metadata)
- `frontend/app/(app)/settings/page.tsx` (no metadata — also `'use client'`)
- `frontend/app/(app)/onboarding/page.tsx` (no metadata — also `'use client'`)
- `frontend/app/(app)/community/page.tsx` (no metadata — also `'use client'`)
- `frontend/app/(app)/beta-signup/page.tsx` (no metadata — also `'use client'`)

While authenticated pages are not typically crawled, the title shown in the browser tab
and in the history bar defaults to the root layout template `"RateShift - Save on Your
Utility Bills"` for all of these pages. Users with many tabs open cannot distinguish them.

Note: `metadata` exports are not valid in `'use client'` files. Affected `'use client'`
pages must either be converted to server components that wrap a client child, or the
metadata must be promoted to a parent server layout (e.g. a route-group layout).

**Fix (server page wrapper pattern):**
```tsx
// app/(app)/optimize/page.tsx — remove 'use client', add metadata
export const metadata = { title: 'Load Optimization | RateShift' }
export default function OptimizePage() {
  return <OptimizeContent />  // client component in components/
}
```

### P2-2: `settings/page.tsx` uses `window.confirm()` for the destructive "Delete Account" action

**File:** `frontend/app/(app)/settings/page.tsx` (lines 214-216)

`window.confirm()` is not accessible (it has no ARIA role, cannot be styled to match the
app theme, and is blocked by some browser extensions). The GDPR delete flow is a
high-stakes irreversible action that warrants a proper confirmation modal with a typed
confirmation phrase (e.g. "type DELETE to confirm") as an additional safeguard.

**Fix:** Replace `window.confirm()` with the existing `Dialog` or `Modal` component
pattern used elsewhere in the codebase.

### P2-3: `beta-signup/page.tsx` uses raw emoji in JSX rather than accessible icon components

**File:** `frontend/app/(app)/beta-signup/page.tsx` (lines 272-292)

Three feature cards render `💰`, `🤖`, and `⚡` as bare text nodes inside a `<span>`.
Screen readers will announce these as "money bag", "robot face", and "high voltage" which
is jarring. The rest of the app uses lucide-react icons.

**Fix:** Replace emoji spans with lucide-react `DollarSign`, `Bot`, and `Zap` icons with
an appropriate `aria-label`.

### P2-4: `dashboard/error.tsx` and all other per-route `error.tsx` files do not report to Sentry

**Files:** All `frontend/app/(app)/*/error.tsx` files (13 files)

The `app/(app)/error.tsx` group boundary and the root `app/error.tsx` both only call
`console.error(...)`. For pages where individual error boundaries also exist
(`dashboard/error.tsx`, `alerts/error.tsx`, etc.), the caught errors are surfaced to the
user but never forwarded to Sentry. The `useEffect` + `console.error` is incomplete
observability.

**Fix:**
```tsx
useEffect(() => {
  console.error('App section error:', error)
  Sentry.captureException(error)
}, [error])
```
Or centralise error reporting inside `PageErrorFallback` to avoid repetition across all
13 files.

### P2-5: `auth/callback/page.tsx` redirects unconditionally to `/dashboard` regardless of any `callbackUrl` query parameter

**File:** `frontend/app/(app)/auth/callback/page.tsx` (lines 23-25)

When Better Auth completes an OAuth flow and lands on this page, the implementation
always sends the user to `/dashboard`. If a user started an OAuth flow from a protected
page like `/alerts` (which sets `callbackUrl=/alerts` in the login redirect), that
context is lost. The `callbackUrl` from the middleware redirect is never read here.

**Fix:**
```tsx
useEffect(() => {
  const params = new URLSearchParams(window.location.search)
  const callbackUrl = params.get('callbackUrl')
  // isSafeRedirect is already in the codebase per CLAUDE.md patterns
  const destination =
    callbackUrl && isSafeRedirect(callbackUrl) ? callbackUrl : '/dashboard'
  router.replace(destination)
}, [router])
```

### P2-6: `privacy/page.tsx` hard-codes the Last Updated date as "February 12, 2026" and references a personal Gmail for contact

**File:** `frontend/app/privacy/page.tsx` (lines 24, 76)

The privacy policy date is static in code, meaning it will silently go stale as the
policy evolves without a code change. The contact email on line 76 is
`autodailynewsletterintake@gmail.com`, which is the same personal address flagged in P0-2.

**Fix:** Replace the contact email with `privacy@rateshift.app` (or a role address). The
date can remain static but should be updated whenever the document changes.

### P2-7: `rates/[state]/[utility]/page.tsx` is missing a `loading.tsx` and `error.tsx` sibling for the ISR route

**File:** `frontend/app/rates/[state]/[utility]/`

There is no `loading.tsx` or `error.tsx` in this directory. During ISR revalidation or
when the component defers to client-side hydration, Next.js will use the nearest parent
boundary (the root `app/error.tsx`). An error on a public SEO page would show the same
error UI as the authenticated app rather than a page-appropriate fallback. Similarly,
there is no `not-found.tsx` at the route level to handle invalid `[state]/[utility]`
combos gracefully (though `notFound()` is called, it falls back to the global 404).

**Fix:** Add minimal `loading.tsx`, `error.tsx`, and optionally `not-found.tsx` in
`frontend/app/rates/[state]/[utility]/`.

### P2-8: `(app)/layout.tsx` wraps children in an `ErrorBoundary` but this class-component boundary is redundant with the per-route `error.tsx` files

**File:** `frontend/app/(app)/layout.tsx` (line 23)

The `(app)` layout renders `<ErrorBoundary fallback={<PageErrorFallback />}>{children}</ErrorBoundary>`.
Every individual route also has its own `error.tsx`. Next.js App Router `error.tsx` files
are themselves React error boundaries; having a class-based `ErrorBoundary` wrapper at
the layout level means errors bubble through two boundary layers. This double-wrapping can
cause double-render of error UIs in edge cases. The layout-level boundary also does not
call `reset()` (it renders a static fallback with no recovery action), making it a worse
fallback than the route-level `error.tsx` files.

**Fix:** Remove the `ErrorBoundary` wrapper from the `(app)` layout and rely solely on
the per-route `error.tsx` boundaries. If a safety net is desired above all routes, use a
`global-error.tsx` at the root instead (which Next.js supports for root layout errors).

---

## P3 — Low

### P3-1: `landing page` (app/page.tsx) and `pricing/page.tsx` duplicate the pricing tier data

**Files:** `frontend/app/page.tsx` (lines 37-82), `frontend/app/pricing/page.tsx` (lines 10-68)

Both files define a `tiers` array with essentially identical content (plan names, prices,
descriptions, feature lists). If pricing changes, two files must be updated in sync. The
landing page tier list omits features that are present in `pricing/page.tsx` (e.g.
"Savings tracker & gamification", "SSE real-time streaming").

**Fix:** Extract the pricing tier data into a shared module (e.g.
`lib/constants/pricing.ts`) imported by both pages.

### P3-2: `beta-signup/page.tsx` lacks a `<title>` / `metadata` export and renders in the `(app)` layout with sidebar

**File:** `frontend/app/(app)/beta-signup/page.tsx`

The beta signup form is a `'use client'` page with no `metadata` export (see also P2-1).
More importantly, it renders inside the authenticated `(app)` layout which shows the
full sidebar navigation. A beta signup form is typically a public-facing marketing page;
if it is intended for logged-in users to share with prospects, the sidebar layout is
misleading. If it is public-facing it should be moved outside the `(app)` route group.

### P3-3: `dashboard/error.tsx` exposes raw `error.message` text to the user without sanitisation

**File:** `frontend/app/(app)/dashboard/error.tsx` (line 19), and all other per-route
`error.tsx` files.

All 13 per-route error boundaries render `{error.message || 'An unexpected error occurred'}`.
In production, some error messages from the backend may contain internal implementation
details (SQL error text, stack traces embedded in error objects, internal endpoint paths).
Only the `app/error.tsx` root boundary — which delegates to `PageErrorFallback` — has a
chance to strip sensitive content. Route-level error boundaries should either use a fixed
generic message or pass through only a sanitised subset.

**Fix:** Replace `{error.message || 'An unexpected error occurred'}` with
`{process.env.NODE_ENV === 'development' ? error.message : 'An unexpected error occurred'}`.

### P3-4: `community/page.tsx` is `'use client'` and renders `<h1>` inside a server-side layout that also has `main` — resulting in no semantic landmark for the community heading

**File:** `frontend/app/(app)/community/page.tsx` (lines 18-23)

The page renders a `<div class="border-b ...">` header rather than using the `<Header>`
component that wraps content in a consistent landmark region with `<h1>`. Other pages
(e.g. `optimize/page.tsx`, `settings/page.tsx`) consistently use `<Header title="..." />`.
The `<h1>` here is inside a plain `<div>`, which is valid HTML but inconsistent with the
rest of the app's heading hierarchy.

**Fix:** Use the `<Header title="Community" />` component for consistency, or at minimum
ensure the `<h1>` is in a semantically appropriate landmark.

### P3-5: `auth/login/page.tsx` and `auth/signup/page.tsx` have no `metadata` export

**Files:** `frontend/app/(app)/auth/login/page.tsx`,
`frontend/app/(app)/auth/signup/page.tsx`

These pages are `'use client'` (they contain `export const dynamic = 'force-dynamic'`)
and therefore cannot directly export `metadata`. The browser tab shows "RateShift - Save
on Your Utility Bills" instead of "Sign In | RateShift" or "Create Account | RateShift".
The `dynamic = 'force-dynamic'` directive itself does not require `'use client'` — it is
valid on server components.

**Fix:** Remove `'use client'` from the page files (it is not used; the actual form
components already contain `'use client'`), then export `metadata` normally.

### P3-6: `(dev)/layout.tsx` guards production access with a `NODE_ENV` check but the guard runs at render-time, not at request-time

**File:** `frontend/app/(dev)/layout.tsx` (lines 5-7)

`if (process.env.NODE_ENV !== 'development') { notFound() }` is evaluated server-side
per request, which is correct for SSR. However, the `middleware.ts` also rewrites
`/architecture` paths to `/404` (line 38). This dual-layer protection is slightly
redundant, but more importantly the middleware rewrite uses `new URL('/404', request.url)`
rather than calling `notFound()` — this returns a 200 status code with the 404 page
content rather than a true 404 HTTP response, which is incorrect for SEO crawlers.

**Fix:** In `middleware.ts`, replace the rewrite with a redirect or use `NextResponse.notFound()`:
```ts
if (pathname.startsWith('/architecture') && process.env.NODE_ENV !== 'development') {
  return NextResponse.notFound() // returns proper 404 status
}
```

### P3-7: Skeleton loading screens for several pages do not match the actual page layout, potentially causing layout shift

**Files:** `frontend/app/(app)/connections/loading.tsx`,
`frontend/app/(app)/community/loading.tsx`

The `connections/loading.tsx` skeleton shows a tab-bar with two items and a 3-column
connection method picker grid. The `connections/page.tsx` renders `<ConnectionsOverview />`
which likely has a different structure. When the real content loads, the visual structure
jumps. This is not a bug per se but contributes to poor Cumulative Layout Shift (CLS)
scores.

**Fix:** Validate skeleton proportions against the actual rendered output of each page's
primary component.

---

## Summary

P0:2  P1:5  P2:8  P3:7

### Key Actions (in priority order)

1. **P0-1** Add `/gas-rates`, `/community-solar`, `/analytics`, `/beta-signup` to
   `middleware.ts` `protectedPaths` and `matcher` — 4-line change, stops unauth access to
   authenticated app shell.
2. **P0-2** Fix the broken `/api/beta-signup` endpoint (create the route or redirect to
   `/auth/signup`) and replace the personal Gmail address with `support@rateshift.app`.
3. **P1-2** Unify the minimum password length constant to 12 characters across
   `settings/page.tsx` and `reset-password/page.tsx`.
4. **P1-4** Update `not-found.tsx` CTA to link to `/` instead of `/dashboard` for
   unauthenticated visitors.
5. **P1-5** Add a fetch timeout to the ISR `rates/[state]/[utility]/page.tsx` server
   fetch to prevent rendering worker hangs during Render cold starts.
6. **P2-4** Instrument all `error.tsx` boundaries with `Sentry.captureException(error)`.
7. **P2-5** Read `callbackUrl` in `auth/callback/page.tsx` to restore post-OAuth
   navigation context.
