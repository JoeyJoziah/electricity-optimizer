"""
Distributed Tracing Middleware

Lightweight request tracing that:
- Generates a unique trace/request ID per request (UUID4), or re-uses the
  caller-supplied ``X-Request-ID`` header when present.
- Binds the trace ID to structlog's contextvars so it appears automatically
  in every log record emitted during the request lifetime.
- Returns the trace ID in the ``X-Request-ID`` response header so clients can
  correlate their own traces with backend logs.
- Stores the trace ID on ``request.state.trace_id`` for endpoint-level access
  (e.g. activity_logs entries).

The implementation intentionally stays dependency-free — no OpenTelemetry SDK
is required.  structlog.contextvars is available in structlog >= 21.2.0 and
is already used elsewhere in this codebase.
"""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


logger = structlog.get_logger(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    """Inject a request-scoped trace ID into every log record and response.

    Middleware ordering note
    -----------------------
    Register this middleware *after* (i.e. at a lower position in the stack
    than) rate-limit and security-header middleware so the trace ID is
    available to all downstream handlers including exception handlers.

    Usage in endpoints::

        @router.get("/example")
        async def example(request: Request):
            trace_id = request.state.trace_id  # available after middleware runs
            ...
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Honour caller-supplied request ID; generate a fresh one otherwise.
        trace_id: str = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Persist on request state so endpoint code can read it directly.
        request.state.trace_id = trace_id

        # Bind to structlog context so every logger.* call in this request
        # automatically includes trace_id without manual threading.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        response: Response = await call_next(request)

        # Reflect trace ID back to the caller for client-side correlation.
        response.headers["X-Request-ID"] = trace_id

        return response
