# Infrastructure & Cloudflare Worker Security Audit

**Date**: 2026-03-16
**Auditor**: Security Engineer (automated review)
**Scope**: `workers/api-gateway/src/`, `render.yaml`, `vercel.json` (absent), `frontend/next.config.js`, `workers/api-gateway/wrangler.toml`, `backend/pyproject.toml`, `.env.example`, `backend/.env.example`, `frontend/.env.example`, `Dockerfile`, `backend/Dockerfile`, `frontend/Dockerfile`

---

## Summary

| Severity | Count |
|----------|-------|
| P0 (Critical) | 2 |
| P1 (High) | 6 |
| P2 (Medium) | 8 |
| P3 (Low / Informational) | 9 |
| **Total** | **25** |

---

## P0 — Critical

### P0-01: Rate-Limit Bypass Key Transmitted as a Plain HTTP Header — Full Bypass Achievable

**File**: `workers/api-gateway/src/middleware/rate-limiter.ts`, lines 23-26
**File**: `workers/api-gateway/wrangler.toml`, lines 43-45 (comment only, no enforcement)

**Description**

The `X-RateLimit-Bypass` header value is compared against `RATE_LIMIT_BYPASS_KEY` and, if they match, the rate limiter is skipped entirely for **all tiers** including `strict` (auth endpoints). The header arrives from the internet and traverses the full Cloudflare edge network before the Worker sees it. Any party that learns the key can send unlimited requests to auth endpoints (`/api/v1/auth/*`), the password reset flow, and every other route.

The key is stored as a Wrangler secret, which is good — but because the bypass is keyed only on a static shared secret, a single exfiltrated `RATE_LIMIT_BYPASS_KEY` value permanently removes rate limiting until the secret is manually rotated. There is no scope limitation: the bypass applies equally to `/api/v1/auth/login`, `/api/v1/auth/register`, `/api/v1/prices/refresh`, and every other route.

Additionally, the bypass check happens **before** bot detection is skipped (bot detection is already skipped for routes with `requireApiKey`), meaning a bot with the bypass key can also enumerate auth endpoints without restriction.

```typescript
// rate-limiter.ts lines 23-26 — current code
const bypassKey = request.headers.get("X-RateLimit-Bypass");
if (bypassKey && env.RATE_LIMIT_BYPASS_KEY && bypassKey === env.RATE_LIMIT_BYPASS_KEY) {
  return { allowed: true, remaining: Infinity, limit: Infinity, resetAt: 0 };
}
```

**Fix**

1. Restrict the bypass to a specific IP allowlist (GHA runner CIDR ranges) rather than a shared secret header. Cloudflare Workers can read `request.cf?.asn` or compare `clientIp` against known GHA CIDRs.
2. If a header-based bypass must be kept, scope it to internal-only routes (`route.requireApiKey === true`) and explicitly block it for `strict`-tier auth routes regardless of the key.
3. Rotate `RATE_LIMIT_BYPASS_KEY` immediately if it has been transmitted in any logs.

```typescript
// Proposed: scope bypass to internal routes only, and reject it on strict tier
if (tier === "strict") {
  // Never bypass strict rate limiting regardless of any header
} else if (tier === "internal" && bypassKey && env.RATE_LIMIT_BYPASS_KEY && bypassKey === env.RATE_LIMIT_BYPASS_KEY) {
  return { allowed: true, remaining: Infinity, limit: Infinity, resetAt: 0 };
}
```

---

### P0-02: Cache Poisoning via Unvalidated User-Controlled `varyOn` Query Parameters

**File**: `workers/api-gateway/src/router.ts`, lines 21-43
**File**: `workers/api-gateway/src/middleware/cache.ts`, lines 22, 83

**Description**

The `buildCacheKey` function appends raw user-supplied query parameter values directly into the KV key and the internal `cache.internal` URL with no sanitization or length limit. Specifically, the `region` and `utility_type` parameters are read verbatim from `URLSearchParams` and interpolated into the cache key string.

```typescript
// router.ts lines 32-36
for (const key of sorted) {
  const val = searchParams.get(key);        // val is fully attacker-controlled
  if (val !== null) {
    parts.push(`${key}=${val}`);            // written directly into the KV key
  }
}
return `rsgw:${pathname}|${parts.join("|")}`;
```

Consequences:

