"""
Redis Caching Layer for Pricing APIs

Provides intelligent caching with:
- Configurable TTL based on data type
- Cache-aside pattern implementation
- Automatic serialization/deserialization
- Cache warming capabilities
- Metrics and monitoring
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional, TypeVar, Generic
import asyncio
import hashlib
import json

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


@dataclass
class CacheConfig:
    """Configuration for caching behavior"""

    # TTL settings (in seconds)
    current_price_ttl: int = 900  # 15 minutes
    price_forecast_ttl: int = 3600  # 1 hour
    historical_price_ttl: int = 86400  # 24 hours
    static_data_ttl: int = 604800  # 1 week

    # Key prefixes
    key_prefix: str = "pricing"

    # Compression for large values
    compress_threshold_bytes: int = 1024

    # Background refresh
    background_refresh: bool = True
    refresh_threshold: float = 0.75  # Refresh when 75% of TTL has passed


class CacheEntry(Generic[T]):
    """Represents a cached value with metadata"""

    def __init__(
        self,
        value: T,
        created_at: datetime,
        ttl_seconds: int,
        key: str,
    ):
        self.value = value
        self.created_at = created_at
        self.ttl_seconds = ttl_seconds
        self.key = key

    @property
    def expires_at(self) -> datetime:
        """When this entry expires"""
        return self.created_at + timedelta(seconds=self.ttl_seconds)

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        return datetime.utcnow() > self.expires_at

    @property
    def ttl_remaining(self) -> float:
        """Remaining TTL in seconds"""
        remaining = (self.expires_at - datetime.utcnow()).total_seconds()
        return max(0, remaining)

    @property
    def age_ratio(self) -> float:
        """Ratio of age to TTL (0.0 = fresh, 1.0 = expired)"""
        age = (datetime.utcnow() - self.created_at).total_seconds()
        return min(1.0, age / self.ttl_seconds)

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "value": self.value,
            "created_at": self.created_at.isoformat(),
            "ttl_seconds": self.ttl_seconds,
            "key": self.key,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CacheEntry":
        """Deserialize from dictionary"""
        return cls(
            value=data["value"],
            created_at=datetime.fromisoformat(data["created_at"]),
            ttl_seconds=data["ttl_seconds"],
            key=data["key"],
        )


class PricingCache:
    """
    Redis-backed cache for pricing data.

    Features:
    - Automatic TTL management
    - Stale-while-revalidate pattern
    - Background refresh for hot data
    - Metrics collection
    """

    def __init__(
        self,
        redis_client,  # Redis client (async)
        config: Optional[CacheConfig] = None,
    ):
        self.redis = redis_client
        self.config = config or CacheConfig()
        self.logger = logger.bind(component="pricing_cache")

        # Metrics
        self._hits = 0
        self._misses = 0
        self._refreshes = 0

        # Background refresh tasks
        self._refresh_tasks: dict[str, asyncio.Task] = {}
        self._refresh_lock = asyncio.Lock()

    def _generate_key(self, *parts: str) -> str:
        """Generate a cache key from parts"""
        key_str = ":".join(str(p) for p in parts)
        return f"{self.config.key_prefix}:{key_str}"

    def _serialize(self, value: Any) -> str:
        """Serialize value to JSON string"""
        return json.dumps(value, default=str)

    def _deserialize(self, data: str) -> Any:
        """Deserialize JSON string to value"""
        return json.loads(data)

    async def get(
        self,
        key: str,
        fetch_func: Optional[Callable[[], Any]] = None,
        ttl: Optional[int] = None,
    ) -> Optional[Any]:
        """
        Get value from cache with optional fetch on miss.

        Implements cache-aside pattern with optional background refresh.

        Args:
            key: Cache key
            fetch_func: Async function to fetch value on cache miss
            ttl: Custom TTL in seconds (uses default if not specified)

        Returns:
            Cached or fetched value, or None if not found
        """
        full_key = self._generate_key(key)

        try:
            # Try to get from cache
            cached_data = await self.redis.get(full_key)

            if cached_data:
                self._hits += 1
                entry = CacheEntry.from_dict(self._deserialize(cached_data))

                self.logger.debug(
                    "cache_hit",
                    key=key,
                    age_ratio=entry.age_ratio,
                    ttl_remaining=entry.ttl_remaining,
                )

                # Check if we should trigger background refresh
                if (
                    self.config.background_refresh
                    and fetch_func
                    and entry.age_ratio >= self.config.refresh_threshold
                ):
                    await self._schedule_refresh(key, fetch_func, ttl)

                return entry.value

            # Cache miss
            self._misses += 1
            self.logger.debug("cache_miss", key=key)

            if fetch_func:
                # Fetch and cache
                value = await fetch_func()
                if value is not None:
                    await self.set(key, value, ttl)
                return value

            return None

        except Exception as e:
            self.logger.error(
                "cache_error",
                key=key,
                error=str(e),
                error_type=type(e).__name__,
            )
            # On cache error, try to fetch directly
            if fetch_func:
                return await fetch_func()
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (uses default if not specified)

        Returns:
            True if successful
        """
        full_key = self._generate_key(key)
        effective_ttl = ttl if ttl is not None else self.config.current_price_ttl

        try:
            entry = CacheEntry(
                value=value,
                created_at=datetime.utcnow(),
                ttl_seconds=effective_ttl,
                key=key,
            )

            serialized = self._serialize(entry.to_dict())
            await self.redis.set(full_key, serialized, ex=effective_ttl)

            self.logger.debug(
                "cache_set",
                key=key,
                ttl=effective_ttl,
            )
            return True

        except Exception as e:
            self.logger.error(
                "cache_set_error",
                key=key,
                error=str(e),
            )
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from cache"""
        full_key = self._generate_key(key)

        try:
            result = await self.redis.delete(full_key)
            self.logger.debug("cache_delete", key=key, deleted=bool(result))
            return bool(result)
        except Exception as e:
            self.logger.error("cache_delete_error", key=key, error=str(e))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        full_pattern = self._generate_key(pattern)

        try:
            keys = []
            async for key in self.redis.scan_iter(match=full_pattern):
                keys.append(key)

            if keys:
                deleted = await self.redis.delete(*keys)
                self.logger.info(
                    "cache_delete_pattern",
                    pattern=pattern,
                    deleted_count=deleted,
                )
                return deleted
            return 0

        except Exception as e:
            self.logger.error(
                "cache_delete_pattern_error",
                pattern=pattern,
                error=str(e),
            )
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        full_key = self._generate_key(key)
        try:
            return bool(await self.redis.exists(full_key))
        except Exception:
            return False

    async def get_ttl(self, key: str) -> int:
        """Get remaining TTL for a key"""
        full_key = self._generate_key(key)
        try:
            ttl = await self.redis.ttl(full_key)
            return max(0, ttl)
        except Exception:
            return 0

    async def _schedule_refresh(
        self,
        key: str,
        fetch_func: Callable[[], Any],
        ttl: Optional[int],
    ) -> None:
        """Schedule background refresh for a key"""
        async with self._refresh_lock:
            if key in self._refresh_tasks:
                # Refresh already scheduled
                return

            async def refresh():
                try:
                    self._refreshes += 1
                    value = await fetch_func()
                    if value is not None:
                        await self.set(key, value, ttl)
                    self.logger.debug("cache_refresh_complete", key=key)
                except Exception as e:
                    self.logger.error(
                        "cache_refresh_error",
                        key=key,
                        error=str(e),
                    )
                finally:
                    async with self._refresh_lock:
                        self._refresh_tasks.pop(key, None)

            task = asyncio.create_task(refresh())
            self._refresh_tasks[key] = task

    # ==========================================================================
    # Convenience methods for pricing data
    # ==========================================================================

    def current_price_key(self, api: str, region: str) -> str:
        """Generate key for current price"""
        return f"current:{api}:{region}"

    def forecast_key(self, api: str, region: str, hours: int) -> str:
        """Generate key for price forecast"""
        return f"forecast:{api}:{region}:{hours}"

    def historical_key(
        self,
        api: str,
        region: str,
        start_date: str,
        end_date: str,
    ) -> str:
        """Generate key for historical prices"""
        return f"historical:{api}:{region}:{start_date}:{end_date}"

    async def get_current_price(
        self,
        api: str,
        region: str,
        fetch_func: Optional[Callable[[], Any]] = None,
    ) -> Optional[dict]:
        """Get current price with appropriate TTL"""
        key = self.current_price_key(api, region)
        return await self.get(key, fetch_func, self.config.current_price_ttl)

    async def set_current_price(
        self,
        api: str,
        region: str,
        data: dict,
    ) -> bool:
        """Set current price with appropriate TTL"""
        key = self.current_price_key(api, region)
        return await self.set(key, data, self.config.current_price_ttl)

    async def get_forecast(
        self,
        api: str,
        region: str,
        hours: int,
        fetch_func: Optional[Callable[[], Any]] = None,
    ) -> Optional[dict]:
        """Get forecast with appropriate TTL"""
        key = self.forecast_key(api, region, hours)
        return await self.get(key, fetch_func, self.config.price_forecast_ttl)

    async def set_forecast(
        self,
        api: str,
        region: str,
        hours: int,
        data: dict,
    ) -> bool:
        """Set forecast with appropriate TTL"""
        key = self.forecast_key(api, region, hours)
        return await self.set(key, data, self.config.price_forecast_ttl)

    # ==========================================================================
    # Metrics
    # ==========================================================================

    def get_metrics(self) -> dict:
        """Get cache metrics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total,
            "hit_rate_percent": round(hit_rate, 2),
            "background_refreshes": self._refreshes,
            "pending_refreshes": len(self._refresh_tasks),
        }

    def reset_metrics(self) -> None:
        """Reset metrics counters"""
        self._hits = 0
        self._misses = 0
        self._refreshes = 0

    # ==========================================================================
    # Cache warming
    # ==========================================================================

    async def warm_cache(
        self,
        items: list[tuple[str, Callable[[], Any], int]],
    ) -> dict:
        """
        Warm cache with multiple items concurrently.

        Args:
            items: List of (key, fetch_func, ttl) tuples

        Returns:
            Dict with success/failure counts
        """
        results = {"success": 0, "failed": 0, "skipped": 0}

        async def warm_item(key: str, fetch_func: Callable, ttl: int):
            try:
                # Skip if already cached
                if await self.exists(key):
                    return "skipped"

                value = await fetch_func()
                if value is not None:
                    await self.set(key, value, ttl)
                    return "success"
                return "failed"
            except Exception as e:
                self.logger.error(
                    "cache_warm_error",
                    key=key,
                    error=str(e),
                )
                return "failed"

        tasks = [
            warm_item(key, func, ttl)
            for key, func, ttl in items
        ]

        outcomes = await asyncio.gather(*tasks)

        for outcome in outcomes:
            results[outcome] += 1

        self.logger.info(
            "cache_warm_complete",
            **results,
        )

        return results

    async def invalidate_region(self, region: str) -> int:
        """Invalidate all cache entries for a region"""
        return await self.delete_pattern(f"*:{region}")

    async def invalidate_api(self, api: str) -> int:
        """Invalidate all cache entries for an API"""
        return await self.delete_pattern(f"*:{api}:*")


