# Audit Report: Feature Flags & Tier Gating
**Date:** 2026-03-23
**Scope:** Tier system, require_tier(), feature flags, rate limiting by tier
**Files Reviewed:**
- `backend/api/dependencies.py` (lines 1-314)
- `backend/api/v1/agent.py` (lines 1-275)
- `backend/api/v1/alerts.py` (lines 1-275)
- `backend/api/v1/billing.py` (lines 1-524)
- `backend/api/v1/connections/common.py` (lines 1-133)
- `backend/api/v1/connections/crud.py` (lines 1-300)
- `backend/api/v1/connections/analytics.py` (lines 1-116)
- `backend/api/v1/connections/rates.py` (lines 1-171)
- `backend/api/v1/connections/direct_sync.py` (lines 1-160)
- `backend/api/v1/connections/email_oauth.py` (lines 1-60)
- `backend/api/v1/connections/bill_upload.py` (lines 1-50)
- `backend/api/v1/connections/portal_scrape.py` (lines 37-164, via grep)
- `backend/api/v1/export.py` (lines 1-82)
- `backend/api/v1/forecast.py` (lines 1-67)
- `backend/api/v1/neighborhood.py` (lines 1-50)
- `backend/api/v1/prices.py` (lines 1-520)
- `backend/api/v1/prices_analytics.py` (lines 1-268)
- `backend/api/v1/prices_sse.py` (lines 1-254)
- `backend/api/v1/public_rates.py` (lines 1-196)
- `backend/api/v1/recommendations.py` (lines 1-103)
- `backend/api/v1/reports.py` (lines 1-35)
- `backend/api/v1/savings.py` (lines 1-96)
- `backend/api/v1/community.py` (lines 1-50)
- `backend/api/v1/internal/operations.py` (lines 1-217)
- `backend/api/v1/internal/billing.py` (lines 1-104)
- `backend/config/settings.py` (lines 195-416)
- `backend/services/agent_service.py` (lines 1-432)
- `backend/services/alert_service.py` (lines 640-740)
- `backend/services/feature_flag_service.py` (lines 1-127)
- `backend/services/stripe_service.py` (lines 1-833)
- `backend/tests/test_tier_gating.py` (lines 1-401)
- `backend/tests/test_premium_tier_gating.py` (lines 1-20)

---

## P0 -- Critical (Fix Immediately)

### P0-01: Agent Rate Limit Check-Then-Act Race Condition in `/agent/query` Streaming Endpoint

**File:** `backend/api/v1/agent.py`, lines 136-164
**File:** `backend/services/agent_service.py`, lines 120-163

**Description:** In the `/agent/query` endpoint, the rate limit is checked at line 137 via `check_rate_limit()`, and usage is incremented later inside `query_streaming()` at `agent_service.py:264`. The `check_rate_limit()` method at `agent_service.py:137-148` performs an INSERT ... ON CONFLICT DO UPDATE with a no-op SET, then checks if `current_count < limit`. However, this INSERT does **not** increment the counter -- it merely ensures the row exists and returns the current count. The actual increment happens separately in `increment_usage()` at line 264 (inside `query_streaming()`).

This means two concurrent requests from the same user can both pass the rate limit check (both read count=2 when limit=3), and both proceed to execute. The second request's increment brings count to 4, exceeding the limit of 3. The atomic upsert pattern only prevents the row from not existing; it does not atomically check-and-increment.

Compare this to the `/agent/task` endpoint at lines 210-226, where `check_rate_limit()` is called and then `increment_usage()` is called immediately at line 226 -- but these are also two separate operations with the same TOCTOU window.

**Impact:** Free-tier users (limit=3/day) could exceed their daily query limit via concurrent requests. Business-tier users are unlimited and unaffected. Pro-tier users (limit=20/day) have a wider window but the race still applies.

