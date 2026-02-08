"""
Supplier Switching Decision Engine

Analyzes electricity tariffs and consumption patterns to recommend
optimal supplier switches based on predicted cost savings.

Features:
- Tariff comparison analysis
- Break-even calculation
- Switching benefit projection
- Risk assessment
- Personalized recommendations

Target: Identify savings opportunities > 5% of annual bill
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TariffType(Enum):
    """Types of electricity tariffs."""
    FIXED_RATE = "fixed_rate"
    VARIABLE_RATE = "variable_rate"
    TIME_OF_USE = "time_of_use"
    DYNAMIC = "dynamic"
    GREEN = "green"


class RiskLevel(Enum):
    """Risk levels for switching decisions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Tariff:
    """
    Represents an electricity tariff.

    Attributes:
        id: Unique identifier
        supplier: Supplier name
        name: Tariff name
        tariff_type: Type of tariff
        unit_rate: Base rate per kWh (USD or currency)
        standing_charge: Daily standing charge
        peak_rate: Peak rate for TOU tariffs (optional)
        off_peak_rate: Off-peak rate for TOU tariffs (optional)
        peak_hours: Peak hours for TOU tariffs (optional)
        exit_fee: Early exit fee (if applicable)
        contract_length_months: Contract length
        renewable_percentage: Percentage from renewable sources
        fixed_until: Date until which rate is fixed (optional)
    """
    id: str
    supplier: str
    name: str
    tariff_type: TariffType
    unit_rate: float
    standing_charge: float
    peak_rate: Optional[float] = None
    off_peak_rate: Optional[float] = None
    peak_hours: Optional[List[Tuple[int, int]]] = None
    exit_fee: float = 0.0
    contract_length_months: int = 12
    renewable_percentage: float = 0.0
    fixed_until: Optional[datetime] = None

    def calculate_cost(
        self,
        consumption_kwh: float,
        days: int = 365,
        peak_fraction: float = 0.4
    ) -> float:
        """
        Calculate total cost for given consumption.

        Args:
            consumption_kwh: Total consumption in kWh
            days: Number of days
            peak_fraction: Fraction of consumption during peak hours

        Returns:
            Total cost in currency units
        """
        standing = self.standing_charge * days

        if self.tariff_type == TariffType.TIME_OF_USE and self.peak_rate and self.off_peak_rate:
            peak_consumption = consumption_kwh * peak_fraction
            off_peak_consumption = consumption_kwh * (1 - peak_fraction)
            energy_cost = (
                peak_consumption * self.peak_rate +
                off_peak_consumption * self.off_peak_rate
            )
        else:
            energy_cost = consumption_kwh * self.unit_rate

        return standing + energy_cost

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'supplier': self.supplier,
            'name': self.name,
            'tariff_type': self.tariff_type.value,
            'unit_rate': self.unit_rate,
            'standing_charge': self.standing_charge,
            'peak_rate': self.peak_rate,
            'off_peak_rate': self.off_peak_rate,
            'peak_hours': self.peak_hours,
            'exit_fee': self.exit_fee,
            'contract_length_months': self.contract_length_months,
            'renewable_percentage': self.renewable_percentage,
            'fixed_until': str(self.fixed_until) if self.fixed_until else None
        }


