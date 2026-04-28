"""Tests for public rates API endpoints."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.v1.public_rates import get_available_states, get_rate_summary


def _mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


def _row(data: dict):
    m = MagicMock()
    m.__getitem__ = lambda self, key: data[key]
    m.get = lambda key, default=None: data.get(key, default)
    return m


class TestGetAvailableStates:
    async def test_returns_states_grouped_by_utility(self):
        db = _mock_db()
        rows = [
            _row({"state": "CT", "utility_type": "electricity"}),
            _row({"state": "CT", "utility_type": "heating_oil"}),
            _row({"state": "TX", "utility_type": "electricity"}),
            _row({"state": "TX", "utility_type": "natural_gas"}),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        db.execute.return_value = result_mock

        result = await get_available_states(db=db)

        assert "CT" in result["states"]
        assert "electricity" in result["states"]["CT"]
        assert "heating_oil" in result["states"]["CT"]
        assert "TX" in result["states"]

    async def test_returns_empty_when_no_db(self):
        result = await get_available_states(db=None)
        assert result["states"] == []

    async def test_returns_empty_when_no_data(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        db.execute.return_value = result_mock

        result = await get_available_states(db=db)
        assert result["states"] == {}


class TestGetRateSummary:
    async def test_electricity_summary(self):
        db = _mock_db()
        now = datetime.now(UTC)
        rows = [
            _row(
                {
                    "supplier": "Eversource",
                    "price_per_kwh": Decimal("0.1200"),
                    "rate_type": "standard",
                    "updated_at": now,
                }
            ),
            _row(
                {
                    "supplier": "CheapCo",
                    "price_per_kwh": Decimal("0.1000"),
                    "rate_type": "standard",
                    "updated_at": now,
                }
            ),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        db.execute.return_value = result_mock

        result = await get_rate_summary(state="ct", utility_type="electricity", db=db)

        assert result["state"] == "CT"
        assert result["utility_type"] == "electricity"
        assert result["unit"] == "kWh"
        assert result["average_price"] == 0.11
        assert len(result["suppliers"]) == 2

    async def test_gas_summary(self):
        db = _mock_db()
        now = datetime.now(UTC)
        rows = [
            _row(
                {
                    "supplier": "EIA",
                    "price": Decimal("1.20"),
                    "source": "eia",
                    "fetched_at": now,
                }
            ),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        db.execute.return_value = result_mock

        result = await get_rate_summary(state="tx", utility_type="natural_gas", db=db)

        assert result["utility_type"] == "natural_gas"
        assert result["unit"] == "therm"
        assert result["average_price"] == 1.2

    async def test_heating_oil_summary(self):
        db = _mock_db()
        now = datetime.now(UTC)
        rows = [
            _row(
                {
                    "state": "CT",
                    "price_per_gallon": Decimal("3.50"),
                    "source": "eia",
                    "period_date": "2026-03-01",
                    "fetched_at": now,
                }
            ),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        db.execute.return_value = result_mock

        result = await get_rate_summary(state="ct", utility_type="heating_oil", db=db)

        assert result["utility_type"] == "heating_oil"
        assert result["unit"] == "gallon"
        assert result["average_price"] == 3.5

    async def test_unknown_utility_type(self):
        db = _mock_db()
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_rate_summary(state="ct", utility_type="steam", db=db)
        assert exc_info.value.status_code == 404

    async def test_no_data_returns_404(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        db.execute.return_value = result_mock

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_rate_summary(state="zz", utility_type="electricity", db=db)
        assert exc_info.value.status_code == 404

    async def test_db_unavailable(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_rate_summary(state="ct", utility_type="electricity", db=None)
        assert exc_info.value.status_code == 503
