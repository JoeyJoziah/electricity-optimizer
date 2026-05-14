"""Tests for the Affiliate API (backend/api/v1/affiliate.py).

Covers:
- POST /affiliate/click (anonymous + authenticated)
- GET  /affiliate/revenue (internal — requires API key)
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import (
    SessionData,
    get_current_user_optional,
    get_db_session,
    verify_api_key,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def anon_client(mock_db):
    from main import app

    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_current_user_optional] = lambda: None
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_current_user_optional, None)


@pytest.fixture
def auth_client(mock_db):
    from main import app

    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_current_user_optional] = lambda: SessionData(
        user_id="user-123", email="u@example.com"
    )
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_current_user_optional, None)


@pytest.fixture
def internal_client(mock_db):
    from main import app

    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[verify_api_key] = lambda: True
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(verify_api_key, None)


VALID_CLICK = {
    "supplier_name": "Eversource Energy",
    "supplier_id": None,
    "utility_type": "electricity",
    "region": "CT",
    "source_page": "/dashboard",
}


class TestRecordClick:
    def test_anonymous_click_succeeds(self, anon_client):
        with patch(
            "services.affiliate_service.AffiliateService.record_click",
            new=AsyncMock(return_value="click-abc"),
        ):
            resp = anon_client.post("/api/v1/affiliate/click", json=VALID_CLICK)
        assert resp.status_code == 200
        body = resp.json()
        assert body["click_id"] == "click-abc"
        assert "chooseenergy.com" in body["affiliate_url"]
        assert "utm_campaign=electricity_ct" in body["affiliate_url"]

    def test_authenticated_click_passes_user_id(self, auth_client):
        captured = {}

        async def fake_record(self, **kwargs):
            captured.update(kwargs)
            return "click-xyz"

        with patch("services.affiliate_service.AffiliateService.record_click", new=fake_record):
            resp = auth_client.post("/api/v1/affiliate/click", json=VALID_CLICK)
        assert resp.status_code == 200
        assert captured["user_id"] == "user-123"
        assert captured["supplier_name"] == "Eversource Energy"
        assert captured["region"] == "CT"

    def test_missing_required_field_returns_422(self, anon_client):
        payload = {k: v for k, v in VALID_CLICK.items() if k != "supplier_name"}
        resp = anon_client.post("/api/v1/affiliate/click", json=payload)
        assert resp.status_code == 422

    def test_db_unavailable_returns_503(self):
        from main import app

        app.dependency_overrides[get_db_session] = lambda: None
        app.dependency_overrides[get_current_user_optional] = lambda: None
        try:
            client = TestClient(app)
            resp = client.post("/api/v1/affiliate/click", json=VALID_CLICK)
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.pop(get_db_session, None)
            app.dependency_overrides.pop(get_current_user_optional, None)


class TestRevenueSummary:
    def test_requires_api_key(self, mock_db):
        # No override on verify_api_key, no header → 401
        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/affiliate/revenue")
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db_session, None)

    def test_returns_summary_when_authorized(self, internal_client):
        fake_summary = {
            "period_days": 30,
            "total_clicks": 42,
            "total_revenue_cents": 12500,
            "by_partner": [],
        }
        with patch(
            "services.affiliate_service.AffiliateService.get_revenue_summary",
            new=AsyncMock(return_value=fake_summary),
        ):
            resp = internal_client.get("/api/v1/affiliate/revenue?days=30")
        assert resp.status_code == 200
        assert resp.json() == fake_summary

    def test_rejects_invalid_days_param(self, internal_client):
        resp = internal_client.get("/api/v1/affiliate/revenue?days=0")
        assert resp.status_code == 422
        resp = internal_client.get("/api/v1/affiliate/revenue?days=999")
        assert resp.status_code == 422

    def test_db_unavailable_returns_503(self):
        from main import app

        app.dependency_overrides[get_db_session] = lambda: None
        app.dependency_overrides[verify_api_key] = lambda: True
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/affiliate/revenue")
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.pop(get_db_session, None)
            app.dependency_overrides.pop(verify_api_key, None)
