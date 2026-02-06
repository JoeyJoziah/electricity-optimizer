"""
Appliance Data Models for MILP Optimization

This module defines the data structures for representing appliances,
their operational constraints, and optimization results.

Time Convention:
- All times are in 24-hour format (0-23 for hours)
- Time slots are 15-minute intervals (0-95 for a full day)
- Slot 0 = 00:00-00:15, Slot 95 = 23:45-24:00
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
import numpy as np


class ApplianceType(Enum):
    """Standard household appliance types with default characteristics."""

    DISHWASHER = "dishwasher"
    WASHING_MACHINE = "washing_machine"
    DRYER = "dryer"
    EV_CHARGER = "ev_charger"
    POOL_PUMP = "pool_pump"
    WATER_HEATER = "water_heater"
    HVAC = "hvac"
    CUSTOM = "custom"


class PriorityLevel(Enum):
    """Priority levels for appliance scheduling.

    Higher priority appliances get preference when there's competition
    for cheap time slots.
    """

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# Default characteristics for each appliance type
APPLIANCE_DEFAULTS: Dict[ApplianceType, Dict[str, Any]] = {
    ApplianceType.DISHWASHER: {
        "power_kw": 1.5,
        "duration_hours": 2.0,
        "must_be_continuous": True,
        "can_be_interrupted": False,
        "min_run_chunk_hours": 2.0,
    },
    ApplianceType.WASHING_MACHINE: {
        "power_kw": 2.0,
        "duration_hours": 1.5,
        "must_be_continuous": True,
        "can_be_interrupted": False,
        "min_run_chunk_hours": 1.5,
    },
    ApplianceType.DRYER: {
        "power_kw": 3.0,
        "duration_hours": 1.0,
        "must_be_continuous": True,
        "can_be_interrupted": False,
        "min_run_chunk_hours": 1.0,
    },
    ApplianceType.EV_CHARGER: {
        "power_kw": 7.0,
        "duration_hours": 6.0,
        "must_be_continuous": False,
        "can_be_interrupted": True,
        "min_run_chunk_hours": 0.5,
    },
    ApplianceType.POOL_PUMP: {
        "power_kw": 1.2,
        "duration_hours": 4.0,
        "must_be_continuous": False,
        "can_be_interrupted": True,
        "min_run_chunk_hours": 1.0,
    },
    ApplianceType.WATER_HEATER: {
        "power_kw": 4.0,
        "duration_hours": 2.0,
        "must_be_continuous": False,
        "can_be_interrupted": True,
        "min_run_chunk_hours": 0.25,
    },
    ApplianceType.HVAC: {
        "power_kw": 3.5,
        "duration_hours": 8.0,
        "must_be_continuous": False,
        "can_be_interrupted": True,
        "min_run_chunk_hours": 0.5,
    },
    ApplianceType.CUSTOM: {
        "power_kw": 1.0,
        "duration_hours": 1.0,
        "must_be_continuous": False,
        "can_be_interrupted": True,
        "min_run_chunk_hours": 0.25,
    },
}


@dataclass
class Appliance:
    """Represents a household appliance with scheduling constraints.

    Attributes:
        name: Human-readable name for the appliance
        appliance_type: Type of appliance (affects defaults)
        power_kw: Power consumption in kilowatts
        duration_hours: Total required run time in hours
        earliest_start: Earliest hour to start (0-23)
        latest_end: Latest hour to finish (0-23, can wrap to next day)
        must_be_continuous: If True, appliance must run continuously
        can_be_interrupted: If True, operation can be split into chunks
        min_run_chunk_hours: Minimum run time per chunk (if interruptible)
        priority: Scheduling priority level
        deadline_flexibility: How flexible the deadline is (0-1)
        max_interruptions: Maximum number of times operation can be paused
        user_preferences: Additional user-specified preferences
    """

    name: str
    appliance_type: ApplianceType = ApplianceType.CUSTOM
    power_kw: Optional[float] = None
    duration_hours: Optional[float] = None
    earliest_start: int = 0
    latest_end: int = 24
    must_be_continuous: Optional[bool] = None
    can_be_interrupted: Optional[bool] = None
    min_run_chunk_hours: Optional[float] = None
    priority: PriorityLevel = PriorityLevel.MEDIUM
    deadline_flexibility: float = 0.0
    max_interruptions: int = 10
    user_preferences: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Apply defaults based on appliance type."""
        defaults = APPLIANCE_DEFAULTS.get(self.appliance_type, {})

        if self.power_kw is None:
            self.power_kw = defaults.get("power_kw", 1.0)
        if self.duration_hours is None:
            self.duration_hours = defaults.get("duration_hours", 1.0)
        if self.must_be_continuous is None:
            self.must_be_continuous = defaults.get("must_be_continuous", False)
        if self.can_be_interrupted is None:
            self.can_be_interrupted = defaults.get("can_be_interrupted", True)
        if self.min_run_chunk_hours is None:
            self.min_run_chunk_hours = defaults.get("min_run_chunk_hours", 0.25)

        # Validate constraints
        self._validate()

    def _validate(self):
        """Validate appliance configuration."""
        if self.power_kw <= 0:
            raise ValueError(f"Power must be positive, got {self.power_kw}")
        if self.duration_hours <= 0:
            raise ValueError(f"Duration must be positive, got {self.duration_hours}")
        if not 0 <= self.earliest_start <= 23:
            raise ValueError(
                f"Earliest start must be 0-23, got {self.earliest_start}"
            )
        if not 0 <= self.latest_end <= 24:
            raise ValueError(f"Latest end must be 0-24, got {self.latest_end}")
        if self.must_be_continuous and self.can_be_interrupted:
            raise ValueError("Appliance cannot be both continuous and interruptible")
        if self.min_run_chunk_hours > self.duration_hours:
            raise ValueError("Min chunk hours cannot exceed total duration")

    @property
    def duration_slots(self) -> int:
        """Get duration in 15-minute time slots."""
        return int(np.ceil(self.duration_hours * 4))

    @property
    def min_chunk_slots(self) -> int:
        """Get minimum chunk size in 15-minute time slots."""
        return int(np.ceil(self.min_run_chunk_hours * 4))

    @property
    def energy_kwh(self) -> float:
        """Get total energy consumption in kWh."""
        return self.power_kw * self.duration_hours

    def get_valid_slots(self, num_slots: int = 96) -> List[int]:
        """Get list of valid time slots for this appliance.

        Args:
            num_slots: Total number of slots (default 96 for 24 hours)

        Returns:
            List of slot indices where appliance can run
        """
        start_slot = self.earliest_start * 4
        end_slot = self.latest_end * 4

        if end_slot > start_slot:
            # Normal case: window within same day
            return list(range(start_slot, min(end_slot, num_slots)))
        else:
            # Wrap-around case: window crosses midnight
            return list(range(start_slot, num_slots)) + list(range(0, end_slot))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "appliance_type": self.appliance_type.value,
            "power_kw": self.power_kw,
            "duration_hours": self.duration_hours,
            "earliest_start": self.earliest_start,
            "latest_end": self.latest_end,
            "must_be_continuous": self.must_be_continuous,
            "can_be_interrupted": self.can_be_interrupted,
            "min_run_chunk_hours": self.min_run_chunk_hours,
            "priority": self.priority.value,
            "deadline_flexibility": self.deadline_flexibility,
            "max_interruptions": self.max_interruptions,
            "user_preferences": self.user_preferences,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Appliance":
        """Create from dictionary."""
        data = data.copy()
        if "appliance_type" in data:
            data["appliance_type"] = ApplianceType(data["appliance_type"])
        if "priority" in data:
            data["priority"] = PriorityLevel(data["priority"])
        return cls(**data)


