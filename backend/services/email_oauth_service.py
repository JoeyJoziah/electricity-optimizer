"""
Email OAuth2 service for Gmail and Outlook integration.

Handles OAuth consent URL generation, token exchange, token refresh,
and encrypted token storage.
"""

import hashlib
import hmac
import secrets
import time
from urllib.parse import urlencode

import httpx
import structlog

from config.settings import settings
from utils.encryption import decrypt_field, encrypt_field

logger = structlog.get_logger(__name__)

_OAUTH_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Maximum age for OAuth state tokens (seconds). States older than this are
# rejected to prevent replay attacks.
_OAUTH_STATE_MAX_AGE_SECONDS = 600  # 10 minutes


# OAuth2 endpoints
GMAIL_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SCOPES = "https://www.googleapis.com/auth/gmail.readonly"

OUTLOOK_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
OUTLOOK_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
OUTLOOK_SCOPES = "https://graph.microsoft.com/Mail.Read offline_access"


def _get_redirect_uri() -> str:
    """Build the OAuth redirect callback URI."""
    base = settings.oauth_redirect_base_url.rstrip("/")
    return f"{base}/api/v1/connections/email/callback"


def _get_oauth_signing_key() -> bytes:
    """Resolve the OAuth state HMAC signing key.

    Prefers ``OAUTH_STATE_SECRET`` (a dedicated secret distinct from
    ``INTERNAL_API_KEY``) so a leak of one key plane (e.g. CF Worker→origin
    auth) does not compromise OAuth CSRF tokens. Falls back to
    ``INTERNAL_API_KEY`` with a one-time deprecation warning to keep
    pre-rotation deployments working.

    Secrets must be non-empty strings; the explicit ``isinstance`` check is a
    guard against ``MagicMock`` attributes leaking through in test contexts
    that patch ``settings`` wholesale.
    """
    secret = settings.oauth_state_secret
    if isinstance(secret, str) and secret:
        return secret.encode()
    fallback = settings.internal_api_key
    if isinstance(fallback, str) and fallback:
        # Pre-rotation fallback. The settings validator enforces that
        # OAUTH_STATE_SECRET is set in production, so this branch should only
        # execute in development or during a live rotation window.
        if not _get_oauth_signing_key._warned:  # type: ignore[attr-defined]
            logger.warning(
                "oauth_state_secret_missing_using_internal_api_key_fallback",
                message=(
                    "OAUTH_STATE_SECRET is not set; falling back to "
                    "INTERNAL_API_KEY for OAuth HMAC signing. "
                    "Configure a dedicated OAUTH_STATE_SECRET to maintain key isolation."
                ),
            )
            _get_oauth_signing_key._warned = True  # type: ignore[attr-defined]
        return fallback.encode()
    raise RuntimeError(
        "OAUTH_STATE_SECRET (or INTERNAL_API_KEY for legacy fallback) must be "
        "set for OAuth HMAC signing"
    )


_get_oauth_signing_key._warned = False  # type: ignore[attr-defined]


