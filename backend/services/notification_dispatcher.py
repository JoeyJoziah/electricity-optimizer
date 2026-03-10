"""
NotificationDispatcher

Strategy-pattern dispatcher that routes notifications across three delivery
channels — in-app (notifications table), push (OneSignal), and email — with
optional deduplication via a cooldown window.

Usage:
    dispatcher = NotificationDispatcher(
        db=db,
        notification_service=NotificationService(db),
        push_service=PushNotificationService(),
        email_service=EmailService(),
    )
    result = await dispatcher.send(
        user_id=user_id,
        type="price_alert",
        title="Low price detected",
        body="Your region hit $0.08/kWh",
        channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH],
        email_to="user@example.com",
        dedup_key="price_alert:us_ct",
        cooldown_seconds=3600,
    )
"""

from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.notification_service import NotificationService
from services.push_notification_service import PushNotificationService
from services.email_service import EmailService

logger = structlog.get_logger(__name__)

# Default cooldown applied when dedup_key is provided but cooldown_seconds is not.
_DEFAULT_COOLDOWN_SECONDS = 3600  # 1 hour


class NotificationChannel(str, Enum):
    IN_APP = "in_app"
    PUSH = "push"
    EMAIL = "email"


# Ordered from lowest cost to highest so fallback chains degrade gracefully.
ALL_CHANNELS: List[NotificationChannel] = [
    NotificationChannel.IN_APP,
    NotificationChannel.PUSH,
    NotificationChannel.EMAIL,
]