1. **KV key namespace exhaustion**: An attacker can submit thousands of unique `region=` values (e.g. `region=AAAA...` with 512-byte values), each creating a new KV entry. Cloudflare KV free/paid tiers have write-per-second and total-key limits; flooding these degrades cache performance globally and can cause unexpected billing spikes.
2. **Cache poisoning**: If an attacker can influence origin response content *and* manufacture a cache key that maps to a legitimate user's cached entry, they can serve poisoned data. The current key construction does not normalize values (e.g., `region=CA` vs `region=ca` vs `region=CA%20` are treated as different keys, but `region=CA` could be poisoned by a concurrent request with crafted headers).
3. **Internal URL injection**: The `cacheUrl = new URL("https://cache.internal/" + cacheKey)` construction at `cache.ts` line 27 passes the raw key into a URL. KV key length is bounded (Cloudflare: 512 bytes), but the Cache API URL has no such bound. An excessively long or path-traversal-style value (e.g., `region=../../secret`) could interact unexpectedly with the `caches.default` namespace.

**Fix**

Validate and normalize all `varyOn` parameter values before they enter the cache key:

```typescript
// router.ts — add validation to buildCacheKey
const ALLOWED_REGION_PATTERN = /^[A-Z]{2,3}$/;
const ALLOWED_UTILITY_PATTERN = /^[a-z_]{1,32}$/;
const PARAM_VALIDATORS: Record<string, RegExp> = {
  region: ALLOWED_REGION_PATTERN,
  utility_type: ALLOWED_UTILITY_PATTERN,
  days: /^\d{1,4}$/,
};

for (const key of sorted) {
  const val = searchParams.get(key);
  if (val === null) continue;
  const validator = PARAM_VALIDATORS[key];
  if (validator && !validator.test(val)) continue; // skip invalid values — treat as miss
  parts.push(`${key}=${val}`);
}
```

Also enforce a maximum total cache key length (e.g., 256 bytes) and return a cache miss if exceeded.

---

## P1 — High

### P1-01: Missing `Content-Security-Policy` on the Cloudflare Worker (API Layer)

**File**: `workers/api-gateway/src/middleware/security.ts`, lines 54-63

**Description**

The `getSecurityHeaders` function applied to every API response is missing a `Content-Security-Policy` header. While the frontend (`next.config.js`) sets a CSP for rendered pages, the CF Worker serves JSON API responses directly (e.g., `gateway-stats`, error bodies) with no CSP. An attacker who triggers a Worker response that reflects content (e.g., a gateway error body that echoes a request field) has no content-type or frame protection at the API layer.

More critically, the HSTS `max-age` on the Worker is 31536000 (1 year) but is **missing the `preload` directive**. The frontend sets `max-age=63072000; includeSubDomains; preload` (2 years with preload), creating an inconsistency where `api.rateshift.app` responses advertise a weaker HSTS posture than the frontend.

```typescript
// security.ts lines 57-58 — current
"Strict-Transport-Security": "max-age=31536000; includeSubDomains",
// missing: preload
// missing: Content-Security-Policy
// missing: Permissions-Policy
```

**Fix**

```typescript
export function getSecurityHeaders(requestId: string, colo: string): Record<string, string> {
  return {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-Request-ID": requestId,
    "X-Edge-Colo": colo,
  };
}
```

---

### P1-02: Webhook Route Bypasses All Rate Limiting, Bot Detection, and Auth — No Signature Enforcement at Edge

**File**: `workers/api-gateway/src/config.ts`, lines 4-9

**Description**

The webhook route pattern `/api/v1/webhooks/` is configured with `rateLimit: "bypass"` and `passthrough: true`. This means:

- Zero rate limiting (unlimited requests per second, per IP, globally)
- Bot detection is skipped (the `!route.requireApiKey` check in `index.ts` line 65 still runs for this route, but since `requireApiKey` is falsy, bot scoring runs — however, it does not block because the rate limit is "bypass" which is set to `allowed: true` even before bot score is checked)
- No caching (acceptable)
- Stripe webhook signature verification is the only protection, and that happens at the origin (Render backend), not at the edge

An attacker who can send 10,000 requests/second to `POST /api/v1/webhooks/stripe` will fully exhaust the Render backend's connection pool even though Stripe validation will reject them all. This is a viable DoS vector against the backend without any edge-layer mitigation.

