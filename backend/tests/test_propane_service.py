"""
Tests for PropaneService — prices, history, comparison, timing, store, static checks.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.propane_service import AVG_ANNUAL_GALLONS, PropaneService


def _mock_db_rows(rows):
    """Create a mock async db result."""
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.all.return_value = rows
    mock_mappings.first.return_value = rows[0] if rows else None
    mock_result.mappings.return_value = mock_mappings
    return mock_result


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return PropaneService(mock_db)


# ------------------------------------------------------------------
# get_current_prices
# ------------------------------------------------------------------


class TestGetCurrentPrices:
    async def test_returns_all_states_when_no_filter(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows(
            [
                {
                    "id": "uuid-1",
                    "state": "CT",
                    "price_per_gallon": Decimal("2.8500"),
                    "source": "eia",
                    "period_date": date(2026, 3, 3),
                    "fetched_at": datetime(2026, 3, 10, tzinfo=UTC),
                },
                {
                    "id": "uuid-2",
                    "state": "US",
                    "price_per_gallon": Decimal("2.6000"),
                    "source": "eia",
                    "period_date": date(2026, 3, 3),
                    "fetched_at": datetime(2026, 3, 10, tzinfo=UTC),
                },
            ]
        )

        prices = await service.get_current_prices()
        assert len(prices) == 2
        assert prices[0]["state"] == "CT"
        assert prices[0]["price_per_gallon"] == 2.85

    async def test_filters_by_state(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows(
            [
                {
                    "id": "uuid-1",
                    "state": "CT",
                    "price_per_gallon": Decimal("2.8500"),
                    "source": "eia",
                    "period_date": date(2026, 3, 3),
                    "fetched_at": datetime(2026, 3, 10, tzinfo=UTC),
                },
            ]
        )

        prices = await service.get_current_prices("ct")
        assert len(prices) == 1
        assert prices[0]["state"] == "CT"

    async def test_empty_result(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows([])
        prices = await service.get_current_prices("TX")
        assert prices == []


# ------------------------------------------------------------------
# get_price_history
# ------------------------------------------------------------------


class TestGetPriceHistory:
    async def test_returns_history(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows(
            [
                {
                    "id": f"uuid-{i}",
                    "state": "MA",
                    "price_per_gallon": Decimal(f"2.{80 + i}00"),
                    "source": "eia",
                    "period_date": date(2026, 3, 10 - i),
                    "fetched_at": datetime(2026, 3, 10, tzinfo=UTC),
                }
                for i in range(4)
            ]
        )

        history = await service.get_price_history("ma", weeks=4)
        assert len(history) == 4
        assert history[0]["state"] == "MA"

    async def test_empty_history(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows([])
        history = await service.get_price_history("ZZ")
        assert history == []


# ------------------------------------------------------------------
# get_price_comparison
# ------------------------------------------------------------------


class TestGetPriceComparison:
    async def test_comparison_cheaper_than_national(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows(
            [
                {
                    "state": "CT",
                    "price_per_gallon": Decimal("2.5000"),
                    "fetched_at": datetime(2026, 3, 10, tzinfo=UTC),
                },
                {
                    "state": "US",
                    "price_per_gallon": Decimal("2.8000"),
                    "fetched_at": datetime(2026, 3, 10, tzinfo=UTC),
                },
            ]
        )

        result = await service.get_price_comparison("CT")
        assert result is not None
        assert result["state"] == "CT"
        assert result["price_per_gallon"] == 2.5
        assert result["national_avg"] == 2.8
        assert result["difference_pct"] < 0  # Cheaper
        assert result["estimated_annual_cost"] == round(2.5 * AVG_ANNUAL_GALLONS, 2)

    async def test_comparison_more_expensive(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows(
            [
                {
                    "state": "NH",
                    "price_per_gallon": Decimal("3.1000"),
                    "fetched_at": datetime(2026, 3, 10, tzinfo=UTC),
                },
                {
                    "state": "US",
                    "price_per_gallon": Decimal("2.8000"),
                    "fetched_at": datetime(2026, 3, 10, tzinfo=UTC),
                },
            ]
        )

        result = await service.get_price_comparison("NH")
        assert result["difference_pct"] > 0  # More expensive

    async def test_comparison_no_data(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows([])
        result = await service.get_price_comparison("ZZ")
        assert result is None


# ------------------------------------------------------------------
# get_seasonal_advice
# ------------------------------------------------------------------


class TestGetSeasonalAdvice:
    async def test_good_timing_below_average(self, service, mock_db):
        prices = [
            {
                "price_per_gallon": Decimal("2.50"),
                "period_date": date(2026, 3, 3),
            },
        ] + [
            {
                "price_per_gallon": Decimal("3.00"),
                "period_date": date(2026, 2, i + 1),
            }
            for i in range(10)
        ]
        mock_db.execute.return_value = _mock_db_rows(prices)

        advice = await service.get_seasonal_advice("CT")
        assert advice["timing"] == "good"
        assert advice["current_price"] == 2.5

    async def test_wait_timing_above_average(self, service, mock_db):
        prices = [
            {
                "price_per_gallon": Decimal("3.50"),
                "period_date": date(2026, 3, 3),
            },
        ] + [
            {
                "price_per_gallon": Decimal("2.50"),
                "period_date": date(2026, 2, i + 1),
            }
            for i in range(10)
        ]
        mock_db.execute.return_value = _mock_db_rows(prices)

        advice = await service.get_seasonal_advice("CT")
        assert advice["timing"] == "wait"

    async def test_insufficient_data(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows(
            [
                {"price_per_gallon": Decimal("2.50"), "period_date": date(2026, 3, 3)},
            ]
        )

        advice = await service.get_seasonal_advice("CT")
        assert "Not enough" in advice["advice"]
        assert advice["data_points"] == 1


# ------------------------------------------------------------------
# store_prices
# ------------------------------------------------------------------


class TestStorePrices:
    async def test_stores_multiple_prices(self, service, mock_db):
        prices = [
            {
                "state": "CT",
                "price_per_gallon": 2.85,
                "source": "eia",
                "period_date": "2026-03-03",
            },
            {
                "state": "US",
                "price_per_gallon": 2.60,
                "source": "eia",
                "period_date": "2026-03-03",
            },
        ]
        stored = await service.store_prices(prices)
        assert stored == 2
        assert mock_db.execute.call_count == 2
        mock_db.commit.assert_called_once()

    async def test_handles_store_error(self, service, mock_db):
        mock_db.execute.side_effect = [Exception("DB error"), None]
        prices = [
            {
                "state": "CT",
                "price_per_gallon": 2.85,
                "source": "eia",
                "period_date": "2026-03-03",
            },
            {
                "state": "US",
                "price_per_gallon": 2.60,
                "source": "eia",
                "period_date": "2026-03-03",
            },
        ]
        stored = await service.store_prices(prices)
        assert stored == 1  # One succeeded, one failed


# ------------------------------------------------------------------
# Static methods
# ------------------------------------------------------------------


class TestStaticMethods:
    def test_is_propane_state_valid(self):
        assert PropaneService.is_propane_state("CT") is True
        assert PropaneService.is_propane_state("ct") is True
        assert PropaneService.is_propane_state("MA") is True

    def test_is_propane_state_invalid(self):
        assert PropaneService.is_propane_state("TX") is False
        assert PropaneService.is_propane_state("CA") is False

    def test_get_tracked_states(self):
        states = PropaneService.get_tracked_states()
        assert isinstance(states, list)
        assert len(states) == 8
        assert states == sorted(states)  # Should be sorted
        assert "CT" in states
        assert "MA" in states
