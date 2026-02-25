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

import hashlib
import hmac
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

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


def sign_callback_state(connection_id: str) -> str:
    """
    Produce a signed state value: ``{connection_id}:{hex_hmac}``.

    The HMAC is computed over the connection_id using INTERNAL_API_KEY as the
    key with SHA-256.  The callback endpoint verifies this signature before
    trusting the connection_id.
    """
    key = _get_hmac_key()
    sig = hmac.new(key, connection_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{connection_id}:{sig}"


def verify_callback_state(state: str) -> str:
    """
    Verify a signed state value and return the connection_id.

    Raises HTTPException(400) if the state is malformed or the HMAC is invalid.
    """
    if ":" not in state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid callback state: missing HMAC signature.",
        )

    connection_id, received_sig = state.rsplit(":", 1)

    key = _get_hmac_key()
    expected_sig = hmac.new(
        key, connection_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(received_sig, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid callback state: HMAC verification failed.",
        )

    return connection_id


# ---------------------------------------------------------------------------
# Email provider OAuth redirect stubs
# ---------------------------------------------------------------------------

_EMAIL_REDIRECT_URLS = {
    "gmail": "https://accounts.google.com/o/oauth2/auth?scope=https://www.googleapis.com/auth/gmail.readonly",
    "outlook": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?scope=https://outlook.office.com/mail.read",
}


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

    Creates a ``pending`` connection record and returns the OAuth redirect URL
    for the given provider (gmail or outlook).
    """
    connection_id = str(uuid4())
    redirect_url = _EMAIL_REDIRECT_URLS[payload.provider]

    await db.execute(
        text("""
            INSERT INTO user_connections
                (id, user_id, connection_type, email_provider, status, created_at)
            VALUES
                (:id, :uid, 'email_import', :provider, 'pending', NOW())
        """),
        {
            "id": connection_id,
            "uid": current_user.user_id,
            "provider": payload.provider,
        },
    )
    await db.commit()

    return EmailConnectionInitResponse(
        connection_id=connection_id,
        redirect_url=redirect_url,
        provider=payload.provider,
    )


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

    # Persist file to local storage
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
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

    connection_id = verify_callback_state(state)
    log = logger.bind(connection_id=connection_id, authorization_uid=authorization_uid)
    log.info("utilityapi_callback_received")

    # 1. Verify connection exists and is still pending
    conn_result = await db.execute(
        text("""
            SELECT id, status FROM user_connections
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
