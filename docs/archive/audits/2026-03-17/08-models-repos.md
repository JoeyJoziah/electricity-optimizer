# Audit Report: Models & Repositories
## Date: 2026-03-17

---

### Executive Summary

The models and repository layers are well-structured: all raw SQL uses parameterized `text()` bindings, the Repository pattern is consistently applied, and bulk-insert chunking is in place. However, two P0 issues require immediate attention: a silent data-loss bug in `_USER_COLUMNS` causes GDPR consent fields to always silently default to `False` on every user read, and an asyncio-shared-session race condition exists in `get_historical_prices_paginated`. Several P1 gaps cover missing indexes on hot query paths, hardcoded data embedded in repository return values, and unvalidated Region values in request schemas.

---

### Findings

---

#### P0 — Critical

**[P0-01] GDPR consent fields silently return wrong defaults on every user read**
- **File:** `backend/repositories/user_repository.py` — lines 23–33 (`_USER_COLUMNS`), lines 67–69 (`_row_to_user`)
- **Description:** `_USER_COLUMNS` does not include `consent_given`, `consent_date`, or `data_processing_agreed`. The `_row_to_user` converter calls `data.get("consent_given", False)`, `data.get("consent_date")`, and `data.get("data_processing_agreed", False)`, but those keys are never in the result mapping because they are never selected. Every call to `get_by_id`, `get_by_email`, `get_by_stripe_customer_id`, `get_users_by_region`, and `list` returns a User object where `consent_given=False` and `data_processing_agreed=False` regardless of what is stored in the database.
- **Impact:** GDPR compliance is broken. Any code path that checks `user.consent_given` or `user.data_processing_agreed` to gate data processing will see stale falsy values, potentially allowing unauthenticated data processing or blocking legitimate users who have given consent. Also causes the `record_consent` method to write correctly to the DB while the following read-back shows the old falsy state, making audit trails unreliable.
- **Fix:** Add the three missing columns to `_USER_COLUMNS`:
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
      onboarding_completed,
      consent_given, consent_date, data_processing_agreed
  """
  ```
  Also update `conftest.py`'s `mock_sqlalchemy_select` fixture to include these fields per the project's own critical reminder #2.

---

**[P0-02] asyncio.gather over a shared AsyncSession in `get_historical_prices_paginated`**
- **File:** `backend/repositories/price_repository.py` — lines 565–568
- **Description:** `get_historical_prices_paginated` issues two queries concurrently against the same `AsyncSession` instance via `asyncio.gather`:
  ```python
  count_result, rows_result = await asyncio.gather(
      self._db.execute(count_sql, base_params),
      self._db.execute(rows_sql, page_params),
  )
  ```
  SQLAlchemy async sessions are not safe for concurrent access. The project's own `patterns.md` documents this pattern as a known corruption risk ("asyncio.gather + shared AsyncSession = corruption; use sequential loops instead").
- **Impact:** Under concurrent request load this can produce silent result corruption, raise `MissingGreenlet` or `InvalidRequestError` from SQLAlchemy, or return mismatched count/row data. The paginator will then return wrong `total_pages` values or wrong rows, leading to inconsistent API responses that are difficult to reproduce.
- **Fix:** Execute the two queries sequentially:
  ```python
  count_result = await self._db.execute(count_sql, base_params)
  total = count_result.scalar() or 0
  rows_result = await self._db.execute(rows_sql, page_params)
  rows = rows_result.mappings().all()
  ```
  If parallelism is needed, open two separate sessions rather than sharing one.

---

#### P1 — High

**[P1-01] Missing index on `electricity_prices(region, utility_type, timestamp DESC)` — the hottest query path in the system**
- **File:** `backend/repositories/price_repository.py` — lines 367–388 (`get_current_prices`), lines 465–492 (`get_historical_prices`), lines 542–573 (`get_historical_prices_paginated`)
- **Description:** Every primary query against `electricity_prices` filters on `(region, utility_type)` and orders by `timestamp DESC`. Without a composite index covering these three columns the planner falls back to a sequential scan or a less selective index, causing full-table scans that degrade as data volume grows.
- **Impact:** `get_current_prices` is called on the critical path for price display and the alert check cron. Without this index response times will degrade to O(N) as data grows. With 6-hour ingestion cycles at potentially 68 regions × 24 hours, the table will grow rapidly.
- **Fix:** Add a migration with:
  ```sql
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_electricity_prices_region_type_ts
      ON electricity_prices (region, utility_type, timestamp DESC);
  ```

**[P1-02] Missing index on `notifications(user_id, delivery_status, created_at DESC)`**
- **File:** `backend/repositories/notification_repository.py` — lines 121–133 (`get_by_delivery_status`), lines 160–172 (`get_by_channel`)
- **Description:** `get_by_delivery_status` and `get_by_channel` both filter on `user_id` plus a status/channel column. These queries back dashboard views and the retry scheduler and will be called repeatedly. Without a composite index these execute a full scan of the notifications table per user per call.
- **Impact:** Retry scheduling and delivery dashboards will slow proportionally to notification volume per user.
- **Fix:**
  ```sql
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_user_status
      ON notifications (user_id, delivery_status, created_at DESC);
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_user_channel
      ON notifications (user_id, delivery_channel, created_at DESC);
  ```

**[P1-03] Missing index on `forecast_observations(region, observed_at, created_at)` — backfill UPDATE is a full-table scan**
- **File:** `backend/repositories/forecast_observation_repository.py` — lines 112–170 (`backfill_actuals`)
- **Description:** The `backfill_actuals` query with a region filter does `WHERE fo.observed_at IS NULL AND fo.region = :region AND fo.forecast_hour = EXTRACT(HOUR FROM ep.timestamp)`. The `observed_at IS NULL` predicate is a perfect use case for a partial index, and `region` needs an index for the join.
- **Impact:** As forecast data accumulates across all 68 regions over weeks, the CF Worker cron running this every 6 hours will increasingly scan large portions of the table.
- **Fix:**
  ```sql
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_forecast_obs_unobserved
      ON forecast_observations (region, forecast_hour, created_at)
      WHERE observed_at IS NULL;
  ```

**[P1-04] `tariff_types` hardcoded to `["fixed", "variable"]` in `SupplierRegistryRepository` — silently wrong for suppliers with other tariff types**
- **File:** `backend/repositories/supplier_repository.py` — lines 214, 266
- **Description:** Both `list_suppliers` and `get_by_id` return `"tariff_types": ["fixed", "variable"]` as a hardcoded literal, ignoring whatever is stored in the `supplier_registry` table. If the table has a `tariff_types` column, it is never read. If the column does not exist, the data is simply fabricated.
- **Impact:** Callers relying on `tariff_types` to filter or display correct options will always get `["fixed", "variable"]` regardless of the actual supplier tariff offerings. This silently corrupts supplier detail responses for all non-fixed/variable tariff types (`TIME_OF_USE`, `PREPAID`, `GREEN`, `AGILE`) defined in the `TariffType` enum.
- **Fix:** Either select `tariff_types` from the table (if the column exists) or remove the field from the response and source it from a join/separate query. Do not fabricate it from a literal.

**[P1-05] `get_by_user` in `UtilityAccountRepository` silently drops data beyond 100 accounts**
- **File:** `backend/repositories/utility_account_repository.py` — line 186–187
- **Description:** `get_by_user` delegates to `list(page=1, page_size=100, user_id=user_id)`, hard-capping at 100 utility accounts. Users with more than 100 connections (possible for business-tier users with multiple properties) will silently have accounts omitted with no pagination returned to the caller.
- **Impact:** Silent data truncation without error. Business-tier GDPR export and deletion flows that call `get_by_user` to enumerate accounts may miss records, creating GDPR compliance gaps.
- **Fix:** Either paginate the caller or use an explicit no-limit query with a documented safety cap and a warning log:
  ```python
  async def get_by_user(self, user_id: str) -> List[UtilityAccount]:
      """Get all utility accounts for a user (max 500 for safety)."""
      result = await self._db.execute(
          text(f"SELECT {_COLUMNS} FROM utility_accounts WHERE user_id = :user_id ORDER BY created_at DESC LIMIT 500"),
          {"user_id": user_id},
      )
      return [_row_to_account(row) for row in result.mappings().all()]
  ```

**[P1-06] `StateRegulationRepository` uses `SELECT *` — fragile against schema migrations**
- **File:** `backend/repositories/supplier_repository.py` — lines 294, 313
- **Description:** `get_by_state` and `list_deregulated` both use `SELECT * FROM state_regulations`. Every other repository in the codebase uses an explicit column list to decouple from schema evolution and avoid silently passing new columns to callers.
- **Impact:** Adding a column to `state_regulations` in a future migration will immediately pass that column through to callers who do not expect it, potentially causing Pydantic validation errors in `StateRegulation` or leaking internal fields through the API.
- **Fix:** Replace `SELECT *` with an explicit column list matching the `StateRegulation` Pydantic model fields.

**[P1-07] `UserRepository.update` builds a SET clause from field names without enforcing the column allowlist for `utility_types` array serialization**
- **File:** `backend/repositories/user_repository.py` — lines 188–232
- **Description:** The `_UPDATABLE_COLUMNS` allowlist correctly prevents injecting arbitrary column names. However, the `utility_types` column (a PostgreSQL array) is passed raw via `:p_utility_types` without any array cast. SQLAlchemy's `text()` binding will pass a Python `list` to asyncpg, which may work with asyncpg's native type inference but is untested for all driver versions and will silently fail if the session is backed by a sync driver. There is also no explicit `::text[]` cast in the SET clause for this field.
- **Impact:** Depending on asyncpg version, `utility_types` updates may silently no-op or raise a type mismatch error, leaving the user's utility_types unchanged without error surfacing to the caller.
- **Fix:** Add an explicit cast for array columns in `update`:
  ```python
  elif field == "utility_types" and value is not None:
      set_clauses.append(f"{field} = :{param_name}::text[]")
      params[param_name] = value  # asyncpg handles list->array with explicit cast
  ```

---

#### P2 — Medium

**[P2-01] `User` Pydantic model uses `str` for `id`, `current_supplier_id` instead of `UUID` — bypasses type validation**
- **File:** `backend/models/user.py` — lines 65, 84
- **Description:** `id` is typed as `str` with `Field(default_factory=lambda: str(uuid4()))`. `current_supplier_id` is also `Optional[str]`. The project pattern for path parameters (CLAUDE.md critical reminder #9) is to use `uuid.UUID` for free 422 validation. The Pydantic model layer accepting arbitrary strings means malformed IDs are only caught by the database, not at deserialization time.
- **Impact:** Invalid UUID strings (e.g., `"DROP TABLE users"`) passed in API request bodies reach SQL layer; the parameterized queries prevent injection but the validation error will be a 500 (`RepositoryError`) rather than a clean 422.
- **Fix:** Type `id` as `UUID` and use `Field(default_factory=uuid4)`. Let `from_attributes=True` and `model_config` coerce DB strings. For `current_supplier_id`, use `Optional[UUID]`.

**[P2-02] `CommunityPost.post_type` and `utility_type` use raw `str` with manual validators instead of the existing enums**
- **File:** `backend/models/community.py` — lines 44–45, 62–78, 69–78
- **Description:** `CommunityPost` declares `utility_type: str` and `post_type: str` with manual `@field_validator` methods that duplicate the valid-value sets defined in `PostType` and `CommunityUtilityType` enums defined in the same file (lines 17–33). The validators hard-code the valid values as string sets rather than deriving them from the enums, creating a synchronization hazard.
- **Impact:** Adding a new value to `PostType` or `CommunityUtilityType` requires also updating the validator set in both `CommunityPost` and `CommunityPostCreate`, or the new value will be rejected at validation time despite being defined in the enum.
- **Fix:** Type the fields as the appropriate enum and remove the custom validators:
  ```python
  utility_type: CommunityUtilityType
  post_type: PostType
  ```

**[P2-03] `ForecastObservation` Pydantic model has no `ge=0` constraint on `predicted_price` or `actual_price`**
- **File:** `backend/models/observation.py` — lines 20–21
- **Description:** Both `predicted_price: float` and `actual_price: Optional[float]` have no lower-bound validation. A negative electricity price (while theoretically possible in wholesale markets) reaching the `accuracy_metrics` computation would produce misleading MAPE values.
- **Impact:** Negative prices from a misbehaving ML model or bad scrape would silently compute negative-contribution accuracy metrics and be stored without a validation error.
- **Fix:** Add `Field(ge=0.0)` or at minimum document explicitly that negative prices are intentionally permitted.

**[P2-04] `UtilityAccount.region` field accepts any string — should be validated against the `Region` enum**
- **File:** `backend/models/utility_account.py` — lines 26, 41
- **Description:** `region: str = Field(..., min_length=2, max_length=50)` in both `UtilityAccount` and `UtilityAccountCreate` accepts any 2–50 character string. The `User` model correctly uses a `@field_validator` to validate against the `Region` enum. `CommunityPost` similarly has raw `str` for region without Region enum validation.
- **Impact:** Invalid regions (e.g., `"xx_zz"`) stored in `utility_accounts` rows will cause silent mismatches when the account is compared to price data keyed on `Region` enum values.
- **Fix:** Add the same `@field_validator("region")` pattern used in `User.validate_region` to `UtilityAccount`, `UtilityAccountCreate`, and `CommunityPostCreate`.

**[P2-05] `ABTest.status` and `ConnectionResponse.status` are unvalidated bare strings**
- **File:** `backend/models/model_version.py` — line 85; `backend/models/connections.py` — line 100
- **Description:** `ABTest.status: str = Field(default="running")` has no validation that the value is one of the lifecycle states `{"running", "completed", "stopped"}`. Similarly `ConnectionResponse.status: ConnectionStatus = "active"` is typed correctly as a `Literal`, but `PortalScrapeResponse.status: str` (line 283) is a bare unvalidated string.
- **Impact:** Services or tests writing arbitrary strings into `status` will bypass any state machine logic at the model level.
- **Fix:** Replace `status: str` with `Literal["running", "completed", "stopped"]` in `ABTest` and `ABTestCreate`. Replace `PortalScrapeResponse.status: str` with `Literal["success", "failed", "in_progress"]`.

**[P2-06] `ForecastObservationRepository.insert_forecasts` silently defaults `forecast_hour` to `0` on missing/null timestamp**
- **File:** `backend/repositories/forecast_observation_repository.py` — lines 48–52
- **Description:**
  ```python
  ts = pred.get("timestamp")
  if isinstance(ts, str):
      ts = datetime.fromisoformat(ts)
  hour = ts.hour if ts else 0
  ```
  If `timestamp` is `None` or missing from the prediction dict, `hour` silently defaults to `0` and the row is inserted with `forecast_hour=0`. This produces a corrupt observation row indistinguishable from a legitimate midnight prediction.
- **Impact:** Backfill queries joining on `forecast_hour` will match these corrupt rows with actual midnight prices, polluting accuracy metrics.
- **Fix:** Raise a `ValueError` or skip the row when `timestamp` is absent, rather than defaulting to `0`:
  ```python
  ts = pred.get("timestamp")
  if ts is None:
      logger.warning("Skipping prediction with missing timestamp: %s", pred)
      continue
  ```

**[P2-07] `ModelConfigRepository.save_config` deactivate-then-insert is not transactionally atomic under concurrent callers**
- **File:** `backend/repositories/model_config_repository.py` — lines 141–175
- **Description:** The two SQL statements (UPDATE to deactivate + INSERT of new active row) are sent as separate `execute` calls within the same session but are only committed at line 177. While a single SQLAlchemy async session processes commands sequentially, if two concurrent ML training jobs call `save_config` for the same `model_name` simultaneously, both can read the pre-deactivation state (there is no SELECT FOR UPDATE or advisory lock), resulting in two active rows for the same `model_name`.
- **Impact:** `get_active_config` documents that multiple active rows are a "data inconsistency" and works around it with `ORDER BY created_at DESC LIMIT 1`, but having two active rows is a silent invariant violation that wastes storage and can produce confusing audit logs.
- **Fix:** Wrap the two statements in an explicit `BEGIN`/`COMMIT` with a PostgreSQL advisory lock or use `INSERT ... ON CONFLICT` with a partial unique index `ON (model_name) WHERE is_active = true`.

**[P2-08] `ConsentRecord.ip_address` and `user_agent` are required `str` with no length or format validation**
- **File:** `backend/models/consent.py` — lines 41–42
- **Description:** Both fields are `str = Field(..., description="...")` with no length limits or format validation. `ip_address` in particular should be constrained to a valid IPv4/IPv6 format to prevent arbitrary data in GDPR audit records.
- **Impact:** Corrupted or forged audit trails; storing multi-kilobyte strings in the `ip_address` field could cause DB storage issues.
- **Fix:**
  ```python
  from pydantic import IPvAnyAddress
  ip_address: str = Field(..., max_length=45)  # IPv6 max is 39 chars; 45 covers mapped
  user_agent: str = Field(..., max_length=1000)
  ```

---

#### P3 — Low

**[P3-01] `import json` duplicated at module level and inside `update_preferences` method**
- **File:** `backend/repositories/user_repository.py` — lines 8, 319
- **Description:** `import json` appears both at the top of the file (line 8) and again inside `update_preferences` (line 319). The inner import is redundant.
- **Fix:** Remove the inner `import json` from `update_preferences`.

**[P3-02] `BaseRepository.ValidationError` shadows the built-in `pydantic.ValidationError`**
- **File:** `backend/repositories/base.py` — lines 37–39; `backend/repositories/__init__.py` — line 12
- **Description:** The custom `ValidationError(RepositoryError)` class is exported from `repositories/__init__.py`. Any module that does `from repositories import ValidationError` receives the repository version. If the same module also needs `pydantic.ValidationError`, the name collision requires an alias import.
- **Fix:** Rename to `RepositoryValidationError` to avoid the namespace collision:
  ```python
  class RepositoryValidationError(RepositoryError): ...
  ```

**[P3-03] `SupplierContact.website` field typed as `Optional[str]` not `Optional[HttpUrl]`**
- **File:** `backend/models/supplier.py` — line 46
- **Description:** `website: Optional[str] = None` accepts any string. The `Supplier` model imports `HttpUrl` (line 14) for use elsewhere but does not apply it to `SupplierContact.website`. A malformed URL stored in `website` will be returned verbatim in API responses.
- **Fix:** Type as `Optional[HttpUrl] = None`. Note that `HttpUrl` serializes to a string in Pydantic v2, so this is backwards-compatible with the response schema.

**[P3-04] `_UPDATABLE_COLUMNS` allowlist in `UserRepository` is defined as a class variable on line 177, but the method `update` that uses it starts on line 188 — the set definition is visually buried and easy to miss in code review**
- **File:** `backend/repositories/user_repository.py` — lines 177–186
- **Description:** This is a minor code-organization concern: the allowlist is defined between two methods rather than at the top of the class with other class-level constants. Future developers adding columns may miss it.
- **Fix:** Move `_UPDATABLE_COLUMNS` to the class body just after `__init__`, near the top of the class definition.

**[P3-05] Missing `__repr__` methods on all SQLAlchemy/Pydantic model classes**
- **File:** All files in `backend/models/`
- **Description:** None of the Pydantic model classes define `__repr__`. While Pydantic v2 provides a default repr, it includes all fields including sensitive ones (`stripe_customer_id`, `email`, `preferences`). In structured logging (structlog), objects are often repr'd into log lines, which could leak PII.
- **Fix:** Override `__repr__` on `User` and `Notification` at minimum to exclude sensitive fields:
  ```python
  def __repr__(self) -> str:
      return f"User(id={self.id!r}, region={self.region!r}, tier={self.subscription_tier!r})"
  ```

**[P3-06] `Tariff.terms_url` typed as `Optional[str]` — should be `Optional[HttpUrl]`**
- **File:** `backend/models/supplier.py` — line 97
- **Description:** Same pattern as P3-03. The field accepts arbitrary strings rather than validated URLs.
- **Fix:** `terms_url: Optional[HttpUrl] = None`

**[P3-07] `connections.py` has an orphaned comment block with no content**
- **File:** `backend/models/connections.py` — lines 242–245
- **Description:**
  ```python
  # ---------------------------------------------------------------------------
  # Email Scan Response (Phase 1 extraction wiring)
  # ---------------------------------------------------------------------------
  ```
  This section header appears between two other sections but contains no code. The actual `EmailScanResponse` class appears much later in the file (lines 289–302). The orphaned comment is misleading.
- **Fix:** Remove the orphaned section comment or move it to precede the `EmailScanResponse` class.

**[P3-08] `ForecastObservation` and `RecommendationOutcome` models lack `model_config = ConfigDict(from_attributes=True)`**
- **File:** `backend/models/observation.py` — lines 13–36
- **Description:** Both `ForecastObservation` and `RecommendationOutcome` are used to map DB rows (see `ForecastObservationRepository`), but neither declares `model_config = ConfigDict(from_attributes=True)`. All other DB-backed models use this pattern.
- **Impact:** If these models are ever instantiated from ORM Row objects (rather than explicit keyword arguments), they will silently fail to map attributes.
- **Fix:** Add `model_config = ConfigDict(from_attributes=True)` to both classes.

**[P3-09] `ConsentRecord.user_id` is `Optional[str]` with a confusing nullable comment — should document the FK behavior explicitly**
- **File:** `backend/models/consent.py` — line 36
- **Description:** The field comment says "nullable for GDPR SET NULL" which is correct, but the lack of validation means a caller could pass `user_id=None` for a non-GDPR-deletion create operation without any error. The `ConsentRequest` schema (line 58–62) does not include `user_id` at all, relying on the endpoint to inject it — this is fine in practice but means the Pydantic model itself cannot enforce the invariant.
- **Fix:** Add a note in the docstring distinguishing the two valid states (`user_id` set during normal recording vs `None` after GDPR deletion). No code change required, but the intent should be documented.

**[P3-10] `Notification.type` field has no enum constraint despite having only documented valid values**
- **File:** `backend/models/notification.py` — line 58
- **Description:** `type: str = Field(default="info", max_length=50)` accepts any string up to 50 characters. Common values (`"info"`, `"warning"`, `"alert"`, `"price_alert"`) are presumably enumerated at the service layer but are not enforced at the model layer.
- **Fix:** Define a `NotificationType = Literal["info", "warning", "alert", "price_alert", "system"]` alias and use it as the field type, or create a `NotificationType(str, Enum)`. This also removes the need for the `max_length=50` guard.

---

### Statistics

| Metric | Value |
|--------|-------|
| Files audited | 25 (16 model files + 9 repository files) |
| Total findings | 20 |
| P0 — Critical | 2 |
| P1 — High | 7 |
| P2 — Medium | 8 |
| P3 — Low | 10 |

### Priority Action Items

1. **P0-01** — Add `consent_given`, `consent_date`, `data_processing_agreed` to `_USER_COLUMNS` and update `conftest.py` fixture. This is a live GDPR data-correctness bug.
2. **P0-02** — Serialize the two queries in `get_historical_prices_paginated`. The current `asyncio.gather` over a shared session violates the documented project pattern and will corrupt results under concurrent load.
3. **P1-01** — Add composite index on `electricity_prices(region, utility_type, timestamp DESC)`. This is the single most impactful index addition given query volume.
4. **P1-04** — Remove hardcoded `tariff_types: ["fixed", "variable"]` from `SupplierRegistryRepository`. This silently fabricates data for all supplier responses.
5. **P1-05** — Fix the silent 100-account truncation in `get_by_user` to prevent GDPR export gaps.
