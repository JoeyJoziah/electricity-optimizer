"""SupplierOfferSource protocol — the contract every pricing source implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from models.supplier_offer import SupplierOffer


@runtime_checkable
class SupplierOfferSource(Protocol):
    """A pluggable supplier-pricing source.

    Implementations must be side-effect free in ``fetch`` (no DB writes) — the
    repository owns persistence. ``name`` is the value written to
    ``supplier_offers.source``.
    """

    name: str

    def covers(self, region: str) -> bool:
        """Whether this source can provide offers for the given region."""
        ...

    async def fetch(self, region: str, *, zip_code: str | None = None) -> list[SupplierOffer]:
        """Return current offers for the region (and optional zip)."""
        ...
