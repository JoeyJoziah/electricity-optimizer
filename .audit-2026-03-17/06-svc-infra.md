# Audit Report: Infrastructure Services
## Date: 2026-03-17

### Executive Summary

The infrastructure services layer is generally well-structured, with good use of structured logging, deduplication guards, and the dispatcher pattern for multi-channel notifications. However, five significant issues were found: a missing `await db.commit()` in `DunningService.record_payment_failure()` that can leave the database in an inconsistent state before the email step runs; `data_persistence_helper.persist_batch()` committing only when at least one row succeeds, meaning partial failures can silently produce partial commits; unbounded parameter expansion in `_batch_insert_extracted_rates` and `_batch_should_send_alerts` that will break Postgres for large payloads; `asyncio.gather(return_exceptions=True)` silently swallowing exceptions raised by `_dispatch_push` and `_dispatch_email` inner functions; and a KPI query that uses `pg_class.reltuples` (a stale estimate, not a live count) while labelling the field `prices_tracked`. Minor concerns include an unindexed JSONB dedup lookup, the fallback `scrape_results` path in `DataQualityService` that unconditionally marks all records as successful, and dead code in `connection_sync_service.py`.

---

### Findings

#### P0 — Critical

- **[P0-01]** Missing commit after recording dunning failure — `dunning_service.py:73-105` — `record_payment_failure()` inserts a `payment_retry_history` row but never calls `await self._db.commit()`. The parent `handle_payment_failure()` only commits at the end (line 384), so if `send_dunning_email()` raises an uncaught exception before the final commit, the INSERT is rolled back entirely. This means payment failures can vanish from the audit trail. More importantly, `should_send_dunning()` (called at line 338) queries the same session _after_ the uncommitted INSERT, so within the same session the row is visible (correct), but if the session is a different transaction scope the row will not exist. The safest fix is to commit immediately after the INSERT, then treat email + escalation + their updates as a separate unit.

  **Impact**: Silent loss of payment failure audit records on any exception during the email step.

  **Fix**: Add `await self._db.commit()` at line 105 (after the `record_payment_failure` INSERT), then wrap the email send + subsequent UPDATEs in a separate `try/except` with their own commit.

---

#### P1 — High

- **[P1-01]** `persist_batch` commits only on partial success, creating silent partial-commit batches — `data_persistence_helper.py:53-55` — The commit at line 54 fires only when `persisted > 0`, meaning a batch where 5 out of 10 rows failed will commit the 5 that succeeded without any signal to the caller that the batch was partial. Callers cannot distinguish "committed 5" from "committed 10". In practice, any downstream re-run relying on `ON CONFLICT DO NOTHING` would be safe, but callers without idempotent INSERTs could persist corrupt partial state.

  **Impact**: Silent partial commits; upstream callers receive a count but no indication that the batch was incomplete.

  **Fix**: Return a tuple `(persisted, failed_count)` instead of just `persisted`, and log the failed count at `WARNING` level. Document clearly that each INSERT is its own autoflush, and that the single commit covers all successful rows, so callers must verify the returned count.

- **[P1-02]** `_batch_insert_extracted_rates` is unbounded — `connection_sync_service.py:407-441` — The method builds a single `VALUES` clause covering every record in `rate_records` with no chunking. A UtilityAPI response returning hundreds of bills (multiple meters, historical backfill) will produce a single INSERT statement with hundreds of parameter placeholders. asyncpg imposes a 65,535-parameter limit; the VALUES approach also generates very large SQL strings that can degrade the Postgres query planner.

  **Impact**: For connections with large historical backlogs, the batch INSERT raises an asyncpg `TooManyParameters` error, causing the entire sync to fail and leaving `status = 'error'` permanently.

  **Fix**: Chunk `rate_records` in slices of at most 500 rows (matching the pattern used in `_batch_should_send_alerts`), and call `_db.execute` + commit per chunk inside the loop.

- **[P1-03]** `asyncio.gather(return_exceptions=True)` silently discards exceptions from inner coroutines — `notification_dispatcher.py:254` — `_dispatch_push` and `_dispatch_email` are async _functions_ defined inside `send()`, not coroutines that naturally raise. However, if an unhandled exception escapes `_send_push` or `_send_email` outside their `try/except` blocks (e.g., a bug in `_persist_channel_outcome`), `return_exceptions=True` silently converts it to a value in the returned list. That list is never inspected (line 254 result is discarded). The caller at `alert_service.py:279-306` checks `dispatch_result.get("channels", {})` — but channels might be missing entries for PUSH or EMAIL if exceptions escaped.

  **Impact**: Push and email delivery failures caused by internal bugs (not external service errors) are completely invisible. No log entry, no metric, no alert.

  **Fix**: After the `gather`, inspect the returned list for `BaseException` instances and log them at `ERROR` level:
  ```python
  gather_results = await asyncio.gather(_dispatch_push(), _dispatch_email(), return_exceptions=True)
  for res in gather_results:
      if isinstance(res, BaseException):
          logger.error("notification_dispatch_inner_exception", error=str(res))
  ```

