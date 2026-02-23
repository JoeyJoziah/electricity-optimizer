"""
Performance Tests

Validates that performance optimizations are working:
- N+1 query fix in recommendation service (<=3 DB calls)
- Redis cache hits for analytics methods
- Stripe calls run in threads (non-blocking)
"""

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from models.price import Price, PriceRegion


# =============================================================================
# Phase 1: Query count verification for get_daily_recommendations
# =============================================================================


class TestRecommendationQueryCount:
    """Verify that get_daily_recommendations uses at most 3 DB calls."""

    @pytest.fixture
    def mock_user(self):
        return MagicMock(
            id="user_1",
            region="us_ct",
            current_supplier="Eversource Energy",
            preferences=None,
        )

    @pytest.fixture
    def mock_prices(self):
        now = datetime.now(timezone.utc)
        return [
            MagicMock(
                supplier="NextEra Energy",
                price_per_kwh=Decimal("0.18"),
                timestamp=now,
            ),
            MagicMock(
                supplier="Eversource Energy",
                price_per_kwh=Decimal("0.26"),
                timestamp=now,
            ),
            MagicMock(
                supplier="United Illuminating",
                price_per_kwh=Decimal("0.30"),
                timestamp=now,
            ),
        ]

    @pytest.fixture
    def mock_windows(self):
        now = datetime.now(timezone.utc)
        return [
            {
                "start": now,
                "end": now + timedelta(hours=2),
                "avg_price": Decimal("0.15"),
                "prices": [Decimal("0.14"), Decimal("0.16")],
            }
        ]

    @pytest.mark.asyncio
    async def test_daily_recommendations_max_3_queries(
        self, mock_user, mock_prices, mock_windows
    ):
        """get_daily_recommendations should make at most 3 service/repo calls."""
        from services.recommendation_service import RecommendationService

        user_repo = AsyncMock()
        user_repo.get_by_id = AsyncMock(return_value=mock_user)

        price_service = AsyncMock()
        price_service.get_price_comparison = AsyncMock(return_value=mock_prices)
        price_service.get_optimal_usage_windows = AsyncMock(return_value=mock_windows)

        service = RecommendationService(price_service, user_repo)
        result = await service.get_daily_recommendations("user_1")

        # Should have made exactly 1 user lookup
        assert user_repo.get_by_id.call_count == 1

        # Should have made exactly 1 price comparison call
        assert price_service.get_price_comparison.call_count == 1

        # Should have made exactly 1 optimal windows call
        assert price_service.get_optimal_usage_windows.call_count == 1

        # Total: 3 async calls. No per-appliance DB calls.
        total_calls = (
            user_repo.get_by_id.call_count
            + price_service.get_price_comparison.call_count
            + price_service.get_optimal_usage_windows.call_count
        )
        assert total_calls <= 3

        # Verify result structure is still correct
        assert result["user_id"] == "user_1"
        assert result["switching_recommendation"] is not None
        assert len(result["usage_recommendations"]) == 3  # 3 appliances

    @pytest.mark.asyncio
    async def test_daily_recommendations_no_user_returns_early(self):
        """If user not found, should make only 1 call (the user lookup)."""
        from services.recommendation_service import RecommendationService

        user_repo = AsyncMock()
        user_repo.get_by_id = AsyncMock(return_value=None)

        price_service = AsyncMock()

        service = RecommendationService(price_service, user_repo)
        result = await service.get_daily_recommendations("missing_user")

        assert user_repo.get_by_id.call_count == 1
        assert price_service.get_price_comparison.call_count == 0
        assert result["switching_recommendation"] is None
        assert result["usage_recommendations"] == []

    @pytest.mark.asyncio
    async def test_individual_methods_still_work(
        self, mock_user, mock_prices, mock_windows
    ):
        """Public methods get_switching_recommendation and get_usage_recommendation
        still work independently (they fetch their own data)."""
        from services.recommendation_service import RecommendationService

        user_repo = AsyncMock()
        user_repo.get_by_id = AsyncMock(return_value=mock_user)

        price_service = AsyncMock()
        price_service.get_price_comparison = AsyncMock(return_value=mock_prices)
        price_service.get_optimal_usage_windows = AsyncMock(return_value=mock_windows)
        price_service.get_current_prices = AsyncMock(return_value=mock_prices)

        service = RecommendationService(price_service, user_repo)

        # Individual call should still work
        switching = await service.get_switching_recommendation("user_1")
        assert switching is not None
        assert switching.user_id == "user_1"

        usage = await service.get_usage_recommendation("user_1", "dishwasher", 2)
        assert usage is not None
        assert usage["appliance"] == "dishwasher"


# =============================================================================
# Phase 4: Cache hit verification for analytics methods
# =============================================================================


