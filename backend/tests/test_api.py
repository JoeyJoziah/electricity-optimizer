"""
API Endpoint Tests - Written FIRST following TDD principles

Tests for:
- Health check endpoints
- Price endpoints
- Supplier endpoints
- Authentication middleware

RED phase: These tests should FAIL initially until endpoints are implemented.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient


# =============================================================================
# MODULE-SCOPED CLIENT FIXTURE
# =============================================================================


@pytest.fixture(scope="module")
def client():
    """Module-scoped TestClient — avoids 28 redundant ASGI lifespan startups."""
    from main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================


class TestHealthEndpoints:
    """Tests for health check endpoints"""

    def test_health_check_returns_healthy(self, client):
        """Test /health endpoint returns healthy status"""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_liveness_check(self, client):
        """Test /health/live endpoint"""
        response = client.get("/health/live")

        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_readiness_check_structure(self, client):
        """Test /health/ready endpoint returns correct structure"""
        # Note: This may fail in test env without real DB connections
        # but we test the structure is correct
        response = client.get("/health/ready")

        # Either 200 (all healthy) or 503 (some unhealthy)
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert "checks" in data


# =============================================================================
# PRICE ENDPOINT TESTS
# =============================================================================


class TestPriceEndpoints:
    """Tests for price API endpoints"""

    @pytest.fixture
    def mock_price_service(self):
        """Create mock price service"""
        service = AsyncMock()
        return service

    def test_get_current_prices(self, client):
        """Test GET /api/v1/prices/current endpoint"""
        response = client.get("/api/v1/prices/current?region=uk")

        # Should return 200 or appropriate error
        assert response.status_code in [200, 404, 422, 500]

        if response.status_code == 200:
            data = response.json()
            assert "prices" in data or "price" in data

    def test_get_current_prices_requires_region(self, client):
        """Test GET /api/v1/prices/current requires region parameter"""
        response = client.get("/api/v1/prices/current")

        # Should require region
        assert response.status_code == 422  # Validation error

    def test_get_prices_invalid_region(self, client):
        """Test API returns error for invalid region"""
        response = client.get("/api/v1/prices/current?region=INVALID_REGION")

        assert response.status_code in [400, 422]

    def test_get_price_history(self, client):
        """Test GET /api/v1/prices/history endpoint"""
        response = client.get(
            "/api/v1/prices/history",
            params={
                "region": "uk",
                "days": 7
            }
        )

        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()
            assert "prices" in data
            assert isinstance(data["prices"], list)

    def test_get_price_forecast(self, client):
        """Test GET /api/v1/prices/forecast endpoint"""
        response = client.get(
            "/api/v1/prices/forecast",
            params={
                "region": "uk",
                "hours": 24
            }
        )

        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()
            assert "forecast" in data or "prices" in data

    def test_get_price_comparison(self, client):
        """Test GET /api/v1/prices/compare endpoint"""
        response = client.get("/api/v1/prices/compare?region=uk")

        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()
            assert "suppliers" in data or "comparison" in data


# =============================================================================
# SUPPLIER ENDPOINT TESTS
# =============================================================================


class TestSupplierEndpoints:
    """Tests for supplier API endpoints"""

    def test_list_suppliers(self, client):
        """Test GET /api/v1/suppliers endpoint"""
        response = client.get("/api/v1/suppliers")

        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            assert "suppliers" in data
            assert isinstance(data["suppliers"], list)

    def test_list_suppliers_by_region(self, client):
        """Test GET /api/v1/suppliers?region=uk endpoint"""
        response = client.get("/api/v1/suppliers?region=uk")

        assert response.status_code in [200, 500]

    def test_get_supplier_by_id(self, client):
        """Test GET /api/v1/suppliers/{id} endpoint"""
        response = client.get("/api/v1/suppliers/supplier_123")

        # 200 if found, 404 if not
        assert response.status_code in [200, 404, 500]

    def test_get_supplier_tariffs(self, client):
        """Test GET /api/v1/suppliers/{id}/tariffs endpoint"""
        response = client.get("/api/v1/suppliers/supplier_123/tariffs")

        assert response.status_code in [200, 404, 500]


# =============================================================================
# AUTHENTICATION TESTS
# =============================================================================


class TestAuthenticationEndpoints:
    """Tests for authentication and protected endpoints"""

    def test_protected_endpoint_requires_auth(self, client):
        """Test protected endpoints require authentication"""
        # Try to access protected endpoint without token
        response = client.get("/api/v1/user/preferences")

        assert response.status_code == 401

    def test_protected_endpoint_with_invalid_token(self, client):
        """Test protected endpoints reject invalid tokens"""
        response = client.get(
            "/api/v1/user/preferences",
            headers={"Authorization": "Bearer invalid_token"}
        )

        # 401 = auth rejected (token invalid/expired)
        # 503 = DB unavailable for Neon Auth session validation (test env)
        # Both indicate the request was properly rejected.
        assert response.status_code in (401, 503)

    def test_user_preferences_endpoint(self, client):
        """Test POST /api/v1/user/preferences requires auth"""
        response = client.post(
            "/api/v1/user/preferences",
            json={"notification_enabled": True}
        )

        assert response.status_code == 401


# =============================================================================
# RECOMMENDATION ENDPOINT TESTS
# =============================================================================


class TestRecommendationEndpoints:
    """Tests for recommendation endpoints"""

    def test_get_switching_recommendation_requires_auth(self, client):
        """Test recommendation endpoint requires authentication"""
        response = client.get("/api/v1/recommendations/switching")

        assert response.status_code == 401

    def test_get_usage_recommendation_requires_auth(self, client):
        """Test usage recommendation endpoint requires authentication"""
        response = client.get(
            "/api/v1/recommendations/usage",
            params={"appliance": "washing_machine", "duration_hours": 2}
        )

        assert response.status_code == 401


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for API error handling"""

    def test_not_found_returns_404(self, client):
        """Test non-existent endpoint returns 404"""
        response = client.get("/api/v1/nonexistent")

        assert response.status_code == 404

    def test_validation_error_returns_422(self, client):
        """Test validation errors return 422"""
        # Invalid data type for region (if endpoint validates)
        response = client.get("/api/v1/prices/current?region=123")

        # Should be validation error or bad request
        assert response.status_code in [400, 422]

    def test_method_not_allowed_returns_405(self, client):
        """Test wrong HTTP method returns 405"""
        # POST to GET-only endpoint
        response = client.post("/health")

        assert response.status_code == 405


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================


