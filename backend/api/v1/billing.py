"""
Billing API Endpoints

Stripe integration for subscription management.
"""

from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, HttpUrl, field_validator
import structlog
import stripe

from api.dependencies import get_current_user, TokenData
from services.stripe_service import StripeService

logger = structlog.get_logger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


ALLOWED_REDIRECT_DOMAINS = [
    "electricity-optimizer.vercel.app",
    "electricity-optimizer-frontend.onrender.com",
    "localhost",
]


class CheckoutSessionRequest(BaseModel):
    """Request to create a checkout session."""

    tier: str = Field(..., pattern=r"^(pro|business)$", description="Subscription tier")
    success_url: HttpUrl = Field(..., description="URL to redirect after successful checkout")
    cancel_url: HttpUrl = Field(..., description="URL to redirect if checkout is cancelled")

    @field_validator("success_url", "cancel_url")
    @classmethod
    def validate_redirect_domain(cls, v):
        parsed = urlparse(str(v))
        hostname = parsed.hostname or ""
        if not any(
            hostname == d or hostname.endswith(f".{d}")
            for d in ALLOWED_REDIRECT_DOMAINS
        ):
            raise ValueError(
                f"Redirect URL domain '{hostname}' is not allowed. "
                f"Must be one of: {', '.join(ALLOWED_REDIRECT_DOMAINS)}"
            )
        return v


class CheckoutSessionResponse(BaseModel):
    """Response containing checkout session details."""

    session_id: str
    checkout_url: str


class PortalSessionRequest(BaseModel):
    """Request to create a customer portal session."""

    return_url: HttpUrl = Field(..., description="URL to return to after portal session")


class PortalSessionResponse(BaseModel):
    """Response containing customer portal URL."""

    portal_url: str


class SubscriptionStatusResponse(BaseModel):
    """Response containing subscription status."""

    tier: str
    status: str
    has_active_subscription: bool
    current_period_end: Optional[str] = None
    cancel_at_period_end: Optional[bool] = None


class WebhookEventResponse(BaseModel):
    """Response for webhook processing."""

    received: bool
    event_id: str


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/checkout",
    response_model=CheckoutSessionResponse,
    summary="Create Stripe checkout session",
    responses={
        200: {"description": "Checkout session created successfully"},
        400: {"description": "Invalid tier or configuration error"},
        401: {"description": "Authentication required"},
        503: {"description": "Stripe not configured"},
    },
)
async def create_checkout_session(
    request: CheckoutSessionRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Create a Stripe Checkout session for subscription.

    Requires authentication. Returns a checkout URL where the user
    can complete payment and subscribe to the selected tier.
    """
    stripe_service = StripeService()

    if not stripe_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing system is not configured. Please contact support.",
        )

    try:
        # TODO: Fetch user details and existing customer_id from database
        # For now, use token data
        user_email = current_user.email or "user@example.com"

        session_data = await stripe_service.create_checkout_session(
            user_id=current_user.user_id,
            email=user_email,
            tier=request.tier,
            success_url=str(request.success_url),
            cancel_url=str(request.cancel_url),
            customer_id=None,  # TODO: Get from user model
        )

        return CheckoutSessionResponse(
            session_id=session_data["id"],
            checkout_url=session_data["url"],
        )

    except ValueError as e:
        logger.warning(
            "checkout_session_invalid",
            user_id=current_user.user_id,
            tier=request.tier,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except stripe.error.StripeError as e:
        logger.error(
            "checkout_session_stripe_error",
            user_id=current_user.user_id,
            tier=request.tier,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session. Please try again.",
        )


@router.post(
    "/portal",
    response_model=PortalSessionResponse,
    summary="Create customer portal session",
    responses={
        200: {"description": "Portal session created successfully"},
        400: {"description": "No active subscription"},
        401: {"description": "Authentication required"},
        503: {"description": "Stripe not configured"},
    },
)
async def create_portal_session(
    request: PortalSessionRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Create a Stripe Customer Portal session for subscription management.

    Requires authentication and an active subscription.
    Returns a portal URL where users can manage their subscription,
    update payment methods, and view billing history.
    """
    stripe_service = StripeService()

    if not stripe_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing system is not configured. Please contact support.",
        )

    # TODO: Fetch user's stripe_customer_id from database
    # For now, raise error
    customer_id = None  # TODO: Get from user model

    if not customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription found. Please subscribe first.",
        )

    try:
        session_data = await stripe_service.create_customer_portal_session(
            customer_id=customer_id,
            return_url=str(request.return_url),
        )

        return PortalSessionResponse(
            portal_url=session_data["url"],
        )

    except stripe.error.StripeError as e:
        logger.error(
            "portal_session_stripe_error",
            user_id=current_user.user_id,
            customer_id=customer_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create portal session. Please try again.",
        )