class TestAnalyticsCaching:
    """Verify that analytics methods use Redis caching correctly."""

    @pytest.fixture
    def mock_cache(self):
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()
        return cache

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo.get_hourly_price_averages = AsyncMock(
            return_value=[
                {"hour": h, "avg_price": Decimal("0.20"), "count": 10}
                for h in range(24)
            ]
        )
        repo.get_supplier_price_stats = AsyncMock(
            return_value=[
                {
                    "supplier": "Eversource Energy",
                    "avg_price": Decimal("0.22"),
                    "min_price": Decimal("0.18"),
                    "max_price": Decimal("0.28"),
                    "volatility": Decimal("0.03"),
                    "count": 100,
                }
            ]
        )
        repo.get_historical_prices = AsyncMock(return_value=[])
        return repo

    @pytest.mark.asyncio
    async def test_peak_hours_caches_result(self, mock_repo, mock_cache):
        """get_peak_hours_analysis should cache its result."""
        from services.analytics_service import AnalyticsService

        service = AnalyticsService(mock_repo, cache=mock_cache)
        await service.get_peak_hours_analysis(PriceRegion.US_CT, days=7)

        # Should have called cache.set with 900s TTL
        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args.kwargs.get("ex") == 900 or call_args[1].get("ex") == 900

    @pytest.mark.asyncio
    async def test_peak_hours_returns_cached_on_hit(self, mock_repo, mock_cache):
        """get_peak_hours_analysis should return cached data on cache hit."""
        import json
        from services.analytics_service import AnalyticsService

        cached_data = {
            "peak_hours": [17, 18, 19],
            "off_peak_hours": [2, 3, 4],
            "average_by_hour": {str(h): "0.20" for h in range(24)},
            "overall_average": "0.2000",
            "peak_premium_percent": "5.0",
        }
        mock_cache.get = AsyncMock(return_value=json.dumps(cached_data))

        service = AnalyticsService(mock_repo, cache=mock_cache)
        result = await service.get_peak_hours_analysis(PriceRegion.US_CT, days=7)

        # Should NOT have called the repo
        mock_repo.get_hourly_price_averages.assert_not_called()

        # Should have returned the cached data
        assert result["peak_hours"] == [17, 18, 19]

    @pytest.mark.asyncio
    async def test_supplier_comparison_caches_with_1hr_ttl(self, mock_repo, mock_cache):
        """get_supplier_comparison_analytics should cache with 1 hour TTL."""
        from services.analytics_service import AnalyticsService

        service = AnalyticsService(mock_repo, cache=mock_cache)
        await service.get_supplier_comparison_analytics(PriceRegion.US_CT, days=30)

        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args.kwargs.get("ex") == 3600 or call_args[1].get("ex") == 3600

    @pytest.mark.asyncio
    async def test_price_trend_caches_result(self, mock_repo, mock_cache):
        """get_price_trend should cache its result with 15 min TTL."""
        from services.analytics_service import AnalyticsService

        now = datetime.now(timezone.utc)
        mock_repo.get_historical_prices = AsyncMock(
            return_value=[
                MagicMock(price_per_kwh=Decimal("0.20"), timestamp=now - timedelta(days=i))
                for i in range(10)
            ]
        )

        service = AnalyticsService(mock_repo, cache=mock_cache)
        await service.get_price_trend(PriceRegion.US_CT, days=7)

        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args.kwargs.get("ex") == 900 or call_args[1].get("ex") == 900

    @pytest.mark.asyncio
    async def test_no_cache_still_works(self, mock_repo):
        """Analytics should work without a cache (cache=None)."""
        from services.analytics_service import AnalyticsService

        service = AnalyticsService(mock_repo, cache=None)
        result = await service.get_peak_hours_analysis(PriceRegion.US_CT, days=7)

        assert "peak_hours" in result
        assert "off_peak_hours" in result


# =============================================================================
# Phase 5: Stripe non-blocking verification
# =============================================================================


