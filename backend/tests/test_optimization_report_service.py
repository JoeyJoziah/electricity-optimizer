"""
Tests for OptimizationReportService — multi-utility spend optimization.

Coverage:
  - AVG_MONTHLY_CONSUMPTION constants
  - Report structure and field completeness
  - Individual utility spend calculations
  - Savings opportunity generation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from services.optimization_report_service import (
    AVG_MONTHLY_CONSUMPTION,
    OptimizationReportService,
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


def _make_db(row_sets=None):
    """Create a mock DB that returns different row sets per call."""
    db = AsyncMock()
    if row_sets:
        db.execute = AsyncMock(side_effect=[_mapping_result(rs) for rs in row_sets])
    else:
        db.execute = AsyncMock(return_value=_mapping_result([]))
    return db


# =============================================================================
# 1. AVG_MONTHLY_CONSUMPTION constants
# =============================================================================


class TestAvgMonthlyConsumption:
    def test_electricity(self):
        assert AVG_MONTHLY_CONSUMPTION["electricity"]["amount"] == 886

    def test_natural_gas(self):
        assert AVG_MONTHLY_CONSUMPTION["natural_gas"]["amount"] == 50

    def test_heating_oil(self):
        assert AVG_MONTHLY_CONSUMPTION["heating_oil"]["amount"] == 67

    def test_propane(self):
        assert AVG_MONTHLY_CONSUMPTION["propane"]["amount"] == 63

    def test_water(self):
        assert AVG_MONTHLY_CONSUMPTION["water"]["amount"] == 5760


# =============================================================================
# 2. Report structure
# =============================================================================


class TestReportStructure:
    async def test_empty_report_has_required_keys(self):
        db = _make_db([[], [], [], []])
        service = OptimizationReportService(db)
        result = await service.generate_report("CT")

        assert result["state"] == "CT"
        assert "generated_at" in result
        assert result["utilities"] == []
        assert result["total_monthly_spend"] == 0
        assert result["total_annual_spend"] == 0
        assert result["savings_opportunities"] == []
        assert result["utility_count"] == 0

    async def test_annual_spend_is_12x_monthly(self):
        elec_rows = [{"price_per_kwh": 0.15, "supplier": "ACME"}]
        db = _make_db([elec_rows, [], [], []])
        service = OptimizationReportService(db)
        result = await service.generate_report("CT")

        assert abs(result["total_annual_spend"] - result["total_monthly_spend"] * 12) < 0.01


# =============================================================================
# 3. Electricity spend
# =============================================================================


class TestElectricitySpend:
    async def test_monthly_cost_calculation(self):
        rows = [{"price_per_kwh": 0.20, "supplier": "Test"}]
        db = _make_db([rows, [], [], []])
        service = OptimizationReportService(db)
        result = await service.generate_report("CT")

        elec = result["utilities"][0]
        assert elec["utility_type"] == "electricity"
        assert abs(elec["monthly_cost"] - 177.20) < 0.01

    async def test_savings_generated_when_price_spread(self):
        rows = [
            {"price_per_kwh": 0.25, "supplier": "Expensive"},
            {"price_per_kwh": 0.15, "supplier": "Cheap"},
        ]
        db = _make_db([rows, [], [], []])
        service = OptimizationReportService(db)
        result = await service.generate_report("CT")

        assert len(result["savings_opportunities"]) > 0
        opp = result["savings_opportunities"][0]
        assert opp["utility_type"] == "electricity"
        assert opp["monthly_savings"] > 0


# =============================================================================
# 4. Multi-utility aggregation
# =============================================================================


class TestMultiUtilityAggregation:
    async def test_utility_count_matches_data(self):
        elec_rows = [{"price_per_kwh": 0.15, "supplier": "A"}]
        gas_rows = [{"price_per_kwh": 1.20}]
        db = _make_db([elec_rows, gas_rows, [], []])
        service = OptimizationReportService(db)
        result = await service.generate_report("CT")

        assert result["utility_count"] == 2
        types = [u["utility_type"] for u in result["utilities"]]
        assert "electricity" in types
        assert "natural_gas" in types

    async def test_total_monthly_aggregates_all(self):
        elec_rows = [{"price_per_kwh": 0.15, "supplier": "A"}]
        gas_rows = [{"price_per_kwh": 1.50}]
        db = _make_db([elec_rows, gas_rows, [], []])
        service = OptimizationReportService(db)
        result = await service.generate_report("CT")

        expected = 0.15 * 886 + 1.50 * 50
        assert abs(result["total_monthly_spend"] - expected) < 1.0


# =============================================================================
# 5. Heating Oil & Propane spend
# =============================================================================


class TestHeatingOilSpend:
    async def test_heating_oil_cost_calculation(self):
        oil_rows = [{"price_per_gallon": 3.50}]
        db = _make_db([[], [], oil_rows, []])
        service = OptimizationReportService(db)
        result = await service.generate_report("CT")

        oil = result["utilities"][0]
        assert oil["utility_type"] == "heating_oil"
        assert abs(oil["monthly_cost"] - 234.50) < 0.01


class TestPropaneSpend:
    async def test_propane_cost_calculation(self):
        propane_rows = [{"price_per_gallon": 2.80}]
        db = _make_db([[], [], [], propane_rows])
        service = OptimizationReportService(db)
        result = await service.generate_report("CT")

        prop = result["utilities"][0]
        assert prop["utility_type"] == "propane"
        assert abs(prop["monthly_cost"] - 176.40) < 0.01
