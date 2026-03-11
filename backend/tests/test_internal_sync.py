"""
Tests for the Internal Sync API endpoint.

Covers:
- POST /internal/sync-connections — sync due UtilityAPI connections

Note: internal router uses lazy imports (inside endpoint functions), so patches
target the service modules directly rather than api.v1.internal.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session, get_redis, verify_api_key


BASE_URL = "/api/v1/internal"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
def auth_client(mock_db, mock_redis_client):
    """TestClient with API key verified and mocked DB/Redis sessions."""
    from main import app

    app.dependency_overrides[verify_api_key] = lambda: True
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis_client

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
def unauth_client(mock_db, mock_redis_client):
    """TestClient without API key override (auth not bypassed)."""
    from main import app

    # Remove the verify_api_key override so real validation runs
    app.dependency_overrides.pop(verify_api_key, None)
    # Still mock DB/Redis to avoid real connection attempts
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis_client

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


# =============================================================================
# POST /internal/sync-connections
# =============================================================================


class TestSyncConnections:
    """Tests for POST /api/v1/internal/sync-connections."""

    @patch("services.connection_sync_service.ConnectionSyncService")
    def test_sync_happy_path(self, mock_svc_cls, auth_client, mock_db):
        """Syncing due connections should return totals."""
        mock_svc = MagicMock()
        mock_svc.sync_all_due = AsyncMock(return_value=[
            {"connection_id": "c1", "success": True, "records": 5},
            {"connection_id": "c2", "success": True, "records": 3},
        ])
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/sync-connections")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0

        mock_svc.sync_all_due.assert_awaited_once()

    @patch("services.connection_sync_service.ConnectionSyncService")
    def test_sync_partial_failure(self, mock_svc_cls, auth_client, mock_db):
        """When some syncs fail, counts should reflect the split."""
        mock_svc = MagicMock()
        mock_svc.sync_all_due = AsyncMock(return_value=[
            {"connection_id": "c1", "success": True, "records": 5},
            {"connection_id": "c2", "success": False, "error": "API timeout"},
        ])
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/sync-connections")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["succeeded"] == 1
        assert data["failed"] == 1

    @patch("services.connection_sync_service.ConnectionSyncService")
    def test_sync_no_due_connections(self, mock_svc_cls, auth_client, mock_db):
        """When no connections are due, return empty results."""
        mock_svc = MagicMock()
        mock_svc.sync_all_due = AsyncMock(return_value=[])
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/sync-connections")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["succeeded"] == 0
        assert data["failed"] == 0

    @patch("services.connection_sync_service.ConnectionSyncService")
    def test_sync_service_error(self, mock_svc_cls, auth_client, mock_db):
        """Service exception should return 500."""
        mock_svc = MagicMock()
        mock_svc.sync_all_due = AsyncMock(
            side_effect=RuntimeError("UtilityAPI down")
        )
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/sync-connections")

        assert response.status_code == 500
        assert "Connection sync failed" in response.json()["detail"]

    def test_sync_requires_api_key(self, unauth_client):
        """Request without X-API-Key header must be rejected."""
        response = unauth_client.post(f"{BASE_URL}/sync-connections")
        assert response.status_code == 401
