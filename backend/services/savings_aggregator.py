"""
Savings Aggregator — combine savings across all monitored utility types.

Aggregates per-utility monthly savings from user_savings table,
computes rank percentile via PERCENT_RANK(), and respects enabled_utilities filter.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional

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
        enabled_utilities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get combined monthly savings across all (or selected) utilities.

        Returns:
            {
                total_monthly_savings: Decimal,
                breakdown: [{utility_type, monthly_savings}],
                savings_rank_pct: float | None,
            }
        """
        # Per-utility monthly savings
        utility_filter = ""
        params: Dict[str, Any] = {"user_id": user_id}

        if enabled_utilities:
            placeholders = ", ".join(f":ut_{i}" for i in range(len(enabled_utilities)))
            utility_filter = f" AND us.utility_type IN ({placeholders})"
            for i, ut in enumerate(enabled_utilities):
                params[f"ut_{i}"] = ut

        savings_sql = text(f"""
            SELECT
                us.utility_type,
                COALESCE(SUM(us.amount), 0) AS monthly_savings
            FROM user_savings us
            WHERE us.user_id = :user_id
              AND us.created_at >= NOW() - INTERVAL '30 days'
              {utility_filter}
            GROUP BY us.utility_type
            ORDER BY us.utility_type
        """)
        result = await db.execute(savings_sql, params)
        rows = result.mappings().fetchall()

        breakdown = [
            {
                "utility_type": row["utility_type"],
                "monthly_savings": Decimal(str(row["monthly_savings"])),
            }
            for row in rows
        ]

        total = sum(item["monthly_savings"] for item in breakdown)

        if not breakdown:
            return {
                "total_monthly_savings": Decimal("0"),
                "breakdown": [],
                "savings_rank_pct": None,
            }

        # Rank percentile among all users
        rank_sql = text("""
            SELECT PERCENT_RANK() OVER (
                ORDER BY total_savings
            ) AS pct
            FROM (
                SELECT user_id, SUM(amount) AS total_savings
                FROM user_savings
                WHERE created_at >= NOW() - INTERVAL '30 days'
                GROUP BY user_id
            ) sub
            WHERE user_id = :user_id
        """)
        rank_result = await db.execute(rank_sql, {"user_id": user_id})
        rank_pct = rank_result.scalar()

        return {
            "total_monthly_savings": total,
            "breakdown": breakdown,
            "savings_rank_pct": float(rank_pct) if rank_pct is not None else None,
        }
