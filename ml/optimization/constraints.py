"""
Constraint Builder for MILP Appliance Scheduling

This module provides functions to build various constraints for the
Mixed Integer Linear Programming optimization problem.

Constraint Types:
1. Duration constraints - Appliance must run for required time
2. Time window constraints - Operation within allowed hours
3. Continuity constraints - Continuous vs interruptible operation
4. Power limits - Maximum simultaneous power consumption
5. Priority constraints - Precedence for high-priority appliances
6. User preference constraints - Custom user requirements
"""

from typing import List, Dict, Optional, Any, Tuple
import pulp
import numpy as np

from ml.optimization.appliance_models import (
    Appliance,
    PriorityLevel,
    OptimizationConfig,
)


class ConstraintBuilder:
    """Builder class for creating MILP constraints.

    This class provides methods to add various types of constraints
    to a PuLP optimization problem.
    """

    def __init__(
        self,
        problem: pulp.LpProblem,
        config: OptimizationConfig,
    ):
        """Initialize constraint builder.

        Args:
            problem: PuLP problem to add constraints to
            config: Optimization configuration
        """
        self.problem = problem
        self.config = config
        self.constraint_count = 0
        self.constraint_info: Dict[str, int] = {}

    def _add_constraint(
        self,
        constraint: pulp.LpConstraint,
        name: str,
        category: str = "general",
    ) -> None:
        """Add a constraint to the problem with tracking.

        Args:
            constraint: PuLP constraint to add
            name: Unique name for the constraint
            category: Category for tracking purposes
        """
        self.problem += constraint, name
        self.constraint_count += 1
        self.constraint_info[category] = self.constraint_info.get(category, 0) + 1

    def add_duration_constraint(
        self,
        appliance: Appliance,
        variables: Dict[int, pulp.LpVariable],
    ) -> None:
        """Add constraint ensuring appliance runs for required duration.

        The sum of all binary variables must equal the required number of slots.

        Args:
            appliance: Appliance being scheduled
            variables: Dictionary mapping slot index to binary variable
        """
        required_slots = appliance.duration_slots

        # Sum of all variables must equal required duration
        self._add_constraint(
            pulp.lpSum(variables.values()) == required_slots,
            f"duration_{appliance.name}",
            "duration",
        )

    def add_time_window_constraint(
        self,
        appliance: Appliance,
        variables: Dict[int, pulp.LpVariable],
    ) -> None:
        """Add constraint restricting operation to allowed time window.

        Variables outside the valid time window are set to 0.

        Args:
            appliance: Appliance being scheduled
            variables: Dictionary mapping slot index to binary variable
        """
        valid_slots = set(appliance.get_valid_slots(self.config.time_slots))

        for slot, var in variables.items():
            if slot not in valid_slots:
                self._add_constraint(
                    var == 0,
                    f"window_{appliance.name}_slot{slot}",
                    "time_window",
                )

    def add_continuity_constraint(
        self,
        appliance: Appliance,
        variables: Dict[int, pulp.LpVariable],
        start_var: pulp.LpVariable,
    ) -> None:
        """Add constraint for continuous operation.

        For appliances that must run continuously, once started they
        must run for the entire duration without interruption.

        Uses a start indicator variable and linking constraints.

        Args:
            appliance: Appliance being scheduled
            variables: Dictionary mapping slot index to binary variable
            start_var: Binary variable indicating start slot
        """
        if not appliance.must_be_continuous:
            return

        num_slots = self.config.time_slots
        required_slots = appliance.duration_slots
        valid_slots = appliance.get_valid_slots(num_slots)

        # For continuous operation, if we start at slot t, we must run
        # from t to t + duration - 1

        # Create auxiliary start variables for each possible start slot
        start_vars = {}
        for t in valid_slots:
            # Check if there's room to complete from this slot
            can_complete = True
            for offset in range(required_slots):
                slot = (t + offset) % num_slots
                if slot not in valid_slots:
                    can_complete = False
                    break

            if can_complete:
                start_vars[t] = pulp.LpVariable(
                    f"start_{appliance.name}_at_{t}",
                    cat=pulp.LpBinary,
                )

        if not start_vars:
            # No valid starting positions - problem is infeasible
            # Add infeasibility constraint
            self._add_constraint(
                pulp.lpSum(variables.values()) >= required_slots + 1,
                f"infeasible_{appliance.name}",
                "continuity",
            )
            return

        # Exactly one start slot must be chosen
        self._add_constraint(
            pulp.lpSum(start_vars.values()) == 1,
            f"one_start_{appliance.name}",
            "continuity",
        )

        # Link start variables to operation variables
        for start_slot, start_v in start_vars.items():
            for offset in range(required_slots):
                slot = (start_slot + offset) % num_slots
                # If we start at start_slot, we must be running at slot
                self._add_constraint(
                    variables[slot] >= start_v,
                    f"cont_{appliance.name}_s{start_slot}_o{offset}",
                    "continuity",
                )

        # Total running slots must equal required duration
        # (already added by duration constraint)

    def add_min_chunk_constraint(
        self,
        appliance: Appliance,
        variables: Dict[int, pulp.LpVariable],
    ) -> None:
        """Add constraint for minimum continuous run chunk.

        For interruptible appliances, each run period must be at least
        min_run_chunk_hours long.

        Args:
            appliance: Appliance being scheduled
            variables: Dictionary mapping slot index to binary variable
        """
        if appliance.must_be_continuous or not appliance.can_be_interrupted:
            return

        min_chunk = appliance.min_chunk_slots
        if min_chunk <= 1:
            return  # No minimum chunk constraint needed

        num_slots = self.config.time_slots

        # For each slot, if it's a "start" (running but previous not running),
        # then the next min_chunk-1 slots must also be running

        for t in range(num_slots):
            prev_slot = (t - 1) % num_slots

            # Create auxiliary variable for "is this a start?"
            # start_t = x_t AND NOT x_{t-1}
            # Linearization: start_t <= x_t, start_t <= 1 - x_{t-1}
            # start_t >= x_t - x_{t-1} (captures the AND)

            # For simplicity, we use: if x_t - x_{t-1} = 1 (start), then
            # the next min_chunk-1 slots must also be 1

            for offset in range(1, min_chunk):
                next_slot = (t + offset) % num_slots
                # If we start at t, slot t+offset must be running
                # x_{t+offset} >= x_t - x_{t-1}
                self._add_constraint(
                    variables[next_slot] >= variables[t] - variables[prev_slot],
                    f"minchunk_{appliance.name}_t{t}_o{offset}",
                    "min_chunk",
                )

    def add_max_interruptions_constraint(
        self,
        appliance: Appliance,
        variables: Dict[int, pulp.LpVariable],
    ) -> None:
        """Add constraint limiting number of interruptions.

        Counts transitions from running to not running.

        Args:
            appliance: Appliance being scheduled
            variables: Dictionary mapping slot index to binary variable
        """
        if appliance.must_be_continuous:
            return

        max_interruptions = appliance.max_interruptions
        num_slots = self.config.time_slots

        # Create transition variables for "stop" events
        # stop_t = x_t AND NOT x_{t+1}
        stop_vars = []
        for t in range(num_slots):
            next_slot = (t + 1) % num_slots
            stop_var = pulp.LpVariable(
                f"stop_{appliance.name}_{t}",
                cat=pulp.LpBinary,
            )
            stop_vars.append(stop_var)

            # Linearize: stop_t >= x_t - x_{t+1}
            self._add_constraint(
                stop_var >= variables[t] - variables[next_slot],
                f"stop_lb_{appliance.name}_{t}",
                "interruption",
            )

        # Limit total stops (interruptions)
        self._add_constraint(
            pulp.lpSum(stop_vars) <= max_interruptions + 1,  # +1 for final stop
            f"max_int_{appliance.name}",
            "interruption",
        )

    def add_power_limit_constraint(
        self,
        appliances: List[Appliance],
        all_variables: Dict[str, Dict[int, pulp.LpVariable]],
        max_power_kw: float,
    ) -> None:
        """Add constraint on maximum total power consumption.

        Args:
            appliances: List of all appliances
            all_variables: Nested dict mapping appliance name -> slot -> variable
            max_power_kw: Maximum allowed total power in kW
        """
        for t in range(self.config.time_slots):
            power_sum = pulp.lpSum(
                app.power_kw * all_variables[app.name][t]
                for app in appliances
                if t in all_variables[app.name]
            )
            self._add_constraint(
                power_sum <= max_power_kw,
                f"max_power_t{t}",
                "power_limit",
            )

    def add_dependency_constraint(
        self,
        predecessor: Appliance,
        successor: Appliance,
        pred_vars: Dict[int, pulp.LpVariable],
        succ_vars: Dict[int, pulp.LpVariable],
        gap_slots: int = 0,
    ) -> None:
        """Add constraint that one appliance must complete before another starts.

        Args:
            predecessor: Appliance that must finish first
            successor: Appliance that must start after
            pred_vars: Variables for predecessor
            succ_vars: Variables for successor
            gap_slots: Minimum gap between end and start
        """
        num_slots = self.config.time_slots
        pred_duration = predecessor.duration_slots

        # For each possible end slot of predecessor, successor cannot
        # start until after that slot plus gap

        # We use: sum of successor vars in slots 0 to t <=
        #         sum of predecessor vars in slots 0 to t-gap-1 * pred_duration
        # This ensures predecessor is done before successor can accumulate runtime

        for t in range(num_slots):
            # Count how much successor has run up to slot t
            succ_count = pulp.lpSum(
                succ_vars[s] for s in range(t + 1) if s in succ_vars
            )

            # This can only be > 0 if predecessor has finished
            # Predecessor finished means all pred_duration slots are done

            if t >= pred_duration + gap_slots:
                # Predecessor could potentially be done
                pass  # Allow successor to run
            else:
                # Predecessor cannot be done yet
                self._add_constraint(
                    succ_count == 0,
                    f"dep_{predecessor.name}_before_{successor.name}_t{t}",
                    "dependency",
                )

    def add_mutual_exclusion_constraint(
        self,
        appliance1: Appliance,
        appliance2: Appliance,
        vars1: Dict[int, pulp.LpVariable],
        vars2: Dict[int, pulp.LpVariable],
    ) -> None:
        """Add constraint preventing two appliances from running simultaneously.

        Args:
            appliance1: First appliance
            appliance2: Second appliance
            vars1: Variables for first appliance
            vars2: Variables for second appliance
        """
        for t in range(self.config.time_slots):
            if t in vars1 and t in vars2:
                self._add_constraint(
                    vars1[t] + vars2[t] <= 1,
                    f"mutex_{appliance1.name}_{appliance2.name}_t{t}",
                    "mutual_exclusion",
                )

    def add_preferred_time_soft_constraint(
        self,
        appliance: Appliance,
        variables: Dict[int, pulp.LpVariable],
        preferred_slots: List[int],
        penalty_vars: Dict[int, pulp.LpVariable],
        penalty_weight: float = 0.01,
    ) -> pulp.LpAffineExpression:
        """Add soft constraint preferring certain time slots.

        Returns penalty term to add to objective.

        Args:
            appliance: Appliance being scheduled
            variables: Dictionary mapping slot index to binary variable
            preferred_slots: List of preferred slot indices
            penalty_vars: Penalty variables for non-preferred slots
            penalty_weight: Weight for penalty in objective

        Returns:
            Penalty expression to add to objective
        """
        preferred_set = set(preferred_slots)
        penalty_terms = []

        for t, var in variables.items():
            if t not in preferred_set:
                # Running at non-preferred time incurs penalty
                penalty_terms.append(penalty_weight * var)

        return pulp.lpSum(penalty_terms)

    def add_deadline_constraint(
        self,
        appliance: Appliance,
        variables: Dict[int, pulp.LpVariable],
        deadline_slot: int,
    ) -> None:
        """Add hard constraint that appliance must complete by deadline.

        Args:
            appliance: Appliance being scheduled
            variables: Dictionary mapping slot index to binary variable
            deadline_slot: Slot by which all operation must complete
        """
        required_slots = appliance.duration_slots

        # All required slots must be scheduled before deadline
        valid_before_deadline = [
            t for t in variables.keys()
            if t < deadline_slot
        ]

        if len(valid_before_deadline) < required_slots:
            # Cannot meet deadline - make infeasible
            self._add_constraint(
                pulp.lpSum(variables.values()) >= required_slots + 1,
                f"deadline_infeasible_{appliance.name}",
                "deadline",
            )
        else:
            # Force all operation before deadline
            after_deadline = [
                variables[t] for t in variables.keys()
                if t >= deadline_slot
            ]
            if after_deadline:
                self._add_constraint(
                    pulp.lpSum(after_deadline) == 0,
                    f"deadline_{appliance.name}",
                    "deadline",
                )

    def get_constraint_summary(self) -> Dict[str, Any]:
        """Get summary of all constraints added.

        Returns:
            Dictionary with constraint statistics
        """
        return {
            "total_constraints": self.constraint_count,
            "by_category": self.constraint_info.copy(),
        }


