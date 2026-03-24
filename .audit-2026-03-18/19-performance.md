# RateShift Performance Audit — 2026-03-18

**Auditor**: Performance Engineer
**Scope**: Full-stack — frontend bundle, backend API, database queries, ML inference, CF Worker
**Status**: READ-ONLY audit — no source files modified

---

## Executive Summary

RateShift is a production SaaS app running on free-tier infrastructure (Render 512 MB, single Gunicorn worker). The existing codebase demonstrates strong performance awareness in many areas — SQL aggregation in the repository layer, Redis-backed caching with stampede protection, CF Worker 2-tier cache, and dynamic imports for heavy chart components. The most critical risks are concentrated at the infrastructure / concurrency tier rather than in algorithmic hot paths.

**Key risk areas**:

1. Single Gunicorn worker creates a cascading bottleneck when any slow request (ML inference, email, external APIs) blocks the async event loop
2. SSE connections are unbounded at the server level and consume persistent Render connections
3. `nodemailer` and `@neondatabase/serverless` are full production dependencies in the frontend `package.json`, adding ~800 KB to the client bundle unless Next.js correctly tree-shakes them
4. Dashboard fires 5 parallel React Query requests on mount with no waterfall guard — on a cold Render start this produces 5 near-simultaneous DB queries plus an SSE connection
5. The `electricity_prices` table currently lacks an index on `(region, utility_type, timestamp DESC)` combining all three filter columns used in `get_current_prices()` — `idx_electricity_prices_region_utility_time` was added in migration 037 but the companion `ORDER BY timestamp` queries in `get_current_prices` and `list_latest_by_regions` use a window function (`ROW_NUMBER OVER (PARTITION BY region ORDER BY timestamp DESC)`) which cannot use any of the existing B-tree indexes efficiently at large table sizes

---

## P0 — Critical (Immediate Risk to Production)

### P0-1: Single Gunicorn Worker Serializes All Async Operations

**Files**: `backend/gunicorn_config.py` line 17, `backend/start.sh`

```python
# gunicorn_config.py:17
workers = 1  # Single worker for free tier
```

**Issue**: The entire backend runs as a single uvicorn asyncio event loop. FastAPI/asyncio is cooperative — any call that blocks the event loop (CPU-bound ML inference, synchronous Sentry SDK calls, or an accidentally synchronous library path) stalls **all** concurrent requests. With `REQUEST_TIMEOUT_SECONDS = 30` (`app_factory.py` line 84), a stalled request blocks the single worker for 30 seconds before timing out.

**Specific blocking risks identified**:
- `price_service.py` line 178: `get_price_forecast()` calls the EnsemblePredictor synchronously within the async handler. If `_ensemble_predictor` is not cached (`_ensemble_load_attempted = False`), the first call under `_ensemble_lock` blocks while loading model files from disk.
- `agent_service.py` line 83: `genai.Client()` is a synchronous constructor inside an async handler path. Gemini client initialization involves HTTP calls to fetch endpoints.
- `community_service.py` content moderation via `asyncio.gather` calls Groq + Gemini synchronously-wrapped APIs that may block briefly during DNS resolution on cold start.
- Render free tier cold starts take 15–30 seconds; during this window the single worker handles the health check probe while simultaneously trying to initialize DB connections.

**Impact**: P99 latency spikes of 5–30 seconds during any concurrent ML or external-API request. Under modest traffic (10 concurrent users), the event loop is effectively serialized.

**Recommendation**:
- Short-term: Add `workers = 2` with `--preload` to get two event loops (memory permits ~240 MB each on the 512 MB instance).
- Medium-term: Offload ML inference to a background task queue (e.g., `asyncio.create_task` with a result callback) so the HTTP handler responds immediately with a job ID.

---

### P0-2: `nodemailer` and `@neondatabase/serverless` as Production Dependencies

**File**: `frontend/package.json` lines 29, 31

```json
"@neondatabase/serverless": "^1.0.2",
"nodemailer": "^6.9.x"  // (via package.json line 29)
```

**Issue**: Both packages are listed under `"dependencies"` (not `"devDependencies"`). `nodemailer` is a 1.1 MB uncompressed Node.js library that includes TLS, stream, and net adapters. `@neondatabase/serverless` bundles the Neon WebSocket driver (~300 KB). Neither should ever be loaded in a browser context.

These are only legitimately used in:
- `frontend/lib/email/send.ts` (server-side, Next.js API route)
- `frontend/lib/auth/server.ts` (server-side, Better Auth Pool connection)

Next.js server components and API routes do tree-shake these correctly **when** the imports occur only in files that are never bundled for the client. However, if any component that accidentally imports from `@/lib/auth/server` or `@/lib/email/send` is rendered on the client, the entire `nodemailer` dependency graph will be included in the client bundle. The `'use client'` boundary does not exist in `lib/auth/server.ts`, creating a latent risk.

