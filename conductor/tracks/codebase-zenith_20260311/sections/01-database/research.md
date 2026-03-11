# Section 1: Database Layer — Research Phase

**Date:** 2026-03-11
**Mode:** Loki Autonomous RARV

---

## Audit Corrections (Index False Positives)

Cross-referencing the audit's "missing indexes" against all 35 migration files revealed **5 of 9 indexes already exist**:

| Audit Finding | Existing Index | Migration | Status |
|---------------|---------------|-----------|--------|
| `electricity_prices(region, utility_type, timestamp DESC)` | `idx_prices_region_utilitytype_timestamp` | 010 | EXISTS |
| `electricity_prices(region, supplier, timestamp DESC)` | `idx_prices_region_supplier_timestamp` | 004 | EXISTS |
| `notifications(metadata->>'dedup_key', user_id, created_at DESC)` | `idx_notifications_dedup_key` | 026 | EXISTS |
| `payment_retry_history(stripe_invoice_id)` | `idx_payment_retry_invoice` | 024 | EXISTS |
| `users(stripe_customer_id)` | `idx_users_stripe_customer_id` | 004 | EXISTS |

**Genuinely missing indexes (4):**
1. `alert_history(user_id, alert_type, region, triggered_at DESC)` — only simple single-column indexes exist
2. `price_alert_configs(is_active, created_at) WHERE is_active = TRUE` — only `idx_alert_configs_active` on (is_active) alone
3. `user_connections(connection_type, status, updated_at ASC) WHERE status = 'active'` — different composites exist but not this one
4. `consent_records(user_id, purpose, timestamp DESC)` — `idx_consent_user_purpose` on (user_id, purpose) exists but without timestamp

**Updated audit score impact:** HIGH-16/17/18 findings partially invalidated. Reduces HIGH count from 26 to 23 (3 false positives removed). Adjusts Performance dimension from 5/10 to 6/10. New aggregate: **48/90** (still below 72/90 minimum).

---

## CRIT-03/05: UserRepository ORM Issue — Production Impact Analysis

### Callers in Production Code
- `api/dependencies.py:246` — Creates `UserRepository(db)` instances via DI
- `services/recommendation_service.py:60` — Takes `user_repo: UserRepository` param, calls `get_by_id()`
- `services/stripe_service.py:497` — Takes `user_repo: UserRepository` param for webhook processing
- `api/v1/billing.py` — Uses `UserRepository` for subscription management

### How This Works Without Crashing
The `conftest.py` mock patches `select()` so tests pass. In production, the auth layer (`neon_auth.py`) uses **raw SQL** for user creation/lookup, completely bypassing `UserRepository`. The DI system creates `UserRepository` instances, but the critical auth paths (`ensure_user_profile`, session validation) never use them.

**However**, `StripeService.apply_webhook_action()` DOES call `user_repo.get_by_id()` and `user_repo.update()` — this means **Stripe webhook processing is broken in production** if it actually goes through UserRepository rather than being mocked. Need to verify if `StripeService` is actually called in prod or if webhooks use a different path.

### Fix Approach
**Option A (Quick)**: Convert UserRepository methods from `select(User)` to raw SQL `text()` — matching the working pattern in `neon_auth.py`. Low risk, consistent with existing patterns.

**Option B (Proper)**: Create `UserORM` declarative base class, use it in repository, translate to/from Pydantic `User` at boundaries. Higher effort, but architecturally correct.

**Recommendation**: Option A for Tier 1 (immediate safety), plan Option B for Section 2 (Models & ORM).

---

## CRIT-01: OAuth Token Encryption

### Current State
- Migration 009 adds `oauth_access_token TEXT` and `oauth_refresh_token TEXT` as **plaintext** columns on `user_connections`
- Tokens are read in `email_scan.py`, `email_oauth.py`, and `email_scanner_service.py`
- Portal credentials (migration 034) correctly use AES-256-GCM via `backend/utils/encryption.py`

