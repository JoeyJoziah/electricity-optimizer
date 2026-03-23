"""
Authentication Security Tests

Tests for the cookie/session-based auth model (Better Auth + Neon Auth).

This app uses Better Auth session cookies validated against neon_auth.session
and neon_auth.user tables. There is NO JWT signing/verification in the backend.
Session tokens arrive as:
  1. Cookie: 'better-auth.session_token' (dev) / '__Secure-better-auth.session_token' (prod)
  2. Header: 'Authorization: Bearer <session_token>'

Coverage:
  - Protected endpoints return 401 without valid session
  - Invalid/garbage Bearer tokens are rejected
  - Malformed Authorization headers are rejected
  - Missing session cookies are rejected
  - Non-existent admin endpoints return 401/404
  - IDOR: users cannot access other users' data paths
  - CSRF: state-changing endpoints require auth
  - Content-Type enforcement on state-changing endpoints
  - Session security properties (WWW-Authenticate, JSON body, no leaks)
  - Brute force protection on login flow
  - Public endpoints accessible without auth
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Ensure the backend package root is importable when pytest is invoked
# from the project root or from within the backend/ directory.
# ---------------------------------------------------------------------------
backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(backend_dir))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_INTERNAL_API_KEY = "test-internal-api-key-for-auth-bypass-tests"
_TEST_STRIPE_SECRET_KEY = "sk_test_auth_bypass_placeholder"
_TEST_STRIPE_WEBHOOK_SECRET = "whsec_test_auth_bypass_placeholder"


@pytest.fixture(scope="module")
def client():
    """
    TestClient for the real FastAPI application defined in main.py.

    Database calls are patched out so the tests are fully offline.
    Module-scoped: all tests are read-only security probes with no state mutation.
    """
    from config.settings import settings as _settings

    _originals = {}
    for attr, val in [
        ("internal_api_key", _TEST_INTERNAL_API_KEY),
        ("stripe_secret_key", _TEST_STRIPE_SECRET_KEY),
        ("stripe_webhook_secret", _TEST_STRIPE_WEBHOOK_SECRET),
    ]:
        _originals[attr] = getattr(_settings, attr)
        object.__setattr__(_settings, attr, val)

    with (
        patch("config.database.db_manager.initialize", new_callable=AsyncMock),
        patch("config.database.db_manager.close", new_callable=AsyncMock),
        patch(
            "config.database.db_manager.get_redis_client",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "config.database.db_manager._execute_raw_query",
            new_callable=AsyncMock,
            return_value=[{"1": 1}],
        ),
        patch("config.database.db_manager.get_timescale_session") as mock_session_cm,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=None)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cm.return_value = mock_session

        import importlib

        import main as _main_mod

        importlib.reload(_main_mod)
        app = _main_mod.app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    for attr, val in _originals.items():
        object.__setattr__(_settings, attr, val)


def _reset_auth_rate_limiters():
    """Reset the brute-force and password-check rate limiters between test classes.

    The /auth/me endpoint has a login-lockout limiter that triggers 429 after
    repeated failures. Since these security tests intentionally send many bad
    requests, the limiter can spill across test classes. Resetting it keeps
    each class isolated.
    """
    try:
        from api.v1.auth import _login_attempt_limiter, _password_check_limiter

        _login_attempt_limiter.reset()
        _password_check_limiter.reset()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 1. Protected endpoints must return 401 without any credentials
# ---------------------------------------------------------------------------


class TestProtectedEndpointsNoAuth:
    """Protected endpoints must reject requests with no session cookie or Bearer token."""

    PROTECTED_ENDPOINTS = [
        ("GET", "/api/v1/user/preferences"),
        ("GET", "/api/v1/recommendations/switching"),
        ("GET", "/api/v1/recommendations/usage"),
        ("GET", "/api/v1/auth/me"),
        ("POST", "/api/v1/auth/logout"),
        ("GET", "/api/v1/savings/summary"),
        ("GET", "/api/v1/billing/subscription"),
        ("GET", "/api/v1/compliance/gdpr/export"),
        ("DELETE", "/api/v1/compliance/gdpr/delete-my-data"),
    ]

    @pytest.mark.parametrize("method,endpoint", PROTECTED_ENDPOINTS)
    def test_no_auth_returns_401(self, client, method, endpoint):
        """Endpoints with get_current_user dependency must return 401 when no credentials are provided."""
        _reset_auth_rate_limiters()

        if method == "GET":
            response = client.get(endpoint)
        elif method == "POST":
            response = client.post(endpoint, json={})
        elif method == "DELETE":
            response = client.delete(endpoint)
        else:
            response = client.request(method, endpoint)

        assert response.status_code == 401, (
            f"{method} {endpoint} returned {response.status_code}, expected 401 (no auth)"
        )


# ---------------------------------------------------------------------------
# 2. Invalid Bearer tokens must be rejected
# ---------------------------------------------------------------------------


class TestInvalidBearerToken:
    """The app must reject garbage, empty, and invalid Bearer tokens.

    Uses /api/v1/user/preferences to avoid /auth/me brute-force lockout.
    """

    INVALID_TOKENS = [
        "invalid_token_here",
        "not-a-real-session-id",
        "x" * 500,  # Oversized token
        "<script>alert(1)</script>",  # XSS in token
        "'; DROP TABLE session; --",  # SQL injection in token
        "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxMjMifQ.",  # JWT none-algorithm
    ]

    @pytest.mark.parametrize("token", INVALID_TOKENS)
    def test_invalid_bearer_rejected(self, client, token):
        """An invalid session token in Authorization header must return 401."""
        response = client.get(
            "/api/v1/user/preferences",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 401 = auth rejected (expected path)
        # 503 = DB unavailable for session validation (acceptable in test env)
        assert response.status_code in (401, 503), (
            f"Invalid token accepted or crashed. Got {response.status_code}"
        )

    def test_empty_bearer_rejected(self, client):
        """An empty Bearer value must return 401."""
        response = client.get(
            "/api/v1/user/preferences",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401

    def test_bearer_whitespace_only_rejected(self, client):
        """A Bearer token that is only whitespace must return 401."""
        response = client.get(
            "/api/v1/user/preferences",
            headers={"Authorization": "Bearer    "},
        )
        assert response.status_code in (401, 503)


# ---------------------------------------------------------------------------
# 3. Malformed Authorization headers must be rejected
# ---------------------------------------------------------------------------


class TestMalformedAuthHeaders:
    """The auth middleware must reject non-Bearer and malformed headers.

    Note: FastAPI's HTTPBearer is case-insensitive per RFC 7235, so 'bearer'
    and 'BEARER' are treated as valid scheme prefixes. This is correct HTTP
    behavior, not a security issue. Those variants are not tested here.
    """

    MALFORMED_HEADERS = [
        "invalid_format",  # Missing "Bearer " prefix entirely
        "Bearer",  # Missing token value after scheme
        "Basic dGVzdDp0ZXN0",  # Wrong auth scheme (Basic)
        "Token some-value",  # Non-standard scheme
        "Digest realm=test",  # Digest auth scheme
        "",  # Empty header
    ]

    @pytest.mark.parametrize("auth_header", MALFORMED_HEADERS)
    def test_malformed_auth_header_rejected(self, client, auth_header):
        """Non-Bearer or malformed Authorization headers must return 401."""
        response = client.get(
            "/api/v1/user/preferences",
            headers={"Authorization": auth_header},
        )
        # HTTPBearer with auto_error=False falls through to cookie check,
        # and without a cookie the request is rejected with 401.
        assert response.status_code == 401, (
            f"Malformed auth header accepted: {auth_header!r}. Got {response.status_code}"
        )


# ---------------------------------------------------------------------------
# 4. Missing or invalid session cookies must be rejected
# ---------------------------------------------------------------------------


class TestSessionCookieAuth:
    """Session cookie validation tests.

    Uses /api/v1/user/preferences to avoid /auth/me brute-force lockout
    that triggers 429 after repeated failed auth attempts.
    """

    def test_no_cookie_returns_401(self, client):
        """Request with no cookie and no Authorization header must return 401."""
        response = client.get("/api/v1/user/preferences")
        assert response.status_code == 401

    def test_wrong_cookie_name_returns_401(self, client):
        """A cookie with the wrong name must not be accepted."""
        response = client.get(
            "/api/v1/user/preferences",
            cookies={"session_id": "some-value"},
        )
        assert response.status_code == 401

    def test_empty_session_cookie_returns_401(self, client):
        """An empty session cookie value must return 401."""
        response = client.get(
            "/api/v1/user/preferences",
            cookies={"better-auth.session_token": ""},
        )
        assert response.status_code == 401

    def test_garbage_session_cookie_rejected(self, client):
        """A garbage value in the session cookie must be rejected."""
        response = client.get(
            "/api/v1/user/preferences",
            cookies={"better-auth.session_token": "not-a-real-session"},
        )
        # 401 = session not found in DB (expected)
        # 503 = DB unavailable (acceptable in test env without DB)
        assert response.status_code in (401, 503), (
            f"Garbage session cookie accepted. Got {response.status_code}"
        )

    def test_sql_injection_in_cookie_rejected(self, client):
        """SQL injection in session cookie must be safely rejected."""
        response = client.get(
            "/api/v1/user/preferences",
            cookies={"better-auth.session_token": "' OR 1=1; --"},
        )
        assert response.status_code in (401, 503)

    def test_wrong_cookie_prefix_returns_401(self, client):
        """A cookie with a wrong prefix (__Host- instead of __Secure-) must be rejected."""
        response = client.get(
            "/api/v1/user/preferences",
            cookies={"__Host-session": "some-value"},
        )
        assert response.status_code == 401

    def test_xss_in_cookie_rejected(self, client):
        """XSS payload in session cookie must be safely rejected."""
        response = client.get(
            "/api/v1/user/preferences",
            cookies={"better-auth.session_token": "<script>alert(1)</script>"},
        )
        assert response.status_code in (401, 503)


# ---------------------------------------------------------------------------
# 5. Non-existent admin endpoints return 401/403/404
# ---------------------------------------------------------------------------


class TestAdminEndpointProtection:
    """Non-existent admin endpoints must not leak information."""

    ADMIN_ENDPOINTS = [
        ("GET", "/api/v1/admin/users"),
        ("DELETE", "/api/v1/admin/user/user_123"),
        ("GET", "/api/v1/admin/audit-logs"),
    ]

    @pytest.mark.parametrize("method,endpoint", ADMIN_ENDPOINTS)
    def test_admin_endpoint_without_auth(self, client, method, endpoint):
        """Admin endpoints (which don't exist) must return 404, not 200 or 500."""
        if method == "GET":
            response = client.get(endpoint)
        elif method == "DELETE":
            response = client.delete(endpoint)
        else:
            response = client.request(method, endpoint)

        # These endpoints don't exist in the app, so 404/405 is expected.
        # They must NEVER return 200 or 500.
        assert response.status_code in (401, 403, 404, 405), (
            f"{method} {endpoint} returned {response.status_code} (expected 401/403/404/405)"
        )

    @pytest.mark.parametrize("method,endpoint", ADMIN_ENDPOINTS)
    def test_admin_endpoint_with_invalid_bearer(self, client, method, endpoint):
        """Admin endpoints with invalid credentials must still return 401/403/404."""
        headers = {"Authorization": "Bearer fake-session-token"}

        if method == "GET":
            response = client.get(endpoint, headers=headers)
        elif method == "DELETE":
            response = client.delete(endpoint, headers=headers)
        else:
            response = client.request(method, endpoint, headers=headers)

        assert response.status_code in (401, 403, 404, 405), (
            f"{method} {endpoint} returned {response.status_code} with invalid bearer"
        )


# ---------------------------------------------------------------------------
# 6. IDOR: users cannot access other users' data via path manipulation
# ---------------------------------------------------------------------------


class TestIDORProtection:
    """Verify that path-based user ID manipulation is rejected."""

    def test_other_user_path_returns_error(self, client):
        """Requesting another user's data path must not return 200."""
        response = client.get(
            "/api/v1/user/other_user_123/preferences",
            headers={"Authorization": "Bearer some-token"},
        )
        # Path doesn't exist (preferences is /api/v1/user/preferences, not parameterized)
        # so 404 is expected.
        assert response.status_code in (401, 403, 404), (
            f"Other user data path returned {response.status_code}"
        )

    def test_uuid_path_traversal_in_protected_route(self, client):
        """UUID-based path params must reject non-UUID values."""
        # Utility accounts use UUID path params
        traversal_payloads = [
            "../../etc/passwd",
            "' OR 1=1 --",
            "00000000-0000-0000-0000-000000000000",  # Valid UUID but not real
        ]
        for payload in traversal_payloads:
            response = client.get(
                f"/api/v1/utility-accounts/{payload}",
                headers={"Authorization": "Bearer fake-token"},
            )
            # 401 (no valid session), 404 (not found), 422 (bad UUID format)
            assert response.status_code in (401, 404, 422, 503), (
                f"Path traversal payload {payload!r} returned {response.status_code}"
            )


# ---------------------------------------------------------------------------
# 7. CSRF: state-changing endpoints require auth
# ---------------------------------------------------------------------------


class TestCSRFProtection:
    """State-changing requests must require authentication."""

    def test_post_without_auth_rejected(self, client):
        """POST to protected endpoint without auth must return 401."""
        response = client.post(
            "/api/v1/user/preferences",
            json={"notification_enabled": True},
        )
        assert response.status_code == 401

    def test_delete_without_auth_rejected(self, client):
        """DELETE to protected endpoint without auth must return 401."""
        response = client.delete("/api/v1/compliance/gdpr/delete-my-data")
        assert response.status_code == 401

    def test_put_without_auth_rejected(self, client):
        """PUT to protected endpoint without auth must return 401."""
        response = client.put(
            "/api/v1/user/supplier",
            json={"supplier_id": "test"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# 8. Content-Type enforcement
# ---------------------------------------------------------------------------


class TestContentTypeEnforcement:
    """API should handle non-JSON content types gracefully."""

    def test_non_json_content_type_rejected(self, client):
        """State-changing endpoint with non-JSON content type should fail gracefully."""
        response = client.post(
            "/api/v1/user/preferences",
            content="notification_enabled=true",
            headers={
                "Content-Type": "text/plain",
            },
        )
        # Without auth, 401 takes precedence. With wrong content type and no auth,
        # 401 is the correct response (auth checked before body parsing).
        assert response.status_code in (401, 415, 422), (
            f"Non-JSON content type returned {response.status_code}"
        )

    def test_form_encoded_rejected(self, client):
        """Form-encoded data on a JSON endpoint should not be processed."""
        response = client.post(
            "/api/v1/auth/password/check-strength",
            content="password=test123",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        # Password check-strength is unauthenticated but expects JSON body.
        # 422 (validation error) or 400 is expected.
        assert response.status_code in (400, 415, 422), (
            f"Form-encoded data returned {response.status_code}"
        )


# ---------------------------------------------------------------------------
# 9. Session security properties
# ---------------------------------------------------------------------------


class TestSessionSecurityProperties:
    """Verify session security invariants.

    Uses /api/v1/user/preferences to avoid /auth/me brute-force lockout.
    Tests that specifically need /auth/me reset the limiter first.
    """

    def test_401_response_includes_www_authenticate_header(self, client):
        """401 responses must include WWW-Authenticate: Bearer header per RFC 6750."""
        _reset_auth_rate_limiters()
        response = client.get("/api/v1/user/preferences")
        assert response.status_code == 401
        www_auth = response.headers.get("www-authenticate", "")
        assert "Bearer" in www_auth, (
            f"401 response missing WWW-Authenticate: Bearer. Got: {www_auth!r}"
        )

    def test_401_response_body_is_json(self, client):
        """401 error responses must be JSON, not HTML."""
        response = client.get("/api/v1/user/preferences")
        assert response.status_code == 401
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type, (
            f"401 response is not JSON. Content-Type: {content_type}"
        )

    def test_401_does_not_leak_server_details(self, client):
        """401 responses must not leak internal server details."""
        response = client.get("/api/v1/user/preferences")
        assert response.status_code == 401
        body = response.text.lower()
        # Must not contain stack traces, DB info, or internal paths
        leak_indicators = [
            "traceback",
            "sqlalchemy",
            "postgresql",
            "neon_auth",
            "/app/",
        ]
        for indicator in leak_indicators:
            assert indicator not in body, (
                f"401 response leaks internal detail: {indicator!r}"
            )

    def test_multiple_auth_mechanisms_do_not_conflict(self, client):
        """Sending both cookie and Bearer should not cause a 500."""
        response = client.get(
            "/api/v1/user/preferences",
            headers={"Authorization": "Bearer some-token"},
            cookies={"better-auth.session_token": "another-token"},
        )
        # Should be 401 or 503 (DB unavailable), never 500
        assert response.status_code in (401, 503), (
            f"Dual auth mechanisms caused {response.status_code}"
        )

    def test_auth_header_takes_precedence_over_cookie(self, client):
        """When both Bearer header and cookie are present, Bearer should be used first."""
        # Both are invalid, but the point is that no 500 occurs and auth fails cleanly
        response = client.get(
            "/api/v1/recommendations/switching",
            headers={"Authorization": "Bearer fake-bearer-token"},
            cookies={"better-auth.session_token": "fake-cookie-token"},
        )
        assert response.status_code in (401, 503), (
            f"Dual auth caused unexpected {response.status_code}"
        )


# ---------------------------------------------------------------------------
# 10. Public endpoints must NOT require auth
# ---------------------------------------------------------------------------


class TestPublicEndpoints:
    """Endpoints that should be accessible without auth."""

    def test_health_endpoint_accessible(self, client):
        """Health endpoint must be publicly accessible."""
        response = client.get("/health")
        assert response.status_code != 401, "Health endpoint returned 401"

    def test_prices_current_accessible(self, client):
        """Current prices endpoint must be publicly accessible."""
        response = client.get("/api/v1/prices/current?region=us_ct")
        assert response.status_code != 401, "Prices endpoint returned 401"

    def test_password_check_strength_accessible(self, client):
        """Password strength check must be publicly accessible."""
        _reset_auth_rate_limiters()
        response = client.post(
            "/api/v1/auth/password/check-strength",
            json={"password": "test123"},
        )
        assert response.status_code != 401, "Password check-strength returned 401"


# ---------------------------------------------------------------------------
# 11. Brute force protection (run last to avoid triggering lockout for others)
# ---------------------------------------------------------------------------


class TestBruteForceProtection:
    """Verify brute force protection on auth-adjacent endpoints.

    These tests intentionally trigger rate limiters, so they are placed last
    to avoid interfering with other test classes that use the same endpoints.
    """

    def test_rapid_auth_me_failures_never_crash(self, client):
        """Rapid failed auth attempts on /auth/me should not crash the server."""
        _reset_auth_rate_limiters()
        for i in range(15):
            response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer bad-token-{i}"},
            )
            # Every response should be 401, 429 (rate limited), or 503, never 500
            assert response.status_code in (401, 429, 503), (
                f"Attempt {i}: got {response.status_code}, expected 401/429/503"
            )

    def test_auth_me_triggers_lockout_after_failures(self, client):
        """Repeated failed auth on /auth/me should eventually trigger 429 lockout.

        The lockout only triggers for 401 responses (not 503). In a test env
        where the DB is unavailable, auth may return 503 instead of 401, which
        does not increment the lockout counter (by design -- DB outage should
        not lock out users). We verify that either:
          a) Lockout triggers (401 -> 429 transition), OR
          b) All responses are 503 (DB unavailable, lockout inapplicable)
        Both are valid security behaviors.
        """
        _reset_auth_rate_limiters()
        statuses = []
        for i in range(10):
            response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer bad-token-lockout-{i}"},
            )
            statuses.append(response.status_code)

        # Every response must be 401, 429, or 503 (never 200 or 500)
        for i, status_code in enumerate(statuses):
            assert status_code in (401, 429, 503), (
                f"Attempt {i}: got {status_code}, expected 401/429/503"
            )

        if 401 in statuses:
            # If we got 401s, lockout should eventually kick in
            assert 429 in statuses, (
                f"Got 401s but lockout never triggered. Statuses: {statuses}"
            )
        else:
            # All 503 = DB unavailable. Lockout cannot trigger without DB.
            # This is correct: brute-force counter only tracks 401 responses.
            assert all(s == 503 for s in statuses), (
                f"Unexpected mix of statuses without 401: {statuses}"
            )

    def test_rapid_password_check_rate_limited(self, client):
        """Rapid requests to password check-strength should be rate limited."""
        _reset_auth_rate_limiters()
        responses = []
        for i in range(8):
            response = client.post(
                "/api/v1/auth/password/check-strength",
                json={"password": f"testpass{i}"},
            )
            responses.append(response.status_code)

        # At least the first few should succeed (200)
        assert 200 in responses, "No successful password check responses"
        # After 5+ attempts, the 5/min limiter should trigger 429
        assert 429 in responses, (
            f"Rate limiting not triggered after 8 rapid requests. "
            f"Responses: {responses}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
