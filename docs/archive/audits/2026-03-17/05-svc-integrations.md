# Audit Report: Integration Services
## Date: 2026-03-17

### Executive Summary

Ten integration service files were audited covering Stripe billing, email delivery, Gmail/Outlook OAuth and scanning, portal credential scraping, the AI agent, push notifications, geocoding, weather, and market intelligence. The overall security posture is strong: Stripe webhook signatures are properly verified before any event data is trusted, OAuth tokens are encrypted at rest with AES-256-GCM, and billing redirect URLs are allowlist-validated at the API layer. Three issues require attention before the next external traffic milestone: an SSRF vector in the portal scraper (user-supplied login URLs are passed to httpx without an allowlist), a missing expiry on OAuth state tokens enabling indefinite state replay, and the async agent job silently swallowing Groq errors without updating the Redis job status to "failed".

---

### Findings

#### P0 — Critical

- **[P0-01] SSRF via unvalidated portal login URL**
  - **File**: `backend/services/portal_scraper_service.py` lines 301–310, 366–368; `backend/models/connections.py` line 257; `backend/api/v1/connections/portal_scrape.py` line 133
  - **Description**: `portal_login_url` is an `Optional[str]` field with only a `max_length=1000` constraint. The value is stored verbatim and later passed directly to `httpx.AsyncClient.get()` in `_scrape_known_utility` and `_scrape_generic`. An authenticated paid-tier user can supply `http://169.254.169.254/latest/meta-data/` (EC2 IMDS), `http://localhost:5432/` (internal Postgres), `file:///etc/passwd`, or any internal service URL. Because `follow_redirects=True` is set on the client, multi-hop SSRF chains are also possible.
  - **Impact**: Full SSRF against the Render backend's internal network. On cloud environments this can expose instance metadata credentials, internal databases, or other services. Even without credentials, the latency oracle reveals internal topology.
  - **Fix**: Validate `portal_login_url` at the Pydantic model level against the `SUPPORTED_UTILITIES` domain allowlist, and enforce it again in the scraper before issuing any HTTP request. Reject private IP ranges (RFC-1918, link-local, loopback) and non-HTTPS schemes. Example for the Pydantic model:

    ```python
    from urllib.parse import urlparse
    import ipaddress

    _ALLOWED_PORTAL_HOSTNAMES = {
        "www.duke-energy.com", "www.pge.com", "www.coned.com",
        "secure.comed.com", "www.fpl.com",
    }
    _PRIVATE_NETS = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
    ]

    @field_validator("portal_login_url")
    @classmethod
    def validate_portal_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        parsed = urlparse(v)
        if parsed.scheme != "https":
            raise ValueError("portal_login_url must use HTTPS")
        if parsed.hostname not in _ALLOWED_PORTAL_HOSTNAMES:
            raise ValueError(f"Hostname '{parsed.hostname}' is not in the approved list")
        # Reject numeric IPs
        try:
            addr = ipaddress.ip_address(parsed.hostname)
            if any(addr in net for net in _PRIVATE_NETS):
                raise ValueError("Private/internal IP addresses are not allowed")
        except ValueError:
            pass  # hostname is a domain name, not an IP
        return v
    ```

    Additionally configure the httpx client with `trust_env=False` and restrict the transport to external HTTPS only.

---

#### P1 — High