def generate_oauth_state(connection_id: str, user_id: str = "") -> str:
    """Generate a signed state parameter with timestamp for CSRF + replay protection.

    Format: {connection_id}:{user_id}:{nonce}:{timestamp}:{hmac_hex}

    The embedded timestamp allows the verifier to reject states older than
    ``_OAUTH_STATE_MAX_AGE_SECONDS`` (default 10 minutes), preventing replay
    attacks with captured OAuth callback URLs.

    The embedded *user_id* allows the callback handler to verify that the
    OAuth state belongs to the user who initiated the connection (preventing
    user A from hijacking user B's callback).
    """
    nonce = secrets.token_hex(16)
    timestamp = str(int(time.time()))
    payload = f"{connection_id}:{user_id}:{nonce}:{timestamp}"
    key = _get_oauth_signing_key()
    mac = hmac.HMAC(key, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{mac}"


def verify_oauth_state(
    state: str,
    max_age_seconds: int | None = None,
) -> tuple[str | None, str | None]:
    """Verify signed state, enforce timestamp expiry, and return (connection_id, user_id).

    Returns ``(None, None)`` if the state is malformed, the HMAC is invalid,
    or the embedded timestamp is older than *max_age_seconds* (defaults to
    ``_OAUTH_STATE_MAX_AGE_SECONDS``).

    Returns ``(connection_id, user_id)`` on success.  *user_id* may be empty
    if the state was generated without one (backwards compatibility).
    """
    if max_age_seconds is None:
        max_age_seconds = _OAUTH_STATE_MAX_AGE_SECONDS

    parts = state.split(":")
    if len(parts) != 5:
        return None, None

    connection_id, user_id, nonce, timestamp_str, received_mac = parts
    payload = f"{connection_id}:{user_id}:{nonce}:{timestamp_str}"

    key = _get_oauth_signing_key()
    expected_mac = hmac.HMAC(key, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_mac, expected_mac):
        return None, None

    # Enforce timestamp expiry
    try:
        state_time = int(timestamp_str)
    except (ValueError, OverflowError):
        logger.warning("oauth_state_invalid_timestamp", timestamp=timestamp_str)
        return None, None

    age = int(time.time()) - state_time
    if age > max_age_seconds or age < 0:
        logger.warning(
            "oauth_state_expired",
            connection_id=connection_id,
            age_seconds=age,
            max_age=max_age_seconds,
        )
        return None, None

    return connection_id, user_id


def get_gmail_consent_url(connection_id: str, user_id: str = "") -> str:
    """Generate Gmail OAuth2 consent URL."""
    state = generate_oauth_state(connection_id, user_id=user_id)
    params = {
        "client_id": settings.gmail_client_id,
        "redirect_uri": _get_redirect_uri(),
        "response_type": "code",
        "scope": GMAIL_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GMAIL_AUTH_URL}?{urlencode(params)}"


def get_outlook_consent_url(connection_id: str, user_id: str = "") -> str:
    """Generate Outlook OAuth2 consent URL."""
    state = generate_oauth_state(connection_id, user_id=user_id)
    params = {
        "client_id": settings.outlook_client_id,
        "redirect_uri": _get_redirect_uri(),
        "response_type": "code",
        "scope": OUTLOOK_SCOPES,
        "state": state,
    }
    return f"{OUTLOOK_AUTH_URL}?{urlencode(params)}"


async def exchange_gmail_code(code: str) -> dict:
    """Exchange Gmail authorization code for tokens."""
    async with httpx.AsyncClient(timeout=_OAUTH_TIMEOUT) as client:
        resp = await client.post(
            GMAIL_TOKEN_URL,
            data={
                "client_id": settings.gmail_client_id,
                "client_secret": settings.gmail_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": _get_redirect_uri(),
            },
        )
        resp.raise_for_status()
        return resp.json()


async def exchange_outlook_code(code: str) -> dict:
    """Exchange Outlook authorization code for tokens."""
    async with httpx.AsyncClient(timeout=_OAUTH_TIMEOUT) as client:
        resp = await client.post(
            OUTLOOK_TOKEN_URL,
            data={
                "client_id": settings.outlook_client_id,
                "client_secret": settings.outlook_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": _get_redirect_uri(),
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_gmail_token(refresh_token_encrypted: bytes) -> dict:
    """Refresh an expired Gmail access token."""
    refresh_token = decrypt_field(refresh_token_encrypted)
    async with httpx.AsyncClient(timeout=_OAUTH_TIMEOUT) as client:
        resp = await client.post(
            GMAIL_TOKEN_URL,
            data={
                "client_id": settings.gmail_client_id,
                "client_secret": settings.gmail_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_outlook_token(refresh_token_encrypted: bytes) -> dict:
    """Refresh an expired Outlook access token."""
    refresh_token = decrypt_field(refresh_token_encrypted)
    async with httpx.AsyncClient(timeout=_OAUTH_TIMEOUT) as client:
        resp = await client.post(
            OUTLOOK_TOKEN_URL,
            data={
                "client_id": settings.outlook_client_id,
                "client_secret": settings.outlook_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()


def encrypt_tokens(
    access_token: str, refresh_token: str | None = None
) -> tuple[bytes, bytes | None]:
    """Encrypt OAuth tokens for storage."""
    encrypted_access = encrypt_field(access_token)
    encrypted_refresh = encrypt_field(refresh_token) if refresh_token else None
    return encrypted_access, encrypted_refresh