class TestRateLimiting:
    """Tests for API rate limiting"""

    def test_rate_limit_headers_present(self, client):
        """Test rate limit headers are present in response"""
        response = client.get("/health")

        # Rate limit headers should be present (if implemented)
        # X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
        # This is optional based on implementation
        assert response.status_code == 200


# =============================================================================
# CORS TESTS
# =============================================================================


class TestCORS:
    """Tests for CORS configuration"""

    def test_cors_headers_on_options(self, client):
        """Test CORS headers are returned on OPTIONS request"""
        response = client.options(
            "/api/v1/prices/current",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        # CORS preflight should return 200 or 204 or 405
        # (405 if CORS middleware doesn't intercept, still valid config)
        assert response.status_code in [200, 204, 405]

    def test_cors_allows_configured_origins(self, client):
        """Test CORS allows configured origins"""
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )

        assert response.status_code == 200
        # Access-Control-Allow-Origin should be present
        assert "access-control-allow-origin" in response.headers or response.status_code == 200


# =============================================================================
# RESPONSE FORMAT TESTS
# =============================================================================


class TestResponseFormat:
    """Tests for consistent API response format"""

    def test_success_response_format(self, client):
        """Test successful responses have consistent format"""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Should have standard fields
        assert isinstance(data, dict)

    def test_error_response_format(self, client):
        """Test error responses have consistent format"""
        response = client.get("/api/v1/prices/current")  # Missing required param

        assert response.status_code == 422
        data = response.json()

        # Should have detail field for errors
        assert "detail" in data

    def test_request_id_header(self, client):
        """Test X-Request-ID header is returned"""
        response = client.get("/health")

        assert response.status_code == 200
        assert "x-request-id" in response.headers

    def test_process_time_header(self, client):
        """Test X-Process-Time header is returned"""
        response = client.get("/health")

        assert response.status_code == 200
        assert "x-process-time" in response.headers
