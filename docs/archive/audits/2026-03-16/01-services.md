# Backend Services Audit — 2026-03-16

**Scope**: All `.py` files in `backend/services/` (52 files)
**Auditor**: Claude Code (claude-sonnet-4-6)

---

## Summary Counts

| Severity | Count |
|----------|-------|
| P0 — Critical (bugs / security) | 8 |
| P1 — High (performance / design flaws) | 14 |
| P2 — Medium (correctness risks, missing validation) | 17 |
| P3 — Low (style, maintainability, minor gaps) | 12 |
| **Total** | **51** |

---

## P0 — Critical

### P0-01 · SQL injection via f-string interpolation in `alert_service.py`

**File**: `backend/services/alert_service.py`
**Lines**: 461–479 (`_batch_should_send_alerts`)

The batch deduplication query constructs a `VALUES` clause by interpolating
parameter names like `:uid_0`, `:atype_0`, `:reg_0` into a raw f-string that
is then passed to `sqlalchemy.text()`. Although the *values themselves* go
through bind parameters, the *structure* of the SQL (number of VALUE tuples)
is controlled by caller-supplied data length.

More critically, the column names `user_id`, `alert_type`, `region` inside the
`VALUES (...) AS q(user_id, alert_type, region)` clause are literal SQL
identifiers that are concatenated at lines 464–466 without any sanitization.
If this method were ever called with attacker-influenced column aliases (e.g.,
via a deserialization path), the query structure would be exploitable.

The more immediate, practical risk is that a large `triggered_pairs` list
causes unbounded query growth: 10,000 triggered alerts → 10,000-value `VALUES`
clause, which can exhaust connection buffer limits and cause denial of service.

**Suggested fix**: Batch in chunks of at most 500 tuples; cap the input or add
an assertion. The column names inside the VALUES alias are constant here and
not user-supplied, so this is a DoS risk rather than a direct injection risk,
but the pattern is fragile.

```python
BATCH_SIZE = 500
for chunk in [tuples[i:i+BATCH_SIZE] for i in range(0, len(tuples), BATCH_SIZE)]:
    # build and execute per chunk
```

---

### P0-02 · SQL injection via f-string in `forecast_service.py`

**File**: `backend/services/forecast_service.py`
**Lines**: 109–135 (`_forecast_electricity`) and 148–186 (`_forecast_from_table`)

`_forecast_electricity` builds the query using an f-string that directly
interpolates `TREND_LOOKBACK_DAYS` (a module constant, safe for now) and the
`region_filter` string (line 109–125). However `_forecast_from_table` is more
dangerous: it assembles `where_clause`, `state_col`, `table`, `price_col`, and
`time_col` (all caller-supplied strings) directly into an f-string that is
handed to `sqlalchemy.text()`:

```python
result = await self.db.execute(
    text(f"""
        SELECT {price_col}, {time_col}
        FROM {table}
        WHERE {where}
        ORDER BY {time_col} ASC
    """),
    params,
)
```

The `table`, `price_col`, `time_col`, and `where_clause` arguments are passed
in by `get_forecast()` as literal Python strings — they are NOT bound
parameters. Any path that could influence these values (e.g., a future
refactor that reads utility_type from user input without whitelisting) would
be a full SQL injection. Even today, `state_col` and `state_prefix` are
internal strings, but the pattern is unsafe and violates the project's own
convention of "all queries use parameterised text() statements."

**Suggested fix**: Use a whitelist dict mapping utility_type to a `(table,
price_col, time_col)` tuple; assert membership before using the values. Do
NOT interpolate table or column names from variables — SQLAlchemy's
`sqlalchemy.sql.expression.literal_column()` can be used for trusted column
names when truly needed.

```python
_TABLE_REGISTRY = {
    "heating_oil":  ("heating_oil_prices",  "price_per_gallon", "fetched_at"),
    "propane":      ("propane_prices",       "price_per_gallon", "fetched_at"),
    "natural_gas":  ("electricity_prices",   "price_per_kwh",    "timestamp"),
}
```

---

### P0-03 · f-string SQL assembly in `savings_service.py`

**File**: `backend/services/savings_service.py`
**Lines**: 67–103 (`get_savings_summary`)

`region_clause` is assembled as an f-string that is embedded in the `text()`
query. The `region` value is properly bound as `:region`, but the conditional
clause string is interpolated directly into the SQL text at lines 61–62 and
81–82:

```python
if region:
    region_clause = " AND region = :region"
    base_params["region"] = region

combined_sql = text(f"""
    ...
    WHERE user_id = :user_id
    {region_clause}   # <-- direct interpolation
    ...
""")
```

This is safe today because `region_clause` is either empty or a fixed string
`" AND region = :region"`. But using an f-string with `text()` is fragile:
any future developer who changes `region_clause` to include the region value
rather than a bind name would introduce injection. The identical pattern
appears in `savings_aggregator.py` line 47–57 with a more dangerous variant
that also interpolates `utility_filter`:

```python
savings_sql = text(f"""
    ...
    {utility_filter}   # user-controlled filter clause
""")
```

In `savings_aggregator.py` the `utility_filter` string contains only bind
parameter names (`:ut_0`, `:ut_1`, ...) assembled from a counter — so the
actual risk is low today, but the pattern is an anti-pattern and one refactor
away from injection.

**Suggested fix**: Use SQLAlchemy `and_()` / `or_()` / `bindparam()` with the
ORM expression layer, or use conditional WHERE building with proven libraries.
If staying with raw SQL, keep a single static SQL template with optional
clauses pre-written and a boolean flag to switch them on/off.