@dataclass
class ApplianceSchedule:
    """Scheduled operation times for a single appliance.

    Attributes:
        appliance: The appliance being scheduled
        scheduled_slots: List of time slot indices when appliance runs
        cost: Total cost for this appliance's operation
        energy_kwh: Total energy consumed
        start_time: Earliest scheduled slot (human-readable time)
        end_time: Latest scheduled slot (human-readable time)
    """

    appliance: Appliance
    scheduled_slots: List[int]
    cost: float
    energy_kwh: float

    @property
    def start_time(self) -> str:
        """Get human-readable start time."""
        if not self.scheduled_slots:
            return "Not scheduled"
        slot = min(self.scheduled_slots)
        return self._slot_to_time(slot)

    @property
    def end_time(self) -> str:
        """Get human-readable end time."""
        if not self.scheduled_slots:
            return "Not scheduled"
        slot = max(self.scheduled_slots) + 1  # End of last slot
        return self._slot_to_time(slot)

    @property
    def run_periods(self) -> List[Tuple[int, int]]:
        """Get list of continuous run periods as (start_slot, end_slot) tuples."""
        if not self.scheduled_slots:
            return []

        periods = []
        sorted_slots = sorted(self.scheduled_slots)
        period_start = sorted_slots[0]
        prev_slot = sorted_slots[0]

        for slot in sorted_slots[1:]:
            if slot != prev_slot + 1:
                # Gap found, end current period
                periods.append((period_start, prev_slot + 1))
                period_start = slot
            prev_slot = slot

        # Add final period
        periods.append((period_start, prev_slot + 1))
        return periods

    @staticmethod
    def _slot_to_time(slot: int) -> str:
        """Convert slot index to HH:MM format."""
        hour = (slot // 4) % 24
        minute = (slot % 4) * 15
        return f"{hour:02d}:{minute:02d}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "appliance": self.appliance.to_dict(),
            "scheduled_slots": self.scheduled_slots,
            "cost": self.cost,
            "energy_kwh": self.energy_kwh,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "run_periods": [
                (self._slot_to_time(s), self._slot_to_time(e))
                for s, e in self.run_periods
            ],
        }


