"""
Internal drip-processor endpoints.

POST /drip/enroll  — enroll a new user and send welcome email; called by Better Auth hook.
POST /drip/process — run Day-2 and Day-7 batches; called daily by drip-processor GHA.

Inherits router-level verify_api_key dependency from the parent internal router.
"""

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from services.drip_service import DripService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/drip", tags=["internal-drip"])


class EnrollRequest(BaseModel):
    user_id: str
    email: EmailStr
    name: str | None = None


@router.post("/enroll")
async def enroll_user(
    req: EnrollRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Enroll a newly-created user in the drip sequence and fire the welcome email.

    Called by the Better Auth databaseHooks.user.create.after hook immediately
    after signup. Idempotent — safe to call multiple times for the same user_id.
    """
    svc = DripService(db)
    sent = await svc.enroll_user(
        user_id=req.user_id,
        email=str(req.email),
        name=req.name,
    )
    return {"enrolled": True, "welcome_sent": sent}


@router.post("/process")
async def process_drip_batches(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Run the Day-2 and Day-7 drip batches atomically.

    Called daily by the drip-processor GHA cron (09:00 UTC).

    Returns per-batch summary counts. Non-zero ``errors`` should trigger a
    Sentry alert when the batch error rate exceeds DISPATCH_ERROR_RATE_THRESHOLD.
    """
    svc = DripService(db)

    day2 = await svc.process_day2_batch()
    day7 = await svc.process_day7_batch()

    total_errors = day2["errors"] + day7["errors"]
    total_sent = day2["sent_a"] + day2["sent_b"] + day7["sent"]
    total_attempted = day2["total"] + day7["total"]

    logger.info(
        "drip_process_complete",
        day2=day2,
        day7=day7,
        total_sent=total_sent,
        total_errors=total_errors,
    )

    return {
        "day2": day2,
        "day7": day7,
        "summary": {
            "total_attempted": total_attempted,
            "total_sent": total_sent,
            "total_errors": total_errors,
        },
    }
