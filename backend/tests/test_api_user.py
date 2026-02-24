"""
Tests for the User API Router (backend/api/v1/user.py)

Tests cover:
- GET /preferences - get user preferences (DB-backed)
- POST /preferences - update user preferences (DB-backed)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.dependencies import get_current_user, TokenData
from config.database import get_timescale_session


TEST_USER = TokenData(user_id="user-prefs-1", email="prefs@example.com")


def _make_mock_user(preferences=None):
    """Create a mock User object with given preferences."""
    user = MagicMock()
    user.preferences = preferences or {}
    user.region = "us_ct"
    user.current_supplier = "Eversource"
    return user


@pytest.fixture
def auth_client():
    """Create a TestClient with authenticated user and mocked DB."""
    from main import app

    mock_db = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_timescale_session] = lambda: mock_db

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_timescale_session, None)


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

    @patch("api.v1.user.UserRepository")
    def test_get_preferences_success(self, mock_repo_cls, auth_client):
        """Authenticated user should receive preferences with defaults."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=_make_mock_user())
        mock_repo_cls.return_value = mock_repo

        response = auth_client.get("/api/v1/user/preferences")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER.user_id
        assert "preferences" in data
        prefs = data["preferences"]
        assert prefs["notification_enabled"] is True
        assert prefs["auto_switch_enabled"] is False
        assert prefs["green_energy_only"] is False

    @patch("api.v1.user.UserRepository")
    def test_get_preferences_returns_stored_values(self, mock_repo_cls, auth_client):
        """Stored preferences should override defaults."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(
            return_value=_make_mock_user({"notification_enabled": False, "green_energy_only": True})
        )
        mock_repo_cls.return_value = mock_repo

        response = auth_client.get("/api/v1/user/preferences")
        assert response.status_code == 200
        prefs = response.json()["preferences"]
        assert prefs["notification_enabled"] is False
        assert prefs["green_energy_only"] is True

    @patch("api.v1.user.UserRepository")
    def test_get_preferences_user_not_found(self, mock_repo_cls, auth_client):
        """Missing user should return default preferences."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo_cls.return_value = mock_repo

        response = auth_client.get("/api/v1/user/preferences")
        assert response.status_code == 200
        assert response.json()["preferences"]["notification_enabled"] is True

    def test_get_preferences_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.get("/api/v1/user/preferences")
        assert response.status_code == 401

    @patch("api.v1.user.UserRepository")
    def test_get_preferences_returns_user_id(self, mock_repo_cls, auth_client):
        """Response should contain the authenticated user's ID."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=_make_mock_user())
        mock_repo_cls.return_value = mock_repo

        response = auth_client.get("/api/v1/user/preferences")
        assert response.json()["user_id"] == "user-prefs-1"


# =============================================================================
# POST /preferences
# =============================================================================


class TestUpdatePreferences:
    """Tests for the POST /api/v1/user/preferences endpoint."""

    @patch("api.v1.user.UserRepository")
    def test_update_single_preference(self, mock_repo_cls, auth_client):
        """Updating one preference should persist and return the merged result."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=_make_mock_user())
        mock_repo.update_preferences = AsyncMock(return_value=_make_mock_user({"notification_enabled": False}))
        mock_repo_cls.return_value = mock_repo

        response = auth_client.post(
            "/api/v1/user/preferences",
            json={"notification_enabled": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER.user_id
        assert data["preferences"]["notification_enabled"] is False
        assert "message" in data
        mock_repo.update_preferences.assert_called_once()

    @patch("api.v1.user.UserRepository")
    def test_update_multiple_preferences(self, mock_repo_cls, auth_client):
        """Updating multiple preferences should persist all updated fields."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=_make_mock_user())
        mock_repo.update_preferences = AsyncMock(return_value=_make_mock_user())
        mock_repo_cls.return_value = mock_repo

        response = auth_client.post(
            "/api/v1/user/preferences",
            json={
                "auto_switch_enabled": True,
                "green_energy_only": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        prefs = data["preferences"]
        assert prefs["auto_switch_enabled"] is True
        assert prefs["green_energy_only"] is True

    @patch("api.v1.user.UserRepository")
    def test_update_user_not_found(self, mock_repo_cls, auth_client):
        """Updating preferences for missing user should return 404."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo_cls.return_value = mock_repo

        response = auth_client.post(
            "/api/v1/user/preferences",
            json={"notification_enabled": True},
        )
        assert response.status_code == 404

    def test_update_preferences_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.post(
            "/api/v1/user/preferences",
            json={"notification_enabled": True},
        )
        assert response.status_code == 401

    @patch("api.v1.user.UserRepository")
    def test_update_preferences_message(self, mock_repo_cls, auth_client):
        """Response should contain success message."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=_make_mock_user())
        mock_repo.update_preferences = AsyncMock(return_value=_make_mock_user())
        mock_repo_cls.return_value = mock_repo

        response = auth_client.post(
            "/api/v1/user/preferences",
            json={"notification_enabled": True},
        )
        assert "Preferences updated successfully" in response.json()["message"]

    @patch("api.v1.user.UserRepository")
    def test_update_ignores_unknown_fields(self, mock_repo_cls, auth_client):
        """Unknown fields should be ignored (Pydantic model validation)."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=_make_mock_user())
        mock_repo.update_preferences = AsyncMock(return_value=_make_mock_user())
        mock_repo_cls.return_value = mock_repo

        response = auth_client.post(
            "/api/v1/user/preferences",
            json={"unknown_field": "value", "notification_enabled": True},
        )
        assert response.status_code == 200
        prefs = response.json()["preferences"]
        assert "unknown_field" not in prefs
        assert prefs["notification_enabled"] is True
