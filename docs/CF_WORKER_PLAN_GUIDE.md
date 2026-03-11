# Cloudflare Worker Plan Guide

## Current Setup

- **Worker**: `rateshift-api-gateway` at `api.rateshift.app`
- **Plan**: Workers Free (with paid features via custom domain route)
- **Account**: `b41be0d03c76c0b2cc91efccdb7a10df`

## Free Tier Limits

| Resource | Daily Limit | Per Request |
|----------|-------------|-------------|
| Worker requests | 100,000/day | N/A |
| KV reads | 100,000/day | ~1 per cache miss |
| KV writes | 1,000/day | ~1 per cache store |
| KV deletes | 1,000/day | On price refresh only |
| KV list ops | 1,000/day | On price refresh only |
| CPU time | 10ms/invocation | Varies |

## Current KV Usage (Post-Optimization)

After the resilience overhaul (Phases 1-3), KV usage is drastically reduced:

- **Rate limiting**: Zero KV operations (migrated to native `ratelimit` bindings)
- **Cache reads**: Reduced ~98% via `cacheTtl: 30` (edge-cached KV reads)
- **Cache writes**: Reduced 50-80% via cache-before-rate-limit reordering (hits skip origin)
- **Cache deletes**: Only on POST /prices/refresh (typically 1-2x daily)

### Estimated Daily KV Operations

| Traffic Level | Requests/day | KV Reads | KV Writes | Within Free? |
|---------------|-------------|----------|-----------|--------------|
| Low (current) | ~5,000 | ~100 | ~50 | Yes |
| Medium | ~20,000 | ~400 | ~200 | Yes |
| High | ~50,000 | ~1,000 | ~500 | Yes |
| Very High | ~100,000 | ~2,000 | ~1,000 | Borderline |

**Key insight**: With `cacheTtl` on KV reads, actual KV reads are ~2% of cache lookups.
Cache hits from the Cache API (tier 1) don't touch KV at all.

## Resilience Features

Even if free tier limits are hit:

1. **Graceful degradation**: KV failures result in fail-open (cache misses, unmetered requests) — not 502s
2. **Frontend circuit breaker**: After 3 consecutive 502/503 errors, frontend falls back to Render backend directly
3. **Native rate limiting**: Uses zero-cost native bindings — unaffected by KV limits
4. **Gateway stats**: `/api/v1/internal/gateway-stats` endpoint monitors degradation in real time
5. **GHA health checks**: `gateway-health.yml` runs every 6 hours, alerts Slack on degradation

## Workers Paid Plan ($5/month)

### What you get

| Resource | Free | Paid ($5/mo) |
|----------|------|--------------|
| Worker requests | 100K/day | 10M/month included |
| KV reads | 100K/day | 10M/month included |
| KV writes | 1K/day | 1M/month included |
| CPU time | 10ms | 30s (Bundled) or 30ms (Standard) |
| Cron triggers | 5 | 5 |
| Durable Objects | No | Yes |

### When to upgrade

Upgrade when any of these are true:
- Daily requests consistently exceed 80,000
- KV writes consistently exceed 800/day
- `gateway-health.yml` reports degradation more than once per week
- You need Durable Objects, Workers Analytics Engine, or Queues

### How to upgrade

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/) > Workers & Pages > Plans
2. Select "Workers Paid" ($5/month)
3. After upgrade, optionally update `wrangler.toml`:
   ```toml
   # Only needed if switching to Standard usage model (default is Bundled)
   # Standard: charged per CPU-ms but no 10ms limit
   # Bundled: 30s CPU limit, billed per request after 10M
   # usage_model = "standard"
   ```
4. Deploy: `npx wrangler deploy`
5. Update CLAUDE.md architecture section to reflect paid plan

### Cost projection

At current traffic (~5K requests/day):
- **Free plan**: $0/month, well within limits
- **Paid plan**: $5/month, massive headroom

At 50K requests/day:
- **Free plan**: $0/month, approaching limits on high-write days
- **Paid plan**: $5/month + ~$0.50 overage = ~$5.50/month

**Recommendation**: Stay on free plan. The resilience features (graceful degradation + circuit breaker) handle edge cases without cost. Upgrade only when growth requires it.
