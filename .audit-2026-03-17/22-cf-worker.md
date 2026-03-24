# Audit Report: Cloudflare Worker (API Gateway)
## Date: 2026-03-17

---

### Executive Summary

The `rateshift-api-gateway` CF Worker is a well-structured, purpose-built API gateway
covering CORS, bot detection, two-tier caching (Cache API + KV), native rate limiting
bindings, internal API-key auth, and three cron-triggered scheduled tasks. The code is
clean and consistently typed, error paths follow a deliberate fail-open / graceful
degradation strategy, and the 90-test suite exercises all critical middleware paths with
good coverage of degradation scenarios.

No P0 (auth bypass / credential-theft CORS) issues were found. The most significant
findings are a **P1 cache-poisoning vector** via unsanitised query parameters in cache
keys, a **P1 rate-limit bypass on webhook endpoints**, a **P1 missing `Vary` response
header** that causes intermediate proxy cache divergence, and several P2 configuration
and observability gaps. None of the issues are show-stoppers for the current traffic
profile, but the cache-key injection and the webhook bypass should be addressed before
any public launch campaign.

---

### Findings

---

#### P0 — Critical

*No P0 findings.*

Auth is fail-closed (503 when `INTERNAL_API_KEY` is unset), timing-safe comparison is
implemented correctly, and CORS origin matching is an exact-match allowlist — not a
prefix or regex — so no subdomain takeover or credential-theft scenario was identified.

---

#### P1 — High

---

##### P1-01 — Cache Key Injection via Unsanitised Query Parameter Values

**File**: `src/router.ts` lines 21–43; `src/middleware/cache.ts` lines 22, 83

**Description**

`buildCacheKey` constructs KV keys of the form `rsgw:/path|param=value`. The `value` is
taken verbatim from `URLSearchParams.get()` with no sanitisation. A pipe character (`|`)
is the delimiter, so a crafted request such as:

```
GET /api/v1/prices/current?region=NY|utility_type=commercial
```

produces the key:

```
rsgw:/api/v1/prices/current|region=NY|utility_type=commercial
```

which is **identical** to the key produced by:

```
GET /api/v1/prices/current?region=NY&utility_type=commercial
```

An attacker who can write a valid cached response for the first request can cause the
second (legitimate) request to be served the crafted body. The impact is read-only (the
attacker can only poison with content the origin already accepted), but it allows a user
to serve arbitrary cached responses to other users for the same logical resource.

The same pipe character also leaks into the KV key prefix used for cache invalidation in
`PRICE_CACHE_PATTERNS`, potentially preventing invalidation of deliberately poisoned keys
(those that sort outside the expected prefix range).

**Recommendation**

Percent-encode (or strip) the pipe character from all `varyOn` values before
concatenating:

```typescript
// router.ts — buildCacheKey
const encodedVal = encodeURIComponent(val); // replaces | with %7C
parts.push(`${key}=${encodedVal}`);
```

Alternatively, use a separator that cannot appear in a percent-encoded value, such as
`\x00` (null byte). Also add a test covering `region=NY|utility_type=foo` to confirm the
key is distinct from `region=NY` + `utility_type=foo` in separate params.

---

##### P1-02 — Webhook Route Bypasses All Rate Limiting and Bot Detection

**File**: `src/config.ts` lines 4–9; `src/index.ts` lines 66–78, 148–163

**Description**

The `/api/v1/webhooks/*` route is configured with `rateLimit: "bypass"` and
`passthrough: true`. Combined with the bot-detection guard that only fires on non-`requireApiKey` routes (step 3 in index.ts), the webhook path also skips bot scoring.
In practice, this means an unauthenticated caller can POST unlimited requests to
`/api/v1/webhooks/stripe` with any payload, at unlimited rate, bypassing both bot
detection and rate limiting.

Stripe's own webhook deliveries include a `Stripe-Signature` header, so the backend
validates authenticity there. However, the CF Worker adds **no friction** to actors who
wish to:

1. Flood the Render backend with large POST bodies (cost/resource exhaustion).
2. Replay valid Stripe signatures captured from logs or network traffic.

**Recommendation**