@dataclass
class ConsumptionProfile:
    """
    User's electricity consumption profile.

    Attributes:
        annual_consumption_kwh: Total annual consumption
        monthly_consumption: Monthly breakdown (optional)
        hourly_pattern: Hourly consumption pattern (24 values, normalized)
        peak_fraction: Fraction consumed during typical peak hours
        has_ev: Whether household has EV
        has_heat_pump: Whether household has heat pump
        has_solar: Whether household has solar panels
        flexible_load_fraction: Fraction of load that can be shifted
    """
    annual_consumption_kwh: float
    monthly_consumption: Optional[List[float]] = None
    hourly_pattern: Optional[List[float]] = None
    peak_fraction: float = 0.4
    has_ev: bool = False
    has_heat_pump: bool = False
    has_solar: bool = False
    flexible_load_fraction: float = 0.2

    def __post_init__(self):
        """Validate and set defaults."""
        if self.monthly_consumption is None:
            # Default seasonal pattern (higher in winter)
            self.monthly_consumption = [
                self.annual_consumption_kwh * w for w in
                [0.11, 0.10, 0.09, 0.08, 0.07, 0.06,
                 0.06, 0.07, 0.08, 0.09, 0.10, 0.09]
            ]

        if self.hourly_pattern is None:
            # Default daily pattern
            self.hourly_pattern = [
                0.02, 0.02, 0.02, 0.02, 0.02, 0.03,
                0.04, 0.06, 0.06, 0.05, 0.04, 0.04,
                0.04, 0.04, 0.04, 0.04, 0.05, 0.07,
                0.08, 0.07, 0.06, 0.05, 0.04, 0.03
            ]


@dataclass
class SwitchingRecommendation:
    """
    Recommendation for switching to a new tariff.

    Attributes:
        recommended_tariff: The recommended tariff
        current_annual_cost: Current annual cost
        projected_annual_cost: Projected cost with new tariff
        annual_savings: Annual savings amount
        savings_percentage: Savings as percentage
        payback_months: Months to recover any switching costs
        risk_level: Risk assessment
        confidence: Confidence in recommendation (0-1)
        reasons: List of reasons for recommendation
        warnings: List of potential concerns
        switching_costs: One-time switching costs
    """
    recommended_tariff: Tariff
    current_annual_cost: float
    projected_annual_cost: float
    annual_savings: float
    savings_percentage: float
    payback_months: float
    risk_level: RiskLevel
    confidence: float
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    switching_costs: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'recommended_tariff': self.recommended_tariff.to_dict(),
            'current_annual_cost': self.current_annual_cost,
            'projected_annual_cost': self.projected_annual_cost,
            'annual_savings': self.annual_savings,
            'savings_percentage': self.savings_percentage,
            'payback_months': self.payback_months,
            'risk_level': self.risk_level.value,
            'confidence': self.confidence,
            'reasons': self.reasons,
            'warnings': self.warnings,
            'switching_costs': self.switching_costs
        }

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "=" * 60,
            "SWITCHING RECOMMENDATION",
            "=" * 60,
            "",
            f"Recommended: {self.recommended_tariff.supplier} - {self.recommended_tariff.name}",
            "",
            "FINANCIAL SUMMARY:",
            f"  Current Annual Cost:   {self.current_annual_cost:>10.2f}",
            f"  Projected Annual Cost: {self.projected_annual_cost:>10.2f}",
            f"  Annual Savings:        {self.annual_savings:>10.2f} ({self.savings_percentage:.1f}%)",
            f"  Payback Period:        {self.payback_months:.1f} months",
            "",
            f"Risk Level: {self.risk_level.value.upper()}",
            f"Confidence: {self.confidence:.0%}",
        ]

        if self.reasons:
            lines.extend(["", "REASONS:"])
            for reason in self.reasons:
                lines.append(f"  + {reason}")

        if self.warnings:
            lines.extend(["", "WARNINGS:"])
            for warning in self.warnings:
                lines.append(f"  ! {warning}")

        lines.append("=" * 60)
        return "\n".join(lines)


