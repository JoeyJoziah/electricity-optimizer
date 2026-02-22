"""
JWT Token Handler

Provides secure JWT token creation, verification, and revocation.
Supports RS256 (asymmetric) and HS256 (symmetric) algorithms.

Token revocation uses a Redis-backed blacklist (keyed by JTI) with TTL
set to the token's remaining lifetime so entries expire automatically.
Falls back to an in-memory set when Redis is unavailable, preserving
functionality at the cost of cross-process revocation.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Set
from uuid import uuid4

import jwt
from jwt.exceptions import PyJWTError as JWTError, ExpiredSignatureError
import redis as redis_sync
import structlog

from config.settings import settings


logger = structlog.get_logger()


# =============================================================================
# EXCEPTIONS
# =============================================================================


class TokenError(Exception):
    """Base exception for token errors"""
    pass


class InvalidTokenError(TokenError):
    """Raised when token is invalid (malformed, wrong signature, etc.)"""
    pass


class TokenExpiredError(TokenError):
    """Raised when token has expired"""
    pass


class TokenRevokedError(TokenError):
    """Raised when token has been revoked"""
    pass


# =============================================================================
# JWT HANDLER
# =============================================================================


class JWTHandler:
    """
    JWT token management with support for access and refresh tokens.

    Features:
    - Access tokens with short expiry (15 min default)
    - Refresh tokens with longer expiry (7 days default)
    - Token revocation via JTI blacklist
    - Unique JTI for each token
    - Support for custom claims
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 15,
        refresh_token_expire_days: int = 7,
        issuer: str = "electricity-optimizer",
    ):
        """
        Initialize JWT handler.

        Args:
            secret_key: Secret key for signing (uses settings if not provided)
            algorithm: JWT algorithm (HS256, RS256, etc.)
            access_token_expire_minutes: Access token expiry in minutes
            refresh_token_expire_days: Refresh token expiry in days
            issuer: Token issuer claim
        """
        self.secret_key = secret_key or settings.jwt_secret
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days
        self.issuer = issuer

        # Redis-backed token blacklist with in-memory fallback.
        # Each revoked JTI is stored under key "jwt:revoked:<jti>" with a TTL
        # matching the token's remaining lifetime, so Redis self-cleans.
        self._redis: Optional[redis_sync.Redis] = self._init_redis()

        # In-memory fallback used when Redis is unavailable.
        self._revoked_tokens: Set[str] = set()

        # Upper-bound TTL (seconds) used when no precise remaining lifetime is
        # known.  Equals the maximum refresh-token lifetime so that blacklisted
        # entries are guaranteed to outlive the token they represent.
        self._max_ttl_seconds: int = refresh_token_expire_days * 86400

    # Redis key namespace for revoked JTIs.
    _REDIS_KEY_PREFIX = "jwt:revoked:"

    # -------------------------------------------------------------------------
    # Redis lifecycle helpers
    # -------------------------------------------------------------------------

    def _init_redis(self) -> Optional[redis_sync.Redis]:
        """
        Create a synchronous Redis client from settings.

        Uses the same redis_url / redis_password as the async db_manager so
        that both layers share one Redis deployment.

        Returns:
            A connected Redis client, or None if Redis is not configured /
            unreachable.
        """
        redis_url = getattr(settings, "redis_url", None)
        if not redis_url:
            logger.info("jwt_revocation_redis_skip", reason="redis_url not configured")
            return None

        try:
            redis_password = getattr(settings, "redis_password", None)
            client = redis_sync.from_url(
                redis_url,
                password=redis_password,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            # Verify connectivity eagerly so we know whether to trust Redis.
            client.ping()
            logger.info("jwt_revocation_redis_ready")
            return client
        except Exception as exc:
            logger.warning(
                "jwt_revocation_redis_unavailable",
                error=str(exc),
                fallback="in-memory set",
            )
            return None

    def create_access_token(
        self,
        user_id: str,
        email: str,
        scopes: Optional[list] = None,
        expires_delta: Optional[timedelta] = None,
        additional_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create an access token.

        Args:
            user_id: User's unique identifier
            email: User's email address
            scopes: List of permission scopes
            expires_delta: Custom expiration time
            additional_claims: Additional JWT claims

        Returns:
            Encoded JWT access token
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=self.access_token_expire_minutes)

        now = datetime.now(timezone.utc)
        expire = now + expires_delta

        payload = {
            "sub": user_id,
            "email": email,
            "scopes": scopes or [],
            "type": "access",
            "iat": now,
            "exp": expire,
            "jti": str(uuid4()),
            "iss": self.issuer,
        }

        if additional_claims:
            payload.update(additional_claims)

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        logger.debug(
            "access_token_created",
            user_id=user_id,
            expires_at=expire.isoformat()
        )

        return token

    def create_refresh_token(
        self,
        user_id: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Create a refresh token.

        Args:
            user_id: User's unique identifier
            expires_delta: Custom expiration time

        Returns:
            Encoded JWT refresh token
        """
        if expires_delta is None:
            expires_delta = timedelta(days=self.refresh_token_expire_days)

        now = datetime.now(timezone.utc)
        expire = now + expires_delta

        payload = {
            "sub": user_id,
            "type": "refresh",
            "iat": now,
            "exp": expire,
            "jti": str(uuid4()),
            "iss": self.issuer,
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        logger.debug(
            "refresh_token_created",
            user_id=user_id,
            expires_at=expire.isoformat()
        )

        return token

    def verify_token(
        self,
        token: str,
        expected_type: str = "access",
    ) -> Dict[str, Any]:
        """
        Verify and decode a token.

        Args:
            token: JWT token to verify
            expected_type: Expected token type ("access" or "refresh")

        Returns:
            Decoded token payload

        Raises:
            InvalidTokenError: If token is invalid
            TokenExpiredError: If token has expired
            TokenRevokedError: If token has been revoked
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"require": ["sub", "exp", "iat", "jti", "type"]}
            )

            # Check token type
            if payload.get("type") != expected_type:
                raise InvalidTokenError(
                    f"Expected {expected_type} token, got {payload.get('type')}"
                )

            # Check revocation
            jti = payload.get("jti")
            if self.is_token_revoked(jti):
                raise TokenRevokedError(f"Token {jti} has been revoked")

            logger.debug(
                "token_verified",
                user_id=payload.get("sub"),
                token_type=expected_type
            )

            return payload

        except ExpiredSignatureError:
            logger.warning("token_expired", token_prefix=token[:20])
            raise TokenExpiredError("Token has expired")

        except JWTError as e:
            logger.warning("token_invalid", error=str(e))
            raise InvalidTokenError(f"Invalid token: {str(e)}")

    def decode_token(
        self,
        token: str,
        verify_exp: bool = True,
    ) -> Dict[str, Any]:
        """
        Decode a token without full verification.

        Useful for inspecting token contents (e.g., for debugging).

        Args:
            token: JWT token to decode
            verify_exp: Whether to verify expiration

        Returns:
            Decoded token payload

        Raises:
            InvalidTokenError: If token is malformed
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={
                    "verify_exp": verify_exp,
                    "verify_signature": True,
                }
            )
            return payload

        except JWTError as e:
            raise InvalidTokenError(f"Cannot decode token: {str(e)}")

    def revoke_token(self, jti: str, ttl_seconds: Optional[int] = None) -> None:
        """
        Revoke a token by its JTI.

        The JTI is stored in Redis with a TTL equal to the token's remaining
        lifetime so that the blacklist entry expires automatically once the
        token would have expired anyway.  When Redis is unavailable the JTI is
        added to the in-memory fallback set instead.

        Args:
            jti: JWT ID to revoke.
            ttl_seconds: Remaining lifetime of the token in seconds.  When
                omitted the maximum possible token lifetime is used as a safe
                upper bound (refresh_token_expire_days converted to seconds).
        """
        effective_ttl = ttl_seconds if ttl_seconds is not None else self._max_ttl_seconds

        if self._redis is not None:
            try:
                redis_key = f"{self._REDIS_KEY_PREFIX}{jti}"
                self._redis.setex(redis_key, effective_ttl, "1")
                logger.info("token_revoked", jti=jti, backend="redis", ttl=effective_ttl)
                return
            except Exception as exc:
                logger.warning(
                    "jwt_revocation_redis_write_failed",
                    jti=jti,
                    error=str(exc),
                    fallback="in-memory set",
                )

        # Fallback: in-memory set (no TTL — entries live for the process lifetime)
        self._revoked_tokens.add(jti)
        logger.info("token_revoked", jti=jti, backend="memory")

    def is_token_revoked(self, jti: str) -> bool:
        """
        Check if a token has been revoked.

        Queries Redis first.  Falls back to the in-memory set when Redis is
        unavailable or raises an exception.

        Args:
            jti: JWT ID to check.

        Returns:
            True if the token has been revoked, False otherwise.
        """
        if self._redis is not None:
            try:
                redis_key = f"{self._REDIS_KEY_PREFIX}{jti}"
                return self._redis.exists(redis_key) == 1
            except Exception as exc:
                logger.warning(
                    "jwt_revocation_redis_read_failed",
                    jti=jti,
                    error=str(exc),
                    fallback="in-memory set",
                )

        # Fallback: in-memory set
        return jti in self._revoked_tokens

    def clear_revoked_tokens(self) -> None:
        """
        Clear all revoked tokens.

        Intended for use in tests.  Flushes matching Redis keys via SCAN so
        that only keys belonging to this handler's namespace are removed
        (rather than flushing the entire database).
        """
        self._revoked_tokens.clear()

        if self._redis is not None:
            try:
                pattern = f"{self._REDIS_KEY_PREFIX}*"
                cursor = 0
                while True:
                    cursor, keys = self._redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        self._redis.delete(*keys)
                    if cursor == 0:
                        break
                logger.debug("jwt_revoked_tokens_cleared", backend="redis")
            except Exception as exc:
                logger.warning(
                    "jwt_revocation_redis_clear_failed",
                    error=str(exc),
                )


# =============================================================================
# GLOBAL JWT HANDLER INSTANCE
# =============================================================================


jwt_handler = JWTHandler(
    secret_key=settings.jwt_secret,
    algorithm=settings.jwt_algorithm,
    access_token_expire_minutes=15,
    refresh_token_expire_days=7,
)
