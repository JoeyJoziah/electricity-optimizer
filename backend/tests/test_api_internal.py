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
        mock_svc.scrape_supplier_rates = AsyncMock(return_value=[
            {"supplier_id": "s1", "extracted_data": {}, "success": True}
        ])
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "s1", "url": "https://example.com"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total"] == 1

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
        mock_svc.scrape_supplier_rates = AsyncMock(return_value=[
            {"supplier_id": "id-1", "success": True},
            {"supplier_id": "id-2", "success": True},
        ])
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/scrape-rates")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

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
