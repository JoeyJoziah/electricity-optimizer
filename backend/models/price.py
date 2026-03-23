"""
Price Data Models

Pydantic models for energy price data with validation.
Supports electricity, natural gas, heating oil, propane, and community solar.
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.region import Region
from models.utility import PriceUnit, UtilityType

# Backward-compatible alias
PriceRegion = Region


class EnergySource(StrEnum):
    """Energy source types"""

    RENEWABLE = "renewable"
    FOSSIL = "fossil"
    NUCLEAR = "nuclear"
    MIXED = "mixed"


class Price(BaseModel):
    """
    Electricity price data model.

    Represents a single price point for electricity at a specific
    time, region, and supplier.
    """

    model_config = ConfigDict(
        from_attributes=True, json_encoders={Decimal: str}, use_enum_values=True
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    region: PriceRegion
    supplier: str = Field(..., min_length=1, max_length=200)
    price_per_kwh: Decimal = Field(..., ge=Decimal("0"))
    timestamp: datetime
    currency: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")

    # Utility type (defaults to electricity for backward compatibility)
    utility_type: UtilityType = Field(default=UtilityType.ELECTRICITY)

    # Optional fields
    unit: PriceUnit = Field(default=PriceUnit.KWH)
    is_peak: bool | None = None
    carbon_intensity: float | None = Field(default=None, ge=0)
    energy_source: EnergySource | None = None
    tariff_name: str | None = None

    # Price breakdown (optional)
    energy_cost: Decimal | None = Field(default=None, ge=Decimal("0"))
    network_cost: Decimal | None = Field(default=None, ge=Decimal("0"))
    taxes: Decimal | None = Field(default=None, ge=Decimal("0"))
    levies: Decimal | None = Field(default=None, ge=Decimal("0"))

    # Metadata
    source_api: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Ensure currency is uppercase and valid format"""
        if not v.isupper():
            raise ValueError("Currency must be uppercase 3-letter code")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_has_timezone(cls, v: datetime) -> datetime:
        """Ensure timestamp has timezone info"""
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

    def convert_to_kwh(self) -> "Price":
        """Convert price from MWh to kWh if needed"""
        if self.unit == PriceUnit.MWH:
            return Price(
                **{
                    **self.model_dump(exclude={"unit", "price_per_kwh"}),
                    "unit": PriceUnit.KWH,
                    "price_per_kwh": self.price_per_kwh / Decimal("1000"),
                }
            )
        return self


class PriceForecast(BaseModel):
    """
    Price forecast model.

    Contains a series of predicted prices over a forecast horizon.
    """

    model_config = ConfigDict(
        from_attributes=True, json_encoders={Decimal: str}, use_enum_values=True
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    region: PriceRegion
    generated_at: datetime
    horizon_hours: int = Field(..., ge=1, le=168)  # Max 1 week
    prices: list[Price] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)

    # Model metadata
    model_version: str | None = None
    source_api: str | None = None

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at_has_timezone(cls, v: datetime) -> datetime:
        """Ensure generated_at has timezone info"""
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v


# =============================================================================
# API Response Schemas
# =============================================================================


class PriceResponse(BaseModel):
    """Response schema for single price"""

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})

    ticker: str
    current_price: Decimal
    currency: str
    region: str
    supplier: str
    updated_at: datetime

    # Optional details
    is_peak: bool | None = None
    carbon_intensity: float | None = None
    price_change_24h: Decimal | None = None


class PriceListResponse(BaseModel):
    """Response schema for paginated price list"""

    prices: list[PriceResponse]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        """Calculate total pages"""
        return (self.total + self.page_size - 1) // self.page_size


class PriceHistoryResponse(BaseModel):
    """Response schema for price history with pagination metadata"""

    region: str
    supplier: str | None = None
    start_date: datetime
    end_date: datetime
    prices: list[Price]
    average_price: Decimal | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    source: str | None = None

    # Pagination metadata
    total: int = 0
    page: int = 1
    page_size: int = 24
    pages: int = 1


class PriceForecastResponse(BaseModel):
    """Response schema for price forecast"""

    region: str
    forecast: PriceForecast
    generated_at: datetime
    horizon_hours: int
    confidence: float
    source: str | None = None


class PriceComparisonResponse(BaseModel):
    """Response schema for supplier price comparison"""

    region: str
    timestamp: datetime
    suppliers: list[PriceResponse]
    cheapest_supplier: str
    cheapest_price: Decimal
    average_price: Decimal
    source: str | None = None