Apply `rateLimit: "standard"` (120/min) to the webhook route instead of `"bypass"`. The
Stripe documentation explicitly states their delivery rate is at most a few per second,
so 120/min per IP will never affect legitimate deliveries. Additionally, consider adding
a lightweight content-length check (e.g., reject > 1 MB without reading the body) to
prevent body-based resource exhaustion.

```typescript
// config.ts
{
  pattern: /^\/api\/v1\/webhooks\//,
  rateLimit: "standard",   // was "bypass"
  passthrough: true,
},
```

---

##### P1-03 — Missing `Vary` Header on Cached Responses Causes Intermediate Proxy Divergence

**File**: `src/middleware/cache.ts` lines 107–119 (`storeInCache`), lines 170–176 (`buildCachedResponse`)

**Description**

When a response is written to the Cache API tier, the stored `Response` object does not
include a `Vary` header reflecting which query parameters were used to partition the
cache key. Any intermediate CDN, load balancer, or browser that caches the response
independently will serve the same body to all requests for the base path regardless of
query parameters.

For example, a Vercel Edge Network node (or even browser cache) that caches
`/api/v1/prices/current?region=NY` may subsequently serve that body to a request for
`/api/v1/prices/current?region=CA`. The CF Worker's own two-tier logic is unaffected
(it uses explicit key construction), but the absence of `Vary` means correctness depends
entirely on the Worker being the sole cache layer.

**Recommendation**

For routes with `varyOn`, inject a `Vary` header naming those parameters, and set
`Cache-Control: private` or `no-store` on responses that should not be
re-cached downstream:

```typescript
// storeInCache — when building the Cache API response
"Vary": cacheConfig.varyOn ? cacheConfig.varyOn.join(", ") : undefined,
"Cache-Control": `public, max-age=${cacheConfig.ttlSeconds}`,
```

Alternatively, mark all cacheable API responses `Cache-Control: no-store` at the origin
so that only the CF Worker tier caches them.

---

#### P2 — Medium

---

##### P2-01 — Rate Limit Key is IP-Only; Trivially Bypassed with IPv6 Rotation

**File**: `src/middleware/rate-limiter.ts` line 41

**Description**

```typescript
const { success } = await binding.limit({ key: clientIp });
```

The rate limit key is the raw client IP address. On IPv6 networks (and via many mobile
carriers or residential proxy providers) a single user may trivially exhaust or rotate
through thousands of `/64` prefixes, effectively bypassing per-IP limits. For the
`strict` tier (auth endpoints, 30/min) this is material because brute-force protection
depends on the key being stable per user.

**Recommendation**

Supplement or replace IP with a fingerprint that is harder to rotate. Options in order
of complexity:

1. Use the `/48` prefix for IPv6 (truncate the last 16 bits of the host portion):
   ```typescript
   function normaliseIp(ip: string): string {
     if (ip.includes(":")) {
       // IPv6: use /48 prefix (first 6 groups)
       const parts = ip.split(":");
       return parts.slice(0, 3).join(":") + "::/48";
     }
     return ip;
   }
   ```
2. For auth endpoints, combine IP + `User-Agent` hash as the key.
3. Use Cloudflare's `cf.botManagement.score` (if on Business/Enterprise plan) as an
   additional gate before the rate limiter.

---

##### P2-02 — `INTERNAL_API_KEY` Sent as Empty String from Cron Handler When Secret Is Absent

**File**: `src/handlers/scheduled.ts` line 54

**Description**

```typescript
"X-API-Key": env.INTERNAL_API_KEY ?? "",
```

When `INTERNAL_API_KEY` is not configured, the cron handler falls back to sending an
empty string. The origin backend's `validateInternalAuth` will likely reject this with a
401, which is the correct outcome — but the cron handler only logs a non-OK status
(`console.error`). There is no alerting path and no `controller.noRetry()` call to
signal CF that the job is misconfigured and should not be retried.

Additionally, the test for this case at `scheduled.test.ts` line 129–145 asserts that
`X-API-Key: ""` is sent rather than asserting that the task exits gracefully — it
effectively documents the fallback without asserting the desired guard behaviour.

