"""Tests for the Propane API (backend/api/v1/propane.py).

Mounted at: /api/v1/rates/propane (public, no auth)

Covers:
- GET /rates/propane              (all prices; optional state filter)
- GET /rates/propane/history      (valid state, invalid state → 404, weeks bounds)
- GET /rates/propane/compare      (found, not found → 404)
- GET /rates/propane/timing       (valid state, invalid state → 404)
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session

_BASE = "/api/v1/rates/propane"


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
# GET /rates/propane
# ---------------------------------------------------------------------------

_PRICES_PAYLOAD = [
    {"state": "CT", "price_per_gallon": 2.85, "week_ending": "2026-05-10"},
    {"state": "MA", "price_per_gallon": 2.90, "week_ending": "2026-05-10"},
]
_TRACKED_STATES = ["CT", "MA", "NY", "PA", "ME"]


class TestGetPropanePrices:
    def test_returns_all_prices_and_tracked_states(self, client):
        with (
            patch(
                "services.propane_service.PropaneService.get_current_prices",
                new=AsyncMock(return_value=_PRICES_PAYLOAD),
            ),
            patch(
                "services.propane_service.PropaneService.get_tracked_states",
                return_value=_TRACKED_STATES,
            ),
        ):
            resp = client.get(_BASE)
        assert resp.status_code == 200
        body = resp.json()
        assert body["prices"] == _PRICES_PAYLOAD
        assert set(body["tracked_states"]) == set(_TRACKED_STATES)

    def test_filters_by_state_query_param(self, client):
        with (
            patch(
                "services.propane_service.PropaneService.get_current_prices",
                new=AsyncMock(return_value=[_PRICES_PAYLOAD[0]]),
            ) as mock_svc,
            patch(
                "services.propane_service.PropaneService.get_tracked_states",
                return_value=_TRACKED_STATES,
            ),
        ):
            resp = client.get(f"{_BASE}?state=CT")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with("CT")

    def test_no_state_passes_none(self, client):
        with (
            patch(
                "services.propane_service.PropaneService.get_current_prices",
                new=AsyncMock(return_value=_PRICES_PAYLOAD),
            ) as mock_svc,
            patch(
                "services.propane_service.PropaneService.get_tracked_states",
                return_value=_TRACKED_STATES,
            ),
        ):
            resp = client.get(_BASE)
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(None)

    def test_empty_prices_returns_200(self, client):
        with (
            patch(
                "services.propane_service.PropaneService.get_current_prices",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "services.propane_service.PropaneService.get_tracked_states",
                return_value=[],
            ),
        ):
            resp = client.get(_BASE)
        assert resp.status_code == 200
        assert resp.json()["prices"] == []


# ---------------------------------------------------------------------------
# GET /rates/propane/history
# ---------------------------------------------------------------------------

_HISTORY_PAYLOAD = [
    {"week_ending": "2026-05-10", "price_per_gallon": 2.85},
    {"week_ending": "2026-05-03", "price_per_gallon": 2.78},
]
_COMPARISON_PAYLOAD = {
    "state": "CT",
    "state_price": 2.85,
    "national_avg": 2.75,
    "vs_national": "+0.10",
}


class TestPropaneHistory:
    def test_returns_history_and_comparison_for_valid_state(self, client):
        with (
            patch(
                "services.propane_service.PropaneService.is_propane_state",
                return_value=True,
            ),
            patch(
                "services.propane_service.PropaneService.get_price_history",
                new=AsyncMock(return_value=_HISTORY_PAYLOAD),
            ),
            patch(
                "services.propane_service.PropaneService.get_price_comparison",
                new=AsyncMock(return_value=_COMPARISON_PAYLOAD),
            ),
        ):
            resp = client.get(f"{_BASE}/history?state=CT")
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "CT"
        assert len(body["history"]) == 2
        assert body["comparison"] == _COMPARISON_PAYLOAD

    def test_invalid_state_returns_404(self, client):
        with patch(
            "services.propane_service.PropaneService.is_propane_state",
            return_value=False,
        ):
            resp = client.get(f"{_BASE}/history?state=AK")
        assert resp.status_code == 404

    def test_missing_state_returns_422(self, client):
        resp = client.get(f"{_BASE}/history")
        assert resp.status_code == 422

    def test_weeks_max_boundary_52(self, client):
        with (
            patch(
                "services.propane_service.PropaneService.is_propane_state",
                return_value=True,
            ),
            patch(
                "services.propane_service.PropaneService.get_price_history",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "services.propane_service.PropaneService.get_price_comparison",
                new=AsyncMock(return_value=_COMPARISON_PAYLOAD),
            ),
        ):
            resp = client.get(f"{_BASE}/history?state=CT&weeks=52")
        assert resp.status_code == 200

    def test_weeks_over_max_returns_422(self, client):
        resp = client.get(f"{_BASE}/history?state=CT&weeks=53")
        assert resp.status_code == 422

    def test_weeks_zero_returns_422(self, client):
        resp = client.get(f"{_BASE}/history?state=CT&weeks=0")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /rates/propane/compare
# ---------------------------------------------------------------------------


class TestPropaneCompare:
    def test_returns_comparison_for_valid_state(self, client):
        with patch(
            "services.propane_service.PropaneService.get_price_comparison",
            new=AsyncMock(return_value=_COMPARISON_PAYLOAD),
        ):
            resp = client.get(f"{_BASE}/compare?state=CT")
        assert resp.status_code == 200
        assert resp.json()["state"] == "CT"

    def test_no_data_returns_404(self, client):
        with patch(
            "services.propane_service.PropaneService.get_price_comparison",
            new=AsyncMock(return_value=None),
        ):
            resp = client.get(f"{_BASE}/compare?state=WY")
        assert resp.status_code == 404

    def test_missing_state_returns_422(self, client):
        resp = client.get(f"{_BASE}/compare")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /rates/propane/timing
# ---------------------------------------------------------------------------

_TIMING_PAYLOAD = {
    "state": "CT",
    "current_month": "May",
    "recommendation": "buy_now",
    "reason": "Prices historically drop June–August; lock in now before winter demand",
    "season": "shoulder",
}


class TestPropaneTiming:
    def test_returns_timing_advice_for_valid_state(self, client):
        with (
            patch(
                "services.propane_service.PropaneService.is_propane_state",
                return_value=True,
            ),
            patch(
                "services.propane_service.PropaneService.get_seasonal_advice",
                new=AsyncMock(return_value=_TIMING_PAYLOAD),
            ),
        ):
            resp = client.get(f"{_BASE}/timing?state=CT")
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "CT"
        assert "recommendation" in body

    def test_invalid_state_returns_404(self, client):
        with patch(
            "services.propane_service.PropaneService.is_propane_state",
            return_value=False,
        ):
            resp = client.get(f"{_BASE}/timing?state=AK")
        assert resp.status_code == 404

    def test_missing_state_returns_422(self, client):
        resp = client.get(f"{_BASE}/timing")
        assert resp.status_code == 422