class SupplierSwitchingEngine:
    """
    Engine for analyzing and recommending supplier switches.

    Analyzes current tariff, consumption patterns, and available
    alternatives to recommend optimal switching decisions.
    """

    def __init__(
        self,
        min_savings_threshold: float = 0.05,
        max_risk_tolerance: RiskLevel = RiskLevel.MEDIUM,
        prefer_renewable: bool = False,
        renewable_premium_tolerance: float = 0.05
    ):
        """
        Initialize the switching engine.

        Args:
            min_savings_threshold: Minimum savings percentage to recommend switch
            max_risk_tolerance: Maximum acceptable risk level
            prefer_renewable: Prefer renewable tariffs
            renewable_premium_tolerance: Maximum premium willing to pay for renewable
        """
        self.min_savings_threshold = min_savings_threshold
        self.max_risk_tolerance = max_risk_tolerance
        self.prefer_renewable = prefer_renewable
        self.renewable_premium_tolerance = renewable_premium_tolerance

    def analyze_tariff(
        self,
        tariff: Tariff,
        profile: ConsumptionProfile
    ) -> Dict[str, Any]:
        """
        Analyze a tariff for a consumption profile.

        Args:
            tariff: Tariff to analyze
            profile: User's consumption profile

        Returns:
            Dictionary with analysis results
        """
        annual_cost = tariff.calculate_cost(
            consumption_kwh=profile.annual_consumption_kwh,
            days=365,
            peak_fraction=profile.peak_fraction
        )

        # Calculate monthly costs
        monthly_costs = []
        for i, monthly_kwh in enumerate(profile.monthly_consumption):
            days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][i]
            cost = tariff.calculate_cost(
                consumption_kwh=monthly_kwh,
                days=days_in_month,
                peak_fraction=profile.peak_fraction
            )
            monthly_costs.append(cost)

        # Assess risk
        risk = self._assess_tariff_risk(tariff)

        # Calculate effective rate
        if profile.annual_consumption_kwh > 0:
            effective_rate = annual_cost / profile.annual_consumption_kwh
        else:
            effective_rate = 0.0

        return {
            'tariff': tariff,
            'annual_cost': annual_cost,
            'monthly_costs': monthly_costs,
            'effective_rate': effective_rate,
            'risk_level': risk,
            'is_renewable': tariff.renewable_percentage > 0
        }

    def _assess_tariff_risk(self, tariff: Tariff) -> RiskLevel:
        """Assess risk level of a tariff."""
        if tariff.tariff_type == TariffType.FIXED_RATE:
            return RiskLevel.LOW
        elif tariff.tariff_type == TariffType.VARIABLE_RATE:
            return RiskLevel.MEDIUM
        elif tariff.tariff_type == TariffType.DYNAMIC:
            return RiskLevel.HIGH
        elif tariff.tariff_type == TariffType.TIME_OF_USE:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.MEDIUM

    def compare_tariffs(
        self,
        current_tariff: Tariff,
        alternatives: List[Tariff],
        profile: ConsumptionProfile
    ) -> List[SwitchingRecommendation]:
        """
        Compare current tariff with alternatives.

        Args:
            current_tariff: User's current tariff
            alternatives: List of alternative tariffs
            profile: User's consumption profile

        Returns:
            List of recommendations sorted by savings
        """
        current_analysis = self.analyze_tariff(current_tariff, profile)
        current_cost = current_analysis['annual_cost']

        recommendations = []

        for alt_tariff in alternatives:
            if alt_tariff.id == current_tariff.id:
                continue

            alt_analysis = self.analyze_tariff(alt_tariff, profile)
            alt_cost = alt_analysis['annual_cost']

            savings = current_cost - alt_cost
            savings_pct = (savings / current_cost) * 100 if current_cost > 0 else 0

            # Skip if savings below threshold
            if savings_pct < self.min_savings_threshold * 100:
                continue

            # Skip if risk too high
            alt_risk = alt_analysis['risk_level']
            if alt_risk == RiskLevel.HIGH and self.max_risk_tolerance != RiskLevel.HIGH:
                continue

            # Calculate payback
            switching_costs = current_tariff.exit_fee
            payback_months = (switching_costs / savings * 12) if savings > 0 else float('inf')

            # Determine confidence
            confidence = self._calculate_confidence(
                current_tariff,
                alt_tariff,
                savings_pct,
                payback_months
            )

            # Build reasons and warnings
            reasons = self._generate_reasons(
                current_tariff,
                alt_tariff,
                savings,
                savings_pct,
                profile
            )

            warnings = self._generate_warnings(
                current_tariff,
                alt_tariff,
                alt_analysis,
                profile
            )

            recommendation = SwitchingRecommendation(
                recommended_tariff=alt_tariff,
                current_annual_cost=current_cost,
                projected_annual_cost=alt_cost,
                annual_savings=savings,
                savings_percentage=savings_pct,
                payback_months=payback_months,
                risk_level=alt_risk,
                confidence=confidence,
                reasons=reasons,
                warnings=warnings,
                switching_costs=switching_costs
            )

            recommendations.append(recommendation)

        # Sort by savings
        recommendations.sort(key=lambda r: r.annual_savings, reverse=True)

        return recommendations

    def _calculate_confidence(
        self,
        current: Tariff,
        alternative: Tariff,
        savings_pct: float,
        payback_months: float
    ) -> float:
        """Calculate confidence in recommendation."""
        confidence = 0.5

        # Higher savings = higher confidence
        if savings_pct >= 15:
            confidence += 0.2
        elif savings_pct >= 10:
            confidence += 0.15
        elif savings_pct >= 5:
            confidence += 0.1

        # Short payback = higher confidence
        if payback_months <= 1:
            confidence += 0.15
        elif payback_months <= 3:
            confidence += 0.1
        elif payback_months <= 6:
            confidence += 0.05

        # Fixed rate = higher confidence
        if alternative.tariff_type == TariffType.FIXED_RATE:
            confidence += 0.1

        # No exit fee = higher confidence
        if current.exit_fee == 0:
            confidence += 0.05

        return min(confidence, 0.95)

    def _generate_reasons(
        self,
        current: Tariff,
        alternative: Tariff,
        savings: float,
        savings_pct: float,
        profile: ConsumptionProfile
    ) -> List[str]:
        """Generate reasons for recommendation."""
        reasons = []

        reasons.append(f"Save {savings:.2f} per year ({savings_pct:.1f}%)")

        if alternative.unit_rate < current.unit_rate:
            rate_diff = current.unit_rate - alternative.unit_rate
            reasons.append(f"Lower unit rate by {rate_diff:.4f}/kWh")

        if alternative.standing_charge < current.standing_charge:
            reasons.append("Lower standing charge")

        if alternative.tariff_type == TariffType.FIXED_RATE:
            reasons.append("Fixed rate protects against price increases")

        if alternative.renewable_percentage > current.renewable_percentage:
            reasons.append(f"Higher renewable content ({alternative.renewable_percentage}%)")

        if (alternative.tariff_type == TariffType.TIME_OF_USE and
                profile.flexible_load_fraction > 0.2):
            reasons.append("TOU tariff suits your flexible consumption")

        return reasons

    def _generate_warnings(
        self,
        current: Tariff,
        alternative: Tariff,
        alt_analysis: Dict,
        profile: ConsumptionProfile
    ) -> List[str]:
        """Generate warnings for recommendation."""
        warnings = []

        if current.exit_fee > 0:
            warnings.append(f"Exit fee of {current.exit_fee:.2f} applies")

        if alternative.tariff_type == TariffType.VARIABLE_RATE:
            warnings.append("Variable rate may increase")

        if alternative.tariff_type == TariffType.DYNAMIC:
            warnings.append("Dynamic pricing can be volatile")

        if (alternative.tariff_type == TariffType.TIME_OF_USE and
                profile.peak_fraction > 0.5):
            warnings.append("High peak usage may reduce TOU savings")

        if alternative.contract_length_months > current.contract_length_months:
            warnings.append(f"Longer contract ({alternative.contract_length_months} months)")

        if alt_analysis['risk_level'] == RiskLevel.HIGH:
            warnings.append("Higher risk tariff")

        return warnings

    def get_best_recommendation(
        self,
        current_tariff: Tariff,
        alternatives: List[Tariff],
        profile: ConsumptionProfile
    ) -> Optional[SwitchingRecommendation]:
        """
        Get the single best switching recommendation.

        Args:
            current_tariff: User's current tariff
            alternatives: List of alternative tariffs
            profile: User's consumption profile

        Returns:
            Best recommendation or None if no beneficial switch found
        """
        recommendations = self.compare_tariffs(
            current_tariff,
            alternatives,
            profile
        )

        if not recommendations:
            return None

        # Filter by confidence and risk
        valid_recs = [
            r for r in recommendations
            if r.confidence >= 0.5 and r.payback_months <= 6
        ]

        if self.prefer_renewable:
            renewable_recs = [
                r for r in valid_recs
                if r.recommended_tariff.renewable_percentage > 50
            ]
            if renewable_recs:
                # Allow slightly lower savings for renewable
                return renewable_recs[0]

        return valid_recs[0] if valid_recs else recommendations[0]

    def should_switch(
        self,
        current_tariff: Tariff,
        alternatives: List[Tariff],
        profile: ConsumptionProfile
    ) -> Tuple[bool, Optional[SwitchingRecommendation]]:
        """
        Determine if switching is recommended.

        Args:
            current_tariff: User's current tariff
            alternatives: List of alternative tariffs
            profile: User's consumption profile

        Returns:
            Tuple of (should_switch, recommendation)
        """
        rec = self.get_best_recommendation(
            current_tariff,
            alternatives,
            profile
        )

        if rec is None:
            return False, None

        # Check criteria
        should = (
            rec.savings_percentage >= self.min_savings_threshold * 100 and
            rec.payback_months <= 12 and
            rec.confidence >= 0.5
        )

        return should, rec


