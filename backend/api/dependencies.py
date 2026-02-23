"""
API Dependencies

FastAPI dependency injection for database, services, and authentication.
"""

from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
import jwt
from jwt.exceptions import PyJWTError as JWTError
from pydantic import BaseModel

from config.settings import settings
from config.database import db_manager


# OAuth2 scheme for JWT tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# API Key header for service-to-service auth
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class TokenData(BaseModel):
    """JWT token payload data"""
    user_id: Optional[str] = None
    email: Optional[str] = None
    scopes: list = []


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


def get_supabase():
    """
    Get Supabase client.

    Returns:
        Supabase client instance (None if not available)
    """
    return db_manager.get_supabase_client()


# =============================================================================
# Authentication Dependencies
# =============================================================================


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme)
) -> Optional[TokenData]:
    """
    Get current user from JWT token (optional).

    Does not raise error if token is missing or invalid.

    Args:
        token: JWT token from Authorization header

    Returns:
        TokenData if valid token, None otherwise
    """
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        scopes: list = payload.get("scopes", [])

        if user_id is None:
            return None

        return TokenData(user_id=user_id, email=email, scopes=scopes)

    except JWTError:
        return None


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme)
) -> TokenData:
    """
    Get current user from JWT token (required).

    Raises 401 if token is missing or invalid.

    Args:
        token: JWT token from Authorization header

    Returns:
        TokenData with user information

    Raises:
        HTTPException: If token is missing or invalid
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        scopes: list = payload.get("scopes", [])

        if user_id is None:
            raise credentials_exception

        return TokenData(user_id=user_id, email=email, scopes=scopes)

    except JWTError:
        raise credentials_exception


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
        if required_scope not in token_data.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Scope '{required_scope}' required"
            )
        return token_data

    return check_scope


def require_admin():
    """
    Require admin scope.

    Returns:
        Dependency that checks for admin scope
    """
    return require_scope("admin")


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

    return RecommendationService(price_service, user_repo)


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
    from services.hnsw_vector_store import HNSWVectorStore
    return HNSWVectorStore()


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
    from services.hnsw_vector_store import HNSWVectorStore
    from services.learning_service import LearningService

    obs = ObservationService(db)
    vs = HNSWVectorStore()
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
    return AnalyticsService(repo)
