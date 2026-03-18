"""
Internal sync endpoints.

Covers: /sync-connections, /sync-users
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/sync-users", tags=["Internal"])
async def sync_neon_users(db: AsyncSession = Depends(get_db_session)):
    """
    Backfill public.users for every account that exists in neon_auth.user
    but is absent from (or out of sync with) public.users.

    Safe to run multiple times — uses INSERT ... ON CONFLICT DO UPDATE so
    existing rows are only touched when email or name has changed.

    Protected by the router-level X-API-Key dependency (same as all internal
    routes — callers must supply the X-API-Key header).

    Returns counts of created, updated, and already-synced users.
    """
    # Pull every user from neon_auth that we manage.
    # neon_auth."user" is written exclusively by Better Auth; we never mutate it.
    fetch_query = text("""
        SELECT
            u.id::text          AS neon_id,
            u.email             AS email,
            COALESCE(u.name, '') AS name
        FROM neon_auth."user" u
        ORDER BY u."createdAt"
    """)
    rows = (await db.execute(fetch_query)).fetchall()

    if not rows:
        return {"status": "ok", "total": 0, "created": 0, "updated": 0, "skipped": 0}

    created = 0
    updated = 0
    skipped = 0
    errors: list[dict] = []

    for row in rows:
        neon_id, email, name = row.neon_id, row.email, row.name
        try:
            upsert = text("""
                INSERT INTO public.users (id, email, name, region, is_active, created_at, updated_at)
                VALUES (:id, :email, :name, NULL, true, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE
                    SET email      = EXCLUDED.email,
                        name       = CASE
                                         WHEN EXCLUDED.name <> '' THEN EXCLUDED.name
                                         ELSE public.users.name
                                     END,
                        updated_at = NOW()
                WHERE public.users.email <> EXCLUDED.email
                   OR (EXCLUDED.name <> '' AND public.users.name <> EXCLUDED.name)
                RETURNING id, (xmax = 0) AS is_insert
            """)
            result = await db.execute(
                upsert,
                {
                    "id": neon_id,
                    "email": email.lower(),
                    "name": name,
                },
            )
            row_result = result.first()
            if row_result is not None:
                if row_result.is_insert:
                    created += 1
                    logger.info("user_sync_created", user_id=neon_id, email=email)
                else:
                    updated += 1
                    logger.info("user_sync_updated", user_id=neon_id, email=email)
            else:
                skipped += 1
        except Exception as exc:
            logger.error("user_sync_row_failed", user_id=neon_id, email=email, error=str(exc))
            errors.append({"user_id": neon_id, "email": email, "error": str(exc)})
            # Continue with remaining rows — don't let one failure abort the batch
            await db.rollback()

    await db.commit()

    return {
        "status": "ok" if not errors else "partial",
        "total": len(rows),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


@router.post("/sync-connections", tags=["Internal"])
async def sync_connections(db: AsyncSession = Depends(get_db_session)):
    """
    Find all active connections due for sync and trigger sync for each.

    A connection is "due" when last_sync_at + sync_frequency_hours <= NOW()
    or when it has never been synced (last_sync_at IS NULL).

    Protected by the router-level X-API-Key dependency.
    """
    from services.connection_sync_service import ConnectionSyncService

    service = ConnectionSyncService(db)
    try:
        results = await service.sync_all_due()
        succeeded = sum(1 for r in results if r.get("success"))
        failed = len(results) - succeeded
        return {
            "status": "ok",
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }
    except Exception as exc:
        logger.error("sync_connections_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Connection sync failed. See server logs.")
