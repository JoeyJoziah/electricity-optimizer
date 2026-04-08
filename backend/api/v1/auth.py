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

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.neon_auth import (
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_NAME_SECURE,
    SessionData,
    get_current_user,
    invalidate_session_cache,
)
from auth.password import check_password_strength
from config.database import db_manager, get_pg_session
from middleware.rate_limiter import UserRateLimiter

logger = structlog.get_logger()

# Strict per-endpoint rate limiter for password check-strength (5 req/min).
# This is an unauthenticated endpoint and must be protected against
# brute-force enumeration beyond the global middleware limits.
_password_check_limiter = UserRateLimiter(
    requests_per_minute=5,
    requests_per_hour=60,
)

# Login brute-force protection: 5 failed attempts per IP in 15 minutes
# triggers a lockout.  This limiter is checked when session validation
# fails (401) on the /me endpoint to prevent credential stuffing attacks.
_login_attempt_limiter = UserRateLimiter(
    login_attempts=5,
    lockout_minutes=15,
)


router = APIRouter(tags=["Authentication"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class UserResponse(BaseModel):
    """Response with user data"""

    id: str
    email: str
    name: str | None = None
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


async def _check_login_lockout(request: Request) -> None:
    """Pre-auth dependency: reject request immediately if IP is locked out.

    This prevents brute-force credential stuffing by blocking further
    attempts once the failure threshold is reached. The lockout counter is
    maintained per-IP in ``_login_attempt_limiter``.
    """
    # Lazily inject Redis for distributed state.
    # Also detach stale Redis if db_manager has been closed (e.g. between test runs).
    redis_client = await db_manager.get_redis_client()
    if _login_attempt_limiter.redis is not None and redis_client is None:
        _login_attempt_limiter.redis = None
    elif _login_attempt_limiter.redis is None and redis_client is not None:
        _login_attempt_limiter.redis = redis_client

    client_ip = request.client.host if request.client else "unknown"
    identifier = f"login:ip:{client_ip}"

    is_locked, seconds_remaining = await _login_attempt_limiter.is_locked_out(identifier)
    if is_locked:
        logger.warning("login_lockout_active", ip=client_ip, seconds_remaining=seconds_remaining)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {seconds_remaining} seconds.",
            headers={"Retry-After": str(seconds_remaining)},
        )


async def _get_current_user_with_brute_force_tracking(
    request: Request,
    db: AsyncSession = Depends(get_pg_session),
) -> SessionData:
    """Wrap ``get_current_user`` to record failed auth attempts per IP.

    On 401 (invalid/expired session), a failure is recorded against the
    client IP.  This feeds into ``_check_login_lockout`` which blocks
    further attempts after 5 failures in 15 minutes.
    """
    from fastapi.security import HTTPAuthorizationCredentials

    # Extract credentials the same way get_current_user would
    credentials: HTTPAuthorizationCredentials | None = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth_header[7:])

    try:
        return await get_current_user(request, credentials, db)
    except HTTPException as exc:
        if exc.status_code == 401:
            client_ip = request.client.host if request.client else "unknown"
            identifier = f"login:ip:{client_ip}"
            await _login_attempt_limiter.record_login_attempt(identifier, success=False)
        raise


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get authenticated user information from Neon Auth session",
    dependencies=[Depends(_check_login_lockout)],
)
async def get_me(
    request: Request,
    current_user: SessionData = Depends(_get_current_user_with_brute_force_tracking),
    db: AsyncSession = Depends(get_pg_session),
):
    """
    Get current authenticated user information.

    Validates the session token from the cookie or Authorization header
    against the neon_auth.session table, then returns user profile data.
    Also ensures the user has a profile in our application's users table.

    Brute-force protection: _check_login_lockout runs BEFORE auth to
    reject locked-out IPs. Successful auth clears the failure counter.
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

    # Record successful auth to clear any prior failed-attempt counter
    client_ip = request.client.host if request.client else "unknown"
    await _login_attempt_limiter.record_login_attempt(f"login:ip:{client_ip}", success=True)

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
    session_token = request.cookies.get(SESSION_COOKIE_NAME) or request.cookies.get(
        SESSION_COOKIE_NAME_SECURE
    )
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
        logger.info(
            "session_cache_invalidated", user_id=current_user.user_id, cache_hit=invalidated
        )
    else:
        logger.warning("logout_no_token", user_id=current_user.user_id)

    return {"status": "ok"}


@router.post(
    "/password/check-strength",
    response_model=PasswordStrengthResponse,
    summary="Check password strength",
    description="Check if password meets security requirements",
)
async def check_password(http_request: Request, request: PasswordStrengthRequest):
    """
    Check password strength without creating account.

    Returns detailed assessment of password security.
    Password is sent in the request body (never as a query parameter)
    to avoid logging in server access logs and browser history.

    Rate limited to 5 requests/minute per IP to prevent brute-force
    enumeration on this unauthenticated endpoint.
    """
    # Lazily inject Redis so the limiter uses distributed state, not in-memory
    if _password_check_limiter.redis is None:
        try:
            _password_check_limiter.redis = await db_manager.get_redis_client()
        except Exception:
            pass  # Falls back to in-memory limiting

    # Per-endpoint rate limit (5/min) — stricter than global middleware
    client_ip = http_request.client.host if http_request.client else "unknown"
    identifier = f"password_check:ip:{client_ip}"
    allowed, remaining = await _password_check_limiter.check_rate_limit(identifier, "minute")
    if not allowed:
        logger.warning(
            "password_check_rate_limited",
            ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": "60"},
        )

    result = check_password_strength(request.password)
    return PasswordStrengthResponse(**result)