**Recommendation:** Change `check_rate_limit()` to atomically increment and check in a single statement:
```sql
INSERT INTO agent_usage_daily (user_id, date, query_count)
VALUES (:user_id, CURRENT_DATE, 1)
ON CONFLICT (user_id, date) DO UPDATE
    SET query_count = agent_usage_daily.query_count + 1
RETURNING query_count
```
Then check if `returned_count > limit`. If so, decrement back (or use a CTE with conditional increment). This eliminates the window between check and increment.

---

### P0-02: `require_paid_tier` Does Not Use the Tier Cache, Hits DB on Every Request

**File:** `backend/api/v1/connections/common.py`, lines 108-132

**Description:** The `require_paid_tier` dependency queries `public.users.subscription_tier` directly via raw SQL on every request (line 120-123). It does not use the `_get_user_tier()` function from `backend/api/dependencies.py` (which implements the 30s Redis + in-memory cache). Every connection-related endpoint (approximately 25 endpoints across 6 sub-modules) pays the cost of a DB query on every request, even though the tier value changes only on subscription events.

Additionally, `require_paid_tier` is a separate implementation from `require_tier("pro")` -- it uses a different code path, different SQL query (`:uid` vs `:id` parameter name), and does not benefit from `invalidate_tier_cache()` called by webhooks.

**Impact:** Increased DB load on every connections API call. More critically, there is a consistency gap: after a Stripe webhook downgrades a user to `free`, `invalidate_tier_cache()` invalidates the cache used by `require_tier()`, but `require_paid_tier()` will continue to serve stale data from the DB's read replica (if any) or see the correct value immediately. The semantic inconsistency between two parallel tier-checking codepaths is a maintenance hazard and potential security gap.

**Recommendation:** Replace `require_paid_tier` with `require_tier("pro")` from `backend/api/dependencies.py`. This centralizes tier logic, uses the cache, and benefits from webhook-driven invalidation. If the error message needs to differ ("Connections require a Pro or Business subscription"), customize it via a parameter.

---

## P1 -- High (Fix This Sprint)

### P1-01: In-Memory Tier Cache `_tier_cache` Grows Without Bound

**File:** `backend/api/dependencies.py`, line 96

**Description:** The `_tier_cache` dictionary at line 96 stores `{cache_key: (tier, expiry_time)}` entries for every user who triggers a tier check. Entries are added at line 140 and only removed by explicit `invalidate_tier_cache()` calls (line 148) or by TTL expiry (line 119-120 checks `now < expires` but never deletes expired entries). Expired entries remain in the dict until the same user triggers another lookup, at which point the stale entry is overwritten. For users who query once and never return, the entry persists forever.

In a long-running Gunicorn/Uvicorn worker, this dict will grow monotonically with the number of unique users. For a SaaS product expecting thousands of users, this is a memory leak.

**Impact:** Gradual memory growth in backend workers proportional to total unique users, not active users. On Render's 512MB free tier, this could eventually trigger OOM restarts.

**Recommendation:** Add periodic eviction. Options:
1. Use an LRU cache (`functools.lru_cache` or `cachetools.TTLCache`) with a max size.
2. Add a background task that sweeps expired entries every N minutes.
3. At minimum, delete expired entries when encountered (change the TTL check to also `del _tier_cache[cache_key]` when expired).

### P1-02: `ENABLE_AI_AGENT=false` Error Message Leaks Internal Configuration Detail

**File:** `backend/api/v1/agent.py`, lines 59-65

**Description:** When `ENABLE_AI_AGENT` is `false`, all four agent endpoints return HTTP 503 with the detail message: `"AI agent is not enabled. Set ENABLE_AI_AGENT=true to activate."` This message exposes the internal environment variable name to any authenticated user who calls the endpoint. In production, users should not see configuration instructions.

**Impact:** Information disclosure -- attackers learn the feature flag mechanism and exact variable name. HTTP 503 semantics are also incorrect for a deliberately disabled feature (503 implies temporary unavailability; the agent is intentionally off).

