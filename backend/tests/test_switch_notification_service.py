"""
Tests for SwitchNotificationService (backend/services/switch_notification_service.py)

Coverage:
- send_switch_confirmation: sends email when user_email is provided
- send_switch_confirmation: sends push notification
- send_switch_confirmation: gracefully skips email when user_email is missing
- send_switch_confirmation: push failure does not block email success
- send_switch_recommendation: sends email with approve URL containing audit_log_id
- send_switch_recommendation: sends push with recommendation details
- send_switch_recommendation: falls back to base dashboard URL when no audit_log_id
- send_contract_expiring: sends email with correct days_remaining
- send_contract_expiring: sends push with free-switch-window message when flag is set
- send_contract_expiring: gracefully handles missing user_email
- email template renders with correct variables (switch_confirmation)
- email template renders with correct variables (switch_recommendation)
- email template renders with correct variables (contract_expiring)
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.switch_notification_service import (SwitchNotificationService,
                                                  _to_float, _to_float_or_none)

# =============================================================================
# Shared test data
# =============================================================================

TEST_USER_ID = str(uuid4())
TEST_EMAIL = "alice@example.com"
TEST_NAME = "Alice"

OLD_PLAN = {
    "plan_name": "Standard Rate",
    "provider": "Con Edison",
    "rate_kwh": Decimal("0.1250"),
    "fixed_charge": Decimal("12.00"),
}

NEW_PLAN = {
    "plan_name": "Green Saver 12",
    "provider": "NRG Energy",
    "rate_kwh": Decimal("0.0990"),
    "fixed_charge": Decimal("9.95"),
}

SAVINGS = {
    "monthly": Decimal("18.50"),
    "annual": Decimal("222.00"),
}

CURRENT_PLAN = {
    "plan_name": "Legacy Fixed",
    "provider": "PSEG",
    "rate_kwh": Decimal("0.1400"),
    "fixed_charge": Decimal("11.00"),
}

PROPOSED_PLAN = {
    "plan_name": "EcoRate Flex",
    "provider": "Ambit Energy",
    "rate_kwh": Decimal("0.1100"),
    "fixed_charge": Decimal("8.50"),
}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_email_service():
    svc = MagicMock()
    svc.render_template = MagicMock(return_value="<html>rendered</html>")
    svc.send = AsyncMock(return_value=True)
    return svc


@pytest.fixture
def mock_push_service():
    svc = AsyncMock()
    svc.is_configured = True
    svc.send_push = AsyncMock(return_value=True)
    return svc


@pytest.fixture
def notification_svc(mock_email_service, mock_push_service):
    return SwitchNotificationService(
        email_service=mock_email_service,
        push_service=mock_push_service,
    )


# =============================================================================
# TestSendSwitchConfirmation
# =============================================================================


class TestSendSwitchConfirmation:
    async def test_sends_email_when_address_provided(
        self, notification_svc, mock_email_service
    ):
        result = await notification_svc.send_switch_confirmation(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            old_plan=OLD_PLAN,
            new_plan=NEW_PLAN,
            savings=SAVINGS,
        )

        assert result["email"] is True
        mock_email_service.send.assert_awaited_once()
        call_kwargs = mock_email_service.send.call_args.kwargs
        assert call_kwargs["to"] == TEST_EMAIL
        assert "switched" in call_kwargs["subject"].lower()

    async def test_sends_push_notification(self, notification_svc, mock_push_service):
        result = await notification_svc.send_switch_confirmation(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            old_plan=OLD_PLAN,
            new_plan=NEW_PLAN,
            savings=SAVINGS,
        )

        assert result["push"] is True
        mock_push_service.send_push.assert_awaited_once()
        call_kwargs = mock_push_service.send_push.call_args.kwargs
        assert call_kwargs["user_id"] == TEST_USER_ID
        assert call_kwargs["data"]["type"] == "switch_confirmation"

    async def test_email_skipped_when_no_address(
        self, notification_svc, mock_email_service
    ):
        result = await notification_svc.send_switch_confirmation(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=None,
            old_plan=OLD_PLAN,
            new_plan=NEW_PLAN,
            savings=SAVINGS,
        )

        assert result["email"] is False
        mock_email_service.send.assert_not_awaited()

    async def test_push_failure_does_not_block_email(
        self, notification_svc, mock_push_service
    ):
        mock_push_service.send_push.side_effect = Exception("OneSignal timeout")

        result = await notification_svc.send_switch_confirmation(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            old_plan=OLD_PLAN,
            new_plan=NEW_PLAN,
            savings=SAVINGS,
        )

        # Email should still succeed even though push exploded
        assert result["email"] is True
        assert result["push"] is False

    async def test_includes_rescission_days_in_template(
        self, notification_svc, mock_email_service
    ):
        await notification_svc.send_switch_confirmation(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            old_plan=OLD_PLAN,
            new_plan=NEW_PLAN,
            savings=SAVINGS,
            rescission_days=10,
            rollback_url="https://rateshift.app/rollback/abc123",
        )

        call_kwargs = mock_email_service.render_template.call_args.kwargs
        assert call_kwargs["rescission_days"] == 10
        assert "rollback_url" in call_kwargs

    async def test_savings_monthly_in_push_data(
        self, notification_svc, mock_push_service
    ):
        await notification_svc.send_switch_confirmation(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            old_plan=OLD_PLAN,
            new_plan=NEW_PLAN,
            savings=SAVINGS,
        )

        push_data = mock_push_service.send_push.call_args.kwargs["data"]
        assert "savings_monthly" in push_data
        assert push_data["savings_monthly"] == "18.5"


# =============================================================================
# TestSendSwitchRecommendation
# =============================================================================


class TestSendSwitchRecommendation:
    async def test_approve_url_contains_audit_log_id(
        self, notification_svc, mock_email_service
    ):
        audit_id = str(uuid4())
        await notification_svc.send_switch_recommendation(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            current_plan=CURRENT_PLAN,
            proposed_plan=PROPOSED_PLAN,
            savings=SAVINGS,
            audit_log_id=audit_id,
        )

        call_kwargs = mock_email_service.render_template.call_args.kwargs
        assert audit_id in call_kwargs["approve_url"]

    async def test_approve_url_falls_back_when_no_audit_log_id(
        self, notification_svc, mock_email_service
    ):
        await notification_svc.send_switch_recommendation(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            current_plan=CURRENT_PLAN,
            proposed_plan=PROPOSED_PLAN,
            savings=SAVINGS,
            audit_log_id=None,
        )

        call_kwargs = mock_email_service.render_template.call_args.kwargs
        assert call_kwargs["approve_url"] == "https://rateshift.app/dashboard"

    async def test_sends_push_with_recommendation_type(
        self, notification_svc, mock_push_service
    ):
        result = await notification_svc.send_switch_recommendation(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            current_plan=CURRENT_PLAN,
            proposed_plan=PROPOSED_PLAN,
            savings=SAVINGS,
        )

        assert result["push"] is True
        push_data = mock_push_service.send_push.call_args.kwargs["data"]
        assert push_data["type"] == "switch_recommendation"

    async def test_email_skipped_when_no_address(
        self, notification_svc, mock_email_service
    ):
        result = await notification_svc.send_switch_recommendation(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=None,
            current_plan=CURRENT_PLAN,
            proposed_plan=PROPOSED_PLAN,
            savings=SAVINGS,
        )

        assert result["email"] is False
        mock_email_service.send.assert_not_awaited()


# =============================================================================
# TestSendContractExpiring
# =============================================================================


class TestSendContractExpiring:
    async def test_sends_email_with_correct_days_remaining(
        self, notification_svc, mock_email_service
    ):
        result = await notification_svc.send_contract_expiring(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            plan_name="Standard Rate",
            days_remaining=30,
        )

        assert result["email"] is True
        call_kwargs = mock_email_service.render_template.call_args.kwargs
        assert call_kwargs["days_remaining"] == 30
        assert "30" in mock_email_service.send.call_args.kwargs["subject"]

    async def test_free_switch_window_flag_passed_to_template(
        self, notification_svc, mock_email_service
    ):
        await notification_svc.send_contract_expiring(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            plan_name="Standard Rate",
            days_remaining=15,
            is_free_switch_window=True,
        )

        call_kwargs = mock_email_service.render_template.call_args.kwargs
        assert call_kwargs["is_free_switch_window"] is True

    async def test_free_switch_window_changes_push_message(
        self, notification_svc, mock_push_service
    ):
        await notification_svc.send_contract_expiring(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            plan_name="Fixed Rate",
            days_remaining=20,
            is_free_switch_window=True,
        )

        message = mock_push_service.send_push.call_args.kwargs["message"]
        assert "no cancellation fee" in message.lower()

    async def test_email_skipped_when_no_address(
        self, notification_svc, mock_email_service
    ):
        result = await notification_svc.send_contract_expiring(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=None,
            plan_name="Standard Rate",
            days_remaining=45,
        )

        assert result["email"] is False
        mock_email_service.send.assert_not_awaited()

    async def test_push_succeeds_even_when_email_fails(
        self, notification_svc, mock_email_service, mock_push_service
    ):
        mock_email_service.send.return_value = False

        result = await notification_svc.send_contract_expiring(
            user_id=TEST_USER_ID,
            user_name=TEST_NAME,
            user_email=TEST_EMAIL,
            plan_name="Standard Rate",
            days_remaining=30,
        )

        assert result["email"] is False
        assert result["push"] is True


# =============================================================================
# TestTemplateRendering
# =============================================================================


class TestTemplateRendering:
    """
    Verify that the Jinja2 templates render without exception when given
    representative context values.  These tests use the real EmailService
    render path (no mocking of render_template) to catch template-level errors.
    """

    def _real_email_svc(self):
        """Return an EmailService pointed at the real templates directory."""
        from services.email_service import EmailService

        return EmailService()

    def test_switch_confirmation_template_renders(self):
        svc = self._real_email_svc()
        html = svc.render_template(
            "switch_confirmation.html",
            user_name="Alice",
            old_plan_name="Standard Rate",
            old_provider="Con Edison",
            old_rate_kwh=0.1250,
            old_fixed_charge=12.00,
            new_plan_name="Green Saver 12",
            new_provider="NRG Energy",
            new_rate_kwh=0.0990,
            new_fixed_charge=9.95,
            savings_monthly=18.50,
            savings_annual=222.00,
            rescission_days=10,
            rollback_url="https://rateshift.app/rollback/abc",
        )
        assert "Green Saver 12" in html
        assert "18.50" in html
        assert "222" in html
        assert (
            "10-day" in html or "10 days" in html or "10</div>" in html or "10" in html
        )

    def test_switch_recommendation_template_renders(self):
        svc = self._real_email_svc()
        html = svc.render_template(
            "switch_recommendation.html",
            user_name="Bob",
            current_plan_name="Legacy Fixed",
            current_provider="PSEG",
            current_rate_kwh=0.1400,
            current_fixed_charge=11.00,
            recommended_plan_name="EcoRate Flex",
            recommended_provider="Ambit Energy",
            recommended_rate_kwh=0.1100,
            recommended_fixed_charge=8.50,
            savings_monthly=22.30,
            savings_annual=267.60,
            confidence=0.87,
            approve_url="https://rateshift.app/dashboard?approve=abc-123",
        )
        assert "EcoRate Flex" in html
        assert "22.30" in html
        assert "87%" in html or "87" in html
        assert "abc-123" in html

    def test_contract_expiring_template_renders(self):
        svc = self._real_email_svc()
        html = svc.render_template(
            "contract_expiring.html",
            user_name="Carol",
            plan_name="Standard Rate",
            days_remaining=30,
            provider="Eversource",
            rate_kwh=0.1300,
            expiry_date="May 3, 2026",
            is_free_switch_window=False,
        )
        assert "30" in html
        assert "Standard Rate" in html
        assert "May 3, 2026" in html

    def test_contract_expiring_free_window_banner_shows(self):
        svc = self._real_email_svc()
        html = svc.render_template(
            "contract_expiring.html",
            user_name="Dave",
            plan_name="Fixed Rate",
            days_remaining=15,
            provider="ConEd",
            rate_kwh=0.1200,
            expiry_date="April 18, 2026",
            is_free_switch_window=True,
        )
        assert "No early termination fee" in html


# =============================================================================
# TestUtilityHelpers
# =============================================================================


class TestUtilityHelpers:
    def test_to_float_decimal(self):
        assert _to_float(Decimal("18.50")) == 18.50

    def test_to_float_none_returns_zero(self):
        assert _to_float(None) == 0.0

    def test_to_float_invalid_returns_zero(self):
        assert _to_float("not-a-number") == 0.0

    def test_to_float_or_none_none(self):
        assert _to_float_or_none(None) is None

    def test_to_float_or_none_valid(self):
        assert _to_float_or_none(Decimal("0.1250")) == 0.1250