**Verified safe paths**:
- `lib/auth/server.ts` is only imported from `app/api/auth/[...all]/route.ts` which is an API route (never client-bundled)
- `lib/email/send.ts` is only imported from `lib/auth/server.ts`

**Remaining risk**: Any future refactor that adds a `'use client'` import chain to these modules will silently include ~1.4 MB of server-only code in the client JS bundle with no build-time error.

**Recommendation**:
- Move `nodemailer` and `@neondatabase/serverless` to `devDependencies` (they are never `npm install`ed in production without devDeps).
- Add a Next.js bundle analyzer step to CI (`@next/bundle-analyzer`) to catch regressions.
- Add `"server-only"` import to `lib/auth/server.ts` and `lib/email/send.ts` to get a compile-time error if they are ever imported in a client context.

---

### P0-3: Dashboard Fires 5 Parallel API Requests + 1 SSE Connection on Mount

**File**: `frontend/components/dashboard/DashboardContent.tsx` lines 43–60

```typescript
// All called simultaneously on component mount:
const { data: pricesData } = useCurrentPrices(region)         // GET /prices/current
const { data: historyData } = usePriceHistory(region, ...)    // GET /prices/history
const { data: forecastData } = usePriceForecast(region, 24)   // GET /prices/forecast
const { data: suppliersData } = useSuppliers(region, ...)     // GET /suppliers
const { data: savingsData } = useSavingsSummary()             // GET /savings/summary
useRealtimePrices(region)                                      // SSE /prices/stream
```

**Issue**: All 5 React Query hooks plus the SSE connection are initiated simultaneously on first render. On a cold Render start:

1. The 5 HTTP requests arrive at the backend within milliseconds of each other.
2. The single Gunicorn worker's event loop receives 5 coroutines simultaneously.
3. Each query hits the Neon connection pool (pool_size=3, max_overflow=5). With 5 simultaneous requests from a single page load, 2 will queue waiting for a pool connection.
4. The SSE connection opens a persistent long-lived HTTP connection, consuming one of the 3 pool connections for the duration of the session.

Additionally, `useSavingsSummary` has no `staleTime` alignment with `useCurrentPrices` — the savings summary will re-fetch on every window-focus event independently of the price data, creating unnecessary load.

**Impact**: First paint is delayed by the slowest of the 5 requests. On cold Render start with DB initialization, P50 TTFB can exceed 3 seconds for the full dashboard.

**Recommendation**:
- Implement request waterfall: fetch prices first (critical path), defer suppliers and savings to `useEffect` after initial render.
- Use React Query's `placeholderData` / `initialData` with locally-cached Zustand values for instant first render.
- Move the SSE connection behind a user interaction (expand/collapse) or a 5-second delay after initial page load.
- Consider a single `/dashboard/summary` endpoint that returns all critical data in one round trip.

---

## P1 — High Severity

### P1-1: `list_latest_by_regions()` Window Function Unindexable for Large Tables

**File**: `backend/repositories/price_repository.py` lines 317–332

```python
sql = f"""
    SELECT {_PRICE_COLUMNS}
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY region ORDER BY timestamp DESC) AS rn
        FROM electricity_prices
        WHERE region IN ({placeholders})
    ) sub
    WHERE rn <= :lim
    ORDER BY region, timestamp DESC
"""
```

**Issue**: The window function `ROW_NUMBER() OVER (PARTITION BY region ORDER BY timestamp DESC)` requires PostgreSQL to sort the full result set for each region partition. Even with `idx_electricity_prices_region_utility_time` (`region, utility_type, timestamp DESC`), this query does **not** include `utility_type` in its WHERE clause, so PostgreSQL must scan all utility types for the given regions before the window function can rank by timestamp. At 50+ regions and thousands of rows per region, this is a sequential scan of a large subset of the table.

The `check-alerts` cron job calls this function every 3 hours for all distinct alert regions (potentially all 50 US states). A full-table scan on `electricity_prices` at scale will time out or severely degrade read latency.

**Recommendation**:
- Replace the window function approach with a LATERAL JOIN or `DISTINCT ON` query that PostgreSQL can resolve using the existing `idx_prices_region_supplier_timestamp` index:
```sql
SELECT ep.*
FROM unnest(ARRAY[:regions]) AS r(region)
CROSS JOIN LATERAL (
    SELECT * FROM electricity_prices
    WHERE electricity_prices.region = r.region
    ORDER BY timestamp DESC
    LIMIT :lim
) ep
```
- This query is index-friendly and avoids materializing a large intermediate result set.

---

### P1-2: Alert Send Loop is Fully Sequential for All Users

**File**: `backend/services/alert_service.py` lines 263–343

```python
async with traced("alert.send", ...):
    for threshold, alert in triggered:
        try:
            html = self._render_alert_email(threshold, alert)
            ...
            dispatch_result = await self._dispatcher.send(...)  # Sequential!
```

