"""
Connection Feature API Router

Endpoints allowing paid-tier users to link utility accounts via three
mechanisms: direct account-number entry, email-import (OAuth redirect), and
manual file upload.

All endpoints require:
  1. A valid Neon Auth session (get_current_user)
  2. An active paid subscription (pro or business) enforced by require_paid_tier

Tier check strategy:
  The ``require_paid_tier`` dependency queries ``public.users.subscription_tier``
  and raises HTTP 403 if the value is "free" or NULL.

Phase 4 additions:
  - GET  /connections/direct/callback    — UtilityAPI authorization callback
  - POST /connections/{id}/sync          — manual UtilityAPI sync trigger
  - GET  /connections/{id}/sync-status   — last/next sync metadata
"""

import asyncio
import base64
import hashlib
import hmac
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from starlette.responses import RedirectResponse

import structlog

from api.dependencies import get_current_user, get_db_session, TokenData
from config.settings import settings
from models.connections import (
    AuthorizationCallbackResponse,
    BillUploadListResponse,
    BillUploadResponse,
    ConnectionResponse,
    ConnectionListResponse,
    CreateDirectConnectionRequest,
    CreateEmailConnectionRequest,
    CreateUploadConnectionRequest,
    DeleteConnectionResponse,
    EmailConnectionInitResponse,
    ExtractedRateResponse,
    SyncResultResponse,
    SyncStatusResponse,
)
from services.bill_parser import (
    BillParserService,
    MAX_FILE_SIZE_BYTES,
    build_storage_key,
    validate_upload_file,
)

# ---------------------------------------------------------------------------
# Local upload directory (Phase 2 — cloud storage in Phase 3)
# ---------------------------------------------------------------------------

_UPLOADS_DIR = Path("uploads")

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# HMAC helpers for callback state parameter
# ---------------------------------------------------------------------------


def _get_hmac_key() -> bytes:
    """Return the HMAC signing key derived from INTERNAL_API_KEY."""
    key = settings.internal_api_key
    if not key:
        raise RuntimeError(
            "INTERNAL_API_KEY must be configured to sign callback state parameters."
        )
    return key.encode("utf-8")


