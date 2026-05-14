"""Tests for the Referrals API (backend/api/v1/referrals.py).

Covers:
- GET  /referrals/code    (returns code; auth-wall)
- POST /referrals/apply   (valid code; invalid/expired code → 400; bad body → 422)
- GET  /referrals/stats   (returns stats; auth-wall)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session
from services.referral_service import ReferralError

_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="referrer@example.com")


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


# ---------------------------------------------------------------------------
# GET /referrals/code
# ---------------------------------------------------------------------------


class TestGetReferralCode:
    def test_returns_referral_code(self, auth_client):
        with patch(
            "services.referral_service.ReferralService.get_or_create_code",
            new=AsyncMock(return_value="RSHIFT42"),
        ):
            resp = auth_client.get("/api/v1/referrals/code")
        assert resp.status_code == 200
        assert resp.json()["referral_code"] == "RSHIFT42"

    def test_passes_user_id_to_service(self, auth_client):
        with patch(
            "services.referral_service.ReferralService.get_or_create_code",
            new=AsyncMock(return_value="RSHIFT42"),
        ) as mock_svc:
            resp = auth_client.get("/api/v1/referrals/code")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(_USER_ID)

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/referrals/code")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /referrals/apply
# ---------------------------------------------------------------------------


class TestApplyReferral:
    def test_valid_code_applies_successfully(self, auth_client):
        with patch(
            "services.referral_service.ReferralService.apply_referral",
            new=AsyncMock(return_value={"referral_code": "FRIEND01"}),
        ):
            resp = auth_client.post("/api/v1/referrals/apply", json={"code": "FRIEND01"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "applied"
        assert body["referral_code"] == "FRIEND01"

    def test_invalid_code_returns_400(self, auth_client):
        with patch(
            "services.referral_service.ReferralService.apply_referral",
            new=AsyncMock(side_effect=ReferralError("invalid")),
        ):
            resp = auth_client.post("/api/v1/referrals/apply", json={"code": "BADCODE"})
        assert resp.status_code == 400
        assert "referral" in resp.json()["detail"].lower()

    def test_empty_code_returns_422(self, auth_client):
        resp = auth_client.post("/api/v1/referrals/apply", json={"code": ""})
        assert resp.status_code == 422

    def test_code_too_long_returns_422(self, auth_client):
        resp = auth_client.post("/api/v1/referrals/apply", json={"code": "A" * 13})
        assert resp.status_code == 422

    def test_missing_code_field_returns_422(self, auth_client):
        resp = auth_client.post("/api/v1/referrals/apply", json={})
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.post("/api/v1/referrals/apply", json={"code": "FRIEND01"})
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /referrals/stats
# ---------------------------------------------------------------------------

_STATS = {
    "referral_code": "RSHIFT42",
    "referrals_sent": 5,
    "referrals_converted": 2,
    "conversion_rate": 0.4,
    "credits_earned": 10.0,
}


class TestGetReferralStats:
    def test_returns_stats_for_user(self, auth_client):
        with patch(
            "services.referral_service.ReferralService.get_stats",
            new=AsyncMock(return_value=_STATS),
        ):
            resp = auth_client.get("/api/v1/referrals/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["referrals_sent"] == 5
        assert body["conversion_rate"] == 0.4

    def test_passes_user_id_to_service(self, auth_client):
        with patch(
            "services.referral_service.ReferralService.get_stats",
            new=AsyncMock(return_value=_STATS),
        ) as mock_svc:
            resp = auth_client.get("/api/v1/referrals/stats")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(_USER_ID)

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/referrals/stats")
        assert resp.status_code in (401, 403)
