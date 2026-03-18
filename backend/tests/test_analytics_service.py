"""
Tests for AnalyticsService

Covers all public methods:
- calculate_average_price: normal case, no data
- calculate_volatility: normal case, single price
- get_price_trend: increasing / decreasing / stable directions, cache hit
- get_peak_hours_analysis: normal case, no data, cache hit
- get_supplier_comparison_analytics: normal case, cache hit
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

# =============================================================================
# HELPERS
# =============================================================================


def _make_price(price_per_kwh: float, hour: int = 0):
    """Create a minimal Price-like mock with price_per_kwh and timestamp."""
    p = MagicMock()
    p.price_per_kwh = Decimal(str(price_per_kwh))
    p.timestamp = datetime(2026, 2, 24, hour, 0, tzinfo=UTC)
    return p


def _make_hourly_row(hour: int, avg_price: float, count: int = 10):
    """Create a dict that matches the shape returned by get_hourly_price_averages."""
    return {
        "hour": hour,
        "avg_price": Decimal(str(avg_price)),
        "count": count,
    }


def _make_supplier_row(
    supplier: str,
    avg_price: float,
    min_price: float,
    max_price: float,
    volatility: float,
    count: int = 20,
):
    return {
        "supplier": supplier,
        "avg_price": Decimal(str(avg_price)),
        "min_price": Decimal(str(min_price)),
        "max_price": Decimal(str(max_price)),
        "volatility": Decimal(str(volatility)),
        "count": count,
    }


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_repo():
    """Mock PriceRepository with relevant async methods pre-wired."""
    repo = AsyncMock()
    repo.get_historical_prices = AsyncMock(return_value=[])
    repo.get_hourly_price_averages = AsyncMock(return_value=[])
    repo.get_supplier_price_stats = AsyncMock(return_value=[])
    repo.get_price_statistics_with_stddev = AsyncMock(
        return_value={
            "min_price": None,
            "max_price": None,
            "avg_price": None,
            "stddev_price": None,
            "count": 0,
            "period_days": 7,
            "utility_type": "electricity",
        }
    )
    return repo


@pytest.fixture
def mock_cache():
    """Mock Redis-like cache that returns None on get by default."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=1)
    # nx=True SET for lock acquisition — returns truthy to signal lock acquired
    cache.set.return_value = True
    return cache


@pytest.fixture
def service(mock_repo):
    """AnalyticsService without cache."""
    from services.analytics_service import AnalyticsService

    return AnalyticsService(mock_repo)


@pytest.fixture
def cached_service(mock_repo, mock_cache):
    """AnalyticsService with mock cache."""
    from services.analytics_service import AnalyticsService

    return AnalyticsService(mock_repo, cache=mock_cache)


# =============================================================================
# TestCalculateAveragePrice
# =============================================================================


class TestCalculateAveragePrice:
    """Tests for AnalyticsService.calculate_average_price"""

    @pytest.mark.asyncio
    async def test_calculate_average_price(self, service, mock_repo):
        """Average price delegates to SQL and returns expected Decimal."""
        from models.price import PriceRegion

        mock_repo.get_price_statistics_with_stddev.return_value = {
            "min_price": Decimal("0.2000"),
            "max_price": Decimal("0.3000"),
            "avg_price": Decimal("0.2500"),
            "stddev_price": Decimal("0.0500"),
            "count": 3,
            "period_days": 7,
            "utility_type": "electricity",
        }

        avg = await service.calculate_average_price(PriceRegion.US_CT, days=7)

        assert avg == Decimal("0.2500")

    @pytest.mark.asyncio
    async def test_calculate_average_price_no_data(self, service, mock_repo):
        """Returns Decimal('0') when repository returns no prices."""
        from models.price import PriceRegion

        mock_repo.get_price_statistics_with_stddev.return_value = {
            "min_price": None,
            "max_price": None,
            "avg_price": None,
            "stddev_price": None,
            "count": 0,
            "period_days": 7,
            "utility_type": "electricity",
        }

        avg = await service.calculate_average_price(PriceRegion.US_CT, days=7)

        assert avg == Decimal("0")


# =============================================================================
# TestCalculateVolatility
# =============================================================================


class TestCalculateVolatility:
    """Tests for AnalyticsService.calculate_volatility"""

    @pytest.mark.asyncio
    async def test_calculate_volatility(self, service, mock_repo):
        """Standard deviation delegates to SQL STDDEV_SAMP and is non-zero."""
        from models.price import PriceRegion

        mock_repo.get_price_statistics_with_stddev.return_value = {
            "min_price": Decimal("0.2000"),
            "max_price": Decimal("0.3600"),
            "avg_price": Decimal("0.2800"),
            "stddev_price": Decimal("0.0800"),
            "count": 3,
            "period_days": 7,
            "utility_type": "electricity",
        }

        vol = await service.calculate_volatility(PriceRegion.US_CT, days=7)

        assert vol > Decimal("0")
        assert vol == Decimal("0.0800")

    @pytest.mark.asyncio
    async def test_calculate_volatility_single_price(self, service, mock_repo):
        """Single price point — count < 2 guard returns Decimal('0')."""
        from models.price import PriceRegion

        mock_repo.get_price_statistics_with_stddev.return_value = {
            "min_price": Decimal("0.2800"),
            "max_price": Decimal("0.2800"),
            "avg_price": Decimal("0.2800"),
            "stddev_price": None,
            "count": 1,
            "period_days": 7,
            "utility_type": "electricity",
        }

        vol = await service.calculate_volatility(PriceRegion.US_CT, days=7)

        assert vol == Decimal("0")


