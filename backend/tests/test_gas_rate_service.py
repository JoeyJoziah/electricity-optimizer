"""
Tests for Gas Rate Service and API endpoints.

Covers:
- GasRateService: fetch, store, query gas prices
- GET /rates/natural-gas — current gas rates
- GET /rates/natural-gas/history — gas price history
- GET /rates/natural-gas/stats — gas statistics
- GET /rates/natural-gas/deregulated-states — deregulated states list
- GET /rates/natural-gas/compare — gas supplier comparison
- POST /internal/fetch-gas-rates — internal cron endpoint
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session, verify_api_key

BASE_URL = "/api/v1/rates/natural-gas"
INTERNAL_URL = "/api/v1/internal"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def client(mock_db):
    """TestClient with mocked DB session."""
    from main import app

    app.dependency_overrides[get_db_session] = lambda: mock_db
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def auth_internal_client(mock_db):
    """TestClient with API key verified for internal endpoints."""
    from main import app

    app.dependency_overrides[verify_api_key] = lambda: True
    app.dependency_overrides[get_db_session] = lambda: mock_db
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_db_session, None)


# =============================================================================
# GasRateService Unit Tests
# =============================================================================


class TestGasRateService:
    """Unit tests for the GasRateService."""

    async def test_fetch_gas_rates_success(self):
        """Fetching gas rates stores prices for each state."""
        from integrations.pricing_apis.base import (PriceData, PriceUnit,
                                                    PricingRegion)
        from services.gas_rate_service import GasRateService

        mock_db = AsyncMock()
        mock_eia = AsyncMock()
        mock_eia.get_gas_price = AsyncMock(
            return_value=PriceData(
                region=PricingRegion.US_CT,
                timestamp=datetime.now(UTC),
                price=Decimal("1.2345"),
                unit=PriceUnit.THERM,
                currency="USD",
                supplier=None,
                source_api="eia",
            )
        )

        service = GasRateService(db=mock_db, eia_client=mock_eia)
        result = await service.fetch_gas_rates(states=["CT", "PA"])

        assert result["fetched"] == 2
        assert result["stored"] == 2
        assert result["errors"] == 0
        assert len(result["details"]) == 2

    async def test_fetch_gas_rates_partial_failure(self):
        """Partial failure should not crash the entire batch."""
        from integrations.pricing_apis.base import (APIError, PriceData,
                                                    PriceUnit)
        from services.gas_rate_service import GasRateService

        mock_db = AsyncMock()
        mock_eia = AsyncMock()

        call_count = 0

        async def mock_get_gas(region):
            nonlocal call_count
            call_count += 1
            if "pa" in region.value:
                raise APIError("No gas data for PA", api_name="eia")
            return PriceData(
                region=region,
                timestamp=datetime.now(UTC),
                price=Decimal("1.5000"),
                unit=PriceUnit.THERM,
                currency="USD",
                supplier=None,
                source_api="eia",
            )

        mock_eia.get_gas_price = mock_get_gas

        service = GasRateService(db=mock_db, eia_client=mock_eia)
        result = await service.fetch_gas_rates(states=["CT", "PA"])

        assert result["fetched"] == 1
        assert result["errors"] == 1

    async def test_fetch_gas_rates_no_client_raises(self):
        """Missing EIA client should raise RuntimeError."""
        from services.gas_rate_service import GasRateService

        service = GasRateService(db=AsyncMock(), eia_client=None)
        with pytest.raises(RuntimeError, match="EIA client not configured"):
            await service.fetch_gas_rates()

    async def test_get_gas_prices_delegates_to_repo(self):
        """get_gas_prices should call PriceRepository with NATURAL_GAS."""
        from models.utility import UtilityType
        from services.gas_rate_service import GasRateService

        mock_db = AsyncMock()
        service = GasRateService(db=mock_db)

        with patch.object(
            service._price_repo, "get_current_prices", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = []
            result = await service.get_gas_prices(region="us_ct")
            mock_get.assert_awaited_once_with(
                region="us_ct",
                limit=10,
                utility_type=UtilityType.NATURAL_GAS,
            )

    async def test_get_deregulated_states_queries_db(self):
        """get_deregulated_states should query state_regulations."""
        from services.gas_rate_service import GasRateService

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {
                "state_code": "CT",
                "state_name": "Connecticut",
                "puc_name": "PURA",
                "puc_website": "https://portal.ct.gov/pura",
                "comparison_tool_url": None,
            },
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = GasRateService(db=mock_db)
        states = await service.get_deregulated_states()

        assert len(states) == 1
        assert states[0]["state_code"] == "CT"


# =============================================================================
# Public API Tests
# =============================================================================


class TestGasRatesAPI:
    """Tests for public gas rate endpoints."""

    def test_get_gas_rates(self, client, mock_db):
        """GET /rates/natural-gas returns gas prices for a region."""
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"{BASE_URL}/?region=us_ct")

        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "us_ct"
        assert data["utility_type"] == "natural_gas"
        assert data["is_deregulated"] is True

    def test_get_gas_rates_non_deregulated(self, client, mock_db):
        """Non-deregulated state should return is_deregulated=False."""
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"{BASE_URL}/?region=us_ca")

        assert response.status_code == 200
        data = response.json()
        assert data["is_deregulated"] is False

    def test_get_gas_rates_missing_region(self, client):
        """Missing region param should return 422."""
        response = client.get(f"{BASE_URL}/")
        assert response.status_code == 422

    def test_get_gas_history(self, client, mock_db):
        """GET /rates/natural-gas/history returns price history."""
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"{BASE_URL}/history?region=us_ct&days=30")

        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 30

    def test_get_gas_stats(self, client, mock_db):
        """GET /rates/natural-gas/stats returns statistics."""
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = {
            "avg_price": Decimal("1.25"),
            "min_price": Decimal("1.10"),
            "max_price": Decimal("1.40"),
            "count": 5,
        }
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"{BASE_URL}/stats?region=us_ct")

        assert response.status_code == 200
        data = response.json()
        assert data["utility_type"] == "natural_gas"

    def test_get_deregulated_states(self, client, mock_db):
        """GET /rates/natural-gas/deregulated-states returns states."""
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {
                "state_code": "CT",
                "state_name": "Connecticut",
                "puc_name": "PURA",
                "puc_website": None,
                "comparison_tool_url": None,
            },
            {
                "state_code": "OH",
                "state_name": "Ohio",
                "puc_name": "PUCO",
                "puc_website": None,
                "comparison_tool_url": None,
            },
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"{BASE_URL}/deregulated-states")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2

    def test_compare_deregulated_state(self, client, mock_db):
        """GET /rates/natural-gas/compare for deregulated state."""
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"{BASE_URL}/compare?region=us_ct")

        assert response.status_code == 200
        data = response.json()
        assert data["is_deregulated"] is True

    def test_compare_non_deregulated_returns_400(self, client):
        """GET /rates/natural-gas/compare for non-deregulated state returns 400."""
        response = client.get(f"{BASE_URL}/compare?region=us_ca")

        assert response.status_code == 400
        assert "deregulated" in response.json()["detail"].lower()


# =============================================================================
# Internal API Tests
# =============================================================================


class TestInternalFetchGasRates:
    """Tests for POST /internal/fetch-gas-rates."""

    @patch("config.settings.get_settings")
    def test_fetch_gas_rates_no_api_key(self, mock_settings, auth_internal_client):
        """Missing EIA API key should return 503."""
        mock_cfg = MagicMock()
        mock_cfg.eia_api_key = None
        mock_settings.return_value = mock_cfg

        response = auth_internal_client.post(f"{INTERNAL_URL}/fetch-gas-rates")
        assert response.status_code == 503

    def test_fetch_gas_rates_requires_api_key(self, mock_db):
        """Request without X-API-Key should be rejected."""
        from main import app

        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides[get_db_session] = lambda: mock_db

        c = TestClient(app)
        response = c.post(f"{INTERNAL_URL}/fetch-gas-rates")
        assert response.status_code == 401

        app.dependency_overrides.pop(get_db_session, None)
