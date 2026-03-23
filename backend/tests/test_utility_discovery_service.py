"""
Tests for UtilityDiscoveryService

Verifies correct utility type discovery and completion tracking
per US state based on deregulation and availability sets.
"""

from services.utility_discovery_service import UtilityDiscoveryService


class TestDiscover:
    """Test utility discovery by state."""

    def test_ny_returns_all_four_utility_types(self):
        """NY has deregulated electricity, deregulated gas, heating oil, and community solar."""
        results = UtilityDiscoveryService.discover("NY")
        types = {r["utility_type"] for r in results}

        assert types == {"electricity", "natural_gas", "heating_oil", "community_solar"}

    def test_ny_electricity_is_deregulated(self):
        results = UtilityDiscoveryService.discover("NY")
        elec = next(r for r in results if r["utility_type"] == "electricity")

        assert elec["status"] == "deregulated"
        assert "supplier" in elec["description"].lower()

    def test_ny_gas_is_deregulated(self):
        results = UtilityDiscoveryService.discover("NY")
        gas = next(r for r in results if r["utility_type"] == "natural_gas")

        assert gas["status"] == "deregulated"

    def test_al_electricity_is_regulated(self):
        """Alabama has regulated electricity, no heating oil, no community solar."""
        results = UtilityDiscoveryService.discover("AL")
        elec = next(r for r in results if r["utility_type"] == "electricity")

        assert elec["status"] == "regulated"

    def test_al_has_only_electricity_and_gas(self):
        """Alabama doesn't have heating oil or community solar."""
        results = UtilityDiscoveryService.discover("AL")
        types = {r["utility_type"] for r in results}

        assert "heating_oil" not in types
        assert "community_solar" not in types
        assert "electricity" in types
        assert "natural_gas" in types

    def test_tx_electricity_deregulated_no_heating_oil(self):
        """Texas has deregulated electricity but no heating oil."""
        results = UtilityDiscoveryService.discover("TX")
        types = {r["utility_type"] for r in results}

        assert "electricity" in types
        assert "heating_oil" not in types

        elec = next(r for r in results if r["utility_type"] == "electricity")
        assert elec["status"] == "deregulated"

    def test_ct_has_all_four(self):
        """Connecticut has deregulated electricity, deregulated gas, heating oil, community solar."""
        results = UtilityDiscoveryService.discover("CT")
        types = {r["utility_type"] for r in results}

        assert types == {"electricity", "natural_gas", "heating_oil", "community_solar"}

    def test_mn_has_community_solar(self):
        """Minnesota has community solar but regulated electricity."""
        results = UtilityDiscoveryService.discover("MN")

        solar = next((r for r in results if r["utility_type"] == "community_solar"), None)
        assert solar is not None
        assert solar["status"] == "available"

        elec = next(r for r in results if r["utility_type"] == "electricity")
        assert elec["status"] == "regulated"

    def test_heating_oil_status_is_available(self):
        """Heating oil is always 'available' (competitive market, not regulated/deregulated)."""
        results = UtilityDiscoveryService.discover("CT")
        oil = next(r for r in results if r["utility_type"] == "heating_oil")

        assert oil["status"] == "available"

    def test_case_insensitive(self):
        """State codes should be case-insensitive."""
        lower = UtilityDiscoveryService.discover("ny")
        upper = UtilityDiscoveryService.discover("NY")

        assert len(lower) == len(upper)
        assert {r["utility_type"] for r in lower} == {r["utility_type"] for r in upper}

    def test_all_results_have_required_keys(self):
        results = UtilityDiscoveryService.discover("NY")

        for r in results:
            assert "utility_type" in r
            assert "label" in r
            assert "status" in r
            assert "description" in r

    def test_ga_gas_deregulated(self):
        """Georgia has deregulated gas."""
        results = UtilityDiscoveryService.discover("GA")
        gas = next(r for r in results if r["utility_type"] == "natural_gas")

        assert gas["status"] == "deregulated"


class TestCompletionStatus:
    """Test completion tracking."""

    def test_one_of_four_tracked_ny(self):
        result = UtilityDiscoveryService.get_completion_status("NY", ["electricity"])

        assert result["tracked"] == 1
        assert result["available"] == 4
        assert result["percent"] == 25
        assert len(result["missing"]) == 3

    def test_all_tracked_ny(self):
        result = UtilityDiscoveryService.get_completion_status(
            "NY", ["electricity", "natural_gas", "heating_oil", "community_solar"]
        )

        assert result["tracked"] == 4
        assert result["available"] == 4
        assert result["percent"] == 100
        assert len(result["missing"]) == 0

    def test_ignores_invalid_tracked_types(self):
        """Tracked types not available in the state are ignored."""
        result = UtilityDiscoveryService.get_completion_status(
            "AL",
            ["electricity", "heating_oil"],  # AL doesn't have heating oil
        )

        assert result["tracked"] == 1  # only electricity counts
        assert result["available"] == 2  # electricity + natural_gas

    def test_missing_contains_undiscovered_utilities(self):
        result = UtilityDiscoveryService.get_completion_status("CT", ["electricity"])
        missing_types = {m["utility_type"] for m in result["missing"]}

        assert "natural_gas" in missing_types
        assert "heating_oil" in missing_types
        assert "community_solar" in missing_types
        assert "electricity" not in missing_types

    def test_empty_state_returns_zero_percent(self):
        """Edge case: state with no tracked types still returns valid structure."""
        result = UtilityDiscoveryService.get_completion_status("AL", [])
        assert result["tracked"] == 0
        assert result["percent"] == 0


class TestAPIValidation:
    """Test API endpoint validation logic."""

    def test_discover_returns_state_and_count(self):
        results = UtilityDiscoveryService.discover("NY")
        assert len(results) > 0

    def test_completion_requires_tracked_types(self):
        result = UtilityDiscoveryService.get_completion_status("NY", [])
        assert result["tracked"] == 0
        assert result["percent"] == 0
