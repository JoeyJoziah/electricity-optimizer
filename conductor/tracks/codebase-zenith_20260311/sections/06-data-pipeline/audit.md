# Section 6: Data Pipeline (Internal Endpoints) — Clarity Gate Audit

**Date:** 2026-03-12
**Auditor:** Claude Code (Direct)
**Score:** 76/90 (PASS)

---

## Aggregate Scores

| # | Dimension | Score |
|---|-----------|-------|
| 1 | Correctness | 8/10 |
| 2 | Coverage | 9/10 |
| 3 | Security | 9/10 |
| 4 | Performance | 8/10 |
| 5 | Maintainability | 8/10 |
| 6 | Documentation | 9/10 |
| 7 | Error Handling | 8/10 |
| 8 | Consistency | 8/10 |
| 9 | Modernity | 9/10 |
| | **TOTAL** | **76/90** |

---

## Files Analyzed (8 files, ~1,200 lines)

`api/v1/internal/__init__.py`, `api/v1/internal/data_pipeline.py`, `api/v1/internal/sync.py`, `api/v1/internal/alerts.py`, `api/v1/internal/billing.py`, `api/v1/internal/operations.py`, `api/v1/internal/email_scan.py`, `api/v1/internal/portal_scan.py`

---

## Architecture Assessment

Clean modular structure: internal package `__init__.py` combines 8 sub-domain routers under a single `verify_api_key` dependency. Each file owns a domain (alerts, billing, data pipeline, sync, email scan, portal scan). All endpoints are POST-based, called by GHA cron workflows with `INTERNAL_API_KEY` header.

## HIGH Findings (3)

**H-01: sync.py per-row upsert instead of batch**
- File: `api/v1/internal/sync.py:53-89`
- `sync_neon_users` executes one SQL upsert per neon_auth user row in a loop
- For large user bases (1000+), this becomes N separate DB round-trips
- Fix: Use a single `INSERT ... ON CONFLICT` with `executemany()` or VALUES list

**H-02: sync.py rollback within loop may corrupt transaction state**
- File: `api/v1/internal/sync.py:89`
- `await db.rollback()` inside the per-row `except` block rolls back the *entire* transaction, not just the failed row
- Subsequent upserts in the loop may silently fail or operate on stale state
- Fix: Use `SAVEPOINT` per row or batch the operation with explicit error collection

**H-03: alerts.py calls private `_batch_should_send_alerts` method**
- File: `api/v1/internal/alerts.py:127`
- Endpoint logic directly calls `service._batch_should_send_alerts()` (private method)
- This couples the endpoint to AlertService internals
- Fix: Expose as a public method or integrate dedup into `send_alerts()`

## MEDIUM Findings (3)

**M-01: data_pipeline.py fetch-weather iterates all 51 regions sequentially**
- File: `api/v1/internal/data_pipeline.py`
- Weather fetch for all US states uses `asyncio.gather` with Semaphore(10), which is good, but the semaphore is created fresh each call
- No caching of recently fetched weather data between runs
- Fix: Add a short-TTL cache to avoid re-fetching if called within 6h window

**M-02: Service construction in request handlers**
- Files: `alerts.py:40-63`, `sync.py:115`
- `AlertService`, `NotificationDispatcher`, `ConnectionSyncService` are constructed inside request handlers
- Not consistent with FastAPI `Depends()` pattern used elsewhere
- Fix: Use dependency injection for consistency

**M-03: No request timeout on internal endpoints**
- Internal endpoints are excluded from `RequestTimeoutMiddleware` (by design for long-running jobs)
- However, there's no per-endpoint timeout either — a stuck weather API could block indefinitely
- Fix: Add `asyncio.wait_for()` with a generous timeout (e.g., 5 minutes)

## Strengths

- **Unified API key gate**: Single `verify_api_key` dependency at package level secures all 8 sub-routers
- **Structured logging**: All endpoints use structlog with semantic event names
- **Error isolation**: `check-alerts` continues sending remaining alerts even if one fails
- **Upsert safety**: `sync-users` uses `ON CONFLICT DO UPDATE` with conditional WHERE clause
- **Comprehensive alert pipeline**: 6-step pipeline (configs -> prices -> thresholds -> dedup -> send -> record)
- **Batch dedup**: Alert dedup uses batch query per frequency tier instead of N+1 queries

**Verdict:** PASS (76/90). Well-structured internal API with proper auth gating and good separation of concerns. Main issues are per-row sync operations and transaction handling in the sync endpoint.
