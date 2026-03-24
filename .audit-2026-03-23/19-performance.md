# Audit Report: Performance Risks
**Date:** 2026-03-23
**Scope:** Backend, frontend, ML, and edge layer performance analysis
**Files Reviewed:**
- `backend/services/price_service.py`
- `backend/services/savings_service.py`
- `backend/services/alert_service.py`
- `backend/services/recommendation_service.py`
- `backend/services/notification_dispatcher.py`
- `backend/services/notification_service.py`
- `backend/services/hnsw_vector_store.py`
- `backend/services/learning_service.py`
- `backend/services/community_service.py`
- `backend/services/community_solar_service.py`
- `backend/services/neighborhood_service.py`
- `backend/services/savings_aggregator.py`
- `backend/services/forecast_service.py`
- `backend/services/email_scanner_service.py`
- `backend/services/portal_scraper_service.py`
- `backend/services/agent_service.py`
- `backend/services/connection_sync_service.py`
- `backend/repositories/base.py`
- `backend/api/v1/prices.py`
- `backend/api/v1/internal/alerts.py`
- `backend/api/v1/internal/data_pipeline.py`
- `backend/api/v1/connections/direct_sync.py`
- `backend/api/dependencies.py`
- `backend/config/database.py`
- `backend/config/settings.py`
- `backend/app_factory.py`
- `backend/middleware/rate_limiter.py`
- `backend/gunicorn_config.py`
- `backend/integrations/pricing_apis/cache.py`
- `ml/inference/ensemble_predictor.py`
- `workers/api-gateway/src/config.ts`
- `workers/api-gateway/src/router.ts`
- `workers/api-gateway/src/handlers/proxy.ts`
- `workers/api-gateway/src/middleware/rate-limiter.ts`
- `workers/api-gateway/src/middleware/observability.ts`
- `frontend/lib/api/client.ts`
- `frontend/app/(app)/layout.tsx`
- `frontend/package.json`
- `tests/performance/test_api_latency.py`

---

## P0 — Critical (Fix Immediately)

### P0-1: EnsemblePredictor Performs Synchronous Blocking I/O on First Weight Access from an Async Context

**File:** `ml/inference/ensemble_predictor.py`, lines 121–222
**File:** `backend/services/price_service.py`, line 196

The `EnsemblePredictor.weights` property lazily calls `_load_weights()` on first access (line 113–115). `_load_weights()` calls `_load_weights_from_redis()` (line 131–136) and `_load_weights_from_db()` (line 140–152), both of which use synchronous blocking clients: `redis.from_url()` and `psycopg2.connect()` respectively. Although `price_service.py` wraps the top-level `_try_ml_forecast` call in `asyncio.to_thread()` (line 206), the lazy load is triggered inside `predict()` at line 310 (`current_weights = self.weights`), which is already running in that thread. If the predictor is loaded in an async context without the thread wrapper (e.g., at module import or during a background task), this blocks the event loop entirely until the psycopg2 TCP connection to Neon completes — typically 100–500ms on cold start. Even within the thread, a new synchronous psycopg2 connection is created per `_load_weights_from_db()` call rather than reusing the async engine's pool, consuming an extra connection slot.

**Impact:** Event loop blockage during cold prediction, wasted DB connections, potential cascading request timeouts.

**Fix:** Replace `_load_weights_from_db()` with a cached result stored at construction time (pass weights explicitly via `weights=` arg when constructing inside an async context) or eagerly pre-load in `asyncio.to_thread` before any request serves this predictor.

---

### P0-2: `_sanitize_log_record` Recompiles Regex Patterns on Every Log Event

**File:** `backend/app_factory.py`, lines 63–68

The two `re.compile()` calls inside `_SENSITIVE_PATTERNS` at lines 63–68 are defined inside the `_sanitize_log_record` function body. This function is called as a structlog processor on **every log event** in production. While CPython caches recently compiled regex patterns in an internal 512-entry LRU, the function still constructs and assigns a fresh list on each invocation (`_SENSITIVE_PATTERNS = [re.compile(...), re.compile(...)]`), defeating the benefit of the module-level re cache for the list object itself. Under moderate production load (1,000 req/s producing ~5 log events each = 5,000 calls/s), this creates significant garbage-collection pressure from the list allocation per call.

**Impact:** Non-trivial CPU and GC overhead at high log volume in production. Python's GC pauses become measurable.

