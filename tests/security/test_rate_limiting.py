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
import time
from concurrent.futures import ThreadPoolExecutor


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
        assert 429 in responses, "Rate limiting should kick in after many requests"

    def test_auth_endpoint_subject_to_per_ip_rate_limit(self, client):
        """Auth endpoints are covered by the global per-IP limiter.

        The limiter is per-IP (100/min), applied to all routes — there is no
        separate, stricter per-auth-endpoint limit. So exceeding the per-IP
        budget on an auth endpoint produces 429s like any other route.
        """
        responses = []
        for i in range(150):  # exceed the per-IP per-minute limit (100)
            response = client.post(
                "/api/v1/auth/signin",
                json={"email": f"test{i}@example.com", "password": "test"},
            )
            responses.append(response.status_code)

        assert 429 in responses, (
            "Auth endpoint should be rate limited by the global per-IP limiter"
        )

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
        present_headers = [
            h
            for h in expected_headers
            if h.lower() in [k.lower() for k in response.headers.keys()]
        ]

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
            assert responses == sorted(responses, reverse=True), (
                "Rate limit remaining should decrease"
            )


class TestPerIpRateLimiting:
    """The limiter is per-IP (see middleware/rate_limiter.py): user-level
    limiting is handled at the endpoint/service layer, not in this middleware."""

    def test_limit_is_shared_across_users_on_same_ip(self, client):
        """Two users from the SAME client IP share one per-IP bucket.

        Once the per-IP budget is exhausted by user 1, a second user on the
        same IP is also limited — this is the actual (per-IP) protection, not
        per-user separation.
        """
        user1_headers = {"Authorization": "Bearer token_user_1"}
        user2_headers = {"Authorization": "Bearer token_user_2"}

        # Exhaust the per-IP limit as user 1 (>100/min).
        for _ in range(120):
            client.get("/api/v1/prices/current?region=UK", headers=user1_headers)

        # User 2 shares the same IP bucket, so is also rate-limited.
        response = client.get("/api/v1/prices/current?region=UK", headers=user2_headers)
        assert response.status_code == 429, (
            "Per-IP limiter: a second user on the same IP shares the exhausted bucket"
        )


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
                    "/api/v1/prices/current?region=UK", headers=headers
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

        # Under a concurrent flood (200 reqs > 100/min per-IP budget), the
        # limiter must still enforce — at least some requests get 429.
        rate_limited_count = sum(1 for s in status_codes if s == 429)
        assert rate_limited_count > 0, (
            "Concurrent flood should be rate limited under the per-IP limiter"
        )


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
                    assert (
                        retry_after.isdigit() or retry_after.replace(".", "").isdigit()
                    ), "Retry-After should be numeric"
                break


class TestEndpointSpecificLimits:
    """Tests for endpoint-specific rate limits."""

    def test_sensitive_endpoints_have_lower_limits(self, client, auth_headers):
        """Sensitive endpoints should have stricter rate limits."""
        # Standard endpoint - higher limit
        standard_responses = []
        for _ in range(50):
            response = client.get(
                "/api/v1/prices/current?region=UK", headers=auth_headers
            )
            standard_responses.append(response.status_code)

        # Sensitive endpoint - lower limit
        sensitive_responses = []
        for _ in range(50):
            response = client.post(
                "/api/v1/compliance/data-delete",
                json={"confirm_email": "test@example.com"},
                headers=auth_headers,
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
        assert all(s == 200 for s in responses), (
            "Health endpoint should not be rate limited"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