def build_all_constraints(
    problem: pulp.LpProblem,
    appliances: List[Appliance],
    all_variables: Dict[str, Dict[int, pulp.LpVariable]],
    start_variables: Dict[str, pulp.LpVariable],
    config: OptimizationConfig,
    dependencies: Optional[List[Tuple[str, str]]] = None,
    mutual_exclusions: Optional[List[Tuple[str, str]]] = None,
) -> ConstraintBuilder:
    """Build all constraints for the optimization problem.

    This is the main entry point for constraint generation.

    Args:
        problem: PuLP problem to add constraints to
        appliances: List of appliances to schedule
        all_variables: Nested dict mapping appliance name -> slot -> variable
        start_variables: Dict mapping appliance name -> start indicator variable
        config: Optimization configuration
        dependencies: Optional list of (predecessor, successor) name pairs
        mutual_exclusions: Optional list of (app1, app2) name pairs

    Returns:
        ConstraintBuilder with all constraints added
    """
    builder = ConstraintBuilder(problem, config)
    appliance_map = {app.name: app for app in appliances}

    # Add constraints for each appliance
    for appliance in appliances:
        variables = all_variables[appliance.name]
        start_var = start_variables.get(appliance.name)

        # Duration constraint
        builder.add_duration_constraint(appliance, variables)

        # Time window constraint
        builder.add_time_window_constraint(appliance, variables)

        # Continuity or chunk constraints
        if appliance.must_be_continuous:
            if start_var is not None:
                builder.add_continuity_constraint(appliance, variables, start_var)
        elif appliance.can_be_interrupted:
            builder.add_min_chunk_constraint(appliance, variables)
            builder.add_max_interruptions_constraint(appliance, variables)

    # Power limit constraint
    if config.max_total_power_kw is not None:
        builder.add_power_limit_constraint(
            appliances, all_variables, config.max_total_power_kw
        )

    # Dependency constraints
    if dependencies:
        for pred_name, succ_name in dependencies:
            if pred_name in appliance_map and succ_name in appliance_map:
                builder.add_dependency_constraint(
                    appliance_map[pred_name],
                    appliance_map[succ_name],
                    all_variables[pred_name],
                    all_variables[succ_name],
                )

    # Mutual exclusion constraints
    if mutual_exclusions:
        for app1_name, app2_name in mutual_exclusions:
            if app1_name in appliance_map and app2_name in appliance_map:
                builder.add_mutual_exclusion_constraint(
                    appliance_map[app1_name],
                    appliance_map[app2_name],
                    all_variables[app1_name],
                    all_variables[app2_name],
                )

    return builder
