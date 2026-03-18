"""
Feedback API

Endpoint for the in-app feedback widget (TASK-GROWTH-004).  Authenticated
users can submit feedback items (bugs, feature requests, or general comments)
which are stored in the ``feedback`` table for the support team to review.

Routes
------
POST /api/v1/feedback  — create a feedback entry (requires auth)
"""

from typing import Any, Dict, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import SessionData, get_current_user, get_db_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/feedback", tags=["Feedback"])

FeedbackType = Literal["bug", "feature", "general"]


# =============================================================================
# Request / response models
# =============================================================================


class CreateFeedbackRequest(BaseModel):
    """Body for POST /feedback."""

    type: FeedbackType = Field(
        description="Feedback category: 'bug', 'feature', or 'general'",
    )
    message: str = Field(
        min_length=10,
        max_length=5000,
        description="Feedback content (10–5000 characters)",
    )


class FeedbackResponse(BaseModel):
    """Response returned after successful feedback submission."""

    id: str
    type: str
    status: str
    created_at: str


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback",
    response_description="The newly created feedback entry",
    response_model=FeedbackResponse,
)
async def create_feedback(
    body: CreateFeedbackRequest,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Store a feedback item submitted by the authenticated user.

    The feedback is inserted into the ``feedback`` table with status ``new``
    and returned to the caller so the UI can confirm receipt.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    result = await db.execute(
        text("""
            INSERT INTO feedback (user_id, type, message, status)
            VALUES (:user_id, :type, :message, 'new')
            RETURNING id, type, status, created_at
            """),
        {
            "user_id": current_user.user_id,
            "type": body.type,
            "message": body.message,
        },
    )
    row = result.fetchone()
    await db.commit()

    logger.info(
        "feedback_created",
        user_id=current_user.user_id,
        feedback_type=body.type,
        feedback_id=str(row.id),
    )

    return {
        "id": str(row.id),
        "type": row.type,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
    }
