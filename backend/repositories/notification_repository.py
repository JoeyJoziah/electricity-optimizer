"""
Notification Repository

Data access layer for the notifications table.  Provides query methods
beyond what NotificationService covers, specifically:

  - get_by_id            — fetch a single notification row
  - update_delivery      — patch delivery-tracking columns after a send attempt
  - get_by_delivery_status — list notifications in a given delivery state
  - get_by_channel       — list notifications sent via a specific channel

These methods are used by NotificationDispatcher to persist delivery outcomes
and by internal reporting / retry logic that needs to query by status or
channel.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    Notification,
    NotificationDeliveryUpdate,
)
from repositories.base import NotFoundError, RepositoryError

logger = structlog.get_logger(__name__)

# Ordered column list used in SELECT queries — must stay in sync with the table
# schema after migrations 015, 026, 029, and 032.
_NOTIFICATION_COLUMNS = (
    "id, user_id, type, title, body, read_at, created_at, "
    "metadata, delivery_channel, delivery_status, delivered_at, "
    "delivery_metadata, retry_count, error_message"
)


def _row_to_notification(row) -> Notification:
    """Map a DB row (Mapping or tuple by position) to a Notification model."""
    # SQLAlchemy RowMapping supports key-based access.
    return Notification(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        type=row["type"],
        title=row["title"],
        body=row["body"],
        read_at=row["read_at"],
        created_at=row["created_at"],
        metadata=row["metadata"],
        delivery_channel=row["delivery_channel"],
        delivery_status=row["delivery_status"] or "pending",
        delivered_at=row["delivered_at"],
        delivery_metadata=row["delivery_metadata"] or {},
        retry_count=row["retry_count"] or 0,
        error_message=row["error_message"],
    )


class NotificationRepository:
    """
    Repository for the notifications table.

    Focused on delivery-tracking read/write operations.  General CRUD
    (create, mark_read, list unread) lives in NotificationService to
    preserve backwards compatibility with existing call sites.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # =========================================================================
    # Read operations
    # =========================================================================

    async def get_by_id(self, notification_id: str, user_id: str) -> Optional[Notification]:
        """Return the notification row for the given ID owned by user_id, or None."""
        try:
            result = await self._db.execute(
                text(
                    f"SELECT {_NOTIFICATION_COLUMNS}"
                    " FROM notifications"
                    " WHERE id = :nid AND user_id = :uid"
                    " LIMIT 1"
                ),
                {"nid": notification_id, "uid": user_id},
            )
            row = result.mappings().first()
            if row is None:
                return None
            return _row_to_notification(row)
        except Exception as exc:
            logger.error(
                "notification_repo_get_by_id_failed",
                notification_id=notification_id,
                error=str(exc),
            )
            raise RepositoryError(
                f"Failed to fetch notification {notification_id}", exc
            )

    async def get_by_delivery_status(
        self,
        user_id: str,
        status: DeliveryStatus,
        limit: int = 50,
    ) -> List[Notification]:
        """
        Return up to ``limit`` notifications for ``user_id`` with the given
        ``delivery_status``, ordered newest-first.

        This powers dashboard views ("show me all failed notifications") and
        the retry scheduler ("find all pending notifications older than 5 min").
        """
        try:
            result = await self._db.execute(
                text(
                    f"SELECT {_NOTIFICATION_COLUMNS}"
                    " FROM notifications"
                    " WHERE user_id = :uid"
                    "   AND delivery_status = :status"
                    " ORDER BY created_at DESC"
                    " LIMIT :lim"
                ),
                {"uid": user_id, "status": status, "lim": limit},
            )
            rows = result.mappings().fetchall()
            return [_row_to_notification(r) for r in rows]
        except Exception as exc:
            logger.error(
                "notification_repo_get_by_status_failed",
                user_id=user_id,
                status=status,
                error=str(exc),
            )
            raise RepositoryError(
                f"Failed to query notifications by status={status}", exc
            )

    async def get_by_channel(
        self,
        user_id: str,
        channel: DeliveryChannel,
        limit: int = 50,
    ) -> List[Notification]:
        """
        Return up to ``limit`` notifications for ``user_id`` delivered via
        ``channel``, ordered newest-first.

        Supports analytics use-cases such as "how many push notifications did
        this user receive this week?" or "find all email notifications that
        bounced".
        """
        try:
            result = await self._db.execute(
                text(
                    f"SELECT {_NOTIFICATION_COLUMNS}"
                    " FROM notifications"
                    " WHERE user_id = :uid"
                    "   AND delivery_channel = :channel"
                    " ORDER BY created_at DESC"
                    " LIMIT :lim"
                ),
                {"uid": user_id, "channel": channel, "lim": limit},
            )
            rows = result.mappings().fetchall()
            return [_row_to_notification(r) for r in rows]
        except Exception as exc:
            logger.error(
                "notification_repo_get_by_channel_failed",
                user_id=user_id,
                channel=channel,
                error=str(exc),
            )
            raise RepositoryError(
                f"Failed to query notifications by channel={channel}", exc
            )

    # =========================================================================
    # Write operations
    # =========================================================================

    async def update_delivery(
        self,
        notification_id: str,
        update: NotificationDeliveryUpdate,
    ) -> bool:
        """
        Patch the delivery-tracking columns on an existing notification row.

        Only non-None fields from ``update`` are written.  ``delivery_status``
        is always updated since it is required on the schema.

        Returns:
            True  — row was found and updated.
            False — no row matched ``notification_id``.
        """
        set_clauses: List[str] = ["delivery_status = :delivery_status"]
        params: Dict[str, Any] = {"nid": notification_id, "delivery_status": update.delivery_status}

        if update.delivery_channel is not None:
            set_clauses.append("delivery_channel = :delivery_channel")
            params["delivery_channel"] = update.delivery_channel

        if update.delivered_at is not None:
            set_clauses.append("delivered_at = :delivered_at")
            params["delivered_at"] = update.delivered_at

        if update.delivery_metadata is not None:
            set_clauses.append("delivery_metadata = :delivery_metadata::jsonb")
            params["delivery_metadata"] = json.dumps(update.delivery_metadata)

        if update.retry_count is not None:
            set_clauses.append("retry_count = :retry_count")
            params["retry_count"] = update.retry_count

        if update.error_message is not None:
            set_clauses.append("error_message = :error_message")
            params["error_message"] = update.error_message

        sql = (
            "UPDATE notifications"
            " SET " + ", ".join(set_clauses) +
            " WHERE id = :nid"
        )

        try:
            result = await self._db.execute(text(sql), params)
            await self._db.commit()
            updated = result.rowcount > 0
            if updated:
                logger.info(
                    "notification_delivery_updated",
                    notification_id=notification_id,
                    delivery_status=update.delivery_status,
                    delivery_channel=update.delivery_channel,
                )
            else:
                logger.warning(
                    "notification_delivery_update_no_match",
                    notification_id=notification_id,
                )
            return updated
        except Exception as exc:
            logger.error(
                "notification_repo_update_delivery_failed",
                notification_id=notification_id,
                error=str(exc),
            )
            raise RepositoryError(
                f"Failed to update delivery tracking for {notification_id}", exc
            )
