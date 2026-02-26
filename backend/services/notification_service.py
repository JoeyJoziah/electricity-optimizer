"""
Notification Service

Manages in-app notifications for users: creating, listing unread, counting,
and marking as read.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger(__name__)


class NotificationService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(
        self,
        user_id: str,
        title: str,
        body: str = None,
        type: str = "info",
    ) -> None:
        """Insert a new notification row for the given user."""
        await self._db.execute(
            text(
                "INSERT INTO notifications (user_id, type, title, body)"
                " VALUES (:uid, :type, :title, :body)"
            ),
            {"uid": user_id, "type": type, "title": title, "body": body},
        )
        await self._db.commit()
        logger.info("notification_created", user_id=user_id, type=type, title=title)

    async def get_unread(self, user_id: str) -> list[dict]:
        """Return up to 50 unread notifications for the user, newest first."""
        result = await self._db.execute(
            text(
                "SELECT id, type, title, body, created_at"
                " FROM notifications"
                " WHERE user_id = :uid AND read_at IS NULL"
                " ORDER BY created_at DESC"
                " LIMIT 50"
            ),
            {"uid": user_id},
        )
        rows = result.fetchall()
        return [
            {
                "id": str(r[0]),
                "type": r[1],
                "title": r[2],
                "body": r[3],
                "created_at": str(r[4]),
            }
            for r in rows
        ]

    async def get_unread_count(self, user_id: str) -> int:
        """Return the count of unread notifications for the user."""
        result = await self._db.execute(
            text(
                "SELECT COUNT(*) FROM notifications"
                " WHERE user_id = :uid AND read_at IS NULL"
            ),
            {"uid": user_id},
        )
        return result.scalar() or 0

    async def mark_read(self, user_id: str, notification_id: str) -> bool:
        """
        Mark a single notification as read.

        Returns True when the row was updated (was unread and owned by user),
        False when nothing was changed (not found or already read).
        """
        result = await self._db.execute(
            text(
                "UPDATE notifications SET read_at = NOW()"
                " WHERE id = :nid AND user_id = :uid AND read_at IS NULL"
            ),
            {"nid": notification_id, "uid": user_id},
        )
        await self._db.commit()
        updated = result.rowcount > 0
        if updated:
            logger.info(
                "notification_marked_read",
                user_id=user_id,
                notification_id=notification_id,
            )
        return updated
