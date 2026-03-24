# Audit Report: Backend Repositories & Models
**Date:** 2026-03-23
**Scope:** All repository classes and ORM models
**Files Reviewed:**

### Repositories (9 files)
- `backend/repositories/__init__.py`
- `backend/repositories/base.py`
- `backend/repositories/forecast_observation_repository.py`
- `backend/repositories/model_config_repository.py`
- `backend/repositories/notification_repository.py`
- `backend/repositories/supplier_repository.py`
- `backend/repositories/user_repository.py`
- `backend/repositories/utility_account_repository.py`
- `backend/repositories/price_repository.py`

### Models (16 files)
- `backend/models/__init__.py`
- `backend/models/community.py`
- `backend/models/connections.py`
- `backend/models/model_config.py`
- `backend/models/model_version.py`
- `backend/models/notification.py`
- `backend/models/observation.py`
- `backend/models/price.py`
- `backend/models/region.py`
- `backend/models/regulation.py`
- `backend/models/supplier.py`
- `backend/models/user.py`
- `backend/models/user_supplier.py`
- `backend/models/utility.py`
- `backend/models/utility_account.py`
- `backend/models/consent.py`

---

## P0 -- Critical (Fix Immediately)

### P0-01: ForecastObservationRepository has no error handling or rollback on write methods
**File:** `backend/repositories/forecast_observation_repository.py`, lines 30-99, 174-199, 201-226
**Severity:** CRITICAL -- data corruption risk

The three write methods (`insert_forecasts`, `insert_recommendation`, `update_recommendation_response`) have no `try/except` blocks and no `rollback()` calls. If any exception occurs mid-transaction (e.g., a constraint violation on the second chunk of `insert_forecasts`), the session is left in a dirty state. The first chunk may be committed while the second fails, or the session may be poisoned for subsequent operations.

Compare to `ModelConfigRepository.save_config()` (lines 136-198) which correctly wraps in try/except and calls `await self._db.rollback()` on failure.

**Impact:** Partial inserts into `forecast_observations` table; poisoned AsyncSession for subsequent callers sharing the same session scope.

**Recommendation:** Wrap each write method in try/except with `await self._db.rollback()` and raise `RepositoryError`, consistent with every other repository in the codebase.

---

### P0-02: ForecastObservationRepository.insert_forecasts commits per-chunk, not per-batch
**File:** `backend/repositories/forecast_observation_repository.py`, line 98
**Severity:** CRITICAL -- partial-write data integrity violation

The `insert_forecasts` method inserts in chunks of `_INSERT_BATCH_SIZE=20` rows, but calls `await self._db.commit()` only once at line 98 after the loop. However, because there is no error handling (P0-01), if the second chunk fails, the first chunk's INSERT has already been sent to the database within the same transaction -- but the absence of rollback means the transaction could be left in an ambiguous state depending on the driver behavior.

More critically, if the commit itself fails (e.g., network timeout to Neon), there is no rollback. The method returns `len(rows)` optimistically at line 99 even though the commit may not have succeeded.

**Recommendation:** Wrap the entire method in try/except. On failure, rollback and re-raise. Do not return a count until commit succeeds.

---

### P0-03: UserRepository._USER_COLUMNS does not include consent_given, data_processing_agreed, consent_date, or last_login
**File:** `backend/repositories/user_repository.py`, lines 24-34 vs. lines 68-73
**Severity:** CRITICAL -- silent data loss on reads

The `_USER_COLUMNS` constant used in every SELECT query does not include `consent_given`, `data_processing_agreed`, `consent_date`, or `last_login`. These columns exist in the database (they are written to by `record_consent()` at line 393 and `update_last_login()` at line 355).

The `_row_to_user()` function at lines 68-73 uses `data.get("consent_given", False)` with a fallback default. Because the column is never selected, it always returns `False` -- even for users who have explicitly granted consent. This means:

1. **GDPR compliance data is silently lost on reads** -- `consent_given` always appears `False`.
2. `last_login` always appears `None` even after being set.

**Impact:** GDPR audit failure. Any code that checks `user.consent_given` after fetching from the repository will incorrectly see `False`. If this gates data processing decisions, it could block legitimate users or violate consent records.

**Recommendation:** Add `consent_given, data_processing_agreed, consent_date, last_login` to the `_USER_COLUMNS` constant.

---

### P0-04: ModelConfigRepository.save_config race condition -- no SELECT FOR UPDATE on deactivation
**File:** `backend/repositories/model_config_repository.py`, lines 136-173
**Severity:** CRITICAL -- data integrity under concurrent writes

