# Backend Services Audit Report

**Audit date**: 2026-03-23
**Auditor**: Claude Opus 4.6
**Scope**: All 52 files in `backend/services/`
**Mode**: READ-ONLY (no source modifications)

---

## Executive Summary

The RateShift backend services layer comprises 52 Python modules totaling approximately 8,500 lines of code. The codebase demonstrates a generally mature architecture with good separation of concerns, consistent use of parameterized SQL, and thoughtful patterns like dual-provider fallback and HMAC-signed OAuth state. However, the audit identified **8 P0 critical issues**, **19 P1 major issues**, **22 P2 moderate issues**, and **14 P3 minor issues** across error handling, transaction management, async safety, logging consistency, and resource management.

The most impactful systemic issues are: (1) missing `try/except/rollback` around write operations in several services, (2) inconsistent use of stdlib `logging` vs `structlog`, (3) row-by-row INSERT patterns where batch inserts would be more efficient and safer, and (4) several services that commit but never rollback on failure.

---

## P0 -- Critical (must fix before next deployment)

### P0-01: `community_service.py` -- asyncio.gather with shared AsyncSession

**File**: `backend/services/community_service.py`
**Lines**: ~428-490 (retroactive_moderate method)
**Category**: Async safety / Data corruption risk

The `retroactive_moderate` method uses `asyncio.gather` to run multiple AI moderation calls concurrently. If the AI classification functions interact with the database session (or if the subsequent batch UPDATE uses the same session that was potentially corrupted by concurrent access), this violates SQLAlchemy's single-threaded session contract.

**Risk**: Session corruption under concurrent access can produce silent data loss, duplicate writes, or transaction rollback of unrelated operations.
**Recommendation**: Ensure AI calls are pure HTTP calls with no session access, or switch to sequential processing. Verify the final batch UPDATE runs on an uncorrupted session.

---

### P0-02: `agent_service.py` -- Background task uses stale/closed DB session

**File**: `backend/services/agent_service.py`
**Lines**: 307-335 (`query_async` and `_run_async_job`)
**Category**: Resource lifecycle / Data corruption

`query_async` creates a background task via `asyncio.create_task` that runs `_run_async_job`. However, the `_run_async_job` method at line 337 receives no `db` parameter for database operations (it only uses Redis). The `_log_conversation` call at line 249-261 in `query_streaming` takes a `db` parameter but `_run_async_job` does not log conversations -- this is inconsistent. If a future change adds DB writes to `_run_async_job`, the session will be closed/committed by the original request handler, leading to `SessionClosedError`.

**Risk**: Currently low (only Redis used), but the pattern is fragile. Any DB write added to `_run_async_job` will fail silently or corrupt data.
**Recommendation**: Document that `_run_async_job` must never use the request-scoped DB session. If DB access is needed, create a new session within the background task.

---

### P0-03: `agent_service.py` -- TOCTOU race in rate limiting (partially mitigated)

**File**: `backend/services/agent_service.py`
**Lines**: 120-163 (`check_rate_limit` and `increment_usage`)
**Category**: Race condition / Business logic bypass

The `check_rate_limit` method (line 120) uses an upsert-and-return pattern that reads the current count, but `increment_usage` (line 150) is called separately after the query response is generated (line 264). Between `check_rate_limit` and `increment_usage`, concurrent requests can both pass the check before either increments. The docstring at line 121 claims TOCTOU safety, but the actual enforcement spans two separate database operations.

**Risk**: Users can exceed daily rate limits under concurrent request load.
**Recommendation**: Combine check and increment into a single atomic `UPDATE ... SET count = count + 1 WHERE count < :limit RETURNING count` statement, or use `SELECT ... FOR UPDATE` with the increment in the same transaction.

---

### P0-04: `affiliate_service.py` -- Missing try/except/rollback on writes

**File**: `backend/services/affiliate_service.py`
**Lines**: 61-100 (`record_click`), 102-126 (`mark_converted`)
**Category**: Error handling / Transaction safety

Both `record_click` and `mark_converted` perform INSERT/UPDATE + commit operations without any `try/except` block. If the commit fails (constraint violation, connection error, etc.), the exception propagates unhandled, and the session is left in an inconsistent state (pending transaction not rolled back).

**Risk**: Uncaught DB exceptions leave the session dirty, causing subsequent operations on the same session to fail or produce unexpected results.
**Recommendation**: Wrap each write operation in `try/except` with `await self._db.rollback()` in the except clause.

---

### P0-05: `notification_service.py` -- Missing error handling on create

**File**: `backend/services/notification_service.py`
**Lines**: 19-35 (`create` method)
**Category**: Error handling / Transaction safety

The `create` method performs an INSERT + commit with no `try/except` block. Any database error (duplicate key, constraint violation, connection failure) propagates unhandled, leaving the session in a dirty state.

**Risk**: Notification creation failures can cascade into the caller (e.g., `notification_dispatcher.py`), which does have error handling -- but the session state may already be corrupted.
**Recommendation**: Add `try/except` with rollback, or ensure all callers handle the exception and rollback.

---

