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
"""

from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

import structlog

from api.dependencies import get_current_user, get_db_session, TokenData
from models.connections import (
    ConnectionResponse,
    ConnectionListResponse,
    CreateDirectConnectionRequest,
    CreateEmailConnectionRequest,
    CreateUploadConnectionRequest,
    DeleteConnectionResponse,
    EmailConnectionInitResponse,
    ExtractedRateResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

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