The `save_config` method performs a two-step mutation (deactivate old + insert new) within a single transaction but without any row-level locking. The comment at line 129 acknowledges a "single-writer assumption," but there is no enforcement. If two concurrent callers invoke `save_config` for the same `model_name`:

1. Both read `is_active=true` for the current config.
2. Both deactivate it (UPDATE sets `is_active=false`).
3. Both insert a new row with `is_active=true`.
4. Result: two active rows for the same model_name, violating the partial unique index.

**Impact:** The partial-index `(model_name) WHERE is_active=true` will cause a unique constraint violation on the second INSERT, but only if the index exists. If it does not exist (or is a non-unique index), both rows silently become active, causing `get_active_config` to return non-deterministic results.

**Recommendation:** Add `SELECT ... FOR UPDATE` on the current active row before the deactivate step, or use an `INSERT ... ON CONFLICT` pattern. The simplest fix is:
```sql
SELECT id FROM model_config
WHERE model_name = :model_name AND is_active = true
FOR UPDATE
```

---

## P1 -- High (Fix This Sprint)

### P1-01: No page_size upper bound on most list/pagination methods
**File:** `backend/repositories/user_repository.py` line 263, `backend/repositories/utility_account_repository.py` line 128, `backend/repositories/price_repository.py` line 279, `backend/repositories/supplier_repository.py` line 135
**Severity:** HIGH -- denial of service / memory exhaustion

Only `PriceRepository.get_historical_prices_paginated()` (line 579) clamps `page_size` to `max(1, min(100, page_size))`. All other `list()` methods accept the caller's `page_size` verbatim with no upper bound. A malicious or buggy client sending `page_size=1000000` could exhaust server memory or trigger an extremely expensive query.

**Impact:** An attacker or misconfigured client can cause OOM or database overload.

**Recommendation:** Add `page_size = max(1, min(MAX_PAGE_SIZE, page_size))` clamping at the start of every `list()` method. A project-wide constant (e.g., `MAX_PAGE_SIZE = 100`) in `base.py` would be ideal.

---

### P1-02: PriceRepository.update() performs read-then-write without locking
**File:** `backend/repositories/price_repository.py`, lines 194-248
**Severity:** HIGH -- lost update race condition

The `update()` method first calls `await self.get_by_id(id)` to check existence (line 206), then performs the UPDATE (line 210). Between the read and the write, another concurrent request could delete the row (the DELETE would succeed, then the UPDATE would match 0 rows but the method would return a fresh `get_by_id` result that is now None). The second `get_by_id` at line 244 after commit could also read stale cache data if the cache wasn't invalidated in the same transaction.

More importantly, the method does not check `result.rowcount` to verify the UPDATE actually matched a row. It always calls `get_by_id` again, which could return cached data or None.

**Recommendation:** Use `UPDATE ... RETURNING` instead of the separate read-check-write-reread pattern. This is already the pattern used in `UserRepository.update()`.

---

### P1-03: PriceRepository cache stampede mitigation has a single-retry design flaw
**File:** `backend/repositories/price_repository.py`, lines 417-422
**Severity:** HIGH -- under high concurrency, most requests fall through to DB

The stampede prevention in `get_current_prices` acquires a lock, and if the lock fails, sleeps 100ms and retries the cache once. If the cache is still empty (e.g., the lock holder is slow), the request silently returns an **empty list** to the caller rather than falling through to the database. This is because control falls to the DB query block only if the lock was acquired.

Wait -- re-reading: if `_acquire_cache_lock` returns False, it sleeps and checks cache. If cache still empty, it falls through to the DB query at line 425. Actually, the flow continues past the lock check. Let me re-verify...

After re-reading lines 417-435: the lock check is *not* inside an `if/else` that gates the DB query. The `if not await self._acquire_cache_lock(...)` block sleeps and checks cache, then `return`s if cached. If not cached, execution continues to the DB query. This is correct for the happy path. However, under heavy concurrency with Redis down, `_acquire_cache_lock` returns `False` (fail-closed at line 102), the cache check also fails, and then N concurrent requests all hit the database simultaneously -- the exact stampede scenario the lock was meant to prevent.

**Impact:** When Redis is down, all concurrent requests for the same cache key stampede the database.

**Recommendation:** When the lock cannot be acquired AND cache is empty, consider a brief exponential backoff retry loop (2-3 attempts) before falling through to the database, or return a 503 to shed load.

