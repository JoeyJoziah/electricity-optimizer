"""
Supabase Auth Service

Integrates with Supabase Auth for user authentication including:
- Email/password signup and signin
- OAuth providers (Google, GitHub)
- Magic link (passwordless) authentication
- Session management
"""

import re
from typing import Optional, Dict, Any
from dataclasses import dataclass

from supabase import Client
import structlog

from config.settings import settings
from config.database import db_manager
from auth.password import validate_password


logger = structlog.get_logger()


# =============================================================================
# EXCEPTIONS
# =============================================================================


class AuthError(Exception):
    """Base exception for authentication errors"""
    pass


class InvalidCredentialsError(AuthError):
    """Raised when credentials are invalid"""
    pass


class InvalidEmailError(AuthError):
    """Raised when email format is invalid"""
    pass


class WeakPasswordError(AuthError):
    """Raised when password doesn't meet requirements"""
    pass


class EmailAlreadyExistsError(AuthError):
    """Raised when email is already registered"""
    pass


class InvalidProviderError(AuthError):
    """Raised when OAuth provider is not supported"""
    pass


class InvalidTokenError(AuthError):
    """Raised when token is invalid"""
    pass


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class AuthUser:
    """Authenticated user data"""
    id: str
    email: str
    email_verified: bool = False
    phone: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    app_metadata: Optional[Dict[str, Any]] = None
    user_metadata: Optional[Dict[str, Any]] = None


