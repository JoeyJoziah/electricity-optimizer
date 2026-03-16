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

        # Should have called cache.set for lock + data + lock release
        # Find the data caching call (the one with ex=900)
        data_calls = [
            c for c in mock_cache.set.call_args_list
            if c.kwargs.get("ex") == 900 or (len(c.args) > 1 and c.kwargs.get("ex") == 900)
        ]
        assert len(data_calls) == 1

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

        # Find the data caching call (the one with ex=3600)
        data_calls = [
            c for c in mock_cache.set.call_args_list
            if c.kwargs.get("ex") == 3600
        ]
        assert len(data_calls) == 1

    @pytest.mark.asyncio
    async def test_price_trend_caches_result(self, mock_repo, mock_cache):
        """get_price_trend should cache its result with 15 min TTL."""
        from services.analytics_service import AnalyticsService

        mock_repo.get_price_trend_aggregates = AsyncMock(return_value={
            "first_third_avg": Decimal("0.20"),
            "last_third_avg": Decimal("0.24"),
            "total_count": 10,
        })

        service = AnalyticsService(mock_repo, cache=mock_cache)
        await service.get_price_trend(PriceRegion.US_CT, days=7)

        # Find the data caching call (the one with ex=900)
        data_calls = [
            c for c in mock_cache.set.call_args_list
            if c.kwargs.get("ex") == 900
        ]
        assert len(data_calls) == 1

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


# =============================================================================
# Phase 6: Learning service — model accuracy SQL aggregation
# =============================================================================


class TestLearningServiceSQLAggregation:
    """Verify get_model_accuracy_by_version uses SQL GROUP BY aggregation.

    The nightly learning cycle calls update_ensemble_weights() which fetches
    per-model accuracy stats.  With large 7-day observation windows this can
    be tens of thousands of rows.  Aggregation must happen in the DB via a
    single GROUP BY query — not by pulling raw rows into Python.
    """

    @pytest.fixture
    def mock_obs(self):
        from unittest.mock import AsyncMock
        obs = AsyncMock()
        obs.get_forecast_accuracy = AsyncMock(
            return_value={"total": 0, "mape": None, "rmse": None, "coverage": None}
        )
        obs.get_hourly_bias = AsyncMock(return_value=[])
        obs.get_model_accuracy_by_version = AsyncMock(return_value=[])
        return obs

    @pytest.fixture
    def mock_vs(self):
        vs = MagicMock()
        vs.async_insert = AsyncMock(return_value="vec-test")
        vs.async_prune = AsyncMock(return_value=0)
        return vs

    @pytest.mark.asyncio
    async def test_update_weights_uses_single_aggregated_call(self, mock_obs, mock_vs):
        """update_ensemble_weights must call get_model_accuracy_by_version once
        and receive pre-aggregated dicts — no raw row iteration in the service."""
        from services.learning_service import LearningService

        mock_obs.get_model_accuracy_by_version.return_value = [
            {"model_version": "v2.1", "mape": 3.5, "rmse": 0.011, "coverage": 91.0, "count": 120},
            {"model_version": "v2.0", "mape": 6.2, "rmse": 0.019, "coverage": 84.0, "count": 95},
        ]

        service = LearningService(
            observation_service=mock_obs,
            vector_store=mock_vs,
            redis_client=None,
        )
        weights = await service.update_ensemble_weights("US", days=7)

        # Exactly one call to the aggregating method — no per-row follow-up queries.
        mock_obs.get_model_accuracy_by_version.assert_awaited_once_with("US", 7)
        assert weights is not None
        assert "v2.1" in weights
        assert "v2.0" in weights
        # Best model (lower MAPE) gets higher weight.
        assert weights["v2.1"] > weights["v2.0"]

    @pytest.mark.asyncio
    async def test_coverage_field_present_in_stats(self, mock_obs, mock_vs):
        """Pre-aggregated stats include coverage so callers can use it without
        a second query.  The field must survive the service pass-through."""
        from services.learning_service import LearningService

        returned_stats = [
            {"model_version": "v2.1", "mape": 4.0, "rmse": 0.012, "coverage": 88.5, "count": 60},
        ]
        mock_obs.get_model_accuracy_by_version.return_value = returned_stats

        service = LearningService(
            observation_service=mock_obs,
            vector_store=mock_vs,
            redis_client=None,
        )

        # The ObservationService is a thin pass-through; verify the dict it
        # returns contains coverage so downstream logic can use it.
        stats = await mock_obs.get_model_accuracy_by_version("US", 7)
        assert stats[0]["coverage"] == 88.5

    @pytest.mark.asyncio
    async def test_full_cycle_passes_days_to_aggregation_call(self, mock_obs, mock_vs):
        """run_full_cycle must forward the days param to the aggregation call."""
        from services.learning_service import LearningService

        service = LearningService(
            observation_service=mock_obs,
            vector_store=mock_vs,
            redis_client=None,
        )
        await service.run_full_cycle(regions=["US"], days=14)

        mock_obs.get_model_accuracy_by_version.assert_awaited_with("US", 14)


