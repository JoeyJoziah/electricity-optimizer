"""
Repository Pattern Implementations

Data access layer for the Electricity Optimizer API.
"""

from repositories.base import (
    BaseRepository,
    CachedRepository,
    RepositoryError,
    NotFoundError,
    DuplicateError,
    ValidationError,
)

from repositories.price_repository import PriceRepository
from repositories.user_repository import UserRepository
from repositories.supplier_repository import SupplierRepository

__all__ = [
    # Base classes and exceptions
    "BaseRepository",
    "CachedRepository",
    "RepositoryError",
    "NotFoundError",
    "DuplicateError",
    "ValidationError",
    # Repository implementations
    "PriceRepository",
    "UserRepository",
    "SupplierRepository",
]