# =============================================================================
# TestGetPriceTrend
# =============================================================================


class TestGetPriceTrend:
    """Tests for AnalyticsService.get_price_trend"""

    @pytest.mark.asyncio
    async def test_get_price_trend_increasing(self, service, mock_repo):
        """When last-third avg > first-third avg by >5%, direction='increasing'."""
        from models.price import PriceRegion

        # SQL aggregate returns first_third_avg=0.20, last_third_avg=0.24 → +20%
        mock_repo.get_price_trend_aggregates.return_value = {
            "first_third_avg": Decimal("0.20"),
            "last_third_avg": Decimal("0.24"),
            "total_count": 9,
        }

        result = await service.get_price_trend(PriceRegion.US_CT, days=7)

        assert result["direction"] == "increasing"
        assert result["change_percent"] > Decimal("5")

    @pytest.mark.asyncio
    async def test_get_price_trend_decreasing(self, service, mock_repo):
        """When last-third avg < first-third avg by >5%, direction='decreasing'."""
        from models.price import PriceRegion

        mock_repo.get_price_trend_aggregates.return_value = {
            "first_third_avg": Decimal("0.30"),
            "last_third_avg": Decimal("0.22"),
            "total_count": 9,
        }

        result = await service.get_price_trend(PriceRegion.US_CT, days=7)

        assert result["direction"] == "decreasing"
        assert result["change_percent"] < Decimal("-5")

    @pytest.mark.asyncio
    async def test_get_price_trend_stable(self, service, mock_repo):
        """When change is within ±5%, direction='stable'."""
        from models.price import PriceRegion

        mock_repo.get_price_trend_aggregates.return_value = {
            "first_third_avg": Decimal("0.25"),
            "last_third_avg": Decimal("0.25"),
            "total_count": 9,
        }

        result = await service.get_price_trend(PriceRegion.US_CT, days=7)

        assert result["direction"] == "stable"

    @pytest.mark.asyncio
    async def test_get_price_trend_insufficient_data(self, service, mock_repo):
        """When fewer than 2 data points, return stable with zeros."""
        from models.price import PriceRegion

        mock_repo.get_price_trend_aggregates.return_value = {
            "first_third_avg": None,
            "last_third_avg": None,
            "total_count": 0,
        }

        result = await service.get_price_trend(PriceRegion.US_CT, days=7)

        assert result["direction"] == "stable"
        assert result["data_points"] == 0

    @pytest.mark.asyncio
    async def test_get_price_trend_cached(self, cached_service, mock_repo, mock_cache):
        """Cache hit returns stored data without touching the repository."""
        from models.price import PriceRegion

        cached_payload = json.dumps(
            {
                "direction": "increasing",
                "change_percent": "7.50",
                "start_price": "0.2000",
                "end_price": "0.2150",
                "data_points": 20,
            }
        )
        mock_cache.get.return_value = cached_payload

        result = await cached_service.get_price_trend(PriceRegion.US_CT, days=7)

        assert result["direction"] == "increasing"
        assert result["change_percent"] == Decimal("7.50")
        mock_repo.get_price_trend_aggregates.assert_not_awaited()


# =============================================================================
# TestGetPeakHoursAnalysis
# =============================================================================


class TestGetPeakHoursAnalysis:
    """Tests for AnalyticsService.get_peak_hours_analysis"""

    @pytest.mark.asyncio
    async def test_get_peak_hours_analysis(self, service, mock_repo):
        """Normal case returns peak_hours, off_peak_hours, average_by_hour."""
        from models.price import PriceRegion

        # Hour 17 is the expensive peak; hour 3 is off-peak
        rows = [
            _make_hourly_row(h, avg, count=10)
            for h, avg in [
                (0, 0.20),
                (1, 0.20),
                (2, 0.20),
                (3, 0.15),  # off-peak at 3
                (4, 0.20),
                (5, 0.20),
                (6, 0.20),
                (7, 0.20),
                (8, 0.20),
                (9, 0.20),
                (10, 0.20),
                (11, 0.20),
                (12, 0.20),
                (13, 0.20),
                (14, 0.20),
                (15, 0.20),
                (16, 0.20),
                (17, 0.28),
                (18, 0.28),  # peaks at 17/18
                (19, 0.20),
                (20, 0.20),
                (21, 0.20),
                (22, 0.20),
                (23, 0.20),
            ]
        ]
        mock_repo.get_hourly_price_averages.return_value = rows

        result = await service.get_peak_hours_analysis(PriceRegion.US_CT, days=7)

        assert "peak_hours" in result
        assert "off_peak_hours" in result
        assert "average_by_hour" in result
        assert 17 in result["peak_hours"]
        assert 3 in result["off_peak_hours"]

    @pytest.mark.asyncio
    async def test_get_peak_hours_analysis_no_data(self, service, mock_repo):
        """Empty hourly rows → returns minimal dict with empty lists."""
        from models.price import PriceRegion

        mock_repo.get_hourly_price_averages.return_value = []

        result = await service.get_peak_hours_analysis(PriceRegion.US_CT, days=7)

        assert result["peak_hours"] == []
        assert result["off_peak_hours"] == []
        assert result["average_by_hour"] == {}