**Fix:** Move `_SENSITIVE_PATTERNS` to module level (outside the function) so the list and both compiled patterns are created exactly once at import time.

---

## P1 — High (Fix This Sprint)

### P1-1: `get_active_alert_configs` Has a Hard LIMIT 5000 With No Pagination

**File:** `backend/services/alert_service.py`, lines 515–556

The `get_active_alert_configs()` query at line 535 fetches up to 5,000 alert config rows in a single query with no cursor-based pagination. As the user base grows, this single query will transfer an increasingly large result set across the Neon connection. At 5,000 rows each containing 8 text/numeric columns, the payload is ~500KB–1MB. The full result set is then materialized into a Python list of dicts before threshold checking. No streaming or chunked processing is applied.

**Impact:** Single-query memory spike on the `check-alerts` cron run; latency grows linearly with user count; potential OOM on a 512MB Render free-tier instance once the user base is large.

**Fix:** Implement cursor-based pagination using `WHERE pac.created_at > :cursor ORDER BY pac.created_at LIMIT 500` and process batches sequentially in `check_alerts`.

---

### P1-2: `NotificationDispatcher._is_duplicate` Performs a JSONB `->>'dedup_key'` Scan Without a Functional Index

**File:** `backend/services/notification_dispatcher.py`, lines 486–503

The dedup check at line 486 queries `metadata->>'dedup_key' = :dedup_key` over the `notifications` table. Unless a functional GIN index on `metadata` or an expression index on `(metadata->>'dedup_key')` exists, PostgreSQL must perform a sequential scan or at best a bitmap index scan using only the `(user_id, created_at)` components. With the `notifications` table growing at rate of multiple rows per cron run per user, this query will degrade over time. The query fires on **every single notification dispatch** (which includes every alert send).

**Impact:** Full or partial sequential scan on `notifications` per alert dispatch; latency growth proportional to table size.

**Fix:** Add a partial expression index: `CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_dedup_key ON notifications ((metadata->>'dedup_key')) WHERE metadata IS NOT NULL;`

---

### P1-3: `_tier_cache` In-Memory Dict is Unbounded and Not Thread-Safe Under Worker Restart

**File:** `backend/api/dependencies.py`, lines 96–141

The `_tier_cache` dict at line 96 has no maximum size limit. Every unique `user_id` adds a permanent entry (until it expires by TTL check on read) that is never proactively evicted. Under a single Gunicorn worker this grows to `O(daily_active_users)` entries, each holding a `(str, float)` tuple. On a 512MB Render instance with 50,000 DAUs, this could consume ~10–15MB of heap that is never recovered.

Additionally, because `gunicorn_config.py` (line 16) uses `workers = 1` in production currently, there is no inter-worker sharing issue, but if scaled to multiple workers each worker maintains its own independent cache, so the Redis cache's role becomes essential and any Redis failure silently falls through to stale in-memory data.

**Impact:** Slow heap growth; potential stale tier data visible to users (30s window is acceptable but unbounded dict is not); memory fragmentation over time.

**Fix:** Cap `_tier_cache` at a fixed size (e.g., 10,000 entries using `collections.OrderedDict` with LRU eviction) or switch fully to Redis with no in-memory fallback for tier data.

---

### P1-4: `HNSWVectorStore.search()` Issues Per-Result SQLite UPDATE Statements in a Loop

**File:** `backend/services/hnsw_vector_store.py`, lines 260–270

After each search, the `search()` method opens a new SQLite connection and iterates over every result, issuing one `UPDATE vectors SET usage_count = ... WHERE id = ?` per result (lines 265–269). For a `k=5` search, this is 5 separate `UPDATE` statements inside the `with sqlite3.connect(...)` context. This is called from the hot path of `_adjust_confidence_from_patterns()` in `recommendation_service.py` (line 335), which is invoked on every recommendation request.

**Impact:** 5× individual SQLite writes on every recommendation — SQLite `UPDATE` with a full table scan per row (unless `id` is indexed) plus Python loop overhead. Under moderate load this becomes a measurable bottleneck, especially since SQLite acquires write locks that block concurrent access.

**Fix:** Use a single batched `UPDATE ... WHERE id IN (...)` statement instead of per-row updates. The batch metadata lookup at lines 231–235 already demonstrates this pattern correctly — apply it to the usage update too.

