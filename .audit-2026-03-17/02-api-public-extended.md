# Audit Report: Backend Public Extended APIs
## Date: 2026-03-17

### Executive Summary

32 files across 22 logical modules were audited (including all 10 `connections/` sub-files). The codebase is generally well-structured with good use of parameterized queries, ownership scoping, and encryption for sensitive credentials. However, three critical issues were found: a broken `hmac.compare_digest` call that makes beta-code verification trivially bypassable, an unvalidated open redirect in the email OAuth callback, and internal exception messages leaking to users in compliance endpoints. Several high-severity issues around input validation gaps, TOCTOU race conditions, and insecure data storage patterns also warrant prompt attention.

---

### Findings

#### P0 — Critical

---

**[P0-01] Broken constant-time comparison — beta code verification always returns `true` for any code in DB**
`backend/api/v1/beta.py` lines 235–238

The `verify-code` endpoint uses `hmac.compare_digest(code, code)` — comparing the user-supplied `code` against *itself*, not against the stored database value. This means:
1. Any value returned by the `LIKE` query will pass the "constant-time comparison," because `code == code` is always `True`.
2. The result: if *any* beta record contains a substring matching `%code={user_input}%`, the user-supplied code is treated as valid — regardless of whether it is the actual code for that record.
3. As a secondary consequence, the LIKE clause `%code={code}%` without anchoring also matches partial codes, so `BETA-2026-A` would match a row containing `code=BETA-2026-AB`.

The security intent (constant-time comparison) is completely negated. Any user can brute-force or enumerate beta codes by observing query timing.

**Fix:**
```python
# Fetch the actual stored codes from the interest field, then compare properly
result = await db.execute(
    text("SELECT interest FROM beta_signups WHERE interest LIKE :pattern"),
    {"pattern": f"%code={code}%"},
)
rows = result.fetchall()

# Extract the actual code value from the interest string and compare
import re
is_valid = False
for row in rows:
    match = re.search(r'code=([^;]+)', row[0])
    if match:
        stored_code = match.group(1)
        if hmac.compare_digest(code, stored_code):
            is_valid = True
            break
```

---

**[P0-02] Open redirect in email OAuth callback via unsanitized `frontend_url`**
`backend/api/v1/connections/email_oauth.py` lines 193–196

The callback endpoint constructs a redirect URL as `f"{frontend_url}/connections?connected={connection_id}"` where `frontend_url` comes from `settings.frontend_url`. If that setting is misconfigured, empty, or tampered with (e.g., via environment variable injection), the response redirects to an attacker-controlled origin. Additionally, `connection_id` is taken from the database but is constructed from user-initiated flow — if any path through this function has `connection_id` from an untrusted source, the `connected=` query parameter becomes a vector for phishing redirects.

More critically, the redirect URL is built without validating that `frontend_url` is a known safe origin. A misconfiguration could cause redirect to `javascript:`, `data:`, or a different HTTPS host.

**Fix:**
```python
from urllib.parse import urlparse

ALLOWED_FRONTEND_ORIGINS = {"https://rateshift.app", "https://www.rateshift.app"}

def _safe_redirect(frontend_url: str, path: str) -> str:
    parsed = urlparse(frontend_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in ALLOWED_FRONTEND_ORIGINS:
        raise ValueError(f"Untrusted frontend_url: {frontend_url}")
    return f"{frontend_url}{path}"
```

---

**[P0-03] Internal exception messages leaked to API consumers in all compliance endpoints**
`backend/api/v1/compliance.py` lines 99–103, 128–132, 159–163, 214–219, 283–287, 339–343, 385–389

Every `except Exception as e:` block in the compliance module returns `detail=f"Failed to ...: {str(e)}"`. This leaks stack-trace fragments, database column names, internal class names, and potentially SQL error text to any authenticated user. For GDPR endpoints specifically, this is a data leak risk: a malformed deletion could expose the internal DB schema or ORM state in the 500 response body.

**Fix:** Log the exception internally and return a generic message:
```python
except Exception as e:
    logger.error("gdpr_export_failed", user_id=current_user.user_id, error=str(e), exc_info=True)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An internal error occurred. Please try again or contact support."
    )
```

