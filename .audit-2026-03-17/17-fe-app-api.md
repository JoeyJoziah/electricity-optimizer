# 17 — Frontend: App API Routes

## Scope

Files audited:

- `frontend/app/api/auth/[...all]/route.ts`
- `frontend/app/api/checkout/route.ts`
- `frontend/app/api/dev/diagrams/route.ts`
- `frontend/app/api/dev/diagrams/[name]/route.ts`
- `frontend/app/api/pwa-icon/route.tsx`
- `frontend/middleware.ts`
- `frontend/next.config.js`
- `frontend/lib/auth/server.ts`
- `frontend/lib/auth/client.ts`
- `frontend/lib/config/env.ts`
- `frontend/lib/email/send.ts` (supporting, follows from auth server)

---

## P0 — Critical

### P0-1: Middleware cookie check is not a real session validation

**File:** `frontend/middleware.ts`, lines 44-46

**Problem:** The middleware gates all protected routes by checking whether the
`better-auth.session_token` cookie is *present*, not whether it is valid. A
browser or proxy can trivially set that cookie to any non-empty string and the
middleware will pass the request through as "authenticated". Because this check
runs in the Next.js Edge Runtime it cannot call the database; however it also
cannot be treated as a security boundary — it is a UX redirect helper only.

The real risk is that developers (or security reviewers) may rely on this check
as proof of authentication for server components or route handlers that sit
behind these paths. Any page or API route under a "protected path" that does not
independently verify the session with `getAuth().api.getSession()` is exposed to
cookie-stuffing attacks.

**Recommendation:** Document prominently in middleware.ts (and in CLAUDE.md) that
this is a *UX guard only*. Every Server Component or route handler that performs
sensitive operations must call `getAuth().api.getSession(request)` independently
and return 401/redirect on a null session. Audit all protected-path server
components to confirm they do this.

---

### P0-2: `/api/dev/diagrams` routes are guarded by `NODE_ENV` only — no middleware matcher, reachable in production if NODE_ENV is set incorrectly

**Files:** `frontend/app/api/dev/diagrams/route.ts`,
`frontend/app/api/dev/diagrams/[name]/route.ts`

**Problem:** The dev diagram routes perform arbitrary local filesystem reads and
writes (`fs.readFileSync`, `fs.writeFileSync`) to `docs/architecture/`. The sole
protection is a runtime `isDev()` check (`process.env.NODE_ENV !== 'development'`
returns 404). There are two issues:

1. The `/api/dev/*` path is **not listed in the `middleware.ts` matcher** and is
   not in `protectedPaths`, so the middleware never runs for it. If `NODE_ENV`
   were ever incorrect (e.g. an operator copies a .env file and forgets to set
   `NODE_ENV=production`) these routes are fully open to unauthenticated callers
   on the production host.

2. The `PUT` handler in `[name]/route.ts` (line 74) writes the entire parsed JSON
   body directly to disk with no size limit. An attacker who reaches this endpoint
   can write arbitrarily large files to the server's filesystem, exhausting disk
   space (Denial of Service).

**Recommendation:**
- Add `/api/dev/:path*` to both `protectedPaths` in `middleware.ts` and the
  `config.matcher` array so the middleware runs.
- Additionally add an explicit runtime check: if `NODE_ENV !== 'development'` return
  404 (already done) *and* also verify a valid admin session token.
- Add a request body size cap (e.g. 1 MB) in the PUT handler before calling
  `fs.writeFileSync`.

---

## P1 — High

### P1-1: Checkout proxy forwards the raw Authorization header without session validation

**File:** `frontend/app/api/checkout/route.ts`, lines 6-58

**Problem:** The checkout proxy accepts any `Bearer <token>` in the
`Authorization` header and forwards it verbatim to the Render backend. It does
not verify that the token corresponds to a live RateShift session, nor does it
validate the session cookie. An attacker can replay any previously captured
token (or craft a plausible-looking Bearer value) against this endpoint. The
header injection guard on lines 24-29 (newline check) is a good hygiene measure
but does not constitute authentication.

Additionally, the `body.tier` value is passed directly to the backend without
any allowlist check. While the backend should validate this, defence-in-depth
would reject unexpected tier values at the proxy layer.

**Recommendation:**
- Call `getAuth().api.getSession(request)` at the top of the handler. If the
  session is null, return 401. Then either pass the backend's own token derived
  from the session, or use an `INTERNAL_API_KEY` on the server-to-server leg so
  the user-facing JWT is never forwarded.
- Validate `body.tier` against an explicit allowlist (`['pro', 'business']`)
  before forwarding.

---

### P1-2: Backend error responses are forwarded verbatim to the client

**File:** `frontend/app/api/checkout/route.ts`, lines 44-48

**Problem:** When the backend returns a non-2xx status, the raw `data` object
from the backend response is returned directly to the browser:

```typescript
if (!response.ok) {
  return NextResponse.json(data, { status: response.status })
}
```

If the backend includes internal stack traces, database error messages, or
internal infrastructure details in error payloads (possible for unhandled
exceptions), those details are forwarded to the client. This can aid
reconnaissance.

