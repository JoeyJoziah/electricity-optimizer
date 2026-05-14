"""Tests for the Neighborhood API (backend/api/v1/neighborhood.py).

Mounted at: /api/v1/neighborhood  (auth required)

Covers:
- GET /neighborhood/compare  (valid; invalid utility_type → 422; auth-wall)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="neighbor@example.com")

_BASE = "/api/v1/neighborhood"

_COMPARISON = {
    "user_rate": 0.18,
    "region_avg": 0.21,
    "percentile": 35,
    "cheaper_alternatives": [{"supplier": "CleanChoice", "rate": 0.16}],
}


@pytest.fixture
def auth_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauth_client():
    from main import app

    c = TestClient(app, raise_server_exceptions=False)
    yield c


class TestNeighborhoodCompare:
    def test_valid_request_returns_comparison(self, auth_client):
        with patch(
            "services.neighborhood_service.NeighborhoodService.get_comparison",
            new=AsyncMock(return_value=_COMPARISON),
        ):
            resp = auth_client.get(f"{_BASE}/compare?region=us_ct&utility_type=electricity")
        assert resp.status_code == 200
        body = resp.json()
        assert "user_rate" in body
        assert "percentile" in body

    def test_invalid_utility_type_returns_422(self, auth_client):
        with patch(
            "services.neighborhood_service.NeighborhoodService.get_comparison",
            new=AsyncMock(return_value=_COMPARISON),
        ):
            resp = auth_client.get(f"{_BASE}/compare?region=us_ct&utility_type=solar")
        assert resp.status_code == 422

    def test_passes_user_id_to_service(self, auth_client):
        with patch(
            "services.neighborhood_service.NeighborhoodService.get_comparison",
            new=AsyncMock(return_value=_COMPARISON),
        ) as mock_svc:
            resp = auth_client.get(f"{_BASE}/compare?region=us_ct&utility_type=electricity")
        assert resp.status_code == 200
        assert mock_svc.call_args.kwargs["user_id"] == _USER_ID

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get(f"{_BASE}/compare?region=us_ct&utility_type=electricity")
        assert resp.status_code in (401, 403)