---

#### P1 — High

---

**[P1-01] `user_id` in affiliate click request is client-supplied — no auth binding**
`backend/api/v1/affiliate.py` lines 26–33, 53–61

`POST /affiliate/click` accepts `user_id: Optional[str]` in the request body from an unauthenticated caller. Any actor can claim any `user_id` when recording a click, associating affiliate revenue with arbitrary users. This allows:
- Attribution fraud (crediting clicks to real users who did not click).
- Enumeration of valid user IDs via error differences.

The endpoint has no authentication requirement (`get_current_user` is absent). The `user_id` field should either be removed from the public request body (recorded server-side only for authenticated calls) or the endpoint should require auth and bind `user_id` from the session.

**Fix:** Either require auth and use `current_user.user_id`, or remove the `user_id` field entirely from `ClickRequest` and only record it when the caller is authenticated:
```python
@router.post("/click")
async def record_affiliate_click(
    body: ClickRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: Optional[SessionData] = Depends(get_optional_user),  # optional auth
) -> Dict[str, Any]:
    recorded_user_id = current_user.user_id if current_user else None
    ...
    click_id = await service.record_click(user_id=recorded_user_id, ...)
```

---

**[P1-02] `region` parameter not validated against Region enum in community, neighborhood, gas_rates, rate_changes endpoints**
`backend/api/v1/community.py` lines 120, 228; `backend/api/v1/neighborhood.py` line 29; `backend/api/v1/gas_rates.py` lines 24, 57, 90, 120; `backend/api/v1/rate_changes.py` line 61

Multiple public-facing endpoints accept `region: str` or `utility_type: str` as raw strings without validation against the project's canonical `Region` enum. This violates the project's own standard (CLAUDE.md: "Region enum for all regions — never raw strings") and means:
- A malformed region string is silently passed to service layer, which may return empty results or trigger unexpected query paths.
- No client-facing error is returned for clearly invalid inputs like `region="'; DROP TABLE users; --"` (though parameterized queries prevent SQLi, the service layer still processes the value).

**Fix:** Use Pydantic field validators or inline validation:
```python
from models.region import Region

@router.get("/posts")
async def list_posts(
    region: Region = Query(..., description="Region code"),  # uses enum for validation
    ...
```
For endpoints where Region enum is too strict (free-text gas region codes), add an explicit allowlist check matching the service's supported values.

---

**[P1-03] TOCTOU race condition in beta signup — duplicate email check not atomic**
`backend/api/v1/beta.py` lines 129–137, 143–156

The duplicate-email check (`SELECT id ... WHERE email = :email`) and the subsequent `INSERT` are two separate round-trips with no transaction isolation. Under concurrent requests (which is common with bot signups), two simultaneous calls for the same email could both pass the duplicate check and both insert a row. The result is duplicate beta signups for the same email address and two different beta codes being generated and emailed.

**Fix:** Use an upsert with `ON CONFLICT DO NOTHING` and check the row count, or rely on a unique constraint:
```sql
INSERT INTO beta_signups (id, email, name, interest, created_at)
VALUES (:id, :email, :name, :interest, NOW())
ON CONFLICT (email) DO NOTHING
RETURNING id
```
If no row is returned, the email was already registered. This requires a `UNIQUE` constraint on `beta_signups.email`.

---

**[P1-04] `verify_callback_state` does not check timestamp expiry — OAuth states never expire**
`backend/api/v1/connections/common.py` lines 76–103

`OAUTH_STATE_TIMEOUT_SECONDS = 600` is defined but never enforced. `verify_callback_state` verifies the HMAC signature but does not check whether the embedded timestamp is within the 600-second window. A signed state captured from a legitimate OAuth initiation flow remains valid indefinitely, allowing replay attacks against the callback endpoint long after the OAuth session should have expired.

