# Section 1: Database Layer — Clarity Gate Audit

**Date:** 2026-03-11
**Assessor:** Loki Mode (Autonomous RARV)
**Audit Agents:** sql-pro (migrations), database-optimizer (query patterns), backend-developer (models)
**Scope:** 35 migration files, query patterns across 40+ service files, connection config, ORM models

---

## Clarity Gate Scorecard (Pre-Optimization)

| # | Dimension | Score | Key Findings |
|---|-----------|-------|-------------|
| 1 | Correctness | 4/10 | Pydantic models used in SQLAlchemy `select()` (will crash in prod), N+1 queries in 4 critical paths, phantom index on non-existent column, GDPR deletion not atomic, Tariff model has 10+ fields not in DB |
| 2 | Coverage | 4/10 | 8+ tables with no Pydantic model, 8+ missing composite indexes, `mock_sqlalchemy_select` masks CRITICAL ORM failures |
| 3 | Security | 4/10 | Plaintext OAuth tokens (009), plaintext portal_username (034), no column-level encryption |
| 4 | Performance | 5/10 | 4 N+1 patterns in hot paths, unbounded queries on growing tables, missing indexes on high-frequency lookups |
| 5 | Maintainability | 5/10 | Pydantic/ORM dual-model confusion, raw `str` instead of Region enum in 6+ models, `float` for currency fields |
| 6 | Documentation | 7/10 | Migration headers are good, but no migration tracking table, no schema changelog |
| 7 | Error Handling | 6/10 | Auto-commit on read-only sessions, multiple commits per orchestrator call, partial GDPR deletion on failure |
| 8 | Consistency | 5/10 | GRANT inconsistencies, CHECK constraint gaps, UUID typed as `str` across all Pydantic models, duplicate PriceRegion alias |
| 9 | Modernity | 6/10 | asyncpg+Neon config is solid, but ~30 outdated packages, no connection pool monitoring |
| | **Aggregate** | **46/90** | **Well below minimum (72/90). Requires major remediation.** |

**Verdict:** FAIL (46/90 vs 72/90 minimum). Section requires extensive Research + Execute + Validate cycle.

---

## Findings Summary — All Agents Combined

### CRITICAL (5)

| ID | Source | Location | Issue |
|----|--------|----------|-------|
| CRIT-01 | Migration | `009_email_oauth_tokens.sql` | OAuth access/refresh tokens stored as plaintext VARCHAR. Must use AES-256-GCM encryption (pattern exists in 034) |
| CRIT-02 | Migration | `034_portal_credentials.sql` | `portal_username` stored as plaintext TEXT while `portal_password_encrypted` uses AES-256-GCM. Username should also be encrypted |
| CRIT-03 | Models | `user_repository.py`, `supplier_repository.py` | Pydantic models used in SQLAlchemy `select()` — will crash with `InvalidRequestError` in production. Masked by `mock_sqlalchemy_select` fixture |
| CRIT-04 | Models | `compliance/repositories.py:31,50` | ORM `user_id` typed as `String(36)` not `UUID`, no FK declaration — violates UUID PK standard |
| CRIT-05 | Models | `user_repository.py` | No ORM model for `users` table — entire `UserRepository` is non-functional against real DB |

### HIGH (26)

