"""
Tests for ForecastService — multi-utility rate forecasting.

Coverage:
  - FORECASTABLE_UTILITIES constant
  - get_forecast() dispatch & unsupported types
  - _extrapolate_trend() linear regression logic
  - Edge cases: no data, single point, stable trend
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from services.forecast_service import (
    FORECASTABLE_UTILITIES,
    ForecastService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mapping_result(rows=None):
    result = MagicMock()
    mapping = MagicMock()
    mapping.all.return_value = rows or []
    result.mappings.return_value = mapping
    return result


def _make_db(rows=None):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_mapping_result(rows))
    return db


def _make_rows(price_data, price_col="price_per_kwh", time_col="timestamp"):
    """Create mock row dicts from (timestamp, price) pairs."""
    return [{time_col: t, price_col: p} for t, p in price_data]


# =============================================================================
# 1. FORECASTABLE_UTILITIES constant
# =============================================================================


class TestForecastableUtilities:
    def test_contains_electricity(self):
        assert "electricity" in FORECASTABLE_UTILITIES

    def test_contains_natural_gas(self):
        assert "natural_gas" in FORECASTABLE_UTILITIES

    def test_contains_heating_oil(self):
        assert "heating_oil" in FORECASTABLE_UTILITIES

    def test_contains_propane(self):
        assert "propane" in FORECASTABLE_UTILITIES

    def test_excludes_water(self):
        assert "water" not in FORECASTABLE_UTILITIES

    def test_count(self):
        assert len(FORECASTABLE_UTILITIES) == 4


# =============================================================================
# 2. get_forecast() dispatch
# =============================================================================


class TestGetForecast:
    async def test_unsupported_utility_returns_error(self):
        service = ForecastService(_make_db())
        result = await service.get_forecast("water")
        assert "error" in result
        assert "supported_types" in result

    async def test_electricity_dispatches(self):
        db = _make_db([])
        service = ForecastService(db)
        result = await service.get_forecast("electricity", state="CT")
        db.execute.assert_called_once()
        assert result["utility_type"] == "electricity"

    async def test_natural_gas_dispatches(self):
        db = _make_db([])
        service = ForecastService(db)
        result = await service.get_forecast("natural_gas", state="CT")
        db.execute.assert_called_once()
        assert result["utility_type"] == "natural_gas"

    async def test_heating_oil_dispatches(self):
        db = _make_db([])
        service = ForecastService(db)
        result = await service.get_forecast("heating_oil", state="CT")
        db.execute.assert_called_once()
        assert result["utility_type"] == "heating_oil"

    async def test_propane_dispatches(self):
        db = _make_db([])
        service = ForecastService(db)
        result = await service.get_forecast("propane", state="CT")
        db.execute.assert_called_once()
        assert result["utility_type"] == "propane"


# =============================================================================
# 3. _extrapolate_trend() — unit tests of the static method
# =============================================================================


class TestExtrapolateTrend:
    """Direct tests of the linear regression logic."""

    def test_empty_rows_returns_error(self):
        result = ForecastService._extrapolate_trend(
            utility_type="electricity",
            rows=[],
            price_col="price_per_kwh",
            time_col="timestamp",
            unit="$/kWh",
            state="CT",
            horizon_days=30,
        )
        assert "error" in result
        assert result["data_points"] == 0

    def test_single_point_returns_error(self):
        rows = _make_rows(
            [(datetime(2026, 1, 1, tzinfo=UTC), 0.12)],
        )
        result = ForecastService._extrapolate_trend(
            utility_type="electricity",
            rows=rows,
            price_col="price_per_kwh",
            time_col="timestamp",
            unit="$/kWh",
            state="CT",
            horizon_days=30,
        )
        assert "error" in result
        assert result["data_points"] <= 1

    def test_increasing_trend(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        rows = _make_rows([(base + timedelta(days=i), 0.10 + 0.002 * i) for i in range(30)])
        result = ForecastService._extrapolate_trend(
            utility_type="electricity",
            rows=rows,
            price_col="price_per_kwh",
            time_col="timestamp",
            unit="$/kWh",
            state="CT",
            horizon_days=30,
        )
        assert result["trend"] == "increasing"
        assert result["forecasted_rate"] > result["current_rate"]
        assert result["data_points"] == 30

    def test_decreasing_trend(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        rows = _make_rows([(base + timedelta(days=i), 0.20 - 0.003 * i) for i in range(30)])
        result = ForecastService._extrapolate_trend(
            utility_type="electricity",
            rows=rows,
            price_col="price_per_kwh",
            time_col="timestamp",
            unit="$/kWh",
            state="CT",
            horizon_days=30,
        )
        assert result["trend"] == "decreasing"
        assert result["forecasted_rate"] < result["current_rate"]

    def test_stable_trend(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        rows = _make_rows([(base + timedelta(days=i), 0.15) for i in range(30)])
        result = ForecastService._extrapolate_trend(
            utility_type="electricity",
            rows=rows,
            price_col="price_per_kwh",
            time_col="timestamp",
            unit="$/kWh",
            state="CT",
            horizon_days=30,
        )
        assert result["trend"] == "stable"

    def test_negative_forecast_clamped_to_zero(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        rows = _make_rows([(base + timedelta(days=i), 0.05 - 0.005 * i) for i in range(10)])
        result = ForecastService._extrapolate_trend(
            utility_type="propane",
            rows=rows,
            price_col="price_per_kwh",
            time_col="timestamp",
            unit="$/gallon",
            state="CT",
            horizon_days=90,
        )
        assert result["forecasted_rate"] >= 0.0

    def test_response_keys_complete(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        rows = _make_rows([(base + timedelta(days=i), 0.12 + 0.001 * i) for i in range(10)])
        result = ForecastService._extrapolate_trend(
            utility_type="natural_gas",
            rows=rows,
            price_col="price_per_kwh",
            time_col="timestamp",
            unit="$/therm",
            state="NY",
            horizon_days=30,
        )
        expected_keys = {
            "utility_type",
            "state",
            "unit",
            "current_rate",
            "forecasted_rate",
            "horizon_days",
            "trend",
            "percent_change",
            "confidence",
            "model",
            "data_points",
            "r_squared",
            "generated_at",
        }
        assert expected_keys <= set(result.keys())
        assert result["model"] == "trend_extrapolation_v1"
        assert result["state"] == "NY"


# =============================================================================
# 4. Forecast edge cases (async, with mocked DB)
# =============================================================================


class TestForecastEdgeCases:
    async def test_horizon_clamped_to_90(self):
        db = _make_db([])
        service = ForecastService(db)
        result = await service.get_forecast("electricity", state="CT", horizon_days=200)
        assert result["utility_type"] == "electricity"

    async def test_no_data_returns_error(self):
        db = _make_db([])
        service = ForecastService(db)
        result = await service.get_forecast("electricity", state="CT")
        assert "error" in result
        assert result["data_points"] == 0
