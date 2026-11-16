# Audit Report: Performance
## Date: 2026-03-17
## Scope: Full codebase — backend hot paths, frontend rendering, DB queries, middleware

---

### Executive Summary

Twenty key files were sampled across both backend and frontend layers. The codebase is in
solid overall shape: composite indexes exist on the primary hot table (`electricity_prices`),
React Query stale-time and refetch intervals are well-tuned, the rate limiter uses an atomic
Lua sliding window, and the notification dispatcher correctly runs push and email concurrently.
The savings summary uses a single CTE-based SQL query rather than multiple round-trips.

Four issues stand out as worth addressing before traffic grows:

1. `ForecastService._forecast_electricity` issues an **unbounded SELECT** against
   `electricity_prices` (no LIMIT clause) filtered only by time window — with 90 days of
   hourly data for all suppliers this can return millions of rows.
2. `PriceService.get_optimal_usage_windows` materialises up to **5,000 Price objects in
   memory** and then runs an O(n) sliding-window loop over them; at scale the memory
   allocation dominates.
3. The `check-alerts` cron endpoint fetches prices with **one DB call per region** in a
   sequential `for` loop — with many distinct active regions this is a latency multiplier.
4. Every SSE price event on the realtime hook triggers a full **React Query cache
   invalidation** for `['prices', 'history', region]`, causing an immediate refetch of
   potentially 7 days of history data on every price tick.

---

### Findings

#### P0 — Critical

**PERF-01: Unbounded SELECT in `ForecastService._forecast_electricity`**

File: `backend/services/forecast_service.py`, lines 128–148

```python
result = await self.db.execute(
    text(f"""
        SELECT price_per_kwh, timestamp
        FROM electricity_prices
        WHERE utility_type = 'ELECTRICITY'
          AND timestamp >= NOW() - make_interval(days => :lookback_days)
          {region_filter}
        ORDER BY timestamp ASC
    """),
    params,
)
rows = result.mappings().all()   # <- all rows loaded into memory
```

`TREND_LOOKBACK_DAYS = 90`. With hourly data for every supplier across all states, this
window can hold tens of thousands of rows. There is **no LIMIT clause**. The `_extrapolate_trend`
function only uses a scalar mean and slope — it does not need every individual row. The same
issue applies to `_forecast_from_table` which calls the same pattern for heating_oil and
propane tables.

Recommended fix: push the aggregation into SQL. A daily-average group-by reduces 2,160 rows
(90 days × 24 hours) to 90 rows:

```sql
SELECT
    DATE_TRUNC('day', timestamp) AS day,
    AVG(price_per_kwh)           AS avg_price
FROM electricity_prices
WHERE utility_type = 'ELECTRICITY'
  AND timestamp >= NOW() - make_interval(days => :lookback_days)
  /* optional: AND region = :region */
GROUP BY DATE_TRUNC('day', timestamp)
ORDER BY day ASC
```

This reduces network transfer, Python heap allocation, and still gives `_extrapolate_trend`
the data it needs for linear regression.

Severity: **P0** — a single unauthenticated call to `/forecast?utility_type=electricity`
without a state filter will scan the entire 90-day global price history.

---

#### P1 — High

**PERF-02: O(n) sliding-window scan materialises up to 5,000 rows in memory**

File: `backend/services/price_service.py`, lines 395–425 (`get_optimal_usage_windows`)

```python
prices = await self._repo.get_historical_prices(
    region=region, start_date=start, end_date=end, supplier=supplier
)  # default limit=5000

prices = sorted(prices, key=lambda p: p.timestamp)

for i in range(len(prices) - duration_hours + 1):
    window_prices = prices[i:i + duration_hours]
    avg_price = sum(p.price_per_kwh for p in window_prices) / duration_hours
    windows.append(...)

windows.sort(key=lambda w: w['avg_price'])
return windows[:5]
```

With `within_hours=24` and hourly data the row count is manageable, but callers can pass
larger values. The loop iterates O(n) times, allocating a list slice on every iteration.
More importantly, the repository default `limit=5000` means callers with wide date ranges
silently get capped without error.

The entire computation can be pushed to SQL using a window function:

```sql
SELECT
    timestamp                                           AS start_time,
    AVG(price_per_kwh) OVER (
        ORDER BY timestamp
        ROWS BETWEEN CURRENT ROW AND :w FOLLOWING
    )                                                   AS window_avg
FROM electricity_prices
WHERE region = :region AND timestamp BETWEEN :start AND :end
ORDER BY window_avg
LIMIT 5
```

