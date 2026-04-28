"""
Portal connection endpoints — Phase 3.

Routes (mounted under the /connections prefix in router.py):
  POST /portal                             — create portal-scrape connection with encrypted credentials
  POST /portal/{connection_id}/scrape      — trigger a manual portal scrape

Design decisions
----------------
- Passwords are encrypted with AES-256-GCM via ``encrypt_field()`` and stored
  as base64-encoded bytes in ``portal_password_encrypted``.  The plaintext is
  never logged or returned.
- Scrape results are persisted to ``connection_extracted_rates`` (same table
  used by bill_upload and email_import) so downstream analytics work unchanged.
- ``portal_scrape_status`` / ``portal_last_scraped_at`` on ``user_connections``
  are updated after every scrape attempt (success or failure).

Registration note:
  portal_scrape.router must be included in router.py BEFORE crud.router so
  that ``/portal`` and ``/portal/{connection_id}/scrape`` are not captured by
  the /{connection_id} wildcard.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import SessionData, get_db_session
from api.v1.connections.common import require_paid_tier
from models.connections import (CreatePortalConnectionRequest,
                                PortalConnectionResponse, PortalScrapeResponse)
from utils.encryption import decrypt_field, encrypt_field

router = APIRouter()
logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# POST /portal  —  create a portal-scrape connection
# ---------------------------------------------------------------------------


@router.post(
    "/portal",
    response_model=PortalConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create portal-scrape connection",
)
async def create_portal_connection(
    payload: CreatePortalConnectionRequest,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> PortalConnectionResponse:
    """
    Store portal credentials (encrypted) and create a user_connections record.

    The ``portal_password`` is encrypted with AES-256-GCM and stored as a
    base64-encoded string.  The plaintext password is never persisted and is
    not included in the response.

    Consent is required (validated by ``CreatePortalConnectionRequest``).
    """
    log = logger.bind(
        user_id=current_user.user_id,
        supplier_id=str(payload.supplier_id),
    )

    # Verify the supplier exists in the registry
    supplier_result = await db.execute(
        text("SELECT id, name FROM supplier_registry WHERE id = :sid"),
        {"sid": str(payload.supplier_id)},
    )
    supplier_row = supplier_result.fetchone()
    if supplier_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found.",
        )

    # Encrypt credentials and encode as base64 for TEXT/VARCHAR column storage
    try:
        encrypted_pw = encrypt_field(payload.portal_password)
        encrypted_pw_b64 = base64.b64encode(encrypted_pw).decode("ascii")
        encrypted_un = encrypt_field(payload.portal_username)
        encrypted_un_b64 = base64.b64encode(encrypted_un).decode("ascii")
    except RuntimeError as exc:
        log.error("portal_encryption_config_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Portal connections are temporarily unavailable due to a configuration issue. Please try bill upload instead.",
        ) from exc

    connection_id = str(uuid4())

    await db.execute(
        text("""
            INSERT INTO user_connections (
                id,
                user_id,
                connection_type,
                supplier_id,
                supplier_name,
                status,
                portal_username,
                portal_password_encrypted,
                portal_login_url,
                portal_scrape_status,
                created_at
            ) VALUES (
                :id,
                :user_id,
                'portal_scrape',
                :supplier_id,
                :supplier_name,
                'active',
                :username,
                :password_encrypted,
                :login_url,
                'pending',
                NOW()
            )
        """),
        {
            "id": connection_id,
            "user_id": current_user.user_id,
            "supplier_id": str(payload.supplier_id),
            "supplier_name": supplier_row[1],
            "username": encrypted_un_b64,
            "password_encrypted": encrypted_pw_b64,
            "login_url": payload.portal_login_url,
        },
    )
    await db.commit()

    log.info("portal_connection_created", connection_id=connection_id)

    return PortalConnectionResponse(
        connection_id=connection_id,
        supplier_id=str(payload.supplier_id),
        portal_username=payload.portal_username,
        portal_login_url=payload.portal_login_url,
        portal_scrape_status="pending",
        portal_last_scraped_at=None,
    )


# ---------------------------------------------------------------------------
# POST /portal/{connection_id}/scrape  —  trigger a manual scrape
# ---------------------------------------------------------------------------


@router.post(
    "/portal/{connection_id}/scrape",
    response_model=PortalScrapeResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger a manual portal scrape",
)
async def trigger_portal_scrape(
    connection_id: uuid.UUID,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> PortalScrapeResponse:
    """
    Decrypt the stored portal credentials and call ``PortalScraperService``
    to extract current billing rate data.

    Rates found are persisted to ``connection_extracted_rates``.
    ``portal_scrape_status`` and ``portal_last_scraped_at`` are updated
    regardless of whether the scrape succeeded or failed.

    Returns a ``PortalScrapeResponse`` with ``status``, ``rates_extracted``,
    and any ``error`` message.
    """

    log = logger.bind(connection_id=connection_id, user_id=current_user.user_id)

    # Fetch connection — must belong to the current user and be portal_scrape type
    conn_result = await db.execute(
        text("""
            SELECT
                id,
                user_id,
                supplier_id,
                portal_username,
                portal_password_encrypted,
                portal_login_url,
                portal_scrape_status
            FROM user_connections
            WHERE id = :cid
              AND user_id = :uid
              AND connection_type = 'portal_scrape'
        """),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    conn_row = conn_result.fetchone()
    if conn_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portal connection not found.",
        )

    (
        _conn_id,
        _user_id,
        supplier_id,
        portal_username_enc,
        portal_password_encrypted,
        portal_login_url,
        _scrape_status,
    ) = conn_row

    # Decrypt portal credentials
    try:
        portal_password = decrypt_field(base64.b64decode(portal_password_encrypted))
        portal_username = decrypt_field(base64.b64decode(portal_username_enc))
    except Exception as exc:
        log.error("portal_credential_decrypt_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt portal credentials.",
        ) from exc

    # Perform the scrape
    scrape_result = await _run_scrape(
        username=portal_username,
        password=portal_password,
        login_url=portal_login_url or "",
        supplier_id=str(supplier_id) if supplier_id else "",
        log=log,
    )

    scraped_at = datetime.now(UTC)
    new_status = "active" if scrape_result["success"] else "error"
    rates_extracted = len(scrape_result.get("rates", []))

    # Persist extracted rates to connection_extracted_rates
    if scrape_result["success"] and scrape_result.get("rates"):
        for rate_entry in scrape_result["rates"]:
            rate_id = str(uuid4())
            await db.execute(
                text("""
                    INSERT INTO connection_extracted_rates (
                        id,
                        connection_id,
                        rate_per_kwh,
                        effective_date,
                        source,
                        raw_label,
                        created_at
                    ) VALUES (
                        :id,
                        :connection_id,
                        :rate_per_kwh,
                        NOW(),
                        'portal_scrape',
                        :raw_label,
                        NOW()
                    )
                """),
                {
                    "id": rate_id,
                    "connection_id": connection_id,
                    "rate_per_kwh": rate_entry["rate_per_kwh"],
                    "raw_label": rate_entry.get("label", "portal_scrape"),
                },
            )

    # Update portal_scrape_status and portal_last_scraped_at
    await db.execute(
        text("""
            UPDATE user_connections
            SET portal_scrape_status = :new_status,
                portal_last_scraped_at = :scraped_at
            WHERE id = :cid
        """),
        {
            "new_status": new_status,
            "scraped_at": scraped_at,
            "cid": connection_id,
        },
    )
    await db.commit()

    log.info(
        "portal_scrape_complete",
        success=scrape_result["success"],
        rates_extracted=rates_extracted,
    )

    return PortalScrapeResponse(
        connection_id=str(connection_id),
        status="success" if scrape_result["success"] else "failed",
        rates_extracted=rates_extracted,
        error=scrape_result.get("error"),
        scraped_at=scraped_at,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _run_scrape(
    username: str,
    password: str,
    login_url: str,
    supplier_id: str,
    log: structlog.BoundLogger,
) -> dict:
    """Run ``PortalScraperService.scrape_portal()`` as an async context manager."""
    from services.portal_scraper_service import PortalScraperService

    try:
        async with PortalScraperService() as svc:
            return await svc.scrape_portal(
                username=username,
                password=password,
                login_url=login_url,
                supplier_id=supplier_id,
            )
    except Exception as exc:
        log.error("portal_scrape_helper_error", error=str(exc))
        return {
            "success": False,
            "rates": [],
            "error": f"Scrape failed: {exc}",
        }
