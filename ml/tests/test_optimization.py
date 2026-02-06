"""
Comprehensive Tests for MILP Appliance Scheduling Optimization

Test coverage includes:
- Appliance model validation
- Constraint satisfaction
- Objective function correctness
- Solver performance
- Savings calculation accuracy
- Edge cases and error handling

Key Validation:
- 15%+ savings on realistic scenarios
- All constraints satisfied
- Solve time under 5 seconds
"""

import pytest
import numpy as np
import time
from typing import List, Tuple

from ml.optimization.appliance_models import (
    Appliance,
    ApplianceType,
    ApplianceSchedule,
    ScheduleResult,
    PriceProfile,
    OptimizationConfig,
    PriorityLevel,
)
from ml.optimization.constraints import ConstraintBuilder, build_all_constraints
from ml.optimization.objective import (
    build_objective,
    calculate_baseline_cost,
    calculate_optimal_cost,
)
from ml.optimization.load_shifter import MILPOptimizer, quick_optimize
from ml.optimization.scheduler import (
    ApplianceScheduler,
    SchedulerPresets,
    create_quick_scheduler,
)
from ml.optimization.visualization import ScheduleVisualizer


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def basic_config():
    """Basic optimization configuration."""
    return OptimizationConfig(
        time_slots=96,
        slot_duration_hours=0.25,
        max_solve_time_seconds=5.0,
        mip_gap=0.01,
    )


@pytest.fixture
def dishwasher():
    """Standard dishwasher appliance."""
    return Appliance(
        name="Dishwasher",
        appliance_type=ApplianceType.DISHWASHER,
        earliest_start=18,
        latest_end=8,
    )


@pytest.fixture
def ev_charger():
    """Standard EV charger appliance."""
    return Appliance(
        name="EV Charger",
        appliance_type=ApplianceType.EV_CHARGER,
        earliest_start=21,
        latest_end=7,
        priority=PriorityLevel.HIGH,
    )


@pytest.fixture
def pool_pump():
    """Standard pool pump appliance."""
    return Appliance(
        name="Pool Pump",
        appliance_type=ApplianceType.POOL_PUMP,
        earliest_start=8,
        latest_end=20,
    )


@pytest.fixture
def flat_price_profile():
    """Flat rate price profile at $0.15/kWh."""
    return PriceProfile.create_flat_rate(0.15, num_slots=96)


@pytest.fixture
def tou_price_profile():
    """Time-of-use price profile with peak 4-9 PM."""
    return PriceProfile.create_time_of_use(
        off_peak_rate=0.10,
        on_peak_rate=0.35,
        on_peak_hours=[(16, 21)],  # 4 PM - 9 PM
        num_slots=96,
    )


@pytest.fixture
def realtime_price_profile():
    """Real-time price profile with high volatility."""
    return PriceProfile.create_realtime(
        base_rate=0.12,
        volatility=0.4,
        num_slots=96,
        seed=42,  # For reproducibility
    )


@pytest.fixture
def typical_household_appliances():
    """Set of typical household appliances."""
    return [
        Appliance(
            name="Dishwasher",
            appliance_type=ApplianceType.DISHWASHER,
            earliest_start=18,
            latest_end=8,
        ),
        Appliance(
            name="Washing Machine",
            appliance_type=ApplianceType.WASHING_MACHINE,
            earliest_start=6,
            latest_end=22,
        ),
        Appliance(
            name="EV Charger",
            appliance_type=ApplianceType.EV_CHARGER,
            earliest_start=21,
            latest_end=7,
        ),
        Appliance(
            name="Water Heater",
            appliance_type=ApplianceType.WATER_HEATER,
            earliest_start=0,
            latest_end=24,
        ),
    ]


# =============================================================================
# Appliance Model Tests
# =============================================================================


