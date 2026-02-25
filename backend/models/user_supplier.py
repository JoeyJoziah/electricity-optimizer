"""
User-Supplier Pydantic Models

Request/response schemas for supplier selection and account linking.
"""

import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SetSupplierRequest(BaseModel):
    """Request to set the user's current supplier."""
    supplier_id: UUID


class LinkAccountRequest(BaseModel):
    """Request to link a utility account to a supplier."""
    supplier_id: UUID
    account_number: str = Field(..., min_length=4, max_length=30)
    meter_number: Optional[str] = Field(default=None, max_length=30)
    service_zip: Optional[str] = Field(default=None, max_length=10)
    account_nickname: Optional[str] = Field(default=None, max_length=100)
    consent_given: bool

    @field_validator("account_number")
    @classmethod
    def validate_account_number(cls, v: str) -> str:
        if not re.match(r"^[A-Za-z0-9\-\s]{4,30}$", v):
            raise ValueError("Account number must be 4-30 alphanumeric characters, hyphens, or spaces")
        return v

    @field_validator("meter_number")
    @classmethod
    def validate_meter_number(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.match(r"^[A-Za-z0-9\-\s]{1,30}$", v):
            raise ValueError("Meter number must be 1-30 alphanumeric characters, hyphens, or spaces")
        return v

    @field_validator("consent_given")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent is required to link an account")
        return v


class UserSupplierResponse(BaseModel):
    """Response for user's current supplier."""
    supplier_id: str
    supplier_name: str
    regions: list[str] = []
    rating: Optional[float] = None
    green_energy: bool = False
    website: Optional[str] = None


class LinkedAccountResponse(BaseModel):
    """Response for a linked supplier account (masked)."""
    supplier_id: str
    supplier_name: str
    account_number_masked: Optional[str] = None
    meter_number_masked: Optional[str] = None
    service_zip: Optional[str] = None
    account_nickname: Optional[str] = None
    is_primary: bool = True
    verified_at: Optional[str] = None
    created_at: str