---

### P1-04: NotificationRepository.update_delivery() does not verify user_id ownership
**File:** `backend/repositories/notification_repository.py`, lines 181-244
**Severity:** HIGH -- authorization bypass potential

The `update_delivery` method's WHERE clause at line 219 filters only by `id = :nid`. It does not include `user_id` in the filter. If a caller passes a `notification_id` belonging to a different user, the delivery status will be updated. While this method is primarily called by internal services (NotificationDispatcher), any future API endpoint that exposes this functionality would allow cross-user notification modification.

Compare to `get_by_id()` at line 80 which correctly filters on both `id` and `user_id`.

**Recommendation:** Either add `user_id` to the WHERE clause, or clearly document that this method is internal-only and add an assertion or access control check.

---

### P1-05: SupplierRegistryRepository.list_suppliers and StateRegulationRepository.list_deregulated have unbounded result sets
**File:** `backend/repositories/supplier_repository.py`, lines 302-335
**Severity:** HIGH -- memory exhaustion on large datasets

`StateRegulationRepository.list_deregulated()` at line 329 adds `ORDER BY state_code` but no `LIMIT` clause. For state regulations this is bounded by ~51 rows (50 states + DC), so it is low risk today. However, `SupplierRegistryRepository.list_suppliers()` does have proper pagination (line 188).

More concerning: `StateRegulationRepository.get_by_state()` at line 294 uses `SELECT *` which returns all columns including any future columns that may contain large JSONB data. This is a minor concern but violates the explicit-columns pattern used everywhere else.

---

### P1-06: UserRepository.create() does not INSERT consent columns
**File:** `backend/repositories/user_repository.py`, lines 123-177
**Severity:** HIGH -- GDPR consent not persisted on user creation

The `create()` method's INSERT statement (lines 133-148) does not include `consent_given`, `data_processing_agreed`, or `consent_date` columns. The `UserCreate` model (validated at the API layer) requires both `consent_given=True` and `data_processing_agreed=True`, but this data is never written to the database row.

The consent values only reach the database if `record_consent()` is called separately (line 387). If this follow-up call fails or is omitted, the user row has `consent_given=FALSE` in the database despite the user having explicitly granted consent.

**Impact:** GDPR compliance gap -- consent is validated at the API layer but not durably stored in the same transaction as user creation.

**Recommendation:** Add `consent_given`, `data_processing_agreed`, `consent_date` to the INSERT column list in `create()`. Pass the values from the entity. This ensures atomicity.

---

## P2 -- Medium (Fix Soon)

### P2-01: Redundant import of `json` inside UserRepository.update_preferences
**File:** `backend/repositories/user_repository.py`, line 327
**Severity:** MEDIUM -- code hygiene

`import json` is already at the top of the file (line 9). The inner import at line 327 is redundant and suggests a copy-paste artifact.

---

### P2-02: `import builtins` usage for type hints is non-idiomatic
**Files:** `backend/repositories/price_repository.py` line 10, `backend/repositories/user_repository.py` line 8, `backend/repositories/utility_account_repository.py` line 8
**Severity:** MEDIUM -- readability / maintainability

These files import `builtins` and use `builtins.list[...]` as a type hint to avoid shadowing the built-in `list` with the method name `list()`. While functional, this is non-standard Python. The modern approach (Python 3.12+) is to use `from __future__ import annotations` or simply use the lowercase `list[...]` in type hints (which works at runtime in 3.12+).

**Recommendation:** Rename the `list()` methods to something more descriptive (e.g., `list_all()`, `find_all()`, `query()`) to avoid the name collision. Or use `from __future__ import annotations` at the top of each file.

---

### P2-03: PriceRepository._acquire_cache_lock fail-closed prevents all cache-miss DB reads during Redis outage
**File:** `backend/repositories/price_repository.py`, lines 85-102
**Severity:** MEDIUM -- degraded availability

The docstring and comment explicitly state "fail-closed" behavior: when Redis is down, `_acquire_cache_lock` returns `False`. In `get_current_prices`, this causes a cache re-check and then falls through to DB. But in isolation, the fail-closed design means that if Redis is simultaneously down (cache miss) AND the lock fails, the caller sleeps 100ms before retrying cache (which will also fail), then hits the DB. This adds latency but does work.

However, the `_set_in_cache` method at line 104 silently swallows the Redis write failure, so subsequent requests will also miss cache and hit DB. This creates a sustained elevated DB load until Redis recovers.

