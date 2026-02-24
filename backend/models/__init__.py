"""
Data Models

Pydantic models for the Energy Optimizer API.
Supports electricity, natural gas, heating oil, propane, and community solar.
"""

from models.region import Region
from models.utility import UtilityType

from models.price import (
    Price,
    PriceRegion,
    PriceUnit,
    EnergySource,
    PriceForecast,
    PriceResponse,
    PriceListResponse,
    PriceHistoryResponse,
    PriceForecastResponse,
    PriceComparisonResponse,
)

from models.user import (
    User,
    UserCreate,
    UserUpdate,
    UserResponse,
    UserPreferences,
    UserPreferencesResponse,
)

from models.supplier import (
    Supplier,
    SupplierContact,
    SupplierResponse,
    SupplierDetailResponse,
    SupplierListResponse,
    Tariff,
    TariffType,
    TariffResponse,
    TariffListResponse,
    ContractLength,
)

from models.regulation import (
    StateRegulation,
    StateRegulationResponse,
    StateRegulationListResponse,
)

from models.observation import (
    ForecastObservation,
    RecommendationOutcome,
    AccuracyMetrics,
    HourlyBias,
)

__all__ = [
    # Region and utility types
    "Region",
    "UtilityType",
    # Price models
    "Price",
    "PriceRegion",
    "PriceUnit",
    "EnergySource",
    "PriceForecast",
    "PriceResponse",
    "PriceListResponse",
    "PriceHistoryResponse",
    "PriceForecastResponse",
    "PriceComparisonResponse",
    # User models
    "User",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserPreferences",
    "UserPreferencesResponse",
    # Supplier models
    "Supplier",
    "SupplierContact",
    "SupplierResponse",
    "SupplierDetailResponse",
    "SupplierListResponse",
    "Tariff",
    "TariffType",
    "TariffResponse",
    "TariffListResponse",
    "ContractLength",
]
