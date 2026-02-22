"""
Tests for the Recommendations API Router (backend/api/v1/recommendations.py)

Tests cover:
- GET /switching - supplier switching recommendations (requires auth)
- GET /usage - usage optimization recommendations (requires auth)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.dependencies import get_current_user, TokenData


@pytest.fixture
def auth_client():
    """Create a TestClient with authenticated user."""
    from main import app

    test_user = TokenData(user_id="test-user-123", email="test@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauth_client():
    """Create a TestClient without authentication override (uses real auth)."""
    from main import app

    # Make sure override is cleared
    app.dependency_overrides.pop(get_current_user, None)
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
        """Currently returns None recommendation as placeholder."""
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
        """Currently returns None optimal_start_time as placeholder."""
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
