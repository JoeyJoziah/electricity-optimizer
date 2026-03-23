"""
Tests for WaterRateService — rates, tier calculator, benchmarking, tips, upsert.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.water_rate_service import (
    WaterRateService,
)


def _mock_db_rows(rows):
    """Create a mock async db result."""
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.all.return_value = rows
    mock_mappings.first.return_value = rows[0] if rows else None
    mock_result.mappings.return_value = mock_mappings
    return mock_result


def _mock_db_fetchone(row):
    """Create a mock async db result with fetchone."""
    mock_result = MagicMock()
    mock_result.fetchone.return_value = row
    return mock_result


SAMPLE_RATE_ROW = {
    "id": "uuid-1",
    "municipality": "New York",
    "state": "NY",
    "rate_tiers": [
        {"limit_gallons": 3000, "rate_per_gallon": 0.004},
        {"limit_gallons": 6000, "rate_per_gallon": 0.006},
        {"limit_gallons": None, "rate_per_gallon": 0.009},
    ],
    "base_charge": Decimal("15.50"),
    "unit": "gallon",
    "effective_date": date(2026, 1, 1),
    "source_url": "https://www1.nyc.gov/water-rates",
    "updated_at": datetime(2026, 3, 1, tzinfo=UTC),
}

SAMPLE_RATE_ROW_2 = {
    "id": "uuid-2",
    "municipality": "Buffalo",
    "state": "NY",
    "rate_tiers": [
        {"limit_gallons": 4000, "rate_per_gallon": 0.005},
        {"limit_gallons": None, "rate_per_gallon": 0.008},
    ],
    "base_charge": Decimal("12.00"),
    "unit": "gallon",
    "effective_date": date(2026, 1, 1),
    "source_url": "https://buffalo.gov/water",
    "updated_at": datetime(2026, 3, 1, tzinfo=UTC),
}


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return WaterRateService(mock_db)


# ------------------------------------------------------------------
# get_rates
# ------------------------------------------------------------------


class TestGetRates:
    async def test_returns_all_rates(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows([SAMPLE_RATE_ROW, SAMPLE_RATE_ROW_2])

        rates = await service.get_rates()
        assert len(rates) == 2
        assert rates[0]["municipality"] == "New York"
        assert rates[0]["state"] == "NY"
        assert rates[0]["base_charge"] == 15.50

    async def test_filters_by_state(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows([SAMPLE_RATE_ROW])

        rates = await service.get_rates("ny")
        assert len(rates) == 1
        assert rates[0]["state"] == "NY"

    async def test_empty_result(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows([])
        rates = await service.get_rates("ZZ")
        assert rates == []


# ------------------------------------------------------------------
# get_rate_by_municipality
# ------------------------------------------------------------------


class TestGetRateByMunicipality:
    async def test_finds_municipality(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows([SAMPLE_RATE_ROW])

        rate = await service.get_rate_by_municipality("New York", "NY")
        assert rate is not None
        assert rate["municipality"] == "New York"
        assert len(rate["rate_tiers"]) == 3

    async def test_returns_none_when_not_found(self, service, mock_db):
        mock_result = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.first.return_value = None
        mock_result.mappings.return_value = mock_mappings
        mock_db.execute.return_value = mock_result

        rate = await service.get_rate_by_municipality("Atlantis", "ZZ")
        assert rate is None


# ------------------------------------------------------------------
# calculate_monthly_cost (tier calculator)
# ------------------------------------------------------------------


class TestCalculateMonthlyCost:
    def test_basic_tiered_calculation(self, service):
        rate = {
            "municipality": "New York",
            "state": "NY",
            "rate_tiers": [
                {"limit_gallons": 3000, "rate_per_gallon": 0.004},
                {"limit_gallons": 6000, "rate_per_gallon": 0.006},
                {"limit_gallons": None, "rate_per_gallon": 0.009},
            ],
            "base_charge": 15.50,
        }

        result = service.calculate_monthly_cost(rate, 5000)
        assert result["municipality"] == "New York"
        assert result["usage_gallons"] == 5000
        assert result["base_charge"] == 15.50
        # Tier 1: 3000 * 0.004 = 12.00
        # Tier 2: 2000 * 0.006 = 12.00
        # Total tier charges: 24.00
        assert result["tier_charges"] == 24.00
        assert result["total_monthly"] == 39.50
        assert len(result["breakdown"]) == 2

    def test_usage_within_first_tier(self, service):
        rate = {
            "municipality": "Test City",
            "state": "TX",
            "rate_tiers": [
                {"limit_gallons": 5000, "rate_per_gallon": 0.005},
                {"limit_gallons": None, "rate_per_gallon": 0.010},
            ],
            "base_charge": 10.00,
        }

        result = service.calculate_monthly_cost(rate, 2000)
        # Only first tier: 2000 * 0.005 = 10.00
        assert result["tier_charges"] == 10.00
        assert result["total_monthly"] == 20.00
        assert len(result["breakdown"]) == 1

    def test_usage_exceeds_all_tiers(self, service):
        rate = {
            "municipality": "Big City",
            "state": "CA",
            "rate_tiers": [
                {"limit_gallons": 2000, "rate_per_gallon": 0.003},
                {"limit_gallons": 5000, "rate_per_gallon": 0.006},
                {"limit_gallons": None, "rate_per_gallon": 0.010},
            ],
            "base_charge": 20.00,
        }

        result = service.calculate_monthly_cost(rate, 8000)
        # Tier 1: 2000 * 0.003 = 6.00
        # Tier 2: 3000 * 0.006 = 18.00
        # Tier 3: 3000 * 0.010 = 30.00
        # Total tier charges: 54.00
        assert result["tier_charges"] == 54.00
        assert result["total_monthly"] == 74.00
        assert len(result["breakdown"]) == 3

    def test_zero_usage(self, service):
        rate = {
            "municipality": "Test",
            "state": "TX",
            "rate_tiers": [
                {"limit_gallons": 3000, "rate_per_gallon": 0.005},
            ],
            "base_charge": 10.00,
        }

        result = service.calculate_monthly_cost(rate, 0)
        assert result["tier_charges"] == 0
        assert result["total_monthly"] == 10.00

    def test_no_tiers(self, service):
        rate = {
            "municipality": "Flat Rate",
            "state": "OH",
            "rate_tiers": [],
            "base_charge": 25.00,
        }

        result = service.calculate_monthly_cost(rate, 5000)
        assert result["tier_charges"] == 0
        assert result["total_monthly"] == 25.00
        assert result["breakdown"] == []


# ------------------------------------------------------------------
# get_benchmark
# ------------------------------------------------------------------


class TestGetBenchmark:
    async def test_returns_benchmark_with_rates(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows([SAMPLE_RATE_ROW, SAMPLE_RATE_ROW_2])

        benchmark = await service.get_benchmark("NY")
        assert benchmark["state"] == "NY"
        assert benchmark["municipalities"] == 2
        assert benchmark["avg_monthly_cost"] is not None
        assert benchmark["min_monthly_cost"] is not None
        assert benchmark["max_monthly_cost"] is not None
        assert len(benchmark["rates"]) == 2
        # Rates should be sorted by monthly_cost
        assert benchmark["rates"][0]["monthly_cost"] <= benchmark["rates"][1]["monthly_cost"]

    async def test_no_data_returns_empty(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_rows([])

        benchmark = await service.get_benchmark("ZZ")
        assert benchmark["municipalities"] == 0
        assert benchmark["avg_monthly_cost"] is None
        assert benchmark["rates"] == []


# ------------------------------------------------------------------
# get_conservation_tips
# ------------------------------------------------------------------


class TestConservationTips:
    def test_returns_tips(self):
        tips = WaterRateService.get_conservation_tips()
        assert len(tips) == 8
        assert all("title" in t for t in tips)
        assert all("category" in t for t in tips)
        assert all("estimated_savings_gallons" in t for t in tips)

    def test_tips_have_indoor_and_outdoor(self):
        tips = WaterRateService.get_conservation_tips()
        categories = {t["category"] for t in tips}
        assert "Indoor" in categories
        assert "Outdoor" in categories


# ------------------------------------------------------------------
# upsert_rate
# ------------------------------------------------------------------


class TestUpsertRate:
    async def test_upserts_rate(self, service, mock_db):
        mock_db.execute.return_value = _mock_db_fetchone(("uuid-new",))

        rate_id = await service.upsert_rate(
            {
                "municipality": "Austin",
                "state": "TX",
                "rate_tiers": '[{"limit_gallons": 3000, "rate_per_gallon": 0.005}]',
                "base_charge": 12.00,
                "effective_date": "2026-01-01",
                "source_url": "https://austintexas.gov/water",
            }
        )
        assert rate_id == "uuid-new"
        mock_db.commit.assert_called_once()


# ------------------------------------------------------------------
# _format_rate
# ------------------------------------------------------------------


class TestFormatRate:
    def test_formats_row_correctly(self):
        formatted = WaterRateService._format_rate(SAMPLE_RATE_ROW)
        assert formatted["id"] == "uuid-1"
        assert formatted["municipality"] == "New York"
        assert formatted["base_charge"] == 15.50
        assert formatted["effective_date"] == "2026-01-01"
        assert len(formatted["rate_tiers"]) == 3

    def test_handles_none_dates(self):
        row = {**SAMPLE_RATE_ROW, "effective_date": None, "updated_at": None}
        formatted = WaterRateService._format_rate(row)
        assert formatted["effective_date"] is None
        assert formatted["updated_at"] is None
