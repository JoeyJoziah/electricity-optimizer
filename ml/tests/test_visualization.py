"""
Unit Tests for ml/optimization/visualization.py

Covers:
- ScheduleVisualizer initialization and helpers (_slot_to_hour, _format_time)
- generate_text_schedule: content correctness, structure
- plot_schedule_gantt: returns figure or None (matplotlib absent)
- plot_power_profile: returns figure or None
- plot_cost_breakdown: returns figure or None
- plot_interactive_schedule: returns figure or None (plotly absent)
- save_all_visualizations: file creation and return paths
- quick_visualize: smoke test
- Behaviour with and without price_profile overlay

All matplotlib/plotly calls are handled via controlled mocking to keep tests
fast and headless. When the real library IS available its __new__ path is also
exercised via the mock to avoid displaying plots.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import numpy as np
import pytest

from ml.optimization.appliance_models import (
    Appliance,
    ApplianceType,
    ApplianceSchedule,
    ScheduleResult,
    PriceProfile,
    OptimizationConfig,
)
from ml.optimization.visualization import (
    ScheduleVisualizer,
    quick_visualize,
    MATPLOTLIB_AVAILABLE,
    PLOTLY_AVAILABLE,
)


# =============================================================================
# Fixtures / Helpers
# =============================================================================


def _make_appliance(
    name="Dishwasher",
    appliance_type=ApplianceType.DISHWASHER,
    power_kw=1.5,
    duration_hours=2.0,
    earliest_start=0,
    latest_end=24,
):
    return Appliance(
        name=name,
        appliance_type=appliance_type,
        power_kw=power_kw,
        duration_hours=duration_hours,
        earliest_start=earliest_start,
        latest_end=latest_end,
    )


def _make_schedule(appliance: Appliance, start_slot: int = 0):
    """Create an ApplianceSchedule whose slots start at start_slot."""
    n_slots = appliance.duration_slots
    slots = list(range(start_slot, start_slot + n_slots))
    cost = sum(0.15 * appliance.power_kw * 0.25 for _ in slots)
    return ApplianceSchedule(
        appliance=appliance,
        scheduled_slots=slots,
        cost=cost,
        energy_kwh=appliance.power_kw * appliance.duration_hours,
    )


def _make_schedule_result(appliances=None, start_slots=None):
    """Build a minimal ScheduleResult from appliances and their start slots."""
    if appliances is None:
        dish = _make_appliance()
        ev = _make_appliance("EV Charger", ApplianceType.EV_CHARGER, 7.0, 6.0, 0, 24)
        appliances = [dish, ev]
    if start_slots is None:
        start_slots = [0] * len(appliances)

    schedules = [_make_schedule(a, s) for a, s in zip(appliances, start_slots)]
    total_cost = sum(s.cost for s in schedules)
    baseline_cost = total_cost * 1.3

    power_profile = np.zeros(96)
    for sched in schedules:
        for slot in sched.scheduled_slots:
            power_profile[slot] += sched.appliance.power_kw

    return ScheduleResult(
        schedules=schedules,
        total_cost=total_cost,
        baseline_cost=baseline_cost,
        savings_amount=baseline_cost - total_cost,
        savings_percent=(baseline_cost - total_cost) / baseline_cost * 100,
        solve_time_seconds=0.1,
        status="Optimal",
        total_energy_kwh=sum(s.energy_kwh for s in schedules),
        peak_power_kw=float(np.max(power_profile)),
        solver_info={},
    )


def _make_price_profile():
    prices = np.full(96, 0.10)
    prices[64:84] = 0.35
    return PriceProfile(prices=prices, profile_type="tou")


@pytest.fixture
def result():
    return _make_schedule_result()


@pytest.fixture
def price_profile():
    return _make_price_profile()


@pytest.fixture
def visualizer():
    return ScheduleVisualizer()


# =============================================================================
# Initialization
# =============================================================================


class TestScheduleVisualizerInit:
    def test_default_config_created_when_none(self):
        v = ScheduleVisualizer()
        assert v.config is not None
        assert v.config.time_slots == 96

    def test_custom_config_accepted(self):
        config = OptimizationConfig(time_slots=48, slot_duration_hours=0.5)
        v = ScheduleVisualizer(config=config)
        assert v.config.time_slots == 48

    def test_colors_palette_has_entries(self):
        v = ScheduleVisualizer()
        assert len(ScheduleVisualizer.COLORS) >= 5


# =============================================================================
# Helper methods
# =============================================================================


class TestHelperMethods:
    def test_slot_to_hour_slot_zero(self, visualizer):
        assert visualizer._slot_to_hour(0) == pytest.approx(0.0)

    def test_slot_to_hour_slot_four_is_one_hour(self, visualizer):
        assert visualizer._slot_to_hour(4) == pytest.approx(1.0)

    def test_slot_to_hour_slot_48_is_twelve(self, visualizer):
        assert visualizer._slot_to_hour(48) == pytest.approx(12.0)

    def test_format_time_slot_zero(self, visualizer):
        assert visualizer._format_time(0) == "00:00"

    def test_format_time_slot_four(self, visualizer):
        assert visualizer._format_time(4) == "01:00"

    def test_format_time_slot_48(self, visualizer):
        assert visualizer._format_time(48) == "12:00"

    def test_format_time_slot_95(self, visualizer):
        assert visualizer._format_time(95) == "23:45"

    def test_format_time_slot_half_hour(self, visualizer):
        # slot 2 = 00:30
        assert visualizer._format_time(2) == "00:30"


# =============================================================================
# generate_text_schedule
# =============================================================================


class TestGenerateTextSchedule:
    def test_returns_string(self, visualizer, result):
        text = visualizer.generate_text_schedule(result)
        assert isinstance(text, str)

    def test_contains_header(self, visualizer, result):
        text = visualizer.generate_text_schedule(result)
        assert "OPTIMIZED APPLIANCE SCHEDULE" in text

    def test_contains_appliance_names(self, visualizer, result):
        text = visualizer.generate_text_schedule(result)
        for sched in result.schedules:
            assert sched.appliance.name[:10] in text

    def test_contains_cost_summary(self, visualizer, result):
        text = visualizer.generate_text_schedule(result)
        assert "$" in text

    def test_contains_status(self, visualizer, result):
        text = visualizer.generate_text_schedule(result)
        assert result.status in text

    def test_contains_timeline_header(self, visualizer, result):
        text = visualizer.generate_text_schedule(result)
        assert "SCHEDULE TIMELINE" in text

    def test_contains_detailed_section(self, visualizer, result):
        text = visualizer.generate_text_schedule(result)
        assert "DETAILED SCHEDULE" in text

    def test_single_appliance_run_period_format(self, visualizer):
        dish = _make_appliance()
        sched = _make_schedule(dish, start_slot=20)
        single_result = _make_schedule_result([dish], [20])
        text = visualizer.generate_text_schedule(single_result)
        assert "Run Time" in text

    def test_multi_period_appliance_shows_periods(self, visualizer):
        """When an appliance has non-contiguous slots, show multiple periods."""
        dish = _make_appliance()
        # Force two separate periods by hand
        n_slots = dish.duration_slots
        half = n_slots // 2
        slots = list(range(0, half)) + list(range(20, 20 + (n_slots - half)))
        sched = ApplianceSchedule(
            appliance=dish,
            scheduled_slots=slots,
            cost=0.5,
            energy_kwh=3.0,
        )
        multi_result = ScheduleResult(
            schedules=[sched],
            total_cost=0.5,
            baseline_cost=0.7,
            savings_amount=0.2,
            savings_percent=28.0,
            solve_time_seconds=0.1,
            status="Optimal",
            total_energy_kwh=3.0,
            peak_power_kw=1.5,
            solver_info={},
        )
        text = visualizer.generate_text_schedule(multi_result)
        assert "Run Periods" in text

    def test_legend_present(self, visualizer, result):
        text = visualizer.generate_text_schedule(result)
        assert "Legend" in text

    def test_non_empty_output(self, visualizer, result):
        text = visualizer.generate_text_schedule(result)
        assert len(text) > 200


# =============================================================================
# plot_schedule_gantt (matplotlib path)
# =============================================================================


class TestPlotScheduleGantt:
    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
    def test_returns_figure_when_matplotlib_available(self, visualizer, result):
        import matplotlib.pyplot as plt
        with patch("matplotlib.pyplot.subplots") as mock_subplots:
            fig_mock = MagicMock()
            ax_mock = MagicMock()
            mock_subplots.return_value = (fig_mock, ax_mock)
            with patch("matplotlib.pyplot.tight_layout"):
                fig = visualizer.plot_schedule_gantt(result)
            assert fig is fig_mock

    def test_returns_none_when_matplotlib_unavailable(self, result):
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False):
            v = ScheduleVisualizer()
            fig = v.plot_schedule_gantt(result)
            assert fig is None

    def test_matplotlib_unavailable_prints_message(self, result, capsys):
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False):
            v = ScheduleVisualizer()
            v.plot_schedule_gantt(result)
            captured = capsys.readouterr()
            assert "matplotlib" in captured.out.lower() or captured.out == ""

    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
    def test_with_price_profile_adds_second_axis(self, visualizer, result, price_profile):
        import matplotlib.pyplot as plt
        with patch("matplotlib.pyplot.subplots") as mock_subplots:
            fig_mock = MagicMock()
            ax1_mock = MagicMock()
            ax2_mock = MagicMock()
            ax1_mock.twinx.return_value = ax2_mock
            mock_subplots.return_value = (fig_mock, ax1_mock)
            with patch("matplotlib.pyplot.tight_layout"):
                visualizer.plot_schedule_gantt(result, price_profile=price_profile, show_prices=True)
            ax1_mock.twinx.assert_called_once()

    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
    def test_save_path_calls_savefig(self, visualizer, result, tmp_path):
        import matplotlib.pyplot as plt
        save_path = str(tmp_path / "gantt.png")
        with patch("matplotlib.pyplot.subplots") as mock_subplots:
            fig_mock = MagicMock()
            ax_mock = MagicMock()
            mock_subplots.return_value = (fig_mock, ax_mock)
            with patch("matplotlib.pyplot.tight_layout"):
                visualizer.plot_schedule_gantt(result, save_path=save_path)
            fig_mock.savefig.assert_called_once()


# =============================================================================
# plot_power_profile (matplotlib path)
# =============================================================================


class TestPlotPowerProfile:
    def test_returns_none_when_matplotlib_unavailable(self, result):
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False):
            v = ScheduleVisualizer()
            assert v.plot_power_profile(result) is None

    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
    def test_returns_figure_when_available(self, visualizer, result):
        with patch("matplotlib.pyplot.subplots") as mock_subplots:
            fig_mock = MagicMock()
            ax_mock = MagicMock()
            mock_subplots.return_value = (fig_mock, ax_mock)
            with patch("matplotlib.pyplot.tight_layout"):
                fig = visualizer.plot_power_profile(result)
            assert fig is fig_mock

    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
    def test_with_price_overlay_adds_twinx(self, visualizer, result, price_profile):
        with patch("matplotlib.pyplot.subplots") as mock_subplots:
            fig_mock = MagicMock()
            ax1_mock = MagicMock()
            ax2_mock = MagicMock()
            ax1_mock.twinx.return_value = ax2_mock
            mock_subplots.return_value = (fig_mock, ax1_mock)
            with patch("matplotlib.pyplot.tight_layout"):
                visualizer.plot_power_profile(result, price_profile=price_profile)
            ax1_mock.twinx.assert_called_once()


# =============================================================================
# plot_cost_breakdown (matplotlib path)
# =============================================================================


class TestPlotCostBreakdown:
    def test_returns_none_when_matplotlib_unavailable(self, result):
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False):
            v = ScheduleVisualizer()
            assert v.plot_cost_breakdown(result) is None

    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
    def test_returns_figure_when_available(self, visualizer, result):
        with patch("matplotlib.pyplot.subplots") as mock_subplots:
            fig_mock = MagicMock()
            ax1_mock = MagicMock()
            ax2_mock = MagicMock()
            ax1_mock.pie.return_value = ([MagicMock()], [MagicMock()], [MagicMock()])
            ax2_mock.bar.return_value = [MagicMock(get_x=MagicMock(return_value=0),
                                                    get_width=MagicMock(return_value=0.5),
                                                    get_height=MagicMock(return_value=1.0)),
                                         MagicMock(get_x=MagicMock(return_value=1),
                                                   get_width=MagicMock(return_value=0.5),
                                                   get_height=MagicMock(return_value=0.8))]
            mock_subplots.return_value = (fig_mock, (ax1_mock, ax2_mock))
            with patch("matplotlib.pyplot.tight_layout"):
                fig = visualizer.plot_cost_breakdown(result)
            assert fig is fig_mock


# =============================================================================
# plot_interactive_schedule (plotly path)
# =============================================================================


class TestPlotInteractiveSchedule:
    def test_returns_none_when_plotly_unavailable(self, result):
        with patch("ml.optimization.visualization.PLOTLY_AVAILABLE", False):
            v = ScheduleVisualizer()
            fig = v.plot_interactive_schedule(result)
            assert fig is None

    def test_plotly_unavailable_prints_message(self, result, capsys):
        with patch("ml.optimization.visualization.PLOTLY_AVAILABLE", False):
            v = ScheduleVisualizer()
            v.plot_interactive_schedule(result)
            captured = capsys.readouterr()
            # Either a message is printed or nothing — both are acceptable
            if captured.out:
                assert "plotly" in captured.out.lower()

    @pytest.mark.skipif(not PLOTLY_AVAILABLE, reason="plotly not installed")
    def test_returns_figure_when_plotly_available(self, visualizer, result):
        from unittest.mock import patch as _patch
        import plotly.graph_objects as go
        fig = visualizer.plot_interactive_schedule(result)
        assert fig is not None

    @pytest.mark.skipif(not PLOTLY_AVAILABLE, reason="plotly not installed")
    def test_adds_price_trace_when_profile_provided(self, visualizer, result, price_profile):
        fig = visualizer.plot_interactive_schedule(result, price_profile=price_profile)
        # Figure should have more traces than without price profile
        fig_no_price = visualizer.plot_interactive_schedule(result)
        assert len(fig.data) > len(fig_no_price.data)


# =============================================================================
# save_all_visualizations
# =============================================================================


class TestSaveAllVisualizations:
    def test_always_saves_text_schedule(self, visualizer, result, price_profile, tmp_path):
        """Text schedule should be saved regardless of library availability."""
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False), \
             patch("ml.optimization.visualization.PLOTLY_AVAILABLE", False):
            saved = visualizer.save_all_visualizations(result, price_profile, str(tmp_path))
        text_files = [f for f in saved if f.endswith(".txt")]
        assert len(text_files) == 1
        assert os.path.isfile(text_files[0])

    def test_text_file_has_schedule_content(self, visualizer, result, price_profile, tmp_path):
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False), \
             patch("ml.optimization.visualization.PLOTLY_AVAILABLE", False):
            saved = visualizer.save_all_visualizations(result, price_profile, str(tmp_path))
        txt = next(f for f in saved if f.endswith(".txt"))
        content = Path(txt).read_text()
        assert "OPTIMIZED APPLIANCE SCHEDULE" in content

    def test_creates_output_directory(self, visualizer, result, price_profile, tmp_path):
        new_dir = str(tmp_path / "new_subdir")
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False), \
             patch("ml.optimization.visualization.PLOTLY_AVAILABLE", False):
            visualizer.save_all_visualizations(result, price_profile, new_dir)
        assert os.path.isdir(new_dir)

    def test_prefix_applied_to_filenames(self, visualizer, result, price_profile, tmp_path):
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False), \
             patch("ml.optimization.visualization.PLOTLY_AVAILABLE", False):
            saved = visualizer.save_all_visualizations(
                result, price_profile, str(tmp_path), prefix="myrun"
            )
        for path in saved:
            assert os.path.basename(path).startswith("myrun")

    def test_returns_list_of_strings(self, visualizer, result, price_profile, tmp_path):
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False), \
             patch("ml.optimization.visualization.PLOTLY_AVAILABLE", False):
            saved = visualizer.save_all_visualizations(result, price_profile, str(tmp_path))
        assert isinstance(saved, list)
        assert all(isinstance(p, str) for p in saved)

    @pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
    def test_matplotlib_files_saved_when_available(self, visualizer, result, price_profile, tmp_path):
        import matplotlib.pyplot as plt
        with patch("matplotlib.pyplot.subplots") as mock_subplots, \
             patch("matplotlib.pyplot.tight_layout"), \
             patch("matplotlib.pyplot.close"), \
             patch("ml.optimization.visualization.PLOTLY_AVAILABLE", False):
            fig_mock = MagicMock()
            ax_mock = MagicMock()
            ax_mock.pie.return_value = ([MagicMock()], [MagicMock()], [MagicMock()])
            ax_mock.bar.return_value = [
                MagicMock(get_x=MagicMock(return_value=0),
                          get_width=MagicMock(return_value=0.5),
                          get_height=MagicMock(return_value=1.0)),
                MagicMock(get_x=MagicMock(return_value=1),
                          get_width=MagicMock(return_value=0.5),
                          get_height=MagicMock(return_value=0.8)),
            ]
            mock_subplots.return_value = (fig_mock, (ax_mock, ax_mock))
            saved = visualizer.save_all_visualizations(result, price_profile, str(tmp_path))
        png_files = [f for f in saved if f.endswith(".png")]
        assert len(png_files) >= 1


# =============================================================================
# quick_visualize
# =============================================================================


class TestQuickVisualize:
    def test_prints_text_schedule(self, result, capsys):
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False):
            quick_visualize(result)
        captured = capsys.readouterr()
        assert "OPTIMIZED APPLIANCE SCHEDULE" in captured.out

    def test_no_crash_without_price_profile(self, result):
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False):
            quick_visualize(result, price_profile=None)

    def test_no_crash_with_price_profile(self, result, price_profile):
        with patch("ml.optimization.visualization.MATPLOTLIB_AVAILABLE", False):
            quick_visualize(result, price_profile=price_profile)


# =============================================================================
# Edge Cases
# =============================================================================


class TestVisualizationEdgeCases:
    def test_single_appliance_result(self):
        dish = _make_appliance()
        single_result = _make_schedule_result([dish], [0])
        v = ScheduleVisualizer()
        text = v.generate_text_schedule(single_result)
        assert "Dishwasher" in text

    def test_empty_schedules_in_result(self):
        """Result with no schedules should not crash text generation."""
        empty_result = ScheduleResult(
            schedules=[],
            total_cost=0.0,
            baseline_cost=1.0,
            savings_amount=1.0,
            savings_percent=100.0,
            solve_time_seconds=0.0,
            status="Infeasible",
            total_energy_kwh=0.0,
            peak_power_kw=0.0,
            solver_info={},
        )
        v = ScheduleVisualizer()
        text = v.generate_text_schedule(empty_result)
        assert "OPTIMIZED APPLIANCE SCHEDULE" in text

    def test_many_appliances_color_cycling(self):
        """More appliances than colors should use modulo cycling without error."""
        n = len(ScheduleVisualizer.COLORS) + 3
        appliances = [
            _make_appliance(f"App{i}", ApplianceType.CUSTOM, 1.0, 0.25, 0, 24)
            for i in range(n)
        ]
        start_slots = list(range(0, n * 1, 1))
        result = _make_schedule_result(appliances, start_slots)
        v = ScheduleVisualizer()
        text = v.generate_text_schedule(result)
        assert "App0" in text

    def test_slot_duration_respected_in_hour_conversion(self):
        """Custom slot_duration_hours should affect _slot_to_hour."""
        config = OptimizationConfig(time_slots=48, slot_duration_hours=0.5)
        v = ScheduleVisualizer(config=config)
        # slot 2 = 1 hour with 0.5h slots
        assert v._slot_to_hour(2) == pytest.approx(1.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