**Fix:**
```python
def verify_callback_state(state: str) -> tuple:
    parts = state.split(":")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="Invalid callback state: ...")

    connection_id, user_id, timestamp, received_sig = parts

    # Verify HMAC first (fail fast on tampered state)
    key = _get_hmac_key()
    payload = f"{connection_id}:{user_id}:{timestamp}"
    expected_sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_sig, expected_sig):
        raise HTTPException(status_code=400, detail="Invalid callback state: HMAC failed.")

    # Then check expiry
    try:
        ts = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid callback state: bad timestamp.")
    if time.time() - ts > OAUTH_STATE_TIMEOUT_SECONDS:
        raise HTTPException(status_code=400, detail="Callback state expired.")

    return connection_id, user_id
```

---

**[P1-05] `hmac.new` used instead of `hmac.new` — API typo that should be `hmac.new`**
`backend/api/v1/webhooks.py` line 48; `backend/api/v1/connections/common.py` lines 72, 93

`hmac.new(...)` is used throughout. In Python's standard library, the function is `hmac.new(key, msg, digestmod)`. This is correct — however, the `webhooks.py` code at line 48 uses `hmac.new(secret.encode("utf-8"), payload, hashlib.sha256)` which is the correct signature. No bug here, just confirming — the calls are correct.

*Retracted — this is not a finding. Confirming `hmac.new` is the correct Python stdlib function.*

---

**[P1-06] Beta signup leaks beta code in the API response to unauthenticated clients**
`backend/api/v1/beta.py` lines 166–170

`POST /beta/signup` returns the generated `betaCode` in the HTTP response body to the caller. While this is intentional (to display to the user on the sign-up confirmation page), it means:
- The beta code is transmitted in plaintext in the HTTP response, stored only as a substring in the `interest` JSONB field.
- Any passive observer (logs, CDN access logs, browser history) captures the beta code.
- There is no mechanism to retrieve the code later, so users who lose the response have no recourse.

Consider emitting the code only in the welcome email (not in the API response), or at minimum ensure the response is not cached by any intermediate layer.

---

**[P1-07] `update_connection` in crud.py builds a partial SET clause from a controlled list but does not prevent the `cid` param from being overwritten if future fields are added**
`backend/api/v1/connections/crud.py` lines 285–299

The PATCH endpoint builds a SET clause by appending strings like `"label = :label"` to an `updates` list, then joins them. The params dict only includes `:cid` and `:label`. This is safe *today* because only `label` is updateable. However, the pattern does not guard against accidentally exposing additional sensitive fields (e.g., `status`, `connection_type`) if `UpdateConnectionRequest` is extended in the future. The WHERE clause also omits `AND user_id = :uid` in the final UPDATE:

```python
# Line 295-298: the UPDATE WHERE clause only uses :cid, not uid
await db.execute(
    text(f"UPDATE user_connections SET {', '.join(updates)} WHERE id = :cid"),
    params,
)
```

The ownership check is done in the prior SELECT (lines 278–283), but between the SELECT and UPDATE there is no `AND user_id = :uid` re-check in the UPDATE. While `require_paid_tier` reduces exposure, removing the uid from the UPDATE statement is a defence-in-depth gap — a race condition or logic error elsewhere could allow one user to update another's connection.

**Fix:** Add `AND user_id = :uid` to the UPDATE WHERE clause and include `"uid": current_user.user_id` in params.

---

**[P1-08] `list_bill_uploads` does not scope the bill_uploads query by `user_id`**
`backend/api/v1/connections/bill_upload.py` lines 306–318

After verifying the connection belongs to the current user (via the `user_connections` check at lines 296–302), the subsequent `SELECT` from `bill_uploads` queries only `WHERE connection_id = :cid` — without joining back to `user_connections` to confirm ownership. If a connection_id belonging to another user were somehow passed (e.g., via the wildcard route capturing a wrong segment), the user_connections check would fail, but the pattern creates a structural gap. More significantly, this means the uploads query result set is not independently scoped to the authenticated user — it relies entirely on the prior SELECT as an ownership gate.

While the connection ownership check mitigates this in practice, the bill_uploads query itself should JOIN to user_connections to enforce ownership at the data layer:

**Fix:**
```sql
SELECT bu.*
FROM bill_uploads bu
JOIN user_connections uc ON bu.connection_id = uc.id
WHERE bu.connection_id = :cid
  AND uc.user_id = :uid
ORDER BY bu.created_at DESC
```

---