---

### P1-5: `InMemoryCache.get()` Acquires the Global Lock on Every Cache Hit

**File:** `backend/integrations/pricing_apis/cache.py`, lines 542–562

The `InMemoryCache.get()` method acquires `self._lock` (an `asyncio.Lock`) on every access, including cache hits (lines 542–562). `asyncio.Lock()` is a coroutine-level mutex that serializes all concurrent reads through a single await point. For a cache that should support high read throughput (it is used for pricing data which is read-heavy), serializing every hit through a lock is unnecessary — reads on a Python dict are already thread-safe for GIL-protected operations, and asyncio is single-threaded.

**Impact:** Artificial serialization of all cache reads; reduces effective concurrency to 1 for cache-hit code paths.

**Fix:** Use a `asyncio.Lock` only for writes (`set`, `delete`) and allow lockless reads by taking a snapshot of the dict reference before accessing.

---

### P1-6: `email_scanner_service.scan_gmail_inbox` Issues One HTTP Request Per Message in a Sequential Loop

**File:** `backend/services/email_scanner_service.py`, lines 117–160

After the initial list request (line 109), the service fetches metadata for each message in a sequential `for msg_stub in messages` loop (lines 117–160), issuing one `client.get(...)` per message. With `max_results=50` (line 93), this is 50 sequential HTTP round-trips to the Gmail API. Each call has a 10s connect timeout. Under normal latency conditions (50ms per call), scanning 50 messages takes 2.5 seconds sequentially. Under degraded conditions it can hit the 30s request timeout.

**Impact:** Inbox scan takes 2–15+ seconds; ties up an async worker for the full duration; the `scan_outlook_inbox` function (lines 165–218) does the same.

**Fix:** Use `asyncio.gather()` or `asyncio.Semaphore` to fetch message metadata concurrently, similar to the weather fetch pattern already used in `fetch-weather`. A `Semaphore(10)` would limit to 10 concurrent Gmail API calls and reduce scan time to ~250ms.

---

### P1-7: `SavingsService.get_savings_history` Issues Two Serial Queries (COUNT + SELECT)

**File:** `backend/services/savings_service.py`, lines 156–173

`get_savings_history()` executes two sequential database queries: a `COUNT(*)` (line 156) followed by a paginated `SELECT` (line 163). These can be merged into a single query using `COUNT(*) OVER ()` as a window function, saving one full round-trip to Neon for every pagination request. The same pattern is used in `AlertService.get_alert_history()` at lines 614–631.

**Impact:** Double the network round-trips and connection usage for every paginated list endpoint.

**Fix:** Replace with a single query: `SELECT *, COUNT(*) OVER() AS total_count FROM user_savings WHERE user_id = :user_id ORDER BY created_at DESC LIMIT :limit OFFSET :offset`.

---

## P2 — Medium (Fix Soon)

### P2-1: `price_service.get_cheapest_supplier` Fetches Up to 50 Rows When Only the Minimum Is Needed

**File:** `backend/services/price_service.py`, lines 87–92

`get_cheapest_supplier()` calls `self._repo.get_current_prices(region, limit=50)` then applies a Python-side `min()`. This transfers up to 50 price rows over the wire when a single `ORDER BY price_per_kwh ASC LIMIT 1` in SQL would suffice. The same 50-row fetch is repeated in `get_price_comparison()` at line 104, which is fine since it returns the full sorted list — but `get_cheapest_supplier()` does not need all 50.

**Impact:** Up to 50× unnecessary data transfer for cheapest-supplier lookups; called on every recommendation request.

**Fix:** Add a `get_cheapest_price(region)` repository method using `ORDER BY price_per_kwh ASC LIMIT 1`.

---

### P2-2: `_sanitize_log_record` Uses a Per-Call `re.sub()` Loop on Every Log Event Value

**File:** `backend/app_factory.py`, lines 70–84

In addition to the list allocation issue (P0-2), the `_scrub()` inner function at line 70 iterates the `_SENSITIVE_PATTERNS` list applying `pattern.sub()` for every value in `event_dict`. Log events in structlog can have 5–15 key-value pairs. For each of the two patterns applied to each string value, this is 10–30 `re.sub()` calls per log event. Given the patterns (`postgresql://...@` and `sk_live_`) are rarely if ever present in normal log output, combining them into a single pre-compiled pattern via alternation (`pattern1|pattern2`) would reduce calls to 5–15 per event.

