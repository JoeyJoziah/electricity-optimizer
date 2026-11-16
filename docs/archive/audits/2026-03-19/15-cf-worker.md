# Audit Report: Cloudflare Worker Edge Layer
**Date:** 2026-03-19
**Scope:** API gateway worker — routing, caching, rate limiting, security, cron triggers
**Files Reviewed:**
- `workers/api-gateway/src/index.ts`
- `workers/api-gateway/src/config.ts`
- `workers/api-gateway/src/types.ts`
- `workers/api-gateway/src/router.ts`
- `workers/api-gateway/src/middleware/cors.ts`
- `workers/api-gateway/src/middleware/security.ts`
- `workers/api-gateway/src/middleware/internal-auth.ts`
- `workers/api-gateway/src/middleware/rate-limiter.ts`
- `workers/api-gateway/src/middleware/cache.ts`
- `workers/api-gateway/src/middleware/observability.ts`
- `workers/api-gateway/src/handlers/proxy.ts`
- `workers/api-gateway/src/handlers/scheduled.ts`
- `workers/api-gateway/test/security.test.ts`
- `workers/api-gateway/test/cors.test.ts`
- `workers/api-gateway/test/internal-auth.test.ts`
- `workers/api-gateway/test/graceful-degradation.test.ts`
- `workers/api-gateway/test/middleware-ordering.test.ts`
- `workers/api-gateway/test/observability.test.ts`
- `workers/api-gateway/test/scheduled.test.ts`
- `workers/api-gateway/test/router.test.ts`
- `workers/api-gateway/wrangler.toml`
- `workers/api-gateway/package.json`
- `workers/api-gateway/tsconfig.json`

---

## P0 — Critical (Fix Immediately)

### P0-1: Rate Limit Bypass Key Uses Non-Constant-Time String Comparison

**File:** `workers/api-gateway/src/middleware/rate-limiter.ts`, line 26

The `X-RateLimit-Bypass` header is compared against `env.RATE_LIMIT_BYPASS_KEY` using JavaScript's `===` operator, which is **not** constant-time. While the internal API key comparison in `internal-auth.ts` correctly uses `crypto.subtle.timingSafeEqual`, this bypass key check uses a direct equality test. An attacker who can measure response timing at scale (feasible against an edge worker with sub-millisecond timing resolution) could progressively extract the bypass key byte-by-byte.

```typescript
// Line 26 — vulnerable to timing attack
if (bypassKey && env.RATE_LIMIT_BYPASS_KEY && bypassKey === env.RATE_LIMIT_BYPASS_KEY) {
```

**Impact:** If the bypass key is discovered, an attacker could bypass rate limiting on all internal endpoints (which are already API-key-gated, reducing severity somewhat, but it breaks defense-in-depth).

**Remediation:** Use the same `timingSafeEqual` function from `internal-auth.ts` for this comparison, or extract it to a shared utility.

---

### P0-2: Scheduled Handler Sends Empty String as API Key When Secret Is Unset

**File:** `workers/api-gateway/src/handlers/scheduled.ts`, line 54

When `INTERNAL_API_KEY` is not configured, the cron handler sends `X-API-Key: ""` (empty string) to the origin. The origin's `validateInternalAuth` in the Worker will 503 on the same request if it arrives via fetch, but the scheduled handler calls origin **directly** bypassing the Worker's own fetch handler. If the backend's internal auth middleware treats an empty API key as valid (or has a misconfiguration), this creates an authentication bypass.

```typescript
// Line 54 — sends empty string API key
"X-API-Key": env.INTERNAL_API_KEY ?? "",
```

**Impact:** Cron jobs silently fail-open with no authentication header value. This is a correctness issue that could escalate to a security issue if the backend's API key validation is not strict about empty strings. The test on line 129-145 of `scheduled.test.ts` actually documents this behavior as expected, which is concerning.

**Remediation:** If `INTERNAL_API_KEY` is undefined, the handler should log an error and abort rather than making an unauthenticated call to the origin. Fail-closed, matching the pattern in `internal-auth.ts`.

---

## P1 — High (Fix This Sprint)