This returns only 5 rows with zero Python-side sorting and no list allocation.

---

**PERF-03: Sequential per-region DB calls in `check-alerts` cron**

File: `backend/api/v1/internal/alerts.py`, lines 81–90

```python
for region in regions:
    try:
        prices = await price_repo.list(region=region, page=1, page_size=20)
        all_prices.extend(prices)
    except Exception as exc:
        ...
```

If there are R distinct alert regions this issues R sequential queries against Neon. Even
with the CF Worker cache, each Render cold-start round trip is ~150–300 ms. With 20 regions
the sequential penalty is 3–6 seconds added to an already time-sensitive cron path.

Two remedies:
1. Batch with `asyncio.gather`: each `await price_repo.list(...)` is independent. However,
   note that sharing a single `AsyncSession` across gathered coroutines is unsafe (session
   is not thread-safe). Use one session per coroutine, or
2. Replace with a single SQL query that uses `DISTINCT ON (region)` to get the latest price
   per region in one round-trip:

```sql
SELECT DISTINCT ON (region) *
FROM electricity_prices
WHERE region = ANY(:regions)
ORDER BY region, timestamp DESC
```

This reduces R round-trips to 1.

---

**PERF-04: SSE message handler invalidates the full history cache on every tick**

File: `frontend/lib/hooks/useRealtime.ts`, lines 87–88

```typescript
// History cache: invalidate since it needs full refetch for chart data
queryClient.invalidateQueries({ queryKey: ['prices', 'history', region] })
```

`useCurrentPrices` is already served by a 60-second polling interval. When the SSE stream
delivers a price update, invalidating `['prices', 'history', region]` triggers an immediate
API call to `/prices/history` — which can return up to 7 days of price rows for the chart.
The comment acknowledges this with "needs full refetch" but accepts it silently.

For the dashboard use case the chart is driven by `historyData` from `usePriceHistory`.
A full refetch every 30 seconds (the SSE interval default) wastes bandwidth and backend
query budget.

Options ranked by preference:
- Remove the history invalidation entirely; instead update the current-price cache only
  (already done via `queryClient.setQueryData`) and let history refetch on its normal stale
  cycle (1 minute).
- If live chart updates are desired, append the new price point to the cached history list
  using `setQueryData` rather than triggering a refetch.

---

**PERF-05: `usePriceHistory` sends `days` param calculated from hours but the hook's queryKey includes `hours`, causing unnecessary cache misses when the hook is called with semantically equivalent hour values**

File: `frontend/lib/hooks/usePrices.ts`, lines 33–41

```typescript
const days = Math.max(1, Math.ceil(hours / 24))
return useQuery({
  queryKey: ['prices', 'history', region, hours],   // keyed on raw hours
  queryFn: ({ signal }) => getPriceHistory({ region: region!, days }, signal),
  ...
})
```

`hours=24` and `hours=23` both produce `days=1` but create two distinct cache entries. The
dashboard passes `TIME_RANGE_HOURS[timeRange]` (e.g. `6, 12, 24, 48, 168`). All values 1–24
produce `days=1`. A user switching between '6h', '12h', and '24h' tabs hits the network each
time even though the backend returns identical data.

Fix: normalise the query key to `days` to match what is actually sent to the backend:

```typescript
queryKey: ['prices', 'history', region, days],
```

---

**PERF-06: `get_cheapest_supplier` and `get_price_comparison` both fetch 50 rows then sort in Python**

File: `backend/services/price_service.py`, lines 78–112

```python
async def get_cheapest_supplier(self, region):
    prices = await self._repo.get_current_prices(region, limit=50)
    return min(prices, key=lambda p: p.price_per_kwh)

async def get_price_comparison(self, region):
    prices = await self._repo.get_current_prices(region, limit=50)
    return sorted(prices, key=lambda p: p.price_per_kwh)
```

Both methods hit the same `get_current_prices` call (which fetches `ORDER BY timestamp DESC`)
and then re-sort in Python. The comparison endpoint should use `ORDER BY price_per_kwh ASC`
directly in SQL and the cheapest should use `LIMIT 1`. Neither benefits from the 1-minute
Redis cache on `get_current_prices` because the cache key encodes `limit=50` — which
coincidentally matches, so the cache does help here, but the Python-side `min()/sorted()`
is redundant if the SQL already orders correctly.

