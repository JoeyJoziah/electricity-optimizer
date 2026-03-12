"""
Tests for Heating Oil Service

Verifies price queries, history, comparison, dealer directory,
data ingestion, and state checks.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import date, datetime, timezone

from services.heating_oil_service import HeatingOilService
from models.region import HEATING_OIL_STATES


PRICE_ROW = {
    "id": uuid4(),
    "state": "CT",
    "price_per_gallon": 3.45,
    "source": "eia",
    "period_date": date(2026, 3, 10),
    "fetched_at": datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc),
}

US_PRICE_ROW = {
    **PRICE_ROW,
    "id": uuid4(),
    "state": "US",
    "price_per_gallon": 3.50,
}

DEALER_ROW = {
    "id": uuid4(),
    "name": "Hocon Gas",
    "state": "CT",
    "city": "Danbury",
    "phone": "203-744-0555",
    "website": "https://hocongas.com",
    "rating": 4.5,
    "is_active": True,
}


def _mock_db_with_rows(rows):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = rows
    mock_result.mappings.return_value.first.return_value = rows[0] if rows else None
    mock_db.execute.return_value = mock_result
    mock_db.commit = AsyncMock()
    return mock_db


def _mock_db_empty():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_result.mappings.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result
    mock_db.commit = AsyncMock()
    return mock_db


class TestGetCurrentPrices:
    """Test current price queries."""

    @pytest.mark.asyncio
    async def test_get_all_prices(self):
        mock_db = _mock_db_with_rows([PRICE_ROW, US_PRICE_ROW])
        service = HeatingOilService(mock_db)
        result = await service.get_current_prices()

        assert len(result) == 2
        assert result[0]["state"] == "CT"
        assert result[0]["price_per_gallon"] == 3.45

    @pytest.mark.asyncio
    async def test_get_prices_by_state(self):
        mock_db = _mock_db_with_rows([PRICE_ROW])
        service = HeatingOilService(mock_db)
        result = await service.get_current_prices(state="ct")

        assert len(result) == 1
        assert result[0]["state"] == "CT"

    @pytest.mark.asyncio
    async def test_get_prices_empty(self):
        mock_db = _mock_db_empty()
        service = HeatingOilService(mock_db)
        result = await service.get_current_prices(state="ZZ")

        assert result == []


class TestGetPriceHistory:
    """Test price history queries."""

    @pytest.mark.asyncio
    async def test_returns_history(self):
        rows = [
            {**PRICE_ROW, "period_date": date(2026, 3, 10)},
            {**PRICE_ROW, "period_date": date(2026, 3, 3)},
        ]
        mock_db = _mock_db_with_rows(rows)
        service = HeatingOilService(mock_db)
        result = await service.get_price_history("CT", weeks=12)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_history(self):
        mock_db = _mock_db_empty()
        service = HeatingOilService(mock_db)
        result = await service.get_price_history("CT")

        assert result == []


class TestGetPriceComparison:
    """Test price comparison against national average."""

    @pytest.mark.asyncio
    async def test_comparison_cheaper_than_national(self):
        """CT at $3.45 vs national $3.50 = cheaper."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"state": "CT", "price_per_gallon": 3.45, "fetched_at": datetime.now(timezone.utc)},
            {"state": "US", "price_per_gallon": 3.50, "fetched_at": datetime.now(timezone.utc)},
        ]
        mock_db.execute.return_value = mock_result

        service = HeatingOilService(mock_db)
        result = await service.get_price_comparison("CT")

        assert result is not None
        assert result["state"] == "CT"
        assert result["price_per_gallon"] == 3.45
        assert result["national_avg"] == 3.50
        assert result["difference_pct"] < 0  # cheaper
        assert result["estimated_monthly_cost"] > 0
        assert result["estimated_annual_cost"] > 0

    @pytest.mark.asyncio
    async def test_comparison_not_found(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = HeatingOilService(mock_db)
        result = await service.get_price_comparison("ZZ")

        assert result is None


class TestGetDealers:
    """Test dealer directory queries."""

    @pytest.mark.asyncio
    async def test_returns_dealers(self):
        mock_db = _mock_db_with_rows([DEALER_ROW])
        service = HeatingOilService(mock_db)
        result = await service.get_dealers("CT")

        assert len(result) == 1
        assert result[0]["name"] == "Hocon Gas"
        assert result[0]["city"] == "Danbury"
        assert result[0]["rating"] == 4.5

    @pytest.mark.asyncio
    async def test_empty_dealers(self):
        mock_db = _mock_db_empty()
        service = HeatingOilService(mock_db)
        result = await service.get_dealers("ZZ")

        assert result == []


class TestStoreprices:
    """Test data ingestion."""

    @pytest.mark.asyncio
    async def test_store_prices(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        service = HeatingOilService(mock_db)
        stored = await service.store_prices([
            {
                "state": "CT",
                "price_per_gallon": 3.45,
                "source": "eia",
                "period_date": "2026-03-10",
            },
            {
                "state": "US",
                "price_per_gallon": 3.50,
                "source": "eia",
                "period_date": "2026-03-10",
            },
        ])

        assert stored == 2
        assert mock_db.execute.call_count == 2
        assert mock_db.commit.call_count == 1


class TestIsHeatingOilState:
    """Test static state checks."""

    def test_ct_is_heating_oil_state(self):
        assert HeatingOilService.is_heating_oil_state("CT") is True

    def test_ma_is_heating_oil_state(self):
        assert HeatingOilService.is_heating_oil_state("MA") is True

    def test_tx_not_heating_oil_state(self):
        assert HeatingOilService.is_heating_oil_state("TX") is False

    def test_case_insensitive(self):
        assert HeatingOilService.is_heating_oil_state("ct") is True

    def test_all_nine_states(self):
        expected = {"CT", "MA", "NY", "NJ", "PA", "ME", "NH", "VT", "RI"}
        assert HEATING_OIL_STATES == expected

    def test_get_tracked_states(self):
        states = HeatingOilService.get_tracked_states()
        assert len(states) == 9
        assert states == sorted(states)  # alphabetical
