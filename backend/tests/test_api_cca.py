"""Tests for the CCA API (backend/api/v1/cca.py).

Covers:
- GET /cca/detect (with zip_code, with state+municipality, missing params)
- GET /cca/compare/{cca_id} (found, not found, invalid rate)
- GET /cca/info/{cca_id} (found, not found)
- GET /cca/programs (all, filtered by state)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def client(mock_db):
    from main import app

    app.dependency_overrides[get_db_session] = lambda: mock_db
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db_session, None)


class TestDetectCCA:
    def test_with_zip_code_returns_program(self, client):
        fake_program = {"id": "abc", "name": "MCE", "state": "CA"}
        with patch(
            "services.cca_service.CCAService.detect_cca",
            new=AsyncMock(return_value=fake_program),
        ):
            resp = client.get("/api/v1/cca/detect?zip_code=94704")
        assert resp.status_code == 200
        body = resp.json()
        assert body["in_cca"] is True
        assert body["program"] == fake_program

    def test_with_zip_code_no_match(self, client):
        with patch(
            "services.cca_service.CCAService.detect_cca",
            new=AsyncMock(return_value=None),
        ):
            resp = client.get("/api/v1/cca/detect?zip_code=99999")
        assert resp.status_code == 200
        body = resp.json()
        assert body["in_cca"] is False
        assert body["program"] is None

    def test_with_state_and_municipality(self, client):
        with patch(
            "services.cca_service.CCAService.detect_cca",
            new=AsyncMock(return_value={"id": "x", "name": "SVCE"}),
        ):
            resp = client.get("/api/v1/cca/detect?state=CA&municipality=Sunnyvale")
        assert resp.status_code == 200
        assert resp.json()["in_cca"] is True

    def test_missing_all_params_returns_400(self, client):
        resp = client.get("/api/v1/cca/detect")
        assert resp.status_code == 400
        assert "zip_code" in resp.json()["detail"]

    def test_state_without_municipality_returns_400(self, client):
        resp = client.get("/api/v1/cca/detect?state=CA")
        assert resp.status_code == 400


class TestCompareRate:
    def test_returns_comparison(self, client):
        cca_id = uuid.uuid4()
        fake = {
            "cca_name": "MCE",
            "cca_rate": 0.11,
            "default_rate": 0.15,
            "savings_pct": 26.7,
        }
        with patch(
            "services.cca_service.CCAService.compare_cca_rate",
            new=AsyncMock(return_value=fake),
        ):
            resp = client.get(f"/api/v1/cca/compare/{cca_id}?default_rate=0.15")
        assert resp.status_code == 200
        assert resp.json() == fake

    def test_not_found_returns_404(self, client):
        cca_id = uuid.uuid4()
        with patch(
            "services.cca_service.CCAService.compare_cca_rate",
            new=AsyncMock(return_value={"error": "CCA not found"}),
        ):
            resp = client.get(f"/api/v1/cca/compare/{cca_id}?default_rate=0.15")
        assert resp.status_code == 404

    def test_zero_default_rate_returns_422(self, client):
        cca_id = uuid.uuid4()
        resp = client.get(f"/api/v1/cca/compare/{cca_id}?default_rate=0")
        assert resp.status_code == 422

    def test_missing_default_rate_returns_422(self, client):
        cca_id = uuid.uuid4()
        resp = client.get(f"/api/v1/cca/compare/{cca_id}")
        assert resp.status_code == 422

    def test_invalid_uuid_returns_422(self, client):
        resp = client.get("/api/v1/cca/compare/not-a-uuid?default_rate=0.15")
        assert resp.status_code == 422


class TestCCAInfo:
    def test_returns_info(self, client):
        cca_id = uuid.uuid4()
        fake = {"id": str(cca_id), "name": "MCE", "opt_out_url": "https://..."}
        with patch(
            "services.cca_service.CCAService.get_cca_info",
            new=AsyncMock(return_value=fake),
        ):
            resp = client.get(f"/api/v1/cca/info/{cca_id}")
        assert resp.status_code == 200
        assert resp.json() == fake

    def test_not_found_returns_404(self, client):
        cca_id = uuid.uuid4()
        with patch(
            "services.cca_service.CCAService.get_cca_info",
            new=AsyncMock(return_value=None),
        ):
            resp = client.get(f"/api/v1/cca/info/{cca_id}")
        assert resp.status_code == 404


class TestListPrograms:
    def test_returns_all_programs(self, client):
        fake_programs = [
            {"id": "1", "name": "MCE", "state": "CA"},
            {"id": "2", "name": "SVCE", "state": "CA"},
        ]
        with patch(
            "services.cca_service.CCAService.list_cca_programs",
            new=AsyncMock(return_value=fake_programs),
        ):
            resp = client.get("/api/v1/cca/programs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert body["programs"] == fake_programs

    def test_filters_by_state(self, client):
        captured = {}

        async def fake_list(self, state=None):
            captured["state"] = state
            return []

        with patch(
            "services.cca_service.CCAService.list_cca_programs",
            new=fake_list,
        ):
            resp = client.get("/api/v1/cca/programs?state=NY")
        assert resp.status_code == 200
        assert captured["state"] == "NY"
        assert resp.json()["count"] == 0
