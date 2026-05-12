"""
Phase 4: UtilityAPI direct sync endpoints.

Routes (mounted under the /connections prefix in router.py):
  GET  /direct/callback          — UtilityAPI authorization callback (no auth required)
  POST /{connection_id}/sync     — manual UtilityAPI sync trigger
  GET  /{connection_id}/sync-status — sync scheduling metadata

IMPORTANT: /direct/callback MUST be registered in router.py BEFORE the
/{connection_id} wildcard routes so FastAPI does not capture "direct" as a
connection_id path parameter.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import SessionData, get_current_user, get_db_session
from api.v1.connections.common import verify_callback_state
from models.connections import (AuthorizationCallbackResponse,
                                SyncResultResponse, SyncStatusResponse)

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /direct/authorize  —  initiate UtilityAPI OAuth flow
# ---------------------------------------------------------------------------


@router.post(
    "/direct/authorize",
    status_code=status.HTTP_201_CREATED,
    summary="Initiate UtilityAPI authorization flow",
)
async def initiate_utilityapi_authorization(
    payload: dict,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Create a pending connection and return a UtilityAPI authorization URL.

    Available on ALL tiers (Free, Pro, Business). Meter monitoring is billed
    as a $2.25/meter/month add-on via Stripe after authorization completes.

    The user is redirected to UtilityAPI to grant data access. After
    authorization, UtilityAPI calls back to GET /direct/callback.

    Returns 503 if UTILITYAPI_KEY is not configured.
    """
    from uuid import uuid4

    import api.v1.connections as _pkg

    _settings = _pkg.settings
    if not _settings.utilityapi_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UtilityAPI connection is not yet configured. Please try bill upload instead.",
        )

    supplier_id = payload.get("supplier_id")
    consent_given = payload.get("consent_given", False)
    accept_addon_pricing = payload.get("accept_addon_pricing", False)
    if not consent_given:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Consent is required.",
        )
    if not accept_addon_pricing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You must accept the $2.25/meter/month add-on pricing to continue.",
        )
    if not supplier_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="supplier_id is required.",
        )

    # Look up supplier name
    sup_result = await db.execute(
        text("SELECT id, name FROM supplier_registry WHERE id = :sid"),
        {"sid": str(supplier_id)},
    )
    supplier = sup_result.mappings().first()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {supplier_id} not found.",
        )

    # Create a pending connection
    connection_id = str(uuid4())
    await db.execute(
        text("""
            INSERT INTO user_connections
                (id, user_id, connection_type, supplier_id, supplier_name,
                 status, created_at)
            VALUES
                (:id, :uid, 'direct', :sid, :sname, 'pending', NOW())
        """),
        {
            "id": connection_id,
            "uid": current_user.user_id,
            "sid": str(supplier_id),
            "sname": supplier["name"],
        },
    )
    await db.commit()

    # Build the UtilityAPI authorization form URL
    from api.v1.connections.common import sign_callback_state
    from integrations.utilityapi import UtilityAPIClient

    state = sign_callback_state(connection_id, current_user.user_id)
    callback_url = f"{_settings.frontend_url}/api/v1/connections/direct/callback"

    client = UtilityAPIClient()
    try:
        redirect_url = await client.create_authorization_form(
            supplier_name=supplier["name"],
            state=state,
            redirect_url=callback_url,
        )
    finally:
        await client.close()

    return {
        "id": connection_id,
        "connection_id": connection_id,
        "redirect_url": redirect_url,
    }


# ---------------------------------------------------------------------------
# GET /direct/callback  —  UtilityAPI authorization callback
# ---------------------------------------------------------------------------

# NOTE: This endpoint must be registered BEFORE /{connection_id} routes so
# that FastAPI does not capture "direct" as a connection_id path parameter.
# This endpoint does NOT require authentication — UtilityAPI calls it as a
# redirect, and the ``state`` parameter provides connection binding.


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
    """
    from integrations.utilityapi import UtilityAPIClient, UtilityAPIError
    from services.connection_sync_service import ConnectionSyncService
    from utils.encryption import encrypt_field

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
    sync_result: dict | None = None
    try:
        sync_svc = ConnectionSyncService(db)
        sync_result = await sync_svc.sync_connection(connection_id)
    except Exception as exc:
        log.warning("utilityapi_callback_initial_sync_failed", error=str(exc))

    # 5. Add meter billing (best-effort — connection still works if billing fails)
    checkout_url: str | None = None
    meter_count = max((sync_result or {}).get("new_rates_found", 0), 1)
    try:
        from services.utilityapi_billing_service import \
            UtilityAPIBillingService

        billing_svc = UtilityAPIBillingService(db)
        billing_result = await billing_svc.add_meters(
            user_id=state_user_id,
            connection_id=connection_id,
            meter_count=meter_count,
        )
        checkout_url = billing_result.get("checkout_url")
    except Exception as exc:
        log.warning("utilityapi_callback_billing_failed", error=str(exc))

    message = "Authorization successful. Initial data sync complete."
    if checkout_url:
        message += " Please complete payment to activate meter monitoring."

    return AuthorizationCallbackResponse(
        connection_id=connection_id,
        status="active",
        message=message,
    )


# ---------------------------------------------------------------------------
# POST /{connection_id}/sync  —  manual sync trigger
# ---------------------------------------------------------------------------


@router.post(
    "/{connection_id}/sync",
    response_model=SyncResultResponse,
    summary="Trigger manual UtilityAPI sync for a connection",
)
async def trigger_sync(
    connection_id: uuid.UUID,
    current_user: SessionData = Depends(get_current_user),
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
    result = await sync_svc.sync_connection(str(connection_id))

    return SyncResultResponse(
        connection_id=result["connection_id"],
        success=result["success"],
        new_rates_found=result["new_rates_found"],
        error=result.get("error"),
        synced_at=result["synced_at"],
    )


# ---------------------------------------------------------------------------
# GET /{connection_id}/sync-status  —  sync metadata
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}/sync-status",
    response_model=SyncStatusResponse,
    summary="Get sync status for a connection",
)
async def get_sync_status(
    connection_id: uuid.UUID,
    current_user: SessionData = Depends(get_current_user),
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
    status_data = await sync_svc.get_sync_status(str(connection_id))

    if status_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    return SyncStatusResponse(**status_data)
