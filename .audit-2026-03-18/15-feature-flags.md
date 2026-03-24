# Audit Report 15: Feature Flags, Tier Gating, and Environment Toggles

**Date**: 2026-03-18
**Auditor**: Backend Developer Agent (read-only)
**Scope**: Feature flag system, subscription tier gating, and environment-based feature toggles across backend and frontend.
**Files audited**: `backend/api/dependencies.py`, `backend/config/settings.py`, `backend/middleware/rate_limiter.py`, `backend/auth/neon_auth.py`, `backend/api/v1/agent.py`, `backend/api/v1/billing.py`, `backend/api/v1/forecast.py`, `backend/api/v1/prices.py`, `backend/api/v1/prices_sse.py`, `backend/api/v1/prices_analytics.py`, `backend/api/v1/savings.py`, `backend/api/v1/recommendations.py`, `backend/api/v1/reports.py`, `backend/api/v1/export.py`, `backend/api/v1/alerts.py`, `backend/api/v1/connections/common.py`, `backend/services/agent_service.py`, `backend/services/stripe_service.py`, `backend/services/feature_flag_service.py`, `backend/services/alert_service.py`, `backend/services/dunning_service.py`, `frontend/middleware.ts`, `frontend/lib/hooks/useAuth.tsx`, `frontend/components/dashboard/DashboardForecast.tsx`, `frontend/components/connections/ConnectionsOverview.tsx`.

---

## Summary

The feature flag and tier gating system is architecturally sound with two complementary mechanisms: environment-variable feature flags (settings.py) and a database-driven `feature_flags` table (FeatureFlagService). The `require_tier()` dependency factory is consistently applied to all declared premium endpoints, and the free-tier alert limit uses an atomic row-level lock to prevent race conditions.

However, two significant bugs exist: (1) `invalidate_tier_cache()` is defined but **never called** after any tier-changing event (Stripe webhook, dunning downgrade), meaning stale tier data can persist in Redis and in-memory cache for up to 30 seconds after a subscription change; (2) the agent streaming endpoint double-counts usage, incrementing the counter both inside `query_streaming()` and at the `/task` call site. Three feature flags defined in `settings.py` (`enable_auto_switching`, `enable_load_optimization`, `enable_real_time_updates`) are completely dead code — they are never read anywhere outside settings.py.

---

## P0 — Critical

No P0 findings. No authentication or authorization bypass was found. All declared premium endpoints properly require authentication before tier checking.

---

## P1 — High Severity

### P1-01: Tier Cache Never Invalidated on Subscription Change

**File**: `backend/api/dependencies.py` lines 152–161; `backend/api/v1/billing.py` lines 384–418; `backend/services/stripe_service.py` lines 501–584; `backend/services/dunning_service.py` lines 280–302

**Description**: `invalidate_tier_cache(user_id)` is defined at `backend/api/dependencies.py:152` but is **never called** from any caller in the codebase. The grep of all files for `invalidate_tier_cache` yields exactly one hit: the function definition itself. This means that when a Stripe webhook fires (`checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`) and `apply_webhook_action()` writes the new `subscription_tier` to the database, the tier cache is not flushed. Similarly, when `DunningService.escalate_if_needed()` downgrades a user to `free` at `dunning_service.py:295`, the cache is not flushed.

**Impact**: After a subscription upgrade, a user may receive 403 responses for up to 30 seconds (the `_TIER_CACHE_TTL`) because `_get_user_tier()` returns the stale `free` value from Redis or the in-memory dict. After a downgrade, a canceled subscriber may continue to access premium endpoints for up to 30 seconds. With a business-tier downgrade to free, they retain SSE streaming access during the window.

