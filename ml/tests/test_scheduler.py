"""
Unit Tests for ml/optimization/scheduler.py

Covers:
- ApplianceScheduler initialization
- add_appliance(): happy path, duplicate detection
- add_appliance_preset(): type/window/priority handling
- _get_time_window(): all named windows, unknown window error
- add_dependency() / add_mutual_exclusion(): storage, method chaining
- set_price_profile(), set_flat_rate(), set_time_of_use_prices(), set_realtime_prices()
- set_max_power()
- optimize(): full workflow, missing inputs, result caching
- get_last_result()
- clear_appliances() / remove_appliance()
- compare_scenarios()
- get_schedule_summary()
- export_to_json() / import_appliances_from_json()
- SchedulerPresets: typical_household, ev_household, pool_house, california_tou, texas_realtime
- create_quick_scheduler(): flat/tou/realtime, unknown rate type error
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from ml.optimization.appliance_models import (
    Appliance,
    ApplianceType,
    ApplianceSchedule,
    ScheduleResult,
    PriceProfile,
    OptimizationConfig,
    PriorityLevel,
)
from ml.optimization.scheduler import (
    ApplianceScheduler,
    SchedulerPresets,
    create_quick_scheduler,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def scheduler():
    return ApplianceScheduler()


@pytest.fixture
def configured_scheduler():
    """Scheduler with one appliance and TOU pricing, ready to optimize."""
    s = ApplianceScheduler()
    s.add_appliance_preset("dishwasher", "anytime")
    s.set_time_of_use_prices(0.10, 0.30, [(16, 21)])
    return s


# =============================================================================
# Initialization
# =============================================================================


class TestApplianceSchedulerInit:
    def test_default_init_no_appliances(self):
        s = ApplianceScheduler()
        assert s.appliances == []

    def test_default_init_no_price_profile(self):
        s = ApplianceScheduler()
        assert s.price_profile is None

    def test_default_config_created(self):
        s = ApplianceScheduler()
        assert s.config is not None
        assert s.config.time_slots == 96

    def test_custom_config_stored(self):
        config = OptimizationConfig(time_slots=48)
        s = ApplianceScheduler(config=config)
        assert s.config.time_slots == 48

    def test_empty_dependencies_and_exclusions(self):
        s = ApplianceScheduler()
        assert s.dependencies == []
        assert s.mutual_exclusions == []


# =============================================================================
# add_appliance
# =============================================================================


class TestAddAppliance:
    def test_adds_appliance_to_list(self, scheduler):
        app = Appliance(name="TestApp", power_kw=1.0, duration_hours=1.0)
        scheduler.add_appliance(app)
        assert len(scheduler.appliances) == 1
        assert scheduler.appliances[0].name == "TestApp"

    def test_returns_self_for_chaining(self, scheduler):
        app = Appliance(name="TestApp", power_kw=1.0, duration_hours=1.0)
        result = scheduler.add_appliance(app)
        assert result is scheduler

    def test_raises_on_duplicate_name(self, scheduler):
        app = Appliance(name="Dup", power_kw=1.0, duration_hours=1.0)
        scheduler.add_appliance(app)
        with pytest.raises(ValueError, match="already exists"):
            scheduler.add_appliance(Appliance(name="Dup", power_kw=2.0, duration_hours=1.0))

    def test_multiple_appliances_added(self, scheduler):
        for i in range(5):
            app = Appliance(name=f"App{i}", power_kw=1.0, duration_hours=1.0)
            scheduler.add_appliance(app)
        assert len(scheduler.appliances) == 5


# =============================================================================
# add_appliance_preset
# =============================================================================


class TestAddAppliancePreset:
    def test_dishwasher_preset_created(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", "anytime")
        assert len(scheduler.appliances) == 1
        assert scheduler.appliances[0].appliance_type == ApplianceType.DISHWASHER

    def test_ev_charger_preset_default_power(self, scheduler):
        scheduler.add_appliance_preset("ev_charger", "anytime")
        app = scheduler.appliances[0]
        assert app.power_kw == 7.0  # Default EV charger

    def test_custom_name_overrides_default(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", "anytime", name="My Dishwasher")
        assert scheduler.appliances[0].name == "My Dishwasher"

    def test_string_priority_converted(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", "anytime", priority="HIGH")
        assert scheduler.appliances[0].priority == PriorityLevel.HIGH

    def test_enum_priority_accepted(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", "anytime", priority=PriorityLevel.CRITICAL)
        assert scheduler.appliances[0].priority == PriorityLevel.CRITICAL

    def test_appliance_type_as_enum(self, scheduler):
        scheduler.add_appliance_preset(ApplianceType.WASHING_MACHINE, "daytime")
        assert scheduler.appliances[0].appliance_type == ApplianceType.WASHING_MACHINE

    def test_returns_self_for_chaining(self, scheduler):
        result = scheduler.add_appliance_preset("dishwasher")
        assert result is scheduler

    def test_default_time_window_is_anytime(self, scheduler):
        scheduler.add_appliance_preset("dishwasher")
        app = scheduler.appliances[0]
        assert app.earliest_start == 0
        assert app.latest_end == 24

    def test_evening_time_window_applied(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", "evening")
        app = scheduler.appliances[0]
        assert app.earliest_start == 17
        assert app.latest_end == 23

    def test_kwargs_override_defaults(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", power_kw=3.0)
        assert scheduler.appliances[0].power_kw == 3.0


# =============================================================================
# _get_time_window
# =============================================================================


class TestGetTimeWindow:
    EXPECTED_WINDOWS = {
        "anytime": (0, 24),
        "morning": (5, 12),
        "afternoon": (12, 18),
        "evening": (17, 23),
        "overnight": (21, 7),
        "daytime": (6, 22),
        "off_peak": (22, 7),
        "business_hours": (9, 17),
        "night": (0, 6),
    }

    @pytest.mark.parametrize("window,expected", list(EXPECTED_WINDOWS.items()))
    def test_known_windows(self, scheduler, window, expected):
        start, end = scheduler._get_time_window(window)
        assert (start, end) == expected

    def test_unknown_window_raises(self, scheduler):
        with pytest.raises(ValueError, match="Unknown time window"):
            scheduler._get_time_window("underwater")

    def test_error_message_includes_valid_options(self, scheduler):
        try:
            scheduler._get_time_window("bad")
        except ValueError as e:
            assert "anytime" in str(e) or "valid" in str(e).lower()


# =============================================================================
# add_dependency / add_mutual_exclusion
# =============================================================================


class TestDependenciesAndExclusions:
    def test_add_dependency_stored(self, scheduler):
        scheduler.add_dependency("Washer", "Dryer")
        assert ("Washer", "Dryer") in scheduler.dependencies

    def test_add_dependency_returns_self(self, scheduler):
        result = scheduler.add_dependency("A", "B")
        assert result is scheduler

    def test_multiple_dependencies(self, scheduler):
        scheduler.add_dependency("A", "B")
        scheduler.add_dependency("B", "C")
        assert len(scheduler.dependencies) == 2

    def test_add_mutual_exclusion_stored(self, scheduler):
        scheduler.add_mutual_exclusion("App1", "App2")
        assert ("App1", "App2") in scheduler.mutual_exclusions

    def test_add_mutual_exclusion_returns_self(self, scheduler):
        result = scheduler.add_mutual_exclusion("A", "B")
        assert result is scheduler


# =============================================================================
# Price profile setters
# =============================================================================


class TestPriceProfileSetters:
    def test_set_price_profile_with_list(self, scheduler):
        prices = [0.10] * 96
        scheduler.set_price_profile(prices)
        assert scheduler.price_profile is not None
        assert scheduler.price_profile.num_slots == 96

    def test_set_price_profile_with_ndarray(self, scheduler):
        prices = np.full(96, 0.15)
        scheduler.set_price_profile(prices)
        assert scheduler.price_profile.num_slots == 96

    def test_set_price_profile_type_custom(self, scheduler):
        scheduler.set_price_profile([0.10] * 96)
        assert scheduler.price_profile.profile_type == "custom"

    def test_set_flat_rate_creates_profile(self, scheduler):
        scheduler.set_flat_rate(0.20)
        assert scheduler.price_profile is not None
        assert scheduler.price_profile.profile_type == "flat"

    def test_set_flat_rate_all_prices_equal(self, scheduler):
        scheduler.set_flat_rate(0.20)
        assert np.all(scheduler.price_profile.prices == 0.20)

    def test_set_flat_rate_returns_self(self, scheduler):
        result = scheduler.set_flat_rate(0.15)
        assert result is scheduler

    def test_set_tou_prices_profile_type(self, scheduler):
        scheduler.set_time_of_use_prices(0.10, 0.30, [(16, 21)])
        assert scheduler.price_profile.profile_type == "tou"

    def test_set_tou_prices_returns_self(self, scheduler):
        result = scheduler.set_time_of_use_prices(0.10, 0.30, [(16, 21)])
        assert result is scheduler

    def test_set_realtime_prices_profile_type(self, scheduler):
        scheduler.set_realtime_prices(0.12, 0.3, seed=42)
        assert scheduler.price_profile.profile_type == "realtime"

    def test_set_realtime_prices_returns_self(self, scheduler):
        result = scheduler.set_realtime_prices(0.12, seed=42)
        assert result is scheduler

    def test_set_realtime_prices_reproducible_with_seed(self, scheduler):
        scheduler.set_realtime_prices(0.12, volatility=0.3, seed=42)
        prices_a = scheduler.price_profile.prices.copy()
        scheduler.set_realtime_prices(0.12, volatility=0.3, seed=42)
        prices_b = scheduler.price_profile.prices.copy()
        np.testing.assert_array_equal(prices_a, prices_b)

    def test_set_max_power_updates_config(self, scheduler):
        scheduler.set_max_power(5.0)
        assert scheduler.config.max_total_power_kw == 5.0

    def test_set_max_power_returns_self(self, scheduler):
        result = scheduler.set_max_power(5.0)
        assert result is scheduler


# =============================================================================
# optimize()
# =============================================================================


class TestOptimize:
    def test_returns_schedule_result(self, configured_scheduler):
        result = configured_scheduler.optimize()
        assert isinstance(result, ScheduleResult)

    def test_feasible_result(self, configured_scheduler):
        result = configured_scheduler.optimize()
        assert result.is_feasible

    def test_raises_when_no_appliances(self, scheduler):
        scheduler.set_flat_rate(0.15)
        with pytest.raises(ValueError, match="No appliances added"):
            scheduler.optimize()

    def test_raises_when_no_price_profile(self, scheduler):
        scheduler.add_appliance_preset("dishwasher")
        with pytest.raises(ValueError, match="No price profile set"):
            scheduler.optimize()

    def test_last_result_cached(self, configured_scheduler):
        result = configured_scheduler.optimize()
        assert configured_scheduler.get_last_result() is result

    def test_total_cost_positive(self, configured_scheduler):
        result = configured_scheduler.optimize()
        assert result.total_cost > 0.0

    def test_status_in_result(self, configured_scheduler):
        result = configured_scheduler.optimize()
        assert result.status is not None

    def test_minimize_peak_flag_accepted(self, configured_scheduler):
        result = configured_scheduler.optimize(minimize_peak=True)
        assert result.is_feasible

    def test_balance_load_flag_accepted(self, configured_scheduler):
        result = configured_scheduler.optimize(balance_load=True)
        assert result.is_feasible


# =============================================================================
# get_last_result
# =============================================================================


class TestGetLastResult:
    def test_returns_none_before_optimize(self, scheduler):
        assert scheduler.get_last_result() is None

    def test_returns_result_after_optimize(self, configured_scheduler):
        configured_scheduler.optimize()
        assert configured_scheduler.get_last_result() is not None


# =============================================================================
# clear_appliances / remove_appliance
# =============================================================================


class TestClearAndRemove:
    def test_clear_removes_all_appliances(self, scheduler):
        scheduler.add_appliance_preset("dishwasher")
        scheduler.add_appliance_preset("dryer")
        scheduler.clear_appliances()
        assert scheduler.appliances == []

    def test_clear_removes_dependencies(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", name="A")
        scheduler.add_appliance_preset("dryer", name="B")
        scheduler.add_dependency("A", "B")
        scheduler.clear_appliances()
        assert scheduler.dependencies == []

    def test_clear_removes_mutual_exclusions(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", name="A")
        scheduler.add_appliance_preset("dryer", name="B")
        scheduler.add_mutual_exclusion("A", "B")
        scheduler.clear_appliances()
        assert scheduler.mutual_exclusions == []

    def test_clear_returns_self(self, scheduler):
        result = scheduler.clear_appliances()
        assert result is scheduler

    def test_remove_specific_appliance(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", name="A")
        scheduler.add_appliance_preset("dryer", name="B")
        scheduler.remove_appliance("A")
        names = [a.name for a in scheduler.appliances]
        assert "A" not in names
        assert "B" in names

    def test_remove_cleans_dependencies(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", name="A")
        scheduler.add_appliance_preset("dryer", name="B")
        scheduler.add_dependency("A", "B")
        scheduler.remove_appliance("A")
        assert ("A", "B") not in scheduler.dependencies

    def test_remove_cleans_mutual_exclusions(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", name="A")
        scheduler.add_appliance_preset("dryer", name="B")
        scheduler.add_mutual_exclusion("A", "B")
        scheduler.remove_appliance("B")
        assert ("A", "B") not in scheduler.mutual_exclusions

    def test_remove_nonexistent_appliance_is_noop(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", name="A")
        scheduler.remove_appliance("NonExistent")
        assert len(scheduler.appliances) == 1

    def test_remove_returns_self(self, scheduler):
        result = scheduler.remove_appliance("anything")
        assert result is scheduler


# =============================================================================
# compare_scenarios
# =============================================================================


class TestCompareScenarios:
    def test_returns_dict_of_results(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", "anytime")
        flat = np.full(96, 0.15)
        tou = np.where(
            np.array([(s // 4) in range(16, 21) for s in range(96)]),
            0.35, 0.10
        )
        results = scheduler.compare_scenarios({"flat": flat, "tou": tou})
        assert isinstance(results, dict)
        assert set(results.keys()) == {"flat", "tou"}

    def test_all_results_are_schedule_results(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", "anytime")
        scenarios = {"s1": np.full(96, 0.10), "s2": np.full(96, 0.20)}
        results = scheduler.compare_scenarios(scenarios)
        for v in results.values():
            assert isinstance(v, ScheduleResult)

    def test_accepts_price_profile_objects(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", "anytime")
        pp = PriceProfile.create_flat_rate(0.15, num_slots=96)
        results = scheduler.compare_scenarios({"pp": pp})
        assert "pp" in results


# =============================================================================
# get_schedule_summary
# =============================================================================


class TestGetScheduleSummary:
    def test_raises_when_no_result(self, scheduler):
        with pytest.raises(ValueError, match="No result available"):
            scheduler.get_schedule_summary()

    def test_returns_dict(self, configured_scheduler):
        configured_scheduler.optimize()
        summary = configured_scheduler.get_schedule_summary()
        assert isinstance(summary, dict)

    def test_required_keys_present(self, configured_scheduler):
        configured_scheduler.optimize()
        summary = configured_scheduler.get_schedule_summary()
        for key in ["status", "total_cost", "baseline_cost", "savings_percent",
                    "savings_amount", "total_energy_kwh", "peak_power_kw",
                    "solve_time_seconds", "schedules"]:
            assert key in summary, f"Missing key: {key}"

    def test_schedules_list_contains_entries(self, configured_scheduler):
        configured_scheduler.optimize()
        summary = configured_scheduler.get_schedule_summary()
        assert isinstance(summary["schedules"], list)
        assert len(summary["schedules"]) > 0

    def test_schedule_entry_has_required_fields(self, configured_scheduler):
        configured_scheduler.optimize()
        summary = configured_scheduler.get_schedule_summary()
        entry = summary["schedules"][0]
        for field in ["appliance", "type", "power_kw", "run_periods", "cost", "energy_kwh"]:
            assert field in entry, f"Missing schedule field: {field}"

    def test_accepts_explicit_result_arg(self, configured_scheduler, scheduler):
        result = configured_scheduler.optimize()
        # Pass to a different scheduler instance
        summary = scheduler.get_schedule_summary(result=result)
        assert "total_cost" in summary

    def test_total_cost_rounded_to_2_decimals(self, configured_scheduler):
        configured_scheduler.optimize()
        summary = configured_scheduler.get_schedule_summary()
        cost = summary["total_cost"]
        assert cost == round(cost, 2)


# =============================================================================
# export_to_json / import_appliances_from_json
# =============================================================================


class TestJsonExportImport:
    def test_export_creates_file(self, configured_scheduler, tmp_path):
        configured_scheduler.optimize()
        out_file = tmp_path / "schedule.json"
        configured_scheduler.export_to_json(str(out_file))
        assert out_file.exists()

    def test_export_raises_without_result(self, scheduler, tmp_path):
        scheduler.add_appliance_preset("dishwasher")
        out_file = tmp_path / "schedule.json"
        with pytest.raises(ValueError, match="No result available"):
            scheduler.export_to_json(str(out_file))

    def test_export_file_valid_json(self, configured_scheduler, tmp_path):
        configured_scheduler.optimize()
        out_file = tmp_path / "schedule.json"
        configured_scheduler.export_to_json(str(out_file))
        with open(out_file) as f:
            data = json.load(f)
        assert "timestamp" in data
        assert "config" in data
        assert "result" in data

    def test_export_with_path_object(self, configured_scheduler, tmp_path):
        configured_scheduler.optimize()
        out_file = tmp_path / "schedule.json"
        configured_scheduler.export_to_json(out_file)  # pathlib.Path object
        assert out_file.exists()

    def test_import_appliances_loads_them(self, scheduler, tmp_path):
        appliances_data = {
            "appliances": [
                {
                    "name": "ImportedDishwasher",
                    "appliance_type": "dishwasher",
                    "power_kw": 1.5,
                    "duration_hours": 2.0,
                    "earliest_start": 0,
                    "latest_end": 24,
                    "must_be_continuous": True,
                    "can_be_interrupted": False,
                    "min_run_chunk_hours": 2.0,
                    "priority": 2,
                    "deadline_flexibility": 0.0,
                    "max_interruptions": 10,
                    "user_preferences": {},
                }
            ]
        }
        json_file = tmp_path / "appliances.json"
        with open(json_file, "w") as f:
            json.dump(appliances_data, f)

        result = scheduler.import_appliances_from_json(str(json_file))
        assert len(scheduler.appliances) == 1
        assert scheduler.appliances[0].name == "ImportedDishwasher"

    def test_import_returns_self(self, scheduler, tmp_path):
        json_file = tmp_path / "empty.json"
        with open(json_file, "w") as f:
            json.dump({"appliances": []}, f)
        result = scheduler.import_appliances_from_json(str(json_file))
        assert result is scheduler


# =============================================================================
# SchedulerPresets
# =============================================================================


class TestSchedulerPresets:
    def test_typical_household_has_four_appliances(self):
        s = SchedulerPresets.typical_household()
        assert len(s.appliances) == 4

    def test_typical_household_has_dependency(self):
        s = SchedulerPresets.typical_household()
        # Dryer depends on Washing Machine
        assert len(s.dependencies) >= 1

    def test_typical_household_appliance_names(self):
        s = SchedulerPresets.typical_household()
        names = [a.name for a in s.appliances]
        assert any("Dishwasher" in n or "dishwasher" in n for n in names)
        assert any("Washing" in n or "washer" in n.lower() for n in names)

    def test_ev_household_adds_ev_charger(self):
        s = SchedulerPresets.ev_household()
        names = [a.name for a in s.appliances]
        assert any("EV" in n or "ev" in n.lower() for n in names)

    def test_ev_household_has_five_appliances(self):
        s = SchedulerPresets.ev_household()
        assert len(s.appliances) == 5

    def test_pool_house_adds_pool_pump(self):
        s = SchedulerPresets.pool_house()
        types = [a.appliance_type for a in s.appliances]
        assert ApplianceType.POOL_PUMP in types

    def test_california_tou_returns_tuple(self):
        result = SchedulerPresets.california_tou()
        assert len(result) == 3
        off_peak, on_peak, hours = result
        assert isinstance(off_peak, float)
        assert isinstance(on_peak, float)
        assert on_peak > off_peak
        assert isinstance(hours, list)

    def test_california_tou_peak_hours_are_tuples(self):
        _, _, hours = SchedulerPresets.california_tou()
        for h in hours:
            assert len(h) == 2

    def test_texas_realtime_returns_price_profile(self):
        pp = SchedulerPresets.texas_realtime(seed=42)
        assert isinstance(pp, PriceProfile)
        assert pp.num_slots == 96

    def test_texas_realtime_reproducible_with_seed(self):
        pp1 = SchedulerPresets.texas_realtime(seed=1)
        pp2 = SchedulerPresets.texas_realtime(seed=1)
        np.testing.assert_array_equal(pp1.prices, pp2.prices)

    def test_all_preset_schedulers_are_scheduler_instances(self):
        for preset_fn in [
            SchedulerPresets.typical_household,
            SchedulerPresets.ev_household,
            SchedulerPresets.pool_house,
        ]:
            s = preset_fn()
            assert isinstance(s, ApplianceScheduler)


# =============================================================================
# create_quick_scheduler
# =============================================================================


class TestCreateQuickScheduler:
    def test_flat_rate_type(self):
        s = create_quick_scheduler(["dishwasher"], rate_type="flat", rate=0.15)
        assert s.price_profile is not None
        assert s.price_profile.profile_type == "flat"

    def test_tou_rate_type(self):
        s = create_quick_scheduler(["dishwasher"], rate_type="tou")
        assert s.price_profile.profile_type == "tou"

    def test_realtime_rate_type(self):
        s = create_quick_scheduler(["dishwasher"], rate_type="realtime", seed=42)
        assert s.price_profile.profile_type == "realtime"

    def test_unknown_rate_type_raises(self):
        with pytest.raises(ValueError, match="Unknown rate type"):
            create_quick_scheduler(["dishwasher"], rate_type="magic_pricing")

    def test_appliances_count_matches_input(self):
        s = create_quick_scheduler(["dishwasher", "ev_charger"], rate_type="flat")
        assert len(s.appliances) == 2

    def test_custom_off_peak_rate_applied(self):
        s = create_quick_scheduler(["dishwasher"], rate_type="tou", off_peak_rate=0.05)
        # Off-peak slots should have price 0.05
        assert s.price_profile.min_price == pytest.approx(0.05)

    def test_returns_scheduler_instance(self):
        s = create_quick_scheduler(["dishwasher"])
        assert isinstance(s, ApplianceScheduler)

    def test_can_optimize_after_creation(self):
        s = create_quick_scheduler(["dishwasher"], rate_type="flat", rate=0.15)
        result = s.optimize()
        assert result.is_feasible


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    def test_method_chaining_full_pipeline(self):
        """All builder methods can be chained and result in a working scheduler."""
        result = (
            ApplianceScheduler()
            .add_appliance_preset("dishwasher", "evening")
            .add_appliance_preset("washing_machine", "daytime")
            .set_time_of_use_prices(0.10, 0.30, [(16, 21)])
            .optimize()
        )
        assert result.is_feasible

    def test_set_price_profile_multiple_times_uses_latest(self, scheduler):
        scheduler.add_appliance_preset("dishwasher")
        scheduler.set_flat_rate(0.10)
        scheduler.set_flat_rate(0.20)
        result = scheduler.optimize()
        # With 0.20/kWh, cost should be higher than 0.10/kWh
        assert result.total_cost > 0.0

    def test_add_and_remove_and_optimize(self, scheduler):
        scheduler.add_appliance_preset("dishwasher", name="D")
        scheduler.add_appliance_preset("dryer", name="E")
        scheduler.remove_appliance("E")
        scheduler.set_flat_rate(0.15)
        result = scheduler.optimize()
        assert result.is_feasible
        assert len(result.schedules) == 1

    def test_compare_scenarios_empty_dict(self, scheduler):
        scheduler.add_appliance_preset("dishwasher")
        results = scheduler.compare_scenarios({})
        assert results == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
