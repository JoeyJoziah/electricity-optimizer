# Performance Audit — RateShift (2026-03-16)

Auditor: Performance Engineer (Claude Sonnet 4.6)
Scope: Backend services, API endpoints, price repository, frontend dashboard components, data-fetching hooks, SSE streaming.

---

## Executive Summary

The codebase is in substantially good shape after Wave 5 performance work. SQL aggregation has replaced in-memory computation in most hot paths, pagination is enforced at the API boundary, Redis caching with stampede prevention is wired into the price repository and analytics service, and composite indexes cover the primary query patterns. The SSE layer uses per-user connection limits and exponential back-off reconnection on the frontend.

The remaining issues fall into two categories: (1) a handful of **unbounded or large-payload SQL queries** that bypass the pagination and caching layers, and (2) **frontend patterns** that either fire redundant network requests or invalidate entire query groups where a targeted cache update would suffice. One backend issue is classified P1 because it can return up to 5,000 rows in a single in-process list before any work is done.

**Total findings: 11**
- P0: 0
- P1: 2
- P2: 5
- P3: 4

---

## P1 Findings

---

### PERF-01 — `check_alerts` fetches prices in a serial Python loop (N+1 per region)

**Severity:** P1
**File:** `backend/api/v1/internal/alerts.py`
**Lines:** 80–90

```python
for region in regions:
    try:
        prices = await price_repo.list(region=region, page=1, page_size=20)
        all_prices.extend(prices)
```

**Description:**
The `check_alerts` cron endpoint collects all distinct regions from up to 5,000 alert configs, then fires one `SELECT … WHERE region = ?` database round-trip per region — sequentially, in a `for` loop. With 50 US states each having alert subscribers this is 50 individual async DB calls that cannot overlap because the next iteration waits for the previous one. Each call also re-queries the same indexed table with no cache layer.

**Estimated impact:**
At 50 regions with a 2 ms per-query Neon round-trip, the price-fetch phase adds ~100 ms to every cron execution. Under network jitter this can exceed 300–500 ms. The cron runs every 30 minutes so this is not catastrophic, but the latency compounds with the downstream alert-history inserts (also serial, lines 152–168).

**Fix:**
Replace the serial loop with a single `IN (:regions)` query using `asyncio.gather`, or better, a single SQL query that returns the N most-recent prices per region using `DISTINCT ON`:

```sql
-- Single query replaces N region loops
SELECT DISTINCT ON (region) id, region, supplier, price_per_kwh,
       currency, timestamp, is_peak, source_api, created_at,
       carbon_intensity, utility_type
FROM electricity_prices
WHERE region = ANY(:regions)
  AND utility_type = 'ELECTRICITY'
ORDER BY region, timestamp DESC
```

Pass `regions` as a PostgreSQL array parameter (`asyncpg` supports `list` natively). This reduces N DB round-trips to 1.

Also convert the history-record loop (lines 152–168) to a bulk insert via `PriceRepository.bulk_create` pattern or a single multi-row `INSERT INTO alert_history … VALUES …`.

---

### PERF-02 — `ForecastService._forecast_electricity` and `_forecast_from_table` issue unbounded SELECT over 90 days with no LIMIT

**Severity:** P1
**File:** `backend/services/forecast_service.py`
**Lines:** 115–135 (`_forecast_electricity`), 168–177 (`_forecast_from_table`)

```python
result = await self.db.execute(
    text(f"""
        SELECT price_per_kwh, timestamp
        FROM electricity_prices
        WHERE utility_type = 'ELECTRICITY'
          AND timestamp >= NOW() - INTERVAL '{TREND_LOOKBACK_DAYS} days'
          {region_filter}
        ORDER BY timestamp ASC
    """),    # <-- no LIMIT
    params,
)
rows = result.mappings().all()   # materialises ALL rows into Python memory
```

**Description:**
`TREND_LOOKBACK_DAYS = 90`. For a busy region such as `us_ct` or `us_ny` with hourly data this is 90 × 24 = 2,160 rows per query. For `natural_gas` the same pattern applies against `electricity_prices` filtered by `utility_type = 'NATURAL_GAS'`. All rows are fetched into Python memory before `_extrapolate_trend` discards everything except the price scalar. The trend computation only needs the slope of a linear regression, which can be computed entirely in SQL with `regr_slope` / `regr_intercept`.

