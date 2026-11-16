# Bug Pattern Audit — RateShift Codebase

**Audit Date**: 2026-03-18
**Auditor**: Debugger Agent (claude-sonnet-4-6)
**Scope**: `backend/`, `frontend/`, `ml/`, `workers/` — read-only
**Total Findings**: 28 bugs across 13 categories

---

## Severity Legend

| Level | Definition |
|-------|-----------|
| **P0 – Critical** | Data loss, security compromise, or production outage risk |
| **P1 – High** | Silent incorrect behavior affecting user data or business logic |
| **P2 – Medium** | Intermittent failures, degraded reliability under load |
| **P3 – Low** | Code smell, minor edge-case misbehavior, technical debt |

---

## P0 — Critical

### BUG-001 — Race Condition: Retroactive Moderation Appends to Shared List Concurrently

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/community_service.py`
**Lines**: 454–484
**Category**: Race Condition / Concurrency Bug

```python
async def classify_post(post) -> None:
    async with sem:
        ...
        if classification == "flagged":
            flagged_ids.append(str(post["id"]))  # Line 464

await asyncio.gather(*(classify_post(p) for p in posts))
```

**Why it's a bug**: `flagged_ids` is a plain `list` shared across all concurrent coroutines. Python's GIL prevents true simultaneous memory corruption on pure Python list appends, but the asyncio cooperative scheduler can switch context at any `await` point. In this case the semaphore release at `async with sem:` exit is an await point, meaning two coroutines can interleave classification and append in ways that produce duplicates or missed IDs under unusual scheduling. More critically, if `asyncio.gather` is used with `return_exceptions=True` in a future refactor and one coroutine modifies `flagged_ids` before raising, the partial state leaks. The real concern is the absence of any `asyncio.Lock` protecting the shared list — this pattern is fragile and will break if refactored to use threads or multiprocessing.

**Severity**: P0 — moderation results can silently be incomplete, allowing flagged content to remain visible.

**Fix**: Use a thread-safe collection or `asyncio.Queue`, or simply collect results via coroutine return values rather than shared mutation:

```python
async def classify_post(post) -> str | None:
    async with sem:
        classification = await agent_service.classify_content(...)
        return str(post["id"]) if classification == "flagged" else None

results = await asyncio.gather(*(classify_post(p) for p in posts))
flagged_ids = [r for r in results if r is not None]
```

---

### BUG-002 — Fail-Open Moderation: Content Published Before Classification Completes

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/community_service.py`
**Lines**: 97–113
**Category**: Race Condition / Logic Error

```python
try:
    await asyncio.wait_for(
        self._run_moderation(db, post_id, ...),
        timeout=MODERATION_TIMEOUT_SECONDS,  # 5 seconds
    )
except (asyncio.TimeoutError, Exception) as exc:
    logger.warning("moderation_timeout_or_failure", ...)
    await self._clear_pending_moderation(db, post_id)  # Makes post VISIBLE
```

**Why it's a bug**: The docstring says "fail-closed: posts start as is_pending_moderation=true" but the exception handler _fails-open_ by calling `_clear_pending_moderation` on **both timeout and any exception**, making the post immediately visible to all users. A 5-second timeout is very aggressive for two sequential LLM calls (Groq primary + Gemini fallback). Under normal network conditions for a rate-limited free-tier LLM API, the 5s window is easily exceeded, meaning every post that takes longer than 5s to classify silently bypasses moderation. Additionally, the `except (asyncio.TimeoutError, Exception)` clause is redundant — `Exception` already catches `TimeoutError` — and this suggests copy-paste rather than careful design.

**Severity**: P0 — toxic content can appear publicly if moderation times out.

**Fix**: On timeout, leave `is_pending_moderation=true` and schedule a background retry. Only fail-open after a configurable number of retry failures. Raise the timeout to at least 30s to match the documented CLAUDE.md value.

---

### BUG-003 — Integer Overflow: `Date.now()` Used as ID for Concurrent Operations

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/prices/PricesContent.tsx` line 47
**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/optimize/page.tsx` lines 99, 119
**Category**: Race Condition / ID Collision

```typescript
addPriceAlert({ id: Date.now().toString(), type, threshold, enabled: true })
addAppliance({ id: Date.now().toString(), ... })
```

**Why it's a bug**: `Date.now()` returns millisecond precision. If two appliances or alerts are added within the same millisecond (possible in automated tests, rapid double-clicks, or batch operations), they receive identical IDs. This can cause React rendering anomalies (duplicate `key` prop warnings, incorrect list updates), Zustand store conflicts (the second add overwrites the first), and broken delete/edit operations that match on ID.

**Severity**: P0 — silent data loss when two items share the same ID in the Zustand store.

**Fix**: Use `crypto.randomUUID()` (available in all modern browsers and Next.js) or a `nanoid` import that is already in the dependency tree.

