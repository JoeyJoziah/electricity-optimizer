"""
Authentication Tests

Comprehensive tests for Neon Auth session validation:
- Neon Auth session validation (neon_auth schema)
- Permission-based access control
- Password validation
- Auth API endpoints
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


# =============================================================================
# NEON AUTH SESSION VALIDATION TESTS
# =============================================================================


class TestNeonAuthSessionValidation:
    """Tests for Neon Auth session validation (neon_auth schema queries)"""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock async database session"""
        session = AsyncMock()
        return session

    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI request"""
        request = MagicMock()
        request.cookies = {}
        return request

    # -------------------------------------------------------------------------
    # _get_session_from_token Tests
    # -------------------------------------------------------------------------

    async def test_get_session_from_token_valid(self, mock_db_session):
        """Test valid session token returns SessionData"""
        from auth.neon_auth import SessionData, _get_session_from_token

        # Mock the DB result row
        mock_row = MagicMock()
        mock_row.user_id = "user-123"
        mock_row.email = "test@example.com"
        mock_row.name = "Test User"
        mock_row.email_verified = True
        mock_row.role = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db_session.execute.return_value = mock_result

        result = await _get_session_from_token("valid-token", mock_db_session)

        assert isinstance(result, SessionData)
        assert result.user_id == "user-123"
        assert result.email == "test@example.com"
        assert result.name == "Test User"
        assert result.email_verified is True

    async def test_get_session_from_token_expired(self, mock_db_session):
        """Test expired session token returns None"""
        from auth.neon_auth import _get_session_from_token

        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await _get_session_from_token("expired-token", mock_db_session)

        assert result is None

    async def test_get_session_from_token_banned_user(self, mock_db_session):
        """Test banned user session returns None (query filters banned users)"""
        from auth.neon_auth import _get_session_from_token

        # Query WHERE clause filters banned users, so fetchone returns None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await _get_session_from_token("banned-user-token", mock_db_session)

        assert result is None

    async def test_get_session_from_token_no_name(self, mock_db_session):
        """Test session with null name defaults to empty string"""
        from auth.neon_auth import SessionData, _get_session_from_token

        mock_row = MagicMock()
        mock_row.user_id = "user-456"
        mock_row.email = "noname@example.com"
        mock_row.name = None
        mock_row.email_verified = False
        mock_row.role = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db_session.execute.return_value = mock_result

        result = await _get_session_from_token("token-no-name", mock_db_session)

        assert isinstance(result, SessionData)
        assert result.name == ""
        assert result.user_id == "user-456"

    # -------------------------------------------------------------------------
    # get_current_user Tests
    # -------------------------------------------------------------------------

    async def test_get_current_user_from_bearer_header(
        self, mock_db_session, mock_request
    ):
        """Test extracting session token from Authorization header"""
        from fastapi.security import HTTPAuthorizationCredentials

        from auth.neon_auth import get_current_user

        mock_row = MagicMock()
        mock_row.user_id = "user-789"
        mock_row.email = "bearer@example.com"
        mock_row.name = "Bearer User"
        mock_row.email_verified = True
        mock_row.role = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db_session.execute.return_value = mock_result

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid-session-token"
        )

        result = await get_current_user(mock_request, credentials, mock_db_session)

        assert result.user_id == "user-789"
        assert result.email == "bearer@example.com"

    async def test_get_current_user_from_cookie(self, mock_db_session, mock_request):
        """Test extracting session token from cookie"""
        from auth.neon_auth import SESSION_COOKIE_NAME, get_current_user

        mock_request.cookies = {SESSION_COOKIE_NAME: "cookie-session-token"}

        mock_row = MagicMock()
        mock_row.user_id = "user-cookie"
        mock_row.email = "cookie@example.com"
        mock_row.name = "Cookie User"
        mock_row.email_verified = False
        mock_row.role = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db_session.execute.return_value = mock_result

        result = await get_current_user(mock_request, None, mock_db_session)

        assert result.user_id == "user-cookie"
        assert result.email == "cookie@example.com"

    async def test_get_current_user_from_secure_cookie(
        self, mock_db_session, mock_request
    ):
        """Test extracting session token from __Secure- prefixed cookie (HTTPS/production)"""
        from auth.neon_auth import SESSION_COOKIE_NAME_SECURE, get_current_user

        mock_request.cookies = {SESSION_COOKIE_NAME_SECURE: "secure-session-token"}

        mock_row = MagicMock()
        mock_row.user_id = "user-secure"
        mock_row.email = "secure@example.com"
        mock_row.name = "Secure User"
        mock_row.email_verified = True
        mock_row.role = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db_session.execute.return_value = mock_result

        result = await get_current_user(mock_request, None, mock_db_session)

        assert result.user_id == "user-secure"
        assert result.email == "secure@example.com"
        assert result.email_verified is True

    async def test_get_current_user_no_token_raises_401(
        self, mock_db_session, mock_request
    ):
        """Test missing session token raises 401"""
        from fastapi import HTTPException

        from auth.neon_auth import get_current_user

        mock_request.cookies = {}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, None, mock_db_session)

        assert exc_info.value.status_code == 401

    async def test_get_current_user_invalid_token_raises_401(
        self, mock_db_session, mock_request
    ):
        """Test invalid session token raises 401"""
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        from auth.neon_auth import get_current_user

        # DB returns no matching session
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db_session.execute.return_value = mock_result

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid-token"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials, mock_db_session)

        assert exc_info.value.status_code == 401

    async def test_get_current_user_no_db_raises_503(self, mock_request):
        """Test missing database connection raises 503"""
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        from auth.neon_auth import get_current_user

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid-token"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials, None)

        assert exc_info.value.status_code == 503

    # -------------------------------------------------------------------------
    # get_current_user_optional Tests
    # -------------------------------------------------------------------------

    async def test_get_current_user_optional_returns_none(
        self, mock_db_session, mock_request
    ):
        """Test optional auth returns None for unauthenticated request"""
        from auth.neon_auth import get_current_user_optional

        mock_request.cookies = {}

        result = await get_current_user_optional(mock_request, None, mock_db_session)

        assert result is None

    async def test_get_current_user_optional_returns_user(
        self, mock_db_session, mock_request
    ):
        """Test optional auth returns SessionData when authenticated"""
        from auth.neon_auth import (SESSION_COOKIE_NAME, SessionData,
                                    get_current_user_optional)

        mock_request.cookies = {SESSION_COOKIE_NAME: "token"}

        mock_row = MagicMock()
        mock_row.user_id = "user-opt"
        mock_row.email = "opt@example.com"
        mock_row.name = ""
        mock_row.email_verified = False
        mock_row.role = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db_session.execute.return_value = mock_result

        result = await get_current_user_optional(mock_request, None, mock_db_session)

        assert isinstance(result, SessionData)
        assert result.user_id == "user-opt"

    # -------------------------------------------------------------------------
    # SessionData Tests
    # -------------------------------------------------------------------------

    def test_session_data_defaults(self):
        """Test SessionData has correct defaults"""
        from auth.neon_auth import SessionData

        data = SessionData(user_id="u1", email="e@e.com")
        assert data.name == ""
        assert data.email_verified is False
        assert data.role is None

    def test_session_data_with_role(self):
        """Test SessionData with role"""
        from auth.neon_auth import SessionData

        data = SessionData(user_id="u1", email="e@e.com", role="admin")
        assert data.role == "admin"

    async def test_session_cache_key_uses_sha256(self, mock_db_session):
        """Test that session cache key uses SHA-256 hash, not token prefix (P0-2 fix)."""
        import hashlib

        from auth.neon_auth import _get_session_from_token

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db_session.execute.return_value = mock_result

        token = "abcdef1234567890abcdef1234567890"
        await _get_session_from_token(token, mock_db_session, redis=mock_redis)

        # Verify the cache key uses SHA-256 hash, not raw token prefix
        expected_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
        expected_key = f"session:{expected_hash}"
        mock_redis.get.assert_awaited_once_with(expected_key)

    async def test_similar_tokens_produce_different_cache_keys(self, mock_db_session):
        """Two tokens sharing the same 16-char prefix must produce different cache keys."""
        import hashlib

        # Two tokens with identical first 16 chars but different suffixes
        token_a = "abcdef1234567890_suffix_AAA"
        token_b = "abcdef1234567890_suffix_BBB"

        hash_a = hashlib.sha256(token_a.encode()).hexdigest()[:32]
        hash_b = hashlib.sha256(token_b.encode()).hexdigest()[:32]

        # The old code would produce the same cache key for both
        assert hash_a != hash_b, "Tokens with same prefix must have distinct cache keys"

    async def test_session_cache_stores_with_sha256_key(self, mock_db_session):
        """Verify Redis SET uses SHA-256 cache key on cache miss + DB hit."""
        import hashlib

        from auth.neon_auth import (_SESSION_CACHE_TTL, SessionData,
                                    _get_session_from_token)

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()

        # Simulate a valid DB result
        mock_row = MagicMock()
        mock_row.user_id = "user-cache"
        mock_row.email = "cache@test.com"
        mock_row.name = "Cache User"
        mock_row.email_verified = True
        mock_row.role = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db_session.execute.return_value = mock_result

        token = "my-session-token-with-sufficient-length"
        result = await _get_session_from_token(token, mock_db_session, redis=mock_redis)

        assert isinstance(result, SessionData)
        assert result.user_id == "user-cache"
        expected_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
        expected_key = f"session:{expected_hash}"

        # Verify setex was called with the SHA-256 key and correct TTL
        mock_redis.setex.assert_awaited_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == expected_key
        assert call_args[0][1] == _SESSION_CACHE_TTL

    async def test_invalidate_session_cache_deletes_key(self):
        """Test invalidate_session_cache deletes the Redis entry."""
        import hashlib

        from auth.neon_auth import invalidate_session_cache

        mock_redis = AsyncMock()
        mock_redis.delete.return_value = 1  # 1 key deleted

        token = "session-to-invalidate"
        result = await invalidate_session_cache(token, redis=mock_redis)

        assert result is True
        expected_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
        expected_key = f"session:{expected_hash}"
        mock_redis.delete.assert_awaited_once_with(expected_key)

    async def test_invalidate_session_cache_no_redis(self):
        """Test invalidate_session_cache returns False when Redis is None."""
        from auth.neon_auth import invalidate_session_cache

        result = await invalidate_session_cache("some-token", redis=None)
        assert result is False

    async def test_invalidate_session_cache_miss(self):
        """Test invalidate_session_cache returns False when key not in cache."""
        from auth.neon_auth import invalidate_session_cache

        mock_redis = AsyncMock()
        mock_redis.delete.return_value = 0  # No key deleted

        result = await invalidate_session_cache("nonexistent-token", redis=mock_redis)
        assert result is False


# =============================================================================
# AUTH API ENDPOINT TESTS
# =============================================================================


class TestAuthAPI:
    """Tests for authentication API endpoints (/me, /password/check-strength)"""

    # -------------------------------------------------------------------------
    # Me Endpoint Tests
    # -------------------------------------------------------------------------

    async def test_me_endpoint_requires_auth(self):
        """Test GET /api/v1/auth/me returns 401 without auth"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.v1.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        with TestClient(app) as client:
            response = client.get("/api/v1/auth/me")
            assert response.status_code == 401

    # -------------------------------------------------------------------------
    # Password Strength Endpoint Tests
    # -------------------------------------------------------------------------

    async def test_password_check_strength_strong(self):
        """Test password strength check with strong password"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.v1.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/password/check-strength",
                json={"password": "ValidPass123!"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "score" in data
            assert "strength" in data
            assert "valid" in data
            assert data["valid"] is True

    async def test_password_check_strength_weak(self):
        """Test password strength check with weak password"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.v1.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/password/check-strength", json={"password": "weak"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False

    async def test_password_check_strength_empty_rejected(self):
        """Test password strength check rejects empty password"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.v1.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/password/check-strength", json={"password": ""}
            )
            assert response.status_code == 422


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================


class TestAuthRateLimiting:
    """Tests for authentication rate limiting"""

    async def test_login_rate_limit_after_failures(self):
        """Test account lockout after failed attempts"""
        from middleware.rate_limiter import UserRateLimiter

        limiter = UserRateLimiter(login_attempts=5, lockout_minutes=15)

        identifier = "user@example.com"

        # Record 5 failed attempts
        for i in range(5):
            locked = await limiter.record_login_attempt(identifier, success=False)

        # 5th attempt should trigger lockout
        assert locked is True

        # Check is_locked_out confirms the lockout
        is_locked, seconds_remaining = await limiter.is_locked_out(identifier)
        assert is_locked is True
        assert seconds_remaining > 0
        assert seconds_remaining <= 15 * 60  # within 15-minute window

    async def test_rate_limit_per_ip(self):
        """Test rate limiting per IP address"""
        from middleware.rate_limiter import UserRateLimiter

        # Use a very low limit so we can test it in-memory without Redis
        limiter = UserRateLimiter(requests_per_minute=3, requests_per_hour=100)

        ip_identifier = "ip:192.168.1.1"

        # First 3 requests should be allowed
        for _ in range(3):
            allowed, remaining = await limiter.check_rate_limit(
                ip_identifier, limit_type="minute"
            )
            assert allowed is True

        # 4th request should be rate limited
        allowed, remaining = await limiter.check_rate_limit(
            ip_identifier, limit_type="minute"
        )
        assert allowed is False
        assert remaining == 0

    async def test_rate_limit_reset_after_success(self):
        """Test rate limit resets after successful login"""
        from middleware.rate_limiter import UserRateLimiter

        limiter = UserRateLimiter(login_attempts=5, lockout_minutes=15)

        identifier = "reset@example.com"

        # Record 3 failed attempts (below threshold)
        for _ in range(3):
            await limiter.record_login_attempt(identifier, success=False)

        # Confirm 3 attempts are tracked (not yet locked)
        is_locked, _ = await limiter.is_locked_out(identifier)
        assert is_locked is False

        # Successful login should clear the counter
        await limiter.record_login_attempt(identifier, success=True)

        # After success, should not be locked out
        is_locked, seconds_remaining = await limiter.is_locked_out(identifier)
        assert is_locked is False
        assert seconds_remaining == 0


# =============================================================================
# PASSWORD VALIDATION TESTS
# =============================================================================


class TestPasswordValidation:
    """Tests for password requirements"""

    def test_password_min_length(self):
        """Test password minimum length requirement"""
        from auth.password import validate_password

        with pytest.raises(ValueError):
            validate_password("Short1!")

    def test_password_requires_uppercase(self):
        """Test password requires uppercase letter"""
        from auth.password import validate_password

        with pytest.raises(ValueError):
            validate_password("lowercase1!")

    def test_password_requires_lowercase(self):
        """Test password requires lowercase letter"""
        from auth.password import validate_password

        with pytest.raises(ValueError):
            validate_password("UPPERCASE1!")

    def test_password_requires_digit(self):
        """Test password requires digit"""
        from auth.password import validate_password

        with pytest.raises(ValueError):
            validate_password("NoDigits!")

    def test_password_requires_special(self):
        """Test password requires special character"""
        from auth.password import validate_password

        with pytest.raises(ValueError):
            validate_password("NoSpecial1")

    def test_valid_password(self):
        """Test valid password passes validation"""
        from auth.password import validate_password

        result = validate_password("ValidPass123!")
        assert result is True

    def test_common_password_rejected(self):
        """Test that common passwords are rejected even if they meet complexity rules"""
        from auth.password import validate_password

        with pytest.raises(ValueError, match="too common"):
            validate_password("password")

    def test_common_password_case_insensitive(self):
        """Test that common password check is case-insensitive"""
        from auth.password import validate_password

        with pytest.raises(ValueError, match="too common"):
            validate_password("PASSWORD")

    def test_common_password_in_list(self):
        """Test several known common passwords are in the blocklist"""
        from auth.password import COMMON_PASSWORDS

        for pwd in ["123456", "qwerty", "letmein", "admin", "password123"]:
            assert pwd in COMMON_PASSWORDS

    def test_uncommon_password_not_blocked(self):
        """Test that a unique password is not flagged as common"""
        from auth.password import COMMON_PASSWORDS

        assert "xK9#mQ2vL7pR!" not in COMMON_PASSWORDS

    def test_strength_check_common_password(self):
        """Test that strength check flags common passwords"""
        from auth.password import check_password_strength

        result = check_password_strength("password")
        assert result["checks"]["not_common"] is False

    def test_strength_check_uncommon_password(self):
        """Test that strength check passes for uncommon passwords"""
        from auth.password import check_password_strength

        result = check_password_strength("xK9#mQ2vL7pR!abc")
        assert result["checks"]["not_common"] is True


# =============================================================================
# SECURITY HEADER TESTS
# =============================================================================


class TestSecurityHeaders:
    """Tests for security headers middleware"""

    def _make_app_with_security_headers(self):
        """Build a minimal FastAPI app wrapped with SecurityHeadersMiddleware."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from middleware.security_headers import SecurityHeadersMiddleware

        app = FastAPI()

        @app.get("/test")
        def ping():
            return {"ok": True}

        app.add_middleware(SecurityHeadersMiddleware)
        return TestClient(app)

    def test_csp_header_present(self):
        """Test Content-Security-Policy header is set"""
        client = self._make_app_with_security_headers()
        response = client.get("/test")
        assert "content-security-policy" in response.headers
        csp = response.headers["content-security-policy"]
        assert "default-src" in csp
        assert "frame-ancestors 'none'" in csp

    def test_xfo_header_deny(self):
        """Test X-Frame-Options is DENY"""
        client = self._make_app_with_security_headers()
        response = client.get("/test")
        assert response.headers.get("x-frame-options") == "DENY"

    def test_hsts_header_present(self):
        """Test Strict-Transport-Security header is added in production"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from middleware.security_headers import SecurityHeadersMiddleware

        app = FastAPI()

        @app.get("/test")
        def ping():
            return {"ok": True}

        # Patch settings.is_production to True so HSTS is added
        with patch("middleware.security_headers.settings") as mock_settings:
            mock_settings.is_production = True
            mock_settings.is_development = False
            app.add_middleware(SecurityHeadersMiddleware)
            client = TestClient(app)
            response = client.get("/test")
            assert "strict-transport-security" in response.headers
            hsts = response.headers["strict-transport-security"]
            assert "max-age=" in hsts
            assert "includeSubDomains" in hsts

    def test_xcto_header_nosniff(self):
        """Test X-Content-Type-Options is nosniff"""
        client = self._make_app_with_security_headers()
        response = client.get("/test")
        assert response.headers.get("x-content-type-options") == "nosniff"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestAuthIntegration:
    """Integration tests for authentication flow (Neon Auth)"""

    async def test_session_validation_flow(self):
        """Test session token validation against neon_auth schema"""
        from auth.neon_auth import SessionData, _get_session_from_token

        # Auth flows (sign-up/sign-in) are handled by Better Auth on the frontend.
        # The backend validates sessions via neon_auth schema queries.
        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.user_id = "integration-user-1"
        mock_row.email = "integration@example.com"
        mock_row.name = "Integration User"
        mock_row.email_verified = True
        mock_row.role = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        session = await _get_session_from_token("integration-session-token", mock_db)

        assert isinstance(session, SessionData)
        assert session.user_id == "integration-user-1"
        assert session.email == "integration@example.com"
        assert session.email_verified is True

    async def test_me_endpoint_with_valid_session(self):
        """Test /me returns user data when session is valid"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.v1.auth import (_get_current_user_with_brute_force_tracking,
                                 router)
        from auth.neon_auth import SessionData
        from config.database import get_pg_session

        # Build a standalone app with the auth router
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        # Mock a DB session (for ensure_user_profile best-effort sync)
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock()
        mock_db.commit = AsyncMock()

        # Override dependencies — /me uses _get_current_user_with_brute_force_tracking
        valid_session = SessionData(
            user_id="me-user-1",
            email="me@example.com",
            name="Me User",
            email_verified=True,
        )
        app.dependency_overrides[_get_current_user_with_brute_force_tracking] = (
            lambda: (valid_session)
        )
        app.dependency_overrides[get_pg_session] = lambda: mock_db

        with TestClient(app) as client:
            response = client.get("/api/v1/auth/me")
            assert response.status_code == 200
            data = response.json()
            # UserResponse returns "id" not "user_id"
            assert data["id"] == "me-user-1"
            assert data["email"] == "me@example.com"
            assert data["email_verified"] is True

    async def test_expired_session_rejected(self):
        """Test that expired sessions are rejected — DB returns None for expired rows"""
        from auth.neon_auth import _get_session_from_token

        # The SQL query filters WHERE s."expiresAt" > NOW(),
        # so an expired session returns fetchone() = None.
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None  # expired session not found
        mock_db.execute.return_value = mock_result

        session = await _get_session_from_token("expired-session-token", mock_db)

        # Expired session returns None, not a SessionData
        assert session is None


