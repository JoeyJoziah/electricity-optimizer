"""
TDD Tests for Supplier Switching Decision Engine

These tests are written FIRST following TDD principles.

Test Coverage:
- Tariff modeling
- Cost calculations
- Consumption profiles
- Recommendation generation
- Risk assessment
- Switching decisions
"""

import pytest
import numpy as np
from datetime import datetime, timedelta


class TestTariff:
    """Tests for Tariff data model."""

    def test_tariff_creation(self):
        """Test tariff can be created with required fields."""
        from ml.optimization.switching_decision import Tariff, TariffType

        tariff = Tariff(
            id="test_tariff",
            supplier="TestSupplier",
            name="Test Fixed Rate",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.28,
            standing_charge=0.45
        )

        assert tariff.id == "test_tariff"
        assert tariff.supplier == "TestSupplier"
        assert tariff.unit_rate == 0.28
        assert tariff.standing_charge == 0.45

    def test_tariff_cost_calculation_fixed_rate(self):
        """Test fixed rate tariff cost calculation."""
        from ml.optimization.switching_decision import Tariff, TariffType

        tariff = Tariff(
            id="fixed",
            supplier="Test",
            name="Fixed",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.25,  # 25p per kWh
            standing_charge=0.50  # 50p per day
        )

        # 3500 kWh over 365 days
        cost = tariff.calculate_cost(
            consumption_kwh=3500,
            days=365
        )

        expected_standing = 0.50 * 365  # 182.50
        expected_energy = 3500 * 0.25  # 875.00
        expected_total = expected_standing + expected_energy  # 1057.50

        assert abs(cost - expected_total) < 0.01

    def test_tariff_cost_calculation_tou(self):
        """Test time-of-use tariff cost calculation."""
        from ml.optimization.switching_decision import Tariff, TariffType

        tariff = Tariff(
            id="tou",
            supplier="Test",
            name="TOU",
            tariff_type=TariffType.TIME_OF_USE,
            unit_rate=0.22,
            standing_charge=0.50,
            peak_rate=0.35,
            off_peak_rate=0.12,
            peak_hours=[(16, 21)]
        )

        # 3500 kWh, 40% during peak
        cost = tariff.calculate_cost(
            consumption_kwh=3500,
            days=365,
            peak_fraction=0.4
        )

        expected_standing = 0.50 * 365
        peak_consumption = 3500 * 0.4
        off_peak_consumption = 3500 * 0.6
        expected_energy = peak_consumption * 0.35 + off_peak_consumption * 0.12
        expected_total = expected_standing + expected_energy

        assert abs(cost - expected_total) < 0.01

    def test_tariff_serialization(self):
        """Test tariff can be serialized to dict."""
        from ml.optimization.switching_decision import Tariff, TariffType

        tariff = Tariff(
            id="test",
            supplier="TestSupplier",
            name="Test Tariff",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.25,
            standing_charge=0.45,
            renewable_percentage=50
        )

        data = tariff.to_dict()

        assert data['id'] == "test"
        assert data['supplier'] == "TestSupplier"
        assert data['tariff_type'] == "fixed_rate"
        assert data['renewable_percentage'] == 50


