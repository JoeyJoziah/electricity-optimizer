"""
Authentication API Endpoints

Provides user authentication endpoints:
- POST /signup: Create new account
- POST /signin: Sign in with email/password
- POST /signin/oauth: Initiate OAuth flow
- POST /signin/magic-link: Send magic link
- POST /signout: Sign out
- POST /refresh: Refresh access token
- GET /me: Get current user info
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

import structlog

from auth.jwt_handler import jwt_handler
from auth.supabase_auth import (
    SupabaseAuthService,
    InvalidCredentialsError,
    InvalidEmailError,
    WeakPasswordError,
    EmailAlreadyExistsError,
    InvalidProviderError,
    InvalidTokenError as AuthInvalidTokenError,
)
from auth.middleware import get_current_user, TokenData
from auth.password import validate_password, check_password_strength


logger = structlog.get_logger()


router = APIRouter()


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class SignUpRequest(BaseModel):
    """Request for user signup"""
    email: EmailStr
    password: str = Field(..., min_length=12)
    name: Optional[str] = None


class SignInRequest(BaseModel):
    """Request for user signin"""
    email: EmailStr
    password: str


class OAuthRequest(BaseModel):
    """Request for OAuth signin"""
    provider: str
    redirect_url: str
    scopes: Optional[str] = None


class MagicLinkRequest(BaseModel):
    """Request for magic link signin"""
    email: EmailStr
    redirect_url: str


class RefreshRequest(BaseModel):
    """Request for token refresh"""
    refresh_token: str


class TokenResponse(BaseModel):
    """Response containing tokens"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class OAuthResponse(BaseModel):
    """Response for OAuth initiation"""
    url: str


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str


class UserResponse(BaseModel):
    """Response with user data"""
    id: str
    email: str
    name: Optional[str] = None
    email_verified: bool = False
    created_at: Optional[str] = None


class PasswordStrengthResponse(BaseModel):
    """Response for password strength check"""
    score: int
    max_score: int
    strength: str
    valid: bool
    checks: dict


# =============================================================================
# DEPENDENCIES
# =============================================================================


def get_auth_service():
    """Get Supabase auth service instance"""
    return SupabaseAuthService()


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new account",
    description="Register a new user with email and password"
)
async def signup(
    request: Request,
    signup_request: SignUpRequest,
    auth_service: SupabaseAuthService = Depends(get_auth_service),
):
    """
    Create a new user account.

    Password must meet security requirements:
    - At least 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    """
    logger.info("signup_attempt", email=signup_request.email)

    try:
        # Validate password first
        validate_password(signup_request.password)

        # Create user via Supabase
        result = await auth_service.sign_up(
            email=signup_request.email,
            password=signup_request.password,
            user_metadata={"name": signup_request.name} if signup_request.name else None,
        )

        if result.session is None:
            # User created but needs email verification
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail="Account created. Please check your email to verify.",
            )

        logger.info("signup_success", user_id=result.user.id if result.user else None)

        return TokenResponse(
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
            token_type="bearer",
            expires_in=result.session.expires_in,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except WeakPasswordError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except InvalidEmailError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except EmailAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )


@router.post(
    "/signin",
    response_model=TokenResponse,
    summary="Sign in",
    description="Sign in with email and password"
)
async def signin(
    request: Request,
    response: Response,
    signin_request: SignInRequest,
    auth_service: SupabaseAuthService = Depends(get_auth_service),
):
    """
    Sign in with email and password.

    Returns access and refresh tokens on success.
    """
    logger.info("signin_attempt", email=signin_request.email)

    try:
        result = await auth_service.sign_in(
            email=signin_request.email,
            password=signin_request.password,
        )

        logger.info("signin_success", user_id=result.user.id if result.user else None)

        # Set refresh token as HTTP-only cookie (more secure)
        response.set_cookie(
            key="refresh_token",
            value=result.session.refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,  # 7 days
        )

        return TokenResponse(
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
            token_type="bearer",
            expires_in=result.session.expires_in,
        )

    except InvalidCredentialsError:
        logger.warning("signin_failed", email=signin_request.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )


