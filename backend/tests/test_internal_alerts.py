"""
Tests for the Internal Alerts API endpoint.

Covers:
- POST /internal/check-alerts — evaluate price thresholds and send alerts

Note: internal router uses lazy imports (inside endpoint functions), so patches
target the service modules directly rather than api.v1.internal.
"""

from datetime import UTC
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
    def test_no_active_configs_returns_zeros(self, mock_repo_cls, mock_svc_cls, auth_client):
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
    def test_alert_triggered_and_sent(self, mock_repo_cls, mock_svc_cls, auth_client, mock_db):
        """A triggered alert that passes dedup should be sent and recorded."""
        from datetime import datetime
        from decimal import Decimal

        from services.alert_service import AlertThreshold, PriceAlert

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
            timestamp=datetime.now(UTC),
        )

        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(return_value=[cfg])
        mock_svc.check_thresholds = MagicMock(return_value=[(threshold, alert)])
        mock_svc._batch_should_send_alerts = AsyncMock(return_value=set())  # nothing in cooldown
        # send_alerts now returns List[bool] — one True for the single successful send
        mock_svc.send_alerts = AsyncMock(return_value=[True])
        mock_svc.record_triggered_alert = AsyncMock(return_value={})
        mock_svc_cls.return_value = mock_svc

        mock_repo = MagicMock()
        mock_repo.list = AsyncMock(
            return_value=[MagicMock(region="us_ct", price_per_kwh=Decimal("0.20"))]
        )
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
    def test_alert_deduplicated(self, mock_repo_cls, mock_svc_cls, auth_client):
        """When _should_send_alert returns False the alert must be deduplicated."""
        from datetime import datetime
        from decimal import Decimal

        from services.alert_service import AlertThreshold, PriceAlert

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
            timestamp=datetime.now(UTC),
        )

        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(return_value=[cfg])
        mock_svc.check_thresholds = MagicMock(return_value=[(threshold, alert)])
        # Batch returns the key as "in cooldown" → should be deduplicated
        mock_svc._batch_should_send_alerts = AsyncMock(
            return_value={(cfg["user_id"], "price_drop", "us_ct")}
        )
        # send_alerts now returns List[bool] — empty list because to_send is empty
        mock_svc.send_alerts = AsyncMock(return_value=[])
        mock_svc.record_triggered_alert = AsyncMock(return_value={})
        mock_svc_cls.return_value = mock_svc

        mock_repo = MagicMock()
        mock_repo.list = AsyncMock(
            return_value=[MagicMock(region="us_ct", price_per_kwh=Decimal("0.20"))]
        )
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
    def test_no_prices_returns_zero_triggered(self, mock_repo_cls, mock_svc_cls, auth_client):
        """When the price repo returns empty lists, no alerts are triggered."""
        cfg = self._make_config(price_below=0.25)

        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(return_value=[cfg])
        mock_svc.check_thresholds = MagicMock(return_value=[])
        mock_svc._batch_should_send_alerts = AsyncMock(return_value=set())
        # send_alerts now returns List[bool] — empty list when nothing to send
        mock_svc.send_alerts = AsyncMock(return_value=[])
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
    def test_price_fetch_error_is_tolerated(self, mock_repo_cls, mock_svc_cls, auth_client):
        """A price fetch error for a region should be logged and skipped, not 500."""
        cfg = self._make_config(region="us_ct")

        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(return_value=[cfg])
        mock_svc.check_thresholds = MagicMock(return_value=[])
        mock_svc._batch_should_send_alerts = AsyncMock(return_value=set())
        # send_alerts now returns List[bool]
        mock_svc.send_alerts = AsyncMock(return_value=[])
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
    def test_service_exception_returns_500(self, mock_repo_cls, mock_svc_cls, auth_client):
        """An unhandled exception inside get_active_alert_configs should return 500."""
        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(
            side_effect=RuntimeError("Neon connection lost")
        )
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/check-alerts")

        assert response.status_code == 500
        assert "Alert check failed" in response.json()["detail"]
        # Error details are sanitized in production (not leaked to clients)

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
    def test_mixed_dedup_outcomes(self, mock_repo_cls, mock_svc_cls, auth_client):
        """2 triggered alerts: 1 sent, 1 deduplicated — counts must match."""
        from datetime import datetime
        from decimal import Decimal

        from services.alert_service import AlertThreshold, PriceAlert

        def _threshold(uid, email):
            return AlertThreshold(
                user_id=uid,
                email=email,
                price_below=Decimal("0.25"),
                region="us_ct",
                currency="USD",
            )

        def _alert(uid):
            return PriceAlert(
                alert_type="price_drop",
                current_price=Decimal("0.20"),
                threshold=Decimal("0.25"),
                region="us_ct",
                supplier="Test",
                timestamp=datetime.now(UTC),
            )

        t1, a1 = _threshold("user-1", "a@example.com"), _alert("user-1")
        t2, a2 = _threshold("user-2", "b@example.com"), _alert("user-2")

        cfg1 = self._make_config(
            user_id="user-1",
            email="a@example.com",
            price_below=0.25,
            notification_frequency="daily",
        )
        cfg2 = self._make_config(
            user_id="user-2",
            email="b@example.com",
            price_below=0.25,
            notification_frequency="weekly",
        )
        cfg1["id"] = "cfg-1"
        cfg2["id"] = "cfg-2"

        mock_svc = MagicMock()
        mock_svc.get_active_alert_configs = AsyncMock(return_value=[cfg1, cfg2])
        mock_svc.check_thresholds = MagicMock(return_value=[(t1, a1), (t2, a2)])
        # user-1 passes, user-2 is in cooldown
        mock_svc._batch_should_send_alerts = AsyncMock(
            return_value={("user-2", "price_drop", "us_ct")}
        )
        # send_alerts now returns List[bool] — one True for user-1's successful send
        mock_svc.send_alerts = AsyncMock(return_value=[True])
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
