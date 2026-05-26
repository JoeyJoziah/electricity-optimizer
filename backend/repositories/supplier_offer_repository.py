"""
SupplierOfferRepository — source-agnostic read/write for supplier_offers.

The read path returns normalized ``SupplierOffer`` objects regardless of which
source produced them. When no real (non-estimate) offers exist for a region it
falls back to a live regional estimate (computed, not persisted), so callers
always get a usable, clearly-labeled answer without showing stale data.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.supplier_offer import SupplierOffer
from services.pricing.base import SupplierOfferSource
from services.pricing.regional_estimate import RegionalEstimateSource

logger = structlog.get_logger(__name__)

# How fresh a persisted offer must be to be served as "current".
DEFAULT_MAX_AGE_DAYS = 14

_SELECT_COLS = (
    "supplier_id, supplier_name, rate_per_kwh, standing_charge, tariff_type, "
    "intro_term_months, post_intro_rate, cancellation_fee, enrollment_fee, "
    "renewable_pct, enroll_url, source, source_ref, is_estimate, "
    "effective_date, expires_at"
)


def _row_to_offer(row: Any, region: str, utility_type: str) -> SupplierOffer:
    return SupplierOffer(
        supplier_name=row["supplier_name"],
        supplier_id=str(row["supplier_id"]) if row["supplier_id"] else None,
        rate_per_kwh=float(row["rate_per_kwh"]),
        standing_charge=float(row["standing_charge"] or 0),
        tariff_type=row["tariff_type"],
        intro_term_months=row["intro_term_months"],
        post_intro_rate=(
            float(row["post_intro_rate"]) if row["post_intro_rate"] is not None else None
        ),
        cancellation_fee=(
            float(row["cancellation_fee"]) if row["cancellation_fee"] is not None else None
        ),
        enrollment_fee=(
            float(row["enrollment_fee"]) if row["enrollment_fee"] is not None else None
        ),
        renewable_pct=row["renewable_pct"],
        enroll_url=row["enroll_url"],
        source=row["source"],
        source_ref=row["source_ref"],
        is_estimate=row["is_estimate"],
        effective_date=row["effective_date"],
        expires_at=row["expires_at"],
        region=region,
        utility_type=utility_type,
    )


class SupplierOfferRepository:
    def __init__(
        self,
        db: AsyncSession,
        cache: Any = None,
        estimate_source: SupplierOfferSource | None = None,
    ):
        self._db = db
        self._estimate = estimate_source or RegionalEstimateSource(db, cache=cache)

    async def cheapest_available_by_supplier(
        self,
        region: str,
        utility_type: str = "electricity",
        *,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    ) -> dict[str, SupplierOffer]:
        """Cheapest *available, non-expired, fresh, real* offer per supplier.

        Keyed by supplier_id (falling back to supplier_name). When there are no
        such real offers, returns a live regional estimate instead — never
        stale persisted data.
        """
        result = await self._db.execute(
            text(
                f"SELECT {_SELECT_COLS} FROM supplier_offers "
                "WHERE region = :region AND utility_type = :ut "
                "AND is_available = TRUE AND is_estimate = FALSE "
                "AND (expires_at IS NULL OR expires_at >= CURRENT_DATE) "
                "AND fetched_at >= now() - make_interval(days => :max_age) "
                "ORDER BY rate_per_kwh ASC"
            ),
            {"region": region, "ut": utility_type, "max_age": max_age_days},
        )
        rows = result.mappings().all()

        offers: dict[str, SupplierOffer] = {}
        for row in rows:
            offer = _row_to_offer(row, region, utility_type)
            key = offer.supplier_id or offer.supplier_name
            # rows are sorted by rate ASC, so the first seen per key is cheapest
            offers.setdefault(key, offer)

        if offers:
            return offers

        # No real offers — fall back to a live, labeled estimate.
        estimates = await self._estimate.fetch(region)
        return {
            (o.supplier_id or o.supplier_name): o
            for o in estimates
            if o.utility_type == utility_type
        }

    async def upsert_offers(self, offers: list[SupplierOffer], *, source: str) -> int:
        """Replace a source's offers for the regions it touched (idempotent).

        Real source adapters call this from their sync jobs. Estimates are never
        persisted. Deletes prior rows for ``(source, region)`` then inserts the
        fresh set, so re-running a sync can't accumulate duplicates or leave
        withdrawn offers behind.
        """
        persistable = [o for o in offers if not o.is_estimate]
        regions = {o.region for o in persistable if o.region}
        if not persistable:
            return 0

        for region in regions:
            await self._db.execute(
                text("DELETE FROM supplier_offers WHERE source = :source AND region = :region"),
                {"source": source, "region": region},
            )

        for o in persistable:
            await self._db.execute(
                text(
                    "INSERT INTO supplier_offers ("
                    "region, zip_code, utility_type, utility_territory, supplier_id, "
                    "supplier_name, rate_per_kwh, standing_charge, tariff_type, "
                    "intro_term_months, post_intro_rate, cancellation_fee, enrollment_fee, "
                    "renewable_pct, enroll_url, source, source_ref, is_estimate, "
                    "is_available, effective_date, expires_at, fetched_at) VALUES ("
                    ":region, :zip_code, :utility_type, :utility_territory, :supplier_id, "
                    ":supplier_name, :rate_per_kwh, :standing_charge, :tariff_type, "
                    ":intro_term_months, :post_intro_rate, :cancellation_fee, :enrollment_fee, "
                    ":renewable_pct, :enroll_url, :source, :source_ref, FALSE, "
                    ":is_available, :effective_date, :expires_at, now())"
                ),
                {
                    "region": o.region,
                    "zip_code": o.zip_code,
                    "utility_type": o.utility_type,
                    "utility_territory": o.utility_territory,
                    "supplier_id": o.supplier_id,
                    "supplier_name": o.supplier_name,
                    "rate_per_kwh": o.rate_per_kwh,
                    "standing_charge": o.standing_charge,
                    "tariff_type": o.tariff_type,
                    "intro_term_months": o.intro_term_months,
                    "post_intro_rate": o.post_intro_rate,
                    "cancellation_fee": o.cancellation_fee,
                    "enrollment_fee": o.enrollment_fee,
                    "renewable_pct": o.renewable_pct,
                    "enroll_url": o.enroll_url,
                    "source": source,
                    "source_ref": o.source_ref,
                    "is_available": o.is_available,
                    "effective_date": o.effective_date,
                    "expires_at": o.expires_at,
                },
            )
        await self._db.commit()
        return len(persistable)
