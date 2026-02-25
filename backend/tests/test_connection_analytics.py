"""
Tests for connection analytics — service layer and API endpoints.

Coverage:
  - ConnectionAnalyticsService.get_rate_comparison — with data, without data
  - ConnectionAnalyticsService.get_rate_history — returns data points, empty case
  - ConnectionAnalyticsService.get_savings_estimate — user above/below market
  - ConnectionAnalyticsService.check_stale_connections — stale detected, no stale
  - ConnectionAnalyticsService.detect_rate_changes — change >5%, no change, skip prev=None
  - GET /connections/analytics/comparison — with/without connection_id filter
  - GET /connections/analytics/history — with/without days param
  - GET /connections/analytics/savings — with monthly_kwh param
  - GET /connections/analytics/health — stale + alerts
  - PATCH /connections/{id} — label update, not found, no fields
  - Paid-tier gate enforcement on analytics endpoints
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Stable test IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "cccccccc-1111-0000-0000-000000000099"
TEST_CONNECTION_ID = str(uuid4())
TEST_CONNECTION_ID_2 = str(uuid4())


# ---------------------------------------------------------------------------
# Helpers shared with connections tests (duplicated here to stay self-contained)
# ---------------------------------------------------------------------------


class _DictRow(dict):
    """Dict subclass that behaves like a SQLAlchemy RowMapping."""


def _row(**kwargs) -> "_DictRow":
    return _DictRow(kwargs)


def _mapping_result(rows: list) -> MagicMock:
    result = MagicMock()
    mock_rows = [_DictRow(r) for r in rows]
    result.mappings.return_value.all.return_value = mock_rows
    result.mappings.return_value.first.return_value = mock_rows[0] if mock_rows else None
    result.fetchone.return_value = mock_rows[0] if mock_rows else None
    return result


def _empty_mapping_result() -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    result.mappings.return_value.first.return_value = None
    result.fetchone.return_value = None
    return result


def _scalar_result(value) -> MagicMock:
    result = MagicMock()
    row = MagicMock()
    row.__getitem__ = lambda self, k: value
    result.fetchone.return_value = row
    result.scalar_one_or_none.return_value = value
    return result


def _session_data(user_id: str = TEST_USER_ID, tier: str = "pro"):
    from auth.neon_auth import SessionData

    sd = SessionData(
        user_id=user_id,
        email=f"{user_id[:8]}@example.com",
        name="Analytics Tester",
        email_verified=True,
        role="user",
    )
    sd._tier = tier
    return sd


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Function-scoped TestClient."""
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_overrides():
    """Clean dependency overrides and reset rate limiter before/after each test."""
    from main import app, _app_rate_limiter

    _app_rate_limiter.reset()
    yield

    for dep in list(app.dependency_overrides.keys()):
        app.dependency_overrides.pop(dep, None)

    _app_rate_limiter.reset()


def _install_auth(tier: str = "pro", user_id: str = TEST_USER_ID):
    """Install auth + DB overrides so require_paid_tier succeeds."""
    from main import app
    from api.dependencies import get_current_user, get_db_session
    from api.v1.connections import require_paid_tier

    session = _session_data(user_id=user_id, tier=tier)
    db = _mock_db()

    if tier in ("pro", "business"):
        app.dependency_overrides[require_paid_tier] = lambda: session
    else:
        app.dependency_overrides[get_current_user] = lambda: session
        db.execute = AsyncMock(return_value=_scalar_result(tier))

    app.dependency_overrides[get_current_user] = lambda: session
    app.dependency_overrides[get_db_session] = lambda: db

    return db


BASE = "/api/v1/connections"


# ===========================================================================
# 1. ConnectionAnalyticsService — unit tests (service layer, no HTTP)
# ===========================================================================


