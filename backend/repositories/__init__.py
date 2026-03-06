"""
Repository Pattern Implementations

Data access layer for the Electricity Optimizer API.
"""

from repositories.base import (BaseRepository, DuplicateError, NotFoundError,
                               RepositoryError, ValidationError)
from repositories.forecast_observation_repository import \
    ForecastObservationRepository
from repositories.price_repository import PriceRepository
from repositories.supplier_repository import SupplierRepository
from repositories.user_repository import UserRepository

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
