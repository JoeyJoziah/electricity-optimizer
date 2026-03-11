# Section 1: Database Layer — Execution Plan

**Date:** 2026-03-11
**Mode:** Loki Autonomous RARV
**Approach:** TDD-first, zero-regression, bite-sized commits

---

## Execution Batches

### Batch 1: Fix N+1 Query Patterns (Code-Only, No Schema Changes)

**Task 1.1**: Fix sync-users N+1 (HIGH-10)
- File: `backend/api/v1/internal/sync.py:56-83`
- Change: Add `RETURNING id, (xmax = 0) AS is_insert` to UPSERT, remove separate SELECT
- Test: Update `test_internal_sync.py` — verify created/updated/skipped counts still correct
- Risk: LOW — RETURNING is standard PostgreSQL

**Task 1.2**: Fix check-alerts dedup N+1 (HIGH-11)
- File: `backend/services/alert_service.py:399-416` (the `_should_send_alert` query)
- File: `backend/api/v1/internal/alerts.py:126-138` (the loop calling it)
- Change: Batch dedup query — single SELECT for all `(user_id, alert_type, region)` tuples, build lookup set
- Test: Update alert tests to verify batch dedup produces same results as per-row dedup
- Risk: MEDIUM — must handle empty tuples edge case

**Task 1.3**: Fix email scan N+1 + commit-per-row (HIGH-12)
- File: `backend/api/v1/internal/email_scan.py:220-247`
- Change: Collect extracted rates into list, batch INSERT, single COMMIT per connection
- Test: Update `test_internal_scan_emails.py` — verify rates_extracted count matches
- Risk: LOW — ON CONFLICT DO NOTHING already handles duplicates

**Task 1.4**: Consolidate dunning service transactions (HIGH-13)
- File: `backend/services/dunning_service.py:305-384`
- Change: Remove intermediate COMMITs, single COMMIT at end of `handle_payment_failure`
- Test: Update `test_dunning_service.py` — verify single-commit behavior
- Risk: MEDIUM — must ensure rollback on failure doesn't lose partial state

**Task 1.5**: Parallelize KPI report queries (MED-09)
- File: `backend/services/kpi_report_service.py:38-55`
- Change: Replace 7 sequential awaits with `asyncio.gather(*queries)`
- Test: Verify KPI report returns same values
- Risk: LOW — queries are independent

**Task 1.6**: Fix unbounded electricity_prices COUNT (HIGH-14)
- File: `backend/services/kpi_report_service.py:73-77`
- Change: Use `pg_class.reltuples` for approximate count
- Test: Verify count returns reasonable number
- Risk: LOW — KPI report uses approximate counts

**Task 1.7**: Add LIMIT to unbounded alert configs query (HIGH-15)
- File: `backend/services/alert_service.py:443-463`
- Change: Add cursor-based pagination (batches of 1000)
- Test: Update alert service tests for pagination
- Risk: MEDIUM — must process all batches, not just first

### Batch 2: Convert UserRepository to Raw SQL (CRIT-03/05)

**Task 2.1**: Convert `get_by_id()` to raw SQL
- File: `backend/repositories/user_repository.py:45-55`
- Change: Replace `select(User).where(User.id == id)` with `text("SELECT ... FROM users WHERE id = :id")`
- Test: Existing tests should pass without mock_sqlalchemy_select
- Risk: HIGH — must map all 25+ User columns correctly

**Task 2.2**: Convert `get_by_email()` to raw SQL
- File: `backend/repositories/user_repository.py:64-74`
- Same pattern as 2.1

**Task 2.3**: Convert `create()`, `update()`, `delete()` to raw SQL
- File: `backend/repositories/user_repository.py` — multiple methods
- Change: Replace ORM operations with parameterized INSERT/UPDATE/DELETE
- Test: Verify CRUD operations work without mocks
- Risk: HIGH — update() has dynamic field selection

**Task 2.4**: Convert `list()`, `count()`, `get_users_by_region()` to raw SQL
- Add LIMIT to `get_users_by_region()` (MED-11)
- Test: Verify pagination works

**Task 2.5**: Convert SupplierRepository similarly
- File: `backend/repositories/supplier_repository.py`
- Same pattern as UserRepository

**Task 2.6**: Eliminate SELECT-before-UPDATE pattern (MED-10)
- Files: `update_last_login()`, `set_email_verified()`, `record_consent()`
- Change: Direct UPDATE with RETURNING instead of SELECT + dirty tracking
- Test: Verify methods return correct boolean

### Batch 3: Security — Encrypt OAuth Tokens (CRIT-01/02)

**Task 3.1**: Create migration 036 for column type changes
- Change: ALTER `oauth_access_token` and `oauth_refresh_token` from TEXT to BYTEA
- Change: ALTER `portal_username` from TEXT to BYTEA
- Add the 4 missing indexes from research phase
- Test: Migration runs idempotently

**Task 3.2**: Update OAuth token write paths
- Files: `email_oauth.py`, `connections/crud.py`
- Change: Call `encrypt_field()` before INSERT/UPDATE of tokens
- Test: Verify encrypted tokens are stored as bytes

**Task 3.3**: Update OAuth token read paths
- Files: `email_scan.py`, `email_scanner_service.py`, `connection_sync_service.py`
- Change: Call `decrypt_field()` after SELECT of tokens
- Test: Verify tokens are correctly decrypted for API calls

**Task 3.4**: Update portal username encryption
- File: `connections/portal_scrape.py`
- Change: Encrypt `portal_username` alongside `portal_password_encrypted`
- Test: Verify round-trip encrypt/decrypt

**Task 3.5**: Create one-time backfill script
- Encrypt existing plaintext tokens in-place
- Must be reversible (log which rows were encrypted)

### Batch 4: GDPR Atomic Deletion (HIGH-19)

**Task 4.1**: Wrap `delete_user_data` in atomic transaction
- File: `backend/compliance/gdpr.py:601-775`
- Change: Use `async with db.begin()`, remove individual commits
- Convert the final `user_repo.delete()` to raw SQL (depends on Batch 2)
- Test: Verify all-or-nothing deletion behavior
- Test: Verify partial failure rolls back all changes

### Batch 5: Missing Indexes + Cleanup

**Task 5.1**: Create migration 036 (or 037 if 036 used in Batch 3)
- 4 missing indexes from research phase
- All `CREATE INDEX CONCURRENTLY IF NOT EXISTS`

**Task 5.2**: Add Region enum validation to User model (HIGH-20)
- File: `backend/models/user.py`
- Change: Add `field_validator('region')` using Region enum
- Test: Verify invalid regions are rejected

**Task 5.3**: Fix consent_records DISTINCT ON query (MED-16)
- File: `backend/compliance/repositories.py:176-200`
- Change: Replace Python-side filtering with SQL DISTINCT ON
- Test: Verify latest consent per purpose is correct

---

## Execution Order & Dependencies

```
Batch 1 (N+1 fixes) ─── no dependencies, safe first
    │
Batch 2 (UserRepo raw SQL) ─── depends on understanding conftest mock
    │
Batch 3 (Encryption) ─── can run parallel with Batch 2
    │
Batch 4 (GDPR atomic) ─── depends on Batch 2 (user_repo.delete → raw SQL)
    │
Batch 5 (Indexes + cleanup) ─── can run last, low risk
```

## Success Criteria
- All 2,045 backend tests pass
- No new test failures introduced
- Clarity Gate re-score >= 72/90
- Zero N+1 queries in cron hot paths
- OAuth tokens encrypted at rest
- GDPR deletion is atomic

---

_Plan complete. Proceeding to Execute phase._
