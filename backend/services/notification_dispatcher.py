"""
NotificationDispatcher

Strategy-pattern dispatcher that routes notifications across three delivery
channels — in-app (notifications table), push (OneSignal), and email — with
optional deduplication via a cooldown window.

Delivery tracking (migrations 029 + 032):
    After every channel attempt the dispatcher writes back to the
    ``notifications`` row via NotificationRepository.update_delivery(),
    recording:
      - delivery_channel  — which channel was used
      - delivery_status   — pending → sent (success) / failed (error)
      - delivered_at      — set when delivery_status becomes "sent"
      - retry_count       — incremented on each attempt beyond the first
      - error_message     — populated on failure for diagnostics

    Only the in-app channel creates a persistent row in the ``notifications``
    table; push and email are external services.  For push/email channels the
    delivery outcome is written to the in-app row when IN_APP is also part of
    the channel set (common case).  When IN_APP is not requested the push/email
    outcomes are returned in the result dict but not persisted.

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

import asyncio
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification import NotificationDeliveryUpdate
from repositories.notification_repository import NotificationRepository
from services.email_service import EmailService
from services.notification_service import NotificationService
from services.push_notification_service import PushNotificationService

logger = structlog.get_logger(__name__)

# Default cooldown applied when dedup_key is provided but cooldown_seconds is not.
_DEFAULT_COOLDOWN_SECONDS = 3600  # 1 hour


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    PUSH = "push"
    EMAIL = "email"


# Ordered from lowest cost to highest so fallback chains degrade gracefully.
ALL_CHANNELS: list[NotificationChannel] = [
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
        self._repo = NotificationRepository(db)

    # =========================================================================
    # Public API
    # =========================================================================

    async def send(
        self,
        user_id: str,
        type: str,
        title: str,
        body: str | None = None,
        channels: list[NotificationChannel] | None = None,
        metadata: dict[str, Any] | None = None,
        dedup_key: str | None = None,
        cooldown_seconds: int | None = None,
        # Email-specific parameters
        email_to: str | None = None,
        email_subject: str | None = None,
        email_html: str | None = None,
    ) -> dict[str, Any]:
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
                notification_id (str)  — ID of the in-app notification row
                                         when IN_APP channel was included, else
                                         None.
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
                return {"skipped_dedup": True, "channels": {}, "notification_id": None}

        # ------------------------------------------------------------------
        # 2. Merge dedup_key into metadata so we can query it later
        # ------------------------------------------------------------------
        effective_metadata: dict[str, Any] = dict(metadata or {})
        if dedup_key:
            effective_metadata["dedup_key"] = dedup_key

        # ------------------------------------------------------------------
        # 3. Route to each channel — IN_APP first (creates the row / notification_id),
        #    then PUSH and EMAIL concurrently (both are external HTTP calls).
        # ------------------------------------------------------------------
        results: dict[str, bool] = {}
        notification_id: str | None = None

        # Step 3a: IN_APP must run first — it creates the DB row whose ID is
        # needed by the push/email outcome-tracking helpers.
        if NotificationChannel.IN_APP in resolved_channels:
            nid, success = await self._send_in_app(
                user_id=user_id,
                type=type,
                title=title,
                body=body,
                metadata=effective_metadata,
            )
            results[NotificationChannel.IN_APP.value] = success
            if nid:
                notification_id = nid

        # Step 3b: PUSH and EMAIL are independent external HTTP calls — run concurrently.
        async def _dispatch_push() -> None:
            if NotificationChannel.PUSH not in resolved_channels:
                return
            success, error = await self._send_push(
                user_id=user_id,
                title=title,
                body=body or title,
                metadata=effective_metadata,
            )
            results[NotificationChannel.PUSH.value] = success
            if notification_id:
                await self._persist_channel_outcome(
                    notification_id=notification_id,
                    channel=NotificationChannel.PUSH.value,
                    success=success,
                    error=error,
                )

        async def _dispatch_email() -> None:
            if NotificationChannel.EMAIL not in resolved_channels:
                return
            if not email_to:
                logger.debug(
                    "notification_email_skipped_no_address",
                    user_id=user_id,
                    title=title,
                )
                results[NotificationChannel.EMAIL.value] = False
                return
            success, error = await self._send_email(
                to=email_to,
                subject=email_subject or title,
                body=body,
                html=email_html,
            )
            results[NotificationChannel.EMAIL.value] = success
            if notification_id:
                await self._persist_channel_outcome(
                    notification_id=notification_id,
                    channel=NotificationChannel.EMAIL.value,
                    success=success,
                    error=error,
                )

        # return_exceptions=True prevents one channel failure from aborting the
        # other, but it silently swallows exceptions unless we inspect the
        # return values.  Log any BaseException instances so failures are
        # visible in the log stream rather than being silently dropped.
        gather_results = await asyncio.gather(
            _dispatch_push(), _dispatch_email(), return_exceptions=True
        )
        for exc in gather_results:
            if isinstance(exc, BaseException):
                logger.error(
                    "notification_dispatch_unhandled_exception",
                    user_id=user_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        logger.info(
            "notification_dispatched",
            user_id=user_id,
            type=type,
            channels=list(results.keys()),
            results=results,
            notification_id=notification_id,
        )

        return {
            "skipped_dedup": False,
            "channels": results,
            "notification_id": notification_id,
        }

    # =========================================================================
    # Channel dispatch helpers
    # =========================================================================

    async def _send_in_app(
        self,
        user_id: str,
        type: str,
        title: str,
        body: str | None,
        metadata: dict[str, Any],
    ) -> tuple[str | None, bool]:
        """Write an in-app notification row with delivery_status='sent'.

        Returns:
            (notification_id, success) — notification_id is None on failure.
        """
        nid = str(uuid4())
        try:
            meta_json = json.dumps(metadata) if metadata else None
            if meta_json is not None:
                await self._db.execute(
                    text(
                        "INSERT INTO notifications"
                        " (id, user_id, type, title, body, metadata,"
                        "  delivery_channel, delivery_status, delivered_at)"
                        " VALUES (:id, :uid, :type, :title, :body, :meta::jsonb,"
                        "  'in_app', 'sent', NOW())"
                    ),
                    {
                        "id": nid,
                        "uid": user_id,
                        "type": type,
                        "title": title,
                        "body": body,
                        "meta": meta_json,
                    },
                )
            else:
                await self._db.execute(
                    text(
                        "INSERT INTO notifications"
                        " (id, user_id, type, title, body,"
                        "  delivery_channel, delivery_status, delivered_at)"
                        " VALUES (:id, :uid, :type, :title, :body,"
                        "  'in_app', 'sent', NOW())"
                    ),
                    {
                        "id": nid,
                        "uid": user_id,
                        "type": type,
                        "title": title,
                        "body": body,
                    },
                )
            await self._db.commit()
            logger.info(
                "notification_in_app_created",
                user_id=user_id,
                type=type,
                title=title,
                notification_id=nid,
            )
            return nid, True
        except Exception as exc:
            logger.error(
                "notification_in_app_failed",
                user_id=user_id,
                error=str(exc),
            )
            return None, False

    async def _send_push(
        self,
        user_id: str,
        title: str,
        body: str,
        metadata: dict[str, Any],
    ) -> tuple[bool, str | None]:
        """Send a OneSignal push notification.

        Returns:
            (success, error_message) — error_message is None on success.
        """
        if not self._push_service.is_configured:
            logger.debug("notification_push_not_configured", user_id=user_id)
            return False, "push service not configured"
        try:
            ok = await self._push_service.send_push(
                user_id=user_id,
                title=title,
                message=body,
                data=metadata,
            )
            return ok, None
        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                "notification_push_failed",
                user_id=user_id,
                error=error_msg,
            )
            return False, error_msg

    async def _send_email(
        self,
        to: str,
        subject: str,
        body: str | None,
        html: str | None,
    ) -> tuple[bool, str | None]:
        """Send an email notification.

        Returns:
            (success, error_message) — error_message is None on success.
        """
        try:
            html_body = html or (f"<p>{body}</p>" if body else f"<p>{subject}</p>")
            ok = await self._email_service.send(
                to=to,
                subject=subject,
                html_body=html_body,
                text_body=body,
            )
            return ok, None
        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                "notification_email_failed",
                to=to,
                error=error_msg,
            )
            return False, error_msg

    # =========================================================================
    # Delivery tracking helpers
    # =========================================================================

    async def _persist_channel_outcome(
        self,
        notification_id: str,
        channel: str,
        success: bool,
        error: str | None,
        retry_count: int | None = None,
    ) -> None:
        """Write the push/email delivery outcome back to the in-app row.

        This keeps the in-app notification row as the single source of truth
        for per-user delivery state regardless of which external channel was
        used.
        """
        if success:
            update = NotificationDeliveryUpdate(
                delivery_status="sent",
                delivery_channel=channel,  # type: ignore[arg-type]
                delivered_at=datetime.now(UTC),
                retry_count=retry_count,
            )
        else:
            update = NotificationDeliveryUpdate(
                delivery_status="failed",
                delivery_channel=channel,  # type: ignore[arg-type]
                error_message=error,
                retry_count=retry_count,
            )
        try:
            await self._repo.update_delivery(notification_id, update)
        except Exception as exc:
            # Non-fatal: we already attempted delivery; tracking failure should
            # not bubble up to the caller.
            logger.warning(
                "notification_delivery_tracking_failed",
                notification_id=notification_id,
                channel=channel,
                error=str(exc),
            )

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
        cutoff = datetime.now(UTC) - timedelta(seconds=cooldown_seconds)
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
