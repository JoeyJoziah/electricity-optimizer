"""
Rate Limiting Middleware

Provides per-user and per-IP rate limiting using Redis-backed sliding window.
"""

import hashlib
import json
import time
from typing import Optional
from datetime import datetime, timezone

from fastapi import HTTPException, status
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send
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

    async def check_rate_limits_combined(
        self,
        identifier: str,
    ) -> tuple[bool, int, bool]:
        """
        Check both minute and hour rate limits in a single round-trip.

        Returns:
            Tuple of (minute_allowed, minute_remaining, hour_allowed)
        """
        if self.redis:
            return await self._check_redis_both(identifier)
        else:
            minute_ok, minute_rem = self._check_memory(
                f"ratelimit:minute:{identifier}",
                self.requests_per_minute,
                60,
            )
            hour_ok, _ = self._check_memory(
                f"ratelimit:hour:{identifier}",
                self.requests_per_hour,
                3600,
            )
            return minute_ok, minute_rem, hour_ok

    async def _check_redis_both(
        self,
        identifier: str,
    ) -> tuple[bool, int, bool]:
        """Check both minute and hour limits in a single Redis pipeline."""
        now = time.time()
        minute_key = f"ratelimit:minute:{identifier}"
        hour_key = f"ratelimit:hour:{identifier}"

        pipe = self.redis.pipeline()

        # Minute window
        pipe.zremrangebyscore(minute_key, 0, now - 60)      # [0]
        pipe.zadd(minute_key, {str(now): now})               # [1]
        pipe.zcard(minute_key)                                # [2]
        pipe.expire(minute_key, 60)                           # [3]

        # Hour window
        pipe.zremrangebyscore(hour_key, 0, now - 3600)       # [4]
        pipe.zadd(hour_key, {str(now): now})                  # [5]
        pipe.zcard(hour_key)                                  # [6]
        pipe.expire(hour_key, 3600)                           # [7]

        results = await pipe.execute()
        minute_count = results[2]
        hour_count = results[6]

        minute_allowed = minute_count <= self.requests_per_minute
        minute_remaining = max(0, self.requests_per_minute - minute_count)
        hour_allowed = hour_count <= self.requests_per_hour

        if not minute_allowed:
            logger.warning(
                "rate_limit_exceeded",
                key=minute_key,
                count=minute_count,
                limit=self.requests_per_minute,
            )
        if not hour_allowed:
            logger.warning(
                "rate_limit_exceeded",
                key=hour_key,
                count=hour_count,
                limit=self.requests_per_hour,
            )

        return minute_allowed, minute_remaining, hour_allowed

    def _check_memory(
        self,
        key: str,
        limit: int,
        window: int,
    ) -> tuple[bool, int]:
        """Check rate limit using in-memory store (fallback)"""
        now = time.time()
        window_start = now - window

        # Remove old entries; use setdefault to avoid race with concurrent coroutines
        existing = self._memory_store.get(key)
        if existing is not None:
            self._memory_store[key] = [t for t in existing if t > window_start]
            # Evict truly empty keys to bound memory growth
            if not self._memory_store[key]:
                del self._memory_store[key]

        # Periodic sweep: cap total keys to prevent unbounded growth during Redis outage
        if len(self._memory_store) > 10_000:
            stale_keys = [
                k for k, v in self._memory_store.items()
                if isinstance(v, list) and (not v or v[-1] < window_start)
            ]
            for k in stale_keys:
                del self._memory_store[k]

        # Add current request (setdefault avoids KeyError if evicted above)
        self._memory_store.setdefault(key, []).append(now)

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


class RateLimitMiddleware:
    """
    Pure ASGI middleware for rate limiting.

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
        self.app = app
        self.rate_limiter = rate_limiter or UserRateLimiter()
        self.exclude_paths = exclude_paths or ["/health", "/metrics"]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Apply rate limiting to request."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # Skip rate limiting for excluded paths
        if any(path.startswith(p) for p in self.exclude_paths):
            await self.app(scope, receive, send)
            return

        # Get identifier (user ID from token or IP address)
        identifier = self._get_identifier(scope)

        # Check both minute and hour limits in a single round-trip
        minute_ok, remaining, hour_ok = await self.rate_limiter.check_rate_limits_combined(
            identifier
        )

        if not minute_ok:
            await self._send_429(send, retry_after=60)
            return

        if not hour_ok:
            await self._send_429(send, retry_after=3600)
            return

        # Process request, injecting rate-limit headers into the response
        limit_str = str(self.rate_limiter.requests_per_minute).encode()
        remaining_str = str(remaining).encode()

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = limit_str.decode()
                headers["X-RateLimit-Remaining"] = remaining_str.decode()
            await send(message)

        await self.app(scope, receive, send_wrapper)

    @staticmethod
    async def _send_429(send: Send, retry_after: int) -> None:
        """Send a 429 Too Many Requests response directly via raw ASGI messages."""
        body = json.dumps(
            {"detail": f"Rate limit exceeded. Retry after {retry_after} seconds."}
        ).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
                [b"retry-after", str(retry_after).encode()],
            ],
        })
        await send({"type": "http.response.body", "body": body})

    def _get_identifier(self, scope: Scope) -> str:
        """Get identifier for rate limiting (user ID or IP) from raw ASGI scope."""
        # Headers in ASGI scope are list[tuple[bytes, bytes]]
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        for header_name, header_value in headers:
            if header_name == b"authorization":
                auth = header_value.decode("latin-1")
                if auth.startswith("Bearer "):
                    token_hash = hashlib.sha256(auth[7:].encode()).hexdigest()[:16]
                    return f"user:{token_hash}"
                break

        # Prefer Cloudflare's real client IP (behind CF Worker edge layer)
        for header_name, header_value in headers:
            if header_name == b"cf-connecting-ip":
                return f"ip:{header_value.decode('ascii')}"

        # Fallback: X-Forwarded-For (first entry = original client)
        for header_name, header_value in headers:
            if header_name == b"x-forwarded-for":
                real_ip = header_value.decode("ascii").split(",")[0].strip()
                return f"ip:{real_ip}"

        # Last resort: ASGI client tuple (reverse proxy IP if behind LB)
        client = scope.get("client")
        if client:
            return f"ip:{client[0]}"

        return "ip:unknown"


# Global rate limiter instance (initialized with app)
rate_limiter: Optional[UserRateLimiter] = None


async def get_rate_limiter(redis: aioredis.Redis = None) -> UserRateLimiter:
    """Get or create rate limiter instance"""
    global rate_limiter
    if rate_limiter is None:
        rate_limiter = UserRateLimiter(redis_client=redis)
    return rate_limiter