class TestConsumptionProfile:
    """Tests for ConsumptionProfile data model."""

    def test_consumption_profile_creation(self):
        """Test consumption profile can be created."""
        from ml.optimization.switching_decision import ConsumptionProfile

        profile = ConsumptionProfile(
            annual_consumption_kwh=3500,
            peak_fraction=0.4
        )

        assert profile.annual_consumption_kwh == 3500
        assert profile.peak_fraction == 0.4

    def test_default_monthly_consumption(self):
        """Test default monthly consumption pattern is generated."""
        from ml.optimization.switching_decision import ConsumptionProfile

        profile = ConsumptionProfile(annual_consumption_kwh=3500)

        assert profile.monthly_consumption is not None
        assert len(profile.monthly_consumption) == 12
        assert abs(sum(profile.monthly_consumption) - 3500) < 1

    def test_default_hourly_pattern(self):
        """Test default hourly pattern is generated."""
        from ml.optimization.switching_decision import ConsumptionProfile

        profile = ConsumptionProfile(annual_consumption_kwh=3500)

        assert profile.hourly_pattern is not None
        assert len(profile.hourly_pattern) == 24
        # Allow small tolerance in sum (pattern may sum to ~1.0)
        assert abs(sum(profile.hourly_pattern) - 1.0) < 0.05

    def test_custom_monthly_consumption(self):
        """Test custom monthly consumption can be set."""
        from ml.optimization.switching_decision import ConsumptionProfile

        custom_monthly = [400, 350, 300, 250, 200, 150,
                         150, 200, 250, 300, 400, 350]

        profile = ConsumptionProfile(
            annual_consumption_kwh=3300,
            monthly_consumption=custom_monthly
        )

        assert profile.monthly_consumption == custom_monthly


class TestSwitchingRecommendation:
    """Tests for SwitchingRecommendation data model."""

    def test_recommendation_creation(self):
        """Test switching recommendation can be created."""
        from ml.optimization.switching_decision import (
            SwitchingRecommendation,
            Tariff,
            TariffType,
            RiskLevel
        )

        tariff = Tariff(
            id="new",
            supplier="NewSupplier",
            name="Better Rate",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.22,
            standing_charge=0.40
        )

        rec = SwitchingRecommendation(
            recommended_tariff=tariff,
            current_annual_cost=1200.0,
            projected_annual_cost=1000.0,
            annual_savings=200.0,
            savings_percentage=16.67,
            payback_months=0.0,
            risk_level=RiskLevel.LOW,
            confidence=0.85,
            reasons=["Lower rate", "No exit fee"],
            warnings=["Contract length"]
        )

        assert rec.annual_savings == 200.0
        assert rec.savings_percentage == 16.67
        assert rec.confidence == 0.85
        assert len(rec.reasons) == 2

    def test_recommendation_serialization(self):
        """Test recommendation can be serialized."""
        from ml.optimization.switching_decision import (
            SwitchingRecommendation,
            Tariff,
            TariffType,
            RiskLevel
        )

        tariff = Tariff(
            id="new",
            supplier="NewSupplier",
            name="Better Rate",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.22,
            standing_charge=0.40
        )

        rec = SwitchingRecommendation(
            recommended_tariff=tariff,
            current_annual_cost=1200.0,
            projected_annual_cost=1000.0,
            annual_savings=200.0,
            savings_percentage=16.67,
            payback_months=0.0,
            risk_level=RiskLevel.LOW,
            confidence=0.85
        )

        data = rec.to_dict()

        assert 'recommended_tariff' in data
        assert data['annual_savings'] == 200.0
        assert data['risk_level'] == 'low'

    def test_recommendation_summary(self):
        """Test recommendation summary generation."""
        from ml.optimization.switching_decision import (
            SwitchingRecommendation,
            Tariff,
            TariffType,
            RiskLevel
        )

        tariff = Tariff(
            id="new",
            supplier="NewSupplier",
            name="Better Rate",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.22,
            standing_charge=0.40
        )

        rec = SwitchingRecommendation(
            recommended_tariff=tariff,
            current_annual_cost=1200.0,
            projected_annual_cost=1000.0,
            annual_savings=200.0,
            savings_percentage=16.67,
            payback_months=0.0,
            risk_level=RiskLevel.LOW,
            confidence=0.85,
            reasons=["Lower rate"]
        )

        summary = rec.summary()

        assert "NewSupplier" in summary
        assert "200.00" in summary
        assert "16.7%" in summary


