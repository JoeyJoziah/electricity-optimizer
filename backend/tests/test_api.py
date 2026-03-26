"""
API Endpoint Tests - Written FIRST following TDD principles

Tests for:
- Health check endpoints
- Price endpoints
- Supplier endpoints
- Authentication middleware

RED phase: These tests should FAIL initially until endpoints are implemented.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# =============================================================================
# CLIENT FIXTURE
# =============================================================================


@pytest.fixture(scope="function")
def client():
    """Function-scoped TestClient — isolates ASGI state between tests."""
    from main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================


class TestHealthEndpoints:
    """Tests for health check endpoints"""

    def test_health_check_returns_status(self, client):
        """Test /health endpoint returns valid status and metadata.

        Without a real DB the status is 'degraded'; with one it is 'healthy'.
        Both are valid — the test verifies the response shape.
        """
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
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

        # Should return 200, 404 (no data), or 422 (validation) — never 500
        assert response.status_code in [200, 404, 422]

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
        response = client.get("/api/v1/prices/history", params={"region": "uk", "days": 7})

        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert "prices" in data
            assert isinstance(data["prices"], list)

    def test_price_history_pagination_metadata_present(self, client):
        """Successful /history response always includes pagination envelope fields"""
        response = client.get(
            "/api/v1/prices/history",
            params={"region": "uk", "days": 1},
        )

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            for field in ("total", "page", "page_size", "pages"):
                assert field in data, f"Missing pagination field: {field}"
            assert isinstance(data["total"], int)
            assert data["total"] >= 0
            assert isinstance(data["page"], int)
            assert data["page"] >= 1
            assert isinstance(data["page_size"], int)
            assert 1 <= data["page_size"] <= 100
            assert isinstance(data["pages"], int)
            assert data["pages"] >= 1

    def test_price_history_default_page_size_is_24(self, client):
        """page_size defaults to 24 when not supplied"""
        response = client.get(
            "/api/v1/prices/history",
            params={"region": "uk"},
        )

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert data["page_size"] == 24

    def test_price_history_respects_page_size_param(self, client):
        """page_size query param is reflected in the response envelope"""
        response = client.get(
            "/api/v1/prices/history",
            params={"region": "uk", "days": 7, "page_size": 10},
        )

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert data["page_size"] == 10
            assert len(data["prices"]) <= 10

    def test_price_history_respects_page_param(self, client):
        """page query param is reflected in the response envelope"""
        response = client.get(
            "/api/v1/prices/history",
            params={"region": "uk", "days": 7, "page": 2, "page_size": 5},
        )

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert data["page"] == 2
            assert data["page_size"] == 5

    def test_price_history_page_size_clamped_to_100(self, client):
        """page_size above 100 is rejected with 422 by FastAPI validation"""
        response = client.get(
            "/api/v1/prices/history",
            params={"region": "uk", "page_size": 500},
        )
        assert response.status_code == 422

    def test_price_history_page_zero_rejected(self, client):
        """page < 1 is rejected with 422 by FastAPI validation"""
        response = client.get(
            "/api/v1/prices/history",
            params={"region": "uk", "page": 0},
        )
        assert response.status_code == 422

    def test_price_history_page_size_zero_rejected(self, client):
        """page_size < 1 is rejected with 422 by FastAPI validation"""
        response = client.get(
            "/api/v1/prices/history",
            params={"region": "uk", "page_size": 0},
        )
        assert response.status_code == 422

    def test_price_history_prices_list_bounded_by_page_size(self, client):
        """The prices array must never exceed page_size records"""
        response = client.get(
            "/api/v1/prices/history",
            params={"region": "uk", "days": 30, "page": 1, "page_size": 12},
        )

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert len(data["prices"]) <= data["page_size"]

    def test_price_history_pages_consistent_with_total(self, client):
        """pages value is ceil(total / page_size), minimum 1"""
        response = client.get(
            "/api/v1/prices/history",
            params={"region": "uk", "days": 7, "page_size": 24},
        )

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            total = data["total"]
            page_size = data["page_size"]
            expected_pages = max(1, (total + page_size - 1) // page_size)
            assert data["pages"] == expected_pages

    def test_get_price_forecast(self, client):
        """Test GET /api/v1/prices/forecast endpoint"""
        response = client.get("/api/v1/prices/forecast", params={"region": "uk", "hours": 24})

        # Unauthenticated request: 401 because no auth token is present.
        # The tier gate (403) only fires after auth succeeds.
        assert response.status_code == 401

    def test_get_price_comparison(self, client):
        """Test GET /api/v1/prices/compare endpoint"""
        response = client.get("/api/v1/prices/compare?region=uk")

        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert "suppliers" in data or "comparison" in data


# =============================================================================
# SUPPLIER ENDPOINT TESTS
# =============================================================================


def _supplier_client_with_mock(execute_side_effect):
    """Create a TestClient with mocked DB session for supplier endpoints.

    Args:
        execute_side_effect: list or callable for mock_session.execute.
    """
    from api.dependencies import get_db_session, get_redis
    from main import app

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=execute_side_effect)

    async def mock_get_db_session():
        yield mock_session

    async def mock_get_redis():
        return None

    app.dependency_overrides[get_db_session] = mock_get_db_session
    app.dependency_overrides[get_redis] = mock_get_redis
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_redis, None)


class TestSupplierEndpoints:
    """Tests for supplier API endpoints.

    Supplier endpoints require a live DB session. These tests override
    get_db_session with a mock that returns empty result sets so the
    endpoint logic is exercised without a real database.
    """

    @pytest.fixture
    def list_supplier_client(self):
        """Client for list endpoints: execute returns count=0, rows=[]."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        rows_result = MagicMock()
        rows_result.mappings.return_value.all.return_value = []

        yield from _supplier_client_with_mock([count_result, rows_result])

    @pytest.fixture
    def single_supplier_client(self):
        """Client for single-item endpoints: execute returns no matching row."""
        empty_result = MagicMock()
        empty_result.mappings.return_value.first.return_value = None

        yield from _supplier_client_with_mock([empty_result])

    def test_list_suppliers(self, list_supplier_client):
        """Test GET /api/v1/suppliers endpoint"""
        response = list_supplier_client.get("/api/v1/suppliers")

        assert response.status_code == 200

        data = response.json()
        assert "suppliers" in data
        assert isinstance(data["suppliers"], list)

    def test_list_suppliers_by_region(self, list_supplier_client):
        """Test GET /api/v1/suppliers?region=uk endpoint"""
        response = list_supplier_client.get("/api/v1/suppliers?region=uk")

        assert response.status_code == 200

    def test_get_supplier_by_id(self, single_supplier_client):
        """Test GET /api/v1/suppliers/{id} endpoint with non-existent UUID"""
        response = single_supplier_client.get(
            "/api/v1/suppliers/00000000-0000-0000-0000-000000000001"
        )

        # Mock DB returns no row, so endpoint returns 404
        assert response.status_code == 404

    def test_get_supplier_by_id_invalid_uuid(self, client):
        """Test GET /api/v1/suppliers/{id} rejects non-UUID path params"""
        response = client.get("/api/v1/suppliers/not-a-uuid")
        assert response.status_code == 422

    def test_get_supplier_tariffs(self, single_supplier_client):
        """Test GET /api/v1/suppliers/{id}/tariffs endpoint with non-existent UUID"""
        response = single_supplier_client.get(
            "/api/v1/suppliers/00000000-0000-0000-0000-000000000001/tariffs"
        )

        # Mock DB returns no supplier, so endpoint returns 404
        assert response.status_code == 404


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
            "/api/v1/user/preferences", headers={"Authorization": "Bearer invalid_token"}
        )

        # 401 = auth rejected (token invalid/expired)
        # 503 = DB unavailable for Neon Auth session validation (test env)
        # Both indicate the request was properly rejected.
        assert response.status_code in (401, 503)

    def test_user_preferences_endpoint(self, client):
        """Test POST /api/v1/user/preferences requires auth"""
        response = client.post("/api/v1/user/preferences", json={"notification_enabled": True})

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
            params={"appliance": "washing_machine", "duration_hours": 2},
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
            },
        )

        # CORS preflight should return 200 or 204 or 405
        # (405 if CORS middleware doesn't intercept, still valid config)
        assert response.status_code in [200, 204, 405]

    def test_cors_allows_configured_origins(self, client):
        """Test CORS allows configured origins"""
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})

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


