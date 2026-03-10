"""
Electricity Optimizer — Application Factory

Centralises FastAPI app construction so that the entry-point (main.py) and
test harnesses can obtain a fully-configured application instance without
importing side-effectful module-level code.

Public API
----------
create_app() -> tuple[FastAPI, UserRateLimiter]
    Build and return the application together with the rate-limiter singleton
    so callers can wire Redis in after startup and reset state between tests.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import structlog
import time

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from starlette.types import ASGIApp, Receive, Scope, Send

from config.settings import settings
from config.database import db_manager

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Logging configuration
#
# Executed once when this module is first imported.  Structured logging is
# configured here rather than in main.py so that the factory can be imported
# by tests and workers without duplicating the setup call.
# ---------------------------------------------------------------------------

if settings.is_production:
    _log_processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]
else:
    _log_processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ]

structlog.configure(
    processors=_log_processors,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)


# ---------------------------------------------------------------------------
# Inline ASGI middleware classes
#
# These are defined here (not in a separate middleware module) because they
# carry application-level constants (MAX_REQUEST_BODY_BYTES, etc.) and are
# tightly coupled to app construction.  Keeping them in the factory avoids
# circular imports while still making them importable for tests via
# ``from app_factory import RequestBodySizeLimitMiddleware``.
# ---------------------------------------------------------------------------

MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024  # 1 MB
REQUEST_TIMEOUT_SECONDS = 30


class RequestBodySizeLimitMiddleware:
    """Reject requests whose body exceeds the configured size limit.

    Pure ASGI middleware — checks Content-Length first (fast path) then
    enforces the limit on the actual body stream for chunked transfers.
    The ``/connections/upload`` endpoint is granted a 10 MB allowance.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # Per-path size limit
        max_bytes = MAX_REQUEST_BODY_BYTES
        if path.endswith("/connections/upload"):
            max_bytes = 10 * 1024 * 1024  # 10 MB for bill uploads

        # Content-Length fast path: reject before reading any body
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        content_length_value: bytes | None = None
        for header_name, header_value in headers:
            if header_name == b"content-length":
                content_length_value = header_value
                break

        if content_length_value is not None:
            try:
                if int(content_length_value) > max_bytes:
                    await self._send_413(send, max_bytes)
                    return
            except (ValueError, TypeError):
                pass

        # Chunked encoding path: wrap receive to count bytes
        method: str = scope.get("method", "")
        if method in ("POST", "PUT", "PATCH") and content_length_value is None:
            bytes_received = 0

            async def counting_receive() -> dict:
                nonlocal bytes_received
                message = await receive()
                if message.get("type") == "http.request":
                    bytes_received += len(message.get("body", b""))
                    if bytes_received > max_bytes:
                        await self._send_413(send, max_bytes)
                        return {"type": "http.request", "body": b"", "more_body": False}
                return message

            await self.app(scope, counting_receive, send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _send_413(send: Send, max_bytes: int) -> None:
        """Send a 413 Payload Too Large response via raw ASGI messages."""
        max_mb = max_bytes // (1024 * 1024)
        body = json.dumps(
            {"detail": f"Request body too large. Maximum size is {max_mb} MB."}
        ).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
            ],
        })
        await send({"type": "http.response.body", "body": body})


class RequestTimeoutMiddleware:
    """Enforce a per-request wall-clock timeout.

    Excluded paths (no timeout):
    - ``/prices/stream`` — SSE streaming
    - ``/api/v1/internal/`` — batch jobs with different latency profiles

    Pure ASGI middleware — does not buffer responses, so it is safe alongside
    SSE and other long-lived streaming endpoints.
    """

    TIMEOUT_EXCLUDED_PREFIXES = ("/api/v1/internal/", "/api/v1/agent/")

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # SSE endpoint must never be subject to a hard timeout
        if path.endswith("/prices/stream"):
            await self.app(scope, receive, send)
            return

        # Internal batch jobs (scraping, syncing) need longer execution times
        if any(path.startswith(p) for p in self.TIMEOUT_EXCLUDED_PREFIXES):
            await self.app(scope, receive, send)
            return

        try:
            await asyncio.wait_for(
                self.app(scope, receive, send),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            body = json.dumps({"detail": "Request timed out"}).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 504,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                ],
            })
            await send({"type": "http.response.body", "body": body})


