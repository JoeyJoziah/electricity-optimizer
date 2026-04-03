"""
Tests for ContractLifecycleService (backend/services/contract_lifecycle_service.py)

Covers:
- get_contract_status: active plan, no plan, expired plan, month-to-month
- is_in_cooldown: active, expired, no prior switch, custom cooldown_days
- is_in_rescission: active, expired, no rescission_ends column value
- get_free_switch_window: within 45-day window, outside window, month-to-month, expired
- get_rescission_period_days: TX=14, OH=7, PA=3, IL=10, NY=3, unknown=3
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.contract_lifecycle_service import ContractLifecycleService

# =============================================================================
# Helpers
# =============================================================================


def _make_db_result(row: dict | None) -> MagicMock:
    """Build a mock SQLAlchemy execute() result whose .mappings().first() returns row."""
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = row
    return mock_result


def _make_db():
    """Create a minimal mock async DB session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    return _make_db()


@pytest.fixture
def service(mock_db):
    return ContractLifecycleService(mock_db)


# =============================================================================
# get_contract_status
# =============================================================================


class TestGetContractStatus:
    async def test_active_plan_found(self, service, mock_db):
        """Returns full contract details when an active plan exists."""
        contract_end = datetime(2026, 9, 1, tzinfo=UTC)
        mock_db.execute.return_value = _make_db_result(
            {
                "plan_name": "Fixed 12-Month Rate",
                "provider_name": "Green Energy Co",
                "contract_start": datetime(2025, 9, 1, tzinfo=UTC),
                "contract_end": contract_end,
                "etf_amount": Decimal("150.00"),
            }
        )

        result = await service.get_contract_status("user-abc")

        assert result["has_active_plan"] is True
        assert result["plan_name"] == "Fixed 12-Month Rate"
        assert result["provider_name"] == "Green Energy Co"
        assert result["is_month_to_month"] is False
        assert result["etf_amount"] == Decimal("150.00")
        assert result["days_remaining"] is not None
        assert result["days_remaining"] >= 0

    async def test_no_active_plan(self, service, mock_db):
        """Returns a zeroed-out dict when no active plan is found."""
        mock_db.execute.return_value = _make_db_result(None)

        result = await service.get_contract_status("user-none")

        assert result["has_active_plan"] is False
        assert result["plan_name"] is None
        assert result["provider_name"] is None
        assert result["contract_start"] is None
        assert result["contract_end"] is None
        assert result["days_remaining"] is None
        assert result["is_month_to_month"] is False
        assert result["etf_amount"] == Decimal("0")

    async def test_expired_plan_days_remaining_zero(self, service, mock_db):
        """days_remaining is clamped to 0 when contract_end is in the past."""
        past_end = datetime(2024, 1, 1, tzinfo=UTC)
        mock_db.execute.return_value = _make_db_result(
            {
                "plan_name": "Old Fixed Plan",
                "provider_name": "Legacy Power",
                "contract_start": datetime(2023, 1, 1, tzinfo=UTC),
                "contract_end": past_end,
                "etf_amount": Decimal("0"),
            }
        )

        result = await service.get_contract_status("user-expired")

        assert result["has_active_plan"] is True
        assert result["days_remaining"] == 0
        assert result["is_month_to_month"] is False

    async def test_month_to_month_no_contract_end(self, service, mock_db):
        """is_month_to_month is True and days_remaining is None when contract_end is NULL."""
        mock_db.execute.return_value = _make_db_result(
            {
                "plan_name": "Variable Rate",
                "provider_name": "Flex Power",
                "contract_start": datetime(2025, 1, 1, tzinfo=UTC),
                "contract_end": None,
                "etf_amount": Decimal("0"),
            }
        )

        result = await service.get_contract_status("user-mtm")

        assert result["has_active_plan"] is True
        assert result["is_month_to_month"] is True
        assert result["days_remaining"] is None
        assert result["etf_amount"] == Decimal("0")


# =============================================================================
# is_in_cooldown
# =============================================================================


class TestIsInCooldown:
    async def test_cooldown_active_returns_true_and_days(self, service, mock_db):
        """Returns (True, N) when enacted_at + cooldown_days is in the future."""
        enacted_at = datetime.now(UTC) - timedelta(days=2)
        mock_db.execute.side_effect = [
            _make_db_result({"enacted_at": enacted_at}),  # switch_executions
            _make_db_result({"cooldown_days": 5}),  # user_agent_settings
        ]

        in_cooldown, days_remaining = await service.is_in_cooldown("user-cool")

        assert in_cooldown is True
        assert days_remaining > 0
        assert days_remaining <= 5

    async def test_cooldown_expired_returns_false_zero(self, service, mock_db):
        """Returns (False, 0) when enacted_at + cooldown_days is in the past."""
        enacted_at = datetime.now(UTC) - timedelta(days=10)
        mock_db.execute.side_effect = [
            _make_db_result({"enacted_at": enacted_at}),
            _make_db_result({"cooldown_days": 5}),
        ]

        in_cooldown, days_remaining = await service.is_in_cooldown("user-expired")

        assert in_cooldown is False
        assert days_remaining == 0

    async def test_no_prior_switch_returns_false_zero(self, service, mock_db):
        """Returns (False, 0) when there is no enacted switch on record."""
        mock_db.execute.return_value = _make_db_result(None)

        in_cooldown, days_remaining = await service.is_in_cooldown("user-new")

        assert in_cooldown is False
        assert days_remaining == 0

    async def test_custom_cooldown_days_respected(self, service, mock_db):
        """Uses the cooldown_days value from user_agent_settings, not the default."""
        enacted_at = datetime.now(UTC) - timedelta(days=8)
        mock_db.execute.side_effect = [
            _make_db_result({"enacted_at": enacted_at}),
            _make_db_result({"cooldown_days": 30}),  # custom 30-day cooldown
        ]

        in_cooldown, days_remaining = await service.is_in_cooldown("user-custom")

        # 30-day cooldown started 8 days ago → still active
        assert in_cooldown is True
        assert days_remaining > 0