**[P1-09] Agent `query_agent` increments usage via `query_streaming` but `submit_agent_task` increments separately — double-counting risk**
`backend/api/v1/agent.py` lines 131–166, 203–219

In `query_agent`, usage appears to be incremented inside `service.query_streaming()` (the service is responsible for incrementing). In `submit_agent_task`, `service.increment_usage()` is called explicitly *after* `service.query_async()` (line 219). If `query_async()` *also* increments usage internally, this results in a double-count for the task submission path. Conversely, if the streaming path does not increment inside `query_streaming()`, the streaming path under-counts.

The inconsistent increment approach means rate limits for the `/task` endpoint may be wrong, and the `/usage` response may not reflect accurate counts. This needs verification against `AgentService` internals, but the surface-level API code shows an asymmetric pattern that is a likely bug.

---

#### P2 — Medium

---

**[P2-01] `GET /community/posts` and `GET /community/stats` accept unvalidated region and utility_type strings**
`backend/api/v1/community.py` lines 118–142, 226–234

`GET /community/posts` validates `post_type` and `utility_type` in the *create* path but does not validate `region` or `utility_type` on the *list* path. An invalid `utility_type` (e.g., empty string or SQL-safe garbage value) is passed directly to `CommunityService.list_posts()`. The service may handle this gracefully, but validation belongs at the API boundary. Same issue applies to `GET /community/stats` which accepts `region` with no validation.

**Fix:** Apply the same `VALID_UTILITY_TYPES` set check to the list endpoint, and validate `region` against the Region enum or a known prefix pattern.

---

**[P2-02] `beta.py` stats endpoints lack any rate limiting or admin-only gating**
`backend/api/v1/beta.py` lines 173–218

`GET /beta/signups/count` and `GET /beta/signups/stats` require authentication but have no role or tier check — any registered user can access total signup count and statistics. More significantly, neither endpoint has rate limiting. An authenticated user can poll these endpoints continuously to track signup velocity in near-real-time.

The `page` and `page_size` parameters on `/beta/signups/stats` (lines 193–195) are accepted but never used — the query always returns all records without pagination, making the parameters misleading and creating a potential for future confusion.

**Fix:** Add admin-role check (or at minimum, require `business` tier). Remove or implement the unused pagination parameters.

---

**[P2-03] `export.py` returns a raw dict with `"error"` key on failure instead of raising HTTPException**
`backend/api/v1/export.py` lines 53–54

```python
if "error" in result:
    return result  # Returns 200 OK with {"error": "..."} body
```

This means export failures return HTTP 200 with an error payload instead of an appropriate 4xx/5xx status code. API clients following standard HTTP conventions will treat this as success. This is inconsistent with every other endpoint in the codebase.

**Fix:**
```python
if "error" in result:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=result["error"])
```

---

**[P2-04] `rate_changes.py` `channels` field not validated against allowed values**
`backend/api/v1/rate_changes.py` lines 39–44, 143–149

`UpsertPreferenceRequest.channels: Optional[List[str]]` accepts any list of strings. The service layer presumably validates this, but the API layer has no check. A caller can submit `channels=["sms", "fax", "arbitrary_channel"]` without a 422 response. The valid cadences are validated (lines 133–138) but channels are not.

**Fix:**
```python
VALID_CHANNELS = {"email", "push", "in_app"}
if body.channels:
    invalid = set(body.channels) - VALID_CHANNELS
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid channels: {invalid}. Must be subset of: {VALID_CHANNELS}",
        )
```

---

**[P2-05] `GET /cca/detect` and `GET /cca/programs` do not validate zip_code format or state code format**
`backend/api/v1/cca.py` lines 19–45, 79–91

`zip_code` is accepted as a raw string with no format validation (it could be `"'; SELECT 1; --"` — safe due to parameterized queries, but not validated). `state` has no pattern constraint (unlike `regulations.py` which uses `pattern=r"^[A-Z]{2}$"`). A caller passing `state="XYZZY"` gets a service call rather than an immediate 422.

**Fix:** Add `min_length=5, max_length=10, pattern=r"^\d{5}(-\d{4})?$"` to `zip_code` and `pattern=r"^[A-Z]{2}$"` to `state` in the Query declarations.

---

