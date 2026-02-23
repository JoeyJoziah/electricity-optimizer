"""
Tests for the Billing API (backend/api/v1/billing.py)

Tests cover:
- POST /billing/checkout - create Stripe checkout session
- POST /billing/portal - create customer portal session
- GET /billing/subscription - get subscription status
- POST /billing/webhook - handle Stripe webhooks
- Unauthenticated access (401)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_db_session, TokenData


TEST_USER = TokenData(user_id="user-billing-1", email="billing@test.com")

BASE_URL = "/api/v1/billing"

ALLOWED_SUCCESS_URL = "https://electricity-optimizer.vercel.app/success"
ALLOWED_CANCEL_URL = "https://electricity-optimizer.vercel.app/cancel"
LOCALHOST_SUCCESS_URL = "http://localhost:3000/success"
LOCALHOST_CANCEL_URL = "http://localhost:3000/cancel"
DISALLOWED_URL = "https://evil-site.com/steal"


# =============================================================================
# Fixtures
# =============================================================================


def _make_mock_user(stripe_customer_id=None):
    """Create a mock User object with optional stripe_customer_id."""
    user = MagicMock()
    user.email = TEST_USER.email
    user.stripe_customer_id = stripe_customer_id
    user.subscription_tier = "free"
    user.model_dump.return_value = {
        "email": TEST_USER.email,
        "stripe_customer_id": stripe_customer_id,
        "subscription_tier": "free",
    }
    return user


def _make_mock_user_repo(user=None):
    """Create a mock UserRepository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=user)
    repo.update = AsyncMock(return_value=user)
    return repo


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def auth_client(mock_db):
    """TestClient with authenticated user and mocked DB session."""
    from main import app

    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_db_session] = lambda: mock_db

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauth_client():
    """TestClient without authentication (no dependency overrides)."""
    from main import app

    app.dependency_overrides.pop(get_current_user, None)
    # Still override DB to avoid real connection attempts
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_db_session, None)


# =============================================================================
# POST /billing/checkout
# =============================================================================