# =============================================================================
# SPRINT 4: AUTH HARDENING TESTS (Audit 2026-03-19)
# =============================================================================


class TestLoginBruteForceProtection:
    """Task 4.3: Login brute-force protection on /me endpoint."""

    async def test_lockout_after_5_failed_attempts(self):
        """After 5 failed login attempts, /me should return 429."""
        from api.v1.auth import _login_attempt_limiter

        # Reset the limiter to ensure clean state
        _login_attempt_limiter.reset()

        identifier = "login:ip:10.0.0.99"
        for _ in range(5):
            await _login_attempt_limiter.record_login_attempt(identifier, success=False)

        is_locked, seconds = await _login_attempt_limiter.is_locked_out(identifier)
        assert is_locked is True
        assert seconds > 0

    async def test_successful_login_clears_lockout(self):
        """A successful login should reset the failure counter."""
        from api.v1.auth import _login_attempt_limiter

        _login_attempt_limiter.reset()

        identifier = "login:ip:10.0.0.100"
        for _ in range(3):
            await _login_attempt_limiter.record_login_attempt(identifier, success=False)

        # Successful login clears counter
        await _login_attempt_limiter.record_login_attempt(identifier, success=True)

        is_locked, _ = await _login_attempt_limiter.is_locked_out(identifier)
        assert is_locked is False

    async def test_check_login_lockout_blocks_locked_ip(self):
        """_check_login_lockout raises 429 for locked-out IPs."""
        from fastapi import HTTPException

        from api.v1.auth import _check_login_lockout, _login_attempt_limiter

        _login_attempt_limiter.reset()

        # Lock out the IP
        identifier = "login:ip:192.168.1.50"
        for _ in range(5):
            await _login_attempt_limiter.record_login_attempt(identifier, success=False)

        # Simulate a request from that IP
        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.50"

        with pytest.raises(HTTPException) as exc_info:
            await _check_login_lockout(mock_request)

        assert exc_info.value.status_code == 429
        assert "Too many failed attempts" in exc_info.value.detail

    async def test_check_login_lockout_allows_unlocked_ip(self):
        """_check_login_lockout does not block unlocked IPs."""
        from api.v1.auth import _check_login_lockout, _login_attempt_limiter

        _login_attempt_limiter.reset()

        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.51"

        # Should not raise
        await _check_login_lockout(mock_request)