**Recommendation:** Return `404 Not Found` or `501 Not Implemented` with a user-friendly message like `"This feature is not currently available."` Remove the environment variable name from the detail string in production (could conditionally include it in development mode for debugging).

### P1-03: Agent Endpoints Bypass `require_tier()` -- No Tier Gating on Agent API

**File:** `backend/api/v1/agent.py`, lines 107-110, 183-186, 237-239, 257-259

**Description:** All four agent endpoints use `get_current_user` for authentication but do NOT use `require_tier()` for tier gating. Instead, they implement a custom tier check via a separate `_get_user_tier()` function at line 68-76 and enforce limits through `check_rate_limit()` in `agent_service.py`. While the rate limit does differentiate by tier (Free=3/day, Pro=20/day, Business=unlimited), free-tier users are NOT blocked from using the agent -- they get 3 queries per day.

The CLAUDE.md states "Rate limits: Free=3/day, Pro=20/day, Business=unlimited" which implies free-tier access is intentional. However, the agent API is the most expensive feature (calls external Gemini/Groq APIs that have real costs). Giving free users 3 queries/day means any signup immediately creates API cost.

**Impact:** Every free-tier signup can consume 3 Gemini API calls per day with zero revenue. At scale, this could create significant API costs. The cost asymmetry (free user generates real API spend) is a business risk, not a bug per se, but it is worth flagging as a deliberate product decision that should be documented.

**Recommendation:** This is a product decision, not a code bug. However:
1. Confirm this is intentional with product/business stakeholders.
2. If free-tier agent access is intentional, add a comment in `agent.py` documenting why `require_tier()` is deliberately omitted.
3. Consider adding `require_tier("pro")` if the intent is that the agent is a paid feature.

### P1-04: Duplicate `_get_user_tier()` Implementation in Agent Module

**File:** `backend/api/v1/agent.py`, lines 68-76
**File:** `backend/api/dependencies.py`, lines 100-142

**Description:** The agent module defines its own `_get_user_tier()` function at line 68 that queries the `users` table directly without any caching. The canonical implementation in `dependencies.py` at line 100 includes Redis + in-memory caching with 30s TTL. The agent's version:
1. Hits the database on every call (no cache).
2. Does not benefit from `invalidate_tier_cache()` called by Stripe webhooks.
3. Has a separate `_get_user_context()` function at line 79 that queries both region and tier in a single query, but this is also uncached.

Both the query endpoint (line 131) and the task endpoint (line 206) call both `_get_user_context()` AND `_get_user_tier()`, resulting in **two** DB queries for tier information per request (one in `_get_user_context` at line 84 and one in `_get_user_tier` at line 72).

**Impact:** Each agent request makes 2 unnecessary DB queries for tier data that could be served from cache. At Free=3/day this is low impact, but at Business=unlimited it could add up.

**Recommendation:** Replace the agent module's `_get_user_tier()` with the cached version from `dependencies.py`. Merge the `_get_user_context()` call to use the cached tier value instead of re-querying.

### P1-05: `_TIER_ORDER` Dictionary Duplicated Across Three Locations

**File:** `backend/api/dependencies.py`, line 93
**File:** `backend/services/feature_flag_service.py`, line 19
**File:** `backend/api/v1/connections/common.py`, line 127 (implicit via string comparison)

**Description:** The tier ordering `{"free": 0, "pro": 1, "business": 2}` is defined independently in `dependencies.py` and `feature_flag_service.py`. The `require_paid_tier` in `connections/common.py` uses a string comparison (`tier not in ("pro", "business")`) which is equivalent but not using the shared constant. If a fourth tier is added (e.g., "enterprise"), all three locations must be updated independently.

**Impact:** Maintenance risk -- adding a new tier requires changes in 3+ locations. The current code is consistent, so no active bug exists.

**Recommendation:** Extract `_TIER_ORDER` into a shared location (e.g., `backend/models/tier.py` or `backend/config/tiers.py`) and import it everywhere. Also add a `is_paid_tier()` helper to replace the string comparisons.