---

### P0-04 · TOCTOU race in `referral_service.apply_referral`

**File**: `backend/services/referral_service.py`
**Lines**: 90–117 (`apply_referral`)

The method performs a read-check-write pattern that is vulnerable to a
time-of-check / time-of-use race condition:

1. Line 96: `referral = await self.get_referral_by_code(code)` — reads the row
2. Lines 101–108: checks `status`, `referee_id`, and self-referral
3. Lines 110–116: `UPDATE referrals SET referee_id = :referee_id WHERE id = :id AND status = 'pending'`

Two concurrent requests with the same referral code can both pass step 2 before
either executes step 3. The UPDATE does have `AND status = 'pending'` as a
guard, but `referee_id` can be set by two concurrent transactions since the
initial check and the write are not atomic. One transaction will commit
successfully and the other will also succeed but overwrite the `referee_id`
with a different user (since the UPDATE has no `referee_id IS NULL` guard).

**Suggested fix**: Perform the claim atomically using a single `UPDATE ... WHERE
id = :id AND status = 'pending' AND referee_id IS NULL RETURNING id`:

```python
result = await self._db.execute(
    text("""
        UPDATE referrals
        SET referee_id = :referee_id
        WHERE id = :id
          AND status = 'pending'
          AND referee_id IS NULL
          AND referrer_id != :referee_id
        RETURNING id, referrer_id, referral_code
    """),
    {"referee_id": referee_id, "id": referral["id"]},
)
row = result.mappings().first()
if not row:
    raise ReferralError("Referral code already claimed or self-referral attempted")
```

---

### P0-05 · `asyncio.create_task` without lifecycle management in `agent_service.py`

**File**: `backend/services/agent_service.py`
**Lines**: 307 (`query_async`)

```python
asyncio.create_task(self._run_async_job(job_id, user_id, prompt, context, redis))
```

This is a classic "fire-and-forget" anti-pattern. The task is created but
never stored or awaited. If the event loop shuts down (e.g., during a graceful
Render restart or test teardown), the task is silently cancelled mid-execution,
which means:

1. The Redis key remains in `{"status": "processing"}` forever (no expiry
   update sets it to "failed").
2. If the task holds a database session reference (via a future refactor), the
   session would not be closed.
3. Unit tests that mock this path will get intermittent failures because the
   task runs after the test asserts.

Python 3.12+ emits a `ResourceWarning` for unawaited tasks. If the exception
in `_run_async_job` is not caught (e.g., a Redis connection error before the
`try` block), the exception is silently swallowed.

**Suggested fix**: Store the task reference and register a done-callback for
error logging; or use a proper background task queue (Celery, arq, FastAPI
`BackgroundTasks`).

```python
task = asyncio.create_task(self._run_async_job(job_id, user_id, prompt, context, redis))
task.add_done_callback(
    lambda t: logger.error("async_job_task_error", exc_info=t.exception())
    if t.exception() else None
)
```

---

### P0-06 · Unsafe `auth_uid_encrypted` decoding may silently corrupt data in `connection_sync_service.py`

**File**: `backend/services/connection_sync_service.py`
**Lines**: 137–143 (`sync_connection`)

```python
if isinstance(auth_uid_encrypted, memoryview):
    auth_uid_encrypted = bytes(auth_uid_encrypted)
elif isinstance(auth_uid_encrypted, str):
    auth_uid_encrypted = auth_uid_encrypted.encode("latin-1")
```

The AES-256-GCM ciphertext stored in the database is binary data. If it is
returned as a `str` by the DB driver (which can happen with `asyncpg` for
`bytea` columns when the connection encoding is misconfigured), converting it
with `latin-1` encoding will silently corrupt bytes that fall in the range
128–255. The resulting ciphertext will be invalid, causing `decrypt_field` to
raise a `ValueError` or, worse, to decrypt to garbled plaintext. The corrupted
value would then be used as the `authorization_uid` for an API call.

There is no test that covers the `str` branch.

**Suggested fix**: Store encrypted credentials as hexadecimal text or use
`asyncpg`'s native `bytea` type with a proper codec. Remove the `str` branch
or add a strict check: `raise ValueError("Expected bytes for encrypted field,
got str")`.

---

### P0-07 · Moderation timeout clears `is_pending_moderation` on *any* exception, not just timeouts

**File**: `backend/services/community_service.py`
**Lines**: 99–112 (`create_post`) and 537–544 (`edit_and_resubmit`)

```python
except (asyncio.TimeoutError, Exception) as exc:
    logger.warning(...)
    await self._clear_pending_moderation(db, post_id)
```

The comment says "Timeout: auto-clear pending moderation so post becomes
visible," but because `Exception` is listed alongside `asyncio.TimeoutError`,
*any* exception — including a database error, a `KeyError` in the classification
result, or a network failure — causes the post to be immediately published
without moderation. This means a bug in the AI service or a transient error
causes the fail-closed mechanism to fail open.