### P1-1: Missing `Host` Header Override in Proxy Creates SSRF-Adjacent Risk

**File:** `workers/api-gateway/src/handlers/proxy.ts`, lines 17-27

The proxy forwards the original request's `Host` header to the origin. The code sets `X-Forwarded-Host` but does **not** override the `Host` header itself to match the origin. If the Render backend uses the `Host` header for any internal routing, URL generation, or security decisions, a crafted `Host` header from the client propagates directly to origin.

```typescript
const headers = new Headers(request.headers);  // copies Host from client request
headers.set("X-Forwarded-Host", url.hostname);
// Host is NOT overridden to env.ORIGIN_URL hostname
```

While Cloudflare's `fetch()` typically overrides `Host` to match the URL, this behavior depends on the runtime and is not guaranteed. The defensive practice is to explicitly set `Host` to the origin hostname.

**Remediation:** Add `headers.set("Host", new URL(env.ORIGIN_URL).hostname);` after line 22.

---

### P1-2: Cache Poisoning via Unvalidated Query Parameter Values

**File:** `workers/api-gateway/src/router.ts`, lines 21-43; `workers/api-gateway/src/middleware/cache.ts`, lines 11-66

The cache key is built from `varyOn` query parameters (e.g., `region`, `utility_type`) with URI encoding, but there is **no validation** that these parameter values are legitimate. An attacker can send arbitrarily large or numerous distinct `region` values (e.g., `?region=AAAA...`, `?region=BBBB...`) to flood KV with cache entries. Each unique value creates a new KV write and Cache API entry.

