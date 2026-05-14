"""Tests for the Forecast API (backend/api/v1/forecast.py).

Covers:
- GET /forecast/{utility_type}  — valid types, invalid type, horizon_days bounds,
                                  state filter, pro-tier gate
- GET /forecast                 — lists supported utility types (pro tier)
- Auth-wall: 401/403 when unauthenticated
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="forecast@example.com")

_VALID_TYPES = ("electricity", "natural_gas", "heating_oil", "propane")


def _pro_db_mock():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "pro"
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


def _free_db_mock():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "free"
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pro_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _pro_db_mock()
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def free_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _free_db_mock()
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauth_client():
    from main import app

    client = TestClient(app, raise_server_exceptions=False)
    yield client


# ---------------------------------------------------------------------------
# Shared forecast payload
# ---------------------------------------------------------------------------

_FORECAST_PAYLOAD = {
    "utility_type": "electricity",
    "state": "CT",
    "horizon_days": 30,
    "trend": "stable",
    "predicted_rate": 0.22,
    "confidence": 0.85,
    "data_points": [
        {"date": "2026-05-15", "rate": 0.218},
        {"date": "2026-06-14", "rate": 0.222},
    ],
}


# ---------------------------------------------------------------------------
# GET /forecast/{utility_type}
# ---------------------------------------------------------------------------


class TestGetForecast:
    @pytest.mark.parametrize("utility_type", _VALID_TYPES)
    def test_valid_utility_type_returns_200(self, pro_client, utility_type):
        payload = {**_FORECAST_PAYLOAD, "utility_type": utility_type}
        with patch(
            "services.forecast_service.ForecastService.get_forecast",
            new=AsyncMock(return_value=payload),
        ):
            resp = pro_client.get(f"/api/v1/forecast/{utility_type}")
        assert resp.status_code == 200
        assert resp.json()["utility_type"] == utility_type

    def test_invalid_utility_type_returns_422(self, pro_client):
        with patch(
            "services.forecast_service.ForecastService.get_forecast",
            new=AsyncMock(return_value=_FORECAST_PAYLOAD),
        ):
            resp = pro_client.get("/api/v1/forecast/solar")
        assert resp.status_code == 422

    def test_state_filter_passed_to_service(self, pro_client):
        with patch(
            "services.forecast_service.ForecastService.get_forecast",
            new=AsyncMock(return_value=_FORECAST_PAYLOAD),
        ) as mock_svc:
            resp = pro_client.get("/api/v1/forecast/electricity?state=CT")
        assert resp.status_code == 200
        call_kwargs = mock_svc.call_args.kwargs
        assert call_kwargs["state"] == "CT"

    def test_default_horizon_is_30_days(self, pro_client):
        with patch(
            "services.forecast_service.ForecastService.get_forecast",
            new=AsyncMock(return_value=_FORECAST_PAYLOAD),
        ) as mock_svc:
            resp = pro_client.get("/api/v1/forecast/electricity")
        assert resp.status_code == 200
        call_kwargs = mock_svc.call_args.kwargs
        assert call_kwargs["horizon_days"] == 30

    def test_custom_horizon_days_passed_to_service(self, pro_client):
        with patch(
            "services.forecast_service.ForecastService.get_forecast",
            new=AsyncMock(return_value=_FORECAST_PAYLOAD),
        ) as mock_svc:
            resp = pro_client.get("/api/v1/forecast/electricity?horizon_days=60")
        assert resp.status_code == 200
        call_kwargs = mock_svc.call_args.kwargs
        assert call_kwargs["horizon_days"] == 60

    def test_horizon_days_min_boundary_1(self, pro_client):
        with patch(
            "services.forecast_service.ForecastService.get_forecast",
            new=AsyncMock(return_value=_FORECAST_PAYLOAD),
        ):
            resp = pro_client.get("/api/v1/forecast/electricity?horizon_days=1")
        assert resp.status_code == 200

    def test_horizon_days_max_boundary_90(self, pro_client):
        with patch(
            "services.forecast_service.ForecastService.get_forecast",
            new=AsyncMock(return_value=_FORECAST_PAYLOAD),
        ):
            resp = pro_client.get("/api/v1/forecast/electricity?horizon_days=90")
        assert resp.status_code == 200

    def test_horizon_days_over_max_returns_422(self, pro_client):
        resp = pro_client.get("/api/v1/forecast/electricity?horizon_days=91")
        assert resp.status_code == 422

    def test_horizon_days_zero_returns_422(self, pro_client):
        resp = pro_client.get("/api/v1/forecast/electricity?horizon_days=0")
        assert resp.status_code == 422

    def test_free_tier_returns_403(self, free_client):
        resp = free_client.get("/api/v1/forecast/electricity")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/forecast/electricity")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /forecast  (list supported types)
# ---------------------------------------------------------------------------


class TestListForecastTypes:
    def test_returns_all_supported_types(self, pro_client):
        resp = pro_client.get("/api/v1/forecast")
        assert resp.status_code == 200
        body = resp.json()
        assert "supported_types" in body
        returned = set(body["supported_types"])
        for t in _VALID_TYPES:
            assert t in returned, f"Expected '{t}' in supported_types"

    def test_includes_description_field(self, pro_client):
        resp = pro_client.get("/api/v1/forecast")
        assert resp.status_code == 200
        assert "description" in resp.json()

    def test_free_tier_returns_403(self, free_client):
        resp = free_client.get("/api/v1/forecast")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/forecast")
        assert resp.status_code in (401, 403)