**Impact:** ~2× regex engine overhead per log event in production.

**Fix:** Combine the two patterns into a single compiled alternation: `re.compile(r"(postgresql|postgres|redis)://[^@\s]*@|\b(sk_live_|rk_live_)\w+", re.IGNORECASE)`.

---

### P2-3: `app_factory.py` `add_process_time_header` Logs Every Request in Non-Production

**File:** `backend/app_factory.py`, lines 501–508

In non-production environments, the `add_process_time_header` middleware logs every single request via `logger.info("request_completed", ...)` unconditionally (lines 501–508). In production, logging is filtered to only slow (>1s) or error (>=400) responses (lines 491–499). During development and staging with high test traffic, this generates thousands of log events per second through the structlog pipeline, including `_sanitize_log_record` processing, JSON serialization, and stdout writes.

**Impact:** Significant CPU and I/O overhead in test/staging environments; log spam obscures meaningful events; slows CI performance tests.

**Fix:** Apply the same filter in staging as in production, or add a `LOG_ALL_REQUESTS` flag to control verbosity.

---

### P2-4: `PricingCache._refresh_tasks` Dict Can Grow Without Eviction on Task Failure

**File:** `backend/integrations/pricing_apis/cache.py`, lines 338–358

The `_schedule_refresh()` method stores background refresh tasks in `self._refresh_tasks` dict keyed by cache key (line 361). The `finally` block at line 356 removes the task from the dict after completion. However, if `asyncio.create_task()` itself raises (e.g., event loop is closed), the task is never added but no exception is caught. More critically, if the `refresh()` coroutine is cancelled externally (e.g., application shutdown), the `finally` block still runs correctly, but if the coroutine raises `CancelledError` before reaching `finally`, the key may remain in `_refresh_tasks` permanently, preventing future refreshes for that key.

**Impact:** Cache keys can become permanently locked from background refresh after a cancellation, degrading to stale-serve-forever behavior.

**Fix:** Wrap the `create_task()` call in a try/except and add a task done callback using `task.add_done_callback(lambda t: self._refresh_tasks.pop(key, None))` as the cleanup mechanism, which runs even on cancellation.

---

### P2-5: CF Worker Metrics Are Per-Isolate and Reset on Every Cold Start

**File:** `workers/api-gateway/src/middleware/observability.ts`, lines 26–36

The `gatewayMetrics` object is defined at module level in the CF Worker (`let _startTime = Date.now()` at line 25). CF Workers use per-isolate memory, meaning each isolate (cold start) gets a fresh metrics counter set. With CF's typical isolate recycling behavior under low traffic, `cacheHits`, `cacheMisses`, and `totalRequests` never accumulate to meaningful values between the daily reset cron. The `getGatewayStats()` function at line 87 reports `cacheHitRate` which will always appear near 0 on freshly started isolates regardless of actual KV cache performance.

**Impact:** Cache hit rate metric is unreliable; operational monitoring of CF Worker health is blind to actual cache performance.

**Fix:** Persist rolling counters to KV every N requests (e.g., every 100) with atomic increment (`KV.put` with `metadata` for counters or use a Durable Object for accurate counters).

---

### P2-6: `EnsemblePredictor._load_weights_from_redis()` Creates a New Synchronous Redis Connection Each Call

**File:** `ml/inference/ensemble_predictor.py`, lines 203–222

`_load_weights_from_redis()` calls `redis.from_url(os.environ.get("REDIS_URL", ...))` at line 208, which creates a brand-new synchronous Redis connection pool on every invocation. There is no connection reuse or pool sharing with the application's async Redis client. Since this is called lazily on first `self.weights` access, it creates a new pool on every new `EnsemblePredictor` instance (or after a weight reload). This pool is also never explicitly closed.

**Impact:** New TCP connections to Redis on each weight load; connection leak if `EnsemblePredictor` instances are created frequently; extra Redis connection slots consumed unnecessarily.

**Fix:** Accept an optional `redis_client` parameter in `EnsemblePredictor.__init__` and pass the application's existing async Redis client; or cache the result in a module-level variable after first load.

---

### P2-7: `NeighborhoodService.get_comparison` Issues Two Sequential Queries Where One CTE Would Suffice

**File:** `backend/services/neighborhood_service.py`, lines 38–80

