#!/usr/bin/env python3
"""
Standalone test script for MILP Appliance Scheduling Optimization.

This script tests the optimization module without requiring other ml dependencies
like TensorFlow. It validates:
1. Core functionality works
2. Constraints are satisfied
3. 15%+ savings achieved on realistic scenarios
4. Solve time under 5 seconds
"""

import os
import sys
import time
import importlib.util

# Direct module loading to bypass ml/__init__.py (which has TensorFlow dependency)
def load_module_direct(module_name, file_path):
    """Load a module directly from file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Load optimization modules directly (relative to this file's location)
BASE = os.path.join(os.path.dirname(__file__), '..', 'optimization')
BASE = os.path.abspath(BASE)

appliance_models = load_module_direct(
    'ml.optimization.appliance_models',
    f'{BASE}/appliance_models.py'
)

constraints = load_module_direct(
    'ml.optimization.constraints',
    f'{BASE}/constraints.py'
)

objective = load_module_direct(
    'ml.optimization.objective',
    f'{BASE}/objective.py'
)

load_shifter = load_module_direct(
    'ml.optimization.load_shifter',
    f'{BASE}/load_shifter.py'
)

scheduler = load_module_direct(
    'ml.optimization.scheduler',
    f'{BASE}/scheduler.py'
)

visualization = load_module_direct(
    'ml.optimization.visualization',
    f'{BASE}/visualization.py'
)

import numpy as np

# Import classes from loaded modules
Appliance = appliance_models.Appliance
ApplianceType = appliance_models.ApplianceType
ApplianceSchedule = appliance_models.ApplianceSchedule
ScheduleResult = appliance_models.ScheduleResult
PriceProfile = appliance_models.PriceProfile
OptimizationConfig = appliance_models.OptimizationConfig
PriorityLevel = appliance_models.PriorityLevel

MILPOptimizer = load_shifter.MILPOptimizer
quick_optimize = load_shifter.quick_optimize

ApplianceScheduler = scheduler.ApplianceScheduler
SchedulerPresets = scheduler.SchedulerPresets

ScheduleVisualizer = visualization.ScheduleVisualizer


def test_basic_optimization():
    """Test basic MILP optimization works."""
    print("\n" + "=" * 70)
    print("TEST: Basic Optimization")
    print("=" * 70)

    config = OptimizationConfig()
    optimizer = MILPOptimizer(config)

    # Create a simple dishwasher
    app = Appliance(
        name="Test Dishwasher",
        appliance_type=ApplianceType.DISHWASHER,
        earliest_start=18,
        latest_end=8,
    )

    # Create TOU pricing (peak 4-9 PM)
    prices = np.full(96, 0.10)  # Off-peak $0.10/kWh
    prices[64:84] = 0.35  # Peak $0.35/kWh (slots 64-83 = 4-9 PM)

    profile = PriceProfile(prices=prices, profile_type="tou")

    result = optimizer.optimize([app], profile)

    print(f"Status: {result.status}")
    print(f"Baseline cost: ${result.baseline_cost:.2f}")
    print(f"Optimized cost: ${result.total_cost:.2f}")
    print(f"Savings: ${result.savings_amount:.2f} ({result.savings_percent:.1f}%)")
    print(f"Solve time: {result.solve_time_seconds:.3f}s")

    # Validate
    assert result.is_optimal, f"Expected optimal, got {result.status}"
    assert result.total_cost < result.baseline_cost, "Should save money"
    assert result.solve_time_seconds < 5.0, "Should solve under 5 seconds"

    print("[PASSED] Basic optimization test")
    return result


def test_continuity_constraint():
    """Test continuous operation constraint."""
    print("\n" + "=" * 70)
    print("TEST: Continuity Constraint")
    print("=" * 70)

    config = OptimizationConfig()
    optimizer = MILPOptimizer(config)

    # Continuous appliance
    app = Appliance(
        name="Washing Machine",
        appliance_type=ApplianceType.WASHING_MACHINE,
        earliest_start=8,
        latest_end=20,
        must_be_continuous=True,
    )

    profile = PriceProfile.create_flat_rate(0.15, num_slots=96)
    result = optimizer.optimize([app], profile)

    # Check continuity
    schedule = result.schedules[0]
    sorted_slots = sorted(schedule.scheduled_slots)

    is_continuous = True
    for i in range(len(sorted_slots) - 1):
        if sorted_slots[i + 1] - sorted_slots[i] != 1:
            is_continuous = False
            break

    print(f"Scheduled slots: {sorted_slots[:10]}... ({len(sorted_slots)} total)")
    print(f"Is continuous: {is_continuous}")

    assert is_continuous, "Continuous appliance should not have gaps"
    assert len(sorted_slots) == app.duration_slots, "Should run for full duration"

    print("[PASSED] Continuity constraint test")
    return result


def test_time_window_constraint():
    """Test time window constraint."""
    print("\n" + "=" * 70)
    print("TEST: Time Window Constraint")
    print("=" * 70)

    config = OptimizationConfig()
    optimizer = MILPOptimizer(config)

    # Restricted window (9 AM - 5 PM)
    app = Appliance(
        name="Restricted Appliance",
        power_kw=1.0,
        duration_hours=2.0,
        earliest_start=9,
        latest_end=17,
    )

    profile = PriceProfile.create_flat_rate(0.15, num_slots=96)
    result = optimizer.optimize([app], profile)

    # Check all slots are within window
    schedule = result.schedules[0]
    valid_slots = set(app.get_valid_slots(96))

    all_valid = all(slot in valid_slots for slot in schedule.scheduled_slots)

    print(f"Valid slots range: {min(valid_slots)} to {max(valid_slots)}")
    print(f"Scheduled slots: {sorted(schedule.scheduled_slots)}")
    print(f"All slots valid: {all_valid}")

    assert all_valid, "All scheduled slots should be within time window"

    print("[PASSED] Time window constraint test")
    return result


def test_15_percent_savings_tou():
    """CRITICAL: Test 15%+ savings with TOU pricing."""
    print("\n" + "=" * 70)
    print("TEST: 15%+ Savings with TOU Pricing (CRITICAL)")
    print("=" * 70)

    config = OptimizationConfig()
    optimizer = MILPOptimizer(config)

    # Typical household with flexible appliances
    appliances = [
        Appliance(
            name="Dishwasher",
            appliance_type=ApplianceType.DISHWASHER,
            earliest_start=17,  # Available during peak
            latest_end=8,        # Can run overnight
        ),
        Appliance(
            name="EV Charger",
            appliance_type=ApplianceType.EV_CHARGER,
            earliest_start=18,  # Arrives during peak
            latest_end=7,        # Must be ready by morning
        ),
        Appliance(
            name="Water Heater",
            appliance_type=ApplianceType.WATER_HEATER,
            earliest_start=0,
            latest_end=24,
            duration_hours=3.0,
        ),
    ]

    # TOU pricing: 3.5x peak ratio (typical California)
    profile = PriceProfile.create_time_of_use(
        off_peak_rate=0.12,
        on_peak_rate=0.42,
        on_peak_hours=[(16, 21)],  # 4 PM - 9 PM
        num_slots=96,
    )

    start = time.time()
    result = optimizer.optimize(appliances, profile)
    elapsed = time.time() - start

    print(f"Status: {result.status}")
    print(f"Solve time: {elapsed:.3f}s")
    print(f"\nCost Analysis:")
    print(f"  Baseline cost: ${result.baseline_cost:.2f}")
    print(f"  Optimized cost: ${result.total_cost:.2f}")
    print(f"  Savings: ${result.savings_amount:.2f} ({result.savings_percent:.1f}%)")

    print(f"\nSchedule Summary:")
    for schedule in result.schedules:
        periods = [
            f"{schedule._slot_to_time(s)}-{schedule._slot_to_time(e)}"
            for s, e in schedule.run_periods
        ]
        print(f"  {schedule.appliance.name}: {', '.join(periods)}")
        print(f"    Cost: ${schedule.cost:.2f}, Energy: {schedule.energy_kwh:.2f} kWh")

    # CRITICAL ASSERTIONS
    assert result.is_optimal, f"Expected optimal, got {result.status}"
    assert elapsed < 5.0, f"Solve time {elapsed:.2f}s exceeds 5s limit"
    assert result.savings_percent >= 15.0, (
        f"CRITICAL FAILURE: Expected >=15% savings, got {result.savings_percent:.1f}%"
    )

    print(f"\n[PASSED] TOU savings test: {result.savings_percent:.1f}% >= 15%")
    return result


def test_15_percent_savings_realtime():
    """CRITICAL: Test 15%+ savings with real-time pricing."""
    print("\n" + "=" * 70)
    print("TEST: 15%+ Savings with Real-Time Pricing (CRITICAL)")
    print("=" * 70)

    config = OptimizationConfig()
    optimizer = MILPOptimizer(config)

    # Flexible appliances
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
            name="Flexible Load",
            power_kw=2.0,
            duration_hours=2.0,
            earliest_start=8,
            latest_end=20,
            can_be_interrupted=True,
        ),
    ]

    # Real-time pricing with volatility
    profile = PriceProfile.create_realtime(
        base_rate=0.10,
        volatility=0.5,
        seed=42,
    )

    print(f"Price range: ${profile.min_price:.3f} - ${profile.max_price:.3f}/kWh")
    print(f"Price spread: ${profile.price_spread:.3f}/kWh")

    result = optimizer.optimize(appliances, profile)

    print(f"\nStatus: {result.status}")
    print(f"Baseline cost: ${result.baseline_cost:.2f}")
    print(f"Optimized cost: ${result.total_cost:.2f}")
    print(f"Savings: ${result.savings_amount:.2f} ({result.savings_percent:.1f}%)")

    assert result.is_optimal
    assert result.savings_percent >= 15.0, (
        f"CRITICAL FAILURE: Expected >=15% savings, got {result.savings_percent:.1f}%"
    )

    print(f"\n[PASSED] Real-time savings test: {result.savings_percent:.1f}% >= 15%")
    return result


def test_scheduler_api():
    """Test high-level scheduler API."""
    print("\n" + "=" * 70)
    print("TEST: High-Level Scheduler API")
    print("=" * 70)

    scheduler = ApplianceScheduler()

    # Add appliances using presets
    scheduler.add_appliance_preset("dishwasher", "evening")
    scheduler.add_appliance_preset("ev_charger", "overnight")
    scheduler.add_appliance_preset("water_heater", "anytime")

    print(f"Appliances added: {[a.name for a in scheduler.appliances]}")

    # Set TOU pricing
    scheduler.set_time_of_use_prices(
        off_peak_rate=0.10,
        on_peak_rate=0.35,
        on_peak_hours=[(16, 21)],
    )

    # Optimize
    result = scheduler.optimize()

    print(f"\nStatus: {result.status}")
    print(f"Total cost: ${result.total_cost:.2f}")
    print(f"Savings: {result.savings_percent:.1f}%")

    # Get summary
    summary = scheduler.get_schedule_summary()
    print(f"\nSchedule summary has {len(summary['schedules'])} appliances")

    assert result.is_feasible
    assert len(result.schedules) == 3

    print("[PASSED] Scheduler API test")
    return result


def test_power_limit_constraint():
    """Test maximum power constraint."""
    print("\n" + "=" * 70)
    print("TEST: Power Limit Constraint")
    print("=" * 70)

    config = OptimizationConfig(
        time_slots=96,
        max_total_power_kw=5.0,  # Limit to 5 kW
    )
    optimizer = MILPOptimizer(config)

    # Two high-power appliances
    appliances = [
        Appliance(name="App1", power_kw=3.0, duration_hours=2.0),
        Appliance(name="App2", power_kw=4.0, duration_hours=2.0),
    ]

    profile = PriceProfile.create_flat_rate(0.15, num_slots=96)
    result = optimizer.optimize(appliances, profile)

    # Check power limit
    power_profile = result.get_power_profile(96)
    max_power = np.max(power_profile)

    print(f"Max power allowed: 5.0 kW")
    print(f"Max power used: {max_power:.2f} kW")

    assert max_power <= 5.01, f"Power limit exceeded: {max_power:.2f} kW"

    print("[PASSED] Power limit constraint test")
    return result


def test_multiple_scenarios():
    """Test savings across multiple price scenarios."""
    print("\n" + "=" * 70)
    print("TEST: Multiple Scenarios Average Savings")
    print("=" * 70)

    config = OptimizationConfig()
    savings_list = []

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

    for seed in range(5):
        profile = PriceProfile.create_realtime(
            base_rate=0.12,
            volatility=0.4,
            seed=seed,
        )

        optimizer = MILPOptimizer(config)
        result = optimizer.optimize(appliances, profile)

        if result.is_feasible:
            savings_list.append(result.savings_percent)
            print(f"  Scenario {seed}: {result.savings_percent:.1f}% savings")

    avg_savings = np.mean(savings_list)
    print(f"\nAverage savings: {avg_savings:.1f}%")

    assert avg_savings >= 15.0, (
        f"Average savings {avg_savings:.1f}% below 15% target"
    )

    print(f"[PASSED] Average savings {avg_savings:.1f}% >= 15%")
    return savings_list


def test_visualization():
    """Test visualization output."""
    print("\n" + "=" * 70)
    print("TEST: Visualization")
    print("=" * 70)

    scheduler = ApplianceScheduler()
    scheduler.add_appliance_preset("dishwasher", "evening")
    scheduler.add_appliance_preset("ev_charger", "overnight")
    scheduler.set_time_of_use_prices(0.10, 0.35, [(16, 21)])

    result = scheduler.optimize()

    visualizer = ScheduleVisualizer()
    text_output = visualizer.generate_text_schedule(result)

    # Print first 40 lines
    lines = text_output.split('\n')
    print('\n'.join(lines[:40]))
    print(f"... ({len(lines)} lines total)")

    assert "OPTIMIZED APPLIANCE SCHEDULE" in text_output
    assert "Dishwasher" in text_output
    assert "$" in text_output

    print("\n[PASSED] Visualization test")
    return text_output


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 70)
    print("MILP APPLIANCE SCHEDULING OPTIMIZATION - TEST SUITE")
    print("=" * 70)

    tests = [
        ("Basic Optimization", test_basic_optimization),
        ("Continuity Constraint", test_continuity_constraint),
        ("Time Window Constraint", test_time_window_constraint),
        ("15%+ Savings TOU", test_15_percent_savings_tou),
        ("15%+ Savings Real-Time", test_15_percent_savings_realtime),
        ("Scheduler API", test_scheduler_api),
        ("Power Limit Constraint", test_power_limit_constraint),
        ("Multiple Scenarios", test_multiple_scenarios),
        ("Visualization", test_visualization),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"[FAILED] {name}: {e}")
        except Exception as e:
            failed += 1
            errors.append((name, f"Error: {e}"))
            print(f"[ERROR] {name}: {e}")

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")

    if errors:
        print("\nFailures:")
        for name, msg in errors:
            print(f"  - {name}: {msg}")

    print("\n" + "=" * 70)

    return passed == len(tests)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
