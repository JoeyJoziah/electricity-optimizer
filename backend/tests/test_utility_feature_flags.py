"""
Tests for utility-type feature flags.

Verifies that each utility type has a corresponding feature flag
and that the flag evaluation integrates correctly with the service.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.feature_flag_service import FeatureFlagService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UTILITY_FLAGS = [
    "utility_electricity",
    "utility_natural_gas",
    "utility_heating_oil",
    "utility_propane",
    "utility_community_solar",
    "utility_water",
]

TIER_GATED_FLAGS = [
    ("utility_forecast", "pro"),
    ("utility_export", "business"),
]


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _enabled_row(tier_required=None, percentage=100) -> MagicMock:
    """Return a mock row for an enabled flag."""
    row = MagicMock()
    vals = [True, tier_required, percentage]
    row.__getitem__ = MagicMock(side_effect=lambda k: vals[k])
    result = MagicMock()
    result.fetchone.return_value = row
    return result


def _disabled_row() -> MagicMock:
    row = MagicMock()
    vals = [False, None, 100]
    row.__getitem__ = MagicMock(side_effect=lambda k: vals[k])
    result = MagicMock()
    result.fetchone.return_value = row
    return result


# ===========================================================================
# 1. Utility flag naming convention
# ===========================================================================


class TestUtilityFlagNames:
    """Verify flag names follow the utility_<type> convention."""

    def test_all_utility_flags_use_prefix(self):
        for flag in UTILITY_FLAGS:
            assert flag.startswith("utility_"), f"{flag} missing utility_ prefix"

    def test_tier_gated_flags_use_prefix(self):
        for flag, _tier in TIER_GATED_FLAGS:
            assert flag.startswith("utility_"), f"{flag} missing utility_ prefix"

    def test_six_base_utility_flags(self):
        assert len(UTILITY_FLAGS) == 6

    def test_two_tier_gated_utility_flags(self):
        assert len(TIER_GATED_FLAGS) == 2


# ===========================================================================
# 2. Base utility flags — enabled for all tiers by default
# ===========================================================================


class TestBaseUtilityFlags:
    """Base utility flags (electricity, gas, etc.) should be available to all."""

    @pytest.mark.parametrize("flag_name", UTILITY_FLAGS)
    async def test_enabled_for_free_tier(self, flag_name):
        db = _mock_db()
        db.execute.return_value = _enabled_row(tier_required=None)
        svc = FeatureFlagService(db)
        assert await svc.is_enabled(flag_name, user_tier="free") is True

    @pytest.mark.parametrize("flag_name", UTILITY_FLAGS)
    async def test_enabled_for_pro_tier(self, flag_name):
        db = _mock_db()
        db.execute.return_value = _enabled_row(tier_required=None)
        svc = FeatureFlagService(db)
        assert await svc.is_enabled(flag_name, user_tier="pro") is True

    @pytest.mark.parametrize("flag_name", UTILITY_FLAGS)
    async def test_disabled_when_flag_off(self, flag_name):
        db = _mock_db()
        db.execute.return_value = _disabled_row()
        svc = FeatureFlagService(db)
        assert await svc.is_enabled(flag_name, user_tier="pro") is False


# ===========================================================================
# 3. Tier-gated utility flags
# ===========================================================================


class TestTierGatedUtilityFlags:
    """Forecast and export flags require higher tiers."""

    @pytest.mark.parametrize("flag_name,required_tier", TIER_GATED_FLAGS)
    async def test_blocked_for_free_tier(self, flag_name, required_tier):
        db = _mock_db()
        db.execute.return_value = _enabled_row(tier_required=required_tier)
        svc = FeatureFlagService(db)
        assert await svc.is_enabled(flag_name, user_tier="free") is False

    async def test_forecast_allowed_for_pro(self):
        db = _mock_db()
        db.execute.return_value = _enabled_row(tier_required="pro")
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("utility_forecast", user_tier="pro") is True

    async def test_forecast_allowed_for_business(self):
        db = _mock_db()
        db.execute.return_value = _enabled_row(tier_required="pro")
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("utility_forecast", user_tier="business") is True

    async def test_export_blocked_for_pro(self):
        db = _mock_db()
        db.execute.return_value = _enabled_row(tier_required="business")
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("utility_export", user_tier="pro") is False

    async def test_export_allowed_for_business(self):
        db = _mock_db()
        db.execute.return_value = _enabled_row(tier_required="business")
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("utility_export", user_tier="business") is True


# ===========================================================================
# 4. Percentage rollout for utility flags
# ===========================================================================


class TestUtilityFlagPercentageRollout:
    """Verify percentage-based rollout works for utility flags."""

    async def test_zero_percent_blocks_all(self):
        db = _mock_db()
        db.execute.return_value = _enabled_row(percentage=0)
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("utility_electricity", user_id="test-user") is False

    async def test_hundred_percent_allows_all(self):
        db = _mock_db()
        db.execute.return_value = _enabled_row(percentage=100)
        svc = FeatureFlagService(db)
        assert await svc.is_enabled("utility_electricity", user_id="test-user") is True

    async def test_rollout_is_deterministic(self):
        """Same user_id always gets the same result for a given flag."""
        db = _mock_db()
        db.execute.return_value = _enabled_row(percentage=50)
        svc = FeatureFlagService(db)

        first = await svc.is_enabled("utility_propane", user_id="deterministic-user")
        db.execute.return_value = _enabled_row(percentage=50)
        second = await svc.is_enabled("utility_propane", user_id="deterministic-user")
        assert first == second
