"""Tests for the Gas Rates API (backend/api/v1/gas_rates.py).

Mounted at: /api/v1/rates/natural-gas

Covers:
- GET /rates/natural-gas/           (region required, limit param, deregulated flag)
- GET /rates/natural-gas/history    (region + days bounds)
- GET /rates/natural-gas/stats      (region + days bounds)
- GET /rates/natural-gas/deregulated-states
- GET /rates/natural-gas/compare    (deregulated vs regulated region, empty data)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session

_BASE = "/api/v1/rates/natural-gas"


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def client(mock_db):
    from main import app

    app.dependency_overrides[get_db_session] = lambda: mock_db
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_price(supplier="Eversource", price=0.85, unit="therm", source="EIA"):
    m = MagicMock()
    m.id = "p-001"
    m.supplier = supplier
    m.price_per_kwh = price
    m.unit = unit
    m.timestamp = MagicMock()
    m.timestamp.isoformat.return_value = "2026-05-14T12:00:00"
    m.source_api = source
    return m


# ---------------------------------------------------------------------------
# GET /rates/natural-gas/
# ---------------------------------------------------------------------------


class TestGetGasRates:
    def test_returns_prices_for_region(self, client):
        fake_prices = [_make_price("UIL", 0.90), _make_price("Eversource", 0.85)]
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_prices",
            new=AsyncMock(return_value=fake_prices),
        ):
            resp = client.get(f"{_BASE}/?region=us_ct")
        assert resp.status_code == 200
        body = resp.json()
        assert body["region"] == "us_ct"
        assert body["utility_type"] == "natural_gas"
        assert body["count"] == 2
        assert len(body["prices"]) == 2

    def test_missing_region_returns_422(self, client):
        resp = client.get(f"{_BASE}/")
        assert resp.status_code == 422

    def test_deregulated_flag_set_for_ct(self, client):
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_prices",
            new=AsyncMock(return_value=[]),
        ):
            resp = client.get(f"{_BASE}/?region=us_ct")
        assert resp.status_code == 200
        assert resp.json()["is_deregulated"] is True

    def test_deregulated_flag_false_for_non_deregulated_state(self, client):
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_prices",
            new=AsyncMock(return_value=[]),
        ):
            resp = client.get(f"{_BASE}/?region=us_ca")
        assert resp.status_code == 200
        assert resp.json()["is_deregulated"] is False

    def test_limit_param_within_bounds(self, client):
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_prices",
            new=AsyncMock(return_value=[]),
        ) as mock_svc:
            resp = client.get(f"{_BASE}/?region=us_ct&limit=5")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(region="us_ct", limit=5)

    def test_limit_over_100_returns_422(self, client):
        resp = client.get(f"{_BASE}/?region=us_ct&limit=101")
        assert resp.status_code == 422

    def test_empty_prices_returns_200(self, client):
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_prices",
            new=AsyncMock(return_value=[]),
        ):
            resp = client.get(f"{_BASE}/?region=us_ct")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# GET /rates/natural-gas/history
# ---------------------------------------------------------------------------


class TestGetGasHistory:
    def test_returns_history_for_region(self, client):
        fake = [_make_price()]
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_price_history",
            new=AsyncMock(return_value=fake),
        ):
            resp = client.get(f"{_BASE}/history?region=us_ct")
        assert resp.status_code == 200
        body = resp.json()
        assert body["region"] == "us_ct"
        assert body["count"] == 1

    def test_missing_region_returns_422(self, client):
        resp = client.get(f"{_BASE}/history")
        assert resp.status_code == 422

    def test_days_max_boundary_365(self, client):
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_price_history",
            new=AsyncMock(return_value=[]),
        ):
            resp = client.get(f"{_BASE}/history?region=us_ct&days=365")
        assert resp.status_code == 200

    def test_days_over_max_returns_422(self, client):
        resp = client.get(f"{_BASE}/history?region=us_ct&days=366")
        assert resp.status_code == 422

    def test_days_zero_returns_422(self, client):
        resp = client.get(f"{_BASE}/history?region=us_ct&days=0")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /rates/natural-gas/stats
# ---------------------------------------------------------------------------


class TestGetGasStats:
    def test_returns_stats_for_region(self, client):
        fake_stats = {"average": 0.87, "min": 0.80, "max": 0.95, "trend": "stable"}
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_stats",
            new=AsyncMock(return_value=fake_stats),
        ):
            resp = client.get(f"{_BASE}/stats?region=us_ct")
        assert resp.status_code == 200
        body = resp.json()
        assert body["region"] == "us_ct"
        assert body["utility_type"] == "natural_gas"
        assert body["average"] == 0.87

    def test_missing_region_returns_422(self, client):
        resp = client.get(f"{_BASE}/stats")
        assert resp.status_code == 422

    def test_days_default_7(self, client):
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_stats",
            new=AsyncMock(return_value={}),
        ) as mock_svc:
            resp = client.get(f"{_BASE}/stats?region=us_ct")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(region="us_ct", days=7)

    def test_days_max_90(self, client):
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_stats",
            new=AsyncMock(return_value={}),
        ):
            resp = client.get(f"{_BASE}/stats?region=us_ct&days=90")
        assert resp.status_code == 200

    def test_days_over_90_returns_422(self, client):
        resp = client.get(f"{_BASE}/stats?region=us_ct&days=91")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /rates/natural-gas/deregulated-states
# ---------------------------------------------------------------------------


class TestDeregulatedStates:
    def test_returns_state_list(self, client):
        fake_states = ["CT", "NY", "NJ", "OH", "PA"]
        with patch(
            "services.gas_rate_service.GasRateService.get_deregulated_states",
            new=AsyncMock(return_value=fake_states),
        ):
            resp = client.get(f"{_BASE}/deregulated-states")
        assert resp.status_code == 200
        body = resp.json()
        assert "states" in body
        assert body["count"] == 5
        assert "CT" in body["states"]


# ---------------------------------------------------------------------------
# GET /rates/natural-gas/compare
# ---------------------------------------------------------------------------


class TestCompareGasSuppliers:
    def test_deregulated_region_returns_suppliers(self, client):
        fake_prices = [
            _make_price("SupplierA", 0.80),
            _make_price("SupplierB", 0.90),
        ]
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_prices",
            new=AsyncMock(return_value=fake_prices),
        ):
            resp = client.get(f"{_BASE}/compare?region=us_ct")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_deregulated"] is True
        assert len(body["suppliers"]) == 2
        assert body["cheapest"] == "SupplierA"

    def test_regulated_region_returns_400(self, client):
        resp = client.get(f"{_BASE}/compare?region=us_ca")
        assert resp.status_code == 400

    def test_deregulated_region_empty_data_returns_message(self, client):
        with patch(
            "services.gas_rate_service.GasRateService.get_gas_prices",
            new=AsyncMock(return_value=[]),
        ):
            resp = client.get(f"{_BASE}/compare?region=us_ct")
        assert resp.status_code == 200
        body = resp.json()
        assert body["suppliers"] == []
        assert "message" in body

    def test_missing_region_returns_422(self, client):
        resp = client.get(f"{_BASE}/compare")
        assert resp.status_code == 422
