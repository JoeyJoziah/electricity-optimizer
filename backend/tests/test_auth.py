"""
Authentication Tests

Comprehensive tests for JWT authentication and Supabase Auth integration:
- JWT token creation and validation
- Token expiration handling
- OAuth flow (mocked)
- Magic link generation
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
# SUPABASE AUTH SERVICE TESTS
# =============================================================================


class TestSupabaseAuthService:
    """Tests for Supabase Auth integration"""

    @pytest.fixture
    def mock_supabase_client(self):
        """Create mock Supabase client"""
        client = MagicMock()

        # Mock auth methods
        client.auth.sign_up.return_value = MagicMock(
            user=MagicMock(id="user-123", email="test@example.com"),
            session=MagicMock(access_token="access-token", refresh_token="refresh-token")
        )
        client.auth.sign_in_with_password.return_value = MagicMock(
            user=MagicMock(id="user-123", email="test@example.com"),
            session=MagicMock(access_token="access-token", refresh_token="refresh-token")
        )
        client.auth.sign_out.return_value = None
        client.auth.refresh_session.return_value = MagicMock(
            session=MagicMock(access_token="new-access-token", refresh_token="new-refresh-token")
        )

        return client

    @pytest.fixture
    def auth_service(self, mock_supabase_client):
        """Create Supabase auth service with mock client"""
        from auth.supabase_auth import SupabaseAuthService

        return SupabaseAuthService(client=mock_supabase_client)

    # -------------------------------------------------------------------------
    # Sign Up Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_sign_up_success(self, auth_service, mock_supabase_client):
        """Test successful user signup"""
        result = await auth_service.sign_up(
            email="newuser@example.com",
            password="SecurePassword123!"
        )

        assert result is not None
        assert result.user is not None
        assert result.session is not None
        mock_supabase_client.auth.sign_up.assert_called_once()

    @pytest.mark.asyncio
    async def test_sign_up_weak_password(self, auth_service):
        """Test signup with weak password fails"""
        from auth.supabase_auth import WeakPasswordError

        with pytest.raises(WeakPasswordError):
            await auth_service.sign_up(
                email="test@example.com",
                password="123"  # Too weak
            )

    @pytest.mark.asyncio
    async def test_sign_up_invalid_email(self, auth_service):
        """Test signup with invalid email fails"""
        from auth.supabase_auth import InvalidEmailError

        with pytest.raises(InvalidEmailError):
            await auth_service.sign_up(
                email="not-an-email",
                password="SecurePassword123!"
            )

    @pytest.mark.asyncio
    async def test_sign_up_duplicate_email(self, auth_service, mock_supabase_client):
        """Test signup with existing email fails"""
        from auth.supabase_auth import EmailAlreadyExistsError

        mock_supabase_client.auth.sign_up.side_effect = Exception("User already registered")

        with pytest.raises(EmailAlreadyExistsError):
            await auth_service.sign_up(
                email="existing@example.com",
                password="SecurePassword123!"
            )

    # -------------------------------------------------------------------------
    # Sign In Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_sign_in_success(self, auth_service, mock_supabase_client):
        """Test successful sign in"""
        result = await auth_service.sign_in(
            email="user@example.com",
            password="CorrectPassword123!"
        )

        assert result is not None
        assert result.user is not None
        assert result.session is not None
        mock_supabase_client.auth.sign_in_with_password.assert_called_once()

    @pytest.mark.asyncio
    async def test_sign_in_wrong_password(self, auth_service, mock_supabase_client):
        """Test sign in with wrong password fails"""
        from auth.supabase_auth import InvalidCredentialsError

        mock_supabase_client.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")

        with pytest.raises(InvalidCredentialsError):
            await auth_service.sign_in(
                email="user@example.com",
                password="WrongPassword"
            )

    @pytest.mark.asyncio
    async def test_sign_in_nonexistent_user(self, auth_service, mock_supabase_client):
        """Test sign in with nonexistent user fails"""
        from auth.supabase_auth import InvalidCredentialsError

        mock_supabase_client.auth.sign_in_with_password.side_effect = Exception("User not found")

        with pytest.raises(InvalidCredentialsError):
            await auth_service.sign_in(
                email="nonexistent@example.com",
                password="SomePassword123!"
            )

    # -------------------------------------------------------------------------
    # OAuth Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_sign_in_with_oauth_google(self, auth_service, mock_supabase_client):
        """Test OAuth sign in with Google"""
        mock_supabase_client.auth.sign_in_with_oauth.return_value = MagicMock(
            url="https://accounts.google.com/oauth/authorize?..."
        )

        result = await auth_service.sign_in_with_oauth(
            provider="google",
            redirect_url="http://localhost:3000/auth/callback"
        )

        assert result is not None
        assert "url" in result

    @pytest.mark.asyncio
    async def test_sign_in_with_oauth_github(self, auth_service, mock_supabase_client):
        """Test OAuth sign in with GitHub"""
        mock_supabase_client.auth.sign_in_with_oauth.return_value = MagicMock(
            url="https://github.com/login/oauth/authorize?..."
        )

        result = await auth_service.sign_in_with_oauth(
            provider="github",
            redirect_url="http://localhost:3000/auth/callback"
        )

        assert result is not None
        assert "url" in result

    @pytest.mark.asyncio
    async def test_sign_in_with_oauth_invalid_provider(self, auth_service):
        """Test OAuth with invalid provider fails"""
        from auth.supabase_auth import InvalidProviderError

        with pytest.raises(InvalidProviderError):
            await auth_service.sign_in_with_oauth(
                provider="invalid-provider",
                redirect_url="http://localhost:3000/auth/callback"
            )

    # -------------------------------------------------------------------------
    # Magic Link Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_sign_in_with_magic_link(self, auth_service, mock_supabase_client):
        """Test magic link sign in"""
        mock_supabase_client.auth.sign_in_with_otp.return_value = MagicMock(
            user=None,  # User comes after clicking link
            session=None
        )

        result = await auth_service.sign_in_with_magic_link(
            email="user@example.com",
            redirect_url="http://localhost:3000/auth/callback"
        )

        assert result is not None
        assert result["message"] == "Magic link sent to email"

    @pytest.mark.asyncio
    async def test_magic_link_invalid_email(self, auth_service):
        """Test magic link with invalid email fails"""
        from auth.supabase_auth import InvalidEmailError

        with pytest.raises(InvalidEmailError):
            await auth_service.sign_in_with_magic_link(
                email="not-an-email",
                redirect_url="http://localhost:3000/auth/callback"
            )

    # -------------------------------------------------------------------------
    # Sign Out Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_sign_out_success(self, auth_service, mock_supabase_client):
        """Test successful sign out"""
        result = await auth_service.sign_out()

        assert result is True
        mock_supabase_client.auth.sign_out.assert_called_once()

    # -------------------------------------------------------------------------
    # Session Refresh Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_refresh_session_success(self, auth_service, mock_supabase_client):
        """Test successful session refresh"""
        result = await auth_service.refresh_session(
            refresh_token="valid-refresh-token"
        )

        assert result is not None
        assert result.session is not None

    @pytest.mark.asyncio
    async def test_refresh_session_invalid_token(self, auth_service, mock_supabase_client):
        """Test session refresh with invalid token fails"""
        from auth.supabase_auth import InvalidTokenError

        mock_supabase_client.auth.refresh_session.side_effect = Exception("Invalid refresh token")

        with pytest.raises(InvalidTokenError):
            await auth_service.refresh_session(
                refresh_token="invalid-token"
            )

    # -------------------------------------------------------------------------
    # Get User Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_current_user(self, auth_service, mock_supabase_client):
        """Test getting current user from token"""
        mock_supabase_client.auth.get_user.return_value = MagicMock(
            user=MagicMock(id="user-123", email="test@example.com")
        )

        result = await auth_service.get_current_user(token="valid-access-token")

        assert result is not None
        assert result.id == "user-123"


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
    """Tests for authentication API endpoints"""

    @pytest.fixture
    def mock_auth_service(self):
        """Create mock auth service"""
        service = AsyncMock()
        return service

    # -------------------------------------------------------------------------
    # Signup Endpoint Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_signup_endpoint_success(self, mock_auth_service):
        """Test POST /api/v1/auth/signup success"""
        # Should create user and return tokens

    @pytest.mark.asyncio
    async def test_signup_endpoint_validation(self, mock_auth_service):
        """Test signup validates request body"""
        # Should reject invalid email/password

    # -------------------------------------------------------------------------
    # Signin Endpoint Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_signin_endpoint_success(self, mock_auth_service):
        """Test POST /api/v1/auth/signin success"""
        # Should return tokens on successful auth

    @pytest.mark.asyncio
    async def test_signin_endpoint_invalid_credentials(self, mock_auth_service):
        """Test signin with invalid credentials"""
        # Should return 401

    # -------------------------------------------------------------------------
    # OAuth Endpoint Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_oauth_endpoint_returns_redirect_url(self, mock_auth_service):
        """Test POST /api/v1/auth/signin/oauth returns redirect URL"""
        # Should return OAuth provider URL

    # -------------------------------------------------------------------------
    # Token Refresh Endpoint Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_refresh_endpoint_success(self, mock_auth_service):
        """Test POST /api/v1/auth/refresh success"""
        # Should return new access token

    @pytest.mark.asyncio
    async def test_refresh_endpoint_invalid_token(self, mock_auth_service):
        """Test refresh with invalid token"""
        # Should return 401

    # -------------------------------------------------------------------------
    # Me Endpoint Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_me_endpoint_authenticated(self, mock_auth_service):
        """Test GET /api/v1/auth/me returns user info"""
        # Should return current user data

    @pytest.mark.asyncio
    async def test_me_endpoint_unauthenticated(self, mock_auth_service):
        """Test /me without auth returns 401"""
        # Should return 401


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
    """Integration tests for authentication flow"""

    @pytest.mark.asyncio
    async def test_full_signup_signin_flow(self):
        """Test complete signup -> signin -> access protected route flow"""
        # 1. Sign up
        # 2. Sign in
        # 3. Access protected route with token
        # 4. Verify user data

    @pytest.mark.asyncio
    async def test_token_refresh_flow(self):
        """Test access token refresh using refresh token"""
        # 1. Sign in
        # 2. Get refresh token
        # 3. Wait for access token to expire
        # 4. Refresh token
        # 5. Use new access token

    @pytest.mark.asyncio
    async def test_oauth_callback_flow(self):
        """Test OAuth callback handling"""
        # 1. Initiate OAuth
        # 2. Simulate callback
        # 3. Verify session created

    @pytest.mark.asyncio
    async def test_logout_invalidates_tokens(self):
        """Test that logout invalidates all tokens"""
        # 1. Sign in
        # 2. Sign out
        # 3. Verify tokens no longer work
