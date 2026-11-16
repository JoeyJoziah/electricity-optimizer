# Audit Report: Domain Services
## Date: 2026-03-17

### Executive Summary

Twelve domain service files were audited covering community posts/voting/moderation, community solar, CCA (Community Choice Aggregation), neighborhood comparison, referrals, affiliate links, A/B testing, feature flags, analytics, bill parsing, utility discovery, and optimization reports. The codebase is generally well-structured with consistent use of parameterised SQL, nh3 XSS sanitization on community content, and atomic CTE patterns for voting and reporting. No P0 SQL injection vulnerabilities were found. However, three noteworthy issues require prompt attention: a SQL injection risk in `community_solar_service.py` where an f-string interpolates a runtime-built WHERE clause, a moderation timeout mismatch where the module constant is 5 seconds but the docstring claims 30 seconds, and unsanitized user-supplied `reason` text in `report_post` that is stored verbatim and returned in admin APIs. Several P2 concerns around missing pagination caps, hardcoded consumption assumptions, and dead code are also documented.

---

### Findings

#### P0 — Critical

No P0 findings. All direct database parameters use SQLAlchemy `text()` with named bind parameters. The one dynamic SQL construction (see P1-01 below) uses a whitelist-built clause, which is safe but is still an anti-pattern that warrants an upgrade.

---

#### P1 — High

**[P1-01] f-string SQL interpolation in get_programs — community_solar_service.py:56**

The `get_programs` method builds `where_sql` by joining a list of hardcoded string literals and then interpolates it directly into an f-string that is passed to `sqlalchemy.text()`:

```python
where_clauses = ["state = :state"]
if enrollment_status:
    where_clauses.append("enrollment_status = :enrollment_status")
where_sql = " AND ".join(where_clauses)

result = await self._db.execute(
    text(f"""
        SELECT ...
        FROM community_solar_programs
        WHERE {where_sql}
        ...
    """),
    params,
)
```

In the current implementation `where_clauses` only ever contains the two hardcoded string literals, so there is no actual injection path. However, the pattern is dangerous: a future developer may add a user-supplied value to `where_clauses` without realising it is interpolated unsafely. Every other file in this codebase uses `text("""...""")` with static SQL and named binds. This one outlier violates the project convention and is a latent injection risk.

**Impact:** Latent SQL injection vector; pattern violation creates real risk if the where-clause list is ever extended with user input.

**Fix:** Rewrite as two separate static queries or use conditional static SQL with an always-true placeholder:

```python
if enrollment_status:
    result = await self._db.execute(
        text("""
            SELECT ...
            FROM community_solar_programs
            WHERE state = :state
              AND enrollment_status = :enrollment_status
            ORDER BY savings_percent DESC NULLS LAST, program_name
            LIMIT :limit
        """),
        {"state": state.upper(), "enrollment_status": enrollment_status, "limit": limit},
    )
else:
    result = await self._db.execute(
        text("""
            SELECT ...
            FROM community_solar_programs
            WHERE state = :state
            ORDER BY savings_percent DESC NULLS LAST, program_name
            LIMIT :limit
        """),
        {"state": state.upper(), "limit": limit},
    )
```

---

**[P1-02] Moderation timeout constant contradicts documented behaviour — community_service.py:28**

The module-level constant reads:
```python
MODERATION_TIMEOUT_SECONDS = 5
```
But the class docstring and the CLAUDE.md project context both state the moderation timeout is **30 seconds**. `asyncio.wait_for` is called with this constant at lines 100 and 538, meaning posts time out of moderation after 5 seconds. Because the timeout behaviour is fail-open (pending flag is cleared, making the post visible), a 5-second timeout causes far more posts to bypass AI classification than intended — the Groq API typical latency is 2–8 seconds and Gemini is often slower.

**Impact:** Significant fraction of posts skip moderation entirely; designed safety boundary is 6x shorter than specified. Any post whose moderation call takes longer than 5 seconds is published without AI review.

**Fix:** Restore to 30 seconds or align the constant with a deliberate product decision, and add a comment justifying the value:
```python
# 30s matches the documented fail-closed timeout; Groq p95 ≈ 3s, Gemini p95 ≈ 8s
MODERATION_TIMEOUT_SECONDS = 30
```

