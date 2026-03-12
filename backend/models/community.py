"""
Community Data Models

Pydantic models for community posts, votes, and reports.
Supports crowdsourcing, tips, discussions, and rate reports.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict, field_validator


class PostType(str, Enum):
    """Types of community posts."""
    TIP = "tip"
    RATE_REPORT = "rate_report"
    DISCUSSION = "discussion"
    REVIEW = "review"


class CommunityUtilityType(str, Enum):
    """Utility types for community posts (includes 'general')."""
    ELECTRICITY = "electricity"
    NATURAL_GAS = "natural_gas"
    HEATING_OIL = "heating_oil"
    PROPANE = "propane"
    COMMUNITY_SOLAR = "community_solar"
    WATER = "water"
    GENERAL = "general"


class CommunityPost(BaseModel):
    """A community post (tip, rate report, discussion, or review)."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    region: str = Field(..., min_length=2, max_length=50)
    utility_type: str = Field(..., max_length=30)
    post_type: str = Field(..., max_length=20)
    title: str = Field(..., min_length=3, max_length=200)
    body: str = Field(..., min_length=10, max_length=5000)
    rate_per_unit: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    rate_unit: Optional[str] = Field(default=None, max_length=10)
    supplier_name: Optional[str] = Field(default=None, max_length=200)
    is_hidden: bool = False
    is_pending_moderation: bool = True
    hidden_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Derived fields (not stored in DB — computed via COUNT queries)
    upvote_count: int = 0
    report_count: int = 0

    @field_validator("post_type")
    @classmethod
    def validate_post_type(cls, v: str) -> str:
        valid = {"tip", "rate_report", "discussion", "review"}
        if v not in valid:
            raise ValueError(f"post_type must be one of {valid}")
        return v

    @field_validator("utility_type")
    @classmethod
    def validate_utility_type(cls, v: str) -> str:
        valid = {
            "electricity", "natural_gas", "heating_oil", "propane",
            "community_solar", "water", "general",
        }
        if v not in valid:
            raise ValueError(f"utility_type must be one of {valid}")
        return v


class CommunityPostCreate(BaseModel):
    """Schema for creating a community post."""

    title: str = Field(..., min_length=3, max_length=200)
    body: str = Field(..., min_length=10, max_length=5000)
    region: str = Field(..., min_length=2, max_length=50)
    utility_type: str = Field(..., max_length=30)
    post_type: str = Field(..., max_length=20)
    rate_per_unit: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    rate_unit: Optional[str] = Field(default=None, max_length=10)
    supplier_name: Optional[str] = Field(default=None, max_length=200)

    @field_validator("post_type")
    @classmethod
    def validate_post_type(cls, v: str) -> str:
        valid = {"tip", "rate_report", "discussion", "review"}
        if v not in valid:
            raise ValueError(f"post_type must be one of {valid}")
        return v

    @field_validator("utility_type")
    @classmethod
    def validate_utility_type(cls, v: str) -> str:
        valid = {
            "electricity", "natural_gas", "heating_oil", "propane",
            "community_solar", "water", "general",
        }
        if v not in valid:
            raise ValueError(f"utility_type must be one of {valid}")
        return v


class CommunityPostUpdate(BaseModel):
    """Schema for editing/resubmitting a flagged post."""

    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    body: Optional[str] = Field(default=None, min_length=10, max_length=5000)


class CommunityPostResponse(BaseModel):
    """Response schema for a community post."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    region: str
    utility_type: str
    post_type: str
    title: str
    body: str
    rate_per_unit: Optional[Decimal] = None
    rate_unit: Optional[str] = None
    supplier_name: Optional[str] = None
    is_hidden: bool
    is_pending_moderation: bool
    upvote_count: int = 0
    report_count: int = 0
    created_at: datetime
    updated_at: datetime


class CommunityVote(BaseModel):
    """A vote on a community post (composite PK: user_id + post_id)."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    post_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommunityReport(BaseModel):
    """A report on a community post (composite PK: user_id + post_id)."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    post_id: str
    reason: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommunityStatsResponse(BaseModel):
    """Aggregated community stats for social proof."""

    total_users: int = 0
    avg_savings_pct: Optional[float] = None
    top_tip: Optional[CommunityPostResponse] = None
    region: str
    reporting_since: Optional[datetime] = None


class PaginatedPostsResponse(BaseModel):
    """Paginated list of community posts."""

    items: list[CommunityPostResponse]
    total: int
    page: int
    per_page: int
    pages: int
