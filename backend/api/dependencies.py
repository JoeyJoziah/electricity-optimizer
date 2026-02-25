"""
API Dependencies

FastAPI dependency injection for database, services, and authentication.
"""

from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from config.settings import settings
from config.database import db_manager

# Re-export auth dependencies from neon_auth module.
# TokenData is an alias for SessionData to maintain backward compatibility
# with existing endpoints that use `current_user: TokenData = Depends(get_current_user)`.
from auth.neon_auth import (
    get_current_user,
    get_current_user_optional,
    SessionData as TokenData,
)

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
    async with db_manager.get_timescale_session() as session:
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


async def verify_api_key(
    api_key: Optional[str] = Depends(api_key_header)
) -> bool:
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required"
        )

    # Validate against a dedicated API key (never reuse the JWT signing secret)
    if not settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key authentication not configured"
        )

    # Use constant-time comparison to prevent timing attacks
    import hmac
    if not hmac.compare_digest(api_key, settings.internal_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    return True


# =============================================================================
# Authorization Dependencies
# =============================================================================


def require_scope(required_scope: str):
    """
    Factory for scope-checking dependencies.

    Args:
        required_scope: Required scope name

    Returns:
        Dependency function that checks for the scope
    """
    async def check_scope(
        token_data: TokenData = Depends(get_current_user)
    ) -> TokenData:
        # Neon Auth sessions don't have scopes — check role instead
        if token_data.role != required_scope and token_data.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Scope '{required_scope}' required"
            )
        return token_data

    return check_scope


def require_admin():
    """
    Require admin role.

    Returns:
        Dependency that checks for admin role
    """
    return require_scope("admin")


def require_paid_tier():
    """
    Require Pro or Business subscription for premium features.

    Returns:
        Dependency function that checks for a paid subscription tier
    """
    async def check_tier(
        current_user: TokenData = Depends(get_current_user),
        db=Depends(get_db_session),
    ) -> TokenData:
        from sqlalchemy import text

        result = await db.execute(
            text("SELECT subscription_tier FROM public.users WHERE id = :id"),
            {"id": current_user.user_id},
        )
        tier = result.scalar_one_or_none()
        if tier not in ("pro", "business"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This feature requires a Pro or Business subscription",
            )
        return current_user

    return check_tier


# =============================================================================
# Service Dependencies
# =============================================================================


async def get_price_service(
    db=Depends(get_db_session),
    redis=Depends(get_redis)
):
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


async def get_recommendation_service(
    db=Depends(get_db_session),
    redis=Depends(get_redis)
):
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
    from services.observation_service import ObservationService
    from services.hnsw_vector_store import get_vector_store_singleton
    from services.learning_service import LearningService

    obs = ObservationService(db)
    vs = get_vector_store_singleton()
    return LearningService(obs, vs, redis)


async def get_analytics_service(
    db=Depends(get_db_session),
    redis=Depends(get_redis)
):
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