def sign_callback_state(connection_id: str, user_id: str) -> str:
    """
    Produce a signed state value: ``{connection_id}:{user_id}:{timestamp}:{hex_hmac}``.

    The HMAC is computed over ``{connection_id}:{user_id}:{timestamp}`` using
    INTERNAL_API_KEY as the key with SHA-256.  The callback endpoint verifies
    this signature and the user_id before trusting the connection_id.
    """
    import time as _time

    timestamp = str(int(_time.time()))
    key = _get_hmac_key()
    payload = f"{connection_id}:{user_id}:{timestamp}"
    sig = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_callback_state(state: str) -> tuple:
    """
    Verify a signed state value and return ``(connection_id, user_id)``.

    Raises HTTPException(400) if the state is malformed or the HMAC is invalid.
    """
    parts = state.split(":")
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid callback state: expected 4 colon-separated parts.",
        )

    connection_id, user_id, timestamp, received_sig = parts

    key = _get_hmac_key()
    payload = f"{connection_id}:{user_id}:{timestamp}"
    expected_sig = hmac.new(
        key, payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(received_sig, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid callback state: HMAC verification failed.",
        )

    return connection_id, user_id


# ---------------------------------------------------------------------------
# Email OAuth redirect URLs are now generated dynamically by email_oauth_service
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Paid-tier gate dependency
# ---------------------------------------------------------------------------


async def require_paid_tier(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> TokenData:
    """
    Dependency that raises 403 for free-tier users.

    Queries ``public.users.subscription_tier`` for the authenticated user.
    Raises:
        HTTP 401: If the user is not authenticated (handled by get_current_user).
        HTTP 403: If the user is on the free tier or has no tier set.
    """
    result = await db.execute(
        text("SELECT subscription_tier FROM public.users WHERE id = :uid"),
        {"uid": current_user.user_id},
    )
    row = result.fetchone()
    tier = row[0] if row else None

    if tier not in ("pro", "business"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Connections require a Pro or Business subscription.",
        )
    return current_user


# ---------------------------------------------------------------------------
# GET /connections  —  list all connections for the authenticated user
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ConnectionListResponse,
    summary="List connections",
)
async def list_connections(
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> ConnectionListResponse:
    """Return all active connections belonging to the current user."""
    result = await db.execute(
        text("""
            SELECT id, user_id, connection_type, supplier_id, supplier_name,
                   status, account_number_masked, email_provider, label, created_at
            FROM user_connections
            WHERE user_id = :uid
            ORDER BY created_at DESC
        """),
        {"uid": current_user.user_id},
    )
    rows = result.mappings().all()
    connections = [ConnectionResponse(**dict(row)) for row in rows]
    return ConnectionListResponse(connections=connections, total=len(connections))


# ---------------------------------------------------------------------------
# POST /connections/direct  —  create a direct (account-number) connection
# ---------------------------------------------------------------------------


@router.post(
    "/direct",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create direct connection",
)
async def create_direct_connection(
    payload: CreateDirectConnectionRequest,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> ConnectionResponse:
    """
    Create a direct connection by storing an encrypted account number.

    Checks that:
    - The referenced supplier exists in ``supplier_registry``.
    - No active direct connection to the same supplier already exists.

    Returns the new ConnectionResponse (account number is masked in response).
    """
    from utils.encryption import encrypt_field, mask_account_number

    supplier_id_str = str(payload.supplier_id)

    # Verify supplier exists
    sup_result = await db.execute(
        text("SELECT id, name FROM supplier_registry WHERE id = :sid"),
        {"sid": supplier_id_str},
    )
    supplier = sup_result.mappings().first()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {supplier_id_str} not found.",
        )

    # Duplicate-active-connection guard
    dup_result = await db.execute(
        text("""
            SELECT id FROM user_connections
            WHERE user_id = :uid
              AND supplier_id = :sid
              AND connection_type = 'direct'
              AND status = 'active'
        """),
        {"uid": current_user.user_id, "sid": supplier_id_str},
    )
    if dup_result.fetchone() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active direct connection to this supplier already exists.",
        )

    # Encrypt account number
    encrypted_account = encrypt_field(payload.account_number)
    masked = mask_account_number(payload.account_number)
    connection_id = str(uuid4())

    await db.execute(
        text("""
            INSERT INTO user_connections
                (id, user_id, connection_type, supplier_id, supplier_name,
                 status, account_number_encrypted, account_number_masked, created_at)
            VALUES
                (:id, :uid, 'direct', :sid, :sname,
                 'active', :enc_acct, :masked_acct, NOW())
        """),
        {
            "id": connection_id,
            "uid": current_user.user_id,
            "sid": supplier_id_str,
            "sname": supplier["name"],
            "enc_acct": encrypted_account,
            "masked_acct": masked,
        },
    )
    await db.commit()

    return ConnectionResponse(
        id=connection_id,
        user_id=current_user.user_id,
        connection_type="direct",
        supplier_id=supplier_id_str,
        supplier_name=supplier["name"],
        status="active",
        account_number_masked=masked,
    )


# ---------------------------------------------------------------------------
# POST /connections/email  —  start an email-import connection
# ---------------------------------------------------------------------------


@router.post(
    "/email",
    response_model=EmailConnectionInitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start email-import connection",
)
async def create_email_connection(
    payload: CreateEmailConnectionRequest,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> EmailConnectionInitResponse:
    """
    Initiate an email-import connection.
    Creates a pending connection and returns the OAuth consent URL.
    """
    from services.email_oauth_service import get_gmail_consent_url, get_outlook_consent_url

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
# GET /connections/email/callback  —  OAuth callback from Gmail/Outlook
# ---------------------------------------------------------------------------

# NOTE: This callback endpoint must be registered BEFORE /{connection_id}
# routes so that FastAPI does not capture "email" as a connection_id.


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
    from services.email_oauth_service import (
        verify_oauth_state,
        exchange_gmail_code,
        exchange_outlook_code,
        encrypt_tokens,
    )
    import httpx as _httpx

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

    # Redirect to frontend connections page
    frontend_url = settings.oauth_redirect_base_url.replace("localhost:8000", "localhost:3000")
    return RedirectResponse(
        url=f"{frontend_url}/connections?connected={connection_id}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# POST /connections/email/{connection_id}/scan  —  trigger email scan
# ---------------------------------------------------------------------------


@router.post(
    "/email/{connection_id}/scan",
    summary="Trigger email inbox scan",
)
async def trigger_email_scan(
    connection_id: str,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
):
    """Trigger a scan of the connected email inbox for utility bills."""
    from utils.encryption import decrypt_field as _decrypt_field
    from services.email_scanner_service import scan_gmail_inbox, scan_outlook_inbox
    import httpx as _httpx

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
            from services.email_oauth_service import refresh_gmail_token, refresh_outlook_token, encrypt_tokens
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
                        "refresh": base64.b64encode(new_enc_refresh).decode() if new_enc_refresh else None,
                        "expires": new_tokens.get("expires_in", 3600),
                    },
                )
                await db.commit()
            except Exception:
                raise HTTPException(status_code=502, detail="Token refresh failed")
        else:
            raise HTTPException(status_code=401, detail="Token expired and no refresh token available")

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


# ---------------------------------------------------------------------------
# POST /connections/upload  —  create a manual-upload connection stub
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create upload connection stub",
)
async def create_upload_connection(
    payload: CreateUploadConnectionRequest,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> ConnectionResponse:
    """Create a manual-upload connection stub; actual file upload is separate."""
    connection_id = str(uuid4())

    await db.execute(
        text("""
            INSERT INTO user_connections
                (id, user_id, connection_type, label, status, created_at)
            VALUES
                (:id, :uid, 'manual_upload', :label, 'active', NOW())
        """),
        {
            "id": connection_id,
            "uid": current_user.user_id,
            "label": payload.label,
        },
    )
    await db.commit()

    return ConnectionResponse(
        id=connection_id,
        user_id=current_user.user_id,
        connection_type="manual_upload",
        status="active",
        label=payload.label,
    )


# ---------------------------------------------------------------------------
# Phase 5 Analytics Endpoints
# NOTE: All /analytics/* routes MUST be registered before /{connection_id}
# so FastAPI does not capture "analytics" as a connection_id path parameter.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /connections/analytics/comparison  —  rate comparison
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/comparison",
    summary="Compare user rates vs market",
)
async def get_rate_comparison(
    connection_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
):
    """Compare extracted rates against current market prices."""
    from services.connection_analytics_service import ConnectionAnalyticsService
    svc = ConnectionAnalyticsService(db)
    return await svc.get_rate_comparison(current_user.user_id, connection_id)