def create_sample_tariffs() -> List[Tariff]:
    """Create sample tariffs for testing."""
    return [
        Tariff(
            id="fixed_standard",
            supplier="BigEnergy",
            name="Standard Fixed",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.28,
            standing_charge=0.45,
            contract_length_months=12,
            renewable_percentage=0
        ),
        Tariff(
            id="variable_flex",
            supplier="FlexPower",
            name="Flexible Variable",
            tariff_type=TariffType.VARIABLE_RATE,
            unit_rate=0.25,
            standing_charge=0.40,
            contract_length_months=0,
            renewable_percentage=20
        ),
        Tariff(
            id="tou_smart",
            supplier="SmartEnergy",
            name="Smart Time-of-Use",
            tariff_type=TariffType.TIME_OF_USE,
            unit_rate=0.22,
            standing_charge=0.50,
            peak_rate=0.35,
            off_peak_rate=0.12,
            peak_hours=[(16, 21)],
            contract_length_months=24,
            renewable_percentage=30
        ),
        Tariff(
            id="green_100",
            supplier="GreenPower",
            name="100% Renewable",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.30,
            standing_charge=0.48,
            contract_length_months=12,
            renewable_percentage=100
        ),
        Tariff(
            id="dynamic_agile",
            supplier="GridFlex",
            name="Dynamic Rate",
            tariff_type=TariffType.DYNAMIC,
            unit_rate=0.18,
            standing_charge=0.42,
            contract_length_months=12,
            renewable_percentage=40
        )
    ]


