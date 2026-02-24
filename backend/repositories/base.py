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