# ---------------------------------------------------------------------------
# GET /connections/analytics/history  —  rate history for charts
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/history",
    summary="Rate history for chart rendering",
)
async def get_rate_history(
    connection_id: Optional[str] = Query(None),
    days: int = Query(365, ge=1, le=1095),
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
):
    """Get time-series rate data for chart rendering."""
    from services.connection_analytics_service import ConnectionAnalyticsService
    svc = ConnectionAnalyticsService(db)
    return await svc.get_rate_history(current_user.user_id, connection_id, days)


# ---------------------------------------------------------------------------
# GET /connections/analytics/savings  —  estimated savings
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/savings",
    summary="Estimated annual savings",
)
async def get_savings_estimate(
    monthly_kwh: float = Query(900, ge=0, le=50000),
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
):
    """Calculate estimated annual savings based on rate comparison."""
    from services.connection_analytics_service import ConnectionAnalyticsService
    svc = ConnectionAnalyticsService(db)
    return await svc.get_savings_estimate(current_user.user_id, monthly_kwh)


# ---------------------------------------------------------------------------
# GET /connections/analytics/health  —  stale connection detection
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/health",
    summary="Connection health status",
)
async def get_connection_health(
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
):
    """Check for stale or unhealthy connections."""
    from services.connection_analytics_service import ConnectionAnalyticsService
    svc = ConnectionAnalyticsService(db)
    stale = await svc.check_stale_connections(current_user.user_id)
    alerts = await svc.detect_rate_changes(current_user.user_id)
    return {
        "stale_connections": stale,
        "rate_change_alerts": alerts,
        "total_stale": len(stale),
        "total_alerts": len(alerts),
    }