def example_usage():
    """Example of using the switching engine."""
    print("=" * 60)
    print("SUPPLIER SWITCHING DECISION ENGINE - DEMO")
    print("=" * 60)

    # Create current tariff and alternatives
    current = Tariff(
        id="current",
        supplier="OldSupplier",
        name="Standard Variable",
        tariff_type=TariffType.VARIABLE_RATE,
        unit_rate=0.32,
        standing_charge=0.50,
        exit_fee=0,
        renewable_percentage=0
    )

    alternatives = create_sample_tariffs()

    # Create consumption profile
    profile = ConsumptionProfile(
        annual_consumption_kwh=3500,
        peak_fraction=0.35,
        has_ev=False,
        flexible_load_fraction=0.25
    )

    # Initialize engine
    engine = SupplierSwitchingEngine(
        min_savings_threshold=0.05,
        prefer_renewable=False
    )

    # Get recommendation
    should_switch, rec = engine.should_switch(current, alternatives, profile)

    print(f"\nCurrent tariff: {current.supplier} - {current.name}")
    print(f"Annual consumption: {profile.annual_consumption_kwh} kWh")

    if should_switch and rec:
        print("\n" + rec.summary())
    else:
        print("\nNo beneficial switch found. Stay with current tariff.")


if __name__ == "__main__":
    example_usage()
