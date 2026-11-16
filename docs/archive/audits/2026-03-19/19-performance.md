# Performance Audit Report

> Generated: 2026-03-19
> Auditor: Claude Opus 4.6 (automated)
> Scope: Backend services, Frontend components, ML inference, CF Worker edge layer

---

## Executive Summary

The RateShift codebase demonstrates strong architectural fundamentals: singleton ML model loading, two-tier edge caching, batch SQL inserts, and proper use of `asyncio.to_thread` for blocking ML inference. However, 19 performance risks were identified across the four layers. The most critical issues are an unbounded SQL query in the forecast service, a full-table vector load into memory, synchronous network I/O in the ensemble predictor constructor, and serial alert dispatch under load.

**Finding counts by severity:**

| Severity | Count | Description |
|----------|-------|-------------|
| P0       | 0     | No imminent outage risks identified |
| P1       | 4     | High-impact issues requiring near-term fixes |
| P2       | 8     | Medium-impact issues to address in next sprint |
| P3       | 7     | Low-impact improvements for backlog |

---

## P0 -- Critical (causes outages or data loss)

_No P0 findings._

---

## P1 -- High (measurable latency or resource waste under normal load)

### P1-1: Unbounded query in `_forecast_from_table` (forecast_service.py)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/forecast_service.py`
**Lines:** 195-203
**Category:** Missing pagination / unbounded result set

The `_forecast_from_table` method queries gas, water, propane, and heating oil tables without a `LIMIT` clause. In contrast, `_forecast_electricity` (line 142) correctly applies `LIMIT 400`. As these commodity tables grow, this query will return increasingly large result sets materialized entirely in Python memory.

**Impact:** For a table with 100K+ rows per region, this query could return thousands of rows to the application layer, causing memory spikes and slow responses on the `/forecast` endpoint. The linear trend extrapolation only needs recent data points.

**Recommendation:** Add `LIMIT 400` (or a configurable bound) to the SQL in `_forecast_from_table`, matching the pattern already used by `_forecast_electricity`. Filter to only the most recent N days of data.

---

### P1-2: Full vector table loaded into memory on startup (hnsw_vector_store.py)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/hnsw_vector_store.py`
**Lines:** 75-114
**Category:** Memory accumulation / unbounded startup load

The `_build_index` method calls `cursor.execute("SELECT id, vector FROM vectors").fetchall()`, loading every stored vector into Python memory before inserting them into the HNSW index. While `_max_elements_cap = 100_000` is defined (line 60), it is only used to pre-allocate the hnswlib index and is not enforced as a hard limit on the number of rows fetched from SQLite.

**Impact:** At 384 dimensions with float32, each vector is ~1.5 KB. At 100K vectors, this is ~150 MB loaded into memory at startup, plus the hnswlib index overhead. If the SQLite table grows beyond the cap, the fetchall() will still load all rows, causing OOM risk on constrained Render instances.

**Recommendation:**
1. Add `LIMIT {self._max_elements_cap}` and `ORDER BY rowid DESC` to the SQL to cap the fetch.
2. Consider streaming rows with `fetchmany(batch_size)` instead of `fetchall()`.
3. Add a startup log warning if the row count exceeds the cap.

---

### P1-3: Synchronous Redis + PostgreSQL connections in EnsemblePredictor constructor

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/ml/inference/ensemble_predictor.py`
**Lines:** 99-170
**Category:** Blocking I/O in potentially async context

The `_load_weights` method (called from `__init__`) synchronously connects to Redis (line 178, `redis.from_url`) and PostgreSQL (line 145, `psycopg2.connect`). While the constructor docstring notes it "may run outside an async context" (line 129), and `price_service.py` does wrap it in `asyncio.to_thread` (line 196), any future caller that instantiates `EnsemblePredictor` from an async context without `to_thread` will block the event loop.

Additionally, the psycopg2 connection (line 145) has no connect timeout, meaning a DNS resolution hang or unreachable database could block the constructor indefinitely. The Redis connection similarly lacks a `socket_connect_timeout`.

**Impact:** If Redis or PostgreSQL are slow or unreachable, Gunicorn worker startup stalls. The default psycopg2 connect timeout is OS-level (often 60-120 seconds).

**Recommendation:**
1. Add `connect_timeout=5` to the `psycopg2.connect()` call.
2. Add `socket_connect_timeout=3` to `redis.from_url()`.
3. Document that `EnsemblePredictor()` must only be called from a sync context or via `asyncio.to_thread`.

---

### P1-4: Serial alert dispatch loop under load (alert_service.py)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/alert_service.py`
**Lines:** 237-344
**Category:** Serial I/O in loop / missing concurrency