**Recommendation:** Log `data` server-side and return a sanitised error message
to the client. Map known backend error codes to safe frontend messages. At
minimum, filter the forwarded object to a known-safe subset (e.g. `{ error,
code }`).

---

### P1-3: No rate limiting on any frontend API route

**Files:** All routes under `frontend/app/api/`

**Problem:** None of the Next.js API routes implement rate limiting. This
affects:

- `POST /api/auth/[...all]` — sign-in attempts are limited only by whatever
  Better Auth internally provides (not visible in this config); magic-link
  requests could be abused to spam email to arbitrary addresses.
- `POST /api/checkout` — repeated calls could trigger multiple Stripe checkout
  session creations per user.
- `GET /api/pwa-icon` — the `ImageResponse` renderer consumes CPU; repeated
  calls with varying (or invalid) `size` params could be used for resource
  exhaustion (mitigated partially by the `VALID_SIZES` allowlist, but still
  callable without auth at high frequency).

The Cloudflare Worker rate limiter (120 req/min) applies only to
`api.rateshift.app`; Vercel-hosted Next.js routes at `rateshift.app/api/*` are
behind Vercel's infrastructure only.

**Recommendation:** Add Vercel KV-backed or in-memory IP-rate limiting to at
least the checkout and auth routes. For the auth routes, confirm Better Auth's
built-in rate limiting is enabled and document the thresholds. Consider
`@upstash/ratelimit` or a thin middleware wrapper.

---

### P1-4: `success_url` and `cancel_url` are not validated for safe redirects

**File:** `frontend/app/api/checkout/route.ts`, lines 38-41

**Problem:** The checkout proxy passes `body.success_url` and `body.cancel_url`
to the Stripe backend. If a caller provides an arbitrary URL (e.g.
`https://attacker.com`), the backend will create a Stripe session whose
post-checkout redirect points to an attacker-controlled domain. This is an
open-redirect via Stripe.

The code has a safe default (`${request.nextUrl.origin}/...`) but a client can
still override it by sending their own `success_url` in the request body.

**Recommendation:** Strip `success_url` and `cancel_url` from the forwarded
body entirely, constructing them server-side from `request.nextUrl.origin` only.
If caller-provided URLs must be supported, run them through the existing
`isSafeRedirect()` utility before forwarding.

---

## P2 — Medium

### P2-1: `script-src 'unsafe-inline'` in Content Security Policy weakens XSS protection

**File:** `frontend/next.config.js`, line 58

**Problem:** The CSP includes `'unsafe-inline'` in `script-src` for both
development and production:

```
script-src 'self' 'unsafe-inline' https://*.clarity.ms https://cdn.onesignal.com
```

`'unsafe-inline'` allows any inline `<script>` or event-handler attribute to
execute. This largely defeats the XSS-prevention benefit of a CSP because any
stored or reflected XSS payload embedded in the HTML will execute regardless of
the `script-src` allowlist.

**Recommendation:** Replace `'unsafe-inline'` with a nonce-based or hash-based
approach. Next.js supports nonce injection via middleware since v13.4. For
OneSignal and Clarity, prefer loading them via `<Script strategy="afterInteractive">`
with a nonce rather than an inline-unsafe exception.

### P2-2: `connect-src` allows `https://*.onrender.com` and `https://*.vercel.app` broadly

**File:** `frontend/next.config.js`, line 62

**Problem:** The CSP `connect-src` directive allows XHR/fetch to any
`*.onrender.com` and any `*.vercel.app` subdomain. An XSS payload could
exfiltrate data to an attacker-owned Render or Vercel deployment using these
allowed origins. The wildcard is overly broad; only the specific hostnames
needed (`api.rateshift.app`, the specific Render service, the specific Vercel
preview URL) should be listed.

**Recommendation:** Replace the wildcards with the exact hostnames:
```
connect-src 'self' https://api.rateshift.app https://electricity-optimizer.onrender.com
https://rateshift.vercel.app https://www.clarity.ms ...
```

### P2-3: Lazy singleton auth object is not thread-safe under concurrent cold starts

**File:** `frontend/lib/auth/server.ts`, lines 141-148

**Problem:** The `_auth` singleton is initialised with a simple `if (!_auth)`
check. In a serverless environment (Vercel), multiple concurrent cold-start
invocations of the same isolate can race through this check simultaneously,
creating multiple `Pool` instances (each opening up to 2 DB connections) before
`_auth` is assigned. Under burst traffic this can transiently exhaust the Neon
connection pool (max: 2 per isolate, but multiple isolates).

The same pattern exists for `_handler` in `frontend/app/api/auth/[...all]/route.ts`
(line 16). Creating two handlers is benign (stateless wrapper) but the duplicate
pool creation is not.

**Recommendation:** Initialise the pool and auth object at module load time
(module-level `const`) and rely on Next.js `export const dynamic = "force-dynamic"`
to prevent build-time evaluation. This is safe in a serverless deployment because
each isolate has its own module scope. Alternatively, use a proper
double-checked lock or a `Promise` singleton pattern.

