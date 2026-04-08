"""
Neighborhood Service — compare user rates against their region.

Uses PERCENT_RANK() to rank the user's rate within their region/utility_type.
Returns null fields when fewer than MIN_USERS_FOR_COMPARISON users in region.
"""

from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Minimum users in region before comparison is meaningful
MIN_USERS_FOR_COMPARISON = 5


class NeighborhoodService:
    """Compare user rates against their region peers."""

    async def get_comparison(
        self,
        db: AsyncSession,
        user_id: str,
        region: str,
        utility_type: str,
    ) -> dict[str, Any]:
        """
        Get neighborhood comparison for a user's rate.

        Returns null fields when < MIN_USERS_FOR_COMPARISON users in region.
        Otherwise returns percentile, cheapest supplier, and potential savings.

        Merges the count check and comparison into a single CTE query to
        avoid two sequential DB round-trips (19-P2-7).
        """
        combined_sql = text("""
            WITH user_rates AS (
                SELECT
                    us.user_id,
                    AVG(us.amount) AS avg_rate,
                    NULL::text AS supplier_name
                FROM user_savings us
                WHERE us.region = :region
                  AND us.savings_type = :utility_type
                  AND us.created_at >= NOW() - INTERVAL '30 days'
                GROUP BY us.user_id
            ),
            stats AS (
                SELECT COUNT(*) AS user_count FROM user_rates
            ),
            ranked AS (
                SELECT
                    user_id,
                    avg_rate,
                    supplier_name,
                    PERCENT_RANK() OVER (ORDER BY avg_rate) AS percentile
                FROM user_rates
            ),
            cheapest AS (
                SELECT supplier_name, avg_rate
                FROM user_rates
                WHERE supplier_name IS NOT NULL
                ORDER BY avg_rate ASC
                LIMIT 1
            )
            SELECT
                s.user_count,
                r.avg_rate AS user_rate,
                r.percentile,
                c.supplier_name AS cheapest_supplier,
                c.avg_rate AS cheapest_rate,
                (SELECT AVG(avg_rate) FROM user_rates) AS avg_rate
            FROM stats s
            LEFT JOIN ranked r ON r.user_id = :user_id
            LEFT JOIN cheapest c ON TRUE
        """)
        result = await db.execute(
            combined_sql,
            {"region": region, "utility_type": utility_type, "user_id": user_id},
        )
        row = result.mappings().fetchone()

        user_count = row["user_count"] if row else 0

        if not row or user_count < MIN_USERS_FOR_COMPARISON or row["user_rate"] is None:
            return {
                "region": region,
                "utility_type": utility_type,
                "user_count": user_count,
                "percentile": None,
                "user_rate": None,
                "cheapest_supplier": None,
                "cheapest_rate": None,
                "avg_rate": None,
                "potential_savings": None,
            }

        user_rate = Decimal(str(row["user_rate"]))
        cheapest_rate = (
            Decimal(str(row["cheapest_rate"])) if row["cheapest_rate"] is not None else user_rate
        )
        potential_savings = max(Decimal("0"), user_rate - cheapest_rate)

        return {
            "region": region,
            "utility_type": utility_type,
            "user_count": user_count,
            "percentile": float(row["percentile"]),
            "user_rate": user_rate,
            "cheapest_supplier": row["cheapest_supplier"],
            "cheapest_rate": cheapest_rate,
            "avg_rate": Decimal(str(row["avg_rate"])) if row["avg_rate"] is not None else user_rate,
            "potential_savings": potential_savings,
        }