class InMemoryCache(PricingCache):
    """
    In-memory cache implementation for testing or single-instance deployments.

    Not suitable for distributed systems.
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.logger = logger.bind(component="memory_cache")

        self._cache: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

        # Metrics
        self._hits = 0
        self._misses = 0
        self._refreshes = 0
        self._refresh_tasks: dict[str, asyncio.Task] = {}
        self._refresh_lock = asyncio.Lock()

    async def get(
        self,
        key: str,
        fetch_func: Optional[Callable[[], Any]] = None,
        ttl: Optional[int] = None,
    ) -> Optional[Any]:
        """Get value from in-memory cache"""
        full_key = self._generate_key(key)

        async with self._lock:
            if full_key in self._cache:
                entry = self._cache[full_key]

                if not entry.is_expired:
                    self._hits += 1
                    self.logger.debug(
                        "memory_cache_hit",
                        key=key,
                        age_ratio=entry.age_ratio,
                    )

                    # Background refresh
                    if (
                        self.config.background_refresh
                        and fetch_func
                        and entry.age_ratio >= self.config.refresh_threshold
                    ):
                        await self._schedule_refresh(key, fetch_func, ttl)

                    return entry.value
                else:
                    # Expired, remove it
                    del self._cache[full_key]

        # Cache miss
        self._misses += 1
        self.logger.debug("memory_cache_miss", key=key)

        if fetch_func:
            value = await fetch_func()
            if value is not None:
                await self.set(key, value, ttl)
            return value

        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set value in memory cache"""
        full_key = self._generate_key(key)
        effective_ttl = ttl if ttl is not None else self.config.current_price_ttl

        async with self._lock:
            self._cache[full_key] = CacheEntry(
                value=value,
                created_at=datetime.utcnow(),
                ttl_seconds=effective_ttl,
                key=key,
            )

        self.logger.debug("memory_cache_set", key=key, ttl=effective_ttl)
        return True

    async def delete(self, key: str) -> bool:
        """Delete from memory cache"""
        full_key = self._generate_key(key)

        async with self._lock:
            if full_key in self._cache:
                del self._cache[full_key]
                return True
        return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete matching keys"""
        import fnmatch

        full_pattern = self._generate_key(pattern)
        deleted = 0

        async with self._lock:
            keys_to_delete = [
                k for k in self._cache.keys()
                if fnmatch.fnmatch(k, full_pattern)
            ]
            for key in keys_to_delete:
                del self._cache[key]
                deleted += 1

        return deleted

    async def exists(self, key: str) -> bool:
        """Check if key exists and is not expired"""
        full_key = self._generate_key(key)

        async with self._lock:
            if full_key in self._cache:
                entry = self._cache[full_key]
                if not entry.is_expired:
                    return True
                del self._cache[full_key]
        return False

    async def get_ttl(self, key: str) -> int:
        """Get remaining TTL"""
        full_key = self._generate_key(key)

        async with self._lock:
            if full_key in self._cache:
                return int(self._cache[full_key].ttl_remaining)
        return 0

    async def cleanup_expired(self) -> int:
        """Remove all expired entries"""
        expired = 0

        async with self._lock:
            keys_to_delete = [
                k for k, v in self._cache.items()
                if v.is_expired
            ]
            for key in keys_to_delete:
                del self._cache[key]
                expired += 1

        if expired:
            self.logger.info("memory_cache_cleanup", expired_count=expired)

        return expired
