"""
Objective Function for MILP Appliance Scheduling

This module provides functions to build the objective function for the
Mixed Integer Linear Programming optimization problem.

The primary objective is to minimize total electricity cost, with optional
secondary objectives for:
- Peak power reduction
- User preference satisfaction
- Schedule stability (minimize changes from baseline)
"""

from typing import List, Dict, Optional, Tuple
import pulp
import numpy as np

from ml.optimization.appliance_models import (
    Appliance,
    PriceProfile,
    PriorityLevel,
    OptimizationConfig,
)


class ObjectiveBuilder:
    """Builder class for creating MILP objective functions.

    Supports multiple objective components that can be weighted
    and combined into a single objective.
    """

    def __init__(
        self,
        problem: pulp.LpProblem,
        config: OptimizationConfig,
    ):
        """Initialize objective builder.

        Args:
            problem: PuLP problem to set objective on
            config: Optimization configuration
        """
        self.problem = problem
        self.config = config
        self.objective_terms: List[Tuple[str, pulp.LpAffineExpression, float]] = []

    def add_cost_objective(
        self,
        appliances: List[Appliance],
        all_variables: Dict[str, Dict[int, pulp.LpVariable]],
        price_profile: PriceProfile,
        weight: float = 1.0,
    ) -> pulp.LpAffineExpression:
        """Add electricity cost minimization objective.

        Cost = sum over appliances and slots of:
            price[t] * power[a] * slot_duration * x[a,t]

        Args:
            appliances: List of appliances to schedule
            all_variables: Nested dict mapping appliance name -> slot -> variable
            price_profile: Electricity price profile
            weight: Weight for this objective component

        Returns:
            Cost expression
        """
        cost_terms = []
        slot_duration = self.config.slot_duration_hours

        for appliance in appliances:
            variables = all_variables[appliance.name]
            power = appliance.power_kw

            for slot, var in variables.items():
                price = price_profile.get_slot_price(slot)
                energy_cost = price * power * slot_duration
                cost_terms.append(energy_cost * var)

        cost_expr = pulp.lpSum(cost_terms)
        self.objective_terms.append(("electricity_cost", cost_expr, weight))
        return cost_expr

    def add_peak_power_objective(
        self,
        appliances: List[Appliance],
        all_variables: Dict[str, Dict[int, pulp.LpVariable]],
        weight: float = 0.1,
    ) -> Tuple[pulp.LpVariable, pulp.LpAffineExpression]:
        """Add peak power minimization objective.

        Uses auxiliary variable to track maximum power across all slots.

        Args:
            appliances: List of appliances to schedule
            all_variables: Nested dict mapping appliance name -> slot -> variable
            weight: Weight for this objective component

        Returns:
            Tuple of (peak variable, peak expression)
        """
        # Create variable for peak power
        max_possible = sum(app.power_kw for app in appliances)
        peak_var = pulp.LpVariable(
            "peak_power",
            lowBound=0,
            upBound=max_possible,
            cat=pulp.LpContinuous,
        )

        # Add constraints: peak_var >= power at each slot
        for t in range(self.config.time_slots):
            power_at_t = pulp.lpSum(
                app.power_kw * all_variables[app.name].get(t, 0)
                for app in appliances
            )
            self.problem += peak_var >= power_at_t, f"peak_power_t{t}"

        peak_expr = peak_var
        self.objective_terms.append(("peak_power", peak_expr, weight))
        return peak_var, peak_expr

    def add_preference_penalty(
        self,
        appliances: List[Appliance],
        all_variables: Dict[str, Dict[int, pulp.LpVariable]],
        weight: float = 0.01,
    ) -> pulp.LpAffineExpression:
        """Add penalty for not meeting user preferences.

        Higher priority appliances get scheduling preference during
        cheaper periods.

        Args:
            appliances: List of appliances to schedule
            all_variables: Nested dict mapping appliance name -> slot -> variable
            weight: Weight for this objective component

        Returns:
            Penalty expression
        """
        penalty_terms = []

        # Sort appliances by priority (higher priority = lower penalty weight)
        priority_weights = {
            PriorityLevel.CRITICAL: 0.1,
            PriorityLevel.HIGH: 0.3,
            PriorityLevel.MEDIUM: 0.6,
            PriorityLevel.LOW: 1.0,
        }

        for appliance in appliances:
            variables = all_variables[appliance.name]
            valid_slots = set(appliance.get_valid_slots(self.config.time_slots))

            # Penalty for running outside of preferred window
            # (but within allowed window)
            pref_weight = priority_weights.get(appliance.priority, 0.6)

            # Add small penalty for later slots to encourage early completion
            # for high-priority appliances
            for slot, var in variables.items():
                if slot in valid_slots:
                    # Small time-based penalty (earlier is better for high priority)
                    time_factor = slot / self.config.time_slots
                    penalty_terms.append(
                        weight * pref_weight * time_factor * var * 0.001
                    )

        penalty_expr = pulp.lpSum(penalty_terms) if penalty_terms else 0
        if penalty_terms:
            self.objective_terms.append(("preference_penalty", penalty_expr, 1.0))
        return penalty_expr

    def add_interruption_penalty(
        self,
        appliances: List[Appliance],
        all_variables: Dict[str, Dict[int, pulp.LpVariable]],
        weight: float = 0.05,
    ) -> pulp.LpAffineExpression:
        """Add penalty for interrupting appliance operation.

        Encourages continuous operation even for interruptible appliances.

        Args:
            appliances: List of appliances to schedule
            all_variables: Nested dict mapping appliance name -> slot -> variable
            weight: Weight for this objective component

        Returns:
            Penalty expression
        """
        penalty_terms = []

        for appliance in appliances:
            if appliance.must_be_continuous:
                continue  # Already enforced by constraints

            variables = all_variables[appliance.name]

            # Penalty for transitions (running -> not running)
            for t in range(self.config.time_slots - 1):
                if t in variables and (t + 1) in variables:
                    # Transition happens when x[t] = 1 and x[t+1] = 0
                    # We can approximate this with x[t] - x[t+1]
                    # but this gives negative values when starting
                    # Instead, use absolute difference / 2

                    # For MILP, we can't directly use abs()
                    # Use auxiliary variables or just penalize any change
                    diff_var = pulp.LpVariable(
                        f"int_pen_{appliance.name}_{t}",
                        lowBound=0,
                        cat=pulp.LpContinuous,
                    )
                    self.problem += diff_var >= variables[t] - variables[t + 1]
                    penalty_terms.append(weight * diff_var)

        penalty_expr = pulp.lpSum(penalty_terms) if penalty_terms else 0
        if penalty_terms:
            self.objective_terms.append(("interruption_penalty", penalty_expr, 1.0))
        return penalty_expr

    def add_load_balancing_objective(
        self,
        appliances: List[Appliance],
        all_variables: Dict[str, Dict[int, pulp.LpVariable]],
        weight: float = 0.01,
    ) -> pulp.LpAffineExpression:
        """Add objective to balance load across time slots.

        Penalizes high variance in power consumption.

        Args:
            appliances: List of appliances to schedule
            all_variables: Nested dict mapping appliance name -> slot -> variable
            weight: Weight for this objective component

        Returns:
            Load balancing expression
        """
        # Calculate total energy
        total_energy = sum(app.energy_kwh for app in appliances)
        avg_power = total_energy / (self.config.time_slots * self.config.slot_duration_hours)

        # Penalize deviation from average
        deviation_terms = []
        for t in range(self.config.time_slots):
            power_at_t = pulp.lpSum(
                app.power_kw * all_variables[app.name].get(t, 0)
                for app in appliances
            )

            # Use auxiliary variable for absolute deviation
            dev_var = pulp.LpVariable(
                f"dev_{t}",
                lowBound=0,
                cat=pulp.LpContinuous,
            )
            self.problem += dev_var >= power_at_t - avg_power
            self.problem += dev_var >= avg_power - power_at_t
            deviation_terms.append(dev_var)

        balance_expr = weight * pulp.lpSum(deviation_terms)
        self.objective_terms.append(("load_balance", balance_expr, 1.0))
        return balance_expr

    def build_objective(self) -> pulp.LpAffineExpression:
        """Combine all objective terms and set on problem.

        Returns:
            Combined objective expression
        """
        if not self.objective_terms:
            raise ValueError("No objective terms have been added")

        total_objective = pulp.lpSum(
            weight * expr for name, expr, weight in self.objective_terms
        )

        self.problem += total_objective, "total_objective"
        return total_objective

    def get_objective_breakdown(
        self,
        solution_values: Dict[str, float],
    ) -> Dict[str, float]:
        """Get breakdown of objective value by component.

        Args:
            solution_values: Dictionary of variable values from solution

        Returns:
            Dictionary mapping component name to its contribution
        """
        breakdown = {}
        for name, expr, weight in self.objective_terms:
            try:
                value = pulp.value(expr)
                breakdown[name] = value * weight if value is not None else 0.0
            except Exception:
                breakdown[name] = 0.0
        return breakdown


