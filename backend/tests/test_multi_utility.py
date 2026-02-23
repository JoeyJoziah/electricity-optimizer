"""
Tests for Multi-State, Multi-Utility Expansion

Tests the new models, enums, and integrations added for the
multi-utility expansion (migration 006).
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from models.utility import (
    UtilityType,
    PriceUnit,
    UTILITY_DEFAULT_UNITS,
    UTILITY_LABELS,
    UNIT_LABELS,
)
from models.region import (
    Region,
    PriceRegion,
    PricingRegion,
    DEREGULATED_ELECTRICITY_STATES,
    DEREGULATED_GAS_STATES,
    HEATING_OIL_STATES,
    COMMUNITY_SOLAR_STATES,
)
from models.price import Price


# =============================================================================
# UtilityType enum tests
# =============================================================================


class TestUtilityType:
    """Tests for the UtilityType enum."""

    def test_all_utility_types_defined(self):
        """Verify all 5 utility types exist."""
        assert len(UtilityType) == 5
        assert UtilityType.ELECTRICITY == "electricity"
        assert UtilityType.NATURAL_GAS == "natural_gas"
        assert UtilityType.HEATING_OIL == "heating_oil"
        assert UtilityType.PROPANE == "propane"
        assert UtilityType.COMMUNITY_SOLAR == "community_solar"

    def test_utility_type_from_string(self):
        """UtilityType can be constructed from string values."""
        assert UtilityType("electricity") == UtilityType.ELECTRICITY
        assert UtilityType("natural_gas") == UtilityType.NATURAL_GAS

    def test_invalid_utility_type_raises(self):
        """Invalid utility type string raises ValueError."""
        with pytest.raises(ValueError):
            UtilityType("water")

    def test_default_units_mapping(self):
        """Each utility type has a default unit."""
        for ut in UtilityType:
            assert ut in UTILITY_DEFAULT_UNITS

    def test_electricity_default_unit_is_kwh(self):
        assert UTILITY_DEFAULT_UNITS[UtilityType.ELECTRICITY] == PriceUnit.KWH

    def test_gas_default_unit_is_therm(self):
        assert UTILITY_DEFAULT_UNITS[UtilityType.NATURAL_GAS] == PriceUnit.THERM

    def test_oil_default_unit_is_gallon(self):
        assert UTILITY_DEFAULT_UNITS[UtilityType.HEATING_OIL] == PriceUnit.GALLON

    def test_propane_default_unit_is_gallon(self):
        assert UTILITY_DEFAULT_UNITS[UtilityType.PROPANE] == PriceUnit.GALLON

    def test_labels_exist_for_all_types(self):
        """Every utility type has a human-readable label."""
        for ut in UtilityType:
            assert ut in UTILITY_LABELS
            assert isinstance(UTILITY_LABELS[ut], str)
            assert len(UTILITY_LABELS[ut]) > 0


# =============================================================================
# PriceUnit enum tests (expanded)
# =============================================================================


class TestPriceUnit:
    """Tests for the expanded PriceUnit enum."""

    def test_electricity_units(self):
        assert PriceUnit.KWH == "kwh"
        assert PriceUnit.MWH == "mwh"
        assert PriceUnit.CENTS_KWH == "cents_kwh"

    def test_gas_units(self):
        assert PriceUnit.THERM == "therm"
        assert PriceUnit.MCF == "mcf"
        assert PriceUnit.MMBTU == "mmbtu"
        assert PriceUnit.CCF == "ccf"

    def test_oil_propane_units(self):
        assert PriceUnit.GALLON == "gallon"

    def test_solar_units(self):
        assert PriceUnit.CREDIT_KWH == "credit_kwh"

    def test_unit_labels_exist(self):
        """Every PriceUnit has a display label."""
        for unit in PriceUnit:
            assert unit in UNIT_LABELS


# =============================================================================
# Region enum tests
# =============================================================================


class TestRegion:
    """Tests for the unified Region enum."""

    def test_all_50_states_plus_dc(self):
        """Region enum covers all 50 US states + DC."""
        us_regions = Region.us_regions()
        assert len(us_regions) == 51  # 50 states + DC

    def test_ct_exists(self):
        assert Region.US_CT.value == "us_ct"

    def test_is_us_property(self):
        assert Region.US_CT.is_us is True
        assert Region.US_TX.is_us is True
        assert Region.UK.is_us is False
        assert Region.GERMANY.is_us is False

    def test_state_code_property(self):
        assert Region.US_CT.state_code == "CT"
        assert Region.US_TX.state_code == "TX"
        assert Region.US_NY.state_code == "NY"
        assert Region.UK.state_code is None

    def test_from_state_code(self):
        assert Region.from_state_code("CT") == Region.US_CT
        assert Region.from_state_code("tx") == Region.US_TX

    def test_backward_compatible_aliases(self):
        """PriceRegion and PricingRegion are aliases for Region."""
        assert PriceRegion is Region
        assert PricingRegion is Region

    def test_international_regions(self):
        """International regions are defined."""
        assert Region.UK.value == "uk"
        assert Region.GERMANY.value == "de"
        assert Region.FRANCE.value == "fr"
        assert Region.JAPAN.value == "jp"
        assert Region.AUSTRALIA.value == "au"

    def test_deregulated_state_sets(self):
        """Deregulated state sets contain expected entries."""
        assert "CT" in DEREGULATED_ELECTRICITY_STATES
        assert "TX" in DEREGULATED_ELECTRICITY_STATES
        assert "OH" in DEREGULATED_ELECTRICITY_STATES
        assert len(DEREGULATED_ELECTRICITY_STATES) >= 17

        assert "CT" in DEREGULATED_GAS_STATES
        assert "GA" in DEREGULATED_GAS_STATES
        assert len(DEREGULATED_GAS_STATES) >= 15

        assert "CT" in HEATING_OIL_STATES
        assert "MA" in HEATING_OIL_STATES
        assert len(HEATING_OIL_STATES) >= 8

        assert "CT" in COMMUNITY_SOLAR_STATES
        assert "NY" in COMMUNITY_SOLAR_STATES


# =============================================================================
# Price model with utility_type tests
# =============================================================================


class TestPriceWithUtilityType:
    """Tests for the Price model's utility_type field."""

    def test_default_utility_type_is_electricity(self):
        """Price defaults to electricity utility type."""
        price = Price(
            region="us_ct",
            supplier="Eversource",
            price_per_kwh=Decimal("0.25"),
            timestamp=datetime.now(timezone.utc),
            currency="USD",
        )
        assert price.utility_type == UtilityType.ELECTRICITY

    def test_explicit_utility_type(self):
        """Price can be created with explicit utility type."""
        price = Price(
            region="us_ct",
            supplier="Eversource",
            price_per_kwh=Decimal("1.50"),
            timestamp=datetime.now(timezone.utc),
            currency="USD",
            utility_type=UtilityType.NATURAL_GAS,
        )
        assert price.utility_type == UtilityType.NATURAL_GAS

    def test_heating_oil_price(self):
        price = Price(
            region="us_ct",
            supplier="CT Oil Co",
            price_per_kwh=Decimal("3.50"),
            timestamp=datetime.now(timezone.utc),
            currency="USD",
            utility_type=UtilityType.HEATING_OIL,
        )
        assert price.utility_type == UtilityType.HEATING_OIL

    def test_utility_type_serialization(self):
        """utility_type serializes to string in model_dump."""
        price = Price(
            region="us_ct",
            supplier="Test",
            price_per_kwh=Decimal("0.10"),
            timestamp=datetime.now(timezone.utc),
            currency="USD",
            utility_type=UtilityType.PROPANE,
        )
        data = price.model_dump()
        assert data["utility_type"] == "propane"