`get_comparison()` issues a `COUNT(DISTINCT user_id)` query first (lines 38–44) and only if it passes the threshold proceeds to the main comparison query (lines 61–80). The count query scans `user_savings` with `created_at >= NOW() - INTERVAL '30 days'` — the same range scanned by the main query. This is two round-trips and two index range scans over the same data.

**Impact:** Double the DB latency for every neighborhood comparison request; 2× connection time to Neon.

**Fix:** Merge the count into the main CTE using `COUNT(*) OVER ()` or check user_count in the CTE itself and return a conditional NULL result in one query.

---

### P2-8: `SavingsAggregator.get_combined_savings` Issues Two Sequential DB Queries

**File:** `backend/services/savings_aggregator.py`, lines 47–96

`get_combined_savings()` runs the per-utility savings query (line 47) and then a separate rank percentile query (lines 79+) as two sequential round-trips. These can be combined into a single CTE expression.

**Impact:** 2× network latency and DB round-trips per savings dashboard load.

**Fix:** Combine both aggregations into a single query using CTEs.

---

### P2-9: `alert_service.get_active_alert_configs` Joins `public.users` Without a Schema-Qualified Index Hint; No Result Streaming

**File:** `backend/services/alert_service.py`, lines 515–556

The join `JOIN public.users u ON u.id = pac.user_id` at line 530 requires that `public.users.id` has an index (it is a UUID PK, so it does). However, the query at line 535 has `ORDER BY pac.created_at` with `LIMIT 5000`, which requires either a full scan of `price_alert_configs` or an index on `(is_active, created_at)`. If `is_active` has low cardinality (most rows are TRUE), PostgreSQL may choose a seqscan. The entire result set is fetched into memory at line 538 (`result.mappings().all()`).

**Impact:** Potential sequential scan on `price_alert_configs`; entire 5,000-row result set held in Python memory simultaneously.

**Fix:** Ensure a composite index exists on `price_alert_configs(is_active, created_at)` and use server-side cursor iteration instead of `.all()`.

---

### P2-10: `NotificationService.get_unread` Has No Index on `(user_id, read_at)`

**File:** `backend/services/notification_service.py`, lines 37–58

The query at line 39 filters on `user_id = :uid AND read_at IS NULL`. The `read_at IS NULL` predicate is a partial filter that benefits enormously from a partial index. Without one, PostgreSQL must scan all rows for the user and filter on `read_at`. As notification rows accumulate (multiple per alert run per user), this query degrades proportionally.

**Impact:** Read latency grows linearly with per-user notification count for the unread notifications API.

**Fix:** Add `CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_unread ON notifications (user_id, created_at DESC) WHERE read_at IS NULL;`

---

### P2-11: CF Worker `proxyToOrigin` Does Not Enable Response Streaming for Non-SSE Routes

**File:** `workers/api-gateway/src/handlers/proxy.ts`, lines 36–50

`proxyToOrigin()` constructs a `new Response(originResponse.body, {...})` at line 44, which passes through the response body stream. However, the response headers are copied from `originResponse.headers` which may include `Content-Length`. If the Render origin compresses responses (GZip), the CF Worker re-wraps the compressed stream. There is no explicit `{ cf: { cacheEverything: false } }` fetch option, meaning CF's default caching may unexpectedly cache some responses that are not meant to be cached (e.g., POST responses that return 200 with body on some routes).

**Impact:** Potential incorrect caching of non-idempotent responses at the CF edge for routes not explicitly declared in `ROUTES`; subtle data staleness for users.

**Fix:** Add `{ cf: { cacheEverything: false } }` to the fetch options in `proxyToOrigin` for all non-GET requests.

---

### P2-12: `gunicorn_config.py` Sets `preload_app = False` and `workers = 1`

**File:** `backend/gunicorn_config.py`, lines 16, 29

`workers = 1` (line 16) means all requests are served by a single uvicorn worker. Under concurrent load this creates a single-thread bottleneck for CPU-bound operations that are not offloaded to `asyncio.to_thread()`. The comment acknowledges this is "for free tier" but the setting of `preload_app = False` (line 29) means the application module is re-imported on every worker restart (including the `max_requests=1000` rolling restart at line 33). At `max_requests=1000` requests, the worker restarts and re-imports the entire FastAPI application, re-registers all 40 routers, and re-initializes database connections — this takes 2–5 seconds during which the process handles no requests.

