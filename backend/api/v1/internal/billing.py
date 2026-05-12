"""
Internal billing endpoints.

Covers: /dunning-cycle
"""

from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/dunning-cycle", tags=["Internal"])
async def run_dunning_cycle(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Find overdue accounts (payment failing >7 days, user still on paid tier)
    and escalate: send final dunning email, downgrade to free.

    Protected by the router-level X-API-Key dependency.
    """
    from repositories.user_repository import UserRepository
    from services.dunning_service import DunningService
    from services.email_service import EmailService
    from services.notification_dispatcher import NotificationDispatcher
    from services.notification_service import NotificationService
    from services.push_notification_service import PushNotificationService

    # Build a NotificationDispatcher so dunning notifications reach all channels.
    try:
        dunning_dispatcher = NotificationDispatcher(
            db=db,
            notification_service=NotificationService(db),
            push_service=PushNotificationService(),
            email_service=EmailService(),
        )
    except Exception as exc:
        logger.warning("dunning_cycle_dispatcher_init_failed", error=str(exc))
        dunning_dispatcher = None

    dunning = DunningService(db, dispatcher=dunning_dispatcher)
    user_repo = UserRepository(db)

    try:
        overdue = await dunning.get_overdue_accounts(grace_period_days=7)

        if not overdue:
            return {
                "status": "ok",
                "overdue_accounts": 0,
                "escalated": 0,
                "emails_sent": 0,
            }

        escalated = 0
        emails_sent = 0

        for account in overdue:
            user_id = str(account["user_id"])
            retry_count = account.get("retry_count", 3)

            # Send final dunning notification (email + push via dispatcher when available)
            email_sent = await dunning.send_dunning_email(
                user_email=account["email"],
                user_name=account.get("name", ""),
                retry_count=max(retry_count, 3),
                amount=(
                    Decimal(str(account["amount_owed"]))
                    if account.get("amount_owed")
                    else None
                ),
                currency=account.get("currency", "USD"),
                user_id=user_id,
            )
            if email_sent:
                emails_sent += 1

            # Escalate (downgrade to free)
            action = await dunning.escalate_if_needed(user_id, 3, user_repo)
            if action:
                escalated += 1

        logger.info(
            "dunning_cycle_complete",
            overdue=len(overdue),
            escalated=escalated,
            emails_sent=emails_sent,
        )

        return {
            "status": "ok",
            "overdue_accounts": len(overdue),
            "escalated": escalated,
            "emails_sent": emails_sent,
        }

    except Exception as exc:
        logger.error("dunning_cycle_failed", error=str(exc))
        raise HTTPException(
            status_code=500, detail="Dunning cycle failed. See server logs."
        )
