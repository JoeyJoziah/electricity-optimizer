"""
Consent Data Models

Pydantic models for GDPR consent tracking and data portability.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConsentPurpose(StrEnum):
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
    user_id: str | None = Field(
        default=None,
        description="User ID this consent belongs to (nullable for GDPR SET NULL)",
    )
    purpose: str = Field(..., description="Purpose of data processing")
    consent_given: bool = Field(
        ..., description="Whether consent was given or withdrawn"
    )
    timestamp: datetime = Field(..., description="When consent was recorded")
    ip_address: str = Field(..., description="IP address for audit trail")
    user_agent: str = Field(..., description="Browser/client for audit trail")

    # Optional fields
    consent_version: str | None = Field(
        default="1.0", description="Version of consent policy"
    )
    withdrawal_timestamp: datetime | None = Field(
        default=None, description="When consent was withdrawn"
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Additional metadata"
    )

    @field_validator("timestamp", "withdrawal_timestamp", mode="before")
    @classmethod
    def ensure_timezone(cls, v: datetime | None) -> datetime | None:
        """Ensure timestamps have timezone info"""
        if v is not None and isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v


class ConsentRequest(BaseModel):
    """Request schema for recording consent"""

    purpose: str = Field(
        ..., description="Purpose for which consent is given/withdrawn"
    )
    consent_given: bool = Field(
        ..., description="True to give consent, False to withdraw"
    )
    consent_version: str | None = Field(
        default="1.0", description="Version of consent policy"
    )


class ConsentResponse(BaseModel):
    """Response schema after recording consent"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None = None
    purpose: str
    consent_given: bool
    timestamp: datetime
    message: str


class ConsentHistoryResponse(BaseModel):
    """Response schema for consent history"""

    user_id: str
    consents: list[ConsentRecord]
    total_count: int


class ConsentStatusResponse(BaseModel):
    """Response schema for current consent status"""

    user_id: str
    consents: dict[str, bool]
    last_updated: datetime | None = None


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
    profile_data: dict[str, Any]

    # User preferences
    preferences_data: dict[str, Any]

    # Consent history
    consent_history: list[dict[str, Any]]

    # Price alerts and notifications
    price_alerts: list[dict[str, Any]]

    # Recommendations received
    recommendations: list[dict[str, Any]]

    # Activity logs
    activity_logs: list[dict[str, Any]]

    # Supplier switching history (if applicable)
    switching_history: list[dict[str, Any]] | None = None


class DataDeletionRequest(BaseModel):
    """Request schema for GDPR data deletion (Right to Erasure)"""

    confirmation: bool = Field(..., description="User confirms deletion request")
    reason: str | None = Field(default=None, description="Optional reason for deletion")
    retain_anonymized: bool = Field(
        default=False, description="Whether to retain anonymized data for analytics"
    )


class DataDeletionResponse(BaseModel):
    """Response schema after data deletion"""

    success: bool
    user_id: str
    deleted_at: datetime
    deleted_categories: list[str]
    message: str
    deletion_log_id: str


class DeletionLog(BaseModel):
    """
    Immutable log of data deletion for audit purposes.

    Required for demonstrating GDPR compliance.

    user_id is nullable: after a GDPR Article 17 deletion the FK on
    deletion_logs.user_id fires ON DELETE SET NULL, preserving the audit log
    entry while the user row is removed.  A NULL user_id in the log is
    therefore expected and must be handled by callers.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str | None = Field(
        default=None,
        description="ID of user whose data was deleted (NULL after account erasure)",
    )
    deleted_at: datetime = Field(..., description="When deletion occurred")
    deleted_by: str = Field(..., description="Who initiated deletion (user or admin)")
    deletion_type: str = Field(..., description="full, partial, or anonymization")
    ip_address: str = Field(..., description="IP address of requestor")
    user_agent: str = Field(..., description="Client of requestor")
    data_categories_deleted: list[str] = Field(
        ..., description="Categories of data deleted"
    )
    legal_basis: str | None = Field(
        default="user_request", description="Legal basis for deletion"
    )
    metadata: dict[str, Any] | None = Field(default=None)

    @field_validator("deleted_at", mode="before")
    @classmethod
    def ensure_timezone(cls, v: datetime) -> datetime:
        """Ensure timestamp has timezone info"""
        if v is not None and isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v