---

**[P1-03] Report `reason` field stored without sanitization — community_service.py:321–360**

The `report_post` method accepts a free-text `reason` string from the caller and stores it directly in `community_reports.reason` with no sanitization:

```python
async def report_post(
    self,
    db: AsyncSession,
    user_id: str,
    post_id: str,
    reason: Optional[str] = None,
) -> None:
    report_sql = text("""
        WITH ins AS (
            INSERT INTO community_reports (user_id, post_id, reason)
            VALUES (:user_id, :post_id, :reason)
            ...
```

If `reason` is displayed in an admin panel or returned via any API endpoint, this is a stored XSS vector. All other user-supplied text in this service (post title, body, supplier name) passes through `nh3.clean()` before storage. `reason` is the sole exception.

**Impact:** Stored XSS risk if report reasons are rendered in a web interface (admin dashboards are common consumers). Even if the current admin UI escapes output, stored raw HTML in the DB is a time-bomb.

**Fix:** Apply `nh3.clean()` to reason before insertion, and add a length cap (e.g. 500 chars):
```python
import nh3
clean_reason = nh3.clean(reason[:500]) if reason else None
```

---

**[P1-04] Referral `complete_referral` has no qualifying-action guard — referral_service.py:127–145**

`complete_referral(referee_id)` marks a referral complete and sets `reward_applied = TRUE` for any referral where `referee_id` matches and `status = 'pending'`. There is no verification that the referee has actually completed the qualifying action (e.g., paid subscription, first savings sync). The caller is trusted to call this only after the qualifying action, but the service itself enforces nothing:

```python
result = await self._db.execute(
    text(
        "UPDATE referrals SET status = 'completed', "
        "completed_at = :now, reward_applied = TRUE "
        "WHERE referee_id = :referee_id AND status = 'pending' "
        "RETURNING ..."
    ),
    {"referee_id": referee_id, "now": now},
)
```

If any endpoint or background job calls this prematurely or can be triggered by the referee themselves, rewards are granted without earning them. Additionally, a user with multiple pending referrals (possible if the code generation query returns a `pending` row without a `referee_id`, but the apply step allows one per user) could have all completed in one call — the UPDATE has no `LIMIT 1`.

**Impact:** Business logic bypass — rewards granted without qualifying action if caller is compromised or endpoint is exposed incorrectly. Secondary: a single call completes all pending referrals for a user.

**Fix:** Add a `LIMIT 1` to the UPDATE to prevent multi-row completion. Document at the call site that callers must verify the qualifying action before invoking. Consider moving verification into the service.

---

**[P1-05] `update_actual` in ABTestService has no ownership/scope check — ab_test_service.py:313–371**

`update_actual(prediction_id, actual_value)` fetches the row, computes error, and updates it with no user scope check. Any caller with a `prediction_id` can overwrite the actual value for any prediction row belonging to any user. In the current flow this is called from internal background jobs, but if it is ever exposed via an API endpoint (even internal), a caller could manipulate historical accuracy data to trigger auto-promotion of a model version.

**Impact:** Data integrity — model A/B test outcome can be corrupted; `auto_promote` decision could be manipulated.

**Fix:** Add a `user_id` or `model_version` scope parameter to the SELECT and UPDATE:
```sql
WHERE id = :prediction_id
  AND model_version = :model_version   -- caller must know which test
```

---

#### P2 — Medium

**[P2-01] No upper bound on `per_page` in `list_posts` — community_service.py:194**

`list_posts` accepts `per_page: int = 10` with no maximum cap. A caller can pass `per_page=100000`, causing a massive `LIMIT` in the query and returning all matching rows in one response. The COUNT(*) OVER() window function will compute the total across all rows regardless of the limit, adding significant query cost.

**Fix:** Add a cap at the service layer:
```python
per_page = min(per_page, 100)
```

---

**[P2-02] No upper bound on `limit` in `get_programs` (CommunitySolarService) — community_solar_service.py:36**

`get_programs(limit: int = 20)` passes `limit` directly to `LIMIT :limit` with no maximum enforcement. A caller can request an arbitrarily large result set.

