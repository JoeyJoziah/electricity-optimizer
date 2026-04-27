"""
Gmail / Outlook OAuth initiation and callback endpoints.

Routes (mounted under the /connections prefix in router.py):
  POST /email                         — initiate an email-import connection (returns OAuth redirect URL)
  GET  /email/callback                — handle OAuth redirect from Gmail/Outlook
  POST /email/{connection_id}/scan    — trigger an email inbox scan

IMPORTANT: /email/callback and /email/{connection_id}/scan MUST be registered
before /{connection_id} wildcard routes in router.py so FastAPI does not
capture "email" as a connection_id path parameter.
"""

import uuid
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from api.dependencies import SessionData, get_db_session
from api.v1.connections.common import require_paid_tier
from models.connections import (
    CreateEmailConnectionRequest,
    EmailConnectionInitResponse,
    EmailScanResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /email  —  start an email-import connection
# ---------------------------------------------------------------------------


@router.post(
    "/email",
    response_model=EmailConnectionInitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start email-import connection",
)
async def create_email_connection(
    payload: CreateEmailConnectionRequest,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> EmailConnectionInitResponse:
    """
    Initiate an email-import connection.
    Creates a pending connection and returns the OAuth consent URL.
    """
    from services.email_oauth_service import (
        get_gmail_consent_url,
        get_outlook_consent_url,
    )
    from services.email_oauth_service import (
        settings as _oauth_settings,
    )

    # Fail fast if OAuth credentials are not configured for the requested provider
    if payload.provider == "gmail":
        if not _oauth_settings.gmail_client_id or not _oauth_settings.gmail_client_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gmail connection is not yet configured. Please try bill upload instead.",
            )
    else:
        if not _oauth_settings.outlook_client_id or not _oauth_settings.outlook_client_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Outlook connection is not yet configured. Please try bill upload instead.",
            )

    connection_id = str(uuid4())

    if payload.provider == "gmail":
        redirect_url = get_gmail_consent_url(connection_id, user_id=current_user.user_id)
    else:
        redirect_url = get_outlook_consent_url(connection_id, user_id=current_user.user_id)

    await db.execute(
        text("""
            INSERT INTO user_connections
                (id, user_id, connection_type, email_provider, status, created_at)
            VALUES
                (:id, :uid, 'email_import', :provider, 'pending', NOW())
        """),
        {"id": connection_id, "uid": current_user.user_id, "provider": payload.provider},
    )
    await db.commit()

    return EmailConnectionInitResponse(
        connection_id=connection_id,
        redirect_url=redirect_url,
        provider=payload.provider,
    )


# ---------------------------------------------------------------------------
# GET /email/callback  —  OAuth callback from Gmail/Outlook
# ---------------------------------------------------------------------------

# NOTE: This endpoint must be registered BEFORE /{connection_id} routes so
# that FastAPI does not capture "email" as a connection_id path parameter.


