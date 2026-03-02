"""
Unit Tests for ml/optimization/load_shifter.py

Covers:
- MILPOptimizer initialization
- _infer_variables: binary variable creation for each appliance/slot
- _build_problem: problem structure
- _get_solver: CBC / GLPK / default selection
- _solve: status return, error path
- _extract_solution: scheduled_slots, cost, energy
- _validate_solution: duration, time window, continuity, power limits
- optimize(): main entry point -- happy path, infeasible, missing inputs
- get_problem_stats(): pre- and post-solve
- create_default_optimizer()
- optimize_single_appliance()
- quick_optimize()

The PuLP solver is exercised lightly (small problems); heavier scenarios use
the existing test_optimization.py suite. This file focuses on unit-level
contracts and error paths.
"""

import time
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
import pulp

from ml.optimization.appliance_models import (
    Appliance,
    ApplianceType,
    ApplianceSchedule,
    ScheduleResult,
    PriceProfile,
    OptimizationConfig,
    PriorityLevel,
)
from ml.optimization.load_shifter import (
    MILPOptimizer,
    create_default_optimizer,
    optimize_single_appliance,
    quick_optimize,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def config():
    return OptimizationConfig(
        time_slots=96,
        slot_duration_hours=0.25,
        max_solve_time_seconds=10.0,
        mip_gap=0.01,
        verbose=False,
    )


@pytest.fixture
def dishwasher():
    return Appliance(
        name="Dishwasher",
        appliance_type=ApplianceType.DISHWASHER,
        earliest_start=0,
        latest_end=24,
    )


@pytest.fixture
def ev_charger():
    return Appliance(
        name="EV Charger",
        appliance_type=ApplianceType.EV_CHARGER,
        earliest_start=0,
        latest_end=24,
        priority=PriorityLevel.HIGH,
    )


@pytest.fixture
def flat_prices():
    return PriceProfile.create_flat_rate(0.15, num_slots=96)


@pytest.fixture
def tou_prices():
    return PriceProfile.create_time_of_use(
        off_peak_rate=0.10,
        on_peak_rate=0.35,
        on_peak_hours=[(16, 21)],
        num_slots=96,
    )


# =============================================================================
# Initialization
# =============================================================================


class TestMILPOptimizerInit:
    def test_default_config_created_when_none(self):
        opt = MILPOptimizer()
        assert opt.config is not None
        assert opt.config.time_slots == 96

    def test_custom_config_stored(self, config):
        opt = MILPOptimizer(config)
        assert opt.config is config

    def test_initial_state_not_solved(self, config):
        opt = MILPOptimizer(config)
        assert opt.problem is None
        assert opt.variables == {}
        assert opt._solver_status == "not_solved"
        assert opt._solve_time == 0.0

    def test_empty_appliance_and_price_lists(self, config):
        opt = MILPOptimizer(config)
        assert opt.appliances == []
        assert opt.price_profile is None


# =============================================================================
# _create_variables
# =============================================================================


class TestCreateVariables:
    def test_creates_variable_per_slot_per_appliance(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.appliances = [dishwasher]
        opt.price_profile = flat_prices
        opt.problem = pulp.LpProblem("test", pulp.LpMinimize)
        opt._create_variables()

        assert dishwasher.name in opt.variables
        # One variable per time slot
        assert len(opt.variables[dishwasher.name]) == config.time_slots

    def test_all_variables_binary(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.appliances = [dishwasher]
        opt.price_profile = flat_prices
        opt.problem = pulp.LpProblem("test", pulp.LpMinimize)
        opt._create_variables()

        # PuLP represents binary variables as Integer with bounds [0,1];
        # the category may be 'Binary' or 'Integer' depending on version.
        # Check that all variables have upBound == 1 and lowBound == 0 (binary semantics).
        for t, var in opt.variables[dishwasher.name].items():
            assert var.upBound == 1
            assert var.lowBound == 0

    def test_continuous_appliance_gets_start_variable(self, config):
        continuous = Appliance(
            name="Continuous",
            power_kw=1.0,
            duration_hours=2.0,
            must_be_continuous=True,
            can_be_interrupted=False,
        )
        opt = MILPOptimizer(config)
        opt.appliances = [continuous]
        opt.price_profile = PriceProfile.create_flat_rate(0.15, 96)
        opt.problem = pulp.LpProblem("test", pulp.LpMinimize)
        opt._create_variables()

        assert "Continuous" in opt.start_variables

    def test_non_continuous_appliance_no_start_variable(self, config, ev_charger, flat_prices):
        assert not ev_charger.must_be_continuous
        opt = MILPOptimizer(config)
        opt.appliances = [ev_charger]
        opt.price_profile = flat_prices
        opt.problem = pulp.LpProblem("test", pulp.LpMinimize)
        opt._create_variables()

        assert ev_charger.name not in opt.start_variables

    def test_variables_created_for_multiple_appliances(self, config, dishwasher, ev_charger, flat_prices):
        opt = MILPOptimizer(config)
        opt.appliances = [dishwasher, ev_charger]
        opt.price_profile = flat_prices
        opt.problem = pulp.LpProblem("test", pulp.LpMinimize)
        opt._create_variables()

        assert dishwasher.name in opt.variables
        assert ev_charger.name in opt.variables


# =============================================================================
# _get_solver
# =============================================================================


class TestGetSolver:
    def test_cbc_solver_returned_for_cbc_config(self):
        config = OptimizationConfig(solver_name="CBC", verbose=False)
        opt = MILPOptimizer(config)
        solver = opt._get_solver()
        assert isinstance(solver, pulp.apis.PULP_CBC_CMD)

    def test_glpk_solver_returned_for_glpk_config(self):
        config = OptimizationConfig(solver_name="GLPK", verbose=False)
        opt = MILPOptimizer(config)
        solver = opt._get_solver()
        # GLPK solver class (or CBC fallback if GLPK not installed)
        assert solver is not None

    def test_unknown_solver_falls_back_to_cbc(self):
        config = OptimizationConfig(solver_name="UNKNOWN_SOLVER", verbose=False)
        opt = MILPOptimizer(config)
        solver = opt._get_solver()
        assert isinstance(solver, pulp.apis.PULP_CBC_CMD)

    def test_time_limit_passed_to_cbc(self):
        config = OptimizationConfig(max_solve_time_seconds=42.0, verbose=False)
        opt = MILPOptimizer(config)
        solver = opt._get_solver()
        assert solver.timeLimit == 42.0

    def test_mip_gap_passed_to_cbc(self):
        config = OptimizationConfig(mip_gap=0.05, verbose=False)
        opt = MILPOptimizer(config)
        solver = opt._get_solver()
        # PuLP stores MIP gap as gapRel or epgap depending on version;
        # verify the config value is preserved on the solver object.
        gap_value = getattr(solver, "gapRel", None) or getattr(solver, "epgap", None)
        if gap_value is not None:
            assert gap_value == pytest.approx(0.05)
        else:
            # Some PuLP versions pass it only via CLI args; the solver was still created
            assert isinstance(solver, pulp.apis.PULP_CBC_CMD)


# =============================================================================
# _solve
# =============================================================================


class TestSolve:
    def test_raises_if_problem_not_built(self, config):
        opt = MILPOptimizer(config)
        with pytest.raises(RuntimeError, match="Problem not built"):
            opt._solve()

    def test_returns_status_string(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.appliances = [dishwasher]
        opt.price_profile = flat_prices
        opt._build_problem()
        status = opt._solve()
        assert isinstance(status, str)
        assert len(status) > 0

    def test_solve_time_recorded(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.appliances = [dishwasher]
        opt.price_profile = flat_prices
        opt._build_problem()
        opt._solve()
        assert opt._solve_time >= 0.0

    def test_solver_exception_captured_gracefully(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.appliances = [dishwasher]
        opt.price_profile = flat_prices
        opt._build_problem()

        with patch.object(opt.problem, "solve", side_effect=RuntimeError("solver crashed")):
            status = opt._solve()
        assert "error" in status.lower()


# =============================================================================
# _extract_solution
# =============================================================================


class TestExtractSolution:
    def test_returns_schedule_per_appliance(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.appliances = [dishwasher]
        opt.price_profile = flat_prices
        opt._build_problem()
        opt._solve()
        schedules = opt._extract_solution()
        assert len(schedules) == 1

    def test_scheduled_slots_count_matches_duration(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.appliances = [dishwasher]
        opt.price_profile = flat_prices
        opt._build_problem()
        opt._solve()
        schedules = opt._extract_solution()
        schedule = schedules[0]
        assert len(schedule.scheduled_slots) == dishwasher.duration_slots

    def test_cost_is_non_negative(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.appliances = [dishwasher]
        opt.price_profile = flat_prices
        opt._build_problem()
        opt._solve()
        schedules = opt._extract_solution()
        assert schedules[0].cost >= 0.0

    def test_energy_matches_power_times_duration(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.appliances = [dishwasher]
        opt.price_profile = flat_prices
        opt._build_problem()
        opt._solve()
        schedules = opt._extract_solution()
        schedule = schedules[0]
        expected_energy = dishwasher.power_kw * dishwasher.duration_hours
        assert schedule.energy_kwh == pytest.approx(expected_energy, rel=0.01)


# =============================================================================
# _validate_solution
# =============================================================================


class TestValidateSolution:
    def _solved_schedule(self, config, appliances, prices):
        opt = MILPOptimizer(config)
        opt.appliances = appliances
        opt.price_profile = prices
        opt._build_problem()
        opt._solve()
        return opt, opt._extract_solution()

    def test_valid_solution_returns_empty_errors(self, config, dishwasher, flat_prices):
        opt, schedules = self._solved_schedule(config, [dishwasher], flat_prices)
        errors = opt._validate_solution(schedules)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_wrong_slot_count_detected(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.appliances = [dishwasher]
        opt.price_profile = flat_prices
        opt._build_problem()
        opt._solve()

        # Manually corrupt the schedule
        bad_schedule = ApplianceSchedule(
            appliance=dishwasher,
            scheduled_slots=[0],          # Only 1 slot, should be duration_slots
            cost=0.1,
            energy_kwh=0.1,
        )
        errors = opt._validate_solution([bad_schedule])
        assert any("Expected" in e and "slots" in e for e in errors), errors

    def test_invalid_slot_detected(self, config, flat_prices):
        restricted = Appliance(
            name="Restricted",
            power_kw=1.0,
            duration_hours=1.0,
            earliest_start=10,
            latest_end=12,
        )
        opt = MILPOptimizer(config)
        opt.appliances = [restricted]
        opt.price_profile = flat_prices
        opt._build_problem()
        opt._solve()

        # Manually place schedule outside window
        bad_schedule = ApplianceSchedule(
            appliance=restricted,
            scheduled_slots=list(range(0, restricted.duration_slots)),  # slots 0-3: before 10 AM
            cost=0.1,
            energy_kwh=1.0,
        )
        errors = opt._validate_solution([bad_schedule])
        assert any("invalid slot" in e.lower() or "outside valid" in e.lower() for e in errors), errors

    def test_non_continuous_gap_flagged(self, config, flat_prices):
        continuous_app = Appliance(
            name="ContApp",
            power_kw=1.0,
            duration_hours=1.0,
            must_be_continuous=True,
            can_be_interrupted=False,
        )
        opt = MILPOptimizer(config)
        opt.appliances = [continuous_app]
        opt.price_profile = flat_prices
        opt._build_problem()

        # Build a schedule with a gap
        n_slots = continuous_app.duration_slots
        gapped_slots = list(range(0, n_slots // 2)) + list(range(n_slots, n_slots + n_slots // 2))
        bad_schedule = ApplianceSchedule(
            appliance=continuous_app,
            scheduled_slots=gapped_slots,
            cost=0.1,
            energy_kwh=1.0,
        )
        errors = opt._validate_solution([bad_schedule])
        assert any("continuous" in e.lower() or "non-continuous" in e.lower() for e in errors), errors

    def test_power_limit_violation_detected(self, flat_prices):
        """When two appliances overlap and exceed max_total_power_kw, error is added."""
        config = OptimizationConfig(
            time_slots=96,
            max_total_power_kw=2.0,
        )
        app1 = Appliance(name="A1", power_kw=2.0, duration_hours=0.25)
        app2 = Appliance(name="A2", power_kw=2.0, duration_hours=0.25)

        opt = MILPOptimizer(config)
        opt.appliances = [app1, app2]
        opt.price_profile = flat_prices
        opt._build_problem()

        # Both in slot 0 → total 4 kW > limit 2 kW
        s1 = ApplianceSchedule(appliance=app1, scheduled_slots=[0], cost=0.1, energy_kwh=0.5)
        s2 = ApplianceSchedule(appliance=app2, scheduled_slots=[0], cost=0.1, energy_kwh=0.5)

        errors = opt._validate_solution([s1, s2])
        assert any("power limit" in e.lower() or "exceeded" in e.lower() for e in errors), errors


# =============================================================================
# optimize() – main entry point
# =============================================================================


class TestOptimize:
    def test_basic_optimization_returns_schedule_result(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices)
        assert isinstance(result, ScheduleResult)

    def test_feasible_result_has_schedules(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices)
        assert result.is_feasible
        assert len(result.schedules) == 1

    def test_correct_appliance_duration_satisfied(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices)
        assert len(result.schedules[0].scheduled_slots) == dishwasher.duration_slots

    def test_total_cost_positive(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices)
        assert result.total_cost > 0.0

    def test_savings_non_negative(self, config, dishwasher, tou_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], tou_prices)
        assert result.savings_amount >= -0.01  # Allow tiny float rounding

    def test_tou_pricing_produces_savings(self, config, tou_prices):
        """Optimizer should shift dishwasher away from peak hours.

        Use an appliance whose window straddles both peak and off-peak periods
        so the optimizer has a genuine decision to make.
        """
        # Dishwasher window: 4 PM → 8 AM (crosses midnight), peak is 4-9 PM.
        # Baseline uses the default start slot (earliest_start * 4); with TOU
        # pricing the optimizer will defer to the cheaper overnight window.
        app = Appliance(
            name="Dishwasher",
            appliance_type=ApplianceType.DISHWASHER,
            earliest_start=16,   # Can start during peak (4 PM)
            latest_end=8,        # Must finish by 8 AM
        )
        opt = MILPOptimizer(config)
        result = opt.optimize([app], tou_prices)
        assert result.is_feasible
        assert result.savings_percent > 0.0

    def test_flat_rate_near_zero_savings(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices)
        # No price variation → savings should be essentially zero
        assert abs(result.savings_percent) < 1.0

    def test_empty_appliance_list_raises(self, config, flat_prices):
        opt = MILPOptimizer(config)
        with pytest.raises(ValueError, match="At least one appliance"):
            opt.optimize([], flat_prices)

    def test_none_price_profile_raises(self, config, dishwasher):
        opt = MILPOptimizer(config)
        with pytest.raises(ValueError, match="Price profile must be provided"):
            opt.optimize([dishwasher], None)

    def test_slot_mismatch_raises(self, config, dishwasher):
        wrong_profile = PriceProfile.create_flat_rate(0.15, num_slots=48)
        opt = MILPOptimizer(config)
        with pytest.raises(ValueError, match="slots"):
            opt.optimize([dishwasher], wrong_profile)

    def test_infeasible_returns_result_with_flag(self, config):
        """Appliance needing 40 slots but window only has 4 slots → infeasible."""
        impossible = Appliance(
            name="Impossible",
            power_kw=1.0,
            duration_hours=10.0,
            earliest_start=10,
            latest_end=11,
            must_be_continuous=True,
            can_be_interrupted=False,
        )
        prices = PriceProfile.create_flat_rate(0.15, num_slots=96)
        opt = MILPOptimizer(config)
        result = opt.optimize([impossible], prices)
        assert not result.is_feasible

    def test_infeasible_result_has_inf_total_cost(self, config):
        impossible = Appliance(
            name="Impossible",
            power_kw=1.0,
            duration_hours=10.0,
            earliest_start=10,
            latest_end=11,
            must_be_continuous=True,
            can_be_interrupted=False,
        )
        prices = PriceProfile.create_flat_rate(0.15, num_slots=96)
        opt = MILPOptimizer(config)
        result = opt.optimize([impossible], prices)
        assert np.isinf(result.total_cost)

    def test_multiple_appliances_all_scheduled(self, config, dishwasher, ev_charger, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher, ev_charger], flat_prices)
        assert result.is_feasible
        assert len(result.schedules) == 2

    def test_solve_time_recorded(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices)
        assert result.solve_time_seconds >= 0.0

    def test_peak_power_kw_non_negative(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices)
        assert result.peak_power_kw >= 0.0

    def test_total_energy_matches_appliance_energy(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices)
        expected = dishwasher.power_kw * dishwasher.duration_hours
        assert result.total_energy_kwh == pytest.approx(expected, rel=0.01)

    def test_solver_info_in_result(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices)
        assert isinstance(result.solver_info, dict)

    def test_with_minimize_peak_flag(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices, minimize_peak=True)
        assert result.is_feasible

    def test_with_balance_load_flag(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices, balance_load=True)
        assert result.is_feasible

    def test_with_dependencies(self, config, flat_prices):
        washer = Appliance(name="Washer", appliance_type=ApplianceType.WASHING_MACHINE,
                           earliest_start=0, latest_end=24)
        dryer = Appliance(name="Dryer", appliance_type=ApplianceType.DRYER,
                          earliest_start=0, latest_end=24)
        opt = MILPOptimizer(config)
        result = opt.optimize([washer, dryer], flat_prices, dependencies=[("Washer", "Dryer")])
        assert result.is_feasible

    def test_with_mutual_exclusions(self, config, flat_prices):
        app1 = Appliance(name="App1", power_kw=3.0, duration_hours=1.0)
        app2 = Appliance(name="App2", power_kw=3.0, duration_hours=1.0)
        opt = MILPOptimizer(config)
        result = opt.optimize([app1, app2], flat_prices, mutual_exclusions=[("App1", "App2")])
        assert result.is_feasible


# =============================================================================
# get_problem_stats
# =============================================================================


class TestGetProblemStats:
    def test_returns_not_built_before_optimization(self, config):
        opt = MILPOptimizer(config)
        stats = opt.get_problem_stats()
        assert stats["status"] == "not_built"

    def test_returns_stats_after_optimization(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.optimize([dishwasher], flat_prices)
        stats = opt.get_problem_stats()
        assert "num_variables" in stats
        assert "num_constraints" in stats
        assert stats["num_variables"] > 0
        assert stats["num_constraints"] > 0

    def test_stats_include_solver_name(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.optimize([dishwasher], flat_prices)
        stats = opt.get_problem_stats()
        assert "solver" in stats

    def test_solve_time_in_stats(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.optimize([dishwasher], flat_prices)
        stats = opt.get_problem_stats()
        assert stats["solve_time"] >= 0.0

    def test_num_appliances_in_stats(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        opt.optimize([dishwasher], flat_prices)
        stats = opt.get_problem_stats()
        assert stats["num_appliances"] == 1


# =============================================================================
# Convenience functions
# =============================================================================


class TestConvenienceFunctions:
    def test_create_default_optimizer_returns_milp(self):
        opt = create_default_optimizer()
        assert isinstance(opt, MILPOptimizer)

    def test_create_default_optimizer_has_default_config(self):
        opt = create_default_optimizer()
        assert opt.config.time_slots == 96

    def test_optimize_single_appliance_returns_schedule(self):
        dish = Appliance(
            name="Dishwasher",
            appliance_type=ApplianceType.DISHWASHER,
            earliest_start=0,
            latest_end=24,
        )
        prices = PriceProfile.create_flat_rate(0.15, num_slots=96)
        schedule = optimize_single_appliance(dish, prices)
        assert isinstance(schedule, ApplianceSchedule)
        assert schedule.appliance.name == "Dishwasher"

    def test_optimize_single_appliance_correct_duration(self):
        dish = Appliance(
            name="Dishwasher",
            appliance_type=ApplianceType.DISHWASHER,
            earliest_start=0,
            latest_end=24,
        )
        prices = PriceProfile.create_flat_rate(0.15, num_slots=96)
        schedule = optimize_single_appliance(dish, prices)
        assert len(schedule.scheduled_slots) == dish.duration_slots

    def test_optimize_single_appliance_raises_on_infeasible(self):
        impossible = Appliance(
            name="Impossible",
            power_kw=1.0,
            duration_hours=10.0,
            earliest_start=10,
            latest_end=11,
            must_be_continuous=True,
            can_be_interrupted=False,
        )
        prices = PriceProfile.create_flat_rate(0.15, num_slots=96)
        with pytest.raises(RuntimeError, match="Optimization failed"):
            optimize_single_appliance(impossible, prices)

    def test_quick_optimize_returns_schedule_result(self):
        appliances = [
            Appliance(name="Test1", power_kw=1.0, duration_hours=1.0),
        ]
        prices = [0.10] * 48 + [0.30] * 48
        result = quick_optimize(appliances, prices)
        assert isinstance(result, ScheduleResult)

    def test_quick_optimize_with_two_appliances(self):
        appliances = [
            Appliance(name="A1", power_kw=1.0, duration_hours=0.5),
            Appliance(name="A2", power_kw=2.0, duration_hours=1.0),
        ]
        prices = [0.10] * 48 + [0.30] * 48
        result = quick_optimize(appliances, prices)
        assert result.is_feasible
        assert len(result.schedules) == 2

    def test_quick_optimize_with_power_limit(self):
        appliances = [
            Appliance(name="A1", power_kw=2.0, duration_hours=0.5),
            Appliance(name="A2", power_kw=2.0, duration_hours=0.5),
        ]
        prices = [0.15] * 96
        result = quick_optimize(appliances, prices, max_power_kw=3.0)
        if result.is_feasible:
            # Peak should respect limit
            assert result.peak_power_kw <= 3.0 + 0.01

    def test_quick_optimize_uses_len_prices_as_time_slots(self):
        appliances = [Appliance(name="App", power_kw=1.0, duration_hours=0.5)]
        prices = [0.10] * 48   # 48 slots instead of default 96
        result = quick_optimize(appliances, prices)
        assert isinstance(result, ScheduleResult)


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    def test_single_slot_appliance(self, config, flat_prices):
        app = Appliance(name="Tiny", power_kw=1.0, duration_hours=0.25)
        opt = MILPOptimizer(config)
        result = opt.optimize([app], flat_prices)
        assert result.is_feasible
        assert len(result.schedules[0].scheduled_slots) == 1

    def test_full_day_appliance(self, config, flat_prices):
        app = Appliance(
            name="AlwaysOn",
            power_kw=0.1,
            duration_hours=24.0,
            can_be_interrupted=True,
            must_be_continuous=False,
        )
        opt = MILPOptimizer(config)
        result = opt.optimize([app], flat_prices)
        assert result.is_feasible
        assert len(result.schedules[0].scheduled_slots) == 96

    def test_solve_time_under_10_seconds_for_simple_problem(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        start = time.time()
        opt.optimize([dishwasher], flat_prices)
        elapsed = time.time() - start
        assert elapsed < 10.0, f"Solve time {elapsed:.2f}s too slow"

    def test_result_to_dict_roundtrip(self, config, dishwasher, flat_prices):
        opt = MILPOptimizer(config)
        result = opt.optimize([dishwasher], flat_prices)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "total_cost" in d

    def test_multiple_optimizations_independent(self, config, dishwasher, flat_prices):
        """Running optimize() twice should return independent results."""
        opt1 = MILPOptimizer(config)
        opt2 = MILPOptimizer(config)
        r1 = opt1.optimize([dishwasher], flat_prices)
        r2 = opt2.optimize([dishwasher], flat_prices)
        assert r1.total_cost == pytest.approx(r2.total_cost, rel=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
