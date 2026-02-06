"""
High-Level Scheduling API for Appliance Optimization

This module provides a user-friendly interface for appliance scheduling,
abstracting away the complexity of the MILP optimizer.

Features:
- Simple appliance registration
- Price profile management
- Preset configurations for common scenarios
- Result caching and comparison
- Integration with external data sources
"""

import json
from typing import List, Dict, Optional, Any, Tuple, Union
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

from ml.optimization.appliance_models import (
    Appliance,
    ApplianceType,
    ApplianceSchedule,
    ScheduleResult,
    PriceProfile,
    OptimizationConfig,
    PriorityLevel,
)
from ml.optimization.load_shifter import MILPOptimizer


class ApplianceScheduler:
    """High-level API for appliance scheduling optimization.

    This class provides a simplified interface for:
    - Registering appliances with common presets
    - Setting up price profiles
    - Running optimization
    - Comparing results and scenarios

    Example:
        scheduler = ApplianceScheduler()
        scheduler.add_appliance_preset("dishwasher", "evening")
        scheduler.add_appliance_preset("ev_charger", "overnight")
        scheduler.set_time_of_use_prices(0.12, 0.25, [(14, 20)])
        result = scheduler.optimize()
        print(result.summary())
    """

    def __init__(self, config: Optional[OptimizationConfig] = None):
        """Initialize the scheduler.

        Args:
            config: Optional optimization configuration
        """
        self.config = config or OptimizationConfig()
        self.appliances: List[Appliance] = []
        self.price_profile: Optional[PriceProfile] = None
        self.dependencies: List[Tuple[str, str]] = []
        self.mutual_exclusions: List[Tuple[str, str]] = []
        self._last_result: Optional[ScheduleResult] = None
        self._optimizer: Optional[MILPOptimizer] = None

    def add_appliance(self, appliance: Appliance) -> "ApplianceScheduler":
        """Add an appliance to be scheduled.

        Args:
            appliance: Appliance to add

        Returns:
            Self for method chaining
        """
        # Check for duplicate names
        if any(a.name == appliance.name for a in self.appliances):
            raise ValueError(f"Appliance '{appliance.name}' already exists")

        self.appliances.append(appliance)
        return self

    def add_appliance_preset(
        self,
        appliance_type: Union[str, ApplianceType],
        time_window: str = "anytime",
        name: Optional[str] = None,
        priority: Union[str, PriorityLevel] = PriorityLevel.MEDIUM,
        **kwargs,
    ) -> "ApplianceScheduler":
        """Add an appliance using preset configurations.

        Args:
            appliance_type: Type of appliance (string or ApplianceType)
            time_window: Time window preset ("anytime", "morning", "afternoon",
                        "evening", "overnight", "daytime", "off_peak")
            name: Optional custom name (defaults to type name)
            priority: Priority level (string or PriorityLevel)
            **kwargs: Additional appliance parameters to override

        Returns:
            Self for method chaining
        """
        # Convert string to enum if needed
        if isinstance(appliance_type, str):
            appliance_type = ApplianceType(appliance_type.lower())

        if isinstance(priority, str):
            priority = PriorityLevel[priority.upper()]

        # Get time window
        earliest_start, latest_end = self._get_time_window(time_window)

        # Create appliance
        appliance_name = name or appliance_type.value.replace("_", " ").title()

        appliance = Appliance(
            name=appliance_name,
            appliance_type=appliance_type,
            earliest_start=earliest_start,
            latest_end=latest_end,
            priority=priority,
            **kwargs,
        )

        return self.add_appliance(appliance)

    def _get_time_window(self, window: str) -> Tuple[int, int]:
        """Get (earliest_start, latest_end) for a named time window.

        Args:
            window: Time window name

        Returns:
            Tuple of (earliest_start_hour, latest_end_hour)
        """
        windows = {
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

        if window not in windows:
            raise ValueError(
                f"Unknown time window '{window}'. "
                f"Valid options: {list(windows.keys())}"
            )

        return windows[window]

    def add_dependency(
        self,
        predecessor: str,
        successor: str,
    ) -> "ApplianceScheduler":
        """Add a dependency between appliances.

        The predecessor must complete before the successor can start.

        Args:
            predecessor: Name of appliance that must finish first
            successor: Name of appliance that must start after

        Returns:
            Self for method chaining
        """
        self.dependencies.append((predecessor, successor))
        return self

    def add_mutual_exclusion(
        self,
        appliance1: str,
        appliance2: str,
    ) -> "ApplianceScheduler":
        """Add mutual exclusion between appliances.

        The two appliances cannot run simultaneously.

        Args:
            appliance1: First appliance name
            appliance2: Second appliance name

        Returns:
            Self for method chaining
        """
        self.mutual_exclusions.append((appliance1, appliance2))
        return self

    def set_price_profile(self, prices: Union[List[float], np.ndarray]) -> "ApplianceScheduler":
        """Set a custom price profile.

        Args:
            prices: Array of prices for each time slot ($/kWh)

        Returns:
            Self for method chaining
        """
        self.price_profile = PriceProfile(
            prices=np.array(prices),
            profile_type="custom",
        )
        return self

    def set_flat_rate(self, rate: float) -> "ApplianceScheduler":
        """Set a flat electricity rate.

        Args:
            rate: Price per kWh

        Returns:
            Self for method chaining
        """
        self.price_profile = PriceProfile.create_flat_rate(
            rate=rate,
            num_slots=self.config.time_slots,
        )
        return self

    def set_time_of_use_prices(
        self,
        off_peak_rate: float,
        on_peak_rate: float,
        on_peak_hours: List[Tuple[int, int]],
    ) -> "ApplianceScheduler":
        """Set time-of-use pricing.

        Args:
            off_peak_rate: Off-peak price per kWh
            on_peak_rate: On-peak price per kWh
            on_peak_hours: List of (start_hour, end_hour) tuples for peak periods

        Returns:
            Self for method chaining
        """
        self.price_profile = PriceProfile.create_time_of_use(
            off_peak_rate=off_peak_rate,
            on_peak_rate=on_peak_rate,
            on_peak_hours=on_peak_hours,
            num_slots=self.config.time_slots,
        )
        return self

    def set_realtime_prices(
        self,
        base_rate: float,
        volatility: float = 0.3,
        seed: Optional[int] = None,
    ) -> "ApplianceScheduler":
        """Set simulated real-time pricing.

        Args:
            base_rate: Base price per kWh
            volatility: Price volatility factor (0-1)
            seed: Random seed for reproducibility

        Returns:
            Self for method chaining
        """
        self.price_profile = PriceProfile.create_realtime(
            base_rate=base_rate,
            volatility=volatility,
            num_slots=self.config.time_slots,
            seed=seed,
        )
        return self

    def set_max_power(self, max_power_kw: float) -> "ApplianceScheduler":
        """Set maximum total power consumption limit.

        Args:
            max_power_kw: Maximum allowed total power in kW

        Returns:
            Self for method chaining
        """
        self.config.max_total_power_kw = max_power_kw
        return self

    def optimize(
        self,
        minimize_peak: bool = False,
        minimize_interruptions: bool = False,
        balance_load: bool = False,
    ) -> ScheduleResult:
        """Run the optimization.

        Args:
            minimize_peak: Include peak power minimization
            minimize_interruptions: Penalize interruptions
            balance_load: Balance load across time

        Returns:
            ScheduleResult with optimized schedules

        Raises:
            ValueError: If no appliances or price profile set
        """
        if not self.appliances:
            raise ValueError("No appliances added. Use add_appliance() first.")
        if self.price_profile is None:
            raise ValueError(
                "No price profile set. Use set_price_profile() or similar."
            )

        # Create optimizer
        self._optimizer = MILPOptimizer(self.config)

        # Run optimization
        result = self._optimizer.optimize(
            appliances=self.appliances,
            price_profile=self.price_profile,
            minimize_peak=minimize_peak,
            minimize_interruptions=minimize_interruptions,
            balance_load=balance_load,
            dependencies=self.dependencies if self.dependencies else None,
            mutual_exclusions=(
                self.mutual_exclusions if self.mutual_exclusions else None
            ),
        )

        self._last_result = result
        return result

    def get_last_result(self) -> Optional[ScheduleResult]:
        """Get the result from the last optimization.

        Returns:
            Last ScheduleResult or None if no optimization run
        """
        return self._last_result

    def clear_appliances(self) -> "ApplianceScheduler":
        """Remove all appliances.

        Returns:
            Self for method chaining
        """
        self.appliances = []
        self.dependencies = []
        self.mutual_exclusions = []
        return self

    def remove_appliance(self, name: str) -> "ApplianceScheduler":
        """Remove an appliance by name.

        Args:
            name: Name of appliance to remove

        Returns:
            Self for method chaining
        """
        self.appliances = [a for a in self.appliances if a.name != name]

        # Clean up dependencies and exclusions
        self.dependencies = [
            (p, s) for p, s in self.dependencies if p != name and s != name
        ]
        self.mutual_exclusions = [
            (a, b) for a, b in self.mutual_exclusions if a != name and b != name
        ]

        return self

    def compare_scenarios(
        self,
        scenario_prices: Dict[str, Union[List[float], PriceProfile]],
    ) -> Dict[str, ScheduleResult]:
        """Compare optimization results across different price scenarios.

        Args:
            scenario_prices: Dictionary mapping scenario names to price profiles

        Returns:
            Dictionary mapping scenario names to ScheduleResult
        """
        results = {}

        for name, prices in scenario_prices.items():
            if isinstance(prices, PriceProfile):
                self.price_profile = prices
            else:
                self.set_price_profile(prices)

            results[name] = self.optimize()

        return results

    def get_schedule_summary(
        self,
        result: Optional[ScheduleResult] = None,
    ) -> Dict[str, Any]:
        """Get a summary of the schedule suitable for display.

        Args:
            result: ScheduleResult to summarize (uses last result if not provided)

        Returns:
            Dictionary with schedule summary
        """
        result = result or self._last_result
        if result is None:
            raise ValueError("No result available. Run optimize() first.")

        schedule_list = []
        for schedule in result.schedules:
            periods = []
            for start, end in schedule.run_periods:
                start_time = schedule._slot_to_time(start)
                end_time = schedule._slot_to_time(end)
                periods.append(f"{start_time}-{end_time}")

            schedule_list.append({
                "appliance": schedule.appliance.name,
                "type": schedule.appliance.appliance_type.value,
                "power_kw": schedule.appliance.power_kw,
                "run_periods": periods,
                "cost": round(schedule.cost, 2),
                "energy_kwh": round(schedule.energy_kwh, 2),
            })

        return {
            "status": result.status,
            "total_cost": round(result.total_cost, 2),
            "baseline_cost": round(result.baseline_cost, 2),
            "savings_percent": round(result.savings_percent, 1),
            "savings_amount": round(result.savings_amount, 2),
            "total_energy_kwh": round(result.total_energy_kwh, 2),
            "peak_power_kw": round(result.peak_power_kw, 2),
            "solve_time_seconds": round(result.solve_time_seconds, 3),
            "schedules": schedule_list,
        }

    def export_to_json(
        self,
        filepath: Union[str, Path],
        result: Optional[ScheduleResult] = None,
    ) -> None:
        """Export schedule to JSON file.

        Args:
            filepath: Output file path
            result: ScheduleResult to export (uses last result if not provided)
        """
        result = result or self._last_result
        if result is None:
            raise ValueError("No result available. Run optimize() first.")

        data = {
            "timestamp": datetime.now().isoformat(),
            "config": self.config.to_dict(),
            "result": result.to_dict(),
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def import_appliances_from_json(
        self,
        filepath: Union[str, Path],
    ) -> "ApplianceScheduler":
        """Import appliances from JSON file.

        Args:
            filepath: Input file path

        Returns:
            Self for method chaining
        """
        with open(filepath, "r") as f:
            data = json.load(f)

        for app_data in data.get("appliances", []):
            appliance = Appliance.from_dict(app_data)
            self.add_appliance(appliance)

        return self


class SchedulerPresets:
    """Factory class for common scheduler configurations."""

    @staticmethod
    def typical_household() -> ApplianceScheduler:
        """Create scheduler with typical household appliances.

        Returns:
            Configured ApplianceScheduler
        """
        scheduler = ApplianceScheduler()

        scheduler.add_appliance_preset("dishwasher", "evening", priority="medium")
        scheduler.add_appliance_preset("washing_machine", "daytime", priority="medium")
        scheduler.add_appliance_preset("dryer", "daytime", priority="low")
        scheduler.add_appliance_preset("water_heater", "anytime", priority="low")

        # Dryer should run after washing machine
        scheduler.add_dependency("Washing Machine", "Dryer")

        return scheduler

    @staticmethod
    def ev_household() -> ApplianceScheduler:
        """Create scheduler for household with EV.

        Returns:
            Configured ApplianceScheduler
        """
        scheduler = SchedulerPresets.typical_household()

        scheduler.add_appliance_preset(
            "ev_charger",
            "overnight",
            priority="high",
            name="EV Charger",
        )

        return scheduler

    @staticmethod
    def pool_house() -> ApplianceScheduler:
        """Create scheduler for house with pool.

        Returns:
            Configured ApplianceScheduler
        """
        scheduler = SchedulerPresets.typical_household()

        scheduler.add_appliance_preset(
            "pool_pump",
            "daytime",
            priority="low",
            name="Pool Pump",
        )

        return scheduler

    @staticmethod
    def california_tou() -> Tuple[float, float, List[Tuple[int, int]]]:
        """Get typical California TOU rate structure.

        Returns:
            Tuple of (off_peak_rate, on_peak_rate, on_peak_hours)
        """
        return (0.12, 0.35, [(16, 21)])  # 4 PM - 9 PM peak

    @staticmethod
    def texas_realtime(seed: Optional[int] = None) -> PriceProfile:
        """Get simulated Texas real-time pricing.

        Args:
            seed: Random seed for reproducibility

        Returns:
            PriceProfile with real-time pricing
        """
        return PriceProfile.create_realtime(
            base_rate=0.08,
            volatility=0.5,
            seed=seed,
        )


def create_quick_scheduler(
    appliances: List[str],
    rate_type: str = "tou",
    **kwargs,
) -> ApplianceScheduler:
    """Quick setup for common scenarios.

    Args:
        appliances: List of appliance types to include
        rate_type: Pricing type ("flat", "tou", "realtime")
        **kwargs: Additional arguments for pricing

    Returns:
        Configured ApplianceScheduler ready to optimize
    """
    scheduler = ApplianceScheduler()

    # Add appliances
    for app_type in appliances:
        scheduler.add_appliance_preset(app_type)

    # Set pricing
    if rate_type == "flat":
        rate = kwargs.get("rate", 0.15)
        scheduler.set_flat_rate(rate)
    elif rate_type == "tou":
        off_peak, on_peak, hours = SchedulerPresets.california_tou()
        off_peak = kwargs.get("off_peak_rate", off_peak)
        on_peak = kwargs.get("on_peak_rate", on_peak)
        hours = kwargs.get("on_peak_hours", hours)
        scheduler.set_time_of_use_prices(off_peak, on_peak, hours)
    elif rate_type == "realtime":
        base = kwargs.get("base_rate", 0.10)
        volatility = kwargs.get("volatility", 0.3)
        seed = kwargs.get("seed", None)
        scheduler.set_realtime_prices(base, volatility, seed)
    else:
        raise ValueError(f"Unknown rate type: {rate_type}")

    return scheduler