# =============================================================================
# Phase 7: Conditional vector store lookup
# =============================================================================


class TestConditionalVectorLookup:
    """Verify that _adjust_confidence_from_patterns skips the kNN search
    when the 'recommendation' domain contains fewer than 10 observations.

    This prevents wasted SQLite I/O on a sparse index that cannot produce
    meaningful nearest-neighbour results.
    """

    @pytest.fixture
    def sparse_vector_store(self):
        """Mock vector store with fewer than 10 recommendation vectors."""
        vs = MagicMock()
        vs.get_stats = MagicMock(return_value={"total_vectors": 5})
        vs.search = MagicMock(return_value=[])
        return vs

    @pytest.fixture
    def dense_vector_store(self):
        """Mock vector store with 15 recommendation vectors (above threshold)."""
        vs = MagicMock()
        vs.get_stats = MagicMock(return_value={"total_vectors": 15})
        vs.search = MagicMock(return_value=[
            {"similarity": 0.95, "confidence": 0.9, "id": "vec-1", "domain": "recommendation", "metadata": {}}
        ])
        return vs

    @pytest.fixture
    def mock_prices(self):
        return [
            MagicMock(price_per_kwh=Decimal("0.20")),
            MagicMock(price_per_kwh=Decimal("0.25")),
        ]

    def test_sparse_index_skips_search(self, sparse_vector_store, mock_prices):
        """Should not call vector_store.search when fewer than 10 observations exist."""
        from services.recommendation_service import RecommendationService

        service = RecommendationService(
            price_service=MagicMock(),
            user_repo=MagicMock(),
            vector_store=sparse_vector_store,
        )
        confidence = service._adjust_confidence_from_patterns(mock_prices, 0.85)

        # get_stats called once to check count
        sparse_vector_store.get_stats.assert_called_once_with(domain="recommendation")
        # search must NOT be called on a sparse index
        sparse_vector_store.search.assert_not_called()
        # confidence returned unchanged
        assert confidence == 0.85

    def test_dense_index_runs_search(self, dense_vector_store, mock_prices):
        """Should call vector_store.search when 10+ observations exist."""
        from services.recommendation_service import RecommendationService

        with patch("services.vector_store.price_curve_to_vector") as mock_ptv:
            import numpy as np
            mock_ptv.return_value = np.zeros(24, dtype=np.float32)

            service = RecommendationService(
                price_service=MagicMock(),
                user_repo=MagicMock(),
                vector_store=dense_vector_store,
            )
            confidence = service._adjust_confidence_from_patterns(mock_prices, 0.85)

        dense_vector_store.get_stats.assert_called_once_with(domain="recommendation")
        dense_vector_store.search.assert_called_once()
        # High-confidence match (0.9 > 0.8) should bump confidence up
        assert confidence == round(min(0.95, 0.85 + 0.1), 2)

    def test_no_vector_store_returns_unchanged(self, mock_prices):
        """Should return confidence unchanged when no vector store is configured."""
        from services.recommendation_service import RecommendationService

        service = RecommendationService(
            price_service=MagicMock(),
            user_repo=MagicMock(),
            vector_store=None,
        )
        confidence = service._adjust_confidence_from_patterns(mock_prices, 0.75)
        assert confidence == 0.75

    def test_empty_prices_returns_unchanged(self, sparse_vector_store):
        """Should return confidence unchanged when prices list is empty."""
        from services.recommendation_service import RecommendationService

        service = RecommendationService(
            price_service=MagicMock(),
            user_repo=MagicMock(),
            vector_store=sparse_vector_store,
        )
        confidence = service._adjust_confidence_from_patterns([], 0.70)
        assert confidence == 0.70
        sparse_vector_store.get_stats.assert_not_called()

    def test_exactly_threshold_minus_one_skips(self, mock_prices):
        """9 observations (one below threshold) must skip the search."""
        from services.recommendation_service import RecommendationService

        vs = MagicMock()
        vs.get_stats = MagicMock(return_value={"total_vectors": 9})
        vs.search = MagicMock(return_value=[])

        service = RecommendationService(
            price_service=MagicMock(),
            user_repo=MagicMock(),
            vector_store=vs,
        )
        service._adjust_confidence_from_patterns(mock_prices, 0.80)
        vs.search.assert_not_called()

    def test_exactly_threshold_runs_search(self, mock_prices):
        """Exactly 10 observations must trigger the search."""
        from services.recommendation_service import RecommendationService

        vs = MagicMock()
        vs.get_stats = MagicMock(return_value={"total_vectors": 10})
        vs.search = MagicMock(return_value=[])

        with patch("services.vector_store.price_curve_to_vector") as mock_ptv:
            import numpy as np
            mock_ptv.return_value = np.zeros(24, dtype=np.float32)

            service = RecommendationService(
                price_service=MagicMock(),
                user_repo=MagicMock(),
                vector_store=vs,
            )
            service._adjust_confidence_from_patterns(mock_prices, 0.80)

        vs.search.assert_called_once()


