# Audit Report: Backend Repositories & Models
**Date:** 2026-03-19
**Scope:** Data access layer, ORM models, query patterns
**Files Reviewed:**
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/__init__.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/base.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/price_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/forecast_observation_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/model_config_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/notification_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/supplier_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/user_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/utility_account_repository.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/__init__.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/community.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/connections.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/consent.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/model_config.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/model_version.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/notification.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/observation.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/price.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/region.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/regulation.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/supplier.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/user.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/user_supplier.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/utility.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/utility_account.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/repositories.py`

***

## P0 -- Critical (Fix Immediately)

### P0-1: DeletionLogORM `user_id` FK has `ondelete="SET NULL"` but column is `nullable=False`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/repositories.py`, lines 50-52

```python
user_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=False
)
```

The `ondelete="SET NULL"` directive instructs PostgreSQL to set `user_id` to `NULL` when the referenced user is deleted, but the column is declared `nullable=False`. This will cause a runtime constraint violation (`NOT NULL constraint violated`) whenever a user with deletion log entries is deleted, which is exactly the GDPR deletion path. The whole point of `SET NULL` on a deletion log is to preserve the audit record after the user is gone. This is a data integrity bug that will crash the GDPR deletion endpoint if the user has any deletion log entries.

**Fix:** Change to `nullable=True`, or switch to `ondelete="CASCADE"` if deletion logs should be purged with the user (unlikely for an audit trail). The correct fix is almost certainly `nullable=True` to allow orphaned audit records.

---

### P0-2: `PriceRepository.update()` cache race -- stale read after invalidation

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/price_repository.py`, lines 206-244

```python
await self._db.commit()

# Invalidate cache
cache_key = self._cache_key("id", id)
if self._cache:
    await self._cache.delete(cache_key)

return await self.get_by_id(id)  # <-- re-fetches and re-caches
```

The method commits, deletes the cache key, then calls `get_by_id()` which may re-cache. However, between `commit()` and `delete()`, another request could read the stale cached value. More critically, only the `id`-keyed cache entry is invalidated. The `current`, `latest`, and `list` cache entries for the affected region/supplier remain stale. This means `get_current_prices()` and `get_latest_by_supplier()` will serve outdated data until their TTL expires.

**Impact:** Users may see stale price data for up to 60 seconds after a price update.

**Fix:** Either (a) invalidate region-level cache keys in `update()` and `create()`, or (b) use write-through caching with versioned keys, or (c) accept eventual consistency and document it.

---

### P0-3: `_row_to_price()` crashes on `NULL` `carbon_intensity` due to unconditional `float()` conversion path

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/price_repository.py`, lines 42-44

```python
carbon_intensity=float(row["carbon_intensity"])
if row.get("carbon_intensity") is not None
else None,
```

This uses `row["carbon_intensity"]` (which would raise `KeyError` on a mapping without the key) inside the true branch, but `row.get("carbon_intensity")` (which returns `None` for missing keys) in the condition. If the key exists but its value is `None`, `float(None)` raises `TypeError`. More importantly, the `row["carbon_intensity"]` lookup could diverge from the `row.get()` check depending on the SQL result set. This is not a current bug since the column is always selected in `_PRICE_COLUMNS`, but the inconsistent access pattern is fragile.

Actually, re-examining: `row.get("carbon_intensity")` returns `None` when the column value IS `None`, and the conditional correctly guards against that. The `float(row["carbon_intensity"])` in the truthy branch is safe because the `get()` would have returned `None` in that case. **Downgraded to P3** on re-analysis -- the logic is technically correct, just uses inconsistent access patterns (`row["key"]` vs `row.get("key")`) in the same expression.

---

## P1 -- High (Fix This Sprint)

### P1-1: `ForecastObservationRepository.backfill_actuals()` logs warning unconditionally when no region filter

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/forecast_observation_repository.py`, lines 153-157

```python
params = {"backfill_limit": self._BACKFILL_LIMIT}
logger.warning(
    "No region filter supplied; capping backfill at LIMIT=%d ...",
    self._BACKFILL_LIMIT,
)
```

The warning is logged **before** the query executes, meaning every scheduled call to `backfill_actuals()` without a region filter emits a warning even if there are zero rows to update. This creates log noise in normal operation (e.g., the CF Worker cron trigger calls this every 6 hours). The warning at line 164 that fires when the limit is actually hit is the correct one. The pre-query warning should be `logger.info()` at most.

---

### P1-2: `UserRepository._row_to_user()` selects columns not in `_USER_COLUMNS`, silently defaults

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/user_repository.py`, lines 24-34 and 37-74

