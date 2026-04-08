"""
Savings Aggregator — combine savings across all monitored utility types.

Aggregates per-utility monthly savings from user_savings table,
computes rank percentile via PERCENT_RANK(), and respects enabled_utilities filter.
"""

from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class SavingsAggregator:
    """Aggregate savings across all utility types for a user."""

    async def get_combined_savings(
        self,
        db: AsyncSession,
        user_id: str,
        enabled_utilities: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Get combined monthly savings across all (or selected) utilities.

        Merges the per-utility breakdown and rank percentile into a single
        CTE query to avoid two sequential DB round-trips (19-P2-8).

        Returns:
            {
                total_monthly_savings: Decimal,
                breakdown: [{utility_type, monthly_savings}],
                savings_rank_pct: float | None,
            }
        """
        utility_filter = ""
        params: dict[str, Any] = {"user_id": user_id}

        if enabled_utilities:
            placeholders = ", ".join(f":ut_{i}" for i in range(len(enabled_utilities)))
            utility_filter = f" AND us.savings_type IN ({placeholders})"
            for i, ut in enumerate(enabled_utilities):
                params[f"ut_{i}"] = ut

        # Combined query: breakdown + rank percentile in one round-trip
        combined_sql = text(f"""
            WITH user_breakdown AS (
                SELECT
                    us.savings_type AS utility_type,
                    COALESCE(SUM(us.amount), 0) AS monthly_savings
                FROM user_savings us
                WHERE us.user_id = :user_id
                  AND us.created_at >= NOW() - INTERVAL '30 days'
                  {utility_filter}
                GROUP BY us.savings_type
                ORDER BY us.savings_type
            ),
            all_user_totals AS (
                SELECT user_id, SUM(amount) AS total_savings
                FROM user_savings
                WHERE created_at >= NOW() - INTERVAL '30 days'
                GROUP BY user_id
            ),
            ranked AS (
                SELECT
                    user_id,
                    PERCENT_RANK() OVER (ORDER BY total_savings) AS pct
                FROM all_user_totals
            )
            SELECT
                ub.utility_type,
                ub.monthly_savings,
                r.pct AS savings_rank_pct
            FROM user_breakdown ub
            LEFT JOIN ranked r ON r.user_id = :user_id
        """)
        result = await db.execute(combined_sql, params)
        rows = result.mappings().fetchall()

        if not rows:
            return {
                "total_monthly_savings": Decimal("0"),
                "breakdown": [],
                "savings_rank_pct": None,
            }

        breakdown = []
        rank_pct = None
        for row in rows:
            breakdown.append(
                {
                    "utility_type": row["utility_type"],
                    "monthly_savings": Decimal(str(row["monthly_savings"])),
                }
            )
            if rank_pct is None and row["savings_rank_pct"] is not None:
                rank_pct = float(row["savings_rank_pct"])

        total = sum(item["monthly_savings"] for item in breakdown)

        return {
            "total_monthly_savings": total,
            "breakdown": breakdown,
            "savings_rank_pct": rank_pct,
        }