**Fix**

Apply a `standard` or `strict` rate limit to the webhook path at the edge. Stripe retries on failure and will not be impacted by a 429 response (it retries with exponential backoff). If Stripe's IP ranges are known, add an IP allowlist check:

```typescript
// config.ts — revised webhook entry
{
  pattern: /^\/api\/v1\/webhooks\//,
  rateLimit: "strict",   // 30 req/min per IP is more than enough for Stripe
  passthrough: true,
},
```

---

### P1-03: `X-Forwarded-For` Blindly Trusted for Rate Limiting Key — Trivial IP Spoofing

**File**: `workers/api-gateway/src/index.ts`, lines 19-22
**File**: `workers/api-gateway/src/middleware/rate-limiter.ts`, line 38

**Description**

The `clientIp` variable used as the rate limiting key is derived as:

```typescript
const clientIp =
  request.headers.get("CF-Connecting-IP") ??
  request.headers.get("X-Forwarded-For")?.split(",")[0]?.trim() ??
  "unknown";
```

When `CF-Connecting-IP` is present (all genuine Cloudflare requests), this is correct — Cloudflare sets this header authoritatively and strips any attacker-supplied version. However, the `X-Forwarded-For` fallback is reached if:

1. The Worker is invoked outside Cloudflare (e.g., `wrangler dev --local`, direct Render origin calls, or a misconfigured zone that bypasses the Worker route).
2. The `CF-Connecting-IP` header is absent for any reason.

In those fallback scenarios, the `X-Forwarded-For` header is attacker-controlled, allowing any requester to set `X-Forwarded-For: 1.2.3.4` and bypass per-IP rate limits by rotating the spoofed IP. This also affects the `X-Forwarded-For` and `X-Real-IP` headers forwarded to the origin in `proxy.ts` lines 18-19, which Render's backend may use for audit logging and IP-based access controls.

**Fix**

Remove the `X-Forwarded-For` fallback. In a Cloudflare Workers deployment, `CF-Connecting-IP` is always present. If it is absent, treat the request as coming from `unknown` and rate limit under the `unknown` key (or block it):

```typescript
// index.ts — safe version
const clientIp = request.headers.get("CF-Connecting-IP") ?? "unknown";
```

Additionally, in `proxy.ts`, strip any attacker-supplied `X-Forwarded-For` before constructing the headers object, then set it authoritatively:

```typescript
// proxy.ts — before building headers
headers.delete("x-forwarded-for");  // strip attacker value (case-insensitive in Headers)
headers.set("X-Forwarded-For", clientIp);
```

---

### P1-04: Sensitive Internal Error Detail in 503 Auth-Not-Configured Response

**File**: `workers/api-gateway/src/middleware/internal-auth.ts`, lines 17-24

**Description**

When `INTERNAL_API_KEY` is not configured in the Worker environment (e.g., during a partial deployment or misconfiguration), the error response body is:

```json
{ "error": "Internal auth not configured" }
```

This message reveals that the Worker has an internal authentication mechanism that is not configured — information useful to an attacker probing the API structure. It distinguishes "auth misconfigured" from "auth correct but key wrong", providing a foothold for targeted infrastructure reconnaissance.

**Fix**

Return a generic 503 that does not distinguish between misconfiguration and other error states:

```typescript
// internal-auth.ts — line 19, change message
JSON.stringify({ error: "Service temporarily unavailable" })
```

---

### P1-05: `render.yaml` Uses Render Free Plan — No DDoS Protection, No Autoscaling, Single Instance

**File**: `render.yaml`, lines 5-6

**Description**

Both the web service and cron job are configured with `plan: free`. The free Render plan:

- Has no autoscaling; a single container handles all traffic that bypasses the CF Worker
- Spins down after 15 minutes of inactivity (cold starts in production)
- Has no Render-native DDoS protection
- Shares compute resources with other free-tier tenants

Combined with P1-02 (webhook bypass), an attacker who floods the origin directly (by discovering `electricity-optimizer.onrender.com` from the hardcoded `ORIGIN_URL` in `wrangler.toml` line 40) can take down the backend with minimal effort. The origin URL is hardcoded in a committed file, making it publicly discoverable.

**File**: `workers/api-gateway/wrangler.toml`, line 40

```toml
ORIGIN_URL = "https://electricity-optimizer.onrender.com"  # publicly visible
```

