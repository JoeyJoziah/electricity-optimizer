"""
Repository Pattern Implementations

Data access layer for the Electricity Optimizer API.
"""

from repositories.base import (
    BaseRepository,
    RepositoryError,
    NotFoundError,
    DuplicateError,
    ValidationError,
)

from repositories.price_repository import PriceRepository
from repositories.user_repository import UserRepository
from repositories.supplier_repository import SupplierRepository
from repositories.forecast_observation_repository import ForecastObservationRepository

__all__ = [
    # Base classes and exceptions
    "BaseRepository",
    "RepositoryError",
    "NotFoundError",
    "DuplicateError",
    "ValidationError",
    # Repository implementations
    "PriceRepository",
    "UserRepository",
    "SupplierRepository",
    "ForecastObservationRepository",
]
