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

from api.dependencies import SessionData, get_current_user, get_db_session

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
    """Return the HMAC signing key for OAuth callback state parameters.

    Prefers ``settings.oauth_state_secret`` (dedicated key) but falls back to
    ``settings.internal_api_key`` for backward compatibility during the
    transition period (dev environments that haven't set OAUTH_STATE_SECRET yet).

    Reads settings through the package namespace so that
    ``patch("api.v1.connections.settings")`` in tests takes effect.
    """
    import api.v1.connections as _pkg

    _settings = _pkg.settings

    # Prefer the dedicated OAuth state secret.
    # Use getattr + isinstance guard so that MagicMock auto-attributes in tests
    # (which are truthy but not strings) fall through to the fallback branch.
    _oauth_secret = getattr(_settings, "oauth_state_secret", None)
    key = _oauth_secret if isinstance(_oauth_secret, str) and _oauth_secret else None

    # Fall back to internal_api_key for backward compat (dev/test only —
    # production validator in settings.py enforces OAUTH_STATE_SECRET).
    if not key:
        key = _settings.internal_api_key

    if not key:
        raise RuntimeError(
            "OAUTH_STATE_SECRET (or INTERNAL_API_KEY as fallback) must be "
            "configured to sign callback state parameters."
        )
    return key.encode("utf-8")


def sign_callback_state(connection_id: str, user_id: str) -> str:
    """
    Produce a signed state value: ``{connection_id}:{user_id}:{timestamp}:{hex_hmac}``.

    The HMAC is computed over ``{connection_id}:{user_id}:{timestamp}`` using
    OAUTH_STATE_SECRET (or INTERNAL_API_KEY as fallback) with SHA-256.  The
    callback endpoint verifies this signature and the user_id before trusting
    the connection_id.
    """
    timestamp = str(int(time.time()))
    key = _get_hmac_key()
    payload = f"{connection_id}:{user_id}:{timestamp}"
    sig = hmac.HMAC(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_callback_state(state: str) -> tuple:
    """
    Verify a signed state value and return ``(connection_id, user_id)``.

    Raises HTTPException(400) if the state is malformed, the HMAC is invalid,
    or the embedded timestamp is expired (older than OAUTH_STATE_TIMEOUT_SECONDS)
    or in the future.
    """
    parts = state.split(":")
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid callback state: expected 4 colon-separated parts.",
        )

    connection_id, user_id, timestamp_str, received_sig = parts

    key = _get_hmac_key()
    payload = f"{connection_id}:{user_id}:{timestamp_str}"
    expected_sig = hmac.HMAC(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(received_sig, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid callback state: HMAC verification failed.",
        )

    # Enforce timestamp expiry to prevent replay attacks
    try:
        state_time = int(timestamp_str)
    except (ValueError, OverflowError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid callback state: malformed timestamp.",
        )

    age = int(time.time()) - state_time
    if age > OAUTH_STATE_TIMEOUT_SECONDS or age < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid callback state: token expired or has future timestamp.",
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
