"""
Service Tests - Written FIRST following TDD principles

Tests for:
- PriceService business logic
- Recommendation logic
- Data aggregation

RED phase: These tests should FAIL initially until services are implemented.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# PRICE SERVICE TESTS
# =============================================================================


class TestPriceService:
    """Tests for PriceService business logic"""

    @pytest.fixture
    def mock_price_repo(self):
        """Create a mock price repository"""
        repo = AsyncMock()
        return repo

    @pytest.fixture
    def mock_cache(self):
        """Create a mock cache"""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()
        return cache

    @pytest.mark.asyncio
    async def test_get_current_price(self, mock_price_repo, mock_cache):
        """Test getting current price for a region"""
        from services.price_service import PriceService
        from models.price import Price, PriceRegion

        # Setup mock return
        mock_price_repo.get_latest_by_supplier.return_value = MagicMock(
            id="price_1",
            region="us_ct",
            supplier="Eversource Energy",
            price_per_kwh=Decimal("0.26"),
            timestamp=datetime.now(timezone.utc),
            currency="USD"
        )

        service = PriceService(mock_price_repo, mock_cache)
        price = await service.get_current_price(
            region=PriceRegion.US_CT,
            supplier="Eversource Energy"
        )

        assert price is not None
        assert price.price_per_kwh == Decimal("0.26")

    @pytest.mark.asyncio
    async def test_get_cheapest_supplier(self, mock_price_repo, mock_cache):
        """Test finding the cheapest supplier in a region"""
        from services.price_service import PriceService
        from models.price import PriceRegion

        # Setup mock with multiple suppliers
        mock_price_repo.get_current_prices.return_value = [
            MagicMock(supplier="Expensive Co", price_per_kwh=Decimal("0.35")),
            MagicMock(supplier="Cheap Energy", price_per_kwh=Decimal("0.18")),
            MagicMock(supplier="Mid Range", price_per_kwh=Decimal("0.25")),
        ]

        service = PriceService(mock_price_repo, mock_cache)
        cheapest = await service.get_cheapest_supplier(region=PriceRegion.US_CT)

        assert cheapest is not None
        assert cheapest.supplier == "Cheap Energy"
        assert cheapest.price_per_kwh == Decimal("0.18")

    @pytest.mark.asyncio
    async def test_get_price_comparison(self, mock_price_repo, mock_cache):
        """Test getting price comparison across suppliers"""
        from services.price_service import PriceService
        from models.price import PriceRegion

        mock_price_repo.get_current_prices.return_value = [
            MagicMock(supplier="A", price_per_kwh=Decimal("0.25")),
            MagicMock(supplier="B", price_per_kwh=Decimal("0.30")),
        ]

        service = PriceService(mock_price_repo, mock_cache)
        comparison = await service.get_price_comparison(region=PriceRegion.US_CT)

        assert isinstance(comparison, list)
        assert len(comparison) == 2
        # Should be sorted by price ascending
        assert comparison[0].price_per_kwh <= comparison[1].price_per_kwh

    @pytest.mark.asyncio
    async def test_calculate_daily_cost(self, mock_price_repo, mock_cache):
        """Test calculating daily cost based on usage"""
        from services.price_service import PriceService
        from models.price import PriceRegion

        # 24 hours of prices
        mock_price_repo.get_historical_prices.return_value = [
            MagicMock(price_per_kwh=Decimal("0.20"), timestamp=datetime.now(timezone.utc) + timedelta(hours=i))
            for i in range(24)
        ]

        service = PriceService(mock_price_repo, mock_cache)

        # 10 kWh usage
        cost = await service.calculate_daily_cost(
            region=PriceRegion.US_CT,
            supplier="Test",
            kwh_usage=Decimal("10.0"),
            target_date=datetime.now(timezone.utc).date()
        )

        # 10 kWh * 0.20/kWh = 2.00
        assert cost == Decimal("2.00")

    @pytest.mark.asyncio
    async def test_get_price_forecast(self, mock_price_repo, mock_cache):
        """Test getting price forecast"""
        from services.price_service import PriceService
        from models.price import PriceRegion, PriceForecast

        mock_price_repo.get_current_prices.return_value = [
            MagicMock(price_per_kwh=Decimal("0.26"), supplier="Test Supplier", currency="USD")
        ]

        service = PriceService(mock_price_repo, mock_cache)
        forecast = await service.get_price_forecast(
            region=PriceRegion.US_CT,
            hours=24
        )

        assert forecast is not None
        assert hasattr(forecast, 'prices')

    @pytest.mark.asyncio
    async def test_get_optimal_usage_windows(self, mock_price_repo, mock_cache):
        """Test finding optimal low-price windows for appliance usage"""
        from services.price_service import PriceService
        from models.price import PriceRegion

        # Create price data with varying prices
        base_time = datetime.now(timezone.utc).replace(minute=0, second=0)
        prices = []
        for i in range(24):
            price = Decimal("0.30") if 16 <= i <= 20 else Decimal("0.15")  # Peak vs off-peak
            prices.append(MagicMock(
                price_per_kwh=price,
                timestamp=base_time + timedelta(hours=i)
            ))

        mock_price_repo.get_historical_prices.return_value = prices

        service = PriceService(mock_price_repo, mock_cache)
        windows = await service.get_optimal_usage_windows(
            region=PriceRegion.US_CT,
            duration_hours=2,
            within_hours=24
        )

        assert isinstance(windows, list)
        assert len(windows) > 0
        # First window should be during off-peak
        assert windows[0]['avg_price'] < Decimal("0.20")


# =============================================================================
# RECOMMENDATION SERVICE TESTS
# =============================================================================


class TestRecommendationService:
    """Tests for recommendation logic"""

    @pytest.fixture
    def mock_price_service(self):
        """Create a mock price service"""
        return AsyncMock()

    @pytest.fixture
    def mock_user_repo(self):
        """Create a mock user repository"""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_generate_switching_recommendation(self, mock_price_service, mock_user_repo):
        """Test generating supplier switching recommendation"""
        from services.recommendation_service import RecommendationService
        from models.price import PriceRegion

        # User is on expensive supplier
        mock_user_repo.get_by_id.return_value = MagicMock(
            id="user_123",
            current_supplier="Expensive Energy",
            region="us_ct",
            preferences={}
        )

        mock_price_service.get_price_comparison.return_value = [
            MagicMock(supplier="Cheap Energy", price_per_kwh=Decimal("0.18")),
            MagicMock(supplier="Expensive Energy", price_per_kwh=Decimal("0.35")),
        ]

        service = RecommendationService(mock_price_service, mock_user_repo)
        recommendation = await service.get_switching_recommendation("user_123")

        assert recommendation is not None
        assert recommendation.recommended_supplier == "Cheap Energy"
        assert recommendation.potential_savings > Decimal("0")

    @pytest.mark.asyncio
    async def test_generate_usage_recommendation(self, mock_price_service, mock_user_repo):
        """Test generating usage timing recommendation"""
        from services.recommendation_service import RecommendationService

        mock_user_repo.get_by_id.return_value = MagicMock(
            id="user_123",
            region="us_ct"
        )

        mock_price_service.get_optimal_usage_windows.return_value = [
            {
                'start': datetime.now(timezone.utc),
                'end': datetime.now(timezone.utc) + timedelta(hours=2),
                'avg_price': Decimal("0.12")
            }
        ]

        mock_price_service.get_current_prices.return_value = [
            MagicMock(price_per_kwh=Decimal("0.30"))
        ]

        service = RecommendationService(mock_price_service, mock_user_repo)
        recommendation = await service.get_usage_recommendation(
            user_id="user_123",
            appliance="washing_machine",
            duration_hours=2
        )

        assert recommendation is not None
        assert 'optimal_start_time' in recommendation

    @pytest.mark.asyncio
    async def test_recommendation_respects_user_preferences(self, mock_price_service, mock_user_repo):
        """Test recommendations respect user preferences like green energy"""
        from services.recommendation_service import RecommendationService

        mock_user_repo.get_by_id.return_value = MagicMock(
            id="user_123",
            region="us_ct",
            preferences={"green_energy_only": True},
        )

        mock_price_service.get_price_comparison.return_value = [
            MagicMock(supplier="Dirty Cheap", price_per_kwh=Decimal("0.10"), green_energy_percentage=0),
            MagicMock(supplier="Green Energy Co", price_per_kwh=Decimal("0.20"), green_energy_percentage=100),
        ]

        service = RecommendationService(mock_price_service, mock_user_repo)
        recommendation = await service.get_switching_recommendation("user_123")

        # Should recommend green supplier even though more expensive
        assert recommendation.recommended_supplier == "Green Energy Co"


# =============================================================================
# ANALYTICS SERVICE TESTS
# =============================================================================


class TestAnalyticsService:
    """Tests for analytics and aggregation"""

    @pytest.fixture
    def mock_price_repo(self):
        """Create a mock price repository"""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_calculate_average_price(self, mock_price_repo):
        """Test calculating average price for a period"""
        from services.analytics_service import AnalyticsService
        from models.price import PriceRegion

        mock_price_repo.get_historical_prices.return_value = [
            MagicMock(price_per_kwh=Decimal("0.20")),
            MagicMock(price_per_kwh=Decimal("0.30")),
            MagicMock(price_per_kwh=Decimal("0.25")),
        ]

        service = AnalyticsService(mock_price_repo)
        avg = await service.calculate_average_price(
            region=PriceRegion.US_CT,
            days=7
        )

        assert avg == Decimal("0.25")

    @pytest.mark.asyncio
    async def test_calculate_price_volatility(self, mock_price_repo):
        """Test calculating price volatility"""
        from services.analytics_service import AnalyticsService
        from models.price import PriceRegion

        mock_price_repo.get_historical_prices.return_value = [
            MagicMock(price_per_kwh=Decimal("0.10")),
            MagicMock(price_per_kwh=Decimal("0.50")),
            MagicMock(price_per_kwh=Decimal("0.20")),
            MagicMock(price_per_kwh=Decimal("0.40")),
        ]

        service = AnalyticsService(mock_price_repo)
        volatility = await service.calculate_volatility(
            region=PriceRegion.US_CT,
            days=7
        )

        assert volatility > 0  # High variance prices
        assert isinstance(volatility, Decimal)

    @pytest.mark.asyncio
    async def test_get_price_trends(self, mock_price_repo):
        """Test getting price trend analysis"""
        from services.analytics_service import AnalyticsService
        from models.price import PriceRegion

        # Prices increasing over time
        base_time = datetime.now(timezone.utc)
        mock_price_repo.get_historical_prices.return_value = [
            MagicMock(price_per_kwh=Decimal("0.20"), timestamp=base_time - timedelta(days=6)),
            MagicMock(price_per_kwh=Decimal("0.22"), timestamp=base_time - timedelta(days=4)),
            MagicMock(price_per_kwh=Decimal("0.25"), timestamp=base_time - timedelta(days=2)),
            MagicMock(price_per_kwh=Decimal("0.28"), timestamp=base_time),
        ]

        service = AnalyticsService(mock_price_repo)
        trend = await service.get_price_trend(
            region=PriceRegion.US_CT,
            days=7
        )

        assert trend['direction'] == 'increasing'
        assert trend['change_percent'] > 0

    @pytest.mark.asyncio
    async def test_get_peak_hours_analysis(self, mock_price_repo):
        """Test analyzing peak usage hours"""
        from services.analytics_service import AnalyticsService
        from models.price import PriceRegion

        # Create 24 hours of price data
        base_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        prices = []
        for hour in range(24):
            # Peak prices 16:00-20:00
            price = Decimal("0.35") if 16 <= hour <= 20 else Decimal("0.15")
            prices.append(MagicMock(
                price_per_kwh=price,
                timestamp=base_time.replace(hour=hour)
            ))

        mock_price_repo.get_historical_prices.return_value = prices

        service = AnalyticsService(mock_price_repo)
        analysis = await service.get_peak_hours_analysis(
            region=PriceRegion.US_CT,
            days=7
        )

        assert 'peak_hours' in analysis
        assert 'off_peak_hours' in analysis
        assert 16 in analysis['peak_hours']
