"""
Tests for the Integration Health Check API (backend/api/v1/health.py).

Coverage
--------
- GET /health/integrations  — all healthy, DB failure, Redis not configured,
  API keys configured / not configured, response shape, HTTP status codes.

The test overrides ``get_db_session`` and mocks ``db_manager`` to control
what the DB and Redis checks return without requiring a real Postgres or Redis
connection.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_session(healthy: bool = True):
    """Return a mock AsyncSession that succeeds or fails SELECT 1."""
    session = AsyncMock()
    if healthy:
        session.execute = AsyncMock(return_value=MagicMock())
    else:
        session.execute = AsyncMock(side_effect=Exception("DB connection refused"))
    return session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def healthy_client():
    """Client where DB is healthy and Redis is healthy."""
    from main import app
    from api.dependencies import get_db_session

    db_session = _make_db_session(healthy=True)
    app.dependency_overrides[get_db_session] = lambda: db_session

    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)

    with patch("api.v1.health.db_manager") as mock_manager:
        mock_manager.get_redis_client = AsyncMock(return_value=redis_mock)
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture()
def db_unhealthy_client():
    """Client where DB execute raises an exception."""
    from main import app
    from api.dependencies import get_db_session

    db_session = _make_db_session(healthy=False)
    app.dependency_overrides[get_db_session] = lambda: db_session

    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)

    with patch("api.v1.health.db_manager") as mock_manager:
        mock_manager.get_redis_client = AsyncMock(return_value=redis_mock)
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture()
def redis_not_configured_client():
    """Client where Redis is not configured (get_redis_client returns None)."""
    from main import app
    from api.dependencies import get_db_session

    db_session = _make_db_session(healthy=True)
    app.dependency_overrides[get_db_session] = lambda: db_session

    with patch("api.v1.health.db_manager") as mock_manager:
        mock_manager.get_redis_client = AsyncMock(return_value=None)
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture()
def redis_unhealthy_client():
    """Client where Redis is configured but ping raises."""
    from main import app
    from api.dependencies import get_db_session

    db_session = _make_db_session(healthy=True)
    app.dependency_overrides[get_db_session] = lambda: db_session

    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(side_effect=Exception("Redis connection refused"))

    with patch("api.v1.health.db_manager") as mock_manager:
        mock_manager.get_redis_client = AsyncMock(return_value=redis_mock)
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.pop(get_db_session, None)


# =============================================================================
# Response shape
# =============================================================================


class TestHealthIntegrationsShape:
    def test_response_has_status_and_integrations(self, healthy_client):
        response = healthy_client.get("/health/integrations")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "integrations" in data

    def test_response_contains_database_key(self, healthy_client):
        response = healthy_client.get("/health/integrations")
        assert "database" in response.json()["integrations"]

    def test_response_contains_redis_key(self, healthy_client):
        response = healthy_client.get("/health/integrations")
        assert "redis" in response.json()["integrations"]

    def test_response_contains_external_api_keys(self, healthy_client):
        response = healthy_client.get("/health/integrations")
        integrations = response.json()["integrations"]
        for key in ("eia", "nrel", "openweathermap", "stripe", "utilityapi",
                    "sendgrid", "gmail_oauth", "outlook_oauth",
                    "field_encryption", "internal_api_key"):
            assert key in integrations, f"Missing integration key: {key}"

    def test_database_check_has_status_field(self, healthy_client):
        response = healthy_client.get("/health/integrations")
        db_check = response.json()["integrations"]["database"]
        assert "status" in db_check

    def test_external_api_checks_have_status_field(self, healthy_client):
        response = healthy_client.get("/health/integrations")
        integrations = response.json()["integrations"]
        for key in ("eia", "nrel", "stripe"):
            assert "status" in integrations[key], f"'{key}' missing status field"


# =============================================================================
# Healthy scenario
# =============================================================================


class TestHealthyIntegrations:
    def test_overall_status_healthy(self, healthy_client):
        response = healthy_client.get("/health/integrations")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_database_status_healthy(self, healthy_client):
        response = healthy_client.get("/health/integrations")
        assert response.json()["integrations"]["database"]["status"] == "healthy"

    def test_redis_status_healthy(self, healthy_client):
        response = healthy_client.get("/health/integrations")
        assert response.json()["integrations"]["redis"]["status"] == "healthy"

    def test_database_latency_present(self, healthy_client):
        response = healthy_client.get("/health/integrations")
        db = response.json()["integrations"]["database"]
        assert "latency_ms" in db
        assert isinstance(db["latency_ms"], (int, float))
        assert db["latency_ms"] >= 0

    def test_redis_latency_present(self, healthy_client):
        response = healthy_client.get("/health/integrations")
        redis = response.json()["integrations"]["redis"]
        assert "latency_ms" in redis
        assert redis["latency_ms"] >= 0


# =============================================================================
# DB failure scenario
# =============================================================================


class TestDatabaseUnhealthy:
    def test_overall_status_degraded(self, db_unhealthy_client):
        response = db_unhealthy_client.get("/health/integrations")
        assert response.status_code == 503
        assert response.json()["status"] == "degraded"

    def test_database_status_unhealthy(self, db_unhealthy_client):
        response = db_unhealthy_client.get("/health/integrations")
        db_check = response.json()["integrations"]["database"]
        assert db_check["status"] == "unhealthy"
        assert "error" in db_check


# =============================================================================
# Redis not configured
# =============================================================================


class TestRedisNotConfigured:
    def test_overall_status_healthy_when_redis_not_configured(
        self, redis_not_configured_client
    ):
        """
        Redis is not configured in many dev / free-tier deployments.
        The endpoint should still return 200/healthy (not_configured counts as OK).
        """
        response = redis_not_configured_client.get("/health/integrations")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_redis_status_not_configured(self, redis_not_configured_client):
        response = redis_not_configured_client.get("/health/integrations")
        redis_check = response.json()["integrations"]["redis"]
        assert redis_check["status"] == "not_configured"


# =============================================================================
# Redis unhealthy
# =============================================================================


class TestRedisUnhealthy:
    def test_overall_status_degraded_when_redis_fails(self, redis_unhealthy_client):
        response = redis_unhealthy_client.get("/health/integrations")
        assert response.status_code == 503
        assert response.json()["status"] == "degraded"

    def test_redis_status_unhealthy(self, redis_unhealthy_client):
        response = redis_unhealthy_client.get("/health/integrations")
        redis_check = response.json()["integrations"]["redis"]
        assert redis_check["status"] == "unhealthy"
        assert "error" in redis_check


# =============================================================================
# External API key configuration checks
# =============================================================================


class TestExternalApiKeyChecks:
    """
    Verify that configured API keys appear as 'configured' and absent keys
    appear as 'not_configured'.  We patch settings to control what's present.
    """

    def test_eia_configured(self):
        from main import app
        from api.dependencies import get_db_session

        db_session = _make_db_session(healthy=True)
        app.dependency_overrides[get_db_session] = lambda: db_session

        redis_mock = AsyncMock()
        redis_mock.ping = AsyncMock(return_value=True)

        with patch("api.v1.health.db_manager") as mock_manager, \
             patch("api.v1.health.settings") as mock_settings:
            mock_manager.get_redis_client = AsyncMock(return_value=redis_mock)
            # Set only EIA key
            mock_settings.eia_api_key = "test-eia-key"
            mock_settings.nrel_api_key = None
            mock_settings.openweathermap_api_key = None
            mock_settings.stripe_secret_key = None
            mock_settings.utilityapi_key = None
            mock_settings.sendgrid_api_key = None
            mock_settings.gmail_client_id = None
            mock_settings.gmail_client_secret = None
            mock_settings.outlook_client_id = None
            mock_settings.outlook_client_secret = None
            mock_settings.field_encryption_key = None
            mock_settings.internal_api_key = None

            with TestClient(app) as client:
                response = client.get("/health/integrations")

        app.dependency_overrides.pop(get_db_session, None)

        assert response.status_code in (200, 503)
        integrations = response.json()["integrations"]
        assert integrations["eia"]["status"] == "configured"
        assert integrations["nrel"]["status"] == "not_configured"

    def test_stripe_not_configured(self):
        from main import app
        from api.dependencies import get_db_session

        db_session = _make_db_session(healthy=True)
        app.dependency_overrides[get_db_session] = lambda: db_session

        redis_mock = AsyncMock()
        redis_mock.ping = AsyncMock(return_value=True)

        with patch("api.v1.health.db_manager") as mock_manager, \
             patch("api.v1.health.settings") as mock_settings:
            mock_manager.get_redis_client = AsyncMock(return_value=redis_mock)
            mock_settings.eia_api_key = None
            mock_settings.nrel_api_key = None
            mock_settings.openweathermap_api_key = None
            mock_settings.stripe_secret_key = None
            mock_settings.utilityapi_key = None
            mock_settings.sendgrid_api_key = None
            mock_settings.gmail_client_id = None
            mock_settings.gmail_client_secret = None
            mock_settings.outlook_client_id = None
            mock_settings.outlook_client_secret = None
            mock_settings.field_encryption_key = None
            mock_settings.internal_api_key = None

            with TestClient(app) as client:
                response = client.get("/health/integrations")

        app.dependency_overrides.pop(get_db_session, None)

        integrations = response.json()["integrations"]
        assert integrations["stripe"]["status"] == "not_configured"


# =============================================================================
# Edge cases
# =============================================================================


class TestHealthIntegrationsEdgeCases:
    def test_no_db_session_returns_unhealthy(self):
        """When get_db_session yields None the DB check should return unhealthy."""
        from main import app
        from api.dependencies import get_db_session

        app.dependency_overrides[get_db_session] = lambda: None

        redis_mock = AsyncMock()
        redis_mock.ping = AsyncMock(return_value=True)

        with patch("api.v1.health.db_manager") as mock_manager:
            mock_manager.get_redis_client = AsyncMock(return_value=redis_mock)
            with TestClient(app) as client:
                response = client.get("/health/integrations")

        app.dependency_overrides.pop(get_db_session, None)

        data = response.json()
        assert data["integrations"]["database"]["status"] == "unhealthy"

    def test_endpoint_is_not_rate_limited(self):
        """
        /health/integrations should be reachable even when the rate limiter
        would normally block requests (exclude_paths in main.py covers /health).
        """
        from main import app
        from api.dependencies import get_db_session

        db_session = _make_db_session(healthy=True)
        app.dependency_overrides[get_db_session] = lambda: db_session

        redis_mock = AsyncMock()
        redis_mock.ping = AsyncMock(return_value=True)

        with patch("api.v1.health.db_manager") as mock_manager:
            mock_manager.get_redis_client = AsyncMock(return_value=redis_mock)
            with TestClient(app) as client:
                # Hit endpoint multiple times — should never 429
                for _ in range(5):
                    response = client.get("/health/integrations")
                    assert response.status_code != 429

        app.dependency_overrides.pop(get_db_session, None)