class TestCheckoutSession:
    """Tests for the POST /api/v1/billing/checkout endpoint."""

    def test_checkout_happy_path(self, auth_client):
        """Valid checkout request should return session_id and checkout_url."""
        mock_user = _make_mock_user(stripe_customer_id="cus_existing123")

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(mock_user)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.create_checkout_session = AsyncMock(
                return_value={
                    "id": "cs_test_abc123",
                    "url": "https://checkout.stripe.com/pay/cs_test_abc123",
                }
            )

            response = auth_client.post(
                f"{BASE_URL}/checkout",
                json={
                    "tier": "pro",
                    "success_url": ALLOWED_SUCCESS_URL,
                    "cancel_url": ALLOWED_CANCEL_URL,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "cs_test_abc123"
        assert data["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_abc123"

    def test_checkout_business_tier(self, auth_client):
        """Checkout with 'business' tier should also succeed."""
        mock_user = _make_mock_user()

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(mock_user)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.create_checkout_session = AsyncMock(
                return_value={
                    "id": "cs_test_biz456",
                    "url": "https://checkout.stripe.com/pay/cs_test_biz456",
                }
            )

            response = auth_client.post(
                f"{BASE_URL}/checkout",
                json={
                    "tier": "business",
                    "success_url": ALLOWED_SUCCESS_URL,
                    "cancel_url": ALLOWED_CANCEL_URL,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "cs_test_biz456"

    def test_checkout_localhost_urls_allowed(self, auth_client):
        """Localhost redirect URLs should be accepted for development."""
        mock_user = _make_mock_user()

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(mock_user)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.create_checkout_session = AsyncMock(
                return_value={"id": "cs_local", "url": "https://checkout.stripe.com/pay/cs_local"}
            )

            response = auth_client.post(
                f"{BASE_URL}/checkout",
                json={
                    "tier": "pro",
                    "success_url": LOCALHOST_SUCCESS_URL,
                    "cancel_url": LOCALHOST_CANCEL_URL,
                },
            )

        assert response.status_code == 200

    def test_checkout_stripe_not_configured(self, auth_client):
        """When Stripe is not configured, should return 503."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = False

            response = auth_client.post(
                f"{BASE_URL}/checkout",
                json={
                    "tier": "pro",
                    "success_url": ALLOWED_SUCCESS_URL,
                    "cancel_url": ALLOWED_CANCEL_URL,
                },
            )

        assert response.status_code == 503
        assert "not configured" in response.json()["detail"].lower()

    def test_checkout_invalid_tier(self, auth_client):
        """Invalid tier value should return 422 (Pydantic validation)."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True

            response = auth_client.post(
                f"{BASE_URL}/checkout",
                json={
                    "tier": "enterprise",
                    "success_url": ALLOWED_SUCCESS_URL,
                    "cancel_url": ALLOWED_CANCEL_URL,
                },
            )

        assert response.status_code == 422

    def test_checkout_free_tier_rejected(self, auth_client):
        """Tier 'free' should be rejected by the pattern validator (422)."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True

            response = auth_client.post(
                f"{BASE_URL}/checkout",
                json={
                    "tier": "free",
                    "success_url": ALLOWED_SUCCESS_URL,
                    "cancel_url": ALLOWED_CANCEL_URL,
                },
            )

        assert response.status_code == 422

    def test_checkout_disallowed_redirect_domain(self, auth_client):
        """Redirect URL from a disallowed domain should return 422."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True

            response = auth_client.post(
                f"{BASE_URL}/checkout",
                json={
                    "tier": "pro",
                    "success_url": DISALLOWED_URL,
                    "cancel_url": ALLOWED_CANCEL_URL,
                },
            )

        assert response.status_code == 422

    def test_checkout_disallowed_cancel_url_domain(self, auth_client):
        """Cancel URL from a disallowed domain should also return 422."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True

            response = auth_client.post(
                f"{BASE_URL}/checkout",
                json={
                    "tier": "pro",
                    "success_url": ALLOWED_SUCCESS_URL,
                    "cancel_url": DISALLOWED_URL,
                },
            )

        assert response.status_code == 422

    def test_checkout_missing_fields(self, auth_client):
        """Missing required fields should return 422."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True

            response = auth_client.post(
                f"{BASE_URL}/checkout",
                json={"tier": "pro"},
            )

        assert response.status_code == 422

    def test_checkout_stripe_value_error(self, auth_client):
        """ValueError from StripeService should return 400."""
        mock_user = _make_mock_user()

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(mock_user)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.create_checkout_session = AsyncMock(
                side_effect=ValueError("Price ID for tier 'pro' not configured.")
            )

            response = auth_client.post(
                f"{BASE_URL}/checkout",
                json={
                    "tier": "pro",
                    "success_url": ALLOWED_SUCCESS_URL,
                    "cancel_url": ALLOWED_CANCEL_URL,
                },
            )

        assert response.status_code == 400
        assert "not configured" in response.json()["detail"].lower()


# =============================================================================
# POST /billing/portal
# =============================================================================


class TestPortalSession:
    """Tests for the POST /api/v1/billing/portal endpoint."""

    def test_portal_happy_path(self, auth_client):
        """Valid portal request for a user with stripe_customer_id should succeed."""
        mock_user = _make_mock_user(stripe_customer_id="cus_portal789")

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(mock_user)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.create_customer_portal_session = AsyncMock(
                return_value={"url": "https://billing.stripe.com/session/bps_test"}
            )

            response = auth_client.post(
                f"{BASE_URL}/portal",
                json={"return_url": ALLOWED_SUCCESS_URL},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["portal_url"] == "https://billing.stripe.com/session/bps_test"

    def test_portal_no_customer_id(self, auth_client):
        """User without stripe_customer_id should get 400."""
        mock_user = _make_mock_user(stripe_customer_id=None)

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(mock_user)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True

            response = auth_client.post(
                f"{BASE_URL}/portal",
                json={"return_url": ALLOWED_SUCCESS_URL},
            )

        assert response.status_code == 400
        assert "no active subscription" in response.json()["detail"].lower()

    def test_portal_user_not_found(self, auth_client):
        """When user does not exist in DB, customer_id is None -> 400."""
        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(user=None)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True

            response = auth_client.post(
                f"{BASE_URL}/portal",
                json={"return_url": ALLOWED_SUCCESS_URL},
            )

        assert response.status_code == 400

    def test_portal_stripe_not_configured(self, auth_client):
        """When Stripe is not configured, should return 503."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = False

            response = auth_client.post(
                f"{BASE_URL}/portal",
                json={"return_url": ALLOWED_SUCCESS_URL},
            )

        assert response.status_code == 503
        assert "not configured" in response.json()["detail"].lower()

    def test_portal_missing_return_url(self, auth_client):
        """Missing return_url should return 422."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True

            response = auth_client.post(f"{BASE_URL}/portal", json={})

        assert response.status_code == 422


# =============================================================================
# GET /billing/subscription
# =============================================================================


class TestSubscriptionStatus:
    """Tests for the GET /api/v1/billing/subscription endpoint."""

    def test_subscription_free_tier_no_customer(self, auth_client):
        """User without stripe_customer_id should be reported as free tier."""
        mock_user = _make_mock_user(stripe_customer_id=None)

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(mock_user)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True

            response = auth_client.get(f"{BASE_URL}/subscription")

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "free"
        assert data["status"] == "active"
        assert data["has_active_subscription"] is False
        assert data["current_period_end"] is None
        assert data["cancel_at_period_end"] is None

    def test_subscription_free_tier_user_not_found(self, auth_client):
        """User not found in DB should also be reported as free tier."""
        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(user=None)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True

            response = auth_client.get(f"{BASE_URL}/subscription")

        assert response.status_code == 200
        assert response.json()["tier"] == "free"

    def test_subscription_active_pro(self, auth_client):
        """Active pro subscription should return correct status."""
        mock_user = _make_mock_user(stripe_customer_id="cus_sub123")
        period_end = datetime(2026, 3, 15, 0, 0, 0, tzinfo=timezone.utc)

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(mock_user)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.get_subscription_status = AsyncMock(
                return_value={
                    "tier": "pro",
                    "status": "active",
                    "current_period_end": period_end,
                    "cancel_at_period_end": False,
                }
            )

            response = auth_client.get(f"{BASE_URL}/subscription")

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "pro"
        assert data["status"] == "active"
        assert data["has_active_subscription"] is True
        assert data["cancel_at_period_end"] is False
        assert data["current_period_end"] is not None

    def test_subscription_trialing_is_active(self, auth_client):
        """Trialing subscription should report has_active_subscription=True."""
        mock_user = _make_mock_user(stripe_customer_id="cus_trial")
        period_end = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(mock_user)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.get_subscription_status = AsyncMock(
                return_value={
                    "tier": "business",
                    "status": "trialing",
                    "current_period_end": period_end,
                    "cancel_at_period_end": False,
                }
            )

            response = auth_client.get(f"{BASE_URL}/subscription")

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "business"
        assert data["has_active_subscription"] is True

    def test_subscription_past_due_not_active(self, auth_client):
        """Past-due subscription should have has_active_subscription=False."""
        mock_user = _make_mock_user(stripe_customer_id="cus_pastdue")
        period_end = datetime(2026, 2, 20, 0, 0, 0, tzinfo=timezone.utc)

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(mock_user)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.get_subscription_status = AsyncMock(
                return_value={
                    "tier": "pro",
                    "status": "past_due",
                    "current_period_end": period_end,
                    "cancel_at_period_end": False,
                }
            )

            response = auth_client.get(f"{BASE_URL}/subscription")

        assert response.status_code == 200
        data = response.json()
        assert data["has_active_subscription"] is False

    def test_subscription_no_stripe_subscription(self, auth_client):
        """Customer exists but no subscription returns free tier."""
        mock_user = _make_mock_user(stripe_customer_id="cus_nosub")

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            MockRepo.return_value = _make_mock_user_repo(mock_user)

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.get_subscription_status = AsyncMock(return_value=None)

            response = auth_client.get(f"{BASE_URL}/subscription")

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "free"
        assert data["has_active_subscription"] is False

    def test_subscription_stripe_not_configured(self, auth_client):
        """When Stripe is not configured, should return 503."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = False

            response = auth_client.get(f"{BASE_URL}/subscription")

        assert response.status_code == 503
        assert "not configured" in response.json()["detail"].lower()


# =============================================================================
# POST /billing/webhook
# =============================================================================


class TestWebhook:
    """Tests for the POST /api/v1/billing/webhook endpoint."""

    def test_webhook_valid_event(self, auth_client):
        """Valid webhook with correct signature should return received=True."""
        mock_event = {
            "id": "evt_test_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"user_id": "user-billing-1", "tier": "pro"},
                    "customer": "cus_wh_123",
                },
            },
        }
        mock_user = _make_mock_user(stripe_customer_id="cus_wh_123")

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            repo_instance = _make_mock_user_repo(mock_user)
            MockRepo.return_value = repo_instance

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.verify_webhook_signature = MagicMock(return_value=mock_event)
            stripe_instance.handle_webhook_event = AsyncMock(
                return_value={
                    "handled": True,
                    "action": "activate_subscription",
                    "user_id": "user-billing-1",
                    "tier": "pro",
                    "customer_id": "cus_wh_123",
                }
            )

            response = auth_client.post(
                f"{BASE_URL}/webhook",
                content=b'{"type": "checkout.session.completed"}',
                headers={"stripe-signature": "t=123,v1=sig_valid"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True
        assert data["event_id"] == "evt_test_123"

    def test_webhook_unhandled_event(self, auth_client):
        """Unhandled event type should still return 200 with received=True."""
        mock_event = {
            "id": "evt_ignored_456",
            "type": "payment_method.attached",
            "data": {"object": {}},
        }

        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.verify_webhook_signature = MagicMock(return_value=mock_event)
            stripe_instance.handle_webhook_event = AsyncMock(
                return_value={
                    "handled": False,
                    "action": None,
                    "user_id": None,
                    "tier": None,
                    "customer_id": None,
                }
            )

            response = auth_client.post(
                f"{BASE_URL}/webhook",
                content=b'{"type": "payment_method.attached"}',
                headers={"stripe-signature": "t=123,v1=sig_valid"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True
        assert data["event_id"] == "evt_ignored_456"

    def test_webhook_missing_signature(self, auth_client):
        """Request without stripe-signature header should return 400."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True

            response = auth_client.post(
                f"{BASE_URL}/webhook",
                content=b'{"type": "checkout.session.completed"}',
            )

        assert response.status_code == 400
        assert "stripe-signature" in response.json()["detail"].lower()

    def test_webhook_invalid_signature(self, auth_client):
        """Invalid webhook signature should return 400."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.verify_webhook_signature = MagicMock(
                side_effect=ValueError("Invalid webhook signature")
            )

            response = auth_client.post(
                f"{BASE_URL}/webhook",
                content=b'{"type": "checkout.session.completed"}',
                headers={"stripe-signature": "t=123,v1=bad_sig"},
            )

        assert response.status_code == 400
        assert "invalid webhook signature" in response.json()["detail"].lower()

    def test_webhook_stripe_not_configured(self, auth_client):
        """When Stripe is not configured, webhook should return 503."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = False

            response = auth_client.post(
                f"{BASE_URL}/webhook",
                content=b'{"type": "checkout.session.completed"}',
                headers={"stripe-signature": "t=123,v1=sig"},
            )

        assert response.status_code == 503

    def test_webhook_activate_subscription_updates_user(self, auth_client):
        """Checkout completed webhook should update user subscription tier and customer_id."""
        mock_event = {
            "id": "evt_activate_789",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"user_id": "user-billing-1", "tier": "business"},
                    "customer": "cus_new_biz",
                },
            },
        }
        mock_user = _make_mock_user()

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            repo_instance = _make_mock_user_repo(mock_user)
            MockRepo.return_value = repo_instance

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.verify_webhook_signature = MagicMock(return_value=mock_event)
            stripe_instance.handle_webhook_event = AsyncMock(
                return_value={
                    "handled": True,
                    "action": "activate_subscription",
                    "user_id": "user-billing-1",
                    "tier": "business",
                    "customer_id": "cus_new_biz",
                }
            )

            response = auth_client.post(
                f"{BASE_URL}/webhook",
                content=b'{}',
                headers={"stripe-signature": "t=123,v1=sig_valid"},
            )

        assert response.status_code == 200
        # Verify user fields were set
        assert mock_user.subscription_tier == "business"
        assert mock_user.stripe_customer_id == "cus_new_biz"
        repo_instance.update.assert_awaited_once_with("user-billing-1", mock_user)

    def test_webhook_deactivate_subscription_resets_to_free(self, auth_client):
        """Subscription deleted webhook should reset user to free tier."""
        mock_event = {
            "id": "evt_deactivate_111",
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "metadata": {"user_id": "user-billing-1"},
                    "customer": "cus_del",
                },
            },
        }
        mock_user = _make_mock_user(stripe_customer_id="cus_del")
        mock_user.subscription_tier = "pro"

        with patch(
            "api.v1.billing.UserRepository"
        ) as MockRepo, patch(
            "api.v1.billing.StripeService"
        ) as MockStripe:
            repo_instance = _make_mock_user_repo(mock_user)
            MockRepo.return_value = repo_instance

            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.verify_webhook_signature = MagicMock(return_value=mock_event)
            stripe_instance.handle_webhook_event = AsyncMock(
                return_value={
                    "handled": True,
                    "action": "deactivate_subscription",
                    "user_id": "user-billing-1",
                    "tier": "free",
                    "customer_id": "cus_del",
                }
            )

            response = auth_client.post(
                f"{BASE_URL}/webhook",
                content=b'{}',
                headers={"stripe-signature": "t=123,v1=sig_valid"},
            )

        assert response.status_code == 200
        assert mock_user.subscription_tier == "free"
        repo_instance.update.assert_awaited_once()


# =============================================================================
# Unauthenticated Access (401)
# =============================================================================


class TestUnauthenticatedAccess:
    """Endpoints requiring auth should return 401 without credentials."""

    def test_checkout_requires_auth(self, unauth_client):
        """POST /checkout without auth should return 401."""
        response = unauth_client.post(
            f"{BASE_URL}/checkout",
            json={
                "tier": "pro",
                "success_url": ALLOWED_SUCCESS_URL,
                "cancel_url": ALLOWED_CANCEL_URL,
            },
        )
        assert response.status_code == 401

    def test_portal_requires_auth(self, unauth_client):
        """POST /portal without auth should return 401."""
        response = unauth_client.post(
            f"{BASE_URL}/portal",
            json={"return_url": ALLOWED_SUCCESS_URL},
        )
        assert response.status_code == 401

    def test_subscription_requires_auth(self, unauth_client):
        """GET /subscription without auth should return 401."""
        response = unauth_client.get(f"{BASE_URL}/subscription")
        assert response.status_code == 401

    def test_webhook_does_not_require_auth(self, unauth_client):
        """POST /webhook should NOT require auth (uses signature verification instead)."""
        with patch("api.v1.billing.StripeService") as MockStripe:
            stripe_instance = MockStripe.return_value
            stripe_instance.is_configured = True
            stripe_instance.verify_webhook_signature = MagicMock(
                return_value={
                    "id": "evt_noauth",
                    "type": "ping",
                    "data": {"object": {}},
                }
            )
            stripe_instance.handle_webhook_event = AsyncMock(
                return_value={
                    "handled": False,
                    "action": None,
                    "user_id": None,
                    "tier": None,
                    "customer_id": None,
                }
            )

            response = unauth_client.post(
                f"{BASE_URL}/webhook",
                content=b'{}',
                headers={"stripe-signature": "t=123,v1=sig"},
            )

        # Webhook should succeed without auth - it uses stripe-signature instead
        assert response.status_code == 200