**Fix**

1. Upgrade to a paid Render plan for production workloads.
2. Move `ORIGIN_URL` out of `[vars]` (which is committed and public) and into a Wrangler secret (`wrangler secret put ORIGIN_URL`).
3. Add a shared secret header that the backend validates — requests not originating from the CF Worker should be rejected by the origin (e.g., `X-Gateway-Token: <secret>` verified at the FastAPI middleware layer).

---

### P1-06: `bandit` Security Scan Is Non-Blocking — High-Severity Python Findings Only Emit Warnings

**File**: `.github/workflows/ci.yml`, lines 301-307

**Description**

The Bandit static analysis step uses `|| { echo "::warning::..." }` rather than `exit 1`, meaning high-severity Python vulnerabilities found by Bandit do not fail the CI pipeline. A developer can merge code containing SQL injection, command injection, hardcoded credentials, or path traversal vulnerabilities without any CI gate blocking the merge.

```yaml
# ci.yml lines 303-306 — current (non-blocking)
bandit -r . -f json -o ../bandit-report.json -ll --severity-level high || {
  echo "::warning::Bandit found high-severity issues"
}
```

Contrast this with `npm audit` at line 317-320, which correctly uses `exit 1`. The asymmetry means the Python backend has a weaker gate than the Node.js frontend.

**Fix**

```yaml
# ci.yml — make Bandit a hard gate
- name: Run Bandit (high-severity)
  run: |
    pip install bandit
    cd backend
    bandit -r . -f json -o ../bandit-report.json -ll --severity-level high
    # Exit code 1 means issues found; this will now fail the step
```

Remove the `|| { echo "::warning::" }` escape hatch. Triage existing Bandit findings first to ensure no false positives will block the pipeline unintentionally; add `.bandit` baseline or `# nosec` comments only for confirmed false positives.

---

## P2 — Medium

### P2-01: `Vary` Header Not Set on Cached Responses — Proxy Cache Poisoning Risk

**File**: `workers/api-gateway/src/middleware/cache.ts`, lines 108-119

**Description**

When storing a response in the CF Cache API, the headers do not include a `Vary` header. The cache key is built correctly from query parameters, but the served response headers do not signal to any intermediate proxy (e.g., a corporate HTTP proxy, a CDN layer in front of Cloudflare) which request attributes were used to select the cached variant. This can cause intermediate proxies to serve a cached response for `region=CA` to a user who requested `region=NY`.

Additionally, the entire origin response headers object is stored in KV verbatim (`headers: Object.fromEntries(response.headers.entries())`), including any `Set-Cookie` headers from the origin. Caching `Set-Cookie` headers causes session cookie replay: user A's session cookie is served to user B from the cache.

```typescript
// cache.ts lines 86-92 — storing all origin headers including Set-Cookie
const entry: CacheEntry = {
  body,
  headers: Object.fromEntries(response.headers.entries()), // includes Set-Cookie!
  ...
};
```

**Fix**

Strip security-sensitive headers before caching and add a `Vary` header:

```typescript
const HEADERS_TO_STRIP_FROM_CACHE = new Set([
  "set-cookie", "authorization", "x-auth-token", "x-api-key",
  "cf-connecting-ip", "cf-ray", "cf-cache-status",
]);

const safeHeaders: Record<string, string> = {};
for (const [k, v] of response.headers.entries()) {
  if (!HEADERS_TO_STRIP_FROM_CACHE.has(k.toLowerCase())) {
    safeHeaders[k] = v;
  }
}
safeHeaders["Vary"] = "Accept-Encoding";

const entry: CacheEntry = { body, headers: safeHeaders, ... };
```

---

### P2-02: `Content-Type` Not Enforced on Cached Responses Served from KV

**File**: `workers/api-gateway/src/middleware/cache.ts`, lines 170-177

**Description**

`buildCachedResponse` reconstructs a `Response` from the stored `entry.headers` object. If the origin omits or incorrectly sets `Content-Type`, the cached response is served with whatever header was stored. Since `X-Content-Type-Options: nosniff` is applied by the Worker, this does not enable MIME sniffing — but it does mean a cache entry created from a buggy origin response (e.g., `Content-Type: text/html` on a JSON endpoint) will serve all subsequent requests with an incorrect type until the TTL expires.