- **[P1-04]** Dedup check in `_is_duplicate` performs an unindexed JSONB text scan — `notification_dispatcher.py:474-491` — The query `metadata ->> 'dedup_key' = :dedup_key` filters a JSONB column by a nested text value. Unless there is a functional index on `(user_id, (metadata->>'dedup_key'), created_at)`, Postgres must scan all notifications rows for the user within the time window. As notification volume grows (100k+ rows), this becomes a sequential scan on a hot table.

  **Impact**: Dedup check latency grows linearly with notification table size; at scale this can add hundreds of milliseconds to every dispatched notification.

  **Fix**: Add a partial index in a migration:
  ```sql
  CREATE INDEX CONCURRENTLY idx_notifications_dedup
      ON notifications (user_id, (metadata->>'dedup_key'), created_at)
      WHERE metadata IS NOT NULL AND metadata ? 'dedup_key';
  ```

- **[P1-05]** `get_overdue_accounts` DISTINCT ON ordering is semantically incorrect — `dunning_service.py:399-414` — `DISTINCT ON (prh.user_id)` with `ORDER BY prh.user_id, prh.created_at DESC` returns the _most recent_ `payment_retry_history` row per user — but the `WHERE prh.created_at <= :cutoff` clause filters to rows _older than_ the grace period. If a user has both an old failure and a new failure, the `DISTINCT ON` keeps the most recent row that passes the `WHERE` filter, which is correct in isolation. However, `retry_count` on that row reflects only that specific row's insert-time count, not the total accumulated retries. A user on retry 4 might show `retry_count = 1` if their oldest-within-cutoff row was the first attempt.

  **Impact**: Dunning escalation decisions (`escalate_if_needed`) based on this `retry_count` may use the wrong value, potentially failing to downgrade users who should be downgraded, or (less likely) double-downgrading.

  **Fix**: Aggregate `MAX(retry_count)` across all rows for each user rather than relying on `DISTINCT ON`:
  ```sql
  SELECT prh.user_id,
         MAX(prh.retry_count) AS retry_count,
         ...
  FROM payment_retry_history prh
  JOIN public.users u ON u.id = prh.user_id
  WHERE prh.created_at <= :cutoff
    AND u.subscription_tier != 'free'
    AND u.is_active = TRUE
  GROUP BY prh.user_id, prh.stripe_invoice_id, prh.stripe_customer_id,
           prh.amount_owed, prh.currency, u.email, u.name, u.subscription_tier
  ```

- **[P1-06]** `get_active_alert_configs` hardcoded LIMIT 5000 with no pagination — `alert_service.py:534` — The cron endpoint fetches all active alert configs in a single query capped at 5,000 rows. If the user base grows beyond 5,000 active alert configs, the remainder are silently skipped and never receive alerts until the next cron run — and they will still be silently skipped then.

  **Impact**: Users with alert configs beyond position 5,000 in the `ORDER BY created_at` list never receive price alerts. This fails silently with no error or metric.

  **Fix**: Add cursor-based pagination (keyset on `created_at, id`) and loop the cron endpoint until an empty page is returned, or remove the hardcoded limit and document the expected max scale. Alternatively, partition by `created_at` range per cron invocation.

---

#### P2 — Medium

- **[P2-01]** `_batch_should_send_alerts` dynamic SQL is vulnerable to unbounded parameter count — `alert_service.py:460-490` — The method batches dedup checks in chunks of 500 (BATCH_SIZE at line 458), which is good. However, `value_clauses` inside each chunk builds SQL like `VALUES (:uid_0, :atype_0, :reg_0), (:uid_1, ...)` where each tuple requires 3 params. A chunk of 500 tuples produces 1,500 bound parameters, which is well within asyncpg's 65,535 limit. This is safe as-is, but the comment at line 458 references "500" without explaining the 3x multiplier relationship to asyncpg limits. If BATCH_SIZE is ever increased carelessly (e.g., to 5000), the query would exceed the parameter limit.

  **Impact**: Latent risk of breakage if BATCH_SIZE is increased without considering the 3-params-per-tuple multiplication.

  **Fix**: Add a comment explaining the limit: `# 500 tuples × 3 params each = 1,500 params — well within asyncpg's 65,535 limit`. Consider asserting `BATCH_SIZE * 3 < 65535` at module level.

