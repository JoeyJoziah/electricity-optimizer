"""
Tests for the Internal Operations API endpoints.

Covers:
- POST /internal/kpi-report          — aggregate and return business KPIs
- GET  /internal/health-data         — table row counts and freshness check
- POST /internal/maintenance/cleanup — run data retention cleanup tasks

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
# POST /internal/kpi-report
# =============================================================================


class TestKPIReport:
    """Tests for POST /api/v1/internal/kpi-report."""

    @patch("services.kpi_report_service.KPIReportService")
    def test_happy_path(self, mock_svc_cls, auth_client):
        """KPI report should return status + metrics."""
        mock_svc = MagicMock()
        mock_svc.aggregate_metrics = AsyncMock(
            return_value={
                "active_users_7d": 42,
                "total_users": 100,
                "prices_tracked": 5000,
                "alerts_sent_today": 15,
                "connections_active": {"active": 10},
                "subscription_breakdown": {"free": 80, "pro": 15, "business": 5},
                "estimated_mrr": 149.80,
                "weather_freshness_hours": 3.2,
            }
        )
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/kpi-report")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "generated_at" in data
        assert data["metrics"]["active_users_7d"] == 42
        assert data["metrics"]["estimated_mrr"] == 149.80

    @patch("services.kpi_report_service.KPIReportService")
    def test_service_error(self, mock_svc_cls, auth_client):
        """Service exception should return 500."""
        mock_svc = MagicMock()
        mock_svc.aggregate_metrics = AsyncMock(side_effect=RuntimeError("Query failed"))
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/kpi-report")

        assert response.status_code == 500
        assert "KPI report failed" in response.json()["detail"]

    def test_requires_api_key(self, unauth_client):
        """Request without X-API-Key header must be rejected."""
        response = unauth_client.post(f"{BASE_URL}/kpi-report")
        assert response.status_code == 401


# =============================================================================
# GET /internal/health-data
# =============================================================================


class TestDataHealthCheck:
    """Tests for GET /api/v1/internal/health-data endpoint."""

    def test_health_check_happy_path(self, auth_client, mock_db):
        """Health check should return table counts and status."""
        # Mock scalar returns for COUNT and MAX queries
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 37

        mock_ts_result = MagicMock()
        mock_ts_result.scalar.return_value = "2026-03-06T12:00:00+00:00"

        mock_db.execute = AsyncMock(
            side_effect=[
                mock_count_result,
                mock_ts_result,  # electricity_prices
                mock_count_result,
                mock_ts_result,  # supplier_registry
                mock_count_result,
                mock_ts_result,  # weather_cache
                mock_count_result,
                mock_ts_result,  # market_intelligence
                mock_count_result,
                mock_ts_result,  # scraped_rates
                mock_count_result,
                mock_ts_result,  # alert_history
                mock_count_result,
                mock_ts_result,  # users
                mock_count_result,
                mock_ts_result,  # user_connections
                mock_count_result,
                mock_ts_result,  # forecast_observations
                mock_count_result,
                mock_ts_result,  # payment_retry_history
            ]
        )

        response = auth_client.get(f"{BASE_URL}/health-data")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "tables" in data
        assert "checked_at" in data
        assert data["critical_empty"] == []

    def test_health_check_flags_empty_critical(self, auth_client, mock_db):
        """Critical empty tables should be flagged in the response."""
        mock_zero_result = MagicMock()
        mock_zero_result.scalar.return_value = 0

        # All tables return 0 rows
        mock_db.execute = AsyncMock(return_value=mock_zero_result)

        response = auth_client.get(f"{BASE_URL}/health-data")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "warning"
        assert len(data["critical_empty"]) > 0
        assert "weather_cache" in data["critical_empty"]

    def test_health_check_db_unavailable(self, auth_client):
        """When DB is None, should return 503."""
        from main import app

        app.dependency_overrides[get_db_session] = lambda: None

        response = auth_client.get(f"{BASE_URL}/health-data")

        assert response.status_code == 503

        # Restore mock db
        from unittest.mock import AsyncMock

        app.dependency_overrides[get_db_session] = lambda: AsyncMock()

    def test_health_check_requires_api_key(self, unauth_client):
        """Request without X-API-Key header must be rejected."""
        response = unauth_client.get(f"{BASE_URL}/health-data")
        assert response.status_code == 401


# =============================================================================
# POST /internal/maintenance/cleanup (resilience)
# =============================================================================


class TestMaintenanceCleanup:
    """Tests for data retention cleanup endpoint."""

    @patch("services.maintenance_service.MaintenanceService")
    def test_cleanup_all_succeed(self, mock_svc_cls, auth_client):
        """All cleanup tasks succeed — status ok."""
        mock_svc = MagicMock()
        mock_svc.cleanup_activity_logs = AsyncMock(return_value={"deleted": 0})
        mock_svc.cleanup_expired_uploads = AsyncMock(return_value={"deleted": 0})
        mock_svc.cleanup_old_prices = AsyncMock(return_value={"deleted": 0})
        mock_svc.cleanup_old_observations = AsyncMock(return_value={"deleted": 0})
        mock_svc.cleanup_weather_cache = AsyncMock(
            return_value={"deleted": 0, "retention_days": 30}
        )
        mock_svc.cleanup_scraped_rates = AsyncMock(
            return_value={"deleted": 0, "retention_days": 90}
        )
        mock_svc.cleanup_market_intelligence = AsyncMock(
            return_value={"deleted": 0, "retention_days": 180}
        )
        mock_svc.cleanup_stripe_processed_events = AsyncMock(return_value={"deleted": 0})
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/maintenance/cleanup")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["activity_logs"]["deleted"] == 0

    @patch("services.maintenance_service.MaintenanceService")
    def test_cleanup_partial_failure_no_500(self, mock_svc_cls, auth_client):
        """One task failing should not crash the entire endpoint."""
        mock_svc = MagicMock()
        mock_svc.cleanup_activity_logs = AsyncMock(return_value={"deleted": 5})
        mock_svc.cleanup_expired_uploads = AsyncMock(side_effect=RuntimeError("DB timeout"))
        mock_svc.cleanup_old_prices = AsyncMock(return_value={"deleted": 0})
        mock_svc.cleanup_old_observations = AsyncMock(return_value={"deleted": 0})
        mock_svc.cleanup_weather_cache = AsyncMock(
            return_value={"deleted": 0, "retention_days": 30}
        )
        mock_svc.cleanup_scraped_rates = AsyncMock(
            return_value={"deleted": 0, "retention_days": 90}
        )
        mock_svc.cleanup_market_intelligence = AsyncMock(
            return_value={"deleted": 0, "retention_days": 180}
        )
        mock_svc.cleanup_stripe_processed_events = AsyncMock(return_value={"deleted": 0})
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/maintenance/cleanup")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "partial"
        assert data["activity_logs"]["deleted"] == 5
        assert "error" in data["uploads"]
        # Error detail must NOT leak internal exception text
        assert "DB timeout" not in data["uploads"]["error"]

    def test_cleanup_requires_api_key(self, unauth_client):
        """Request without X-API-Key header must be rejected."""
        response = unauth_client.post(f"{BASE_URL}/maintenance/cleanup")
        assert response.status_code == 401
