"""
Multi-Utility Spend Optimization Report Service

Aggregates spend across all tracked utilities for a user's region,
identifies top savings opportunities ranked by dollar impact,
and generates a structured report (Business tier).
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Average monthly consumption by utility type (US household averages)
AVG_MONTHLY_CONSUMPTION = {
    "electricity": {"amount": 886, "unit": "kWh", "source": "EIA"},
    "natural_gas": {"amount": 50, "unit": "therms", "source": "EIA"},
    "heating_oil": {"amount": 67, "unit": "gallons", "source": "EIA Northeast"},
    "propane": {"amount": 63, "unit": "gallons", "source": "EIA"},
    "water": {"amount": 5760, "unit": "gallons", "source": "EPA/USGS"},
}


class OptimizationReportService:
    """Multi-utility spend optimization report generator."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_report(
        self,
        state: str,
        _user_id: str | None = None,
    ) -> dict:
        """
        Generate a multi-utility optimization report.

        Args:
            state: State code (e.g., "CT", "NY")
            user_id: Optional user ID for personalized data

        Returns:
            Report dict with utilities, total_monthly_spend, savings_opportunities
        """
        state = state.upper()
        now = datetime.now(UTC)

        utilities = []
        total_monthly = 0.0
        total_potential_savings = 0.0
        opportunities = []

        # Electricity + Natural Gas (single query — both use electricity_prices table)
        elec, gas = await self._get_electricity_and_gas_spend(state)
        for item in (elec, gas):
            if item:
                utilities.append(item)
                total_monthly += item["monthly_cost"]
                if item.get("savings"):
                    opportunities.append(item["savings"])
                    total_potential_savings += item["savings"]["monthly_savings"]

        # Heating Oil
        oil = await self._get_heating_oil_spend(state)
        if oil:
            utilities.append(oil)
            total_monthly += oil["monthly_cost"]
            if oil.get("savings"):
                opportunities.append(oil["savings"])
                total_potential_savings += oil["savings"]["monthly_savings"]

        # Propane
        propane = await self._get_propane_spend(state)
        if propane:
            utilities.append(propane)
            total_monthly += propane["monthly_cost"]
            if propane.get("savings"):
                opportunities.append(propane["savings"])
                total_potential_savings += propane["savings"]["monthly_savings"]

        # Sort opportunities by monthly savings descending
        opportunities.sort(key=lambda x: x["monthly_savings"], reverse=True)

        return {
            "state": state,
            "generated_at": now.isoformat(),
            "utilities": utilities,
            "total_monthly_spend": round(total_monthly, 2),
            "total_annual_spend": round(total_monthly * 12, 2),
            "savings_opportunities": opportunities,
            "total_potential_monthly_savings": round(total_potential_savings, 2),
            "total_potential_annual_savings": round(total_potential_savings * 12, 2),
            "utility_count": len(utilities),
        }

    async def _get_electricity_and_gas_spend(
        self, state: str
    ) -> tuple[dict | None, dict | None]:
        """Get electricity + natural gas spend in a single query (CTE merge).

        Both utility types live in electricity_prices, so one round trip suffices.
        """
        result = await self.db.execute(
            text("""
                WITH recent_prices AS (
                    SELECT price_per_kwh, supplier, utility_type,
                           ROW_NUMBER() OVER (
                               PARTITION BY utility_type ORDER BY timestamp DESC
                           ) AS rn
                    FROM electricity_prices
                    WHERE region = :region
                      AND utility_type IN ('ELECTRICITY', 'NATURAL_GAS')
                )
                SELECT price_per_kwh, supplier, utility_type
                FROM recent_prices
                WHERE (utility_type = 'ELECTRICITY' AND rn <= 10)
                   OR (utility_type = 'NATURAL_GAS' AND rn <= 5)
                ORDER BY utility_type, rn
            """),
            {"region": f"us_{state.lower()}"},
        )
        rows = result.mappings().all()

        # Partition results by utility_type
        elec_rows = [r for r in rows if r["utility_type"] == "ELECTRICITY"]
        gas_rows = [r for r in rows if r["utility_type"] == "NATURAL_GAS"]

        elec = self._build_electricity_result(elec_rows) if elec_rows else None
        gas = self._build_gas_result(gas_rows) if gas_rows else None
        return elec, gas

    @staticmethod
    def _build_electricity_result(rows: list) -> dict:
        """Build electricity spend dict from pre-fetched rows."""
        prices = [float(r["price_per_kwh"]) for r in rows]
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        consumption = AVG_MONTHLY_CONSUMPTION["electricity"]
        monthly_cost = avg_price * consumption["amount"]

        savings = None
        if len(prices) > 1 and avg_price > min_price:
            monthly_savings = (avg_price - min_price) * consumption["amount"]
            if monthly_savings > 1.0:
                savings = {
                    "utility_type": "electricity",
                    "action": f"Switch to cheapest supplier ({rows[-1].get('supplier', 'best rate')})",
                    "monthly_savings": round(monthly_savings, 2),
                    "annual_savings": round(monthly_savings * 12, 2),
                    "difficulty": "easy",
                }

        return {
            "utility_type": "electricity",
            "unit": "$/kWh",
            "current_rate": round(avg_price, 4),
            "monthly_consumption": consumption["amount"],
            "consumption_unit": consumption["unit"],
            "monthly_cost": round(monthly_cost, 2),
            "savings": savings,
        }

    @staticmethod
    def _build_gas_result(rows: list) -> dict:
        """Build natural gas spend dict from pre-fetched rows."""
        prices = [float(r["price_per_kwh"]) for r in rows]
        avg_price = sum(prices) / len(prices)
        consumption = AVG_MONTHLY_CONSUMPTION["natural_gas"]
        monthly_cost = avg_price * consumption["amount"]

        return {
            "utility_type": "natural_gas",
            "unit": "$/therm",
            "current_rate": round(avg_price, 4),
            "monthly_consumption": consumption["amount"],
            "consumption_unit": consumption["unit"],
            "monthly_cost": round(monthly_cost, 2),
            "savings": None,
        }

    async def _get_heating_oil_spend(self, state: str) -> dict | None:
        """Get heating oil spend analysis."""
        result = await self.db.execute(
            text("""
                SELECT price_per_gallon
                FROM heating_oil_prices
                WHERE state = :state
                ORDER BY fetched_at DESC
                LIMIT 5
            """),
            {"state": state},
        )
        rows = result.mappings().all()
        if not rows:
            return None

        prices = [float(r["price_per_gallon"]) for r in rows]
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        consumption = AVG_MONTHLY_CONSUMPTION["heating_oil"]
        monthly_cost = avg_price * consumption["amount"]

        savings = None
        if len(prices) > 1 and avg_price > min_price:
            monthly_savings = (avg_price - min_price) * consumption["amount"]
            if monthly_savings > 1.0:
                savings = {
                    "utility_type": "heating_oil",
                    "action": "Buy in bulk during summer low-price season",
                    "monthly_savings": round(monthly_savings, 2),
                    "annual_savings": round(monthly_savings * 12, 2),
                    "difficulty": "moderate",
                }

        return {
            "utility_type": "heating_oil",
            "unit": "$/gallon",
            "current_rate": round(avg_price, 4),
            "monthly_consumption": consumption["amount"],
            "consumption_unit": consumption["unit"],
            "monthly_cost": round(monthly_cost, 2),
            "savings": savings,
        }

    async def _get_propane_spend(self, state: str) -> dict | None:
        """Get propane spend analysis."""
        result = await self.db.execute(
            text("""
                SELECT price_per_gallon
                FROM propane_prices
                WHERE state = :state
                ORDER BY fetched_at DESC
                LIMIT 5
            """),
            {"state": state},
        )
        rows = result.mappings().all()
        if not rows:
            return None

        prices = [float(r["price_per_gallon"]) for r in rows]
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        consumption = AVG_MONTHLY_CONSUMPTION["propane"]
        monthly_cost = avg_price * consumption["amount"]

        savings = None
        if len(prices) > 1 and avg_price > min_price:
            monthly_savings = (avg_price - min_price) * consumption["amount"]
            if monthly_savings > 1.0:
                savings = {
                    "utility_type": "propane",
                    "action": "Fill tank during off-season (spring/summer)",
                    "monthly_savings": round(monthly_savings, 2),
                    "annual_savings": round(monthly_savings * 12, 2),
                    "difficulty": "easy",
                }

        return {
            "utility_type": "propane",
            "unit": "$/gallon",
            "current_rate": round(avg_price, 4),
            "monthly_consumption": consumption["amount"],
            "consumption_unit": consumption["unit"],
            "monthly_cost": round(monthly_cost, 2),
            "savings": savings,
        }
