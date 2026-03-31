"""
Internal portal scanning endpoint.

Route:
  POST /scrape-portals  — batch-scrape all active portal_scrape connections

Design decisions
----------------
- Uses ``asyncio.gather + asyncio.Semaphore(2)`` to parallelize scrapes while
  limiting concurrency to 2 simultaneous HTTP sessions.  Portal scraping is
  slow (multiple HTTP round-trips) so a narrow semaphore prevents exhausting
  the server's connection pool or triggering utility-side rate limiting.
- Each scrape is fully isolated: a failure for one connection does not abort
  others.
- Extracted rates are persisted to ``connection_extracted_rates``; the portal
  status columns on ``user_connections`` are updated after each attempt.
- Credentials are decrypted in memory only for the duration of the scrape and
  are never logged.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from utils.encryption import decrypt_field

router = APIRouter()
logger = structlog.get_logger(__name__)

_SEMAPHORE_LIMIT = 2  # max concurrent portal HTTP sessions


# ---------------------------------------------------------------------------
# POST /scrape-portals
# ---------------------------------------------------------------------------


@router.post("/scrape-portals", tags=["Internal"])
async def scrape_all_portals(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Batch-scrape all active portal_scrape connections.

    Steps:
      1. Query ``user_connections`` for all ``connection_type = 'portal_scrape'``
         rows with ``status = 'active'``.
      2. For each connection: decrypt the stored password, call
         ``PortalScraperService.scrape_portal()``, persist any rates found,
         and update the scrape status columns.
      3. Run up to ``_SEMAPHORE_LIMIT`` scrapes concurrently via
         ``asyncio.gather`` + ``asyncio.Semaphore``.

    Returns a summary dict: ``{total, succeeded, failed, errors}``.
    """
    # 1. Fetch all active portal connections
    result = await db.execute(text("""
            SELECT
                id,
                user_id,
                supplier_id,
                portal_username,
                portal_password_encrypted,
                portal_login_url
            FROM user_connections
            WHERE connection_type = 'portal_scrape'
              AND status = 'active'
            ORDER BY portal_last_scraped_at ASC NULLS FIRST
        """))
    rows = result.fetchall()

    if not rows:
        logger.info("scrape_portals_no_connections")
        return {
            "status": "ok",
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "errors": [],
        }

    logger.info("scrape_portals_start", total=len(rows))

    # 2. Run scrapes sequentially to avoid shared AsyncSession corruption.
    #    The semaphore inside _scrape_one still gates external HTTP concurrency.
    sem = asyncio.Semaphore(_SEMAPHORE_LIMIT)
    results = []
    for row in rows:
        try:
            result = await _scrape_one(
                db=db,
                sem=sem,
                connection_id=str(row[0]),
                user_id=str(row[1]),
                supplier_id=str(row[2]) if row[2] else "",
                portal_username_enc=row[3],
                portal_password_encrypted=row[4],
                portal_login_url=row[5] or "",
            )
            results.append(result)
        except Exception as exc:
            results.append(exc)

    # 3. Tally outcomes
    succeeded = 0
    failed = 0
    errors: list[str] = []

    for i, res in enumerate(results):
        conn_id = str(rows[i][0])
        if isinstance(res, Exception):
            failed += 1
            errors.append(f"{conn_id}: Portal scrape task failed. See server logs for details.")
            logger.exception("scrape_portals_task_exception", connection_id=conn_id, error=str(res))
        elif res.get("success"):
            succeeded += 1
        else:
            failed += 1
            if res.get("error"):
                errors.append(f"{conn_id}: {res['error']}")

    logger.info(
        "scrape_portals_complete",
        total=len(rows),
        succeeded=succeeded,
        failed=failed,
    )

    return {
        "status": "ok",
        "total": len(rows),
        "succeeded": succeeded,
        "failed": failed,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Private: per-connection scrape task
# ---------------------------------------------------------------------------


async def _scrape_one(
    db: AsyncSession,
    sem: asyncio.Semaphore,
    connection_id: str,
    user_id: str,
    supplier_id: str,
    portal_username_enc: str,
    portal_password_encrypted: str,
    portal_login_url: str,
) -> dict:
    """
    Scrape a single portal connection under the concurrency semaphore.

    Returns ``{"success": bool, "rates_extracted": int, "error": str | None}``.
    """
    from services.portal_scraper_service import PortalScraperService

    log = logger.bind(connection_id=connection_id, user_id=user_id)

    # Decrypt portal credentials
    try:
        portal_password = decrypt_field(base64.b64decode(portal_password_encrypted))
        portal_username = decrypt_field(base64.b64decode(portal_username_enc))
    except Exception as exc:
        log.exception("portal_decrypt_error", error=str(exc))
        await _update_status(db, connection_id, "error", datetime.now(UTC))
        return {
            "success": False,
            "rates_extracted": 0,
            "error": "Credential decryption failed. See server logs for details.",
        }

    async with sem:
        log.info("portal_scrape_start")
        try:
            async with PortalScraperService() as svc:
                scrape_result = await svc.scrape_portal(
                    username=portal_username,
                    password=portal_password,
                    login_url=portal_login_url,
                    supplier_id=supplier_id,
                )
        except Exception as exc:
            log.exception("portal_scrape_exception", error=str(exc))
            scrape_result = {
                "success": False,
                "rates": [],
                "error": "Portal scrape failed. See server logs for details.",
            }

    scraped_at = datetime.now(UTC)
    rates = scrape_result.get("rates", [])
    rates_extracted = len(rates)
    new_status = "active" if scrape_result["success"] else "error"

    # Persist extracted rates
    if scrape_result["success"] and rates:
        for rate_entry in rates:
            rate_id = str(uuid4())
            try:
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
            except Exception as exc:
                log.error("portal_rate_persist_error", rate_id=rate_id, error=str(exc))

    # Update scrape status columns
    await _update_status(db, connection_id, new_status, scraped_at)

    try:
        await db.commit()
    except Exception as exc:
        log.error("portal_commit_error", error=str(exc))
        await db.rollback()

    log.info(
        "portal_scrape_task_complete",
        success=scrape_result["success"],
        rates_extracted=rates_extracted,
    )

    return {
        "success": scrape_result["success"],
        "rates_extracted": rates_extracted,
        "error": scrape_result.get("error"),
    }


async def _update_status(
    db: AsyncSession,
    connection_id: str,
    new_status: str,
    scraped_at: datetime,
) -> None:
    """Update portal_scrape_status and portal_last_scraped_at on the connection row."""
    try:
        await db.execute(
            text("""
                UPDATE user_connections
                SET portal_scrape_status  = :new_status,
                    portal_last_scraped_at = :scraped_at
                WHERE id = :cid
            """),
            {
                "new_status": new_status,
                "scraped_at": scraped_at,
                "cid": connection_id,
            },
        )
    except Exception as exc:
        logger.error("portal_update_status_error", connection_id=connection_id, error=str(exc))