Recommended fix: add a dedicated `get_cheapest_by_price` repository method using
`ORDER BY price_per_kwh ASC LIMIT 1` to eliminate both the over-fetch and the Python sort.

---

**PERF-07: `_is_duplicate` dedup query in `NotificationDispatcher` lacks a partial index on `metadata ->> 'dedup_key'`**

File: `backend/services/notification_dispatcher.py`, lines 473–492

```python
result = await self._db.execute(
    text("""
        SELECT id FROM notifications
        WHERE user_id   = :user_id
          AND metadata  IS NOT NULL
          AND metadata  ->> 'dedup_key' = :dedup_key
          AND created_at >= :cutoff
        ORDER BY created_at DESC
        LIMIT 1
    """), ...
)
```

Migration 026 (`026_notifications_metadata.sql`) adds:

```sql
CREATE INDEX IF NOT EXISTS idx_notifications_dedup_key
    ON notifications ((metadata ->> 'dedup_key'), user_id, created_at DESC)
```

This index exists, which is good. However the query filters on `metadata IS NOT NULL` first,
which is evaluated as a separate predicate before the index expression. PostgreSQL may use
the functional index on `(metadata ->> 'dedup_key')`, but only when the planner estimates
the selectivity is high enough — with many NULL-metadata rows the planner may prefer a
sequential scan. The index should use a `WHERE metadata IS NOT NULL` partial clause to
signal to the planner that NULLs are excluded:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_dedup_key_v2
    ON notifications ((metadata ->> 'dedup_key'), user_id, created_at DESC)
    WHERE metadata IS NOT NULL;
```

This is a query-pattern correctness issue that will degrade under load; it is not guaranteed
to be a problem today on small datasets.

---

#### P2 — Medium

**PERF-08: `calculate_daily_cost` in `PriceService` runs two sequential DB round-trips on cache miss**

File: `backend/services/price_service.py`, lines 136–155

```python
prices = await self._repo.get_historical_prices(...)
if not prices:
    current = await self.get_current_price(region, supplier)  # second DB call
