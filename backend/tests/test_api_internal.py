"""
Tests for the Internal API (backend/api/v1/internal.py)

Tests cover:
- POST /internal/observe-forecasts - backfill actual prices
- POST /internal/learn - run adaptive learning cycle
- GET /internal/observation-stats - get forecast accuracy stats
- API key authentication enforcement
- Service error handling (500)

Note: internal.py uses lazy imports (inside endpoint functions), so patches
target the service modules directly rather than api.v1.internal.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
# POST /internal/observe-forecasts
# =============================================================================


class TestObserveForecasts:
    """Tests for the POST /api/v1/internal/observe-forecasts endpoint."""

    @patch("services.observation_service.ObservationService")
    def test_observe_happy_path(self, mock_obs_cls, auth_client):
        """Observe-forecasts with no region filter should return ok status."""
        mock_obs = MagicMock()
        mock_obs.observe_actuals_batch = AsyncMock(return_value=42)
        mock_obs_cls.return_value = mock_obs

        response = auth_client.post(f"{BASE_URL}/observe-forecasts")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["observations_updated"] == 42
        assert data["region"] == "all"

        mock_obs.observe_actuals_batch.assert_awaited_once_with(region=None)

    @patch("services.observation_service.ObservationService")
    def test_observe_with_region_filter(self, mock_obs_cls, auth_client):
        """Observe-forecasts with region filter should pass it to the service."""
        mock_obs = MagicMock()
        mock_obs.observe_actuals_batch = AsyncMock(return_value=15)
        mock_obs_cls.return_value = mock_obs

        response = auth_client.post(
            f"{BASE_URL}/observe-forecasts",
            json={"region": "US_CT"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["observations_updated"] == 15
        assert data["region"] == "US_CT"

        mock_obs.observe_actuals_batch.assert_awaited_once_with(region="US_CT")

    @patch("services.observation_service.ObservationService")
    def test_observe_zero_updates(self, mock_obs_cls, auth_client):
        """When no observations are updated, count should be 0."""
        mock_obs = MagicMock()
        mock_obs.observe_actuals_batch = AsyncMock(return_value=0)
        mock_obs_cls.return_value = mock_obs

        response = auth_client.post(f"{BASE_URL}/observe-forecasts")

        assert response.status_code == 200
        data = response.json()
        assert data["observations_updated"] == 0

    @patch("services.observation_service.ObservationService")
    def test_observe_service_error(self, mock_obs_cls, auth_client):
        """Service exception should return 500 with error detail."""
        mock_obs = MagicMock()
        mock_obs.observe_actuals_batch = AsyncMock(
            side_effect=RuntimeError("Database connection lost")
        )
        mock_obs_cls.return_value = mock_obs

        response = auth_client.post(f"{BASE_URL}/observe-forecasts")

        assert response.status_code == 500
        assert "Observation failed" in response.json()["detail"]
        assert "Database connection lost" in response.json()["detail"]

    def test_observe_requires_api_key(self, unauth_client):
        """Request without X-API-Key header should be rejected."""
        response = unauth_client.post(f"{BASE_URL}/observe-forecasts")

        # verify_api_key returns 401 when no API key is provided
        assert response.status_code == 401


# =============================================================================
# POST /internal/learn
# =============================================================================


class TestLearnCycle:
    """Tests for the POST /api/v1/internal/learn endpoint."""

    @patch("services.learning_service.LearningService")
    @patch("services.hnsw_vector_store.HNSWVectorStore")
    @patch("services.observation_service.ObservationService")
    def test_learn_happy_path(self, mock_obs_cls, mock_vs_cls, mock_learner_cls, auth_client):
        """Learn with default params should run full cycle and return results."""
        mock_results = {
            "regions_processed": ["US"],
            "accuracy": {"US": 0.87},
            "weights_updated": True,
            "bias_corrections": 3,
        }

        mock_learner = MagicMock()
        mock_learner.run_full_cycle = AsyncMock(return_value=mock_results)
        mock_learner_cls.return_value = mock_learner

        response = auth_client.post(f"{BASE_URL}/learn")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["results"]["regions_processed"] == ["US"]
        assert data["results"]["weights_updated"] is True

        # Default params: regions=None, days=7
        mock_learner.run_full_cycle.assert_awaited_once_with(
            regions=None,
            days=7,
        )

    @patch("services.learning_service.LearningService")
    @patch("services.hnsw_vector_store.HNSWVectorStore")
    @patch("services.observation_service.ObservationService")
    def test_learn_custom_regions_and_days(self, mock_obs_cls, mock_vs_cls, mock_learner_cls, auth_client):
        """Learn with custom regions and days should pass them through."""
        mock_learner = MagicMock()
        mock_learner.run_full_cycle = AsyncMock(return_value={"regions_processed": ["US_CT", "US_TX"]})
        mock_learner_cls.return_value = mock_learner

        response = auth_client.post(
            f"{BASE_URL}/learn",
            json={"regions": ["US_CT", "US_TX"], "days": 14},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

        mock_learner.run_full_cycle.assert_awaited_once_with(
            regions=["US_CT", "US_TX"],
            days=14,
        )

    @patch("services.learning_service.LearningService")
    @patch("services.hnsw_vector_store.HNSWVectorStore")
    @patch("services.observation_service.ObservationService")
    def test_learn_service_error(self, mock_obs_cls, mock_vs_cls, mock_learner_cls, auth_client):
        """Service exception during learning should return 500."""
        mock_learner = MagicMock()
        mock_learner.run_full_cycle = AsyncMock(
            side_effect=RuntimeError("Redis unavailable")
        )
        mock_learner_cls.return_value = mock_learner

        response = auth_client.post(f"{BASE_URL}/learn")

        assert response.status_code == 500
        assert "Learning cycle failed" in response.json()["detail"]
        assert "Redis unavailable" in response.json()["detail"]

    def test_learn_requires_api_key(self, unauth_client):
        """Request without X-API-Key header should be rejected."""
        response = unauth_client.post(f"{BASE_URL}/learn")

        assert response.status_code == 401

    @patch("services.learning_service.LearningService")
    @patch("services.hnsw_vector_store.HNSWVectorStore")
    @patch("services.observation_service.ObservationService")
    def test_learn_empty_results(self, mock_obs_cls, mock_vs_cls, mock_learner_cls, auth_client):
        """Learning cycle that produces empty results should still return ok."""
        mock_learner = MagicMock()
        mock_learner.run_full_cycle = AsyncMock(return_value={})
        mock_learner_cls.return_value = mock_learner

        response = auth_client.post(f"{BASE_URL}/learn")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["results"] == {}


# =============================================================================
# GET /internal/observation-stats
# =============================================================================


class TestObservationStats:
    """Tests for the GET /api/v1/internal/observation-stats endpoint."""

    @patch("services.observation_service.ObservationService")
    def test_stats_happy_path(self, mock_obs_cls, auth_client):
        """Stats with defaults should return accuracy and hourly_bias."""
        mock_obs = MagicMock()
        mock_obs.get_forecast_accuracy = AsyncMock(return_value={
            "mape": 0.08,
            "rmse": 0.012,
            "sample_size": 168,
        })
        mock_obs.get_hourly_bias = AsyncMock(return_value={
            str(h): round(0.002 * (h - 12), 4)
            for h in range(24)
        })
        mock_obs_cls.return_value = mock_obs

        response = auth_client.get(f"{BASE_URL}/observation-stats")

        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "US"
        assert data["days"] == 7
        assert data["accuracy"]["mape"] == 0.08
        assert data["accuracy"]["sample_size"] == 168
        assert "hourly_bias" in data
        assert len(data["hourly_bias"]) == 24

        mock_obs.get_forecast_accuracy.assert_awaited_once_with("US", 7)
        mock_obs.get_hourly_bias.assert_awaited_once_with("US", 7)

    @patch("services.observation_service.ObservationService")
    def test_stats_custom_params(self, mock_obs_cls, auth_client):
        """Stats with custom region and days should pass them to service."""
        mock_obs = MagicMock()
        mock_obs.get_forecast_accuracy = AsyncMock(return_value={"mape": 0.05})
        mock_obs.get_hourly_bias = AsyncMock(return_value={})
        mock_obs_cls.return_value = mock_obs

        response = auth_client.get(f"{BASE_URL}/observation-stats?region=US_CT&days=30")

        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "US_CT"
        assert data["days"] == 30

        mock_obs.get_forecast_accuracy.assert_awaited_once_with("US_CT", 30)
        mock_obs.get_hourly_bias.assert_awaited_once_with("US_CT", 30)

    @patch("services.observation_service.ObservationService")
    def test_stats_service_error(self, mock_obs_cls, auth_client):
        """Service exception during stats should return 500."""
        mock_obs = MagicMock()
        mock_obs.get_forecast_accuracy = AsyncMock(
            side_effect=RuntimeError("Query timeout")
        )
        mock_obs_cls.return_value = mock_obs

        response = auth_client.get(f"{BASE_URL}/observation-stats")

        assert response.status_code == 500
        assert "Query timeout" in response.json()["detail"]

    def test_stats_requires_api_key(self, unauth_client):
        """Request without X-API-Key header should be rejected."""
        response = unauth_client.get(f"{BASE_URL}/observation-stats")

        assert response.status_code == 401

    @patch("services.observation_service.ObservationService")
    def test_stats_empty_accuracy(self, mock_obs_cls, auth_client):
        """When no observations exist, should return empty accuracy and bias."""
        mock_obs = MagicMock()
        mock_obs.get_forecast_accuracy = AsyncMock(return_value=None)
        mock_obs.get_hourly_bias = AsyncMock(return_value=None)
        mock_obs_cls.return_value = mock_obs

        response = auth_client.get(f"{BASE_URL}/observation-stats")

        assert response.status_code == 200
        data = response.json()
        assert data["accuracy"] is None
        assert data["hourly_bias"] is None


# =============================================================================
# POST /internal/check-alerts
# =============================================================================


class TestCheckAlerts:
    """Tests for POST /api/v1/internal/check-alerts."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_config(
        user_id="user-1",
        email="test@example.com",
        region="us_ct",
        price_below=None,
        price_above=None,
        notify_optimal_windows=True,
        notification_frequency="daily",
    ):
        from decimal import Decimal
        return {
            "id": "cfg-1",
            "user_id": user_id,
            "email": email,
            "region": region,
            "currency": "USD",
            "price_below": Decimal(str(price_below)) if price_below else None,
            "price_above": Decimal(str(price_above)) if price_above else None,
            "notify_optimal_windows": notify_optimal_windows,
            "notification_frequency": notification_frequency,
        }

    # ------------------------------------------------------------------
    # Happy path — no active configs
    # ------------------------------------------------------------------

    @patch("services.alert_service.AlertService")
    @patch("repositories.price_repository.PriceRepository")
    def test_no_active_configs_returns_zeros(
        self, mock_repo_cls, mock_svc_cls, auth_client
    ):
        """When there are no active alert configs the endpoint returns all zeros."""
        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(return_value=[])
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/check-alerts")

        assert response.status_code == 200
        data = response.json()
        assert data == {"checked": 0, "triggered": 0, "sent": 0, "deduplicated": 0}

    # ------------------------------------------------------------------
    # Happy path — config present, price triggers, alert sent
    # ------------------------------------------------------------------

    @patch("services.alert_service.AlertService")
    @patch("repositories.price_repository.PriceRepository")
    def test_alert_triggered_and_sent(
        self, mock_repo_cls, mock_svc_cls, auth_client, mock_db
    ):
        """A triggered alert that passes dedup should be sent and recorded."""
        from decimal import Decimal
        from services.alert_service import AlertThreshold, PriceAlert
        from datetime import datetime, timezone

        cfg = self._make_config(price_below=0.25, notification_frequency="immediate")

        # Build a synthetic threshold and alert as check_thresholds() would return
        threshold = AlertThreshold(
            user_id=cfg["user_id"],
            email=cfg["email"],
            price_below=Decimal("0.25"),
            region=cfg["region"],
            currency="USD",
        )
        alert = PriceAlert(
            alert_type="price_drop",
            current_price=Decimal("0.20"),
            threshold=Decimal("0.25"),
            region="us_ct",
            supplier="Eversource Energy",
            timestamp=datetime.now(timezone.utc),
        )

        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(return_value=[cfg])
        mock_svc.check_thresholds = MagicMock(return_value=[(threshold, alert)])
        mock_svc._should_send_alert = AsyncMock(return_value=True)
        mock_svc.send_alerts = AsyncMock(return_value=1)
        mock_svc.record_triggered_alert = AsyncMock(return_value={})
        mock_svc_cls.return_value = mock_svc

        mock_repo = MagicMock()
        mock_repo.list = AsyncMock(return_value=[MagicMock(region="us_ct", price_per_kwh=Decimal("0.20"))])
        mock_repo_cls.return_value = mock_repo

        response = auth_client.post(f"{BASE_URL}/check-alerts")

        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] == 1
        assert data["sent"] == 1
        assert data["deduplicated"] == 0

        mock_svc.send_alerts.assert_awaited_once_with([(threshold, alert)])
        mock_svc.record_triggered_alert.assert_awaited_once()

    # ------------------------------------------------------------------
    # Deduplication — alert suppressed by cooldown
    # ------------------------------------------------------------------

    @patch("services.alert_service.AlertService")
    @patch("repositories.price_repository.PriceRepository")
    def test_alert_deduplicated(
        self, mock_repo_cls, mock_svc_cls, auth_client
    ):
        """When _should_send_alert returns False the alert must be deduplicated."""
        from decimal import Decimal
        from services.alert_service import AlertThreshold, PriceAlert
        from datetime import datetime, timezone

        cfg = self._make_config(price_below=0.25, notification_frequency="daily")

        threshold = AlertThreshold(
            user_id=cfg["user_id"],
            email=cfg["email"],
            price_below=Decimal("0.25"),
            region=cfg["region"],
            currency="USD",
        )
        alert = PriceAlert(
            alert_type="price_drop",
            current_price=Decimal("0.20"),
            threshold=Decimal("0.25"),
            region="us_ct",
            supplier="Eversource Energy",
            timestamp=datetime.now(timezone.utc),
        )

        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(return_value=[cfg])
        mock_svc.check_thresholds = MagicMock(return_value=[(threshold, alert)])
        mock_svc._should_send_alert = AsyncMock(return_value=False)  # inside cooldown
        mock_svc.send_alerts = AsyncMock(return_value=0)
        mock_svc.record_triggered_alert = AsyncMock(return_value={})
        mock_svc_cls.return_value = mock_svc

        mock_repo = MagicMock()
        mock_repo.list = AsyncMock(return_value=[MagicMock(region="us_ct", price_per_kwh=Decimal("0.20"))])
        mock_repo_cls.return_value = mock_repo

        response = auth_client.post(f"{BASE_URL}/check-alerts")

        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] == 1
        assert data["sent"] == 0
        assert data["deduplicated"] == 1

        # send_alerts must be called with an empty list
        mock_svc.send_alerts.assert_awaited_once_with([])
        # No history record when deduplicated
        mock_svc.record_triggered_alert.assert_not_awaited()

    # ------------------------------------------------------------------
    # No prices available for the region
    # ------------------------------------------------------------------

    @patch("services.alert_service.AlertService")
    @patch("repositories.price_repository.PriceRepository")
    def test_no_prices_returns_zero_triggered(
        self, mock_repo_cls, mock_svc_cls, auth_client
    ):
        """When the price repo returns empty lists, no alerts are triggered."""
        cfg = self._make_config(price_below=0.25)

        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(return_value=[cfg])
        mock_svc.check_thresholds = MagicMock(return_value=[])
        mock_svc.send_alerts = AsyncMock(return_value=0)
        mock_svc_cls.return_value = mock_svc

        mock_repo = MagicMock()
        mock_repo.list = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        response = auth_client.post(f"{BASE_URL}/check-alerts")

        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] == 0
        assert data["sent"] == 0
        assert data["deduplicated"] == 0

    # ------------------------------------------------------------------
    # Price fetch failure is tolerated
    # ------------------------------------------------------------------

    @patch("services.alert_service.AlertService")
    @patch("repositories.price_repository.PriceRepository")
    def test_price_fetch_error_is_tolerated(
        self, mock_repo_cls, mock_svc_cls, auth_client
    ):
        """A price fetch error for a region should be logged and skipped, not 500."""
        cfg = self._make_config(region="us_ct")

        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(return_value=[cfg])
        mock_svc.check_thresholds = MagicMock(return_value=[])
        mock_svc.send_alerts = AsyncMock(return_value=0)
        mock_svc_cls.return_value = mock_svc

        mock_repo = MagicMock()
        mock_repo.list = AsyncMock(side_effect=RuntimeError("DB unavailable"))
        mock_repo_cls.return_value = mock_repo

        response = auth_client.post(f"{BASE_URL}/check-alerts")

        # Endpoint must survive the price fetch failure
        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] == 0

    # ------------------------------------------------------------------
    # Service-level exception → 500
    # ------------------------------------------------------------------

    @patch("services.alert_service.AlertService")
    @patch("repositories.price_repository.PriceRepository")
    def test_service_exception_returns_500(
        self, mock_repo_cls, mock_svc_cls, auth_client
    ):
        """An unhandled exception inside get_active_alert_configs should return 500."""
        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(
            side_effect=RuntimeError("Neon connection lost")
        )
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/check-alerts")

        assert response.status_code == 500
        assert "Alert check failed" in response.json()["detail"]
        assert "Neon connection lost" in response.json()["detail"]

    # ------------------------------------------------------------------
    # API key enforcement
    # ------------------------------------------------------------------

    def test_requires_api_key(self, unauth_client):
        """Request without X-API-Key header must be rejected with 401."""
        response = unauth_client.post(f"{BASE_URL}/check-alerts")

        assert response.status_code == 401

    # ------------------------------------------------------------------
    # Multiple configs, mixed dedup outcomes
    # ------------------------------------------------------------------

    @patch("services.alert_service.AlertService")
    @patch("repositories.price_repository.PriceRepository")
    def test_mixed_dedup_outcomes(
        self, mock_repo_cls, mock_svc_cls, auth_client
    ):
        """2 triggered alerts: 1 sent, 1 deduplicated — counts must match."""
        from decimal import Decimal
        from services.alert_service import AlertThreshold, PriceAlert
        from datetime import datetime, timezone

        def _threshold(uid, email):
            return AlertThreshold(
                user_id=uid, email=email,
                price_below=Decimal("0.25"), region="us_ct", currency="USD",
            )

        def _alert(uid):
            return PriceAlert(
                alert_type="price_drop",
                current_price=Decimal("0.20"),
                threshold=Decimal("0.25"),
                region="us_ct",
                supplier="Test",
                timestamp=datetime.now(timezone.utc),
            )

        t1, a1 = _threshold("user-1", "a@example.com"), _alert("user-1")
        t2, a2 = _threshold("user-2", "b@example.com"), _alert("user-2")

        cfg1 = self._make_config(user_id="user-1", email="a@example.com", price_below=0.25, notification_frequency="daily")
        cfg2 = self._make_config(user_id="user-2", email="b@example.com", price_below=0.25, notification_frequency="weekly")
        cfg1["id"] = "cfg-1"
        cfg2["id"] = "cfg-2"

        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(return_value=[cfg1, cfg2])
        mock_svc.check_thresholds = MagicMock(return_value=[(t1, a1), (t2, a2)])
        # user-1 passes, user-2 is in cooldown
        mock_svc._should_send_alert = AsyncMock(side_effect=[True, False])
        mock_svc.send_alerts = AsyncMock(return_value=1)
        mock_svc.record_triggered_alert = AsyncMock(return_value={})
        mock_svc_cls.return_value = mock_svc

        mock_repo = MagicMock()
        mock_repo.list = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        response = auth_client.post(f"{BASE_URL}/check-alerts")

        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] == 2
        assert data["sent"] == 1
        assert data["deduplicated"] == 1

        # Only the non-deduplicated alert should be passed to send_alerts
        mock_svc.send_alerts.assert_awaited_once_with([(t1, a1)])
        # Only one history record written
        mock_svc.record_triggered_alert.assert_awaited_once()


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