class NotificationDispatcher:
    """
    Routes a notification to one or more delivery channels.

    Channel behaviour:
        IN_APP  — Writes a row to the ``notifications`` table via
                  NotificationService.  Always available; cannot be
                  "unconfigured".
        PUSH    — Sends to OneSignal via PushNotificationService.  Skipped
                  gracefully when OneSignal is not configured.
        EMAIL   — Sends through Resend/SMTP via EmailService.  Requires
                  ``email_to`` to be provided in the send() call.

    Deduplication:
        When ``dedup_key`` is supplied the dispatcher checks the
        ``notifications`` table for an existing row with a matching
        ``dedup_key`` value in ``metadata`` that was created within the
        last ``cooldown_seconds``.  If one exists the send is skipped and
        the result dict contains ``"skipped_dedup": True``.

        The ``dedup_key`` is stored in the notification row's ``metadata``
        JSON column so it persists across restarts without a dedicated table.
    """

    def __init__(
        self,
        db: AsyncSession,
        notification_service: NotificationService,
        push_service: PushNotificationService,
        email_service: EmailService,
    ) -> None:
        self._db = db
        self._notification_service = notification_service
        self._push_service = push_service
        self._email_service = email_service

    # =========================================================================
    # Public API
    # =========================================================================

    async def send(
        self,
        user_id: str,
        type: str,
        title: str,
        body: Optional[str] = None,
        channels: Optional[List[NotificationChannel]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        dedup_key: Optional[str] = None,
        cooldown_seconds: Optional[int] = None,
        # Email-specific parameters
        email_to: Optional[str] = None,
        email_subject: Optional[str] = None,
        email_html: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch a notification to the requested channels.

        Args:
            user_id:          UUID string of the target user.
            type:             Notification type label (e.g. "price_alert").
            title:            Short notification heading.
            body:             Longer description text (optional).
            channels:         Channels to attempt.  Defaults to all three
                              channels when omitted.
            metadata:         Arbitrary dict stored in the ``metadata`` JSON
                              column on the in-app notification row.
            dedup_key:        When provided, skip delivery if a matching
                              notification was created within cooldown_seconds.
            cooldown_seconds: Dedup window in seconds.  Defaults to 3600 (1h)
                              when dedup_key is set but this is omitted.
            email_to:         Recipient address for EMAIL channel.
            email_subject:    Email subject line; defaults to ``title``.
            email_html:       HTML body for the email; defaults to ``body``.

        Returns:
            Dict with keys:
                skipped_dedup (bool)   — True when dedup suppressed delivery.
                channels (dict)        — Per-channel success flags, e.g.:
                                         {"in_app": True, "push": False}.
        """
        resolved_channels = channels if channels is not None else ALL_CHANNELS

        # ------------------------------------------------------------------
        # 1. Deduplication check
        # ------------------------------------------------------------------
        if dedup_key:
            window = cooldown_seconds if cooldown_seconds is not None else _DEFAULT_COOLDOWN_SECONDS
            duplicate = await self._is_duplicate(user_id, dedup_key, window)
            if duplicate:
                logger.info(
                    "notification_dedup_skipped",
                    user_id=user_id,
                    dedup_key=dedup_key,
                    cooldown_seconds=window,
                )
                return {"skipped_dedup": True, "channels": {}}

        # ------------------------------------------------------------------
        # 2. Merge dedup_key into metadata so we can query it later
        # ------------------------------------------------------------------
        effective_metadata: Dict[str, Any] = dict(metadata or {})
        if dedup_key:
            effective_metadata["dedup_key"] = dedup_key

        # ------------------------------------------------------------------
        # 3. Route to each channel — independent try/except per channel
        # ------------------------------------------------------------------
        results: Dict[str, bool] = {}

        for channel in resolved_channels:
            if channel == NotificationChannel.IN_APP:
                results[channel.value] = await self._send_in_app(
                    user_id=user_id,
                    type=type,
                    title=title,
                    body=body,
                    metadata=effective_metadata,
                )

            elif channel == NotificationChannel.PUSH:
                results[channel.value] = await self._send_push(
                    user_id=user_id,
                    title=title,
                    body=body or title,
                    metadata=effective_metadata,
                )

            elif channel == NotificationChannel.EMAIL:
                if not email_to:
                    logger.debug(
                        "notification_email_skipped_no_address",
                        user_id=user_id,
                        title=title,
                    )
                    results[channel.value] = False
                else:
                    results[channel.value] = await self._send_email(
                        to=email_to,
                        subject=email_subject or title,
                        body=body,
                        html=email_html,
                    )

        logger.info(
            "notification_dispatched",
            user_id=user_id,
            type=type,
            channels=list(results.keys()),
            results=results,
        )

        return {"skipped_dedup": False, "channels": results}

    # =========================================================================
    # Channel dispatch helpers
    # =========================================================================

    async def _send_in_app(
        self,
        user_id: str,
        type: str,
        title: str,
        body: Optional[str],
        metadata: Dict[str, Any],
    ) -> bool:
        """Write an in-app notification row.  Stores metadata as JSON."""
        try:
            # NotificationService.create does not expose a metadata param yet.
            # We write directly here so the metadata (incl. dedup_key) is
            # persisted without modifying the existing service API.
            if metadata:
                import json
                await self._db.execute(
                    text(
                        "INSERT INTO notifications"
                        " (user_id, type, title, body, metadata)"
                        " VALUES (:uid, :type, :title, :body, :meta::jsonb)"
                    ),
                    {
                        "uid": user_id,
                        "type": type,
                        "title": title,
                        "body": body,
                        "meta": json.dumps(metadata),
                    },
                )
                await self._db.commit()
                logger.info(
                    "notification_in_app_created",
                    user_id=user_id,
                    type=type,
                    title=title,
                )
            else:
                await self._notification_service.create(
                    user_id=user_id,
                    title=title,
                    body=body,
                    type=type,
                )
            return True
        except Exception as exc:
            logger.error(
                "notification_in_app_failed",
                user_id=user_id,
                error=str(exc),
            )
            return False

    async def _send_push(
        self,
        user_id: str,
        title: str,
        body: str,
        metadata: Dict[str, Any],
    ) -> bool:
        """Send a OneSignal push notification."""
        if not self._push_service.is_configured:
            logger.debug("notification_push_not_configured", user_id=user_id)
            return False
        try:
            return await self._push_service.send_push(
                user_id=user_id,
                title=title,
                message=body,
                data=metadata,
            )
        except Exception as exc:
            logger.error(
                "notification_push_failed",
                user_id=user_id,
                error=str(exc),
            )
            return False

    async def _send_email(
        self,
        to: str,
        subject: str,
        body: Optional[str],
        html: Optional[str],
    ) -> bool:
        """Send an email notification."""
        try:
            html_body = html or (
                f"<p>{body}</p>" if body else f"<p>{subject}</p>"
            )
            return await self._email_service.send(
                to=to,
                subject=subject,
                html_body=html_body,
                text_body=body,
            )
        except Exception as exc:
            logger.error(
                "notification_email_failed",
                to=to,
                error=str(exc),
            )
            return False

    # =========================================================================
    # Deduplication helpers
    # =========================================================================

    async def _is_duplicate(
        self,
        user_id: str,
        dedup_key: str,
        cooldown_seconds: int,
    ) -> bool:
        """Return True if a matching notification already exists in the cooldown window.

        Queries the ``notifications`` table for any row matching:
            user_id = :user_id
            AND metadata->>'dedup_key' = :dedup_key
            AND created_at >= :cutoff

        Returns:
            True  — a duplicate exists; the caller should skip delivery.
            False — no duplicate found; the caller may proceed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
        try:
            result = await self._db.execute(
                text("""
                    SELECT id
                    FROM notifications
                    WHERE user_id   = :user_id
                      AND metadata  IS NOT NULL
                      AND metadata  ->> 'dedup_key' = :dedup_key
                      AND created_at >= :cutoff
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {
                    "user_id": user_id,
                    "dedup_key": dedup_key,
                    "cutoff": cutoff,
                },
            )
            row = result.first()
            return row is not None
        except Exception as exc:
            # On query failure, allow delivery rather than silently suppressing.
            logger.warning(
                "notification_dedup_check_failed",
                user_id=user_id,
                dedup_key=dedup_key,
                error=str(exc),
            )
            return False
