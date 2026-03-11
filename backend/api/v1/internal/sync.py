"""
Internal sync endpoints.

Covers: /sync-connections
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session

logger = structlog.get_logger(__name__)

router = APIRouter()


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
        raise HTTPException(
            status_code=500, detail=f"Connection sync failed: {str(exc)}"
        )
