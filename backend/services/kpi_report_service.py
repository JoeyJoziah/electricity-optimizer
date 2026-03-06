"""
KPI Report Service

Aggregates key business metrics for the nightly KPI report:
active users, subscription breakdown, MRR, data freshness, etc.
"""

from typing import Any, Dict, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class KPIReportService:
    """
    Service for aggregating business KPI metrics.

    Usage:
        service = KPIReportService(db)
        metrics = await service.aggregate_metrics()
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def aggregate_metrics(self) -> Dict[str, Any]:
        """
        Collect all KPI metrics in a single pass.

        Returns dict with:
            active_users_7d, total_users, prices_tracked, alerts_sent_today,
            connections_active, subscription_breakdown, estimated_mrr,
            weather_freshness_hours
        """
        active_users_7d = await self._count_active_users_7d()
        total_users = await self._count_total_users()
        prices_tracked = await self._count_prices_tracked()
        alerts_sent_today = await self._count_alerts_sent_today()
        connections = await self._connection_status_breakdown()
        subscriptions = await self._subscription_breakdown()
        mrr = self._calculate_mrr(subscriptions)
        weather_freshness = await self._weather_freshness_hours()

        return {
            "active_users_7d": active_users_7d,
            "total_users": total_users,
            "prices_tracked": prices_tracked,
            "alerts_sent_today": alerts_sent_today,
            "connections_active": connections,
            "subscription_breakdown": subscriptions,
            "estimated_mrr": mrr,
            "weather_freshness_hours": weather_freshness,
        }

    async def _count_active_users_7d(self) -> int:
        result = await self._db.execute(text("""
                SELECT COUNT(DISTINCT "userId") FROM neon_auth.session
                WHERE "updatedAt" >= NOW() - INTERVAL '7 days'
            """))
        return result.scalar() or 0

    async def _count_total_users(self) -> int:
        result = await self._db.execute(text("SELECT COUNT(*) FROM users WHERE is_active = TRUE"))
        return result.scalar() or 0

    async def _count_prices_tracked(self) -> int:
        result = await self._db.execute(text("SELECT COUNT(*) FROM electricity_prices"))
        return result.scalar() or 0

    async def _count_alerts_sent_today(self) -> int:
        result = await self._db.execute(text("""
                SELECT COUNT(*) FROM alert_history
                WHERE triggered_at >= CURRENT_DATE
                  AND email_sent = TRUE
            """))
        return result.scalar() or 0

    async def _connection_status_breakdown(self) -> Dict[str, int]:
        result = await self._db.execute(text("""
                SELECT status, COUNT(*) AS cnt
                FROM user_connections
                GROUP BY status
            """))
        rows = result.mappings().all()
        return {row["status"]: row["cnt"] for row in rows}

    async def _subscription_breakdown(self) -> Dict[str, int]:
        result = await self._db.execute(text("""
                SELECT COALESCE(subscription_tier, 'free') AS tier, COUNT(*) AS cnt
                FROM users
                WHERE is_active = TRUE
                GROUP BY subscription_tier
            """))
        rows = result.mappings().all()
        return {row["tier"]: row["cnt"] for row in rows}

    @staticmethod
    def _calculate_mrr(subscriptions: Dict[str, int]) -> float:
        pro_count = subscriptions.get("pro", 0)
        business_count = subscriptions.get("business", 0)
        return round(pro_count * 4.99 + business_count * 14.99, 2)

    async def _weather_freshness_hours(self) -> Optional[float]:
        try:
            result = await self._db.execute(text("""
                    SELECT EXTRACT(EPOCH FROM (NOW() - MAX(timestamp))) / 3600.0
                    FROM electricity_prices
                """))
            val = result.scalar()
            if val is None:
                return None
            return round(float(val), 1)
        except Exception:
            return None