### P1-06: Feature Flag `tier_required` Input Not Validated Against Valid Tiers

**File:** `backend/api/v1/internal/operations.py`, lines 28-31
**File:** `backend/services/feature_flag_service.py`, lines 92-126

**Description:** The `FlagUpdateBody` model at line 30 accepts any string for `tier_required` -- there is no validation that it must be one of `"free"`, `"pro"`, or `"business"`. The `update_flag()` method at `feature_flag_service.py:122` writes the value directly to the database. A typo like `tier_required="Pro"` (capitalized) or `tier_required="premium"` would silently create a flag that no user can satisfy, because `_TIER_ORDER.get("Pro", 0)` returns 0 (same as free), and `_TIER_ORDER.get("premium", 0)` also returns 0.

**Impact:** An operator could accidentally set a flag with an invalid tier name, causing the flag to behave unexpectedly (either too permissive or too restrictive depending on the misspelling).

**Recommendation:** Add a validator to `FlagUpdateBody`:
```python
tier_required: str | None = Field(None, pattern=r"^(free|pro|business)$")
```

---

## P2 -- Medium (Fix Soon)

### P2-01: `GET /savings/combined` Missing Tier Gate -- Inconsistent with `/savings/summary` and `/savings/history`

**File:** `backend/api/v1/savings.py`, lines 85-95

**Description:** The `/savings/summary` endpoint (line 30) and `/savings/history` endpoint (line 59) both use `require_tier("pro")`. However, `/savings/combined` at line 87 uses only `get_current_user` with no tier gating. This endpoint returns "combined savings across all utility types" which is arguably the same class of premium data.

**Impact:** Free-tier users can access combined savings data that should require a Pro subscription. This is either a bypass or an intentional design choice for a less-detailed summary view.

**Recommendation:** If this is premium data, add `require_tier("pro")`. If it is intentionally free (e.g., as a teaser), add a code comment explaining the product decision.

### P2-02: `GET /prices/current`, `/prices/history`, `/prices/compare` Are Unauthenticated -- Design Decision Undocumented

**File:** `backend/api/v1/prices.py`, lines 93-98, 192-215, 413-416

**Description:** The `/prices/current`, `/prices/history`, and `/prices/compare` endpoints require no authentication at all -- they use `get_price_service` directly without any auth dependency. Only `/prices/forecast` uses `require_tier("pro")`. This means anyone (including unauthenticated users) can access current prices, full history (up to 365 days), and supplier comparisons.

Meanwhile, all four analytics endpoints (`/statistics`, `/optimal-windows`, `/trends`, `/peak-hours`) in `prices_analytics.py` require `require_tier("pro")`.

**Impact:** The free data (current prices, history, comparisons) is the core value proposition. If this is intentional (freemium model where basic data is free, analytics are paid), it should be documented. If history access is supposed to be limited for free users, this is a bypass.

**Recommendation:** This appears intentional based on the free-tier design. Add a comment in `prices.py` explaining that these endpoints are intentionally public/unauthenticated as part of the freemium model.

### P2-03: Feature Flags in Settings Are Not Wired to Any Runtime Check

**File:** `backend/config/settings.py`, lines 214-220

**Description:** Three feature flags are defined in settings:
- `enable_auto_switching` (default `False`)
- `enable_load_optimization` (default `True`)
- `enable_real_time_updates` (default `True`)

A grep for these flag names across the entire backend shows they are ONLY defined in `settings.py` and never referenced anywhere in the API layer or service layer. They exist as configuration but are completely inert -- no code path checks them.

**Impact:** These are dormant flags. If the features they are supposed to gate are already implemented without checking the flag, the flags serve no purpose. If the features are not yet implemented, the flags are premature configuration.

