"""
Tests for SavingsAggregator (backend/services/savings_aggregator.py)

Covers:
- Combined savings for single and multiple utilities
- No data returns zero
- Per-utility breakdown
- Rank percentile
- Disabled utility flags skipped

Updated for combined CTE query (19-P2-8): the aggregator now returns
utility_type, monthly_savings, AND savings_rank_pct in a single query.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.savings_aggregator import SavingsAggregator

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
def aggregator():
    return SavingsAggregator()


# =============================================================================
# Combined savings
# =============================================================================


class TestCombinedSavings:
    async def test_combined_savings_single_utility(self, aggregator, mock_db):
        """Single utility returns its savings as the total."""
        result_mock = MagicMock()
        result_mock.mappings.return_value.fetchall.return_value = [
            {
                "utility_type": "electricity",
                "monthly_savings": Decimal("25.50"),
                "savings_rank_pct": 0.72,
            },
        ]

        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await aggregator.get_combined_savings(mock_db, user_id="user-1")

        assert result["total_monthly_savings"] == Decimal("25.50")
        assert len(result["breakdown"]) == 1
        assert result["breakdown"][0]["utility_type"] == "electricity"

    async def test_combined_savings_multiple_utilities(self, aggregator, mock_db):
        """Multiple utilities aggregated correctly."""
        result_mock = MagicMock()
        result_mock.mappings.return_value.fetchall.return_value = [
            {
                "utility_type": "electricity",
                "monthly_savings": Decimal("25.00"),
                "savings_rank_pct": 0.85,
            },
            {
                "utility_type": "natural_gas",
                "monthly_savings": Decimal("15.00"),
                "savings_rank_pct": 0.85,
            },
            {
                "utility_type": "water",
                "monthly_savings": Decimal("8.00"),
                "savings_rank_pct": 0.85,
            },
        ]

        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await aggregator.get_combined_savings(mock_db, user_id="user-1")

        assert result["total_monthly_savings"] == Decimal("48.00")
        assert len(result["breakdown"]) == 3

    async def test_combined_savings_no_data_returns_zero(self, aggregator, mock_db):
        """No savings data returns zero total and empty breakdown."""
        result_mock = MagicMock()
        result_mock.mappings.return_value.fetchall.return_value = []

        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await aggregator.get_combined_savings(mock_db, user_id="user-1")

        assert result["total_monthly_savings"] == Decimal("0")
        assert result["breakdown"] == []
        assert result["savings_rank_pct"] is None


class TestSavingsBreakdown:
    async def test_savings_breakdown_per_utility(self, aggregator, mock_db):
        """Breakdown includes utility_type and savings per utility."""
        result_mock = MagicMock()
        result_mock.mappings.return_value.fetchall.return_value = [
            {
                "utility_type": "electricity",
                "monthly_savings": Decimal("30.00"),
                "savings_rank_pct": 0.60,
            },
            {
                "utility_type": "propane",
                "monthly_savings": Decimal("12.50"),
                "savings_rank_pct": 0.60,
            },
        ]

        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await aggregator.get_combined_savings(mock_db, user_id="user-1")

        breakdown = result["breakdown"]
        types = [b["utility_type"] for b in breakdown]
        assert "electricity" in types
        assert "propane" in types


class TestSavingsRank:
    async def test_savings_rank_percentile(self, aggregator, mock_db):
        """Savings rank is a percentile from PERCENT_RANK()."""
        result_mock = MagicMock()
        result_mock.mappings.return_value.fetchall.return_value = [
            {
                "utility_type": "electricity",
                "monthly_savings": Decimal("50.00"),
                "savings_rank_pct": 0.92,
            },
        ]

        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await aggregator.get_combined_savings(mock_db, user_id="user-1")

        assert result["savings_rank_pct"] == 0.92


class TestDisabledFlags:
    async def test_combined_savings_skips_disabled_flags(self, aggregator, mock_db):
        """Disabled utility flags should be excluded from aggregation."""
        result_mock = MagicMock()
        result_mock.mappings.return_value.fetchall.return_value = [
            {
                "utility_type": "electricity",
                "monthly_savings": Decimal("25.00"),
                "savings_rank_pct": 0.55,
            },
        ]

        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await aggregator.get_combined_savings(
            mock_db, user_id="user-1", enabled_utilities=["electricity"]
        )

        assert result["total_monthly_savings"] == Decimal("25.00")
        assert len(result["breakdown"]) == 1
