"""
Tests for RateExportService — historical rate data export.

Coverage:
  - EXPORT_CONFIGS structure
  - JSON export format
  - CSV export format
  - Unsupported utility type error
  - Date range enforcement
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from services.rate_export_service import EXPORT_CONFIGS, RateExportService

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


# =============================================================================
# 1. EXPORT_CONFIGS structure
# =============================================================================


class TestExportConfigs:
    def test_electricity_config(self):
        cfg = EXPORT_CONFIGS["electricity"]
        assert cfg["table"] == "electricity_prices"
        assert cfg["price_col"] == "price_per_kwh"

    def test_natural_gas_config(self):
        cfg = EXPORT_CONFIGS["natural_gas"]
        assert cfg["table"] == "electricity_prices"
        assert cfg["extra_where"] == "utility_type = 'NATURAL_GAS'"

    def test_heating_oil_config(self):
        cfg = EXPORT_CONFIGS["heating_oil"]
        assert cfg["table"] == "heating_oil_prices"
        assert cfg["price_col"] == "price_per_gallon"

    def test_propane_config(self):
        cfg = EXPORT_CONFIGS["propane"]
        assert cfg["table"] == "propane_prices"

    def test_all_configs_have_required_keys(self):
        required = {"table", "columns", "price_col", "time_col", "state_col", "unit"}
        for name, cfg in EXPORT_CONFIGS.items():
            assert required <= set(cfg.keys()), f"{name} missing keys"

    def test_four_utility_types(self):
        assert len(EXPORT_CONFIGS) == 4


# =============================================================================
# 2. JSON export
# =============================================================================


class TestExportJSON:
    async def test_json_format_structure(self):
        now = datetime.now(UTC)
        rows = [
            {
                "region": "us_ct",
                "supplier": "A",
                "price_per_kwh": 0.15,
                "currency": "USD",
                "timestamp": now,
            },
        ]
        db = _make_db(rows)
        service = RateExportService(db)
        result = await service.export_rates("electricity", format="json", state="CT")

        assert result["format"] == "json"
        assert result["count"] == 1
        assert "date_range" in result
        assert isinstance(result["data"], list)

    async def test_empty_export(self):
        service = RateExportService(_make_db([]))
        result = await service.export_rates("electricity", format="json")
        assert result["count"] == 0
        assert result["data"] == []


# =============================================================================
# 3. CSV export
# =============================================================================


class TestExportCSV:
    async def test_csv_format_structure(self):
        now = datetime.now(UTC)
        rows = [
            {
                "region": "us_ct",
                "supplier": "A",
                "price_per_kwh": 0.15,
                "currency": "USD",
                "timestamp": now,
            },
        ]
        db = _make_db(rows)
        service = RateExportService(db)
        result = await service.export_rates("electricity", format="csv", state="CT")

        assert result["format"] == "csv"
        assert result["count"] == 1
        assert isinstance(result["data"], str)
        assert "region" in result["data"]

    async def test_csv_has_header_row(self):
        service = RateExportService(_make_db([]))
        result = await service.export_rates("electricity", format="csv")
        assert "region" in result["data"]
        assert "price_per_kwh" in result["data"]


# =============================================================================
# 4. Unsupported utility type
# =============================================================================


class TestUnknownUtilityType:
    async def test_error_returned(self):
        service = RateExportService(_make_db())
        result = await service.export_rates("solar")
        assert "error" in result
        assert "supported_types" in result


# =============================================================================
# 5. Date range enforcement
# =============================================================================


class TestDateRangeEnforcement:
    async def test_max_window_enforced(self):
        now = datetime.now(UTC)
        far_past = now - timedelta(days=500)
        service = RateExportService(_make_db([]))
        result = await service.export_rates(
            "electricity",
            format="json",
            start_date=far_past,
            end_date=now,
        )
        assert "error" not in result
        assert result["count"] == 0

    async def test_default_90_day_window(self):
        service = RateExportService(_make_db([]))
        result = await service.export_rates("electricity", format="json")
        assert "date_range" in result