**Estimated impact:**
2,000+ row result sets serialised over the Neon connection on every `/forecast` request. At peak concurrent usage (multiple tabs, Business-tier users) this can saturate the Neon connection pool and add 50–200 ms of transfer latency per call.

**Fix (option A — SQL regression):**
Replace both raw-row queries with a single SQL aggregation call:

```sql
SELECT
    REGR_SLOPE(price_val, day_offset)    AS slope,
    REGR_INTERCEPT(price_val, day_offset) AS intercept,
    MAX(price_val)                        AS last_price,
    MAX(day_offset)                       AS last_day,
    COUNT(*)                              AS n
FROM (
    SELECT
        price_per_kwh::float AS price_val,
        EXTRACT(EPOCH FROM (timestamp - MIN(timestamp) OVER())) / 86400 AS day_offset
    FROM electricity_prices
    WHERE region = :region
      AND utility_type = :utility_type
      AND timestamp >= NOW() - INTERVAL '90 days'
) sub
```

This returns 1 row, lets Postgres do the maths, and eliminates the Python linear-regression loop entirely.

**Fix (option B — add LIMIT as immediate stopgap):**
Add `LIMIT 500` to both queries until option A is implemented. 500 daily points over 90 days is more than sufficient for trend accuracy.

**Also add Redis caching** in `ForecastService.get_forecast()` — the result is deterministic for a 24-hour window and could be cached with a 30-minute TTL, matching the `analytics_service` pattern already used for `get_price_trend`.

---

## P2 Findings

---

### PERF-03 — `PriceService.get_optimal_usage_windows` loads up to 5,000 price rows into Python memory

**Severity:** P2
**File:** `backend/services/price_service.py`
**Lines:** 396–425

```python
prices = await self._repo.get_historical_prices(
    region=region,
    start_date=start,
    end_date=end,
    supplier=supplier
)
# default limit=5000 in the repo
...
windows = []
for i in range(len(prices) - duration_hours + 1):
    window_prices = prices[i:i + duration_hours]
    avg_price = sum(p.price_per_kwh for p in window_prices) / duration_hours
```

**Description:**
`get_historical_prices` has a default `limit=5000`. For `within_hours=24` this is reasonable (~24 rows), but there is no upper-bound check on `within_hours` and the caller does not enforce one. The sliding-window calculation is O(n × duration) in Python. For `within_hours=168` (7 days) this is 168 rows × 24 window iterations = still small, but the default `limit=5000` in the repository creates a footgun if `within_hours` is increased without re-constraining the repo call.

More importantly, the `get_prices/stream` SSE endpoint and `usePriceHistory` hook can request up to `hours=168` (7d) which translates to `days=7` downstream — currently capped at 100 records per page in the paginated path, which is fine. But `get_optimal_usage_windows` uses the *non-paginated* path with `limit=5000`.

**Fix:**
Cap `within_hours` to 168 (7 days) in the service method and pass an explicit `limit` equal to `within_hours + some margin` to the repository call. Replace the Python sliding window with a SQL window query:

```sql
SELECT
    start_ts,
    AVG(price_per_kwh) OVER (
        ORDER BY timestamp
        ROWS BETWEEN CURRENT ROW AND :window_hours FOLLOWING
    ) AS window_avg
FROM electricity_prices
WHERE region = :region
  AND timestamp BETWEEN :start AND :end
ORDER BY window_avg ASC
LIMIT 5
```

---

### PERF-04 — `SavingsAggregator.get_combined_savings` fires two sequential DB queries; the rank query scans all users without an index

**Severity:** P2
**File:** `backend/services/savings_aggregator.py`
**Lines:** 79–92

```python
rank_sql = text("""
    SELECT PERCENT_RANK() OVER (ORDER BY total_savings) AS pct
    FROM (
        SELECT user_id, SUM(amount) AS total_savings
        FROM user_savings
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY user_id
    ) sub
    WHERE user_id = :user_id
""")
```