**Recommendation**

Fail fast at the start of `handleScheduled` if the secret is absent:

```typescript
if (!env.INTERNAL_API_KEY) {
  console.error(`${route.name}: INTERNAL_API_KEY not configured — skipping`);
  controller.noRetry(); // tell CF not to retry a misconfiguration
  return;
}
```

---

##### P2-03 — Cache Invalidation Is Not Atomic; Stale Entries Can Serve Between List and Delete

**File**: `src/middleware/cache.ts` lines 129–167 (`invalidatePriceCache`)

**Description**

The invalidation flow:
1. `CACHE.list({ prefix })` — returns a snapshot of key names.
2. For each key, issues a `CACHE.delete(key.name)` asynchronously.

Between the list call and the last delete, any new cache write for the same prefix can
create a key that is never deleted. More importantly, if a new request is served a stale
KV entry and triggers a background refresh (stale-while-revalidate) concurrently with
invalidation, the refresh can re-populate KV with the old value after the delete — a
classic TOCTOU window.

This is inherent to the KV list-then-delete pattern and not fully solvable without
distributed locks, but the risk is low given current traffic. However, documenting the
limitation and setting a short post-invalidation grace period on affected routes would
reduce the window.

**Recommendation**

After issuing the deletes, insert a short TTL override on the KV entry
(e.g., `expirationTtl: 1`) rather than deleting — this allows the KV put-on-delete
semantic to clear the entry atomically relative to KV's eventual-consistency model.
Alternatively, add a comment in the code acknowledging the TOCTOU window so future
maintainers do not assume it is atomic.

---

##### P2-04 — Log Entry `status` Field Is Always `0` (Not Enriched)

**File**: `src/index.ts` lines 221–233

**Description**

```typescript
buildLogEntry({
  ...
  status: 0, // logged before we know — structured log enriched by CF
  ...
})
```

The `status` field is hard-coded to `0` in every log entry. The comment says CF enriches
it, but Cloudflare Workers logs emitted via `console.log` are NOT automatically enriched
with the HTTP response status. CF's analytics/logpush products operate on a separate
plane and do not backfill `console.log` output. Observability dashboards or alerting
rules that filter on `status >= 500` in the JSON log will never fire.

**Recommendation**

Track the response status from the returned `Response` object and pass it to the log
entry. This requires lifting the `response` variable into the outer scope:

```typescript
// in the finally block, capture actual status
ctx.waitUntil(
  Promise.resolve().then(() =>
    logRequest(
      buildLogEntry({
        ...
        status: _responseStatus, // set at each return point
        ...
      })
    )
  )
);
```

A cleaner pattern is to resolve the response inside `fetch()`, set a module-scoped
`let status = 0`, and update it before every `return` statement.

---

##### P2-05 — `Strict-Transport-Security` Header Missing `preload` Directive

**File**: `src/middleware/security.ts` line 58

**Description**

```typescript
"Strict-Transport-Security": "max-age=31536000; includeSubDomains",
```

The HSTS header does not include `preload`. For a production API domain on `rateshift.app`
(with Cloudflare as registrar and SSL: Full Strict), the preload directive is the final
step to ensure browsers hard-code the HTTPS redirect without ever making a plaintext
request, even on first visit. Without `preload`, users who visit the origin directly for
the first time may be vulnerable to a downgrade attack if they bypass Cloudflare.

**Recommendation**

Add `preload` once the domain is listed in the HSTS Preload List submission:

```typescript
"Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
```

Note: `api.rateshift.app` is a subdomain; the apex `rateshift.app` must carry the header
for inclusion. Confirm Cloudflare's automatic HSTS setting for the zone before adding
`preload` here to avoid conflicts.

---

##### P2-06 — `Content-Security-Policy` Header Absent from API Responses

**File**: `src/middleware/security.ts` lines 54–63

**Description**

The security headers function emits `X-Content-Type-Options`, `X-Frame-Options`, HSTS,
and `Referrer-Policy`, but no `Content-Security-Policy`. While an API gateway that only
emits JSON responses does not strictly need a CSP (browsers enforce CSP on document
fetches, not `fetch()` API responses), there are two scenarios where its absence matters:

1. Any endpoint that could return HTML (error pages, redirects, or future admin panels
   proxied through the gateway) would have no CSP protection.
2. Some security scanners (Qualys, Observatory) flag its absence as a medium finding.

**Recommendation**

Add a restrictive CSP targeting the API nature of this gateway:

```typescript
"Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
```

`default-src 'none'` prevents resource loading from any response interpreted as a
document. `frame-ancestors 'none'` is redundant with `X-Frame-Options: DENY` but more
modern.

---

##### P2-07 — `price-sync` Cron Calls `/api/v1/prices/refresh` Which Is NOT an Internal Endpoint

**File**: `src/handlers/scheduled.ts` lines 27–31

**Description**

```typescript
"0 */6 * * *": {
  endpoint: "/api/v1/prices/refresh",
  name: "price-sync",
  method: "POST",
},
```

The `price-sync` cron posts to `/api/v1/prices/refresh`, which — per `src/config.ts`
line 36 — has `rateLimit: "strict"` but does **not** have `requireApiKey: true`. This
means:

1. The cron call sends `X-API-Key` in its headers, but the gateway route does not
   validate it (no `validateInternalAuth` call for this path).
2. Any external actor who discovers the endpoint can POST to it without an API key,
   triggering a price refresh and the associated cache invalidation.
3. Because the cron call is going directly to `env.ORIGIN_URL` (not through the Worker's
   own `fetch` handler), the strict rate limit at the Worker level does not apply to the
   cron itself — only to external callers of that path.

This is a logical inconsistency: the price-sync endpoint performs a privileged write
operation (flushing price caches, triggering a scrape) but is gated only by a 30/min IP
rate limit, not by API-key auth.

**Recommendation**

Either:

a) Move `/api/v1/prices/refresh` under the `/api/v1/internal/` prefix so it inherits
   `requireApiKey: true` and the internal rate limiter, or

b) Add an explicit route entry for `/api/v1/prices/refresh` with `requireApiKey: true`.

Update the cron entry to use the new internal path:

```typescript
"0 */6 * * *": {
  endpoint: "/api/v1/internal/price-sync",  // renamed internal path
  name: "price-sync",
  method: "POST",
},
```

---

##### P2-08 — Cache Stores Full Response Headers Including `Set-Cookie`

**File**: `src/middleware/cache.ts` lines 86–92

**Description**

```typescript
const entry: CacheEntry = {
  body,
  headers: Object.fromEntries(response.headers.entries()),
  ...
};
```

All response headers from the origin are stored verbatim in the KV cache entry. If the
origin ever returns a `Set-Cookie` header on a cacheable endpoint (e.g., a session
cookie on an analytics or prices endpoint that has a session refresh side-effect), that
cookie would be served from cache to all subsequent users who receive that cache entry.
This is a potential credential-leakage vector that is dormant today but could activate
if the origin behaviour changes.

**Recommendation**

Strip security-sensitive headers before caching:

```typescript
const CACHE_STRIP_HEADERS = ["set-cookie", "authorization", "www-authenticate"];

const headers = Object.fromEntries(
  [...response.headers.entries()].filter(
    ([key]) => !CACHE_STRIP_HEADERS.includes(key.toLowerCase())
  )
);
```

---

#### P3 — Low

---

##### P3-01 — Bot Detection Scores Are Not Logged Per-Request to Observability

**File**: `src/index.ts` lines 67, 224–233; `src/middleware/observability.ts`

**Description**

`botScore` is captured per-request and included in the `LogEntry` struct. However, there
is no counter for blocked bot requests in `gatewayMetrics` — only raw `botScore` in
individual log lines. The `/internal/gateway-stats` endpoint therefore cannot report bot
block rate, making it impossible to detect a scraping campaign from the stats endpoint
alone without parsing raw logs.

**Recommendation**

Add a `botBlocks` counter to `GatewayMetrics` and call `recordBotBlock()` at line 69–77
of `index.ts` when `shouldBlockBot(botScore)` returns true.

---

##### P3-02 — `vitest.config.*` File Is Absent; Vitest Runs with Default Config

