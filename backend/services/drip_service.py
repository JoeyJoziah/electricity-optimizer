"""
Drip Email Service

3-email onboarding sequence for new RateShift signups:
  #1  Welcome      — fires immediately on signup
  #2  Day-2 value  — Template A (connected) or Template B (pending); snapshotted at batch time
  #3  Day-7 nudge  — Pro upgrade framing, no discount

State machine lives in user_drip_state table (migration 067 + 068).

All SQL uses parameterised text() statements; no string interpolation.
"""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings
from services.email_service import EmailService

logger = structlog.get_logger(__name__)

# Days after enrollment before each batch fires
DAY2_DELAY = timedelta(days=2)
DAY7_DELAY = timedelta(days=7)

# Sentry-alertable error rate threshold (raised externally via Sentry alert rules)
# exposed here so tests and callers can reference the constant
DISPATCH_ERROR_RATE_THRESHOLD = 0.02  # 2%

_UNSUBSCRIBE_BASE = "https://rateshift.app/api/v1/public/unsubscribe"


def _make_unsubscribe_url(user_id: str) -> str:
    """Return a one-click unsubscribe URL signed with the unsubscribe secret."""
    secret = get_settings().effective_unsubscribe_secret.encode()
    tok = hmac.new(secret, user_id.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{_UNSUBSCRIBE_BASE}?uid={user_id}&tok={tok}"


class DripService:
    """Orchestrates the 3-email onboarding drip sequence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.email = EmailService()

    # ------------------------------------------------------------------
    # Enrollment
    # ------------------------------------------------------------------

    async def enroll_user(
        self,
        user_id: str,
        email: str,
        name: str | None,
    ) -> bool:
        """
        Insert a new drip_state row and immediately send the welcome email.

        Idempotent: silently ignores conflicts (second call for same user_id is a no-op).
        Returns True if email was sent, False if already enrolled or send failed.
        """
        insert_result = await self.db.execute(
            text("""
                INSERT INTO user_drip_state (user_id, enrolled_at)
                VALUES (:user_id, NOW())
                ON CONFLICT (user_id) DO NOTHING
                RETURNING user_id
            """),
            {"user_id": user_id},
        )
        if not insert_result.fetchone():
            # Already enrolled; do not re-send welcome
            logger.debug("drip_already_enrolled", user_id=user_id)
            return False

        await self.db.commit()

        sent = await self._send_welcome(user_id=user_id, email=email, name=name)
        if sent:
            await self.db.execute(
                text("""
                    UPDATE user_drip_state
                    SET welcome_sent_at = NOW(), updated_at = NOW()
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id},
            )
            await self.db.commit()

        return sent

    # ------------------------------------------------------------------
    # Daily batch processors (called by /internal/drip/process)
    # ------------------------------------------------------------------

    async def process_day2_batch(self) -> dict[str, Any]:
        """
        Send Day-2 emails to all users where:
          - enrolled_at <= NOW() - 2 days
          - day2_sent_at IS NULL

        State is snapshot at query time (PRD spec): connection status evaluated
        when the cron picks the user, not when the email is actually sent.

        Returns summary counts for logging / Sentry.
        """
        cutoff = datetime.now(UTC) - DAY2_DELAY
        result = await self.db.execute(
            text("""
                SELECT
                    ds.user_id,
                    u.email,
                    u.name,
                    u.region,
                    EXISTS (
                        SELECT 1 FROM user_connections uc
                        WHERE uc.user_id = ds.user_id
                        LIMIT 1
                    ) AS has_connection,
                    EXISTS (
                        SELECT 1 FROM bill_uploads bu
                        WHERE bu.user_id = ds.user_id AND bu.parse_status = 'complete'
                        LIMIT 1
                    ) AS has_bill,
                    (
                        SELECT ROUND(COALESCE(SUM(amount), 0) * 12, 0)
                        FROM user_savings us
                        WHERE us.user_id = ds.user_id
                          AND us.savings_type = 'bill_estimate'
                          AND us.created_at >= NOW() - INTERVAL '30 days'
                    ) AS potential_savings_annual
                FROM user_drip_state ds
                JOIN users u ON u.id = ds.user_id
                WHERE ds.enrolled_at <= :cutoff
                  AND ds.day2_sent_at IS NULL
                  AND ds.unsubscribed_at IS NULL
            """),
            {"cutoff": cutoff},
        )
        rows = result.mappings().all()

        sent_a = sent_b = errors = 0
        for row in rows:
            user_id = str(row["user_id"])
            is_connected = row["has_connection"] or row["has_bill"]
            template_key = "connected" if is_connected else "pending"

            try:
                unsub_url = _make_unsubscribe_url(user_id)
                if is_connected:
                    annual_savings = row["potential_savings_annual"]
                    ok = await self._send_day2_connected(
                        user_id=user_id,
                        email=row["email"],
                        name=row["name"],
                        region=row["region"],
                        potential_savings_annual=float(annual_savings) if annual_savings else None,
                        unsubscribe_url=unsub_url,
                    )
                    if ok:
                        sent_a += 1
                else:
                    ok = await self._send_day2_pending(
                        user_id=user_id,
                        email=row["email"],
                        name=row["name"],
                        unsubscribe_url=unsub_url,
                    )
                    if ok:
                        sent_b += 1

                if ok:
                    await self.db.execute(
                        text("""
                            UPDATE user_drip_state
                            SET day2_sent_at = NOW(),
                                day2_template = :tpl,
                                updated_at = NOW()
                            WHERE user_id = :user_id
                        """),
                        {"user_id": user_id, "tpl": template_key},
                    )
                    await self.db.commit()

            except Exception:
                errors += 1
                logger.exception("drip_day2_error", user_id=user_id)
                await self.db.rollback()

        total = len(rows)
        logger.info(
            "drip_day2_batch_complete",
            total=total,
            sent_a=sent_a,
            sent_b=sent_b,
            errors=errors,
        )
        return {"total": total, "sent_a": sent_a, "sent_b": sent_b, "errors": errors}

    async def process_day7_batch(self) -> dict[str, Any]:
        """
        Send Day-7 upgrade nudge to all users where:
          - enrolled_at <= NOW() - 7 days
          - day7_sent_at IS NULL

        Returns summary counts.
        """
        cutoff = datetime.now(UTC) - DAY7_DELAY
        result = await self.db.execute(
            text("""
                SELECT ds.user_id, u.email, u.name
                FROM user_drip_state ds
                JOIN users u ON u.id = ds.user_id
                WHERE ds.enrolled_at <= :cutoff
                  AND ds.day7_sent_at IS NULL
                  AND ds.unsubscribed_at IS NULL
            """),
            {"cutoff": cutoff},
        )
        rows = result.mappings().all()

        sent = errors = 0
        for row in rows:
            user_id = str(row["user_id"])
            try:
                ok = await self._send_day7_upgrade(
                    user_id=user_id,
                    email=row["email"],
                    name=row["name"],
                    unsubscribe_url=_make_unsubscribe_url(user_id),
                )
                if ok:
                    sent += 1
                    await self.db.execute(
                        text("""
                            UPDATE user_drip_state
                            SET day7_sent_at = NOW(), updated_at = NOW()
                            WHERE user_id = :user_id
                        """),
                        {"user_id": user_id},
                    )
                    await self.db.commit()
            except Exception:
                errors += 1
                logger.exception("drip_day7_error", user_id=user_id)
                await self.db.rollback()

        logger.info("drip_day7_batch_complete", total=len(rows), sent=sent, errors=errors)
        return {"total": len(rows), "sent": sent, "errors": errors}

    # ------------------------------------------------------------------
    # Private send helpers
    # ------------------------------------------------------------------

    async def _send_welcome(self, user_id: str, email: str, name: str | None) -> bool:
        html = self.email.render_template(
            "welcome_signup.html",
            name=name or "",
            unsubscribe_url=_make_unsubscribe_url(user_id),
        )
        ok = await self.email.send(
            to=email,
            subject="Welcome to RateShift",
            html_body=html,
        )
        logger.info("drip_welcome_sent" if ok else "drip_welcome_skipped", user_id=user_id)
        return ok

    async def _send_day2_connected(
        self,
        user_id: str,
        email: str,
        name: str | None,
        region: str | None,
        potential_savings_annual: float | None = None,
        unsubscribe_url: str | None = None,
    ) -> bool:
        html = self.email.render_template(
            "drip_day2_connected.html",
            name=name or "",
            region=region or "your region",
            potential_savings_annual=potential_savings_annual,
            unsubscribe_url=unsubscribe_url or _make_unsubscribe_url(user_id),
        )
        ok = await self.email.send(
            to=email,
            subject="Your savings estimate is ready — RateShift",
            html_body=html,
        )
        logger.info(
            "drip_day2_connected_sent" if ok else "drip_day2_connected_skipped",
            user_id=user_id,
        )
        return ok

    async def _send_day2_pending(
        self,
        user_id: str,
        email: str,
        name: str | None,
        unsubscribe_url: str | None = None,
    ) -> bool:
        html = self.email.render_template(
            "drip_day2_pending.html",
            name=name or "",
            zip_code=None,
            sample_annual_savings=180,
            unsubscribe_url=unsubscribe_url or _make_unsubscribe_url(user_id),
        )
        ok = await self.email.send(
            to=email,
            subject="See what people near you are saving — RateShift",
            html_body=html,
        )
        logger.info(
            "drip_day2_pending_sent" if ok else "drip_day2_pending_skipped",
            user_id=user_id,
        )
        return ok

    async def _send_day7_upgrade(
        self,
        user_id: str,
        email: str,
        name: str | None,
        unsubscribe_url: str | None = None,
    ) -> bool:
        html = self.email.render_template(
            "drip_day7_upgrade.html",
            name=name or "",
            unsubscribe_url=unsubscribe_url or _make_unsubscribe_url(user_id),
        )
        ok = await self.email.send(
            to=email,
            subject="A week in — what Pro adds for you — RateShift",
            html_body=html,
        )
        logger.info(
            "drip_day7_sent" if ok else "drip_day7_skipped",
            user_id=user_id,
        )
        return ok