@dataclass
class PriceProfile:
    """Electricity price profile for optimization.

    Attributes:
        prices: Array of prices for each time slot ($/kWh)
        slot_duration_hours: Duration of each slot in hours (default 0.25)
        currency: Currency code (default USD)
        profile_type: Type of pricing (flat, tou, realtime)
    """

    prices: np.ndarray
    slot_duration_hours: float = 0.25
    currency: str = "USD"
    profile_type: str = "realtime"

    def __post_init__(self):
        """Validate and convert prices."""
        if isinstance(self.prices, list):
            self.prices = np.array(self.prices, dtype=np.float64)

        if len(self.prices) < 1:
            raise ValueError("Price profile must have at least one value")

    @property
    def num_slots(self) -> int:
        """Get number of time slots."""
        return len(self.prices)

    @property
    def min_price(self) -> float:
        """Get minimum price."""
        return float(np.min(self.prices))

    @property
    def max_price(self) -> float:
        """Get maximum price."""
        return float(np.max(self.prices))

    @property
    def mean_price(self) -> float:
        """Get mean price."""
        return float(np.mean(self.prices))

    @property
    def price_spread(self) -> float:
        """Get price spread (max - min)."""
        return self.max_price - self.min_price

    def get_cheapest_slots(self, n: int) -> List[int]:
        """Get indices of n cheapest slots."""
        return list(np.argsort(self.prices)[:n])

    def get_slot_price(self, slot: int) -> float:
        """Get price for a specific slot."""
        return float(self.prices[slot % self.num_slots])

    def calculate_cost(self, slots: List[int], power_kw: float) -> float:
        """Calculate total cost for running at given slots.

        Args:
            slots: List of slot indices
            power_kw: Power consumption in kW

        Returns:
            Total cost in currency units
        """
        energy_per_slot = power_kw * self.slot_duration_hours
        return sum(
            self.get_slot_price(slot) * energy_per_slot for slot in slots
        )

    @classmethod
    def create_flat_rate(
        cls, rate: float, num_slots: int = 96
    ) -> "PriceProfile":
        """Create a flat-rate price profile.

        Args:
            rate: Constant price per kWh
            num_slots: Number of time slots

        Returns:
            PriceProfile with constant prices
        """
        return cls(
            prices=np.full(num_slots, rate),
            profile_type="flat",
        )

    @classmethod
    def create_time_of_use(
        cls,
        off_peak_rate: float,
        on_peak_rate: float,
        on_peak_hours: List[Tuple[int, int]],
        num_slots: int = 96,
    ) -> "PriceProfile":
        """Create a time-of-use price profile.

        Args:
            off_peak_rate: Off-peak price per kWh
            on_peak_rate: On-peak price per kWh
            on_peak_hours: List of (start_hour, end_hour) tuples for peak periods
            num_slots: Number of time slots

        Returns:
            PriceProfile with TOU pricing
        """
        prices = np.full(num_slots, off_peak_rate)

        for start_hour, end_hour in on_peak_hours:
            start_slot = start_hour * 4
            end_slot = end_hour * 4
            if end_slot > start_slot:
                prices[start_slot:end_slot] = on_peak_rate
            else:
                # Wrap around midnight
                prices[start_slot:] = on_peak_rate
                prices[:end_slot] = on_peak_rate

        return cls(prices=prices, profile_type="tou")

    @classmethod
    def create_realtime(
        cls,
        base_rate: float,
        volatility: float = 0.3,
        num_slots: int = 96,
        seed: Optional[int] = None,
    ) -> "PriceProfile":
        """Create a simulated real-time price profile.

        Args:
            base_rate: Base price per kWh
            volatility: Price volatility factor (0-1)
            num_slots: Number of time slots
            seed: Random seed for reproducibility

        Returns:
            PriceProfile with simulated real-time pricing
        """
        if seed is not None:
            np.random.seed(seed)

        # Create base pattern (higher during day, lower at night)
        hours = np.arange(num_slots) / 4
        daily_pattern = 1 + 0.3 * np.sin(2 * np.pi * (hours - 6) / 24)

        # Add random noise
        noise = 1 + volatility * np.random.randn(num_slots)
        noise = np.clip(noise, 0.5, 2.0)

        prices = base_rate * daily_pattern * noise
        prices = np.maximum(prices, 0.01)  # Ensure positive prices

        return cls(prices=prices, profile_type="realtime")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "prices": self.prices.tolist(),
            "slot_duration_hours": self.slot_duration_hours,
            "currency": self.currency,
            "profile_type": self.profile_type,
            "statistics": {
                "min": self.min_price,
                "max": self.max_price,
                "mean": self.mean_price,
                "spread": self.price_spread,
            },
        }