# =============================================================================
# EIA Client tests
# =============================================================================


class TestEIAClient:
    """Tests for the EIA API client."""

    @pytest.fixture
    def mock_eia_client(self):
        from integrations.pricing_apis.eia import EIAClient
        from integrations.pricing_apis.rate_limiter import create_api_rate_limiter

        client = EIAClient(
            api_key="test-key",
            rate_limiter=create_api_rate_limiter("eia", requests_per_hour=100),
        )
        return client

    def test_supported_regions_are_all_us(self, mock_eia_client):
        """EIA client only supports US regions."""
        regions = mock_eia_client.get_supported_regions()
        assert len(regions) == 51  # 50 states + DC
        for r in regions:
            assert r.is_us

    def test_international_region_raises(self, mock_eia_client):
        """EIA client rejects non-US regions."""
        with pytest.raises(ValueError, match="US regions"):
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                mock_eia_client.get_electricity_price(Region.UK)
            )

    def test_eia_client_name(self, mock_eia_client):
        assert mock_eia_client.client_name == "eia"

    def test_eia_base_url(self, mock_eia_client):
        assert "eia.gov" in mock_eia_client.base_url


# =============================================================================
# NREL expansion tests
# =============================================================================


class TestNRELExpansion:
    """Tests for the expanded NREL region mapping."""

    def test_all_us_states_mapped(self):
        from integrations.pricing_apis.nrel import NREL_REGION_MAP
        # All US regions should be in the map
        us_regions = Region.us_regions()
        for r in us_regions:
            assert r in NREL_REGION_MAP, f"{r} not in NREL_REGION_MAP"

    def test_all_states_have_zip_codes(self):
        from integrations.pricing_apis.nrel import STATE_ZIP_CODES
        # All 50 states + DC should have ZIP codes
        assert len(STATE_ZIP_CODES) >= 51

    def test_ct_zip_unchanged(self):
        from integrations.pricing_apis.nrel import STATE_ZIP_CODES
        assert STATE_ZIP_CODES["CT"] == "06510"

    def test_state_codes_are_two_letters(self):
        from integrations.pricing_apis.nrel import STATE_ZIP_CODES
        for code in STATE_ZIP_CODES:
            assert len(code) == 2
            assert code.isupper()

    def test_zip_codes_are_five_digits(self):
        from integrations.pricing_apis.nrel import STATE_ZIP_CODES
        for zip_code in STATE_ZIP_CODES.values():
            assert len(zip_code) == 5
            assert zip_code.isdigit()