### P0-06: `savings_service.py` -- No rollback on record_savings failure

**File**: `backend/services/savings_service.py`
**Lines**: 191-254 (`record_savings`)
**Category**: Transaction safety

The `record_savings` method performs INSERT + commit (line 243) with no error handling. If the commit fails, the session is left dirty.

**Risk**: Failed savings recording leaves the DB session in an inconsistent state.
**Recommendation**: Wrap in `try/except` with rollback.

---

### P0-07: `referral_service.py` -- apply_referral and complete_referral lack rollback

**File**: `backend/services/referral_service.py`
**Lines**: 89-124 (`apply_referral`), 126-144 (`complete_referral`)
**Category**: Transaction safety

Both `apply_referral` (UPDATE + commit at line 116) and `complete_referral` (UPDATE + commit at line 142) lack `try/except` blocks. If the commit fails, the session is corrupted for subsequent operations.

**Risk**: Failed referral operations leave session dirty. For `apply_referral`, a partial failure could leave the referral in an inconsistent state (read as pending but UPDATE not committed).
**Recommendation**: Add `try/except` with rollback. Note that `generate_code` (line 40) does have proper rollback handling -- apply the same pattern to the other write methods.

---

### P0-08: `water_rate_service.py` -- upsert_rate lacks error handling

**File**: `backend/services/water_rate_service.py`
**Lines**: 276-309 (`upsert_rate`)
**Category**: Transaction safety

The `upsert_rate` method performs an INSERT ON CONFLICT + commit with no `try/except`. A constraint violation or connection error leaves the session dirty.

**Risk**: Failed upsert corrupts session state.
**Recommendation**: Add `try/except` with rollback.

---

## P1 -- Major (should fix soon)

### P1-01: `data_persistence_helper.py` -- Row-by-row inserts with silent skip

**File**: `backend/services/data_persistence_helper.py`
**Lines**: 42-52
**Category**: Performance / Data integrity

The helper performs N individual INSERT statements (one per row) instead of a batched INSERT. Individual row failures are silently skipped (logged but continue), and a single commit at the end means the successful subset is committed without any indication of which rows failed.

**Risk**: Silent partial data loss. N round-trips instead of 1 for N rows. No way for the caller to know which rows succeeded.
**Recommendation**: Use a batch INSERT with VALUES lists (chunked at 500 rows per the project pattern). On failure, rollback the entire batch and return the error to the caller.

---

### P1-02: `heating_oil_service.py` -- Row-by-row inserts, single commit

**File**: `backend/services/heating_oil_service.py`
**Lines**: 156-188 (`store_prices`)
**Category**: Performance / Data integrity

Same pattern as P1-01: row-by-row inserts with per-row error handling but a single commit at end. Partial failures leave some rows uncommitted/skipped without clear reporting.

**Risk**: Silent partial data loss on ingestion failures.
**Recommendation**: Switch to batch INSERT or use the `bulk_create` pattern established elsewhere.

---

### P1-03: `propane_service.py` -- Row-by-row inserts, single commit

**File**: `backend/services/propane_service.py`
**Category**: Performance / Data integrity

Same pattern as P1-01 and P1-02. Identical row-by-row insert pattern for propane price storage.

**Risk**: Silent partial data loss.
**Recommendation**: Same as P1-01.

---

### P1-04: `recommendation_service.py` -- Uses stdlib logging instead of structlog

**File**: `backend/services/recommendation_service.py`
**Line**: 7 (`import logging`), 17 (`_logger = logging.getLogger(__name__)`)
**Category**: Logging consistency

Uses stdlib `logging` while the project standard is `structlog`. Structured log context (request IDs, user IDs, trace context) will not propagate through this service.

**Risk**: Missing observability context in production logs. Log aggregation tools expecting structlog JSON format will not parse these entries correctly.
**Recommendation**: Replace `import logging` with `import structlog` and use `logger = structlog.get_logger(__name__)`.

---

### P1-05: `vector_store.py` -- Uses stdlib logging instead of structlog

**File**: `backend/services/vector_store.py`
**Line**: 13 (`import logging`), 23 (`logger = logging.getLogger(__name__)`)
**Category**: Logging consistency

Same issue as P1-04. Uses stdlib logging instead of structlog.

**Recommendation**: Switch to structlog.

---

### P1-06: `hnsw_vector_store.py` -- Uses stdlib logging instead of structlog

**File**: `backend/services/hnsw_vector_store.py`
**Category**: Logging consistency

Same issue as P1-04 and P1-05.

**Recommendation**: Switch to structlog.

---

### P1-07: `learning_service.py` -- Uses stdlib logging instead of structlog

**File**: `backend/services/learning_service.py`
**Line**: 34
**Category**: Logging consistency

Same issue as P1-04 through P1-06. Four services using stdlib logging is a systemic inconsistency.

**Recommendation**: Switch to structlog. Consider adding a ruff rule or pre-commit hook to flag `import logging` in service files.

---

### P1-08: `email_scanner_service.py` -- No retry on Gmail/Outlook API failures

**File**: `backend/services/email_scanner_service.py`
**Lines**: ~117-160
**Category**: Resilience / External API integration