The intent of the fail-closed design (stated in the module docstring: "Fail-
closed moderation: posts start as is_pending_moderation=true") is violated.

**Suggested fix**: Separate timeout from unexpected errors:

```python
except asyncio.TimeoutError:
    logger.warning("moderation_timeout", post_id=str(post_id))
    await self._clear_pending_moderation(db, post_id)
except Exception as exc:
    logger.error("moderation_unexpected_error", post_id=str(post_id), error=str(exc))
    # Leave is_pending_moderation=True on unexpected errors (fail-closed)
    # A background job (retroactive_moderate) will re-check these posts
```

---

### P0-08 · Missing `await db.commit()` before moderation writes on a committed session

**File**: `backend/services/community_service.py`
**Lines**: 93–112

The `create_post` method commits the INSERT at line 95 (`await db.commit()`)
and then immediately passes the same `db` session to `_run_moderation()` (line
101). Inside `_run_moderation()`, the method performs UPDATE statements and
calls `await db.commit()` again (lines 169–170).

While this works in SQLAlchemy's autocommit mode, there is a subtle problem:
`_run_moderation` is called within `asyncio.wait_for(...)` which shares the
same session object. If the moderation task times out, the session may have a
pending UPDATE (or even a partially-executed UPDATE that raised mid-flight)
in an incomplete transaction state when `_clear_pending_moderation` is called.
This leads to a `sqlalchemy.exc.InvalidRequestError: Can't operate on a closed
transaction` or similar depending on timing.

**Suggested fix**: Open a new database session for the moderation step, or
use a `SAVEPOINT` for the moderation transaction so it can be rolled back
independently of the INSERT transaction.

---

## P1 — High

### P1-01 · No input validation on `user_id` before using as a SQL parameter across all services

**Files**: Multiple — `alert_service.py`, `agent_service.py`, `dunning_service.py`, `referral_service.py`, `savings_service.py`, and others.

Every service accepts `user_id: str` and passes it directly to `sqlalchemy.text()` bind parameters. There is no validation that the value is a well-formed UUID. SQLAlchemy's bind parameters prevent injection, but passing a 10MB string as `user_id` would cause Postgres to try to cast it to UUID and raise a DB exception that bubbles up as an unhandled 500 rather than a clean 422.

More importantly, if `user_id` comes from a JWT claim and the JWT validation is bypassed (e.g., in tests or misconfigured middleware), there is no service-layer defense.

**Suggested fix**: Add a UUID validation helper called at the top of service methods that accept user IDs:

```python
import uuid
def _validate_uuid(value: str, field: str = "id") -> str:
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        raise ValueError(f"Invalid {field}: must be a valid UUID")
```

---

### P1-02 · Unbounded `retroactive_moderate` can process all posts in 24 hours without pagination

**File**: `backend/services/community_service.py`
**Lines**: 440–449 (`retroactive_moderate`)

```python
select_sql = text("""
    SELECT id, title, body FROM community_posts
    WHERE is_pending_moderation = false
      AND is_hidden = false
      AND hidden_reason IS NULL
      AND created_at >= NOW() - INTERVAL '24 hours'
    ORDER BY created_at ASC
""")
result = await db.execute(select_sql)
posts = result.mappings().fetchall()
```

There is no LIMIT on this query. If there are 50,000 posts created in a 24-
hour window (e.g., after a spam event), this fetches all 50,000 rows into
memory before starting the Semaphore-limited AI classification. Even with 5
concurrent workers, classifying 50,000 posts exhausts the Groq rate limit
quickly and ties up the endpoint for hours.

**Suggested fix**: Add `LIMIT 1000` or pagination, and run this as a
background job with progress tracking.

---

### P1-03 · `check_rate_limit` has a TOCTOU race condition

**File**: `backend/services/agent_service.py`
**Lines**: 110–134 (`check_rate_limit`)

The method does:
1. `INSERT ... ON CONFLICT DO NOTHING` to ensure the row exists (line 119)
2. A separate `SELECT query_count` (line 129)
3. Returns `current_count < limit`

Then the caller increments usage in a separate call (`increment_usage`). The
sequence INSERT → SELECT → compare → return → (caller) UPDATE is not atomic.
Two concurrent requests for the same user can both read `current_count = 2`
when the limit is `3`, both pass the check, and both increment to `3` and `4`.
This allows users to exceed their daily limit by the number of concurrent
requests.

**Suggested fix**: Use a single atomic query:

```python
result = await db.execute(text("""
    INSERT INTO agent_usage_daily (user_id, date, query_count)
    VALUES (:user_id, CURRENT_DATE, 1)
    ON CONFLICT (user_id, date)
    DO UPDATE SET query_count = agent_usage_daily.query_count + 1
    RETURNING query_count
"""), {"user_id": user_id})
new_count = result.scalar()
allowed = new_count <= limit
```

This increments and checks atomically. If the limit is exceeded, decrement:
`DO UPDATE SET query_count = LEAST(agent_usage_daily.query_count + 1, limit)`.

---

### P1-04 · Module-level mutable shared state for ML predictor is not thread-safe

**File**: `backend/services/price_service.py`
**Lines**: 20–21, 199–214 (`_try_ml_forecast`)

```python
_ensemble_predictor = None
_ensemble_load_attempted = False
```

These module-level globals are modified inside `_try_ml_forecast` while
executing in `asyncio.to_thread`. Multiple concurrent requests can race on
`_ensemble_load_attempted` flag:

- Request A checks `_ensemble_load_attempted` → False, enters the load branch
- Request B checks `_ensemble_load_attempted` → False (before A sets it), enters the load branch
- Both threads load the predictor independently, one overwrites the other

The load is expensive (reads from disk) and the double-load is wasteful. In
practice `asyncio.to_thread` uses a `ThreadPoolExecutor`, so the GIL mostly
protects against race corruption, but the TOCTOU is real for the "check before
setting" logic.

**Suggested fix**: Use an `asyncio.Lock` or a class-level initialized-once
pattern with `asyncio.Event`.

---

### P1-05 · `email_scanner_service` silently swallows all attachment download failures

**File**: `backend/services/email_scanner_service.py`
**Lines**: 340–342 (`download_gmail_attachments`) and 380–387 (`download_outlook_attachments`)

```python
except Exception:
    # Skip attachments that fail to download
    continue
```

Bare `except Exception: continue` without logging means attachment download
failures are completely invisible. A persistent failure (e.g., expired OAuth
token, API quota exceeded, permission error) would silently produce empty
extraction results, which would look like successful processing to callers.

**Suggested fix**: Log the exception with at least a warning:

```python
except Exception as exc:
    logger.warning(
        "attachment_download_failed",
        email_id=email_id,
        attachment_id=meta.get("attachment_id"),
        error=str(exc),
    )
    continue
```

---

### P1-06 · `extract_rates_from_attachments` swallows all extraction failures silently

**File**: `backend/services/email_scanner_service.py`
**Lines**: 466–469

```python
except Exception:
    # Never crash on a single attachment — log and move on
    extracted_results.append({"filename": filename})
    continue
```

The comment says "log and move on" but there is no logging call. An extraction
exception (e.g., a `pypdf` crash on a corrupt PDF) will produce a result with
only `{"filename": filename}`, and the caller has no way to distinguish
"successfully processed but found nothing" from "crashed during processing."

---

### P1-07 · `dunning_service.handle_payment_failure` does not commit after marking email_sent

**File**: `backend/services/dunning_service.py`
**Lines**: 359–368

```python
if email_sent and record.get("id"):
    await self._db.execute(
        text("""
            UPDATE payment_retry_history
            SET email_sent = TRUE, email_sent_at = NOW(), updated_at = NOW()
            WHERE id = :id
        """),
        {"id": str(record["id"])},
    )

# 5. Escalate if needed
escalation = await self.escalate_if_needed(user_id, retry_count, user_repo)
```

The UPDATE marking `email_sent = TRUE` is not committed until line 384
(`await self._db.commit()`). If `escalate_if_needed` raises an exception
between the UPDATE and the commit, the email_sent flag will never be persisted,
causing the next webhook event to re-send the dunning email despite having
already sent it. This partially defeats the cooldown check.

**Suggested fix**: Commit or use a savepoint after each independent state
update, or ensure the exception in `escalate_if_needed` is caught and still
commits.

---

### P1-08 · `portal_scraper_service` has no timeout on the full scrape sequence

**File**: `backend/services/portal_scraper_service.py`
**Lines**: 279–345 (`_scrape_known_utility`)

Each individual HTTP call uses the `httpx.AsyncClient` timeout of `_DEFAULT_TIMEOUT = 30s`, but the scrape sequence performs up to 3 separate HTTP requests:

1. GET login page (30s)
2. POST credentials (30s)
3. GET billing page (30s)

Total worst-case: 90 seconds with no overall timeout. The `scrape_portals.yml`
GHA cron workflow likely has its own timeout, but the service itself has no
guard. A portal that responds slowly on every call (but within 30s each) could
hold a connection for 90 seconds.

**Suggested fix**: Wrap `_scrape_known_utility` in `asyncio.wait_for(..., timeout=60)`.

---

### P1-09 · `alert_service.update_alert` builds dynamic SET clause with column names from `filtered` dict — trusted but fragile

**File**: `backend/services/alert_service.py`
**Lines**: 753–770 (`update_alert`)

```python
allowed_fields = {
    "region", "currency", "price_below", "price_above",
    "notify_optimal_windows", "is_active",
}
filtered = {k: v for k, v in updates.items() if k in allowed_fields}
set_clauses = ", ".join(f"{k} = :{k}" for k in filtered)
result = await db.execute(
    text(f"""
        UPDATE price_alert_configs
        SET {set_clauses}, updated_at = NOW()
        ...
    """),
    params,
)
```

The column names in `set_clauses` come from the `filtered` dict keys, which
are whitelisted against `allowed_fields`. This prevents unknown columns from
being used. However, the column names are interpolated directly into the SQL
text using an f-string rather than through bind parameters. This is safe only
because the allowlist is a hard-coded set of strings — but future maintainers
may not realize this pattern requires the allowlist to be maintained carefully.
The pattern is structurally identical to SQL injection and should be replaced
with explicit conditional column building.

---

### P1-10 · `rate_scraper_service` passes API token in query string (logged by httpx)

**File**: `backend/services/rate_scraper_service.py`
**Lines**: 72–78 (`extract_rates_from_url`)

```python
resp = await client.get(
    DIFFBOT_EXTRACT_URL,
    params={"token": self._token, "url": url},
)
```

The Diffbot API token is sent as a URL query parameter. httpx logs requests at
DEBUG level, and structured loggers (structlog) may include URL parameters in
log lines. The API key would appear in:
- Application logs (if DEBUG logging is enabled in dev/staging)
- Any HTTP proxy access logs
- Diffbot's own server logs (which show the full URL)

**Suggested fix**: Use the `Authorization: Bearer <token>` header instead of
a query parameter:

```python
resp = await client.get(
    DIFFBOT_EXTRACT_URL,
    params={"url": url},
    headers={"Authorization": f"Bearer {self._token}"},
)
```

---

### P1-11 · `market_intelligence_service` passes API key in request body

**File**: `backend/services/market_intelligence_service.py`
**Lines**: 29–39 (`search_energy_news`)

```python
resp = await client.post(
    TAVILY_SEARCH_URL,
    json={
        "api_key": self._api_key,
        ...
    },
)
```

The Tavily API key is in the JSON body of each request. While less exposed
than a URL query parameter, the key will appear in:
- Any request body logging enabled at DEBUG level
- Packet captures / network debugging tools
- The Tavily access logs

**Suggested fix**: Use `Authorization: Bearer` header per the Tavily
documentation.

---

### P1-12 · `data_quality_service.get_source_reliability` silently catches all DB exceptions including fatal ones

**File**: `backend/services/data_quality_service.py`
**Lines**: 165–196 (`get_source_reliability`)

```python
try:
    result = await self._db.execute(text("SELECT ... FROM scrape_results ..."))
    ...
except Exception:
    # Fallback: count records per source in electricity_prices
    logger.info("scrape_results table not found, falling back to electricity_prices")
    ...
```

The bare `except Exception` is intended to handle the case where the
`scrape_results` table does not exist (migration not run). But it also silently
catches and hides:
- Connection pool exhaustion
- Authentication failures
- SQL syntax errors (masked as "table not found")
- `asyncpg.TooManyConnectionsError`

When the fallback is used due to a real database failure rather than a missing
table, the returned reliability data will be completely wrong (showing 100%
success rate for all sources).

**Suggested fix**: Catch the specific exception for missing tables
(`sqlalchemy.exc.ProgrammingError` with `UndefinedTableError`) rather than
all exceptions.

---

### P1-13 · `feature_flag_service.is_enabled` uses MD5 for rollout hashing

**File**: `backend/services/feature_flag_service.py`
**Lines**: 64–69

```python
hash_val = int(
    hashlib.md5(f"{flag_name}:{user_id}".encode()).hexdigest()[:8],
    16,
)
```

MD5 is used only for deterministic hashing, not for cryptographic security,
so this is not an immediate vulnerability. However, MD5 is a banned hash
algorithm in many security compliance frameworks (FIPS 140-2, PCI-DSS). The
`ab_test_service.py` correctly uses SHA-256 for the same purpose (line 77).

**Suggested fix**: Replace MD5 with SHA-256 for consistency and compliance:

```python
hash_val = int(hashlib.sha256(f"{flag_name}:{user_id}".encode()).hexdigest()[:8], 16)
```

---

### P1-14 · `forecast_service._forecast_electricity` embeds interval value as f-string

**File**: `backend/services/forecast_service.py`
**Lines**: 115–125

```python
result = await self.db.execute(
    text(f"""
        SELECT price_per_kwh, timestamp
        FROM electricity_prices
        WHERE utility_type = 'ELECTRICITY'
          AND timestamp >= NOW() - INTERVAL '{TREND_LOOKBACK_DAYS} days'
          {region_filter}
        ORDER BY timestamp ASC
    """),
    params,
)
```

`TREND_LOOKBACK_DAYS` is an integer constant (90), so this is safe from
injection today. But the pattern (interpolating an integer into an INTERVAL
expression via f-string) is fragile. If this constant is ever made configurable
via an API parameter, the code becomes immediately injectable. PostgreSQL
supports `NOW() - ($1 * INTERVAL '1 day')` or `NOW() - make_interval(days => $1)`.

**Suggested fix**:
```python
AND timestamp >= NOW() - (:lookback_days * INTERVAL '1 day')
```
with `params["lookback_days"] = TREND_LOOKBACK_DAYS`.

---

## P2 — Medium

### P2-01 · `agent_service._run_async_job` falls back to Groq unconditionally on any Gemini error

**File**: `backend/services/agent_service.py`
**Lines**: 318–323 (`_run_async_job`)

```python
try:
    result = await self._query_gemini(system, prompt)
    model_used = "gemini-3-flash-preview"
except Exception:
    result = await self._query_groq(system, prompt)
    model_used = "llama-3.3-70b-versatile"
```

Unlike the streaming path (`query_streaming`, lines 197–224), the async job
path does NOT check whether the error is a rate limit (429) before falling
back to Groq. Any Gemini error — including a malformed API key, network error,
or a permanent API error — will trigger the Groq fallback and consume Groq
rate limit credits. If the Gemini key is misconfigured, every async job will
silently double the Groq API calls.

**Suggested fix**: Mirror the rate-limit check logic from `query_streaming`:
```python
except Exception as gemini_err:
    if "429" in str(gemini_err) and settings.groq_api_key:
        result = await self._query_groq(system, prompt)
    else:
        raise
```

---

### P2-02 · `community_service.list_posts` does not validate `page` or `per_page` inputs

**File**: `backend/services/community_service.py`
**Lines**: 188–250 (`list_posts`)

The `list_posts` method accepts `page` and `per_page` parameters but applies
no bounds checking. A caller passing `per_page=100000` would cause Postgres to
fetch up to 100,000 community post rows with full vote and report COUNT joins,
leading to heavy database load. `page=0` would produce a negative OFFSET
(`(0-1) * per_page = -per_page`), causing a Postgres error.

**Suggested fix**:
```python
page = max(1, page)
per_page = max(1, min(100, per_page))
```

---

### P2-03 · `alert_service.get_active_alert_configs` has hard-coded LIMIT 5000

**File**: `backend/services/alert_service.py`
**Lines**: 527–530

```python
ORDER BY pac.created_at
LIMIT 5000
```

If the platform grows beyond 5,000 active alert configurations, the check-
alerts cron will silently process only the oldest 5,000. Newer alerts will
never be checked until older ones are deleted. This is a silent data loss
scenario — users will stop receiving alerts without any error or warning.

**Suggested fix**: Paginate the query in the cron endpoint, or at minimum log
a warning when `len(rows) == 5000`.

---

### P2-04 · `push_notification_service` import assumed correct but never validated at module level

**File**: `backend/services/notification_dispatcher.py`
**Lines**: 56–58

The `PushNotificationService`, `NotificationService`, and `EmailService` are
imported at module level. If any of these imports fail (e.g., missing
dependency), the entire `notification_dispatcher` module fails to load, which
cascades to all services that import `NotificationChannel`. No lazy-import
guard exists.

This is lower priority than the above but affects startup reliability.

---

### P2-05 · `recommendation_service._compute_switching` returns recommendation when `potential_savings` is negative

**File**: `backend/services/recommendation_service.py`
**Lines**: 279–308 (`_compute_switching`)

When `current_price` is `None` (user's supplier not in the price list), it
falls back to `prices[-1].price_per_kwh` — the most expensive supplier (since
`prices` is sorted ascending). In that case `current_price` equals the maximum
price, `potential_savings` is always positive, and the method always returns a
recommendation even when no better option exists.

However, when the user is already on the cheapest supplier, `potential_savings`
is `<= 0` and `savings_percentage` is `<= 0`. The method still returns a
`SwitchingRecommendation` with a negative or zero `potential_savings`. The
caller would need to check for this case, and there is no documentation or
type annotation indicating the return value may have negative savings.

**Suggested fix**: Return `None` when `potential_savings <= 0`:
```python
if potential_savings <= Decimal("0"):
    return None
```

---

### P2-06 · `maintenance_service.cleanup_expired_uploads` deletes files outside the transaction

**File**: `backend/services/maintenance_service.py`
**Lines**: 95–102

```python
await self._db.commit()  # DB rows deleted here

for row in old_uploads:  # File deletion happens after commit
    file_path = row[1]
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
```

Files are deleted from disk *after* the DB transaction commits. If the file
deletion fails (permissions, race with another process), the DB record is gone
but the file remains — a storage leak. Conversely, if the process crashes
between the commit and the file deletions, files are leaked.

The `except OSError: pass` silently ignores all filesystem errors including
unexpected ones (e.g., `os.remove` on a directory).

**Suggested fix**: Log file deletion failures. Consider a separate cleanup
table that records files to be deleted, with a background job to drain it.

---

### P2-07 · `email_service` logs the recipient email address at INFO level

**File**: `backend/services/email_service.py`
**Lines**: 100–104, 143–144

```python
logger.info("email_sent_resend", to=to, subject=subject)
logger.info("email_sent_smtp", to=to, subject=subject)
```

Logging email addresses at INFO level means they appear in production logs.
Depending on the logging aggregator (Grafana, Sentry, etc.), this may violate
GDPR/CCPA by persisting PII in logging infrastructure without adequate controls.

**Suggested fix**: Hash or redact the email address in logs:
```python
import hashlib
email_hash = hashlib.sha256(to.encode()).hexdigest()[:12]
logger.info("email_sent_resend", to_hash=email_hash, subject=subject)
```

---

### P2-08 · `geocoding_service` swallows all geocoding exceptions including auth failures

**File**: `backend/services/geocoding_service.py`
**Lines**: 102–104 and 143–145

```python
except Exception as e:
    logger.warning("geocode_owm_failed", error=str(e))
    return None
```

A 401 Unauthorized response (expired or invalid API key) is treated the same
as a temporary network timeout. The service silently falls back to Nominatim
for every request rather than alerting that the OWM API key is invalid. This
can lead to unexpected Nominatim rate-limit violations (1 req/s policy).

**Suggested fix**: Distinguish auth errors from transient failures:
```python
if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 401:
    logger.error("geocode_owm_auth_failed", message="OWM API key invalid or expired")
```

---

### P2-09 · `savings_service.record_savings` does not validate that `amount > 0`

**File**: `backend/services/savings_service.py`
**Lines**: 192–254 (`record_savings`)

The method accepts `amount: float` and inserts it without validation. A caller
passing `amount=-50.0` or `amount=0.0` would silently insert invalid savings
records that would corrupt totals and streak calculations. The docstring says
"amount: Monetary saving amount (must be positive)" but this is not enforced.

**Suggested fix**:
```python
if amount <= 0:
    raise ValueError(f"Savings amount must be positive, got {amount}")
```

---

### P2-10 · `kpi_report_service` uses `pg_class.reltuples` which is approximate and can be zero on a fresh table

**File**: `backend/services/kpi_report_service.py`
**Lines**: 53–55

```python
prices AS (
    SELECT COALESCE(reltuples, 0)::bigint AS val
    FROM pg_class WHERE relname = 'electricity_prices'
),
```

`pg_class.reltuples` is a statistics estimate updated by VACUUM/ANALYZE, not a
live count. On a freshly created table or after a large bulk insert, it can
be 0 or wildly inaccurate. For a KPI dashboard this can mislead operators into
thinking there are no price records. The comment "prices_tracked" implies this
is a meaningful business metric.

**Suggested fix**: Use `SELECT COUNT(*)` wrapped in a time-bounded query, or
at minimum add a note in the response that this is an estimate.

---

### P2-11 · `forecast_service._extrapolate_trend` divides by `current_rate` without handling zero

**File**: `backend/services/forecast_service.py`
**Lines**: 262

```python
pct_change = ((forecasted_rate - current_rate) / current_rate * 100) if current_rate > 0 else 0
```

This is correctly guarded for `current_rate > 0`. However, `current_rate =
prices[-1]` could theoretically be 0.0 if bad data was ingested (a price of
$0.00/kWh). The guard handles this, but it returns `pct_change = 0` which is
misleading (trend would look stable when forecasted_rate is nonzero).

---

### P2-12 · `connection_sync_service._batch_insert_extracted_rates` can produce unbounded query size

**File**: `backend/services/connection_sync_service.py`
**Lines**: 407–441 (`_batch_insert_extracted_rates`)

```python
placeholders = []
params: dict = {}
for i, rate_data in enumerate(rate_records):
    placeholders.append(f"(:id{i}, :cid{i}, :rate{i}, ...)")
    params[f"id{i}"] = ...
```

If a single sync returns thousands of bills (a power user with years of
history), this creates a single INSERT with thousands of rows. PostgreSQL
has a hard limit of ~65,535 parameters per query. With 6 parameters per row,
this overflows at ~10,922 records.

**Suggested fix**: Batch in chunks of 500:
```python
for chunk in [rate_records[i:i+500] for i in range(0, len(rate_records), 500)]:
    await self._do_batch_insert(connection_id, chunk)
```

---

### P2-13 · `portal_scraper_service` does not validate that `login_url` is an http/https URL

**File**: `backend/services/portal_scraper_service.py`
**Lines**: 206–273 (`scrape_portal`)

The `login_url` parameter is passed directly to `httpx.AsyncClient.get()`.
If a caller passes a `file://` URI or a `javascript:` scheme, httpx would
raise a `httpx.UnsupportedProtocol` exception which is caught by the outer
`except Exception` and returned as `{"success": False, ...}`. This is safe,
but the error message would be misleading.

More importantly, if `login_url` is user-supplied and the service runs without
proper network egress controls, it could be used as an SSRF vector to probe
internal endpoints.

**Suggested fix**: Validate that the URL starts with `https://`:
```python
if not login_url.startswith("https://"):
    raise ValueError(f"login_url must use HTTPS: {login_url!r}")
```

---

### P2-14 · `notification_dispatcher` does not validate `email_to` format before attempting send

**File**: `backend/services/notification_dispatcher.py`
**Lines**: 223–246

If `email_to` is a non-empty string but not a valid email address (e.g.,
`""` or `"not-an-email"`), the EmailService will attempt to send to an invalid
address. Resend and SMTP will return an error, but this error is only logged at
WARNING level and `success` is set to `False` without surfacing to the caller.

---

### P2-15 · `ab_test_service.assign_user` does not handle the case where persistent assignment differs from hash

**File**: `backend/services/ab_test_service.py`
**Lines**: 156–158

```python
existing = await self.get_assignment(user_id)
if existing is not None:
    return existing
```

If a user was assigned to `version_a` in a previous test run and the caller
is now running a new test with different `version_a`/`version_b` strings, the
method returns the stale assignment from the old test. The `salt` parameter
exists to differentiate tests but is not included in the `get_assignment` DB
lookup — the lookup is only by `user_id`.

This means a user who participated in test "v1.0 vs v2.0" will be returned
"v1.0" even when the caller is running test "v2.0 vs v3.0".

**Suggested fix**: Include `salt` in the DB lookup:
```sql
SELECT model_version FROM model_ab_assignments
WHERE user_id = :user_id AND salt = :salt
```
(requires adding a `salt` column to `model_ab_assignments`).

---

### P2-16 · `data_quality_service.detect_anomalies` returns anomalies from the `electricity_prices` table only

**File**: `backend/services/data_quality_service.py`
**Lines**: 97–152 (`detect_anomalies`)

The method is called `detect_anomalies` and is on `DataQualityService`, which
monitors "all utility data sources" per the module docstring. However it only
queries `electricity_prices`, ignoring `heating_oil_prices`,
`propane_prices`, `water_rates`, and `gas_supplier_rates`. Anomalies in other
utility types are silently missed.

---

### P2-17 · `neighborhood_service` comparison SQL uses `user_savings.amount` as a rate proxy

**File**: `backend/services/neighborhood_service.py`
**Lines**: 62–100

The comparison query joins `user_savings` to `suppliers` on `supplier_id`,
but `user_savings` stores monetary *amounts* (dollars saved), not rate values
($/kWh). Using `AVG(us.amount)` as a rate proxy is semantically incorrect —
the average of "dollars saved per month" is not comparable to "rate per kWh."
This will produce misleading percentile rankings.

The correct table to use for actual rate comparisons would be
`connection_extracted_rates` or `electricity_prices`.

---

## P3 — Low

### P3-01 · `agent_service.py` uses `except Exception:` in top-level import blocks

**File**: `backend/services/agent_service.py`
**Lines**: 25–33

```python
try:
    from google import genai
except Exception:
    genai = None
```

Using `except Exception:` instead of `except ImportError:` would silently
catch and hide bugs in the `google.genai` module (e.g., a
`ModuleNotFoundError` from a missing sub-dependency like `google-auth`). This
can make debugging difficult.

**Suggested fix**: Use `except ImportError:`.

---

### P3-02 · `forecast_service.get_forecast` has an unreachable `return` statement

**File**: `backend/services/forecast_service.py`
**Lines**: 99

```python
elif utility_type == "propane":
    return await self._forecast_from_table(...)

return {"utility_type": utility_type, "error": "Unknown utility type"}
```

The final `return` at line 99 is unreachable because the preceding `if/elif`
chain covers all cases in `FORECASTABLE_UTILITIES` (the only values that can
reach this code, since other values were returned at line 52–56). This is
dead code and can confuse future maintainers.

---

### P3-03 · Missing type hints on public methods in `community_service.py`

**File**: `backend/services/community_service.py`

The `agent_service` parameter on `create_post`, `_run_moderation`,
`retroactive_moderate`, etc. is typed as `Any`. Using a proper Protocol or
abstract base class would make the interface explicit and catch mismatches
at type-check time.

---

### P3-04 · `savings_service._compute_streak` is a dead method

**File**: `backend/services/savings_service.py`
**Lines**: 278–303 (`_compute_streak`)

`_compute_streak` is a private static method that is never called within the
class. The streak calculation was moved to SQL (the CTE in
`get_savings_summary`, lines 89–96). This method is dead code and should be
removed to avoid confusion.

---

### P3-05 · `recommendation_service` uses `logging.getLogger` while all other services use `structlog`

**File**: `backend/services/recommendation_service.py`
**Line**: 18

```python
import logging
_logger = logging.getLogger(__name__)
```

All other services use `structlog.get_logger()`. Using standard `logging`
here means log events from this service lose structured context (user IDs,
region codes, etc.) and do not integrate with the project's log aggregation
pipeline correctly.

**Suggested fix**: `logger = structlog.get_logger(__name__)`.

---

### P3-06 · `price_service.py` also uses `logging` instead of `structlog`

**File**: `backend/services/price_service.py`
**Line**: 17

Same issue as P3-05.

---

### P3-07 · `email_scanner_service` opens separate `httpx.AsyncClient` instances per API call

**File**: `backend/services/email_scanner_service.py`
**Lines**: 99, 168, 220, 292, 363

Each function opens its own `httpx.AsyncClient` inside an `async with` block.
For functions called in a loop (e.g., `extract_rates_from_email` called per
email), this creates and tears down a new connection pool for each iteration.
A shared client (or at least a per-scan client) would be more efficient.

---

### P3-08 · `market_intelligence_service.weekly_market_scan` hardcodes "2026" in search queries

**File**: `backend/services/market_intelligence_service.py`
**Lines**: 60–62

```python
queries = [
    f"{region} electricity rate change 2026"
    for region in regions[:10]
]
```

The year `2026` is hardcoded. This query will produce poor results in 2027
without a code change.

**Suggested fix**:
```python
from datetime import datetime
year = datetime.now().year
queries = [f"{region} electricity rate change {year}" for region in regions[:10]]
```

---

### P3-09 · `portal_scraper_service._extract_from_response` is a public method wrapping a private function

**File**: `backend/services/portal_scraper_service.py`
**Lines**: 468–470

```python
async def _extract_from_response(self, html: str) -> List[Dict[str, Any]]:
    """Extract rate data from an HTML response string."""
    return _extract_rates_from_html(html)
```

This method is named with a leading underscore (private) but the docstring
says "exposed for testing." If it is intended to be a test interface, it
should be public (no underscore). If it is private, tests should not use it
directly. The inconsistency is a minor API design issue.

---

### P3-10 · `savings_aggregator.get_combined_savings` returns `Decimal` values in `breakdown` but `float` for `savings_rank_pct`

**File**: `backend/services/savings_aggregator.py`
**Lines**: 61–97

The `breakdown` items contain `Decimal` objects for `monthly_savings`, while
`savings_rank_pct` is `float`. The `total_monthly_savings` is a `Decimal`.
Callers serializing this to JSON need to handle both types. Consistency would
simplify serialization.

---

### P3-11 · `weather_service.get_current_weather` accesses `data["weather"][0]` without bounds check

**File**: `backend/services/weather_service.py`
**Lines**: 103

```python
"description": data["weather"][0]["description"],
```

If the OWM API returns an empty `weather` list (which can happen for
edge-case location data), this raises `IndexError`. The method's exception
handling (`raise_for_status()` only catches HTTP errors) would not catch this.

**Suggested fix**:
```python
"description": data.get("weather", [{}])[0].get("description", ""),
```

---

### P3-12 · `referral_service.generate_code` leaks the exception type on all retries

**File**: `backend/services/referral_service.py`
**Lines**: 56–59

```python
except Exception:
    await self._db.rollback()
    if attempt == _MAX_RETRIES - 1:
        raise ReferralError("Failed to generate unique referral code")
```

On the final retry, the code raises a `ReferralError` but swallows the
original exception. The original error (which could be a connection timeout,
a constraint violation on a column other than the code, or a serialization
failure) is lost. Callers and logs only see "Failed to generate unique referral
code" without any way to distinguish a collision from a database error.

**Suggested fix**:
```python
raise ReferralError("Failed to generate unique referral code") from exc
```

---

## Cross-Cutting Observations

1. **Consistent use of `text()` with bind parameters is good.** The vast
   majority of raw SQL in these services correctly uses `:param_name` style
   bind parameters. The injection risks documented above are the exceptions.

2. **Structlog is used consistently.** Only `price_service.py` and
   `recommendation_service.py` use the standard `logging` module; all other
   services use `structlog`. This should be unified.

3. **No hardcoded secrets found.** API keys, webhook secrets, and credentials
   are correctly read from `settings.*` throughout. The only issue is tokens
   being passed in URL query parameters (P1-10) and request bodies (P1-11)
   rather than headers.

4. **Transaction discipline is mostly good.** Most write operations call
   `await db.commit()` after mutations. The exceptions noted above (P1-07,
   P0-08) should be fixed.

5. **Error handling breadth vs. specificity.** Many `except Exception:` clauses
   are too broad. The pattern of catching the broadest exception and returning
   a safe default silently hides bugs. Consider adding Sentry error tracking
   or re-raising unexpected exceptions after logging.

6. **`asyncio.to_thread` is used correctly** for blocking I/O (ML predictor
   loading, Stripe/Resend calls). The Semaphore pattern in `weather_service`
   and `rate_scraper_service` is well implemented.

---

*Generated by Claude Code on 2026-03-16. Review findings and triage before closing.*
