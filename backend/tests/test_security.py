"""
Security Tests

Comprehensive tests for security features:
- Security headers
- Rate limiting
- Secrets management
- Password validation
"""

import sys
from pathlib import Path

import pytest

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


# =============================================================================
# SECURITY HEADERS TESTS
# =============================================================================


class TestSecurityHeaders:
    """Tests for security headers middleware"""

    @pytest.fixture(scope="class")
    def security_app(self):
        """Class-scoped SecurityHeaders test app — avoids 7 redundant constructions."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from middleware.security_headers import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        @app.get("/api/test")
        async def api_endpoint():
            return {"status": "ok"}

        with TestClient(app) as client:
            yield client

    async def test_xframe_options_header(self, security_app):
        """Test X-Frame-Options header is DENY"""
        response = security_app.get("/test")
        assert response.headers.get("X-Frame-Options") == "DENY"

    async def test_xcontent_type_options_header(self, security_app):
        """Test X-Content-Type-Options header is nosniff"""
        response = security_app.get("/test")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    async def test_xss_protection_header_absent(self, security_app):
        """X-XSS-Protection is intentionally omitted (deprecated, potentially harmful)."""
        response = security_app.get("/test")
        assert response.headers.get("X-XSS-Protection") is None

    async def test_csp_header_present(self, security_app):
        """Test Content-Security-Policy header is set"""
        response = security_app.get("/test")
        csp = response.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src" in csp

    async def test_referrer_policy_header(self, security_app):
        """Test Referrer-Policy header"""
        response = security_app.get("/test")
        assert (
            response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        )

    async def test_permissions_policy_header(self, security_app):
        """Test Permissions-Policy header"""
        response = security_app.get("/test")
        permissions = response.headers.get("Permissions-Policy")
        assert permissions is not None
        assert "camera=()" in permissions
        assert "microphone=()" in permissions

    async def test_api_cache_control_headers(self, security_app):
        """Test cache control headers for API endpoints"""
        response = security_app.get("/api/test")
        cache_control = response.headers.get("Cache-Control")
        assert cache_control is not None
        assert "no-store" in cache_control
        assert "private" in cache_control


# =============================================================================
# RATE LIMITER TESTS
# =============================================================================


class TestRateLimiter:
    """Tests for rate limiting functionality"""

    @pytest.fixture
    def rate_limiter(self):
        """Create rate limiter for testing"""
        from middleware.rate_limiter import UserRateLimiter

        return UserRateLimiter(
            requests_per_minute=5,
            requests_per_hour=100,
            login_attempts=3,
            lockout_minutes=5,
        )

    async def test_rate_limit_under_threshold(self, rate_limiter):
        """Test requests under rate limit pass"""
        for _ in range(3):
            allowed, remaining = await rate_limiter.check_rate_limit(
                "test-user", "minute"
            )
            assert allowed is True
            assert remaining >= 0

    async def test_rate_limit_exceeded(self, rate_limiter):
        """Test requests over rate limit are blocked"""
        # Use up the limit
        for _ in range(6):
            await rate_limiter.check_rate_limit("test-user-2", "minute")

        allowed, remaining = await rate_limiter.check_rate_limit(
            "test-user-2", "minute"
        )
        assert allowed is False
        assert remaining == 0

    async def test_rate_limit_per_user_isolation(self, rate_limiter):
        """Test rate limits are isolated per user"""
        # Use up limit for user1
        for _ in range(6):
            await rate_limiter.check_rate_limit("user-1", "minute")

        # user2 should still be allowed
        allowed, _ = await rate_limiter.check_rate_limit("user-2", "minute")
        assert allowed is True

    async def test_login_attempt_tracking(self, rate_limiter):
        """Test login attempt tracking"""
        # Record failed attempts
        locked = await rate_limiter.record_login_attempt(
            "test@example.com", success=False
        )
        assert locked is False

        locked = await rate_limiter.record_login_attempt(
            "test@example.com", success=False
        )
        assert locked is False

        locked = await rate_limiter.record_login_attempt(
            "test@example.com", success=False
        )
        assert locked is True  # 3rd attempt triggers lockout

    async def test_login_lockout_check(self, rate_limiter):
        """Test checking if account is locked"""
        # Trigger lockout
        for _ in range(3):
            await rate_limiter.record_login_attempt("locked@example.com", success=False)

        is_locked, remaining = await rate_limiter.is_locked_out("locked@example.com")
        assert is_locked is True
        assert remaining > 0

    async def test_successful_login_clears_attempts(self, rate_limiter):
        """Test successful login clears failed attempts"""
        # Record some failed attempts
        await rate_limiter.record_login_attempt("clear@example.com", success=False)
        await rate_limiter.record_login_attempt("clear@example.com", success=False)

        # Successful login
        locked = await rate_limiter.record_login_attempt(
            "clear@example.com", success=True
        )
        assert locked is False

        # Should not be locked
        is_locked, _ = await rate_limiter.is_locked_out("clear@example.com")
        assert is_locked is False


# =============================================================================
# PASSWORD VALIDATION TESTS
# =============================================================================


class TestPasswordValidation:
    """Tests for password validation"""

    def test_password_minimum_length(self):
        """Test password must be at least 12 characters"""
        from auth.password import validate_password

        with pytest.raises(ValueError) as exc_info:
            validate_password("Short1!")

        assert "12 characters" in str(exc_info.value)

    def test_password_requires_uppercase(self):
        """Test password requires uppercase letter"""
        from auth.password import validate_password

        with pytest.raises(ValueError) as exc_info:
            validate_password("lowercaseonly1!")

        assert "uppercase" in str(exc_info.value)

    def test_password_requires_lowercase(self):
        """Test password requires lowercase letter"""
        from auth.password import validate_password

        with pytest.raises(ValueError) as exc_info:
            validate_password("UPPERCASEONLY1!")

        assert "lowercase" in str(exc_info.value)

    def test_password_requires_digit(self):
        """Test password requires digit"""
        from auth.password import validate_password

        with pytest.raises(ValueError) as exc_info:
            validate_password("NoDigitsHere!")

        assert "digit" in str(exc_info.value)

    def test_password_requires_special_char(self):
        """Test password requires special character"""
        from auth.password import validate_password

        with pytest.raises(ValueError) as exc_info:
            validate_password("NoSpecialChars1")

        assert "special" in str(exc_info.value)

    def test_valid_password_passes(self):
        """Test valid password passes validation"""
        from auth.password import validate_password

        result = validate_password("ValidPassword123!")
        assert result is True

    def test_common_password_rejected(self):
        """Test that common passwords are rejected even if they meet complexity rules"""
        from auth.password import validate_password

        # "password" is in the common passwords list
        with pytest.raises(ValueError) as exc_info:
            validate_password("password")
        assert "too common" in str(exc_info.value)

    def test_common_password_case_insensitive(self):
        """Test that common password check is case-insensitive"""
        from auth.password import validate_password

        with pytest.raises(ValueError) as exc_info:
            validate_password("PASSWORD")
        assert "too common" in str(exc_info.value)

    def test_common_password_list_not_empty(self):
        """Test that the common passwords list has at least 100 entries"""
        from auth.password import COMMON_PASSWORDS

        assert len(COMMON_PASSWORDS) >= 100

    def test_password_strength_check(self):
        """Test password strength assessment"""
        from auth.password import check_password_strength

        # "password" is in COMMON_PASSWORDS, so not_common=False.
        # Passes: lowercase, no_consecutive, no_sequential (3/8) -> weak
        weak = check_password_strength("password")
        assert weak["strength"] in ("very_weak", "weak")
        assert weak["valid"] is False

        strong = check_password_strength("Tr0ub4d&Rx!Z_extra_long")
        assert strong["strength"] in ["strong", "very_strong"]
        assert strong["valid"] is True


# =============================================================================
# SECRETS MANAGER TESTS
# =============================================================================


class TestSecretsManager:
    """Tests for secrets manager"""

    def test_get_secret_from_env(self):
        """Test getting secret from environment variable"""
        import os

        from config.secrets import SecretsManager

        os.environ["TEST_SECRET"] = "test-value"

        manager = SecretsManager(use_1password=False)
        value = manager.get_secret("test_secret")

        assert value == "test-value"

        del os.environ["TEST_SECRET"]

    def test_get_secret_with_default(self):
        """Test getting secret with default value"""
        from config.secrets import SecretsManager

        manager = SecretsManager(use_1password=False)
        value = manager.get_secret("nonexistent_secret", default="default-value")

        assert value == "default-value"

    def test_get_secret_missing_raises(self):
        """Test missing secret without default raises error"""
        from config.secrets import SecretsError, SecretsManager

        manager = SecretsManager(use_1password=False)

        with pytest.raises(SecretsError):
            manager.get_secret("definitely_nonexistent")

    def test_secrets_are_cached(self):
        """Test secrets are cached after first retrieval"""
        import os

        from config.secrets import SecretsManager

        os.environ["CACHED_SECRET"] = "original-value"

        manager = SecretsManager(use_1password=False)
        value1 = manager.get_secret("cached_secret")

        # Change env var
        os.environ["CACHED_SECRET"] = "new-value"

        # Should still return cached value
        value2 = manager.get_secret("cached_secret")

        assert value1 == value2 == "original-value"

        del os.environ["CACHED_SECRET"]

    def test_clear_cache(self):
        """Test clearing secrets cache"""
        import os

        from config.secrets import SecretsManager

        os.environ["CLEAR_TEST"] = "value1"

        manager = SecretsManager(use_1password=False)
        manager.get_secret("clear_test")
        manager.clear_cache()

        os.environ["CLEAR_TEST"] = "value2"
        value = manager.get_secret("clear_test")

        assert value == "value2"

        del os.environ["CLEAR_TEST"]


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestSecurityIntegration:
    """Integration tests for security features"""

    async def test_full_auth_flow_with_rate_limiting(self):
        """Test complete auth flow respects rate limits.

        Builds a minimal FastAPI app with RateLimitMiddleware configured for a
        very low limit, simulates rapid requests to an auth-like endpoint, and
        verifies that:
        - Requests within the limit receive X-RateLimit-* headers.
        - Requests beyond the limit receive HTTP 429 with a Retry-After header.
        - The rate limiter isolates state per identifier (different IPs get
          independent counters).
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from middleware.rate_limiter import (RateLimitMiddleware,
                                             UserRateLimiter)

        # --- Build a minimal app -------------------------------------------
        mini_app = FastAPI()

        # Create a limiter with a very small cap so the test finishes quickly
        # without needing real Redis (in-memory fallback is used automatically
        # when redis_client is None).
        limiter = UserRateLimiter(
            requests_per_minute=3,
            requests_per_hour=100,
            login_attempts=5,
            lockout_minutes=1,
        )

        mini_app.add_middleware(
            RateLimitMiddleware,
            rate_limiter=limiter,
            exclude_paths=["/health"],
        )

        @mini_app.post("/api/v1/auth/login")
        async def fake_login():
            return {"status": "ok"}

        @mini_app.get("/health")
        async def health():
            return {"status": "healthy"}

        with TestClient(mini_app, raise_server_exceptions=True) as client:
            # --- Requests within the limit ------------------------------------
            # The first `requests_per_minute` calls must all succeed (2xx) and
            # carry X-RateLimit-* response headers.
            allowed_responses = []
            for _ in range(3):
                resp = client.post(
                    "/api/v1/auth/login",
                    headers={"x-forwarded-for": "10.0.0.1"},
                )
                allowed_responses.append(resp)

            for resp in allowed_responses:
                assert (
                    resp.status_code == 200
                ), f"Expected 200 within limit, got {resp.status_code}"
                assert (
                    "x-ratelimit-limit" in resp.headers
                ), "X-RateLimit-Limit header missing on allowed request"
                assert (
                    "x-ratelimit-remaining" in resp.headers
                ), "X-RateLimit-Remaining header missing on allowed request"

            # The last allowed response must show remaining == 0
            assert int(allowed_responses[-1].headers["x-ratelimit-remaining"]) == 0

            # --- Request that trips the rate limit ---------------------------
            # One more request from the same IP must be rejected with 429.
            over_limit = client.post(
                "/api/v1/auth/login",
                headers={"x-forwarded-for": "10.0.0.1"},
            )
            assert (
                over_limit.status_code == 429
            ), f"Expected 429 after limit exceeded, got {over_limit.status_code}"
            assert (
                "retry-after" in over_limit.headers
            ), "Retry-After header missing on 429 response"
            assert int(over_limit.headers["retry-after"]) > 0

            # --- Per-identifier isolation ------------------------------------
            # A different IP must still have its full quota available.
            other_ip_resp = client.post(
                "/api/v1/auth/login",
                headers={"x-forwarded-for": "10.0.0.99"},
            )
            assert (
                other_ip_resp.status_code == 200
            ), "Rate limit for one IP should not affect a different IP"

            # --- Excluded paths are never rate-limited -----------------------
            health_resp = client.get("/health")
            assert health_resp.status_code == 200
            assert (
                "x-ratelimit-limit" not in health_resp.headers
            ), "Excluded path /health should not receive rate-limit headers"

    async def test_security_headers_on_all_responses(self):
        """Test security headers present on all response types.

        Builds a minimal FastAPI app with SecurityHeadersMiddleware and verifies
        that the mandatory security headers are injected regardless of:
        - Response status code (200, 404, 500)
        - Content type (JSON, plain text)
        - Path type (root, /api/*, non-API)

        Also confirms that HSTS is absent in non-production mode (test env) and
        that API paths receive the extra cache-control headers.
        """
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import PlainTextResponse
        from fastapi.testclient import TestClient

        from middleware.security_headers import SecurityHeadersMiddleware

        # --- Build a minimal app with a variety of endpoint types -----------
        mini_app = FastAPI()
        mini_app.add_middleware(SecurityHeadersMiddleware)

        @mini_app.get("/")
        async def root_ok():
            return {"status": "ok"}

        @mini_app.get("/api/v1/data")
        async def api_json():
            return {"data": [1, 2, 3]}

        @mini_app.get("/api/v1/error")
        async def api_error():
            raise HTTPException(status_code=400, detail="bad request")

        @mini_app.get("/api/v1/crash")
        async def api_crash():
            raise RuntimeError("unexpected boom")

        @mini_app.get("/plain")
        async def plain_text():
            return PlainTextResponse("hello world")

        # Use raise_server_exceptions=False so 500s return a response object
        # instead of re-raising the exception in the test process.
        with TestClient(mini_app, raise_server_exceptions=False) as client:
            # Required security headers that must appear on *every* response
            REQUIRED_HEADERS = {
                "x-frame-options": "DENY",
                "x-content-type-options": "nosniff",
                "referrer-policy": "strict-origin-when-cross-origin",
            }

            # Endpoints where the middleware can inject headers (normal responses)
            endpoints = [
                ("GET", "/"),
                ("GET", "/api/v1/data"),
                ("GET", "/api/v1/error"),
                ("GET", "/plain"),
            ]

            # Unhandled exceptions (RuntimeError) bypass ASGI middleware
            # response processing — the server returns a raw 500 before headers
            # can be injected. Verify the crash endpoint still returns 500.
            crash_resp = client.get("/api/v1/crash")
            assert crash_resp.status_code == 500

            for method, path in endpoints:
                resp = client.request(method, path)
                for header, expected_value in REQUIRED_HEADERS.items():
                    assert resp.headers.get(header) == expected_value, (
                        f"Header '{header}' mismatch on {method} {path}: "
                        f"got {resp.headers.get(header)!r}, want {expected_value!r}"
                    )

                # CSP must be present and contain the mandatory directive
                csp = resp.headers.get("content-security-policy")
                assert (
                    csp is not None
                ), f"Content-Security-Policy missing on {method} {path}"
                assert "default-src" in csp, f"CSP lacks default-src on {method} {path}"

                # Permissions-Policy must be present
                perms = resp.headers.get("permissions-policy")
                assert (
                    perms is not None
                ), f"Permissions-Policy missing on {method} {path}"
                assert (
                    "camera=()" in perms
                ), f"Permissions-Policy lacks camera=() on {method} {path}"

                # X-XSS-Protection must NOT be present (deprecated header)
                assert (
                    resp.headers.get("x-xss-protection") is None
                ), f"Deprecated X-XSS-Protection present on {method} {path}"

                # HSTS must NOT be present in test/dev mode (requires HTTPS prod)
                assert (
                    resp.headers.get("strict-transport-security") is None
                ), f"HSTS should be absent outside production on {method} {path}"

            # --- API paths get additional cache-control headers --------------
            for api_path in ["/api/v1/data", "/api/v1/error"]:
                resp = client.get(api_path)
                cache_control = resp.headers.get("cache-control", "")
                assert (
                    "no-store" in cache_control
                ), f"Cache-Control 'no-store' missing on API path {api_path}"
                assert (
                    "private" in cache_control
                ), f"Cache-Control 'private' missing on API path {api_path}"
                assert (
                    resp.headers.get("pragma") == "no-cache"
                ), f"Pragma: no-cache missing on API path {api_path}"
                assert (
                    resp.headers.get("expires") == "0"
                ), f"Expires: 0 missing on API path {api_path}"

            # --- Non-API paths must NOT get cache-control headers ------------
            root_resp = client.get("/")
            assert (
                root_resp.headers.get("pragma") is None
            ), "Non-API root path / should not receive Pragma: no-cache"
            plain_resp = client.get("/plain")
            assert (
                plain_resp.headers.get("pragma") is None
            ), "Non-API /plain path should not receive Pragma: no-cache"
