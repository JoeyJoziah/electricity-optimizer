"""
Authentication API Endpoints

Provides user authentication endpoints:
- GET /me: Get current user info (session validated via neon_auth)
- POST /logout: Invalidate session cache (backend-side logout complement)
- POST /password/check-strength: Check password strength (no auth needed)

Note: Sign-up, sign-in, sign-out, OAuth, and magic link flows are now
handled by Better Auth via the Next.js frontend API routes (/api/auth/*).
The backend only validates sessions and serves protected resources.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from auth.neon_auth import (
    get_current_user, SessionData, invalidate_session_cache, SESSION_COOKIE_NAME,
)
from auth.password import check_password_strength
from config.database import get_timescale_session, db_manager


logger = structlog.get_logger()


router = APIRouter()


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class UserResponse(BaseModel):
    """Response with user data"""
    id: str
    email: str
    name: Optional[str] = None
    email_verified: bool = False


class PasswordStrengthRequest(BaseModel):
    """Request for password strength check"""
    password: str = Field(..., min_length=1, max_length=128)


class PasswordStrengthResponse(BaseModel):
    """Response for password strength check"""
    score: int
    max_score: int
    strength: str
    valid: bool
    checks: dict


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get authenticated user information from Neon Auth session"
)
async def get_me(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_timescale_session),
):
    """
    Get current authenticated user information.

    Validates the session token from the cookie or Authorization header
    against the neon_auth.session table, then returns user profile data.
    Also ensures the user has a profile in our application's users table.
    """
    logger.info("get_user_info", user_id=current_user.user_id)

    # Ensure user profile exists in our app's users table (best-effort)
    try:
        from auth.neon_auth import ensure_user_profile
        await ensure_user_profile(
            neon_user_id=current_user.user_id,
            email=current_user.email,
            name=current_user.name,
            db=db,
        )
    except Exception as e:
        logger.warning("user_profile_sync_failed", user_id=current_user.user_id, error=str(e))

    return UserResponse(
        id=current_user.user_id,
        email=current_user.email,
        name=current_user.name or None,
        email_verified=current_user.email_verified,
    )


@router.post(
    "/logout",
    summary="Invalidate session cache",
    description="Clear cached session from Redis so the backend immediately stops accepting it",
)
async def logout(
    request: Request,
    current_user: SessionData = Depends(get_current_user),
):
    """
    Backend complement to Better Auth sign-out.

    Better Auth handles the actual session deletion in neon_auth.session.
    This endpoint clears our Redis session cache so the backend stops
    accepting the token immediately instead of waiting up to 30s.
    """
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        # Fall back to Authorization header (already validated by get_current_user)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_token = auth_header[7:]

    if session_token:
        redis = None
        try:
            redis = await db_manager.get_redis_client()
        except Exception:
            pass
        invalidated = await invalidate_session_cache(session_token, redis)
        logger.info("session_cache_invalidated", user_id=current_user.user_id, cache_hit=invalidated)
    else:
        logger.warning("logout_no_token", user_id=current_user.user_id)

    return {"status": "ok"}


@router.post(
    "/password/check-strength",
    response_model=PasswordStrengthResponse,
    summary="Check password strength",
    description="Check if password meets security requirements"
)
async def check_password(request: PasswordStrengthRequest):
    """
    Check password strength without creating account.

    Returns detailed assessment of password security.
    Password is sent in the request body (never as a query parameter)
    to avoid logging in server access logs and browser history.
    """
    result = check_password_strength(request.password)
    return PasswordStrengthResponse(**result)