# =============================================================================
# is_in_rescission
# =============================================================================


class TestIsInRescission:
    async def test_rescission_active_returns_true_and_days(self, service, mock_db):
        """Returns (True, N) when rescission_ends is in the future."""
        rescission_ends = datetime.now(UTC) + timedelta(days=5)
        mock_db.execute.return_value = _make_db_result({"rescission_ends": rescission_ends})

        in_rescission, days_remaining = await service.is_in_rescission("user-resc")

        assert in_rescission is True
        assert days_remaining > 0
        assert days_remaining <= 5

    async def test_rescission_expired_returns_false_zero(self, service, mock_db):
        """Returns (False, 0) when rescission_ends is in the past."""
        rescission_ends = datetime.now(UTC) - timedelta(days=3)
        mock_db.execute.return_value = _make_db_result({"rescission_ends": rescission_ends})

        in_rescission, days_remaining = await service.is_in_rescission("user-past")

        assert in_rescission is False
        assert days_remaining == 0

    async def test_no_rescission_ends_returns_false_zero(self, service, mock_db):
        """Returns (False, 0) when rescission_ends is NULL or no row exists."""
        mock_db.execute.return_value = _make_db_result({"rescission_ends": None})

        in_rescission, days_remaining = await service.is_in_rescission("user-noresc")

        assert in_rescission is False
        assert days_remaining == 0


# =============================================================================
# get_free_switch_window
# =============================================================================


class TestGetFreeSwitchWindow:
    async def test_window_open_contract_expiring_within_45_days(self, service, mock_db):
        """window_open=True and etf_waived=True when contract ends in 30 days."""
        contract_end = datetime.now(UTC) + timedelta(days=30)
        mock_db.execute.return_value = _make_db_result(
            {
                "contract_end": contract_end,
                "etf_amount": Decimal("200.00"),
                "status": "active",
            }
        )

        result = await service.get_free_switch_window("user-window")

        assert result["window_open"] is True
        assert result["etf_waived"] is True
        assert 29 <= result["days_until_expiry"] <= 30
        assert "switch" in result["recommended_action"].lower()

    async def test_window_closed_contract_far_from_expiry(self, service, mock_db):
        """window_open=False when contract has 90 days remaining."""
        contract_end = datetime.now(UTC) + timedelta(days=90)
        mock_db.execute.return_value = _make_db_result(
            {
                "contract_end": contract_end,
                "etf_amount": Decimal("300.00"),
                "status": "active",
            }
        )

        result = await service.get_free_switch_window("user-closed")

        assert result["window_open"] is False
        assert result["etf_waived"] is False
        assert 89 <= result["days_until_expiry"] <= 90

    async def test_month_to_month_window_always_open(self, service, mock_db):
        """Month-to-month plans always have window_open=True."""
        mock_db.execute.return_value = _make_db_result(
            {
                "contract_end": None,
                "etf_amount": Decimal("0"),
                "status": "active",
            }
        )

        result = await service.get_free_switch_window("user-mtm")

        assert result["window_open"] is True
        assert result["etf_waived"] is True
        assert result["days_until_expiry"] is None
        assert "month-to-month" in result["recommended_action"].lower()

    async def test_expired_contract_window_open(self, service, mock_db):
        """Window is open (and ETF waived) when contract has already expired."""
        past_end = datetime.now(UTC) - timedelta(days=5)
        mock_db.execute.return_value = _make_db_result(
            {
                "contract_end": past_end,
                "etf_amount": Decimal("100.00"),
                "status": "active",
            }
        )

        result = await service.get_free_switch_window("user-expired")

        assert result["window_open"] is True
        assert result["etf_waived"] is True
        assert result["days_until_expiry"] == 0


# =============================================================================
# get_rescission_period_days
# =============================================================================


class TestGetRescissionPeriodDays:
    def test_tx_returns_14(self):
        assert ContractLifecycleService.get_rescission_period_days("TX") == 14

    def test_oh_returns_7(self):
        assert ContractLifecycleService.get_rescission_period_days("OH") == 7

    def test_pa_returns_3(self):
        assert ContractLifecycleService.get_rescission_period_days("PA") == 3

    def test_il_returns_10(self):
        assert ContractLifecycleService.get_rescission_period_days("IL") == 10

    def test_ny_returns_3(self):
        assert ContractLifecycleService.get_rescission_period_days("NY") == 3

    def test_unknown_state_returns_3(self):
        assert ContractLifecycleService.get_rescission_period_days("ZZ") == 3
