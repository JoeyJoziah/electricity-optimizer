"""
Maintenance Service

Provides data retention and cleanup operations for housekeeping tasks:
- Activity log retention (default: 365 days)
- Bill upload record and file cleanup (default: 730 days)

These are designed to be triggered via the internal API (API-key protected)
on a scheduled basis (e.g., nightly or weekly cron).
"""

import os
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class MaintenanceService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def cleanup_activity_logs(self, retention_days: int = 365):
        """Delete activity logs older than retention period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await self._db.execute(
            text("DELETE FROM activity_logs WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await self._db.commit()
        count = result.rowcount
        logger.info("activity_logs_cleaned", deleted=count, retention_days=retention_days)
        return {"deleted": count, "retention_days": retention_days}

    async def cleanup_old_prices(self, retention_days: int = 365):
        """Call the PL/pgSQL cleanup_old_prices function."""
        result = await self._db.execute(
            text("SELECT cleanup_old_prices(:days)"),
            {"days": retention_days},
        )
        deleted = result.scalar() or 0
        await self._db.commit()
        logger.info("old_prices_cleaned", deleted=deleted, retention_days=retention_days)
        return {"deleted": deleted, "retention_days": retention_days}

    async def cleanup_old_observations(self, retention_days: int = 90):
        """Call the PL/pgSQL cleanup_old_observations function."""
        result = await self._db.execute(
            text("SELECT cleanup_old_observations(:days)"),
            {"days": retention_days},
        )
        deleted = result.scalar() or 0
        await self._db.commit()
        logger.info("old_observations_cleaned", deleted=deleted, retention_days=retention_days)
        return {"deleted": deleted, "retention_days": retention_days}

    async def cleanup_expired_uploads(self, retention_days: int = 730):
        """Delete bill upload records and files older than retention period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # Get file paths before deleting records
        result = await self._db.execute(
            text("SELECT id, file_path FROM bill_uploads WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        old_uploads = result.fetchall()

        if not old_uploads:
            return {"deleted": 0, "retention_days": retention_days}

        # Delete extracted rates first (FK dependency)
        upload_ids = [str(r[0]) for r in old_uploads]
        if upload_ids:
            await self._db.execute(
                text(
                    "DELETE FROM connection_extracted_rates"
                    " WHERE bill_upload_id = ANY(:ids)"
                ),
                {"ids": upload_ids},
            )

        # Delete upload records
        await self._db.execute(
            text("DELETE FROM bill_uploads WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await self._db.commit()

        # Clean up files (best-effort — failures are non-fatal)
        for row in old_uploads:
            file_path = row[1]
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

        count = len(old_uploads)
        logger.info("uploads_cleaned", deleted=count, retention_days=retention_days)
        return {"deleted": count, "retention_days": retention_days}