def build_objective(
    problem: pulp.LpProblem,
    appliances: List[Appliance],
    all_variables: Dict[str, Dict[int, pulp.LpVariable]],
    price_profile: PriceProfile,
    config: OptimizationConfig,
    minimize_peak: bool = False,
    minimize_interruptions: bool = False,
    balance_load: bool = False,
    peak_weight: float = 0.1,
    interruption_weight: float = 0.05,
    balance_weight: float = 0.01,
) -> ObjectiveBuilder:
    """Build complete objective function for the optimization problem.

    This is the main entry point for objective generation.

    Args:
        problem: PuLP problem to set objective on
        appliances: List of appliances to schedule
        all_variables: Nested dict mapping appliance name -> slot -> variable
        price_profile: Electricity price profile
        config: Optimization configuration
        minimize_peak: Whether to include peak power minimization
        minimize_interruptions: Whether to penalize interruptions
        balance_load: Whether to balance load across time
        peak_weight: Weight for peak power objective
        interruption_weight: Weight for interruption penalty
        balance_weight: Weight for load balancing

    Returns:
        ObjectiveBuilder with all objectives added
    """
    builder = ObjectiveBuilder(problem, config)

    # Primary objective: minimize cost
    builder.add_cost_objective(appliances, all_variables, price_profile, weight=1.0)

    # Optional secondary objectives
    if minimize_peak:
        builder.add_peak_power_objective(appliances, all_variables, weight=peak_weight)

    if minimize_interruptions:
        builder.add_interruption_penalty(
            appliances, all_variables, weight=interruption_weight
        )

    if balance_load:
        builder.add_load_balancing_objective(
            appliances, all_variables, weight=balance_weight
        )

    # Always add small preference penalty
    builder.add_preference_penalty(appliances, all_variables, weight=0.001)

    # Build combined objective
    builder.build_objective()

    return builder