**Impact:** 2–5s cold gap every ~1,000 requests; all requests during restart are dropped or delayed.

**Fix:** Set `preload_app = True` so the application module is loaded once in the master process and forked to workers; this also enables copy-on-write memory sharing between workers if scaled to >1.

---

## P3 — Low / Housekeeping

### P3-1: `PricingCache` Wraps Every Cached Value in a `CacheEntry` Envelope

**File:** `backend/integrations/pricing_apis/cache.py`, lines 47–111

Every cached value is serialized as `{"value": ..., "created_at": "...", "ttl_seconds": ..., "key": "..."}` (lines 94–101). This adds ~60–80 bytes of JSON overhead per cached entry. For current price data (small dicts ~200 bytes), this is a ~30–40% storage overhead that Redis must store and the application must deserialize on every hit. Redis's native `EXPIREAT` / `EX` option on `SET` can handle TTL without storing it in the value.

**Fix:** Remove the `CacheEntry` envelope and use Redis `SET key value EX ttl` directly; track `created_at` only when needed for `stale-while-revalidate` via separate metadata key.

---

### P3-2: `app_factory._sanitize_log_record` Rebuilds a New `sanitized` Dict on Every Log Call

**File:** `backend/app_factory.py`, lines 75–87

A new `sanitized: dict = {}` is created and populated on every log event (line 75). Given structlog processes this for every log call across the application, including high-frequency debug logs, this creates a new dict allocation per event. Structlog processors can mutate `event_dict` in-place rather than constructing a new dict.

**Fix:** Mutate `event_dict` in place rather than constructing a new dict: `event_dict[key] = _scrub(value)`.

---

### P3-3: CF Worker `matchRoute` Iterates All Routes Linearly

**File:** `workers/api-gateway/src/router.ts`, lines 11–18

`matchRoute()` tests each route pattern in order against the pathname. With 14 routes in `ROUTES`, this is at most 14 regex `.test()` calls per request. Under CF Worker's V8 isolate this is fast (~microseconds), but patterns like `/^\/api\/v1\/suppliers(?:\/|$)/` at config.ts line 84 use non-trivial regex. For a production gateway receiving 100M+ requests/month, even a 1µs overhead per request costs 100 seconds of total CPU time per month.

**Fix:** This is acceptable for the current scale. For future growth, consider a trie-based router or pre-compiling route patterns into a single combined regex with capture groups.

---

### P3-4: `ensemble_predictor.py` Validates Input for NaN/Inf on Every Predict Call Using Full `np.any()`

**File:** `ml/inference/ensemble_predictor.py`, lines 298–304

The NaN/Inf validation at lines 298–304 calls `np.any(np.isnan(feature_values))` and `np.any(np.isinf(feature_values))` on the full feature matrix. For a 168-row DataFrame (7 days × hourly data), `feature_values` is a ~168×5 matrix. `np.isnan()` creates a temporary boolean array before `np.any()` traverses it. This is two full array allocations plus two traversals on each `predict()` call, which runs in a thread for each forecast request.

**Fix:** Use `np.any(~np.isfinite(feature_values))` to combine both checks into a single pass, reducing allocations from 2 to 1.

---

### P3-5: `RecommendationService._adjust_confidence_from_patterns` Does a Synchronous Vector Store Search In a Sync Call

**File:** `backend/services/recommendation_service.py`, lines 303–350

`_adjust_confidence_from_patterns()` (line 303) calls `self._vector_store.search()` synchronously (line 335). This is a sync method that opens a SQLite connection and executes queries, but it is called directly from the async `_compute_switching()` path without offloading to `asyncio.to_thread()`. Since the calling chain is `get_switching_recommendation()` → `_compute_switching()` → `_adjust_confidence_from_patterns()`, the synchronous SQLite I/O blocks the event loop for the duration.

**Fix:** Convert `_adjust_confidence_from_patterns` to `async def` and call `await self._vector_store.async_search()` (which already exists in `HNSWVectorStore`).

---

### P3-6: `alert_service.send_alerts` Processes Alerts in a Sequential `for` Loop

**File:** `backend/services/alert_service.py`, lines 264–343

