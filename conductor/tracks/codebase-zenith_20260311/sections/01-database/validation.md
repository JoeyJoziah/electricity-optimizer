# Section 1: Database Layer — Clarity Gate Re-Assessment

**Date:** 2026-03-12
**Assessor:** database-optimizer
**Trigger:** Post-optimization re-score after 5 remediation batches
**Original audit:** 2026-03-11 (46/90 — FAIL)
**Files verified:** 12 source files + migration 036

---

## Optimization Batches Applied (Summary)

| Batch | Description |
|-------|-------------|
| 1 | N+1 elimination in sync-users, check-alerts, email-scan, dunning, KPI; LIMIT on unbounded queries |
| 2 | UserRepository converted to raw SQL; removed Pydantic-in-SQLAlchemy anti-pattern (CRIT-03/05) |
| 3 | portal_username encrypted with AES-256-GCM (CRIT-02); OAuth tokens verified as already encrypted (CRIT-01 false positive) |
| 4 | GDPR delete_user_data converted to single atomic transaction with rollback on failure (HIGH-19) |
| 5 | Migration 036 — 4 new performance indexes; Region enum validation in User model; DISTINCT ON in ConsentRepository |

---

## Dimension-by-Dimension Re-Score

### 1. Correctness (4 → 7)

**Old score: 4/10**
**New score: 7/10**

Evidence for improvement:

- **CRIT-03/05 resolved.** `UserRepository` fully converted to raw SQL (`_USER_COLUMNS` column list, `_row_to_user()` mapper). No Pydantic model is passed to `sqlalchemy.select()` anywhere in `user_repository.py`. The `InvalidRequestError` crash path is eliminated.
  File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/user_repository.py` lines 1-100.

- **CRIT-04 partially resolved.** `ConsentRecordORM` and `DeletionLogORM` remain typed as `String(36)` for `user_id` — no `ForeignKey("users.id")` declaration. This is a residual gap. The `deleted_by` column is still `String(36)` while the DB column is `VARCHAR(100)`, so the truncation risk (HIGH-23) remains.

- **HIGH-08 resolved (migration 005 re-read).** The phantom index on `forecast_observations.utility_type` does not appear in the current `005_observation_tables.sql` — only `idx_fobs_region_created` and `idx_fobs_unobserved` are defined, both on columns that exist. No phantom index found.

- **HIGH-05 remains.** Migration `021_fix_supplier_api_available.sql` is a bare `UPDATE` statement with no IF NOT EXISTS guard or DO block — still non-idempotent. Safe on production but will error in fresh-deploy CI scenarios.

- **HIGH-06 remains.** The `current_supplier_id` FK vs column order conflict between migration 006 and 007 is not addressed.

- **HIGH-01/02/03/04 remain.** Missing FK constraints on `user_savings.user_id`, `notifications.user_id`, `model_predictions.user_id`, and `recommendation_outcomes.user_id` are still absent from the migrations.

Remaining deduction rationale: Three migration correctness issues (FK gaps, non-idempotent 021, FK declaration order conflict) and one ORM typing gap hold the score below 8.

---

### 2. Coverage (4 → 6)

**Old score: 4/10**
**New score: 6/10**

Evidence for improvement:

- **HIGH-16/17/18 addressed via migration 036.**
  File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/migrations/036_performance_indexes.sql`
  - `idx_alert_history_dedup` — covers `(user_id, alert_type, region, triggered_at DESC)` for check-alerts dedup queries (HIGH-17).
  - `idx_price_alert_configs_active_created` — partial index on `is_active=TRUE` for the bulk-load query (MED-23).
  - `idx_user_connections_type_status_updated` — partial index on `status='active'` for email/portal scan crons (MED-19).
  - `idx_consent_records_user_purpose_time` — composite for GDPR DISTINCT ON query (supports MED-16 fix).

- **Notifications dedup index already existed.** Migration 026 (`026_notifications_metadata.sql`) defines `idx_notifications_dedup_key` on `(metadata->>'dedup_key', user_id, created_at DESC) WHERE metadata IS NOT NULL`. HIGH-16 was already covered prior to batch 5.