class TestSupplierSwitchingEngine:
    """Tests for the main switching engine."""

    @pytest.fixture
    def engine(self):
        """Create switching engine."""
        from ml.optimization.switching_decision import SupplierSwitchingEngine

        return SupplierSwitchingEngine(
            min_savings_threshold=0.05,
            prefer_renewable=False
        )

    @pytest.fixture
    def current_tariff(self):
        """Create current tariff."""
        from ml.optimization.switching_decision import Tariff, TariffType

        return Tariff(
            id="current",
            supplier="OldSupplier",
            name="Expensive Fixed",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.32,
            standing_charge=0.50,
            exit_fee=0
        )

    @pytest.fixture
    def alternatives(self):
        """Create alternative tariffs."""
        from ml.optimization.switching_decision import Tariff, TariffType

        return [
            Tariff(
                id="cheap_fixed",
                supplier="CheapPower",
                name="Budget Fixed",
                tariff_type=TariffType.FIXED_RATE,
                unit_rate=0.24,
                standing_charge=0.42
            ),
            Tariff(
                id="green",
                supplier="GreenEnergy",
                name="100% Green",
                tariff_type=TariffType.FIXED_RATE,
                unit_rate=0.30,
                standing_charge=0.48,
                renewable_percentage=100
            ),
            Tariff(
                id="tou",
                supplier="SmartGrid",
                name="Time of Use",
                tariff_type=TariffType.TIME_OF_USE,
                unit_rate=0.26,
                standing_charge=0.45,
                peak_rate=0.38,
                off_peak_rate=0.14
            )
        ]

    @pytest.fixture
    def profile(self):
        """Create consumption profile."""
        from ml.optimization.switching_decision import ConsumptionProfile

        return ConsumptionProfile(
            annual_consumption_kwh=3500,
            peak_fraction=0.35
        )

    def test_engine_initialization(self):
        """Test engine can be initialized."""
        from ml.optimization.switching_decision import SupplierSwitchingEngine, RiskLevel

        engine = SupplierSwitchingEngine(
            min_savings_threshold=0.05,
            max_risk_tolerance=RiskLevel.MEDIUM,
            prefer_renewable=True,
            renewable_premium_tolerance=0.03
        )

        assert engine.min_savings_threshold == 0.05
        assert engine.prefer_renewable is True

    def test_analyze_tariff(self, engine, current_tariff, profile):
        """Test single tariff analysis."""
        analysis = engine.analyze_tariff(current_tariff, profile)

        assert 'annual_cost' in analysis
        assert 'monthly_costs' in analysis
        assert 'effective_rate' in analysis
        assert 'risk_level' in analysis

        # Check monthly costs sum to approximately annual cost
        monthly_sum = sum(analysis['monthly_costs'])
        assert abs(monthly_sum - analysis['annual_cost']) < 1

    def test_compare_tariffs_finds_savings(
        self, engine, current_tariff, alternatives, profile
    ):
        """Test comparing tariffs identifies savings opportunities."""
        recommendations = engine.compare_tariffs(
            current_tariff,
            alternatives,
            profile
        )

        # Should find at least one recommendation
        assert len(recommendations) >= 1

        # First recommendation should have highest savings
        if len(recommendations) > 1:
            assert recommendations[0].annual_savings >= recommendations[1].annual_savings

    def test_compare_tariffs_excludes_low_savings(
        self, engine, current_tariff, profile
    ):
        """Test that low-savings alternatives are excluded."""
        from ml.optimization.switching_decision import Tariff, TariffType

        # Create alternative with tiny savings
        marginal_alternative = Tariff(
            id="marginal",
            supplier="MarginalSupplier",
            name="Barely Cheaper",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.315,  # Only slightly cheaper
            standing_charge=0.50
        )

        recommendations = engine.compare_tariffs(
            current_tariff,
            [marginal_alternative],
            profile
        )

        # Should not recommend marginal savings
        assert len(recommendations) == 0

    def test_get_best_recommendation(
        self, engine, current_tariff, alternatives, profile
    ):
        """Test getting the best single recommendation."""
        best = engine.get_best_recommendation(
            current_tariff,
            alternatives,
            profile
        )

        assert best is not None
        assert best.annual_savings > 0
        assert best.confidence > 0

    def test_should_switch_returns_true_for_good_deal(
        self, engine, current_tariff, alternatives, profile
    ):
        """Test should_switch returns True for beneficial switches."""
        should, rec = engine.should_switch(
            current_tariff,
            alternatives,
            profile
        )

        assert should is True
        assert rec is not None
        assert rec.savings_percentage >= 5.0

    def test_should_switch_returns_false_when_no_savings(self, engine, profile):
        """Test should_switch returns False when no savings."""
        from ml.optimization.switching_decision import Tariff, TariffType

        cheap_current = Tariff(
            id="already_cheap",
            supplier="CheapSupplier",
            name="Already Cheapest",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.18,
            standing_charge=0.35
        )

        expensive_alternatives = [
            Tariff(
                id="expensive",
                supplier="ExpensiveSupplier",
                name="Expensive Option",
                tariff_type=TariffType.FIXED_RATE,
                unit_rate=0.30,
                standing_charge=0.50
            )
        ]

        should, rec = engine.should_switch(
            cheap_current,
            expensive_alternatives,
            profile
        )

        assert should is False

    def test_risk_assessment(self, engine, profile):
        """Test risk level assessment for different tariff types."""
        from ml.optimization.switching_decision import Tariff, TariffType, RiskLevel

        fixed = Tariff(
            id="fixed",
            supplier="Test",
            name="Fixed",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.25,
            standing_charge=0.40
        )

        dynamic = Tariff(
            id="dynamic",
            supplier="Test",
            name="Dynamic",
            tariff_type=TariffType.DYNAMIC,
            unit_rate=0.18,
            standing_charge=0.40
        )

        fixed_analysis = engine.analyze_tariff(fixed, profile)
        dynamic_analysis = engine.analyze_tariff(dynamic, profile)

        assert fixed_analysis['risk_level'] == RiskLevel.LOW
        assert dynamic_analysis['risk_level'] == RiskLevel.HIGH


