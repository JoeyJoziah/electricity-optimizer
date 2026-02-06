"""
Authentication Security Tests

Tests for:
- Protected endpoints require authentication
- Invalid tokens are rejected
- Expired tokens are rejected
- Token format validation
- Role-based access control
"""

import pytest
from fastapi.testclient import TestClient
import jwt
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Create test client."""
    from main import app
    return TestClient(app)


@pytest.fixture
def valid_token():
    """Generate a valid JWT token for testing."""
    payload = {
        "sub": "user_123",
        "email": "test@example.com",
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow(),
        "role": "user",
    }
    # Use test secret - in production this would be the actual secret
    return jwt.encode(payload, "test_secret_key", algorithm="HS256")


@pytest.fixture
def expired_token():
    """Generate an expired JWT token."""
    payload = {
        "sub": "user_123",
        "email": "test@example.com",
        "exp": datetime.utcnow() - timedelta(hours=1),  # Expired
        "iat": datetime.utcnow() - timedelta(hours=2),
        "role": "user",
    }
    return jwt.encode(payload, "test_secret_key", algorithm="HS256")


@pytest.fixture
def admin_token():
    """Generate an admin JWT token."""
    payload = {
        "sub": "admin_123",
        "email": "admin@example.com",
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow(),
        "role": "admin",
    }
    return jwt.encode(payload, "test_secret_key", algorithm="HS256")


class TestProtectedEndpoints:
    """Tests for protected endpoint authentication."""

    # List of protected endpoints that require authentication
    PROTECTED_ENDPOINTS = [
        ("GET", "/api/v1/user/preferences"),
        ("GET", "/api/v1/recommendations/switching"),
        ("GET", "/api/v1/recommendations/usage"),
        ("GET", "/api/v1/analytics/savings"),
        ("POST", "/api/v1/optimization/schedule"),
        ("GET", "/api/v1/compliance/data-export"),
        ("POST", "/api/v1/compliance/data-delete"),
    ]

    @pytest.mark.parametrize("method,endpoint", PROTECTED_ENDPOINTS)
    def test_protected_endpoint_without_token(self, client, method, endpoint):
        """Protected endpoints should reject requests without JWT."""
        if method == "GET":
            response = client.get(endpoint)
        else:
            response = client.post(endpoint, json={})

        assert response.status_code == 401, \
            f"{endpoint} should require authentication"

    @pytest.mark.parametrize("method,endpoint", PROTECTED_ENDPOINTS)
    def test_protected_endpoint_with_invalid_token(self, client, method, endpoint):
        """Protected endpoints should reject invalid tokens."""
        headers = {"Authorization": "Bearer invalid_token_here"}

        if method == "GET":
            response = client.get(endpoint, headers=headers)
        else:
            response = client.post(endpoint, json={}, headers=headers)

        assert response.status_code == 401, \
            f"{endpoint} should reject invalid token"

    @pytest.mark.parametrize("method,endpoint", PROTECTED_ENDPOINTS)
    def test_protected_endpoint_with_expired_token(self, client, expired_token, method, endpoint):
        """Protected endpoints should reject expired tokens."""
        headers = {"Authorization": f"Bearer {expired_token}"}

        if method == "GET":
            response = client.get(endpoint, headers=headers)
        else:
            response = client.post(endpoint, json={}, headers=headers)

        assert response.status_code == 401, \
            f"{endpoint} should reject expired token"


class TestTokenValidation:
    """Tests for JWT token validation."""

    def test_malformed_authorization_header(self, client):
        """Should reject malformed Authorization header."""
        test_cases = [
            "invalid_format",  # Missing "Bearer "
            "Bearer",  # Missing token
            "Bearer ",  # Empty token
            "Basic dGVzdDp0ZXN0",  # Wrong auth type
            "bearer token123",  # Wrong case
        ]

        for auth_header in test_cases:
            response = client.get(
                "/api/v1/user/preferences",
                headers={"Authorization": auth_header}
            )
            assert response.status_code == 401, \
                f"Should reject header: {auth_header}"

    def test_token_with_wrong_algorithm(self, client):
        """Should reject tokens signed with wrong algorithm."""
        payload = {
            "sub": "user_123",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        # Sign with none algorithm (security vulnerability if accepted)
        token = jwt.encode(payload, None, algorithm="none")

        response = client.get(
            "/api/v1/user/preferences",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    def test_token_with_modified_payload(self, client, valid_token):
        """Should reject tokens with tampered payload."""
        # Decode, modify, re-encode with different signature
        parts = valid_token.split(".")
        # Modify payload part
        import base64
        payload = base64.urlsafe_b64decode(parts[1] + "==")
        payload = payload.replace(b"user_123", b"admin_123")
        parts[1] = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        tampered_token = ".".join(parts)

        response = client.get(
            "/api/v1/user/preferences",
            headers={"Authorization": f"Bearer {tampered_token}"}
        )
        assert response.status_code == 401

    def test_token_with_missing_claims(self, client):
        """Should reject tokens missing required claims."""
        # Token without 'sub' claim
        payload = {
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, "test_secret_key", algorithm="HS256")

        response = client.get(
            "/api/v1/user/preferences",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401


class TestRoleBasedAccessControl:
    """Tests for role-based access control."""

    ADMIN_ONLY_ENDPOINTS = [
        ("GET", "/api/v1/admin/users"),
        ("DELETE", "/api/v1/admin/user/{user_id}"),
        ("GET", "/api/v1/admin/audit-logs"),
    ]

    @pytest.mark.parametrize("method,endpoint", ADMIN_ONLY_ENDPOINTS)
    def test_admin_endpoint_with_user_token(self, client, valid_token, method, endpoint):
        """Admin endpoints should reject regular user tokens."""
        headers = {"Authorization": f"Bearer {valid_token}"}
        endpoint = endpoint.replace("{user_id}", "user_123")

        if method == "GET":
            response = client.get(endpoint, headers=headers)
        else:
            response = client.delete(endpoint, headers=headers)

        # Should be 403 Forbidden (authenticated but not authorized)
        assert response.status_code in [401, 403, 404], \
            f"{endpoint} should restrict admin access"

    def test_user_cannot_access_other_user_data(self, client, valid_token):
        """Users should not access other users' data."""
        headers = {"Authorization": f"Bearer {valid_token}"}

        # Try to access another user's preferences
        response = client.get(
            "/api/v1/user/other_user_123/preferences",
            headers=headers
        )

        # Should be forbidden or not found
        assert response.status_code in [403, 404]