- **MED-27 (stripe_customer_id index) not addressed.** No migration creates an index on `users.stripe_customer_id`, leaving the payment webhook lookup path on a full table scan.

- **HIGH-18 (electricity_prices composite indexes) not in 036.** The audit called for `(region, utility_type, timestamp DESC)` and `(region, supplier, timestamp DESC)` indexes on `electricity_prices`. Migration 036 does not include these. Migration 020 adds some price indexes but not this exact composite.

- **8+ unmodeled tables remain unmodeled** (HIGH-25: `payment_retry_history`, `weather_cache`, `feedback`, `agent_conversations`, etc.).

- **mock_sqlalchemy_select conftest fixture** still present. It was updated in Batch 2 to support new fields but the masking of ORM failures is structural — raw SQL in UserRepository means this fixture is now less dangerous for that path, but supplier repository and compliance ORM models are still not independently tested against real query execution.

Remaining deduction: 3 missing high-priority indexes (electricity_prices composites, stripe_customer_id) and 8+ unmodeled tables are non-trivial coverage gaps.

---

### 3. Security (4 → 7)

**Old score: 4/10**
**New score: 7/10**

Evidence for improvement:

- **CRIT-02 resolved.** `portal_username` is now encrypted with AES-256-GCM before storage.
  File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/portal_scrape.py` lines 91-94.
  Both `encrypt_field(payload.portal_username)` and `encrypt_field(payload.portal_password)` are called. The base64-encoded ciphertext is stored in the `portal_username` column. The batch scan in `portal_scan.py` decrypts both symmetrically (lines 172-173).

- **CRIT-01 confirmed false positive.** OAuth tokens in `user_connections.oauth_access_token` and `oauth_refresh_token` are stored as base64-encoded AES-256-GCM ciphertexts.
  File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/connections/email_oauth.py` lines 164-183.
  The `encrypt_tokens()` helper encrypts both tokens before storing. The `decrypt_field()` call in `email_scan.py` line 128 decrypts them at use time.

- **Migration 034 schema gap persists.** The migration file `034_portal_credentials.sql` still documents `portal_username` as `VARCHAR(255)` plaintext (line 26), while the application layer now encrypts it. The schema comment and column type are misleading — the column should be renamed to `portal_username_encrypted` or at minimum the migration comment updated. This is a documentation/schema alignment issue rather than a live security vulnerability, since the application code does encrypt.

- **No column-level encryption in DB layer.** Encryption is application-side only, not enforced by DB constraints. This is acceptable for the current stack but means DB dumps expose plaintext if the encryption key is compromised separately.

Remaining deduction: migration 034 schema documentation still describes plaintext storage. No DB-side enforcement of encryption. Both are known architectural limits rather than active regressions.

---

### 4. Performance (5 → 8)

**Old score: 5/10**
**New score: 8/10**

Evidence for improvement:

- **HIGH-10 resolved.** `sync-users` (`sync.py`) uses a single UPSERT with `RETURNING id, (xmax = 0) AS is_insert` to determine insert vs update without a separate SELECT per row. Lines 56-83.

