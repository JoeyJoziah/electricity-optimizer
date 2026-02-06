"""
MILP-based Appliance Scheduling Optimization Module

This module provides Mixed Integer Linear Programming (MILP) optimization
for scheduling household appliances to minimize electricity costs.

Key Components:
- appliance_models: Data models for appliances and their constraints
- constraints: Constraint builders for the MILP problem
- objective: Objective function formulation
- load_shifter: Core MILP optimizer using PuLP
- scheduler: High-level scheduling API
- visualization: Schedule visualization tools

Algorithm Overview:
The optimization minimizes total electricity cost over a 24-hour period
using 15-minute time slots (96 total). Each appliance is modeled with:
- Binary decision variables for each time slot
- Constraints for operation duration, time windows, and continuity
- Power consumption limits and user preferences

Example Usage:
    from ml.optimization import ApplianceScheduler, Appliance, ApplianceType

    scheduler = ApplianceScheduler()

    # Add appliances
    scheduler.add_appliance(Appliance(
        name="Dishwasher",
        appliance_type=ApplianceType.DISHWASHER,
        power_kw=1.5,
        duration_hours=2.0,
        earliest_start=18,  # 6 PM
        latest_end=8,       # 8 AM next day
        must_be_continuous=True
    ))

    # Set price profile (96 values for 15-min intervals)
    scheduler.set_price_profile(prices)

    # Optimize
    result = scheduler.optimize()
    print(f"Total cost: ${result.total_cost:.2f}")
    print(f"Savings vs baseline: {result.savings_percent:.1f}%")
"""

from ml.optimization.appliance_models import (
    Appliance,
    ApplianceType,
    ScheduleResult,
    ApplianceSchedule,
    PriceProfile,
    OptimizationConfig,
)
from ml.optimization.load_shifter import MILPOptimizer
from ml.optimization.scheduler import ApplianceScheduler
from ml.optimization.visualization import ScheduleVisualizer

__all__ = [
    "Appliance",
    "ApplianceType",
    "ScheduleResult",
    "ApplianceSchedule",
    "PriceProfile",
    "OptimizationConfig",
    "MILPOptimizer",
    "ApplianceScheduler",
    "ScheduleVisualizer",
]

__version__ = "1.0.0"
