"""
Basic CRUD endpoints for the Connections feature.

Routes (mounted under the /connections prefix in router.py):
  GET    /                     — list all connections for the authenticated user
  GET    /{connection_id}      — retrieve a single connection
  DELETE /{connection_id}      — soft-delete a connection
  PATCH  /{connection_id}      — update connection label / settings
"""

import uuid
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import SessionData, get_db_session
from api.v1.connections.common import require_paid_tier
from models.connections import (
    ConnectionListResponse,
    ConnectionResponse,
    CreateDirectConnectionRequest,
    DeleteConnectionResponse,
    UpdateConnectionRequest,
)

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
            SELECT uc.id, uc.user_id, uc.connection_type, uc.supplier_id,
                   uc.supplier_name, uc.status, uc.account_number_masked,
                   uc.meter_number_masked, uc.email_provider, uc.label,
                   uc.created_at, uc.last_sync_at, uc.last_sync_error,
                   uc.utilityapi_meter_count,
                   uc.stripe_subscription_item_id,
                   (SELECT cer.rate_per_kwh FROM connection_extracted_rates cer
                    WHERE cer.connection_id = uc.id
                    ORDER BY cer.effective_date DESC LIMIT 1
                   ) AS current_rate
            FROM user_connections uc
            WHERE uc.user_id = :uid
            ORDER BY uc.created_at DESC
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

    # Encrypt meter number if provided
    encrypted_meter = None
    masked_meter = None
    if payload.meter_number:
        encrypted_meter = encrypt_field(payload.meter_number)
        masked_meter = mask_account_number(payload.meter_number)

    await db.execute(
        text("""
            INSERT INTO user_connections
                (id, user_id, connection_type, supplier_id, supplier_name,
                 status, account_number_encrypted, account_number_masked,
                 meter_number_encrypted, meter_number_masked, created_at)
            VALUES
                (:id, :uid, 'direct', :sid, :sname,
                 'active', :enc_acct, :masked_acct,
                 :enc_meter, :masked_meter, NOW())
        """),
        {
            "id": connection_id,
            "uid": current_user.user_id,
            "sid": supplier_id_str,
            "sname": supplier["name"],
            "enc_acct": encrypted_account,
            "masked_acct": masked,
            "enc_meter": encrypted_meter,
            "masked_meter": masked_meter,
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
        meter_number_masked=masked_meter,
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
    connection_id: uuid.UUID,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> ConnectionResponse:
    """Return a single connection record, scoped to the current user."""
    result = await db.execute(
        text("""
            SELECT uc.id, uc.user_id, uc.connection_type, uc.supplier_id,
                   uc.supplier_name, uc.status, uc.account_number_masked,
                   uc.meter_number_masked, uc.email_provider, uc.label,
                   uc.created_at, uc.last_sync_at, uc.last_sync_error,
                   uc.utilityapi_meter_count,
                   uc.stripe_subscription_item_id,
                   (SELECT cer.rate_per_kwh FROM connection_extracted_rates cer
                    WHERE cer.connection_id = uc.id
                    ORDER BY cer.effective_date DESC LIMIT 1
                   ) AS current_rate
            FROM user_connections uc
            WHERE uc.id = :cid AND uc.user_id = :uid
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
    connection_id: uuid.UUID,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> DeleteConnectionResponse:
    """Mark a connection as disconnected (soft delete), scoped to the current user."""
    result = await db.execute(
        text("""
            SELECT id, connection_type, stripe_subscription_item_id
            FROM user_connections
            WHERE id = :cid AND user_id = :uid
        """),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    conn_row = result.mappings().first()
    if conn_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    # Remove UtilityAPI billing if applicable (best-effort)
    if conn_row["connection_type"] == "direct" and conn_row["stripe_subscription_item_id"]:
        try:
            from services.utilityapi_billing_service import UtilityAPIBillingService

            billing_svc = UtilityAPIBillingService(db)
            await billing_svc.remove_meters(current_user.user_id, str(connection_id))
        except Exception as exc:
            logger.warning(
                "delete_connection_billing_removal_failed",
                connection_id=str(connection_id),
                error=str(exc),
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
        connection_id=str(connection_id),
    )


# ---------------------------------------------------------------------------
# PATCH /{connection_id}  —  update connection label / settings
# ---------------------------------------------------------------------------


@router.patch(
    "/{connection_id}",
    summary="Update connection",
)
async def update_connection(
    connection_id: uuid.UUID,
    payload: UpdateConnectionRequest,
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
    params: dict = {"cid": connection_id, "uid": current_user.user_id}
    if payload.label is not None:
        updates.append("label = :label")
        params["label"] = payload.label

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = NOW()")
    await db.execute(
        text(
            f"UPDATE user_connections SET {', '.join(updates)} WHERE id = :cid AND user_id = :uid"
        ),
        params,
    )
    await db.commit()
    return {"connection_id": str(connection_id), "updated": True}
