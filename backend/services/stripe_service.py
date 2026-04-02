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
from sqlalchemy import text

from config.settings import settings
from lib.tracing import traced

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Set stripe.api_key once at module load time.
#
# Previously this was done inside StripeService.__init__(), which meant every
# construction of the service (i.e. every request) was mutating a module-level
# global — not concurrency-safe under async load.  Setting it here ensures:
#   1. The assignment runs exactly once per process startup.
#   2. No concurrent request can interleave a different key mid-flight
#      (the global stripe library does not support per-client keys in v7-).
#   3. StripeService.__init__() no longer writes to shared mutable state.
#
# NOTE: When upgrading to stripe-python v7+ that exposes a per-client
# ``stripe.StripeClient``, migrate all SDK calls to use that client
# object instead and remove this module-level assignment entirely.
# ---------------------------------------------------------------------------
if settings.stripe_secret_key:
    stripe.api_key = settings.stripe_secret_key
    key_mode = "live" if settings.stripe_secret_key.startswith("sk_live_") else "test"
    logger.info("stripe_api_key_set", mode=key_mode)


class StripeService:
    """
    Service for managing Stripe subscriptions and payments.

    Tiers:
    - Free: $0 (basic price view, 1 alert, manual scheduling)
    - Pro: $4.99/mo (unlimited alerts, ML forecasts, optimization, weather)
    - Business: $14.99/mo (API access, multi-property, priority support)
    """

    def __init__(self, db=None):
        """Initialize Stripe service.

        The stripe.api_key is set once at module load time (see module-level
        code above) rather than here per-request, so this constructor no longer
        mutates any global state.
        """
        self._db = db
        if not settings.stripe_secret_key:
            logger.warning("stripe_not_configured", message="STRIPE_SECRET_KEY not set")
            self._configured = False
        else:
            self._configured = True

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
                addon_type = session.get("metadata", {}).get("addon_type")

                if addon_type == "utilityapi_meter":
                    # UtilityAPI add-on checkout completed
                    result.update(
                        {
                            "handled": True,
                            "action": "activate_addon",
                            "user_id": user_id,
                            "customer_id": customer_id,
                            "addon_connection_id": session.get("metadata", {}).get("connection_id"),
                        }
                    )
                    logger.info(
                        "addon_checkout_completed",
                        user_id=user_id,
                        customer_id=customer_id,
                        addon_type=addon_type,
                    )
                else:
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

            # Payment succeeded — reactivate tier and clear dunning state.
            # This is the counterpart to invoice.payment_failed: when Stripe
            # successfully charges a past-due invoice the user's subscription
            # should be re-activated and any dunning escalation reversed.
            elif event_type == "invoice.payment_succeeded":
                invoice = data
                customer_id = invoice.get("customer")
                subscription_id = invoice.get("subscription")
                # billing_reason "subscription_cycle" = normal renewal;
                # "subscription_update" = plan change; "subscription_create" =
                # first charge.  We handle all of them the same way.
                billing_reason = invoice.get("billing_reason", "")
                invoice_id = invoice.get("id")

                result.update(
                    {
                        "handled": True,
                        "action": "payment_succeeded",
                        "customer_id": customer_id,
                        "subscription_id": subscription_id,
                        "billing_reason": billing_reason,
                        "invoice_id": invoice_id,
                    }
                )

                logger.info(
                    "payment_succeeded",
                    customer_id=customer_id,
                    subscription_id=subscription_id,
                    billing_reason=billing_reason,
                    invoice_id=invoice_id,
                )

            # Charge refunded — flag user account for review.
            # Stripe does not automatically cancel the subscription on refund,
            # so we flag the user for manual review rather than auto-downgrading.
            # A full refund may indicate fraud or a billing dispute; the ops team
            # should verify before revoking access.
            elif event_type == "charge.refunded":
                charge = data
                customer_id = charge.get("customer")
                charge_id = charge.get("id")
                amount_refunded = charge.get("amount_refunded", 0)
                currency = charge.get("currency", "usd").upper()

                # Convert cents to dollars
                if amount_refunded and isinstance(amount_refunded, (int, float)):
                    amount_refunded = Decimal(str(amount_refunded)) / Decimal("100")

                result.update(
                    {
                        "handled": True,
                        "action": "charge_refunded",
                        "customer_id": customer_id,
                        "charge_id": charge_id,
                        "amount_refunded": amount_refunded,
                        "currency": currency,
                    }
                )

                logger.warning(
                    "charge_refunded",
                    customer_id=customer_id,
                    charge_id=charge_id,
                    amount_refunded=amount_refunded,
                )

            # Dispute created — flag account immediately.
            # Chargebacks are a fraud signal; flag the account so ops can
            # review and, if warranted, freeze it before evidence is submitted.
            elif event_type == "charge.dispute.created":
                dispute = data
                customer_id = dispute.get("customer") or (
                    # Disputes may not have direct customer — look it up from charge
                    None
                )
                charge_id = dispute.get("charge")
                dispute_id = dispute.get("id")
                dispute_reason = dispute.get("reason", "unknown")
                dispute_amount = dispute.get("amount", 0)
                currency = dispute.get("currency", "usd").upper()

                if dispute_amount and isinstance(dispute_amount, (int, float)):
                    dispute_amount = Decimal(str(dispute_amount)) / Decimal("100")

                result.update(
                    {
                        "handled": True,
                        "action": "dispute_created",
                        "customer_id": customer_id,
                        "charge_id": charge_id,
                        "dispute_id": dispute_id,
                        "dispute_reason": dispute_reason,
                        "dispute_amount": dispute_amount,
                        "currency": currency,
                    }
                )

                logger.warning(
                    "dispute_created",
                    customer_id=customer_id,
                    charge_id=charge_id,
                    dispute_id=dispute_id,
                    dispute_reason=dispute_reason,
                    dispute_amount=dispute_amount,
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

    if action == "activate_addon":
        # UtilityAPI add-on checkout completed — finalize billing link
        addon_connection_id = result.get("addon_connection_id")
        if addon_connection_id and db is not None:
            from services.utilityapi_billing_service import UtilityAPIBillingService

            billing_svc = UtilityAPIBillingService(db)
            await billing_svc.finalize_checkout(addon_connection_id)
            # Also store customer_id on user if not already set
            if customer_id and not user.stripe_customer_id:
                user.stripe_customer_id = customer_id
                await user_repo.update(user_id, user)
        return True

    elif action == "activate_subscription":
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
        # Disconnect all UtilityAPI connections when subscription is fully canceled
        if db is not None:
            try:
                await db.execute(
                    text("""
                        UPDATE user_connections
                        SET status = 'disconnected',
                            stripe_subscription_item_id = NULL,
                            utilityapi_meter_count = 0
                        WHERE user_id = :uid
                          AND connection_type = 'direct'
                          AND status = 'active'
                    """),
                    {"uid": user_id},
                )
                logger.info("utilityapi_connections_disconnected_on_cancel", user_id=user_id)
            except Exception as exc:
                logger.warning(
                    "utilityapi_disconnect_on_cancel_failed",
                    user_id=user_id,
                    error=str(exc),
                )
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

    elif action == "payment_succeeded":
        # Re-activate user's subscription tier after a successful payment.
        #
        # This reverses any dunning escalation: if the user was downgraded to
        # free tier after 3+ payment failures and then catches up, they should
        # be restored to their paid tier.  We query the current Stripe
        # subscription to determine the authoritative tier rather than relying
        # on stale metadata in the invoice.
        if db is not None:
            subscription_id = result.get("subscription_id")
            restored_tier: str | None = None

            if subscription_id:
                try:
                    subscription = await asyncio.to_thread(
                        stripe.Subscription.retrieve, subscription_id
                    )
                    restored_tier = subscription.metadata.get("tier")
                    # Stripe may store sub-status "active" after payment
                    # succeeds; only restore if subscription is actually live.
                    if subscription.status not in ("active", "trialing"):
                        logger.info(
                            "payment_succeeded_subscription_not_active",
                            user_id=user_id,
                            subscription_id=subscription_id,
                            status=subscription.status,
                        )
                        restored_tier = None
                except stripe.StripeError as e:
                    logger.warning(
                        "payment_succeeded_subscription_lookup_failed",
                        user_id=user_id,
                        subscription_id=subscription_id,
                        error=str(e),
                    )

            if restored_tier and restored_tier in ("pro", "business"):
                user.subscription_tier = restored_tier
                await user_repo.update(user_id, user)
                await invalidate_tier_cache(user_id)
                logger.info(
                    "tier_restored_after_payment",
                    user_id=user_id,
                    tier=restored_tier,
                    subscription_id=subscription_id,
                )
            else:
                # Could not determine tier from Stripe — log for ops review
                # but do not downgrade; err on the side of granting access.
                logger.warning(
                    "payment_succeeded_tier_unknown",
                    user_id=user_id,
                    customer_id=customer_id,
                    subscription_id=subscription_id,
                )
        else:
            logger.warning(
                "payment_succeeded_no_db_session",
                user_id=user_id,
                customer_id=customer_id,
            )

    elif action in ("charge_refunded", "dispute_created"):
        # Flag account for ops review — we do not auto-downgrade because:
        #   - Refunds: Stripe subscription may still be valid (partial refund,
        #     goodwill refund, etc.). Ops should verify intent.
        #   - Disputes: evidence window is time-limited; flagging triggers alert
        #     so ops can respond within Stripe's 7-21 day window.
        #
        # We log a structured WARNING at CRITICAL severity to ensure alert
        # routing (Sentry/Slack) picks it up without a code path to DB.
        charge_id = result.get("charge_id", "unknown")
        dispute_id = result.get("dispute_id", "unknown")
        if action == "dispute_created":
            logger.warning(
                "account_dispute_flagged_for_review",
                user_id=user_id,
                customer_id=customer_id,
                charge_id=charge_id,
                dispute_id=dispute_id,
                dispute_reason=result.get("dispute_reason", "unknown"),
                dispute_amount=result.get("dispute_amount"),
                severity="CRITICAL",
                action_required="ops_review",
            )
        else:
            logger.warning(
                "account_refund_flagged_for_review",
                user_id=user_id,
                customer_id=customer_id,
                charge_id=charge_id,
                amount_refunded=result.get("amount_refunded"),
                severity="HIGH",
                action_required="ops_review",
            )

    else:
        return False

    return True
