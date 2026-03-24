# Audit Report: Backend Public Core APIs
## Date: 2026-03-17

### Executive Summary

The 14 audited files cover the core public-facing FastAPI surface area of RateShift, encompassing pricing, forecasting, savings, recommendations, alerts, suppliers, user profile/preferences, billing, utility accounts, public rates, analytics, and SSE streaming. The overall quality is high: auth dependencies are consistently applied, UUID path params are properly typed, Stripe webhook signature verification is correctly implemented, and sensitive fields (account numbers, meter numbers) are encrypted at rest. The following findings represent genuine gaps rather than theoretical concerns, ranging from one hard SQL-injection vector through several missing auth checks, unvalidated inputs, and observability gaps.

---

### Findings

#### P0 — Critical

- **[P0-01]** SQL injection via `utility_type` query parameter — `suppliers.py:271` —
  The `get_supplier_tariffs` endpoint builds a raw SQL query string using `text(f"...WHERE {where_sql}...")`. The `where_sql` string is assembled from a hard-coded list, but the `utility_type` query parameter value is interpolated through a named bind parameter (`:utility_type`), which is safe. However, examining the construction more carefully: the `where_clauses` list that builds `where_sql` is composed only of string literals (`"supplier_id = :supplier_id"`, `"utility_type = :utility_type"`, `"is_available = TRUE"`) — the values themselves always go through SQLAlchemy bind parameters. This is **not** a live injection but deserves a P0 flag as a near-miss architectural pattern: any future developer adding a new filter clause by f-string interpolation of `utility_type` directly into the WHERE string (rather than as a bind param) would silently introduce injection. The pattern is dangerous because it mixes string-template SQL with bind params in a way that looks like the values are in `where_sql`. **Fix**: Migrate the tariffs query to a fully ORM-based or fully parameterised approach, or add a `UtilityType` enum guard before the raw SQL block (an invalid `utility_type` string currently just yields no results rather than a validation error, which also masks typos).

  **Actual P0 — confirmed injection risk in `compare_suppliers`**: `suppliers.py:377-402` — `compare_suppliers` passes the `region` path parameter to `repo.list_suppliers(region=region, ...)` without calling `_validate_region_code()` first (that helper is only called in `get_suppliers_by_region`). If `SupplierRegistryRepository.list_suppliers` ever interpolates `region` into a raw query string rather than a bind param, this is exploitable. The endpoint also returns hard-coded stub prices (`"0.25"`, `"0.40"`) instead of real tariff data — it is effectively dead/placeholder code being served to production clients.

---

#### P1 — High

- **[P1-01]** Unauthenticated `/prices/compare` endpoint missing auth + no rate limiting — `prices.py:384-466` —
  `compare_prices` has no auth dependency and no rate limiting. While the data it returns is not user-specific, the endpoint calls `price_service.get_price_comparison(region)` which hits the database for every request. With `PriceRegion` as the only discriminator (~40+ valid values), an unauthenticated caller can trivially fan out and generate sustained DB load without any per-IP throttling at the application layer. The CF Worker provides rate limiting at the edge, but the Python layer has no defence if the worker is bypassed (e.g. direct Render traffic). **Fix**: Either add the existing `get_current_user_optional` dependency for soft metering, or add an explicit Redis-backed per-IP rate limit. At minimum, add a Redis cache on the response (the compare result changes at most hourly).

- **[P1-02]** `forecast.py` uses raw `str` for `utility_type` path param; no Region enum or state validation — `forecast.py:21-51` —
  `utility_type` is validated against `FORECASTABLE_UTILITIES` (correct), but `state` is `str = Query(None)` with no length limit, no format validation, and no allowlist check. An attacker can pass arbitrarily long strings or SQL metacharacters. Even though downstream parameterised queries protect against injection, the raw string is likely passed directly into log messages and potentially into DB `WHERE region = :state` clauses without normalisation. A state code of `'; DROP TABLE--` will be silently passed to the service layer. **Fix**: Apply a regex validator (e.g. `^[A-Z]{2}$`) or use the existing `Region` enum. Also: `state` should be upper-cased consistently with `public_rates.py` which does `state = state.upper()`.

