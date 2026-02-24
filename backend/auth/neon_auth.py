"""
Neon Auth Session Validation

Validates user sessions by querying the neon_auth.session and neon_auth.user
tables directly. Sessions are created by Better Auth (via the Next.js frontend)
and validated here for backend API access.

Session tokens arrive via:
1. Cookie: 'better-auth.session_token' (primary — set by Better Auth)
2. Header: 'Authorization: Bearer <session_token>' (API clients)
"""

import hashlib
import json
from typing import Optional
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

import structlog

from config.database import get_timescale_session, db_manager


logger = structlog.get_logger()


# Security scheme — accepts Bearer token but doesn't require it
# (we also check cookies)
security = HTTPBearer(auto_error=False)


SESSION_COOKIE_NAME = "better-auth.session_token"


@dataclass
class SessionData:
    """Authenticated user session data from neon_auth schema."""
    user_id: str
    email: str
    name: str = ""
    email_verified: bool = False
    role: Optional[str] = None


_SESSION_CACHE_TTL = 30  # seconds — kept short to limit access window after logout/ban


async def _get_session_from_token(
    session_token: str,
    db: AsyncSession,
    redis=None,
) -> Optional[SessionData]:
    """
    Query neon_auth.session + neon_auth.user for the given session token.

    Uses Redis as a short-lived cache (120s TTL) to avoid hitting the DB
    on every authenticated request. Returns SessionData if the token is
    valid and not expired, None otherwise.
    """
    cache_key = f"session:{hashlib.sha256(session_token.encode()).hexdigest()[:32]}"

    # Try Redis cache first
    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return SessionData(**data)
        except Exception:
            pass  # Cache miss or error — fall through to DB

    query = text("""
        SELECT
            u.id AS user_id,
            u.email,
            u.name,
            u."emailVerified" AS email_verified,
            u.role
        FROM neon_auth.session s
        JOIN neon_auth."user" u ON s."userId" = u.id
        WHERE s.token = :token
          AND s."expiresAt" > NOW()
          AND (u.banned IS NULL OR u.banned = false)
    """)

    result = await db.execute(query, {"token": session_token})
    row = result.fetchone()

    if row is None:
        return None

    session_data = SessionData(
        user_id=str(row.user_id),
        email=row.email,
        name=row.name or "",
        email_verified=row.email_verified,
        role=row.role,
    )

    # Cache in Redis for subsequent requests
    if redis is not None:
        try:
            await redis.setex(
                cache_key,
                _SESSION_CACHE_TTL,
                json.dumps({
                    "user_id": session_data.user_id,
                    "email": session_data.email,
                    "name": session_data.name,
                    "email_verified": session_data.email_verified,
                    "role": session_data.role,
                }),
            )
        except Exception:
            pass  # Non-fatal — next request will just re-query

    return session_data


async def invalidate_session_cache(session_token: str, redis=None) -> bool:
    """
    Remove a session from Redis cache, forcing re-validation on next request.

    Called on logout to immediately revoke cached access.
    Returns True if a cache entry was deleted, False otherwise.
    """
    if redis is None:
        return False
    cache_key = f"session:{hashlib.sha256(session_token.encode()).hexdigest()[:32]}"
    try:
        deleted = await redis.delete(cache_key)
        return deleted > 0
    except Exception:
        return False


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_timescale_session),
) -> SessionData:
    """
    FastAPI dependency — extracts and validates a Neon Auth session.

    Checks for session token in:
    1. Authorization: Bearer <token> header
    2. 'better-auth.session_token' cookie

    Returns:
        SessionData with user information

    Raises:
        HTTPException 401: If no valid session is found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Extract session token from header or cookie
    session_token: Optional[str] = None

    if credentials and credentials.credentials:
        session_token = credentials.credentials
    else:
        session_token = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_token:
        logger.warning("missing_session_token")
        raise credentials_exception

    if db is None:
        logger.error("database_not_available_for_session_validation")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available",
        )

    # Fetch Redis for session caching
    redis = None
    try:
        redis = await db_manager.get_redis_client()
    except Exception:
        pass

    # Validate session against neon_auth tables
    session_data = await _get_session_from_token(session_token, db, redis)

    if session_data is None:
        logger.warning("invalid_or_expired_session")
        raise credentials_exception

    return session_data


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_timescale_session),
) -> Optional[SessionData]:
    """
    Get current user if authenticated, None otherwise.

    Does not raise exceptions for missing or invalid sessions.
    """
    try:
        return await get_current_user(request, credentials, db)
    except HTTPException:
        return None


async def ensure_user_profile(
    neon_user_id: str,
    email: str,
    name: str,
    db: AsyncSession,
):
    """
    Ensure a user profile exists in our application's users table.

    When a user signs up via Neon Auth, they exist in neon_auth.user but
    not in our public.users table. This syncs on first API call.
    """
    from repositories.user_repository import UserRepository

    user_repo = UserRepository(db)
    existing = await user_repo.get_by_id(neon_user_id)

    if existing is None:
        from models.user import User
        new_user = User(
            id=neon_user_id,
            email=email,
            name=name or "",
            region="CT",
        )
        await user_repo.create(new_user)
        logger.info("user_profile_synced", user_id=neon_user_id, email=email)