The `_USER_COLUMNS` constant lists the columns selected from the database:
```python
_USER_COLUMNS = """
    id::text, email, name, region, preferences,
    current_supplier, is_active, is_verified,
    created_at, updated_at,
    stripe_customer_id, subscription_tier,
    email_verified, current_tariff,
    average_daily_kwh, household_size,
    current_supplier_id::text,
    utility_types, annual_usage_kwh,
    onboarding_completed
"""
```

But `_row_to_user()` also reads `consent_given`, `consent_date`, `data_processing_agreed`, and `last_login` via `data.get()` with defaults. These columns are NOT in `_USER_COLUMNS` and will never be populated from the database query. The User model will always have `consent_given=False`, `consent_date=None`, `data_processing_agreed=False`, and `last_login=None` regardless of actual DB values.

This means:
- `last_login` is written by `update_last_login()` but never read back via `get_by_id()`.
- GDPR consent fields on the User model are always defaulted, even if `record_consent()` updated them.
- Any downstream code relying on `user.consent_given` from a repository read will get stale/incorrect values.

**Fix:** Add `consent_given, consent_date, data_processing_agreed, last_login` to `_USER_COLUMNS`.

---

### P1-3: `UserRepository.create()` does not persist `utility_types`, `annual_usage_kwh`, or `onboarding_completed`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/user_repository.py`, lines 130-170

The `INSERT INTO users` statement lists 16 columns but omits `utility_types`, `annual_usage_kwh`, `onboarding_completed`, and `current_supplier_id` even though these are in `_USER_COLUMNS` for reads and in `_UPDATABLE_COLUMNS` for updates. A newly created user will have these fields set to DB defaults (`NULL` / `false`) regardless of what was passed in the `User` entity.

**Fix:** Add the missing columns to the INSERT statement, or document that they can only be set via `update()`.

---

### P1-4: `PriceRepository` cache stampede prevention has a single-retry fallback

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/price_repository.py`, lines 417-422

```python
if not await self._acquire_cache_lock(cache_key):
    await asyncio.sleep(0.1)
    cached = await self._get_from_cache(cache_key)
    if cached:
        return [Price(**p) for p in cached]
```

When the lock is not acquired, the code sleeps 100ms and tries the cache once more. If the cache is still empty (the other request hasn't finished), it falls through to the database query anyway. Under high concurrency with a cold cache, many requests will still stampede the DB after the 100ms sleep. The lock key also has no cleanup path if the lock holder crashes -- the 5-second TTL (`px=5000`) provides some safety but is arbitrary.

Additionally, this stampede prevention pattern is only used in `get_current_prices()` but not in `get_latest_by_supplier()`, `get_historical_prices()`, or `get_price_statistics()`, making the protection inconsistent.

---

### P1-5: `NotificationRepository.update_delivery()` does not scope update to `user_id`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/notification_repository.py`, lines 196-219

```python
sql = "UPDATE notifications SET " + ", ".join(set_clauses) + " WHERE id = :nid"
```

The `WHERE` clause uses only the notification `id`, with no `user_id` filter. While `get_by_id()` does enforce `user_id`, `update_delivery()` accepts only `notification_id` and could theoretically update a notification belonging to a different user. This is an authorization gap since the NotificationDispatcher (the primary caller) operates across users.

For the current call patterns this is likely safe (dispatcher has legitimate access to all notifications), but it violates the principle of least privilege applied in `get_by_id()`.

---

### P1-6: `SupplierRegistryRepository.list_suppliers()` issues two sequential queries where one `COUNT(*) OVER()` would suffice

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/supplier_repository.py`, lines 161-196

Two separate round-trips to the database are made: one for `COUNT(*)` and one for the paginated data. Since supplier data is semi-static and the table is small, the performance impact is minor, but this is an unnecessary N+1 pattern. A `COUNT(*) OVER()` window function in the data query would eliminate one round-trip.

---

### P1-7: `SupplierRegistryRepository` hardcodes `tariff_types: ["fixed", "variable"]` for every supplier

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/supplier_repository.py`, lines 214 and 265

```python
"tariff_types": ["fixed", "variable"],
```

This is hardcoded in both `list_suppliers()` and `get_by_id()`. Every supplier is reported as offering both fixed and variable tariffs regardless of what tariff data actually exists. This is misleading to users.

**Fix:** Either query the actual tariff types from a tariffs table, or add a `tariff_types` column to `supplier_registry` and read it.

---

## P2 -- Medium (Fix Soon)