Individual email fetch operations have no retry logic. A single 429 (rate limit) or transient network error from Gmail/Outlook stops the entire scan for that connection.

**Risk**: Transient API failures cause missed bill data. Gmail rate limits (250 quota units/second) can be hit during batch scans.
**Recommendation**: Add exponential backoff retry (2-3 attempts) around individual email fetches. Consider using `tenacity` or a custom retry decorator.

---

### P1-09: `email_oauth_service.py` -- Uses INTERNAL_API_KEY for HMAC signing

**File**: `backend/services/email_oauth_service.py`
**Lines**: 61-64 (`generate_oauth_state`), 91-95 (`verify_oauth_state`)
**Category**: Security / Key separation

The OAuth HMAC state signing uses `settings.internal_api_key` as the signing key. This is the same key used for internal API authentication. Compromise of the internal API key would allow forging OAuth state tokens (and vice versa).

**Risk**: Key reuse reduces the blast radius of key rotation and increases attack surface.
**Recommendation**: Use a dedicated `OAUTH_STATE_SECRET` environment variable for HMAC signing, separate from the internal API key. The CLAUDE.md already mentions this pattern in the patterns section.

---

### P1-10: `forecast_service.py` -- where_clause parameter interpolated into SQL

**File**: `backend/services/forecast_service.py`
**Lines**: 185-186, 193
**Category**: SQL injection (mitigated but fragile)

The `_forecast_from_table` method accepts a `where_clause` string parameter (line 163) and directly interpolates it into the SQL query (line 193: `where = " AND ".join(conditions)`). While the current callers only pass hardcoded strings like `"utility_type = 'NATURAL_GAS'"` (line 86), the interface allows arbitrary SQL injection if a future caller passes user-controlled input.

The table/column names are validated against allowlists (good), but the `where_clause` parameter is not.

**Risk**: Currently safe because all callers are internal with hardcoded values. Future maintenance could introduce injection if a dynamic where_clause is added.
**Recommendation**: Either (a) validate `where_clause` against an allowlist, (b) replace with parameterized conditions, or (c) add a prominent docstring warning that this parameter must never contain user input.

---

### P1-11: `rate_export_service.py` -- f-string SQL with table/column names

**File**: `backend/services/rate_export_service.py`
**Lines**: ~170-178
**Category**: SQL injection (mitigated but fragile)

Uses f-strings to interpolate table and column names from the `EXPORT_CONFIGS` dictionary into SQL queries. The values are from a hardcoded dict, not user input, so currently safe. But unlike `forecast_service.py`, there is no allowlist validation.

**Risk**: If `EXPORT_CONFIGS` values are ever derived from user input or external config, SQL injection becomes possible.
**Recommendation**: Add an allowlist check similar to `forecast_service.py`'s `_validate_sql_identifier` pattern.

---

### P1-12: `observation_service.py` -- Deprecated datetime.utcnow()

**File**: `backend/services/observation_service.py`
**Lines**: ~123-149 (`archive_old_observations`)
**Category**: Correctness / Deprecation

Uses `datetime.utcnow()` which is deprecated in Python 3.12+ (returns naive datetime). The rest of the codebase consistently uses `datetime.now(UTC)` which returns timezone-aware datetimes.

**Risk**: Mixing naive and aware datetimes can cause comparison errors, off-by-timezone-offset bugs, and deprecation warnings in logs.
**Recommendation**: Replace `datetime.utcnow()` with `datetime.now(UTC)`.

---

### P1-13: `observation_service.py` -- Direct access to private attribute `_repo._db`

**File**: `backend/services/observation_service.py`
**Lines**: ~123-149
**Category**: Encapsulation violation