**Description:**
This subquery groups and sums `user_savings` for **all users** in the last 30 days just to compute a percentile for one user. As the user base grows this becomes a full table scan aggregation that runs on every `/savings/combined` request. It is not cached. The `user_savings` table has `idx_user_savings_user_id` and `idx_user_savings_created_at` but no composite index covering `(created_at, user_id, amount)` for the aggregate.

**Estimated impact:**
At 10,000 users with 30 savings records each (300,000 rows), the rank sub-query causes a seq-scan aggregation on the entire recent-activity window every time the CombinedSavingsCard renders.

**Fix (short term):**
Cache the result in Redis with a 5-minute TTL, keyed by user_id. The combined savings data is already `staleTime: 5 * 60 * 1000` on the frontend so caching server-side at the same TTL eliminates repeat DB work.

**Fix (long term):**
Add a composite index: `CREATE INDEX idx_user_savings_created_amount ON user_savings (created_at, user_id, amount)`. Also consider materialising the rank into a `user_savings_rank` table updated by a daily cron, avoiding the real-time subquery altogether.

---

### PERF-05 — `useRealtimePrices` SSE `onmessage` invalidates the full history query cache on every price tick

**Severity:** P2
**File:** `frontend/lib/hooks/useRealtime.ts`
**Lines:** 87–88

```typescript
// History cache: invalidate since it needs full refetch for chart data
queryClient.invalidateQueries({ queryKey: ['prices', 'history', region] })
```

**Description:**
Every SSE message (every 30 seconds for Business users) triggers a background refetch of the entire price history query — potentially 24–168 rows per request, serialised to JSON and sent across the network. The `useCurrentPrices` partial-merge (lines 76–84) is correctly implemented, but the history invalidation negates that optimisation for the chart. Since the history endpoint is already paginated and the chart only shows the most recent page, a targeted `setQueryData` append is significantly cheaper than a full cache bust.

**Estimated impact:**
For a 7-day time range (`hours=168`), each SSE tick triggers a `GET /prices/history?region=X&days=7` response (~168 rows). At 30-second intervals per open Business tab this is 120 API calls/hour per user — most returning identical data.

**Fix:**
In `onmessage`, append the new price point to the cached history list rather than invalidating:

```typescript
queryClient.setQueryData(
  ['prices', 'history', region],
  (old: ApiPriceHistoryResponse | undefined) => {
    if (!old?.prices) return old
    const updated = [...old.prices]
    // Replace or append the matching timestamp entry
    const idx = updated.findIndex(p => p.supplier === data.supplier)
    if (idx >= 0) {
      updated[idx] = { ...updated[idx], price_per_kwh: data.price_per_kwh, timestamp: data.timestamp }
    } else {
      updated.push({ supplier: data.supplier, price_per_kwh: data.price_per_kwh, timestamp: data.timestamp, is_peak: data.is_peak, region })
    }
    return { ...old, prices: updated }
  }
)
```

Remove the `invalidateQueries` call. Schedule a periodic full refetch at a longer interval (e.g. 5 minutes) using `refetchInterval` on the `usePriceHistory` hook.

---

### PERF-06 — `community_service.list_posts` joins full `community_votes` and `community_reports` aggregates on every page request without caching

**Severity:** P2
**File:** `backend/services/community_service.py`
**Lines:** 203–226

```sql
LEFT JOIN (
    SELECT post_id, COUNT(*) AS cnt
    FROM community_votes
    GROUP BY post_id
) v ON v.post_id = cp.id
LEFT JOIN (
    SELECT post_id, COUNT(*) AS cnt
    FROM community_reports
    GROUP BY post_id
) r ON r.post_id = cp.id
```

**Description:**
The `list_posts` query aggregates the entire `community_votes` and `community_reports` tables via correlated subqueries on every request, then filters to 10 posts. As votes and reports grow, the inner `GROUP BY` subqueries scan all rows regardless of the outer `WHERE cp.region = :region` filter, because the subqueries are unconditional. There is no caching on this endpoint.

**Note:** Migration 050 adds partial indexes for `community_posts` visibility, which helps the outer query. The join subqueries are not indexed.

**Estimated impact:**
With 50,000 total votes across all regions, both subqueries do 50,000 row aggregations on each page load. For the Community page at 60-second refetch intervals across concurrent users this adds unnecessary DB load.

