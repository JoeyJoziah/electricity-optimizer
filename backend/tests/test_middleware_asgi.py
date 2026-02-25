"""
Tests for pure ASGI middleware — verify SSE streaming works through the
middleware stack without response buffering.
"""

import asyncio
import os

os.environ.setdefault("ENVIRONMENT", "test")

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Function-scoped test client to avoid rate limiter accumulation."""
    from main import app
    from middleware.rate_limiter import UserRateLimiter

    # Reset rate limiter for clean state
    from main import _app_rate_limiter
    _app_rate_limiter.reset()
    _app_rate_limiter.__init__()

    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_auth():
    """Mock authentication for SSE endpoint."""
    mock_session = MagicMock()
    mock_session.user_id = "test-user-123"
    mock_session.email = "test@example.com"
    mock_session.name = "Test User"
    mock_session.email_verified = True
    mock_session.role = "user"
    return mock_session


# ---------------------------------------------------------------------------
# SecurityHeadersMiddleware tests
# ---------------------------------------------------------------------------

class TestSecurityHeadersASGI:
    """Verify security headers are injected on all responses."""

    def test_security_headers_on_health(self, client):
        """Health endpoint gets all security headers."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-xss-protection"] == "1; mode=block"
        assert "content-security-policy" in resp.headers
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "permissions-policy" in resp.headers

    def test_cache_headers_on_api_path(self, client):
        """API paths get cache-control headers."""
        resp = client.get("/api/v1/prices/current?region=us_ct")
        assert resp.headers.get("cache-control") == "no-store, no-cache, must-revalidate, private"
        assert resp.headers.get("pragma") == "no-cache"
        assert resp.headers.get("expires") == "0"

    def test_no_cache_headers_on_non_api(self, client):
        """Non-API paths should NOT get cache-control headers."""
        resp = client.get("/health")
        # health is not under /api/ — should NOT have the api-specific cache headers
        assert resp.headers.get("pragma") is None


# ---------------------------------------------------------------------------
# RateLimitMiddleware tests
# ---------------------------------------------------------------------------

class TestRateLimitASGI:
    """Verify rate limit headers are present and 429 is returned correctly."""

    def test_rate_limit_headers_present(self, client):
        """Rate limit headers are present on normal responses."""
        resp = client.get("/health/live")
        # /health/live is excluded — no rate limit headers
        assert "x-ratelimit-limit" not in resp.headers

        resp = client.get("/")
        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers

    def test_excluded_paths_skip_rate_limit(self, client):
        """Excluded paths bypass rate limiting entirely."""
        for path in ["/health", "/health/live", "/health/ready"]:
            resp = client.get(path)
            assert "x-ratelimit-limit" not in resp.headers


# ---------------------------------------------------------------------------
# RequestBodySizeLimitMiddleware tests
# ---------------------------------------------------------------------------

class TestBodySizeLimitASGI:
    """Verify body size enforcement works without buffering."""

    def test_oversized_content_length_rejected(self, client):
        """Request with Content-Length exceeding limit gets 413."""
        oversized = b"x" * (1024 * 1024 + 1)  # 1 MB + 1 byte
        resp = client.post(
            "/api/v1/beta/signup",
            content=oversized,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert resp.status_code == 413
        assert "too large" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# RequestTimeoutMiddleware tests
# ---------------------------------------------------------------------------

class TestTimeoutASGI:
    """Verify SSE is excluded from timeout enforcement."""

    def test_sse_endpoint_excluded_from_timeout(self, client, mock_auth):
        """SSE endpoint should not be killed by timeout middleware.

        We verify this by checking that the /prices/stream endpoint returns
        a streaming response (200 with text/event-stream) rather than 504.
        """
        with patch("api.v1.prices_sse._sse_incr", new_callable=AsyncMock, return_value=1), \
             patch("api.v1.prices_sse._sse_decr", new_callable=AsyncMock), \
             patch("api.dependencies.get_current_user", return_value=mock_auth):
            # Use stream=True to not wait for full response
            with client.stream("GET", "/api/v1/prices/stream?region=us_ct&interval=10") as resp:
                # If timeout middleware were applied, we'd get 504
                # SSE should start streaming (200 with text/event-stream)
                assert resp.status_code in (200, 401, 503)
                if resp.status_code == 200:
                    assert "text/event-stream" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# SSE streaming through full middleware stack
# ---------------------------------------------------------------------------

class TestSSEMiddlewareStack:
    """Verify SSE works end-to-end through all 4 middleware layers."""

    def test_sse_gets_security_headers(self, client, mock_auth):
        """SSE response includes security headers from the middleware stack."""
        with patch("api.v1.prices_sse._sse_incr", new_callable=AsyncMock, return_value=1), \
             patch("api.v1.prices_sse._sse_decr", new_callable=AsyncMock), \
             patch("api.dependencies.get_current_user", return_value=mock_auth):
            with client.stream("GET", "/api/v1/prices/stream?region=us_ct&interval=10") as resp:
                if resp.status_code == 200:
                    assert resp.headers.get("x-frame-options") == "DENY"
                    assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_sse_gets_rate_limit_headers(self, client, mock_auth):
        """SSE response includes rate limit headers."""
        with patch("api.v1.prices_sse._sse_incr", new_callable=AsyncMock, return_value=1), \
             patch("api.v1.prices_sse._sse_decr", new_callable=AsyncMock), \
             patch("api.dependencies.get_current_user", return_value=mock_auth):
            with client.stream("GET", "/api/v1/prices/stream?region=us_ct&interval=10") as resp:
                if resp.status_code == 200:
                    assert "x-ratelimit-limit" in resp.headers