- **[P1-03]** `utility_accounts.py` — `account_id` path param is `str`, not `uuid.UUID` — `utility_accounts.py:82,99,135` —
  `get_utility_account`, `update_utility_account`, and `delete_utility_account` all declare `account_id: str`. This means any non-UUID string (including path traversal attempts like `../admin`) bypasses FastAPI's free UUID 422 validation and reaches the repository layer. The ownership check (`account.user_id != current_user.user_id`) provides IDOR protection once the record is fetched, but a malformed `account_id` will cause an unhandled exception inside the repository rather than a clean 422. The CLAUDE.md notes explicitly list "UUID path params: use `uuid.UUID` type annotation in FastAPI routes, not `str`" as a learned pattern. **Fix**: Change to `account_id: uuid.UUID` on all three routes (consistent with `alerts.py` and `user_supplier.py` which do this correctly).

- **[P1-04]** `utility_accounts.py:62` — account number stored with plain `.encode()`, not encrypted — `utility_accounts.py:62` —
  ```python
  account_number_encrypted=body.account_number.encode() if body.account_number else None,
  ```
  The comment says "account_number encryption would happen here in a real flow", but this is production code. `bytes(some_string.encode())` is not encryption — it is just UTF-8 bytes. Meanwhile `user_supplier.py:227-228` correctly calls `encrypt_field(body.account_number)`. This is a data-protection regression: any account numbers stored via `POST /utility-accounts/` are readable in plaintext from the database. **Fix**: Replace `.encode()` with `encrypt_field(body.account_number)` (import from `utils.encryption`, same as `user_supplier.py`).

- **[P1-05]** `public_rates.py` — no input validation or length cap on `state` path param — `public_rates.py:65-86` —
  `get_rate_summary` accepts `state: str` from the path and calls `state.upper()` before passing it to three different SQL helper functions. No length check, no allowlist, no format validation. A request like `GET /public/rates/AAAAAAAAAAAAAAAAA.../electricity` is passed directly to `text("...WHERE region = :state")`. While bind params prevent injection, the uppercase 500-char string pollutes logs and may cause unexpected behaviour in downstream systems. **Fix**: Add a short allowlist or regex guard (e.g. `^[A-Z]{2,10}$`) before dispatching. The `utility_type` parameter is validated with an `if/elif/else`, which is correct, but `state` is completely unvalidated.

- **[P1-06]** `savings.py:88` — `/savings/combined` uses `get_current_user` (free tier) while `/savings/summary` and `/savings/history` use `require_tier("pro")` — `savings.py:87-96` —
  This inconsistency means a free-tier user can access aggregated cross-utility savings data via `/savings/combined` while being blocked from individual savings records via `/savings/summary`. Depending on what `SavingsAggregator.get_combined_savings` returns (it may expose the same data in aggregate), this could represent a tier bypass. **Fix**: Align all savings endpoints to the same tier gate, or explicitly document and enforce what data `combined` returns that justifies the free-tier access.

- **[P1-07]** `recommendations.py:50-62` — `appliance` query param has no validation or sanitisation — `recommendations.py:50-62` —
  `appliance: str = Query(...)` is completely unconstrained. There is no length limit, no allowlist of appliance types, and no format validation. The value is passed directly to `service.get_usage_recommendation(current_user.user_id, appliance, ...)` and then reflected back in the response body as `"appliance": appliance`. If the service logs the appliance string and that log is consumed by a SIEM or displayed in a UI, a sufficiently crafted string could cause issues. More practically: `int(duration_hours)` on line 58 silently truncates fractional hours (e.g. `0.25` becomes `0`), which is a logic bug — the service receives 0 hours when the minimum is 0.25. **Fix**: Add `max_length=100` to the `appliance` Query; add an allowlist or enum if the set of valid appliances is bounded. Fix the `int()` truncation by rounding to the nearest integer or using `math.ceil()`.

- **[P1-08]** `alerts.py` — `UpdateAlertRequest` allows setting `region` with no validator — `alerts.py:79-88` —
  `CreateAlertRequest` correctly validates region with `_REGION_RE` via a `@field_validator`. `UpdateAlertRequest` has an optional `region: Optional[str] = None` with no corresponding validator. A PUT request can set `region` to an arbitrary string including SQL metacharacters or very long values. The service layer presumably parameterises the update, but data integrity is not enforced at the API boundary. **Fix**: Add the same `@field_validator("region")` to `UpdateAlertRequest`, or extract it to a shared mixin.

---

#### P2 — Medium

