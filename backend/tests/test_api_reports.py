"""Tests for the Reports API (backend/api/v1/reports.py).

Mounted at: /api/v1/reports  (prefix in app_factory)
Single endpoint: GET /reports/optimization  (business tier gated)

Covers:
- GET /reports/optimization  (business tier; missing state 422;
                              free/pro tier 403; auth-wall 401)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="reports@example.com")

_REPORT = {
    "state": "CT",
    "generated_at": "2026-05-14T12:00:00",
    "utilities": ["electricity", "natural_gas", "heating_oil"],
    "top_savings": [
        {
            "utility": "electricity",
            "opportunity": "Switch to off-peak pricing",
            "annual_savings": 120.0,
        },
        {"utility": "heating_oil", "opportunity": "Pre-buy at May prices", "annual_savings": 80.0},
    ],
    "total_annual_opportunity": 200.0,
}


def _tier_db(tier: str) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = tier
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


@pytest.fixture
def business_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _tier_db("business")
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def pro_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _tier_db("pro")
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauth_client():
    from main import app

    c = TestClient(app, raise_server_exceptions=False)
    yield c


class TestGetOptimizationReport:
    def test_business_tier_returns_report(self, business_client):
        with patch(
            "services.optimization_report_service.OptimizationReportService.generate_report",
            new=AsyncMock(return_value=_REPORT),
        ):
            resp = business_client.get("/api/v1/reports/optimization?state=CT")
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "CT"
        assert "top_savings" in body

    def test_passes_state_to_service(self, business_client):
        with patch(
            "services.optimization_report_service.OptimizationReportService.generate_report",
            new=AsyncMock(return_value=_REPORT),
        ) as mock_svc:
            resp = business_client.get("/api/v1/reports/optimization?state=NY")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(state="NY")

    def test_missing_state_returns_422(self, business_client):
        resp = business_client.get("/api/v1/reports/optimization")
        assert resp.status_code == 422

    def test_pro_tier_returns_403(self, pro_client):
        resp = pro_client.get("/api/v1/reports/optimization?state=CT")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/reports/optimization?state=CT")
        assert resp.status_code in (401, 403)