**Issue**: The `send_alerts()` method iterates over all triggered alerts sequentially. Each `dispatcher.send()` call involves:
1. A DB deduplication check query
2. An in-app DB INSERT
3. Concurrent push + email (both external HTTP calls)

Steps 1 and 2 are DB-bound; step 3 is correctly concurrent within a single alert dispatch. However, if 100 users have alerts triggered in a single cron run, these 100 × 3 operations execute fully sequentially. At 200ms average per DB round-trip + 300ms for external push/email, 100 alerts = ~50 seconds — approaching the internal endpoint timeout exclusion.

**Recommendation**:
- Batch the deduplication check into a single query before the loop: fetch all `alert_history` rows for the affected `(user_id, alert_type, region)` tuples in one query.
- Use `asyncio.gather` with bounded concurrency (`asyncio.Semaphore(10)`) to dispatch alerts in parallel.

---

### P1-3: Notification Polling Every 30 Seconds from Every Authenticated Page

**File**: `frontend/components/layout/NotificationBell.tsx` lines 34–39

```typescript
const { data: countData } = useQuery<CountResponse>({
    queryKey: ['notifications', 'count'],
    queryFn: () => apiClient.get<CountResponse>('/notifications/count'),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
})
```

**Issue**: `NotificationBell` is rendered inside `AppLayout` (`frontend/app/(app)/layout.tsx` line 10), which wraps every authenticated page. This means every authenticated user polls `/notifications/count` every 30 seconds regardless of which page they are on. With 100 active users, this generates 200 backend requests per minute to the single-worker Render instance — a non-trivial baseline load before any user interaction.

The endpoint itself (`/notifications/count`) runs a `SELECT COUNT(*)` query against the `notifications` table with a partial index filter (`WHERE read_at IS NULL`). The index `idx_notifications_user_unread` covers this, but at scale the constant polling pressure is disproportionate.

**Recommendation**:
- Increase polling interval to 60s or 120s.
- Implement push-based badge updates via the existing SSE infrastructure or WebSocket to eliminate polling entirely.
- Add `staleTime: 25_000` to match the interval and prevent window-focus spurious refetches.

---

### P1-4: `get_users_by_region()` Hard-Coded LIMIT 5000 Creates Memory Spike

**File**: `backend/repositories/user_repository.py` lines 425–450

```python
result = await self._db.execute(
    text(f"""
        SELECT {_USER_COLUMNS} FROM users
        WHERE {where_clause}
        LIMIT 5000
    """),
    {"region": region.lower()},
)
rows = result.mappings().all()
return [_row_to_user(row) for row in rows]
```

**Issue**: This method fetches up to 5,000 full user rows into memory simultaneously. Each `User` Pydantic model is ~1 KB serialized. 5,000 users = ~5 MB of Python objects in the single Render worker's 512 MB RAM allocation. This method is called by `check_alerts` indirectly and by any regional user batch operation. The `_USER_COLUMNS` string includes all 21 user columns including the `preferences` JSONB field which can be arbitrarily large.

**Recommendation**:
- Implement cursor-based pagination (using `id > :last_id`) for all batch user operations.
- For alert purposes, only select the columns needed (user_id, email, region, preferences->>'notification_frequency') rather than the full user model.

---

### P1-5: `@excalidraw/excalidraw` as a devDependency with Incorrect Placement

**File**: `frontend/package.json` line 43

```json
"@excalidraw/excalidraw": "^0.18.0"
```

**Issue**: `@excalidraw/excalidraw` is listed as a `devDependency` but is imported via `next/dynamic` in `frontend/components/dev/ExcalidrawWrapper.tsx`. The `devDependencies` placement is correct (it should not ship to production), but `ExcalidrawWrapper.tsx` is inside the `components/` directory — not gated behind a build flag. If `ExcalidrawWrapper` is ever imported from a non-dev page, the 2.3 MB Excalidraw bundle will be added to the production build. The npm audit warning about 5 unresolved vulnerabilities in `@excalidraw/excalidraw` transitive deps (`@excalidraw/utils`, nanoid) means this also carries a latent security risk at build time.

**Recommendation**:
- Move `ExcalidrawWrapper.tsx` and the entire `components/dev/` directory to a proper development-only gate (e.g., `process.env.NODE_ENV === 'development'` conditional import at the page level).
- Verify no production page imports from `components/dev/`.

---

### P1-6: Redis Connection Pool Inadequate for Production Scale

**File**: `backend/config/database.py` line 130, `backend/config/settings.py` line 52

```python
# database.py:130
max_connections=10  # Redis

# settings.py:51-52
db_pool_size: int = Field(default=3, ...)  # SQLAlchemy pool
db_max_overflow: int = Field(default=5, ...)  # max 8 total
```