- **[P2-02]** `DataQualityService.get_source_reliability` fallback silently marks all records as successful — `data_quality_service.py:212-222` — When `scrape_results` does not exist, the fallback queries `electricity_prices` and sets `successes = r["total"]` and `failures = 0`, `failure_rate = 0.0`, `is_degraded = False` for every source. This means any configured monitoring or alerting based on `is_degraded` will never trigger in the fallback path, regardless of actual source health.

  **Impact**: Data quality monitoring is completely blind to source failures when running on the fallback path. Degraded data sources appear healthy in dashboards.

  **Fix**: Either (a) always create the `scrape_results` table (it should be part of the migrations), or (b) mark the fallback response with an explicit `"monitoring_limited": True` flag and log a warning rather than silently inferring success.

- **[P2-03]** `MaintenanceService` has no transaction rollback on partial FK failure — `maintenance_service.py:63-106` — `cleanup_expired_uploads` deletes from `connection_extracted_rates` and then from `bill_uploads` in the same implicit transaction, committing once (line 93). If the second DELETE raises an exception (e.g., a race condition with a concurrent insert that added a FK-linked record), the first DELETE is already executed on the session but the commit has not yet fired. Since SQLAlchemy async sessions buffer DML, the exception will trigger a rollback automatically — but the file cleanup loop at lines 96-102 runs _after_ the commit, so files could be deleted even if the DB commit failed in a subsequent call pattern. The bigger issue: there is no explicit check that the first DELETE succeeded before issuing the second.

  **Impact**: If the DELETE from `connection_extracted_rates` fails silently (wrong column name after a schema change, for example), the orphaned rate records remain but the upload records are deleted, creating dangling FK references.

  **Fix**: Wrap both DELETEs in a single explicit `BEGIN`/`COMMIT` block or restructure so the commit is verified before file deletion. The current pattern is actually safe with async SQLAlchemy's unit-of-work, but the file deletion after commit should be wrapped in a try/except with a warning log.

- **[P2-04]** `ConnectionAnalyticsService` is missing `structlog` — `connection_analytics_service.py` — No logger is imported or used. Errors from any of the four public methods (e.g., a DB query exception) propagate directly to the caller with no structured log context. The other analytics/sync services in this module all use `structlog`.

  **Impact**: Production errors in rate comparison, history, savings estimate, and stale connection checks produce no structured log events. Debugging requires reconstructing context from FastAPI exception logs alone.

  **Fix**: Add `import structlog` and `logger = structlog.get_logger(__name__)`, then wrap DB calls in try/except with `logger.error(...)` and re-raise.

- **[P2-05]** `KPIReportService` uses `pg_class.reltuples` (a stale estimate) for `prices_tracked` — `kpi_report_service.py:53-55` — `pg_class.reltuples` is updated by AUTOVACUUM and may lag actual row count by hours or days, especially for a table that receives high write volume (price ingestion every few hours). The field is labelled `prices_tracked` in the returned dict, implying an accurate count.

  **Impact**: The KPI report's `prices_tracked` metric can be wildly inaccurate (under or over by millions of rows depending on when AUTOVACUUM last ran). Business decisions made on this number are unreliable.

  **Fix**: Replace with a `COUNT(*)` against a recent time window (e.g., `SELECT COUNT(*) FROM electricity_prices WHERE timestamp >= NOW() - INTERVAL '30 days'`) to get a meaningful and accurate count, or retain the estimate but clearly rename it `prices_tracked_estimate` and document the source.

- **[P2-06]** `alert_service.py` `create_alert` `FOR UPDATE` lock does not span the entire transaction — `alert_service.py:697-741` — The `SELECT ... FOR UPDATE` on the users row correctly serialises concurrent alert creations. However, `db.commit()` is called at line 741 which releases the lock _and_ commits the INSERT in a single step. If the session is shared (reused from a connection pool by a concurrent request between the `FOR UPDATE` acquisition and the commit), the lock window is correct. However, if a caller passes `db=None` (line 687 falls back to `self._db`), and `self._db` is the same session reused across multiple coroutines, there is a potential for the lock to be held across an `await` for the INSERT, which asyncpg handles correctly. The actual risk here is lower than it appears, but the dual-session logic (explicit `db` arg vs. `self._db`) is fragile. Callers passing the wrong session could bypass the lock entirely.

  **Impact**: Two concurrent free-tier users might both pass the count check and both create alerts, exceeding the 1-alert limit.

  **Fix**: Remove `self._db` as a fallback in `create_alert` — require `db` to always be passed explicitly. This makes the transaction boundary explicit and avoids the dual-session ambiguity.