**Fix (option A — targeted join):**
Filter the vote/report subqueries by post_id set from the outer query using a CTE:

```sql
WITH visible AS (
    SELECT id FROM community_posts
    WHERE region = :region AND utility_type = :utility_type
      AND is_hidden = false AND is_pending_moderation = false
    ORDER BY created_at DESC LIMIT :limit OFFSET :offset
),
vote_counts AS (
    SELECT post_id, COUNT(*) AS cnt
    FROM community_votes
    WHERE post_id IN (SELECT id FROM visible)
    GROUP BY post_id
),
report_counts AS (
    SELECT post_id, COUNT(*) AS cnt
    FROM community_reports
    WHERE post_id IN (SELECT id FROM visible)
    GROUP BY post_id
)
SELECT cp.*, COALESCE(v.cnt, 0) AS upvote_count,
             COALESCE(r.cnt, 0) AS report_count,
             (SELECT COUNT(*) FROM community_posts
              WHERE region = :region AND utility_type = :utility_type
                AND is_hidden = false AND is_pending_moderation = false) AS _total_count
FROM community_posts cp
JOIN visible ON cp.id = visible.id
LEFT JOIN vote_counts v ON v.post_id = cp.id
LEFT JOIN report_counts r ON r.post_id = cp.id
```

**Fix (option B — short-term):**
Add indexes: `CREATE INDEX idx_community_votes_post_id ON community_votes (post_id)` and `CREATE INDEX idx_community_reports_post_id ON community_reports (post_id)`. This transforms the GROUP BY subqueries from seq-scans to index scans.

Add `staleTime: 1000 * 60 * 2` on the `useCommunityPosts` hook (already set) but also add `refetchIntervalInBackground: false` so background tabs don't keep polling.

---

### PERF-07 — `get_stats` in `community_service` fires two sequential queries with no caching

**Severity:** P2
**File:** `backend/services/community_service.py`
**Lines:** 561–600

```python
stats_result = await db.execute(stats_sql, {"region": region})
# ...
top_result = await db.execute(top_tip_sql, {"region": region})
```

**Description:**
`get_stats` (called by the `CommunityStats` component on the Community page) executes two separate DB round-trips sequentially: one `COUNT(DISTINCT user_id)` aggregate and one `LEFT JOIN (GROUP BY post_id)` join. Neither result is cached. The `top_tip` query repeats the same unbounded vote-count join described in PERF-06. The `CommunityStats` component is rendered on every Community page mount.

**Fix:**
1. Merge both queries into a single CTE.
2. Cache the result in Redis with a 5-minute TTL keyed by `community_stats:{region}`.

```python
cache_key = f"community_stats:{region}"
cached = await redis.get(cache_key)
if cached:
    return json.loads(cached)
# ... compute ...
await redis.set(cache_key, json.dumps(result), ex=300)
```

---

## P3 Findings

---

### PERF-08 — `alert_history` `get_alert_history` runs a separate `COUNT(*)` query before the paginated SELECT

**Severity:** P3
**File:** `backend/services/alert_service.py`
**Lines:** 603–607

```python
count_result = await db.execute(
    text("SELECT COUNT(*) FROM alert_history WHERE user_id = :user_id"),
    {"user_id": user_id},
)
```

**Description:**
This is a sequential count-then-fetch pattern. The same issue exists in `savings_service.get_savings_history` (lines 156–161). While `PriceRepository.get_historical_prices_paginated` correctly runs the `COUNT` and `SELECT` in parallel via `asyncio.gather`, these two service methods do not. At high concurrency each alert history page request uses two serial DB round-trips instead of one parallel pair.

**Estimated impact:** Low, ~2–5 ms extra latency per request. Cumulative under load.

**Fix:**
Mirror the pattern in `PriceRepository.get_historical_prices_paginated` — run the count and the data query in `asyncio.gather`:

```python
count_result, rows_result = await asyncio.gather(
    db.execute(text("SELECT COUNT(*) FROM alert_history WHERE user_id = :user_id"), {"user_id": user_id}),
    db.execute(text("SELECT ... FROM alert_history WHERE user_id = :user_id ORDER BY triggered_at DESC LIMIT :limit OFFSET :offset"), {...}),
)
```

Apply the same fix to `SavingsService.get_savings_history`.

