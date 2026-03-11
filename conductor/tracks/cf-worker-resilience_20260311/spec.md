# Specification: CF Worker API Gateway Resilience & Rate Limit Overhaul

**Track ID:** cf-worker-resilience_20260311
**Type:** Feature
**Created:** 2026-03-11
**Status:** Draft

## Summary

Overhaul the Cloudflare Worker API gateway (`rateshift-api-gateway`) to eliminate KV write exhaustion on the free tier, reorder middleware for optimal KV efficiency, replace KV-based rate limiting with a zero-KV alternative, add graceful degradation when platform limits are hit, and optionally upgrade to the Workers Paid plan ($5/month) for 1000x headroom. The goal is to ensure that hitting any Cloudflare limit never "breaks" the project — the gateway should degrade gracefully, not fail catastrophically.

## Context

RateShift's API gateway is a Cloudflare Worker (`workers/api-gateway/`) deployed at `api.rateshift.app`. It handles all backend traffic with:
- 2-tier caching (CF Cache API per-colo + KV global)
- KV-based fixed-window rate limiting (120/30/600 per minute by tier)
- Bot detection, CORS, security headers, internal auth
- Proxy to Render origin (`electricity-optimizer.onrender.com`)

The worker is deployed on the **Cloudflare Workers Free Plan** with these hard daily limits:
- **100,000 requests/day** (resets 00:00 UTC)
- **100,000 KV reads/day**
- **1,000 KV writes/day** (THE BINDING CONSTRAINT)
- **1,000 KV deletes/day**
- **10ms CPU time per invocation**

## Problem Description

### Root Cause: KV Write Exhaustion

Every non-bypassed request to the gateway performs **at minimum 1 KV write** (rate limiter increment via `RATE_LIMIT.put()`). Cache misses add a second KV write (`CACHE.put()`). With a daily budget of only 1,000 writes shared across BOTH namespaces, the free tier exhausts after approximately **500-1,000 requests per day**.

At the configured rate limit of 120 req/min (standard tier), the daily write budget is consumed in approximately **8 minutes** of sustained traffic.

### KV Operations Per Request Path

| Request Path | Rate Limit | Cache | KV Reads | KV Writes | Total KV Ops |
|---|---|---|---|---|---|
| Cache API hit (best case) | 1 read + 1 write | 0 (Cache API only) | 1 | 1 | 2 |
| KV cache hit | 1 read + 1 write | 1 read | 2 | 1 | 3 |
| Full cache miss | 1 read + 1 write | 1 read + 1 write | 2 | 2 | 4 |
| Bypass tier (webhooks, health) | 0 | varies | 0-1 | 0-1 | 0-2 |

### Middleware Ordering Problem

In `index.ts`, the middleware pipeline runs:
1. CORS preflight
2. Route matching
3. Bot detection
4. Internal auth
5. **Rate limiting** (KV read + write) <-- runs BEFORE cache
6. **Cache check** (KV read on miss)
7. Proxy to origin
8. Cache store (KV write on miss)

Rate limiting runs before cache lookup, meaning **every request burns a KV write even for responses that would be served from cache**. Reordering to check cache first would eliminate KV writes for all cache hits.

### Silent Failure Mode

The rate limiter write on line 47 of `rate-limiter.ts` uses `await` but has **no try/catch**:
```typescript
await env.RATE_LIMIT.put(key, String(current + 1), { expirationTtl: ttl });
```

When the daily KV write limit is exceeded, this throws a 429 error from KV. Since it's inside the main `try/catch` in `index.ts`, the entire request returns a 502 "Gateway error" — **not a rate limit error, not a graceful degradation, but a total gateway failure**.

### Cascading Failures

Once KV writes are exhausted:
1. Rate limiter writes fail → 502 for all non-bypass requests
2. Cache store writes fail → even cache refreshes stop working
3. Price cache invalidation (using `CACHE.list()` + `CACHE.delete()`) also fails
4. The gateway becomes effectively non-functional until 00:00 UTC daily reset

### What Happens When 100K Request Limit Is Hit

