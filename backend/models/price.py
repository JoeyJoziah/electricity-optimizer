"""
Price Data Models

Pydantic models for electricity price data with validation.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, List
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, ConfigDict


class PriceRegion(str, Enum):
    """Supported pricing regions"""
    UK = "uk"
    GERMANY = "germany"
    FRANCE = "france"
    SPAIN = "spain"
    ITALY = "italy"
    NETHERLANDS = "netherlands"
    BELGIUM = "belgium"
    US_CA = "us_ca"
    US_TX = "us_tx"
    US_NY = "us_ny"
    US_FL = "us_fl"
    AUSTRALIA = "australia"
    JAPAN = "japan"


class PriceUnit(str, Enum):
    """Price unit types"""
    KWH = "kwh"
    MWH = "mwh"


class EnergySource(str, Enum):
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
        from_attributes=True,
        json_encoders={Decimal: str},
        use_enum_values=True
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    region: PriceRegion
    supplier: str = Field(..., min_length=1, max_length=200)
    price_per_kwh: Decimal = Field(..., ge=Decimal("0"))
    timestamp: datetime
    currency: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")

    # Optional fields
    unit: PriceUnit = Field(default=PriceUnit.KWH)
    is_peak: Optional[bool] = None
    carbon_intensity: Optional[float] = Field(default=None, ge=0)
    energy_source: Optional[EnergySource] = None
    tariff_name: Optional[str] = None

    # Price breakdown (optional)
    energy_cost: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    network_cost: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    taxes: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    levies: Optional[Decimal] = Field(default=None, ge=Decimal("0"))

    # Metadata
    source_api: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
            return v.replace(tzinfo=timezone.utc)
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
        from_attributes=True,
        json_encoders={Decimal: str},
        use_enum_values=True
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    region: PriceRegion
    generated_at: datetime
    horizon_hours: int = Field(..., ge=1, le=168)  # Max 1 week
    prices: List[Price] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)

    # Model metadata
    model_version: Optional[str] = None
    source_api: Optional[str] = None

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at_has_timezone(cls, v: datetime) -> datetime:
        """Ensure generated_at has timezone info"""
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


# =============================================================================
# API Response Schemas
# =============================================================================


class PriceResponse(BaseModel):
    """Response schema for single price"""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str}
    )

    ticker: str
    current_price: Decimal
    currency: str
    region: str
    supplier: str
    updated_at: datetime

    # Optional details
    is_peak: Optional[bool] = None
    carbon_intensity: Optional[float] = None
    price_change_24h: Optional[Decimal] = None


class PriceListResponse(BaseModel):
    """Response schema for paginated price list"""

    prices: List[PriceResponse]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        """Calculate total pages"""
        return (self.total + self.page_size - 1) // self.page_size


class PriceHistoryResponse(BaseModel):
    """Response schema for price history"""

    region: str
    supplier: Optional[str] = None
    start_date: datetime
    end_date: datetime
    prices: List[Price]
    average_price: Optional[Decimal] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None


class PriceForecastResponse(BaseModel):
    """Response schema for price forecast"""

    region: str
    forecast: PriceForecast
    generated_at: datetime
    horizon_hours: int
    confidence: float


class PriceComparisonResponse(BaseModel):
    """Response schema for supplier price comparison"""

    region: str
    timestamp: datetime
    suppliers: List[PriceResponse]
    cheapest_supplier: str
    cheapest_price: Decimal
    average_price: Decimal