```

The fallback `get_current_price` call only fires when there are no historical prices, which
is rare. But when it does fire, it is sequential without any await parallelism. This is a
minor issue today; consider caching the fallback result or handling it with `COALESCE` in a
single SQL query.

---

**PERF-09: `get_savings_history` issues two sequential queries (COUNT then SELECT)**

File: `backend/services/savings_service.py`, lines 156–175

```python
count_result = await self.db.execute(
    text("SELECT COUNT(*) FROM user_savings WHERE user_id = :user_id"), ...
)
rows_result = await self.db.execute(
    text("SELECT ... FROM user_savings WHERE user_id = :user_id ORDER BY ... LIMIT :limit OFFSET :offset"), ...
)
```

This is the same pattern as `PriceRepository.get_historical_prices_paginated` — two
sequential queries where `asyncio.gather` would allow both to execute concurrently within
the same session. The `get_historical_prices_paginated` in `price_repository.py` (lines
565–573) already does this correctly with `asyncio.gather`. The savings pagination should
adopt the same pattern.

Note: `asyncio.gather` on a shared `AsyncSession` is safe for read-only queries because
asyncpg multiplexes concurrent statements over a single connection when using the async
driver. Both queries here are reads.

---

**PERF-10: `_build_features` in `PriceService` calls `get_historical_prices` with 7 days of data but does not cache the result**

File: `backend/services/price_service.py`, lines 260–288 (`_build_features`)

```python
start = end - timedelta(hours=168)  # 7 days of history
prices = await self._repo.get_historical_prices(
    region=region, start_date=start, end_date=end
)
```

`get_historical_prices` does not cache (unlike `get_current_prices` which has a 60-second
Redis cache). Every forecast call rebuilds the feature DataFrame from scratch. Given that
forecasts are refetched every 5 minutes by the frontend (`refetchInterval: 300000`), this
DB query runs every 5 minutes per user per region.

Since `_build_features` only needs the last 7 days and the ML prediction is read-only, the
feature DataFrame (or the raw price series) is a strong candidate for a 5-minute Redis
cache keyed on `(region, round-to-5min)`.

---

**PERF-11: `record_login_attempt` issues two Redis round-trips sequentially**

File: `backend/middleware/rate_limiter.py`, lines 328–330

```python
attempts = await self.redis.incr(key)
await self.redis.expire(key, self.lockout_minutes * 60)
```

`INCR` and `EXPIRE` are two separate round-trips. This is a classic race where the key can
persist without expiry if the process crashes between the two calls. Use `SET ... EX ...
NX` with an explicit counter-in-value approach, or use a pipeline:

```python
pipe = self.redis.pipeline()
pipe.incr(key)
pipe.expire(key, self.lockout_minutes * 60)
attempts, _ = await pipe.execute()
```

The Lua script used for per-request rate limiting (lines 42–65) already correctly sets TTL
atomically; the login path should match that discipline.

---

**PERF-12: `DashboardContent` computes `optimalWindow` with an O(n) JavaScript loop inside `useMemo`**

File: `frontend/components/dashboard/DashboardContent.tsx`, lines 95–119

```typescript
const optimalWindow: OptimalWindow | null = React.useMemo(() => {
  const prices: ApiPrice[] = forecastModel.prices || []
  for (let i = 0; i <= prices.length - 4; i++) {
    const sum = prices
      .slice(i, i + 4)
      .reduce((s, p) => s + parseFloat(p.price_per_kwh), 0)
    ...
  }
}, [forecastData])
```

`parseFloat` is called inside the inner `reduce` — O(n * 4) float parses per render trigger.
With a 24-hour forecast this is 24 × 4 = 96 parses, which is negligible for modern browsers.
However, if `hours` is ever increased to 168 (7-day forecast) the inner loop does 672 parses
per `useMemo` recalculation. The dependency is `forecastData` which is stable across renders,
so the memoisation is correct. This is a micro-concern but worth noting for future horizon
expansion.

---

**PERF-13: `useRealtimePrices` sets incorrect `setQueryData` shape for the current-prices cache**

File: `frontend/lib/hooks/useRealtime.ts`, lines 76–84

```typescript
queryClient.setQueryData<unknown>(
  ['prices', 'current', region],
  (old: unknown) => {
    if (!old || !Array.isArray(old)) return old   // <-- guard bails when old is ApiCurrentPriceResponse
    return old.map(...)
  }
)
```

`useCurrentPrices` stores data as `ApiCurrentPriceResponse` (an object with a `prices`
array), not a bare array. The `Array.isArray(old)` check will always be false, so the
partial-merge branch never runs — the cache is never updated from SSE events. The fallback
is the history cache invalidation (PERF-04), which causes a full refetch. The cache update
logic should be fixed to match the actual response shape:

```typescript
(old: ApiCurrentPriceResponse | undefined) => {
  if (!old?.prices) return old
  return {
    ...old,
    prices: old.prices.map(entry =>
      entry.supplier === data.supplier
        ? { ...entry, price_per_kwh: data.price_per_kwh, timestamp: data.timestamp, is_peak: data.is_peak }
        : entry
    )
  }
}
```

When this is fixed, the history invalidation (PERF-04) can be removed entirely.

---

**PERF-14: `ForecastService._extrapolate_trend` runs its own pure-Python linear regression on all rows**

File: `backend/services/forecast_service.py`, lines 255–294

```python
sum_x  = sum(days)
sum_y  = sum(prices)
sum_xy = sum(x * y for x, y in zip(days, prices))
sum_xx = sum(x * x for x in days)
# ... then separately:
predicted = [intercept + slope * d for d in days]
ss_res = sum((y - yp) ** 2 for y, yp in zip(prices, predicted))
```

Five separate `sum()` passes over the same data. With PERF-01 fixed (aggregated to ~90
daily rows) this is fine. Without PERF-01 the data can be thousands of rows and these five
O(n) Python loops run synchronously on the event loop thread, blocking the async event loop
for potentially tens of milliseconds.

If PERF-01 is fixed first this becomes negligible. If not, wrap in `asyncio.to_thread`.

---

#### P3 — Low

**PERF-15: `rate_limiter._check_memory` rebuilds the list comprehension on every call**

File: `backend/middleware/rate_limiter.py`, lines 278–280

```python
self._memory_store[key] = [t for t in existing if t > window_start]
```

This creates a new list on every request when using the in-memory fallback. With Redis
configured (production), this code path is never executed, so the impact is zero in prod
but may slow down tests that exercise the in-memory path under load. `collections.deque`
with `popleft` would be more efficient for sliding-window semantics, but this is a
cold-standby path only.

---

**PERF-16: `_PRICE_COLUMNS` string interpolated into every raw SQL query**

File: `backend/repositories/price_repository.py`, lines 22–26

```python
_PRICE_COLUMNS = (
    "id, region, supplier, price_per_kwh, currency, timestamp, "
    "is_peak, source_api, created_at, carbon_intensity, utility_type"
)
```

Used as `f"SELECT {_PRICE_COLUMNS} FROM electricity_prices ..."` in 6+ methods. This
produces query strings that are unique per call, bypassing SQLAlchemy's internal prepared
statement plan cache. In asyncpg with `prepared_statement_cache_size > 0`, identical query
strings hit a plan cache; slightly varying strings do not. Since `_PRICE_COLUMNS` is a
module-level constant the interpolated string is always identical, so this is fine. However,
the combination with dynamic `LIMIT` and `WHERE` clauses means many query strings are
structurally unique. This is a known limitation of raw `text()` SQL and is not urgently
actionable without a larger refactor to SQLAlchemy Core expressions.

---

**PERF-17: `DashboardContent` subscribes to three separate Zustand store slices independently**

File: `frontend/components/dashboard/DashboardContent.tsx`, lines 38–40

```typescript
const region          = useSettingsStore((s) => s.region)
const currentSupplier = useSettingsStore((s) => s.currentSupplier)
const annualUsage     = useSettingsStore((s) => s.annualUsageKwh)
```

Three separate `useSettingsStore` calls means three separate subscriptions. If multiple
store fields change atomically (e.g. onboarding saves all preferences at once), the
component re-renders three times. A combined selector would reduce this to one subscription:

```typescript
const { region, currentSupplier, annualUsage } = useSettingsStore(
  (s) => ({ region: s.region, currentSupplier: s.currentSupplier, annualUsage: s.annualUsageKwh }),
  shallow
)
```

This requires Zustand's `shallow` equality. The impact is trivial for a component that
re-renders at most once per settings save, but the pattern should be consistent across the
codebase.

---

**PERF-18: `_row_to_price` Pydantic model construction called N times per repository query**

File: `backend/repositories/price_repository.py`, lines 29–43

Every query result row creates a new `Price` Pydantic model via `_row_to_price`. Pydantic
v2 model construction is fast (~1–2 µs per instance), but with `limit=5000` this is 5,000
constructor calls. This is negligible at current scale but would be a bottleneck at very
high data volumes. Consider a dataclass or TypedDict for internal data transfer objects
that don't need validation, converting to Pydantic only at the API boundary.

---

### Statistics

| Severity | Count | Files Affected |
|----------|-------|----------------|
| P0 Critical | 1 | `forecast_service.py` |
| P1 High | 6 | `price_service.py`, `internal/alerts.py`, `useRealtime.ts`, `usePrices.ts`, `notification_dispatcher.py` |
| P2 Medium | 6 | `price_service.py`, `savings_service.py`, `rate_limiter.py`, `DashboardContent.tsx`, `useRealtime.ts`, `forecast_service.py` |
| P3 Low | 4 | `rate_limiter.py`, `price_repository.py`, `DashboardContent.tsx`, `price_repository.py` |
| **Total** | **17** | **9 files** |

### Recommended Priority Order

1. **PERF-01** (P0) — Add LIMIT or aggregate in `ForecastService._forecast_electricity`.
   One-line fix, zero risk, prevents potential OOM on high-traffic.
2. **PERF-13** (P2) — Fix the SSE `setQueryData` shape so the cache partial-merge actually
   runs. This is a correctness bug masquerading as a performance issue. Once fixed, PERF-04
   (history invalidation) resolves itself.
3. **PERF-04** (P1) — Remove the blanket history cache invalidation on SSE tick (becomes
   redundant after PERF-13).
4. **PERF-03** (P1) — Replace sequential per-region loop in check-alerts with a single
   `DISTINCT ON` query.
5. **PERF-05** (P1) — Align `usePriceHistory` queryKey to `days` not `hours`.
6. **PERF-02** (P1) — Push optimal-window computation to SQL.
7. **PERF-09** (P2) — Parallelise COUNT + SELECT in `get_savings_history` with
   `asyncio.gather`.
8. **PERF-11** (P2) — Pipeline the Redis `INCR` + `EXPIRE` in `record_login_attempt`.