### P2-1: `BaseRepository` declares `id` parameter as `str` but project uses UUID primary keys

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/base.py`, lines 52, 78, 92

```python
async def get_by_id(self, id: str) -> T | None:
async def update(self, id: str, entity: T) -> T | None:
async def delete(self, id: str) -> bool:
```

The CLAUDE.md states "All primary keys use UUID type", but the base repository signature uses `str`. While UUIDs are passed as strings in the raw SQL queries, using `uuid.UUID` as the type annotation would provide stronger type safety and automatic validation at the API layer boundary.

---

### P2-2: `PriceRepository` silently swallows all cache errors

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/price_repository.py`, lines 79-83, 99-102, 112-113

Multiple `except Exception: pass` blocks throughout the caching layer:
```python
except Exception:
    pass
```

While fail-open caching is a reasonable strategy, completely swallowing exceptions including `ConnectionError`, `TimeoutError`, and `AuthenticationError` makes it impossible to detect a persistently broken Redis connection. At minimum, a `logger.debug()` or a counter metric should be emitted.

The same pattern appears in `SupplierRegistryRepository._cache_set()` (line 111) and `_cache_get()` (line 98-99).

---

### P2-3: `ForecastObservationRepository` mixes `result.fetchone()` / `result.fetchall()` with `result.mappings()`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/forecast_observation_repository.py`, lines 246-247, 274-280

Methods like `get_accuracy_metrics()` use positional tuple access (`row.total`, `row.mape`) via `result.fetchone()`, while other repositories consistently use `result.mappings().first()` with dictionary-style access. This inconsistency is not a bug (SQLAlchemy Row supports both), but it creates a maintenance hazard: if the column order in the SELECT changes, the positional access breaks silently.

---

### P2-4: `PriceRepository` does not validate or clamp `page_size` in `list()` method

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/price_repository.py`, lines 279-314

```python
async def list(self, page: int = 1, page_size: int = 10, **filters: Any) -> list[Price]:
```

Unlike `get_historical_prices_paginated()` which clamps `page_size` to 1-100 (line 579), the generic `list()` method passes `page_size` directly to `LIMIT` without validation. A caller could pass `page_size=1000000` and dump the entire table.

The same issue exists in `UserRepository.list()` (line 263), `UtilityAccountRepository.list()` (line 125), and `NotificationRepository` methods (though those have a hardcoded `limit=50` default).

---

### P2-5: `CommunityPost` model uses `str` for `utility_type` and `post_type` instead of the defined Enums

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/community.py`, lines 45-47

```python
utility_type: str = Field(..., max_length=30)
post_type: str = Field(..., max_length=20)
```

The file defines `PostType` and `CommunityUtilityType` enums (lines 17-34), but the `CommunityPost` model uses plain `str` with `field_validator` to enforce allowed values. This is a weaker contract than using the enum directly: it allows construction with invalid values before validation runs, doesn't provide IDE autocomplete, and duplicates the valid-value set (once in the enum, once in the validator set literal).

The same duplication exists in `CommunityPostCreate` (lines 94-121).

---

### P2-6: `UserRepository.update()` uses `model_dump(exclude_unset=True)` which may omit intentional `None` values

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/user_repository.py`, lines 207-213

```python
updates = entity.model_dump(exclude_unset=True)
```

If a caller constructs a `User` without setting a field, it will not appear in the update. But if they explicitly set a field to `None` to clear it, `exclude_unset=True` still correctly includes it. This is actually fine for Pydantic v2. However, the method receives the full `User` entity rather than a partial `UserUpdate`, meaning callers must pass a complete `User` object even for single-field updates. This leads to unnecessary data transfer and the possibility of accidentally overwriting fields if the caller doesn't first fetch the current state.

---

### P2-7: `ConsentRecordORM.id` and `DeletionLogORM.id` use `String(36)` for UUID storage

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/repositories.py`, lines 28, 49

```python
id: Mapped[str] = mapped_column(String(36), primary_key=True)
```

UUIDs stored as `String(36)` instead of the PostgreSQL native `UUID` type waste space (36 bytes vs 16 bytes), prevent the database from enforcing UUID format, and are slower for index lookups. The rest of the project uses UUID primary keys per CLAUDE.md. This ORM model should use `sqlalchemy.dialects.postgresql.UUID` or `sqlalchemy.Uuid`.

The same issue applies to `user_id` foreign keys in both ORM models (lines 29-31, 50-52).

---

