"""
Data Models

Pydantic models for the Energy Optimizer API.
Supports electricity, natural gas, heating oil, propane, and community solar.
"""

from models.available_plan import AvailablePlan, AvailablePlanResponse
from models.community import (CommunityPost, CommunityPostCreate,
                              CommunityPostResponse, CommunityPostUpdate,
                              CommunityReport, CommunityStatsResponse,
                              CommunityUtilityType, CommunityVote,
                              PaginatedPostsResponse, PostType)
from models.meter_reading import (MeterReading, MeterReadingBatch,
                                  MeterReadingCreate)
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
from models.switch_audit_log import SwitchAuditLog, SwitchAuditLogResponse
from models.switch_execution import SwitchExecution, SwitchExecutionResponse
from models.user import (User, UserCreate, UserPreferences,
                         UserPreferencesResponse, UserResponse, UserUpdate)
from models.user_agent_settings import (UserAgentSettings,
                                        UserAgentSettingsResponse,
                                        UserAgentSettingsUpdate)
from models.user_plan import UserPlan, UserPlanCreate, UserPlanResponse
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
    # Community models
    "PostType",
    "CommunityUtilityType",
    "CommunityPost",
    "CommunityPostCreate",
    "CommunityPostUpdate",
    "CommunityPostResponse",
    "CommunityVote",
    "CommunityReport",
    "CommunityStatsResponse",
    "PaginatedPostsResponse",
    # Auto-switcher models
    "UserPlan",
    "UserPlanCreate",
    "UserPlanResponse",
    "AvailablePlan",
    "AvailablePlanResponse",
    "MeterReading",
    "MeterReadingCreate",
    "MeterReadingBatch",
    "SwitchAuditLog",
    "SwitchAuditLogResponse",
    "SwitchExecution",
    "SwitchExecutionResponse",
    "UserAgentSettings",
    "UserAgentSettingsUpdate",
    "UserAgentSettingsResponse",
]
