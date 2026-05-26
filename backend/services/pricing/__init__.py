"""Vendor-neutral supplier pricing sources.

Each adapter implements ``SupplierOfferSource`` and produces normalized
``SupplierOffer`` objects. The read path (repositories.supplier_offer_repository)
consumes offers without knowing which source produced them, so sources can be
added/swapped (regional_estimate, ct_rate_board, arcadia, energybot, manual)
with no change to the API or frontend.
"""

from services.pricing.base import SupplierOfferSource
from services.pricing.regional_estimate import RegionalEstimateSource

__all__ = ["SupplierOfferSource", "RegionalEstimateSource"]