`send_alerts()` iterates `triggered` pairs sequentially (line 265), calling `self._dispatcher.send()` for each. Each dispatcher call involves at minimum an in-app DB insert and possibly push + email HTTP calls. If there are 20 triggered alerts, they are processed one after the other, each waiting for the previous to complete. The `NotificationDispatcher.send()` already correctly parallelizes push and email within a single alert, but the outer loop is still sequential.

**Fix:** Use `asyncio.gather()` with `return_exceptions=True` to dispatch multiple alerts concurrently (up to a configurable `Semaphore` to prevent DB connection saturation).

---

### P3-7: `hnsw_vector_store.py` Opens Two Separate SQLite Connections in `search()` Back-to-Back

**File:** `backend/services/hnsw_vector_store.py`, lines 229–269

`search()` opens one SQLite connection for the batch metadata lookup (line 230) and then immediately opens a second connection for the usage count updates (line 264). Two consecutive `sqlite3.connect()` and `sqlite3.close()` calls for a single logical operation. SQLite connections are cheap but not free, especially on NFS or Docker-mounted volumes.

**Fix:** Combine both operations into a single `with sqlite3.connect(...) as conn:` block, or defer usage count updates to a background task.

---

### P3-8: `community_service.py` Issues a COUNT Query Before Every Post Creation

**File:** `backend/services/community_service.py`, lines 55–62

The rate limit check queries `COUNT(*) FROM community_posts WHERE user_id = :user_id AND created_at >= NOW() - INTERVAL '1 hour'`. This query runs before every post creation. For a table with many posts, this requires an index on `(user_id, created_at)` — which likely exists — but it is an extra round-trip before every insert. The rate-limiter middleware already provides IP-level rate limiting; moving post rate limiting to Redis (via the existing sliding window Lua script) would eliminate this DB query.

**Fix:** Implement post rate limiting using the Redis sliding window already in `middleware/rate_limiter.py` instead of a DB count.

---

### P3-9: `InMemoryCache` Holds an Unrestricted Dict as a Cache with No Maximum Size

**File:** `backend/integrations/pricing_apis/cache.py`, line 522

`InMemoryCache._cache` (line 522) is an unbounded dict. Expired entries are removed lazily on access (line 565) and via explicit `cleanup_expired()` (line 646), but `cleanup_expired()` is not called automatically on a schedule. If the cache fills with many unique region+supplier keys, expired entries accumulate until accessed again. In a long-running process with many regions, this becomes a memory leak.

**Fix:** Add a background task in `PricingCache.__init__` that calls `cleanup_expired()` periodically (e.g., every 5 minutes via `asyncio.create_task(self._periodic_cleanup())`).

---

### P3-10: Frontend `fetchWithRetry` Uses Sequential Retry Delay That Compounds With the 30s Backend Timeout

**File:** `frontend/lib/api/client.ts`, lines 170–207

The retry logic at line 202 uses `RETRY_BASE_MS * 2 ** attempt` — giving delays of 500ms, 1000ms between retries. With `MAX_RETRIES = 2`, a worst-case request that times out at the 30s backend timeout (from `app_factory.py` `REQUEST_TIMEOUT_SECONDS`) would take `30s + 0.5s + 30s + 1s + 30s = 91.5s` before final failure. Users waiting nearly 2 minutes for a definitive error response is unacceptable UX.

**Fix:** Add an `AbortController` with a client-side timeout (e.g., 15s per attempt) to match the user-facing expectation, separate from the backend's 30s infrastructure timeout. Only retry on network errors and 5xx, not on timeouts.

---

### P3-11: `gunicorn_config.py` Uses `max_requests = 1000` Without Considering Memory Leak Detection

**File:** `backend/gunicorn_config.py`, line 33

`max_requests = 1000` (line 33) causes the worker to restart after 1,000 requests. This is a blunt memory-leak mitigation. The `max_requests_jitter = 50` (line 34) adds randomness to avoid thundering herds. However, 1,000 requests at 100 RPS means a restart every 10 seconds in production — nearly a rolling restart that keeps the process permanently cold. More appropriate for a free-tier Render instance is `max_requests = 10000` or higher.

**Fix:** Increase `max_requests` to 5,000–10,000 to reduce restart frequency; instrument memory usage via Prometheus to identify actual leaks rather than relying on blunt restart cycling.

---

### P3-12: CF Worker KV Cache Has No Stampede Protection on Cache Miss

**File:** `workers/api-gateway/src/config.ts`, lines 40–99