- **[P1-01] OAuth state token has no expiry — indefinite replay window**
  - **File**: `backend/services/email_oauth_service.py` lines 38–65
  - **Description**: `generate_oauth_state` creates `{connection_id}:{nonce}:{hmac}`. The HMAC is a valid CSRF defence, but because there is no timestamp embedded and no server-side nonce store, a captured state token is valid forever. Anyone who intercepts a state from a network log, browser history, or monitoring tool can replay it at any future time against the callback endpoint.
  - **Impact**: A replayed state token could be used to associate an attacker-controlled OAuth grant with a victim's `connection_id`, hijacking their email connection.
  - **Fix**: Embed a Unix timestamp in the payload and reject tokens older than 10 minutes in `verify_oauth_state`. No server-side state is required:

    ```python
    import time

    _STATE_MAX_AGE_SECONDS = 600

    def generate_oauth_state(connection_id: str) -> str:
        nonce = secrets.token_hex(16)
        ts = str(int(time.time()))
        payload = f"{connection_id}:{nonce}:{ts}"
        key = settings.internal_api_key.encode()
        mac = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}:{mac}"

    def verify_oauth_state(state: str) -> Optional[str]:
        parts = state.split(":")
        if len(parts) != 4:
            return None
        connection_id, nonce, ts_str, received_mac = parts
        payload = f"{connection_id}:{nonce}:{ts_str}"
        key = settings.internal_api_key.encode()
        expected_mac = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received_mac, expected_mac):
            return None
        try:
            age = int(time.time()) - int(ts_str)
        except ValueError:
            return None
        if age > _STATE_MAX_AGE_SECONDS or age < 0:
            return None
        return connection_id
    ```

    Note: existing tests in `test_email_oauth.py` check for three-part state format and will need updating.

- **[P1-02] Async agent job silently swallows Groq fallback errors**
  - **File**: `backend/services/agent_service.py` lines 314–342 (`_run_async_job`)
  - **Description**: In `_run_async_job`, if `_query_gemini` raises an exception the code immediately calls `_query_groq`. If Groq also raises, the outer `except Exception as e` correctly marks the job as "failed". However, if Gemini raises for a *non-rate-limit* reason (e.g. network timeout, content policy rejection) the fallback to Groq is unconditional — unlike in `query_streaming` which only falls back on 429/ResourceExhausted. This means a permanent Gemini misconfiguration causes every async job to silently consume a Groq token per attempt even when Groq will also fail, and the failure reason is buried.
  - **Secondary issue**: `query_async` uses `asyncio.create_task` to run `_run_async_job`. If `db` expires before the task reads from it (FastAPI closes the session after the request returns), the background task will encounter a detached session error; the DB session is not passed into the background task.
  - **Impact**: (1) Groq quota exhaustion from unnecessary fallback attempts. (2) Background task DB writes fail silently when the session is closed.
  - **Fix**: Mirror the `query_streaming` fallback logic (only fall back on rate-limit errors), and pass a fresh DB session obtained from the app's `sessionmaker` rather than relying on the request-scoped session:

    ```python
    # _run_async_job: mirror the 429-only fallback
    try:
        result = await self._query_gemini(system, prompt)
        model_used = "gemini-3-flash-preview"
    except Exception as gemini_err:
        err_str = str(gemini_err)
        is_rate_limited = "429" in err_str or "ResourceExhausted" in err_str
        if is_rate_limited:
            result = await self._query_groq(system, prompt)
            model_used = "llama-3.3-70b-versatile"
        else:
            raise  # bubble up to outer except, marks job "failed"
    ```

- **[P1-03] Rate limit check and usage increment are not atomic in the streaming path**
  - **File**: `backend/services/agent_service.py` lines 110–138 (`check_rate_limit`), line 248 (`increment_usage`); `backend/api/v1/agent.py` lines 130–137
  - **Description**: `check_rate_limit` reads the current count with an upsert that deliberately does *not* increment (`SET query_count = agent_usage_daily.query_count`). Then the caller yields the response, and only after the response is fully generated does `increment_usage` run. Two concurrent SSE requests from the same free-tier user can both pass the limit check (both reading `count < 3`) before either increments. The memory notes describe this as "TOCTOU-safe" but the fix only applied to the upsert itself — the check and increment remain separate round-trips.
  - **Impact**: Free users can exceed the 3-query daily limit by submitting concurrent requests. For Pro users (20/day) the window is wider.
  - **Fix**: Increment first (unconditionally), then compare the returned count to the limit. Reject if over by rolling back the increment:

    ```python
    count_result = await db.execute(
        text("""
            INSERT INTO agent_usage_daily (user_id, date, query_count)
            VALUES (:user_id, CURRENT_DATE, 1)
            ON CONFLICT (user_id, date) DO UPDATE
                SET query_count = agent_usage_daily.query_count + 1
            RETURNING query_count
        """),
        {"user_id": user_id},
    )
    new_count = count_result.scalar() or 1
    allowed = new_count <= limit
    if not allowed:
        # Roll back the speculative increment
        await db.execute(
            text("UPDATE agent_usage_daily SET query_count = query_count - 1 "
                 "WHERE user_id = :user_id AND date = CURRENT_DATE"),
            {"user_id": user_id},
        )
    return allowed, new_count - (0 if allowed else 1), limit
    ```

    Alternatively, use a Postgres advisory lock on `(user_id, date)` to serialize concurrent checks.

