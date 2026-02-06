"""
MILP Optimizer for Appliance Load Shifting

This module implements the core Mixed Integer Linear Programming (MILP)
optimizer for scheduling household appliances to minimize electricity costs.

Algorithm Overview:
1. Create binary decision variables x[a,t] for each appliance a and slot t
2. Add constraints for duration, time windows, continuity, power limits
3. Set objective to minimize total electricity cost
4. Solve using CBC (default) or other MIP solvers
5. Extract and validate solution

The optimizer uses PuLP as the modeling interface, which supports multiple
backend solvers including CBC (open source, bundled with PuLP).
"""

import time
from typing import List, Dict, Optional, Tuple, Any
import pulp
import numpy as np

from ml.optimization.appliance_models import (
    Appliance,
    ApplianceSchedule,
    ScheduleResult,
    PriceProfile,
    OptimizationConfig,
)
from ml.optimization.constraints import build_all_constraints, ConstraintBuilder
from ml.optimization.objective import (
    build_objective,
    calculate_baseline_cost,
    ObjectiveBuilder,
)


class MILPOptimizer:
    """Mixed Integer Linear Programming optimizer for appliance scheduling.

    This class handles the complete optimization workflow:
    1. Problem formulation (variables, constraints, objective)
    2. Solving using PuLP/CBC
    3. Solution extraction and validation
    4. Result packaging

    Attributes:
        config: Optimization configuration
        problem: PuLP optimization problem
        variables: Dictionary of decision variables
        appliances: List of appliances to schedule
        price_profile: Electricity price profile
    """

    def __init__(self, config: Optional[OptimizationConfig] = None):
        """Initialize the optimizer.

        Args:
            config: Optimization configuration (uses defaults if not provided)
        """
        self.config = config or OptimizationConfig()
        self.problem: Optional[pulp.LpProblem] = None
        self.variables: Dict[str, Dict[int, pulp.LpVariable]] = {}
        self.start_variables: Dict[str, pulp.LpVariable] = {}
        self.appliances: List[Appliance] = []
        self.price_profile: Optional[PriceProfile] = None
        self.constraint_builder: Optional[ConstraintBuilder] = None
        self.objective_builder: Optional[ObjectiveBuilder] = None
        self._solve_time: float = 0.0
        self._solver_status: str = "not_solved"

    def _create_variables(self) -> None:
        """Create decision variables for all appliances.

        Creates binary variable x[a,t] for each appliance a and time slot t,
        indicating whether appliance a is running during slot t.
        """
        self.variables = {}
        self.start_variables = {}

        for appliance in self.appliances:
            app_vars = {}
            valid_slots = set(appliance.get_valid_slots(self.config.time_slots))

            for t in range(self.config.time_slots):
                # Create variable even for invalid slots (will be constrained to 0)
                var = pulp.LpVariable(
                    f"x_{appliance.name}_{t}",
                    cat=pulp.LpBinary,
                )
                app_vars[t] = var

            self.variables[appliance.name] = app_vars

            # Create start indicator variable for continuous appliances
            if appliance.must_be_continuous:
                start_var = pulp.LpVariable(
                    f"start_{appliance.name}",
                    cat=pulp.LpBinary,
                )
                self.start_variables[appliance.name] = start_var

    def _build_problem(
        self,
        minimize_peak: bool = False,
        minimize_interruptions: bool = False,
        balance_load: bool = False,
        dependencies: Optional[List[Tuple[str, str]]] = None,
        mutual_exclusions: Optional[List[Tuple[str, str]]] = None,
    ) -> None:
        """Build the complete optimization problem.

        Args:
            minimize_peak: Include peak power minimization objective
            minimize_interruptions: Penalize operation interruptions
            balance_load: Balance load across time slots
            dependencies: List of (predecessor, successor) appliance name pairs
            mutual_exclusions: List of mutually exclusive appliance name pairs
        """
        # Create new problem
        self.problem = pulp.LpProblem(
            "Appliance_Scheduling",
            pulp.LpMinimize,
        )

        # Create decision variables
        self._create_variables()

        # Build constraints
        self.constraint_builder = build_all_constraints(
            problem=self.problem,
            appliances=self.appliances,
            all_variables=self.variables,
            start_variables=self.start_variables,
            config=self.config,
            dependencies=dependencies,
            mutual_exclusions=mutual_exclusions,
        )

        # Build objective
        self.objective_builder = build_objective(
            problem=self.problem,
            appliances=self.appliances,
            all_variables=self.variables,
            price_profile=self.price_profile,
            config=self.config,
            minimize_peak=minimize_peak,
            minimize_interruptions=minimize_interruptions,
            balance_load=balance_load,
        )

    def _get_solver(self) -> pulp.apis.LpSolver:
        """Get the appropriate solver based on configuration.

        Returns:
            PuLP solver instance
        """
        solver_name = self.config.solver_name.upper()

        if solver_name == "CBC":
            return pulp.PULP_CBC_CMD(
                timeLimit=self.config.max_solve_time_seconds,
                gapRel=self.config.mip_gap,
                msg=1 if self.config.verbose else 0,
                presolve=self.config.presolve,
            )
        elif solver_name == "GLPK":
            return pulp.GLPK_CMD(
                timeLimit=self.config.max_solve_time_seconds,
                msg=1 if self.config.verbose else 0,
            )
        else:
            # Default to CBC
            return pulp.PULP_CBC_CMD(
                timeLimit=self.config.max_solve_time_seconds,
                gapRel=self.config.mip_gap,
                msg=1 if self.config.verbose else 0,
            )

    def _solve(self) -> str:
        """Solve the optimization problem.

        Returns:
            Solver status string
        """
        if self.problem is None:
            raise RuntimeError("Problem not built. Call _build_problem first.")

        solver = self._get_solver()
        start_time = time.time()

        try:
            self.problem.solve(solver)
        except Exception as e:
            self._solve_time = time.time() - start_time
            self._solver_status = f"error: {str(e)}"
            return self._solver_status

        self._solve_time = time.time() - start_time
        self._solver_status = pulp.LpStatus[self.problem.status]

        return self._solver_status

    def _extract_solution(self) -> List[ApplianceSchedule]:
        """Extract appliance schedules from solved problem.

        Returns:
            List of ApplianceSchedule objects
        """
        schedules = []
        slot_duration = self.config.slot_duration_hours

        for appliance in self.appliances:
            app_vars = self.variables[appliance.name]

            # Extract scheduled slots
            scheduled_slots = []
            for t, var in app_vars.items():
                if var.value() is not None and var.value() > 0.5:
                    scheduled_slots.append(t)

            # Calculate cost
            cost = 0.0
            for slot in scheduled_slots:
                price = self.price_profile.get_slot_price(slot)
                energy = appliance.power_kw * slot_duration
                cost += price * energy

            # Calculate energy
            energy_kwh = appliance.power_kw * len(scheduled_slots) * slot_duration

            schedule = ApplianceSchedule(
                appliance=appliance,
                scheduled_slots=sorted(scheduled_slots),
                cost=cost,
                energy_kwh=energy_kwh,
            )
            schedules.append(schedule)

        return schedules

    def _validate_solution(self, schedules: List[ApplianceSchedule]) -> List[str]:
        """Validate that solution satisfies all constraints.

        Args:
            schedules: List of appliance schedules

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        for schedule in schedules:
            appliance = schedule.appliance
            slots = schedule.scheduled_slots

            # Check duration
            expected_slots = appliance.duration_slots
            if len(slots) != expected_slots:
                errors.append(
                    f"{appliance.name}: Expected {expected_slots} slots, "
                    f"got {len(slots)}"
                )

            # Check time window
            valid_slots = set(appliance.get_valid_slots(self.config.time_slots))
            invalid_slots = [s for s in slots if s not in valid_slots]
            if invalid_slots:
                errors.append(
                    f"{appliance.name}: Running in invalid slots {invalid_slots}"
                )

            # Check continuity
            if appliance.must_be_continuous and len(slots) > 1:
                sorted_slots = sorted(slots)
                for i in range(len(sorted_slots) - 1):
                    if sorted_slots[i + 1] - sorted_slots[i] != 1:
                        # Allow wrap-around
                        if not (
                            sorted_slots[i] == self.config.time_slots - 1
                            and sorted_slots[i + 1] == 0
                        ):
                            errors.append(
                                f"{appliance.name}: Non-continuous operation "
                                f"detected at slot {sorted_slots[i]}"
                            )
                            break

        # Check power limits
        if self.config.max_total_power_kw is not None:
            power_per_slot = np.zeros(self.config.time_slots)
            for schedule in schedules:
                for slot in schedule.scheduled_slots:
                    power_per_slot[slot] += schedule.appliance.power_kw

            max_power = np.max(power_per_slot)
            if max_power > self.config.max_total_power_kw + 0.01:
                errors.append(
                    f"Power limit exceeded: {max_power:.2f} kW > "
                    f"{self.config.max_total_power_kw:.2f} kW"
                )

        return errors

    def _calculate_results(
        self,
        schedules: List[ApplianceSchedule],
    ) -> ScheduleResult:
        """Calculate final results and statistics.

        Args:
            schedules: List of appliance schedules

        Returns:
            Complete ScheduleResult object
        """
        # Calculate total cost
        total_cost = sum(s.cost for s in schedules)

        # Calculate baseline cost
        baseline_cost = calculate_baseline_cost(
            self.appliances, self.price_profile, self.config
        )

        # Calculate savings
        savings_amount = baseline_cost - total_cost
        savings_percent = (
            (savings_amount / baseline_cost * 100) if baseline_cost > 0 else 0.0
        )

        # Calculate energy and power
        total_energy = sum(s.energy_kwh for s in schedules)

        power_profile = np.zeros(self.config.time_slots)
        for schedule in schedules:
            for slot in schedule.scheduled_slots:
                power_profile[slot] += schedule.appliance.power_kw
        peak_power = float(np.max(power_profile))

        # Collect solver info
        solver_info = {
            "variables": self.problem.numVariables() if self.problem else 0,
            "constraints": self.problem.numConstraints() if self.problem else 0,
            "solver": self.config.solver_name,
            "mip_gap": self.config.mip_gap,
        }

        if self.constraint_builder:
            solver_info["constraint_breakdown"] = (
                self.constraint_builder.get_constraint_summary()
            )

        return ScheduleResult(
            schedules=schedules,
            total_cost=total_cost,
            baseline_cost=baseline_cost,
            savings_amount=savings_amount,
            savings_percent=savings_percent,
            solve_time_seconds=self._solve_time,
            status=self._solver_status,
            total_energy_kwh=total_energy,
            peak_power_kw=peak_power,
            solver_info=solver_info,
        )

    def optimize(
        self,
        appliances: List[Appliance],
        price_profile: PriceProfile,
        minimize_peak: bool = False,
        minimize_interruptions: bool = False,
        balance_load: bool = False,
        dependencies: Optional[List[Tuple[str, str]]] = None,
        mutual_exclusions: Optional[List[Tuple[str, str]]] = None,
    ) -> ScheduleResult:
        """Run the complete optimization workflow.

        This is the main entry point for optimization.

        Args:
            appliances: List of appliances to schedule
            price_profile: Electricity price profile
            minimize_peak: Include peak power minimization objective
            minimize_interruptions: Penalize operation interruptions
            balance_load: Balance load across time slots
            dependencies: List of (predecessor, successor) appliance name pairs
            mutual_exclusions: List of mutually exclusive appliance name pairs

        Returns:
            ScheduleResult with optimized schedules and statistics

        Raises:
            ValueError: If no appliances provided or invalid price profile
        """
        # Validate inputs
        if not appliances:
            raise ValueError("At least one appliance must be provided")
        if price_profile is None:
            raise ValueError("Price profile must be provided")
        if price_profile.num_slots != self.config.time_slots:
            raise ValueError(
                f"Price profile has {price_profile.num_slots} slots, "
                f"expected {self.config.time_slots}"
            )

        # Store inputs
        self.appliances = appliances
        self.price_profile = price_profile

        # Build and solve problem
        self._build_problem(
            minimize_peak=minimize_peak,
            minimize_interruptions=minimize_interruptions,
            balance_load=balance_load,
            dependencies=dependencies,
            mutual_exclusions=mutual_exclusions,
        )

        status = self._solve()

        # Handle infeasible/error cases
        if status.lower() not in ("optimal", "feasible"):
            return ScheduleResult(
                schedules=[],
                total_cost=float("inf"),
                baseline_cost=calculate_baseline_cost(
                    appliances, price_profile, self.config
                ),
                savings_amount=0.0,
                savings_percent=0.0,
                solve_time_seconds=self._solve_time,
                status=status,
                total_energy_kwh=0.0,
                peak_power_kw=0.0,
                solver_info={"error": "Optimization failed"},
            )

        # Extract and validate solution
        schedules = self._extract_solution()
        validation_errors = self._validate_solution(schedules)

        if validation_errors:
            # Log warnings but continue
            for error in validation_errors:
                print(f"Warning: {error}")

        # Calculate and return results
        return self._calculate_results(schedules)

    def get_problem_stats(self) -> Dict[str, Any]:
        """Get statistics about the optimization problem.

        Returns:
            Dictionary with problem statistics
        """
        if self.problem is None:
            return {"status": "not_built"}

        return {
            "num_variables": self.problem.numVariables(),
            "num_constraints": self.problem.numConstraints(),
            "num_appliances": len(self.appliances),
            "time_slots": self.config.time_slots,
            "solver": self.config.solver_name,
            "status": self._solver_status,
            "solve_time": self._solve_time,
        }


def create_default_optimizer() -> MILPOptimizer:
    """Create optimizer with default configuration.

    Returns:
        MILPOptimizer instance with default settings
    """
    return MILPOptimizer(OptimizationConfig())


def optimize_single_appliance(
    appliance: Appliance,
    price_profile: PriceProfile,
    config: Optional[OptimizationConfig] = None,
) -> ApplianceSchedule:
    """Convenience function to optimize a single appliance.

    Args:
        appliance: Appliance to schedule
        price_profile: Electricity price profile
        config: Optional configuration

    Returns:
        Optimized schedule for the appliance
    """
    optimizer = MILPOptimizer(config)
    result = optimizer.optimize([appliance], price_profile)

    if not result.schedules:
        raise RuntimeError(f"Optimization failed: {result.status}")

    return result.schedules[0]


def quick_optimize(
    appliances: List[Appliance],
    prices: List[float],
    max_power_kw: Optional[float] = None,
) -> ScheduleResult:
    """Quick optimization with minimal configuration.

    Args:
        appliances: List of appliances to schedule
        prices: List of prices for each 15-minute slot (96 values)
        max_power_kw: Optional maximum total power limit

    Returns:
        ScheduleResult with optimized schedules
    """
    config = OptimizationConfig(
        time_slots=len(prices),
        max_total_power_kw=max_power_kw,
    )
    optimizer = MILPOptimizer(config)
    price_profile = PriceProfile(prices=np.array(prices))

    return optimizer.optimize(appliances, price_profile)