class TestApplianceModels:
    """Test suite for appliance data models."""

    def test_appliance_defaults(self):
        """Test that appliance defaults are applied correctly."""
        dishwasher = Appliance(
            name="Test Dishwasher",
            appliance_type=ApplianceType.DISHWASHER,
        )

        assert dishwasher.power_kw == 1.5
        assert dishwasher.duration_hours == 2.0
        assert dishwasher.must_be_continuous is True
        assert dishwasher.can_be_interrupted is False

    def test_appliance_custom_values(self):
        """Test that custom values override defaults."""
        custom = Appliance(
            name="Custom Appliance",
            appliance_type=ApplianceType.DISHWASHER,
            power_kw=2.5,
            duration_hours=1.5,
            min_run_chunk_hours=0.25,  # Ensure min_chunk <= duration
        )

        assert custom.power_kw == 2.5
        assert custom.duration_hours == 1.5

    def test_appliance_validation_errors(self):
        """Test that invalid configurations raise errors."""
        with pytest.raises(ValueError, match="Power must be positive"):
            Appliance(name="Bad", power_kw=-1)

        with pytest.raises(ValueError, match="Duration must be positive"):
            Appliance(name="Bad", duration_hours=0)

        with pytest.raises(ValueError, match="Earliest start must be"):
            Appliance(name="Bad", earliest_start=25)

    def test_appliance_duration_slots(self):
        """Test slot duration calculation."""
        app = Appliance(name="Test", duration_hours=2.0)
        assert app.duration_slots == 8  # 2 hours * 4 slots/hour

        app2 = Appliance(name="Test2", duration_hours=1.5)
        assert app2.duration_slots == 6  # 1.5 hours * 4 slots/hour

    def test_appliance_valid_slots_normal(self):
        """Test valid slots for normal time window."""
        app = Appliance(name="Test", earliest_start=9, latest_end=17)
        valid = app.get_valid_slots(96)

        # Should be slots from 9*4=36 to 17*4=68
        assert min(valid) == 36
        assert max(valid) == 67
        assert len(valid) == 32

    def test_appliance_valid_slots_overnight(self):
        """Test valid slots for overnight time window."""
        app = Appliance(name="Test", earliest_start=21, latest_end=7)
        valid = app.get_valid_slots(96)

        # Should include slots from 21*4=84 to 96 and 0 to 7*4=28
        assert 84 in valid
        assert 0 in valid
        assert 27 in valid
        assert 50 not in valid

    def test_appliance_energy_calculation(self):
        """Test energy consumption calculation."""
        app = Appliance(name="Test", power_kw=2.0, duration_hours=3.0)
        assert app.energy_kwh == 6.0

    def test_appliance_serialization(self):
        """Test appliance to/from dict conversion."""
        original = Appliance(
            name="Test",
            appliance_type=ApplianceType.EV_CHARGER,
            power_kw=7.0,
            earliest_start=21,
            priority=PriorityLevel.HIGH,
        )

        data = original.to_dict()
        restored = Appliance.from_dict(data)

        assert restored.name == original.name
        assert restored.power_kw == original.power_kw
        assert restored.priority == original.priority


class TestPriceProfile:
    """Test suite for price profile functionality."""

    def test_flat_rate_creation(self):
        """Test flat rate profile creation."""
        profile = PriceProfile.create_flat_rate(0.15, num_slots=96)

        assert profile.num_slots == 96
        assert all(p == 0.15 for p in profile.prices)
        assert profile.min_price == 0.15
        assert profile.max_price == 0.15

    def test_tou_creation(self):
        """Test time-of-use profile creation."""
        profile = PriceProfile.create_time_of_use(
            off_peak_rate=0.10,
            on_peak_rate=0.30,
            on_peak_hours=[(14, 20)],
            num_slots=96,
        )

        # Check off-peak slots (before 2 PM = slot 56)
        assert profile.prices[0] == 0.10
        assert profile.prices[55] == 0.10

        # Check on-peak slots (2 PM - 8 PM = slots 56-79)
        assert profile.prices[56] == 0.30
        assert profile.prices[79] == 0.30

        # Check after peak
        assert profile.prices[80] == 0.10

    def test_realtime_creation(self):
        """Test real-time profile creation."""
        profile = PriceProfile.create_realtime(
            base_rate=0.12,
            volatility=0.3,
            num_slots=96,
            seed=42,
        )

        assert profile.num_slots == 96
        assert profile.min_price > 0
        assert profile.max_price > profile.min_price
        assert profile.price_spread > 0

    def test_cost_calculation(self):
        """Test cost calculation for given slots."""
        profile = PriceProfile.create_flat_rate(0.10, num_slots=96)
        power_kw = 2.0

        # Running for 4 slots (1 hour) at 2 kW
        slots = [0, 1, 2, 3]
        cost = profile.calculate_cost(slots, power_kw)

        # Expected: 4 slots * 0.25 hours * 2 kW * $0.10/kWh = $0.20
        assert abs(cost - 0.20) < 0.001

    def test_cheapest_slots(self):
        """Test finding cheapest slots."""
        prices = np.array([0.1, 0.2, 0.05, 0.3, 0.15, 0.08])
        profile = PriceProfile(prices=prices)

        cheapest = profile.get_cheapest_slots(3)
        assert cheapest == [2, 5, 0]  # Indices of 0.05, 0.08, 0.1