@router.get(
    "/email/callback",
    summary="OAuth callback for email providers",
)
async def email_oauth_callback(
    code: str = Query(..., description="Authorization code from OAuth provider"),
    state: str = Query(..., description="Signed state parameter"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Handle OAuth redirect from Gmail/Outlook.
    Exchanges code for tokens, encrypts and stores them,
    then redirects to the frontend connections page.
    """
    import httpx as _httpx

    from services.email_oauth_service import (
        encrypt_tokens,
        exchange_gmail_code,
        exchange_outlook_code,
        verify_oauth_state,
    )

    # Verify state (includes timestamp expiry and HMAC integrity)
    connection_id, state_user_id = verify_oauth_state(state)
    if not connection_id:
        raise HTTPException(status_code=400, detail="Invalid or tampered OAuth state")

    # Look up connection (include user_id for ownership verification)
    result = await db.execute(
        text("SELECT id, user_id, email_provider, status FROM user_connections WHERE id = :cid"),
        {"cid": connection_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Connection not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="Connection already processed")

    # Ownership check: the user_id embedded in the signed state must match
    # the user_id stored in the DB when the connection was created.  This
    # prevents user A from consuming user B's OAuth callback URL.
    if state_user_id and row["user_id"] and state_user_id != row["user_id"]:
        logger.warning(
            "oauth_callback_ownership_mismatch",
            connection_id=connection_id,
            state_user_id=state_user_id,
            db_user_id=row["user_id"],
        )
        raise HTTPException(
            status_code=403, detail="OAuth state does not belong to this connection"
        )

    provider = row["email_provider"]

    try:
        if provider == "gmail":
            token_data = await exchange_gmail_code(code)
        else:
            token_data = await exchange_outlook_code(code)
    except _httpx.HTTPStatusError:
        await db.execute(
            text("UPDATE user_connections SET status = 'error' WHERE id = :cid"),
            {"cid": connection_id},
        )
        await db.commit()
        raise HTTPException(status_code=502, detail="OAuth token exchange failed")

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)

    # Encrypt tokens
    enc_access, enc_refresh = encrypt_tokens(access_token, refresh_token)

    # Store encrypted tokens as raw BYTEA (no base64 wrapper — migration 059)
    await db.execute(
        text("""
            UPDATE user_connections
            SET status = 'active',
                oauth_access_token = :access,
                oauth_refresh_token = :refresh,
                oauth_token_expires_at = NOW() + make_interval(secs => :expires),
                updated_at = NOW()
            WHERE id = :cid
        """),
        {
            "cid": connection_id,
            "access": enc_access,
            "refresh": enc_refresh,
            "expires": expires_in,
        },
    )
    await db.commit()

    # Redirect to frontend connections page.
    # Access settings through the package namespace so that
    # ``patch("api.v1.connections.settings")`` in tests is observed at call time.
    import api.v1.connections as _pkg

    _settings = _pkg.settings
    frontend_url = (_settings.frontend_url or "").rstrip("/")

    # Validate redirect target to prevent open redirect
    _ALLOWED_FRONTENDS = {
        "https://rateshift.app",
        "https://www.rateshift.app",
        "http://localhost:3000",
        "http://localhost:3001",
    }
    if frontend_url not in _ALLOWED_FRONTENDS:
        logger.warning("oauth_callback_invalid_frontend_url", frontend_url=frontend_url)
        frontend_url = "https://rateshift.app"

    return RedirectResponse(
        url=f"{frontend_url}/connections?connected={connection_id}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# POST /email/{connection_id}/scan  —  trigger email inbox scan
# ---------------------------------------------------------------------------

# NOTE: This endpoint must be registered BEFORE /{connection_id} wildcard
# routes in router.py so "email" is not consumed as a connection_id.


@router.post(
    "/email/{connection_id}/scan",
    response_model=EmailScanResponse,
    summary="Trigger email inbox scan",
)
async def trigger_email_scan(
    connection_id: uuid.UUID,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> EmailScanResponse:
    """Trigger a scan of the connected email inbox for utility bills.

    For each detected utility bill the endpoint:
    1. Extracts rate data from the email body text.
    2. Downloads PDF/image attachments (up to 5 per email) and parses them
       through bill_parser extractors.
    3. Persists all extracted rates into ``connection_extracted_rates``.

    The response includes extraction summary counts so callers can surface
    meaningful feedback without inspecting individual bill records.
    """
    import httpx as _httpx

    from services.email_scanner_service import (
        download_gmail_attachments,
        download_outlook_attachments,
        extract_rates_from_attachments,
        extract_rates_from_email,
        scan_gmail_inbox,
        scan_outlook_inbox,
    )
    from utils.encryption import decrypt_field as _decrypt_field

    result = await db.execute(
        text("""
            SELECT id, user_id, email_provider, status,
                   oauth_access_token, oauth_refresh_token, oauth_token_expires_at
            FROM user_connections
            WHERE id = :cid AND user_id = :uid
        """),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Connection not found")
    if row["status"] != "active":
        raise HTTPException(status_code=409, detail="Connection is not active")

    # Decrypt access token — stored as raw BYTEA (migration 059)
    raw_access = row["oauth_access_token"]
    enc_access = bytes(raw_access) if raw_access is not None else None
    if not enc_access:
        raise HTTPException(status_code=409, detail="No OAuth token found for connection")
    access_token = _decrypt_field(enc_access)

    # Check if token expired and refresh if needed
    if row["oauth_token_expires_at"] and row["oauth_token_expires_at"] < datetime.now(UTC):
        if row["oauth_refresh_token"]:
            from services.email_oauth_service import (
                encrypt_tokens,
                refresh_gmail_token,
                refresh_outlook_token,
            )

            enc_refresh = bytes(row["oauth_refresh_token"])
            try:
                if row["email_provider"] == "gmail":
                    new_tokens = await refresh_gmail_token(enc_refresh)
                else:
                    new_tokens = await refresh_outlook_token(enc_refresh)

                access_token = new_tokens["access_token"]
                new_enc_access, new_enc_refresh = encrypt_tokens(
                    access_token,
                    new_tokens.get("refresh_token"),
                )
                await db.execute(
                    text("""
                        UPDATE user_connections
                        SET oauth_access_token = :access,
                            oauth_refresh_token = COALESCE(:refresh, oauth_refresh_token),
                            oauth_token_expires_at = NOW() + make_interval(secs => :expires),
                            updated_at = NOW()
                        WHERE id = :cid
                    """),
                    {
                        "cid": connection_id,
                        "access": new_enc_access,
                        "refresh": new_enc_refresh,
                        "expires": new_tokens.get("expires_in", 3600),
                    },
                )
                await db.commit()
            except Exception:
                raise HTTPException(status_code=502, detail="Token refresh failed")
        else:
            raise HTTPException(
                status_code=401, detail="Token expired and no refresh token available"
            )

    # Scan inbox
    provider = row["email_provider"]
    try:
        if provider == "gmail":
            scan_results = await scan_gmail_inbox(access_token)
        else:
            scan_results = await scan_outlook_inbox(access_token)
    except _httpx.HTTPStatusError:
        raise HTTPException(status_code=502, detail="Email provider API error")

    # Filter to utility bills only
    utility_bills = [r for r in scan_results if r.is_utility_bill]

    # -----------------------------------------------------------------------
    # Rate extraction and persistence
    # -----------------------------------------------------------------------

    # Collect extracted rates so we can persist them with a single bulk INSERT
    # and one commit at the end. The previous per-row commit pattern produced
    # ~150 round-trips on a 50-bill / 2-attachment scan and left partial state
    # if the loop failed mid-flight (P0-3 / performance QW1).
    extracted_rates: list[dict[str, object]] = []
    attachments_parsed_count = 0

    for bill in utility_bills:
        # 1. Extract rates from email body text
        try:
            body_rates = await extract_rates_from_email(provider, access_token, bill.email_id)
            if body_rates.get("rate_per_kwh") is not None:
                extracted_rates.append(
                    {
                        "id": str(uuid4()),
                        "cid": connection_id,
                        "rate": body_rates["rate_per_kwh"],
                        "source": "email_scan",
                        "label": f"email_body:{bill.email_id}",
                    }
                )
        except Exception as _exc:
            logger.warning(
                "email_scan_body_extraction_failed",
                connection_id=connection_id,
                email_id=bill.email_id,
                error=str(_exc),
            )

        # 2. Download and parse attachments (only if email has any)
        if bill.attachment_count > 0:
            try:
                if provider == "gmail":
                    attachments = await download_gmail_attachments(access_token, bill.email_id)
                else:
                    attachments = await download_outlook_attachments(access_token, bill.email_id)

                if attachments:
                    att_results = await extract_rates_from_attachments(attachments)
                    attachments_parsed_count += len(att_results)

                    for att_result in att_results:
                        rate_val = att_result.get("rate_per_kwh")
                        if rate_val is not None:
                            extracted_rates.append(
                                {
                                    "id": str(uuid4()),
                                    "cid": connection_id,
                                    "rate": rate_val,
                                    "source": "email_attachment",
                                    "label": (
                                        f"email_attachment:{bill.email_id}:"
                                        f"{att_result.get('filename', 'unknown')}"
                                    ),
                                }
                            )
            except Exception as _exc:
                logger.warning(
                    "email_scan_attachment_extraction_failed",
                    connection_id=connection_id,
                    email_id=bill.email_id,
                    error=str(_exc),
                )

    # Single bulk INSERT for the whole scan. SQLAlchemy expands the parameter
    # list into a multi-row VALUES clause when the statement is executed with
    # a list of mappings. ON CONFLICT (id) DO NOTHING is defensive against the
    # rare case of UUID collision on retry.
    rates_extracted_count = 0
    if extracted_rates:
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO connection_extracted_rates
                        (id, connection_id, rate_per_kwh, effective_date, source, raw_label)
                    VALUES
                        (:id, :cid, :rate, NOW(), :source, :label)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                extracted_rates,
            )
            await db.commit()
            rates_extracted_count = len(extracted_rates)
        except Exception as _exc:
            await db.rollback()
            logger.error(
                "email_scan_bulk_persist_failed",
                connection_id=connection_id,
                row_count=len(extracted_rates),
                error=str(_exc),
            )
            # Surface as 502 — the scan succeeded but persistence failed; the
            # client should retry rather than treat the partial state as final.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Email scan completed but rate persistence failed. Please retry.",
            )

    logger.info(
        "email_scan_complete",
        connection_id=connection_id,
        provider=provider,
        total_scanned=len(scan_results),
        utility_bills=len(utility_bills),
        rates_extracted=rates_extracted_count,
        attachments_parsed=attachments_parsed_count,
    )

    return EmailScanResponse(
        connection_id=str(connection_id),
        provider=provider,
        total_emails_scanned=len(scan_results),
        utility_bills_found=len(utility_bills),
        rates_extracted=rates_extracted_count,
        attachments_parsed=attachments_parsed_count,
        bills=[b.to_dict() for b in utility_bills[:20]],
    )
