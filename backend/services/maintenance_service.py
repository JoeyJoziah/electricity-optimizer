"""
Maintenance Service

Provides data retention and cleanup operations for housekeeping tasks:
- Activity log retention (default: 365 days)
- Bill upload record and file cleanup (default: 730 days)
- Stale bill-upload parse sweep (in-flight for more than 15 minutes -> failed)
- Weather cache retention (default: 30 days)
- Scraped rates retention (default: 90 days)
- Market intelligence retention (default: 180 days)

These are designed to be triggered via the internal API (API-key protected)
on a scheduled basis (e.g., nightly or weekly cron).
"""

import os
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# A bill parse runs in a FastAPI BackgroundTask. If the process restarts
# mid-parse nothing ever moves the row out of its in-flight status, so the
# frontend polls forever. Rows still in-flight after this long are abandoned.
STALE_UPLOAD_MINUTES = 15
STALE_UPLOAD_ERROR = (
    "Processing did not finish (the server restarted or timed out while parsing). "
    "Please retry the upload."
)


class MaintenanceService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def cleanup_activity_logs(self, retention_days: int = 365):
        """Delete activity logs older than retention period."""
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        try:
            result = await self._db.execute(
                text('DELETE FROM activity_logs WHERE "timestamp" < :cutoff'),
                {"cutoff": cutoff},
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        count = result.rowcount
        logger.info("activity_logs_cleaned", deleted=count, retention_days=retention_days)
        return {"deleted": count, "retention_days": retention_days}

    async def cleanup_old_prices(self, retention_days: int = 365):
        """Call the PL/pgSQL cleanup_old_prices function."""
        try:
            result = await self._db.execute(
                text("SELECT cleanup_old_prices(:days)"),
                {"days": retention_days},
            )
            deleted = result.scalar() or 0
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        logger.info("old_prices_cleaned", deleted=deleted, retention_days=retention_days)
        return {"deleted": deleted, "retention_days": retention_days}

    async def cleanup_old_observations(self, retention_days: int = 90):
        """Call the PL/pgSQL cleanup_old_observations function."""
        try:
            result = await self._db.execute(
                text("SELECT cleanup_old_observations(:days)"),
                {"days": retention_days},
            )
            deleted = result.scalar() or 0
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        logger.info("old_observations_cleaned", deleted=deleted, retention_days=retention_days)
        return {"deleted": deleted, "retention_days": retention_days}

    async def cleanup_expired_uploads(self, retention_days: int = 730):
        """Delete bill upload records and files older than retention period."""
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        # Get file paths before deleting records
        result = await self._db.execute(
            text("SELECT id, storage_key FROM bill_uploads WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        old_uploads = result.fetchall()

        if not old_uploads:
            return {"deleted": 0, "retention_days": retention_days}

        # connection_extracted_rates has no reference to bill_uploads (it is keyed
        # by connection_id), so there is nothing to delete there first.
        try:
            # Delete upload records
            await self._db.execute(
                text("DELETE FROM bill_uploads WHERE created_at < :cutoff"),
                {"cutoff": cutoff},
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise

        # Clean up files (best-effort — failures are non-fatal)
        for row in old_uploads:
            # storage_key is relative to the uploads directory (see BillParserService)
            file_path = os.path.join("uploads", row[1]) if row[1] else None
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

        count = len(old_uploads)
        logger.info("uploads_cleaned", deleted=count, retention_days=retention_days)
        return {"deleted": count, "retention_days": retention_days}

    async def sweep_stale_bill_uploads(self, stale_minutes: int = STALE_UPLOAD_MINUTES):
        """Mark bill uploads stuck in an in-flight parse status as failed.

        ``pending`` is set on upload/reparse and ``processing`` when the parser
        starts; both bump ``updated_at``, so a row whose ``updated_at`` is older
        than the cutoff has had no parser activity for ``stale_minutes``.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=stale_minutes)
        try:
            result = await self._db.execute(
                text("""
                    UPDATE bill_uploads
                    SET parse_status = 'failed',
                        parse_error  = :error,
                        updated_at   = NOW()
                    WHERE parse_status IN ('pending', 'processing')
                      AND updated_at < :cutoff
                """),
                {"error": STALE_UPLOAD_ERROR, "cutoff": cutoff},
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        count = result.rowcount
        logger.info("stale_bill_uploads_swept", swept=count, stale_minutes=stale_minutes)
        return {"swept": count, "stale_minutes": stale_minutes}

    async def cleanup_weather_cache(self, retention_days: int = 30):
        """Delete weather cache entries older than retention period."""
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        try:
            result = await self._db.execute(
                text("DELETE FROM weather_cache WHERE fetched_at < :cutoff"),
                {"cutoff": cutoff},
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        count = result.rowcount
        logger.info("weather_cache_cleaned", deleted=count, retention_days=retention_days)
        return {"deleted": count, "retention_days": retention_days}

    async def cleanup_scraped_rates(self, retention_days: int = 90):
        """Delete scraped rate entries older than retention period."""
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        try:
            result = await self._db.execute(
                text("DELETE FROM scraped_rates WHERE fetched_at < :cutoff"),
                {"cutoff": cutoff},
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        count = result.rowcount
        logger.info("scraped_rates_cleaned", deleted=count, retention_days=retention_days)
        return {"deleted": count, "retention_days": retention_days}

    async def cleanup_market_intelligence(self, retention_days: int = 180):
        """Delete market intelligence entries older than retention period."""
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        try:
            result = await self._db.execute(
                text("DELETE FROM market_intelligence WHERE fetched_at < :cutoff"),
                {"cutoff": cutoff},
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        count = result.rowcount
        logger.info("market_intelligence_cleaned", deleted=count, retention_days=retention_days)
        return {"deleted": count, "retention_days": retention_days}

    async def cleanup_stripe_processed_events(self, retention_hours: int = 72):
        """Delete Stripe webhook idempotency records older than retention window.

        Stripe retries webhooks for up to 72 hours.  Records older than that
        window will never be replayed, so they can be safely pruned to keep
        the table small.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=retention_hours)
        try:
            result = await self._db.execute(
                text("DELETE FROM stripe_processed_events WHERE processed_at < :cutoff"),
                {"cutoff": cutoff},
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        count = result.rowcount
        logger.info(
            "stripe_processed_events_cleaned",
            deleted=count,
            retention_hours=retention_hours,
        )
        return {"deleted": count, "retention_hours": retention_hours}