# =============================================================================
# TestGetSupplierComparisonAnalytics
# =============================================================================


class TestGetSupplierComparisonAnalytics:
    """Tests for AnalyticsService.get_supplier_comparison_analytics"""

    @pytest.mark.asyncio
    async def test_get_supplier_comparison_analytics(self, service, mock_repo):
        """Normal case builds supplier stats and identifies cheapest/most_stable."""
        from models.price import PriceRegion

        rows = [
            _make_supplier_row("Eversource", 0.26, 0.22, 0.32, 0.03, 50),
            _make_supplier_row("United Illuminating", 0.24, 0.20, 0.30, 0.02, 40),
        ]
        mock_repo.get_supplier_price_stats.return_value = rows

        result = await service.get_supplier_comparison_analytics(PriceRegion.US_CT, days=30)

        assert "suppliers" in result
        assert len(result["suppliers"]) == 2
        # First row is cheapest_supplier (first in list)
        assert result["cheapest_supplier"] == "Eversource"
        # Lowest volatility is United Illuminating (0.02)
        assert result["most_stable"] == "United Illuminating"

    @pytest.mark.asyncio
    async def test_get_supplier_comparison_cached(self, cached_service, mock_repo, mock_cache):
        """Cache hit returns stored payload without querying repository."""
        from models.price import PriceRegion

        cached_payload = json.dumps(
            {
                "region": "us_ct",
                "period_days": 30,
                "suppliers": [
                    {
                        "supplier": "Eversource",
                        "average_price": "0.26",
                        "min_price": "0.22",
                        "max_price": "0.32",
                        "volatility": "0.03",
                        "data_points": 50,
                    }
                ],
                "cheapest_supplier": "Eversource",
                "most_stable": "Eversource",
            }
        )
        mock_cache.get.return_value = cached_payload

        result = await cached_service.get_supplier_comparison_analytics(PriceRegion.US_CT, days=30)

        assert result["cheapest_supplier"] == "Eversource"
        assert result["suppliers"][0]["average_price"] == Decimal("0.26")
        mock_repo.get_supplier_price_stats.assert_not_awaited()


# =============================================================================
# TestAcquireCacheLock — thundering herd / fail-closed
# =============================================================================


class TestAcquireCacheLock:
    """Tests for AnalyticsService._acquire_cache_lock.

    The lock must be fail-closed: when Redis raises an exception, the method
    must return False (lock appears held) so that concurrent callers do NOT
    proceed to query the database simultaneously.  Returning True on error
    (fail-open) would allow every waiting request to hammer the DB during a
    Redis outage, causing a thundering herd.
    """

    @pytest.mark.asyncio
    async def test_lock_acquired_when_redis_returns_truthy(self, mock_repo, mock_cache):
        """SET NX returns truthy → lock acquired (True)."""
        from services.analytics_service import AnalyticsService

        mock_cache.set = AsyncMock(return_value=True)
        svc = AnalyticsService(mock_repo, cache=mock_cache)

        acquired = await svc._acquire_cache_lock("test:key")
        assert acquired is True

    @pytest.mark.asyncio
    async def test_lock_not_acquired_when_redis_returns_falsy(self, mock_repo, mock_cache):
        """SET NX returns falsy (lock already held) → returns False."""
        from services.analytics_service import AnalyticsService

        mock_cache.set = AsyncMock(return_value=None)
        svc = AnalyticsService(mock_repo, cache=mock_cache)

        acquired = await svc._acquire_cache_lock("test:key")
        assert acquired is False

    @pytest.mark.asyncio
    async def test_lock_fail_closed_on_redis_exception(self, mock_repo, mock_cache):
        """Redis error → returns False (fail-closed, NOT fail-open).

        Returning True on error would let every concurrent request proceed
        to the database (thundering herd).  Returning False prevents this
        by making the lock appear held to all callers.
        """
        from services.analytics_service import AnalyticsService

        mock_cache.set = AsyncMock(side_effect=ConnectionError("Redis down"))
        svc = AnalyticsService(mock_repo, cache=mock_cache)

        acquired = await svc._acquire_cache_lock("test:key")
        assert acquired is False, (
            "_acquire_cache_lock must return False (fail-closed) on Redis error "
            "to prevent concurrent requests from stampeding the database."
        )

    @pytest.mark.asyncio
    async def test_lock_returns_true_when_no_cache_configured(self, mock_repo):
        """Without a cache the lock is trivially acquired (single process)."""
        from services.analytics_service import AnalyticsService

        svc = AnalyticsService(mock_repo, cache=None)
        acquired = await svc._acquire_cache_lock("test:key")
        assert acquired is True
