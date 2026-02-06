# MILP Appliance Scheduling Optimization

This module implements a Mixed Integer Linear Programming (MILP) optimizer for scheduling
household appliances to minimize electricity costs while respecting operational constraints.

## Overview

The optimization system schedules appliances across 96 time slots (15-minute intervals over 24 hours)
to minimize total electricity cost while satisfying:

- **Duration constraints**: Each appliance runs for its required time
- **Time window constraints**: Operation within user-specified hours
- **Continuity constraints**: Continuous operation for appliances that require it
- **Power limits**: Maximum simultaneous power consumption
- **User preferences**: Priority levels and scheduling preferences

## Performance Results

Validated on realistic scenarios:

| Scenario | Savings | Solve Time |
|----------|---------|------------|
| TOU Pricing (3.5x peak ratio) | 51.3% | 0.1s |
| Real-Time Pricing (volatile) | 40.2% | 0.08s |
| Average across 5 scenarios | 28.2% | <0.2s |

**All tests achieve the target of 15%+ savings with solve times under 5 seconds.**

## Installation

```bash
pip install pulp numpy
```

PuLP includes the CBC solver by default (no additional installation required).

## Quick Start

### Basic Usage

```python
from ml.optimization import ApplianceScheduler

# Create scheduler
scheduler = ApplianceScheduler()

# Add appliances
scheduler.add_appliance_preset("dishwasher", "evening")
scheduler.add_appliance_preset("ev_charger", "overnight")
scheduler.add_appliance_preset("water_heater", "anytime")

# Set time-of-use pricing
scheduler.set_time_of_use_prices(
    off_peak_rate=0.10,    # $/kWh
    on_peak_rate=0.35,     # $/kWh
    on_peak_hours=[(16, 21)]  # 4 PM - 9 PM
)

# Optimize
result = scheduler.optimize()

# View results
print(result.summary())
print(f"Savings: {result.savings_percent:.1f}%")
```

### Custom Appliances

```python
from ml.optimization import Appliance, ApplianceType, PriorityLevel

# Custom appliance with specific constraints
ev_charger = Appliance(
    name="Tesla Model 3",
    appliance_type=ApplianceType.EV_CHARGER,
    power_kw=7.2,           # Level 2 charger
    duration_hours=5.0,      # Time to full charge
    earliest_start=18,       # Home at 6 PM
    latest_end=7,            # Must be ready by 7 AM
    priority=PriorityLevel.HIGH,
    can_be_interrupted=True, # OK to pause charging
    min_run_chunk_hours=1.0, # At least 1 hour per charging session
)

scheduler.add_appliance(ev_charger)
```

### Price Profiles

```python
from ml.optimization import PriceProfile
import numpy as np

# Flat rate
flat = PriceProfile.create_flat_rate(0.15, num_slots=96)

# Time-of-use
tou = PriceProfile.create_time_of_use(
    off_peak_rate=0.10,
    on_peak_rate=0.35,
    on_peak_hours=[(14, 20)],  # 2 PM - 8 PM
    num_slots=96,
)

# Real-time pricing (from actual data)
prices = np.array([...])  # 96 values for each 15-min slot
realtime = PriceProfile(prices=prices, profile_type="realtime")

# Simulated real-time
simulated = PriceProfile.create_realtime(
    base_rate=0.12,
    volatility=0.3,
    seed=42,
)
```

### Visualization

```python
from ml.optimization import ScheduleVisualizer

visualizer = ScheduleVisualizer()

# Text-based schedule
print(visualizer.generate_text_schedule(result))

# Gantt chart (requires matplotlib)
visualizer.plot_schedule_gantt(result, price_profile, save_path="schedule.png")

# Power consumption profile
visualizer.plot_power_profile(result, price_profile, save_path="power.png")

# Interactive HTML (requires plotly)
fig = visualizer.plot_interactive_schedule(result, price_profile)
fig.write_html("schedule.html")
```

## Algorithm Details

### MILP Formulation

**Decision Variables:**
- `x[a,t]` - Binary variable indicating if appliance `a` is running at time slot `t`

**Objective Function:**
```
Minimize: sum over all (a,t) of price[t] * power[a] * slot_duration * x[a,t]
```

**Constraints:**

1. **Duration**: Each appliance runs for required slots
   ```
   sum over t of x[a,t] = required_slots[a]
   ```

2. **Time Window**: Only run within allowed hours
   ```
   x[a,t] = 0  for t outside valid window
   ```

3. **Continuity** (for continuous appliances):
   - Exactly one start position is chosen
   - Once started, runs for full duration without gaps

4. **Power Limit** (optional):
   ```
   sum over a of power[a] * x[a,t] <= max_power  for all t
   ```

### Solver Configuration

Default configuration optimized for household scenarios:

```python
OptimizationConfig(
    time_slots=96,              # 15-minute intervals
    slot_duration_hours=0.25,
    max_solve_time_seconds=5.0,
    mip_gap=0.01,               # 1% optimality gap
    solver_name="CBC",          # Bundled open-source solver
    verbose=False,
    presolve=True,
)
```

