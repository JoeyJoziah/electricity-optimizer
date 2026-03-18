"""
Distributed Tracing Middleware

Lightweight request tracing that:
- Generates a unique trace/request ID per request (UUID4), or re-uses the
  caller-supplied ``X-Request-ID`` header when present (validated as safe ASCII).
- Binds the trace ID to structlog's contextvars so it appears automatically
  in every log record emitted during the request lifetime.
- Returns the trace ID in the ``X-Request-ID`` response header so clients can
  correlate their own traces with backend logs.

Pure ASGI implementation — does not buffer responses, safe for SSE and
streaming endpoints.
"""

import re
import uuid

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

logger = structlog.get_logger(__name__)

# Only allow safe ASCII tokens as caller-supplied request IDs (max 64 chars)
_SAFE_REQUEST_ID = re.compile(r"^[\w\-]{1,64}$")


class TracingMiddleware:
    """Inject a request-scoped trace ID into every log record and response.

    Pure ASGI middleware — no BaseHTTPMiddleware overhead, no response buffering.

    Middleware ordering note
    -----------------------
    Register this middleware *last* in add_middleware() calls so it executes
    first (LIFO), propagating the trace_id context variable to all downstream
    middleware and handlers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract and validate caller-supplied request ID
        headers = dict(scope.get("headers", []))
        raw_id = headers.get(b"x-request-id", b"").decode("latin-1", errors="replace")
        if raw_id and _SAFE_REQUEST_ID.match(raw_id):
            trace_id = raw_id
        else:
            trace_id = str(uuid.uuid4())

        # Store on scope state for endpoint access via request.state.trace_id
        scope.setdefault("state", {})["trace_id"] = trace_id

        # Bind to structlog context for automatic inclusion in all log records
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        async def send_with_trace_id(message: dict) -> None:
            if message.get("type") == "http.response.start":
                raw_headers = list(message.get("headers", []))
                raw_headers.append([b"x-request-id", trace_id.encode("ascii")])
                message = {**message, "headers": raw_headers}
            await send(message)

        await self.app(scope, receive, send_with_trace_id)
