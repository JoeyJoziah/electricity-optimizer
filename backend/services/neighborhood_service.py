"""
Neighborhood Service — compare user rates against their region.

Uses PERCENT_RANK() to rank the user's rate within their region/utility_type.
Returns null fields when fewer than MIN_USERS_FOR_COMPARISON users in region.
"""

from decimal import Decimal
from typing import Any, Dict, Optional

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
    ) -> Dict[str, Any]:
        """
        Get neighborhood comparison for a user's rate.

        Returns null fields when < MIN_USERS_FOR_COMPARISON users in region.
        Otherwise returns percentile, cheapest supplier, and potential savings.
        """
        # Count users in region with this utility type
        count_sql = text("""
            SELECT COUNT(DISTINCT user_id) FROM user_savings
            WHERE region = :region
              AND utility_type = :utility_type
              AND created_at >= NOW() - INTERVAL '30 days'
        """)
        count_result = await db.execute(
            count_sql, {"region": region, "utility_type": utility_type}
        )
        user_count = count_result.scalar()

        if user_count < MIN_USERS_FOR_COMPARISON:
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

        # Get user's rate, percentile, cheapest supplier, and average
        comparison_sql = text("""
            WITH user_rates AS (
                SELECT
                    us.user_id,
                    AVG(us.amount) AS avg_rate,
                    MAX(s.name) AS supplier_name
                FROM user_savings us
                LEFT JOIN suppliers s ON us.supplier_id = s.id
                WHERE us.region = :region
                  AND us.utility_type = :utility_type
                  AND us.created_at >= NOW() - INTERVAL '30 days'
                GROUP BY us.user_id
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
                r.avg_rate AS user_rate,
                r.percentile,
                c.supplier_name AS cheapest_supplier,
                c.avg_rate AS cheapest_rate,
                (SELECT AVG(avg_rate) FROM user_rates) AS avg_rate
            FROM ranked r
            CROSS JOIN cheapest c
            WHERE r.user_id = :user_id
        """)
        result = await db.execute(
            comparison_sql,
            {"region": region, "utility_type": utility_type, "user_id": user_id},
        )
        row = result.mappings().fetchone()

        if not row:
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
        cheapest_rate = Decimal(str(row["cheapest_rate"]))
        potential_savings = max(Decimal("0"), user_rate - cheapest_rate)

        return {
            "region": region,
            "utility_type": utility_type,
            "user_count": user_count,
            "percentile": float(row["percentile"]),
            "user_rate": user_rate,
            "cheapest_supplier": row["cheapest_supplier"],
            "cheapest_rate": cheapest_rate,
            "avg_rate": Decimal(str(row["avg_rate"])),
            "potential_savings": potential_savings,
        }