- **[P1-04] Missing timeout on Resend email API call**
  - **File**: `backend/services/email_service.py` lines 71–109 (`_send_via_resend`)
  - **Description**: `asyncio.to_thread(resend.Emails.send, params)` has no timeout. The underlying `resend` library uses `httpx` internally but the timeout is not configured. A hung Resend connection will block the thread pool worker indefinitely, potentially exhausting the thread pool under load.
  - **Impact**: DoS via resource exhaustion if Resend experiences latency. Email sending (including alerts, dunning emails, and password resets) will stall.
  - **Fix**: Wrap with `asyncio.wait_for`:

    ```python
    await asyncio.wait_for(
        asyncio.to_thread(resend.Emails.send, params),
        timeout=15.0,
    )
    ```

- **[P1-05] Gmail/Outlook email body fetched without size cap — memory exhaustion risk**
  - **File**: `backend/services/email_scanner_service.py` lines 220–249 (`extract_rates_from_email`)
  - **Description**: `format=full` for Gmail and `$select=body` for Outlook fetch the complete email body with no content length guard. A maliciously crafted or pathologically large email (e.g. a newsletter with an embedded base64 image in the body text rather than as an attachment) will be downloaded in its entirety into memory and then passed through regex extraction.
  - **Impact**: A single large email could exhaust server memory. The `_OAUTH_TIMEOUT` of 10 seconds limits download time but not response size.
  - **Fix**: Add a response size check before processing:

    ```python
    resp.raise_for_status()
    if int(resp.headers.get("content-length", 0)) > 10 * 1024 * 1024:  # 10 MB
        return {}
    data = resp.json()
    ```

    For Gmail, prefer fetching with `format=metadata` first (already done in `scan_gmail_inbox`) and only fetch full body for confirmed utility-bill messages.

---

#### P2 — Medium

- **[P2-01] `_extract_rates_from_text` regex produces unbounded match for `total_kwh`**
  - **File**: `backend/services/email_scanner_service.py` lines 496–503
  - **Description**: The `total_kwh` regex `([\d,]+(?:\.\d+)?)` has no upper bound and will match strings like `1,234,567,890`. The result is cast to `float` without a sanity check. A value of `float("1234567890")` would be stored as a legitimate usage figure.
  - **Impact**: Corrupted rate extraction data stored in the DB. Could cause savings calculations to wildly misrepresent actual usage.
  - **Fix**: After `float(kwh_match.group(1).replace(",", ""))`, validate the value is within a plausible range (e.g. 0 < kwh < 100_000) before including it in the result. Apply the same guard to `rate_per_kwh` (0.01–2.00 $/kWh) and `total_amount` (0–50_000).