- **[P2-07]** `alert_renderer.py` silently discards template rendering exceptions — `alert_renderer.py:81-83` — `render_alert_email` catches all `Exception` with a bare `except Exception:` and falls back to inline HTML. The exception is neither logged nor re-raised, so template errors (missing template file, Jinja syntax error, wrong variable name) are invisible in production logs.

  **Impact**: Template regressions silently fall back to the minimal HTML template with no alerting. Engineers will not discover template breakage until manual inspection or a user complaint.

  **Fix**: Log the exception before falling back:
  ```python
  except Exception as exc:
      logger.warning("alert_template_render_failed", template="price_alert.html", error=str(exc))
      return self.render_fallback_alert(alert, threshold.currency)
  ```

- **[P2-08]** `connection_sync_service.py` double-commit risk — `connection_sync_service.py:226-239` — `_batch_insert_extracted_rates` calls `_db.execute` without committing; the caller at line 239 then calls `await self._db.commit()`. However, `_persist_sync_result` at line 233 calls `_db.execute` as well (a separate UPDATE) also without committing. This is correct by intent: everything is committed once at line 239. But `_persist_sync_result` is also called at lines 125-132 and 163-168 for early-exit error paths — in those paths there is no subsequent commit at line 239 (the function returns early). This means the UPDATE to `user_connections.last_sync_error` in error paths is never committed.

  **Impact**: On connection fetch failure, decrypt failure, or meter fetch failure, the sync error state (`last_sync_error`, `status='error'`) is written to the session but never committed to the database. The connection's UI status will appear stale (still `active` or last committed value).

  **Fix**: Add `await self._db.commit()` after each early-exit `_persist_sync_result` call in the error branches (lines 125-132, 146-155, 163-168, 177-185).

---

#### P3 — Low

- **[P3-01]** `connection_sync_service.py` dead method `_insert_extracted_rate` — `connection_sync_service.py:443-450` — `_insert_extracted_rate` simply delegates to `_batch_insert_extracted_rates` with a single-element list. It is not called anywhere in the file after `_batch_insert_extracted_rates` was introduced. It is dead code.

  **Fix**: Remove `_insert_extracted_rate` entirely, or document explicitly that it is retained as a public convenience API for callers.

- **[P3-02]** `notification_service.py` `create()` has `body: str = None` (missing `Optional`) — `notification_service.py:24` — The parameter annotation `body: str = None` is incorrect Python typing. It should be `body: Optional[str] = None`. This causes `mypy` and type checkers to flag it, and could confuse IDE tooling.

  **Fix**: Change signature to `body: Optional[str] = None` and add `from typing import Optional`.

- **[P3-03]** `alert_renderer.py` `render_fallback_alert` produces XSS-unsafe output — `alert_renderer.py:88-102` — The fallback HTML template interpolates `alert.region`, `alert.supplier`, and other fields directly into the HTML string with f-strings. If any of these fields contain `<script>` tags or other HTML, the email body would be unsafe. While email clients typically strip scripts, this is still a hygiene issue.

  **Fix**: Escape interpolated values with `html.escape()` from the standard library:
  ```python
  import html
  region = html.escape(str(alert.region))
  supplier = html.escape(str(alert.supplier))
  ```

- **[P3-04]** `data_quality_service.py` `get_source_reliability` swallows all exceptions on `scrape_results` query — `data_quality_service.py:194` — The bare `except Exception:` catches not just `UndefinedTable` (the intended case) but also transient network errors, asyncpg connection pool exhaustion, and programming bugs in the query. A transient error will silently activate the fallback path and return misleading "all healthy" results.

  **Fix**: Catch only `sqlalchemy.exc.ProgrammingError` (which wraps Postgres `UndefinedTable` / `42P01`) instead of the bare `Exception`, and re-raise all other exception types.

- **[P3-05]** `maintenance_service.py` uses `logger = structlog.get_logger()` without `__name__` — `maintenance_service.py:22` — All other services use `structlog.get_logger(__name__)`. The missing `__name__` means all log events from `MaintenanceService` will appear under the root logger name rather than `services.maintenance_service`, making log filtering/searching harder.

  **Fix**: Change to `logger = structlog.get_logger(__name__)`.