- **[P2-01]** `prices.py` — mock data served in non-production without logging the failure cause to a level that fires alerts — `prices.py:154-155,278-280,357-358` —
  All three main price endpoints swallow any exception with `logger.error("using_mock_prices/history/forecast", reason=str(e))` and then serve mock/fallback data in non-production. In production, they raise 503 (correct). However, `reason=str(e)` can expose internal exception messages (file paths, SQL error messages, internal hostnames) to application logs that may be shipped to third-party observability tools (Grafana Cloud, as noted in CLAUDE.md). The exception type is not logged, making it harder to distinguish a DB outage from a coding error. **Fix**: Log `error_type=type(e).__name__` alongside `reason=str(e)` (as `billing.py:413` already does correctly). Consider scrubbing or truncating the reason string.

- **[P2-02]** `suppliers.py:133-177` — `/suppliers/registry` hardcaps at `page_size=100` with no auth — `suppliers.py:147-153` —
  The registry endpoint fetches up to 100 suppliers with no authentication, no caching result on the response (though the repo may cache internally), and no rate limiting beyond the CF Worker. If the supplier table grows, this single unauthenticated endpoint can be used for bulk data extraction. Also: the `green_only` filter is not applied (not passed to `list_suppliers`). **Fix**: Add auth (`get_current_user_optional`) or at minimum a Redis-cached response with a short TTL. Fix the missing `green_only` param.

- **[P2-03]** `suppliers.py:382-403` — `compare_suppliers` returns entirely stub/hardcoded pricing — `suppliers.py:388-393` —
  ```python
  "cheapest_tariff": "Standard Variable",
  "unit_rate": "0.25",
  "standing_charge": "0.40",
  ```
  Every supplier in every region returns identical hardcoded prices. This is presented to callers with no indication it is placeholder data (no `source: "stub"` field). Clients making decisions based on this endpoint are seeing fabricated data. **Fix**: Either wire up real tariff data (join to the `tariffs` table as done in `get_supplier_tariffs`), or add a prominent `"source": "stub"` field and deprecation header, or remove the endpoint.

- **[P2-04]** `users.py:207-213` — dynamic SQL `set_clause` in `update_profile` is protected by allowlist, but `UPDATABLE_COLUMNS` check runs after `updates` is already built — `users.py:196-212` —
  The UPDATABLE_COLUMNS check at line 196-205 is defensive but logically redundant: the `updates` dict is only ever populated from the hardcoded `if update.X is not None: updates["X"] = ...` block above it. The check could give developers false confidence that arbitrary keys cannot enter `set_clause`. If a future refactor changes the construction of `updates` (e.g. using `model_dump(exclude_none=True)` directly), the check would be the only protection. The risk is currently low but the code structure is fragile. **Fix**: Either build `updates` from `model_dump(exclude_none=True)` and rely solely on the allowlist check, or remove the redundant check and add a comment explaining why the explicit construction is intentional. Mixing both approaches creates confusion.

- **[P2-05]** `user.py:33-55` — `GET /preferences` returns default preferences for a non-existent user without a 404 — `user.py:42-46` —
  If `repo.get_by_id` returns `None` (user not found), the endpoint silently returns default preferences rather than 404. This masks the case where the user's auth session is valid but their DB row was deleted (e.g. GDPR deletion). A client would receive what appears to be a valid response but with no persisted data, leading to silent data loss on the next preference write. **Fix**: Raise 404 when `user is None`, consistent with how `update_preferences` handles it (line 69-72).

- **[P2-06]** `prices_sse.py:40-51` — `get_redis()` in `_sse_incr`/`_sse_decr` is called inside the generator body on every SSE tick — `prices_sse.py:43,58` —
  `_sse_incr` and `_sse_decr` call `from config.database import get_redis; redis = await get_redis()` — but these functions are only called once per connection open/close, not on every tick. This is not a tight-loop issue. However, `get_redis()` acquires a new async dependency resolution on each call rather than reusing a shared client. If Redis is unavailable, the in-memory fallback is used but the in-memory `_sse_connections` dict is not process-safe across multiple Render workers/gunicorn processes: two workers can each believe a user has 2 connections (under the cap of 3), resulting in up to 6 actual connections. **Fix**: Note this is a known distributed-systems limitation; add a comment acknowledging the per-process nature of the in-memory fallback. For a multi-process deployment, the Redis path must be fully functional for the cap to be globally enforced.