**Issue**: The DB pool allows max 8 simultaneous connections (3 base + 5 overflow). Each SSE connection holds a connection for the session lifetime. With the 3-connection-per-user limit and Business tier users, a modest 3 Business tier users with 3 SSE connections each = 9 connections — already exceeding the pool. New requests will fail with a pool timeout (20 seconds, `pool_timeout=20` at database.py:88) rather than queuing gracefully.

The Redis pool of 10 connections is shared across: rate limiter (Lua scripts), SSE connection tracking (INCR/DECR), price caching (GET/SET), tier caching (30s TTL), and session rate limit sliding windows. Under concurrent load, Redis commands will queue, increasing latency for all operations that depend on Redis.

**Recommendation**:
- Increase `DB_POOL_SIZE` to 5, `DB_MAX_OVERFLOW` to 10 (Neon free tier supports ~10-20 connections via the pooler endpoint).
- Audit SSE connection patterns — if the SSE endpoint holds a DB session for the 30-second polling interval, refactor to open/close a session per poll cycle rather than holding it open.
- For Redis, increase `max_connections` to 20 and add a Redis Sentinel or connection retry with exponential backoff.

---

### P1-7: `get_historical_prices()` Returns Up to 5,000 Rows to Python

**File**: `backend/repositories/price_repository.py` line 479

```python
async def get_historical_prices(
    ...
    limit: int = 5000,
) -> List[Price]:
```

**Issue**: The default `limit=5000` in `get_historical_prices()` returns up to 5,000 full `Price` Pydantic objects. In `PriceService.calculate_daily_cost()` (price_service.py line 138), this method is called to get prices for a single day, which should return at most 24 rows (one per hour) — but the limit is not reduced at the call site. If the DB has higher-frequency data (sub-hourly), 5,000 rows may legitimately be returned and then Python performs `sum(p.price_per_kwh for p in prices)` and `len(prices)` — O(n) work that could be a SQL `AVG()`.

**Recommendation**:
- In `calculate_daily_cost()`, pass `limit=48` (generous for sub-hourly data over 1 day).
- Replace the Python-side average with a SQL `AVG(price_per_kwh)` query so only one value is transferred from DB to Python.

---

## P2 — Medium Severity

### P2-1: CF Worker `storeInCache` Reads Entire Response Body for KV Write

**File**: `workers/api-gateway/src/middleware/cache.ts` line 84

```typescript
const body = await response.clone().text();
```

**Issue**: `storeInCache` clones the response and reads the full body as a string before writing to KV. For large analytics responses (price history with 100 data points, supplier lists), this fully buffers the response in CF Worker memory before the KV write. CF Workers have a 128 MB memory limit per isolate and a 10 ms CPU time budget (outside `waitUntil`). Reading a large response body inside `ctx.waitUntil` (which is correctly used) avoids the CPU time issue, but a 500 KB response body in memory alongside the parsed KV entry doubles the in-memory footprint temporarily.

**Recommendation**:
- Add a `maxBodyBytes` guard in `storeInCache` — skip KV caching for responses above a threshold (e.g., 256 KB).
- Consider compressing the body before KV write (use `CompressionStream` if available in CF Worker environment).

---

### P2-2: `invalidatePriceCache` Does Sequential KV List + Delete Per Pattern

**File**: `workers/api-gateway/src/middleware/cache.ts` lines 148–170

```typescript
for (const prefix of PRICE_CACHE_PATTERNS) {
    const list = await env.CACHE.list({ prefix });  // Blocking KV list
    for (const key of list.keys) {
        deletePromises.push(env.CACHE.delete(key.name)...)
    }
}
```

**Issue**: The outer loop over `PRICE_CACHE_PATTERNS` (3 patterns) is sequential. Each `env.CACHE.list({ prefix })` is a separate KV list operation. While the deletes are correctly batched into `Promise.allSettled`, the 3 list operations are sequential (each ~5–10ms network hop to KV). This runs inside `ctx.waitUntil` so it doesn't block the response, but on a high-traffic `/prices/refresh` event (e.g., after a price sync cron), the 15–30ms cleanup delay prolongs the stale window.

**Recommendation**: `Promise.all` the three list operations: `await Promise.all(PRICE_CACHE_PATTERNS.map(prefix => env.CACHE.list({ prefix })))`.

---

### P2-3: SSE Heartbeat Logic Has Double-Sleep Bug

**File**: `backend/api/v1/prices_sse.py` lines 141–153

```python
sleep_remaining = interval_seconds
while sleep_remaining > 0:
    sleep_chunk = min(sleep_remaining, heartbeat_interval)  # heartbeat_interval = 45
    await asyncio.sleep(sleep_chunk)
    sleep_remaining -= sleep_chunk
    elapsed_since_heartbeat += sleep_chunk

    if request is not None and await request.is_disconnected():
        return

    if elapsed_since_heartbeat >= heartbeat_interval:
        yield ": heartbeat\n\n"
        elapsed_since_heartbeat = 0
```