**Recommendation:** Either wire these flags into the relevant code paths or remove them from settings to reduce confusion. The CLAUDE.md pattern "Dormant API config: define key in settings.py... don't wire into services (instant activation later)" suggests this is intentional, but the flags should have comments indicating their dormant status and planned usage.

### P2-04: Alert Limit Hardcoded to 1 for Free Tier -- Not Configurable

**File:** `backend/services/alert_service.py`, line 718

**Description:** The free-tier alert limit is hardcoded as `if alert_count >= 1:` at line 718. Unlike the agent rate limits which are configurable via `settings.agent_free_daily_limit` and `settings.agent_pro_daily_limit`, the alert limit cannot be changed without a code deployment.

**Impact:** Cannot A/B test different alert limits, cannot temporarily increase limits for promotional campaigns, cannot adjust without a deploy.

**Recommendation:** Add a `free_alert_limit` configuration to `Settings`:
```python
free_alert_limit: int = Field(default=1, validation_alias="FREE_ALERT_LIMIT")
```
Then reference `settings.free_alert_limit` instead of the hardcoded `1`.

### P2-05: `GET /neighborhood/compare` Missing Tier Gate -- Returns Premium-Grade Analysis

**File:** `backend/api/v1/neighborhood.py`, lines 27-49

**Description:** The neighborhood comparison endpoint returns the user's rate percentile vs regional peers and the cheapest alternative. This is arguably pro-tier analytical data (comparable to `/savings/summary` which requires pro). However, it only uses `get_current_user` with no tier gate.

**Impact:** Free-tier users can access neighborhood comparison analytics. Could be intentional to drive conversions, but is inconsistent with the gating on similar analytical endpoints.

**Recommendation:** Evaluate whether this should be gated behind `require_tier("pro")` for consistency with other analytical endpoints. If intentionally free, add a comment.

### P2-06: DB-Level Feature Flags Table Not Used by Any API Endpoint for Runtime Gating

**File:** `backend/services/feature_flag_service.py`, lines 22-71
**File:** `backend/api/v1/internal/operations.py`, lines 39-74

**Description:** A `feature_flags` database table exists with `enabled`, `tier_required`, and `percentage` columns. The `FeatureFlagService.is_enabled()` method correctly evaluates these flags (lines 26-71). However, no API endpoint or route handler calls `is_enabled()` for runtime gating decisions. The only consumers are the internal admin endpoints (`GET /flags`, `PUT /flags/{name}`) for managing the flags.

The actual feature gating in production uses:
- `require_tier()` dependency (static, code-level)
- `settings.enable_ai_agent` environment variable
- `settings.enable_auto_switching` / `enable_load_optimization` / `enable_real_time_updates` (dormant)

The DB-based feature flag system is fully implemented but completely unused for runtime decisions.

**Impact:** The feature flag system provides no value in its current state. If it was built for gradual rollout, it needs to be wired into endpoints. If it is planned for future use, this is acceptable but should be documented.

**Recommendation:** Either integrate `FeatureFlagService.is_enabled()` into actual feature gates (e.g., create a FastAPI dependency that wraps it) or document that this is infrastructure for future use. Consider deprecating the dormant `settings.enable_*` flags in favor of DB-based flags for operational flexibility.

### P2-07: `verify_callback_state` Does Not Enforce Timestamp Expiry

**File:** `backend/api/v1/connections/common.py`, lines 75-100

**Description:** The `verify_callback_state()` function verifies the HMAC signature but does NOT check the timestamp against `OAUTH_STATE_TIMEOUT_SECONDS` (600 seconds, defined at line 42). The timestamp is embedded in the state string and verified as part of the HMAC (so it cannot be tampered with), but there is no check that the callback arrived within 10 minutes.

This means a valid signed state token never expires -- an attacker who obtains a signed state URL can replay it indefinitely. The CLAUDE.md documents "OAuth state format: 5-part... with 10-min expiry" but this expiry is not enforced.

Note: The CLAUDE.md says "5-part" but the code at line 82 checks for 4 parts (`connection_id:user_id:timestamp:hmac`). This is a separate documentation inconsistency.

