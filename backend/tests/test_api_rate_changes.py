"""Tests for the Rate Changes API (backend/api/v1/rate_changes.py).

Covers:
- GET  /rate-changes              (public; query params; bounds)
- GET  /rate-changes/preferences  (auth required)
- PUT  /rate-changes/preferences  (valid body; invalid utility_type; invalid cadence)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="ratechanges@example.com")

_BASE = "/api/v1/rate-changes"

_CHANGE = {
    "id": str(uuid.uuid4()),
    "utility_type": "electricity",
    "region": "us_ct",
    "change_pct": -5.2,
    "detected_at": "2026-05-14T08:00:00",
}

_PREF = {
    "utility_type": "electricity",
    "enabled": True,
    "channels": ["email", "push"],
    "cadence": "daily",
}


@pytest.fixture
def public_client():
    from main import app

    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db_session, None)


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
# GET /rate-changes
# ---------------------------------------------------------------------------


class TestGetRateChanges:
    def test_returns_changes_list(self, public_client):
        with patch(
            "services.rate_change_detector.RateChangeDetector.get_recent_changes",
            new=AsyncMock(return_value=[_CHANGE]),
        ):
            resp = public_client.get(_BASE)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["changes"][0]["utility_type"] == "electricity"

    def test_empty_changes_returns_200(self, public_client):
        with patch(
            "services.rate_change_detector.RateChangeDetector.get_recent_changes",
            new=AsyncMock(return_value=[]),
        ):
            resp = public_client.get(_BASE)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_utility_type_filter_passed_to_detector(self, public_client):
        with patch(
            "services.rate_change_detector.RateChangeDetector.get_recent_changes",
            new=AsyncMock(return_value=[]),
        ) as mock_det:
            resp = public_client.get(f"{_BASE}?utility_type=electricity")
        assert resp.status_code == 200
        call_kwargs = mock_det.call_args.kwargs
        assert call_kwargs["utility_type"] == "electricity"

    def test_region_filter_passed_to_detector(self, public_client):
        with patch(
            "services.rate_change_detector.RateChangeDetector.get_recent_changes",
            new=AsyncMock(return_value=[]),
        ) as mock_det:
            resp = public_client.get(f"{_BASE}?region=us_ct")
        assert resp.status_code == 200
        assert mock_det.call_args.kwargs["region"] == "us_ct"

    def test_days_max_boundary_90(self, public_client):
        with patch(
            "services.rate_change_detector.RateChangeDetector.get_recent_changes",
            new=AsyncMock(return_value=[]),
        ):
            resp = public_client.get(f"{_BASE}?days=90")
        assert resp.status_code == 200

    def test_days_over_max_returns_422(self, public_client):
        resp = public_client.get(f"{_BASE}?days=91")
        assert resp.status_code == 422

    def test_limit_max_boundary_200(self, public_client):
        with patch(
            "services.rate_change_detector.RateChangeDetector.get_recent_changes",
            new=AsyncMock(return_value=[]),
        ):
            resp = public_client.get(f"{_BASE}?limit=200")
        assert resp.status_code == 200

    def test_limit_over_max_returns_422(self, public_client):
        resp = public_client.get(f"{_BASE}?limit=201")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /rate-changes/preferences
# ---------------------------------------------------------------------------


class TestGetPreferences:
    def test_returns_preferences_for_user(self, auth_client):
        with patch(
            "services.rate_change_detector.AlertPreferenceService.get_preferences",
            new=AsyncMock(return_value=[_PREF]),
        ):
            resp = auth_client.get(f"{_BASE}/preferences")
        assert resp.status_code == 200
        assert resp.json()["preferences"][0]["cadence"] == "daily"

    def test_passes_user_id_to_service(self, auth_client):
        with patch(
            "services.rate_change_detector.AlertPreferenceService.get_preferences",
            new=AsyncMock(return_value=[]),
        ) as mock_svc:
            resp = auth_client.get(f"{_BASE}/preferences")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(_USER_ID)

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get(f"{_BASE}/preferences")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PUT /rate-changes/preferences
# ---------------------------------------------------------------------------

_VALID_BODY = {
    "utility_type": "electricity",
    "enabled": True,
    "channels": ["email"],
    "cadence": "daily",
}


class TestUpsertPreferences:
    def test_valid_body_returns_200(self, auth_client):
        with patch(
            "services.rate_change_detector.AlertPreferenceService.upsert_preference",
            new=AsyncMock(return_value=_PREF),
        ):
            resp = auth_client.put(f"{_BASE}/preferences", json=_VALID_BODY)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_invalid_utility_type_returns_422(self, auth_client):
        body = {**_VALID_BODY, "utility_type": "solar"}
        with patch(
            "services.rate_change_detector.AlertPreferenceService.upsert_preference",
            new=AsyncMock(return_value=_PREF),
        ):
            resp = auth_client.put(f"{_BASE}/preferences", json=body)
        assert resp.status_code == 422

    def test_invalid_cadence_returns_422(self, auth_client):
        body = {**_VALID_BODY, "cadence": "hourly"}
        with patch(
            "services.rate_change_detector.AlertPreferenceService.upsert_preference",
            new=AsyncMock(return_value=_PREF),
        ):
            resp = auth_client.put(f"{_BASE}/preferences", json=body)
        assert resp.status_code == 422

    def test_partial_body_allowed(self, auth_client):
        """utility_type is required; all other fields are optional."""
        with patch(
            "services.rate_change_detector.AlertPreferenceService.upsert_preference",
            new=AsyncMock(return_value=_PREF),
        ):
            resp = auth_client.put(f"{_BASE}/preferences", json={"utility_type": "electricity"})
        assert resp.status_code == 200

    def test_missing_utility_type_returns_422(self, auth_client):
        resp = auth_client.put(f"{_BASE}/preferences", json={"enabled": True})
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.put(f"{_BASE}/preferences", json=_VALID_BODY)
        assert resp.status_code in (401, 403)
