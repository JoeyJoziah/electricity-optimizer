"""
Tests for the Internal Sync API endpoints.

Covers:
- POST /internal/sync-connections — sync due UtilityAPI connections
- POST /internal/sync-users       — backfill public.users from neon_auth.user

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
        mock_svc.sync_all_due = AsyncMock(
            return_value=[
                {"connection_id": "c1", "success": True, "records": 5},
                {"connection_id": "c2", "success": True, "records": 3},
            ]
        )
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
        mock_svc.sync_all_due = AsyncMock(
            return_value=[
                {"connection_id": "c1", "success": True, "records": 5},
                {"connection_id": "c2", "success": False, "error": "API timeout"},
            ]
        )
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
        mock_svc.sync_all_due = AsyncMock(side_effect=RuntimeError("UtilityAPI down"))
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/sync-connections")

        assert response.status_code == 500
        assert "Connection sync failed" in response.json()["detail"]

    def test_sync_requires_api_key(self, unauth_client):
        """Request without X-API-Key header must be rejected."""
        response = unauth_client.post(f"{BASE_URL}/sync-connections")
        assert response.status_code == 401


# =============================================================================
# POST /internal/sync-users
# =============================================================================


class TestSyncUsers:
    """Tests for POST /api/v1/internal/sync-users."""

    def _make_neon_row(self, neon_id: str, email: str, name: str):
        """Return a MagicMock that behaves like an asyncpg/SQLAlchemy Row."""
        row = MagicMock()
        row.neon_id = neon_id
        row.email = email
        row.name = name
        return row

    def test_sync_users_no_neon_users(self, auth_client, mock_db):
        """When neon_auth has no users, endpoint returns zeroed counts."""
        fetch_result = MagicMock()
        fetch_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=fetch_result)

        response = auth_client.post(f"{BASE_URL}/sync-users")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total"] == 0
        assert data["created"] == 0
        assert data["updated"] == 0
        assert data["skipped"] == 0

    def test_sync_users_creates_missing(self, auth_client, mock_db):
        """
        When neon_auth has users absent from public.users, they are created.

        The upsert uses RETURNING id, (xmax = 0) AS is_insert.
        For a new INSERT, .first() returns a row with is_insert=True.
        """
        neon_row = self._make_neon_row("uuid-new-1", "new@example.com", "New User")

        # 1. fetch neon_auth users
        fetch_result = MagicMock()
        fetch_result.fetchall.return_value = [neon_row]
        # 2. upsert with RETURNING → .first() returns row with is_insert=True
        upsert_result = MagicMock()
        returning_row = MagicMock()
        returning_row.is_insert = True
        upsert_result.first.return_value = returning_row

        mock_db.execute = AsyncMock(side_effect=[fetch_result, upsert_result])
        mock_db.commit = AsyncMock()

        response = auth_client.post(f"{BASE_URL}/sync-users")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total"] == 1
        assert data["created"] == 1
        assert data["updated"] == 0
        assert data["skipped"] == 0
        assert data["errors"] == []

    def test_sync_users_updates_stale(self, auth_client, mock_db):
        """
        When a user already exists but email/name has changed, it is updated.

        The upsert RETURNING clause yields is_insert=False for an UPDATE.
        """
        neon_row = self._make_neon_row(
            "uuid-stale-1", "changed@example.com", "Updated Name"
        )

        fetch_result = MagicMock()
        fetch_result.fetchall.return_value = [neon_row]
        upsert_result = MagicMock()
        returning_row = MagicMock()
        returning_row.is_insert = False
        upsert_result.first.return_value = returning_row

        mock_db.execute = AsyncMock(side_effect=[fetch_result, upsert_result])
        mock_db.commit = AsyncMock()

        response = auth_client.post(f"{BASE_URL}/sync-users")

        assert response.status_code == 200
        data = response.json()
        assert data["updated"] == 1
        assert data["created"] == 0

    def test_sync_users_skips_already_synced(self, auth_client, mock_db):
        """
        When the user is already in sync (no email/name change), the RETURNING
        clause yields no row (WHERE condition not met) → .first() returns None.
        """
        neon_row = self._make_neon_row("uuid-ok-1", "synced@example.com", "Synced User")

        fetch_result = MagicMock()
        fetch_result.fetchall.return_value = [neon_row]
        upsert_result = MagicMock()
        upsert_result.first.return_value = None  # no row returned → skipped

        mock_db.execute = AsyncMock(side_effect=[fetch_result, upsert_result])
        mock_db.commit = AsyncMock()

        response = auth_client.post(f"{BASE_URL}/sync-users")

        assert response.status_code == 200
        data = response.json()
        assert data["skipped"] == 1
        assert data["created"] == 0
        assert data["updated"] == 0

    def test_sync_users_row_error_continues(self, auth_client, mock_db):
        """
        When one row raises an exception, the rest of the batch continues
        and the endpoint returns status='partial' with an errors list.
        """
        row1 = self._make_neon_row("uuid-err-1", "bad@example.com", "Bad User")
        row2 = self._make_neon_row("uuid-ok-2", "good@example.com", "Good User")

        fetch_result = MagicMock()
        fetch_result.fetchall.return_value = [row1, row2]

        # row2: upsert succeeds with RETURNING → .first() returns is_insert=True
        upsert_ok_result = MagicMock()
        returning_row = MagicMock()
        returning_row.is_insert = True
        upsert_ok_result.first.return_value = returning_row

        call_count = 0

        async def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return fetch_result
            if call_count == 2:
                raise Exception("constraint violation")
            if call_count == 3:
                return upsert_ok_result

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        response = auth_client.post(f"{BASE_URL}/sync-users")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "partial"
        assert len(data["errors"]) == 1
        assert data["errors"][0]["user_id"] == "uuid-err-1"

    def test_sync_users_requires_api_key(self, unauth_client):
        """Request without X-API-Key must be rejected with 401."""
        response = unauth_client.post(f"{BASE_URL}/sync-users")
        assert response.status_code == 401
