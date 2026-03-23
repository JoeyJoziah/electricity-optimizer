"""
Propane Price Service

Manages propane price data: fetching from EIA, storing in DB,
querying current prices + history. No dealer directory (Decision D12:
no propane dealer API exists, YAGNI for MVP).
"""

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.region import PROPANE_STATES

logger = structlog.get_logger(__name__)

# Average household propane usage: ~750 gallons/year (US avg for heating)
AVG_ANNUAL_GALLONS = 750
AVG_MONTHLY_GALLONS = AVG_ANNUAL_GALLONS / 12


class PropaneService:
    """Service for propane prices and regional comparison."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Price queries
    # ------------------------------------------------------------------

    async def get_current_prices(
        self,
        state: str | None = None,
    ) -> list[dict]:
        """Get latest propane prices, optionally filtered by state.

        Returns rows from propane_prices ordered by fetched_at desc.
        If state is provided, returns only that state; otherwise returns
        the most recent price for each tracked state.
        """
        if state:
            state = state.upper()
            result = await self.db.execute(
                text("""
                    SELECT id, state, price_per_gallon, source,
                           period_date, fetched_at
                    FROM propane_prices
                    WHERE state = :state
                    ORDER BY fetched_at DESC
                    LIMIT 1
                """),
                {"state": state},
            )
        else:
            result = await self.db.execute(
                text("""
                    SELECT DISTINCT ON (state)
                           id, state, price_per_gallon, source,
                           period_date, fetched_at
                    FROM propane_prices
                    ORDER BY state, fetched_at DESC
                """),
            )

        rows = result.mappings().all()
        return [
            {
                "id": str(r["id"]),
                "state": r["state"],
                "price_per_gallon": float(r["price_per_gallon"]),
                "source": r["source"],
                "period_date": r["period_date"].isoformat() if r["period_date"] else None,
                "fetched_at": r["fetched_at"].isoformat() if r["fetched_at"] else None,
            }
            for r in rows
        ]

    async def get_price_history(
        self,
        state: str,
        weeks: int = 12,
    ) -> list[dict]:
        """Get price history for a state over the last N weeks."""
        state = state.upper()
        result = await self.db.execute(
            text("""
                SELECT id, state, price_per_gallon, source,
                       period_date, fetched_at
                FROM propane_prices
                WHERE state = :state
                ORDER BY period_date DESC
                LIMIT :limit
            """),
            {"state": state, "limit": weeks},
        )

        rows = result.mappings().all()
        return [
            {
                "id": str(r["id"]),
                "state": r["state"],
                "price_per_gallon": float(r["price_per_gallon"]),
                "source": r["source"],
                "period_date": r["period_date"].isoformat() if r["period_date"] else None,
                "fetched_at": r["fetched_at"].isoformat() if r["fetched_at"] else None,
            }
            for r in rows
        ]

    async def get_price_comparison(self, state: str) -> dict | None:
        """Compare state propane price against national average."""
        state = state.upper()

        result = await self.db.execute(
            text("""
                SELECT state, price_per_gallon, fetched_at
                FROM propane_prices
                WHERE state IN (:state, 'US')
                  AND fetched_at = (
                      SELECT MAX(fetched_at) FROM propane_prices
                      WHERE state IN (:state, 'US')
                  )
                ORDER BY state
            """),
            {"state": state},
        )

        rows = {r["state"]: r for r in result.mappings().all()}

        if state not in rows:
            return None

        state_price = float(rows[state]["price_per_gallon"])
        national_price = float(rows["US"]["price_per_gallon"]) if "US" in rows else None

        monthly_cost = state_price * AVG_MONTHLY_GALLONS

        return {
            "state": state,
            "price_per_gallon": state_price,
            "national_avg": national_price,
            "difference_pct": (
                round((state_price - national_price) / national_price * 100, 1)
                if national_price
                else None
            ),
            "estimated_monthly_cost": round(monthly_cost, 2),
            "estimated_annual_cost": round(state_price * AVG_ANNUAL_GALLONS, 2),
        }

    # ------------------------------------------------------------------
    # Seasonal timing
    # ------------------------------------------------------------------

    async def get_seasonal_advice(self, state: str) -> dict:
        """Get fill-up timing advice based on seasonal price patterns.

        Propane prices are typically lowest in summer (May-Sep) and
        highest in winter (Dec-Feb). This provides simple guidance.
        """
        state = state.upper()

        # Get 52-week history to identify pattern
        result = await self.db.execute(
            text("""
                SELECT price_per_gallon, period_date
                FROM propane_prices
                WHERE state = :state
                ORDER BY period_date DESC
                LIMIT 52
            """),
            {"state": state},
        )

        rows = result.mappings().all()
        if len(rows) < 4:
            return {
                "state": state,
                "advice": "Not enough historical data for seasonal guidance yet.",
                "data_points": len(rows),
            }

        prices = [float(r["price_per_gallon"]) for r in rows]
        current = prices[0]
        avg = sum(prices) / len(prices)
        low = min(prices)
        high = max(prices)

        if current <= avg * 0.95:
            timing = "good"
            message = "Current prices are below the yearly average — good time to fill up."
        elif current >= avg * 1.05:
            timing = "wait"
            message = "Prices are above average. Consider waiting if your tank isn't low."
        else:
            timing = "neutral"
            message = "Prices are near the yearly average."

        return {
            "state": state,
            "timing": timing,
            "message": message,
            "current_price": current,
            "yearly_avg": round(avg, 4),
            "yearly_low": low,
            "yearly_high": high,
            "data_points": len(rows),
        }

    # ------------------------------------------------------------------
    # Data ingestion (called by internal pipeline)
    # ------------------------------------------------------------------

    async def store_prices(self, prices: list[dict]) -> int:
        """Store fetched propane prices.

        Inserts rows individually to isolate per-row errors (ON CONFLICT upsert).
        A single commit flushes all successfully staged rows at the end of each
        500-row chunk. The commit itself is guarded with try/except/rollback to
        prevent leaving the session in a dirty state on commit failure.

        Each dict should have: state, price_per_gallon, source, period_date
        """
        if not prices:
            return 0

        insert_sql = text("""
            INSERT INTO propane_prices
                (state, price_per_gallon, source, period_date)
            VALUES (:state, :price, :source, :period_date)
            ON CONFLICT (state, period_date) DO UPDATE
                SET price_per_gallon = EXCLUDED.price_per_gallon,
                    fetched_at = now()
        """)

        stored = 0
        chunk_size = 500
        for chunk_start in range(0, len(prices), chunk_size):
            chunk = prices[chunk_start : chunk_start + chunk_size]
            chunk_stored = 0
            for p in chunk:
                try:
                    await self.db.execute(
                        insert_sql,
                        {
                            "state": p["state"],
                            "price": p["price_per_gallon"],
                            "source": p["source"],
                            "period_date": p["period_date"],
                        },
                    )
                    chunk_stored += 1
                except Exception as e:
                    logger.warning(
                        "propane_store_failed",
                        state=p.get("state"),
                        error=str(e),
                    )
            if chunk_stored:
                try:
                    await self.db.commit()
                    stored += chunk_stored
                except Exception as e:
                    await self.db.rollback()
                    logger.warning(
                        "propane_store_batch_failed",
                        chunk_start=chunk_start,
                        chunk_size=chunk_stored,
                        error=str(e),
                    )
        return stored

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def is_propane_state(state_code: str) -> bool:
        """Check if a state has propane price tracking."""
        return state_code.upper() in PROPANE_STATES

    @staticmethod
    def get_tracked_states() -> list[str]:
        """Return list of states with propane tracking."""
        return sorted(PROPANE_STATES)
