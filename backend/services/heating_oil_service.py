"""
Heating Oil Price Service

Manages heating oil price data: fetching from EIA, storing in DB,
querying current prices + history, and dealer directory lookups.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.region import HEATING_OIL_STATES

logger = structlog.get_logger(__name__)

# Average household heating oil usage: ~800 gallons/year (Northeast avg)
AVG_ANNUAL_GALLONS = 800
AVG_MONTHLY_GALLONS = AVG_ANNUAL_GALLONS / 12


class HeatingOilService:
    """Service for heating oil prices and dealer directory."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Price queries
    # ------------------------------------------------------------------

    async def get_current_prices(
        self, state: Optional[str] = None,
    ) -> list[dict]:
        """Get latest heating oil prices, optionally filtered by state.

        Returns rows from heating_oil_prices ordered by fetched_at desc.
        If state is provided, returns only that state; otherwise returns
        the most recent price for each tracked state.
        """
        if state:
            state = state.upper()
            result = await self.db.execute(
                text("""
                    SELECT id, state, price_per_gallon, source,
                           period_date, fetched_at
                    FROM heating_oil_prices
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
                    FROM heating_oil_prices
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
        self, state: str, weeks: int = 12,
    ) -> list[dict]:
        """Get price history for a state over the last N weeks."""
        state = state.upper()
        result = await self.db.execute(
            text("""
                SELECT id, state, price_per_gallon, source,
                       period_date, fetched_at
                FROM heating_oil_prices
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

    async def get_price_comparison(self, state: str) -> Optional[dict]:
        """Compare state heating oil price against national average."""
        state = state.upper()

        result = await self.db.execute(
            text("""
                SELECT state, price_per_gallon, fetched_at
                FROM heating_oil_prices
                WHERE state IN (:state, 'US')
                  AND fetched_at = (
                      SELECT MAX(fetched_at) FROM heating_oil_prices
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
    # Data ingestion (called by internal pipeline)
    # ------------------------------------------------------------------

    async def store_prices(self, prices: list[dict]) -> int:
        """Store fetched heating oil prices.

        Each dict should have: state, price_per_gallon, source, period_date
        """
        stored = 0
        for p in prices:
            try:
                await self.db.execute(
                    text("""
                        INSERT INTO heating_oil_prices
                            (state, price_per_gallon, source, period_date)
                        VALUES (:state, :price, :source, :period_date)
                        ON CONFLICT (state, period_date) DO UPDATE
                            SET price_per_gallon = EXCLUDED.price_per_gallon,
                                fetched_at = now()
                    """),
                    {
                        "state": p["state"],
                        "price": p["price_per_gallon"],
                        "source": p["source"],
                        "period_date": p["period_date"],
                    },
                )
                stored += 1
            except Exception as e:
                logger.warning(
                    "heating_oil_store_failed",
                    state=p.get("state"),
                    error=str(e),
                )
        await self.db.commit()
        return stored

    # ------------------------------------------------------------------
    # Dealer directory
    # ------------------------------------------------------------------

    async def get_dealers(
        self, state: str, limit: int = 20,
    ) -> list[dict]:
        """Get heating oil dealers for a state."""
        state = state.upper()
        result = await self.db.execute(
            text("""
                SELECT id, name, state, city, phone, website,
                       rating, is_active
                FROM heating_oil_dealers
                WHERE state = :state AND is_active = TRUE
                ORDER BY rating DESC NULLS LAST, name ASC
                LIMIT :limit
            """),
            {"state": state, "limit": limit},
        )

        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "state": r["state"],
                "city": r["city"],
                "phone": r["phone"],
                "website": r["website"],
                "rating": float(r["rating"]) if r["rating"] else None,
            }
            for r in result.mappings().all()
        ]

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def is_heating_oil_state(state_code: str) -> bool:
        """Check if a state has a significant heating oil market."""
        return state_code.upper() in HEATING_OIL_STATES

    @staticmethod
    def get_tracked_states() -> list[str]:
        """Return list of states with heating oil tracking."""
        return sorted(HEATING_OIL_STATES)
