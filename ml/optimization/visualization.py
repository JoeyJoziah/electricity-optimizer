"""
Schedule Visualization for Appliance Optimization

This module provides visualization tools for displaying optimization results,
including:
- Gantt charts for appliance schedules
- Price profiles with scheduled operations
- Power consumption over time
- Cost breakdown charts
"""

from typing import List, Optional, Dict, Any, Tuple
from io import BytesIO
import numpy as np

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.colors import LinearSegmentedColormap
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

from ml.optimization.appliance_models import (
    ScheduleResult,
    PriceProfile,
    OptimizationConfig,
)


class ScheduleVisualizer:
    """Visualization tools for appliance scheduling results.

    Supports both matplotlib (static) and plotly (interactive) backends.
    Falls back gracefully if libraries are not installed.
    """

    # Color palette for appliances
    COLORS = [
        "#FF6B6B",  # Red
        "#4ECDC4",  # Teal
        "#45B7D1",  # Blue
        "#96CEB4",  # Green
        "#FFEAA7",  # Yellow
        "#DDA0DD",  # Plum
        "#98D8C8",  # Mint
        "#F7DC6F",  # Gold
        "#BB8FCE",  # Purple
        "#85C1E9",  # Light Blue
    ]

    def __init__(self, config: Optional[OptimizationConfig] = None):
        """Initialize visualizer.

        Args:
            config: Optimization configuration for time slot info
        """
        self.config = config or OptimizationConfig()

    def _slot_to_hour(self, slot: int) -> float:
        """Convert slot index to hour of day.

        Args:
            slot: Time slot index

        Returns:
            Hour as float (e.g., 14.5 for 2:30 PM)
        """
        return slot * self.config.slot_duration_hours

    def _format_time(self, slot: int) -> str:
        """Format slot as time string.

        Args:
            slot: Time slot index

        Returns:
            Time string in HH:MM format
        """
        hour = int(slot // 4)
        minute = int((slot % 4) * 15)
        return f"{hour:02d}:{minute:02d}"

    def plot_schedule_gantt(
        self,
        result: ScheduleResult,
        price_profile: Optional[PriceProfile] = None,
        figsize: Tuple[int, int] = (14, 8),
        save_path: Optional[str] = None,
        show_prices: bool = True,
    ) -> Optional[Any]:
        """Create Gantt chart of appliance schedules.

        Args:
            result: Optimization result to visualize
            price_profile: Optional price profile to overlay
            figsize: Figure size (width, height)
            save_path: Optional path to save figure
            show_prices: Whether to show price overlay

        Returns:
            Matplotlib figure or None if library not available
        """
        if not MATPLOTLIB_AVAILABLE:
            print("Matplotlib not available. Install with: pip install matplotlib")
            return None

        fig, ax1 = plt.subplots(figsize=figsize)

        # Number of appliances
        n_appliances = len(result.schedules)
        y_ticks = []
        y_labels = []

        # Plot each appliance
        for i, schedule in enumerate(result.schedules):
            y_pos = n_appliances - i - 1
            y_ticks.append(y_pos)
            y_labels.append(schedule.appliance.name)
            color = self.COLORS[i % len(self.COLORS)]

            for start, end in schedule.run_periods:
                start_hour = self._slot_to_hour(start)
                duration_hours = (end - start) * self.config.slot_duration_hours

                ax1.barh(
                    y_pos,
                    duration_hours,
                    left=start_hour,
                    height=0.6,
                    color=color,
                    edgecolor="black",
                    linewidth=1,
                    alpha=0.8,
                )

        ax1.set_yticks(y_ticks)
        ax1.set_yticklabels(y_labels)
        ax1.set_xlabel("Hour of Day")
        ax1.set_xlim(0, 24)
        ax1.set_ylim(-0.5, n_appliances - 0.5)
        ax1.grid(axis="x", alpha=0.3)

        # Add price overlay if provided
        if show_prices and price_profile is not None:
            ax2 = ax1.twinx()
            hours = np.arange(self.config.time_slots) * self.config.slot_duration_hours
            ax2.plot(
                hours,
                price_profile.prices,
                color="gray",
                linestyle="--",
                linewidth=1.5,
                alpha=0.7,
                label="Price ($/kWh)",
            )
            ax2.fill_between(
                hours,
                price_profile.prices,
                alpha=0.1,
                color="gray",
            )
            ax2.set_ylabel("Price ($/kWh)", color="gray")
            ax2.tick_params(axis="y", labelcolor="gray")
            ax2.legend(loc="upper right")

        # Add title and summary
        title = "Optimized Appliance Schedule\n"
        title += f"Total Cost: ${result.total_cost:.2f} "
        title += f"(Savings: {result.savings_percent:.1f}%)"
        ax1.set_title(title, fontsize=12, fontweight="bold")

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")

        return fig

    def plot_power_profile(
        self,
        result: ScheduleResult,
        price_profile: Optional[PriceProfile] = None,
        figsize: Tuple[int, int] = (12, 6),
        save_path: Optional[str] = None,
    ) -> Optional[Any]:
        """Plot power consumption over time.

        Args:
            result: Optimization result to visualize
            price_profile: Optional price profile to overlay
            figsize: Figure size (width, height)
            save_path: Optional path to save figure

        Returns:
            Matplotlib figure or None if library not available
        """
        if not MATPLOTLIB_AVAILABLE:
            print("Matplotlib not available. Install with: pip install matplotlib")
            return None

        fig, ax1 = plt.subplots(figsize=figsize)

        hours = np.arange(self.config.time_slots) * self.config.slot_duration_hours
        power_profile = result.get_power_profile(self.config.time_slots)

        # Stacked area chart for each appliance
        bottom = np.zeros(self.config.time_slots)
        for i, schedule in enumerate(result.schedules):
            power = np.zeros(self.config.time_slots)
            for slot in schedule.scheduled_slots:
                power[slot] = schedule.appliance.power_kw

            color = self.COLORS[i % len(self.COLORS)]
            ax1.fill_between(
                hours,
                bottom,
                bottom + power,
                color=color,
                alpha=0.7,
                label=schedule.appliance.name,
            )
            bottom += power

        ax1.set_xlabel("Hour of Day")
        ax1.set_ylabel("Power (kW)")
        ax1.set_xlim(0, 24)
        ax1.set_ylim(0, max(power_profile) * 1.1)
        ax1.legend(loc="upper left", fontsize=9)
        ax1.grid(alpha=0.3)

        # Add price overlay
        if price_profile is not None:
            ax2 = ax1.twinx()
            ax2.plot(
                hours,
                price_profile.prices,
                color="red",
                linestyle="--",
                linewidth=2,
                label="Price",
            )
            ax2.set_ylabel("Price ($/kWh)", color="red")
            ax2.tick_params(axis="y", labelcolor="red")

        ax1.set_title(
            f"Power Consumption Profile (Peak: {result.peak_power_kw:.1f} kW)",
            fontsize=12,
            fontweight="bold",
        )

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")

        return fig

    def plot_cost_breakdown(
        self,
        result: ScheduleResult,
        figsize: Tuple[int, int] = (10, 6),
        save_path: Optional[str] = None,
    ) -> Optional[Any]:
        """Plot cost breakdown by appliance.

        Args:
            result: Optimization result to visualize
            figsize: Figure size (width, height)
            save_path: Optional path to save figure

        Returns:
            Matplotlib figure or None if library not available
        """
        if not MATPLOTLIB_AVAILABLE:
            print("Matplotlib not available. Install with: pip install matplotlib")
            return None

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)

        # Pie chart of costs
        names = [s.appliance.name for s in result.schedules]
        costs = [s.cost for s in result.schedules]
        colors = [self.COLORS[i % len(self.COLORS)] for i in range(len(names))]

        ax1.pie(
            costs,
            labels=names,
            colors=colors,
            autopct=lambda pct: f"${pct/100*sum(costs):.2f}\n({pct:.1f}%)",
            startangle=90,
        )
        ax1.set_title("Cost by Appliance", fontweight="bold")

        # Bar chart comparing baseline vs optimized
        categories = ["Baseline", "Optimized"]
        values = [result.baseline_cost, result.total_cost]
        bar_colors = ["#E74C3C", "#27AE60"]

        bars = ax2.bar(categories, values, color=bar_colors, edgecolor="black")

        for bar, val in zip(bars, values):
            ax2.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.1,
                f"${val:.2f}",
                ha="center",
                fontsize=11,
                fontweight="bold",
            )

        ax2.set_ylabel("Cost ($)")
        ax2.set_title(
            f"Cost Comparison (Savings: ${result.savings_amount:.2f})",
            fontweight="bold",
        )
        ax2.set_ylim(0, max(values) * 1.2)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")

        return fig

    def plot_interactive_schedule(
        self,
        result: ScheduleResult,
        price_profile: Optional[PriceProfile] = None,
    ) -> Optional[Any]:
        """Create interactive Plotly visualization.

        Args:
            result: Optimization result to visualize
            price_profile: Optional price profile to overlay

        Returns:
            Plotly figure or None if library not available
        """
        if not PLOTLY_AVAILABLE:
            print("Plotly not available. Install with: pip install plotly")
            return None

        fig = make_subplots(
            rows=2,
            cols=1,
            subplot_titles=("Appliance Schedule", "Power Consumption"),
            vertical_spacing=0.15,
            row_heights=[0.5, 0.5],
        )

        # Gantt chart
        for i, schedule in enumerate(result.schedules):
            color = self.COLORS[i % len(self.COLORS)]

            for start, end in schedule.run_periods:
                start_hour = self._slot_to_hour(start)
                end_hour = self._slot_to_hour(end)

                fig.add_trace(
                    go.Bar(
                        x=[end_hour - start_hour],
                        y=[schedule.appliance.name],
                        orientation="h",
                        base=[start_hour],
                        marker_color=color,
                        name=schedule.appliance.name,
                        showlegend=i == 0 or start == schedule.run_periods[0][0],
                        text=f"${schedule.cost:.2f}",
                        textposition="inside",
                        hovertemplate=(
                            f"<b>{schedule.appliance.name}</b><br>"
                            f"Time: {self._format_time(start)} - {self._format_time(end)}<br>"
                            f"Power: {schedule.appliance.power_kw} kW<br>"
                            f"Cost: ${schedule.cost:.2f}<extra></extra>"
                        ),
                    ),
                    row=1,
                    col=1,
                )

        # Power profile
        hours = np.arange(self.config.time_slots) * self.config.slot_duration_hours
        power_profile = result.get_power_profile(self.config.time_slots)

        fig.add_trace(
            go.Scatter(
                x=hours,
                y=power_profile,
                fill="tozeroy",
                name="Total Power",
                line=dict(color="#3498DB", width=2),
            ),
            row=2,
            col=1,
        )

        # Add price overlay if provided
        if price_profile is not None:
            fig.add_trace(
                go.Scatter(
                    x=hours,
                    y=price_profile.prices,
                    name="Price ($/kWh)",
                    yaxis="y3",
                    line=dict(color="red", dash="dash"),
                ),
                row=2,
                col=1,
            )

        fig.update_layout(
            title=dict(
                text=(
                    f"<b>Optimized Schedule</b><br>"
                    f"<sup>Total: ${result.total_cost:.2f} | "
                    f"Savings: {result.savings_percent:.1f}%</sup>"
                ),
                x=0.5,
            ),
            barmode="stack",
            height=700,
            showlegend=True,
        )

        fig.update_xaxes(title_text="Hour of Day", range=[0, 24], row=1, col=1)
        fig.update_xaxes(title_text="Hour of Day", range=[0, 24], row=2, col=1)
        fig.update_yaxes(title_text="Power (kW)", row=2, col=1)

        return fig

    def generate_text_schedule(self, result: ScheduleResult) -> str:
        """Generate text-based schedule display.

        Args:
            result: Optimization result to display

        Returns:
            Formatted string representation of schedule
        """
        lines = []
        lines.append("=" * 70)
        lines.append("OPTIMIZED APPLIANCE SCHEDULE")
        lines.append("=" * 70)
        lines.append("")

        # Summary
        lines.append(f"Status: {result.status}")
        lines.append(f"Solve Time: {result.solve_time_seconds:.3f}s")
        lines.append("")
        lines.append("COST SUMMARY:")
        lines.append(f"  Baseline Cost:  ${result.baseline_cost:>8.2f}")
        lines.append(f"  Optimized Cost: ${result.total_cost:>8.2f}")
        lines.append(f"  Savings:        ${result.savings_amount:>8.2f} ({result.savings_percent:.1f}%)")
        lines.append("")
        lines.append(f"Total Energy: {result.total_energy_kwh:.2f} kWh")
        lines.append(f"Peak Power:   {result.peak_power_kw:.2f} kW")
        lines.append("")

        # Schedule timeline
        lines.append("SCHEDULE TIMELINE:")
        lines.append("-" * 70)

        # Create 24-hour timeline header
        hour_header = "Hour: "
        for h in range(0, 24, 2):
            hour_header += f"{h:02d}    "
        lines.append(hour_header)
        lines.append("-" * 70)

        # For each appliance, show a visual timeline
        for schedule in result.schedules:
            name = schedule.appliance.name[:15].ljust(15)
            timeline = ""

            for slot in range(self.config.time_slots):
                if slot in schedule.scheduled_slots:
                    timeline += "#"
                else:
                    timeline += "."

                # Add space every 8 slots (2 hours) for readability
                if (slot + 1) % 8 == 0 and slot < self.config.time_slots - 1:
                    timeline += " "

            lines.append(f"{name} |{timeline}|")

        lines.append("-" * 70)
        lines.append("Legend: # = Running, . = Off")
        lines.append("")

        # Detailed schedule
        lines.append("DETAILED SCHEDULE:")
        lines.append("-" * 70)

        for schedule in result.schedules:
            lines.append(f"\n{schedule.appliance.name}:")
            lines.append(f"  Type: {schedule.appliance.appliance_type.value}")
            lines.append(f"  Power: {schedule.appliance.power_kw} kW")
            lines.append(f"  Duration: {schedule.appliance.duration_hours} hours")
            lines.append(f"  Cost: ${schedule.cost:.2f}")

            if len(schedule.run_periods) == 1:
                start, end = schedule.run_periods[0]
                lines.append(
                    f"  Run Time: {self._format_time(start)} - {self._format_time(end)}"
                )
            else:
                lines.append(f"  Run Periods ({len(schedule.run_periods)}):")
                for i, (start, end) in enumerate(schedule.run_periods, 1):
                    lines.append(
                        f"    {i}. {self._format_time(start)} - {self._format_time(end)}"
                    )

        lines.append("")
        lines.append("=" * 70)

        return "\n".join(lines)

    def save_all_visualizations(
        self,
        result: ScheduleResult,
        price_profile: PriceProfile,
        output_dir: str,
        prefix: str = "schedule",
    ) -> List[str]:
        """Save all visualizations to files.

        Args:
            result: Optimization result to visualize
            price_profile: Price profile used
            output_dir: Directory to save files
            prefix: Filename prefix

        Returns:
            List of saved file paths
        """
        from pathlib import Path

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        saved_files = []

        # Gantt chart
        gantt_path = output_path / f"{prefix}_gantt.png"
        self.plot_schedule_gantt(
            result, price_profile, save_path=str(gantt_path)
        )
        if MATPLOTLIB_AVAILABLE:
            saved_files.append(str(gantt_path))
            plt.close()

        # Power profile
        power_path = output_path / f"{prefix}_power.png"
        self.plot_power_profile(
            result, price_profile, save_path=str(power_path)
        )
        if MATPLOTLIB_AVAILABLE:
            saved_files.append(str(power_path))
            plt.close()

        # Cost breakdown
        cost_path = output_path / f"{prefix}_cost.png"
        self.plot_cost_breakdown(result, save_path=str(cost_path))
        if MATPLOTLIB_AVAILABLE:
            saved_files.append(str(cost_path))
            plt.close()

        # Text schedule
        text_path = output_path / f"{prefix}_schedule.txt"
        with open(text_path, "w") as f:
            f.write(self.generate_text_schedule(result))
        saved_files.append(str(text_path))

        # Interactive HTML (if plotly available)
        if PLOTLY_AVAILABLE:
            html_path = output_path / f"{prefix}_interactive.html"
            fig = self.plot_interactive_schedule(result, price_profile)
            if fig:
                fig.write_html(str(html_path))
                saved_files.append(str(html_path))

        return saved_files


def quick_visualize(
    result: ScheduleResult,
    price_profile: Optional[PriceProfile] = None,
) -> None:
    """Quick visualization of optimization result.

    Args:
        result: Optimization result to visualize
        price_profile: Optional price profile
    """
    visualizer = ScheduleVisualizer()

    # Print text schedule
    print(visualizer.generate_text_schedule(result))

    # Try to show matplotlib plots
    if MATPLOTLIB_AVAILABLE:
        visualizer.plot_schedule_gantt(result, price_profile)
        plt.show()