---

### PERF-09 — `useToggleVote` (VoteButton) invalidates the full community posts query on every vote

**Severity:** P3
**File:** `frontend/lib/hooks/useCommunity.ts`
**Lines:** 32–36

```typescript
onSuccess: () => {
  qc.invalidateQueries({ queryKey: ['community', 'posts'] })
},
```

**Description:**
`useToggleVote` and `useReportPost` both call `invalidateQueries` with the broad `['community', 'posts']` key on success. The `VoteButton` component already implements an optimistic update (lines 21–26 of `VoteButton.tsx`), so the backend response's `voted` and `upvote_count` fields are available in `onSuccess`. A targeted `setQueryData` using the returned counts would avoid the full re-fetch entirely.

**Fix:**

```typescript
onSuccess: (data, postId) => {
  qc.setQueryData<ApiCommunityPostsResponse>(
    ['community', 'posts', region, utilityType, page],
    (old) => {
      if (!old?.posts) return old
      return {
        ...old,
        posts: old.posts.map((p) =>
          p.id === postId ? { ...p, upvote_count: data.upvote_count } : p
        ),
      }
    }
  )
},
```

This requires passing `region`, `utilityType`, and `page` into the mutation context, which `useToggleVote` can receive as mutation variables.

---

### PERF-10 — `PriceLineChart` runs `parseISO` on every data point inside a `useMemo` but recomputes on every data reference change

**Severity:** P3
**File:** `frontend/components/charts/PriceLineChart.tsx`
**Lines:** 61–68

```typescript
const chartData = useMemo(() => {
  return data.map((point) => ({
    ...point,
    formattedTime: format(parseISO(point.time), 'HH:mm'),
    displayPrice: point.price ?? point.forecast,
  }))
}, [data])
```

**Description:**
`data` is created in `DashboardContent` via a `useMemo` that depends on `historyData` (line 63–74 of `DashboardContent.tsx`). Because `historyData` is a new reference on every React Query refetch, `chartData` is recomputed on each 60-second polling cycle even when the underlying values have not changed. For the 7-day range this means mapping 168 objects including a `parseISO` parse on every element every minute.

This is a minor cost but compounds with the SSE-triggered history invalidations described in PERF-05.

**Fix:**
Stabilise the `data` array reference in `DashboardContent` by including a primitive check. Alternatively, memoize the formatted data in `PriceLineChart` with a custom comparison that checks array length and last-item timestamp before recomputing:

```typescript
const prevDataRef = useRef<typeof data>([])
const chartData = useMemo(() => {
  const prev = prevDataRef.current
  if (prev.length === data.length && prev[prev.length - 1]?.time === data[data.length - 1]?.time) {
    return prev.map(...) // return cached
  }
  prevDataRef.current = data
  return data.map(...)
}, [data])
```

A simpler fix is to add `structuralSharing: true` (already the React Query default) and ensure the upstream `chartData` `useMemo` uses a stable key instead of creating new array entries for unchanged price values.

---

### PERF-11 — `ForecastService` SQL queries use string interpolation for the lookback interval (SQL injection vector doubles as a performance note)

**Severity:** P3 (performance; the injection risk is negligible since `TREND_LOOKBACK_DAYS` is a module constant, not user input)
**File:** `backend/services/forecast_service.py`
**Lines:** 119–120, 155–156

```python
f"AND timestamp >= NOW() - INTERVAL '{TREND_LOOKBACK_DAYS} days'"
```

**Description:**
Embedding the interval value as a literal string rather than as a parameterised value prevents PostgreSQL's query plan cache from recognising these as the same plan across calls with different constants. This is a minor concern since `TREND_LOOKBACK_DAYS` is a constant, but it is worth standardising.

**Fix:**
Use a parameterised interval:

```sql
AND timestamp >= NOW() - (INTERVAL '1 day' * :lookback_days)
```

with `params["lookback_days"] = TREND_LOOKBACK_DAYS`. PostgreSQL will then cache the plan.

---

## Index Gap Summary

The following indexes exist and cover the main hot paths:

| Table | Index | Query covered |
|---|---|---|
| `electricity_prices` | `idx_electricity_prices_region_utility_time (region, utility_type, timestamp DESC)` | Price lookups, history queries |
| `alert_history` | `idx_alert_history_dedup (user_id, alert_type, region, triggered_at DESC)` | Alert dedup checks |
| `price_alert_configs` | `idx_price_alert_configs_active_created (is_active, created_at) WHERE is_active` | check-alerts cron load |
| `community_posts` | `idx_community_posts_visible (region, utility_type, created_at DESC) WHERE visible` | list_posts query |

**Missing indexes identified:**

| Table | Recommended Index | Reason |
|---|---|---|
| `community_votes` | `idx_community_votes_post_id ON community_votes (post_id)` | list_posts GROUP BY subquery (PERF-06) |
| `community_reports` | `idx_community_reports_post_id ON community_reports (post_id)` | list_posts GROUP BY subquery (PERF-06) |
| `user_savings` | `idx_user_savings_created_amount ON user_savings (created_at, user_id, amount)` | SavingsAggregator rank query (PERF-04) |

---

## Items Already Well-Optimised (Not Needing Action)

The following patterns were reviewed and found to be correctly implemented:

- `PriceRepository.get_historical_prices_paginated`: parallel `COUNT` + `SELECT` via `asyncio.gather` — correct.
- `PriceRepository.get_current_prices`: Redis cache with stampede prevention lock (NX + px) — correct.
- `AnalyticsService.get_price_trend` / `get_peak_hours_analysis` / `get_supplier_comparison_analytics`: Redis caching with stampede locks, SQL aggregation in repository layer — correct.
- `AlertService.check_thresholds`: pre-groups prices by region O(n+m) — correct.
- `AlertService._batch_should_send_alerts`: batches dedup queries by cooldown tier (max 4 DB calls) — correct.
- `SavingsService.get_savings_summary`: single CTE with streak + aggregation — correct.
- `CommunityService.toggle_vote`: atomic INSERT ON CONFLICT CTE — correct.
- `CommunityService.report_post`: atomic INSERT + COUNT + UPDATE in one CTE — correct.
- `useRealtimePrices` SSE hook: `openWhenHidden: false`, exponential back-off, per-user connection limit (Redis-backed) — correct.
- `NotificationBell`: `refetchIntervalInBackground: false`, panel list only fetched when `open: true` — correct.
- `DashboardCharts`, `PriceLineChart`, `DashboardContent` sub-components: wrapped in `React.memo` — correct.
- `ForecastService._extrapolate_trend`: pure Python linear regression on already-fetched rows (fix target is the upstream fetch, not this function) — correct once PERF-02 fetch is fixed.
- `PriceService._simple_forecast` and `_ml_result_to_forecast`: runs in-process, ML prediction offloaded to thread pool via `asyncio.to_thread` — correct.
- `PriceService.get_price_forecast`: ML predictor loaded once at module level (`_ensemble_predictor` singleton) — correct.
- `get_user_alerts` in `AlertService`: no pagination needed (users have few alerts), direct single query — acceptable.

---

## Remediation Priority Order

1. **PERF-02** — Add `LIMIT` to `ForecastService` SQL queries immediately (1-line stopgap). Implement SQL `REGR_SLOPE`/`REGR_INTERCEPT` as follow-up. Add Redis cache.
2. **PERF-01** — Replace per-region loop in `check_alerts` with `ANY(:regions)` single query. Batch the history inserts.
3. **PERF-06** (index fix) — Add `idx_community_votes_post_id` and `idx_community_reports_post_id`. Apply as a migration 051.
4. **PERF-05** — Replace SSE `invalidateQueries` on history with `setQueryData` append.
5. **PERF-04** — Add Redis cache to `SavingsAggregator.get_combined_savings`. Add composite index.
6. **PERF-07** — Merge `get_stats` queries into one CTE; add Redis cache.
7. **PERF-03** — Cap `within_hours` and add explicit repo `limit` in `get_optimal_usage_windows`.
8. **PERF-08** — Parallelize count + rows queries in `alert_service` and `savings_service`.
9. **PERF-09** — Targeted `setQueryData` in vote/report mutations.
10. **PERF-10** — Stabilise `PriceLineChart` `useMemo` dependency.
11. **PERF-11** — Parameterise interval constant in forecast SQL.