| ID | Source | Location | Issue |
|----|--------|----------|-------|
| HIGH-01 | Migration | `012_user_savings.sql` | Missing FK: `user_savings.user_id` has no REFERENCES constraint |
| HIGH-02 | Migration | `015_notifications.sql` | Missing FK: `notifications.user_id` has no REFERENCES constraint |
| HIGH-03 | Migration | `033_model_predictions_ab.sql` | Missing FK: `model_predictions.user_id` has no REFERENCES constraint |
| HIGH-04 | Migration | `014_alert_tables.sql` | Missing FK: `recommendation_outcomes.user_id` has no REFERENCES constraint |
| HIGH-05 | Migration | `021_fix_supplier_api.sql` | Non-idempotent ALTER TABLE — will fail on re-run (no IF NOT EXISTS/DO block) |
| HIGH-06 | Migration | `006` vs `007` | `current_supplier_id FK` declared in 006 but column added in 007 — execution order conflict |
| HIGH-07 | Migration | Index migrations | Duplicate index on `electricity_prices(region)` in both 004 and 017 |
| HIGH-08 | Migration | `005_observation_tables.sql` | Phantom index on `forecast_observations.utility_type` — column does not exist in CREATE TABLE |
| HIGH-09 | Migration | `014_alert_tables.sql` | Missing CHECK constraints on `alert_type` and `notification_frequency` columns |
| HIGH-10 | Query | `api/v1/internal/sync.py:79` | N+1: per-row SELECT xmax after UPSERT (2x queries per user row) |
| HIGH-11 | Query | `api/v1/internal/alerts.py:128` | N+1: per-alert dedup query in loop (500+ queries per cron run) |
| HIGH-12 | Query | `api/v1/internal/email_scan.py:230` | N+1: per-email INSERT + COMMIT in loop (150 round-trips worst case) |
| HIGH-13 | Query | `services/dunning_service.py:305` | N+1: 3-4 separate transactions per payment failure webhook |
| HIGH-14 | Query | `services/kpi_report_service.py:73` | Unbounded `COUNT(*)` on `electricity_prices` — seq scan on growing table |
| HIGH-15 | Query | `services/alert_service.py:443` | Unbounded SELECT on `price_alert_configs` — no LIMIT, loads all active configs |
| HIGH-16 | Query | `services/notification_dispatcher.py:466` | JSONB `metadata->>'dedup_key'` query without GIN index |
| HIGH-17 | Query | `services/alert_service.py:399` | Missing composite index on `alert_history(user_id, alert_type, region, triggered_at)` |
| HIGH-18 | Query | `repositories/price_repository.py:367` | Missing `(region, utility_type, timestamp DESC)` index on `electricity_prices` |
| HIGH-19 | Query | `compliance/gdpr.py:601` | GDPR `delete_user_data` not atomic — partial deletion possible on failure |
| HIGH-20 | Models | `models/user.py:69` | `User.region` typed as raw `str` instead of `Region` enum — violates project mandate |
| HIGH-21 | Models | `models/supplier.py:91,161` | `Supplier.regions` and `Tariff.available_regions` are `List[str]` not `List[Region]` |
| HIGH-22 | Models | `compliance/repositories.py:32,51` | No `ForeignKey("users.id")` on ORM `user_id` columns |
| HIGH-23 | Models | `compliance/repositories.py:53` | `deleted_by` is `String(36)` but DB column is `VARCHAR(100)` — truncation risk |
| HIGH-24 | Models | Migration 012 | `user_savings` has no Pydantic model, no FK constraint, no GRANT |
| HIGH-25 | Models | Migrations 024-033 | 8+ tables have no corresponding Pydantic models (`payment_retry_history`, `weather_cache`, `feedback`, `agent_conversations`, etc.) |
| HIGH-26 | Models | `models/supplier.py:70-98` | `Tariff` Pydantic model has 10+ fields not in actual `tariffs` DB table — severe schema drift |

### MEDIUM (23)

| ID | Source | Location | Issue |
|----|--------|----------|-------|
| MED-01 | Migration | Multiple | Missing NOT NULL on `notifications.channel`, `alert_history.triggered_at` |
| MED-02 | Migration | `028_feedback_table.sql` | Missing CHECK on `feedback.rating` (1-5 range not enforced) |
| MED-03 | Migration | `030_model_versioning.sql` | Missing CHECK on `model_versions.status` enum values |
| MED-04 | Migration | `031_agent_tables.sql` | Missing DEFAULT on `agent_sessions.messages` (JSONB should default to '[]') |
| MED-05 | Migration | Multiple | GRANT inconsistencies — 7 migrations grant to neondb_owner, 2 to public, rest have none |
| MED-06 | Migration | `016_feature_flags.sql` | Missing unique constraint on `feature_flags.flag_name` |
| MED-07 | Migration | `025_data_cache_tables.sql` | `data_cache.ttl_seconds` has no CHECK > 0 |
| MED-08 | Migration | Multiple | `created_at` defaults vary: some use `now()`, others `CURRENT_TIMESTAMP` |
| MED-09 | Query | `services/kpi_report_service.py:38` | 7 sequential queries — should use `asyncio.gather()` |
| MED-10 | Query | `repositories/user_repository.py:261` | SELECT before UPDATE pattern (3 methods) — unnecessary round-trips |
| MED-11 | Query | `repositories/user_repository.py:355` | `get_users_by_region` — no LIMIT on large result set |
| MED-12 | Query | `services/savings_service.py:103` | Streak computation fetches 365 dates to Python — should use window functions |
| MED-13 | Query | `services/email_scanner_service.py:109` | N+1 HTTP: sequential per-email Gmail API calls (not DB, but same pattern) |
| MED-14 | Query | `services/dunning_service.py:97,369,384` | 3 commits per `handle_payment_failure` — should consolidate |
| MED-15 | Query | `compliance/gdpr.py:322` | Sequential INSERTs per ConsentPurpose in `withdraw_all_consents` |
| MED-16 | Query | `compliance/repositories.py:192` | Loads ALL consent records to find latest — should use DISTINCT ON |
| MED-17 | Query | `config/database.py:167` | Auto-commit on every read-only session — unnecessary WAL overhead |
| MED-18 | Query | `services/dunning_service.py:110` | Missing index on `payment_retry_history.stripe_invoice_id` |
| MED-19 | Query | `api/v1/internal/email_scan.py:71` | `user_connections` query without composite index |
| MED-20 | Query | `api/v1/users.py:196` | Dynamic f-string SQL in `update_profile` |
| MED-21 | Query | `services/alert_service.py:671` | Dynamic f-string SQL in `update_alert` |
| MED-22 | Query | `config/settings.py:51` | Pool size (3+5=8 max) may be insufficient — document as scaling lever |
| MED-23 | Query | `services/alert_service.py:450` | Missing index on `price_alert_configs(is_active, created_at)` |