# =============================================================================
# POST /internal/scrape-rates (auto-discovery)
# =============================================================================


class TestScrapeRatesAutoDiscovery:
    """Tests for the auto-discovery behavior when no supplier_urls provided."""

    @patch("services.rate_scraper_service.RateScraperService")
    def test_explicit_urls(self, mock_svc_cls, auth_client, mock_db):
        """Providing explicit supplier_urls should use them directly."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 1,
            "succeeded": 1,
            "failed": 0,
            "errors": [],
            "results": [{"supplier_id": "s1", "extracted_data": {}, "success": True}],
        })
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "s1", "url": "https://example.com"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total"] == 1
        assert data["succeeded"] == 1
        assert data["failed"] == 0

        mock_svc.scrape_supplier_rates.assert_awaited_once_with(
            [{"supplier_id": "s1", "url": "https://example.com"}]
        )

    @patch("services.rate_scraper_service.RateScraperService")
    def test_empty_body_auto_discovers(self, mock_svc_cls, auth_client, mock_db):
        """Empty body should trigger DB auto-discovery of suppliers with websites."""
        # Mock DB execute to return suppliers with websites
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("id-1", "SupplierA", "https://a.com/rates"),
            ("id-2", "SupplierB", "https://b.com/rates"),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 2,
            "succeeded": 2,
            "failed": 0,
            "errors": [],
            "results": [
                {"supplier_id": "id-1", "success": True},
                {"supplier_id": "id-2", "success": True},
            ],
        })
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/scrape-rates")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2

    @patch("services.rate_scraper_service.RateScraperService")
    def test_no_suppliers_found(self, mock_svc_cls, auth_client, mock_db):
        """When no suppliers have websites, return empty results."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = auth_client.post(f"{BASE_URL}/scrape-rates")

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert "No suppliers" in data.get("message", "")


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


