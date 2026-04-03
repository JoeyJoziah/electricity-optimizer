"""
Tests for PlanScorer — Rate Structure Matching Engine

Covers flat, TOU, and tiered rate calculations, confidence scoring,
plan ranking, and plan comparison.
"""

from decimal import Decimal

import pytest

from services.plan_scorer import (
    PlanScore,
    PlanScorer,
    RateStructure,
    UsageProfile,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scorer() -> PlanScorer:
    """Return a fresh PlanScorer instance."""
    return PlanScorer()


def _flat(rate_kwh: str, fixed_charge: str = "0") -> RateStructure:
    """Convenience factory for flat-rate structures."""
    return RateStructure(
        rate_type="flat",
        rate_kwh=Decimal(rate_kwh),
        fixed_charge=Decimal(fixed_charge),
    )


def _tou(
    peak_rate: str,
    off_peak_rate: str,
    shoulder_rate: str = "0",
    fixed_charge: str = "0",
) -> RateStructure:
    """Convenience factory for TOU rate structures."""
    return RateStructure(
        rate_type="tou",
        peak_rate=Decimal(peak_rate),
        off_peak_rate=Decimal(off_peak_rate),
        shoulder_rate=Decimal(shoulder_rate),
        fixed_charge=Decimal(fixed_charge),
    )


def _tiered(tiers: list[dict], fixed_charge: str = "0") -> RateStructure:
    """Convenience factory for tiered rate structures."""
    return RateStructure(
        rate_type="tiered",
        tiers=tiers,
        fixed_charge=Decimal(fixed_charge),
    )


def _usage(
    kwh: str,
    data_source: str = "manual",
    months: int = 1,
    peak_pct: str = "0.40",
    off_peak_pct: str = "0.60",
    shoulder_pct: str = "0",
) -> UsageProfile:
    """Convenience factory for UsageProfile."""
    return UsageProfile(
        monthly_kwh=Decimal(kwh),
        peak_kwh_pct=Decimal(peak_pct),
        off_peak_kwh_pct=Decimal(off_peak_pct),
        shoulder_kwh_pct=Decimal(shoulder_pct),
        data_source=data_source,
        months_of_data=months,
    )


def _score(
    scorer: PlanScorer,
    rate: RateStructure,
    usage: UsageProfile,
    plan_id: str = "p1",
) -> PlanScore:
    """Thin wrapper so tests don't have to repeat boilerplate strings."""
    return scorer.score_plan(plan_id, "Test Plan", "Test Provider", rate, usage)


# ===========================================================================
# 1. Flat rate — basic calculation
# ===========================================================================


def test_flat_rate_basic(scorer):
    """800 kWh at $0.10/kWh = $80.00."""
    rate = _flat("0.10")
    usage = _usage("800")
    result = _score(scorer, rate, usage)

    assert result.projected_monthly_cost == Decimal("80.00")
    assert result.projected_annual_cost == Decimal("960.00")
    assert result.rate_type == "flat"


# ===========================================================================
# 2. Flat rate — with fixed charge
# ===========================================================================


def test_flat_rate_with_fixed_charge(scorer):
    """800 kWh * $0.10 + $9.95 fixed = $89.95."""
    rate = _flat("0.10", fixed_charge="9.95")
    usage = _usage("800")
    result = _score(scorer, rate, usage)

    assert result.projected_monthly_cost == Decimal("89.95")
    assert result.projected_annual_cost == Decimal("89.95") * 12


# ===========================================================================
# 3. Flat rate — zero usage
# ===========================================================================


def test_flat_rate_zero_usage(scorer):
    """Zero usage: only fixed charge should be billed."""
    rate = _flat("0.12", fixed_charge="7.50")
    usage = _usage("0")
    result = _score(scorer, rate, usage)

    assert result.projected_monthly_cost == Decimal("7.50")
    assert result.projected_annual_cost == Decimal("90.00")


# ===========================================================================
# 4. TOU — default peak/off-peak split (40% peak, 60% off-peak)
# ===========================================================================


def test_tou_default_split(scorer):
    """800 kWh, 40% peak at $0.15, 60% off-peak at $0.08.

    Expected: 320*0.15 + 480*0.08 = 48.00 + 38.40 = $86.40
    """
    rate = _tou(peak_rate="0.15", off_peak_rate="0.08")
    usage = _usage("800")
    result = _score(scorer, rate, usage)

    assert result.projected_monthly_cost == Decimal("86.40")
    assert result.rate_type == "tou"


# ===========================================================================
# 5. TOU — off-peak heavy user (should be cheaper than a peak-heavy user)
# ===========================================================================


def test_tou_off_peak_heavy_cheaper(scorer):
    """Off-peak heavy usage should produce lower cost than peak-heavy."""
    rate = _tou(peak_rate="0.20", off_peak_rate="0.07")

    off_peak_heavy = _usage("1000", peak_pct="0.10", off_peak_pct="0.90")
    peak_heavy = _usage("1000", peak_pct="0.90", off_peak_pct="0.10")

    cost_off_peak = _score(scorer, rate, off_peak_heavy).projected_monthly_cost
    cost_peak = _score(scorer, rate, peak_heavy).projected_monthly_cost

    assert cost_off_peak < cost_peak


# ===========================================================================
# 6. TOU — peak heavy user (should be more expensive)
# ===========================================================================


def test_tou_peak_heavy_more_expensive(scorer):
    """Peak-heavy user (90% peak) is more expensive than default split."""
    rate = _tou(peak_rate="0.20", off_peak_rate="0.07")

    default_split = _usage("1000")
    peak_heavy = _usage("1000", peak_pct="0.90", off_peak_pct="0.10")

    cost_default = _score(scorer, rate, default_split).projected_monthly_cost
    cost_peak = _score(scorer, rate, peak_heavy).projected_monthly_cost

    assert cost_peak > cost_default


# ===========================================================================
# 7. TOU — with shoulder period
# ===========================================================================


def test_tou_with_shoulder_period(scorer):
    """Verify shoulder period contributes to cost.

    800 kWh: 30% peak ($0.18), 50% off-peak ($0.08), 20% shoulder ($0.11).
    Expected: 240*0.18 + 400*0.08 + 160*0.11 + $5 fixed
             = 43.20 + 32.00 + 17.60 + 5.00 = $97.80
    """
    rate = _tou(
        peak_rate="0.18",
        off_peak_rate="0.08",
        shoulder_rate="0.11",
        fixed_charge="5.00",
    )
    usage = _usage(
        "800",
        peak_pct="0.30",
        off_peak_pct="0.50",
        shoulder_pct="0.20",
    )
    result = _score(scorer, rate, usage)

    assert result.projected_monthly_cost == Decimal("97.80")
    assert result.breakdown["shoulder_cost"] == pytest.approx(17.60, abs=1e-6)


# ===========================================================================
# 8. Tiered — under first tier
# ===========================================================================


def test_tiered_under_first_tier(scorer):
    """300 kWh all falls within the 500 kWh first tier at $0.08."""
    rate = _tiered(
        tiers=[
            {"limit_kwh": 500, "rate": 0.08},
            {"limit_kwh": None, "rate": 0.14},
        ]
    )
    usage = _usage("300")
    result = _score(scorer, rate, usage)

    assert result.projected_monthly_cost == Decimal("24.00")


# ===========================================================================
# 9. Tiered — spanning two tiers
# ===========================================================================


def test_tiered_spanning_two_tiers(scorer):
    """700 kWh: first 500 at $0.08, remaining 200 at $0.14.

    Expected: 500*0.08 + 200*0.14 = 40.00 + 28.00 = $68.00
    """
    rate = _tiered(
        tiers=[
            {"limit_kwh": 500, "rate": 0.08},
            {"limit_kwh": None, "rate": 0.14},
        ]
    )
    usage = _usage("700")
    result = _score(scorer, rate, usage)

    assert result.projected_monthly_cost == Decimal("68.00")


# ===========================================================================
# 10. Tiered — spanning all three tiers
# ===========================================================================


def test_tiered_spanning_all_tiers(scorer):
    """1100 kWh across 3 tiers.

    Tier 1: 500 kWh at $0.07 = $35.00
    Tier 2: 500 kWh at $0.10 = $50.00 (limit from 500→1000)
    Tier 3: 100 kWh at $0.15 = $15.00 (unlimited)
    Total: $100.00
    """
    rate = _tiered(
        tiers=[
            {"limit_kwh": 500, "rate": 0.07},
            {"limit_kwh": 500, "rate": 0.10},
            {"limit_kwh": None, "rate": 0.15},
        ]
    )
    usage = _usage("1100")
    result = _score(scorer, rate, usage)

    assert result.projected_monthly_cost == Decimal("100.00")


# ===========================================================================
# 11. Tiered — no final unlimited tier (overflow falls to last tier rate)
# ===========================================================================


def test_tiered_no_final_unlimited_tier(scorer):
    """When no unlimited tier is defined, overflow uses the last tier's rate.

    Tier 1: 500 kWh at $0.08  →  $40.00
    Remaining: 300 kWh at last defined rate $0.13  →  $39.00
    Total: $79.00
    """
    rate = _tiered(
        tiers=[
            {"limit_kwh": 500, "rate": 0.08},
            {"limit_kwh": 200, "rate": 0.13},
        ]
    )
    # 500 + 200 = 700 kWh covered, but usage is 800 → 100 kWh overflow
    usage = _usage("800")
    result = _score(scorer, rate, usage)

    # 500*0.08 + 200*0.13 + 100*0.13 = 40.00 + 26.00 + 13.00 = $79.00
    assert result.projected_monthly_cost == Decimal("79.00")


# ===========================================================================
# 12. Confidence — arcadia_15min → 0.95 base, 1 month → lower multiplier
# ===========================================================================


def test_confidence_arcadia_15min_one_month(scorer):
    """arcadia_15min at 1 month: base=0.95, factor=1/6≈0.1667.

    confidence = 0.95 * (0.7 + 0.3 * 0.1667) ≈ 0.95 * 0.75 = 0.71
    """
    rate = _flat("0.10")
    usage = _usage("500", data_source="arcadia_15min", months=1)
    result = _score(scorer, rate, usage)

    # At 1 month: factor = min(1/6, 1.0) ≈ 0.1667
    # confidence = 0.95 * (0.7 + 0.3 * 0.1667) = 0.95 * 0.75 ≈ 0.71
    assert Decimal("0.70") <= result.confidence <= Decimal("0.72")


# ===========================================================================
# 13. Confidence — bills → 0.60 base
# ===========================================================================


def test_confidence_bills_data_source(scorer):
    """bills source: base confidence = 0.60."""
    rate = _flat("0.10")
    usage = _usage("500", data_source="bills", months=1)
    result = _score(scorer, rate, usage)

    # 0.60 * (0.7 + 0.3 * 1/6) = 0.60 * 0.75 = 0.45
    assert Decimal("0.44") <= result.confidence <= Decimal("0.46")


# ===========================================================================
# 14. Confidence — manual → 0.40 base
# ===========================================================================


def test_confidence_manual_data_source(scorer):
    """manual source: base confidence = 0.40."""
    rate = _flat("0.10")
    usage = _usage("500", data_source="manual", months=1)
    result = _score(scorer, rate, usage)

    # 0.40 * (0.7 + 0.3 * 1/6) = 0.40 * 0.75 = 0.30
    assert Decimal("0.29") <= result.confidence <= Decimal("0.31")


# ===========================================================================
# 15. Confidence boost with 6+ months of data
# ===========================================================================


def test_confidence_boost_six_months(scorer):
    """Six months maximises the months_factor multiplier.

    confidence = base * (0.7 + 0.3 * 1.0) = base * 1.0 = base
    """
    rate = _flat("0.10")
    usage_one_month = _usage("500", data_source="bills", months=1)
    usage_six_months = _usage("500", data_source="bills", months=6)

    conf_one = _score(scorer, rate, usage_one_month).confidence
    conf_six = _score(scorer, rate, usage_six_months).confidence

    assert conf_six > conf_one
    # At 6 months, confidence == base (0.60 rounded)
    assert conf_six == Decimal("0.60")


# ===========================================================================
# 16. Confidence capped at 1.0
# ===========================================================================


def test_confidence_capped_at_one(scorer):
    """Confidence must never exceed 1.0 regardless of data source or months."""
    rate = _flat("0.10")
    # arcadia_15min base = 0.95; at 6 months factor = 1.0 → 0.95 * 1.0 = 0.95
    # Even with an artificially high months value it must not exceed 1.0
    usage = _usage("500", data_source="arcadia_15min", months=100)
    result = _score(scorer, rate, usage)

    assert result.confidence <= Decimal("1.0")
    # At max months_factor the cap is just the base value (0.95)
    assert result.confidence == Decimal("0.95")


# ===========================================================================
# 17. rank_plans returns plans sorted by projected cost ascending
# ===========================================================================


def test_rank_plans_sorted_ascending(scorer):
    """rank_plans should order plans from cheapest to most expensive."""
    usage = _usage("800", data_source="bills", months=3)

    plans = [
        ("p3", "Expensive Plan", "Provider C", _flat("0.20")),
        ("p1", "Cheap Plan", "Provider A", _flat("0.08")),
        ("p2", "Mid Plan", "Provider B", _flat("0.12")),
    ]

    ranked = scorer.rank_plans(plans, usage)

    assert len(ranked) == 3
    assert ranked[0].plan_id == "p1"
    assert ranked[1].plan_id == "p2"
    assert ranked[2].plan_id == "p3"
    # Costs are strictly increasing
    assert ranked[0].projected_monthly_cost < ranked[1].projected_monthly_cost
    assert ranked[1].projected_monthly_cost < ranked[2].projected_monthly_cost


# ===========================================================================
# 18. rank_plans with an empty list
# ===========================================================================


def test_rank_plans_empty_list(scorer):
    """rank_plans on an empty input should return an empty list."""
    usage = _usage("800")
    ranked = scorer.rank_plans([], usage)

    assert ranked == []


# ===========================================================================
# 19. compare_plans calculates savings correctly
# ===========================================================================


def test_compare_plans_calculates_savings(scorer):
    """Switching from $120/mo to $90/mo should show $30 monthly savings."""
    usage = _usage("1000", data_source="bills", months=6)

    current = scorer.score_plan("cur", "Old Plan", "Old Co", _flat("0.12"), usage)
    proposed = scorer.score_plan("new", "New Plan", "New Co", _flat("0.09"), usage)

    comparison = scorer.compare_plans(current, proposed)

    assert comparison["monthly_savings"] == Decimal("30.00")
    assert comparison["annual_savings"] == Decimal("360.00")
    assert comparison["savings_pct"] == Decimal("25.00")
    assert comparison["current_monthly"] == Decimal("120.00")
    assert comparison["proposed_monthly"] == Decimal("90.00")
    # Confidence is the min of the two (both same source here, so equal)
    assert comparison["confidence"] == current.confidence


# ===========================================================================
# 20. compare_plans with zero current cost (avoids division by zero)
# ===========================================================================


def test_compare_plans_zero_current_cost(scorer):
    """When current cost is $0.00, savings_pct must be 0 (no division by zero)."""
    usage = _usage("0", data_source="manual", months=1)

    current = scorer.score_plan("cur", "Zero Plan", "Zero Co", _flat("0.12"), usage)
    proposed = scorer.score_plan("new", "New Plan", "New Co", _flat("0.09"), usage)

    assert current.projected_monthly_cost == Decimal("0.00")

    comparison = scorer.compare_plans(current, proposed)

    assert comparison["savings_pct"] == Decimal("0")
    assert comparison["monthly_savings"] == Decimal("0.00")
    assert comparison["annual_savings"] == Decimal("0.00")
