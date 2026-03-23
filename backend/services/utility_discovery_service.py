"""
Utility Discovery Service

Given a region/state, determines which utility types are available
and their deregulation status. Pure logic — no database required.
"""

from models.region import (
    COMMUNITY_SOLAR_STATES,
    DEREGULATED_ELECTRICITY_STATES,
    DEREGULATED_GAS_STATES,
    HEATING_OIL_STATES,
)


class UtilityDiscoveryService:
    """
    Determines available utility types for a given US state.

    Returns a list of utility descriptors with type, status,
    and human-readable description.
    """

    # Utility type definitions with availability logic
    _UTILITY_DEFS = [
        {
            "utility_type": "electricity",
            "label": "Electricity",
            "description_deregulated": "Choose your electricity supplier for the best rate.",
            "description_regulated": "Track your electricity rates and optimize usage.",
            "states": None,  # available everywhere
            "deregulated_states": DEREGULATED_ELECTRICITY_STATES,
        },
        {
            "utility_type": "natural_gas",
            "label": "Natural Gas",
            "description_deregulated": "Compare natural gas suppliers in your area.",
            "description_regulated": "Monitor natural gas prices in your state.",
            "states": None,  # available everywhere (but only deregulated in some)
            "deregulated_states": DEREGULATED_GAS_STATES,
        },
        {
            "utility_type": "heating_oil",
            "label": "Heating Oil",
            "description_deregulated": "Compare heating oil delivery prices.",
            "description_regulated": "Compare heating oil delivery prices.",
            "states": HEATING_OIL_STATES,
            "deregulated_states": set(),  # heating oil is always competitive market
        },
        {
            "utility_type": "community_solar",
            "label": "Community Solar",
            "description_deregulated": "Browse community solar programs to save on your bill.",
            "description_regulated": "Browse community solar programs to save on your bill.",
            "states": COMMUNITY_SOLAR_STATES,
            "deregulated_states": set(),  # not applicable
        },
    ]

    @classmethod
    def discover(cls, state_code: str) -> list[dict]:
        """
        Discover available utility types for a state.

        Args:
            state_code: 2-letter US state abbreviation (e.g. "NY", "TX")

        Returns:
            List of dicts with keys: utility_type, label, status, description
            status is one of: "deregulated", "regulated", "available"
        """
        state = state_code.upper()
        results = []

        for defn in cls._UTILITY_DEFS:
            # Check if this utility is available in this state
            if defn["states"] is not None and state not in defn["states"]:
                continue

            # Determine status
            if defn["deregulated_states"] and state in defn["deregulated_states"]:
                status = "deregulated"
                description = defn["description_deregulated"]
            elif defn["utility_type"] in ("heating_oil", "community_solar"):
                # These are always "available" (not regulated/deregulated)
                status = "available"
                description = defn["description_deregulated"]
            else:
                status = "regulated"
                description = defn["description_regulated"]

            results.append(
                {
                    "utility_type": defn["utility_type"],
                    "label": defn["label"],
                    "status": status,
                    "description": description,
                }
            )

        return results

    @classmethod
    def get_completion_status(cls, state_code: str, tracked_types: list[str]) -> dict:
        """
        Calculate utility tracking completion for a user.

        Args:
            state_code: 2-letter state abbreviation
            tracked_types: List of utility_type strings the user is tracking

        Returns:
            Dict with tracked, available, percent, missing utility types
        """
        available = cls.discover(state_code)
        available_types = {u["utility_type"] for u in available}
        tracked_set = set(tracked_types) & available_types

        total = len(available_types)
        tracked_count = len(tracked_set)
        percent = round((tracked_count / total) * 100) if total > 0 else 0
        missing = [u for u in available if u["utility_type"] not in tracked_set]

        return {
            "tracked": tracked_count,
            "available": total,
            "percent": percent,
            "missing": missing,
        }
