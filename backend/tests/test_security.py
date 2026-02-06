"""
Security Tests

Comprehensive tests for security features:
- Security headers
- Rate limiting
- Secrets management
- Password validation
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import time

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


# =============================================================================
# SECURITY HEADERS TESTS
# =============================================================================


class TestSecurityHeaders:
    """Tests for security headers middleware"""

    @pytest.mark.asyncio
    async def test_xframe_options_header(self):
        """Test X-Frame-Options header is DENY"""
        from middleware.security_headers import SecurityHeadersMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.headers.get("X-Frame-Options") == "DENY"

    @pytest.mark.asyncio
    async def test_xcontent_type_options_header(self):
        """Test X-Content-Type-Options header is nosniff"""
        from middleware.security_headers import SecurityHeadersMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    @pytest.mark.asyncio
    async def test_xss_protection_header(self):
        """Test X-XSS-Protection header"""
        from middleware.security_headers import SecurityHeadersMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    @pytest.mark.asyncio
    async def test_csp_header_present(self):
        """Test Content-Security-Policy header is set"""
        from middleware.security_headers import SecurityHeadersMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        csp = response.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src" in csp

    @pytest.mark.asyncio
    async def test_referrer_policy_header(self):
        """Test Referrer-Policy header"""
        from middleware.security_headers import SecurityHeadersMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_permissions_policy_header(self):
        """Test Permissions-Policy header"""
        from middleware.security_headers import SecurityHeadersMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        permissions = response.headers.get("Permissions-Policy")
        assert permissions is not None
        assert "camera=()" in permissions
        assert "microphone=()" in permissions

    @pytest.mark.asyncio
    async def test_api_cache_control_headers(self):
        """Test cache control headers for API endpoints"""
        from middleware.security_headers import SecurityHeadersMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/api/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/api/test")

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

    @pytest.mark.asyncio
    async def test_rate_limit_under_threshold(self, rate_limiter):
        """Test requests under rate limit pass"""
        for _ in range(3):
            allowed, remaining = await rate_limiter.check_rate_limit("test-user", "minute")
            assert allowed is True
            assert remaining >= 0

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, rate_limiter):
        """Test requests over rate limit are blocked"""
        # Use up the limit
        for _ in range(6):
            await rate_limiter.check_rate_limit("test-user-2", "minute")

        allowed, remaining = await rate_limiter.check_rate_limit("test-user-2", "minute")
        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_rate_limit_per_user_isolation(self, rate_limiter):
        """Test rate limits are isolated per user"""
        # Use up limit for user1
        for _ in range(6):
            await rate_limiter.check_rate_limit("user-1", "minute")

        # user2 should still be allowed
        allowed, _ = await rate_limiter.check_rate_limit("user-2", "minute")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_login_attempt_tracking(self, rate_limiter):
        """Test login attempt tracking"""
        # Record failed attempts
        locked = await rate_limiter.record_login_attempt("test@example.com", success=False)
        assert locked is False

        locked = await rate_limiter.record_login_attempt("test@example.com", success=False)
        assert locked is False

        locked = await rate_limiter.record_login_attempt("test@example.com", success=False)
        assert locked is True  # 3rd attempt triggers lockout

    @pytest.mark.asyncio
    async def test_login_lockout_check(self, rate_limiter):
        """Test checking if account is locked"""
        # Trigger lockout
        for _ in range(3):
            await rate_limiter.record_login_attempt("locked@example.com", success=False)

        is_locked, remaining = await rate_limiter.is_locked_out("locked@example.com")
        assert is_locked is True
        assert remaining > 0

    @pytest.mark.asyncio
    async def test_successful_login_clears_attempts(self, rate_limiter):
        """Test successful login clears failed attempts"""
        # Record some failed attempts
        await rate_limiter.record_login_attempt("clear@example.com", success=False)
        await rate_limiter.record_login_attempt("clear@example.com", success=False)

        # Successful login
        locked = await rate_limiter.record_login_attempt("clear@example.com", success=True)
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

    def test_password_strength_check(self):
        """Test password strength assessment"""
        from auth.password import check_password_strength

        weak = check_password_strength("weak")
        assert weak["strength"] == "very_weak"
        assert weak["valid"] is False

        strong = check_password_strength("VeryStrongPassword123!")
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
        from config.secrets import SecretsManager, SecretsError

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
# JWT TOKEN REVOCATION TESTS
# =============================================================================


class TestTokenRevocation:
    """Tests for JWT token revocation"""

    @pytest.fixture
    def jwt_handler(self):
        """Create JWT handler for testing"""
        from auth.jwt_handler import JWTHandler

        return JWTHandler(
            secret_key="test-secret",
            algorithm="HS256",
            access_token_expire_minutes=15,
        )

    def test_token_revocation(self, jwt_handler):
        """Test token can be revoked"""
        token = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com"
        )

        payload = jwt_handler.decode_token(token)
        jti = payload["jti"]

        # Token should work before revocation
        jwt_handler.verify_token(token)

        # Revoke
        jwt_handler.revoke_token(jti)

        # Token should fail after revocation
        from auth.jwt_handler import TokenRevokedError
        with pytest.raises(TokenRevokedError):
            jwt_handler.verify_token(token)

    def test_is_token_revoked(self, jwt_handler):
        """Test checking if token is revoked"""
        assert jwt_handler.is_token_revoked("random-jti") is False

        jwt_handler.revoke_token("random-jti")

        assert jwt_handler.is_token_revoked("random-jti") is True


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestSecurityIntegration:
    """Integration tests for security features"""

    @pytest.mark.asyncio
    async def test_full_auth_flow_with_rate_limiting(self):
        """Test complete auth flow respects rate limits"""
        pass  # Would require full app setup

    @pytest.mark.asyncio
    async def test_security_headers_on_all_responses(self):
        """Test security headers present on all response types"""
        pass  # Would require full app setup