# =============================================================================
# POST /internal/kpi-report
# =============================================================================


class TestKPIReport:
    """Tests for POST /api/v1/internal/kpi-report."""

    @patch("services.kpi_report_service.KPIReportService")
    def test_happy_path(self, mock_svc_cls, auth_client):
        """KPI report should return status + metrics."""
        mock_svc = MagicMock()
        mock_svc.aggregate_metrics = AsyncMock(return_value={
            "active_users_7d": 42,
            "total_users": 100,
            "prices_tracked": 5000,
            "alerts_sent_today": 15,
            "connections_active": {"active": 10},
            "subscription_breakdown": {"free": 80, "pro": 15, "business": 5},
            "estimated_mrr": 149.80,
            "weather_freshness_hours": 3.2,
        })
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
        mock_svc.aggregate_metrics = AsyncMock(
            side_effect=RuntimeError("Query failed")
        )
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/kpi-report")

        assert response.status_code == 500
        assert "KPI report failed" in response.json()["detail"]

    def test_requires_api_key(self, unauth_client):
        """Request without X-API-Key header must be rejected."""
        response = unauth_client.post(f"{BASE_URL}/kpi-report")
        assert response.status_code == 401


# =============================================================================
# POST /internal/fetch-weather (persistence)
# =============================================================================