- **[P2-02] `scan_gmail_inbox` makes N+1 HTTP calls with no concurrency limit**
  - **File**: `backend/services/email_scanner_service.py` lines 109–147
  - **Description**: For up to 50 messages, the function issues one `GET` per message ID inside a sequential `for` loop, totalling up to 51 HTTP calls. Each call respects the 10-second timeout, so in the worst case the function can take 500+ seconds to complete. The Gmail API supports batch requests (`https://www.googleapis.com/batch/gmail/v1`).
  - **Impact**: The `scan-emails` cron job (via `daily-data-pipeline.yml`) can time out or consume excessive resources when users have many matching emails.
  - **Fix**: Gather metadata fetches concurrently with a semaphore (Gmail allows ~10 concurrent requests per user token), similar to the pattern already used in `WeatherService.fetch_weather_for_regions`:

    ```python
    sem = asyncio.Semaphore(10)
    async def _fetch_meta(msg_stub):
        async with sem:
            return await client.get(...)
    responses = await asyncio.gather(*[_fetch_meta(m) for m in messages], return_exceptions=True)
    ```

- **[P2-03] Portal scraper bot-detection fingerprint is trivially blocked**
  - **File**: `backend/services/portal_scraper_service.py` lines 94–100
  - **Description**: The `User-Agent` header is `Mozilla/5.0 (compatible; RateShift/1.0; +https://rateshift.app/bot)`. The self-identifying `RateShift/1.0` token is advertised, and the `compatible;` fragment followed by a custom identifier is an unusual UA string that utility portals' WAFs will fingerprint. More problematically, the client sends no `Cookie` or `Referer` header, and modern utility portals (Duke Energy, PG&E) require JavaScript execution and multi-step auth flows that httpx cannot handle.
  - **Impact**: Scrapes against all 5 supported utilities will fail in production because these portals use React/Angular SPAs with OAuth redirects, not plain HTML form POSTs. This is a known design limitation (documented in the module docstring) but the User-Agent identification makes it easy for portals to block the IP proactively.
  - **Fix**: Either use a non-identifying UA string (a vanilla browser UA) or, preferably, gate portal scraping behind an explicit "may not work" disclaimer in the UI and handle the expected failure rate in the `_is_still_login_page` heuristic with more specific signals per utility. Do not advertise bot identity to utility WAFs.

- **[P2-04] Market intelligence service sends API key in JSON body**
  - **File**: `backend/services/market_intelligence_service.py` lines 29–39
  - **Description**: `{"api_key": self._api_key, "query": query, ...}` includes the Tavily API key in the POST body. This is consistent with Tavily's documented API contract, but means the key appears in: (a) application logs if request bodies are logged, (b) any HTTP proxy or WAF that inspects bodies, (c) error responses that echo back the request. The weather service notes this same issue for OWM (with a correct explanation in the docstring), but the market intelligence service has no such documentation.
  - **Impact**: Low probability key leak to log aggregators (Grafana, Sentry). Tavily free tier keys have limited blast radius, but good hygiene requires documentation.
  - **Fix**: Add the same explanatory comment as in `weather_service.py`. Additionally, ensure Sentry's `before_send` scrubs request bodies that contain `api_key` fields.

- **[P2-05] No retry on transient HTTP errors in push notification service**
  - **File**: `backend/services/push_notification_service.py` lines 43–64
  - **Description**: `send_push` makes a single POST to `https://onesignal.com/api/v1/notifications` with no retry on 429, 500, or 502. `resp.raise_for_status()` raises immediately. The broader notification dispatcher already calls this with `return_exceptions=True`, so a single transient OneSignal error silently drops the push notification.
  - **Impact**: Push notifications for price alerts are silently lost on transient OneSignal failures.
  - **Fix**: Add exponential backoff for 429 and 5xx responses (2–3 retries). This is consistent with the `retry-curl` pattern used in GHA workflows:

    ```python
    for attempt in range(3):
        resp = await client.post(ONESIGNAL_API_URL, ...)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
        resp.raise_for_status()
        break
    ```