---

## P1 — High

### BUG-004 — Error Swallowing: `asyncio.gather` with `return_exceptions=False` on Rate Scraper

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/rate_scraper_service.py`
**Line**: 190
**Category**: Error Swallowing / Concurrency

```python
raw_results: list[dict] = list(await asyncio.gather(*tasks, return_exceptions=False))
```

**Why it's a bug**: `return_exceptions=False` (the default) causes `asyncio.gather` to immediately cancel all remaining tasks and re-raise the first exception. `_scrape_one` wraps its logic in `try/except Exception`, so individual supplier errors are captured. However, if the asyncio framework itself raises (e.g., `CancelledError`, `KeyboardInterrupt`, or a `BaseException` subclass), the entire batch fails silently — the caller at line 190 would receive a partially-executed gather. Given the `finally` clause always sleeps `_RATE_LIMIT_SLEEP_S = 12` seconds inside the semaphore, a `BaseException` during sleep would propagate out of `_scrape_one` without being caught, since `BaseException` is not `Exception`.

**Severity**: P1 — task cancellation can corrupt the batch result or leave semaphore slots permanently held.

**Fix**: Change to `return_exceptions=True` and filter exceptions from results, or add `except BaseException` handling to `_scrape_one`.

---

### BUG-005 — Stale Closure: `useEffect` in `BillUploadForm` Closes Over Stale `connectionId`

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/BillUploadForm.tsx`
**Lines**: 100–158
**Category**: Stale Closure / React Hook

```typescript
const pollParseStatus = useCallback(
  async (uploadId: string) => {
    ...
    pollIntervalRef.current = setInterval(async () => {
      const res = await fetch(
        `${API_ORIGIN}/api/v1/connections/${connectionId}/uploads/${uploadId}`,
```

**Why it's a bug**: `connectionId` is a prop captured in the `useCallback` dependency array. The `setInterval` callback forms a closure over `uploadId` (a parameter) which is fine, but the interval callback also directly uses `connectionId` from the outer scope. If `connectionId` prop changes after the interval is started (e.g., parent component re-renders with a different connection), the polling continues fetching from the old connection ID because the interval callback holds a stale closure reference. The `useCallback` dependencies are `[connectionId, onUploadComplete]`, so a new callback is created when `connectionId` changes — but the already-running interval from the old callback still executes with the old URL.

**Severity**: P1 — polling continues against the wrong connection, returning data for a different upload session.

**Fix**: Use a ref for `connectionId` inside the interval callback, or clear and restart the interval when `connectionId` changes.

---

### BUG-006 — Null Dereference: `parseFloat` on Potentially Null Forecast Prices

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/DashboardContent.tsx`
**Lines**: 104–107
**Category**: Null Handling / Type Coercion

```typescript
const sum = prices
  .slice(i, i + 4)
  .reduce((s: number, p: ApiPrice) => s + parseFloat(p.price_per_kwh), 0)
```

**Why it's a bug**: `ApiPrice.price_per_kwh` is typed as a `Decimal` string from the backend. The backend schema shows it can be `null` (the `PricesContent.tsx` version on line 72 guards with `p.price_per_kwh != null`). In `DashboardContent.tsx` line 106, the reduce uses `parseFloat(p.price_per_kwh)` without a null check. `parseFloat(null)` returns `NaN`, which propagates through the reduce sum, making `minSum` become `NaN`, `bestStart` always 0, and the "optimal window" label always shows `"00:00 - 04:00"` regardless of actual prices.

**Severity**: P1 — silent incorrect optimal window displayed to all dashboard users when any forecast price is null.

**Fix**: Add a null guard: `s + (p.price_per_kwh != null ? parseFloat(p.price_per_kwh) : 0)`.

---

### BUG-007 — Division By Zero: `check_rate_anomaly` Callers Pass Zero `std_rate`

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/data_quality_service.py`
**Lines**: 226–243
**Category**: Boundary Condition / Division By Zero

```python
@staticmethod
def check_rate_anomaly(rate: float, avg_rate: float, std_rate: float) -> dict:
    if std_rate <= 0:
        return {"is_anomaly": False, "z_score": 0.0}
    z_score = abs(rate - avg_rate) / std_rate
```

**Why it's a bug**: While the zero-check is present, the return value of `{"is_anomaly": False, "z_score": 0.0}` silently suppresses anomaly detection for any dataset with zero variance (e.g., a region that always returns the same price from a cached static source). This means a genuine anomaly injected into such a dataset (e.g., a price spike when the cache breaks) will never be detected. The caller receives a false `is_anomaly: False` with no indication that the check was not performed.

**Severity**: P1 — anomaly detection silently disabled for stable-price regions without any log warning.

**Fix**: Add a `logger.warning("anomaly_check_skipped_zero_std", ...)` and return a distinct sentinel like `{"is_anomaly": None, "z_score": None, "skipped_reason": "zero_variance"}`.