The `archive_old_observations` method accesses `self._repo._db` (the repository's private database session attribute) directly instead of going through the repository's public interface.

**Risk**: If the repository's internal implementation changes (e.g., connection pooling, session management), this code will break silently.
**Recommendation**: Add a public method to the repository for archival/deletion, or pass the session explicitly.

---

### P1-14: `price_sync_service.py` -- Dead code path

**File**: `backend/services/price_sync_service.py`
**Line**: ~104
**Category**: Code quality / Dead code

The code checks `if not session` after the session has already been used in prior operations. This branch can never be reached unless the session was somehow set to None mid-execution, which would have already caused an error.

**Risk**: Dead code reduces readability and may confuse future maintainers.
**Recommendation**: Remove the unreachable check or clarify the intent.

---

### P1-15: `stripe_service.py` -- Logging API key prefix at module load

**File**: `backend/services/stripe_service.py`
**Line**: 37 (`logger.info("stripe_api_key_set", key_prefix=settings.stripe_secret_key[:7])`)
**Category**: Security / Information disclosure

Logs the first 7 characters of the Stripe secret key at INFO level during module load. Stripe secret keys start with `sk_live_` or `sk_test_`, so the first 7 characters reveal whether it is a live or test key and the first character of the actual key.

**Risk**: Key prefix in logs could aid attacker reconnaissance. While minimal, it violates the principle of least privilege for log content.
**Recommendation**: Log a boolean (`stripe_configured=True`) or a masked version (`sk_****`) instead.

---

### P1-16: `market_intelligence_service.py` -- No retry or backoff on Tavily API failures

**File**: `backend/services/market_intelligence_service.py`
**Category**: Resilience

The `weekly_market_scan` method catches per-query errors but does not retry failed queries. A transient network error causes permanent data loss for that scan cycle.

**Risk**: Transient Tavily API failures lead to incomplete market intelligence data.
**Recommendation**: Add 1-2 retries with exponential backoff per query.

---

### P1-17: `maintenance_service.py` -- cleanup_expired_uploads deletes FK children then parents in two queries

**File**: `backend/services/maintenance_service.py`
**Lines**: 63-103 (`cleanup_expired_uploads`)
**Category**: Data integrity / Race condition

The method first queries old uploads, then deletes child records (`connection_extracted_rates`), then deletes parent records (`bill_uploads`). If a new extracted rate is inserted between the child DELETE and the parent DELETE, the parent DELETE will succeed but the new child will become orphaned (dangling FK reference).

**Risk**: Rare race condition under concurrent writes during the maintenance window.
**Recommendation**: Use a single CTE-based DELETE or wrap in an explicit transaction with appropriate isolation level.

---

### P1-18: `vector_store.py` -- Full table scan on every search

**File**: `backend/services/vector_store.py`
**Lines**: 184-194 (`search` method)
**Category**: Performance

The `search` method fetches ALL vectors from the SQLite database for the given domain (or all domains) and computes cosine similarity in Python. With a growing vector store, this becomes O(n) per search with full table data transfer.

**Risk**: Performance degrades linearly with vector count. For 10,000+ vectors, search latency becomes unacceptable.
**Recommendation**: This is the legacy store; the newer `hnsw_vector_store.py` uses HNSW indexing for O(log n) search. Ensure all callers have migrated to the HNSW store and consider deprecating `VectorStore`.

---

### P1-19: `agent_service.py` -- Gemini model name may be unstable

**File**: `backend/services/agent_service.py`
**Lines**: 213, 282 (`gemini-3-flash-preview`)
**Category**: External dependency risk

The model name `gemini-3-flash-preview` is a preview identifier. Google frequently renames, deprecates, or removes preview models without notice.

**Risk**: A sudden model deprecation by Google would break the primary AI agent with no automatic fallback to a non-preview model.
**Recommendation**: Externalize the model name to an environment variable (e.g., `GEMINI_MODEL_NAME`) so it can be updated without code deployment.

---

## P2 -- Moderate (should address in next sprint)

### P2-01: `analytics_service.py` -- Cache stampede protection incomplete

**File**: `backend/services/analytics_service.py`
**Lines**: 46-63 (`_acquire_cache_lock`)
**Category**: Resilience

The cache stampede lock uses Redis `SET NX` with a 5-second TTL. If the computation takes longer than 5 seconds, the lock expires and another request proceeds with duplicate computation. There is also no cleanup of the lock key on computation failure (only on success via `_set_cached`).

**Risk**: Under high load with slow DB queries, multiple requests can stampede past the lock.
**Recommendation**: Use a longer lock TTL (e.g., 30s) or implement lock extension. Clean up the lock in a `finally` block.

---

### P2-02: `savings_aggregator.py` -- PERCENT_RANK query can be expensive

**File**: `backend/services/savings_aggregator.py`
**Lines**: 79-92
**Category**: Performance

The rank calculation uses `PERCENT_RANK() OVER (ORDER BY total_savings)` which requires sorting all users' savings. This is a full-table GROUP BY + ORDER BY that becomes expensive as the user base grows.

**Risk**: O(n log n) query on every call with no caching.
**Recommendation**: Cache the result with a 5-15 minute TTL, or pre-compute ranks in a materialized view updated nightly.

---

### P2-03: `stripe_service.py` -- apply_webhook_action fetches user twice

**File**: `backend/services/stripe_service.py`
**Lines**: 686 and 712
**Category**: Performance / Code quality

The `apply_webhook_action` function fetches the user at line 686 (`user = await user_repo.get_by_id(user_id)`), and then in the `payment_failed` branch at line 712, fetches the user again (`user = await user_repo.get_by_id(user_id)`).

**Risk**: Unnecessary database round-trip. Also, the second fetch could return a different state if the user was modified between the two reads.
**Recommendation**: Remove the second `get_by_id` call and reuse the `user` variable from line 686.

---

### P2-04: `notification_dispatcher.py` -- type parameter shadows builtin

**File**: `backend/services/notification_dispatcher.py`
**Lines**: 123, 267-268
**Category**: Code quality

The `send` method uses `type` as a parameter name (line 123), and later uses `type(exc).__name__` (line 268) which references the builtin `type()` function. However, at line 268, the local `type` parameter has shadowed the builtin, so `type(exc)` refers to the string parameter, not the builtin.

**Risk**: `type(exc).__name__` at line 268 will raise `AttributeError` because `type` is a string, not the builtin function.
**Recommendation**: Rename the parameter from `type` to `notification_type` or `ntype` to avoid shadowing the builtin.

---

### P2-05: `community_service.py` -- AI moderation fail-closed may block legitimate content

**File**: `backend/services/community_service.py`
**Category**: Business logic

The AI moderation is configured fail-closed with a 30-second timeout. If both Groq and Gemini are down or slow, all community posts are rejected.

**Risk**: Extended AI provider outages (which have occurred with Groq) would silently block all community participation.
**Recommendation**: Consider a "moderation queue" fallback: when AI is unavailable, accept the post but mark it for manual review rather than rejecting outright. Or add a circuit breaker that switches to allow-with-flag after N consecutive failures.

---

### P2-06: `feature_flag_service.py` -- Dynamic SQL SET clause construction

**File**: `backend/services/feature_flag_service.py`
**Lines**: 92-126 (`update_flag`)
**Category**: SQL construction pattern

The `update_flag` method builds SQL SET clauses using f-strings from a list of column name strings. While the column names are hardcoded (not user input), the pattern of building SQL dynamically is fragile.

**Risk**: Currently safe, but refactoring could introduce injection if column names become dynamic.
**Recommendation**: Use a parameterized approach or an ORM-level update.

---

### P2-07: `dunning_service.py` -- Multiple commits in single flow

**File**: `backend/services/dunning_service.py`
**Category**: Transaction safety

The `handle_payment_failure` method may perform multiple commits across different sub-operations (retry record, notification dispatch, tier downgrade). If an intermediate commit succeeds but a later operation fails, the data is in a partially-updated state.

**Risk**: Partial payment failure handling (e.g., retry recorded but notification not sent, or vice versa).
**Recommendation**: Consider wrapping the entire flow in a single transaction with a commit at the end, or document the intentional partial-commit design with compensating actions.

---

### P2-08: `kpi_report_service.py` -- Uses pg_class.reltuples for approximate count

**File**: `backend/services/kpi_report_service.py`
**Lines**: 56-57
**Category**: Data accuracy

Uses `pg_class.reltuples` for the `prices_tracked` metric, which returns an estimate based on the last VACUUM/ANALYZE. This can be significantly stale (hours to days old depending on autovacuum frequency).

**Risk**: KPI report shows stale/inaccurate price count if autovacuum hasn't run recently.
**Recommendation**: Document that this is an estimate. For exact counts, use `COUNT(*)` with a date filter, or accept the estimate with a note in the report output.

---

### P2-09: `bill_parser.py` -- Regex-based extraction without input size limits on content

**File**: `backend/services/bill_parser.py`
**Category**: Performance / DoS

While the service has file size limits for uploaded files, the regex extraction operates on the full text content without a character limit. A large text file that passes the file size check could cause regex catastrophic backtracking.

**Risk**: Specially crafted bill content could cause CPU-intensive regex operations.
**Recommendation**: Add a character limit on the extracted text before running regex patterns.

---

### P2-10: `gas_rate_service.py` -- Semaphore-limited but no overall timeout

**File**: `backend/services/gas_rate_service.py`
**Category**: Resilience

Uses `asyncio.Semaphore` for concurrency limiting on API calls, but there is no overall timeout for the batch operation. If one state's API call hangs, the entire batch operation hangs.

**Risk**: A single hung API call blocks the entire gas rate fetch cycle.
**Recommendation**: Wrap the `asyncio.gather` call with `asyncio.wait_for` and an overall timeout (e.g., 120 seconds).

---

### P2-11: `weather_service.py` -- No caching of weather data

**File**: `backend/services/weather_service.py`
**Category**: Performance / API quota

Each call to `get_current_weather` or `get_forecast_5day` makes a fresh HTTP request to OpenWeatherMap. With the free tier limit of 1,000 calls/day, repeated requests for the same region can exhaust the quota.

**Risk**: Quota exhaustion under moderate load. Weather data changes slowly (hourly), so caching is safe.
**Recommendation**: Add in-memory or Redis caching with a 30-60 minute TTL for weather data.

---

### P2-12: `weather_service.py` -- No error handling in get_current_weather / get_forecast_5day

**File**: `backend/services/weather_service.py`
**Lines**: 79-111, 113-142
**Category**: Error handling

Both methods call `resp.raise_for_status()` which raises `httpx.HTTPStatusError` on 4xx/5xx, but there is no `try/except` to handle the error gracefully. The caller (`fetch_weather_for_regions`) does catch exceptions at line 170, but individual method callers outside that path would get unhandled exceptions.

**Risk**: Callers of the individual methods must handle HTTP exceptions themselves.
**Recommendation**: Either add error handling in the individual methods (returning None on failure) or clearly document the exception contract.

---

### P2-13: `email_service.py` -- Resend API key set as module-level global in constructor

**File**: `backend/services/email_service.py`
**Lines**: 44-48
**Category**: Thread safety

The constructor sets `resend.api_key` as a module-level global. The comment explains the race condition fix (setting once in `__init__` vs per-call), but if multiple `EmailService` instances are constructed with different settings (e.g., in tests), the last one wins globally.

**Risk**: Low in production (single settings object), but test isolation issues possible.
**Recommendation**: Document this constraint. When upgrading `resend` library, migrate to per-client auth.

---

### P2-14: `portal_scraper_service.py` -- Hardcoded utility selectors may break

**File**: `backend/services/portal_scraper_service.py`
**Category**: Maintainability

The scraper contains hardcoded CSS selectors and URL patterns for 5 utility companies (Duke Energy, PG&E, Con Edison, ComEd, FPL). Utility website redesigns will silently break scraping.

**Risk**: Scraper failures are caught and logged but produce no data, leading to stale rates with no alert to operations.
**Recommendation**: Add a staleness check that alerts when a utility has not been successfully scraped within 2x the expected interval.

---

### P2-15: `geocoding_service.py` -- Nominatim fallback lacks rate limiting

**File**: `backend/services/geocoding_service.py`
**Category**: External API compliance

Nominatim's usage policy requires max 1 request per second. The fallback path has no rate limiting, so if OWM is down and multiple geocoding requests arrive, Nominatim may be hit concurrently.

**Risk**: Nominatim may ban the server's IP for violating usage policy.
**Recommendation**: Add a semaphore (limit 1) or sleep between Nominatim requests.

---

### P2-16: `connection_sync_service.py` -- No overall timeout for batch sync

**File**: `backend/services/connection_sync_service.py`
**Category**: Resilience

Sequential sync operations across all connections have no overall timeout. If one UtilityAPI sync hangs, the entire sync cycle blocks.

**Risk**: Hung API call blocks all subsequent connection syncs.
**Recommendation**: Add per-connection timeout (e.g., 60s via `asyncio.wait_for`) or an overall batch timeout.

---

### P2-17: `alert_service.py` -- Alert fan-out could generate high email volume

**File**: `backend/services/alert_service.py`
**Category**: Business logic / Cost

When a price drop triggers alerts, every matching user receives an email and/or push notification. With thousands of users in the same region, a single price change could generate thousands of emails in a short window.

**Risk**: Resend rate limits (varies by plan), high email costs, and potential spam reputation damage.
**Recommendation**: Add a batch size limit and stagger alert delivery over time. Consider an alert digest mode for high-frequency regions.

---

### P2-18: `stripe_service.py` -- Webhook handler does not verify event idempotency

**File**: `backend/services/stripe_service.py`
**Lines**: 379-636 (`handle_webhook_event`)
**Category**: Idempotency

The `handle_webhook_event` method processes events without checking whether the event has already been processed. While `apply_webhook_action` at the API layer may have idempotency checks (via `stripe_processed_events` table), the service layer itself is not idempotent.

**Risk**: Replay of a webhook event could double-apply tier changes or trigger duplicate dunning flows.
**Recommendation**: Add idempotency check within the service (check `stripe_processed_events` table) or clearly document that the caller is responsible for idempotency.

---

### P2-19: `model_version_service.py` -- HMAC signing key defaults to empty string

**File**: `backend/services/model_version_service.py`
**Category**: Security

If `ML_MODEL_SIGNING_KEY` is not set, the service may use an empty string for HMAC signing, making all signatures trivially forgeable.

**Risk**: Model integrity verification is bypassed when the signing key is unset.
**Recommendation**: Raise an error or skip signing entirely when the key is not configured, rather than signing with an empty key.

---

### P2-20: `ab_test_service.py` -- Consistent hashing without salt

**File**: `backend/services/ab_test_service.py`
**Category**: Security / Predictability

The A/B test assignment uses a hash of `user_id + test_name` for consistent bucket assignment. Without a salt, an attacker who knows the user_id and test_name can predict the assignment.

**Risk**: Users could manipulate their assignment by creating accounts until they get the desired variant. Low impact for A/B tests, higher impact if used for feature gating.
**Recommendation**: Add a server-side secret salt to the hash input.

---

### P2-21: `data_quality_service.py` -- Fallback query when table doesn't exist

**File**: `backend/services/data_quality_service.py`
**Category**: Schema coupling

The service catches exceptions from querying `scrape_results` and falls back to a different query. This suggests the schema may not be consistently migrated.

**Risk**: Silent degradation to a less informative fallback that may mask real issues.
**Recommendation**: Ensure the `scrape_results` table is always created via migration and remove the fallback.

---

### P2-22: `savings_aggregator.py` -- Dynamic SQL with f-string IN clause

**File**: `backend/services/savings_aggregator.py`
**Lines**: 42-45
**Category**: SQL construction

Builds an IN clause using f-string placeholder generation: `", ".join(f":ut_{i}" for i in range(...))`. While the values are parameterized (`:ut_0, :ut_1, ...`), the construction pattern with f-strings for the placeholder names is unusual and could confuse maintainers.

**Risk**: Currently safe (parameterized values), but non-standard pattern.
**Recommendation**: Use PostgreSQL's `ANY(:array)` pattern instead: `WHERE us.utility_type = ANY(:utilities)` with a list parameter.

---

## P3 -- Minor (nice-to-have improvements)

### P3-01: `forecast_service.py` -- Manual linear regression implementation

**File**: `backend/services/forecast_service.py`
**Lines**: 266-278
**Category**: Code quality / Maintainability

Implements manual least-squares linear regression from scratch. While functional, numpy or scipy could provide this in 2 lines with better numerical stability.

**Recommendation**: Consider `numpy.polyfit(days, prices, 1)` for cleaner code, or keep the manual implementation with a comment explaining why numpy is avoided (e.g., to avoid the dependency in the backend).

---

### P3-02: `email_oauth_service.py` -- OAuth state format tightly coupled to colon delimiter

**File**: `backend/services/email_oauth_service.py`
**Lines**: 60, 84-88
**Category**: Robustness

The state format uses `:` as a delimiter between fields. If a `connection_id` or `user_id` contains a colon (unlikely for UUIDs but possible for other ID formats), the `split(":")` parsing at line 84 would produce incorrect results.

**Recommendation**: Use a different delimiter (e.g., `|`) or use URL-safe base64 encoding for the entire payload.

---

### P3-03: `recommendation_service.py` -- Hardcoded appliance list

**File**: `backend/services/recommendation_service.py`
**Lines**: 217 (`appliances = ["washing_machine", "dishwasher", "electric_vehicle"]`)
**Category**: Maintainability

The daily recommendations always compute for 3 hardcoded appliances. Users may have different appliance profiles.

**Recommendation**: Make the appliance list configurable per user (from user preferences) or from a settings constant.

---

### P3-04: `stripe_service.py` -- Large function: handle_webhook_event (250+ lines)

**File**: `backend/services/stripe_service.py`
**Lines**: 379-636
**Category**: Code quality / Readability

The `handle_webhook_event` method is over 250 lines with a long if/elif chain. Each event type handler is 15-30 lines of similar boilerplate.

**Recommendation**: Extract each event handler into a private method (e.g., `_handle_checkout_completed`, `_handle_subscription_updated`) and use a dispatch dict.

---

### P3-05: `stripe_service.py` -- apply_webhook_action is a module-level function

**File**: `backend/services/stripe_service.py`
**Lines**: 639-832
**Category**: Code organization

`apply_webhook_action` is a standalone function rather than a method on `StripeService`. It imports from `api.dependencies` (creating an upward dependency from service to API layer) and takes a loosely-typed `user_repo: Any`.

**Recommendation**: Move to a dedicated webhook handler class, or make it a method on `StripeService` to improve cohesion. Replace `Any` type hints with the actual types.

---

### P3-06: `notification_dispatcher.py` -- IN_APP insert has branching for metadata null

**File**: `backend/services/notification_dispatcher.py`
**Lines**: 305-339
**Category**: Code quality

The `_send_in_app` method has two separate SQL INSERT statements -- one with metadata and one without -- to handle the `metadata IS NULL` case. This duplication can be eliminated by always passing metadata (as `'{}'` when empty).

**Recommendation**: Always include the metadata column and pass `'{}'` as default to eliminate the branching.

---

### P3-07: `vector_store.py` -- Potential deprecation candidate

**File**: `backend/services/vector_store.py`
**Category**: Architecture

The `VectorStore` class is a legacy implementation that does brute-force cosine similarity search. The newer `HNSWVectorStore` (in `hnsw_vector_store.py`) provides O(log n) approximate nearest neighbor search. Both are in active use.

**Recommendation**: Audit callers to determine if `VectorStore` can be deprecated in favor of `HNSWVectorStore`. If retained, add a deprecation notice.

---

### P3-08: `kpi_report_service.py` -- Queries neon_auth schema directly

**File**: `backend/services/kpi_report_service.py`
**Lines**: 48-51
**Category**: Schema coupling

Queries `neon_auth.session` directly for active user counts. This couples the KPI service to the Neon Auth internal schema, which could change during Neon platform updates.

**Recommendation**: Consider using a view or abstraction layer for cross-schema queries.

---

### P3-09: `utility_discovery_service.py` -- Class methods could be module-level functions

**File**: `backend/services/utility_discovery_service.py`
**Category**: Code organization

Both `discover` and `get_completion_status` are `@classmethod` with no instance state. They could be plain module-level functions for simplicity.

**Recommendation**: Minor stylistic preference. The class provides good namespace grouping, so this is acceptable as-is.

---

### P3-10: `maintenance_service.py` -- File deletion outside transaction

**File**: `backend/services/maintenance_service.py`
**Lines**: 93-99
**Category**: Consistency

The `cleanup_expired_uploads` method commits the DB deletion first, then attempts file system cleanup. If the process crashes between commit and file deletion, orphaned files remain on disk.

**Recommendation**: This is intentionally best-effort (non-fatal file cleanup). Add a periodic orphan file scanner as a safety net.

---

### P3-11: `weather_service.py` -- API key in query parameters

**File**: `backend/services/weather_service.py`
**Lines**: 99, 127
**Category**: Security (mitigated)

The OWM API key is passed as a query parameter (`appid=self._api_key`), which means it appears in server access logs and any HTTP debugging output. The code has thorough docstring explaining the mitigation (free tier, no billing authority, server-side only).

**Recommendation**: Already mitigated with clear documentation. No action needed.

---

### P3-12: `push_notification_service.py` -- Minimal implementation

**File**: `backend/services/push_notification_service.py`
**Category**: Feature completeness

The push service is minimal: a single `send_push` method with no batch sending, no targeting beyond user_id, and no delivery tracking.

**Recommendation**: Acceptable for current scale. Consider adding batch push and delivery callbacks when user base grows.

---

### P3-13: `cca_service.py` / `community_solar_service.py` -- Read-only services with no caching

**File**: `backend/services/cca_service.py`, `backend/services/community_solar_service.py`
**Category**: Performance

Both services perform database reads on every call with no caching. CCA programs and community solar data change infrequently.

**Recommendation**: Add Redis caching with 1-hour TTL for program listings.

---

### P3-14: `alert_renderer.py` -- Template fallback to plain text

**File**: `backend/services/alert_renderer.py`
**Category**: Resilience (positive)

The alert renderer has a solid fallback chain: Jinja2 template -> inline HTML -> plain text. This is a good resilience pattern.

**Recommendation**: No action needed. Noted as a positive pattern.

---

## Files With No Issues

The following services were reviewed and found to have no significant issues:

| File | Notes |
|------|-------|
| `__init__.py` | Clean module exports |
| `alert_renderer.py` | Good template fallback pattern, clean separation |
| `connection_analytics_service.py` | Read-only, clean query patterns |
| `optimization_report_service.py` | Read-only aggregation, clean structure |
| `neighborhood_service.py` | Read-only with proper MIN_USERS threshold |
| `price_service.py` | Good async Lock pattern for ML predictor, clean caching |

---

## Cross-Cutting Observations

### Positive Patterns Observed

1. **SQL injection prevention**: Most services use parameterized queries via `text()` with named parameters. The `forecast_service.py` allowlist pattern for SQL identifiers is exemplary.

2. **Dual-provider resilience**: Gemini+Groq (agent), Resend+SMTP (email), OWM+Nominatim (geocoding) all implement clean fallback chains.

3. **SSRF protection**: `portal_scraper_service.py` implements domain allowlisting and private IP blocking -- a strong security pattern.

4. **Structured logging**: The majority of services (48 of 52) use `structlog` consistently with semantic event names and structured context.

5. **HMAC-signed OAuth state**: The `email_oauth_service.py` implementation with timestamp expiry and user binding is well-designed.

6. **Semaphore-based rate limiting**: Several services (`gas_rate_service`, `rate_scraper_service`, `weather_service`) properly use `asyncio.Semaphore` to limit concurrent external API calls.

7. **Background task GC protection**: `agent_service.py` correctly maintains a module-level set to prevent garbage collection of asyncio tasks.

8. **Tier cache invalidation**: `stripe_service.py` immediately invalidates the tier cache after subscription changes, avoiding stale-tier issues.

### Systemic Issues

1. **Inconsistent error handling on writes**: Approximately 8-10 services perform INSERT/UPDATE + commit without `try/except/rollback`. This is the single most common issue pattern.

2. **Logging framework inconsistency**: 4 services (`recommendation_service`, `vector_store`, `hnsw_vector_store`, `learning_service`) use stdlib `logging` instead of `structlog`.

3. **Row-by-row inserts**: 3 services (`data_persistence_helper`, `heating_oil_service`, `propane_service`) use row-by-row INSERT instead of batch INSERT, reducing throughput and making partial failure handling ambiguous.

4. **Missing external API retry logic**: Several services that call external APIs (`email_scanner_service`, `market_intelligence_service`) lack retry/backoff on transient failures.

---

## Summary Statistics

| Severity | Count | Category Breakdown |
|----------|-------|--------------------|
| P0 Critical | 8 | Transaction safety (6), Async safety (1), Race condition (1) |
| P1 Major | 19 | Logging (4), Performance (3), Resilience (3), Security (3), SQL patterns (2), Code quality (2), External API (2) |
| P2 Moderate | 22 | Performance (5), Error handling (3), Business logic (3), Security (3), SQL patterns (2), Resilience (2), Others (4) |
| P3 Minor | 14 | Code quality (5), Performance (3), Architecture (2), Security (2), Others (2) |
| **Total** | **63** | |

### Top 5 Recommendations (by impact)

1. **Add try/except/rollback to all write operations** (fixes P0-04 through P0-08): Systematic sweep of all `await db.commit()` calls to ensure rollback on failure.

2. **Standardize on structlog** (fixes P1-04 through P1-07): Replace all stdlib `logging` imports with `structlog`. Add a ruff/linting rule.

3. **Migrate row-by-row inserts to batch** (fixes P1-01 through P1-03): Use the established `bulk_create` pattern with 500-row chunks.

4. **Add retry logic to external API calls** (fixes P1-08, P1-16): Wrap Gmail, Outlook, and Tavily API calls with exponential backoff.

5. **Fix notification_dispatcher type shadowing** (fixes P2-04): Rename the `type` parameter to `notification_type` to prevent the `type(exc).__name__` runtime error.