- **HIGH-11 resolved.** `alert_service.py` `_batch_should_send_alerts()` groups triggered pairs by cooldown window and runs one VALUES-clause query per group (max 4 queries for 4 frequency tiers), replacing per-alert N+1.
  File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/alert_service.py` lines 421-481.

- **HIGH-12 resolved.** `email_scan.py` accumulates all extracted rates into `rate_rows[]` then executes a batch INSERT loop followed by a single `db.commit()` per connection (lines 249-264). Previously this was per-email INSERT+COMMIT.

- **HIGH-13/MED-14 resolved.** `dunning_service.py` `handle_payment_failure()` performs record, email-flag UPDATE, and escalation UPDATE all within a single transaction ending in one `db.commit()` at line 384.

- **HIGH-14 resolved.** `kpi_report_service.py` `_count_prices_tracked()` uses `pg_class.reltuples` approximate count (lines 74-83) instead of `COUNT(*)` full scan.

- **HIGH-15 resolved.** `alert_service.py` `get_active_alert_configs()` has `LIMIT 5000` (line 524) and joins users inline to avoid per-user follow-up queries.

- **MED-09 NOT resolved.** `kpi_report_service.py` `aggregate_metrics()` still awaits 7 coroutines sequentially (lines 38-46). `asyncio.gather()` was listed in Batch 1 description but is absent from the file. No `gather` call exists in `kpi_report_service.py`. This is a missed fix — the 7 sequential DB round-trips on the nightly KPI cron remain.

- **Migration 036 indexes deployed.** Four new composite/partial indexes directly support the dedup, alert-config, connection-scan, and consent query patterns identified in HIGH-17, MED-19, MED-23.

- **electricity_prices composite index still missing.** HIGH-18 called for `(region, utility_type, timestamp DESC)` — this remains absent from all migrations.

Remaining deduction: KPI sequential queries (MED-09) unresolved, electricity_prices lookup index still missing.

---

### 5. Maintainability (5 → 7)

**Old score: 5/10**
**New score: 7/10**

Evidence for improvement:

- **CRIT-03/05 resolved.** The Pydantic/SQLAlchemy dual-model confusion in `UserRepository` is gone. The repository is now cleanly raw SQL with explicit column mapping. The `_USER_COLUMNS` constant and `_row_to_user()` helper are well-named and centralised.

- **HIGH-20 resolved.** `User.region` now has a `@field_validator("region")` that calls `Region(lowered)` and raises `ValueError` for invalid values.
  File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/user.py` lines 103-117.

- **HIGH-21 NOT resolved.** `Supplier.regions` and `Tariff.available_regions` remain `List[str]` without Region enum typing — not verified as changed.

- **MED-10 resolved.** `UserRepository` methods use RETURNING clauses and direct UPDATEs instead of SELECT-before-UPDATE patterns (e.g., `update_last_login` at line 321, `record_consent` at line 364).

- **HIGH-26 NOT resolved.** `Tariff` Pydantic model schema drift (10+ fields not in DB) is not addressed.

- **MED-25/26 NOT resolved.** `id` fields still use `str(uuid4())` not `uuid.UUID`, and `float` is still used for monetary fields in some models.

- **DeletionLogORM.deleted_by** remains `String(36)` while DB column is `VARCHAR(100)`. Truncation risk unresolved.

Remaining deduction: Supplier/Tariff model issues, UUID typing inconsistency, and the ORM String(36) vs VARCHAR(100) mismatch are unresolved.

---

### 6. Documentation (7 → 8)

**Old score: 7/10**
**New score: 8/10**

Evidence for improvement:

- **Migration 036 is well-documented.** Header block explains all 4 indexes, their purpose, and a note about CONCURRENTLY requiring psql (not psycopg2 in a transaction).
  File: `/Users/devinmcgrath/projects/electricity-optimizer/backend/migrations/036_performance_indexes.sql` lines 1-18.

- **UserRepository docstring updated.** The class docstring at line 75-77 explicitly notes "Uses raw SQL queries (not ORM)" and links the decision to CRIT-03/05.

- **GDPR atomic transaction is documented.** `delete_user_data()` docstring (lines 610-633) explicitly states "All database deletions are executed within a single transaction — if any step fails, all changes are rolled back (atomic all-or-nothing semantics)."

- **Migration 034 schema comment gap.** The `portal_username` column is still described as plaintext in migration 034 while the application encrypts it. A schema-level comment or column rename to `portal_username_encrypted` would close this.

- INFO-01 (no `schema_migrations` tracking table) remains unaddressed.

---

### 7. Error Handling (6 → 8)

**Old score: 6/10**
**New score: 8/10**

Evidence for improvement:

- **HIGH-19 resolved.** GDPR `delete_user_data()` now wraps all 9 DELETE statements in a single try/except block with `await self.db_session.commit()` at line 759 and `await self.db_session.rollback()` at line 762 on failure. Partial deletion on failure is eliminated.

