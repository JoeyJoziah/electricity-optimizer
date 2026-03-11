"""
Gas Rate Service

Orchestrates EIA natural gas data fetching, normalization, and storage.
Stores gas prices in the existing `electricity_prices` table using
utility_type=NATURAL_GAS (multi-utility since migration 006).
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from integrations.pricing_apis.eia import EIAClient
from integrations.pricing_apis.base import PricingRegion, APIError
from models.price import Price
from models.utility import UtilityType, PriceUnit
from models.region import DEREGULATED_GAS_STATES
from repositories.price_repository import PriceRepository

logger = structlog.get_logger(__name__)


class GasRateService:
    """
    Service for fetching, storing, and querying natural gas rate data.

    Uses the EIA API client to fetch residential gas prices by state,
    then stores them in `electricity_prices` with utility_type=NATURAL_GAS.
    """

    def __init__(self, db: AsyncSession, eia_client: Optional[EIAClient] = None):
        self._db = db
        self._eia_client = eia_client
        self._price_repo = PriceRepository(db)

    async def fetch_gas_rates(
        self,
        states: Optional[list[str]] = None,
        concurrency: int = 5,
    ) -> dict:
        """
        Fetch gas rates from EIA for specified states (or all deregulated states).

        Args:
            states: List of state codes (e.g. ["CT", "PA"]). Defaults to all
                    deregulated gas states.
            concurrency: Max concurrent EIA API calls.

        Returns:
            Summary dict with counts: {fetched, stored, errors, details}
        """
        if not self._eia_client:
            raise RuntimeError("EIA client not configured — missing EIA_API_KEY")

        target_states = states or sorted(DEREGULATED_GAS_STATES)
        semaphore = asyncio.Semaphore(concurrency)
        results = {"fetched": 0, "stored": 0, "errors": 0, "details": []}

        async def fetch_state(state_code: str):
            async with semaphore:
                try:
                    region = PricingRegion(f"us_{state_code.lower()}")
                    price_data = await self._eia_client.get_gas_price(region)

                    # Convert PriceData to Price model for storage
                    price = Price(
                        region=f"us_{state_code.lower()}",
                        supplier="EIA Average",
                        price_per_kwh=price_data.price,  # actually $/therm
                        timestamp=price_data.timestamp,
                        currency="USD",
                        utility_type=UtilityType.NATURAL_GAS,
                        unit=PriceUnit.THERM,
                        source_api="eia",
                    )

                    await self._price_repo.create(price)
                    results["fetched"] += 1
                    results["stored"] += 1
                    results["details"].append({
                        "state": state_code,
                        "price_therm": str(price_data.price),
                        "status": "ok",
                    })
                    logger.info(
                        "gas_rate_fetched",
                        state=state_code,
                        price_therm=str(price_data.price),
                    )
                except APIError as e:
                    results["errors"] += 1
                    results["details"].append({
                        "state": state_code,
                        "status": "error",
                        "error": str(e),
                    })
                    logger.warning("gas_rate_fetch_failed", state=state_code, error=str(e))
                except Exception as e:
                    results["errors"] += 1
                    results["details"].append({
                        "state": state_code,
                        "status": "error",
                        "error": str(e),
                    })
                    logger.error("gas_rate_fetch_unexpected", state=state_code, error=str(e))

        await asyncio.gather(*[fetch_state(s) for s in target_states])

        logger.info(
            "gas_rate_fetch_complete",
            fetched=results["fetched"],
            stored=results["stored"],
            errors=results["errors"],
            total_states=len(target_states),
        )
        return results

    async def get_gas_prices(
        self,
        region: str,
        limit: int = 10,
    ) -> list[Price]:
        """Get recent gas prices for a region."""
        return await self._price_repo.get_current_prices(
            region=region,
            limit=limit,
            utility_type=UtilityType.NATURAL_GAS,
        )

    async def get_gas_price_history(
        self,
        region: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Price]:
        """Get gas price history for a region."""
        return await self._price_repo.get_historical_prices(
            region=region,
            start_date=start_date,
            end_date=end_date,
            utility_type=UtilityType.NATURAL_GAS,
        )

    async def get_gas_stats(self, region: str, days: int = 7) -> dict:
        """Get gas price statistics for a region."""
        return await self._price_repo.get_price_statistics(
            region=region,
            days=days,
            utility_type=UtilityType.NATURAL_GAS,
        )

    async def get_deregulated_states(self) -> list[dict]:
        """Get list of gas-deregulated states with regulation details."""
        result = await self._db.execute(
            text("""
                SELECT state_code, state_name, puc_name, puc_website,
                       comparison_tool_url
                FROM state_regulations
                WHERE gas_deregulated = TRUE
                ORDER BY state_name
            """)
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]
