"""
Savings Service — track, query, and record per-user monetary savings.

Persists savings events to ``user_savings`` and exposes summary aggregations
(total, weekly, monthly) plus a consecutive-day streak counter.

All queries use parameterised ``text()`` statements and the async SQLAlchemy
session pattern established across this codebase.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

logger = structlog.get_logger()


class SavingsService:
    """Service for managing user savings records."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    async def get_savings_summary(
        self,
        user_id: str,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return aggregated savings totals for a user.

        Calculates:
          - total  : sum of all savings ever recorded
          - weekly : sum of savings created in the last 7 calendar days
          - monthly: sum of savings created in the last 30 calendar days
          - streak_days: number of consecutive calendar days (ending today)
                         on which at least one savings record was created
          - currency: currency code of the user's savings (defaults to 'USD')

        If the user has no records every value is 0 / 0.0 and streak_days is 0.

        Args:
            user_id: UUID string of the authenticated user.
            region:  Optional region filter applied to all sub-queries.

        Returns:
            Dict with keys total, weekly, monthly, streak_days, currency.
        """
        base_params: Dict[str, Any] = {"user_id": user_id}
        region_clause = ""
        if region:
            region_clause = " AND region = :region"
            base_params["region"] = region

        # -------------------------------------------------------------------
        # Aggregate totals (total / weekly / monthly) in a single query
        # -------------------------------------------------------------------
        agg_sql = text(f"""
            SELECT
                COALESCE(SUM(amount), 0)                                          AS total,
                COALESCE(SUM(amount) FILTER (
                    WHERE created_at >= NOW() - INTERVAL '7 days'
                ), 0)                                                             AS weekly,
                COALESCE(SUM(amount) FILTER (
                    WHERE created_at >= NOW() - INTERVAL '30 days'
                ), 0)                                                             AS monthly,
                MAX(currency)                                                      AS currency
            FROM user_savings
            WHERE user_id = :user_id
            {region_clause}
        """)
        agg_result = await self.db.execute(agg_sql, base_params)
        agg_row = agg_result.mappings().first()

        total = float(agg_row["total"]) if agg_row and agg_row["total"] is not None else 0.0
        weekly = float(agg_row["weekly"]) if agg_row and agg_row["weekly"] is not None else 0.0
        monthly = float(agg_row["monthly"]) if agg_row and agg_row["monthly"] is not None else 0.0
        currency = (agg_row["currency"] if agg_row and agg_row["currency"] else "USD") or "USD"

        if total == 0.0:
            # No data at all — skip streak calculation
            return {
                "total": 0.0,
                "weekly": 0.0,
                "monthly": 0.0,
                "streak_days": 0,
                "currency": currency,
            }

        # -------------------------------------------------------------------
        # Streak: fetch distinct active days (most recent first, limited to a
        # practical window of 365 days to bound the query cost)
        # -------------------------------------------------------------------
        streak_sql = text(f"""
            SELECT DISTINCT DATE(created_at AT TIME ZONE 'UTC') AS day
            FROM user_savings
            WHERE user_id = :user_id
              AND created_at >= NOW() - INTERVAL '365 days'
            {region_clause}
            ORDER BY day DESC
        """)
        streak_result = await self.db.execute(streak_sql, base_params)
        streak_rows = streak_result.fetchall()

        streak_days = self._compute_streak(streak_rows)

        logger.debug(
            "savings_summary_computed",
            user_id=user_id,
            total=total,
            weekly=weekly,
            monthly=monthly,
            streak_days=streak_days,
        )

        return {
            "total": total,
            "weekly": weekly,
            "monthly": monthly,
            "streak_days": streak_days,
            "currency": currency,
        }

    # ------------------------------------------------------------------
    # History (paginated)
    # ------------------------------------------------------------------

    async def get_savings_history(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Return a paginated list of savings records for a user.

        Args:
            user_id:   UUID string of the authenticated user.
            page:      1-based page number (default 1).
            page_size: Number of records per page (default 20).

        Returns:
            Dict with keys items (list of record dicts), total, page, page_size,
            pages (total page count).
        """
        page = max(1, page)
        page_size = max(1, min(100, page_size))  # clamp between 1 and 100
        offset = (page - 1) * page_size

        # Total count for this user
        count_result = await self.db.execute(
            text("SELECT COUNT(*) FROM user_savings WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        total = count_result.scalar() or 0

        # Paginated records
        rows_result = await self.db.execute(
            text("""
                SELECT id, user_id, savings_type, amount, currency,
                       description, region, period_start, period_end, created_at
                FROM user_savings
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"user_id": user_id, "limit": page_size, "offset": offset},
        )
        rows = rows_result.mappings().all()

        items = [self._row_to_record(row) for row in rows]
        pages = max(1, (total + page_size - 1) // page_size)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
        }

    # ------------------------------------------------------------------
    # Record a new savings event
    # ------------------------------------------------------------------

    async def record_savings(
        self,
        user_id: str,
        savings_type: str,
        amount: float,
        period_start: datetime,
        period_end: datetime,
        region: Optional[str] = None,
        description: Optional[str] = None,
        currency: str = "USD",
    ) -> Dict[str, Any]:
        """
        Insert a new savings record and return it.

        Args:
            user_id:      UUID string of the user.
            savings_type: One of 'switching', 'usage', 'alert'.
            amount:       Monetary saving amount (must be positive).
            period_start: Start of the period the saving covers.
            period_end:   End of the period the saving covers.
            region:       Optional region code (e.g. 'US_CT').
            description:  Optional human-readable description.
            currency:     ISO 4217 currency code (default 'USD').

        Returns:
            Dict representation of the inserted row.
        """
        record_id = str(uuid4())

        result = await self.db.execute(
            text("""
                INSERT INTO user_savings
                    (id, user_id, savings_type, amount, currency,
                     description, region, period_start, period_end)
                VALUES
                    (:id, :user_id, :savings_type, :amount, :currency,
                     :description, :region, :period_start, :period_end)
                RETURNING id, user_id, savings_type, amount, currency,
                          description, region, period_start, period_end, created_at
            """),
            {
                "id": record_id,
                "user_id": user_id,
                "savings_type": savings_type,
                "amount": amount,
                "currency": currency,
                "description": description,
                "region": region,
                "period_start": period_start,
                "period_end": period_end,
            },
        )
        await self.db.commit()
        row = result.mappings().first()

        logger.info(
            "savings_recorded",
            user_id=user_id,
            savings_type=savings_type,
            amount=amount,
            record_id=record_id,
        )

        return self._row_to_record(row)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row) -> Dict[str, Any]:
        """Convert a SQLAlchemy row mapping to a plain dict."""
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "savings_type": row["savings_type"],
            "amount": float(row["amount"]),
            "currency": row["currency"],
            "description": row["description"],
            "region": row["region"],
            "period_start": row["period_start"].isoformat() if row["period_start"] else None,
            "period_end": row["period_end"].isoformat() if row["period_end"] else None,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

    @staticmethod
    def _compute_streak(day_rows) -> int:
        """
        Count consecutive calendar days (ending today UTC) that appear in
        day_rows (ordered most-recent first).

        Each element in day_rows is expected to have a ``day`` column (a
        ``datetime.date`` object).  If today has no record the streak is 0.
        """
        if not day_rows:
            return 0

        today = datetime.now(tz=timezone.utc).date()
        streak = 0

        for i, row in enumerate(day_rows):
            day = row[0]  # fetchall() returns tuples
            if hasattr(day, "date"):
                day = day.date()  # handle datetime objects

            expected = today - timedelta(days=i)
            if day == expected:
                streak += 1
            else:
                break

        return streak
