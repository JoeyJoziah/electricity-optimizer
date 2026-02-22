"""
Tests for the User API Router (backend/api/v1/user.py)

Tests cover:
- GET /preferences - get user preferences
- POST /preferences - update user preferences
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.dependencies import get_current_user, TokenData


TEST_USER = TokenData(user_id="user-prefs-1", email="prefs@example.com")


@pytest.fixture
def auth_client():
    """Create a TestClient with authenticated user."""
    from main import app

    app.dependency_overrides[get_current_user] = lambda: TEST_USER

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauth_client():
    """Create a TestClient without authentication."""
    from main import app

    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app)
    yield client


# =============================================================================
# GET /preferences
# =============================================================================


class TestGetPreferences:
    """Tests for the GET /api/v1/user/preferences endpoint."""

    def test_get_preferences_success(self, auth_client):
        """Authenticated user should receive default preferences."""
        response = auth_client.get("/api/v1/user/preferences")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER.user_id
        assert "preferences" in data
        prefs = data["preferences"]
        assert prefs["notification_enabled"] is True
        assert prefs["auto_switch_enabled"] is False
        assert prefs["green_energy_only"] is False

    def test_get_preferences_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.get("/api/v1/user/preferences")
        assert response.status_code == 401

    def test_get_preferences_returns_user_id(self, auth_client):
        """Response should contain the authenticated user's ID."""
        response = auth_client.get("/api/v1/user/preferences")
        assert response.json()["user_id"] == "user-prefs-1"


# =============================================================================
# POST /preferences
# =============================================================================


class TestUpdatePreferences:
    """Tests for the POST /api/v1/user/preferences endpoint."""

    def test_update_single_preference(self, auth_client):
        """Updating one preference should return only that field."""
        response = auth_client.post(
            "/api/v1/user/preferences",
            json={"notification_enabled": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER.user_id
        assert data["preferences"]["notification_enabled"] is False
        assert "message" in data

    def test_update_multiple_preferences(self, auth_client):
        """Updating multiple preferences should return all updated fields."""
        response = auth_client.post(
            "/api/v1/user/preferences",
            json={
                "auto_switch_enabled": True,
                "green_energy_only": True,
                "region": "US_CT",
            },
        )
        assert response.status_code == 200
        data = response.json()
        prefs = data["preferences"]
        assert prefs["auto_switch_enabled"] is True
        assert prefs["green_energy_only"] is True
        assert prefs["region"] == "US_CT"

    def test_update_empty_body(self, auth_client):
        """Empty update body should return empty preferences dict."""
        response = auth_client.post(
            "/api/v1/user/preferences",
            json={},
        )
        assert response.status_code == 200
        data = response.json()
        # exclude_none means no keys in preferences
        assert data["preferences"] == {}

    def test_update_preferences_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.post(
            "/api/v1/user/preferences",
            json={"notification_enabled": True},
        )
        assert response.status_code == 401

    def test_update_preferences_message(self, auth_client):
        """Response should contain success message."""
        response = auth_client.post(
            "/api/v1/user/preferences",
            json={"notification_enabled": True},
        )
        assert "Preferences updated successfully" in response.json()["message"]

    def test_update_ignores_unknown_fields(self, auth_client):
        """Unknown fields should be ignored (Pydantic model validation)."""
        response = auth_client.post(
            "/api/v1/user/preferences",
            json={"unknown_field": "value", "notification_enabled": True},
        )
        assert response.status_code == 200
        prefs = response.json()["preferences"]
        assert "unknown_field" not in prefs
        assert prefs["notification_enabled"] is True
