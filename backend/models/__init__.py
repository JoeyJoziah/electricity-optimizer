"""
Data Models

Pydantic models for the Energy Optimizer API.
Supports electricity, natural gas, heating oil, propane, and community solar.
"""

from models.observation import (AccuracyMetrics, ForecastObservation,
                                HourlyBias, RecommendationOutcome)
from models.price import (EnergySource, Price, PriceComparisonResponse,
                          PriceForecast, PriceForecastResponse,
                          PriceHistoryResponse, PriceListResponse, PriceRegion,
                          PriceResponse, PriceUnit)
from models.region import Region
from models.regulation import (StateRegulation, StateRegulationListResponse,
                               StateRegulationResponse)
from models.supplier import (ContractLength, Supplier, SupplierContact,
                             SupplierDetailResponse, SupplierListResponse,
                             SupplierResponse, Tariff, TariffListResponse,
                             TariffResponse, TariffType)
from models.user import (User, UserCreate, UserPreferences,
                         UserPreferencesResponse, UserResponse, UserUpdate)
from models.utility import UtilityType

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
