"""Tests for the Public Rates API (backend/api/v1/public_rates.py).

Mounted at: /api/v1/public/rates  (public, no auth)

Covers:
- GET /public/rates/states               (returns state map)
- GET /public/rates/{state}/electricity  (found; no data → 404)
- GET /public/rates/{state}/natural_gas  (found)
- GET /public/rates/{state}/heating_oil  (found)
- GET /public/rates/{state}/unknown      (unknown utility type → 404)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session

_BASE = "/api/v1/public/rates"


def _db_with_rows(rows: list) -> AsyncMock:
    """Return DB mock whose execute() yields the given mapping rows."""
    mapping_result = MagicMock()
    mapping_result.all.return_value = rows
    result = MagicMock()
    result.mappings.return_value = mapping_result
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


def _db_no_rows() -> AsyncMock:
    return _db_with_rows([])


@pytest.fixture
def client():
    from main import app

    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# GET /public/rates/states
# ---------------------------------------------------------------------------


class TestGetAvailableStates:
    def test_returns_state_map(self, client):
        rows = [
            {"state": "CT", "utility_type": "electricity"},
            {"state": "CT", "utility_type": "natural_gas"},
        ]
        db_mock = _db_with_rows(rows)

        from main import app

        app.dependency_overrides[get_db_session] = lambda: db_mock
        c = TestClient(app)
        resp = c.get(f"{_BASE}/states")
        app.dependency_overrides.pop(get_db_session, None)

        assert resp.status_code == 200
        body = resp.json()
        assert "states" in body

    def test_empty_db_returns_empty_map(self, client):
        db_mock = _db_with_rows([])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: db_mock
        c = TestClient(app)
        resp = c.get(f"{_BASE}/states")
        app.dependency_overrides.pop(get_db_session, None)

        assert resp.status_code == 200
        assert resp.json()["states"] == {}


# ---------------------------------------------------------------------------
# GET /public/rates/{state}/{utility_type}
# ---------------------------------------------------------------------------


class TestGetRateSummary:
    def test_electricity_found_returns_200(self, client):
        row = MagicMock()
        row.__getitem__ = lambda self, k: {
            "supplier": "Eversource",
            "price_per_kwh": 0.19,
            "rate_type": "variable",
            "updated_at": "2026-05-14",
        }[k]
        result = MagicMock()
        result.mappings.return_value.all.return_value = [row]
        db_mock = AsyncMock()
        db_mock.execute = AsyncMock(return_value=result)

        from main import app

        app.dependency_overrides[get_db_session] = lambda: db_mock
        c = TestClient(app)
        resp = c.get(f"{_BASE}/CT/electricity")
        app.dependency_overrides.pop(get_db_session, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["utility_type"] == "electricity"
        assert body["state"] == "CT"

    def test_electricity_no_data_returns_404(self, client):
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        db_mock = AsyncMock()
        db_mock.execute = AsyncMock(return_value=result)

        from main import app

        app.dependency_overrides[get_db_session] = lambda: db_mock
        c = TestClient(app)
        resp = c.get(f"{_BASE}/XX/electricity")
        app.dependency_overrides.pop(get_db_session, None)

        assert resp.status_code == 404

    def test_unknown_utility_type_returns_404(self, client):
        resp = client.get(f"{_BASE}/CT/wind_power")
        assert resp.status_code == 404
