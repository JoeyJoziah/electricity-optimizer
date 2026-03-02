"""
Analytics dashboard endpoints for the Connections feature.

Routes (mounted under the /connections prefix in router.py):
  GET /analytics/comparison   — compare user rates vs current market
  GET /analytics/history      — time-series rate data for chart rendering
  GET /analytics/savings      — estimated annual savings
  GET /analytics/health       — stale connection detection + rate-change alerts

CRITICAL: All /analytics/* routes MUST be registered in router.py BEFORE the
/{connection_id} wildcard routes (i.e., include this router before crud.py).
FastAPI matches routes in registration order; if the wildcard is registered
first, "analytics" gets captured as a connection_id and these endpoints will
never be reached.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, TokenData
from api.v1.connections.common import require_paid_tier

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /analytics/comparison  —  rate comparison
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/comparison",
    summary="Compare user rates vs market",
)
async def get_rate_comparison(
    connection_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
):
    """Compare extracted rates against current market prices."""
    from services.connection_analytics_service import ConnectionAnalyticsService
    svc = ConnectionAnalyticsService(db)
    return await svc.get_rate_comparison(current_user.user_id, connection_id)


# ---------------------------------------------------------------------------
# GET /analytics/history  —  rate history for charts
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/history",
    summary="Rate history for chart rendering",
)
async def get_rate_history(
    connection_id: Optional[str] = Query(None),
    days: int = Query(365, ge=1, le=1095),
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
):
    """Get time-series rate data for chart rendering."""
    from services.connection_analytics_service import ConnectionAnalyticsService
    svc = ConnectionAnalyticsService(db)
    return await svc.get_rate_history(current_user.user_id, connection_id, days)


# ---------------------------------------------------------------------------
# GET /analytics/savings  —  estimated savings
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/savings",
    summary="Estimated annual savings",
)
async def get_savings_estimate(
    monthly_kwh: float = Query(900, ge=0, le=50000),
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
):
    """Calculate estimated annual savings based on rate comparison."""
    from services.connection_analytics_service import ConnectionAnalyticsService
    svc = ConnectionAnalyticsService(db)
    return await svc.get_savings_estimate(current_user.user_id, monthly_kwh)


# ---------------------------------------------------------------------------
# GET /analytics/health  —  stale connection detection
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/health",
    summary="Connection health status",
)
async def get_connection_health(
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
):
    """Check for stale or unhealthy connections."""
    from services.connection_analytics_service import ConnectionAnalyticsService
    svc = ConnectionAnalyticsService(db)
    stale = await svc.check_stale_connections(current_user.user_id)
    alerts = await svc.detect_rate_changes(current_user.user_id)
    return {
        "stale_connections": stale,
        "rate_change_alerts": alerts,
        "total_stale": len(stale),
        "total_alerts": len(alerts),
    }
