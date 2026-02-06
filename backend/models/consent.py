"""
Consent Data Models

Pydantic models for GDPR consent tracking and data portability.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, ConfigDict


class ConsentPurpose(str, Enum):
    """Valid consent purposes for GDPR compliance"""
    DATA_PROCESSING = "data_processing"
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    PRICE_ALERTS = "price_alerts"
    OPTIMIZATION = "optimization"
    THIRD_PARTY_SHARING = "third_party_sharing"


class ConsentRecord(BaseModel):
    """
    Model for tracking user consent records.

    Compliant with GDPR Article 6 (Lawful basis for processing)
    and Article 7 (Conditions for consent).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = Field(..., description="User ID this consent belongs to")
    purpose: str = Field(..., description="Purpose of data processing")
    consent_given: bool = Field(..., description="Whether consent was given or withdrawn")
    timestamp: datetime = Field(..., description="When consent was recorded")
    ip_address: str = Field(..., description="IP address for audit trail")
    user_agent: str = Field(..., description="Browser/client for audit trail")

    # Optional fields
    consent_version: Optional[str] = Field(default="1.0", description="Version of consent policy")
    withdrawal_timestamp: Optional[datetime] = Field(default=None, description="When consent was withdrawn")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")

    @field_validator("timestamp", "withdrawal_timestamp", mode="before")
    @classmethod
    def ensure_timezone(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Ensure timestamps have timezone info"""
        if v is not None and isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class ConsentRequest(BaseModel):
    """Request schema for recording consent"""

    purpose: str = Field(..., description="Purpose for which consent is given/withdrawn")
    consent_given: bool = Field(..., description="True to give consent, False to withdraw")
    consent_version: Optional[str] = Field(default="1.0", description="Version of consent policy")


class ConsentResponse(BaseModel):
    """Response schema after recording consent"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    purpose: str
    consent_given: bool
    timestamp: datetime
    message: str


class ConsentHistoryResponse(BaseModel):
    """Response schema for consent history"""

    user_id: str
    consents: List[ConsentRecord]
    total_count: int


class ConsentStatusResponse(BaseModel):
    """Response schema for current consent status"""

    user_id: str
    consents: Dict[str, bool]
    last_updated: Optional[datetime] = None


class UserDataExport(BaseModel):
    """
    Complete user data export for GDPR Article 15 (Right of access)
    and Article 20 (Right to data portability).

    All user data in machine-readable JSON format.
    """

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    export_timestamp: datetime
    export_format_version: str = Field(default="1.0")

    # User profile data
    profile_data: Dict[str, Any]

    # User preferences
    preferences_data: Dict[str, Any]

    # Consent history
    consent_history: List[Dict[str, Any]]

    # Price alerts and notifications
    price_alerts: List[Dict[str, Any]]

    # Recommendations received
    recommendations: List[Dict[str, Any]]

    # Activity logs
    activity_logs: List[Dict[str, Any]]

    # Supplier switching history (if applicable)
    switching_history: Optional[List[Dict[str, Any]]] = None


class DataDeletionRequest(BaseModel):
    """Request schema for GDPR data deletion (Right to Erasure)"""

    confirmation: bool = Field(..., description="User confirms deletion request")
    reason: Optional[str] = Field(default=None, description="Optional reason for deletion")
    retain_anonymized: bool = Field(
        default=False,
        description="Whether to retain anonymized data for analytics"
    )


class DataDeletionResponse(BaseModel):
    """Response schema after data deletion"""

    success: bool
    user_id: str
    deleted_at: datetime
    deleted_categories: List[str]
    message: str
    deletion_log_id: str


class DeletionLog(BaseModel):
    """
    Immutable log of data deletion for audit purposes.

    Required for demonstrating GDPR compliance.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = Field(..., description="ID of user whose data was deleted")
    deleted_at: datetime = Field(..., description="When deletion occurred")
    deleted_by: str = Field(..., description="Who initiated deletion (user or admin)")
    deletion_type: str = Field(..., description="full, partial, or anonymization")
    ip_address: str = Field(..., description="IP address of requestor")
    user_agent: str = Field(..., description="Client of requestor")
    data_categories_deleted: List[str] = Field(..., description="Categories of data deleted")
    legal_basis: Optional[str] = Field(default="user_request", description="Legal basis for deletion")
    metadata: Optional[Dict[str, Any]] = Field(default=None)

    @field_validator("deleted_at", mode="before")
    @classmethod
    def ensure_timezone(cls, v: datetime) -> datetime:
        """Ensure timestamp has timezone info"""
        if v is not None and isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v
