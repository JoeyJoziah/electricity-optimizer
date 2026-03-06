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

import base64
from datetime import datetime, timezone
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from api.dependencies import SessionData, get_db_session
from api.v1.connections.common import require_paid_tier
from models.connections import (CreateEmailConnectionRequest,
                                EmailConnectionInitResponse)

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
    from services.email_oauth_service import (get_gmail_consent_url,
                                              get_outlook_consent_url)
    from services.email_oauth_service import settings as _oauth_settings

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
        redirect_url = get_gmail_consent_url(connection_id)
    else:
        redirect_url = get_outlook_consent_url(connection_id)

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

    from services.email_oauth_service import (encrypt_tokens,
                                              exchange_gmail_code,
                                              exchange_outlook_code,
                                              verify_oauth_state)

    # Verify state
    connection_id = verify_oauth_state(state)
    if not connection_id:
        raise HTTPException(status_code=400, detail="Invalid or tampered OAuth state")

    # Look up connection
    result = await db.execute(
        text("SELECT id, email_provider, status FROM user_connections WHERE id = :cid"),
        {"cid": connection_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Connection not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="Connection already processed")

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

    # Store encrypted tokens (base64 for text column storage)
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
            "access": base64.b64encode(enc_access).decode(),
            "refresh": base64.b64encode(enc_refresh).decode() if enc_refresh else None,
            "expires": expires_in,
        },
    )
    await db.commit()

    # Redirect to frontend connections page.
    # Access settings through the package namespace so that
    # ``patch("api.v1.connections.settings")`` in tests is observed at call time.
    import api.v1.connections as _pkg

    _settings = _pkg.settings
    # TODO (tech debt): oauth_redirect_base_url currently points to the backend
    # (default: http://localhost:8000). The redirect after OAuth must land on the
    # FRONTEND, so until a dedicated FRONTEND_URL setting is added we derive it
    # with a local-only port swap. In production, set OAUTH_REDIRECT_BASE_URL to
    # the frontend origin (e.g. https://app.example.com) so the replace() is a
    # no-op and the redirect is correct. Adding a FRONTEND_URL env var and
    # Settings field is the proper fix; tracked as tech debt.
    frontend_url = _settings.oauth_redirect_base_url.replace("localhost:8000", "localhost:3000")
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
    summary="Trigger email inbox scan",
)
async def trigger_email_scan(
    connection_id: str,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
):
    """Trigger a scan of the connected email inbox for utility bills."""
    import httpx as _httpx

    from services.email_scanner_service import (scan_gmail_inbox,
                                                scan_outlook_inbox)
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

    # Decrypt access token
    enc_access = base64.b64decode(row["oauth_access_token"])
    access_token = _decrypt_field(enc_access)

    # Check if token expired and refresh if needed
    if row["oauth_token_expires_at"] and row["oauth_token_expires_at"] < datetime.now(timezone.utc):
        if row["oauth_refresh_token"]:
            from services.email_oauth_service import (encrypt_tokens,
                                                      refresh_gmail_token,
                                                      refresh_outlook_token)

            enc_refresh = base64.b64decode(row["oauth_refresh_token"])
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
                        "access": base64.b64encode(new_enc_access).decode(),
                        "refresh": (
                            base64.b64encode(new_enc_refresh).decode() if new_enc_refresh else None
                        ),
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
    try:
        if row["email_provider"] == "gmail":
            scan_results = await scan_gmail_inbox(access_token)
        else:
            scan_results = await scan_outlook_inbox(access_token)
    except _httpx.HTTPStatusError:
        raise HTTPException(status_code=502, detail="Email provider API error")

    # Filter to utility bills only
    utility_bills = [r for r in scan_results if r.is_utility_bill]

    return {
        "connection_id": connection_id,
        "provider": row["email_provider"],
        "total_emails_scanned": len(scan_results),
        "utility_bills_found": len(utility_bills),
        "bills": [b.to_dict() for b in utility_bills[:20]],
    }