# ---------------------------------------------------------------------------
# create_app
# ---------------------------------------------------------------------------


def create_app() -> tuple[FastAPI, "UserRateLimiter"]:
    """Construct and return a fully-configured FastAPI application.

    Returns
    -------
    tuple[FastAPI, UserRateLimiter]
        ``(app, rate_limiter)`` — the rate-limiter is returned separately so
        that callers can wire in Redis after the application has started and
        reset state between tests without reaching into middleware internals.
    """
    from middleware.rate_limiter import RateLimitMiddleware, UserRateLimiter
    from middleware.security_headers import SecurityHeadersMiddleware
    from middleware.tracing import TracingMiddleware

    # ------------------------------------------------------------------
    # Rate limiter — created before the app so the lifespan closure can
    # capture it via a nonlocal reference.
    # ------------------------------------------------------------------
    app_rate_limiter = UserRateLimiter()

    # ------------------------------------------------------------------
    # Lifespan
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifecycle management."""
        logger.info("application_starting", environment=settings.environment)

        try:
            await db_manager.initialize()
            logger.info("database_connections_initialized")

            # Instrument the SQLAlchemy engine for tracing once it is
            # available.  No-op when OTEL_ENABLED is false.
            if settings.otel_enabled and db_manager.timescale_engine is not None:
                try:
                    from observability import instrument_sqlalchemy_engine

                    instrument_sqlalchemy_engine(db_manager.timescale_engine)
                except Exception as _sa_exc:
                    logger.warning("otel_sqlalchemy_wire_failed", error=str(_sa_exc))
        except Exception as e:
            logger.error("database_init_failed", error=str(e))
            logger.warning(
                "continuing_without_full_db", environment=settings.environment
            )

        # Wire Redis into the rate limiter for distributed rate limiting.
        # Skipped in the test environment to prevent cross-test state leakage.
        if settings.environment != "test":
            try:
                redis = await db_manager.get_redis_client()
                if redis:
                    app_rate_limiter.redis = redis
                    logger.info("rate_limiter_redis_wired")
                else:
                    logger.warning(
                        "rate_limiter_redis_unavailable",
                        fallback="in-memory",
                        detail="Redis client returned None; rate limiting will use in-memory store (not shared across workers)",
                    )
            except Exception as e:
                logger.warning(
                    "rate_limiter_redis_wire_failed",
                    error=str(e),
                    fallback="in-memory",
                    detail="Rate limiting will use in-memory store (not shared across workers)",
                )

        # Initialise Sentry if configured (lazy import to reduce startup time)
        if settings.sentry_dsn:
            try:
                import sentry_sdk
                from sentry_sdk.integrations.fastapi import FastApiIntegration

                sentry_sdk.init(
                    dsn=settings.sentry_dsn,
                    environment=settings.environment,
                    traces_sample_rate=0.1 if settings.is_production else 0.05,
                    profiles_sample_rate=0.0,
                    integrations=[FastApiIntegration()],
                    send_default_pii=False,
                    max_breadcrumbs=30,
                )
                logger.info("sentry_initialized")
            except Exception as e:
                logger.warning("sentry_init_failed", error=str(e))

        logger.info("application_started", version=settings.app_version)

        yield

        # Shutdown
        logger.info("application_shutting_down")
        try:
            await db_manager.close()
            logger.info("database_connections_closed")
        except Exception as e:
            logger.error("shutdown_error", error=str(e))
        logger.info("application_stopped")

    # ------------------------------------------------------------------
    # FastAPI instance
    # ------------------------------------------------------------------

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI-powered electricity price optimization platform",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # OpenTelemetry instrumentation (opt-in via OTEL_ENABLED=true)
    #
    # Must be called after the FastAPI instance is created so that the
    # FastAPI instrumentor can wrap the application directly.  The call
    # is a no-op when OTEL_ENABLED is false (default), so there is zero
    # overhead in environments that have not opted in.
    # ------------------------------------------------------------------
    if settings.otel_enabled:
        try:
            from observability import init_telemetry, instrument_fastapi_app

            init_telemetry(app)
            # instrument_fastapi_app instruments the specific app instance
            # so route-level spans carry the correct operation names.
            instrument_fastapi_app(app)
            logger.info("otel_wired_into_app")
        except Exception as _otel_exc:
            logger.warning("otel_wire_failed", error=str(_otel_exc))

    # ------------------------------------------------------------------
    # Middleware (registration order matters — last registered = outermost
    # wrapper = runs first on the inbound request path)
    # ------------------------------------------------------------------

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-API-Key"],
    )

    # GZip compression
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Distributed tracing — registered last so it runs first, propagating
    # the trace_id context variable to all downstream middleware and handlers.
    app.add_middleware(TracingMiddleware)

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Rate limiting — Redis wired during lifespan() startup
    app.add_middleware(
        RateLimitMiddleware,
        rate_limiter=app_rate_limiter,
        exclude_paths=["/health", "/health/live", "/health/ready", "/metrics"],
    )

    # Request body size limit (1 MB; /connections/upload gets 10 MB)
    app.add_middleware(RequestBodySizeLimitMiddleware)

    # Per-request timeout (30 s; /prices/stream is excluded)
    app.add_middleware(RequestTimeoutMiddleware)

    # ------------------------------------------------------------------
    # Request timing middleware (decorator style — runs inside all ASGI
    # wrappers above, so trace_id is already available on request.state)
    # ------------------------------------------------------------------

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        """Record processing time and emit per-request access logs."""
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        if not settings.is_production:
            response.headers["X-Process-Time"] = str(process_time)

        trace_id = getattr(request.state, "trace_id", None)

        if settings.is_production:
            if process_time > 1.0 or response.status_code >= 400:
                logger.info(
                    "request_completed",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    process_time=process_time,
                    trace_id=trace_id,
                )
        else:
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                process_time=process_time,
                trace_id=trace_id,
            )

        return response

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """Handle validation errors — never echo back potentially sensitive input."""
        sanitized_errors = []
        for err in exc.errors():
            sanitized = {k: v for k, v in err.items() if k not in ("input", "ctx")}
            sanitized_errors.append(sanitized)

        logger.warning(
            "validation_error", errors=sanitized_errors, path=request.url.path
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": sanitized_errors},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected errors."""
        logger.error(
            "unexpected_error",
            error=str(exc),
            path=request.url.path,
            method=request.method,
        )

        if settings.is_production:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"},
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": str(exc)},
        )

    # ------------------------------------------------------------------
    # Prometheus metrics (protected by API key)
    # ------------------------------------------------------------------

    metrics_app = make_asgi_app()

    @app.middleware("http")
    async def protect_metrics(request: Request, call_next):
        """Require API key for /metrics to prevent information leakage."""
        if request.url.path.startswith("/metrics"):
            api_key = (
                request.headers.get("X-API-Key")
                or request.query_params.get("api_key")
            )
            if settings.internal_api_key and api_key != settings.internal_api_key:
                return JSONResponse(
                    status_code=403, content={"detail": "Forbidden"}
                )
        return await call_next(request)

    app.mount("/metrics", metrics_app)

    # ------------------------------------------------------------------
    # Root endpoint
    # ------------------------------------------------------------------

    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint with API information."""
        info = {
            "name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "health": "/health",
            "metrics": "/metrics",
        }
        if not settings.is_production:
            info["docs"] = "/docs"
        return info

    # ------------------------------------------------------------------
    # API routers
    # ------------------------------------------------------------------

    from routers import predictions
    from api.v1 import prices as prices_v1
    from api.v1 import suppliers as suppliers_v1
    from api.v1 import prices_analytics as prices_analytics_v1
    from api.v1 import prices_sse as prices_sse_v1
    from api.v1 import beta as beta_v1
    from api.v1 import auth as auth_v1
    from api.v1 import compliance as compliance_v1
    from api.v1 import user as user_v1
    from api.v1 import recommendations as recommendations_v1
    from api.v1 import billing as billing_v1
    from api.v1 import internal as internal_v1
    from api.v1 import regulations as regulations_v1
    from api.v1 import user_supplier as user_supplier_v1
    from api.v1 import webhooks as webhooks_v1
    from api.v1 import connections as connections_v1
    from api.v1 import users as users_v1
    from api.v1 import savings as savings_v1
    from api.v1 import alerts as alerts_v1
    from api.v1 import notifications as notifications_v1
    from api.v1 import health as health_v1
    from api.v1 import feedback as feedback_v1
    from api.v1 import agent as agent_v1

    app.include_router(
        predictions.router,
        prefix=f"{settings.api_prefix}/ml",
        tags=["ML Predictions"],
    )

    # Prices (CRUD + analytics + SSE)
    app.include_router(
        prices_v1.router,
        prefix=f"{settings.api_prefix}/prices",
        tags=["Prices"],
    )
    app.include_router(
        prices_analytics_v1.router,
        prefix=f"{settings.api_prefix}/prices",
        tags=["Price Analytics"],
    )
    app.include_router(
        prices_sse_v1.router,
        prefix=f"{settings.api_prefix}/prices",
        tags=["Price Streaming"],
    )

    app.include_router(
        suppliers_v1.router,
        prefix=f"{settings.api_prefix}/suppliers",
        tags=["Suppliers"],
    )
    app.include_router(
        beta_v1.router,
        prefix=f"{settings.api_prefix}",
        tags=["Beta"],
    )
    app.include_router(
        auth_v1.router,
        prefix=f"{settings.api_prefix}/auth",
        tags=["Authentication"],
    )
    app.include_router(
        compliance_v1.router,
        prefix=f"{settings.api_prefix}/compliance",
        tags=["Compliance"],
    )
    app.include_router(
        user_v1.router,
        prefix=f"{settings.api_prefix}/user",
        tags=["User"],
    )
    app.include_router(
        recommendations_v1.router,
        prefix=f"{settings.api_prefix}/recommendations",
        tags=["Recommendations"],
    )
    app.include_router(
        billing_v1.router,
        prefix=f"{settings.api_prefix}/billing",
        tags=["Billing"],
    )
    app.include_router(
        internal_v1.router,
        prefix=f"{settings.api_prefix}/internal",
        tags=["Internal"],
    )
    app.include_router(
        regulations_v1.router,
        prefix=f"{settings.api_prefix}/regulations",
        tags=["Regulations"],
    )
    app.include_router(
        user_supplier_v1.router,
        prefix=f"{settings.api_prefix}/user",
        tags=["User Supplier"],
    )
    app.include_router(
        webhooks_v1.router,
        prefix=f"{settings.api_prefix}/webhooks",
        tags=["Webhooks"],
    )
    app.include_router(
        connections_v1.router,
        prefix=f"{settings.api_prefix}/connections",
        tags=["Connections"],
    )
    app.include_router(
        users_v1.router,
        prefix=f"{settings.api_prefix}",
        tags=["Users"],
    )
    app.include_router(
        savings_v1.router,
        prefix=f"{settings.api_prefix}",
        tags=["Savings"],
    )
    app.include_router(
        alerts_v1.router,
        prefix=f"{settings.api_prefix}",
        tags=["Alerts"],
    )
    app.include_router(
        notifications_v1.router,
        prefix=f"{settings.api_prefix}",
        tags=["Notifications"],
    )
    # Health router: integrations check lives here; basic /health/* endpoints
    # are also registered in this router (see api/v1/health.py).
    app.include_router(
        health_v1.router,
        prefix="",
        tags=["Health"],
    )
    app.include_router(
        feedback_v1.router,
        prefix=f"{settings.api_prefix}",
        tags=["Feedback"],
    )
    app.include_router(
        agent_v1.router,
        prefix=f"{settings.api_prefix}",
        tags=["Agent"],
    )

    return app, app_rate_limiter
