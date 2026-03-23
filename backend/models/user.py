"""
User Data Models

Pydantic models for user data with validation.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from models.region import Region


class UserPreferences(BaseModel):
    """
    User preferences for notifications and automation.
    """

    model_config = ConfigDict(from_attributes=True)

    # Notification preferences
    notification_enabled: bool = True
    email_notifications: bool = True
    push_notifications: bool = False
    notification_frequency: str = Field(
        default="daily", pattern=r"^(immediate|hourly|daily|weekly)$"
    )

    # Cost preferences
    cost_threshold: Decimal | None = Field(default=None, ge=Decimal("0"))
    budget_limit_daily: Decimal | None = Field(default=None, ge=Decimal("0"))
    budget_limit_monthly: Decimal | None = Field(default=None, ge=Decimal("0"))

    # Automation preferences
    auto_switch_enabled: bool = False
    auto_switch_threshold: Decimal | None = Field(default=None, ge=Decimal("0"))

    # Supplier preferences
    preferred_suppliers: list[str] = Field(default_factory=list)
    excluded_suppliers: list[str] = Field(default_factory=list)

    # Energy preferences
    green_energy_only: bool = False
    min_renewable_percentage: int = Field(default=0, ge=0, le=100)

    # Time-of-use preferences
    peak_avoidance_enabled: bool = False
    preferred_usage_hours: list[int] = Field(default_factory=list)

    # Price alert preferences
    price_alert_enabled: bool = False
    price_alert_below: Decimal | None = Field(default=None, ge=Decimal("0"))
    price_alert_above: Decimal | None = Field(default=None, ge=Decimal("0"))
    alert_optimal_windows: bool = True


class User(BaseModel):
    """
    User model representing a platform user.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=200)
    region: str | None = Field(default=None, min_length=2, max_length=50)

    # Account status
    is_active: bool = True
    is_verified: bool = False
    email_verified: bool = False

    # Subscription (Stripe integration)
    subscription_tier: str = Field(default="free", pattern=r"^(free|pro|business)$")
    stripe_customer_id: str | None = None

    # Preferences
    preferences: dict[str, Any] = Field(default_factory=dict)

    # Current supplier info
    current_supplier: str | None = None
    current_supplier_id: str | None = None
    current_tariff: str | None = None

    # Usage data
    average_daily_kwh: Decimal | None = Field(default=None, ge=Decimal("0"))
    annual_usage_kwh: Decimal | None = Field(default=None, ge=Decimal("0"))
    household_size: int | None = Field(default=None, ge=1)
    utility_types: list[str] | None = None

    # Onboarding
    onboarding_completed: bool = False

    # GDPR compliance
    consent_given: bool = False
    consent_date: datetime | None = None
    data_processing_agreed: bool = False

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_login: datetime | None = None

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str | None) -> str | None:
        """Ensure region is a valid Region enum value (lowercase)."""
        if v is None:
            return v
        lowered = v.lower()
        try:
            Region(lowered)
        except ValueError:
            raise ValueError(
                f"Invalid region '{v}'. Must be a valid Region enum value "
                f"(e.g. 'us_ct', 'us_ny', 'uk')."
            )
        return lowered

    @field_validator("created_at", "updated_at", "last_login", "consent_date")
    @classmethod
    def validate_timestamp_has_timezone(cls, v: datetime | None) -> datetime | None:
        """Ensure timestamps have timezone info"""
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v


class UserCreate(BaseModel):
    """Schema for creating a new user.

    GDPR compliance requires explicit affirmative consent at registration time.
    Both ``consent_given`` (Article 6 lawful basis) and ``data_processing_agreed``
    (Article 7 conditions) must be ``True`` — omitting them or passing ``False``
    raises a 422 Unprocessable Entity error so callers cannot silently skip consent.
    """

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=200)
    region: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=8)

    # GDPR consent — required at registration; must be explicitly True
    consent_given: bool = Field(
        ...,
        description=(
            "User has given explicit consent to data processing "
            "(GDPR Article 6 lawful basis). Must be True to register."
        ),
    )
    data_processing_agreed: bool = Field(
        ...,
        description=(
            "User has agreed to the data processing terms "
            "(GDPR Article 7 conditions). Must be True to register."
        ),
    )

    # Optional fields
    current_supplier: str | None = None
    average_daily_kwh: Decimal | None = Field(default=None, ge=Decimal("0"))
    household_size: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_gdpr_consent(self) -> "UserCreate":
        """Reject registration if either GDPR consent field is not True.

        Silently defaulting consent to False would violate GDPR Article 7(1)
        which requires a clear affirmative act.  Callers must pass both fields
        explicitly as ``True``; passing ``False`` or omitting them is a
        client error that surfaces as HTTP 422.
        """
        if not self.consent_given:
            raise ValueError(
                "consent_given must be True — explicit GDPR consent is required "
                "to create an account (GDPR Article 6 lawful basis)."
            )
        if not self.data_processing_agreed:
            raise ValueError(
                "data_processing_agreed must be True — agreement to data processing "
                "terms is required to create an account (GDPR Article 7 conditions)."
            )
        return self


class UserUpdate(BaseModel):
    """Schema for updating user data"""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    region: str | None = Field(default=None, min_length=2, max_length=50)
    current_supplier: str | None = None
    current_tariff: str | None = None
    average_daily_kwh: Decimal | None = Field(default=None, ge=Decimal("0"))
    household_size: int | None = Field(default=None, ge=1)


class UserResponse(BaseModel):
    """Response schema for user data (excludes sensitive fields)"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    name: str
    region: str | None = None
    is_active: bool
    is_verified: bool
    current_supplier: str | None = None
    current_tariff: str | None = None
    created_at: datetime


class UserPreferencesResponse(BaseModel):
    """Response schema for user preferences"""

    user_id: str
    preferences: UserPreferences
    updated_at: datetime