**Impact:** OAuth state tokens are replay-vulnerable. An attacker with a captured callback URL could replay it after the 10-minute window.

**Recommendation:** Add timestamp validation in `verify_callback_state()`:
```python
import time
ts = int(timestamp)
if time.time() - ts > OAUTH_STATE_TIMEOUT_SECONDS:
    raise HTTPException(status_code=400, detail="Callback state expired.")
```

---

## P3 -- Low / Housekeeping

### P3-01: `require_tier()` Error Message Exposes Tier Name Requirement

**File:** `backend/api/dependencies.py`, lines 182-185

**Description:** The 403 error message is `f"This feature requires a {min_tier.title()} or higher subscription"`. This tells the user exactly which tier they need, which is useful for UX but could be considered an information disclosure issue in a strict security context.

**Recommendation:** This is acceptable for a consumer SaaS product. The message helps users understand what upgrade is needed. No change required.

### P3-02: `_get_user_tier` in Dependencies Returns `"free"` for Non-Existent Users

**File:** `backend/api/dependencies.py`, line 130

**Description:** If the DB query returns `None` (user ID not found in the users table), the function defaults to `"free"` via `or "free"`. This means a valid session token for a deleted user would be treated as free tier rather than raising an error.

**Impact:** Minimal -- `get_current_user` should fail first for deleted users. But if session tokens outlive user deletion, the user gets free-tier access to gated endpoints.

**Recommendation:** This is acceptable defensive coding. The auth layer should handle user deletion. No change required.

### P3-03: Agent `_get_user_context` and `_get_user_tier` Use Separate Queries That Could Be Combined

**File:** `backend/api/v1/agent.py`, lines 68-94, 125-133

**Description:** Both the `/agent/query` and `/agent/task` endpoints call `_get_user_context()` (which queries `region, subscription_tier`) and then separately call `_get_user_tier()` (which queries `subscription_tier` again). This results in 2 DB round trips where 1 would suffice, since `_get_user_context` already fetches the tier.

**Recommendation:** Remove the second `_get_user_tier()` call and use the tier already fetched by `_get_user_context()`. The code at lines 131-132 already overrides `context["tier"]` -- it could use the value from `_get_user_context()` instead.

### P3-04: `FeatureFlagService.is_enabled()` Uses `user_id=None` Default -- Could Cause Unexpected Rollout

**File:** `backend/services/feature_flag_service.py`, lines 26-30

**Description:** When `user_id` is `None` and `percentage < 100`, the percentage check is skipped entirely (line 61: `if percentage < 100 and user_id:`). This means calling `is_enabled("some_flag")` without a user_id returns `True` for partial rollouts, which could cause internal/system checks to see features as enabled even when they should only be available to a subset of users.

**Recommendation:** Document this behavior. Consider requiring `user_id` for percentage-based flags or returning `False` when `user_id` is absent and `percentage < 100`.

### P3-05: `hmac` Module Imported Inside Function Body in `verify_api_key`

**File:** `backend/api/dependencies.py`, line 79

**Description:** `import hmac` is inside the `verify_api_key()` function body, called on every authenticated internal request. While Python caches module imports, the import lookup adds a trivial overhead.

**Recommendation:** Move `import hmac` to the top-level module imports. This is purely a code style issue with negligible performance impact.

### P3-06: Community Endpoints Have No Tier Gate -- All Are Free

**File:** `backend/api/v1/community.py`

**Description:** All community endpoints (create post, list posts, vote, report, stats) use `get_current_user` only -- no tier gating. Community features are available to all authenticated users including free tier.

**Impact:** This is likely intentional -- community engagement from free users drives network effects and conversions.

**Recommendation:** This appears to be a correct product decision. No action needed, but consider documenting this in the codebase.

### P3-07: `GET /agent/task/{job_id}` Does Not Check Rate Limit or Increment Usage

