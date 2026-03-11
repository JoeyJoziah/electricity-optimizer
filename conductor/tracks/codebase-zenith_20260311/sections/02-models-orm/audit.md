# Section 2: Backend Models & ORM — Clarity Gate Audit

**Date:** 2026-03-12
**Auditor:** Claude Code (Explore agent)
**Score:** 57/90 (FAIL — threshold 72/90)

---

## Aggregate Scores

| # | Dimension | Score |
|---|-----------|-------|
| 1 | Correctness | 6/10 |
| 2 | Coverage | 5/10 |
| 3 | Security | 7/10 |
| 4 | Performance | 7/10 |
| 5 | Maintainability | 6/10 |
| 6 | Documentation | 8/10 |
| 7 | Error Handling | 6/10 |
| 8 | Consistency | 5/10 |
| 9 | Modernity | 7/10 |
| | **TOTAL** | **57/90** |

---

## Files Analyzed (23 files, ~4,970 lines)

Models: `__init__.py`, `region.py`, `user.py`, `price.py`, `supplier.py`, `notification.py`, `consent.py`, `connections.py`, `utility.py`, `observation.py`, `regulation.py`, `user_supplier.py`, `model_config.py`, `model_version.py`
Repositories: `base.py`, `__init__.py`, `user_repository.py`, `price_repository.py`, `supplier_repository.py`, `notification_repository.py`, `forecast_observation_repository.py`, `model_config_repository.py`
ORM: `compliance/repositories.py`

---

## CRITICAL Findings (6)

**CRIT-01: SupplierRepository uses Pydantic model in select() — runtime crash**
- File: `backend/repositories/supplier_repository.py:116-122`
- `select(Supplier)` where Supplier is Pydantic BaseModel, not SQLAlchemy ORM
- Fix: Replace with raw SQL or create SupplierORM (SupplierRegistryRepository already has correct pattern)

**CRIT-02: User preferences serialized via str() — invalid JSON**
- File: `backend/repositories/user_repository.py:149`
- `str(entity.preferences)` produces Python repr (single quotes, True/False) not valid JSON
- Fix: Use `json.dumps(entity.preferences)` (update_preferences on line 310 already does this correctly)

**CRIT-03: metadata vs metadata_json field name collision**
- File: `backend/compliance/repositories.py:42`, `backend/models/consent.py:46`
- Pydantic uses `metadata`, DB column is `metadata_json`. Raw SQL mappings will lose data
- Fix: Add alias or rename field to match DB column

**CRIT-04: supplier.__dict__.copy() breaks Pydantic v2 cache serialization**
- File: `backend/repositories/supplier_repository.py:155,348`
- `__dict__` includes Pydantic internal keys; `Supplier(**cached)` fails on restore
- Fix: Use `supplier.model_dump()` instead

**CRIT-05: SupplierRepository.create() calls db.add() on Pydantic model**
- File: `backend/repositories/supplier_repository.py:176-183`
- `self._db.add(entity)` requires ORM instance, raises UnmappedInstanceError
- Fix: Retire SupplierRepository in favor of SupplierRegistryRepository

**CRIT-06: Tariff operations use Pydantic model as ORM — runtime crash**
- File: `backend/repositories/supplier_repository.py:370-378`
- `select(Tariff)` and `self._db.add(tariff)` on Pydantic model
- Fix: Create TariffORM or raw SQL TariffRepository

## HIGH Findings (9)

- H-01: User model missing email_verified_at, login_count, locked_until; _USER_COLUMNS missing consent fields
- H-02: __init__.py missing exports for 10+ model classes
- H-03: ConnectionType literal missing "utilityapi" value (5 types in prod, 4 in model)
- H-04: SupplierRegistryRepository.list_suppliers() hardcodes tariff_types
- H-05: ConsentRepository.create() has no rollback on exception
- H-06: EmailScanResponse.bills typed as List[dict] (untyped)
- H-07: 16 tables (48% of public schema) have no Pydantic model
- H-08: UserRepository.update() dynamic SQL SET with no column allowlist
- H-09: list_by_region() uses any_(Supplier.regions) on Pydantic field

## MEDIUM Findings (14)

- M-01: json_encoders deprecated Pydantic v1 pattern
- M-02: sqlalchemy.future.select deprecated import
- M-03: ForecastObservation missing default_factory for id/created_at
- M-04: Redundant list min_length + validator on Supplier.regions
- M-05: get_users_by_region LIMIT 5000 silent truncation
- M-06: Price.convert_to_kwh() loses id and created_at
- M-07: update() with model_dump(exclude_unset=True) can overwrite payment/consent state
- M-08: Tariff model has no ORM backing or repository
- M-09: StateRegulation missing updated_at field (DB has it)
- M-10: Row access inconsistent (row.id vs row["id"]) across repos
- M-11: Redis cache clear uses O(N) per-key deletes
- M-12: _NOTIFICATION_COLUMNS string fragile if schema drifts
- M-13: Cache stampede retry waits only 100ms vs 5000ms lock TTL
- M-14: ABTest.version_a_id/b_id no UUID validation

## LOW Findings (10)

- L-01 through L-10: structlog vs logging inconsistency, function-level imports, str vs Literal for subscription_tier/ABTest.status, missing __init__.py exports, unused HttpUrl import, dead ORM imports

---

## Top 10 Priority Fixes

1. CRIT-01/05/06/H-09: Retire SupplierRepository entirely — SupplierRegistryRepository is the working path
2. CRIT-02: `json.dumps()` for preferences in create/update
3. CRIT-03: metadata_json field naming alignment
4. H-01: Add missing columns to _USER_COLUMNS and User model
5. CRIT-04: model_dump() for cache serialization
6. H-08: Column allowlist for UserRepository.update()
7. H-03: Add "utilityapi" to ConnectionType
8. H-07: Create models for price_alert_configs, alert_history, user_savings
9. M-01/L-05/L-06: Pydantic v2 modernization (Literal types, remove json_encoders)
10. M-10: Standardize on result.mappings() across all repos
