"""
Tests for KPIReportService (backend/services/kpi_report_service.py)

Covers:
- aggregate_metrics happy path (CTE + 2 GROUP BY queries)
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
# Helper: create result mocks
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


def _cte_row_result(row_dict):
    """Return a mock result whose .mappings().one() returns a single row dict.

    Used for the CTE scalar query that returns all 5 metrics in one row.
    """
    r = MagicMock()
    r.mappings.return_value.one.return_value = row_dict
    return r


# =============================================================================
# aggregate_metrics — happy path
# =============================================================================


class TestAggregateMetrics:
    async def test_happy_path(self, mock_db):
        """aggregate_metrics should return all expected keys.

        The CTE query returns all 5 scalar metrics in one row,
        followed by 2 GROUP BY queries for connections and subscriptions.
        """
        mock_db.execute = AsyncMock(
            side_effect=[
                _cte_row_result(
                    {  # CTE scalars (1 query)
                        "active_users_7d": 42,
                        "total_users": 100,
                        "prices_tracked": 5000,
                        "alerts_sent_today": 15,
                        "weather_freshness": 6.5,
                    }
                ),
                _rows_result(
                    [  # connections GROUP BY
                        {"status": "active", "cnt": 10},
                        {"status": "error", "cnt": 2},
                    ]
                ),
                _rows_result(
                    [  # subscriptions GROUP BY
                        {"tier": "free", "cnt": 80},
                        {"tier": "pro", "cnt": 15},
                        {"tier": "business", "cnt": 5},
                    ]
                ),
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
    async def test_returns_zeros(self, mock_db):
        """All zeros when tables are empty."""
        mock_db.execute = AsyncMock(
            side_effect=[
                _cte_row_result(
                    {
                        "active_users_7d": 0,
                        "total_users": 0,
                        "prices_tracked": 0,
                        "alerts_sent_today": 0,
                        "weather_freshness": None,
                    }
                ),
                _rows_result([]),  # connections
                _rows_result([]),  # subscriptions
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
    async def test_groups_correctly(self, mock_db):
        """Subscription breakdown should group by tier."""
        mock_db.execute = AsyncMock(
            side_effect=[
                _cte_row_result(
                    {
                        "active_users_7d": 0,
                        "total_users": 0,
                        "prices_tracked": 0,
                        "alerts_sent_today": 0,
                        "weather_freshness": None,
                    }
                ),
                _rows_result([]),  # connections
                _rows_result(
                    [  # subscriptions
                        {"tier": "free", "cnt": 50},
                        {"tier": "pro", "cnt": 25},
                    ]
                ),
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
    async def test_returns_none_when_no_data(self, mock_db):
        """Should return None when no price data exists."""
        mock_db.execute = AsyncMock(
            side_effect=[
                _cte_row_result(
                    {
                        "active_users_7d": 0,
                        "total_users": 0,
                        "prices_tracked": 0,
                        "alerts_sent_today": 0,
                        "weather_freshness": None,
                    }
                ),
                _rows_result([]),  # connections
                _rows_result([]),  # subscriptions
            ]
        )

        service = KPIReportService(mock_db)
        metrics = await service.aggregate_metrics()

        assert metrics["weather_freshness_hours"] is None
