"""
Email OAuth2 service for Gmail and Outlook integration.

Handles OAuth consent URL generation, token exchange, token refresh,
and encrypted token storage.
"""
import hashlib
import hmac
import secrets
import time
from typing import Optional, Tuple
from urllib.parse import urlencode

import httpx

from config.settings import settings
from utils.encryption import encrypt_field, decrypt_field


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


def generate_oauth_state(connection_id: str) -> str:
    """Generate a signed state parameter for CSRF protection.

    Format: {connection_id}:{nonce}:{hmac_hex}
    """
    nonce = secrets.token_hex(16)
    payload = f"{connection_id}:{nonce}"
    key = (settings.internal_api_key or settings.jwt_secret).encode()
    mac = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{mac}"


def verify_oauth_state(state: str) -> Optional[str]:
    """Verify signed state and return connection_id, or None if invalid."""
    parts = state.split(":")
    if len(parts) != 3:
        return None
    connection_id, nonce, received_mac = parts
    payload = f"{connection_id}:{nonce}"
    key = (settings.internal_api_key or settings.jwt_secret).encode()
    expected_mac = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_mac, expected_mac):
        return None
    return connection_id


def get_gmail_consent_url(connection_id: str) -> str:
    """Generate Gmail OAuth2 consent URL."""
    state = generate_oauth_state(connection_id)
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


def get_outlook_consent_url(connection_id: str) -> str:
    """Generate Outlook OAuth2 consent URL."""
    state = generate_oauth_state(connection_id)
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
    async with httpx.AsyncClient() as client:
        resp = await client.post(GMAIL_TOKEN_URL, data={
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": _get_redirect_uri(),
        })
        resp.raise_for_status()
        return resp.json()


async def exchange_outlook_code(code: str) -> dict:
    """Exchange Outlook authorization code for tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(OUTLOOK_TOKEN_URL, data={
            "client_id": settings.outlook_client_id,
            "client_secret": settings.outlook_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": _get_redirect_uri(),
        })
        resp.raise_for_status()
        return resp.json()


async def refresh_gmail_token(refresh_token_encrypted: bytes) -> dict:
    """Refresh an expired Gmail access token."""
    refresh_token = decrypt_field(refresh_token_encrypted)
    async with httpx.AsyncClient() as client:
        resp = await client.post(GMAIL_TOKEN_URL, data={
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        return resp.json()


async def refresh_outlook_token(refresh_token_encrypted: bytes) -> dict:
    """Refresh an expired Outlook access token."""
    refresh_token = decrypt_field(refresh_token_encrypted)
    async with httpx.AsyncClient() as client:
        resp = await client.post(OUTLOOK_TOKEN_URL, data={
            "client_id": settings.outlook_client_id,
            "client_secret": settings.outlook_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        return resp.json()


def encrypt_tokens(access_token: str, refresh_token: Optional[str] = None) -> Tuple[bytes, Optional[bytes]]:
    """Encrypt OAuth tokens for storage."""
    encrypted_access = encrypt_field(access_token)
    encrypted_refresh = encrypt_field(refresh_token) if refresh_token else None
    return encrypted_access, encrypted_refresh
