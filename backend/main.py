"""
Electricity Optimizer - FastAPI Backend Application

Main application entry point with API endpoints, middleware, and lifecycle management.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from prometheus_client import make_asgi_app
import structlog
import sys
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
        # Initialize database connections (graceful degradation in dev)
        await db_manager.initialize()
        logger.info("database_connections_initialized")
    except Exception as e:
        logger.error("database_init_failed", error=str(e))
        if settings.is_production:
            raise
        logger.warning("continuing_without_full_db", environment=settings.environment)

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
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)


# ============================================================================
# MIDDLEWARE
# ============================================================================

# CORS -- restrict origin regex to only the project's own subdomains.
# The previous regex r"https://.*\.(vercel\.app|onrender\.com)" was too broad
# and would allow any attacker-controlled Vercel/Render deployment to make
# credentialed cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://electricity-optimizer[a-z0-9\-]*\.(vercel\.app|onrender\.com)",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-API-Key"],
)

# GZIP Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Security Headers
from middleware.security_headers import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)

# Rate Limiting
from middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(
    RateLimitMiddleware,
    exclude_paths=["/health", "/health/live", "/health/ready", "/metrics"],
)


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
    # Sanitize error details: strip 'input' field which may contain sensitive values
    sanitized_errors = []
    for err in exc.errors():
        sanitized = {k: v for k, v in err.items() if k != "input"}
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
            result = await db_manager.execute_timescale_query("SELECT 1")
            if result:
                db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(uptime_seconds, 2),
        "python_version": sys.version,
        "database_status": db_status,
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """Readiness check - verify all dependencies are available"""
    checks = {
        "redis": False,
        "timescaledb": False,
        "supabase": False
    }

    # Check Redis
    try:
        redis = await db_manager.get_redis_client()
        await redis.ping()
        checks["redis"] = True
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))

    # Check TimescaleDB
    try:
        result = await db_manager.execute_timescale_query("SELECT 1")
        checks["timescaledb"] = len(result) > 0
    except Exception as e:
        logger.error("timescaledb_health_check_failed", error=str(e))

    # Check Supabase
    try:
        supabase = db_manager.get_supabase_client()
        checks["supabase"] = supabase is not None
    except Exception as e:
        logger.error("supabase_health_check_failed", error=str(e))

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

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# ============================================================================
# API ROUTES
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }


# Import and include API routers
from routers import predictions
from api.v1 import prices as prices_v1
from api.v1 import suppliers as suppliers_v1

app.include_router(
    predictions.router,
    prefix=f"{settings.api_prefix}/ml",
    tags=["ML Predictions"]
)

# Price endpoints
app.include_router(
    prices_v1.router,
    prefix=f"{settings.api_prefix}/prices",
    tags=["Prices"]
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.backend_port,
        reload=settings.is_development,
        log_level="info"
    )