class TestGetRateComparisonService:
    """Unit tests for ConnectionAnalyticsService.get_rate_comparison."""

    @pytest.mark.asyncio
    async def test_get_rate_comparison_with_data(self):
        """Returns full comparison dict when extracted rates exist."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        now = datetime.now(timezone.utc)

        # First call: user's extracted rate
        rate_row = _DictRow({
            "rate_per_kwh": 0.2500,
            "supplier_name": "Eversource",
            "extracted_at": now,
            "connection_id": TEST_CONNECTION_ID,
            "connection_type": "direct",
        })
        rate_result = MagicMock()
        rate_result.mappings.return_value.first.return_value = rate_row

        # Second call: user's region
        region_row = MagicMock()
        region_row.__getitem__ = lambda self, idx: "US_CT"
        region_result = MagicMock()
        region_result.fetchone.return_value = region_row

        # Third call: market stats
        market_row = _DictRow({
            "avg_price": 0.2000,
            "min_price": 0.1500,
            "max_price": 0.2800,
            "sample_count": 42,
        })
        market_result = MagicMock()
        market_result.mappings.return_value.first.return_value = market_row

        db.execute = AsyncMock(side_effect=[rate_result, region_result, market_result])

        svc = ConnectionAnalyticsService(db)
        result = await svc.get_rate_comparison(TEST_USER_ID)

        assert result["has_data"] is True
        assert result["user_rate"] == 0.25
        assert result["supplier"] == "Eversource"
        assert result["market_average"] == 0.2
        assert result["market_min"] == 0.15
        assert result["market_max"] == 0.28
        assert result["delta"] == round(0.25 - 0.20, 4)
        assert result["is_above_average"] is True
        assert result["sample_count"] == 42
        assert result["region"] == "US_CT"

    @pytest.mark.asyncio
    async def test_get_rate_comparison_no_data(self):
        """Returns has_data=False when no extracted rates exist."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        empty_result = _empty_mapping_result()
        db.execute = AsyncMock(return_value=empty_result)

        svc = ConnectionAnalyticsService(db)
        result = await svc.get_rate_comparison(TEST_USER_ID)

        assert result["has_data"] is False
        assert "message" in result

    @pytest.mark.asyncio
    async def test_get_rate_comparison_with_connection_id_filter(self):
        """Query includes connection_id filter when provided."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        empty_result = _empty_mapping_result()
        db.execute = AsyncMock(return_value=empty_result)

        svc = ConnectionAnalyticsService(db)
        await svc.get_rate_comparison(TEST_USER_ID, connection_id=TEST_CONNECTION_ID)

        # Verify the execute was called — the connection_id param should be in the SQL
        call_args = db.execute.call_args_list[0]
        # Second positional arg is params dict
        params = call_args[0][1]
        assert params.get("cid") == TEST_CONNECTION_ID

    @pytest.mark.asyncio
    async def test_get_rate_comparison_below_average(self):
        """User rate below market average: delta is negative, is_above_average=False."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        now = datetime.now(timezone.utc)

        rate_row = _DictRow({
            "rate_per_kwh": 0.1500,
            "supplier_name": "UI",
            "extracted_at": now,
            "connection_id": TEST_CONNECTION_ID,
            "connection_type": "direct",
        })
        rate_result = MagicMock()
        rate_result.mappings.return_value.first.return_value = rate_row

        region_row = MagicMock()
        region_row.__getitem__ = lambda self, idx: "US_CT"
        region_result = MagicMock()
        region_result.fetchone.return_value = region_row

        market_row = _DictRow({
            "avg_price": 0.2000,
            "min_price": 0.1200,
            "max_price": 0.2800,
            "sample_count": 10,
        })
        market_result = MagicMock()
        market_result.mappings.return_value.first.return_value = market_row

        db.execute = AsyncMock(side_effect=[rate_result, region_result, market_result])

        svc = ConnectionAnalyticsService(db)
        result = await svc.get_rate_comparison(TEST_USER_ID)

        assert result["has_data"] is True
        assert result["is_above_average"] is False
        assert result["delta"] < 0