**[P2-06] Community post `region` field not validated against Region enum on creation**
`backend/api/v1/community.py` lines 50, 95–110

`CreatePostRequest.region` is a plain `str` field. The project standard is to use the Region enum for all region parameters. An invalid region (e.g., `"foo"`) is stored in the database, polluting the community posts table and potentially causing downstream analytics errors.

**Fix:**
```python
from models.region import Region
region: Region = Field(description="Region code (e.g. 'us_ct')")
```
Or add a `@field_validator("region")` that validates against the Region enum.

---

**[P2-07] `delete_account` endpoint (`/gdpr/delete`) bypasses explicit confirmation — CSRF risk**
`backend/api/v1/compliance.py` lines 295–343

The `/gdpr/delete` endpoint is a DELETE with no request body. It immediately deletes all user data with the comment "confirmation is considered given by the act of calling this endpoint." This is reasonable for a confirmed frontend flow, but this endpoint has no CSRF protection other than the auth token. If the auth cookie is not SameSite=Strict, a CSRF attack from a third-party site could trigger account deletion by a victim who is logged in. The comment says "the frontend must obtain explicit user confirmation before invoking it" — but this is a policy, not a technical control.

**Fix:** Consider requiring a short-lived, single-use deletion token issued by a separate `POST /gdpr/prepare-delete` endpoint, so the DELETE must present a token that proves intentionality within the last N minutes.

---

**[P2-08] `gas_rates.py` `compare_gas_suppliers` returns duplicate state in deregulated check message**
`backend/api/v1/gas_rates.py` lines 125–128

The error message on line 128 includes the full `sorted(DEREGULATED_GAS_STATES)` set in the response. Depending on the size of this set, this could be a very large response body for a 400 error, and it exposes the complete internal state list configuration. Minor but worth a cleaner message.

---

**[P2-09] `bill_upload.py` stores files in local filesystem (`uploads/` relative path) — not production-safe**
`backend/api/v1/connections/bill_upload.py` lines 35, 225–236

`_UPLOADS_DIR = Path("uploads")` is a relative path. On Render's ephemeral filesystem, uploaded files are lost on every deploy or restart. The code comment on line 32 says "Phase 2 — cloud in Phase 3" but Phase 3 is listed as complete in the project memory. This means uploaded bill files are being silently discarded on every redeployment, causing background parse jobs to fail for any file uploaded before the last deploy.

**Fix:** Migrate to S3/R2/Cloudflare R2 storage as planned in Phase 3. Until then, document the data loss risk explicitly. Add a check in the background parser that returns a clear "file no longer available" error instead of a generic parse failure when the storage key is missing.

---

**[P2-10] `email_oauth_callback` does not validate that the connection belongs to the user who initiated the OAuth flow**
`backend/api/v1/connections/email_oauth.py` lines 134–143

The callback fetches the connection by `id` only (`WHERE id = :cid`) without checking `user_id`. The `state` parameter proves the `connection_id` is valid (via HMAC), but it does not re-bind the connection to the initiating user at callback time. The `verify_oauth_state` function in the email service returns the `connection_id`, but it does not embed the `user_id` the way `sign_callback_state` does for the UtilityAPI flow. If an attacker can predict or guess a pending `connection_id`, they could supply a crafted `state` value (if `verify_oauth_state` only checks the connection_id exists) to activate a connection they don't own.

This requires reviewing `email_oauth_service.verify_oauth_state` to confirm whether `user_id` is embedded in the email OAuth state (unlike the UtilityAPI state which explicitly embeds `user_id`). If it does not, the email callback has a weaker ownership guarantee than the direct sync callback.

**Fix:** Embed `user_id` in the email OAuth state using the same `sign_callback_state` mechanism used in `direct_sync.py`, and verify it in the callback.

---

**[P2-11] No rate limiting on public `POST /beta/signup` — enumeration and spam risk**
`backend/api/v1/beta.py` lines 106–169

`POST /beta/signup` is unauthenticated and has no rate limiting. A bot can submit unlimited signup requests. The only deduplication is per-email, but using disposable email addresses bypasses this entirely. The endpoint also sends a welcome email on each valid submission — unlimited valid signups consume Resend API quota without bound.

