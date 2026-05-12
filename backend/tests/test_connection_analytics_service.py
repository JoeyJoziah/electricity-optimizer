"""Tests for ConnectionAnalyticsService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.connection_analytics_service import ConnectionAnalyticsService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db():
    return AsyncMock()


def _make_row(**kwargs):
    row = MagicMock()
    row.__getitem__ = lambda self, key: kwargs[key]
    row.get = lambda key, default=None: kwargs.get(key, default)
    return row


def _mappings_first(row):
    r = MagicMock()
    r.mappings.return_value.first.return_value = row
    return r


def _mappings_all(rows):
    r = MagicMock()
    r.mappings.return_value.all.return_value = rows
    return r


# ---------------------------------------------------------------------------
# get_rate_comparison
# ---------------------------------------------------------------------------


class TestGetRateComparison:
    @pytest.mark.asyncio
    async def test_no_user_rate_returns_has_data_false(self):
        db = _make_db()
        db.execute.return_value = _mappings_first(None)
        svc = ConnectionAnalyticsService(db)
        result = await svc.get_rate_comparison("uid-1")
        assert result["has_data"] is False
        assert "No extracted rates" in result["message"]

    @pytest.mark.asyncio
    async def test_returns_has_data_true_with_rate_fields(self):
        db = _make_db()
        user_row = _make_row(
            rate_per_kwh=0.18,
            supplier_name="GridCo",
            effective_date=datetime(2026, 5, 1, tzinfo=UTC),
            connection_id="cid-1",
            connection_type="utility",
            user_region="US_CT",
        )
        market_row = _make_row(avg_price=0.16, min_price=0.14, max_price=0.20, sample_count=50)
        db.execute.side_effect = [_mappings_first(user_row), _mappings_first(market_row)]
        svc = ConnectionAnalyticsService(db)
        result = await svc.get_rate_comparison("uid-1")

        assert result["has_data"] is True
        assert result["user_rate"] == 0.18
        assert result["supplier"] == "GridCo"
        assert result["market_average"] == 0.16
        assert result["market_min"] == 0.14
        assert result["region"] == "US_CT"
        assert result["is_above_average"] is True
        assert result["sample_count"] == 50

    @pytest.mark.asyncio
    async def test_delta_and_pct_diff_computed_correctly(self):
        db = _make_db()
        user_row = _make_row(
            rate_per_kwh=0.20,
            supplier_name="ExpensiveCo",
            effective_date=datetime(2026, 5, 1, tzinfo=UTC),
            connection_id="cid-1",
            connection_type="utility",
            user_region="US_CT",
        )
        market_row = _make_row(avg_price=0.16, min_price=0.12, max_price=0.22, sample_count=10)
        db.execute.side_effect = [_mappings_first(user_row), _mappings_first(market_row)]
        svc = ConnectionAnalyticsService(db)
        result = await svc.get_rate_comparison("uid-1")
        assert result["delta"] == round(0.20 - 0.16, 4)
        expected_pct = round((0.04 / 0.16) * 100, 2)
        assert result["percentage_difference"] == expected_pct

    @pytest.mark.asyncio
    async def test_market_fallback_when_no_market_data(self):
        db = _make_db()
        user_row = _make_row(
            rate_per_kwh=0.15,
            supplier_name="UtilCo",
            effective_date=datetime(2026, 5, 1, tzinfo=UTC),
            connection_id="cid-1",
            connection_type="utility",
            user_region="US_CT",
        )
        # no market data row
        market_row = _make_row(avg_price=None, min_price=None, max_price=None, sample_count=0)
        db.execute.side_effect = [_mappings_first(user_row), _mappings_first(market_row)]
        svc = ConnectionAnalyticsService(db)
        result = await svc.get_rate_comparison("uid-1")
        # falls back to user_rate for all market values
        assert result["market_average"] == 0.15
        assert result["delta"] == 0.0
        assert result["is_above_average"] is False


# ---------------------------------------------------------------------------
# get_savings_estimate
# ---------------------------------------------------------------------------


class TestGetSavingsEstimate:
    @pytest.mark.asyncio
    async def test_returns_has_data_false_when_no_rate_data(self):
        db = _make_db()
        db.execute.return_value = _mappings_first(None)
        svc = ConnectionAnalyticsService(db)
        result = await svc.get_savings_estimate("uid-1")
        assert result["has_data"] is False
        assert "No rate data" in result["message"]

    @pytest.mark.asyncio
    async def test_computes_savings_when_user_above_market(self):
        db = _make_db()
        user_row = _make_row(
            rate_per_kwh=0.20,
            supplier_name="GridCo",
            effective_date=datetime(2026, 5, 1, tzinfo=UTC),
            connection_id="cid-1",
            connection_type="utility",
            user_region="US_CT",
        )
        market_row = _make_row(avg_price=0.16, min_price=0.14, max_price=0.22, sample_count=30)
        db.execute.side_effect = [_mappings_first(user_row), _mappings_first(market_row)]
        svc = ConnectionAnalyticsService(db)
        result = await svc.get_savings_estimate("uid-1", monthly_kwh=1000)

        annual_kwh = 1000 * 12
        expected_vs_best = round((0.20 - 0.14) * annual_kwh, 2)
        expected_vs_avg = round((0.20 - 0.16) * annual_kwh, 2)
        assert result["has_data"] is True
        assert result["annual_kwh"] == annual_kwh
        assert result["estimated_annual_savings_vs_best"] == expected_vs_best
        assert result["estimated_annual_savings_vs_average"] == expected_vs_avg

    @pytest.mark.asyncio
    async def test_savings_is_zero_when_user_below_market(self):
        db = _make_db()
        user_row = _make_row(
            rate_per_kwh=0.10,
            supplier_name="CheapCo",
            effective_date=datetime(2026, 5, 1, tzinfo=UTC),
            connection_id="cid-1",
            connection_type="utility",
            user_region="US_CT",
        )
        market_row = _make_row(avg_price=0.16, min_price=0.14, max_price=0.22, sample_count=30)
        db.execute.side_effect = [_mappings_first(user_row), _mappings_first(market_row)]
        svc = ConnectionAnalyticsService(db)
        result = await svc.get_savings_estimate("uid-1")
        assert result["estimated_annual_savings_vs_best"] == 0
        assert result["estimated_annual_savings_vs_average"] == 0


# ---------------------------------------------------------------------------
# check_stale_connections
# ---------------------------------------------------------------------------


class TestCheckStaleConnections:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_stale_connections(self):
        db = _make_db()
        db.execute.return_value = _mappings_all([])
        svc = ConnectionAnalyticsService(db)
        result = await svc.check_stale_connections("uid-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_formatted_rows(self):
        db = _make_db()
        last_scan = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        row = _make_row(
            id="cid-1",
            connection_type="email",
            label="My Home",
            email_provider="gmail",
            last_scan_at=last_scan,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        db.execute.return_value = _mappings_all([row])
        svc = ConnectionAnalyticsService(db)
        result = await svc.check_stale_connections("uid-1")
        assert len(result) == 1
        item = result[0]
        assert item["connection_id"] == "cid-1"
        assert item["connection_type"] == "email"
        assert item["last_scan_at"] == last_scan.isoformat()
        assert isinstance(item["days_since_sync"], int)

    @pytest.mark.asyncio
    async def test_null_last_scan_at_uses_created_at(self):
        db = _make_db()
        created = datetime(2026, 1, 1, tzinfo=UTC)
        row = _make_row(
            id="cid-2",
            connection_type="utility",
            label="Work",
            email_provider=None,
            last_scan_at=None,
            created_at=created,
        )
        db.execute.return_value = _mappings_all([row])
        svc = ConnectionAnalyticsService(db)
        result = await svc.check_stale_connections("uid-1")
        item = result[0]
        assert item["last_scan_at"] is None
        assert item["days_since_sync"] is not None
        assert item["days_since_sync"] > 0


# ---------------------------------------------------------------------------
# detect_rate_changes
# ---------------------------------------------------------------------------


class TestDetectRateChanges:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_rows(self):
        db = _make_db()
        db.execute.return_value = _mappings_all([])
        svc = ConnectionAnalyticsService(db)
        result = await svc.detect_rate_changes("uid-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_skips_rows_without_prev_rate(self):
        db = _make_db()
        row = _make_row(
            rate_per_kwh=0.18,
            prev_rate=None,
            supplier_name="GridCo",
            effective_date=datetime(2026, 5, 1, tzinfo=UTC),
            connection_id="cid-1",
            label="Home",
        )
        db.execute.return_value = _mappings_all([row])
        svc = ConnectionAnalyticsService(db)
        result = await svc.detect_rate_changes("uid-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_detects_increase_above_threshold(self):
        db = _make_db()
        row = _make_row(
            rate_per_kwh=0.20,
            prev_rate=0.16,
            supplier_name="GridCo",
            effective_date=datetime(2026, 5, 1, tzinfo=UTC),
            connection_id="cid-1",
            label="Home",
        )
        db.execute.return_value = _mappings_all([row])
        svc = ConnectionAnalyticsService(db)
        result = await svc.detect_rate_changes("uid-1", threshold_pct=5.0)
        assert len(result) == 1
        alert = result[0]
        assert alert["direction"] == "increase"
        assert alert["current_rate"] == 0.20
        assert alert["previous_rate"] == 0.16
        # (0.20 - 0.16) / 0.16 * 100 = 25%
        assert alert["change_percentage"] == 25.0

    @pytest.mark.asyncio
    async def test_detects_decrease_above_threshold(self):
        db = _make_db()
        row = _make_row(
            rate_per_kwh=0.12,
            prev_rate=0.16,
            supplier_name="CheapCo",
            effective_date=datetime(2026, 5, 1, tzinfo=UTC),
            connection_id="cid-1",
            label="Home",
        )
        db.execute.return_value = _mappings_all([row])
        svc = ConnectionAnalyticsService(db)
        result = await svc.detect_rate_changes("uid-1", threshold_pct=5.0)
        assert len(result) == 1
        assert result[0]["direction"] == "decrease"

    @pytest.mark.asyncio
    async def test_excludes_change_below_threshold(self):
        db = _make_db()
        # 1% change < 5% threshold
        row = _make_row(
            rate_per_kwh=0.1616,
            prev_rate=0.16,
            supplier_name="GridCo",
            effective_date=datetime(2026, 5, 1, tzinfo=UTC),
            connection_id="cid-1",
            label="Home",
        )
        db.execute.return_value = _mappings_all([row])
        svc = ConnectionAnalyticsService(db)
        result = await svc.detect_rate_changes("uid-1", threshold_pct=5.0)
        assert result == []

    @pytest.mark.asyncio
    async def test_skips_row_when_prev_rate_is_zero(self):
        db = _make_db()
        row = _make_row(
            rate_per_kwh=0.18,
            prev_rate=0.0,
            supplier_name="GridCo",
            effective_date=datetime(2026, 5, 1, tzinfo=UTC),
            connection_id="cid-1",
            label="Home",
        )
        db.execute.return_value = _mappings_all([row])
        svc = ConnectionAnalyticsService(db)
        result = await svc.detect_rate_changes("uid-1")
        assert result == []
