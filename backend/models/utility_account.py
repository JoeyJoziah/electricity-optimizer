"""
Utility Account Models

Pydantic models for user utility account management.
Links users to their utility providers (electricity, gas, etc.)
for personalized rate comparisons.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from models.utility import UtilityType


class UtilityAccount(BaseModel):
    """Full utility account model matching DB columns."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    utility_type: UtilityType
    region: str = Field(..., min_length=2, max_length=50)
    provider_name: str = Field(..., min_length=1, max_length=200)
    account_number_encrypted: bytes | None = None
    is_primary: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UtilityAccountCreate(BaseModel):
    """Request body for creating a utility account."""

    model_config = ConfigDict(use_enum_values=True)

    utility_type: UtilityType
    region: str = Field(..., min_length=2, max_length=50)
    provider_name: str = Field(..., min_length=1, max_length=200)
    account_number: str | None = Field(None, max_length=100)
    is_primary: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class UtilityAccountUpdate(BaseModel):
    """Partial update for a utility account. All fields optional."""

    model_config = ConfigDict(use_enum_values=True)

    provider_name: str | None = Field(None, min_length=1, max_length=200)
    account_number: str | None = Field(None, max_length=100)
    is_primary: bool | None = None
    metadata: dict[str, Any] | None = None


class UtilityAccountResponse(BaseModel):
    """API response — excludes encrypted fields."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str
    user_id: str
    utility_type: str
    region: str
    provider_name: str
    is_primary: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