The `send_alerts` method iterates over triggered alerts sequentially. For each alert, it calls `dispatcher.send()` which performs a DB insert (IN_APP notification) followed by concurrent PUSH + EMAIL delivery. However, the outer loop itself is serial -- each alert must fully complete before the next begins.

During a price spike event that triggers alerts for many users (e.g., 500+ active alert configs), this sequential processing becomes the bottleneck on the `/internal/check-alerts` endpoint. The 30-second `RequestTimeoutMiddleware` is excluded for internal endpoints, but the CF Worker cron trigger has a 35-second retry window.

**Impact:** With 500 alerts, each taking ~200ms (DB insert + HTTP calls), the endpoint takes ~100 seconds, risking CF Worker timeout and duplicate cron firings.

**Recommendation:**
1. Use `asyncio.gather` with a semaphore (e.g., `Semaphore(10)`) to dispatch alerts concurrently in batches.
2. Note: Each alert dispatch uses its own DB operations, so shared-session corruption (the `asyncio.gather` anti-pattern documented in CLAUDE.md) does not apply here if each dispatch creates its own session or uses separate transactions.

---

## P2 -- Medium (potential issue under peak traffic or growth)

### P2-1: Sequential connection sync for all due connections (connection_sync_service.py)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/connection_sync_service.py`
**Lines:** 259-315
**Category:** Serial external API calls

`sync_all_due` iterates over all connections due for sync in a sequential `for` loop. Each iteration makes an external API call to UtilityAPI (or similar). With 100+ active connections, this serialization significantly extends the sync window.

**Recommendation:** Use `asyncio.gather` with `Semaphore(5)` to parallelize syncs. Each sync operates on independent connection records and can use separate DB sessions.

---

### P2-2: JSONB text query without GIN index for notification dedup (notification_dispatcher.py)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/notification_dispatcher.py`
**Lines:** 472-479
**Category:** Missing database index

The `_is_duplicate` method queries `WHERE metadata ->> 'dedup_key' = :key`, which performs a sequential scan on the JSONB `metadata` column. This runs on every alert dispatch to prevent duplicate notifications.

**Impact:** As the notifications table grows, this query degrades from O(1) index lookup to O(n) sequential scan. With the alert service potentially dispatching hundreds of notifications per cron cycle, this becomes a compounding bottleneck.

**Recommendation:** Add a GIN index on `metadata` or a functional B-tree index on `(metadata ->> 'dedup_key')`. Migration 053 added a notification dedup index, but verify it covers this specific query pattern.

---

### P2-3: 5000-row default limit on historical prices (price_repository.py)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/price_repository.py`
**Lines:** ~499
**Category:** Large data transfer to application layer

`get_historical_prices` defaults to `limit=5000`, materializing up to 5000 Price objects in Python memory per call. While the paginated variant exists (`get_historical_prices_paginated`), the non-paginated version is still used by `_build_features` in `price_service.py` (line 254) and potentially other callers.

**Impact:** Each Price object with its Decimal fields and datetime attributes consumes ~500 bytes. 5000 rows = ~2.5 MB per request, which is significant for a Render free-tier instance with limited memory.

**Recommendation:**
1. Reduce the default limit to 1000 or less.
2. Audit all callers of `get_historical_prices` -- `_build_features` only needs 168 hours (~168 rows), not 5000.
3. Consider adding an explicit `limit` parameter to `_build_features` to fetch only what the ML model needs.

---

### P2-4: Bot detection regex compiled per-request in CF Worker (security.ts)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/src/middleware/security.ts`
**Lines:** 16-22
**Category:** Regex compilation in hot path

The `botPatterns` regex with alternation (line 16) and two additional regex patterns (lines 21-22) are evaluated on every incoming request. In V8 isolates, regex literals are re-compiled when the function is invoked if they are not hoisted to module scope.

**Impact:** Regex compilation is microsecond-level, but at high request rates (thousands/sec), this adds unnecessary CPU time per isolate. The alternation pattern (`bot|crawl|spider|...`) with many alternatives is particularly expensive to compile.