### P2-8: `ConsentRepository.create()` and `DeletionLogRepository.create()` commit inside the repository

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/compliance/repositories.py`, lines 107-108, 292-294

```python
self.session.add(orm_record)
await self.session.commit()
```

Both `create()` methods commit the transaction immediately. This breaks composability -- the caller cannot bundle consent/deletion-log creation into a larger atomic transaction. Notably, `ConsentRepository.delete_by_user_id()` explicitly does NOT commit (line 226-228, with a comment explaining why), showing awareness of this pattern. The inconsistency suggests `create()` methods should also defer commit to the caller.

`DeletionLogRepository.create()` is particularly problematic: if the GDPR deletion flow creates a deletion log and then the subsequent user deletion fails, the log entry has already been committed and cannot be rolled back.

---

### P2-9: `ForecastObservationRepository.backfill_actuals()` JOIN condition may match wrong prices

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/forecast_observation_repository.py`, lines 114-127

```sql
AND fo.forecast_hour = EXTRACT(HOUR FROM ep.timestamp)
AND ep.timestamp >= fo.created_at - INTERVAL '1 hour'
AND ep.timestamp <= fo.created_at + INTERVAL '25 hours'
```

The join matches on `forecast_hour = EXTRACT(HOUR FROM ep.timestamp)` within a 26-hour window around `created_at`. If multiple prices exist for the same hour within that window (e.g., prices from different suppliers or updated prices), the UPDATE will non-deterministically pick one. The query does not have a `DISTINCT ON` or `ORDER BY` to select the most appropriate match (e.g., latest price, or price from the same supplier as the forecast).

---

### P2-10: `Price` model has `use_enum_values=True` which strips enum type safety

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/price.py`, lines 39-41

```python
model_config = ConfigDict(
    from_attributes=True, json_encoders={Decimal: str}, use_enum_values=True
)
```

With `use_enum_values=True`, accessing `price.region` returns a string like `"us_ct"` instead of a `Region.US_CT` enum member. This means downstream code cannot rely on `isinstance(price.region, Region)` checks, and enum methods like `price.region.is_us` or `price.region.state_code` are not available on the model instance. The repository layer already works around this with `if hasattr(region, "value")` checks, but this should not be necessary.

The same issue applies to `Supplier` (line 108), `UtilityAccount` (line 21), `UtilityAccountCreate` (line 38), and `UtilityAccountResponse` (line 62).

---

### P2-11: `UtilityAccountRepository.get_by_user()` and `get_by_user_and_type()` use `page_size=100` as an unbounded proxy

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/utility_account_repository.py`, lines 183-189

```python
async def get_by_user(self, user_id: str) -> builtins.list[UtilityAccount]:
    return await self.list(page=1, page_size=100, user_id=user_id)
```

A user with more than 100 utility accounts would silently lose data. While 100 is a reasonable practical limit, the method name `get_by_user` implies "get all", not "get first 100". Either rename to make the limit explicit, or implement proper pagination/iteration.

---

## P3 -- Low / Housekeeping

### P3-1: Duplicate `import json` in `UserRepository.update_preferences()`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/user_repository.py`, line 327

```python
async def update_preferences(self, user_id: str, ...) -> User | None:
    try:
        import json  # <-- already imported at module level (line 9)
```

`json` is already imported at the top of the file. This local import is unnecessary.

---

### P3-2: `_row_to_price()` inconsistent access: `row["key"]` vs `row.get("key")`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/price_repository.py`, lines 32-46

Some fields use `row["key"]` (raises `KeyError` on missing) while others use `row.get("key")` (returns `None` on missing). Since all columns are explicitly selected via `_PRICE_COLUMNS`, they should all be present. Using `row["key"]` consistently would surface bugs faster; using `row.get("key")` consistently would be more defensive. The current mix is neither.

---

### P3-3: `CommunityPost` and `CommunityPostCreate` duplicate validation logic

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/community.py`, lines 62-84 and 99-121

The `validate_post_type` and `validate_utility_type` field validators are copy-pasted between `CommunityPost` and `CommunityPostCreate`, including identical valid-value sets. If a new post type or utility type is added, both must be updated. Extract the validators into shared functions or use the defined enums directly.

---

### P3-4: `ModelConfigRepository` and `NotificationRepository` not exported from `repositories/__init__.py`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/__init__.py`

`ModelConfigRepository` and `NotificationRepository` are not listed in `__all__` or imported in the package `__init__.py`. While they work fine when imported directly, this inconsistency means some repositories are discoverable via `from repositories import X` and others are not.

---

