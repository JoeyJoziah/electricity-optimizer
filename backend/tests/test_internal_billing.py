"""
Tests for the Internal Billing API endpoint.

Covers:
- POST /internal/dunning-cycle — escalate overdue payment accounts

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
# POST /internal/dunning-cycle
# =============================================================================


class TestDunningCycle:
    """Tests for POST /api/v1/internal/dunning-cycle."""

    @patch("services.dunning_service.DunningService")
    @patch("repositories.user_repository.UserRepository")
    def test_no_overdue_accounts(self, mock_repo_cls, mock_svc_cls, auth_client):
        """No overdue accounts returns all zeros."""
        mock_svc = MagicMock()
        mock_svc.get_overdue_accounts = AsyncMock(return_value=[])
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/dunning-cycle")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["overdue_accounts"] == 0
        assert data["escalated"] == 0
        assert data["emails_sent"] == 0

    @patch("services.dunning_service.DunningService")
    @patch("repositories.user_repository.UserRepository")
    def test_happy_path_with_overdue(self, mock_repo_cls, mock_svc_cls, auth_client):
        """Overdue accounts should be emailed and escalated."""
        mock_svc = MagicMock()
        mock_svc.get_overdue_accounts = AsyncMock(return_value=[
            {
                "user_id": "user-1",
                "email": "test@example.com",
                "name": "Test",
                "retry_count": 3,
                "amount_owed": 4.99,
                "currency": "USD",
                "subscription_tier": "pro",
            },
        ])
        mock_svc.send_dunning_email = AsyncMock(return_value=True)
        mock_svc.escalate_if_needed = AsyncMock(return_value="downgraded_to_free")
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/dunning-cycle")

        assert response.status_code == 200
        data = response.json()
        assert data["overdue_accounts"] == 1
        assert data["escalated"] == 1
        assert data["emails_sent"] == 1

    @patch("services.dunning_service.DunningService")
    @patch("repositories.user_repository.UserRepository")
    def test_service_error(self, mock_repo_cls, mock_svc_cls, auth_client):
        """Service exception should return 500."""
        mock_svc = MagicMock()
        mock_svc.get_overdue_accounts = AsyncMock(
            side_effect=RuntimeError("DB error")
        )
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/dunning-cycle")

        assert response.status_code == 500
        assert "Dunning cycle failed" in response.json()["detail"]

    def test_requires_api_key(self, unauth_client):
        """Request without X-API-Key header must be rejected."""
        response = unauth_client.post(f"{BASE_URL}/dunning-cycle")
        assert response.status_code == 401