---

### BUG-008 — Missing Null Check: `int(duration_hours)` Truncates Float Input

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/recommendations.py`
**Lines**: 57–59
**Category**: Type Coercion / Off-By-One

```python
result = await service.get_usage_recommendation(
    current_user.user_id, appliance, int(duration_hours)
)
```

**Why it's a bug**: `duration_hours` is declared as `float` with `ge=0.25, le=24`. A valid input of `0.25` (15 minutes) is converted to `int(0.25) = 0`, causing the service to compute appliance usage for 0 hours. The service receives `duration_hours=0`, multiplies by appliance kWh rate, returns `estimated_cost=0`, and produces a recommendation that is silently wrong (no cost, no energy use). Values like `0.5`, `0.75`, `1.5`, `2.75` all silently truncate.

**Severity**: P1 — incorrect recommendations for any fractional-hour appliance usage, with no error surfaced to the user.

**Fix**: Accept `duration_hours` as float throughout, or round to the nearest valid increment instead of truncating: `round(duration_hours, 2)`.

---

### BUG-009 — Error Swallowing: Exception in `analytics_service._get_cached` Masks Redis Issues

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/analytics_service.py`
**Lines**: 34–43, 45–52, 54–65
**Category**: Error Swallowing

```python
async def _get_cached(self, key: str) -> Optional[Dict]:
    if self._cache:
        try:
            cached = await self._cache.get(key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
    return None

async def _acquire_cache_lock(self, key: str, ttl_ms: int = 5000) -> bool:
    ...
    try:
        return bool(await self._cache.set(...))
    except Exception:
        return True  # Lock assumed acquired on error!
```

**Why it's a bug**: `_acquire_cache_lock` returns `True` (lock acquired) when Redis throws an exception. Under a Redis connection failure, every concurrent request will believe it holds the cache lock, defeat the stampede prevention, and all execute the expensive SQL computation simultaneously. This creates a thundering herd attack vector: when Redis fails, all cached analytics queries hit the database in parallel.

**Severity**: P1 — Redis connection failure causes database overload via thundering herd.

**Fix**: Return `False` (not acquired) when Redis fails to set the lock, causing callers to skip caching rather than assuming they own it.

---

### BUG-010 — Moderation Bypass When Gemini Fallback Unavailable

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/community_service.py`
**Lines**: 386–401 (the `moderate_post` private method, distinct from `_run_moderation`)
**Category**: Logic Error / Security

```python
try:
    ...
    classification = await agent_service.classify_content_groq(content)
except Exception:
    # Fallback to Gemini
    try:
        if hasattr(agent_service, "classify_content_gemini"):
            classification = await agent_service.classify_content_gemini(content)
    except Exception:
        # Both failed — clear pending moderation
        await self._clear_pending_moderation(db, post_id)
        return  # <-- post becomes visible without any moderation
```

**Why it's a bug**: When both Groq AND Gemini fail, `_clear_pending_moderation` is called, making the post visible with `is_hidden=False` and no `hidden_reason`. This is the same fail-open pattern as BUG-002 but in a different code path (`moderate_post` vs the timed create flow). Critically, when Groq fails and `hasattr(agent_service, "classify_content_gemini")` is `False`, `classification` remains `None` (from initialization at line 385). The code then falls through to the `if classification == "flagged":` check — `None != "flagged"` — so the `else` branch runs and sets `is_pending_moderation = false` (post becomes visible), without any exception being raised and without either AI system having classified anything.

**Severity**: P1 — posts can become public with `classification = None` treated as "not flagged."

**Fix**: Add an explicit check: `if classification is None: return  # leave pending`. Never fall through to the update when no classification was obtained.

---

### BUG-011 — Timezone-Naive Datetime in Production Database Queries

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/observation_service.py`
**Line**: 127
**File**: `/Users/devinmcgrath/projects/electricity-optimizer/ml/inference/ensemble_predictor.py`
**Line**: 229
**Category**: Date/Time Bug

```python
cutoff = datetime.utcnow() - timedelta(days=days)  # noqa: DTZ003 — intentional naive match
```

```python
self.version = datetime.utcnow().strftime("%Y%m%d")
```

**Why it's a bug**: `datetime.utcnow()` returns a naive (timezone-unaware) datetime. PostgreSQL `TIMESTAMPTZ` columns store timezone-aware values. When SQLAlchemy compares a naive Python datetime against a `TIMESTAMPTZ` column, PostgreSQL may perform an implicit coercion, but this behavior can differ between PostgreSQL versions and SQLAlchemy configurations. In `observation_service.py`, the `# noqa: DTZ003` suppression and the comment say "intentional naive match" — but this is fragile. If the database connection timezone changes from UTC to something else (e.g., server timezone set to US/Eastern in a Render environment change), the cutoff query silently archives different data than intended. In the ML module, naive datetimes in file metadata can cause incorrect model age calculations.

