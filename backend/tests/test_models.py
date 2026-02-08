"""
Model Tests - Written FIRST following TDD principles

Tests for:
- Price models with validation
- User models with validation
- Supplier models with validation

RED phase: These tests should FAIL initially until models are implemented.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pydantic import ValidationError


# =============================================================================
# PRICE MODEL TESTS
# =============================================================================


class TestPriceModel:
    """Tests for the Price Pydantic model"""

    def test_price_model_creation_with_valid_data(self):
        """Test Price model can be created with valid data"""
        from models.price import Price, PriceRegion

        price = Price(
            id="price_123",
            region=PriceRegion.US_CT,
            supplier="Eversource Energy",
            price_per_kwh=Decimal("0.26"),
            timestamp=datetime.now(timezone.utc),
            currency="USD"
        )

        assert price.region == PriceRegion.US_CT
        assert price.price_per_kwh == Decimal("0.26")
        assert price.supplier == "Eversource Energy"
        assert price.currency == "USD"

    def test_price_model_validates_negative_price(self):
        """Test Price model rejects negative prices"""
        from models.price import Price, PriceRegion

        with pytest.raises(ValidationError) as exc_info:
            Price(
                id="price_123",
                region=PriceRegion.US_CT,
                supplier="Test Supplier",
                price_per_kwh=Decimal("-0.10"),  # Invalid negative price
                timestamp=datetime.now(timezone.utc),
                currency="USD"
            )

        assert "price_per_kwh" in str(exc_info.value)

    def test_price_model_validates_zero_price(self):
        """Test Price model accepts zero price (can happen with negative pricing)"""
        from models.price import Price, PriceRegion

        # Zero price should be allowed (negative pricing scenarios)
        price = Price(
            id="price_123",
            region=PriceRegion.US_CT,
            supplier="Test Supplier",
            price_per_kwh=Decimal("0.00"),
            timestamp=datetime.now(timezone.utc),
            currency="USD"
        )

        assert price.price_per_kwh == Decimal("0.00")

    def test_price_model_validates_currency_code(self):
        """Test Price model validates currency code format"""
        from models.price import Price, PriceRegion

        with pytest.raises(ValidationError):
            Price(
                id="price_123",
                region=PriceRegion.US_CT,
                supplier="Test",
                price_per_kwh=Decimal("0.25"),
                timestamp=datetime.now(timezone.utc),
                currency="INVALID"  # Should be 3-letter code
            )

    def test_price_model_validates_region_enum(self):
        """Test Price model validates region is a valid enum"""
        from models.price import Price, PriceRegion

        with pytest.raises(ValidationError):
            Price(
                id="price_123",
                region="INVALID_REGION",  # Invalid region
                supplier="Test",
                price_per_kwh=Decimal("0.25"),
                timestamp=datetime.now(timezone.utc),
                currency="USD"
            )

    def test_price_model_auto_generates_id(self):
        """Test Price model auto-generates UUID if not provided"""
        from models.price import Price, PriceRegion

        price = Price(
            region=PriceRegion.US_CT,
            supplier="Test",
            price_per_kwh=Decimal("0.25"),
            timestamp=datetime.now(timezone.utc),
            currency="USD"
        )

        assert price.id is not None
        assert len(price.id) > 0

    def test_price_model_optional_fields(self):
        """Test Price model optional fields have correct defaults"""
        from models.price import Price, PriceRegion

        price = Price(
            region=PriceRegion.US_CT,
            supplier="Test",
            price_per_kwh=Decimal("0.25"),
            timestamp=datetime.now(timezone.utc),
            currency="USD"
        )

        assert price.is_peak is None
        assert price.carbon_intensity is None
        assert price.energy_source is None

    def test_price_model_serialization(self):
        """Test Price model can be serialized to dict"""
        from models.price import Price, PriceRegion

        timestamp = datetime.now(timezone.utc)
        price = Price(
            id="price_123",
            region=PriceRegion.US_CT,
            supplier="Test",
            price_per_kwh=Decimal("0.25"),
            timestamp=timestamp,
            currency="USD"
        )

        data = price.model_dump()

        assert data["id"] == "price_123"
        assert data["region"] == "us_ct"
        assert data["price_per_kwh"] == Decimal("0.25")


class TestPriceRegionEnum:
    """Tests for PriceRegion enum"""

    def test_all_regions_defined(self):
        """Test all expected regions are defined"""
        from models.price import PriceRegion

        expected_regions = ["UK", "GERMANY", "FRANCE", "SPAIN", "US_CA", "US_TX", "US_NY", "US_CT"]

        for region in expected_regions:
            assert hasattr(PriceRegion, region)

    def test_region_values(self):
        """Test region enum values are lowercase strings"""
        from models.price import PriceRegion

        assert PriceRegion.UK.value == "uk"
        assert PriceRegion.GERMANY.value == "germany"


class TestPriceForecastModel:
    """Tests for PriceForecast model"""

    def test_forecast_creation(self):
        """Test PriceForecast model creation"""
        from models.price import PriceForecast, Price, PriceRegion

        base_time = datetime.now(timezone.utc)
        prices = [
            Price(
                region=PriceRegion.US_CT,
                supplier="Test",
                price_per_kwh=Decimal("0.25"),
                timestamp=base_time + timedelta(hours=i),
                currency="USD"
            )
            for i in range(24)
        ]

        forecast = PriceForecast(
            region=PriceRegion.US_CT,
            generated_at=base_time,
            horizon_hours=24,
            prices=prices,
            confidence=0.85
        )

        assert len(forecast.prices) == 24
        assert forecast.confidence == 0.85
        assert forecast.horizon_hours == 24

    def test_forecast_validates_confidence_range(self):
        """Test PriceForecast validates confidence is between 0 and 1"""
        from models.price import PriceForecast, PriceRegion

        with pytest.raises(ValidationError):
            PriceForecast(
                region=PriceRegion.US_CT,
                generated_at=datetime.now(timezone.utc),
                horizon_hours=24,
                prices=[],
                confidence=1.5  # Invalid - must be <= 1.0
            )


# =============================================================================
# USER MODEL TESTS
# =============================================================================


class TestUserModel:
    """Tests for the User Pydantic model"""

    def test_user_model_creation(self):
        """Test User model can be created with valid data"""
        from models.user import User

        user = User(
            id="user_123",
            email="test@example.com",
            name="Test User",
            region="us_ct"
        )

        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.region == "us_ct"

    def test_user_model_validates_email(self):
        """Test User model validates email format"""
        from models.user import User

        with pytest.raises(ValidationError):
            User(
                id="user_123",
                email="invalid-email",  # Invalid email format
                name="Test User",
                region="us_ct"
            )

    def test_user_model_auto_generates_id(self):
        """Test User model auto-generates UUID if not provided"""
        from models.user import User

        user = User(
            email="test@example.com",
            name="Test User",
            region="us_ct"
        )

        assert user.id is not None

    def test_user_model_preferences_default(self):
        """Test User model has default empty preferences"""
        from models.user import User

        user = User(
            email="test@example.com",
            name="Test User",
            region="us_ct"
        )

        assert user.preferences is not None
        assert isinstance(user.preferences, dict)

    def test_user_model_created_at_timestamp(self):
        """Test User model has created_at timestamp"""
        from models.user import User

        user = User(
            email="test@example.com",
            name="Test User",
            region="us_ct"
        )

        assert user.created_at is not None
        assert isinstance(user.created_at, datetime)


class TestUserPreferencesModel:
    """Tests for UserPreferences model"""

    def test_preferences_creation(self):
        """Test UserPreferences can be created"""
        from models.user import UserPreferences

        prefs = UserPreferences(
            preferred_suppliers=["Eversource Energy", "United Illuminating"],
            notification_enabled=True,
            cost_threshold=Decimal("0.30"),
            auto_switch_enabled=False
        )

        assert len(prefs.preferred_suppliers) == 2
        assert prefs.notification_enabled is True
        assert prefs.cost_threshold == Decimal("0.30")

    def test_preferences_defaults(self):
        """Test UserPreferences has sensible defaults"""
        from models.user import UserPreferences

        prefs = UserPreferences()

        assert prefs.notification_enabled is True
        assert prefs.auto_switch_enabled is False


# =============================================================================
# SUPPLIER MODEL TESTS
# =============================================================================


class TestSupplierModel:
    """Tests for the Supplier Pydantic model"""

    def test_supplier_model_creation(self):
        """Test Supplier model can be created with valid data"""
        from models.supplier import Supplier

        supplier = Supplier(
            id="supplier_123",
            name="Eversource Energy",
            regions=["us_ct"],
            tariff_types=["variable", "fixed"],
            api_available=True
        )

        assert supplier.name == "Eversource Energy"
        assert "us_ct" in supplier.regions
        assert supplier.api_available is True

    def test_supplier_model_validates_name_length(self):
        """Test Supplier model validates name is not empty"""
        from models.supplier import Supplier

        with pytest.raises(ValidationError):
            Supplier(
                id="supplier_123",
                name="",  # Empty name should fail
                regions=["us_ct"],
                tariff_types=["variable"]
            )

    def test_supplier_model_validates_regions_not_empty(self):
        """Test Supplier model requires at least one region"""
        from models.supplier import Supplier

        with pytest.raises(ValidationError):
            Supplier(
                id="supplier_123",
                name="Test Supplier",
                regions=[],  # Empty regions should fail
                tariff_types=["variable"]
            )

    def test_supplier_model_contact_info(self):
        """Test Supplier model can include contact info"""
        from models.supplier import Supplier, SupplierContact

        contact = SupplierContact(
            email="support@eversource.com",
            phone="+1 800 286 2000",
            website="https://eversource.com"
        )

        supplier = Supplier(
            name="Eversource Energy",
            regions=["us_ct"],
            tariff_types=["variable"],
            contact=contact
        )

        assert supplier.contact.email == "support@eversource.com"


class TestTariffModel:
    """Tests for the Tariff model"""

    def test_tariff_creation(self):
        """Test Tariff model creation"""
        from models.supplier import Tariff, TariffType

        tariff = Tariff(
            id="tariff_123",
            supplier_id="supplier_456",
            name="Standard Service",
            type=TariffType.VARIABLE,
            base_rate=Decimal("0.10"),
            unit_rate=Decimal("0.25"),
            standing_charge=Decimal("0.40"),
            green_energy_percentage=100
        )

        assert tariff.name == "Standard Service"
        assert tariff.type == TariffType.VARIABLE
        assert tariff.green_energy_percentage == 100

    def test_tariff_validates_rates(self):
        """Test Tariff validates rates are non-negative"""
        from models.supplier import Tariff, TariffType

        with pytest.raises(ValidationError):
            Tariff(
                supplier_id="supplier_456",
                name="Test Tariff",
                type=TariffType.FIXED,
                base_rate=Decimal("-0.10"),  # Invalid negative rate
                unit_rate=Decimal("0.25"),
                standing_charge=Decimal("0.40")
            )


# =============================================================================
# API SCHEMA TESTS
# =============================================================================


class TestAPISchemas:
    """Tests for API request/response schemas"""

    def test_price_response_schema(self):
        """Test PriceResponse schema"""
        from models.price import PriceResponse

        response = PriceResponse(
            ticker="ELEC-US-CT",
            current_price=Decimal("0.26"),
            currency="USD",
            region="us_ct",
            supplier="Eversource Energy",
            updated_at=datetime.now(timezone.utc)
        )

        assert response.ticker == "ELEC-US-CT"
        assert response.current_price == Decimal("0.26")

    def test_price_list_response_schema(self):
        """Test PriceListResponse schema for paginated results"""
        from models.price import PriceListResponse, PriceResponse

        prices = [
            PriceResponse(
                ticker="ELEC-US-CT",
                current_price=Decimal("0.26"),
                currency="USD",
                region="us_ct",
                supplier="Test",
                updated_at=datetime.now(timezone.utc)
            )
        ]

        response = PriceListResponse(
            prices=prices,
            total=100,
            page=1,
            page_size=10
        )

        assert len(response.prices) == 1
        assert response.total == 100
        assert response.page == 1
