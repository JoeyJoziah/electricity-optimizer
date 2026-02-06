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
import time

from config.settings import settings
from config.database import db_manager


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
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
        # Initialize database connections
        await db_manager.initialize()
        logger.info("database_connections_initialized")

        # Initialize Sentry if configured
        if settings.sentry_dsn:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.environment,
                traces_sample_rate=1.0 if settings.is_development else 0.1,
                integrations=[FastApiIntegration()]
            )
            logger.info("sentry_initialized")

        logger.info("application_started", version=settings.app_version)

    except Exception as e:
        logger.error("application_startup_failed", error=str(e))
        raise

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
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered electricity price optimization platform",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan
)


# ============================================================================
# MIDDLEWARE
# ============================================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZIP Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Request ID and Timing Middleware
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
    """Handle validation errors"""
    logger.warning("validation_error", errors=exc.errors(), body=exc.body)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": exc.body
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
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment
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
        "docs": "/docs" if settings.is_development else "disabled",
        "health": "/health",
        "metrics": "/metrics"
    }


# Import and include API routers
from routers import predictions

app.include_router(
    predictions.router,
    prefix=f"{settings.api_prefix}/ml",
    tags=["ML Predictions"]
)

# TODO: Uncomment as additional routers are implemented
# from routers import prices, suppliers, users, compliance
# app.include_router(prices.router, prefix=f"{settings.api_prefix}/prices", tags=["Prices"])
# app.include_router(suppliers.router, prefix=f"{settings.api_prefix}/suppliers", tags=["Suppliers"])
# app.include_router(users.router, prefix=f"{settings.api_prefix}/users", tags=["Users"])
# app.include_router(compliance.router, prefix=f"{settings.api_prefix}/compliance", tags=["Compliance"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.backend_port,
        reload=settings.is_development,
        log_level="info"
    )
