"""
Dunning Service

Handles failed payment recovery via empathetic email flows.
Records retry history, enforces cooldown windows (24 h between emails),
and escalates to free tier after 3 consecutive failures.

Migration: 024_payment_retry_history.sql
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.email_service import EmailService

logger = structlog.get_logger(__name__)

BILLING_URL = "https://electricity-optimizer.app/settings?tab=billing"
DUNNING_COOLDOWN_HOURS = 24


class DunningService:
    """
    Service for managing payment failure recovery (dunning).

    Usage:
        service = DunningService(db)
        await service.handle_payment_failure(user_id, invoice_id, customer_id, amount, currency, user_repo)
    """

    def __init__(
        self,
        db: AsyncSession,
        email_service: Optional[EmailService] = None,
    ):
        self._db = db
        self._email_service = email_service or EmailService()

    async def record_payment_failure(
        self,
        user_id: str,
        stripe_invoice_id: str,
        stripe_customer_id: str,
        amount_owed: Optional[float] = None,
        currency: str = "USD",
    ) -> Dict[str, Any]:
        """Insert a payment_retry_history row and return it."""
        retry_count = await self.get_retry_count(stripe_invoice_id)
        new_count = retry_count + 1
        retry_type = "soft" if new_count < 3 else "final"

        result = await self._db.execute(
            text("""
                INSERT INTO payment_retry_history
                    (id, user_id, stripe_invoice_id, stripe_customer_id,
                     retry_count, retry_type, amount_owed, currency)
                VALUES
                    (:id, :user_id, :stripe_invoice_id, :stripe_customer_id,
                     :retry_count, :retry_type, :amount_owed, :currency)
                RETURNING id, user_id, stripe_invoice_id, stripe_customer_id,
                          retry_count, retry_type, amount_owed, currency,
                          email_sent, email_sent_at, escalation_action,
                          created_at, updated_at
            """),
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "stripe_invoice_id": stripe_invoice_id,
                "stripe_customer_id": stripe_customer_id,
                "retry_count": new_count,
                "retry_type": retry_type,
                "amount_owed": amount_owed,
                "currency": currency,
            },
        )
        await self._db.commit()
        row = result.mappings().first()
        logger.info(
            "payment_failure_recorded",
            user_id=user_id,
            invoice_id=stripe_invoice_id,
            retry_count=new_count,
            retry_type=retry_type,
        )
        return dict(row) if row else {}

    async def get_retry_count(self, stripe_invoice_id: str) -> int:
        """Return how many retry rows exist for a given invoice."""
        result = await self._db.execute(
            text("""
                SELECT COUNT(*) FROM payment_retry_history
                WHERE stripe_invoice_id = :invoice_id
            """),
            {"invoice_id": stripe_invoice_id},
        )
        return result.scalar() or 0

    async def should_send_dunning(
        self,
        user_id: str,
        stripe_invoice_id: str,
    ) -> bool:
        """
        Return True if no dunning email was sent for this invoice
        within the cooldown window (24 hours).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=DUNNING_COOLDOWN_HOURS)
        result = await self._db.execute(
            text("""
                SELECT email_sent_at
                FROM payment_retry_history
                WHERE user_id = :user_id
                  AND stripe_invoice_id = :invoice_id
                  AND email_sent = TRUE
                  AND email_sent_at >= :cutoff
                ORDER BY email_sent_at DESC
                LIMIT 1
            """),
            {
                "user_id": user_id,
                "invoice_id": stripe_invoice_id,
                "cutoff": cutoff,
            },
        )
        return result.first() is None

    async def send_dunning_email(
        self,
        user_email: str,
        user_name: str,
        retry_count: int,
        amount: Optional[float] = None,
        currency: str = "USD",
    ) -> bool:
        """
        Send a dunning email — soft (<3 retries) or final (>=3).

        Returns True on success.
        """
        template = "dunning_final.html" if retry_count >= 3 else "dunning_soft.html"
        subject = (
            "Action Required: Update your payment method"
            if retry_count < 3
            else "Final Notice: Your subscription will be downgraded"
        )

        try:
            html = self._email_service.render_template(
                template,
                user_name=user_name,
                amount=f"{amount:.2f}" if amount else "N/A",
                currency=currency,
                billing_url=BILLING_URL,
                retry_count=retry_count,
            )
            success = await self._email_service.send(
                to=user_email,
                subject=subject,
                html_body=html,
            )
            if success:
                logger.info(
                    "dunning_email_sent",
                    email=user_email,
                    template=template,
                    retry_count=retry_count,
                )
            return success
        except Exception as e:
            logger.error("dunning_email_failed", email=user_email, error=str(e))
            return False

    async def escalate_if_needed(
        self,
        user_id: str,
        retry_count: int,
        user_repo: Any,
    ) -> Optional[str]:
        """
        Downgrade user to free tier after 3+ failures.

        Returns the escalation action taken, or None.
        """
        if retry_count < 3:
            return None

        user = await user_repo.get_by_id(user_id)
        if not user:
            logger.warning("escalate_user_not_found", user_id=user_id)
            return None

        if user.subscription_tier == "free":
            return None

        user.subscription_tier = "free"
        await user_repo.update(user_id, user)
        logger.warning(
            "user_downgraded_to_free",
            user_id=user_id,
            reason="payment_failed_3x",
        )
        return "downgraded_to_free"

    async def handle_payment_failure(
        self,
        user_id: str,
        stripe_invoice_id: str,
        stripe_customer_id: str,
        amount_owed: Optional[float],
        currency: str,
        user_email: str,
        user_name: str,
        user_repo: Any,
    ) -> Dict[str, Any]:
        """
        Orchestrator: record failure → check cooldown → send email → escalate.

        Called from apply_webhook_action() on invoice.payment_failed events.
        """
        # 1. Record the failure
        record = await self.record_payment_failure(
            user_id=user_id,
            stripe_invoice_id=stripe_invoice_id,
            stripe_customer_id=stripe_customer_id,
            amount_owed=amount_owed,
            currency=currency,
        )
        retry_count = record.get("retry_count", 1)

        result = {
            "recorded": True,
            "retry_count": retry_count,
            "email_sent": False,
            "escalation_action": None,
        }

        # 2. Cooldown check
        should_send = await self.should_send_dunning(user_id, stripe_invoice_id)
        if not should_send:
            logger.info(
                "dunning_cooldown_active",
                user_id=user_id,
                invoice_id=stripe_invoice_id,
            )
            return result

        # 3. Send dunning email
        email_sent = await self.send_dunning_email(
            user_email=user_email,
            user_name=user_name,
            retry_count=retry_count,
            amount=amount_owed,
            currency=currency,
        )
        result["email_sent"] = email_sent

        # 4. Mark email sent in the record
        if email_sent and record.get("id"):
            await self._db.execute(
                text("""
                    UPDATE payment_retry_history
                    SET email_sent = TRUE, email_sent_at = NOW(), updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": str(record["id"])},
            )
            await self._db.commit()

        # 5. Escalate if needed
        escalation = await self.escalate_if_needed(user_id, retry_count, user_repo)
        result["escalation_action"] = escalation

        if escalation and record.get("id"):
            await self._db.execute(
                text("""
                    UPDATE payment_retry_history
                    SET escalation_action = :action, updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": str(record["id"]), "action": escalation},
            )
            await self._db.commit()

        return result

    async def get_overdue_accounts(
        self,
        grace_period_days: int = 7,
    ) -> list:
        """
        Return users whose most recent payment failure is older than
        grace_period_days and who are still on a paid tier.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=grace_period_days)
        result = await self._db.execute(
            text("""
                SELECT DISTINCT ON (prh.user_id)
                    prh.user_id,
                    prh.stripe_invoice_id,
                    prh.stripe_customer_id,
                    prh.retry_count,
                    prh.amount_owed,
                    prh.currency,
                    u.email,
                    u.name,
                    u.subscription_tier
                FROM payment_retry_history prh
                JOIN public.users u ON u.id = prh.user_id
                WHERE prh.created_at <= :cutoff
                  AND u.subscription_tier != 'free'
                  AND u.is_active = TRUE
                ORDER BY prh.user_id, prh.created_at DESC
            """),
            {"cutoff": cutoff},
        )
        rows = result.mappings().all()
        return [dict(row) for row in rows]
