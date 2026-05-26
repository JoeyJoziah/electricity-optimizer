"""Tests for the vendor-neutral supplier_offers read/write layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from models.supplier_offer import SupplierOffer
from repositories.supplier_offer_repository import SupplierOfferRepository
from services.pricing.regional_estimate import RegionalEstimateSource


def _rows_result(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _offer_row(**over):
    base = {
        "supplier_id": None,
        "supplier_name": "Acme",
        "rate_per_kwh": 0.20,
        "standing_charge": 0,
        "tariff_type": "fixed",
        "intro_term_months": None,
        "post_intro_rate": None,
        "cancellation_fee": None,
        "enrollment_fee": None,
        "renewable_pct": None,
        "enroll_url": None,
        "source": "ct_rate_board",
        "source_ref": None,
        "is_estimate": False,
        "effective_date": None,
        "expires_at": None,
    }
    base.update(over)
    return base


class TestCheapestAvailableBySupplier:
    async def test_keeps_cheapest_per_supplier(self):
        # Sorted by rate ASC (as the SQL guarantees); two rows for sup-1.
        rows = [
            _offer_row(supplier_id="sup-1", supplier_name="A", rate_per_kwh=0.18),
            _offer_row(supplier_id="sup-1", supplier_name="A", rate_per_kwh=0.22),
            _offer_row(supplier_id="sup-2", supplier_name="B", rate_per_kwh=0.20),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_rows_result(rows))
        estimate = MagicMock()
        estimate.fetch = AsyncMock(return_value=[])  # must NOT be used

        repo = SupplierOfferRepository(db, estimate_source=estimate)
        offers = await repo.cheapest_available_by_supplier("us_ct")

        assert set(offers) == {"sup-1", "sup-2"}
        assert offers["sup-1"].rate_per_kwh == 0.18  # cheapest of the two
        estimate.fetch.assert_not_called()

    async def test_falls_back_to_estimate_when_no_real_offers(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_rows_result([]))
        est = SupplierOffer(
            supplier_name="A",
            supplier_id="sup-1",
            rate_per_kwh=0.25,
            source="regional_estimate",
            is_estimate=True,
            utility_type="electricity",
        )
        estimate = MagicMock()
        estimate.fetch = AsyncMock(return_value=[est])

        repo = SupplierOfferRepository(db, estimate_source=estimate)
        offers = await repo.cheapest_available_by_supplier("us_ct")

        estimate.fetch.assert_awaited_once_with("us_ct")
        assert offers["sup-1"].is_estimate is True


class TestUpsertOffers:
    async def test_persists_real_offers_skips_estimates(self):
        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        repo = SupplierOfferRepository(db, estimate_source=MagicMock())

        offers = [
            SupplierOffer(
                supplier_name="A",
                rate_per_kwh=0.2,
                source="ct_rate_board",
                region="us_ct",
                is_estimate=False,
            ),
            SupplierOffer(
                supplier_name="B",
                rate_per_kwh=0.3,
                source="ct_rate_board",
                region="us_ct",
                is_estimate=True,  # estimate — must be skipped
            ),
        ]
        n = await repo.upsert_offers(offers, source="ct_rate_board")

        assert n == 1  # only the real offer persisted
        db.commit.assert_awaited_once()
        # 1 DELETE (per region) + 1 INSERT
        assert db.execute.await_count == 2

    async def test_no_real_offers_is_noop(self):
        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        repo = SupplierOfferRepository(db, estimate_source=MagicMock())
        n = await repo.upsert_offers(
            [
                SupplierOffer(
                    supplier_name="A",
                    rate_per_kwh=0.2,
                    source="regional_estimate",
                    region="us_ct",
                    is_estimate=True,
                )
            ],
            source="regional_estimate",
        )
        assert n == 0
        db.execute.assert_not_called()


class TestRegionalEstimateSource:
    async def test_one_estimate_per_active_supplier(self):
        src = RegionalEstimateSource(MagicMock())
        with (
            pytest.MonkeyPatch.context() as mp,
        ):
            mp.setattr(
                "repositories.supplier_repository.SupplierRegistryRepository.get_region_market_rate",
                AsyncMock(return_value=0.27),
            )
            mp.setattr(
                "repositories.supplier_repository.SupplierRegistryRepository.list_suppliers",
                AsyncMock(
                    return_value=(
                        [{"id": "s1", "name": "Eversource"}, {"id": "s2", "name": "UI"}],
                        2,
                    )
                ),
            )
            offers = await src.fetch("us_ct")

        assert len(offers) == 2
        assert all(o.is_estimate and o.rate_per_kwh == 0.27 for o in offers)
        assert {o.supplier_name for o in offers} == {"Eversource", "UI"}

    async def test_empty_when_no_market_rate(self):
        src = RegionalEstimateSource(MagicMock())
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "repositories.supplier_repository.SupplierRegistryRepository.get_region_market_rate",
                AsyncMock(return_value=None),
            )
            offers = await src.fetch("us_ct")
        assert offers == []