**Recommendation:** Consider a circuit breaker on the cache layer to skip cache operations entirely when Redis is known-down, removing the 100ms sleep penalty per request.

---

### P2-04: UtilityAccountRepository.get_by_user returns up to 100 accounts without further pagination
**File:** `backend/repositories/utility_account_repository.py`, lines 183-185
**Severity:** MEDIUM -- hidden hard limit

`get_by_user()` calls `self.list(page=1, page_size=100, ...)`. If a user has more than 100 utility accounts, the excess is silently truncated. While 100 accounts per user is unlikely, the method name does not indicate a limit exists.

**Recommendation:** Either remove the limit (use a large but documented cap), or rename to `get_by_user(limit=100)` with an explicit parameter.

---

### P2-05: ForecastObservationRepository.backfill_actuals logs warning unconditionally when no region supplied
**File:** `backend/repositories/forecast_observation_repository.py`, lines 156-157
**Severity:** MEDIUM -- log noise

The `logger.warning()` at line 154-157 fires every time `backfill_actuals()` is called without a region, even if the total rows needing backfill is small. This will produce a warning in every scheduled cron invocation. The limit-hit warning at lines 164-170 is appropriate, but the preemptive warning is noisy.

**Recommendation:** Remove the preemptive warning at line 154. The post-query check at line 163 already handles the case where the limit was actually hit.

---

### P2-06: PriceRepository uses SELECT * in list_latest_by_regions subquery
**File:** `backend/repositories/price_repository.py`, line 341
**Severity:** MEDIUM -- performance / forward compatibility

The `list_latest_by_regions` method uses `SELECT *, ROW_NUMBER() ...` in the subquery. When new columns are added to `electricity_prices`, they will be included in the subquery's sort and transfer, increasing query cost. The outer SELECT uses `_PRICE_COLUMNS`, so only known columns are returned, but the inner scan is wider than necessary.

**Recommendation:** Replace `SELECT *` in the subquery with the explicit column list from `_PRICE_COLUMNS`.

---

### P2-07: UserRepository.update uses model_dump(exclude_unset=True) which may include unexpected fields
**File:** `backend/repositories/user_repository.py`, lines 203-247
**Severity:** MEDIUM -- defense in depth

The `update()` method uses `entity.model_dump(exclude_unset=True)` then filters keys against `_UPDATABLE_COLUMNS`. This is correct for preventing SQL injection on column names. However, the `User` model has many fields that are not in `_UPDATABLE_COLUMNS` (e.g., `consent_given`, `data_processing_agreed`, `last_login`). If a caller constructs a `User` with these fields set and calls `update()`, the values are silently dropped. This could be confusing.

**Recommendation:** Document that `update()` only updates the subset in `_UPDATABLE_COLUMNS`, or raise a warning/error if excluded fields are present in the dump.

---

### P2-08: No index hint documentation for frequently-filtered columns
**Files:** Multiple repositories
**Severity:** MEDIUM -- performance at scale

Several queries filter on columns that should have indexes:
- `UserRepository.get_by_email()` -- `WHERE email = :email`
- `UserRepository.get_by_stripe_customer_id()` -- `WHERE stripe_customer_id = :customer_id`
- `UserRepository.get_users_by_region()` -- `WHERE region = :region`
- `NotificationRepository.get_by_delivery_status()` -- `WHERE user_id = :uid AND delivery_status = :status`
- `PriceRepository.get_current_prices()` -- `WHERE region = :region AND utility_type = :utility_type`

While the migrations likely create these indexes, there is no documentation or assertion in the repository layer confirming their existence. As the dataset grows, missing indexes on these columns would cause full table scans.

**Recommendation:** Add a comment block at the top of each repository documenting the expected indexes, or add a startup health check that verifies critical indexes exist.

---

### P2-09: NotificationRepository._row_to_notification uses dict-style key access but column order is fragile
**File:** `backend/repositories/notification_repository.py`, lines 36-40, 43-61
**Severity:** MEDIUM -- maintenance risk

The `_NOTIFICATION_COLUMNS` constant at line 36 defines a string of column names used in SELECT queries. The `_row_to_notification` function at line 43 uses `row["column_name"]` key access (via `.mappings()`). This is correct and robust. However, if `_NOTIFICATION_COLUMNS` gets out of sync with the actual table schema (e.g., a migration adds a column that the function expects), queries will fail at runtime, not at startup.