@router.get(
    "/subscription",
    response_model=SubscriptionStatusResponse,
    summary="Get subscription status",
    responses={
        200: {"description": "Subscription status retrieved successfully"},
        401: {"description": "Authentication required"},
        503: {"description": "Stripe not configured"},
    },
)
async def get_subscription_status(
    current_user: TokenData = Depends(get_current_user),
):
    """
    Get current subscription status for the authenticated user.

    Returns subscription tier, status, and billing period information.
    """
    stripe_service = StripeService()

    if not stripe_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing system is not configured. Please contact support.",
        )

    # TODO: Fetch user's stripe_customer_id from database
    customer_id = None  # TODO: Get from user model

    if not customer_id:
        # No customer ID means user is on free tier
        return SubscriptionStatusResponse(
            tier="free",
            status="active",
            has_active_subscription=False,
        )

    try:
        subscription = await stripe_service.get_subscription_status(customer_id)

        if not subscription:
            # Customer exists but no active subscription
            return SubscriptionStatusResponse(
                tier="free",
                status="active",
                has_active_subscription=False,
            )

        # Determine if subscription is active
        active_statuses = ["active", "trialing"]
        has_active = subscription["status"] in active_statuses

        return SubscriptionStatusResponse(
            tier=subscription["tier"],
            status=subscription["status"],
            has_active_subscription=has_active,
            current_period_end=subscription["current_period_end"].isoformat(),
            cancel_at_period_end=subscription["cancel_at_period_end"],
        )

    except stripe.error.StripeError as e:
        logger.error(
            "subscription_status_stripe_error",
            user_id=current_user.user_id,
            customer_id=customer_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve subscription status. Please try again.",
        )


@router.post(
    "/webhook",
    response_model=WebhookEventResponse,
    summary="Handle Stripe webhooks",
    responses={
        200: {"description": "Webhook processed successfully"},
        400: {"description": "Invalid webhook signature"},
        503: {"description": "Stripe not configured"},
    },
)
async def handle_stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.

    This endpoint is called by Stripe to notify us of subscription changes,
    payment events, and other billing activities. It verifies the webhook
    signature and processes the event.

    No authentication required - security is handled via webhook signature.
    """
    stripe_service = StripeService()

    if not stripe_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing system is not configured.",
        )

    # Get raw body and signature
    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )

    try:
        # Verify webhook signature
        event = stripe_service.verify_webhook_signature(payload, signature)

        # Process the event
        result = await stripe_service.handle_webhook_event(event)

        # TODO: Update user record in database based on result
        if result["handled"]:
            action = result["action"]
            user_id = result.get("user_id")
            tier = result.get("tier")
            customer_id = result.get("customer_id")

            logger.info(
                "webhook_processed",
                event_id=event["id"],
                action=action,
                user_id=user_id,
                tier=tier,
                customer_id=customer_id,
            )

            # TODO: Database operations
            # - activate_subscription: Update user.subscription_tier and user.stripe_customer_id
            # - update_subscription: Update user.subscription_tier
            # - deactivate_subscription: Set user.subscription_tier to "free"
            # - payment_failed: Send notification to user

        return WebhookEventResponse(
            received=True,
            event_id=event["id"],
        )

    except ValueError as e:
        logger.warning("webhook_signature_invalid", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("webhook_processing_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook",
        )
