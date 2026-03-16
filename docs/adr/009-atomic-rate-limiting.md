# ADR-009: Atomic Rate Limiting at the Edge

**Status**: Accepted
**Date**: 2026-03-09
**Decision Makers**: Devin McGrath

## Context

RateShift's API needed rate limiting to prevent abuse and stay within Render's free tier capacity. The initial implementation used Cloudflare Workers KV for rate limit counters, but this had problems:

- KV writes are eventually consistent (race conditions under concurrent requests)
- Each rate limit check required a KV read + write, consuming KV operation quota
- KV has a 1,000 writes/day free tier limit, easily exhausted by rate limiting alone
- Non-atomic increment: two concurrent requests could both read the same count and both pass

Options considered: KV-based counters, Durable Objects, Cloudflare native rate limiting bindings, backend-side rate limiting.

## Decision

Migrate to **Cloudflare native rate limiting bindings** for all edge rate limiting.

### Configuration (in `wrangler.toml`)
Three tiers of rate limits:
- **Standard**: 120 requests/minute (general API endpoints)
- **Strict**: 30 requests/minute (auth endpoints, write operations)
- **Burst**: 600 requests/minute (read-heavy public endpoints)

### Implementation (`workers/api-gateway/src/middleware/rate-limiter.ts`)
- Uses CF `RATE_LIMITER` binding (native, per-isolate, atomic)
- Rate limit key: client IP (from `CF-Connecting-IP` header)
- Returns `429 Too Many Requests` with `Retry-After` header when tripped
- Zero KV operations for rate limiting (KV reserved for caching only)

### Backend fallback
- `RequestTimeoutMiddleware` in FastAPI provides a secondary timeout (30s)
- Internal endpoints (`/api/v1/internal/*`) are excluded from both edge and backend rate limiting

## Consequences

### Positive
- Atomic counters: no race conditions under concurrent requests
- Zero KV cost for rate limiting (stays within free plan)
- Lower latency: native binding is faster than KV read+write
- Simpler code: no manual TTL management or counter reset logic
- Rate limiting happens before any backend processing

### Negative
- Native rate limiting is per-isolate, not globally distributed (a user hitting different edge locations gets separate counters)
- Less flexibility than custom KV logic (e.g., cannot implement sliding window easily)
- Tied to Cloudflare platform (no local development equivalent; tests use mocks)
- `CF-Connecting-IP` can be spoofed if not behind Cloudflare proxy (mitigated by SSL Full Strict mode)

### Conventions
- New endpoints must be assigned a rate limit tier in the Worker router config
- Rate limit tiers are defined in `workers/api-gateway/src/config.ts`
- KV namespace `CACHE` is for caching only; never use it for counters
- Test rate limiting behavior with the mock bindings in `workers/api-gateway/test/`
