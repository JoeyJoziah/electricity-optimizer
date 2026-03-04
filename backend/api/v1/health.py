"""
Health Check API

Provides health and readiness endpoints for load-balancer probes, uptime
monitors, and the integration deep-check used by operators.

Routes
------
GET /health                — basic health + uptime + DB connectivity status
GET /health/ready          — readiness check (DB + Redis)
GET /health/live           — liveness probe (always 200 if process is alive)
GET /health/integrations   — deep integration status (DB, Redis, all API keys)
"""

import time
from typing import Any, Dict

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, verify_api_key
from config.database import db_manager
from config.settings import settings

logger = structlog.get_logger(__name__)

# Recorded once when this module is first imported so that /health can report
# the application uptime.  In practice this happens at startup time when the
# router is registered with the app.
_startup_time: float = time.time()

router = APIRouter(prefix="/health", tags=["Health"])


# =============================================================================
# Shared helpers
# =============================================================================


def _configured(value: Any) -> str:
    """Return 'configured' if *value* is truthy, otherwise 'not_configured'."""
    return "configured" if value else "not_configured"


async def _check_database(db: AsyncSession) -> Dict[str, Any]:
    """Verify DB connectivity with a lightweight SELECT 1 and measure latency."""
    start = time.monotonic()
    try:
        if db is None:
            return {"status": "unhealthy", "error": "No database session"}
        await db.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        logger.warning("health_check_db_failed", error=str(exc))
        return {"status": "unhealthy", "error": str(exc), "latency_ms": latency_ms}


async def _check_redis() -> Dict[str, Any]:
    """Verify Redis connectivity with a PING and measure latency."""
    start = time.monotonic()
    try:
        redis = await db_manager.get_redis_client()
        if redis is None:
            return {"status": "not_configured"}
        await redis.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        logger.warning("health_check_redis_failed", error=str(exc))
        return {"status": "unhealthy", "error": str(exc), "latency_ms": latency_ms}


def _check_external_apis() -> Dict[str, Dict[str, str]]:
    """
    Check whether external API keys are present in config.

    Deliberately avoids live HTTP calls (too slow, risks rate-limit exhaustion)
    — only verifies that credentials are configured.
    """
    return {
        "eia": {"status": _configured(settings.eia_api_key)},
        "nrel": {"status": _configured(settings.nrel_api_key)},
        "openweathermap": {"status": _configured(settings.openweathermap_api_key)},
        "stripe": {"status": _configured(settings.stripe_secret_key)},
        "utilityapi": {"status": _configured(settings.utilityapi_key)},
        "resend": {"status": _configured(settings.resend_api_key)},
        "gmail_oauth": {
            "status": _configured(
                settings.gmail_client_id and settings.gmail_client_secret
            )
        },
        "outlook_oauth": {
            "status": _configured(
                settings.outlook_client_id and settings.outlook_client_secret
            )
        },
        "field_encryption": {"status": _configured(settings.field_encryption_key)},
        "internal_api_key": {"status": _configured(settings.internal_api_key)},
    }


# =============================================================================
# Basic health endpoints
# =============================================================================


@router.get("", tags=["Health"], summary="Basic health check")
async def health_check():
    """Basic health check endpoint with deployment metadata and uptime."""
    uptime_seconds = time.time() - _startup_time

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


@router.get("/ready", tags=["Health"], summary="Readiness check")
async def readiness_check():
    """Readiness check — verify all dependencies are available."""
    checks: Dict[str, bool] = {
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
    http_status = 200 if all_healthy else 503

    return JSONResponse(
        status_code=http_status,
        content={
            "status": "ready" if all_healthy else "not ready",
            "checks": checks,
        },
    )


@router.get("/live", tags=["Health"], summary="Liveness probe")
async def liveness_check():
    """Liveness check — verify application process is running."""
    return {"status": "alive"}


# =============================================================================
# Integration deep-check endpoint
# =============================================================================


@router.get(
    "/integrations",
    summary="Integration health check",
    response_description="Status of all external service integrations",
    dependencies=[Depends(verify_api_key)],
)
async def check_integrations(
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Deep health check for all external service integrations.

    Performs live connectivity checks for database and Redis.  For third-party
    APIs (EIA, NREL, Stripe, etc.) the check only verifies that credentials are
    configured — no live HTTP calls are made to avoid rate-limit exhaustion.

    Response shape::

        {
          "status": "healthy" | "degraded",
          "integrations": {
            "database":      {"status": "healthy", "latency_ms": 4.2},
            "redis":         {"status": "healthy", "latency_ms": 1.1},
            "eia":           {"status": "configured"},
            "stripe":        {"status": "not_configured"},
            ...
          }
        }

    HTTP 200 is returned when all *live* checks pass (database + redis).
    HTTP 503 is returned if any *live* check fails.
    """
    checks: Dict[str, Any] = {}

    checks["database"] = await _check_database(db)
    checks["redis"] = await _check_redis()
    checks.update(_check_external_apis())

    live_statuses = [checks["database"]["status"], checks["redis"]["status"]]
    overall = (
        "healthy"
        if all(s in ("healthy", "not_configured") for s in live_statuses)
        else "degraded"
    )

    http_status = 200 if overall == "healthy" else 503

    logger.info(
        "integration_health_checked",
        overall=overall,
        db=checks["database"]["status"],
        redis=checks["redis"]["status"],
    )

    return JSONResponse(
        status_code=http_status,
        content={"status": overall, "integrations": checks},
    )
