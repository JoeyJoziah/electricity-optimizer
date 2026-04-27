"""
Unit tests for price_service.py (PriceService).

Tests the service-layer logic in isolation using a mocked PriceRepository.
API-layer coverage lives in test_prices_api.py; this file focuses on
internal method behaviour, delegation contracts, and edge cases.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.price import Price, PriceForecast, PriceRegion
from services.price_service import PriceService

# =============================================================================
# Fixtures
# =============================================================================


def _make_price(
    region: str = "us_ct",
    supplier: str = "Eversource Energy",
    price_per_kwh: str = "0.2100",
    source_api: str = "utility",
    is_peak: bool = False,
) -> Price:
    return Price(
        region=region,
        supplier=supplier,
        price_per_kwh=Decimal(price_per_kwh),
        timestamp=datetime.now(UTC),
        currency="USD",
        is_peak=is_peak,
        source_api=source_api,
    )


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get_current_prices = AsyncMock(return_value=[])
    repo.get_cheapest_price = AsyncMock(return_value=None)
    repo.get_latest_by_supplier = AsyncMock(return_value=None)
    repo.get_historical_prices = AsyncMock(return_value=[])
    repo.get_historical_prices_paginated = AsyncMock(return_value=([], 0))
    repo.get_price_statistics = AsyncMock(return_value={})
    repo._db = AsyncMock()
    return repo


@pytest.fixture
def service(mock_repo):
    return PriceService(price_repo=mock_repo)


# =============================================================================
# TestGetCurrentPrices
# =============================================================================


class TestGetCurrentPrices:
    """Tests for PriceService.get_current_prices()."""

    async def test_returns_prices_from_repo(self, service, mock_repo):
        prices = [_make_price(), _make_price(supplier="United Illuminating")]
        mock_repo.get_current_prices.return_value = prices

        result = await service.get_current_prices(PriceRegion.US_CT, limit=10)

        assert result == prices

    async def test_passes_limit_to_repo(self, service, mock_repo):
        mock_repo.get_current_prices.return_value = []

        await service.get_current_prices(PriceRegion.US_CT, limit=5)

        mock_repo.get_current_prices.assert_called_once_with(PriceRegion.US_CT, 5)

    async def test_empty_result_for_region_with_no_prices(self, service, mock_repo):
        mock_repo.get_current_prices.return_value = []

        result = await service.get_current_prices(PriceRegion.US_AK, limit=10)

        assert result == []

    async def test_default_limit_is_ten(self, service, mock_repo):
        mock_repo.get_current_prices.return_value = []

        await service.get_current_prices(PriceRegion.US_CT)

        _, called_limit = mock_repo.get_current_prices.call_args[0]
        assert called_limit == 10


# =============================================================================
# TestGetCurrentPrice (single supplier)
# =============================================================================


class TestGetCurrentPrice:
    """Tests for PriceService.get_current_price() — single-supplier lookup."""

    async def test_returns_price_when_found(self, service, mock_repo):
        price = _make_price()
        mock_repo.get_latest_by_supplier.return_value = price

        result = await service.get_current_price(PriceRegion.US_CT, "Eversource Energy")

        assert result is price

    async def test_returns_none_when_supplier_not_found(self, service, mock_repo):
        mock_repo.get_latest_by_supplier.return_value = None

        result = await service.get_current_price(PriceRegion.US_NY, "Unknown Supplier")

        assert result is None

    async def test_delegates_to_repo_get_latest_by_supplier(self, service, mock_repo):
        mock_repo.get_latest_by_supplier.return_value = None

        await service.get_current_price(PriceRegion.US_MA, "National Grid")

        mock_repo.get_latest_by_supplier.assert_called_once_with(PriceRegion.US_MA, "National Grid")


# =============================================================================
# TestGetCheapestSupplier
# =============================================================================


class TestGetCheapestSupplier:
    """Tests for PriceService.get_cheapest_supplier()."""

    async def test_returns_cheapest_price_from_repo(self, service, mock_repo):
        cheap = _make_price(price_per_kwh="0.1500")
        mock_repo.get_cheapest_price.return_value = cheap

        result = await service.get_cheapest_supplier(PriceRegion.US_CT)

        assert result is cheap

    async def test_returns_none_when_no_prices(self, service, mock_repo):
        mock_repo.get_cheapest_price.return_value = None

        result = await service.get_cheapest_supplier(PriceRegion.US_HI)

        assert result is None


# =============================================================================
# TestGetPriceComparison
# =============================================================================


class TestGetPriceComparison:
    """Tests for PriceService.get_price_comparison() — sorted output."""

    async def test_returns_prices_sorted_ascending(self, service, mock_repo):
        prices = [
            _make_price(supplier="SupplierC", price_per_kwh="0.30"),
            _make_price(supplier="SupplierA", price_per_kwh="0.10"),
            _make_price(supplier="SupplierB", price_per_kwh="0.20"),
        ]
        mock_repo.get_current_prices.return_value = prices

        result = await service.get_price_comparison(PriceRegion.US_CT)

        assert result[0].price_per_kwh < result[1].price_per_kwh < result[2].price_per_kwh

    async def test_empty_region_returns_empty_list(self, service, mock_repo):
        mock_repo.get_current_prices.return_value = []

        result = await service.get_price_comparison(PriceRegion.US_AK)

        assert result == []

    async def test_comparison_requests_up_to_50_from_repo(self, service, mock_repo):
        mock_repo.get_current_prices.return_value = []

        await service.get_price_comparison(PriceRegion.US_CT)

        call = mock_repo.get_current_prices.call_args
        # limit may be passed positionally or as keyword
        called_limit = call[0][1] if len(call[0]) > 1 else call[1].get("limit")
        assert called_limit == 50


# =============================================================================
# TestCalculateDailyCost
# =============================================================================


class TestCalculateDailyCost:
    """Tests for PriceService.calculate_daily_cost()."""

    async def test_uses_historical_price_when_available(self, service, mock_repo):
        price = _make_price(price_per_kwh="0.20")
        mock_repo.get_historical_prices.return_value = [price]

        result = await service.calculate_daily_cost(
            PriceRegion.US_CT, "Eversource Energy", Decimal("10"), datetime.now(UTC).date()
        )

        # 10 kWh * $0.20 = $2.00
        assert result == Decimal("2.00")

    async def test_falls_back_to_current_price_when_no_history(self, service, mock_repo):
        mock_repo.get_historical_prices.return_value = []
        mock_repo.get_latest_by_supplier.return_value = _make_price(price_per_kwh="0.25")

        result = await service.calculate_daily_cost(
            PriceRegion.US_CT, "Eversource Energy", Decimal("8"), datetime.now(UTC).date()
        )

        # 8 kWh * $0.25 = $2.00
        assert result == Decimal("2.00")

    async def test_returns_zero_when_no_prices_at_all(self, service, mock_repo):
        mock_repo.get_historical_prices.return_value = []
        mock_repo.get_latest_by_supplier.return_value = None

        result = await service.calculate_daily_cost(
            PriceRegion.US_CT, "UnknownSupplier", Decimal("5"), datetime.now(UTC).date()
        )

        assert result == Decimal("0")

    async def test_weighted_average_over_multiple_historical_prices(self, service, mock_repo):
        mock_repo.get_historical_prices.return_value = [
            _make_price(price_per_kwh="0.10"),
            _make_price(price_per_kwh="0.30"),
        ]

        result = await service.calculate_daily_cost(
            PriceRegion.US_CT, "Eversource Energy", Decimal("10"), datetime.now(UTC).date()
        )

        # avg price = (0.10 + 0.30) / 2 = 0.20 ; 10 * 0.20 = 2.00
        assert result == Decimal("2.00")


# =============================================================================
# TestSourceAttribution
# =============================================================================


class TestSourceAttribution:
    """Verify source_api field is preserved through the service layer."""

    async def test_source_api_preserved_for_utility_source(self, service, mock_repo):
        price = _make_price(source_api="eia_api")
        mock_repo.get_current_prices.return_value = [price]

        result = await service.get_current_prices(PriceRegion.US_CT, limit=1)

        assert result[0].source_api == "eia_api"

    async def test_source_api_preserved_for_scrape_source(self, service, mock_repo):
        price = _make_price(source_api="web_scraper")
        mock_repo.get_latest_by_supplier.return_value = price

        result = await service.get_current_price(PriceRegion.US_CT, "Eversource Energy")

        assert result.source_api == "web_scraper"


# =============================================================================
# TestSimpleForecast
# =============================================================================


class TestSimpleForecast:
    """Tests for PriceService._simple_forecast() (static heuristic)."""

    def test_forecast_length_matches_hours(self):
        now = datetime.now(UTC)
        result = PriceService._simple_forecast(
            PriceRegion.US_CT, 12, now, Decimal("0.20"), "Eversource", "USD"
        )
        assert result.horizon_hours == 12
        assert len(result.prices) == 12

    def test_peak_hours_have_higher_price(self):
        # Force time so hour 18 is within the forecast window
        now = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)  # noon — ensures hour 16-20 appears
        result = PriceService._simple_forecast(
            PriceRegion.US_CT, 24, now, Decimal("0.20"), "Eversource", "USD"
        )
        peak_prices = [p for p in result.prices if p.is_peak]
        off_peak_prices = [p for p in result.prices if not p.is_peak]

        assert peak_prices, "Expected at least one peak-hour price"
        assert off_peak_prices, "Expected at least one off-peak price"
        assert (
            min(p.price_per_kwh for p in peak_prices)
            > max(
                p.price_per_kwh
                for p in off_peak_prices
                if (p.timestamp.hour < 7)  # overnight off-peak (0.7x)
            )
            if any(p.timestamp.hour < 7 for p in off_peak_prices)
            else True
        )

    def test_confidence_is_07_for_simple_model(self):
        now = datetime.now(UTC)
        result = PriceService._simple_forecast(
            PriceRegion.US_CT, 6, now, Decimal("0.20"), "Eversource", "USD"
        )
        assert result.confidence == 0.7

    def test_model_version_is_simple_v1(self):
        now = datetime.now(UTC)
        result = PriceService._simple_forecast(
            PriceRegion.US_CT, 6, now, Decimal("0.20"), "Eversource", "USD"
        )
        assert result.model_version == "simple_v1"

    def test_forecast_uses_supplied_region(self):
        now = datetime.now(UTC)
        result = PriceService._simple_forecast(
            PriceRegion.US_MA, 4, now, Decimal("0.18"), "National Grid", "USD"
        )
        assert result.region == PriceRegion.US_MA


# =============================================================================
# TestGetPriceForecast — repo integration
# =============================================================================


class TestGetPriceForecast:
    """Tests for PriceService.get_price_forecast() in the simple-fallback path."""

    async def test_returns_none_when_no_current_prices(self, service, mock_repo):
        mock_repo.get_current_prices.return_value = []

        result = await service.get_price_forecast(PriceRegion.US_CT, hours=24)

        assert result is None

    async def test_returns_forecast_from_simple_heuristic_when_ml_unavailable(
        self, service, mock_repo
    ):
        mock_repo.get_current_prices.return_value = [_make_price()]

        with patch.object(service, "_try_ml_forecast", return_value=None):
            result = await service.get_price_forecast(PriceRegion.US_CT, hours=6)

        assert isinstance(result, PriceForecast)
        assert len(result.prices) == 6


# =============================================================================
# TestGetHistoricalPrices
# =============================================================================


class TestGetHistoricalPrices:
    """Tests for PriceService.get_historical_prices() — delegation contract."""

    async def test_delegates_to_repo_with_correct_params(self, service, mock_repo):
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 1, 31, tzinfo=UTC)
        mock_repo.get_historical_prices.return_value = []

        await service.get_historical_prices(PriceRegion.US_CT, start, end, supplier="Eversource")

        mock_repo.get_historical_prices.assert_called_once_with(
            region=PriceRegion.US_CT,
            start_date=start,
            end_date=end,
            supplier="Eversource",
        )

    async def test_returns_prices_from_repo(self, service, mock_repo):
        prices = [_make_price(), _make_price()]
        mock_repo.get_historical_prices.return_value = prices
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 1, 31, tzinfo=UTC)

        result = await service.get_historical_prices(PriceRegion.US_CT, start, end)

        assert result == prices