@dataclass
class ScheduleResult:
    """Complete optimization result.

    Attributes:
        schedules: List of individual appliance schedules
        total_cost: Total cost of optimized schedule
        baseline_cost: Cost if all appliances ran immediately
        savings_amount: Dollar savings vs baseline
        savings_percent: Percentage savings vs baseline
        solve_time_seconds: Time taken to solve optimization
        status: Optimization status (optimal, feasible, infeasible)
        total_energy_kwh: Total energy consumption
        peak_power_kw: Maximum instantaneous power
        solver_info: Additional solver information
    """

    schedules: List[ApplianceSchedule]
    total_cost: float
    baseline_cost: float
    savings_amount: float
    savings_percent: float
    solve_time_seconds: float
    status: str
    total_energy_kwh: float
    peak_power_kw: float
    solver_info: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_optimal(self) -> bool:
        """Check if solution is optimal."""
        return self.status.lower() == "optimal"

    @property
    def is_feasible(self) -> bool:
        """Check if a feasible solution was found."""
        return self.status.lower() in ("optimal", "feasible")

    def get_schedule_by_name(self, name: str) -> Optional[ApplianceSchedule]:
        """Get schedule for a specific appliance by name."""
        for schedule in self.schedules:
            if schedule.appliance.name == name:
                return schedule
        return None

    def get_power_profile(self, num_slots: int = 96) -> np.ndarray:
        """Get total power consumption for each time slot.

        Args:
            num_slots: Number of time slots

        Returns:
            Array of power consumption per slot
        """
        power = np.zeros(num_slots)
        for schedule in self.schedules:
            for slot in schedule.scheduled_slots:
                if slot < num_slots:
                    power[slot] += schedule.appliance.power_kw
        return power

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "schedules": [s.to_dict() for s in self.schedules],
            "total_cost": self.total_cost,
            "baseline_cost": self.baseline_cost,
            "savings_amount": self.savings_amount,
            "savings_percent": self.savings_percent,
            "solve_time_seconds": self.solve_time_seconds,
            "status": self.status,
            "total_energy_kwh": self.total_energy_kwh,
            "peak_power_kw": self.peak_power_kw,
            "solver_info": self.solver_info,
        }

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "=" * 60,
            "OPTIMIZATION RESULT SUMMARY",
            "=" * 60,
            f"Status: {self.status}",
            f"Solve Time: {self.solve_time_seconds:.2f} seconds",
            "",
            "COST ANALYSIS:",
            f"  Baseline Cost: ${self.baseline_cost:.2f}",
            f"  Optimized Cost: ${self.total_cost:.2f}",
            f"  Savings: ${self.savings_amount:.2f} ({self.savings_percent:.1f}%)",
            "",
            "ENERGY ANALYSIS:",
            f"  Total Energy: {self.total_energy_kwh:.2f} kWh",
            f"  Peak Power: {self.peak_power_kw:.2f} kW",
            "",
            "APPLIANCE SCHEDULES:",
        ]

        for schedule in self.schedules:
            lines.append(f"  {schedule.appliance.name}:")
            lines.append(f"    Run Time: {schedule.start_time} - {schedule.end_time}")
            lines.append(f"    Cost: ${schedule.cost:.2f}")
            lines.append(f"    Energy: {schedule.energy_kwh:.2f} kWh")
            if len(schedule.run_periods) > 1:
                lines.append(f"    Periods: {len(schedule.run_periods)} segments")

        lines.append("=" * 60)
        return "\n".join(lines)


