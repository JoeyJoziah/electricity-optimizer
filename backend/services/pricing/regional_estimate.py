"""RegionalEstimateSource — the universal fallback pricing source.

There is no per-supplier tariff data yet, so this derives an *estimate* from the
regional electricity market rate (the same figure the dashboard uses) and
applies it to every active supplier in the region. Offers are flagged
``is_estimate=True`` so the UI labels them honestly and the recommendation
engine never treats them as an actionable switch basis.

This source is computed live (never persisted) so it can't go stale — the
repository invokes it only when no real offers exist for a region.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from models.supplier_offer import SupplierOffer
from repositories.supplier_repository import SupplierRegistryRepository

logger = structlog.get_logger(__name__)


class RegionalEstimateSource:
    """Estimate every active supplier at the regional market rate."""

    name = "regional_estimate"

    def __init__(self, db: AsyncSession, cache: Any = None):
        self._db = db
        self._cache = cache

    def covers(self, region: str) -> bool:  # noqa: ARG002 — interface signature
        # Universal fallback — applies wherever a regional rate exists.
        return True

    async def fetch(
        self,
        region: str,
        *,
        zip_code: str | None = None,  # noqa: ARG002 — interface signature
    ) -> list[SupplierOffer]:
        repo = SupplierRegistryRepository(self._db, cache=self._cache)
        rate = await repo.get_region_market_rate(region)
        if rate is None:
            logger.info("regional_estimate_no_rate", region=region)
            return []

        suppliers, _ = await repo.list_suppliers(
            region=region,
            utility_type="electricity",
            active_only=True,
            page=1,
            page_size=100,
        )
        return [
            SupplierOffer(
                supplier_name=s["name"],
                supplier_id=s["id"],
                rate_per_kwh=rate,
                region=region,
                utility_type="electricity",
                source=self.name,
                is_estimate=True,
            )
            for s in suppliers
        ]