# =============================================================================
# Supplier model with utility_types tests
# =============================================================================


class TestSupplierUtilityTypes:
    """Tests for the Supplier model's utility_types field."""

    def test_supplier_default_utility_types(self):
        from models.supplier import Supplier
        supplier = Supplier(
            name="Test Supplier",
            regions=["us_ct"],
            tariff_types=["fixed"],
        )
        assert supplier.utility_types == [UtilityType.ELECTRICITY]

    def test_supplier_multiple_utility_types(self):
        from models.supplier import Supplier
        supplier = Supplier(
            name="Multi Utility Co",
            regions=["us_ct", "us_ma"],
            tariff_types=["fixed", "variable"],
            utility_types=[UtilityType.ELECTRICITY, UtilityType.NATURAL_GAS],
        )
        assert len(supplier.utility_types) == 2
        assert UtilityType.ELECTRICITY in supplier.utility_types
        assert UtilityType.NATURAL_GAS in supplier.utility_types


# =============================================================================
# Tariff model with utility_type tests
# =============================================================================


class TestTariffUtilityType:
    """Tests for the Tariff model's utility_type field."""

    def test_tariff_default_utility_type(self):
        from models.supplier import Tariff, TariffType
        tariff = Tariff(
            supplier_id="test",
            name="Standard",
            type=TariffType.FIXED,
            base_rate=Decimal("0"),
            unit_rate=Decimal("0.25"),
            standing_charge=Decimal("0.40"),
        )
        assert tariff.utility_type == UtilityType.ELECTRICITY

    def test_tariff_gas_utility_type(self):
        from models.supplier import Tariff, TariffType
        tariff = Tariff(
            supplier_id="test",
            name="Gas Fixed",
            type=TariffType.FIXED,
            base_rate=Decimal("0"),
            unit_rate=Decimal("1.20"),
            standing_charge=Decimal("0.50"),
            utility_type=UtilityType.NATURAL_GAS,
        )
        assert tariff.utility_type == UtilityType.NATURAL_GAS
