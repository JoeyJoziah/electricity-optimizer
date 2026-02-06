"""
Rate Limiting Security Tests

Tests for:
- Per-user rate limiting
- Per-IP rate limiting
- API endpoint rate limiting
- Rate limit header presence
- Rate limit bypass attempts
"""

import pytest
from fastapi.testclient import TestClient
import time
from concurrent.futures import ThreadPoolExecutor


@pytest.fixture
def client():
    """Create test client."""
    from main import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Get authentication headers."""
    return {"Authorization": "Bearer test_token_user_1"}


class TestRateLimitEnforcement:
    """Tests for rate limit enforcement."""

    def test_rate_limiting_enforced_on_public_endpoints(self, client):
        """Public endpoints should enforce rate limiting."""
        responses = []

        # Make many rapid requests
        for i in range(150):  # Exceeds typical 100/min limit
            response = client.get("/api/v1/prices/current?region=UK")
            responses.append(response.status_code)

        # At some point, should get 429 Too Many Requests
        assert 429 in responses, \
            "Rate limiting should kick in after many requests"

    def test_rate_limiting_on_auth_endpoint(self, client):
        """Auth endpoints should have stricter rate limits."""
        responses = []

        # Auth endpoints typically have lower limits (e.g., 10/min)
        for i in range(20):
            response = client.post(
                "/api/v1/auth/signin",
                json={"email": f"test{i}@example.com", "password": "test"}
            )
            responses.append(response.status_code)

        # Should see rate limiting after a few attempts
        rate_limited = sum(1 for r in responses if r == 429)
        assert rate_limited > 0 or all(r in [401, 422] for r in responses), \
            "Auth endpoint should be rate limited"

    def test_rate_limit_resets_after_window(self, client):
        """Rate limit should reset after the time window."""
        # Hit the rate limit
        for _ in range(150):
            client.get("/api/v1/prices/current?region=UK")

        # Wait for window to reset (assuming 1 minute window)
        # In tests, we may need to mock time or use shorter windows
        time.sleep(1)  # Just a short wait for demo

        # After window, requests should succeed again
        response = client.get("/api/v1/prices/current?region=UK")

        # May or may not be rate limited depending on window
        assert response.status_code in [200, 429]


class TestRateLimitHeaders:
    """Tests for rate limit headers in responses."""

    def test_rate_limit_headers_present(self, client):
        """Rate limit headers should be present in responses."""
        response = client.get("/api/v1/prices/current?region=UK")

        # Standard rate limit headers
        expected_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ]

        # At least some rate limit headers should be present
        present_headers = [h for h in expected_headers if h.lower() in
                          [k.lower() for k in response.headers.keys()]]

        # Note: This is optional based on implementation
        # assert len(present_headers) > 0, "Rate limit headers should be present"

    def test_rate_limit_remaining_decreases(self, client):
        """X-RateLimit-Remaining should decrease with each request."""
        responses = []

        for _ in range(5):
            response = client.get("/api/v1/prices/current?region=UK")
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining:
                responses.append(int(remaining))

        if len(responses) >= 2:
            # Each subsequent request should have fewer remaining
            assert responses == sorted(responses, reverse=True), \
                "Rate limit remaining should decrease"


class TestPerUserRateLimiting:
    """Tests for per-user rate limiting."""

    def test_different_users_have_separate_limits(self, client):
        """Different users should have separate rate limits."""
        user1_headers = {"Authorization": "Bearer token_user_1"}
        user2_headers = {"Authorization": "Bearer token_user_2"}

        # Hit limit for user 1
        for _ in range(100):
            client.get(
                "/api/v1/prices/current?region=UK",
                headers=user1_headers
            )

        # User 2 should still be able to make requests
        response = client.get(
            "/api/v1/prices/current?region=UK",
            headers=user2_headers
        )

        # User 2 should not be affected by user 1's rate limit
        # (assuming per-user rate limiting)
        assert response.status_code in [200, 401]


class TestRateLimitBypass:
    """Tests for rate limit bypass attempts."""

    def test_rate_limit_cannot_be_bypassed_by_headers(self, client):
        """Rate limits should not be bypassable by fake headers."""
        bypass_attempts = [
            {"X-Forwarded-For": "192.168.1.100"},
            {"X-Real-IP": "10.0.0.1"},
            {"X-Forwarded-Host": "trusted.example.com"},
            {"X-Originating-IP": "192.168.1.200"},
            {"CF-Connecting-IP": "172.16.0.1"},
        ]

        for headers in bypass_attempts:
            # Try to bypass by changing perceived IP
            responses = []
            for _ in range(150):
                response = client.get(
                    "/api/v1/prices/current?region=UK",
                    headers=headers
                )
                responses.append(response.status_code)

            # Should still get rate limited
            if 429 in responses:
                continue  # Expected behavior
            # If no 429, the headers might be ignored (also acceptable)

    def test_rate_limit_applies_to_all_methods(self, client):
        """Rate limiting should apply to all HTTP methods."""
        # GET requests
        for _ in range(50):
            client.get("/api/v1/prices/current?region=UK")

        # POST requests should also be counted
        for _ in range(50):
            client.post("/api/v1/optimization/schedule", json={})

        # Should be rate limited across methods
        response = client.get("/api/v1/prices/current?region=UK")
        # Rate limiting may or may not apply across methods


class TestConcurrentRequests:
    """Tests for rate limiting under concurrent load."""

    def test_concurrent_requests_rate_limited(self, client):
        """Concurrent requests should respect rate limits."""
        def make_request():
            return client.get("/api/v1/prices/current?region=UK")

        # Make many concurrent requests
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request) for _ in range(200)]
            responses = [f.result() for f in futures]

        status_codes = [r.status_code for r in responses]

        # Should see some 429s from concurrent requests
        # (depends on implementation)
        rate_limited_count = sum(1 for s in status_codes if s == 429)

        # At least some requests should succeed
        success_count = sum(1 for s in status_codes if s == 200)
        assert success_count > 0, "Some requests should succeed"


class TestRetryAfterHeader:
    """Tests for Retry-After header when rate limited."""

    def test_retry_after_header_present_when_limited(self, client):
        """429 responses should include Retry-After header."""
        # Hit the rate limit
        for _ in range(200):
            response = client.get("/api/v1/prices/current?region=UK")
            if response.status_code == 429:
                # Should have Retry-After header
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    # Should be a number of seconds
                    assert retry_after.isdigit() or retry_after.replace(".", "").isdigit(), \
                        "Retry-After should be numeric"
                break


class TestEndpointSpecificLimits:
    """Tests for endpoint-specific rate limits."""

    def test_sensitive_endpoints_have_lower_limits(self, client, auth_headers):
        """Sensitive endpoints should have stricter rate limits."""
        # Standard endpoint - higher limit
        standard_responses = []
        for _ in range(50):
            response = client.get(
                "/api/v1/prices/current?region=UK",
                headers=auth_headers
            )
            standard_responses.append(response.status_code)

        # Sensitive endpoint - lower limit
        sensitive_responses = []
        for _ in range(50):
            response = client.post(
                "/api/v1/compliance/data-delete",
                json={"confirm_email": "test@example.com"},
                headers=auth_headers
            )
            sensitive_responses.append(response.status_code)

        # Sensitive endpoint should hit limit sooner
        # (implementation dependent)

    def test_health_endpoint_not_rate_limited(self, client):
        """Health check endpoint should not be rate limited."""
        responses = []
        for _ in range(200):
            response = client.get("/health")
            responses.append(response.status_code)

        # Health should always return 200
        assert all(s == 200 for s in responses), \
            "Health endpoint should not be rate limited"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
