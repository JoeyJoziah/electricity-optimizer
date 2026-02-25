"""
Connection Feature Pydantic Models

Request/response schemas for the Connection feature, which allows paid-tier
users to link utility accounts via three mechanisms:

  - direct:        account number + consent (AES-256-GCM encrypted at rest)
  - email_import:  OAuth/IMAP redirect for Gmail or Outlook bill parsing
  - manual_upload: manual file upload stub (e.g., PDF bill)
"""

from datetime import datetime, timezone
from typing import Optional, List, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums (expressed as Literal types to stay Pydantic-native)
# ---------------------------------------------------------------------------

ConnectionType = Literal["direct", "email_import", "manual_upload"]
ConnectionStatus = Literal["active", "pending", "error", "disconnected"]
EmailProvider = Literal["gmail", "outlook"]


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class CreateDirectConnectionRequest(BaseModel):
    """Request to create a direct (account-number) connection to a supplier."""

    supplier_id: UUID
    account_number: str = Field(..., min_length=4, max_length=30)
    meter_number: Optional[str] = Field(default=None, max_length=30)
    consent_given: bool

    @field_validator("account_number")
    @classmethod
    def validate_account_number(cls, v: str) -> str:
        import re
        if not re.match(r"^[A-Za-z0-9\-\s]{4,30}$", v):
            raise ValueError(
                "Account number must be 4-30 alphanumeric characters, hyphens, or spaces"
            )
        return v

    @field_validator("consent_given")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent is required to link an account")
        return v


class CreateEmailConnectionRequest(BaseModel):
    """Request to start an email-import connection (OAuth redirect)."""

    provider: EmailProvider
    consent_given: bool

    @field_validator("consent_given")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent is required to link an email account")
        return v


class CreateUploadConnectionRequest(BaseModel):
    """Request to register a manual-upload connection stub."""

    label: Optional[str] = Field(default=None, max_length=100)
    consent_given: bool

    @field_validator("consent_given")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent is required")
        return v


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class ConnectionResponse(BaseModel):
    """Serialised representation of a single user connection."""

    id: str
    user_id: str
    connection_type: ConnectionType
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    status: ConnectionStatus = "active"
    account_number_masked: Optional[str] = None
    email_provider: Optional[str] = None
    label: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class EmailConnectionInitResponse(BaseModel):
    """Response returned when an email-import connection is started."""

    connection_id: str
    redirect_url: str
    provider: str


class ConnectionListResponse(BaseModel):
    """Paginated list of connections for the authenticated user."""

    connections: List[ConnectionResponse]
    total: int


class DeleteConnectionResponse(BaseModel):
    """Confirmation of a deleted connection."""

    message: str
    connection_id: str


class ExtractedRateResponse(BaseModel):
    """A single rate extracted from a connected account (e.g., bill parse)."""

    id: str
    connection_id: str
    rate_per_kwh: float
    effective_date: datetime
    source: str  # e.g. "bill_parse", "api_pull"
    raw_label: Optional[str] = None


# ---------------------------------------------------------------------------
# Bill Upload Models (Phase 2)
# ---------------------------------------------------------------------------

ParseStatus = Literal["pending", "processing", "complete", "failed"]


class BillUploadResponse(BaseModel):
    """Serialised representation of a single bill upload record."""

    id: str
    connection_id: str
    file_name: str
    file_type: str
    file_size_bytes: int
    parse_status: ParseStatus = "pending"
    detected_supplier: Optional[str] = None
    detected_rate_per_kwh: Optional[float] = None
    detected_billing_period_start: Optional[str] = None
    detected_billing_period_end: Optional[str] = None
    detected_total_kwh: Optional[float] = None
    detected_total_amount: Optional[float] = None
    parse_error: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class BillUploadListResponse(BaseModel):
    """List of bill uploads for a connection."""

    uploads: List[BillUploadResponse]
    total: int


# ---------------------------------------------------------------------------
# Phase 4: UtilityAPI Direct Sync Models
# ---------------------------------------------------------------------------


class SyncStatusResponse(BaseModel):
    """
    Current sync health and scheduling information for a connection.

    Returned by GET /connections/{id}/sync-status.
    """

    connection_id: str
    last_sync_at: Optional[datetime] = None
    last_sync_error: Optional[str] = None
    next_sync_at: Optional[datetime] = None
    sync_frequency_hours: int = 24


class SyncResultResponse(BaseModel):
    """
    Result of a triggered sync operation.

    Returned by POST /connections/{id}/sync.
    """

    connection_id: str
    success: bool
    new_rates_found: int = 0
    error: Optional[str] = None
    synced_at: datetime


class AuthorizationCallbackResponse(BaseModel):
    """
    Response returned by GET /connections/direct/callback after a successful
    UtilityAPI authorization callback has been processed.
    """

    connection_id: str
    status: str  # 'active' | 'error'
    message: str