class TestGetRateHistoryService:
    """Unit tests for ConnectionAnalyticsService.get_rate_history."""

    @pytest.mark.asyncio
    async def test_get_rate_history_returns_data_points(self):
        """Returns list of data points from extracted rates."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        now = datetime.now(timezone.utc)

        rows = [
            _DictRow({
                "rate_per_kwh": 0.21,
                "supplier_name": "Eversource",
                "extracted_at": now - timedelta(days=10),
                "billing_period_start": None,
                "billing_period_end": None,
                "connection_id": TEST_CONNECTION_ID,
                "connection_type": "direct",
                "label": "Home",
            }),
            _DictRow({
                "rate_per_kwh": 0.23,
                "supplier_name": "Eversource",
                "extracted_at": now,
                "billing_period_start": None,
                "billing_period_end": None,
                "connection_id": TEST_CONNECTION_ID,
                "connection_type": "direct",
                "label": "Home",
            }),
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        output = await svc.get_rate_history(TEST_USER_ID)

        assert output["total"] == 2
        assert output["days"] == 365
        assert len(output["data_points"]) == 2
        assert output["data_points"][0]["rate"] == 0.21
        assert output["data_points"][1]["rate"] == 0.23

    @pytest.mark.asyncio
    async def test_get_rate_history_empty(self):
        """Returns empty data_points when no history exists."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        output = await svc.get_rate_history(TEST_USER_ID)

        assert output["total"] == 0
        assert output["data_points"] == []

    @pytest.mark.asyncio
    async def test_get_rate_history_custom_days(self):
        """Custom days parameter is passed through."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        output = await svc.get_rate_history(TEST_USER_ID, days=90)

        assert output["days"] == 90
        params = db.execute.call_args[0][1]
        assert params["days"] == 90

    @pytest.mark.asyncio
    async def test_get_rate_history_with_connection_filter(self):
        """Connection ID filter is passed in query params."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        await svc.get_rate_history(TEST_USER_ID, connection_id=TEST_CONNECTION_ID)

        params = db.execute.call_args[0][1]
        assert params.get("cid") == TEST_CONNECTION_ID