- **HIGH-13/MED-14 resolved.** Dunning `handle_payment_failure()` consolidates 3 prior commits into one at line 384. The overall payment failure flow is now atomic.

- **email_scan.py rollback present.** The batch persist block has `await db.rollback()` on failure (line 273). Single connection failure does not abort the full batch.

- **sync.py per-row rollback.** The sync loop calls `await db.rollback()` on per-row failure (line 89) and continues with remaining rows — well-handled partial failure pattern.

- **MED-17 (auto-commit on read-only sessions) NOT resolved.** `config/database.py` read-only session configuration was not among the batch changes. Unnecessary WAL overhead on read queries remains.

- **ConsentRepository.delete_by_user_id commits inside the method** (line 231). This is called from within the GDPR deletion transaction, which creates a nested commit inside the parent atomic block — a subtle transaction isolation issue that could cause the GDPR atomicity guarantee to be bypassed for consent records specifically.

Remaining deduction: Auto-commit on read sessions unaddressed. Nested commit in `ConsentRepository.delete_by_user_id` called from the GDPR atomic block is a residual correctness/error handling concern.

---

### 8. Consistency (5 → 6)

**Old score: 5/10**
**New score: 6/10**

Evidence for improvement:

- **UserRepository is now fully consistent** in its raw SQL pattern with `_USER_COLUMNS` constant. The repository layer no longer mixes ORM and Pydantic models.

- **GRANT inconsistencies not addressed.** MED-05 (7 migrations grant to neondb_owner, 2 to public, rest have none) is unchanged.

- **UUID typing not resolved.** `id` fields across models still use `str(uuid4())` — HIGH-22 ORM String(36) vs UUID for `user_id` in compliance ORM models was identified but not fully resolved.

- **MED-08 (timestamp default inconsistency)** between `now()` vs `CURRENT_TIMESTAMP` across migrations is unresolved.

- **duplicate PriceRegion alias** in `models/region.py` and `models/price.py` (LOW-12) not addressed.

- **check-alerts `get_active_alert_configs` LIMIT 5000** is an improvement but an arbitrary cap — the original design intent called for cursor-based pagination that was never implemented.

Remaining deduction: GRANT inconsistencies, UUID typing mix, timestamp default variation, duplicate alias all remain. Score held at 6.

---

### 9. Modernity (6 → 7)

**Old score: 6/10**
**New score: 7/10**

Evidence for improvement:

- **Raw SQL with asyncpg pattern** is now used consistently in the core hot paths (`UserRepository`, `sync.py`, `kpi_report_service.py`, `dunning_service.py`). The removal of Pydantic misuse in ORM context aligns with modern async SQLAlchemy practices.

- **Batch VALUES queries** in `_batch_should_send_alerts()` use parameterised VALUES clause patterns — idiomatic for PostgreSQL bulk operations.

- **DISTINCT ON** in `ConsentRepository.get_consent_status()` (lines 197-215) is idiomatic PostgreSQL replacing Python-side filtering.

- **~30 outdated packages** noted in original audit — not addressed in these batches (out of scope for database layer).

- **Connection pool monitoring** — still absent.

- **MED-22 (pool size 3+5=8 max documented as scaling lever)** — not addressed.

---

## Aggregate Scorecard

