"""
SupplierOffer — normalized, source-agnostic supplier pricing.

Every pricing source adapter (regional_estimate, ct_rate_board, arcadia,
energybot, manual) produces SupplierOffer instances in this one shape. The read
path (/suppliers, /suppliers/recommend) consumes them without knowing the
source. ``is_estimate`` distinguishes a derived/uniform figure from an actually
obtainable offer so the UI can label it honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class SupplierOffer:
    """One supplier pricing record, normalized across sources."""

    supplier_name: str
    rate_per_kwh: float
    source: str  # 'regional_estimate' | 'ct_rate_board' | 'arcadia' | 'energybot' | 'manual'

    # Defaults
    region: str | None = None
    zip_code: str | None = None
    utility_type: str = "electricity"
    utility_territory: str | None = None
    supplier_id: str | None = None
    standing_charge: float = 0.0
    tariff_type: str = "fixed"
    intro_term_months: int | None = None
    post_intro_rate: float | None = None
    cancellation_fee: float | None = None
    enrollment_fee: float | None = None
    renewable_pct: int | None = None
    enroll_url: str | None = None
    source_ref: str | None = None
    is_estimate: bool = False
    is_available: bool = True
    effective_date: date | None = None
    expires_at: date | None = None
    raw: dict[str, Any] | None = field(default=None, repr=False)

    def annual_cost(self, annual_usage_kwh: float) -> float:
        """Estimated annual cost for a given usage, rounded to cents.

        Uses standing_charge as an annualized fixed component when present.
        """
        return round(self.rate_per_kwh * annual_usage_kwh + (self.standing_charge or 0.0), 2)
