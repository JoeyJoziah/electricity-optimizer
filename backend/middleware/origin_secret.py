"""
CF Worker Origin-Secret Middleware

Validates the X-CF-Origin-Secret header on every inbound request.
When CF_ORIGIN_SECRET is configured in the environment, any request
that arrives without the correct header is rejected with 403.

Bypassed paths (always allowed regardless of header):
- /health               — UptimeRobot probes arrive directly, not via CF
- /api/v1/webhooks/     — Stripe retries originate from Stripe IPs, not CF
- /metrics              — Prometheus scraper is internal

Design notes:
- Comparison uses hmac.compare_digest to prevent timing-side-channel leaks.
- When CF_ORIGIN_SECRET is NOT set (dev / staging without the secret), the
  middleware is a no-op so local development continues to work unchanged.
- Rejected requests return 403 (not 401) to avoid hinting that auth is
  involved — the secret is not a user credential.
"""

import hmac

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

from config.settings import get_settings

logger = structlog.get_logger(__name__)

_BYPASSED_PREFIXES = (
    "/health",
    "/api/v1/webhooks/",
    "/metrics",
)

_HEADER_NAME = "x-cf-origin-secret"


class CFOriginSecretMiddleware:
    """Reject requests lacking the correct X-CF-Origin-Secret header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        secret = get_settings().cf_origin_secret
        if not secret:
            # Secret not configured — middleware is a no-op (dev / staging)
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if any(path.startswith(p) for p in _BYPASSED_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Extract header value (ASGI headers are bytes tuples)
        header_value: str | None = None
        for name, value in scope.get("headers", []):
            if name.lower() == _HEADER_NAME.encode():
                header_value = value.decode("utf-8", errors="replace")
                break

        if header_value is None or not hmac.compare_digest(header_value, secret):
            logger.warning(
                "origin_secret_rejected",
                path=path,
                has_header=header_value is not None,
            )
            body = b'{"detail":"Forbidden"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        [b"content-type", b"application/json"],
                        [b"content-length", str(len(body)).encode()],
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
