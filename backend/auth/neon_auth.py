"""
Neon Auth Session Validation

Validates user sessions by querying the neon_auth.session and neon_auth.user
tables directly. Sessions are created by Better Auth (via the Next.js frontend)
and validated here for backend API access.

Session tokens arrive via:
1. Cookie: '__Secure-better-auth.session_token' (production HTTPS only)
   or 'better-auth.session_token' (development/test HTTP)
2. Header: 'Authorization: Bearer <session_token>' (API clients, all environments)

In production, ONLY the __Secure- prefixed cookie is accepted to prevent
cookie downgrade attacks (11-P1-2).

Session cache entries in Redis are encrypted with AES-256-GCM using the
FIELD_ENCRYPTION_KEY to protect user data at rest.
"""

import hashlib
import json
from dataclasses import dataclass

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import db_manager, get_timescale_session
from config.settings import settings

logger = structlog.get_logger()


# Security scheme — accepts Bearer token but doesn't require it
# (we also check cookies)
security = HTTPBearer(auto_error=False)


SESSION_COOKIE_NAME = "better-auth.session_token"
# On HTTPS (production), Better Auth prefixes with __Secure-
SESSION_COOKIE_NAME_SECURE = "__Secure-better-auth.session_token"


@dataclass
class SessionData:
    """Authenticated user session data from neon_auth schema."""

    user_id: str
    email: str
    name: str = ""
    email_verified: bool = False
    role: str | None = None


# Zenith audit H-15-01: reduced from 300s to 60s to limit stale-session window
# for banned/deactivated users. Explicit cache invalidation on logout ensures
# immediate session termination (see invalidate_session_cache in api/v1/auth.py).
_SESSION_CACHE_TTL = 60  # seconds

# Audit 2026-03-19 finding 11-P1-2: "banned user" marker TTL.
# When a user is banned, we set a short-lived Redis marker keyed by user_id.
# The session cache lookup checks this marker and bypasses the cache hit,
# forcing a DB re-check (which filters banned=true).  This eliminates the
# stale-cache window entirely without needing a user->token reverse index.
_BANNED_USER_MARKER_TTL = 120  # seconds (covers 2x cache TTL)


def _encrypt_session_cache(plaintext: str) -> bytes:
    """
    Encrypt session cache data with AES-256-GCM before storing in Redis.

    Uses the same FIELD_ENCRYPTION_KEY as field-level encryption. Falls back
    to plaintext JSON if the encryption key is not configured (dev mode only).

    In production, encryption is mandatory — a missing FIELD_ENCRYPTION_KEY
    raises RuntimeError to prevent storing plaintext session data in Redis.
    """
    try:
        from utils.encryption import encrypt_field

        return encrypt_field(plaintext)
    except RuntimeError:
        if settings.is_production:
            # 11-P1-4: Never fall back to plaintext in production.
            # Session data in Redis MUST be encrypted.
            raise
        # FIELD_ENCRYPTION_KEY not configured — fall back to unencrypted
        # so development environments without the key still work.
        return plaintext.encode("utf-8")


def _decrypt_session_cache(data) -> str:
    """
    Decrypt session cache data retrieved from Redis.

    Handles both encrypted (AES-256-GCM) and legacy unencrypted (plain JSON)
    cache entries for seamless migration.
    """
    if isinstance(data, str):
        raw = data.encode("utf-8")
    else:
        raw = bytes(data)

    # Try decryption first. AES-256-GCM ciphertext is always binary and will
    # never start with '{', so a quick check distinguishes encrypted from
    # legacy plaintext entries.
    if raw and raw[0:1] != b"{":
        try:
            from utils.encryption import decrypt_field

            return decrypt_field(raw)
        except Exception:
            pass  # Fall through to plaintext handling

    # Legacy unencrypted entry or decryption failed — treat as plain JSON
    return raw.decode("utf-8")


