"""
CCA (Community Choice Aggregation) Service

Detects CCA enrollment by zip code/municipality, compares CCA rates
against default utility rates, and provides opt-out information.
"""

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.region import CCA_STATES

logger = structlog.get_logger(__name__)


class CCAService:
    """
    Detects and provides information about Community Choice Aggregation programs.

    CCA programs allow municipalities to purchase electricity on behalf of
    residents, often at lower rates or with greener generation mixes.
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def detect_cca(
        self,
        zip_code: str | None = None,
        state: str | None = None,
        municipality: str | None = None,
    ) -> dict | None:
        """
        Detect if a user is in a CCA program.

        Looks up by zip_code first (most precise), then by state + municipality.
        Returns the CCA program dict or None if not in a CCA.
        """
        if zip_code:
            result = await self._db.execute(
                text("""
                    SELECT id, state, municipality, program_name, provider,
                           generation_mix, rate_vs_default_pct, opt_out_url,
                           program_url, status
                    FROM cca_programs
                    WHERE :zip = ANY(zip_codes)
                      AND status = 'active'
                    LIMIT 1
                """),
                {"zip": zip_code},
            )
            row = result.mappings().first()
            if row:
                return self._row_to_dict(row)

        if state and municipality:
            result = await self._db.execute(
                text("""
                    SELECT id, state, municipality, program_name, provider,
                           generation_mix, rate_vs_default_pct, opt_out_url,
                           program_url, status
                    FROM cca_programs
                    WHERE UPPER(state) = UPPER(:state)
                      AND LOWER(municipality) = LOWER(:municipality)
                      AND status = 'active'
                    LIMIT 1
                """),
                {"state": state, "municipality": municipality},
            )
            row = result.mappings().first()
            if row:
                return self._row_to_dict(row)

        return None

    async def compare_cca_rate(
        self,
        cca_id: str,
        default_rate: float,
    ) -> dict:
        """
        Compare a CCA program's rate against the default utility rate.

        Returns savings info based on the CCA's rate_vs_default_pct.
        A negative pct means the CCA is cheaper (savings).
        """
        result = await self._db.execute(
            text("""
                SELECT id, program_name, provider, rate_vs_default_pct
                FROM cca_programs
                WHERE id = :cca_id::uuid
            """),
            {"cca_id": cca_id},
        )
        row = result.mappings().first()
        if not row:
            return {"error": "CCA program not found"}

        pct = float(row["rate_vs_default_pct"]) if row["rate_vs_default_pct"] else 0.0
        cca_rate = default_rate * (1 + pct / 100)
        savings_per_kwh = default_rate - cca_rate
        monthly_savings = savings_per_kwh * 900  # avg 900 kWh/month

        return {
            "cca_id": str(row["id"]),
            "program_name": row["program_name"],
            "provider": row["provider"],
            "default_rate": round(default_rate, 4),
            "cca_rate": round(cca_rate, 4),
            "rate_difference_pct": pct,
            "savings_per_kwh": round(savings_per_kwh, 4),
            "estimated_monthly_savings": round(monthly_savings, 2),
            "is_cheaper": pct < 0,
        }

    async def get_cca_info(self, cca_id: str) -> dict | None:
        """Get full CCA program details including opt-out info."""
        result = await self._db.execute(
            text("""
                SELECT id, state, municipality, zip_codes, program_name,
                       provider, generation_mix, rate_vs_default_pct,
                       opt_out_url, program_url, status
                FROM cca_programs
                WHERE id = :cca_id::uuid
            """),
            {"cca_id": cca_id},
        )
        row = result.mappings().first()
        if not row:
            return None

        info = self._row_to_dict(row)
        info["zip_codes"] = list(row["zip_codes"]) if row["zip_codes"] else []
        return info

    async def list_cca_programs(self, state: str | None = None) -> list[dict]:
        """List all active CCA programs, optionally filtered by state."""
        if state:
            result = await self._db.execute(
                text("""
                    SELECT id, state, municipality, program_name, provider,
                           generation_mix, rate_vs_default_pct, opt_out_url,
                           program_url, status
                    FROM cca_programs
                    WHERE UPPER(state) = UPPER(:state) AND status = 'active'
                    ORDER BY municipality
                """),
                {"state": state},
            )
        else:
            result = await self._db.execute(
                text("""
                    SELECT id, state, municipality, program_name, provider,
                           generation_mix, rate_vs_default_pct, opt_out_url,
                           program_url, status
                    FROM cca_programs
                    WHERE status = 'active'
                    ORDER BY state, municipality
                """),
            )
        return [self._row_to_dict(r) for r in result.mappings().all()]

    @staticmethod
    def is_cca_state(state_code: str) -> bool:
        """Check if a state has CCA programs."""
        return state_code.upper() in CCA_STATES

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": str(row["id"]),
            "state": row["state"],
            "municipality": row["municipality"],
            "program_name": row["program_name"],
            "provider": row["provider"],
            "generation_mix": row["generation_mix"],
            "rate_vs_default_pct": float(row["rate_vs_default_pct"])
            if row["rate_vs_default_pct"]
            else None,
            "opt_out_url": row["opt_out_url"],
            "program_url": row["program_url"],
            "status": row["status"],
        }