- **[P2-06] `WeatherService` and `GeocodingService` share a new httpx client per call**
  - **File**: `backend/services/weather_service.py` lines 94–106, 125–136; `backend/services/geocoding_service.py` lines 80–103, 109–144
  - **Description**: Both services create an `httpx.AsyncClient` inside each method call using `async with httpx.AsyncClient(...)`. This means no connection pooling across calls. For `fetch_weather_for_regions` which fans out 51 concurrent calls using `asyncio.gather`, each task creates and tears down its own client, forgoing TCP connection reuse. This also defeats the `Semaphore(10)` intent slightly because each client has its own connection pool.
  - **Impact**: Increased latency and OS socket exhaustion risk during the 51-state weather fetch cron. No functional bug.
  - **Fix**: Share a single client instance at the service level (created in `__init__` or lazily on first use), closed via a `close()` method or async context manager — the same pattern already used in `PortalScraperService`.

- **[P2-07] `_run_async_job` does not increment usage counter**
  - **File**: `backend/services/agent_service.py` lines 314–342
  - **Description**: The async job path in `query_async` / `_run_async_job` checks the rate limit before queuing (in the API layer) but `_run_async_job` never calls `increment_usage`. In contrast, `query_streaming` calls `increment_usage` after generating the response (line 248). Async jobs therefore consume quota without decrementing the counter.
  - **Impact**: Async jobs bypass the daily usage limit entirely. Business-tier users are unaffected (unlimited), but free/pro users can submit unlimited async jobs.
  - **Fix**: Call `self.increment_usage(user_id, db)` from `_run_async_job` after a successful response, using a fresh DB session.

---

#### P3 — Low

- **[P3-01] `hmac.new` should be `hmac.new` — shadowed by standard library alias**
  - **File**: `backend/services/email_oauth_service.py` lines 48, 62
  - **Description**: The code calls `hmac.new(key, payload.encode(), hashlib.sha256)`. In Python 3, `hmac.new` is a valid alias for `hmac.HMAC` but is an undocumented implementation detail. The canonical constructor is `hmac.new()` which does work correctly, but linters and type checkers may flag it. Using `hmac.HMAC(key, payload.encode(), hashlib.sha256)` or the function form `hmac.new(key, msg, digestmod)` is equivalent. No functional issue — purely cosmetic/style.
  - **Fix**: Use `hmac.new(key, payload.encode(), hashlib.sha256)` — this is actually fine as written; however, document that `hmac.new` is the documented public API in Python 3.6+ per the stdlib source.

- **[P3-02] `AgentService` docstring references "Gemini 2.5 Flash" but code uses "gemini-3-flash-preview"**
  - **File**: `backend/services/agent_service.py` line 6
  - **Description**: The module docstring reads `Primary: Gemini 2.5 Flash (free tier)` but the actual model ID used at line 197 and 267 is `"gemini-3-flash-preview"`. The MEMORY.md also refers to "Gemini 3 Flash Preview". The docstring is stale.
  - **Fix**: Update the module docstring to `Primary: Gemini 3 Flash Preview (gemini-3-flash-preview)`.

- **[P3-03] `QUERY_TIMEOUT_SECONDS = 120` with no upper bound on `max_results` in `weekly_market_scan`**
  - **File**: `backend/services/market_intelligence_service.py` lines 54–73
  - **Description**: `weekly_market_scan` iterates sequentially over up to 10 queries with no overall timeout. Each `search_energy_news` call has a 15-second httpx timeout, so the worst case is 150 seconds total. There is no outer timeout guard and the cron workflow (`market-research.yml`) uses the `retry-curl` composite action which does not help here (the timeout is in the Python process, not the curl call).
  - **Impact**: No outage risk; the cron job will simply take longer than expected. Low severity.
  - **Fix**: Add `asyncio.gather` for the 10 queries with a shared semaphore (1–2 concurrent, per Tavily free-tier rate limits) to reduce total wall time.

- **[P3-04] Silent exception swallowing in attachment download**
  - **File**: `backend/services/email_scanner_service.py` lines 340–342, 386–387
  - **Description**: Both `download_gmail_attachments` and `download_outlook_attachments` use bare `except Exception: continue` to skip failed attachment downloads. There is no log statement in either catch block.
  - **Impact**: Attachment download failures are invisible in logs — no way to distinguish a persistent API error from an occasional network hiccup without adding instrumentation.
  - **Fix**: Add `logger.warning("attachment_download_failed", filename=meta.get("filename"), error=str(e))` in both except blocks.

