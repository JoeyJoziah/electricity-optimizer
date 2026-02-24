"""
Stripe Monetization Service

Handles subscription lifecycle, checkout sessions, webhooks, and customer portal.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import structlog
import stripe

from config.settings import settings

logger = structlog.get_logger(__name__)


class StripeService:
    """
    Service for managing Stripe subscriptions and payments.

    Tiers:
    - Free: $0 (basic price view, 1 alert, manual scheduling)
    - Pro: $4.99/mo (unlimited alerts, ML forecasts, optimization, weather)
    - Business: $14.99/mo (API access, multi-property, priority support)
    """

    def __init__(self):
        """Initialize Stripe service with API key from settings."""
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

    def _get_price_id_for_tier(self, tier: str) -> Optional[str]:
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
        tier: str,
        success_url: str,
        cancel_url: str,
        customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a Stripe Checkout session for subscription.

        Args:
            user_id: User ID from our database
            email: User email
            tier: Subscription tier (pro, business)
            success_url: URL to redirect after successful checkout
            cancel_url: URL to redirect if checkout is cancelled
            customer_id: Existing Stripe customer ID (if any)

        Returns:
            Dict with checkout session info (id, url)

        Raises:
            ValueError: If Stripe not configured or invalid tier
            stripe.error.StripeError: On Stripe API errors
        """
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

        except stripe.error.StripeError as e:
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
    ) -> Dict[str, str]:
        """
        Create a Stripe Customer Portal session for subscription management.

        Args:
            customer_id: Stripe customer ID
            return_url: URL to return to after portal session

        Returns:
            Dict with portal session URL

        Raises:
            ValueError: If Stripe not configured
            stripe.error.StripeError: On Stripe API errors
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

        except stripe.error.StripeError as e:
            logger.error(
                "portal_session_failed",
                customer_id=customer_id,
                error=str(e),
            )
            raise

    async def get_subscription_status(
        self,
        customer_id: str,
    ) -> Optional[Dict[str, Any]]:
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
            stripe.error.StripeError: On Stripe API errors
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
                    subscription.current_period_end, tz=timezone.utc
                ),
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "subscription_id": subscription.id,
            }

        except stripe.error.StripeError as e:
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
    ) -> Dict[str, Any]:
        """
        Cancel a subscription.

        Args:
            subscription_id: Stripe subscription ID
            cancel_immediately: If True, cancel now. If False, cancel at period end.

        Returns:
            Dict with updated subscription info

        Raises:
            ValueError: If Stripe not configured
            stripe.error.StripeError: On Stripe API errors
        """
        self._ensure_configured()

        try:
            if cancel_immediately:
                subscription = await asyncio.to_thread(
                    stripe.Subscription.cancel, subscription_id
                )
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

        except stripe.error.StripeError as e:
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
        except stripe.error.SignatureVerificationError as e:
            logger.error("webhook_signature_verification_failed", error=str(e))
            raise ValueError("Invalid webhook signature") from e

    async def handle_webhook_event(
        self,
        event: stripe.Event,
    ) -> Dict[str, Any]:
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

            result.update({
                "handled": True,
                "action": "activate_subscription",
                "user_id": user_id,
                "tier": tier,
                "customer_id": customer_id,
            })

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

            result.update({
                "handled": True,
                "action": "update_subscription",
                "user_id": user_id,
                "tier": tier if status == "active" else "free",
                "customer_id": customer_id,
                "status": status,
            })

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

            result.update({
                "handled": True,
                "action": "deactivate_subscription",
                "user_id": user_id,
                "tier": "free",
                "customer_id": customer_id,
            })

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

            result.update({
                "handled": True,
                "action": "payment_failed",
                "customer_id": customer_id,
                "subscription_id": subscription_id,
            })

            logger.warning(
                "payment_failed",
                customer_id=customer_id,
                subscription_id=subscription_id,
            )

        else:
            logger.info("webhook_event_ignored", event_type=event_type)

        return result



async def apply_webhook_action(
    result: Dict[str, Any],
    user_repo: Any,
) -> bool:
    """
    Apply a webhook action to the user's subscription in the database.

    Args:
        result: Dict returned by StripeService.handle_webhook_event.
        user_repo: UserRepository instance for DB access.

    Returns:
        True if a DB update was applied, False otherwise.
    """
    if not result.get("handled") or not result.get("user_id"):
        return False

    action = result["action"]
    user_id = result["user_id"]
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
    elif action == "update_subscription":
        user.subscription_tier = tier or user.subscription_tier
        await user_repo.update(user_id, user)
    elif action == "deactivate_subscription":
        user.subscription_tier = "free"
        await user_repo.update(user_id, user)
    elif action == "payment_failed":
        logger.warning(
            "payment_failed_notification",
            user_id=user_id,
            customer_id=customer_id,
        )
    else:
        return False

    return True
