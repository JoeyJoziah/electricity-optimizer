"""
Supplier Data Models

Pydantic models for electricity supplier data with validation.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, List
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, HttpUrl, EmailStr, ConfigDict


class TariffType(str, Enum):
    """Types of electricity tariffs"""
    FIXED = "fixed"
    VARIABLE = "variable"
    TIME_OF_USE = "time_of_use"
    PREPAID = "prepaid"
    GREEN = "green"
    AGILE = "agile"


class ContractLength(str, Enum):
    """Contract length options"""
    MONTHLY = "monthly"
    ANNUAL = "annual"
    TWO_YEAR = "two_year"
    THREE_YEAR = "three_year"
    ROLLING = "rolling"


class SupplierContact(BaseModel):
    """Contact information for a supplier"""

    model_config = ConfigDict(from_attributes=True)

    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    website: Optional[str] = None
    support_hours: Optional[str] = None
    address: Optional[str] = None


class Tariff(BaseModel):
    """
    Electricity tariff model.

    Represents a specific tariff offered by a supplier.
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str},
        use_enum_values=True
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    supplier_id: str
    name: str = Field(..., min_length=1, max_length=200)
    type: TariffType

    # Pricing
    base_rate: Decimal = Field(..., ge=Decimal("0"))
    unit_rate: Decimal = Field(..., ge=Decimal("0"))
    standing_charge: Decimal = Field(..., ge=Decimal("0"))

    # Time-of-use rates (optional)
    peak_rate: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    off_peak_rate: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    peak_hours_start: Optional[int] = Field(default=None, ge=0, le=23)
    peak_hours_end: Optional[int] = Field(default=None, ge=0, le=23)

    # Contract details
    contract_length: ContractLength = ContractLength.ROLLING
    exit_fee: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    minimum_usage: Optional[Decimal] = Field(default=None, ge=Decimal("0"))

    # Green energy
    green_energy_percentage: int = Field(default=0, ge=0, le=100)
    renewable_sources: List[str] = Field(default_factory=list)

    # Availability
    is_available: bool = True
    available_regions: List[str] = Field(default_factory=list)
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None

    # Metadata
    description: Optional[str] = None
    terms_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Supplier(BaseModel):
    """
    Electricity supplier model.

    Represents an energy supplier/provider.
    """

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(..., min_length=1, max_length=200)
    regions: List[str] = Field(..., min_length=1)
    tariff_types: List[str] = Field(..., min_length=1)

    # API integration
    api_available: bool = False
    api_name: Optional[str] = None

    # Contact info
    contact: Optional[SupplierContact] = None

    # Rating and reviews
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    review_count: Optional[int] = Field(default=None, ge=0)

    # Green credentials
    green_energy_provider: bool = False
    carbon_neutral: bool = False
    average_renewable_percentage: Optional[int] = Field(default=None, ge=0, le=100)

    # Business info
    established_year: Optional[int] = Field(default=None, ge=1900)
    customer_count: Optional[int] = Field(default=None, ge=0)

    # Metadata
    logo_url: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        """Ensure name is not just whitespace"""
        if not v.strip():
            raise ValueError("Name cannot be empty or whitespace only")
        return v.strip()

    @field_validator("regions")
    @classmethod
    def validate_regions_not_empty(cls, v: List[str]) -> List[str]:
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
    regions: List[str]
    tariff_types: List[str]
    api_available: bool
    rating: Optional[float] = None
    green_energy_provider: bool
    is_active: bool


class SupplierDetailResponse(BaseModel):
    """Detailed response schema for supplier"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    regions: List[str]
    tariff_types: List[str]
    api_available: bool
    contact: Optional[SupplierContact] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    green_energy_provider: bool
    carbon_neutral: bool
    average_renewable_percentage: Optional[int] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: bool


class SupplierListResponse(BaseModel):
    """Response schema for supplier list"""

    suppliers: List[SupplierResponse]
    total: int
    page: int
    page_size: int


class TariffResponse(BaseModel):
    """Response schema for tariff"""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str}
    )

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
    tariffs: List[TariffResponse]
    total: int
