"""
Shared helpers for the Connections feature package.

Contents:
  - _UPLOADS_DIR: shared Path constant (patchable in tests via api.v1.connections._UPLOADS_DIR)
  - HMAC state signing/verification (sign_callback_state, verify_callback_state)
  - Paid-tier FastAPI dependency (require_paid_tier)

Patching note:
  Tests patch ``api.v1.connections.settings``.  All functions that read
  ``settings`` do so via a lazy ``import api.v1.connections as _pkg`` inside
  the function body so that the patched value is observed at call time.
  This avoids circular imports because ``common.py`` does not import from
  other sub-modules in this package.
"""

import hashlib
import hmac
import time
from pathlib import Path

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_db_session, SessionData

# ---------------------------------------------------------------------------
# Shared filesystem paths
# ---------------------------------------------------------------------------

#: Local upload directory used by bill_upload.py (Phase 2 — cloud in Phase 3).
#: Exposed at the package level via __init__.py so tests can patch it as
#: ``api.v1.connections._UPLOADS_DIR``.
_UPLOADS_DIR = Path("uploads")


# ---------------------------------------------------------------------------
# HMAC helpers for callback state parameter
# ---------------------------------------------------------------------------

OAUTH_STATE_TIMEOUT_SECONDS = 600  # 10 minutes


def _get_hmac_key() -> bytes:
    """Return the HMAC signing key derived from INTERNAL_API_KEY.

    Reads ``settings.internal_api_key`` through the package namespace so that
    ``patch("api.v1.connections.settings")`` in tests takes effect.
    """
    import api.v1.connections as _pkg
    _settings = _pkg.settings
    key = _settings.internal_api_key
    if not key:
        raise RuntimeError(
            "INTERNAL_API_KEY must be configured to sign callback state parameters."
        )
    return key.encode("utf-8")


def sign_callback_state(connection_id: str, user_id: str) -> str:
    """
    Produce a signed state value: ``{connection_id}:{user_id}:{timestamp}:{hex_hmac}``.

    The HMAC is computed over ``{connection_id}:{user_id}:{timestamp}`` using
    INTERNAL_API_KEY as the key with SHA-256.  The callback endpoint verifies
    this signature and the user_id before trusting the connection_id.
    """
    timestamp = str(int(time.time()))
    key = _get_hmac_key()
    payload = f"{connection_id}:{user_id}:{timestamp}"
    sig = hmac.HMAC(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_callback_state(state: str) -> tuple:
    """
    Verify a signed state value and return ``(connection_id, user_id)``.

    Raises HTTPException(400) if the state is malformed or the HMAC is invalid.
    """
    parts = state.split(":")
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid callback state: expected 4 colon-separated parts.",
        )

    connection_id, user_id, timestamp, received_sig = parts

    key = _get_hmac_key()
    payload = f"{connection_id}:{user_id}:{timestamp}"
    expected_sig = hmac.HMAC(
        key, payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(received_sig, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid callback state: HMAC verification failed.",
        )

    return connection_id, user_id


# ---------------------------------------------------------------------------
# Paid-tier gate dependency
# ---------------------------------------------------------------------------


async def require_paid_tier(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> SessionData:
    """
    Dependency that raises 403 for free-tier users.

    Queries ``public.users.subscription_tier`` for the authenticated user.
    Raises:
        HTTP 401: If the user is not authenticated (handled by get_current_user).
        HTTP 403: If the user is on the free tier or has no tier set.
    """
    result = await db.execute(
        text("SELECT subscription_tier FROM public.users WHERE id = :uid"),
        {"uid": current_user.user_id},
    )
    row = result.fetchone()
    tier = row[0] if row else None

    if tier not in ("pro", "business"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Connections require a Pro or Business subscription.",
        )
    return current_user