class TestGetSavingsEstimateService:
    """Unit tests for ConnectionAnalyticsService.get_savings_estimate."""

    @pytest.mark.asyncio
    async def test_savings_user_above_market(self):
        """User rate above market → positive savings."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        svc = ConnectionAnalyticsService(db)

        # Patch get_rate_comparison to return canned data
        canned_comparison = {
            "has_data": True,
            "user_rate": 0.25,
            "market_min": 0.15,
            "market_average": 0.20,
            "market_max": 0.30,
            "delta": 0.05,
            "percentage_difference": 25.0,
            "region": "US_CT",
            "is_above_average": True,
            "sample_count": 10,
            "supplier": "Eversource",
        }

        async def _fake_comparison(uid, cid=None):
            return canned_comparison

        svc.get_rate_comparison = _fake_comparison

        result = await svc.get_savings_estimate(TEST_USER_ID, monthly_kwh=900)

        assert result["has_data"] is True
        assert result["monthly_kwh"] == 900
        assert result["annual_kwh"] == 10800
        # user_rate 0.25 > market_min 0.15 → savings = (0.25 - 0.15) * 10800 = 1080
        assert result["estimated_annual_savings_vs_best"] == 1080.0
        assert result["estimated_monthly_savings_vs_best"] == pytest.approx(90.0, abs=0.01)
        assert result["current_annual_cost"] == pytest.approx(0.25 * 10800, abs=0.01)
        assert result["best_annual_cost"] == pytest.approx(0.15 * 10800, abs=0.01)

    @pytest.mark.asyncio
    async def test_savings_user_below_market(self):
        """User rate below market best → zero savings vs best."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        svc = ConnectionAnalyticsService(db)

        canned_comparison = {
            "has_data": True,
            "user_rate": 0.12,
            "market_min": 0.15,
            "market_average": 0.20,
            "market_max": 0.30,
            "delta": -0.08,
            "percentage_difference": -40.0,
            "region": "US_CT",
            "is_above_average": False,
            "sample_count": 10,
            "supplier": "UI",
        }

        async def _fake_comparison(uid, cid=None):
            return canned_comparison

        svc.get_rate_comparison = _fake_comparison

        result = await svc.get_savings_estimate(TEST_USER_ID, monthly_kwh=900)

        assert result["has_data"] is True
        # user_rate < market_min → no savings vs best
        assert result["estimated_annual_savings_vs_best"] == 0
        # user_rate < market_avg → no savings vs avg either
        assert result["estimated_annual_savings_vs_average"] == 0

    @pytest.mark.asyncio
    async def test_savings_no_rate_data(self):
        """Returns has_data=False when no comparison data."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        svc = ConnectionAnalyticsService(db)

        async def _fake_comparison(uid, cid=None):
            return {"has_data": False, "message": "No data"}

        svc.get_rate_comparison = _fake_comparison

        result = await svc.get_savings_estimate(TEST_USER_ID)

        assert result["has_data"] is False
        assert "message" in result


class TestCheckStaleConnectionsService:
    """Unit tests for ConnectionAnalyticsService.check_stale_connections."""

    @pytest.mark.asyncio
    async def test_stale_connections_detected(self):
        """Returns stale connections when last_scan_at is old."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        old_scan = datetime.now(timezone.utc) - timedelta(days=45)
        created = datetime.now(timezone.utc) - timedelta(days=60)

        rows = [
            _DictRow({
                "id": TEST_CONNECTION_ID,
                "connection_type": "direct",
                "label": "Home",
                "email_provider": None,
                "status": "active",
                "last_scan_at": old_scan,
                "updated_at": old_scan,
                "created_at": created,
            })
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        stale = await svc.check_stale_connections(TEST_USER_ID)

        assert len(stale) == 1
        assert stale[0]["connection_id"] == TEST_CONNECTION_ID
        assert stale[0]["connection_type"] == "direct"
        assert stale[0]["days_since_sync"] >= 45

    @pytest.mark.asyncio
    async def test_no_stale_connections(self):
        """Returns empty list when no stale connections."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        stale = await svc.check_stale_connections(TEST_USER_ID)

        assert stale == []

    @pytest.mark.asyncio
    async def test_stale_connection_null_last_scan_at(self):
        """Connection with NULL last_scan_at falls back to created_at for days calculation."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        created = datetime.now(timezone.utc) - timedelta(days=50)

        rows = [
            _DictRow({
                "id": TEST_CONNECTION_ID,
                "connection_type": "email_import",
                "label": None,
                "email_provider": "gmail",
                "status": "active",
                "last_scan_at": None,
                "updated_at": created,
                "created_at": created,
            })
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        stale = await svc.check_stale_connections(TEST_USER_ID)

        assert len(stale) == 1
        assert stale[0]["last_scan_at"] is None
        assert stale[0]["days_since_sync"] >= 50


class TestDetectRateChangesService:
    """Unit tests for ConnectionAnalyticsService.detect_rate_changes."""

    @pytest.mark.asyncio
    async def test_significant_rate_change_detected(self):
        """Rate change >=5% produces an alert."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        now = datetime.now(timezone.utc)

        rows = [
            _DictRow({
                "rate_per_kwh": 0.2700,
                "supplier_name": "Eversource",
                "extracted_at": now,
                "connection_id": TEST_CONNECTION_ID,
                "label": "Home",
                "prev_rate": 0.2400,  # 12.5% increase
            }),
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        alerts = await svc.detect_rate_changes(TEST_USER_ID)

        assert len(alerts) == 1
        assert alerts[0]["direction"] == "increase"
        assert alerts[0]["change_percentage"] > 5.0
        assert alerts[0]["current_rate"] == 0.27
        assert alerts[0]["previous_rate"] == 0.24

    @pytest.mark.asyncio
    async def test_no_significant_rate_change(self):
        """Rate change <5% produces no alert."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        now = datetime.now(timezone.utc)

        rows = [
            _DictRow({
                "rate_per_kwh": 0.2510,
                "supplier_name": "Eversource",
                "extracted_at": now,
                "connection_id": TEST_CONNECTION_ID,
                "label": "Home",
                "prev_rate": 0.2500,  # 0.4% change — below threshold
            }),
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        alerts = await svc.detect_rate_changes(TEST_USER_ID)

        assert alerts == []

    @pytest.mark.asyncio
    async def test_rate_change_skips_null_prev(self):
        """Rows with NULL prev_rate (first extraction) are skipped."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        now = datetime.now(timezone.utc)

        rows = [
            _DictRow({
                "rate_per_kwh": 0.25,
                "supplier_name": "Eversource",
                "extracted_at": now,
                "connection_id": TEST_CONNECTION_ID,
                "label": "Home",
                "prev_rate": None,  # No previous rate
            }),
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        alerts = await svc.detect_rate_changes(TEST_USER_ID)

        assert alerts == []

    @pytest.mark.asyncio
    async def test_rate_decrease_detected(self):
        """Rate decrease >=5% detected with direction='decrease'."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        now = datetime.now(timezone.utc)

        rows = [
            _DictRow({
                "rate_per_kwh": 0.2000,
                "supplier_name": "UI",
                "extracted_at": now,
                "connection_id": TEST_CONNECTION_ID,
                "label": "Office",
                "prev_rate": 0.2500,  # 20% decrease
            }),
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        alerts = await svc.detect_rate_changes(TEST_USER_ID)

        assert len(alerts) == 1
        assert alerts[0]["direction"] == "decrease"
        assert alerts[0]["change_percentage"] == pytest.approx(20.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_rate_change_no_rows(self):
        """Empty result set produces no alerts."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        alerts = await svc.detect_rate_changes(TEST_USER_ID)

        assert alerts == []


# ===========================================================================
# 2. Analytics API endpoint tests (HTTP layer)
# ===========================================================================


class TestAnalyticsComparisonEndpoint:
    """Tests for GET /connections/analytics/comparison."""

    def test_comparison_returns_data(self, client):
        """Endpoint returns comparison data from service."""
        db = _install_auth()

        now = datetime.now(timezone.utc)
        # Rate query result
        rate_row = _DictRow({
            "rate_per_kwh": 0.25,
            "supplier_name": "Eversource",
            "extracted_at": now,
            "connection_id": TEST_CONNECTION_ID,
            "connection_type": "direct",
        })
        rate_result = MagicMock()
        rate_result.mappings.return_value.first.return_value = rate_row

        # Region query result
        region_row = MagicMock()
        region_row.__getitem__ = lambda self, idx: "US_CT"
        region_result = MagicMock()
        region_result.fetchone.return_value = region_row

        # Market query result
        market_row = _DictRow({
            "avg_price": 0.20,
            "min_price": 0.15,
            "max_price": 0.28,
            "sample_count": 50,
        })
        market_result = MagicMock()
        market_result.mappings.return_value.first.return_value = market_row

        db.execute = AsyncMock(side_effect=[rate_result, region_result, market_result])

        response = client.get(f"{BASE}/analytics/comparison")

        assert response.status_code == 200
        data = response.json()
        assert data["has_data"] is True
        assert data["user_rate"] == 0.25
        assert data["market_average"] == 0.20

    def test_comparison_no_data(self, client):
        """Returns has_data=False when no extracted rates."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        response = client.get(f"{BASE}/analytics/comparison")

        assert response.status_code == 200
        data = response.json()
        assert data["has_data"] is False

    def test_comparison_with_connection_id_query(self, client):
        """connection_id query parameter is accepted."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        response = client.get(
            f"{BASE}/analytics/comparison",
            params={"connection_id": TEST_CONNECTION_ID},
        )

        assert response.status_code == 200

    def test_comparison_requires_paid_tier(self, client):
        """Free-tier user gets 403."""
        from main import app
        from api.dependencies import get_current_user, get_db_session
        from api.v1.connections import require_paid_tier

        app.dependency_overrides.pop(require_paid_tier, None)

        session = _session_data(tier="free")
        db = _mock_db()
        db.execute = AsyncMock(return_value=_scalar_result("free"))

        app.dependency_overrides[get_current_user] = lambda: session
        app.dependency_overrides[get_db_session] = lambda: db

        response = client.get(f"{BASE}/analytics/comparison")
        assert response.status_code == 403


class TestAnalyticsHistoryEndpoint:
    """Tests for GET /connections/analytics/history."""

    def test_history_returns_data_points(self, client):
        """Endpoint returns data points list."""
        db = _install_auth()

        now = datetime.now(timezone.utc)
        rows = [
            _DictRow({
                "rate_per_kwh": 0.22,
                "supplier_name": "Eversource",
                "extracted_at": now - timedelta(days=5),
                "billing_period_start": None,
                "billing_period_end": None,
                "connection_id": TEST_CONNECTION_ID,
                "connection_type": "direct",
                "label": "Home",
            }),
        ]
        history_result = MagicMock()
        history_result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=history_result)

        response = client.get(f"{BASE}/analytics/history")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["data_points"]) == 1
        assert data["data_points"][0]["rate"] == 0.22

    def test_history_empty(self, client):
        """Empty history returns zero data points."""
        db = _install_auth()
        history_result = MagicMock()
        history_result.mappings.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=history_result)

        response = client.get(f"{BASE}/analytics/history")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["data_points"] == []

    def test_history_custom_days(self, client):
        """Custom days parameter is accepted (1–1095)."""
        db = _install_auth()
        history_result = MagicMock()
        history_result.mappings.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=history_result)

        response = client.get(f"{BASE}/analytics/history", params={"days": 90})

        assert response.status_code == 200
        assert response.json()["days"] == 90

    def test_history_days_out_of_range(self, client):
        """days > 1095 is rejected with 422."""
        _install_auth()

        response = client.get(f"{BASE}/analytics/history", params={"days": 2000})
        assert response.status_code == 422

    def test_history_days_zero_rejected(self, client):
        """days=0 is rejected with 422 (ge=1)."""
        _install_auth()

        response = client.get(f"{BASE}/analytics/history", params={"days": 0})
        assert response.status_code == 422


class TestAnalyticsSavingsEndpoint:
    """Tests for GET /connections/analytics/savings."""

    def test_savings_with_data(self, client):
        """Endpoint returns savings estimate when rate data exists."""
        db = _install_auth()
        now = datetime.now(timezone.utc)

        rate_row = _DictRow({
            "rate_per_kwh": 0.25,
            "supplier_name": "Eversource",
            "extracted_at": now,
            "connection_id": TEST_CONNECTION_ID,
            "connection_type": "direct",
        })
        rate_result = MagicMock()
        rate_result.mappings.return_value.first.return_value = rate_row

        region_row = MagicMock()
        region_row.__getitem__ = lambda self, idx: "US_CT"
        region_result = MagicMock()
        region_result.fetchone.return_value = region_row

        market_row = _DictRow({
            "avg_price": 0.20,
            "min_price": 0.15,
            "max_price": 0.28,
            "sample_count": 20,
        })
        market_result = MagicMock()
        market_result.mappings.return_value.first.return_value = market_row

        db.execute = AsyncMock(side_effect=[rate_result, region_result, market_result])

        response = client.get(f"{BASE}/analytics/savings", params={"monthly_kwh": 800})

        assert response.status_code == 200
        data = response.json()
        assert data["has_data"] is True
        assert data["monthly_kwh"] == 800
        assert data["annual_kwh"] == 9600
        assert "estimated_annual_savings_vs_best" in data

    def test_savings_no_data(self, client):
        """Returns has_data=False when no rate data."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        response = client.get(f"{BASE}/analytics/savings")

        assert response.status_code == 200
        assert response.json()["has_data"] is False

    def test_savings_monthly_kwh_too_high(self, client):
        """monthly_kwh > 50000 is rejected with 422."""
        _install_auth()

        response = client.get(f"{BASE}/analytics/savings", params={"monthly_kwh": 99999})
        assert response.status_code == 422

    def test_savings_monthly_kwh_negative_rejected(self, client):
        """Negative monthly_kwh is rejected with 422."""
        _install_auth()

        response = client.get(f"{BASE}/analytics/savings", params={"monthly_kwh": -1})
        assert response.status_code == 422


class TestAnalyticsHealthEndpoint:
    """Tests for GET /connections/analytics/health."""

    def test_health_returns_stale_and_alerts(self, client):
        """Returns stale_connections and rate_change_alerts lists."""
        db = _install_auth()

        old_scan = datetime.now(timezone.utc) - timedelta(days=45)
        created_at = datetime.now(timezone.utc) - timedelta(days=60)

        stale_rows = [
            _DictRow({
                "id": TEST_CONNECTION_ID,
                "connection_type": "direct",
                "label": "Home",
                "email_provider": None,
                "status": "active",
                "last_scan_at": old_scan,
                "updated_at": old_scan,
                "created_at": created_at,
            })
        ]

        change_rows = [
            _DictRow({
                "rate_per_kwh": 0.27,
                "supplier_name": "Eversource",
                "extracted_at": datetime.now(timezone.utc),
                "connection_id": TEST_CONNECTION_ID,
                "label": "Home",
                "prev_rate": 0.24,
            }),
        ]

        stale_result = MagicMock()
        stale_result.mappings.return_value.all.return_value = stale_rows

        change_result = MagicMock()
        change_result.mappings.return_value.all.return_value = change_rows

        db.execute = AsyncMock(side_effect=[stale_result, change_result])

        response = client.get(f"{BASE}/analytics/health")

        assert response.status_code == 200
        data = response.json()
        assert "stale_connections" in data
        assert "rate_change_alerts" in data
        assert data["total_stale"] == 1
        assert data["total_alerts"] == 1

    def test_health_all_healthy(self, client):
        """Returns empty lists when all connections are healthy."""
        db = _install_auth()

        stale_result = MagicMock()
        stale_result.mappings.return_value.all.return_value = []

        change_result = MagicMock()
        change_result.mappings.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[stale_result, change_result])

        response = client.get(f"{BASE}/analytics/health")

        assert response.status_code == 200
        data = response.json()
        assert data["total_stale"] == 0
        assert data["total_alerts"] == 0
        assert data["stale_connections"] == []
        assert data["rate_change_alerts"] == []


# ===========================================================================
# 3. PATCH /connections/{connection_id} endpoint tests
# ===========================================================================


class TestUpdateConnectionEndpoint:
    """Tests for PATCH /connections/{connection_id}."""

    def test_update_label_success(self, client):
        """Label update succeeds for connection owner."""
        db = _install_auth()

        # First call: ownership check — connection found
        ownership_result = MagicMock()
        ownership_result.fetchone.return_value = MagicMock()

        # Second call: UPDATE
        update_result = MagicMock()

        db.execute = AsyncMock(side_effect=[ownership_result, update_result])

        response = client.patch(
            f"{BASE}/{TEST_CONNECTION_ID}",
            params={"label": "New Label"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["connection_id"] == TEST_CONNECTION_ID
        assert data["updated"] is True

    def test_update_connection_not_found(self, client):
        """Non-existent connection returns 404."""
        db = _install_auth()

        not_found_result = MagicMock()
        not_found_result.fetchone.return_value = None
        db.execute = AsyncMock(return_value=not_found_result)

        response = client.patch(
            f"{BASE}/{uuid4()}",
            params={"label": "Whatever"},
        )

        assert response.status_code == 404

    def test_update_connection_no_fields(self, client):
        """Request with no fields to update returns 400."""
        db = _install_auth()

        # Ownership check — found
        ownership_result = MagicMock()
        ownership_result.fetchone.return_value = MagicMock()
        db.execute = AsyncMock(return_value=ownership_result)

        # No label param provided
        response = client.patch(f"{BASE}/{TEST_CONNECTION_ID}")

        assert response.status_code == 400

    def test_update_connection_requires_paid_tier(self, client):
        """Free-tier user cannot update connections."""
        from main import app
        from api.dependencies import get_current_user, get_db_session
        from api.v1.connections import require_paid_tier

        app.dependency_overrides.pop(require_paid_tier, None)

        session = _session_data(tier="free")
        db = _mock_db()
        db.execute = AsyncMock(return_value=_scalar_result("free"))

        app.dependency_overrides[get_current_user] = lambda: session
        app.dependency_overrides[get_db_session] = lambda: db

        response = client.patch(
            f"{BASE}/{TEST_CONNECTION_ID}",
            params={"label": "Hacker"},
        )
        assert response.status_code == 403

    def test_update_connection_wrong_user(self, client):
        """Connection owned by another user returns 404."""
        db = _install_auth(user_id=TEST_USER_ID)

        not_found_result = MagicMock()
        not_found_result.fetchone.return_value = None
        db.execute = AsyncMock(return_value=not_found_result)

        response = client.patch(
            f"{BASE}/{TEST_CONNECTION_ID}",
            params={"label": "Steal"},
        )

        assert response.status_code == 404
