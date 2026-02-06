"""
Data Models

Pydantic models for the Electricity Optimizer API.
"""

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

__all__ = [
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
