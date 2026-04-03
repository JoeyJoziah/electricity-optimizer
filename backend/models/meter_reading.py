"""
Meter Reading Models

Pydantic models for interval-level electricity usage data ingested from
Arcadia, UtilityAPI, manual entry, or portal scraping.  Supports single-
record creation and efficient batch ingestion (up to 1 000 readings per
request).
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums (expressed as Literal types to stay Pydantic-native)
# ---------------------------------------------------------------------------

MeterSource = Literal["arcadia", "utilityapi", "manual", "portal"]


# ---------------------------------------------------------------------------
# Domain Model
# ---------------------------------------------------------------------------


class MeterReading(BaseModel):
    """Full representation of a single meter reading record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    connection_id: UUID | None = None
    reading_time: datetime
    kwh: Decimal
    interval_minutes: int = 60
    source: MeterSource
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class MeterReadingCreate(BaseModel):
    """Request body for creating a single meter reading."""

    reading_time: datetime
    kwh: Decimal = Field(..., ge=Decimal("0"))
    interval_minutes: int = Field(default=60, ge=1)
    source: MeterSource
    connection_id: UUID | None = None


class MeterReadingBatch(BaseModel):
    """Request body for bulk-inserting meter readings (1–1 000 per call)."""

    readings: list[MeterReadingCreate] = Field(..., min_length=1, max_length=1000)
