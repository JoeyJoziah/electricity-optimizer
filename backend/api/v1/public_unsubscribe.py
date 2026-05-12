"""
Public Unsubscribe Endpoint

GET /api/v1/public/unsubscribe?uid=<user_id>&tok=<hmac_token>

CAN-SPAM one-click unsubscribe for drip emails.  No session auth required;
security comes from the HMAC token tied to the user_id and signed with
settings.internal_api_key.  Tokens do not expire — a legitimate unsubscribe
link should always work, even for old emails.

On success the endpoint redirects to a confirmation page on the frontend
so the user sees friendly feedback.
"""

import hashlib
import hmac

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from config.settings import get_settings

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/public/unsubscribe", tags=["Unsubscribe"])

_settings = get_settings()


def _make_unsubscribe_token(user_id: str, secret: str) -> str:
    """Return a 32-char hex HMAC-SHA256 token for the given user_id."""
    return hmac.new(
        secret.encode(),
        user_id.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def _verify_token(user_id: str, tok: str, secret: str) -> bool:
    expected = _make_unsubscribe_token(user_id, secret)
    return hmac.compare_digest(expected, tok)


@router.get("", summary="One-click drip email unsubscribe")
async def unsubscribe(
    uid: str = Query(..., description="User ID"),
    tok: str = Query(..., description="HMAC verification token"),
    db: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    secret = _settings.internal_api_key or ""
    if not secret:
        logger.error("unsubscribe_no_secret")
        raise HTTPException(status_code=500, detail="Service misconfigured")

    if not _verify_token(uid, tok, secret):
        logger.warning("unsubscribe_invalid_token", user_id=uid)
        raise HTTPException(status_code=400, detail="Invalid unsubscribe link")

    result = await db.execute(
        text("""
            UPDATE user_drip_state
            SET unsubscribed_at = NOW(), updated_at = NOW()
            WHERE user_id = :uid
              AND unsubscribed_at IS NULL
            RETURNING user_id
        """),
        {"uid": uid},
    )
    updated = result.fetchone()
    await db.commit()

    if updated:
        logger.info("drip_unsubscribed", user_id=uid)
    else:
        logger.debug("drip_unsubscribe_noop", user_id=uid)

    return RedirectResponse(
        url="https://rateshift.app/unsubscribed",
        status_code=302,
    )
