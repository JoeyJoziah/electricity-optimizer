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