**Fix:** Apply `limit = min(limit, 200)` at the start of the method.

---

**[P2-03] No upper bound on `days` in `get_revenue_summary` — affiliate_service.py:131**

`get_revenue_summary(days: int = 30)` passes `days` to `NOW() - :days * INTERVAL '1 day'`. A caller can pass `days=36500` (100 years), causing Postgres to scan the entire `affiliate_clicks` table. There is no pagination or limit on the result set either.

**Fix:** Cap at a reasonable maximum (e.g. 365 days) and consider adding pagination:
```python
days = min(days, 365)
```

---

**[P2-04] `retroactive_moderate` fetches unbounded result set — community_service.py:440–484**

`retroactive_moderate` selects all qualifying posts from the last 24 hours with no `LIMIT`. In a community with high posting volume, this could return tens of thousands of rows into memory before launching parallel AI classification tasks (capped at Semaphore(5)). A runaway post volume could cause memory exhaustion.

**Fix:** Add a `LIMIT` (e.g. 1000) and implement batch processing if the total exceeds it:
```sql
SELECT id, title, body FROM community_posts
WHERE ...
ORDER BY created_at ASC
LIMIT 1000
```

---

**[P2-05] Hardcoded 900 kWh/month assumption in `compare_cca_rate` — cca_service.py:105**

```python
monthly_savings = savings_per_kwh * 900  # avg 900 kWh/month
```

This is a fixed national average not personalized to the user. The `OptimizationReportService` uses the `AVG_MONTHLY_CONSUMPTION` dict (which uses 886 kWh for electricity from EIA), but `CCAService` uses a separate hardcoded inline literal. The values are inconsistent (900 vs 886) and neither is sourced from user data.

**Impact:** Savings estimate is wrong for most users; inconsistency between services confuses anyone debugging discrepancies.

**Fix:** Import and use the constant from `OptimizationReportService.AVG_MONTHLY_CONSUMPTION` (or a shared module), and accept an optional `monthly_kwh` parameter for personalized calculation.

---

**[P2-06] `_get_electricity_spend` references wrong row for "cheapest supplier" — optimization_report_service.py:137**

```python
"action": f"Switch to cheapest supplier ({rows[-1].get('supplier', 'best rate')})",
```

`rows` is ordered `DESC` by `timestamp` (most recent first), so `rows[-1]` is the **oldest** record, not the cheapest. The intent is to show the supplier with the lowest price; the correct approach is to find `min(prices)` and its corresponding supplier.

**Impact:** The displayed "cheapest supplier" in the optimization report is incorrect — it shows an unrelated historical record's supplier name.

**Fix:**
```python
min_idx = prices.index(min(prices))
cheapest_supplier = rows[min_idx].get('supplier', 'best rate')
"action": f"Switch to cheapest supplier ({cheapest_supplier})",
```

---

**[P2-07] `feature_flag_service.update_flag` does not validate `tier_required` values — feature_flag_service.py:93–127**

`update_flag` accepts any string as `tier_required` without checking it against the valid set `{"free", "pro", "business"}`. An invalid value like `"enterprise"` will be stored in the DB, and because `_TIER_ORDER.get(tier_required, 0)` defaults to `0`, a flag with `tier_required = "enterprise"` will be accessible to all free users, silently defeating the tier gate.

**Fix:** Validate before storing:
```python
VALID_TIERS = {"free", "pro", "business"}
if tier_required is not None and tier_required not in VALID_TIERS:
    raise ValueError(f"Invalid tier_required '{tier_required}'. Must be one of: {VALID_TIERS}")
```

---

**[P2-08] `is_enabled` silently allows unknown `user_tier` — feature_flag_service.py:58–62**

When `user_tier` is an unrecognised value, `_TIER_ORDER.get(user_tier, 0)` silently returns `0` (free tier). A mis-spelled tier (`"Pro"` vs `"pro"`) would pass a tier check if the required tier is also free, or block a pro/business user from a feature they paid for. No warning is logged.