**Recommendation:** Consider adding a lightweight startup or test-time schema validation that ensures `_NOTIFICATION_COLUMNS` matches the actual table definition.

---

### P2-10: CommunityPost and CommunityPostCreate duplicate validator logic
**File:** `backend/models/community.py`, lines 62-84 and lines 99-121
**Severity:** MEDIUM -- DRY violation

The `validate_post_type` and `validate_utility_type` validators are identically duplicated between `CommunityPost` and `CommunityPostCreate`. If a new post type or utility type is added, both validators must be updated.

**Recommendation:** Extract the validation sets into module-level constants (e.g., `VALID_POST_TYPES = {"tip", "rate_report", ...}`) and reference them from both validators.

---

## P3 -- Low / Housekeeping

### P3-01: BaseRepository abstract class uses `str` for ID type instead of `UUID`
**File:** `backend/repositories/base.py`, lines 52, 78, 92
**Severity:** LOW -- type safety

The project uses UUID primary keys throughout, but the `BaseRepository` abstract methods define `id: str`. While all UUIDs are stored as strings in the repository layer, using `uuid.UUID` as the parameter type would catch accidental non-UUID string arguments at the type-checking level.

---

### P3-02: Supplier model field name inconsistency: green_energy vs green_energy_provider
**File:** `backend/repositories/supplier_repository.py`, line 210 vs `backend/models/supplier.py`, line 128
**Severity:** LOW -- naming inconsistency

The DB column is `green_energy` (line 210 of supplier_repository.py: `row["green_energy"]`), but the dict key returned by `list_suppliers()` is `green_energy_provider`. The `Supplier` Pydantic model also uses `green_energy_provider`. This mapping is correct but could cause confusion when debugging raw SQL vs. API responses.

---

### P3-03: PriceRepository.get_by_id returns cached data that may be stale after concurrent updates
**File:** `backend/repositories/price_repository.py`, lines 115-147
**Severity:** LOW -- cache consistency

`get_by_id` checks the cache first and returns cached data without validating freshness. The `update()` method does invalidate the cache (line 241), but a concurrent `get_by_id` between the `update` commit and the cache invalidation could return stale data. Given the 60s default TTL, this is a minor window.

---

### P3-04: ForecastObservation model has optional created_at (None default)
**File:** `backend/models/observation.py`, line 27
**Severity:** LOW -- schema completeness

`ForecastObservation.created_at` is `datetime | None = None`, while the database column has `DEFAULT now()`. This means a round-tripped object could have `created_at=None` if the column was not included in the SELECT. The repository's `insert_forecasts` does not select `created_at` after insert.

---

### P3-05: StateRegulation model does not have ConfigDict(from_attributes=True)
**File:** `backend/models/regulation.py`, lines 12-28
**Severity:** LOW -- potential ORM incompatibility

Unlike most other models in the codebase, `StateRegulation` does not set `model_config = ConfigDict(from_attributes=True)`. If future code attempts to construct it from an ORM row or named tuple, it would fail. Since the repository returns `dict(row)` (line 298), this works today but is inconsistent.

---

### P3-06: UtilityAccount model has account_number_encrypted as `bytes | None` but repository handles it as a parameter
**File:** `backend/models/utility_account.py`, line 28 vs `backend/repositories/utility_account_repository.py`, line 74
**Severity:** LOW -- type coercion edge case

The model defines `account_number_encrypted: bytes | None`, and the repository passes it directly as a SQL parameter. asyncpg handles `bytes` as `BYTEA` correctly, but if the value is a `memoryview` or another bytes-like type, it could fail. This is a defensive concern, not an active bug.

---

### P3-07: Missing `Water` utility type in `UtilityType` enum
**File:** `backend/models/utility.py`, lines 11-19 vs `backend/models/community.py`, line 32
**Severity:** LOW -- enum gap

`CommunityUtilityType` includes `WATER = "water"` but the main `UtilityType` enum does not. The `water_rate_service.py` exists in services, suggesting water is a supported utility type. The enum should be extended for consistency.

---

### P3-08: Inconsistent error wrapping in SupplierRegistryRepository vs other repositories
**File:** `backend/repositories/supplier_repository.py`, lines 223-224, 273-274
**Severity:** LOW -- inconsistent patterns

`SupplierRegistryRepository` uses `raise RepositoryError(f"...: {str(e)}", e)` with `str(e)` in the message, while other repos (e.g., `UserRepository`) use `{str(e)}` consistently. This is correct but some repositories (e.g., `UtilityAccountRepository` line 54) use `{e}` directly (relying on implicit str conversion). Minor inconsistency.