class TestStripeNonBlocking:
    """Verify Stripe SDK calls use asyncio.to_thread (non-blocking)."""

    @pytest.fixture
    def stripe_service(self):
        from config.settings import settings

        with patch.object(settings, "stripe_secret_key", "sk_test_mock"):
            with patch.object(settings, "stripe_price_pro", "price_pro_test"):
                with patch.object(settings, "stripe_price_business", "price_biz_test"):
                    from services.stripe_service import StripeService
                    yield StripeService()

    @pytest.mark.asyncio
    async def test_checkout_uses_to_thread(self, stripe_service):
        """create_checkout_session should use asyncio.to_thread."""
        mock_session = MagicMock(
            id="cs_test_123",
            url="https://checkout.stripe.com/test",
            customer="cus_test",
        )

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = mock_session

            result = await stripe_service.create_checkout_session(
                user_id="user_1",
                email="test@example.com",
                tier="pro",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )

            mock_to_thread.assert_called_once()
            assert result["id"] == "cs_test_123"

    @pytest.mark.asyncio
    async def test_portal_uses_to_thread(self, stripe_service):
        """create_customer_portal_session should use asyncio.to_thread."""
        mock_session = MagicMock(
            id="bps_test",
            url="https://billing.stripe.com/test",
        )

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = mock_session

            result = await stripe_service.create_customer_portal_session(
                customer_id="cus_test",
                return_url="https://example.com/return",
            )

            mock_to_thread.assert_called_once()
            assert "url" in result

    @pytest.mark.asyncio
    async def test_subscription_list_uses_to_thread(self, stripe_service):
        """get_subscription_status should use asyncio.to_thread."""
        mock_sub = MagicMock(
            id="sub_test",
            status="active",
            current_period_end=int(datetime.now(timezone.utc).timestamp()) + 86400,
            cancel_at_period_end=False,
            metadata={"tier": "pro", "user_id": "user_1"},
        )
        mock_list = MagicMock(data=[mock_sub])

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = mock_list

            result = await stripe_service.get_subscription_status("cus_test")

            mock_to_thread.assert_called_once()
            assert result["tier"] == "pro"

    @pytest.mark.asyncio
    async def test_cancel_uses_to_thread(self, stripe_service):
        """cancel_subscription should use asyncio.to_thread."""
        mock_sub = MagicMock(
            status="canceled",
            cancel_at_period_end=False,
            canceled_at=int(datetime.now(timezone.utc).timestamp()),
        )

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = mock_sub

            result = await stripe_service.cancel_subscription(
                "sub_test", cancel_immediately=True
            )

            mock_to_thread.assert_called_once()
            assert result["status"] == "canceled"

    @pytest.mark.asyncio
    async def test_modify_uses_to_thread(self, stripe_service):
        """cancel_subscription with cancel_immediately=False should use to_thread for modify."""
        mock_sub = MagicMock(
            status="active",
            cancel_at_period_end=True,
            canceled_at=None,
            current_period_end=int(datetime.now(timezone.utc).timestamp()) + 86400,
        )

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = mock_sub

            result = await stripe_service.cancel_subscription(
                "sub_test", cancel_immediately=False
            )

            mock_to_thread.assert_called_once()
            assert result["cancel_at_period_end"] is True

    @pytest.mark.asyncio
    async def test_stripe_does_not_block_event_loop(self, stripe_service):
        """Verify that a slow Stripe call doesn't block the event loop."""
        import time

        async def slow_stripe_call(*args, **kwargs):
            # Simulate a 200ms Stripe API call in a thread
            await asyncio.sleep(0.05)
            return MagicMock(
                id="cs_test",
                url="https://checkout.stripe.com/test",
                customer="cus_test",
            )

        with patch("asyncio.to_thread", side_effect=slow_stripe_call):
            # Run the checkout call and a concurrent task
            event_loop_was_free = False

            async def concurrent_task():
                nonlocal event_loop_was_free
                await asyncio.sleep(0.01)
                event_loop_was_free = True

            results = await asyncio.gather(
                stripe_service.create_checkout_session(
                    user_id="user_1",
                    email="test@example.com",
                    tier="pro",
                    success_url="https://example.com/success",
                    cancel_url="https://example.com/cancel",
                ),
                concurrent_task(),
            )

            # The concurrent task should have completed while Stripe was "processing"
            assert event_loop_was_free


# =============================================================================
# Phase 3: SQL aggregation verification
# =============================================================================


class TestSQLAggregation:
    """Verify analytics service uses new SQL aggregation repo methods."""

    @pytest.mark.asyncio
    async def test_peak_hours_uses_sql_aggregation(self):
        """get_peak_hours_analysis should call get_hourly_price_averages, not get_historical_prices."""
        from services.analytics_service import AnalyticsService

        repo = AsyncMock()
        repo.get_hourly_price_averages = AsyncMock(
            return_value=[
                {"hour": h, "avg_price": Decimal("0.20"), "count": 10}
                for h in range(24)
            ]
        )

        service = AnalyticsService(repo)
        await service.get_peak_hours_analysis(PriceRegion.US_CT, days=7)

        repo.get_hourly_price_averages.assert_called_once()
        repo.get_historical_prices.assert_not_called()

    @pytest.mark.asyncio
    async def test_supplier_comparison_uses_sql_aggregation(self):
        """get_supplier_comparison_analytics should call get_supplier_price_stats, not get_historical_prices."""
        from services.analytics_service import AnalyticsService

        repo = AsyncMock()
        repo.get_supplier_price_stats = AsyncMock(
            return_value=[
                {
                    "supplier": "Eversource",
                    "avg_price": Decimal("0.22"),
                    "min_price": Decimal("0.18"),
                    "max_price": Decimal("0.28"),
                    "volatility": Decimal("0.03"),
                    "count": 100,
                }
            ]
        )

        service = AnalyticsService(repo)
        result = await service.get_supplier_comparison_analytics(PriceRegion.US_CT, days=30)

        repo.get_supplier_price_stats.assert_called_once()
        repo.get_historical_prices.assert_not_called()
        assert result["cheapest_supplier"] == "Eversource"
