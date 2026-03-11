# Section 4: Services Layer — Clarity Gate Audit

**Date:** 2026-03-12
**Auditor:** Claude Code (Explore agent)
**Score:** 65/90 (FAIL — threshold 72/90)

---

## Aggregate Scores

| # | Dimension | Score |
|---|-----------|-------|
| 1 | Correctness | 7/10 |
| 2 | Coverage | 7/10 |
| 3 | Security | 6/10 |
| 4 | Performance | 6/10 |
| 5 | Maintainability | 8/10 |
| 6 | Documentation | 9/10 |
| 7 | Error Handling | 7/10 |
| 8 | Consistency | 7/10 |
| 9 | Modernity | 8/10 |
| | **TOTAL** | **65/90** |

---

## CRITICAL Findings

**C-001: Resend SDK `send()` is synchronous — blocks event loop**
- File: `backend/services/email_service.py`
- The Resend Python SDK's `Emails.send()` is a synchronous HTTP call. Calling it from an async handler blocks the event loop for the duration of the API round-trip (~200-500ms).
- Fix: Wrap in `asyncio.to_thread()` or use httpx directly for async Resend calls.

**C-002: Agent async job has no DB session, rate limit bypass possible**
- File: `backend/services/agent_service.py`
- The `POST /agent/task` async job creates a background task but does not acquire a DB session or check rate limits within the background context. Rate limiting is only enforced at the route level; a crafted request could bypass it.
- Fix: Move rate limit check into the service layer; acquire DB session inside the background task.

**C-003: Dunning DISTINCT ON has wrong ORDER BY**
- File: `backend/services/dunning_service.py`
- `DISTINCT ON (user_id)` query orders by `created_at ASC` but the intent is to get the latest payment failure. Should order by `created_at DESC`.
- Fix: Change `ORDER BY user_id, created_at ASC` to `ORDER BY user_id, created_at DESC`.

**C-004: Resend fallback to Gmail SMTP has no timeout**
- File: `backend/services/email_service.py`
- Gmail SMTP fallback uses nodemailer-style transport without explicit socket/connection timeouts. A DNS or SMTP hang will block the worker indefinitely.
- Fix: Add `timeout=30` to SMTP connection parameters.

**C-005: Prompt injection in Gemini agent call**
- File: `backend/services/agent_service.py`
- User query is interpolated directly into the system prompt template without sanitization. A crafted query can override system instructions.
- Fix: Use separate system/user message roles; never interpolate user input into system prompts.

## HIGH Findings

**H-001: PII in structured logs**
- Multiple service files log user emails, names, and session tokens at INFO level.
- Fix: Redact PII fields in log output; use user IDs only.

**H-002: Email service retry has no exponential backoff**
- Fix: Add jitter + exponential backoff between retry attempts.

**H-003: sync-connections processes sequentially**
- File: `backend/services/price_sync_service.py`
- Each connection is synced sequentially. With 100+ active connections, the cron can exceed its window.
- Fix: Use `asyncio.gather()` with `Semaphore` for bounded parallelism.

**H-004: Weather fetch has no circuit breaker**
- External API failures cascade into repeated timeout waits.
- Fix: Implement circuit breaker pattern (fail-fast after N consecutive failures).

**H-005: KPI service dead helper methods**
- File: `backend/services/kpi_report_service.py`
- After CTE refactor, `_count_active_users_7d`, `_count_total_users`, `_count_prices_tracked`, `_count_alerts_sent_today`, `_weather_freshness_hours` are unused.
- Fix: Remove dead methods.

**H-006: Market research stores raw HTML in JSONB**
- Diffbot/Tavily responses stored without size limits; large articles can balloon the `market_intelligence` table.
- Fix: Truncate content to 10KB max before storage.

**H-007: Alert service LIMIT 5000 is arbitrary cap**
- `get_active_alert_configs()` silently truncates at 5000 rows.
- Fix: Implement cursor-based pagination or at minimum log a warning at capacity.

**H-008: Portal scraper has no request timeout per page**
- httpx client used without per-request timeout; a hanging portal page blocks the scraper indefinitely.
- Fix: Add `timeout=httpx.Timeout(30.0)` to each request.

**H-009: GDPR deletion misses 4 tables**
- `delete_user_data()` does not delete from `agent_conversations`, `agent_tasks`, `connection_extracted_rates`, `bill_uploads`.
- Fix: Add DELETE statements for all user-linked tables.

## MEDIUM Findings (11)

- M-001: `email_service.py` template rendering has no XSS escaping for dynamic content
- M-002: Dunning email sends are fire-and-forget with no delivery confirmation
- M-003: Price sync service uses `SELECT *` without column limits
- M-004: Alert dedup cooldown uses application time, not DB server time
- M-005: Weather service caches in DB but no Redis layer for hot reads
- M-006: Supplier scraping retry count not persisted across process restarts
- M-007: Agent service Composio tool list is hardcoded, not configurable
- M-008: KPI report has no caching — regenerates on every request
- M-009: Portal scraper AES key loaded on every call (should cache)
- M-010: Email scan attachment download has no size limit
- M-011: Savings calculation uses float arithmetic for currency

## LOW Findings (8)

- L-001 through L-008: Naming inconsistencies, unused imports, missing type annotations on internal helpers, stale TODO comments

---

## Priority: C-001 Resend async, C-003 dunning ORDER BY, C-005 prompt injection, H-009 GDPR deletion completeness, then H-003 sync parallelism
