"""
KPI Report Service

Aggregates key business metrics for the nightly KPI report:
active users, subscription breakdown, MRR, data freshness, etc.
"""

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings

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

    async def aggregate_metrics(self) -> dict[str, Any]:
        """
        Collect all KPI metrics in a single DB round-trip.

        Uses a multi-CTE query to fetch scalar metrics in one statement,
        followed by two lightweight GROUP BY queries for breakdowns.
        This replaces the previous 7-sequential-await pattern (MED-09).

        Returns dict with:
            active_users_7d, total_users, prices_tracked, alerts_sent_today,
            connections_active, subscription_breakdown, estimated_mrr,
            weather_freshness_hours
        """
        # Single CTE query for all scalar metrics (was 5 sequential queries)
        scalars = await self._db.execute(text("""
                WITH active AS (
                    SELECT COUNT(DISTINCT "userId") AS val
                    FROM neon_auth.session
                    WHERE "updatedAt" >= NOW() - INTERVAL '7 days'
                ),
                total AS (
                    SELECT COUNT(*) AS val FROM users WHERE is_active = TRUE
                ),
                prices AS (
                    SELECT COALESCE(reltuples, 0)::bigint AS val
                    FROM pg_class WHERE relname = 'electricity_prices'
                ),
                alerts AS (
                    SELECT COUNT(*) AS val FROM alert_history
                    WHERE triggered_at >= CURRENT_DATE AND email_sent = TRUE
                ),
                freshness AS (
                    SELECT EXTRACT(EPOCH FROM (NOW() - MAX(timestamp))) / 3600.0 AS val
                    FROM electricity_prices
                )
                SELECT
                    (SELECT val FROM active) AS active_users_7d,
                    (SELECT val FROM total) AS total_users,
                    (SELECT val FROM prices) AS prices_tracked,
                    (SELECT val FROM alerts) AS alerts_sent_today,
                    (SELECT val FROM freshness) AS weather_freshness
            """))
        row = scalars.mappings().one()

        # Two lightweight GROUP BY queries (breakdown results need row iteration)
        connections = await self._connection_status_breakdown()
        subscriptions = await self._subscription_breakdown()
        mrr = self._calculate_mrr(subscriptions)

        weather = row["weather_freshness"]

        return {
            "active_users_7d": row["active_users_7d"] or 0,
            "total_users": row["total_users"] or 0,
            "prices_tracked": row["prices_tracked"] or 0,
            "alerts_sent_today": row["alerts_sent_today"] or 0,
            "connections_active": connections,
            "subscription_breakdown": subscriptions,
            "estimated_mrr": mrr,
            "weather_freshness_hours": (
                round(float(weather), 1) if weather is not None else None
            ),
        }

    async def _connection_status_breakdown(self) -> dict[str, int]:
        result = await self._db.execute(text("""
                SELECT status, COUNT(*) AS cnt
                FROM user_connections
                GROUP BY status
            """))
        rows = result.mappings().all()
        return {row["status"]: row["cnt"] for row in rows}

    async def _subscription_breakdown(self) -> dict[str, int]:
        result = await self._db.execute(text("""
                SELECT COALESCE(subscription_tier, 'free') AS tier, COUNT(*) AS cnt
                FROM users
                WHERE is_active = TRUE
                GROUP BY subscription_tier
            """))
        rows = result.mappings().all()
        return {row["tier"]: row["cnt"] for row in rows}

    @staticmethod
    def _calculate_mrr(subscriptions: dict[str, int]) -> float:
        pro_count = subscriptions.get("pro", 0)
        business_count = subscriptions.get("business", 0)
        return round(
            pro_count * settings.stripe_mrr_price_pro
            + business_count * settings.stripe_mrr_price_business,
            2,
        )