```typescript
// router.ts line 34-35 — accepts any value without validation
const val = searchParams.get(key);
if (val !== null) {
  parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(val)}`);
}
```

**Impact:** KV write quota exhaustion (KV has per-day write limits on the free/paid plans). Cache storage bloat. Potential cost escalation on paid KV plans.

**Remediation:** Validate `varyOn` parameter values against a whitelist (e.g., validate `region` against the Region enum before including it in the cache key). Alternatively, cap the maximum length of each parameter value used in cache keys (e.g., 64 characters).

---

### P1-3: `DELETE` Method Body Not Forwarded by Proxy

**File:** `workers/api-gateway/src/handlers/proxy.ts`, line 30

The proxy only forwards request bodies for `POST`, `PUT`, and `PATCH` methods. `DELETE` requests with a body (which some APIs use for batch deletion endpoints, e.g., GDPR data deletion) will have their body silently dropped.

```typescript
// Line 30 — DELETE is not listed
const hasBody = ["POST", "PUT", "PATCH"].includes(request.method);
```

**Impact:** If any backend endpoint accepts `DELETE` with a request body, the request will arrive at the origin with no body, potentially causing silent failures or incorrect behavior. The GDPR compliance endpoints (`/compliance/gdpr/delete`) accept POST but this warrants verification across all endpoints.

**Remediation:** Add `"DELETE"` to the `hasBody` array, or better, forward the body unconditionally and let the origin decide (the HTTP spec allows bodies on any method).

---

### P1-4: Missing `Permissions-Policy` and `Content-Security-Policy` Security Headers

**File:** `workers/api-gateway/src/middleware/security.ts`, lines 54-63

The security headers applied to every response are missing several recommended headers:

- **`Permissions-Policy`**: Not set. Browsers will use defaults, allowing access to camera, microphone, geolocation, etc. via embedded content.
- **`X-XSS-Protection`**: Not set. While modern browsers have deprecated this in favor of CSP, setting `X-XSS-Protection: 0` explicitly prevents XSS auditor quirks in older browsers.
- **`Content-Security-Policy`**: Not set at the edge layer. While the frontend may set its own CSP, API responses should include at minimum `default-src 'none'` to prevent any unintended content rendering if an API response is opened directly in a browser.

```typescript
return {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Request-ID": requestId,
  "X-Edge-Colo": colo,
  // Missing: Permissions-Policy, Content-Security-Policy
};
```

**Remediation:** Add:
- `"Permissions-Policy": "camera=(), microphone=(), geolocation=()"`
- `"Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"`
- `"X-XSS-Protection": "0"` (explicit disable per OWASP recommendation)

---

### P1-5: HSTS Header Missing `preload` Directive

**File:** `workers/api-gateway/src/middleware/security.ts`, line 58

The `Strict-Transport-Security` header includes `includeSubDomains` but is missing the `preload` directive. Without `preload`, the domain cannot be submitted to the HSTS preload list (hstspreload.org), leaving a window for MITM attacks on first visit.

```typescript
"Strict-Transport-Security": "max-age=31536000; includeSubDomains",
// Should be: "max-age=31536000; includeSubDomains; preload"
```

**Remediation:** Add `; preload` to the HSTS header value. Ensure all subdomains support HTTPS before enabling.

---

## P2 — Medium (Fix Soon)

### P2-1: Bot Detection Easily Bypassed by Spoofed Headers

**File:** `workers/api-gateway/src/middleware/security.ts`, lines 5-42

The bot detection is entirely heuristic-based on trivially spoofable request headers. Any bot operator can pass the scoring by including: a Chrome-like `User-Agent`, `Accept: application/json`, `Accept-Language`, and `Accept-Encoding` headers, achieving a score of 90/100 (baseline 50 + browser UA 20 + Accept 10 + Accept-Language 5 + Accept-Encoding 5).

The scoring provides minimal protection against automated tools like `puppeteer`, `playwright`, or even `curl` with custom headers. The threshold of `< 20` to block is very permissive.

```typescript
// Lines 21-23 — trivially spoofed
if (/Mozilla\/5\.0/.test(ua) && /Chrome|Firefox|Safari|Edge/.test(ua)) {
  score += 20;
}
```

**Impact:** The bot detection is more of a filter for unconfigured scrapers than a real security control. Determined bots pass trivially.

**Remediation:** Consider integrating Cloudflare's native Bot Management (available on paid plans) or Turnstile for critical endpoints. Document that the current heuristic is a low-confidence signal only. Consider adding IP reputation, TLS fingerprinting (JA3), or request frequency analysis.

---

### P2-2: Client IP Extraction Falls Back to `X-Forwarded-For` Which Is Spoofable

**File:** `workers/api-gateway/src/index.ts`, lines 20-23

When `CF-Connecting-IP` is not present (should not happen in production behind Cloudflare), the code falls back to the `X-Forwarded-For` header, which is client-controlled and spoofable. This IP is used as the rate limiting key.

```typescript
const clientIp =
  request.headers.get("CF-Connecting-IP") ??
  request.headers.get("X-Forwarded-For")?.split(",")[0]?.trim() ??
  "unknown";