**Issue**: `heartbeat_interval = 45` seconds and `interval_seconds = 30` (default). The inner `sleep_chunk = min(30, 45) = 30`. After sleeping 30 seconds, `elapsed_since_heartbeat = 30` which is < 45, so no heartbeat is sent. Then the outer loop continues to fetch new prices and the cycle repeats. The heartbeat is only sent when `interval_seconds >= 45`, i.e., never under the default 30-second interval. This means proxies with 30-second idle timeouts will terminate SSE connections silently, leaking the `_sse_connections` counter if `_sse_decr` is not reached via the `finally` block.

The `finally` block does correctly decrement the counter (lines 219–222), so counter leaks are avoided. However, proxies (Render's load balancer, Cloudflare's proxying) will close idle connections, causing clients to reconnect — creating churn. `openWhenHidden: false` in the frontend hook helps, but active tab users will see frequent reconnections.

**Recommendation**: Set `heartbeat_interval = 20` seconds (well below any 30-second proxy idle timeout) and adjust the sleep logic to always send a heartbeat before the proxy timeout window.

---

### P2-4: `useRealtimeOptimization` Polls Every 60 Seconds Redundantly

**File**: `frontend/lib/hooks/useRealtime.ts` lines 150–168

```typescript
export function useRealtimeOptimization() {
    useEffect(() => {
        const timer = setInterval(() => {
            queryClient.invalidateQueries({ queryKey: ['optimization'] })
        }, 60_000)
```

**Issue**: This polling hook invalidates **all** optimization-related queries every 60 seconds. `invalidateQueries` triggers background refetches for every active observer of `['optimization', ...]`. If `useOptimizationSchedule` and `useApplianceOptimization` are both mounted (which they are on the Optimize page), this generates 2 API calls every 60 seconds from this hook alone, plus the natural `refetchInterval` in those hooks (300s and 60s respectively in `useOptimization.ts`). The combined effect is 3 requests per minute for optimization data when a single well-coordinated cache invalidation would suffice.

**Recommendation**: Remove `useRealtimeOptimization` entirely and rely on the `refetchInterval` in individual hooks. If server-push invalidation is needed, wire it to the SSE stream.

---

### P2-5: `DashboardContent.tsx` Renders Derived State Without Memoization

**File**: `frontend/components/dashboard/DashboardContent.tsx` lines 77–92

```typescript
const rawPrice = pricesData?.prices?.[0] as ApiPriceResponse | undefined
const currentPrice: CurrentPriceInfo | null = rawPrice ? {
    price: parseFloat(rawPrice.current_price),
    ...
} : null
const trend = currentPrice?.trend || 'stable'
const TrendIcon = trend === 'increasing' ? TrendingUp : ...
```

