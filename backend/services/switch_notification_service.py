"""
Switch Notification Service

Sends email + OneSignal push notifications for Auto Rate Switcher events.

Three notification types:
    switch_confirmation   — Business tier: a switch was executed automatically.
    switch_recommendation — Pro tier: a better plan was found; user approval needed.
    contract_expiring     — All tiers: current contract expires within 45 days.

Email uses the Jinja2 HTML templates in backend/templates/emails/.
Push uses the existing PushNotificationService (OneSignal REST API).

Both channels are attempted concurrently via asyncio.gather with
return_exceptions=True so that a OneSignal failure never blocks the email
and vice versa.

Usage:
    svc = SwitchNotificationService()
    await svc.send_switch_confirmation(
        user_id="...",
        user_name="Alice",
        user_email="alice@example.com",
        old_plan={"plan_name": "Standard Rate", "provider": "Con Edison", ...},
        new_plan={"plan_name": "Green 12", "provider": "NRG Energy", ...},
        savings={"monthly": Decimal("18.50"), "annual": Decimal("222.00")},
    )
"""

import asyncio
from decimal import Decimal
from typing import Any

import structlog

from services.email_service import EmailService
from services.push_notification_service import PushNotificationService

logger = structlog.get_logger(__name__)


class SwitchNotificationService:
    """Dispatch switch-lifecycle notifications via email and push.

    Args:
        email_service: EmailService instance (Resend primary, SMTP fallback).
            Defaults to a fresh EmailService() when omitted.
        push_service: PushNotificationService instance (OneSignal).
            Defaults to a fresh PushNotificationService() when omitted.

    All public methods return a dict:
        {"email": bool, "push": bool}
    where each value indicates whether that channel succeeded.
    """

    def __init__(
        self,
        email_service: EmailService | None = None,
        push_service: PushNotificationService | None = None,
    ) -> None:
        self._email = email_service or EmailService()
        self._push = push_service or PushNotificationService()

    # =========================================================================
    # Public API
    # =========================================================================

    async def send_switch_confirmation(
        self,
        user_id: str,
        user_name: str | None,
        user_email: str | None,
        old_plan: dict[str, Any],
        new_plan: dict[str, Any],
        savings: dict[str, Any],
        rescission_days: int | None = None,
        rollback_url: str | None = None,
    ) -> dict[str, bool]:
        """Notify the user that a plan switch was executed automatically.

        Sent on Business tier when the decision engine action is ``"switch"``.

        Args:
            user_id:        UUID string of the user (for push targeting).
            user_name:      Display name shown in the email greeting.
            user_email:     Recipient address for the email channel.
            old_plan:       Dict describing the previous plan. Expected keys:
                              plan_name, provider, rate_kwh (optional),
                              fixed_charge (optional).
            new_plan:       Dict describing the new plan. Same keys as old_plan.
            savings:        Dict with keys ``monthly`` (Decimal or float) and
                              optionally ``annual`` (Decimal or float).
            rescission_days: Days the user has to cancel without penalty.
                              Omit or pass None to hide the rescission section.
            rollback_url:   URL the user can visit to cancel the switch.
                              Omit or pass None to hide the cancel button.

        Returns:
            {"email": bool, "push": bool}
        """
        savings_monthly = _to_float(savings.get("monthly", 0))
        savings_annual = _to_float_or_none(savings.get("annual"))

        # Build email
        subject = "Your electricity plan has been switched"
        html_body: str | None = None
        if user_email:
            try:
                html_body = self._email.render_template(
                    "switch_confirmation.html",
                    user_name=user_name,
                    old_plan_name=old_plan.get("plan_name", ""),
                    old_provider=old_plan.get("provider", ""),
                    old_rate_kwh=_to_float_or_none(old_plan.get("rate_kwh")),
                    old_fixed_charge=_to_float_or_none(old_plan.get("fixed_charge")),
                    new_plan_name=new_plan.get("plan_name", ""),
                    new_provider=new_plan.get("provider", ""),
                    new_rate_kwh=_to_float_or_none(new_plan.get("rate_kwh")),
                    new_fixed_charge=_to_float_or_none(new_plan.get("fixed_charge")),
                    savings_monthly=savings_monthly,
                    savings_annual=savings_annual,
                    rescission_days=rescission_days,
                    rollback_url=rollback_url,
                )
            except Exception as exc:
                logger.error(
                    "switch_notification.render_failed",
                    template="switch_confirmation.html",
                    user_id=user_id,
                    error=str(exc),
                )

        # Push message
        push_message = (
            f"You've been switched to {new_plan.get('plan_name', 'a new plan')} "
            f"from {new_plan.get('provider', 'your new provider')}. "
            f"Projected savings: ${savings_monthly:.2f}/month."
        )

        email_ok, push_ok = await self._dispatch(
            user_id=user_id,
            user_email=user_email,
            subject=subject,
            html_body=html_body,
            push_title="Plan Switched Successfully",
            push_message=push_message,
            push_data={
                "type": "switch_confirmation",
                "new_plan": new_plan.get("plan_name", ""),
                "savings_monthly": str(savings_monthly),
            },
        )

        logger.info(
            "switch_notification.confirmation_sent",
            user_id=user_id,
            email_ok=email_ok,
            push_ok=push_ok,
            new_plan=new_plan.get("plan_name"),
        )

        return {"email": email_ok, "push": push_ok}

    async def send_switch_recommendation(
        self,
        user_id: str,
        user_name: str | None,
        user_email: str | None,
        current_plan: dict[str, Any],
        proposed_plan: dict[str, Any],
        savings: dict[str, Any],
        confidence: float | Decimal | None = None,
        audit_log_id: str | None = None,
    ) -> dict[str, bool]:
        """Notify the user that a better plan was found and awaits approval.

        Sent on Pro tier when the decision engine action is ``"recommend"``.

        Args:
            user_id:       UUID string of the user (for push targeting).
            user_name:     Display name shown in the email greeting.
            user_email:    Recipient address for the email channel.
            current_plan:  Dict describing the user's current plan. Expected keys:
                             plan_name, provider, rate_kwh (optional),
                             fixed_charge (optional).
            proposed_plan: Dict describing the recommended plan. Same keys.
            savings:       Dict with keys ``monthly`` and optionally ``annual``.
            confidence:    Model confidence score (0–1). Displayed as a progress
                             bar in the email. Omit to hide the confidence section.
            audit_log_id:  UUID of the ``switch_audit_log`` row. When provided
                             the approve URL deep-links to that recommendation.

        Returns:
            {"email": bool, "push": bool}
        """
        savings_monthly = _to_float(savings.get("monthly", 0))
        savings_annual = _to_float_or_none(savings.get("annual"))

        approve_url = (
            f"https://rateshift.app/dashboard?approve={audit_log_id}"
            if audit_log_id
            else "https://rateshift.app/dashboard"
        )

        subject = "We found a better electricity plan for you"
        html_body: str | None = None
        if user_email:
            try:
                html_body = self._email.render_template(
                    "switch_recommendation.html",
                    user_name=user_name,
                    current_plan_name=current_plan.get("plan_name", ""),
                    current_provider=current_plan.get("provider", ""),
                    current_rate_kwh=_to_float_or_none(current_plan.get("rate_kwh")),
                    current_fixed_charge=_to_float_or_none(current_plan.get("fixed_charge")),
                    recommended_plan_name=proposed_plan.get("plan_name", ""),
                    recommended_provider=proposed_plan.get("provider", ""),
                    recommended_rate_kwh=_to_float_or_none(proposed_plan.get("rate_kwh")),
                    recommended_fixed_charge=_to_float_or_none(proposed_plan.get("fixed_charge")),
                    savings_monthly=savings_monthly,
                    savings_annual=savings_annual,
                    confidence=_to_float_or_none(confidence),
                    approve_url=approve_url,
                )
            except Exception as exc:
                logger.error(
                    "switch_notification.render_failed",
                    template="switch_recommendation.html",
                    user_id=user_id,
                    error=str(exc),
                )

        push_message = (
            f"A new plan from {proposed_plan.get('provider', 'a new provider')} "
            f"could save you ${savings_monthly:.2f}/month. "
            "Tap to review and approve."
        )

        email_ok, push_ok = await self._dispatch(
            user_id=user_id,
            user_email=user_email,
            subject=subject,
            html_body=html_body,
            push_title="Better Plan Found",
            push_message=push_message,
            push_data={
                "type": "switch_recommendation",
                "proposed_plan": proposed_plan.get("plan_name", ""),
                "savings_monthly": str(savings_monthly),
                "audit_log_id": audit_log_id or "",
            },
        )

        logger.info(
            "switch_notification.recommendation_sent",
            user_id=user_id,
            email_ok=email_ok,
            push_ok=push_ok,
            proposed_plan=proposed_plan.get("plan_name"),
        )

        return {"email": email_ok, "push": push_ok}

    async def send_contract_expiring(
        self,
        user_id: str,
        user_name: str | None,
        user_email: str | None,
        plan_name: str,
        days_remaining: int,
        provider: str | None = None,
        rate_kwh: float | Decimal | None = None,
        expiry_date: str | None = None,
        is_free_switch_window: bool = False,
    ) -> dict[str, bool]:
        """Notify the user that their current contract expires within 45 days.

        Args:
            user_id:              UUID string of the user (for push targeting).
            user_name:            Display name shown in the email greeting.
            user_email:           Recipient address for the email channel.
            plan_name:            Name of the current plan.
            days_remaining:       Days until the contract expires.
            provider:             Name of the current electricity provider.
            rate_kwh:             Current supply rate in $/kWh (optional display).
            expiry_date:          Human-readable expiry date string (e.g. "May 15, 2026").
            is_free_switch_window: True when days_remaining <= 45 — enables the
                                   "no ETF" banner in the email.

        Returns:
            {"email": bool, "push": bool}
        """
        subject = f"Your electricity contract expires in {days_remaining} days"
        html_body: str | None = None
        if user_email:
            try:
                html_body = self._email.render_template(
                    "contract_expiring.html",
                    user_name=user_name,
                    plan_name=plan_name,
                    days_remaining=days_remaining,
                    provider=provider,
                    rate_kwh=_to_float_or_none(rate_kwh),
                    expiry_date=expiry_date,
                    is_free_switch_window=is_free_switch_window,
                )
            except Exception as exc:
                logger.error(
                    "switch_notification.render_failed",
                    template="contract_expiring.html",
                    user_id=user_id,
                    error=str(exc),
                )

        push_message = (
            f"Your {plan_name} contract expires in {days_remaining} days. "
            "Tap to compare plans and avoid a default rate rollover."
        )
        if is_free_switch_window:
            push_message = (
                f"Your {plan_name} contract expires in {days_remaining} days "
                "— switch now with no cancellation fee."
            )

        email_ok, push_ok = await self._dispatch(
            user_id=user_id,
            user_email=user_email,
            subject=subject,
            html_body=html_body,
            push_title=f"Contract Expiring in {days_remaining} Days",
            push_message=push_message,
            push_data={
                "type": "contract_expiring",
                "plan_name": plan_name,
                "days_remaining": str(days_remaining),
                "is_free_switch_window": str(is_free_switch_window),
            },
        )

        logger.info(
            "switch_notification.contract_expiry_sent",
            user_id=user_id,
            email_ok=email_ok,
            push_ok=push_ok,
            days_remaining=days_remaining,
        )

        return {"email": email_ok, "push": push_ok}

    # =========================================================================
    # Internal helpers
    # =========================================================================

    async def _dispatch(
        self,
        user_id: str,
        user_email: str | None,
        subject: str,
        html_body: str | None,
        push_title: str,
        push_message: str,
        push_data: dict[str, Any] | None = None,
    ) -> tuple[bool, bool]:
        """Send email and push concurrently.

        Returns:
            (email_ok, push_ok) — True indicates the channel succeeded.
        """

        async def _send_email_channel() -> bool:
            if not user_email:
                logger.debug(
                    "switch_notification.email_skipped_no_address",
                    user_id=user_id,
                )
                return False
            if not html_body:
                logger.debug(
                    "switch_notification.email_skipped_no_body",
                    user_id=user_id,
                )
                return False
            try:
                return await self._email.send(
                    to=user_email,
                    subject=subject,
                    html_body=html_body,
                )
            except Exception as exc:
                logger.error(
                    "switch_notification.email_failed",
                    user_id=user_id,
                    error=str(exc),
                )
                return False

        async def _send_push_channel() -> bool:
            try:
                return await self._push.send_push(
                    user_id=user_id,
                    title=push_title,
                    message=push_message,
                    data=push_data or {},
                )
            except Exception as exc:
                logger.error(
                    "switch_notification.push_failed",
                    user_id=user_id,
                    error=str(exc),
                )
                return False

        results = await asyncio.gather(
            _send_email_channel(),
            _send_push_channel(),
            return_exceptions=True,
        )

        email_ok = results[0] if isinstance(results[0], bool) else False
        push_ok = results[1] if isinstance(results[1], bool) else False

        if isinstance(results[0], BaseException):
            logger.error(
                "switch_notification.email_unhandled_exception",
                user_id=user_id,
                error=str(results[0]),
            )
        if isinstance(results[1], BaseException):
            logger.error(
                "switch_notification.push_unhandled_exception",
                user_id=user_id,
                error=str(results[1]),
            )

        return email_ok, push_ok


# =========================================================================
# Utility helpers (module-level, not part of the public API)
# =========================================================================


def _to_float(value: Any) -> float:
    """Convert a Decimal, int, float, or str to float. Returns 0.0 on failure."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_float_or_none(value: Any) -> float | None:
    """Convert to float or return None when the value is absent/invalid."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
