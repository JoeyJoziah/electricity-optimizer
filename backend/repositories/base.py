"""
Base Repository

Provides the abstract base class and common functionality for all repositories.
Implements the Repository pattern for data access abstraction.
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional, List, Any
from datetime import datetime

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


class RepositoryError(Exception):
    """Base exception for repository errors"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class NotFoundError(RepositoryError):
    """Raised when an entity is not found"""
    pass


class DuplicateError(RepositoryError):
    """Raised when a duplicate entity is detected"""
    pass


class ValidationError(RepositoryError):
    """Raised when validation fails"""
    pass


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base repository providing common CRUD operations.

    All repositories should inherit from this class and implement
    the abstract methods.
    """

    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[T]:
        """
        Retrieve an entity by its ID.

        Args:
            id: The unique identifier of the entity

        Returns:
            The entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def create(self, entity: T) -> T:
        """
        Create a new entity.

        Args:
            entity: The entity to create

        Returns:
            The created entity with any auto-generated fields populated
        """
        pass

    @abstractmethod
    async def update(self, id: str, entity: T) -> Optional[T]:
        """
        Update an existing entity.

        Args:
            id: The unique identifier of the entity
            entity: The updated entity data

        Returns:
            The updated entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def delete(self, id: str) -> bool:
        """
        Delete an entity by its ID.

        Args:
            id: The unique identifier of the entity

        Returns:
            True if deleted successfully, False if not found
        """
        pass

    @abstractmethod
    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        **filters: Any
    ) -> List[T]:
        """
        List entities with pagination and optional filtering.

        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            **filters: Additional filter criteria

        Returns:
            List of entities matching the criteria
        """
        pass

    @abstractmethod
    async def count(self, **filters: Any) -> int:
        """
        Count entities matching the given filters.

        Args:
            **filters: Filter criteria

        Returns:
            Number of matching entities
        """
        pass


class CachedRepository(BaseRepository[T]):
    """
    Repository with caching support.

    Wraps another repository and adds caching functionality.
    """

    def __init__(self, repository: BaseRepository[T], cache: Any, ttl: int = 300):
        """
        Initialize cached repository.

        Args:
            repository: The underlying repository
            cache: Cache client (e.g., Redis)
            ttl: Cache time-to-live in seconds
        """
        self._repository = repository
        self._cache = cache
        self._ttl = ttl

    def _cache_key(self, *args: Any) -> str:
        """Generate a cache key from arguments"""
        return f"{self.__class__.__name__}:{':'.join(str(a) for a in args)}"

    async def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if self._cache:
            return await self._cache.get(key)
        return None

    async def _set_in_cache(self, key: str, value: Any) -> None:
        """Set value in cache"""
        if self._cache:
            await self._cache.set(key, value, ex=self._ttl)

    async def _invalidate_cache(self, *keys: str) -> None:
        """Invalidate cache entries"""
        if self._cache:
            for key in keys:
                await self._cache.delete(key)

    async def get_by_id(self, id: str) -> Optional[T]:
        """Get entity by ID with caching"""
        cache_key = self._cache_key("id", id)

        # Try cache first
        cached = await self._get_from_cache(cache_key)
        if cached:
            return cached

        # Fall back to repository
        entity = await self._repository.get_by_id(id)

        # Cache the result
        if entity:
            await self._set_in_cache(cache_key, entity)

        return entity

    async def create(self, entity: T) -> T:
        """Create entity and update cache"""
        created = await self._repository.create(entity)
        cache_key = self._cache_key("id", created.id)
        await self._set_in_cache(cache_key, created)
        return created

    async def update(self, id: str, entity: T) -> Optional[T]:
        """Update entity and invalidate cache"""
        updated = await self._repository.update(id, entity)
        if updated:
            cache_key = self._cache_key("id", id)
            await self._invalidate_cache(cache_key)
            await self._set_in_cache(cache_key, updated)
        return updated

    async def delete(self, id: str) -> bool:
        """Delete entity and invalidate cache"""
        result = await self._repository.delete(id)
        if result:
            cache_key = self._cache_key("id", id)
            await self._invalidate_cache(cache_key)
        return result

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        **filters: Any
    ) -> List[T]:
        """List entities (not cached by default)"""
        return await self._repository.list(page, page_size, **filters)

    async def count(self, **filters: Any) -> int:
        """Count entities"""
        return await self._repository.count(**filters)
