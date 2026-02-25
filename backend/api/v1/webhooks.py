"""
GitHub Webhook Endpoint

Receives and verifies GitHub webhook events using HMAC-SHA256 signature
verification. Logs events and can trigger downstream actions (e.g., Notion sync).
"""

import hashlib
import hmac

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)

router = APIRouter()


class WebhookResponse(BaseModel):
    """Response for webhook processing."""
    received: bool
    event: str


def verify_github_signature(payload: bytes, signature_header: str, secret: str) -> None:
    """
    Verify the X-Hub-Signature-256 header from GitHub.

    Args:
        payload: Raw request body bytes.
        signature_header: Value of the X-Hub-Signature-256 header.
        secret: The webhook secret shared with GitHub.

    Raises:
        ValueError: If signature is missing or invalid.
    """
    if not signature_header:
        raise ValueError("Missing X-Hub-Signature-256 header")

    # GitHub sends "sha256=<hex digest>"
    if not signature_header.startswith("sha256="):
        raise ValueError("Invalid signature format")

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    received = signature_header[7:]  # strip "sha256=" prefix

    if not hmac.compare_digest(expected, received):
        raise ValueError("Invalid webhook signature")


@router.post(
    "/github",
    response_model=WebhookResponse,
    summary="Handle GitHub webhooks",
    responses={
        200: {"description": "Webhook processed"},
        400: {"description": "Invalid signature"},
        503: {"description": "Webhook secret not configured"},
    },
)
async def handle_github_webhook(request: Request):
    """
    Receive GitHub webhook events.

    Verifies the payload signature using the shared GITHUB_WEBHOOK_SECRET,
    then logs the event. No authentication required — security is handled
    via HMAC signature verification.
    """
    secret = settings.github_webhook_secret
    if not secret:
        logger.error("github_webhook_secret_not_configured")
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    payload = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    try:
        verify_github_signature(payload, signature, secret)
    except ValueError as e:
        logger.warning("github_webhook_signature_invalid", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    event_type = request.headers.get("X-GitHub-Event", "unknown")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")

    logger.info(
        "github_webhook_received",
        event_type=event_type,
        delivery_id=delivery_id,
    )

    return WebhookResponse(received=True, event=event_type)