@router.post(
    "/signin/oauth",
    response_model=OAuthResponse,
    summary="Initiate OAuth",
    description="Start OAuth authentication flow"
)
async def signin_oauth(
    oauth_request: OAuthRequest,
    auth_service: SupabaseAuthService = Depends(get_auth_service),
):
    """
    Initiate OAuth authentication flow.

    Supported providers: google, github, apple, azure, discord

    Returns URL to redirect user to for OAuth authorization.
    """
    logger.info("oauth_attempt", provider=oauth_request.provider)

    try:
        result = await auth_service.sign_in_with_oauth(
            provider=oauth_request.provider,
            redirect_url=oauth_request.redirect_url,
            scopes=oauth_request.scopes,
        )

        return OAuthResponse(url=result["url"])

    except InvalidProviderError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/signin/magic-link",
    response_model=MessageResponse,
    summary="Send magic link",
    description="Send passwordless sign-in link to email"
)
async def signin_magic_link(
    magic_request: MagicLinkRequest,
    auth_service: SupabaseAuthService = Depends(get_auth_service),
):
    """
    Send magic link for passwordless authentication.

    User will receive an email with a sign-in link.
    """
    logger.info("magic_link_attempt", email=magic_request.email)

    try:
        result = await auth_service.sign_in_with_magic_link(
            email=magic_request.email,
            redirect_url=magic_request.redirect_url,
        )

        return MessageResponse(message=result["message"])

    except InvalidEmailError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/signout",
    response_model=MessageResponse,
    summary="Sign out",
    description="Sign out and invalidate session"
)
async def signout(
    response: Response,
    current_user: TokenData = Depends(get_current_user),
    auth_service: SupabaseAuthService = Depends(get_auth_service),
):
    """
    Sign out and invalidate current session.

    Clears the refresh token cookie and revokes tokens.
    """
    logger.info("signout_attempt", user_id=current_user.user_id)

    try:
        await auth_service.sign_out()

        # Clear refresh token cookie
        response.delete_cookie("refresh_token")

        logger.info("signout_success", user_id=current_user.user_id)

        return MessageResponse(message="Successfully signed out")

    except Exception as e:
        logger.error("signout_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sign out",
        )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh token",
    description="Get new access token using refresh token"
)
async def refresh_token(
    request: Request,
    response: Response,
    refresh_request: Optional[RefreshRequest] = None,
    auth_service: SupabaseAuthService = Depends(get_auth_service),
):
    """
    Refresh access token using refresh token.

    Refresh token can be provided in request body or from HTTP-only cookie.
    """
    # Try to get refresh token from request body or cookie
    refresh_token = None
    if refresh_request and refresh_request.refresh_token:
        refresh_token = refresh_request.refresh_token
    else:
        refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token required",
        )

    logger.info("token_refresh_attempt")

    try:
        result = await auth_service.refresh_session(refresh_token)

        # Update refresh token cookie
        response.set_cookie(
            key="refresh_token",
            value=result.session.refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
        )

        logger.info("token_refresh_success")

        return TokenResponse(
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
            token_type="bearer",
            expires_in=result.session.expires_in,
        )

    except AuthInvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get authenticated user information"
)
async def get_me(
    current_user: TokenData = Depends(get_current_user),
    auth_service: SupabaseAuthService = Depends(get_auth_service),
):
    """
    Get current authenticated user information.

    Requires valid access token.
    """
    logger.info("get_user_info", user_id=current_user.user_id)

    return UserResponse(
        id=current_user.user_id,
        email=current_user.email or "",
        email_verified=True,  # If token is valid, email is verified
    )


@router.post(
    "/password/check-strength",
    response_model=PasswordStrengthResponse,
    summary="Check password strength",
    description="Check if password meets security requirements"
)
async def check_password(password: str):
    """
    Check password strength without creating account.

    Returns detailed assessment of password security.
    """
    result = check_password_strength(password)
    return PasswordStrengthResponse(**result)