**File:** `backend/api/v1/agent.py`, lines 237-249

**Description:** The task polling endpoint does not check or count against the rate limit. This is correct behavior (polling a previously submitted job should not cost a query), but there is no comment explaining why rate limiting is intentionally omitted.

**Recommendation:** Add a brief comment explaining the design decision.

### P3-08: `GET /agent/usage` Does Not Check Rate Limit

**File:** `backend/api/v1/agent.py`, lines 257-274

**Description:** The usage-check endpoint itself does not count against the rate limit, which is correct. But for completeness, it also does not validate that the user is on a tier that has agent access. A free-tier user can check their agent usage stats even though they have 3 free queries.

**Recommendation:** This is fine -- showing usage info does not leak sensitive data and helps free users understand their remaining queries.

---

## Files With No Issues Found

- `backend/api/v1/export.py` -- Correctly gated with `require_tier("business")` on both endpoints.
- `backend/api/v1/reports.py` -- Correctly gated with `require_tier("business")`.
- `backend/api/v1/forecast.py` -- Correctly gated with `require_tier("pro")` on both endpoints.
- `backend/api/v1/recommendations.py` -- Correctly gated with `require_tier("pro")` on all 3 endpoints.
- `backend/api/v1/prices_analytics.py` -- Correctly gated with `require_tier("pro")` on all 4 endpoints.
- `backend/api/v1/prices_sse.py` -- Correctly gated with `require_tier("business")` on the stream endpoint.
- `backend/api/v1/public_rates.py` -- Intentionally unauthenticated (SEO pages), no tier needed.
- `backend/api/v1/connections/bill_upload.py` -- Correctly uses `require_paid_tier` on all 5 endpoints (per grep).
- `backend/api/v1/connections/portal_scrape.py` -- Correctly uses `require_paid_tier` on both endpoints (per grep).
- `backend/api/v1/connections/email_oauth.py` -- Correctly uses `require_paid_tier` on both authenticated endpoints.
- `backend/api/v1/connections/direct_sync.py` -- Correctly uses `require_paid_tier` on authenticated endpoints; callback correctly uses HMAC verification.
- `backend/api/v1/internal/billing.py` -- Internal endpoint, correctly protected by API key at router level.
- `backend/api/v1/internal/operations.py` -- Internal endpoints, correctly protected by API key at router level.
- `backend/tests/test_tier_gating.py` -- Comprehensive test coverage for all 7 require_tier gated endpoints + alert limit.
- `backend/tests/test_premium_tier_gating.py` -- Additional test coverage for forecast/reports/export tier gating.
- `backend/services/stripe_service.py` -- `apply_webhook_action()` correctly calls `invalidate_tier_cache()` on all tier-changing events (activate, update, deactivate, payment_succeeded).

---

## Summary

### Findings by Severity

| Severity | Count | Category |
|----------|-------|----------|
| P0 | 2 | Rate limit TOCTOU race, parallel tier-check implementation bypasses cache |
| P1 | 6 | Memory leak, info disclosure, missing tier gate on agent, duplicate code, hardcoded tier order, unvalidated flag input |
| P2 | 7 | Missing tier gates, dormant flags, unused flag system, replay vulnerability |
| P3 | 8 | Housekeeping, documentation, code style |

### Endpoint Tier Gating Map

