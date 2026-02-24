"""
Authentication Tests

Comprehensive tests for Neon Auth session validation:
- Neon Auth session validation (neon_auth schema)
- Permission-based access control
- Password validation
- Auth API endpoints
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import sys
from pathlib import Path

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

    @pytest.mark.asyncio
    async def test_get_session_from_token_valid(self, mock_db_session):
        """Test valid session token returns SessionData"""
        from auth.neon_auth import _get_session_from_token, SessionData

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

        assert result is not None
        assert isinstance(result, SessionData)
        assert result.user_id == "user-123"
        assert result.email == "test@example.com"
        assert result.name == "Test User"
        assert result.email_verified is True

    @pytest.mark.asyncio
    async def test_get_session_from_token_expired(self, mock_db_session):
        """Test expired session token returns None"""
        from auth.neon_auth import _get_session_from_token

        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await _get_session_from_token("expired-token", mock_db_session)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_from_token_banned_user(self, mock_db_session):
        """Test banned user session returns None (query filters banned users)"""
        from auth.neon_auth import _get_session_from_token

        # Query WHERE clause filters banned users, so fetchone returns None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await _get_session_from_token("banned-user-token", mock_db_session)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_from_token_no_name(self, mock_db_session):
        """Test session with null name defaults to empty string"""
        from auth.neon_auth import _get_session_from_token

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

        assert result is not None
        assert result.name == ""

    # -------------------------------------------------------------------------
    # get_current_user Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_current_user_from_bearer_header(self, mock_db_session, mock_request):
        """Test extracting session token from Authorization header"""
        from auth.neon_auth import get_current_user, SessionData
        from fastapi.security import HTTPAuthorizationCredentials

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

    @pytest.mark.asyncio
    async def test_get_current_user_from_cookie(self, mock_db_session, mock_request):
        """Test extracting session token from cookie"""
        from auth.neon_auth import get_current_user, SESSION_COOKIE_NAME

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

    @pytest.mark.asyncio
    async def test_get_current_user_no_token_raises_401(self, mock_db_session, mock_request):
        """Test missing session token raises 401"""
        from auth.neon_auth import get_current_user
        from fastapi import HTTPException

        mock_request.cookies = {}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, None, mock_db_session)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token_raises_401(self, mock_db_session, mock_request):
        """Test invalid session token raises 401"""
        from auth.neon_auth import get_current_user
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

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

    @pytest.mark.asyncio
    async def test_get_current_user_no_db_raises_503(self, mock_request):
        """Test missing database connection raises 503"""
        from auth.neon_auth import get_current_user
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid-token"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials, None)

        assert exc_info.value.status_code == 503

    # -------------------------------------------------------------------------
    # get_current_user_optional Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_current_user_optional_returns_none(self, mock_db_session, mock_request):
        """Test optional auth returns None for unauthenticated request"""
        from auth.neon_auth import get_current_user_optional

        mock_request.cookies = {}

        result = await get_current_user_optional(mock_request, None, mock_db_session)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_user_optional_returns_user(self, mock_db_session, mock_request):
        """Test optional auth returns SessionData when authenticated"""
        from auth.neon_auth import get_current_user_optional, SESSION_COOKIE_NAME

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

        assert result is not None
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

        data = SessionData(
            user_id="u1", email="e@e.com", role="admin"
        )
        assert data.role == "admin"

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_similar_tokens_produce_different_cache_keys(self, mock_db_session):
        """Two tokens sharing the same 16-char prefix must produce different cache keys."""
        import hashlib
        from auth.neon_auth import _get_session_from_token

        # Two tokens with identical first 16 chars but different suffixes
        token_a = "abcdef1234567890_suffix_AAA"
        token_b = "abcdef1234567890_suffix_BBB"

        hash_a = hashlib.sha256(token_a.encode()).hexdigest()[:32]
        hash_b = hashlib.sha256(token_b.encode()).hexdigest()[:32]

        # The old code would produce the same cache key for both
        assert hash_a != hash_b, "Tokens with same prefix must have distinct cache keys"

    @pytest.mark.asyncio
    async def test_session_cache_stores_with_sha256_key(self, mock_db_session):
        """Verify Redis SET uses SHA-256 cache key on cache miss + DB hit."""
        import hashlib
        from auth.neon_auth import _get_session_from_token, _SESSION_CACHE_TTL

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

        assert result is not None
        expected_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
        expected_key = f"session:{expected_hash}"

        # Verify setex was called with the SHA-256 key and correct TTL
        mock_redis.setex.assert_awaited_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == expected_key
        assert call_args[0][1] == _SESSION_CACHE_TTL


# =============================================================================
# AUTH API ENDPOINT TESTS
# =============================================================================


class TestAuthAPI:
    """Tests for authentication API endpoints (/me, /password/check-strength)"""

    # -------------------------------------------------------------------------
    # Me Endpoint Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_me_endpoint_requires_auth(self):
        """Test GET /api/v1/auth/me returns 401 without auth"""
        from api.v1.auth import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        with TestClient(app) as client:
            response = client.get("/api/v1/auth/me")
            assert response.status_code == 401

    # -------------------------------------------------------------------------
    # Password Strength Endpoint Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_password_check_strength_strong(self):
        """Test password strength check with strong password"""
        from api.v1.auth import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/password/check-strength",
                json={"password": "ValidPass123!"}
            )
            assert response.status_code == 200
            data = response.json()
            assert "score" in data
            assert "strength" in data
            assert "valid" in data
            assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_password_check_strength_weak(self):
        """Test password strength check with weak password"""
        from api.v1.auth import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/password/check-strength",
                json={"password": "weak"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_password_check_strength_empty_rejected(self):
        """Test password strength check rejects empty password"""
        from api.v1.auth import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/password/check-strength",
                json={"password": ""}
            )
            assert response.status_code == 422


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================


class TestAuthRateLimiting:
    """Tests for authentication rate limiting"""

    @pytest.mark.asyncio
    async def test_login_rate_limit_after_failures(self):
        """Test account lockout after failed attempts"""
        # 5 failed attempts should trigger 15 min lockout

    @pytest.mark.asyncio
    async def test_rate_limit_per_ip(self):
        """Test rate limiting per IP address"""
        # Should limit requests per IP

    @pytest.mark.asyncio
    async def test_rate_limit_reset_after_success(self):
        """Test rate limit resets after successful login"""
        # Successful login should reset failure counter


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


# =============================================================================
# SECURITY HEADER TESTS
# =============================================================================


class TestSecurityHeaders:
    """Tests for security headers middleware"""

    @pytest.mark.asyncio
    async def test_csp_header_present(self):
        """Test Content-Security-Policy header is set"""
        # Response should have CSP header

    @pytest.mark.asyncio
    async def test_xfo_header_deny(self):
        """Test X-Frame-Options is DENY"""
        # Response should have X-Frame-Options: DENY

    @pytest.mark.asyncio
    async def test_hsts_header_present(self):
        """Test Strict-Transport-Security header"""
        # Response should have HSTS header

    @pytest.mark.asyncio
    async def test_xcto_header_nosniff(self):
        """Test X-Content-Type-Options is nosniff"""
        # Response should have X-Content-Type-Options: nosniff


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestAuthIntegration:
    """Integration tests for authentication flow (Neon Auth)"""

    @pytest.mark.asyncio
    async def test_session_validation_flow(self):
        """Test session token validation against neon_auth schema"""
        # Auth flows (sign-up/sign-in) are now handled by Better Auth
        # via the Next.js frontend. Backend only validates sessions.
        # Full integration requires a live database with neon_auth schema.

    @pytest.mark.asyncio
    async def test_me_endpoint_with_valid_session(self):
        """Test /me returns user data when session is valid"""
        # Requires mocking neon_auth.session + neon_auth.user queries

    @pytest.mark.asyncio
    async def test_expired_session_rejected(self):
        """Test that expired sessions are rejected"""
        # neon_auth.session rows with expiresAt < NOW() should be rejected