class TestFetchWeatherPersistence:
    """Tests for weather data persistence in POST /api/v1/internal/fetch-weather."""

    @patch("services.weather_service.WeatherService")
    def test_weather_persists_to_db(self, mock_svc_cls, auth_client, mock_db):
        """Weather results should be inserted into weather_cache table."""
        mock_svc = MagicMock()
        mock_svc.fetch_weather_for_regions = AsyncMock(return_value={
            "NY": {"temp_f": 72.5, "humidity": 65, "wind_mph": 8.2, "description": "partly cloudy"},
            "CA": {"temp_f": 85.0, "humidity": 30, "wind_mph": 3.1, "description": "clear sky"},
        })
        mock_svc_cls.return_value = mock_svc

        mock_db.execute = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/fetch-weather",
            json={"regions": ["NY", "CA"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["regions_fetched"] == 2
        assert data["persisted"] == 2

        # Verify 2 INSERT calls were made
        assert mock_db.execute.await_count == 2
        mock_db.commit.assert_awaited_once()

    @patch("services.weather_service.WeatherService")
    def test_weather_defaults_to_all_states(self, mock_svc_cls, auth_client, mock_db):
        """Empty body should default to all 51 US state regions."""
        mock_svc = MagicMock()
        mock_svc.fetch_weather_for_regions = AsyncMock(return_value={})
        mock_svc_cls.return_value = mock_svc

        mock_db.execute = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock(return_value=None)

        # No body — should use all-states default
        response = auth_client.post(f"{BASE_URL}/fetch-weather")

        assert response.status_code == 200
        # Verify service was called with all 51 states
        call_args = mock_svc.fetch_weather_for_regions.call_args[0][0]
        assert len(call_args) == 51
        assert "NY" in call_args
        assert "CA" in call_args

    @patch("services.weather_service.WeatherService")
    def test_weather_no_results_no_persist(self, mock_svc_cls, auth_client, mock_db):
        """Empty weather results should not trigger any DB writes."""
        mock_svc = MagicMock()
        mock_svc.fetch_weather_for_regions = AsyncMock(return_value={})
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(
            f"{BASE_URL}/fetch-weather",
            json={"regions": ["NY"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["persisted"] == 0
        mock_db.execute.assert_not_awaited()

    @patch("services.weather_service.WeatherService")
    def test_weather_persist_error_tolerated(self, mock_svc_cls, auth_client, mock_db):
        """DB insert failures should be logged and tolerated, not cause 500."""
        mock_svc = MagicMock()
        mock_svc.fetch_weather_for_regions = AsyncMock(return_value={
            "NY": {"temp_f": 72.5, "humidity": 65, "wind_mph": 8.2, "description": "clear"},
        })
        mock_svc_cls.return_value = mock_svc

        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB write failed"))
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/fetch-weather",
            json={"regions": ["NY"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["regions_fetched"] == 1
        assert data["persisted"] == 0


# =============================================================================
# POST /internal/market-research (persistence)
# =============================================================================


class TestMarketResearchPersistence:
    """Tests for market research data persistence."""

    @patch("services.market_intelligence_service.MarketIntelligenceService")
    def test_market_research_persists_to_db(self, mock_svc_cls, auth_client, mock_db):
        """Market scan results should be inserted into market_intelligence table."""
        mock_svc = MagicMock()
        mock_svc.weekly_market_scan = AsyncMock(return_value=[
            {
                "query": "NY electricity rate change 2026",
                "data": {
                    "answer": "Rates are increasing",
                    "results": [
                        {"title": "NY Rate Hike", "url": "https://example.com/1", "content": "..."},
                        {"title": "Energy Report", "url": "https://example.com/2", "content": "..."},
                    ],
                },
            },
        ])
        mock_svc_cls.return_value = mock_svc

        mock_db.execute = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/market-research",
            json={"regions": ["NY"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["persisted"] == 2  # 2 results in the scan

        assert mock_db.execute.await_count == 2
        mock_db.commit.assert_awaited_once()

    @patch("services.market_intelligence_service.MarketIntelligenceService")
    def test_market_research_no_results_no_persist(self, mock_svc_cls, auth_client, mock_db):
        """Empty market scan should not trigger DB writes."""
        mock_svc = MagicMock()
        mock_svc.weekly_market_scan = AsyncMock(return_value=[])
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(
            f"{BASE_URL}/market-research",
            json={"regions": ["NY"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["persisted"] == 0


# =============================================================================
# POST /internal/scrape-rates (persistence)
# =============================================================================


class TestScrapeRatesPersistence:
    """Tests for scraped rates data persistence."""

    @patch("services.rate_scraper_service.RateScraperService")
    def test_scrape_results_persisted(self, mock_svc_cls, auth_client, mock_db):
        """Scrape results should be inserted into scraped_rates table."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 1,
            "succeeded": 1,
            "failed": 0,
            "errors": [],
            "results": [{"supplier_id": "s1", "extracted_data": {"rates": [1.5]}, "success": True}],
        })
        mock_svc_cls.return_value = mock_svc

        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "s1", "url": "https://example.com", "name": "Test"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["persisted"] == 1

        mock_db.commit.assert_awaited_once()


# =============================================================================
# POST /internal/scrape-rates — batch summary endpoint tests
# =============================================================================


class TestScrapeRatesBatchSummary:
    """Endpoint-level tests for the batch summary response format.

    The service layer now returns a summary dict rather than a raw list.
    These tests verify the endpoint exposes all summary fields correctly.
    """

    @patch("services.rate_scraper_service.RateScraperService")
    def test_endpoint_exposes_succeeded_and_failed_counts(self, mock_svc_cls, auth_client, mock_db):
        """Response includes succeeded/failed counts from the batch summary."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 3,
            "succeeded": 2,
            "failed": 1,
            "errors": [{"supplier_id": "bad", "error": "HTTP 503"}],
            "results": [
                {"supplier_id": "s1", "success": True, "extracted_data": {}},
                {"supplier_id": "s2", "success": True, "extracted_data": {}},
                {"supplier_id": "bad", "success": False, "extracted_data": None},
            ],
        })
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={
                "supplier_urls": [
                    {"supplier_id": "s1", "url": "https://s1.com"},
                    {"supplier_id": "s2", "url": "https://s2.com"},
                    {"supplier_id": "bad", "url": "https://bad.com"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total"] == 3
        assert data["succeeded"] == 2
        assert data["failed"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["supplier_id"] == "bad"

    @patch("services.rate_scraper_service.RateScraperService")
    def test_partial_failure_does_not_return_500(self, mock_svc_cls, auth_client, mock_db):
        """A batch with failures must not cause a 500 — partial success is still 200."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 5,
            "succeeded": 3,
            "failed": 2,
            "errors": [
                {"supplier_id": "fail1", "error": "timeout"},
                {"supplier_id": "fail2", "error": "Connection refused"},
            ],
            "results": [
                {"supplier_id": "ok1", "success": True, "extracted_data": {}},
                {"supplier_id": "ok2", "success": True, "extracted_data": {}},
                {"supplier_id": "ok3", "success": True, "extracted_data": {}},
                {"supplier_id": "fail1", "success": False, "extracted_data": None, "error": "timeout"},
                {"supplier_id": "fail2", "success": False, "extracted_data": None, "error": "Connection refused"},
            ],
        })
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        mock_db.commit = AsyncMock(return_value=None)

        suppliers = [
            {"supplier_id": f"ok{i}", "url": f"https://ok{i}.com"} for i in range(1, 4)
        ] + [
            {"supplier_id": "fail1", "url": "https://slow.com"},
            {"supplier_id": "fail2", "url": "https://down.com"},
        ]
        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": suppliers},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["failed"] == 2
        assert data["succeeded"] == 3

    @patch("services.rate_scraper_service.RateScraperService")
    def test_all_fail_still_returns_200(self, mock_svc_cls, auth_client, mock_db):
        """Even if every supplier fails, the endpoint returns 200 with the summary."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 2,
            "succeeded": 0,
            "failed": 2,
            "errors": [
                {"supplier_id": "a", "error": "timeout"},
                {"supplier_id": "b", "error": "HTTP 404"},
            ],
            "results": [
                {"supplier_id": "a", "success": False, "extracted_data": None, "error": "timeout"},
                {"supplier_id": "b", "success": False, "extracted_data": None, "error": "HTTP 404"},
            ],
        })
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [
                {"supplier_id": "a", "url": "https://a.com"},
                {"supplier_id": "b", "url": "https://b.com"},
            ]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total"] == 2
        assert data["succeeded"] == 0
        assert data["failed"] == 2

    @patch("services.rate_scraper_service.RateScraperService")
    def test_response_includes_all_summary_keys(self, mock_svc_cls, auth_client, mock_db):
        """The response must include all required batch summary fields."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 1,
            "succeeded": 1,
            "failed": 0,
            "errors": [],
            "results": [{"supplier_id": "x", "success": True, "extracted_data": {}}],
        })
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "x", "url": "https://x.com"}]},
        )

        assert response.status_code == 200
        data = response.json()
        required_keys = {"status", "total", "succeeded", "failed", "errors", "persisted", "results"}
        missing = required_keys - set(data.keys())
        assert not missing, f"Response missing keys: {missing}"


# =============================================================================
# RateScraperService unit tests (concurrency + timeout behaviour)
# =============================================================================


class TestRateScraperServiceConcurrency:
    """Unit tests for the concurrent scraping logic in RateScraperService."""

    @pytest.mark.asyncio
    async def test_scrape_all_succeed(self):
        """All suppliers succeed — summary has succeeded=3, failed=0."""
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        async def _fast_extract(url):
            return {"objects": [{"type": "price", "text": "$.12/kWh"}]}

        with patch.object(svc, "extract_rates_from_url", side_effect=_fast_extract):
            # Zero-out the 12-second rate-limit sleep so the test runs fast
            with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
                batch = await svc.scrape_supplier_rates(
                    [
                        {"supplier_id": "s1", "url": "https://a.com"},
                        {"supplier_id": "s2", "url": "https://b.com"},
                        {"supplier_id": "s3", "url": "https://c.com"},
                    ]
                )

        assert batch["total"] == 3
        assert batch["succeeded"] == 3
        assert batch["failed"] == 0
        assert batch["errors"] == []
        results = batch["results"]
        assert len(results) == 3
        assert all(r["success"] for r in results)
        sids = {r["supplier_id"] for r in results}
        assert sids == {"s1", "s2", "s3"}

    @pytest.mark.asyncio
    async def test_partial_failure_does_not_block_batch(self):
        """A failing supplier records success=False without crashing others.

        Verifies that:
        - The batch summary reflects the partial failure counts.
        - The errors list contains the failing supplier_id.
        - Successful suppliers are unaffected.
        """
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        async def _flaky_extract(url):
            if "bad" in url:
                raise httpx.HTTPStatusError(
                    "503", request=MagicMock(), response=MagicMock(status_code=503)
                )
            return {"objects": []}

        with patch.object(svc, "extract_rates_from_url", side_effect=_flaky_extract):
            with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
                batch = await svc.scrape_supplier_rates(
                    [
                        {"supplier_id": "ok1", "url": "https://good.com"},
                        {"supplier_id": "fail1", "url": "https://bad.com"},
                        {"supplier_id": "ok2", "url": "https://good2.com"},
                    ]
                )

        assert batch["total"] == 3
        assert batch["succeeded"] == 2
        assert batch["failed"] == 1
        assert len(batch["errors"]) == 1
        assert batch["errors"][0]["supplier_id"] == "fail1"

        by_id = {r["supplier_id"]: r for r in batch["results"]}
        assert by_id["ok1"]["success"] is True
        assert by_id["fail1"]["success"] is False
        assert by_id["ok2"]["success"] is True

    @pytest.mark.asyncio
    async def test_per_supplier_timeout_recorded(self):
        """Suppliers that exceed the per-call timeout are recorded with success=False."""
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        async def _hung_extract(url):
            # Simulate a hung connection: sleep longer than the patched timeout.
            # We use the real asyncio.sleep here (not the module-level mock) so
            # asyncio.wait_for can actually cancel this coroutine.
            await asyncio.sleep(10)

        # Patch only the rate-limit sleep in the service module (the one called
        # after releasing the semaphore); leave the real asyncio.wait_for + real
        # asyncio.sleep so the cancellation path works correctly.
        with patch.object(svc, "extract_rates_from_url", side_effect=_hung_extract):
            with patch("services.rate_scraper_service._PER_SUPPLIER_TIMEOUT_S", 0.01):
                # Zero-out the post-call rate-limit sleep so the test completes fast
                with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
                    batch = await svc.scrape_supplier_rates(
                        [{"supplier_id": "hung1", "url": "https://slow.com"}]
                    )

        assert batch["total"] == 1
        assert batch["succeeded"] == 0
        assert batch["failed"] == 1
        assert batch["errors"][0]["supplier_id"] == "hung1"
        assert batch["errors"][0]["error"] == "timeout"
        assert batch["results"][0]["success"] is False
        assert batch["results"][0].get("error") == "timeout"

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_summary(self):
        """An empty supplier list returns a zero summary without calling Diffbot."""
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        with patch.object(svc, "extract_rates_from_url", new=AsyncMock()) as mock_extract:
            batch = await svc.scrape_supplier_rates([])

        assert batch == {"total": 0, "succeeded": 0, "failed": 0, "errors": [], "results": []}
        mock_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_token_returns_none_for_extracted_data(self):
        """When DIFFBOT_API_TOKEN is not configured, extract returns None gracefully."""
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = ""  # empty = not configured

        # Patch the rate-limit sleep to avoid a 12-second wait in unit tests
        with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
            batch = await svc.scrape_supplier_rates(
                [{"supplier_id": "s1", "url": "https://example.com"}]
            )

        assert batch["total"] == 1
        assert batch["failed"] == 1
        # extract_rates_from_url returns None when not configured — the service
        # treats data=None as not-successful.
        assert batch["results"][0]["extracted_data"] is None
        assert batch["results"][0]["success"] is False

    @pytest.mark.asyncio
    async def test_concurrency_respects_semaphore_limit(self):
        """Peak concurrent calls must not exceed max_concurrency."""
        import asyncio as _asyncio
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        peak_concurrent = 0
        current_concurrent = 0

        async def _counting_extract(url):
            nonlocal peak_concurrent, current_concurrent
            current_concurrent += 1
            peak_concurrent = max(peak_concurrent, current_concurrent)
            await _asyncio.sleep(0.01)  # tiny delay so concurrency overlaps
            current_concurrent -= 1
            return {"objects": []}

        with patch.object(svc, "extract_rates_from_url", side_effect=_counting_extract):
            with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
                # 10 suppliers with max_concurrency=3
                suppliers = [
                    {"supplier_id": f"s{i}", "url": f"https://s{i}.com"}
                    for i in range(10)
                ]
                await svc.scrape_supplier_rates(suppliers, max_concurrency=3)

        assert peak_concurrent <= 3, (
            f"Peak concurrent calls ({peak_concurrent}) exceeded semaphore limit (3)"
        )

    @pytest.mark.asyncio
    async def test_summary_response_format_complete(self):
        """scrape_supplier_rates always returns all required summary keys."""
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        async def _mixed_extract(url):
            if "fail" in url:
                raise RuntimeError("Connection refused")
            return {"objects": []}

        with patch.object(svc, "extract_rates_from_url", side_effect=_mixed_extract):
            with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
                batch = await svc.scrape_supplier_rates(
                    [
                        {"supplier_id": "good", "url": "https://good.com"},
                        {"supplier_id": "bad", "url": "https://fail.com"},
                    ]
                )

        # All summary keys must be present
        required_keys = {"total", "succeeded", "failed", "errors", "results"}
        assert required_keys == set(batch.keys())

        # Counts must add up correctly
        assert batch["total"] == batch["succeeded"] + batch["failed"]
        assert len(batch["errors"]) == batch["failed"]
        assert len(batch["results"]) == batch["total"]

        # Error entries have supplier_id and error fields
        for err in batch["errors"]:
            assert "supplier_id" in err
            assert "error" in err


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

        mock_db.execute = AsyncMock(side_effect=[
            mock_count_result, mock_ts_result,  # electricity_prices
            mock_count_result, mock_ts_result,  # supplier_registry
            mock_count_result, mock_ts_result,  # weather_cache
            mock_count_result, mock_ts_result,  # market_intelligence
            mock_count_result, mock_ts_result,  # scraped_rates
            mock_count_result, mock_ts_result,  # alert_history
            mock_count_result, mock_ts_result,  # users
            mock_count_result, mock_ts_result,  # user_connections
            mock_count_result, mock_ts_result,  # forecast_observations
            mock_count_result, mock_ts_result,  # payment_retry_history
        ])

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
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/maintenance/cleanup")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "partial"
        assert data["activity_logs"]["deleted"] == 5
        assert "error" in data["uploads"]

    def test_cleanup_requires_api_key(self, unauth_client):
        """Request without X-API-Key header must be rejected."""
        response = unauth_client.post(f"{BASE_URL}/maintenance/cleanup")
        assert response.status_code == 401
