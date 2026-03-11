# RateShift API Gateway

Cloudflare Worker serving as the edge API gateway for RateShift at `api.rateshift.app`.

## Overview

The RateShift API Gateway provides a secure, performant edge layer between client applications and the Render backend. Deployed globally via Cloudflare's edge network, it handles caching, rate limiting, bot detection, authentication, and security policy enforcement.

**Deployed at**: https://api.rateshift.app

## Architecture

### Request Flow

```
Client Request
  ↓
Cloudflare Workers (API Gateway)
  ├─ CORS Preflight
  ├─ Route Matching
  ├─ Bot Detection (heuristic scoring)
  ├─ Internal Auth (X-API-Key)
  ├─ Rate Limiting (KV-based per IP/tier)
  ├─ Cache Lookup (Cache API)
  ├─ Security Headers
  └─ Proxy to Origin
      ↓
Render Backend (electricity-optimizer.onrender.com)
```

## Features

### 1. Dual-Layer Caching

**Cache API** (Cloudflare's standard cache):
- HTTP cache headers honored (Cache-Control, ETag)
- Edge location-aware (faster than origin)
- TTL up to 1 year

**KV Namespace** (Worker-controlled cache):
- Custom TTL per route
- Granular cache invalidation
- Ideal for price updates and dynamic data

Used for:
- `/api/v1/prices/current` — 5 min TTL
- `/api/v1/suppliers/registry` — 24 hour TTL
- `/api/v1/regions` — 24 hour TTL

### 2. Rate Limiting

**Fixed-window KV-based limiter** with 3 configurable tiers:

| Tier | Limit (per 60s) | Use Case |
|------|---|---|
| `standard` | 120 requests | Public API endpoints |
| `strict` | 30 requests | Authentication endpoints |
| `internal` | 600 requests | GHA cron jobs + server-to-server |

Each IP gets its own counter per tier per time window. Bypass via:
- Constant-time header comparison: `X-RateLimit-Bypass: <RATE_LIMIT_BYPASS_KEY>`
- Internal API key: `X-API-Key: <INTERNAL_API_KEY>`

### 3. Bot Detection

Heuristic scoring based on:
- Missing User-Agent header
- Suspicious patterns (automated tools)
- Request entropy analysis

Score threshold: 75/100 blocks request with 403.

### 4. Internal Authentication

Routes matching `/api/v1/internal/*`:
- Require `X-API-Key: <INTERNAL_API_KEY>` header
- Constant-time comparison (prevents timing attacks)
- Used by GHA cron workflows and internal batch jobs

### 5. CORS

Whitelist of allowed origins:
- `https://rateshift.app`
- `https://www.rateshift.app`

Preflight requests (OPTIONS) handled fast-path without proxying.

### 6. Security Headers

Applied to all responses:
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
```

## KV Namespaces

| Binding | ID | Purpose |
|---------|----|----|
| `CACHE` | `6946d19ce8264f6fae4481d6ad8afcd1` | Cache API storage for routes with custom TTL |
| `RATE_LIMIT` | `c9be3741ee784956a0d99b3fa0c1d6c4` | Fixed-window rate limit counters |

## Configuration

### wrangler.toml

```toml
name = "rateshift-api-gateway"
main = "src/index.ts"
compatibility_date = "2024-12-01"

routes = [
  { pattern = "api.rateshift.app/*", zone_name = "rateshift.app" }
]

kv_namespaces = [
  { binding = "CACHE", id = "6946d19ce8264f6fae4481d6ad8afcd1" },
  { binding = "RATE_LIMIT", id = "c9be3741ee784956a0d99b3fa0c1d6c4" }
]

[vars]
ORIGIN_URL = "https://electricity-optimizer.onrender.com"
ALLOWED_ORIGINS = "https://rateshift.app,https://www.rateshift.app"
RATE_LIMIT_STANDARD = "120"
RATE_LIMIT_STRICT = "30"
RATE_LIMIT_INTERNAL = "600"
RATE_LIMIT_WINDOW_SECONDS = "60"
```

### Environment Variables

**Non-secret** (in wrangler.toml):
- `ORIGIN_URL` — Render backend URL
- `ALLOWED_ORIGINS` — CORS whitelist (comma-separated)
- `RATE_LIMIT_*` — Per-tier request limits
- `RATE_LIMIT_WINDOW_SECONDS` — Fixed-window duration (60s)

**Secrets** (via `wrangler secret put`):
- `INTERNAL_API_KEY` — API key for `/internal/*` endpoints
- `RATE_LIMIT_BYPASS_KEY` — Bypass rate limiting (GHA workflows)

## Directory Structure

```
workers/api-gateway/
├── src/
│   ├── index.ts                 # Main fetch handler + request flow
│   ├── types.ts                 # TypeScript interfaces (Env, LogEntry, etc.)
│   ├── config.ts                # Route table definitions
│   ├── router.ts                # Path matching and cache key generation
│   ├── middleware/
│   │   ├── cors.ts              # CORS preflight + header injection
│   │   ├── rate-limiter.ts      # Fixed-window KV-based limiter
│   │   ├── cache.ts             # Cache API + KV lookups/storage
│   │   ├── security.ts          # Bot detection + security headers
│   │   ├── internal-auth.ts     # X-API-Key validation
│   │   └── observability.ts     # Structured logging
│   └── handlers/
│       └── proxy.ts             # Origin request + response handling
├── tests/
│   ├── rate-limiter.test.ts
│   ├── cache.test.ts
│   ├── cors.test.ts
│   └── ...                      # 37 vitest tests total
├── wrangler.toml
├── package.json
└── tsconfig.json
```

## Development

### Install Dependencies

```bash
npm install
```

### Local Testing

```bash
npm run dev
```

Server runs on `http://localhost:8787` with live reload.

### Type Checking

```bash
npm run typecheck
```

### Run Tests

```bash
npm test                 # Run all 37 tests
npm test:watch          # Watch mode
```

## Deployment

### Manual Deployment

```bash
wrangler deploy
```

### Automated via GitHub Actions

Workflow: `.github/workflows/deploy-worker.yml`

Triggers:
- Commits to `workers/api-gateway/**` on `main`
- Manual workflow dispatch

Steps:
1. Validate TypeScript (`npm run typecheck`)
2. Run tests (`npm test`)
3. Deploy via `wrangler deploy`
4. Run smoke tests against live Worker
5. Notify Slack on failure

### Smoke Tests

POST requests to key endpoints verify:
- Proxy routing (`/api/v1/prices/current` — 422 = working)
- CORS headers present
- Rate limit headers returned
- Bot detection disabled for test client

## Monitoring

### Observability

Each request logs structured JSON:
```json
{
  "requestId": "uuid",
  "timestamp": "ISO-8601",
  "method": "GET",
  "path": "/api/v1/prices/current",
  "status": 200,
  "cacheStatus": "HIT|MISS|BYPASS",
  "rateLimited": false,
  "botScore": 15,
  "duration": 125,
  "clientIp": "203.0.113.42",
  "colo": "lax"
}
```

Logs sent to Cloudflare's Tail service (real-time view via `wrangler tail`).

### Rate Limit Headers

All responses include:

```
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1678886400
```

## Routes & Cache Configuration

| Path | Method | Tier | Cache TTL | Bot Bypass |
|------|--------|------|-----------|-----------|
| `/api/v1/prices/*` | GET | standard | 5 min | Yes |
| `/api/v1/suppliers/registry` | GET | standard | 24 hr | Yes |
| `/api/v1/regions` | GET | standard | 24 hr | Yes |
| `/api/v1/auth/login` | POST | strict | none | No |
| `/api/v1/auth/signup` | POST | strict | none | No |
| `/api/v1/internal/*` | * | internal | none | N/A (API key required) |
| `*` (default) | * | standard | none | Yes |

## Limits

### Cloudflare Free Tier

- **100K requests/day** included with free plan
- **1GB KV storage** (shared across namespaces)
- **No additional costs** below limits

Current usage: ~5-10K requests/day (well within limits).

### Worker Limits

- **Execution timeout**: 30 seconds
- **Response size**: 128 MB
- **KV write**: 1 MB per request
- **Subrequests**: Unlimited (to origin)

## Troubleshooting

### 503 Bad Gateway

Likely origin is down. Check:
```bash
curl -I https://electricity-optimizer.onrender.com/health
```

### 429 Too Many Requests

Rate limit exceeded. Check headers:
```bash
curl -I -X GET https://api.rateshift.app/api/v1/prices/current
# Look for X-RateLimit-* headers
```

### Cache Not Invalidating

KV entries don't auto-invalidate. Force clear:
```bash
wrangler kv:key delete --namespace-id <ID> rl:*
```

## Rollout & Monitoring

### Deploy Checklist

- [ ] Commit changes to `workers/api-gateway/src/`
- [ ] GHA `deploy-worker.yml` triggers automatically
- [ ] Monitor Slack #deployments channel
- [ ] Check Cloudflare Analytics for 5xx errors
- [ ] Test endpoint: `curl -I https://api.rateshift.app/api/v1/prices/current`

### Rollback

If critical bug detected:

1. Revert commit on `main`
2. GHA redeploys automatically
3. Or manual: `wrangler deploy` with previous code

## Security Considerations

- **No secrets in code**: All sensitive values in `wrangler.toml` secrets
- **Constant-time auth**: `crypto.subtle` used for key comparison
- **Bot scoring**: Heuristic-based (not ML) to avoid false positives
- **CORS whitelist**: Strict origin validation
- **Logging**: No sensitive headers logged (auth redacted)

## Resources

- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)
- [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/)
- [KV Storage](https://developers.cloudflare.com/workers/runtime-apis/kv/)
- [Cache API](https://developers.cloudflare.com/workers/runtime-apis/cache/)
