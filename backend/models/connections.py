"""
Connection Feature Pydantic Models

Request/response schemas for the Connection feature, which allows paid-tier
users to link utility accounts via three mechanisms:

  - direct:        account number + consent (AES-256-GCM encrypted at rest)
  - email_import:  OAuth/IMAP redirect for Gmail or Outlook bill parsing
  - manual_upload: manual file upload stub (e.g., PDF bill)
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enums (expressed as Literal types to stay Pydantic-native)
# ---------------------------------------------------------------------------

ConnectionType = Literal[
    "direct", "email_import", "manual_upload", "portal_scrape", "utilityapi"
]
ConnectionStatus = Literal["active", "pending", "error", "disconnected"]
EmailProvider = Literal["gmail", "outlook"]


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class CreateDirectConnectionRequest(BaseModel):
    """Request to create a direct (account-number) connection to a supplier."""

    supplier_id: UUID
    account_number: str = Field(..., min_length=4, max_length=30)
    meter_number: str | None = Field(default=None, max_length=30)
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

    label: str | None = Field(default=None, max_length=100)
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
    supplier_id: str | None = None
    supplier_name: str | None = None
    status: ConnectionStatus = "active"
    account_number_masked: str | None = None
    meter_number_masked: str | None = None
    email_provider: str | None = None
    label: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_sync_at: datetime | None = None
    last_sync_error: str | None = None
    current_rate: float | None = None
    utilityapi_meter_count: int = 0
    stripe_subscription_item_id: str | None = None


class UpdateConnectionRequest(BaseModel):
    """Request body for PATCH /connections/{connection_id}."""

    label: str | None = Field(default=None, max_length=100)


class EmailConnectionInitResponse(BaseModel):
    """Response returned when an email-import connection is started."""

    connection_id: str
    redirect_url: str
    provider: str


class ConnectionListResponse(BaseModel):
    """Paginated list of connections for the authenticated user."""

    connections: list[ConnectionResponse]
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
    raw_label: str | None = None


class ExtractedRateListResponse(BaseModel):
    """Paginated list of extracted rates for a connection."""

    rates: list[ExtractedRateResponse]
    total: int
    page: int
    page_size: int
    pages: int


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
    detected_supplier: str | None = None
    detected_rate_per_kwh: float | None = None
    detected_billing_period_start: str | None = None
    detected_billing_period_end: str | None = None
    detected_total_kwh: float | None = None
    detected_total_amount: float | None = None
    parse_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BillUploadListResponse(BaseModel):
    """List of bill uploads for a connection."""

    uploads: list[BillUploadResponse]
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
    last_sync_at: datetime | None = None
    last_sync_error: str | None = None
    next_sync_at: datetime | None = None
    sync_frequency_hours: int = 24


class SyncResultResponse(BaseModel):
    """
    Result of a triggered sync operation.

    Returned by POST /connections/{id}/sync.
    """

    connection_id: str
    success: bool
    new_rates_found: int = 0
    error: str | None = None
    synced_at: datetime


class AuthorizationCallbackResponse(BaseModel):
    """
    Response returned by GET /connections/direct/callback after a successful
    UtilityAPI authorization callback has been processed.
    """

    connection_id: str
    status: str  # 'active' | 'error'
    message: str


# ---------------------------------------------------------------------------
# Email Scan Response (Phase 1 extraction wiring)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 3: Portal Scrape Models
# ---------------------------------------------------------------------------


class CreatePortalConnectionRequest(BaseModel):
    """Request to create a portal-scrape connection with encrypted credentials."""

    supplier_id: UUID
    portal_username: str = Field(..., min_length=1, max_length=255)
    portal_password: str = Field(..., min_length=1, max_length=255)
    portal_login_url: str | None = Field(default=None, max_length=1000)
    consent_given: bool

    @field_validator("consent_given")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent is required to store portal credentials")
        return v


class PortalConnectionResponse(BaseModel):
    """Serialised representation of a portal-scrape connection (password never returned)."""

    connection_id: str
    supplier_id: str
    portal_username: str
    portal_login_url: str | None = None
    portal_scrape_status: str = "pending"
    portal_last_scraped_at: datetime | None = None


class PortalScrapeResponse(BaseModel):
    """Result of a manual or scheduled portal scrape."""

    connection_id: str
    status: str  # 'success', 'failed', 'in_progress'
    rates_extracted: int = 0
    error: str | None = None
    scraped_at: datetime | None = None


class EmailScanResponse(BaseModel):
    """
    Response returned by POST /connections/email/{connection_id}/scan.

    Includes extraction summary counts alongside the raw bill metadata list.
    """

    connection_id: str
    provider: str
    total_emails_scanned: int
    utility_bills_found: int
    rates_extracted: int = 0
    attachments_parsed: int = 0
    bills: list[dict] = Field(default_factory=list)
