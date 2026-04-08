"""
API Dependencies

FastAPI dependency injection for database, services, and authentication.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

# Re-export auth dependencies from neon_auth module.
from auth.neon_auth import (  # noqa: F401
    SessionData,
    get_current_user,
    get_current_user_optional,
)
from config.database import db_manager
from config.settings import settings

# API Key header for service-to-service auth
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# =============================================================================
# Database Dependencies
# =============================================================================


async def get_db_session() -> AsyncGenerator:
    """
    Get async database session.

    Yields:
        AsyncSession for database operations (None if DB not available)
    """
    async with db_manager.get_pg_session() as session:
        yield session


async def get_redis():
    """
    Get Redis client.

    Returns:
        Redis client instance (None if not available)
    """
    return await db_manager.get_redis_client()


# =============================================================================
# Authentication Dependencies
# =============================================================================


async def verify_api_key(api_key: str | None = Depends(api_key_header)) -> bool:
    """
    Verify API key for service-to-service authentication.

    Args:
        api_key: API key from X-API-Key header

    Returns:
        True if valid

    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required")

    # Validate against a dedicated API key (never reuse the JWT signing secret)
    if not settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key authentication not configured",
        )

    # Use constant-time comparison to prevent timing attacks
    import hmac

    if not hmac.compare_digest(api_key, settings.internal_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return True


# =============================================================================
# Authorization Dependencies
# =============================================================================


# Tier ordering for require_tier comparisons
_TIER_ORDER: dict[str, int] = {"free": 0, "pro": 1, "business": 2}

# In-memory tier cache with LRU eviction (single-worker safe, bounded TTL).
# Capped at 10,000 entries to prevent unbounded memory growth (19-P1-3).
_TIER_CACHE_MAX_SIZE = 10_000
_tier_cache: dict[str, tuple[str, float]] = {}
_TIER_CACHE_TTL = 30  # seconds


async def _get_user_tier(user_id: str, db) -> str:
    """Get user tier with Redis cache (30s TTL), in-memory fallback."""
    import time

    cache_key = f"tier:{user_id}"

    # Check Redis first
    redis = db_manager.redis_client
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return cached.decode() if isinstance(cached, bytes) else cached
        except Exception:
            pass

    # Check in-memory fallback
    now = time.time()
    if cache_key in _tier_cache:
        tier, expires = _tier_cache[cache_key]
        if now < expires:
            return tier

    # Cache miss — query DB
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT subscription_tier FROM public.users WHERE id = :id"),
        {"id": user_id},
    )
    user_tier = result.scalar_one_or_none() or "free"

    # Store in Redis
    if redis:
        try:
            await redis.set(cache_key, user_tier, ex=_TIER_CACHE_TTL)
        except Exception:
            pass

    # Store in memory (bounded by same TTL).
    # Evict oldest entries when at capacity to prevent unbounded growth (19-P1-3).
    if len(_tier_cache) >= _TIER_CACHE_MAX_SIZE:
        # Evict ~10% of the oldest entries by expiry time
        entries_sorted = sorted(_tier_cache.items(), key=lambda kv: kv[1][1])
        for stale_key, _ in entries_sorted[: _TIER_CACHE_MAX_SIZE // 10]:
            _tier_cache.pop(stale_key, None)
    _tier_cache[cache_key] = (user_tier, now + _TIER_CACHE_TTL)

    return user_tier


async def invalidate_tier_cache(user_id: str) -> None:
    """Invalidate tier cache on subscription change (call from Stripe webhook)."""
    cache_key = f"tier:{user_id}"
    _tier_cache.pop(cache_key, None)
    redis = db_manager.redis_client
    if redis:
        try:
            await redis.delete(cache_key)
        except Exception:
            pass


@lru_cache(maxsize=8)
def require_tier(min_tier: str):
    """
    Factory for tier-gating dependencies.

    Args:
        min_tier: Minimum subscription tier required ('free', 'pro', or 'business').

    Returns:
        Dependency function that checks the user's subscription tier.
        Returns 403 if the user's tier is below min_tier.

    Examples:
        require_tier("pro")      — allows pro + business
        require_tier("business") — allows business only
    """

    async def check_tier(
        current_user: SessionData = Depends(get_current_user),
        db=Depends(get_db_session),
    ) -> SessionData:
        user_tier = await _get_user_tier(current_user.user_id, db)
        user_level = _TIER_ORDER.get(user_tier, 0)
        required_level = _TIER_ORDER.get(min_tier, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires a {min_tier.title()} or higher subscription",
            )
        return current_user

    return check_tier


# =============================================================================
# Service Dependencies
# =============================================================================


async def get_price_service(db=Depends(get_db_session), redis=Depends(get_redis)):
    """
    Get PriceService instance.

    Args:
        db: Database session
        redis: Redis client

    Returns:
        PriceService instance
    """
    from repositories.price_repository import PriceRepository
    from services.price_service import PriceService

    repo = PriceRepository(db, redis)
    return PriceService(repo, redis)


async def get_recommendation_service(db=Depends(get_db_session), redis=Depends(get_redis)):
    """
    Get RecommendationService instance.

    Args:
        db: Database session
        redis: Redis client

    Returns:
        RecommendationService instance
    """
    from repositories.price_repository import PriceRepository
    from repositories.user_repository import UserRepository
    from services.price_service import PriceService
    from services.recommendation_service import RecommendationService

    price_repo = PriceRepository(db, redis)
    user_repo = UserRepository(db)
    price_service = PriceService(price_repo, redis)

    # Wire HNSW vector store for pattern-based confidence adjustment
    vector_store = None
    try:
        from services.hnsw_vector_store import get_vector_store_singleton

        vector_store = get_vector_store_singleton()
    except Exception:
        pass  # Graceful fallback — recommendations work without vector store

    return RecommendationService(price_service, user_repo, vector_store)


async def get_observation_service(
    db=Depends(get_db_session),
):
    """
    Get ObservationService instance.

    Args:
        db: Database session

    Returns:
        ObservationService instance
    """
    from services.observation_service import ObservationService

    return ObservationService(db)


def get_hnsw_vector_store():
    """
    Get HNSWVectorStore singleton instance.

    Returns:
        HNSWVectorStore instance
    """
    from services.hnsw_vector_store import get_vector_store_singleton

    return get_vector_store_singleton()


async def get_learning_service(
    db=Depends(get_db_session),
    redis=Depends(get_redis),
):
    """
    Get LearningService instance.

    Args:
        db: Database session
        redis: Redis client

    Returns:
        LearningService instance
    """
    from services.hnsw_vector_store import get_vector_store_singleton
    from services.learning_service import LearningService
    from services.observation_service import ObservationService

    obs = ObservationService(db)
    vs = get_vector_store_singleton()
    return LearningService(obs, vs, redis)


async def get_analytics_service(db=Depends(get_db_session), redis=Depends(get_redis)):
    """
    Get AnalyticsService instance.

    Args:
        db: Database session
        redis: Redis client

    Returns:
        AnalyticsService instance
    """
    from repositories.price_repository import PriceRepository
    from services.analytics_service import AnalyticsService

    repo = PriceRepository(db, redis)
    return AnalyticsService(repo, cache=redis)
