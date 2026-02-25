"""
Electricity Optimizer - FastAPI Backend Application

Main application entry point with API endpoints, middleware, and lifecycle management.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from prometheus_client import make_asgi_app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import structlog
import time

from config.settings import settings
from config.database import db_manager

# Record application startup time for uptime calculation
_startup_time = time.time()


# Configure structured logging (optimized for free tier)
# Use simpler processors in production to reduce overhead
if settings.is_production:
    log_processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ]
else:
    log_processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ]

structlog.configure(
    processors=log_processors,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # Startup
    logger.info("application_starting", environment=settings.environment)

    try:
        # Initialize database connections (graceful degradation — app starts even if DB unavailable)
        await db_manager.initialize()
        logger.info("database_connections_initialized")
    except Exception as e:
        logger.error("database_init_failed", error=str(e))
        logger.warning("continuing_without_full_db", environment=settings.environment)

    # Wire Redis into rate limiter for distributed rate limiting
    # Skip in test environment to prevent cross-test state leakage
    if settings.environment != "test":
        try:
            redis = await db_manager.get_redis_client()
            if redis:
                _app_rate_limiter.redis = redis
                logger.info("rate_limiter_redis_wired")
        except Exception as e:
            logger.warning("rate_limiter_redis_wire_failed", error=str(e))

    # Initialize Sentry if configured (lazy import to reduce startup time)
    if settings.sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.environment,
                traces_sample_rate=0.1 if settings.is_production else 0.05,  # Lower sample rate for free tier
                profiles_sample_rate=0.0,  # Disable profiling to save memory
                integrations=[FastApiIntegration()],
                send_default_pii=False,
                max_breadcrumbs=30,  # Reduce from default 100
            )
            logger.info("sentry_initialized")
        except Exception as e:
            logger.warning("sentry_init_failed", error=str(e))
            # Continue without Sentry rather than failing

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


# Create FastAPI application
# Disable interactive API docs in production to reduce attack surface
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered electricity price optimization platform",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    lifespan=lifespan
)


# ============================================================================
# MIDDLEWARE
# ============================================================================

# CORS -- restrict origin regex to only the project's own subdomains.
# CORS: Use explicit origin allowlist (settings.cors_origins) instead of regex.
# Production origins should be set via CORS_ORIGINS env var.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-API-Key"],
)

# GZIP Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Security Headers
from middleware.security_headers import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)

# Rate Limiting — Redis wired in lifespan() for distributed rate limiting
from middleware.rate_limiter import RateLimitMiddleware, UserRateLimiter
_app_rate_limiter = UserRateLimiter()
app.add_middleware(
    RateLimitMiddleware,
    rate_limiter=_app_rate_limiter,
    exclude_paths=["/health", "/health/live", "/health/ready", "/metrics"],
)

# Request Body Size Limit (1 MB) — prevents memory exhaustion DoS
MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024  # 1 MB


class RequestBodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests exceeding the configured body size limit.

    Checks Content-Length header first (fast path), then enforces the limit
    on the actual body stream to handle chunked transfer encoding.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Allow larger uploads for bill upload endpoint (10 MB)
        max_bytes = MAX_REQUEST_BODY_BYTES
        if request.url.path.endswith("/connections/upload"):
            max_bytes = 10 * 1024 * 1024  # 10 MB for bill uploads

        content_length = request.headers.get("content-length")
        try:
            if content_length and int(content_length) > max_bytes:
                max_mb = max_bytes // (1024 * 1024)
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large. Maximum size is {max_mb} MB."},
                )
        except (ValueError, TypeError):
            pass

        # For requests without Content-Length (chunked encoding), read and
        # check the actual body size for methods that carry a body.
        if request.method in ("POST", "PUT", "PATCH") and not content_length:
            body = await request.body()
            if len(body) > max_bytes:
                max_mb = max_bytes // (1024 * 1024)
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large. Maximum size is {max_mb} MB."},
                )

        return await call_next(request)


app.add_middleware(RequestBodySizeLimitMiddleware)

# Per-Request Timeout (30s) — prevents slow requests from holding workers
REQUEST_TIMEOUT_SECONDS = 30


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Enforce a per-request timeout. SSE streaming endpoints are excluded."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.endswith("/prices/stream"):
            return await call_next(request)
        try:
            return await asyncio.wait_for(
                call_next(request), timeout=REQUEST_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={"detail": "Request timed out"},
            )


app.add_middleware(RequestTimeoutMiddleware)


# Request ID and Timing Middleware (optimized for production)
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add request ID and processing time to response headers"""
    import uuid

    request_id = str(uuid.uuid4())
    start_time = time.time()

    # Add request ID to structlog context
    structlog.contextvars.bind_contextvars(request_id=request_id)

    response = await call_next(request)

    process_time = time.time() - start_time
    response.headers["X-Request-ID"] = request_id
    if not settings.is_production:
        response.headers["X-Process-Time"] = str(process_time)

    # Only log slow requests in production to reduce overhead
    if settings.is_production:
        if process_time > 1.0 or response.status_code >= 400:
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                process_time=process_time
            )
    else:
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            process_time=process_time
        )

    return response


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors -- never echo back the request body as it may contain passwords or tokens"""
    # Sanitize error details:
    #   - Strip 'input' field which may contain sensitive values (passwords, tokens).
    #   - Strip 'ctx' field: Pydantic v2 stores the raw exception object in
    #     ctx["error"], which is NOT JSON-serialisable and would cause a
    #     cascading 500 if included in the JSONResponse payload.
    sanitized_errors = []
    for err in exc.errors():
        sanitized = {k: v for k, v in err.items() if k not in ("input", "ctx")}
        sanitized_errors.append(sanitized)

    logger.warning("validation_error", errors=sanitized_errors, path=request.url.path)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": sanitized_errors,
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors"""
    logger.error(
        "unexpected_error",
        error=str(exc),
        path=request.url.path,
        method=request.method
    )

    if settings.is_production:
        # Don't expose internal errors in production
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"}
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": str(exc)}
        )


# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Basic health check endpoint with deployment metadata"""
    uptime_seconds = time.time() - _startup_time

    # Determine database connectivity status
    db_status = "disconnected"
    try:
        if db_manager.timescale_engine or db_manager.timescale_pool:
            result = await db_manager._execute_raw_query("SELECT 1")
            if result:
                db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(uptime_seconds, 2),
        "database_status": db_status,
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """Readiness check - verify all dependencies are available"""
    checks = {
        "database": False,
        "redis": False,
    }

    # Check Database (Neon PostgreSQL)
    try:
        result = await db_manager._execute_raw_query("SELECT 1")
        checks["database"] = len(result) > 0
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))

    # Check Redis
    try:
        redis = await db_manager.get_redis_client()
        if redis:
            await redis.ping()
            checks["redis"] = True
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))

    all_healthy = all(checks.values())
    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_healthy else "not ready",
            "checks": checks
        }
    )


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    """Liveness check - verify application is running"""
    return {"status": "alive"}


# ============================================================================
# METRICS
# ============================================================================

# Mount Prometheus metrics behind API key auth
metrics_app = make_asgi_app()


@app.middleware("http")
async def protect_metrics(request: Request, call_next):
    """Require API key for /metrics endpoint to prevent information leakage."""
    if request.url.path.startswith("/metrics"):
        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if settings.internal_api_key and api_key != settings.internal_api_key:
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)


app.mount("/metrics", metrics_app)


# ============================================================================
# API ROUTES
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
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


# Import and include API routers
from routers import predictions
from api.v1 import prices as prices_v1
from api.v1 import suppliers as suppliers_v1

app.include_router(
    predictions.router,
    prefix=f"{settings.api_prefix}/ml",
    tags=["ML Predictions"]
)

# Price endpoints (split into CRUD, analytics, and SSE modules)
from api.v1 import prices_analytics as prices_analytics_v1
from api.v1 import prices_sse as prices_sse_v1

app.include_router(
    prices_v1.router,
    prefix=f"{settings.api_prefix}/prices",
    tags=["Prices"]
)
app.include_router(
    prices_analytics_v1.router,
    prefix=f"{settings.api_prefix}/prices",
    tags=["Price Analytics"]
)
app.include_router(
    prices_sse_v1.router,
    prefix=f"{settings.api_prefix}/prices",
    tags=["Price Streaming"]
)

# Supplier endpoints
app.include_router(
    suppliers_v1.router,
    prefix=f"{settings.api_prefix}/suppliers",
    tags=["Suppliers"]
)

# Beta Signup endpoints
from api.v1 import beta as beta_v1

app.include_router(
    beta_v1.router,
    prefix=f"{settings.api_prefix}",
    tags=["Beta"]
)

# Authentication endpoints
from api.v1 import auth as auth_v1

app.include_router(
    auth_v1.router,
    prefix=f"{settings.api_prefix}/auth",
    tags=["Authentication"]
)

# GDPR Compliance endpoints
from api.v1 import compliance as compliance_v1

app.include_router(
    compliance_v1.router,
    prefix=f"{settings.api_prefix}/compliance",
    tags=["Compliance"]
)

# User endpoints
from api.v1 import user as user_v1

app.include_router(
    user_v1.router,
    prefix=f"{settings.api_prefix}/user",
    tags=["User"]
)

# Recommendation endpoints
from api.v1 import recommendations as recommendations_v1

app.include_router(
    recommendations_v1.router,
    prefix=f"{settings.api_prefix}/recommendations",
    tags=["Recommendations"]
)

# Billing endpoints
from api.v1 import billing as billing_v1

app.include_router(
    billing_v1.router,
    prefix=f"{settings.api_prefix}/billing",
    tags=["Billing"]
)

# Internal endpoints (observation + learning jobs, API-key protected)
from api.v1 import internal as internal_v1

app.include_router(
    internal_v1.router,
    prefix=f"{settings.api_prefix}/internal",
    tags=["Internal"]
)

# State regulations endpoints
from api.v1 import regulations as regulations_v1

app.include_router(
    regulations_v1.router,
    prefix=f"{settings.api_prefix}/regulations",
    tags=["Regulations"]
)

# User supplier management endpoints
from api.v1 import user_supplier as user_supplier_v1

app.include_router(
    user_supplier_v1.router,
    prefix=f"{settings.api_prefix}/user",
    tags=["User Supplier"]
)


# GitHub webhook endpoint
from api.v1 import webhooks as webhooks_v1

app.include_router(
    webhooks_v1.router,
    prefix=f"{settings.api_prefix}/webhooks",
    tags=["Webhooks"]
)


# Connection feature endpoints (paid-tier gate enforced inside router)
from api.v1 import connections as connections_v1

app.include_router(
    connections_v1.router,
    prefix=f"{settings.api_prefix}/connections",
    tags=["Connections"]
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.backend_port,
        reload=settings.is_development,
        log_level="info"
    )
