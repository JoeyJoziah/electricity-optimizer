"""
Plan Scorer — Rate Structure Matching Engine

Scores how well each available plan's rate structure matches a user's actual
consumption pattern. Handles flat, TOU, and tiered rate structures.

Confidence scoring based on data source quality:
  - 15-min interval data (Arcadia/UtilityAPI) → 0.95 base
  - Hourly interval data → 0.90 base
  - Monthly kWh from bills → 0.60 base
  - Portal scrape data → 0.55 base
  - Manual entry → 0.40 base

Confidence is further adjusted by months_of_data (more months → higher
confidence, capped at 1.0).
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog

from lib.tracing import traced

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Confidence multipliers by data source
# ---------------------------------------------------------------------------

DATA_SOURCE_CONFIDENCE: dict[str, Decimal] = {
    "arcadia_15min": Decimal("0.95"),
    "arcadia_60min": Decimal("0.90"),
    "utilityapi_15min": Decimal("0.95"),
    "utilityapi_60min": Decimal("0.90"),
    "bills": Decimal("0.60"),
    "portal": Decimal("0.55"),
    "manual": Decimal("0.40"),
}

_TWO_PLACES = Decimal("0.01")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class UsageProfile:
    """User's consumption pattern used as input for plan scoring.

    Attributes:
        monthly_kwh: Average monthly usage in kilowatt-hours.
        peak_kwh_pct: Fraction of usage occurring during peak hours (0–1).
        off_peak_kwh_pct: Fraction of usage occurring during off-peak hours (0–1).
        shoulder_kwh_pct: Fraction during shoulder period (0–1); default 0.
        data_source: Origin of usage data — determines base confidence.
            One of: arcadia_15min, arcadia_60min, utilityapi_15min,
            utilityapi_60min, bills, portal, manual.
        months_of_data: Number of full billing months represented in the
            profile. More months raises confidence (up to the cap).
    """

    monthly_kwh: Decimal
    peak_kwh_pct: Decimal = Decimal("0.40")
    off_peak_kwh_pct: Decimal = Decimal("0.60")
    shoulder_kwh_pct: Decimal = Decimal("0")
    data_source: str = "manual"
    months_of_data: int = 1


@dataclass
class RateStructure:
    """A plan's pricing structure.

    Attributes:
        rate_type: One of "flat", "tou", or "tiered".
        rate_kwh: Flat rate in dollars per kWh (used when rate_type == "flat").
        fixed_charge: Monthly fixed/service charge in dollars.
        peak_rate: Peak-period rate $/kWh (used when rate_type == "tou").
        off_peak_rate: Off-peak rate $/kWh (used when rate_type == "tou").
        shoulder_rate: Shoulder-period rate $/kWh (used when rate_type == "tou").
        tiers: List of tier dicts for rate_type == "tiered".
            Each dict: ``{"limit_kwh": <int|None>, "rate": <float>}``.
            ``limit_kwh=None`` marks the final (unlimited) tier.
    """

    rate_type: str
    rate_kwh: Decimal = Decimal("0")
    fixed_charge: Decimal = Decimal("0")

    # TOU-specific
    peak_rate: Decimal = Decimal("0")
    off_peak_rate: Decimal = Decimal("0")
    shoulder_rate: Decimal = Decimal("0")

    # Tiered-specific
    tiers: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PlanScore:
    """Result of scoring a single plan against a usage profile.

    Attributes:
        plan_id: Unique identifier for the plan.
        plan_name: Human-readable plan name.
        provider_name: Name of the electricity provider.
        projected_monthly_cost: Estimated monthly cost in dollars.
        projected_annual_cost: Estimated annual cost in dollars (monthly * 12).
        confidence: Scoring confidence between 0 and 1.
        rate_type: Rate structure type of the scored plan.
        breakdown: Itemised cost components for display/debugging.
    """

    plan_id: str
    plan_name: str
    provider_name: str
    projected_monthly_cost: Decimal
    projected_annual_cost: Decimal
    confidence: Decimal
    rate_type: str
    breakdown: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class PlanScorer:
    """Scores electricity plans against a user's usage profile.

    All monetary values are handled as ``Decimal`` to avoid floating-point
    drift in billing calculations. Results are rounded to 2 decimal places.

    Example:
        scorer = PlanScorer()
        usage = UsageProfile(monthly_kwh=Decimal("800"), data_source="bills")
        rate = RateStructure(rate_type="flat", rate_kwh=Decimal("0.12"))
        score = scorer.score_plan("p1", "Basic Plan", "ACME Energy", rate, usage)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_plan(
        self,
        plan_id: str,
        plan_name: str,
        provider_name: str,
        rate_structure: RateStructure,
        usage: UsageProfile,
    ) -> PlanScore:
        """Score a single plan against a usage profile.

        Args:
            plan_id: Unique plan identifier.
            plan_name: Human-readable plan name.
            provider_name: Name of the electricity provider.
            rate_structure: The plan's pricing structure.
            usage: The user's consumption profile.

        Returns:
            A ``PlanScore`` with projected costs, confidence, and a breakdown
            of cost components.
        """
        with traced(
            "plan_scorer.score_plan",
            attributes={
                "scorer.plan_id": plan_id,
                "scorer.rate_type": rate_structure.rate_type,
                "scorer.data_source": usage.data_source,
            },
        ):
            rate_type = rate_structure.rate_type

            if rate_type == "tou":
                monthly_cost = self._calc_tou_cost(rate_structure, usage)
                breakdown = self._tou_breakdown(rate_structure, usage)
            elif rate_type == "tiered":
                monthly_cost = self._calc_tiered_cost(rate_structure, usage)
                breakdown = {
                    "tiers": rate_structure.tiers,
                    "fixed_charge": float(rate_structure.fixed_charge),
                }
            else:
                # Default: flat rate
                monthly_cost = self._calc_flat_cost(rate_structure, usage)
                breakdown = {
                    "usage_cost": float(usage.monthly_kwh * rate_structure.rate_kwh),
                    "fixed_charge": float(rate_structure.fixed_charge),
                }

            monthly_cost = monthly_cost.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
            annual_cost = (monthly_cost * 12).quantize(
                _TWO_PLACES, rounding=ROUND_HALF_UP
            )
            confidence = self._calc_confidence(usage)

            logger.debug(
                "plan_scored",
                plan_id=plan_id,
                rate_type=rate_type,
                monthly_cost=str(monthly_cost),
                confidence=str(confidence),
                data_source=usage.data_source,
                months_of_data=usage.months_of_data,
            )

            return PlanScore(
                plan_id=plan_id,
                plan_name=plan_name,
                provider_name=provider_name,
                projected_monthly_cost=monthly_cost,
                projected_annual_cost=annual_cost,
                confidence=confidence,
                rate_type=rate_type,
                breakdown=breakdown,
            )

    def rank_plans(
        self,
        plans: list[tuple[str, str, str, RateStructure]],
        usage: UsageProfile,
    ) -> list[PlanScore]:
        """Score and rank multiple plans by projected monthly cost (ascending).

        Args:
            plans: List of ``(plan_id, plan_name, provider_name, rate_structure)``
                tuples to evaluate.
            usage: The user's consumption profile.

        Returns:
            List of ``PlanScore`` objects sorted cheapest-first.
        """
        scores = [
            self.score_plan(plan_id, plan_name, provider_name, rate_structure, usage)
            for plan_id, plan_name, provider_name, rate_structure in plans
        ]
        scores.sort(key=lambda s: s.projected_monthly_cost)
        return scores

    def compare_plans(
        self,
        current_score: PlanScore,
        proposed_score: PlanScore,
    ) -> dict[str, Any]:
        """Compare two plan scores and calculate potential savings.

        Args:
            current_score: The user's existing plan score.
            proposed_score: The candidate plan score.

        Returns:
            Dict with keys:
              - ``monthly_savings``: positive = savings, negative = more expensive
              - ``annual_savings``: monthly_savings * 12
              - ``savings_pct``: percentage reduction vs. current cost
              - ``confidence``: min of the two plan confidences
              - ``current_monthly``: projected cost for the current plan
              - ``proposed_monthly``: projected cost for the proposed plan
        """
        monthly_savings = (
            current_score.projected_monthly_cost - proposed_score.projected_monthly_cost
        )
        annual_savings = monthly_savings * 12

        if current_score.projected_monthly_cost > 0:
            savings_pct = (
                monthly_savings / current_score.projected_monthly_cost * 100
            ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            savings_pct = Decimal("0")

        # Use the lower of the two confidences — the weakest link determines
        # how much we trust the overall comparison.
        confidence = min(current_score.confidence, proposed_score.confidence)

        return {
            "monthly_savings": monthly_savings.quantize(_TWO_PLACES),
            "annual_savings": annual_savings.quantize(_TWO_PLACES),
            "savings_pct": savings_pct,
            "confidence": confidence,
            "current_monthly": current_score.projected_monthly_cost,
            "proposed_monthly": proposed_score.projected_monthly_cost,
        }

    # ------------------------------------------------------------------
    # Private calculation helpers
    # ------------------------------------------------------------------

    def _calc_flat_cost(self, rate: RateStructure, usage: UsageProfile) -> Decimal:
        """Calculate monthly cost for a flat-rate plan.

        Args:
            rate: Rate structure with ``rate_kwh`` and ``fixed_charge``.
            usage: User's usage profile.

        Returns:
            Total monthly cost as ``Decimal``.
        """
        return usage.monthly_kwh * rate.rate_kwh + rate.fixed_charge

    def _calc_tou_cost(self, rate: RateStructure, usage: UsageProfile) -> Decimal:
        """Calculate monthly cost for a time-of-use plan.

        Splits monthly_kwh by peak/off-peak/shoulder fractions and applies
        the corresponding period rates.

        Args:
            rate: Rate structure with ``peak_rate``, ``off_peak_rate``,
                ``shoulder_rate``, and ``fixed_charge``.
            usage: User's usage profile with period percentage splits.

        Returns:
            Total monthly cost as ``Decimal``.
        """
        peak_cost = usage.monthly_kwh * usage.peak_kwh_pct * rate.peak_rate
        off_peak_cost = usage.monthly_kwh * usage.off_peak_kwh_pct * rate.off_peak_rate
        shoulder_cost = usage.monthly_kwh * usage.shoulder_kwh_pct * rate.shoulder_rate
        return peak_cost + off_peak_cost + shoulder_cost + rate.fixed_charge

    def _calc_tiered_cost(self, rate: RateStructure, usage: UsageProfile) -> Decimal:
        """Calculate monthly cost for a tiered-rate plan.

        Iterates through tiers in order, consuming usage at each tier's rate
        until usage is exhausted or all tiers are processed.  A tier with
        ``limit_kwh=None`` is treated as the unlimited final tier.

        If usage exceeds all defined tier limits and no unlimited tier exists,
        any remaining usage is billed at the last defined tier's rate.

        Args:
            rate: Rate structure with a ``tiers`` list and ``fixed_charge``.
            usage: User's usage profile.

        Returns:
            Total monthly cost as ``Decimal``.
        """
        remaining = usage.monthly_kwh
        total_cost = rate.fixed_charge

        for tier in rate.tiers:
            if remaining <= 0:
                break

            tier_limit = tier.get("limit_kwh")
            tier_rate = Decimal(str(tier.get("rate", 0)))

            if tier_limit is None:
                # Unlimited final tier — consume all remaining usage
                total_cost += remaining * tier_rate
                remaining = Decimal("0")
                break

            tier_limit_dec = Decimal(str(tier_limit))
            tier_usage = min(remaining, tier_limit_dec)
            total_cost += tier_usage * tier_rate
            remaining -= tier_usage

        # Overflow: remaining usage beyond all explicit tier limits
        if remaining > 0 and rate.tiers:
            last_rate = Decimal(str(rate.tiers[-1].get("rate", 0)))
            total_cost += remaining * last_rate

        return total_cost

    def _calc_confidence(self, usage: UsageProfile) -> Decimal:
        """Calculate confidence score for a usage profile.

        Base confidence comes from data_source quality. Months of data
        provides a linear boost from 0.7× to 1.0× of the base value,
        reaching maximum multiplier at 6 months of data.

        Formula:
            confidence = base * (0.7 + 0.3 * min(months / 6, 1.0))
            confidence = min(confidence, 1.0)

        Args:
            usage: The user's usage profile.

        Returns:
            Confidence value between 0 and 1, rounded to 2 decimal places.
        """
        base = DATA_SOURCE_CONFIDENCE.get(usage.data_source, Decimal("0.40"))
        months_factor = min(
            Decimal(str(usage.months_of_data)) / Decimal("6"),
            Decimal("1.0"),
        )
        confidence = base * (Decimal("0.7") + Decimal("0.3") * months_factor)
        confidence = min(confidence, Decimal("1.0"))
        return confidence.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    def _tou_breakdown(
        self, rate: RateStructure, usage: UsageProfile
    ) -> dict[str, Any]:
        """Build a cost breakdown dict for a TOU plan.

        Args:
            rate: TOU rate structure.
            usage: User's usage profile.

        Returns:
            Dict with itemised cost components as floats.
        """
        return {
            "peak_cost": float(usage.monthly_kwh * usage.peak_kwh_pct * rate.peak_rate),
            "off_peak_cost": float(
                usage.monthly_kwh * usage.off_peak_kwh_pct * rate.off_peak_rate
            ),
            "shoulder_cost": float(
                usage.monthly_kwh * usage.shoulder_kwh_pct * rate.shoulder_rate
            ),
            "fixed_charge": float(rate.fixed_charge),
        }