**Severity**: P1 — DST boundary or timezone config change silently archives wrong observation data range.

**Fix**: Use `datetime.now(timezone.utc)` consistently. The SQLAlchemy `TIMESTAMPTZ` column type handles timezone-aware datetimes correctly.

---

### BUG-012 — Resource Leak: `pollIntervalRef` Not Cleared on Upload Error

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/connections/BillUploadForm.tsx`
**Lines**: 105–157
**Category**: Resource Leak

```typescript
pollIntervalRef.current = setInterval(async () => {
    attempts++
    ...
    if (attempts >= maxAttempts) {
        clearInterval(pollIntervalRef.current)
        setParseResult({ status: 'failed', ... })
        return  // interval cleared
    }
    try {
        const res = await fetch(...)
        if (res.ok) {
            ...
            if (data.status === 'complete' || data.status === 'failed') {
                clearInterval(pollIntervalRef.current)  // cleared here too
            }
        }
        // If !res.ok, interval continues polling silently forever
    } catch {
        // Silently retry — interval NOT cleared on network error
    }
```

**Why it's a bug**: If the fetch returns a non-OK HTTP status (e.g., 401, 403, 500), the interval continues polling indefinitely because neither the `attempts >= maxAttempts` check nor the `data.status` check applies. The interval only stops after `maxAttempts` (60 attempts, 2 minutes) — but during that time the user may navigate away, the parent component is unmounted, and the `useEffect` cleanup clears `pollIntervalRef.current`. However, the `clearInterval` in the cleanup runs after unmount, and if the component re-mounts (e.g., tab switch), a new interval is created while the old one from the unmounted instance is still running (since the old ref is gone after unmount).

**Severity**: P1 — multiple polling intervals can run concurrently causing duplicate API calls and React state updates on unmounted components.

**Fix**: Set the interval ref to `null` after clearing, and add a mounted-check ref (`isMountedRef`) to guard all state updates inside the interval callback.

---

## P2 — Medium

### BUG-013 — Off-By-One: Optimal Window Uses Clock Hours Not Forecast Timestamps

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/DashboardContent.tsx`
**Lines**: 101–118
**Category**: Off-By-One / Logic Error

```typescript
const fmtHour = (h: number) => `${String(h % 24).padStart(2, '0')}:00`
return {
  startLabel: fmtHour(bestStart),      // "04:00"
  endLabel: fmtHour(bestStart + 4),    // "08:00"
  avgPrice: minSum / 4,
}
```

**Why it's a bug**: `bestStart` is an index into the `prices` array, not an actual clock hour. If the forecast array starts at 14:00 (the current time), then `bestStart=3` means 17:00, not 03:00. The `fmtHour` function treats the array index as if it were an hour number, displaying completely wrong window times. For example, if the cheapest 4-hour window starts at index 6 in a forecast that begins at noon, the UI shows "06:00–10:00" instead of "18:00–22:00".

**Severity**: P2 — users shown incorrect optimal usage windows.

**Fix**: Use the actual timestamp from `prices[bestStart].timestamp` and `prices[bestStart + 3].timestamp` to construct labels.

---

### BUG-014 — Regex DoS Risk: HTML Form Field Parser Uses Catastrophic Backtracking Pattern

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/portal_scraper_service.py`
**Lines**: 476–483
**Category**: Regex Denial of Service

```python
pattern = re.compile(
    r'<input[^>]+type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
pattern_alt = re.compile(
    r'<input[^>]+type=["\']hidden["\'][^>]*value=["\']([^"\']*)["\'][^>]*name=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
```

**Why it's a bug**: The pattern `[^>]+...[^>]*...[^>]*` applied to a long malformed HTML attribute string can exhibit exponential backtracking. Specifically, if a `<input` tag has many attributes and no `type=` match, the regex engine tries all combinations of `[^>]+` and `[^>]*` expansions. A crafted portal response with a long attribute string (e.g., `<input class="aaaa...aaaa" id="..." data-x="..."`) without a `type=hidden` can cause the match to take seconds to fail. Since portal HTML comes from untrusted third-party utility websites, this is an external input vector.

**Severity**: P2 — a slow or adversarial portal response can block a Python asyncio thread for seconds per scrape.

**Fix**: Use an HTML parser (Python's `html.parser` or `lxml`) instead of regex to extract form fields from untrusted HTML.

---

### BUG-015 — Type Coercion: `parseInt(timeRange)` Returns `NaN` for String Time Ranges

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/prices/PricesContent.tsx`
**Line**: 58
**Category**: Type Coercion

```typescript
const { data: historyData, isLoading: historyLoading } = usePriceHistory(
  region,
  parseInt(timeRange) || 24
)
```

**Why it's a bug**: `timeRange` is typed as `TimeRange` which includes values like `'7d'`, `'48h'`, `'24h'`. `parseInt('7d')` returns `7` (not `168`), `parseInt('24h')` returns `24` (coincidentally correct), and `parseInt('48h')` returns `48`. When `timeRange = '7d'`, the history query fetches only 7 hours of data instead of 7 days (168 hours). The `PricesContent` component handles `'7d'` but the adjacent `DashboardContent.tsx` correctly uses the `TIME_RANGE_HOURS` lookup table — making this an inconsistency between the two content components.

**Severity**: P2 — users selecting "7 days" on the prices page see only 7 hours of history.

**Fix**: Use the same `TIME_RANGE_HOURS` lookup table that `DashboardContent.tsx` uses at line 28–34.

---

### BUG-016 — Bare `except Exception` Silently Swallows DB Errors in GDPR Export

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/gdpr.py`
**Lines**: 558, 565, 568, 594, 624
**Category**: Error Swallowing

```python
except Exception:
    account_data["account_number"] = "(decryption failed)"
...
except Exception:
    account_data["meter_number"] = "(decryption failed)"
...
except Exception as e:
    logger.warning("supplier_accounts_export_failed", error=str(e))
...
except Exception as e:
    logger.warning("notifications_export_failed", error=str(e))
```

**Why it's a bug**: GDPR export is a legally regulated operation. If a database query fails (e.g., timeout, missing table, constraint error), the GDPR export continues and returns a partial dataset without the affected category. The user receives an export that appears complete but is missing their data. Under GDPR Article 20 (data portability), an incomplete export delivered without explicit notice of incompleteness may constitute a compliance violation.

**Severity**: P2 — users and regulators cannot distinguish a successful complete export from a partial one.

**Fix**: Collect all errors into an `export_errors` list and include it in the export response. Surface a warning to the user when their export is incomplete.

---

### BUG-017 — Memory Store Race Condition in Rate Limiter During Redis Outage

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py`
**Lines**: 266–300
**Category**: Race Condition / Concurrency

```python
def _check_memory(self, key: str, limit: int, window: int) -> tuple[bool, int]:
    now = time.time()
    window_start = now - window
    existing = self._memory_store.get(key)
    if existing is not None:
        self._memory_store[key] = [t for t in existing if t > window_start]
        ...
    self._memory_store.setdefault(key, []).append(now)
    request_count = len(self._memory_store[key])
```

**Why it's a bug**: In asyncio, the GIL prevents true thread-level races, but coroutine interleaving at `await` points is possible. However, `_check_memory` is synchronous (no `await`), so the GIL prevents interleaving within this function. The real issue is that in a **multi-worker Gunicorn setup** (which Render uses by default), `_memory_store` is not shared across workers. Each worker maintains an independent in-memory rate limit counter, so a user can make `limit * num_workers` requests before any single worker enforces a limit. The comment "single-worker safe" in the code acknowledges this but does not prevent it from being deployed in multi-worker mode.

**Severity**: P2 — rate limiting is ineffective during Redis outages in multi-worker deployments.

**Fix**: The docstring should explicitly document multi-worker limitations. A process-level advisory lock or a minimum Redis requirement for production should be enforced.

---

### BUG-018 — Lag Features Produce `NaN` Propagation Into Model Training

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/ml/data/feature_engineering.py`
**Lines**: 150–159, 380–444
**Category**: Null Handling / ML Data Quality

```python
def create_lag_features(self, df, target_col='price', lags=None):
    for lag in lags:
        df[f'{target_col}_lag_{lag}h'] = df[target_col].shift(lag)
    return df  # NaN values left in first `lag` rows

# Later in fit_transform:
self.scaler.fit(df_transformed[feature_cols].fillna(0))
```

**Why it's a bug**: Lag features introduce `NaN` for the first `max(lags)` rows. For a lag of 168 (1 week), the first 168 rows are entirely `NaN` for that feature. `fillna(0)` replaces these with 0 — which is not a missing-data sentinel but a semantically meaningful value (price = 0 $/kWh is physically impossible and would be a severe anomaly). The scaler then fits including these zero-filled rows, biasing the mean and variance. At inference time, `fillna(0)` produces equally biased inputs. The rolling_std features also produce `NaN` for windows smaller than `min_periods=1`, but in edge cases single-row windows can produce `NaN` std (rolling std with 1 observation is undefined).

**Severity**: P2 — model training data contains systematically biased values that reduce forecast accuracy.

**Fix**: Drop the first `max(lags)` rows from training data after feature generation, before fitting the scaler. Never use `fillna(0)` for lag features — use `fillna(df[target_col].median())` or explicitly drop.

---

### BUG-019 — Timezone-Naive `datetime.utcnow()` in ML Model Age Calculation

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/ml/inference/predictor.py`
**Line**: 257
**Category**: Date/Time Bug

```python
age_days = (datetime.utcnow() - self._trained_at).days
```

**Why it's a bug**: If `self._trained_at` is timezone-aware (loaded from a database `TIMESTAMPTZ` column or parsed from an ISO string with `+00:00`), subtracting a naive `datetime.utcnow()` raises `TypeError: can't subtract offset-naive and offset-aware datetimes`. This would crash the model version check, preventing inference entirely. If `self._trained_at` is naive (loaded from a file with `.isoformat()` without timezone), the subtraction works but only by coincidence — any future refactor to store timezone-aware datetimes would break it.

**Severity**: P2 — `TypeError` in production would crash all ML predictions for affected model versions.

**Fix**: Use `datetime.now(timezone.utc)` and ensure `self._trained_at` is always timezone-aware.

---

### BUG-020 — Partial Portal HTML Scrape: `_extract_hidden_fields` Regex Swaps Name/Value in Alternate Pattern

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/portal_scraper_service.py`
**Lines**: 486–489
**Category**: Logic Error / Off-By-One

```python
for match in pattern_alt.finditer(html):
    fields[match.group(2)] = match.group(1)  # name=group(2), value=group(1)
```

**Why it's a bug**: `pattern_alt` matches `value=[...] name=[...]` (value first, name second). Group 1 is the **value**, group 2 is the **name**. The assignment `fields[match.group(2)] = match.group(1)` is correct (name → value). However, since `pattern` matches `name=[...] value=[...]` (group 1 = name, group 2 = value) and assigns `fields[match.group(1)] = match.group(2)`, both assignments are internally consistent. The real bug is that if an attribute appears in both patterns, the `pattern_alt` result silently overwrites the `pattern` result, potentially replacing a correctly-captured value with a different one. The patterns are not mutually exclusive for all inputs.

**Severity**: P2 — CSRF tokens extracted as empty strings or wrong values will cause portal login to silently fail.

**Fix**: Use `pattern.finditer` and only fall back to `pattern_alt` for unmatched tags, not run both patterns unconditionally.

---

## P3 — Low

### BUG-021 — Missing `read_at` Field in Notification Bell Display

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/NotificationBell.tsx`
**Lines**: 9–15, 133–147
**Category**: Missing Null Check / UX

```typescript
interface Notification {
  id: string
  type: string
  title: string
  body: string | null
  created_at: string
  // read_at: NOT present in interface
}
```

**Why it's a bug**: The notification panel displays all fetched notifications without visual distinction between read and unread. The backend `/notifications` endpoint returns a `read_at` field (present in `notification_service.py` schema) but the frontend `Notification` interface omits it. Every notification in the dropdown appears identical regardless of read status, making "Mark all read" the only way to distinguish. This creates poor UX and can cause users to miss unread items.

**Severity**: P3 — UX degradation but no data integrity issue.

**Fix**: Add `read_at: string | null` to the interface and render unread notifications with a visual indicator (bold text or accent dot).

---

### BUG-022 — Error Swallowing in `referral_service.generate_code` Hides DB Errors

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/referral_service.py`
**Lines**: 41–60
**Category**: Error Swallowing

```python
for attempt in range(_MAX_RETRIES):
    try:
        await self._db.execute(...)
        await self._db.commit()
        return code
    except Exception:  # catches ALL exceptions, not just unique violations
        await self._db.rollback()
        if attempt == _MAX_RETRIES - 1:
            raise ReferralError("Failed to generate unique referral code")
```

**Why it's a bug**: The `except Exception` block catches any DB exception — including network timeouts, connection failures, and syntax errors — and retries them as if they were unique constraint violations. A database timeout on attempt 1 causes two more retries with a new random code each time, potentially inserting duplicate rows if the first transaction committed but the acknowledgement was lost in transit. The `rollback()` call on a disconnected session would itself raise, causing the outer `raise ReferralError(...)` to fire with no information about the real error.

**Severity**: P3 — misleading error message; potential for phantom inserts on network instability.

**Fix**: Catch `sqlalchemy.exc.IntegrityError` specifically for unique violations, and re-raise all other exceptions immediately.

---

### BUG-023 — `Date.now().toString()` ID Generation Not Monotonic Across DST Changes

**File**: Various frontend files
**Category**: Date/Time Bug

`Date.now()` in JavaScript returns milliseconds since the Unix epoch, which is monotonic. However, the `toString()` representation is a variable-length numeric string. Sorting or comparing these string IDs lexicographically (`"999" > "1000"` is `true` due to string comparison starting with `'9' > '1'`) can cause incorrect ordering in any code that compares IDs as strings rather than numbers. Zustand store operations finding items by ID use `===` equality which is fine, but any future sort or range query on these IDs would be incorrect.

**Severity**: P3 — low risk currently, but a time bomb for any feature that orders by ID.

---

### BUG-024 — Unguarded `response.text` Access in Portal Scraper Before Status Check

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/portal_scraper_service.py`
**Lines**: 364–367
**Category**: Null Handling

```python
login_page_resp = await client.get(effective_login_url)
hidden_fields = self._extract_hidden_fields(login_page_resp.text)
```

**Why it's a bug**: `login_page_resp.text` is accessed without checking the HTTP status code first. If the portal returns a 404, 503, or redirect to a JavaScript-rendered page, `login_page_resp.text` is the error page HTML, not a login form. `_extract_hidden_fields` then searches this error page for hidden inputs, finds none or finds error-page-specific inputs (e.g., CSRF tokens for an error reporting form), and the subsequent POST login step uses these wrong field values. The failure is silent — no exception, just a failed login at step 3 later.

**Severity**: P3 — portal scraping silently fails for any utility returning non-200 on the login page.

**Fix**: Add `login_page_resp.raise_for_status()` before accessing `.text`.

---

### BUG-025 — `console.log` in Production Code (Service Worker)

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/pwa/ServiceWorkerRegistrar.tsx`
**Lines**: 17–18
**Category**: Code Quality / Information Disclosure

```typescript
.then((reg) => {
  console.log('[SW] Registered:', reg.scope)
})
```

**Why it's a bug**: `console.log` in production exposes the service worker scope URL to browser developer tools, which can leak internal path information. While low severity on its own, it's indicative of debug code left in production paths. The `.catch` correctly uses `console.warn` which is appropriate for warnings, but the success path should use no logging in production.

**Severity**: P3 — minor information disclosure in browser console.

**Fix**: Remove the `console.log`, or gate it with `process.env.NODE_ENV !== 'production'`.

---

### BUG-026 — Unbounded Memory Growth: `_memory_store` Login Attempts Dict

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/middleware/rate_limiter.py`
**Lines**: 334–338
**Category**: Resource Leak

```python
if key not in self._memory_store:
    self._memory_store[key] = {"count": 0, "expires": 0}
self._memory_store[key]["count"] += 1
self._memory_store[key]["expires"] = time.time() + self.lockout_minutes * 60
```

**Why it's a bug**: Login attempt tracking uses a dict with structure `{"count": int, "expires": float}`. The periodic sweep at lines 284–291 only evicts keys where `isinstance(v, list)`, which excludes the login attempt entries (which are dicts). Login attempt entries are never evicted from memory, growing without bound for every unique email/IP that attempts a login. Under a credential stuffing attack with many unique identifiers, this dict grows indefinitely per worker process.

**Severity**: P3 — memory exhaustion over time under attack conditions.

**Fix**: Add eviction logic that also handles dict-type entries: evict when `isinstance(v, dict) and v.get('expires', 0) < now`.

---

### BUG-027 — `DashboardContent` Ignores `pricesError` and `forecastError`

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/dashboard/DashboardContent.tsx`
**Lines**: 43–57
**Category**: Error Swallowing / Null Handling

```typescript
const {
  data: pricesData,
  isLoading: pricesLoading,
  error: pricesError,       // destructured but...
} = useCurrentPrices(region)
...
const { data: forecastData, isLoading: forecastLoading, error: forecastError } = usePriceForecast(...)
```

**Why it's a bug**: `pricesError` and `forecastError` are destructured from React Query hooks but never used in the component render. When these queries fail, the component renders empty/null data without informing the user that an error occurred. The dashboard silently shows "no data" states which the user may interpret as legitimate (no prices for their region) rather than a connectivity error.

**Severity**: P3 — users cannot distinguish "no data" from "API error", leading to confusion.

**Fix**: Render an error alert when `pricesError` or `forecastError` is non-null.

---

### BUG-028 — Base64 Padding Applied Unconditionally to Gmail Attachment Data

**File**: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/email_scanner_service.py`
**Line**: 334
**Category**: String Encoding

```python
raw_data = att_resp.json().get("data", "")
file_bytes = base64.urlsafe_b64decode(raw_data + "==")
```

**Why it's a bug**: Gmail returns Base64URL-encoded data without padding. Adding `"=="` unconditionally compensates for missing padding — but if the data length modulo 4 is already 0 (correctly padded or no padding needed), the added `"=="` is stripped by the decoder silently. If the data length modulo 4 is 1 (invalid Base64), no amount of padding fixes the error and `binascii.Error` is raised. The correct approach is to calculate the correct padding. The silent "skip attachments that fail to download" `except Exception: continue` at line 340 masks any resulting `binascii.Error`.

**Severity**: P3 — some Gmail attachments silently fail to decode, causing missed bill rate extraction.

**Fix**: Use the standard padding calculation: `raw_data + "=" * (-len(raw_data) % 4)`.

---

## Summary Table

| ID | Severity | File | Category | One-Line Description |
|----|----------|------|----------|---------------------|
| BUG-001 | P0 | `community_service.py:464` | Race Condition | Shared list appended to concurrently across coroutines |
| BUG-002 | P0 | `community_service.py:104` | Logic Error | Moderation timeout fails-open, making unmoderated posts visible |
| BUG-003 | P0 | `PricesContent.tsx:47`, `optimize/page.tsx:99,119` | ID Collision | `Date.now()` as ID allows duplicates within same millisecond |
| BUG-004 | P1 | `rate_scraper_service.py:190` | Concurrency | `asyncio.gather` `return_exceptions=False` can abort entire batch |
| BUG-005 | P1 | `BillUploadForm.tsx:105` | Stale Closure | `setInterval` closes over stale `connectionId` prop |
| BUG-006 | P1 | `DashboardContent.tsx:106` | Null Handling | `parseFloat(null)` propagates `NaN` to optimal window calculation |
| BUG-007 | P1 | `data_quality_service.py:226` | Boundary | Zero-variance check silently disables anomaly detection |
| BUG-008 | P1 | `recommendations.py:58` | Type Coercion | `int(0.25)=0` makes fractional-hour appliance usage cost = $0 |
| BUG-009 | P1 | `analytics_service.py:52` | Error Swallowing | Cache lock failure returns `True`, causing thundering herd |
| BUG-010 | P1 | `community_service.py:393` | Security | `classification=None` treated as "not flagged", bypasses moderation |
| BUG-011 | P1 | `observation_service.py:127` | Date/Time | Naive UTC datetime in TIMESTAMPTZ query, breaks on timezone config change |
| BUG-012 | P1 | `BillUploadForm.tsx:105` | Resource Leak | Poll interval not cleared on non-OK HTTP response, runs indefinitely |
| BUG-013 | P2 | `DashboardContent.tsx:113` | Off-By-One | Array index used as clock hour for optimal window labels |
| BUG-014 | P2 | `portal_scraper_service.py:476` | Regex DoS | Nested `[^>]+` groups with catastrophic backtracking on malformed HTML |
| BUG-015 | P2 | `PricesContent.tsx:58` | Type Coercion | `parseInt('7d')=7` fetches 7 hours instead of 7 days |
| BUG-016 | P2 | `gdpr.py:558,565,568,594,624` | Error Swallowing | GDPR export silently partial when DB queries fail |
| BUG-017 | P2 | `rate_limiter.py:266` | Concurrency | In-memory rate limit not shared across Gunicorn workers |
| BUG-018 | P2 | `feature_engineering.py:156` | ML Data Quality | `fillna(0)` on lag features biases model training data |
| BUG-019 | P2 | `predictor.py:257` | Date/Time | Naive `utcnow()` vs timezone-aware `trained_at` causes `TypeError` |
| BUG-020 | P2 | `portal_scraper_service.py:489` | Logic Error | Both regex patterns run, second can overwrite first's results |
| BUG-021 | P3 | `NotificationBell.tsx:9` | Missing Field | `read_at` missing from interface; all notifications appear unread |
| BUG-022 | P3 | `referral_service.py:44` | Error Swallowing | All DB exceptions retried as unique violations |
| BUG-023 | P3 | Multiple frontend files | Date/Time | `Date.now().toString()` IDs don't sort lexicographically |
| BUG-024 | P3 | `portal_scraper_service.py:366` | Null Handling | Portal login page accessed without HTTP status check |
| BUG-025 | P3 | `ServiceWorkerRegistrar.tsx:17` | Info Disclosure | `console.log` exposes SW scope in production |
| BUG-026 | P3 | `rate_limiter.py:334` | Resource Leak | Login attempt dict never evicted from memory |
| BUG-027 | P3 | `DashboardContent.tsx:45` | Error Swallowing | `pricesError` and `forecastError` destructured but never rendered |
| BUG-028 | P3 | `email_scanner_service.py:334` | String Encoding | Unconditional `"=="` padding on Base64URL Gmail attachment data |

---

## Prevention Checklist

- [ ] Add ESLint rule `no-console` for production builds
- [ ] Add `mypy` strict mode to CI for `backend/services/` to catch `datetime` naive/aware mismatches
- [ ] Add `asyncio.Lock` linting or documentation requirement for any shared mutable state in coroutines
- [ ] Replace `Date.now().toString()` pattern with `crypto.randomUUID()` across all frontend ID generation
- [ ] Require explicit `read_at` field in all Notification-related TypeScript interfaces
- [ ] Enforce `raise_for_status()` before accessing `.text` or `.json()` in portal scraper HTTP calls
- [ ] Add property-based tests for `feature_engineering.py` with short time series to catch NaN propagation
- [ ] Gate GDPR export completeness with a response field `export_complete: bool` and `export_warnings: list`
