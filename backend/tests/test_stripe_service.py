"""
Tests for Stripe Service

Tests subscription management with mocked Stripe calls.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock
import pytest
import stripe

from services.stripe_service import StripeService
from config.settings import settings


@pytest.fixture
def mock_stripe_configured():
    """Mock Stripe configuration."""
    with patch.object(settings, "stripe_secret_key", "sk_test_mock"):
        with patch.object(settings, "stripe_webhook_secret", "whsec_test_mock"):
            with patch.object(settings, "stripe_price_pro", "price_pro_test"):
                with patch.object(settings, "stripe_price_business", "price_business_test"):
                    yield


@pytest.fixture
def stripe_service(mock_stripe_configured):
    """Create StripeService instance with mocked config."""
    return StripeService()


@pytest.fixture
def mock_checkout_session():
    """Mock Stripe checkout session."""
    return Mock(
        id="cs_test_123",
        url="https://checkout.stripe.com/pay/cs_test_123",
        customer="cus_test_456",
    )


@pytest.fixture
def mock_portal_session():
    """Mock Stripe portal session."""
    return Mock(
        id="bps_test_789",
        url="https://billing.stripe.com/p/session/bps_test_789",
    )


@pytest.fixture
def mock_subscription():
    """Mock Stripe subscription."""
    return Mock(
        id="sub_test_abc",
        status="active",
        current_period_end=int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        cancel_at_period_end=False,
        metadata={"user_id": "user_123", "tier": "pro"},
        canceled_at=None,
    )


# =============================================================================
# Service Initialization Tests
# =============================================================================


def test_stripe_service_initialization_configured(mock_stripe_configured):
    """Test service initializes when Stripe is configured."""
    service = StripeService()
    assert service.is_configured is True


def test_stripe_service_initialization_not_configured():
    """Test service handles missing configuration gracefully."""
    with patch.object(settings, "stripe_secret_key", None):
        service = StripeService()
        assert service.is_configured is False


def test_stripe_service_ensure_configured_raises_when_not_configured():
    """Test _ensure_configured raises error when Stripe not configured."""
    with patch.object(settings, "stripe_secret_key", None):
        service = StripeService()
        with pytest.raises(ValueError, match="Stripe is not configured"):
            service._ensure_configured()


# =============================================================================
# Checkout Session Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_checkout_session_success(stripe_service, mock_checkout_session):
    """Test successful checkout session creation."""
    with patch("stripe.checkout.Session.create", return_value=mock_checkout_session):
        result = await stripe_service.create_checkout_session(
            user_id="user_123",
            email="user@example.com",
            tier="pro",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )

        assert result["id"] == "cs_test_123"
        assert result["url"] == "https://checkout.stripe.com/pay/cs_test_123"
        assert result["customer_id"] == "cus_test_456"


@pytest.mark.asyncio
async def test_create_checkout_session_with_existing_customer(
    stripe_service, mock_checkout_session
):
    """Test checkout session creation with existing customer."""
    with patch("stripe.checkout.Session.create", return_value=mock_checkout_session) as mock_create:
        await stripe_service.create_checkout_session(
            user_id="user_123",
            email="user@example.com",
            tier="pro",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            customer_id="cus_existing",
        )

        # Verify customer parameter was used
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["customer"] == "cus_existing"
        assert "customer_email" not in call_kwargs


@pytest.mark.asyncio
async def test_create_checkout_session_invalid_tier(stripe_service):
    """Test checkout session with invalid tier raises error."""
    with pytest.raises(ValueError, match="Invalid tier"):
        await stripe_service.create_checkout_session(
            user_id="user_123",
            email="user@example.com",
            tier="invalid",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )


@pytest.mark.asyncio
async def test_create_checkout_session_missing_price_id(stripe_service):
    """Test checkout session with missing price ID raises error."""
    with patch.object(settings, "stripe_price_pro", None):
        with pytest.raises(ValueError, match="Price ID for tier 'pro' not configured"):
            await stripe_service.create_checkout_session(
                user_id="user_123",
                email="user@example.com",
                tier="pro",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )


@pytest.mark.asyncio
async def test_create_checkout_session_stripe_error(stripe_service):
    """Test checkout session handles Stripe API errors."""
    with patch(
        "stripe.checkout.Session.create",
        side_effect=stripe.error.StripeError("API error"),
    ):
        with pytest.raises(stripe.error.StripeError):
            await stripe_service.create_checkout_session(
                user_id="user_123",
                email="user@example.com",
                tier="pro",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )


@pytest.mark.asyncio
async def test_create_checkout_session_not_configured():
    """Test checkout session fails when Stripe not configured."""
    with patch.object(settings, "stripe_secret_key", None):
        service = StripeService()
        with pytest.raises(ValueError, match="Stripe is not configured"):
            await service.create_checkout_session(
                user_id="user_123",
                email="user@example.com",
                tier="pro",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )


# =============================================================================
# Customer Portal Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_portal_session_success(stripe_service, mock_portal_session):
    """Test successful portal session creation."""
    with patch("stripe.billing_portal.Session.create", return_value=mock_portal_session):
        result = await stripe_service.create_customer_portal_session(
            customer_id="cus_test_456",
            return_url="https://example.com/account",
        )

        assert result["url"] == "https://billing.stripe.com/p/session/bps_test_789"


@pytest.mark.asyncio
async def test_create_portal_session_stripe_error(stripe_service):
    """Test portal session handles Stripe API errors."""
    with patch(
        "stripe.billing_portal.Session.create",
        side_effect=stripe.error.StripeError("API error"),
    ):
        with pytest.raises(stripe.error.StripeError):
            await stripe_service.create_customer_portal_session(
                customer_id="cus_test_456",
                return_url="https://example.com/account",
            )


# =============================================================================
# Subscription Status Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_subscription_status_active(stripe_service, mock_subscription):
    """Test getting active subscription status."""
    with patch("stripe.Subscription.list", return_value=Mock(data=[mock_subscription])):
        result = await stripe_service.get_subscription_status("cus_test_456")

        assert result["tier"] == "pro"
        assert result["status"] == "active"
        assert result["cancel_at_period_end"] is False
        assert isinstance(result["current_period_end"], datetime)


@pytest.mark.asyncio
async def test_get_subscription_status_no_subscription(stripe_service):
    """Test getting status when no subscription exists."""
    with patch("stripe.Subscription.list", return_value=Mock(data=[])):
        result = await stripe_service.get_subscription_status("cus_test_456")

        assert result is None


@pytest.mark.asyncio
async def test_get_subscription_status_stripe_error(stripe_service):
    """Test subscription status handles Stripe API errors."""
    with patch(
        "stripe.Subscription.list",
        side_effect=stripe.error.StripeError("API error"),
    ):
        with pytest.raises(stripe.error.StripeError):
            await stripe_service.get_subscription_status("cus_test_456")


# =============================================================================
# Subscription Cancellation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_cancel_subscription_at_period_end(stripe_service, mock_subscription):
    """Test canceling subscription at period end."""
    mock_subscription.cancel_at_period_end = True

    with patch("stripe.Subscription.modify", return_value=mock_subscription):
        result = await stripe_service.cancel_subscription(
            subscription_id="sub_test_abc",
            cancel_immediately=False,
        )

        assert result["status"] == "active"
        assert result["cancel_at_period_end"] is True


@pytest.mark.asyncio
async def test_cancel_subscription_immediately(stripe_service, mock_subscription):
    """Test canceling subscription immediately."""
    mock_subscription.status = "canceled"

    with patch("stripe.Subscription.cancel", return_value=mock_subscription):
        result = await stripe_service.cancel_subscription(
            subscription_id="sub_test_abc",
            cancel_immediately=True,
        )

        assert result["status"] == "canceled"


# =============================================================================
# Webhook Tests
# =============================================================================


def test_verify_webhook_signature_success(stripe_service):
    """Test successful webhook signature verification."""
    mock_event = Mock(spec=stripe.Event)
    mock_event.__getitem__ = Mock(return_value="test_event")

    with patch("stripe.Webhook.construct_event", return_value=mock_event):
        event = stripe_service.verify_webhook_signature(
            payload=b"test_payload",
            signature="test_signature",
        )

        assert event is not None


def test_verify_webhook_signature_invalid(stripe_service):
    """Test webhook signature verification with invalid signature."""
    with patch(
        "stripe.Webhook.construct_event",
        side_effect=stripe.error.SignatureVerificationError("Invalid signature", "sig"),
    ):
        with pytest.raises(ValueError, match="Invalid webhook signature"):
            stripe_service.verify_webhook_signature(
                payload=b"test_payload",
                signature="invalid_signature",
            )


def test_verify_webhook_signature_no_secret():
    """Test webhook verification fails without webhook secret."""
    with patch.object(settings, "stripe_webhook_secret", None):
        service = StripeService()
        with pytest.raises(ValueError, match="STRIPE_WEBHOOK_SECRET not configured"):
            service.verify_webhook_signature(
                payload=b"test_payload",
                signature="test_signature",
            )


@pytest.mark.asyncio
async def test_handle_webhook_checkout_completed(stripe_service):
    """Test handling checkout.session.completed webhook."""
    event = {
        "id": "evt_test_123",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {
                    "user_id": "user_123",
                    "tier": "pro",
                },
                "customer": "cus_test_456",
            }
        },
    }

    result = await stripe_service.handle_webhook_event(event)

    assert result["handled"] is True
    assert result["action"] == "activate_subscription"
    assert result["user_id"] == "user_123"
    assert result["tier"] == "pro"
    assert result["customer_id"] == "cus_test_456"


@pytest.mark.asyncio
async def test_handle_webhook_subscription_updated(stripe_service):
    """Test handling customer.subscription.updated webhook."""
    event = {
        "id": "evt_test_456",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "metadata": {
                    "user_id": "user_123",
                    "tier": "business",
                },
                "customer": "cus_test_456",
                "status": "active",
            }
        },
    }

    result = await stripe_service.handle_webhook_event(event)

    assert result["handled"] is True
    assert result["action"] == "update_subscription"
    assert result["user_id"] == "user_123"
    assert result["tier"] == "business"
    assert result["status"] == "active"


@pytest.mark.asyncio
async def test_handle_webhook_subscription_deleted(stripe_service):
    """Test handling customer.subscription.deleted webhook."""
    event = {
        "id": "evt_test_789",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "metadata": {
                    "user_id": "user_123",
                },
                "customer": "cus_test_456",
            }
        },
    }

    result = await stripe_service.handle_webhook_event(event)

    assert result["handled"] is True
    assert result["action"] == "deactivate_subscription"
    assert result["user_id"] == "user_123"
    assert result["tier"] == "free"


@pytest.mark.asyncio
async def test_handle_webhook_payment_failed(stripe_service):
    """Test handling invoice.payment_failed webhook."""
    event = {
        "id": "evt_test_abc",
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "customer": "cus_test_456",
                "subscription": "sub_test_123",
            }
        },
    }

    result = await stripe_service.handle_webhook_event(event)

    assert result["handled"] is True
    assert result["action"] == "payment_failed"
    assert result["customer_id"] == "cus_test_456"


@pytest.mark.asyncio
async def test_handle_webhook_unhandled_event(stripe_service):
    """Test handling unknown webhook event type."""
    event = {
        "id": "evt_test_xyz",
        "type": "unknown.event.type",
        "data": {
            "object": {}
        },
    }

    result = await stripe_service.handle_webhook_event(event)

    assert result["handled"] is False
    assert result["action"] is None


# =============================================================================
# Price ID Retrieval Tests
# =============================================================================


def test_get_price_id_for_tier_pro(stripe_service):
    """Test getting price ID for pro tier."""
    price_id = stripe_service._get_price_id_for_tier("pro")
    assert price_id == "price_pro_test"


def test_get_price_id_for_tier_business(stripe_service):
    """Test getting price ID for business tier."""
    price_id = stripe_service._get_price_id_for_tier("business")
    assert price_id == "price_business_test"


def test_get_price_id_for_tier_invalid(stripe_service):
    """Test getting price ID for invalid tier."""
    price_id = stripe_service._get_price_id_for_tier("invalid")
    assert price_id is None
