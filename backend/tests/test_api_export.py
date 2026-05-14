"""Tests for the Export API (backend/api/v1/export.py).

Covers:
- GET /export/rates    (business tier required, JSON + CSV, filters, error path)
- GET /export/types    (business tier required, returns config metadata)
- Auth-wall: 401/403 when unauthenticated
- Tier-wall: 403 when free/pro user hits business endpoints
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
_TEST_USER = SessionData(user_id=_USER_ID, email="export@example.com")


def _tier_db_mock(tier: str):
    """DB mock whose tier query returns the given tier."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = tier
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def business_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _tier_db_mock("business")
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def pro_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _tier_db_mock("pro")
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def free_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _tier_db_mock("free")
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
# GET /export/rates
# ---------------------------------------------------------------------------

_JSON_PAYLOAD = {
    "format": "json",
    "data": [
        {
            "region": "US_CT",
            "supplier": "Eversource",
            "price_per_kwh": "0.21",
            "timestamp": "2026-05-01T00:00:00Z",
        },
        {
            "region": "US_CT",
            "supplier": "Eversource",
            "price_per_kwh": "0.22",
            "timestamp": "2026-05-02T00:00:00Z",
        },
    ],
    "count": 2,
    "metadata": {"utility_type": "electricity"},
}

_CSV_PAYLOAD = {
    "format": "csv",
    "data": "region,supplier,price_per_kwh,timestamp\nUS_CT,Eversource,0.21,2026-05-01T00:00:00Z\n",
    "count": 1,
    "metadata": {"utility_type": "electricity"},
}


class TestExportRates:
    def test_business_user_can_export_json(self, business_client):
        with patch(
            "services.rate_export_service.RateExportService.export_rates",
            new=AsyncMock(return_value=_JSON_PAYLOAD),
        ):
            resp = business_client.get("/api/v1/export/rates?utility_type=electricity")
        assert resp.status_code == 200
        body = resp.json()
        assert body["format"] == "json"
        assert body["count"] == 2
        assert len(body["data"]) == 2

    def test_business_user_can_export_csv(self, business_client):
        with patch(
            "services.rate_export_service.RateExportService.export_rates",
            new=AsyncMock(return_value=_CSV_PAYLOAD),
        ):
            resp = business_client.get("/api/v1/export/rates?utility_type=electricity&format=csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        assert "rateshift_electricity_rates.csv" in resp.headers["content-disposition"]
        assert "region,supplier" in resp.text

    def test_state_filter_is_forwarded(self, business_client):
        with patch(
            "services.rate_export_service.RateExportService.export_rates",
            new=AsyncMock(return_value=_JSON_PAYLOAD),
        ) as mock_svc:
            resp = business_client.get("/api/v1/export/rates?utility_type=electricity&state=CT")
        assert resp.status_code == 200
        kwargs = mock_svc.await_args.kwargs
        assert kwargs["state"] == "CT"
        assert kwargs["utility_type"] == "electricity"
        assert kwargs["format"] == "json"

    def test_date_range_is_forwarded(self, business_client):
        with patch(
            "services.rate_export_service.RateExportService.export_rates",
            new=AsyncMock(return_value=_JSON_PAYLOAD),
        ) as mock_svc:
            resp = business_client.get(
                "/api/v1/export/rates"
                "?utility_type=electricity"
                "&start_date=2026-01-01T00:00:00Z"
                "&end_date=2026-05-01T00:00:00Z"
            )
        assert resp.status_code == 200
        kwargs = mock_svc.await_args.kwargs
        assert kwargs["start_date"] is not None
        assert kwargs["end_date"] is not None
        assert kwargs["start_date"].year == 2026
        assert kwargs["start_date"].month == 1
        assert kwargs["end_date"].month == 5

    def test_no_date_filter_passes_none(self, business_client):
        with patch(
            "services.rate_export_service.RateExportService.export_rates",
            new=AsyncMock(return_value=_JSON_PAYLOAD),
        ) as mock_svc:
            resp = business_client.get("/api/v1/export/rates?utility_type=electricity")
        assert resp.status_code == 200
        kwargs = mock_svc.await_args.kwargs
        assert kwargs["start_date"] is None
        assert kwargs["end_date"] is None
        assert kwargs["state"] is None

    def test_unknown_utility_type_returns_error_payload(self, business_client):
        error = {
            "error": "Unknown utility type: spaceship_fuel",
            "supported_types": ["electricity", "natural_gas"],
        }
        with patch(
            "services.rate_export_service.RateExportService.export_rates",
            new=AsyncMock(return_value=error),
        ):
            resp = business_client.get("/api/v1/export/rates?utility_type=spaceship_fuel")
        # Endpoint returns the error dict at status 200 (no exception path).
        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body
        assert "spaceship_fuel" in body["error"]
        assert "supported_types" in body

    def test_invalid_format_query_returns_422(self, business_client):
        # `format` regex restricts to json|csv.
        resp = business_client.get("/api/v1/export/rates?utility_type=electricity&format=xml")
        assert resp.status_code == 422

    def test_missing_utility_type_returns_422(self, business_client):
        resp = business_client.get("/api/v1/export/rates")
        assert resp.status_code == 422

    def test_free_user_blocked_403(self, free_client):
        resp = free_client.get("/api/v1/export/rates?utility_type=electricity")
        assert resp.status_code == 403

    def test_pro_user_blocked_403(self, pro_client):
        resp = pro_client.get("/api/v1/export/rates?utility_type=electricity")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401_or_403(self, unauth_client):
        resp = unauth_client.get("/api/v1/export/rates?utility_type=electricity")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /export/types
# ---------------------------------------------------------------------------


class TestExportTypes:
    def test_business_user_gets_type_list(self, business_client):
        resp = business_client.get("/api/v1/export/types")
        assert resp.status_code == 200
        body = resp.json()
        assert "supported_types" in body
        assert isinstance(body["supported_types"], list)
        assert len(body["supported_types"]) >= 1
        # electricity must be in the list given EXPORT_CONFIGS shipped value.
        assert "electricity" in body["supported_types"]

    def test_response_contains_format_and_limits(self, business_client):
        resp = business_client.get("/api/v1/export/types")
        assert resp.status_code == 200
        body = resp.json()
        assert body["formats"] == ["json", "csv"]
        assert body["max_days"] == 365
        assert body["max_rows"] == 10000

    def test_free_user_blocked_403(self, free_client):
        resp = free_client.get("/api/v1/export/types")
        assert resp.status_code == 403

    def test_pro_user_blocked_403(self, pro_client):
        resp = pro_client.get("/api/v1/export/types")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401_or_403(self, unauth_client):
        resp = unauth_client.get("/api/v1/export/types")
        assert resp.status_code in (401, 403)
