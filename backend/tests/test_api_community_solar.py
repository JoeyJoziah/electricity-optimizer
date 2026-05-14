"""Tests for the Community Solar API (backend/api/v1/community_solar.py).

Mounted at: /api/v1/community-solar  (public, no auth required)

Covers:
- GET /community-solar/programs        (valid state; unsupported state → 400;
                                        bad enrollment_status → 400; limit max 100)
- GET /community-solar/savings         (valid params; non-numeric → 400;
                                        bill=0 → 400; pct=0 → 400; pct=101 → 400)
- GET /community-solar/program/{id}    (found; not found → 404; invalid UUID → 422)
- GET /community-solar/states          (returns list)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session

_BASE = "/api/v1/community-solar"

_PROGRAM = {
    "id": str(uuid.uuid4()),
    "name": "CT Green Energy Cooperative",
    "state": "CT",
    "enrollment_status": "open",
    "savings_percent": 10,
}


@pytest.fixture
def client():
    from main import app

    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# GET /programs
# ---------------------------------------------------------------------------


class TestGetPrograms:
    def test_valid_state_returns_programs(self, client):
        with patch(
            "services.community_solar_service.CommunitySolarService.get_programs",
            new=AsyncMock(return_value=[_PROGRAM]),
        ):
            resp = client.get(f"{_BASE}/programs?state=CT")
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "CT"
        assert body["count"] == 1

    def test_unsupported_state_returns_400(self, client):
        resp = client.get(f"{_BASE}/programs?state=XX")
        assert resp.status_code == 400

    def test_invalid_enrollment_status_returns_400(self, client):
        resp = client.get(f"{_BASE}/programs?state=CT&enrollment_status=pending")
        assert resp.status_code == 400

    def test_limit_over_max_returns_422(self, client):
        resp = client.get(f"{_BASE}/programs?state=CT&limit=101")
        assert resp.status_code == 422

    def test_open_filter_passed_through(self, client):
        with patch(
            "services.community_solar_service.CommunitySolarService.get_programs",
            new=AsyncMock(return_value=[]),
        ) as mock_svc:
            resp = client.get(f"{_BASE}/programs?state=NY&enrollment_status=open")
        assert resp.status_code == 200
        assert mock_svc.call_args.kwargs["enrollment_status"] == "open"


# ---------------------------------------------------------------------------
# GET /savings
# ---------------------------------------------------------------------------


class TestEstimateSavings:
    def test_valid_params_returns_savings(self, client):
        with patch(
            "services.community_solar_service.CommunitySolarService.calculate_savings",
            return_value={"monthly_savings": 15.0, "annual_savings": 180.0},
        ):
            resp = client.get(f"{_BASE}/savings?monthly_bill=150&savings_percent=10")
        assert resp.status_code == 200

    def test_non_numeric_bill_returns_400(self, client):
        resp = client.get(f"{_BASE}/savings?monthly_bill=abc&savings_percent=10")
        assert resp.status_code == 400

    def test_zero_bill_returns_400(self, client):
        resp = client.get(f"{_BASE}/savings?monthly_bill=0&savings_percent=10")
        assert resp.status_code == 400

    def test_zero_savings_percent_returns_400(self, client):
        resp = client.get(f"{_BASE}/savings?monthly_bill=150&savings_percent=0")
        assert resp.status_code == 400

    def test_savings_percent_over_100_returns_400(self, client):
        resp = client.get(f"{_BASE}/savings?monthly_bill=150&savings_percent=101")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /program/{program_id}
# ---------------------------------------------------------------------------


class TestGetProgram:
    def test_found_program_returns_200(self, client):
        pid = str(uuid.uuid4())
        with patch(
            "services.community_solar_service.CommunitySolarService.get_program_by_id",
            new=AsyncMock(return_value=_PROGRAM),
        ):
            resp = client.get(f"{_BASE}/program/{pid}")
        assert resp.status_code == 200

    def test_not_found_returns_404(self, client):
        pid = str(uuid.uuid4())
        with patch(
            "services.community_solar_service.CommunitySolarService.get_program_by_id",
            new=AsyncMock(return_value=None),
        ):
            resp = client.get(f"{_BASE}/program/{pid}")
        assert resp.status_code == 404

    def test_invalid_uuid_returns_422(self, client):
        resp = client.get(f"{_BASE}/program/not-a-uuid")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /states
# ---------------------------------------------------------------------------


class TestGetStates:
    def test_returns_states_list(self, client):
        with patch(
            "services.community_solar_service.CommunitySolarService.get_state_program_count",
            new=AsyncMock(return_value={"CT": 3, "NY": 7}),
        ):
            resp = client.get(f"{_BASE}/states")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_states"] == 2
        assert len(body["states"]) == 2