### Appliance Types

| Type | Default Power | Duration | Continuous | Interruptible |
|------|--------------|----------|------------|---------------|
| Dishwasher | 1.5 kW | 2.0 hr | Yes | No |
| Washing Machine | 2.0 kW | 1.5 hr | Yes | No |
| Dryer | 3.0 kW | 1.0 hr | Yes | No |
| EV Charger | 7.0 kW | 6.0 hr | No | Yes |
| Pool Pump | 1.2 kW | 4.0 hr | No | Yes |
| Water Heater | 4.0 kW | 2.0 hr | No | Yes |

### Time Windows

Pre-defined time window presets:

| Preset | Hours |
|--------|-------|
| `anytime` | 00:00 - 24:00 |
| `morning` | 05:00 - 12:00 |
| `afternoon` | 12:00 - 18:00 |
| `evening` | 17:00 - 23:00 |
| `overnight` | 21:00 - 07:00 |
| `daytime` | 06:00 - 22:00 |
| `off_peak` | 22:00 - 07:00 |

## Module Structure

```
ml/optimization/
    __init__.py           # Public API exports
    appliance_models.py   # Data models (Appliance, PriceProfile, etc.)
    constraints.py        # Constraint builder
    objective.py          # Objective function builder
    load_shifter.py       # Core MILP optimizer
    scheduler.py          # High-level scheduling API
    visualization.py      # Schedule visualization tools
```

## API Reference

### ApplianceScheduler

High-level API for scheduling optimization.

```python
class ApplianceScheduler:
    def add_appliance(self, appliance: Appliance) -> self
    def add_appliance_preset(self, type: str, window: str, **kwargs) -> self
    def add_dependency(self, predecessor: str, successor: str) -> self
    def add_mutual_exclusion(self, app1: str, app2: str) -> self
    def set_price_profile(self, prices: List[float]) -> self
    def set_flat_rate(self, rate: float) -> self
    def set_time_of_use_prices(self, off_peak, on_peak, peak_hours) -> self
    def set_realtime_prices(self, base_rate, volatility, seed) -> self
    def set_max_power(self, max_kw: float) -> self
    def optimize(self, minimize_peak=False, ...) -> ScheduleResult
    def get_schedule_summary(self) -> dict
    def export_to_json(self, filepath: str) -> None
```

### MILPOptimizer

Low-level optimizer with full control.

```python
class MILPOptimizer:
    def __init__(self, config: OptimizationConfig)
    def optimize(
        self,
        appliances: List[Appliance],
        price_profile: PriceProfile,
        minimize_peak: bool = False,
        minimize_interruptions: bool = False,
        balance_load: bool = False,
        dependencies: List[Tuple[str, str]] = None,
        mutual_exclusions: List[Tuple[str, str]] = None,
    ) -> ScheduleResult
    def get_problem_stats(self) -> dict
```

### ScheduleResult

Optimization result with schedules and metrics.

```python
@dataclass
class ScheduleResult:
    schedules: List[ApplianceSchedule]
    total_cost: float
    baseline_cost: float
    savings_amount: float
    savings_percent: float
    solve_time_seconds: float
    status: str  # "Optimal", "Feasible", "Infeasible"
    total_energy_kwh: float
    peak_power_kw: float
    solver_info: dict

    def is_optimal(self) -> bool
    def is_feasible(self) -> bool
    def get_power_profile(self, num_slots=96) -> np.ndarray
    def summary(self) -> str
```

## Testing

Run the standalone test suite:

```bash
python test_milp_optimization.py
```

Or with pytest (requires TensorFlow for other ml modules):

```bash
python -m pytest ml/tests/test_optimization.py -v
```

## Edge Cases Handled

- **Overnight windows**: Correctly handles time windows crossing midnight
- **Impossible constraints**: Returns infeasible status with clear error
- **Flat pricing**: Returns near-zero savings (no optimization opportunity)
- **Power oversubscription**: Schedules appliances to not exceed limits
- **Very short durations**: Handles single-slot appliances correctly
- **Full-day appliances**: Handles 24-hour operation correctly

## Integration with Price Forecasting

This optimizer is designed to work with the electricity price forecasting module:

```python
from ml import ElectricityPriceForecaster
from ml.optimization import ApplianceScheduler, PriceProfile

# Get price forecast
forecaster = ElectricityPriceForecaster.load("model.h5")
forecast = forecaster.predict(horizon=24)

# Convert to optimization format
# forecast.prices is hourly, expand to 15-minute slots
prices_15min = np.repeat(forecast.prices, 4)
profile = PriceProfile(prices=prices_15min, profile_type="forecast")

# Optimize schedule
scheduler = ApplianceScheduler()
# ... add appliances ...
result = scheduler.optimize()
```

## License

Part of the electricity-optimizer project.