| # | Dimension | Old Score | New Score | Change | Primary Evidence |
|---|-----------|-----------|-----------|--------|-----------------|
| 1 | Correctness | 4/10 | 7/10 | +3 | CRIT-03/05: UserRepository raw SQL; HIGH-08 phantom index not present in 005 |
| 2 | Coverage | 4/10 | 6/10 | +2 | Migration 036: 4 new indexes; notifications dedup index confirmed in 026 |
| 3 | Security | 4/10 | 7/10 | +3 | CRIT-02: portal_username encrypted; CRIT-01: OAuth tokens confirmed encrypted |
| 4 | Performance | 5/10 | 8/10 | +3 | HIGH-10/11/12/13 N+1s eliminated; HIGH-14 approx count; HIGH-15 LIMIT 5000 |
| 5 | Maintainability | 5/10 | 7/10 | +2 | HIGH-20: Region validator in User; MED-10: SELECT-before-UPDATE eliminated |
| 6 | Documentation | 7/10 | 8/10 | +1 | Migration 036 header; GDPR atomic docstring; UserRepository raw SQL note |
| 7 | Error Handling | 6/10 | 8/10 | +2 | HIGH-19: GDPR atomic txn; MED-14: dunning single commit |
| 8 | Consistency | 5/10 | 6/10 | +1 | UserRepository internally consistent; GRANT/UUID issues remain |
| 9 | Modernity | 6/10 | 7/10 | +1 | DISTINCT ON; batch VALUES; raw SQL replaces ORM misuse |
| | **Aggregate** | **46/90** | **64/90** | **+18** | |

**Minimum to pass: 72/90**

---

## Verdict: FAIL (64/90)

Score improved from 46 to 64 — an 18-point gain (39% improvement). The 5 batches successfully eliminated the most critical production-safety issues and the hottest N+1 patterns. However, 64/90 remains below the 72/90 minimum threshold.

---

## Remaining Gap to Pass: 8 points

To reach 72/90, the following issues must be resolved. They are ranked by score impact:

### Must-Fix to Pass (estimated +8 points)

| Issue ID | Dimension | Impact | Fix Required |
|----------|-----------|--------|-------------|
| MED-09 | Performance | +1 | Parallelize 7 KPI queries with `asyncio.gather()` in `kpi_report_service.py:aggregate_metrics()` |
| HIGH-18 | Coverage/Performance | +1 | Add `(region, utility_type, timestamp DESC)` composite index on `electricity_prices` in a migration 037 |
| MED-27 | Coverage | +1 | Add index on `users.stripe_customer_id` — payment webhook full scan |
| CRIT-04 | Correctness | +1 | Add `ForeignKey("users.id")` to `ConsentRecordORM.user_id` and `DeletionLogORM.user_id`; fix `deleted_by` to String(100) |
| HIGH-23 | Correctness/Consistency | +1 | Fix `DeletionLogORM.deleted_by` from `String(36)` to `String(100)` to match DB schema |
| ConsentRepo nested commit | Error Handling | +1 | Remove `await self.session.commit()` from `ConsentRepository.delete_by_user_id()` — this fires inside the GDPR atomic block, bypassing rollback coverage for consent records |
| Migration 034 comment | Security/Documentation | +1 | Rename `portal_username` column to `portal_username_encrypted` in DB schema, or add a migration comment clarifying application-side encryption |
| MED-05 | Consistency | +1 | Standardize GRANT statements across all migrations (neondb_owner consistently) |

### Lower Priority (does not block pass threshold)

- HIGH-21: `Supplier.regions` / `Tariff.available_regions` as `List[str]` instead of `List[Region]`
- HIGH-26: Tariff model schema drift (10+ phantom fields)
- MED-17: Auto-commit on read-only sessions
- MED-09 parallelization in KPI (listed above — this one does block the threshold)
- HIGH-01/02/03/04: Missing FK constraints on 4 tables
- HIGH-05: Non-idempotent migration 021
- MED-25/26: UUID and Decimal typing in Pydantic models
- INFO-01: Schema migrations tracking table

---

## Notes on Scoring Methodology

Scores reflect the state of the codebase as directly verified against the 12 listed source files and migration 036. No score was adjusted for issues that could not be directly confirmed. The following items were treated as false positives in the original audit:
- CRIT-01: OAuth token encryption — confirmed already implemented via `email_oauth.py` encrypt path.
- HIGH-08: Phantom index — confirmed absent from current `005_observation_tables.sql`.

The following item was verified as NOT fixed despite being listed in Batch 1's description:
- MED-09: KPI parallel queries — `asyncio.gather` is absent from `kpi_report_service.py`. The 7 sequential awaits remain.

---

_Re-assessment complete. Proceed to remediation round 2 targeting the 8 remaining must-fix items._