class TestScheduleResult:
    """Test suite for schedule result functionality."""

    def test_schedule_run_periods(self, dishwasher):
        """Test run period extraction."""
        schedule = ApplianceSchedule(
            appliance=dishwasher,
            scheduled_slots=[10, 11, 12, 13, 20, 21, 22, 23],
            cost=1.50,
            energy_kwh=3.0,
        )

        periods = schedule.run_periods
        assert len(periods) == 2
        assert periods[0] == (10, 14)
        assert periods[1] == (20, 24)

    def test_schedule_time_formatting(self, dishwasher):
        """Test time formatting."""
        schedule = ApplianceSchedule(
            appliance=dishwasher,
            scheduled_slots=[36, 37, 38, 39],  # 9:00-10:00
            cost=0.50,
            energy_kwh=1.5,
        )

        assert schedule.start_time == "09:00"
        assert schedule.end_time == "10:00"


# =============================================================================
# Constraint Tests
# =============================================================================


class TestConstraints:
    """Test suite for constraint building and satisfaction."""

    def test_duration_constraint(self, basic_config, dishwasher, flat_price_profile):
        """Test that duration constraint is satisfied."""
        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([dishwasher], flat_price_profile)

        schedule = result.schedules[0]
        expected_slots = dishwasher.duration_slots

        assert len(schedule.scheduled_slots) == expected_slots

    def test_time_window_constraint(self, basic_config, flat_price_profile):
        """Test that time window constraint is satisfied."""
        # Create appliance with restricted window (9 AM - 5 PM)
        app = Appliance(
            name="Restricted",
            power_kw=1.0,
            duration_hours=2.0,
            earliest_start=9,
            latest_end=17,
        )

        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([app], flat_price_profile)

        schedule = result.schedules[0]
        valid_slots = set(app.get_valid_slots(96))

        # All scheduled slots must be in valid window
        for slot in schedule.scheduled_slots:
            assert slot in valid_slots, f"Slot {slot} outside valid window"

    def test_continuity_constraint(self, basic_config, flat_price_profile):
        """Test that continuous appliances run without interruption."""
        continuous_app = Appliance(
            name="Continuous",
            power_kw=2.0,
            duration_hours=2.0,
            must_be_continuous=True,
            can_be_interrupted=False,
            earliest_start=0,
            latest_end=24,
        )

        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([continuous_app], flat_price_profile)

        schedule = result.schedules[0]
        sorted_slots = sorted(schedule.scheduled_slots)

        # Check continuity
        for i in range(len(sorted_slots) - 1):
            diff = sorted_slots[i + 1] - sorted_slots[i]
            assert diff == 1, f"Gap found between slots {sorted_slots[i]} and {sorted_slots[i+1]}"

    def test_interruptible_appliance(self, basic_config):
        """Test that interruptible appliances can have gaps."""
        # Create price profile with expensive middle period
        prices = np.full(96, 0.10)
        prices[40:50] = 1.00  # Very expensive period

        profile = PriceProfile(prices=prices)

        interruptible = Appliance(
            name="Interruptible",
            power_kw=1.0,
            duration_hours=4.0,  # 16 slots
            must_be_continuous=False,
            can_be_interrupted=True,
            min_run_chunk_hours=0.25,  # 1 slot minimum
            earliest_start=8,
            latest_end=20,
        )

        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([interruptible], profile)

        schedule = result.schedules[0]

        # Should avoid expensive slots
        expensive_used = sum(1 for s in schedule.scheduled_slots if 40 <= s < 50)
        assert expensive_used == 0, "Should avoid expensive slots"

    def test_power_limit_constraint(self, basic_config, flat_price_profile):
        """Test maximum power consumption limit."""
        config = OptimizationConfig(
            time_slots=96,
            max_total_power_kw=5.0,
        )

        appliances = [
            Appliance(name="App1", power_kw=3.0, duration_hours=2.0),
            Appliance(name="App2", power_kw=4.0, duration_hours=2.0),
        ]

        optimizer = MILPOptimizer(config)
        result = optimizer.optimize(appliances, flat_price_profile)

        # Check power at each slot
        power_profile = result.get_power_profile(96)
        max_power = np.max(power_profile)

        assert max_power <= 5.0 + 0.01, f"Power limit exceeded: {max_power}"