- **[P3-05] `PortalConnectionResponse` leaks the plaintext portal username**
  - **File**: `backend/api/v1/connections/portal_scrape.py` line 143; `backend/models/connections.py` lines 268–276
  - **Description**: `PortalConnectionResponse` includes `portal_username: str` (line 273 of connections.py) and the create endpoint returns `portal_username=payload.portal_username` (line 143 of portal_scrape.py) — the plaintext username before encryption. While the password is correctly omitted, returning the username verbatim in the API response means the username is stored in browser history, logging middleware, and any API client that caches responses.
  - **Impact**: Utility portal usernames (typically email addresses) are exposed in API responses, a minor data minimization concern under GDPR.
  - **Fix**: Either omit `portal_username` from the response entirely or return a masked version (e.g., `user***@example.com`). The stored encrypted username can still be used server-side.

- **[P3-06] Dead constant `MAX_TOOL_ITERATIONS = 30` is never referenced**
  - **File**: `backend/services/agent_service.py` line 38
  - **Description**: `MAX_TOOL_ITERATIONS = 30` is defined but no tool-calling loop exists in the current implementation (Composio tools are initialized but the streaming path does not iterate tool calls). The constant is vestigial from a planned multi-turn tool-use implementation.
  - **Fix**: Remove the constant or add a TODO comment tying it to the planned Composio tool integration.

---

### Statistics

- **Files audited**: 10
  - `backend/services/stripe_service.py`
  - `backend/services/email_service.py`
  - `backend/services/email_scanner_service.py`
  - `backend/services/email_oauth_service.py`
  - `backend/services/portal_scraper_service.py`
  - `backend/services/agent_service.py`
  - `backend/services/push_notification_service.py`
  - `backend/services/geocoding_service.py`
  - `backend/services/weather_service.py`
  - `backend/services/market_intelligence_service.py`
  - *(Supporting files reviewed: `billing.py`, `portal_scrape.py` API layer, `webhooks.py`, `connections.py` models)*

- **Total findings**: 15 (P0: 1, P1: 5, P2: 7, P3: 6 — P3-01 is a near-false-positive counted for completeness)

| Severity | Count | Finding IDs |
|----------|-------|-------------|
| P0 Critical | 1 | P0-01 |
| P1 High | 5 | P1-01 through P1-05 |
| P2 Medium | 7 | P2-01 through P2-07 |
| P3 Low | 6 | P3-01 through P3-06 |

### Positive Observations

The following patterns are done well and should be preserved:

1. **Stripe webhook signature verification** (`stripe_service.py` lines 327–355 + `billing.py` lines 365–376): Raw bytes are verified against `Stripe-Signature` before any event data is deserialized. The API layer correctly returns 200 to Stripe after processing errors to prevent indefinite retries.
2. **Redirect URL allowlisting** (`billing.py` lines 37–51): `success_url` and `cancel_url` are validated against `settings.allowed_redirect_domains` at the Pydantic layer — open redirect is not possible via the Stripe checkout flow.
3. **AES-256-GCM credential encryption** (`portal_scrape.py` lines 91–94): Portal passwords are encrypted before storage and decrypted only at scrape time; plaintext is never logged.
4. **HMAC-signed OAuth state** (`email_oauth_service.py` lines 38–65): CSRF protection uses constant-time comparison (`hmac.compare_digest`) with a random nonce — correct implementation apart from the missing expiry (P1-01).
5. **IDOR prevention on async jobs** (`agent_service.py` lines 344–370): `get_job_result` verifies `job_owner == user_id` before returning results — correctly prevents cross-user job enumeration.
6. **Thread-safe Stripe API calls** (`stripe_service.py`): All blocking Stripe SDK calls are wrapped in `asyncio.to_thread` — event loop is not blocked.
