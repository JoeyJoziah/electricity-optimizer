"""Tests for the Heating Oil API (backend/api/v1/heating_oil.py).

Covers:
- GET /rates/heating-oil (current prices, optionally by state)
- GET /rates/heating-oil/history (valid state, invalid state)
- GET /rates/heating-oil/dealers (valid state, invalid state)
- GET /rates/heating-oil/compare (with data, missing data)
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session


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


class TestGetCurrentPrices:
    def test_returns_prices_and_tracked_states(self, client):
        fake_prices = [{"state": "CT", "price_per_gallon": 3.85}]
        fake_states = ["CT", "MA", "NY"]
        with (
            patch(
                "services.heating_oil_service.HeatingOilService.get_current_prices",
                new=AsyncMock(return_value=fake_prices),
            ),
            patch(
                "services.heating_oil_service.HeatingOilService.get_tracked_states",
                return_value=fake_states,
            ),
        ):
            resp = client.get("/api/v1/rates/heating-oil")
        assert resp.status_code == 200
        body = resp.json()
        assert body["prices"] == fake_prices
        assert body["tracked_states"] == fake_states

    def test_filters_by_state_query_param(self, client):
        with (
            patch(
                "services.heating_oil_service.HeatingOilService.get_current_prices",
                new=AsyncMock(return_value=[]),
            ) as mock_get,
            patch(
                "services.heating_oil_service.HeatingOilService.get_tracked_states",
                return_value=["CT"],
            ),
        ):
            resp = client.get("/api/v1/rates/heating-oil?state=CT")
        assert resp.status_code == 200
        mock_get.assert_awaited_once()
        # First positional arg after self is the state
        args, _ = mock_get.call_args
        assert args[0] == "CT"


class TestGetHistory:
    def test_valid_state_returns_history_and_comparison(self, client):
        fake_history = [{"week": "2026-05-05", "price": 3.80}]
        fake_comparison = {"state_price": 3.85, "national_avg": 3.70}
        with (
            patch(
                "services.heating_oil_service.HeatingOilService.is_heating_oil_state",
                return_value=True,
            ),
            patch(
                "services.heating_oil_service.HeatingOilService.get_price_history",
                new=AsyncMock(return_value=fake_history),
            ),
            patch(
                "services.heating_oil_service.HeatingOilService.get_price_comparison",
                new=AsyncMock(return_value=fake_comparison),
            ),
        ):
            resp = client.get("/api/v1/rates/heating-oil/history?state=ct&weeks=8")
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "CT"
        assert body["weeks"] == 8
        assert body["history"] == fake_history
        assert body["comparison"] == fake_comparison

    def test_invalid_state_returns_404(self, client):
        with patch(
            "services.heating_oil_service.HeatingOilService.is_heating_oil_state",
            return_value=False,
        ):
            resp = client.get("/api/v1/rates/heating-oil/history?state=AZ")
        assert resp.status_code == 404
        assert "AZ" in resp.json()["detail"]

    def test_weeks_param_out_of_range_returns_422(self, client):
        resp = client.get("/api/v1/rates/heating-oil/history?state=CT&weeks=100")
        assert resp.status_code == 422


class TestGetDealers:
    def test_valid_state_returns_dealer_list(self, client):
        fake_dealers = [
            {"name": "Acme Oil", "phone": "555-0100"},
            {"name": "Bay Heating", "phone": "555-0101"},
        ]
        with (
            patch(
                "services.heating_oil_service.HeatingOilService.is_heating_oil_state",
                return_value=True,
            ),
            patch(
                "services.heating_oil_service.HeatingOilService.get_dealers",
                new=AsyncMock(return_value=fake_dealers),
            ),
        ):
            resp = client.get("/api/v1/rates/heating-oil/dealers?state=ma&limit=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "MA"
        assert body["count"] == 2
        assert body["dealers"] == fake_dealers

    def test_invalid_state_returns_404(self, client):
        with patch(
            "services.heating_oil_service.HeatingOilService.is_heating_oil_state",
            return_value=False,
        ):
            resp = client.get("/api/v1/rates/heating-oil/dealers?state=TX")
        assert resp.status_code == 404
        assert "TX" in resp.json()["detail"]

    def test_limit_param_out_of_range_returns_422(self, client):
        resp = client.get("/api/v1/rates/heating-oil/dealers?state=CT&limit=200")
        assert resp.status_code == 422


class TestComparePrice:
    def test_returns_comparison_when_data_exists(self, client):
        fake_comparison = {
            "state": "CT",
            "state_price": 3.85,
            "national_avg": 3.70,
            "delta_pct": 4.05,
        }
        with patch(
            "services.heating_oil_service.HeatingOilService.get_price_comparison",
            new=AsyncMock(return_value=fake_comparison),
        ):
            resp = client.get("/api/v1/rates/heating-oil/compare?state=CT")
        assert resp.status_code == 200
        assert resp.json() == fake_comparison

    def test_returns_404_when_no_data(self, client):
        with patch(
            "services.heating_oil_service.HeatingOilService.get_price_comparison",
            new=AsyncMock(return_value=None),
        ):
            resp = client.get("/api/v1/rates/heating-oil/compare?state=ZZ")
        assert resp.status_code == 404
        assert "ZZ" in resp.json()["detail"]