### LOW (8)

| ID | Source | Location | Issue |
|----|--------|----------|-------|
| LOW-01 | Migration | `031_agent_tables.sql` | Table `agent_usage_limits` — `limit` is a reserved word in SQL |
| LOW-02 | Migration | `018_nationwide_defaults.sql` | `default_utility_settings.created_at` missing |
| LOW-03 | Migration | `019_nationwide_suppliers.sql` | `nationwide_suppliers.created_at` missing |
| LOW-04 | Migration | `027_model_config.sql` | `model_config` table lacks version/changelog columns |
| LOW-05 | Migration | Multiple | Inconsistent naming: `updated_at` vs `last_updated` |
| LOW-06 | Query | `services/savings_service.py:160` | Separate COUNT + SELECT for pagination |
| LOW-07 | Migration | `024_payment_retry.sql` | `email_sent_at` nullable but `email_sent` boolean default false — redundant |
| LOW-08 | Migration | `026_notifications_metadata.sql` | `metadata` JSONB added without GIN index |

### INFO (6)

| ID | Source | Location | Issue |
|----|--------|----------|-------|
| INFO-01 | Migration | N/A | No migration tracking table (`schema_migrations`) — relies on filename ordering |
| INFO-02 | Migration | 004 + 017 | Duplicate `idx_electricity_prices_region` in two migration files |
| INFO-03 | Config | `database.py:62` | `statement_cache_size=0` correctly set for Neon PgBouncer |
| INFO-04 | Config | `database.py:84` | `pool_recycle=200` correctly prevents Neon auto-suspend disconnections |
| INFO-05 | Query | `auth/neon_auth.py:81` | Verify Better Auth creates index on `neon_auth.session.token` |
| INFO-06 | Config | `database.py:164` | Session lifecycle correctly managed with explicit close in finally block |

---

## Missing Index Inventory (New Migration Required)

```sql
-- 1. electricity_prices (primary lookup)
CREATE INDEX IF NOT EXISTS idx_electricity_prices_region_type_time
    ON electricity_prices (region, utility_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_electricity_prices_region_supplier_time
    ON electricity_prices (region, supplier, timestamp DESC);

-- 2. alert_history (dedup + history)
CREATE INDEX IF NOT EXISTS idx_alert_history_dedup
    ON alert_history (user_id, alert_type, region, triggered_at DESC);

-- 3. notifications (JSONB dedup)
CREATE INDEX IF NOT EXISTS idx_notifications_dedup_key
    ON notifications (user_id, (metadata->>'dedup_key'), created_at DESC)
    WHERE metadata IS NOT NULL;

-- 4. payment_retry_history
CREATE INDEX IF NOT EXISTS idx_payment_retry_invoice
    ON payment_retry_history (stripe_invoice_id);

-- 5. price_alert_configs
CREATE INDEX IF NOT EXISTS idx_price_alert_configs_active_created
    ON price_alert_configs (is_active, created_at)
    WHERE is_active = TRUE;

-- 6. user_connections (email scan)
CREATE INDEX IF NOT EXISTS idx_user_connections_type_status
    ON user_connections (connection_type, status, updated_at ASC)
    WHERE status = 'active';

-- 7. consent_records
CREATE INDEX IF NOT EXISTS idx_consent_records_user_purpose_time
    ON consent_records (user_id, purpose, timestamp DESC);
```

---

## Priority Remediation Order