# =============================================================================
# Optimizer Tests
# =============================================================================


class TestMILPOptimizer:
    """Test suite for MILP optimizer."""

    def test_basic_optimization(self, basic_config, dishwasher, tou_price_profile):
        """Test basic optimization produces valid result."""
        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([dishwasher], tou_price_profile)

        assert result.is_feasible
        assert result.total_cost > 0
        assert len(result.schedules) == 1

    def test_solve_time_under_limit(
        self, basic_config, typical_household_appliances, tou_price_profile
    ):
        """Test that solve time is under 5 seconds."""
        optimizer = MILPOptimizer(basic_config)

        start = time.time()
        result = optimizer.optimize(typical_household_appliances, tou_price_profile)
        elapsed = time.time() - start

        assert elapsed < 5.0, f"Solve time {elapsed:.2f}s exceeds 5s limit"
        assert result.solve_time_seconds < 5.0

    def test_savings_with_tou_pricing(
        self, basic_config, typical_household_appliances, tou_price_profile
    ):
        """Test that TOU pricing produces significant savings."""
        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize(typical_household_appliances, tou_price_profile)

        # With 3.5x peak/off-peak ratio, should see meaningful savings
        assert result.savings_percent > 10.0, (
            f"Expected >10% savings, got {result.savings_percent:.1f}%"
        )

    def test_no_savings_with_flat_rate(
        self, basic_config, dishwasher, flat_price_profile
    ):
        """Test that flat rate produces minimal savings."""
        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([dishwasher], flat_price_profile)

        # With flat rate, timing doesn't matter
        # May have small savings from preference penalties
        assert abs(result.savings_percent) < 1.0

    def test_infeasible_detection(self, basic_config):
        """Test that infeasible problems are detected."""
        # Create impossible constraint: 10 hour appliance in 2 hour window
        impossible = Appliance(
            name="Impossible",
            power_kw=1.0,
            duration_hours=10.0,
            earliest_start=10,
            latest_end=12,  # Only 2 hour window
            must_be_continuous=True,
            can_be_interrupted=False,  # Explicitly set to avoid conflict
        )

        prices = PriceProfile.create_flat_rate(0.15, num_slots=96)
        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([impossible], prices)

        assert not result.is_feasible

    def test_multiple_appliances(self, basic_config, tou_price_profile):
        """Test optimization with multiple appliances."""
        appliances = [
            Appliance(
                name="Dishwasher",
                appliance_type=ApplianceType.DISHWASHER,
                earliest_start=18,
                latest_end=8,
            ),
            Appliance(
                name="Washing Machine",
                appliance_type=ApplianceType.WASHING_MACHINE,
                earliest_start=8,
                latest_end=20,
            ),
            Appliance(
                name="Dryer",
                appliance_type=ApplianceType.DRYER,
                earliest_start=8,
                latest_end=20,
            ),
        ]

        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize(appliances, tou_price_profile)

        assert result.is_feasible
        assert len(result.schedules) == 3

        # Each appliance should have correct duration
        for schedule in result.schedules:
            expected = schedule.appliance.duration_slots
            actual = len(schedule.scheduled_slots)
            assert actual == expected, (
                f"{schedule.appliance.name}: expected {expected} slots, got {actual}"
            )