**Evidence**:
```python
# backend/api/dependencies.py:152-161
async def invalidate_tier_cache(user_id: str) -> None:
    """Invalidate tier cache on subscription change (call from Stripe webhook)."""
    cache_key = f"tier:{user_id}"
    _tier_cache.pop(cache_key, None)
    redis = db_manager.redis_client
    if redis:
        try:
            await redis.delete(cache_key)
        except Exception:
            pass

# backend/api/v1/billing.py:398 — no call to invalidate_tier_cache
user_repo = UserRepository(db)
await apply_webhook_action(result, user_repo, db=db)
# <-- invalidate_tier_cache(result.get("user_id")) is never called here
```

**Recommendation**: Call `invalidate_tier_cache(user_id)` in `apply_webhook_action()` in `stripe_service.py` after writing the new tier to the database, and in `DunningService.escalate_if_needed()` after downgrading. Both require importing and awaiting the function.

---

### P1-02: Agent Usage Double-Counted on Streaming Queries

**File**: `backend/services/agent_service.py` lines 247–248; `backend/api/v1/agent.py` — no explicit increment call for streaming

**Description**: In `query_streaming()` at `agent_service.py:248`, `self.increment_usage(user_id, db)` is called unconditionally inside the generator after a successful response. This is correct for the streaming path. However, for the async task path (`/agent/task`), `increment_usage()` is called explicitly at `agent.py:219` AFTER `query_async()` starts the background task. The background task (`_run_async_job`) does NOT call `increment_usage`, so the task path counts once — correct.

The **actual bug** is a check/increment race in the streaming path: `check_rate_limit()` reads the current count with a no-op upsert at line 127–138, returning the pre-increment count. Then `query_streaming()` calls `increment_usage()` at line 248 only after the query completes. If a user sends N concurrent streaming requests before any completes, all N will pass `check_rate_limit()` (all read the same `current_count`), then all N will eventually call `increment_usage()`. The ON CONFLICT upsert in `increment_usage` is atomic per call but the check and increment are not atomic together. A user can exhaust their daily limit across concurrent requests.

**Evidence**:
```python
# agent_service.py:110-138 — reads count atomically but does NOT atomically increment
count_result = await db.execute(
    text("""
        INSERT INTO agent_usage_daily (user_id, date, query_count)
        VALUES (:user_id, CURRENT_DATE, 0)
        ON CONFLICT (user_id, date) DO UPDATE
            SET query_count = agent_usage_daily.query_count  -- no-op!
        RETURNING query_count
    """), {"user_id": user_id},
)
current_count = count_result.scalar() or 0
return current_count < limit, current_count, limit

# agent_service.py:247-248 — increment happens AFTER query completes
await self.increment_usage(user_id, db)
```

The pattern used for the original TOCTOU fix (PR context: "INSERT ... ON CONFLICT DO UPDATE SET count=count+1 RETURNING count") is **not applied here**. The check reads the pre-increment count with a no-op update, then increments separately. Concurrent requests will both read count=0 and both be allowed.

**Recommendation**: Merge `check_rate_limit()` and `increment_usage()` into a single atomic operation: `INSERT ... ON CONFLICT DO UPDATE SET query_count = agent_usage_daily.query_count + 1 RETURNING query_count` — then compare the returned post-increment count against the limit. If over limit, rollback or accept that one excess query went through but block future ones.

---

## P2 — Medium Severity

### P2-01: Three Feature Flags Are Dead Code (Never Read)

**File**: `backend/config/settings.py` lines 178–180

**Description**: Three feature flags are defined in `Settings` but are never read or evaluated by any service, API endpoint, or middleware:
- `enable_auto_switching` (default `False`) — line 178
- `enable_load_optimization` (default `True`) — line 179
- `enable_real_time_updates` (default `True`) — line 180

The `enable_auto_switching` field appears to relate to the `auto_switch_enabled` preference in the user model (`models/user.py:36`), but the backend setting is never checked. `enable_real_time_updates` presumably gates the SSE streaming endpoint, but `prices_sse.py` does not consult it. A thorough grep of all Python files confirms zero usages outside of settings.py.

**Impact**: If `enable_real_time_updates` were intended to gate real-time streaming, it is currently non-functional. An operator cannot disable SSE streaming via environment variable. Low immediate security risk but creates false confidence in operational controls.