**Fix**

After reconstructing headers from cache, assert that API route responses have `Content-Type: application/json`:

```typescript
function buildCachedResponse(entry: CacheEntry, cacheStatus: "HIT" | "STALE"): Response {
  const headers = new Headers(entry.headers);
  headers.set("X-Cache", cacheStatus);
  // Ensure JSON content-type is not lost or corrupted from cache
  if (!headers.get("content-type")?.includes("application/json")) {
    headers.set("Content-Type", "application/json; charset=utf-8");
  }
  return new Response(entry.body, { status: entry.status, headers });
}
```

---

### P2-03: Bot Detection Is Trivially Bypassed — No Real Signal Used

**File**: `workers/api-gateway/src/middleware/security.ts`, lines 5-42

**Description**

The `calculateBotScore` function grants a +20 bonus to any request that includes `Mozilla/5.0` and one of `Chrome|Firefox|Safari|Edge` in the `User-Agent`. This is a purely syntactic check that any script can satisfy:

```python
# attacker bypasses bot detection with one header
headers = {"User-Agent": "Mozilla/5.0 (compatible) Chrome/120 Safari/537"}
```

The function also applies positive scoring for `Accept-Language` and `Accept-Encoding` — headers that are trivially added. A score of `50 (baseline) + 20 (Mozilla/5.0+browser) + 10 (Accept: application/json) + 5 (Accept-Language) + 5 (Accept-Encoding) = 90` means any automated scanner that sends four common headers passes through unblocked.

In practice this check provides no meaningful bot protection and creates false confidence that scrapers are being filtered.

**Fix**