### P2-4: Verification email URL is logged at INFO level

**File:** `frontend/lib/auth/server.ts`, line 57

**Problem:**
```typescript
console.log(`[Auth] sendVerificationEmail called for user=${user.email} url=${url}`)
```

The full verification URL (which contains a one-time secret token) is logged to
stdout. In production this means verification tokens appear in Vercel/Render
log drains, where they may be accessible to any team member with log access and
could be stored by log aggregators. A token visible in logs is a valid
authentication bypass for an email verification step.

**Recommendation:** Remove the `url` from the log line or truncate it. Log only
`user.email` and a boolean indicator. Apply the same review to the password
reset email handler.

### P2-5: No `X-Content-Type-Options` or security headers on inline API JSON responses

**File:** `frontend/next.config.js`, lines 44-72

**Problem:** The security headers defined in `next.config.js` apply to all
responses via the `source: '/(.*)'` matcher, which in Next.js applies to page
routes but not to `app/api/` routes in all framework versions. Verify that
`X-Frame-Options: DENY`, `Content-Security-Policy`, and `X-Content-Type-Options`
are actually present on responses from `/api/checkout`, `/api/auth/[...all]`,
etc. If they are not, JSON API responses can be embedded in iframes and JSON
responses with wrong `Content-Type` can be sniffed.

**Recommendation:** Test API route responses with `curl -I` in production and
confirm the security headers are present. If they are absent, add them
explicitly in each route handler or via a shared helper, or configure a Vercel
`vercel.json` `headers` rule targeting `/api/(.*)`.

---

## P3 — Low

### P3-1: `BACKEND_URL` falls back silently to `localhost:8000` if unset

**File:** `frontend/app/api/checkout/route.ts`, line 3

**Problem:**
```typescript
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'
```

If `BACKEND_URL` is not set in a production deploy, requests will silently
target `http://localhost:8000` (which will fail or hit an unintended local
service) rather than failing fast at startup. There is no warning logged.

**Recommendation:** Apply the same fail-fast pattern used in `env.ts`: throw or
warn loudly if `BACKEND_URL` is absent in a production context. Alternatively
import and reuse the existing `env.ts` helpers here so the variable is validated
centrally.

### P3-2: `pwa-icon` route has no cache headers

**File:** `frontend/app/api/pwa-icon/route.tsx`

**Problem:** The route generates an image dynamically on every request via
`ImageResponse` (which is CPU-intensive). No `Cache-Control` header is set, so
Vercel's CDN may or may not cache it depending on framework defaults. The icon
content is static (only 2 possible sizes), so it could be cached for a very
long time.

**Recommendation:** Return an explicit `Cache-Control: public, max-age=31536000,
immutable` header (the set of valid sizes is static). This also prevents any
DoS vector from repeat cache misses.

### P3-3: `/api/dev/diagrams` POST route does not validate the `data` object size or structure beyond type check

**File:** `frontend/app/api/dev/diagrams/[name]/route.ts`, lines 70-74

**Problem:** The PUT handler checks `typeof data !== 'object'` but does not
limit the depth or number of keys of the object before serialising it to disk.
A deeply nested or very large payload could trigger stack overflow during
`JSON.stringify` or produce a very large file. This is a dev-only route, but
defence in depth is still valuable.

**Recommendation:** Add a raw body size limit (check `Content-Length` header or
read body as a limited buffer) before parsing. A 2 MB cap is reasonable for
Excalidraw diagrams.

### P3-4: `authPaths` redirect does not include `/auth/reset-password` or `/auth/verify-email`

**File:** `frontend/middleware.ts`, lines 32-33

**Problem:** The `authPaths` array redirects authenticated users away from login
and signup pages. It does not include `/auth/reset-password` or
`/auth/verify-email`. An already-authenticated user visiting a password-reset
link will be served the page instead of being redirected, which could cause
confusing UX (e.g. they inadvertently change the password of whoever owns the
token, if the token was somehow obtained for a different account).

**Recommendation:** Consider adding `/auth/reset-password` and
`/auth/verify-email` to `authPaths` so authenticated users are redirected away,
or add a route-level check to confirm the session user matches the token's
target user.

### P3-5: Better Auth `onAPIError: { throw: true }` surfaces raw exceptions

**File:** `frontend/lib/auth/server.ts`, lines 129-131

**Problem:** Setting `throw: true` causes Better Auth to re-throw raw exceptions
from its internal handlers. The `wrapHandler` function in `route.ts` catches
these and returns `{ error: "Internal auth error" }`, which is correct. However,
if the Better Auth library throws an error object that has a `toJSON()` or
`toString()` that includes database details, those details will be in the
`console.error` output (line 38 in `route.ts`) and could surface in structured
log drains.

**Recommendation:** In the `catch` block in `wrapHandler`, sanitise the error
before logging: log only `error.constructor.name` and a safe `.message` with
potential database identifiers redacted (e.g. strip connection strings from the
message using a regex).

---

## Summary

P0:2 P1:4 P2:5 P3:5
