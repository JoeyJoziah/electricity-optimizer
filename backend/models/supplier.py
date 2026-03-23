"""
Supplier Data Models

Pydantic models for energy supplier data with validation.
Supports multi-utility types and multi-region suppliers.
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from models.utility import UtilityType


class TariffType(StrEnum):
    """Types of electricity tariffs"""

    FIXED = "fixed"
    VARIABLE = "variable"
    TIME_OF_USE = "time_of_use"
    PREPAID = "prepaid"
    GREEN = "green"
    AGILE = "agile"


class ContractLength(StrEnum):
    """Contract length options"""

    MONTHLY = "monthly"
    ANNUAL = "annual"
    TWO_YEAR = "two_year"
    THREE_YEAR = "three_year"
    ROLLING = "rolling"


class SupplierContact(BaseModel):
    """Contact information for a supplier"""

    model_config = ConfigDict(from_attributes=True)

    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = None
    support_hours: str | None = None
    address: str | None = None


class Tariff(BaseModel):
    """
    Electricity tariff model.

    Represents a specific tariff offered by a supplier.
    """

    model_config = ConfigDict(
        from_attributes=True, json_encoders={Decimal: str}, use_enum_values=True
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    supplier_id: str
    name: str = Field(..., min_length=1, max_length=200)
    type: TariffType
    utility_type: UtilityType = Field(default=UtilityType.ELECTRICITY)

    # Pricing
    base_rate: Decimal = Field(..., ge=Decimal("0"))
    unit_rate: Decimal = Field(..., ge=Decimal("0"))
    standing_charge: Decimal = Field(..., ge=Decimal("0"))

    # Time-of-use rates (optional)
    peak_rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    off_peak_rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    peak_hours_start: int | None = Field(default=None, ge=0, le=23)
    peak_hours_end: int | None = Field(default=None, ge=0, le=23)

    # Contract details
    contract_length: ContractLength = ContractLength.ROLLING
    exit_fee: Decimal | None = Field(default=None, ge=Decimal("0"))
    minimum_usage: Decimal | None = Field(default=None, ge=Decimal("0"))

    # Green energy
    green_energy_percentage: int = Field(default=0, ge=0, le=100)
    renewable_sources: list[str] = Field(default_factory=list)

    # Availability
    is_available: bool = True
    available_regions: list[str] = Field(default_factory=list)
    available_from: datetime | None = None
    available_until: datetime | None = None

    # Metadata
    description: str | None = None
    terms_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Supplier(BaseModel):
    """
    Electricity supplier model.

    Represents an energy supplier/provider.
    """

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(..., min_length=1, max_length=200)
    regions: list[str] = Field(..., min_length=1)
    tariff_types: list[str] = Field(..., min_length=1)
    utility_types: list[UtilityType] = Field(default_factory=lambda: [UtilityType.ELECTRICITY])

    # API integration
    api_available: bool = False
    api_name: str | None = None

    # Contact info
    contact: SupplierContact | None = None

    # Rating and reviews
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)

    # Green credentials
    green_energy_provider: bool = False
    carbon_neutral: bool = False
    average_renewable_percentage: int | None = Field(default=None, ge=0, le=100)

    # Business info
    established_year: int | None = Field(default=None, ge=1900)
    customer_count: int | None = Field(default=None, ge=0)

    # Metadata
    logo_url: str | None = None
    description: str | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        """Ensure name is not just whitespace"""
        if not v.strip():
            raise ValueError("Name cannot be empty or whitespace only")
        return v.strip()

    @field_validator("regions")
    @classmethod
    def validate_regions_not_empty(cls, v: list[str]) -> list[str]:
        """Ensure at least one region is specified"""
        if not v:
            raise ValueError("At least one region must be specified")
        return [r.lower() for r in v]


# =============================================================================
# API Response Schemas
# =============================================================================


class SupplierResponse(BaseModel):
    """Response schema for supplier"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    regions: list[str]
    tariff_types: list[str]
    api_available: bool
    rating: float | None = None
    green_energy_provider: bool
    is_active: bool


class SupplierDetailResponse(BaseModel):
    """Detailed response schema for supplier"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    regions: list[str]
    tariff_types: list[str]
    api_available: bool
    contact: SupplierContact | None = None
    rating: float | None = None
    review_count: int | None = None
    green_energy_provider: bool
    carbon_neutral: bool
    average_renewable_percentage: int | None = None
    description: str | None = None
    logo_url: str | None = None
    is_active: bool


class SupplierListResponse(BaseModel):
    """Response schema for supplier list"""

    suppliers: list[SupplierResponse]
    total: int
    page: int
    page_size: int


class TariffResponse(BaseModel):
    """Response schema for tariff"""

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})

    id: str
    supplier_id: str
    name: str
    type: TariffType
    unit_rate: Decimal
    standing_charge: Decimal
    green_energy_percentage: int
    contract_length: ContractLength
    is_available: bool


class TariffListResponse(BaseModel):
    """Response schema for tariff list"""

    supplier_id: str
    supplier_name: str
    tariffs: list[TariffResponse]
    total: int
