"""
Integration Health Check API

Provides a deep health-check endpoint that verifies connectivity and
configuration status for every external service integration: database,
Redis, and third-party API keys (EIA, NREL, OpenWeatherMap, Stripe,
UtilityAPI, SendGrid/SMTP, and email OAuth providers).

The endpoint is intentionally unauthenticated so it can be called by
uptime monitors and load-balancer probes.  Sensitive internals are never
exposed — only ``"configured"`` / ``"not_configured"`` / ``"healthy"`` /
``"unhealthy"`` status strings are returned, never credentials.

Route
-----
GET /health/integrations   — deep integration status check
"""

import time
from typing import Any, Dict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from api.dependencies import get_db_session
from config.database import db_manager
from config.settings import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


# =============================================================================
# Helpers
# =============================================================================


def _configured(value: Any) -> str:
    """Return 'configured' if value is truthy, else 'not_configured'."""
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

    We deliberately do NOT make live HTTP calls here (too slow, may exhaust
    rate limits) — instead we confirm that credentials are configured so that
    operators know which integrations are wired up.
    """
    return {
        "eia": {"status": _configured(settings.eia_api_key)},
        "nrel": {"status": _configured(settings.nrel_api_key)},
        "openweathermap": {"status": _configured(settings.openweathermap_api_key)},
        "stripe": {"status": _configured(settings.stripe_secret_key)},
        "utilityapi": {"status": _configured(settings.utilityapi_key)},
        "sendgrid": {"status": _configured(settings.sendgrid_api_key)},
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
# Endpoint
# =============================================================================


@router.get(
    "/integrations",
    summary="Integration health check",
    response_description="Status of all external service integrations",
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

    # Live connectivity checks
    checks["database"] = await _check_database(db)
    checks["redis"] = await _check_redis()

    # Configuration-presence checks for external APIs
    checks.update(_check_external_apis())

    # Overall status considers only the live checks
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