**Recommendation:** Hoist regex patterns to module-level `const` declarations outside the function body. V8 will compile them once per isolate lifecycle rather than per function call.

```typescript
// Module level (compiled once per isolate)
const BOT_UA_PATTERN = /bot|crawl|spider|slurp|lighthouse/i;
```

---

### P2-5: Service instantiation on every cron invocation (internal/alerts.py)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/alerts.py`
**Lines:** 52-57
**Category:** Redundant object construction

The `check_alerts` endpoint creates new `PushNotificationService` and `EmailService` instances on every invocation. These services likely initialize HTTP clients, load templates, or establish connections in their constructors.

**Impact:** For the cron-triggered endpoint (every 3 hours), this is negligible. However, if the endpoint is called more frequently during incident response or testing, the repeated initialization adds latency.

**Recommendation:** Use FastAPI's dependency injection system (`Depends`) to manage service lifecycle, or use module-level singletons for stateless services.

---

### P2-6: Sequential region processing in nightly learning cycle (learning_service.py)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/learning_service.py`
**Lines:** 380-451
**Category:** Serial computation across independent regions

`run_full_cycle` processes each region sequentially. Each region involves fetching observations, computing metrics, and updating weights. Since regions are independent, this is a parallelization opportunity.

**Impact:** With 23 DEFAULT_REGIONS and ~2-5 seconds per region (DB queries + computation), the nightly learning cycle takes 45-115 seconds. Parallelizing could reduce this to ~10-20 seconds.

**Recommendation:** Use `asyncio.gather` with `Semaphore(5)` to process regions concurrently. Each region uses independent data, but ensure DB session management is per-task (not shared).

---

### P2-7: Cache invalidation iterates KV keys with list + delete (cache.ts)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/src/middleware/cache.ts`
**Lines:** 148-173
**Category:** Expensive KV operations

`invalidatePriceCache` calls `KV.list()` to enumerate all cached keys matching a prefix, then deletes each one individually. KV list operations have a latency of ~50ms and return up to 1000 keys per call. Individual deletes are ~10ms each.

**Impact:** If hundreds of price cache entries exist, a single invalidation call could take seconds and consume significant KV operation quota. This runs on price sync (every 6 hours), so frequency is low, but the operation cost scales with cache size.

**Recommendation:**
1. Use a cache generation counter (a single KV key) instead of deleting individual entries. Increment the counter on invalidation; cache reads check the counter.
2. Alternatively, rely on TTL-based expiry rather than explicit invalidation, since price data has natural staleness windows.

---

### P2-8: Response body buffered as text for KV storage (cache.ts)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/src/middleware/cache.ts`
**Lines:** ~84
**Category:** Memory pressure from body cloning

`storeInCache` clones the response body as text (`await response.text()`) before storing it in KV. For large API responses (e.g., historical prices with 5000 rows), this doubles memory usage within the Worker isolate -- once for the response stream and once for the text string.

**Impact:** CF Workers have a 128 MB memory limit per isolate. Large responses (>1 MB) could cause isolate eviction under concurrent request load.

**Recommendation:**
1. Stream the response body to KV using `ReadableStream` instead of buffering as text.
2. Add a response size check before caching -- skip KV storage for responses exceeding a threshold (e.g., 512 KB).

---

## P3 -- Low (negligible now, could compound over time)

### P3-1: Linear route matching in CF Worker router (router.ts)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/src/router.ts`
**Lines:** 8-15
**Category:** O(n) route resolution

`matchRoute` performs a linear scan of the ROUTES array (12 entries in `config.ts`), testing each regex pattern against the request path. With only 12 routes, this is sub-microsecond.

**Impact:** Negligible at current scale. Would only matter if routes grew to 100+.

**No action required** at current scale. Note for future: consider a trie-based router if routes exceed 50.

---

### P3-2: Missing React.memo on DashboardTabs component

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/DashboardTabs.tsx`
**Lines:** Default export (end of file)
**Category:** Unnecessary re-renders

`DashboardTabs` is not wrapped in `React.memo`. While it uses `useMemo` and `useCallback` internally (lines 35, 49), the component itself will re-render whenever its parent (`DashboardContent`) re-renders, even if props are unchanged.

**Impact:** Minor -- the tab bar is a lightweight component. Re-renders cost <1ms.

**Recommendation:** Wrap in `React.memo` for consistency with the codebase pattern. Low priority.

---

### P3-3: Missing React.memo on PricesContent component

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/prices/PricesContent.tsx`
**Lines:** Default export (end of file)
**Category:** Unnecessary re-renders