**Recommendation**: Either wire these flags into the relevant code paths (checking `settings.enable_real_time_updates` in the SSE route, etc.) or remove them from `settings.py` to reduce confusion. Document which flags are operational vs. planned.

---

### P2-02: `require_paid_tier` in Connections Does Not Use Tier Cache

**File**: `backend/api/v1/connections/common.py` lines 111–135

**Description**: `require_paid_tier` performs a direct database query on every request:
```python
result = await db.execute(
    text("SELECT subscription_tier FROM public.users WHERE id = :uid"),
    {"uid": current_user.user_id},
)
```
Unlike `require_tier()` in `api/dependencies.py`, which uses a two-layer cache (Redis + in-memory, 30s TTL), `require_paid_tier` hits the database on every single connection-related API call. Connections endpoints are called frequently (connection lists, syncs, analytics). This is N+1 database queries for tier validation.

Additionally, `require_paid_tier` and `require_tier` are two separate implementations of the same concept, creating a maintenance surface. They will diverge over time (e.g., if the tier cache TTL changes, `require_paid_tier` won't benefit).

**Recommendation**: Refactor `require_paid_tier` to call `_get_user_tier()` from `api/dependencies.py` (which implements caching), then compare against `("pro", "business")`. This unifies the implementation and eliminates redundant DB queries.

---

### P2-03: Agent Streaming Does Not Check Tier for Business Unlimited Access

**File**: `backend/api/v1/agent.py` lines 95–167

**Description**: The `POST /agent/query` endpoint is gated only by `ENABLE_AI_AGENT` and the daily rate limit. It is not gated by `require_tier()`. The CLAUDE.md documents that the agent is rate-limited by tier (Free=3/day, Pro=20/day, Business=unlimited), and the `check_rate_limit()` implementation at `agent_service.py:119` returns `(True, 0, -1)` for business tier (unlimited).

However, the agent endpoint accepts queries from all authenticated users regardless of tier. A free user who exhausts their 3 daily queries still cannot access the agent (rate-limit returns 429), so access is functionally correct. But the feature is **not documented or signaled as a tier-gated premium feature** in the API response. A free user hitting the 429 receives: "Daily query limit reached (3/3)." There is no indication that upgrading to Pro gives 20 queries or Business gives unlimited.

More importantly: the endpoint does not verify that the tier is at least `free` (a trivial check, since all authenticated users are at least free). If the tier system ever adds a "suspended" pseudo-tier below free, this endpoint would still serve them.

**Recommendation**: Add a clear error message distinguishing tier-based limits vs. global rate limiting. Consider adding explicit tier documentation in the `429` response body. The current behavior is acceptable but could be more informative.

---

### P2-04: `GET /savings/combined` Not Tier-Gated (Asymmetry with `/summary` and `/history`)

**File**: `backend/api/v1/savings.py` lines 82–96

**Description**: `GET /savings/combined` uses `get_current_user` (authentication only), while `GET /savings/summary` and `GET /savings/history` use `require_tier("pro")`. The `/combined` endpoint returns combined savings across all utilities via `SavingsAggregator`. This is a meaningful data aggregation that arguably belongs in the same tier as `/summary` (pro-gated).

```python
# savings.py:86-96 — only requires authentication, not pro tier
@router.get("/combined")
async def get_combined_savings(
    current_user: SessionData = Depends(get_current_user),  # no require_tier
    db: AsyncSession = Depends(get_db_session),
):
```

**Impact**: A free-tier user can access combined multi-utility savings data while being blocked from the simpler `/summary` and `/history` endpoints. This is an intentional or accidental asymmetry that may expose value meant for paid tiers.

**Recommendation**: Determine if `/savings/combined` should require Pro tier. If it's intended to be a free teaser, document that decision explicitly. If not, add `require_tier("pro")` to match the other savings endpoints.

---

### P2-05: Price Analytics Endpoints Unauthenticated and Ungated

**File**: `backend/api/v1/prices_analytics.py` lines 50–239

**Description**: All four analytics endpoints (`/statistics`, `/optimal-windows`, `/trends`, `/peak-hours`) have no authentication dependency whatsoever — no `get_current_user`, no `require_tier`, not even an API key check. These endpoints return detailed statistical analyses including optimal usage windows and trend data.

```python
# prices_analytics.py:58-62 — no auth dependency
async def get_price_statistics(
    region: PriceRegion = Query(...),
    days: int = Query(7, ge=1, le=365),
    price_service: PriceService = Depends(get_price_service),
):
```

The pricing page declares that "Savings tracker & gamification" and "Historical price data" are Pro features, but these analytics endpoints expose comparable data to anonymous users. The `/optimal-windows` endpoint in particular returns optimal usage timing — data that the pricing page markets as a premium feature ("Smart schedule optimization").

**Impact**: Unauthenticated users can call these endpoints directly via the API, bypassing the frontend's paywall UI. This is a backend enforcement gap for what appears to be intended premium content.

**Recommendation**: At minimum, require authentication (`get_current_user`) for analytics endpoints. Consider whether `/optimal-windows` and `/trends` warrant `require_tier("pro")` to match the stated value proposition on the pricing page. `/statistics` could remain free to support the public rates SEO pages.

---

### P2-06: `FeatureFlagService.is_enabled()` Not Integrated with `require_tier()`

**File**: `backend/services/feature_flag_service.py` lines 26–72; `backend/api/dependencies.py` lines 164–194

**Description**: There are two parallel feature gate systems that do not interact:
1. The `require_tier()` dependency, which hard-codes gates in route definitions.
2. The `FeatureFlagService` (backed by a `feature_flags` database table), which supports global enable/disable, tier-gating, and percentage-based rollouts.

The `FeatureFlagService` is accessible via `PUT /internal/flags/{name}` and `GET /internal/flags`, but no production endpoint currently calls `FeatureFlagService.is_enabled()` in a request handler. The `savings_aggregator.py` has a test at line 143 (`test_combined_savings_skips_disabled_flags`) that mocks a feature flag check, suggesting the aggregator was meant to query flags — but the production `SavingsAggregator.get_combined_savings()` does not call `FeatureFlagService`.

**Impact**: The `feature_flags` table and admin API exist but provide no runtime behavior. Feature rollouts cannot be managed via this system. Changes to flags via `PUT /internal/flags/{name}` have no observable effect on user experience.

**Recommendation**: Wire `FeatureFlagService.is_enabled()` into at least one endpoint as a proof of concept (e.g., the savings aggregator), or document that the feature flags system is planned infrastructure and not yet operational.

---

## P3 — Low Severity / Informational

### P3-01: In-Memory Tier Cache Has Process-Level Scope

**File**: `backend/api/dependencies.py` lines 103–148

**Description**: The `_tier_cache` dict is a module-level Python dict:
```python
_tier_cache: dict[str, tuple[str, float]] = {}
```
In a multi-worker deployment (Render with Gunicorn workers), each process has its own `_tier_cache`. A tier change will be propagated to Redis (shared across workers) once `invalidate_tier_cache()` is called (currently never called — see P1-01), but each worker's in-memory dict will retain stale data until its own TTL expires. This is by design (in-memory as a Redis fallback), but means the effective stale window per worker is the full 30 seconds even after a Redis invalidation.

**Recommendation**: When P1-01 is fixed, confirm that invalidation flushes Redis. The in-memory dict will self-heal within 30 seconds. Accept this as a design trade-off, or reduce `_TIER_CACHE_TTL` to 10 seconds if subscription transitions need faster propagation.

---

### P3-02: `enable_ai_agent` Defaults to `False` — No Staging/Test Override Pattern

**File**: `backend/config/settings.py` lines 173–175

**Description**: `enable_ai_agent` defaults to `False`, requiring an explicit `ENABLE_AI_AGENT=true` environment variable. There is no staging-specific default or test-specific override pattern documented. The `model_validator` at line 355 only validates that `GEMINI_API_KEY` is set when the flag is enabled in production. In test environments, if `ENABLE_AI_AGENT` is not set, the agent endpoint returns `503` rather than a meaningful test skip.

```python
# settings.py:173
enable_ai_agent: bool = Field(default=False, validation_alias="ENABLE_AI_AGENT")
```

**Recommendation**: Document the required environment variables for staging and test environments. Consider a test helper that overrides settings for agent tests without requiring real API keys.

---

### P3-03: Frontend Tier Gating Is Entirely Reactive (No Proactive Prefetch)

**File**: `frontend/components/dashboard/DashboardForecast.tsx` lines 33–35; `frontend/components/connections/ConnectionsOverview.tsx` lines 46–68

**Description**: Frontend tier enforcement is implemented by catching 403 responses from the backend and rendering an upgrade prompt. This is the correct pattern (backend is authoritative), but the frontend does not proactively fetch the user's subscription tier to conditionally render or hide gated UI before the API call fires. Users on the free tier will always see an API request dispatched to `/prices/forecast`, `/savings/summary`, etc. before the upgrade prompt appears.

This creates unnecessary backend traffic and an observable loading spinner before the paywall appears. There is no `useTier()` hook or subscription state in the auth context or settings store.

**Evidence**:
```typescript
// DashboardForecast.tsx:34-35
const isTierGated =
  forecastError instanceof ApiClientError && forecastError.status === 403
```

**Recommendation**: Add `subscription_tier` to the user profile response from `GET /users/profile` (or a separate `GET /billing/subscription` call on app init). Store the tier in the Zustand settings store or React Query cache. Gate UI components proactively. This reduces wasted API calls and improves UX (no spinner before paywall).

---

### P3-04: No Tier Gate on `POST /agent/query` — Streaming Available to All Authenticated Users

**File**: `backend/api/v1/agent.py` lines 97–167

**Description**: CLAUDE.md states "Business tier: unlimited + SSE streaming." The SSE price stream at `/prices/stream` is correctly gated to `require_tier("business")`. However, `POST /agent/query` uses SSE (`StreamingResponse`) and is accessible to all authenticated users including free tier (just rate-limited to 3/day). The architecture description distinguishes "SSE streaming" as a business feature, but agent streaming is a separate concept (conversation streaming, not price streaming).

If the intent is that SSE streaming as a transport is a business feature, agent queries should also require business tier. If agent streaming is a separate feature available to all tiers, that is fine but should be explicitly documented.

**Recommendation**: Clarify whether agent SSE streaming counts as the "SSE streaming" feature listed in Business tier. If so, add `require_tier("business")` to `POST /agent/query` and offer polling-only access (`/agent/task` + `GET /agent/task/{job_id}`) to lower tiers.

---

### P3-05: `require_paid_tier` Returns 403 But Does Not Distinguish Pro vs Business

**File**: `backend/api/v1/connections/common.py` lines 111–135

**Description**: `require_paid_tier` checks `tier not in ("pro", "business")` and raises 403. The error detail is: "Connections require a Pro or Business subscription." This is correct. However, all connection endpoints — including analytics and portal scraping — are gated at the same "paid" level. If a future feature requires Business tier for connections, the existing `require_paid_tier` dependency would need replacement rather than modification.

**Recommendation**: Consider refactoring `require_paid_tier` as a thin wrapper over `require_tier("pro")` from `api/dependencies.py`. This keeps a single gating mechanism and allows easy escalation to `require_tier("business")` per endpoint if needed.

---

### P3-06: Dunning Downgrade Does Not Clear Tier Cache

**File**: `backend/services/dunning_service.py` lines 292–302

**Description**: When `escalate_if_needed()` downgrades a user to free, it calls `user_repo.update()` but does not call `invalidate_tier_cache()`. This is the same root issue as P1-01 but in a different code path. Even if P1-01 is fixed in the webhook handler, the dunning downgrade path remains uncovered.

```python
# dunning_service.py:295-296
user.subscription_tier = "free"
await user_repo.update(user_id, user)
# no invalidate_tier_cache(user_id) call
```

**Recommendation**: Add `invalidate_tier_cache(user_id)` call after the update in `escalate_if_needed()`. This requires importing the function from `api.dependencies`, which introduces a service-to-API dependency. Alternatively, move `invalidate_tier_cache` to a shared utility module (e.g., `lib/cache.py`) to avoid the circular import concern.

---

### P3-07: Free Tier Alert Limit Uses Row Lock But Not for Updates

**File**: `backend/services/alert_service.py` lines 696–717

**Description**: The free-tier alert limit (max 1 active alert) uses `SELECT ... FOR UPDATE` on the users table to prevent concurrent insert races:
```python
tier_result = await db.execute(
    text("SELECT subscription_tier FROM public.users WHERE id = :id FOR UPDATE"),
    {"id": user_id},
)
```
This is correct for the creation path. However, the `update_alert()` method at line 746 allows setting `is_active = True` on an existing alert without checking whether the user already has the maximum number of active alerts. A free-tier user could: (1) create 1 alert, (2) deactivate it (`is_active=False`), (3) create another alert (limit check only counts `is_active=TRUE`), then (4) reactivate the first one via `PUT /alerts/{id}` with `is_active: true`. This lets free users have 2 active alerts.

**Evidence**:
```python
# alert_service.py:768-772 — no tier limit check on update
allowed_fields = {
    "region", "currency", "price_below", "price_above",
    "notify_optimal_windows", "is_active",  # <-- is_active can be set True
}
```

**Recommendation**: Add a tier limit check in `update_alert()` when `is_active` is being set to `True`, similar to the check in `create_alert()`.

---

### P3-08: `GET /billing/subscription` Returns Tier from Stripe, Not Local DB

**File**: `backend/api/v1/billing.py` lines 259–321

**Description**: `GET /billing/subscription` fetches the tier from Stripe's API via `get_subscription_status()`, not from the local `public.users.subscription_tier` column. If Stripe is unavailable, this endpoint returns 500. More subtly, there could be a brief discrepancy between what the Stripe API returns and what the database holds (the webhook may not have been processed yet), which could confuse the frontend.

The `tier` field returned in `SubscriptionStatusResponse` comes from the Stripe subscription metadata, not the authoritative local DB column:
```python
# stripe_service.py:251-252
tier = subscription.metadata.get("tier", "unknown")
```
If the metadata is missing or stale on the Stripe side, this returns "unknown" for the tier.

**Recommendation**: Consider returning the tier from `public.users.subscription_tier` (the authoritative source) and use Stripe's subscription status for additional billing context (status, period end, cancel_at_period_end). This makes the billing status endpoint more resilient to Stripe API outages.

---

### P3-09: `ENABLE_AI_AGENT` Check in `/agent/query` Does Not Return Tier-Appropriate Error

**File**: `backend/api/v1/agent.py` lines 56–62

**Description**: When `ENABLE_AI_AGENT=false`, all four agent endpoints return `503 Service Unavailable`. A 503 is semantically for "service temporarily unavailable." In this context, the agent is intentionally disabled, not temporarily down. A 404 or 501 (Not Implemented) would better communicate intent. Additionally, authenticated pro/business users cannot distinguish "disabled globally" from "server error."

```python
def _require_agent_enabled():
    if not settings.enable_ai_agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI agent is not enabled. Set ENABLE_AI_AGENT=true to activate.",
        )
```

**Recommendation**: Return `404` or `501` when `ENABLE_AI_AGENT=false`, with a user-facing message that does not expose internal environment variable names in production. The detail string "Set ENABLE_AI_AGENT=true to activate" is an internal configuration hint that should not be visible to users.

---

### P3-10: Frontend Middleware Does Not Validate Session Token Authenticity

**File**: `frontend/middleware.ts` lines 72–96

**Description**: The Next.js middleware checks for the presence of `better-auth.session_token` or `__Secure-better-auth.session_token` cookies to determine if a user is authenticated for route protection. It does not validate the token — any non-empty string in that cookie will pass as "authenticated." This means a user could set a fake cookie value and bypass the frontend redirect to the login page.

```typescript
const sessionToken =
  request.cookies.get('better-auth.session_token')?.value ||
  request.cookies.get('__Secure-better-auth.session_token')?.value

if (isProtectedPath && !sessionToken) {
  // redirect to login
}
```

**Impact**: A user with a fake session token cookie can access protected page routes at the Next.js level. However, all actual data fetches will hit the backend which validates the token against `neon_auth.session` via `get_current_user()` and return 401. The user sees an authenticated page shell but no data. This is standard Next.js middleware behavior and is not a security vulnerability (backend is authoritative), but it is a UX concern.

**Recommendation**: This is acceptable and expected for Next.js middleware (token validation in middleware would require calling an external service on every request, which has significant performance implications). Document this as a known design trade-off. The backend is the authoritative gatekeeper.

---

## Findings Summary Table

| ID | Severity | Area | Title |
|----|----------|------|-------|
| P1-01 | High | Cache | Tier cache never invalidated on subscription change |
| P1-02 | High | Agent | Agent usage double-counted on concurrent streaming queries (TOCTOU) |
| P2-01 | Medium | Config | Three feature flags are dead code (never evaluated) |
| P2-02 | Medium | Auth | `require_paid_tier` bypasses tier cache, hits DB on every request |
| P2-03 | Medium | Agent | Agent streaming endpoint tier ambiguity (all tiers access SSE) |
| P2-04 | Medium | Savings | `GET /savings/combined` not tier-gated, asymmetric with summary/history |
| P2-05 | Medium | Auth | Price analytics endpoints are fully unauthenticated and ungated |
| P2-06 | Medium | Flags | `FeatureFlagService` not wired into any production endpoint |
| P3-01 | Low | Cache | In-memory tier cache process-scoped in multi-worker deployment |
| P3-02 | Low | Config | `ENABLE_AI_AGENT` has no staging/test override pattern |
| P3-03 | Low | Frontend | Frontend tier gating is entirely reactive (no proactive tier prefetch) |
| P3-04 | Low | Agent | Agent SSE streaming not explicitly scoped to business tier |
| P3-05 | Low | Auth | `require_paid_tier` does not support future Business-only connections |
| P3-06 | Low | Dunning | Dunning downgrade does not clear tier cache |
| P3-07 | Low | Alerts | Free-tier alert limit bypassable via update reactivation |
| P3-08 | Low | Billing | `GET /billing/subscription` reads tier from Stripe metadata, not local DB |
| P3-09 | Low | Agent | `ENABLE_AI_AGENT=false` returns 503 with internal config detail in message |
| P3-10 | Low | Frontend | Frontend middleware authenticates by cookie presence, not validity |

---

## Verified Correct Behaviors

The following areas were audited and found to be correctly implemented:

1. **`require_tier()` factory** (`api/dependencies.py:164-194`): Correctly chains `get_current_user` → DB tier lookup → comparison using `_TIER_ORDER`. Business tier satisfies pro requirements (`_TIER_ORDER = {"free": 0, "pro": 1, "business": 2}`).

2. **Tier gate coverage on declared premium endpoints**:
   - `GET /prices/forecast` — `require_tier("pro")` at `prices.py:330`
   - `GET /forecast/{utility_type}` — `require_tier("pro")` at `forecast.py:25`
   - `GET /forecast` (list) — `require_tier("pro")` at `forecast.py:60`
   - `GET /savings/summary` — `require_tier("pro")` at `savings.py:31`
   - `GET /savings/history` — `require_tier("pro")` at `savings.py:60`
   - `GET /recommendations/switching` — `require_tier("pro")` at `recommendations.py:24`
   - `GET /recommendations/usage` — `require_tier("pro")` at `recommendations.py:52`
   - `GET /recommendations/daily` — `require_tier("pro")` at `recommendations.py:84`
   - `GET /prices/stream` (SSE) — `require_tier("business")` at `prices_sse.py:177`
   - `GET /export/rates` — `require_tier("business")` at `export.py:31`
   - `GET /export/types` — `require_tier("business")` at `export.py:74`
   - `GET /reports/optimization` — `require_tier("business")` at `reports.py:23`
   - All `/connections/*` endpoints — `require_paid_tier` (pro or business) via `common.py:111`

3. **Free-tier alert limit** (`alert_service.py:696-717`): Uses `SELECT ... FOR UPDATE` to atomically check tier and count before inserting. Raises `PermissionError` converted to 403 in the API layer.

4. **Agent rate limit TOCTOU-safe check** (`agent_service.py:127-138`): Uses upsert with no-op update to ensure row exists, then reads `query_count`. Concurrent requests may race (see P1-02), but the check itself is atomic per row.

5. **Stripe webhook tier transitions** (`stripe_service.py:413-425`): Correctly only forces `free` for terminal states (`canceled`, `unpaid`), preserving tier for `trialing`/`past_due`/`incomplete`.

6. **Session cache invalidation on logout** (`auth/neon_auth.py:130-144`): `invalidate_session_cache()` is called correctly from the logout endpoint.

7. **ENABLE_AI_AGENT validation** (`settings.py:355-365`): `model_validator` correctly raises `ValueError` if the flag is enabled in production without `GEMINI_API_KEY`.

8. **Agent tier override prevention** (`agent.py:123-128`): User-supplied `context` cannot override `tier` or `user_id` — these are always sourced from the authenticated session and database.

9. **Redis Lua sliding-window rate limiter** (`middleware/rate_limiter.py:42-65`): Correctly expires the `:seq` counter key with the same TTL as the main key (previous bug from Quality Hardening Sprint was fixed).

10. **Frontend middleware route protection** (`middleware.ts:77-91`): All 15 protected paths are enumerated; unauthenticated access redirects to `/auth/login` with `callbackUrl` preserved.

11. **Frontend paywall rendering** (`DashboardForecast.tsx:34-86`, `ConnectionsOverview.tsx:66-68`): Frontend correctly renders upgrade CTAs on 403 responses. No client-side bypass of tier checks — all actual data gating is backend-enforced.

---

## Appendix: Feature Flag Inventory

### Environment-Variable Flags (settings.py)

| Flag | Default | Currently Enforced? | Notes |
|------|---------|---------------------|-------|
| `ENABLE_AI_AGENT` | `false` | YES — `_require_agent_enabled()` checks it | Correct |
| `ENABLE_AUTO_SWITCHING` | `false` | NO — never read outside settings.py | Dead code (P2-01) |
| `ENABLE_LOAD_OPTIMIZATION` | `true` | NO — never read outside settings.py | Dead code (P2-01) |
| `ENABLE_REAL_TIME_UPDATES` | `true` | NO — never read outside settings.py | Dead code (P2-01) |

### Database Feature Flags (feature_flags table via FeatureFlagService)

The `feature_flags` table supports: `name`, `enabled`, `tier_required`, `percentage`, `description`, `updated_at`.

Admin API: `GET /internal/flags`, `PUT /internal/flags/{name}` (both require `X-API-Key`).

**Currently wired into production code**: NONE. The `FeatureFlagService` class exists and is correct, but zero production request handlers call `is_enabled()`. See P2-06.

### Tier Ordering

| Tier | Level | Agent Limit | Alerts |
|------|-------|-------------|--------|
| `free` | 0 | 3/day (`AGENT_FREE_DAILY_LIMIT`) | 1 active |
| `pro` | 1 | 20/day (`AGENT_PRO_DAILY_LIMIT`) | Unlimited |
| `business` | 2 | Unlimited | Unlimited |

Default values from `settings.py:174-175`. These are configurable via environment variables without code changes.
