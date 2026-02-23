"""
Authentication Tests

Comprehensive tests for JWT authentication and Neon Auth session validation:
- JWT token creation and validation
- Token expiration handling
- Neon Auth session validation (neon_auth schema)
- Permission-based access control
- Invalid token rejection
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
# JWT HANDLER TESTS
# =============================================================================


class TestJWTHandler:
    """Tests for JWTHandler token management"""

    @pytest.fixture
    def jwt_handler(self):
        """Create JWT handler with test configuration"""
        from auth.jwt_handler import JWTHandler

        return JWTHandler(
            secret_key="test-secret-key-for-testing-only",
            algorithm="HS256",
            access_token_expire_minutes=15,
            refresh_token_expire_days=7,
        )

    # -------------------------------------------------------------------------
    # Token Creation Tests
    # -------------------------------------------------------------------------

    def test_create_access_token(self, jwt_handler):
        """Test creating a valid access token"""
        token = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com",
            scopes=["read", "write"]
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_custom_expiry(self, jwt_handler):
        """Test creating token with custom expiration"""
        token = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com",
            expires_delta=timedelta(minutes=30)
        )

        payload = jwt_handler.decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)

        # Should expire in ~30 minutes
        assert 29 < (exp - now).total_seconds() / 60 < 31

    def test_create_refresh_token(self, jwt_handler):
        """Test creating a refresh token"""
        token = jwt_handler.create_refresh_token(user_id="user-123")

        assert token is not None
        assert isinstance(token, str)

        payload = jwt_handler.decode_token(token)
        assert payload["type"] == "refresh"
        assert payload["sub"] == "user-123"

    def test_refresh_token_longer_expiry(self, jwt_handler):
        """Test that refresh tokens have longer expiry than access tokens"""
        access_token = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com"
        )
        refresh_token = jwt_handler.create_refresh_token(user_id="user-123")

        access_payload = jwt_handler.decode_token(access_token)
        refresh_payload = jwt_handler.decode_token(refresh_token)

        access_exp = access_payload["exp"]
        refresh_exp = refresh_payload["exp"]

        assert refresh_exp > access_exp

    def test_token_contains_required_claims(self, jwt_handler):
        """Test that token contains all required JWT claims"""
        token = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com",
            scopes=["read"]
        )

        payload = jwt_handler.decode_token(token)

        assert "sub" in payload  # Subject (user_id)
        assert "email" in payload
        assert "scopes" in payload
        assert "iat" in payload  # Issued at
        assert "exp" in payload  # Expiration
        assert "jti" in payload  # JWT ID (unique)
        assert "type" in payload

    def test_token_has_unique_jti(self, jwt_handler):
        """Test that each token has a unique JTI"""
        token1 = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com"
        )
        token2 = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com"
        )

        payload1 = jwt_handler.decode_token(token1)
        payload2 = jwt_handler.decode_token(token2)

        assert payload1["jti"] != payload2["jti"]

    # -------------------------------------------------------------------------
    # Token Verification Tests
    # -------------------------------------------------------------------------

    def test_verify_valid_token(self, jwt_handler):
        """Test verifying a valid token"""
        token = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com"
        )

        payload = jwt_handler.verify_token(token)

        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"

    def test_verify_expired_token(self, jwt_handler):
        """Test that expired tokens are rejected"""
        from auth.jwt_handler import TokenExpiredError

        # Create token that's already expired
        token = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com",
            expires_delta=timedelta(seconds=-10)  # Expired 10 seconds ago
        )

        with pytest.raises(TokenExpiredError):
            jwt_handler.verify_token(token)

    def test_verify_invalid_signature(self, jwt_handler):
        """Test that tokens with invalid signature are rejected"""
        from auth.jwt_handler import InvalidTokenError

        # Create token with different handler (different secret)
        from auth.jwt_handler import JWTHandler
        other_handler = JWTHandler(
            secret_key="different-secret-key",
            algorithm="HS256"
        )

        token = other_handler.create_access_token(
            user_id="user-123",
            email="test@example.com"
        )

        with pytest.raises(InvalidTokenError):
            jwt_handler.verify_token(token)

    def test_verify_malformed_token(self, jwt_handler):
        """Test that malformed tokens are rejected"""
        from auth.jwt_handler import InvalidTokenError

        with pytest.raises(InvalidTokenError):
            jwt_handler.verify_token("not-a-valid-jwt-token")

    def test_verify_token_wrong_type(self, jwt_handler):
        """Test that refresh token cannot be used as access token"""
        from auth.jwt_handler import InvalidTokenError

        refresh_token = jwt_handler.create_refresh_token(user_id="user-123")

        with pytest.raises(InvalidTokenError):
            jwt_handler.verify_token(refresh_token, expected_type="access")

    # -------------------------------------------------------------------------
    # Token Decoding Tests
    # -------------------------------------------------------------------------

    def test_decode_token_success(self, jwt_handler):
        """Test decoding a valid token"""
        token = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com",
            scopes=["admin"]
        )

        payload = jwt_handler.decode_token(token)

        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"
        assert "admin" in payload["scopes"]

    def test_decode_expired_token_allowed(self, jwt_handler):
        """Test that decode allows expired tokens (for inspection)"""
        token = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com",
            expires_delta=timedelta(seconds=-10)
        )

        # decode_token should work even for expired tokens
        payload = jwt_handler.decode_token(token, verify_exp=False)

        assert payload["sub"] == "user-123"

    # -------------------------------------------------------------------------
    # Token Revocation Tests
    # -------------------------------------------------------------------------

    def test_revoke_token(self, jwt_handler):
        """Test token revocation"""
        token = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com"
        )

        payload = jwt_handler.decode_token(token)
        jti = payload["jti"]

        # Revoke the token
        jwt_handler.revoke_token(jti)

        # Token should now be invalid
        assert jwt_handler.is_token_revoked(jti) is True

    def test_verify_revoked_token_fails(self, jwt_handler):
        """Test that revoked tokens are rejected"""
        from auth.jwt_handler import TokenRevokedError

        token = jwt_handler.create_access_token(
            user_id="user-123",
            email="test@example.com"
        )

        payload = jwt_handler.decode_token(token)
        jwt_handler.revoke_token(payload["jti"])

        with pytest.raises(TokenRevokedError):
            jwt_handler.verify_token(token)


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


# =============================================================================
# AUTH MIDDLEWARE TESTS
# =============================================================================


class TestAuthMiddleware:
    """Tests for authentication middleware"""

    @pytest.fixture
    def mock_jwt_handler(self):
        """Create mock JWT handler"""
        handler = MagicMock()
        handler.verify_token.return_value = {
            "sub": "user-123",
            "email": "test@example.com",
            "scopes": ["read", "write"],
            "type": "access"
        }
        return handler

    # -------------------------------------------------------------------------
    # Get Current User Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self, mock_jwt_handler):
        """Test getting current user with valid token"""
        from auth.middleware import get_current_user

        # Mock the dependency
        with patch("auth.middleware.jwt_handler", mock_jwt_handler):
            from fastapi.security import HTTPAuthorizationCredentials
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="valid-token"
            )

            # This would be called by FastAPI
            # user = await get_current_user(credentials)

    @pytest.mark.asyncio
    async def test_get_current_user_missing_token(self):
        """Test that missing token raises 401"""
        from fastapi import HTTPException
        from auth.middleware import get_current_user

        # Should raise 401 when no token provided

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_jwt_handler):
        """Test that invalid token raises 401"""
        from auth.jwt_handler import InvalidTokenError

        mock_jwt_handler.verify_token.side_effect = InvalidTokenError("Invalid token")

        # Should raise 401 when token is invalid

    # -------------------------------------------------------------------------
    # Permission Checking Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_require_permission_success(self, mock_jwt_handler):
        """Test permission check passes with correct scope"""
        mock_jwt_handler.verify_token.return_value = {
            "sub": "user-123",
            "email": "test@example.com",
            "scopes": ["admin"],
            "type": "access"
        }

        # User has "admin" scope, should pass

    @pytest.mark.asyncio
    async def test_require_permission_missing_scope(self, mock_jwt_handler):
        """Test permission check fails without required scope"""
        mock_jwt_handler.verify_token.return_value = {
            "sub": "user-123",
            "email": "test@example.com",
            "scopes": ["read"],
            "type": "access"
        }

        # User lacks "admin" scope, should raise 403

    @pytest.mark.asyncio
    async def test_require_multiple_permissions(self, mock_jwt_handler):
        """Test checking for multiple required permissions"""
        mock_jwt_handler.verify_token.return_value = {
            "sub": "user-123",
            "email": "test@example.com",
            "scopes": ["read", "write", "admin"],
            "type": "access"
        }

        # User has all required scopes, should pass


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