**Fix:** Log a warning when the tier string is unrecognised:
```python
user_level = _TIER_ORDER.get(user_tier)
if user_level is None:
    logger.warning("unknown_user_tier", user_tier=user_tier, flag=flag_name)
    user_level = 0
```

---

**[P2-09] `report_post` exposes `report_count` to public `list_posts` response — community_service.py:207**

`list_posts` returns `report_count` (the raw count of reports) as part of every post object visible to all users. A user can observe exactly how many reports have been filed on any post, which could help adversarial users game the threshold (filing the last required report knowing they are one away from hiding). It also exposes internal moderation state to the public.

**Fix:** Strip `report_count` from the public-facing response dict. It should only be available to admins.

---

**[P2-10] `get_stats` exposes full `top_tip` post object including metadata — community_service.py:561–600**

`get_stats` returns `dict(top_tip)` which is the entire database row for the top-voted tip, including internal fields like `is_pending_moderation`, `hidden_reason`, `user_id`, etc. The response is a public/social-proof endpoint and should not expose these internal columns.

**Fix:** Project only the public fields from `top_tip`:
```python
"top_tip": {
    "id": str(top_tip["id"]),
    "title": top_tip["title"],
    "body": top_tip["body"],
    "upvote_count": top_tip["upvote_count"],
    "region": top_tip["region"],
} if top_tip else None,
```

---

**[P2-11] `OptimizationReportService.generate_report` accepts `user_id` but never uses it — optimization_report_service.py:34–106**

The signature includes `user_id: Optional[str] = None` and the docstring mentions "personalized data," but the parameter is never referenced in the method body or passed to any of the four private helper methods. The report is purely state-level aggregated data regardless of `user_id`. This is dead API surface that creates misleading expectations about personalization.