async def _get_session_from_token(
    session_token: str,
    db: AsyncSession,
    redis=None,
) -> SessionData | None:
    """
    Query neon_auth.session + neon_auth.user for the given session token.

    Uses Redis as a short-lived cache (_SESSION_CACHE_TTL) to avoid hitting the DB
    on every authenticated request. Returns SessionData if the token is
    valid and not expired, None otherwise.
    """
    cache_key = f"session:{hashlib.sha256(session_token.encode()).hexdigest()[:32]}"

    # Try Redis cache first (encrypted with AES-256-GCM)
    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                data = json.loads(_decrypt_session_cache(cached))
                # Check for "banned user" marker — if present, skip cache hit
                # and fall through to DB (which filters banned=true).  This
                # eliminates the stale-cache window after a user ban.
                user_id = data.get("user_id")
                if user_id:
                    banned_marker = await redis.get(f"banned_user:{user_id}")
                    if banned_marker:
                        logger.info(
                            "session_cache_bypass_banned_user",
                            user_id=user_id,
                        )
                        # Delete the stale cache entry proactively
                        await redis.delete(cache_key)
                        # Fall through to DB query (will return None for banned user)
                    else:
                        return SessionData(**data)
                else:
                    return SessionData(**data)
        except Exception:
            pass  # Cache miss, decryption error, or connection error — fall through to DB

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
          AND u."emailVerified" = true
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

    # Cache in Redis for subsequent requests (encrypted with AES-256-GCM)
    if redis is not None:
        try:
            plaintext = json.dumps(
                {
                    "user_id": session_data.user_id,
                    "email": session_data.email,
                    "name": session_data.name,
                    "email_verified": session_data.email_verified,
                    "role": session_data.role,
                }
            )
            await redis.setex(
                cache_key,
                _SESSION_CACHE_TTL,
                _encrypt_session_cache(plaintext),
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


async def invalidate_sessions_for_banned_user(user_id: str, redis=None) -> bool:
    """
    Set a "banned user" marker in Redis so all cached sessions for this user
    are bypassed on their next use, forcing a DB re-check.

    This is more robust than trying to find and delete individual session
    cache keys (which are keyed by token hash, not user_id).  The marker
    lives for ``_BANNED_USER_MARKER_TTL`` seconds — long enough to cover
    all unexpired cache entries (TTL 60s).

    Call this when banning/suspending a user to immediately revoke access
    without waiting for the session cache to expire.

    Returns True if the marker was set, False otherwise.
    """
    if redis is None:
        return False
    try:
        await redis.setex(
            f"banned_user:{user_id}",
            _BANNED_USER_MARKER_TTL,
            "1",
        )
        logger.info("banned_user_marker_set", user_id=user_id, ttl=_BANNED_USER_MARKER_TTL)
        return True
    except Exception:
        return False


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
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
    session_token: str | None = None

    if credentials and credentials.credentials:
        session_token = credentials.credentials
    else:
        # 11-P1-2: In production (HTTPS), ONLY accept the __Secure- prefixed
        # cookie to prevent cookie downgrade attacks where an attacker tricks
        # the browser into sending a non-secure cookie over HTTP.
        if settings.is_production:
            session_token = request.cookies.get(SESSION_COOKIE_NAME_SECURE)
        else:
            # In dev/test, accept both cookie names (for local HTTP servers)
            session_token = request.cookies.get(SESSION_COOKIE_NAME) or request.cookies.get(
                SESSION_COOKIE_NAME_SECURE
            )

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
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_timescale_session),
) -> SessionData | None:
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
) -> bool:
    """
    Ensure a user profile exists in our application's users table.

    When a user signs up via Neon Auth, they exist in neon_auth.user but
    not in our public.users table. This syncs on first API call.

    Returns True if a new profile was created, False if it already existed.

    Uses raw SQL because the User model is Pydantic (not SQLAlchemy ORM),
    so select(User) doesn't work outside of the test mock fixture.

    Notes on schema compatibility:
    - `region` is nullable since migration 018 (DROP NOT NULL). Upsert passes
      NULL so the user selects their region during onboarding.
    - `name` VARCHAR(200) NOT NULL — we pass an empty string as the safe
      default when the provider supplies no name.
    - ON CONFLICT (id) DO UPDATE email/name handles the edge case where a
      user changes their email or display name in the identity provider.
    """
    # Upsert — create profile if absent; update email/name if changed.
    # ON CONFLICT (id) DO UPDATE keeps the row in sync with neon_auth.user
    # without touching region/preferences/onboarding data the user may have set.
    insert = text("""
        INSERT INTO public.users (id, email, name, region, is_active, created_at, updated_at)
        VALUES (:id, :email, :name, NULL, true, NOW(), NOW())
        ON CONFLICT (id) DO UPDATE
            SET email      = EXCLUDED.email,
                name       = CASE
                                 WHEN EXCLUDED.name <> '' THEN EXCLUDED.name
                                 ELSE public.users.name
                             END,
                updated_at = NOW()
        WHERE public.users.email <> EXCLUDED.email
           OR (EXCLUDED.name <> '' AND public.users.name <> EXCLUDED.name)
    """)
    result = await db.execute(
        insert, {"id": neon_user_id, "email": email.lower(), "name": name or ""}
    )
    await db.commit()
    created = result.rowcount > 0
    if created:
        logger.info("user_profile_synced", user_id=neon_user_id, email=email)
    return created