### Encryption Utility
`backend/utils/encryption.py` provides:
- `encrypt_field(plaintext: str) -> bytes` — AES-256-GCM with random 12-byte nonce
- `decrypt_field(data: bytes) -> str` — corresponding decryption
- Uses `FIELD_ENCRYPTION_KEY` env var (32-byte hex key)
- Already tested in `test_encryption.py`

### Fix Approach
1. New migration: ALTER `oauth_access_token` and `oauth_refresh_token` from TEXT to BYTEA
2. Update all write paths to call `encrypt_field()` before INSERT/UPDATE
3. Update all read paths to call `decrypt_field()` after SELECT
4. Create a backfill script to encrypt existing plaintext tokens (one-time run)
5. Same pattern for `portal_username` (CRIT-02)

### Risk: Data loss if encryption key is lost or rotated without migration. Must add key backup to 1Password vault.

---

## N+1 Fix Research

### sync.py (HIGH-10): UPSERT + xmax SELECT
**Current**: 2 queries per row (UPSERT + separate `SELECT xmax`)
**Fix**: Add `RETURNING id, (xmax = 0) AS is_insert` to the UPSERT — collapses to 1 query per row
**Code-only change**: Yes, no schema changes needed
**Test coverage**: `test_internal_sync.py` exists

### alerts.py (HIGH-11): Per-alert dedup query
**Current**: `_should_send_alert()` called in a loop, each executing a SELECT on `alert_history`
**Fix**: Batch query all `(user_id, alert_type, region)` tuples with a single SELECT, build lookup set
**Code-only change**: Yes
**Test coverage**: `test_alerts.py` exists

### email_scan.py (HIGH-12): Per-email INSERT + COMMIT
**Current**: INSERT + COMMIT inside a `for email_result in utility_emails` loop
**Fix**: Collect extracted rates, batch INSERT with `executemany()`, single COMMIT
**Code-only change**: Yes
**Test coverage**: `test_internal_scan_emails.py`, `test_email_scan_extraction.py`

### dunning_service.py (HIGH-13): Multiple transactions per webhook
**Current**: 3-4 separate COMMIT calls in `handle_payment_failure`
**Fix**: Move all COMMITs to end of orchestrator, use single transaction
**Code-only change**: Yes
**Test coverage**: `test_dunning_service.py`

---

## Missing Index Migration (036)

Only 4 indexes genuinely need to be created:

```sql
-- Migration 036: Performance indexes from database audit
-- All indexes are IF NOT EXISTS for idempotency

-- 1. alert_history composite for dedup queries (HIGH-17)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alert_history_dedup
    ON alert_history (user_id, alert_type, region, triggered_at DESC);

-- 2. price_alert_configs for check-alerts cron (MED-23)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_alert_configs_active_created
    ON price_alert_configs (is_active, created_at)
    WHERE is_active = TRUE;

-- 3. user_connections for email scan cron (MED-19)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_connections_type_status_updated
    ON user_connections (connection_type, status, updated_at ASC)
    WHERE status = 'active';

-- 4. consent_records for GDPR latest-consent query (MED-16)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_consent_records_user_purpose_time
    ON consent_records (user_id, purpose, timestamp DESC);
```

**Note**: Index-only migrations are explicitly allowed by the Zenith spec constraints.

---

## GDPR Atomic Deletion

**Current flow** in `compliance/gdpr.py:601-775`:
1. `consent_repo.delete_by_user_id()` — commits
2. `price_alert_repo.delete_by_user_id()` — commits
3. Raw SQL deletes (extracted_rates, bill_uploads, connections, supplier_accounts)
4. `user_repo.delete()` — commits

**Problem**: If step 3 fails, consent records are already deleted but user profile remains.

**Fix**: Wrap in `async with db.begin()` and remove individual commits from each step. The GDPR compliance requirement mandates all-or-nothing deletion. If user_repo.delete() is broken (CRIT-03), convert the final deletion to raw SQL first.

---

_Research complete. Proceeding to Plan phase._