# ---------------------------------------------------------------------------
# GET /connections/{connection_id}  —  retrieve a single connection
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}",
    response_model=ConnectionResponse,
    summary="Get connection",
)
async def get_connection(
    connection_id: str,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> ConnectionResponse:
    """Return a single connection record, scoped to the current user."""
    result = await db.execute(
        text("""
            SELECT id, user_id, connection_type, supplier_id, supplier_name,
                   status, account_number_masked, email_provider, label, created_at
            FROM user_connections
            WHERE id = :cid AND user_id = :uid
        """),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )
    return ConnectionResponse(**dict(row))


# ---------------------------------------------------------------------------
# DELETE /connections/{connection_id}  —  soft-delete a connection
# ---------------------------------------------------------------------------


@router.delete(
    "/{connection_id}",
    response_model=DeleteConnectionResponse,
    summary="Delete connection",
)
async def delete_connection(
    connection_id: str,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> DeleteConnectionResponse:
    """Mark a connection as disconnected (soft delete), scoped to the current user."""
    result = await db.execute(
        text("""
            SELECT id FROM user_connections
            WHERE id = :cid AND user_id = :uid
        """),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    await db.execute(
        text("""
            UPDATE user_connections SET status = 'disconnected'
            WHERE id = :cid AND user_id = :uid
        """),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    await db.commit()

    return DeleteConnectionResponse(
        message="Connection deleted",
        connection_id=connection_id,
    )


# ---------------------------------------------------------------------------
# PATCH /connections/{connection_id}  —  update connection (label, etc.)
# ---------------------------------------------------------------------------


@router.patch(
    "/{connection_id}",
    summary="Update connection",
)
async def update_connection(
    connection_id: str,
    label: Optional[str] = None,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
):
    """Update connection label or settings."""
    # Verify ownership
    result = await db.execute(
        text("SELECT id FROM user_connections WHERE id = :cid AND user_id = :uid"),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Connection not found")

    updates = []
    params: dict = {"cid": connection_id}
    if label is not None:
        updates.append("label = :label")
        params["label"] = label

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = NOW()")
    await db.execute(
        text(f"UPDATE user_connections SET {', '.join(updates)} WHERE id = :cid"),
        params,
    )
    await db.commit()
    return {"connection_id": connection_id, "updated": True}


# ---------------------------------------------------------------------------
# GET /connections/{connection_id}/rates  —  list extracted rates
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}/rates",
    response_model=List[ExtractedRateResponse],
    summary="Get extracted rates for a connection",
)
async def get_rates(
    connection_id: str,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> List[ExtractedRateResponse]:
    """Return all rates extracted for the given connection (scoped to current user)."""
    # Verify ownership
    conn_result = await db.execute(
        text("SELECT id FROM user_connections WHERE id = :cid AND user_id = :uid"),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if conn_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    result = await db.execute(
        text("""
            SELECT id, connection_id, rate_per_kwh, effective_date, source, raw_label
            FROM connection_extracted_rates
            WHERE connection_id = :cid
            ORDER BY effective_date DESC
        """),
        {"cid": connection_id},
    )
    rows = result.mappings().all()
    return [ExtractedRateResponse(**dict(row)) for row in rows]


# ---------------------------------------------------------------------------
# GET /connections/{connection_id}/rates/current  —  most recent rate
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}/rates/current",
    response_model=Optional[ExtractedRateResponse],
    summary="Get the most recent extracted rate for a connection",
)
async def get_current_rate(
    connection_id: str,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> Optional[ExtractedRateResponse]:
    """Return the single most recent rate extracted for this connection."""
    # Verify ownership
    conn_result = await db.execute(
        text("SELECT id FROM user_connections WHERE id = :cid AND user_id = :uid"),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if conn_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    result = await db.execute(
        text("""
            SELECT id, connection_id, rate_per_kwh, effective_date, source, raw_label
            FROM connection_extracted_rates
            WHERE connection_id = :cid
            ORDER BY effective_date DESC
            LIMIT 1
        """),
        {"cid": connection_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    return ExtractedRateResponse(**dict(row))


# ---------------------------------------------------------------------------
# POST /connections/{connection_id}/upload  —  upload a bill file
# ---------------------------------------------------------------------------


@router.post(
    "/{connection_id}/upload",
    response_model=BillUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a utility bill file for parsing",
)
async def upload_bill_file(
    connection_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> BillUploadResponse:
    """
    Accept a PDF, PNG, or JPEG bill file, store it locally, create a
    ``bill_uploads`` record, and schedule background parsing.

    Returns the upload record with ``parse_status="pending"``; the client
    should poll ``GET /{connection_id}/uploads/{upload_id}`` for completion.

    Validation:
    - File extension must be .pdf, .png, .jpg, or .jpeg
    - Content-Type must match the extension
    - Magic bytes are checked to prevent MIME-type spoofing
    - File size must not exceed 10 MB
    """
    log = logger.bind(
        connection_id=connection_id,
        user_id=current_user.user_id,
        filename=file.filename,
    )

    # Verify the connection belongs to the current user
    conn_result = await db.execute(
        text("SELECT id FROM user_connections WHERE id = :cid AND user_id = :uid"),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if conn_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    # Read file content (bounded by RequestBodySizeLimitMiddleware at 10 MB)
    data = await file.read()

    # Size guard (belt-and-suspenders in addition to middleware)
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Validate file type via extension, MIME type, and magic bytes
    content_type = file.content_type or ""
    filename = file.filename or "upload.bin"

    try:
        file_type = validate_upload_file(filename, content_type, data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc

    # Generate IDs and storage path
    upload_id = str(uuid4())
    storage_key = build_storage_key(connection_id, upload_id, filename)
    dest = _UPLOADS_DIR / storage_key

    # Persist file to local storage (async to avoid blocking the event loop)
    try:
        await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(dest.write_bytes, data)
    except OSError as exc:
        log.error("bill_upload_storage_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store uploaded file.",
        ) from exc

    # Insert bill_uploads record
    await db.execute(
        text("""
            INSERT INTO bill_uploads
                (id, connection_id, user_id, file_name, file_type,
                 file_size_bytes, storage_key, parse_status, created_at, updated_at)
            VALUES
                (:id, :connection_id, :user_id, :file_name, :file_type,
                 :file_size_bytes, :storage_key, 'pending', NOW(), NOW())
        """),
        {
            "id": upload_id,
            "connection_id": connection_id,
            "user_id": current_user.user_id,
            "file_name": filename,
            "file_type": file_type,
            "file_size_bytes": len(data),
            "storage_key": storage_key,
        },
    )
    await db.commit()

    log.info("bill_upload_created", upload_id=upload_id, file_type=file_type, bytes=len(data))

    # Schedule background parse (fire-and-forget; status queryable via GET)
    background_tasks.add_task(
        _run_background_parse,
        upload_id=upload_id,
        connection_id=connection_id,
        storage_key=storage_key,
    )

    return BillUploadResponse(
        id=upload_id,
        connection_id=connection_id,
        file_name=filename,
        file_type=file_type,
        file_size_bytes=len(data),
        parse_status="pending",
    )


async def _run_background_parse(
    upload_id: str,
    connection_id: str,
    storage_key: str,
) -> None:
    """Background task: acquire a fresh DB session and run the bill parser."""
    from api.dependencies import get_db_session as _get_db

    try:
        # get_db_session is an async generator — iterate it manually
        gen = _get_db()
        db: AsyncSession = await gen.__anext__()
        try:
            parser = BillParserService(db=db, uploads_dir=_UPLOADS_DIR)
            await parser.parse(
                upload_id=upload_id,
                connection_id=connection_id,
                storage_key=storage_key,
            )
        finally:
            try:
                await gen.aclose()
            except Exception:
                pass
    except Exception as exc:
        logger.error(
            "background_parse_error",
            upload_id=upload_id,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# GET /connections/{connection_id}/uploads  —  list bill uploads
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}/uploads",
    response_model=BillUploadListResponse,
    summary="List bill uploads for a connection",
)
async def list_bill_uploads(
    connection_id: str,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> BillUploadListResponse:
    """Return all bill uploads for the given connection (scoped to current user)."""
    conn_result = await db.execute(
        text("SELECT id FROM user_connections WHERE id = :cid AND user_id = :uid"),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if conn_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    result = await db.execute(
        text("""
            SELECT id, connection_id, file_name, file_type, file_size_bytes,
                   parse_status, detected_supplier, detected_rate_per_kwh,
                   detected_billing_period_start, detected_billing_period_end,
                   detected_total_kwh, detected_total_amount,
                   parse_error, created_at
            FROM bill_uploads
            WHERE connection_id = :cid
            ORDER BY created_at DESC
        """),
        {"cid": connection_id},
    )
    rows = result.mappings().all()

    uploads = []
    for row in rows:
        row_dict = dict(row)
        # Cast date columns to ISO string (may be date or str depending on driver)
        for date_col in ("detected_billing_period_start", "detected_billing_period_end"):
            val = row_dict.get(date_col)
            if val is not None and not isinstance(val, str):
                row_dict[date_col] = str(val)
        # Cast Decimal to float
        for num_col in ("detected_rate_per_kwh", "detected_total_kwh", "detected_total_amount"):
            val = row_dict.get(num_col)
            if val is not None:
                row_dict[num_col] = float(val)
        uploads.append(BillUploadResponse(**row_dict))

    return BillUploadListResponse(uploads=uploads, total=len(uploads))


# ---------------------------------------------------------------------------
# GET /connections/{connection_id}/uploads/{upload_id}  —  single upload status
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}/uploads/{upload_id}",
    response_model=BillUploadResponse,
    summary="Get single bill upload status",
)
async def get_bill_upload(
    connection_id: str,
    upload_id: str,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> BillUploadResponse:
    """Return a single bill upload record (for polling parse status)."""
    result = await db.execute(
        text("""
            SELECT bu.id, bu.connection_id, bu.file_name, bu.file_type,
                   bu.file_size_bytes, bu.parse_status, bu.detected_supplier,
                   bu.detected_rate_per_kwh, bu.detected_billing_period_start,
                   bu.detected_billing_period_end, bu.detected_total_kwh,
                   bu.detected_total_amount, bu.parse_error, bu.created_at
            FROM bill_uploads bu
            JOIN user_connections uc ON bu.connection_id = uc.id
            WHERE bu.id = :uid AND bu.connection_id = :cid AND uc.user_id = :user_id
        """),
        {"uid": upload_id, "cid": connection_id, "user_id": current_user.user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Upload not found")

    row_dict = dict(row)
    # Cast date fields to string for Pydantic
    for date_col in ("detected_billing_period_start", "detected_billing_period_end"):
        val = row_dict.get(date_col)
        if val is not None:
            row_dict[date_col] = str(val)
    # Cast Decimal fields to float
    for num_col in ("detected_rate_per_kwh", "detected_total_kwh", "detected_total_amount"):
        val = row_dict.get(num_col)
        if val is not None:
            row_dict[num_col] = float(val)
    return BillUploadResponse(**row_dict)


# ---------------------------------------------------------------------------
# POST /connections/{connection_id}/uploads/{upload_id}/reparse
# ---------------------------------------------------------------------------


@router.post(
    "/{connection_id}/uploads/{upload_id}/reparse",
    response_model=BillUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-trigger bill parsing for an upload",
)
async def reparse_bill_upload(
    connection_id: str,
    upload_id: str,
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> BillUploadResponse:
    """
    Reset a bill upload's parse_status to 'pending' and schedule a fresh parse.

    Useful when:
    - The initial parse failed and the issue has been corrected.
    - Parser logic has been improved and historical bills need reprocessing.
    """
    # Verify connection ownership
    conn_result = await db.execute(
        text("SELECT id FROM user_connections WHERE id = :cid AND user_id = :uid"),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if conn_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    # Fetch the upload record (must belong to this connection)
    upload_result = await db.execute(
        text("""
            SELECT id, connection_id, file_name, file_type, file_size_bytes,
                   storage_key, parse_status, detected_supplier, detected_rate_per_kwh,
                   detected_billing_period_start, detected_billing_period_end,
                   detected_total_kwh, detected_total_amount,
                   parse_error, created_at
            FROM bill_uploads
            WHERE id = :upload_id AND connection_id = :cid
        """),
        {"upload_id": upload_id, "cid": connection_id},
    )
    row = upload_result.mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found.",
        )

    storage_key = row["storage_key"]

    # Reset parse_status to pending
    await db.execute(
        text("""
            UPDATE bill_uploads
            SET parse_status = 'pending',
                parse_error  = NULL,
                parsed_at    = NULL,
                updated_at   = NOW()
            WHERE id = :upload_id
        """),
        {"upload_id": upload_id},
    )
    await db.commit()

    logger.info("bill_reparse_scheduled", upload_id=upload_id, connection_id=connection_id)

    # Schedule background parse
    background_tasks.add_task(
        _run_background_parse,
        upload_id=upload_id,
        connection_id=connection_id,
        storage_key=storage_key,
    )

    return BillUploadResponse(
        id=upload_id,
        connection_id=connection_id,
        file_name=row["file_name"],
        file_type=row["file_type"],
        file_size_bytes=row["file_size_bytes"],
        parse_status="pending",
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Phase 4: UtilityAPI Direct Sync
# ---------------------------------------------------------------------------


# NOTE: This callback endpoint must be registered BEFORE /{connection_id}
# routes so that FastAPI does not capture "direct" as a connection_id.
# The router prefix is /api/v1/connections, so this is mounted at:
#   GET /api/v1/connections/direct/callback


@router.get(
    "/direct/callback",
    response_model=AuthorizationCallbackResponse,
    summary="UtilityAPI authorization callback",
)
async def utilityapi_callback(
    authorization_uid: str = Query(..., description="UtilityAPI authorization UID"),
    state: str = Query(..., description="Opaque state value (maps to connection_id)"),
    db: AsyncSession = Depends(get_db_session),
) -> AuthorizationCallbackResponse:
    """
    Receive the UtilityAPI authorization callback after a customer completes
    the authorization form.

    Query parameters sent by UtilityAPI:
    - ``authorization_uid``: UID of the newly created authorization.
    - ``state``: The value we passed when creating the form URL; we use the
      ``connection_id`` as the state.

    Processing:
    1. Validate that a ``pending`` connection exists for the given state/connection_id.
    2. Verify the authorization is active via UtilityAPI.
    3. Encrypt and store the ``authorization_uid``.
    4. Set connection status to ``active``.
    5. Trigger an initial data sync in the background.

    This endpoint does NOT require authentication — UtilityAPI calls it as a
    redirect, and the ``state`` parameter provides connection binding.
    """
    from utils.encryption import encrypt_field
    from integrations.utilityapi import UtilityAPIClient, UtilityAPIError
    from services.connection_sync_service import ConnectionSyncService

    connection_id, state_user_id = verify_callback_state(state)
    log = logger.bind(connection_id=connection_id, authorization_uid=authorization_uid)
    log.info("utilityapi_callback_received")

    # 1. Verify connection exists and is still pending
    conn_result = await db.execute(
        text("""
            SELECT id, user_id, status FROM user_connections
            WHERE id = :cid AND connection_type = 'direct'
        """),
        {"cid": connection_id},
    )
    row = conn_result.mappings().first()
    if row is None:
        log.warning("utilityapi_callback_connection_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    # 2. Verify the user_id embedded in the state matches the connection owner
    if str(row["user_id"]) != state_user_id:
        log.warning(
            "utilityapi_callback_user_mismatch",
            state_user_id=state_user_id,
            connection_user_id=str(row["user_id"]),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Callback state user does not match connection owner.",
        )

    if row["status"] == "disconnected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Connection has been disconnected.",
        )

    # 2. Verify authorization is active via UtilityAPI
    client = UtilityAPIClient()
    try:
        auth_status = await client.get_authorization_status(authorization_uid)
    except UtilityAPIError as exc:
        log.error("utilityapi_callback_auth_verify_failed", error=str(exc))
        # Mark connection as error but still return 200 so UtilityAPI doesn't retry
        await db.execute(
            text("""
                UPDATE user_connections
                SET status = 'error'
                WHERE id = :cid
            """),
            {"cid": connection_id},
        )
        await db.commit()
        return AuthorizationCallbackResponse(
            connection_id=connection_id,
            status="error",
            message=f"Could not verify UtilityAPI authorization: {exc}",
        )
    finally:
        await client.close()

    ua_status = auth_status.get("status", "")
    if ua_status not in ("active", "pending"):
        msg = f"UtilityAPI authorization status is '{ua_status}', expected 'active'."
        log.warning("utilityapi_callback_auth_inactive", ua_status=ua_status)
        await db.execute(
            text("UPDATE user_connections SET status = 'error' WHERE id = :cid"),
            {"cid": connection_id},
        )
        await db.commit()
        return AuthorizationCallbackResponse(
            connection_id=connection_id,
            status="error",
            message=msg,
        )

    # 3. Encrypt the authorization UID and persist
    try:
        encrypted_uid = encrypt_field(authorization_uid)
    except RuntimeError as exc:
        log.error("utilityapi_callback_encrypt_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Encryption configuration error — cannot store authorization.",
        ) from exc

    await db.execute(
        text("""
            UPDATE user_connections
            SET status                          = 'active',
                utilityapi_auth_uid_encrypted   = :enc_uid
            WHERE id = :cid
        """),
        {"enc_uid": encrypted_uid, "cid": connection_id},
    )
    await db.commit()

    log.info("utilityapi_callback_connection_activated")

    # 4. Kick off initial sync (best-effort — don't fail the callback if it errors)
    try:
        sync_svc = ConnectionSyncService(db)
        await sync_svc.sync_connection(connection_id)
    except Exception as exc:
        log.warning("utilityapi_callback_initial_sync_failed", error=str(exc))

    return AuthorizationCallbackResponse(
        connection_id=connection_id,
        status="active",
        message="Authorization successful. Initial data sync complete.",
    )


# ---------------------------------------------------------------------------
# POST /connections/{connection_id}/sync  —  manual sync trigger
# ---------------------------------------------------------------------------


@router.post(
    "/{connection_id}/sync",
    response_model=SyncResultResponse,
    summary="Trigger manual UtilityAPI sync for a connection",
)
async def trigger_sync(
    connection_id: str,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> SyncResultResponse:
    """
    Immediately pull the latest rate/billing data from UtilityAPI for the
    given connection and persist any new rates.

    Only valid for connections of type ``direct`` that have been authorized
    (i.e., status is ``active`` and ``utilityapi_auth_uid_encrypted`` is set).

    Returns:
        SyncResultResponse containing success flag, count of new rates found,
        and any error message.
    """
    from services.connection_sync_service import ConnectionSyncService

    # Verify ownership
    conn_result = await db.execute(
        text("""
            SELECT id FROM user_connections
            WHERE id = :cid AND user_id = :uid
        """),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if conn_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    sync_svc = ConnectionSyncService(db)
    result = await sync_svc.sync_connection(connection_id)

    return SyncResultResponse(
        connection_id=result["connection_id"],
        success=result["success"],
        new_rates_found=result["new_rates_found"],
        error=result.get("error"),
        synced_at=result["synced_at"],
    )


# ---------------------------------------------------------------------------
# GET /connections/{connection_id}/sync-status  —  sync metadata
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}/sync-status",
    response_model=SyncStatusResponse,
    summary="Get sync status for a connection",
)
async def get_sync_status(
    connection_id: str,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> SyncStatusResponse:
    """
    Return sync scheduling metadata for a connection without triggering a sync.

    Response fields:
    - ``last_sync_at``        — timestamp of the most recent successful sync.
    - ``last_sync_error``     — error message from the last failed sync (or null).
    - ``next_sync_at``        — when the next automatic sync is scheduled.
    - ``sync_frequency_hours``— how often the connection is auto-synced.
    """
    from services.connection_sync_service import ConnectionSyncService

    # Verify ownership first
    conn_result = await db.execute(
        text("""
            SELECT id FROM user_connections
            WHERE id = :cid AND user_id = :uid
        """),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if conn_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    sync_svc = ConnectionSyncService(db)
    status_data = await sync_svc.get_sync_status(connection_id)

    if status_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    return SyncStatusResponse(**status_data)
