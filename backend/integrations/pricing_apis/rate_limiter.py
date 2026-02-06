"""
Rate Limiting Implementation

Provides token bucket and sliding window rate limiting for API calls.
Supports both in-memory and Redis-backed rate limiting for distributed systems.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import asyncio
import time

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""

    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    requests_per_day: Optional[int] = None

    # Burst allowance (multiplier of per-minute rate)
    burst_multiplier: float = 1.5

    # Whether to queue requests when rate limited
    queue_when_limited: bool = True
    max_queue_size: int = 100
    queue_timeout_seconds: float = 30.0


class RateLimiter(ABC):
    """Abstract base class for rate limiters"""

    @abstractmethod
    async def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        """
        Attempt to acquire tokens from the rate limiter.

        Args:
            key: Identifier for the rate limit bucket (e.g., API name)
            tokens: Number of tokens to acquire

        Returns:
            True if tokens were acquired, False if rate limited
        """
        pass

    @abstractmethod
    async def wait_for_token(
        self,
        key: str = "default",
        timeout: Optional[float] = None,
    ) -> bool:
        """
        Wait until a token is available.

        Args:
            key: Identifier for the rate limit bucket
            timeout: Maximum time to wait in seconds

        Returns:
            True if token was acquired, False if timeout
        """
        pass

    @abstractmethod
    async def get_remaining(self, key: str = "default") -> int:
        """Get remaining tokens in the bucket"""
        pass

    @abstractmethod
    async def reset(self, key: str = "default") -> None:
        """Reset the rate limiter for a key"""
        pass


class TokenBucketLimiter(RateLimiter):
    """
    Token bucket rate limiter implementation.

    Tokens are added at a constant rate up to a maximum bucket size.
    Each request consumes one or more tokens.
    """

    def __init__(
        self,
        rate: float,  # Tokens per second
        capacity: int,  # Maximum bucket size
        name: str = "default",
    ):
        self.rate = rate
        self.capacity = capacity
        self.name = name

        # State per key
        self._buckets: dict[str, dict] = {}
        self._lock = asyncio.Lock()

        self.logger = logger.bind(rate_limiter=name)

    def _get_bucket(self, key: str) -> dict:
        """Get or create bucket for key"""
        if key not in self._buckets:
            self._buckets[key] = {
                "tokens": float(self.capacity),
                "last_update": time.monotonic(),
            }
        return self._buckets[key]

    def _refill_bucket(self, bucket: dict) -> None:
        """Refill tokens based on elapsed time"""
        now = time.monotonic()
        elapsed = now - bucket["last_update"]
        bucket["tokens"] = min(
            self.capacity,
            bucket["tokens"] + (elapsed * self.rate)
        )
        bucket["last_update"] = now

    async def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        """Attempt to acquire tokens"""
        async with self._lock:
            bucket = self._get_bucket(key)
            self._refill_bucket(bucket)

            if bucket["tokens"] >= tokens:
                bucket["tokens"] -= tokens
                self.logger.debug(
                    "tokens_acquired",
                    key=key,
                    tokens=tokens,
                    remaining=bucket["tokens"],
                )
                return True

            self.logger.debug(
                "rate_limited",
                key=key,
                tokens_requested=tokens,
                tokens_available=bucket["tokens"],
            )
            return False

    async def wait_for_token(
        self,
        key: str = "default",
        timeout: Optional[float] = None,
    ) -> bool:
        """Wait until token is available"""
        start_time = time.monotonic()

        while True:
            if await self.acquire(key):
                return True

            # Calculate wait time
            async with self._lock:
                bucket = self._get_bucket(key)
                tokens_needed = 1 - bucket["tokens"]
                wait_time = tokens_needed / self.rate if self.rate > 0 else 1.0

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed + wait_time > timeout:
                    self.logger.warning(
                        "rate_limit_timeout",
                        key=key,
                        timeout=timeout,
                    )
                    return False
                wait_time = min(wait_time, timeout - elapsed)

            # Wait for tokens to refill
            await asyncio.sleep(min(wait_time, 1.0))

    async def get_remaining(self, key: str = "default") -> int:
        """Get remaining tokens"""
        async with self._lock:
            bucket = self._get_bucket(key)
            self._refill_bucket(bucket)
            return int(bucket["tokens"])

    async def reset(self, key: str = "default") -> None:
        """Reset bucket to full capacity"""
        async with self._lock:
            self._buckets[key] = {
                "tokens": float(self.capacity),
                "last_update": time.monotonic(),
            }
            self.logger.info("rate_limiter_reset", key=key)


class SlidingWindowLimiter(RateLimiter):
    """
    Sliding window rate limiter implementation.

    Tracks requests within a time window and limits based on count.
    More accurate than fixed window but requires more memory.
    """

    def __init__(
        self,
        requests_per_window: int,
        window_seconds: float,
        name: str = "default",
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.name = name

        # Timestamps of requests per key
        self._windows: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

        self.logger = logger.bind(rate_limiter=name)

    def _clean_window(self, key: str) -> None:
        """Remove expired timestamps from window"""
        if key not in self._windows:
            self._windows[key] = []
            return

        cutoff = time.monotonic() - self.window_seconds
        self._windows[key] = [
            ts for ts in self._windows[key] if ts > cutoff
        ]

    async def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        """Attempt to acquire tokens"""
        async with self._lock:
            self._clean_window(key)

            if len(self._windows[key]) + tokens <= self.requests_per_window:
                now = time.monotonic()
                self._windows[key].extend([now] * tokens)
                self.logger.debug(
                    "request_allowed",
                    key=key,
                    count=len(self._windows[key]),
                    limit=self.requests_per_window,
                )
                return True

            self.logger.debug(
                "rate_limited",
                key=key,
                count=len(self._windows[key]),
                limit=self.requests_per_window,
            )
            return False

    async def wait_for_token(
        self,
        key: str = "default",
        timeout: Optional[float] = None,
    ) -> bool:
        """Wait until token is available"""
        start_time = time.monotonic()

        while True:
            if await self.acquire(key):
                return True

            # Calculate wait time based on oldest request
            async with self._lock:
                self._clean_window(key)
                if not self._windows[key]:
                    continue

                oldest = min(self._windows[key])
                wait_time = (oldest + self.window_seconds) - time.monotonic()
                wait_time = max(0.1, wait_time)

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)

            await asyncio.sleep(wait_time)

    async def get_remaining(self, key: str = "default") -> int:
        """Get remaining requests in window"""
        async with self._lock:
            self._clean_window(key)
            return self.requests_per_window - len(self._windows.get(key, []))

    async def reset(self, key: str = "default") -> None:
        """Clear window"""
        async with self._lock:
            self._windows[key] = []
            self.logger.info("rate_limiter_reset", key=key)


class CompositeRateLimiter(RateLimiter):
    """
    Combines multiple rate limiters with AND logic.

    Request is only allowed if ALL limiters allow it.
    Useful for APIs with multiple rate limits (per-minute AND per-hour).
    """

    def __init__(self, limiters: list[RateLimiter], name: str = "composite"):
        self.limiters = limiters
        self.name = name
        self.logger = logger.bind(rate_limiter=name)

    async def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        """Acquire from all limiters"""
        # Check all limiters first without consuming
        for limiter in self.limiters:
            remaining = await limiter.get_remaining(key)
            if remaining < tokens:
                self.logger.debug(
                    "composite_rate_limited",
                    key=key,
                    limiter=getattr(limiter, "name", "unknown"),
                )
                return False

        # All have capacity, consume from all
        for limiter in self.limiters:
            await limiter.acquire(key, tokens)

        return True

    async def wait_for_token(
        self,
        key: str = "default",
        timeout: Optional[float] = None,
    ) -> bool:
        """Wait for all limiters to have tokens"""
        start_time = time.monotonic()

        while True:
            if await self.acquire(key):
                return True

            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False

            await asyncio.sleep(0.1)

    async def get_remaining(self, key: str = "default") -> int:
        """Get minimum remaining across all limiters"""
        remaining_counts = []
        for limiter in self.limiters:
            remaining_counts.append(await limiter.get_remaining(key))
        return min(remaining_counts) if remaining_counts else 0

    async def reset(self, key: str = "default") -> None:
        """Reset all limiters"""
        for limiter in self.limiters:
            await limiter.reset(key)


class RedisRateLimiter(RateLimiter):
    """
    Redis-backed rate limiter for distributed systems.

    Uses Redis sorted sets for sliding window implementation.
    """

    def __init__(
        self,
        redis_client,  # aioredis client
        requests_per_window: int,
        window_seconds: float,
        name: str = "redis",
        key_prefix: str = "ratelimit",
    ):
        self.redis = redis_client
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.name = name
        self.key_prefix = key_prefix

        self.logger = logger.bind(rate_limiter=name)

    def _get_redis_key(self, key: str) -> str:
        """Generate Redis key"""
        return f"{self.key_prefix}:{self.name}:{key}"

    async def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        """Acquire tokens using Redis sorted set"""
        redis_key = self._get_redis_key(key)
        now = time.time()
        window_start = now - self.window_seconds

        pipe = self.redis.pipeline()

        # Remove expired entries
        pipe.zremrangebyscore(redis_key, "-inf", window_start)

        # Count current entries
        pipe.zcard(redis_key)

        # Execute pipeline
        results = await pipe.execute()
        current_count = results[1]

        if current_count + tokens <= self.requests_per_window:
            # Add new entries
            pipe = self.redis.pipeline()
            for i in range(tokens):
                pipe.zadd(redis_key, {f"{now}:{i}": now})
            pipe.expire(redis_key, int(self.window_seconds) + 1)
            await pipe.execute()

            self.logger.debug(
                "redis_request_allowed",
                key=key,
                count=current_count + tokens,
                limit=self.requests_per_window,
            )
            return True

        self.logger.debug(
            "redis_rate_limited",
            key=key,
            count=current_count,
            limit=self.requests_per_window,
        )
        return False

    async def wait_for_token(
        self,
        key: str = "default",
        timeout: Optional[float] = None,
    ) -> bool:
        """Wait for token availability"""
        start_time = time.monotonic()

        while True:
            if await self.acquire(key):
                return True

            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False

            await asyncio.sleep(0.1)

    async def get_remaining(self, key: str = "default") -> int:
        """Get remaining requests"""
        redis_key = self._get_redis_key(key)
        now = time.time()
        window_start = now - self.window_seconds

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(redis_key, "-inf", window_start)
        pipe.zcard(redis_key)
        results = await pipe.execute()

        current_count = results[1]
        return max(0, self.requests_per_window - current_count)

    async def reset(self, key: str = "default") -> None:
        """Delete Redis key"""
        redis_key = self._get_redis_key(key)
        await self.redis.delete(redis_key)
        self.logger.info("redis_rate_limiter_reset", key=key)


def create_api_rate_limiter(
    api_name: str,
    requests_per_minute: Optional[int] = None,
    requests_per_hour: Optional[int] = None,
) -> RateLimiter:
    """
    Factory function to create rate limiter for an API.

    Args:
        api_name: Name of the API (used for logging)
        requests_per_minute: Rate limit per minute
        requests_per_hour: Rate limit per hour

    Returns:
        Configured rate limiter
    """
    limiters = []

    if requests_per_minute:
        limiters.append(
            SlidingWindowLimiter(
                requests_per_window=requests_per_minute,
                window_seconds=60,
                name=f"{api_name}_minute",
            )
        )

    if requests_per_hour:
        limiters.append(
            SlidingWindowLimiter(
                requests_per_window=requests_per_hour,
                window_seconds=3600,
                name=f"{api_name}_hour",
            )
        )

    if len(limiters) == 0:
        # No limits - return a permissive limiter
        return TokenBucketLimiter(
            rate=1000,  # Very high rate
            capacity=10000,
            name=api_name,
        )
    elif len(limiters) == 1:
        return limiters[0]
    else:
        return CompositeRateLimiter(limiters, name=api_name)