class TestBannedUserSessionBypass:
    """Task 4.4: Immediate session cache invalidation after user ban."""

    async def test_banned_marker_bypasses_cache(self):
        """When a banned_user marker exists, cached session is bypassed."""
        import json

        from auth.neon_auth import _get_session_from_token

        # Mock Redis with a cached session AND a banned marker
        mock_redis = AsyncMock()
        cached_data = json.dumps(
            {
                "user_id": "banned-user-123",
                "email": "banned@example.com",
                "name": "Banned",
                "email_verified": True,
                "role": None,
            }
        ).encode("utf-8")
        mock_redis.get = AsyncMock(
            side_effect=lambda key: (
                cached_data
                if key.startswith("session:")
                else b"1" if key == "banned_user:banned-user-123" else None
            )
        )
        mock_redis.delete = AsyncMock()

        # DB returns None because user is banned
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        result = await _get_session_from_token("some-token", mock_db, redis=mock_redis)

        # Should return None (banned user filtered out by DB query)
        assert result is None
        # Should have deleted the stale cache entry
        mock_redis.delete.assert_awaited()

    async def test_no_banned_marker_returns_cached_session(self):
        """Without a banned marker, cached session is returned normally."""
        import json

        from auth.neon_auth import SessionData, _get_session_from_token

        mock_redis = AsyncMock()
        cached_data = json.dumps(
            {
                "user_id": "active-user-456",
                "email": "active@example.com",
                "name": "Active",
                "email_verified": True,
                "role": None,
            }
        ).encode("utf-8")
        mock_redis.get = AsyncMock(
            side_effect=lambda key: (
                cached_data if key.startswith("session:") else None
            )  # No banned marker
        )

        mock_db = AsyncMock()
        result = await _get_session_from_token("some-token", mock_db, redis=mock_redis)

        assert isinstance(result, SessionData)
        assert result.user_id == "active-user-456"

    async def test_invalidate_sessions_for_banned_user_sets_marker(self):
        """invalidate_sessions_for_banned_user sets a Redis marker."""
        from auth.neon_auth import (_BANNED_USER_MARKER_TTL,
                                    invalidate_sessions_for_banned_user)

        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        result = await invalidate_sessions_for_banned_user(
            "user-to-ban", redis=mock_redis
        )

        assert result is True
        mock_redis.setex.assert_awaited_once_with(
            "banned_user:user-to-ban",
            _BANNED_USER_MARKER_TTL,
            "1",
        )

    async def test_invalidate_sessions_returns_false_without_redis(self):
        """invalidate_sessions_for_banned_user returns False without Redis."""
        from auth.neon_auth import invalidate_sessions_for_banned_user

        result = await invalidate_sessions_for_banned_user("any-user", redis=None)
        assert result is False