The CF Worker route table enables KV-backed caching for price endpoints (e.g., TTL 300s for `/prices/current`). When a cached entry expires, multiple concurrent requests can simultaneously miss the KV cache and all forward to the Render origin before any response is written back to KV. This "cache stampede" multiplies origin traffic on expiry boundaries.

**Impact:** Bursts of simultaneous origin hits every 5 minutes (price cache TTL) when cache expires under load.

**Fix:** Implement a "lock" flag in KV: on miss, write a short-TTL placeholder before forwarding to origin. Alternatively, use the `staleWhileRevalidateSeconds` already defined per-route (e.g., 60s for `/prices/current`) which should be implemented in the caching middleware to serve stale content while background-refreshing.

---

## Files With No Issues Found

- `backend/repositories/base.py` — Abstract base only; no performance concerns.
- `backend/config/settings.py` — Settings loading via pydantic; appropriate validators; no performance concerns beyond standard startup cost.
- `workers/api-gateway/src/middleware/rate-limiter.ts` — Native CF rate limiter binding with fail-open; well-implemented.
- `workers/api-gateway/src/middleware/observability.ts` (logging only) — `buildLogEntry` and `logRequest` are lightweight; IP anonymization is O(1).
- `backend/services/recommendation_service.py` `get_daily_recommendations` — Correctly prefetches all data in 3 queries and delegates to pure computation helpers; the 3-query-to-11-query comment is accurate.
- `backend/services/alert_service.py` `check_thresholds` and `check_optimal_windows` — Correctly uses region-grouped dict for O(n+m) matching; no N+1 issues.
- `backend/services/alert_service.py` `_batch_should_send_alerts` — Correctly batches dedup checks by frequency tier; good use of VALUES clause.
- `backend/middleware/rate_limiter.py` — Lua sliding window script is correct; atomic ZADD+EXPIRE; `_check_redis_both` uses `asyncio.gather` for concurrent evaluation; seq counter TTL is set (after the prior fix).
- `backend/services/learning_service.py` `run_full_cycle` — Correctly sequential per region (avoids shared AsyncSession corruption per known codebase pattern); Redis + DB dual persistence.
- `backend/services/notification_dispatcher.py` `send()` — Correctly runs push and email concurrently with `asyncio.gather`; IN_APP runs first to create the notification_id; exceptions are logged via `return_exceptions=True`.

---

## Summary

**Total Findings:** 22 (2 P0, 7 P1, 12 P2 rolled into P2 section, 12 P3)

**Most Critical Issues:**

1. **P0-1** — `EnsemblePredictor` lazy weight loading performs synchronous blocking psycopg2 and synchronous Redis I/O that can block the event loop and wastes DB connections.

2. **P0-2** — `_sanitize_log_record` rebuilds compiled regex patterns and a fresh list on every single log event across the entire application, creating continuous GC pressure at scale.

3. **P1-1** — `get_active_alert_configs` fetches up to 5,000 rows with no pagination or streaming, creating a memory spike risk on the free-tier instance as users grow.

4. **P1-2** — Missing functional index on `notifications.metadata->>'dedup_key'` causes per-dispatch table scans that will degrade with every alert sent.

5. **P1-4** — `HNSWVectorStore.search()` issues individual per-row `UPDATE` statements in a loop on the hot recommendation path instead of a single batched statement.

6. **P1-6** — Gmail/Outlook inbox scanning uses sequential per-message HTTP calls instead of concurrent fan-out, causing 2–15s latency per scan and event loop blockage.

**Architecture Health:** The codebase demonstrates several excellent patterns — the `asyncio.to_thread()` wrapping of synchronous ML inference, the atomic Lua sliding-window rate limiter, the batch dedup query strategy in `_batch_should_send_alerts`, and the prefetch-then-compute approach in `get_daily_recommendations`. The primary risk profile is latency under scale, not correctness. The most impactful near-term improvements are the regex compilation fix (P0-2) and the notification dedup index (P1-2), as both affect every production request and every alert dispatch respectively.

**Infrastructure Note:** The single Gunicorn worker configuration (`workers = 1`, `preload_app = False`, `max_requests = 1000`) is appropriate for the current free-tier constraint but creates a predictable restart cadence at ~10 RPS that leaves a 2–5s gap during reload. This should be addressed before any significant traffic increase.