```

An attacker who can craft a request where `CF-Connecting-IP` is absent (e.g., during local development, or if the Worker processes requests not routed through Cloudflare's proxy) could spoof `X-Forwarded-For` to bypass per-IP rate limiting entirely by rotating fake IP addresses.

Additionally, the fallback to `"unknown"` means if both headers are missing, ALL such requests share a single rate limit bucket, creating either a denial-of-service for legitimate users behind that bucket or a bypass if the bucket is not rate-limited.

**Remediation:** In production, `CF-Connecting-IP` should always be present. Consider logging a warning when falling back to `X-Forwarded-For` and treating it as suspicious. The `"unknown"` fallback should be replaced with a stricter behavior (e.g., rate limit aggressively for unidentified clients).

---

### P2-3: Cached Responses May Leak `Set-Cookie` or Authorization Headers

**File:** `workers/api-gateway/src/middleware/cache.ts`, lines 86-98

When storing responses in cache, the code stores **all** response headers from origin (`Object.fromEntries(response.headers.entries())`), which may include `Set-Cookie`, `Authorization`, or other sensitive per-user headers. If the origin ever returns `Set-Cookie` on a cacheable endpoint (e.g., session tokens on `/api/v1/prices/current`), those cookies would be served to all subsequent users from cache.

```typescript
// Line 87 — stores ALL headers, including potentially sensitive ones
const storedHeaders = Object.fromEntries(response.headers.entries());
```

**Impact:** Cookie or auth token leakage across users if the origin returns per-user headers on cacheable routes.

**Remediation:** Strip sensitive headers before caching: `Set-Cookie`, `Authorization`, `WWW-Authenticate`, `Proxy-Authorization`, `Cookie`. Add a header sanitization step before line 92.

---

### P2-4: No Request Body Size Limit on Proxy

**File:** `workers/api-gateway/src/handlers/proxy.ts`, lines 29-37

The proxy forwards request bodies of arbitrary size to the origin without any size validation. While Cloudflare Workers have a 100MB limit, an attacker could send large payloads to consume Worker CPU time and origin bandwidth.

```typescript
// Line 35 — no body size validation
body: hasBody ? request.body : undefined,
```

**Remediation:** For non-file-upload endpoints, consider reading the body and rejecting requests over a reasonable threshold (e.g., 1MB for JSON API endpoints). File upload endpoints can be exempted via route configuration.

---

### P2-5: Cache Key Does Not Include HTTP Method

**File:** `workers/api-gateway/src/router.ts`, lines 21-43; `workers/api-gateway/src/middleware/cache.ts`, lines 18-19

The `tryCache` function correctly rejects non-GET requests (lines 18-19), but `storeInCache` does not check the request method, and the cache key itself does not include the method. If a POST response with status 200 is somehow stored (the guard is in `index.ts` line 169 which checks `response.status === 200` but not `request.method`), it could be served to subsequent GET requests for the same path.

Looking at `index.ts` line 169:
```typescript
if (route.cache && !route.passthrough && response.status === 200) {
  recordCacheWrite();
  ctx.waitUntil(storeInCache(response, route.cache, url, env, ctx));
}
```

This runs for ANY method (including POST) as long as the route is cacheable and the response is 200. If someone POSTs to `/api/v1/prices/current` (which has a cache config), the POST response body would be stored in the cache and served to subsequent GET requests.

**Remediation:** Add a method check in the cache store logic at `index.ts` line 169: `if (route.cache && !route.passthrough && response.status === 200 && request.method === "GET")`.

---

### P2-6: `price-sync` Cron Route Targets `/api/v1/prices/refresh` Which Is Not an Internal Endpoint

**File:** `workers/api-gateway/src/handlers/scheduled.ts`, lines 28-32

The `price-sync` cron route calls `/api/v1/prices/refresh`, which in the route configuration (`config.ts` line 33-36) is defined with `strict` rate limiting and **no** `requireApiKey`. However, the scheduled handler sends the `X-API-Key` header anyway (line 53). The endpoint itself does not require API key auth at the Worker level.

More importantly, `/api/v1/prices/refresh` is a publicly accessible route (no API key required at the Worker level). An attacker could trigger price refreshes by POSTing to this endpoint, potentially causing excessive backend load or cache invalidation storms.

```typescript
// config.ts lines 33-36 — no requireApiKey
{
  pattern: /^\/api\/v1\/prices\/refresh$/,
  rateLimit: "strict",
},
```

**Impact:** External actors can trigger cache invalidation and backend scraping workload by calling `POST /api/v1/prices/refresh`, limited only by strict rate limiting (30/min).

**Remediation:** Either add `requireApiKey: true` to the prices/refresh route, or ensure the backend itself validates the API key for this endpoint. Price refresh should be internal-only.

---

### P2-7: `Vary` Header in Cache Entry Set to Query Param Names, Not HTTP Headers

**File:** `workers/api-gateway/src/middleware/cache.ts`, lines 88-89

The `Vary` header is set to query parameter names (e.g., `region, utility_type`) rather than HTTP request headers. The `Vary` header is meant to specify which **request headers** cause cache variation. Setting it to query param names is semantically incorrect and could confuse downstream caches (CDNs, browser caches) into incorrect cache behavior.

```typescript
if (cacheConfig.varyOn && cacheConfig.varyOn.length > 0) {
  storedHeaders["Vary"] = cacheConfig.varyOn.join(", ");
}
```

**Impact:** Downstream caches may not correctly discriminate between responses for different query parameters, potentially serving the wrong cached response.

**Remediation:** Remove the `Vary` header from the cache entry since variation is already handled via the cache key. If HTTP header variation is needed, define separate `varyOnHeaders` in the `CacheConfig` type.

---

### P2-8: Observability Logs Client IP Addresses — GDPR Compliance Concern

**File:** `workers/api-gateway/src/middleware/observability.ts`, lines 115-140; `workers/api-gateway/src/index.ts`, line 227

The structured log entry includes `clientIp` in plaintext. Under GDPR, IP addresses are considered personal data. Logging them without anonymization, a documented legal basis, and defined retention periods is a compliance risk, especially given the project already has GDPR compliance features in the backend.

```typescript
// observability.ts line 135
clientIp: params.clientIp,
```

**Impact:** GDPR non-compliance for EU users. Cloudflare Worker logs are retained per Cloudflare's retention policies, which may not align with the project's data privacy commitments.

**Remediation:** Hash or truncate IP addresses in logs (e.g., zero the last octet for IPv4, last 80 bits for IPv6). Document the legal basis for any retained IP data. Align retention with the project's GDPR policy.

---

## P3 — Low / Housekeeping

### P3-1: CORS Preflight Without `Origin` Header Returns 204 Instead of 400

**File:** `workers/api-gateway/src/middleware/cors.ts`, lines 16-18

When an OPTIONS request arrives without an `Origin` header, the handler returns `204 No Content` with no CORS headers. While not a security vulnerability, this is a deviation from the CORS specification — a preflight without `Origin` is technically invalid and returning 204 may mask client-side misconfigurations.

```typescript
if (!origin) {
  return new Response(null, { status: 204 });
}
```

**Remediation:** Consider returning 400 for OPTIONS requests without an `Origin` header, or at minimum log it as a warning for monitoring.

---

### P3-2: Log Entry `status` Field Is Always 0

**File:** `workers/api-gateway/src/index.ts`, line 224

The log entry always records `status: 0` because logging happens in the `finally` block before the response status is known. The comment acknowledges this ("logged before we know"), but this makes the structured logs significantly less useful for monitoring and alerting.

```typescript
status: 0, // logged before we know -- structured log enriched by CF
```

**Remediation:** Refactor to capture the response status before the `finally` block. One approach: set a mutable `let responseStatus = 0` at the top and update it before each `return`.

---

### P3-3: `resetMetrics()` Exported for Tests But Available in Production

**File:** `workers/api-gateway/src/middleware/observability.ts`, line 71

The `resetMetrics()` function resets all observability counters. While it is documented as "exposed for tests only," it is a regular export that could be called from any module. In Workers, there is no separate test build, so this function exists in the production bundle.

**Impact:** No direct attack vector since it is not exposed via any route, but it is unnecessary surface area.

**Remediation:** Consider using `vitest`'s module mocking to access internals during testing rather than exporting a reset function in production code.

---

### P3-4: `tsconfig.json` Excludes `test/` Directory From Type Checking

**File:** `workers/api-gateway/tsconfig.json`, line 17

The `exclude` array includes `test`, meaning TypeScript does not type-check test files during `tsc --noEmit`. Type errors in tests would only surface when vitest runs them, not during the `typecheck` npm script.

```json
"exclude": ["node_modules", "test"]
```

**Remediation:** Create a separate `tsconfig.test.json` that extends the base config and includes the test directory, or add a `typecheck:test` script.

---

### P3-5: No Test Coverage for `proxyToOrigin` Function

**File:** `workers/api-gateway/src/handlers/proxy.ts`

There are no dedicated unit tests for the `proxyToOrigin` function. The proxy is tested indirectly through the integration tests in `middleware-ordering.test.ts`, but edge cases like header forwarding, body handling for different methods, and redirect behavior are not directly tested.

**Remediation:** Add unit tests for `proxyToOrigin` covering: header forwarding/stripping, body forwarding for each HTTP method, redirect pass-through, and error scenarios.

---

### P3-6: `wrangler.toml` Contains Production KV Namespace ID

**File:** `workers/api-gateway/wrangler.toml`, line 12

The production KV namespace ID (`6946d19ce8264f6fae4481d6ad8afcd1`) is committed to the repository. While KV namespace IDs are not secret (they require API auth to access), committing them increases the surface for targeted attacks if an attacker obtains API credentials.

```toml
kv_namespaces = [
  { binding = "CACHE", id = "6946d19ce8264f6fae4481d6ad8afcd1" }
]
```

**Remediation:** Low priority, but consider using `wrangler.toml` environment sections and keeping production IDs in environment-specific config or CI secrets.

---

### P3-7: No Rate Limiting on Cache-Served `/health` Endpoint

**File:** `workers/api-gateway/src/config.ts`, lines 93-99

The `/health` endpoint has `rateLimit: "bypass"` and a 30-second cache. While bypassing rate limiting for health checks is common, an attacker could use the health endpoint as a low-cost fingerprinting mechanism or load generator during the 30-second cache refresh windows.

**Remediation:** Consider using `standard` rate limiting for `/health` or at minimum ensuring the cache hit path handles the load. Current setup is reasonable for most threat models.

---

### P3-8: `ALLOWED_ORIGINS` Hardcoded in `wrangler.toml` Without Staging Variant

**File:** `workers/api-gateway/wrangler.toml`, line 41

The `ALLOWED_ORIGINS` only includes production origins. There is no staging/preview environment configuration. If a staging environment exists (e.g., preview deployments on Vercel), requests from those origins would fail CORS checks.

```toml
ALLOWED_ORIGINS = "https://rateshift.app,https://www.rateshift.app"
```

**Remediation:** Add a `[env.staging]` section in `wrangler.toml` with staging origins, or use `wrangler secret put ALLOWED_ORIGINS` to manage origins per environment.

---

## Files With No Issues Found

- `workers/api-gateway/test/cors.test.ts` — Tests are well-structured and cover allowed/disallowed origins and no-Origin cases.
- `workers/api-gateway/test/internal-auth.test.ts` — Covers fail-closed, missing key, wrong key, matching key, and different-length keys.
- `workers/api-gateway/test/graceful-degradation.test.ts` — Comprehensive coverage of fail-open behavior for both rate limiter and cache.
- `workers/api-gateway/test/observability.test.ts` — Thorough coverage of counter increments, stats shape, and hit rate calculation.
- `workers/api-gateway/test/router.test.ts` — Good coverage of route matching and cache key building.

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| P0 Critical | 2 | Timing-unsafe bypass key comparison; scheduled handler sends unauthenticated requests when secret is unset |
| P1 High | 5 | Missing Host header override; cache poisoning via unbounded query params; missing security headers (CSP, Permissions-Policy); HSTS missing preload; DELETE body dropped |
| P2 Medium | 8 | Bot detection trivially bypassable; spoofable IP fallback; cached Set-Cookie leakage; no body size limit; cache key ignores method; price-sync endpoint publicly accessible; invalid Vary header semantics; GDPR IP logging |
| P3 Low | 8 | OPTIONS without Origin returns 204; log status always 0; resetMetrics exported; tests excluded from typecheck; no proxy unit tests; committed KV namespace ID; health endpoint bypass; no staging CORS |
| **Total** | **23** | |

**Overall Assessment:** The Cloudflare Worker edge layer is architecturally sound with good separation of concerns, proper fail-open/fail-closed patterns, comprehensive graceful degradation, and solid test coverage (90 tests across 8 test files). The two P0 findings center on a timing-unsafe comparison and a fail-open authentication gap in the cron handler. The most impactful P1/P2 issues are the missing security headers (CSP, Permissions-Policy), cache poisoning risk from unvalidated query parameters, and the publicly-accessible price-refresh endpoint that should be internal-only. The 90-test suite covers most critical paths but lacks direct proxy handler tests and cache poisoning scenarios. No evidence of SQL injection, XSS, or path traversal vulnerabilities was found. Internal route authentication uses the correct fail-closed pattern with constant-time comparison. CORS validation is strict and correct. The codebase would benefit from a security headers hardening pass and tighter input validation on cache-key-generating parameters.
