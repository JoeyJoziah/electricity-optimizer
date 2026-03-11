# Scaling Plan -- RateShift (RateShift)

> Created: 2026-03-10
> Target: 500+ concurrent users with 99.5%+ availability

## Table of Contents

1. [Current State](#current-state)
2. [Render Backend Scaling](#render-backend-scaling)
3. [Neon Database Scaling](#neon-database-scaling)
4. [Redis / Cache Layer](#redis--cache-layer)
5. [CDN and Static Assets](#cdn-and-static-assets)
6. [Cost Projections](#cost-projections)
7. [Scaling Triggers](#scaling-triggers)
8. [Migration Checklists](#migration-checklists)
9. [Load Test Baseline](#load-test-baseline)
10. [Horizontal Scaling Considerations](#horizontal-scaling-considerations)

---

## Current State

| Component | Current Tier | Specs | Monthly Cost |
|-----------|-------------|-------|-------------|
| Frontend | Vercel (Free/Hobby) | Unlimited bandwidth, Edge CDN, auto-scaling | $0 |
| Backend | Render Free | 512MB RAM, 0.5 CPU, auto-sleep after 15min | $0 |
| Database | Neon Free | 0.25 CU compute, 512MB storage, 100h/mo active | $0 |
| Redis | None | In-memory fallback for rate limiter (not shared across workers) | $0 |
| Monitoring | UptimeRobot Free + Better Stack Free | 50 monitors (5min) + 10 monitors (3min) | $0 |
| **Total** | | | **$0/mo** |

### Current Bottlenecks

- **Render auto-sleep**: Backend goes idle after 15 minutes of inactivity. Cold start takes 20-30 seconds, causing first-request failures for returning users.
- **DB connection pool**: `pool_size=3, max_overflow=5` (8 max). Sufficient for single-worker free tier but will saturate under concurrent load.
- **Single worker**: Uvicorn runs with `--workers 1`. No parallelism for CPU-bound ML inference or concurrent DB queries.
- **No shared rate limiter**: In-memory rate limiter is per-process. Multiple workers would each have their own counter, making rate limits inconsistent.
- **Neon compute limits**: Free tier suspends after 100h/month active time (~3.3h/day average). Sustained traffic will exhaust this.

---

## Render Backend Scaling

### Tier Progression

| Tier | RAM | CPU | Auto-Sleep | Custom Domain | Price |
|------|-----|-----|-----------|---------------|-------|
| Free | 512MB | 0.5 shared | Yes (15min) | No | $0 |
| Starter | 512MB | 0.5 shared | **No** | **Yes** | $7/mo |
| Standard | 2GB | 1 dedicated | No | Yes | $25/mo |
| Pro | 4GB | 2 dedicated | No | Yes | $85/mo |

### Recommended Path

**Phase 1 -- Launch (0-50 DAU): Starter ($7/mo)**

The single most impactful upgrade. Eliminates auto-sleep, which causes 20-30 second cold starts that degrade user experience and trigger UptimeRobot false alarms.

- No code changes required.
- Health check endpoint (`/health`) already configured in `render.yaml`.
- Custom domain support enables `api.rateshift.app`.
- Keep `--workers 1` (512MB is insufficient for multiple workers).

**Phase 2 -- Growth (50-200 DAU): Standard ($25/mo)**

2GB RAM enables running 2 Uvicorn workers, doubling request throughput.

- Update Dockerfile CMD: `--workers 2` (rule of thumb: 2x CPU cores, but stay conservative with 2GB).
- Requires Redis for shared rate limiting (see [Redis section](#redis--cache-layer)).
- Increase DB pool: `DB_POOL_SIZE=5, DB_MAX_OVERFLOW=10` (15 max, within Neon Launch plan limits).

**Phase 3 -- Scale (200-500 DAU): Standard + optimization**

Same Render tier, but optimize the application layer.

- Enable response caching (Redis-backed) for public endpoints.
- Consider Gunicorn with Uvicorn workers for better process management.
- Review and optimize slow queries identified by the `request_completed` structured logs.

**Phase 4 -- Beyond 500 DAU: Pro ($85/mo)**

4GB RAM enables 3-4 workers. At this point, consider horizontal scaling (multiple Render instances behind a load balancer) or migrating to a container orchestration platform.

### Health Check Configuration

Already configured in `render.yaml`:

```yaml
healthCheckPath: /health
```

For zero-downtime deploys on paid tiers, Render performs rolling deploys:
1. New instance starts and passes health check.
2. Traffic shifts to the new instance.
3. Old instance drains existing connections and shuts down.

No additional configuration is needed -- this is automatic on Render paid tiers.

### Worker Count Guidance

| Render Tier | RAM | Recommended Workers | Max DB Pool (total) |
|-------------|-----|--------------------|--------------------|
| Free/Starter | 512MB | 1 | 8 (3+5) |
| Standard | 2GB | 2 | 15 (5+10) per worker, 30 total |
| Pro | 4GB | 3-4 | 10 (5+5) per worker, 30-40 total |

**Important**: Each Uvicorn worker gets its own connection pool. With 2 workers at `pool_size=5, max_overflow=10`, the total max connections are 30. Neon Launch plan supports ~50 connections via PgBouncer pooling.

---

## Neon Database Scaling

### Tier Progression

| Tier | Compute | Storage | Active Hours | Autoscaling | Price |
|------|---------|---------|-------------|-------------|-------|
| Free | 0.25 CU | 512MB | 100h/mo | No | $0 |
| Launch | 1 CU | 10GB | 300h/mo | No | $19/mo |
| Scale | 2 CU | 50GB | Unlimited | **0.25-8 CU** | $69/mo |

### Connection Pool Optimization

The pool settings are now configurable via environment variables (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`) so scaling is a config change, not a code change.

| User Tier | DB_POOL_SIZE | DB_MAX_OVERFLOW | Total Max | Neon Plan |
|-----------|-------------|-----------------|-----------|-----------|
| Current (free) | 3 | 5 | 8 | Free |
| Launch (50-200) | 5 | 10 | 15 | Launch |
| Growth (200-500) | 10 | 20 | 30 | Scale |
| Scale (500+, 2 workers) | 5 per worker | 10 per worker | 30 | Scale |

### Neon Autoscaling (Scale Plan)

The Scale plan includes autoscaling from 0.25 to 8 CU. This means the database automatically allocates more compute during traffic spikes and scales down during quiet periods:

```
Neon console > Project settings > Compute > Autoscaling
  Min: 0.25 CU (idle/low traffic)
  Max: 2 CU (peak traffic)
  Scale-to-zero: Enabled (suspends after 5min idle to save costs)
```

### Read Replicas (Analytics Offloading)

Neon supports read replicas via branching at no additional cost on the Scale plan. Use for:

- KPI report queries (`/internal/kpi-report`) -- heavy aggregation across multiple tables.
- Connection analytics dashboards -- historical data analysis.
- ML training data extraction -- batch reads that should not compete with real-time queries.

Implementation: Create a `DATABASE_READ_URL` env var pointing to a Neon read replica branch. Route analytics queries to this connection.

### Storage Projections

| Timeframe | Estimated Storage | Notes |
|-----------|------------------|-------|
| Current | ~50MB | 25 migrations, seed data, small user base |
| 6 months (200 users) | ~500MB | Price history, weather cache, alerts |
| 12 months (500 users) | ~2GB | Connection data, bill uploads, ML features |
| 24 months (2000 users) | ~8GB | Full analytics history, all caches |

The Free tier (512MB) is sufficient for launch. Upgrade to Launch (10GB) when approaching 400MB to maintain headroom.

---

## Redis / Cache Layer

### Why Redis

Currently the application has no Redis. The rate limiter falls back to in-memory storage (logged as a warning in `app_factory.py`). This works for a single worker but breaks with multiple workers or horizontal scaling because each process maintains its own counters.

### Recommended: Upstash Redis (Serverless)

| Tier | Commands/day | Storage | Price |
|------|-------------|---------|-------|
| Free | 10K | 256MB | $0 |
| Pay-as-you-go | Unlimited | 1GB | ~$0.20/100K commands |
| Pro | Unlimited | 10GB | $10/mo flat |

**Recommendation**: Start with the Free tier (10K commands/day). A single user session generates approximately 5-10 Redis commands (rate limit check + cache reads). At 50 DAU with average 5 page views, that is roughly 1,250-2,500 commands/day -- well within the free tier. Upgrade to Pay-as-you-go at 200 DAU.

### Implementation

The `REDIS_URL` env var already exists in `backend/config/settings.py` and `render.yaml`. The `DatabaseManager._init_redis()` method and `app_factory.py` rate limiter wiring already handle Redis gracefully:

1. Set `REDIS_URL` on Render to the Upstash connection string.
2. The rate limiter will automatically switch from in-memory to Redis.
3. No code changes required.

### Cache Strategy (Future Enhancement)

Once Redis is available, add response caching for frequently accessed public endpoints:

| Endpoint | TTL | Cache Key | Rationale |
|----------|-----|-----------|-----------|
| `GET /prices/current?region=X` | 5 min | `prices:{region}` | Price data updates every 15-30 min |
| `GET /suppliers` | 1 hour | `suppliers:all` | Supplier registry is static (37 rows) |
| `GET /suppliers/registry` | 1 hour | `suppliers:registry` | Same as above |
| Weather data (internal) | 6 hours | `weather:{region}` | Matches fetch-weather cron interval |
| Market intelligence | 24 hours | `market:{topic}` | Matches market-research daily cron |

**Implementation pattern** (future work, not part of this plan):

```python
# In the route handler:
cached = await redis.get(f"prices:{region}")
if cached:
    return json.loads(cached)
# ... fetch from DB ...
await redis.setex(f"prices:{region}", 300, json.dumps(result))
```

---

## CDN and Static Assets

### Frontend (Vercel)

Vercel provides a global Edge CDN by default. No changes needed. The `next.config.js` already enables:

- `output: 'standalone'` for optimized builds.
- `compress: true` for Gzip.
- Image optimization with AVIF/WebP formats.
- Package import optimization for date-fns, lucide-react, recharts.

### Backend (Render)

The FastAPI backend already includes `GZipMiddleware` (minimum 500 bytes). For further optimization:

- **Static assets**: The backend serves no static assets directly. All UI assets are on Vercel.
- **API caching**: Public endpoints (prices, suppliers) can be cached at the Cloudflare level if a proxy is placed in front of the Render service. This is a future optimization, not needed before 500 DAU.

### API Response Caching (Future)

If a Cloudflare proxy is added in front of `api.rateshift.app`:

```
Cache-Control: public, max-age=300  # 5 min for prices
Cache-Control: public, max-age=3600 # 1 hour for suppliers
Cache-Control: no-store             # Authenticated endpoints
```

This would offload read traffic from Render entirely for public endpoints.

---

## Cost Projections

| DAU | Render | Neon | Redis | Monitoring | Total/mo | Per-User/mo |
|-----|--------|------|-------|------------|----------|-------------|
| <50 | $0 (Free) | $0 (Free) | $0 (Free) | $0 (Free) | **$0** | $0 |
| 50-100 | $7 (Starter) | $19 (Launch) | $0 (Free) | $0 (Free) | **$26** | $0.26-0.52 |
| 100-200 | $7 (Starter) | $19 (Launch) | $0 (Free) | $6 (Better Stack) | **$32** | $0.16-0.32 |
| 200-500 | $25 (Standard) | $19 (Launch) | $10 (Upstash Pro) | $6 | **$60** | $0.12-0.30 |
| 500-1000 | $25 (Standard) | $69 (Scale) | $10 | $6 | **$110** | $0.11-0.22 |
| 1000-2000 | $85 (Pro) | $69 (Scale) | $20 | $6 | **$180** | $0.09-0.18 |

### Revenue vs. Cost

With Stripe billing at $4.99/mo (Pro) and $14.99/mo (Business):

| Scenario | Paying Users | Est. MRR | Infra Cost | Margin |
|----------|-------------|----------|-----------|--------|
| 200 DAU, 10% conversion | 20 Pro | $100 | $32 | 68% |
| 500 DAU, 15% conversion | 60 Pro + 15 Biz | $524 | $60 | 89% |
| 1000 DAU, 20% conversion | 150 Pro + 50 Biz | $1,498 | $110 | 93% |

Infrastructure costs remain under 15% of revenue in all projected scenarios beyond 200 DAU.

---

## Scaling Triggers

These are the signals that indicate an upgrade is needed. Monitor via structured logs, UptimeRobot, and the `scripts/scale_check.py` diagnostic.

### Immediate Action (P0)

| Trigger | Threshold | Action |
|---------|----------|--------|
| p95 latency > 1500ms sustained (30min+) | Load test threshold | Upgrade Render tier or add workers |
| DB connection pool exhaustion | `asyncpg.exceptions.TooManyConnectionsError` in logs | Increase `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` or upgrade Neon |
| Neon active hours > 80h/month | 80% of free tier 100h limit | Upgrade to Neon Launch ($19) |
| Error rate > 5% sustained (1h+) | Load test threshold | Investigate root cause; likely infra bottleneck |

### Planned Upgrade (P1)

| Trigger | Threshold | Action |
|---------|----------|--------|
| Cold start complaints from users | Any | Upgrade Render Free to Starter ($7) |
| Rate limiter inconsistency (multi-worker) | Deploying 2+ workers | Add Redis (Upstash Free) |
| Storage > 400MB | 80% of Neon free tier | Upgrade to Neon Launch ($19) |
| p95 latency > 1000ms at 500 VU load test | Approaching SLA ceiling | Upgrade to Render Standard ($25) |

### Optimization (P2)

| Trigger | Threshold | Action |
|---------|----------|--------|
| Redis commands > 8K/day | 80% of Upstash free tier | Upgrade to Upstash Pay-as-you-go |
| DB query latency p95 > 500ms | Slow query threshold | Add read replica for analytics |
| Neon autoscaling hitting max CU frequently | Scale plan monitoring | Increase max CU or optimize queries |
| Worker memory > 80% of allocation | Render metrics | Right-size: add workers or upgrade RAM |

---

## Migration Checklists

### Checklist: Render Free to Starter

- [ ] Navigate to Render Dashboard > electricity-optimizer service
- [ ] Settings > Instance Type > Change to "Starter" ($7/mo)
- [ ] Verify health check still passes after restart
- [ ] Confirm auto-sleep is disabled (check service status after 20min idle)
- [ ] Configure custom domain `api.rateshift.app` if not already set
- [ ] Update UptimeRobot monitors to remove cold-start tolerance
- [ ] Run smoke load test: `k6 run --env SCENARIO=smoke scripts/load_test.js`

### Checklist: Add Redis (Upstash)

- [ ] Create Upstash Redis instance (us-east-1 region to match Neon)
- [ ] Copy connection string (format: `rediss://default:PASSWORD@ENDPOINT:PORT`)
- [ ] Set `REDIS_URL` on Render via REST API or dashboard
- [ ] Store `REDIS_URL` in 1Password vault "RateShift"
- [ ] Restart Render service
- [ ] Verify in logs: `rate_limiter_redis_wired` (not `rate_limiter_redis_unavailable`)
- [ ] Test rate limiting from two different IPs to confirm shared state

### Checklist: Render Starter to Standard

- [ ] Upgrade instance type to "Standard" ($25/mo) in Render dashboard
- [ ] Redis must be configured first (required for multi-worker rate limiting)
- [ ] Update Dockerfile CMD to `--workers 2`
- [ ] Set env vars: `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=10`
- [ ] Verify both workers are healthy in Render logs
- [ ] Run standard load test: `k6 run --env SCENARIO=standard scripts/load_test.js`
- [ ] Monitor DB connection count via Neon dashboard for 24h

### Checklist: Neon Free to Launch

- [ ] Navigate to Neon Console > Project cold-rice-23455092 > Settings > Billing
- [ ] Upgrade to Launch plan ($19/mo)
- [ ] Verify compute and storage limits in project dashboard
- [ ] No connection string changes needed (same endpoint)
- [ ] Confirm active hour limit increased (100h to 300h)
- [ ] Consider increasing `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` if on Render Standard

### Checklist: Neon Launch to Scale

- [ ] Upgrade to Scale plan ($69/mo) in Neon console
- [ ] Enable autoscaling: min 0.25 CU, max 2 CU
- [ ] Consider creating a read replica branch for analytics
- [ ] Set `DATABASE_READ_URL` if using read replicas
- [ ] Update `DB_POOL_SIZE=10`, `DB_MAX_OVERFLOW=20` for main connection
- [ ] Run soak load test: `k6 run --env SCENARIO=soak scripts/load_test.js`

---

## Load Test Baseline

The existing `scripts/load_test.js` defines 5 scenarios with clear SLA thresholds:

| Metric | Target | Current Infra (est.) |
|--------|--------|---------------------|
| p95 latency | < 1500ms | ~800ms (warm), 20s+ (cold start) |
| p99 latency | < 2000ms | ~1200ms (warm) |
| Error rate | < 5% | ~2% (warm), 15%+ (cold start spike) |
| Throughput | > 100 req/s | ~50 req/s (single worker, 0.5 CPU) |

**Before each upgrade**, run the appropriate load test scenario:

```bash
# After Render Starter upgrade (eliminates cold start)
k6 run --env SCENARIO=smoke scripts/load_test.js

# After Standard upgrade (2 workers)
k6 run --env SCENARIO=standard scripts/load_test.js

# After full scaling (Redis + Standard + Neon Scale)
k6 run --env SCENARIO=full scripts/load_test.js

# Monthly regression check
k6 run --env SCENARIO=soak scripts/load_test.js
```

---

## Horizontal Scaling Considerations

Beyond a single Render Standard instance (the 500-1000 DAU range), horizontal scaling becomes necessary.

### Render Horizontal Scaling

Render does not natively support multiple instances of a single service behind a load balancer on the web service tier. Options:

1. **Render Private Services + Caddy/Nginx**: Deploy multiple backend instances as private services and a Caddy reverse proxy as the public-facing web service.
2. **Container orchestration**: Migrate to Railway, Fly.io, or AWS ECS for native horizontal scaling with auto-scaling groups.
3. **Serverless hybrid**: Offload stateless read endpoints to Vercel Edge Functions while keeping the FastAPI backend for write operations and ML inference.

### Stateless Requirements for Horizontal Scaling

The current architecture is nearly stateless. Remaining state:

| State | Location | Fix for Multi-Instance |
|-------|----------|----------------------|
| Rate limiter counters | In-memory | Redis (already planned) |
| DB connection pool | Per-process | Already isolated; just ensure total connections fit Neon limits |
| ML model cache | In-memory | Acceptable -- each instance loads model independently |
| File uploads (bill OCR) | Local disk | Move to Cloudflare R2 or S3 |

Once Redis is added and file uploads are externalized, the backend is fully horizontally scalable.

---

## Appendix: Environment Variables for Scaling

These environment variables control scaling-relevant configuration. All have sensible defaults that match the current free-tier setup.

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `None` | Redis connection string. When absent, rate limiter uses in-memory fallback. |
| `DB_POOL_SIZE` | `3` | SQLAlchemy connection pool base size. |
| `DB_MAX_OVERFLOW` | `5` | SQLAlchemy pool overflow (max total = pool_size + max_overflow). |
| `DATABASE_READ_URL` | `None` | Optional read replica connection string for analytics queries. |

Set via Render Dashboard or REST API:

```bash
# Example: upgrade pool for Render Standard with 2 workers
curl -X PUT "https://api.render.com/v1/services/srv-d649uhur433s73d557cg/env-vars" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '[{"key":"DB_POOL_SIZE","value":"5"},{"key":"DB_MAX_OVERFLOW","value":"10"}]'
```

---

**Last Updated**: 2026-03-10