`PricesContent` is not wrapped in `React.memo`. It is the main content component for the prices page and fires 4 React Query hooks on mount (`useCurrentPrices`, `usePriceHistory`, `usePriceForecast`, `useOptimalPeriods` -- lines 84-94). Each hook's state change triggers a re-render of the entire component tree.

**Impact:** The dynamic imports for charts (`PriceLineChart`, `ForecastChart` with `ssr: false`) mitigate some cost, and `useMemo` guards the derived data. The re-render cost is moderate but bounded by React Query's internal deduplication.

**Recommendation:** Consider extracting chart sections into memoized sub-components to isolate re-renders when individual queries update.

---

### P3-4: Four concurrent API calls on Prices page mount

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/prices/PricesContent.tsx`
**Lines:** 84-94
**Category:** Waterfall vs. parallel API calls

Four React Query hooks fire simultaneously on page mount: current prices, price history (7 days), forecast (24h), and optimal periods. While parallelism is generally good, this creates a burst of 4 concurrent requests per user page load.

**Impact:** At current user scale, this is fine. At 1000+ concurrent users, the backend receives 4000+ simultaneous requests. React Query's `staleTime` (55s for prices, 180s for forecast) provides good caching.

**No action required.** The React Query caching strategy is appropriate. Consider adding `placeholderData` for a smoother loading experience.

---

### P3-5: Calibration runs individual forward passes (predictor.py)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/ml/inference/predictor.py`
**Lines:** 318-345
**Category:** Missing batching in ML calibration

The `calibrate()` method iterates over calibration samples one at a time, running individual forward passes. For tree-based models (XGBoost, LightGBM), batching provides significant speedup due to vectorized operations.

**Impact:** Calibration runs at model load time (once), not per-request. The cost is paid only during nightly learning or model reload. With ~100 calibration samples, total time is <1 second.

**Recommendation:** Batch calibration samples into a single prediction call where the model supports it. Low priority since this is not in the hot path.

---

### P3-6: crypto.randomUUID() on every Worker request

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/src/index.ts`
**Lines:** ~19
**Category:** Minor CPU overhead

`crypto.randomUUID()` is called on every request for request tracing. While this is a fast operation (~1 microsecond), it is unnecessary for cached responses that never reach the origin.

**Impact:** Negligible. The UUID generation is orders of magnitude cheaper than any network I/O.

**No action required.** The tracing value outweighs the cost.

---

### P3-7: Hardcoded LIMIT 50 on unread notifications (notification_service.py)

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/notification_service.py`
**Lines:** 44
**Category:** Missing configurability

The `get_unread` method hardcodes `LIMIT 50`. While this prevents unbounded queries, it means users with 50+ unread notifications silently lose visibility of older ones with no pagination support.

**Impact:** Functional correctness issue more than performance. The query itself is efficient with proper indexing on `(user_id, read_at)`.

**Recommendation:** Add pagination support (page/page_size parameters) matching the pattern used in `SavingsService.get_savings_history`. Low priority.

---

## Positive Findings (What the Codebase Does Well)

These patterns demonstrate strong performance awareness and should be preserved:

1. **Singleton ML model loading** (`price_service.py` lines 19-22): Module-level `_ensemble_predictor` with `asyncio.Lock` ensures the model is loaded exactly once across all Gunicorn workers. The `asyncio.to_thread` wrapper (line 196) correctly offloads blocking inference to a thread pool.

2. **Two-tier edge caching** (`cache.ts`): Cache API (per-colo, sub-ms) checked before KV (global, ~50ms). Stale-while-revalidate pattern via `ctx.waitUntil` for background refresh. Cache-before-ratelimit ordering in the middleware chain (`index.ts` line 89) means cache hits skip rate limiting entirely.

3. **Batch SQL inserts** (`price_repository.py` lines 632-694): `bulk_create` uses 500-row parameterized INSERT chunks, avoiding N individual INSERT round-trips.