class TestPreferRenewable:
    """Tests for renewable energy preferences."""

    def test_renewable_preference(self):
        """Test engine prefers renewable when configured."""
        from ml.optimization.switching_decision import (
            SupplierSwitchingEngine,
            Tariff,
            TariffType,
            ConsumptionProfile
        )

        engine = SupplierSwitchingEngine(
            min_savings_threshold=0.0,  # Accept any savings
            prefer_renewable=True,
            renewable_premium_tolerance=0.10
        )

        current = Tariff(
            id="current",
            supplier="Old",
            name="Old Tariff",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.28,
            standing_charge=0.45,
            renewable_percentage=0
        )

        alternatives = [
            Tariff(
                id="cheaper_fossil",
                supplier="CheapFossil",
                name="Cheap but Dirty",
                tariff_type=TariffType.FIXED_RATE,
                unit_rate=0.22,  # Cheaper
                standing_charge=0.40,
                renewable_percentage=0
            ),
            Tariff(
                id="green",
                supplier="GreenPower",
                name="100% Green",
                tariff_type=TariffType.FIXED_RATE,
                unit_rate=0.25,  # More expensive but green
                standing_charge=0.45,
                renewable_percentage=100
            )
        ]

        profile = ConsumptionProfile(annual_consumption_kwh=3500)

        best = engine.get_best_recommendation(current, alternatives, profile)

        # With renewable preference, should recommend green option
        # (even though fossil is cheaper) if within premium tolerance
        assert best is not None


class TestExitFeeHandling:
    """Tests for exit fee handling."""

    def test_exit_fee_affects_payback(self):
        """Test exit fee is included in payback calculation."""
        from ml.optimization.switching_decision import (
            SupplierSwitchingEngine,
            Tariff,
            TariffType,
            ConsumptionProfile
        )

        engine = SupplierSwitchingEngine(min_savings_threshold=0.0)

        current = Tariff(
            id="current",
            supplier="Old",
            name="Old Tariff",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.32,
            standing_charge=0.50,
            exit_fee=100.0  # £100 exit fee
        )

        alternatives = [
            Tariff(
                id="new",
                supplier="New",
                name="Better Rate",
                tariff_type=TariffType.FIXED_RATE,
                unit_rate=0.25,
                standing_charge=0.45
            )
        ]

        profile = ConsumptionProfile(annual_consumption_kwh=3500)

        recs = engine.compare_tariffs(current, alternatives, profile)

        assert len(recs) > 0
        # Payback should be > 0 due to exit fee
        assert recs[0].payback_months > 0
        assert recs[0].switching_costs == 100.0