@dataclass
class OptimizationConfig:
    """Configuration for the MILP optimizer.

    Attributes:
        time_slots: Number of time slots (default 96 for 15-min intervals)
        slot_duration_hours: Duration of each slot in hours
        max_solve_time_seconds: Maximum solver time limit
        mip_gap: Acceptable optimality gap (0.01 = 1%)
        max_total_power_kw: Maximum total power consumption limit
        solver_name: Name of solver to use (CBC, GLPK, etc.)
        verbose: Enable verbose solver output
        presolve: Enable presolve optimization
    """

    time_slots: int = 96
    slot_duration_hours: float = 0.25
    max_solve_time_seconds: float = 5.0
    mip_gap: float = 0.01
    max_total_power_kw: Optional[float] = None
    solver_name: str = "CBC"
    verbose: bool = False
    presolve: bool = True

    def __post_init__(self):
        """Validate configuration."""
        if self.time_slots < 1:
            raise ValueError("Must have at least 1 time slot")
        if self.slot_duration_hours <= 0:
            raise ValueError("Slot duration must be positive")
        if self.max_solve_time_seconds <= 0:
            raise ValueError("Max solve time must be positive")
        if not 0 <= self.mip_gap <= 1:
            raise ValueError("MIP gap must be between 0 and 1")

    @property
    def hours_per_day(self) -> float:
        """Get total hours covered by all slots."""
        return self.time_slots * self.slot_duration_hours

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "time_slots": self.time_slots,
            "slot_duration_hours": self.slot_duration_hours,
            "max_solve_time_seconds": self.max_solve_time_seconds,
            "mip_gap": self.mip_gap,
            "max_total_power_kw": self.max_total_power_kw,
            "solver_name": self.solver_name,
            "verbose": self.verbose,
            "presolve": self.presolve,
        }