def calculate_baseline_cost(
    appliances: List[Appliance],
    price_profile: PriceProfile,
    config: OptimizationConfig,
) -> float:
    """Calculate baseline cost if appliances run immediately.

    Baseline assumes each appliance starts at its earliest allowed time.

    Args:
        appliances: List of appliances to schedule
        price_profile: Electricity price profile
        config: Optimization configuration

    Returns:
        Total baseline cost
    """
    total_cost = 0.0
    slot_duration = config.slot_duration_hours

    for appliance in appliances:
        # Start at earliest possible slot
        start_slot = appliance.earliest_start * 4
        duration_slots = appliance.duration_slots

        for offset in range(duration_slots):
            slot = (start_slot + offset) % config.time_slots
            price = price_profile.get_slot_price(slot)
            energy = appliance.power_kw * slot_duration
            total_cost += price * energy

    return total_cost


def calculate_optimal_cost(
    appliances: List[Appliance],
    price_profile: PriceProfile,
    config: OptimizationConfig,
) -> float:
    """Calculate theoretical optimal cost (lower bound).

    This ignores constraints and assumes each appliance can run
    during its absolute cheapest slots.

    Args:
        appliances: List of appliances to schedule
        price_profile: Electricity price profile
        config: Optimization configuration

    Returns:
        Theoretical minimum cost (may not be achievable)
    """
    total_cost = 0.0
    slot_duration = config.slot_duration_hours

    for appliance in appliances:
        # Get cheapest slots within valid window
        valid_slots = appliance.get_valid_slots(config.time_slots)
        slot_prices = [
            (slot, price_profile.get_slot_price(slot))
            for slot in valid_slots
        ]
        slot_prices.sort(key=lambda x: x[1])

        # Take cheapest slots for required duration
        duration_slots = appliance.duration_slots
        cheapest_slots = slot_prices[:duration_slots]

        for slot, price in cheapest_slots:
            energy = appliance.power_kw * slot_duration
            total_cost += price * energy

    return total_cost