Either remove the bot-scoring function (accept that it adds no real value and rely solely on Cloudflare's native Bot Management) or gate it behind the paid Cloudflare Bot Management product which uses behavioral fingerprinting. If the heuristic check is kept, do not use it as a blocking signal — use it only as a supplementary logging/scoring signal:

```typescript
// Change shouldBlockBot to never block based purely on heuristic score
// Rely on CF Bot Management binding (paid feature) for actual blocking
export function shouldBlockBot(_score: number): boolean {
  return false; // heuristic only — log score, do not block
}
```

---

### P2-04: `wrangler.toml` Hardcodes KV Namespace ID in a Committed File

**File**: `workers/api-gateway/wrangler.toml`, line 12

**Description**

```toml
kv_namespaces = [
  { binding = "CACHE", id = "6946d19ce8264f6fae4481d6ad8afcd1" }
]
```

The KV namespace ID `6946d19ce8264f6fae4481d6ad8afcd1` is committed to version control. While a namespace ID alone does not grant access to KV data (the Cloudflare API token is required), it:

1. Reveals infrastructure identifiers that assist in targeted API enumeration if a Cloudflare token is ever compromised.
2. Couples the production namespace to the committed configuration — making it impossible to use a different namespace for staging without modifying the committed file.

**Fix**

Use Wrangler environment overrides to separate production and staging namespace IDs:

```toml
# wrangler.toml — use environment-specific IDs
[env.production]
kv_namespaces = [
  { binding = "CACHE", id = "6946d19ce8264f6fae4481d6ad8afcd1" }
]

[env.staging]
kv_namespaces = [
  { binding = "CACHE", id = "STAGING_KV_ID_HERE" }
]
```

---

### P2-05: `next.config.js` CSP Allows `unsafe-inline` Scripts Unconditionally in Production

**File**: `frontend/next.config.js`, lines 43-44

**Description**

```javascript
`script-src 'self' 'unsafe-inline' https://*.clarity.ms https://cdn.onesignal.com${isDev ? " 'unsafe-eval'" : ''}`,
```

`'unsafe-inline'` is present in `script-src` in production, which defeats Content Security Policy's primary purpose of preventing XSS. Any injected inline script (via a DOM XSS, a third-party script compromise, or a template injection) executes without restriction. The CSP effectively protects against only remote-script-injection from unlisted domains, not inline execution.

The `isDev` guard correctly removes `'unsafe-eval'` for production, but `'unsafe-inline'` is unconditional.

**Fix**

Migrate to a nonce-based or hash-based CSP for inline scripts. Next.js 13+ supports nonce generation via middleware:

```javascript
// next.config.js — replace 'unsafe-inline' with nonce placeholder
// In middleware.ts, generate per-request nonce and set the CSP header there
`script-src 'self' 'nonce-${nonce}' https://*.clarity.ms https://cdn.onesignal.com`,
```

As an interim step (if nonce migration is complex), document the risk and track it as a known security debt item.

---

### P2-06: `next.config.js` Image `remotePatterns` Uses a Wildcard Subdomain

**File**: `frontend/next.config.js`, lines 20-24

**Description**

```javascript
remotePatterns: [
  {
    protocol: 'https',
    hostname: '*.rateshift.app',
  },
],
```

The wildcard `*.rateshift.app` allows Next.js Image Optimization to proxy and serve images from **any** subdomain of `rateshift.app`, including attacker-controlled subdomains if a subdomain takeover were to occur (e.g., an unclaimed CNAME on a decommissioned Vercel/Render deployment). This is a Supply Chain / SSRF-adjacent risk.

**Fix**

Restrict to only the subdomains that are expected to serve images:

```javascript
remotePatterns: [
  { protocol: 'https', hostname: 'rateshift.app' },
  { protocol: 'https', hostname: 'www.rateshift.app' },
  { protocol: 'https', hostname: 'api.rateshift.app' },
],
```

---

### P2-07: `pyproject.toml` Has `[tool.bandit]` Configured but Bandit Is Not in Project Dependencies

**File**: `backend/pyproject.toml`, lines 118-120

**Description**

```toml
[tool.bandit]
exclude_dirs = ["tests", "alembic"]
skips = ["B101"]  # assert_used
```

Bandit configuration is present in `pyproject.toml` but `bandit` is not listed in `requirements.txt` or any dependency group. CI installs it via `pip install bandit` as a one-off command (`.github/workflows/ci.yml` line 303), meaning:

1. Local developers running `bandit` will get whatever version pip resolves at install time, potentially different from CI.
2. There is no pinned version, so a breaking Bandit release could silently change false-positive behavior.
3. `B101` (assert_used) is globally skipped via `pyproject.toml`, but `tests/*` already has `S101` skipped in ruff. The global skip means production code can use `assert` for security checks and Bandit will not flag it.

**Fix**

Add `bandit[toml]` to a development/security requirements file with a pinned version:

```
# requirements-security.txt
bandit[toml]==1.8.0
pip-audit==2.7.3
```

Review and remove the global `B101` skip — it should apply only to `tests/`, not to production code.

---

### P2-08: `OTEL_EXPORTER_OTLP_HEADERS` Contains Authorization Credentials — Logged in Plain Text if Debug Mode Enabled

**File**: `render.yaml`, line 80; `backend/.env.example`, lines 125-127

**Description**

`OTEL_EXPORTER_OTLP_HEADERS` is documented as containing `Authorization: Basic <base64(instanceId:token)>`. If `OTEL_ENABLED=true` and any logging framework logs outgoing HTTP request headers (e.g., `httpx` debug mode, OpenTelemetry SDK verbose logging), the Grafana Cloud authorization token will appear in application logs, which Sentry and other log aggregators may capture.

The environment variable holds the complete auth credential as a comma-separated header string, meaning it is effectively a long-lived secret stored in an environment variable rather than a dedicated secrets manager.

**Fix**

1. Confirm that the OpenTelemetry SDK does not log outgoing OTLP headers in the production log level configuration.
2. Store the Grafana Cloud OTLP token in 1Password and reference it via `op://` URI in Render's environment variables rather than pasting the base64-encoded value directly.
3. Rotate the Grafana Cloud OTLP token periodically (add to 90-day rotation schedule).

---

## P3 — Low / Informational

### P3-01: No `Retry-After` Header on Rate Limit Bypass Response (Webhook Route Returns 200 with No Indication)

**File**: `workers/api-gateway/src/middleware/rate-limiter.ts`, lines 18-19

The `bypass` tier returns `remaining: Infinity` and `limit: Infinity`. The `rateLimitHeaders` function checks `if (result.limit === Infinity) return {}` and emits no rate limit headers at all. This is correct for the bypass case, but means the response for webhooks and health checks contains no standard `X-RateLimit-*` headers, making it harder for callers to discover rate limit configuration through introspection.

**No immediate fix required**, but document that the bypass tier intentionally omits rate limit headers.

---

### P3-02: CORS Preflight Does Not Include `Vary: Origin` Header

**File**: `workers/api-gateway/src/middleware/cors.ts`, lines 25-35

The CORS preflight response sets `Access-Control-Allow-Origin: <specific-origin>` dynamically but does not set `Vary: Origin`. Intermediate HTTP caches that are not aware of the Worker may serve a cached preflight response to a request from a different origin, incorrectly allowing or denying it.

**Fix**

```typescript
// cors.ts — add Vary: Origin to preflight
return new Response(null, {
  status: 204,
  headers: {
    "Vary": "Origin",
    "Access-Control-Allow-Origin": origin,
    // ... rest of headers
  },
});
```

---

### P3-03: `Access-Control-Allow-Methods` Includes `DELETE` and `PUT` — Verify All Routes Need Them

**File**: `workers/api-gateway/src/middleware/cors.ts`, line 29

```typescript
"Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
```

`DELETE` and `PUT` are permitted for CORS from all listed origins. If any cached routes (which are all `GET`-only) mistakenly allow `DELETE` via CORS, a CSRF-like attack from an allowed origin could delete data. Verify that the backend enforces HTTP method restrictions at the route level and that no `DELETE` requests can be satisfied by a cached response.

**No code change required if backend method enforcement is confirmed.**

---

### P3-04: `wrangler.toml` Declares `compatibility_date = "2024-12-01"` — 15+ Months Out of Date

**File**: `workers/api-gateway/wrangler.toml`, line 3

The compatibility date controls which Cloudflare breaking-change flags are active. Setting it to `2024-12-01` when the current date is 2026-03-16 means the Worker does not benefit from security and behavior improvements introduced in 2025-2026 compatibility flags (e.g., improved `Headers` iteration behavior, stricter URL parsing). It also means a future update to a current compatibility date could introduce unexpected behavior changes.

**Fix**

Update to a recent date (e.g., `2025-12-01`) and run the Worker test suite. Review the [Cloudflare compatibility flags changelog](https://developers.cloudflare.com/workers/configuration/compatibility-dates/) for any security-relevant changes between 2024-12 and the updated date.

---

### P3-05: `render.yaml` Missing Readiness Probe — Health Check Only After Service Start

**File**: `render.yaml`, line 8

```yaml
healthCheckPath: /health
```

Render uses `healthCheckPath` for liveness (restart on failure), but there is no documented readiness configuration. On a cold start (the free plan spins down after inactivity), Render may route traffic to the container before it has established database connections. A failed database connection at startup could produce 500 errors for the first few requests.

**Fix**

Implement a readiness endpoint (separate from `/health`) that verifies database connectivity before returning 200. This is an operational concern that also has security implications (failed auth DB connection could bypass auth checks if error handling falls through to allow-all).

---

### P3-06: Root `Dockerfile` (Used by `render.yaml` Cron Job) Does Not Have a `production` Build Target

**File**: `Dockerfile` (root), lines 1-54
**File**: `render.yaml`, line 8

The root `Dockerfile` (used by the `db-maintenance` cron job in `render.yaml`) has only two stages: `builder` and the runtime stage (no named `production` target). The `backend/Dockerfile` correctly defines `FROM python:3.12-slim as production`, but the root `Dockerfile` CMD runs as `appuser` (correct) but does not pin `uvicorn` workers or tune shutdown timeout for the cron context.

More critically, the root Dockerfile runs `curl` in the healthcheck against `http://localhost:${PORT:-8000}` but the Render cron job runs `python scripts/db_maintenance.py` — not a web server — so the health check will always fail and produce noisy Render health-check logs.

**Fix**

The cron job Dockerfile should omit the `HEALTHCHECK` directive since it is a one-shot script, not a long-running web server.

---

### P3-07: `.env.example` Root File Contains Misleading `DATA_RESIDENCY=EU` While Production Uses `US`

**File**: `.env.example`, line 71
**File**: `render.yaml`, line 41

Root `.env.example` sets `DATA_RESIDENCY=EU` as default, while `render.yaml` explicitly sets `DATA_RESIDENCY=US` for production. `backend/.env.example` sets `DATA_RESIDENCY=US`. A developer who copies the root `.env.example` without checking the backend-specific file will configure a local development environment with an incorrect data residency setting, potentially testing GDPR-path logic when US logic is intended and vice versa.

**Fix**

Align the root `.env.example` to `DATA_RESIDENCY=US` or remove the data-residency section from it and direct developers to `backend/.env.example`.

---

### P3-08: OWASP ZAP Scan Suppresses Rule 10021 (`X-Content-Type-Options`) With "Handled by CF Worker" Justification — Verify This Claim

**File**: `.zap/rules.tsv`, line 4

```
10021	IGNORE	(X-Content-Type-Options - handled by CF Worker)
```

The suppression assumes the ZAP scan target (`https://api.rateshift.app`) always routes through the CF Worker. If ZAP scans the origin Render URL directly (e.g., via `secrets.RENDER_BACKEND_URL`), this rule suppression hides a genuine finding: the origin Render backend may not set `X-Content-Type-Options` itself. Confirm that either (a) ZAP always scans through the CF Worker, or (b) the Render backend independently sets this header in its FastAPI middleware.

**Fix**

Add `X-Content-Type-Options: nosniff` to the FastAPI response middleware so it is present at the origin layer, then remove the ZAP suppression.

---

### P3-09: `secret-scan.yml` Uses `gitleaks/gitleaks-action@v2` Without Pinning to a Specific SHA

**File**: `.github/workflows/secret-scan.yml`, line 28

```yaml
uses: gitleaks/gitleaks-action@v2
```

Using a mutable tag (`@v2`) means a compromised or updated `gitleaks-action` release could alter scan behavior without any repository change. This is a supply-chain risk for the security scanning step itself.

**Fix**

Pin to a specific commit SHA:

```yaml
uses: gitleaks/gitleaks-action@v2.3.4  # or pin to SHA: uses: gitleaks/gitleaks-action@abc123...
```

Apply the same pinning review to all third-party GHA actions across all 31 workflows.

---

## Cross-Cutting Observations

### Positive Security Controls Confirmed

The following controls were reviewed and found to be correctly implemented:

- **Timing-safe comparison**: `internal-auth.ts` uses `crypto.subtle.timingSafeEqual` with a correct constant-time fallback. The length-difference timing leak is handled by always processing `max(len_a, len_b)` iterations.
- **Fail-closed internal auth**: When `INTERNAL_API_KEY` is not configured, all internal endpoint requests are rejected with 503 rather than allowed through.
- **Rate limiting per-IP using native CF bindings**: Zero KV cost, correct tier separation (standard/strict/internal).
- **Cache only on GET**: `tryCache` correctly returns MISS for non-GET methods, preventing cache poisoning via POST bodies.
- **CORS origin allowlist**: Both preflight and actual response paths validate the `Origin` header against an explicit allowlist; wildcard `*` is never used.
- **Non-root Docker users**: Both `backend/Dockerfile` and `frontend/Dockerfile` production stages correctly run as non-root (`appuser`/`nextjs`).
- **Secrets in Wrangler secrets store**: `INTERNAL_API_KEY` and `RATE_LIMIT_BYPASS_KEY` are documented as wrangler secrets, not `[vars]`.
- **Gitleaks secret scanning**: Runs on every PR and push to main plus weekly schedule.
- **pip-audit blocking gate**: `_backend-tests.yml` runs `pip-audit --strict` and fails the pipeline on known vulnerabilities.
- **HSTS on frontend**: `next.config.js` sets `max-age=63072000; includeSubDomains; preload` — 2-year HSTS with preload.

---

## Prioritized Remediation Order

| Priority | Finding | Effort |
|----------|---------|--------|
| 1 | P0-01: Rate limit bypass on all tiers including auth | Low (add tier restriction) |
| 2 | P0-02: Cache poisoning via unvalidated query params | Low (add regex validation) |
| 3 | P1-03: XFF spoofing as rate limit bypass | Trivial (remove fallback) |
| 4 | P1-02: Webhook route fully unrated | Trivial (change to strict) |
| 5 | P1-06: Bandit non-blocking in CI | Trivial (remove escape hatch) |
| 6 | P1-01: Missing CSP + preload HSTS on Worker | Low |
| 7 | P2-01: Set-Cookie cached in KV entries | Low (header stripping) |
| 8 | P1-05: Origin URL exposed in committed file | Medium (move to secret) |
| 9 | P1-04: Auth-misconfigured error leaks info | Trivial |
| 10 | P2-05: `unsafe-inline` in production CSP | High effort (nonce migration) |
