"""
AI Agent API

Endpoints for the RateShift AI assistant — powered by Gemini 2.5 Flash
with Groq fallback and Composio tool integration.

Routes
------
POST   /agent/query         — SSE streaming agent response
POST   /agent/task          — submit async job for tool-heavy tasks
GET    /agent/task/{job_id} — poll async job result
GET    /agent/usage         — remaining queries today
"""

import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.dependencies import SessionData, get_current_user, get_db_session
from config.settings import settings
from services.agent_service import AgentService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])


# =============================================================================
# Request / response models
# =============================================================================


class AgentQueryRequest(BaseModel):
    """Body for POST /agent/query and /agent/task."""

    prompt: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="User prompt for the AI agent",
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description="Additional context (region, supplier override)",
    )


# =============================================================================
# Helpers
# =============================================================================


def _require_agent_enabled():
    """Raise 503 if AI agent feature is disabled."""
    if not settings.enable_ai_agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI agent is not enabled. Set ENABLE_AI_AGENT=true to activate.",
        )


async def _get_user_tier(user_id: str, db: AsyncSession) -> str:
    """Look up the user's subscription tier."""
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT subscription_tier FROM public.users WHERE id = :id"),
        {"id": user_id},
    )
    return result.scalar_one_or_none() or "free"


async def _get_user_context(user_id: str, db: AsyncSession) -> dict:
    """Build user context dict with region, supplier, tier."""
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT region, subscription_tier FROM public.users WHERE id = :id"),
        {"id": user_id},
    )
    row = result.first()
    if row:
        return {
            "region": row[0] or "Unknown",
            "tier": row[1] or "free",
            "supplier": "Unknown",
        }
    return {"region": "Unknown", "supplier": "Unknown", "tier": "free"}


# Keys that user-supplied context is allowed to set.  Everything else is
# derived from the authenticated session / database and must never be
# overridable from the request body.
_ALLOWED_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "region_override",
        "supplier_override",
        "utility_type",
        "comparison_mode",
    }
)


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/query",
    summary="Query RateShift AI (streaming)",
    response_description="Server-Sent Events stream of agent responses",
)
async def query_agent(
    body: AgentQueryRequest,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Send a prompt to RateShift AI and receive a streaming response.
    Uses Gemini 2.5 Flash with automatic Groq fallback.
    """
    _require_agent_enabled()

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    # Build context from DB — then selectively merge whitelisted user overrides.
    context = await _get_user_context(current_user.user_id, db)
    if body.context:
        for key in _ALLOWED_CONTEXT_KEYS:
            if key in body.context:
                context[key] = body.context[key]
    # Security-sensitive keys always come from the authenticated session / DB.
    context["tier"] = await _get_user_tier(current_user.user_id, db)
    context["user_id"] = current_user.user_id
    tier = context["tier"]

    # Atomic rate-limit check + increment (prevents TOCTOU race)
    service = AgentService()
    allowed, count = await service.increment_usage_atomic(current_user.user_id, tier, db)
    if not allowed:
        limit = settings.agent_pro_daily_limit if tier == "pro" else settings.agent_free_daily_limit
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily query limit reached ({count}/{limit}). Upgrade your plan for more queries.",
        )

    async def event_stream():
        async for msg in service.query_streaming(
            user_id=current_user.user_id,
            prompt=body.prompt,
            context=context,
            db=db,
        ):
            data = json.dumps(
                {
                    "role": msg.role,
                    "content": msg.content,
                    "model_used": msg.model_used,
                    "tools_used": msg.tools_used,
                    "tokens_used": msg.tokens_used,
                    "duration_ms": msg.duration_ms,
                }
            )
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"

    logger.info("agent_query_started", user_id=current_user.user_id, prompt_len=len(body.prompt))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/task",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit async agent task",
    response_description="Job ID for polling",
)
async def submit_agent_task(
    body: AgentQueryRequest,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """
    Submit a prompt as an async background task (for tool-heavy queries).
    Returns a job_id that can be polled via GET /agent/task/{job_id}.
    """
    _require_agent_enabled()

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    # Build context from DB — then selectively merge whitelisted user overrides.
    context = await _get_user_context(current_user.user_id, db)
    if body.context:
        for key in _ALLOWED_CONTEXT_KEYS:
            if key in body.context:
                context[key] = body.context[key]
    # Security-sensitive keys always come from the authenticated session / DB.
    context["tier"] = await _get_user_tier(current_user.user_id, db)
    context["user_id"] = current_user.user_id
    tier = context["tier"]

    # Atomic rate-limit check + increment (prevents TOCTOU race)
    service = AgentService()
    allowed, count = await service.increment_usage_atomic(current_user.user_id, tier, db)
    if not allowed:
        limit = settings.agent_pro_daily_limit if tier == "pro" else settings.agent_free_daily_limit
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily query limit reached ({count}/{limit}).",
        )

    job_id = await service.query_async(
        user_id=current_user.user_id,
        prompt=body.prompt,
        context=context,
        db=db,
    )

    logger.info("agent_task_submitted", user_id=current_user.user_id, job_id=job_id)
    return {"job_id": job_id}


@router.get(
    "/task/{job_id}",
    summary="Poll async task result",
    response_description="Job status and result",
)
async def get_task_result(
    job_id: uuid.UUID,
    current_user: SessionData = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Poll the result of an async agent task by job_id.
    Returns status: processing | completed | failed | not_found.
    """
    _require_agent_enabled()

    service = AgentService()
    result = await service.get_job_result(str(job_id), user_id=current_user.user_id)
    return result


@router.get(
    "/usage",
    summary="Get agent usage stats",
    response_description="Daily usage and tier limits",
)
async def get_agent_usage(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Return today's query usage, tier limit, and remaining queries.
    """
    _require_agent_enabled()

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    tier = await _get_user_tier(current_user.user_id, db)
    service = AgentService()
    return await service.get_usage(current_user.user_id, tier, db)