1. **CRIT-01/02**: Encrypt OAuth tokens + portal_username (security)
2. **HIGH-19**: Make GDPR deletion atomic (compliance)
3. **HIGH-10/11/12/13**: Fix N+1 patterns in hot cron paths (performance)
4. **HIGH-16/17/18**: Create missing indexes (performance)
5. **HIGH-14/15**: Add bounds to unbounded queries (stability)
6. **HIGH-01/02/03/04**: Add missing foreign keys (correctness)
7. **HIGH-05**: Make migration 021 idempotent (maintainability)
8. **HIGH-08**: Fix phantom index on forecast_observations (correctness)
9. **MED-09**: Parallelize KPI report queries (performance)
10. **MED-10**: Eliminate SELECT-before-UPDATE pattern (performance)

---

## Model Layer Findings (from backend-developer agent)

### Additional MEDIUM (Models)

| ID | Source | Location | Issue |
|----|--------|----------|-------|
| MED-24 | Models | `models/__init__.py` | 20+ models missing from `__all__` exports — package API non-discoverable |
| MED-25 | Models | Multiple `models/*.py` | `id` fields use `str(uuid4())` not `uuid.UUID` type — loses type safety |
| MED-26 | Models | `models/observation.py:20` | `float` for `predicted_price`/`actual_price` — DB uses `DECIMAL(12,6)` |
| MED-27 | Models | Migrations | No index on `users.stripe_customer_id` — webhook payment path is full scan |
| MED-28 | Models | `models/model_version.py:79` | `ABTest` FK fields typed as `str` not `UUID` |
| MED-29 | Models | `models/regulation.py:22` | `bond_amount` uses `float` instead of `Decimal` for currency |

### Additional LOW (Models)

| ID | Source | Location | Issue |
|----|--------|----------|-------|
| LOW-09 | Models | `models/notification.py:58` | `type` field has no enum/Literal constraint |
| LOW-10 | Models | `models/consent.py:37` | `purpose` accepts any string — should use `ConsentPurpose` enum |
| LOW-11 | Models | `models/observation.py:13` | Missing `ConfigDict(from_attributes=True)` |
| LOW-12 | Models | `models/region.py:116`, `models/price.py:20` | Duplicate `PriceRegion` alias in two files |

### Additional INFO (Models)

| ID | Source | Location | Issue |
|----|--------|----------|-------|
| INFO-07 | Models | `conftest.py` | `mock_sqlalchemy_select` fixture masks all CRITICAL ORM failures in tests |
| INFO-08 | Models | Migration 002 | `auth_sessions`, `login_attempts` are dead infrastructure post-Neon-Auth |
| INFO-09 | Models | `init_neon.sql` vs `006` | `suppliers` and `supplier_registry` are parallel — legacy table not deprecated |
| INFO-10 | Models | `027_model_config.sql:1` | Internal comment says "Migration 026" but filename is 027 |

---

## Total Findings: 78

| Severity | Count |
|----------|-------|
| CRITICAL | 5 |
| HIGH | 26 |
| MEDIUM | 29 |
| LOW | 12 |
| INFO | 10 |

---

## Priority Remediation Order (Updated)

### Tier 1 — Production Safety (Immediate)
1. **CRIT-03/05**: Create SQLAlchemy ORM models (`UserORM`, `SupplierORM`) — `UserRepository` is broken against real DB
2. **CRIT-01/02**: Encrypt OAuth tokens + portal_username (security)
3. **CRIT-04**: Fix ORM `user_id` typing from `String(36)` to `UUID` with FK declaration
4. **HIGH-19**: Make GDPR deletion atomic (compliance)

### Tier 2 — Performance (This Sprint)
5. **HIGH-10/11/12/13**: Fix N+1 patterns in hot cron paths
6. **HIGH-16/17/18**: Create missing composite indexes (new migration 036)
7. **HIGH-14/15**: Add bounds to unbounded queries
8. **MED-27**: Add index on `users.stripe_customer_id`

### Tier 3 — Correctness (Next Sprint)
9. **HIGH-20/21**: Enforce Region enum in User/Supplier models
10. **HIGH-26**: Resolve Tariff model vs DB schema drift
11. **HIGH-01/02/03/04**: Add missing foreign keys
12. **HIGH-25**: Create Pydantic models for 8+ unmodeled tables
13. **MED-25/26**: Fix UUID typing and Decimal for currency fields

### Tier 4 — Maintenance
14. **HIGH-05/08**: Fix non-idempotent migration and phantom index
15. **MED-05/08**: Standardize GRANTs and timestamp defaults
16. **LOW/INFO items**: Clean up naming, enums, dead tables

---

_Audit complete. All 3 agent reports synthesized. Proceeding to Research phase._
