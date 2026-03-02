"""
Basic CRUD endpoints for the Connections feature.

Routes (mounted under the /connections prefix in router.py):
  GET    /                     — list all connections for the authenticated user
  GET    /{connection_id}      — retrieve a single connection
  DELETE /{connection_id}      — soft-delete a connection
  PATCH  /{connection_id}      — update connection label / settings
"""

from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from api.dependencies import get_db_session, SessionData
from models.connections import (
    ConnectionListResponse,
    ConnectionResponse,
    CreateDirectConnectionRequest,
    DeleteConnectionResponse,
)
from api.v1.connections.common import require_paid_tier

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /  —  list all connections for the authenticated user
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=ConnectionListResponse,
    summary="List connections",
)
async def list_connections(
    current_user: SessionData = Depends(require_paid_tier),
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
# POST /direct  —  create a direct (account-number) connection
# ---------------------------------------------------------------------------


@router.post(
    "/direct",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create direct connection",
)
async def create_direct_connection(
    payload: CreateDirectConnectionRequest,
    current_user: SessionData = Depends(require_paid_tier),
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
# GET /{connection_id}  —  retrieve a single connection
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}",
    response_model=ConnectionResponse,
    summary="Get connection",
)
async def get_connection(
    connection_id: str,
    current_user: SessionData = Depends(require_paid_tier),
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
# DELETE /{connection_id}  —  soft-delete a connection
# ---------------------------------------------------------------------------


@router.delete(
    "/{connection_id}",
    response_model=DeleteConnectionResponse,
    summary="Delete connection",
)
async def delete_connection(
    connection_id: str,
    current_user: SessionData = Depends(require_paid_tier),
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
# PATCH /{connection_id}  —  update connection label / settings
# ---------------------------------------------------------------------------


@router.patch(
    "/{connection_id}",
    summary="Update connection",
)
async def update_connection(
    connection_id: str,
    label: Optional[str] = None,
    current_user: SessionData = Depends(require_paid_tier),
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
