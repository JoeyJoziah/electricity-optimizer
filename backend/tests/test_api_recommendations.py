"""
Tests for the Recommendations API Router (backend/api/v1/recommendations.py)

Tests cover:
- GET /switching - supplier switching recommendations (requires auth)
- GET /usage - usage optimization recommendations (requires auth)
- GET /daily - all daily recommendations (requires auth)
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_recommendation_service, TokenData


@pytest.fixture
def mock_recommendation_service():
    """Create a mock RecommendationService."""
    service = AsyncMock()
    # Default: return None (no data available)
    service.get_switching_recommendation.return_value = None
    service.get_usage_recommendation.return_value = None
    service.get_daily_recommendations.return_value = None
    return service


@pytest.fixture
def auth_client(mock_recommendation_service):
    """Create a TestClient with authenticated user and mocked service."""
    from main import app

    test_user = TokenData(user_id="test-user-123", email="test@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_recommendation_service] = lambda: mock_recommendation_service

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_recommendation_service, None)


@pytest.fixture
def unauth_client():
    """Create a TestClient without authentication override (uses real auth)."""
    from main import app

    # Make sure override is cleared
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_recommendation_service, None)
    client = TestClient(app)
    yield client


# =============================================================================
# GET /switching
# =============================================================================


class TestSwitchingRecommendation:
    """Tests for the GET /api/v1/recommendations/switching endpoint."""

    def test_switching_requires_auth(self, unauth_client):
        """Request without auth token should return 401."""
        response = unauth_client.get("/api/v1/recommendations/switching")
        assert response.status_code == 401

    def test_switching_returns_user_id(self, auth_client):
        """Authenticated request should include user_id in response."""
        response = auth_client.get("/api/v1/recommendations/switching")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-123"

    def test_switching_returns_no_recommendation(self, auth_client):
        """Returns None recommendation when service has no data."""
        response = auth_client.get("/api/v1/recommendations/switching")
        assert response.status_code == 200
        data = response.json()
        assert data["recommendation"] is None
        assert "message" in data

    def test_switching_message_content(self, auth_client):
        """Response message should indicate no recommendations available."""
        response = auth_client.get("/api/v1/recommendations/switching")
        data = response.json()
        assert "No switching recommendations" in data["message"]

    def test_switching_with_real_data(self, auth_client, mock_recommendation_service):
        """When service returns a recommendation, response includes it."""
        from services.recommendation_service import SwitchingRecommendation

        mock_recommendation_service.get_switching_recommendation.return_value = SwitchingRecommendation(
            user_id="test-user-123",
            current_supplier="Eversource Energy",
            recommended_supplier="NextEra Energy",
            current_price=Decimal("0.28"),
            recommended_price=Decimal("0.22"),
            potential_savings=Decimal("0.06"),
            savings_percentage=Decimal("21.4"),
            confidence=0.85,
            reasons=["Save up to 21.4% on electricity costs"],
            generated_at=datetime(2026, 2, 23, 12, 0, tzinfo=timezone.utc),
        )

        response = auth_client.get("/api/v1/recommendations/switching")
        assert response.status_code == 200
        data = response.json()
        assert data["recommendation"] is not None
        assert data["recommendation"]["recommended_supplier"] == "NextEra Energy"
        assert data["message"] is None

    def test_switching_handles_service_error(self, auth_client, mock_recommendation_service):
        """When service raises an exception, endpoint returns graceful fallback."""
        mock_recommendation_service.get_switching_recommendation.side_effect = Exception("DB error")

        response = auth_client.get("/api/v1/recommendations/switching")
        assert response.status_code == 200
        data = response.json()
        assert data["recommendation"] is None
        assert "No switching recommendations" in data["message"]


# =============================================================================
# GET /usage
# =============================================================================


class TestUsageRecommendation:
    """Tests for the GET /api/v1/recommendations/usage endpoint."""

    def test_usage_requires_auth(self, unauth_client):
        """Request without auth token should return 401."""
        response = unauth_client.get(
            "/api/v1/recommendations/usage",
            params={"appliance": "dishwasher", "duration_hours": 2.0},
        )
        assert response.status_code == 401

    def test_usage_requires_appliance_param(self, auth_client):
        """Missing required 'appliance' query param should return 422."""
        response = auth_client.get(
            "/api/v1/recommendations/usage",
            params={"duration_hours": 2.0},
        )
        assert response.status_code == 422

    def test_usage_requires_duration_param(self, auth_client):
        """Missing required 'duration_hours' query param should return 422."""
        response = auth_client.get(
            "/api/v1/recommendations/usage",
            params={"appliance": "dishwasher"},
        )
        assert response.status_code == 422

    def test_usage_success(self, auth_client):
        """Valid request with all params should succeed."""
        response = auth_client.get(
            "/api/v1/recommendations/usage",
            params={"appliance": "dishwasher", "duration_hours": 2.0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-123"
        assert data["appliance"] == "dishwasher"
        assert data["duration_hours"] == 2.0

    def test_usage_returns_no_recommendation(self, auth_client):
        """Returns None optimal_start_time when service has no data."""
        response = auth_client.get(
            "/api/v1/recommendations/usage",
            params={"appliance": "washer", "duration_hours": 1.5},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["optimal_start_time"] is None
        assert "message" in data

    def test_usage_duration_min_boundary(self, auth_client):
        """Duration at minimum boundary (0.25) should succeed."""
        response = auth_client.get(
            "/api/v1/recommendations/usage",
            params={"appliance": "lamp", "duration_hours": 0.25},
        )
        assert response.status_code == 200

    def test_usage_duration_below_min(self, auth_client):
        """Duration below minimum (0.25) should return 422."""
        response = auth_client.get(
            "/api/v1/recommendations/usage",
            params={"appliance": "lamp", "duration_hours": 0.1},
        )
        assert response.status_code == 422

    def test_usage_duration_above_max(self, auth_client):
        """Duration above maximum (24) should return 422."""
        response = auth_client.get(
            "/api/v1/recommendations/usage",
            params={"appliance": "heater", "duration_hours": 25.0},
        )
        assert response.status_code == 422

    def test_usage_with_real_data(self, auth_client, mock_recommendation_service):
        """When service returns data, response includes usage recommendation."""
        mock_recommendation_service.get_usage_recommendation.return_value = {
            "optimal_start_time": "2026-02-23T02:00:00+00:00",
            "optimal_end_time": "2026-02-23T04:00:00+00:00",
            "estimated_cost": Decimal("0.72"),
            "cost_vs_peak": Decimal("0.45"),
            "reasons": ["Running during off-peak hours saves significantly"],
            "generated_at": datetime(2026, 2, 23, 12, 0, tzinfo=timezone.utc),
        }

        response = auth_client.get(
            "/api/v1/recommendations/usage",
            params={"appliance": "dishwasher", "duration_hours": 2.0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["optimal_start_time"] == "2026-02-23T02:00:00+00:00"
        assert data["message"] is None

    def test_usage_handles_service_error(self, auth_client, mock_recommendation_service):
        """When service raises an exception, endpoint returns graceful fallback."""
        mock_recommendation_service.get_usage_recommendation.side_effect = Exception("DB error")

        response = auth_client.get(
            "/api/v1/recommendations/usage",
            params={"appliance": "dishwasher", "duration_hours": 2.0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["optimal_start_time"] is None


# =============================================================================
# GET /daily
# =============================================================================


class TestDailyRecommendations:
    """Tests for the GET /api/v1/recommendations/daily endpoint."""

    def test_daily_requires_auth(self, unauth_client):
        """Request without auth token should return 401."""
        response = unauth_client.get("/api/v1/recommendations/daily")
        assert response.status_code == 401

    def test_daily_returns_empty_when_no_data(self, auth_client):
        """Returns empty recommendations when service has no data."""
        response = auth_client.get("/api/v1/recommendations/daily")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-123"
        assert data["switching_recommendation"] is None
        assert data["usage_recommendations"] == []

    def test_daily_with_real_data(self, auth_client, mock_recommendation_service):
        """When service returns data, response includes all recommendations."""
        mock_recommendation_service.get_daily_recommendations.return_value = {
            "user_id": "test-user-123",
            "generated_at": "2026-02-23T12:00:00+00:00",
            "switching_recommendation": {
                "recommended_supplier": "NextEra Energy",
                "potential_savings": "0.06",
            },
            "usage_recommendations": [
                {"appliance": "dishwasher", "optimal_start_time": "2026-02-23T02:00:00+00:00"}
            ],
        }

        response = auth_client.get("/api/v1/recommendations/daily")
        assert response.status_code == 200
        data = response.json()
        assert data["switching_recommendation"] is not None
        assert len(data["usage_recommendations"]) == 1

    def test_daily_handles_service_error(self, auth_client, mock_recommendation_service):
        """When service raises an exception, endpoint returns graceful fallback."""
        mock_recommendation_service.get_daily_recommendations.side_effect = Exception("DB error")

        response = auth_client.get("/api/v1/recommendations/daily")
        assert response.status_code == 200
        data = response.json()
        assert data["switching_recommendation"] is None
        assert data["usage_recommendations"] == []
