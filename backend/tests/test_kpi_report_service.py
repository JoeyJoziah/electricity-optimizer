"""
Tests for KPIReportService (backend/services/kpi_report_service.py)

Covers:
- aggregate_metrics happy path
- empty tables return zeros
- subscription_breakdown correctness
- estimated_mrr calculation
- weather_freshness returns None when no data
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.kpi_report_service import KPIReportService

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def kpi_service(mock_db):
    """KPIReportService with mocked DB."""
    return KPIReportService(mock_db)


# =============================================================================
# Helper: create scalar result mock
# =============================================================================


def _scalar_result(value):
    """Return a mock result whose .scalar() returns `value`."""
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _rows_result(rows):
    """Return a mock result whose .mappings().all() returns row dicts."""
    r = MagicMock()
    r.mappings.return_value.all.return_value = rows
    return r


# =============================================================================
# aggregate_metrics — happy path
# =============================================================================


class TestAggregateMetrics:
    @pytest.mark.asyncio
    async def test_happy_path(self, mock_db):
        """aggregate_metrics should return all expected keys."""
        mock_db.execute = AsyncMock(
            side_effect=[
                _scalar_result(42),  # active_users_7d
                _scalar_result(100),  # total_users
                _scalar_result(5000),  # prices_tracked
                _scalar_result(15),  # alerts_sent_today
                _rows_result(
                    [  # connections status
                        {"status": "active", "cnt": 10},
                        {"status": "error", "cnt": 2},
                    ]
                ),
                _rows_result(
                    [  # subscription breakdown
                        {"tier": "free", "cnt": 80},
                        {"tier": "pro", "cnt": 15},
                        {"tier": "business", "cnt": 5},
                    ]
                ),
                _scalar_result(6.5),  # weather freshness
            ]
        )

        service = KPIReportService(mock_db)
        metrics = await service.aggregate_metrics()

        assert metrics["active_users_7d"] == 42
        assert metrics["total_users"] == 100
        assert metrics["prices_tracked"] == 5000
        assert metrics["alerts_sent_today"] == 15
        assert metrics["connections_active"] == {"active": 10, "error": 2}
        assert metrics["subscription_breakdown"]["pro"] == 15
        assert metrics["subscription_breakdown"]["business"] == 5
        assert metrics["estimated_mrr"] == round(15 * 4.99 + 5 * 14.99, 2)
        assert metrics["weather_freshness_hours"] == 6.5


# =============================================================================
# Empty tables
# =============================================================================


class TestEmptyTables:
    @pytest.mark.asyncio
    async def test_returns_zeros(self, mock_db):
        """All zeros when tables are empty."""
        mock_db.execute = AsyncMock(
            side_effect=[
                _scalar_result(0),  # active_users_7d
                _scalar_result(0),  # total_users
                _scalar_result(0),  # prices_tracked
                _scalar_result(0),  # alerts_sent_today
                _rows_result([]),  # connections
                _rows_result([]),  # subscriptions
                _scalar_result(None),  # weather freshness
            ]
        )

        service = KPIReportService(mock_db)
        metrics = await service.aggregate_metrics()

        assert metrics["active_users_7d"] == 0
        assert metrics["total_users"] == 0
        assert metrics["prices_tracked"] == 0
        assert metrics["alerts_sent_today"] == 0
        assert metrics["connections_active"] == {}
        assert metrics["subscription_breakdown"] == {}
        assert metrics["estimated_mrr"] == 0.0
        assert metrics["weather_freshness_hours"] is None


# =============================================================================
# subscription_breakdown
# =============================================================================


class TestSubscriptionBreakdown:
    @pytest.mark.asyncio
    async def test_groups_correctly(self, mock_db):
        """Subscription breakdown should group by tier."""
        mock_db.execute = AsyncMock(
            side_effect=[
                _scalar_result(0),
                _scalar_result(0),
                _scalar_result(0),
                _scalar_result(0),
                _rows_result([]),
                _rows_result(
                    [
                        {"tier": "free", "cnt": 50},
                        {"tier": "pro", "cnt": 25},
                    ]
                ),
                _scalar_result(None),
            ]
        )

        service = KPIReportService(mock_db)
        metrics = await service.aggregate_metrics()

        assert metrics["subscription_breakdown"]["free"] == 50
        assert metrics["subscription_breakdown"]["pro"] == 25
        assert "business" not in metrics["subscription_breakdown"]


# =============================================================================
# estimated_mrr
# =============================================================================


class TestEstimatedMRR:
    def test_calculation(self):
        """MRR = pro * $4.99 + business * $14.99."""
        mrr = KPIReportService._calculate_mrr({"pro": 10, "business": 2})
        assert mrr == round(10 * 4.99 + 2 * 14.99, 2)

    def test_zero_when_all_free(self):
        """MRR should be 0 when everyone is on free."""
        mrr = KPIReportService._calculate_mrr({"free": 100})
        assert mrr == 0.0

    def test_empty_dict(self):
        """MRR should be 0 with empty dict."""
        mrr = KPIReportService._calculate_mrr({})
        assert mrr == 0.0


# =============================================================================
# weather_freshness
# =============================================================================


class TestWeatherFreshness:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_data(self, mock_db):
        """Should return None when no price data exists."""
        mock_db.execute = AsyncMock(
            side_effect=[
                _scalar_result(0),
                _scalar_result(0),
                _scalar_result(0),
                _scalar_result(0),
                _rows_result([]),
                _rows_result([]),
                _scalar_result(None),
            ]
        )

        service = KPIReportService(mock_db)
        metrics = await service.aggregate_metrics()

        assert metrics["weather_freshness_hours"] is None