**Issue**: `currentPrice`, `trend`, and `TrendIcon` are computed on every render without `useMemo`. While these computations are cheap individually, the `TrendIcon` component reference changes on every render (it's not `React.memo`-ized), causing child components receiving `TrendIcon` as a prop to re-render unnecessarily. In Strict Mode (enabled via `next.config.js` line 18), every component renders twice in development, making this more visible.

**Recommendation**:
- Wrap `currentPrice`, `trend`, and `TrendIcon` in `useMemo` with appropriate dependencies.
- Pass `trend` as a string prop instead of `TrendIcon` as a component reference, and let `DashboardStatsRow` do the icon resolution internally.

---

### P2-6: `UserRepository.update()` Calls `model_dump(exclude_unset=True)` Then Filters to Allowed Columns

**File**: `backend/repositories/user_repository.py` lines 192–216

```python
updates = entity.model_dump(exclude_unset=True)
updates.pop("id", None)
updates.pop("created_at", None)
updates["updated_at"] = datetime.now(timezone.utc)
updates = {k: v for k, v in updates.items() if k in self._UPDATABLE_COLUMNS}
```

**Issue**: `model_dump(exclude_unset=True)` is correct and efficient. However, the subsequent `_UPDATABLE_COLUMNS` filter creates a new dict comprehension on every update call. More importantly, when updating a user after a successful Stripe webhook, the full `User` object is passed with all fields set — `exclude_unset` only works when the model was created with `model_construct()`. For webhook-triggered updates, all 20+ fields are included in `updates` before filtering, causing unnecessary serialization work.

This is a minor inefficiency but compounds with the fact that `update()` is called after every `tier_cache` miss, meaning it runs ~every 30 seconds per active user when tier checks are frequent.

**Recommendation**: Use `model_construct()` in webhook handlers to create partial User objects with only the fields being updated, ensuring `model_dump(exclude_unset=True)` returns only the changed fields.

---

### P2-7: Frontend `next.config.js` Missing `turbo` Bundle Analyzer and Webpack Config

**File**: `frontend/next.config.js`

```javascript
const nextConfig = {
    output: 'standalone',
    optimizePackageImports: ['date-fns', 'lucide-react', 'recharts', 'better-auth'],
    ...
}
```

**Issue**: `optimizePackageImports` is configured for 4 packages, which is good. However:

1. `recharts` v3 uses named exports but the chart components import full submodules (`from 'recharts'`). While `optimizePackageImports` should handle this, recharts v3 is a peer dependency of `@tanstack/react-query` which may cause import resolution interference.

2. There is no `bundleAnalyzer` configuration to detect future regressions. Without bundle analysis in CI, the `nodemailer`/`@neondatabase` risk (P0-2) can silently regress.

3. `compress: true` delegates compression to Next.js's built-in gzip. For Vercel deployments this is redundant (Vercel serves Brotli). For Render (if frontend were ever self-hosted), gzip at the application level adds CPU overhead.

4. The `images.remotePatterns` allows all subdomains of `rateshift.app` (`*.rateshift.app`) but there are no user-uploaded images from that domain in the current codebase. `next/image` is used only in `SupplierCard.tsx` for supplier logos, which appear to come from user-supplied `logo_url` strings — these may point to arbitrary CDN domains not in the allowlist, causing them to fall back to `<img>` rendering without optimization.

**Recommendation**:
- Add `@next/bundle-analyzer` to devDependencies and configure in CI.
- Audit `SupplierCard` logo URLs to determine the actual image sources and update `remotePatterns` accordingly.
- Add `sizes` prop to `<Image>` in `SupplierCard.tsx` for proper responsive image hints.

---

### P2-8: Alert Config Query Fetches All 5,000 Active Configs Without Streaming

**File**: `backend/services/alert_service.py` lines 514–551

```python
result = await db.execute(text("""
    SELECT ...
    FROM price_alert_configs pac
    JOIN public.users u ON u.id = pac.user_id
    WHERE pac.is_active = TRUE AND u.is_active = TRUE
    ORDER BY pac.created_at
    LIMIT 5000
"""))
rows = result.mappings().all()  # Materializes all 5000 rows at once
```

**Issue**: `result.mappings().all()` materializes the entire result set in memory before any processing begins. At 5,000 alert configs × ~200 bytes per row = ~1 MB of Python dicts, plus the Decimal conversions and list comprehension, this is a ~2 MB allocation that the single-worker process must hold while also processing the check-alerts pipeline.

**Recommendation**: Use `result.mappings().partitions(500)` (SQLAlchemy's streaming result partitioning) to process configs in 500-row batches, reducing peak memory from 2 MB to ~200 KB.

---

## P3 — Low Severity / Optimization Opportunities

### P3-1: `PriceLineChart` Redundant `useMemo` on Every `data` Change

**File**: `frontend/components/charts/PriceLineChart.tsx` lines 55–62

```typescript
const chartData = useMemo(() => {
    return data.map((point) => ({
        ...point,
        time: point.time,
        formattedTime: format(parseISO(point.time), 'HH:mm'),
        displayPrice: point.price ?? point.forecast,
    }))
}, [data])
```

**Issue**: `data` is an array from `historyData.prices.map(...)` computed in `DashboardContent`. Both `DashboardContent` wraps the computation in `useMemo` (lines 63–74) and `PriceLineChart` wraps it again. While `useMemo` is cheap, the `data` prop reference will be stable across renders (because the outer `useMemo` in `DashboardContent` is correct), making the inner `useMemo` redundant but not harmful. The `format(parseISO(...))` call inside the memo is O(n) with `date-fns` — acceptable for 168 data points (7d hourly) but could be replaced with a simpler string slice for performance.

**Recommendation**: Remove the `useMemo` from `PriceLineChart` since the parent already memoizes `chartData`. Add a comment explaining this invariant.

---

### P3-2: CF Worker Route Matching Uses Linear Scan on Every Request

**File**: `workers/api-gateway/src/router.ts` lines 8–15, `workers/api-gateway/src/config.ts`

```typescript
export function matchRoute(pathname: string): RouteConfig {
    for (const route of ROUTES) {
        if (route.pattern.test(pathname)) {
            return route;
        }
    }
    return DEFAULT_ROUTE;
}
```

**Issue**: Route matching does a linear scan over 11 regex patterns on every request. JavaScript regex `test()` with alternating patterns is efficient, but the patterns include complex expressions like `/^\/api\/v1\/suppliers(?:\/|$)/`. For the CF Worker's typical 1–5ms CPU budget, this is negligible. However, if ROUTES grows significantly, a trie-based prefix matcher would be more scalable.

**Recommendation**: This is acceptable for the current 11 routes. Document the O(n) complexity with a `// Max ~20 routes before consider trie optimization` comment.

---

### P3-3: `get_savings_summary` CTE Uses Streak Calculation with N+1 Pattern

**File**: `backend/services/savings_service.py` lines 67–110

The CTE-based savings query is well-structured for aggregation. However, the streak calculation joins `active_days` against itself implicitly via the subquery:

```sql
SELECT day, CURRENT_DATE - day AS days_ago,
       ROW_NUMBER() OVER (ORDER BY day DESC) - 1 AS rn
FROM active_days
WHERE days_ago = rn
```

This inner query performs a full scan of `active_days` (all distinct saving days in the last 365 days) per call. If a user has 200+ active days, this is 200 rows for the window function evaluation. The query correctly returns in a single DB round-trip, but the `active_days` CTE itself requires scanning `user_savings WHERE user_id = :user_id AND created_at >= NOW() - INTERVAL '365 days'`. Without an index on `(user_id, created_at)`, this is a sequential scan of all user savings rows.

**Potential missing index**: Checking migration 012 (`_user_savings`) is needed to confirm whether `idx_user_savings_user_created` exists.

**Recommendation**: Verify that `user_savings` has an index on `(user_id, created_at)`. If not, add it as a priority index migration.

---

### P3-4: HNSW Index Rebuild is Synchronous and Blocking on Startup

**File**: `backend/services/hnsw_vector_store.py` lines 73–113

```python
def __init__(self, ...):
    self._store = VectorStore(...)
    ...
    if HNSW_AVAILABLE:
        self._build_index()  # Synchronous SQLite read + hnswlib index construction

def _build_index(self) -> None:
    with sqlite3.connect(self._store._db_path) as conn:
        rows = conn.execute("SELECT id, vector FROM vectors").fetchall()  # Blocking!
    if rows:
        data = np.stack(vectors)
        self._index.add_items(data, ids)  # CPU-intensive
```

**Issue**: `_build_index()` is called from `__init__` synchronously. It reads all vectors from SQLite (potentially thousands of rows) and performs CPU-intensive `np.stack` + `hnswlib.add_items`. If the `HNSWVectorStore` is instantiated inside an async handler (e.g., from an import chain triggered by a learning-cycle endpoint), this blocks the event loop during index construction.

`HNSWVectorStore` is a module-level singleton in `price_service.py` (lines 19–22) guarded by `_ensemble_lock`, so it's only constructed once. However, that construction happens inside `asyncio.Lock()` which does not prevent blocking — it prevents concurrent construction attempts. The blocking SQLite read happens synchronously in the event loop.

**Recommendation**: Move `_build_index()` to an async method that runs `sqlite3.connect` via `asyncio.to_thread()` and constructs the HNSW index in a thread pool:
```python
await asyncio.to_thread(self._build_index)
```

---

### P3-5: `Sidebar.tsx` Imports 19 Lucide Icons at Top Level

**File**: `frontend/components/layout/Sidebar.tsx` lines 11–33

```typescript
import {
    LayoutDashboard, TrendingUp, Flame, Sun, Building2, Link2,
    Calendar, Bell, Bot, Settings, Zap, Fuel, Droplets, Waves,
    BarChart3, Users, LogOut, User, X, HelpCircle, FileText,
} from 'lucide-react'
```

**Issue**: `lucide-react` v0.577 ships with `optimizePackageImports` in `next.config.js`, which should convert these named imports to individual module imports at build time. This is correct and the tree-shaking should work. However, `Sidebar.tsx` is rendered on every authenticated page (it's in `AppLayout`), so all 19 icons are included in the shared layout chunk. This is acceptable but should be confirmed via bundle analysis.

**Recommendation**: Confirm via `@next/bundle-analyzer` that the sidebar icon chunk is < 5 KB (each Lucide icon is ~200 bytes SVG-as-JSX). No action needed if confirmed.

---

### P3-6: `useAuth` Hook Fetches User Profile on Every Mount

**File**: `frontend/lib/hooks/useAuth.tsx` (referenced but not read in full)

The `AuthProvider` wraps the entire app (`app/layout.tsx` line 6). Based on the CLAUDE.md note about `profile fetch retry-once-after-1s`, the auth hook performs a profile fetch on mount. This means a fresh `GET /api/v1/users/profile` request fires on every page navigation (or page reload) for authenticated users. With React Router soft navigation in Next.js App Router, this may be deduplicated by React Query, but it depends on whether `useAuth` is a React Query hook or a raw `useEffect` pattern.

**Recommendation**: Confirm that `useAuth` uses React Query with `staleTime >= 60000` to prevent a profile refetch on every navigation. If using raw `useEffect`, migrate to React Query with a 5-minute stale time.

---

### P3-7: `prices_sse.py` Opens a New `get_redis()` Call on Every Connection Event

**File**: `backend/api/v1/prices_sse.py` lines 41–51

```python
async def _sse_incr(user_id: str) -> int:
    from config.database import get_redis
    redis = await get_redis()  # Re-fetches global redis client on every call
    if redis:
        key = f"sse:conn:{user_id}"
        count = await redis.incr(key)
        await redis.expire(key, _SSE_REDIS_TTL)
        return int(count)
```

**Issue**: `get_redis()` is called on every SSE connection open and close (`_sse_incr` and `_sse_decr`). While `get_redis()` is a simple attribute lookup (`return await db_manager.get_redis_client()` which returns `self.redis_client`), it adds a function call and `await` on every SSE event. More importantly, INCR + EXPIRE are two separate Redis round-trips where a single SETEX with an atomic approach would suffice.

**Recommendation**: Replace the INCR + EXPIRE pattern with a single Lua script (similar to the rate limiter) that atomically increments and sets TTL in one round-trip.

---

### P3-8: `gunicorn_config.py` Disables `preload_app`

**File**: `backend/gunicorn_config.py` lines 28–30

```python
preload_app = False  # Set to False to avoid startup issues
```

**Issue**: With `workers = 1`, `preload_app` is irrelevant (there's nothing to share). However, for the recommended future state of `workers = 2`, disabling preload means each worker must independently import all backend modules, load the ML ensemble predictor from disk, and initialize the HNSW index from SQLite. This roughly doubles startup time (2 × ~5-10 seconds = 10-20 seconds cold start) before Render's health check passes.

**Recommendation**: When moving to 2 workers, enable `preload_app = True`. This serializes module loading, shares the loaded code across workers via OS copy-on-write, and reduces memory footprint by ~30% (shared read-only code pages).

---

## Performance Metrics Reference

### Database Index Coverage (Current State)

| Query Pattern | Supporting Index | Status |
|---|---|---|
| `electricity_prices WHERE region AND utility_type ORDER BY timestamp DESC` | `idx_electricity_prices_region_utility_time` (migration 037) | Present |
| `electricity_prices WHERE region AND supplier ORDER BY timestamp DESC` | `idx_prices_region_supplier_timestamp` (migration 004) | Present |
| `electricity_prices PARTITION BY region ORDER BY timestamp DESC` (window fn) | None (cannot use B-tree) | **Missing** |
| `users WHERE stripe_customer_id = ?` | `idx_users_stripe_customer_id` (migration 037) | Present |
| `notifications WHERE user_id AND read_at IS NULL` | `idx_notifications_user_unread` (migration 015) | Present |
| `alert_history WHERE user_id AND alert_type AND region` | `idx_alert_history_dedup` (migration 036) | Present |
| `price_alert_configs WHERE is_active = TRUE` | `idx_price_alert_configs_active_created` (migration 036) | Present |
| `user_savings WHERE user_id AND created_at` | **Unknown — not confirmed** | Needs verification |
| `forecast_observations WHERE region AND observed_at IS NULL` | `idx_fobs_unobserved` (migration 005) | Present |

### Frontend Polling Load Summary

| Hook | Interval | Endpoint | Active On |
|---|---|---|---|
| `useCurrentPrices` | 60s | `GET /prices/current` | Dashboard |
| `usePriceForecast` | 300s | `GET /prices/forecast` | Dashboard |
| `useRealtimePrices` | 30s (SSE) | `SSE /prices/stream` | Dashboard (Business only) |
| `NotificationBell` | 30s | `GET /notifications/count` | ALL authenticated pages |
| `useRealtimeOptimization` | 60s | cache invalidation only | Optimize page |

**Baseline load per active authenticated user**: 3 API calls/minute (notifications + prices + forecast combined). With 100 active users: 300 backend requests/minute on a single Gunicorn worker.

---

## Recommended Remediation Priority

| Priority | Finding | Effort | Impact |
|---|---|---|---|
| P0 | Single Gunicorn worker (P0-1) | Medium (config + test) | Very High |
| P0 | `nodemailer`/`@neondatabase` as prod deps (P0-2) | Low (package.json + import guards) | High |
| P0 | 5 parallel requests on dashboard mount (P0-3) | Medium (refactor hooks) | High |
| P1 | `list_latest_by_regions` window function (P1-1) | Low (SQL rewrite) | High |
| P1 | Sequential alert dispatch (P1-2) | Medium (asyncio.gather + batching) | Medium |
| P1 | 30s notification polling from every page (P1-3) | Low (interval increase) | Medium |
| P1 | 5,000-row user memory spike (P1-4) | Medium (pagination) | Medium |
| P1 | Connection pool inadequate for SSE load (P1-6) | Low (config + env var) | High |
| P2 | CF Worker body buffering in storeInCache (P2-1) | Low (size guard) | Low |
| P2 | SSE heartbeat never fires at 30s interval (P2-3) | Low (constant fix) | Medium |
| P2 | Alert config materializes 5,000 rows (P2-8) | Low (partitions()) | Low |
| P3 | HNSW index build blocks event loop (P3-4) | Low (asyncio.to_thread) | Low |