Cloudflare returns `Error 1027: Worker exceeded free tier daily request limit`. All requests to `api.rateshift.app/*` fail completely. The frontend (on Vercel) shows errors for every API call. No graceful fallback exists.

## Acceptance Criteria

- [ ] KV write operations reduced by 90%+ (from ~1-2 per request to ~0.05-0.1)
- [ ] Rate limiting works without any KV writes (via native `ratelimit` binding or Cache API approach)
- [ ] Cache hits skip rate limiter KV operations entirely (middleware reordering)
- [ ] All KV operations wrapped in try/catch with graceful degradation (fail-open, not 502)
- [ ] Gateway serves traffic (degraded but functional) when KV daily limits are exhausted
- [ ] Gateway serves traffic (degraded but functional) when request daily limit is hit (frontend fallback)
- [ ] Frontend has circuit breaker / direct-to-origin fallback when CF Worker returns 502/503/1027
- [ ] Rate limiter uses `cacheTtl` on KV reads to reduce read consumption by ~90%
- [ ] KV write coalescing: only write on threshold boundaries, not every request
- [ ] Observability: log/alert when approaching 80% of daily KV or request limits
- [ ] All existing tests pass, new tests cover degradation paths
- [ ] Worker deployed and verified in production

## Dependencies

- Cloudflare account (existing: `b41be0d03c76c0b2cc91efccdb7a10df`)
- Cloudflare Workers KV namespaces (existing: CACHE + RATE_LIMIT)
- Wrangler CLI for deployment
- Frontend `next.config.ts` may need fallback origin config
- Optional: Cloudflare Workers Paid plan ($5/month) for 10M requests + 1M KV writes

## Out of Scope

- Migrating away from Cloudflare Workers entirely
- Implementing Durable Objects (adds complexity, latency for non-local users)
- Changing the backend (Render) rate limiting — this track is CF Worker only
- Adding new API endpoints or routes
- Changing existing rate limit values (120/30/600 per min)

## Technical Notes

### Cloudflare Free vs Paid Plan Comparison

| Resource | Free Plan | Paid Plan ($5/mo) | Improvement |
|---|---|---|---|
| Requests/day | 100,000 | ~333,333/day (10M/mo) | 3.3x |
| KV reads/day | 100,000 | ~333,333/day (10M/mo) | 3.3x |
| KV writes/day | 1,000 | ~33,333/day (1M/mo) | 33x |
| CPU time/invocation | 10ms | 5 minutes | 30,000x |
| Subrequests (external) | 50 | 10,000 | 200x |

### Native Rate Limit Binding (GA since Sept 2025)

Cloudflare's native `ratelimit` binding maintains counters in-memory on the same machine as the Worker — **zero KV operations**. Configuration in `wrangler.toml`:

```toml
[[unsafe.bindings]]
type = "ratelimit"
name = "RATE_LIMITER"
namespace_id = "1001"
simple = { limit = 120, period = 60 }
```

Usage: `const { success } = await env.RATE_LIMITER.limit({ key: clientIp })`. Per-location, eventually consistent (same tradeoff as KV-based approach, but free of KV write costs).

### KV Read Caching via `cacheTtl`

KV `.get()` supports a `cacheTtl` parameter that caches the value at the edge for N seconds:
```typescript
const val = await env.RATE_LIMIT.get(key, { cacheTtl: 30 });
```
Reduces actual KV reads to ~1 per 30 seconds per edge node per key, instead of 1 per request.

### Write Coalescing Pattern

Instead of writing on every request, only write at boundary thresholds:
```typescript
const shouldWrite = current === 0 || current >= limit - 10 || current % 20 === 0;
```
Reduces KV writes by 80-95% while maintaining effective enforcement near the limit.

### Frontend Direct-to-Origin Fallback

When CF Worker returns 502/503/1027, the frontend should fall back to calling Render directly:
```
Primary: api.rateshift.app (CF Worker) → Render origin
Fallback: electricity-optimizer.onrender.com (direct)
```
This requires CORS configuration on the Render backend and a circuit breaker in the frontend API client.

---

_Generated by Conductor. Review and edit as needed._