# =============================================================================
# Savings Validation Tests (Critical: 15%+ Savings)
# =============================================================================


class TestSavingsValidation:
    """Critical tests validating 15%+ savings on realistic scenarios."""

    def test_savings_15_percent_tou_scenario(self, basic_config):
        """CRITICAL: Validate 15%+ savings with TOU pricing."""
        # Typical California TOU: 3.5x peak ratio
        profile = PriceProfile.create_time_of_use(
            off_peak_rate=0.12,
            on_peak_rate=0.42,  # 3.5x multiplier
            on_peak_hours=[(16, 21)],  # 4 PM - 9 PM
            num_slots=96,
        )

        # Flexible appliances that can shift
        appliances = [
            Appliance(
                name="Dishwasher",
                appliance_type=ApplianceType.DISHWASHER,
                earliest_start=17,  # Can start during peak
                latest_end=8,        # Can run overnight
            ),
            Appliance(
                name="EV Charger",
                appliance_type=ApplianceType.EV_CHARGER,
                earliest_start=18,  # Comes home during peak
                latest_end=7,        # Must be done by morning
            ),
            Appliance(
                name="Water Heater",
                appliance_type=ApplianceType.WATER_HEATER,
                earliest_start=0,
                latest_end=24,
            ),
        ]

        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize(appliances, profile)

        assert result.is_optimal, f"Solution status: {result.status}"
        assert result.savings_percent >= 15.0, (
            f"CRITICAL: Expected >=15% savings, got {result.savings_percent:.1f}%\n"
            f"Baseline: ${result.baseline_cost:.2f}, "
            f"Optimized: ${result.total_cost:.2f}"
        )

        print(f"\nTOU Scenario Savings: {result.savings_percent:.1f}%")
        print(f"Baseline: ${result.baseline_cost:.2f}")
        print(f"Optimized: ${result.total_cost:.2f}")
        print(f"Savings: ${result.savings_amount:.2f}")

    def test_savings_15_percent_realtime_scenario(self, basic_config):
        """CRITICAL: Validate 15%+ savings with real-time pricing."""
        # High volatility real-time pricing
        profile = PriceProfile.create_realtime(
            base_rate=0.10,
            volatility=0.5,  # High volatility for more opportunities
            num_slots=96,
            seed=42,
        )

        appliances = [
            Appliance(
                name="Pool Pump",
                appliance_type=ApplianceType.POOL_PUMP,
                earliest_start=6,
                latest_end=22,
            ),
            Appliance(
                name="Water Heater",
                appliance_type=ApplianceType.WATER_HEATER,
                earliest_start=0,
                latest_end=24,
                duration_hours=3.0,
            ),
            Appliance(
                name="HVAC Precooling",
                power_kw=3.5,
                duration_hours=2.0,
                earliest_start=10,
                latest_end=18,
                must_be_continuous=False,
                can_be_interrupted=True,
            ),
        ]

        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize(appliances, profile)

        assert result.is_feasible
        assert result.savings_percent >= 15.0, (
            f"CRITICAL: Expected >=15% savings, got {result.savings_percent:.1f}%"
        )

        print(f"\nReal-time Scenario Savings: {result.savings_percent:.1f}%")

    def test_savings_extreme_price_spread(self, basic_config):
        """Test savings with extreme price variations."""
        # Create profile with very cheap night rates
        prices = np.full(96, 0.30)  # Default high price
        prices[0:24] = 0.05   # 12 AM - 6 AM very cheap
        prices[84:96] = 0.05  # 9 PM - 12 AM very cheap

        profile = PriceProfile(prices=prices)

        appliances = [
            Appliance(
                name="EV Charger",
                appliance_type=ApplianceType.EV_CHARGER,
                earliest_start=20,
                latest_end=8,
            ),
        ]

        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize(appliances, profile)

        # With 6x price ratio, should see significant savings
        # The actual savings depend on how much of the window overlaps with cheap slots
        assert result.savings_percent >= 40.0, (
            f"With 6x price ratio, expected >=40% savings, "
            f"got {result.savings_percent:.1f}%"
        )

    def test_multiple_households_average_savings(self, basic_config):
        """Test that average savings across different households exceeds 15%."""
        savings_list = []

        # Test multiple random price profiles
        for seed in range(5):
            profile = PriceProfile.create_realtime(
                base_rate=0.12,
                volatility=0.4,
                seed=seed,
            )

            appliances = [
                Appliance(
                    name="Dishwasher",
                    appliance_type=ApplianceType.DISHWASHER,
                    earliest_start=17,
                    latest_end=8,
                ),
                Appliance(
                    name="EV Charger",
                    appliance_type=ApplianceType.EV_CHARGER,
                    earliest_start=18,
                    latest_end=7,
                ),
            ]

            optimizer = MILPOptimizer(basic_config)
            result = optimizer.optimize(appliances, profile)

            if result.is_feasible:
                savings_list.append(result.savings_percent)

        avg_savings = np.mean(savings_list)
        assert avg_savings >= 15.0, (
            f"Average savings {avg_savings:.1f}% below 15% target"
        )

        print(f"\nAverage savings across scenarios: {avg_savings:.1f}%")
        print(f"Individual savings: {[f'{s:.1f}%' for s in savings_list]}")