@dataclass
class AuthSession:
    """Authentication session data"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    expires_at: Optional[int] = None


@dataclass
class AuthResult:
    """Result of authentication operation"""
    user: Optional[AuthUser]
    session: Optional[AuthSession]


# =============================================================================
# SUPABASE AUTH SERVICE
# =============================================================================


class SupabaseAuthService:
    """
    Supabase Auth integration service.

    Provides authentication operations using Supabase Auth backend.
    """

    # Supported OAuth providers
    SUPPORTED_PROVIDERS = {"google", "github", "apple", "azure", "discord"}

    def __init__(self, client: Optional[Client] = None):
        """
        Initialize Supabase Auth service.

        Args:
            client: Supabase client (uses db_manager if not provided)
        """
        self._client = client

    @property
    def client(self) -> Client:
        """Get Supabase client"""
        if self._client:
            return self._client
        return db_manager.get_supabase_client()

    async def sign_up(
        self,
        email: str,
        password: str,
        user_metadata: Optional[Dict[str, Any]] = None,
    ) -> AuthResult:
        """
        Register a new user with email and password.

        Args:
            email: User's email address
            password: User's password (must meet requirements)
            user_metadata: Optional user metadata

        Returns:
            AuthResult with user and session

        Raises:
            InvalidEmailError: If email format is invalid
            WeakPasswordError: If password doesn't meet requirements
            EmailAlreadyExistsError: If email is already registered
        """
        # Validate email format
        if not self._is_valid_email(email):
            raise InvalidEmailError(f"Invalid email format: {email}")

        # Validate password strength
        try:
            validate_password(password)
        except ValueError as e:
            raise WeakPasswordError(str(e))

        logger.info("signing_up_user", email=email)

        try:
            result = self.client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": user_metadata or {}
                }
            })

            if result.user is None:
                raise AuthError("Failed to create user")

            logger.info("user_signed_up", user_id=result.user.id)

            return AuthResult(
                user=self._to_auth_user(result.user),
                session=self._to_auth_session(result.session) if result.session else None
            )

        except Exception as e:
            error_msg = str(e).lower()
            if "already registered" in error_msg or "already exists" in error_msg:
                raise EmailAlreadyExistsError(f"Email already registered: {email}")
            logger.error("signup_failed", email=email, error=str(e))
            raise AuthError(f"Signup failed: {str(e)}")

    async def sign_in(
        self,
        email: str,
        password: str,
    ) -> AuthResult:
        """
        Sign in user with email and password.

        Args:
            email: User's email address
            password: User's password

        Returns:
            AuthResult with user and session

        Raises:
            InvalidCredentialsError: If credentials are invalid
        """
        logger.info("signing_in_user", email=email)

        try:
            result = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if result.user is None or result.session is None:
                raise InvalidCredentialsError("Invalid email or password")

            logger.info("user_signed_in", user_id=result.user.id)

            return AuthResult(
                user=self._to_auth_user(result.user),
                session=self._to_auth_session(result.session)
            )

        except Exception as e:
            error_msg = str(e).lower()
            if "invalid" in error_msg or "credentials" in error_msg or "not found" in error_msg:
                raise InvalidCredentialsError("Invalid email or password")
            logger.error("signin_failed", email=email, error=str(e))
            raise AuthError(f"Sign in failed: {str(e)}")

    async def sign_in_with_oauth(
        self,
        provider: str,
        redirect_url: str,
        scopes: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Initiate OAuth sign in flow.

        Args:
            provider: OAuth provider name (google, github, etc.)
            redirect_url: URL to redirect after authentication
            scopes: OAuth scopes to request

        Returns:
            Dict containing the OAuth authorization URL

        Raises:
            InvalidProviderError: If provider is not supported
        """
        provider_lower = provider.lower()
        if provider_lower not in self.SUPPORTED_PROVIDERS:
            raise InvalidProviderError(
                f"Provider '{provider}' not supported. "
                f"Supported: {', '.join(self.SUPPORTED_PROVIDERS)}"
            )

        logger.info("initiating_oauth", provider=provider_lower)

        try:
            result = self.client.auth.sign_in_with_oauth({
                "provider": provider_lower,
                "options": {
                    "redirect_to": redirect_url,
                    "scopes": scopes,
                }
            })

            return {"url": result.url}

        except Exception as e:
            logger.error("oauth_init_failed", provider=provider_lower, error=str(e))
            raise AuthError(f"OAuth initialization failed: {str(e)}")

    async def sign_in_with_magic_link(
        self,
        email: str,
        redirect_url: str,
    ) -> Dict[str, str]:
        """
        Send magic link for passwordless sign in.

        Args:
            email: User's email address
            redirect_url: URL to redirect after clicking link

        Returns:
            Dict containing confirmation message

        Raises:
            InvalidEmailError: If email format is invalid
        """
        if not self._is_valid_email(email):
            raise InvalidEmailError(f"Invalid email format: {email}")

        logger.info("sending_magic_link", email=email)

        try:
            self.client.auth.sign_in_with_otp({
                "email": email,
                "options": {
                    "email_redirect_to": redirect_url,
                }
            })

            return {"message": "Magic link sent to email"}

        except Exception as e:
            logger.error("magic_link_failed", email=email, error=str(e))
            raise AuthError(f"Failed to send magic link: {str(e)}")

    async def sign_out(self) -> bool:
        """
        Sign out the current user.

        Returns:
            True if successful
        """
        logger.info("signing_out_user")

        try:
            self.client.auth.sign_out()
            return True

        except Exception as e:
            logger.error("signout_failed", error=str(e))
            raise AuthError(f"Sign out failed: {str(e)}")

    async def refresh_session(
        self,
        refresh_token: str,
    ) -> AuthResult:
        """
        Refresh authentication session using refresh token.

        Args:
            refresh_token: The refresh token

        Returns:
            AuthResult with new session

        Raises:
            InvalidTokenError: If refresh token is invalid
        """
        logger.info("refreshing_session")

        try:
            result = self.client.auth.refresh_session(refresh_token)

            if result.session is None:
                raise InvalidTokenError("Invalid refresh token")

            logger.info("session_refreshed")

            return AuthResult(
                user=self._to_auth_user(result.user) if result.user else None,
                session=self._to_auth_session(result.session)
            )

        except Exception as e:
            error_msg = str(e).lower()
            if "invalid" in error_msg or "expired" in error_msg:
                raise InvalidTokenError("Invalid or expired refresh token")
            logger.error("session_refresh_failed", error=str(e))
            raise AuthError(f"Session refresh failed: {str(e)}")

    async def get_current_user(
        self,
        token: str,
    ) -> AuthUser:
        """
        Get current user from access token.

        Args:
            token: Access token

        Returns:
            AuthUser data

        Raises:
            InvalidTokenError: If token is invalid
        """
        try:
            result = self.client.auth.get_user(token)

            if result.user is None:
                raise InvalidTokenError("Invalid access token")

            return self._to_auth_user(result.user)

        except Exception as e:
            error_msg = str(e).lower()
            if "invalid" in error_msg or "expired" in error_msg:
                raise InvalidTokenError("Invalid or expired access token")
            raise AuthError(f"Failed to get user: {str(e)}")

    async def verify_otp(
        self,
        email: str,
        token: str,
        token_type: str = "magiclink",
    ) -> AuthResult:
        """
        Verify OTP or magic link token.

        Args:
            email: User's email
            token: OTP or magic link token
            token_type: Type of token (magiclink, email, sms)

        Returns:
            AuthResult with user and session
        """
        try:
            result = self.client.auth.verify_otp({
                "email": email,
                "token": token,
                "type": token_type,
            })

            return AuthResult(
                user=self._to_auth_user(result.user) if result.user else None,
                session=self._to_auth_session(result.session) if result.session else None
            )

        except Exception as e:
            raise InvalidTokenError(f"Invalid OTP: {str(e)}")

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _is_valid_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def _to_auth_user(self, user) -> AuthUser:
        """Convert Supabase user to AuthUser"""
        return AuthUser(
            id=user.id,
            email=user.email,
            email_verified=getattr(user, "email_confirmed_at", None) is not None,
            phone=getattr(user, "phone", None),
            created_at=str(getattr(user, "created_at", None)),
            updated_at=str(getattr(user, "updated_at", None)),
            app_metadata=getattr(user, "app_metadata", None),
            user_metadata=getattr(user, "user_metadata", None),
        )

    def _to_auth_session(self, session) -> AuthSession:
        """Convert Supabase session to AuthSession"""
        return AuthSession(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            token_type=getattr(session, "token_type", "bearer"),
            expires_in=getattr(session, "expires_in", 3600),
            expires_at=getattr(session, "expires_at", None),
        )