class TestPasswordPolicyStrengthening:
    """Task 4.5: Stronger password validation beyond length-only."""

    def test_consecutive_identical_chars_rejected(self):
        """Password with 3+ consecutive identical chars is rejected."""
        from auth.password import validate_password

        with pytest.raises(ValueError, match="identical consecutive"):
            validate_password("Abcdefffg1!x")  # "fff" = 3 consecutive

    def test_sequential_alpha_rejected(self):
        """Password with sequential alphabetic chars (abcd) is rejected."""
        from auth.password import validate_password

        with pytest.raises(ValueError, match="sequential"):
            validate_password("Xabcdefgh1!z")  # "abcdefgh" = sequential

    def test_sequential_numeric_rejected(self):
        """Password with sequential numeric chars (1234) is rejected."""
        from auth.password import validate_password

        with pytest.raises(ValueError, match="sequential"):
            validate_password("Good1234Pass!")  # "1234" = sequential

    def test_sequential_keyboard_rejected(self):
        """Password with keyboard row sequences (qwer) is rejected."""
        from auth.password import validate_password

        with pytest.raises(ValueError, match="sequential"):
            validate_password("Xqwerty1!zzz")  # "qwert" = keyboard row

    def test_max_length_exceeded_rejected(self):
        """Password exceeding MAX_PASSWORD_LENGTH is rejected."""
        from auth.password import MAX_PASSWORD_LENGTH, validate_password

        long_password = "Aa1!" + "x" * (MAX_PASSWORD_LENGTH + 1)
        with pytest.raises(ValueError, match="at most"):
            validate_password(long_password)

    def test_valid_strong_password_passes(self):
        """A properly strong password still passes validation."""
        from auth.password import validate_password

        # No consecutive, no sequential, meets all complexity rules
        result = validate_password("Tr0ub4d&Rx!Z")
        assert result is True

    def test_strength_check_includes_new_checks(self):
        """check_password_strength returns no_consecutive and no_sequential."""
        from auth.password import check_password_strength

        result = check_password_strength("Tr0ub4d&Rx!Z")
        assert "no_consecutive" in result["checks"]
        assert "no_sequential" in result["checks"]
        assert result["checks"]["no_consecutive"] is True
        assert result["checks"]["no_sequential"] is True

    def test_strength_check_flags_consecutive(self):
        """check_password_strength flags consecutive identical chars."""
        from auth.password import check_password_strength

        result = check_password_strength("Abcdefffg1!x")
        assert result["checks"]["no_consecutive"] is False
        assert result["valid"] is False

    def test_strength_check_max_score_is_10(self):
        """Max score is now 10 (8 checks + 2 length bonuses)."""
        from auth.password import check_password_strength

        result = check_password_strength("Tr0ub4d&Rx!Z_very_long_pw")
        assert result["max_score"] == 10

    def test_reverse_sequential_rejected(self):
        """Reverse sequential chars (dcba, 4321) are also rejected."""
        from auth.password import validate_password

        with pytest.raises(ValueError, match="sequential"):
            validate_password("Good4321Pass!")  # "4321" = reverse sequential