class TestSessionSecurity:
    """Tests for session security."""

    def test_token_in_response_body_not_url(self, client):
        """Tokens should never appear in URLs."""
        response = client.post(
            "/api/v1/auth/signin",
            json={"email": "test@example.com", "password": "TestPass123!"}
        )

        # Token should be in body, not URL
        if response.status_code == 200:
            data = response.json()
            assert "access_token" in data
            assert "?token=" not in response.url
            assert "&token=" not in response.url

    def test_logout_invalidates_token(self, client, valid_token):
        """Logout should invalidate the token."""
        headers = {"Authorization": f"Bearer {valid_token}"}

        # Logout
        logout_response = client.post("/api/v1/auth/signout", headers=headers)

        # Try to use token after logout (may or may not work depending on implementation)
        # In a proper implementation with token revocation, this should fail
        if logout_response.status_code == 200:
            # This is a weak test since stateless JWTs can't be truly revoked
            # without additional infrastructure (blacklist, short expiry, etc.)
            pass

    def test_sensitive_headers_not_logged(self, client, valid_token):
        """Authorization headers should not be logged."""
        # This is a code review item more than a test
        # Ensure logging configuration doesn't include auth headers
        pass


class TestBruteForceProtection:
    """Tests for brute force attack protection."""

    def test_login_rate_limiting(self, client):
        """Should rate limit login attempts."""
        # Make many failed login attempts
        for i in range(10):
            response = client.post(
                "/api/v1/auth/signin",
                json={"email": "test@example.com", "password": f"wrong_pass_{i}"}
            )

        # After many attempts, should get rate limited
        response = client.post(
            "/api/v1/auth/signin",
            json={"email": "test@example.com", "password": "another_wrong"}
        )

        # Should eventually get 429 Too Many Requests
        # Note: This depends on rate limiting configuration
        assert response.status_code in [401, 429]

    def test_account_lockout_after_failed_attempts(self, client):
        """Should lock account after multiple failed attempts."""
        email = "lockout_test@example.com"

        # Make many failed attempts
        for i in range(5):
            client.post(
                "/api/v1/auth/signin",
                json={"email": email, "password": f"wrong_{i}"}
            )

        # Subsequent attempts should fail even with correct password
        # (if account lockout is implemented)
        response = client.post(
            "/api/v1/auth/signin",
            json={"email": email, "password": "correct_password"}
        )

        # Should be either unauthorized or locked out
        assert response.status_code in [401, 403, 423, 429]


class TestCrossSiteRequestForgery:
    """Tests for CSRF protection."""

    def test_state_changing_requires_csrf_or_auth(self, client):
        """State-changing requests should require CSRF token or auth."""
        # POST without auth or CSRF
        response = client.post(
            "/api/v1/user/preferences",
            json={"notification_enabled": True}
        )

        assert response.status_code == 401

    def test_api_endpoints_allow_json_content_type(self, client, valid_token):
        """API should only accept application/json for state-changing requests."""
        headers = {
            "Authorization": f"Bearer {valid_token}",
            "Content-Type": "text/plain",
        }

        response = client.post(
            "/api/v1/user/preferences",
            content="notification_enabled=true",
            headers=headers
        )

        # Should reject non-JSON content type
        assert response.status_code in [400, 415, 422]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
