"""
UtilityAPI Meter Monitoring Add-On Billing Service

Manages the $2.25/meter/month add-on for UtilityAPI direct connections.
Available on all tiers (including Free). Uses Stripe subscription items
for quantity-based billing.

Cost breakdown:
  - UtilityAPI charges RateShift $1.50/meter/month
  - RateShift charges users $2.25/meter/month (50% markup)
"""

import asyncio
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import stripe
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from lib.tracing import traced

logger = structlog.get_logger(__name__)

# Use Decimal for currency to avoid float drift. With ≥40 meters, the float
# expression `40 * 2.25` rounds to 90.00000000000001 — fine for display but
# diverges from Stripe-side reconciliation and Origin Financial bookkeeping.
PRICE_PER_METER_USD: Decimal = Decimal("2.25")
_CENTS = Decimal("0.01")


def _meter_total(meter_count: int) -> Decimal:
    """Return the monthly total for ``meter_count`` meters, rounded to cents."""
    return (Decimal(meter_count) * PRICE_PER_METER_USD).quantize(_CENTS, rounding=ROUND_HALF_UP)


class UtilityAPIBillingService:
    """Manages UtilityAPI meter monitoring billing as a Stripe add-on."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def add_meters(
        self,
        user_id: str,
        connection_id: str,
        meter_count: int,
        *,
        success_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict[str, Any]:
        """Add meter billing for a UtilityAPI connection.

        Returns:
            {subscription_item_id, checkout_url} — checkout_url is set only
            for users who need to complete payment via Stripe Checkout.
        """
        async with traced(
            "billing.add_meters",
            attributes={"billing.meter_count": meter_count, "billing.user_id": user_id},
        ):
            if meter_count < 1:
                raise ValueError("meter_count must be at least 1")

            price_id = settings.stripe_price_utilityapi_meter
            if not price_id:
                logger.warning("utilityapi_billing_price_not_configured")
                raise ValueError(
                    "STRIPE_PRICE_UTILITYAPI_METER is not configured. "
                    "Cannot bill for UtilityAPI meters."
                )

            # Look up user's Stripe customer ID and existing subscription
            user_result = await self._db.execute(
                text(
                    "SELECT stripe_customer_id, subscription_tier FROM public.users WHERE id = :uid"
                ),
                {"uid": user_id},
            )
            user_row = user_result.mappings().first()
            if not user_row:
                raise ValueError(f"User {user_id} not found")

            customer_id = user_row["stripe_customer_id"]
            tier = user_row["subscription_tier"] or "free"

            # Calculate total meters across all active connections for this user
            existing_meters = await self._get_total_meters(
                user_id, exclude_connection_id=connection_id
            )
            new_total = existing_meters + meter_count

            if customer_id and tier in ("pro", "business"):
                # User has an active subscription — add/update subscription item
                result = await self._add_to_existing_subscription(
                    customer_id=customer_id,
                    user_id=user_id,
                    connection_id=connection_id,
                    meter_count=meter_count,
                    new_total=new_total,
                    price_id=price_id,
                )
                return result
            else:
                # Free tier or no subscription — create Stripe Checkout session
                result = await self._create_addon_checkout(
                    user_id=user_id,
                    customer_id=customer_id,
                    connection_id=connection_id,
                    meter_count=meter_count,
                    price_id=price_id,
                    success_url=success_url or f"{settings.frontend_url}/connections?addon=success",
                    cancel_url=cancel_url or f"{settings.frontend_url}/connections?addon=cancelled",
                )
                return result

    async def remove_meters(self, user_id: str, connection_id: str) -> None:
        """Remove a connection's meters from billing."""
        async with traced(
            "billing.remove_meters",
            attributes={"billing.user_id": user_id, "billing.connection_id": connection_id},
        ):
            # Read connection's current billing info
            conn_result = await self._db.execute(
                text("""
                    SELECT stripe_subscription_item_id, utilityapi_meter_count
                    FROM user_connections
                    WHERE id = :cid AND user_id = :uid
                """),
                {"cid": connection_id, "uid": user_id},
            )
            conn_row = conn_result.mappings().first()
            if not conn_row or not conn_row["stripe_subscription_item_id"]:
                logger.info(
                    "remove_meters_no_billing",
                    connection_id=connection_id,
                    user_id=user_id,
                )
                return

            si_id = conn_row["stripe_subscription_item_id"]

            # Calculate new total across all OTHER active connections
            new_total = await self._get_total_meters(user_id, exclude_connection_id=connection_id)

            try:
                if new_total > 0:
                    # Other connections still have meters — update quantity
                    await asyncio.to_thread(
                        stripe.SubscriptionItem.modify,
                        si_id,
                        quantity=new_total,
                    )
                    logger.info(
                        "subscription_item_quantity_reduced",
                        si_id=si_id,
                        new_quantity=new_total,
                        user_id=user_id,
                    )
                else:
                    # No more meters — delete the subscription item entirely
                    await asyncio.to_thread(
                        stripe.SubscriptionItem.delete,
                        si_id,
                    )
                    logger.info(
                        "subscription_item_deleted",
                        si_id=si_id,
                        user_id=user_id,
                    )
            except stripe.StripeError as e:
                logger.error(
                    "remove_meters_stripe_error",
                    si_id=si_id,
                    user_id=user_id,
                    error=str(e),
                )
                raise

            # Clear billing fields on the connection
            await self._db.execute(
                text("""
                    UPDATE user_connections
                    SET stripe_subscription_item_id = NULL,
                        utilityapi_meter_count = 0
                    WHERE id = :cid AND user_id = :uid
                """),
                {"cid": connection_id, "uid": user_id},
            )
            await self._db.commit()

    async def get_addon_pricing(self, user_id: str) -> dict[str, Any]:
        """Return pricing info for frontend display.

        Currency values are computed as Decimal and stringified for transport
        so JSON consumers (frontend, Origin reconciliation) see exact cents
        rather than float-truncated representations.
        """
        current_meters = await self._get_total_meters(user_id)
        return {
            "price_per_meter": str(PRICE_PER_METER_USD),
            "current_meters": current_meters,
            "monthly_total": str(_meter_total(current_meters)),
            "currency": "usd",
        }

    async def finalize_checkout(self, connection_id: str) -> None:
        """Called from webhook when a user completes add-on checkout.

        Links the Stripe subscription item to the connection record.
        """
        async with traced(
            "billing.finalize_checkout",
            attributes={"billing.connection_id": connection_id},
        ):
            # Look up connection to get user_id and meter_count
            conn_result = await self._db.execute(
                text("""
                    SELECT user_id, utilityapi_meter_count
                    FROM user_connections
                    WHERE id = :cid
                """),
                {"cid": connection_id},
            )
            conn_row = conn_result.mappings().first()
            if not conn_row:
                logger.error("finalize_checkout_connection_not_found", connection_id=connection_id)
                return

            user_id = str(conn_row["user_id"])

            # Look up the user's Stripe customer to find the subscription item
            user_result = await self._db.execute(
                text("SELECT stripe_customer_id FROM public.users WHERE id = :uid"),
                {"uid": user_id},
            )
            user_row = user_result.mappings().first()
            if not user_row or not user_row["stripe_customer_id"]:
                logger.error("finalize_checkout_no_customer", user_id=user_id)
                return

            customer_id = user_row["stripe_customer_id"]
            price_id = settings.stripe_price_utilityapi_meter

            # Find the subscription item with our add-on price
            si_id = await self._find_addon_subscription_item(customer_id, price_id)
            if not si_id:
                logger.error(
                    "finalize_checkout_si_not_found",
                    customer_id=customer_id,
                    connection_id=connection_id,
                )
                return

            # Link the subscription item to the connection
            await self._db.execute(
                text("""
                    UPDATE user_connections
                    SET stripe_subscription_item_id = :si_id
                    WHERE id = :cid
                """),
                {"si_id": si_id, "cid": connection_id},
            )
            await self._db.commit()

            logger.info(
                "addon_checkout_finalized",
                connection_id=connection_id,
                si_id=si_id,
                user_id=user_id,
            )

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _get_total_meters(
        self, user_id: str, *, exclude_connection_id: str | None = None
    ) -> int:
        """Sum utilityapi_meter_count across all active direct connections."""
        if exclude_connection_id:
            result = await self._db.execute(
                text("""
                    SELECT COALESCE(SUM(utilityapi_meter_count), 0) AS total
                    FROM user_connections
                    WHERE user_id = :uid
                      AND connection_type = 'direct'
                      AND status = 'active'
                      AND id != :exclude_id
                """),
                {"uid": user_id, "exclude_id": exclude_connection_id},
            )
        else:
            result = await self._db.execute(
                text("""
                    SELECT COALESCE(SUM(utilityapi_meter_count), 0) AS total
                    FROM user_connections
                    WHERE user_id = :uid
                      AND connection_type = 'direct'
                      AND status = 'active'
                """),
                {"uid": user_id},
            )
        row = result.mappings().first()
        return int(row["total"]) if row else 0

    async def _add_to_existing_subscription(
        self,
        customer_id: str,
        user_id: str,
        connection_id: str,
        meter_count: int,
        new_total: int,
        price_id: str,
    ) -> dict[str, Any]:
        """Add meters to an existing Pro/Business subscription."""
        # Find existing add-on subscription item
        si_id = await self._find_addon_subscription_item(customer_id, price_id)

        try:
            if si_id:
                # Update existing item quantity
                await asyncio.to_thread(
                    stripe.SubscriptionItem.modify,
                    si_id,
                    quantity=new_total,
                )
                logger.info(
                    "subscription_item_quantity_updated",
                    si_id=si_id,
                    quantity=new_total,
                    user_id=user_id,
                )
            else:
                # Add new line item to the subscription
                subscriptions = await asyncio.to_thread(
                    stripe.Subscription.list,
                    customer=customer_id,
                    status="active",
                    limit=1,
                )
                if not subscriptions.data:
                    raise ValueError("No active subscription found for customer")

                sub = subscriptions.data[0]
                modified_sub = await asyncio.to_thread(
                    stripe.Subscription.modify,
                    sub.id,
                    items=[{"price": price_id, "quantity": new_total}],
                    metadata={"has_utilityapi_addon": "true"},
                )

                # Find the newly added item
                for item in modified_sub["items"]["data"]:
                    if item["price"]["id"] == price_id:
                        si_id = item["id"]
                        break

                logger.info(
                    "subscription_item_added",
                    si_id=si_id,
                    quantity=new_total,
                    subscription_id=sub.id,
                    user_id=user_id,
                )
        except stripe.StripeError as e:
            logger.error(
                "add_meters_stripe_error",
                user_id=user_id,
                connection_id=connection_id,
                error=str(e),
            )
            raise

        # Store billing info on the connection
        await self._db.execute(
            text("""
                UPDATE user_connections
                SET stripe_subscription_item_id = :si_id,
                    utilityapi_meter_count = :meter_count
                WHERE id = :cid
            """),
            {"si_id": si_id, "meter_count": meter_count, "cid": connection_id},
        )
        await self._db.commit()

        from api.dependencies import invalidate_tier_cache

        await invalidate_tier_cache(user_id)

        return {"subscription_item_id": si_id, "checkout_url": None}

    async def _create_addon_checkout(
        self,
        user_id: str,
        customer_id: str | None,
        connection_id: str,
        meter_count: int,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, Any]:
        """Create a Stripe Checkout session for the add-on (Free tier users)."""
        # Store meter_count on connection as pending
        await self._db.execute(
            text("""
                UPDATE user_connections
                SET utilityapi_meter_count = :meter_count
                WHERE id = :cid
            """),
            {"meter_count": meter_count, "cid": connection_id},
        )
        await self._db.commit()

        # Look up user email
        user_result = await self._db.execute(
            text("SELECT email FROM public.users WHERE id = :uid"),
            {"uid": user_id},
        )
        user_row = user_result.mappings().first()
        email = user_row["email"] if user_row else None

        customer_params = {}
        if customer_id:
            customer_params["customer"] = customer_id
        elif email:
            customer_params["customer_email"] = email

        try:
            session = await asyncio.to_thread(
                stripe.checkout.Session.create,
                **customer_params,
                mode="subscription",
                line_items=[{"price": price_id, "quantity": meter_count}],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "user_id": user_id,
                    "addon_type": "utilityapi_meter",
                    "connection_id": connection_id,
                },
                subscription_data={
                    "metadata": {
                        "user_id": user_id,
                        "has_utilityapi_addon": "true",
                    }
                },
            )
            logger.info(
                "addon_checkout_session_created",
                session_id=session.id,
                user_id=user_id,
                connection_id=connection_id,
                meter_count=meter_count,
            )
            return {"subscription_item_id": None, "checkout_url": session.url}
        except stripe.StripeError as e:
            logger.error(
                "addon_checkout_create_failed",
                user_id=user_id,
                connection_id=connection_id,
                error=str(e),
            )
            raise

    async def _find_addon_subscription_item(
        self, customer_id: str, price_id: str | None
    ) -> str | None:
        """Find existing UtilityAPI add-on subscription item for a customer."""
        if not price_id:
            return None

        try:
            subscriptions = await asyncio.to_thread(
                stripe.Subscription.list,
                customer=customer_id,
                status="active",
                limit=5,
            )
            for sub in subscriptions.data:
                for item in sub["items"]["data"]:
                    if item["price"]["id"] == price_id:
                        return item["id"]
        except stripe.StripeError as e:
            logger.warning(
                "find_addon_si_failed",
                customer_id=customer_id,
                error=str(e),
            )
        return None
