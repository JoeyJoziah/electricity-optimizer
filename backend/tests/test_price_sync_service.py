"""
Tests for price_sync_service.sync_prices

Covers:
- Happy path: full sync with mocked pricing service and DB
- DEFAULT_REGIONS used when no regions argument given
- Custom regions list passed through
- RateLimitError → status=partial, error recorded
- APIError → status=partial, error recorded
- Generic Exception → status=partial, error recorded
- Empty comparison dict → synced_records=0, status=partial
- prices_to_store populated but session is None → no DB write
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# HELPERS
# =============================================================================


def _make_price_data(region_value: str = "us_ct", price: float = 0.28):
    """Build a minimal PriceData-like mock that has a .convert_to_kwh() method."""
    kwh = MagicMock()
    kwh.supplier = "Eversource Energy"
    kwh.price = Decimal(str(price))
    kwh.timestamp = datetime(2026, 2, 24, 10, 0, tzinfo=timezone.utc)
    kwh.currency = "USD"
    kwh.is_peak = False
    kwh.carbon_intensity = 180.5
    kwh.source_api = "nrel"

    pd = MagicMock()
    pd.convert_to_kwh.return_value = kwh
    return pd


def _make_region_mock(value: str):
    """Build a minimal PricingRegion-like mock."""
    r = MagicMock()
    r.value = value
    return r


def _make_async_pricing_service(comparison: dict | None = None):
    """
    Return a mock PricingService that supports `async with` and .compare_prices().
    """
    svc = AsyncMock()
    svc.__aenter__ = AsyncMock(return_value=svc)
    svc.__aexit__ = AsyncMock(return_value=False)
    svc.compare_prices = AsyncMock(return_value=comparison or {})
    return svc


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db():
    return AsyncMock()


# =============================================================================
# Tests
# =============================================================================


class TestSyncPrices:
    """Tests for services.price_sync_service.sync_prices"""

    @pytest.mark.asyncio
    async def test_sync_prices_success(self, mock_db):
        """Full sync: 3 regions → 3 Price objects inserted, status=refreshed."""
        region_ct = _make_region_mock("us_ct")
        region_ny = _make_region_mock("us_ny")
        region_ca = _make_region_mock("us_ca")

        comparison = {
            region_ct: _make_price_data("us_ct", 0.28),
            region_ny: _make_price_data("us_ny", 0.25),
            region_ca: _make_price_data("us_ca", 0.22),
        }

        mock_pricing_svc = _make_async_pricing_service(comparison)
        mock_repo = AsyncMock()
        mock_repo.bulk_create = AsyncMock(return_value=3)

        with (
            patch(
                "services.price_sync_service.create_pricing_service_from_settings",
                return_value=mock_pricing_svc,
            ),
            patch(
                "services.price_sync_service.PriceRepository",
                return_value=mock_repo,
            ),
        ):
            from services.price_sync_service import sync_prices

            result = await sync_prices(mock_db)

        assert result["status"] == "refreshed"
        assert result["synced_records"] == 3
        assert len(result["regions_covered"]) == 3
        assert result["errors"] is None

    @pytest.mark.asyncio
    async def test_sync_prices_default_regions(self, mock_db):
        """When regions=None, DEFAULT_REGIONS is passed to compare_prices."""
        mock_pricing_svc = _make_async_pricing_service({})

        with (
            patch(
                "services.price_sync_service.create_pricing_service_from_settings",
                return_value=mock_pricing_svc,
            ),
        ):
            from services.price_sync_service import sync_prices, DEFAULT_REGIONS

            await sync_prices(mock_db, regions=None)

        mock_pricing_svc.compare_prices.assert_awaited_once_with(DEFAULT_REGIONS)

    @pytest.mark.asyncio
    async def test_sync_prices_custom_regions(self, mock_db):
        """Custom regions list is forwarded verbatim to compare_prices."""
        mock_pricing_svc = _make_async_pricing_service({})

        from models.region import Region

        custom = [Region.US_CT, Region.UK]

        with (
            patch(
                "services.price_sync_service.create_pricing_service_from_settings",
                return_value=mock_pricing_svc,
            ),
        ):
            from services.price_sync_service import sync_prices

            await sync_prices(mock_db, regions=custom)

        mock_pricing_svc.compare_prices.assert_awaited_once_with(custom)

    @pytest.mark.asyncio
    async def test_sync_prices_rate_limit_error(self, mock_db):
        """RateLimitError is caught — status=partial, error message captured."""
        from integrations.pricing_apis.base import RateLimitError

        mock_pricing_svc = AsyncMock()
        mock_pricing_svc.__aenter__ = AsyncMock(return_value=mock_pricing_svc)
        mock_pricing_svc.__aexit__ = AsyncMock(return_value=False)
        mock_pricing_svc.compare_prices = AsyncMock(
            side_effect=RateLimitError("Too fast", retry_after=60)
        )

        # price_sync_service uses structlog; patch the module-level logger so
        # keyword-argument calls like logger.warning("msg", error=...) don't
        # fail against a stdlib Logger that rejects unknown kwargs.
        mock_logger = MagicMock()

        with (
            patch(
                "services.price_sync_service.create_pricing_service_from_settings",
                return_value=mock_pricing_svc,
            ),
            patch("services.price_sync_service.logger", mock_logger),
        ):
            from services.price_sync_service import sync_prices

            result = await sync_prices(mock_db)

        assert result["status"] == "partial"
        assert result["synced_records"] == 0
        assert result["errors"] is not None
        assert any("Rate limited" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_sync_prices_api_error(self, mock_db):
        """APIError is caught — status=partial, error message captured."""
        from integrations.pricing_apis.base import APIError

        mock_pricing_svc = AsyncMock()
        mock_pricing_svc.__aenter__ = AsyncMock(return_value=mock_pricing_svc)
        mock_pricing_svc.__aexit__ = AsyncMock(return_value=False)
        mock_pricing_svc.compare_prices = AsyncMock(
            side_effect=APIError("Upstream failure", status_code=502)
        )

        mock_logger = MagicMock()

        with (
            patch(
                "services.price_sync_service.create_pricing_service_from_settings",
                return_value=mock_pricing_svc,
            ),
            patch("services.price_sync_service.logger", mock_logger),
        ):
            from services.price_sync_service import sync_prices

            result = await sync_prices(mock_db)

        assert result["status"] == "partial"
        assert result["errors"] is not None
        assert any("API error" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_sync_prices_unexpected_error(self, mock_db):
        """Generic Exception is caught — status=partial, error recorded."""
        mock_pricing_svc = AsyncMock()
        mock_pricing_svc.__aenter__ = AsyncMock(return_value=mock_pricing_svc)
        mock_pricing_svc.__aexit__ = AsyncMock(return_value=False)
        mock_pricing_svc.compare_prices = AsyncMock(
            side_effect=RuntimeError("Connection reset")
        )

        mock_logger = MagicMock()

        with (
            patch(
                "services.price_sync_service.create_pricing_service_from_settings",
                return_value=mock_pricing_svc,
            ),
            patch("services.price_sync_service.logger", mock_logger),
        ):
            from services.price_sync_service import sync_prices

            result = await sync_prices(mock_db)

        assert result["status"] == "partial"
        assert result["errors"] is not None
        assert any("Unexpected error" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_sync_prices_empty_comparison(self, mock_db):
        """Empty comparison dict → no prices stored, status=partial."""
        mock_pricing_svc = _make_async_pricing_service({})

        with patch(
            "services.price_sync_service.create_pricing_service_from_settings",
            return_value=mock_pricing_svc,
        ):
            from services.price_sync_service import sync_prices

            result = await sync_prices(mock_db)

        assert result["status"] == "partial"
        assert result["synced_records"] == 0
        assert result["regions_covered"] == []

    @pytest.mark.asyncio
    async def test_sync_prices_no_session(self):
        """When session is None, DB write is skipped even if prices are available."""
        region_ct = _make_region_mock("us_ct")
        comparison = {region_ct: _make_price_data("us_ct", 0.28)}
        mock_pricing_svc = _make_async_pricing_service(comparison)

        mock_repo = AsyncMock()
        mock_repo.bulk_create = AsyncMock(return_value=1)

        with (
            patch(
                "services.price_sync_service.create_pricing_service_from_settings",
                return_value=mock_pricing_svc,
            ),
            patch(
                "services.price_sync_service.PriceRepository",
                return_value=mock_repo,
            ),
        ):
            from services.price_sync_service import sync_prices

            result = await sync_prices(session=None)

        # Session was None so bulk_create must NOT have been called
        mock_repo.bulk_create.assert_not_awaited()
        assert result["synced_records"] == 0
        assert result["status"] == "partial"