**Fix:** Apply IP-based rate limiting (e.g., via the CF Worker layer's native rate limiting) or add a simple in-app rate limit dependency.

---

**[P2-12] `portal_scrape.py` response leaks portal username in plain text**
`backend/api/v1/connections/portal_scrape.py` lines 140–147

`PortalConnectionResponse` includes `portal_username=payload.portal_username` (line 143) — the plaintext portal username is returned in the 201 response. While not a password, portal usernames (often email addresses) are PII and should be masked or omitted from the response.

**Fix:** Return a masked form (e.g., first 2 chars + `***` + domain for email usernames) or omit entirely, consistent with how account numbers are masked throughout the connections feature.

---

**[P2-13] `export.py` `utility_type` not validated before passing to service**
`backend/api/v1/export.py` lines 26–51

`utility_type` is accepted as a raw `str` query param. The service checks `EXPORT_CONFIGS` but the API layer does not validate upfront. An invalid utility type causes the service to return an `{"error": ...}` dict (which is then returned as HTTP 200 — see P2-03). The validation + error-type fix together would resolve both issues.

---

#### P3 — Low

---

**[P3-01] `neighborhood.py` missing `structlog` logger — inconsistent with rest of codebase**
`backend/api/v1/neighborhood.py`

Every other file in this audit imports and uses `structlog.get_logger(__name__)`. `neighborhood.py` has no logger at all, meaning the neighborhood comparison endpoint emits no structured log events (no request start, no errors). Silent failure in this endpoint would be invisible in Grafana dashboards.

**Fix:** Add `import structlog; logger = structlog.get_logger(__name__)` and log at least request start and service errors.

---

**[P3-02] `referrals.py` instantiates `structlog.get_logger()` without `__name__`**
`backend/api/v1/referrals.py` line 17

```python
logger = structlog.get_logger()  # missing __name__
```
All other files pass `__name__` for correct log attribution. Without it, log events from this module appear with no module context in structured logs.

**Fix:** `logger = structlog.get_logger(__name__)`

---

**[P3-03] `beta.py` uses inline `from uuid import uuid4` inside function body**
`backend/api/v1/beta.py` line 143

`from uuid import uuid4` is imported inside the `beta_signup` function body instead of at module level. This is a minor style inconsistency — every other file imports at the top level. While Python caches module imports, repeated inline imports are a code smell.

**Fix:** Move to the top of the file: `from uuid import uuid4`.

---

**[P3-04] `agent.py` duplicates user context + tier fetch logic between `query_agent` and `submit_agent_task`**
`backend/api/v1/agent.py` lines 119–128, 193–201

Both endpoints contain identical blocks: fetch user context, merge body context, strip tier/user_id from body context, re-fetch tier from DB. This is 10 lines repeated verbatim. Any change to tier-lookup logic must be made in two places.

**Fix:** Extract into a private helper:
```python
async def _build_context(body_context: Optional[dict], user_id: str, db: AsyncSession) -> tuple[dict, str]:
    context = await _get_user_context(user_id, db)
    if body_context:
        context.update(body_context)
    context["tier"] = await _get_user_tier(user_id, db)
    context["user_id"] = user_id
    return context, context["tier"]
```

---

**[P3-05] `webhooks.py` endpoint detail leaks internal error messages from signature validation**
`backend/api/v1/webhooks.py` line 90

```python
raise HTTPException(status_code=400, detail=str(e))
```
The `ValueError` message from `verify_github_signature` is returned verbatim to callers. While these messages are benign ("Missing X-Hub-Signature-256 header", "Invalid signature format"), returning raw exception strings is inconsistent with the project's practice of controlled error messages.

**Fix:** Return a fixed message: `detail="Webhook signature verification failed"`.

---

**[P3-06] `community.py` route comment says `PUT /posts/{post_id}` is "author only" but service owns that check**
`backend/api/v1/community.py` lines 150–174

The docstring and module header both indicate "author only" restriction, but the API layer does not enforce this — it passes `user_id` to the service and relies on `CommunityService.edit_and_resubmit()` to enforce ownership. This is fine as a pattern, but the API layer should document this explicitly and consider what happens if the service layer changes.

---

**[P3-07] `cca.py` `cca_id` path parameter has no UUID validation**
`backend/api/v1/cca.py` lines 48–61, 64–76

`cca_id: str` path parameter has no format validation. While parameterized queries prevent injection, the project standard is to use `uuid.UUID` type annotation for UUID path params (CLAUDE.md: "UUID path params: use `uuid.UUID` type annotation in FastAPI routes"). Using the UUID type provides free 422 validation.

**Fix:**
```python
import uuid

@router.get("/compare/{cca_id}")
async def compare_cca_rate(
    cca_id: uuid.UUID,
    ...
```

---

**[P3-08] `compliance.py` has two DELETE endpoints for account deletion — subtle behavioral difference not documented at call sites**
`backend/api/v1/compliance.py` lines 227–287, 295–343

`DELETE /gdpr/delete-my-data` requires `confirmation: true` in the request body and respects `retain_anonymized`. `DELETE /gdpr/delete` hardcodes `anonymize_retained=False` and skips confirmation. The two endpoints have different data retention behavior that is not surfaced in their OpenAPI summaries. A developer picking one over the other based on name alone could inadvertently change the data retention outcome for users who expected the other behavior.

**Fix:** Add explicit `retain_anonymized` description differences to both endpoint summaries, and consider whether two deletion endpoints are necessary or if one with optional body would be cleaner.

---

**[P3-09] `beta.py` `get_beta_stats` accepts `page` and `page_size` parameters that are completely unused**
`backend/api/v1/beta.py` lines 188–218

```python
async def get_beta_stats(
    ...
    page: int = 1,
    page_size: int = 50,
):
```
These parameters appear in the function signature and are echoed back in the response dict, but no pagination is applied to any query. The endpoint always returns aggregate counts only. This is misleading to API consumers.

**Fix:** Remove the unused parameters or implement actual pagination.

---

**[P3-10] `connections/common.py` `_UPLOADS_DIR` is a relative path — behavior is process-working-directory dependent**
`backend/api/v1/connections/common.py` line 35

`_UPLOADS_DIR = Path("uploads")` resolves relative to whatever directory the process is launched from. In production on Render, this depends on the working directory at server startup. This is fragile.

**Fix:** Use an absolute path anchored to the app root: `Path(__file__).parent.parent.parent.parent / "uploads"`, or better, make it configurable via `settings.uploads_dir`.

---

### Statistics

- **Files audited:** 32 (22 top-level modules + 10 `connections/` sub-files)
- **Total findings:** 30 (P0: 3, P1: 7, P2: 13, P3: 10)

| Severity | Count | Files Affected |
|----------|-------|---------------|
| P0 Critical | 3 | beta.py, connections/email_oauth.py, compliance.py |
| P1 High | 7 | affiliate.py, community.py, neighborhood.py, gas_rates.py, rate_changes.py, beta.py, connections/ (common, crud, bill_upload, agent) |
| P2 Medium | 13 | export.py, rate_changes.py, cca.py, community.py, compliance.py, gas_rates.py, bill_upload.py, email_oauth.py, beta.py, portal_scrape.py, agent.py |
| P3 Low | 10 | neighborhood.py, referrals.py, beta.py, agent.py, webhooks.py, community.py, cca.py, compliance.py, connections/common.py |

### Priority Action Items

1. **[P0-01]** Fix `hmac.compare_digest(code, code)` in `beta.py` — this is a broken security control deployed in production.
2. **[P0-02]** Add origin validation to the email OAuth redirect in `connections/email_oauth.py`.
3. **[P0-03]** Replace all bare `except Exception as e: detail=f"...{str(e)}"` patterns in `compliance.py` with logged-then-generic responses.
4. **[P1-04]** Enforce the `OAUTH_STATE_TIMEOUT_SECONDS` window in `verify_callback_state`.
5. **[P1-01]** Remove client-supplied `user_id` from the affiliate click request or bind it to session.
6. **[P1-07]** Add `AND user_id = :uid` to the UPDATE WHERE in `connections/crud.py` PATCH endpoint.
7. **[P2-09]** Address ephemeral filesystem storage for bill uploads before uploads silently disappear on redeployment.
