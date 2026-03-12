"""
Tests for NeighborhoodService (backend/services/neighborhood_service.py)

Covers:
- Percentile comparison
- Insufficient data (< 5 users) returns null fields
- Cheapest supplier identification
- Potential savings calculation
- Comparison by utility type
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.neighborhood_service import NeighborhoodService, MIN_USERS_FOR_COMPARISON


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock async database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def service():
    return NeighborhoodService()


# =============================================================================
# Comparison
# =============================================================================


class TestComparison:
    @pytest.mark.asyncio
    async def test_comparison_returns_percentile(self, service, mock_db):
        """Returns user's rate percentile within their region."""
        # User count in region
        count_result = MagicMock()
        count_result.scalar.return_value = 25

        # User's percentile
        rank_result = MagicMock()
        rank_result.mappings.return_value.fetchone.return_value = {
            "user_rate": Decimal("0.1850"),
            "percentile": 0.65,
            "cheapest_supplier": "Town Square Energy",
            "cheapest_rate": Decimal("0.1200"),
            "avg_rate": Decimal("0.1750"),
        }

        mock_db.execute = AsyncMock(side_effect=[count_result, rank_result])

        result = await service.get_comparison(
            mock_db, user_id="user-1", region="us_ct", utility_type="electricity"
        )

        assert result["percentile"] == 0.65
        assert result["user_rate"] == Decimal("0.1850")

    @pytest.mark.asyncio
    async def test_comparison_null_when_insufficient_data(self, service, mock_db):
        """< 5 users in region returns null fields."""
        count_result = MagicMock()
        count_result.scalar.return_value = 3  # Below MIN_USERS_FOR_COMPARISON

        mock_db.execute = AsyncMock(return_value=count_result)

        result = await service.get_comparison(
            mock_db, user_id="user-1", region="us_wy", utility_type="electricity"
        )

        assert result["percentile"] is None
        assert result["cheapest_supplier"] is None
        assert result["potential_savings"] is None

    @pytest.mark.asyncio
    async def test_comparison_cheapest_supplier(self, service, mock_db):
        """Returns the cheapest supplier in the region."""
        count_result = MagicMock()
        count_result.scalar.return_value = 15

        rank_result = MagicMock()
        rank_result.mappings.return_value.fetchone.return_value = {
            "user_rate": Decimal("0.2100"),
            "percentile": 0.80,
            "cheapest_supplier": "Green Mountain Energy",
            "cheapest_rate": Decimal("0.1100"),
            "avg_rate": Decimal("0.1800"),
        }

        mock_db.execute = AsyncMock(side_effect=[count_result, rank_result])

        result = await service.get_comparison(
            mock_db, user_id="user-1", region="us_tx", utility_type="electricity"
        )

        assert result["cheapest_supplier"] == "Green Mountain Energy"
        assert result["cheapest_rate"] == Decimal("0.1100")

    @pytest.mark.asyncio
    async def test_comparison_potential_savings(self, service, mock_db):
        """Potential savings = user_rate - cheapest_rate (when positive)."""
        count_result = MagicMock()
        count_result.scalar.return_value = 20

        rank_result = MagicMock()
        rank_result.mappings.return_value.fetchone.return_value = {
            "user_rate": Decimal("0.2500"),
            "percentile": 0.90,
            "cheapest_supplier": "Budget Electric",
            "cheapest_rate": Decimal("0.1300"),
            "avg_rate": Decimal("0.1900"),
        }

        mock_db.execute = AsyncMock(side_effect=[count_result, rank_result])

        result = await service.get_comparison(
            mock_db, user_id="user-1", region="us_ct", utility_type="electricity"
        )

        assert result["potential_savings"] == Decimal("0.1200")

    @pytest.mark.asyncio
    async def test_comparison_by_utility_type(self, service, mock_db):
        """Comparison filters by utility_type."""
        count_result = MagicMock()
        count_result.scalar.return_value = 10

        rank_result = MagicMock()
        rank_result.mappings.return_value.fetchone.return_value = {
            "user_rate": Decimal("1.5000"),
            "percentile": 0.45,
            "cheapest_supplier": "Local Gas Co",
            "cheapest_rate": Decimal("1.2000"),
            "avg_rate": Decimal("1.4000"),
        }

        mock_db.execute = AsyncMock(side_effect=[count_result, rank_result])

        result = await service.get_comparison(
            mock_db, user_id="user-1", region="us_ct", utility_type="natural_gas"
        )

        assert result["utility_type"] == "natural_gas"
        assert result["percentile"] == 0.45