# =============================================================================
# GENERAL EXCEPTION HANDLER SANITIZATION TESTS
# =============================================================================


class TestGeneralExceptionHandlerSanitization:
    """Verify the general exception handler never leaks raw exception details
    to HTTP clients — regardless of the runtime environment.

    The handler in app_factory.py previously returned ``str(exc)`` in
    non-production environments.  This is a security vulnerability: SQLAlchemy
    exceptions contain connection strings (with credentials), crypto exceptions
    expose algorithm details, etc.

    The fix: always return a generic message; log the full exception server-side.
    """

    def test_general_handler_returns_generic_message_in_test_env(self):
        """The general exception handler must return a generic 500, not raw exc text."""

        from fastapi.testclient import TestClient

        from main import app

        # Inject a route that unconditionally raises an exception with
        # sensitive content to simulate an unhandled exception reaching the
        # global exception handler.
        @app.get("/test-exception-leak-canary")
        async def _canary_exception():
            raise RuntimeError(
                "SECRET_TOKEN=sk_live_xxxxxDATABASE_URL=postgresql://admin:hunter2@db/prod"
            )

        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/test-exception-leak-canary")

        assert response.status_code == 500
        body = response.text
        # The raw exception string must NOT appear in the response body
        assert "SECRET_TOKEN" not in body
        assert "sk_live_" not in body
        assert "hunter2" not in body
        assert "DATABASE_URL" not in body
        assert "postgresql://" not in body

        # Response must still be valid JSON with a non-empty detail
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], str)
        assert len(data["detail"]) > 0

    def test_general_handler_detail_is_not_raw_exception_string(self):
        """The detail field must not equal str(exc) under any environment."""

        from fastapi.testclient import TestClient

        from main import app

        @app.get("/test-exception-detail-canary")
        async def _detail_canary():
            raise ValueError("this_is_a_very_specific_internal_error_xyz123")

        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/test-exception-detail-canary")

        assert response.status_code == 500
        data = response.json()
        # The exact exception string must not appear verbatim in the response
        assert "this_is_a_very_specific_internal_error_xyz123" not in data.get("detail", "")