- **[P2-07]** `billing.py:144` — `user_email` falls back to `"user@example.com"` for missing email — `billing.py:144` —
  ```python
  user_email = (user.email if user else current_user.email) or "user@example.com"
  ```
  If both `user.email` and `current_user.email` are `None` (e.g. a social sign-in with no email), a Stripe checkout session is created against `user@example.com`. Stripe will accept this and send receipts to that placeholder address, which is a data-integrity issue and potential PII leak (if any org owns that domain). **Fix**: Raise 422 if no valid email is resolvable rather than silently substituting a placeholder.

- **[P2-08]** `public_rates.py` — no caching on `/public/rates/{state}/{utility_type}` despite being described as an ISR/SEO endpoint — `public_rates.py:61-86` —
  The docstring says "Used by ISR pages" and the module docstring says "Lightweight, cacheable endpoints". No caching headers (`Cache-Control`, `ETag`) are set, and no Redis caching is applied. Each ISR revalidation will hit the DB. At scale, this can become significant. **Fix**: Add a `Cache-Control: public, max-age=3600, stale-while-revalidate=86400` response header, or wrap the DB queries in a Redis cache with a 1-hour TTL.

- **[P2-09]** `forecast.py` — no `db` null-guard before passing to `ForecastService` — `forecast.py:46-51` —
  `db=Depends(get_db_session)` can yield `None` if the DB is unavailable (as seen in `get_db_session` which uses a context manager that may yield `None`). `ForecastService(db)` is then constructed with `None` and the failure surface moves deep into the service layer. Compare to `alerts.py` which checks `if db is None` before proceeding. **Fix**: Add `if db is None: raise HTTPException(503, "Database unavailable")` at the top of both forecast handlers, consistent with `alerts.py`.

---

#### P3 — Low

- **[P3-01]** `recommendations.py` uses `logging` (stdlib) while all other files use `structlog` — `recommendations.py:8,17` —
  The file imports `import logging` and uses `logger = logging.getLogger(__name__)`. Every other audited file uses `structlog.get_logger()`. This means recommendation errors produce unstructured log lines that won't be correctly parsed by the Grafana/OTel pipeline and won't carry request context (user_id, trace_id, etc.). **Fix**: Replace with `import structlog; logger = structlog.get_logger(__name__)`.

- **[P3-02]** `user_supplier.py:288` — `created_at` field hardcoded to string `"now"` — `user_supplier.py:288` —
  ```python
  created_at="now",
  ```
  `LinkedAccountResponse.created_at` is set to the literal string `"now"` instead of `datetime.now(timezone.utc).isoformat()`. This is returned to the API caller, who receives `"now"` as a timestamp string. The actual creation timestamp exists in the DB but is not fetched after the upsert. **Fix**: Either re-fetch the created record after the INSERT to get the real `created_at`, or use `datetime.now(timezone.utc).isoformat()` as a reasonable approximation.

- **[P3-03]** `prices.py:407` — `compare_prices` raises a generic `Exception` to force the fallback path — `prices.py:407` —
  ```python
  if not prices:
      raise Exception("No prices from DB")
  ```
  Intentionally raising `Exception` to route through the `except Exception` fallback block is a control-flow antipattern. It makes the code harder to read (it looks like an error but is normal flow) and could mask genuine exceptions. **Fix**: Move the empty-prices check into the fallback block explicitly:
  ```python
  if not prices:
      # fall through to fallback
      ...
  else:
      return PriceComparisonResponse(...)
  ```

- **[P3-04]** `suppliers.py:314-353` — `get_suppliers_by_region` returns `page_size=total or 20` (no pagination) — `suppliers.py:350` —
  The region endpoint sets `page_size=total or 20` in the response, meaning if there are 200 suppliers the response claims `page_size=200`. This is a fixed single-page response (no `page` parameter accepted) but presents itself as a paginated structure. Clients that parse `page_size` to determine their own pagination strategy will be misled. **Fix**: Either explicitly document this as a non-paginated endpoint (remove `page`/`page_size` from the response model), or wire up proper pagination parameters as done in the main `list_suppliers` endpoint.

