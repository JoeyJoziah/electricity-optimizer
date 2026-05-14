"""Tests for the Utility Discovery API (backend/api/v1/utility_discovery.py).

Mounted at: /api/v1/utility-discovery  (public, no auth)

Covers:
- GET /utility-discovery/discover    (valid 2-letter state; state too short/long → 422)
- GET /utility-discovery/completion  (valid; empty tracked → 400; state validation)
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_BASE = "/api/v1/utility-discovery"

_UTILITIES = [
    {"utility_type": "electricity", "available": True},
    {"utility_type": "natural_gas", "available": True},
    {"utility_type": "heating_oil", "available": False},
]

_COMPLETION = {
    "total_available": 2,
    "total_tracked": 1,
    "completion_pct": 50.0,
    "missing": ["natural_gas"],
}


@pytest.fixture
def client():
    from main import app

    c = TestClient(app)
    yield c


# ---------------------------------------------------------------------------
# GET /utility-discovery/discover
# ---------------------------------------------------------------------------


class TestDiscoverUtilities:
    def test_valid_state_returns_utilities(self, client):
        with patch(
            "services.utility_discovery_service.UtilityDiscoveryService.discover",
            return_value=_UTILITIES,
        ):
            resp = client.get(f"{_BASE}/discover?state=CT")
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "CT"
        assert body["count"] == 3

    def test_state_too_short_returns_422(self, client):
        resp = client.get(f"{_BASE}/discover?state=C")
        assert resp.status_code == 422

    def test_state_too_long_returns_422(self, client):
        resp = client.get(f"{_BASE}/discover?state=CTX")
        assert resp.status_code == 422

    def test_state_uppercased(self, client):
        with patch(
            "services.utility_discovery_service.UtilityDiscoveryService.discover",
            return_value=[],
        ) as mock_svc:
            resp = client.get(f"{_BASE}/discover?state=ct")
        assert resp.status_code == 200
        mock_svc.assert_called_once_with("CT")


# ---------------------------------------------------------------------------
# GET /utility-discovery/completion
# ---------------------------------------------------------------------------


class TestGetCompletion:
    def test_valid_request_returns_completion(self, client):
        with patch(
            "services.utility_discovery_service.UtilityDiscoveryService.get_completion_status",
            return_value=_COMPLETION,
        ):
            resp = client.get(f"{_BASE}/completion?state=CT&tracked=electricity,natural_gas")
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "CT"
        assert "completion_pct" in body

    def test_empty_tracked_returns_400(self, client):
        resp = client.get(f"{_BASE}/completion?state=CT&tracked=")
        assert resp.status_code == 400

    def test_default_tracked_electricity(self, client):
        with patch(
            "services.utility_discovery_service.UtilityDiscoveryService.get_completion_status",
            return_value=_COMPLETION,
        ) as mock_svc:
            resp = client.get(f"{_BASE}/completion?state=NY")
        assert resp.status_code == 200
        args = mock_svc.call_args[0]
        assert "electricity" in args[1]