# =============================================================================
# Scheduler API Tests
# =============================================================================


class TestSchedulerAPI:
    """Test suite for high-level scheduler API."""

    def test_appliance_preset(self):
        """Test adding appliances via presets."""
        scheduler = ApplianceScheduler()
        scheduler.add_appliance_preset("dishwasher", "evening")
        scheduler.add_appliance_preset("ev_charger", "overnight")

        assert len(scheduler.appliances) == 2
        assert scheduler.appliances[0].name == "Dishwasher"
        assert scheduler.appliances[1].must_be_continuous is False

    def test_time_windows(self):
        """Test different time window presets."""
        scheduler = ApplianceScheduler()

        windows = {
            "morning": (5, 12),
            "afternoon": (12, 18),
            "evening": (17, 23),
            "overnight": (21, 7),
        }

        for window_name, (expected_start, expected_end) in windows.items():
            start, end = scheduler._get_time_window(window_name)
            assert start == expected_start
            assert end == expected_end

    def test_price_profile_setters(self):
        """Test various price profile setters."""
        scheduler = ApplianceScheduler()

        # Flat rate
        scheduler.set_flat_rate(0.15)
        assert scheduler.price_profile is not None
        assert scheduler.price_profile.profile_type == "flat"

        # TOU
        scheduler.set_time_of_use_prices(0.10, 0.30, [(14, 20)])
        assert scheduler.price_profile.profile_type == "tou"

        # Real-time
        scheduler.set_realtime_prices(0.12, 0.3, seed=42)
        assert scheduler.price_profile.profile_type == "realtime"

    def test_full_scheduler_workflow(self):
        """Test complete scheduler workflow."""
        scheduler = ApplianceScheduler()

        # Add appliances
        scheduler.add_appliance_preset("dishwasher", "evening")
        scheduler.add_appliance_preset("washing_machine", "daytime")

        # Set pricing
        scheduler.set_time_of_use_prices(0.10, 0.30, [(16, 21)])

        # Optimize
        result = scheduler.optimize()

        assert result.is_feasible
        assert result.total_cost > 0

        # Get summary
        summary = scheduler.get_schedule_summary()
        assert "total_cost" in summary
        assert "schedules" in summary

    def test_scheduler_presets(self):
        """Test preset scheduler configurations."""
        household = SchedulerPresets.typical_household()
        assert len(household.appliances) == 4

        ev_house = SchedulerPresets.ev_household()
        assert len(ev_house.appliances) == 5

    def test_quick_scheduler(self):
        """Test quick scheduler creation."""
        scheduler = create_quick_scheduler(
            appliances=["dishwasher", "ev_charger"],
            rate_type="tou",
        )

        assert len(scheduler.appliances) == 2
        assert scheduler.price_profile is not None

        result = scheduler.optimize()
        assert result.is_feasible

    def test_dependency_handling(self):
        """Test appliance dependencies."""
        scheduler = ApplianceScheduler()

        scheduler.add_appliance_preset("washing_machine", "daytime", name="Washer")
        scheduler.add_appliance_preset("dryer", "daytime", name="Dryer")
        scheduler.add_dependency("Washer", "Dryer")

        scheduler.set_flat_rate(0.15)
        result = scheduler.optimize()

        # Both should be scheduled (dependencies are soft in current implementation)
        assert result.is_feasible
        assert len(result.schedules) == 2


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Test suite for edge cases and error handling."""

    def test_single_slot_appliance(self, basic_config, flat_price_profile):
        """Test appliance that only needs one slot."""
        app = Appliance(
            name="Quick",
            power_kw=1.0,
            duration_hours=0.25,  # 1 slot
        )

        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([app], flat_price_profile)

        assert result.is_feasible
        assert len(result.schedules[0].scheduled_slots) == 1

    def test_full_day_appliance(self, basic_config, flat_price_profile):
        """Test appliance that runs all day."""
        app = Appliance(
            name="Always On",
            power_kw=0.5,
            duration_hours=24.0,  # Full day
            can_be_interrupted=True,
        )

        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([app], flat_price_profile)

        assert result.is_feasible
        assert len(result.schedules[0].scheduled_slots) == 96

    def test_narrow_window(self, basic_config, flat_price_profile):
        """Test appliance with barely sufficient window."""
        app = Appliance(
            name="Tight",
            power_kw=1.0,
            duration_hours=2.0,  # 8 slots needed
            earliest_start=10,
            latest_end=12,       # 8 slots available
            must_be_continuous=True,
            can_be_interrupted=False,  # Explicitly set to avoid conflict
        )

        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([app], flat_price_profile)

        assert result.is_feasible

    def test_overlapping_peak_periods(self, basic_config):
        """Test TOU with multiple peak periods."""
        profile = PriceProfile.create_time_of_use(
            off_peak_rate=0.10,
            on_peak_rate=0.30,
            on_peak_hours=[(7, 10), (17, 21)],  # Morning and evening peaks
            num_slots=96,
        )

        app = Appliance(
            name="Flexible",
            power_kw=2.0,
            duration_hours=4.0,
            earliest_start=6,
            latest_end=22,
            can_be_interrupted=True,
        )

        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([app], profile)

        assert result.is_feasible

        # Should avoid both peak periods
        schedule = result.schedules[0]
        morning_peak_slots = set(range(28, 40))  # 7-10 AM
        evening_peak_slots = set(range(68, 84))  # 5-9 PM

        peak_usage = sum(
            1 for s in schedule.scheduled_slots
            if s in morning_peak_slots or s in evening_peak_slots
        )

        # Should minimize peak usage
        assert peak_usage < 8, f"Too much peak usage: {peak_usage} slots"

    def test_empty_appliance_list(self, basic_config, flat_price_profile):
        """Test error handling for empty appliance list."""
        optimizer = MILPOptimizer(basic_config)

        with pytest.raises(ValueError, match="At least one appliance"):
            optimizer.optimize([], flat_price_profile)

    def test_missing_price_profile(self, basic_config, dishwasher):
        """Test error handling for missing price profile."""
        optimizer = MILPOptimizer(basic_config)

        with pytest.raises(ValueError, match="Price profile must be provided"):
            optimizer.optimize([dishwasher], None)

    def test_price_slot_mismatch(self, basic_config, dishwasher):
        """Test error handling for mismatched slot counts."""
        wrong_profile = PriceProfile.create_flat_rate(0.15, num_slots=48)

        optimizer = MILPOptimizer(basic_config)

        with pytest.raises(ValueError, match="slots"):
            optimizer.optimize([dishwasher], wrong_profile)


# =============================================================================
# Visualization Tests
# =============================================================================


class TestVisualization:
    """Test suite for visualization functionality."""

    def test_text_schedule_generation(
        self, basic_config, dishwasher, flat_price_profile
    ):
        """Test text schedule generation."""
        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize([dishwasher], flat_price_profile)

        visualizer = ScheduleVisualizer()
        text = visualizer.generate_text_schedule(result)

        assert "OPTIMIZED APPLIANCE SCHEDULE" in text
        assert "Dishwasher" in text
        assert "$" in text

    def test_slot_to_time_conversion(self):
        """Test time slot conversion."""
        visualizer = ScheduleVisualizer()

        assert visualizer._format_time(0) == "00:00"
        assert visualizer._format_time(4) == "01:00"
        assert visualizer._format_time(48) == "12:00"
        assert visualizer._format_time(95) == "23:45"


# =============================================================================
# Performance Tests
# =============================================================================


class TestPerformance:
    """Test suite for performance requirements."""

    def test_many_appliances_solve_time(self, basic_config, tou_price_profile):
        """Test solve time with many appliances."""
        appliances = []
        for i in range(10):
            app = Appliance(
                name=f"Appliance_{i}",
                power_kw=1.0 + (i % 3),
                duration_hours=1.0 + (i % 4) * 0.5,
                earliest_start=6,
                latest_end=22,
                can_be_interrupted=True,
            )
            appliances.append(app)

        optimizer = MILPOptimizer(basic_config)

        start = time.time()
        result = optimizer.optimize(appliances, tou_price_profile)
        elapsed = time.time() - start

        assert elapsed < 5.0, f"Solve time {elapsed:.2f}s exceeds 5s limit"
        assert result.is_feasible

        print(f"\n10 appliances solve time: {elapsed:.2f}s")

    def test_problem_size_reporting(
        self, basic_config, typical_household_appliances, tou_price_profile
    ):
        """Test problem statistics reporting."""
        optimizer = MILPOptimizer(basic_config)
        result = optimizer.optimize(typical_household_appliances, tou_price_profile)

        stats = optimizer.get_problem_stats()

        assert "num_variables" in stats
        assert "num_constraints" in stats
        assert stats["num_variables"] > 0
        assert stats["num_constraints"] > 0

        print(f"\nProblem size: {stats['num_variables']} variables, "
              f"{stats['num_constraints']} constraints")


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_end_to_end_optimization(self):
        """Test complete end-to-end optimization workflow."""
        # Create scheduler
        scheduler = ApplianceScheduler()

        # Add appliances
        scheduler.add_appliance(Appliance(
            name="Dishwasher",
            appliance_type=ApplianceType.DISHWASHER,
            earliest_start=18,
            latest_end=8,
        ))
        scheduler.add_appliance(Appliance(
            name="EV Charger",
            appliance_type=ApplianceType.EV_CHARGER,
            earliest_start=20,
            latest_end=7,
            priority=PriorityLevel.HIGH,
        ))
        scheduler.add_appliance(Appliance(
            name="Water Heater",
            appliance_type=ApplianceType.WATER_HEATER,
            earliest_start=0,
            latest_end=24,
        ))

        # Set TOU pricing
        scheduler.set_time_of_use_prices(
            off_peak_rate=0.10,
            on_peak_rate=0.35,
            on_peak_hours=[(16, 21)],
        )

        # Optimize
        result = scheduler.optimize()

        # Validate
        assert result.is_optimal
        assert result.savings_percent > 0
        assert all(
            len(s.scheduled_slots) == s.appliance.duration_slots
            for s in result.schedules
        )

        # Generate output
        summary = scheduler.get_schedule_summary()
        assert summary["status"] == "Optimal"

        visualizer = ScheduleVisualizer()
        text = visualizer.generate_text_schedule(result)
        assert len(text) > 100

        print("\n" + result.summary())

    def test_quick_optimize_function(self):
        """Test quick optimization convenience function."""
        appliances = [
            Appliance(name="Test1", power_kw=1.0, duration_hours=2.0),
            Appliance(name="Test2", power_kw=2.0, duration_hours=1.0),
        ]

        # Create TOU-like prices
        prices = [0.10] * 64 + [0.30] * 20 + [0.10] * 12

        result = quick_optimize(appliances, prices)

        assert result.is_feasible
        assert len(result.schedules) == 2


# =============================================================================
# Run Tests
# =============================================================================


if __name__ == "__main__":
    # Run with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