### P3-5: `StateRegulationRepository.get_by_state()` uses `SELECT *` instead of explicit columns

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/supplier_repository.py`, lines 293-295

```python
result = await self._db.execute(
    text("SELECT * FROM state_regulations WHERE state_code = :code"),
```

`SELECT *` returns all columns including any future additions, which may include sensitive data or cause unexpected serialization issues. All other repositories in this layer use explicit column lists.

The same issue exists in `list_deregulated()` at line 313.

---

### P3-6: `PriceRegion` short-form aliases use `type: ignore` comments

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/region.py`, lines 121-125

```python
PriceRegion.NY = Region.US_NY  # type: ignore[attr-defined]
PriceRegion.CA = Region.US_CA  # type: ignore[attr-defined]
```

Monkey-patching enum classes with `type: ignore` is fragile and prevents type checkers from catching misuse. Consider using a lookup dict or helper function instead.

---

### P3-7: `Notification` model uses `str` for `type` field without validation

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/notification.py`, lines 57-58

```python
type: str = Field(default="info", max_length=50)
```

Unlike `delivery_status` and `delivery_channel` which use `Literal` types, the notification `type` field accepts any string up to 50 characters. If there are known notification types (info, warning, alert, etc.), a `Literal` or enum constraint would prevent invalid values.

---

### P3-8: `UtilityAccount.account_number_encrypted` is `bytes | None` which may conflict with JSON serialization

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/utility_account.py`, line 28

```python
account_number_encrypted: bytes | None = None
```

A `bytes` field in a Pydantic model will fail default JSON serialization. The `UtilityAccountResponse` correctly excludes this field, but if the `UtilityAccount` model is ever serialized directly (e.g., in logs or cache), it will raise a `TypeError`.

---

### P3-9: `ABTest.status` field uses plain `str` instead of a `Literal` type

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/model_version.py`, line 84

```python
status: str = Field(default="running")
```

The docstring says the lifecycle is `running -> completed | stopped`, but the field accepts any string. A `Literal["running", "completed", "stopped"]` would enforce the constraint.

---

### P3-10: `UserPreferences.preferred_usage_hours` has no range validation

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/user.py`, line 51

```python
preferred_usage_hours: list[int] = Field(default_factory=list)
```

Hours should be 0-23 but there is no element-level validation. A user could submit `[25, -1, 100]` and it would be stored.

---

### P3-11: `PriceRepository.get_hourly_price_averages()` does not filter by `utility_type`

**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/price_repository.py`, lines 877-926

Unlike `get_current_prices()`, `get_historical_prices()`, and `get_price_statistics()`, this method does not accept or filter by `utility_type`. In a multi-utility system, it would aggregate electricity and gas prices together in the hourly averages, producing meaningless results.

The same omission exists in `get_supplier_price_stats()` (lines 928-985).

---

***

## Files With No Issues Found

- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/regulation.py` -- Clean, simple Pydantic models with appropriate Field constraints.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/utility.py` -- Well-structured enums with comprehensive unit coverage and display labels.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/user_supplier.py` -- Clean request/response models with proper regex validation.

## Summary

**Overall Assessment:** The repository and model layer is well-architected with consistent use of raw SQL via `text()`, proper parameterized queries (no SQL injection risk), and a clean separation between Pydantic models and data access. The codebase shows strong evidence of iterative hardening (stampede prevention, batch inserts, backfill limits, GDPR compliance). However, several drift issues have accumulated:

| Severity | Count | Key Themes |
|----------|-------|------------|
| P0 | 1 (confirmed) | DeletionLogORM nullable/SET NULL contradiction |
| P1 | 7 | Missing SELECT columns in UserRepository, missing INSERT columns, cache inconsistency, hardcoded tariff types |
| P2 | 11 | UUID type usage inconsistency, transaction management in compliance repos, enum type safety erosion, missing utility_type filters |
| P3 | 11 | Duplicate code, minor validation gaps, housekeeping |

**Top 3 Actionable Recommendations:**

1. **Fix P0-1 immediately** -- the `DeletionLogORM` nullable contradiction will crash the GDPR deletion path.
2. **Fix P1-2 (UserRepository column drift)** -- `consent_given`, `consent_date`, `data_processing_agreed`, and `last_login` are written but never read back, meaning the User model from repository reads has incorrect GDPR consent state.
3. **Fix P1-3 (UserRepository INSERT gaps)** -- new users lose `utility_types`, `annual_usage_kwh`, `onboarding_completed`, and `current_supplier_id` on creation.

The P0-3 finding was downgraded during analysis -- the `carbon_intensity` conversion is technically correct despite the inconsistent access pattern.