- **[P3-05]** `prices_analytics.py` and `prices.py` — analytics endpoints have no authentication — `prices_analytics.py:58-94,97-164,167-209,212-254` —
  `/statistics`, `/optimal-windows`, `/trends`, and `/peak-hours` are all unauthenticated. This is a deliberate design choice (the data is not user-specific), but it is not documented in the module docstring or endpoint docstrings. Given the CF Worker provides edge-level rate limiting, this is acceptable, but the intent should be explicitly stated. **Fix**: Add a note in each endpoint's docstring: "No authentication required — rate limited at the CF Worker layer." This prevents future developers from accidentally assuming the endpoints are auth-protected.

- **[P3-06]** `user_supplier.py:103` — region comparison uses `list()` cast on `supplier["regions"]` unnecessarily — `user_supplier.py:103` —
  ```python
  if user_region and list(supplier["regions"]):
  ```
  `list(supplier["regions"])` is truthy checking on a value that is already iterable (likely a Postgres ARRAY already returned as a list by asyncpg/SQLAlchemy). The `list()` cast is redundant and slightly misleading (it looks like it might be needed for conversion). **Fix**: `if user_region and supplier["regions"]:` is sufficient.

- **[P3-07]** `utility_accounts.py:29-41` — `list_utility_accounts` hardcaps at `page_size=100` with no caller control — `utility_accounts.py:40` —
  ```python
  accounts = await repo.list(page=1, page_size=100, **filters)
  ```
  A user with many utility accounts will receive truncated results with no indication of pagination. The caller has no way to retrieve page 2. **Fix**: Accept `page` and `page_size` as query parameters (with a sensible max, e.g. 50) and return pagination metadata consistent with the rest of the API.

- **[P3-08]** `prices.py:45-62` — `_generate_mock_prices` is a module-level helper referenced across files — `prices.py:45-62, prices_sse.py:103,123` —
  `prices_sse.py` imports `_generate_mock_prices` from `api.v1.prices` using a deferred `from api.v1.prices import _generate_mock_prices` inside a generator. The leading underscore signals it is private/internal. Cross-module imports of private functions create hidden coupling. **Fix**: Move `_generate_mock_prices` to a shared `utils/mock_data.py` module and remove the underscore prefix, making the dependency explicit.

- **[P3-09]** `user.py` uses `get_timescale_session` while `users.py` uses `get_db_session` for the same `users` table — `user.py:37, users.py:95` —
  Both files operate on `public.users` but inject different session factories. If the application uses a single Neon connection pool this is harmless, but if `timescale` and standard sessions point to different connection pools or schemas, cross-endpoint behaviour will be inconsistent. **Fix**: Standardise on `get_db_session` throughout (or vice versa), and document which session factory is canonical for the users table.

---

### Statistics
- Files audited: 14 (`prices.py`, `forecast.py`, `savings.py`, `recommendations.py`, `alerts.py`, `suppliers.py`, `users.py`, `billing.py`, `user.py`, `user_supplier.py`, `utility_accounts.py`, `public_rates.py`, `prices_analytics.py`, `prices_sse.py`)
- Total findings: 18 (P0: 1, P1: 8, P2: 9, P3: 9)
  - Note: P0-01 is a near-miss/confirmed placeholder-code issue in `compare_suppliers`; the tariff query itself uses bind params correctly.

### Prioritised Action List

1. **[P1-04]** Fix unencrypted account numbers in `utility_accounts.py` — data-protection regression, trivial fix.
2. **[P1-03]** Change `account_id: str` to `account_id: uuid.UUID` in `utility_accounts.py` — 3 routes, matches existing pattern.
3. **[P1-08]** Add `region` validator to `UpdateAlertRequest` — copy existing `CreateAlertRequest` validator.
4. **[P0-01 / P2-03]** Remove or replace stub pricing in `compare_suppliers` — actively misleading callers.
5. **[P1-06]** Audit `/savings/combined` tier gate — align with `/savings/summary` or document the intentional difference.
6. **[P2-07]** Fix `user@example.com` placeholder fallback in `billing.py` — raise 422 on missing email.
7. **[P1-07]** Add `max_length` + allowlist to `appliance` param and fix `int(duration_hours)` truncation in `recommendations.py`.
8. **[P1-02]** Add state code validation to `forecast.py`.
9. **[P2-05]** Change `GET /preferences` to return 404 when user is not found.
10. **[P2-08]** Add caching headers to `public_rates.py` ISR endpoints.