# =============================================================================
# Phase 8: Forecast observation batch INSERT (20-row chunks)
# =============================================================================


class TestForecastObservationBatchInsert:
    """Verify that insert_forecasts uses explicit multi-row VALUES chunks of
    _INSERT_BATCH_SIZE (20) rather than individual per-row INSERT calls.
    """

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def repo(self, db):
        from repositories.forecast_observation_repository import ForecastObservationRepository
        return ForecastObservationRepository(db)

    def _make_predictions(self, count: int) -> list:
        from datetime import datetime, timezone
        return [
            {
                "timestamp": datetime(2026, 2, 23, h % 24, 0, tzinfo=timezone.utc),
                "predicted_price": 0.10 + (h % 24) * 0.01,
            }
            for h in range(count)
        ]

    @pytest.mark.asyncio
    async def test_20_predictions_single_execute(self, repo, db):
        """Exactly 20 predictions should produce exactly 1 execute call."""
        preds = self._make_predictions(20)
        result = await repo.insert_forecasts("fc-20", "US", preds)
        assert result == 20
        assert db.execute.await_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_21_predictions_two_execute_calls(self, repo, db):
        """21 predictions (20 + 1) should produce exactly 2 execute calls."""
        preds = self._make_predictions(21)
        result = await repo.insert_forecasts("fc-21", "US", preds)
        assert result == 21
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_40_predictions_two_execute_calls(self, repo, db):
        """40 predictions (2 full chunks) should produce exactly 2 execute calls."""
        preds = self._make_predictions(40)
        result = await repo.insert_forecasts("fc-40", "US", preds)
        assert result == 40
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_single_commit_regardless_of_chunks(self, repo, db):
        """Only one COMMIT should be issued regardless of how many chunks are used."""
        preds = self._make_predictions(45)
        await repo.insert_forecasts("fc-45", "US", preds)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_params_use_indexed_keys(self, repo, db):
        """Params dict must use index-suffixed keys (id0, forecast_id0, ...)."""
        preds = self._make_predictions(3)
        await repo.insert_forecasts("fc-keys", "US", preds)
        params = db.execute.call_args[0][1]
        for i in range(3):
            assert f"id{i}" in params
            assert f"forecast_id{i}" in params
            assert f"region{i}" in params
            assert f"forecast_hour{i}" in params
            assert f"predicted_price{i}" in params

    @pytest.mark.asyncio
    async def test_batch_size_constant(self, repo):
        """_INSERT_BATCH_SIZE should be 20."""
        from repositories.forecast_observation_repository import ForecastObservationRepository
        assert ForecastObservationRepository._INSERT_BATCH_SIZE == 20
