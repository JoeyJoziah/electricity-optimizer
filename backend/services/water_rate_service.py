"""
Water Rate Benchmarking Service

Municipal water rate lookups, tier-based cost calculation, and regional
benchmarking. Monitoring only — no "switch" CTA (Decision D4: water is
a geographic monopoly).
"""

from typing import Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Average US household water usage: ~80 gallons/person/day, ~2.4 people/household
# ≈ 5,760 gallons/month (source: USGS / EPA WaterSense)
AVG_MONTHLY_GALLONS = 5760

CONSERVATION_TIPS = [
    {
        "category": "Indoor",
        "title": "Fix leaky faucets",
        "description": "A faucet dripping at one drip per second wastes over 3,000 gallons per year.",
        "estimated_savings_gallons": 3000,
        "difficulty": "easy",
    },
    {
        "category": "Indoor",
        "title": "Install low-flow showerheads",
        "description": "Switching to a WaterSense-labeled showerhead can save 2,700 gallons per year.",
        "estimated_savings_gallons": 2700,
        "difficulty": "easy",
    },
    {
        "category": "Indoor",
        "title": "Run full loads only",
        "description": "Only run dishwashers and washing machines with full loads to maximize efficiency.",
        "estimated_savings_gallons": 1500,
        "difficulty": "easy",
    },
    {
        "category": "Indoor",
        "title": "Upgrade to dual-flush toilets",
        "description": "Older toilets use 3-7 gallons per flush. Dual-flush models use 0.8-1.6 gallons.",
        "estimated_savings_gallons": 4000,
        "difficulty": "moderate",
    },
    {
        "category": "Outdoor",
        "title": "Water lawns early morning",
        "description": "Watering before 10am reduces evaporation by up to 30%.",
        "estimated_savings_gallons": 2000,
        "difficulty": "easy",
    },
    {
        "category": "Outdoor",
        "title": "Use drip irrigation",
        "description": "Drip systems deliver water directly to roots, reducing waste by 30-50%.",
        "estimated_savings_gallons": 3000,
        "difficulty": "moderate",
    },
    {
        "category": "Outdoor",
        "title": "Install a rain barrel",
        "description": "Capture rainwater for garden use. A 55-gallon barrel can save ~1,300 gallons per year.",
        "estimated_savings_gallons": 1300,
        "difficulty": "moderate",
    },
    {
        "category": "Monitoring",
        "title": "Check your water meter",
        "description": "Read your meter before and after a 2-hour no-use window. Any change indicates a leak.",
        "estimated_savings_gallons": 0,
        "difficulty": "easy",
    },
]


