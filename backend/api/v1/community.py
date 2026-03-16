"""
Community API

CRUD endpoints for community posts, votes, reports, and stats.
POST routes require authentication. GET routes are public.

Routes
------
POST   /community/posts              — create a new post
GET    /community/posts              — list posts with filters
PUT    /community/posts/{post_id}    — edit/resubmit a flagged post (author only)
POST   /community/posts/{id}/vote    — toggle upvote
POST   /community/posts/{id}/report  — flag post for review
GET    /community/stats              — aggregated community stats
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from api.dependencies import get_current_user, get_db_session, SessionData
from services.community_service import CommunityService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/community", tags=["Community"])


# =============================================================================
# Request / response models
# =============================================================================

VALID_POST_TYPES = {"tip", "rate_report", "discussion", "review"}
VALID_UTILITY_TYPES = {
    "electricity", "natural_gas", "heating_oil", "propane",
    "community_solar", "water", "general",
}


class CreatePostRequest(BaseModel):
    """Body for POST /community/posts."""

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    utility_type: str = Field(description="Utility type")
    region: str = Field(description="Region code (e.g. 'us_ct')")
    post_type: str = Field(description="One of: tip, rate_report, discussion, review")
    rate_per_unit: Optional[float] = Field(default=None)
    rate_unit: Optional[str] = Field(default=None, max_length=10)
    supplier_name: Optional[str] = Field(default=None, max_length=200)


class EditPostRequest(BaseModel):
    """Body for PUT /community/posts/{post_id}."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    body: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    supplier_name: Optional[str] = Field(default=None, max_length=200)


class ReportRequest(BaseModel):
    """Body for POST /community/posts/{id}/report."""

    reason: Optional[str] = Field(default=None, max_length=500)


# =============================================================================
# POST /community/posts
# =============================================================================


@router.post("/posts", status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: CreatePostRequest,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new community post."""
    if payload.post_type not in VALID_POST_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid post_type. Must be one of: {sorted(VALID_POST_TYPES)}",
        )
    if payload.utility_type not in VALID_UTILITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid utility_type. Must be one of: {sorted(VALID_UTILITY_TYPES)}",
        )

    service = CommunityService()
    post = await service.create_post(
        db=db,
        user_id=current_user.user_id,
        data={
            "title": payload.title,
            "body": payload.body,
            "utility_type": payload.utility_type,
            "region": payload.region,
            "post_type": payload.post_type,
            "rate_per_unit": payload.rate_per_unit,
            "rate_unit": payload.rate_unit,
            "supplier_name": payload.supplier_name,
        },
        agent_service=None,  # Moderation auto-clears if no agent available
    )
    return post


# =============================================================================
# GET /community/posts
# =============================================================================


@router.get("/posts")
async def list_posts(
    region: str = Query(description="Region code"),
    utility_type: str = Query(description="Utility type"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
):
    """List community posts filtered by region and utility type."""
    service = CommunityService()
    result = await service.list_posts(
        db=db,
        region=region,
        utility_type=utility_type,
        page=page,
        per_page=per_page,
    )
    # Service returns {items, total, page, per_page, pages}; alias items → posts
    return {
        "posts": result.get("items", []),
        "total": result.get("total", 0),
        "page": result.get("page", page),
        "per_page": result.get("per_page", per_page),
        "pages": result.get("pages", 1),
    }


# =============================================================================
# PUT /community/posts/{post_id}
# =============================================================================


@router.put("/posts/{post_id}")
async def edit_post(
    post_id: str,
    payload: EditPostRequest,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Edit and resubmit a flagged post (author only)."""
    service = CommunityService()
    data = {}
    if payload.title is not None:
        data["title"] = payload.title
    if payload.body is not None:
        data["body"] = payload.body
    if payload.supplier_name is not None:
        data["supplier_name"] = payload.supplier_name

    result = await service.edit_and_resubmit(
        db=db,
        user_id=current_user.user_id,
        post_id=post_id,
        data=data,
        agent_service=None,  # Moderation auto-clears if no agent available
    )
    return result


# =============================================================================
# POST /community/posts/{post_id}/vote
# =============================================================================


@router.post("/posts/{post_id}/vote")
async def toggle_vote(
    post_id: str,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Toggle upvote on a post."""
    service = CommunityService()
    # Returns {"voted": bool, "upvote_count": int} in a single DB round-trip
    return await service.toggle_vote(
        db=db,
        user_id=current_user.user_id,
        post_id=post_id,
    )


# =============================================================================
# POST /community/posts/{post_id}/report
# =============================================================================


@router.post("/posts/{post_id}/report")
async def report_post(
    post_id: str,
    payload: ReportRequest = ReportRequest(),
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Report a post for review."""
    service = CommunityService()
    await service.report_post(
        db=db,
        user_id=current_user.user_id,
        post_id=post_id,
        reason=payload.reason,
    )
    return {"status": "reported"}


# =============================================================================
# GET /community/stats
# =============================================================================


@router.get("/stats")
async def community_stats(
    region: str = Query(description="Region code"),
    db: AsyncSession = Depends(get_db_session),
):
    """Get aggregated community stats for a region."""
    service = CommunityService()
    stats = await service.get_stats(db=db, region=region)
    return stats
