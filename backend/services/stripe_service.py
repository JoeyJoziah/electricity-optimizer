"""
Stripe Monetization Service

Handles subscription lifecycle, checkout sessions, webhooks, and customer portal.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import stripe
import structlog

from config.settings import settings
from lib.tracing import traced

logger = structlog.get_logger(__name__)


class StripeService:
    """
    Service for managing Stripe subscriptions and payments.

    Tiers:
    - Free: $0 (basic price view, 1 alert, manual scheduling)
    - Pro: $4.99/mo (unlimited alerts, ML forecasts, optimization, weather)
    - Business: $14.99/mo (API access, multi-property, priority support)
    """

    def __init__(self, db=None):
        """Initialize Stripe service with API key from settings."""
        self._db = db
        if not settings.stripe_secret_key:
            logger.warning("stripe_not_configured", message="STRIPE_SECRET_KEY not set")
            self._configured = False
        else:
            stripe.api_key = settings.stripe_secret_key
            self._configured = True
            logger.info("stripe_service_initialized")

    @property
    def is_configured(self) -> bool:
        """Check if Stripe is properly configured."""
        return self._configured

    def _ensure_configured(self):
        """Raise error if Stripe is not configured."""
        if not self._configured:
            raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY.")

    def _get_price_id_for_tier(self, tier: str) -> str | None:
        """
        Get Stripe Price ID for a subscription tier.

        Args:
            tier: Subscription tier name (pro, business)

        Returns:
            Stripe Price ID or None if not configured
        """
        if tier == "pro":
            return settings.stripe_price_pro
        elif tier == "business":
            return settings.stripe_price_business
        return None

    async def create_checkout_session(
        self,
        user_id: str,
        email: str,
        tier: str | None = None,
        success_url: str = "",
        cancel_url: str = "",
        customer_id: str | None = None,
        plan: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a Stripe Checkout session for subscription.

        Args:
            user_id: User ID from our database
            email: User email
            tier: Subscription tier (pro, business)
            success_url: URL to redirect after successful checkout
            cancel_url: URL to redirect if checkout is cancelled
            customer_id: Existing Stripe customer ID (if any)
            plan: Alias for tier (used by newer callers)

        Returns:
            Dict with checkout session info (id, url)

        Raises:
            ValueError: If Stripe not configured or invalid tier
            stripe.StripeError: On Stripe API errors
        """
        # Support 'plan' as an alias for 'tier'
        if plan is not None and tier is None:
            tier = plan
        async with traced("stripe.create_checkout", attributes={"stripe.plan": tier or ""}):
            self._ensure_configured()

            if tier not in ["pro", "business"]:
                raise ValueError(f"Invalid tier: {tier}. Must be 'pro' or 'business'.")

            price_id = self._get_price_id_for_tier(tier)
            if not price_id:
                raise ValueError(
                    f"Price ID for tier '{tier}' not configured. "
                    f"Set STRIPE_PRICE_{tier.upper()} environment variable."
                )

            try:
                # Prepare customer data
                customer_params = {}
                if customer_id:
                    customer_params["customer"] = customer_id
                else:
                    customer_params["customer_email"] = email

                # Create checkout session (run in thread to avoid blocking event loop)
                session = await asyncio.to_thread(
                    stripe.checkout.Session.create,
                    **customer_params,
                    mode="subscription",
                    line_items=[
                        {
                            "price": price_id,
                            "quantity": 1,
                        }
                    ],
                    success_url=success_url,
                    cancel_url=cancel_url,
                    metadata={
                        "user_id": user_id,
                        "tier": tier,
                    },
                    subscription_data={
                        "metadata": {
                            "user_id": user_id,
                            "tier": tier,
                        }
                    },
                    allow_promotion_codes=True,
                    billing_address_collection="auto",
                )

                logger.info(
                    "checkout_session_created",
                    user_id=user_id,
                    tier=tier,
                    session_id=session.id,
                )

                return {
                    "id": session.id,
                    "url": session.url,
                    "customer_id": session.customer,
                }

            except stripe.StripeError as e:
                logger.error(
                    "checkout_session_failed",
                    user_id=user_id,
                    tier=tier,
                    error=str(e),
                )
                raise

    async def create_customer_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> dict[str, str]:
        """
        Create a Stripe Customer Portal session for subscription management.

        Args:
            customer_id: Stripe customer ID
            return_url: URL to return to after portal session

        Returns:
            Dict with portal session URL

        Raises:
            ValueError: If Stripe not configured
            stripe.StripeError: On Stripe API errors
        """
        self._ensure_configured()

        try:
            session = await asyncio.to_thread(
                stripe.billing_portal.Session.create,
                customer=customer_id,
                return_url=return_url,
            )

            logger.info(
                "portal_session_created",
                customer_id=customer_id,
                session_id=session.id,
            )

            return {"url": session.url}

        except stripe.StripeError as e:
            logger.error(
                "portal_session_failed",
                customer_id=customer_id,
                error=str(e),
            )
            raise

    async def get_subscription_status(
        self,
        customer_id: str,
    ) -> dict[str, Any] | None:
        """
        Get current subscription status for a customer.

        Args:
            customer_id: Stripe customer ID

        Returns:
            Dict with subscription info or None if no active subscription
            {
                "tier": "pro" | "business",
                "status": "active" | "trialing" | "past_due" | "canceled" | "incomplete",
                "current_period_end": datetime,
                "cancel_at_period_end": bool,
            }

        Raises:
            ValueError: If Stripe not configured
            stripe.StripeError: On Stripe API errors
        """
        self._ensure_configured()

        try:
            subscriptions = await asyncio.to_thread(
                stripe.Subscription.list,
                customer=customer_id,
                status="all",
                limit=1,
            )

            if not subscriptions.data:
                return None

            subscription = subscriptions.data[0]

            # Extract tier from metadata
            tier = subscription.metadata.get("tier", "unknown")

            return {
                "tier": tier,
                "status": subscription.status,
                "current_period_end": datetime.fromtimestamp(
                    subscription.current_period_end, tz=UTC
                ),
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "subscription_id": subscription.id,
            }

        except stripe.StripeError as e:
            logger.error(
                "subscription_status_failed",
                customer_id=customer_id,
                error=str(e),
            )
            raise

    async def cancel_subscription(
        self,
        subscription_id: str,
        cancel_immediately: bool = False,
    ) -> dict[str, Any]:
        """
        Cancel a subscription.

        Args:
            subscription_id: Stripe subscription ID
            cancel_immediately: If True, cancel now. If False, cancel at period end.

        Returns:
            Dict with updated subscription info

        Raises:
            ValueError: If Stripe not configured
            stripe.StripeError: On Stripe API errors
        """
        self._ensure_configured()

        try:
            if cancel_immediately:
                subscription = await asyncio.to_thread(stripe.Subscription.cancel, subscription_id)
                logger.info(
                    "subscription_canceled_immediately",
                    subscription_id=subscription_id,
                )
            else:
                subscription = await asyncio.to_thread(
                    stripe.Subscription.modify,
                    subscription_id,
                    cancel_at_period_end=True,
                )
                logger.info(
                    "subscription_scheduled_cancel",
                    subscription_id=subscription_id,
                    cancel_at=subscription.current_period_end,
                )

            return {
                "status": subscription.status,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "canceled_at": subscription.canceled_at,
            }

        except stripe.StripeError as e:
            logger.error(
                "subscription_cancel_failed",
                subscription_id=subscription_id,
                error=str(e),
            )
            raise

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> stripe.Event:
        """
        Verify Stripe webhook signature and construct event.

        Args:
            payload: Raw request body bytes
            signature: Stripe-Signature header value

        Returns:
            Verified Stripe Event object

        Raises:
            ValueError: If webhook secret not configured or signature invalid
        """
        if not settings.stripe_webhook_secret:
            raise ValueError("STRIPE_WEBHOOK_SECRET not configured")

        try:
            event = stripe.Webhook.construct_event(
                payload, signature, settings.stripe_webhook_secret
            )
            return event
        except stripe.SignatureVerificationError as e:
            logger.error("webhook_signature_verification_failed", error=str(e))
            raise ValueError("Invalid webhook signature") from e

    async def handle_webhook_event(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle a Stripe webhook event.

        Args:
            event: Verified Stripe Event object

        Returns:
            Dict with processing result and any actions needed
            {
                "handled": bool,
                "action": str,
                "user_id": str,
                "tier": str,
                "customer_id": str,
            }
        """
        async with traced(
            "stripe.webhook", attributes={"stripe.event_type": event.get("type", "unknown")}
        ):
            event_type = event["type"]
            data = event["data"]["object"]

            logger.info("webhook_event_received", event_type=event_type, event_id=event["id"])

            result = {
                "handled": False,
                "action": None,
                "user_id": None,
                "tier": None,
                "customer_id": None,
            }

            # Checkout session completed
            if event_type == "checkout.session.completed":
                session = data
                user_id = session.get("metadata", {}).get("user_id")
                tier = session.get("metadata", {}).get("tier")
                customer_id = session.get("customer")

                result.update(
                    {
                        "handled": True,
                        "action": "activate_subscription",
                        "user_id": user_id,
                        "tier": tier,
                        "customer_id": customer_id,
                    }
                )

                logger.info(
                    "checkout_completed",
                    user_id=user_id,
                    tier=tier,
                    customer_id=customer_id,
                )

            # Subscription updated
            elif event_type == "customer.subscription.updated":
                subscription = data
                user_id = subscription.get("metadata", {}).get("user_id")
                tier = subscription.get("metadata", {}).get("tier")
                customer_id = subscription.get("customer")
                status = subscription.get("status")

                # Only force "free" for terminal failure states; preserve tier
                # for trialing, past_due, incomplete so users retain access
                # during grace periods (Stripe retries before hard-canceling).
                _downgrade_statuses = {"canceled", "unpaid"}
                effective_tier = "free" if status in _downgrade_statuses else (tier or "free")
                result.update(
                    {
                        "handled": True,
                        "action": "update_subscription",
                        "user_id": user_id,
                        "tier": effective_tier,
                        "customer_id": customer_id,
                        "status": status,
                    }
                )

                logger.info(
                    "subscription_updated",
                    user_id=user_id,
                    tier=tier,
                    status=status,
                    customer_id=customer_id,
                )

            # Subscription deleted/canceled
            elif event_type == "customer.subscription.deleted":
                subscription = data
                user_id = subscription.get("metadata", {}).get("user_id")
                customer_id = subscription.get("customer")

                result.update(
                    {
                        "handled": True,
                        "action": "deactivate_subscription",
                        "user_id": user_id,
                        "tier": "free",
                        "customer_id": customer_id,
                    }
                )

                logger.info(
                    "subscription_deleted",
                    user_id=user_id,
                    customer_id=customer_id,
                )

            # Payment failed
            elif event_type == "invoice.payment_failed":
                invoice = data
                customer_id = invoice.get("customer")
                subscription_id = invoice.get("subscription")
                amount_due = invoice.get("amount_due", 0)
                currency = invoice.get("currency", "usd").upper()
                invoice_id = invoice.get("id")

                # Convert amount from cents to dollars using Decimal for precision
                if amount_due and isinstance(amount_due, (int, float)):
                    amount_due = Decimal(str(amount_due)) / Decimal("100")

                result.update(
                    {
                        "handled": True,
                        "action": "payment_failed",
                        "customer_id": customer_id,
                        "subscription_id": subscription_id,
                        "amount_due": amount_due,
                        "currency": currency,
                        "invoice_id": invoice_id,
                    }
                )

                logger.warning(
                    "payment_failed",
                    customer_id=customer_id,
                    subscription_id=subscription_id,
                    amount_due=amount_due,
                    invoice_id=invoice_id,
                )

            else:
                logger.info("webhook_event_ignored", event_type=event_type)

            return result


async def apply_webhook_action(
    result: dict[str, Any],
    user_repo: Any,
    db: Any = None,
) -> bool:
    """
    Apply a webhook action to the user's subscription in the database.

    After any subscription tier change (activate, update, deactivate), the
    in-memory and Redis tier caches are invalidated immediately so that the
    next request sees the new tier without waiting for the 30 s TTL to expire.

    Args:
        result: Dict returned by StripeService.handle_webhook_event.
        user_repo: UserRepository instance for DB access.
        db: AsyncSession — required for payment_failed dunning flow.

    Returns:
        True if a DB update was applied, False otherwise.
    """
    from api.dependencies import invalidate_tier_cache

    if not result.get("handled"):
        return False

    action = result["action"]
    user_id = result.get("user_id")

    # payment_failed events come from invoices which carry no user metadata.
    # Resolve the user via the stripe_customer_id column instead.
    if not user_id and action == "payment_failed" and result.get("customer_id"):
        customer_id_for_lookup = result["customer_id"]
        resolved = await user_repo.get_by_stripe_customer_id(customer_id_for_lookup)
        if resolved:
            user_id = str(resolved.id)
        else:
            logger.warning(
                "payment_failed_customer_not_found",
                customer_id=customer_id_for_lookup,
            )
            return False

    if not user_id:
        return False
    tier = result.get("tier")
    customer_id = result.get("customer_id")

    user = await user_repo.get_by_id(user_id)
    if not user:
        logger.warning("webhook_user_not_found", user_id=user_id, action=action)
        return False

    if action == "activate_subscription":
        user.subscription_tier = tier or "pro"
        user.stripe_customer_id = customer_id
        await user_repo.update(user_id, user)
        await invalidate_tier_cache(user_id)
        logger.info("tier_cache_invalidated", user_id=user_id, action=action)
    elif action == "update_subscription":
        user.subscription_tier = tier or user.subscription_tier
        await user_repo.update(user_id, user)
        await invalidate_tier_cache(user_id)
        logger.info("tier_cache_invalidated", user_id=user_id, action=action)
    elif action == "deactivate_subscription":
        user.subscription_tier = "free"
        await user_repo.update(user_id, user)
        await invalidate_tier_cache(user_id)
        logger.info("tier_cache_invalidated", user_id=user_id, action=action)
    elif action == "payment_failed":
        if db is not None:
            from services.dunning_service import DunningService

            dunning = DunningService(db)
            user = await user_repo.get_by_id(user_id)
            user_email = user.email if user else ""
            user_name = user.name if user else ""

            await dunning.handle_payment_failure(
                user_id=user_id,
                stripe_invoice_id=result.get("invoice_id", ""),
                stripe_customer_id=customer_id or "",
                amount_owed=result.get("amount_due"),
                currency=result.get("currency", "USD"),
                user_email=user_email,
                user_name=user_name or "",
                user_repo=user_repo,
            )
        else:
            logger.warning(
                "payment_failed_no_db_session",
                user_id=user_id,
                customer_id=customer_id,
            )
    else:
        return False

    return True