**File**: `workers/api-gateway/` (root)

**Description**

There is no `vitest.config.ts` or `vitest.config.js`. Vitest runs with default settings,
which means:

- The test environment defaults to `node`, not `miniflare` or `workerd`. This means
  CF-specific globals (`caches`, `crypto.subtle.timingSafeEqual`, `ScheduledController`)
  must be manually stubbed in every test file — which they currently are, but any future
  test author may miss this requirement.
- No explicit include/exclude patterns, so any test file accidentally placed in
  `node_modules/` could theoretically be discovered (in practice Vitest excludes
  `node_modules` by default, but the intent is not explicit).
- Coverage is not configured; running `vitest --coverage` would use defaults without any
  threshold gates.

**Recommendation**

Add a minimal `vitest.config.ts`:

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["test/**/*.test.ts"],
    exclude: ["node_modules/**"],
    coverage: {
      provider: "v8",
      thresholds: { lines: 80, functions: 80, branches: 75 },
    },
  },
});
```

---

##### P3-03 — `wrangler.toml` Exposes Render `ORIGIN_URL` as a Plaintext `[vars]` Entry

**File**: `workers/api-gateway/wrangler.toml` lines 39–41

**Description**

```toml
[vars]
ORIGIN_URL = "https://electricity-optimizer.onrender.com"
ALLOWED_ORIGINS = "https://rateshift.app,https://www.rateshift.app"
```

`wrangler.toml` is committed to the repository. The Render internal hostname
(`electricity-optimizer.onrender.com`) is now publicly visible in version control. While
Render hostnames are not strictly secret, advertising the internal origin URL assists
attackers who wish to bypass the CF Worker and send requests directly to the Render
backend (which still needs its own auth layer for protection but loses the Worker's rate
limiting and bot detection).

**Recommendation**

Move `ORIGIN_URL` to a Wrangler secret (`wrangler secret put ORIGIN_URL`) or document
in the repo that direct-origin access is intentionally accepted risk (which it may be,
given Render's public routing). If moved to a secret, update `types.ts` to mark
`ORIGIN_URL` as required:

```typescript
ORIGIN_URL: string; // already required — but also set via secret
```

---

##### P3-04 — Webhook Route Pattern Is Overly Broad

**File**: `src/config.ts` line 7

**Description**

```typescript
pattern: /^\/api\/v1\/webhooks\//,
```

This matches any path under `/api/v1/webhooks/`, including hypothetical future paths
like `/api/v1/webhooks/internal-admin`. The pattern has no upper bound on specificity
and could inadvertently include endpoints that should not be passthroughs.

**Recommendation**

Enumerate the known webhook providers explicitly:

```typescript
pattern: /^\/api\/v1\/webhooks\/(stripe|sendgrid|onesignal)\//,
```

---

##### P3-05 — No `X-Robots-Tag` Header to Prevent Search Engine Indexing of API

**File**: `src/middleware/security.ts`

**Description**

The API gateway does not emit `X-Robots-Tag: noindex, nofollow`. While search engines
are unlikely to crawl API JSON responses, some bots honour this header to avoid indexing
error messages or JSON containing PII fragments. This is a low-severity gap.

**Recommendation**

Add to `getSecurityHeaders`:

```typescript
"X-Robots-Tag": "noindex, nofollow",
```

---

##### P3-06 — `observability.ts` `resetMetrics()` Is Public; Could Be Called Accidentally in Production

**File**: `src/middleware/observability.ts` lines 71–81

**Description**

`resetMetrics()` is exported from the module with only a JSDoc comment noting it is for
tests only. There is no runtime guard (e.g., `if (process.env.NODE_ENV !== 'production')`)
preventing it from being called from non-test code in a future refactor.

**Recommendation**

Either unexport the function and re-export it only in a test-specific barrel, or add a
naming convention like `_resetMetricsForTest()` with a leading underscore to signal
private intent. In TypeScript strict mode, the compiler will not help here, so naming is
the only signal.

---

##### P3-07 — `refreshCache` in `index.ts` Is a Module-Level Function Leaking Into Scope

**File**: `src/index.ts` lines 249–266

**Description**

`refreshCache` is defined at module scope as a plain `async function` rather than being
colocated with the cache middleware in `src/middleware/cache.ts`. This breaks the
single-responsibility grouping: all cache logic lives in `cache.ts` except this one
helper. It also means `refreshCache` is not unit-testable without importing the full
`index.ts` module.

**Recommendation**

Move `refreshCache` into `src/middleware/cache.ts` and export it. The function already
imports `proxyToOrigin` and `storeInCache`, both of which can be imported there without
circular dependencies.

---

##### P3-08 — Cron Handler Uses `route.method === "POST"` Check but All Routes Are POST

**File**: `src/handlers/scheduled.ts` lines 56–57

**Description**

```typescript
body: route.method === "POST" ? "{}" : undefined,
```

All three cron routes are defined as `method: "POST"`, so this ternary always evaluates
to `"{}"`. The conditional adds code-reading overhead without providing real flexibility.
If a GET-based cron route is ever added, it would correctly send no body — but adding a
`method` field to the route config already implies the caller knows the method. The
ternary is fine but slightly misleading.

**Recommendation**

Minor: remove the redundant check or add a comment clarifying the intent:

```typescript
body: "{}", // all scheduled triggers are POST with empty JSON body
```

---

### Statistics

| Severity | Count | Files Affected |
|----------|-------|----------------|
| P0 — Critical | 0 | — |
| P1 — High | 3 | router.ts, config.ts, cache.ts, scheduled.ts |
| P2 — Medium | 8 | rate-limiter.ts, scheduled.ts, cache.ts, index.ts, security.ts, config.ts |
| P3 — Low | 8 | observability.ts, index.ts, scheduled.ts, config.ts, security.ts, wrangler.toml |
| **Total** | **19** | |

**Files reviewed** (12 source + 6 tests = 18 total):

| File | Lines | Notes |
|------|-------|-------|
| `src/index.ts` | 267 | Main fetch + scheduled entrypoint |
| `src/config.ts` | 129 | Route table + cache key constants |
| `src/types.ts` | 84 | Shared TypeScript interfaces |
| `src/router.ts` | 43 | Route matching + cache key builder |
| `src/middleware/cors.ts` | 60 | CORS preflight + header injection |
| `src/middleware/security.ts` | 79 | Bot scoring + security headers |
| `src/middleware/internal-auth.ts` | 82 | X-API-Key validation + timing-safe compare |
| `src/middleware/rate-limiter.ts` | 126 | Native binding wrapper + fail-open |
| `src/middleware/cache.ts` | 201 | Two-tier cache read/write/invalidate |
| `src/middleware/observability.ts` | 141 | In-memory metrics + structured logging |
| `src/handlers/proxy.ts` | 47 | Origin proxy with header forwarding |
| `src/handlers/scheduled.ts` | 85 | Cron trigger handler + cold-start retry |
| `test/router.test.ts` | 104 | Route matching + cache key tests |
| `test/cors.test.ts` | 86 | CORS preflight + header tests |
| `test/security.test.ts` | 84 | Bot scoring + security header tests |
| `test/internal-auth.test.ts` | 51 | API key validation tests |
| `test/scheduled.test.ts` | 298 | Cron routing + retry tests |
| `test/graceful-degradation.test.ts` | 221 | KV/binding failure tests |
| `test/middleware-ordering.test.ts` | 323 | Cache-before-rate-limit ordering tests |
| `test/observability.test.ts` | 191 | Metrics counter + stats shape tests |

**Test coverage estimate**: 90 tests across 8 files. All middleware modules and the
scheduled handler have dedicated test files. Notable gaps: no integration test for the
cache-key injection scenario (P1-01), no test asserting that `/api/v1/prices/refresh`
requires auth (P2-07), and no test covering STALE response headers in the
middleware-ordering suite.

**Overall assessment**: The Worker is production-ready for its current traffic profile.
The P1 issues (cache-key injection, webhook rate-limit bypass, missing `Vary` header)
should be addressed before any high-volume marketing push. The P2 issues are good
hardening targets for the next sprint.