**Fix:** Either remove the `user_id` parameter and update callers, or implement the personalized lookup (user's own tracked rates from their connections) that the parameter implies.

---

**[P2-12] `CCAService.compare_cca_rate` does not 404 cleanly — cca_service.py:98–101**

When a `cca_id` is not found, the method returns `{"error": "CCA program not found"}` as a plain dict rather than raising an exception. Callers must inspect the dict for the `"error"` key to detect failure, which is inconsistent with how the rest of the codebase raises exceptions for not-found conditions. This pattern leads to silent failures if a caller forgets to check.

**Fix:** Raise a `ValueError` or a custom `NotFoundError` consistent with the rest of the service layer, and let the API layer convert it to a 404 response.

---

**[P2-13] `NeighborhoodService.get_comparison` leaks supplier names across users — neighborhood_service.py:82–100**

The `cheapest` CTE finds the user with the single cheapest rate and exposes their `supplier_name` directly:
```sql
cheapest AS (
    SELECT supplier_name, avg_rate
    FROM user_rates
    WHERE supplier_name IS NOT NULL
    ORDER BY avg_rate ASC
    LIMIT 1
)
```

This returns one specific user's supplier name (the cheapest user in the cohort). While supplier names are not personally identifying on their own, in small cohorts (close to `MIN_USERS_FOR_COMPARISON = 5`) this can narrow down which specific neighbour has a particular supplier arrangement. Consider whether this is acceptable, or whether aggregating multiple suppliers is more appropriate.

**Fix (optional):** Add a minimum count guard on the `cheapest` CTE — only show the cheapest supplier if at least N users share it, or query the `suppliers` table directly for available rates instead of inferring from peer data.

---

#### P3 — Low

**[P3-01] Dead imports in `ab_test_service.py` — ab_test_service.py:44–45**

```python
import json
import logging
```

Neither `json` nor `logging` is used anywhere in the file. The project uses `structlog` (imported and used correctly at line 54). These stale imports should be removed.

---

**[P3-02] Placeholder `avg_savings_pct: None` in `get_stats` response — community_service.py:599**

```python
"avg_savings_pct": None,  # Placeholder — populated when savings aggregation exists
```

This stub field has been in place since the feature was written. If the API contract has stabilised and no near-term work is planned, the field should either be implemented or removed to avoid confusing API consumers who attempt to use it.

---

**[P3-03] MD5 used for feature flag percentage hashing — feature_flag_service.py:66**

```python
hashlib.md5(f"{flag_name}:{user_id}".encode()).hexdigest()[:8]
```

MD5 is cryptographically broken, but the usage here is purely deterministic bucketing (not a security function), so there is no real vulnerability. However, for consistency with `ab_test_service.py` which uses `hashlib.sha256` for an identical purpose, using MD5 is inconsistent. If the codebase is ever scanned by a SAST tool or goes through a compliance audit, MD5 will be flagged. Use SHA-256 for consistency.

---

**[P3-04] `MODERATION_TIMEOUT_SECONDS` used in `edit_and_resubmit` but module-level constant name implies single use — community_service.py:28, 100, 538**

The constant is used in two separate `asyncio.wait_for` calls (initial post creation and resubmission). This is correct behaviour, but the constant name does not indicate it applies to both paths. Adding a brief comment clarifying both usages would improve maintainability.

---

**[P3-05] `AffiliateService` partner config is hardcoded in module-level dict — affiliate_service.py:21–32**

```python
AFFILIATE_PARTNERS: Dict[str, Dict[str, str]] = {
    "choose_energy": {...},
    "energysage": {...},
}
```

The docstring comment says "In production, these would come from a config table or env vars." This is a known deferred item, but the hardcoded URLs and UTM parameters (including `utm_source: "rateshift"` reflecting the public brand name) mean any change requires a code deployment. This is minor but worth tracking if affiliate partners change or expand.

---

**[P3-06] `CommunitySolarService` constructor stores `db` as `self._db` but `BillParserService` and `AffiliateService` use `self.db` (no underscore) — multiple files**

Minor naming inconsistency across the service layer. `CommunitySolarService`, `CCAService`, `ABTestService`, `FeatureFlagService`, and `ReferralService` all use `self._db` (private). `BillParserService` and `AffiliateService` use `self.db` (public). This creates inconsistency — new developers will look at two services side-by-side and be uncertain of the convention.

**Fix:** Standardise on `self._db` throughout the service layer.

---

**[P3-07] `AnalyticsService` cache stampede protection is incomplete — analytics_service.py:138–146, 222–230, 313–321**

The `_acquire_cache_lock` method prevents duplicate computation under the lock, but after a failed lock acquisition the code re-checks the cache **without sleeping or retrying**. If the lock holder has not yet written the result (e.g., still mid-computation), the second request gets a cache miss and returns stale defaults rather than the computed result. This is a minor race window, not a security issue.

---

### Statistics

- Files audited: 12
- Total findings: 22 (P0: 0, P1: 5, P2: 13, P3: 7 — including sub-items P3-07)

| Severity | Count | Files Affected |
|----------|-------|----------------|
| P0 Critical | 0 | — |
| P1 High | 5 | community_service.py, community_solar_service.py, ab_test_service.py, referral_service.py |
| P2 Medium | 13 | community_service.py, optimization_report_service.py, feature_flag_service.py, affiliate_service.py, cca_service.py, neighborhood_service.py |
| P3 Low | 7 | ab_test_service.py, community_service.py, affiliate_service.py, feature_flag_service.py, analytics_service.py, multiple |

### Priority Remediation Order

1. **[P1-02]** Fix moderation timeout constant (5s → 30s) — safety boundary violation, one-line fix
2. **[P1-03]** Sanitize `report_post` reason with `nh3.clean()` — stored XSS risk
3. **[P2-06]** Fix wrong row index for cheapest supplier in optimization report — incorrect user-facing data
4. **[P1-01]** Refactor `community_solar_service.get_programs` to eliminate f-string SQL — latent injection pattern
5. **[P2-10]** Strip internal fields from `get_stats` top_tip response — data exposure
6. **[P2-09]** Remove `report_count` from public `list_posts` response — moderation state leak
7. **[P2-07]** Add `tier_required` validation in `update_flag` — silent tier gate bypass
8. **[P1-04]** Add `LIMIT 1` to `complete_referral` UPDATE and document qualifying-action requirement
9. **[P2-01–03]** Add per_page/limit/days caps across community, solar, and affiliate services
10. **[P3-01]** Remove unused `import json` and `import logging` from `ab_test_service.py`