---

### P3-09: PriceRepository.get_price_trend_aggregates CTE scans entire partition for ROW_NUMBER
**File:** `backend/repositories/price_repository.py`, lines 826-875
**Severity:** LOW -- query optimization opportunity

The `numbered` CTE assigns `ROW_NUMBER()` and `COUNT(*) OVER()` to every row in the date range. For very large date ranges with millions of price rows, this could be expensive. The `bounds` CTE then uses `LIMIT 1` to extract the third value, but the full window function has already been computed.

**Recommendation:** For large datasets, consider using `NTILE(3)` instead of ROW_NUMBER + manual third computation, or pre-compute the count in a separate CTE.

---

## Files With No Issues Found

- `backend/repositories/__init__.py` -- Clean re-export module, all referenced classes exist.
- `backend/models/__init__.py` -- Clean re-export module, all referenced classes exist.
- `backend/models/model_config.py` -- Well-structured Pydantic model with appropriate field types and defaults.
- `backend/models/model_version.py` -- Comprehensive A/B testing models with proper validation.
- `backend/models/notification.py` -- Thorough delivery-tracking model with migration version documentation.
- `backend/models/connections.py` -- Good validation (consent required, account number regex), proper Literal types.
- `backend/models/user_supplier.py` -- Proper input validation with regex patterns and consent enforcement.
- `backend/models/utility.py` -- Clean enum definitions with comprehensive unit coverage.
- `backend/models/region.py` -- Thorough enum with all 50 states + DC + international regions.
- `backend/models/consent.py` -- GDPR-compliant model with proper audit trail fields and nullable user_id documentation.

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| P0 -- Critical | 4 | Missing error handling/rollback in ForecastObservationRepository; User columns missing from SELECT (GDPR consent lost on read); Race condition in model config activation |
| P1 -- High | 6 | Unbounded page_size on list endpoints; Read-then-write without locking; Cache stampede under Redis failure; Missing user_id check in notification delivery update; Consent columns not INSERTed on user creation |
| P2 -- Medium | 10 | Redundant imports; Non-idiomatic builtins usage; Hidden hard limits; Log noise; SELECT *; DRY violations in validators |
| P3 -- Low | 9 | Type safety improvements; Naming inconsistencies; Enum gaps; Minor cache staleness; Query optimization opportunities |
| **Total** | **29** | |

### Strengths

1. **Consistent parameterized queries throughout.** Every repository uses `text()` with `:named_params` -- zero raw string interpolation of user inputs into SQL. No SQL injection vectors found.
2. **Good separation of concerns.** The repository layer is cleanly separated from services. Pydantic models are pure data contracts with no ORM coupling.
3. **Proper batch insert pattern.** `PriceRepository.bulk_create()` and `ForecastObservationRepository.insert_forecasts()` both use multi-row VALUES with chunking to stay within parameter limits.
4. **Cache stampede prevention.** `PriceRepository` implements distributed lock-based cache stampede prevention via Redis `SET NX PX`.
5. **Column allowlist for dynamic updates.** `UserRepository._UPDATABLE_COLUMNS` prevents arbitrary column injection in dynamic UPDATE SET clauses.
6. **Backfill safety.** `ForecastObservationRepository.backfill_actuals()` uses a CTE with LIMIT to prevent unbounded memory usage.
7. **GDPR model design.** `ConsentRecord`, `DeletionLog`, and `UserDataExport` models are well-designed for regulatory compliance.
8. **Correct AsyncSession handling.** The comment at `PriceRepository` line 619 correctly avoids `asyncio.gather` on shared AsyncSession.
9. **Removed deprecated class with migration stub.** `_RemovedSupplierRepository` raises `ImportError` with clear migration guidance.

### Top Priority Actions

1. **P0-03 (URGENT):** Add `consent_given, data_processing_agreed, consent_date, last_login` to `_USER_COLUMNS` in `user_repository.py`. This is a one-line fix that restores GDPR consent visibility.
2. **P0-01 + P0-02:** Add try/except/rollback to all write methods in `forecast_observation_repository.py`.
3. **P0-04:** Add `SELECT ... FOR UPDATE` to `model_config_repository.save_config()` deactivation step.
4. **P1-01:** Add `page_size` clamping to all `list()` methods (define `MAX_PAGE_SIZE` in `base.py`).
5. **P1-06:** Add consent columns to `UserRepository.create()` INSERT statement.
