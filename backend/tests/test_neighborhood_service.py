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

from services.neighborhood_service import NeighborhoodService

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
    async def test_comparison_returns_percentile(self, service, mock_db):
        """Returns user's rate percentile within their region."""
        combined_result = MagicMock()
        combined_result.mappings.return_value.fetchone.return_value = {
            "user_count": 25,
            "user_rate": Decimal("0.1850"),
            "percentile": 0.65,
            "cheapest_supplier": "Town Square Energy",
            "cheapest_rate": Decimal("0.1200"),
            "avg_rate": Decimal("0.1750"),
        }

        mock_db.execute = AsyncMock(return_value=combined_result)

        result = await service.get_comparison(
            mock_db, user_id="user-1", region="us_ct", utility_type="electricity"
        )

        assert result["percentile"] == 0.65
        assert result["user_rate"] == Decimal("0.1850")

    async def test_comparison_null_when_insufficient_data(self, service, mock_db):
        """< 5 users in region returns null fields."""
        combined_result = MagicMock()
        combined_result.mappings.return_value.fetchone.return_value = {
            "user_count": 3,
            "user_rate": None,
            "percentile": None,
            "cheapest_supplier": None,
            "cheapest_rate": None,
            "avg_rate": None,
        }

        mock_db.execute = AsyncMock(return_value=combined_result)

        result = await service.get_comparison(
            mock_db, user_id="user-1", region="us_wy", utility_type="electricity"
        )

        assert result["percentile"] is None
        assert result["cheapest_supplier"] is None
        assert result["potential_savings"] is None

    async def test_comparison_cheapest_supplier(self, service, mock_db):
        """Returns the cheapest supplier in the region."""
        combined_result = MagicMock()
        combined_result.mappings.return_value.fetchone.return_value = {
            "user_count": 15,
            "user_rate": Decimal("0.2100"),
            "percentile": 0.80,
            "cheapest_supplier": "Green Mountain Energy",
            "cheapest_rate": Decimal("0.1100"),
            "avg_rate": Decimal("0.1800"),
        }

        mock_db.execute = AsyncMock(return_value=combined_result)

        result = await service.get_comparison(
            mock_db, user_id="user-1", region="us_tx", utility_type="electricity"
        )

        assert result["cheapest_supplier"] == "Green Mountain Energy"
        assert result["cheapest_rate"] == Decimal("0.1100")

    async def test_comparison_potential_savings(self, service, mock_db):
        """Potential savings = user_rate - cheapest_rate (when positive)."""
        combined_result = MagicMock()
        combined_result.mappings.return_value.fetchone.return_value = {
            "user_count": 20,
            "user_rate": Decimal("0.2500"),
            "percentile": 0.90,
            "cheapest_supplier": "Budget Electric",
            "cheapest_rate": Decimal("0.1300"),
            "avg_rate": Decimal("0.1900"),
        }

        mock_db.execute = AsyncMock(return_value=combined_result)

        result = await service.get_comparison(
            mock_db, user_id="user-1", region="us_ct", utility_type="electricity"
        )

        assert result["potential_savings"] == Decimal("0.1200")

    async def test_comparison_by_utility_type(self, service, mock_db):
        """Comparison filters by utility_type."""
        combined_result = MagicMock()
        combined_result.mappings.return_value.fetchone.return_value = {
            "user_count": 10,
            "user_rate": Decimal("1.5000"),
            "percentile": 0.45,
            "cheapest_supplier": "Local Gas Co",
            "cheapest_rate": Decimal("1.2000"),
            "avg_rate": Decimal("1.4000"),
        }

        mock_db.execute = AsyncMock(return_value=combined_result)

        result = await service.get_comparison(
            mock_db, user_id="user-1", region="us_ct", utility_type="natural_gas"
        )

        assert result["utility_type"] == "natural_gas"
        assert result["percentile"] == 0.45