class WaterRateService:
    """Service for water rate benchmarking and cost estimation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Rate queries
    # ------------------------------------------------------------------

    async def get_rates(
        self, state: Optional[str] = None,
    ) -> list[dict]:
        """Get water rates, optionally filtered by state."""
        if state:
            state = state.upper()
            result = await self.db.execute(
                text("""
                    SELECT id, municipality, state, rate_tiers, base_charge,
                           unit, effective_date, source_url, updated_at
                    FROM water_rates
                    WHERE state = :state
                    ORDER BY municipality
                """),
                {"state": state},
            )
        else:
            result = await self.db.execute(
                text("""
                    SELECT id, municipality, state, rate_tiers, base_charge,
                           unit, effective_date, source_url, updated_at
                    FROM water_rates
                    ORDER BY state, municipality
                """),
            )

        rows = result.mappings().all()
        return [self._format_rate(r) for r in rows]

    async def get_rate_by_municipality(
        self, municipality: str, state: str,
    ) -> Optional[dict]:
        """Get water rate for a specific municipality."""
        result = await self.db.execute(
            text("""
                SELECT id, municipality, state, rate_tiers, base_charge,
                       unit, effective_date, source_url, updated_at
                FROM water_rates
                WHERE LOWER(municipality) = LOWER(:municipality)
                  AND state = :state
            """),
            {"municipality": municipality, "state": state.upper()},
        )
        row = result.mappings().first()
        return self._format_rate(row) if row else None

    # ------------------------------------------------------------------
    # Tier calculator
    # ------------------------------------------------------------------

    def calculate_monthly_cost(
        self, rate: dict, usage_gallons: int,
    ) -> dict:
        """Calculate monthly water cost using tiered pricing.

        Tiers are applied incrementally: usage up to tier 1 limit is
        charged at tier 1 rate, usage between tier 1 and tier 2 limits
        at tier 2 rate, etc. Any usage beyond the last tier's limit
        uses the last tier's rate.
        """
        tiers = rate.get("rate_tiers", [])
        base_charge = float(rate.get("base_charge", 0))

        if not tiers:
            return {
                "municipality": rate.get("municipality"),
                "state": rate.get("state"),
                "usage_gallons": usage_gallons,
                "base_charge": base_charge,
                "tier_charges": 0,
                "total_monthly": base_charge,
                "breakdown": [],
            }

        remaining = usage_gallons
        tier_charges = 0.0
        breakdown = []
        prev_limit = 0

        for i, tier in enumerate(tiers):
            limit = tier.get("limit_gallons")
            rate_per_gallon = float(tier.get("rate_per_gallon", 0))

            if limit is None:
                # Unlimited top tier
                gallons_in_tier = remaining
            else:
                tier_capacity = limit - prev_limit
                gallons_in_tier = min(remaining, tier_capacity)

            charge = gallons_in_tier * rate_per_gallon
            tier_charges += charge

            breakdown.append({
                "tier": i + 1,
                "gallons": gallons_in_tier,
                "rate_per_gallon": rate_per_gallon,
                "charge": round(charge, 2),
            })

            remaining -= gallons_in_tier
            if limit is not None:
                prev_limit = limit

            if remaining <= 0:
                break

        return {
            "municipality": rate.get("municipality"),
            "state": rate.get("state"),
            "usage_gallons": usage_gallons,
            "base_charge": base_charge,
            "tier_charges": round(tier_charges, 2),
            "total_monthly": round(base_charge + tier_charges, 2),
            "breakdown": breakdown,
        }

    # ------------------------------------------------------------------
    # Regional benchmarking
    # ------------------------------------------------------------------

    async def get_benchmark(self, state: str) -> dict:
        """Compare water rates across municipalities in a state.

        Returns average cost at typical usage (AVG_MONTHLY_GALLONS)
        for all municipalities in the state.
        """
        state = state.upper()
        rates = await self.get_rates(state)

        if not rates:
            return {
                "state": state,
                "municipalities": 0,
                "avg_monthly_cost": None,
                "min_monthly_cost": None,
                "max_monthly_cost": None,
                "rates": [],
            }

        costs = []
        rate_details = []
        for rate in rates:
            cost = self.calculate_monthly_cost(rate, AVG_MONTHLY_GALLONS)
            total = cost["total_monthly"]
            costs.append(total)
            rate_details.append({
                "municipality": rate["municipality"],
                "monthly_cost": total,
                "base_charge": float(rate["base_charge"]),
            })

        avg_cost = sum(costs) / len(costs) if costs else 0

        return {
            "state": state,
            "municipalities": len(rates),
            "usage_gallons": AVG_MONTHLY_GALLONS,
            "avg_monthly_cost": round(avg_cost, 2),
            "min_monthly_cost": round(min(costs), 2) if costs else None,
            "max_monthly_cost": round(max(costs), 2) if costs else None,
            "rates": sorted(rate_details, key=lambda r: r["monthly_cost"]),
        }

    # ------------------------------------------------------------------
    # Conservation tips
    # ------------------------------------------------------------------

    @staticmethod
    def get_conservation_tips() -> list[dict]:
        """Return water conservation recommendations."""
        return CONSERVATION_TIPS

    # ------------------------------------------------------------------
    # Data management
    # ------------------------------------------------------------------

    async def upsert_rate(self, rate_data: dict) -> str:
        """Insert or update a water rate record.

        Returns the ID of the upserted record.
        """
        result = await self.db.execute(
            text("""
                INSERT INTO water_rates
                    (municipality, state, rate_tiers, base_charge, unit,
                     effective_date, source_url)
                VALUES (:municipality, :state, :rate_tiers::jsonb, :base_charge,
                        :unit, :effective_date, :source_url)
                ON CONFLICT (municipality, state) DO UPDATE
                    SET rate_tiers = EXCLUDED.rate_tiers,
                        base_charge = EXCLUDED.base_charge,
                        unit = EXCLUDED.unit,
                        effective_date = EXCLUDED.effective_date,
                        source_url = EXCLUDED.source_url,
                        updated_at = NOW()
                RETURNING id
            """),
            {
                "municipality": rate_data["municipality"],
                "state": rate_data["state"].upper(),
                "rate_tiers": rate_data.get("rate_tiers", "[]"),
                "base_charge": rate_data.get("base_charge", 0),
                "unit": rate_data.get("unit", "gallon"),
                "effective_date": rate_data.get("effective_date"),
                "source_url": rate_data.get("source_url"),
            },
        )
        row = result.fetchone()
        await self.db.commit()
        return str(row[0]) if row else ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_rate(row) -> dict:
        """Format a water_rates DB row into API dict."""
        return {
            "id": str(row["id"]),
            "municipality": row["municipality"],
            "state": row["state"],
            "rate_tiers": row["rate_tiers"] if row["rate_tiers"] else [],
            "base_charge": float(row["base_charge"]),
            "unit": row["unit"],
            "effective_date": (
                row["effective_date"].isoformat() if row["effective_date"] else None
            ),
            "source_url": row["source_url"],
            "updated_at": (
                row["updated_at"].isoformat() if row["updated_at"] else None
            ),
        }
