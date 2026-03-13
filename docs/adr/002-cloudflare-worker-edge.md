# ADR-002: Cloudflare Worker Edge Layer

**Status**: Accepted
**Date**: 2026-03-06
**Decision Makers**: Devin McGrath

## Context

The backend on Render's free tier has cold starts and limited request capacity. We needed an edge layer to:
- Cache frequent API responses to reduce backend load
- Rate limit requests without backend involvement
- Add security headers and bot detection
- Provide graceful degradation if the backend is slow or down

Options considered: Cloudflare Worker, Vercel Edge Middleware, AWS CloudFront + Lambda@Edge, direct Render.

## Decision

Deploy a **Cloudflare Worker** (`rateshift-api-gateway`) at `api.rateshift.app` as the edge proxy.

- **2-tier caching**: Cache API (primary) + KV namespace (fallback), `cacheTtl` on KV reads
- **Native rate limiting**: CF rate limiting bindings (120/30/600 req/min), zero KV cost
- **Fail-open**: If KV is down, requests pass through with `X-Gateway-Degraded` header
- **Free plan**: Stays within CF Workers free tier limits

## Consequences

### Positive
- Cache hits never reach Render, reducing cold starts and load
- Rate limiting at edge is more efficient than backend middleware
- Bot detection blocks abuse before it reaches the application
- Security headers applied consistently at edge
- `/internal/gateway-stats` endpoint for observability

### Negative
- Additional complexity: 17 source files, 77 tests
- Cache invalidation requires careful key design (varyOn `utility_type`)
- Frontend needs circuit breaker for edge-layer outages (CLOSED/OPEN/HALF_OPEN)
- Debugging requires checking both Worker logs and backend logs
- Must stay within free plan limits (see `docs/CF_WORKER_PLAN_GUIDE.md`)