4. **Cache stampede prevention** (`price_repository.py` lines 85-102): Lock-based mechanism prevents multiple concurrent requests from triggering the same expensive query.

5. **SQL-pushed window aggregation** (`price_service.py` lines 396-420): `get_optimal_usage_windows` uses SQL `AVG() OVER (ROWS BETWEEN)` to push the sliding-window computation to PostgreSQL rather than computing in Python.

6. **Native CF rate limiting** (`rate-limiter.ts`): Uses Cloudflare's native rate limiting bindings instead of KV-based counters, eliminating KV read/write costs for rate limit checks.

7. **Dynamic imports for heavy charts** (`PricesContent.tsx` lines 11-20): Recharts components loaded with `dynamic(() => import(...), { ssr: false })`, reducing initial bundle size and preventing SSR hydration issues.

8. **React Query cache configuration** (`usePrices.ts`): Appropriate `staleTime` and `refetchInterval` values prevent unnecessary refetches while keeping data fresh. The `enabled: !!region` guard prevents queries from firing without required parameters.

9. **Single CTE for savings summary** (`savings_service.py` lines 66-102): Aggregations, streak calculation, and currency lookup all in one round-trip to PostgreSQL via CTE.

10. **Atomic rate limiting with Lua** (`rate_limiter.py` lines 38-61): Sliding window rate limiting implemented as an atomic Redis Lua script, preventing race conditions between check and increment.

---

## Summary Table

| ID    | Severity | Layer    | File                         | Issue                                    |
|-------|----------|----------|------------------------------|------------------------------------------|
| P1-1  | P1       | Backend  | forecast_service.py:195      | Unbounded query (no LIMIT)               |
| P1-2  | P1       | Backend  | hnsw_vector_store.py:75      | Full vector table loaded via fetchall()  |
| P1-3  | P1       | ML       | ensemble_predictor.py:99     | Sync Redis+DB in constructor (no timeout)|
| P1-4  | P1       | Backend  | alert_service.py:237         | Serial alert dispatch loop               |
| P2-1  | P2       | Backend  | connection_sync_service.py:259| Sequential connection sync              |
| P2-2  | P2       | Backend  | notification_dispatcher.py:472| JSONB query without GIN index           |
| P2-3  | P2       | Backend  | price_repository.py:499      | 5000-row default limit                   |
| P2-4  | P2       | Worker   | security.ts:16               | Regex compiled per-request               |
| P2-5  | P2       | Backend  | internal/alerts.py:52        | Service instantiation per cron call      |
| P2-6  | P2       | Backend  | learning_service.py:380      | Sequential region processing             |
| P2-7  | P2       | Worker   | cache.ts:148                 | KV list+delete for cache invalidation    |
| P2-8  | P2       | Worker   | cache.ts:84                  | Response body buffered as text for KV    |
| P3-1  | P3       | Worker   | router.ts:8                  | Linear route matching (12 routes)        |
| P3-2  | P3       | Frontend | DashboardTabs.tsx            | Missing React.memo                       |
| P3-3  | P3       | Frontend | PricesContent.tsx            | Missing React.memo                       |
| P3-4  | P3       | Frontend | PricesContent.tsx:84         | 4 concurrent API calls on mount          |
| P3-5  | P3       | ML       | predictor.py:318             | Individual forward passes in calibration |
| P3-6  | P3       | Worker   | index.ts:19                  | crypto.randomUUID() on every request     |
| P3-7  | P3       | Backend  | notification_service.py:44   | Hardcoded LIMIT 50, no pagination        |

---

## Recommended Fix Order

1. **P1-1** (forecast_service.py LIMIT) -- 5-minute fix, prevents unbounded memory on growing tables
2. **P1-3** (ensemble_predictor.py timeouts) -- 5-minute fix, prevents startup hangs
3. **P1-2** (hnsw_vector_store.py fetchall) -- 15-minute fix, caps memory at startup
4. **P1-4** (alert_service.py serial dispatch) -- 30-minute refactor, critical for scale
5. **P2-2** (notification_dispatcher.py GIN index) -- 10-minute migration, check existing index coverage
6. **P2-4** (security.ts regex hoisting) -- 5-minute fix, free CPU savings
7. **P2-3** (price_repository.py default limit) -- 10-minute fix with caller audit
8. **P2-1, P2-6** (sequential loops) -- 30-minute each, parallelize with semaphore pattern
