"""
Community Solar Service

Manages community solar program discovery, savings estimation,
and enrollment status for the community solar marketplace.
"""

from decimal import ROUND_HALF_UP, Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class CommunitySolarService:
    """
    Service for community solar program discovery and savings calculation.

    Programs are stored in the `community_solar_programs` table (migration 041).
    Savings estimates use the program's savings_percent against the user's
    current electricity bill.
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_programs(
        self,
        state: str,
        enrollment_status: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Get community solar programs available in a state.

        Args:
            state: 2-letter state code (e.g. "NY", "MA")
            enrollment_status: Filter by status (open, waitlist, closed)
            limit: Maximum number of programs to return
        """
        params: dict = {"state": state.upper(), "limit": limit}
        where_clauses = ["state = :state"]

        if enrollment_status:
            where_clauses.append("enrollment_status = :enrollment_status")
            params["enrollment_status"] = enrollment_status

        where_sql = " AND ".join(where_clauses)

        result = await self._db.execute(
            text(f"""
                SELECT id, state, program_name, provider, savings_percent,
                       capacity_kw, spots_available, enrollment_url,
                       enrollment_status, description, min_bill_amount,
                       contract_months, updated_at
                FROM community_solar_programs
                WHERE {where_sql}
                ORDER BY savings_percent DESC NULLS LAST, program_name
                LIMIT :limit
            """),
            params,
        )
        rows = result.mappings().all()
        return [
            {
                "id": str(r["id"]),
                "state": r["state"],
                "program_name": r["program_name"],
                "provider": r["provider"],
                "savings_percent": str(r["savings_percent"]) if r["savings_percent"] else None,
                "capacity_kw": str(r["capacity_kw"]) if r["capacity_kw"] else None,
                "spots_available": r["spots_available"],
                "enrollment_url": r["enrollment_url"],
                "enrollment_status": r["enrollment_status"],
                "description": r["description"],
                "min_bill_amount": str(r["min_bill_amount"]) if r["min_bill_amount"] else None,
                "contract_months": r["contract_months"],
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
            for r in rows
        ]

    async def get_program_by_id(self, program_id: str) -> dict | None:
        """Get a specific community solar program by ID."""
        result = await self._db.execute(
            text("""
                SELECT id, state, program_name, provider, savings_percent,
                       capacity_kw, spots_available, enrollment_url,
                       enrollment_status, description, min_bill_amount,
                       contract_months, created_at, updated_at
                FROM community_solar_programs
                WHERE id = :id
            """),
            {"id": program_id},
        )
        r = result.mappings().first()
        if not r:
            return None

        return {
            "id": str(r["id"]),
            "state": r["state"],
            "program_name": r["program_name"],
            "provider": r["provider"],
            "savings_percent": str(r["savings_percent"]) if r["savings_percent"] else None,
            "capacity_kw": str(r["capacity_kw"]) if r["capacity_kw"] else None,
            "spots_available": r["spots_available"],
            "enrollment_url": r["enrollment_url"],
            "enrollment_status": r["enrollment_status"],
            "description": r["description"],
            "min_bill_amount": str(r["min_bill_amount"]) if r["min_bill_amount"] else None,
            "contract_months": r["contract_months"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }

    @staticmethod
    def calculate_savings(
        monthly_bill: Decimal,
        savings_percent: Decimal,
    ) -> dict:
        """
        Calculate estimated savings from a community solar program.

        Args:
            monthly_bill: User's current monthly electricity bill in dollars
            savings_percent: Program's savings percentage (e.g. 10.0 for 10%)

        Returns:
            Dict with monthly, annual, and 5-year savings projections
        """
        savings_rate = savings_percent / Decimal("100")
        monthly_savings = (monthly_bill * savings_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        annual_savings = (monthly_savings * 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        five_year_savings = (annual_savings * 5).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        new_monthly_bill = (monthly_bill - monthly_savings).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return {
            "current_monthly_bill": str(monthly_bill),
            "savings_percent": str(savings_percent),
            "monthly_savings": str(monthly_savings),
            "annual_savings": str(annual_savings),
            "five_year_savings": str(five_year_savings),
            "new_monthly_bill": str(new_monthly_bill),
        }

    async def get_state_program_count(self) -> dict:
        """Get count of open community solar programs per state."""
        result = await self._db.execute(
            text("""
                SELECT state, COUNT(*) as program_count
                FROM community_solar_programs
                WHERE enrollment_status IN ('open', 'waitlist')
                GROUP BY state
                ORDER BY program_count DESC
            """)
        )
        rows = result.mappings().all()
        return {r["state"]: r["program_count"] for r in rows}