| Endpoint | Tier Required | Mechanism | Status |
|----------|--------------|-----------|--------|
| `GET /prices/current` | None (public) | No auth | Intentional |
| `GET /prices/history` | None (public) | No auth | Intentional |
| `GET /prices/compare` | None (public) | No auth | Intentional |
| `GET /prices/forecast` | Pro | `require_tier("pro")` | Correct |
| `GET /prices/stream` | Business | `require_tier("business")` | Correct |
| `GET /prices/statistics` | Pro | `require_tier("pro")` | Correct |
| `GET /prices/optimal-windows` | Pro | `require_tier("pro")` | Correct |
| `GET /prices/trends` | Pro | `require_tier("pro")` | Correct |
| `GET /prices/peak-hours` | Pro | `require_tier("pro")` | Correct |
| `GET /savings/summary` | Pro | `require_tier("pro")` | Correct |
| `GET /savings/history` | Pro | `require_tier("pro")` | Correct |
| `GET /savings/combined` | Auth only | `get_current_user` | **P2-01: Missing gate** |
| `GET /recommendations/switching` | Pro | `require_tier("pro")` | Correct |
| `GET /recommendations/usage` | Pro | `require_tier("pro")` | Correct |
| `GET /recommendations/daily` | Pro | `require_tier("pro")` | Correct |
| `GET /forecast/{utility_type}` | Pro | `require_tier("pro")` | Correct |
| `GET /forecast` | Pro | `require_tier("pro")` | Correct |
| `GET /reports/optimization` | Business | `require_tier("business")` | Correct |
| `GET /export/rates` | Business | `require_tier("business")` | Correct |
| `GET /export/types` | Business | `require_tier("business")` | Correct |
| `POST /agent/query` | Auth + rate limit | Custom tier-based rate limit | **P1-03: No tier gate** |
| `POST /agent/task` | Auth + rate limit | Custom tier-based rate limit | **P1-03: No tier gate** |
| `GET /agent/task/{job_id}` | Auth only | `get_current_user` | Correct (poll only) |
| `GET /agent/usage` | Auth only | `get_current_user` | Correct (info only) |
| `POST /alerts` | Auth + free limit | Custom (1 alert for free) | Correct |
| `GET /alerts` | Auth only | `get_current_user` | Correct |
| `GET /alerts/history` | Auth only | `get_current_user` | Correct |
| `DELETE /alerts/{id}` | Auth only | `get_current_user` | Correct |
| `PUT /alerts/{id}` | Auth only | `get_current_user` | Correct |
| `GET /neighborhood/compare` | Auth only | `get_current_user` | **P2-05: Missing gate?** |
| All `/connections/*` (25 endpoints) | Paid (Pro+) | `require_paid_tier` | **P0-02: Uncached** |
| `GET /public/rates/*` | None (public) | No auth | Correct (SEO) |
| All `/community/*` | Auth only | `get_current_user` | Intentional |

### Feature Flag Inventory

| Flag | Source | Wired to Runtime? | Status |
|------|--------|-------------------|--------|
| `ENABLE_AI_AGENT` | `settings.py` | Yes -- `_require_agent_enabled()` | Active |
| `ENABLE_AUTO_SWITCHING` | `settings.py` | No | Dormant |
| `ENABLE_LOAD_OPTIMIZATION` | `settings.py` | No | Dormant |
| `ENABLE_REAL_TIME_UPDATES` | `settings.py` | No | Dormant |
| DB `feature_flags` table | `feature_flag_service.py` | No (admin CRUD only) | Unused for runtime |

### Key Architecture Observations

1. **Two parallel tier-check systems exist**: `require_tier()` (cached, in `dependencies.py`) and `require_paid_tier()` (uncached, in `connections/common.py`). These should be unified.
2. **Three locations define tier ordering**: `dependencies.py`, `feature_flag_service.py`, and implicitly `connections/common.py`. Should be centralized.
3. **Stripe webhook cache invalidation is thorough**: All tier-changing events correctly call `invalidate_tier_cache()`. This is well-implemented.
4. **Alert free-tier limit enforcement is atomic**: Uses `SELECT ... FOR UPDATE` to lock the user row before counting alerts, preventing race conditions. This is correctly implemented.
5. **Agent rate limiting has a TOCTOU race**: The check-then-increment pattern allows concurrent requests to exceed the limit. This is the most significant functional issue.
6. **Test coverage for tier gating is excellent**: `test_tier_gating.py` (401 lines) and `test_premium_tier_gating.py` cover all major gated endpoints with free/pro/business/null tier scenarios.
