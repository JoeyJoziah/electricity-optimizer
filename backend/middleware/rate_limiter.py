"""
Rate Limiting Middleware

Provides per-user and per-IP rate limiting using Redis-backed sliding window.
"""

import time
from typing import Optional, Callable
from datetime import datetime, timezone

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from redis import asyncio as aioredis

import structlog

from config.settings import settings


logger = structlog.get_logger()


class RateLimitExceeded(HTTPException):
    """Exception raised when rate limit is exceeded"""

    def __init__(self, retry_after: int, limit_type: str = "requests"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
        self.retry_after = retry_after
        self.limit_type = limit_type


class UserRateLimiter:
    """
    Per-user rate limiter using Redis sliding window.

    Implements:
    - Per-minute rate limiting (default: 100/min)
    - Per-hour rate limiting (default: 1000/hour)
    - Login attempt limiting (5 attempts, 15 min lockout)
    """

    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
        requests_per_minute: int = None,
        requests_per_hour: int = None,
        login_attempts: int = 5,
        lockout_minutes: int = 15,
    ):
        """
        Initialize rate limiter.

        Args:
            redis_client: Redis client (uses in-memory fallback if not provided)
            requests_per_minute: Max requests per minute per user
            requests_per_hour: Max requests per hour per user
            login_attempts: Max failed login attempts before lockout
            lockout_minutes: Lockout duration after max attempts
        """
        self.redis = redis_client
        self.requests_per_minute = requests_per_minute or settings.rate_limit_per_minute
        self.requests_per_hour = requests_per_hour or settings.rate_limit_per_hour
        self.login_attempts = login_attempts
        self.lockout_minutes = lockout_minutes

        # In-memory fallback for when Redis is not available
        self._memory_store: dict = {}

    def reset(self):
        """Clear all in-memory rate limit state and detach Redis."""
        self._memory_store.clear()
        self.redis = None

    async def check_rate_limit(
        self,
        identifier: str,
        limit_type: str = "minute",
    ) -> tuple[bool, int]:
        """
        Check if rate limit is exceeded.

        Args:
            identifier: User ID or IP address
            limit_type: "minute" or "hour"

        Returns:
            Tuple of (allowed, remaining_requests)
        """
        if limit_type == "minute":
            limit = self.requests_per_minute
            window = 60
        else:
            limit = self.requests_per_hour
            window = 3600

        key = f"ratelimit:{limit_type}:{identifier}"

        if self.redis:
            return await self._check_redis(key, limit, window)
        else:
            return self._check_memory(key, limit, window)

    async def _check_redis(
        self,
        key: str,
        limit: int,
        window: int,
    ) -> tuple[bool, int]:
        """Check rate limit using Redis sliding window"""
        now = time.time()
        window_start = now - window

        pipe = self.redis.pipeline()

        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)

        # Add current request
        pipe.zadd(key, {str(now): now})

        # Count requests in window
        pipe.zcard(key)

        # Set expiry
        pipe.expire(key, window)

        results = await pipe.execute()
        request_count = results[2]

        allowed = request_count <= limit
        remaining = max(0, limit - request_count)

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                key=key,
                count=request_count,
                limit=limit,
            )

        return allowed, remaining

    def _check_memory(
        self,
        key: str,
        limit: int,
        window: int,
    ) -> tuple[bool, int]:
        """Check rate limit using in-memory store (fallback)"""
        now = time.time()
        window_start = now - window

        if key not in self._memory_store:
            self._memory_store[key] = []

        # Remove old entries
        self._memory_store[key] = [
            t for t in self._memory_store[key]
            if t > window_start
        ]

        # Add current request
        self._memory_store[key].append(now)

        request_count = len(self._memory_store[key])
        allowed = request_count <= limit
        remaining = max(0, limit - request_count)

        return allowed, remaining

    async def record_login_attempt(
        self,
        identifier: str,
        success: bool,
    ) -> bool:
        """
        Record login attempt and check for lockout.

        Args:
            identifier: User email or IP
            success: Whether login was successful

        Returns:
            True if locked out, False otherwise
        """
        key = f"login_attempts:{identifier}"

        if success:
            # Clear attempts on successful login
            if self.redis:
                await self.redis.delete(key)
            elif key in self._memory_store:
                del self._memory_store[key]
            return False

        # Record failed attempt
        if self.redis:
            attempts = await self.redis.incr(key)
            await self.redis.expire(key, self.lockout_minutes * 60)
        else:
            if key not in self._memory_store:
                self._memory_store[key] = {"count": 0, "expires": 0}
            self._memory_store[key]["count"] += 1
            self._memory_store[key]["expires"] = time.time() + self.lockout_minutes * 60
            attempts = self._memory_store[key]["count"]

        locked_out = attempts >= self.login_attempts

        if locked_out:
            logger.warning(
                "account_locked_out",
                identifier=identifier,
                attempts=attempts,
                lockout_minutes=self.lockout_minutes,
            )

        return locked_out

    async def is_locked_out(self, identifier: str) -> tuple[bool, int]:
        """
        Check if identifier is locked out.

        Args:
            identifier: User email or IP

        Returns:
            Tuple of (is_locked, seconds_remaining)
        """
        key = f"login_attempts:{identifier}"

        if self.redis:
            attempts = await self.redis.get(key)
            if attempts and int(attempts) >= self.login_attempts:
                ttl = await self.redis.ttl(key)
                return True, max(0, ttl)
        else:
            if key in self._memory_store:
                data = self._memory_store[key]
                if data["count"] >= self.login_attempts:
                    remaining = data["expires"] - time.time()
                    if remaining > 0:
                        return True, int(remaining)

        return False, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.

    Applies per-user and per-IP rate limits to all requests.
    """

    def __init__(
        self,
        app: ASGIApp,
        rate_limiter: Optional[UserRateLimiter] = None,
        exclude_paths: Optional[list] = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: ASGI application
            rate_limiter: UserRateLimiter instance
            exclude_paths: Paths to exclude from rate limiting
        """
        super().__init__(app)
        self.rate_limiter = rate_limiter or UserRateLimiter()
        self.exclude_paths = exclude_paths or ["/health", "/metrics"]

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Apply rate limiting to request"""
        # Skip rate limiting for excluded paths
        if any(request.url.path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        # Get identifier (user ID from token or IP address)
        identifier = self._get_identifier(request)

        # Check per-minute limit
        allowed, remaining = await self.rate_limiter.check_rate_limit(
            identifier, "minute"
        )

        if not allowed:
            raise RateLimitExceeded(retry_after=60, limit_type="per_minute")

        # Check per-hour limit
        allowed, _ = await self.rate_limiter.check_rate_limit(
            identifier, "hour"
        )

        if not allowed:
            raise RateLimitExceeded(retry_after=3600, limit_type="per_hour")

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.rate_limiter.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response

    def _get_identifier(self, request: Request) -> str:
        """Get identifier for rate limiting (user ID or IP)"""
        # Try to get user ID from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # Hash the full token to get a unique per-user bucket
            import hashlib
            token_hash = hashlib.sha256(auth_header[7:].encode()).hexdigest()[:16]
            return f"user:{token_hash}"

        # Fall back to IP address
        client = request.client
        if client:
            return f"ip:{client.host}"

        return "ip:unknown"


# Global rate limiter instance (initialized with app)
rate_limiter: Optional[UserRateLimiter] = None


async def get_rate_limiter(redis: aioredis.Redis = None) -> UserRateLimiter:
    """Get or create rate limiter instance"""
    global rate_limiter
    if rate_limiter is None:
        rate_limiter = UserRateLimiter(redis_client=redis)
    return rate_limiter