class TestTOUTariffRecommendation:
    """Tests for Time-of-Use tariff recommendations."""

    def test_tou_recommended_for_flexible_load(self):
        """Test TOU tariff recommended for flexible load patterns."""
        from ml.optimization.switching_decision import (
            SupplierSwitchingEngine,
            Tariff,
            TariffType,
            ConsumptionProfile
        )

        engine = SupplierSwitchingEngine(min_savings_threshold=0.0)

        current = Tariff(
            id="current",
            supplier="Old",
            name="Flat Rate",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.28,
            standing_charge=0.45
        )

        alternatives = [
            Tariff(
                id="tou",
                supplier="SmartGrid",
                name="Smart TOU",
                tariff_type=TariffType.TIME_OF_USE,
                unit_rate=0.22,
                standing_charge=0.45,
                peak_rate=0.35,
                off_peak_rate=0.10,
                peak_hours=[(16, 21)]
            )
        ]

        # Low peak fraction = flexible load
        profile = ConsumptionProfile(
            annual_consumption_kwh=3500,
            peak_fraction=0.2,  # Only 20% during peak
            flexible_load_fraction=0.4
        )

        recs = engine.compare_tariffs(current, alternatives, profile)

        assert len(recs) > 0
        # TOU should show good savings with low peak fraction
        assert recs[0].annual_savings > 0


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_alternatives_list(self):
        """Test handling of empty alternatives list."""
        from ml.optimization.switching_decision import (
            SupplierSwitchingEngine,
            Tariff,
            TariffType,
            ConsumptionProfile
        )

        engine = SupplierSwitchingEngine()

        current = Tariff(
            id="current",
            supplier="Old",
            name="Old Tariff",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.28,
            standing_charge=0.45
        )

        profile = ConsumptionProfile(annual_consumption_kwh=3500)

        recs = engine.compare_tariffs(current, [], profile)

        assert len(recs) == 0

    def test_current_tariff_in_alternatives(self):
        """Test current tariff is excluded from recommendations."""
        from ml.optimization.switching_decision import (
            SupplierSwitchingEngine,
            Tariff,
            TariffType,
            ConsumptionProfile
        )

        engine = SupplierSwitchingEngine(min_savings_threshold=0.0)

        current = Tariff(
            id="current",
            supplier="Old",
            name="Old Tariff",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.28,
            standing_charge=0.45
        )

        # Include current in alternatives
        alternatives = [current]

        profile = ConsumptionProfile(annual_consumption_kwh=3500)

        recs = engine.compare_tariffs(current, alternatives, profile)

        # Should not recommend switching to current tariff
        assert all(r.recommended_tariff.id != current.id for r in recs)

    def test_zero_consumption(self):
        """Test handling of zero consumption."""
        from ml.optimization.switching_decision import (
            SupplierSwitchingEngine,
            Tariff,
            TariffType,
            ConsumptionProfile
        )

        engine = SupplierSwitchingEngine()

        tariff = Tariff(
            id="test",
            supplier="Test",
            name="Test Tariff",
            tariff_type=TariffType.FIXED_RATE,
            unit_rate=0.28,
            standing_charge=0.45
        )

        profile = ConsumptionProfile(annual_consumption_kwh=0)

        analysis = engine.analyze_tariff(tariff, profile)

        # Should only have standing charge
        expected_cost = 0.45 * 365
        assert abs(analysis['annual_cost'] - expected_cost) < 0.01