- **[P3-06]** `connection_analytics_service.py` raw f-string SQL in `get_rate_comparison` — `connection_analytics_service.py:45-56` — The `rate_region_query` is built with an f-string embedding `cid_filter` (line 53). While `cid_filter` is either an empty string or a hardcoded string literal (not user input), this pattern is fragile and trains developers to write SQL via string concatenation. If the pattern is copied carelessly with a user-supplied value, it becomes a SQL injection vector.

  **Fix**: Use a constant filter string and rely on SQLAlchemy's `text()` parameter binding exclusively. If dynamic filtering is needed, use `and_()` with conditionally appended clauses.

- **[P3-07]** `alert_service.py` `check_optimal_windows` does not filter thresholds by region — `alert_service.py:215-235` — Unlike `check_thresholds` (which groups prices by region and only matches thresholds to their region), `check_optimal_windows` notifies every threshold that opted into `notify_optimal_windows`, regardless of region. A user configured for `US_CA` will receive an optimal window alert for `US_CT` forecast data.

  **Fix**: Filter the threshold loop by region:
  ```python
  for threshold in thresholds:
      if not threshold.notify_optimal_windows:
          continue
      if threshold.region and getattr(window_start_price, "region", None) and \
         threshold.region != getattr(window_start_price, "region", None):
          continue
  ```

- **[P3-08]** `kpi_report_service.py` `weather_freshness` field name is misleading — `kpi_report_service.py:70, 90` — The CTE is named `freshness` and queries `electricity_prices.timestamp` (not weather data). The returned dict key is `weather_freshness_hours`. This is an incorrect label — the metric measures electricity price data freshness, not weather freshness.

  **Fix**: Rename to `price_data_freshness_hours` in both the CTE and the returned dict.

- **[P3-09]** `dunning_service.py` `send_dunning_email` has incorrect `amount` format guard — `dunning_service.py:210` — The `body` string uses `f"{amount:.2f}"` inside a conditional `if amount else subject`. If `amount` is `0.0` (a valid edge case for a $0.00 invoice), this evaluates the falsy branch and uses `subject` as the body, which is misleading. A zero-amount dunning scenario should still include amount context.

  **Fix**: Change the guard to `if amount is not None` to correctly handle the zero-amount case.

- **[P3-10]** `connection_sync_service.py` auth UID decryption uses `latin-1` encoding — `connection_sync_service.py:141` — `auth_uid_encrypted.encode("latin-1")` is used to convert a string to bytes for decryption. If the encrypted field ever contains non-Latin-1 characters (e.g., after a storage encoding change), this will silently corrupt the bytes rather than raise an error. `latin-1` encodes bytes 0-255 round-trip safely, which is correct for raw binary data, but this is non-obvious and should be documented.

  **Fix**: Add a comment explaining why `latin-1` is intentional for binary-safe round-trip encoding of raw encrypted bytes.

---

### Statistics

- Files audited: 11
- Total findings: 18 (P0: 1, P1: 6, P2: 8, P3: 10 — see note)

**Note**: The counts above reflect 1 P0, 6 P1, 8 P2, and 10 P3 findings as assigned above. The P3 total includes 10 items numbered P3-01 through P3-10.

| Severity | Count | Files Affected |
|----------|-------|----------------|
| P0 — Critical | 1 | dunning_service.py |
| P1 — High | 6 | dunning_service.py, data_persistence_helper.py, notification_dispatcher.py, alert_service.py, connection_sync_service.py |
| P2 — Medium | 8 | alert_service.py, alert_renderer.py, connection_analytics_service.py, connection_sync_service.py, data_quality_service.py, kpi_report_service.py, maintenance_service.py |
| P3 — Low | 10 | alert_renderer.py, alert_service.py, connection_analytics_service.py, connection_sync_service.py, data_quality_service.py, dunning_service.py, kpi_report_service.py, maintenance_service.py, notification_service.py |

### Priority Fix Order

1. **[P0-01]** Add commit after dunning failure record INSERT — prevents silent audit trail loss on email exceptions.
2. **[P1-08]** Add commits to `connection_sync_service` early-exit error branches — sync errors are never persisted to DB today.
3. **[P1-02]** Chunk `_batch_insert_extracted_rates` — prevents `TooManyParameters` crashes on large historical syncs.
4. **[P1-05]** Fix `get_overdue_accounts` DISTINCT ON / retry_count accuracy — dunning escalation decisions use wrong retry count.
5. **[P1-03]** Inspect `asyncio.gather` return values in `notification_dispatcher` — invisible push/email delivery bugs.
6. **[P1-06]** Remove hardcoded LIMIT 5000 from `get_active_alert_configs` — silent alert delivery failure at scale.
7. **[P1-04]** Add JSONB dedup index on `notifications` table — dedup query degrades to sequential scan at volume.
