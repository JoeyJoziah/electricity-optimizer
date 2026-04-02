"""
Tests for UtilityAPI Billing Service

Tests the $2.25/meter/month add-on billing for UtilityAPI direct connections.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import stripe

from config.settings import settings
from services.utilityapi_billing_service import (
    PRICE_PER_METER_USD,
    UtilityAPIBillingService,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Create a mock async DB session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def billing_service(mock_db):
    """Create a UtilityAPIBillingService with mocked DB."""
    return UtilityAPIBillingService(mock_db)


@pytest.fixture
def mock_price_configured():
    """Patch the Stripe price setting."""
    with patch.object(settings, "stripe_price_utilityapi_meter", "price_utilityapi_test"):
        yield


def _make_mapping_result(rows: list[dict]):
    """Helper to build a mock SQLAlchemy result with mappings."""
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.all.return_value = rows
    mock_mappings.first.return_value = rows[0] if rows else None
    mock_result.mappings.return_value = mock_mappings
    return mock_result


# =============================================================================
# Constants
# =============================================================================


class TestConstants:
    def test_price_per_meter(self):
        assert PRICE_PER_METER_USD == 2.25


# =============================================================================
# get_addon_pricing
# =============================================================================


class TestGetAddonPricing:
    @pytest.mark.asyncio
    async def test_returns_pricing_with_zero_meters(self, billing_service, mock_db):
        """User with no meters gets correct pricing info."""
        mock_db.execute.return_value = _make_mapping_result([{"total": 0}])

        result = await billing_service.get_addon_pricing("user_123")

        assert result == {
            "price_per_meter": 2.25,
            "current_meters": 0,
            "monthly_total": 0.0,
            "currency": "usd",
        }

    @pytest.mark.asyncio
    async def test_returns_pricing_with_active_meters(self, billing_service, mock_db):
        """User with 3 active meters gets correct total."""
        mock_db.execute.return_value = _make_mapping_result([{"total": 3}])

        result = await billing_service.get_addon_pricing("user_123")

        assert result["current_meters"] == 3
        assert result["monthly_total"] == 6.75

    @pytest.mark.asyncio
    async def test_returns_pricing_with_null_total(self, billing_service, mock_db):
        """Handles NULL result from COALESCE (empty result set)."""
        mock_db.execute.return_value = _make_mapping_result([])

        result = await billing_service.get_addon_pricing("user_123")

        assert result["current_meters"] == 0
        assert result["monthly_total"] == 0.0


# =============================================================================
# add_meters — validation
# =============================================================================


class TestAddMetersValidation:
    @pytest.mark.asyncio
    async def test_rejects_zero_meter_count(self, billing_service, mock_price_configured):
        """Meter count must be at least 1."""
        with pytest.raises(ValueError, match="meter_count must be at least 1"):
            await billing_service.add_meters("user_123", "conn_abc", 0)

    @pytest.mark.asyncio
    async def test_rejects_negative_meter_count(self, billing_service, mock_price_configured):
        with pytest.raises(ValueError, match="meter_count must be at least 1"):
            await billing_service.add_meters("user_123", "conn_abc", -1)

    @pytest.mark.asyncio
    async def test_rejects_when_price_not_configured(self, billing_service):
        """Raises if STRIPE_PRICE_UTILITYAPI_METER is not set."""
        with patch.object(settings, "stripe_price_utilityapi_meter", None):
            with pytest.raises(ValueError, match="STRIPE_PRICE_UTILITYAPI_METER"):
                await billing_service.add_meters("user_123", "conn_abc", 1)

    @pytest.mark.asyncio
    async def test_rejects_when_user_not_found(
        self, billing_service, mock_db, mock_price_configured
    ):
        """Raises if user does not exist."""
        mock_db.execute.side_effect = [
            _make_mapping_result([]),  # user lookup returns empty
        ]

        with pytest.raises(ValueError, match="User user_123 not found"):
            await billing_service.add_meters("user_123", "conn_abc", 1)


# =============================================================================
# add_meters — Pro/Business user (existing subscription)
# =============================================================================


class TestAddMetersExistingSubscription:
    @pytest.mark.asyncio
    async def test_adds_new_item_to_subscription(
        self, billing_service, mock_db, mock_price_configured
    ):
        """Pro user without existing addon item gets a new subscription item."""
        # 1. User lookup
        mock_db.execute.side_effect = [
            _make_mapping_result([{"stripe_customer_id": "cus_pro", "subscription_tier": "pro"}]),
            # 2. _get_total_meters (existing meters for other connections)
            _make_mapping_result([{"total": 0}]),
            # 3. Store billing on connection (UPDATE)
            MagicMock(),
        ]

        mock_sub = Mock(id="sub_123")
        mock_sub_list = Mock(data=[mock_sub])
        modified_sub = {
            "items": {
                "data": [
                    {"id": "si_new", "price": {"id": "price_utilityapi_test"}},
                ]
            }
        }

        with (
            patch("services.utilityapi_billing_service.asyncio.to_thread") as mock_thread,
            patch("api.dependencies.invalidate_tier_cache", new_callable=AsyncMock),
        ):
            # _find_addon_subscription_item returns None (no existing item)
            mock_thread.side_effect = [
                Mock(data=[]),  # Subscription.list in _find_addon_subscription_item
                mock_sub_list,  # Subscription.list for adding new item
                modified_sub,  # Subscription.modify
            ]

            result = await billing_service.add_meters("user_pro", "conn_1", 2)

        assert result["subscription_item_id"] == "si_new"
        assert result["checkout_url"] is None

    @pytest.mark.asyncio
    async def test_updates_existing_item_quantity(
        self, billing_service, mock_db, mock_price_configured
    ):
        """Pro user with existing addon item gets quantity updated."""
        mock_db.execute.side_effect = [
            _make_mapping_result([{"stripe_customer_id": "cus_pro", "subscription_tier": "pro"}]),
            _make_mapping_result([{"total": 2}]),  # existing 2 meters
            MagicMock(),  # UPDATE statement
        ]

        existing_sub = Mock()
        existing_sub.__getitem__ = lambda self, key: {
            "items": {"data": [{"id": "si_existing", "price": {"id": "price_utilityapi_test"}}]}
        }[key]

        with (
            patch("services.utilityapi_billing_service.asyncio.to_thread") as mock_thread,
            patch("api.dependencies.invalidate_tier_cache", new_callable=AsyncMock),
        ):
            # _find_addon_subscription_item finds existing item
            mock_thread.side_effect = [
                Mock(data=[existing_sub]),  # Subscription.list finds addon
                None,  # SubscriptionItem.modify
            ]

            result = await billing_service.add_meters("user_pro", "conn_2", 3)

        assert result["subscription_item_id"] == "si_existing"
        assert result["checkout_url"] is None
        # Verify modify was called with total = 2 existing + 3 new = 5
        modify_call = mock_thread.call_args_list[1]
        assert modify_call.args == (stripe.SubscriptionItem.modify, "si_existing")
        assert modify_call.kwargs == {"quantity": 5}


# =============================================================================
# add_meters — Free user (checkout session)
# =============================================================================


class TestAddMetersFreeUser:
    @pytest.mark.asyncio
    async def test_creates_checkout_session(self, billing_service, mock_db, mock_price_configured):
        """Free user gets a Stripe Checkout URL instead of direct billing."""
        mock_db.execute.side_effect = [
            _make_mapping_result([{"stripe_customer_id": None, "subscription_tier": "free"}]),
            _make_mapping_result([{"total": 0}]),  # existing meters
            MagicMock(),  # UPDATE meter count
            _make_mapping_result([{"email": "test@example.com"}]),  # email lookup
        ]

        mock_session = Mock(id="cs_test_addon", url="https://checkout.stripe.com/addon")

        with patch("services.utilityapi_billing_service.asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_session

            result = await billing_service.add_meters("user_free", "conn_3", 1)

        assert result["subscription_item_id"] is None
        assert result["checkout_url"] == "https://checkout.stripe.com/addon"

        # Verify checkout session metadata includes addon_type
        call_kwargs = mock_thread.call_args.kwargs
        assert call_kwargs["metadata"]["addon_type"] == "utilityapi_meter"
        assert call_kwargs["metadata"]["connection_id"] == "conn_3"

    @pytest.mark.asyncio
    async def test_uses_customer_id_if_exists(
        self, billing_service, mock_db, mock_price_configured
    ):
        """Free user with a Stripe customer ID reuses it."""
        mock_db.execute.side_effect = [
            _make_mapping_result([{"stripe_customer_id": "cus_free", "subscription_tier": "free"}]),
            _make_mapping_result([{"total": 0}]),
            MagicMock(),
            _make_mapping_result([{"email": "test@example.com"}]),
        ]

        mock_session = Mock(id="cs_test", url="https://checkout.stripe.com/test")

        with patch("services.utilityapi_billing_service.asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_session

            await billing_service.add_meters("user_free", "conn_4", 1)

        call_kwargs = mock_thread.call_args.kwargs
        assert call_kwargs["customer"] == "cus_free"


# =============================================================================
# remove_meters
# =============================================================================


class TestRemoveMeters:
    @pytest.mark.asyncio
    async def test_no_op_when_no_billing(self, billing_service, mock_db):
        """Does nothing if connection has no subscription item."""
        mock_db.execute.return_value = _make_mapping_result(
            [{"stripe_subscription_item_id": None, "utilityapi_meter_count": 0}]
        )

        await billing_service.remove_meters("user_123", "conn_abc")

        # No Stripe calls should be made
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_deletes_item_when_no_other_meters(self, billing_service, mock_db):
        """Deletes the subscription item when this is the only connection with meters."""
        mock_db.execute.side_effect = [
            _make_mapping_result(
                [{"stripe_subscription_item_id": "si_del", "utilityapi_meter_count": 2}]
            ),
            _make_mapping_result([{"total": 0}]),  # no other meters
            MagicMock(),  # UPDATE to clear billing
        ]

        with patch("services.utilityapi_billing_service.asyncio.to_thread") as mock_thread:
            await billing_service.remove_meters("user_123", "conn_del")

        mock_thread.assert_called_once()
        call_args = mock_thread.call_args.args
        assert call_args[0].__name__ == "delete"
        assert call_args[1] == "si_del"
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_reduces_quantity_when_other_meters_exist(self, billing_service, mock_db):
        """Reduces quantity when other connections still have meters."""
        mock_db.execute.side_effect = [
            _make_mapping_result(
                [{"stripe_subscription_item_id": "si_reduce", "utilityapi_meter_count": 2}]
            ),
            _make_mapping_result([{"total": 3}]),  # 3 meters from other connections
            MagicMock(),  # UPDATE to clear billing
        ]

        with patch("services.utilityapi_billing_service.asyncio.to_thread") as mock_thread:
            await billing_service.remove_meters("user_123", "conn_reduce")

        mock_thread.assert_called_once()
        call_args = mock_thread.call_args.args
        assert call_args[0].__name__ == "modify"
        assert call_args[1] == "si_reduce"
        assert mock_thread.call_args.kwargs == {"quantity": 3}

    @pytest.mark.asyncio
    async def test_raises_on_stripe_error(self, billing_service, mock_db):
        """Re-raises StripeError from Stripe API."""
        mock_db.execute.side_effect = [
            _make_mapping_result(
                [{"stripe_subscription_item_id": "si_err", "utilityapi_meter_count": 1}]
            ),
            _make_mapping_result([{"total": 0}]),
        ]

        with patch("services.utilityapi_billing_service.asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = stripe.StripeError("API error")

            with pytest.raises(stripe.StripeError):
                await billing_service.remove_meters("user_123", "conn_err")


# =============================================================================
# finalize_checkout
# =============================================================================


class TestFinalizeCheckout:
    @pytest.mark.asyncio
    async def test_links_subscription_item_to_connection(
        self, billing_service, mock_db, mock_price_configured
    ):
        """Successfully links the SI after checkout completion."""
        mock_db.execute.side_effect = [
            _make_mapping_result([{"user_id": "user_123", "utilityapi_meter_count": 1}]),
            _make_mapping_result([{"stripe_customer_id": "cus_123"}]),
            MagicMock(),  # UPDATE
        ]

        mock_sub = Mock()
        mock_sub.__getitem__ = lambda self, key: {
            "items": {"data": [{"id": "si_final", "price": {"id": "price_utilityapi_test"}}]}
        }[key]

        with patch("services.utilityapi_billing_service.asyncio.to_thread") as mock_thread:
            mock_thread.return_value = Mock(data=[mock_sub])

            await billing_service.finalize_checkout("conn_final")

        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_no_op_when_connection_not_found(self, billing_service, mock_db):
        """Does nothing if connection doesn't exist."""
        mock_db.execute.return_value = _make_mapping_result([])

        await billing_service.finalize_checkout("conn_missing")

        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_op_when_no_customer_id(self, billing_service, mock_db, mock_price_configured):
        """Does nothing if user has no Stripe customer ID."""
        mock_db.execute.side_effect = [
            _make_mapping_result([{"user_id": "user_nocust", "utilityapi_meter_count": 1}]),
            _make_mapping_result([{"stripe_customer_id": None}]),
        ]

        await billing_service.finalize_checkout("conn_nocust")

        mock_db.commit.assert_not_called()


# =============================================================================
# _get_total_meters
# =============================================================================


class TestGetTotalMeters:
    @pytest.mark.asyncio
    async def test_returns_sum(self, billing_service, mock_db):
        mock_db.execute.return_value = _make_mapping_result([{"total": 5}])

        result = await billing_service._get_total_meters("user_123")

        assert result == 5

    @pytest.mark.asyncio
    async def test_excludes_connection(self, billing_service, mock_db):
        mock_db.execute.return_value = _make_mapping_result([{"total": 3}])

        result = await billing_service._get_total_meters("user_123", exclude_connection_id="conn_x")

        assert result == 3
        # Verify the exclude_id parameter was passed
        call_params = mock_db.execute.call_args[0][1]
        assert call_params["exclude_id"] == "conn_x"

    @pytest.mark.asyncio
    async def test_returns_zero_on_empty_result(self, billing_service, mock_db):
        mock_db.execute.return_value = _make_mapping_result([])

        result = await billing_service._get_total_meters("user_123")

        assert result == 0
